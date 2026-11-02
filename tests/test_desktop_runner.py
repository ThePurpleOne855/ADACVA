import contextlib
import io
import unittest
from unittest.mock import patch

from scripts.desktop_tests import main


class DesktopRunnerTests(unittest.TestCase):
    def test_exit_status_requires_executed_successful_tests(self):
        cases = {
            "passed": (unittest.FunctionTestCase(lambda: None), 0),
            "skipped": (unittest.FunctionTestCase(
                lambda: self.skipTest("Desktop unavailable")), 1),
            "failed": (unittest.FunctionTestCase(lambda: self.fail("broken")), 1),
            "empty": (unittest.TestSuite(), 1),
        }
        for name, (suite, status) in cases.items():
            with self.subTest(name=name), contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                # Use unittest's real loader/runner, including how it records skips.
                with patch("unittest.defaultTestLoader.loadTestsFromNames", return_value=suite):
                    self.assertEqual(main(["desktop_tests", "fixture"]), status)
