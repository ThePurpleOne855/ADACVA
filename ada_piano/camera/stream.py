"""Camera capture runs off the UI thread; only the latest frame is retained."""

from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic_ns


@dataclass(frozen=True)
class CameraFrame:
    ppm: bytes
    hands: int
    bgr: object = None


def camera_frames(index, stop):
    try:
        import cv2
        import mediapipe as mp
    except ImportError as exc:
        raise RuntimeError("Install camera support: uv sync --extra camera") from exc
    from ada_piano.camera.overlay import draw_hand

    model = Path(__file__).resolve().parents[2] / "hand_landmarker.task"
    if not model.is_file():
        raise FileNotFoundError(f"Hand tracking model not found: {model}")
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2,
    )
    camera = None
    try:
        with mp.tasks.vision.HandLandmarker.create_from_options(options) as tracker:
            if stop.is_set():
                return
            camera = cv2.VideoCapture(index)
            if not camera.isOpened():
                raise RuntimeError(f"Cannot open camera {index}. Check permissions or try another index.")
            previous_timestamp = -1
            while not stop.is_set():
                ok, frame = camera.read()
                if not ok:
                    raise RuntimeError("Camera stopped delivering frames. Reconnect it and start again.")
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp = max(previous_timestamp + 1, monotonic_ns() // 1_000_000)
                previous_timestamp = timestamp
                result = tracker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp,
                )
                for hand in result.hand_landmarks:
                    draw_hand(frame, hand)
                # Fit both dimensions, including portrait cameras, into the panel.
                height, width = frame.shape[:2]
                scale = min(420 / width, 315 / height)
                preview = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))
                preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
                h, w = preview.shape[:2]
                ppm = f"P6\n{w} {h}\n255\n".encode() + preview.tobytes()
                yield CameraFrame(ppm, len(result.hand_landmarks), frame)
    finally:
        if camera is not None:
            camera.release()


class CameraWorker:
    def __init__(self, source=camera_frames):
        self._source = source
        self._stop = Event()
        self._lock = Lock()
        self._thread = None
        self._frame = None
        self._status = "Camera off. MIDI works independently."

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, index=0):
        if self.running:
            raise RuntimeError("Camera is still running or stopping. Wait before restarting.")
        self._stop.clear()
        with self._lock:
            self._frame = None
            self._status = "Starting camera…"
        self._thread = Thread(target=self._run, args=(index,), daemon=True)
        self._thread.start()

    def _run(self, index):
        try:
            with closing(self._source(index, self._stop)) as frames:
                for frame in frames:
                    if self._stop.is_set():
                        break
                    with self._lock:
                        self._frame = frame
                        self._status = (f"Tracking {frame.hands} hand(s)." if frame.hands else
                                        "Camera live. No hands detected.")
            with self._lock:
                self._frame = None
                self._status = "Camera stopped."
        except Exception as exc:
            with self._lock:
                self._frame = None
                self._status = f"Camera error: {exc}"

    def snapshot(self):
        with self._lock:
            frame, self._frame = self._frame, None
            return frame, self._status

    def stop(self):
        self._stop.set()
        with self._lock:
            self._frame = None
            self._status = "Stopping camera…" if self.running else "Camera stopped."

    def close(self):
        self.stop()
        if self._thread is not None:
            self._thread.join(timeout=0.2)
