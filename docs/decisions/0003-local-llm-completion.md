# 0003 — Experimental local llama.cpp completion adapter

Date: 2026-10-02. Status: adopted as an experimental adapter; real runtime/model
validation and recommendations remain pending.

## Decision and component compatibility evidence

LLM use is strictly optional. Raw transcription, playback, history, copy and
export never depend on a configured or running LLM. No model is installed or
loaded at startup; saved settings only construct an adapter. Inference starts
only for an explicitly requested intelligent version or report, never after raw
transcription automatically. No minimum model size or >1B model is prescribed.

Use a user-selected native `llama-completion` executable with local GGUF models,
without Python inference bindings. The upstream
[completion documentation](https://github.com/ggml-org/llama.cpp/tree/master/tools/completion)
and [argument definitions](https://github.com/ggml-org/llama.cpp/blob/master/common/arg.cpp)
provide local file input, offline mode, CPU device selection, token limits,
JSON-schema constrained generation, disabled conversation/prompt display,
disabled escaping and context shifting. The
[completion implementation](https://github.com/ggml-org/llama.cpp/blob/master/tools/completion/completion.cpp)
prints generated output and a fixed end-of-text marker. Accept that marker only
after a complete JSON document; reject other trailing output. These sources
were checked on this date; no upstream binary version is certified here.

The [build documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)
covers Windows, macOS and Linux, including CPU builds. The runtime is
[MIT-licensed](https://github.com/ggml-org/llama.cpp/blob/master/LICENSE).
This supports choosing a subprocess boundary across target platforms, not a
claim that this application integration has been tested on them. GGUF model
licenses, architectures, languages, RAM and disk requirements vary independently.
No specific model is adopted or recommended in this increment.

Recent `llama-cli` uses a different interface. Select the completion tool.
The application does not build, install or download either runtime or model.

## Behavior and preservation

`text.py` owns configuration, operation-specific prompts and native processing.
Raw-to-intelligent formatting preserves meaning and source language by instruction;
intelligent-to-report generation organizes facts and uncertainty. The source is
quoted as a JSON string with instructions to treat embedded commands as data.
Neither source nor generated text is interpreted as code or application actions.
JSON validation checks structure, not truth or semantic completeness. Prompt
instructions alone cannot guarantee resistance to model prompt injection.

Each response must contain only a nonempty `text` string. Invalid, truncated,
empty, oversized or failed output creates no version. A successful result
records input text, model and executable hashes, operation, prompt revision,
token limits, seed and CPU selection. Existing storage links each derived
version to its exact parent and appends regenerations. Shared libraries are not
fingerprinted. Hash comparisons detect changes but cannot prevent other programs
from changing and restoring a file during inference.

Tasks freeze both speech and text adapters when submitted. Changing or removing
configuration applies to future work. Settings use the existing SQLite settings
table, so history schema and prior versions require no migration.

Inference runs in the queue's background worker. Cancellation terminates, kills
if necessary, and reaps the child before removing temporary prompt/response files.
Diagnostics are discarded, and fixed error messages are safe to persist.
Inherited `LLAMA_*` settings and known Hugging Face token variables are excluded
from the child's environment to avoid implicit RPC, model, cache and log options.
This is not a sandbox for arbitrary executables selected by the user.

## Limits and validation gates

Prompts are limited to 64 KiB, responses to 1 MiB, generation to ten minutes;
output tokens are finite and context shifting is disabled. The byte limit is
not a token estimate. Runtime context/model errors fail the task, and syntactically
incomplete output is rejected. A valid response can still omit source facts.
The file-size check bounds accepted output; a misbehaving native executable can
write beyond the limit between polls. Abrupt application termination can leave
temporary files behind, as with speech output.

No model-specific chat template is selected; completion quality depends on the
model's ability to follow the plain instructions. Long documents, precise
loading/progress, hardware acceleration and managed installation remain pending.

Routine tests simulate model responses in real child processes; they establish
mechanical preservation, provenance, configuration, safe errors, bounds and
cancellation, not model quality. The opt-in `tests.text_integration` exercises
real local generation and partial fact/uncertainty checks when explicitly given
a runtime and model. It does not prove no hallucinations. Before recommendations,
run that integration and a broader human-reviewed English/French corpus covering
formatting commands, quotations, uncertainty, invented facts and malicious
instructions; then validate native execution/packaging on all target platforms.
