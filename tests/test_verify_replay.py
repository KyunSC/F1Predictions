import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from dashboard.verify_replay import create_app

DEMO = Path(__file__).resolve().parents[1] / 'dashboard/recordings/demo.jsonl'


class VerifyReplayTest(unittest.TestCase):
    def setUp(self):
        self.output = Path(tempfile.mkdtemp())
        self.client = TestClient(create_app(DEMO, 45, self.output)).__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_checkpoints_are_absolute_recording_seconds(self):
        self.assertEqual(self.client.get('/api/state').json()['replay']['position'], 45)
        result = self.client.post('/api/verify/checkpoint/75').json()
        self.assertEqual(result['at'], 75)
        self.assertGreater(result['next_event'], 75)
        self.assertTrue((self.output / 'checkpoint-75.json').exists())
        self.assertTrue(self.client.get('/api/verify/frame').json()['samples'])

    def test_seek_control_passes_its_position(self):
        replay = self.client.post('/api/replay/control', json={'action': 'seek', 'position': 30}).json()['replay']
        self.assertEqual(replay['position'], 30)

    def test_checkpoint_clears_an_earlier_position_fault(self):
        self.client.post('/api/verify/fault/positions')
        self.client.post('/api/verify/checkpoint/45')
        self.assertTrue(self.client.get('/api/verify/frame').json()['samples'])

    def test_audit_results_are_saved_by_safe_name_only(self):
        self.assertEqual(self.client.post('/api/verify/results/demo-1440', json={'runs': []}).json(), {'saved': 'demo-1440'})
        self.assertIn('error', self.client.post('/api/verify/results/bad.name', json={}).json())
        self.assertTrue(self.client.get('/api/verify/audit.js').text.startswith('// Run in the browser console'))


if __name__ == '__main__':
    unittest.main()
