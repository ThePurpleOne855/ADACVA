"""Local voice controls for the same devices and passages used by the desktop."""

from copy import copy
import os
from pathlib import Path

from ada_piano import pieces
from ada_piano.agent.tools import select_passage
from ada_piano.camera.analysis import describe
from ada_piano.music_sheet import note_name


def choose(selection, choices):
    choices = list(choices)
    if selection.isdigit() and 1 <= int(selection) <= len(choices):
        return choices[int(selection) - 1]
    matches = [name for name in choices if pieces._plain(name) == pieces._plain(selection)]
    if len(matches) == 1:
        return matches[0]
    raise ValueError("Selection not found. List the choices again and use its number or full name.")


def numbered(choices):
    return "; ".join(f"{index}: {name}" for index, name in enumerate(choices, 1)) or "none"


class VoiceControls:
    def __init__(self, window):
        self.window = window
        self.files = []
        self._review = None
        self._review_rows = []
        self._review_index = 0

    def perform(self, name, args):
        w, score = self.window, self.window.score
        if name == "status":
            activity = "Recording" if score.take else "Guided practice" if score.tutor else "Ready"
            title = score.loaded.exercise.title if score.loaded else "No piece loaded"
            return (f"{activity}. {title}. {w.status.get()}. Output: {w.playback.output.get() or 'none'}. "
                    f"Tempo {w.playback.tempo.get()}. {w.coach.microphone_status.get()}. "
                    f"{w.camera.status.get()}. {w.hands.status}")
        if name in {"midi_list", "midi_select"}:
            is_input = args["direction"] == "input"
            panel = w if is_input else w.playback
            panel.refresh()
            choices = panel.selector["values"]
            if name == "midi_list":
                return f"MIDI {args['direction']}s: {numbered(choices)}."
            selection = choose(args["selection"], choices)
            if is_input:
                score.stop_practice()
                w.port.set(selection)
                w.connect()
                return w.status.get()
            if w.playback.player.status.state == "playing":
                w.coach.stop()
            w.playback.output.set(selection)
            return f"MIDI output selected: {selection}. Say play it for me to hear your passage."
        if name == "midi_connect":
            w.refresh()
            if len(w._instrument_ports(w.selector["values"])) > 1 and not w.reader.connected:
                return "Choose an input first. MIDI inputs: " + numbered(w.selector["values"])
            w.connect()
            return w.status.get()
        if name == "midi_disconnect":
            w.disconnect()
            return "Piano disconnected. Say connect piano to reconnect."
        if name == "camera_list":
            w.camera.refresh()
            return "Cameras: " + numbered(w.camera._choices) + ". Say select camera followed by its number."
        if name == "camera_select":
            w.camera.refresh()
            selection = args["selection"]
            if selection.isdigit() or pieces._plain(selection) in [pieces._plain(x) for x in w.camera._choices]:
                selection = choose(selection, w.camera._choices)
            w.camera.selection.set(selection)
            w.camera.start()
            w._camera_said = "starting"
            return w.camera.status.get()
        if name == "tempo":
            if score.take is not None or score.tutor is not None or w.playback.player.status.state == "playing":
                return "Stop practice or playback before changing the tempo."
            value = args["value"] if "value" in args else float(w.playback.tempo.get()) + args["delta"]
            if not 20 <= value <= 300:
                raise ValueError("Choose a tempo from 20 to 300 beats per minute.")
            w.playback.tempo.set(f"{value:g}")
            score.take_tempo = value
            return f"Tempo set to {value:g} beats per minute."
        if name == "guided":
            w.coach.stop()
            score.practice()
            return None
        if name in {"passage", "guided_passage"}:
            if score.loaded is None:
                score.first.set(args["start_measure"])
                score.last.set(args["end_measure"])
                score.preview()
                return self.read_review()
            review = copy(score.loaded)
            review.exercise = select_passage(review, args["start_measure"], args["end_measure"])
            review.selection = {**review.selection, "start_measure_label": args["start_measure"],
                                "end_measure_label": args["end_measure"]}
            w.coach.stop()
            score._invalidate()
            score.review = review
            score._set_loaded(review)
            if name == "guided_passage":
                score.practice()
                return None
            return f"Selected measures {args['start_measure']} through {args['end_measure']}. Say record or guided practice."
        if name == "hands":
            if score.loaded is None or not hasattr(score.loaded, "piece"):
                return "Choose a checked piece first. For imports, say select score staff followed by a staff number, or all."
            review = score.loaded
            piece = pieces.find(review.piece["id"], score.catalog)
            replacement = pieces.load(piece, review.piece["passage"], args["hands"])
            if "start_measure_label" in review.selection:
                replacement.exercise = select_passage(replacement, review.selection["start_measure_label"],
                                                      review.selection["end_measure_label"])
                replacement.selection = {**replacement.selection,
                    "start_measure_label": review.selection["start_measure_label"],
                    "end_measure_label": review.selection["end_measure_label"]}
            w.coach.stop()
            score._invalidate()
            score.review = replacement
            score._set_loaded(replacement)
            return f"Selected {args['hands']} hand{'s' if args['hands'] == 'both' else ''}. Say play it for me or record."
        if name == "calibrate":
            if not w.reader.connected or w.demo:
                return "Connect a real MIDI piano before calibration. Say list MIDI inputs."
            w.coach.stop()
            if not w.camera.worker.running:
                w.camera.start()
                w._camera_said = "starting"
            if "error" in w.camera.status.get().lower():
                return w.camera.status.get()
            return w.hands.begin_calibration(args.get("hand", "right"))
        if name == "calibration_done":
            return w.hands.finish_calibration()
        if name == "calibration_reset":
            return w.hands.reset("Calibration cleared.")
        if name == "hand_report":
            summary = score.hand_summary()
            return describe(summary) if summary else "No hand report for this passage yet. " + w.hands.status
        if name == "save_session":
            score.stop_practice()
            snapshot = score.session_snapshot()
            if snapshot is None:
                return "No completed practice session to save. Load a piece and record first."
            if w.sessions is None:
                return "Automatic session saving is available in the main ADA practice window."
            w.sessions.save(snapshot, announce=True)
            return "Saving your latest session."
        if name == "show_tools":
            w.toggle_tools(args["visible"])
            return None
        if name == "quit":
            w.root.after_idle(w.close)
            return "Closing ADA and saving the current practice session."
        if name in {"score_files", "import_score"}:
            directory = Path(os.environ.get("ADA_SCORE_DIR", "scores/inbox")).expanduser()
            if name == "score_files":
                directory.mkdir(parents=True, exist_ok=True)
                self.files = sorted((p for p in directory.iterdir() if p.is_file() and
                                     p.suffix.lower() in {".pdf", ".musicxml", ".xml", ".mxl"}),
                                    key=lambda p: p.name.casefold())
                return f"Score files in {directory}: {numbered(p.name for p in self.files)}. Say import score followed by its number."
            selection = args["selection"]
            if selection.isdigit():
                filename = choose(selection, [p.name for p in self.files])
                path = next(p for p in self.files if p.name == filename)
            else:
                path = Path(selection).expanduser()
                if not path.is_file():
                    path = directory / selection
            if not path.is_file():
                raise ValueError("Score file not found. Say list score files, then import score followed by its number.")
            score.import_file(path)
            return score.status.get()
        if name == "score_options":
            return ("Score outputs: " + numbered(score._outputs) + ". Parts: " +
                    numbered(score.part_selector["values"]) + ". " + score.status.get())
        if name == "score_select":
            field, selection = args["field"], args["selection"]
            if field == "output":
                score.output.set(choose(selection, score._outputs))
                score.select_output()
            elif field == "part":
                score.part.set(choose(selection, score.part_selector["values"]))
                score.select_part()
            else:
                choices = score._selected_part()["staves" if field == "staff" else "voices"]
                if selection != "all" and selection not in choices:
                    raise ValueError("Available score " + field + " choices: " + ", ".join(choices) + ", or all.")
                getattr(score, field).set("" if selection == "all" else selection)
            return score.status.get() + " Say review passage, then approve passage after checking the notes."
        if name in {"review_score", "review_next"}:
            return self.read_review(next_page=name == "review_next")
        if name == "approve_score":
            if score.review is None:
                return "Say review passage first, and check the recognized notes against a trusted source."
            if score.review.approved:
                return "This passage is already approved. Say record or guided practice."
            score.confirmed.set(True)
            score.approve()
            return "Passage approved and loaded. Say record or play it for me." if score.loaded else score.status.get()
        if name == "cancel_import":
            score.importer.cancel()
            return "Import cancellation requested."
        raise ValueError("Unknown local control. Say help for available commands.")

    def read_review(self, next_page=False):
        score = self.window.score
        if score.review is None:
            score.preview()
        review = score.review
        if review is None:
            return score.status.get()
        if not next_page or review is not self._review:
            self._review = review
            self._review_index = 0
            rows = [(e.onset, e.measure, f"{note_name(t.pitch)}, {t.duration} beats, staff {t.staff}, voice {t.voice}")
                    for e in review.exercise.events for t in e.tones]
            rows.extend((r.onset, r.measure, f"rest, {r.duration} beats, staff {r.staff}, voice {r.voice}")
                        for r in review.exercise.rests)
            self._review_rows = sorted(rows)
        start = self._review_index
        if start >= len(self._review_rows):
            return "End of passage review. After checking the notes against a trusted source, say approve passage."
        measure = self._review_rows[start][1]
        lines = []
        while self._review_index < len(self._review_rows) and len(lines) < 8:
            onset, label, text = self._review_rows[self._review_index]
            if label != measure:
                break
            lines.append(f"Beat {onset}: {text}.")
            self._review_index += 1
        more = self._review_index < len(self._review_rows)
        ending = ("Say next measure to continue." if more else
                  "End of passage. After checking the notes against a trusted source, say approve passage.")
        return (f"Measure {measure}. Beat positions start at zero for this passage. " + " ".join(lines) +
                " " + ending + (" PDF recognition can be wrong; a spoken preview does not verify it." if start == 0 else ""))
