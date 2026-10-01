# Project instructions for local-whisper

## Purpose

Build a desktop application for Windows, macOS, and Linux (Debian and Arch) that plays audio files, transcribes them locally, and processes transcripts with a local LLM. The interface must also install and configure the required dependencies and models.

The repository starts empty. No language, framework, inference runtime, or storage format has been selected. Do not treat a technical choice as already approved. Prefer maintainable architecture and verify dependency compatibility on the target platforms before adopting it.

## Language

- English is the default application language.
- Use English for repository content, documentation, code identifiers, comments, commit messages, and contribution materials.
- Keep user-facing strings ready for future localization.
- Respond to the user in their preferred conversation language; this does not change the repository language.

## Required capabilities

- Import one or multiple audio files, play them, and transcribe them locally. Provide a processing queue and per-file status.
- Preserve the raw transcript directly produced by the speech recognition engine.
- Produce an intelligent transcript using a local LLM.
- Produce a structured report from the intelligent transcript while preserving the source versions.
- Copy, export, and delete transcripts.
- Keep a local history that persists across application restarts.
- Support live dictation: listen to the microphone, detect the end of a spoken segment, and transcribe once the user stops speaking. Also support manual stopping. Make the silence threshold configurable; do not require the entire session to end before transcribing.

## Modes and data preservation

1. **Raw transcription**: direct recognition engine output, without LLM rewriting.
2. **Intelligent transcription**: local post-processing that interprets punctuation, line breaks, lists, and obvious spoken formatting commands. Preserve meaning and do not add facts.
3. **Structured report**: an organized document derived from the intelligent transcript. Never replace either source transcript with this report.

Store versions separately with their provenance: audio source, engine and model, dates, and relevant parameters. Regeneration must not silently overwrite the original. Spoken commands apply to text formatting; they must not trigger system actions or deletion.

## Engines and models

- Use adapters to separate the interface, speech recognition, and LLM post-processing.
- Support Whisper-style engines and Parakeet 0.6B subject to verified runtime compatibility.
- The user mentioned "oruk/orukeet" on Hugging Face. Confirm the exact identifier and model family before integration. Do not invent repository identifiers or automatically classify these models as Whisper.
- Allow downloads of predefined, recommended, and custom speech recognition models, as well as local LLMs.
- Verify identifiers, formats, licenses, supported languages, and hardware requirements before publishing a model catalog or recommendations.
- Display download sizes and CPU, GPU, RAM, and disk requirements when known. Support CPU execution where the selected model allows it and detect available acceleration.
- Provide progress and cancellation for long downloads and processing tasks. Clearly report errors, incomplete downloads, and incompatible models.

## Installation and configuration through the interface

- Display dependency status and allow installation of packages required by the application.
- Isolate application-managed dependencies where possible; do not silently modify the machine's global environment.
- Allow users to download, select, and manage speech recognition models and LLMs.
- Provide a link to the official Hugging Face token creation page and an interface for configuring the token.
- Store the token in the operating system's secret store when available. Never expose it in history, logs, exports, or the repository. Allow replacement and removal.
- Explain which operations require network access. Transcription and LLM processing must work offline after dependencies and models are available.

## Interface and privacy

- Provide views for audio import and playback, dictation, transcripts and their versions, history, models, and settings.
- Keep the interface responsive during inference, installations, and downloads by running these tasks in the background.
- Display meaningful states: queued, downloading, loading model, listening, transcribing, post-processing, completed, cancelled, or failed.
- Keep audio and transcripts on the user's machine. Do not send them to remote services or enable telemetry containing their content.
- Make deletion scope explicit: transcript, derived versions, and any application-managed audio copy. Do not delete an imported source audio file without an explicit request.
- Provide keyboard navigation and accessible controls.

## Architecture and development

- Separate presentation, audio processing, model adapters, task orchestration, local storage, and dependency/model management.
- Avoid paths, shells, or package managers specific to one platform in shared code. Use appropriate application directories for each operating system.
- Version the storage schema and provide migrations that preserve history.
- Treat model outputs as untrusted data. The LLM must not execute transcribed content.
- Document technical decisions and actual development, test, and packaging commands once they exist. Do not invent commands for an absent stack.
- Work in usable increments, preserving the separation between raw and derived text from the first transcription workflow.

## Contribution workflow

- Follow standard contribution practices: focused changes, clear descriptions, consistent formatting, and validation proportional to the change.
- Read applicable repository instructions and inspect the working tree before editing. Preserve unrelated user changes and never overwrite them to simplify a task.
- Update documentation when behavior, setup, configuration, or public interfaces change. Never commit credentials, local audio, transcripts, downloaded models, or generated runtime data.
- The AI agent manages local commits for completed work. Use concise, descriptive English commit messages and stage only changes belonging to the task.
- Run relevant available checks before committing and report any failures or checks that could not run. Do not claim verification without evidence.
- Push only when the user explicitly requests it. Permission to edit or commit is not permission to push.
- Avoid destructive Git operations, history rewriting, or force pushes without explicit user authorization.
- When opening a pull request is requested, explain the resulting behavior, relevant validation, and material limitations.

## Verification

- Test critical behavior: original preservation, persistent history, export and deletion, task queues, errors, and cancellation.
- Test dictation segmentation with pauses, resumed speech, and manual session completion.
- Verify that intelligent transcription preserves meaning and structured reports do not invent information. Do not require exact text from a nondeterministic model.
- Use simulated adapters for routine tests to avoid downloading large models on every run. Separate integration tests requiring real models or specific hardware.
- Verify installation, startup, audio playback, microphone access, and packaging on Windows, macOS, Debian, and Arch. Report untested platforms rather than claiming compatibility without evidence.

## Decisions to resolve during implementation

- Exact initial model identifiers and inference runtimes.
- Desktop stack and distribution strategy for all four targets.
- Priority audio and export formats.
- Reference hardware, priority languages, and dictation latency expectations.
- Retention policy for audio copies and successive generated versions.

These decisions do not block project initialization. Resolve them before making implementation choices that depend on them.
