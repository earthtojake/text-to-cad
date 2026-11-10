"""The Python test runner must fail when it collects no tests.

`packages/core` and `viewer` both exit 1 from
`scripts/run-tests.mjs` when their collector finds nothing. `run_python_unittest`
in `scripts/test/common.sh` is the Python side of the same gate, so a renamed or
emptied test directory must stop CI rather than report a group that never ran.

And a suite whose job exists to run it whole (`PYTHON_TEST_NO_SKIPS`: the blender
suite's on CI) fails when a test of it skips: a job that skipped is one that passed
having checked nothing. A shard (`CAD_TEST_SHARD`) that none of the selected files falls
to is not a run that selected nothing: it passes, saying so.
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


SKIPPING_TEST = """\
import unittest


class Skipping(unittest.TestCase):
    def test_passes(self):
        self.assertTrue(True)

    def test_skips(self):
        self.skipTest("nothing to draw on")
"""


def run_group(start_dir: Path, no_skips: bool = False, shard: str = "",
              narrowed_to: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Invoke `run_python_unittest` on one directory, as `test-*.sh` would: in shard ``shard`` of
    its files when one is named, narrowed to the path ``narrowed_to`` when one is."""
    relative = start_dir.relative_to(REPO_ROOT).as_posix()
    script = (
        "set -euo pipefail\n"
        f'source "{COMMON_SH}"\n'
        + ("export PYTHON_TEST_NO_SKIPS=1\n" if no_skips else "unset PYTHON_TEST_NO_SKIPS\n")
        + f'export CAD_TEST_SHARD="{shard}"\n'
        + (f'TEST_PATHS=("{narrowed_to.relative_to(REPO_ROOT).as_posix()}")\n' if narrowed_to else "")
        + f'run_python_unittest "runner gate" "{relative}"\n'
        + "require_selected_tests\n"
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

    def test_a_skip_passes_a_run_and_fails_one_that_takes_none(self):
        with temporary_directory(prefix="runner-gate-skips-") as tmp:
            (Path(tmp) / "test_skipping.py").write_text(SKIPPING_TEST, encoding="utf-8")
            allowed, refused = run_group(Path(tmp)), run_group(Path(tmp), no_skips=True)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        self.assertIn("OK (skipped=1)", allowed.stderr)
        self.assertEqual(refused.returncode, 1, refused.stdout + refused.stderr)
        self.assertIn("1 test skipped in a run that takes none (--no-skips)", refused.stderr)
        self.assertIn("FAILED (skipped=1)", refused.stderr)

    def test_a_narrowed_run_whose_files_all_fall_to_another_shard_passes_saying_so(self):
        # The selection is counted before the shard is taken: the file was selected, and the
        # other shard runs it.
        with temporary_directory(prefix="runner-gate-shard-") as tmp:
            (Path(tmp) / "test_collected.py").write_text(PASSING_TEST, encoding="utf-8")
            (Path(tmp) / "test_other.py").write_text(PASSING_TEST, encoding="utf-8")
            first = run_group(Path(tmp), shard="1/2", narrowed_to=Path(tmp) / "test_collected.py")
            second = run_group(Path(tmp), shard="2/2", narrowed_to=Path(tmp) / "test_collected.py")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertIn("shard 1/2: 1 of the 1 files given\n", first.stderr)
        self.assertIn("Ran 1 test", first.stderr)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("shard 2/2: none of the 1 files given is this shard's; nothing to run (OK)", second.stderr)
        self.assertNotIn("No test file at or under", second.stderr)


if __name__ == "__main__":
    unittest.main()
