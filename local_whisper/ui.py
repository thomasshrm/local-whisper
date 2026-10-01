"""Tk presentation. Background workers never access widgets."""

import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .domain import Kind
from .i18n import _
from .management import HF_TOKEN_URL, dependency_status
from .storage import Store
from .tasks import TaskQueue


class Application:
    def __init__(self, root: tk.Tk, store: Store, tasks: TaskQueue, demo: bool):
        self.root, self.store, self.tasks = root, store, tasks
        self.demo = demo
        self._snapshot = None
        self._poll_id = None
        root.title(_("Local Whisper — development preview"))
        root.geometry("1050x720")
        root.minsize(800, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)
        banner = (_("DEMO MODE: all generated text is simulated. No audio recognition or LLM is running.")
                  if demo else _("Development preview: speech and LLM engines are not configured. Import and history are available."))
        ttk.Label(root, text=banner, padding=12, wraplength=950).pack(fill="x")
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
        ttk.Label(self.audio_tab, text=_("Files are referenced in place. Playback is not yet integrated."), wraplength=850).pack(anchor="w", pady=8)
        self.sources_tree = self._tree(self.audio_tab, ("file", "date"), (_("Audio source"), _("Imported at (UTC)")))
        ttk.Label(self.audio_tab, text=_("Processing queue")).pack(anchor="w")
        self.tasks_tree = self._tree(self.audio_tab, ("file", "kind", "status"), (_("Audio source"), _("Operation"), _("Status")))
        self.tasks_tree.bind("<<TreeviewSelect>>", self._task_detail)
        ttk.Button(self.audio_tab, text=_("Cancel selected task"), command=self.cancel_task).pack(anchor="w")
        self.task_error = ttk.Label(self.audio_tab, text="", wraplength=850)
        self.task_error.pack(anchor="w", pady=8)

    def _build_transcripts(self):
        ttk.Label(self.transcripts_tab, text=_("Select an entry in History to inspect its immutable transcript versions.")).pack(anchor="w")
        self.versions_tree = self._tree(self.transcripts_tab, ("kind", "engine", "date"),
                                        (_("Version"), _("Engine / model"), _("Created at (UTC)")), height=5)
        self.versions_tree.bind("<<TreeviewSelect>>", self._show_version)
        self.provenance = ttk.Label(self.transcripts_tab, text="", wraplength=850)
        self.provenance.pack(anchor="w")
        self.text = tk.Text(self.transcripts_tab, wrap="word", height=12, state="disabled", takefocus=True)
        self.text.pack(fill="both", expand=True, pady=8)
        controls = ttk.Frame(self.transcripts_tab)
        controls.pack(fill="x")
        for label, command, needs_engine in [(_("Copy"), self.copy, False), (_("Export…"), self.export, False),
                                            (_("Simulate intelligent version"), lambda: self.derive(Kind.INTELLIGENT), True),
                                            (_("Simulate report version"), lambda: self.derive(Kind.REPORT), True)]:
            button = ttk.Button(controls, text=label, command=command)
            button.pack(side="left", padx=(0, 8))
            if needs_engine and not self.demo:
                button.configure(state="disabled")

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
        ttk.Label(self.models_tab, text=_("No model catalog has been verified yet. Downloads, installation and hardware detection will be added with real adapters.\n\n"
                                         "Whisper-style engines, Parakeet 0.6B and local LLM runtimes remain to be evaluated.\n"
                                         "The exact Hugging Face identifier for ‘oruk/orukeet’ must be confirmed before integration."),
                  wraplength=850).pack(anchor="w")

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
                                           filetypes=[(_("Audio files"), "*.wav *.mp3 *.flac *.m4a *.ogg")])
        for path in paths:
            self._guard(lambda p=path: self.store.import_audio(Path(p)))
        self._snapshot = None

    def transcribe(self):
        self._guard(lambda: self.tasks.submit(self._selected(self.sources_tree)))

    def cancel_task(self):
        self._guard(lambda: self.tasks.cancel(self._selected(self.tasks_tree)))

    def _task_detail(self, event=None):
        selected = self.tasks_tree.selection()
        details = next((t for t in self.store.tasks() if selected and t["id"] == selected[0]), None)
        self.task_error.configure(text=_(details["error"]) if details and details["error"] else "")

    def open_versions(self):
        def operation():
            self.open_source = self._selected(self.history_tree)
            self._refresh_versions()
            self.notebook.select(self.transcripts_tab)
        self._guard(operation)

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
            self.tasks.submit(version.source_id, kind, version.id)
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
        sources, tasks = self.store.sources(), self.store.tasks()
        version_counts = {s["id"]: len(self.store.versions(s["id"])) for s in sources}
        snapshot = (sources, tasks, version_counts)
        if snapshot != self._snapshot:
            self._snapshot = snapshot
            names = {s["id"]: Path(s["path"]).name for s in sources}
            self._replace(self.sources_tree, [(s["id"], (names[s["id"]], s["created_at"])) for s in sources])
            self._replace(self.history_tree, [(s["id"], (names[s["id"]], version_counts[s["id"]], s["created_at"])) for s in sources])
            self._replace(self.tasks_tree, [(t["id"], (names.get(t["source_id"], ""), _(t["kind"]), _(t["status"]))) for t in tasks])
            if hasattr(self, "open_source"):
                self._refresh_versions()
            self._task_detail()
        self._poll_id = self.root.after(150, self._poll)

    def close(self):
        if self._poll_id is not None:
            self.root.after_cancel(self._poll_id)
        self.tasks.close()
        self.root.destroy()
