#!/usr/bin/env python3

"""Measurement tests for the injection-molding tool.

Each part is built with build123d so the correct answer is known from the
construction: a wall lofted at 2 deg reads 2 deg because it was built that
way, and a straight box has no draft anywhere. A regression shows up as a
disagreement with the model, not as a diff against a recorded run.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from build123d import Align, Axis, Box, Cone, Cylinder, Plane, Pos, Rectangle, export_stl, loft

from tests.python.support.paths import add_repo_path

add_repo_path("skills/dfm/scripts")

import mold_tool  # noqa: E402


def _stl(part, tmp: Path, name: str) -> str:
    path = tmp / f"{name}.stl"
    export_stl(part, str(path))
    return str(path)


def _drafted_box(draft_deg: float, base: float = 20.0, height: float = 15.0):
    """Four side walls leaning inward by draft_deg; top and bottom flat."""
    top = base - 2 * height * math.tan(math.radians(draft_deg))
    return loft([Plane.XY * Rectangle(base, base), Plane.XY.offset(height) * Rectangle(top, top)])


def _z(mesh):
    return mold_tool._draft_facts(mesh, np.array([0.0, 0.0, 1.0]), 45.0, 0.05)


class PullVectorTest(unittest.TestCase):
    def test_axis_names_and_components_normalise(self) -> None:
        np.testing.assert_allclose(mold_tool._pull_vector("z"), [0, 0, 1])
        np.testing.assert_allclose(mold_tool._pull_vector("-y"), [0, -1, 0])
        np.testing.assert_allclose(mold_tool._pull_vector("0,0,2"), [0, 0, 1])
        with self.assertRaises(ValueError):
            mold_tool._pull_vector("0,0,0")
        with self.assertRaises(ValueError):
            mold_tool._pull_vector("1,2")


class StraightBoxTest(unittest.TestCase):
    def test_all_four_sides_are_zero_draft_walls_and_the_ends_are_not(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(Box(20, 20, 15), Path(td), "box"))
            facts = _z(mesh)

        self.assertAlmostEqual(facts["wall_area_mm2"], 4 * 20 * 15, delta=0.5)
        self.assertAlmostEqual(facts["zero_draft_wall_area_mm2"], 4 * 20 * 15, delta=0.5)
        self.assertAlmostEqual(facts["non_wall_area_mm2"], 2 * 20 * 20, delta=0.5)
        self.assertEqual(facts["min_wall_draft"]["draft_deg"], 0.0)
        self.assertEqual(facts["min_wall_draft"]["opens_toward"], "none")
        # Four planar walls pool into four reported faces of 300 mm2 each.
        pooled = facts["largest_zero_draft_faces"]
        self.assertEqual(len(pooled), 4)
        for face in pooled:
            self.assertAlmostEqual(face["area_mm2"], 300.0, delta=0.5)
            self.assertAlmostEqual(face["extent_along_pull_mm"], 15.0, delta=0.01)

    def test_pulling_along_x_makes_the_ends_into_walls(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(Box(20, 20, 15), Path(td), "box"))
            facts = mold_tool._draft_facts(mesh, np.array([1.0, 0.0, 0.0]), 45.0, 0.05)

        self.assertAlmostEqual(facts["wall_area_mm2"], 2 * 20 * 15 + 2 * 20 * 20, delta=0.5)


class DraftedBoxTest(unittest.TestCase):
    def test_measured_draft_matches_constructed_draft(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(_drafted_box(2.0), Path(td), "draft2"))
            facts = _z(mesh)

        self.assertEqual(facts["zero_draft_wall_area_mm2"], 0.0)
        self.assertEqual(facts["largest_zero_draft_faces"], [])
        self.assertAlmostEqual(facts["min_wall_draft"]["draft_deg"], 2.0, delta=0.01)
        # Walls narrow toward +Z, so their outward normals lean toward +Z.
        self.assertEqual(facts["min_wall_draft"]["opens_toward"], "+pull")
        self.assertEqual(list(facts["wall_draft_histogram_mm2"]), ["2-3deg"])

    def test_less_draft_measures_less(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            one = _z(mold_tool._load(_stl(_drafted_box(1.0), tmp, "d1")))
            three = _z(mold_tool._load(_stl(_drafted_box(3.0), tmp, "d3")))

        self.assertLess(one["min_wall_draft"]["draft_deg"], three["min_wall_draft"]["draft_deg"])


class HoleTest(unittest.TestCase):
    def test_a_straight_bore_is_zero_draft_and_a_tapered_one_is_not(self) -> None:
        align = (Align.CENTER, Align.CENTER, Align.MIN)
        plate = Pos(0, 0, 0) * Box(30, 30, 6, align=align)
        straight = plate - Cylinder(3, 6, align=align)
        r_top = 3 + 6 * math.tan(math.radians(1.0))
        tapered = plate - Cone(3, r_top, 6, align=align)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            s = _z(mold_tool._load(_stl(straight, tmp, "bore")))
            t = _z(mold_tool._load(_stl(tapered, tmp, "taper")))

        # The bore wall is 2*pi*r*h; the outer plate sides add 4*30*6.
        self.assertAlmostEqual(s["zero_draft_wall_area_mm2"], 4 * 30 * 6 + 2 * math.pi * 3 * 6, delta=2.0)
        self.assertAlmostEqual(t["zero_draft_wall_area_mm2"], 4 * 30 * 6, delta=0.5)
        self.assertAlmostEqual(t["min_wall_draft"]["draft_deg"], 0.0, delta=0.01)
        # Everything that is not a plate side is the bore. A chord facet of a
        # cone tilts a little less than the analytic half-angle, so the bore
        # reads just under 1 deg: that is the documented per-facet limit.
        bore = 2 * math.pi * 3 * 6
        hist = t["wall_draft_histogram_mm2"]
        self.assertAlmostEqual(sum(v for k, v in hist.items() if k != "0-0.25deg"), bore, delta=3.0)
        self.assertAlmostEqual(t["drafted_wall_area_mm2"], bore, delta=3.0)
        self.assertAlmostEqual(t["drafted_wall_mean_draft_deg"], 1.0, delta=0.1)
        self.assertEqual(s["drafted_wall_area_mm2"], 0.0)


class PullsTest(unittest.TestCase):
    def test_the_lofted_pull_is_the_only_one_without_zero_draft(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(_drafted_box(2.0), Path(td), "draft2"))
            facts = mold_tool._pull_facts(mesh, 45.0, 0.05)

        by = {c["pull"]: c for c in facts["candidates"]}
        self.assertEqual(sorted(k for k in by if not k.startswith("principal")), ["x", "y", "z"])
        self.assertEqual(by["z"]["zero_draft_wall_area_mm2"], 0.0)
        # Under an X pull the flat top and bottom become zero-draft walls.
        self.assertGreater(by["x"]["zero_draft_wall_area_mm2"], 0.0)
        self.assertGreater(by["y"]["zero_draft_wall_area_mm2"], 0.0)
        self.assertAlmostEqual(by["z"]["min_wall_draft_deg"], 2.0, delta=0.01)


def _hollow_box(wall: float, outer: float = 24.0, height: float = 16.0):
    """Open-top box sitting on Z=0 with `wall` on the floor and four sides."""
    align = (Align.CENTER, Align.CENTER, Align.MIN)
    inner = outer - 2 * wall
    return Box(outer, outer, height, align=align) - Pos(0, 0, wall) * Box(inner, inner, height, align=align)


def _grooved_box():
    """20 mm cube with a 4 x 4 mm groove across one side face at mid height.

    For a Z pull the groove's upper and lower faces face each other and its
    back face is a zero-draft wall blocked both ways: all three are undercut
    candidates. Every other face withdraws freely.
    """
    align = (Align.CENTER, Align.CENTER, Align.MIN)
    cube = Box(20, 20, 20, align=align)
    groove = Pos(10, 0, 10) * Box(8, 30, 4)  # centred on the +X face, 4 mm deep
    return cube - groove


class UndercutTest(unittest.TestCase):
    def test_a_plain_box_has_no_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(Box(20, 20, 15), Path(td), "box"))
            facts = mold_tool._undercut_facts(mesh, np.array([0.0, 0.0, 1.0]), 0.05)

        self.assertEqual(facts["candidate_area_mm2"], 0.0)
        self.assertEqual(facts["largest_candidate_faces"], [])

    def test_a_side_groove_is_a_candidate_for_z_and_not_for_y(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(_grooved_box(), Path(td), "groove"))
            z = mold_tool._undercut_facts(mesh, np.array([0.0, 0.0, 1.0]), 0.05)
            y = mold_tool._undercut_facts(mesh, np.array([0.0, 1.0, 0.0]), 0.05)

        # Upper + lower groove faces (4 x 20 each) and the trapped back (4 x 20).
        self.assertAlmostEqual(z["candidate_area_mm2"], 3 * 4 * 20, delta=1.0)
        self.assertAlmostEqual(z["leaning_blocked_area_mm2"], 2 * 4 * 20, delta=1.0)
        self.assertAlmostEqual(z["trapped_zero_draft_area_mm2"], 4 * 20, delta=1.0)
        # Pulled along the groove, nothing is trapped.
        self.assertEqual(y["candidate_area_mm2"], 0.0)

    def test_a_t_shaped_lip_is_not_an_undercut(self) -> None:
        """The underside of a wider top withdraws freely toward -Z."""
        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(20, 20, 10, align=align) + Pos(0, 0, 10) * Box(30, 30, 4, align=align)
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(part, Path(td), "tee"))
            facts = mold_tool._undercut_facts(mesh, np.array([0.0, 0.0, 1.0]), 0.05)

        self.assertEqual(facts["candidate_area_mm2"], 0.0)


class ProjectionTest(unittest.TestCase):
    def test_silhouette_matches_the_box_footprint(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(Box(20, 30, 10), Path(td), "box"))
            z = mold_tool._projection_facts(mesh, np.array([0.0, 0.0, 1.0]))
            x = mold_tool._projection_facts(mesh, np.array([1.0, 0.0, 0.0]))

        self.assertAlmostEqual(z["projected_area_mm2"], 600.0, delta=12.0)
        self.assertAlmostEqual(z["depth_along_pull_mm"], 10.0, delta=0.01)
        self.assertAlmostEqual(x["projected_area_mm2"], 300.0, delta=10.0)

    def test_overlapping_features_do_not_double_count(self) -> None:
        """A boss on a plate projects to the plate area, not plate plus boss."""
        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(30, 30, 3, align=align) + Pos(0, 0, 3) * Cylinder(5, 10, align=align)
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(part, Path(td), "plateboss"))
            facts = mold_tool._projection_facts(mesh, np.array([0.0, 0.0, 1.0]))

        self.assertAlmostEqual(facts["projected_area_mm2"], 900.0, delta=15.0)


class PullsUndercutTest(unittest.TestCase):
    def test_pulls_reports_the_groove_only_off_axis(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(_grooved_box(), Path(td), "groove"))
            facts = mold_tool._pull_facts(mesh, 45.0, 0.05)

        by = {c["pull"]: c for c in facts["candidates"]}
        # The groove runs along Y and opens toward +X: only a Z pull traps it.
        self.assertEqual(by["y"]["undercut_candidate_area_mm2"], 0.0)
        self.assertEqual(by["x"]["undercut_candidate_area_mm2"], 0.0)
        self.assertAlmostEqual(by["z"]["undercut_candidate_area_mm2"], 3 * 4 * 20, delta=1.0)


# --- cases the PR review's 41-part battery found -------------------------------

class TangentCurvedFaceTest(unittest.TestCase):
    """A sphere is parallel to the pull along a LINE, not over an area.

    Tessellated, that line becomes a band of facets whose area is a property
    of the export: one sphere read 261 mm2 coarse and 67 mm2 fine. That band
    is reported apart from a flat zero-draft wall, which is a real one.
    """

    def test_a_sphere_has_no_zero_draft_wall_at_any_resolution(self) -> None:
        import trimesh

        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            areas = []
            for subdivisions in (2, 4):
                path = tmp / f"sphere{subdivisions}.stl"
                trimesh.creation.icosphere(subdivisions=subdivisions, radius=20).export(path)
                facts = _z(mold_tool._load(str(path)))
                self.assertEqual(facts["zero_draft_wall_area_mm2"], 0.0)
                areas.append(facts["zero_draft_tangent_area_mm2"])
            self.assertGreater(areas[0], 0.0, "the band exists; it is just not a wall")
            self.assertLess(areas[1], areas[0] / 2, "and it shrinks with the mesh, as an artifact does")

    def test_a_uv_spheres_vertical_equator_band_is_tangent_too(self) -> None:
        """Its band is a coplanar PAIR of triangles, so each half sees one side only."""
        import trimesh

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "uv.stl"
            trimesh.creation.uv_sphere(radius=20, count=[32, 32]).export(path)
            facts = _z(mold_tool._load(str(path)))

        self.assertEqual(facts["zero_draft_wall_area_mm2"], 0.0)
        self.assertGreater(facts["zero_draft_tangent_area_mm2"], 0.0)

    def test_a_cylinder_wall_is_a_real_zero_draft_wall(self) -> None:
        """Curved, but parallel to the pull over its whole area, not just a line."""
        align = (Align.CENTER, Align.CENTER, Align.MIN)
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(Cylinder(10, 30, align=align), Path(td), "cyl"))
            facts = _z(mesh)

        self.assertAlmostEqual(facts["zero_draft_wall_area_mm2"], 2 * math.pi * 10 * 30, delta=20.0)
        self.assertEqual(facts["zero_draft_tangent_area_mm2"], 0.0)


class MinimumDraftIsPooledTest(unittest.TestCase):
    def test_a_sliver_face_does_not_set_the_minimum(self) -> None:
        """Read off one triangle, the figure moved with the mesh.

        A 20 mm box drafted 2 deg carries a 0.5 mm square pin with NO draft on
        its top. The pin's four walls are 0.5 mm2 each, far under the area
        floor and in the sliver tail of the wall area, so the part's minimum
        wall draft is still the 2 deg its walls were built at -- while the
        per-facet reading, which is what used to be reported, is the pin's 0.
        The sliver is geometry here, not a tessellation artifact, so the
        answer does not depend on how the mesher happened to triangulate.
        """
        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = _drafted_box(2.0, base=20.0, height=15.0) + Pos(0, 0, 15) * Box(0.5, 0.5, 1.0, align=align)
        with tempfile.TemporaryDirectory() as td:
            facts = _z(mold_tool._load(_stl(part, Path(td), "pinned")))

        self.assertAlmostEqual(facts["min_wall_draft"]["draft_deg"], 2.0, delta=0.05)
        self.assertGreater(facts["min_wall_draft"]["area_mm2"], 100.0, "a wall, not a sliver")
        self.assertEqual(facts["min_facet_draft"]["draft_deg"], 0.0)
        self.assertLess(facts["min_facet_draft"]["area_mm2"], 1.0)
        # The pin's four vertical walls are real zero-draft walls, just tiny ones.
        self.assertAlmostEqual(facts["zero_draft_wall_area_mm2"], 4 * 0.5 * 1.0, delta=0.1)


class WallOpeningDirectionTest(unittest.TestCase):
    def test_walls_that_open_opposite_ways_are_reported_as_such(self) -> None:
        part = _drafted_box(2.0) + Pos(40, 0, 15) * (Pos(0, 0, 0) * _drafted_box(2.0).rotate(Axis.X, 180))
        with tempfile.TemporaryDirectory() as td:
            facts = _z(mold_tool._load(_stl(part, Path(td), "opposed")))

        opening = facts["wall_area_by_opening_mm2"]
        self.assertGreater(opening["+pull"], 0.0)
        self.assertGreater(opening["-pull"], 0.0)


class CoarseMeshUndercutTest(unittest.TestCase):
    """One ray per triangle counted whole triangles, so a CAD-coarse export
    rounded an undercut to its nearest triangle: a shelf over a plate read
    9,500 mm2 against a true 8,000. Faces are split before casting."""

    def test_a_shelf_over_a_plate_measures_its_own_area(self) -> None:
        part = (Pos(0, 0, 2.5) * Box(100, 100, 5)
                + Pos(-45, 0, 15) * Box(10, 100, 20)
                + Pos(-30, 0, 27.5) * Box(40, 100, 5))
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(part, Path(td), "shelf"))
            self.assertLess(len(mesh.faces), 100, "a CAD-coarse export: the point of the fixture")
            facts = mold_tool._undercut_facts(mesh, np.array([0.0, 0.0, 1.0]), 0.05)

        # Shelf underside 40 x 100, the plate under it 30 x 100, the post wall
        # it shadows 10 x 100: 8,000 mm2 from the construction.
        self.assertAlmostEqual(facts["candidate_area_mm2"], 8000.0, delta=200.0)

    def test_a_dovetail_slots_floor_strips_are_counted(self) -> None:
        from build123d import Polygon, extrude

        block = Pos(0, 0, 10) * Box(40, 30, 20)
        slot = extrude(Plane.XZ * Polygon((-4, 20), (4, 20), (7, 14), (-7, 14), align=None), 20, both=True)
        truth = 2 * math.hypot(3, 6) * 30 + 2 * 3 * 30  # two slanted walls, two floor strips
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(block - slot, Path(td), "dovetail"))
            facts = mold_tool._undercut_facts(mesh, np.array([0.0, 0.0, 1.0]), 0.05)

        self.assertAlmostEqual(facts["candidate_area_mm2"], truth, delta=truth * 0.05)


class MultiBodyTest(unittest.TestCase):
    def test_two_plain_plates_are_not_an_undercut_in_each_other(self) -> None:
        """An assembly STL is not one molded part; it used to read 2,400 mm2."""
        import trimesh

        lower = trimesh.creation.box(extents=(40, 30, 5))
        upper = trimesh.creation.box(extents=(40, 30, 5))
        upper.apply_translation((0, 0, 12.5))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "two.stl"
            trimesh.util.concatenate([lower, upper]).export(path)
            mesh = mold_tool._load(str(path))
            facts = mold_tool._undercut_facts(mesh, np.array([0.0, 0.0, 1.0]), 0.05)
            summary = mold_tool._mesh_facts(mesh)

        self.assertEqual(facts["candidate_area_mm2"], 0.0)
        self.assertEqual(facts["body_count"], 2)
        self.assertEqual(len(facts["per_body"]), 2)
        self.assertIn("bodies", summary["note"])


class ScaleTest(unittest.TestCase):
    def test_a_part_exported_in_metres_measures_once_its_units_are_given(self) -> None:
        """A fixed 0.25 mm raster printed area 0.0 for a 100 mm part in metres."""
        import trimesh

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "metres.stl"
            trimesh.creation.box(extents=(0.1, 0.08, 0.02)).export(path)
            mesh = mold_tool._load(str(path), units="m")
            facts = mold_tool._projection_facts(mesh, np.array([0.0, 0.0, 1.0]))

        self.assertAlmostEqual(facts["projected_area_mm2"], 100 * 80, delta=50.0)
        self.assertEqual(mold_tool._scale_hint(mesh)["declared_units"], "m")

    def test_a_two_metre_panel_coarsens_its_raster_instead_of_its_memory(self) -> None:
        import trimesh

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "panel.stl"
            trimesh.creation.box(extents=(2000, 1500, 100)).export(path)
            facts = mold_tool._projection_facts(mold_tool._load(str(path)), np.array([0.0, 0.0, 1.0]))

        self.assertAlmostEqual(facts["projected_area_mm2"], 3.0e6, delta=3.0e6 * 0.005)
        self.assertGreater(facts["raster_resolution_mm"], 0.25)

    def test_a_part_read_in_the_wrong_units_is_flagged(self) -> None:
        import trimesh

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "metres.stl"
            trimesh.creation.box(extents=(0.1, 0.08, 0.02)).export(path)
            self.assertTrue(mold_tool._scale_hint(mold_tool._load(str(path)))["units_suspect"])
            self.assertFalse(mold_tool._scale_hint(mold_tool._load(str(path), units="m"))["units_suspect"])


class OffAxisPullTest(unittest.TestCase):
    def test_pulls_offers_the_meshs_own_axes(self) -> None:
        """A 2 deg part modelled 20 deg off-axis has no good pull among x, y, z."""
        from build123d import Axis, extrude

        # A square base has two equal principal moments, so its principal frame
        # would be arbitrary in that plane; 40 x 30 is well defined.
        part = extrude(Rectangle(40, 30), 20, taper=2.0).rotate(Axis.X, 20)
        with tempfile.TemporaryDirectory() as td:
            facts = mold_tool._pull_facts(mold_tool._load(_stl(part, Path(td), "tilted")), 45.0, 0.05)

        by = {c["pull"]: c for c in facts["candidates"]}
        self.assertGreater(by["x"]["zero_draft_wall_area_mm2"], 0.0,
                           "x reads the tilted top and bottom as zero-draft walls")
        drafts = [c["min_wall_draft_deg"] for name, c in by.items()
                  if name.startswith("principal") and c["min_wall_draft_deg"] is not None]
        self.assertTrue(drafts, "the principal axes are offered")
        self.assertTrue(any(abs(d - 2.0) < 0.2 for d in drafts),
                        f"one principal axis is the axis it was drafted about; got {drafts}")


class RobustnessTest(unittest.TestCase):
    def test_a_degenerate_triangle_is_dropped_before_it_becomes_a_nan(self) -> None:
        """build123d exports a couple of zero-area triangles on any sphere, and
        their NaN normals reached the report as bare `NaN` JSON tokens."""
        import trimesh

        box = trimesh.creation.box(extents=(20, 20, 20))
        vertices = np.vstack([box.vertices, box.vertices[0], box.vertices[0]])
        faces = np.vstack([box.faces, [0, len(box.vertices), len(box.vertices) + 1]])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "degenerate.stl"
            trimesh.Trimesh(vertices=vertices, faces=faces, process=False).export(path)
            mesh = mold_tool._load(str(path))
            report = {"mesh": mold_tool._mesh_facts(mesh), "draft": _z(mesh)}

        self.assertEqual(mesh.metadata["degenerate_faces_dropped"], 1)
        json.dumps(report, allow_nan=False)  # a strict parser has to accept it

    def test_a_failed_family_marks_the_report_partial(self) -> None:
        report = {"draft": {"error": "boom"}, "undercuts": {"candidate_area_mm2": 0.0}}
        self.assertTrue(mold_tool._mark_partial(report))
        self.assertEqual(report["partial_sections"], ["draft"])
        clean = {"draft": {"wall_area_mm2": 1.0}}
        self.assertFalse(mold_tool._mark_partial(clean))
        self.assertNotIn("partial_sections", clean)

    def test_pull_accepts_a_negative_axis_and_refuses_an_empty_one(self) -> None:
        self.assertEqual(
            mold_tool._normalise_argv(["measure", "p.stl", "--pull", "-z"]),
            ["measure", "p.stl", "--pull=-z"],
        )
        np.testing.assert_allclose(mold_tool._pull_vector("-z"), [0, 0, -1])
        for bad in ("", "   ", "-"):
            with self.assertRaises(ValueError):
                mold_tool._pull_vector(bad)


class CommandLineTest(unittest.TestCase):
    def test_the_cli_runs_end_to_end_and_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code, text = _run_cli(["measure", _stl(Box(20, 20, 15), Path(td), "box"), "--pull", "-z"])

        self.assertEqual(code, 0)
        report = json.loads(text)
        self.assertFalse(report["partial"])
        self.assertEqual(sorted(k for k in report if k != "file"),
                         ["draft", "mesh", "partial", "projection", "scale", "undercuts"])
        self.assertNotIn("wall_thickness", report, "thickness is $dfam-check's measurement")
        self.assertEqual(report["draft"]["pull_axis"], [-0.0, -0.0, -1.0], "--pull -z reached argparse")

    def test_a_bad_pull_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            code, text = _run_cli(["measure", _stl(Box(20, 20, 15), Path(td), "box"), "--pull", "sideways"])

        self.assertEqual(code, 1)
        self.assertIn("error", json.loads(text))


def _run_cli(argv: list[str]) -> tuple[int, str]:
    """Run main() with stdout captured, returning its exit code and output."""
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = mold_tool.main(argv)
    return code, buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
