"""A release never carries a version the PyPI project `cad` published before its transfer.

PyPI never accepts a filename twice, so `scripts/release/unavailable-versions.txt` lists versions no
release of text-to-cad can take. `check-version.sh` and `bump-version.sh` refuse them (Prepare Release
runs the latter), and CONTRIBUTING.md names the same list for people.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

LIST = repo_path("scripts", "release", "unavailable-versions.txt")
RELEASE_FILES = ("bump-version.sh", "check-version.sh", "release-tags.sh", "unavailable-versions.txt")
REFUSAL = (
    "{} is not available: the PyPI project cad published it before the transfer "
    "(scripts/release/unavailable-versions.txt)"
)


def _listed() -> list[str]:
    lines = (line.split("#", 1)[0].strip() for line in LIST.read_text(encoding="utf-8").splitlines())
    return [line for line in lines if line]


def _run(*command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", *command], cwd=cwd, capture_output=True, text=True, timeout=60)


def _repo(root: Path, version: str) -> Path:
    """A repository of its own holding the release scripts, at `version`."""
    scripts = root / "scripts" / "release"
    scripts.mkdir(parents=True)
    for name in RELEASE_FILES:
        shutil.copy2(repo_path("scripts", "release", name), scripts / name)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    for command in (("init", "-q"), ("config", "user.name", "t"), ("config", "user.email", "t@example.invalid"),
                    ("config", "core.hooksPath", str(root / "no-hooks")), ("config", "gc.auto", "0"),
                    ("config", "gc.autoDetach", "false"), ("config", "maintenance.auto", "false"),
                    ("add", "."), ("commit", "-qm", "base")):
        subprocess.run(["git", *command], cwd=root, check=True, capture_output=True)
    return root


class UnavailableVersionsTests(unittest.TestCase):
    def test_the_list_is_the_burned_versions_and_contributing_names_the_same_ones(self) -> None:
        listed = _listed()
        self.assertEqual(21, len(listed))
        self.assertEqual(len(listed), len(set(listed)))
        contributing = repo_path("CONTRIBUTING.md").read_text(encoding="utf-8")
        section = re.search(r"^### Versions a release cannot take\n(.*?)(?=^#{1,3} )", contributing, re.M | re.S)
        self.assertIsNotNone(section, "CONTRIBUTING.md's Releases section names the versions a release cannot take")
        documented = re.findall(r"`(\d+(?:\.\d+)+)`", section[1])
        self.assertEqual(listed, documented, "CONTRIBUTING.md and unavailable-versions.txt list different versions")

    def test_bump_refuses_a_listed_version_and_accepts_0_10_0(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unavailable-versions-") as root:
            repo = _repo(Path(root), "0.8.4")
            for version in ("0.9.0", "1.0.0"):  # 1.0.0 is the listed 1.0 to PyPI
                result = _run("scripts/release/bump-version.sh", version, "--base", "HEAD", "--dry-run", cwd=repo)
                self.assertEqual(1, result.returncode, result.stdout)
                self.assertEqual(REFUSAL.format(version), result.stderr.strip())
            result = _run("scripts/release/bump-version.sh", "0.10.0", "--base", "HEAD", "--dry-run", cwd=repo)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("-> 0.10.0", result.stdout)

    def test_a_bump_that_lands_on_a_listed_version_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unavailable-versions-") as root:
            repo = _repo(Path(root), "0.8.5")  # a patch bump of 0.8.5 is 0.8.6, free; a minor one is 0.9.0
            result = _run("scripts/release/bump-version.sh", "minor", "--base", "HEAD", "--dry-run", cwd=repo)
            self.assertEqual(1, result.returncode)
            self.assertEqual(REFUSAL.format("0.9.0"), result.stderr.strip())
            result = _run("scripts/release/bump-version.sh", "patch", "--base", "HEAD", "--dry-run", cwd=repo)
            self.assertEqual(0, result.returncode, result.stderr)

    def test_check_version_refuses_a_listed_version_and_passes_the_guard_for_0_10_0(self) -> None:
        with tempfile.TemporaryDirectory(prefix="unavailable-versions-") as root:
            repo = _repo(Path(root), "0.9.0")
            result = _run("scripts/release/check-version.sh", cwd=repo)
            self.assertEqual(1, result.returncode)
            self.assertEqual(REFUSAL.format("0.9.0"), result.stderr.strip())
            (repo / "VERSION").write_text("0.10.0\n", encoding="utf-8")
            result = _run("scripts/release/check-version.sh", cwd=repo)
            self.assertIn("Canonical release version is valid: 0.10.0", result.stdout)
            self.assertNotIn("is not available", result.stderr)


if __name__ == "__main__":
    unittest.main()
