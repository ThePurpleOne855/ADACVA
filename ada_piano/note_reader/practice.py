"""Live score following and the piano/camera practice surface."""

from io import BytesIO
import math
import tkinter as tk
from tkinter import ttk

from ada_piano.ai_tutor import Tutor
from ada_piano.sound_sensor import NoteEvent
from ada_piano.note_reader.keyboard import PianoKeyboard
from ada_piano.note_reader import lettering


class LivePractice:
    """Follow score attacks with the same chord rules as guided practice."""

    def __init__(self):
        self.exercise = None
        self.token = None
        self.tutor = None
        self.verdicts = {}
        self.message = "Load a piece to check your notes."

    def sync(self, exercise, token):
        if exercise is self.exercise and token == self.token:
            return
        self.exercise, self.token = exercise, token
        self.restart()

    def restart(self):
        self.tutor = Tutor(self.exercise) if self.exercise is not None else None
        self.verdicts.clear()
        self.message = "Play the highlighted notes." if self.tutor else "Load a piece to check your notes."

    @property
    def expected(self):
        if self.tutor is None or self.tutor.complete:
            return ()
        return self.exercise.events[self.tutor.position].pitches

    def observe(self, event, source):
        if source == "Reference":
            return
        key = (event.channel, event.note)
        if event.kind == "off":
            self.verdicts.pop(key, None)
        if source != "Piano":
            self.message = "Simulated input · not graded"
            return
        if self.tutor is None or self.tutor.complete:
            return
        if event.kind == "on":
            self.verdicts[key] = event.note in self.expected
        result = self.tutor.evaluate(NoteEvent(event.note, event.velocity, event.timestamp, "midi",
                                               "note_on" if event.kind == "on" else "note_off",
                                               event.channel - 1))
        if result:
            played = " + ".join(PianoKeyboard.name(n) for n in result.played_pitches)
            self.message = (f"Correct: {played}" if result.type == "correct" else
                            f"Wrong note: {played}" if result.type in {"wrong_note", "unexpected_note"} else
                            "Release extra keys" if result.type == "extra_key" else
                            "Release and retry together")
            if result.type in {"chord_attack_spread", "replay_required"}:
                for held in self.verdicts:
                    if held[1] in result.played_pitches:
                        self.verdicts[held] = False
        elif event.kind == "on":
            self.message = "Correct pitch · finish chord"

    def feedback(self, held):
        return {note: self.verdicts.get((channel, note)) for channel, note in held}


class PracticePanel(tk.Frame):
    def __init__(self, parent, view):
        from ada_piano.note_reader.accessible import PLATE, RAISED, INK, SLATE
        super().__init__(parent, background=PLATE)
        self.view = view
        self.follow = LivePractice()
        self._frame = None
        self._photo = None
        self._render_key = None
        self._camera_on = False
        self._camera_status = "Camera off. Start camera to see your hands."
        self._labels = {}
        self.viewport = tk.Canvas(self, background=PLATE, highlightthickness=0, width=1, height=1,
                                  takefocus=True)
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.viewport.yview)
        self.viewport.configure(yscrollcommand=self.scroll.set)
        self.viewport.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.viewport, background=PLATE)
        self._body_item = self.viewport.create_window(0, 0, window=self.body, anchor="nw")
        self.body.grid_columnconfigure(0, weight=3, uniform="practice")
        self.body.grid_columnconfigure(1, weight=2, uniform="practice")
        self.body.grid_rowconfigure(1, weight=1)
        self.viewport.bind("<Configure>", self._resized)
        self.viewport.bind("<Next>", lambda e: self.viewport.yview_scroll(1, "pages"))
        self.viewport.bind("<Prior>", lambda e: self.viewport.yview_scroll(-1, "pages"))
        self.title = tk.Label(self.body, background=PLATE, foreground=INK, anchor="w")
        self.title.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        camera = tk.Frame(self.body, background=RAISED)
        camera.grid(row=1, column=0, sticky="nsew", padx=(0, 18))
        self.preview = tk.Canvas(camera, background=RAISED, highlightthickness=0, width=1, height=1)
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Configure>", lambda e: self._draw_camera())
        self.camera_status = tk.Label(camera, background=RAISED, foreground=SLATE, anchor="w", justify="left")
        self.camera_status.pack(fill="x", padx=12, pady=8)
        side = tk.Frame(self.body, background=PLATE)
        side.grid(row=1, column=1, sticky="nsew")
        actions = tk.Frame(side, background=PLATE)
        actions.pack(side="bottom", fill="x")
        self.camera_button = view._button(actions, "Start camera", "F7", lambda: None)
        self.camera_button._ring.pack(anchor="w", pady=(0, 6))
        self.restart_button = view._button(actions, "Restart notes", "", self.follow.restart)
        self.restart_button._ring.pack(anchor="w")
        for name in ("progress", "expected", "played", "feedback"):
            label = tk.Label(side, background=PLATE, foreground=INK, anchor="w", justify="left")
            label.pack(fill="x", pady=(0, 6))
            self._labels[name] = label
        self.legend = tk.Label(self.body, background=PLATE, foreground=SLATE, anchor="w")
        self.legend.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 6))
        self.keyboard = PianoKeyboard(self.body)
        self.keyboard.grid(row=3, column=0, columnspan=2, sticky="ew")
        for widget in (self.viewport, self.body, self.preview, self.keyboard, self.title,
                       self.legend, self.camera_status, *self._labels.values()):
            widget.bind("<MouseWheel>", lambda e: self.viewport.yview_scroll(-1 if e.delta > 0 else 1, "units"))
            widget.bind("<Button-4>", lambda e: self.viewport.yview_scroll(-1, "units"))
            widget.bind("<Button-5>", lambda e: self.viewport.yview_scroll(1, "units"))
        for button in (self.camera_button, self.restart_button):
            button.bind("<FocusIn>", self._reveal_control, add="+")
        self.render("No piece loaded", (), None, (), False, False)

    def _letter(self, widget, text, size, color=None):
        from ada_piano.note_reader.accessible import INK
        width = max(100, self.body.winfo_width())
        if widget in self._labels.values():
            width = max(100, int(width * 0.4) - 4)
        elif widget is self.camera_status:
            width = max(100, int(width * 0.6) - 42)
        lettering.letter(widget, text, self.view._size(size), color or INK,
                         width=width, max_lines=3)

    def _resized(self, event=None):
        height = max(self.viewport.winfo_height(), round(540 * self.view.scale))
        width = max(1, self.viewport.winfo_width())
        self.viewport.itemconfigure(self._body_item, width=width, height=height)
        self.viewport.configure(scrollregion=(0, 0, width, height))
        if height > self.viewport.winfo_height():
            self.scroll.pack(side="right", fill="y")
        else:
            self.scroll.pack_forget()
        self._render_key = None
        self.keyboard.configure(height=120 if height < 650 else 170)

    def _reveal_control(self, event):
        y = event.widget.winfo_rooty() - self.body.winfo_rooty()
        top = self.viewport.canvasy(0)
        if y < top or y + event.widget.winfo_height() > top + self.viewport.winfo_height():
            self.viewport.yview_moveto(y / max(1, self.body.winfo_height()))

    def render(self, title, held, last, reference, connected, demo):
        from ada_piano.note_reader.accessible import SLATE
        held = tuple(held)
        if self._render_key is None or self._render_key[-2] != self.view.scale:
            self._resized()
        follower = self.follow
        expected = follower.expected
        self.keyboard.show_notes((note for _, note in held), last, reference or expected,
                                 follower.feedback(held) if not demo else {})
        tutor = follower.tutor
        if tutor is None:
            progress, next_notes = "Choose a piece in Pieces", "No score loaded"
        elif tutor.complete:
            progress, next_notes = "Passage complete", "All notes played"
        else:
            event = follower.exercise.events[tutor.position]
            progress = f"Measure {event.measure or '—'} · Step {tutor.position + 1} / {len(follower.exercise.events)}"
            next_notes = "Next: " + " + ".join(PianoKeyboard.name(n) for n in expected)
        played = "Playing: " + (" + ".join(PianoKeyboard.name(n) for n in sorted({n for _, n in held})) or "—")
        feedback = follower.message
        if demo:
            feedback = "Simulated input · not graded"
        elif not connected:
            feedback = "Connect your MIDI piano in Piano."
        elif reference:
            feedback = "Reference playing · listen first"
        key = (title, progress, next_notes, played, feedback, self.view.scale, self.body.winfo_width())
        if key != self._render_key:
            self._render_key = key
            self._letter(self.title, title or "No piece loaded", 26)
            for name, text, size in (("progress", progress, 21), ("expected", next_notes, 30),
                                     ("played", played, 24), ("feedback", feedback, 22)):
                self._letter(self._labels[name], text, size)
            self._letter(self.legend, "Green: correct   Red: retry   Blue: next / reference   Amber: ungraded", 18, SLATE)
            for button in (self.camera_button, self.restart_button):
                self._letter_action(button)
            self.camera_state(self._camera_status, self._camera_on, force=True)

    def _letter_action(self, button):
        from ada_piano.note_reader.accessible import INK
        text = button._label + (f" ({button._key})" if button._key else "")
        if lettering.available():
            photo = lettering.photo_runs(button, ((text, round(self.view._size(21)), INK, "bold"),),
                                         0, padding=(12, 8))
            button.configure(image=photo, compound="none", text=text)
            button._lettering = photo
        else:
            lettering.letter(button, text, self.view._size(21), INK, weight="bold")

    def camera_state(self, status, running, force=False):
        if not force and (status, running) == (self._camera_status, self._camera_on):
            return
        self._camera_status, self._camera_on = status, running
        self._letter(self.camera_status, status, 18)
        self.camera_button._label = "Stop camera" if running else "Start camera"
        self._letter_action(self.camera_button)
        if not running:
            self.clear_camera()

    def show_frame(self, frame):
        self._frame = frame
        if self.winfo_ismapped():
            self._draw_camera()

    def clear_camera(self):
        self._frame = self._photo = None
        self._draw_camera()

    def _draw_camera(self):
        from ada_piano.note_reader.accessible import SLATE
        canvas = self.preview
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        canvas.delete("all")
        if self._frame is None:
            text = "Hand tracking\nStart camera to see your hands"
            if lettering.available():
                self._photo = lettering.photo(canvas, text, self.view._size(22), SLATE, width=max(1, width - 24))
                canvas.create_image(width / 2, height / 2, image=self._photo)
            else:
                canvas.create_text(width / 2, height / 2, text=text, fill=SLATE, font=("", 13),
                                   justify="center", width=max(1, width - 24))
            return
        try:
            from PIL import Image, ImageTk
        except ImportError:
            photo = tk.PhotoImage(master=self, data=self._frame.ppm, format="PPM")
            self._photo = photo.subsample(max(1, math.ceil(max(photo.width() / width, photo.height() / height))))
        else:
            frame = self._frame
            picture = (Image.fromarray(frame.bgr[:, :, ::-1]) if frame.bgr is not None
                       else Image.open(BytesIO(frame.ppm)))
            scale = min(width / picture.width, height / picture.height)
            picture = picture.resize((max(1, int(picture.width * scale)), max(1, int(picture.height * scale))))
            self._photo = ImageTk.PhotoImage(picture, master=self)
        canvas.create_image(width / 2, height / 2, image=self._photo)
