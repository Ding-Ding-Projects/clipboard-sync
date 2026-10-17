import asyncio
import base64
import binascii
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time
import uuid
from urllib.parse import urlsplit, quote
from aiohttp import web, ClientSession, WSMsgType
from PIL import Image
from .native import Clipboard, check_image_size

MAX_BYTES=25*1024*1024
VERSION='0.1.0'

def now(): return datetime.now(timezone.utc).isoformat()
def safe_name(value):
    name=str(value or 'clipboard.bin')
    if len(name)>200 or name in ('.','..') or any(c in name for c in '/\\\x00<>:"|?*') or any(ord(c)<32 for c in name):
        raise ValueError('Invalid filename')
    if name.endswith((' ','.')) or name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}: raise ValueError('Invalid filename')
    return name

def validate(raw):
    if not isinstance(raw,dict): raise ValueError('Content must be a JSON object')
    kind=raw.get('type')
    if kind=='text':
        text=raw.get('text')
        if not isinstance(text,str) or len(text)>100000: raise ValueError('Text must contain at most 100,000 characters')
        if '\x00' in text: raise ValueError('Text cannot contain NUL characters')
        text.encode('utf-8')
        return {'type':'text','text':text}
    if kind not in ('image','file'): raise ValueError('Unsupported content type')
    name=safe_name(raw.get('name'))
    try: data=raw.get('_bytes') if '_bytes' in raw else base64.b64decode(raw.get('data',''),validate=True)
    except (ValueError,TypeError,binascii.Error): raise ValueError('Invalid base64 data')
    if not isinstance(data,bytes) or len(data)>MAX_BYTES: raise ValueError('File exceeds 25 MiB')
    mime=str(raw.get('mime','application/octet-stream'))[:200]
    if kind=='image':
        try:
            with Image.open(io.BytesIO(data)) as im:
                check_image_size(*im.size)
                im.verify()
        except Exception: kind='file'
    return {'type':kind,'name':name,'mime':mime,'_bytes':data}

class History:
    def __init__(self,path):
        self.path=Path(path); self.path.mkdir(parents=True,exist_ok=True)
        self.git('init','--quiet'); self.git('config','user.name','Clipboard Sync'); self.git('config','user.email','clipboard@localhost')
        self.git('config','core.autocrlf','false'); self.git('config','commit.gpgsign','false')
        self.items=[]
        for p in self.path.glob('*/entry.json'):
            self.items.append(json.loads(p.read_text('utf-8')))
        self.items.sort(key=lambda x:x['createdAt'],reverse=True)
    def git(self,*args):
        try: subprocess.run(['git','-C',str(self.path),*args],check=True,capture_output=True,timeout=30)
        except FileNotFoundError: raise RuntimeError('Git is required for durable local clipboard history')
        except subprocess.CalledProcessError as e: raise RuntimeError('Local Git history update failed') from e
    def add(self,payload,source):
        data=payload['text'].encode('utf-8') if payload['type']=='text' else payload['_bytes']
        identity=json.dumps([payload['type'],payload.get('name',''),payload.get('mime','')],ensure_ascii=False).encode()
        digest=hashlib.sha256(identity+b'\0'+data).hexdigest()
        if self.items and self.items[0]['digest']==digest: return self.items[0],False
        ident=str(uuid.uuid4()); folder=self.path/ident; folder.mkdir()
        item={'id':ident,'type':payload['type'],'name':payload.get('name','Text'), 'mime':payload.get('mime','text/plain'), 'preview':payload.get('text',payload.get('name',''))[:200], 'size':len(data),'createdAt':now(),'source':str(source)[:100],'status':'saved','digest':digest}
        (folder/'content').write_bytes(data); (folder/'entry.json').write_text(json.dumps(item,ensure_ascii=False),encoding='utf-8')
        self.git('add','--',ident)
        try: self.git('commit','--quiet','-m','Save clipboard entry '+ident)
        except Exception:
            self.git('reset','--',ident)
            import shutil; shutil.rmtree(folder); raise
        self.items.insert(0,item); return item,True
    def get(self,ident):
        return next((x for x in self.items if x['id']==ident),None)
    def payload(self,item):
        data=(self.path/item['id']/'content').read_bytes()
        return {'type':'text','text':data.decode('utf-8')} if item['type']=='text' else {'type':item['type'],'name':item['name'],'mime':item['mime'],'_bytes':data}
    def clear(self):
        # Git commits deliberately retain prior content until repository retention is managed.
        import shutil
        for item in self.items: shutil.rmtree(self.path/item['id'])
        self.git('add','-A')
        if self.items: self.git('commit','--quiet','-m','Clear visible clipboard history')
        self.items=[]

class Receiver:
    def __init__(self,data_dir=None,headless=False,port=5333,dist=None):
        self.root=Path(data_dir or Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local/share'))/'ClipboardSync')
        self.root.mkdir(parents=True,exist_ok=True)
        if os.name=='nt':
            try:
                account=next(csv.reader(subprocess.check_output(['whoami','/user','/fo','csv','/nh'],text=True).strip().splitlines()))
                subprocess.run(['icacls',str(self.root),'/inheritance:r','/grant:r','*'+account[1]+':(OI)(CI)F'],check=True,capture_output=True)
            except Exception as exc: raise RuntimeError('Cannot restrict clipboard data to the current Windows user') from exc
        self.config_path=self.root/'settings.json'; self.secret_path=self.root/'secrets.json'
        self.settings=json.loads(self.config_path.read_text()) if self.config_path.exists() else {'paused':False,'setupComplete':False,'sync':{'enabled':False,'url':'','room':'default'}}
        self.secrets=json.loads(self.secret_path.read_text()) if self.secret_path.exists() else {'admin':secrets.token_urlsafe(32),'mobile':secrets.token_urlsafe(32),'device':str(uuid.uuid4()),'relay':''}
        self.save(); self.clipboard=Clipboard(headless); self.history=History(self.root/'history'); self.lock=asyncio.Lock()
        self.port=port; self.phone_seen=0; self.connected=False; self.error=''; self.capture_error=''; self.ws=None; self.last_seq=self.clipboard.sequence(); self.seen=set(); self.tasks=[]
        self.dist=Path(dist) if dist else Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))/'dist'
        self.app=web.Application(client_max_size=36*1024*1024,middlewares=[self.middleware])
        self.app.router.add_route('*','/api/{tail:.*}',self.api)
        self.app.router.add_get('/{tail:.*}',self.static)
        self.app.on_startup.append(self.start); self.app.on_cleanup.append(self.stop)
    def save(self):
        for path,data in ((self.config_path,self.settings),(self.secret_path,self.secrets)):
            temp=path.with_suffix('.tmp'); temp.write_text(json.dumps(data),encoding='utf-8'); temp.chmod(0o600); temp.replace(path)
    @web.middleware
    async def middleware(self,request,handler):
        try:
            if request.path.startswith('/api/'):
                token=request.headers.get('Authorization','').removeprefix('Bearer ')
                admin=secrets.compare_digest(token,self.secrets['admin'])
                mobile=secrets.compare_digest(token,self.secrets['mobile'])
                if not admin and not (mobile and request.path in ('/api/transfer','/api/phone')): raise web.HTTPUnauthorized(reason='Authentication required')
                if request.method not in ('GET','HEAD'):
                    origin=request.headers.get('Origin')
                    if origin and origin not in ('http://'+request.host,'https://'+request.host): raise web.HTTPForbidden(reason='Foreign origin is not allowed')
            response=await handler(request)
        except web.HTTPException as e: response=web.json_response({'error':e.reason},status=e.status)
        except (ValueError,KeyError,TypeError) as e: response=web.json_response({'error':str(e)},status=400)
        except Exception:
            response=web.json_response({'error':'Operation failed; check local Git and clipboard availability'},status=500)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'"
        return response
    def status(self,request):
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s: s.connect(('192.0.2.1',80)); host=s.getsockname()[0]
        except OSError: host='127.0.0.1'
        return {'deviceName':self.settings.get('deviceName',socket.gethostname()),'platform':sys.platform,'clipboardAvailable':self.clipboard.available,'phoneConnected':time.time()-self.phone_seen<60,'paused':self.settings['paused'],'pairUrl':f'http://{host}:{self.port}/send#token='+self.secrets['mobile'],'receivedToday':sum(x['createdAt'][:10]==now()[:10] for x in self.history.items),'historyCount':len(self.history.items),'lastCaptureError':self.capture_error,'captureWarnings':[self.capture_error] if self.capture_error else [],'sync':{**self.settings['sync'],'connected':self.connected,'error':self.error},'setupComplete':self.settings['setupComplete'],'version':VERSION}
    async def accept(self,payload,source,broadcast=True,copy=True):
        async with self.lock:
            item,new=await asyncio.to_thread(self.history.add,payload,source)
            copied=False
            if copy:
                path=None
                if payload['type']=='file':
                    folder=self.root/'files'/item['id']; folder.mkdir(parents=True,exist_ok=True); path=folder/payload['name']; path.write_bytes(payload['_bytes'])
                copied,written_sequence=await asyncio.to_thread(self.clipboard.write,payload,path)
                if copied: self.last_seq=written_sequence
            if new and broadcast and not self.settings['paused'] and self.ws and not self.ws.closed:
                wire={k:v for k,v in payload.items() if k!='_bytes'}
                if '_bytes' in payload: wire['data']=base64.b64encode(payload['_bytes']).decode()
                try: await self.ws.send_json({'type':'clipboard','id':str(uuid.uuid4()),'origin':self.secrets['device'],'createdAt':now(),'payload':wire})
                except Exception: self.error='Relay disconnected; content saved locally'
            return {'ok':True,'id':item['id'],'copied':copied,'status':'copied' if copied else 'saved locally; native clipboard unavailable'}
    async def api(self,r):
        tail=r.match_info['tail']; method=r.method
        if tail=='status' and method=='GET': return web.json_response(self.status(r))
        if tail=='phone' and method=='GET':
            self.phone_seen=time.time(); return web.json_response({k:v for k,v in self.status(r).items() if k in ('deviceName','clipboardAvailable','paused','version')}|{'maxFileBytes':MAX_BYTES})
        if tail=='transfer' and method=='POST':
            if self.settings['paused']: raise web.HTTPConflict(reason='Clipboard synchronization is paused')
            raw=await r.json(); self.phone_seen=time.time(); return web.json_response(await self.accept(validate(raw),str(raw.get('deviceName','Phone'))))
        if tail=='history' and method=='GET':
            kind=r.query.get('type','all'); q=r.query.get('q','').casefold()
            items=[x for x in self.history.items if (kind=='all' or x['type']==kind) and (not q or q in (x['name']+' '+x['preview']).casefold() or (x['type']=='text' and q in (await asyncio.to_thread((self.history.path/x['id']/'content').read_text,encoding='utf-8')).casefold()))]
            return web.json_response({'items':items[:100],'total':len(items)})
        if tail=='settings' and method=='POST':
            raw=await r.json()
            if not isinstance(raw,dict): raise ValueError('Settings must be a JSON object')
            candidate=json.loads(json.dumps(self.settings)); candidate_secrets=dict(self.secrets)
            if 'deviceName' in raw:
                label=raw['deviceName']
                if not isinstance(label,str) or not 1<=len(label)<=80 or not label.isprintable() or not label.strip(): raise ValueError('Device name must contain 1 to 80 printable characters')
                candidate['deviceName']=label
            for k in ('paused','setupComplete'):
                if k in raw:
                    if not isinstance(raw[k],bool): raise ValueError(k+' must be boolean')
                    candidate[k]=raw[k]
            if 'sync' in raw:
                sync=raw['sync']
                if not isinstance(sync,dict): raise ValueError('Sync settings must be a JSON object')
                current=candidate['sync']
                for k in ('enabled','url','room'):
                    if k in sync: current[k]=sync[k]
                if not isinstance(current['enabled'],bool): raise ValueError('Sync enabled must be boolean')
                url=current['url']
                if not isinstance(url,str): raise ValueError('Invalid relay URL')
                if url:
                    parsed=urlsplit(url)
                    if (parsed.scheme not in ('http','https','ws','wss') or not parsed.hostname or not parsed.netloc or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or any(c.isspace() or ord(c)<32 for c in url)):
                        raise ValueError('Invalid relay URL')
                    try: parsed.port
                    except ValueError: raise ValueError('Invalid relay port')
                if not isinstance(current['room'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',current['room']): raise ValueError('Invalid room')
                if 'token' in sync and not isinstance(sync['token'],str): raise ValueError('Invalid relay token')
                if sync.get('token'): candidate_secrets['relay']=sync['token']
            old_settings,old_secrets=self.settings,self.secrets
            self.settings,self.secrets=candidate,candidate_secrets
            try: self.save()
            except Exception:
                self.settings,self.secrets=old_settings,old_secrets
                raise
            if 'sync' in raw and self.ws: await self.ws.close()
            return web.json_response(self.status(r))
        if tail=='pair/reset' and method=='POST':
            self.secrets['mobile']=secrets.token_urlsafe(32); self.phone_seen=0; self.save(); return web.json_response(self.status(r))
        if tail=='history/clear' and method=='POST':
            confirmation=await r.json()
            if not isinstance(confirmation,dict) or confirmation.get('confirm') is not True: raise ValueError('Explicit confirmation required')
            async with self.lock: await asyncio.to_thread(self.history.clear)
            return web.json_response({'ok':True,'message':'Visible history cleared. Previous content remains in local Git commits.'})
        match=re.fullmatch(r'history/([0-9a-f-]{36})/(restore|file|detail)',tail)
        if match:
            item=self.history.get(match[1])
            if not item: raise web.HTTPNotFound(reason='History entry not found')
            action=match[2]; payload=self.history.payload(item)
            if action=='restore' and method=='POST': return web.json_response(await self.accept(payload,'Restore'))
            if action=='detail' and method=='GET': return web.json_response(item|({'text':payload['text']} if item['type']=='text' else {}))
            if action=='file' and method=='GET':
                response=web.FileResponse(self.history.path/item['id']/'content'); response.headers['Content-Disposition']="attachment; filename*=UTF-8''"+quote(item['name'],safe=''); return response
        raise web.HTTPNotFound(reason='Endpoint not found')
    async def static(self,r):
        target=(self.dist/r.match_info['tail']).resolve()
        if not target.is_relative_to(self.dist.resolve()): raise web.HTTPNotFound()
        if not target.is_file(): target=self.dist/'index.html'
        if not target.is_file(): return web.Response(text='Clipboard Sync receiver is running. Build the local web interface to continue.',content_type='text/plain')
        return web.FileResponse(target)
    async def start(self,app):
        self.tasks=[asyncio.create_task(self.watch()),asyncio.create_task(self.relay())]
    async def stop(self,app):
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
    async def watch(self):
        while True:
            await asyncio.sleep(.4)
            if self.settings['paused'] or not self.clipboard.available: continue
            seq=self.clipboard.sequence()
            if seq==self.last_seq: continue
            try:
                async with self.lock:
                    payloads=await asyncio.to_thread(self.clipboard.read); self.last_seq=seq
                warnings=[]
                if not payloads: warnings.append('This clipboard change has no supported text, bitmap, or file-drop content.')
                for raw in payloads:
                    if '_path' in raw:
                        p=Path(raw['_path'])
                        if not p.is_file():
                            warnings.append('A directory or unavailable file could not be captured.'); continue
                        if p.stat().st_size>MAX_BYTES:
                            warnings.append('A clipboard file larger than 25 MiB could not be captured.'); continue
                        raw={'type':'file','name':p.name,'_bytes':await asyncio.to_thread(p.read_bytes)}
                    await self.accept(validate(raw),'This computer',copy=False)
                self.capture_error=' '.join(warnings)
            except Exception as exc:
                self.capture_error='Could not capture this clipboard change: '+(str(exc) if isinstance(exc,ValueError) else 'clipboard access or local history failed')
    async def relay(self):
        delay=1
        async with ClientSession() as session:
            while True:
                sync=self.settings['sync']
                if not sync['enabled'] or not sync['url']:
                    await asyncio.sleep(1); continue
                try:
                    url=sync['url'].rstrip('/')+'/ws/'+sync['room']
                    async with session.ws_connect(url,headers={'Authorization':'Bearer '+self.secrets['relay']},max_msg_size=36*1024*1024,heartbeat=20) as ws:
                        self.ws=ws; self.connected=True; self.error=''; delay=1
                        async for msg in ws:
                            if msg.type!=WSMsgType.TEXT: continue
                            try:
                                event=json.loads(msg.data)
                                if not isinstance(event,dict): raise ValueError('Invalid relay event')
                                if event.get('type')!='clipboard': continue
                                uuid.UUID(event['id']); uuid.UUID(event['origin'])
                                if event['origin']==self.secrets['device'] or event['id'] in self.seen or self.settings['paused']: continue
                                payload=validate(event['payload'])
                            except (ValueError,TypeError,KeyError,AttributeError):
                                self.error='An invalid relay event was ignored; connection remains active'
                                continue
                            await self.accept(payload,'Synced computer',broadcast=False)
                            self.seen.add(event['id'])
                            if len(self.seen)>2048: self.seen={event['id']}
                except asyncio.CancelledError: raise
                except Exception: self.error='Relay unavailable; local clipboard history remains active'
                finally: self.connected=False; self.ws=None
                await asyncio.sleep(delay); delay=min(delay*2,30)
