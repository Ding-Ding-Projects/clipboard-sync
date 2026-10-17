"""Clipboard Sync desktop receiver."""
from pathlib import Path

# Packaging supplies the same version used by the installer and PE metadata.
try:
    __version__ = Path(__file__).with_name("_build_version.txt").read_text(encoding="utf-8-sig").strip()
except FileNotFoundError:
    __version__ = "0.1.0"
