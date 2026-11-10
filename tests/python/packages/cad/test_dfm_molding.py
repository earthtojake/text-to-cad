#!/usr/bin/env python3

"""Injection molding's measurements on exact geometry, family by family, on tiny parts built here: each
expected figure is the construction's (a wall extruded with a 2 degree taper has 2 degrees of draft, a cone
its half-angle, a plate cut 3 thick is 3 thick). The planted-defect corpus is ``test_dfm_molding_corpus``;
this is the facts each verdict reads, the shared geometry (``cad._internal.molding_geometry``) and the type
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
from cad._internal import molding_geometry as ops
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


class UndercutTest(unittest.TestCase):
    def test_a_side_hole_needs_one_slide_along_its_axis(self) -> None:
        part = _tray() - bd.Pos(30, 0, 10) * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 12)
        result = _check(part)
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["kind"], item["release"], item["side_actions"]), ("external", "side_action", ["+x"]))
        self.assertEqual(_dfm_brep.surface(_face(result, part, item["location"])).kind, "cylinder")
        # the pin travels the whole wall (2 mm at 3 deg: 2.003 across, and the bore's own lean), not as far as the
        # deepest sampled point happens to lie
        self.assertGreaterEqual(item["stroke_mm"], 2.0)
        self.assertLess(item["stroke_mm"], 2.5)
        self.assertAlmostEqual(item["height_mm"], 4.0, delta=0.3)
        (said,) = [f for f in result.findings if f.code == "molding.undercut"]
        self.assertIn("released by a side action along +x", said.message)
        self.assertNotIn("deep against the pull", said.message)   # a bump-off's figure, no hole's

    def test_holes_through_both_walls_are_two_slides_and_three_slots_in_one_wall_are_one(self) -> None:
        # A ray along +x from the -x wall's hole leaves through the hole opposite: the slide is the one whose way
        # out is the shorter. And a part's side actions are its distinct slide directions, not its features.
        through = _check(_tray() - bd.Pos(0, 0, 10) * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 200)).measurements["undercuts"]
        self.assertEqual(sorted(tuple(item["side_actions"]) for item in through["items"]), [("+x",), ("-x",)])
        self.assertEqual((through["side_action_count"], sorted(through["side_action_directions"])), (2, ["+x", "-x"]))
        slotted = _tray()
        for x in (-15, 0, 15):
            slotted -= bd.Pos(x, 20, 10) * bd.Box(4, 8, 4)
        result = _check(slotted)
        slots = result.measurements["undercuts"]
        self.assertEqual([item["side_actions"] for item in slots["items"]], [["+y"]] * 3)
        self.assertEqual((slots["undercut_count"], slots["side_action_count"], slots["side_action_directions"]),
                         (3, 1, ["+y"]))
        (summed,) = [f for f in result.findings if f.code == "undercut_candidates"]
        self.assertIn("3 feature(s): 1 side action(s) (+y)", summed.message)

    def test_a_slot_takes_one_slide_along_its_own_run(self) -> None:
        # One slot off-centre in a long box: its own run (square to its faces' normals) is tried first, exactly,
        # so one slide along +y frees it, whatever the eight directions round the parting plane lean against.
        box = bd.extrude(bd.Rectangle(120, 80), 30, taper=-2) - \
            bd.Pos(0, 0, 2) * bd.extrude(bd.Rectangle(116, 76), 28, taper=-2)
        result = _check(box - bd.Pos(-50, 40, 18) * bd.Box(1.5, 10, 8))
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["release"], item["side_actions"], item["angled"]), ("side_action", ["+y"], False))
        self.assertGreaterEqual(item["stroke_mm"], 2.07)   # the wall, across
        self.assertLess(item["stroke_mm"], 2.5)

    def test_a_hole_off_the_grid_takes_a_slide_along_its_own_axis(self) -> None:
        # 20 deg off x in the parting plane: a plain slide along the bore. 25 deg out of the plane: an angled one.
        for turn, angled in ((bd.Rot(0, 0, 20), False), (bd.Rot(0, 25, 0), True)):
            part = _tray() - bd.Pos(30, 0, 10) * turn * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 14)
            result = _check(part)
            (item,) = result.measurements["undercuts"]["items"]
            self.assertEqual((item["release"], item["kind"], item["angled"]), ("side_action", "external", angled), turn)
            (way,) = item["side_actions"]
            axis = (turn * bd.Pos(1, 0, 0)).position
            self.assertAlmostEqual(float(np.array([float(v) for v in way.split(",")]) @ np.array([axis.X, axis.Y, axis.Z])),
                                   1.0, places=3)
            self.assertTrue(result.ok)

    def test_a_cavity_wider_below_its_mouth_is_an_inside_undercut_and_the_pull_check_agrees(self) -> None:
        # A box tapered the wrong way: its inside walls are trapped behind its mouth. No slide reaches them from
        # beside the part (the rays that leave it tilt out through the mouth: no side action's), and the report's
        # two readings of the pull are one.
        part = bd.extrude(bd.Rectangle(60, 40), 30, taper=2) - bd.Pos(0, 0, 2) * bd.extrude(bd.Rectangle(56, 36), 28, taper=2)
        result = _check(part)
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["kind"], item["release"], item["side_actions"]), ("internal", "collapsible_core", []))
        chosen = result.measurements["pull_check"]["chosen"]
        self.assertEqual((chosen["undercut_count"], chosen["side_action_count"], chosen["lifter_count"],
                          chosen["unreleasable_count"]), (1, 0, 1, 0))
        self.assertEqual(chosen["undercut_candidate_area_mm2"], result.measurements["undercuts"]["candidate_area_mm2"])

    def test_a_rib_s_end_a_hair_off_a_drafted_wall_is_a_crevice_not_an_undercut(self) -> None:
        # A square-ended rib run 0.1 mm into walls drafted 2 deg: buried at the floor, a hair off the wall above
        # it, the gap opening along the pull. A sample on the rib's end, stepped off it to cast its rays, landed in
        # the wall's material, read trapped both ways and freed by nothing: the part failed on two samples.
        box = bd.extrude(bd.Rectangle(60, 40), 30, taper=-2) - bd.Pos(0, 0, 2) * bd.extrude(bd.Rectangle(56, 36), 28, taper=-2)
        result = _check(box + bd.Pos(0, 0, 5) * bd.Box(1.2, 36.2, 6))
        undercuts = result.measurements["undercuts"]
        self.assertEqual((undercuts["undercut_count"], undercuts["candidate_area_mm2"]), (0, 0.0))
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(undercuts["crevice_count"], 2)   # the rib's two ends
        # no undercut, but steel between two faces a hair apart is a knife edge: a warning, at their refs
        (said,) = [f for f in result.findings if f.code == "crevices"]
        self.assertEqual(said.severity, "warning")
        self.assertEqual(len(undercuts["crevices"][0]["faces"]), 2)
        self.assertEqual(set(said.refs), {face for crevice in undercuts["crevices"] for face in crevice["faces"]})

    def test_a_feature_nothing_releases_is_read_again_on_denser_points_before_it_fails_the_part(self) -> None:
        from unittest import mock

        from cad.build123d import _dfm_molding

        void = bd.Box(20, 20, 20) - bd.Sphere(5)
        # every feature made to rest on "few" points: the void is sampled again, and still nothing releases it
        with mock.patch.object(_dfm_molding, "_CONFIRM_UNDER", 10 ** 6):
            read = _check(void).measurements["undercuts"]
            self.assertEqual((read["unreleasable_count"], read["unconfirmed_count"]), (1, 0))
            self.assertGreaterEqual(read["items"][0]["confirmed_points"], _dfm_molding._CONFIRM_POINTS)
            # ... and where the denser points are not trapped it was a sample's reading: no feature, no error
            empty = (np.zeros((0, 3)), np.zeros((0, 3)))
            with mock.patch.object(_dfm_molding, "_denser", return_value=empty):
                result = _check(void)
        read = result.measurements["undercuts"]
        self.assertEqual((read["undercut_count"], read["unconfirmed_count"], read["candidate_area_mm2"]), (0, 1, 0.0))
        self.assertNotIn("molding.undercut_unreleasable", {f.code for f in result.findings})
        # ... dropped, but never silently: counted, and said
        (said,) = [f for f in result.findings if f.code == "undercuts_unconfirmed"]
        self.assertEqual(said.severity, "info")
        self.assertIn("1 place(s)", said.message)

    def test_an_external_groove_needs_two_slides(self) -> None:
        part = bd.Cylinder(15, 20) - (bd.Cylinder(16, 4) - bd.Cylinder(12, 4))
        (item,) = _check(part).measurements["undercuts"]["items"]
        # A round groove: any two opposite slides in the parting plane release it, +-x or +-y alike.
        self.assertEqual(item["release"], "side_action")
        self.assertIn(sorted(item["side_actions"]), (["+x", "-x"], ["+y", "-y"]))
        self.assertLess(item["stroke_mm"], 10.0, "each half travels its own half, not the whole diameter")

    def test_a_groove_s_depth_is_said_and_a_shallow_re_entrant_lip_is_bumped_off(self) -> None:
        # a 3 mm round groove in a rim, its centre inset: 0.5 mm in, its opening is 0.042 mm narrower each side
        # than the groove (3 - sqrt(9 - 0.25)), a lip the slides scrape over (a bump-off, a warning); 1 mm in,
        # 0.17 mm -- over BUMP_OFF_MM, nothing frees it (an error). Each says how deep it is against the pull.
        disc = bd.Cylinder(35, 16, align=BOTTOM) - bd.Cylinder(5, 40)
        turned = bd.Rot(0, 90, 0) * bd.Pos(2, -1, 0)
        for turn, pull, inset in ((bd.Rot(0, 0, 0), "z", 1.0), (turned, "x", 0.5)):
            result = _check(turn * (disc - bd.Pos(0, 0, 8) * bd.Torus(35 - inset, 3)), pull=pull)
            (item,) = result.measurements["undercuts"]["items"]
            self.assertAlmostEqual(item["depth_mm"], 3.0 + inset, delta=0.15, msg=(pull, inset))
            codes = {(f.severity, f.code) for f in result.findings if f.code.startswith("molding.undercut")}
            finding = next(f for f in result.findings if f.code.startswith("molding.undercut"))
            self.assertIn("mm deep against the pull", finding.message)
            # every ref it names is a whole one (`cad step inspect` resolves it): its faces', never a bare word
            self.assertTrue(set(item["trapped_faces"]) <= set(finding.refs))
            self.assertEqual(set(finding.refs), {*item["faces"], *item["trapped_faces"], *item["blocked_by"]})
            if inset == 0.5:
                self.assertEqual(codes, {("warning", "molding.undercut_bump_off")}, pull)
                # external by its geometry: slides reach the groove from beside the part
                self.assertEqual((item["release"], item["kind"]), ("bump_off", "external"))
                self.assertLessEqual(item["interference_mm"], type_side.BUMP_OFF_MM)
                self.assertIn("resin's flexibility", finding.message)
            else:
                self.assertEqual(codes, {("error", "molding.undercut_unreleasable")}, pull)
                self.assertGreater(item["slide_depth_mm"], type_side.BUMP_OFF_MM)
                self.assertLess(item["slide_depth_mm"], 0.18)

    def test_inside_undercuts_take_a_lifter_or_a_collapsing_core(self) -> None:
        inner = 20.0 + 15.0 * math.tan(math.radians(3.0)) - 2.0 / math.cos(math.radians(3.0))
        snap = _tray() + bd.Pos(0, inner - 0.6, 15) * bd.Box(10, 2, 1.5)
        (item,) = _check(snap).measurements["undercuts"]["items"]
        self.assertEqual((item["kind"], item["release"]), ("internal", "lifter"))
        self.assertAlmostEqual(item["stroke_mm"], 1.5, delta=0.2, msg="the lip's reach into the cavity")
        groove = bd.Cylinder(15, 20) - bd.Cylinder(6, 20) - bd.Cylinder(8, 3)
        (item,) = _check(groove).measurements["undercuts"]["items"]
        self.assertEqual(item["release"], "collapsible_core")

    def test_an_undercut_whose_release_was_not_searched_is_counted_never_passed(self) -> None:
        from unittest import mock

        from cad.build123d import _dfm_molding

        part = _tray() - bd.Pos(30, 0, 10) * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 12)
        with mock.patch.object(_dfm_molding, "_RELEASE_SECONDS", 0.0):   # the release search's time, spent
            result = _check(part)
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["release"], item["unreleasable_area_mm2"]), ("unknown", None))
        outcome = next(o for o in result.measurements["rules"]["outcomes"] if o["rule"] == "molding.undercut_unreleasable")
        self.assertEqual((outcome["status"], outcome["unmeasured"]), ("not_evaluated", 1))
        self.assertIn(("warning", "undercuts_unsearched"), {(f.severity, f.code) for f in result.findings})
        # nothing trustworthy was judged of what is trapped: the check is not checked, never OK
        self.assertEqual((result.status, result.reason), ("not_checked", "rule_partly_judged"))
        # A window beside the hole, and rays that run out after the larger of the two: the search judged most
        # of what is trapped, so the verdict is of that. The hole is warned as the undercut it is and counted --
        # not passed, and not the whole check's undoing -- and the window keeps its slide, less the stroke the
        # budget ran out before.
        with mock.patch.object(_dfm_molding, "_RELEASE_RAYS", 1):
            result = _check(part - bd.Pos(0, 20, 10) * bd.Box(16, 12, 8))
        window, hole = result.measurements["undercuts"]["items"]
        self.assertEqual((window["release"], window["side_actions"], window["stroke_mm"], window["figures_measured"]),
                         ("side_action", ["+y"], None, False))
        self.assertEqual((hole["release"], hole["not_applicable"]), ("unknown", ["unreleasable_area_mm2"]))
        self.assertEqual(result.status, "ok")
        (said,) = [f for f in result.findings if f.code == "undercuts_unsearched"]
        self.assertIn("1 feature(s) not searched", said.message)
        self.assertEqual((said.severity, said.refs), ("warning", [hole["location"]]))
        self.assertIn("--pull", said.hint)
        self.assertEqual(sum(f.code == "molding.undercut" for f in result.findings), 2)   # each warned as an undercut
        outcome = next(o for o in result.measurements["rules"]["outcomes"] if o["rule"] == "molding.undercut_unreleasable")
        self.assertEqual((outcome["status"], outcome["unmeasured"]), ("passed", 0))

    def test_a_sealed_void_is_released_by_nothing(self) -> None:
        result = _check(bd.Box(20, 20, 20) - bd.Sphere(5))
        (item,) = result.measurements["undercuts"]["items"]
        self.assertEqual((item["release"], item["kind"]), ("none", "internal"))
        self.assertIn(("error", "molding.undercut_unreleasable"), {(f.severity, f.code) for f in result.findings})

    def test_a_ray_the_kernel_cannot_intersect_is_counted_not_fatal(self) -> None:
        """OCCT's exact intersector raised ``Standard_Failure`` on one face of a real part (a degenerate patch),
        which lost the whole undercuts family and then the summary (a ``KeyError``): the crossing is now not
        found, counted and said, and every family measured."""
        from unittest import mock

        from OCP.IntCurvesFace import IntCurvesFace_Intersector as Real
        from OCP.Standard import Standard_Failure

        made: list[Any] = []

        class Failing:
            def __init__(self, face: Any, tolerance: float) -> None:
                self.inner, self.fails = Real(face, tolerance), not made
                made.append(self)

            def Perform(self, *args: Any) -> None:  # noqa: N802 - the kernel's name
                if self.fails:
                    raise Standard_Failure("")
                self.inner.Perform(*args)

            def __getattr__(self, name: str) -> Any:
                return getattr(self.inner, name)

        part = _tray() - bd.Pos(30, 0, 10) * bd.Rotation(0, 90, 0) * bd.Cylinder(2, 12)
        with mock.patch("OCP.IntCurvesFace.IntCurvesFace_Intersector", Failing):
            result = _check(part)
        self.assertEqual(result.measurements["partial_sections"], [])
        (said,) = [f for f in result.findings if f.code == "rays_unintersected"]
        self.assertRegex(said.location, r"face \d+$")  # at the face, not at a family
        self.assertIn("undercut candidates", result.summary)

    def test_a_face_the_kernel_cannot_intersect_is_not_measured_in_every_family_its_rays_cross(self) -> None:
        """Thickness, ribs and corners cast rays too: a face the kernel fails on is named in each family whose
        rays it cost, and the family's rules say it was not measured there -- never a plain pass."""
        from unittest import mock

        from OCP.IntCurvesFace import IntCurvesFace_Intersector as Real
        from OCP.Standard import Standard_Failure

        part = _tray()
        part.label = "tray"
        floor = min(part.faces(), key=lambda face: face.center().Z)  # the tray's underside, under every wall ray

        class Failing:
            def __init__(self, face: Any, tolerance: float) -> None:
                self.inner, self.fails = Real(face, tolerance), face.IsPartner(floor.wrapped)

            def Perform(self, *args: Any) -> None:  # noqa: N802 - the kernel's name
                if self.fails:
                    raise Standard_Failure("")
                self.inner.Perform(*args)

            def __getattr__(self, name: str) -> Any:
                return getattr(self.inner, name)

        with mock.patch("OCP.IntCurvesFace.IntCurvesFace_Intersector", Failing):
            result = _check(part)
        ref = next(f.location for f in result.findings if f.code == "rays_unintersected")
        self.assertIn(ref, result.measurements["thickness"]["unmeasured_faces"])
        outcomes = {o["rule"]: o for o in result.measurements["rules"]["outcomes"]}
        self.assertIn(ref, outcomes["molding.wall_min"]["unmeasured_faces"])
        self.assertIn("not measured at 1 face(s)", outcomes["molding.wall_min"]["reason"])
        self.assertGreaterEqual(outcomes["molding.wall_min"]["unmeasured"], 1)

    def test_a_face_lost_only_while_the_pulls_are_ranked_is_said_once_for_the_part(self) -> None:
        """A bar drafted along x, molded along z, has a doubtful pull, so the part's own pulls are ranked
        (``pull_check``, which reads what x traps): a face the kernel fails on there alone is the part's one
        ``rays_unintersected``, naming it, and the pulls' too."""
        from unittest import mock

        from OCP.IntCurvesFace import IntCurvesFace_Intersector as Real
        from OCP.Standard import Standard_Failure

        from cad.build123d import _dfm_molding

        bar = bd.extrude(bd.Plane.YZ * bd.Rectangle(40, 20), amount=60, taper=5)
        bar.label = "bar"
        side = max(bar.faces(), key=lambda face: face.center().Y)
        ranking = {"now": False}

        class Failing:
            def __init__(self, face: Any, tolerance: float) -> None:
                self.inner, self.side = Real(face, tolerance), face.IsPartner(side.wrapped)

            def Perform(self, *args: Any) -> None:  # noqa: N802 - the kernel's name
                if self.side and ranking["now"]:
                    raise Standard_Failure("")
                self.inner.Perform(*args)

            def __getattr__(self, name: str) -> Any:
                return getattr(self.inner, name)

        check = _dfm_molding._pull_check

        def ranked(*args: Any, **kwargs: Any) -> Any:
            ranking["now"] = True
            try:
                return check(*args, **kwargs)
            finally:
                ranking["now"] = False

        with mock.patch("OCP.IntCurvesFace.IntCurvesFace_Intersector", Failing), \
                mock.patch.object(_dfm_molding, "_pull_check", ranked):
            result = _check(bar)
        said = [f for f in result.findings if f.code == "rays_unintersected"]
        self.assertEqual(len(said), 1, [f.message for f in said])
        self.assertIn(" face(s) of bar (", said[0].message)
        self.assertEqual(result.measurements["pull_check"]["unmeasured_faces"], [said[0].location])

    def test_a_family_not_measured_fails_the_check_and_never_raises(self) -> None:
        from unittest import mock

        from cad.build123d import _dfm_molding

        with mock.patch.object(_dfm_molding, "_undercut_part", side_effect=RuntimeError("no rays")):
            result = _check(_tray())
        self.assertFalse(result.ok)
        failed = [f for f in result.findings if f.code == "measurement_failed"]
        self.assertEqual([f.location for f in failed], ["undercuts"])
        self.assertIn("undercut candidates - mm2", result.summary)

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

    def test_ribs_that_cross_stand_on_the_wall_not_on_each_other(self) -> None:
        # Two ribs 4.8 mm apart, 6 tall, crossed by a third: the stretch between them is nearer the crossing rib's
        # sides than the floor, and read their 1.2 mm as the wall it stands on (a ratio of 1, a warning).
        part = bd.extrude(bd.Rectangle(80, 60), 2, taper=3)
        for x in (-3.0, 3.0):
            part += bd.Pos(x, 0, 2 + 3) * bd.Box(1.2, 40, 6)
        result = _check(part + bd.Pos(0, 0, 2 + 3) * bd.Box(40, 1.2, 6))
        ribs = result.measurements["ribs"]["items"]
        self.assertEqual(len(ribs), 7)
        self.assertEqual({(rib["wall_mm"], rib["thickness_ratio"], rib["height_mm"]) for rib in ribs}, {(2.0, 0.6, 6.0)})
        self.assertNotIn("molding.rib_thickness", {f.code for f in result.findings})

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

    def test_a_ratio_is_of_lengths_as_measured_so_a_radius_at_the_limit_is_at_it(self) -> None:
        # A sampled wall is good to a micron: one that reads 2.00001 (a filleted shell's did) under a 1 mm fillet
        # is a ratio of 0.5, at Hubs' limit -- not 0.499997 and a warning.
        from unittest import mock

        from cad.build123d import _dfm_molding

        profile = bd.Polygon((0, 0), (30, 0), (30, 2), (2, 2), (2, 30), (0, 30), align=None)
        sharp = bd.extrude(profile, 20)
        edge = [e for e in sharp.edges() if abs(e.center().X - 2) < 1e-6 and abs(e.center().Y - 2) < 1e-6]
        with mock.patch.object(_dfm_molding, "_face_wall", return_value=2.00001):
            result = _check(sharp.fillet(1.0, edge))
        (corner,) = result.measurements["corners"]["items"]
        self.assertEqual((corner["wall_mm"], corner["ratio_to_wall"]), (2.0, 0.5))
        self.assertNotIn("molding.inside_corner_radius", {f.code for f in result.findings})

    def test_a_corner_s_place_is_its_part_s_whatever_the_turn(self) -> None:
        # a square cup's sharp inside corners sit between walls of one area: each at the same face however the
        # cup is turned (the findings, one per face, then count alike)
        with bd.BuildPart() as cup:
            bd.Box(24, 24, 40, align=BOTTOM)
            bd.offset(amount=-2.0, openings=cup.faces().sort_by(bd.Axis.Z)[-1])
        read = []
        for turn in (bd.Rot(0, 0, 0), bd.Rot(23, -37, 61)):
            pull = (turn * bd.Pos(0, 0, 1)).position
            result = _check(turn * cup.part, pull=f"{pull.X:.15g},{pull.Y:.15g},{pull.Z:.15g}")
            read.append((sorted((c["edge"], c["location"]) for c in result.measurements["corners"]["items"]),
                         sorted(f.location for f in result.findings if f.code == "molding.inside_corner_radius")))
        self.assertEqual(read[0], read[1])


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
        (said,) = [f for f in result.findings if f.code == "stepped_parting"]
        self.assertTrue(said.refs)   # the pieces of the outline off the plane
        # A part split along its axis: a cone's two silhouette lines lie level with its axis, a lofted handle's
        # silhouette at its widest -- one flat plane takes each (their least-drafted samples read a band).
        barb = _check(bd.Rot(0, 90, 0) * bd.Cone(6, 4, 20)).measurements["parting"]
        self.assertEqual((barb["flat_parting_possible"], barb["parting_plane_height_mm"]), (True, 0.0))
        from cad.build123d import _dfm_molding

        handle = bd.loft([bd.Pos(x, 0, 0) * bd.Rot(0, 90, 0) * bd.Ellipse(a, b)
                          for x, a, b in ((0, 5, 8), (30, 7, 11), (60, 6, 9))])
        (skin,) = [face for face in handle.faces() if face.geom_type != bd.GeomType.PLANE]
        _dfm_molding._samples(skin, 100)   # the face meshed, as a check meshes it
        heights = _dfm_molding._silhouette(skin, np.array([0.0, 0.0, 1.0]))
        self.assertGreater(len(heights), 8)
        self.assertLess(max(abs(height) for height in heights), 1e-3)

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

    def test_a_cup_modelled_along_x_is_told_x_does_better(self) -> None:
        cup = bd.Rot(0, 90, 0) * (bd.Cone(20, 18, 20, align=BOTTOM) - bd.Pos(0, 0, 3) * bd.Cone(18, 16, 17, align=BOTTOM))
        result = _check(cup, pull="z")
        (said,) = [f for f in result.findings if f.code == "pull_better"]
        self.assertEqual(said.severity, "warning")
        self.assertIn("along x (1,0,0)", said.message)
        self.assertIn("--pull 1,0,0", said.hint)
        self.assertNotIn("the default", said.message)   # z was given
        self.assertEqual(result.measurements["pull_check"]["better"], "x")
        self.assertTrue(said.refs)   # the faces this pull falls by
        # The pulls offered are the part's own, not the world's: turned 37 deg about (1, 2, 3), the cup offers
        # the same directions turned with it, its axis first and toward its mouth -- where the world's x, y and z
        # are no directions of it.
        from cad.build123d import _dfm_molding

        def offered(shape: Any) -> list[tuple[str, np.ndarray]]:
            return _dfm_molding._own_pulls(_dfm_molding._Geometry(_dfm_brep.parts_of(shape).parts[0]))

        turn = bd.Axis((0, 0, 0), (1, 2, 3))
        straight, turned = offered(cup), offered(cup.rotate(turn, 37))
        self.assertEqual((straight[0][0], [round(float(value), 9) + 0.0 for value in straight[0][1]]), ("x", [1.0, 0.0, 0.0]))
        self.assertEqual(turned[0][0], "face0")
        self.assertEqual(len(straight), len(turned))
        for (_name, axis), (_other, moved) in zip(straight, turned):
            there = bd.Vector(*axis).rotate(turn, 37)
            self.assertGreater(float(moved @ np.array([there.X, there.Y, there.Z])), 0.99999)

    def test_a_part_tilted_off_the_default_pull_is_told_its_own_axis(self) -> None:
        # A clean tray turned 37 deg off the axes and checked with no --pull: along z a fifth of its surface is
        # trapped and no wall reads zero draft -- under both of the triggers that once asked whether the pull was
        # right. Every check asks now, and names the pull that does better: the tray's own axis.
        turn = bd.Rotation(20, 30, 0)
        result = _check(turn * _tray())
        (said,) = [f for f in result.findings if f.code == "pull_better"]
        self.assertIn("the default, z: none was given", said.message)
        self.assertIn("(the default pull)", result.summary)
        check = result.measurements["pull_check"]
        better = next(row for row in check["candidates"] if row["pull"] == check["better"])
        own = (turn * bd.Pos(0, 0, 1)).position
        self.assertAlmostEqual(abs(float(np.array(better["axis"]) @ np.array([own.X, own.Y, own.Z]))), 1.0, places=3)
        self.assertEqual((better["undercut_candidate_area_mm2"], better["zero_draft_wall_area_mm2"]), (0.0, 0.0))
        # along its own axis, given: nothing is trapped and no wall is without draft, so no other pull is read
        given = _check(turn * _tray(), pull=",".join(f"{value:.12g}" for value in (own.X, own.Y, own.Z)))
        self.assertNotIn("pull_better", {f.code for f in given.findings})
        self.assertEqual(given.measurements["pull_check"]["candidates"], [])
        self.assertNotIn("the default pull", given.summary)

    def test_a_pull_does_better_only_where_it_is_no_worse_anywhere(self) -> None:
        chosen = {"wall_area_mm2": 5000.0, "undercut_candidate_area_mm2": 400.0, "side_action_count": 1,
                  "zero_draft_wall_area_mm2": 0.0, "flat_parting": True}
        clean = {**chosen, "undercut_candidate_area_mm2": 0.0, "side_action_count": 0, "measured": "full"}
        self.assertTrue(type_side.dominates(clean, chosen))
        self.assertFalse(type_side.dominates(chosen, clean))
        # less trapped, but a wall without draft the measured pull has not: no better, and a tie is none
        self.assertFalse(type_side.dominates({**clean, "zero_draft_wall_area_mm2": 900.0}, chosen))
        self.assertFalse(type_side.dominates({**clean, "flat_parting": False}, chosen))
        self.assertFalse(type_side.dominates({**chosen, "undercut_candidate_area_mm2": 420.0}, chosen))
        # a feature nothing releases decides, whatever else: the pull that leaves none does better, though it
        # takes a lifter more (a tray lying 37 deg off the default pull, an off-centre boss in it)
        stuck = {**chosen, "unreleasable_count": 1}
        self.assertTrue(type_side.dominates({**chosen, "lifter_count": 1}, stuck))
        self.assertFalse(type_side.dominates(stuck, {**chosen, "lifter_count": 1}))
        # a pull only screened (its figures not all read) is never the one named
        self.assertIsNone(type_side.better_pull(chosen, [{**clean, "measured": "trapped"}]))
        self.assertEqual(type_side.better_pull(chosen, [clean | {"pull": "x"}])["pull"], "x")

    def test_two_solids_touching_are_said_to_be_fused_and_their_contact_is_no_undercut(self) -> None:
        pair = bd.Compound([bd.Box(10, 10, 10), bd.Pos(10, 0, 0) * bd.Box(10, 10, 10)])
        pair.label = "pair"
        result = _check(pair)
        # one thing said once: the part's several solids are every process's warning, which says of molding that
        # their contacts are left out; each pair is a fact of the report
        (said,) = [f for f in result.findings if f.code in ("several_solids", "solids_touching")]
        self.assertEqual(said.code, "several_solids")
        self.assertIn("where two touch without being fused", said.message)
        self.assertIn("fuse", said.hint)
        (touching,) = result.measurements["touching"]["items"]
        self.assertEqual(touching["solids"], [1, 2])
        self.assertAlmostEqual(touching["contact_area_mm2"], 100.0, delta=1.0)
        self.assertEqual(result.measurements["undercuts"]["candidate_area_mm2"], 0.0)
        self.assertNotIn("several_bodies", {f.code for f in result.findings})
        # the contact faces are no walls: six sides of the pair, not eight
        self.assertEqual(len(result.measurements["draft"]["items"]), 6)

    def test_several_solids_in_one_part_are_said(self) -> None:
        pair = bd.Box(10, 10, 10) + bd.Pos(30, 0, 0) * bd.Box(10, 10, 10)
        self.assertEqual(len(pair.solids()), 2)
        found = _check(pair).findings
        (said,) = [f for f in found if f.code == "several_solids"]   # every process's warning, once
        self.assertIn("2 solids in one part", said.message)
        self.assertIn("shadow each other", said.message)
        self.assertNotIn("several_bodies", {f.code for f in found})

    def test_an_assembly_is_measured_part_by_part_at_its_parts_refs(self) -> None:
        plain = bd.Box(20, 20, 10)
        plain.label = "plain"
        drafted = bd.Pos(40, 0, 0) * bd.extrude(bd.Rectangle(20, 20), 10, taper=3)
        drafted.label = "drafted"
        result = _check(bd.Compound(label="pair", children=[plain, drafted]))
        failed = next(o for o in result.measurements["rules"]["outcomes"] if o["rule"] == "molding.draft_min")
        self.assertEqual({failure["location"].split("/face")[0] for failure in failed["failures"]}, {"plain"})
        self.assertEqual(len(result.measurements["projection"]["items"]), 2)
        (said,) = [f for f in result.findings if f.code == "several_bodies"]
        self.assertEqual(sorted(said.refs), ["drafted", "plain"])   # its parts, as `cad step inspect` takes them
        self.assertNotIn("pull_check", result.measurements)   # each part opens its own way: no one pull to compare
        self.assertEqual([part["own"] for part in result.measurements["pulls"]], [False, False])

    def test_a_part_that_occurs_twice_is_judged_each_way_it_stands_and_counted_every_time(self) -> None:
        # A STEP holds a part's geometry once. Its occurrences turned alike are measured once and counted twice
        # in the totals; one turned on its side is a part of its own, judged along its own pull: an assembly's
        # parts lie as they are assembled, not as each is molded, and none fails it for that.
        def pair(turn: Any) -> Any:
            clip = bd.extrude(bd.Rectangle(20, 20), 3, taper=3)
            clip.label = "clip"
            other = bd.Pos(40, 0, 0) * turn * clip
            other.label = "clip"
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "pair.step"
                bd.export_step(bd.Compound(label="pair", children=[clip, other]), str(path))
                return cad.step.dfm(path, process="molding", material="abs")

        alike = pair(bd.Rot(0, 0, 0))
        (body,) = alike.measurements["bodies"]
        self.assertEqual(body["occurrences"], 2)
        (one,) = alike.measurements["projection"]["items"]
        self.assertEqual(one["occurrences"], 2)
        self.assertAlmostEqual(alike.measurements["projection"]["projected_area_mm2"], 2 * one["projected_area_mm2"],
                               delta=0.1)
        self.assertAlmostEqual(alike.measurements["projection"]["volume_mm3"], 2 * one["volume_mm3"], delta=0.1)
        self.assertAlmostEqual(alike.measurements["clamp"]["tons"], 2 * alike.measurements["clamp"]["items"][0]["tons"],
                               delta=0.011)
        self.assertEqual(alike.measurements["rules"]["failed"], [])
        turned = pair(bd.Rot(90, 0, 0))
        self.assertEqual([body["occurrences"] for body in turned.measurements["bodies"]], [1, 1])
        flat, side = turned.measurements["pulls"]
        self.assertEqual((flat["own"], side["own"]), (False, True))
        self.assertAlmostEqual(abs(side["axis"][1]), 1.0, places=6)   # its own axis, the world's y
        (said,) = [f for f in turned.findings if f.code == "part_pull"]
        self.assertEqual((said.severity, said.refs), ("warning", [side["part"]]))
        flat, side = turned.measurements["projection"]["items"]
        self.assertAlmostEqual(side["projected_area_mm2"], flat["projected_area_mm2"], delta=1.0)
        self.assertEqual((turned.ok, turned.measurements["rules"]["failed"]), (True, []))
        self.assertNotIn("occurrences_measured_once", {f.code for f in turned.findings + alike.findings})

    def test_a_step_reads_as_its_live_shape(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tray.step"
            bd.export_step(_tray(), str(path))
            from_file = cad.step.dfm(path, process="molding", material="abs").measurements
        live = _check(_tray()).measurements
        for family in ("draft", "undercuts", "parting"):
            self.assertEqual(len(from_file[family]["items"]), len(live[family]["items"]), family)
        self.assertEqual(from_file["thickness"]["nominal_mm"], live["thickness"]["nominal_mm"])


class OrientationTest(unittest.TestCase):
    def test_the_verdict_and_the_figures_do_not_turn_with_the_part_s_placement(self) -> None:
        # A box with square walls 18 mm deep inside (an error), a pad and a side window, off-centre. Turned about
        # the pull, moved, turned any way or tilted a third of a degree off the axes with its pull, it is the same
        # part: its verdict, its findings and its figures hold.
        part = bd.Box(60, 40, 20, align=BOTTOM) - bd.Pos(0, 0, 2) * bd.Box(56, 36, 20, align=BOTTOM) + \
            bd.Pos(-10, 5, 2) * bd.Box(12, 8, 3, align=BOTTOM) - bd.Pos(0, 20, 10) * bd.Box(10, 6, 4)

        def read(shape: Any, pull: str | None = None) -> tuple:
            result = _check(shape, pull=pull)
            m = result.measurements
            codes = sorted((f.severity, f.code) for f in result.findings if f.severity != "info")
            (window,) = m["undercuts"]["items"]
            return (result.ok, codes, m["thickness"]["nominal_mm"], m["thickness"]["max_mm"],
                    m["undercuts"]["candidate_area_mm2"], m["draft"]["wall_area_mm2"], window)

        ok, codes, nominal, thick, trapped, walls, window = read(part)
        self.assertFalse(ok)
        self.assertIn(("error", "molding.draft_zero"), codes)
        self.assertEqual((window["release"], window["side_actions"]), ("side_action", ["+y"]))
        placements = [(bd.Rot(0, 0, 30.0), None), (bd.Pos(250, -40, 1000), None),
                      (bd.Rot(0.3, 0, 0), "tilted"), (bd.Rot(23, -37, 61), "turned")]
        def turned(place: Any, x: float, y: float, z: float) -> np.ndarray:
            moved = (place * bd.Pos(x, y, z)).position - place.position
            return np.array([moved.X, moved.Y, moved.Z])

        def way_of(name: str) -> np.ndarray:
            if "," in name:
                found = np.array([float(value) for value in name.split(",")])   # as said, to three places
                return found / np.linalg.norm(found)
            return np.eye(3)["xyz".index(name[1])] * (1.0 if name[0] == "+" else -1.0)

        for place, pulled in placements:
            pull = ",".join(f"{value:.15g}" for value in turned(place, 0, 0, 1)) if pulled else None
            got = read(place * part, pull)
            self.assertEqual((ok, codes), got[:2], place)
            for want, have in zip((nominal, thick, walls), (got[2], got[3], got[5])):
                self.assertAlmostEqual(want, have, delta=1e-3 * max(1.0, abs(want)), msg=place)
            # the trapped area is sampled: a rectangle's mesh takes either diagonal, and its samples follow it
            self.assertAlmostEqual(trapped, got[4], delta=0.05 * trapped, msg=place)
            # the window's place and its slide, in the world the part stands in
            there = (place * bd.Pos(*window["xyz"])).position
            self.assertLess(float(np.linalg.norm(np.asarray(got[6]["xyz"]) - np.array([there.X, there.Y, there.Z]))),
                            0.5, place)
            (slide,) = got[6]["side_actions"]
            self.assertGreater(float(way_of(slide) @ turned(place, 0, 1, 0)), 0.9999, place)


class RulesTest(unittest.TestCase):
    def test_the_rules_cite_their_numbers_and_name_molding(self) -> None:
        self.assertIsInstance(type_side.RULES, RuleSet)
        for rule in type_side.RULES.rules:
            self.assertTrue(rule.id.startswith("molding."), rule.id)
            self.assertTrue(type_side.RULES.source(rule.source).url.startswith("https://"))
        # the wall table, in inches on its page, is millimetres here.
        self.assertAlmostEqual(type_side.WALL_RANGES["abs"][0], 1.143, places=3)
        self.assertAlmostEqual(type_side.WALL_RANGES["pc"][1], 3.81, places=3)

    def test_a_part_past_a_large_press_is_warned_and_one_past_any_press_built_fails(self) -> None:
        # The clamp force is an estimate of the part's projected area; the press that gives it is a shop's. Two
        # floors of text-to-cad's own stand on it all the same: a 12 m x 3 m panel takes 56 000 tons at a ton per
        # square inch, half the lowest factor published and five times what any press built gives -- it does not
        # read OK; a 2 m2 one is molded, on a press few shops run.
        def clamp(shape: Any) -> tuple[bool, dict[str, str], float]:
            result = _check(shape)
            press = {f.code: f.severity for f in result.findings if f.code.startswith("molding.clamp")}
            self.assertTrue(all(f.source.startswith("text-to-cad, ") for f in result.findings if f.code in press))
            return result.ok, press, result.measurements["clamp"]["tons"]

        ok, press, tons = clamp(bd.extrude(bd.Rectangle(12000, 3000), 30, taper=3))
        self.assertEqual((ok, press), (False, {"molding.clamp_beyond_press": "error"}))
        self.assertGreater(tons, 20 * type_side.CLAMP_LARGEST_TONS)
        # a 2 m2 panel is estimated past the largest press and takes a third of it at the least factor: warned
        ok, press, tons = clamp(bd.extrude(bd.Rectangle(2000, 1000), 4, taper=3))
        self.assertEqual((ok, press), (True, {"molding.clamp_large_press": "warning"}))
        self.assertGreater(tons, type_side.CLAMP_LARGEST_TONS)

    def test_the_rules_recommend_two_degrees_and_a_block_s_zero_draft_is_no_wrong_pull(self) -> None:
        (draft,) = [rule for rule in type_side.RULES.rules if rule.id == "molding.draft"]
        self.assertEqual(draft.limit, 2.0)
        self.assertIn("Most situations: 2", draft.note)
        for taper, warned in ((-1, True), (-2, False)):
            flared = bd.extrude(bd.Rectangle(40, 30), 20, taper=taper)
            self.assertEqual("molding.draft" in {f.code for f in _check(flared).findings}, warned)
        # a square block along its shortest side: every wall reads zero draft, and no other pull does better
        box = _check(bd.Box(40, 30, 20))
        (zero,) = [f for f in box.findings if f.code == "zero_draft_walls"]
        # a sum of what molding.draft_min and molding.draft_zero judge face by face: a fact
        self.assertEqual(zero.severity, "info")
        self.assertNotIn("pull_better", {f.code for f in box.findings})
        self.assertIsNone(box.measurements["pull_check"]["better"])
        # a cube's principal axes are any three: the kernel's pick (its diagonals) is no pull to offer
        cube = _check(bd.Box(40, 40, 40)).measurements["pull_check"]
        self.assertEqual(([row["pull"] for row in cube["candidates"]], cube["better"]), (["x", "y"], None))

    def test_a_limit_is_compared_unrounded(self) -> None:
        (thick,) = [rule for rule in type_side.RULES.rules if rule.id == "molding.thick_section"]
        self.assertEqual(thick.limit, 1 / 0.6)
        report = {"thickness": {"nominal_mm": 18.0, "items": [
            {"location": "p/face 1", "ratio_to_nominal": 30 / 18, "feature": "wall"},
            {"location": "p/face 2", "ratio_to_nominal": 30.001 / 18, "feature": "wall"}]}}
        from cad._internal.dfm import rules

        found, _record = rules.evaluate(report, type_side.RULES, type_side.context(report, {"material": "abs"}))
        self.assertEqual([f.location for f in found if f.code == "molding.thick_section"], ["p/face 2"])

    def test_one_cause_one_finding_and_hints_in_millimetres(self) -> None:
        # A rib's sides are judged by rib_draft alone, a window's walls (formed by its slide) by the undercut rule
        # alone; the sums of the faces and features are facts (info), the rules' findings what to act on.
        plate = bd.Box(60, 40, 2, align=BOTTOM) + bd.Pos(0, 0, 2) * bd.Box(40, 1.2, 8, align=BOTTOM)
        result = _check(plate)
        ribs = result.measurements["ribs"]["items"]
        sides = set(ribs[0]["faces"][:2])
        drafted = {f.location for f in result.findings if f.code in ("molding.draft_min", "molding.draft")}
        self.assertFalse(sides & drafted)
        self.assertIn("molding.rib_draft", {f.code for f in result.findings})
        cup = _tray() - bd.Pos(0, 20, 10) * bd.Box(10, 6, 4)
        cupped = _check(cup)
        window = {face for item in cupped.measurements["undercuts"]["items"] for face in item["trapped_faces"]}
        self.assertTrue(window)
        self.assertFalse(window & {f.location for f in cupped.findings if f.code.startswith("molding.draft")})
        corner = next(f for f in cupped.findings if f.code == "molding.inside_corner_radius")
        self.assertRegex(corner.hint, r"round this internal corner to [0-9.]+ mm or more")

    def test_a_metal_is_refused(self) -> None:
        from cad._internal import manufacturing
        from cad._internal.refused import ArgumentRefused
        with self.assertRaisesRegex(ArgumentRefused, "is a resin: steel is a metal"):
            manufacturing.options("step", "molding", {"material": "steel"})

    def test_a_thin_wall_for_the_resin(self) -> None:
        thin = bd.extrude(bd.Rectangle(40, 30), 0.8, taper=3)
        warned = _check(thin, material="abs")
        self.assertIn(("warning", "molding.wall_min"), {(f.severity, f.code) for f in warned.findings})
        self.assertTrue(warned.ok)   # under ABS's recommended 1.14 mm, over half of it: made, at a cost
        self.assertNotIn("molding.wall_min", {f.code for f in _check(thin, material="nylon").findings})

    def test_a_broad_wall_far_under_the_resin_s_range_fails_and_a_thick_one_is_warned(self) -> None:
        def plate(thickness: float) -> Any:
            return bd.extrude(bd.Rectangle(40, 30), thickness, taper=3)

        checked: dict[tuple, Any] = {}

        def codes(thickness: float, material: str | None, severity: str = "error") -> set[str]:
            if (thickness, material) not in checked:
                checked[thickness, material] = _check(plate(thickness), material=material)
            return {f.code for f in checked[thickness, material].findings
                    if f.severity == severity and f.code.startswith("molding.wall")}

        # 0.4 mm: under half of ABS's 1.14 mm minimum; within PPS's range down to 0.51 less than half short; and
        # under every resin's minimum, which is all that can be said with no resin named
        self.assertEqual(codes(0.4, "abs"), {"molding.wall_too_thin"})
        self.assertEqual(codes(0.4, "pps"), set())
        self.assertEqual(codes(0.4, None), {"molding.wall_too_thin"})
        # 8 mm: over twice ABS's 3.56 mm maximum -- it sinks, voids and cools slowly, and is molded all the same
        # (a cutting board): a warning, louder than the recommendation's; inside acrylic's range
        self.assertEqual(codes(8.0, "abs"), set())
        self.assertEqual(codes(8.0, "abs", "warning"), {"molding.wall_too_thick"})
        self.assertEqual(codes(8.0, "pmma", "warning"), set())
        self.assertEqual(codes(30.0, None, "warning"), {"molding.wall_too_thick"})   # over every resin's 25.4 mm
        thin = checked[0.4, "abs"]
        floor = next(f for f in thin.findings if f.code == "molding.wall_too_thin")
        self.assertTrue(floor.source.startswith("text-to-cad, "))   # ours: half of Protolabs' recommendation, said as that
        self.assertIn("0.5 of Protolabs' recommended minimum for abs", floor.message)
        # the recommendation is left to the record beside the floor: one finding a face
        self.assertFalse({f.location for f in thin.findings if f.code == "molding.wall_min"}
                         & {f.location for f in thin.findings if f.code == "molding.wall_too_thin"})

    def test_a_feature_s_width_is_no_wall_s_thickness(self) -> None:
        # What the floor judges is a broad wall: the face and the face across it each at least ten of the wall
        # wide. Two 2 mm plates joined by a web 0.4 mm thick and 1.5 mm long (a living hinge), a ridge down one
        # whose crest is 0.3 mm wide, and a 0.3 mm deep logo cut in the other: features a molder fills from the
        # wall beside them. Each reads thin where it is thin -- the recommendation's warning -- and none fails.
        plates = bd.Pos(-20.75, 0, 0) * bd.Box(40, 40, 2, align=BOTTOM) + bd.Pos(20.75, 0, 0) * bd.Box(40, 40, 2, align=BOTTOM)
        hinge = bd.Pos(0, 0, 1.6) * bd.Box(1.5, 40, 0.4, align=BOTTOM)
        ridge = bd.Pos(20, 0, 2) * bd.Rot(90, 0, 0) * bd.extrude(bd.Trapezoid(1.2, 1.5, 73.3, align=(A.CENTER, A.MIN)), 8, both=True)
        logo = bd.Pos(-20, 0, 1.7) * bd.Box(0.5, 10, 0.3, align=BOTTOM) + bd.Pos(-19.2, 0, 1.7) * bd.Box(0.5, 10, 0.3, align=BOTTOM)
        result = _check(plates + hinge + ridge - logo, material="pp")
        items = result.measurements["thickness"]["items"]
        floor = 0.5 * type_side.WALL_RANGES["pp"][0]
        thin = [item for item in items if item["thickness_mm"] < floor]
        self.assertGreaterEqual(len(thin), 3)   # the web, the crest and the strip between the logo's strokes
        self.assertFalse([item for item in items if item["broad"] and item["broad_wall_mm"] < floor])
        self.assertTrue(result.ok, result.summary)
        self.assertNotIn("molding.wall_too_thin", {f.code for f in result.findings})
        self.assertIn(("warning", "molding.wall_min"), {(f.severity, f.code) for f in result.findings})
        # the plates themselves are broad walls, read as their own 2 mm
        self.assertEqual({item["broad_wall_mm"] for item in items if item["broad"]}, {2.0})


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

    def test_a_median_on_the_half_is_the_lower_value_whatever_the_order(self) -> None:
        # a boss face of 16 equal samples, eight at 3.5: summed in any order the half falls on 3.5 -- a turned
        # part's samples came in another order and read 4.64, its corner bosses a wall_max of their own
        values = np.array([3.5] * 8 + [4.64, 4.65, 6.07, 4.64, 4.65, 6.07, 4.64, 4.65])
        weights = np.full(16, 14.46404682274)
        for seed in range(8):
            order = np.random.default_rng(seed).permutation(16)
            self.assertEqual(ops.weighted_median(values[order], weights[order] * (1 + 1e-15 * seed)), 3.5, seed)

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
