"""Offline dashboard protocol, state, replay, API and notebook export tests."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient
from dashboard.app import app
from dashboard.state import State, merge, match_predictions
from dashboard.replay import Replay
from dashboard.live import decode_frame, feed_events, run_live, TOPICS
from test_prediction import NS

INFO = dict(Key=1, Type='Race', StartDate='2026-10-04T15:00:00', Meeting={'Location':'Kuala Lumpur'})
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

    def test_http_websocket_and_invalid_control(self):
        with patch.dict('os.environ',{'F1_MODE':'replay'}), TestClient(app) as client:
            self.assertEqual(client.get('/api/state').status_code,200)
            self.assertEqual(client.post('/api/replay/control',json={'action':'pause'}).status_code,200)
            self.assertTrue(client.get('/api/state').json()['replay']['paused'])
            self.assertEqual(client.post('/api/replay/control',json={'action':'speed','speed':3}).status_code,422)
            with client.websocket_connect('/ws') as ws:
                self.assertIn('drivers',ws.receive_json())
