#!/usr/bin/env python3

"""Measurement tests for the injection-molding tool.

Each part is built with build123d so the correct answer is known from the
construction: a wall lofted at 2 deg reads 2 deg because it was built that
way, and a straight box has no draft anywhere. A regression shows up as a
disagreement with the model, not as a diff against a recorded run.
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
from build123d import Align, Box, Cone, Cylinder, Plane, Pos, Rectangle, export_stl, loft

from tests.python.support.paths import add_repo_path

add_repo_path("skills/injection-molding-dfm/scripts")

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
        self.assertEqual(sorted(by), ["x", "y", "z"])
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


class WallThicknessTest(unittest.TestCase):
    def test_measured_wall_matches_constructed_wall(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(_hollow_box(2.0), Path(td), "wall2"))
            facts = mold_tool._wall_facts(mesh, samples=800)

        self.assertAlmostEqual(facts["median_mm"], 2.0, delta=0.4)
        self.assertEqual(facts["body_count"], 1)
        self.assertEqual(len(facts["thickest_samples"]), 8)

    def test_a_thick_boss_shows_in_the_thick_tail(self) -> None:
        """A 2 mm shell with a solid 10 mm boss: the boss is the max, not the median."""
        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = _hollow_box(2.0) + Pos(0, 0, 2) * Cylinder(5, 10, align=align)
        with tempfile.TemporaryDirectory() as td:
            mesh = mold_tool._load(_stl(part, Path(td), "boss"))
            facts = mold_tool._wall_facts(mesh, samples=1500)

        self.assertAlmostEqual(facts["median_mm"], 2.0, delta=0.5)
        self.assertGreater(facts["max_mm"], 8.0)
        self.assertGreater(facts["max_to_median_ratio"], 3.0)


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


if __name__ == "__main__":
    unittest.main()
