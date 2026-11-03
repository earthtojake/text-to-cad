"""An STL's or a 3MF's own mesh tolerance (`export/__init__.py`, `export/mesh.py`): an absolute
ceiling on the linear deflection in millimetres, for a print whose fits are finer than the viewer's
quarter per cent of each part, given by `export(tolerance=)`, `cad export --tolerance` or the
decorator; each part meshed again at the finer of the two for that file alone, the cache left
holding the engine's tolerance, and the file saying what it was meshed to (#753)."""

from __future__ import annotations

import math
import re
import shutil
import struct
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

import numpy as np

from cad.engine import api
from cad.engine.export import ExportRefused

# The issue's own part: a 85 mm tube, 47 segments round at the engine's tolerance, its facets 0.095 mm deep.
SCRIPT = """
import build123d as bd
from cad import threemf, xbf


@xbf("XBF/tube.xbf")
@threemf("fine.3mf", tolerance=0.01)
def tube():
    return bd.Cylinder(42.5, 60) - bd.Cylinder(38.5, 60)
"""

_RECORD = np.dtype([("normal", "<f4", 3), ("corners", "<f4", (3, 3)), ("attribute", "<u2")])


def _stl(path: Path) -> tuple[bytes, np.ndarray]:
    data = path.read_bytes()
    return data[:80], np.frombuffer(data[84:], dtype=_RECORD)["corners"].reshape(-1, 3)


def _segments(points: np.ndarray) -> int:
    """The outer circle's segment count, read off its vertices on the tube's bottom face."""
    radius = np.hypot(points[:, 0], points[:, 1])
    ring = points[(radius > 40) & (np.abs(points[:, 2] - points[:, 2].min()) < 1e-3)]
    return len(np.unique(np.round(np.arctan2(ring[:, 1], ring[:, 0]), 5)))


def _depth(segments: int) -> float:
    return 42.5 * (1 - math.cos(math.pi / segments))


class ExportToleranceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = Path(tempfile.mkdtemp(prefix="export-tolerance-")).resolve()
        (cls.folder / "tube.py").write_text(textwrap.dedent(SCRIPT), encoding="utf-8")
        api.build_script(cls.folder / "tube.py", daemon=False)
        cls.xbf = cls.folder / "XBF/tube.xbf"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.folder, ignore_errors=True)

    def test_an_stl_at_a_tolerance_is_meshed_to_it_and_says_so_and_the_next_is_the_viewer_s_again(self) -> None:
        fine, coarse = self.folder / "fine.stl", self.folder / "coarse.stl"
        [written] = api.export(self.xbf, fine, tolerance=0.01, daemon=False, progress=False)
        self.assertEqual(written.kind, "stl")
        header, points = _stl(fine)
        self.assertEqual(header.rstrip(), b"tube (meshed within 0.01 mm)")
        self.assertLessEqual(_depth(_segments(points)), 0.01)
        # The cache still holds the engine's tolerance: an export after it is the viewer's mesh.
        api.export(self.xbf, coarse, daemon=False, progress=False)
        header, points = _stl(coarse)
        self.assertEqual(header.rstrip(), b"tube")
        self.assertEqual(_segments(points), 47)

    def test_a_tolerance_coarser_than_a_part_s_own_leaves_the_part_as_the_viewer_meshes_it(self) -> None:
        # The tube's own deflection is a quarter per cent of its 230 mm of sides, 0.19 mm: a ceiling of 1 mm
        # never makes it coarser (a small part meshed coarser than its own was seen to lose faces).
        coarse, ceiling = self.folder / "viewer.stl", self.folder / "ceiling.stl"
        api.export(self.xbf, coarse, daemon=False, progress=False)
        api.export(self.xbf, ceiling, tolerance=1.0, daemon=False, progress=False)
        self.assertEqual(_stl(ceiling)[1].tobytes(), _stl(coarse)[1].tobytes())

    def test_a_declared_3mf_at_a_tolerance_is_meshed_to_it_and_says_so(self) -> None:
        model = zipfile.ZipFile(self.folder / "fine.3mf").read("3D/3dmodel.model").decode()
        self.assertIn('<metadata name="Description">Meshed to within 0.01 mm</metadata>', model)
        vertices = re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"/>', model)
        self.assertLessEqual(_depth(_segments(np.array(vertices, dtype=float))), 0.01)

    def test_a_tolerance_is_refused_by_name_before_anything_is_written(self) -> None:
        for tolerance, destination, said in ((0.0001, "a.stl", "at least 0.001 mm"), (float("nan"), "a.stl", "at least"),
                                             ("0.01", "a.stl", "a number of millimetres"),
                                             (0.01, "a.step", "export the STEP without one"),
                                             (0.01, "a.glb", "export the GLB without one")):
            with self.subTest(tolerance=tolerance, destination=destination):
                with self.assertRaises(ExportRefused) as refused:
                    api.export(self.xbf, self.folder / "refused" / destination, self.folder / "refused" / "b.stl",
                               tolerance=tolerance, daemon=False, progress=False)
                self.assertIn(said, str(refused.exception))
        self.assertFalse((self.folder / "refused").exists())
        coarse = self.folder / "mesh.stl"
        api.export(self.xbf, coarse, daemon=False, progress=False)
        with self.assertRaisesRegex(ExportRefused, "no tolerance meshes it again"):
            api.export(coarse, self.folder / "again.3mf", tolerance=0.01, daemon=False, progress=False)
        from cad import step, stl

        with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'tolerance'"):
            step("part.step", tolerance=0.01)
        with self.assertRaisesRegex(ExportRefused, "at least 0.001 mm"):
            stl("part.stl", tolerance=0)


if __name__ == "__main__":
    unittest.main()
