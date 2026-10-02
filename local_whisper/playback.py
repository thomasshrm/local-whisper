"""Bounded PCM streaming and background playback, without widget access."""

import importlib
from dataclasses import dataclass
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Callable, Protocol

from .adapters import Cancelled, check_cancelled
from .audio import AudioError, pcm_wav


class PlaybackAdapter(Protocol):
    def play(self, audio: Path, cancel: Event, progress: Callable[[float], None]): ...


class SoundDevicePlayback:
    def play(self, audio: Path, cancel: Event, progress: Callable[[float], None]):
        check_cancelled(cancel)
        with pcm_wav(audio) as source:
            try:
                device = importlib.import_module("sounddevice")
            except (ImportError, OSError):
                raise RuntimeError("Playback requires the optional sounddevice package and PortAudio. "
                                   "See the README installation instructions.") from None
            stream = device.RawOutputStream(samplerate=source.getframerate(),
                                            channels=source.getnchannels(), dtype="int16")
            try:
                stream.start()
                remaining = source.getnframes()
                # At most 50 ms of audio per write, regardless of file size.
                chunk_frames = max(1, source.getframerate() // 20)
                while remaining:
                    check_cancelled(cancel)
                    frames = min(remaining, chunk_frames)
                    data = source.readframes(frames)
                    if len(data) != frames * source.getnchannels() * 2:
                        raise AudioError("The WAV file is truncated or incomplete.")
                    stream.write(data)
                    remaining -= frames
                    progress(1 - remaining / source.getnframes())
                check_cancelled(cancel)
                stream.stop()  # Drain the final buffered audio before completion.
            finally:
                try:
                    stream.abort()
                finally:
                    stream.close()


@dataclass(frozen=True)
class PlaybackState:
    status: str = "idle"
    progress: float = 0
    error: str = ""


class Playback:
    def __init__(self, adapter: PlaybackAdapter | None = None):
        self.adapter = adapter or SoundDevicePlayback()
        self._lock = RLock()
        self._state = PlaybackState()
        self._cancel = Event()
        self._thread: Thread | None = None
        self._closed = False

    def snapshot(self) -> PlaybackState:
        with self._lock:
            return self._state

    def play(self, audio: Path):
        with self._lock:
            if self._closed:
                raise RuntimeError("Playback is closed.")
            if self._thread and self._thread.is_alive():
                raise RuntimeError("Stop the current playback before starting another file.")
            self._cancel = Event()
            self._state = PlaybackState("playing")
            self._thread = Thread(target=self._run, args=(audio,), name="audio-playback", daemon=True)
            self._thread.start()

    def _progress(self, value: float):
        with self._lock:
            self._state = PlaybackState("playing", value)

    def _run(self, audio: Path):
        try:
            self.adapter.play(audio, self._cancel, self._progress)
            check_cancelled(self._cancel)
            state = PlaybackState("completed", 1)
        except Cancelled:
            state = PlaybackState("cancelled")
        except (AudioError, FileNotFoundError) as error:
            message = str(error) if isinstance(error, AudioError) else "Audio source is no longer available."
            state = PlaybackState("failed", error=message)
        except Exception:
            # Native/backend exception text may contain private paths or data.
            state = PlaybackState("failed", error="Playback failed. Check sounddevice, PortAudio and the output device.")
        with self._lock:
            if state.status == "completed" and self._cancel.is_set():
                state = PlaybackState("cancelled")
            self._state = state

    def stop(self):
        with self._lock:
            self._cancel.set()

    def close(self):
        with self._lock:
            self._closed = True
            self._cancel.set()

    def join(self, timeout: float | None = 2):
        if self._thread:
            self._thread.join(timeout)
