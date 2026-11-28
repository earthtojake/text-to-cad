"""The model spellings of ``cad.xbf``: ``cad.model`` (``from cad import model``, ``import cad.model``), ``@model``,
``model(shape, ...)``, ``model.param``, ``model.read`` and every ``cad.model.<operation>``, and ``cad.read_xbf``. Each
is an alias of the xbf spelling through the library's one table (``cad._internal.aliases``, pinned by ``test_aliases``):
the same object, so the same behaviour and the same results, saying once per process that it is deprecated and what to
use. These are the tests a removal of the spellings deletes with them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path

import cad
import cad.engine
import cad.engine.model

# One model, declared by either spelling: its .xbf beside the script, in a folder of its own.
ARM = """
import build123d as bd
{imports}


{declared}
def arm():
    base = bd.Box(40, 20, 10)
    pin = bd.Pos(0, 0, 10) * bd.Cylinder(4, 10)
    base.label, pin.label = "base", "pin"
    return bd.Compound(children=[base, pin], label="arm")
"""

# Every spelling, each said once, at the line that spelled it, naming the new path; said again, silent.
SPELLINGS = """\
from cad import model
import cad, cad.model, cad.xbf
model.read, model.export, cad.model.inspect
cad.read_xbf
from cad import model
cad.read_xbf, cad.model.dfm
"""


class TheModelSpellingsAreTheXbfOnes(unittest.TestCase):
    def test_each_is_the_xbf_object_and_listed_nowhere(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", cad.CadDeprecationWarning)
            from cad import model

            self.assertIs(model, cad.xbf)
            self.assertIs(cad.model, cad.xbf)
            self.assertIs(cad.read_xbf, cad.xbf.read)
            self.assertIs(model.read, cad.xbf.read)
            for name in ("export", "inspect", "snapshot", "dfm", "interference", "solve", "ranges", "param"):
                with self.subTest(operation=name):
                    self.assertIs(getattr(model, name), getattr(cad.xbf, name))
        self.assertNotIn("model", cad.__all__)
        self.assertNotIn("model", dir(cad))

    def test_each_warns_once_naming_the_xbf_spelling_at_the_line_that_spelled_it(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "older.py"
            script.write_text(SPELLINGS, encoding="utf-8")
            proc = subprocess.run([sys.executable, "older.py"], capture_output=True, text=True, timeout=120, cwd=folder)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual(["older.py:1: CadDeprecationWarning: cad.model is deprecated; use cad.xbf",
                          "older.py:4: CadDeprecationWarning: cad.read_xbf is deprecated; use cad.xbf.read"],
                         [line for line in proc.stderr.splitlines() if "CadDeprecationWarning" in line])

    def test_the_decorator_and_the_hand_over_are_the_xbf_ones_under_the_warning(self) -> None:
        script = ("""\
import warnings
warnings.simplefilter("error", FutureWarning)
from cad import xbf
@xbf
def a():
    return None
""")
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "primary.py").write_text(script, encoding="utf-8")
            primary = subprocess.run([sys.executable, "primary.py"], capture_output=True, text=True, timeout=120, cwd=folder)
        self.assertEqual((primary.returncode, primary.stderr), (0, ""), "@xbf is the primary spelling: no warning")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", cad.CadDeprecationWarning)
            from cad import model

            self.assertIs(type(model).__call__, type(cad.xbf).__call__)
            self.assertIs(type(model), type(cad.xbf))


class TheModelDecoratorBuildsTheSameDocument(unittest.TestCase):
    def test_either_spelling_makes_one_document_one_file_and_one_closure(self) -> None:
        """A script that says ``@xbf(path)`` and the same script saying ``@model(path)`` are one model: the
        same id, the same file at the path relative to the script, byte for byte (the closure in it too), and a
        run of one after the other is a run that changed nothing, which leaves the file as it is."""
        from cad.engine import build as engine_build

        folder = Path(tempfile.mkdtemp(prefix="older-model-")).resolve()
        self.addCleanup(shutil.rmtree, folder, True)
        script, saved = folder / "src" / "arm.py", folder / "share" / "arm.xbf"
        script.parent.mkdir()

        def built(imports: str, declared: str) -> dict:
            script.write_text(ARM.format(imports=imports, declared=declared), encoding="utf-8")
            os.utime(script, ns=(time.time_ns(), time.time_ns()))  # a rewrite in one clock tick is a new file
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", cad.CadDeprecationWarning)
                (report,) = engine_build.build(script, ["arm"], cwd=folder)
            self.assertTrue(report["ok"], report)
            return report

        now = built("from cad import xbf", '@xbf("../share/arm.xbf")')
        self.assertEqual({path: row["written"] for path, row in now["files"].items()}, {str(saved): True})
        first, written = saved.read_bytes(), saved.stat().st_mtime_ns
        older = built("from cad import model", '@model("../share/arm.xbf")')
        self.assertEqual((older["id"], list(older["files"])), (now["id"], list(now["files"])))
        self.assertEqual([row["written"] for row in older["files"].values()], [False], "the file it already is")
        self.assertEqual((saved.read_bytes(), saved.stat().st_mtime_ns), (first, written))
        saved.unlink()
        again = built("from cad import model", '@model("../share/arm.xbf")')
        self.assertEqual(([row["written"] for row in again["files"].values()], saved.read_bytes()), ([True], first))


if __name__ == "__main__":
    unittest.main()
