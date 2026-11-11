#!/usr/bin/env python3

"""The CNC check's measurements on exact geometry, family by family, on tiny parts built here: each expected
figure is the construction's (a pocket cut 12 deep is 12 deep, a 118-degree drill point is 118 degrees) --
holes, pockets and cavities, walls, gaps and edges, turning and threads, stock, a part turned or occurring
twice -- and the rays the check casts and its rules. Which tool reaches what is
``test_dfm_cnc_access``; the planted-defect corpus is ``test_dfm_cnc_corpus``; this is the facts each
verdict reads."""

from __future__ import annotations

import json
import math
import unittest
from typing import Any

import build123d as bd
import numpy as np

from cad._internal import manufacturing
from cad._internal.dfm import cnc as rules_side
from cad.build123d import _dfm_cnc_holes, cnc
from tests.python.support.dfm_cnc import A, _check, _codes, _judged, _part, _pocket


def _drill(diameter: float, depth: float, point: float = 118.0) -> Any:
    radius = diameter / 2
    tip = radius / math.tan(math.radians(point / 2))
    body = bd.Pos(0, 0, 1) * bd.Cylinder(radius, depth + 1, align=(A.CENTER, A.CENTER, A.MAX))
    return body + bd.Pos(0, 0, -depth) * bd.Cone(0.0, radius, tip, align=(A.CENTER, A.CENTER, A.MAX))


class BatchedRaysTest(unittest.TestCase):
    """The rays a CNC check casts many at a time (``Model.escape_all``, ``first_all``, ``blocked_each``: their
    boxes tested together) answer as each cast alone; and a point is in the material as the kernel's solid
    classifier says (``Model.solid``, a ray met edge-on told along the next of three)."""

    def _model(self) -> Any:
        from cad.build123d import _dfm_brep, _dfm_cnc_model

        block = bd.Box(60, 40, 30) - bd.Pos(0, 0, 10) * bd.Cylinder(8, 30) - bd.Pos(18, 8, 15) * bd.Sphere(6)
        # a slanted face (a wedge's chamfer), a torus round a boss and a hole through
        block = block - bd.Pos(30, 0, 15) * bd.Rot(0, 35, 20) * bd.Box(20, 80, 20)
        block = block + bd.Pos(-20, -10, 15) * bd.Torus(6, 2)
        return _dfm_cnc_model.Model(_dfm_brep.Part("p", "p", block))

    def test_batched_rays_answer_as_each_alone(self) -> None:
        from unittest import mock

        from cad.build123d import _dfm_cnc_model

        rng = np.random.default_rng(5)
        batched, alone = self._model(), self._model()
        # a batch is as many rays as keep rays x faces under a bound, whatever the part's face count: here 8 a batch
        self.assertEqual(batched._batch(), 256)
        patcher = mock.patch.object(_dfm_cnc_model, "BATCH_PAIRS", 100)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(batched._batch(), 8)
        origins = rng.uniform((-40, -30, -25), (40, 30, 25), size=(300, 3))
        ways = rng.normal(size=(300, 3))
        ways /= np.linalg.norm(ways, axis=1)[:, None]
        for d in (np.array([0.0, 0.0, 1.0]), np.array([0.6, 0.0, 0.8]), ways[0]):
            normals = np.tile(-d, (len(origins), 1))
            self.assertEqual(batched.escape_all(origins, normals, d).tolist(),
                             [alone.escapes(o, n, d) for o, n in zip(origins, normals)])
        for mine, o, w in zip(batched.first_all(origins, ways), origins, ways):
            theirs = alone.first(o, w)
            self.assertEqual(mine is None, theirs is None)
            if mine is not None and theirs is not None:
                # the same crossing (``first_all`` normalizes its directions once more: the last digit may differ)
                self.assertEqual(mine.face, theirs.face)
                self.assertAlmostEqual(mine.distance, theirs.distance, delta=1e-9)
        self.assertEqual(batched.blocked_each(origins, ways).tolist(), [alone.blocked(o, w) for o, w in zip(origins, ways)])

    def test_a_point_is_in_the_material_as_the_classifier_says(self) -> None:
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_IN

        model = self._model()
        rng = np.random.default_rng(9)
        points = rng.uniform((-35, -25, -18), (35, 25, 18), size=(400, 3))
        classifier = BRepClass3d_SolidClassifier(model.part.shape.wrapped)
        expected = []
        for point in points:
            classifier.Perform(gp_Pnt(*point), 1e-6)
            expected.append(classifier.State() == TopAbs_IN)
        np.testing.assert_array_equal(model.solid(points), expected)

    def test_a_point_whose_ray_meets_an_edge_or_that_lies_on_a_face_is_classified_as_the_kernel_does(self) -> None:
        # A grid of whole millimetres over a part drawn in whole millimetres: rays from it pass exactly through
        # edges (from inside an open slot, one leaves through the slot wall's top edge, which reads as material by
        # that wall's normal), and a fifth of its points lie on a face (the boundary: not in the material).
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_IN

        from cad.build123d import _dfm_brep, _dfm_cnc_model

        block = bd.Box(20, 12, 12) - bd.Pos(0, 0, 3) * bd.Box(6, 20, 6) - bd.Pos(6, 2, -3) * bd.Cylinder(2, 20)
        model = _dfm_cnc_model.Model(_dfm_brep.Part("p", "p", block))
        points = np.mgrid[-10:10.5:1.0, -6:6.5:1.0, -6:6.5:1.0].reshape(3, -1).T
        classifier = BRepClass3d_SolidClassifier(block.wrapped)
        expected = []
        for point in points:
            classifier.Perform(gp_Pnt(*point), 1e-6)
            expected.append(classifier.State() == TopAbs_IN)
        np.testing.assert_array_equal(model.solid(points), expected)


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
        # a round corner is a feature of its own, as a sharp one is: one finding a corner, at its own fillet's
        # face (refs[0], the face to edit), the cavity's floor after it
        corners = tight.measurements["internal_corners"]["items"]
        self.assertEqual(sorted(f.location for f in found), sorted(c["corner"] for c in corners))
        self.assertEqual(len({f.location for f in found}), 4)
        (floor,) = {c["pocket"] for c in corners}
        self.assertTrue(all(f.refs == [f.location, floor] for f in found))
        self.assertIn("under the 1.5 mm minimum", found[0].message)
        self.assertIn(f"a corner of the cavity at {floor}", found[0].message)
        self.assertIn("cnc.internal_corner_radius x4", tight.summary)

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
        # a corner is a feature: one finding a corner, at its own edge, the cavity's floor among its refs; the
        # rule's hint and its source are said once for the four
        self.assertEqual(sorted(f.location for f in found), sorted(c["edge"] for c in corners))
        self.assertEqual(len({c["edge"] for c in corners}), 4)
        self.assertEqual({c["pocket"] for c in corners}, {"part/face 11"})
        self.assertTrue(all("part/face 11" in f.refs and f.refs[0] == f.location for f in found))
        self.assertTrue(all(f.source.startswith("text-to-cad, ") for f in found))  # the 0.025 mm is our own floor
        self.assertEqual(sum("cnc.internal_corner_sharp, 4 place(s)" in line for line in result.human_lines()), 1)
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


class PartsTest(unittest.TestCase):
    def test_each_solid_of_a_part_is_judged_as_its_own(self) -> None:
        # a block floating 1 mm over a plate's pocket, in one compound: no obstacle to the plate's tools, no gap
        # to it, and no share of its stock or setups
        plate = bd.Box(100, 60, 10) - _pocket(40, 30, 5, 3, 5)
        both = bd.Compound([plate, bd.Pos(0, 0, 11) * bd.Box(50, 40, 10)])
        result = cnc(_part(both, "pair"))
        self.assertTrue(result.ok)
        # said once, by the warning every process gives of such a part, with how this one reads it
        self.assertEqual(_judged(result), {"several_solids"})
        (said,) = [f for f in result.findings if f.code == "several_solids"]
        self.assertIn("each is judged as a part of its own", said.message)
        self.assertEqual(sorted(i["setup_count"] for i in result.measurements["setups"]["items"]), [0, 1])
        self.assertEqual([i["size_mm"] for i in result.measurements["stock"]["items"]],
                         [[100.0, 60.0, 10.0], [50.0, 40.0, 10.0]])
        self.assertIn("2 part(s)", result.summary)
        # its refs are the whole part's: the pocket's corner faces resolve in the compound
        for corner in result.measurements["internal_corners"]["items"]:
            ordinal = int(corner["corner"].rsplit(" ", 1)[1])
            self.assertEqual(both.faces()[ordinal - 1].geom_type, bd.GeomType.CYLINDER)

    def test_a_part_of_too_many_faces_is_not_measured_and_said(self) -> None:
        from unittest import mock

        from cad.build123d import _dfm_cnc

        with mock.patch.object(_dfm_cnc, "FACE_BUDGET", 5):
            result = cnc(_part(bd.Box(20, 20, 20)))
        self.assertFalse(result.ok)
        self.assertTrue(result.measurements["partial"])
        self.assertIn("over the 5 a check measures", result.measurements["model"]["error"])

    def test_a_part_far_past_any_general_machine(self) -> None:
        def plate(length: float) -> Any:
            return _part(bd.Box(length, 300, 20) - bd.Pos(0, 0, 5) * bd.Cylinder(20, 10))

        self.assertEqual(_judged(cnc(plate(1900))), set())
        self.assertEqual(_judged(cnc(plate(2200))), {"cnc.part_size"})
        # past twice a general shop's it is a specialist's machine: said, and made -- size alone fails no part
        far = cnc(plate(4500))
        self.assertTrue(far.ok)
        self.assertEqual(_judged(far), {"cnc.part_size_limit"})
        self.assertTrue(cnc(_part(bd.Cylinder(550, 100)), turning=True).ok)
        # a stock the user gave that the part does not fit is the error
        self.assertIn("cnc.stock_too_small", {f.code for f in cnc(plate(4500), stock="4000x300x20").findings
                                              if f.severity == "error"})


class TallAndDeepTest(unittest.TestCase):
    def test_a_thin_feature_standing_tall_is_a_warning(self) -> None:
        pin = cnc(_part(bd.Box(40, 40, 5) + bd.Pos(0, 0, 22.5) * bd.Cylinder(1, 40)))
        self.assertTrue(pin.ok)
        self.assertEqual(_judged(pin), {"cnc.tall_feature"})
        [wall] = [w for w in pin.measurements["walls"]["items"] if w["standing"]]
        self.assertEqual((wall["thickness_mm"], wall["height_mm"], wall["height_to_thickness"]), (2.0, 40.0, 20.0))
        # a plate is no standing feature, with a boss on it or not; nor is a dovetail's lip, a wedge
        plate = cnc(_part(bd.Box(100, 60, 3) + bd.Pos(0, 0, 6.5) * bd.Cylinder(8, 10)))
        self.assertEqual(_judged(plate), set())

    def test_a_slot_no_tool_reaches_the_floor_of(self) -> None:
        def slot(width: float, depth: float) -> Any:
            return _part(bd.Box(40, 40, depth + 10) - bd.Pos(0, 0, 5) * bd.Box(40, width, depth))

        def closed(width: float, depth: float) -> Any:  # a slot shut at both ends, round ones: an end mill's alone
            cut = bd.Pos(0, 0, 5 - depth / 2) * bd.extrude(bd.SlotOverall(30, width), depth)
            return _part(bd.Box(40, 40, depth + 10) - cut)

        # 15 widths deep is slow work (a warning); 33 is past what any end mill of its width reaches
        self.assertTrue(cnc(slot(2.0, 30.0)).ok)
        self.assertIn("cnc.pocket_depth_limit", {f.code for f in cnc(closed(1.2, 40.0)).findings
                                                 if f.severity == "error"})
        # open at both ends the slit is a slitting saw's, said by name: made, to sixty of its widths
        sawn = cnc(slot(1.2, 40.0))
        self.assertTrue(sawn.ok)
        self.assertIn("cnc.slitting_saw", _judged(sawn))
        self.assertNotIn("cnc.pocket_depth_to_width", _judged(sawn))  # one finding for the slit's depth
        self.assertIn("cnc.pocket_depth_limit", _judged(cnc(slot(0.5, 32.0))))
        # a micro tool's reach is one continuous limit, 25 diameters at 0.5 mm rising to 30 at 1 mm: no cliff
        self.assertEqual([rules_side.reach_limit(d) for d in (0.2, 0.5, 0.75, 1.0, 3.0)], [25.0, 25.0, 27.5, 30.0, 30.0])
        self.assertTrue(cnc(closed(0.8, 9.0)).ok)
        self.assertTrue(cnc(closed(0.99, 29.0)).ok)
        self.assertFalse(cnc(closed(0.5, 13.0)).ok)
        for depth, made in ((6.5, False), (4.5, True)):  # a 0.1 mm corner takes a 0.2 mm tool: 5 mm deep at most
            cut = bd.fillet(bd.Box(10, 10, depth + 1, align=(A.CENTER, A.CENTER, A.MIN)).edges().filter_by(bd.Axis.Z), 0.1)
            result = cnc(_part(bd.Box(40, 40, 20) - bd.Pos(0, 0, 10 - depth) * cut))
            self.assertEqual((result.ok, "cnc.corner_reach_limit" in _judged(result)), (made, not made), depth)
        # a micro drill reaches as a micro end mill does: 33 diameters at 0.06 mm is past it
        micro = cnc(_part(bd.Box(5, 5, 4) - bd.Pos(0, 0, 2) * bd.Cylinder(0.03, 4, align=(A.CENTER, A.CENTER, A.MAX))))
        self.assertIn("cnc.hole_depth_limit", {f.code for f in micro.findings if f.severity == "error"})

    def test_a_thick_pin_stands_tall_too(self) -> None:
        # 6 mm across and 40 tall: over the 5 mm a wall is listed under, and a tall feature all the same
        pin = cnc(_part(bd.Box(40, 40, 5) + bd.Pos(0, 0, 22.5) * bd.Cylinder(3, 40)))
        self.assertEqual(_judged(pin), {"cnc.tall_feature"})
        short = cnc(_part(bd.Box(40, 40, 5) + bd.Pos(0, 0, 12.5) * bd.Cylinder(3, 20)))
        self.assertEqual(_judged(short), set())


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
        # both grooves are within a tool's reach: 2 mm deep in an 8 mm bore, as deep as wide
        internal = next(g for g in self.report["grooves"]["items"] if g["internal"])
        self.assertEqual((internal["entry_diameter_mm"], internal["depth_to_entry"]), (8.0, 0.25))
        judged = {o["rule"]: o["status"] for o in self.report["rules"]["outcomes"]}
        self.assertEqual((judged["cnc.groove_depth_limit"], judged["cnc.groove_depth"]), ("passed", "passed"))
        # what turning does not judge is said, never read as a pass
        self.assertIn("cnc.turning_not_judged", _codes(self.result))

    def test_a_groove_no_bar_reaches_and_a_slender_part(self) -> None:
        # a 24 mm groove behind a 10 mm bore is 7 mm past the bore's wall: no tool that enters the bore reaches it
        deep = bd.Cylinder(20, 40) - bd.Pos(0, 0, 5) * bd.Cylinder(5, 30) - bd.Cylinder(12, 6)
        result = cnc(_part(deep), turning=True)
        self.assertFalse(result.ok)
        self.assertLessEqual({"cnc.groove_depth_limit", "cnc.no_line_of_sight"}, _judged(result))
        # a chamber no tool reaches is no better for being checked as a turned part
        block = bd.Box(40, 40, 40) - bd.Pos(0, 0, 10) * bd.Cylinder(5, 20) - bd.Pos(0, 0, -5) * bd.Cylinder(12, 10)
        self.assertIn("cnc.no_line_of_sight", _judged(cnc(_part(block), turning=True)))
        # 2 mm by 100 mm: made, on a steady rest or a sliding-head lathe -- a warning
        slender = cnc(_part(bd.Cylinder(1, 100)), turning=True)
        self.assertTrue(slender.ok)
        self.assertEqual(_judged(slender), {"cnc.turned_slenderness"})
        # judged a section: a 6 x 120 stem on a 60 mm flange is twenty diameters, the flange's width no help
        stem = bd.Cylinder(30, 10, align=(A.CENTER, A.CENTER, A.MAX)) + bd.Cylinder(3, 120, align=(A.CENTER, A.CENTER, A.MIN))
        stemmed = cnc(_part(stem), turning=True)
        (said,) = [f for f in stemmed.findings if f.code == "cnc.turned_slenderness"]
        self.assertEqual(said.value, 20.0)
        runs = sorted((d["diameter_mm"], d["run_mm"]) for d in stemmed.measurements["turned_diameters"]["items"])
        self.assertEqual(runs, [(6.0, 120.0), (60.0, 130.0)])
        # an internal groove's depth has a warning before its error: a quarter of the bore, then half of it
        def grooved(depth: float) -> Any:
            return _part(bd.Cylinder(30, 40) - bd.Pos(0, 0, 5) * bd.Cylinder(10, 30) - bd.Cylinder(10 + depth, 6))

        self.assertEqual(_judged(cnc(grooved(4.0), turning=True)), set())
        near = cnc(grooved(9.0), turning=True)
        self.assertTrue(near.ok)
        self.assertIn("cnc.groove_depth", _judged(near))

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


class DraftedCavitiesTest(unittest.TestCase):
    """One cavity model: a wall drafted back from the tool's axis is a wall, a cavity's width and its corners'
    radius are read at its floor, and an annular cavity is a pocket -- each judged as its straight twin is."""

    @staticmethod
    def _lofted(width: float, length: float, depth: float, radius: float, draft: float) -> Any:
        inset = depth * math.tan(math.radians(draft))
        return bd.loft([bd.Pos(0, 0, -depth) * bd.RectangleRounded(length - 2 * inset, width - 2 * inset, radius - inset),
                        bd.RectangleRounded(length, width, radius)])

    def test_drafted_and_annular_pockets_read_as_their_straight_twins_whatever_the_turn(self) -> None:
        plate = bd.Box(200, 60, 20, align=(A.CENTER, A.CENTER, A.MAX))
        straight = bd.Pos(-70, 0, -10) * bd.extrude(bd.RectangleRounded(40, 30, 4), 10)
        lofted = bd.Pos(-20, 0, 0) * self._lofted(30, 40, 10, 4, 5)
        tapered = bd.Pos(30, 0, 0) * bd.extrude(bd.RectangleRounded(40, 30, 4), -10, taper=3)
        # a drafted box whose corner edges are filleted after: cylinders leaning with the corner
        wedge = bd.loft([bd.Pos(0, 0, -10) * bd.Rectangle(18.9, 28.9), bd.Rectangle(20, 30)])
        leaning = bd.Pos(75, 0, 0) * bd.fillet([e for e in wedge.edges() if abs(e.center().Z + 5) < 1e-6], 4)
        part = plate - straight - lofted - tapered - leaning
        # an O-ring's face groove (3 wide, 2 deep) and a round pocket about a boss, cut in the far face
        part -= bd.Pos(-60, 0, -20) * (bd.Cylinder(13.5, 2, align=(A.CENTER, A.CENTER, A.MIN))
                                       - bd.Cylinder(10.5, 2, align=(A.CENTER, A.CENTER, A.MIN)))
        part -= bd.Pos(60, 0, -20) * (bd.Cylinder(15, 6, align=(A.CENTER, A.CENTER, A.MIN))
                                      - bd.Cylinder(5, 6, align=(A.CENTER, A.CENTER, A.MIN)))

        def read(shape: Any) -> tuple[Any, ...]:
            result = cnc(_part(shape), material="aluminum")
            report = result.measurements
            pockets = sorted((p["kind"], p["depth_mm"], round(p["width_mm"], 2), p["wall_count"])
                             for p in report["pockets"]["items"])
            corners = sorted(round(c["radius_mm"], 1) for c in report["internal_corners"]["items"])
            return (result.status, sorted(_judged(result)), report["holes"]["count"], pockets, corners,
                    [i["setup_count"] for i in report["setups"]["items"]])

        drawn = read(part)
        # every one measured, none a hole, nothing to send back: only the lofted one's corners, 3.1 mm at the
        # floor of a 10 mm cavity, are under the third of its depth recommended
        self.assertEqual(drawn[:3], ("ok", ["cnc.corner_radius_to_depth"], 0))
        # each the pocket its twin is: 10 deep and closed, 8 walls, its width at the floor (40 x 30 less the
        # draft's inset, the leaning one's 20 x 30), four corners at their radius there; the groove's width is
        # its radial gap (3), the ring's 10
        self.assertEqual(drawn[3], [("closed", 2.0, 3.0, 2), ("closed", 6.0, 10.0, 2), ("closed", 10.0, 18.9, 8),
                                    ("closed", 10.0, 28.25, 8), ("closed", 10.0, 28.95, 8), ("closed", 10.0, 30.0, 8)])
        self.assertEqual(drawn[4], [3.1] * 4 + [3.5] * 4 + [4.0] * 8 + [13.5, 15.0])
        self.assertEqual(drawn[5], [2])
        self.assertEqual(read(bd.Pos(13, -7, 5) * bd.Rot(17, 23, 41) * part), drawn)

    def test_a_drafted_cavity_too_deep_fails_as_its_straight_twin_does(self) -> None:
        # 6 x 30 and 60 deep with 0.3 mm corners: straight, and lofted with 0.2 degrees of draft
        block = bd.Box(100, 60, 65, align=(A.CENTER, A.CENTER, A.MAX))
        straight = bd.Pos(-25, 0, -60) * bd.extrude(bd.RectangleRounded(6, 30, 0.3), 60)
        part = block - straight - bd.Pos(25, 0, 0) * bd.Rot(0, 0, 90) * self._lofted(6, 30, 60, 0.3, 0.2)
        result = cnc(_part(part), material="aluminum")
        self.assertFalse(result.ok)
        failed = [f for f in result.findings if f.code == "cnc.corner_reach_limit"]
        self.assertEqual(len(failed), 8)  # four corners each: the drafted ones tighter still at the floor
        radii = sorted(c["radius_mm"] for c in result.measurements["internal_corners"]["items"])
        self.assertEqual(radii, [0.09] * 4 + [0.3] * 4)
        # a slit drafted 1.5 degrees a side, 3 mm at the top and 0.38 at its floor 50 down, is no 3 mm slot
        slit = bd.extrude(bd.Plane.XZ * bd.make_face(bd.Polyline(
            (-1.5, 0), (1.5, 0), (0.19, -50), (-0.19, -50), close=True)), 30, both=True)
        drafted = cnc(_part(bd.Box(40, 40, 60, align=(A.CENTER, A.CENTER, A.MAX)) - slit))
        (pocket,) = drafted.measurements["pockets"]["items"]
        self.assertEqual((pocket["kind"], pocket["depth_mm"], round(pocket["width_mm"], 2)), ("slot", 50.0, 0.38))
        self.assertIn("cnc.pocket_depth_limit", {f.code for f in drafted.findings if f.severity == "error"})

    def test_a_tapered_window_is_a_through_cavity(self) -> None:
        window = bd.Box(80, 60, 20) - bd.Pos(0, 0, 10) * self._lofted(30, 40, 20, 4, 3)
        (cavity,) = cnc(_part(window)).measurements["pockets"]["items"]
        self.assertEqual((cavity["kind"], cavity["depth_mm"], round(cavity["width_mm"], 1)), ("through", 20.0, 27.9))


class EngravingAndEntryTest(unittest.TestCase):
    def test_shallow_lettering_is_an_engraving_tool_s_said_once(self) -> None:
        # an L-shaped stroke 0.8 wide and 0.4 deep, five sharp corners: no end mill's corner to fail
        outline = bd.make_face(bd.Polyline((0, 0), (6, 0), (6, 0.8), (0.8, 0.8), (0.8, 8), (0, 8), close=True))
        stroke = bd.extrude(outline, -0.4)
        result = cnc(_part(bd.Box(30, 30, 5, align=(A.CENTER, A.CENTER, A.MAX)) - bd.Pos(-3, -4, 0) * stroke))
        self.assertTrue(result.ok)
        self.assertEqual(_judged(result), {"cnc.gap_width_small"})  # micro-machining still, one stroke one warning
        (said,) = [f for f in result.findings if f.code == "cnc.engraving"]
        self.assertEqual(said.severity, "info")
        self.assertIn("1 shallow, narrow cavity", said.message)
        self.assertIn("with 5 corner(s)", said.message)  # the elbow's sixth is the material's, no corner to cut
        self.assertEqual(result.measurements["internal_corners"]["count"], 0)
        # the same stroke 3 mm deep is a pocket, and its corners are sharp
        deep = bd.extrude(outline, -3)
        self.assertIn("cnc.internal_corner_sharp",
                      _judged(cnc(_part(bd.Box(30, 30, 5, align=(A.CENTER, A.CENTER, A.MAX)) - bd.Pos(-3, -4, 0) * deep))))

    def test_a_closed_t_slot_s_way_in_is_its_entry_hole(self) -> None:
        # the cutter drops in through a 16 mm hole at one end and travels the slot: its far end's edges are made
        block = bd.Box(80, 40, 20)
        slot = bd.extrude(bd.Pos(0, 0, 10) * bd.SlotOverall(56, 6), -8)
        slot += bd.Pos(0, 0, -1) * bd.extrude(bd.SlotOverall(64, 14), 4)
        with_entry = cnc(_part(block - slot - bd.Pos(-25, 0, 3) * bd.Cylinder(8, 14)))
        self.assertTrue(with_entry.ok)
        self.assertEqual(_judged(with_entry), {"cnc.special_cutter"})  # (with no way in at all: DiscCutterTest)


class OccurrencesTest(unittest.TestCase):
    def test_every_occurrence_counts_however_it_is_turned(self) -> None:
        from unittest import mock

        from cad.build123d import _dfm_cnc

        def kit(*turns: tuple[float, float, float]) -> Any:
            parts = []
            for index, turn in enumerate(turns):
                placed = bd.Pos(60 * index, 0, 0) * bd.Rot(*turn) * (bd.Box(40, 30, 12) - _pocket(10, 10, 4, 0.0, 6)
                                                                    - bd.Pos(12, 0, 0) * bd.Cylinder(2, 12))
                placed.label = f"p{index}"
                parts.append(placed)
            return bd.Compound(children=parts, label="kit")

        def read(shape: Any) -> tuple[Any, ...]:
            with mock.patch.object(_dfm_cnc, "_measure_part", side_effect=_dfm_cnc._measure_part) as measured:
                result = cnc(shape)
            line = result.summary.split(": ", 1)[1]
            return line, result.measurements["holes"]["count"], measured.call_count

        alike = read(kit((0, 0, 0), (0, 0, 0), (0, 0, 0)))
        turned = read(kit((0, 0, 0), (90, 0, 0), (17, 23, 41)))
        # three parts, three holes, three pockets, twelve sharp corners: measured once, turned alike or not
        self.assertEqual(alike, turned)
        self.assertEqual(alike[1:], (3, 1))
        self.assertIn("3 part(s)", alike[0])
        self.assertIn("3 holes, 3 pockets", alike[0])
        self.assertIn("cnc.internal_corner_sharp x12", alike[0])

    def test_a_recess_reads_as_one_feature_at_any_turn_and_every_ref_is_one_ref(self) -> None:
        # a chamber behind a neck, its floor reached in part by a line at an angle: one recess, one finding
        chamber = bd.fillet((bd.Pos(0, 0, -3) * bd.Cylinder(5, 6)).edges(), 1)
        necked = bd.Box(40, 40, 40) - bd.Pos(0, 0, 17.5) * bd.Cylinder(10, 5) - chamber
        necked -= bd.Pos(0, 0, 7.5) * bd.Cylinder(3, 15.01)
        said = []
        for turn in (bd.Rot(0, 0, 0), bd.Pos(13, -7, 5) * bd.Rot(17, 23, 41)):
            result = cnc(_part(turn * necked))
            said.append(sorted((f.code, f.location, f.severity) for f in result.findings if f.severity != "info"))
            for finding in result.findings:
                for ref in finding.refs:
                    self.assertRegex(ref, r"^part/(face|edge) \d+$")
        self.assertEqual(said[0], said[1])
        self.assertEqual([code for code, _, _ in said[0]], ["cnc.undercut"])


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
        # a quarter turn is still square to the world: no frame of its own is needed; a tilt of a twentieth of a
        # degree is a frame of its own as much as one of 37 (the world's frame aligns less of the part than its own)
        tilts = [(bd.Rot(*angles), True) for angles in ((0.05, 0, 0), (0.4, 0.4, 0), (0, 0.8, 0), (1.0, 0, 0))]
        for turn, own in ((bd.Rot(0, 0, 30), True), (bd.Rot(17, 23, 41), True), (bd.Rot(90, 0, 0), False), *tilts):
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
            # a publisher's number cites its page; text-to-cad's own figure says it is, and why
            if rule.source == "text-to-cad":
                self.assertIn("text-to-cad's own", rule.note, rule.id)
            else:
                self.assertTrue(rules_side.RULES.source(rule.source).url.startswith("https://"))
        # one tool floor: a hole, a gap and a corner's radius (half of it) fail under the same tool
        floors = {rule.family: rule.limit for rule in rules_side.RULES.rules
                  if rule.id in ("cnc.hole_diameter", "cnc.gap_width", "cnc.internal_corner_radius")
                  and rule.severity == "error" and not rule.scale_by and not rule.item_when.get("made_by")}
        self.assertEqual(floors, {"holes": 0.05, "gaps": 0.05, "internal_corners": 0.025})
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
        # a corner is at its edge, and a STEP numbers its edges anew: the corners are the same faces' in both
        def corners(result: object) -> list[list[str]]:
            return sorted(sorted(ref for ref in f.refs if "/face " in ref)
                          for f in result.findings if f.code == "cnc.internal_corner_sharp")

        self.assertEqual(len(corners(live)), 4)
        self.assertEqual(corners(live), corners(written))
        json.dumps(live.measurements, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
