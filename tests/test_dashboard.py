"""Offline dashboard protocol, state, replay, API and notebook export tests."""
import asyncio
import json
import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient
from dashboard import app as app_module
from dashboard.app import app, default_recording
from dashboard.state import State, merge, match_predictions
from dashboard.replay import Replay
from dashboard.live import connect, decode_frame, feed_events, load_token, run_live, TOPICS
from test_prediction import NS
from test_historical import DURING_RACE_COOLDOWN, INDEX_2026, index_fetch

INFO = dict(Key=1, Type='Race', Name='Race', StartDate='2026-10-04T15:00:00', Meeting={'Location':'Kuala Lumpur'})
DEMO = str(Path(__file__).resolve().parents[1] / 'dashboard/recordings/demo.jsonl')
EXPORT = dict(session=dict(year=2026,venue='Sepang',race_date='2026-10-04'), drivers=[dict(racing_number='44',pace_rank=2)])


class DashboardTests(unittest.TestCase):
    def test_sparse_array_merge_and_missing_fields(self):
        original = {'Stints':[{'Compound':'MEDIUM','TotalLaps':1}]}
        base = merge({}, original)
        value = merge(base, {'Stints':{'0':{'TotalLaps':3}}})
        self.assertEqual(value['Stints']['0'],dict(Compound='MEDIUM',TotalLaps=3))
        self.assertEqual(base['Stints']['0']['TotalLaps'],1)
        self.assertEqual(merge({'old': 1}, {'_kf': True, 'new': 2}), {'_kf': True, 'new': 2})
        state=State(); state.apply('DriverList',{'44':{'Tla':'HAM'}})
        self.assertIsNone(state.snapshot()['drivers'][0]['last_lap'])

    def test_reset_on_session_change_not_partial_metadata(self):
        state=State(); state.apply('SessionInfo',INFO); state.apply('TimingData',{'Lines':{'44':{'Position':'1'}}})
        state.apply('SessionInfo',{'Meeting':{'Name':'Race'}})
        self.assertIn('TimingData',state.topics)
        state.apply('SessionInfo',{'Key':2})
        self.assertNotIn('TimingData',state.topics)
        self.assertNotIn('StartDate',state.topics['SessionInfo'])

    def test_stale_and_disconnect(self):
        state=State(mode='live'); self.assertTrue(state.snapshot(100)['connection']['stale'])
        state.connection='connected'; state.apply('TimingData',{},now=100)
        self.assertFalse(state.snapshot(110)['connection']['stale'])
        self.assertTrue(state.snapshot(116)['connection']['stale'])
        state.source_timestamp='1970-01-01T00:00:00Z'
        self.assertTrue(state.snapshot(110)['connection']['stale'])
        state.connection='reconnecting'
        self.assertTrue(state.snapshot(110)['connection']['stale'])

    def test_identity_and_number_matching(self):
        self.assertEqual(match_predictions(EXPORT,INFO)[0],EXPORT['drivers'])
        for patch_info in [dict(Type='Qualifying'),dict(StartDate='2025-10-04'),dict(StartDate='2026-10-05'),dict(Meeting={'Location':'Sakhir'})]:
            self.assertFalse(match_predictions(EXPORT,dict(INFO,**patch_info))[0])
        state=State(EXPORT); state.apply('SessionInfo',INFO)
        state.apply('DriverList',{'44':{'Tla':'XXX'},'1':{'Tla':'HAM'}})
        drivers={d['number']:d for d in state.snapshot()['drivers']}
        self.assertEqual(drivers['44']['prediction']['pace_rank'],2)
        self.assertIsNone(drivers['1']['prediction'])

    def test_pit_rejoin_projection_in_snapshot(self):
        info=dict(INFO,Meeting={'Location':'Kuala Lumpur','Circuit':{'Key':12}})
        table=dict(races=[dict(circuit_key=12,location='Sepang',date='2017-10-01',losses={'green':{'median_loss':22.0},'sc':{'median_loss':12.0}}),
                          dict(circuit_key=12,location='Sepang',date='2026-10-04',losses={'green':{'median_loss':99.0}})])
        lines={'1':{'Position':'1','GapToLeader':'LAP 12'},'44':{'Position':'2','GapToLeader':'+5.000'},
               '16':{'Position':'3','GapToLeader':'+20.000','NumberOfPitStops':1},'4':{'Position':'4','GapToLeader':'+30.000'}}
        state=State(pit_loss=table); state.apply('SessionInfo',info)
        state.apply('DriverList',{n:{'Tla':n} for n in lines}); state.apply('TimingData',{'Lines':lines})
        snap=state.snapshot(); drivers={d['number']:d for d in snap['drivers']}
        self.assertEqual(snap['pit_loss'],dict(seconds=22.0,basis='circuit',condition='green',races=1,label='Kuala Lumpur'))
        self.assertEqual(drivers['44']['pit_rejoin'],dict(position=3,ahead='16',gap_ahead=7.0,behind='4',gap_behind=3.0,positions_lost=1))
        self.assertEqual(drivers['16']['pit_stops'],1)
        state.apply('TrackStatus',{'Status':'4','Message':'SCDeployed'})
        snap=state.snapshot(); drivers={d['number']:d for d in snap['drivers']}
        self.assertEqual((snap['pit_loss']['condition'],snap['pit_loss']['seconds']),('sc',12.0))
        self.assertEqual(drivers['44']['pit_rejoin']['position'],2)
        state.apply('TrackStatus',{'Status':'1','Message':'AllClear'})
        state.apply('TimingData',{'Lines':{'44':{'InPit':True}}})
        drivers={d['number']:d for d in state.snapshot()['drivers']}
        self.assertTrue(drivers['44']['in_pit']); self.assertIsNone(drivers['44']['pit_rejoin'])
        state.apply('SessionInfo',{'Type':'Qualifying','Name':'Qualifying'})
        snap=state.snapshot()
        self.assertTrue(all(d['pit_rejoin'] is None for d in snap['drivers']))
        self.assertIn('only in races',snap['pit_loss']['reason'])
        self.assertEqual(State().snapshot()['pit_loss']['reason'],'No pit-loss table loaded.')

    def test_championship_projection_in_snapshot(self):
        state=State(); state.apply('SessionInfo',INFO)
        self.assertEqual(state.snapshot()['standings'],dict(rows=[],reason='Awaiting championship data from the timing feed.'))
        state.apply('DriverList',{'12':{'Tla':'ANT','TeamName':'Mercedes','TeamColour':'00D7B6'},'63':{'Tla':'RUS'}})
        state.apply('ChampionshipPrediction',{'Drivers':{
            '12':{'RacingNumber':'12','CurrentPosition':1,'PredictedPosition':1,'CurrentPoints':302.0,'PredictedPoints':302.0},
            '63':{'RacingNumber':'63','CurrentPosition':2,'PredictedPosition':2,'CurrentPoints':236.0,'PredictedPoints':236.0},
            '7':{'RacingNumber':'7','CurrentPosition':3,'PredictedPosition':3,'CurrentPoints':230.0,'PredictedPoints':230.0}},'Teams':{}})
        # Sparse patches as the race runs: 7 (not entered in this session) takes 3rd, RUS drops behind.
        state.apply('ChampionshipPrediction',{'Drivers':{'63':{'PredictedPosition':3,'PredictedPoints':244.0},
                                                          '7':{'PredictedPosition':2,'PredictedPoints':255.0}}})
        rows=state.snapshot()['standings']['rows']
        self.assertEqual([r['number'] for r in rows],['12','7','63'])
        self.assertEqual(rows[0],dict(number='12',code='ANT',name=None,team='Mercedes',color='00D7B6',position=1,points=302.0,
                                      current_position=1,current_points=302.0,points_gained=0.0,positions_gained=0))
        self.assertEqual((rows[1]['code'],rows[1]['points_gained'],rows[1]['positions_gained']),(None,25.0,1))
        self.assertEqual((rows[2]['points_gained'],rows[2]['positions_gained']),(8.0,-1))
        state.apply('SessionInfo',{'Type':'Qualifying','Name':'Qualifying'})
        self.assertEqual(state.snapshot()['standings'],dict(rows=[],reason='Championship projection is shown only in races and sprints.'))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.jsonl'; path.write_text(json.dumps(dict(at=0,topic='SessionInfo',data=INFO)))
            state=State(); Replay(state,path)
            self.assertIn('No championship data in this recording',state.snapshot()['standings']['reason'])

    def test_replay_controls_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.jsonl'
            path.write_text('\n'.join(json.dumps(dict(at=t,topic='LapCount',data={'CurrentLap':lap})) for t,lap in [(110,3),(100,1),(105,2)]))
            state=State(); replay=Replay(state,path); replay.advance(0)
            self.assertEqual(state.snapshot()['laps']['CurrentLap'],1)
            replay.control('pause'); replay.advance(100); self.assertEqual(replay.position,0)
            replay.control('resume'); replay.control('speed',2); replay.advance(2.5)
            self.assertEqual(state.snapshot()['laps']['CurrentLap'],2)
            replay.control('speed',5); replay.advance(1); self.assertTrue(state.replay['ended'])
            replay.control('restart'); self.assertEqual(state.snapshot()['laps']['CurrentLap'],1)
            self.assertFalse(state.replay['ended'])
            with self.assertRaises(ValueError): replay.control('speed',3)

    def test_replay_seek_rebuilds_state_at_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.jsonl'
            path.write_text('\n'.join(json.dumps(dict(at=t,topic='LapCount',data={'CurrentLap':lap})) for t,lap in [(100,1),(105,2),(110,3)]))
            state=State(); replay=Replay(state,path); replay.control('pause')
            generation=state.positions.generation
            replay.control('seek',position=7); self.assertEqual((replay.position,state.snapshot()['laps']['CurrentLap']),(7,2))
            self.assertGreater(state.positions.generation,generation)
            self.assertTrue(state.replay['paused'])
            replay.control('seek',position=99); self.assertTrue(state.replay['ended'])
            replay.control('seek',position=1); self.assertEqual(state.snapshot()['laps']['CurrentLap'],1)
            self.assertFalse(state.replay['ended'])
            replay.control('seek',position=-5); self.assertEqual(replay.position,0)
            for bad in (None,float('nan'),float('inf')):
                with self.assertRaises(ValueError): replay.control('seek',position=bad)

    def test_replay_seek_keeps_the_frames_normal_playback_would_show(self):
        frames=lambda state:[(f['presentation_timestamp'],f['laps']) for f in state.timing_history]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'dense.jsonl'
            path.write_text('\n'.join(json.dumps(dict(at=t,topic='LapCount',data={'CurrentLap':t})) for t in range(61)))
            played=State(); replay=Replay(played,path)
            for _ in range(50): replay.advance(1)
            jumped=State(); Replay(jumped,path).control('seek',position=50)
            self.assertEqual(frames(jumped),frames(played))
            self.assertEqual(frames(jumped)[0][0],44)
            path=Path(tmp)/'sparse.jsonl'
            path.write_text('\n'.join(json.dumps(dict(at=t,topic=topic,data=data)) for t,topic,data in
                [(0,'LapCount',{'CurrentLap':1}),(10,'LapCount',{'CurrentLap':2}),(48,'Position.z','x'),(100,'LapCount',{'CurrentLap':3})]))
            state=State(); Replay(state,path).control('seek',position=50)
            self.assertEqual(frames(state),[(10,{'CurrentLap':2})])

    def test_archive_replay_opens_at_lights_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'archive.jsonl'
            events=[(0,'SessionInfo',INFO),(5,'SessionStatus',{'Status':'Inactive'}),(10,'LapCount',{'CurrentLap':1,'TotalLaps':56}),
                    (100,'SessionStatus',{'Status':'Started'}),(110,'LapCount',{'CurrentLap':2})]
            path.write_text('\n'.join(json.dumps(dict(at=t,topic=topic,data=data,reconstructed=True)) for t,topic,data in events))
            state=State(); replay=Replay(state,path)
            self.assertEqual((replay.start,replay.position,state.replay['position']),(100,100,100))
            self.assertEqual(state.replay['duration'],110)
            self.assertEqual(state.snapshot()['laps']['TotalLaps'],56)
            self.assertEqual(state.topics['SessionStatus']['Status'],'Started')
            replay.advance(10); self.assertEqual(state.snapshot()['laps']['CurrentLap'],2)
            replay.control('restart')
            self.assertEqual(replay.position,100)
            self.assertEqual(state.snapshot()['laps']['CurrentLap'],1)
            self.assertEqual(state.topics['SessionInfo']['Key'],1)
        state=State(); replay=Replay(state,Path(DEMO))
        self.assertEqual((replay.start,replay.position),(0,0))

    def test_default_recording(self):
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(default_recording(),app_module.DEMO_RECORDING)
            self.assertEqual(default_recording().name,'demo.jsonl')
            with patch.dict('os.environ',{'F1_RECORDING':'/elsewhere/x.jsonl'}):
                self.assertEqual(default_recording(),Path('/elsewhere/x.jsonl'))

    def test_protocol_and_reconnect_backoff(self):
        self.assertNotIn('CarData.z',TOPICS); self.assertIn('Position.z',TOPICS)
        frames=decode_frame('{"type":6}\u001e{"type":1,"target":"feed","arguments":["LapCount",{"CurrentLap":2},"now"]}\u001e')
        self.assertEqual(list(feed_events(frames[1]))[0],('LapCount',{'CurrentLap':2},'now'))
        with self.assertRaises(RuntimeError): list(feed_events({'type':3,'error':'Unauthorized'}))
        self.assertEqual(list(feed_events({'type':3,'result':{'TimingData':{},'SessionInfo':INFO}}))[0][0],'SessionInfo')
        state=State(mode='live'); delays=[]
        async def failed(*args): raise OSError('offline')
        async def sleep(delay):
            delays.append(delay)
            if len(delays)==4: raise asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError): asyncio.run(run_live(state,Path('/unused'),failed,sleep))
        self.assertEqual(delays,[1,2,4,8]); self.assertEqual(state.reconnects,4)
        self.assertEqual(state.connection,'reconnecting')

    def test_f1tv_token_loading(self):
        import base64
        def jwt(exp):
            return 'h.' + base64.urlsafe_b64encode(json.dumps({'exp': exp}).encode()).decode().rstrip('=') + '.s'
        with tempfile.TemporaryDirectory() as tmp:
            stored, missing = Path(tmp)/'f1auth.json', Path(tmp)/'none.json'
            stored.write_text(jwt(200))
            self.assertEqual(load_token({}, stored, now=100), (jwt(200), None))
            self.assertEqual(load_token({'F1TV_TOKEN': jwt(300)}, stored, now=100)[0], jwt(300))
            token, problem = load_token({}, stored, now=300)
            self.assertIsNone(token); self.assertIn('expired', problem)
            token, problem = load_token({}, missing, now=100)
            self.assertIsNone(token); self.assertIn('F1TV subscription', problem)
            self.assertIn('malformed', load_token({'F1TV_TOKEN': 'not-a-jwt'}, missing)[1])

    def test_live_connection_sends_token_and_explains_missing_positions(self):
        calls = {}
        class Client:
            cookies = {}
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def options(self, url): pass
            async def post(self, url, headers=None):
                calls['negotiate'] = headers
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'connectionToken': 't'})
        def ws(url, additional_headers, open_timeout):
            calls['websocket'] = additional_headers
            raise OSError('stop')
        state = State(mode='live')
        with patch('dashboard.live.httpx.AsyncClient', Client), patch('dashboard.live.websockets.connect', ws):
            with self.assertRaises(OSError): asyncio.run(connect(state, Path('/unused'), lambda: ('tok', None)))
            self.assertEqual(calls['negotiate']['Authorization'], 'Bearer tok')
            self.assertEqual(calls['websocket']['Authorization'], 'Bearer tok')
            with self.assertRaises(OSError): asyncio.run(connect(state, Path('/unused'), lambda: (None, 'needs F1TV')))
            self.assertNotIn('Authorization', calls['negotiate']); self.assertNotIn('Authorization', calls['websocket'])
        state.connection = 'connected'
        self.assertEqual(state.position_snapshot()['reason'], 'needs F1TV')

    def test_driver_numbers_come_only_from_qualifying(self):
        results = pd.DataFrame(dict(Abbreviation=['HAM'], DriverNumber=['44'],
            FirstName=['Lewis'], LastName=['Hamilton'], TeamName=['Ferrari'], Position=[1],
            Q1=pd.to_timedelta([90], unit='s'), Q2=pd.to_timedelta([89], unit='s'),
            Q3=pd.to_timedelta([88], unit='s')))
        session = SimpleNamespace(results=results, load=Mock())
        with patch.object(NS['fastf1'], 'get_session', return_value=session) as get:
            frame = NS['build_race_frame'](2026, 16, include_target=False)
        get.assert_called_once_with(2026, 16, 'Q')
        self.assertEqual(frame.DriverNumber.tolist(), ['44'])
        self.assertTrue(frame.PaceRatio.isna().all())

    def test_notebook_export_is_fixed_and_offline(self):
        frame=pd.DataFrame([dict(DriverNumber='44',Driver='HAM',FullName='Lewis Hamilton',Team='Ferrari',PaceRank=1,PredictedPaceRatio=.99,MissingQualiTime=False,MissingQualifyingPosition=False,MissingPriorPace=True)])
        original=frame.copy(deep=True)
        event=dict(Location='Kuala Lumpur',RaceStartUtc=pd.Timestamp('2026-10-04',tz='UTC'),EventName='Bahrain Grand Prix')
        with tempfile.TemporaryDirectory() as tmp, patch.object(NS['fastf1'],'get_session',side_effect=AssertionError('No session loads')):
            path=Path(tmp)/'prediction.json'
            result=NS['export_predictions'](frame,event,2026,path)
            self.assertEqual(result,json.loads(path.read_text()))
            self.assertEqual(result['drivers'][0]['racing_number'],'44')
            self.assertTrue(result['drivers'][0]['missing_features']['MissingPriorPace'])
            self.assertEqual(match_predictions(result,INFO)[0],result['drivers'])
            pd.testing.assert_frame_equal(frame,original)
            frame.loc[0,'DriverNumber']=None
            with self.assertRaises(ValueError): NS['export_predictions'](frame,event,2026,path)

    def test_sprint_export_matches_only_the_sprint(self):
        frame=pd.DataFrame([dict(DriverNumber='44',Driver='HAM',FullName='Lewis Hamilton',Team='Ferrari',PaceRank=1,PredictedPaceRatio=.99,MissingQualiTime=False,MissingQualifyingPosition=False,MissingPriorPace=False)])
        event=pd.Series(dict(Location='Marina Bay',RaceStartUtc=pd.Timestamp('2026-10-10 09:00',tz='UTC'),EventName='Singapore Grand Prix',Kind='sprint'))
        sprint=dict(Key=2, Type='Race', Name='Sprint', StartDate='2026-10-10T17:00:00', GmtOffset='08:00:00', Meeting={'Location':'Marina Bay'})
        with tempfile.TemporaryDirectory() as tmp:
            result=NS['export_predictions'](frame,event,2026,Path(tmp)/'prediction.json')
        self.assertEqual(result['session']['race_date'],'2026-10-10')
        self.assertEqual(result['session']['name'],'Sprint')
        self.assertEqual(match_predictions(result,sprint)[0],result['drivers'])
        for patch_info in [dict(Name='Race',StartDate='2026-10-11T20:00:00'),dict(Name='Race'),
                           dict(Type='Qualifying',Name='Qualifying',StartDate='2026-10-10T21:00:00'),
                           dict(Type='Qualifying',Name='Sprint Qualifying',StartDate='2026-10-09T20:30:00')]:
            self.assertFalse(match_predictions(result,dict(sprint,**patch_info))[0],patch_info)
        legacy=dict(EXPORT,session={k:v for k,v in EXPORT['session'].items() if k!='name'})
        self.assertEqual(match_predictions(legacy,dict(INFO,Name='Anything'))[0],EXPORT['drivers'])

    def test_http_websocket_and_invalid_control(self):
        with patch.dict('os.environ',{'F1_MODE':'replay','F1_RECORDING':DEMO}), TestClient(app) as client:
            self.assertEqual(client.get('/api/state').status_code,200)
            self.assertEqual(client.post('/api/replay/control',json={'action':'pause'}).status_code,200)
            self.assertTrue(client.get('/api/state').json()['replay']['paused'])
            self.assertEqual(client.post('/api/replay/control',json={'action':'speed','speed':3}).status_code,422)
            self.assertEqual(client.post('/api/replay/control',json={'action':'seek','position':3}).json()['replay']['position'],3)
            self.assertEqual(client.post('/api/replay/control',json={'action':'seek'}).status_code,422)
            with client.websocket_connect('/ws') as ws:
                self.assertIn('drivers',ws.receive_json())

    def test_mode_switch_rebuilds_state(self):
        async def idle_live(state, path):
            await asyncio.Event().wait()
        with patch.dict('os.environ',{'F1_MODE':'replay','F1_RECORDING':DEMO}), patch('dashboard.app.run_live',idle_live), TestClient(app) as client:
            replay_state=app.state.timing
            self.assertEqual(client.post('/api/mode',json={'mode':'live'}).json()['connection']['mode'],'live')
            self.assertIsNot(app.state.timing,replay_state)
            self.assertIsNone(app.state.replay)
            self.assertEqual(client.post('/api/replay/control',json={'action':'pause'}).status_code,409)
            self.assertEqual(client.post('/api/mode',json={'mode':'replay'}).json()['connection']['mode'],'replay')
            self.assertEqual(client.post('/api/replay/control',json={'action':'pause'}).status_code,200)
            self.assertEqual(client.post('/api/mode',json={'mode':'bogus'}).status_code,422)

    @contextmanager
    def archive_client(self, tmp, import_by_key=None):
        """App on the demo replay with the archive index, recordings dir, importer and clock patched."""
        async def idle_live(state, path):
            await asyncio.Event().wait()
        with patch.dict('os.environ',{'F1_MODE':'replay','F1_RECORDING':DEMO}), patch('dashboard.app.run_live',idle_live),\
                patch('dashboard.historical.download',index_fetch({2026:INDEX_2026})),\
                patch('dashboard.historical.RECORDINGS',Path(tmp)),patch('dashboard.app.utc_now',lambda:DURING_RACE_COOLDOWN),\
                patch('dashboard.historical.import_by_key',import_by_key),TestClient(app) as client:
            yield client

    def wait_for_archive(self, client):
        deadline=time.monotonic()+20
        while client.get('/api/state').json()['archive']['status']=='importing':
            self.assertLess(time.monotonic(),deadline); time.sleep(.05)
        return client.get('/api/state').json()

    def test_archive_catalog_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.archive_client(tmp) as client:
                body=client.get('/api/archive?year=2026').json()
                self.assertEqual(body['years'],list(range(2018,2027)))
                self.assertEqual(body['year'],2026)
                self.assertEqual([s['available'] for s in body['events'][3]['sessions']],[True,False])
                self.assertEqual(client.get('/api/archive').json()['year'],2026)
                for year in (2017,2027):
                    self.assertEqual(client.get(f'/api/archive?year={year}').status_code,422)
                with patch('dashboard.historical.download',side_effect=subprocess.CalledProcessError(6,'curl')):
                    response=client.get('/api/archive?year=2025')
                self.assertEqual(response.status_code,502)
                self.assertIn('archive index',response.json()['detail'])

    def test_archive_load_replays_the_session_and_survives_mode_switch(self):
        imported=[]
        def fake_import(year,key,output,fetch):
            imported.append((year,key)); shutil.copy(DEMO,output)
        with tempfile.TemporaryDirectory() as tmp:
            with self.archive_client(tmp,fake_import) as client:
                self.assertIsNone(client.get('/api/state').json()['archive'])
                response=client.post('/api/archive/load',json={'year':2026,'key':41})
                self.assertEqual(response.status_code,202)
                self.assertEqual(response.json(),dict(id=1,status='importing',year=2026,key=41,label='2026 Bahrain Grand Prix · Race',error=None))
                state=self.wait_for_archive(client)
                expected=Path(tmp)/'archive-2026-bahrain-grand-prix-race-41.jsonl'
                self.assertEqual(state['archive']['status'],None)
                self.assertEqual(app.state.recording,expected)
                self.assertTrue(state['replay']['label'].endswith(expected.name))
                self.assertEqual(imported,[(2026,41)])
                client.post('/api/mode',json={'mode':'live'})
                self.assertIsNone(client.get('/api/state').json()['replay'])
                state=client.post('/api/mode',json={'mode':'replay'}).json()
                self.assertTrue(state['replay']['label'].endswith(expected.name))
                self.assertEqual(state['archive']['status'],None)
                # Loading again reuses the recording; loading from Live switches to Historical.
                client.post('/api/mode',json={'mode':'live'})
                self.assertEqual(client.post('/api/archive/load',json={'year':2026,'key':41}).json()['id'],2)
                state=self.wait_for_archive(client)
                self.assertEqual(state['connection']['mode'],'replay')
                self.assertEqual(imported,[(2026,41)])

    def test_archive_load_rejects_busy_unknown_unavailable_and_reports_errors(self):
        def failed_import(year,key,output,fetch):
            raise ValueError('Archive lacks SessionInfo')
        with tempfile.TemporaryDirectory() as tmp:
            with self.archive_client(tmp,failed_import) as client:
                before=app.state.timing
                self.assertEqual(client.post('/api/archive/load',json={'year':2026,'key':999}).status_code,422)
                unavailable=client.post('/api/archive/load',json={'year':2026,'key':31})
                self.assertEqual(unavailable.status_code,422)
                self.assertIn('not archived yet',unavailable.json()['detail'])
                self.assertEqual(client.post('/api/archive/load',json={'year':2017,'key':41}).status_code,422)
                app.state.archive_job=dict(status='importing')
                self.assertEqual(client.post('/api/archive/load',json={'year':2026,'key':41}).status_code,409)
                app.state.archive_job=None
                self.assertEqual(client.post('/api/archive/load',json={'year':2026,'key':41}).status_code,202)
                state=self.wait_for_archive(client)
                self.assertEqual((state['archive']['status'],state['archive']['error']),('error','Archive lacks SessionInfo'))
                self.assertIs(app.state.timing,before)
                self.assertEqual(app.state.recording,Path(DEMO))
                self.assertEqual(state['replay']['label'],'Demo replay')
