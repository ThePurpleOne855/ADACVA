"""Run two-hand tracking on an image or a USB camera."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time


FINGERTIPS = {4: "thumb", 8: "index", 12: "middle", 16: "ring", 20: "pinky"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--image", type=Path, help="Process one still image")
    source.add_argument("--source", type=int, default=0, help="USB camera index (default: 0)")
    parser.add_argument("--model", type=Path, default=Path("hand_landmarker.task"))
    parser.add_argument("--output", type=Path, help="Save an annotated image (requires --image)")
    parser.add_argument("--jsonl", type=Path, help="Write timestamped landmarks as JSON lines")
    parser.add_argument("--seconds", type=float, help="Stop live capture after this many seconds")
    parser.add_argument("--no-preview", action="store_true", help="Run without a display window")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    args = parser.parse_args()
    if args.output and not args.image:
        parser.error("--output requires --image")
    if args.seconds is not None and args.seconds <= 0:
        parser.error("--seconds must be positive")
    if args.width <= 0 or args.height <= 0:
        parser.error("--width and --height must be positive")
    return args


def observation(result: object, timestamp_ms: int, captured_monotonic_ns: int | None,
                width: int, height: int) -> dict:
    """Keep raw normalized coordinates for downstream calibration and MIDI matching."""
    hands = []
    for index, landmarks in enumerate(result.hand_landmarks):
        category = result.handedness[index][0] if result.handedness[index] else None
        hands.append(
            {
                "handedness": category.category_name if category else "Unknown",
                "score": round(float(category.score), 4) if category else None,
                "landmarks": [
                    {"x": round(float(p.x), 5), "y": round(float(p.y), 5), "z": round(float(p.z), 5)}
                    for p in landmarks
                ],
            }
        )
    return {"timestamp_ms": timestamp_ms, "captured_monotonic_ns": captured_monotonic_ns,
            "width": width, "height": height, "hands": hands}


def annotate(frame: object, result: object, cv2: object, mp: object) -> object:
    height, width = frame.shape[:2]
    connections = mp.tasks.vision.HandLandmarksConnections.HAND_CONNECTIONS
    for index, landmarks in enumerate(result.hand_landmarks):
        color = (52, 220, 52) if index == 0 else (255, 160, 36)
        for edge in connections:
            first, second = landmarks[edge.start], landmarks[edge.end]
            a = (int(first.x * width), int(first.y * height))
            b = (int(second.x * width), int(second.y * height))
            cv2.line(frame, a, b, color, 2)
        for tip_index, finger in FINGERTIPS.items():
            tip = landmarks[tip_index]
            point = (int(tip.x * width), int(tip.y * height))
            cv2.circle(frame, point, 6, (0, 255, 255), -1)
            cv2.putText(frame, finger[0].upper(), (point[0] + 8, point[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        if result.handedness[index]:
            label = result.handedness[index][0].category_name
            wrist = landmarks[0]
            cv2.putText(frame, label, (int(wrist.x * width), int(wrist.y * height)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
    return frame


def main() -> int:
    args = parse_args()
    if not args.model.is_file():
        print(f"Model missing: {args.model}. See docs/CAMERA.md for download instructions.", file=sys.stderr)
        return 2
    try:
        import cv2
        import mediapipe as mp
    except ImportError as exc:
        print(f"Camera dependency missing: {exc}. Install with pip install -e '.[camera]'.", file=sys.stderr)
        return 2

    mode = mp.tasks.vision.RunningMode.IMAGE if args.image else mp.tasks.vision.RunningMode.VIDEO
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(args.model.resolve())),
        running_mode=mode,
        num_hands=2,
    )
    log = args.jsonl.open("w", encoding="utf-8") if args.jsonl else None
    try:
        with mp.tasks.vision.HandLandmarker.create_from_options(options) as tracker:
            if args.image:
                frame = cv2.imread(str(args.image))
                if frame is None:
                    print(f"Cannot read image: {args.image}", file=sys.stderr)
                    return 2
                image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                 data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                result = tracker.detect(image)
                record = observation(result, 0, None, frame.shape[1], frame.shape[0])
                print(f"Detected {len(record['hands'])} hand(s) in {args.image}")
                if log:
                    log.write(json.dumps(record) + "\n")
                if args.output:
                    if not cv2.imwrite(str(args.output), annotate(frame, result, cv2, mp)):
                        print(f"Cannot write image: {args.output}", file=sys.stderr)
                        return 2
                return 0

            backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
            camera = cv2.VideoCapture(args.source, backend)
            if not camera.isOpened():
                print(f"Cannot open camera index {args.source}. Check USB connection and try --source 1.", file=sys.stderr)
                return 2
            camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
            started = time.monotonic()
            last_timestamp_ms = -1
            frames = 0
            try:
                while args.seconds is None or time.monotonic() - started < args.seconds:
                    ok, frame = camera.read()
                    if not ok:
                        print("Camera stopped delivering frames.", file=sys.stderr)
                        return 2
                    if frames == 0:
                        print(f"Camera {args.source}: {frame.shape[1]}x{frame.shape[0]} captured", flush=True)
                    captured_monotonic_ns = time.monotonic_ns()
                    timestamp_ms = max(last_timestamp_ms + 1, int((time.monotonic() - started) * 1000))
                    last_timestamp_ms = timestamp_ms
                    image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                     data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    result = tracker.detect_for_video(image, timestamp_ms)
                    frames += 1
                    if log:
                        log.write(json.dumps(observation(result, timestamp_ms, captured_monotonic_ns,
                                                         frame.shape[1], frame.shape[0])) + "\n")
                    if not args.no_preview:
                        cv2.imshow("ADA hand tracking - press q to quit", annotate(frame, result, cv2, mp))
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            break
            except KeyboardInterrupt:
                pass
            finally:
                camera.release()
                if not args.no_preview:
                    cv2.destroyAllWindows()
            elapsed = max(time.monotonic() - started, 0.001)
            print(f"Processed {frames} frames in {elapsed:.1f}s ({frames / elapsed:.1f} fps)")
            return 0
    finally:
        if log:
            log.close()


if __name__ == "__main__":
    raise SystemExit(main())
