"""Piano display for received notes and clickable audible references."""

import tkinter as tk


class PianoKeyboard(tk.Canvas):
    WHITE = "#f8fafc"
    BLACK = "#172033"
    PRESSED = "#22c55e"
    LAST = "#2563eb"
    REFERENCE = "#60a5fa"
    BLACK_NOTES = {1, 3, 6, 8, 10}

    def __init__(self, parent, on_note=None, **kwargs):
        super().__init__(parent, height=150, background="#dbe3ed",
                         highlightthickness=0, **kwargs)
        # Match the YPT-300's 61-key layout. Shift the displayed range if MIDI
        # transposition produces notes outside it, including MIDI 0 and 127.
        self.first_note = 36
        self.last_note = 96
        self.key_items: dict[int, int] = {}
        self.label_items: dict[int, int] = {}
        self.active: set[int] = set()
        self.last_played: int | None = None
        self.reference: set[int] = set()
        self.on_note = on_note
        self.bind("<Configure>", self._draw)
        self.bind("<Button-1>", self._click)

    def _click(self, event):
        # Rectangles and their labels share a note tag; the topmost item wins
        # where black keys overlap white keys.
        for item in reversed(self.find_overlapping(event.x, event.y, event.x, event.y)):
            for tag in self.gettags(item):
                if tag.startswith("note:") and self.on_note is not None:
                    self.on_note(int(tag.split(":")[1]))
                    return

    @staticmethod
    def name(note):
        return ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")[note % 12] + str(note // 12 - 1)

    def show_notes(self, notes, last_played=None, reference=()):
        active = set(notes)
        reference = set(reference)
        redraw = False
        focus_note = min(reference) if reference else last_played
        if focus_note is not None and not self.first_note <= focus_note <= self.last_note:
            self.first_note = max(0, min(67, (focus_note // 12 - 2) * 12))
            self.last_note = self.first_note + 60
            redraw = True
        if active == self.active and reference == self.reference and last_played == self.last_played and not redraw:
            return
        self.active = active
        self.last_played = last_played
        self.reference = reference
        if redraw:
            self._draw()
        else:
            self._paint()

    def _draw(self, event=None):
        self.delete("all")
        self.key_items.clear()
        self.label_items.clear()
        width = max(self.winfo_width(), 100)
        height = max(self.winfo_height(), 100)
        whites = [note for note in range(self.first_note, self.last_note + 1)
                  if note % 12 not in self.BLACK_NOTES]
        key_width = (width - 4) / len(whites)
        positions = {}
        for index, note in enumerate(whites):
            x = 2 + index * key_width
            positions[note] = x
            self.key_items[note] = self.create_rectangle(x, 2, x + key_width, height - 2,
                                                       outline="#94a3b8", fill=self.WHITE)
            self.label_items[note] = self.create_text(x + key_width / 2, height - 19,
                                                     text=self.name(note), font=("", 9))
            self.addtag_withtag(f"note:{note}", self.key_items[note])
            self.addtag_withtag(f"note:{note}", self.label_items[note])
        for note in range(self.first_note, self.last_note + 1):
            if note % 12 not in self.BLACK_NOTES:
                continue
            # Edge notes may be black when showing the topmost MIDI octave.
            center = positions.get(note - 1, 2 - key_width) + key_width
            x1 = max(2, center - key_width * 0.32)
            x2 = min(width - 2, center + key_width * 0.32)
            bottom = height * 0.62
            self.key_items[note] = self.create_rectangle(x1, 2, x2, bottom,
                                                       outline=self.BLACK, fill=self.BLACK)
            self.label_items[note] = self.create_text((x1 + x2) / 2, bottom - 17,
                                                     text=self.name(note), font=("", 7), fill="white")
            self.addtag_withtag(f"note:{note}", self.key_items[note])
            self.addtag_withtag(f"note:{note}", self.label_items[note])
        self._paint()

    def _paint(self):
        for note, item in self.key_items.items():
            black = note % 12 in self.BLACK_NOTES
            held = note in self.active
            reference = note in self.reference
            fill = self.PRESSED if held else self.REFERENCE if reference else self.BLACK if black else self.WHITE
            self.itemconfigure(item, fill=fill,
                               outline=self.LAST if note == self.last_played else "#94a3b8" if not black else self.BLACK,
                               width=3 if note == self.last_played else 1)
            self.itemconfigure(self.label_items[note], fill="#10251a" if held or reference else "white" if black else "#172033")
