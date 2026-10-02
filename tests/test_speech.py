"""CLI boundary tests with real child processes and a simulated engine."""

import hashlib
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from local_whisper.adapters import DemoText
from local_whisper.audio import AudioError
from local_whisper.domain import Kind, Result, Status
from local_whisper.speech import SpeechError, WhisperConfig, WhisperCppSpeech
from local_whisper.storage import Store
from local_whisper.tasks import TaskQueue
from tests.test_playback import write_wav


FAKE_CLI = '''
import sys, time
from pathlib import Path
args = sys.argv[1:]
model = Path(args[args.index("-m") + 1])
output = Path(args[args.index("-of") + 1] + ".txt")
mode = model.read_text(encoding="utf-8")
if mode == "missing":
    sys.exit(0)
output.write_bytes("  Bonjour !\\r\\nDeuxième ligne.\\n\\n".encode("utf-8"))
if mode == "fail":
    print("private-token-and-transcript", file=sys.stderr)
    sys.exit(2)
if mode == "change":
    model.write_text("changed", encoding="utf-8")
if mode == "hang":
    model.with_suffix(".started").touch()
    time.sleep(30)
'''


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.model = self.directory / "modèle with spaces.bin"
        self.model.write_text("success", encoding="utf-8")
        self.audio = self.directory / "audio with spaces.wav"
        write_wav(self.audio)
        self.fixture = self.directory / "fake_cli.py"
        self.fixture.write_text(FAKE_CLI, encoding="utf-8")
        self.config = WhisperConfig(Path(sys.executable).resolve(), self.model, "fr")
        self.commands, self.processes = [], []
        real_popen = subprocess.Popen

        def launch(command, **options):
            self.assertFalse(options["shell"])
            self.assertEqual(options["stdout"], subprocess.DEVNULL)
            self.assertEqual(options["stderr"], subprocess.DEVNULL)
            self.commands.append(command)
            process = real_popen([sys.executable, str(self.fixture), *command[1:]], **options)
            self.processes.append(process)
            return process

        self.patch = patch("local_whisper.speech.subprocess.Popen", side_effect=launch)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def assert_temporary_outputs_removed(self):
        for command in self.commands:
            output = Path(command[command.index("-of") + 1])
            self.assertFalse(output.parent.exists())

    def test_raw_output_is_preserved_and_provenance_identifies_files(self):
        original = self.audio.read_bytes()
        result = WhisperCppSpeech(self.config).transcribe(self.audio, Event())
        self.assertEqual(result.text, "  Bonjour !\r\nDeuxième ligne.\n\n")
        self.assertEqual(result.parameters["language"], "fr")
        self.assertEqual(result.parameters["device"], "cpu")
        self.assertEqual(result.parameters["model_sha256"], hashlib.sha256(b"success").hexdigest())
        self.assertEqual(result.parameters["audio_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(result.parameters["model_path"], str(self.model.resolve()))
        self.assertIn("-ng", self.commands[0])
        self.assertEqual(self.audio.read_bytes(), original)
        self.assert_temporary_outputs_removed()

    def test_failed_missing_and_changed_outputs_are_not_accepted(self):
        for mode in ("fail", "missing", "change"):
            with self.subTest(mode=mode):
                self.model.write_text(mode, encoding="utf-8")
                with self.assertRaises(SpeechError) as error:
                    WhisperCppSpeech(self.config).transcribe(self.audio, Event())
                self.assertNotIn("private-token", str(error.exception))
                self.assert_temporary_outputs_removed()

    def test_cancel_terminates_child_discards_partial_text_and_keeps_source(self):
        self.model.write_text("hang", encoding="utf-8")
        store = Store(self.directory / "history.sqlite3")
        source = store.import_audio(self.audio)
        queue = TaskQueue(store, WhisperCppSpeech(self.config), DemoText())
        self.addCleanup(queue.join)
        self.addCleanup(queue.close)
        task = queue.submit(source)
        deadline = time.monotonic() + 5
        while not self.model.with_suffix(".started").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(self.model.with_suffix(".started").exists())
        queue.cancel(task)
        queue.wait_idle()
        self.assertEqual(store.tasks()[0]["status"], Status.CANCELLED)
        self.assertEqual(store.versions(source), [])
        self.assertIsNotNone(self.processes[0].poll())
        self.assertTrue(self.audio.exists())
        self.assert_temporary_outputs_removed()

    def test_queue_regeneration_preserves_original_engine_output(self):
        store = Store(self.directory / "history.sqlite3")
        source = store.import_audio(self.audio)
        queue = TaskQueue(store, WhisperCppSpeech(self.config), DemoText())
        self.addCleanup(queue.join)
        self.addCleanup(queue.close)
        queue.submit(source)
        queue.wait_idle()
        first = store.versions(source)[0]
        queue.submit(source)
        queue.wait_idle()
        self.assertEqual(len(Store(store.path).versions(source)), 2)
        self.assertEqual(store.version(first.id).text, "  Bonjour !\r\nDeuxième ligne.\n\n")
        target = self.directory / "raw.txt"
        store.export(first.id, target)
        self.assertEqual(target.read_bytes(), "  Bonjour !\r\nDeuxième ligne.\n\n".encode("utf-8"))

    def test_unsupported_audio_never_launches_engine(self):
        for settings in ({"rate": 44100}, {"channels": 3}, {"width": 1}):
            write_wav(self.audio, **settings)
            with self.assertRaises(AudioError):
                WhisperCppSpeech(self.config).transcribe(self.audio, Event())
        write_wav(self.audio)
        self.audio.write_bytes(self.audio.read_bytes()[:-2])
        with self.assertRaises(AudioError):
            WhisperCppSpeech(self.config).transcribe(self.audio, Event())
        self.assertEqual(self.commands, [])

    def test_stereo_transcription_preserves_source_and_records_channel_count(self):
        write_wav(self.audio, channels=2)
        original = self.audio.read_bytes()
        result = WhisperCppSpeech(self.config).transcribe(self.audio, Event())
        self.assertEqual(result.parameters["channels"], 2)
        self.assertEqual(result.parameters["channel_handling"], "engine downmix to mono")
        self.assertEqual(result.parameters["audio_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(self.audio.read_bytes(), original)
        self.assertEqual(Path(self.commands[0][self.commands[0].index("-f") + 1]), self.audio.resolve())
        self.assert_temporary_outputs_removed()

    def test_truncated_stereo_does_not_launch_engine(self):
        write_wav(self.audio, channels=2)
        self.audio.write_bytes(self.audio.read_bytes()[:-2])
        with self.assertRaisesRegex(AudioError, "truncated"):
            WhisperCppSpeech(self.config).transcribe(self.audio, Event())
        self.assertEqual(self.commands, [])

    def test_configuration_persistence_validation_and_removal(self):
        store = Store(self.directory / "history.sqlite3")
        store.set_speech_config(self.config)
        # Persistence canonicalizes paths, including macOS /var symlinks and
        # Windows short-name aliases. Compare against that explicit contract.
        expected = WhisperConfig(self.config.executable.resolve(), self.config.model.resolve(), self.config.language)
        self.assertEqual(Store(store.path).speech_config(), expected)
        for config in (WhisperConfig(Path("missing"), self.model),
                       WhisperConfig(Path(sys.executable), self.model, "fr --translate")):
            with self.assertRaises(ValueError):
                store.set_speech_config(config)
        self.assertEqual(store.speech_config(), expected)
        store.set_speech_config(None)
        self.assertIsNone(Store(store.path).speech_config())
        self.assertTrue(self.model.exists())

    def test_model_selection_is_frozen_when_task_is_queued(self):
        entered, release = Event(), Event()

        class OriginalSpeech:
            def transcribe(self, audio, cancel):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("Test timed out")
                return Result("original", "test", "original-model")

        class NewSpeech:
            def transcribe(self, audio, cancel):
                return Result("new", "test", "new-model")

        store = Store(self.directory / "history.sqlite3")
        source = store.import_audio(self.audio)
        queue = TaskQueue(store, OriginalSpeech(), DemoText())
        self.addCleanup(queue.join)
        self.addCleanup(queue.close)
        queue.submit(source)
        self.assertTrue(entered.wait(2))
        queue.submit(source)
        queue.set_speech(NewSpeech())
        queue.submit(source)
        release.set()
        queue.wait_idle()
        self.assertEqual([v.model for v in store.versions(source)],
                         ["original-model", "original-model", "new-model"])
