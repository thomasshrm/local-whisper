"""Local whisper.cpp CLI adapter. No shells, downloads or remote inference."""

import hashlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from .adapters import check_cancelled
from .audio import AudioError, pcm_wav
from .domain import Result


class SpeechError(RuntimeError):
    """Known safe diagnostics; never include arbitrary subprocess output."""


@dataclass(frozen=True)
class WhisperConfig:
    executable: Path
    model: Path
    language: str = "auto"

    def validate(self):
        if not self.executable.is_file() or not os.access(self.executable, os.X_OK):
            raise ValueError("Select an executable whisper-cli file.")
        if self.executable.suffix.lower() in (".bat", ".cmd"):
            raise ValueError("Select the native whisper-cli executable, not a shell script.")
        if not self.model.is_file() or self.model.stat().st_size == 0:
            raise ValueError("Select a nonempty local Whisper model in whisper.cpp GGML format.")
        if self.language != "auto" and not re.fullmatch(r"[a-z]{2,3}", self.language):
            raise ValueError("Use auto or a Whisper language code such as en or fr.")


def file_digest(path: Path, cancel: Event) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            check_cancelled(cancel)
            digest.update(chunk)
    check_cancelled(cancel)
    return digest.hexdigest()


class WhisperCppSpeech:
    def __init__(self, config: WhisperConfig):
        # Freeze absolute paths so cwd changes cannot select a different engine.
        self.config = WhisperConfig(config.executable.resolve(), config.model.resolve(), config.language)

    def transcribe(self, audio: Path, cancel: Event) -> Result:
        check_cancelled(cancel)
        self.config.validate()
        audio = audio.resolve(strict=True)
        with pcm_wav(audio, speech=True) as source:
            # Validate all declared frames in bounded chunks before invoking native code.
            remaining = source.getnframes()
            while remaining:
                check_cancelled(cancel)
                count = min(remaining, 16000)
                if len(source.readframes(count)) != count * 2:
                    raise AudioError("The WAV file is truncated or incomplete.")
                remaining -= count
        model_digest = file_digest(self.config.model, cancel)
        engine_digest = file_digest(self.config.executable, cancel)
        audio_digest = file_digest(audio, cancel)
        with tempfile.TemporaryDirectory(prefix="local-whisper-") as directory:
            output = Path(directory) / "raw"
            command = [str(self.config.executable), "-m", str(self.config.model),
                       "-f", str(audio), "-l", self.config.language, "-ng",
                       "-otxt", "-of", str(output), "-np"]
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            # Raw transcript comes only from the output file. Discard diagnostics
            # instead of logging transcripts or accumulating unbounded pipe data.
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       shell=False, cwd=directory, **options)
            try:
                while process.poll() is None:
                    check_cancelled(cancel)
                    cancel.wait(0.05)
                check_cancelled(cancel)
                if process.returncode != 0:
                    raise SpeechError("Whisper transcription failed. Check the executable, model format and language.")
                transcript = output.with_suffix(".txt")
                if not transcript.is_file():
                    raise SpeechError("The speech engine produced no transcript file. Check whisper-cli compatibility.")
                # Preserve whitespace, punctuation and newline bytes, decoded as UTF-8.
                with transcript.open(encoding="utf-8", newline="") as file:
                    text = file.read()
                # Detect replacement during processing before recording provenance.
                if (model_digest != file_digest(self.config.model, cancel)
                        or engine_digest != file_digest(self.config.executable, cancel)
                        or audio_digest != file_digest(audio, cancel)):
                    raise SpeechError("An input or engine file changed during transcription. Queue a new task.")
                return Result(text, "whisper.cpp", self.config.model.name,
                              {"language": self.config.language, "device": "cpu",
                               "model_sha256": model_digest, "engine_sha256": engine_digest,
                               "audio_sha256": audio_digest, "executable": str(self.config.executable),
                               "model_path": str(self.config.model), "sample_rate": 16000,
                               "channels": 1, "sample_width": 2, "output": "whisper-cli text"})
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
