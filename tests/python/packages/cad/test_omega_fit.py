"""``cad gsl fit`` and ``cad gsl bake``: exact parts held to a GSL concept's field, with no mesh of the concept.

The sampling of a GLB's surfaces, the distance from points to triangles and the grouping of changed points into
regions are numpy alone and tested everywhere. What scores points with omega's evaluator needs the omega-core wheel
(requirements-dev.txt installs it on macOS and Linux): those tests skip, by name, where it is absent. Every concept
and every exact part is written by the test into a temporary folder, the exact parts as GLBs, so no engine runs.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

HAS_OMEGA = importlib.util.find_spec("omega_core") is not None
NEEDS_OMEGA = "needs omega-core (cad[omega]: macOS and Linux)"

# A box's eight corners (signs) and its twelve triangles.
_CORNERS = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=np.float64)
_FACES = np.array([[0, 1, 3], [0, 3, 2], [4, 6, 7], [4, 7, 5], [0, 4, 5], [0, 5, 1],
                   [2, 3, 7], [2, 7, 6], [0, 2, 6], [0, 6, 4], [1, 5, 7], [1, 7, 3]])


def box(half: tuple[float, float, float], at: tuple[float, float, float] = (0.0, 0.0, 0.0)):
    """A box's points (mm) and triangles."""
    return _CORNERS * np.asarray(half) + np.asarray(at), _FACES


def write_glb(path: Path, bodies: dict[str, tuple[np.ndarray, np.ndarray]]) -> Path:
    """A binary glTF of named bodies, ``name -> (points (n, 3) mm, triangles (t, 3))``, Z up, as the engine writes
    one (``extras.cadUpAxis``; metres)."""
    blob = b""
    views, accessors, meshes, nodes = [], [], [], []
    for index, (name, (points, triangles)) in enumerate(bodies.items()):
        for data, kind, component in ((np.asarray(points, np.float64) / 1000.0, "VEC3", 5126),
                                      (np.asarray(triangles).reshape(-1), "SCALAR", 5125)):
            data = np.asarray(data, "<f4" if component == 5126 else "<u4")
            views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": data.nbytes})
            accessors.append({"bufferView": len(views) - 1, "componentType": component, "type": kind,
                              "count": int(len(data))})
            blob += data.tobytes()
        meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": 2 * index}, "indices": 2 * index + 1}]})
        nodes.append({"mesh": index, "name": name, "extras": {"cadUpAxis": "z"}})
    document = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(blob)}], "bufferViews": views,
                           "accessors": accessors, "meshes": meshes, "nodes": nodes,
                           "scenes": [{"nodes": list(range(len(nodes)))}], "scene": 0}).encode()
    document += b" " * (-len(document) % 4)
    blob += b"\0" * (-len(blob) % 4)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 28 + len(document) + len(blob))
                     + struct.pack("<I4s", len(document), b"JSON") + document
                     + struct.pack("<I4s", len(blob), b"BIN\0") + blob)
    return path


class Sampling(unittest.TestCase):
    def test_points_lie_on_each_part_and_number_about_the_density_times_its_area(self) -> None:
        from cad.omega._fit import sample

        with tempfile.TemporaryDirectory() as folder:
            glb = write_glb(Path(folder) / "two.glb", {"a": box((5, 5, 5)), "b": box((2, 3, 4), (20, 0, 0))})
            sampled = sample(glb, density=4.0)
        self.assertEqual(["a", "b"], sampled.names)
        a = sampled.points[sampled.part == 0]
        self.assertTrue(np.allclose(np.max(np.abs(a), axis=1), 5.0, atol=1e-4))  # every point on a face
        self.assertAlmostEqual(600 * 4.0, len(a) - 8, delta=600 * 4.0 * 0.1)  # 600 mm2 of surface, and 8 vertices
        b = sampled.points[sampled.part == 1] - [20, 0, 0]
        self.assertTrue(np.allclose(np.max(np.abs(b) / [2, 3, 4], axis=1), 1.0, atol=1e-4))
        self.assertEqual((12 * 2, 3, 3), sampled.triangles.shape)

    def test_the_same_file_gives_the_same_points(self) -> None:
        from cad.omega._fit import sample

        with tempfile.TemporaryDirectory() as folder:
            glb = write_glb(Path(folder) / "one.glb", {"a": box((5, 5, 5))})
            self.assertTrue(np.array_equal(sample(glb).points, sample(glb).points))


class Distances(unittest.TestCase):
    def test_a_point_off_a_face_an_edge_and_a_corner_is_measured_to_each(self) -> None:
        from cad.omega._fit import distance_to_triangles

        points, faces = box((1, 1, 1))
        triangles = points[faces]
        probes = np.array([[0.2, 0.3, 3.0], [2.0, 2.0, 0.0], [2.0, 3.0, 3.0], [0.0, 0.0, 0.5], [40.0, 0.0, 0.0]])
        want = [2.0, np.sqrt(2.0), np.sqrt(1 + 4 + 4), 0.5, 39.0]
        self.assertTrue(np.allclose(want, distance_to_triangles(probes, triangles), atol=1e-9))


class Regions(unittest.TestCase):
    def test_points_far_apart_are_two_regions_and_near_ones_one(self) -> None:
        from cad.omega._fit import _regions

        near = np.array([[0, 0, 0], [0.5, 0, 0], [1.5, 0.5, 0], [3.0, 0, 0]], dtype=np.float64)
        far = near + [30, 0, 0]
        regions = _regions(np.concatenate([near, far]))
        self.assertEqual([[0, 1, 2, 3], [4, 5, 6, 7]], sorted(sorted(int(i) for i in r) for r in regions))
        self.assertEqual([], _regions(np.zeros((0, 3))))


# A closed box 30 mm a side, its walls 2 thick: the cavity is |x|, |y|, |z| < 13.
ENCLOSURE = ("@scene(60)\nouter = max(abs(p.x) - 15.0, abs(p.y) - 15.0, abs(p.z) - 15.0);\n"
             "enclosure = max(outer, -(outer + 2.0));\nreturn enclosure;\n")
CONCEPT = "@scene(40)\n@range(5, 15) w = 10.0;\nblock = max(abs(p.x) - w, abs(p.y) - 10.0, abs(p.z) - 5.0);\nreturn block;\n"


@unittest.skipUnless(HAS_OMEGA, NEEDS_OMEGA)
class Fit(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        self.concept = self.folder / "enclosure.gsl"
        self.concept.write_text(ENCLOSURE, encoding="utf-8")

    def fit(self, bodies, **options):
        from cad.gsl import fit

        return fit(self.concept, str(write_glb(self.folder / "exact.glb", bodies)), **options)

    def test_a_part_on_the_floor_is_clear_and_touches_where_it_is_meant_to(self) -> None:
        # A block 20 x 20 x 10 standing on the cavity's floor (z = -13): 3 mm from each side wall.
        result = self.fit({"block": box((10, 10, 5), (0, 0, -8))}, contact=("0,0,-13",))
        self.assertTrue(result.ok, result.findings)
        (row,) = result.measurements["parts"]
        self.assertEqual(("block", 0, 0.0), (row["part"], row["in_wall"], round(row["clearance_mm"], 4)))
        self.assertEqual(0.0, result.measurements["contacts"][0]["gap_mm"])

    def test_a_contact_the_part_does_not_make_fails_where_clearance_alone_passes(self) -> None:
        result = self.fit({"block": box((10, 10, 5), (0, 0, -6))}, contact=("0,0,-11",))  # 2 mm off the floor
        self.assertFalse(result.ok)
        self.assertEqual(["no_contact"], [finding.code for finding in result.findings])
        self.assertAlmostEqual(2.0, result.measurements["contacts"][0]["gap_mm"], places=3)

    def test_a_part_through_the_wall_is_interference_by_its_depth(self) -> None:
        result = self.fit({"long": box((14, 5, 5))})  # 1 mm into each 2 mm side wall
        self.assertFalse(result.ok)
        self.assertEqual(["interference"], [finding.code for finding in result.findings])
        self.assertAlmostEqual(-1.0, result.measurements["parts"][0]["clearance_mm"], places=3)

    def test_a_contact_away_from_every_part_is_said_so(self) -> None:
        result = self.fit({"block": box((10, 10, 5), (0, 0, -8))}, contact=("0,0,12",))
        self.assertEqual(["contact_off_part"], [finding.code for finding in result.findings])


@unittest.skipUnless(HAS_OMEGA, NEEDS_OMEGA)
class Bake(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))
        self.concept = self.folder / "block.gsl"
        self.concept.write_text(CONCEPT, encoding="utf-8")
        self.exact = str(write_glb(self.folder / "block.glb", {"block": box((10, 10, 5))}))

    def test_an_exact_bake_departs_by_nothing_both_ways_and_keeps_the_concept(self) -> None:
        from cad.gsl import bake

        result = bake(self.concept, self.exact)
        self.assertTrue(result.ok, result.findings)
        self.assertLess(result.measurements["parts"][0]["max_mm"], 1e-3)
        self.assertGreater(result.measurements["reverse"]["points"], 100)
        self.assertLess(result.measurements["reverse"]["max_mm"], 1e-3)
        kept = self.folder / "block.baked.gsl"
        self.assertEqual(kept.resolve(), Path(result.measurements["record"]).resolve())
        self.assertIn(CONCEPT, kept.read_text(encoding="utf-8"))

    def test_a_concept_changed_since_its_bake_is_stale_where_it_moved_and_not_after_it_is_put_back(self) -> None:
        from cad.gsl import bake

        self.assertTrue(bake(self.concept, self.exact).ok)
        self.assertTrue(bake(self.concept, self.exact, stale=True).ok)
        self.concept.write_text(CONCEPT.replace("w = 10.0", "w = 11.0"), encoding="utf-8")
        stale = bake(self.concept, self.exact, stale=True)
        self.assertFalse(stale.ok)
        self.assertEqual(["stale", "stale"], [finding.code for finding in stale.findings])  # the two end faces
        regions = stale.measurements["parts"][0]["regions"]
        self.assertEqual([-1.0, -1.0], [region["change_mm"] for region in regions])  # grown 1 mm at each
        self.assertEqual({-10.0, 10.0}, {region["min"][0] for region in regions})
        self.concept.write_text(CONCEPT, encoding="utf-8")
        self.assertTrue(bake(self.concept, self.exact, stale=True).ok)

    def test_a_value_given_at_the_bake_is_kept_with_it(self) -> None:
        from cad.gsl import bake

        wide = str(write_glb(self.folder / "wide.glb", {"block": box((12, 10, 5))}))
        self.assertTrue(bake(self.concept, wide, define=("w=12",), max_deviation=1e-3).ok)
        self.assertTrue(bake(self.concept, wide, stale=True, define=("w=12",)).ok)
        self.assertFalse(bake(self.concept, wide, stale=True).ok)  # w = 10 now: the concept is 2 mm shorter

    def test_a_bake_past_its_deviation_fails_and_keeps_nothing(self) -> None:
        from cad.gsl import bake

        long = str(write_glb(self.folder / "long.glb", {"block": box((12, 10, 5))}))
        result = bake(self.concept, long, max_deviation=0.5)
        self.assertEqual(["deviation"], [finding.code for finding in result.findings])
        self.assertFalse((self.folder / "block.baked.gsl").exists())

    def test_staleness_without_a_bake_is_said_so(self) -> None:
        from cad.gsl import bake

        self.assertEqual(["no_record"], [f.code for f in bake(self.concept, self.exact, stale=True).findings])


class Registered(unittest.TestCase):
    def test_fit_and_bake_are_gsl_operations_of_the_omega_integration(self) -> None:
        from cad.registry import DOCUMENT_TYPES

        gsl = DOCUMENT_TYPES["gsl"]
        self.assertEqual(("validate", "mesh", "fit", "bake"), gsl.operation_names)
        self.assertEqual({"omega"}, {gsl.operation(name).integration for name in ("fit", "bake")})


if __name__ == "__main__":
    unittest.main()
