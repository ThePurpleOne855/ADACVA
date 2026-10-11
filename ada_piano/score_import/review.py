"""Reviewed passage shared by reference playback, the tutor, and future agents."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path

from ada_piano.music_sheet import load_exercise, note_name
from ada_piano.playback import PlaybackNote, validate_notes
from .conversion import save_json


def playback_notes(exercise, *, tempo: float = 90, velocity=70, channel=1):
    notes = []
    for event in exercise.events:
        # Unisons in two voices need one MIDI key held for the longest duration.
        durations = {}
        for tone in event.tones:
            durations[tone.pitch] = max(durations.get(tone.pitch, 0), tone.duration)
        notes.extend(PlaybackNote(pitch, float(event.onset), float(duration), velocity, channel)
                     for pitch, duration in sorted(durations.items()))
    return validate_notes(notes, tempo)


class ReviewedScore:
    def __init__(self, path, **selection):
        self.path = Path(path).resolve()
        self.selection = selection
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.exercise = load_exercise(self.path, **selection)
        self.approved = False

    def approve(self):
        if hashlib.sha256(self.path.read_bytes()).hexdigest() != self.digest:
            raise ValueError("MusicXML changed since preview. Load the preview again before approving.")
        self.approved = True

    def context(self):
        if not self.approved:
            raise ValueError("Review and approve the passage before loading it.")
        return {
            "title": self.exercise.title, "musicxml": str(self.path), "sha256": self.digest,
            "selection": self.selection, "reviewed": True,
            "timing_unit": "quarter-note beats", "duration": str(self.exercise.duration),
            "limitations": "Pitch/chord practice; fixed-tempo reference. Score tempo changes, pedal, dynamics, and fingering are not interpreted.",
            "events": [{"onset": str(event.onset), "measure": event.measure,
                        "tones": [{"pitch": tone.pitch, "name": note_name(tone.pitch),
                                   "duration": str(tone.duration), "staff": tone.staff, "voice": tone.voice}
                                  for tone in event.tones]} for event in self.exercise.events],
            "rests": [{"onset": str(rest.onset), "duration": str(rest.duration),
                       "staff": rest.staff, "voice": rest.voice, "measure": rest.measure}
                      for rest in self.exercise.rests],
        }

    def save(self, folder):
        path = Path(folder) / "reviewed-exercise.json"
        data = self.context()
        data["approved_at"] = datetime.now(timezone.utc).isoformat()
        save_json(path, data)
        return path
