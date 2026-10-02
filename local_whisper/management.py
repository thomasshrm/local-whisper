"""Read-only dependency status; no installers, downloads or model catalog yet."""

import importlib
import sqlite3
import sys

HF_TOKEN_URL = "https://huggingface.co/settings/tokens"


def tkinter_status() -> str:
    """Check native library loading without requiring a graphical display."""
    try:
        importlib.import_module("tkinter")
    except (ImportError, OSError) as error:
        return f"unavailable: {error}"
    return "available"


def dependency_status() -> dict[str, str]:
    try:
        module = importlib.import_module("sounddevice")
        playback = f"sounddevice {module.__version__} / PortAudio available"
    except (ImportError, OSError):
        playback = "unavailable: install the playback extra and PortAudio"
    return {
        "Python": sys.version.split()[0],
        "Tkinter": tkinter_status(),
        "SQLite": sqlite3.sqlite_version,
        "Speech engine": "whisper.cpp adapter available; select a local executable and model in Models",
        "Local LLM (optional)": "disabled unless configured; raw transcription does not require it",
        "WAV playback": playback,
        "Microphone": "not integrated",
    }
