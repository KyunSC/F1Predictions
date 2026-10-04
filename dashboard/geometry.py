"""Exact circuit/year MultiViewer geometry, fetched without FastF1 sessions."""
import asyncio
import json
import math
from pathlib import Path
import httpx

CACHE = Path(__file__).resolve().parents[1] / 'cache' / 'track-maps'


def resolve(info):
    meeting = info.get('Meeting', {})
    circuit = meeting.get('Circuit', {})
    location = str(meeting.get('Location', '')).lower()
    name = str(circuit.get('ShortName', '')).lower()
    key = circuit.get('Key')
    year = str(info.get('StartDate', ''))[:4]
    if not str(key).isdigit() or not year.isdigit() or not location or not name:
        raise ValueError('Circuit key, year and physical venue metadata required')
    sepang = any(v in location for v in ('sepang', 'kuala lumpur'))
    if sepang and (not any(v in name for v in ('sepang', 'kuala lumpur')) or int(key) == 63):
        raise ValueError('Sepang venue conflicts with circuit metadata; refusing Sakhir geometry')
    if 'sakhir' in location and any(v in name for v in ('sepang', 'kuala lumpur')):
        raise ValueError('Sakhir/Sepang venue mismatch')
    return int(key), int(year)


def validate_provider(data, circuit, year, info):
    if data.get('circuitKey') != circuit or data.get('year') != year:
        raise ValueError('Provider geometry circuit/year differs from requested session')
    location = str(info.get('Meeting', {}).get('Location', '')).casefold()
    provider = str(data.get('location', '')).casefold()
    aliases = {'sepang', 'kuala lumpur', 'sepang international circuit'}
    if not provider or (location != provider and not {location, provider} <= aliases):
        raise ValueError('Provider physical venue differs from session')
    return validate(data)


def validate(data):
    x, y, rotation = data['x'], data['y'], data['rotation']
    if len(x) != len(y) or len(x) < 3 or len(x) > 100000:
        raise ValueError('Invalid outline length')
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in [*x, *y, rotation]):
        raise ValueError('Invalid outline coordinates or rotation')
    if max(x) == min(x) or max(y) == min(y):
        raise ValueError('Degenerate outline')
    return dict(outline=list(map(list, zip(x, y))), rotation=rotation,
                bounds=[min(x), min(y), max(x), max(y)], coordinate_system='F1 Cartesian decimetres')


class Geometry:
    def __init__(self, cache=CACHE):
        self.cache = cache
        self.key = None
        self.task = None
        self.value = {}

    def request(self, state):
        key = state.map_id()
        if key != self.key:
            if self.task:
                self.task.cancel()
            self.key = key
            self.value = dict(session_identity=key, geometry_id=None, available=False, reason='Loading circuit geometry')
            self.task = asyncio.create_task(self.load(key, dict(state.topics.get('SessionInfo', {})), state.synthetic))
        return dict(self.value)

    async def load(self, identity, info, synthetic):
        geometry_id = None
        provenance = None
        try:
            if synthetic:
                data = json.loads((Path(__file__).parent / 'demo-outline.json').read_text())
                provenance, geometry_id = 'Bundled synthetic demonstration', 'synthetic-demo'
            else:
                circuit, year = resolve(info)
                geometry_id = f'{circuit}/{year}'
                provenance = f'https://api.multiviewer.app/api/v1/circuits/{geometry_id}'
                path = self.cache / f'{circuit}-{year}.json'
                try:
                    data = json.loads(path.read_text())
                    validate_provider(data, circuit, year, info)
                except (OSError, ValueError, KeyError, TypeError):
                    async with httpx.AsyncClient(timeout=10) as client:
                        response = await client.get(provenance)
                        response.raise_for_status()
                        data = response.json()
                    validate_provider(data, circuit, year, info)
                    self.cache.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data))
            value = dict(validate(data), session_identity=identity, geometry_id=geometry_id, available=True,
                         reason=None, synthetic=synthetic, attribution='Synthetic demo' if synthetic else 'MultiViewer', provenance=provenance)
        except Exception as exc:
            value = dict(session_identity=identity, geometry_id=geometry_id, available=False, reason=str(exc),
                         outline=[], bounds=None, rotation=None, coordinate_system='F1 Cartesian decimetres',
                         synthetic=synthetic, attribution='Synthetic demo' if synthetic else 'MultiViewer', provenance=provenance)
        if self.key == identity:
            self.value = value
