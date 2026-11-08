"""A model that returns ``cad.cadjoint.solid(...)`` built by the engine and exported, as any model is.

The solid is build123d's and its faces planes, so the document the engine writes of it takes it as any
solid (no face without a surface), and an STL exported from that document holds the box the field draws:
40 x 20 x 6 mm. The engine runs in folders of the test's own (``engine_daemon.isolate``).
"""

from __future__ import annotations

import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import engine_daemon

MODEL = """
from cadjoint.construction import Solid

from cad import xbf
from cad.cadjoint import solid


@xbf("out/block.xbf")
def block():
    return solid(Solid.box(size=(20.0, 10.0, 3.0), position=(0.0, 0.0, 3.0), name="block"), cell=1.0)
"""


class EngineTest(unittest.TestCase):
    def setUp(self) -> None:
        engine_daemon.isolate(self.addCleanup)
        self.folder = Path(tempfile.mkdtemp(prefix="cadjoint-engine-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)

    def test_a_model_of_a_field_builds_into_a_document_and_exports_its_box(self) -> None:
        import numpy as np

        import cad
        from cad.engine import build as engine_build
        from cad.engine.formats.stl import read_stl

        script = self.folder / "block.py"
        script.write_text(textwrap.dedent(MODEL), encoding="utf-8")
        [report] = engine_build.build(script, None, cwd=self.folder)
        self.assertTrue(report["ok"], report.get("error"))
        document = self.folder / "out" / "block.xbf"
        self.assertTrue(document.is_file())
        stl = self.folder / "block.stl"
        cad.xbf.export(document, stl)
        corners = read_stl(stl).reshape(-1, 3)
        low, high = corners.min(axis=0), corners.max(axis=0)
        np.testing.assert_allclose(high - low, (40.0, 20.0, 6.0), atol=0.05)
        np.testing.assert_allclose(low, (-20.0, -10.0, 0.0), atol=0.05)


if __name__ == "__main__":
    unittest.main()
