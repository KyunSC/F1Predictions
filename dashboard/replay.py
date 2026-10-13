import json
import math
from pathlib import Path

from .state import HISTORY_SECONDS


class Replay:
    def __init__(self, state, path):
        self.state = state
        self.events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if not self.events:
            raise ValueError('Recording is empty')
        self.events.sort(key=lambda e: e['at'])  # stable ordering for simultaneous messages
        start = self.events[0]['at']
        self.events = [dict(e, at=e['at'] - start) for e in self.events]
        self.state.recording_has_positions = any(e['topic'] == 'Position.z' for e in self.events)
        self.state.recording_has_championship = any(e['topic'] == 'ChampionshipPrediction' for e in self.events)
        self.label = 'Demo replay' if path.name == 'demo.jsonl' else f'Recorded replay · {path.name}'
        if any(e.get('reconstructed') for e in self.events):
            self.label = f'Reconstructed archive replay · {path.name}'
        self.state.synthetic = path.resolve() == (Path(__file__).parent / "recordings/demo.jsonl").resolve()
        # Archive races carry hours of pre-race; open at lights out with earlier timing applied.
        self.start = next((e['at'] for e in self.events if e.get('reconstructed') and e['topic'] == 'SessionStatus'
                           and e['data'].get('Status') == 'Started'), 0.)
        self.position = 0.
        self.index = 0
        self.speed = 1
        self.paused = False
        self.seek(self.start)
        self.publish()

    def publish(self):
        self.state.replay = dict(label=self.label, paused=self.paused, speed=self.speed,
            position=self.position, duration=self.events[-1]['at'], ended=self.index == len(self.events))

    def control(self, action, speed=None, position=None):
        if action == 'restart':
            self.state.reset()
            self.position = 0.
            self.index = 0
            self.paused = False
            self.seek(self.start)
        elif action == 'pause': self.paused = True
        elif action == 'resume': self.paused = False
        elif action == 'speed' and speed in (1, 2, 5): self.speed = speed
        elif action == 'seek' and isinstance(position, (int, float)) and math.isfinite(position):
            # Rebuild from the start, as restart does, so every jump starts a fresh presentation generation.
            self.state.reset()
            self.index = 0
            self.seek(min(max(float(position), 0.), self.events[-1]['at']))
        else: raise ValueError('Use pause, resume, restart, speed (1, 2, 5) or seek (seconds)')
        self.advance(0)

    def advance(self, elapsed):
        if not self.paused:
            self.seek(min(self.events[-1]['at'], self.position + elapsed * self.speed))
        self.publish()

    def seek(self, position):
        """Move forward to `position`, applying every event up to it in order.

        Events older than the timing history window are applied without frames, which
        would be trimmed unseen; their combined state is recorded once as the predecessor."""
        self.position = position
        cutoff = position - HISTORY_SECONDS
        pending = False
        while self.index < len(self.events) and self.events[self.index]['at'] <= self.position:
            e = self.events[self.index]
            recent = e['at'] >= cutoff
            if pending and recent:
                self.state.record()
                pending = False
            self.state.apply(e['topic'], e['data'], e.get('timestamp'), now=e['at'], record=recent)
            pending = pending or not recent
            self.index += 1
        if pending:
            self.state.record()
