import json
from pathlib import Path


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
        self.label = 'Demo replay' if path.name == 'demo.jsonl' else f'Recorded replay · {path.name}'
        if any(e.get('reconstructed') for e in self.events):
            self.label = f'Reconstructed archive replay · {path.name}'
        self.state.synthetic = path.resolve() == (Path(__file__).parent / "recordings/demo.jsonl").resolve()
        self.position = 0.
        self.index = 0
        self.speed = 1
        self.paused = False
        self.publish()

    def publish(self):
        self.state.replay = dict(label=self.label, paused=self.paused, speed=self.speed,
            position=self.position, duration=self.events[-1]['at'], ended=self.index == len(self.events))

    def control(self, action, speed=None):
        if action == 'restart':
            self.state.reset()
            self.position = 0.
            self.index = 0
            self.paused = False
        elif action == 'pause': self.paused = True
        elif action == 'resume': self.paused = False
        elif action == 'speed' and speed in (1, 2, 5): self.speed = speed
        else: raise ValueError('Use pause, resume, restart or speed (1, 2, 5)')
        self.advance(0)

    def advance(self, elapsed):
        if not self.paused:
            self.position = min(self.events[-1]['at'], self.position + elapsed * self.speed)
            while self.index < len(self.events) and self.events[self.index]['at'] <= self.position:
                e = self.events[self.index]
                self.state.apply(e['topic'], e['data'], e.get('timestamp'), now=e['at'])
                self.index += 1
        self.publish()
