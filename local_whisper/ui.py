"""Tk presentation. Background workers never access widgets."""

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .domain import Kind, Status
from .i18n import _
from .management import HF_TOKEN_URL, dependency_status
from .storage import Store
from .tasks import TaskQueue
from .adapters import UnconfiguredSpeech, UnconfiguredText
from .playback import Playback
from .speech import WhisperConfig, WhisperCppSpeech
from .text import LlamaConfig, LlamaCppText


class Application:
    def __init__(self, root: tk.Tk, store: Store, tasks: TaskQueue, demo: bool):
        self.root, self.store, self.tasks = root, store, tasks
        self.demo = demo
        self.playback = Playback()
        self._closed = False
        self._snapshot = None
        self._pending_task_id = None
        self._poll_id = None
        root.title(_("Local Whisper — development preview"))
        root.geometry("1050x720")
        root.minsize(800, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.banner = ttk.Label(root, padding=12, wraplength=950)
        self.banner.pack(fill="x")
        self._update_banner()
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.audio_tab = self._tab(_("Audio and queue"))
        self.transcripts_tab = self._tab(_("Transcripts"))
        self.history_tab = self._tab(_("History"))
        self.dictation_tab = self._tab(_("Dictation"))
        self.models_tab = self._tab(_("Models"))
        self.settings_tab = self._tab(_("Settings"))
        self._build_audio()
        self._build_transcripts()
        self._build_history()
        self._build_info()
        self._build_settings()
        root.bind("<Control-o>", lambda event: self.import_audio())
        root.bind("<Control-c>", self._copy_shortcut)
        self._poll()

    def _update_banner(self):
        if self.demo:
            banner = _("DEMO MODE: all generated text is simulated. No audio recognition or LLM is running.")
        else:
            speech = (_("Local Whisper transcription selected (CPU).") if isinstance(self.tasks.speech, WhisperCppSpeech)
                      else _("Select a local speech engine and model in Models to enable transcription."))
            text = (_("Local LLM processing selected (CPU). Review generated text for accuracy.")
                    if isinstance(self.tasks.text, LlamaCppText) else _("Optional LLM processing is disabled."))
            banner = speech + " " + text
        self.banner.configure(text=banner)

    def _tab(self, label):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=label)
        return frame

    def _tree(self, parent, columns, labels, height=7):
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True, pady=8)
        tree = ttk.Treeview(container, columns=columns, show="headings", height=height, selectmode="browse")
        for column, label in zip(columns, labels):
            tree.heading(column, text=label)
            tree.column(column, width=170)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return tree

    def _build_audio(self):
        controls = ttk.Frame(self.audio_tab)
        controls.pack(fill="x")
        ttk.Button(controls, text=_("Import audio…"), command=self.import_audio).pack(side="left", padx=(0, 8))
        self.transcribe_button = ttk.Button(controls, text=_("Queue simulated transcription") if self.demo else _("Transcription unavailable"),
                                           command=self.transcribe, state="normal" if self.demo else "disabled")
        self.transcribe_button.pack(side="left")
        self._update_transcribe_button()
        self.play_button = ttk.Button(controls, text=_("Play selected audio"), command=self.play_audio)
        self.play_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(controls, text=_("Stop playback"), command=self.playback.stop, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Label(self.audio_tab, text=_("Files are referenced in place. Playback: mono/stereo 16-bit PCM WAV. "
                                       "Transcription: mono/stereo 16-bit PCM WAV at 16000 Hz."), wraplength=850).pack(anchor="w", pady=8)
        self.playback_label = ttk.Label(self.audio_tab, text=_("Playback: idle"), wraplength=850)
        self.playback_label.pack(anchor="w")
        self.playback_progress = ttk.Progressbar(self.audio_tab, maximum=100)
        self.playback_progress.pack(fill="x")
        self.sources_tree = self._tree(self.audio_tab, ("file", "date"), (_("Audio source"), _("Imported at (UTC)")))
        ttk.Label(self.audio_tab, text=_("Processing queue")).pack(anchor="w")
        self.tasks_tree = self._tree(self.audio_tab, ("file", "kind", "status"), (_("Audio source"), _("Operation"), _("Status")))
        self.tasks_tree.bind("<<TreeviewSelect>>", self._task_detail)
        self.tasks_tree.bind("<Double-1>", lambda event: self.open_task_versions())
        self.tasks_tree.bind("<Return>", lambda event: self.open_task_versions())
        ttk.Button(self.audio_tab, text=_("Open selected task's transcript"),
                   command=self.open_task_versions).pack(anchor="w")
        ttk.Button(self.audio_tab, text=_("Cancel selected task"), command=self.cancel_task).pack(anchor="w")
        self.task_error = ttk.Label(self.audio_tab, text="", wraplength=850)
        self.task_error.pack(anchor="w", pady=8)

    def _update_transcribe_button(self):
        available = self.demo or isinstance(self.tasks.speech, WhisperCppSpeech)
        label = (_("Queue simulated transcription") if self.demo else _("Queue local transcription")
                 if available else _("Transcription unavailable"))
        self.transcribe_button.configure(text=label, state="normal" if available else "disabled")

    def play_audio(self):
        self._guard(lambda: self.playback.play(Path(self.store.source(self._selected(self.sources_tree))["path"])))

    def _build_transcripts(self):
        ttk.Label(self.transcripts_tab, text=_("Choose an audio entry to inspect its transcript versions. "
                                             "Completed transcripts remain available after restarting the application."),
                  wraplength=850).pack(anchor="w")
        row = ttk.Frame(self.transcripts_tab)
        row.pack(fill="x", pady=8)
        ttk.Label(row, text=_("Audio source:")).pack(side="left", padx=(0, 8))
        self.transcript_sources = []
        self.transcript_source = ttk.Combobox(row, state="readonly")
        self.transcript_source.pack(side="left", fill="x", expand=True)
        self.transcript_source.bind("<<ComboboxSelected>>", self._select_transcript_source)
        self.versions_tree = self._tree(self.transcripts_tab, ("kind", "engine", "date"),
                                        (_("Version"), _("Engine / model"), _("Created at (UTC)")), height=5)
        self.versions_tree.bind("<<TreeviewSelect>>", self._show_version)
        self.provenance = ttk.Label(self.transcripts_tab, text="", wraplength=850)
        self.provenance.pack(anchor="w")
        self.text = tk.Text(self.transcripts_tab, wrap="word", height=12, state="disabled", takefocus=True)
        self.text.pack(fill="both", expand=True, pady=8)
        controls = ttk.Frame(self.transcripts_tab)
        controls.pack(fill="x")
        for label, command in [(_("Copy"), self.copy), (_("Export…"), self.export)]:
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=(0, 8))
        self.intelligent_button = ttk.Button(controls, command=lambda: self.derive(Kind.INTELLIGENT))
        self.intelligent_button.pack(side="left", padx=(0, 8))
        self.report_button = ttk.Button(controls, command=lambda: self.derive(Kind.REPORT))
        self.report_button.pack(side="left")
        self._update_text_buttons()

    def _update_text_buttons(self):
        available = self.demo or isinstance(self.tasks.text, LlamaCppText)
        self.intelligent_button.configure(text=_("Simulate intelligent version") if self.demo else _("Create intelligent version"),
                                           state="normal" if available else "disabled")
        self.report_button.configure(text=_("Simulate report version") if self.demo else _("Create report version"),
                                     state="normal" if available else "disabled")

    def _build_history(self):
        ttk.Label(self.history_tab, text=_("History persists locally. Select an entry to open its versions.")).pack(anchor="w")
        self.history_tree = self._tree(self.history_tab, ("file", "count", "date"),
                                       (_("Audio source"), _("Versions"), _("Imported at (UTC)")))
        ttk.Button(self.history_tab, text=_("Open versions"), command=self.open_versions).pack(anchor="w")
        self.history_tree.bind("<Double-1>", lambda event: self.open_versions())
        self.history_tree.bind("<Return>", lambda event: self.open_versions())
        ttk.Button(self.history_tab, text=_("Delete history entry…"), command=self.delete).pack(anchor="w", pady=8)

    def _build_info(self):
        ttk.Label(self.dictation_tab, text=_("Live microphone capture and voice activity detection are not integrated yet.\n"
                                            "The segment boundary logic is tested independently. Configure the future silence threshold in Settings."),
                  wraplength=850).pack(anchor="w")
        model_tabs = ttk.Notebook(self.models_tab)
        model_tabs.pack(fill="both", expand=True)
        speech_frame = ttk.Frame(model_tabs, padding=8)
        text_frame = ttk.Frame(model_tabs, padding=8)
        model_tabs.add(speech_frame, text=_("Speech recognition"))
        model_tabs.add(text_frame, text=_("Optional local LLM"))
        ttk.Label(speech_frame, text=_("Choose a trusted local whisper-cli executable and a Whisper model in whisper.cpp GGML format. "
                                         "No downloads are performed. Transcription runs locally on the CPU. "
                                         "Model compatibility is checked by the engine during transcription.\n\n"
                                         "Parakeet support is pending. The exact Hugging Face identifier for ‘oruk/orukeet’ must be confirmed before integration."),
                  wraplength=850).pack(anchor="w")
        config = self.store.speech_config()
        self.speech_executable = tk.StringVar(value=str(config.executable) if config else "")
        self.speech_model = tk.StringVar(value=str(config.model) if config else "")
        self.speech_language = tk.StringVar(value=config.language if config else "auto")
        for label, variable in [(_("Speech engine executable"), self.speech_executable),
                                (_("Local GGML model"), self.speech_model)]:
            row = ttk.Frame(speech_frame)
            row.pack(fill="x", pady=8)
            ttk.Label(row, text=label, width=24).pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text=_("Browse…"), command=lambda v=variable: self._browse_model(v)).pack(side="left", padx=8)
        row = ttk.Frame(speech_frame)
        row.pack(anchor="w", pady=8)
        ttk.Label(row, text=_("Language (auto, en, fr, …):")).pack(side="left")
        ttk.Entry(row, textvariable=self.speech_language, width=10).pack(side="left", padx=8)
        self.apply_speech_button = ttk.Button(row, text=_("Apply speech configuration"), command=self.configure_speech,
                                              state="disabled" if self.demo else "normal")
        self.apply_speech_button.pack(side="left")
        ttk.Button(row, text=_("Remove configuration"), command=self.clear_speech,
                   state="disabled" if self.demo else "normal").pack(side="left", padx=8)
        ttk.Label(speech_frame, text=_("Changes apply to newly queued tasks. Existing tasks retain their selected model. "
                                         "Auto detection requires a multilingual model; use en for an English-only model. "
                                         "Demo mode ignores saved engine settings."), wraplength=850).pack(anchor="w", pady=8)

        self._build_text_models(text_frame)

    def _build_text_models(self, frame):
        ttk.Label(frame, text=_("LLM processing is optional. Raw transcription, playback, history and exports work without a language model. "
                                "The LLM runs only when you request an intelligent version or report. "
                                "Select a trusted native llama-completion executable and a local GGUF language model. "
                                "Processing runs offline on the CPU. No downloads are performed. "
                                "Generated documents require review: models can omit or invent information."),
                  wraplength=800).pack(anchor="w", pady=8)
        config = self.store.text_config()
        self.text_executable = tk.StringVar(value=str(config.executable) if config else "")
        self.text_model = tk.StringVar(value=str(config.model) if config else "")
        self.text_context = tk.StringVar(value=str(config.context_tokens) if config else "8192")
        self.text_output = tk.StringVar(value=str(config.output_tokens) if config else "2048")
        for label, variable in [(_("LLM executable"), self.text_executable), (_("Local GGUF model"), self.text_model)]:
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=8)
            ttk.Label(row, text=label, width=24).pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text=_("Browse…"), command=lambda v=variable: self._browse_model(v)).pack(side="left", padx=8)
        row = ttk.Frame(frame)
        row.pack(anchor="w", pady=8)
        for label, variable in [(_("Context tokens:"), self.text_context), (_("Maximum output tokens:"), self.text_output)]:
            ttk.Label(row, text=label).pack(side="left")
            ttk.Entry(row, textvariable=variable, width=8).pack(side="left", padx=8)
        row = ttk.Frame(frame)
        row.pack(anchor="w", pady=8)
        ttk.Button(row, text=_("Apply LLM configuration"), command=self.configure_text,
                   state="disabled" if self.demo else "normal").pack(side="left")
        ttk.Button(row, text=_("Remove configuration"), command=self.clear_text,
                   state="disabled" if self.demo else "normal").pack(side="left", padx=8)
        ttk.Label(frame, text=_("Select a raw version in Transcripts to create an intelligent version; "
                                "select an intelligent version to create a report. Every generation creates a new version. "
                                "Changes apply to newly queued tasks. Removing configuration keeps model files. "
                                "This preview limits prompts to 64 KiB and generation to ten minutes."),
                  wraplength=800).pack(anchor="w", pady=8)

    def configure_text(self):
        if self.demo:
            return
        def operation():
            config = LlamaConfig(Path(self.text_executable.get()), Path(self.text_model.get()),
                                 int(self.text_context.get()), int(self.text_output.get()))
            self.store.set_text_config(config)
            self.tasks.set_text(LlamaCppText(config))
            self._update_banner()
            self._update_text_buttons()
        self._guard(operation)

    def clear_text(self):
        if self.demo:
            return
        self.store.set_text_config(None)
        self.tasks.set_text(UnconfiguredText())
        self.text_executable.set("")
        self.text_model.set("")
        self.text_context.set("8192")
        self.text_output.set("2048")
        self._update_banner()
        self._update_text_buttons()

    def _browse_model(self, variable):
        path = filedialog.askopenfilename(parent=self.root, title=_("Select local engine or model"))
        if path:
            variable.set(path)

    def configure_speech(self):
        if self.demo:
            return
        def operation():
            config = WhisperConfig(Path(self.speech_executable.get()), Path(self.speech_model.get()),
                                   self.speech_language.get().strip())
            self.store.set_speech_config(config)
            self.tasks.set_speech(WhisperCppSpeech(config))
            self._update_banner()
            self._update_transcribe_button()
        self._guard(operation)

    def clear_speech(self):
        if self.demo:
            return
        self.store.set_speech_config(None)
        self.tasks.set_speech(UnconfiguredSpeech())
        self.speech_executable.set("")
        self.speech_model.set("")
        self.speech_language.set("auto")
        self._update_banner()
        self._update_transcribe_button()

    def _build_settings(self):
        for name, status in dependency_status().items():
            ttk.Label(self.settings_tab, text=f"{_(name)}: {_(status)}").pack(anchor="w", pady=3)
        ttk.Label(self.settings_tab, text=_("History directory: {path}").format(path=self.store.path.parent), wraplength=850).pack(anchor="w", pady=12)
        row = ttk.Frame(self.settings_tab)
        row.pack(anchor="w", pady=8)
        ttk.Label(row, text=_("Silence threshold (seconds):")).pack(side="left")
        self.silence = tk.StringVar(value=str(self.store.silence_seconds()))
        ttk.Entry(row, textvariable=self.silence, width=8).pack(side="left", padx=8)
        ttk.Button(row, text=_("Save"), command=self.save_settings).pack(side="left")
        ttk.Label(self.settings_tab, text=_("This preview works offline and performs no downloads. Opening the Hugging Face page uses your browser and network.\n"
                                           "Token storage is not available yet; do not enter a token into this preview."), wraplength=850).pack(anchor="w", pady=12)
        ttk.Button(self.settings_tab, text=_("Open official Hugging Face token page"),
                   command=lambda: webbrowser.open(HF_TOKEN_URL)).pack(anchor="w")

    def _selected(self, tree):
        selection = tree.selection()
        if not selection:
            raise ValueError(_("Select an entry first."))
        return selection[0]

    def _guard(self, operation):
        try:
            operation()
        except (ValueError, KeyError, OSError, RuntimeError) as error:
            messagebox.showerror(_("Operation unavailable"), str(error), parent=self.root)

    def import_audio(self):
        paths = filedialog.askopenfilenames(parent=self.root, title=_("Import audio"),
                                           filetypes=[(_("PCM WAV files"), "*.wav"), (_("All files"), "*")])
        for path in paths:
            self._guard(lambda p=path: self.store.import_audio(Path(p)))
        self._snapshot = None

    def transcribe(self):
        def operation():
            self._pending_task_id = self.tasks.submit(self._selected(self.sources_tree))
        self._guard(operation)

    def cancel_task(self):
        self._guard(lambda: self.tasks.cancel(self._selected(self.tasks_tree)))

    def _task_detail(self, event=None):
        selected = self.tasks_tree.selection()
        details = next((t for t in self.store.tasks() if selected and t["id"] == selected[0]), None)
        self.task_error.configure(text=_(details["error"]) if details and details["error"] else "")

    def open_versions(self):
        self._guard(lambda: self._open_transcripts(self._selected(self.history_tree)))

    def open_task_versions(self):
        def operation():
            task_id = self._selected(self.tasks_tree)
            task = next((t for t in self.store.tasks() if t["id"] == task_id), None)
            if task is None or task["status"] != Status.COMPLETED:
                raise ValueError(_("Select a completed task to open its transcript."))
            self._open_transcripts(task["source_id"])
        self._guard(operation)

    def _open_transcripts(self, source_id):
        self.store.source(source_id)
        self.open_source = source_id
        self._sync_transcript_selection()
        self._refresh_versions()
        self.notebook.select(self.transcripts_tab)

    def _select_transcript_source(self, event=None):
        index = self.transcript_source.current()
        if index >= 0:
            self._guard(lambda: self._open_transcripts(self.transcript_sources[index]))

    def _sync_transcript_selection(self):
        source = getattr(self, "open_source", None)
        if source in self.transcript_sources:
            self.transcript_source.current(self.transcript_sources.index(source))
        else:
            self.transcript_source.set("")

    def _refresh_transcript_sources(self, sources, version_counts):
        available = [s for s in sources if version_counts[s["id"]]]
        self.transcript_sources = [s["id"] for s in available]
        self.transcript_source.configure(values=[f"{Path(s['path']).name} — {s['created_at']}" for s in available])
        if getattr(self, "open_source", None) not in {s["id"] for s in sources}:
            if available:
                self.open_source = available[0]["id"]
            elif hasattr(self, "open_source"):
                del self.open_source
                self._replace(self.versions_tree, [])
                self._show_version()
        self._sync_transcript_selection()

    def _refresh_versions(self):
        versions = self.store.versions(self.open_source)
        self._replace(self.versions_tree, [(v.id, (_(v.kind.value), f"{v.engine} / {v.model}", v.created_at)) for v in versions])
        if versions and not self.versions_tree.selection():
            self.versions_tree.selection_set(versions[-1].id)
        self._show_version()

    def _show_version(self, event=None):
        selected = self.versions_tree.selection()
        value = self.store.version(selected[0]) if selected else None
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if value:
            self.text.insert("1.0", value.text)
        self.text.configure(state="disabled")
        self.provenance.configure(text=_("Version: {id}\nParent: {parent}").format(
            id=value.id, parent=value.parent_id or _("none")) if value else "")

    def copy(self):
        def operation():
            version = self.store.version(self._selected(self.versions_tree))
            self.root.clipboard_clear()
            self.root.clipboard_append(version.text)
        self._guard(operation)

    def _copy_shortcut(self, event):
        if self.root.focus_get() == self.versions_tree:
            self.copy()
            return "break"

    def export(self):
        def operation():
            version_id = self._selected(self.versions_tree)
            path = filedialog.asksaveasfilename(parent=self.root, title=_("Export to a new file"),
                                              defaultextension=".txt", filetypes=[(_("Text"), "*.txt"), (_("JSON with provenance"), "*.json")])
            if path:
                self.store.export(version_id, Path(path))
        self._guard(operation)

    def derive(self, kind):
        def operation():
            version = self.store.version(self._selected(self.versions_tree))
            self._pending_task_id = self.tasks.submit(version.source_id, kind, version.id)
        self._guard(operation)

    def delete(self):
        def operation():
            source_id = self._selected(self.history_tree)
            if self.tasks.source_busy(source_id):
                raise ValueError(_("Cancel the entry's active tasks and wait for completion before deleting it."))
            source = self.store.source(source_id)
            if messagebox.askyesno(_("Delete history entry"),
                                   _("Delete this history entry, all its transcript versions and task records?\n\n"
                                     "The original audio file will be kept:\n{path}").format(path=source["path"]), parent=self.root):
                self.store.delete_source(source_id)
                if getattr(self, "open_source", None) == source_id:
                    self._refresh_versions()
                self._snapshot = None
        self._guard(operation)

    def save_settings(self):
        self._guard(lambda: self.store.set_silence_seconds(float(self.silence.get())))

    @staticmethod
    def _replace(tree, rows):
        selected = tree.selection()
        tree.delete(*tree.get_children())
        for key, values in rows:
            tree.insert("", "end", iid=key, values=values)
        for key in selected:
            if tree.exists(key):
                tree.selection_set(key)

    def _poll(self):
        playback = self.playback.snapshot()
        self.playback_label.configure(text=_("Playback: {status}").format(status=_(playback.status))
                                      + (f" — {_(playback.error)}" if playback.error else ""))
        self.playback_progress.configure(value=playback.progress * 100)
        self.play_button.configure(state="disabled" if playback.status == "playing" else "normal")
        self.stop_button.configure(state="normal" if playback.status == "playing" else "disabled")
        sources, tasks = self.store.sources(), self.store.tasks()
        version_counts = {s["id"]: len(self.store.versions(s["id"])) for s in sources}
        snapshot = (sources, tasks, version_counts)
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            names = {s["id"]: Path(s["path"]).name for s in sources}
            self._replace(self.sources_tree, [(s["id"], (names[s["id"]], s["created_at"])) for s in sources])
            self._replace(self.history_tree, [(s["id"], (names[s["id"]], version_counts[s["id"]], s["created_at"])) for s in sources])
            self._refresh_transcript_sources(sources, version_counts)
            self._replace(self.tasks_tree, [(t["id"], (names.get(t["source_id"], ""), _(t["kind"]), _(t["status"]))) for t in tasks])
            if self._pending_task_id and self.tasks_tree.exists(self._pending_task_id):
                self.tasks_tree.selection_set(self._pending_task_id)
                self.tasks_tree.see(self._pending_task_id)
                self._pending_task_id = None
            if hasattr(self, "open_source"):
                self._refresh_versions()
            self._task_detail()
        self._poll_id = self.root.after(150, self._poll)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.playback.close()
        self.tasks.close()
        try:
            if self._poll_id is not None:
                self.root.after_cancel(self._poll_id)
            self.root.destroy()
        except tk.TclError:
            pass  # Worker cancellation still applies if Tk was already destroyed.
