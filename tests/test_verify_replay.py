import json
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from dashboard.verify_replay import create_app

DEMO = Path(__file__).resolve().parents[1] / 'dashboard/recordings/demo.jsonl'


class VerifyReplayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)
        self.client = self.start(DEMO, 45)

    def start(self, recording, at):
        client = TestClient(create_app(recording, at, self.output)).__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client

    def samples(self, client=None):
        return (client or self.client).get('/api/verify/frame').json()['samples']

    def test_checkpoints_are_absolute_recording_seconds(self):
        self.assertEqual(self.client.get('/api/state').json()['replay']['position'], 45)
        result = self.client.post('/api/verify/checkpoint/75').json()
        self.assertEqual(result['at'], 75)
        self.assertGreater(result['next_event'], 75)
        self.assertTrue((self.output / 'checkpoint-75.json').exists())
        self.assertTrue(self.samples())

    def test_checkpoints_ignore_an_archive_replay_opening_at_lights_out(self):
        # Archive replays open at lights out; a checkpoint must not be counted from there.
        events = [dict(at=0, topic='SessionInfo', data={'Key': 1, 'Type': 'Race', 'Name': 'Race'}),
                  dict(at=10, topic='SessionStatus', data={'Status': 'Started'}, reconstructed=True),
                  *[dict(at=t, topic='LapCount', data={'CurrentLap': t}, reconstructed=True) for t in (20, 30, 40)]]
        recording = self.output / 'archive.jsonl'
        recording.write_text(''.join(json.dumps(e)+'\n' for e in events))
        client = self.start(recording, 20)
        self.assertEqual(client.get('/api/state').json()['replay']['position'], 20)
        self.assertEqual(client.post('/api/verify/checkpoint/25').json()['at'], 25)

    def test_seek_control_passes_its_position(self):
        replay = self.client.post('/api/replay/control', json={'action': 'seek', 'position': 30}).json()['replay']
        self.assertEqual(replay['position'], 30)
        self.assertEqual(self.client.post('/api/replay/control', json={'action': 'speed', 'speed': 3}).status_code, 422)

    def test_checkpoint_clears_an_earlier_position_fault(self):
        self.client.post('/api/verify/fault/positions')
        self.client.post('/api/verify/checkpoint/45')
        self.assertTrue(self.samples())

    def test_position_fault_withholds_only_coordinates_after_it_starts(self):
        self.assertEqual(self.client.post('/api/verify/fault/positions').status_code, 200)
        for body in ({'action': 'seek', 'position': 30}, {'action': 'restart'}):
            self.client.post('/api/replay/control', json=body)
            self.assertTrue(self.samples(), body)
        self.assertEqual(self.client.post('/api/verify/fault/unknown').status_code, 404)

    def test_audit_results_are_saved_by_safe_name_only(self):
        self.assertEqual(self.client.post('/api/verify/results/demo-1440', json={'runs': []}).json(), {'saved': 'demo-1440'})
        self.client.get('/api/track-map')
        self.client.post('/api/verify/results/demo-1440', json={'runs': []})
        saved = json.loads((self.output / 'demo-1440.json').read_text())
        self.assertEqual(saved['geometry']['geometry_id'], 'synthetic-demo')
        self.assertEqual(self.client.post('/api/verify/results/bad.name', json={}).status_code, 400)
        self.assertTrue(self.client.get('/api/verify/audit.js').text.startswith('// Run in the browser console'))


if __name__ == '__main__':
    unittest.main()
