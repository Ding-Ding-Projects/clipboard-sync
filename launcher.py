"""Packaged entry point. Tools are private to this process, never added to user PATH."""
import os
import runpy
import sys
from pathlib import Path

from receiver.squirrel import handle_squirrel_events

if handle_squirrel_events():
    raise SystemExit(0)
# The first interactive launch is a regular app launch, not an installer hook.
sys.argv = [arg for arg in sys.argv if arg != "--squirrel-firstrun"]

bundle = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
portable_git = bundle / "tools" / "git" / "cmd"
if portable_git.is_dir():
    os.environ["PATH"] = str(portable_git) + os.pathsep + os.environ.get("PATH", "")
runpy.run_module("receiver", run_name="__main__")
