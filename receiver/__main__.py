import argparse
import asyncio
import webbrowser
from .squirrel import handle_squirrel_events
from . import __version__

def main():
    if handle_squirrel_events():
        return
    from aiohttp import web
    from .app import Receiver
    parser=argparse.ArgumentParser(description='Clipboard Sync Windows receiver')
    parser.add_argument('--squirrel-firstrun',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--version',action='version',version=__version__)
    parser.add_argument('--headless',action='store_true',help='Transport testing only; never writes a native clipboard')
    parser.add_argument('--port',type=int,default=5333)
    parser.add_argument('--host',default='0.0.0.0')
    parser.add_argument('--data-dir')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    receiver=Receiver(args.data_dir,args.headless,args.port)
    async def run():
        runner=web.AppRunner(receiver.app,access_log=None)
        await runner.setup()
        try:
            site=web.TCPSite(runner,args.host,args.port)
            await site.start()
            if not args.no_browser and not args.headless:
                webbrowser.open(f'http://127.0.0.1:{args.port}/#admin='+receiver.secrets['admin'])
            await asyncio.Event().wait()
        finally: await runner.cleanup()
    try: asyncio.run(run())
    except KeyboardInterrupt: pass

if __name__=='__main__': main()
