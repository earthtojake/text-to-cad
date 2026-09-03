"""A build writes no bytecode for model code, so none can go stale.

`_purge_stale_bytecode` deletes `__pycache__` at the job boundary, but on
Windows a `.pyc` held open by a scanner or another interpreter refuses deletion
and the purge swallows it (`ignore_errors=True`). CPython then ACCEPTS that
stale file, because it validates by (whole-second mtime, size) -- two
same-length edits inside one second, which is an agent's edit loop -- and the
build silently uses code that is not on disk. Correctness therefore rests on
writing no bytecode at all, not on a delete succeeding.
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class NoStaleBytecodeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cadgen-pyc-")
        self.root = Path(self._tmp.name)
        self.project = self.root / "proj"
        (self.project / "lib").mkdir(parents=True)
        (self.project / "lib" / "__init__.py").write_text("", encoding="utf-8")
        (self.project / "lib" / "dims.py").write_text("SIZE = 6\n", encoding="utf-8")
        (self.project / "model.py").write_text(
            textwrap.dedent('''
            from cadgen import build123d as bd
            from cadgen import step
            from lib import dims

            @step(out="model.step")
            def model():
                return bd.Box(dims.SIZE, dims.SIZE, dims.SIZE)


            if __name__ == "__main__":
                model()
            '''),
            encoding="utf-8",
        )
        self._env = {k: os.environ.get(k) for k in ("CADGEN_CACHE_DIR", "CADGEN_DAEMON")}
        os.environ["CADGEN_CACHE_DIR"] = str(self.root / "cache")
        os.environ["CADGEN_DAEMON"] = "0"
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for name in [n for n in sys.modules if n == "lib" or n.startswith("lib.") or n == "model"]:
            sys.modules.pop(name, None)
        self._tmp.cleanup()

    def _build(self) -> None:
        from cadgen.generation import generate_step_targets

        self.assertEqual(0, generate_step_targets([str(self.project / "model.py")], force=True))

    def test_a_build_leaves_no_bytecode_for_the_model_or_its_helpers(self) -> None:
        self._build()
        self.assertTrue((self.project / "model.step").is_file())
        leftovers = sorted(str(p.relative_to(self.project)) for p in self.project.rglob("__pycache__"))
        # Not "the purge removed them" -- none were ever written, which is what
        # makes the guarantee independent of a delete being permitted.
        self.assertEqual([], leftovers, f"a build wrote bytecode for model code: {leftovers}")

    def test_the_flag_is_restored_afterwards(self) -> None:
        before = sys.dont_write_bytecode
        self._build()
        self.assertEqual(before, sys.dont_write_bytecode)

    def test_the_window_is_what_suppresses_it(self) -> None:
        """Mutation check: with the window neutralised, bytecode reappears.

        Pins that the absence above is caused by `_without_bytecode_writes` and
        not by some incidental property of the loader.
        """
        import contextlib
        from unittest import mock

        from cadgen._internal import generation_runner

        with mock.patch.object(generation_runner, "_without_bytecode_writes", contextlib.nullcontext):
            self._build()
        leftovers = sorted(str(p.relative_to(self.project)) for p in self.project.rglob("__pycache__"))
        self.assertNotEqual([], leftovers, "the window is not what suppresses bytecode writes")


if __name__ == "__main__":
    unittest.main()
