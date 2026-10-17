"""Standalone offline documentation companion; serves bundled public docs only."""
import functools
import http.server
from pathlib import Path
import sys
import threading
import webbrowser

root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "docs"
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
    url = f"http://127.0.0.1:{server.server_port}/"
    threading.Timer(.3, webbrowser.open, args=(url,)).start()
    print("Clipboard Sync offline guide. Close this window to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
