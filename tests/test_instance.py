"""Exercise real OS locks across processes without opening a desktop."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from local_whisper.domain import Kind, Status
from local_whisper.instance import history_instance
from local_whisper.storage import Store


PROBE = """
import sys
from pathlib import Path
from local_whisper.instance import HistoryInUse, history_instance
try:
    with history_instance(Path(sys.argv[1])):
        pass
except HistoryInUse:
    sys.exit(3)
"""


class InstanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.history = Path(self.temp.name) / "history.sqlite3"

    def probe(self, path):
        return subprocess.run([sys.executable, "-c", PROBE, str(path)],
                              capture_output=True, text=True, timeout=10)

    def test_second_process_is_refused_and_release_allows_restart(self):
        with history_instance(self.history):
            store = Store(self.history)
            audio = self.history.parent / "source.wav"
            audio.write_bytes(b"audio")
            source = store.import_audio(audio)
            task = store.create_task(source, Kind.RAW)
            store.update_task(task, Status.TRANSCRIBING)
            result = self.probe(self.history)
            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertEqual(store.tasks()[0]["status"], Status.TRANSCRIBING)
        result = self.probe(self.history)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.history.with_suffix(".sqlite3.lock").exists())

    def test_independent_histories_can_open_together(self):
        with history_instance(self.history):
            result = self.probe(self.history.parent / "other.sqlite3")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_process_exit_releases_lock_without_cleanup(self):
        script = """
import os, sys
from pathlib import Path
from local_whisper.instance import history_instance
with history_instance(Path(sys.argv[1])):
    os._exit(0)
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.history)],
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(child.returncode, 0, child.stderr)
        result = self.probe(self.history)
        self.assertEqual(result.returncode, 0, result.stderr)
