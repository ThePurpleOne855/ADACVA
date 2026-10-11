"""Camera capture runs off the UI thread; only the latest frame is retained."""

from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic_ns

from ada_piano.camera.source import CameraSource, parse_camera_source


@dataclass(frozen=True)
class HandLandmark:
    """MediaPipe normalized image coordinates, independent of GUI objects."""

    x: float
    y: float
    z: float


@dataclass(frozen=True)
class CameraFrame:
    ppm: bytes
    hands: int
    bgr: object = None
    # Host acquisition time just after read(), not sensor exposure time.
    # Same monotonic clock as MIDI timestamps (convert ns to seconds).
    captured_at_ns: int | None = None
    hand_landmarks: tuple[tuple[HandLandmark, ...], ...] = ()


def camera_frames(source: CameraSource, stop: Event):
    source = parse_camera_source(source)
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
            if isinstance(source, str) and "://" in source:
                # Network cameras (phone apps over Wi-Fi): fail within seconds, not minutes.
                camera = cv2.VideoCapture(source, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                                                                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000])
            else:
                camera = cv2.VideoCapture(source)
            if not camera.isOpened():
                if isinstance(source, str) and "://" in source:
                    raise RuntimeError(f"Cannot reach the phone camera at {source}. Open the camera app on the "
                                       "phone, keep it on the same Wi-Fi, and check the address it shows.")
                raise RuntimeError(f"Cannot open camera source {source}. Check permissions or try another source.")
            previous_timestamp = -1
            while not stop.is_set():
                ok, frame = camera.read()
                captured_at_ns = monotonic_ns()
                if not ok:
                    raise RuntimeError(f"Camera source {source} stopped delivering frames. Reconnect it and start again.")
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp = max(previous_timestamp + 1, captured_at_ns // 1_000_000)
                previous_timestamp = timestamp
                result = tracker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp,
                )
                landmarks = tuple(tuple(HandLandmark(point.x, point.y, point.z)
                                        for point in hand) for hand in result.hand_landmarks)
                for hand in result.hand_landmarks:
                    draw_hand(frame, hand)
                # Fit both dimensions, including portrait cameras, into the panel.
                height, width = frame.shape[:2]
                scale = min(420 / width, 315 / height)
                preview = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))))
                preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
                h, w = preview.shape[:2]
                ppm = f"P6\n{w} {h}\n255\n".encode() + preview.tobytes()
                yield CameraFrame(ppm, len(landmarks), frame, captured_at_ns, landmarks)
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

    def start(self, source: CameraSource = 0):
        if self.running:
            raise RuntimeError("Camera is still running or stopping. Wait before restarting.")
        source = parse_camera_source(source)
        self._stop.clear()
        with self._lock:
            self._frame = None
            self._status = "Starting camera…"
        self._thread = Thread(target=self._run, args=(source,), daemon=True)
        self._thread.start()

    def _run(self, source):
        try:
            with closing(self._source(source, self._stop)) as frames:
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
