"""Run: python -m dashboard.smoke --seconds 45 (requires internet)."""
import argparse
import asyncio
import json
from pathlib import Path
from .live import connect
from .state import State
from .geometry import Geometry
import time

async def main(seconds):
    state = State(mode='live')
    try:
        await asyncio.wait_for(connect(state, Path('dashboard/recordings/live-smoke.jsonl')), seconds)
    except TimeoutError:
        pass
    except Exception as exc:
        state.error = f'{type(exc).__name__}: {exc}'
    snapshot = state.snapshot()
    geometry = Geometry()
    geometry.request(state)
    await geometry.task
    positions = state.position_snapshot()
    source = max(state.positions.latest.values(), default=None)
    print(json.dumps({'connection': snapshot['connection'], 'session': snapshot['session'],
        'position_samples': sum(len(s) for s in state.positions.samples.values()),
        'position_drivers': list(state.positions.samples), 'position_source_age': time.time()-source if source else None,
        'positions': {k:v for k,v in positions.items() if k != 'samples'},
        'geometry': {k:v for k,v in geometry.value.items() if k != 'outline'}, 'topics_received': list(state.topics), 'drivers': len(snapshot['drivers']),
        'timing_lines': len(state.topics.get('TimingData', {}).get('Lines', {}))}, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=45)
    asyncio.run(main(parser.parse_args().seconds))
