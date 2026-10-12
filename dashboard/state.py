from .positions import Positions
from . import pit_loss as pit
import copy
import json
from datetime import datetime, timezone

TOPICS = ['SessionInfo', 'SessionStatus', 'DriverList', 'TimingData', 'TimingAppData',
          'TrackStatus', 'WeatherData', 'RaceControlMessages', 'LapCount', 'ChampionshipPrediction', 'Position.z']


def merge(base, patch):
    """SignalR objects are sparse patches; numeric keys also patch arrays."""
    if isinstance(patch, list):
        patch = {str(i): value for i, value in enumerate(patch)}
    if isinstance(patch, dict):
        result = copy.deepcopy(base) if isinstance(base, dict) and not patch.get('_kf') else {}
        for key, value in patch.items():
            result[str(key)] = merge(result.get(str(key)), value)
        return result
    return copy.deepcopy(patch)


def venue(value):
    value = str(value or '').strip().casefold()
    return 'sepang' if value in {'sepang', 'kuala lumpur', 'sepang international circuit'} else value


def identity(info):
    date = str(info.get('StartDate', ''))[:10]
    if info.get('StartDate') and info.get('GmtOffset'):
        try:
            start = datetime.fromisoformat(info['StartDate'])
            if start.tzinfo is None:
                offset = info['GmtOffset']
                start = datetime.fromisoformat(info['StartDate'] + (offset if offset.startswith(('+', '-')) else '+' + offset))
            date = start.astimezone(timezone.utc).date().isoformat()
        except ValueError:
            return {'year': None, 'venue': '', 'race_date': ''}
    return {'year': int(date[:4]) if date[:4].isdigit() else None,
            'venue': venue(info.get('Meeting', {}).get('Location')), 'race_date': date}


def match_predictions(export, info):
    if not export:
        return [], 'No pre-race prediction export loaded.'
    actual = identity(info)
    expected = export.get('session', {})
    # A sprint is also Type 'Race' in the feed; exports name the session ('Race' or
    # 'Sprint') so a sprint prediction is not shown for the Grand Prix. Older exports
    # without a name match on year, venue and date only.
    if (info.get('Type') != 'Race' or not all(actual.values()) or
        any(actual[k] != (venue(expected.get(k)) if k == 'venue' else expected.get(k)) for k in actual) or
        ('name' in expected and info.get('Name') != expected['name'])):
        return [], 'Predictions withheld: year, venue, date and session name must match the predicted session.'
    return export.get('drivers', []), None


def championship(prediction, driver_list, info, missing_reason):
    """Drivers' standings if every car finished where it runs now, from F1's ChampionshipPrediction."""
    if info.get('Type') != 'Race':
        return dict(rows=[], reason='Championship projection is shown only in races and sprints.')
    rows = []
    for number, entry in (prediction or {}).get('Drivers', {}).items():
        if not isinstance(entry, dict) or entry.get('PredictedPosition') is None or entry.get('PredictedPoints') is None:
            continue
        driver = driver_list.get(str(number), {})
        current_points = entry.get('CurrentPoints', entry['PredictedPoints'])
        current_position = entry.get('CurrentPosition')
        rows.append(dict(number=str(number), code=driver.get('Tla'), name=driver.get('FullName'),
                         team=driver.get('TeamName'), color=driver.get('TeamColour'),
                         position=entry['PredictedPosition'], points=entry['PredictedPoints'],
                         current_position=current_position, current_points=current_points,
                         points_gained=entry['PredictedPoints'] - current_points,
                         positions_gained=None if current_position is None else current_position - entry['PredictedPosition']))
    rows.sort(key=lambda r: (r['position'], int(r['number']) if r['number'].isdigit() else 999))
    return dict(rows=rows, reason=None if rows else missing_reason)


class State:
    def __init__(self, predictions=None, mode='replay', pit_loss=None):
        self.topics = {}
        self.timing_history = []
        self.presentation_frozen = None
        self.positions = Positions()
        self.positions_enabled = True
        self.synthetic = False
        self.recording_has_positions = None
        self.recording_has_championship = None
        self.predictions = copy.deepcopy(predictions)
        self.pit_loss = pit_loss
        self.pit_loss_cache = (None, None)
        self.mode = mode
        self.connection = 'connecting' if mode == 'live' else 'replay'
        self.error = None
        self.last_update = None
        self.source_timestamp = None
        self.reconnects = 0
        self.live_verified = False
        self.replay = None
        self.archive = None  # Session-picker import job, carried across State rebuilds by app.py.

    def reset(self):
        self.positions.reset()
        self.timing_history = []
        self.presentation_frozen = None
        self.live_verified = False
        self.topics = {}
        self.last_update = None
        self.source_timestamp = None

    def apply(self, topic, payload, timestamp=None, now=None):
        if topic == 'Position.z':
            self.positions.apply(payload, now if now is not None else datetime.now(timezone.utc).timestamp())
            return
        if topic not in TOPICS:
            return
        if isinstance(payload, str):
            payload = json.loads(payload)
        if topic == 'SessionInfo':
            old = self.topics.get(topic, {})
            if any(k in payload and k in old and payload[k] != old[k] for k in ('Key', 'StartDate')):
                self.reset()
        self.topics[topic] = merge(self.topics.get(topic), payload)
        self.last_update = now if now is not None else datetime.now(timezone.utc).timestamp()
        self.source_timestamp = timestamp
        # Keep the predecessor as well as recent changes: a quiet timing topic
        # must still have a state at the shared buffered presentation moment.
        frame = self.snapshot(now=self.last_update)
        frame['presentation_timestamp'] = self.last_update
        self.timing_history.append(frame)
        cutoff = self.last_update - 5
        while len(self.timing_history) > 1 and self.timing_history[1]['presentation_timestamp'] < cutoff:
            self.timing_history.pop(0)

    def map_id(self):
        info = self.topics.get('SessionInfo', {})
        return json.dumps([self.positions.generation, info.get('Key'), info.get('StartDate'), info.get('Meeting')], sort_keys=True)

    def pit_loss_for(self, info):
        # Snapshots run on every message; the lookup only changes with the session and track status.
        key, status = self.map_id(), str(self.topics.get('TrackStatus', {}).get('Status', ''))
        if self.pit_loss_cache[0] != key:
            self.pit_loss_cache = (key, {})
        cache = self.pit_loss_cache[1]
        if status not in cache:
            cache[status] = pit.loss_for(self.pit_loss, info, status)
        return cache[status]

    def position_snapshot(self, now=None):
        clock = self.replay['position'] if self.replay else (now if now is not None else datetime.now(timezone.utc).timestamp())
        if self.connection in ('connecting', 'reconnecting'):
            clock = self.presentation_frozen if self.presentation_frozen is not None else clock
        else:
            self.presentation_frozen = clock
        result = self.positions.snapshot(clock)
        if not self.positions_enabled:
            result.update(available=False, reason='Position subscription rejected; timing-only connection')
        if not result['reason'] and not result['available']:
            result['reason'] = ('No position data in this recording.' if self.recording_has_positions is False else 'Awaiting recorded coordinates') if self.replay else (self.positions.auth_problem or 'Awaiting upstream coordinates')
        known = {n for n in self.topics.get('DriverList', {}) if n.isdigit()}
        result['diagnostics']['missing_drivers'] = sorted(known - self.positions.latest.keys(), key=int)
        result['diagnostics']['unlisted_numbers'] = sorted(self.positions.latest.keys() - known, key=int)
        return dict(result, session_identity=self.map_id(), replay=self.replay, connection=self.connection, synthetic=self.synthetic,
                    presentation_timestamp=clock - 1, timing_history=self.timing_history,
                    current=self.snapshot(now=now))

    def snapshot(self, now=None):
        now = now if now is not None else datetime.now(timezone.utc).timestamp()
        info = self.topics.get('SessionInfo', {})
        predictions, reason = match_predictions(self.predictions, info)
        prediction_by_number = {str(d['racing_number']): d for d in predictions}
        timing = self.topics.get('TimingData', {}).get('Lines', {})
        tyres = self.topics.get('TimingAppData', {}).get('Lines', {})
        drivers = []
        for number, driver in self.topics.get('DriverList', {}).items():
            if not isinstance(driver, dict) or not number.isdigit():
                continue
            line = timing.get(number, {})
            stints = tyres.get(number, {}).get('Stints', {})
            stint_keys = [k for k in stints if k.isdigit()]
            stint = stints[max(stint_keys, key=int)] if stint_keys else {}
            drivers.append(dict(number=number, name=driver.get('FullName'), code=driver.get('Tla'),
                team=driver.get('TeamName'), color=driver.get('TeamColour'), position=line.get('Position'),
                gap=line.get('GapToLeader'), interval=line.get('IntervalToPositionAhead', {}).get('Value'),
                last_lap=line.get('LastLapTime', {}).get('Value'), best_lap=line.get('BestLapTime', {}).get('Value'),
                compound=stint.get('Compound'), stint_laps=stint.get('TotalLaps'), prediction=prediction_by_number.get(number),
                in_pit=bool(line.get('InPit')), pit_stops=line.get('NumberOfPitStops'),
                retired=bool(line.get('Retired') or line.get('Stopped'))))
        drivers.sort(key=lambda d: (int(d['position']) if str(d['position']).isdigit() else 999, int(d['number'])))
        pit_loss = self.pit_loss_for(info)
        race = info.get('Type') == 'Race'
        if not race and not pit_loss.get('reason'):
            pit_loss = dict(pit_loss, reason='Pit rejoin projections are shown only in races.')
        rejoin = pit.project_rejoin(drivers, pit_loss['seconds']) if race and pit_loss['seconds'] is not None else {}
        for driver in drivers:
            driver['pit_rejoin'] = rejoin.get(driver['number'])
        standings = championship(self.topics.get('ChampionshipPrediction'), self.topics.get('DriverList', {}), info,
            'No championship data in this recording; re-import it with dashboard.historical.'
            if self.recording_has_championship is False else 'Awaiting championship data from the timing feed.')
        source_age = None
        if self.source_timestamp:
            try:
                source_age = max(0, now - datetime.fromisoformat(self.source_timestamp.replace('Z', '+00:00')).timestamp())
            except (ValueError, TypeError):
                pass
        age = None if self.last_update is None else max(0, now - self.last_update)
        messages = self.topics.get('RaceControlMessages', {}).get('Messages', {})
        return dict(map_id=self.map_id(), session_identity=self.map_id(), generation=self.positions.generation, presentation_timestamp=self.last_update, session=info, drivers=drivers, predictions=predictions, prediction_reason=reason, pit_loss=pit_loss, standings=standings,
            prediction_generated_at=self.predictions.get('generated_at') if self.predictions else None,
            messages=[m for m in messages.values() if isinstance(m, dict)][-100:][::-1], track=self.topics.get('TrackStatus', {}),
            weather=self.topics.get('WeatherData', {}), laps=self.topics.get('LapCount', {}),
            connection=dict(mode=self.mode, status=self.connection, error=self.error, reconnects=self.reconnects,
                last_update=self.last_update, source_timestamp=self.source_timestamp, age_seconds=age,
                source_age_seconds=source_age,
                stale=self.mode == 'live' and (age is None or age > 15 or (source_age is not None and source_age > 15) or self.connection != 'connected'),
                live_verified=self.live_verified), replay=self.replay, archive=self.archive)
