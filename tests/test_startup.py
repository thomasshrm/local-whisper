"""Startup diagnostics must work even when native Tk is unavailable."""

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from local_whisper.__main__ import main
from local_whisper.management import tkinter_status


class StartupTests(unittest.TestCase):
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
