"""Platform directories; importing this module creates no directories."""

import os
import sys
from pathlib import Path


def data_directory() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "LocalWhisper"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LocalWhisper"
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    if not base.is_absolute():
        base = Path.home() / ".local" / "share"
    return base / "local-whisper"
