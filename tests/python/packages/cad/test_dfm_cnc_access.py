#!/usr/bin/env python3

"""The CNC check's access on exact geometry, on tiny parts built here: which faces and edges a tool reaches,
from which setups (three, four or five axes), an end mill's flank from the side, a disc cutter's way in, and
one finding for what one feature causes. The check's other measurements are ``test_dfm_cnc_features``; the
planted-defect corpus is ``test_dfm_cnc_corpus``."""

from __future__ import annotations

import math
import unittest
from typing import Any

import build123d as bd
import numpy as np

from cad.build123d import cnc
from tests.python.support.dfm_cnc import A, _check, _codes, _judged, _part, _pocket


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
        # a void with corners is one defect too: its edges are no tool's to make, sharp or not
        boxed = cnc(_part(bd.Box(30, 30, 30) - bd.Box(10, 10, 10)))
        self.assertEqual(_judged(boxed), {"cnc.enclosed_void"})
        self.assertEqual(boxed.measurements["sharp_edges"]["items"], [])

    @staticmethod
    def _chamber(radius: float, round_: float = 1.0) -> Any:
        """A block with a 10 mm bore from its top into a round chamber of ``radius``, its edges rounded."""
        chamber = bd.Pos(0, 0, -5) * bd.Cylinder(radius, 6)
        if round_:
            chamber = bd.fillet(chamber.edges(), round_)
        return bd.Box(40, 40, 40) - bd.Pos(0, 0, 10) * bd.Cylinder(5, 30) - chamber

    def test_a_face_no_tool_reaches_is_an_error_rounded_or_not(self) -> None:
        # no straight line reaches the chamber's faces; the disc that reaches a 12 mm wall from a 10 mm bore is
        # 14 mm across and does not pass it. Rounding the chamber's edges used to turn that into a pass
        for shape, axes in ((self._chamber(12.0, 2.0), 3), (self._chamber(12.0, 2.0), 5), (self._chamber(12.0, 0.0), 3),
                            # a ball cavity behind a 3 mm vent; a passage that turns twice
                            (bd.Box(30, 30, 30) - bd.Sphere(8) - bd.Pos(0, 0, 10) * bd.Cylinder(1.5, 10.01), 3),
                            (bd.Box(60, 40, 40) - bd.Pos(-15, 0, 10) * bd.Cylinder(3, 20) - bd.Pos(-15, 0, 0) * bd.Sphere(3)
                             - bd.Rot(0, 90, 0) * bd.Cylinder(3, 30) - bd.Pos(15, 0, 0) * bd.Sphere(3)
                             - bd.Pos(15, 0, -7) * bd.Cylinder(3, 14), 3)):
            result = cnc(_part(shape), axes=axes)
            self.assertFalse(result.ok)
            # one recess, one finding
            self.assertEqual([f.severity for f in result.findings if f.code == "cnc.no_line_of_sight"], ["error"])

    def test_a_recess_a_disc_cutter_gets_into_is_a_warning_up_to_its_limit(self) -> None:
        # a disc no wider than the 10 mm bore reaches 5 mm past its wall: a chamber of 20 mm at most
        for radius, reached in ((7.0, True), (10.0, True), (10.2, False)):
            result = cnc(_part(self._chamber(radius)))
            [item] = [i for i in result.measurements["access"]["items"] if i["kind"] == "no_line_of_sight"]
            self.assertEqual((item["disc_reach"], result.ok), (reached, reached), radius)
            self.assertEqual(item["face_count"], 5)
            self.assertIn("cnc.undercut" if reached else "cnc.no_line_of_sight", _judged(result))

    def test_a_verdict_stands_whatever_the_part_s_placement(self) -> None:
        chamber = self._chamber(12.0, 2.0)
        drawn = cnc(_part(chamber))
        for turn in (bd.Rot(0.3, 0.15, 0), bd.Pos(13, -7, 5) * bd.Rot(17, 23, 41)):
            turned = cnc(_part(turn * chamber))
            self.assertEqual(sorted((f.severity, f.code) for f in turned.findings),
                             sorted((f.severity, f.code) for f in drawn.findings))
            self.assertEqual(turned.measurements["setups"]["items"][0]["setup_count"],
                             drawn.measurements["setups"]["items"][0]["setup_count"])

    def test_the_setups_count_the_same_however_the_stock_is_said(self) -> None:
        # the stock as it comes has no face to cut; the same block with a pocket has one setup, and typing the
        # stock the part's own box changes nothing
        self.assertEqual(cnc(_part(bd.Box(20, 20, 20))).measurements["setups"]["items"][0]["setup_count"], 0)
        plate = _part(bd.Box(60, 40, 10) - _pocket(20, 20, 5, 2, 5) - bd.Pos(20, 0, 2.5) * bd.Box(4, 40, 5))
        for stock in (None, "60x40x10", "40x10x60"):
            self.assertEqual(cnc(plate, stock=stock).measurements["setups"]["items"][0]["setup_count"], 1, stock)
        self.assertEqual(cnc(plate, stock="60x40x12").measurements["setups"]["items"][0]["setup_count"], 2)

    def test_a_hole_is_one_setup_along_its_axis(self) -> None:
        # two legs at 60 degrees, a hole in each: the profile, the flat leg's hole from the side nothing overhangs,
        # and the tilted hole's own setup -- its wall, glimpsed from three machine directions, asks none of them
        leg = bd.Box(40, 30, 5) - bd.Pos(5, 0, 0) * bd.Cylinder(3, 5)
        bracket = bd.Pos(20, 0, 0) * leg + bd.Rot(0, -60, 0) * bd.Pos(20, 0, 0) * leg
        for turn in (bd.Rot(0, 0, 0), bd.Rot(17, 23, 41)):
            setup = cnc(_part(turn * bracket)).measurements["setups"]["items"][0]
            self.assertEqual((setup["setup_count"], len(setup["inclined_directions"])), (3, 1))


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
        hint = next(f.hint for f in result.findings if f.code == "cnc.special_cutter")
        self.assertIn("standard size", hint)
        # a through slot whose walls lean 4 degrees back past square (86-degree dovetails): a wall drafted the
        # wrong way, not a dovetail drawn as one -- the hint asks it squared; nothing names a function
        lean = 2.5 * math.tan(math.radians(4))
        drafted = plate - bd.extrude(bd.Plane.YZ.offset(-41) * bd.make_face(bd.Polyline(
            (-5, 12.01), (5, 12.01), (5 + lean, 9.5), (-5 - lean, 9.5), close=True)), 82)
        finding = next(f for f in cnc(_part(drafted), material="aluminum").findings if f.code == "cnc.special_cutter")
        self.assertIn("leans 4 degree(s) back past square: square it", finding.hint)
        self.assertNotIn("_", finding.message.split("(")[-1] + finding.hint)

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


if __name__ == "__main__":
    unittest.main()
