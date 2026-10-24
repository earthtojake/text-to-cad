"""The viewer backend's suite must actually run.

This repo has lost a cross-language mirror to a deleted check before (the viewer scanner's
package-path constants drifted silently once nothing compared them), and the viewer backend's
own suite once ran in no configuration at all. This pins that the runner still reaches it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class TheViewerSuiteActuallyRuns(unittest.TestCase):
    """The wiring, not the check.

    The viewer backend suite is the executable specification of the backend, and
    for one release cycle it ran in ZERO configurations of this repo: the JS
    runner stopped covering the server, the Python runner discovered only what it
    was pointed at, and the workflow never named it. It lives under the cadgen
    package suite now, so the ordinary runner reaches it -- this pins that the
    directory the runner walks still contains it.
    """

    def test_the_viewer_suite_is_under_the_cadgen_package_tests(self) -> None:
        suite = ROOT / "tests/python/packages/cadgen/viewer"
        tests = sorted(p.name for p in suite.glob("test_*.py"))
        self.assertIn("test_launcher.py", tests)
        self.assertIn("test_module_boundaries.py", tests)
        runner = (ROOT / "scripts/test/test-python.sh").read_text(encoding="utf-8")
        self.assertIn(
            '"tests/python/packages/cadgen"',
            runner,
            "test-python.sh must run the cadgen package suite, which is where the viewer suite lives",
        )


if __name__ == "__main__":
    unittest.main()
