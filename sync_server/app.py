"""Room-scoped clipboard relay. Clipboard content is never persisted."""
import asyncio
import base64
import binascii
from collections import OrderedDict
from datetime import datetime
import hmac
import json
import re
import time
from uuid import UUID

from aiohttp import web, WSMsgType

MAX_BINARY = 25 * 1024 * 1024
MAX_MESSAGE = 36 * 1024 * 1024
ROOM = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
MIME = re.compile(r'[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+\Z')
STATE = web.AppKey('relay_state', dict)


def validate_event(event):
    if not isinstance(event, dict) or event.get('type') != 'clipboard':
        raise ValueError('Expected a clipboard event')
    for key in ('id', 'origin'):
        if not isinstance(event.get(key), str):
            raise ValueError('Event id and origin must be UUIDs')
        UUID(event[key])
    stamp = event.get('createdAt')
    if not isinstance(stamp, str) or len(stamp) > 64:
        raise ValueError('createdAt must be an ISO8601 timestamp')
    parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('createdAt must include timezone')
    payload = event.get('payload')
    if not isinstance(payload, dict):
        raise ValueError('Missing payload')
    kind = payload.get('type')
    if kind == 'text':
        if not isinstance(payload.get('text'), str) or len(payload['text']) > 100_000:
            raise ValueError('Text limit is 100000 characters')
        clean = {'type': kind, 'text': payload['text']}
    elif kind in ('image', 'file'):
        name, mime, data = (payload.get(k) for k in ('name', 'mime', 'data'))
        if (not isinstance(name, str) or not name.strip() or len(name) > 255
                or name.endswith(('.', ' '))
                or name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1, 10)), *('LPT'+str(i) for i in range(1, 10))}
                or any(ord(c) < 32 or ord(c) == 127 or c in '/\\:<>\"|?*' for c in name)):
            raise ValueError('Invalid filename')
        if not isinstance(mime, str) or len(mime) > 255 or not MIME.fullmatch(mime):
            raise ValueError('Invalid MIME type')
        if not isinstance(data, str) or len(data) > ((MAX_BINARY + 2) // 3) * 4:
            raise ValueError('Binary limit is 25 MiB')
        try:
            decoded = base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('Invalid base64 data') from None
        if len(decoded) > MAX_BINARY:
            raise ValueError('Binary limit is 25 MiB')
        clean = {'type': kind, 'name': name, 'mime': mime, 'data': data}
    else:
        raise ValueError('Invalid payload type')
    return {'type': 'clipboard', 'id': str(UUID(event['id'])),
            'origin': str(UUID(event['origin'])), 'createdAt': stamp, 'payload': clean}


async def health(request):
    state = request.app[STATE]
    return web.json_response({'status': 'ok', 'service': 'clipboard-sync-server',
                              'version': '0.1.0', 'uptimeSeconds': int(time.monotonic()-state['started'])})


async def landing(request):
    return web.Response(text=LANDING, content_type='text/html')


async def relay(request):
    state = request.app[STATE]
    authorization = request.headers.get('Authorization', '')
    if not hmac.compare_digest(authorization.encode(), ('Bearer '+state['token']).encode()):
        raise web.HTTPUnauthorized(text='{"error":"Bearer token required"}', content_type='application/json')
    room = request.match_info['room']
    if not ROOM.fullmatch(room):
        raise web.HTTPBadRequest(text='{"error":"Invalid room"}', content_type='application/json')
    if sum(len(m) for m in state['rooms'].values()) >= 128:
        raise web.HTTPServiceUnavailable(text='Connection limit reached')
    ws = web.WebSocketResponse(max_msg_size=MAX_MESSAGE, heartbeat=30, compress=False)
    await ws.prepare(request)
    peers = state['rooms'].setdefault(room, {})
    peers[ws] = None
    await ws.send_json({'type': 'ready'})
    try:
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                if message.type == WSMsgType.BINARY:
                    await ws.close(code=1003, message=b'JSON text required')
                continue
            try:
                event = validate_event(json.loads(message.data))
                if peers[ws] is not None and peers[ws] != event['origin']:
                    raise ValueError('Origin cannot change during a connection')
                peers[ws] = event['origin']
            except (ValueError, TypeError, RecursionError):
                await ws.send_json({'type': 'error', 'error': 'Invalid clipboard event'})
                continue
            seen = state['seen']
            now = time.monotonic()
            while seen and (len(seen) >= 4096 or next(iter(seen.values())) < now - 600):
                seen.popitem(last=False)
            key = (room, event['id'])
            if key not in seen:
                seen[key] = now
                targets = [peer for peer, origin in list(peers.items())
                           if peer is not ws and origin != event['origin'] and not peer.closed]
                async def send(peer):
                    try:
                        await asyncio.wait_for(peer.send_json(event), timeout=10)
                    except (ConnectionError, asyncio.TimeoutError, RuntimeError):
                        await peer.close()
                await asyncio.gather(*(send(peer) for peer in targets))
            await ws.send_json({'type': 'ack', 'id': event['id']})
    finally:
        peers.pop(ws, None)
        if not peers:
            state['rooms'].pop(room, None)
    return ws


async def shutdown(app):
    await asyncio.gather(*(ws.close(code=1001, message=b'Server shutdown')
                           for peers in list(app[STATE]['rooms'].values()) for ws in list(peers)))


@web.middleware
async def headers(request, handler):
    response = await handler(request)
    if not isinstance(response, web.WebSocketResponse):
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'no-referrer'})
    return response


def create_app(token):
    if not isinstance(token, str) or len(token) < 32 or any(c.isspace() for c in token):
        raise ValueError('SERVER_TOKEN must contain at least 32 characters without whitespace')
    app = web.Application(client_max_size=MAX_MESSAGE, middlewares=[headers])
    app[STATE] = {'token': token, 'rooms': {}, 'seen': OrderedDict(), 'started': time.monotonic()}
    app.add_routes([web.get('/', landing), web.get('/health', health), web.get('/ws/{room}', relay)])
    app.on_shutdown.append(shutdown)
    return app


LANDING = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Clipboard Sync Relay</title><style>body{font:18px system-ui;max-width:760px;margin:3rem auto;padding:1rem;background:#101820;color:#edf6f9}a{color:#83d9d0}button,input{font:inherit;padding:.6rem}section{margin:2rem 0}code{overflow-wrap:anywhere}label{display:block}#health{padding:1rem;border:1px solid #83d9d0}</style>
<h1>Clipboard Sync Relay</h1><p id="health" role="status">Checking live service health…</p><button id="refresh">Refresh health</button>
<section><h2>Connect your computers</h2><ol><li>Run <code>host.bat --detached</code> on your host. Its health check prints a verified LAN address.</li><li>Open Clipboard Sync on each computer and enable Computer sync in Settings.</li><li>Use the same room and server token on every computer. Copy the token privately from the host’s local <code>.env</code> file; this page never displays it.</li></ol>
<label for="room">Room name (letters, numbers, underscores or hyphens)</label><input id="room" value="home" maxlength="64" pattern="[A-Za-z0-9_-]{1,64}"><p>Your relay URL: <code id="url"></code></p><p>Room names group devices; the shared server token authenticates them. Use a different server for groups that must not share access.</p></section>
<section><h2>Hosting and privacy</h2><p><code>host.bat --logs</code> opens keyboard controls for live status and logs; leaving the view keeps the server running. To use the published image, add <code>--pull</code>. Default hosting builds your local source.</p><p>The relay forwards text, images and files in memory and stores no clipboard history. Each computer keeps its own local Git history. Events are limited to 100,000 text characters or 25 MiB of binary data.</p><p>Use this service on a trusted LAN. For access beyond it, put the service behind HTTPS/WSS or a private VPN. Plain HTTP does not encrypt tokens or clipboard content.</p><p><a href="/health">View health JSON</a>. A healthy relay does not prove desktop clipboard support or that another computer is connected.</p></section>
<script>const room=document.querySelector('#room'),url=document.querySelector('#url');function update(){url.textContent=/^[A-Za-z0-9_-]{1,64}$/.test(room.value)?`${location.protocol==='https:'?'wss':'ws'}://${location.host}/ws/${room.value}`:'Enter a valid room';}room.oninput=update;update();async function health(){const el=document.querySelector('#health');try{const r=await fetch('/health',{cache:'no-store'});const d=await r.json();if(!r.ok||d.status!=='ok')throw Error();el.textContent=`Relay healthy · version ${d.version} · uptime ${d.uptimeSeconds}s`;}catch{el.textContent='Health check failed. Check the host logs and network.';}}document.querySelector('#refresh').onclick=health;health();</script></html>'''
