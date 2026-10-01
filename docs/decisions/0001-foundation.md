# 0001 — Python desktop foundation with Tkinter and SQLite

Date: 2026-10-01. Status: adopted for the initial preview, subject to revisiting
desktop accessibility and multimedia needs before a production UI is committed.

## Context and decision

The repository initially contained only project instructions. No stack or engine
was preapproved. Initialize a small, runnable application with Python 3.11+,
standard-library Tkinter/ttk presentation and SQLite storage. Do not select an
inference runtime on the basis of a similarly named model. Keep engine adapters
independent of presentation so a later runtime can run in an isolated process or
application-managed environment.

Tkinter avoids a browser/backend bridge and third-party UI dependencies for this
increment. Python is useful for later evaluation of local inference tooling, but
that does not establish runtime compatibility. SQLite provides transactions,
foreign keys and local persistent storage without a database service.

## Compatibility evidence

Official sources checked on 2026-10-01:

- [Python Tkinter documentation](https://docs.python.org/3/library/tkinter.html)
  describes availability on Windows, macOS and most Unix platforms and requires
  UI event handling to remain responsive. Tk may be an optional installation.
- [Python.org macOS Tcl/Tk guidance](https://www.python.org/download/mac/tcltk/)
  describes bundled Tk in current python.org installers.
- [Debian python3-tk](https://packages.debian.org/stable/python/python3-tk)
  supplies Tk bindings for the distribution Python.
- [Arch tk](https://archlinux.org/packages/extra/x86_64/tk/)
  supplies the Tk runtime. An actual Arch startup test is still required.
- [Python SQLite documentation](https://docs.python.org/3/library/sqlite3.html)
  describes local databases and connection/thread constraints. This application
  opens one connection per operation rather than sharing connections across
  worker and UI threads.

These sources establish component availability, not verified application support
or packaging on every platform. macOS, Debian and Arch remain untested.

## Boundaries and retention

- `ui.py`: presentation, native file dialogs and clipboard; all widget access
  happens on the main thread. UI polls worker state.
- `adapters.py`: protocols for speech and text inference, unconfigured adapters,
  opt-in simulated adapters. Model output remains data and is never executed.
- `tasks.py`: serial background inference, cancellation and error isolation.
- `storage.py`: schema v1 migration, history, immutable version insertion,
  provenance, transactions, exports and history deletion.
- `audio.py`: timestamped frame segmentation; capture, playback, decoding and
  VAD are intentionally pending.
- `management.py`: dependency status and official Hugging Face link; installation,
  catalog, downloads and secret storage are pending.
- `paths.py` and `i18n.py`: platform directories and gettext boundary.

Initial import accepts file references without decoding. The future first
decoder should prioritize PCM WAV, with other formats added only after decoder
and license verification. Text/JSON are the first export formats. Every
generation appends a new version. Intelligent versions reference raw parents;
reports reference intelligent parents from the same source. No source is replaced.
Audio copies are not made, and versions are retained until explicit entry deletion.

Schema migration from version 0 creates schema v1 transactionally. No migration
between released history schemas exists yet. New migrations must preserve history;
a newer database version is refused instead of being modified.

## Consequences and unresolved decisions

The preview needs no network or large model files and can test preservation
independently of nondeterministic inference. It cannot transcribe or play audio.
Tk multimedia, screen reader support and native packaging require evaluation;
a different presentation toolkit may be chosen after that evaluation.

Standalone distribution strategy, exact ASR/LLM runtimes and model identifiers,
hardware targets, language priority, dictation latency and final audio retention
settings remain unresolved. No model catalog is published. Confirm the exact
`oruk/orukeet` Hugging Face repository and family before integrating it.
