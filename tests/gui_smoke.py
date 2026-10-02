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
from local_whisper.speech import WhisperConfig, WhisperCppSpeech
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
        # Replace the scheduled poll; manual refresh must not add another timer.
        if self.app._poll_id is not None:
            self.root.after_cancel(self.app._poll_id)
            self.app._poll_id = None
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
        self.assertEqual(self.app.tasks_tree.selection(), (self.store.tasks()[0]["id"],))
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
        self.assertEqual(self.app.transcript_sources, [])
        self.assertEqual(self.app.versions_tree.get_children(), ())
        self.assertEqual(self.app.text.get("1.0", "end-1c"), "")
        self.assertTrue(self.audio.exists())

    def test_normal_preview_disables_simulated_transcription(self):
        self.assertIn("disabled", self.app.transcribe_button.state())

    def test_completed_transcript_is_visible_without_opening_history(self):
        source = self.store.import_audio(self.audio)
        self.refresh()
        self.app.sources_tree.selection_set(source)
        self.app.transcribe()
        self.queue.wait_idle()
        self.refresh()
        raw = self.store.versions(source)[0]
        self.app.notebook.select(self.app.transcripts_tab)
        self.assertEqual(self.app.transcript_sources, [source])
        self.assertEqual(self.app.versions_tree.selection(), (raw.id,))
        self.assertEqual(self.app.text.get("1.0", "end-1c"), raw.text)

    def test_source_selector_and_completed_task_open_correct_transcripts(self):
        first = self.store.import_audio(self.audio)
        self.queue.submit(first)
        self.queue.wait_idle()
        self.refresh()
        first_version = self.store.versions(first)[0]
        # Same filename, separate imports: the selector must distinguish entries.
        second = self.store.import_audio(self.audio)
        second_task = self.queue.submit(second)
        self.queue.wait_idle()
        self.refresh()
        second_version = self.store.versions(second)[0]
        self.assertEqual(self.app.versions_tree.selection(), (first_version.id,))
        labels = self.app.transcript_source.cget("values")
        self.assertEqual(len(labels), 2)
        self.assertNotEqual(labels[0], labels[1])
        self.app.transcript_source.current(self.app.transcript_sources.index(second))
        self.app.transcript_source.event_generate("<<ComboboxSelected>>")
        self.root.update()
        self.assertEqual(self.app.versions_tree.selection(), (second_version.id,))
        self.app.history_tree.selection_set(first)
        self.app.open_versions()
        self.assertEqual(self.app.versions_tree.selection(), (first_version.id,))
        self.app.notebook.select(self.app.audio_tab)
        self.app.tasks_tree.selection_set(second_task)
        self.app.open_task_versions()
        self.assertEqual(self.app.notebook.select(), str(self.app.transcripts_tab))
        self.assertEqual(self.app.versions_tree.selection(), (second_version.id,))
        with patch("local_whisper.ui.messagebox.askyesno", return_value=True):
            self.app.history_tree.selection_set(second)
            self.app.delete()
        self.refresh()
        self.assertEqual(self.app.transcript_sources, [first])
        self.assertEqual(self.app.versions_tree.selection(), (first_version.id,))

    def test_completed_transcript_is_visible_after_restart(self):
        source = self.store.import_audio(self.audio)
        self.queue.submit(source)
        self.queue.wait_idle()
        raw = self.store.versions(source)[0]
        self.app.close()
        self.queue.join()
        store = Store(self.store.path)
        queue = TaskQueue(store, DemoSpeech(), DemoText())
        self.addCleanup(queue.join)
        root = tk.Tk()
        root.withdraw()
        app = Application(root, store, queue, demo=True)
        self.addCleanup(app.close)
        self.assertEqual(app.transcript_sources, [source])
        self.assertEqual(app.versions_tree.selection(), (raw.id,))
        self.assertEqual(app.text.get("1.0", "end-1c"), raw.text)

    def test_queued_failure_is_selected_and_displays_reason(self):
        with wave.open(str(self.audio), "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(44100)
            audio.writeframes(b"\x00\x00" * 3200)
        model = self.directory / "model.bin"
        model.write_bytes(b"test model")
        self.queue.set_speech(WhisperCppSpeech(WhisperConfig(Path(sys.executable), model)))
        source = self.store.import_audio(self.audio)
        self.refresh()
        self.app.sources_tree.selection_set(source)
        with patch("local_whisper.speech.subprocess.Popen") as process:
            self.app.transcribe()
            self.queue.wait_idle()
            process.assert_not_called()
        self.refresh()
        task = self.store.tasks()[0]
        self.assertEqual(task["status"], "failed")
        self.assertEqual(self.app.tasks_tree.selection(), (task["id"],))
        self.assertIn("44100 Hz", self.app.task_error.cget("text"))

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
