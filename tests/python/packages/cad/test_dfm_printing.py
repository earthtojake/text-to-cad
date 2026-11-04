#!/usr/bin/env python3

"""3D printing's check of exact geometry (``cad.build123d._dfm_printing``), its numpy measures
(``cad._internal.meshops_printing``) and its rule sets (``cad._internal.dfm.printing``).

Every part is built here with build123d, so each figure is the construction's: a tunnel 8 mm wide is a
bridge of 8 mm because it was cut that way, a 30 deg underside is 30 deg because it was drawn so, a void
of 24 mm a side holds 13824 mm3. A regression shows as a disagreement with the model.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

import build123d as bd
import numpy as np

import cad
from cad._internal import manufacturing
from cad._internal import meshops_printing as mo
from cad._internal.dfm import printing as rules
from cad.build123d import _dfm_brep as brep

A = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


def check(shape, name: str, **options):
    shape.label = name
    result = cad.build123d.printing(shape, **options)
    json.dumps(result.measurements, allow_nan=False)
    return result


def items(result, family: str, **match) -> list[dict]:
    return [item for item in result.measurements[family]["items"]
            if all(item.get(key) == value for key, value in match.items())]


def near(result, family: str, xyz, within: float = 1.0, **match) -> dict:
    found = [item for item in items(result, family, **match)
             if np.linalg.norm(np.array(item["xyz"]) - np.array(xyz)) <= within]
    assert found, f"no {family} item near {xyz} in {result.measurements[family]['items'][:6]}"
    return found[0]


def codes(result) -> list[str]:
    return [finding.code for finding in result.findings]


def outcome(result, rule: str) -> list[dict]:
    return [o for o in result.measurements["rules"]["outcomes"] if o["rule"] == rule]


def wedge(angle: float, length: float = 30.0, width: float = 12.0):
    """A cantilever whose underside rises at ``angle`` from the plate."""
    h = length * math.tan(math.radians(angle))
    return bd.Rotation(90, 0, 0) * bd.extrude(bd.make_face(bd.Polyline((0, 0), (length, h), (0, h), (0, 0))), width)


def tunnel(width: float = 8.0):
    """A block on two legs: its ceiling a bridge ``width`` wide."""
    return bd.Box(30, 20, 12, align=A) - bd.Box(width, 40, 6, align=A)


def tee():
    """A 10 x 10 post 20 tall under a 30 x 10 slab: two 10 mm cantilevers, 6000 mm3 under them."""
    return bd.Box(10, 10, 20, align=A) + bd.Pos(0, 0, 20) * bd.Box(30, 10, 2, align=A)


class OverhangTest(unittest.TestCase):
    def test_a_plane_reads_its_exact_angle_and_needs_support_under_the_limit(self) -> None:
        result = check(wedge(30.0), "wedge")
        slope = items(result, "overhangs", kind="slope")[0]
        self.assertAlmostEqual(slope["angle_deg"], 30.0, places=6)
        self.assertAlmostEqual(slope["area_below_limit_mm2"], 12 * 30 / math.cos(math.radians(30)), places=3)
        self.assertIn("printing.overhang_angle", codes(result))
        self.assertTrue(result.ok, "support is a warning, not a failure")

    def test_powder_holds_every_overhang(self) -> None:
        result = check(wedge(30.0), "wedge", technology="sls")
        self.assertNotIn("printing.overhang_angle", codes(result))
        self.assertNotIn("overhangs", codes(result))
        self.assertEqual({o["status"] for o in outcome(result, "printing.overhang_angle")}
                         - {"not_evaluated", "not_applicable"}, set())

    def test_a_ceiling_carried_on_both_sides_is_a_bridge_of_its_span(self) -> None:
        result = check(tunnel(8.0), "tunnel")
        bridge = items(result, "bridges", kind="bridge")[0]
        self.assertAlmostEqual(bridge["length_mm"], 8.0, places=4)
        self.assertEqual(bridge["supporting_edges"], 2)
        self.assertEqual(items(result, "overhangs", location=bridge["location"])[0]["kind"], "bridge")
        self.assertIn("printing.bridge_length", codes(result), "Hubs's 5 mm FDM bridge")
        self.assertNotIn("printing.overhang_angle", codes(result), "a bridge is no overhang FDM supports")
        metal = check(tunnel(8.0), "tunnel", technology="pbf")
        self.assertIn("printing.overhang_angle", codes(metal), "metal supports every ceiling")

    def test_a_slab_past_its_post_is_a_cantilever_of_its_reach(self) -> None:
        result = check(tee(), "tee", technology="sla")
        cantilever = items(result, "bridges", kind="cantilever")[0]
        self.assertAlmostEqual(cantilever["length_mm"], 10.0, places=4)
        self.assertIn("printing.cantilever_length", codes(result), "Hubs SLA: under 1 mm unsupported")

    def test_support_fills_the_columns_under_what_needs_it(self) -> None:
        support = check(tee(), "tee").measurements["support_volume"]
        self.assertAlmostEqual(support["estimated_support_volume_mm3"], 2 * 10 * 10 * 20, delta=1.0)
        self.assertAlmostEqual(support["support_contact_mm2"], 200.0, delta=1.0)


class WallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cup = bd.Box(30, 30, 20, align=A) - bd.Pos(0, 0, 2) * bd.Box(28.8, 28.8, 20, align=A)
        fin = bd.Pos(40, 0, 0) * (bd.Box(20, 20, 2, align=A) + bd.Pos(0, 0, 2) * bd.Box(0.6, 15, 10, align=A))
        cls.result = check(cup + fin, "walls")

    def test_a_wall_joined_on_its_sides_is_supported_and_measured_exactly(self) -> None:
        wall = items(self.result, "wall_thickness", supported=True)[0]
        self.assertAlmostEqual(wall["thickness_mm"], 0.6, places=6)
        self.assertGreaterEqual(wall["joined_sides"], 2)
        self.assertIn("printing.wall_supported", codes(self.result))

    def test_a_free_fin_is_unsupported(self) -> None:
        fin = near(self.result, "wall_thickness", (40, 0, 7), 9.0, supported=False)
        self.assertAlmostEqual(fin["thickness_mm"], 0.6, places=6)
        self.assertEqual(fin["joined_sides"], 1)
        self.assertIn("printing.wall_unsupported", codes(self.result))
        self.assertFalse(self.result.ok)


class FeatureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        block = bd.Box(60, 20, 20, align=A)
        across = bd.Pos(-20, 0, 10) * bd.Rotation(90, 0, 0) * bd.Cylinder(5, 40)
        drop = bd.Pos(0, 0, 10) * bd.Rotation(90, 0, 0) * (
            bd.Cylinder(3, 40) + bd.Rotation(0, 0, 45) * bd.Box(4.2426, 4.2426, 40, align=(bd.Align.MIN, bd.Align.MIN,
                                                                                         bd.Align.CENTER)))
        small = bd.Pos(20, 5, 0) * bd.Cylinder(0.4, 50)
        blind = bd.Pos(20, -5, 20) * bd.Cylinder(1, 8, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
        pin = bd.Pos(25, 0, 20) * bd.Cylinder(0.75, 13.5, align=A)
        cls.part = block - across - drop - small - blind + pin
        cls.fdm = check(cls.part, "features")
        cls.pbf = check(cls.part, "features", technology="pbf")

    def test_holes_are_cylinders_round_an_axis(self) -> None:
        small = near(self.fdm, "holes", (20, 5, 10), 1.0)
        self.assertEqual((small["diameter_mm"], small["orientation"], small["through"]), (0.8, "vertical", True))
        blind = near(self.fdm, "holes", (20, -5, 16), 1.0)
        self.assertEqual((blind["depth_mm"], blind["through"]), (8.0, False))
        self.assertIn("printing.hole_diameter", codes(self.fdm))

    def test_a_horizontal_hole_needs_a_teardrop_top_above_metals_limit(self) -> None:
        across = near(self.pbf, "holes", (-20, 0, 10), 1.0)
        drop = near(self.pbf, "holes", (0, 0, 10), 1.0)
        self.assertEqual((across["orientation"], across["teardrop"], drop["teardrop"]), ("horizontal", False, True))
        self.assertAlmostEqual(drop["coverage_deg"], 270.0, places=3)
        failing = [f for f in self.pbf.findings if f.code == "printing.horizontal_hole_diameter"]
        self.assertEqual([f.location for f in failing], [across["location"]], "Protolabs: 8 mm, teardrop above")

    def test_a_horizontal_holes_arch_is_a_bridge_in_fdm(self) -> None:
        arch = near(self.fdm, "bridges", (-20, 0, 10), 1.0, arch=True)
        self.assertAlmostEqual(arch["length_mm"], 10.0 * math.sin(math.radians(45)), places=4)
        hole = near(self.fdm, "holes", (-20, 0, 10), 1.0)
        self.assertEqual(items(self.fdm, "overhangs", location=hole["location"])[0]["kind"], "hole")

    def test_a_pin_is_a_convex_cylinder_with_its_aspect(self) -> None:
        pin = near(self.pbf, "pins", (25, 0, 26.75), 1.0)
        self.assertEqual((pin["diameter_mm"], pin["height_mm"], pin["aspect_ratio"]), (1.5, 13.5, 9.0))
        self.assertIn("printing.pin_aspect", codes(self.pbf), "Hubs metal: 8:1")
        self.assertIn("printing.pin_diameter", codes(self.fdm), "Hubs FDM: pins under 5 mm are perimeters alone")


class DetailAndGapTest(unittest.TestCase):
    def test_embossed_and_engraved_steps_and_a_slot(self) -> None:
        base = bd.Box(60, 20, 4, align=A)
        raised = bd.Pos(-20, 0, 4) * bd.Box(3, 10, 0.5, align=A)
        groove = bd.Pos(0, 0, 4) * bd.Box(0.3, 10, 0.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
        slot = bd.Pos(20, 0, 4) * bd.Box(0.4, 30, 3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
        part = base + raised - groove - slot
        sla, sls = check(part, "details", technology="sla"), check(part, "details", technology="sls")
        emboss = items(sla, "details", kind="emboss")[0]
        self.assertEqual((emboss["height_mm"], emboss["width_mm"]), (0.5, 3.0))
        engrave = near(sla, "details", (0, 0, 3.5), 6.0, kind="engrave")
        self.assertEqual((engrave["height_mm"], engrave["width_mm"]), (0.5, 0.3))
        self.assertIn("printing.engrave_width", codes(sla), "Hubs SLA: 0.4 mm wide")
        self.assertIn("printing.emboss_height", codes(sls), "Hubs SLS: 1 mm high")
        widths = sorted(item["gap_mm"] for item in items(sla, "gaps"))
        self.assertEqual(widths[:2], [0.3, 0.4])
        self.assertEqual(codes(sla).count("printing.gap"), 2, "Protolabs SLA: 0.635 mm")


class AssemblyTest(unittest.TestCase):
    def test_the_least_distance_between_parts(self) -> None:
        a, b, c = bd.Box(10, 10, 10, align=A), bd.Pos(10.2, 0, 0) * bd.Box(10, 10, 10, align=A), \
            bd.Pos(0, 10, 0) * bd.Box(10, 10, 10, align=A)
        a.label, b.label, c.label = "a", "b", "c"
        result = check(bd.Compound(children=[a, b, c]), "pair", technology="mjf")
        found = {tuple(item["parts"]): item for item in result.measurements["clearances"]["items"]}
        self.assertAlmostEqual(found[("a", "b")]["distance_mm"], 0.2, places=6)
        self.assertEqual(found[("a", "c")]["kind"], "contact")
        self.assertGreaterEqual(codes(result).count("printing.clearance"), 2, "Hubs MJF: 0.9 mm printed assembled")


class TrappedTest(unittest.TestCase):
    sealed = bd.Box(30, 30, 30, align=A) - bd.Pos(0, 0, 3) * bd.Box(24, 24, 24, align=A)

    def test_an_inner_shell_is_a_sealed_void_measured_exactly(self) -> None:
        result = check(self.sealed, "sealed", technology="sls")
        void = items(result, "trapped_volumes")[0]
        self.assertEqual((void["exact"], void["sealed"], void["escape_holes"]), (True, True, 0))
        self.assertAlmostEqual(void["volume_mm3"], 24 ** 3, places=3)
        self.assertAlmostEqual(void["min_wall_mm"], 3.0, places=6)
        self.assertIn("printing.escape_holes", codes(result))
        self.assertFalse(result.ok, "powder sealed in is no part")
        fdm = check(self.sealed, "sealed")
        self.assertIn("internal_void", codes(fdm))
        self.assertNotIn("printing.escape_holes", codes(fdm))

    def test_a_hollow_drains_through_its_exact_holes(self) -> None:
        drained = self.sealed - bd.Pos(0, 0, -1) * bd.Cylinder(2, 5, align=A) - bd.Pos(0, 0, 26) * bd.Cylinder(1, 6, align=A)
        result = check(drained, "drained", technology="sla")
        hollow = items(result, "trapped_volumes")[0]
        self.assertEqual((hollow["sealed"], hollow["escape_holes"], hollow["escape_hole_diameters_mm"]),
                         (False, 2, [2.0, 4.0]))
        self.assertAlmostEqual(hollow["volume_mm3"], 24 ** 3, delta=0.15 * 24 ** 3)
        self.assertIn("printing.escape_hole_diameter", codes(result), "Hubs SLA: 3.5 mm")
        self.assertNotIn("printing.escape_holes", codes(result))


class PlateTest(unittest.TestCase):
    def test_the_build_volume_in_the_best_axis_orientation(self) -> None:
        bar = bd.Box(250, 20, 10, align=A)
        result = check(bar, "bar")
        fit = result.measurements["build_volume"]
        self.assertEqual((fit["fill_ratio"], fit["fits"], fit["volume_mm"]), (1.25, False, [200.0, 200.0, 200.0]))
        self.assertIn("printing.build_volume", codes(result))
        self.assertFalse(result.ok)
        self.assertTrue(check(bar, "bar", build_volume="100x100x300").measurements["build_volume"]["fits"])
        self.assertTrue(check(bar, "bar", rules="hubs").ok, "Hubs's industrial FDM, 900 x 600 x 900")

    def test_bed_contact_and_warping(self) -> None:
        result = check(bd.Box(150, 40, 3, align=A), "flat", material="abs")
        bed = result.measurements["bed"]
        self.assertAlmostEqual(bed["contact_area_mm2"], 6000.0, places=3)
        self.assertEqual(bed["contact_length_mm"], 150.0)
        self.assertIn("warping_risk", codes(result))
        self.assertNotIn("warping_risk", codes(check(bd.Box(150, 40, 3, align=A), "flat", material="pla")))

    def test_a_shallow_slope_stair_steps(self) -> None:
        ramp = bd.Rotation(90, 0, 0) * bd.extrude(bd.make_face(bd.Polyline(
            (0, 0), (40, 0), (40, 40 * math.tan(math.radians(10))), (0, 0))), 10)
        result = check(ramp, "ramp", layer_height=0.3)
        step = items(result, "stair_stepping")[0]
        self.assertAlmostEqual(step["angle_deg"], 10.0, places=6)
        self.assertAlmostEqual(step["cusp_mm"], 0.3 * math.cos(math.radians(10)), places=4)
        self.assertAlmostEqual(result.measurements["stair_stepping"]["area_mm2"], 400 / math.cos(math.radians(10)),
                               delta=0.5)

    def test_a_sound_closed_solid(self) -> None:
        solid = check(bd.Box(10, 10, 10), "box").measurements["solid"]
        self.assertEqual((solid["watertight"], solid["sound"], solid["body_count"]), (True, True, 1))
        self.assertAlmostEqual(solid["volume_mm3"], 1000.0, places=6)


class OrientationTest(unittest.TestCase):
    def test_candidates_rank_by_the_stated_weighting(self) -> None:
        result = cad.build123d.printing(wedge(30.0), candidates=True)
        ranked = result.measurements["orientations"]
        rows = ranked["candidates"]
        self.assertGreaterEqual(len(rows), 6)
        self.assertEqual(ranked["weights"], mo.WEIGHTS["support"])
        self.assertEqual(rows[0]["support_volume_mm3"], 0.0)
        current = next(row for row in rows if row["orientation"] == "current_plus_z")
        self.assertGreater(current["support_volume_mm3"], 0.0)
        self.assertEqual([row["rank"] for row in rows], list(range(1, len(rows) + 1)))
        self.assertIn("orientations ranked", result.summary)


class StepTest(unittest.TestCase):
    def test_a_step_is_measured_on_its_b_rep_at_refs_the_engine_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tunnel.step"
            part = tunnel(8.0)
            part.label = "tunnel"
            bd.export_step(part, str(path))
            result = cad.step.check(path, process="printing", technology="sla")
        self.assertEqual(result.measurements["source"]["measured_as"], "brep")
        bridge = items(result, "bridges", kind="bridge")[0]
        self.assertAlmostEqual(bridge["length_mm"], 8.0, places=4)
        self.assertRegex(bridge["location"], r"^tunnel/face \d+$")


class RuleSetTest(unittest.TestCase):
    def test_every_set_cites_every_rule_and_keys_its_limits_by_technology(self) -> None:
        self.assertEqual(set(rules.RULE_SETS), {"generic", "hubs", "protolabs", "xometry"})
        for rule_set in rules.RULE_SETS.values():
            cited = {source.id for source in rule_set.sources}
            for rule in rule_set.rules:
                self.assertIn(rule.source, cited)
                self.assertTrue(rule.id.startswith("printing."))
                self.assertEqual(rule.by, "technology")
                self.assertTrue(set(rule.limit) <= set(rules.TECHNOLOGIES), rule.id)
        self.assertTrue(rules.RULE_SETS["generic"].generic)

    def test_a_technology_a_source_does_not_cover_is_not_evaluated_never_passed(self) -> None:
        result = check(bd.Box(20, 20, 5) - bd.Cylinder(0.3, 10), "plate", technology="mjf")
        hole = outcome(result, "printing.hole_diameter")
        self.assertTrue(all(o["status"] in ("not_evaluated", "not_applicable") for o in hole) or not hole)
        self.assertNotIn("printing.hole_diameter", codes(result))

    def test_options_are_refused_by_name(self) -> None:
        for given, said in (({"technology": "sla", "nozzle": 0.4}, "--nozzle is FDM's"),
                            ({"build_volume": "200x200"}, "--build-volume is three lengths"),
                            ({"angle_limit": 91}, "--angle-limit is an angle"),
                            ({"layer_height": 0}, "--layer-height is a length")):
            with self.subTest(given=given), self.assertRaisesRegex(ValueError, said):
                manufacturing.options("step", "printing", given)
        self.assertEqual(rules.machine_volume({"technology": "pbf", "rules": "protolabs"})["volume_mm"],
                         [245.0, 245.0, 330.0])


class MeshopsTest(unittest.TestCase):
    def test_support_and_cavities_of_a_triangulation(self) -> None:
        V, F, _ = brep.triangles(tee(), 0.05)
        self.assertAlmostEqual(mo.support(V, F, 45.0, 0.5)["volume_mm3"], 4000.0, delta=1.0)
        hollow = TrappedTest.sealed - bd.Pos(0, 0, -1) * bd.Cylinder(2, 5, align=A) - \
            bd.Pos(8, 8, -1) * bd.Cylinder(2, 5, align=A)
        V, F, _ = brep.triangles(hollow, 0.02)
        pitch, ball = mo.field_pitch(V.max(axis=0) - V.min(axis=0))
        found, labels = mo.cavities(mo.voxels(V, F, pitch, pad=mo.ball_pad(ball, pitch)), ball)
        self.assertEqual(len(found), 1)
        self.assertEqual(len(found[0].openings), 2)
        self.assertFalse(found[0].sealed)
        for opening in found[0].openings:
            self.assertAlmostEqual(opening["diameter_mm"], 4.0, delta=2 * pitch)

    def test_the_mesh_check_answers_the_same_families(self) -> None:
        drained = TrappedTest.sealed - bd.Pos(0, 0, -1) * bd.Cylinder(2.5, 5, align=A)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "drained.stl"
            bd.export_stl(tunnel(8.0) + bd.Pos(50, 0, 0) * drained, str(path), tolerance=0.01)
            result = cad.stl.check(path, process="printing", technology="sla")
        report = result.measurements
        bridge = near(result, "bridges", (0, 0, 6), 12.0, kind="bridge")
        self.assertAlmostEqual(bridge["length_mm"], 8.0, delta=0.05)
        hollow = items(result, "trapped_volumes")[0]
        self.assertEqual((hollow["sealed"], hollow["escape_holes"]), (False, 1))
        self.assertAlmostEqual(hollow["min_wall_mm"], 3.0, delta=0.05)
        self.assertNotIn("holes", report, "a mesh has no axis: holes are exact geometry's")
        self.assertEqual(outcome(result, "printing.hole_diameter")[0]["status"], "not_evaluated")
        json.dumps(report, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
