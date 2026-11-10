#!/usr/bin/env python3

"""Injection molding's features on exact geometry, on tiny parts built here: ribs, bosses and inside corners
(a rib cut 1.2 wide is 1.2 thick), a part of one closed face that has none, and the outline the pull sees --
the projected area, the parting plane and the clamp estimated from them. The check's other families are
``test_dfm_molding_walls``, ``test_dfm_molding_undercuts`` and ``test_dfm_molding_verdicts``; the
planted-defect corpus is ``test_dfm_molding_corpus``."""

from __future__ import annotations

import math
import unittest
from typing import Any

import build123d as bd
import numpy as np

from cad._internal import molding_geometry as ops
from tests.python.support.dfm_molding import A, BOTTOM, _check, _tray


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
