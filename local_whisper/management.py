"""Read-only dependency status; no installers, downloads or model catalog yet."""

import importlib.util
import sqlite3
import sys

HF_TOKEN_URL = "https://huggingface.co/settings/tokens"


def dependency_status() -> dict[str, str]:
    return {
        "Python": sys.version.split()[0],
        "Tkinter": "available" if importlib.util.find_spec("tkinter") else "missing",
        "SQLite": sqlite3.sqlite_version,
        "Speech engine": "not configured",
        "Local LLM": "not configured",
        "Microphone / playback": "not integrated",
    }
