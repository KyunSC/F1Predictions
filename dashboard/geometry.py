"""Exact circuit/year MultiViewer geometry, fetched without FastF1 sessions.

When MultiViewer has no outline for the circuit (404, e.g. Sepang), the outline is
traced from this session's own car coordinates instead; another circuit is never used.
"""
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


# Feed Location and MultiViewer location name the same venue differently.
VENUE_ALIASES = [{'sepang', 'kuala lumpur', 'sepang international circuit'},
                 {'marina bay', 'singapore'}]


def validate_provider(data, circuit, year, info):
    # MultiViewer serves the circuit's most recent layout it has, which can be an
    # earlier season (Singapore 2026 returns the 2023 Marina Bay layout). Never accept
    # a later season's layout.
    provider_year = data.get('year')
    if data.get('circuitKey') != circuit or not isinstance(provider_year, int) or provider_year > year:
        raise ValueError('Provider geometry circuit/year differs from requested session')
    location = str(info.get('Meeting', {}).get('Location', '')).casefold()
    provider = str(data.get('location', '')).casefold()
    if not provider or (location != provider and not any({location, provider} <= a for a in VENUE_ALIASES)):
        raise ValueError('Provider physical venue differs from session')
    return dict(validate(data), layout_year=provider_year)


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
        self.unpublished = set()  # circuit/year ids MultiViewer answered 404 for

    def request(self, state):
        key = state.map_id()
        if key != self.key:
            if self.task:
                self.task.cancel()
            self.key = key
            self.value = dict(session_identity=key, geometry_id=None, available=False, reason='Loading circuit geometry')
            self.task = asyncio.create_task(self.load(key, dict(state.topics.get('SessionInfo', {})), state.synthetic,
                                                      state.positions.outline))
        elif self.value.get('pending') and self.task.done():
            # Waiting for enough cars to complete a lap; try tracing again.
            self.task = asyncio.create_task(self.load(key, dict(state.topics.get('SessionInfo', {})), state.synthetic,
                                                      state.positions.outline))
        return dict(self.value)

    async def load(self, identity, info, synthetic, trace=lambda: None):
        geometry_id = None
        provenance = None
        traced = False
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
                    data = None
                    if geometry_id not in self.unpublished:
                        async with httpx.AsyncClient(timeout=10) as client:
                            response = await client.get(provenance)
                        if response.status_code == 404:
                            self.unpublished.add(geometry_id)
                        else:
                            response.raise_for_status()
                            data = response.json()
                            validate_provider(data, circuit, year, info)
                            self.cache.mkdir(parents=True, exist_ok=True)
                            path.write_text(json.dumps(data))
                    if data is None:
                        outline = trace()
                        provenance = f'Traced from this session\'s Position.z coordinates (MultiViewer has no outline for {geometry_id})'
                        if outline is None:
                            value = dict(session_identity=identity, geometry_id=geometry_id, available=False, pending=True,
                                         reason='No published outline for this circuit; tracing one once cars complete a lap',
                                         outline=[], bounds=None, rotation=None, coordinate_system='F1 Cartesian decimetres',
                                         synthetic=False, attribution='Traced from car coordinates', provenance=provenance)
                            if self.key == identity:
                                self.value = value
                            return
                        data = dict(x=[p[0] for p in outline], y=[p[1] for p in outline], rotation=0, year=year)
                        traced = True
            attribution = ('Synthetic demo' if synthetic else
                           f'Traced from {data["year"]} car coordinates' if traced else f"MultiViewer · {data['year']} layout")
            value = dict(validate(data), session_identity=identity, geometry_id=geometry_id, available=True,
                         reason=None, synthetic=synthetic, attribution=attribution, provenance=provenance)
        except Exception as exc:
            value = dict(session_identity=identity, geometry_id=geometry_id, available=False, reason=str(exc),
                         outline=[], bounds=None, rotation=None, coordinate_system='F1 Cartesian decimetres',
                         synthetic=synthetic, attribution='Synthetic demo' if synthetic else 'MultiViewer', provenance=provenance)
        if self.key == identity:
            self.value = value
