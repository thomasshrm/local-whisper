"""Startup diagnostics must work even when native Tk is unavailable."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

from local_whisper.__main__ import main
from local_whisper.management import tkinter_status
from local_whisper.instance import HistoryInUse, history_instance


class StartupTests(unittest.TestCase):
    def test_second_instance_does_not_open_or_recover_history(self):
        root = Mock()
        dialog = Mock()
        tk = SimpleNamespace(Tk=Mock(return_value=root), TclError=RuntimeError,
                             messagebox=SimpleNamespace(showerror=dialog))
        with tempfile.TemporaryDirectory() as directory:
            with history_instance(Path(directory) / "history.sqlite3"), \
                    patch.dict(sys.modules, {"tkinter": tk,
                                             "local_whisper.ui": SimpleNamespace(Application=Mock())}), \
                    patch.object(sys, "argv", ["local_whisper", "--data-dir", directory]), \
                    patch("local_whisper.__main__.Store") as store, \
                    patch("local_whisper.__main__.TaskQueue") as queue:
                self.assertEqual(main(), 1)
                store.assert_not_called()
                queue.assert_not_called()
        dialog.assert_called_once()
        root.destroy.assert_called_once()

    def test_shutdown_waits_for_worker_before_releasing_history(self):
        root = Mock()
        tk = SimpleNamespace(Tk=Mock(return_value=root), TclError=RuntimeError)
        with tempfile.TemporaryDirectory() as directory:
            def check_ownership(timeout):
                self.assertIsNone(timeout)
                with self.assertRaises(HistoryInUse):
                    with history_instance(Path(directory) / "history.sqlite3"):
                        pass

            with patch.dict(sys.modules, {"tkinter": tk,
                                          "local_whisper.ui": SimpleNamespace(Application=Mock())}), \
                    patch.object(sys, "argv", ["local_whisper", "--data-dir", directory]), \
                    patch("local_whisper.__main__.Store"), \
                    patch("local_whisper.__main__.TaskQueue") as queue:
                queue.return_value.join.side_effect = check_ownership
                main()
                queue.return_value.close.assert_called_once()
                queue.return_value.join.assert_called_once_with(timeout=None)
            with history_instance(Path(directory) / "history.sqlite3"):
                pass
        root.destroy.assert_called_once()

    def test_missing_native_library_is_not_reported_as_available(self):
        error = ImportError("libtk8.6.so: cannot open shared object file")
        with patch("local_whisper.management.importlib.import_module", side_effect=error):
            self.assertIn("libtk8.6.so", tkinter_status())
            output = io.StringIO()
            with patch.object(sys, "argv", ["local_whisper", "--check"]), redirect_stdout(output):
                main()
            self.assertTrue(json.loads(output.getvalue())["Tkinter"].startswith("unavailable:"))

    def test_demo_missing_tk_exits_cleanly_before_creating_history(self):
        output = io.StringIO()
        with patch.dict(sys.modules, {"tkinter": None}), \
                patch.object(sys, "argv", ["local_whisper", "--demo"]), \
                patch("local_whisper.__main__.Store") as store, redirect_stderr(output):
            self.assertEqual(main(), 1)
            store.assert_not_called()
        self.assertIn("Install Tk support", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_display_failure_exits_cleanly_before_creating_history(self):
        class DisplayError(Exception):
            pass

        def no_display():
            raise DisplayError("no display name")

        tk = SimpleNamespace(Tk=no_display, TclError=DisplayError)
        output = io.StringIO()
        with patch.dict(sys.modules, {"tkinter": tk}), \
                patch.object(sys, "argv", ["local_whisper", "--demo"]), \
                patch("local_whisper.__main__.Store") as store, redirect_stderr(output):
            self.assertEqual(main(), 1)
            store.assert_not_called()
        self.assertIn("graphical desktop session", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())
