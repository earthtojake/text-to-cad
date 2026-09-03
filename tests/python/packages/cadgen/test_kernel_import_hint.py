"""The eager-kernel hint names the statement that imported the kernel.

``from cadgen import build123d as bd`` keeps a module body kernel-free only
until something resolves an attribute on it: a module-level
``(bd.Align.CENTER,) * 3`` default is enough, and the old hint -- "use `from
cadgen import build123d as bd`" -- pointed a model that already did exactly
that at the wrong fix (w16 BUGS.md #2). The recorder installed by ``import
cadgen`` notes the first kernel import request and its calling line.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT

CADGEN_SRC = REPO_ROOT / "packages" / "cadgen" / "src"


def _posix_slashes(text: str) -> str:
    """The hint prints the OS separator, which is right for the reader and wrong
    for a fixed needle. One backslash is what a Windows path carries; the needle
    used to be a two-backslash literal, so the replace was a no-op and the
    assertion could never match on Windows."""
    return text.replace("\\", "/")


class NormalizerTest(unittest.TestCase):
    def test_a_windows_hint_path_is_normalized(self) -> None:
        """Pinned from any host: on macOS the replace is a no-op either way, so
        only a synthetic Windows hint tells the two needles apart."""
        hint = r"hint: the CAD kernel was imported at lib\geo.py:3 (CENTER3 = ...)"
        self.assertIn("lib/geo.py:3", _posix_slashes(hint))
        self.assertNotIn("lib/geo.py:3", hint.replace("\\\\", "/"))


class KernelImportHintTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cadgen-kernel-hint-")
        self.project = Path(self._tmp.name)
        (self.project / "lib").mkdir()
        (self.project / "lib" / "__init__.py").write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, name: str) -> str:
        env = dict(os.environ)
        env.update({
            "CADGEN_DAEMON": "0",
            "CADGEN_CACHE_DIR": str(self.project / "cache"),
            "PYTHONPATH": str(CADGEN_SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
        })
        result = subprocess.run(
            [sys.executable, f"{name}.py"], cwd=self.project, env=env, capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stderr

    def test_module_level_attribute_access_is_named_by_file_and_line(self) -> None:
        (self.project / "lib" / "geo.py").write_text(
            textwrap.dedent('''
            from cadgen import build123d as bd
            CENTER3 = (bd.Align.CENTER,) * 3
            def cube(size):
                return bd.Box(size, size, size, align=CENTER3)
            '''),
            encoding="utf-8",
        )
        (self.project / "hinted.py").write_text(
            textwrap.dedent('''
            from cadgen import build123d as bd
            from cadgen import step
            from lib import geo

            @step(out="hinted.step")
            def hinted():
                return geo.cube(5)


            if __name__ == "__main__":
                hinted()
            '''),
            encoding="utf-8",
        )
        stderr = self._run("hinted")
        hint = next((line for line in stderr.splitlines() if line.startswith("hint:")), "")
        self.assertIn("lib/geo.py:3", _posix_slashes(hint))
        self.assertIn("bd.Align.CENTER", hint)
        self.assertNotIn("imported the CAD kernel at module top", hint)

    def test_a_kernel_free_module_body_gets_no_hint(self) -> None:
        (self.project / "clean.py").write_text(
            textwrap.dedent('''
            from cadgen import build123d as bd
            from cadgen import step
            from cadgen import srgb

            GREY = srgb("#808080")   # a palette constant must not pull the kernel in

            @step(out="clean.step")
            def clean():
                box = bd.Box(5, 5, 5)
                box.color = GREY
                return box


            if __name__ == "__main__":
                clean()
            '''),
            encoding="utf-8",
        )
        stderr = self._run("clean")
        self.assertFalse([line for line in stderr.splitlines() if line.startswith("hint:")], stderr)


if __name__ == "__main__":
    unittest.main()
