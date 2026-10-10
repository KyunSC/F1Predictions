"""SignalR Core JSON protocol. Actual Position.z coordinates; CarData.z excluded.

F1 only streams Position.z to F1TV subscribers. Without a subscription token the
connection still receives timing, and the track map reports why it is empty.
"""
import asyncio
import base64
import json
import os
import time
from pathlib import Path
from urllib.parse import quote
import httpx
import websockets
from .state import TOPICS

BASE = 'https://livetiming.formula1.com/signalrcore'
RS = '\x1e'
SIGN_IN = 'run `./.venv/bin/python -m fastf1 auth f1tv --authenticate` or set F1TV_TOKEN, then restart'


def token_expiry(token):
    try:
        payload = token.split('.')[1]
        return json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4))).get('exp')
    except (IndexError, ValueError, AttributeError):
        return None


def load_token(env=os.environ, path=None, now=None):
    """Return (token, problem). The token itself is never logged or recorded.

    FastF1's sign-in stores the token in its user data directory.
    """
    token = env.get('F1TV_TOKEN', '').strip()
    if not token:
        if path is None:
            import platformdirs
            path = Path(platformdirs.user_data_dir('fastf1')) / 'f1auth.json'
        try:
            token = path.read_text().strip()
        except OSError:
            token = ''
    if not token:
        return None, f'Car positions need an F1TV subscription: {SIGN_IN}'
    expiry = token_expiry(token)
    if expiry is None:
        return None, f'F1TV token is malformed: {SIGN_IN}'
    if expiry < (now if now is not None else time.time()):
        return None, f'F1TV token expired: {SIGN_IN}'
    return token, None


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


async def connect(state, record_path, token_loader=load_token):
    token, state.positions.auth_problem = token_loader()
    auth = {'Authorization': f'Bearer {token}'} if token else {}
    async with httpx.AsyncClient(timeout=15) as client:
        await client.options(BASE + '/negotiate')
        response = await client.post(BASE + '/negotiate?negotiateVersion=1', headers=auth)
        response.raise_for_status()
        negotiated = response.json()
        token = negotiated.get('connectionToken') or negotiated['connectionId']
        cookies = '; '.join(f'{k}={v}' for k, v in client.cookies.items())
        url = BASE.replace('https:', 'wss:') + '?id=' + quote(token, safe='')
        async with websockets.connect(url, additional_headers={'Cookie': cookies, **auth}, open_timeout=15) as ws:
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
