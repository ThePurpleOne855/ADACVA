"""Audible-reference controls. MIDI scheduling stays in ReferencePlayer."""

import re
import tkinter as tk
from tkinter import ttk

from ada_piano.playback import PlaybackNote, ReferencePlayer, parse_note


class PlaybackPanel(ttk.Frame):
    def __init__(self, parent, player=None):
        super().__init__(parent, padding=10)
        self.player = player if player is not None else ReferencePlayer()
        self.output = tk.StringVar()
        self.pitch = tk.StringVar(value="C4")
        self.sequence = tk.StringVar(value="C4 D4 E4 F4 G4")
        self.tempo = tk.StringVar(value="90")
        self.beats = tk.StringVar(value="1")
        self.velocity = tk.StringVar(value="70")
        self.channel = tk.StringVar(value="1")
        self.status = tk.StringVar(value=self.player.status.detail)
        self._last_status = self.player.status
        self.active: set[tuple[int, int]] = set()
        self._build()

    def _build(self):
        ttk.Label(self, text="Listen to a reference on the Yamaha; then play it yourself.").pack(anchor="w")
        outputs = ttk.Frame(self)
        outputs.pack(fill="x", pady=5)
        ttk.Label(outputs, text="MIDI output").pack(side="left", padx=(0, 8))
        self.selector = ttk.Combobox(outputs, textvariable=self.output, state="readonly")
        self.selector.pack(side="left", fill="x", expand=True)
        ttk.Button(outputs, text="Refresh outputs", command=self.refresh).pack(side="left", padx=6)
        settings = ttk.Frame(self)
        settings.pack(fill="x", pady=5)
        for title, variable, start, end, step in (
            ("Tempo (BPM)", self.tempo, 20, 300, 5),
            ("Beats / note", self.beats, 0.05, 16, 0.25),
            ("Velocity", self.velocity, 1, 127, 5),
            ("Channel", self.channel, 1, 16, 1),
        ):
            ttk.Label(settings, text=title).pack(side="left", padx=(0, 4))
            ttk.Spinbox(settings, textvariable=variable, from_=start, to=end,
                        increment=step, width=6).pack(side="left", padx=(0, 12))
        single = ttk.Frame(self)
        single.pack(fill="x", pady=5)
        ttk.Label(single, text="Note").pack(side="left", padx=(0, 8))
        ttk.Entry(single, textvariable=self.pitch, width=10).pack(side="left")
        ttk.Button(single, text="Play note", command=self.play_note).pack(side="left", padx=6)
        ttk.Label(single, text="Or click a key above. Examples: C4, F#4, Bb3, 60.").pack(side="left")
        sequence = ttk.Frame(self)
        sequence.pack(fill="x", pady=5)
        ttk.Label(sequence, text="Sequence").pack(side="left", padx=(0, 8))
        ttk.Entry(sequence, textvariable=self.sequence).pack(side="left", fill="x", expand=True)
        ttk.Button(sequence, text="Play sequence", command=self.play_sequence).pack(side="left", padx=6)
        ttk.Button(sequence, text="Stop sound", command=self.stop).pack(side="left")
        ttk.Label(self, textvariable=self.status, wraplength=980).pack(anchor="w", pady=5)
        ttk.Label(self, text="Sound connection: computer USB → mioXC MIDI OUT → Yamaha MIDI IN. "
                  "Keep the piano volume audible. Blue keys are reference notes.", wraplength=980).pack(anchor="w")

    def refresh(self):
        try:
            ports = self.player.list_ports()
            self.selector["values"] = ports
            if self.output.get() not in ports:
                preferred = next((port for port in ports if "mioxc" in port.lower()), None)
                candidates = [port for port in ports if "midi through" not in port.lower()
                              and "rtmidi input" not in port.lower()]
                self.output.set(preferred or (candidates[0] if candidates else ""))
            if self.output.get():
                self.status.set("Output selected. Play a note or sequence.")
            elif ports:
                self.status.set("Only software outputs found. Connect the Yamaha interface, or select an output explicitly.")
            else:
                self.status.set("No MIDI outputs found. Connect the interface and refresh.")
        except Exception as exc:
            self.status.set(f"Output error: {exc}")

    def _play(self, pitches):
        try:
            if not self.output.get():
                self.refresh()
            beats = float(self.beats.get())
            notes = [PlaybackNote(pitch, index * beats, beats, int(self.velocity.get()), int(self.channel.get()))
                     for index, pitch in enumerate(pitches)]
            self.player.play_notes(notes, port_name=self.output.get(), tempo=float(self.tempo.get()))
            self._last_status = self.player.status
            self.status.set(self._last_status.detail)
        except Exception as exc:
            self.status.set(f"Cannot play: {exc}")

    def play_note(self, pitch=None):
        try:
            if pitch is None:
                pitch = parse_note(self.pitch.get())
            else:
                self.pitch.set(str(pitch))
            self._play([pitch])
        except ValueError as exc:
            self.status.set(str(exc))

    def play_sequence(self):
        try:
            tokens = re.split(r"[\s,]+", self.sequence.get().strip())
            if not self.sequence.get().strip() or len(tokens) > 4096:
                raise ValueError("Enter between 1 and 4096 notes, separated by spaces or commas.")
            self._play([parse_note(token) for token in tokens])
        except ValueError as exc:
            self.status.set(str(exc))

    def play_exercise(self, exercise):
        from ada_piano.score_import.review import playback_notes
        try:
            if not self.output.get():
                self.refresh()
            tempo = float(self.tempo.get())
            notes = playback_notes(exercise, tempo=tempo, velocity=int(self.velocity.get()), channel=int(self.channel.get()))
            self.player.play_notes(notes, port_name=self.output.get(), tempo=tempo)
            self._last_status = self.player.status
            self.status.set(self._last_status.detail)
        except Exception as exc:
            self.status.set(f"Cannot play score: {exc}")

    def stop(self):
        self.player.stop()

    def poll(self):
        events = self.player.drain_events()
        for event in events:
            key = (event.channel, event.note)
            if event.kind == "on":
                self.active.add(key)
            else:
                self.active.discard(key)
        status = self.player.status
        if status != self._last_status:
            self.status.set(status.detail)
            self._last_status = status
        if status.state in ("idle", "error", "finished", "stopped"):
            self.active.clear()
        return events
