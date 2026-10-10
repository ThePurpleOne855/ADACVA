"""Keyboard-accessible entry points for testing each module independently."""

import argparse
from contextlib import closing
from pathlib import Path
import sys

from ada_piano.ai_tutor import Tutor
from ada_piano.ai_tutor.speech import Feedback
from ada_piano.music_sheet import load_exercise, note_name
from ada_piano.sound_sensor import list_ports, midi_notes, simulated_notes

DEFAULT_EXERCISE = Path(__file__).parent / "exercises" / "five_notes.json"


def midi_number(text: str) -> int:
    value = int(text)
    if not 0 <= value <= 127:
        raise argparse.ArgumentTypeError("MIDI notes must be from 0 to 127.")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="ADA accessible piano learning prototype")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("demo", "Practice with simulated notes; no hardware needed"),
                            ("practice", "Practice using a real MIDI input")):
        p = commands.add_parser(name, help=help_text)
        p.add_argument("--exercise", type=Path, default=DEFAULT_EXERCISE)
        p.add_argument("--speak", action="store_true", help="Speak feedback using a local voice")
        if name == "demo":
            p.add_argument("--notes", nargs="+", type=midi_number, default=[60, 61, 62, 64, 65, 67])
        else:
            p.add_argument("--port", required=True, help="Exact name from midi-ports")
    commands.add_parser("midi-ports", help="List available MIDI inputs")
    monitor = commands.add_parser("midi-monitor", help="Read MIDI independently of the tutor")
    monitor.add_argument("--port", required=True)
    reader = commands.add_parser("note-reader", help="Open the Note Reader MIDI test GUI")
    reader.add_argument("--demo", action="store_true", help="Show simulated notes without MIDI hardware")
    sheet = commands.add_parser("sheet", help="Read an exercise as accessible text")
    sheet.add_argument("--exercise", type=Path, default=DEFAULT_EXERCISE)
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
                    print(f"{note_name(event.note)}: MIDI {event.note}, velocity {event.velocity}", flush=True)
        elif args.command == "sheet":
            exercise = load_exercise(args.exercise)
            print(exercise.title)
            print(", ".join(note_name(n) for n in exercise.notes))
        else:
            exercise = load_exercise(args.exercise)
            tutor = Tutor(exercise)
            with closing(Feedback(args.speak)) as feedback:
                feedback.say(f"{exercise.title}. {tutor.prompt()}")
                source = simulated_notes(args.notes) if args.command == "demo" else midi_notes(args.port)
                with closing(source) as events:
                    for event in events:
                        feedback.say(tutor.observe(event))
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
