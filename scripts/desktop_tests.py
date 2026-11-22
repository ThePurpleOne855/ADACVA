"""Run unittest in a desktop environment, failing on empty suites or any skips."""

import sys
import unittest


def main(argv=None):
    result = unittest.main(module=None, argv=argv, exit=False).result
    print(f"Desktop checks: {result.testsRun} run, {len(result.skipped)} skipped.")
    return 0 if result.wasSuccessful() and result.testsRun and not result.skipped else 1


if __name__ == "__main__":
    sys.exit(main())
