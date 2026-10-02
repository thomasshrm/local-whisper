# Local Whisper

A local desktop audio transcription application for Windows, macOS, Debian,
Ubuntu, Arch and Omarchy. This repository contains a **development preview**
with PCM WAV playback and a first local Whisper transcription adapter.

## Current increment

- English Tkinter desktop interface with Audio/queue, Transcripts, History,
  Dictation, Models and Settings views.
- Multiple audio imports stored as references to the original files.
- Background PCM WAV playback with stop, progress and safe device errors.
- Offline CPU transcription through a user-selected local `whisper-cli`
  executable and Whisper GGML model. Configuration is persistent and queued tasks
  keep their original model selection. Raw text is preserved exactly, with file
  hashes and audio/engine/model parameters in provenance.
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

**Not implemented yet:** local LLM inference, microphone
capture, dependency installation, model downloads/catalog, hardware detection,
secret-store token configuration and standalone desktop installers. The ordinary
preview enables real transcription after a local speech configuration is applied.
Intelligent transcripts and reports remain simulation-only in demo mode.

## Run from the checkout

Requires Python 3.11+ with Tkinter and SQLite. History and demo mode have no
third-party Python runtime dependencies; playback is an optional extra.
On Windows/macOS, use a Python installation with
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

### Audio playback

Create an isolated environment with `python -m venv .venv`. Install the playback
extra using that environment's Python executable:

```text
python -m pip install -e ".[playback]"
```

Use `.venv/bin/python` on Linux/macOS or `.venv\Scripts\python.exe` on Windows
in place of `python` above, and to start the application. Installation downloads
Python dependencies; playback itself works offline. The pinned `sounddevice`
package uses PortAudio and does not need NumPy for this implementation.
Windows/macOS pip wheels supply PortAudio; Linux needs the distribution's
PortAudio runtime. See the [audio/runtime decision](docs/decisions/0002-local-audio-and-whisper-cli.md).
The application never installs global dependencies automatically.

Import and select a mono/stereo, uncompressed **16-bit PCM WAV** file, then use
**Play selected audio** and **Stop playback**. Audio streams in bounded chunks
on a worker thread. Progress indicates frames submitted to the device; completed
means the final device buffer has drained. Seeking and pause are pending.

### Real offline transcription

Obtain a trusted native `whisper-cli` executable from the official
[whisper.cpp project](https://github.com/ggml-org/whisper.cpp), with any native
libraries it requires, and a local Whisper model in that runtime's GGML format.
Setup may require network access; the application only passes local file paths
and never invokes a downloader or remote inference endpoint.

In **Models**, select the executable and model, enter `auto` or a Whisper
language code (`en`, `fr`, etc.), then apply the configuration. Select a **mono
16-bit PCM WAV at 16000 Hz**, queue a local transcription, and open its History
entry to view/copy/export the raw version. Use a multilingual model for language
auto detection or French; `.en` models are English-only. Unsupported model
formats/languages produce a task error. Models are not copied or deleted by
removing the configuration. MP3/FLAC/M4A/OGG decoding is pending.

Cancellation terminates the CLI process and discards its partial transcript.
Temporary CLI output is removed at normal completion or cancellation. Abrupt OS
termination can leave private temporary output in the OS temporary directory.
Do not change engine, model or audio files while processing: their SHA-256 hashes
are checked before and after inference. This adds disk I/O for large models.
Task states currently provide coarse activity, including engine model loading
within the transcription phase; no inference percentage or latency guarantee is
reported. CPU is the initial mode; acceleration detection/configuration is pending.

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
create additional versions. Demo mode ignores the saved speech configuration.
Import records a path; real playback/transcription validate PCM WAV in the worker.

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
Opt-in integration checks are separate from the normal suite:

```text
python -m unittest tests.playback_integration -v
python -m unittest tests.speech_integration -v
```

Playback integration requires the playback extra and an output device; it writes
only short silent WAV audio and never opens a microphone. Speech integration
requires `LOCAL_WHISPER_CLI`, `LOCAL_WHISPER_MODEL` and `LOCAL_WHISPER_AUDIO`
environment variables pointing to existing local files. The audio must contain
speech in the supported WAV format. Optionally set `LOCAL_WHISPER_LANGUAGE`
(defaults to `auto`). Without those paths, the speech test is skipped. Neither
test downloads dependencies/models. See validation evidence for tested versions.

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
exits. The whisper.cpp adapter runs in a separate process with terminate/kill
cancellation. Other future adapters must also support prompt shutdown; native
audio-device calls are not currently isolated in a process. Interrupted tasks
are marked failed on the next startup and are never automatically retried.

## Architecture and next steps

See [the foundation decision](docs/decisions/0001-foundation.md),
[the audio/runtime decision](docs/decisions/0002-local-audio-and-whisper-cli.md),
[the implementation roadmap](docs/roadmap.md) and
[validation evidence](docs/validation.md). Interfaces, storage, engine adapters,
orchestration, audio segmentation and management status live in separate modules.

The roadmap includes a dedicated GitHub Actions build and release increment for
downloadable Windows/macOS binaries and Debian/Ubuntu/Arch packages, with Omarchy
validation. Standalone packaging and release publication are still pending; the
current CI only runs tests. Its matrix follows the official
[GitHub Python CI guidance](https://docs.github.com/en/actions/tutorials/build-and-test-code/python).
