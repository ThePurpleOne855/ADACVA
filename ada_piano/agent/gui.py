"""Compact coach panel. Workers never touch Tk; actions return through a queue."""

from copy import deepcopy
from queue import Empty, Queue
from threading import Event, Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ada_piano.voice import VoiceService
from .coach import Coach
from .tools import AgentTools, passage_context, select_passage


class CoachPanel(ttk.Frame):
    def __init__(self, parent, score, *, client=None, voice=None):
        super().__init__(parent, padding=10)
        self.score = score
        self.client = client
        self.voice = voice if voice is not None else VoiceService()
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
        self.text = tk.StringVar()
        self.speak = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="ADA ready. Approve a passage first. " + self.voice.status)
        ttk.Label(self, text="ADA Coach").pack(anchor="w")
        self.transcript = tk.Text(self, height=10, wrap="word", state="disabled")
        self.transcript.pack(fill="both", expand=True)
        entry = ttk.Entry(self, textvariable=self.text)
        entry.pack(fill="x", pady=5)
        entry.bind("<Return>", lambda event: self.ask())
        controls = ttk.Frame(self)
        controls.pack(fill="x")
        self.ask_button = ttk.Button(controls, text="Ask ADA", command=self.ask)
        self.ask_button.pack(side="left")
        ttk.Button(controls, text="Stop", command=self.stop).pack(side="left", padx=5)
        ttk.Checkbutton(controls, text="Speak responses", variable=self.speak,
                        command=self._speech_changed).pack(side="left")
        ttk.Button(controls, text="Save latest attempt", command=self.save_attempt).pack(side="left", padx=5)
        ttk.Label(self, textvariable=self.status, wraplength=850).pack(anchor="w")
        self._timer = self.after(30, self._poll)

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
        if self.score.tutor is not None or self.score.playback.player.status.state == "playing":
            self.status.set("Stop practice / sound before asking ADA, so speech does not overlap.")
            return
        review = self.score.loaded
        if review is None:
            self._append("ADA", "No approved passage is loaded. Review and approve a score first.")
            return
        identity = (review.digest, repr(review.selection))
        if identity != self._identity:
            self._history = []
            self._identity = identity
        attempt = self.score.latest_attempt
        summary = attempt.summary() if attempt else None
        if summary and (summary["score_sha256"] != review.digest or
                        any(attempt.context["selection"].get(k) != v for k, v in review.selection.items())):
            summary = None
        snapshot = deepcopy(review)
        token = self._cancel = Event()
        self._append("You", question)
        self.text.set("")
        self.status.set("Thinking…")
        self.ask_button.configure(state="disabled")

        def action(name, arguments):
            done, box = Event(), {}
            self._queue.put(("action", token, (review, name, arguments, done, box)))
            while not done.wait(.05):
                if token.is_set():
                    return {"status": "cancelled"}
            return box["result"]

        tools = AgentTools(snapshot, summary, action)
        coach = Coach(tools, self.client)
        coach.history = list(self._history)

        def run():
            try:
                answer = coach.ask(question, token)
                self._queue.put(("answer", token, (review, answer, coach.history)))
            except Exception:
                # Avoid leaking SDK errors, credentials or remote payloads into UI/logs.
                self._queue.put(("error", token, "ADA AI is unavailable. Local pitch/chord practice is still available. Check the agent dependency, OPENAI_API_KEY, model and network."))
            finally:
                coach.close()
        self._thread = Thread(target=run, name="ada-coach", daemon=True)
        self._thread.start()

    def _perform(self, review, name, arguments):
        if self.score.loaded is not review or not review.approved:
            return {"status": "rejected", "reason": "Approved selection changed."}
        if name == "stop_practice":
            self._pending_reference = self._pending_practice = None
            self._reference_active = False
            self.voice.stop()
            self.score.stop()
            self._activity_version = self.score.activity_version
            return {"status": "stopped"}
        exercise = select_passage(review, arguments["start_measure"], arguments["end_measure"])
        if name == "play_reference":
            if not messagebox.askyesno("ADA reference", f"Play approved measures {arguments['start_measure']}–{arguments['end_measure']} at {arguments['tempo']} BPM?", parent=self):
                return {"status": "declined"}
            if self._cancel.is_set() or self.score.loaded is not review or not review.approved:
                return {"status": "cancelled", "reason": "Request or approval changed during confirmation."}
            self.score.stop()
            self._activity_version = self.score.activity_version
            announcement = f"I'll play measure {arguments['start_measure']} through {arguments['end_measure']} once."
            self._append("ADA", announcement)
            finished = self.voice.say(announcement) if self.speak.get() else Event()
            if not self.speak.get():
                finished.set()
            self._pending_reference = (review, exercise, arguments["tempo"], finished)
            return {"status": "queued", "announcement": announcement}
        context = passage_context(review)
        context["selection"] = {**context["selection"], "start_measure_label": arguments["start_measure"], "end_measure_label": arguments["end_measure"]}
        chosen = set(e.measure for e in exercise.events)
        context["events"] = [e for e in context["events"] if e["measure"] in chosen]
        context["rests"] = [r for r in context["rests"] if r["measure"] in chosen]
        for index, event in enumerate(context["events"]):
            event["approved_event_index"] = event["event_index"]
            event["event_index"] = index
        if (self._pending_reference is not None or self._reference_active
                or (self._turn_ready is not None and not self._turn_ready.is_set())):
            self._pending_practice = (review, exercise, context)
            return {"status": "queued_after_reference"}
        self.voice.stop()
        self.score.practice(exercise, context)
        self.status.set(self.score.feedback.get())
        return {"status": "practicing" if self.score.tutor is not None else "unavailable"}

    def _poll(self):
        try:
            while True:
                kind, token, payload = self._queue.get_nowait()
                if token is not self._cancel or token.is_set():
                    continue
                if kind == "action":
                    review, name, args, done, box = payload
                    try:
                        box["result"] = self._perform(review, name, args)
                    except Exception:
                        box["result"] = {"status": "failed", "reason": "Application action unavailable."}
                    finally:
                        done.set()
                elif kind == "answer":
                    review, answer, history = payload
                    if self.score.loaded is not review:
                        continue
                    self._history = history
                    self._append("ADA", answer)
                    attempt = self.score.latest_attempt
                    if attempt and attempt.context["sha256"] == review.digest:
                        attempt.feedback.append(answer)
                    if self.speak.get() and self.score.tutor is None and not self._reference_active and self._pending_reference is None:
                        self.voice.say(answer)
                    self.status.set("ADA ready. " + self.voice.status)
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
        if not self._closed:
            self._timer = self.after(30, self._poll)

    def _advance_actions(self):
        if ((self._pending_reference or self._reference_active or self._pending_practice)
                and self.score.activity_version != self._activity_version):
            self.stop()
            return
        if self.score.tutor is not None:
            self.voice.stop()
        if self._pending_reference:
            review, exercise, tempo, finished = self._pending_reference
            if self.score.loaded is not review:
                self.stop()
                return
            if finished.is_set():
                self._pending_reference = None
                self.score.playback.tempo.set(str(tempo))
                self.score.playback.play_exercise(exercise)
                self._reference_active = self.score.playback.player.status.state == "playing"
                self._reference_review = review
                self.status.set(self.score.playback.status.get())
                if not self._reference_active:
                    self._pending_practice = None
        if self._reference_active:
            if self.score.loaded is not self._reference_review:
                self.stop()
                return
            state = self.score.playback.player.status.state
            if state != "playing":
                self._reference_active = False
                if state != "finished":
                    self._pending_practice = None
                    self._append("ADA", "Reference stopped or failed. Practice was not started.")
                else:
                    self._append("ADA", "Your turn.")
                    if self.speak.get():
                        self._turn_ready = self.voice.say("Your turn.")
        if (self._pending_practice and not self._reference_active and self._pending_reference is None
                and (self._turn_ready is None or self._turn_ready.is_set())):
            review, exercise, context = self._pending_practice
            self._pending_practice = None
            if self.score.loaded is review:
                self.score.practice(exercise, context)
                self.status.set(self.score.feedback.get())

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
        self._cancel.set()
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
