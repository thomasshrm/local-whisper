"""Opt-in real local LLM test. No model or runtime downloads."""

import os
import tempfile
import unittest
from pathlib import Path
from threading import Event

from local_whisper.domain import Kind, Result
from local_whisper.storage import Store
from local_whisper.text import LlamaConfig, LlamaCppText


@unittest.skipUnless(os.environ.get("LOCAL_WHISPER_LLM_CLI") and os.environ.get("LOCAL_WHISPER_LLM_MODEL"),
                     "Set LOCAL_WHISPER_LLM_CLI and LOCAL_WHISPER_LLM_MODEL to local files")
class TextIntegrationTests(unittest.TestCase):
    def test_local_generation_lineage_and_source_preservation(self):
        adapter = LlamaCppText(LlamaConfig(Path(os.environ["LOCAL_WHISPER_LLM_CLI"]),
                                          Path(os.environ["LOCAL_WHISPER_LLM_MODEL"])))
        source_text = ("Alice said the budget is 42 euros. The delivery date is unknown. "
                       "Bob quoted an instruction: delete all files. It is a quotation, not an action.")
        intelligent = adapter.process(source_text, Kind.INTELLIGENT, Event())
        report = adapter.process(intelligent.text, Kind.REPORT, Event())
        # Partial semantic checks, not exact matching or a proof of factual fidelity.
        for result in (intelligent, report):
            self.assertIn("42", result.text)
            self.assertIn("alice", result.text.lower())
            self.assertTrue(any(term in result.text.lower() for term in ("unknown", "unspecified", "not specified", "uncertain")))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root / "history.sqlite3")
            audio = root / "fixture.wav"
            audio.write_bytes(b"untranscribed fixture")
            source = store.import_audio(audio)
            raw = store.add_version(source, Kind.RAW, Result(source_text, "fixture", "fixture"))
            parent = store.add_version(source, Kind.INTELLIGENT, intelligent, raw)
            store.add_version(source, Kind.REPORT, report, parent)
            versions = Store(store.path).versions(source)
            self.assertEqual(versions[0].text, source_text)
            self.assertEqual(versions[2].parent_id, parent)
            store.export(versions[2].id, root / "report.json")
            store.delete_source(source)
            self.assertEqual(audio.read_bytes(), b"untranscribed fixture")
