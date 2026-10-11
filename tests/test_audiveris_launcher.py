from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ada_piano.score_import.launcher import audiveris_command


class AudiverisLauncherTests(unittest.TestCase):
    def test_native_install_is_preferred(self):
        with patch("ada_piano.score_import.launcher._native", return_value="/opt/audiveris/bin/Audiveris"), \
                patch("ada_piano.score_import.launcher.subprocess.run") as run:
            self.assertEqual(audiveris_command("auto", "/tmp/job"), ["/opt/audiveris/bin/Audiveris"])
            run.assert_not_called()

    def test_flatpak_install_is_detected_and_granted_only_job_folder(self):
        with patch("ada_piano.score_import.launcher._native", return_value=None), \
                patch("ada_piano.score_import.launcher.shutil.which", return_value="/usr/bin/flatpak"), \
                patch("ada_piano.score_import.launcher.subprocess.run", return_value=SimpleNamespace(returncode=0)):
            folder = Path("scores/test import").resolve()
            command = audiveris_command("auto", folder)
            self.assertEqual(command, ["/usr/bin/flatpak", "run", f"--filesystem={folder}", "org.audiveris.audiveris"])

    def test_flatpak_missing_app_has_install_instructions(self):
        with patch("ada_piano.score_import.launcher._native", return_value=None), \
                patch("ada_piano.score_import.launcher.shutil.which", return_value="/usr/bin/flatpak"), \
                patch("ada_piano.score_import.launcher.subprocess.run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, "flatpak install"):
                audiveris_command("auto", "/tmp/job")

    def test_explicit_executable_is_one_argument_and_not_replaced(self):
        with patch("ada_piano.score_import.launcher.shutil.which", return_value="/apps/my audiveris"):
            self.assertEqual(audiveris_command("/apps/my audiveris", "/tmp/job"), ["/apps/my audiveris"])
        with patch("ada_piano.score_import.launcher.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Cannot run"):
                audiveris_command("/missing/launcher", "/tmp/job")

    def test_pdf_selected_as_executable_has_clear_message(self):
        with self.assertRaisesRegex(ValueError, "not the score"):
            audiveris_command("fur elise.pdf", "/tmp/job")
