"""A display-only piano keyboard driven by received MIDI note state."""

import tkinter as tk


class PianoKeyboard(tk.Canvas):
    WHITE = "#f8fafc"
    BLACK = "#172033"
    PRESSED = "#22c55e"
    LAST = "#2563eb"
    BLACK_NOTES = {1, 3, 6, 8, 10}

    def __init__(self, parent, **kwargs):
        super().__init__(parent, height=190, background="#dbe3ed",
                         highlightthickness=0, **kwargs)
        # Match the YPT-300's 61-key layout. Shift the displayed range if MIDI
        # transposition produces notes outside it, including MIDI 0 and 127.
        self.first_note = 36
        self.last_note = 96
        self.key_items: dict[int, int] = {}
        self.label_items: dict[int, int] = {}
        self.active: set[int] = set()
        self.last_played: int | None = None
        self.bind("<Configure>", self._draw)

    @staticmethod
    def name(note):
        return ("C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B")[note % 12] + str(note // 12 - 1)

    def show_notes(self, notes, last_played=None):
        active = set(notes)
        redraw = False
        if last_played is not None and not self.first_note <= last_played <= self.last_note:
            self.first_note = max(0, min(67, (last_played // 12 - 2) * 12))
            self.last_note = self.first_note + 60
            redraw = True
        if active == self.active and last_played == self.last_played and not redraw:
            return
        self.active = active
        self.last_played = last_played
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
        self._paint()

    def _paint(self):
        for note, item in self.key_items.items():
            black = note % 12 in self.BLACK_NOTES
            held = note in self.active
            fill = self.PRESSED if held else self.BLACK if black else self.WHITE
            self.itemconfigure(item, fill=fill,
                               outline=self.LAST if note == self.last_played else "#94a3b8" if not black else self.BLACK,
                               width=3 if note == self.last_played else 1)
            self.itemconfigure(self.label_items[note], fill="#10251a" if held else "white" if black else "#172033")
