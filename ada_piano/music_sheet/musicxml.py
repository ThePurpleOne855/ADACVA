"""Import MusicXML attacks, chords, rests and exact quarter-note timing."""

from fractions import Fraction
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as ET
from zipfile import ZipFile, BadZipFile

from . import Exercise, ScoreEvent, ScoreNote, ScoreRest

MAX_XML_BYTES = 16 * 1024 * 1024


def _xml(data: bytes) -> ET.Element:
    if len(data) > MAX_XML_BYTES:
        raise ValueError("MusicXML document exceeds the 16 MiB limit.")
    # Permit the standard external DOCTYPE (ElementTree does not fetch it),
    # but reject entity declarations, including UTF-16/32 encodings.
    if b"<!ENTITY" in data.replace(b"\x00", b"").upper():
        raise ValueError("XML entity declarations are not supported.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid MusicXML: {exc}") from exc
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    return root


def _read(path: Path) -> ET.Element:
    if path.suffix.lower() != ".mxl":
        with path.open("rb") as stream:
            return _xml(stream.read(MAX_XML_BYTES + 1))
    try:
        with ZipFile(path) as archive:
            def member(name):
                info = archive.getinfo(name)
                if info.file_size > MAX_XML_BYTES:
                    raise ValueError("MusicXML archive member exceeds the 16 MiB limit.")
                return _xml(archive.read(info))
            container = member("META-INF/container.xml")
            roots = container.findall("./rootfiles/rootfile")
            candidates = [r for r in roots if r.get("media-type") in
                          (None, "application/vnd.recordare.musicxml+xml")]
            if not candidates:
                raise ValueError("MXL container has no MusicXML rootfile.")
            name = candidates[0].get("full-path", "")
            if not name or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name:
                raise ValueError("Invalid MXL rootfile path.")
            return member(name)
    except (BadZipFile, KeyError, RuntimeError) as exc:
        raise ValueError(f"Invalid MXL archive: {exc}") from exc


def load_musicxml(path: Path, *, part=None, staff=None, voice=None,
                  start_measure=None, end_measure=None, written_order=False) -> Exercise:
    root = _read(path)
    if root.tag != "score-partwise":
        raise ValueError("Only score-partwise MusicXML is supported; export a partwise score.")
    parts = root.findall("part")
    labels = {p.get("id"): p.findtext("part-name", "Unnamed")
              for p in root.findall("./part-list/score-part")}
    choices = ", ".join(f"{p.get('id')} ({labels.get(p.get('id'), 'Unnamed')})" for p in parts)
    if part is None and len(parts) != 1:
        raise ValueError(f"Select a MusicXML part with --part. Available: {choices or 'none'}")
    selected = parts if part is None else [p for p in parts if p.get("id") == part]
    if len(selected) != 1:
        raise ValueError(f"Unknown or ambiguous part {part!r}. Available: {choices}")
    selected = selected[0]
    all_measures = selected.findall("measure")
    count = len(all_measures)
    start = 1 if start_measure is None else start_measure
    end = count if end_measure is None else end_measure
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= count:
        raise ValueError(f"Invalid measure range: use inclusive positions 1–{count}, with start <= end.")
    measures = all_measures[start - 1:end]
    prefix = all_measures[:start - 1]
    # Earlier pitch-changing state can persist into the excerpt. Conservatively
    # reject it rather than silently importing the wrong sounding pitches.
    for earlier in prefix:
        for tag in ("transpose", "octave-shift", "measure-repeat"):
            if earlier.find(f".//{tag}") is not None:
                raise ValueError(f"Unsupported inherited MusicXML feature: {tag} before the selected range.")
    active_ending = False
    for earlier in prefix:
        for ending in earlier.iter("ending"):
            active_ending = ending.get("type") == "start"
    if active_ending and not written_order:
        raise ValueError("Selected range starts inside an unsupported repeat ending.")
    for tag in ("repeat", "ending", "transpose", "octave-shift", "measure-repeat"):
        if written_order and tag in {"repeat", "ending"}:
            continue
        if any(m.find(f".//{tag}") is not None for m in measures):
            raise ValueError(f"Unsupported MusicXML feature: {tag}. Export an unfolded, concert-pitch practice line.")
    for sound in (s for m in measures for s in m.iter("sound")):
        if any(k in sound.attrib for k in ("dacapo", "dalsegno", "tocoda", "fine")):
            raise ValueError("Playback jumps are unsupported; export an unfolded practice line.")

    # Mutable spans allow tied continuations to extend the original attack.
    spans = []
    active_ties = {}
    rests = []
    measure_start = Fraction(0)
    divisions = Fraction(1)
    for earlier in prefix:
        for value in earlier.findall("./attributes/divisions"):
            try:
                divisions = Fraction(value.text)
                if divisions <= 0:
                    raise ValueError()
            except (ValueError, TypeError, ZeroDivisionError):
                raise ValueError("Invalid inherited divisions before the selected range.") from None
    for measure in measures:
        location = f"part {selected.get('id')}, measure {measure.get('number', '?')}"
        label = measure.get("number", "?")
        cursor = Fraction(0)
        extent = Fraction(0)
        chord_base = None
        line_ends = {}
        for item in measure:
            if item.tag == "attributes" and item.find("divisions") is not None:
                try:
                    divisions = Fraction(item.findtext("divisions"))
                    if divisions <= 0:
                        raise ValueError()
                except (ValueError, TypeError, ZeroDivisionError):
                    raise ValueError(f"Invalid divisions at {location}.") from None
            if item.tag not in {"note", "backup", "forward"}:
                continue
            note_staff = item.findtext("staff", "1")
            note_voice = item.findtext("voice", "1")
            included = (staff is None or note_staff == staff) and (voice is None or note_voice == voice)
            if item.find("grace") is not None:
                chord_base = None
                if included:
                    raise ValueError(f"Unsupported grace at {location}.")
                continue
            try:
                duration = Fraction(item.findtext("duration")) / divisions
                if duration <= 0:
                    raise ValueError()
            except (ValueError, TypeError, ZeroDivisionError):
                raise ValueError(f"Invalid or missing duration at {location}.") from None
            if item.tag == "backup":
                cursor -= duration
                chord_base = None
                if cursor < 0:
                    raise ValueError(f"Backup precedes the measure start at {location}.")
                continue
            elif item.tag == "forward":
                cursor += duration
                extent = max(extent, cursor)
                chord_base = None
                continue
            chord = item.find("chord") is not None
            is_rest = item.find("rest") is not None
            if chord:
                if chord_base is None or is_rest or chord_base[2] != note_voice or duration > chord_base[1]:
                    raise ValueError(f"Invalid chord at {location}: needs a preceding pitched note in the same voice with sufficient duration.")
                onset = chord_base[0]
            else:
                onset = cursor
                cursor += duration
                chord_base = None if is_rest else (onset, duration, note_voice)
            extent = max(extent, onset + duration)
            if not included:
                continue
            for tag in ("unpitched", "cue"):
                if item.find(tag) is not None:
                    raise ValueError(f"Unsupported {tag} at {location}.")
            line = (note_staff, note_voice)
            if not chord and onset < line_ends.get(line, 0):
                raise ValueError(f"Overlapping or reordered notes at {location}; select a monophonic line.")
            line_ends[line] = max(line_ends.get(line, 0), onset + duration)
            absolute = measure_start + onset
            if is_rest:
                if any(k[0] == note_voice for k in active_ties):
                    raise ValueError(f"A rest interrupts a tie at {location}.")
                rests.append(ScoreRest(absolute, duration, note_staff, note_voice, label))
                continue
            pitch = item.find("pitch")
            if pitch is None:
                raise ValueError(f"Missing pitch at {location}.")
            try:
                step = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[pitch.findtext("step")]
                alter = Fraction(pitch.findtext("alter", "0"))
                if alter.denominator != 1:
                    raise ValueError("Microtonal pitches are unsupported")
                midi = (int(pitch.findtext("octave")) + 1) * 12 + step + int(alter)
                if not 0 <= midi <= 127:
                    raise ValueError("Pitch is outside MIDI range 0–127")
            except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
                raise ValueError(f"Invalid or unsupported pitch at {location}: {exc}") from exc
            ties = {t.get("type") for t in item.findall("tie")}
            if ties - {"start", "stop"}:
                raise ValueError(f"Unsupported tie at {location}.")
            key = (note_voice, midi)
            if "stop" in ties:
                span = active_ties.get(key)
                if span is None or span['onset'] + span['duration'] != absolute:
                    raise ValueError(f"Unmatched tie at {location}. If the range cuts a tie, extend its start to include the attack.")
                span['duration'] += duration
            else:
                if key in active_ties:
                    raise ValueError(f"Unclosed tie at {location}.")
                span = dict(onset=absolute, duration=duration, pitch=midi,
                            staff=note_staff, voice=note_voice, measure=label)
                spans.append(span)
            if "start" in ties:
                active_ties[key] = span
            else:
                active_ties.pop(key, None)
        measure_start += extent
    if active_ties:
        raise ValueError("Score or selected range ends with an unclosed tie; extend the end to include its release.")
    if not spans:
        raise ValueError("No playable notes in the selected part/staff/voice.")
    title = root.findtext("movement-title") or root.findtext("./work/work-title") or path.stem
    title = title.strip() or path.stem
    if written_order:
        title += " — written order, repeats/endings played once"
    if start_measure is not None or end_measure is not None:
        first_label, last_label = measures[0].get("number", "?"), measures[-1].get("number", "?")
        title += f" — measure positions {start}–{end} (score labels {first_label}–{last_label})"
    grouped = {}
    for span in spans:
        grouped.setdefault(span['onset'], []).append(span)
    events = tuple(ScoreEvent(onset, tuple(
        ScoreNote(s['pitch'], s['duration'], s['staff'], s['voice'])
        for s in sorted(group, key=lambda s: (s['pitch'], s['staff'], s['voice']))), group[0]['measure'])
        for onset, group in sorted(grouped.items()))
    notes = tuple(n for event in events for n in event.pitches)
    return Exercise(title, notes, events, tuple(rests), measure_start)
