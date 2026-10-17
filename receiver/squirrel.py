"""Squirrel.Windows lifecycle hooks; no application or network initialization."""
import subprocess
import sys
from pathlib import Path


_LIFECYCLE = {
    "--squirrel-install", "--squirrel-updated", "--squirrel-uninstall", "--squirrel-obsolete"
}


def handle_squirrel_events(argv=None, executable=None):
    """Return True when this process must exit after handling an installer event."""
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] not in _LIFECYCLE:
        return False
    event = args[0]
    if event == "--squirrel-obsolete":
        return True
    app_exe = Path(sys.executable if executable is None else executable).resolve()
    updater = app_exe.parent.parent / "Update.exe"
    if not updater.is_file():
        raise RuntimeError("Squirrel lifecycle event requires the installed Update.exe")
    action = "--removeShortcut" if event == "--squirrel-uninstall" else "--createShortcut"
    subprocess.run(
        [str(updater), action, app_exe.name, "--shortcut-locations", "StartMenu,Desktop"],
        check=True, timeout=10,
    )
    return True
