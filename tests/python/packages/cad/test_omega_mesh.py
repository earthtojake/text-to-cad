"""``cad omega mesh``: a GSL model meshed on request, judged as ``cad omega check`` judges one, and kept.

A model is asked about through its field (``cad run gsl eval``, ``cad run gsl render``) and meshed only when a
file is wanted. ``mesh`` is that step: omega's ``gsl eval`` meshes the model with the values given into a GLB, the
mesh is held to the field before anyone is handed it, and a mesh that passed is kept by what made it, so the same
model with the same values is never meshed twice.

What reads a GLB and names a mesh's key is numpy and the standard library, tested everywhere. What runs ``gsl``
needs one whose ``eval`` meshes (omega-core 0.1.2 or later; ``CAD_GSL`` names another than the extra's): those
tests skip, by name, where the ``gsl`` found does not. Every model is written by the test into a temporary folder.
"""

from __future__ import annotations

import importlib.util
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

HAS_OMEGA = importlib.util.find_spec("omega_core") is not None

BALL = "@scene(40)\nr = 8.0;\nr.min = 2.0;\nr.max = 15.0;\nball = length(p) - r;\nreturn ball;\n"


def _gsl_meshes() -> bool:
    """Whether the ``gsl`` cad would run answers ``eval``'s ``mesh``: asked once, of a model it must refuse."""
    if not HAS_OMEGA:
        return False
    try:
        import omega_core

        from cad.omega._program import find_gsl

        with omega_core.Session(program=str(find_gsl())) as session:
            try:
                session.request({"op": "mesh", "code": "return 1.0;"})
            except omega_core.EvalError as error:
                return "names out" in str(error)
    except Exception:  # noqa: BLE001 - no gsl to ask is no gsl that meshes
        return False
    return False


MESHES = _gsl_meshes()
NEEDS_MESH = "needs a gsl whose eval meshes (omega-core 0.1.2 or later: set CAD_GSL)"


def write_glb(path: Path, bodies: list[tuple[np.ndarray, np.ndarray]]) -> Path:
    """A binary glTF of ``bodies``, each ``(positions (n, 3), triangles (t, 3))``, a mesh and a node apiece."""
    blob = b""
    views, accessors, meshes, nodes = [], [], [], []
    for index, (positions, triangles) in enumerate(bodies):
        for data, kind, component in ((np.asarray(positions, "<f4"), "VEC3", 5126),
                                      (np.asarray(triangles, "<u4").reshape(-1), "SCALAR", 5125)):
            views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": data.nbytes})
            accessors.append({"bufferView": len(views) - 1, "componentType": component, "type": kind,
                              "count": int(len(data))})
            blob += data.tobytes()
        meshes.append({"primitives": [{"attributes": {"POSITION": 2 * index}, "indices": 2 * index + 1}]})
        nodes.append({"mesh": index, "name": f"body{index}"})
    document = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(blob)}], "bufferViews": views,
                           "accessors": accessors, "meshes": meshes, "nodes": nodes,
                           "scenes": [{"nodes": list(range(len(nodes)))}], "scene": 0}).encode()
    document += b" " * (-len(document) % 4)
    blob += b"\0" * (-len(blob) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 28 + len(document) + len(blob))
                     + struct.pack("<I4s", len(document), b"JSON") + document
                     + struct.pack("<I4s", len(blob), b"BIN\0") + blob)
    return path


TETRA_POINTS = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64)
TETRA_FACES = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])


class Reading(unittest.TestCase):
    def test_a_glb_s_bodies_are_read_as_one_array_of_triangles(self) -> None:
        from cad.omega._check import measure
        from cad.omega._mesh import read_glb

        with tempfile.TemporaryDirectory() as folder:
            path = write_glb(Path(folder) / "two.glb", [(TETRA_POINTS, TETRA_FACES), (TETRA_POINTS + 5, TETRA_FACES)])
            triangles = read_glb(path)
        self.assertEqual((8, 3, 3), triangles.shape)
        measured = measure(triangles)
        self.assertEqual((0, 0), (measured["open_edges"], measured["non_manifold_edges"]))
        self.assertAlmostEqual(2 / 6, measured["volume_mm3"])
        self.assertEqual([6.0, 6.0, 6.0], measured["bbox_max"])

    def test_a_file_that_is_no_glb_is_refused(self) -> None:
        from cad.omega._mesh import read_glb

        with tempfile.TemporaryDirectory() as folder:
            junk = Path(folder) / "j.glb"
            junk.write_bytes(b"not a mesh at all")
            with self.assertRaisesRegex(ValueError, "not a GLB"):
                read_glb(junk)


class Values(unittest.TestCase):
    def test_each_define_is_a_name_and_a_number_and_becomes_a_statement(self) -> None:
        from cad.omega._mesh import statements

        self.assertEqual("", statements(()))
        self.assertEqual("r = 6.5;\nwall = 2;\n", statements(("r=6.5", " wall = 2 ")))
        self.assertEqual("t = -1e-3;\n", statements(("t=-1e-3",)))

    def test_a_define_that_is_no_name_and_number_is_refused_by_name(self) -> None:
        from cad.omega._mesh import statements

        for bad in ("r", "=3", "r=", "r=wide", "2r=3", "r=1; return 0", "r=nan", "r=inf"):
            with self.subTest(bad), self.assertRaisesRegex(ValueError, "name=number"):
                statements((bad,))


class Key(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.model = self.folder / "part.gsl"
        self.model.write_text('@scene(40)\nimportMesh 0 "scan.stl";\nreturn bvhSdf(0);\n', encoding="utf-8")

    def key(self, **changed) -> str:
        from cad.omega._mesh import key

        given = {"defs": "", "depth": None, "gsl": "gsl 0.1.3"} | changed
        return key(self.model, given["defs"], given["depth"], given["gsl"])

    def test_the_same_model_values_depth_and_gsl_have_one_key(self) -> None:
        self.assertEqual(self.key(), self.key())
        self.assertRegex(self.key(), r"^[0-9a-f]{64}$")

    def test_the_values_the_depth_and_the_gsl_each_change_it(self) -> None:
        keys = {self.key(), self.key(defs="r = 6;\n"), self.key(depth=7), self.key(gsl="gsl 0.1.4")}
        self.assertEqual(4, len(keys))

    def test_an_edit_of_the_model_or_of_a_file_it_reads_changes_it(self) -> None:
        before = self.key()
        (self.folder / "scan.stl").write_bytes(b"one")
        with_file = self.key()
        (self.folder / "scan.stl").write_bytes(b"two")
        edited_file = self.key()
        self.model.write_text(self.model.read_text(encoding="utf-8") + "// a note\n", encoding="utf-8")
        self.assertEqual(4, len({before, with_file, edited_file, self.key()}))

    def test_where_the_model_is_does_not_change_it(self) -> None:
        other = self.folder / "elsewhere"
        other.mkdir()
        moved = other / "renamed.gsl"
        moved.write_bytes(self.model.read_bytes())
        from cad.omega._mesh import key

        self.assertEqual(self.key(), key(moved, "", None, "gsl 0.1.3"))


@unittest.skipUnless(MESHES, NEEDS_MESH)
class Mesh(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        cache = mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(self.folder / "cache")})
        cache.start()
        self.addCleanup(cache.stop)

    def model(self, name: str, text: str) -> Path:
        path = self.folder / f"{name}.gsl"
        path.write_text(text, encoding="utf-8")
        return path

    def codes(self, result) -> set[str]:
        return {finding.code for finding in result.findings if finding.severity == "error"}

    def test_a_sound_part_is_written_as_a_glb_whose_volume_is_the_field_s(self) -> None:
        from cad.omega import mesh
        from cad.omega._check import measure
        from cad.omega._mesh import read_glb

        out = self.folder / "made" / "ball.glb"
        result = mesh(self.model("ball", BALL), out, depth=6)
        self.assertTrue(result.ok, result.findings)
        self.assertRegex(result.summary, r"^OK .*ball\.gsl -> .*ball\.glb: \d+ triangles, .* mm3, .* in @scene\(40\)$")
        self.assertEqual(str(out), result.measurements["glb"])
        self.assertFalse(result.measurements["cached"])
        self.assertEqual(6, result.measurements["depth"])
        self.assertAlmostEqual(4 / 3 * np.pi * 8 ** 3, result.measurements["volume_mm3"], delta=20.0)
        low, high = result.measurements["field_volume_mm3"]
        self.assertLessEqual(low * 0.98, result.measurements["volume_mm3"])
        self.assertLessEqual(result.measurements["volume_mm3"], high * 1.02)
        written = measure(read_glb(out))
        self.assertEqual(result.measurements["triangles"], written["triangles"])
        self.assertEqual((0, 0), (written["open_edges"], written["non_manifold_edges"]))

    def test_a_value_given_moves_the_part_and_the_volume_it_is_held_to(self) -> None:
        from cad.omega import mesh

        result = mesh(self.model("ball", BALL), self.folder / "big.glb", define=("r=12",), depth=6)
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("r = 12;\n", result.measurements["defs"])
        self.assertAlmostEqual(4 / 3 * np.pi * 12 ** 3, result.measurements["volume_mm3"], delta=60.0)
        low, high = result.measurements["field_volume_mm3"]
        self.assertLess(low, 4 / 3 * np.pi * 12 ** 3)
        self.assertGreater(high, 4 / 3 * np.pi * 12 ** 3)

    def test_the_same_model_and_values_are_meshed_once(self) -> None:
        from cad.omega import _mesh, mesh

        model = self.model("ball", BALL)
        first = mesh(model, self.folder / "a.glb", depth=6)
        with mock.patch.object(_mesh, "_meshed", side_effect=AssertionError("meshed again")):
            again = mesh(model, self.folder / "b.glb", depth=6)
        self.assertTrue(again.ok, again.findings)
        self.assertTrue(again.measurements["cached"])
        self.assertEqual((self.folder / "a.glb").read_bytes(), (self.folder / "b.glb").read_bytes())
        self.assertEqual(first.measurements["volume_mm3"], again.measurements["volume_mm3"])
        # Another value, another depth and an edit are each another mesh.
        for changed in ({"define": ("r=9",)}, {"depth": 5}):
            self.assertFalse(mesh(model, **({"depth": 6} | changed)).measurements["cached"], changed)
        model.write_text(BALL.replace("r = 8.0", "r = 7.0"), encoding="utf-8")
        self.assertFalse(mesh(model, depth=6).measurements["cached"])

    def test_with_no_file_named_the_mesh_is_where_it_is_kept(self) -> None:
        from cad.omega import mesh

        result = mesh(self.model("ball", BALL), depth=6)
        self.assertTrue(result.ok, result.findings)
        kept = Path(result.measurements["glb"])
        self.assertTrue(kept.is_file())
        self.assertEqual(self.folder / "cache" / "omega", kept.parent)

    def test_a_part_that_leaves_its_scene_is_refused_and_nothing_is_written_or_kept(self) -> None:
        from cad.omega import mesh

        out = self.folder / "cut.glb"
        model = self.model("ball", "@scene(40)\nr = 8.0;\nball = length(p) - r;\nreturn ball;\n")
        result = mesh(model, out, define=("r=25",), depth=6)
        self.assertFalse(result.ok)
        self.assertIn("cut_off", self.codes(result))
        self.assertFalse(out.exists())
        self.assertEqual([], list((self.folder / "cache" / "omega").glob("*.glb")))
        # A refusal is not remembered as a mesh: asked again, it is judged again.
        self.assertFalse(mesh(model, out, define=("r=25",), depth=6).ok)

    def test_a_value_outside_its_slider_s_range_is_refused_in_gsl_s_words(self) -> None:
        from cad.omega import mesh

        result = mesh(self.model("ball", BALL), define=("r=25",), depth=6)
        self.assertEqual({"compile_failed"}, self.codes(result))
        self.assertIn("outside range [2, 15]", result.findings[0].message)

    def test_a_model_without_scene_and_a_value_that_is_no_number_are_refused_before_gsl_runs(self) -> None:
        from cad.omega import _mesh, mesh

        with mock.patch.object(_mesh, "_meshed", side_effect=AssertionError("gsl ran")):
            bare = mesh(self.model("bare", "return sphere(8);\n"))
            self.assertEqual({"no_scene"}, self.codes(bare))
            bad = mesh(self.model("ball", BALL), define=("r=wide",))
            self.assertEqual({"bad_define"}, self.codes(bad))

    def test_a_model_gsl_refuses_is_said_in_gsl_s_words(self) -> None:
        from cad.omega import mesh

        result = mesh(self.model("broken", "@scene(40)\nreturn nothing_named_this(p);\n"))
        self.assertFalse(result.ok)
        self.assertEqual({"compile_failed"}, self.codes(result))
        self.assertIn("nothing_named_this", " ".join(finding.message for finding in result.findings))


@unittest.skipUnless(HAS_OMEGA, "needs omega-core (cad[omega]: macOS and Linux)")
class OlderGsl(unittest.TestCase):
    def test_a_gsl_whose_eval_does_not_mesh_is_named_with_what_to_do(self) -> None:
        import omega_core

        from cad.omega import _mesh, mesh

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(Path(folder) / "cache")}), \
                mock.patch.object(_mesh, "_meshed", side_effect=omega_core.EvalError(
                    'op "mesh": one of eval, extremum, certify, bounds, surface, volume, describe or render')):
            model = Path(folder) / "ball.gsl"
            model.write_text(BALL, encoding="utf-8")
            result = mesh(model)
        self.assertFalse(result.ok)
        self.assertEqual(["gsl_cannot_mesh"], [finding.code for finding in result.findings])
        self.assertIn("CAD_GSL", result.findings[0].hint or "")


if __name__ == "__main__":
    unittest.main()
