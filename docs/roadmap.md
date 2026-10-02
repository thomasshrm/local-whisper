# Implementation roadmap

## Increment 1 — foundation

Implemented: desktop shell, local history, append-only versions, background
queue, explicit simulation, cancellation, export/deletion, dependency status,
segment boundary logic and tests. See validation evidence for actual checks.

Follow-up implemented: one application instance per history, held through worker
shutdown to protect active tasks from another process's recovery; portable core
CI on Windows, macOS and Ubuntu with Python 3.11 and 3.14. CI runs still need to be
observed on GitHub; they do not validate desktop packaging or hardware.

## Increment 2 — verified audio and speech integration

Implemented first slice: optional `sounddevice` PCM WAV playback with progress
and cancellation; local whisper.cpp CLI configuration in Models; CPU transcription
of mono/stereo 16 kHz/16-bit PCM WAV; process termination on cancellation; exact raw
text/provenance preservation and immutable queued model selection. Local speech
and audio integration tests are separate from routine simulated tests. See
[the runtime decision](decisions/0002-local-audio-and-whisper-cli.md) and validation
evidence for compatibility sources and actual platform checks.

Remaining:

1. Confirm target languages, reference CPU/GPU/RAM and latency expectations.
2. Extend verification of Whisper-style and Parakeet 0.6B model/runtime combinations across
   Windows, macOS, Debian and Arch: identifiers, versions, licenses, formats,
   language support and hardware requirements. Clarify `oruk/orukeet` first.
3. Add decoding/conversion for other formats after license and packaging checks;
   evaluate microphone capture and VAD separately. Confirm reference languages,
   hardware and latency before recommending models or acceleration settings.
4. Add inference progress reporting, bounded work history, precise model loading
   states and further per-model integration tests. History ownership is now
   enforced by the desktop entry point; keep it across future worker processes.

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

## Increment 6 — GitHub Actions binary builds and downloadable releases

1. Select and verify standalone packaging after the multimedia and inference
   runtimes are chosen. Publish the supported OS versions and CPU architectures;
   do not assume one Linux build works on every distribution.
2. Add a GitHub Actions build matrix for downloadable Windows executables or
   installers, macOS app bundles/installers, Debian/Ubuntu packages and Arch
   packages. Cover Omarchy explicitly with installation and desktop validation
   of the Arch package. Final package formats remain to be verified.
3. Build on native runners or suitable isolated distribution environments. Pin
   build dependencies, include required native libraries and license notices,
   and keep audio, transcripts, tokens and downloaded models out of artifacts.
4. Upload intermediate build artifacts for review. On version tags, verify
   package versions, run installation/startup checks, produce checksums and
   attach the validated binaries to a draft GitHub Release with installation
   instructions and known limitations. Grant release write permission only to
   the publication job. Separate artifact production from final publication.
5. Decide Windows signing and macOS signing/notarization, configure credentials
   as protected GitHub secrets, and document unsigned preview limitations until
   signing is available. Test upgrades and uninstall behavior without losing
   local history, and cancellation/offline use in installed builds.

The current `.github/workflows/ci.yml` is the first automation step: portable
tests only. It neither generates standalone binaries nor publishes releases.
No release workflow has been executed and no packages are currently available.

## Release gates

Choose and test standalone packaging for Windows, macOS, Debian, Ubuntu, Arch and
Omarchy; test startup, playback,
microphone permissions, offline inference, migration, accessibility and keyboard
navigation. Extend portable core CI with desktop, distribution and separate
hardware/model integration jobs. Resolve retention options, managed audio deletion
and localization catalogs.
