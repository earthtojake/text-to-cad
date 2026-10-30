"""Implicit solids (``cadgen.implicit.solid``): a field the model's own code writes, sampled on a
grid in the model's worker, contoured into a closed manifold of planar triangles and handed back
as B-rep -- a part like any other, so its document, exports and assemblies are the engine's
ordinary ones. What the grid cannot resolve is refused by name (law 17), and the B-rep is one
memo operation keyed by the samples."""

from __future__ import annotations

import math
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from cadgen.engine import build as engine_build
from cadgen.engine import document, implicit


def ball(radius: float, centre=(0.0, 0.0, 0.0)):
    centre = np.asarray(centre, dtype=float)
    return lambda points: np.linalg.norm(points - centre, axis=1) - radius


def box(half: float):
    return lambda points: np.abs(points).max(axis=1) - half


def edges_of(triangles: np.ndarray) -> np.ndarray:
    """How many triangles hold each undirected edge."""
    pairs = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
    return np.unique(pairs, axis=0, return_counts=True)[1]


class ContourTest(unittest.TestCase):
    """The contour alone, of sampled values: no kernel."""

    def sampled(self, field, low: float, high: float, cell: float) -> tuple[np.ndarray, np.ndarray, float]:
        count = int(round((high - low) / cell)) + 1
        origin = np.full(3, low)
        values = implicit._sample(field, origin, cell, (count,) * 3)
        return values, origin, cell

    def test_a_sampled_ball_contours_to_a_closed_outward_manifold_of_its_volume(self) -> None:
        vertices, triangles = implicit.contour(*self.sampled(ball(5.0), -6.5, 6.5, 0.5))
        counts = edges_of(triangles)
        self.assertEqual(set(counts.tolist()), {2}, "every edge is two triangles'")
        volume = implicit._volume(vertices, triangles)
        self.assertGreater(volume, 0, "wound outward")
        self.assertAlmostEqual(volume / (4 / 3 * math.pi * 125), 1.0, delta=0.01)
        # Every vertex is on the zero surface of the field's linear interpolant: near the sphere.
        self.assertLess(np.abs(np.linalg.norm(vertices, axis=1) - 5.0).max(), 0.05)

    def test_a_surface_through_the_samples_leaves_no_sliver_and_stays_closed(self) -> None:
        # The ball's poles and the cube's faces run through samples: a value of zero is outside,
        # a crossing is clamped off its sample, and the slivers that leaves around the sample
        # (their normals the grid's, not the surface's) are collapsed away.
        for field, low, high, cell in ((ball(5.0), -6.0, 6.0, 1.0), (box(3.0), -4.0, 4.0, 1.0)):
            values, origin, cell = self.sampled(field, low, high, cell)
            raw = implicit.contour(values, origin, cell)
            vertices, triangles = implicit.collapse(*raw, implicit.SHORT * cell)
            with self.subTest(field=field):
                self.assertLess(len(triangles), len(raw[1]))
                self.assertEqual(set(edges_of(triangles).tolist()), {2})
                pairs = np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]])
                shortest = np.linalg.norm(vertices[pairs[:, 0]] - vertices[pairs[:, 1]], axis=1).min()
                self.assertGreater(shortest, implicit.SHORT * cell / 2)
                self.assertAlmostEqual(implicit._volume(vertices, triangles), implicit._volume(*raw), delta=0.1)

    def test_each_vertex_is_where_the_field_crosses_its_edge_not_where_the_line_does(self) -> None:
        # A 2 mm tube wall at a 1.25 mm cell: the field's kink at the wall's middle sits inside
        # the diagonal edges, and the line between their samples misses the surface by a
        # quarter of a millimetre; the field's own crossing is on it.
        def wall(p):
            return np.maximum(np.abs(np.hypot(p[:, 1], p[:, 2]) - 6) - 1, np.abs(p[:, 0]) - 5)

        values, origin, cell = self.sampled(wall, -10.0, 10.0, 1.25)
        linear, _ = implicit.contour(values, origin, cell)
        refined, triangles = implicit.surface(wall, values, origin, cell)
        self.assertGreater(np.abs(wall(linear)).max(), 0.2)
        self.assertLess(np.abs(wall(refined)).max(), 0.01)
        self.assertEqual(set(edges_of(triangles).tolist()), {2})

    def test_a_triangle_the_crossings_turn_over_is_refused(self) -> None:
        # Three vertices on edges running up +z (inside below), wound clockwise seen from
        # above: the section faces down, into the part.
        lower = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]])
        vertices = lower + [0, 0, 0.5]
        with self.assertRaisesRegex(ValueError, r"the surface folds there \(1 triangles; 1 mm cell\)"):
            implicit._refuse_folded(vertices, np.array([[0, 2, 1]]), lower, lower + [0, 0, 1],
                                    np.full(3, -1.0), 1.0)
        implicit._refuse_folded(vertices, np.array([[0, 1, 2]]), lower, lower + [0, 0, 1], np.full(3, -1.0), 1.0)

    def test_a_field_is_called_a_chunk_at_a_time_padded_to_one_length(self) -> None:
        lengths = []

        def field(points):
            lengths.append(len(points))
            return np.linalg.norm(points, axis=1) - 2

        with mock.patch.object(implicit, "CHUNK", 100):
            chunked = implicit._sample(field, np.full(3, -3.0), 1.0, (7, 7, 7))
        self.assertEqual(set(lengths), {100}, "every call the same length: a tracing kernel traces once")
        whole = implicit._sample(ball(2.0), np.full(3, -3.0), 1.0, (7, 7, 7))
        np.testing.assert_array_equal(chunked, whole)


class SolidTest(unittest.TestCase):
    """``solid`` outside a build: the B-rep, and what it refuses."""

    def test_a_ball_is_one_valid_solid_of_planar_triangles(self) -> None:
        import build123d as bd
        from OCP.BRepCheck import BRepCheck_Analyzer

        made = implicit.solid(ball(5.0), bounds=((-6, -6, -6), (6, 6, 6)), cell=1.0)
        self.assertIsInstance(made, bd.Solid)
        self.assertTrue(BRepCheck_Analyzer(made.wrapped).IsValid())
        self.assertEqual({face.geom_type for face in made.faces()}, {bd.GeomType.PLANE})
        self.assertAlmostEqual(made.volume / (4 / 3 * math.pi * 125), 1.0, delta=0.03)
        # A BoundBox is bounds too.
        again = implicit.solid(ball(5.0), bounds=bd.Box(12, 12, 12).bounding_box(), cell=1.0)
        self.assertAlmostEqual(again.volume, made.volume, places=6)

    def test_a_hollow_ball_is_one_solid_with_its_void_and_two_balls_are_two_solids(self) -> None:
        import build123d as bd
        from OCP.BRepCheck import BRepCheck_Analyzer

        shell = implicit.solid(lambda p: np.abs(np.linalg.norm(p, axis=1) - 4.5) - 1.0, ((-7,) * 3, (7,) * 3), 0.5)
        self.assertIsInstance(shell, bd.Solid)
        self.assertEqual(len(shell.shells()), 2)
        self.assertTrue(BRepCheck_Analyzer(shell.wrapped).IsValid())
        self.assertAlmostEqual(shell.volume / (4 / 3 * math.pi * (5.5 ** 3 - 3.5 ** 3)), 1.0, delta=0.03)
        # A ball inside the void is a body of its own; the void stays the outer ball's.
        nested = implicit.solid(lambda p: np.minimum(np.abs(np.linalg.norm(p, axis=1) - 4.5) - 1.0,
                                                     np.linalg.norm(p, axis=1) - 2.0), ((-7,) * 3, (7,) * 3), 0.5)
        self.assertIsInstance(nested, bd.Compound)
        self.assertEqual(sorted(len(solid.shells()) for solid in nested.solids()), [1, 2])
        two = implicit.solid(lambda p: np.minimum(ball(3.0, (-5, 0, 0))(p), ball(3.0, (5, 0, 0))(p)),
                             ((-9, -4, -4), (9, 4, 4)), 0.5)
        self.assertEqual(len(two.solids()), 2)

    def test_facets_of_a_smooth_surface_meet_at_tangent_edges_and_a_crease_stays_a_feature(self) -> None:
        from cadgen.engine.mesh import FEATURE, TANGENT, mesh_shape

        def classes(shape) -> set[int]:
            """The edge classes the engine's mesher gives the part: what the viewer and the
            stills draw by."""
            return set(mesh_shape(shape.wrapped).edges[:, 3].tolist())

        self.assertEqual(classes(implicit.solid(ball(5.0), ((-6,) * 3, (6,) * 3), 1.0)), {TANGENT})
        self.assertIn(FEATURE, classes(implicit.solid(box(3.2), ((-4.5,) * 3, (4.5,) * 3), 1.0)))

    def test_what_the_grid_cannot_hold_is_refused_by_name(self) -> None:
        cases = {
            "the bounds cut the part": (ball(5.0), ((-4, -6, -6), (6, 6, 6)), 1.0),
            "nowhere inside the bounds": (lambda p: np.linalg.norm(p, axis=1) + 1, ((-6,) * 3, (6,) * 3), 1.0),
            # A wall between two planes of samples, and a gap: the cells' centres see them.
            "a wall or a feature thinner than the cell": (
                lambda p: np.maximum(np.abs(p[:, 0] - 0.5) - 0.15, np.linalg.norm(p, axis=1) - 4), ((-6,) * 3, (6,) * 3), 1.0),
            "a gap or a hole thinner than the cell": (
                lambda p: np.maximum(np.linalg.norm(p, axis=1) - 4, 0.15 - np.abs(p[:, 0] - 0.5)), ((-6,) * 3, (6,) * 3), 1.0),
            r"shape \(343, 2\)": (lambda p: p[:, :2], ((-3,) * 3, (3,) * 3), 1.0),
            "every value must be finite": (lambda p: np.where(p[:, 0] > 2, np.nan, -1.0), ((-3,) * 3, (3,) * 3), 1.0),
            "a function of points": (3.0, ((-3,) * 3, (3,) * 3), 1.0),
            "second point must exceed": (ball(1.0), ((3, -3, -3), (-3, 3, 3)), 1.0),
            "a BoundBox or two points": (ball(1.0), (1, 2, 3), 1.0),
            "positive length": (ball(1.0), ((-3,) * 3, (3,) * 3), 0.0),
            "under two cells": (ball(1.0), ((-3,) * 3, (3, 3, -2)), 1.0),
        }
        for words, (field, bounds, cell) in cases.items():
            with self.subTest(words=words), self.assertRaisesRegex(ValueError, words):
                implicit.solid(field, bounds, cell)
        with mock.patch.object(implicit, "MAX_SAMPLES", 1000), \
                self.assertRaisesRegex(ValueError, "past the 1,000 the engine samples: give a larger cell"):
            implicit.solid(ball(5.0), ((-6,) * 3, (6,) * 3), 1.0)


MODEL = """
import build123d as bd
import numpy as np

from cadgen import step, stl, xbf
from cadgen.implicit import solid

RADIUS = 5.0


def bead_field(points):
    return np.linalg.norm(points, axis=1) - RADIUS


@xbf("XBF/bead.xbf")
@stl("bead.stl")
@step("bead.step")
def bead():
    body = solid(bead_field, bounds=((-6, -6, -6), (6, 6, 6)), cell=1.0)
    body.color = bd.Color("{colour}")
    return body


@xbf("XBF/pair.xbf")
def pair():
    two = solid(lambda p: np.minimum(np.linalg.norm(p - (4, 0, 0), axis=1),
                                     np.linalg.norm(p + (4, 0, 0), axis=1)) - 3, ((-8, -4, -4), (8, 4, 4)), 1.0)
    two.label = "pair"
    return two


@xbf("XBF/mounted.xbf")
def mounted():
    plate = bd.Pos(0, 0, -8) * bd.Box(20, 20, 4)
    plate.label = "plate"
    held = bead().shape
    held.label = "bead"
    return bd.Compound(children=[plate, held], label="mounted")
"""


class BuildTest(unittest.TestCase):
    """A field model built by the engine, in process: its document, its files, an assembly with
    B-rep, and an edit that leaves the field alone keeping the B-rep and its names."""

    def setUp(self) -> None:
        from cadgen.engine.kernel import memo

        self.folder = Path(tempfile.mkdtemp(prefix="engine-implicit-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.write("#c8a46e")
        memo.clear()
        self.addCleanup(memo.clear)

    def write(self, colour: str) -> None:
        (self.folder / "bead.py").write_text(textwrap.dedent(MODEL.format(colour=colour)), encoding="utf-8")

    def built(self, name: str) -> dict:
        report = engine_build.build(self.folder / "bead.py", [name], cwd=self.folder)[-1]
        self.assertTrue(report["ok"], report)
        return report

    def test_a_field_model_is_a_document_its_exports_and_a_part_of_an_assembly(self) -> None:
        import build123d as bd

        from cadgen.engine.formats.stl import read_stl
        from cadgen.engine.reader import read_step

        self.built("bead")
        loaded = document.Loaded(self.folder / "XBF/bead.xbf")
        (part,) = loaded.prototypes
        self.assertGreater(len(part.face_names), 100)
        self.assertTrue(all(name.startswith("f:bead.body.") for name in part.face_names.values()),
                        list(part.face_names.values())[:3])
        corners = read_stl(self.folder / "bead.stl")
        self.assertEqual(len(corners), len(part.face_names), "the STL is the facets, a triangle each")
        step = read_step(self.folder / "bead.step")
        self.assertAlmostEqual(step.volume / (4 / 3 * math.pi * 125), 1.0, delta=0.03)
        report = self.built("mounted")
        self.assertEqual(report["memo"]["bodies_run"], 1, "the child bead's body replayed")
        mounted = document.Loaded(self.folder / "XBF/mounted.xbf")
        self.assertEqual(sorted(prototype.name for prototype in mounted.prototypes), ["bead", "plate"])
        # A field of two bodies is one part of two solids.
        self.built("pair")
        (pair,) = document.Loaded(self.folder / "XBF/pair.xbf").prototypes
        self.assertEqual((pair.name, len(bd.Compound(pair.shape).solids())), ("pair", 2))

    def test_an_edit_that_samples_the_same_field_keeps_the_b_rep_and_its_names(self) -> None:
        self.built("bead")
        before = dict(document.Loaded(self.folder / "XBF/bead.xbf").prototypes[0].face_names)
        self.write("#3366cc")
        report = self.built("bead")
        self.assertEqual(report["bodies"], {"bead.py::bead": "run"})
        self.assertGreaterEqual(report["memo"]["hits"], 1, report["memo"])
        self.assertEqual(dict(document.Loaded(self.folder / "XBF/bead.xbf").prototypes[0].face_names), before)

    def test_a_field_the_grid_cannot_hold_fails_the_build_by_name(self) -> None:
        source = (self.folder / "bead.py").read_text(encoding="utf-8").replace("(-6, -6, -6)", "(-4, -6, -6)")
        (self.folder / "bead.py").write_text(source, encoding="utf-8")
        (report,) = engine_build.build(self.folder / "bead.py", ["bead"], cwd=self.folder)
        self.assertFalse(report["ok"])
        self.assertIn("the bounds cut the part", str(report.get("error")))
        self.assertFalse((self.folder / "XBF/bead.xbf").exists())


if __name__ == "__main__":
    unittest.main()
