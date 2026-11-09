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
import numpy as np

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
        # the hole's depth is its drilled length below the counterbore, which is its own feature
        self.assertEqual((bored["diameter_mm"], bored["through"], bored["depth_mm"], bored["overall_depth_mm"]),
                         (6.6, True, 34.0, 40.0))
        self.assertAlmostEqual(bored["depth_to_diameter"], 34.0 / 6.6, places=6)
        self.assertEqual(bored["counterbores"], [{"diameter_mm": 11.0, "depth_mm": 6.0,
                                                  "depth_to_diameter": round(6.0 / 11.0, 9)}])
        self.assertEqual(sunk["diameter_mm"], 4.5)
        self.assertEqual(len(sunk["countersinks"]), 1)
        self.assertAlmostEqual(sunk["countersinks"][0]["angle_deg"], 90.0, places=6)
        self.assertAlmostEqual(sunk["countersinks"][0]["diameter_mm"], 9.0, places=4)

    def test_a_counterbore_is_judged_by_the_hole_depth_rule_as_a_hole_of_its_own(self) -> None:
        """A 6.6 mm hole under an 11 mm counterbore 55 deep (5 diameters), and a 20 mm bore 80 deep (4) over a 6
        mm hole 5 deep: each counterbore is an item of its own, its depth over its own diameter judged."""
        deep = bd.Box(40, 40, 70) - bd.Pos(0, 0, 0) * bd.Cylinder(3.3, 70) \
            - bd.Pos(0, 0, 35) * bd.Cylinder(5.5, 55, align=(A.CENTER, A.CENTER, A.MAX))
        stepped = bd.Box(40, 40, 85) - bd.Cylinder(3.0, 85) \
            - bd.Pos(0, 0, 42.5) * bd.Cylinder(10.0, 80, align=(A.CENTER, A.CENTER, A.MAX))
        for shape, bore, failed in ((deep, (11.0, 5.0), True), (stepped, (20.0, 4.0), False)):
            result = _check(_part(shape), material="aluminum")
            [item] = result.measurements["counterbores"]["items"]
            self.assertEqual((item["diameter_mm"], item["depth_to_diameter"]), bore)
            [outcome] = [o for o in result.measurements["rules"]["outcomes"] if o["rule"] == "cnc.hole_depth"]
            self.assertEqual(outcome["evaluated"], 2, "the hole and its counterbore")
            self.assertEqual(outcome["status"] == "failed", failed)
            self.assertEqual("cnc.hole_depth" in _codes(result), failed)
            if failed:
                self.assertEqual(outcome["failures"][0]["location"], item["location"])

    def test_drill_sizes_are_named_from_every_series(self) -> None:
        self.assertEqual(self.holes[10]["bottom"], "flat")
        self.assertIsNone(self.holes[10]["standard_drill"])
        # a drill leaves its point: a flat floor is an end mill's, or a flat-bottom drill's
        self.assertEqual((self.holes[10]["drilled"], self.holes[10]["floor_tool"]),
                         (False, "end mill or flat-bottom drill"))
        self.assertEqual((self.holes[-35]["drilled"], self.holes[-35]["floor_tool"]), (True, None))
        self.assertAlmostEqual(self.holes[10]["drill_deviation_mm"], 4.33 - 0.1695 * 25.4, places=4)  # #18
        self.assertEqual(self.holes[25]["standard_drill"], "1/4 in (6.350 mm)")
        self.assertEqual(_dfm_cnc_holes.standard_drill(0.201 * 25.4)[0], "#7 (5.105 mm)")
        self.assertEqual(_dfm_cnc_holes.standard_drill(0.257 * 25.4)[0], "letter F (6.528 mm)")
        self.assertEqual(_dfm_cnc_holes.standard_drill(10.2)[0], "10.2 mm")  # M12's tap drill, as stocked
        self.assertEqual(_dfm_cnc_holes.standard_drill(3.33)[0], None)


class CountersinkAngleTest(unittest.TestCase):
    def test_a_countersinks_included_angle_reads_as_drawn(self) -> None:
        # the kernel signs a cone's semi-angle by its axis's way (-41 deg here): the angle reported is 82
        with bd.BuildPart() as made:
            bd.Box(40, 40, 10)
            with bd.Locations((0, 0, 5)):
                bd.CounterSinkHole(radius=2.5, counter_sink_radius=5, counter_sink_angle=82)
        holes = cnc(made.part, material="aluminum").measurements["holes"]["items"]
        self.assertEqual([sink["angle_deg"] for hole in holes for sink in hole["countersinks"]], [82.0])


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
        corners = [c for c in self.report["internal_corners"]["items"] if c["pocket"] == closed["floor"]]
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
        outcome = next(o for o in result.measurements["rules"]["outcomes"]
                       if o["rule"] == "cnc.internal_corner_sharp" and o["status"] == "failed")
        self.assertEqual(len(outcome["failures"]), 4)
        found = [f for f in result.findings if f.code == "cnc.internal_corner_sharp"]
        # sharp is the error (no round tool makes it); 1.25 mm is the radius recommended, said in the hint
        self.assertIn("sharp vertical corner (no round tool makes it): radius 0 mm is under the 0.025 mm minimum",
                      found[0].message)
        self.assertIn("4 mm tall", found[0].message)
        self.assertIn("radius of 1.25 mm or more (recommended", found[0].hint)
        # two corners share a face ref: the fold names the worst one's edge and counts the other
        named = {c["edge"] for c in corners if any(f"{c['edge']}," in f.message for f in found)}
        self.assertEqual(len(named), len(found))
        self.assertEqual(sum(1 + ("1 more at this ref" in f.message) for f in found), 4)
        # open on one side and cut from it, the same sharp corner is a side mill's root
        step = bd.Box(40, 30, 12) - bd.Pos(15, 0, 6) * bd.Box(20, 10, 8)
        self.assertNotIn("cnc.internal_corner_sharp", _codes(_check(_part(step))))


class ThroughCavitiesTest(unittest.TestCase):
    def test_a_window_s_corners_follow_the_tools(self) -> None:
        plate = bd.Box(100, 50, 10)
        window = bd.Pos(0, 0, -6) * bd.extrude(bd.RectangleRounded(30, 20, 0.5), 12)
        result = _check(_part(plate - window), tools="3,6,10")
        corners = result.measurements["internal_corners"]["items"]
        self.assertEqual([(c["radius_mm"], c["height_mm"]) for c in corners], [(0.5, 10.0)] * 4)
        self.assertIn("cnc.internal_corner_radius", _codes(result))
        self.assertFalse(result.ok)
        through = result.measurements["pockets"]["items"][0]
        self.assertEqual((through["kind"], through["depth_mm"], through["width_mm"]), ("through", 10.0, 20.0))

    def test_a_through_slot_is_deep_for_its_width(self) -> None:
        part = bd.Box(60, 40, 20) - bd.Pos(0, 0, -11) * bd.extrude(bd.SlotOverall(30, 3), 22)
        result = _check(_part(part))
        slot = result.measurements["pockets"]["items"][0]
        self.assertEqual((slot["kind"], slot["width_mm"], slot["depth_mm"]), ("through", 3.0, 20.0))
        self.assertEqual(len(slot["width_faces"]), 2)
        self.assertTrue({"cnc.pocket_depth_to_width", "cnc.corner_reach"} <= _codes(result))

    def test_an_l_bracket_s_inside_fillet_is_a_floor_root_not_a_corner(self) -> None:
        bracket = bd.Box(60, 50, 8, align=(A.CENTER, A.MIN, A.MIN)) + bd.Box(60, 8, 48, align=(A.CENTER, A.MIN, A.MIN))
        inner = bracket.edges().filter_by(bd.Axis.X).filter_by_position(bd.Axis.Y, 7.9, 8.1) \
            .filter_by_position(bd.Axis.Z, 7.9, 8.1)
        result = _check(_part(bd.fillet(inner, 4)))
        self.assertEqual(result.measurements["internal_corners"]["items"], [])
        self.assertTrue(result.ok)

    def test_a_boss_gap_names_the_two_faces_it_is_between(self) -> None:
        part = bd.Box(60, 60, 20) - _pocket(40, 40, 10, 4, 10) + bd.Pos(13.5, 0, 0) * bd.Cylinder(5, 20, align=(A.CENTER, A.CENTER, A.MIN))
        result = _check(_part(part))
        pocket = result.measurements["pockets"]["items"][0]
        self.assertEqual(pocket["location"], pocket["width_faces"][0])
        self.assertNotEqual(pocket["location"], pocket["floor"])
        self.assertAlmostEqual(result.measurements["gaps"]["items"][0]["width_mm"], 1.5, places=4)  # exact


class WallsAndGapsTest(unittest.TestCase):
    def test_the_web_between_two_holes_is_its_exact_minimum(self) -> None:
        part = bd.Box(40, 20, 10) - bd.Pos(-3.2, 0, 0) * bd.Cylinder(3, 12) - bd.Pos(3.2, 0, 0) * bd.Cylinder(3, 12)
        result = _check(_part(part), material="aluminum")
        wall = result.measurements["walls"]["items"][0]
        self.assertAlmostEqual(wall["thickness_mm"], 0.4, places=4)  # 16 sampled rays read 0.6157
        self.assertTrue(wall["refined"])
        finding = next(f for f in result.findings if f.code == "cnc.wall_thickness")
        self.assertIn(f"(to {wall['opposite']} at ", finding.message)

    def test_a_knife_edge_is_its_own_item_not_a_wall(self) -> None:
        wedge = bd.extrude(bd.Plane.XZ * bd.Polygon((0, 0), (40, 0), (40, 10), (30, 10), align=None), 15, both=True)
        result = _check(_part(wedge), material="aluminum")
        knife = result.measurements["knife_edges"]["items"]
        self.assertEqual(len(knife), 1)
        self.assertAlmostEqual(knife[0]["angle_deg"], math.degrees(math.atan(10 / 30)), places=3)
        self.assertEqual(result.measurements["walls"]["items"], [])
        self.assertEqual(_codes(result) & {"cnc.wall_thickness", "cnc.knife_edge"}, {"cnc.knife_edge"})
        self.assertTrue(result.ok)  # a warning: blunt it

    def test_a_curved_edge_is_read_along_its_length(self) -> None:
        # a 10 mm rod cut 60 deg from its axis: its edge runs from 30 deg at the low side to 150 at the high, a
        # knife over a quarter of it, whatever its middle reads
        rod = bd.Cylinder(5, 30, align=(A.CENTER, A.CENTER, A.MIN))
        cut = rod - bd.Pos(0, 0, 20) * bd.Rot(0, 60, 0) * bd.Box(80, 80, 40, align=(A.CENTER, A.CENTER, A.MIN))
        for turn in (bd.Rot(0, 0, 0), bd.Rot(23, -37, 61)):
            [knife] = cnc(_part(turn * cut), material="aluminum").measurements["knife_edges"]["items"]
            # its least found between the samples about it, not the nearest sample's
            self.assertAlmostEqual(knife["angle_deg"], 30.0, delta=1e-3)
            self.assertLess(knife["length_mm"], 0.5 * knife["edge_length_mm"])

    def test_wall_thickness_and_gap_width_are_exact(self) -> None:
        part = bd.Box(60, 40, 5, align=(A.CENTER, A.CENTER, A.MAX))
        for y, thickness in ((-4, 1.2), (4, 1.2)):
            part += bd.Pos(0, y, 0) * bd.Box(50, thickness, 15, align=(A.CENTER, A.CENTER, A.MIN))
        report = _check(_part(part), material="abs").measurements
        thinnest = report["walls"]["items"][0]
        self.assertAlmostEqual(thinnest["thickness_mm"], 1.2, places=6)
        self.assertAlmostEqual(thinnest["height_mm"], 15.0, places=6)
        self.assertAlmostEqual(report["gaps"]["items"][0]["width_mm"], 6.8, places=6)


class SharpEdgesTest(unittest.TestCase):
    def _valley(self, void: float) -> Any:
        rise = 30 * math.tan(math.radians((180 - void) / 2))
        profile = bd.Polygon((-30, 0), (30, 0), (30, 10 + rise), (0, 10), (-30, 10 + rise), align=None)
        return _part(bd.extrude(bd.Plane.XZ * profile, 20, both=True))

    def test_a_near_flat_crease_is_a_ball_end_mill_s(self) -> None:
        for void in (176.0, 160.0):
            result = _check(self._valley(void))
            self.assertTrue(result.ok, void)
            self.assertEqual(result.measurements["sharp_edges"]["by_tool"], {"ball_mill": 1})
            # made, and still in the record: the ball's round departs from the drawn crease by R (1/sin(v/2) - 1)
            [crease] = result.measurements["sharp_edges"]["items"]
            self.assertEqual((crease["made_by"], crease["radius_mm"]), ("ball_mill", 1.25))
            self.assertAlmostEqual(crease["deviation_mm"], 1.25 * (1 / math.sin(math.radians(void / 2)) - 1), places=4)
            self.assertIn("cnc.ball_creases", _codes(result))
        # under BALL_VOID_DEG: obtuse, sharp only faced from each flank's own direction -- no setup of its own
        # counted, and said: a ball or a side-milling tool leaves its radius (obtuse_root, a warning)
        for axes in (3, 5):
            sharp = _check(self._valley(140.0), axes=axes)
            self.assertEqual([(i["reason"], i["made_by"]) for i in sharp.measurements["sharp_edges"]["items"]],
                             [("obtuse_root", "end_mill")], axes)
            self.assertEqual(sharp.measurements["sharp_edges"]["by_tool"], {"end_mill": 1}, axes)
            self.assertEqual([f.severity for f in sharp.findings if f.code == "cnc.sharp_internal_edge"],
                             ["warning"], axes)
        setup = _check(self._valley(140.0)).measurements["setups"]["items"][0]
        self.assertFalse([d for d in setup["directions"] if d.get("sharp_edges")])

    def test_a_slot_s_floor_chamfers_are_an_end_mill_s_corner_and_a_chamfer_mill_s_tip(self) -> None:
        # a through slot 10 wide whose floor roots are 1.5 mm 45-degree chamfers: each wall's root over its
        # chamfer is the corner of the end mill side-milling the wall, each chamfer's root on the floor a 90-degree
        # chamfer mill's tip -- no slot cutter, nothing to say, at any turn
        profile = bd.Polyline((-5, 12.01), (-5, 9.5), (-3.5, 8), (3.5, 8), (5, 9.5), (5, 12.01), close=True)
        slot = bd.Box(80, 40, 12, align=(A.CENTER, A.CENTER, A.MIN)) - bd.extrude(
            bd.Plane.YZ.offset(-41) * bd.make_face(profile), 82)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(0, 0, 25) * bd.Pos(1, 2, 0)):
            result = cnc(_part(turn * slot), material="aluminum")
            self.assertEqual(result.measurements["sharp_edges"]["by_tool"], {"end_mill": 2, "chamfer_mill": 2}, turn)
            self.assertEqual([f for f in result.findings if f.severity != "info"], [], turn)

    def test_an_obtuse_root_beside_a_counted_setup_s_floor_is_one_more_setup(self) -> None:
        # a through channel's floor meets its 10-degree leaning walls at 100 degrees: the floor is faced in the
        # top setup the count has, each wall wants its own -- one more setup, said; the same turned
        lean = math.tan(math.radians(10)) * 10
        channel = bd.extrude(bd.Plane.YZ * bd.Polygon((-8, 0), (8, 0), (8 + lean, 10.01), (-8 - lean, 10.01),
                                                      align=None), 40, both=True)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(0, 0, 30) * bd.Pos(2, 3, 1)):
            result = cnc(_part(turn * (bd.Box(60, 40, 20) - channel)), material="aluminum")
            roots = result.measurements["sharp_edges"]["items"]
            self.assertEqual([(i["reason"], i["more_setups"]) for i in roots], [("obtuse_root", "one more setup")] * 2)
            hint = next(f.hint for f in result.findings if f.code == "cnc.sharp_internal_edge")
            self.assertIn("one more setup than the count", hint)

    def test_a_crease_says_why_no_tool_makes_it(self) -> None:
        # a closed trough's ends: no 3-axis tool makes them; a chamfer mill tilted to their bisector would
        trough = _check(_part(bd.Box(60, 40, 20) - bd.Pos(0, 0, 10) * bd.Rot(0, 90, 0) * bd.Cylinder(8, 40)))
        self.assertEqual({item["reason"] for item in trough.measurements["sharp_edges"]["items"]}, {"other_axes"})
        finding = next(f for f in trough.findings if f.code == "cnc.sharp_internal_edge")
        self.assertEqual(finding.severity, "warning")
        self.assertIn("an angled setup or more axes", finding.hint)
        # a D-bore's flat meets its arc along the bore: a corner along a tool's axis, a radius or EDM
        bore = bd.Box(30, 30, 20) - (bd.Cylinder(6, 40) & bd.Pos(0, -2, 0) * bd.Box(12, 12, 40))
        result = _check(_part(bore))
        corners = result.measurements["internal_corners"]["items"]
        self.assertEqual(sorted((c["radius_mm"], c["sharp"]) for c in corners)[:2], [(0.0, True), (0.0, True)])

    def test_a_curved_floor_is_no_end_mill_s_floor(self) -> None:
        trough = bd.Box(60, 40, 20) - bd.Pos(0, 0, 10) * bd.Rot(0, 90, 0) * bd.Cylinder(8, 40)
        result = _check(_part(trough))
        self.assertEqual(result.measurements["sharp_edges"]["by_tool"], {"none": 2})
        self.assertEqual(len(result.measurements["sharp_edges"]["items"]), 2)
        self.assertEqual(result.measurements["internal_corners"]["items"], [])  # closed at its ends: no through cut

    def test_by_tool_counts_every_unmade_edge_once(self) -> None:
        # a pocket with sharp corners and a rim round, beside a 140-degree crease: every unmade edge is an
        # item, a corner or an edge folded into one
        part = bd.Box(60, 30, 12) - bd.Pos(-15, 0, 2) * bd.Box(16, 10, 8.01, align=(A.CENTER, A.CENTER, A.MIN))
        rim = [e for e in part.edges() if abs(e.center().Z - 6) < 1e-6 and abs(e.center().X + 15) < 8.1
               and abs(e.center().Y) < 5.1]
        part = bd.fillet(rim, 0.3) - bd.Pos(15, 0, 6) * bd.Rot(0, 0, 0) * bd.extrude(
            bd.Plane.XZ * bd.Polygon((-8, 0.01), (8, 0.01), (0, -8 * math.tan(math.radians(20))), align=None), 20,
            both=True)
        report = _check(_part(part)).measurements
        items = report["sharp_edges"]["items"]
        corners = report["internal_corners"]["items"]
        unmade = (len([i for i in items if i["made_by"] is None]) + len([c for c in corners if c.get("edge")])
                  + sum(len(c.get("folded_edges") or ()) for c in corners))
        self.assertEqual(report["sharp_edges"]["by_tool"].get("none", 0), unmade)
        self.assertGreater(unmade, 4)
        self.assertEqual(report["sharp_edges"]["by_tool"].get("ball_mill", 0),
                         len([i for i in items if i["made_by"] == "ball_mill"]))

    def test_the_edges_a_corner_runs_through_a_rim_round_are_that_corner(self) -> None:
        part = bd.Box(40, 30, 12) - bd.Pos(0, 0, 2) * bd.Box(16, 10, 8.01, align=(A.CENTER, A.CENTER, A.MIN))
        rim = [e for e in part.edges() if abs(e.center().Z - 6) < 1e-6 and abs(e.center().X) < 8.1
               and abs(e.center().Y) < 5.1]
        result = _check(_part(bd.fillet(rim, 0.3)))
        self.assertEqual(result.measurements["sharp_edges"]["items"], [])
        corners = result.measurements["internal_corners"]["items"]
        self.assertEqual([len(c.get("folded_edges") or ()) for c in corners], [1, 1, 1, 1])

    def test_a_radius_is_read_to_the_tolerance(self) -> None:
        for radius in (1.5, 1.4999):
            result = _check(_part(bd.Box(60, 40, 20) - _pocket(40, 24, 8, radius, 10)), tools="3,6,10")
            self.assertNotIn("cnc.internal_corner_radius", _codes(result), radius)
        self.assertIn("cnc.internal_corner_radius",
                      _codes(_check(_part(bd.Box(60, 40, 20) - _pocket(40, 24, 8, 1.48, 10)), tools="3,6,10")))


class AccessTest(unittest.TestCase):
    def test_five_axes_reach_at_least_what_four_do(self) -> None:
        part = bd.Box(40, 40, 30) - _pocket(20, 20, 15, 4, 15)
        part -= bd.Pos(10, 0, 0) * bd.Box(6, 12, 4, align=(A.CENTER, A.CENTER, A.MIN))  # a recess under the rim
        unreached = {axes: _check(_part(part), axes=axes).measurements["setups"]["items"][0]["unreached_area_fraction"]
                     for axes in (4, 5)}
        self.assertLessEqual(unreached[5], unreached[4])

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
        result = _check(_part(opened))
        report = result.measurements
        # every face in line of sight, but a T-slot cutter's work: an undercut all the same
        self.assertEqual([(item["kind"], item["cutter"], item["edge_count"]) for item in report["access"]["items"]],
                         [("special_cutter", "slot cutter", 4)])
        self.assertEqual(report["sharp_edges"]["items"], [])
        self.assertEqual(report["sharp_edges"]["by_tool"].get("slot_cutter"), 4)
        self.assertEqual([f.severity for f in result.findings if f.code == "cnc.special_cutter"], ["warning"])

    def test_five_axes_reach_an_inclined_hole_three_do_not(self) -> None:
        part = _part(bd.Box(60, 40, 30) - bd.Rot(0, 30, 0) * bd.Cylinder(4, 100))
        three = _check(part)
        # one cause, one finding: the hole's unreached faces are the inclined hole's, not undercuts of their own
        self.assertIn("cnc.inclined_feature", _codes(three))
        self.assertNotIn("cnc.undercut", _codes(three))
        self.assertTrue(all(item.get("part_of") for item in three.measurements["access"]["items"] if item["hole"]))
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
        cls.result = _check(_part(body, "shaft"), turning=True, material="aluminum")
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
        # grooves are facts: a lathe's groove limits are a shop's, compared with the measurements, never a rule
        judged = {o["family"] for o in self.report["rules"]["outcomes"] if o["status"] in ("passed", "failed")}
        self.assertNotIn("grooves", judged)

    def test_a_square_plate_with_a_bore_is_mostly_not_turned(self) -> None:
        result = _check(_part(bd.Box(100, 100, 10) - bd.Cylinder(10, 30)), turning=True)
        self.assertLess(result.measurements["turning"]["items"][0]["axisymmetric_fraction"], 0.1)
        self.assertIn("cnc.mostly_not_turned", _codes(result))

    def test_a_prism_has_no_axis(self) -> None:
        result = _check(_part(bd.Box(10, 10, 10)), turning=True)
        self.assertIn("cnc.no_turning_axis", _codes(result))


class ThreadsTest(unittest.TestCase):
    def test_a_modelled_thread_is_a_thread_not_an_undercut(self) -> None:
        profile = bd.Plane.XZ.shift_origin((2.5, 0, 0)) * bd.Polygon((-0.05, -0.4), (0.5, 0), (-0.05, 0.4), align=None)
        thread = bd.sweep(profile, path=bd.Pos(0, 0, 3) * bd.Helix(1.0, 4.0, 2.5), is_frenet=True)
        part = bd.Box(16, 16, 10, align=(A.CENTER, A.CENTER, A.MIN)) - bd.Cylinder(2.5, 30) - thread
        result = _check(_part(part))
        found = result.measurements["threads"]["items"]
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["internal"], found[0]["minor_diameter_mm"]), (True, 5.0))
        self.assertAlmostEqual(found[0]["major_diameter_mm"], 6.0, places=3)  # read from the flanks' points
        self.assertAlmostEqual(found[0]["pitch_mm"], 1.0, places=3)
        self.assertEqual(result.measurements["access"]["items"], [])
        self.assertEqual(result.measurements["sharp_edges"]["items"], [])


    def test_a_revolved_round_is_no_thread(self) -> None:
        with bd.BuildPart() as pulley:
            with bd.BuildSketch(bd.Plane.XZ):
                with bd.BuildLine():
                    bd.Polyline((1.6, 0), (5.6, 0))
                    bd.Spline((5.6, 0), (6.0, 0.75), (5.6, 1.5))
                    bd.Polyline((5.6, 1.5), (1.6, 1.5), (1.6, 0))
                bd.make_face()
            bd.revolve(axis=bd.Axis.Z)
        self.assertIn(bd.GeomType.REVOLUTION, {face.geom_type for face in pulley.part.faces()})
        result = _check(_part(pulley.part))
        self.assertEqual(result.measurements["threads"]["items"], [])


class OneCauseTest(unittest.TestCase):
    """What one feature causes is one finding: the rest are its facts, naming it."""

    def test_a_recess_is_its_cutter_s_and_its_height_is_no_end_mill_s(self) -> None:
        part = bd.Box(60, 40, 20) - _pocket(30, 20, 10, 4, 10)
        part -= bd.Pos(0, 12, 1.5) * bd.Box(16, 4, 3)  # a 3 mm recess under the pocket's rim
        part -= bd.Pos(22, 0, 0) * bd.Box(3, 16, 30)  # a 3 mm through slot
        result = cnc(_part(part), tools="6", material="aluminum")
        codes = [f.code for f in result.findings]
        self.assertEqual(codes.count("cnc.special_cutter"), 1)
        self.assertNotIn("cnc.undercut", codes)
        self.assertNotIn("cnc.no_line_of_sight", codes)
        special = next(i for i in result.measurements["access"]["items"] if i["kind"] == "special_cutter")
        self.assertTrue(special["unreached_faces"])
        # the recess's floor-to-ceiling is a slot cutter's to cut; the slot's walls an end mill's: one finding
        gaps = result.measurements["gaps"]["items"]
        self.assertIn("slot_cutter", {gap["made_by"] for gap in gaps})
        found = [f for f in result.findings if f.code == "cnc.gap_width"]
        self.assertEqual(len(found), 1)
        self.assertIn("3 mm is under the 6 mm minimum", found[0].message)


def _judged(result: Any) -> set[str]:
    return {finding.code for finding in result.findings if finding.severity in ("error", "warning")}


class OpenRecessTest(unittest.TestCase):
    """A slot open at its neck is no through cavity, and two faces that share an edge are no gap's walls."""

    @staticmethod
    def _slot(flank_deg: float) -> Any:
        # a slot along x, 8 deep, 20 wide at its floor (z = 12), narrowing to its neck at the top (z = 20)
        inset = 8 / math.tan(math.radians(flank_deg))
        section = bd.Plane.YZ * bd.make_face(bd.Polyline((-(10 - inset), 20.001), (10 - inset, 20.001), (10, 12),
                                                        (-10, 12), close=True))
        return _part(bd.Box(60, 40, 20, align=(A.CENTER, A.CENTER, A.MIN)) - bd.extrude(section, 40, both=True))

    def test_a_dovetail_s_flank_is_no_gap_over_its_floor_and_its_slot_is_open(self) -> None:
        for flank, tools in ((45.0, "3,6"), (76.0, None)):
            result = cnc(self._slot(flank), material="aluminum", **({"tools": tools} if tools else {}))
            with self.subTest(flank=flank):
                # its flank meets its floor: the gap between them closes to nothing, the void's angle
                self.assertFalse([g for g in result.measurements["gaps"]["items"] if g["width_mm"] < 2.5])
                # open at its neck: no through cavity 60 mm deep along its length, no corner 60 mm tall
                self.assertFalse([p for p in result.measurements["pockets"]["items"] if p["kind"] == "through"])
                self.assertEqual(result.measurements["internal_corners"]["items"], [])
                self.assertFalse({"cnc.gap_width", "cnc.gap_width_small", "cnc.pocket_depth_to_width",
                                  "cnc.internal_corner_sharp"} & _judged(result))
        # 45 degrees is a dovetail cutter's: one special cutter, nothing else
        self.assertEqual(_judged(cnc(self._slot(45.0), material="aluminum")), {"cnc.special_cutter"})

    def test_a_v_groove_s_flanks_are_no_gap(self) -> None:
        half = 10 * math.tan(math.radians(15))
        groove = bd.Plane.YZ * bd.make_face(bd.Polyline((-half, 20.001), (half, 20.001), (0, 10), close=True))
        part = _part(bd.Box(60, 40, 20, align=(A.CENTER, A.CENTER, A.MIN)) - bd.extrude(groove, 40, both=True))
        result = cnc(part, material="aluminum")
        self.assertFalse([g for g in result.measurements["gaps"]["items"] if g["width_mm"] < 2.5])
        # its 30-degree root is no standard chamfer mill's: a V cutter ground to it, said with its angle
        [special] = [i for i in result.measurements["access"]["items"] if i["kind"] == "special_cutter"]
        self.assertIn("v cutter of 30 deg (no standard angle)", special["cutter"])
        self.assertEqual(_judged(result), {"cnc.special_cutter"})

    def test_an_internal_groove_is_one_keyseat_recess(self) -> None:
        part = bd.Box(80, 60, 25)  # top at z = 12.5
        part -= bd.Pos(0, 0, -2.5) * bd.extrude(bd.Circle(8), 15.001)
        part -= bd.Pos(0, 0, 2.5) * bd.extrude(bd.Circle(10), 3)
        result = cnc(_part(part), material="aluminum")
        self.assertEqual(_judged(result), {"cnc.special_cutter"})
        [special] = [i for i in result.measurements["access"]["items"] if i["kind"] == "special_cutter"]
        self.assertEqual((special["cutter"], len(special["unreached_faces"])), ("keyseat cutter", 3))
        [hole] = result.measurements["holes"]["items"]
        self.assertEqual((hole["diameter_mm"], hole["counterbores"]), (16.0, []))
        self.assertEqual([(g["diameter_mm"], g["width_mm"]) for g in hole["grooves"]], [(20.0, 3.0)])

    def test_a_tilted_hole_s_depth_is_its_drilled_length(self) -> None:
        result = cnc(_part(bd.Box(80, 60, 25) - bd.Rot(30, 0, 0) * bd.Cylinder(3, 100)), material="aluminum", axes=5)
        [hole] = result.measurements["holes"]["items"]
        self.assertAlmostEqual(hole["depth_mm"], 25 / math.cos(math.radians(30)), places=4)
        self.assertGreater(hole["overall_depth_mm"], hole["depth_mm"] + 3)  # its longest side, entry to exit

    def test_a_profile_s_root_reads_as_any_crease_whatever_the_part_s_thinnest(self) -> None:
        # a 10 mm plate's outline with a 110-degree notch turned off the axes: no square end mill's end and flank
        # make it; it is made in the setups that make its flanks -- none of its own, as a valley's crease of that
        # angle reads, whichever way the part is thinnest
        notch = bd.Pos(20, 0, 0) * bd.Rot(0, 0, 17) * bd.extrude(bd.make_face(bd.Polyline(
            (0, 0), (30 * math.cos(math.radians(55)), 30 * math.sin(math.radians(55))),
            (30 * math.cos(math.radians(55)), -30 * math.sin(math.radians(55))), close=True)), 20, both=True)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(23, -37, 61)):
            result = cnc(_part(turn * (bd.Box(60, 60, 10) - notch)), material="aluminum")
            [root] = [i for i in result.measurements["sharp_edges"]["items"] if abs(i["void_angle_deg"] - 110) < 1e-3]
            self.assertEqual((root["reason"], root["made_by"]), ("obtuse_root", "end_mill"), turn)
            setup = result.measurements["setups"]["items"][0]
            self.assertEqual(sum(d.get("sharp_edges") or 0 for d in setup["directions"]), 0)


class SideMillTest(unittest.TestCase):
    """A sharp concave edge a square end mill makes from some direction a setup presents -- its end on one face
    square to the direction, its flank on the other along it, seen from outside -- is made, each such direction
    a setup; one no tool makes from any direction is an error, however the part is turned."""

    def test_a_notch_in_a_plate_is_side_milled_at_any_angle(self) -> None:
        plate = bd.Box(100, 60, 8)
        read = []
        for angle in (0, 30, 45, 73):
            notched = plate - bd.Pos(0, 30, 0) * bd.Rot(0, 0, angle) * bd.Box(14, 14, 20)
            for turn in (bd.Rot(0, 0, 0), bd.Rot(23, -37, 61), bd.Rot(90, 0, 0)):
                result = cnc(_part(turn * notched), material="aluminum")
                self.assertFalse({"cnc.sharp_internal_edge", "cnc.internal_corner_sharp", "cnc.inclined_feature"}
                                 & _codes(result), (angle, turn))
                setup = result.measurements["setups"]["items"][0]
                self.assertTrue(any(d.get("sharp_edges") for d in setup["directions"]), (angle, turn))
                read.append(setup["setup_count"])
        self.assertEqual(set(read), {read[0]})

    def test_a_gear_s_curved_root_and_a_pocket_s_corner_are_made_by_no_tool(self) -> None:
        edges = []
        for k in range(12):
            a0, am, a1 = (2 * math.pi * (k + f) / 12 for f in (0.0, 0.5, 1.0))
            ends = [(16 * math.cos(a0), 16 * math.sin(a0)), (20 * math.cos(am), 20 * math.sin(am)),
                    (16 * math.cos(a1), 16 * math.sin(a1))]
            for p, q in zip(ends, ends[1:]):
                mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
                bulge = 1 + 0.8 / math.hypot(mx, my)
                edges.append(bd.Edge.make_three_point_arc(p, (mx * bulge, my * bulge), q))
        gear = bd.extrude(bd.Face(bd.Wire(edges)), 8)
        pocket = bd.Box(60, 40, 20) - bd.Pos(0, 0, 5) * bd.Box(30, 20, 10.001)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(23, -37, 61)):
            roots = cnc(_part(turn * gear), material="aluminum")
            self.assertEqual({i["reason"] for i in roots.measurements["sharp_edges"]["items"]}, {"vertical_corner"})
            self.assertEqual(roots.measurements["sharp_edges"]["count"], 12)
            self.assertFalse(roots.ok)
            corners = cnc(_part(turn * pocket), material="aluminum")
            self.assertEqual(sum(c["sharp"] for c in corners.measurements["internal_corners"]["items"]), 4)
            self.assertIn("cnc.internal_corner_sharp", _codes(corners))

    def test_an_opening_beside_a_cavity_makes_no_corner_of_it(self) -> None:
        # an 8 mm port through a wall is no way in for a disc cutter's shank along the 25 mm corners
        box = bd.Box(80, 60, 30) - bd.Pos(0, 0, 2.5) * bd.Box(70, 50, 25.001)
        port = box - bd.Pos(-37.5, 0, 0) * bd.Rot(0, 90, 0) * bd.Cylinder(4, 10)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(23, -37, 61)):
            result = cnc(_part(turn * port), material="aluminum")
            self.assertEqual(sum(c["sharp"] for c in result.measurements["internal_corners"]["items"]), 4, turn)
            self.assertNotIn("cnc.special_cutter", _codes(result))
            self.assertFalse(result.ok)

    def test_an_edge_is_made_only_where_every_station_along_it_is_reached(self) -> None:
        block = bd.Box(60, 40, 20) - bd.Pos(0, 0, 5) * bd.Box(30, 20, 10.001)  # pocket floor at z = 0
        # a 0.5 mm window at the corner's mid-height is no way to side-mill its 10 mm
        window = block - bd.Pos(14.75, -15, 5) * bd.Box(0.5, 10.2, 0.5)
        # a front wall cut down to a 2 mm lip: the back corners side-mill above it, not its bottom 2 mm
        tray = block - bd.Pos(-22.5, 0, 6.5) * bd.Box(15, 40.01, 9.001)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(0, 0, 30)):
            self.assertIn("cnc.internal_corner_sharp", _codes(cnc(_part(turn * window), material="aluminum")))
            result = cnc(_part(turn * tray), material="aluminum")
            back = [c for c in result.measurements["internal_corners"]["items"] if c["height_mm"] > 9]
            self.assertEqual(len(back), 2, turn)
            for corner in back:
                # the stretch none reaches is the corner's place, its length said
                self.assertLess(corner["xyz"][2], 2.0)
                self.assertTrue(1.5 < corner["unreached_mm"] < 3.0, corner)
                self.assertIn("reached by no tool", corner["unreached"])

    def test_v_notches_and_obtuse_roots_are_made_at_any_turn_each_direction_a_setup(self) -> None:
        plate = bd.Box(100, 60, 8)
        for angle, own in ((60.0, [1]), (120.0, [None])):
            w = 60 * math.tan(math.radians(angle / 2))
            v = bd.extrude(bd.make_face(bd.Polyline((0, 0), (-w, 60), (w, 60), close=True)), 20, both=True)
            for turn in (0.0, 20.0):
                result = cnc(_part(plate - bd.Pos(0, 18, 0) * bd.Rot(0, 0, turn) * v), material="aluminum")
                # a 120 deg V is a 120 deg chamfer mill's, its cone the V as drawn: nothing to say at any turn
                self.assertEqual(_judged(result), set(), (angle, turn))
                self.assertEqual(result.measurements["sharp_edges"]["by_tool"], {"chamfer_mill": 1}, (angle, turn))
                self.assertTrue(result.ok)
                # a 60 deg V's chamfer mill is a setup of its own along its bisector, counted even along a machine
                # axis; a 120 deg one is obtuse, made in the setups of its flanks
                setup = result.measurements["setups"]["items"][0]
                self.assertEqual([d.get("sharp_edges") for d in setup["directions"]], own, (angle, turn))
        counts = []
        for void in (100.0, 120.0):
            wedge = bd.extrude(bd.make_face(bd.Polyline((0, 0), (80, 0), (80 * math.cos(math.radians(void)),
                                                                         80 * math.sin(math.radians(void))),
                                                       close=True)), 20, both=True)
            for cut, turn in ((0, bd.Rot(0, 0, 0)), (20, bd.Rot(0, 0, 0)), (20, bd.Rot(23, -37, 61)), (35, bd.Rot(0, 0, 0))):
                result = cnc(_part(turn * (plate - bd.Pos(0, 5, 0) * bd.Rot(0, 0, cut) * wedge)), material="aluminum")
                # a 100 deg root is no chamfer mill's: side-milled, it keeps the tool's radius (obtuse_root, its
                # faces square to no setup counted: two more); a 120 deg one is a 120 deg chamfer mill's
                roots = [i for i in result.measurements["sharp_edges"]["items"] if abs(i["void_angle_deg"] - void) < 1e-3]
                self.assertEqual([(i["reason"], i["more_setups"]) for i in roots],
                                 [("obtuse_root", "two more setups")] if void == 100.0 else [], (void, cut))
                self.assertTrue(result.ok, (void, cut))
                # an obtuse root: made in the setups that make its flanks, whatever the turn -- none of its own
                setup = result.measurements["setups"]["items"][0]
                self.assertEqual(sum(d.get("sharp_edges") or 0 for d in setup["directions"]), 0, (void, cut))
                counts.append(setup["setup_count"])
        self.assertEqual(set(counts), {counts[0]})

    def test_five_axes_follow_a_curved_v_three_present_one_direction(self) -> None:
        # a 90 deg V groove around a shaft: its bisector turns all the way round, no one direction makes it; five
        # simultaneous axes follow it with a chamfer mill, three only warn that more axes would
        shaft = bd.Cylinder(10, 40) - bd.revolve(bd.Plane.XZ * bd.make_face(
            bd.Polyline((7, 0), (10.5, 3.5), (10.5, -3.5), close=True)), bd.Axis.Z)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(23, -37, 61)):
            three = cnc(_part(turn * shaft), material="aluminum")
            self.assertEqual([i["reason"] for i in three.measurements["sharp_edges"]["items"]], ["other_axes"], turn)
            five = cnc(_part(turn * shaft), material="aluminum", axes=5)
            self.assertEqual(five.measurements["sharp_edges"]["by_tool"], {"chamfer_mill": 1}, turn)

    def test_a_hex_socket_s_pointed_floor_adds_no_setup(self) -> None:
        # a hex socket with a six-facet pyramid floor: its facets' creases are obtuse, made in the setup that
        # reaches the socket; the count is the flat-floored socket's
        def socket(point: bool) -> Any:
            hexagon = bd.RegularPolygon(3, 6)
            part = bd.Box(20, 20, 15) - bd.Pos(0, 0, 1.5) * bd.extrude(hexagon, 6.001)
            if point:
                part -= bd.Pos(0, 0, 1.5) * bd.Rot(180, 0, 0) * bd.extrude(hexagon, 1.7, taper=55)
            return part
        read = [cnc(_part(socket(point)), material="aluminum").measurements["setups"]["items"][0]["setup_count"]
                for point in (False, True)]
        self.assertEqual(read[0], read[1])


class DiscCutterTest(unittest.TestCase):
    """A disc cutter -- T-slot, keyseat, dovetail -- makes an edge only where its disc can get in; one of no standard
    angle is a special cutter, said with its angle."""

    def test_a_disc_must_pass_its_way_in(self) -> None:
        # (one placement: the turns are FrameTest's) a 20 mm chamber behind a 4 mm bore: a disc reaching its wall
        # from inside the bore is wider than it; behind a 12 mm bore it is a keyseat cutter's
        blk = bd.Box(24, 24, 12, align=(A.CENTER, A.CENTER, A.MIN))
        chamber = bd.Pos(0, 0, 6) * bd.Cylinder(10, 3)
        bottle = cnc(_part(blk - bd.Cylinder(2, 40) - chamber), material="aluminum")
        self.assertEqual({i["reason"] for i in bottle.measurements["sharp_edges"]["items"]}, {"no_way_in"})
        self.assertFalse(bottle.ok)
        groove = cnc(_part(blk - bd.Cylinder(6, 40) - chamber), material="aluminum")
        self.assertEqual(groove.measurements["sharp_edges"]["by_tool"], {"keyseat_cutter": 2})
        self.assertTrue(groove.ok)

    def test_a_v_or_a_dovetail_of_no_standard_angle_is_a_special_cutter(self) -> None:
        plate = bd.Box(80, 40, 12, align=(A.CENTER, A.CENTER, A.MIN))
        h = 3.0 * math.tan(math.radians(75 / 2))
        v75 = plate - bd.extrude(bd.Plane.YZ.offset(-41) * bd.make_face(
            bd.Polyline((-h, 12.01), (h, 12.01), (0, 9), close=True)), 82)
        three = cnc(_part(v75), material="aluminum")
        [special] = [i for i in three.measurements["access"]["items"] if i["kind"] == "special_cutter"]
        self.assertIn("v cutter of 75 deg", special["cutter"])
        self.assertEqual(_judged(three), {"cnc.special_cutter"})
        # five axes tilt a standard chamfer mill to each flank in turn: no special cutter
        five = cnc(_part(v75), material="aluminum", axes=5)
        self.assertEqual(five.measurements["sharp_edges"]["by_tool"], {"chamfer_mill": 1})
        self.assertEqual(_judged(five), set())
        # a Parker O-ring dovetail (66 deg): its cutter plunges through the 3 mm neck and moves under each lip
        off = 2.5 / math.tan(math.radians(66))
        ring = bd.revolve(bd.Plane.XZ * bd.make_face(bd.Polyline(
            (23.5, 12.01), (26.5, 12.01), (26.5 + off, 9.5), (23.5 - off, 9.5), close=True)), bd.Axis.Z)
        result = cnc(_part(bd.Box(80, 80, 12, align=(A.CENTER, A.CENTER, A.MIN)) - ring), material="aluminum")
        [special] = [i for i in result.measurements["access"]["items"] if i["kind"] == "special_cutter"]
        self.assertIn("dovetail cutter of 66 deg", special["cutter"])
        self.assertTrue(result.ok)

    def test_a_slot_cutter_s_narrow_neck_is_said_where_it_narrows(self) -> None:
        # a T-slot through along x, its neck 12 wide for half its length and 4 for the rest, the undercut 8 tall
        part = bd.Box(80, 40, 40) - bd.Pos(-20, 0, 13) * bd.Box(41, 12, 14.01) - bd.Pos(20, 0, 13) * bd.Box(41, 4, 14.01) \
            - bd.Pos(0, 0, 2) * bd.Box(82, 20, 8)
        result = cnc(_part(part), material="aluminum")
        narrow = [i for i in result.measurements["sharp_edges"]["items"] if i["reason"] == "narrow_opening"]
        self.assertTrue(narrow)
        self.assertTrue(all(abs(i["opening_mm"] - 4.0) < 0.05 and abs(i["recess_mm"] - 8.0) < 0.05 for i in narrow))
        self.assertEqual({f.severity for f in result.findings if f.code == "cnc.sharp_internal_edge"}, {"warning"})
        self.assertTrue(result.ok)

    def test_an_obstacle_between_stations_is_found_and_measured(self) -> None:
        # a 10 mm channel along a 40 mm block, a 3 mm bridge over it between two stations: the floor's edges
        # under it are unmade for its 3 mm
        block = bd.Box(40, 30, 20, align=(A.CENTER, A.CENTER, A.MIN)) - bd.Pos(0, 0, 15) * bd.Box(42, 10, 10.01)
        result = cnc(_part(block + bd.Pos(-6.9, 0, 18.5) * bd.Box(3, 10, 3)), material="aluminum")
        under = [i for i in result.measurements["sharp_edges"]["items"] if i.get("unreached_mm")]
        self.assertEqual(len(under), 2)
        for item in under:
            self.assertAlmostEqual(item["unreached_mm"], 3.0, delta=0.25)
            self.assertEqual(item["reason"], "blocked")
            self.assertLess(abs(item["xyz"][0] + 6.9), 1.0)

    def test_a_slot_cutter_s_groove_adds_no_setup(self) -> None:
        # an O-ring groove round a boss: cut by a slot cutter from above, its bottom asks no side of its own
        boss = bd.Box(80, 80, 6, align=(A.CENTER, A.CENTER, A.MIN)) + bd.Pos(0, 0, 6) * bd.Cylinder(
            15, 25, align=(A.CENTER, A.CENTER, A.MIN))
        groove = bd.Pos(0, 0, 16.25) * bd.Cylinder(16, 2.5) - bd.Pos(0, 0, 16.25) * bd.Cylinder(13, 2.6)
        setup = cnc(_part(boss - groove), material="aluminum").measurements["setups"]["items"][0]
        self.assertEqual(setup["setup_count"], 1)

    def test_the_least_angle_is_searched_at_an_end_too(self) -> None:
        # sampled least at an end: the least between it and its neighbour is found (here at a tenth of the edge)
        from cad.build123d import _dfm_brep

        real = _dfm_brep.edge_angles
        try:
            _dfm_brep.edge_angles = lambda part, edge, f: (None, 10.0 + 100.0 * (np.asarray(f) - 0.1) ** 2)
            fractions = np.array([0.0, 0.5, 1.0])
            _, angles = _dfm_brep.least_edge_angle(None, None, fractions, 10.0 + 100.0 * (fractions - 0.1) ** 2)
        finally:
            _dfm_brep.edge_angles = real
        self.assertAlmostEqual(float(angles.min()), 10.0, places=6)


class FrameTest(unittest.TestCase):
    """A part is machined in its own frame: turned in its model, its verdicts and figures stay."""

    def test_a_turned_part_reads_as_drawn(self) -> None:
        plate = bd.Box(60, 40, 16) - _pocket(30, 20, 6, 3, 8)
        plate -= bd.Pos(22, 12, 0) * bd.Cylinder(2.5, 30)
        plate -= bd.Pos(-22, -12, 8) * _drill(4.2, 10)

        def read(shape: Any) -> tuple[Any, ...]:
            result = cnc(_part(shape), material="aluminum")
            report = result.measurements
            verdicts = sorted((f.severity, f.code) for f in result.findings if f.severity != "info")
            return (result, verdicts, report["setups"]["items"][0]["setup_count"],
                    sorted(round(h["depth_to_diameter"], 3) for h in report["holes"]["items"]),
                    sorted(round(c["radius_mm"], 3) for c in report["internal_corners"]["items"]))

        drawn = read(plate)
        self.assertFalse(drawn[0].measurements["machine"]["frames"][0]["turned"])
        # a quarter turn is still square to the world: no frame of its own is needed
        for turn, own in ((bd.Rot(0, 0, 30), True), (bd.Rot(17, 23, 41), True), (bd.Rot(90, 0, 0), False)):
            turned = read(turn * plate)
            self.assertEqual(turned[1:], drawn[1:])
            frame = turned[0].measurements["machine"]["frames"][0]
            self.assertEqual(frame["turned"], own)
            # places are the part's own: the hole's centre is where the turn put it
            hole = min(turned[0].measurements["holes"]["items"], key=lambda h: h["diameter_mm"])
            expected = (turn * bd.Pos(-22, -12, 3)).position
            self.assertLess((bd.Vector(*hole["xyz"]) - expected).length, 0.05)


    def test_a_hexagonal_window_s_corners_are_sharp_in_every_turn(self) -> None:
        # a 120-degree void is a chamfer mill's shoulder only where one face is the mill's cone: a face along
        # the axis reads its normal's 1e-16 off square in a turned part, and is none
        window = bd.Box(100, 60, 8) - bd.extrude(bd.RegularPolygon(10, 6), 10, both=True)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(90, 0, 0), bd.Rot(23, -37, 61), bd.Rot(0, 0, 17)):
            result = cnc(_part(turn * window), material="aluminum")
            corners = [c for c in result.measurements["internal_corners"]["items"] if c["sharp"]]
            self.assertEqual(len(corners), 6, turn)
            self.assertFalse(result.ok)

    def test_a_many_sided_pocket_s_corners_are_the_flank_s(self) -> None:
        # a 24-gon's 165-degree corners along the axis: the end mill's flank makes them, its radius leaving
        # R (1/sin(v/2) - 1) in each -- said, a warning only past 0.05 mm (a 20 mm tool's 0.086 mm)
        plate = bd.Box(80, 80, 12, align=(A.CENTER, A.CENTER, A.MIN))
        pocket = plate - bd.Pos(0, 0, 6) * bd.extrude(bd.RegularPolygon(20, 24), 6.01)
        residue = 1.25 * (1 / math.sin(math.radians(165 / 2)) - 1)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(0, 0, 7) * bd.Pos(3, -2, 1), bd.Rot(90, 0, 0)):
            result = cnc(_part(turn * pocket), material="aluminum")
            self.assertTrue(result.ok, turn)
            flanks = [i for i in result.measurements["sharp_edges"]["items"] if i["made_by"] == "end_mill_flank"]
            self.assertEqual(len(flanks), 24, turn)
            self.assertAlmostEqual(max(i["deviation_mm"] for i in flanks), residue, places=3)
            self.assertIn("cnc.flank_corners", _codes(result))
            self.assertNotIn("cnc.flank_corner_residue", _codes(result))
        coarse = cnc(_part(pocket), material="aluminum", tools="20")
        self.assertEqual([f.severity for f in coarse.findings if f.code == "cnc.flank_corner_residue"], ["warning"])


class TurnedLiveToolingTest(unittest.TestCase):
    def test_a_square_keyway_end_is_a_sharp_corner_a_round_one_is_not(self) -> None:
        shaft = bd.Rot(0, 90, 0) * bd.Cylinder(12, 80)
        square = shaft - bd.Pos(0, 0, 12) * bd.Box(30, 6, 6)
        result = cnc(_part(square, "shaft"), turning=True, material="aluminum")
        self.assertIn("cnc.internal_corner_sharp", _codes(result))
        self.assertEqual(result.measurements["pockets"]["count"], 1)
        rounded = shaft - bd.Pos(0, 0, 12) * bd.extrude(bd.SlotCenterToCenter(24, 6), 3, both=True)
        self.assertNotIn("cnc.internal_corner_sharp", _codes(cnc(_part(rounded, "shaft"), turning=True)))


class NarrowCornerTest(unittest.TestCase):
    def test_a_corner_too_narrow_for_its_radius_names_how_it_is_made(self) -> None:
        # a hub's 6 mm keyway off its bore, 22 deep: a third of the depth (7.3 mm) does not fit its 6 mm width --
        # the hint says so and names the broach; a 6 mm slot in a block, the same depth, names EDM
        hub = bd.Cylinder(20, 22) - bd.Cylinder(8, 30) - bd.Pos(0, 9, 0) * bd.Box(6, 6, 30)
        block = bd.Box(60, 40, 22) - bd.Pos(0, 0, 3) * bd.Box(30, 6, 22)
        for part, said in ((hub, "broached or slotted"), (bd.Rot(0, 0, 30) * bd.Pos(1, 2, 0) * hub, "broached"),
                           (block, "plan EDM")):
            result = cnc(_part(part), material="aluminum")
            hints = {f.hint for f in result.findings if f.code == "cnc.internal_corner_sharp"}
            self.assertTrue(hints, said)
            for hint in hints:
                self.assertIn("6 mm width takes a radius of 3 mm at most", hint)
                self.assertIn(said, hint)
                self.assertNotIn("7.33", hint.split("recommended")[-1])


class UnroundedTest(unittest.TestCase):
    def test_a_ratio_a_hair_over_its_limit_fails(self) -> None:
        # 20.0002 / 5 = 4.00004: four decimals would read 4.0 and pass the 4 D recommendation
        result = cnc(_part(bd.Box(20, 20, 20.0002) - bd.Cylinder(2.5, 30)))
        self.assertIn("cnc.hole_depth", _codes(result))


class RulesTest(unittest.TestCase):
    def test_the_rules_cite_what_they_use_and_the_options_resolve(self) -> None:
        for rule in rules_side.RULES.rules:
            self.assertTrue(rule.id.startswith("cnc."), rule.id)
            self.assertTrue(rules_side.RULES.source(rule.source).url.startswith("https://"))
        resolved = manufacturing.options("step", "cnc", {"tools": "6,3", "material": "6061"})
        context = rules_side.context({}, resolved)
        self.assertEqual((context["min_tool_mm"], context["wall_class"]), (3.0, "metal"))
        with self.assertRaisesRegex(ValueError, "--tools"):
            manufacturing.options("step", "cnc", {"tools": "3,x"})
        with self.assertRaisesRegex(ValueError, "--rules is not cnc's"):
            manufacturing.options("step", "cnc", {"rules": "generic"})

    def test_a_live_shape_is_checked_as_its_step_is(self) -> None:
        part = _part(bd.Box(40, 30, 12) - _pocket(10, 10, 4, 0.0, 6), "block")
        live = cnc(part)
        written = _check(part)
        self.assertEqual(sorted(f.location for f in live.findings if f.code == "cnc.internal_corner_sharp"),
                         sorted(f.location for f in written.findings if f.code == "cnc.internal_corner_sharp"))
        json.dumps(live.measurements, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
