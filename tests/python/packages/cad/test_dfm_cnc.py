#!/usr/bin/env python3

"""The CNC check's measurements on exact geometry, family by family, on tiny parts built here: each expected
figure is the construction's (a pocket cut 12 deep is 12 deep, a 118-degree drill point is 118 degrees).
The planted-defect corpus is ``test_dfm_cnc_corpus``; this is the facts each verdict reads."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from typing import Any

import build123d as bd

import cad.step
from cad._internal import manufacturing
from cad._internal.dfm import cnc as rules_side
from cad.build123d import _dfm_cnc_holes, cnc

A = bd.Align


def _check(shape: Any, **options: Any) -> Any:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "part.step"
        bd.export_step(shape, str(path))
        return cad.step.dfm(path, process="cnc", **options)


def _part(shape: Any, label: str = "part") -> Any:
    shape.label = label
    return shape


def _drill(diameter: float, depth: float, point: float = 118.0) -> Any:
    radius = diameter / 2
    tip = radius / math.tan(math.radians(point / 2))
    body = bd.Pos(0, 0, 1) * bd.Cylinder(radius, depth + 1, align=(A.CENTER, A.CENTER, A.MAX))
    return body + bd.Pos(0, 0, -depth) * bd.Cone(0.0, radius, tip, align=(A.CENTER, A.CENTER, A.MAX))


def _pocket(length: float, width: float, depth: float, radius: float, top: float) -> Any:
    cut = bd.Box(length, width, depth + 1, align=(A.CENTER, A.CENTER, A.MIN))
    if radius > 0:
        cut = bd.fillet(cut.edges().filter_by(bd.Axis.Z), radius)
    return bd.Pos(0, 0, top - depth) * cut


def _codes(result: Any) -> set[str]:
    return {finding.code for finding in result.findings}


class HolesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        part = bd.Box(90, 30, 40)  # top at z = 20
        part -= bd.Pos(-35, 0, 20) * _drill(6.8, 15)
        part -= bd.Pos(-20, 0, 0) * bd.Cylinder(3.3, 60)
        part -= bd.Pos(-20, 0, 20.5) * bd.Cylinder(5.5, 6.5, align=(A.CENTER, A.CENTER, A.MAX))
        part -= bd.Pos(-5, 0, 0) * bd.Cylinder(2.25, 60)
        part -= bd.Pos(-5, 0, 20.25) * bd.Cone(2.25, 4.75, 2.5, align=(A.CENTER, A.CENTER, A.MAX))
        part -= bd.Pos(10, 0, 20) * bd.Cylinder(2.165, 12, align=(A.CENTER, A.CENTER, A.MAX))
        part -= bd.Pos(25, 0, 20) * _drill(25.4 / 4, 10, point=135.0)
        cls.holes = {round(h["xyz"][0]): h for h in _check(_part(part)).measurements["holes"]["items"]}

    def test_a_drilled_hole_is_blind_with_its_point(self) -> None:
        hole = self.holes[-35]
        self.assertEqual((hole["diameter_mm"], hole["depth_mm"], hole["through"], hole["bottom"]),
                         (6.8, 15.0, False, "drill_point"))
        self.assertAlmostEqual(hole["point_angle_deg"], 118.0, places=6)
        self.assertEqual((hole["standard_drill"], hole["tap_candidate"]), ("6.8 mm", "M8x1.25"))
        self.assertEqual(hole["opening"], [0.0, 0.0, 1.0])
        self.assertAlmostEqual(self.holes[25]["point_angle_deg"], 135.0, places=6)

    def test_counterbores_and_countersinks_belong_to_their_hole(self) -> None:
        bored, sunk = self.holes[-20], self.holes[-5]
        self.assertEqual((bored["diameter_mm"], bored["through"], bored["depth_mm"]), (6.6, True, 40.0))
        self.assertEqual(bored["counterbores"], [{"diameter_mm": 11.0, "depth_mm": 6.0}])
        self.assertEqual(sunk["diameter_mm"], 4.5)
        self.assertEqual(len(sunk["countersinks"]), 1)
        self.assertAlmostEqual(sunk["countersinks"][0]["angle_deg"], 90.0, places=6)
        self.assertAlmostEqual(sunk["countersinks"][0]["diameter_mm"], 9.0, places=4)

    def test_drill_sizes_are_named_from_every_series(self) -> None:
        self.assertEqual(self.holes[10]["bottom"], "flat")
        self.assertIsNone(self.holes[10]["standard_drill"])
        self.assertAlmostEqual(self.holes[10]["drill_deviation_mm"], 4.33 - 0.1695 * 25.4, places=4)  # #18
        self.assertEqual(self.holes[25]["standard_drill"], "1/4 in (6.350 mm)")
        self.assertEqual(_dfm_cnc_holes.standard_drill(0.201 * 25.4)[0], "#7 (5.105 mm)")
        self.assertEqual(_dfm_cnc_holes.standard_drill(0.257 * 25.4)[0], "letter F (6.528 mm)")
        self.assertEqual(_dfm_cnc_holes.standard_drill(10.2)[0], "10.2 mm")  # M12's tap drill, as stocked
        self.assertEqual(_dfm_cnc_holes.standard_drill(3.33)[0], None)


class PocketsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        part = bd.Box(100, 60, 30)  # top at z = 15
        part -= bd.Pos(-25, 0, 0) * _pocket(30, 20, 12, 3.0, 15)   # closed, 12 deep, 20 wide
        part -= bd.Pos(20, 0, 15 - 8) * bd.Box(4, 80, 8.01, align=(A.CENTER, A.CENTER, A.MIN))  # a 4 mm slot
        part -= bd.Pos(40, 0, 15 - 5) * bd.Box(30, 80, 5.01, align=(A.CENTER, A.CENTER, A.MIN))  # a step
        cls.result = _check(_part(part), tools="2,4")
        cls.report = cls.result.measurements

    def test_a_closed_pocket_has_its_depth_width_and_corners(self) -> None:
        closed = next(p for p in self.report["pockets"]["items"] if p["kind"] == "closed")
        self.assertEqual((closed["depth_mm"], closed["depth_from_top_mm"], closed["width_mm"]), (12.0, 12.0, 20.0))
        self.assertEqual(closed["axis"], [0.0, 0.0, 1.0])
        corners = [c for c in self.report["internal_corners"]["items"] if c["pocket"] == closed["location"]]
        self.assertEqual(len(corners), 4)
        for corner in corners:
            self.assertEqual((corner["radius_mm"], corner["height_mm"], corner["tool_mm"]), (3.0, 12.0, 4.0))
            self.assertEqual(corner["reach_ratio"], 3.0)  # 12 deep / the 4 mm tool, the largest that fits r 3
            self.assertEqual(corner["radius_to_depth"], 0.25)

    def test_slots_and_steps_are_open_pockets(self) -> None:
        kinds = sorted((p["kind"], p["width_mm"], p["depth_mm"]) for p in self.report["pockets"]["items"])
        self.assertEqual(kinds, [("closed", 20.0, 12.0), ("open", None, 5.0), ("slot", 4.0, 8.0)])

    def test_floor_roots_are_no_corners(self) -> None:
        # every floor meets its walls sharp: an end mill's corner makes that, so no edge is reported
        self.assertEqual(self.report["sharp_edges"]["items"], [])
        self.assertFalse(any(c["sharp"] for c in self.report["internal_corners"]["items"]))
        self.assertGreaterEqual(self.report["sharp_edges"]["by_tool"]["end_mill"], 8)

    def test_the_rules_follow_the_tools(self) -> None:
        self.assertIn("cnc.corner_radius_to_depth", _codes(self.result))
        tight = _check(_part(bd.Box(40, 30, 12) - _pocket(20, 14, 4, 1.0, 6)), tools="3,6")
        found = [f for f in tight.findings if f.code == "cnc.internal_corner_radius"]
        self.assertEqual(len(found), 4)
        self.assertIn("under the 1.5 mm minimum", found[0].message)

    def test_a_sharp_corner_is_radius_zero_and_once(self) -> None:
        result = _check(_part(bd.Box(40, 30, 12) - _pocket(10, 10, 4, 0.0, 6)))
        corners = result.measurements["internal_corners"]["items"]
        self.assertEqual(sorted(c["radius_mm"] for c in corners), [0.0] * 4)
        self.assertEqual(result.measurements["sharp_edges"]["items"], [])  # not reported twice
        self.assertEqual(sum(f.code == "cnc.internal_corner_sharp" for f in result.findings), 4)
        # open on one side and cut from it, the same sharp corner is a side mill's root
        step = bd.Box(40, 30, 12) - bd.Pos(15, 0, 6) * bd.Box(20, 10, 8)
        self.assertNotIn("cnc.internal_corner_sharp", _codes(_check(_part(step))))


class WallsAndGapsTest(unittest.TestCase):
    def test_wall_thickness_and_gap_width_are_exact(self) -> None:
        part = bd.Box(60, 40, 5, align=(A.CENTER, A.CENTER, A.MAX))
        for y, thickness in ((-4, 1.2), (4, 1.2)):
            part += bd.Pos(0, y, 0) * bd.Box(50, thickness, 15, align=(A.CENTER, A.CENTER, A.MIN))
        report = _check(_part(part), material="abs").measurements
        thinnest = report["walls"]["items"][0]
        self.assertAlmostEqual(thinnest["thickness_mm"], 1.2, places=6)
        self.assertAlmostEqual(thinnest["height_mm"], 15.0, places=6)
        self.assertAlmostEqual(report["gaps"]["items"][0]["width_mm"], 6.8, places=6)


class AccessTest(unittest.TestCase):
    def test_setups_are_the_fewest_directions_and_undercuts_are_located(self) -> None:
        two = bd.Box(60, 40, 30) - _pocket(30, 20, 8, 5, 15) - bd.Rot(180, 0, 0) * _pocket(30, 20, 8, 5, 15)
        setup = _check(_part(two)).measurements["setups"]["items"][0]
        self.assertEqual(setup["setup_count"], 2)
        self.assertEqual(sorted(d["direction"][2] for d in setup["directions"]), [-1.0, 1.0])
        closed = bd.Box(80, 60, 30) - bd.Pos(0, 0, 12) * bd.Box(50, 8, 6) - bd.Pos(0, 0, 6) * bd.Box(50, 20, 6)
        report = _check(_part(closed)).measurements
        undersides = [item for item in report["access"]["items"] if item["kind"] == "no_line_of_sight"]
        self.assertTrue(undersides)
        self.assertTrue(all(3 <= item["xyz"][2] <= 9 for item in undersides))
        opened = bd.Box(80, 60, 30) - bd.Pos(0, 0, 12) * bd.Box(90, 8, 6) - bd.Pos(0, 0, 6) * bd.Box(90, 20, 6)
        report = _check(_part(opened)).measurements
        self.assertEqual(report["access"]["items"], [])
        self.assertEqual(report["sharp_edges"]["items"], [])
        self.assertEqual(report["sharp_edges"]["by_tool"].get("slot_cutter"), 4)

    def test_five_axes_reach_an_inclined_hole_three_do_not(self) -> None:
        part = _part(bd.Box(60, 40, 30) - bd.Rot(0, 30, 0) * bd.Cylinder(4, 100))
        self.assertIn("cnc.undercut", _codes(_check(part)))
        five = _check(part, axes=5)
        self.assertNotIn("cnc.undercut", _codes(five))
        self.assertEqual(five.measurements["setups"]["items"][0]["unreached_area_fraction"], 0.0)

    def test_a_closed_void_is_its_own_finding(self) -> None:
        result = _check(_part(bd.Box(40, 40, 20) - bd.Sphere(5)))
        void = result.measurements["voids"]["items"][0]
        self.assertAlmostEqual(void["volume_mm3"], 4 / 3 * math.pi * 125, delta=0.5)
        self.assertIn("cnc.enclosed_void", _codes(result))
        self.assertEqual(result.measurements["access"]["items"], [])


class StockTest(unittest.TestCase):
    def test_removal_and_a_stock_too_small(self) -> None:
        part = _part(bd.Box(40, 20, 10) - _pocket(20, 10, 5, 2, 5))
        item = _check(part).measurements["stock"]["items"][0]
        self.assertEqual((item["length_mm"], item["width_mm"], item["height_mm"]), (40.0, 20.0, 10.0))
        self.assertAlmostEqual(item["removal_ratio"], 1 - item["volume_mm3"] / 8000.0, places=4)
        small = _check(part, stock="30x30x30")
        self.assertIn("cnc.stock_too_small", _codes(small))
        self.assertFalse(small.ok)
        self.assertEqual(_check(part, stock="50x30x12").measurements["stock"]["items"][0]["stock_volume_mm3"], 18000.0)


class TurningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        body = bd.Cylinder(15, 60, align=(A.CENTER, A.CENTER, A.MIN))
        body += bd.Pos(0, 0, 60) * bd.Cylinder(10, 20, align=(A.CENTER, A.CENTER, A.MIN))
        body -= bd.Pos(0, 0, 20) * (bd.Cylinder(16, 2, align=(A.CENTER, A.CENTER, A.MIN))
                                    - bd.Cylinder(13, 2, align=(A.CENTER, A.CENTER, A.MIN)))
        body -= bd.Pos(0, 0, -1) * bd.Cylinder(4, 41, align=(A.CENTER, A.CENTER, A.MIN))
        body -= bd.Pos(0, 0, 30) * bd.Cylinder(6, 3, align=(A.CENTER, A.CENTER, A.MIN))
        body -= bd.Pos(0, 0, 50) * bd.Rot(0, 90, 0) * bd.Cylinder(2.5, 40)
        cls.result = _check(_part(body, "shaft"), turning=True, material="aluminum", rules="protolabs")
        cls.report = cls.result.measurements

    def test_the_axis_and_the_envelope(self) -> None:
        turning = self.report["turning"]["items"][0]
        self.assertEqual(turning["axis"], [0.0, 0.0, 1.0])
        self.assertEqual((turning["max_diameter_mm"], turning["length_mm"]), (30.0, 80.0))
        self.assertGreater(turning["axisymmetric_fraction"], 0.9)

    def test_grooves_bores_and_cross_holes(self) -> None:
        grooves = sorted((g["internal"], g["width_mm"], g["depth_mm"]) for g in self.report["grooves"]["items"])
        self.assertEqual(grooves, [(False, 2.0, 2.0), (True, 3.0, 2.0)])
        self.assertEqual([(b["diameter_mm"], b["through"]) for b in self.report["bores"]["items"]], [(8.0, False)])
        relations = sorted(h.get("relation") for h in self.report["holes"]["items"])
        self.assertEqual(relations, ["axial", "radial"])
        self.assertEqual({item["kind"] for item in self.report["live_tooling"]["items"]}, {"cross_hole"})
        self.assertIn("cnc.internal_groove", _codes(self.result))  # Protolabs offers no ID groove
        self.assertNotIn("cnc.groove_width", _codes(self.result))  # 2 mm: wide enough

    def test_a_prism_has_no_axis(self) -> None:
        result = _check(_part(bd.Box(10, 10, 10)), turning=True)
        self.assertIn("cnc.no_turning_axis", _codes(result))


class ThreadsTest(unittest.TestCase):
    def test_a_modelled_thread_is_a_thread_not_an_undercut(self) -> None:
        profile = bd.Plane.XZ.shift_origin((2.5, 0, 0)) * bd.Polygon((-0.05, -0.4), (0.5, 0), (-0.05, 0.4), align=None)
        thread = bd.sweep(profile, path=bd.Pos(0, 0, 3) * bd.Helix(1.0, 4.0, 2.5), is_frenet=True)
        part = bd.Box(16, 16, 10, align=(A.CENTER, A.CENTER, A.MIN)) - bd.Cylinder(2.5, 30) - thread
        result = _check(_part(part), rules="protolabs")
        found = result.measurements["threads"]["items"]
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["internal"], found[0]["major_diameter_mm"], found[0]["minor_diameter_mm"]),
                         (True, 6.0, 5.0))
        self.assertAlmostEqual(found[0]["pitch_mm"], 1.0, places=3)
        self.assertEqual(result.measurements["access"]["items"], [])
        self.assertEqual(result.measurements["sharp_edges"]["items"], [])
        self.assertIn("cnc.modelled_thread", _codes(result))


class RuleSetsTest(unittest.TestCase):
    def test_every_set_cites_what_it_uses_and_the_options_resolve(self) -> None:
        self.assertEqual(set(rules_side.RULE_SETS), {"generic", "hubs", "protolabs", "xometry"})
        for rule_set in rules_side.RULE_SETS.values():
            for rule in rule_set.rules:
                self.assertTrue(rule.id.startswith("cnc."), rule.id)
                self.assertTrue(rule_set.source(rule.source).url.startswith("https://"))
        self.assertTrue(rules_side.RULE_SETS["generic"].generic)
        resolved = manufacturing.options("step", "cnc", {"tools": "6,3", "rules": "xometry", "material": "6061"})
        context = rules_side.context({}, resolved)
        self.assertEqual((context["min_tool_mm"], context["envelope"], context["hardness"]),
                         (3.0, "aluminum/3", "soft"))
        with self.assertRaisesRegex(ValueError, "--tools"):
            manufacturing.options("step", "cnc", {"tools": "3,x"})

    def test_a_live_shape_is_checked_as_its_step_is(self) -> None:
        part = _part(bd.Box(40, 30, 12) - _pocket(10, 10, 4, 0.0, 6), "block")
        live = cnc(part)
        written = _check(part)
        self.assertEqual(sorted(f.location for f in live.findings if f.code == "cnc.internal_corner_sharp"),
                         sorted(f.location for f in written.findings if f.code == "cnc.internal_corner_sharp"))
        json.dumps(live.measurements, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
