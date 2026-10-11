"""Compact coach panel. Workers never touch Tk; actions return through a queue."""

from copy import deepcopy
import os
from queue import Empty, Queue
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ada_piano import pieces
from ada_piano.ai_tutor.performance import describe
from ada_piano.voice import VoiceService, piper_tts
from . import local_commands
from .coach import Coach, error_message
from .cloud_voice import CloudVoiceService, VOICES, DEFAULT_VOICE, DEFAULT_SPEED, PREVIEW_TEXT
from .session import ChatSession
from .speech_input import create_speech_input, voice_command
from .tools import AgentTools, passage_context, select_passage


NATURAL_VOICE = "Natural (offline)"
SOUND_TOOLS = {"play_reference", "play_notes", "replay_my_playing"}


class CoachPanel(ttk.Frame):
    def __init__(self, parent, score=None, *, client=None, voice=None, microphone=None):
        super().__init__(parent, padding=10)
        self.score = score if score is not None else ChatSession()
        self.client = client
        self.voice = voice if voice is not None else CloudVoiceService()
        self._injected_voice = voice is not None
        self.microphone = microphone if microphone is not None else create_speech_input()
        self._api_key = None
        self._model = os.environ.get("ADA_OPENAI_MODEL", "gpt-4.1-mini")
        self._request_context_active = False
        self._speech_done = Event()
        self._speech_done.set()
        self._listen_pending = False
        self._queue = Queue()
        self._cancel = Event()
        self._closed = False
        self._thread = None
        self._history = []
        self._identity = None
        self._pending_reference = None
        self._pending_practice = None
        self._reference_active = False
        self._reference_review = None
        self._turn_ready = None
        self._activity_version = None
        self._request_review = None
        self._request_attempt = None
        self._reference_outcome = None
        self._reference_waiter = None
        self._request_playback_status = None
        self._request = None
        self.camera = None  # optional callable(on=True) -> spoken status, set by the main window
        self.conversation = False  # accessible mode: auto-send speech and listen again after replies
        self._listen_next = False
        self.local_commands = hasattr(self.score, "load_piece")
        if self.local_commands and getattr(self.score, "announce", None) is None:
            self.score.announce = self.announce
        self.text = tk.StringVar()
        self.speak = tk.BooleanVar(value=False)
        self.hands_free = tk.BooleanVar(value=False)
        self.voice_choice = tk.StringVar(value=DEFAULT_VOICE)
        self.voice_speed = tk.StringVar(value=f"{DEFAULT_SPEED:.2f}")
        self.microphone_status = tk.StringVar(value=self.microphone.status)
        self.connection = tk.StringVar()
        self._update_connection()
        self.status = tk.StringVar(value="ADA ready. Ask a piano question, or approve a passage for guided practice.")
        ttk.Label(self, text="ADA Coach").pack(anchor="w")
        # Pack the fixed controls first so resizing never hides the input below
        # the expanding transcript. Display order is transcript, then controls.
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x")
        ttk.Label(bottom, text="Your message — type here, or use the microphone:").pack(anchor="w", pady=(6, 2))
        self.entry = ttk.Entry(bottom, textvariable=self.text, font=("", 13))
        self.entry.pack(fill="x", ipady=6, pady=(0, 5))
        self.entry.bind("<Return>", lambda event: self.ask())
        controls = ttk.Frame(bottom)
        controls.pack(fill="x")
        self.ask_button = ttk.Button(controls, text="Ask ADA", command=self.ask)
        self.ask_button.pack(side="left")
        ttk.Button(controls, text="Stop", command=self.stop).pack(side="left", padx=5)
        self.listen_button = ttk.Button(controls, text="Speak a question", command=self.listen)
        self.listen_button.pack(side="left")
        ttk.Button(controls, text="Save latest attempt", command=self.save_attempt).pack(side="right")
        voice_controls = ttk.Frame(bottom)
        voice_controls.pack(fill="x", pady=4)
        ttk.Checkbutton(voice_controls, text='Hands-free: say "ADA …"', variable=self.hands_free,
                        command=self._hands_free_changed).pack(side="left", padx=5)
        ttk.Checkbutton(voice_controls, text="Speak responses", variable=self.speak,
                        command=self._speech_changed).pack(side="left")
        ttk.Label(voice_controls, text="Voice:").pack(side="left", padx=(10, 3))
        self.voice_selector = ttk.Combobox(voice_controls, textvariable=self.voice_choice,
                                          values=(*VOICES, "System (local)"), state="readonly", width=15)
        self.voice_selector.pack(side="left")
        self.voice_selector.bind("<<ComboboxSelected>>", self._voice_changed)
        speech_controls = ttk.Frame(bottom)
        speech_controls.pack(fill="x", pady=(0, 4))
        ttk.Label(speech_controls, text="Speaking speed:").pack(side="left", padx=(5, 3))
        self.speed_selector = ttk.Combobox(speech_controls, textvariable=self.voice_speed,
                                          values=("0.75", "0.85", "0.95", "1.00", "1.10", "1.15"),
                                          state="readonly", width=5)
        self.speed_selector.pack(side="left")
        ttk.Label(speech_controls, text="× (cloud voices)").pack(side="left", padx=4)
        ttk.Button(speech_controls, text="Preview voice", command=self.preview_voice).pack(side="left", padx=5)
        self.voice_status = tk.StringVar(value="OpenAI voice is AI-generated; enabling speech sends reply text and incurs API charges.")
        ttk.Label(bottom, textvariable=self.voice_status, wraplength=750).pack(anchor="w")
        settings = ttk.Frame(bottom)
        settings.pack(fill="x", pady=4)
        ttk.Button(settings, text="API settings", command=self.api_settings).pack(side="left")
        ttk.Label(settings, textvariable=self.connection, wraplength=600).pack(side="left", padx=8)
        ttk.Label(bottom, textvariable=self.microphone_status, wraplength=950).pack(anchor="w")
        if getattr(self.microphone, "cloud_transcription", False):
            ttk.Label(bottom, text="Linux voice input sends recorded audio to OpenAI when listening is enabled (API charges apply).",
                      wraplength=950).pack(anchor="w")
        ttk.Label(bottom, textvariable=self.status, wraplength=950).pack(anchor="w")
        history = ttk.Frame(self)
        history.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(history)
        scrollbar.pack(side="right", fill="y")
        self.transcript = tk.Text(history, height=10, wrap="word", state="disabled",
                                  yscrollcommand=scrollbar.set)
        self.transcript.pack(fill="both", expand=True)
        scrollbar.configure(command=self.transcript.yview)
        self.voice_selector["values"] = (*self.voice_selector["values"], NATURAL_VOICE)
        self._timer = self.after(30, self._poll)

    def use_best_voice(self):
        """OpenAI voice with a key; otherwise natural offline, then system speech."""
        if self._injected_voice:
            return
        if not (self._api_key or os.environ.get("OPENAI_API_KEY")):
            self.voice_choice.set(NATURAL_VOICE if piper_tts.available() else "System (local)")
            self._voice_changed()

    def _update_connection(self):
        configured = bool(self._api_key or os.environ.get("OPENAI_API_KEY"))
        self.connection.set(f"API key: {'set' if configured else 'missing'} · Model: {self._model}")

    def api_settings(self):
        if self._thread is not None and self._thread.is_alive():
            self.status.set("Wait for the current request to finish before changing API settings.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("ADA API settings — this session only")
        dialog.transient(self.winfo_toplevel())
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="OpenAI API key (hidden; leave blank to use OPENAI_API_KEY):").pack(anchor="w")
        key = tk.StringVar()
        key_entry = ttk.Entry(frame, textvariable=key, show="•", width=60)
        key_entry.pack(fill="x", pady=5)
        ttk.Label(frame, text="Model:").pack(anchor="w")
        model = tk.StringVar(value=self._model)
        ttk.Entry(frame, textvariable=model).pack(fill="x", pady=5)
        ttk.Label(frame, text="Keys are kept in memory for this run. API usage requires API credit.").pack(anchor="w")

        def apply():
            selected = model.get().strip()
            if not selected or len(selected) > 100:
                return
            self._api_key = key.get().strip() or None
            if hasattr(self.microphone, "configure"):
                self.microphone.configure(api_key=self._api_key)
            self._model = selected
            key.set("")
            self._history = []
            self._update_connection()
            self.status.set("API settings updated. Type a question and press Ask ADA to test.")
            dialog.destroy()

        def cancel():
            key.set("")
            dialog.destroy()

        ttk.Button(frame, text="Apply for this session", command=apply).pack(pady=(8, 0))
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.grab_set()
        key_entry.focus_set()

    def _say(self, text):
        self._listen_pending = False
        self.microphone.stop()
        if isinstance(self.voice, CloudVoiceService):
            self.voice.configure(api_key=self._api_key, voice=self.voice_choice.get(),
                                 speed=float(self.voice_speed.get()))
        self._speech_done = self.voice.say(text)
        return self._speech_done

    def announce(self, text):
        """Show and (when enabled) speak a local status message."""
        self._append("ADA", text)
        self.status.set(text)
        if self.speak.get() and not self._closed:
            self._say(text)
        if getattr(self, "conversation", False):
            self._listen_next = True

    def _api_configured(self):
        return bool(self.client or self._api_key or os.environ.get("OPENAI_API_KEY"))

    def _local(self, question):
        """Handle offline commands; returns True when handled locally."""
        command = local_commands.parse(question, self.score.catalog)
        if command is None:
            return False
        name, arguments = command
        if name == "results" and getattr(self.score, "take", None) is None and self._api_configured():
            return False  # the coach can explain the measured report in more depth
        self._append("You", question)
        self.text.set("")
        if name == "stop":
            take = getattr(self.score, "take", None)
            self.stop()
            if take is None or not take.notes:  # otherwise stop() just announced the take's results
                self.announce("Stopped.")
        elif name == "help":
            self.announce(local_commands.HELP)
        elif name == "list":
            self.announce(local_commands.list_text(self.score.catalog))
        elif name == "load":
            self.stop()
            try:
                self.score.load_piece(arguments["piece"], arguments["passage"], arguments["hands"])
            except ValueError as exc:
                self.announce(str(exc))
        elif name == "record":
            self.voice.stop()
            self.score.play_through()
        elif name == "results":
            if getattr(self.score, "take", None) is not None:
                self.score.finish_take()
            else:
                report = self.score.performance_summary()
                self.announce(describe(report) if report else
                              "No play-through yet for this passage. Say: ADA, record. Then play.")
        elif name == "reference":
            self._local_reference()
        elif name == "replay":
            self.stop()  # scores a take still in progress, so the replay is the one just played
            plan = self.score.replay_plan()
            if not plan:
                self.announce("There's no recording of this passage yet. Say record, then play.")
            else:
                self._queue_local_sound(plan, 60, "Here's how your last play-through sounded.")
        elif name in ("camera", "camera_off"):
            if self.camera is None:
                self.announce("The camera isn't available in this window.")
            else:
                self.announce(self.camera() if name == "camera" else self.camera(False))
        return True

    def _queue_local_sound(self, plan, tempo, announcement):
        self._append("ADA", announcement)
        if self.speak.get():
            finished = self._say(announcement)
        else:
            finished = Event()
            finished.set()
        self._activity_version = self.score.activity_version
        self._pending_reference = (self.score.loaded, plan, tempo, finished)

    def _local_reference(self):
        review = self.score.loaded
        if review is None:
            self.announce("Load a piece first. Say: ADA, list pieces.")
            return
        self.stop()
        tempo = self.score.take_tempo or self.score.playback.tempo.get()
        self._queue_local_sound(review.exercise, tempo, "Listen. Then it's your turn.")

    def preview_voice(self):
        if (self.score.tutor is not None or self.score.playback.player.status.state == "playing"
                or self._pending_reference is not None
                or (self._thread is not None and self._thread.is_alive())):
            self.status.set("Stop practice or wait for ADA to finish before previewing a voice.")
            return
        self._say(PREVIEW_TEXT)
        self.status.set("Previewing the selected voice. Stop cancels the preview.")

    def _voice_changed(self, event=None):
        if self._injected_voice:
            return
        self.voice.close()
        choice = self.voice_choice.get()
        if choice == NATURAL_VOICE:
            self.voice = piper_tts.PiperVoiceService()
            self.voice_status.set(self.voice.status)
        elif choice == "System (local)":
            self.voice = VoiceService()
            self.voice_status.set("Local system voice selected.")
        else:
            self.voice = CloudVoiceService()
            self.voice_status.set("OpenAI voice is AI-generated; enabling speech sends reply text and incurs API charges.")

    def listen(self):
        self.hands_free.set(False)
        self.microphone.stop()
        self.voice.stop()
        self._listen_pending = True
        if self._microphone_busy():
            self._listen_pending = False
            self.microphone_status.set("Stop practice / playback or wait for ADA before speaking a question.")
            return
        self._poll_microphone()

    def listen_after_speech(self, tries=600):
        """Open the microphone once ADA finishes speaking (e.g. after a question)."""
        if self._closed or not self.microphone.available or self.hands_free.get() or self.microphone.running:
            return  # the learner already chose how to talk; listen() would switch hands-free off
        if not self._speech_done.is_set():
            if tries:
                self.after(100, lambda: self.listen_after_speech(tries - 1))
            return
        self.listen()

    def _hands_free_changed(self):
        self._listen_pending = False
        self.microphone.stop()
        self.voice.stop()
        if self.hands_free.get() and not self.microphone.available:
            self.microphone.start(continuous=True, retry=True)
        self._poll_microphone()

    def _microphone_busy(self):
        return (self._closed
                or getattr(self.score, "take", None) is not None
                or self.score.tutor is not None
                or self.score.playback.player.status.state == "playing"
                or self._pending_reference is not None
                or not self._speech_done.is_set())

    def _poll_microphone(self):
        if not hasattr(self, "microphone"):
            return  # Lightweight headless test panels have no audio service.
        if self._microphone_busy():
            self._listen_pending = False
            if self.microphone.running:
                self.microphone.stop()
            self.microphone_status.set("Microphone paused while ADA speaks or reference sound plays.")
            return
        for text in self.microphone.drain():
            if self.hands_free.get():
                command = voice_command(text)
                if command is None:
                    continue
                name, question = command
                if name == "stop":
                    self.stop()
                else:
                    self.text.set(question)
                    self.ask()
                break
            else:
                self.text.set(text)
                self.entry.focus_set()
                if self.conversation:
                    # Voice-first mode: send what was heard; no button press needed.
                    self.ask()
                    self._listen_next = True
        if self.hands_free.get() and self.microphone.available and not self._microphone_busy():
            self.microphone.start(continuous=True)
        elif self._listen_pending and not self.microphone.running:
            self._listen_pending = False
            self.microphone.start(retry=True)
        if not self.microphone.available:
            self.hands_free.set(False)
        self.microphone_status.set(self.microphone.status)

    def _append(self, speaker, text):
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"{speaker}: {text}\n\n")
        # Bounded visible history too.
        if int(self.transcript.index("end-1c").split(".")[0]) > 300:
            self.transcript.delete("1.0", "100.0")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _speech_changed(self):
        if not self.speak.get():
            self.voice.stop()

    def ask(self):
        if self._thread is not None and self._thread.is_alive():
            self.status.set("ADA is still finishing a request. Stop it or wait.")
            return
        question = self.text.get().strip()
        if not question:
            return
        if self.local_commands and self._local(question):
            return
        if getattr(self.score, "take", None) is not None:
            self.score.finish_take()  # "ADA, ..." right after playing scores the take first
        if self.score.tutor is not None or self.score.playback.player.status.state == "playing":
            self.status.set("Stop practice / sound before asking ADA, so speech does not overlap.")
            return
        if len(question) > 2000:
            self.status.set("Keep your question under 2,000 characters.")
            return
        self.microphone.stop()
        self.voice.stop()
        review = self.score.loaded
        if review is None:
            self._append("ADA", "No piece is loaded yet. Say a piece name to practice it, or ask me anything about piano.")
        identity = (review.digest, repr(review.selection)) if review else None
        if identity != self._identity:
            self._history = []
            self._identity = identity
        attempt = self.score.latest_attempt
        summary = attempt.summary() if attempt and review else None
        if summary and (summary["score_sha256"] != review.digest or
                        any(attempt.context["selection"].get(k) != v for k, v in review.selection.items())):
            summary = None
        performance = self.score.performance_summary() if hasattr(self.score, "performance_summary") else None
        snapshot = deepcopy(review)
        token = self._cancel = Event()
        request = self._request = {"review": review}
        self._request_review = review
        self._request_context_active = True
        self._request_attempt = attempt if summary else None
        self._activity_version = self.score.activity_version
        self._reference_outcome = None
        self._request_playback_status = self.score.playback.player.status
        self._append("You", question)
        self.text.set("")
        self.status.set("Thinking…")
        self.ask_button.configure(state="disabled")

        def action(name, arguments):
            done, box = Event(), {}
            self._queue.put(("action", token, (request["review"], name, arguments, done, box)))
            while not done.wait(.05):
                if token.is_set():
                    return {"status": "cancelled"}
            return box["result"]

        tools = AgentTools(snapshot, summary, action, performance,
                           self.score.catalog if hasattr(self.score, "catalog") else None)
        coach = Coach(tools, self.client, api_key=self._api_key, model=self._model)
        coach.history = list(self._history)

        def run():
            try:
                answer = coach.ask(question, token)
                self._queue.put(("answer", token, (request["review"], answer, coach.history)))
            except Exception as exc:
                # Avoid leaking SDK errors, credentials or remote payloads into UI/logs.
                self._queue.put(("error", token, error_message(exc)))
            finally:
                coach.close()
        self._thread = Thread(target=run, name="ada-coach", daemon=True)
        self._thread.start()

    def _perform(self, review, name, arguments):
        if name == "load_piece":
            return self._perform_load(arguments)
        if name in ("play_notes", "replay_my_playing"):
            return self._perform_sound(name, arguments)
        if review is None or self.score.loaded is not review or not review.approved:
            return {"status": "rejected", "reason": "Approved selection changed or is not loaded."}
        if self._request_stale():
            self._cancel_request()
            return {"status": "cancelled", "reason": "Local activity changed."}
        if name == "stop_practice":
            self._finish_reference("cancelled")
            self._pending_reference = self._pending_practice = None
            self._reference_active = False
            self.voice.stop()
            self.score.stop()
            self._activity_version = self.score.activity_version
            self._request_playback_status = self.score.playback.player.status
            return {"status": "stopped"}
        if name == "play_reference":
            self._reference_outcome = "failed"
        exercise = select_passage(review, arguments["start_measure"], arguments["end_measure"])
        if name == "play_reference":
            # No visual confirmation dialog: ADA announces sound aloud first, and
            # Stop (Esc or "stop") cancels it, so the flow works without sight.
            announcement = f"I'll play measure {arguments['start_measure']} through {arguments['end_measure']} once."
            return self._queue_sound(review, exercise, arguments["tempo"], announcement)
        if self._reference_outcome in ("failed", "cancelled", "declined"):
            return {"status": "rejected", "reason": "Reference did not finish. Ask again to start a new practice request."}
        context = passage_context(review)
        context["selection"] = {**context["selection"], "start_measure_label": arguments["start_measure"], "end_measure_label": arguments["end_measure"]}
        chosen = set(e.measure for e in exercise.events)
        context["events"] = [e for e in context["events"] if e["measure"] in chosen]
        context["rests"] = [r for r in context["rests"] if r["measure"] in chosen]
        for index, event in enumerate(context["events"]):
            event["approved_event_index"] = event["event_index"]
            event["event_index"] = index
        mode = "record" if name == "start_play_through" else "practice"
        if (self._pending_reference is not None or self._reference_active
                or (self._turn_ready is not None and not self._turn_ready.is_set())):
            self._pending_practice = (review, exercise, context, mode)
            return {"status": "queued_after_reference"}
        self.voice.stop()
        return self._begin(exercise, context, mode)

    def _begin(self, exercise, context, mode):
        if mode == "record":
            started = self.score.play_through(exercise, context)
        else:
            self.score.practice(exercise, context)
            started = self.score.tutor is not None
        self._activity_version = self.score.activity_version
        self.status.set(self.score.feedback.get())
        return {"status": ("recording" if mode == "record" else "practicing") if started else "unavailable"}

    def _queue_sound(self, review, plan, tempo, announcement):
        if self._cancel.is_set() or self._request_stale():
            return {"status": "cancelled", "reason": "Local activity changed."}
        if self.score.tutor is not None or getattr(self.score, "take", None) is not None:
            return {"status": "rejected", "reason": "The learner is playing; wait until they finish."}
        self.score.stop()
        self._activity_version = self.score.activity_version
        self._request_playback_status = self.score.playback.player.status
        self._append("ADA", announcement)
        if self.speak.get():
            finished = self._say(announcement)
        else:
            finished = Event()
            finished.set()
        self._pending_reference = (review, plan, tempo, finished)
        self._reference_outcome = "pending"
        return {"status": "queued", "announcement": announcement}

    def _perform_sound(self, name, arguments):
        if not hasattr(self.score.playback, "play_plan"):
            return {"status": "unavailable", "reason": "No piano sound output in this window."}
        review = self.score.loaded
        if review is not None and self._request_review is not review:
            return {"status": "rejected", "reason": "The loaded passage changed."}
        if name == "play_notes":
            kind = "chord" if arguments["chord"] else ("note" if " " not in arguments["notes"] else "notes")
            return self._queue_sound(review, arguments["plan"], arguments["tempo"],
                                     f"Here's the {kind}: {arguments['notes']}.")
        plan = self.score.replay_plan() if hasattr(self.score, "replay_plan") else None
        if not plan:
            return {"status": "no_play_through"}
        return self._queue_sound(review, plan, 60, "Here's how your last play-through sounded.")

    def _perform_load(self, arguments):
        if not hasattr(self.score, "load_piece"):
            return {"status": "unavailable"}
        if self.score.playback.player.status.state == "playing":
            return {"status": "rejected", "reason": "Reference sound is playing."}
        if self._reference_waiter is not None:
            self._finish_reference("cancelled")
        self._reference_outcome = None  # a new passage starts with no reference history
        self._pending_reference = self._pending_practice = None
        self._reference_active = False
        try:
            result = self.score.load_piece(arguments["piece"], arguments["passage"], arguments["hands"])
        except ValueError as exc:
            return {"status": "rejected", "reason": str(exc)}
        # This request now refers to the new passage rather than being cancelled as stale.
        self._request_review = self.score.loaded
        if self._request is not None:
            self._request["review"] = self.score.loaded
        self._request_attempt = None
        self._activity_version = self.score.activity_version
        self._request_playback_status = self.score.playback.player.status
        return {**result, "_review": deepcopy(self.score.loaded)}

    def _poll(self):
        if self._request_stale():
            self._cancel_request()
        try:
            while True:
                kind, token, payload = self._queue.get_nowait()
                if token is not self._cancel or token.is_set():
                    continue
                if kind == "action":
                    review, name, args, done, box = payload
                    try:
                        box["result"] = self._perform(review, name, args)
                        if name in SOUND_TOOLS and box["result"]["status"] == "queued":
                            self._reference_waiter = (done, box)
                    except Exception:
                        box["result"] = {"status": "failed", "reason": "Application action unavailable."}
                    finally:
                        if self._reference_waiter is None or self._reference_waiter[0] is not done:
                            done.set()
                elif kind == "answer":
                    review, answer, history = payload
                    if self.score.loaded is not review:
                        continue
                    self._history = history
                    self._append("ADA", answer)
                    attempt = self._request_attempt
                    if attempt and attempt.context["sha256"] == review.digest:
                        attempt.feedback.append(answer)
                    if self.speak.get() and self.score.tutor is None and not self._reference_active and self._pending_reference is None:
                        self._say(answer)
                    self.status.set("ADA ready. " + self.voice.status)
                    if (self._pending_reference is None and self._pending_practice is None
                            and not self._reference_active):
                        # Request delivered: later local activity must not "cancel" it and silence announcements.
                        self._request_context_active = False
                else:
                    self._append("ADA", payload)
                    self.status.set(payload)
        except Empty:
            pass
        try:
            self._advance_actions()
        except Exception:
            self.stop()
            self._append("ADA", "Practice or playback is unavailable. MIDI remains independent.")
        if self._thread is None or not self._thread.is_alive():
            self.ask_button.configure(state="normal")
        self._poll_microphone()
        if (getattr(self, "_listen_next", False) and (self._thread is None or not self._thread.is_alive())
                and self._pending_reference is None and not self._reference_active):
            self._listen_next = False
            self.listen_after_speech()
        if hasattr(self, "voice_status") and hasattr(self.voice, "status"):
            self.voice_status.set(self.voice.status + (" AI-generated · Reply text sent to OpenAI · API charges apply." if isinstance(self.voice, CloudVoiceService) else ""))
        if not self._closed:
            self._timer = self.after(30, self._poll)

    def _advance_actions(self):
        if ((self._pending_reference or self._reference_active or self._pending_practice)
                and self.score.activity_version != self._activity_version):
            self._cancel_request()
            return
        if self.score.tutor is not None:
            self.voice.stop()
        if self._pending_reference:
            review, exercise, tempo, finished = self._pending_reference
            if self.score.loaded is not review:
                self._cancel_request()
                return
            if finished.is_set():
                self._pending_reference = None
                # A passage invites the learner to play; a demo or replayed take does not.
                self._turn_after_sound = not isinstance(exercise, list)
                if isinstance(exercise, list):  # coach-chosen notes or a replayed take
                    self.score.playback.play_plan(exercise, tempo)
                else:
                    self.score.playback.tempo.set(str(tempo))
                    self.score.playback.play_exercise(exercise)
                self._request_playback_status = self.score.playback.player.status
                self._reference_active = self.score.playback.player.status.state == "playing"
                self._reference_review = review
                self.status.set(self.score.playback.status.get())
                if not self._reference_active:
                    self._pending_practice = None
                    self._finish_reference("failed")
        if self._reference_active:
            if self.score.loaded is not self._reference_review:
                self._cancel_request()
                return
            state = self.score.playback.player.status.state
            self._request_playback_status = self.score.playback.player.status
            if state != "playing":
                self._reference_active = False
                if state != "finished":
                    self._finish_reference("failed")
                    self._pending_practice = None
                    self._append("ADA", "Reference stopped or failed. Practice was not started.")
                else:
                    self._finish_reference("completed")
                    if getattr(self, "_turn_after_sound", True):
                        self._append("ADA", "Your turn.")
                        if self.speak.get():
                            self._turn_ready = self._say("Your turn.")
        if (self._pending_practice and not self._reference_active and self._pending_reference is None
                and (self._turn_ready is None or self._turn_ready.is_set())):
            review, exercise, context, *mode = self._pending_practice
            self._pending_practice = None
            if self.score.loaded is review:
                self._begin(exercise, context, mode[0] if mode else "practice")

    def _request_stale(self):
        """Only compare versions captured by this request, never stop newer work."""
        return getattr(self, "_request_context_active", self._request_review is not None) and (
            self.score.loaded is not self._request_review
            or (self._request_review is not None and not self._request_review.approved)
            or self.score.activity_version != self._activity_version
            or (not self._reference_active
                and self._request_playback_status is not None
                and self.score.playback.player.status != self._request_playback_status)
        )

    def _finish_reference(self, outcome):
        self._reference_outcome = outcome
        if self._reference_waiter is not None:
            done, box = self._reference_waiter
            self._reference_waiter = None
            box["result"] = {"status": outcome}
            done.set()

    def _cancel_request(self):
        """Invalidate agent work without stopping a user's newer local session."""
        self._cancel.set()
        self._finish_reference("cancelled")
        self._pending_reference = self._pending_practice = None
        self._reference_active = False
        self._turn_ready = None
        self._request_review = None
        self._request_context_active = False
        self._request_attempt = None
        self.voice.stop()
        self.status.set("ADA request cancelled because local activity changed.")

    def save_attempt(self):
        attempt = self.score.latest_attempt
        if attempt is None:
            self.status.set("No finished attempt to save.")
            return
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".json", initialfile="attempt.json")
        if path:
            snapshot = deepcopy(attempt)
            token = self._cancel
            def save():
                try:
                    snapshot.save(path)
                except Exception:
                    self._queue.put(("error", token, "Cannot save attempt. Check the destination."))
            Thread(target=save, name="ada-attempt-save", daemon=True).start()

    def stop(self):
        self._listen_pending = False
        self.hands_free.set(False)
        self.microphone.stop()
        self._cancel_request()
        self._pending_reference = self._pending_practice = None
        self._reference_active = False
        self._turn_ready = None
        self._activity_version = None
        self.voice.stop()
        self.score.stop()
        self.status.set("ADA stopped. MIDI remains connected.")

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.stop()
        self.after_cancel(self._timer)
        self.voice.close()
        self.microphone.close()
        self._api_key = None
