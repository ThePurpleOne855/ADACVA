"""Tkinter test panel for live MIDI input; no camera or tutor required."""

from time import monotonic
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

from ada_piano.music_sheet import note_name
from ada_piano.note_reader import NoteEvent, NoteReader
from ada_piano.note_reader.keyboard import PianoKeyboard
from ada_piano.playback.gui import PlaybackPanel


class NoteReaderWindow:
    def __init__(self, root: tk.Tk, reader=None, demo=False, player=None):
        self.root = root
        self.reader = reader if reader is not None else NoteReader()
        self.demo = False
        self._demo_step = 0
        self._demo_due = 0.0
        self._check_due = 0.0
        self._timer = None
        self._closed = False
        self._last_played = None
        self.root.title("Note Reader — ADA Piano Teacher")
        self.root.geometry("1100x820")
        self.root.minsize(900, 760)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.port = tk.StringVar()
        self.status = tk.StringVar(value="Disconnected. Select a MIDI input or try Demo.")
        self.latest = tk.StringVar(value="Play a note")
        self.details = tk.StringVar(value="MIDI —   Velocity —   Channel —")
        self.held = tk.StringVar(value="Held keys: none")
        self.pedal = tk.StringVar(value="Sustain: off   |   Notes received: 0")
        self.activity = tk.StringVar(value="MIDI activity: disconnected")
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Note Reader", font=("", 24, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Yamaha YPT-300 · MIDI input test · Middle C = C4 (60)").pack(anchor="w", pady=(0, 12))
        ttk.Label(frame, text="MIDI input (the USB cable's name may appear instead of Yamaha):").pack(anchor="w")
        self.selector = ttk.Combobox(frame, textvariable=self.port, state="readonly")
        self.selector.pack(fill="x", pady=6)
        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        for label, command in (("Refresh inputs", self.refresh), ("Connect", self.connect),
                               ("Disconnect / Stop", self.disconnect), ("Demo", self.start_demo),
                               ("Clear log", self.clear_log)):
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=(0, 6))
        ttk.Label(frame, textvariable=self.status, wraplength=1000).pack(anchor="w", pady=(10, 3))
        ttk.Label(frame, textvariable=self.activity, wraplength=1000).pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, textvariable=self.latest, font=("", 28, "bold")).pack(anchor="w")
        ttk.Label(frame, textvariable=self.details).pack(anchor="w")
        self.keyboard = PianoKeyboard(frame, on_note=self._play_key)
        self.keyboard.pack(fill="x", pady=(12, 4))
        ttk.Label(frame, text="Green = your held key     Blue fill = reference     Blue outline = last played     Click a key to hear it").pack(anchor="w")
        ttk.Label(frame, textvariable=self.held, wraplength=840).pack(anchor="w", pady=(12, 4))
        ttk.Label(frame, textvariable=self.pedal).pack(anchor="w", pady=(0, 12))
        self.tabs = ttk.Notebook(frame)
        self.tabs.pack(fill="both", expand=True)
        log_frame = ttk.Frame(self.tabs)
        self.tabs.add(log_frame, text="MIDI event log")
        self.playback = PlaybackPanel(self.tabs, player=player)
        self.tabs.add(self.playback, text="Audible reference")
        columns = ("time", "event", "note", "midi", "velocity", "channel", "duration", "source")
        self.log = ttk.Treeview(log_frame, columns=columns, show="headings", height=4)
        for column, title in zip(columns, ("Elapsed (s)", "Event", "Note", "MIDI", "Velocity", "Channel", "Duration (s)", "Source")):
            self.log.heading(column, text=title)
            self.log.column(column, width=110, minwidth=70, anchor="center")
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)
        ttk.Label(frame, text="Keyboard MIDI OUT → cable MIDI IN → computer USB.\n"
                  "Duration measures press to release on OFF rows; sustain is shown separately. MIDI carries notes, not audio.",
                  wraplength=840).pack(anchor="w", pady=(12, 0))
        self._started = monotonic()
        self.selector.focus_set()
        if demo:
            self.start_demo()
        else:
            self.refresh()
            self.playback.refresh()
            candidates = self._instrument_ports(self.selector["values"])
            if len(candidates) == 1:
                self.connect()
        self._timer = root.after(20, self._tick)

    def _show_state(self):
        state = self.reader.state
        keys = ", ".join(f"{note_name(note)} (ch {channel})" for channel, note in sorted(state.held))
        self.held.set("Held keys: " + (keys or "none"))
        channels = ", ".join(map(str, sorted(state.sustain)))
        self.pedal.set(f"Sustain: {'on (ch ' + channels + ')' if channels else 'off'}"
                       f"   |   Notes received: {state.note_count}")
        self.keyboard.show_notes((note for channel, note in state.held), self._last_played,
                                 (note for channel, note in self.playback.active))
        if self.demo:
            self.activity.set("DEMO — simulated input; the piano connection is not being tested.")
        elif self.reader.connected:
            count = self.reader.message_count
            last = self.reader.last_message or "none"
            age = monotonic() - (self.reader.connected_at or monotonic())
            if not state.note_count and age >= 5:
                self.activity.set(f"MIDI messages: {count} · Last: {last} · No key presses received. "
                                  "Check piano MIDI OUT → cable IN and Yamaha PC mode = OFF (PC1 disables notes).")
            elif count:
                seconds = monotonic() - self.reader.last_received
                self.activity.set(f"MIDI messages: {count} · Last: {last} · Received {seconds:.1f}s ago")
            else:
                self.activity.set("Input is open. Waiting for piano data — play a key.")
        else:
            self.activity.set("MIDI activity: disconnected")

    @staticmethod
    def _instrument_ports(ports):
        return [port for port in ports if "midi through" not in port.lower()]

    def _error(self, exc):
        self.demo = False
        try:
            self.reader.disconnect()
        except Exception:
            pass
        self.status.set(f"Error: {exc}")
        self.latest.set("Input stopped")
        self._last_played = None
        self.details.set("MIDI —   Velocity —   Channel —")
        self._show_state()

    def refresh(self):
        try:
            ports = self.reader.list_ports()
            self.selector["values"] = ports
            if self.port.get() not in ports:
                candidates = self._instrument_ports(ports)
                preferred = next((port for port in candidates if "mioxc" in port.lower()), None)
                self.port.set(preferred or (candidates[0] if candidates else ports[0] if ports else ""))
            if not self.reader.connected and not self.demo:
                self.status.set("Select an input and click Connect." if ports else
                                "No MIDI inputs found. Connect the USB-to-MIDI cable and click Refresh inputs.")
        except Exception as exc:
            self._error(exc)

    def connect(self):
        try:
            self.demo = False
            self.reader.connect(self.port.get())
            self.clear_log()
            self._last_played = None
            self.latest.set("Play a note")
            self.details.set("MIDI —   Velocity —   Channel —")
            self.status.set(f"Listening: {self.reader.port_name}")
            self._check_due = monotonic() + 2
            self._show_state()
        except Exception as exc:
            self._error(exc)

    def disconnect(self):
        self.demo = False
        self.playback.stop()
        try:
            self.reader.disconnect()
            self._last_played = None
            self.status.set("Disconnected. Select a MIDI input or try Demo.")
            self.latest.set("Input stopped")
            self.details.set("MIDI —   Velocity —   Channel —")
            self._show_state()
        except Exception as exc:
            self._error(exc)

    def start_demo(self):
        self.disconnect()
        self.clear_log()
        self.demo = True
        self._demo_step = 0
        self._demo_due = monotonic()
        self.status.set("DEMO — simulated C4–E4–G4 chord, releases, and sustain. No keyboard input or audio.")

    def clear_log(self):
        children = self.log.get_children()
        if children:
            self.log.delete(*children)
        self._started = monotonic()

    def _demo_message(self):
        sequence = (("control_change", 64, 127), ("note_on", 60, 80),
                    ("note_on", 64, 96), ("note_on", 67, 112),
                    ("note_off", 60, 64), ("note_on", 64, 0),
                    ("note_off", 67, 64), ("control_change", 64, 0))
        kind, number, value = sequence[self._demo_step % len(sequence)]
        self._demo_step += 1
        if kind == "control_change":
            return SimpleNamespace(type=kind, channel=0, control=number, value=value)
        return SimpleNamespace(type=kind, channel=0, note=number, velocity=value)

    def _play_key(self, pitch):
        self.tabs.select(self.playback)
        self.playback.play_note(pitch)

    def _record(self, event, source="Piano"):
        if event.kind == "on" and source != "Reference":
            self._last_played = event.note
        if source != "Reference":
            self.latest.set(f"{event.name}  {'pressed' if event.kind == 'on' else 'released'}")
            self.details.set(f"MIDI {event.note}   Velocity {event.velocity}   Channel {event.channel}")
        row = self.log.insert("", "end", values=(f"{event.timestamp - self._started:.2f}",
                              event.kind.upper(), event.name, event.note, event.velocity, event.channel,
                              "—" if event.duration is None else f"{event.duration:.3f}", source))
        children = self.log.get_children()
        if len(children) > 500:
            self.log.delete(*children[:-500])
        self.log.see(row)

    def _tick(self):
        try:
            now = monotonic()
            if self.demo:
                if now >= self._demo_due:
                    event = self.reader.state.consume(self._demo_message())
                    if event is not None:
                        self._record(event, source="Demo")
                    self._demo_due = now + 0.4
            elif self.reader.connected:
                if now >= self._check_due:
                    self.reader.check_connection()
                    self._check_due = now + 2
                for event in self.reader.poll():
                    self._record(event)
            for event in self.playback.poll():
                self._record(NoteEvent(event.kind, event.note, event.velocity, event.channel,
                                       event.timestamp, event.duration), source="Reference")
            self._show_state()
        except Exception as exc:
            self._error(exc)
        finally:
            if not self._closed:
                self._timer = self.root.after(20, self._tick)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._timer is not None:
            self.root.after_cancel(self._timer)
        try:
            self.playback.player.close()
        finally:
            try:
                self.reader.disconnect()
            finally:
                self.root.destroy()


def launch(demo=False):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("Note Reader needs a graphical desktop. Run it from a desktop terminal.") from exc
    window = NoteReaderWindow(root, demo=demo)
    try:
        root.mainloop()
    finally:
        if not window._closed:
            window.close()
