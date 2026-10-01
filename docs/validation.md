# Validation evidence — initial development preview

Date: 2026-10-01. Host: Windows, Python 3.12.6, Tk 8.6, SQLite 3.45.3.

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 16 tests passed |
| `python -m unittest tests.gui_smoke -v` | 2 native Tk tests passed |
| `python -m compileall -q local_whisper tests` | Passed |
| `python -m local_whisper --check` | Passed; reports unavailable inference and audio integrations |
| `python -m pip wheel --no-index --no-deps --no-build-isolation --wheel-dir .work/wheels .` | Built `local_whisper-0.1.0-py3-none-any.whl` |
| `git diff --cached --check` | Passed before commit |

Core tests exercise original text preservation, version lineage, regeneration,
restart persistence, provenance exports, overwrite protection, deletion without
audio loss, newer-schema refusal, settings, interrupted task recovery, serial
processing, cancellation of queued/active work, error handling without leaking
adapter exception text and shutdown. Segment tests exercise silence, short
pauses, resumed speech, manual flush and invalid timestamps.

Native Tk tests instantiate withdrawn windows and exercise the widget workflow:
import, queue, versions, copy, JSON export, settings and deletion. File dialogs
and deletion confirmation are simulated; the clipboard and Tk widgets are real.
They also verify that the ordinary preview disables simulated transcription.
These tests do not constitute visual or screen reader QA.

The first core test run caught a Windows file handle left open by a test's direct
SQLite connection. The test now closes that connection explicitly; the complete
suite passed after correction. The first wheel build was blocked by sandbox
permissions on pip's temporary directory. The authorized retry succeeded without
network access or dependency installation.
The final sandboxed core test rerun also encountered temporary-directory access
denials; the authorized rerun passed all 16 tests.

## Not verified

- macOS and Debian startup, installation and UI behavior.
- Arch distributions other than the Omarchy host documented below.
- Native desktop installers or installation of the generated wheel.
- Playback, microphone access or device permissions on any platform.
- Real ASR, local LLM output quality, offline model inference and acceleration.
- Model downloads, cancellation, dependency installers and operating system
  secret stores; these features have not been implemented.
- Manual visual layout, keyboard-only navigation and screen reader behavior.

Component availability was researched through official sources in
[the foundation decision](decisions/0001-foundation.md); application compatibility
must not be inferred from that availability alone.

## Omarchy startup correction

Date: 2026-10-01. Host: Omarchy 4.0.4 (Arch-based), Python 3.14.7,
Tk 8.6.16, SQLite 3.53.4.

The documented demo command initially failed with an `ImportError` for
`libtk8.6.so`. The Tkinter module existed, so the previous module-spec check
incorrectly reported it as available. Dependency status now imports Tkinter to
check native library loading without opening a window. Startup reports missing
Tk support or display access with actionable messages and a nonzero exit code.

Installed the system `tk` package and its `tcl` dependency through Omarchy's
package helper after system authentication. The 19 routine tests passed,
including regression tests for missing native libraries, missing Tkinter and
display failures. Compilation and `git diff --check` passed. `--check` reports
Tkinter as available after installation. Both native GUI smoke tests passed on
the desktop outside the sandbox; their initial sandbox run failed because it
could not connect to display `:0`.
