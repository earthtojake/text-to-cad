"""A release's own check of itself (``cad_server._internal.selftest``), which cad's update runs once in a release it
built before the release counts (``store.verify``): run as ``__main__``, it imports what the release runs, says ``cad
<release>`` last and ends with 0; a module it cannot import ends it otherwise.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from cad_server._internal import selftest, store
from tests.python.support.paths import REPO_ROOT, SOURCE_PATH
from tests.python.support.tmp_root import temporary_directory

SECONDS = 120


def run(command: list[str], timeout: float) -> tuple[int | None, str]:
    done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    return done.returncode, done.stdout + done.stderr


class SelftestTest(unittest.TestCase):
    def test_this_tree_passes_its_own_check(self) -> None:
        """Every module it names imports in the development environment, and it says this tree's release last."""
        found = subprocess.run([sys.executable, "-m", "cad_server._internal.selftest"], capture_output=True, text=True,
                               timeout=SECONDS, env={**os.environ, "PYTHONPATH": SOURCE_PATH})
        self.assertEqual(found.returncode, 0, found.stderr)
        release = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(found.stdout.splitlines()[-1], f"cad {release}")

    def test_run_as_verify_runs_it_it_needs_its_folder_alone_and_fails_on_a_module_it_lacks(self) -> None:
        """The module itself, in a release folder whose every module it names is a stand-in, run by ``store.verify``'s
        own command: nothing on the path but the standard library and that folder. Then one stand-in taken away."""
        scratch = temporary_directory(prefix="selftest-")
        self.addCleanup(scratch.cleanup)
        folder = Path(scratch.name) / "release"
        for name in ("cad_server", *selftest.MODULES):
            parts = name.split(".")
            for depth in range(1, len(parts) + 1):
                package = folder.joinpath(*parts[:depth])
                package.mkdir(parents=True, exist_ok=True)
                (package / "__init__.py").touch()
        (folder / "cad_server" / "__init__.py").write_text("__version__ = '9.9.9'\n", encoding="utf-8")
        shutil.copyfile(selftest.__file__, folder / "cad_server" / "_internal" / "selftest.py")
        command = [sys.executable, "-I", "-S", "-c", store.VERIFY, str(folder)]
        code, said = run(command, SECONDS)
        self.assertEqual((code, said.splitlines()[-1:]), (0, ["cad 9.9.9"]), said)
        shutil.rmtree(folder.joinpath(*selftest.MODULES[-1].split(".")))
        code, said = run(command, SECONDS)
        self.assertNotEqual(code, 0)
        self.assertIn("ModuleNotFoundError", said)
        self.assertNotIn("cad 9.9.9", said)


if __name__ == "__main__":
    unittest.main()
