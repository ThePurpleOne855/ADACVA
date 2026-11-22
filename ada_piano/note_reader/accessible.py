"""Tactile sign plate: the learner's home screen, readable from the piano bench.

ADA speaks everything; this plate repeats it in very large type: what ADA is doing,
what it just said, and each take embossed as one dot per note, grouped by measure.
Widgets stay native (keyboard focus, real text for tests and copying); lettering.py
draws the type smooth where Tk cannot.
"""

import re
import tkinter as tk
import tkinter.font as tkfont

from ada_piano.note_reader import lettering

# Flat matte plate, ivory ink, one amber signal that owns every live state.
# Contrast on the plate: INK 15.3:1, SLATE 9.4:1, AMBER 9.6:1, FADED 5.6:1.
PLATE, RAISED, RAISED_HOVER, EDGE = "#15181F", "#1E222C", "#2A3040", "#3A4152"
INK, SLATE, AMBER, FADED = "#F2EFE6", "#B9BFCD", "#FFB020", "#8A90A0"
CELL = 24  # one cell unit sets every space
SCALES = (0.8, 0.9, 1.0, 1.15, 1.3, 1.5, 1.75)
BRAILLE_ADA = ((1,), (1, 4, 5), (1,))  # Grade 1 braille dot numbers for A, D, A
WORDS_LINES = 3  # ADA's latest words always get at least this many lines, and fill any room beyond it
COMPACT_HEIGHT = 760  # shorter windows show one take row so ADA's words keep their room
LIVE = {"Listening", "Recording", "Guided practice", "Speaking", "Thinking", "Hearing you"}
SUBLINE = {"Recording", "Guided practice", "Voice input stopped", "Ready"}  # states whose sentence adds an instruction
PLACEHOLDER = "Type to ADA, or press F1 and speak"
ROOMS = (("practice", "Practice"), ("piano", "Piano"), ("pieces", "Pieces"), ("camera", "Camera"),
         ("voice", "Voice & AI"))


def state_word(status):
    """The one word the plate shows for ADA's state, and whether that state is live."""
    text = status.lower()
    for key, word in (("recording", "Recording"), ("guided", "Guided practice"), ("speaking", "Speaking"),
                      ("thinking", "Thinking"), ("transcribing", "Hearing you"), ("understanding", "Hearing you"),
                      ("failed", "Voice input stopped"), ("microphone off", "Microphone off"),
                      ("paused", "Paused"), ("listening", "Listening"), ("starting", "Starting")):
        if key in text:
            return word, word in LIVE
    return "Ready", False


def take_cells(exercise, report):
    """One dot per expected note, grouped by measure: "ok", "miss" (wrong or missed) or "rest" (not reached)."""
    from ada_piano.ai_tutor.performance import expected_notes
    from ada_piano.music_sheet import note_name

    reached = report.get("notes_reached", 0)
    groups = []
    for index, note in enumerate(expected_notes(exercise)):
        if not groups or groups[-1][0] != note.measure:
            groups.append((note.measure, []))
        groups[-1][1].append([note_name(note.pitch), "ok" if index < reached else "rest"])
    problems = {detail["measure"]: [wrong["expected"] for wrong in detail.get("wrong", [])] + list(detail.get("missed", []))
                for detail in report.get("measure_details", [])}
    for measure, dots in groups:
        for name in problems.get(measure, []):
            dot = (next((d for d in dots if d[0] == name and d[1] == "ok"), None)
                   or next((d for d in dots if d[1] == "ok"), None))
            if dot is not None:
                dot[1] = "miss"
    work = report.get("measures_needing_work") or []
    return [{"measure": measure, "dots": [state for _, state in dots], "ring": bool(work) and measure == work[0]}
            for measure, dots in groups]


def _spoken(name):
    return re.sub(r"(\D)(-?\d+)$", r"\1 \2", name)


def take_note(report):
    """The single measured fact worth reading first."""
    details = {detail["measure"]: detail for detail in report.get("measure_details", [])}
    for measure in report.get("measures_needing_work") or []:
        detail = details.get(measure, {})
        if detail.get("wrong"):
            wrong = detail["wrong"][0]
            return f"Measure {measure}: {_spoken(wrong['played'])} instead of {_spoken(wrong['expected'])}."
        if detail.get("missed"):
            return f"Measure {measure}: {_spoken(detail['missed'][0])} was missed."
        if detail.get("late") or detail.get("early"):
            return f"Measure {measure}: the timing drifted."
        if detail.get("short"):
            return f"Measure {measure}: {_spoken(detail['short'][0])} was held too briefly."
        if detail.get("hesitations"):
            return f"Measure {measure}: you paused before going on."
        return f"Measure {measure} needs work."
    if not report.get("complete", True):
        return "The take stopped before the end."
    return "Every note right."


class Room(tk.Frame):
    """One tool room on the plate: a title, its status in large type, a few big buttons, ADA's latest reply."""

    def __init__(self, view, parent):
        super().__init__(parent, background=PLATE)
        self.view = view
        self._key = None
        self._buttons = []
        self.title_label = tk.Label(self, background=PLATE, borderwidth=0, anchor="w")
        self.title_label.pack(fill="x")
        self.lines = tk.Frame(self, background=PLATE)
        self.lines.pack(fill="x", pady=(CELL // 2, 0))
        self.actions = tk.Frame(self, background=PLATE)
        self.actions.pack(fill="x", pady=(CELL, 0))
        self.actions.columnconfigure((0, 1), weight=1, uniform="action")
        self.reply_label = tk.Label(self, background=PLATE, borderwidth=0, anchor="w", justify="left")
        self.reply_label.pack(side="bottom", fill="x")

    def show(self, title, lines, actions, reply, width, force=False):
        """lines: (text, "lead" or "line"); actions: (label, words to say or "", callback)."""
        view = self.view
        key = (title, tuple(lines), tuple((a[0], a[1]) for a in actions), reply, width, view.scale)
        if key == self._key and not force:
            return
        self._key = key
        lettering.letter(self.title_label, title, view._size(40), INK, weight="bold")
        for child in self.lines.winfo_children():
            child.destroy()
        for text, role in lines:
            label = tk.Label(self.lines, background=PLATE, borderwidth=0, anchor="w", justify="left")
            size, color = (view._size(34), INK) if role == "lead" else (view._size(24), SLATE)
            lettering.letter(label, text, size, color, width=width, max_lines=3)
            label.pack(fill="x", pady=(0, CELL // 3))
        for button in self._buttons:
            button._ring.destroy()
        self._buttons = []
        compact = view._compact()
        column_width = (width - CELL // 2) // 2 - 12
        for index, (label, say, callback) in enumerate(actions):
            subtitle = "" if compact else (f"Say \u201cADA, {say}\u201d" if say else "")
            button = view._card_button(self.actions, label, subtitle, column_width, callback)
            button._ring.grid(row=index // 2, column=index % 2, sticky="w", padx=(0, CELL // 2), pady=(0, CELL // 2))
            self._buttons.append(button)
        if reply:
            lettering.letter(self.reply_label, reply, view._size(26), INK, width=width, max_lines=3)
        else:
            self.reply_label.configure(image="", text="")


class AccessibleView(tk.Frame):
    """The home screen: a rail of rooms (Practice, Piano, Pieces, Camera, Voice & AI), one open at a time."""

    def __init__(self, parent, *, submit, talk, stop, tools, status):
        super().__init__(parent, background=PLATE)
        self._submit = submit
        self._closed = False
        self.status = status
        self.scale = 1.0
        self._smooth = lettering.available()
        self._said_text = ""
        self._takes = []
        self._take_images = []
        self._rendered = {}
        self._animation = None
        self._reveal = None
        self._width = 0
        self._compact_drawn = False
        self._context = {"piano": "", "piece": ""}
        self._typed = tk.StringVar(self)
        self.room = "practice"
        self._rail_status = {key: ("", False) for key, _ in ROOMS}
        self._room_specs = {}
        self._view_width = 0

        # The rail: ADA's mark, then one door per room, each with a lamp and its live status.
        self.rail = tk.Frame(self, background=RAISED)
        self.rail.pack(side="left", fill="y")
        mark_row = tk.Frame(self.rail, background=RAISED)
        mark_row.pack(side="top", fill="x", padx=CELL // 2 + 6, pady=(CELL, CELL // 2))
        self.mark = tk.Canvas(mark_row, background=RAISED, highlightthickness=0, borderwidth=0, takefocus=False,
                              width=1, height=1)
        self.mark.pack(side="left")
        self.word = tk.Label(mark_row, text="ADA", background=RAISED, foreground=INK, borderwidth=0)
        self.word.pack(side="left", padx=(CELL // 2, 0))
        self.rail_buttons = {}
        for key, label in ROOMS:
            button = self._card_button(self.rail, label, "", 240, lambda key=key: self.open_room(key), ground=RAISED)
            button._ring.pack(side="top", fill="x", padx=CELL // 3, pady=(0, CELL // 4))
            self.rail_buttons[key] = button
        self.tools_button = self._button(self.rail, "All settings", "F3", tools, ground=RAISED)
        self.tools_button._ring.pack(side="bottom", anchor="w", padx=CELL // 3, pady=(0, CELL))

        main = self._main = tk.Frame(self, background=PLATE)
        main.pack(side="left", fill="both", expand=True, padx=CELL, pady=CELL)
        self.bind("<Configure>", self._view_resized)
        rooms = self._rooms = tk.Frame(main, background=PLATE)
        inner = self._inner = tk.Frame(rooms, background=PLATE)
        inner.pack(fill="both", expand=True)
        inner.bind("<Configure>", self._resized)
        self.rooms = {"practice": inner}
        for key, _ in ROOMS[1:]:
            self.rooms[key] = Room(self, rooms)

        state = tk.Frame(main, background=PLATE)
        self.lamp = tk.Canvas(state, background=PLATE, highlightthickness=0, borderwidth=0, takefocus=False,
                              width=1, height=1)
        self.lamp.pack(side="left", padx=(0, CELL // 2))
        self.state_label = tk.Label(state, text="", background=PLATE, foreground=INK, borderwidth=0)
        self.state_label.pack(side="left")
        self.status_label = tk.Label(main, textvariable=status, anchor="w", justify="left",
                                     background=PLATE, foreground=SLATE, borderwidth=0)

        bar = tk.Frame(inner, background=PLATE)
        self.box = tk.Frame(bar, background=RAISED, highlightthickness=3, highlightbackground=EDGE,
                            highlightcolor=INK, height=64)
        self.box.pack(fill="x")
        hidden = RAISED if self._smooth else INK  # the large overlay shows the typed text instead
        self.entry = tk.Entry(self.box, name="message", textvariable=self._typed, background=RAISED,
                              foreground=hidden, insertbackground=hidden, selectforeground=hidden,
                              selectbackground=RAISED if self._smooth else EDGE, relief="flat", borderwidth=0,
                              highlightthickness=0, font=("", 13))
        self.entry.place(x=0, y=0, relwidth=1, relheight=1)
        self.entry.bind("<Return>", self._send)
        self.typed = tk.Label(self.box, background=RAISED, borderwidth=0, anchor="w", takefocus=False)
        if self._smooth:
            self.typed.place(x=CELL // 2, rely=0.5, anchor="w")
            self.typed.bind("<Button-1>", self._focus_entry)
        for sequence in ("<KeyRelease>", "<ButtonRelease-1>"):
            self.entry.bind(sequence, self._show_typed, add="+")
        self.entry.bind("<FocusIn>", lambda event: self._entry_focus(True), add="+")
        self.entry.bind("<FocusOut>", lambda event: self._entry_focus(False), add="+")
        self._typed_trace = self._typed.trace_add("write", self._show_typed)
        controls = tk.Frame(bar, background=PLATE)
        controls.pack(fill="x", pady=(CELL // 2, 0))
        self.talk_button = self._button(controls, "Talk to ADA", "F1", talk, primary=True)
        self.talk_button._ring.pack(side="left", padx=(0, CELL // 2))
        self.stop_button = self._button(controls, "Stop", "Esc", stop)
        self.stop_button._ring.pack(side="left")

        takes = self._takes_frame = tk.Frame(inner, background=PLATE)
        self.piece_label = tk.Label(takes, text="", anchor="w", background=PLATE, foreground=SLATE, borderwidth=0)
        self.piece_label.pack(fill="x")
        self.background = tk.Canvas(takes, background=PLATE, highlightthickness=0, borderwidth=0,
                                    takefocus=False, height=1)
        self.background.pack(fill="x", pady=(CELL // 3, 0))
        self.background.bind("<Configure>", self._takes_resized)
        self._takes_width = 0

        words = self._words = tk.Frame(inner, background=PLATE)
        self.transcript = tk.Text(words, name="conversation", height=4, wrap="word", state="disabled",
                                  takefocus=True, background=PLATE, foreground=INK, insertbackground=PLATE,
                                  selectbackground=EDGE, selectforeground=INK, relief="flat", borderwidth=0,
                                  highlightthickness=3, highlightbackground=PLATE, highlightcolor=INK,
                                  font=("", 13), padx=0, pady=CELL // 4, cursor="arrow")
        self.transcript.tag_configure("speaker", foreground=INK)
        # The plate shows only ADA's latest words; every turn's text stays here, hidden, for copying and tests.
        # The full conversation lives in Tools > ADA Coach.
        self.transcript.tag_configure("said", elide=self._smooth)
        if self._smooth:
            self._said = tk.PhotoImage(master=self.transcript, width=1, height=1)
            self._said_note = tk.PhotoImage(master=self.transcript, width=1, height=1)
            self.transcript.configure(state="normal")
            self.transcript.image_create("1.0", image=self._said, name="said", align="top")
            self.transcript.insert("end", "\n")  # visible: the measured note sits on its own line
            self.transcript.image_create("end", image=self._said_note, name="said_note", align="top")
            self.transcript.configure(state="disabled")
        self.transcript.pack(fill="both", expand=True)
        self.transcript.bind("<Tab>", self._next_control)
        self.transcript.bind("<Shift-Tab>", self._previous_control)
        try:
            self.transcript.bind("<ISO_Left_Tab>", self._previous_control)  # X11 sends this for Shift+Tab
        except tk.TclError:
            pass  # Windows and macOS Tk have no such keysym; <Shift-Tab> covers them
        self.transcript.bind("<Configure>", lambda event: self._show_words())

        # Packing order is priority: controls, state and ADA's words keep their room first;
        # the takes, packed last, yield space before ADA's words do.
        bar.pack(side="bottom", fill="x", pady=(CELL // 2, 0))
        from ada_piano.note_reader.practice import PracticePanel
        self.practice = PracticePanel(inner, self)
        self.practice.pack(side="top", fill="both", expand=True)
        rooms.pack(side="top", fill="both", expand=True)

        self._status_trace = status.trace_add("write", self._show_status)
        self._render_all()

    # Construction helpers

    def _button(self, parent, label, key, command, *, primary=False, ground=PLATE):
        ring = tk.Frame(parent, background=ground, padx=3, pady=3)  # turns ivory while the button has focus
        button = tk.Button(ring, text=label, command=command, takefocus=True, relief="flat", borderwidth=0,
                           highlightthickness=3, highlightbackground=ground, highlightcolor=ground,
                           background=INK if primary else RAISED, foreground=PLATE if primary else INK,
                           activebackground="#FFFFFF" if primary else RAISED_HOVER,
                           activeforeground=PLATE if primary else INK, cursor="hand2",
                           padx=CELL // 2, pady=CELL // 4, font=("", 11, "bold"))
        button.pack()
        button.bind("<FocusIn>", lambda event: ring.configure(background=INK), add="+")
        button.bind("<FocusOut>", lambda event: ring.configure(background=ground), add="+")
        button._ring, button._label, button._key, button._primary = ring, label, key, primary
        return button

    def _card_button(self, parent, title, subtitle, width, command, *, ground=PLATE):
        """A big button whose face is a card: bold title over one line of status or words to say."""
        ring = tk.Frame(parent, background=ground, padx=3, pady=3)
        button = tk.Button(ring, text=title, command=command, takefocus=True, relief="flat", borderwidth=0,
                           highlightthickness=3, highlightbackground=ground, highlightcolor=ground,
                           background=RAISED if ground == PLATE else ground, activebackground=RAISED_HOVER,
                           foreground=INK, activeforeground=INK, cursor="hand2", anchor="w", font=("", 11, "bold"))
        button.pack(fill="x")
        button.bind("<FocusIn>", lambda event: ring.configure(background=INK), add="+")
        button.bind("<FocusOut>", lambda event: ring.configure(background=ground), add="+")
        button._ring, button._ground = ring, ground
        self._face(button, title, subtitle, width)
        return button

    def _face(self, button, title, subtitle, width, *, lamp=None, outline=None):
        if not self._smooth:
            button.configure(text=f"{title}: {subtitle}" if subtitle else title, image="")
            return
        image = lettering.card(button, title, subtitle, width, self._size(30 if lamp else 26),
                               self._size(21 if lamp else 20), INK, SLATE, lamp=lamp, lamp_color=INK if lamp == "on"
                               else SLATE, outline=outline, padding=(round(self._size(14)), round(self._size(12))))
        button.configure(image=image, compound="none", text=title)
        button._lettering = image

    def _rail_width(self):
        width = self.winfo_width()
        return int(min(max((width if width > 50 else 928) * 0.24, 190 * self.scale),
                       280 * self.scale)) - CELL

    def _render_rail(self):
        width = self._rail_width()
        compact = self._compact()
        for key, label in ROOMS:
            status, ready = self._rail_status[key]
            button = self.rail_buttons[key]
            selected = key == self.room
            button.configure(background=RAISED_HOVER if selected else RAISED)
            self._face(button, label, "" if compact else status, width, lamp="on" if ready else "off",
                       outline=INK if selected else None)

    def _view_resized(self, event):
        if event.widget is self and abs(event.width - self._view_width) >= CELL // 2:
            self._view_width = event.width
            self._render_rail()
            self._show_room()

    def open_room(self, key):
        """Show one room; the rail marks it. Practice is home; Escape returns there."""
        if self._closed or key not in self.rooms:
            return
        self.rooms[self.room].pack_forget()
        self.room = key
        self.rooms[key].pack(fill="both", expand=True)
        self._render_rail()
        self._show_room()

    def set_rail(self, key, status, ready):
        if self._closed or self._rail_status.get(key) == (status, ready):
            return
        self._rail_status[key] = (status, ready)
        self._render_rail()

    def set_room(self, key, title, lines, actions):
        """The window describes a room's content; only the open room is drawn."""
        if self._closed:
            return
        self._room_specs[key] = (title, list(lines), list(actions))
        if key == self.room:
            self._show_room()

    def _show_room(self, force=False):
        if self.room == "practice" or self.room not in self._room_specs:
            return
        title, lines, actions = self._room_specs[self.room]
        width = self._text_width()
        self.rooms[self.room].show(title, lines, actions, self._said_text and f"ADA: {self._said_text}", width,
                                   force=force)

    def _size(self, base):
        return base * self.scale

    def _text_width(self):
        width = self._main.winfo_width()
        return (width if width > 50 else 560) - 8

    # Rendering

    def _render_all(self):
        if self._closed:
            return
        self._rendered.clear()
        self._draw_mark()
        lettering.letter(self.word, "ADA", self._size(30), INK, weight="bold", tracking=round(6 * self.scale))
        self._show_context()
        self._show_status()
        for button in (self.talk_button, self.stop_button, self.tools_button):
            self._letter_button(button)
        self.box.configure(height=int(round(66 * self.scale)))
        self._show_typed()
        self._show_words(force=True)
        self._draw_takes()
        self._render_rail()
        self._show_room(force=True)

    def _letter_button(self, button):
        if not self._smooth:
            button.configure(text=f"{button._label} ({button._key})")
            return
        ink, hint = (PLATE, "#4A4F5C") if button._primary else (INK, SLATE)
        image = lettering.photo_runs(button, ((button._label, round(self._size(26)), ink, "bold"),
                                              (button._key, round(self._size(20)), hint, "regular")),
                                     round(self._size(14)), padding=(round(self._size(26)), round(self._size(15))))
        button.configure(image=image, compound="none", text=button._label)
        button._lettering = image

    def _flat_dot(self, canvas, x, y, radius, color, keep, *, hollow=False, line=0):
        """A flat dot (or hollow ring) with smooth edges; Tk's own ovals are jagged."""
        if self._smooth:
            image = lettering.shape(canvas, "ring" if hollow else "dot", radius * 2, radius * 2, color, line=line)
            keep.append(image)
            canvas.create_image(x, y, image=image)
        elif hollow:
            canvas.create_oval(x - radius + line / 2, y - radius + line / 2, x + radius - line / 2,
                               y + radius - line / 2, outline=color, width=line)
        else:
            canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="")

    def _draw_mark(self):
        """ADA in Grade 1 braille dots, as on a tactile sign."""
        canvas = self.mark
        canvas.delete("all")
        self._mark_images = []
        radius = 6.5 * self.scale
        pitch, gap = radius * 3.0, radius * 2.6
        cell = pitch + radius * 2
        for index, dots in enumerate(BRAILLE_ADA):
            left = radius + 2 + index * (cell + gap)
            for dot in dots:
                column, row = (0 if dot <= 3 else 1), (dot - 1) % 3
                self._flat_dot(canvas, left + column * pitch, radius + 2 + row * pitch, radius, INK,
                               self._mark_images)  # on the raised rail
        canvas.configure(width=int(len(BRAILLE_ADA) * (cell + gap) - gap + 4),
                         height=int(radius * 2 + pitch * 2 + 6))

    def _draw_lamp(self, live):
        size = int(round(32 * self.scale))
        canvas = self.lamp
        canvas.delete("all")
        self._lamp_images = []
        canvas.configure(width=size, height=size)
        radius = size * 0.34
        if live:
            self._flat_dot(canvas, size / 2, size / 2, radius, AMBER, self._lamp_images)
        else:
            self._flat_dot(canvas, size / 2, size / 2, radius, SLATE, self._lamp_images, hollow=True,
                           line=max(3, size / 10))

    def _show_status(self, *args):
        if self._closed:
            return
        text = self.status.get()
        word, live = state_word(text)
        width = self._text_width()
        key = (text, self.scale, width, self._compact())
        if self._rendered.get("status") == key:
            return
        self._rendered["status"] = key
        lettering.letter(self.state_label, word, self._size(50), AMBER if live else INK, weight="bold")
        self._draw_lamp(live)
        # Voice status stays available as native text without displacing the piano.
        self.status_label.pack_forget()

    def _show_context(self):
        width = self._text_width()
        key = (self._context["piano"], self._context["piece"], self.scale, width)
        if self._rendered.get("context") == key:
            return
        self._rendered["context"] = key
        for label, text, size in ((self.piece_label, self._context["piece"], 24),):
            if text:
                lettering.letter(label, text, self._size(size), SLATE, width=width, max_lines=1)
            else:
                label.configure(image="", text="")

    def _entry_focus(self, focused):
        if not self._closed:
            self.box.configure(highlightbackground=INK if focused else EDGE)
            self._show_typed()

    def _show_typed(self, *args):
        if self._closed or not self._smooth:
            return
        text = self._typed.get()
        try:
            focused = self.focus_get() is self.entry
        except (KeyError, tk.TclError):
            focused = False
        if not text and not focused:
            image = lettering.photo(self.typed, PLACEHOLDER, self._size(26), SLATE)
        else:
            caret = self.entry.index("insert") if focused else None
            room = max(120, self.box.winfo_width() - CELL * 2)
            start = 0
            while caret is not None and start < caret and lettering.measure(text[start:caret], self._size(28)) > room:
                start += 1  # keep the caret in view while typing past the edge
            image = lettering.photo(self.typed, text[start:], self._size(28), INK,
                                    caret=None if caret is None else caret - start)
        self.typed.configure(image=image)
        self.typed._lettering = image

    def _focus_entry(self, event=None):
        if not self._closed:
            self.entry.focus_set()
            self.entry.icursor("end")
            self._show_typed()

    def _show_words(self, force=False):
        """ADA's latest words, filling the block (three lines at least), plus the measured note in compact windows."""
        if self._closed or not self._smooth:
            return
        transcript = self.transcript
        size = self._size(34)
        step = round(size * 1.22)
        ascent, descent = lettering.face(size).getmetrics()
        linespace = tkfont.Font(font=transcript.cget("font")).metrics("linespace") or 13
        minimum = max(2, -(-(step * (WORDS_LINES - 1) + ascent + descent + 4) // linespace))
        if int(transcript.cget("height")) != minimum:
            transcript.configure(height=minimum)  # the packer never gives ADA's words less than this
        width = (transcript.winfo_width() if transcript.winfo_width() > 50 else self._text_width()) - 12
        room = transcript.winfo_height() - 2 * (int(transcript.cget("pady")) + 3)
        note = ""
        if self._compact() and self._takes:
            take = self._takes[-1]
            note = f"{take['score']} · {take['note']}"  # one line, so ADA's words keep their room
        key = (self._said_text, note, self.scale, width, room)
        if not force and self._rendered.get("words") == key:
            return
        self._rendered["words"] = key
        note_image = (lettering.photo(transcript, note, self._size(26), SLATE, width=width, max_lines=2)
                      if note else tk.PhotoImage(master=transcript, width=1, height=1))
        if room > 50 and note:
            room -= note_image.height() + CELL // 3
        # Largest size, from 34 down to 24 at this scale, at which all of ADA's words fit; only below that,
        # the words end with an ellipsis. The measured note is never clipped.
        size, lines = self._size(34), WORDS_LINES
        if room > 50 and self._said_text:
            for candidate in range(round(self._size(34)), round(self._size(24)) - 1, -1):
                step = round(candidate * 1.22)
                ascent, descent = lettering.face(candidate).getmetrics()
                wrapped = len(lettering.wrap(self._said_text, candidate, width))
                size, lines = candidate, max(1, (room - ascent - descent) // step + 1)
                if (wrapped - 1) * step + ascent + descent <= room:
                    lines = wrapped
                    break
        self._said = (lettering.photo(transcript, self._said_text, size, INK, width=width, max_lines=lines)
                      if self._said_text else tk.PhotoImage(master=transcript, width=1, height=1))
        self._said_note = note_image
        transcript.image_configure("said", image=self._said)
        transcript.image_configure("said_note", image=self._said_note, pady=CELL // 6 if note else 0)
        transcript.yview_moveto(0)

    def _compact(self):
        height = self.winfo_height()
        return 1 < height < COMPACT_HEIGHT * self.scale

    def _resized(self, event):
        compact = self._compact()
        if abs(event.width - self._width) < CELL // 2 and compact == self._compact_drawn:
            return
        self._width, self._compact_drawn = event.width, compact
        self._rendered.pop("status", None)
        self._show_words(force=True)
        self._show_status()
        self._show_context()
        self._draw_takes()

    def _takes_resized(self, event):
        if abs(event.width - self._takes_width) >= 8:  # height changes come from drawing; ignore them
            self._takes_width = event.width
            self._draw_takes()

    def _draw_takes(self, reveal=None):
        """Emboss the latest takes: one dot per note, grouped by measure, last take faded above."""
        if self._closed:
            return
        canvas = self.background
        canvas.delete("all")
        self._take_images = []
        width = canvas.winfo_width() if canvas.winfo_width() > 50 else self._text_width()
        if not self._takes:
            if self._context["piece"] and self._smooth:
                image = lettering.photo(canvas, 'No take yet. Say "record" when you are ready.',
                                        self._size(22), SLATE, width=width)
                self._take_images.append(image)
                canvas.create_image(0, 0, image=image, anchor="nw")
                canvas.configure(height=image.height())
            else:
                canvas.configure(height=1)
            return
        if not self._smooth:  # without Pillow: the same evidence as plain Tk text
            lines = [f"{'This take' if index == len(self._takes) - 1 else 'Last take'}: {take['score']}"
                     for index, take in enumerate(self._takes)] + [self._takes[-1]["note"]]
            item = canvas.create_text(0, 0, text="\n".join(line for line in lines if line), anchor="nw",
                                      fill=INK, width=width, font=("", 13))
            box = canvas.bbox(item)
            canvas.configure(height=(box[3] - box[1] + 4) if box else 1)
            return
        compact = self._compact()
        rows = self._takes
        labels = [lettering.photo(canvas, text, self._size(22), SLATE) for text in ("Last take", "This take")]
        scores = [lettering.photo(canvas, take["score"], self._size(26 if index < len(rows) - 1 else 40), INK
                                  if index == len(rows) - 1 else SLATE, weight="bold")
                  for index, take in enumerate(rows)]
        self._take_images.extend(labels + scores)
        label_width = max(image.width() for image in labels) + CELL // 2
        score_width = max(image.width() for image in scores) + CELL // 2
        room = max(120, width - label_width - score_width)
        y = 0
        for index, take in enumerate(rows):
            current = index == len(rows) - 1
            cells = take["cells"]
            notes = sum(len(cell["dots"]) for cell in cells)
            measures = max(1, len(cells))
            # dot, gap within a measure, ring padding and gap between measures, all from one diameter
            factor = notes + 0.42 * (notes - measures) + 0.76 * measures + 0.9 * (measures - 1)
            fit = room / max(1, factor)
            floor = self._size(9 if compact else 18)
            diameter = max(floor, min(self._size(28), fit))
            lines = 1 if compact or fit >= floor else -(-factor * diameter // room)
            per_line = -(-measures // max(1, int(lines)))  # balanced: 8 measures on 2 lines is 4 + 4
            if compact and fit < floor:
                diameter = fit  # one honest row; the window is too small for more
            gap, pad, between = diameter * 0.42, diameter * 0.38, diameter * 0.9
            line_height = diameter + pad * 2 + self._size(8)
            label = labels[1 if current else 0]
            canvas.create_image(0, y + line_height / 2, image=label, anchor="w")
            x, top = label_width, y
            shown = len(cells) if (not current or reveal is None) else reveal
            for position, cell in enumerate(cells):
                span = len(cell["dots"]) * diameter + (len(cell["dots"]) - 1) * gap + pad * 2
                if position and position % per_line == 0:
                    x, top = label_width, top + line_height  # wrap whole measures, never shrink below legibility
                if position < shown:
                    if current and cell["ring"]:
                        self._ring(canvas, x, top + self._size(2), x + span, top + line_height - self._size(6))
                    for count, dot in enumerate(cell["dots"]):
                        cx = x + pad + count * (diameter + gap) + diameter / 2
                        self._dot(canvas, cx, top + line_height / 2 - self._size(2),
                                  diameter / 2 * (1 if current else 0.74), dot, current)
                x += span + between
            canvas.create_image(width, y + line_height / 2, image=scores[index], anchor="e")
            y = top + line_height + self._size(6)
            if current and take["note"]:
                note = lettering.photo(canvas, take["note"], self._size(24), INK, width=width)
                self._take_images.append(note)
                canvas.create_image(label_width, y, image=note, anchor="nw")
                y += note.height()
        canvas.configure(height=int(y) + 2)

    def _dot(self, canvas, x, y, radius, state, current):
        color = INK if current else FADED
        if state == "ok":
            self._flat_dot(canvas, x, y, radius, color, self._take_images)
        elif state == "miss":
            self._flat_dot(canvas, x, y, radius, color, self._take_images, hollow=True, line=max(3, radius * 0.34))
        else:
            self._flat_dot(canvas, x, y, radius * 0.3, FADED, self._take_images)

    def _ring(self, canvas, left, top, right, bottom):
        line = max(3, round(self._size(4)))
        radius = min(self._size(14), (bottom - top) / 2)
        if self._smooth:
            image = lettering.shape(canvas, "frame", right - left, bottom - top, AMBER, line=line, radius=radius)
            self._take_images.append(image)
            canvas.create_image(left, top, image=image, anchor="nw")
            return
        points = (left + radius, top, right - radius, top, right, top, right, top + radius, right, bottom - radius,
                  right, bottom, right - radius, bottom, left + radius, bottom, left, bottom, left, bottom - radius,
                  left, top + radius, left, top)
        canvas.create_polygon(points, smooth=True, fill="", outline=AMBER, width=line)

    # Public surface used by the window and tests

    def append(self, speaker, text):
        """Keep every turn as native text (copying, tests, keyboards); show ADA's latest words large."""
        if self._closed:
            return
        transcript = self.transcript
        transcript.configure(state="normal")
        transcript.insert("end", f"{speaker}: ", ("speaker", "said"))
        transcript.insert("end", f"{text}\n\n", ("said",))
        if int(transcript.index("end-1c").split(".")[0]) > 300:
            transcript.delete("2.1" if self._smooth else "1.0", "100.0")  # the two image lines stay
        transcript.configure(state="disabled")
        if speaker == "ADA":
            self._said_text = text
            self._show_words()
            self._show_room()
        if not self._smooth:
            transcript.see("end")

    def show_take(self, cells, correct, expected, *, key=None, note=""):
        """Emboss a scored take; the previous take of the same passage stays faded above it."""
        if self._closed:
            return
        take = {"key": key, "cells": cells, "score": f"{correct} / {expected}", "note": note}
        same = key is not None and self._takes and self._takes[-1]["key"] == key
        self._takes = ([self._takes[-1]] if same else []) + [take]
        if self._animation is not None:  # a take arriving mid-animation restarts it, never stacks timers
            self.after_cancel(self._animation)
            self._animation = None
        self._press(0)
        self._show_words()

    def _press(self, shown):
        """The signature moment: the new take presses in measure by measure."""
        if self._closed:
            return
        self._animation = None
        cells = self._takes[-1]["cells"] if self._takes else []
        if shown >= len(cells):
            self._draw_takes()
            return
        self._draw_takes(reveal=shown)
        self._animation = self.after(70, self._press, shown + 1)

    def set_context(self, *, piano=None, piece=None):
        if self._closed:
            return
        changed = {name for name, value in (("piano", piano), ("piece", piece))
                   if value is not None and value != self._context[name]}
        for name in changed:
            self._context[name] = piano if name == "piano" else piece
        if changed:
            self._show_context()
        if "piece" in changed:
            self._takes = []
            self._draw_takes()

    def change_scale(self, step):
        """Bigger (+1), smaller (-1) or normal (0) text; returns the new scale."""
        if step == 0:
            self.scale = 1.0
        else:
            index = min(range(len(SCALES)), key=lambda i: abs(SCALES[i] - self.scale))
            self.scale = SCALES[max(0, min(len(SCALES) - 1, index + step))]
        if not self._closed:
            self._render_all()
        return self.scale

    def _send(self, event=None):
        text = self.entry.get().strip()
        if text and not self._closed:
            self._submit(text)
            self.entry.delete(0, "end")
        return "break"

    def focus_message(self):
        if not self._closed:
            self.entry.focus_set()

    @staticmethod
    def _next_control(event):
        event.widget.tk_focusNext().focus_set()
        return "break"

    @staticmethod
    def _previous_control(event):
        event.widget.tk_focusPrev().focus_set()
        return "break"

    def close(self):
        """Stop timers and late updates before the parent destroys the window."""
        if self._closed:
            return
        self._closed = True
        if self._animation is not None:
            self.after_cancel(self._animation)
            self._animation = None
        for variable, trace in ((self.status, self._status_trace), (self._typed, self._typed_trace)):
            try:
                variable.trace_remove("write", trace)
            except (tk.TclError, ValueError):
                pass
