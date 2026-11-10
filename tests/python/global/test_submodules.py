"""No submodule is checked out by a recursive clone of this repository.

An app pinned here as a submodule (``apps/t3code``) is another repository, fetched
only by someone who asks for it. An agent app that installs the plugin from ``main``
clones it with ``--recurse-submodules``: without ``update = none`` that clone fetches
the whole app, then recurses into the app's own gitlinks, and T3 Code's pinned tree
carries two with no ``.gitmodules`` entry, so the clone exits 128 and the install fails.
``update = none`` makes the clone skip it; ``git submodule update --init --checkout
<path>`` still fetches it.

The pin is a gitlink, a commit of the other repository, so the tree's size check skips
it: ``git cat-file`` has no such object here and answers ``<sha> missing``, which read
as a size is any sha that starts with digits and an ``e``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _sections(text: str) -> dict[str, dict[str, str]]:
    """``.gitmodules``' submodule sections, each its keys."""
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in text.splitlines():
        header = re.match(r'^\s*\[submodule\s+"([^"]+)"\]\s*$', line)
        if header:
            current = sections.setdefault(header.group(1), {})
        elif current is not None and (entry := re.match(r"^\s*([A-Za-z]+)\s*=\s*(.*?)\s*$", line)):
            current[entry.group(1).lower()] = entry.group(2)
    return sections


class SubmodulesTest(unittest.TestCase):
    def test_a_recursive_clone_checks_out_no_submodule(self) -> None:
        gitmodules = REPO_ROOT / ".gitmodules"
        if not gitmodules.is_file():
            self.skipTest("no submodules")
        for name, keys in _sections(gitmodules.read_text(encoding="utf-8")).items():
            with self.subTest(submodule=name):
                self.assertEqual(keys.get("update"), "none", f"{name}: a recursive clone would check it out")

    def test_the_size_check_reads_no_gitlink_as_a_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gitlink-size-") as temporary:
            root = Path(temporary)
            script = root / "scripts/github-workflows/check-builds.sh"
            script.parent.mkdir(parents=True)
            shutil.copy(repo_path("scripts/github-workflows/check-builds.sh"), script)

            def git(*args: str) -> None:
                subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

            def tree_check() -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    ["bash", str(script), "--tree-only"], cwd=root, text=True, capture_output=True, check=False,
                )

            git("init", "-b", "main")
            git("add", "scripts")
            # "3e7..." as a size is 3e7 bytes, over the 5 MiB limit.
            git("update-index", "--add", "--cacheinfo", f"160000,3e7{'a' * 37},apps/pinned")
            result = tree_check()
            self.assertEqual(result.returncode, 0, result.stderr)

            (root / "big.bin").write_bytes(b"\0" * (5 * 1024 * 1024))
            git("add", "big.bin")
            result = tree_check()
            self.assertEqual(result.returncode, 1)
            self.assertIn("big.bin", result.stderr)
            self.assertNotIn("apps/pinned", result.stderr)


if __name__ == "__main__":
    unittest.main()
