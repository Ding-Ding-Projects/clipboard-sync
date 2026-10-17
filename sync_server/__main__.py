import os
from aiohttp import web
from .app import create_app

if __name__ == '__main__':
    try:
        app = create_app(os.environ.get('SERVER_TOKEN', ''))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    # Access logs are disabled so room names and request metadata are not retained.
    web.run_app(app, host='0.0.0.0', port=8787, access_log=None)
