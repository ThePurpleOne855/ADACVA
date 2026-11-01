"""Combined piano reader, reference playback, and optional camera preview."""

import re
from time import monotonic
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

from ada_piano.music_sheet import note_name
from ada_piano.note_reader import NoteEvent, NoteReader
from ada_piano.note_reader.keyboard import PianoKeyboard
from ada_piano.playback.gui import PlaybackPanel
from ada_piano.camera.gui import CameraPanel
from ada_piano.score_import.gui import ScorePanel
from ada_piano.agent.gui import CoachPanel
from ada_piano.camera.analysis import HandAnalysis
from ada_piano.sessions import SessionStore
from ada_piano import pieces
from ada_piano.note_reader import lettering
from ada_piano.note_reader.accessible import INK, ROOMS, AccessibleView, take_cells, take_note
from ada_piano.agent.coach import is_meta
from ada_piano.note_reader.actions import VoiceControls
from ada_piano.note_reader.theme import style_tools


class NoteReaderWindow:
    def __init__(self, root: tk.Tk, reader=None, demo=False, player=None, camera_worker=None,
                 agent_client=None, voice=None, accessible=False, session_directory=None, microphone=None):
        self.root = root
        self.accessible = accessible
        self.hands = HandAnalysis()
        self.sessions = SessionStore(session_directory) if accessible or session_directory is not None else None
        self.home = None
        self.tools_visible = not accessible
        self.reader = reader if reader is not None else NoteReader()
        self.demo = False
        self._demo_step = 0
        self._demo_due = 0.0
        self._check_due = 0.0
        self._timer = None
        self._closed = False
        self._last_played = None
        self._user_disconnected = False
        self._last_key = None
        self.root.title("Piano & Camera — ADA Piano Teacher")
        self.root.geometry("1400x850")
        self.root.minsize(1100, 760)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        style_tools(root)
        self.port = tk.StringVar()
        self.status = tk.StringVar(value="Disconnected. Select a MIDI input or try Demo.")
        self.latest = tk.StringVar(value="Play a note")
        self.details = tk.StringVar(value="MIDI —   Velocity —   Channel —")
        self.held = tk.StringVar(value="Held keys: none")
        self.pedal = tk.StringVar(value="Sustain: off   |   Notes received: 0")
        self.activity = tk.StringVar(value="MIDI activity: disconnected")
        self.workspace = ttk.Notebook(root)
        self.workspace.pack(fill="both", expand=True)
        panes = ttk.Panedwindow(self.workspace, orient="horizontal")
        self.workspace.add(panes, text="Piano & Camera")
        frame = ttk.Frame(panes, padding=16)
        panes.add(frame, weight=3)
        self.camera = CameraPanel(panes, worker=camera_worker, on_frame=self.hands.add_frame,
                                  on_reset=self._camera_reset)
        panes.add(self.camera, weight=2)
        self._heading = ttk.Label(frame, text="Note Reader", font=("", 24, "bold"))
        self._heading.pack(anchor="w")
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
        self.score = ScorePanel(self.workspace, self.playback, connected=lambda: self.reader.connected and not self.demo)
        self.workspace.add(self.score, text="Scores · import & practice")
        self.score.hand_analysis = self.hands
        self.score.on_completed = self._save_completed
        self.controls = VoiceControls(self)
        self.coach = CoachPanel(self.workspace, self.score, client=agent_client, voice=voice,
                                microphone=microphone, controls=self.controls.perform)
        self.workspace.add(self.coach, text="ADA Coach")
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
        ttk.Label(frame, textvariable=self.score.feedback, wraplength=840).pack(anchor="w", pady=4)
        self._started = monotonic()
        self.selector.focus_set()
        self.coach.camera = self.camera_voice
        self._camera_said = None
        for key, action in (("<F1>", self.talk), ("<F2>", self.toggle_import), ("<F3>", self.toggle_tools), ("<F5>", self.record),
                            ("<F6>", self.results), ("<F7>", self.toggle_camera), ("<Escape>", self.stop_all)):
            root.bind(key, lambda event, action=action: action() or "break")
        if accessible:
            self.workspace.pack_forget()
            self.home_status = tk.StringVar(value="Starting ADA. F1 to talk; Escape to stop.")
            self.home = AccessibleView(root, submit=self.submit, talk=self.talk, stop=self.stop_all,
                                       tools=self.toggle_tools, status=self.home_status)
            self.home.pack(fill="both", expand=True)
            self.coach.on_message = self.home.append
            for key, step in (("<Control-plus>", 1), ("<Control-equal>", 1), ("<Control-KP_Add>", 1),
                              ("<Control-minus>", -1), ("<Control-KP_Subtract>", -1), ("<Control-0>", 0)):
                root.bind(key, lambda event, step=step: self.text_size(step) or "break")
            for number, (room, _) in enumerate(ROOMS, 1):  # Ctrl+1 Practice ... Ctrl+5 Voice & AI
                root.bind(f"<Control-Key-{number}>", lambda event, room=room: self.open_room(room) or "break")
            self.root.geometry("900x700")
            self.root.minsize(700, 540)
            self.coach.use_best_voice()
            self.coach.wake_default = self.coach.wake_word = True  # always listening for "ADA ..."
            self.coach.speak.set(True)
            self.home.focus_message()
        if demo:
            self.start_demo()
        else:
            self.refresh()
            self.playback.refresh()
            candidates = self._instrument_ports(self.selector["values"])
            if len(candidates) == 1:
                self.connect()
        if accessible:
            piano = "The piano is connected." if self.reader.connected else (
                "The piano is not connected yet. Plug in the USB MIDI cable; I'll keep checking.")
            self.greet(piano)
        self._letter_tools()
        self._next_scan = monotonic() + 3
        self._timer = root.after(20, self._tick)

    def greet(self, piano=""):
        """ADA opens the session: ask what to practice and read the catalog."""
        titles = [piece.title for piece in self.score.catalog]
        listening = self.coach.microphone.available
        answer = ("Just say its name. After that, start with ADA whenever you want something, like ADA, record."
                  if listening else "Type its name and press Enter.")
        self._announce(f"Hi, I'm Ada. {piano} What would you like to practice today? "
                       f"I have {', and '.join(titles)}. {answer} "
                       "You can press F1 to talk to me any time, or say help.")
        if listening:
            self.coach.listen_after_speech()

    def _announce(self, text):
        if self.accessible:
            self.coach.announce(text)

    def talk(self):
        if self.accessible:
            self.coach.wake_word = True  # F1 also turns the wake word back on after "stop listening"
        self.coach.listen()
        if not self.coach.microphone.available:
            if self.home is not None and not self.tools_visible:
                self.home.focus_message()
            else:
                self.workspace.select(self.coach)
                self.coach.entry.focus_set()
            self._announce("Type your message and press Enter.")

    def submit(self, text):
        self.coach.text.set(text)
        self.coach.ask()

    def toggle_tools(self, visible=None):
        if self.home is None:
            return
        self.tools_visible = not self.tools_visible if visible is None else visible
        if self.tools_visible:
            self.home.pack_forget()
            self.workspace.pack(fill="both", expand=True)
            self.root.minsize(1100, 760)
            self.root.geometry("1400x850")
            self.workspace.select(self.coach)
            self.coach.entry.focus_set()
        else:
            self.workspace.pack_forget()
            self.home.pack(fill="both", expand=True)
            self.root.minsize(700, 540)
            self.root.geometry("900x700")
            self.home.focus_message()
        self._announce("Tools open. Press F3 or say hide tools to return." if self.tools_visible else "Practice screen.")

    def _camera_reset(self, reason):
        previously_ready = self.hands.calibrated or self.hands.calibrating
        message = self.hands.reset(reason)
        if previously_ready and hasattr(self, "coach"):
            self._announce(message)

    def _save_completed(self, snapshot):
        if self.sessions is not None:
            self.sessions.save(snapshot)
        exercise = self.score.take_exercise
        if self.home is not None and snapshot.get("mode") == "play_through" and exercise is not None:
            report = snapshot["report"]
            self.home.show_take(take_cells(exercise, report), report["correct"], report["notes_expected"],
                                key=(snapshot["score_sha256"], repr(snapshot["selection"])), note=take_note(report))

    def open_room(self, room):
        """Open a room on the practice screen; returns the spoken reply."""
        if self.home is None:
            return "Rooms are on the practice screen."
        if self.tools_visible:
            self.toggle_tools(False)
        self.home.open_room(room)
        self._rooms_state()
        name = dict(ROOMS)[room]
        if room == "pieces":
            return f"{name} open. " + "; ".join(p.title for p in self.score.catalog) + "."
        return f"{name} open."

    def _rooms_state(self):
        """Rail lamps and room content from live state; the view redraws only what changed."""
        home, connected = self.home, self.reader.connected and not self.demo
        piece = self._piece_line()
        takes = home._takes
        take = takes[-1] if takes else None
        coach = self.coach
        coach_ready = coach._api_configured()
        coach_name = ("Meta Muse Spark" if is_meta(coach._model) else "OpenAI") + f" ({coach._model})"
        listening = coach.wake_word and coach.microphone.available
        camera_on = self.camera.worker.running
        key = self._last_key
        home.set_rail("practice", f"Last take {take['score']}" if take else ("Ready to record" if piece else
                                  "No piece yet"), bool(piece))
        home.set_rail("piano", f"Connected · last key {key}" if connected and key else
                      "Connected · press a key" if connected else "Not connected", connected)
        home.set_rail("pieces", piece.split(" · ")[0] if piece else "Choose a piece", bool(piece))
        home.set_rail("camera", "On" if camera_on else "Off", camera_on)
        home.set_rail("voice", ("Muse Spark ready" if is_meta(coach._model) else "Coach ready") if coach_ready
                      and listening else "Listening for ADA" if listening else "Microphone off", coach_ready and listening)
        if connected:
            heard = (f"Last key you played: {key}" if key else
                     "No keys yet. Press any key; it will show here." if self.reader.message_count else
                     "Nothing from the piano yet. Check that the plug marked MIDI IN is in the piano's MIDI OUT.")
            piano_lines = [("Piano connected", "lead"), (heard, "lead"), (f"Input: {self.reader.port_name}", "line"),
                           (f"Sound plays through: {self.playback.output.get() or 'nothing selected'}", "line"),
                           (f"Tempo: {self.playback.tempo.get()} beats per minute", "line")]
            piano_actions = [("Test sound", "test sound", lambda: self.submit("test sound")),
                             ("Slower", "slower", lambda: self.submit("slower")),
                             ("Faster", "faster", lambda: self.submit("faster")),
                             ("MIDI inputs", "list MIDI inputs", lambda: self.submit("list MIDI inputs"))]
        else:
            piano_lines = [("Piano not connected", "lead"),
                           ("Plug in the USB MIDI interface; I connect by myself. On the YPT-300, PC mode must be "
                            "oFF (hold DEMO).", "line")]
            piano_actions = [("Connect piano", "connect piano", lambda: self.submit("connect piano")),
                             ("MIDI inputs", "list MIDI inputs", lambda: self.submit("list MIDI inputs"))]
        home.set_room("piano", "Piano", piano_lines, piano_actions)
        piece_lines = [(piece or "No piece loaded yet. Choose one below.", "lead")]
        if take:
            piece_lines.append((f"Last take {take['score']}. {take['note']}", "line"))
        piece_actions = [(p.title.split(" (")[0], f"practice {p.title.split(' (')[0].lower()}",
                          lambda title=p.title: self.submit(f"practice {title}")) for p in self.score.catalog]
        if piece:
            piece_actions += [(label, label.lower(), lambda words=label.lower(): self.submit(words))
                              for label in ("Play it for me", "Record", "Guided practice", "Right hand",
                                            "Left hand", "Both hands")]
        home.set_room("pieces", "Pieces", piece_lines, piece_actions)
        calibrating = self.hands.calibrating
        camera_actions = [("Stop camera", "stop camera", lambda: self.submit("stop camera")) if camera_on else
                          ("Start camera", "start camera", lambda: self.submit("start camera")),
                          ("Finish calibration", "finish calibration", lambda: self.submit("finish calibration"))
                          if calibrating else ("Calibrate hands", "calibrate hands",
                                               lambda: self.submit("calibrate hands")),
                          ("Hand report", "hand report", lambda: self.submit("hand report"))]
        home.set_room("camera", "Camera", [(self.camera.status.get() or ("Camera on" if camera_on else "Camera off"),
                                            "lead"), (self.hands.status, "line")], camera_actions)
        voice_lines = [(f"Coach: {coach_name}, " + ("ready" if coach_ready else "needs an API key"), "lead"),
                       ('Listening for "ADA". Start with ADA, then what you want.' if listening else
                        "Microphone off. Press F1 or the button below to listen again.", "lead"),
                       (f"Voice: {coach.voice_choice.get()}", "line"),
                       (f"Text size {round(home.scale * 100)} percent", "line")]
        voice_actions = [("Stop listening", "stop listening", lambda: self.submit("stop listening")) if listening
                         else ("Listen for ADA", "start listening", lambda: self.submit("start listening")),
                         ("Bigger text", "bigger text", lambda: self.submit("bigger text")),
                         ("Smaller text", "smaller text", lambda: self.submit("smaller text")),
                         ("API settings", "", coach.api_settings)]
        home.set_room("voice", "Voice & AI", voice_lines, voice_actions)

    def text_size(self, step):
        """Bigger (+1), smaller (-1) or normal (0) text on the practice screen; returns the spoken reply."""
        if self.home is None:
            return "Text size applies to the practice screen."
        scale = self.home.change_scale(step)
        self._letter_tools()
        reply = f"Text size {round(scale * 100)} percent."
        self._announce(reply)
        return reply

    def _letter_tools(self):
        """Tab labels and the main heading in the plate's smooth type, at the chosen text size."""
        if not lettering.available():
            return
        scale = self.home.scale if self.home is not None else 1.0
        self._tool_images = []
        for child in self.workspace.tabs():
            image = lettering.photo(self.workspace, self.workspace.tab(child, "text"), 20 * scale, INK, weight="bold")
            self.workspace.tab(child, image=image, compound="image")
            self._tool_images.append(image)
        lettering.letter(self._heading, "Note Reader", 30 * scale, INK, weight="bold")

    def _piece_line(self):
        loaded = self.score.loaded
        if loaded is None:
            return ""
        piece = getattr(loaded, "piece", None)
        found = pieces.find(piece["id"], self.score.catalog) if piece else None
        if found is None:
            return loaded.exercise.title.split(" — ")[0]
        hands = "both hands" if piece["hands"] == "both" else f"{piece['hands']} hand"
        selection = loaded.selection
        passage = (f"measures {selection['start_measure_label']} to {selection['end_measure_label']}"
                   if "start_measure_label" in selection else found.passages[piece["passage"]][2])
        return f"{found.title} · {passage} · {hands}"

    def _saved_sessions(self):
        if self.sessions is not None:
            for path, error, announce in self.sessions.drain():
                if error:
                    self.coach.announce(error)
                elif announce:
                    self.coach.announce("Session saved in your local ADA sessions folder.")
                    self.coach._append("Saved file", path)

    def _home_state(self):
        if self.home is None:
            return
        if self.score.take is not None:
            status = "Recording. Pause four seconds for results; say ADA stop to finish."
        elif self.score.tutor is not None:
            status = "Guided practice. Follow the spoken notes; say ADA stop to finish."
        elif not self.coach._speech_done.is_set():
            status = "ADA is speaking. Say ADA stop or press Escape to interrupt."
        elif self.coach._thread is not None and self.coach._thread.is_alive():
            status = "ADA is thinking. Say ADA stop or press Escape to cancel."
        else:
            status = self.coach.microphone_status.get()
        self.home_status.set(status[:180])
        self.home.set_context(piano="Piano connected" if self.reader.connected and not self.demo
                              else "Piano not connected", piece=self._piece_line())
        self._rooms_state()

    def camera_voice(self, on=True):
        """Start/stop the camera by voice; progress is announced from _tick."""
        if not on:
            self.camera.stop()
            self._camera_said = None
            return "Camera off."
        name = self.camera.auto_start()
        self._camera_said = "starting"
        return f"Starting the camera: {name}. I'll tell you when I can see your hands."

    def toggle_camera(self):
        self._announce(self.camera_voice(not self.camera.worker.running))

    def _watch_camera(self):
        """Speak the camera outcome after a voice/F7 start: error, no hands, then hands seen."""
        if self._camera_said is None:
            return
        status = self.camera.status.get()
        tracking = re.search(r"Tracking (\d+) hand", status)
        if "error" in status.lower():
            self._camera_said = None
            self._announce(status.split(": ", 1)[-1] + " Try another camera, or a phone camera app's address.")
        elif tracking:
            self._camera_said = None
            count = int(tracking.group(1))
            if not self.hands.calibrating:
                self._announce(f"Camera is on. I can see {'one hand' if count == 1 else f'{count} hands'}.")
        elif "No hands" in status and self._camera_said == "starting":
            self._camera_said = "no hands"
            self._announce("Camera is on, but I can't see your hands yet. Move them under the camera.")

    def toggle_import(self):
        if self.home is not None and not self.tools_visible:
            self.toggle_tools(True)
        self.score.show_import.set(not self.score.show_import.get())
        self.score._toggle_import()
        self.workspace.select(self.score)

    def record(self):
        self.coach.stop()
        self.score.play_through()

    def results(self):
        if self.tools_visible:
            self.workspace.select(self.coach)
        self.coach.text.set("How did I do?")
        self.coach.ask()

    def stop_all(self):
        take = self.score.take
        if self.home is not None:
            self.home.open_room("practice")  # Escape always comes home
        self.coach.stop()
        self.playback.stop()
        if self.hands.calibrating:
            self._announce(self.hands.cancel_calibration())
        if take is None or not take.notes:  # otherwise the take's results were just announced
            self._announce("Stopped.")

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
                seconds = monotonic() - (self.reader.last_received or monotonic())
                self.activity.set(f"MIDI messages: {count} · Last: {last} · Received {seconds:.1f}s ago")
            else:
                self.activity.set("Input is open. Waiting for piano data — play a key.")
        else:
            self.activity.set("MIDI activity: disconnected")

    @staticmethod
    def _instrument_ports(ports):
        # Software ports are never the piano; an RtMidi port can be ADA's own reference output.
        return [port for port in ports if "midi through" not in port.lower() and "rtmidi" not in port.lower()]

    @staticmethod
    def _device(port):
        """Name shared by one device's input and output ports.

        'mioXC:mioXC MIDI 1 36:0' (Linux ALSA client) -> 'mioxc'; 'Digital Piano 1' (Windows index) -> 'digital piano'.
        """
        return re.sub(r"\s+\d+$", "", port.split(":")[0]).casefold()

    def _pair_output(self):
        """Play reference sound through the device ADA listens to; returns the extra words to announce."""
        self.playback.refresh()
        device = self._device(self.reader.port_name)
        match = next((port for port in self.playback.selector["values"] if self._device(port) == device), None)
        if match is None:
            return ""
        self.playback.output.set(match)
        return " I'll play reference sound through it too."

    def _error(self, exc, was_connected=None):
        # NoteReader disconnects itself before raising, so callers pass the earlier state.
        if was_connected is None:
            was_connected = self.reader.connected
        self.score.stop_practice()
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
        if was_connected:
            self._announce("The piano was disconnected. Check the USB MIDI cable; I'll reconnect when it's back.")

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
        self._user_disconnected = False
        try:
            self.demo = False
            self.reader.connect(self.port.get())
            self.clear_log()
            self._last_played = None
            self.latest.set("Play a note")
            self.details.set("MIDI —   Velocity —   Channel —")
            self.status.set(f"Listening: {self.reader.port_name}")
            self._announce("Piano connected." + self._pair_output())
            self._check_due = monotonic() + 2
            self._show_state()
        except Exception as exc:
            self._error(exc)

    def disconnect(self):
        self._user_disconnected = True  # no accessible auto-reconnect until Connect is used again
        self.score.stop_practice()
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
        if source == "Piano":
            self.hands.observe(event.kind, event.note, event.velocity, event.channel, event.timestamp)
        self.score.observe(event, source)
        if event.kind == "on" and source != "Reference":
            self._last_played = event.note
            self._last_key = event.name
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
        was_connected = self.reader.connected
        try:
            now = monotonic()
            if self.demo:
                if now >= self._demo_due:
                    event = self.reader.state.consume(self._demo_message())
                    if event is not None:
                        self._record(event, source="Demo")
                    self._demo_due = now + 0.4
            elif (self.accessible and not self.reader.connected and not self._user_disconnected
                  and now >= self._next_scan):
                self._next_scan = now + 3
                candidates = self._instrument_ports(self.reader.list_ports())
                if len(candidates) == 1:
                    self.refresh()
                    self.port.set(candidates[0])
                    self.connect()
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
            for message in self.hands.tick(now):
                self.coach.announce(message)
            self._saved_sessions()
            self._home_state()
            if self.accessible:
                self._watch_camera()
        except Exception as exc:
            self._error(exc, was_connected)
        finally:
            if not self._closed:
                self._timer = self.root.after(20, self._tick)

    def close(self):
        if self._closed:
            return
        self.score.stop_practice()
        if self.sessions is not None:
            snapshot = self.score.session_snapshot()
            if snapshot is not None:
                self.sessions.save(snapshot)
            failures = [error for _, error, _ in self.sessions.flush() if error]
            if failures:
                self.coach.announce(failures[-1] + " ADA is still open with your latest session. "
                                    "Fix the folder or disk space, then say save session and quit again.")
                return
        self._closed = True
        if self._timer is not None:
            self.root.after_cancel(self._timer)
        try:
            try:
                self.coach.close()
            finally:
                self.score.close()
        finally:
            try:
                self.camera.close()
            finally:
                try:
                    if self.sessions is not None:
                        self.sessions.close()
                        self._saved_sessions()
                finally:
                    try:
                        self.playback.player.close()
                    finally:
                        try:
                            self.reader.disconnect()
                        finally:
                            if self.home is not None:
                                self.home.close()
                            self.root.destroy()


def launch(demo=False):
    from ada_piano.agent.settings import load_api_key
    load_api_key()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("Note Reader needs a graphical desktop. Run it from a desktop terminal.") from exc
    window = NoteReaderWindow(root, demo=demo, accessible=True)
    try:
        root.mainloop()
    finally:
        if not window._closed:
            window.close()
