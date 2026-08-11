"""The canonical version file moved from `plugins/cad/VERSION` to `VERSION`.

`scripts/release/bump-version.sh --check-incremented-from REF` reads the
canonical version *at a git ref*, and the refs it is pointed at are frequently
older than the move: `origin/main` until the first new-layout release lands, and
release tags forever after that, since tags are immutable.

Without a fallback the script fails with git's exit 128 ("path 'VERSION' exists
on disk, but not in <ref>") rather than a version comparison, which takes the
whole `Release` workflow down at its first gate. These tests pin the fallback.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[3]
BUMP_SCRIPT = REPO_ROOT / "scripts" / "release" / "bump-version.sh"

VERSION_PATH = "VERSION"
LEGACY_VERSION_PATH = "plugins/cad/VERSION"


def git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def init_repo(root: Path) -> None:
    """Init a repo with the script installed at its real repo-relative path.

    `bump-version.sh` resolves its own repo root from `${BASH_SOURCE[0]}`, not
    from the working directory, so the fixture only exercises the fixture repo
    when the script is invoked from inside it.
    """
    git("init", "--quiet", cwd=root)
    git("config", "user.email", "test@example.com", cwd=root)
    git("config", "user.name", "test", cwd=root)

    script_copy = root / "scripts" / "release" / "bump-version.sh"
    script_copy.parent.mkdir(parents=True, exist_ok=True)
    script_copy.write_bytes(BUMP_SCRIPT.read_bytes())
    script_copy.chmod(0o755)


def build_repo(root: Path, base_version_path: str, base_version: str) -> None:
    """Create a repo whose base commit holds `base_version` at `base_version_path`."""
    init_repo(root)

    base_file = root / base_version_path
    base_file.parent.mkdir(parents=True, exist_ok=True)
    base_file.write_text(f"{base_version}\n", encoding="utf-8")
    git("add", "-A", cwd=root)
    git("commit", "--quiet", "-m", "base layout", cwd=root)
    git("tag", base_version, cwd=root)


def run_check(root: Path, ref: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(root / "scripts" / "release" / "bump-version.sh"), "--check-incremented-from", ref],
        cwd=root,
        capture_output=True,
        text=True,
    )


class ReleaseVersionPathTest(unittest.TestCase):
    def _scenario(self, base_version_path: str, next_version: str) -> subprocess.CompletedProcess[str]:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        build_repo(root, base_version_path, "0.3.11")

        # Move to the current layout and bump.
        if base_version_path != VERSION_PATH:
            git("rm", "--quiet", "-r", "plugins", cwd=root)
        (root / VERSION_PATH).write_text(f"{next_version}\n", encoding="utf-8")
        git("add", "-A", cwd=root)
        git("commit", "--quiet", "-m", "move to repo root", cwd=root)

        return run_check(root, "refs/tags/0.3.11")

    def test_reads_the_legacy_version_path_at_older_refs(self) -> None:
        result = self._scenario(LEGACY_VERSION_PATH, "0.3.12")
        self.assertEqual(
            result.returncode,
            0,
            f"expected the legacy fallback to resolve\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        self.assertIn("0.3.11 -> 0.3.12", result.stdout)

    def test_reads_the_current_version_path_at_newer_refs(self) -> None:
        result = self._scenario(VERSION_PATH, "0.3.12")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0.3.11 -> 0.3.12", result.stdout)

    def test_still_rejects_a_version_that_did_not_advance(self) -> None:
        # The fallback must not turn a real comparison failure into a pass.
        result = self._scenario(LEGACY_VERSION_PATH, "0.3.11")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be greater than", result.stderr)

    def test_fails_clearly_when_no_version_file_exists_at_the_ref(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)

        init_repo(root)
        (root / "README.md").write_text("no version here\n", encoding="utf-8")
        git("add", "-A", cwd=root)
        git("commit", "--quiet", "-m", "no version", cwd=root)
        git("tag", "empty-base", cwd=root)

        (root / VERSION_PATH).write_text("0.3.12\n", encoding="utf-8")
        git("add", "-A", cwd=root)
        git("commit", "--quiet", "-m", "add version", cwd=root)

        result = run_check(root, "refs/tags/empty-base")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no canonical version file", result.stderr)


if __name__ == "__main__":
    unittest.main()
