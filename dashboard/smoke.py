"""Run: python -m dashboard.smoke --seconds 45 (requires internet)."""
import argparse
import asyncio
import json
from pathlib import Path
from .live import connect
from .state import State

async def main(seconds):
    state = State(mode='live')
    try:
        await asyncio.wait_for(connect(state, Path('dashboard/recordings/live-smoke.jsonl')), seconds)
    except TimeoutError:
        pass
    except Exception as exc:
        state.error = f'{type(exc).__name__}: {exc}'
    snapshot = state.snapshot()
    print(json.dumps({'connection': snapshot['connection'], 'session': snapshot['session'],
        'topics_received': list(state.topics), 'drivers': len(snapshot['drivers']),
        'timing_lines': len(state.topics.get('TimingData', {}).get('Lines', {}))}, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=45)
    asyncio.run(main(parser.parse_args().seconds))
