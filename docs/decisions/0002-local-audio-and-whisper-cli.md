# 0002 — Optional PCM playback and a local whisper.cpp CLI adapter

Date: 2026-10-02. Status: adopted for the first real transcription slice.

## Decision and compatibility evidence

Use Python's WAV reader for uncompressed mono/stereo 16-bit PCM playback,
with optional `sounddevice==0.5.6` raw output streams in a worker thread.
No NumPy or decoding/conversion runtime is required. The package's
[release metadata](https://pypi.org/project/sounddevice/0.5.6/) declares Python
3.7+ and MIT licensing and provides Windows and macOS wheels plus a generic
Python wheel for Linux. The upstream
[installation guide](https://python-sounddevice.readthedocs.io/en/0.5.6/installation.html)
requires CFFI and explains PortAudio bundling on Windows/macOS and the system
runtime requirement on Linux. Packaging must account for those native libraries.

Run a user-selected native `whisper-cli` in a separate subprocess, without a
shell, using a local model and audio path. Initial speech input is mono 16-bit
PCM WAV at 16000 Hz; initial inference is CPU-only. This avoids Python bindings
coupled to interpreter-specific inference wheels and permits terminate/kill
cancellation. The upstream [whisper.cpp documentation](https://github.com/ggml-org/whisper.cpp)
lists Windows, macOS and Linux support and its WAV input constraints. Runtime
code is [MIT-licensed](https://github.com/ggml-org/whisper.cpp/blob/v1.9.4/LICENSE).
The [v1.9.4 CLI source](https://github.com/ggml-org/whisper.cpp/blob/v1.9.4/examples/cli/cli.cpp)
documents local model/input, language, CPU mode and text-output arguments used
by this adapter. This is component evidence, not application certification.

The initial integration fixture is `ggerganov/whisper.cpp`'s
`ggml-tiny-q5_1.bin`, a quantized multilingual Whisper model converted to GGML.
The [model card](https://huggingface.co/ggerganov/whisper.cpp) declares MIT,
approximately 31 MiB disk and SHA-1
`2827a03e495b1ed3048ef28a6a4620537db4ee51`. Model-specific memory and latency
requirements for the selected quantization are not established here. This is a
test fixture, not a recommended model catalog. `.en` models are English-only;
Whisper's multilingual family supports French (see the upstream
[Whisper languages](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py)).
Parakeet and the unresolved `oruk/orukeet` identifier are not integrated or
classified by this adapter.

## Boundaries and behavior

- `audio.py` validates PCM headers; streaming checks reject truncated data.
- `playback.py` owns bounded writes, output-device cleanup, progress and errors.
  The UI only polls immutable snapshots and sets cancellation flags.
- `speech.py` invokes the selected executable with no shell, no stdin and
  discarded diagnostics. Raw output comes from a unique temporary text file,
  preserving UTF-8 text and line endings. Arbitrary engine messages never enter
  history or application logs. The subprocess is reaped before temporary cleanup.
- `storage.py` stores only explicit engine/model paths and language settings;
  clearing configuration leaves those files intact. No schema change is needed.
- `tasks.py` freezes each queued task's adapter. Editing model settings applies
  to new tasks. Every successful regeneration still appends a separate version.

Provenance includes audio, model and executable SHA-256 hashes plus local paths,
language, audio parameters and CPU selection. Files are hashed before and after
inference to reject detected changes. Hashes identify executable bytes rather
than an asserted runtime version; associated shared libraries are not fingerprinted.
This check adds I/O and does not prevent an unrelated program from modifying
files and restoring them during processing.

## Limits and remaining work

Model compatibility is determined by the selected runtime during transcription;
file selection validates availability, not internal tensor architecture.
Choose the executable from a trusted source: it runs with the user's permissions.
The adapter itself uses no network; it is not an OS network sandbox for arbitrary
executables or modified runtimes. No arbitrary engine argument entry is provided.

Managed installation/downloads, hardware detection, other audio formats,
seeking/pause, precise inference loading/progress, LLMs, microphone/VAD and
standalone packaging remain pending. Native audio driver calls are in a thread
and require separate evaluation for hard shutdown guarantees. OS termination
can leave CLI temporary output behind; normal success/error/cancellation removes
it. GUI responsiveness/accessibility, integration and packaging must be checked
on every target system; a Linux run alone does not establish portability.
