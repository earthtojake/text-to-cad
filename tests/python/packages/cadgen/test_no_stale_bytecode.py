"""Model code runs from the source on disk: a build neither reads nor writes
its bytecode.

CPython accepts a ``.pyc`` by (whole-second mtime, size), so two same-length
edits inside one second -- an agent's edit loop -- run STALE bytecode while the
closure hashes the new source, and a wrong result is recorded as current. A
build compiles every first-party module from the bytes on disk and writes no
``.pyc`` for anything it imports, so whatever another tool left in
``__pycache__`` never runs.
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
        flag_before = sys.dont_write_bytecode
        self._build()
        self.assertEqual(flag_before, sys.dont_write_bytecode, "the window must restore the flag")
        self.assertTrue((self.project / "model.step").is_file())
        leftovers = sorted(str(p.relative_to(self.project)) for p in self.project.rglob("__pycache__"))
        # Not "the purge removed them" -- none were ever written, which is what
        # makes the guarantee independent of a delete being permitted.
        self.assertEqual([], leftovers, f"a build wrote bytecode for model code: {leftovers}")

    def test_the_window_is_what_suppresses_it(self) -> None:
        """Mutation check: with the window neutralised, bytecode reappears.

        Pins that the absence above is caused by `_first_party_from_source` and
        not by some incidental property of the loader.
        """
        import contextlib
        from unittest import mock

        from cadgen._internal import generation_runner

        with mock.patch.object(generation_runner, "_first_party_from_source", contextlib.nullcontext):
            self._build()
        leftovers = sorted(str(p.relative_to(self.project)) for p in self.project.rglob("__pycache__"))
        self.assertNotEqual([], leftovers, "the window is not what suppresses bytecode writes")


    def test_a_stale_pyc_left_by_another_tool_never_runs(self) -> None:
        import importlib
        import py_compile

        from cadgen._internal.generation_runner import _first_party_from_source

        dims = self.project / "lib" / "dims.py"
        stat = dims.stat()
        py_compile.compile(str(dims), doraise=True)  # another tool compiles SIZE = 6
        dims.write_text("SIZE = 7\n", encoding="utf-8")  # the same length...
        os.utime(dims, ns=(stat.st_atime_ns, stat.st_mtime_ns))  # ...inside the same second
        sys.path.insert(0, str(self.project))
        self.addCleanup(sys.path.remove, str(self.project))

        def size() -> int:
            for name in ("lib.dims", "lib"):
                sys.modules.pop(name, None)
            return importlib.import_module("lib.dims").SIZE

        self.assertEqual(size(), 6, "control: CPython runs the stale bytecode")
        with _first_party_from_source():
            self.assertEqual(size(), 7)
            with _first_party_from_source():  # nested, as a metadata load inside a build
                self.assertEqual(size(), 7)


    def test_a_delegating_import_hook_beside_the_window_does_not_recurse(self) -> None:
        """An import hook that asks the rest of ``sys.meta_path`` (a user's, a
        tool's) and the window's finder must not hand a lookup back and forth."""
        import importlib
        import importlib.abc

        from cadgen._internal.generation_runner import _first_party_from_source

        class Delegating(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path, target=None):
                for finder in sys.meta_path:
                    if finder is not self and hasattr(finder, "find_spec"):
                        spec = finder.find_spec(fullname, path, target)
                        if spec is not None:
                            return spec
                return None

        hook = Delegating()
        sys.meta_path.insert(0, hook)
        self.addCleanup(sys.meta_path.remove, hook)
        sys.path.insert(0, str(self.project))
        self.addCleanup(sys.path.remove, str(self.project))
        for name in ("lib.dims", "lib"):
            sys.modules.pop(name, None)
        with _first_party_from_source():
            self.assertEqual(importlib.import_module("lib.dims").SIZE, 6)

if __name__ == "__main__":
    unittest.main()
