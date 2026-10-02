"""Source-tree and installed application entry point."""

import argparse
import json
import sys
from pathlib import Path

from .adapters import DemoSpeech, DemoText, UnconfiguredSpeech, UnconfiguredText
from .management import dependency_status
from .i18n import _
from .instance import HistoryInUse, history_instance
from .paths import data_directory
from .storage import Store
from .speech import WhisperCppSpeech
from .tasks import TaskQueue
from .text import LlamaCppText


def main():
    parser = argparse.ArgumentParser(description="Local Whisper development preview")
    parser.add_argument("--demo", action="store_true", help="Use clearly labeled simulated engine adapters")
    parser.add_argument("--data-dir", type=Path, help="Override the application data directory")
    parser.add_argument("--check", action="store_true", help="Print dependency status without opening the UI")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(dependency_status(), indent=2))
        return
    try:
        import tkinter as tk
    except (ImportError, OSError) as error:
        print(_("Unable to load Tkinter: {error}\n"
                "Install Tk support for your Python installation: the tk system package on Arch/Omarchy, "
                "python3-tk on Debian, or a Python installation with Tk on Windows/macOS.\n"
                "See the README troubleshooting instructions.").format(error=error), file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except tk.TclError as error:
        print(_("Unable to open the desktop window: {error}\n"
                "Run this command from a graphical desktop session and check your Tk installation "
                "with python -m tkinter.").format(error=error), file=sys.stderr)
        return 1
    from .ui import Application
    try:
        with history_instance((args.data_dir or data_directory()) / "history.sqlite3"):
            tasks = None
            app = None
            try:
                store = Store((args.data_dir or data_directory()) / "history.sqlite3")
                config = store.speech_config()
                speech = DemoSpeech() if args.demo else WhisperCppSpeech(config) if config else UnconfiguredSpeech()
                text_config = store.text_config()
                text = DemoText() if args.demo else LlamaCppText(text_config) if text_config else UnconfiguredText()
                tasks = TaskQueue(store, speech, text)
                app = Application(root, store, tasks, args.demo)
                root.mainloop()
            finally:
                if app:
                    app.close()
                    app.playback.join(timeout=None)
                if tasks:
                    tasks.close()
                    # Keep ownership until no worker can write to this history.
                    tasks.join(timeout=None)
    except HistoryInUse as error:
        from tkinter import messagebox
        messagebox.showerror(_("History already open"), _(str(error)), parent=root)
        return 1
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass  # The window may already have been closed through Application.


if __name__ == "__main__":
    sys.exit(main())
