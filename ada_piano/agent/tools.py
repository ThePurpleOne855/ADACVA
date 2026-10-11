"""Allowlisted operations on an approved in-memory score, never files or raw MIDI."""

from dataclasses import replace
import math
import re

from ada_piano import pieces
from ada_piano.music_sheet import Exercise
from ada_piano.playback import PlaybackNote, parse_note, validate_notes
from ada_piano.score_import.review import playback_notes


def passage_context(review):
    data = review.context()
    data.pop("musicxml", None)
    data["calibrated_fingering_available"] = False
    for index, event in enumerate(data["events"]):
        event["event_index"] = index
    return data


def select_passage(review, start_measure, end_measure):
    """Use score labels, not guessed measure positions; never reread another file."""
    review.context()  # approval gate
    if not isinstance(start_measure, str) or not isinstance(end_measure, str):
        raise ValueError("Measure labels must be strings from the approved passage.")
    labels = list(dict.fromkeys(e.measure for e in review.exercise.events))
    if start_measure not in labels or end_measure not in labels:
        raise ValueError("Requested measure is outside the approved passage.")
    first, last = labels.index(start_measure), labels.index(end_measure)
    if first > last:
        raise ValueError("Measure range is reversed.")
    chosen = set(labels[first:last + 1])
    original = [e for e in review.exercise.events if e.measure in chosen]
    rests = [r for r in review.exercise.rests if r.measure in chosen]
    origin = min([e.onset for e in original] + [r.onset for r in rests])
    events = tuple(replace(e, onset=e.onset - origin) for e in original)
    rests = tuple(replace(r, onset=r.onset - origin) for r in rests)
    return Exercise(review.exercise.title, tuple(n for e in events for n in e.pitches), events, rests)


class AgentTools:
    def __init__(self, review, summary=None, action=None, performance=None, catalog=None):
        self.review = review
        self.summary = summary
        self.performance = performance
        self.action = action
        self.catalog = catalog

    def _pieces(self):
        if self.catalog is None:
            self.catalog = pieces.catalog()
        return self.catalog

    def dispatch(self, name, arguments):
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be an object.")
        if name in {"get_current_passage", "get_attempt_summary", "get_performance_report",
                    "list_pieces", "stop_practice", "replay_my_playing"}:
            if arguments:
                raise ValueError("This tool takes no arguments.")
            if name == "get_current_passage":
                return passage_context(self.review) if self.review else {"status": "no_approved_score"}
            if name == "get_attempt_summary":
                return self.summary or {"status": "no_attempt"}
            if name == "get_performance_report":
                return self.performance or {"status": "no_play_through"}
            if name == "list_pieces":
                return {"pieces": [piece.describe() for piece in self._pieces()]}
            if name == "replay_my_playing" and not self.performance:
                return {"status": "no_play_through"}
            return self._action(name, {})
        if name == "play_notes":
            return self._action(name, note_plan(arguments))
        if name == "load_piece":
            return self._load_piece(arguments)
        allowed = {"start_measure", "end_measure"}
        if name == "play_reference":
            allowed |= {"tempo"}
        elif name not in {"start_practice", "start_play_through"}:
            raise ValueError("Unknown or forbidden tool.")
        if set(arguments) != allowed:
            raise ValueError("Unexpected or missing tool arguments.")
        if self.review is None:
            raise ValueError("No approved passage is loaded.")
        exercise = select_passage(self.review, arguments["start_measure"], arguments["end_measure"])
        if name == "play_reference":
            tempo = arguments["tempo"]
            if type(tempo) not in (int, float) or not math.isfinite(tempo):
                raise ValueError("Tempo must be a finite number.")
            playback_notes(exercise, tempo=tempo)  # existing safety limits
        return self._action(name, arguments)

    def _load_piece(self, arguments):
        """Only pre-checked catalog pieces; never arbitrary files or unreviewed imports."""
        if set(arguments) != {"piece", "passage", "hands"} or not all(
                isinstance(v, str) and len(v) <= 100 for v in arguments.values()):
            raise ValueError("load_piece needs piece, passage and hands strings.")
        piece = pieces.find(arguments["piece"], self._pieces())
        if piece is None:
            raise ValueError("Unknown piece. Call list_pieces for the available titles.")
        passage = arguments["passage"] or "whole"
        hands = arguments["hands"] or next(iter(piece.hands))
        if passage not in piece.passages:
            raise ValueError(f"Unknown passage. Choose one of: {', '.join(piece.passages)}.")
        if hands not in piece.hands:
            raise ValueError(f"Unsupported hands. Choose one of: {', '.join(piece.hands)}.")
        result = dict(self._action("load_piece", {"piece": piece.id, "passage": passage, "hands": hands}))
        review = result.pop("_review", None)
        if review is not None:
            # Later tools in this turn refer to the newly loaded passage.
            self.review, self.summary, self.performance = review, None, None
        return result

    def _action(self, name, arguments):
        if self.action is None:
            return {"status": "actions_unavailable"}
        return self.action(name, arguments)


def note_plan(arguments):
    """Validate a short demonstration: up to 16 piano notes as a melody or one chord."""
    if set(arguments) != {"notes", "chord", "tempo"}:
        raise ValueError("play_notes needs notes, chord and tempo.")
    text, chord, tempo = arguments["notes"], arguments["chord"], arguments["tempo"]
    if not isinstance(text, str) or type(chord) is not bool:
        raise ValueError("notes must be a string and chord a boolean.")
    if type(tempo) not in (int, float) or not math.isfinite(tempo) or not 30 <= tempo <= 200:
        raise ValueError("Tempo must be from 30 to 200 BPM.")
    tokens = [t for t in re.split(r"[\s,]+", text.strip()) if t]
    if not 1 <= len(tokens) <= 16:
        raise ValueError("Play between 1 and 16 notes, such as 'C4 E4 G4'.")
    pitches = [parse_note(t) for t in tokens]
    if any(not 21 <= p <= 108 for p in pitches):
        raise ValueError("Notes must be on an 88-key piano (A0 to C8).")
    if chord:
        pitches = sorted(set(pitches))
        notes = [PlaybackNote(p, 0, 2, 70, 1) for p in pitches]
    else:
        notes = [PlaybackNote(p, i, 1, 70, 1) for i, p in enumerate(pitches)]
    validate_notes(notes, tempo)
    return {"notes": " ".join(tokens), "chord": chord, "tempo": tempo, "plan": notes}
