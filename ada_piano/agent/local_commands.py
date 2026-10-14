"""Deterministic spoken/typed commands that work offline, without the cloud model.

Blind learners should be able to load a piece, record, hear results and stop
without depending on network access, API credit or a model's interpretation.
Anything not matched here is passed to the ADA coach unchanged.
"""

import re

from ada_piano import pieces

HELP = ("Say list pieces, then practice a piece by name. Say play it for me, guided practice, "
        "or record. Pause four seconds for results. Say list MIDI inputs, select MIDI input one, "
        "or connect piano. Say start camera, calibrate hands, or hand report. "
        "Say help settings for more controls. While playing or hearing ADA, say ADA stop. "
        "F1 opens the microphone; Escape stops; Tab moves between controls.")
SETTINGS_HELP = ("Say status, repeat, list MIDI outputs, select MIDI output one, list cameras, "
                 "select camera one, tempo sixty, slower, faster, measures one to four, "
                 "right hand, left hand, or both hands. Say save session, show tools, hide tools, "
                 "list voices, use system voice, speech speed one, stop listening, or quit. "
                 "For imports, say list score files, import score one, list score options, "
                 "review passage, next measure, then approve passage after checking the notes.")

_STOP = re.compile(r"^(stop|cancel|quiet|be quiet|pause)( (it|that|now|please|recording|practice|playing))*$")
_HELP = re.compile(r"\b(help|what can (i|you) (say|do)|commands)\b")
_LIST = re.compile(r"\b(what|which|list|show)\b.*\b(pieces|songs|music|scores)\b")
_REPLAY = re.compile(r"\b(replay|play (it |that )?back|hear (myself|my playing|what i played|how i sounded))\b")
_CAMERA = re.compile(r"\b(start|turn on|open|switch on) (the )?camera\b|^camera on$")
_CAMERA_OFF = re.compile(r"\b(stop|turn off|close|switch off) (the )?camera\b|^camera off$")
_REFERENCE = re.compile(r"\b(play it for me|play it|let me hear|listen|demonstrate|how does it (go|sound))\b")
_RECORD = re.compile(r"\b(record|recording|ready|let me (play|try)|start|play through|playthrough)\b")
_RESULTS = re.compile(r"\b(how did i do|how was (that|it)|results?|feedback|score me|grade)\b")
_QUESTION = re.compile(r"\b(why|what|how|who|when|where|tell|about|history|explain|which|is|are|was|does|hard|easy|love|like|famous|favorite|favourite)\b")
_HANDS = {"right": re.compile(r"\bright\b"), "left": re.compile(r"\bleft\b"),
          "both": re.compile(r"\b(both|two) hands?\b")}


def _plain(text):
    return " ".join(pieces._plain(text).split())


def _number(text):
    """Recognizers return either digits or English numbers for device/tempo commands."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    units = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
             "fourteen fifteen sixteen seventeen eighteen nineteen").split()
    tens = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
    words = text.replace("-", " ").split()
    if len(words) == 1:
        return units.index(text) if text in units else tens.get(text)
    if len(words) == 2 and words[0] in tens and words[1] in units[1:10]:
        return tens[words[0]] + units.index(words[1])
    if len(words) >= 2 and words[0] in units[1:4] and words[1] == "hundred":
        rest = " ".join(words[2:]).removeprefix("and ")
        tail = _number(rest) if rest else 0
        if tail is not None and tail < 100:
            return units.index(words[0]) * 100 + tail
    return None


def _controls(plain):
    commands = {
        "status": "status", "where am i": "status", "what is happening": "status",
        "repeat": "repeat", "repeat that": "repeat", "say that again": "repeat",
        "repeat last instruction": "repeat", "help settings": "settings_help",
        "connect": "midi_connect", "connect piano": "midi_connect", "connect midi": "midi_connect",
        "disconnect": "midi_disconnect", "disconnect piano": "midi_disconnect", "disconnect midi": "midi_disconnect",
        "list cameras": "camera_list", "guided practice": "guided", "start guided practice": "guided",
        "calibrate hands": "calibrate", "start calibration": "calibrate", "calibrate": "calibrate",
        "calibration done": "calibration_done", "finish calibration": "calibration_done",
        "reset calibration": "calibration_reset", "hand report": "hand_report", "hand analysis": "hand_report",
        "save session": "save_session", "save attempt": "save_session",
        "list voices": "voice_list", "quit": "quit", "exit": "quit", "close ada": "quit",
        "list import files": "score_files", "list score files": "score_files",
        "read score": "review_score", "review passage": "review_score",
        "next measure": "review_next", "approve passage": "approve_score", "approve score": "approve_score",
        "cancel import": "cancel_import",
        "list score options": "score_options",
    }
    if plain in commands:
        return commands[plain], {}
    match = re.fullmatch(r"calibrate (?:my )?(left|right)(?: hand)?", plain)
    if match:
        return "calibrate", {"hand": match[1]}
    match = re.fullmatch(r"(?:select|use|choose) score (output|part|staff|voice) (.+)", plain)
    if match:
        selected = match[2].removeprefix("number ")
        number = _number(selected)
        return "score_select", {"field": match[1], "selection": str(number) if number is not None else selected}
    if plain in {"show tools", "hide tools"}:
        return "show_tools", {"visible": plain == "show tools"}
    if plain in {"slower", "slow down", "faster", "speed up"}:
        return "tempo", {"delta": -10 if plain in {"slower", "slow down"} else 10}
    if plain in {"stop listening", "microphone off", "start listening", "microphone on"}:
        return "listening", {"enabled": plain in {"start listening", "microphone on"}}
    if plain in {"speech on", "speech off", "speak responses", "mute responses"}:
        return "speech", {"enabled": plain in {"speech on", "speak responses"}}
    match = re.fullmatch(r"(?:list|show) (?:midi )?(inputs|outputs)", plain)
    if match:
        return "midi_list", {"direction": match[1][:-1]}
    match = re.fullmatch(r"(?:select|use|choose) (?:midi )?(input|output|camera) (.+)", plain)
    if match:
        selected = match[2].removeprefix("number ")
        number = _number(selected)
        selected = str(number) if number is not None else selected
        return (("camera_select", {"selection": selected}) if match[1] == "camera" else
                ("midi_select", {"direction": match[1], "selection": selected}))
    match = re.fullmatch(r"(?:set )?(?:the )?tempo(?: to)? (.+?)(?: bpm| beats per minute)?", plain)
    if match:
        number = _number(match[1])
        if number is not None:
            return "tempo", {"value": number}
    match = re.fullmatch(r"(?:practice |select |use )?(right|left|both)(?: hand| hands)(?: only)?", plain)
    if match:
        return "hands", {"hands": match[1]}
    match = re.fullmatch(r"(?:practice |select |use )?(?:measures?|bars?) (.+?)(?: (?:to|through) (.+))?", plain)
    if match:
        first, last = _number(match[1]), _number(match[2] or match[1])
        if first is not None and last is not None:
            return ("guided_passage" if plain.startswith("practice ") else "passage"), {
                "start_measure": str(first), "end_measure": str(last)}
    match = re.fullmatch(r"(?:use |select |set )?(?:voice (.+)|(.+?) voice)", plain)
    if match and not _QUESTION.search(plain):
        return "voice_select", {"selection": match[1] or match[2]}
    return None


def parse(text, catalog):
    """Return (command, arguments) or None to let the cloud coach answer."""
    source = re.fullmatch(r"(?:hey\s+)?(?:ada[, ]+)?(?:please\s+)?import score\s+(.+)", text.strip(), re.I)
    if source:
        selected = source[1].strip().strip('"')
        number = _number(_plain(selected).removeprefix("number "))
        return "import_score", {"selection": str(number) if number is not None else selected}
    camera = re.fullmatch(r"(?:ada[, ]+)?(?:select|use|choose) camera\s+(.+)", text.strip(), re.I)
    if camera and re.search(r"[.:/\\]", camera[1]):
        return "camera_select", {"selection": camera[1]}
    plain = _plain(text.replace("'", ""))
    plain = re.sub(r"^(?:hey )?(?:ada|aida|a da) ", "", plain)
    plain = re.sub(r"^please | please$", "", plain)
    if not plain:
        return None
    # Preserve decimal speeds before general punctuation normalization.
    speed = re.fullmatch(r"(?:ada[, ]+)?(?:set )?(?:speech|speaking|voice) speed(?: to)? (\d+(?:\.\d+)?)",
                         text.strip().lower().rstrip(".!"))
    if speed:
        return "speech_speed", {"value": float(speed[1])}
    if plain in {"speech speed one", "speaking speed one", "normal speaking speed"}:
        return "speech_speed", {"value": 1.0}
    control = _controls(plain)
    if control is not None:
        return control
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
