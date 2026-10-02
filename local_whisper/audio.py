"""Segment boundary logic independent of microphone, VAD and speech runtime."""

from dataclasses import dataclass, field
from math import isfinite
from contextlib import contextmanager
from pathlib import Path
import wave


class AudioError(ValueError):
    """A safe, user-facing audio validation error."""


@contextmanager
def pcm_wav(path: Path, *, speech: bool = False):
    """Open supported PCM without converting or modifying the source file."""
    try:
        source = wave.open(str(path), "rb")
    except (wave.Error, EOFError):
        raise AudioError("Choose an uncompressed PCM WAV file.") from None
    with source:
        if (source.getcomptype() != "NONE" or source.getsampwidth() != 2
                or source.getnchannels() not in (1, 2) or source.getnframes() == 0):
            raise AudioError("Choose a nonempty 16-bit PCM WAV file with one or two channels.")
        if speech and source.getframerate() != 16000:
            raise AudioError("Transcription currently requires a 16-bit PCM WAV file at 16000 Hz "
                             "with one or two channels. This file is at "
                             f"{source.getframerate()} Hz.")
        yield source


@dataclass
class Segmenter:
    """Feed ordered frames and a speech flag from a future VAD adapter.

    Emit after enough silence, or flush at manual stop. Timestamp is the end
    of a frame in seconds. Silence before speech is discarded.
    """

    silence_seconds: float = 1.0
    _frames: list[bytes] = field(default_factory=list, init=False)
    _last_speech: float | None = field(default=None, init=False)
    _last_frame: float | None = field(default=None, init=False)

    def __post_init__(self):
        if not isfinite(self.silence_seconds) or not 0.1 <= self.silence_seconds <= 10:
            raise ValueError("Silence threshold must be between 0.1 and 10 seconds.")

    def feed(self, frame: bytes, speech: bool, timestamp: float) -> bytes | None:
        if not isfinite(timestamp) or timestamp < 0 or (self._last_frame is not None and timestamp < self._last_frame):
            raise ValueError("Frame timestamps must be finite, nonnegative and ordered.")
        self._last_frame = timestamp
        if speech:
            self._last_speech = timestamp
        if self._last_speech is None:
            return None
        self._frames.append(frame)
        if not speech and timestamp - self._last_speech >= self.silence_seconds:
            return self.stop()
        return None

    def stop(self) -> bytes | None:
        segment = b"".join(self._frames) if self._frames else None
        self._frames.clear()
        self._last_speech = None
        return segment
