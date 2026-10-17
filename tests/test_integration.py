"""Full local transport: two receivers, real relay, independent local Git histories."""
import asyncio
import tempfile
import unittest

from aiohttp import ClientSession, web
from receiver.app import Receiver
from sync_server.app import create_app


class MultiComputerSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_relay_delivers_and_commits_without_echo(self):
        token = 'test-server-token-' + 'a' * 32
        runners = []
        with tempfile.TemporaryDirectory() as temp:
            try:
                async def serve(app):
                    runner = web.AppRunner(app)
                    await runner.setup()
                    runners.append(runner)
                    site = web.TCPSite(runner, '127.0.0.1', 0)
                    await site.start()
                    return 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])

                relay_url = await serve(create_app(token))
                receivers = [Receiver(temp + '/a', True), Receiver(temp + '/b', True)]
                urls = [await serve(receiver.app) for receiver in receivers]
                async with ClientSession() as session:
                    headers = [{'Authorization': 'Bearer ' + r.secrets['admin']} for r in receivers]
                    for url, header in zip(urls, headers):
                        response = await session.post(url + '/api/settings', headers=header, json={
                            'sync': {'enabled': True, 'url': relay_url, 'room': 'integration', 'token': token}})
                        self.assertEqual(response.status, 200)
                    for _ in range(100):
                        if all(r.connected for r in receivers):
                            break
                        await asyncio.sleep(.05)
                    self.assertTrue(all(r.connected for r in receivers))
                    response = await session.post(urls[0] + '/api/transfer', headers=headers[0], json={
                        'type': 'text', 'text': 'Real relay integration test', 'deviceName': 'Test phone'})
                    self.assertFalse((await response.json())['copied'])
                    for _ in range(100):
                        if receivers[1].history.items:
                            break
                        await asyncio.sleep(.05)
                    self.assertEqual(len(receivers[1].history.items), 1)
                    for receiver in receivers:
                        item = receiver.history.items[0]
                        self.assertEqual(receiver.history.payload(item)['text'], 'Real relay integration test')
                        self.assertTrue((receiver.history.path / '.git').is_dir())
                    await asyncio.sleep(.2)
                    self.assertEqual([len(r.history.items) for r in receivers], [1, 1])
            finally:
                for runner in reversed(runners):
                    await runner.cleanup()
