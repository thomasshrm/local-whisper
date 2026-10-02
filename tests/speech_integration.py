"""Opt-in real-model test. No downloads; paths are supplied by the developer."""

import os
import tempfile
import unittest
from pathlib import Path

from local_whisper.adapters import UnconfiguredText
from local_whisper.domain import Status
from local_whisper.speech import WhisperConfig, WhisperCppSpeech
from local_whisper.storage import Store
from local_whisper.tasks import TaskQueue


@unittest.skipUnless(all(os.environ.get(name) for name in
                         ("LOCAL_WHISPER_CLI", "LOCAL_WHISPER_MODEL", "LOCAL_WHISPER_AUDIO")),
                     "Set LOCAL_WHISPER_CLI, LOCAL_WHISPER_MODEL and LOCAL_WHISPER_AUDIO.")
class SpeechIntegrationTests(unittest.TestCase):
    def test_offline_raw_transcription_persistence_and_export(self):
        config = WhisperConfig(Path(os.environ["LOCAL_WHISPER_CLI"]),
                               Path(os.environ["LOCAL_WHISPER_MODEL"]),
                               os.environ.get("LOCAL_WHISPER_LANGUAGE", "auto"))
        audio = Path(os.environ["LOCAL_WHISPER_AUDIO"])
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "history.sqlite3")
            source = store.import_audio(audio)
            queue = TaskQueue(store, WhisperCppSpeech(config), UnconfiguredText())
            try:
                queue.submit(source)
                queue.wait_idle()
                self.assertEqual(store.tasks()[0]["status"], Status.COMPLETED, store.tasks()[0]["error"])
                raw = Store(store.path).versions(source)[0]
                self.assertTrue(raw.text.strip(), "Use a WAV sample containing audible speech.")
                self.assertEqual(raw.engine, "whisper.cpp")
                self.assertEqual(raw.parameters["device"], "cpu")
                self.assertEqual(len(raw.parameters["model_sha256"]), 64)
                target = Path(directory) / "transcript.txt"
                store.export(raw.id, target)
                with target.open(encoding="utf-8", newline="") as file:
                    self.assertEqual(file.read(), raw.text)
                store.delete_source(source)
                self.assertTrue(audio.is_file())
            finally:
                queue.close()
                queue.join(timeout=None)
