import asyncio
import unittest
from uuid import uuid4
from aiohttp import web, ClientSession, WSServerHandshakeError, WSMsgType
from sync_server.app import create_app, validate_event, MAX_BINARY

TOKEN = 'a' * 64


def event():
    return {'type': 'clipboard', 'id': str(uuid4()), 'origin': str(uuid4()),
            'createdAt': '2026-10-17T12:00:00Z', 'payload': {'type': 'text', 'text': 'Hello'}}


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runner = web.AppRunner(create_app(TOKEN))
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await self.site.start()
        self.url = 'http://127.0.0.1:' + str(self.site._server.sockets[0].getsockname()[1])
        self.client = ClientSession()
        self.sockets = []

    async def asyncTearDown(self):
        for ws in self.sockets:
            await ws.close()
        await self.client.close()
        await self.runner.cleanup()

    async def connect(self, room='home'):
        ws = await self.client.ws_connect(self.url+'/ws/'+room, headers={'Authorization': 'Bearer '+TOKEN})
        self.sockets.append(ws)
        self.assertEqual(await ws.receive_json(), {'type': 'ready'})
        return ws

    async def test_health_and_authentication(self):
        response = await self.client.get(self.url+'/health')
        self.assertEqual((await response.json())['status'], 'ok')
        for headers in ({}, {'Authorization': 'Bearer wrong'}):
            with self.assertRaises(WSServerHandshakeError) as error:
                await self.client.ws_connect(self.url+'/ws/home', headers=headers)
            self.assertEqual(error.exception.status, 401)
        with self.assertRaises(WSServerHandshakeError) as error:
            await self.connect('bad.room')
        self.assertEqual(error.exception.status, 400)
        response = await self.client.get(self.url)
        self.assertNotIn(TOKEN, await response.text())

    async def test_forward_isolate_deduplicate(self):
        sender, peer, isolated = await self.connect(), await self.connect(), await self.connect('other')
        item = event()
        await sender.send_json(item)
        self.assertEqual(await peer.receive_json(), item)
        self.assertEqual((await sender.receive_json())['type'], 'ack')
        await sender.send_json(item)
        self.assertEqual((await sender.receive_json())['id'], item['id'])
        for ws in (peer, isolated):
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(ws.receive_json(), .05)
        # The same id is valid in a distinct room.
        await isolated.send_json(item)
        self.assertEqual((await isolated.receive_json())['type'], 'ack')

    async def test_malformed_and_origin_stability(self):
        sender, peer = await self.connect(), await self.connect()
        for invalid in ('{', '[]', '{"type":"unknown"}'):
            await sender.send_str(invalid)
            self.assertEqual((await sender.receive_json())['type'], 'error')
        item = event()
        await sender.send_json(item)
        await sender.receive_json()
        await peer.receive_json()
        item['id'], item['origin'] = str(uuid4()), str(uuid4())
        await sender.send_json(item)
        self.assertEqual((await sender.receive_json())['type'], 'error')

    async def test_wire_limit_and_binary_rejection(self):
        from unittest.mock import patch
        with patch('sync_server.app.MAX_MESSAGE', 1024):
            ws = await self.connect()
        await ws.send_str('x' * 1025)
        message = await ws.receive()
        self.assertIn(message.type, (WSMsgType.CLOSE, WSMsgType.CLOSED))
        self.assertEqual(ws.close_code, 1009)
        ws = await self.connect()
        await ws.send_bytes(b'not json')
        await ws.receive()
        self.assertEqual(ws.close_code, 1003)

    async def test_origin_loop_suppression(self):
        first, second = await self.connect(), await self.connect()
        item = event()
        await first.send_json(item)
        await first.receive_json()
        await second.receive_json()
        item['id'] = str(uuid4())
        await second.send_json(item)
        await second.receive_json()
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(first.receive_json(), .05)


class ValidationTests(unittest.TestCase):
    def test_limits_and_invalid_payloads(self):
        cases = [None, [], {'type': 'text', 'text': 'a'*100001},
                 {'type': 'text', 'text': 'bad\x00text'},
                 {'type': 'file', 'name': 'a'*201, 'mime': 'text/plain', 'data': 'YQ=='},
                 {'type': 'file', 'name': '../bad', 'mime': 'text/plain', 'data': 'YQ=='},
                 {'type': 'file', 'name': 'CON.txt', 'mime': 'text/plain', 'data': 'YQ=='},
                 {'type': 'file', 'name': 'bad?.txt', 'mime': 'text/plain', 'data': 'YQ=='},
                 {'type': 'file', 'name': 'a', 'mime': 'text/plain', 'data': '%%%='},
                 {'type': 'file', 'name': 'a', 'mime': 'text/plain', 'data': 'a'*(((MAX_BINARY+2)//3)*4+1)}]
        for payload in cases:
            item = event(); item['payload'] = payload
            with self.assertRaises(ValueError): validate_event(item)
        item = event(); item['payload'] = {'type': 'text', 'text': 'a'*100000}
        self.assertEqual(len(validate_event(item)['payload']['text']), 100000)
        item['payload'] = {'type':'file','name':'safe.txt','mime':'text/plain','data':'YQ=='}
        self.assertEqual(validate_event(item)['payload'], item['payload'])

    def test_decoded_binary_limit(self):
        from unittest.mock import patch
        item = event()
        item['payload'] = {'type':'file','name':'a','mime':'text/plain','data':'YWFhYQ=='}
        with patch('sync_server.app.MAX_BINARY', 3):
            with self.assertRaises(ValueError): validate_event(item)
        item['payload']['data'] = 'YWFh'
        with patch('sync_server.app.MAX_BINARY', 3):
            self.assertEqual(validate_event(item)['payload']['data'], 'YWFh')

    def test_identity_and_timestamp(self):
        for key, value in [('id','bad'), ('origin','bad'), ('createdAt','2026-10-17'), ('createdAt',None)]:
            item = event(); item[key] = value
            with self.assertRaises((ValueError, TypeError)): validate_event(item)
        with self.assertRaises(ValueError): create_app('short')


if __name__ == '__main__':
    unittest.main()
