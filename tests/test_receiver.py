import asyncio
import base64
import tempfile
import unittest
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from receiver.app import Receiver, validate

class ReceiverTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.receiver=Receiver(self.temp.name,headless=True)
        self.client=TestClient(TestServer(self.receiver.app)); await self.client.start_server()
        self.admin={'Authorization':'Bearer '+self.receiver.secrets['admin']}
        self.mobile={'Authorization':'Bearer '+self.receiver.secrets['mobile']}
    async def asyncTearDown(self):
        await self.client.close(); self.temp.cleanup()
    async def test_auth_transfer_restore_history(self):
        self.assertEqual((await self.client.get('/api/status')).status,401)
        self.assertEqual((await self.client.get('/api/status',headers=self.mobile)).status,401)
        response=await self.client.post('/api/transfer',headers=self.mobile,json={'type':'text','text':'hello'})
        result=await response.json(); self.assertFalse(result['copied']); self.assertEqual(response.status,200)
        detail=await (await self.client.get('/api/history/'+result['id']+'/detail',headers=self.admin)).json()
        self.assertEqual(detail['text'],'hello')
        restored=await (await self.client.post('/api/history/'+result['id']+'/restore',headers=self.admin)).json()
        self.assertFalse(restored['copied']); self.assertEqual(len(self.receiver.history.items),1)
        self.assertTrue((Path(self.temp.name)/'history'/'.git').is_dir())
    async def test_pair_origin_and_clear(self):
        response=await self.client.post('/api/transfer',headers=self.mobile|{'Origin':'https://evil.invalid'},json={'type':'text','text':'x'})
        self.assertEqual(response.status,403)
        await self.client.post('/api/pair/reset',headers=self.admin)
        self.assertEqual((await self.client.get('/api/phone',headers=self.mobile)).status,401)
        self.assertEqual((await self.client.post('/api/history/clear',headers=self.admin,json={})).status,400)
    async def test_binary_roundtrip_and_restart(self):
        response=await self.client.post('/api/transfer',headers=self.admin,json={'type':'file','name':'a.bin','data':base64.b64encode(b'abc').decode()})
        ident=(await response.json())['id']
        download=await self.client.get('/api/history/'+ident+'/file',headers=self.admin)
        self.assertEqual(await download.read(),b'abc')
        from receiver.app import History
        self.assertEqual(len(History(Path(self.temp.name)/'history').items),1)
        await self.client.post('/api/history/clear',headers=self.admin,json={'confirm':True})
        self.assertEqual(len(History(Path(self.temp.name)/'history').items),0)
    async def test_relay_receive_without_echo(self):
        from aiohttp import web
        import uuid
        received=asyncio.Event()
        messages=[]
        async def relay(request):
            self.assertEqual(request.headers['Authorization'],'Bearer test-relay-token')
            ws=web.WebSocketResponse(); await ws.prepare(request)
            await ws.send_json({'type':'clipboard','id':str(uuid.uuid4()),'origin':str(uuid.uuid4()),'createdAt':'2026-01-01T00:00:00Z','payload':{'type':'text','text':'remote content'}})
            received.set()
            async for msg in ws: messages.append(msg.data)
            return ws
        app=web.Application(); app.router.add_get('/ws/default',relay)
        server=TestServer(app); await server.start_server()
        try:
            self.receiver.settings['sync']={'enabled':True,'url':str(server.make_url('/')).rstrip('/'),'room':'default'}
            self.receiver.secrets['relay']='test-relay-token'
            await asyncio.wait_for(received.wait(),3)
            for _ in range(50):
                if self.receiver.history.items: break
                await asyncio.sleep(.02)
            self.assertEqual(self.receiver.history.payload(self.receiver.history.items[0])['text'],'remote content')
            self.assertEqual(messages,[])
            self.assertTrue(self.receiver.connected)
        finally:
            if self.receiver.ws: await self.receiver.ws.close()
            await server.close()

    async def test_watcher_capture_and_write_echo_deduplication(self):
        class FakeClipboard:
            available=True
            seq=0
            payload={'type':'text','text':'local edit'}
            def sequence(self): return self.seq
            def read(self): return [self.payload]
            def write(self,payload,path=None):
                self.payload=payload; self.seq+=1; return True
        fake=FakeClipboard(); self.receiver.clipboard=fake
        result=await (await self.client.post('/api/transfer',headers=self.admin,json={'type':'text','text':'phone edit'})).json()
        self.assertTrue(result['copied'])
        await asyncio.sleep(.5)
        self.assertEqual(len(self.receiver.history.items),1)
        fake.payload={'type':'text','text':'local edit'}; fake.seq+=1
        await asyncio.sleep(.5)
        self.assertEqual(len(self.receiver.history.items),2)
        self.assertEqual(self.receiver.history.items[0]['source'],'This computer')
        fake.seq+=1
        await asyncio.sleep(.5)
        self.assertEqual(len(self.receiver.history.items),2)

    async def test_settings_validation_is_transactional(self):
        import copy
        original=copy.deepcopy(self.receiver.settings)
        for url in ('http://','https://user:pass@host','https://host/#secret','https://host/\npath','https://host:bad'):
            response=await self.client.post('/api/settings',headers=self.admin,json={'paused':True,'setupComplete':True,'sync':{'url':url}})
            self.assertEqual(response.status,400)
            self.assertEqual(self.receiver.settings,original)
        response=await self.client.post('/api/transfer',headers=self.admin,json=[])
        self.assertEqual(response.status,400)
    async def test_same_bytes_different_filename_retained(self):
        for name in ('one.txt','two.txt'):
            await self.client.post('/api/transfer',headers=self.admin,json={'type':'file','name':name,'data':'YQ=='})
        self.assertEqual(len(self.receiver.history.items),2)
    async def test_unsupported_capture_is_visible(self):
        class UnsupportedClipboard:
            available=True
            def sequence(self): return 1
            def read(self): return []
        self.receiver.clipboard=UnsupportedClipboard()
        await asyncio.sleep(.5)
        status=await (await self.client.get('/api/status',headers=self.admin)).json()
        self.assertIn('no supported',status['lastCaptureError'])
        self.assertTrue(status['captureWarnings'])
    async def test_pause_suppresses_restore_broadcast(self):
        class Socket:
            closed=False
            messages=[]
            async def send_json(self,event): self.messages.append(event)
        ws=Socket(); self.receiver.ws=ws
        self.receiver.settings['paused']=True
        await self.receiver.accept({'type':'text','text':'restore'},'Restore')
        self.assertEqual(ws.messages,[])
        self.receiver.ws=None

    async def test_validation(self):
        for raw in ({'type':'text','text':'x'*100001},{'type':'file','name':'../x','data':''},{'type':'file','data':'!!'}):
            with self.assertRaises(ValueError): validate(raw)

if __name__=='__main__': unittest.main()
