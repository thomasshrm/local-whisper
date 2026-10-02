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

## Not verified at the initial preview stage

Later sections record subsequent checks; this list describes the initial preview.

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

## History ownership and CI follow-up

Date: 2026-10-02. Host: Omarchy 4.0.4, Python 3.14.7, SQLite 3.53.4.

- All 24 routine tests passed. New tests use actual child processes to verify
  rejection of concurrent history ownership, release after normal exit and
  abrupt process exit, and independent history directories. Startup regressions
  verify that a refused instance never opens storage or starts task recovery,
  and that the history lock remains held while waiting for worker shutdown.
- Both native Tk smoke tests passed outside the sandbox. The sandbox attempt
  failed with `couldn't connect to display ":0"`; the approved retry could access
  the desktop. These checks do not constitute manual visual/accessibility QA.
- Compilation, `--check` and whitespace checks passed.
- The CI YAML parsed with the locally available PyYAML, with six OS/Python
  matrix combinations and read-only repository permissions. No GitHub Actions
  run or workflow-specific linter has been executed here. Remote Windows/macOS
  tests, binary packaging and release publication remain unverified.

This increment does not select an inference runtime or packaging tool. The new
release roadmap explicitly covers Windows, macOS, Debian/Ubuntu and Arch/Omarchy.

## First real PCM audio and Whisper transcription

Date: 2026-10-02. Host: Omarchy 4.0.4 x86-64, Python 3.14.7, SQLite 3.53.4.

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests -v` | 37 routine tests passed |
| `python -m unittest tests.gui_smoke -v` | 3 native Tk tests passed outside sandbox |
| `.work/dev-env/bin/python -m unittest tests.playback_integration -v` | 2 real default-output stream tests passed outside sandbox |
| `python -m unittest tests.speech_integration -v` with local paths configured | 1 real CPU transcription/history/export/deletion test passed inside sandbox |
| Compilation, dependency diagnostics, `git diff --check` | Passed |

Installed the editable playback extra in `.work/dev-env`, with
`sounddevice==0.5.6`, CFFI 2.1.1 and pycparser 3.0. The existing host PortAudio
runtime loaded; no system packages were installed. Device enumeration and
native output required approved access outside the sandbox. Output tests used
250 ms of silence; successful device streaming is not evidence of audible
quality, volume behavior or compatibility with every device.

Downloaded the official whisper.cpp v1.9.4 source archive and built the CLI with
CMake 4.4.3 / GNU 16.2.1. Build configuration disabled CURL, GPU backends and
shared libraries. The CLI reports `1.9.4-dev` for this tagged source build.
Upstream compilation emitted CMake deprecation and timestamp-format truncation
warnings but completed successfully. The x86 CPU build enables AVX2 and related
instructions; it is a host integration fixture, not a portable release binary.

The integration model was `ggerganov/whisper.cpp`'s `ggml-tiny-q5_1.bin`,
32,152,673 bytes. Its SHA-1 matched the official model card:
`2827a03e495b1ed3048ef28a6a4620537db4ee51`. Recorded SHA-256:
`818710568da3ca15689e31a743197b520007872ff9576237bda97bd1b469c3d7`.
Used the upstream `samples/jfk.wav` with `en`, inside the network-restricted
sandbox after download/build. The complete test took about 1.75 seconds here;
this is neither an inference benchmark nor a latency guarantee. Runtime/model
files remain ignored under `.work`; no personal audio was used or uploaded.

The routine CLI tests use a simulated engine in real child processes. They
exercise exact UTF-8/CRLF/whitespace preservation, raw regeneration, persistent
configuration, frozen queued model selection, truncated/unsupported WAV input,
failed/missing output, changed model rejection, cancellation with child reaping,
and temporary transcript cleanup. Export tests ensure newline preservation as
well. Playback tests cover bounded writes, device cleanup, cancellation,
completion, busy/closed guards, restart and safe backend errors. Native widget
tests exercise the new configuration, removal and playback controls with a fake
output adapter; the real stream tests are separate.

Remaining unverified: Windows/macOS/Debian/Ubuntu execution of these adapters,
native distribution packages, multilingual accuracy (including French), model
resource requirements, GPU execution, precise loading/progress, audible output
quality, microphone/VAD, real LLM post-processing and unattended dependency/model
installation. GitHub CI has not run remotely. Source compatibility evidence is
recorded in [the audio/runtime decision](decisions/0002-local-audio-and-whisper-cli.md).

### Reproducing the local integration fixture on Linux

The following build commands were used after extracting the official v1.9.4
archive under `.work` and installing CMake in the development environment:

```sh
.work/dev-env/bin/cmake -S .work/whisper.cpp-1.9.4 -B .work/whisper-build -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF -DWHISPER_CURL=OFF -DGGML_NATIVE=OFF -DGGML_CUDA=OFF -DGGML_METAL=OFF -DGGML_BLAS=OFF -DGGML_CCACHE=OFF -DBUILD_SHARED_LIBS=OFF
.work/dev-env/bin/cmake --build .work/whisper-build --target whisper-cli --parallel 2
LOCAL_WHISPER_CLI=.work/whisper-build/bin/whisper-cli LOCAL_WHISPER_MODEL=.work/ggml-tiny-q5_1.bin LOCAL_WHISPER_AUDIO=.work/whisper.cpp-1.9.4/samples/jfk.wav LOCAL_WHISPER_LANGUAGE=en .work/dev-env/bin/python -m unittest tests.speech_integration -v
```

These are host integration commands, not Windows/macOS packaging instructions.
