"""Opt-in native Tk smoke tests; run explicitly on a graphical desktop."""

import tempfile
import sys
import tkinter as tk
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from local_whisper.adapters import DemoSpeech, DemoText
from local_whisper.domain import Kind
from local_whisper.storage import Store
from local_whisper.tasks import TaskQueue
from local_whisper.ui import Application


class DesktopSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.store = Store(self.directory / "history.sqlite3")
        self.queue = TaskQueue(self.store, DemoSpeech(), DemoText())
        self.addCleanup(self.queue.join)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = Application(self.root, self.store, self.queue,
                               demo=self._testMethodName != "test_normal_preview_disables_simulated_transcription")
        self.addCleanup(self.app.close)
        self.audio = self.directory / "sample.wav"
        with wave.open(str(self.audio), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x00\x00" * 1600)

    def refresh(self):
        self.app._poll()
        self.root.update_idletasks()

    def test_desktop_import_queue_versions_export_copy_delete(self):
        self.assertEqual(len(self.app.notebook.tabs()), 6)
        with patch("local_whisper.ui.filedialog.askopenfilenames", return_value=(str(self.audio),)):
            self.app.import_audio()
        self.refresh()
        source = self.store.sources()[0]["id"]
        self.app.sources_tree.selection_set(source)
        self.app.transcribe_button.invoke()
        self.queue.wait_idle()
        self.refresh()
        self.app.history_tree.selection_set(source)
        self.app.open_versions()
        self.app.derive(Kind.INTELLIGENT)
        self.queue.wait_idle()
        self.refresh()
        intelligent = self.store.versions(source)[1]
        self.app.versions_tree.selection_set(intelligent.id)
        self.app.derive(Kind.REPORT)
        self.queue.wait_idle()
        self.refresh()
        self.assertEqual(len(self.store.versions(source)), 3)
        self.app.copy()
        self.assertIn("DEMO", self.root.clipboard_get())
        export = self.directory / "export.json"
        with patch("local_whisper.ui.filedialog.asksaveasfilename", return_value=str(export)):
            self.app.export()
        self.assertTrue(export.exists())
        self.app.silence.set("0.7")
        self.app.save_settings()
        self.assertEqual(self.store.silence_seconds(), 0.7)
        with patch("local_whisper.ui.messagebox.askyesno", return_value=True):
            self.app.delete()
        self.refresh()
        self.assertEqual(self.store.sources(), [])
        self.assertTrue(self.audio.exists())

    def test_normal_preview_disables_simulated_transcription(self):
        self.assertIn("disabled", self.app.transcribe_button.state())

    def test_local_configuration_and_playback_controls(self):
        # Exercise real widgets with simulated audio output and no model download.
        self.app.demo = False
        model = self.directory / "model.bin"
        model.write_bytes(b"test model")
        self.app.speech_executable.set(sys.executable)
        self.app.speech_model.set(str(model))
        self.app.speech_language.set("fr")
        self.app.configure_speech()
        self.assertNotIn("disabled", self.app.transcribe_button.state())
        self.assertEqual(Store(self.store.path).speech_config().language, "fr")
        self.app.clear_speech()
        self.assertIn("disabled", self.app.transcribe_button.state())
        self.assertIsNone(self.store.speech_config())
        self.assertTrue(model.exists())
        with patch("local_whisper.ui.filedialog.askopenfilenames", return_value=(str(self.audio),)):
            self.app.import_audio()
        self.refresh()
        self.app.sources_tree.selection_set(self.store.sources()[0]["id"])

        class Output:
            def play(self, audio, cancel, progress):
                self.audio = audio
                progress(1)

        output = Output()
        self.app.playback.adapter = output
        self.app.play_button.invoke()
        self.app.playback.join()
        self.refresh()
        self.assertEqual(output.audio, self.audio)
        self.assertIn("completed", self.app.playback_label.cget("text"))
        self.assertIn("disabled", self.app.stop_button.state())
        self.assertTrue(self.audio.exists())
