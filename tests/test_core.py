import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from threading import Event

from local_whisper.adapters import DemoSpeech, DemoText, UnconfiguredSpeech
from local_whisper.audio import Segmenter
from local_whisper.domain import Kind, Result, Status
from local_whisper.storage import Store
from local_whisper.tasks import TaskQueue


class StoreFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.audio = self.directory / "source.wav"
        self.audio.write_bytes(b"source bytes")
        self.db = self.directory / "history.sqlite3"
        self.store = Store(self.db)
        self.source = self.store.import_audio(self.audio)

    def raw(self):
        return self.store.add_version(self.source, Kind.RAW,
                                      Result("Original text\nwith punctuation!", "test", "test-model", {"language": "en"}))


class StoreTests(StoreFixture, unittest.TestCase):

    def test_append_only_versions_and_restart(self):
        raw = self.raw()
        intelligent = self.store.add_version(self.source, Kind.INTELLIGENT,
                                             Result("Formatted text", "test-llm", "model"), raw)
        report = self.store.add_version(self.source, Kind.REPORT, Result("Report", "test-llm", "model"), intelligent)
        self.store.add_version(self.source, Kind.RAW, Result("Regenerated raw", "test", "test-model"))
        restarted = Store(self.db)
        self.assertEqual(len(restarted.versions(self.source)), 4)
        self.assertEqual(restarted.version(raw).text, "Original text\nwith punctuation!")
        self.assertEqual(restarted.version(report).parent_id, intelligent)
        self.assertEqual(restarted.version(raw).parameters, {"language": "en"})
        self.assertTrue(restarted.version(raw).created_at)

    def test_parent_validation(self):
        raw = self.raw()
        with self.assertRaises(ValueError):
            self.store.add_version(self.source, Kind.REPORT, Result("Bad", "x", "x"), raw)
        other_source = self.store.import_audio(self.audio)
        with self.assertRaises(ValueError):
            self.store.add_version(other_source, Kind.INTELLIGENT, Result("Bad", "x", "x"), raw)
        with self.assertRaises(ValueError):
            self.store.add_version(self.source, Kind.RAW, Result("Bad", "x", "x"), raw)

    def test_export_with_provenance_and_overwrite_protection(self):
        raw = self.raw()
        target = self.directory / "transcript.json"
        self.store.export(raw, target)
        content = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(content["version"]["id"], raw)
        self.assertEqual(content["source"]["path"], str(self.audio.resolve()))
        self.assertEqual(content["version"]["text"], self.store.version(raw).text)
        text = self.directory / "transcript.txt"
        self.store.export(raw, text)
        self.assertEqual(text.read_text(encoding="utf-8"), self.store.version(raw).text)
        with self.assertRaises(FileExistsError):
            self.store.export(raw, text)
        with self.assertRaises(ValueError):
            self.store.export(raw, self.audio)
        with self.assertRaises(ValueError):
            self.store.export(raw, self.db)

    def test_delete_keeps_original_audio_and_removes_history(self):
        raw = self.raw()
        self.store.add_version(self.source, Kind.INTELLIGENT, Result("Formatted", "x", "x"), raw)
        self.store.create_task(self.source, Kind.RAW)
        self.store.delete_source(self.source)
        self.assertEqual(self.audio.read_bytes(), b"source bytes")
        self.assertEqual(self.store.sources(), [])
        self.assertEqual(self.store.versions(self.source), [])
        self.assertEqual(self.store.tasks(), [])

    def test_schema_version_and_newer_database_protection(self):
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            db.execute("PRAGMA user_version = 99")
            db.commit()
        with self.assertRaises(RuntimeError):
            Store(self.db)
        self.assertTrue(self.audio.exists())

    def test_settings_persist_and_validate(self):
        self.store.set_silence_seconds(0.8)
        self.assertEqual(Store(self.db).silence_seconds(), 0.8)
        for value in (0, -1, 11, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.store.set_silence_seconds(value)

    def test_interrupted_tasks_recovered_without_losing_versions(self):
        raw = self.raw()
        pending = self.store.create_task(self.source, Kind.RAW)
        self.store.update_task(pending, Status.TRANSCRIBING)
        finished = self.store.create_task(self.source, Kind.RAW)
        self.store.update_task(finished, Status.COMPLETED)
        Store(self.db).recover_tasks()
        states = {t["id"]: t["status"] for t in self.store.tasks()}
        self.assertEqual(states[pending], Status.FAILED)
        self.assertEqual(states[finished], Status.COMPLETED)
        self.assertEqual(self.store.version(raw).text, "Original text\nwith punctuation!")


class QueueTests(StoreFixture, unittest.TestCase):
    def queue(self, speech=None, text=None):
        queue = TaskQueue(self.store, speech or DemoSpeech(), text or DemoText())
        self.addCleanup(queue.join)
        self.addCleanup(queue.close)
        return queue

    def test_complete_pipeline_keeps_every_source_version(self):
        queue = self.queue()
        queue.submit(self.source)
        queue.wait_idle()
        raw = self.store.versions(self.source)[0]
        queue.submit(self.source, Kind.INTELLIGENT, raw.id)
        queue.wait_idle()
        intelligent = self.store.versions(self.source)[1]
        queue.submit(self.source, Kind.REPORT, intelligent.id)
        queue.wait_idle()
        versions = self.store.versions(self.source)
        self.assertEqual([v.kind for v in versions], list(Kind))
        self.assertTrue(all(v.text == raw.text for v in versions))
        self.assertTrue(all(v.parameters["simulated"] for v in versions))
        self.assertTrue(all(t["status"] == Status.COMPLETED for t in self.store.tasks()))

    def test_queued_and_active_cancellation_persist_no_text(self):
        entered, release = Event(), Event()

        class BlockingSpeech:
            def transcribe(self, audio, cancel):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("Test adapter timed out")
                # Deliberately ignores cancellation: the queue must still discard output.
                return Result("Should not persist", "test", "test")

        queue = self.queue(BlockingSpeech())
        first = queue.submit(self.source)
        self.assertTrue(entered.wait(2))
        second = queue.submit(self.source)
        queue.cancel(first)
        queue.cancel(second)
        release.set()
        queue.wait_idle()
        self.assertEqual([t["status"] for t in self.store.tasks()], [Status.CANCELLED, Status.CANCELLED])
        self.assertEqual(self.store.versions(self.source), [])
        self.assertFalse(queue.source_busy(self.source))

    def test_failure_does_not_stop_next_task_or_leak_adapter_error(self):
        class FailingOnce:
            calls = 0

            def transcribe(self, audio, cancel):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("private-token-and-transcript")
                return Result("Success", "test", "test")

        queue = self.queue(FailingOnce())
        queue.submit(self.source)
        queue.submit(self.source)
        queue.wait_idle()
        tasks = self.store.tasks()
        self.assertEqual([t["status"] for t in tasks], [Status.FAILED, Status.COMPLETED])
        self.assertNotIn("private-token", tasks[0]["error"])
        self.assertEqual(len(self.store.versions(self.source)), 1)

    def test_unconfigured_engine_produces_no_fake_transcript(self):
        queue = self.queue(UnconfiguredSpeech())
        queue.submit(self.source)
        queue.wait_idle()
        self.assertEqual(self.store.tasks()[0]["status"], Status.FAILED)
        self.assertEqual(self.store.versions(self.source), [])

    def test_report_requires_intelligent_parent_before_enqueue(self):
        raw = self.raw()
        queue = self.queue()
        with self.assertRaises(ValueError):
            queue.submit(self.source, Kind.REPORT, raw)
        self.assertEqual(self.store.tasks(), [])

    def test_shutdown_cancels_work_and_rejects_new_tasks(self):
        queue = self.queue()
        queue.submit(self.source)
        queue.close()
        queue.wait_idle()
        queue.join()
        self.assertEqual(self.store.tasks()[0]["status"], Status.CANCELLED)
        with self.assertRaises(RuntimeError):
            queue.submit(self.source)


class SegmentTests(unittest.TestCase):
    def test_pause_emits_before_session_ends_and_resumed_speech_starts_new_segment(self):
        segmenter = Segmenter(0.5)
        self.assertIsNone(segmenter.feed(b"ignored", False, 0))
        self.assertIsNone(segmenter.feed(b"one", True, 0.1))
        self.assertIsNone(segmenter.feed(b"pause", False, 0.3))
        self.assertEqual(segmenter.feed(b"end", False, 0.6), b"onepauseend")
        self.assertIsNone(segmenter.feed(b"ignored", False, 0.8))
        self.assertIsNone(segmenter.feed(b"two", True, 1))
        self.assertEqual(segmenter.stop(), b"two")
        self.assertIsNone(segmenter.stop())

    def test_short_pause_does_not_split_and_manual_stop_flushes(self):
        segmenter = Segmenter(1)
        segmenter.feed(b"one", True, 0)
        segmenter.feed(b"pause", False, 0.5)
        segmenter.feed(b"two", True, 0.6)
        self.assertIsNone(segmenter.feed(b"pause", False, 1.2))
        self.assertEqual(segmenter.stop(), b"onepausetwopause")

    def test_invalid_threshold_and_timestamps(self):
        for value in (0, 11, float("nan")):
            with self.assertRaises(ValueError):
                Segmenter(value)
        segmenter = Segmenter()
        segmenter.feed(b"", False, 1)
        for value in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                segmenter.feed(b"", False, value)
