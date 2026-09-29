"""cadgen.implicit: parts as signed distance fields.

Contracts pinned here: primitives are exact distances; booleans are min/max
arithmetic with the leaf that owns each point tracked through them; the
contour is watertight, outward-facing and volume-accurate to the grid; the
GLB is Y-up with one node per leaf and the STL is a valid binary STL; the
tape round-trips a tree exactly and refuses a custom field; the @part
decorator writes what it declares (and composes inside another part); and
the two verbs mirror as generated CLIs over a saved tape.
"""

from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import numpy as np

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import implicit as im  # noqa: E402
from cadgen._internal.implicit import field as engine  # noqa: E402
from cadgen._internal.implicit.tape import read_tape, write_tape  # noqa: E402

REPO = Path(__file__).resolve().parents[4]


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "packages" / "cadgen" / "src")
    env["CADGEN_DAEMON"] = "0"
    return env


class Primitives(unittest.TestCase):
    def test_primitives_are_exact_distances(self) -> None:
        cases = [
            (im.sphere(10), (15, 0, 0), 5.0),
            (im.sphere(10), (0, 0, 0), -10.0),
            (im.box((20, 10, 6)), (15, 0, 0), 5.0),
            (im.box((20, 10, 6)), (0, 0, 0), -3.0),
            (im.box((20, 10, 6)), (13, 9, 0), 5.0),  # a corner: the diagonal
            (im.cylinder(5, 10), (8, 0, 0), 3.0),
            (im.cylinder(5, 10), (0, 0, 9), 4.0),
            (im.capsule((0, 0, -5), (0, 0, 5), 2), (0, 0, 9), 2.0),
            (im.torus(10, 3), (10, 0, 5), 2.0),
            (im.cone(5, 5, 10), (8, 0, 0), 3.0),  # a cylinder in disguise
            (im.extrude(im.rect(20, 10), 6), (15, 0, 0), 5.0),
            (im.extrude(im.circle(5), 10), (0, 0, 9), 4.0),
            (im.revolve(im.polygon([(5, -5), (9, -5), (9, 5), (5, 5)])), (12, 0, 0), 3.0),
            (im.half_space((0, 0, 1), (0, 0, 2)), (0, 0, 5), -3.0),  # the normal's side is inside
            (im.half_space((0, 0, 1), (0, 0, 2)), (0, 0, -1), 3.0),
        ]
        for field, point, expected in cases:
            with self.subTest(field=field, point=point):
                self.assertAlmostEqual(float(field.distance(point)[0]), expected, places=9)

    def test_polygon_distance_is_signed_in_either_winding(self) -> None:
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        for winding in (square, square[::-1]):
            profile = im.polygon(winding)
            q = np.array([[5.0, 5.0], [15.0, 5.0], [5.0, -2.0]])
            np.testing.assert_allclose(profile.distance(q), [-5.0, 5.0, 2.0], atol=1e-12)

    def test_rounded_box_is_the_offset_of_a_smaller_box(self) -> None:
        rounded = im.box((20, 10, 6), radius=2)
        offset = im.box((16, 6, 2)).offset(2)
        pts = np.random.default_rng(1).uniform(-15, 15, (500, 3))
        np.testing.assert_allclose(rounded.distance(pts), offset.distance(pts), atol=1e-12)

    def test_a_translated_field_can_still_be_offset(self) -> None:
        # Translate once stored its vector as ``.offset``, shadowing the method.
        cavity = im.box((20, 10, 6)).translate(0, 0, 3).offset(-2)
        self.assertAlmostEqual(float(cavity.distance((0, 0, 3))[0]), -1.0)
        self.assertAlmostEqual(float(cavity.distance((0, 0, 5))[0]), 1.0)

    def test_transforms_are_rigid_and_exact(self) -> None:
        moved = im.sphere(5).translate(10, 0, 0)
        self.assertAlmostEqual(float(moved.distance((10, 0, 0))[0]), -5.0)
        turned = im.box((20, 2, 2)).rotate(90, (0, 0, 1))
        self.assertAlmostEqual(float(turned.distance((0, 12, 0))[0]), 2.0)
        self.assertAlmostEqual(float(turned.distance((12, 0, 0))[0]), 11.0)
        scaled = im.sphere(5).scale(2)
        self.assertAlmostEqual(float(scaled.distance((12, 0, 0))[0]), 2.0)
        mirrored = im.sphere(2).translate(10, 0, 0).mirror("x")
        self.assertAlmostEqual(float(mirrored.distance((-10, 0, 0))[0]), -2.0)
        grid = im.sphere(1).repeat((10, 10, 10), (3, 1, 1))
        self.assertAlmostEqual(float(grid.distance((10, 0, 0))[0]), -1.0)
        self.assertAlmostEqual(float(grid.distance((20, 0, 0))[0]), 9.0)  # only three copies
        self.assertAlmostEqual(float(im.box(10).shell(2).distance((0, 0, 0))[0]), 4.0)

    def test_bounds_are_conservative(self) -> None:
        part = (im.box((20, 10, 6)) | im.sphere(4).translate(15, 0, 0)).rotate(30) - im.cylinder(2, 50)
        rng = np.random.default_rng(2)
        pts = rng.uniform(-40, 40, (20000, 3))
        inside = pts[part.contains(pts)]
        lo, hi = np.asarray(part.bounds.min), np.asarray(part.bounds.max)
        self.assertTrue(((inside >= lo - 1e-9) & (inside <= hi + 1e-9)).all())
        with self.assertRaisesRegex(ValueError, "bounds"):
            im.contour(im.half_space())


class Booleans(unittest.TestCase):
    def test_booleans_are_min_max_arithmetic(self) -> None:
        a, b = im.sphere(5), im.sphere(5).translate(6, 0, 0)
        pts = np.random.default_rng(3).uniform(-10, 15, (300, 3))
        da, db = a.distance(pts), b.distance(pts)
        np.testing.assert_allclose((a | b).distance(pts), np.minimum(da, db))
        np.testing.assert_allclose((a & b).distance(pts), np.maximum(da, db))
        np.testing.assert_allclose((a - b).distance(pts), np.maximum(da, -db))
        np.testing.assert_allclose(im.union(a, b).distance(pts), np.minimum(da, db))

    def test_a_point_knows_which_leaf_owns_it(self) -> None:
        body = im.box(20).named("body")
        bore = im.cylinder(3, 30).named("bore")
        part = body - bore
        _, owner = part.evaluate([(0, 0, 0), (9.9, 9.9, 0), (2.9, 0, 0)])
        names = [engine.leaves(part)[i].label for i in owner]
        self.assertEqual(names, ["bore", "body", "bore"])

    def test_named_reaches_every_unnamed_leaf_beneath(self) -> None:
        part = (im.box(4) | im.sphere(3).translate(5, 0, 0)).named("pair") | im.sphere(1).named("dot")
        self.assertEqual([leaf.label for leaf in engine.leaves(part)], ["pair", "pair", "dot"])
        moved = im.cylinder(1, 2).translate(3, 0, 0).named("pin")
        self.assertEqual(engine.leaves(moved)[0].label, "pin")

    def test_a_leaf_remembers_where_it_was_written(self) -> None:
        leaf = im.sphere(1)
        self.assertRegex(leaf.site or "", r"test_implicit\.py:\d+")

    def test_round_union_bridges_a_gap_and_chamfer_bevels(self) -> None:
        a, b = im.box((10, 10, 10)), im.box((10, 10, 10)).translate(12, 0, 0)
        gap = np.array([[6.0, 0.0, 0.0]])
        self.assertGreater(float((a | b).distance(gap)[0]), 0.0)
        self.assertLess(float(im.union(a, b, round=6).distance(gap)[0]), 0.0)
        self.assertGreaterEqual(float(im.union(a, b, round=4).distance(gap)[0]), 0.0)  # a 4 mm blend fills k/4 = 1 mm: just not
        self.assertLess(float(im.union(a, b, chamfer=4).distance(gap)[0]), 0.0)
        with self.assertRaises(ValueError):
            im.union(a, b, round=1, chamfer=1)


class Contouring(unittest.TestCase):
    def _closed_and_outward(self, mesh) -> None:
        tris = mesh.triangles
        edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
        directed = {(int(a), int(b)) for a, b in edges}
        self.assertEqual(len(directed), len(edges), "no directed edge repeats")
        for a, b in list(directed)[:2000]:
            self.assertIn((b, a), directed, "every edge has its twin: the mesh is closed and consistently wound")
        v = mesh.vertices[tris]
        face_n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
        centroid = v.mean(axis=1) - mesh.vertices.mean(axis=0)
        self.assertGreater(float((np.einsum("ij,ij->i", face_n, centroid) > 0).mean()), 0.97, "faces point outward")

    def test_a_sphere_meshes_to_its_volume_and_area(self) -> None:
        # crease_deg=0 keeps vertices welded, which the closed-mesh check needs.
        mesh = im.contour(im.sphere(10), resolution=0.4, crease_deg=0)
        self.assertAlmostEqual(mesh.volume(), 4 / 3 * math.pi * 1000, delta=0.005 * 4188)
        self.assertAlmostEqual(mesh.area(), 4 * math.pi * 100, delta=0.005 * 1256)
        self._closed_and_outward(mesh)
        d = im.sphere(10).distance(mesh.vertices[: len(mesh.vertices) // 2])
        self.assertLess(float(np.abs(d).max()), 0.02, "vertices lie on the surface")

    def test_a_box_keeps_its_edges_sharp(self) -> None:
        mesh = im.contour(im.box((20, 10, 6)), resolution=0.37, crease_deg=0)
        np.testing.assert_allclose(mesh.vertices.min(axis=0), [-10, -5, -3], atol=1e-6)
        np.testing.assert_allclose(mesh.vertices.max(axis=0), [10, 5, 3], atol=1e-6)
        self.assertAlmostEqual(mesh.volume(), 1200.0, delta=1.0)
        self.assertAlmostEqual(mesh.area(), 760.0, delta=3.0)
        self._closed_and_outward(mesh)

    def test_triangles_and_vertices_carry_their_leaf(self) -> None:
        part = im.box(20).named("body") - im.cylinder(3, 30).named("bore")
        mesh = im.contour(part, resolution=0.5)
        self.assertEqual(sorted(set(mesh.triangle_leaf.tolist())), [0, 1])
        bore = mesh.vertices[mesh.vertex_leaf == 1]
        np.testing.assert_allclose(np.hypot(bore[:, 0], bore[:, 1]), 3.0, atol=0.05)

    def test_an_empty_field_contours_to_nothing(self) -> None:
        mesh = im.contour(im.sphere(5) & im.sphere(5).translate(20, 0, 0), resolution=1.0)
        self.assertEqual(mesh.triangle_count, 0)

    def test_a_grid_too_fine_is_refused_with_a_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "raise the resolution"):
            im.contour(im.box(1000), resolution=0.5)


class Questions(unittest.TestCase):
    def test_clearance_and_interference(self) -> None:
        apart = im.clearance(im.sphere(5), im.sphere(5).translate(12, 0, 0), resolution=0.25)
        self.assertAlmostEqual(apart["clearance"], 2.0, delta=0.05)
        self.assertFalse(apart["touching"])
        overlap = im.clearance(im.sphere(5), im.sphere(5).translate(8, 0, 0), resolution=0.25)
        self.assertAlmostEqual(overlap["clearance"], -2.0, delta=0.05)
        lens = im.interference(im.sphere(5), im.sphere(5).translate(8, 0, 0), resolution=0.2)
        exact = math.pi * (4 * 5 + 8) * (2 * 5 - 8) ** 2 / 12
        self.assertAlmostEqual(lens["volume"], exact, delta=0.05 * exact)
        self.assertEqual(im.interference(im.sphere(5), im.sphere(5).translate(20, 0, 0))["volume"], 0.0)

    def test_thickness_finds_the_thin_wall(self) -> None:
        walls = im.thickness(im.box(20).shell(2), resolution=0.25)
        self.assertAlmostEqual(walls["min_thickness"], 2.0, delta=0.3)
        self.assertAlmostEqual(walls["p05_thickness"], 2.0, delta=0.3)
        self.assertAlmostEqual(walls["median_thickness"], 2.0, delta=0.3)
        self.assertAlmostEqual(walls["max_thickness"], 2.0, delta=0.3)
        # A plane cut through a sloping wall leaves a knife edge: the minimum says so, the percentile does not.
        cone_shell = im.cone(10, 6, 10).shell(1.5) - im.half_space((0, 0, -1), (0, 0, -4))
        edge = im.thickness(cone_shell, resolution=0.25)
        self.assertLess(edge["min_thickness"], 0.5)
        self.assertAlmostEqual(edge["p05_thickness"], 1.5, delta=0.4)
        plate = im.thickness(im.box((40, 40, 3)), resolution=0.25)
        self.assertAlmostEqual(plate["min_thickness"], 3.0, delta=0.3)

    def test_probe_reports_distance_inside_and_leaf(self) -> None:
        part = im.box(20).named("body") - im.cylinder(3, 30).named("bore")
        [origin, corner] = im.probe(part, [(0, 0, 0), (9, 9, 9)])
        self.assertAlmostEqual(origin["distance"], 3.0)
        self.assertFalse(origin["inside"])
        self.assertEqual(origin["leaf"], 1)
        self.assertTrue(corner["inside"])
        self.assertEqual(corner["leaf"], 0)


class BrepLeaves(unittest.TestCase):
    """A B-rep enters the field as a leaf, and leaves exactly."""

    @classmethod
    def setUpClass(cls) -> None:
        from cadgen import build123d as bd

        cls.tmp = tempfile.TemporaryDirectory()
        body = bd.Box(30, 20, 10) - bd.Cylinder(4, 20)
        cls.step = Path(cls.tmp.name) / "plate.step"
        bd.export_step(body, str(cls.step))
        cls.volume = float(body.volume)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_a_step_is_a_field_with_exact_distances(self) -> None:
        plate = im.from_step(self.step, label="plate")
        plate.prepare(0.25)
        d = plate.distance([(0, 0, 0), (16, 0, 0), (4.5, 0, 0), (0, 0, 6), (14, 9, 4), (0, 12, 0)])
        np.testing.assert_allclose(d, [4.0, 1.0, -0.5, math.sqrt(17), -1.0, 2.0], atol=0.02)  # (0,0,0) is in the bore; (0,0,6) is above the hole
        self.assertEqual(engine.leaves(plate)[0].label, "plate")
        self.assertAlmostEqual(im.contour(plate, resolution=0.3).volume(), self.volume, delta=0.01 * self.volume)

    def test_an_operation_in_the_field_leaves_as_an_exact_step(self) -> None:
        slotted = im.from_step(self.step) - im.box((40, 4, 6)).translate(0, 0, 5).named("slot")
        mesh_volume = im.contour(slotted, resolution=0.25).volume()
        shape = im.to_brep(slotted)
        self.assertAlmostEqual(shape.volume, mesh_volume, delta=0.01 * mesh_volume)
        self.assertGreater(len(shape.faces()), 6, "the original faces survive, plus the slot's")
        shelled = im.from_step(self.step).shell(1.5)
        self.assertGreater(im.contour(shelled, resolution=0.25).triangle_count, 0, "the field shells what it is given")

    def test_a_brep_leaf_is_taped_as_its_step(self) -> None:
        part = im.from_step(self.step, label="plate") | im.sphere(3).translate(0, 0, 6)
        tape = Path(self.tmp.name) / "part.implicit.json"
        write_tape(part, tape, name="part", resolution=0.3)
        back, header = read_tape(tape)
        self.assertEqual(header["leaves"][0]["kind"], "brep")
        pts = np.random.default_rng(5).uniform(-20, 20, (500, 3))
        back.prepare(0.3)
        part.prepare(0.3)
        np.testing.assert_allclose(back.distance(pts), part.distance(pts), atol=1e-6)
        from cadgen import build123d as bd

        with self.assertRaisesRegex(ValueError, "no file|not tapeable|custom"):
            write_tape(im.from_shape(bd.Box(1, 1, 1)), Path(self.tmp.name) / "x.implicit.json", name="x", resolution=0.5)


class Tape(unittest.TestCase):
    def test_a_tree_round_trips_through_its_tape(self) -> None:
        part = (
            im.union(im.box((30, 20, 10), radius=2).named("body"), im.sphere(6).translate(-10, 0, 5), round=2)
            - im.cylinder(4, 20).translate(5, 0, 0).named("bore")
            - im.extrude(im.regular_polygon(6, 3), 30).rotate(45, (1, 0, 0))
            - im.revolve(im.polygon([(6, -2), (8, -2), (8, 2), (6, 2)])).translate(0, 8, 0)
        ).mirror("y").repeat((0, 0, 40), (1, 1, 2)).elongate(z=3).scale(1.5).shell(1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "part.implicit.json"
            write_tape(part, path, name="part", resolution=0.5)
            back, header = read_tape(path)
        pts = np.random.default_rng(4).uniform(-60, 60, (2000, 3))
        np.testing.assert_allclose(back.distance(pts), part.distance(pts), atol=1e-9)
        self.assertEqual(header["name"], "part")
        self.assertEqual([leaf["label"] for leaf in header["leaves"]][:3], ["body", "", "bore"])
        self.assertEqual(engine.leaves(back)[0].label, "body")

    def test_a_custom_field_cannot_be_taped(self) -> None:
        blob = im.custom(lambda p: np.linalg.norm(p, axis=1) - 3, ((-3, -3, -3), (3, 3, 3)))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "custom"):
                write_tape(blob, Path(tmp) / "blob.implicit.json", name="blob", resolution=0.5)
        self.assertAlmostEqual(im.contour(blob, resolution=0.2).volume(), 4 / 3 * math.pi * 27, delta=1.0)

    def test_a_foreign_json_is_refused_by_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.implicit.json"
            path.write_text('{"hello": 1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not a cadgen implicit tape"):
                read_tape(path)


PART = textwrap.dedent('''\
    from cadgen import implicit as im


    @im.part(out=["../GLB/housing.glb", "../STL/housing.stl"], resolution=0.5)
    def housing():
        body = im.box((30, 30, 20), radius=2).named("body")
        bore = im.cylinder(radius=8, height=40).named("bore")
        return body - bore


    if __name__ == "__main__":
        housing()
''')

ASSEMBLY = textwrap.dedent('''\
    from cadgen import implicit as im
    from housing import housing


    @im.part(out="../GLB/assembly.glb", resolution=0.5)
    def assembly():
        return housing() | im.sphere(4).translate(0, 0, 14).named("cap")


    if __name__ == "__main__":
        assembly()
''')


def _read_glb(path: Path) -> tuple[dict, bytes]:
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF" and version == 2 and length == len(data)
    json_len, json_type = struct.unpack_from("<II", data, 12)
    assert json_type == 0x4E4F534A
    document = json.loads(data[20 : 20 + json_len])
    bin_len, bin_type = struct.unpack_from("<II", data, 20 + json_len)
    assert bin_type == 0x004E4942
    return document, data[28 + json_len : 28 + json_len + bin_len]


class Authoring(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "housing.py").write_text(PART, encoding="utf-8")
        (self.root / "src" / "assembly.py").write_text(ASSEMBLY, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        run = subprocess.run([sys.executable, *argv], cwd=self.root, env=_env(), capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return run

    def test_a_part_script_writes_its_meshes_and_tape(self) -> None:
        run = self._run("src/housing.py")
        glb, stl, tape = (self.root / "GLB" / "housing.glb", self.root / "STL" / "housing.stl", self.root / "GLB" / "housing.implicit.json")
        for path in (glb, stl, tape):
            self.assertTrue(path.is_file(), path)
        self.assertEqual(run.stderr.count("wrote GLB"), 2)  # the [cadgen] line and the result line
        self.assertFalse(list(self.root.rglob("*.step")))
        document, binary = _read_glb(glb)
        leaf_nodes = [n for n in document["nodes"] if "mesh" in n]
        self.assertEqual([n["name"] for n in leaf_nodes], ["body", "bore"])
        self.assertEqual({n["extras"]["cadUpAxis"] for n in leaf_nodes}, {"y"})
        self.assertEqual(leaf_nodes[0]["extras"]["implicitSite"], "housing.py:6")
        position = document["accessors"][document["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
        self.assertEqual(position["componentType"], 5126)
        # Y-up: the part's 20 mm Z extent shows on the file's Y axis.
        self.assertAlmostEqual(position["max"][1] - position["min"][1], 20.0, delta=0.01)
        self.assertAlmostEqual(position["max"][2] - position["min"][2], 30.0, delta=0.01)
        self.assertEqual(sum(view["byteLength"] for view in document["bufferViews"]) <= len(binary), True)
        header = stl.read_bytes()[:84]
        (count,) = struct.unpack_from("<I", header, 80)
        self.assertEqual(stl.stat().st_size, 84 + 50 * count)
        self.assertIn("cadgen implicit housing", header[:80].decode("ascii", "replace"))
        saved = json.loads(tape.read_text(encoding="utf-8"))
        self.assertEqual(saved["format"], "cadgen-implicit-tape")
        self.assertEqual([leaf["label"] for leaf in saved["leaves"]], ["body", "bore"])

    def test_run_flags_ride_the_scripts_argv(self) -> None:
        run = self._run("src/housing.py", "--json", "--resolution", "1.5")
        result = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertTrue(result["ok"])
        self.assertEqual(result["resolution"], 1.5)
        self.assertEqual([o["fmt"] for o in result["outputs"]], ["glb", "stl"])

    def test_a_part_called_inside_another_part_composes(self) -> None:
        self._run("src/assembly.py")
        self.assertTrue((self.root / "GLB" / "assembly.glb").is_file())
        self.assertFalse((self.root / "GLB" / "housing.glb").exists(), "the child composes; it does not build its own outputs")
        document, _ = _read_glb(self.root / "GLB" / "assembly.glb")
        self.assertEqual([n["name"] for n in document["nodes"] if "mesh" in n], ["body", "bore", "cap"])

    def test_a_wrong_return_or_output_fails_loudly(self) -> None:
        (self.root / "src" / "bad.py").write_text(
            "from cadgen import implicit as im\n\n@im.part(resolution=1)\ndef bad():\n    return 42\n\nif __name__ == '__main__':\n    bad()\n",
            encoding="utf-8",
        )
        run = subprocess.run([sys.executable, "src/bad.py"], cwd=self.root, env=_env(), capture_output=True, text=True)
        self.assertEqual(run.returncode, 1)
        self.assertIn("must return an implicit Field", run.stderr)
        (self.root / "src" / "worse.py").write_text("from cadgen import implicit as im\n\n@im.part(out='x.obj')\ndef worse():\n    return im.sphere(1)\n", encoding="utf-8")
        run = subprocess.run([sys.executable, "src/worse.py"], cwd=self.root, env=_env(), capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("an implicit part writes", run.stderr)

    def test_a_part_writes_a_step_by_default_and_faces_map_back_to_code(self) -> None:
        (self.root / "src" / "sharp.py").write_text(textwrap.dedent('''\
            from cadgen import implicit as im

            @im.part
            def sharp():
                body = im.box((30, 20, 10), radius=2).named("body")
                return body - im.cylinder(4, 20).translate(5, 0, 0).named("bore") - im.extrude(im.regular_polygon(6, 2), 20).translate(-8, 0, 0).named("socket")

            if __name__ == "__main__":
                sharp()
        '''), encoding="utf-8")
        run = self._run("src/sharp.py", "--json")
        result = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertEqual([o["fmt"] for o in result["outputs"]], ["step"], "the default output is the B-rep")
        step, tape = self.root / "src" / "sharp.step", self.root / "src" / "sharp.implicit.json"
        self.assertTrue(step.is_file() and tape.is_file())
        self.assertIn("ISO-10303-21", step.read_text(encoding="utf-8", errors="replace")[:200])
        # Every face of the STEP names the leaf, and the line, that made it.
        listed = json.loads(self._run("-m", "cadgen.cli", "implicit", "faces", "src/sharp.step", "--json").stdout)
        self.assertTrue(listed["ok"])
        labels = {face["label"] for face in listed["faces"]}
        self.assertEqual(labels, {"body", "bore", "socket"})
        bore = next(face for face in listed["faces"] if face["label"] == "bore")
        self.assertEqual(bore["surface"], "cylinder")
        self.assertRegex(bore["site"], r"sharp\.py:\d+")
        one = json.loads(self._run("-m", "cadgen.cli", "implicit", "faces", "src/sharp.step", "--ref", f"sharp.step{bore['ref']}", "--json").stdout)
        self.assertEqual([f["label"] for f in one["faces"]], ["bore"])
        # The mesh is still one build away, and its volume agrees with the STEP's.
        mesh = json.loads(self._run("-m", "cadgen.cli", "implicit", "build", "src/sharp.implicit.json", "src/sharp.glb", "--resolution", "0.3", "--json").stdout)
        self.assertTrue(mesh["ok"] and (self.root / "src" / "sharp.glb").is_file())
        facts = json.loads(self._run("-m", "cadgen.cli", "implicit", "measure", "src/sharp.implicit.json", "--resolution", "0.3", "--json").stdout)
        from cadgen import build123d as bd

        self.assertAlmostEqual(bd.import_step(str(step)).volume, facts["volume"], delta=0.01 * facts["volume"])

    def test_blends_become_fillets_or_are_refused_by_name(self) -> None:
        (self.root / "src" / "blend.py").write_text(textwrap.dedent('''\
            from cadgen import implicit as im

            @im.part(out=["../STEP/blend.step", "../GLB/blend.glb"], resolution=0.5)
            def blend():
                return im.subtract(im.box((30, 20, 10)).named("plate"), im.cylinder(4, 20).translate(5, 0, 0), round=1)

            if __name__ == "__main__":
                blend()
        '''), encoding="utf-8")
        run = self._run("src/blend.py", "--json")
        result = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertEqual([o["fmt"] for o in result["outputs"]], ["step", "glb"])
        self.assertEqual([w for w in result["warnings"] if "sharp" in w], [], "the cut edge was filleted, not dropped")
        tape = "STEP/blend.implicit.json"
        filleted = json.loads(self._run("-m", "cadgen.cli", "implicit", "build", tape, "STEP/f.step", "--json").stdout)
        sharp = json.loads(self._run("-m", "cadgen.cli", "implicit", "build", tape, "STEP/s.step", "--blends", "drop", "--json").stdout)
        self.assertTrue(any("left sharp" in w for w in sharp["warnings"]))
        from cadgen import build123d as bd

        self.assertLess(bd.import_step(str(self.root / "STEP" / "f.step")).volume, bd.import_step(str(self.root / "STEP" / "s.step")).volume, "a fillet on a cut edge removes material")
        refused = subprocess.run([sys.executable, "-m", "cadgen.cli", "implicit", "build", tape, "STEP/r.step", "--blends", "refuse"], cwd=self.root, env=_env(), capture_output=True, text=True)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("round blend has no exact B-rep", refused.stdout + refused.stderr)

    def test_a_tree_the_kernel_cannot_build_falls_back_to_a_mesh(self) -> None:
        (self.root / "src" / "blob.py").write_text(textwrap.dedent('''\
            import numpy as np
            from cadgen import implicit as im

            @im.part(resolution=0.5)
            def blob():
                return im.custom(lambda p: np.linalg.norm(p, axis=1) - 3, ((-3, -3, -3), (3, 3, 3)))

            if __name__ == "__main__":
                blob()
        '''), encoding="utf-8")
        run = self._run("src/blob.py", "--json")
        result = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertEqual([o["fmt"] for o in result["outputs"]], ["glb"])
        self.assertTrue(any("no STEP" in w for w in result["warnings"]))
        self.assertTrue((self.root / "src" / "blob.glb").is_file())

    def test_to_brep_bridges_a_field_into_build123d(self) -> None:
        part = im.box(20).shell(2) - im.half_space((0, 0, 1), (0, 0, 9))  # a 2 mm shell with its top cut off
        shape = im.to_brep(part)
        mesh_volume = im.contour(part, resolution=0.2).volume()
        self.assertAlmostEqual(shape.volume, mesh_volume, delta=0.01 * mesh_volume)
        with self.assertRaisesRegex(ValueError, "custom"):
            im.to_brep(im.custom(lambda p: np.linalg.norm(p, axis=1) - 1, ((-1, -1, -1), (1, 1, 1))))
        with self.assertRaisesRegex(ValueError, "elongate"):
            im.to_brep(im.sphere(1).elongate(z=2))

    def test_the_verbs_work_on_the_saved_tape(self) -> None:
        self._run("src/housing.py")
        tape = "GLB/housing.implicit.json"
        run = self._run("-m", "cadgen.cli", "implicit", "build", tape, "STL/fine.stl", "--resolution", "0.3", "--json")
        result = json.loads(run.stdout.strip())
        self.assertTrue(result["ok"])
        self.assertEqual(result["resolution"], 0.3)
        self.assertTrue((self.root / "STL" / "fine.stl").is_file())
        run = self._run("-m", "cadgen.cli", "implicit", "measure", tape, "--at", "0,0,0", "--at", "14,14,0", "--walls", "--json")
        facts = json.loads(run.stdout.strip())
        self.assertTrue(facts["ok"])
        expected = 30 * 30 * 20 - math.pi * 64 * 20 - (4 - math.pi) * 4 * 20 * 4 / 4
        self.assertAlmostEqual(facts["volume"], expected, delta=0.02 * expected)
        self.assertEqual([p["inside"] for p in facts["probes"]], [False, True])
        self.assertEqual(facts["probes"][0]["leaf"], 1)
        # The shortest inward ray starts at the bore rim and exits through the 2 mm
        # rounded top edge: 15 - 2 - 8 = 5 (the wall proper, lower down, is 7).
        self.assertAlmostEqual(facts["thickness"]["min_thickness"], 5.0, delta=0.5)
        human = self._run("-m", "cadgen.cli", "implicit", "measure", tape)
        self.assertIn("leaf 0: body (housing.py:6)", human.stdout)


if __name__ == "__main__":
    unittest.main()
