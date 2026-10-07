"""Offline replay diagnostics: python -m dashboard.diagnostics RECORDING [--geometry FILE]."""
from collections import Counter
import argparse
import json
import zlib
from pathlib import Path
from .geometry import validate_provider, resolve
from .replay import Replay
from .state import State


def summarize(path, geometry=None):
    state = State()
    replay = Replay(state, path)
    replay.advance(float('inf'))
    result = state.position_snapshot()['diagnostics']
    result.update(playback=replay.label, duration=replay.position,
                  geometry_available=False, geometry_reason='No geometry file supplied')
    if geometry:
        try:
            info = state.topics['SessionInfo']
            circuit, year = resolve(info)
            validated = validate_provider(json.loads(geometry.read_text()), circuit, year, info)
            x0,y0,x1,y1 = validated['bounds']
            margin = max(x1-x0,y1-y0)*.1
            # Inspect recorded measurements, not just the last parked cars.
            from .positions import decode_positions
            checked = inside = 0
            for event in replay.events:
                if event['topic'] != 'Position.z':
                    continue
                try:
                    samples = decode_positions(event['data'], Counter())
                except (ValueError, TypeError, KeyError, AttributeError, zlib.error):
                    continue  # Already counted by the replay decoder above.
                for sample in samples:
                    if sample['status'] in ('OnTrack', 0):
                        checked += 1
                        inside += x0-margin <= sample['x'] <= x1+margin and y0-margin <= sample['y'] <= y1+margin
            compatible = checked > 0 and inside / checked > .95
            result.update(geometry_available=compatible,
                          geometry_reason=None if compatible else 'Coordinates outside geometry bounds or no on-track samples',
                          on_track_samples=checked, samples_inside_bounds=inside)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            result['geometry_reason'] = str(exc)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording', type=Path)
    parser.add_argument('--geometry', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.recording, args.geometry), indent=2))
