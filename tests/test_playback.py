import tempfile
import unittest
import wave
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from local_whisper.adapters import Cancelled
from local_whisper.audio import AudioError, pcm_wav
from local_whisper.playback import Playback, SoundDevicePlayback


def write_wav(path, *, rate=16000, channels=1, width=2, frames=1600):
    with wave.open(str(path), "wb") as file:
        file.setnchannels(channels)
        file.setsampwidth(width)
        file.setframerate(rate)
        file.writeframes(b"\x01\x00" * (frames * channels * width // 2))


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.audio = Path(self.temp.name) / "source.wav"
        write_wav(self.audio)

    def test_pcm_formats_and_speech_requirements(self):
        with pcm_wav(self.audio, speech=True) as source:
            self.assertEqual(source.getnframes(), 1600)
        write_wav(self.audio, channels=2)
        with pcm_wav(self.audio, speech=True) as source:
            self.assertEqual(source.getnchannels(), 2)
        for settings in ({"rate": 44100},):
            write_wav(self.audio, **settings)
            with pcm_wav(self.audio):
                pass
            with self.assertRaises(AudioError):
                with pcm_wav(self.audio, speech=True):
                    pass
        for settings in ({"width": 1}, {"frames": 0}, {"channels": 3}):
            write_wav(self.audio, **settings)
            with self.assertRaises(AudioError):
                with pcm_wav(self.audio):
                    pass
        self.audio.write_bytes(b"not a WAV")
        with self.assertRaises(AudioError):
            with pcm_wav(self.audio):
                pass

    def test_streams_bounded_chunks_and_closes_output(self):
        write_wav(self.audio, channels=2, frames=2000)
        original = self.audio.read_bytes()
        stream = Mock()
        device = SimpleNamespace(RawOutputStream=Mock(return_value=stream))
        progress = []
        with patch("local_whisper.playback.importlib.import_module", return_value=device):
            SoundDevicePlayback().play(self.audio, Event(), progress.append)
        chunks = [call.args[0] for call in stream.write.call_args_list]
        self.assertEqual(len(b"".join(chunks)), 8000)
        self.assertLessEqual(max(map(len, chunks)), 3200)
        self.assertEqual(progress[-1], 1)
        stream.start.assert_called_once()
        stream.stop.assert_called_once()
        stream.close.assert_called_once()
        self.assertEqual(self.audio.read_bytes(), original)

    def test_cancel_aborts_stream_without_draining(self):
        cancel = Event()
        stream = Mock()
        stream.write.side_effect = lambda data: cancel.set()
        device = SimpleNamespace(RawOutputStream=Mock(return_value=stream))
        with patch("local_whisper.playback.importlib.import_module", return_value=device):
            with self.assertRaises(Cancelled):
                SoundDevicePlayback().play(self.audio, cancel, lambda value: None)
        stream.stop.assert_not_called()
        stream.abort.assert_called_once()
        stream.close.assert_called_once()

    def test_truncated_file_is_rejected_and_output_closed(self):
        self.audio.write_bytes(self.audio.read_bytes()[:-4])
        stream = Mock()
        device = SimpleNamespace(RawOutputStream=Mock(return_value=stream))
        with patch("local_whisper.playback.importlib.import_module", return_value=device):
            with self.assertRaisesRegex(AudioError, "truncated"):
                SoundDevicePlayback().play(self.audio, Event(), lambda value: None)
        stream.close.assert_called_once()

    def test_background_stop_busy_guard_and_restart(self):
        entered = Event()

        class WaitingAdapter:
            def play(self, audio, cancel, progress):
                progress(0.5)
                entered.set()
                if not cancel.wait(3):
                    raise RuntimeError("Test timed out")
                raise Cancelled()

        player = Playback(WaitingAdapter())
        self.addCleanup(player.join)
        self.addCleanup(player.close)
        player.play(self.audio)
        self.assertTrue(entered.wait(2))
        self.assertEqual(player.snapshot().progress, 0.5)
        with self.assertRaises(RuntimeError):
            player.play(self.audio)
        player.stop()
        player.join()
        self.assertEqual(player.snapshot().status, "cancelled")
        player.adapter = SimpleNamespace(play=lambda *args: None)
        player.play(self.audio)
        player.join()
        self.assertEqual(player.snapshot().status, "completed")
        player.close()
        with self.assertRaises(RuntimeError):
            player.play(self.audio)

    def test_backend_error_does_not_leak_private_details(self):
        adapter = Mock()
        adapter.play.side_effect = RuntimeError("private-token-and-audio-path")
        player = Playback(adapter)
        player.play(self.audio)
        player.join()
        self.assertEqual(player.snapshot().status, "failed")
        self.assertNotIn("private-token", player.snapshot().error)
