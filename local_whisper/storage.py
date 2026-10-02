"""Append-only transcript versions and versioned SQLite storage.

Connections belong to individual operations, never shared between threads.
Imported audio is referenced, not copied or deleted.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .domain import Kind, Result, Status, Version, now

SCHEMA_VERSION = 1


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError("History was created by a newer application version.")
            if version == 0:
                db.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE sources (
                        id TEXT PRIMARY KEY, path TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE versions (
                        id TEXT PRIMARY KEY,
                        source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                        kind TEXT NOT NULL CHECK(kind IN ('raw', 'intelligent', 'report')),
                        parent_id TEXT REFERENCES versions(id) ON DELETE CASCADE,
                        text TEXT NOT NULL, engine TEXT NOT NULL, model TEXT NOT NULL,
                        created_at TEXT NOT NULL, parameters TEXT NOT NULL
                    );
                    CREATE TABLE tasks (
                        id TEXT PRIMARY KEY,
                        source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                        kind TEXT NOT NULL,
                        status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL
                    );
                    CREATE INDEX versions_source ON versions(source_id, created_at);
                    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    PRAGMA user_version = 1;
                    COMMIT;
                """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def import_audio(self, path: Path) -> str:
        path = path.resolve(strict=True)
        if not path.is_file():
            raise ValueError("Audio source must be a file.")
        source_id = str(uuid4())
        with self.connection() as db:
            db.execute("INSERT INTO sources VALUES (?, ?, ?)", (source_id, str(path), now()))
        return source_id

    def sources(self) -> list[dict]:
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM sources ORDER BY created_at DESC")]

    def source(self, source_id: str) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
            if row is None:
                raise KeyError("Audio source does not exist.")
            return dict(row)

    def _insert_version(self, db, source_id: str, kind: Kind, result: Result, parent_id: str | None) -> str:
        if kind == Kind.RAW and parent_id is not None:
            raise ValueError("Raw transcripts cannot have a parent version.")
        if kind != Kind.RAW:
            parent = db.execute("SELECT source_id, kind FROM versions WHERE id = ?", (parent_id,)).fetchone()
            expected = Kind.RAW if kind == Kind.INTELLIGENT else Kind.INTELLIGENT
            if parent is None or parent["source_id"] != source_id or parent["kind"] != expected:
                raise ValueError("Derived versions require the correct source and parent kind.")
        version_id = str(uuid4())
        db.execute("INSERT INTO versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (version_id, source_id, kind, parent_id, result.text, result.engine,
                    result.model, now(), json.dumps(result.parameters, ensure_ascii=False)))
        return version_id

    def add_version(self, source_id: str, kind: Kind, result: Result, parent_id: str | None = None) -> str:
        with self.connection() as db:
            return self._insert_version(db, source_id, kind, result, parent_id)

    @staticmethod
    def _version(row) -> Version:
        data = dict(row)
        data["kind"] = Kind(data["kind"])
        data["parameters"] = json.loads(data["parameters"])
        return Version(**data)

    def versions(self, source_id: str) -> list[Version]:
        with self.connection() as db:
            return [self._version(r) for r in db.execute(
                "SELECT * FROM versions WHERE source_id = ? ORDER BY created_at", (source_id,))]

    def version(self, version_id: str) -> Version:
        with self.connection() as db:
            row = db.execute("SELECT * FROM versions WHERE id = ?", (version_id,)).fetchone()
            if row is None:
                raise KeyError("Transcript version does not exist.")
            return self._version(row)

    def delete_source(self, source_id: str):
        """Delete the history entry, all versions and tasks; never touch audio."""
        with self.connection() as db:
            db.execute("DELETE FROM sources WHERE id = ?", (source_id,))

    def export(self, version_id: str, target: Path):
        version = self.version(version_id)
        source = self.source(version.source_id)
        if target.resolve() == Path(source["path"]).resolve() or target.resolve() == self.path.resolve():
            raise ValueError("Export cannot replace the audio source or history database.")
        if target.suffix.lower() == ".json":
            from dataclasses import asdict
            content = json.dumps({"schema_version": SCHEMA_VERSION, "source": source,
                                  "version": asdict(version)}, ensure_ascii=False, indent=2)
        elif target.suffix.lower() == ".txt":
            content = version.text
        else:
            raise ValueError("Choose a .txt or .json export.")
        # Exclusive creation prevents overwriting unrelated files.
        with target.open("x", encoding="utf-8", newline="") as file:
            file.write(content)

    def create_task(self, source_id: str, kind: Kind) -> str:
        task_id = str(uuid4())
        with self.connection() as db:
            db.execute("INSERT INTO tasks VALUES (?, ?, ?, ?, NULL, ?)",
                       (task_id, source_id, kind, Status.QUEUED, now()))
        return task_id

    def update_task(self, task_id: str, status: Status, error: str | None = None):
        with self.connection() as db:
            db.execute("UPDATE tasks SET status = ?, error = ? WHERE id = ?", (status, error, task_id))

    def complete_task(self, task_id: str, source_id: str, kind: Kind, result: Result, parent_id: str | None):
        with self.connection() as db:
            self._insert_version(db, source_id, kind, result, parent_id)
            db.execute("UPDATE tasks SET status = ?, error = NULL WHERE id = ?", (Status.COMPLETED, task_id))

    def tasks(self) -> list[dict]:
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT * FROM tasks ORDER BY created_at")]

    def recover_tasks(self):
        with self.connection() as db:
            db.execute("UPDATE tasks SET status = ?, error = ? WHERE status NOT IN (?, ?, ?)",
                       (Status.FAILED, "Processing was interrupted. Queue a new task to retry.",
                        Status.COMPLETED, Status.CANCELLED, Status.FAILED))

    def set_silence_seconds(self, seconds: float):
        if not 0.1 <= seconds <= 10:
            raise ValueError("Silence threshold must be between 0.1 and 10 seconds.")
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('silence_seconds', ?)", (str(seconds),))

    def silence_seconds(self) -> float:
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'silence_seconds'").fetchone()
            return float(row[0]) if row else 1.0

    def speech_config(self):
        from .speech import WhisperConfig
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'whisper_cpp'").fetchone()
        if row is None:
            return None
        value = json.loads(row[0])
        return WhisperConfig(Path(value["executable"]), Path(value["model"]), value["language"])

    def set_speech_config(self, config):
        if config is None:
            with self.connection() as db:
                db.execute("DELETE FROM settings WHERE key = 'whisper_cpp'")
            return
        config.validate()
        value = json.dumps({"executable": str(config.executable.resolve()),
                            "model": str(config.model.resolve()), "language": config.language})
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('whisper_cpp', ?)", (value,))

    def text_config(self):
        from .text import LlamaConfig
        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key = 'llama_cpp'").fetchone()
        if row is None:
            return None
        value = json.loads(row[0])
        return LlamaConfig(Path(value["executable"]), Path(value["model"]),
                           value["context_tokens"], value["output_tokens"])

    def set_text_config(self, config):
        if config is None:
            with self.connection() as db:
                db.execute("DELETE FROM settings WHERE key = 'llama_cpp'")
            return
        config.validate()
        value = json.dumps({"executable": str(config.executable.resolve()),
                            "model": str(config.model.resolve()), "context_tokens": config.context_tokens,
                            "output_tokens": config.output_tokens})
        with self.connection() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('llama_cpp', ?)", (value,))
