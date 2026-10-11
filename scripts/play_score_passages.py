"""Play the first and last four written measures with a five-second pause."""

import argparse
from pathlib import Path
import time

from ada_piano.playback import ReferencePlayer
from ada_piano.score_import.conversion import score_parts
from ada_piano.score_import.review import ReviewedScore, playback_notes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("score", type=Path)
    parser.add_argument("--port", help="Exact MIDI output name; defaults to the sole Yamaha/mioXC output")
    parser.add_argument("--dry-run", action="store_true", help="Validate passages without accessing MIDI")
    args = parser.parse_args()
    parts = score_parts(args.score)
    if len(parts) != 1:
        parser.error("This command requires a score with one piano part.")
    part = parts[0]
    count = part["measures"]
    passages = []
    for start, end in ((1, min(4, count)), (max(1, count - 3), count)):
        review = ReviewedScore(args.score, part=part["id"], start_measure=start,
                               end_measure=end, written_order=True)
        notes = playback_notes(review.exercise, tempo=90)
        passages.append(notes)
        print(f"Measure positions {start}–{end}: {len(notes)} notes, both hands, written order.", flush=True)
    if args.dry_run:
        return
    player = ReferencePlayer()
    try:
        ports = player.list_ports()
        port = args.port
        if port is None:
            candidates = [p for p in ports if any(name in p.lower() for name in ("mioxc", "yamaha"))]
            if len(candidates) != 1:
                parser.error(f"Specify --port using one of these outputs: {ports}")
            port = candidates[0]
        if port not in ports:
            parser.error(f"Output not available. Available outputs: {ports}")
        for index, notes in enumerate(passages):
            if index:
                print("Pausing for 5 seconds…", flush=True)
                time.sleep(5)
            print(f"Playing passage {index + 1} through {port}. Ctrl+C stops playback.", flush=True)
            player.play_notes(notes, port_name=port, tempo=90)
            while player.status.state == "playing":
                time.sleep(0.02)
            if player.status.state != "finished":
                raise RuntimeError(player.status.detail)
        print("Finished both passages.", flush=True)
    finally:
        player.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Playback stopped.")
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
