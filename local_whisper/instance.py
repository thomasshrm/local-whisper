"""Process-lifetime history ownership, independent of SQLite transactions."""

import errno
import os
from contextlib import contextmanager
from pathlib import Path


class HistoryInUse(RuntimeError):
    """Another application instance owns this history."""


@contextmanager
def history_instance(history: Path):
    # Resolve directory aliases so both processes lock the same sidecar.
    history = history.resolve()
    history.parent.mkdir(parents=True, exist_ok=True)
    # Never delete this file: replacing its inode would allow two owners.
    with history.with_suffix(history.suffix + ".lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise HistoryInUse("This history is already open in another Local Whisper instance. "
                                   "Close that instance before trying again.") from None
            raise
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
