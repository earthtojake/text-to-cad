"""The PR version guard distinguishes inherited releases from branch changes."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path


class PrVersionGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="pr-version-guard-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Version guard test")
        self.git("config", "user.email", "version-guard@example.invalid")
        self.git("config", "core.hooksPath", str(self.root / "no-hooks"))
        self.write_version("0.5.0")
        self.commit("Initial release")
        self.old_base = self.git("rev-parse", "HEAD").strip()
        self.git("switch", "-c", "feature")
        (self.root / "README.md").write_text("Feature work\n", encoding="utf-8")
        self.commit("Feature work")
        self.git("switch", "main")
        self.write_version("0.5.1")
        self.commit("Canonical release")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("switch", "feature")

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=self.root, text=True, stderr=subprocess.DEVNULL,
        )

    def write_version(self, value: str) -> None:
        (self.root / "VERSION").write_text(value + "\n", encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", ".")
        self.git("commit", "-m", message)

    def check(self, branch: str = "feature", base: str = "main") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(repo_path("scripts/release/check-pr-version.sh")),
             base, branch, self.git("rev-parse", "HEAD").strip()],
            cwd=self.root, text=True, capture_output=True, check=False,
        )

    def test_inherited_main_release_is_not_a_pr_version_bump(self) -> None:
        self.git("merge", "--no-edit", "main")
        self.assertTrue(self.git("diff", self.old_base, "HEAD", "--", "VERSION"))
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_older_feature_without_a_version_edit_is_allowed(self) -> None:
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_normal_branch_cannot_introduce_a_version_change(self) -> None:
        self.git("merge", "--no-edit", "main")
        self.write_version("0.5.2")
        self.commit("Unapproved bump")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not release/*", result.stderr)

    def test_release_branch_can_introduce_a_version_change(self) -> None:
        self.git("merge", "--no-edit", "main")
        self.write_version("0.5.2")
        self.commit("Release bump")
        result = self.check("release/0.5.2")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_target_history_fails_closed(self) -> None:
        self.assertNotEqual(self.check(base="missing").returncode, 0)
