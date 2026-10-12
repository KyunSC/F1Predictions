"""Green-flag pit-loss table from past races, and "if pitted now" rejoin projections.

Display only: nothing here feeds the prediction notebook. Lookups still use only races
that started strictly before the session being shown.
"""
import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from . import state

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT.parent / 'cache'
METHOD = ("green: in+out lap minus 2x the driver's local clean-lap median; "
          'sc/vsc: in-lap start to out-lap end minus the same span for the nearest non-pitting cars')
MIN_STOPS = 3
MIN_CLEAN_LAPS = 3
WINDOW = 5
NEIGHBOURS = 3
LOSS_RANGES = {'green': (10, 45), 'sc': (5, 35), 'vsc': (5, 35)}
LANE_FACTOR = 1.5
# TrackStatus codes: 1 green, 2 yellow, 4 safety car, 5 red flag, 6 VSC, 7 VSC ending.
TRACK_CONDITIONS = {'4': 'sc', '6': 'vsc', '7': 'vsc'}
LABELS = {'green': 'green-flag', 'sc': 'safety-car', 'vsc': 'VSC'}


def seconds(value):
    if value is None or pd.isna(value):
        return None
    return value.total_seconds() if hasattr(value, 'total_seconds') else float(value)


def codes(status):
    return set('' if status is None or pd.isna(status) else str(status))


def condition(in_status, out_status):
    """Track condition of a stop from its in- and out-lap status codes, or None when mixed."""
    stop_in, stop_out = codes(in_status), codes(out_status)
    if stop_in == stop_out == {'1'}:
        return 'green'
    if '5' in stop_in | stop_out:
        return None
    if '4' in stop_in and '4' in stop_out:
        return 'sc'
    if '6' in stop_in and stop_out & {'6', '7'} and '4' not in stop_in | stop_out:
        return 'vsc'
    return None


def green_loss(clean, lap_in, lap_out):
    """In- plus out-lap against the driver's own clean laps around the stop."""
    near = clean[(clean['Driver'] == lap_in['Driver']) & ((clean['LapNumber'] - lap_in['LapNumber']).abs() <= WINDOW)]
    in_time, out_time = seconds(lap_in['LapTime']), seconds(lap_out['LapTime'])
    if len(near) < MIN_CLEAN_LAPS or in_time is None or out_time is None:
        return None
    return in_time + out_time - 2 * statistics.median(seconds(t) for t in near['LapTime'])


def neutralised_loss(drivers, lap_in, lap_out):
    """In- plus out-lap against the nearest non-pitting cars over the same two laps.

    Under a safety car or VSC everyone laps slowly, so the driver's own green laps are
    no reference; cars next to it on track run under the same conditions.
    """
    own = seconds(lap_out['Time'] - lap_in['LapStartTime'])
    if own is None:
        return None
    spans = []
    for driver, laps in drivers.items():
        starts = laps['LapStartTime'].dropna()
        if driver == lap_in['Driver'] or starts.empty:
            continue
        number = (starts - lap_in['LapStartTime']).abs().idxmin()
        if number + 1 not in laps.index:
            continue
        first, second = laps.loc[number], laps.loc[number + 1]
        if any(pd.notna(lap[c]) for lap in (first, second) for c in ('PitInTime', 'PitOutTime')):
            continue
        span = seconds(second['Time'] - first['LapStartTime'])
        if span is not None:
            spans.append((abs(seconds(first['LapStartTime'] - lap_in['LapStartTime'])), span))
    nearest = [span for _, span in sorted(spans)[:NEIGHBOURS]]
    return own - statistics.median(nearest) if len(nearest) >= 2 else None


def stop_losses(laps):
    """Loss of each valid stop in one race, in seconds, by track condition."""
    laps = laps.assign(LapNumber=laps['LapNumber'].astype(float))
    clean = laps[laps['PitInTime'].isna() & laps['PitOutTime'].isna() & laps['LapTime'].notna() &
                 (laps['TrackStatus'].astype(str) == '1') & (laps['LapNumber'] > 1)]
    stops = []
    for _, lap_in in laps[laps['PitInTime'].notna()].iterrows():
        driver = laps[laps['Driver'] == lap_in['Driver']]
        out = driver[(driver['LapNumber'] == lap_in['LapNumber'] + 1) & driver['PitOutTime'].notna()]
        if out.empty:
            continue
        lap_out = out.iloc[0]
        lane = seconds(lap_out['PitOutTime'] - lap_in['PitInTime'])
        stops.append((lap_in, lap_out, lane))
    lanes = [lane for _, _, lane in stops if lane is not None and lane > 0]
    lane_limit = LANE_FACTOR * statistics.median(lanes) if lanes else None
    drivers = {driver: group.set_index('LapNumber') for driver, group in laps.groupby('Driver')}
    losses = {kind: [] for kind in LOSS_RANGES}
    for lap_in, lap_out, lane in stops:
        kind = condition(lap_in['TrackStatus'], lap_out['TrackStatus'])
        if kind is None or lap_in['LapNumber'] <= 1:
            continue
        if lane is None or lane_limit is None or lane > lane_limit:
            continue
        loss = green_loss(clean, lap_in, lap_out) if kind == 'green' else neutralised_loss(drivers, lap_in, lap_out)
        low, high = LOSS_RANGES[kind]
        if loss is not None and low <= loss <= high:
            losses[kind].append(loss)
    return losses


def race_start(event):
    """UTC start of the event's Grand Prix, or None."""
    for i in range(1, 6):
        if event.get(f'Session{i}') == 'Race':
            start = pd.Timestamp(event.get(f'Session{i}DateUtc'))
            if pd.isna(start):
                return None
            return start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC')
    return None


def build_table(seasons, now=None, log=print):
    import fastf1
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    now = now.tz_localize('UTC') if now.tzinfo is None else now
    races = []
    for year in seasons:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        for _, event in schedule.iterrows():
            start = race_start(event)
            if start is None or start >= now:
                continue
            name = event['EventName']
            try:
                session = fastf1.get_session(year, name, 'R')
                session.load(laps=True, telemetry=False, weather=False, messages=False)
                losses = stop_losses(session.laps)
            except Exception as exc:
                log(f'Skipped {year} {name}: {exc}')
                continue
            kept = {kind: dict(stops=len(v), median_loss=round(statistics.median(v), 2))
                    for kind, v in losses.items() if len(v) >= MIN_STOPS}
            if not kept:
                log(f'Skipped {year} {name}: valid stops ' + ', '.join(f'{k} {len(v)}' for k, v in losses.items()))
                continue
            meeting = (getattr(session, 'session_info', None) or {}).get('Meeting', {})
            races.append(dict(year=int(year), event=name, circuit_key=meeting.get('Circuit', {}).get('Key'),
                              location=meeting.get('Location') or event.get('Location'),
                              date=start.date().isoformat(), losses=kept))
            log(f'{year} {name}: ' + ', '.join(f'{k} {v["stops"]} stops, median {v["median_loss"]:.1f} s' for k, v in kept.items()))
    return dict(generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), method=METHOD, races=races)


def same_circuit(race, key, location):
    if key is not None and race.get('circuit_key') is not None:
        return str(race['circuit_key']) == str(key)
    return bool(location) and state.venue(race.get('location')) == location


def lookup(table, info, kind='green'):
    """Pit loss under `kind` for the session in `info`, from races that started before it."""
    if not table:
        return dict(seconds=None, basis=None, condition=kind, reason='No pit-loss table loaded.')
    race_date = state.identity(info)['race_date']
    races = [r for r in table.get('races', [])
             if kind in r.get('losses', {}) and (not race_date or r['date'] < race_date)]
    meeting = info.get('Meeting', {})
    key, location = meeting.get('Circuit', {}).get('Key'), state.venue(meeting.get('Location'))
    matched = [r['losses'][kind]['median_loss'] for r in races if same_circuit(r, key, location)]
    if matched:
        return dict(seconds=round(statistics.median(matched), 2), basis='circuit', condition=kind,
                    races=len(matched), label=meeting.get('Location'))
    circuits = {}
    for race in races:
        circuits.setdefault(race.get('circuit_key') or state.venue(race.get('location')), []).append(race['losses'][kind]['median_loss'])
    if not circuits:
        return dict(seconds=None, basis=None, condition=kind, reason=f'No {LABELS[kind]} pit-loss history before this session.')
    return dict(seconds=round(statistics.median(statistics.median(v) for v in circuits.values()), 2),
                basis='all-tracks median', condition=kind, races=len(circuits))


def loss_for(table, info, track_status=None):
    """Pit loss for the current track status; green-flag loss when that condition has no history."""
    if str(track_status) == '5':
        return dict(seconds=None, basis=None, condition='red', reason='Red flag: pit stops are not projected.')
    kind = TRACK_CONDITIONS.get(str(track_status), 'green')
    result = lookup(table, info, kind)
    return lookup(table, info) if result['seconds'] is None and kind != 'green' else result


def parse_seconds(text):
    text = str(text or '').strip().lstrip('+')
    if not text or 'LAP' in text.upper():
        return None
    try:
        minutes, _, rest = text.rpartition(':')
        return (int(minutes) * 60 if minutes else 0) + float(rest)
    except ValueError:
        return None


def race_times(drivers):
    """Seconds behind the leader per racing number, walking the cars in position order."""
    ordered = sorted((d for d in drivers if str(d.get('position')).isdigit()), key=lambda d: int(d['position']))
    times, previous = {}, None
    for i, driver in enumerate(ordered):
        gap, interval = parse_seconds(driver.get('gap')), parse_seconds(driver.get('interval'))
        if i == 0:
            time = 0.0
        elif gap is not None:
            time = gap
        elif interval is not None and previous is not None:
            time = previous + interval
        else:
            break
        times[driver['number']] = previous = time
    return times


def project_rejoin(drivers, loss):
    """Projected race position and neighbours if each driver pitted now."""
    times = race_times(drivers)
    running = {d['number']: times[d['number']] for d in drivers
               if d['number'] in times and not d.get('retired')}
    result = {}
    for driver in drivers:
        number = driver['number']
        if driver.get('in_pit') or driver.get('retired') or number not in times:
            result[number] = None
            continue
        new = times[number] + loss
        others = [(t, n) for n, t in running.items() if n != number]
        ahead = max((o for o in others if o[0] < new), default=None)
        behind = min((o for o in others if o[0] >= new), default=None)
        position = 1 + sum(t < new for t, _ in others)
        current = int(driver['position']) if str(driver.get('position')).isdigit() else None
        result[number] = dict(position=position,
                              ahead=ahead[1] if ahead else None, gap_ahead=round(new - ahead[0], 3) if ahead else None,
                              behind=behind[1] if behind else None, gap_behind=round(behind[0] - new, 3) if behind else None,
                              positions_lost=None if current is None else position - current)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build the median green-flag pit-loss table.')
    parser.add_argument('--seasons', type=int, nargs='+', required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'pit_loss.json')
    args = parser.parse_args(argv)
    import fastf1
    CACHE_DIR.mkdir(exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))
    table = build_table(args.seasons)
    args.out.write_text(json.dumps(table, indent=2) + '\n')
    print(f'Wrote {len(table["races"])} races to {args.out}')


if __name__ == '__main__':
    main()
