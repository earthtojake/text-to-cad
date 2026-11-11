#!/usr/bin/env python3

"""Injection molding's wall measurements on exact geometry, on tiny parts built here: draft (a wall extruded
with a 2 degree taper has 2 degrees of draft, a cone its half-angle) and thickness (a plate cut 3 thick is 3
thick), with the ball the shared geometry (``cad._internal.molding_geometry``) measures it by. The check's
other families are ``test_dfm_molding_undercuts``, ``test_dfm_molding_features`` and
``test_dfm_molding_verdicts``; the planted-defect corpus is ``test_dfm_molding_corpus``."""

from __future__ import annotations

import math
import unittest
from typing import Any

import build123d as bd
import numpy as np

from cad._internal import molding_geometry as ops
from cad._internal.dfm import molding as type_side
from cad.build123d import _dfm_brep
from tests.python.support.dfm_molding import BOTTOM, _check, _face


def _ramp(run: float) -> Any:
    """A 20 mm wide plate 2 mm thick stepping to 3 over ``run`` (0: a sharp step)."""
    profile = bd.Polygon((-30, 0), (30, 0), (30, 3), (run / 2, 3), (-run / 2, 2), (-30, 2), align=None)
    return bd.extrude(bd.Plane.XZ * profile, amount=-20)


class DraftTest(unittest.TestCase):
    def test_planes_cones_and_cylinders_read_exactly(self) -> None:
        part = bd.extrude(bd.Rectangle(30, 20), 10, taper=2.0) + bd.Pos(0, 0, 10) * bd.Cone(6, 4, 5, align=BOTTOM)
        part -= bd.Cylinder(2, 40)
        result = _check(part)
        items = result.measurements["draft"]["items"]
        by_kind = {kind: sorted({item["draft_deg"] for item in items if item["surface"] == kind})
                   for kind in ("plane", "cone", "cylinder")}
        self.assertEqual(by_kind["plane"], [2.0])
        self.assertAlmostEqual(by_kind["cone"][0], math.degrees(math.atan(2 / 5)), places=3)
        self.assertEqual(by_kind["cylinder"], [0.0])
        self.assertTrue(all(item["exact"] for item in items))
        opens = {item["surface"]: item["opens"] for item in items}
        self.assertEqual((opens["plane"], opens["cone"], opens["cylinder"]), ("+pull", "+pull", "none"))
        draft = result.measurements["draft"]
        self.assertEqual(draft["min_wall_draft"]["draft_deg"], 0.0)
        self.assertAlmostEqual(draft["zero_draft_wall_area_mm2"], 2 * math.pi * 2 * 15, delta=0.5)

    def test_a_face_turning_through_the_pull_is_split_and_a_freeform_face_reads_its_samples(self) -> None:
        pin = bd.Rotation(0, 90, 0) * bd.Cylinder(5, 30)
        items = _check(pin).measurements["draft"]["items"]
        self.assertEqual([item["opens"] for item in items if item["surface"] == "cylinder"], ["split"])
        # A loft between squares writes its flat walls as splines: they are read as the planes they are.
        lofted = bd.loft([bd.Rectangle(20, 20), bd.Pos(0, 0, 10) * bd.Rectangle(20 - 2 * 10 * math.tan(math.radians(4)),
                                                                                 20 - 2 * 10 * math.tan(math.radians(4)))])
        walls = [item for item in _check(lofted).measurements["draft"]["items"] if item["surface"] == "plane"
                 and item["opens"] != "none"]
        self.assertEqual(len(walls), 4)
        for wall in walls:
            self.assertAlmostEqual(wall["draft_deg"], 4.0, places=6)
            self.assertTrue(wall["exact"])
        # A loft from an ellipse to a larger one is free-form: its draft is the least over its samples.
        flared = bd.loft([bd.Ellipse(20, 10), bd.Pos(0, 0, 10) * bd.Ellipse(21, 11)])
        free = [item for item in _check(flared).measurements["draft"]["items"] if item["surface"] == "bspline"]
        self.assertTrue(free)
        for wall in free:
            self.assertFalse(wall["exact"])
            self.assertGreater(wall["draft_deg"], 3.0)
            self.assertLess(wall["draft_deg"], 6.0)

    def test_a_round_tangent_to_a_wall_square_to_the_pull_has_its_zero_draft(self) -> None:
        # a block's bottom edges rounded: each round is tangent to a vertical side, so its least draft is 0 on
        # that edge -- read there, the same however the part and its pull are turned
        block = bd.Box(40, 30, 20)
        block = bd.fillet(block.edges().group_by(bd.Axis.Z)[0], 3)
        for turn in ((0, 0, 0), (23, -37, 61)):
            placed = bd.Rot(*turn) * block
            pull = (bd.Rot(*turn) * bd.Pos(0, 0, 1)).position
            items = _check(placed, pull=f"{pull.X:.12f},{pull.Y:.12f},{pull.Z:.12f}").measurements["draft"]["items"]
            with self.subTest(turn=turn):
                rounds = [item["draft_deg"] for item in items if item["surface"] in ("cylinder", "torus")]
                self.assertEqual(len(rounds), 4)
                self.assertTrue(all(abs(draft) < 1e-6 for draft in rounds), rounds)

    def test_splines_that_are_analytic_surfaces_read_as_them(self) -> None:
        from OCP.BRepBuilderAPI import BRepBuilderAPI_NurbsConvert

        def nurbs(shape: Any) -> list[Any]:
            return bd.Shape.cast(BRepBuilderAPI_NurbsConvert(shape.wrapped, True).Shape()).faces()

        for shape, kinds in ((bd.Box(10, 10, 10), {"plane"}), (bd.Cylinder(4, 10), {"cylinder", "plane"}),
                             (bd.Cone(5, 3, 10), {"cone", "plane"}), (bd.Sphere(5), {"sphere"}),
                             (bd.Torus(10, 2), {"torus"})):
            with self.subTest(shape=type(shape).__name__):
                surfaces = [_dfm_brep.surface(face) for face in nurbs(shape)]
                self.assertEqual({surface.kind for surface in surfaces}, kinds)
        (torus,) = [_dfm_brep.surface(face) for face in nurbs(bd.Torus(10, 2))]
        self.assertAlmostEqual(torus.radius, 10.0, places=6)
        self.assertAlmostEqual(torus.minor_radius, 2.0, places=6)
        (cone,) = [s for s in (_dfm_brep.surface(face) for face in nurbs(bd.Cone(5, 3, 10))) if s.kind == "cone"]
        self.assertAlmostEqual(abs(cone.half_angle_deg), math.degrees(math.atan(0.2)), places=6)
        # extrude(taper=) flaring outward writes B-spline walls: planes all the same.
        flared = bd.extrude(bd.Rectangle(40, 30), 20, taper=-1)
        self.assertEqual({_dfm_brep.surface(face).kind for face in flared.faces()}, {"plane"})
        # a free-form face stays one
        free = bd.loft([bd.Ellipse(20, 10), bd.Pos(0, 0, 10) * bd.Ellipse(21, 11)])
        self.assertIn("bspline", {_dfm_brep.surface(face).kind for face in free.faces()})

    def test_the_rule_reads_every_wall_at_its_ref(self) -> None:
        result = _check(bd.Box(20, 20, 10))
        failures = next(o for o in result.measurements["rules"]["outcomes"] if o["rule"] == "molding.draft_min")["failures"]
        self.assertEqual(len(failures), 4)
        for failure in failures:
            face = _face(result, bd.Box(20, 20, 10), failure["location"])
            self.assertAlmostEqual(abs(face.normal_at().Z), 0.0, places=9)
        # Protolabs' 0.5 deg is a recommendation ("VERTICAL FACES 0.5"; only its shut-off and texture rows are
        # minimums): a warning, so zero draft on a wall this shallow does not fail the check.
        self.assertEqual({f.severity for f in result.findings if "draft" in f.code and f.code.startswith("molding.")},
                         {"warning"})
        hint = next(f.hint for f in result.findings if f.code == "molding.draft_min")
        self.assertIn("+z back into the material above the parting line", hint)

    def test_too_little_draft_for_its_depth_fails_a_shell_wall_and_says_whose_floor_it_is(self) -> None:
        # An open box with square walls, 2 mm thick and 30 mm deep: it cannot be sent to a shop as drawn (a
        # shallow one is warned: the guides' recommendation). The floor is text-to-cad's own: no guide is cited.
        def box(depth: float) -> Any:
            return bd.Box(60, 40, depth, align=BOTTOM) - bd.Pos(0, 0, 2) * bd.Box(56, 36, depth, align=BOTTOM)

        def floors_of(result: Any) -> list[Any]:
            return [f for f in result.findings if f.code == "molding.draft_zero"]

        deep = _check(box(30), pull="z")
        self.assertFalse(deep.ok)
        floors = floors_of(deep)
        self.assertEqual(({f.severity for f in floors}, len(floors)), ({"error"}, 8))   # four outside, four inside
        self.assertTrue(all(f.source.startswith("text-to-cad, ") for f in floors))
        self.assertNotRegex(floors[0].message + floors[0].source, "Protolabs|Hubs|Xometry")
        # Depth is a mold half's: the core's walls run their 28 mm in one half; the outside's, which the parting
        # line may run anywhere up, 15 either side of it.
        self.assertEqual({item["half_depth_mm"] for item in deep.measurements["draft"]["items"]}, {15.0, 28.0})
        self.assertRegex(floors[0].message, r"(15|28) mm deep in its mold half")
        # the recommendation is left to the record where the floor says it: one finding a face
        self.assertFalse({f.location for f in floors} & {f.location for f in deep.findings if f.code == "molding.draft_min"})
        (rule,) = {rule.note for rule in type_side.RULES.rules if rule.id == "molding.draft_zero"}
        self.assertTrue(rule.startswith("text-to-cad's own floor"))
        # No step at --zero-tol, and no turn with a tilt under the same pull: a tenth of a degree about (1, 1, 0)
        # its walls lean 0.07 deg, as stuck as with none, and it fails as it did; half a degree, their 0.35 deg
        # clears the floor and is the recommendation's warning -- beside the wall that now leans against the
        # pull, an undercut -- never a clean pass.
        axis = bd.Axis((0, 0, 0), (1, 1, 0))
        tenth = _check(box(30).rotate(axis, 0.1), pull="z")
        self.assertAlmostEqual(tenth.measurements["draft"]["min_wall_draft"]["draft_deg"], 0.0707, places=3)
        self.assertGreaterEqual(len(floors_of(tenth)), 4)
        half = _check(box(30).rotate(axis, 0.5), pull="z")
        self.assertEqual(floors_of(half), [])
        self.assertTrue({"molding.draft_min", "molding.undercut"} <= {f.code for f in half.findings if f.severity == "warning"})
        # A standoff is no wall of a shell (under ten nominal walls across): 15 mm with no draft is the
        # recommendation's warning, a hair off the pull (its faces sampled, where straight they are exact) or a
        # degree off it (its faces then turn through the pull, and are judged all the same): one verdict.
        standoff = bd.Cylinder(4, 15, align=BOTTOM) - bd.Cylinder(1.6, 15, align=BOTTOM)
        for tilt in (0.02, 1.0):
            result = _check(standoff.rotate(bd.Axis.X, tilt), pull="z")
            self.assertTrue(result.ok, tilt)
            self.assertEqual([f.code for f in result.findings if "draft" in f.code and f.severity != "info"],
                             ["molding.draft_min"] * 2, tilt)
        # A tube 30 across with a 3 mm wall is ten walls across to the measurement's own error (its wall reads
        # 2.995): at the limit of broad, which is no broad wall -- an error rests on what is clearly one.
        tube = _check(bd.Cylinder(15, 30) - bd.Cylinder(12, 30))
        self.assertEqual((tube.ok, {item["broad"] for item in tube.measurements["draft"]["items"]}), (True, {False}))
        # a dome 15 mm deep is tangent to the pull along its rim: no draft there, on a line -- no depth without it
        dome = _check(bd.Sphere(15) - bd.Sphere(13) - bd.Pos(0, 0, -20) * bd.Box(60, 60, 40))
        self.assertLess(max(item["half_depth_mm"] for item in dome.measurements["draft"]["items"]), 1.0)
        self.assertTrue(dome.ok, dome.summary)


class ThicknessTest(unittest.TestCase):
    def test_a_plate_reads_its_thickness_everywhere_even_at_its_ends(self) -> None:
        thickness = _check(bd.extrude(bd.Rectangle(60, 40), 3, taper=3)).measurements["thickness"]
        self.assertAlmostEqual(thickness["nominal_mm"], 3.0, places=3)
        for item in thickness["items"]:
            self.assertAlmostEqual(item["thickness_mm"], 3.0, delta=0.15, msg=item["location"])

    def test_a_part_under_a_micron_is_measured_whole(self) -> None:
        # drawn in metres and read as millimetres: its lengths are under the micron a sampled length is good to,
        # and are kept as they are (rounded to it they were 0, and every ratio of them a division by it)
        tiny = _check(bd.Box(0.0005, 0.00025, 0.00001) + bd.Pos(0, 0, 0.00001) * bd.Box(0.00002, 0.0002, 0.00002))
        self.assertEqual(tiny.measurements["partial_sections"], [])
        self.assertEqual(tiny.findings[0].code, "units_suspect")

    def test_a_pad_is_a_thick_section_and_a_step_an_abrupt_transition(self) -> None:
        plate = bd.extrude(bd.Rectangle(80, 60), 2, taper=3)
        stepped = plate + bd.Pos(0, 0, 5) * bd.Box(20, 20, 6)
        thickness = _check(stepped).measurements["thickness"]
        self.assertAlmostEqual(thickness["nominal_mm"], 2.0, places=3)
        self.assertAlmostEqual(thickness["max_mm"], 8.0, delta=0.05)
        self.assertGreater(thickness["thick_section_count"], 0)
        # The step is reported where it is (by the pad's edge, on the plate's bottom under it), its two walls
        # bracketing the change.
        steps = _check(stepped).measurements["transitions"]["items"]
        worst = steps[0]
        self.assertLess(worst["transition_ratio"], 1.0)
        self.assertGreaterEqual(worst["max_mm"] - worst["min_mm"], 1.0)   # at least half the 2 mm wall
        self.assertAlmostEqual(worst["max_mm"], 8.0, delta=0.05)          # the pad's full section
        self.assertAlmostEqual(worst["change_mm"], worst["max_mm"] - worst["min_mm"], places=2)
        self.assertLess(abs(max(abs(worst["xyz"][0]), abs(worst["xyz"][1])) - 10.0), 3.0, worst["xyz"])
        for point in worst["at_xyz"]:
            self.assertLess(abs(max(abs(point[0]), abs(point[1])) - 10.0), 5.0, point)  # within its section
        # The same rise as a ramp ten times its height long: no abrupt transition.
        ramp = bd.extrude(bd.Plane.XZ * bd.Polygon((-40, 0), (40, 0), (40, 2), (35, 2), (5, 8), (-5, 8), (-35, 2),
                                                   (-40, 2), align=None), 30)
        steps = _check(ramp).measurements["transitions"]["items"]
        self.assertGreater(min([step["transition_ratio"] for step in steps] or [99]), 3.0)

    def test_a_step_reads_its_run_over_its_rise(self) -> None:
        # 2 to 3 mm: a sharp step reads 0, a 2 mm ramp 2 (under Hubs' 3: it fails), a 4 mm ramp 4 (it passes).
        for run, ratio, fails in ((0.0, 0.0, True), (2.0, 2.0, True), (4.0, 4.0, False)):
            with self.subTest(run=run):
                result = _check(_ramp(run))
                (step,) = result.measurements["transitions"]["items"]
                self.assertAlmostEqual(step["transition_ratio"], ratio, places=3)
                self.assertEqual((step["min_mm"], step["max_mm"], step["basis"]), (2.0, 3.0, "step"))
                self.assertEqual("molding.wall_transition" in {f.code for f in result.findings}, fails)

    def test_the_skill_s_drafted_tray_reads_its_walls(self) -> None:
        # extrude(taper=) walls lie a hair off the tangent plane of the floor's ball: their edges' roots once
        # cancelled and read the wall 4 mm.
        body = bd.extrude(bd.Rectangle(60, 40), 20, taper=1)
        tray = body - bd.Pos(0, 0, 20) * bd.extrude(bd.Rectangle(56, 36), -17, taper=1)
        result = _check(tray)
        # its thickest ball is 3.2676 where the drafted 2.3 mm wall meets the 3 mm floor at a corner (the exact
        # distance to the shell): a reading never over it, and near it, far under the thick-section limit
        self.assertTrue(3.1 < result.measurements["thickness"]["max_mm"] <= 3.268, result.measurements["thickness"]["max_mm"])
        self.assertFalse({"molding.wall_max", "molding.thick_section", "molding.wall_transition"}
                         & {f.code for f in result.findings})

    def test_a_uniform_cup_reads_no_transition_wherever_it_stands(self) -> None:
        # a 2 mm cup 40 x 30 x 80 drafted 1 deg, its inside corners 1.2 mm: its tall corner strips tessellate as
        # needles, whose ill-set plane once held a ball of 0.015 mm under a 2 mm wall -- 2 to 4 false
        # transitions, a count that moved with the cup
        with bd.BuildPart() as cup:
            with bd.BuildSketch():
                bd.RectangleRounded(40, 30, 3.2)
            bd.extrude(amount=80, taper=1.0)
            bd.offset(amount=-2.0, openings=cup.faces().sort_by(bd.Axis.Z)[0])
        for turn, move in ((bd.Rot(0, 0, 0), (0, 0, 0)), (bd.Rot(0, 0, 0), (1000, -700, 300)),
                           (bd.Rot(0, 0, 37), (5, 5, 5)), (bd.Rot(90, 0, 0), (0, 0, 0))):
            pull = (turn * bd.Pos(0, 0, 1)).position
            result = _check(bd.Pos(*move) * turn * cup.part, pull=f"{pull.X:.15g},{pull.Y:.15g},{pull.Z:.15g}")
            self.assertEqual(result.measurements["transitions"]["items"], [], (turn, move))
            self.assertNotIn("molding.wall_transition", {f.code for f in result.findings})
            self.assertAlmostEqual(result.measurements["thickness"]["nominal_mm"], 2.0, places=6)

    def test_a_thin_wall_between_samples_is_never_hidden(self) -> None:
        # a drafted 2 mm cup, a cut grazing one corner to a 0.6 mm wall: its two bounding faces are narrow, and
        # their balls read 0.9 and 1.2; the exact least distance between them is the wall (BRepExtrema)
        with bd.BuildPart() as cup:
            with bd.BuildSketch():
                bd.RectangleRounded(40, 30, 3.2)
            bd.extrude(amount=80, taper=1.0)
            bd.offset(amount=-2.0, openings=cup.faces().sort_by(bd.Axis.Z)[0])
        reach = 1.2 + 0.6 + 5.0
        cut = cup.part - bd.Pos(16.8 + reach / math.sqrt(2), 11.8 + reach / math.sqrt(2), 40) * bd.Cylinder(5, 100)
        for turn in (bd.Rot(0, 0, 0), bd.Rot(23, -37, 61)):
            pull = (turn * bd.Pos(0, 0, 1)).position
            result = _check(turn * cut, pull=f"{pull.X:.15g},{pull.Y:.15g},{pull.Z:.15g}")
            thickness = result.measurements["thickness"]
            self.assertAlmostEqual(thickness["min_mm"], 0.6, delta=0.01)
            thin = [i for i in thickness["items"] if i["thickness_mm"] < 1.5]
            self.assertEqual(len(thin), 2, thin)  # the two faces either side of the 0.6 wall, refined to it
            self.assertTrue(all(i["refined"] and abs(i["thickness_mm"] - 0.6) < 0.01 for i in thin), thin)
            self.assertIn("molding.wall_min", {f.code for f in result.findings})
            self.assertAlmostEqual(thickness["nominal_mm"], 2.0, places=3)
        # the uniform cup it was cut from: no face refined under its wall
        plain = _check(cup.part)
        self.assertGreater(plain.measurements["thickness"]["min_mm"], 1.95)
        self.assertNotIn("molding.wall_min", {f.code for f in plain.findings})

    def test_alike_features_read_alike_thick_in_every_placement(self) -> None:
        # four blind-hole floors in bosses on a 2 mm cup, each 4 mm of material under it: turned, their samples
        # read 2.6 to 3.1, some under the thick-section limit; refined over the face, all four reach it
        outer = bd.extrude(bd.RectangleRounded(80, 50, 4), 25, taper=1)
        cup = outer - bd.Pos(0, 0, 2) * bd.extrude(bd.RectangleRounded(76, 46, 2), 24, taper=-1)
        for sx in (-1, 1):
            for sy in (-1, 1):
                cup = cup + bd.Pos(sx * 33, sy * 18, 2) * bd.extrude(bd.Circle(2.3), 15, taper=0.5) \
                    - bd.Pos(sx * 33, sy * 18, 4) * bd.extrude(bd.Circle(1.1), 14, taper=0.5)
        turn = bd.Rot(23, -37, 61)
        pull = (turn * bd.Pos(0, 0, 1)).position
        result = _check(turn * cup, pull=f"{pull.X:.15g},{pull.Y:.15g},{pull.Z:.15g}")
        thickness = result.measurements["thickness"]
        limit = type_side.RULES and next(r.limit for r in type_side.RULES.rules if r.id == "molding.thick_section")
        floors = [i for i in thickness["items"] if i["xyz"] and abs(abs((turn.inverse() * bd.Pos(*i["xyz"])).position.Z) - 4.0) < 1e-3]
        self.assertEqual(len(floors), 4)
        self.assertTrue(all(i["ratio_to_nominal"] >= limit for i in floors), floors)

    def test_the_ball_against_its_closed_form(self) -> None:
        # One flat face of a 4 mm slab, from above: the ball is half the slab.
        vertices = np.array([[-50, -50, 0], [50, -50, 0], [50, 50, 0], [-50, 50, 0.0]])
        triangles = np.array([[0, 1, 2], [0, 2, 3]])
        values, bound = ops.ball_thickness(np.array([[0, 0, 4.0]]), np.array([[0, 0, 1.0]]), np.array([np.inf]),
                                           vertices, triangles)
        self.assertAlmostEqual(values[0], 4.0, places=9)
        self.assertGreaterEqual(bound[0], 0)
        # Beside a step 1 mm off: held by the step's corner, r = (1 + 4) / 4.
        corner = np.array([[1.0, -50, 0], [1.0, 50, 0], [1.0, 50, -5]])
        values, _ = ops.ball_thickness(np.array([[0, 0, 4.0]]), np.array([[0, 0, 1.0]]), np.array([np.inf]),
                                       corner, np.array([[0, 1, 2]]))
        self.assertAlmostEqual(values[0], 2 * (1 + 16) / 8, places=9)
        # The same edge tilted a hair off the tangent plane (a drafted wall's): its root, solved stably, holds.
        tilted = corner + np.array([[0, 0, 0], [0, 0, 1e-12], [0, 0, 0]])
        values, _ = ops.ball_thickness(np.array([[0, 0, 4.0]]), np.array([[0, 0, 1.0]]), np.array([np.inf]),
                                       tilted, np.array([[0, 1, 2]]))
        self.assertAlmostEqual(values[0], 2 * (1 + 16) / 8, places=9)


if __name__ == "__main__":
    unittest.main()
