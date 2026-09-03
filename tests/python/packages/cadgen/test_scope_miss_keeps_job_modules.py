"""A scope miss runs against the modules the job started with.

The scope layer used to evict every first-party module (and purge bytecode) on
every miss, mid-job. In a daemon worker the script's folder leaves sys.path
once its body has loaded, so a lazy ``from lib import x`` inside a function
that ran AFTER the first miss found no ``lib`` (w16 BUGS.md #9/#11: three
builders lost cold rebuilds to it); in-process the re-import created a second
``lib`` beside the first. Eviction belongs to the job boundary only.
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class ScopeMissKeepsJobModulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cadgen-scope-evict-")
        self.root = Path(self._tmp.name)
        self.project = self.root / "proj"
        (self.project / "lib").mkdir(parents=True)
        (self.project / "lib" / "__init__.py").write_text("", encoding="utf-8")
        (self.project / "lib" / "dims.py").write_text("SIZE = 5\n", encoding="utf-8")
        (self.project / "lib" / "heavy.py").write_text(
            textwrap.dedent('''
            from cadgen import build123d as bd

            def build():
                return bd.Box(4, 4, 4)
            '''),
            encoding="utf-8",
        )
        (self.project / "model.py").write_text(
            textwrap.dedent('''
            import sys
            from cadgen import build123d as bd
            from cadgen import step
            from cadgen.compose import memo
            from lib import heavy

            _HEAVY = memo(heavy.build)
            LIB_AT_LOAD = sys.modules["lib"]

            @step(out="model.step", kind="assembly")
            def model():
                core = _HEAVY()                      # a scope MISS on a fresh store
                from lib import dims                 # lazy sibling import AFTER the miss
                assert sys.modules["lib"] is LIB_AT_LOAD, "the job's lib was replaced mid-run"
                plate = bd.Box(dims.SIZE * 4, dims.SIZE * 4, 1).moved(bd.Location((0, 0, -3)))
                core.label = "core"; plate.label = "plate"
                return bd.Compound(children=[core, plate], label="model")


            if __name__ == "__main__":
                model()
            '''),
            encoding="utf-8",
        )
        self._env = {k: os.environ.get(k) for k in ("CADGEN_CACHE_DIR", "CADGEN_DAEMON")}
        os.environ["CADGEN_CACHE_DIR"] = str(self.root / "cache")
        os.environ["CADGEN_DAEMON"] = "0"
        self._cwd = os.getcwd()
        os.chdir(self.root)  # not the project: like a worker, the script's folder is off sys.path after load

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

    def test_lazy_sibling_import_after_a_scope_miss_still_resolves(self) -> None:
        from cadgen.generation import generate_step_targets

        self.assertEqual(0, generate_step_targets([str(self.project / "model.py")], force=True))
        self.assertTrue((self.project / "model.step").is_file())


if __name__ == "__main__":
    unittest.main()
