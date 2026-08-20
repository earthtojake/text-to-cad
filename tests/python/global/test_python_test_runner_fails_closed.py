"""The Python test runner must fail when it collects no tests.

`packages/cadjs`, `packages/implicitjs`, and `viewer` all exit 1 from
`scripts/run-tests.mjs` when their collector finds nothing. `run_python_unittest`
in `scripts/test/common.sh` is the Python side of the same gate, so a renamed or
emptied test directory must stop CI rather than report a group that never ran.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory


COMMON_SH = REPO_ROOT / "scripts" / "test" / "common.sh"

PASSING_TEST = """\
import unittest


class Passing(unittest.TestCase):
    def test_passes(self):
        self.assertTrue(True)
"""


def run_group(start_dir: Path) -> subprocess.CompletedProcess[str]:
    """Invoke `run_python_unittest` on one directory, as `test-*.sh` would."""
    relative = start_dir.relative_to(REPO_ROOT).as_posix()
    script = (
        "set -euo pipefail\n"
        f'source "{COMMON_SH}"\n'
        f'run_python_unittest "runner gate" "{relative}"\n'
    )
    return subprocess.run(
        ["bash", "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class PythonTestRunnerFailsClosed(unittest.TestCase):
    def test_missing_directory_fails(self):
        with temporary_directory(prefix="runner-gate-missing-") as tmp:
            result = run_group(Path(tmp) / "does-not-exist")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_directory_without_tests_fails(self):
        with temporary_directory(prefix="runner-gate-empty-") as tmp:
            result = run_group(Path(tmp))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("No Python tests found", result.stderr, result.stdout)

    def test_directory_with_tests_passes(self):
        with temporary_directory(prefix="runner-gate-collected-") as tmp:
            (Path(tmp) / "test_collected.py").write_text(PASSING_TEST, encoding="utf-8")
            result = run_group(Path(tmp))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
