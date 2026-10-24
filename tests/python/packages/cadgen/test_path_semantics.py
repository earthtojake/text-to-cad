"""``~`` expansion across cadgen's path arguments.

USER RULING: every cadgen CLI/function path argument takes NATIVE semantics —
relative resolves against the process working directory, absolute works
anywhere, ``~`` expands. The relative/absolute halves are pinned where each
door is tested; what is easy to regress is the tilde, because a bare
``Path(text)`` looks correct and only fails against a real ``~`` argument.

These drive the RESOLUTION helpers directly rather than the full commands: the
thing under test is one line of path handling in each.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

from cadgen.cli import doctor  # noqa: E402


class TildeExpansion(unittest.TestCase):
    def setUp(self) -> None:
        tempdir = temporary_directory(prefix="cadpath-")
        self.addCleanup(tempdir.cleanup)
        self.home = Path(tempdir.name).resolve()
        self.cwd = self.home / "cwd"
        self.cwd.mkdir(parents=True, exist_ok=True)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home)}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Path.expanduser reads HOME on POSIX and USERPROFILE on Windows.
        if os.name == "nt":  # pragma: no cover - parity, not a second code path
            nt_patcher = mock.patch.dict(
                os.environ, {"USERPROFILE": str(self.home)}, clear=False
            )
            nt_patcher.start()
            self.addCleanup(nt_patcher.stop)

    def test_doctor_target_expands_a_tilde(self) -> None:
        skill_dir = self.home / "skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill = skill_dir / "SKILL.md"
        skill.write_text("---\nname: skill\n---\n", encoding="utf-8")
        self.assertEqual(doctor._resolve_skill("~/skill"), Path("~/skill").expanduser() / "SKILL.md")
        self.assertEqual(doctor._resolve_skill("~/skill/SKILL.md"), skill)

    def test_doctor_target_reports_nothing_when_no_skill_exists(self) -> None:
        empty = self.home / "empty"
        empty.mkdir(parents=True, exist_ok=True)
        self.assertIsNone(doctor._resolve_skill("~/empty"))


if __name__ == "__main__":
    unittest.main()
