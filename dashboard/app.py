import asyncio
import json
import os
import subprocess
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from . import historical
from .live import run_live
from .replay import Replay
from .state import State
from .geometry import Geometry

ROOT = Path(__file__).resolve().parent


MODES = ('live', 'replay')
DEMO_RECORDING = ROOT / 'recordings/demo.jsonl'


def default_recording():
    """F1_RECORDING if set (run.py points it at the most recent race), else the synthetic demo."""
    if os.getenv('F1_RECORDING'):
        return Path(os.environ['F1_RECORDING'])
    return DEMO_RECORDING


def utc_now():
    return datetime.now(timezone.utc)


def prepare_mode(app, mode, recording):
    timing = State(app.state.predictions, mode, pit_loss=app.state.pit_loss)
    return timing, Replay(timing, recording) if mode == 'replay' else None


async def start_mode(app, mode, recording=None):
    """Build fresh timing state for `mode`, then stop the current task and start the new one.

    Seeking an archive replay to lights out takes seconds, so it runs off the event loop
    while the current mode keeps serving; a recording that fails to load changes nothing.
    """
    recording = recording or app.state.recording
    timing, replay = await asyncio.to_thread(prepare_mode, app, mode, recording)
    await stop_mode(app)
    if mode == 'replay':
        app.state.recording = recording
    timing.archive = app.state.archive_job
    app.state.timing, app.state.replay = timing, replay
    if mode == 'replay':
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
    if app.state.task is None:
        return
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
    pit_loss_path = Path(os.getenv('F1_PIT_LOSS', str(ROOT / 'pit_loss.json')))
    app.state.pit_loss = json.loads(pit_loss_path.read_text()) if pit_loss_path.exists() else None
    app.state.geometry = Geometry()
    app.state.mode_lock = asyncio.Lock()
    app.state.recording = default_recording()
    app.state.archive_job = None
    app.state.archive_task = None
    app.state.task = None
    await start_mode(app, mode)
    yield
    if app.state.geometry.task:
        app.state.geometry.task.cancel()
    if app.state.archive_task:
        app.state.archive_task.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.archive_task
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
            await start_mode(app, body.mode)
    return app.state.timing.snapshot()


def archive_years(now):
    return list(range(historical.FIRST_YEAR, now.year + 1))


def set_archive_job(app, **job):
    app.state.archive_job = job
    app.state.timing.archive = job


async def read_archive(read, year, now):
    """Run an index reader off the event loop; a missing, uncached index is a 502."""
    if year not in archive_years(now):
        raise HTTPException(422, f'year must be between {historical.FIRST_YEAR} and {now.year}')
    try:
        return await asyncio.to_thread(read, year, now, historical.download)
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        raise HTTPException(502, f'Could not fetch the {year} archive index; check the network connection.') from exc


@app.get('/api/archive')
async def archive(year: int | None = None):
    now = utc_now()
    year = now.year if year is None else year
    events = await read_archive(historical.catalog, year, now)
    return dict(years=archive_years(now), year=year, events=events)


class ArchiveLoad(BaseModel):
    year: int
    key: int


async def load_archive(app, year, meeting, session):
    """Import the session if it is not recorded yet, then replay it in place of the current mode."""
    output = historical.recording_path(year, meeting, session)
    try:
        if not output.exists():
            await asyncio.to_thread(historical.import_by_key, year, session['Key'], output, historical.download)
        async with app.state.mode_lock:
            await start_mode(app, 'replay', output)
    except Exception as exc:  # Report any failure in the panel; the current mode keeps running.
        set_archive_job(app, **dict(app.state.archive_job, status='error', error=str(exc) or type(exc).__name__))
    else:
        set_archive_job(app, **dict(app.state.archive_job, status=None))


@app.post('/api/archive/load', status_code=202)
async def load(body: ArchiveLoad):
    now = utc_now()
    found = historical.find_session(await read_archive(historical.load_index, body.year, now), body.key)
    if not found:
        raise HTTPException(422, f'No archive session {body.key} in {body.year}')
    meeting, session = found
    if not historical.available(session, now):
        raise HTTPException(422, f"{meeting['Name']} · {session['Name']} is not archived yet")
    if (app.state.archive_job or {}).get('status') == 'importing':
        raise HTTPException(409, 'Another session is already loading')
    # `id` lets the picker tell this job's result from an earlier one for the same session.
    set_archive_job(app, id=(app.state.archive_job or {}).get('id', 0) + 1, status='importing', year=body.year, key=body.key,
                    label=f"{body.year} {meeting['Name']} · {session['Name']}", error=None)
    app.state.archive_task = asyncio.create_task(load_archive(app, body.year, meeting, session))
    return app.state.archive_job
