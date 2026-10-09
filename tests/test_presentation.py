"""Shared presentation timeline regressions, using only preceding events."""
import unittest
from pathlib import Path
from dashboard.state import State
from dashboard.replay import Replay


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.state = State()
        self.state.apply('DriverList', {'44': {'Tla': 'HAM'}}, now=0)
        self.state.apply('TimingData', {'Lines': {'44': {'Position': '2'}}}, now=1)
        self.state.apply('TimingData', {'Lines': {'44': {'Position': '1'}}}, now=2)

    def test_history_retains_timing_before_buffered_clock(self):
        frame = self.state.position_snapshot(now=2.5)
        self.assertEqual(frame['presentation_timestamp'], 1.5)
        history = frame['timing_history']
        eligible = [s for s in history if s['presentation_timestamp'] <= 1.5]
        self.assertEqual(eligible[-1]['drivers'][0]['position'], '2')
        self.assertEqual(frame['current']['drivers'][0]['position'], '1')
        self.assertEqual(eligible[-1]['generation'], frame['generation'])

    def test_quiet_timing_keeps_predecessor_and_reset_clears_history(self):
        self.state.apply('WeatherData', {'AirTemp': '20'}, now=50)
        self.assertEqual(self.state.timing_history[0]['presentation_timestamp'], 2)
        generation = self.state.positions.generation
        self.state.reset()
        self.assertEqual(self.state.timing_history, [])
        self.assertGreater(self.state.positions.generation, generation)

    def test_upstream_disconnect_freezes_common_clock(self):
        self.state.connection = 'connected'
        self.state.position_snapshot(now=3)
        self.state.connection = 'reconnecting'
        frame = self.state.position_snapshot(now=30)
        self.assertEqual(frame['presentation_clock'], 3)
        self.assertEqual(frame['timing_history'][-1]['drivers'][0]['position'], '1')
        self.state.reset()
        self.assertEqual(self.state.position_snapshot(now=31)['timing_history'], [])

    def test_replay_speed_pause_restart_share_one_timeline(self):
        for speed in (1, 2, 5):
            state = State()
            replay = Replay(state, Path('dashboard/recordings/demo.jsonl'))
            replay.control('speed', speed)
            replay.advance(2)
            self.assertEqual(state.position_snapshot()['presentation_timestamp'], 2*speed-1)
            replay.control('pause')
            replay.advance(10)
            self.assertEqual(state.position_snapshot()['presentation_clock'], 2*speed)
            replay.control('resume')
            replay.advance(1)
            self.assertEqual(state.position_snapshot()['presentation_clock'], 3*speed)
            generation = state.positions.generation
            replay.control('restart')
            frame = state.position_snapshot()
            self.assertGreater(frame['generation'], generation)
            self.assertEqual(frame['presentation_timestamp'], -1)
            self.assertTrue(all(h['presentation_timestamp'] <= 0 for h in frame['timing_history']))
