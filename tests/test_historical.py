import json
import tempfile
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from dashboard.historical import (catalog, download, find_session, import_by_key, import_session, latest_race,
                                  parse_stream, recording_path)
from dashboard.replay import Replay
from dashboard.state import State


def session(key, name, end, path=None, offset='08:00:00'):
    return dict(Key=key, Name=name, Type='Race' if name in ('Race', 'Sprint') else 'Practice',
                StartDate=(datetime.fromisoformat(end) - timedelta(hours=2)).isoformat(), EndDate=end, GmtOffset=offset, Path=path or f'2026/{key}/')


# Two meetings share a name (as 2026's two tests do); Singapore's race ends 14:00 UTC.
INDEX_2026 = {'Meetings': [
    dict(Key=1, Name='Pre-Season Testing', Location='Sakhir', Sessions=[session(10, 'Day 1', '2026-02-11T19:00:00', offset='03:00:00')]),
    dict(Key=2, Name='Pre-Season Testing', Location='Sakhir', Sessions=[session(20, 'Day 1', '2026-02-18T19:00:00', offset='03:00:00')]),
    dict(Key=4, Name='Bahrain Grand Prix', Location='Kuala Lumpur', Sessions=[session(41, 'Race', '2026-10-04T17:00:00')]),
    dict(Key=3, Name='Singapore Grand Prix', Location='Marina Bay',
         Sessions=[session(30, 'Sprint', '2026-10-10T18:00:00'), session(31, 'Race', '2026-10-11T22:00:00')]),
]}
DURING_RACE_COOLDOWN = datetime(2026, 10, 11, 14, 30, tzinfo=timezone.utc)


def index_fetch(indexes, calls=None):
    def fetch(relative, refresh=False):
        if calls is not None:
            calls.append((relative, refresh))
        return json.dumps(indexes[int(relative[:4])])
    return fetch


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

    def test_catalog_marks_available_and_cached_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            singapore = INDEX_2026['Meetings'][3]
            recording_path(2026, singapore, singapore['Sessions'][0], Path(tmp)).write_text('{}')
            events = catalog(2026, DURING_RACE_COOLDOWN, index_fetch({2026: INDEX_2026}, calls), Path(tmp))
        self.assertEqual(calls, [('2026/Index.json', True)])
        self.assertEqual([e['event'] for e in events], ['Pre-Season Testing', 'Pre-Season Testing',
                                                         'Bahrain Grand Prix', 'Singapore Grand Prix'])
        self.assertEqual(events[3]['sessions'], [
            dict(key=30, name='Sprint', type='Race', start_utc='2026-10-10T08:00:00+00:00', available=True, cached=True),
            dict(key=31, name='Race', type='Race', start_utc='2026-10-11T12:00:00+00:00', available=False, cached=False)])
        self.assertTrue(events[0]['sessions'][0]['available'])
        later = catalog(2026, datetime(2026, 10, 11, 15, tzinfo=timezone.utc), index_fetch({2026: INDEX_2026}), Path(tmp))
        self.assertTrue(later[3]['sessions'][1]['available'])
        calls = []
        catalog(2025, DURING_RACE_COOLDOWN, index_fetch({2025: INDEX_2026}, calls), Path(tmp))
        self.assertEqual(calls, [('2025/Index.json', False)])

    def test_find_and_import_by_key_with_duplicate_meeting_names(self):
        meeting, found = find_session(INDEX_2026, 20)
        self.assertEqual((meeting['Key'], found['Path']), (2, '2026/20/'))
        self.assertIsNone(find_session(INDEX_2026, 99))
        fetched = []
        def fetch(relative):
            fetched.append(relative)
            if relative.endswith('Index.json'): return json.dumps(INDEX_2026)
            return '00:00:00.000{"Key":20}' if relative.endswith('SessionInfo.jsonStream') else '00:00:01.000{}'
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'out.jsonl'
            import_by_key(2026, 20, output, fetch)
            self.assertTrue(output.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [output])
            self.assertTrue(all(r.startswith('2026/20/') for r in fetched[1:]))
            with self.assertRaises(ValueError): import_by_key(2026, 99, output, fetch)

    def test_latest_race_skips_sprints_and_unpublished_races(self):
        found = latest_race(DURING_RACE_COOLDOWN, index_fetch({2026: INDEX_2026}))
        self.assertEqual((found['year'], found['meeting']['Name'], found['session']['Key']), (2026, 'Bahrain Grand Prix', 41))
        found = latest_race(datetime(2026, 10, 11, 15, tzinfo=timezone.utc), index_fetch({2026: INDEX_2026}))
        self.assertEqual(found['session']['Key'], 31)
        calls = []
        january = datetime(2027, 1, 5, tzinfo=timezone.utc)
        found = latest_race(january, index_fetch({2027: {'Meetings': []}, 2026: INDEX_2026}, calls))
        self.assertEqual((found['year'], found['session']['Key']), (2026, 31))
        self.assertEqual(calls, [('2027/Index.json', True), ('2026/Index.json', False)])
        self.assertIsNone(latest_race(january, index_fetch({2027: {'Meetings': []}, 2026: {'Meetings': []}})))

    def test_refreshed_download_falls_back_to_cache_offline(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch('dashboard.historical.subprocess.run') as run:
            cached = Path(tmp) / '2026/Index.json'
            run.side_effect = subprocess.CalledProcessError(6, 'curl')
            with self.assertRaises(subprocess.CalledProcessError): download('2026/Index.json', Path(tmp), refresh=True)
            cached.parent.mkdir(parents=True); cached.write_text('old')
            self.assertEqual(download('2026/Index.json', Path(tmp)), 'old')
            self.assertEqual(run.call_count, 1)
            self.assertEqual(download('2026/Index.json', Path(tmp), refresh=True), 'old')
            run.side_effect = OSError('no curl')
            self.assertEqual(download('2026/Index.json', Path(tmp), refresh=True), 'old')
            run.side_effect = None; run.return_value.stdout = b'new'
            self.assertEqual(download('2026/Index.json', Path(tmp), refresh=True), 'new')
            self.assertEqual(cached.read_text(), 'new')

    def test_missing_streams_are_http_4xx_even_when_curl_exits_56(self):
        def fetch(relative):
            if relative.endswith('Index.json'): return json.dumps(INDEX_2026)
            if relative.endswith('SessionInfo.jsonStream'): return '00:00:00.000{"Key":20}'
            if relative.endswith('LapCount.jsonStream'):
                raise subprocess.CalledProcessError(56, 'curl', stderr=b'curl: (56) The requested URL returned error: 403\n')
            if relative.endswith('TimingData.jsonStream'): raise subprocess.CalledProcessError(22, 'curl')
            return '00:00:01.000{}'
        with tempfile.TemporaryDirectory() as tmp:
            result = import_by_key(2026, 20, Path(tmp) / 'out.jsonl', fetch)
        self.assertEqual(result['missing_streams'], ['TimingData', 'LapCount'])
        for code, stderr in ((56, b'curl: (56) Recv failure: Connection reset by peer'), (6, b''),
                             (56, b'curl: (56) The requested URL returned error: 503')):
            def failing(relative, code=code, stderr=stderr):
                if relative.endswith('Index.json'): return json.dumps(INDEX_2026)
                raise subprocess.CalledProcessError(code, 'curl', stderr=stderr)
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(subprocess.CalledProcessError):
                import_by_key(2026, 20, Path(tmp) / 'out.jsonl', failing)

    def test_recording_path_slugs(self):
        path = recording_path(2025, {'Name': 'São Paulo Grand Prix'}, {'Name': 'Sprint Qualifying', 'Key': 9}, Path('/r'))
        self.assertEqual(path, Path('/r/archive-2025-sao-paulo-grand-prix-sprint-qualifying-9.jsonl'))
        path = recording_path(2026, {'Name': 'Pre-Season Testing'}, {'Name': 'Day 1', 'Key': 20})
        self.assertEqual(path.name, 'archive-2026-pre-season-testing-day-1-20.jsonl')
        self.assertEqual(path.parent.name, 'recordings')
