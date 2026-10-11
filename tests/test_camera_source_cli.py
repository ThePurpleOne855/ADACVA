"""Source plumbing checks without OpenCV, MediaPipe or camera hardware."""

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from ada_piano.camera import check_camera
from ada_piano.cli import main


class CameraCliTests(unittest.TestCase):
    def test_cli_sources_and_index_alias(self):
        for arguments, expected in [([], 0), (["--source", "2"], 2),
                                     (["--source", "/dev/video2"], "/dev/video2"),
                                     (["--source", "https://example.invalid/live"], "https://example.invalid/live"),
                                     (["--index", "1"], 1)]:
            with self.subTest(arguments=arguments), patch("ada_piano.camera.check_camera", return_value=3) as check, \
                    redirect_stdout(StringIO()):
                self.assertEqual(main(["camera", *arguments, "--seconds", "10", "--preview"]), 0)
                check.assert_called_once_with(expected, 10.0, True)

    def test_cli_rejects_conflicting_source_options(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            main(["camera", "--source", "/dev/video2", "--index", "0"])
        self.assertEqual(error.exception.code, 2)

    def test_cli_reports_bad_source_without_opening_camera(self):
        with patch("ada_piano.camera.check_camera") as check, redirect_stderr(StringIO()), \
                self.assertRaises(SystemExit):
            main(["camera", "--source", ""])
        check.assert_not_called()

    def test_capture_check_forwards_source_and_cleans_up(self):
        for requested, expected in [(0, 0), ("2", 2), ("/dev/video2", "/dev/video2"),
                                    ("https://example.invalid/live", "https://example.invalid/live")]:
            with self.subTest(source=requested):
                cv2 = MagicMock()
                cv2.VideoCapture.return_value.read.return_value = (True, object())
                with patch.dict(sys.modules, {"cv2": cv2}), \
                        patch("ada_piano.camera.monotonic", side_effect=[0, 0, 2]):
                    self.assertEqual(check_camera(requested, 1, preview=True), 1)
                cv2.VideoCapture.assert_called_once_with(expected)
                cv2.flip.assert_not_called()
                cv2.VideoCapture.return_value.release.assert_called_once()
                cv2.destroyAllWindows.assert_called_once()

    def test_capture_check_names_failed_source(self):
        cv2 = MagicMock()
        cv2.VideoCapture.return_value.isOpened.return_value = False
        with patch.dict(sys.modules, {"cv2": cv2}), \
                self.assertRaisesRegex(RuntimeError, "Cannot open camera source /dev/video2"):
            check_camera("/dev/video2")
        cv2.VideoCapture.return_value.release.assert_called_once()

    def test_standalone_tracker_passes_source_and_closes(self):
        from ada_piano.camera.hand_tracker import main as track
        cv2 = MagicMock()
        cv2.waitKey.return_value = ord("q")
        frames = MagicMock()
        frames.__iter__.return_value = iter([SimpleNamespace(bgr=object())])
        with patch.dict(sys.modules, {"cv2": cv2}), \
                patch("ada_piano.camera.stream.camera_frames", return_value=frames) as capture:
            track("/dev/video2")
        self.assertEqual(capture.call_args.args[0], "/dev/video2")
        frames.close.assert_called_once()
        cv2.destroyAllWindows.assert_called_once()


try:
    from ada_piano.camera.gui import CameraPanel
except ImportError:
    CameraPanel = None


@unittest.skipIf(CameraPanel is None, "Tkinter is not installed")
class CameraPanelInputTests(unittest.TestCase):
    """Exercise the callback without requiring a Tk root/display."""

    def test_generic_source_start_callback(self):
        for text, expected in [("0", 0), ("2", 2), ("/dev/video2", "/dev/video2")]:
            with self.subTest(source=text):
                panel = SimpleNamespace(source=MagicMock(), controller=MagicMock(), status=MagicMock(),
                                        _choices={}, _clear_preview=MagicMock())
                panel.source.get.return_value = text
                CameraPanel.start(panel)
                panel.controller.start.assert_called_once_with(expected)
                self.assertIsNone(panel._notice)

    def test_invalid_source_does_not_start_worker(self):
        panel = SimpleNamespace(source=MagicMock(), controller=MagicMock(), status=MagicMock(), _choices={})
        panel.source.get.return_value = ""
        CameraPanel.start(panel)
        panel.controller.start.assert_not_called()
        self.assertIn("cannot be empty", panel._notice)
