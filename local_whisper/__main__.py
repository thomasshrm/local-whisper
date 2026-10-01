"""Source-tree and installed application entry point."""

import argparse
import json
from pathlib import Path

from .adapters import DemoSpeech, DemoText, UnconfiguredSpeech, UnconfiguredText
from .management import dependency_status
from .paths import data_directory
from .storage import Store
from .tasks import TaskQueue


def main():
    parser = argparse.ArgumentParser(description="Local Whisper development preview")
    parser.add_argument("--demo", action="store_true", help="Use clearly labeled simulated engine adapters")
    parser.add_argument("--data-dir", type=Path, help="Override the application data directory")
    parser.add_argument("--check", action="store_true", help="Print dependency status without opening the UI")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(dependency_status(), indent=2))
        return
    import tkinter as tk
    from .ui import Application

    root = tk.Tk()
    tasks = None
    try:
        store = Store((args.data_dir or data_directory()) / "history.sqlite3")
        tasks = TaskQueue(store, DemoSpeech() if args.demo else UnconfiguredSpeech(),
                          DemoText() if args.demo else UnconfiguredText())
        Application(root, store, tasks, args.demo)
        root.mainloop()
    finally:
        if tasks:
            tasks.close()
            tasks.join()


if __name__ == "__main__":
    main()
