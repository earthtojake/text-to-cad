"""A GLB's, an STL's or a 3MF's own mesh tolerance and angle (`export/__init__.py`, `export/mesh.py`):
absolute ceilings on the linear deflection in millimetres and the angular one in degrees, for a print
whose fits are finer than the viewer's quarter per cent of each part or a picture whose curves are,
given by `export(tolerance=, angle=)`, `cad export --tolerance --angle` or the decorator; each part
meshed again at the finer of each for that file alone, the cache left holding the engine's tolerance,
and the file saying what it was meshed to (#753)."""

from __future__ import annotations

import json
import math
import re
import shutil
import struct
import tempfile
import textwrap
import unittest
import zipfile
from unittest import mock
from pathlib import Path

import numpy as np

from cad.engine import api
from cad.engine.export import MAX_ANGLE, ExportRefused, translate
from cad.engine.mesh_format import ANGULAR

# The issue's own part: a 85 mm tube, 47 segments round at the engine's tolerance, its facets 0.095 mm deep.
SCRIPT = """
import build123d as bd
from cad import glb, threemf, xbf


@xbf("XBF/tube.xbf")
@threemf("fine.3mf", tolerance=0.01)
@glb("fine.glb", tolerance=0.05, angle=5)
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


def _glb(path: Path) -> tuple[dict, int]:
    """A GLB's JSON and its triangle count."""
    data = path.read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + length])
    return gltf, sum(gltf["accessors"][primitive["indices"]]["count"] // 3
                     for mesh in gltf["meshes"] for primitive in mesh["primitives"])


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

    def test_a_glb_is_the_viewer_s_mesh_unless_the_export_says_and_then_it_says_what_it_was_meshed_to(self) -> None:
        plain, again = self.folder / "plain.glb", self.folder / "again.glb"
        api.export(self.xbf, plain, daemon=False, progress=False)
        gltf, triangles = _glb(plain)
        self.assertEqual(gltf["asset"], {"version": "2.0", "generator": "cad"}, "no stamp where the export asked nothing")
        finer = {}
        for name, options, stamp in (("tolerance", {"tolerance": 0.01}, {"meshedWithin": 0.01}),
                                     ("angle", {"angle": 5}, {"angle": 5.0})):
            finer[name] = self.folder / f"{name}.glb"
            api.export(self.xbf, finer[name], daemon=False, progress=False, **options)
            gltf, fine = _glb(finer[name])
            self.assertEqual(gltf["asset"]["extras"], {"cad": stamp})
            self.assertGreater(fine, triangles, name)
        declared, _fine = _glb(self.folder / "fine.glb")
        self.assertEqual(declared["asset"]["extras"], {"cad": {"meshedWithin": 0.05, "angle": 5.0}})
        # Never cached: the next plain export is the viewer's mesh, byte for byte.
        api.export(self.xbf, again, daemon=False, progress=False)
        self.assertEqual(again.read_bytes(), plain.read_bytes())

    def test_an_angle_reaches_small_radii_and_an_stl_and_a_3mf_say_it(self) -> None:
        self.assertAlmostEqual(MAX_ANGLE, math.degrees(ANGULAR), msg="the ceiling is the viewer's own angle")
        stl_file, threemf_file = self.folder / "angle.stl", self.folder / "angle.3mf"
        api.export(self.xbf, stl_file, angle=5, daemon=False, progress=False)
        header, points = _stl(stl_file)
        self.assertEqual(header.rstrip(), b"tube (meshed within 5 degrees)")
        self.assertGreaterEqual(_segments(points), 72, "at most 5 degrees a segment round the tube")
        api.export(self.xbf, threemf_file, tolerance=0.1, angle=5, daemon=False, progress=False)
        self.assertIn('<metadata name="Description">Meshed to within 0.1 mm and 5 degrees</metadata>',
                      zipfile.ZipFile(threemf_file).read("3D/3dmodel.model").decode())

    def test_a_face_left_without_triangles_is_named_at_an_angle_too(self) -> None:
        from cad.engine import mesh

        real, lines = mesh.mesh_shape, []

        def leaving_a_face(*args, **options):
            made = real(*args, **options)
            made.unmeshed = {3: "SelfIntersectingWire"}
            return made

        with mock.patch.object(mesh, "mesh_shape", leaving_a_face):
            translate(self.xbf, None, self.folder / "told.glb", told=lines.append, angle=5)
        self.assertEqual(lines, ["told.glb: 1 face of part1 left without triangles meshing to within 5 degrees"])

    def test_a_server_too_old_for_an_option_is_said_by_the_option_it_did_not_honour(self) -> None:
        target = self.folder / "old.stl"
        row = {"path": str(target), "kind": "stl", "bytes": 1, "seconds": 0.0}
        for answer, said in (({**row, "tolerance": 0.01}, "at its own angle: it is older"),
                             (row, "at its own tolerance and angle: it is older")):
            with self.subTest(said=said), mock.patch.object(api, "_exported", return_value={"files": [answer]}):
                with self.assertRaisesRegex(api.EngineError, said):
                    api.export(self.xbf, target, tolerance=0.01, angle=5, progress=False)

    def test_a_tolerance_is_refused_by_name_before_anything_is_written(self) -> None:
        for tolerance, destination, said in ((0.0001, "a.stl", "at least 0.001 mm"), (float("nan"), "a.stl", "at least"),
                                             ("0.01", "a.stl", "a number of millimetres"),
                                             (0.01, "a.step", "export the STEP without one")):
            with self.subTest(tolerance=tolerance, destination=destination):
                with self.assertRaises(ExportRefused) as refused:
                    api.export(self.xbf, self.folder / "refused" / destination, self.folder / "refused" / "b.stl",
                               tolerance=tolerance, daemon=False, progress=False)
                self.assertIn(said, str(refused.exception))
        for angle, destination, said in ((28.6, "a.glb", "from 1 to 28.5 degrees"), (0.5, "a.glb", "from 1 to 28.5 degrees"),
                                         (float("nan"), "a.stl", "from 1 to 28.5 degrees"),
                                         ("5", "a.stl", "a number of degrees"), (True, "a.stl", "a number of degrees"),
                                         (5, "a.step", "an angle meshes a GLB, an STL or a 3MF; export the STEP without one")):
            with self.subTest(angle=angle, destination=destination):
                with self.assertRaises(ExportRefused) as refused:
                    api.export(self.xbf, self.folder / "refused" / destination, angle=angle, daemon=False, progress=False)
                self.assertIn(said, str(refused.exception))
        self.assertFalse((self.folder / "refused").exists())
        coarse = self.folder / "mesh.stl"
        api.export(self.xbf, coarse, daemon=False, progress=False)
        for option in ({"tolerance": 0.01}, {"angle": 5}):
            with self.subTest(option=option), self.assertRaisesRegex(ExportRefused, "no tolerance or angle meshes it again"):
                api.export(coarse, self.folder / "again.3mf", daemon=False, progress=False, **option)
        from cad import glb, step, stl

        with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'tolerance'"):
            step("part.step", tolerance=0.01)
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'angle'"):
            step("part.step", angle=5)
        with self.assertRaisesRegex(TypeError, "unexpected keyword argument 'angle'"):
            stl.export("part.stl", "part.glb", angle=5)
        with self.assertRaisesRegex(ExportRefused, "at least 0.001 mm"):
            stl("part.stl", tolerance=0)
        with self.assertRaisesRegex(ExportRefused, "from 1 to 28.5 degrees"):
            glb("part.glb", angle=29)


if __name__ == "__main__":
    unittest.main()
