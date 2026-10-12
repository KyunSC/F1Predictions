"""Offline tests for the pit-loss table and "if pitted now" rejoin projections."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pandas as pd
from dashboard.pit_loss import build_table, loss_for, lookup, parse_seconds, project_rejoin, race_times, stop_losses

INFO = dict(Type='Race', Name='Race', StartDate='2025-10-05T20:00:00', GmtOffset='08:00:00',
            Meeting={'Location': 'Marina Bay', 'Circuit': {'Key': 61}})


def race(year, key, location, date, green=None, sc=None):
    losses = {kind: dict(stops=5, median_loss=v) for kind, v in (('green', green), ('sc', sc)) if v is not None}
    return dict(year=year, circuit_key=key, location=location, date=date, losses=losses)


TABLE = dict(races=[
    race(2023, 61, 'Marina Bay', '2023-09-17', green=28.0, sc=12.0),
    race(2024, 61, 'Marina Bay', '2024-09-22', green=30.0),
    race(2025, 61, 'Marina Bay', '2025-10-05', green=99.0, sc=99.0),
    race(2024, 7, 'Monza', '2024-09-01', green=24.0, sc=10.0),
    race(2025, 7, 'Monza', '2025-09-07', green=22.0),
    race(2024, 63, 'Sakhir', '2024-03-02', green=20.0, sc=8.0)])


def seconds(value):
    return pd.to_timedelta(value, unit='s') if value is not None else pd.NaT


def driver_laps(driver, times, status=None, stops=None):
    """Laps 1..n with cumulative session times; `stops` maps an in-lap to its lane time."""
    rows, clock, pit_in = [], 0.0, {}
    status, stops = status or {}, stops or {}
    for lap, time in enumerate(times, 1):
        if lap in stops:
            pit_in[lap] = clock + time - 5
        rows.append(dict(Driver=driver, LapNumber=float(lap), LapTime=seconds(time), TrackStatus=status.get(lap, '1'),
                         LapStartTime=seconds(clock), Time=seconds(clock + time), PitInTime=seconds(pit_in.get(lap)),
                         PitOutTime=seconds(pit_in[lap - 1] + stops[lap - 1] if lap - 1 in stops else None)))
        clock += time
    return rows


def laps_frame(stop_lap=10, in_status='1', out_status='1', lane=20.0, other_lanes=(20.0, 21.0)):
    """One driver lapping 90 s with a stop costing 20 s in and 5 s out, plus two reference stops."""
    times = [90.0] * 20
    times[stop_lap - 1:stop_lap + 1] = [110.0, 95.0]
    rows = driver_laps('AAA', times, {stop_lap: in_status, stop_lap + 1: out_status}, {stop_lap: lane})
    for driver, lane_time in zip(('BBB', 'CCC'), other_lanes):
        rows += driver_laps(driver, [110.0 if lap == 12 else 95.0 if lap == 13 else 90.0 for lap in range(1, 21)],
                            stops={12: lane_time})
    return pd.DataFrame(rows)


def neutralised_frame(in_status, out_status):
    """Laps 10-11 run at 130 s by the field; AAA pits on lap 10 and takes 140 + 135 s."""
    rows = driver_laps('AAA', [90.0] * 9 + [140.0, 135.0] + [90.0] * 9, {10: in_status, 11: out_status}, {10: 20.0})
    for driver in ('BBB', 'CCC', 'DDD'):
        rows += driver_laps(driver, [90.0] * 9 + [130.0, 130.0] + [90.0] * 9, {10: in_status, 11: out_status})
    return pd.DataFrame(rows)


def car(number, position, gap, interval=None, **extra):
    return dict(number=number, position=str(position), gap=gap, interval=interval, **extra)


class StopLossTests(unittest.TestCase):
    def test_normal_stop(self):
        self.assertEqual(stop_losses(laps_frame()), dict(green=[25.0, 25.0, 25.0], sc=[], vsc=[]))

    def test_mixed_status_stop_is_excluded(self):
        self.assertEqual(len(stop_losses(laps_frame(in_status='14'))['green']), 2)
        self.assertEqual(stop_losses(laps_frame(out_status='41'))['sc'], [])
        self.assertEqual(stop_losses(neutralised_frame('4', '1')), dict(green=[], sc=[], vsc=[]))
        self.assertEqual(stop_losses(neutralised_frame('45', '4')), dict(green=[], sc=[], vsc=[]))

    def test_safety_car_and_vsc_stops_use_nearby_cars(self):
        # 275 s for the two laps against 260 s for the cars that stayed out, not the driver's 90 s green laps.
        self.assertEqual(stop_losses(neutralised_frame('14', '4')), dict(green=[], sc=[15.0], vsc=[]))
        self.assertEqual(stop_losses(neutralised_frame('6', '671')), dict(green=[], sc=[], vsc=[15.0]))
        self.assertEqual(stop_losses(neutralised_frame('6', '4'))['vsc'], [])

    def test_lap_one_stop_is_excluded(self):
        self.assertEqual(len(stop_losses(laps_frame(stop_lap=1))['green']), 2)

    def test_long_lane_time_is_excluded(self):
        self.assertEqual(len(stop_losses(laps_frame(lane=40.0))['green']), 2)


class LookupTests(unittest.TestCase):
    def test_circuit_match_uses_only_earlier_races(self):
        # The 2025 Marina Bay race is the session itself, so its 99 s must not count.
        self.assertEqual(lookup(TABLE, INFO), dict(seconds=29.0, basis='circuit', condition='green', races=2, label='Marina Bay'))
        self.assertEqual(lookup(TABLE, INFO, 'sc'), dict(seconds=12.0, basis='circuit', condition='sc', races=1, label='Marina Bay'))

    def test_unknown_circuit_uses_all_tracks_median(self):
        info = dict(INFO, Meeting={'Location': 'Kuala Lumpur', 'Circuit': {'Key': 12}})
        # Circuit medians before the date: Marina Bay 29, Monza 23, Sakhir 20.
        self.assertEqual(lookup(TABLE, info), dict(seconds=23.0, basis='all-tracks median', condition='green', races=3))
        self.assertEqual(lookup(TABLE, info, 'sc'), dict(seconds=10.0, basis='all-tracks median', condition='sc', races=3))

    def test_location_fallback_without_circuit_key(self):
        info = dict(INFO, Meeting={'Location': 'Monza'})
        self.assertEqual(lookup(TABLE, info)['seconds'], 23.0)

    def test_race_on_or_after_session_date_is_ignored(self):
        info = dict(INFO, StartDate='2024-09-22T20:00:00')
        self.assertEqual(lookup(TABLE, info)['seconds'], 28.0)
        info = dict(INFO, StartDate='2023-09-01T12:00:00', GmtOffset='00:00:00')
        self.assertIsNone(lookup(TABLE, info)['seconds'])
        self.assertIsNone(lookup(TABLE, info, 'sc')['seconds'])

    def test_track_status_picks_the_condition(self):
        self.assertEqual(loss_for(TABLE, INFO, '1')['condition'], 'green')
        self.assertEqual(loss_for(TABLE, INFO, '4')['seconds'], 12.0)
        # No VSC history anywhere: fall back to the green-flag loss.
        self.assertEqual(loss_for(TABLE, INFO, '6'), lookup(TABLE, INFO))
        self.assertEqual(loss_for(TABLE, INFO, '7'), lookup(TABLE, INFO))
        self.assertEqual(loss_for(TABLE, INFO, '5')['condition'], 'red')
        self.assertIsNone(loss_for(TABLE, INFO, '5')['seconds'])

    def test_missing_table(self):
        self.assertEqual(lookup(None, INFO), dict(seconds=None, basis=None, condition='green', reason='No pit-loss table loaded.'))


class RaceTimeTests(unittest.TestCase):
    def test_parse_seconds(self):
        self.assertEqual(parse_seconds('+1.800'), 1.8)
        self.assertAlmostEqual(parse_seconds('1:02.345'), 62.345)
        for text in ('LAP 12', '+1 LAP', '+2 LAPS', '', None):
            self.assertIsNone(parse_seconds(text))

    def test_lapped_car_chains_interval(self):
        drivers = [car('1', 1, 'LAP 12', 'LAP 12'), car('2', 2, '+30.000', '+30.000'), car('3', 3, '+1 LAP', '+5.500')]
        self.assertEqual(race_times(drivers), {'1': 0.0, '2': 30.0, '3': 35.5})

    def test_missing_interval_breaks_chain(self):
        drivers = [car('1', 1, ''), car('2', 2, '+1 LAP', '+1 LAP'), car('3', 3, '+40.000', '+2.000')]
        self.assertEqual(race_times(drivers), {'1': 0.0})


class RejoinTests(unittest.TestCase):
    def test_rejoin_position_and_neighbours(self):
        drivers = [car('1', 1, 'LAP 5'), car('2', 2, '+5.000'), car('3', 3, '+20.000'), car('4', 4, '+30.000')]
        result = project_rejoin(drivers, 22)
        self.assertEqual(result['2'], dict(position=3, ahead='3', gap_ahead=7.0, behind='4', gap_behind=3.0, positions_lost=1))
        self.assertEqual(result['4'], dict(position=4, ahead='3', gap_ahead=32.0, behind=None, gap_behind=None, positions_lost=0))

    def test_pitting_and_retired_drivers(self):
        drivers = [car('1', 1, 'LAP 5'), car('2', 2, '+5.000', in_pit=True), car('3', 3, '+20.000', retired=True),
                   car('4', 4, '+30.000')]
        result = project_rejoin(drivers, 22)
        self.assertIsNone(result['2'])
        self.assertIsNone(result['3'])
        # The retired car is not a competitor; the car in the pits still is.
        self.assertEqual(result['1'], dict(position=2, ahead='2', gap_ahead=17.0, behind='4', gap_behind=8.0, positions_lost=1))


class BuildTableTests(unittest.TestCase):
    def test_skips_failed_and_future_races(self):
        schedule = pd.DataFrame([
            dict(EventName='Italian Grand Prix', Location='Monza', Session5='Race', Session5DateUtc=pd.Timestamp('2025-09-07 13:00')),
            dict(EventName='Azerbaijan Grand Prix', Location='Baku', Session5='Race', Session5DateUtc=pd.Timestamp('2025-09-21 11:00')),
            dict(EventName='Singapore Grand Prix', Location='Marina Bay', Session5='Race', Session5DateUtc=pd.Timestamp('2025-10-05 12:00'))])
        good = SimpleNamespace(load=Mock(), laps=laps_frame(), session_info={'Meeting': {'Location': 'Monza', 'Circuit': {'Key': 39}}})
        broken = SimpleNamespace(load=Mock(side_effect=RuntimeError('no data')))
        sessions = {'Italian Grand Prix': good, 'Azerbaijan Grand Prix': broken}
        log = []
        with patch('fastf1.get_event_schedule', return_value=schedule), \
                patch('fastf1.get_session', side_effect=lambda year, name, kind: sessions[name]) as get:
            table = build_table([2025], now=pd.Timestamp('2025-10-01', tz='UTC'), log=log.append)
        self.assertEqual([c.args for c in get.call_args_list], [(2025, 'Italian Grand Prix', 'R'), (2025, 'Azerbaijan Grand Prix', 'R')])
        self.assertEqual(table['races'], [dict(year=2025, event='Italian Grand Prix', circuit_key=39, location='Monza',
                                               date='2025-09-07', losses=dict(green=dict(stops=3, median_loss=25.0)))])
        self.assertTrue(any('Azerbaijan' in line and 'no data' in line for line in log))


if __name__ == '__main__':
    unittest.main()
