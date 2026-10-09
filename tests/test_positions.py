import asyncio
import base64
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from dashboard.app import app
from dashboard.geometry import Geometry, resolve, validate, validate_provider
from dashboard.positions import decode_positions
from dashboard.state import State
from dashboard.replay import Replay


def packet(times=(0, .2), number='44'):
    return {'Position': [dict(Timestamp=f'2026-10-04T12:00:{t:06.3f}Z', Entries={number: dict(X=t*100,Y=2,Z=0,Status='OffTrack')}) for t in times]}


def compressed(value):
    obj=zlib.compressobj(wbits=-15)
    return base64.b64encode(obj.compress(json.dumps(value).encode())+obj.flush()).decode()


class PositionTests(unittest.TestCase):
    def test_compressed_snapshot_order_and_duplicates(self):
        state=State();state.apply('Position.z',compressed(packet((.2,0))),now=10)
        self.assertEqual([s['x'] for s in state.positions.samples['44']],[0,20])
        self.assertAlmostEqual(state.positions.samples['44'][0]['presentation_timestamp'],9.8)
        state.apply('Position.z',packet(),now=11)
        self.assertEqual(len(state.positions.samples['44']),2)
        self.assertEqual(state.positions.samples['44'][0]['status'],'OffTrack')
        self.assertIsNone(state.last_update)
        state.apply('TimingData',{},now=12)
        self.assertEqual(state.positions.received,10)
        self.assertEqual(state.position_snapshot(12)['driver_age_seconds']['44'],2)

    def test_malformed_isolated_and_reset(self):
        state=State();state.apply('Position.z','bad compressed packet')
        self.assertIn('Malformed',state.positions.error)
        state.apply('TimingData',{},now=10);self.assertEqual(state.last_update,10)
        bad=packet();bad['Position'][0]['Entries']['44']['X']=float('nan')
        with self.assertRaises(ValueError):decode_positions(bad)
        state.apply('SessionInfo',{'Key':1});state.apply('Position.z',packet(),now=1)
        generation=state.positions.generation
        state.apply('SessionInfo',{'Key':2});self.assertFalse(state.positions.samples)
        self.assertGreater(state.positions.generation,generation)
        state.apply('Position.z',{'Position':[{'Timestamp':'2026-10-04T12:00:00Z','Entries':{}}]})
        self.assertFalse(state.positions.samples)

    def test_bounded_history(self):
        state=State()
        for i in range(1000):
            state.apply('Position.z',packet((i/100,)),now=i/100)
        self.assertLessEqual(len(state.positions.samples['44']),300)
        self.assertEqual(len(state.position_snapshot(30)['samples']['44']),1)

    def test_replay_clock_old_recording_and_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.jsonl';path.write_text(json.dumps(dict(at=100,topic='TimingData',data={})))
            state=State();r=Replay(state,path);r.advance(0)
            self.assertEqual(state.position_snapshot()['reason'],'No position data in this recording.')
        state=State();r=Replay(state,Path('dashboard/recordings/demo.jsonl'));r.advance(1)
        self.assertTrue(state.synthetic);self.assertEqual(len(state.positions.samples),6)
        r.control('pause');r.advance(9);self.assertEqual(state.position_snapshot()['presentation_clock'],1)
        r.control('resume');r.control('speed',2);r.advance(1);self.assertEqual(r.position,3)
        self.assertTrue(all(s['presentation_timestamp']<=3 for h in state.positions.samples.values() for s in h))
        r.control('speed',5);r.advance(1);self.assertEqual(r.position,8)
        generation=state.positions.generation;r.control('restart');self.assertGreater(state.positions.generation,generation)
        r.advance(9999);end=r.position;r.advance(10);self.assertEqual(r.position,end);self.assertTrue(state.replay['ended'])

    def test_demo_track_order_matches_timing(self):
        # The synthetic demo once placed the leader at the back of the pack.
        outline=json.loads(Path('dashboard/demo-outline.json').read_text())
        points=list(zip(outline['x'],outline['y']));points.append(points[0])
        segments=[];length=0
        for a,b in zip(points,points[1:]):
            size=((b[0]-a[0])**2+(b[1]-a[1])**2)**.5
            if size:segments.append((a,b,length,size));length+=size
        def lap_distance(x,y):
            best=None
            for a,b,start,size in segments:
                dx,dy=b[0]-a[0],b[1]-a[1];f=max(0,min(1,((x-a[0])*dx+(y-a[1])*dy)/size**2))
                d=(a[0]+dx*f-x)**2+(a[1]+dy*f-y)**2
                if best is None or d<best[0]:best=(d,start+size*f)
            return best[1]
        timing={};checked=0
        for line in Path('dashboard/recordings/demo.jsonl').read_text().splitlines():
            event=json.loads(line)
            if event['topic']=='TimingData':
                for n,v in event['data'].get('Lines',{}).items():
                    if 'Position' in v:timing[n]=int(v['Position'])
            if event['topic']!='Position.z':continue
            for entry in json.loads(zlib.decompress(base64.b64decode(event['data']),-15))['Position']:
                distance={n:lap_distance(v['X'],v['Y']) for n,v in entry['Entries'].items()}
                leader=min(timing,key=timing.get)
                behind={n:(distance[leader]-d)%length for n,d in distance.items()}
                self.assertEqual(sorted(behind,key=behind.get),sorted(timing,key=timing.get),entry['Timestamp'])
                self.assertLess(max(behind.values()),length/2);checked+=1
        self.assertGreater(checked,500)

    def test_geometry_validation_and_venue(self):
        info={'StartDate':'2026-10-04','Meeting':{'Location':'Kuala Lumpur','Circuit':{'Key':63,'ShortName':'Sakhir'}}}
        with self.assertRaises(ValueError):resolve(info)
        good=dict(x=[0,1,2],y=[0,2,0],rotation=90)
        self.assertEqual(validate(good)['bounds'],[0,0,2,2])
        for bad in [dict(good,rotation=float('inf')),dict(good,x=[0]),dict(good,y=[0,0,0])]:
            with self.assertRaises(ValueError):validate(bad)
        with self.assertRaises(ValueError):validate_provider(dict(good,circuitKey=63,year=2022),63,2026,info)

    def test_geometry_cache_failure_and_late_result(self):
        async def run():
            with tempfile.TemporaryDirectory() as tmp:
                cache=Path(tmp);g=Geometry(cache)
                info={'StartDate':'2026-01-01','Meeting':{'Location':'Monza','Circuit':{'Key':1,'ShortName':'Monza'}}}
                data=dict(x=[0,1,2],y=[0,2,0],rotation=0,circuitKey=1,year=2026,location='Monza')
                (cache/'1-2026.json').write_text(json.dumps(data));g.key='current'
                with patch('dashboard.geometry.httpx.AsyncClient',side_effect=AssertionError('offline')):
                    await g.load('current',info,False);self.assertTrue(g.value['available'])
                    await g.load('obsolete',{},False);self.assertTrue(g.value['available'])
                    (cache/'1-2026.json').unlink();await g.load('current',info,False);self.assertFalse(g.value['available'])
        asyncio.run(run())

    def test_websocket_contracts_and_origin(self):
        with patch.dict('os.environ',{'F1_MODE':'replay'}),TestClient(app) as client:
            client.post('/api/replay/control',json={'action':'pause'})
            geometry=client.get('/api/track-map').json();self.assertTrue(geometry['synthetic'])
            with client.websocket_connect('/ws/positions') as ws:
                data=ws.receive_json()
                for key in ('session_identity','generation','sequence','samples','presentation_clock','replay','available'):
                    self.assertIn(key,data)
            for endpoint in ('/ws','/ws/positions'):
                with self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect(endpoint,headers={'origin':'https://untrusted.example'}):pass

    def test_subscription_rejection_retries_timing_only(self):
        from unittest.mock import AsyncMock, Mock
        from dashboard.live import connect
        state=State(mode='live')
        http=AsyncMock()
        http.cookies={}
        response=Mock();response.json.return_value={'connectionToken':'test'}
        http.post.return_value=response
        context=AsyncMock();context.__aenter__.return_value=http
        socket=AsyncMock();socket.recv.side_effect=['{}\x1e',json.dumps({'type':3,'invocationId':'1','error':'Position unavailable'})+'\x1e']
        ws_context=AsyncMock();ws_context.__aenter__.return_value=socket
        async def run():
            with tempfile.TemporaryDirectory() as tmp, patch('dashboard.live.httpx.AsyncClient',return_value=context),patch('dashboard.live.websockets.connect',return_value=ws_context):
                with self.assertRaises(RuntimeError):await connect(state,Path(tmp)/'recording.jsonl')
                self.assertFalse(state.positions_enabled)
                socket.recv.side_effect=['{}\x1e',asyncio.CancelledError()]
                with self.assertRaises(asyncio.CancelledError):await connect(state,Path(tmp)/'recording.jsonl')
                subscription=json.loads(socket.send.call_args_list[-1].args[0].rstrip('\x1e'))
                self.assertNotIn('Position.z',subscription['arguments'][0])
                self.assertIn('TimingData',subscription['arguments'][0])
                self.assertIn('timing-only',state.position_snapshot()['reason'])
        asyncio.run(run())

class PositionRegressionTests(unittest.TestCase):
    def test_delayed_packet_retains_session_clock(self):
        state=State();state.apply('Position.z',packet((0,)),now=10)
        state.apply('Position.z',packet((1,)),now=13)
        self.assertEqual(state.positions.samples['44'][-1]['presentation_timestamp'],11)

    def test_malformed_driver_does_not_drop_other_cars(self):
        state=State();value=packet((0,))
        value['Position'][0]['Entries']['1']={'X':None,'Y':0,'Z':0}
        state.apply('Position.z',value,now=0)
        self.assertIn('44',state.positions.samples)
        self.assertEqual(state.position_snapshot()['diagnostics']['rejected']['invalid_sample'],1)

    def test_partial_coverage_number_normalization_late_updates_and_gaps(self):
        state=State();state.apply('DriverList',{'44':{},'1':{}})
        state.apply('Position.z',packet((0,),number='044'),now=10)
        self.assertEqual(state.position_snapshot()['diagnostics']['missing_drivers'],['1'])
        state.apply('Position.z',packet((6,),number='44'),now=16)
        state.apply('Position.z',packet((1,),number='44'),now=17)
        stats=state.position_snapshot()['diagnostics']
        self.assertEqual(stats['gaps_over_5s'],{'44':1})
        self.assertEqual(stats['rejected'],{'duplicate_or_late':1})
        self.assertEqual(state.positions.samples['44'][-1]['x'],600)
        state.reset();self.assertEqual(state.position_snapshot()['diagnostics']['coordinate_packets'],0)

    def test_long_delivery_delay_keeps_stale_sample_without_crashing(self):
        state=State();state.apply('Position.z',packet((0,)),now=0)
        state.apply('Position.z',packet((1,)),now=20)
        snapshot=state.position_snapshot(20)
        self.assertEqual(snapshot['driver_age_seconds']['44'],19)
        self.assertEqual(snapshot['samples']['44'][-1]['presentation_timestamp'],1)
