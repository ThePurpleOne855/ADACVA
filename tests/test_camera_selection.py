from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ada_piano.camera.controller import CameraController
from ada_piano.camera.devices import camera_choices, has_camera


class DelayedWorker:
    """Stopping remains asynchronous, like a real capture read."""
    def __init__(self):
        self.running = False
        self.started = []
        self.stops = 0

    def start(self, index):
        if self.running:
            raise AssertionError("Previous device has not been released")
        self.started.append(index)
        self.running = True

    def stop(self):
        self.stops += 1

    def snapshot(self):
        return None, "Tracking 1 hand(s)."

    def close(self):
        self.running = False


class CameraSelectionTests(unittest.TestCase):
    def test_switch_to_generic_source_waits_for_release(self):
        worker = DelayedWorker()
        controller = CameraController(worker)
        controller.start("0")
        controller.start("/dev/video2")
        self.assertEqual(worker.started, [0])
        self.assertIn("/dev/video2", controller.snapshot()[1])
        worker.running = False
        controller.snapshot()
        self.assertEqual(worker.started, [0, "/dev/video2"])

    def test_switch_waits_for_release_and_keeps_latest_selection(self):
        worker = DelayedWorker()
        controller = CameraController(worker)
        controller.start(0)
        controller.start(1)
        self.assertIn("waiting", controller.snapshot()[1])
        controller.start(2)
        self.assertEqual(worker.started, [0])
        worker.running = False
        self.assertIn("Camera 2", controller.snapshot()[1])
        self.assertEqual(worker.started, [0, 2])
        controller.start(2)
        self.assertIsNone(controller.pending)
        self.assertEqual(worker.started, [0, 2])

    def test_stop_and_close_cancel_pending_switch(self):
        for action in ("stop", "close"):
            with self.subTest(action=action):
                worker = DelayedWorker()
                controller = CameraController(worker)
                controller.start(0)
                controller.start(1)
                getattr(controller, action)()
                worker.running = False
                controller.snapshot()
                self.assertEqual(worker.started, [0])

    def test_failed_switch_does_not_retry_forever(self):
        worker = DelayedWorker()
        controller = CameraController(worker)
        controller.start(0)
        controller.start(1)
        worker.running = False
        def fail(index):
            raise RuntimeError("Device unavailable")
        worker.start = fail
        with self.assertRaisesRegex(RuntimeError, "Device unavailable"):
            controller.snapshot()
        self.assertIsNone(controller.pending)

    def test_device_names_and_nonconsecutive_indices(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            for name, label in (("video0", "Integrated Camera"), ("video4", "USB Camera")):
                (root / name).mkdir()
                (root / name / "name").write_text(label)
            self.assertEqual(camera_choices(root), {
                "Integrated Camera (camera 0)": 0, "USB Camera (camera 4)": 4,
            })

    def test_numbered_fallback_when_no_devices_are_listed(self):
        with TemporaryDirectory() as root:
            choices = camera_choices(Path(root))
            self.assertEqual(choices["Camera 0"], 0)
            self.assertEqual(choices["Camera 1"], 1)

    def test_has_camera_detects_capture_nodes(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            self.assertFalse(has_camera(root, {}))
            (root / "video2").mkdir()
            (root / "video2" / "name").write_text("Brio 100")
            (root / "video2" / "index").write_text("0")
            self.assertTrue(has_camera(root, {}))

    def test_has_camera_ignores_metadata_nodes(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            (root / "video3").mkdir()
            (root / "video3" / "name").write_text("Brio 100")
            (root / "video3" / "index").write_text("1")
            self.assertFalse(has_camera(root, {}))

    def test_has_camera_honors_configured_source(self):
        with TemporaryDirectory() as root:
            self.assertTrue(has_camera(Path(root), {"ADA_CAMERA": "2"}))
            self.assertFalse(has_camera(Path(root), {"ADA_CAMERA": "-1"}))
