"""What the desktop app ships from ``apps/desktop/resources`` is real bytes, never LFS.

electron-builder copies ``apps/desktop/resources/{sample,cadgen,skills}`` into
every installer (``extraResources``), and the release workflow checks out
without git-lfs. An LFS-tracked path there ships as a 130-byte pointer: the
onboarding sample's ``l_bracket.step`` did, and the first thing a new person
opened failed to load.
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path
from tests.python.support.tmp_root import temporary_directory


LFS_POINTER = b"version https://git-lfs"


def git(*args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=repo_path(), input=input, capture_output=True, check=True,
    ).stdout


class DesktopResourcesAreNotLfsTests(unittest.TestCase):
    def tracked(self) -> list[str]:
        return git("ls-files", "-z", "apps/desktop/resources").decode().split("\0")[:-1]

    def test_no_path_under_desktop_resources_is_lfs_tracked(self) -> None:
        attributes = git("check-attr", "--stdin", "-z", "filter", input="\0".join(self.tracked()).encode())
        fields = attributes.decode().split("\0")
        lfs = [fields[i] for i in range(0, len(fields) - 2, 3) if fields[i + 2] == "lfs"]
        self.assertEqual(lfs, [])

    def test_no_committed_desktop_resource_is_an_lfs_pointer(self) -> None:
        paths = self.tracked()
        batch = git("cat-file", "--batch", input="".join(f":{path}\n" for path in paths).encode())
        pointers, offset = [], 0
        for path in paths:
            header_end = batch.index(b"\n", offset)
            size = int(batch[offset:header_end].split()[2])
            if batch[header_end + 1 : header_end + 1 + size].startswith(LFS_POINTER):
                pointers.append(path)
            offset = header_end + 1 + size + 1
        self.assertEqual(pointers, [])


class CheckBuildsRefusesLfsInDesktopResourcesTests(unittest.TestCase):
    """``check-builds.sh`` over a fake repository: its tree checks, not the bundle."""

    def setUp(self) -> None:
        temporary = temporary_directory(prefix="check-builds-lfs-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git("init", "-q", "-b", "main")
        script = self.root / "scripts" / "github-workflows" / "check-builds.sh"
        script.parent.mkdir(parents=True)
        shutil.copy(repo_path("scripts/github-workflows/check-builds.sh"), script)
        # The bundler's generated-path list, empty: nothing is built here.
        outputs = self.root / "scripts" / "bundle" / "cadgen-runtime.sh"
        outputs.parent.mkdir(parents=True)
        outputs.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        outputs.chmod(0o755)
        (self.root / ".gitattributes").write_text("*.step filter=lfs diff=lfs merge=lfs -text\n", encoding="utf-8")
        sample = self.root / "apps" / "desktop" / "resources" / "sample"
        sample.mkdir(parents=True)
        (sample / "l_bracket.step").write_text("ISO-10303-21;\n", encoding="utf-8")
        self.git("add", ".")

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def check(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(self.root / "scripts" / "github-workflows" / "check-builds.sh"), "--skip-bundle-check"],
            cwd=self.root, text=True, capture_output=True, check=False,
        )

    def test_an_lfs_path_under_desktop_resources_fails_the_check(self) -> None:
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("apps/desktop/resources/sample/l_bracket.step", result.stderr)

    def test_a_non_ascii_lfs_path_fails_the_check(self) -> None:
        sample = self.root / "apps" / "desktop" / "resources" / "sample"
        self.git("rm", "-q", "-f", "apps/desktop/resources/sample/l_bracket.step")
        sample.mkdir(parents=True, exist_ok=True)
        (sample / "résumé.step").write_text("ISO-10303-21;\n", encoding="utf-8")
        self.git("add", ".")
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("apps/desktop/resources/sample/résumé.step", result.stderr)

    def test_a_path_taken_out_of_lfs_passes(self) -> None:
        sample = self.root / "apps" / "desktop" / "resources" / "sample"
        (sample / ".gitattributes").write_text("l_bracket.step !filter !diff !merge text\n", encoding="utf-8")
        self.git("add", ".")
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
