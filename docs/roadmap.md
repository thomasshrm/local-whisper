# Implementation roadmap

## Increment 1 — foundation

Implemented: desktop shell, local history, append-only versions, background
queue, explicit simulation, cancellation, export/deletion, dependency status,
segment boundary logic and tests. See validation evidence for actual checks.

## Increment 2 — verified audio and speech integration

1. Confirm target languages, reference CPU/GPU/RAM and latency expectations.
2. Verify exact Whisper-style and Parakeet 0.6B model/runtime combinations across
   Windows, macOS, Debian and Arch: identifiers, versions, licenses, formats,
   language support and hardware requirements. Clarify `oruk/orukeet` first.
3. Select a playback/decoder/capture stack, check its packaging and licenses,
   then implement PCM WAV playback and a first real offline transcription adapter.
4. Add progress reporting, bounded work history, model loading states, safe worker
   process isolation and per-model integration tests. Enforce one process per
   history database or coordinate recovery across processes.

## Increment 3 — local intelligent transcript and report

Verify and integrate a local LLM runtime. Treat source text and model responses
as untrusted data. Spoken formatting commands may alter formatting only.
Generate an intelligent version from a specific raw version and a report from
a specific intelligent version. Evaluate meaning preservation, omitted facts,
hallucinations, multilingual text and adversarial spoken instructions using
semantic checks rather than exact nondeterministic output matching.

## Increment 4 — live dictation

Connect a microphone and VAD adapter to the tested segmenter. Queue segments
as soon as silence ends a phrase, permit continued recording while recognition
runs, flush on manual stop and preserve segment audio provenance. Define bounded
buffers/maximum segment duration and cancellation under overload. Test device
permissions, pause/resume and latency on each target system.

## Increment 5 — dependency and model management

Create isolated, application-managed environments and a verified model catalog.
Add explicit network explanations, download size/resource requirements, progress,
cancellation, checksums, incomplete download handling and compatibility errors.
Store Hugging Face tokens through operating system secret-store adapters, with
replacement/removal and tests preventing leakage. Never fall back silently to
plaintext tokens or change the global Python environment.

## Release gates

Choose and test standalone packaging for all four targets; test startup, playback,
microphone permissions, offline inference, migration, accessibility and keyboard
navigation. Add CI for portable core tests and separate hardware/model integration
jobs. Resolve retention options, managed audio deletion and localization catalogs.
