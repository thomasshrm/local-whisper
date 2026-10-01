"""One background worker, serial inference, cooperative cancellation."""

from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from threading import Event, RLock, Thread

from .adapters import Cancelled, SpeechAdapter, TextAdapter, check_cancelled
from .domain import Kind, Status
from .storage import Store


@dataclass
class Work:
    id: str
    source_id: str
    kind: Kind
    parent_id: str | None
    cancel: Event


class TaskQueue:
    def __init__(self, store: Store, speech: SpeechAdapter, text: TextAdapter):
        self.store, self.speech, self.text = store, speech, text
        self._queue: Queue[Work | None] = Queue()
        self._lock = RLock()
        self._work: dict[str, Work] = {}
        self._closed = False
        store.recover_tasks()
        self._thread = Thread(target=self._run, name="local-inference", daemon=True)
        self._thread.start()

    def submit(self, source_id: str, kind: Kind = Kind.RAW, parent_id: str | None = None) -> str:
        with self._lock:
            if self._closed:
                raise RuntimeError("Task queue is closed.")
            self.store.source(source_id)
            if kind != Kind.RAW:
                parent = self.store.version(parent_id or "")
                expected = Kind.RAW if kind == Kind.INTELLIGENT else Kind.INTELLIGENT
                if parent.source_id != source_id or parent.kind != expected:
                    raise ValueError("Select the correct source transcript version.")
            elif parent_id is not None:
                raise ValueError("Raw transcription cannot have a parent.")
            task_id = self.store.create_task(source_id, kind)
            work = Work(task_id, source_id, kind, parent_id, Event())
            self._work[task_id] = work
            self._queue.put(work)
            return task_id

    def cancel(self, task_id: str):
        with self._lock:
            work = self._work.get(task_id)
            if work:
                work.cancel.set()

    def source_busy(self, source_id: str) -> bool:
        with self._lock:
            return any(w.source_id == source_id for w in self._work.values())

    def _run(self):
        while True:
            work = self._queue.get()
            try:
                if work is None:
                    return
                try:
                    check_cancelled(work.cancel)
                    self.store.update_task(work.id, Status.LOADING)
                    if work.kind == Kind.RAW:
                        self.store.update_task(work.id, Status.TRANSCRIBING)
                        audio = Path(self.store.source(work.source_id)["path"])
                        result = self.speech.transcribe(audio, work.cancel)
                    else:
                        self.store.update_task(work.id, Status.PROCESSING)
                        parent = self.store.version(work.parent_id or "")
                        result = self.text.process(parent.text, work.kind, work.cancel)
                    # Cancellation and persistence have a single ordered boundary.
                    with self._lock:
                        check_cancelled(work.cancel)
                        self.store.complete_task(work.id, work.source_id, work.kind, result, work.parent_id)
                        self._work.pop(work.id, None)
                except Cancelled:
                    self.store.update_task(work.id, Status.CANCELLED)
                except Exception:
                    # Adapter exception messages may contain private text or tokens.
                    self.store.update_task(work.id, Status.FAILED,
                                           "Processing failed. Check engine configuration and audio availability.")
                finally:
                    with self._lock:
                        self._work.pop(work.id, None)
            finally:
                self._queue.task_done()

    def wait_idle(self):
        """For tests and command-line consumers; never call from the UI thread."""
        self._queue.join()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for work in self._work.values():
                work.cancel.set()
            self._queue.put(None)

    def join(self, timeout: float = 2):
        self._thread.join(timeout)
