import json
import tempfile
import unittest
from pathlib import Path
from dashboard.historical import parse_stream, import_session
from dashboard.replay import Replay
from dashboard.state import State


class HistoricalTests(unittest.TestCase):
    def test_shared_archive_clock_and_raw_compression(self):
        events=parse_stream('\ufeff00:01:02.500"compressed"\r\n', 'Position.z')
        self.assertEqual(events[0]['at'],62.5)
        self.assertEqual(events[0]['data'],'compressed')
        self.assertTrue(events[0]['reconstructed'])
        with self.assertRaises(ValueError):parse_stream('00:99:00.000{}','TimingData')

    def test_download_accepts_accented_archive_folders_but_not_traversal(self):
        from unittest import mock
        from dashboard.historical import download
        relative='2025/2025-11-09_São_Paulo_Grand_Prix/2025-11-09_Race/SessionInfo.jsonStream'
        with tempfile.TemporaryDirectory() as tmp, mock.patch('dashboard.historical.subprocess.run') as run:
            run.return_value.stdout='﻿00:00:00.000{}'.encode()
            self.assertEqual(download(relative,Path(tmp)),'00:00:00.000{}')
            self.assertTrue(run.call_args[0][0][-1].endswith('/2025-11-09_S%C3%A3o_Paulo_Grand_Prix/2025-11-09_Race/SessionInfo.jsonStream'))
            self.assertEqual(download(relative,Path(tmp)),'00:00:00.000{}')
            self.assertEqual(run.call_count,1)
            for bad in ('2025/../Index.json','2025//Index.json','/etc/passwd','2025/a b.json','2025/x?y=1'):
                with self.assertRaises(ValueError):download(bad,Path(tmp))
            self.assertEqual(run.call_count,1)

    def test_import_uses_index_preserves_clock_and_replay_order(self):
        index={'Meetings':[{'Name':'Test Grand Prix','Sessions':[{'Name':'Race','Path':'2025/test/'}]}]}
        def fetch(path):
            if path.endswith('Index.json'):return json.dumps(index)
            if path.endswith('SessionInfo.jsonStream'):return '00:00:00.000{"Key":1}'
            if path.endswith('TimingData.jsonStream'):return '00:00:02.000{"Lines":{"44":{"Position":"1"}}}'
            return '00:00:01.000{}' if not path.endswith('Position.z.jsonStream') else '00:00:03.000"bad"'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'replay.jsonl'
            import_session(2025,'Test Grand Prix','Race',path,fetch)
            for speed in (1,2,5):
                state=State();replay=Replay(state,path);replay.control('speed',speed)
                replay.advance(1/speed)
                self.assertNotIn('TimingData',state.topics)
                replay.control('pause');replay.advance(100);self.assertEqual(replay.position,1)
                replay.control('resume');replay.advance(1/speed)
                self.assertEqual(state.topics['TimingData']['Lines']['44']['Position'],'1')
                replay.advance(100);self.assertTrue(state.replay['ended'])
                self.assertIn('TimingData',state.topics)
                replay.control('restart');self.assertNotIn('TimingData',state.topics)

    def test_real_suzuka_fixture_all_cars_and_raw_coordinates(self):
        from dashboard.positions import decode_positions
        state=State();r=Replay(state,Path('tests/fixtures/suzuka-2025.jsonl'))
        r.advance(100)
        diagnostics=state.position_snapshot()['diagnostics']
        self.assertEqual(len(diagnostics['driver_coverage']),20)
        self.assertEqual(diagnostics['coordinate_packets'],3)
        self.assertEqual(diagnostics['missing_drivers'],[])
        self.assertEqual(diagnostics['rejected'],{})
        packet=next(e for e in reversed(r.events) if e['topic']=='Position.z')
        raw=decode_positions(packet['data'])[-20:]
        for sample in raw:
            actual=state.positions.samples[sample['number']][-1]
            self.assertEqual((actual['x'],actual['y']),(sample['x'],sample['y']))

    def test_overtake_and_lapped_classification_never_relocate_cars(self):
        from test_positions import packet
        state=State();state.apply('DriverList',{'1':{'Tla':'ONE'},'44':{'Tla':'HAM'}})
        state.apply('Position.z',packet((0,),number='1'),now=0)
        state.apply('Position.z',packet((0,),number='44'),now=0)
        state.apply('TimingData',{'Lines':{'1':{'Position':'1'},'44':{'Position':'2'}}})
        before=json.dumps(state.positions.samples,sort_keys=True)
        state.apply('TimingData',{'Lines':{'1':{'Position':'2'},'44':{'Position':'1'}}})
        self.assertEqual([d['number'] for d in state.snapshot()['drivers']],['44','1'])
        state.apply('TimingData',{'Lines':{'1':{'GapToLeader':'+1 LAP'}}})
        self.assertEqual(state.snapshot()['drivers'][1]['gap'],'+1 LAP')
        self.assertEqual(json.dumps(state.positions.samples,sort_keys=True),before)

    def test_diagnostics_separates_malformed_packets_from_geometry(self):
        from dashboard.diagnostics import summarize
        events=[dict(at=0,topic='SessionInfo',data={'StartDate':'2025-01-01','Meeting':{'Location':'Test','Circuit':{'Key':1,'ShortName':'Test'}}}),
                dict(at=1,topic='Position.z',data='invalid'),
                dict(at=2,topic='Position.z',data={'Position':[{'Timestamp':'2025-01-01T00:00:02Z','Entries':{'44':{'X':1,'Y':1,'Z':0,'Status':'OnTrack'}}}]})]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'r.jsonl';path.write_text(''.join(json.dumps(e)+'\n' for e in events))
            geometry=Path(tmp)/'g.json';geometry.write_text(json.dumps(dict(circuitKey=1,year=2025,location='Test',x=[0,2,0],y=[0,1,2],rotation=0)))
            result=summarize(path,geometry)
            self.assertTrue(result['geometry_available'])
            self.assertEqual(result['rejected']['malformed_packet'],1)
