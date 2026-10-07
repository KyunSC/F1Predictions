"""Actual upstream coordinates; no timing-derived estimates."""
import base64
import json
import math
import zlib
from collections import Counter
from datetime import datetime


def decode_positions(payload, rejected=None):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            pass
        if isinstance(payload, str):
            raw = zlib.decompressobj(-zlib.MAX_WBITS)
            decoded = raw.decompress(base64.b64decode(payload, validate=True), 4_000_001)
            if len(decoded) > 4_000_000 or not raw.eof:
                raise ValueError('Position packet exceeds limit or is incomplete')
            payload = json.loads(decoded)
    samples = payload['Position']
    if isinstance(samples, dict):
        samples = samples.values()
    result = []
    for sample in samples:
        try:
            source = datetime.fromisoformat(sample['Timestamp'].replace('Z', '+00:00'))
            if source.tzinfo is None:
                raise ValueError('Position timestamp must include UTC offset')
            entries = sample['Entries'].items()
        except (ValueError, TypeError, KeyError, AttributeError):
            if rejected is None:
                raise
            rejected['invalid_frame'] += 1
            continue
        for number, entry in entries:
            try:
                coords = [entry[k] for k in ('X', 'Y', 'Z')]
                if not str(number).isdigit() or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in coords):
                    raise ValueError('Invalid position coordinates or racing number')
                result.append(dict(number=str(int(number)), x=coords[0], y=coords[1], z=coords[2],
                                   source_timestamp=source.timestamp(), status=entry.get('Status')))
            except (ValueError, TypeError, KeyError, AttributeError):
                if rejected is None:
                    raise
                rejected['invalid_sample'] += 1
    return sorted(result, key=lambda s: s['source_timestamp'])


class Positions:
    def __init__(self):
        self.generation = 0
        self.sequence = 0
        self.reset()

    def reset(self):
        self.generation += 1
        self.samples = {}
        self.latest = {}
        self.error = None
        self.received = None
        self.offset = None
        self.packets = self.decoded = self.accepted = 0
        self.rejected = Counter()
        self.gaps = Counter()
        self.max_gap = 0.

    def apply(self, payload, receipt):
        self.packets += 1
        try:
            samples = decode_positions(payload, self.rejected)
            self.decoded += len(samples)
            if not samples:
                return
            end = max(s['source_timestamp'] for s in samples)
            if self.offset is None:
                # One clock mapping per session/reconnect; packet delivery jitter
                # must not move old measurements forward or compress their spacing.
                self.offset = receipt - end
            for sample in samples:
                number = sample.pop('number')
                if sample['source_timestamp'] <= self.latest.get(number, float('-inf')):
                    self.rejected['duplicate_or_late'] += 1
                    continue
                sample['presentation_timestamp'] = self.offset + sample['source_timestamp']
                history = self.samples.setdefault(number, [])
                if history and sample['presentation_timestamp'] <= history[-1]['presentation_timestamp']:
                    continue
                if number in self.latest:
                    gap = sample['source_timestamp'] - self.latest[number]
                    self.max_gap = max(self.max_gap, gap)
                    if gap > 5:
                        self.gaps[number] += 1
                history.append(sample)
                self.accepted += 1
                self.latest[number] = sample['source_timestamp']
                self.samples[number] = [s for s in history if s['presentation_timestamp'] >= receipt - 10][-300:] or history[-1:]
                self.received = receipt
            self.error = None
        except (ValueError, TypeError, KeyError, AttributeError, zlib.error) as exc:
            self.rejected['malformed_packet'] += 1
            self.error = f'Malformed position message: {exc}'

    def snapshot(self, clock):
        self.sequence += 1
        for number, history in self.samples.items():
            self.samples[number] = [s for s in history if s['presentation_timestamp'] >= clock-10] or history[-1:]
        return dict(generation=self.generation, sequence=self.sequence, available=bool(self.samples) and not self.error,
                    reason=self.error, presentation_clock=clock,
                    diagnostics=dict(coordinate_packets=self.packets, decoded_samples=self.decoded,
                                     accepted_samples=self.accepted, driver_coverage=sorted(self.latest, key=int),
                                     rejected=dict(self.rejected), gaps_over_5s=dict(self.gaps), max_gap_seconds=self.max_gap),
                    age_seconds=None if self.received is None else max(0, clock-self.received),
                    driver_age_seconds={n: max(0, clock-s[-1]['presentation_timestamp']) for n,s in self.samples.items()},
                    samples={n: [v for v in s if v['presentation_timestamp'] >= clock-10] or s[-1:] for n,s in self.samples.items()})
