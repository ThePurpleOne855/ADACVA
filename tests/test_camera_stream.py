"""Camera worker checks without camera hardware or optional vision packages."""

from threading import Event
from time import monotonic, sleep
import unittest
from unittest.mock import MagicMock, patch
import sys

from ada_piano.camera.stream import CameraFrame, CameraWorker, camera_frames


def wait_for(predicate):
    deadline = monotonic() + 2
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError("Timed out waiting for camera worker")
        sleep(0.005)


class CameraWorkerTests(unittest.TestCase):
    def test_latest_frame_only_and_cleanup_on_stop(self):
        ready, released = Event(), Event()
        def source(index, stop):
            self.assertEqual(index, 2)
            try:
                for count in range(50):
                    yield CameraFrame(b"preview", count)
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
        cv2.flip.return_value = frame
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
                patch("ada_piano.camera.stream.monotonic_ns", return_value=1_000_000):
            frames = camera_frames(1, Event())
            preview = next(frames)
            self.assertTrue(preview.ppm.startswith(b"P6\n420 315\n255\n"))
            self.assertEqual(preview.hands, 0)
            next(frames)
            timestamps = [call.args[1] for call in tracker.detect_for_video.call_args_list]
            self.assertEqual(timestamps, [1, 2])
            with self.assertRaisesRegex(RuntimeError, "stopped delivering"):
                next(frames)
        camera.release.assert_called_once()
        tracker_context.__exit__.assert_called_once()

    def test_unavailable_camera_releases_handle(self):
        cv2, mp = MagicMock(), MagicMock()
        cv2.VideoCapture.return_value.isOpened.return_value = False
        with patch.dict(sys.modules, {"cv2": cv2, "mediapipe": mp,
                                     "ada_piano.camera.overlay": MagicMock()}), \
                patch("ada_piano.camera.stream.Path.is_file", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "Cannot open camera"):
                next(camera_frames(0, Event()))
        cv2.VideoCapture.return_value.release.assert_called_once()
