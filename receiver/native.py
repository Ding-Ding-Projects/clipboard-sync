"""Windows clipboard access, serialized across readers and writers."""
import ctypes
from ctypes import wintypes
import io
import os
import struct
import threading
import time
from PIL import Image

class Clipboard:
    def __init__(self, headless=False):
        self.available = os.name == 'nt' and not headless
        self.lock = threading.RLock()
        if not self.available:
            return
        self.u = ctypes.WinDLL('user32', use_last_error=True)
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.s = ctypes.WinDLL('shell32', use_last_error=True)
        for name, args, result in [
            ('CreateWindowExW', [wintypes.DWORD,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.HWND,wintypes.HMENU,wintypes.HINSTANCE,ctypes.c_void_p], wintypes.HWND),
            ('DestroyWindow',[wintypes.HWND],wintypes.BOOL),
            ('OpenClipboard', [wintypes.HWND], wintypes.BOOL),
            ('CloseClipboard', [], wintypes.BOOL), ('EmptyClipboard', [], wintypes.BOOL),
            ('GetClipboardData', [wintypes.UINT], wintypes.HANDLE),
            ('SetClipboardData', [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE),
            ('IsClipboardFormatAvailable', [wintypes.UINT], wintypes.BOOL),
            ('GetClipboardSequenceNumber', [], wintypes.DWORD)]:
            f = getattr(self.u, name); f.argtypes = args; f.restype = result
        for name, args, result in [('GlobalAlloc', [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL),
            ('GlobalLock', [wintypes.HGLOBAL], ctypes.c_void_p),
            ('GlobalUnlock', [wintypes.HGLOBAL], wintypes.BOOL),
            ('GlobalSize', [wintypes.HGLOBAL], ctypes.c_size_t),
            ('GlobalFree', [wintypes.HGLOBAL], wintypes.HGLOBAL)]:
            f = getattr(self.k, name); f.argtypes=args; f.restype=result
        self.s.DragQueryFileW.argtypes=[wintypes.HANDLE,wintypes.UINT,wintypes.LPWSTR,wintypes.UINT]
        self.s.DragQueryFileW.restype=wintypes.UINT

    def sequence(self):
        return self.u.GetClipboardSequenceNumber() if self.available else 0

    def _open(self):
        self.window=self.u.CreateWindowExW(0,'STATIC','Clipboard Sync',0,0,0,0,0,None,None,None,None)
        if not self.window: raise OSError('Cannot create clipboard owner window')
        for _ in range(20):
            if self.u.OpenClipboard(self.window): return
            time.sleep(.025)
        self.u.DestroyWindow(self.window)
        raise OSError('Windows clipboard is busy; try again')

    def write(self, payload, path=None):
        if not self.available: return False
        if payload['type'] == 'text':
            fmt, data = 13, (payload['text']+'\0').encode('utf-16-le')
        elif payload['type'] == 'image':
            with Image.open(io.BytesIO(payload['_bytes'])) as im:
                buf=io.BytesIO(); im.convert('RGB').save(buf, 'BMP'); data=buf.getvalue()[14:]
            fmt=8
        else:
            fmt=15; data=struct.pack('<IiiII',20,0,0,0,1)+(str(path)+'\0\0').encode('utf-16-le')
        with self.lock:
            self._open()
            handle=None
            try:
                handle=self.k.GlobalAlloc(0x42,len(data))
                if not handle: raise OSError('Clipboard memory allocation failed')
                ptr=self.k.GlobalLock(handle)
                if not ptr: raise OSError('Clipboard memory lock failed')
                ctypes.memmove(ptr,data,len(data)); self.k.GlobalUnlock(handle)
                if not self.u.EmptyClipboard() or not self.u.SetClipboardData(fmt,handle):
                    raise OSError('Windows rejected clipboard data')
                handle=None
            finally:
                if handle: self.k.GlobalFree(handle)
                self.u.CloseClipboard(); self.u.DestroyWindow(self.window)
        return True

    def read(self):
        if not self.available: return []
        with self.lock:
            self._open()
            try:
                if self.u.IsClipboardFormatAvailable(15):
                    h=self.u.GetClipboardData(15); paths=[]
                    for i in range(self.s.DragQueryFileW(h,0xffffffff,None,0)):
                        n=self.s.DragQueryFileW(h,i,None,0); buf=ctypes.create_unicode_buffer(n+1)
                        self.s.DragQueryFileW(h,i,buf,n+1); paths.append(buf.value)
                    return [{'type':'file','_path':p} for p in paths]
                for fmt in (13,8,17):
                    if not self.u.IsClipboardFormatAvailable(fmt): continue
                    h=self.u.GetClipboardData(fmt); ptr=self.k.GlobalLock(h)
                    if not ptr: continue
                    try:
                        if fmt==13: return [{'type':'text','text':ctypes.wstring_at(ptr)}]
                        dib=ctypes.string_at(ptr,self.k.GlobalSize(h))
                    finally: self.k.GlobalUnlock(h)
                    header=struct.unpack_from('<I',dib)[0]
                    bits=struct.unpack_from('<H',dib,14)[0]
                    colors=struct.unpack_from('<I',dib,32)[0] if header>=40 else 0
                    offset=14+header+(colors or (1<<bits if bits<=8 else 0))*4
                    if header==40 and struct.unpack_from('<I',dib,16)[0]==3: offset+=12
                    bmp=b'BM'+struct.pack('<IHHI',len(dib)+14,0,0,offset)+dib
                    with Image.open(io.BytesIO(bmp)) as im:
                        out=io.BytesIO(); im.save(out,'PNG')
                    return [{'type':'image','name':'Clipboard.png','mime':'image/png','_bytes':out.getvalue()}]
                return []
            finally: self.u.CloseClipboard(); self.u.DestroyWindow(self.window)
