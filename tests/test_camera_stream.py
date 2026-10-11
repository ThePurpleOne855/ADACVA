"""Camera worker checks without camera hardware or optional vision packages."""

from threading import Event, get_ident
from types import SimpleNamespace
from time import monotonic, sleep
import unittest
from unittest.mock import MagicMock, patch
import sys

from ada_piano.camera.stream import CameraFrame, CameraWorker, HandLandmark, camera_frames
from ada_piano.camera.source import parse_camera_source


class CameraSourceTests(unittest.TestCase):
    def test_numeric_sources(self):
        for source, expected in [(0, 0), (2, 2), ("0", 0), ("2", 2), (" 02 ", 2), ("+1", 1)]:
            with self.subTest(source=source):
                actual = parse_camera_source(source)
                self.assertEqual(actual, expected)
                self.assertIsInstance(actual, int)

    def test_string_sources(self):
        for source in ["/dev/video2", "https://example.invalid/camera", "rtsp://example.invalid/live", "video.mp4"]:
            with self.subTest(source=source):
                self.assertEqual(parse_camera_source(source), source)

    def test_invalid_sources(self):
        for source in ["", "   ", -1, "-2", True, None, 2.5]:
            with self.subTest(source=source), self.assertRaises(ValueError):
                parse_camera_source(source)


def wait_for(predicate):
    deadline = monotonic() + 2
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("Timed out waiting for camera worker")
        sleep(0.005)


class CameraWorkerTests(unittest.TestCase):
    def test_source_forwarding_and_capture_thread(self):
        caller = get_ident()
        for requested, expected in [(0, 0), ("2", 2), ("/dev/video2", "/dev/video2"),
                                    ("https://example.invalid/live", "https://example.invalid/live")]:
            with self.subTest(source=requested):
                observed, ready = [], Event()
                def generator(source, stop):
                    observed.append((source, get_ident()))
                    yield CameraFrame(b"preview", 0)
                    ready.set()
                    stop.wait(2)
                worker = CameraWorker(generator)
                try:
                    worker.start(requested)
                    self.assertTrue(ready.wait(2))
                    self.assertEqual(observed[0][0], expected)
                    self.assertNotEqual(observed[0][1], caller)
                finally:
                    worker.close()

    def test_invalid_source_does_not_start_thread(self):
        generator = MagicMock()
        worker = CameraWorker(generator)
        with self.assertRaises(ValueError):
            worker.start("")
        self.assertFalse(worker.running)
        generator.assert_not_called()

    def test_latest_frame_only_and_cleanup_on_stop(self):
        ready, released = Event(), Event()
        def source(index, stop):
            self.assertEqual(index, 2)
            try:
                for count in range(50):
                    yield CameraFrame(b"preview", count, captured_at_ns=count * 1_000_000,
                                      hand_landmarks=((HandLandmark(0.1, 0.2, 0.3),),))
                ready.set()
                stop.wait(2)
            finally:
                released.set()
        worker = CameraWorker(source)
        self.addCleanup(worker.close)
        worker.start(2)
        self.assertTrue(ready.wait(2))
        frame, status = worker.snapshot()
        self.assertEqual(frame.hands, 49)
        self.assertEqual(frame.captured_at_ns, 49_000_000)
        self.assertEqual(frame.hand_landmarks, ((HandLandmark(0.1, 0.2, 0.3),),))
        self.assertIn("49", status)
        self.assertIsNone(worker.snapshot()[0])
        with self.assertRaises(RuntimeError):
            worker.start()
        worker.stop()
        wait_for(lambda: not worker.running)
        self.assertTrue(released.is_set())
        self.assertEqual(worker.snapshot(), (None, "Camera stopped."))

    def test_device_failure_clears_frame_and_allows_restart(self):
        def source(index, stop):
            yield CameraFrame(b"preview", 1)
            raise RuntimeError("Camera unplugged")
        worker = CameraWorker(source)
        self.addCleanup(worker.close)
        for _ in range(2):
            worker.start()
            wait_for(lambda: not worker.running)
            frame, status = worker.snapshot()
            self.assertIsNone(frame)
            self.assertIn("Camera unplugged", status)

    def test_missing_dependency_is_reported(self):
        def source(index, stop):
            raise ImportError("Missing camera dependency")
        worker = CameraWorker(source)
        self.addCleanup(worker.close)
        worker.start()
        wait_for(lambda: not worker.running)
        self.assertIn("Missing camera dependency", worker.snapshot()[1])


class CameraCaptureTests(unittest.TestCase):
    def test_capture_encodes_preview_and_releases_on_disconnect(self):
        cv2, mp, overlay = MagicMock(), MagicMock(), MagicMock()
        frame = MagicMock()
        frame.shape = (315, 420, 3)
        frame.tobytes.return_value = bytes(315 * 420 * 3)
        cv2.resize.return_value = frame
        cv2.cvtColor.return_value = frame
        camera = cv2.VideoCapture.return_value
        camera.isOpened.return_value = True
        camera.read.side_effect = [(True, frame), (True, frame), (False, None)]
        tracker_context = mp.tasks.vision.HandLandmarker.create_from_options.return_value
        tracker = tracker_context.__enter__.return_value
        tracker.detect_for_video.return_value.hand_landmarks = []
        with patch.dict(sys.modules, {"cv2": cv2, "mediapipe": mp,
                                     "ada_piano.camera.overlay": overlay}), \
                patch("ada_piano.camera.stream.Path.is_file", return_value=True), \
                patch("ada_piano.camera.stream.monotonic_ns", side_effect=[1_000_000, 1_500_000, 2_000_000]):
            frames = camera_frames("1", Event())
            preview = next(frames)
            self.assertTrue(preview.ppm.startswith(b"P6\n420 315\n255\n"))
            self.assertEqual(preview.hands, 0)
            second = next(frames)
            self.assertEqual([preview.captured_at_ns, second.captured_at_ns], [1_000_000, 1_500_000])
            self.assertGreater(second.captured_at_ns, preview.captured_at_ns)
            timestamps = [call.args[1] for call in tracker.detect_for_video.call_args_list]
            self.assertEqual(timestamps, [1, 2])
            with self.assertRaisesRegex(RuntimeError, "stopped delivering"):
                next(frames)
        camera.release.assert_called_once()
        cv2.VideoCapture.assert_called_once_with(1)
        cv2.flip.assert_not_called()
        tracker_context.__exit__.assert_called_once()

    def test_unavailable_camera_releases_handle(self):
        cv2, mp = MagicMock(), MagicMock()
        cv2.VideoCapture.return_value.isOpened.return_value = False
        with patch.dict(sys.modules, {"cv2": cv2, "mediapipe": mp,
                                     "ada_piano.camera.overlay": MagicMock()}), \
                patch("ada_piano.camera.stream.Path.is_file", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "Cannot open camera source /dev/video2"):
                next(camera_frames("/dev/video2", Event()))
        cv2.VideoCapture.assert_called_once_with("/dev/video2")
        cv2.VideoCapture.return_value.release.assert_called_once()

    def test_landmarks_and_timestamp_precede_inference_and_overlay(self):
        cv2, mp, overlay = MagicMock(), MagicMock(), MagicMock()
        image = MagicMock()
        image.shape = (315, 420, 3)
        image.tobytes.return_value = b"pixels"
        cv2.resize.return_value = image
        cv2.cvtColor.return_value = image
        camera = cv2.VideoCapture.return_value
        timeline = []
        def read():
            timeline.append("read")
            return True, image
        camera.read.side_effect = read
        point = SimpleNamespace(x=0.1, y=0.2, z=-0.3)
        tracker = mp.tasks.vision.HandLandmarker.create_from_options.return_value.__enter__.return_value
        def detect(*args):
            timeline.append("inference")
            return SimpleNamespace(hand_landmarks=[[point]])
        tracker.detect_for_video.side_effect = detect
        def clock():
            timeline.append("acquisition")
            return 123_456_789
        with patch.dict(sys.modules, {"cv2": cv2, "mediapipe": mp,
                                     "ada_piano.camera.overlay": overlay}), \
                patch("ada_piano.camera.stream.Path.is_file", return_value=True), \
                patch("ada_piano.camera.stream.monotonic_ns", side_effect=clock):
            frames = camera_frames(0, Event())
            try:
                captured = next(frames)
            finally:
                frames.close()
        self.assertEqual(timeline, ["read", "acquisition", "inference"])
        self.assertEqual(captured.captured_at_ns, 123_456_789)
        self.assertEqual(captured.hands, 1)
        self.assertEqual(captured.hand_landmarks, ((HandLandmark(0.1, 0.2, -0.3),),))
        point.x = 0.9
        self.assertEqual(captured.hand_landmarks[0][0].x, 0.1)
        cv2.flip.assert_not_called()
        cv2.cvtColor.assert_any_call(image, cv2.COLOR_BGR2RGB)
        overlay.draw_hand.assert_called_once_with(image, [point])
        self.assertEqual(tracker.detect_for_video.call_args.args[1], 123)
        camera.release.assert_called_once()
