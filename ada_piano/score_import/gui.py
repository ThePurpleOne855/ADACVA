"""PDF import, text review, and approved score practice inside the piano window."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
import webbrowser

from ada_piano.ai_tutor import Tutor
from ada_piano.music_sheet import note_name
from ada_piano.sound_sensor import NoteEvent
from .conversion import ScoreImporter, score_parts
from .review import ReviewedScore


class ScorePanel(ttk.Frame):
    def __init__(self, parent, playback, connected=lambda: False, importer=None):
        super().__init__(parent, padding=8)
        self.playback = playback
        self.connected = connected
        self.importer = importer if importer is not None else ScoreImporter()
        self.review = None
        self.loaded = None
        self.tutor = None
        self._closed = False
        self._handled = None
        self._outputs = {}
        self._parts = []
        self._folder = None
        self._source = None
        self._following_playback = False
        self.executable = tk.StringVar(value="auto")
        self.output = tk.StringVar()
        self.part = tk.StringVar()
        self.staff = tk.StringVar()
        self.voice = tk.StringVar()
        self.first = tk.StringVar(value="1")
        self.last = tk.StringVar(value="4")
        self.confirmed = tk.BooleanVar(value=False)
        self.written_order = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Choose a PDF or MusicXML file. Nothing is uploaded.")
        self.feedback = tk.StringVar(value="Review and approve a passage to enable playback and practice.")
        self.path_label = tk.StringVar(value="No score loaded")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(5, weight=1)

        tools = ttk.Frame(self)
        tools.grid(row=0, column=0, sticky="ew")
        self.choose_button = ttk.Button(tools, text="Choose PDF / MusicXML", command=self.choose)
        self.choose_button.pack(side="left")
        ttk.Button(tools, text="Cancel conversion", command=self.importer.cancel).pack(side="left", padx=4)
        ttk.Button(tools, text="Open source", command=self.open_source).pack(side="left", padx=4)
        ttk.Button(tools, text="Diagnostics", command=self.diagnostics).pack(side="left")
        settings = ttk.Frame(self)
        settings.grid(row=1, column=0, sticky="ew", pady=3)
        self.converter_label = tk.StringVar(value="Converter: automatic Audiveris detection")
        ttk.Label(settings, textvariable=self.converter_label).pack(side="left", fill="x", expand=True)
        ttk.Button(settings, text="Advanced converter settings", command=self.converter_settings).pack(side="left")
        files = ttk.Frame(self)
        files.grid(row=2, column=0, sticky="ew")
        ttk.Label(files, text="Available score:").pack(side="left")
        self.file_selector = ttk.Combobox(files, textvariable=self.output, state="readonly")
        self.file_selector.pack(side="left", fill="x", expand=True, padx=4)
        self.file_selector.bind("<<ComboboxSelected>>", self.select_output)
        self.progress = ttk.Progressbar(files, mode="indeterminate", length=100)
        self.progress.pack(side="left")
        selection = ttk.Frame(self)
        selection.grid(row=3, column=0, sticky="ew", pady=3)
        ttk.Label(selection, text="Part:").pack(side="left")
        self.part_selector = ttk.Combobox(selection, textvariable=self.part, state="readonly", width=18)
        self.part_selector.pack(side="left")
        self.part_selector.bind("<<ComboboxSelected>>", self.select_part)
        for title, variable, width in (("Staff", self.staff, 4), ("Voice", self.voice, 4),
                                       ("From", self.first, 4), ("To", self.last, 4)):
            ttk.Label(selection, text=title).pack(side="left", padx=(6, 2))
            ttk.Entry(selection, textvariable=variable, width=width).pack(side="left")
        self.preview_button = ttk.Button(selection, text="Preview passage", command=self.preview, state="disabled")
        self.preview_button.pack(side="left", padx=6)
        options = ttk.Frame(self)
        options.grid(row=4, column=0, sticky="ew")
        ttk.Checkbutton(options, text="Play written measures once (ignore repeats and ending signs)",
                        variable=self.written_order).pack(anchor="w")
        ttk.Label(options, text="Staff/voice blank = all. From/to = measure positions. Fixed tempo; pedal, dynamics and fingering ignored.",
                  wraplength=820).pack(anchor="w")
        table = ttk.Frame(self)
        table.grid(row=5, column=0, sticky="nsew", pady=4)
        self.table = ttk.Treeview(table, columns=("measure", "beat", "notes", "duration", "line"),
                                  show="headings", height=3)
        for name, title in (("measure", "Measure"), ("beat", "Beat"), ("notes", "Note / rest"),
                            ("duration", "Beats held"), ("line", "Staff / voice")):
            self.table.heading(name, text=title)
            self.table.column(name, width=110, minwidth=70)
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.table.pack(fill="both", expand=True)
        approval = ttk.Frame(self)
        approval.grid(row=6, column=0, sticky="ew")
        ttk.Checkbutton(approval, text="I checked this passage against the source", variable=self.confirmed,
                        command=self._confirmation_changed).pack(side="left")
        ttk.Button(approval, text="Approve & load", command=self.approve).pack(side="left", padx=4)
        actions = ttk.Frame(self)
        actions.grid(row=7, column=0, sticky="ew", pady=3)
        self.play_button = ttk.Button(actions, text="Play approved passage", command=self.play, state="disabled")
        self.play_button.pack(side="left")
        self.practice_button = ttk.Button(actions, text="Start practice", command=self.practice, state="disabled")
        self.practice_button.pack(side="left", padx=4)
        ttk.Button(actions, text="Stop practice / sound", command=self.stop).pack(side="left")
        ttk.Label(self, textvariable=self.feedback, wraplength=820).grid(row=8, column=0, sticky="w")
        ttk.Label(self, textvariable=self.status, wraplength=820).grid(row=9, column=0, sticky="w")
        ttk.Label(self, textvariable=self.path_label, wraplength=820).grid(row=10, column=0, sticky="w")
        for variable in (self.part, self.staff, self.voice, self.first, self.last, self.written_order):
            variable.trace_add("write", self._invalidate)
        self._timer = self.after(150, self._poll)

    def _invalidate(self, *args):
        if self.loaded is not None:
            self.playback.stop()
        self.review = self.loaded = self.tutor = None
        self._following_playback = False
        self.confirmed.set(False)
        self.play_button.configure(state="disabled")
        self.practice_button.configure(state="disabled")
        children = self.table.get_children()
        if children:
            self.table.delete(*children)
        self.feedback.set("Preview the selected passage, check it, then approve and load.")

    def _confirmation_changed(self):
        if not self.confirmed.get():
            self.loaded = self.tutor = None
            self.playback.stop()
            self.play_button.configure(state="disabled")
            self.practice_button.configure(state="disabled")

    def choose_executable(self):
        path = filedialog.askopenfilename(parent=self, title="Select the Audiveris application — not your PDF")
        if path:
            if Path(path).suffix.lower() in {".pdf", ".xml", ".mxl", ".musicxml"}:
                self.status.set("That is a score, not the Audiveris application. Use Choose PDF / MusicXML at the top. Automatic detection remains available.")
                return
            self.executable.set(path)
            self.converter_label.set(f"Custom converter: {Path(path).name}")

    def converter_settings(self):
        window = tk.Toplevel(self)
        window.title("Advanced converter settings")
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Automatic detection finds native and Flatpak Audiveris.\n"
                  "Only change this to use a custom Audiveris application.\n"
                  "Choose your PDF on the main Scores screen.").pack(anchor="w")
        ttk.Label(frame, textvariable=self.converter_label, wraplength=450).pack(anchor="w", pady=10)
        def automatic():
            self.executable.set("auto")
            self.converter_label.set("Converter: automatic Audiveris detection")
            window.destroy()
        ttk.Button(frame, text="Use automatic detection", command=automatic).pack(fill="x", pady=4)
        ttk.Button(frame, text="Select custom Audiveris application", command=self.choose_executable).pack(fill="x", pady=4)
        ttk.Button(frame, text="Close", command=window.destroy).pack(fill="x", pady=4)

    def choose(self):
        path = filedialog.askopenfilename(parent=self, title="Choose a score",
                                          filetypes=[("Scores", "*.pdf *.musicxml *.xml *.mxl"), ("All files", "*")])
        if path:
            self.import_file(path)

    def import_file(self, path):
        try:
            self.importer.start(path, self.executable.get())
            self._invalidate()
            self._outputs = {}
            self._parts = []
            self.part.set("")
            self.part_selector["values"] = ()
            self.preview_button.configure(state="disabled")
            self.output.set("")
            self.file_selector["values"] = ()
            self._folder = self._source = self._handled = None
            self.path_label.set(str(path))
            self.status.set("Importing…")
            self.progress.start(15)
        except Exception as exc:
            self.status.set(f"Cannot import: {exc}")

    def select_output(self, event=None):
        self._invalidate()
        self.preview_button.configure(state="disabled")
        try:
            path = self._outputs[self.output.get()]
            self._parts = score_parts(path)
            self.part_selector["values"] = tuple(f"{p['id']} — {p['name']}" for p in self._parts)
            self.part.set(self.part_selector["values"][0])
            self.select_part()
            self.preview_button.configure(state="normal")
        except Exception as exc:
            self.status.set(f"Cannot read score: {exc}")

    def select_part(self, event=None):
        part = self._selected_part()
        self.staff.set(part["staves"][0] if part["staves"] else "")
        self.voice.set("")
        self.first.set("1")
        self.last.set(str(min(4, part["measures"])))
        self.status.set(f"{part['measures']} measures. Staves: {', '.join(part['staves'])}; voices: {', '.join(part['voices'])}. Preview a short passage.")

    def _selected_part(self):
        index = self.part_selector.current()
        if not 0 <= index < len(self._parts):
            raise ValueError("Select a score part first.")
        return self._parts[index]

    def preview(self):
        if self.output.get() not in self._outputs:
            detail = self.importer.status.detail
            self.status.set(f"No MusicXML is available to preview. {detail}")
            return
        self._invalidate()
        try:
            review = ReviewedScore(self._outputs[self.output.get()], part=self._selected_part()["id"],
                                   staff=self.staff.get().strip() or None, voice=self.voice.get().strip() or None,
                                   start_measure=int(self.first.get()), end_measure=int(self.last.get()),
                                   written_order=self.written_order.get())
            rows = []
            for event in review.exercise.events:
                for tone in event.tones:
                    rows.append((event.onset, event.measure, note_name(tone.pitch), tone.duration, tone.staff, tone.voice))
            for rest in review.exercise.rests:
                rows.append((rest.onset, rest.measure, "Rest", rest.duration, rest.staff, rest.voice))
            if len(rows) > 4096:
                raise ValueError("Select a shorter passage (at most 4096 note/rest rows).")
            for beat, measure, name, duration, staff, voice in sorted(rows):
                self.table.insert("", "end", values=(measure, str(beat), name, str(duration), f"{staff} / {voice}"))
            self.review = review
            self.feedback.set(f"{review.exercise.title}: {len(review.exercise.events)} attack groups. Beat positions start at 0.")
            self.status.set("Needs review. Compare the table with the source. Correct recognition errors in Audiveris or a score editor, then reimport.")
        except Exception as exc:
            self.status.set(f"Cannot preview: {exc}")

    def approve(self):
        try:
            if self.review is None or not self.confirmed.get():
                raise ValueError("Preview the passage and confirm you checked it against the source first.")
            self.review.approve()
            saved = self.review.save(self._folder)
            self.loaded = self.review
            self.play_button.configure(state="normal")
            self.practice_button.configure(state="normal")
            self.status.set(f"Approved and loaded. Structured exercise saved: {saved}")
            self.feedback.set("Ready. Select MIDI output and tempo in Piano & Camera → Audible reference, or start pitch practice.")
        except Exception as exc:
            self.loaded = self.tutor = None
            self.play_button.configure(state="disabled")
            self.practice_button.configure(state="disabled")
            self.status.set(f"Cannot load: {exc}")

    def play(self):
        if self.loaded is None:
            return
        self.stop_practice()
        self.playback.play_exercise(self.loaded.exercise)
        self._following_playback = self.playback.player.status.state == "playing"
        self.feedback.set(self.playback.status.get())

    def practice(self):
        if self.loaded is None:
            return
        if not self.connected():
            self.feedback.set("Connect the piano input first. Demo input is not graded.")
            return
        if self.playback.player.status.state == "playing":
            self.feedback.set("Wait for the reference to finish or stop its sound before practicing.")
            return
        self.tutor = Tutor(self.loaded.exercise)
        self._following_playback = False
        self.feedback.set("Your turn. Release held keys first. " + self.tutor.prompt())

    def stop_practice(self):
        if self.tutor is not None:
            self.feedback.set("Practice stopped. Start a new attempt when ready.")
        self.tutor = None

    def stop(self):
        self._following_playback = False
        self.stop_practice()
        self.playback.stop()
        self.feedback.set("Practice stopped.")

    def observe(self, event, source):
        if self.tutor is None or source != "Piano":
            return
        if self.playback.player.status.state == "playing":
            self.stop_practice()
            self.feedback.set("Reference playing. Start practice again when it finishes.")
            return
        message = self.tutor.observe(NoteEvent(event.note, event.velocity, event.timestamp, "midi",
                                              "note_on" if event.kind == "on" else "note_off", event.channel - 1))
        if message:
            self.feedback.set(message)
        if self.tutor.complete:
            self.tutor = None

    def agent_context(self):
        if self.loaded is None:
            raise ValueError("No approved passage is loaded.")
        return self.loaded.context()

    def open_source(self):
        if self._source is not None:
            webbrowser.open(Path(self._source).resolve().as_uri())

    def diagnostics(self):
        window = tk.Toplevel(self)
        window.title("Conversion diagnostics")
        text = tk.Text(window, width=100, height=24, wrap="word")
        text.pack(fill="both", expand=True)
        text.insert("1.0", self.importer.diagnostics())
        text.configure(state="disabled")

    def _poll(self):
        try:
            status = self.importer.status
            self.choose_button.configure(state="disabled" if self.importer.running else "normal")
            if status.state == "running":
                self.status.set(f"{status.detail} {status.elapsed:.0f}s elapsed.")
            elif status is not self._handled and status.state != "idle":
                self._handled = status
                self.progress.stop()
                self.status.set(status.detail)
                self._folder, self._source = status.folder, status.source
                self.path_label.set(f"Saved files: {status.folder}")
                if status.state == "ready":
                    if status.folder is None:
                        raise RuntimeError("Import has no saved output folder.")
                    self._outputs = {str(path.relative_to(status.folder)): path for path in status.outputs}
                    self.file_selector["values"] = tuple(self._outputs)
                    self.output.set(next(iter(self._outputs)))
                    self.select_output()
            if self.tutor is not None and self.playback.player.status.state == "playing":
                self.stop_practice()
                self.feedback.set("Reference playing. Start practice again when it finishes.")
            if self._following_playback:
                self.feedback.set(self.playback.player.status.detail)
                if self.playback.player.status.state != "playing":
                    self._following_playback = False
        except Exception as exc:
            self.status.set(f"Score error: {exc}")
        finally:
            if not self._closed:
                self._timer = self.after(150, self._poll)

    def close(self):
        self._closed = True
        self.after_cancel(self._timer)
        self.importer.close()
