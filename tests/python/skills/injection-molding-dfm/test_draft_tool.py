#!/usr/bin/env python3

"""Measurement tests for the injection-molding draft tool.

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

import draft_tool  # noqa: E402


def _stl(part, tmp: Path, name: str) -> str:
    path = tmp / f"{name}.stl"
    export_stl(part, str(path))
    return str(path)


def _drafted_box(draft_deg: float, base: float = 20.0, height: float = 15.0):
    """Four side walls leaning inward by draft_deg; top and bottom flat."""
    top = base - 2 * height * math.tan(math.radians(draft_deg))
    return loft([Plane.XY * Rectangle(base, base), Plane.XY.offset(height) * Rectangle(top, top)])


def _z(mesh):
    return draft_tool._draft_facts(mesh, np.array([0.0, 0.0, 1.0]), 45.0, 0.05)


class PullVectorTest(unittest.TestCase):
    def test_axis_names_and_components_normalise(self) -> None:
        np.testing.assert_allclose(draft_tool._pull_vector("z"), [0, 0, 1])
        np.testing.assert_allclose(draft_tool._pull_vector("-y"), [0, -1, 0])
        np.testing.assert_allclose(draft_tool._pull_vector("0,0,2"), [0, 0, 1])
        with self.assertRaises(ValueError):
            draft_tool._pull_vector("0,0,0")
        with self.assertRaises(ValueError):
            draft_tool._pull_vector("1,2")


class StraightBoxTest(unittest.TestCase):
    def test_all_four_sides_are_zero_draft_walls_and_the_ends_are_not(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = draft_tool._load(_stl(Box(20, 20, 15), Path(td), "box"))
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
            mesh = draft_tool._load(_stl(Box(20, 20, 15), Path(td), "box"))
            facts = draft_tool._draft_facts(mesh, np.array([1.0, 0.0, 0.0]), 45.0, 0.05)

        self.assertAlmostEqual(facts["wall_area_mm2"], 2 * 20 * 15 + 2 * 20 * 20, delta=0.5)


class DraftedBoxTest(unittest.TestCase):
    def test_measured_draft_matches_constructed_draft(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mesh = draft_tool._load(_stl(_drafted_box(2.0), Path(td), "draft2"))
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
            one = _z(draft_tool._load(_stl(_drafted_box(1.0), tmp, "d1")))
            three = _z(draft_tool._load(_stl(_drafted_box(3.0), tmp, "d3")))

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
            s = _z(draft_tool._load(_stl(straight, tmp, "bore")))
            t = _z(draft_tool._load(_stl(tapered, tmp, "taper")))

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
            mesh = draft_tool._load(_stl(_drafted_box(2.0), Path(td), "draft2"))
            facts = draft_tool._pull_facts(mesh, 45.0, 0.05)

        by = {c["pull"]: c for c in facts["candidates"]}
        self.assertEqual(sorted(by), ["x", "y", "z"])
        self.assertEqual(by["z"]["zero_draft_wall_area_mm2"], 0.0)
        # Under an X pull the flat top and bottom become zero-draft walls.
        self.assertGreater(by["x"]["zero_draft_wall_area_mm2"], 0.0)
        self.assertGreater(by["y"]["zero_draft_wall_area_mm2"], 0.0)
        self.assertAlmostEqual(by["z"]["min_wall_draft_deg"], 2.0, delta=0.01)


if __name__ == "__main__":
    unittest.main()
