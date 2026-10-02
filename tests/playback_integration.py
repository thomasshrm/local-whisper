"""Opt-in output-device checks using silent audio; never open a microphone."""

import tempfile
import unittest
import wave
from pathlib import Path
from threading import Event

from local_whisper.adapters import Cancelled
from local_whisper.playback import SoundDevicePlayback


class PlaybackIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.audio = Path(self.temp.name) / "silence.wav"
        with wave.open(str(self.audio), "wb") as file:
            file.setnchannels(1)
            file.setsampwidth(2)
            file.setframerate(16000)
            file.writeframes(b"\x00\x00" * 4000)

    def test_default_output_stream_completes(self):
        progress = []
        SoundDevicePlayback().play(self.audio, Event(), progress.append)
        self.assertEqual(progress[-1], 1)

    def test_cancel_closes_real_output_stream(self):
        cancel = Event()
        with self.assertRaises(Cancelled):
            SoundDevicePlayback().play(self.audio, cancel, lambda value: cancel.set())
