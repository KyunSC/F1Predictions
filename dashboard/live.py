"""Unauthenticated SignalR Core JSON protocol. Actual Position.z coordinates; CarData.z excluded."""
import asyncio
import json
import time
from urllib.parse import quote
import httpx
import websockets
from .state import TOPICS

BASE = 'https://livetiming.formula1.com/signalrcore'
RS = '\x1e'


def decode_frame(frame):
    return [json.loads(part) for part in frame.split(RS) if part]


def feed_events(message):
    if message.get('type') == 1 and message.get('target', '').lower() == 'feed':
        args = message.get('arguments', [])
        if len(args) >= 2 and args[0] in TOPICS:
            yield args[0], args[1], args[2] if len(args) > 2 else None
    elif message.get('type') == 3:
        if message.get('error'):
            raise RuntimeError(message['error'])
        result = message.get('result', {})
        if isinstance(result, dict):
            # Identity must arrive before other snapshots, including on reconnect.
            for topic in sorted(result, key=lambda t: t != 'SessionInfo'):
                if topic in TOPICS:
                    yield topic, result[topic], None


async def connect(state, record_path):
    async with httpx.AsyncClient(timeout=15) as client:
        await client.options(BASE + '/negotiate')
        response = await client.post(BASE + '/negotiate?negotiateVersion=1')
        response.raise_for_status()
        negotiated = response.json()
        token = negotiated.get('connectionToken') or negotiated['connectionId']
        cookies = '; '.join(f'{k}={v}' for k, v in client.cookies.items())
        url = BASE.replace('https:', 'wss:') + '?id=' + quote(token, safe='')
        async with websockets.connect(url, additional_headers={'Cookie': cookies}, open_timeout=15) as ws:
            await ws.send(json.dumps({'protocol': 'json', 'version': 1}) + RS)
            frames = decode_frame(await asyncio.wait_for(ws.recv(), 15))
            if not frames or frames[0].get('error'):
                raise RuntimeError('SignalR handshake refused')
            state.connection, state.error = 'connected', None
            # Invalidate old snapshots until the new subscription supplies current data.
            state.reset()
            await ws.send(json.dumps({'type': 1, 'invocationId': '1', 'target': 'Subscribe', 'arguments': [TOPICS if state.positions_enabled else [t for t in TOPICS if t != 'Position.z']]}) + RS)
            if not state.positions_enabled:
                state.positions.error = 'Position subscription rejected; timing-only connection'
            record_path.parent.mkdir(parents=True, exist_ok=True)
            subscription_confirmed = False
            with record_path.open('a') as recording:
                while True:
                    try:
                        frame = await asyncio.wait_for(ws.recv(), 45)
                    except websockets.exceptions.ConnectionClosed:
                        if not subscription_confirmed:
                            state.positions_enabled = False
                        raise
                    for message in decode_frame(frame):
                        if message.get('type') == 7:
                            if not subscription_confirmed:
                                state.positions_enabled = False
                            raise RuntimeError(message.get('error', 'Server closed connection'))
                        if message.get('type') == 6:
                            await ws.send('{"type":6}' + RS)
                        if message.get('type') == 3 and message.get('error') and state.positions_enabled:
                            state.positions_enabled = False
                            raise RuntimeError('Position subscription rejected; reconnecting with timing subscriptions')
                        if message.get('type') == 3 and not message.get('error'):
                            subscription_confirmed = True
                        for topic, data, timestamp in feed_events(message):
                            state.apply(topic, data, timestamp)
                            if topic == 'TimingData' and timestamp and state.topics.get('SessionInfo', {}).get('SessionStatus') == 'Started':
                                state.live_verified = True
                            recording.write(json.dumps(dict(at=time.time(), topic=topic, data=data, timestamp=timestamp)) + '\n')
                            recording.flush()


async def run_live(state, path, connector=connect, sleep=asyncio.sleep):
    delay = 1
    while True:
        try:
            state.connection = 'connecting'
            await connector(state, path)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.connection = 'reconnecting'
            state.error = f'{type(exc).__name__}: {exc}'
            state.reconnects += 1
            await sleep(delay)
            delay = min(delay * 2, 30)
