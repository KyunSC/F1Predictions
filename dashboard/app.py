import asyncio
import json
import os
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from .live import run_live
from .replay import Replay
from .state import State
from .geometry import Geometry

ROOT = Path(__file__).resolve().parent


MODES = ('live', 'replay')
ARCHIVE_RECORDING = ROOT / 'recordings/archive-2026-bahrain-race.jsonl'
DEMO_RECORDING = ROOT / 'recordings/demo.jsonl'


def default_recording():
    """F1_RECORDING if set, else the imported archive race, else the synthetic demo."""
    if os.getenv('F1_RECORDING'):
        return Path(os.environ['F1_RECORDING'])
    return ARCHIVE_RECORDING if ARCHIVE_RECORDING.exists() else DEMO_RECORDING


def start_mode(app, mode):
    """Build fresh timing state for `mode` and start its background task."""
    app.state.timing = State(app.state.predictions, mode)
    app.state.replay = None
    if mode == 'replay':
        app.state.replay = Replay(app.state.timing, default_recording())
        async def advance():
            previous = time.monotonic()
            while True:
                now = time.monotonic()
                app.state.replay.advance(now - previous)
                previous = now
                await asyncio.sleep(.05)
        app.state.task = asyncio.create_task(advance())
    else:
        recording = ROOT / 'recordings' / f'live-{int(time.time())}.jsonl'
        app.state.task = asyncio.create_task(run_live(app.state.timing, recording))


async def stop_mode(app):
    app.state.task.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.task


@asynccontextmanager
async def lifespan(app):
    mode = os.getenv('F1_MODE', 'replay')
    if mode not in MODES:
        raise ValueError('F1_MODE must be live or replay')
    prediction_path = Path(os.getenv('F1_PREDICTIONS', str(ROOT / 'predictions.json')))
    app.state.predictions = json.loads(prediction_path.read_text()) if prediction_path.exists() else None
    app.state.geometry = Geometry()
    app.state.mode_lock = asyncio.Lock()
    start_mode(app, mode)
    yield
    if app.state.geometry.task:
        app.state.geometry.task.cancel()
    await stop_mode(app)


app = FastAPI(lifespan=lifespan)


@app.get('/api/state')
async def state():
    return app.state.timing.snapshot()


@app.get('/api/track-map')
async def track_map():
    geometry = app.state.geometry
    geometry.request(app.state.timing)
    task = geometry.task
    await asyncio.shield(task)
    return geometry.request(app.state.timing)


@app.websocket('/ws/positions')
async def position_websocket(ws: WebSocket):
    await stream_websocket(ws, positions=True)


@app.websocket('/ws')
async def websocket(ws: WebSocket):
    await stream_websocket(ws, positions=False)


async def stream_websocket(ws: WebSocket, positions):
    if ws.headers.get('origin') not in (None, 'http://localhost:5173', 'http://127.0.0.1:5173',
                                      'http://localhost:8000', 'http://127.0.0.1:8000'):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        while True:
            await ws.send_json(app.state.timing.position_snapshot() if positions else app.state.timing.snapshot())
            await asyncio.sleep(.2 if positions else 1)
    except (WebSocketDisconnect, RuntimeError):
        pass


class Control(BaseModel):
    action: str
    speed: int | None = None


@app.post('/api/replay/control')
async def control(body: Control):
    if app.state.replay is None:
        raise HTTPException(409, 'Replay controls are unavailable in live mode')
    try:
        app.state.replay.control(body.action, body.speed)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return app.state.timing.snapshot()


class ModeSwitch(BaseModel):
    mode: str


@app.post('/api/mode')
async def switch_mode(body: ModeSwitch):
    if body.mode not in MODES:
        raise HTTPException(422, 'mode must be live or replay')
    async with app.state.mode_lock:
        if app.state.timing.mode != body.mode:
            await stop_mode(app)
            start_mode(app, body.mode)
    return app.state.timing.snapshot()
