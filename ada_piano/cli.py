"""Keyboard-accessible entry points for testing each module independently."""

import argparse
from contextlib import closing
from pathlib import Path
import sys

from ada_piano.ai_tutor import Tutor
from ada_piano.ai_tutor.speech import Feedback
from ada_piano.music_sheet import load_exercise, note_name
from ada_piano.sound_sensor import list_ports, midi_notes, simulated_notes, simulated_chords

DEFAULT_EXERCISE = Path(__file__).parent / "exercises" / "five_notes.json"


def midi_number(text: str) -> int:
    value = int(text)
    if not 0 <= value <= 127:
        raise argparse.ArgumentTypeError("MIDI notes must be from 0 to 127.")
    return value


def midi_chord(text: str) -> tuple[int, ...]:
    try:
        notes = tuple(midi_number(n) for n in text.split("+"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use MIDI pitches separated by +, e.g. 60+64+67") from exc
    if len(set(notes)) != len(notes):
        raise argparse.ArgumentTypeError("A chord cannot contain duplicate pitches.")
    return notes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ADA accessible piano learning prototype")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("demo", "Practice with simulated notes; no hardware needed"),
                            ("practice", "Practice using a real MIDI input")):
        p = commands.add_parser(name, help=help_text)
        p.add_argument("--exercise", type=Path, default=DEFAULT_EXERCISE)
        p.add_argument("--speak", action="store_true", help="Speak feedback using a local voice")
        p.add_argument("--chord-window-ms", type=float, default=150,
                       help="Maximum spread of chord note-on times in milliseconds (default 150)")
        if name == "demo":
            inputs = p.add_mutually_exclusive_group()
            inputs.add_argument("--notes", nargs="+", type=midi_number)
            inputs.add_argument("--chords", nargs="+", type=midi_chord,
                                help="Simulated attack groups, e.g. 60+64+67 62+65+69")
        else:
            p.add_argument("--port", required=True, help="Exact name from midi-ports")
    commands.add_parser("midi-ports", help="List available MIDI inputs")
    monitor = commands.add_parser("midi-monitor", help="Read MIDI independently of the tutor")
    monitor.add_argument("--port", required=True)
    reader = commands.add_parser("note-reader", help="Open the Note Reader MIDI test GUI")
    reader.add_argument("--demo", action="store_true", help="Show simulated notes without MIDI hardware")
    sheet = commands.add_parser("sheet", help="Read an exercise as accessible text")
    sheet.add_argument("--exercise", type=Path, default=DEFAULT_EXERCISE)
    for name in ("demo", "practice", "sheet"):
        command = commands.choices[name]
        command.add_argument("--part", help="MusicXML part ID, e.g. P1")
        command.add_argument("--staff", help="MusicXML staff number, e.g. 1")
        command.add_argument("--voice", help="MusicXML voice ID, e.g. 1")
        command.add_argument("--start-measure", type=int,
                             help="First measure position, inclusive, counting from 1 (not printed label)")
        command.add_argument("--end-measure", type=int,
                             help="Last measure position, inclusive (defaults to end of part)")
    camera = commands.add_parser("camera", help="Check camera capture independently")
    camera.add_argument("--index", type=int, default=0)
    camera.add_argument("--seconds", type=float, default=5)
    camera.add_argument("--preview", action="store_true", help="Open an optional visual preview")
    args = parser.parse_args(argv)
    try:
        if args.command == "note-reader":
            try:
                from ada_piano.note_reader.gui import launch
            except ImportError as exc:
                raise RuntimeError("Note Reader requires Tkinter. On Arch Linux install tk: sudo pacman -S tk") from exc
            launch(demo=args.demo)
        elif args.command == "camera":
            from ada_piano.camera import check_camera
            print("Checking camera capture. Press Control C to stop.", flush=True)
            count = check_camera(args.index, args.seconds, args.preview)
            print(f"Camera check complete: {count} frames captured. Hand tracking is not enabled.")
        elif args.command == "midi-ports":
            ports = list_ports()
            print("\n".join(ports) if ports else "No MIDI inputs found. Connect the USB-to-MIDI interface and retry.")
        elif args.command == "midi-monitor":
            print("Listening for notes. Press Control C to stop.", flush=True)
            with closing(midi_notes(args.port)) as events:
                for event in events:
                    print(f"{event.kind}: {note_name(event.note)}, MIDI {event.note}, velocity {event.velocity}", flush=True)
        elif args.command == "sheet":
            exercise = load_exercise(args.exercise, part=args.part, staff=args.staff, voice=args.voice,
                                     start_measure=args.start_measure, end_measure=args.end_measure)
            if args.exercise.suffix.lower() != ".json":
                print("MusicXML pitch practice: rhythm and rests are not graded; tied notes count once.")
            print(exercise.title)
            print(", ".join(" + ".join(note_name(n) for n in event.pitches) for event in exercise.events))
            if args.exercise.suffix.lower() != ".json":
                print(f"{len(exercise.events)} attack groups; {len(exercise.rests)} rests; {exercise.duration} quarter-note beats.")
        else:
            exercise = load_exercise(args.exercise, part=args.part, staff=args.staff, voice=args.voice,
                                     start_measure=args.start_measure, end_measure=args.end_measure)
            tutor = Tutor(exercise, chord_window=args.chord_window_ms / 1000)
            with closing(Feedback(args.speak)) as feedback:
                if args.exercise.suffix.lower() != ".json":
                    feedback.say("MusicXML pitch practice. Rhythm and rests are not graded; tied notes count once.")
                feedback.say(f"{exercise.title}. {tutor.prompt()}")
                if args.command == "demo":
                    source = simulated_chords(args.chords) if args.chords is not None else simulated_notes(
                        args.notes if args.notes is not None else [60, 61, 62, 64, 65, 67], releases=True)
                else:
                    source = midi_notes(args.port)
                with closing(source) as events:
                    for event in events:
                        response = tutor.observe(event)
                        if response:
                            feedback.say(response)
                        if tutor.complete:
                            break
                if not tutor.complete:
                    feedback.say(f"Session ended. {tutor.prompt()}")
        return 0
    except KeyboardInterrupt:
        print("\nSession stopped.")
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
