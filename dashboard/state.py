from .positions import Positions
import copy
import json
from datetime import datetime, timezone

TOPICS = ['SessionInfo', 'SessionStatus', 'DriverList', 'TimingData', 'TimingAppData',
          'TrackStatus', 'WeatherData', 'RaceControlMessages', 'LapCount', 'Position.z']


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
    if (info.get('Type') != 'Race' or not all(actual.values()) or
        any(actual[k] != (venue(expected.get(k)) if k == 'venue' else expected.get(k)) for k in actual)):
        return [], 'Predictions withheld: year, venue and race date must match a race session.'
    return export.get('drivers', []), None


class State:
    def __init__(self, predictions=None, mode='replay'):
        self.topics = {}
        self.positions = Positions()
        self.positions_enabled = True
        self.synthetic = False
        self.recording_has_positions = None
        self.predictions = copy.deepcopy(predictions)
        self.mode = mode
        self.connection = 'connecting' if mode == 'live' else 'replay'
        self.error = None
        self.last_update = None
        self.source_timestamp = None
        self.reconnects = 0
        self.live_verified = False
        self.replay = None

    def reset(self):
        self.positions.reset()
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

    def map_id(self):
        info = self.topics.get('SessionInfo', {})
        return json.dumps([self.positions.generation, info.get('Key'), info.get('StartDate'), info.get('Meeting')], sort_keys=True)

    def position_snapshot(self, now=None):
        clock = self.replay['position'] if self.replay else (now if now is not None else datetime.now(timezone.utc).timestamp())
        result = self.positions.snapshot(clock)
        if not self.positions_enabled:
            result.update(available=False, reason='Position subscription rejected; timing-only connection')
        if not result['reason'] and not result['available']:
            result['reason'] = ('No position data in this recording.' if self.recording_has_positions is False else 'Awaiting recorded coordinates') if self.replay else 'Awaiting free upstream coordinates'
        return dict(result, session_identity=self.map_id(), replay=self.replay, connection=self.connection, synthetic=self.synthetic)

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
                compound=stint.get('Compound'), stint_laps=stint.get('TotalLaps'), prediction=prediction_by_number.get(number)))
        drivers.sort(key=lambda d: (int(d['position']) if str(d['position']).isdigit() else 999, int(d['number'])))
        source_age = None
        if self.source_timestamp:
            try:
                source_age = max(0, now - datetime.fromisoformat(self.source_timestamp.replace('Z', '+00:00')).timestamp())
            except (ValueError, TypeError):
                pass
        age = None if self.last_update is None else max(0, now - self.last_update)
        messages = self.topics.get('RaceControlMessages', {}).get('Messages', {})
        return dict(map_id=self.map_id(), session=info, drivers=drivers, predictions=predictions, prediction_reason=reason,
            prediction_generated_at=self.predictions.get('generated_at') if self.predictions else None,
            messages=[m for m in messages.values() if isinstance(m, dict)][-100:][::-1], track=self.topics.get('TrackStatus', {}),
            weather=self.topics.get('WeatherData', {}), laps=self.topics.get('LapCount', {}),
            connection=dict(mode=self.mode, status=self.connection, error=self.error, reconnects=self.reconnects,
                last_update=self.last_update, source_timestamp=self.source_timestamp, age_seconds=age,
                source_age_seconds=source_age,
                stale=self.mode == 'live' and (age is None or age > 15 or (source_age is not None and source_age > 15) or self.connection != 'connected'),
                live_verified=self.live_verified), replay=self.replay)
