"""Offline tests for the pit strategy advisor."""
import unittest
from dashboard.state import State
from dashboard.strategy import advise, plan, tyre_lives

GREEN = dict(seconds=22.0, condition='green')
SC = dict(seconds=12.0, condition='sc')
VSC = dict(seconds=14.0, condition='vsc')


def stint(compound, age, start=0):
    return dict(Compound=compound, TotalLaps=age, StartLaps=start)


def tyres(**cars):
    """Racing number (as `n<number>`) to its stints, oldest first."""
    return {name[1:]: {'Stints': {str(i): s for i, s in enumerate(stints)}} for name, stints in cars.items()}


def car(number, position, gap, team='T' , rejoin_lost=None, **extra):
    rejoin = None if rejoin_lost is None else dict(position=position + rejoin_lost, positions_lost=rejoin_lost)
    return dict(number=number, position=str(position), gap=gap, team=team + number, pit_rejoin=rejoin, **extra)


LAPS = dict(CurrentLap=20, TotalLaps=50)
# Default lives for 50 laps: soft 15, medium 22, hard 30.


class StrategyTests(unittest.TestCase):
    def test_tyre_life_defaults_until_the_race_shows_its_own(self):
        lives = tyre_lives(tyres(n1=[stint('MEDIUM', 18)]), 50)
        self.assertEqual(lives['MEDIUM'], dict(laps=22, basis='default', stints=0))
        lives = tyre_lives(tyres(n1=[stint('MEDIUM', 18), stint('HARD', 2)], n2=[stint('MEDIUM', 16), stint('HARD', 2)],
                                 n3=[stint('MEDIUM', 20), stint('HARD', 2)], n4=[stint('MEDIUM', 4), stint('HARD', 2)],
                                 n5=[stint('SOFT', 12, 6), stint('HARD', 2)]), 50)
        # The 4-lap stint is a lap-one stop and the used soft ran only 6 laps: neither counts.
        self.assertEqual(lives['MEDIUM'], dict(laps=18, basis='race', stints=3))
        self.assertEqual(lives['SOFT']['basis'], 'default')

    def test_plan_counts_stops_and_the_window(self):
        lives = tyre_lives({}, 50)
        p = plan([stint('MEDIUM', 10)], 20, 50, lives)
        # Medium runs to age 24 (lap 34); hards fit from lap 18 to the flag; window opens at age 17.
        self.assertEqual((p['stops'], p['window'], p['must_change']), (1, [27, 34], True))
        p = plan([stint('MEDIUM', 12), stint('HARD', 20)], 40, 50, lives)
        self.assertEqual((p['stops'], p['window'], p['reaches_end']), (0, None, True))
        # Still one compound used: a stop is due even though the tyre would last.
        p = plan([stint('HARD', 20)], 40, 50, lives)
        self.assertEqual((p['stops'], p['window']), (1, [43, 49]))
        # Intermediates lift the two-compound rule.
        self.assertEqual(plan([stint('INTERMEDIATE', 10), stint('MEDIUM', 5)], 45, 50, lives)['stops'], 0)
        # Softs then hards reach the flag in one stop; with 20 more laps it takes two.
        self.assertEqual(plan([stint('SOFT', 2)], 5, 50, lives)['stops'], 1)
        self.assertEqual(plan([stint('SOFT', 2)], 5, 70, lives)['stops'], 2)
        self.assertIsNone(plan([], 5, 50, lives))
        self.assertIsNone(plan([stint('UNKNOWN', 3)], 5, 50, lives))

    def test_green_flag_calls(self):
        drivers = [car('1', 1, 'LAP 20'), car('4', 2, '+3.0'), car('16', 3, '+8.0'), car('44', 4, '+12.0'), car('63', 5, '+20.0')]
        calls, summary = advise(drivers, tyres(n1=[stint('MEDIUM', 10)], n4=[stint('MEDIUM', 18)], n16=[stint('SOFT', 17)],
                                               n44=[stint('MEDIUM', 18), stint('HARD', 2)], n63=[stint('HARD', 20, 3)]),
                                LAPS, '1', GREEN, 22.0)
        self.assertEqual((calls['1']['call'], calls['1']['label']), ('stay_out', 'L27–34'))
        self.assertEqual((calls['4']['call'], calls['4']['window']), ('window', [20, 26]))
        self.assertEqual(calls['16']['call'], 'box')
        self.assertIn('past expected life', calls['16']['reason'])
        self.assertEqual((calls['44']['call'], calls['44']['label']), ('no_stop', 'TO END'))
        self.assertEqual(calls['63']['call'], 'stay_out')
        self.assertEqual((summary['condition'], summary['saving'], summary['boxes']), ('green', None, ['16']))

    def test_safety_car_boxes_cars_that_need_a_stop_or_lose_nothing(self):
        drivers = [car('1', 1, 'LAP 30', rejoin_lost=2), car('4', 2, '+1.0', rejoin_lost=2), car('16', 3, '+2.0', rejoin_lost=1),
                   car('44', 4, '+30.0', rejoin_lost=0), car('63', 5, '+31.0', rejoin_lost=0), car('81', 6, '+40.0', rejoin_lost=0),
                   car('10', 7, '+42.0', rejoin_lost=0, in_pit=True)]
        laps = dict(CurrentLap=30, TotalLaps=50)
        stints = tyres(n1=[stint('MEDIUM', 18)],                        # needs a stop; hards reach the flag
                       n4=[stint('MEDIUM', 12), stint('HARD', 10)],     # can reach the flag; boxing loses 2 places
                       n16=[stint('MEDIUM', 12), stint('HARD', 2)],     # just stopped
                       n44=[stint('MEDIUM', 12), stint('HARD', 10)],    # can reach the flag, but stops for free
                       n63=[stint('HARD', 6)],                          # young hards, still needs a medium later
                       n81=[stint('SOFT', 10), stint('MEDIUM', 19)],    # mediums will not last 21 laps
                       n10=[stint('MEDIUM', 20)])
        calls, summary = advise(drivers, stints, laps, '4', SC, 22.0)
        self.assertEqual(calls['1']['call'], 'box')
        self.assertEqual(calls['1']['reason'], 'Cheap stop: saves 10.0 s on a green-flag stop, rejoins P3')
        self.assertEqual((calls['4']['call'], calls['4']['reason']), ('stay_out', 'Keep track position: boxing loses 2 places'))
        self.assertEqual((calls['16']['call'], calls['16']['reason']), ('stay_out', 'Stopped 2 laps ago'))
        self.assertEqual(calls['44']['call'], 'box')
        self.assertIn('Free stop', calls['44']['reason'])
        self.assertEqual(calls['63']['call'], 'box')  # 21 laps to go: one set of mediums or hards reaches the flag
        self.assertEqual(calls['10']['call'], 'in_pit')
        self.assertEqual((summary['condition'], summary['saving'], summary['loss']), ('sc', 10.0, 12.0))
        self.assertEqual(summary['boxes'], ['1', '44', '63', '81'])

        # Young tyres early in the race: boxing still leaves another stop to make.
        calls, _ = advise([car('63', 1, 'LAP 10', rejoin_lost=0)], tyres(n63=[stint('SOFT', 4)]),
                          dict(CurrentLap=10, TotalLaps=50), '4', SC, 22.0)
        self.assertEqual(calls['63']['call'], 'consider')
        self.assertEqual(calls['63']['reason'], 'Tyres only 4/15 laps old; boxing saves 10.0 s on a green-flag stop without losing a place '
                                                'but still needs another stop')
        # Too late for fresh tyres to pay back.
        calls, _ = advise([car('1', 1, 'LAP 49', rejoin_lost=0)], tyres(n1=[stint('MEDIUM', 12), stint('HARD', 25)]),
                          dict(CurrentLap=49, TotalLaps=50), '4', SC, 22.0)
        self.assertEqual(calls['1']['call'], 'stay_out')

    def test_team_mates_boxing_together_are_flagged(self):
        drivers = [dict(car('1', 1, 'LAP 30', rejoin_lost=1), team='Red'), dict(car('22', 2, '+1.5', rejoin_lost=1), team='Red'),
                   dict(car('4', 3, '+9.0', rejoin_lost=1), team='Orange')]
        stints = tyres(n1=[stint('MEDIUM', 25)], n22=[stint('MEDIUM', 25)], n4=[stint('MEDIUM', 25)])
        calls, _ = advise(drivers, stints, dict(CurrentLap=30, TotalLaps=50), '6', VSC, 22.0)
        self.assertEqual([calls[n]['stack'] for n in ('1', '22', '4')], [None, '1', None])
        # A VSC that is ending may turn green before the car reaches the pit lane.
        calls, _ = advise(drivers, stints, dict(CurrentLap=30, TotalLaps=50), '7', VSC, 22.0)
        self.assertEqual(calls['1']['call'], 'consider')
        self.assertTrue(calls['1']['reason'].startswith('VSC ending'))

    def test_missing_inputs_and_red_flag(self):
        drivers = [car('1', 1, 'LAP 30')]
        self.assertIn('Red flag', advise(drivers, tyres(n1=[stint('HARD', 5)]), LAPS, '5', {}, 22.0)[1]['reason'])
        self.assertIn('Awaiting', advise(drivers, {}, LAPS, '1', GREEN, 22.0)[1]['reason'])
        # SC with no SC history: the pit loss falls back to green and the summary says so.
        calls, summary = advise(drivers, tyres(n1=[stint('MEDIUM', 18)]), LAPS, '4', GREEN, 22.0)
        self.assertIsNone(summary['saving'])
        self.assertIn('assume the green-flag loss', summary['reason'])
        self.assertEqual(calls['1']['reason'], 'Cheap stop: same loss as a green-flag stop, rejoin unknown')

    def test_snapshot_carries_strategy_in_races_only(self):
        info = dict(Key=1, Type='Race', Name='Race', StartDate='2026-10-25T15:00:00', GmtOffset='-05:00:00',
                    Meeting={'Location': 'Austin', 'Circuit': {'Key': 9}})
        table = dict(races=[dict(circuit_key=9, location='Austin', date='2025-10-19',
                                 losses={'green': {'median_loss': 20.0}, 'sc': {'median_loss': 11.0}})])
        state = State(pit_loss=table)
        state.apply('SessionInfo', info)
        state.apply('DriverList', {'1': {'Tla': 'VER', 'TeamName': 'Red Bull'}, '4': {'Tla': 'NOR', 'TeamName': 'McLaren'}})
        state.apply('TimingData', {'Lines': {'1': {'Position': '1', 'GapToLeader': 'LAP 30'}, '4': {'Position': '2', 'GapToLeader': '+25.0'}}})
        state.apply('TimingAppData', {'Lines': {'1': {'Stints': [stint('MEDIUM', 25)]}, '4': {'Stints': [stint('HARD', 25)]}}})
        state.apply('LapCount', {'CurrentLap': 30, 'TotalLaps': 56})
        state.apply('TrackStatus', {'Status': '4', 'Message': 'SCDeployed'})
        snap = state.snapshot()
        drivers = {d['number']: d for d in snap['drivers']}
        self.assertEqual((snap['strategy']['condition'], snap['strategy']['saving']), ('sc', 9.0))
        self.assertEqual(drivers['1']['strategy']['call'], 'box')
        self.assertEqual(drivers['1']['pit_rejoin']['position'], 1)  # 11 s loss against a 25 s gap
        state.apply('SessionInfo', {'Type': 'Qualifying', 'Name': 'Qualifying'})
        snap = state.snapshot()
        self.assertIn('only in races', snap['strategy']['reason'])
        self.assertTrue(all(d['strategy'] is None for d in snap['drivers']))


if __name__ == '__main__':
    unittest.main()
