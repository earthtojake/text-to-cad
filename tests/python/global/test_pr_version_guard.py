"""A pull request releases when it changes VERSION; the guard decides when it may.

Run on the pull request's merge commit, as Version Check runs it: the first parent is the
target branch as it is now, so a release the branch inherited is not one it makes.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

REPOSITORY = "owner/repo"


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
        self.git("tag", "v0.5.0")
        self.git("switch", "-c", "feature")
        (self.root / "README.md").write_text("Feature work\n", encoding="utf-8")
        self.commit("Feature work")
        self.git("switch", "main")

    def git(self, *args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=self.root, text=True, stderr=subprocess.DEVNULL,
        )

    def write_version(self, value: str) -> None:
        (self.root / "VERSION").write_text(value + "\n", encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", ".")
        self.git("commit", "-m", message)

    def release_on_main(self, version: str) -> None:
        self.git("switch", "main")
        self.write_version(version)
        self.commit(f"Release {version}")
        self.git("tag", f"v{version}")

    def check(self, head_repo: str = REPOSITORY) -> subprocess.CompletedProcess[str]:
        """The guard on the merge commit GitHub would test: main with the branch merged in."""
        self.git("switch", "--detach", "main")
        self.git("merge", "--no-ff", "--no-edit", "feature")
        return subprocess.run(
            ["bash", str(repo_path("scripts/release/check-pr-version.sh")), head_repo],
            cwd=self.root, text=True, capture_output=True, check=False,
            env={**os.environ, "GITHUB_REPOSITORY": REPOSITORY, "PR_NUMBER": "7", "BASE_REF": "main",
                 "GITHUB_OUTPUT": str(self.root / "output")},
        )

    def output(self) -> str:
        path = self.root / "output"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def bump_feature(self, version: str) -> None:
        self.git("switch", "feature")
        self.write_version(version)
        self.commit(f"Bump to {version}")

    def test_a_branch_that_leaves_version_alone_releases_nothing(self) -> None:
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("releases nothing", result.stdout)
        self.assertEqual(self.output(), "")

    def test_a_release_the_branch_inherited_is_not_one_it_makes(self) -> None:
        self.release_on_main("0.5.1")
        self.git("switch", "feature")
        self.git("merge", "--no-edit", "main")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("releases nothing", result.stdout)

    def test_a_branch_of_this_repository_may_release(self) -> None:
        self.bump_feature("0.5.1")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        # The next step holds the merge until this version is on PyPI.
        self.assertEqual(self.output(), "version=0.5.1\n")
        self.assertIn("releases 0.5.1", result.stdout)
        self.assertIn("gh workflow run release-publish.yml --ref main -f pr=7", result.stdout)

    def test_a_fork_may_not_release(self) -> None:
        self.bump_feature("0.5.1")
        result = self.check(head_repo="someone/fork")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fork", result.stderr)

    def test_a_version_behind_the_target_branch_is_refused(self) -> None:
        self.bump_feature("0.4.9")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not past 0.5.0", result.stderr)

    def test_a_bump_another_pull_request_released_first_releases_nothing(self) -> None:
        # Both bumped to 0.5.1 and the other merged first: the merge takes the identical
        # line from both sides, so this one no longer changes VERSION.
        self.bump_feature("0.5.1")
        self.release_on_main("0.5.1")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("releases nothing", result.stdout)

    def test_a_release_must_pass_the_latest_tag(self) -> None:
        self.git("tag", "v0.6.0")
        self.bump_feature("0.5.1")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("latest release, v0.6.0", result.stderr)

    def test_it_refuses_anything_but_a_merge_commit(self) -> None:
        result = subprocess.run(
            ["bash", str(repo_path("scripts/release/check-pr-version.sh")), REPOSITORY],
            cwd=self.root, text=True, capture_output=True, check=False,
            env={**os.environ, "GITHUB_REPOSITORY": REPOSITORY},
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
