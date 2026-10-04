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

ROOT = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app):
    mode = os.getenv('F1_MODE', 'replay')
    if mode not in ('live', 'replay'):
        raise ValueError('F1_MODE must be live or replay')
    prediction_path = Path(os.getenv('F1_PREDICTIONS', str(ROOT / 'predictions.json')))
    predictions = json.loads(prediction_path.read_text()) if prediction_path.exists() else None
    app.state.timing = State(predictions, mode)
    app.state.replay = None
    if mode == 'replay':
        app.state.replay = Replay(app.state.timing, Path(os.getenv('F1_RECORDING', str(ROOT / 'recordings/demo.jsonl'))))
        async def advance():
            previous = time.monotonic()
            while True:
                now = time.monotonic()
                app.state.replay.advance(now - previous)
                previous = now
                await asyncio.sleep(.05)
        task = asyncio.create_task(advance())
    else:
        recording = ROOT / 'recordings' / f'live-{int(time.time())}.jsonl'
        task = asyncio.create_task(run_live(app.state.timing, recording))
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(lifespan=lifespan)


@app.get('/api/state')
async def state():
    return app.state.timing.snapshot()


@app.websocket('/ws')
async def websocket(ws: WebSocket):
    if ws.headers.get('origin') not in (None, 'http://localhost:5173', 'http://127.0.0.1:5173',
                                      'http://localhost:8000', 'http://127.0.0.1:8000'):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        while True:
            await ws.send_json(app.state.timing.snapshot())
            await asyncio.sleep(1)
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
