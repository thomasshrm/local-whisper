"""Engine boundaries. Demo adapters do not recognize speech or run an LLM."""

from pathlib import Path
from threading import Event
from typing import Protocol

from .domain import Kind, Result


class Cancelled(Exception):
    pass


def check_cancelled(cancel: Event):
    if cancel.is_set():
        raise Cancelled()


class SpeechAdapter(Protocol):
    def transcribe(self, audio: Path, cancel: Event) -> Result: ...


class TextAdapter(Protocol):
    def process(self, text: str, kind: Kind, cancel: Event) -> Result: ...


class UnconfiguredSpeech:
    def transcribe(self, audio: Path, cancel: Event) -> Result:
        raise RuntimeError("No speech engine is configured. Use --demo to test the workflow.")


class UnconfiguredText:
    def process(self, text: str, kind: Kind, cancel: Event) -> Result:
        raise RuntimeError("No local LLM is configured. Use --demo to test the workflow.")


class DemoSpeech:
    def transcribe(self, audio: Path, cancel: Event) -> Result:
        if not audio.is_file():
            raise FileNotFoundError("Audio source is no longer available.")
        if cancel.wait(0.3):
            raise Cancelled()
        return Result("[DEMO — simulated output; audio was not transcribed.]\n"
                      "This sample verifies local history and transcript versions.",
                      "demo-speech", "simulation", {"simulated": True})


class DemoText:
    def process(self, text: str, kind: Kind, cancel: Event) -> Result:
        if cancel.wait(0.3):
            raise Cancelled()
        # Identity transformation: no invented facts or interpreted system commands.
        return Result(text, "demo-text", "identity", {"simulated": True, "operation": kind.value})
