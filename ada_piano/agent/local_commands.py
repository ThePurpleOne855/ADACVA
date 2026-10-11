"""Deterministic spoken/typed commands that work offline, without the cloud model.

Blind learners should be able to load a piece, record, hear results and stop
without depending on network access, API credit or a model's interpretation.
Anything not matched here is passed to the ADA coach unchanged.
"""

import re

from ada_piano import pieces

HELP = ("You can say: list pieces. Practice Für Elise, or Ode to Joy, optionally with a passage "
        "like theme, and right hand or left hand. Play it for me, to hear it. Replay, to hear yourself. Start camera. Record, then play; "
        "pause four seconds when done. How did I do. Stop. Keys: F1 speak to ADA, F5 record, "
        "F6 results, F7 camera, Escape stop.")

_STOP = re.compile(r"^(stop|cancel|quiet|be quiet|pause)( (it|that|now|please|recording|practice|playing))*$")
_HELP = re.compile(r"\b(help|what can (i|you) (say|do)|commands)\b")
_LIST = re.compile(r"\b(what|which|list|show)\b.*\b(pieces|songs|music|scores)\b")
_REPLAY = re.compile(r"\b(replay|play (it |that )?back|what i played|my playing|hear myself|how i sounded)\b")
_CAMERA = re.compile(r"\b(start|turn on|open|switch on) (the )?camera\b|^camera on$")
_CAMERA_OFF = re.compile(r"\b(stop|turn off|close|switch off) (the )?camera\b|^camera off$")
_REFERENCE = re.compile(r"\b(play it for me|play it|let me hear|listen|demonstrate|how does it (go|sound))\b")
_RECORD = re.compile(r"\b(record|recording|ready|let me (play|try)|start|play through|playthrough)\b")
_RESULTS = re.compile(r"\b(how did i do|how was (that|it)|results?|feedback|score me|grade)\b")
_QUESTION = re.compile(r"\b(why|what|how|who|when|where|tell|about|history|explain|which|is|are|was|does|hard|easy|love|like|famous|favorite|favourite)\b")
_HANDS = {"right": re.compile(r"\bright\b"), "left": re.compile(r"\bleft\b"),
          "both": re.compile(r"\b(both|two) hands?\b")}


def _plain(text):
    return pieces._plain(text)


def parse(text, catalog):
    """Return (command, arguments) or None to let the cloud coach answer."""
    plain = _plain(text.replace("'", ""))
    if not plain:
        return None
    if _STOP.match(plain):
        return "stop", {}
    # Short commands only, so questions like "can you help me with measure three in the
    # left hand" or "where should I start" still reach the coach.
    short = len(plain.split()) <= 6
    if _HELP.search(plain) and short:
        return "help", {}
    piece = pieces.find(plain, catalog)
    if piece is not None and not _QUESTION.search(plain):
        padded = f" {plain} "
        passage = next((name for name in piece.passages if f" {_plain(name)} " in padded), None)
        hands = next((name for name, pattern in _HANDS.items() if pattern.search(plain)), None)
        return "load", {"piece": piece.id, "passage": passage, "hands": hands}
    if _LIST.search(plain):
        return "list", {}
    if _RESULTS.search(plain):
        return "results", {}
    if _CAMERA_OFF.search(plain) and short:
        return "camera_off", {}
    if _CAMERA.search(plain) and short:
        return "camera", {}
    if _REPLAY.search(plain) and short:
        return "replay", {}
    if _REFERENCE.search(plain) and short:
        return "reference", {}
    if _RECORD.search(plain) and short and not _QUESTION.search(plain):
        return "record", {}
    return None


def list_text(catalog):
    titles = [piece.title for piece in catalog]
    return ("I have " + ", and ".join(titles) + ". Say, for example, ADA, practice " + titles[0] + "."
            if titles else "No checked pieces are installed.")
