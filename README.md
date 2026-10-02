# Local Whisper

A local desktop audio transcription application for Windows, macOS, Debian,
Ubuntu, Arch and Omarchy. This repository currently contains a **development preview**, not
a working speech recognition engine.

## Current increment

- English Tkinter desktop interface with Audio/queue, Transcripts, History,
  Dictation, Models and Settings views.
- Multiple audio imports stored as references to the original files.
- Serial background task queue with per-task status and cooperative cancellation.
- SQLite history with a versioned schema and immutable, separate raw,
  intelligent and report versions, parent links and engine/model provenance.
- Copy, UTF-8 text export, JSON export with provenance and explicit history
  deletion that keeps the original audio file. Exports require a new filename.
- Explicit `--demo` adapters for exercising the pipeline without downloading
  models. Simulated text is visibly labeled and recorded as simulated in provenance.
  The demo text adapter returns the input unchanged; it does not format a real
  intelligent transcript or generate a structured report.
- Tested segment boundary logic and a persistent silence threshold. No live
  microphone or VAD adapter is connected yet.
- One desktop instance per history, with an OS lock protecting active tasks from
  recovery by a second instance. Different history directories can open independently.
- GitHub Actions portable tests on Windows, macOS and Ubuntu with Python 3.11/3.14.
  The workflow has not yet been executed on GitHub.

**Not implemented yet:** real speech/LLM inference, audio playback, microphone
capture, dependency installation, model downloads/catalog, hardware detection,
secret-store token configuration and standalone desktop installers. The ordinary
preview disables inference actions. No model identifiers or runtime requirements
are asserted before verification.

## Run from the checkout

Requires Python 3.11+ with Tkinter and SQLite. The preview has no third-party
Python runtime dependencies. On Windows/macOS, use a Python installation with
Tk support. Debian provides `python3-tk`; Arch provides `tk`. These are system
prerequisites, not packages silently installed by the application. See
[the compatibility decision](docs/decisions/0001-foundation.md) for official sources.

Run these commands in the repository directory (`python3` may be the command
name on Linux/macOS):

```text
python -m local_whisper --check
python -m local_whisper
python -m local_whisper --demo
```

### Startup troubleshooting

If startup reports `No module named tkinter` or a missing native library such as
`libtk8.6.so`, install Tk support for the Python executable you are using.
On Omarchy, run `omarchy pkg add tk`; on Arch, run `sudo pacman -S --needed tk`;
on Debian, run `sudo apt install python3-tk`. These commands install system
packages and require administrator authentication. A Python virtual environment
alone does not supply the native Tk libraries.

Then run `python -m tkinter` to verify that a test window opens, and retry
`python -m local_whisper --demo`. Use `python3` instead if that is your Python
command. On Windows/macOS, use a Python installation that includes Tk support.

`--check` verifies that Tkinter and its native libraries can be imported without
opening a window. It does not verify access to a graphical display. If startup
reports that it cannot open the desktop window, run it from a graphical desktop
session; a headless terminal does not provide a display for this application.

### Demo workflow

To keep development data in an ignored repository directory:

```text
python -m local_whisper --demo --data-dir .work/demo
```

In demo mode: import an audio file, select it, queue a simulated transcription,
then open its History entry. Select a raw version to simulate an intelligent
version, and an intelligent version to simulate a report. Repeat operations to
create additional versions. File import currently records the path only; format
validation/decoding will belong to the real audio adapter.

`Ctrl+O` imports files. `Tab` navigates controls; `Enter` opens the selected
history entry. Use the Copy button for a whole version; text selection supports
the native copy shortcut. Accessibility and screen reader behavior still require
manual testing on each target system.

## Development and validation

```text
python -m unittest discover -s tests -v
python -m compileall -q local_whisper tests
python -m unittest tests.gui_smoke -v
```

The last command is opt-in and requires a graphical desktop with working Tk.
The normal test suite uses simulated adapters, temporary data and no network.
No real model integration tests are available yet.

The project has setuptools package metadata and a `local-whisper` GUI entry
point. For an optional isolated editable installation, create a virtual
environment and run its Python executable with `-m pip install -e .`. Build
dependencies may require network access. Native installer packaging has not
been selected or validated; running from source is the initial distribution.

With setuptools and wheel already installed, build a Python wheel without network:

```text
python -m pip wheel --no-index --no-deps --no-build-isolation --wheel-dir .work/wheels .
```

This wheel is a Python package, not a standalone desktop installer, and still
requires a Python installation with Tk.

## Local data and privacy

Default history locations:

| System | Directory |
| --- | --- |
| Windows | `%LOCALAPPDATA%/LocalWhisper` |
| macOS | `~/Library/Application Support/LocalWhisper` |
| Linux | `$XDG_DATA_HOME/local-whisper` or `~/.local/share/local-whisper` |

Audio is never copied or deleted by this increment. Transcript versions are kept
until their entire history entry is explicitly deleted. Plain text exports
contain the selected text; JSON also includes the local source path and
provenance. Keep exported files private as needed.

No telemetry or remote inference is implemented. The Hugging Face settings link
opens the official token creation page in the browser and requires network
access. This preview never accepts or stores a token. SQLite is not encrypted;
use your operating system's user account and disk protection for local history.

The desktop refuses a second application process for the same history database
with a visible message. The lock is released by the OS if the process exits;
the empty `history.sqlite3.lock` sidecar is kept and must not be removed while
the application is running. Use local storage for history; network filesystem
locking has not been validated. Direct library consumers must also acquire
`history_instance` before opening storage and starting a task queue.

Shutdown requests cancellation and retains history ownership until the worker
exits. An adapter must observe cancellation to terminate promptly; hard
process isolation for unresponsive runtimes is a future task. Interrupted tasks
are marked failed on the next startup and are never automatically retried.

## Architecture and next steps

See [the foundation decision](docs/decisions/0001-foundation.md),
[the implementation roadmap](docs/roadmap.md) and
[validation evidence](docs/validation.md). Interfaces, storage, engine adapters,
orchestration, audio segmentation and management status live in separate modules.

The roadmap includes a dedicated GitHub Actions build and release increment for
downloadable Windows/macOS binaries and Debian/Ubuntu/Arch packages, with Omarchy
validation. Standalone packaging and release publication are still pending; the
current CI only runs tests. Its matrix follows the official
[GitHub Python CI guidance](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).
