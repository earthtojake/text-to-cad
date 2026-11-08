#!/usr/bin/env python3

"""Injection molding's measurements on exact geometry, family by family, on tiny parts built here: each
expected figure is the construction's (a wall extruded with a 2 degree taper has 2 degrees of draft, a cone
its half-angle, a plate cut 3 thick is 3 thick). The planted-defect corpus is ``test_dfm_molding_corpus``;
this is the facts each verdict reads, the shared geometry (``cad._internal.meshops_molding``) and the type
side's rules and clamp estimate."""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from typing import Any

import build123d as bd
import numpy as np

import cad
from cad._internal import meshops_molding as ops
from cad._internal.dfm import molding as type_side
from cad._internal.dfm.rules import RuleSet
from cad.build123d import _dfm_brep

A = bd.Align
BOTTOM = (A.CENTER, A.CENTER, A.MIN)


def _check(shape: Any, **options: Any) -> Any:
    return cad.build123d.molding(shape, material=options.pop("material", "abs"), **options)


def _face(result: Any, shape: Any, location: str) -> Any:
    """The face a ref names, on the document the live shape reads as."""
    owner, _, ordinal = location.rpartition("face ")
    part = next(part for part in _dfm_brep.parts_of(shape).parts if part.owner == owner.rstrip("/"))
    return part.faces()[int(ordinal) - 1]


def _ramp(run: float) -> Any:
    """A 20 mm wide plate 2 mm thick stepping to 3 over ``run`` (0: a sharp step)."""
    profile = bd.Polygon((-30, 0), (30, 0), (30, 3), (run / 2, 3), (-run / 2, 2), (-30, 2), align=None)
    return bd.extrude(bd.Plane.XZ * profile, amount=-20)


def _tray(draft: float = 3.0, wall: float = 2.0) -> Any:
    outer = bd.extrude(bd.Rectangle(60, 40), 20, taper=-draft)
    inset = wall / math.cos(math.radians(draft)) - wall * math.tan(math.radians(draft))
    return outer - bd.Pos(0, 0, wall) * bd.extrude(bd.Rectangle(60 - 2 * inset, 40 - 2 * inset), 20, taper=-draft)


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
        self.assertFalse(result.ok)


class UndercutTest(unittest.TestCase):
    def test_a_side_hole_needs_one_slide_along_its_axis(self) -> None:
        part = _tray() - bd.Pos(30, 0, 10) * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 12)
        result = _check(part)
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["kind"], item["release"], item["side_actions"]), ("external", "side_action", ["+x"]))
        self.assertEqual(_dfm_brep.surface(_face(result, part, item["location"])).kind, "cylinder")
        self.assertGreater(item["stroke_mm"], 1.5)   # through the 2 mm wall
        self.assertAlmostEqual(item["height_mm"], 4.0, delta=0.3)
        self.assertIn("molding.undercut", {f.code for f in result.findings})

    def test_an_external_groove_needs_two_slides(self) -> None:
        part = bd.Cylinder(15, 20) - (bd.Cylinder(16, 4) - bd.Cylinder(12, 4))
        (item,) = _check(part).measurements["undercuts"]["items"]
        # A round groove: any two opposite slides in the parting plane release it, +-x or +-y alike.
        self.assertEqual(item["release"], "side_action")
        self.assertIn(sorted(item["side_actions"]), (["+x", "-x"], ["+y", "-y"]))
        self.assertLess(item["stroke_mm"], 10.0, "each half travels its own half, not the whole diameter")

    def test_inside_undercuts_take_a_lifter_or_a_collapsing_core(self) -> None:
        inner = 20.0 + 15.0 * math.tan(math.radians(3.0)) - 2.0 / math.cos(math.radians(3.0))
        snap = _tray() + bd.Pos(0, inner - 0.6, 15) * bd.Box(10, 2, 1.5)
        (item,) = _check(snap).measurements["undercuts"]["items"]
        self.assertEqual((item["kind"], item["release"]), ("internal", "lifter"))
        self.assertAlmostEqual(item["stroke_mm"], 1.5, delta=0.2, msg="the lip's reach into the cavity")
        groove = bd.Cylinder(15, 20) - bd.Cylinder(6, 20) - bd.Cylinder(8, 3)
        (item,) = _check(groove).measurements["undercuts"]["items"]
        self.assertEqual(item["release"], "collapsible_core")

    def test_a_sealed_void_is_released_by_nothing(self) -> None:
        result = _check(bd.Box(20, 20, 20) - bd.Sphere(5))
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["release"], item["kind"]), ("none", "internal"))
        self.assertIn(("error", "molding.undercut_unreleasable"), {(f.severity, f.code) for f in result.findings})

    def test_a_drafted_tray_pulls_clean(self) -> None:
        result = _check(_tray())
        undercuts = result.measurements["undercuts"]
        self.assertEqual((undercuts["candidate_area_mm2"], undercuts["undercut_count"]), (0.0, 0))
        self.assertTrue(result.ok, [f for f in result.findings if f.severity == "error"])


class ThicknessTest(unittest.TestCase):
    def test_a_plate_reads_its_thickness_everywhere_even_at_its_ends(self) -> None:
        thickness = _check(bd.extrude(bd.Rectangle(60, 40), 3, taper=3)).measurements["thickness"]
        self.assertAlmostEqual(thickness["nominal_mm"], 3.0, places=3)
        for item in thickness["items"]:
            self.assertAlmostEqual(item["thickness_mm"], 3.0, delta=0.15, msg=item["location"])

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
        self.assertLess(result.measurements["thickness"]["max_mm"], 3.2)
        self.assertFalse({"molding.wall_max", "molding.thick_section", "molding.wall_transition"}
                         & {f.code for f in result.findings})

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


class FeaturesTest(unittest.TestCase):
    def test_ribs_their_proportions_fillet_and_gap(self) -> None:
        plate = bd.extrude(bd.Rectangle(80, 60), 2, taper=3)
        part = plate + bd.Pos(-10, 0, 2 + 3) * bd.Box(1.2, 50, 6) + bd.Pos(10, 0, 2 + 3) * bd.Box(1.2, 50, 6)
        part = part.solids()[0]
        roots = [edge for edge in part.edges() if abs(edge.center().Z - 2) < 1e-6 and edge.geom_type == bd.GeomType.LINE
                 and abs(abs(edge.center().X) - 10) < 0.7 and abs(edge.center().X) > 9]
        part = part.fillet(0.4, roots)
        ribs = _check(part).measurements["ribs"]
        self.assertEqual(ribs["count"], 2)
        for rib in ribs["items"]:
            self.assertAlmostEqual(rib["thickness_mm"], 1.2, places=3)
            self.assertAlmostEqual(rib["height_mm"], 6.0, places=3)
            self.assertAlmostEqual(rib["length_mm"], 50.0, places=3)
            self.assertAlmostEqual(rib["thickness_ratio"], 0.6, places=3)
            self.assertAlmostEqual(rib["base_fillet_mm"], 0.4, places=4)
            self.assertAlmostEqual(rib["gap_mm"], 20 - 1.2, delta=0.02)

    def test_a_boss_its_core_and_its_wall_against_the_plate(self) -> None:
        plate = bd.extrude(bd.Rectangle(80, 60), 2, taper=3)
        part = plate + bd.Pos(0, 0, 2) * bd.Cylinder(4, 8, align=BOTTOM) - bd.Pos(0, 0, 2) * bd.Cylinder(1.5, 8, align=BOTTOM)
        (boss,) = _check(part).measurements["bosses"]["items"]
        self.assertEqual((boss["od_mm"], boss["id_mm"], boss["height_mm"]), (8.0, 3.0, 8.0))
        self.assertAlmostEqual(boss["wall_ratio"], 2.5 / 2.0, places=3)
        self.assertEqual(boss["hole_floor_above_base_mm"], 0.0)

    def test_a_rib_s_ends_are_its_roots_too(self) -> None:
        plate = bd.extrude(bd.Rectangle(80, 60), 2, taper=3)
        part = (plate + bd.Pos(0, 0, 2 + 3) * bd.Box(1.2, 30, 6)).solids()[0]
        roots = [edge for edge in part.edges() if abs(edge.center().Z - 2) < 1e-6 and abs(edge.center().X) < 1
                 and abs(edge.center().Y) < 15.5]
        rounded = part.fillet(0.3, roots)   # all round: sides and ends
        result = _check(rounded)
        (rib,) = result.measurements["ribs"]["items"]
        self.assertAlmostEqual(rib["base_fillet_mm"], 0.3, places=4)
        # the end fillets are the rib's root, judged by the rib's rule (0.25 of it), not by the corner rule
        self.assertEqual(result.measurements["corners"]["items"], [])
        # sides filleted, ends sharp: the rib's root fillet is its sharpest, 0
        sides = [edge for edge in roots if abs(edge.center().Y) < 14]
        (rib,) = _check(part.fillet(0.3, sides)).measurements["ribs"]["items"]
        self.assertEqual(rib["base_fillet_mm"], 0.0)

    def test_a_snap_arm_is_judged_as_one(self) -> None:
        # A 1.2 x 6 x 10 cantilever with a 1 mm barb: a snap (Hubs' 0.5 x wall), not a rib too tall.
        plate = bd.Box(60, 40, 2, align=BOTTOM)
        arm = plate + bd.Pos(0, 0, 2) * bd.Box(1.2, 6, 10, align=BOTTOM) + \
            bd.Pos(0.6, 0, 10) * bd.Box(1.0, 6, 1.5, align=(A.MIN, A.CENTER, A.MIN))
        result = _check(arm)
        (snap,) = result.measurements["ribs"]["items"]
        self.assertEqual(snap["kind"], "snap")
        self.assertTrue(snap["barb"])
        codes = {f.code for f in result.findings}
        self.assertIn("molding.undercut", codes)
        self.assertFalse({"molding.rib_height", "molding.rib_gap", "molding.snap_thickness"} & codes)
        outcomes = {o["rule"]: o for o in result.measurements["rules"]["outcomes"]}
        self.assertEqual(outcomes["molding.snap_thickness"]["status"], "passed")
        self.assertEqual(outcomes["molding.rib_height"].get("evaluated"), 0)

    def test_a_boss_root_is_judged_and_rib_faces_leave_the_wall_range(self) -> None:
        plate = bd.Box(60, 40, 2, align=BOTTOM)
        part = (plate + bd.Pos(0, 0, 2) * (bd.Cylinder(3, 8, align=BOTTOM) - bd.Cylinder(1.5, 8, align=BOTTOM))).solids()[0]
        root = [e for e in part.edges() if abs(e.center().Z - 2) < 1e-6 and e.geom_type == bd.GeomType.CIRCLE
                and abs(e.radius - 3) < 1e-6]
        for shape, fails in ((part, True), (part.fillet(0.5, root), False)):
            with self.subTest(filleted=not fails):
                self.assertEqual("molding.boss_root_fillet" in {f.code for f in _check(shape).findings}, fails)
        # 1 mm ribs on ABS (whose wall table starts at 1.14): the rib rules judge them, the wall's range not.
        ribbed = bd.extrude(bd.Rectangle(80, 60), 2, taper=3) + bd.Pos(0, 0, 4.5) * bd.Box(1.0, 50, 5)
        result = _check(ribbed)
        self.assertIn("rib", {item["feature"] for item in result.measurements["thickness"]["items"]})
        self.assertNotIn("molding.wall_min", {f.code for f in result.findings})

    def test_a_drafted_boss_is_a_boss(self) -> None:
        plate = bd.extrude(bd.Rectangle(80, 60), 2, taper=3)
        lean = 8 * math.tan(math.radians(1.0))
        part = (plate + bd.Pos(0, 0, 2) * bd.Cone(4, 4 - lean, 8, align=BOTTOM)
                - bd.Pos(0, 0, 2) * bd.Cone(1.5, 1.5 + lean, 8, align=BOTTOM))
        (boss,) = _check(part).measurements["bosses"]["items"]
        self.assertEqual((boss["od_mm"], boss["id_mm"], boss["height_mm"]), (8.0, 3.0, 8.0))
        self.assertAlmostEqual(boss["wall_ratio"], 2.5 / 2.0, places=3)

    def test_a_free_form_fillet_is_read_by_its_curvature(self) -> None:
        outer = bd.extrude(bd.Ellipse(30, 20), 20, taper=-2)
        cavity = bd.loft([bd.Pos(0, 0, 2) * bd.Ellipse(28, 18), bd.Pos(0, 0, 21) * bd.Ellipse(29, 19)])
        part = (outer - cavity).solids()[0]
        floor_edge = [edge for edge in part.edges() if abs(edge.center().Z - 2) < 1e-6]
        corners = _check(part.fillet(1.0, floor_edge)).measurements["corners"]["items"]
        (corner,) = corners
        self.assertEqual(corner["sharp"], False)
        self.assertAlmostEqual(corner["radius_mm"], 1.0, places=3)

    def test_internal_corners_sharp_and_rounded(self) -> None:
        profile = bd.Polygon((0, 0), (30, 0), (30, 2), (2, 2), (2, 30), (0, 30), align=None)
        sharp = bd.extrude(profile, 20)
        (corner,) = _check(sharp).measurements["corners"]["items"]
        self.assertEqual((corner["radius_mm"], corner["sharp"], corner["angle_deg"]), (0.0, True, 270.0))
        self.assertRegex(corner["edge"], r"^edge \d+$")
        self.assertAlmostEqual(corner["xyz"][0], 2.0, places=6)
        edge = [e for e in sharp.edges() if abs(e.center().X - 2) < 1e-6 and abs(e.center().Y - 2) < 1e-6]
        rounded = sharp.fillet(1.5, edge)
        (corner,) = _check(rounded).measurements["corners"]["items"]
        self.assertEqual((corner["radius_mm"], corner["sharp"], corner["ratio_to_wall"]), (1.5, False, 0.75))


class ProjectionPartingClampTest(unittest.TestCase):
    def test_the_projected_area_is_the_outline_once(self) -> None:
        part = bd.Box(30, 20, 5, align=BOTTOM) + bd.Pos(0, 0, 5) * bd.Cylinder(8, 10, align=BOTTOM)
        projection = _check(part).measurements["projection"]
        self.assertAlmostEqual(projection["projected_area_mm2"], 600.0, delta=projection["area_error_mm2"] + 0.5)
        disc = _check(bd.Cylinder(10, 3)).measurements["projection"]
        self.assertAlmostEqual(disc["projected_area_mm2"], math.pi * 100, delta=disc["area_error_mm2"] + 1.0)

    def test_parting_flat_at_the_rim_on_a_sphere_and_stepped(self) -> None:
        parting = _check(_tray()).measurements["parting"]
        self.assertTrue(parting["flat_parting_possible"])
        self.assertAlmostEqual(parting["parting_plane_height_mm"], 20.0, delta=0.05)
        self.assertAlmostEqual(parting["depth_from_parting_mm"], 20.0, delta=0.05)
        sphere = _check(bd.Sphere(10)).measurements["parting"]
        self.assertEqual((sphere["flat_parting_possible"], sphere["parting_plane_height_mm"]), (True, 0.0))
        steps = bd.extrude(bd.Rectangle(20, 20), 10, taper=3) + bd.Pos(20, 0, 5) * bd.extrude(bd.Rectangle(20, 20), 10,
                                                                                            taper=3)
        result = _check(steps)
        self.assertFalse(result.measurements["parting"]["flat_parting_possible"])
        self.assertIn("stepped_parting", {f.code for f in result.findings})

    def test_the_clamp_is_area_factor_cavities_and_margin(self) -> None:
        result = _check(bd.Box(50.8, 25.4, 10), material="pc", cavities=2)
        clamp = result.measurements["clamp"]
        self.assertEqual((clamp["factor_tons_per_in2"], clamp["cavities"]), (4.0, 2))
        area_in2 = result.measurements["projection"]["projected_area_mm2"] / 645.16
        self.assertAlmostEqual(clamp["tons"], area_in2 * 4.0 * 2 * 1.15, places=1)
        unknown = _check(bd.Box(50.8, 25.4, 10), material="peek")
        self.assertEqual(unknown.measurements["clamp"]["factor_range_tons_per_in2"], [2.0, 5.0])
        self.assertIn("resin_unknown", {f.code for f in unknown.findings})


class CandidatesAndPartsTest(unittest.TestCase):
    def test_a_blind_side_hole_ranks_its_own_axis_first(self) -> None:
        part = bd.Box(30, 20, 20) - bd.Pos(10, 0, 0) * bd.Rotation(0, 90, 0) * bd.Cylinder(3, 20)
        rows = {row["pull"]: row for row in _check(part, candidates=True).measurements["pulls"]["candidates"]}
        self.assertEqual((rows["x"]["undercut_count"], rows["x"]["undercut_candidate_area_mm2"]), (0, 0.0))
        self.assertEqual((rows["z"]["undercut_count"], rows["z"]["side_action_count"]), (1, 1))

    def test_pulls_tie_on_area_and_part_on_draft(self) -> None:
        rows = [{"pull": "x", "axis": [1, 0, 0], "undercut_candidate_area_mm2": 0.0, "zero_draft_wall_area_mm2": 0.4,
                 "wall_area_mm2": 5000.0, "min_wall_draft_deg": 1.66},
                {"pull": "z", "axis": [0, 0, 1], "undercut_candidate_area_mm2": 0.0, "zero_draft_wall_area_mm2": 11.4,
                 "wall_area_mm2": 5000.0, "min_wall_draft_deg": 7.46},
                {"pull": "y", "axis": [0, 1, 0], "undercut_candidate_area_mm2": 900.0, "zero_draft_wall_area_mm2": 0.0,
                 "wall_area_mm2": 5000.0, "min_wall_draft_deg": 9.0}]
        self.assertEqual([row["pull"] for row in type_side.ranked(rows)], ["z", "x", "y"])

    def test_a_cup_modelled_along_x_says_which_pull_ranks_first(self) -> None:
        cup = bd.Rot(0, 90, 0) * (bd.Cone(20, 18, 20, align=BOTTOM) - bd.Pos(0, 0, 3) * bd.Cone(18, 16, 17, align=BOTTOM))
        (trapped,) = [f for f in _check(cup, pull="z").findings if f.code == "undercut_candidates"]
        self.assertIn("--candidates ranks x first", trapped.hint)

    def test_several_solids_in_one_part_are_said(self) -> None:
        pair = bd.Box(10, 10, 10) + bd.Pos(30, 0, 0) * bd.Box(10, 10, 10)
        self.assertEqual(len(pair.solids()), 2)
        (said,) = [f for f in _check(pair).findings if f.code == "several_bodies"]
        self.assertIn("2 solids in one part", said.message)

    def test_an_assembly_is_measured_part_by_part_at_its_parts_refs(self) -> None:
        plain = bd.Box(20, 20, 10)
        plain.label = "plain"
        drafted = bd.Pos(40, 0, 0) * bd.extrude(bd.Rectangle(20, 20), 10, taper=3)
        drafted.label = "drafted"
        result = _check(bd.Compound(label="pair", children=[plain, drafted]))
        failed = next(o for o in result.measurements["rules"]["outcomes"] if o["rule"] == "molding.draft_min")
        self.assertEqual({failure["location"].split("/face")[0] for failure in failed["failures"]}, {"plain"})
        self.assertEqual(len(result.measurements["projection"]["items"]), 2)
        self.assertIn("several_bodies", {f.code for f in result.findings})

    def test_a_step_reads_as_its_live_shape(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tray.step"
            bd.export_step(_tray(), str(path))
            from_file = cad.step.dfm(path, process="molding", material="abs").measurements
        live = _check(_tray()).measurements
        for family in ("draft", "undercuts", "parting"):
            self.assertEqual(len(from_file[family]["items"]), len(live[family]["items"]), family)
        self.assertEqual(from_file["thickness"]["nominal_mm"], live["thickness"]["nominal_mm"])


class RulesTest(unittest.TestCase):
    def test_the_rules_cite_their_numbers_and_name_molding(self) -> None:
        self.assertIsInstance(type_side.RULES, RuleSet)
        for rule in type_side.RULES.rules:
            self.assertTrue(rule.id.startswith("molding."), rule.id)
            self.assertTrue(type_side.RULES.source(rule.source).url.startswith("https://"))
        # the wall table, in inches on its page, is millimetres here.
        self.assertAlmostEqual(type_side.WALL_RANGES["abs"][0], 1.143, places=3)
        self.assertAlmostEqual(type_side.WALL_RANGES["pc"][1], 3.81, places=3)

    def test_a_press_s_size_is_measured_never_judged(self) -> None:
        panel = _check(bd.extrude(bd.Rectangle(800, 500), 3, taper=3))
        judged = {o["family"] for o in panel.measurements["rules"]["outcomes"] if o["status"] in ("passed", "failed")}
        self.assertFalse({"projection", "envelope"} & judged)
        self.assertGreater(panel.measurements["projection"]["projected_area_mm2"], 390000)

    def test_the_rules_recommend_two_degrees_and_a_zero_draft_pull_points_at_candidates(self) -> None:
        (draft,) = [rule for rule in type_side.RULES.rules if rule.id == "molding.draft"]
        self.assertEqual(draft.limit, 2.0)
        self.assertIn("Most situations: 2", draft.note)
        for taper, warned in ((-1, True), (-2, False)):
            flared = bd.extrude(bd.Rectangle(40, 30), 20, taper=taper)
            self.assertEqual("molding.draft" in {f.code for f in _check(flared).findings}, warned)
        box = bd.Box(40, 30, 20)
        (zero,) = [f for f in _check(box).findings if f.code == "zero_draft_walls"]
        self.assertIn("--candidates", zero.hint)
        drafted_box = _check(bd.extrude(bd.Rectangle(40, 30), 20, taper=2) - bd.Pos(0, 0, 4) * bd.Box(4, 4, 8))
        (zero,) = [f for f in drafted_box.findings if f.code == "zero_draft_walls"]
        self.assertNotIn("--candidates", zero.hint)

    def test_a_metal_is_refused(self) -> None:
        from cad._internal import manufacturing
        from cad._internal.refused import ArgumentRefused
        with self.assertRaisesRegex(ArgumentRefused, "is a resin: steel is a metal"):
            manufacturing.options("step", "molding", {"material": "steel"})

    def test_a_thin_wall_for_the_resin(self) -> None:
        thin = bd.extrude(bd.Rectangle(40, 30), 0.8, taper=3)
        self.assertIn("molding.wall_min", {f.code for f in _check(thin, material="abs").findings})
        self.assertNotIn("molding.wall_min", {f.code for f in _check(thin, material="nylon").findings})



def _ellipsoid(a: float, b: float, c: float) -> Any:
    """A unit sphere stretched to semi-axes a, b, c: one closed freeform face."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform
    from OCP.gp import gp_GTrsf, gp_Mat

    stretch = gp_GTrsf()
    stretch.SetVectorialPart(gp_Mat(a, 0, 0, 0, b, 0, 0, 0, c))
    return bd.Solid(BRepBuilderAPI_GTransform(bd.Sphere(1).wrapped, stretch, True).Shape())


class OneFaceTest(unittest.TestCase):
    """A part of one closed face has no other face to hold a ball, bound a rib or meet a corner: each family
    reports what it found (nothing, where nothing is there), never an empty reduction."""

    def test_a_sphere_an_ellipsoid_and_a_torus_are_measured_whole(self) -> None:
        for name, shape, wall in (("sphere", bd.Sphere(5), 10.0), ("ellipsoid", _ellipsoid(6, 4, 3), 6.0),
                                  ("torus", bd.Torus(10, 3), 6.0)):
            with self.subTest(part=name):
                self.assertEqual(len(shape.faces()), 1)
                report = _check(shape).measurements
                self.assertEqual((report["partial"], report["partial_sections"]), (False, []))
                for family in ("ribs", "bosses", "corners"):
                    self.assertEqual(report[family]["count"], 0, family)
                # The widest ball is the least diameter (an ellipsoid's 2 x 3); no reading exceeds it.
                self.assertAlmostEqual(report["thickness"]["max_mm"], wall, delta=0.05 * wall)
                self.assertLessEqual(report["thickness"]["nominal_mm"], wall * 1.01)

    def test_the_shared_geometry_takes_empty_input(self) -> None:
        none = np.zeros((0, 3))
        values, bound = ops.ball_thickness(np.array([[0, 0, 1.0]]), np.array([[0, 0, 1.0]]), np.array([2.0]),
                                           np.array([[0, 0, 0.0], [1, 0, 0], [0, 1, 0]]), np.array([[0, 1, 2]]),
                                           others=none, point_face=np.array([1]), triangle_face=np.array([1]),
                                           others_face=np.zeros(0, dtype=int))
        self.assertEqual((float(values[0]), int(bound[0])), (2.0, -1), "its own face alone: the ray bounds it")
        release = ops.classify_undercut(none, none, np.array([0, 0, 1.0]), lambda o, d: np.full(len(o), np.inf),
                                        scale=10.0, zero_tol_deg=0.05)
        self.assertEqual(release["release"], "none")

if __name__ == "__main__":
    unittest.main()
