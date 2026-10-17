"""Local acceptance harness using a full recording, never future seed state.

python -m dashboard.verify_replay --at 3600
Listens on 127.0.0.1:8000, where the frontend's rewrites send /api and /ws, so stop
`npm run dev` first and serve the current build with `npm run build && npm start`.
Checkpoint, fault and result endpoints live under /api/verify/ so the frontend
proxies them too; they exist only in this separately launched test harness.
Checkpoints are absolute recording seconds, the same clock as the seek control.
"""
import argparse
import asyncio
import hashlib
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
import uvicorn
from .geometry import Geometry
from .replay import Replay
from .state import State

ROOT = Path(__file__).resolve().parents[1]


def checkpoint(recording, at):
    state = State()
    replay = Replay(state, recording)
    replay.control('seek', position=at)
    replay.control('pause')
    return state, replay


def create_app(recording, at, output):
    state, replay = checkpoint(recording, at)
    geometry = Geometry()
    disconnected_until = 0.
    omit_positions_until = -1.
    original_apply = state.apply

    def apply(topic, payload, timestamp=None, now=None, record=True):
        if topic == 'Position.z' and now is not None and now <= omit_positions_until:
            return
        original_apply(topic, payload, timestamp, now, record=record)
    state.apply = apply

    @asynccontextmanager
    async def lifespan(app):
        async def tick():
            previous = time.monotonic()
            while True:
                now = time.monotonic()
                replay.advance(now-previous)
                previous = now
                await asyncio.sleep(.05)
        task = asyncio.create_task(tick())
        yield
        task.cancel()

    app = FastAPI(lifespan=lifespan)

    @app.get('/api/state')
    async def current():
        return state.snapshot()

    @app.get('/api/track-map')
    async def track():
        geometry.request(state)
        await geometry.task
        return geometry.request(state)

    @app.post('/api/replay/control')
    async def control(body: dict):
        replay.control(body['action'], body.get('speed'), body.get('position'))
        return state.snapshot()

    @app.post('/api/verify/checkpoint/{moment}')
    async def seek(moment: float):
        nonlocal omit_positions_until
        omit_positions_until = -1.  # a checkpoint starts clean; faults never outlive it
        replay.control('seek', position=moment)
        replay.control('pause')
        frame = state.position_snapshot()
        output.mkdir(parents=True, exist_ok=True)
        (output / f'checkpoint-{moment:g}.json').write_text(json.dumps(frame))
        upcoming = replay.events[replay.index]['at'] if replay.index < len(replay.events) else None
        return {'at': replay.position, 'preceding_events': replay.index, 'next_event': upcoming}

    @app.post('/api/verify/fault/{kind}')
    async def fault(kind: str):
        nonlocal disconnected_until, omit_positions_until
        if kind == 'disconnect':
            disconnected_until = time.monotonic()+4
        elif kind == 'positions':
            omit_positions_until = replay.position+19
        return {'fault': kind}

    @app.websocket('/ws/positions')
    async def positions(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                if time.monotonic() < disconnected_until:
                    await ws.close(code=1012)
                    return
                await ws.send_json(state.position_snapshot())
                await asyncio.sleep(.2)
        except WebSocketDisconnect:
            pass

    @app.websocket('/ws')
    async def timing(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.send_json(state.snapshot())
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            pass

    @app.get('/api/verify/audit.js')
    async def audit_script():
        return FileResponse(ROOT/'verification/track-map/audit.js', media_type='text/javascript')

    @app.post('/api/verify/results/{name}')
    async def results(name: str, body: dict):
        if not name.replace('-', '').isalnum():
            return {'error': 'Invalid name'}
        (output / (name+'.json')).write_text(json.dumps(body, indent=2))
        return {'saved': name}

    @app.get('/api/verify/frame')
    async def frame():
        return state.position_snapshot()

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recording', type=Path, default=ROOT/'cache/suzuka-replay.jsonl')
    parser.add_argument('--at', type=float, default=3600)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--output', type=Path, default=ROOT/'verification/track-map')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'source.json').write_text(json.dumps({'recording': args.recording.name,
        'sha256': hashlib.sha256(args.recording.read_bytes()).hexdigest()}, indent=2))
    uvicorn.run(create_app(args.recording, args.at, args.output), host='127.0.0.1', port=args.port)
