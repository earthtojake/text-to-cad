"""A published skill must not run against a cadgen it was not published against.

`scripts/release/pin-cadgen-requirements.sh` writes `cadgen==<release>` into every
skill's requirements.txt at publish, but nothing makes pip re-resolve that on a machine
where some other cadgen is already installed. The skill then runs on an untested runtime
and fails somewhere far from the cause. `enforce_requirements_pin` is the entrypoint
check that turns it into one line naming both versions.

Its silence matters as much as its failure: a development checkout is deliberately
unpinned (`cadgen[snapshot]`) so the editable install satisfies it, and the guard runs on
EVERY skill invocation. A false positive there would break the repo's own workflows.

The companion policy test that keeps the guard wired into the shims is
tests/python/global/test_shim_pin_guard.py.
"""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from cadgen import __version__ as INSTALLED
from cadgen.cli import enforce_requirements_pin


class RequirementsPinGuard(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _requirements(self, body: str) -> Path:
        path = self.root / "requirements.txt"
        path.write_text(body, encoding="utf-8")
        return path

    def assertSilent(self, path: Path) -> None:
        """The guard returns without writing anything — the overwhelmingly common case."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            enforce_requirements_pin(path)
        self.assertEqual(stderr.getvalue(), "")

    # --- the cases that must stay silent ------------------------------------------
    def test_missing_file_is_silent(self) -> None:
        # Not every skill ships a manifest; absent means nothing claims a version.
        self.assertSilent(self.root / "requirements.txt")

    def test_unreadable_path_is_silent(self) -> None:
        # A directory where a file was expected must not take down the command.
        (self.root / "requirements.txt").mkdir()
        self.assertSilent(self.root / "requirements.txt")

    def test_unpinned_distribution_is_silent(self) -> None:
        # Only the `==` form is a pin; a bare line is not one and is not enforced here
        # (check-version.sh is what rejects it in the repo).
        self.assertSilent(self._requirements("cadgen\n"))

    def test_unpinned_with_extras_is_silent(self) -> None:
        self.assertSilent(self._requirements("cadgen[snapshot]\n"))

    def test_matching_pin_is_silent(self) -> None:
        self.assertSilent(self._requirements(f"cadgen=={INSTALLED}\n"))

    def test_matching_pin_with_extras_is_silent(self) -> None:
        self.assertSilent(self._requirements(f"cadgen[snapshot]=={INSTALLED}\n"))

    def test_other_distributions_are_ignored(self) -> None:
        # A pinned NEIGHBOUR is not a cadgen pin. Guards against a loose prefix match.
        self.assertSilent(self._requirements("playwright==1.0.0\ncadgen-extras==0.0.1\n"))

    def test_comment_is_not_a_pin(self) -> None:
        self.assertSilent(self._requirements("# cadgen==0.0.0\ncadgen\n"))

    # --- the case it exists for -----------------------------------------------------
    def test_mismatched_pin_exits_3_and_names_both_versions(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
            enforce_requirements_pin(self._requirements("cadgen==0.0.0\n"))
        # 3 is the shims' existing "cadgen is not installed" code: same fix, same exit.
        self.assertEqual(caught.exception.code, 3)
        message = stderr.getvalue()
        self.assertIn("cadgen==0.0.0", message)
        self.assertIn(INSTALLED, message)
        self.assertIn("pip install -r requirements.txt", message)

    def test_mismatch_detected_with_extras_and_surrounding_lines(self) -> None:
        body = "# pinned at publish\nplaywright\ncadgen[snapshot]==0.0.0\nezdxf\n"
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            enforce_requirements_pin(self._requirements(body))

    def test_accepts_a_string_path(self) -> None:
        # Shims pass a Path, but nothing in the signature demands one.
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            enforce_requirements_pin(str(self._requirements("cadgen==0.0.0\n")))


if __name__ == "__main__":
    unittest.main()
