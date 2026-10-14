"""Helix bore and thread mill: arcs about the exact hole centres, the right radii, pitch, hand and direction, depths
reached, the refusals; and one plan of the whole 2.5D family end to end, its G-code read back."""

from __future__ import annotations

import math
import unittest

import numpy as np

from cadgen._internal.cam.ir import ARC_CCW, ARC_CW
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.operations.thread_mill import nominal_major
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support import gcode_reader
from tests.python.support.cam_fixtures import quiet
from tests.python.support.cam_fixtures_milling2d import (
    BOSS, BRACKET, COUNTERBORE, boss_step, bracket_step, class_directory, counterbore_step, engrave_dxf, face_at, job,
    plan_error,
)


def plan(part, operations):
    parsed = parse_job(job(operations))
    stock = build_stock(parsed.stock, part)
    setups, ops, _ = plan_setups(parsed, parse_operations(parsed), part, stock)
    return setups[0], ops


def arcs_of(setup_plan, index=0):
    op = next(o for o in setup_plan.toolpath.ops if o.index == index)
    path = setup_plan.toolpath.slice(op.start, op.end)
    starts = path.positions()[:-1]
    kinds = path.moves["kind"]
    keep = (kinds == ARC_CW) | (kinds == ARC_CCW)
    return path.moves[keep], starts[keep]


class Holes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.bracket = bracket_step(cls.directory)
        cls.boss = boss_step(cls.directory)
        cls.bracket_part = read_part(cls.bracket)
        cls.boss_part = read_part(cls.boss)
        features = cam.features(cls.bracket)
        cls.bore = face_at(features, surface="cylinder", diameter_mm=16.0)
        cls.taps = [h["faces"][0] for h in features.holes if abs(h["diameter_mm"] - 5.0) < 1e-6]
        cls.stud = face_at(cam.features(cls.boss), surface="cylinder", diameter_mm=12.0)
        cls.features = features

    def test_a_helix_bore_circles_the_exact_centre_inside_out_down_through_the_hole(self):
        setup, ops = plan(self.bracket_part, [{"op": "helix_bore", "tool": "T1", "faces": [self.bore]}])
        moves, starts = arcs_of(setup)
        self.assertTrue(np.allclose(moves["i"], -25.0) and np.allclose(moves["j"], 0.0))
        radii = np.round(np.hypot(moves["x"] + 25.0, moves["y"]), 6)
        # Ø16 less the 6 mm tool: the last circle at 5; the first at 5 less the 2.4 mm stepover, inside the tool's
        # radius, so no core stands.
        self.assertEqual([2.6, 5.0], sorted(set(radii.tolist())))
        self.assertTrue(np.all(moves["kind"] == ARC_CCW))                  # climb round a hole's wall
        self.assertAlmostEqual(-13.0, float(moves["z"].min()), places=6)   # through: to the part's bottom
        helical = moves["z"] < starts[:, 2] - 1e-9
        self.assertGreater(int(helical.sum()), 20)
        sweep = np.abs(np.unwrap(np.arctan2(moves["y"][helical], moves["x"][helical] + 25.0)))
        self.assertTrue(np.all(np.abs(np.diff(sweep)) <= math.pi + 1e-6))  # no arc over half a turn
        self.assertEqual(2, ops[0].meta["passes"])
        setup, _ = plan(self.bracket_part, [{"op": "helix_bore", "tool": "T2", "direction": "conventional",
                                             "holes": [{"center": [0, 10], "diameter_mm": 9, "bottom_z": -4}]}])
        moves, _ = arcs_of(setup)
        self.assertTrue(np.all(moves["kind"] == ARC_CW))
        # Ø9 less the 4 mm tool: 2.5, and a first circle a 1.6 mm stepover in (held at half the tool's radius).
        self.assertEqual([1.0, 2.5], sorted(set(np.round(np.hypot(moves["x"], moves["y"] - 10.0), 6).tolist())))
        self.assertAlmostEqual(-4.0, float(moves["z"].min()), places=6)

    def test_the_helix_keeps_to_the_ramp_angle_at_the_tools_centre_and_a_steeper_pitch_is_refused(self):
        setup, ops = plan(self.bracket_part, [{"op": "helix_bore", "tool": "T1", "faces": [self.bore]}])
        moves, starts = arcs_of(setup)
        helical = moves["z"] < starts[:, 2] - 1e-9
        rho = np.hypot(moves["x"] + 25.0, moves["y"])[helical]
        drop = (starts[:, 2] - moves["z"])[helical]
        # Half turns: each drops at most pi x rho x tan(3 degrees), however wide the circle.
        self.assertTrue(np.all(drop <= math.pi * rho * math.tan(math.radians(3.0)) * (1 + 1e-6)))
        self.assertLessEqual(ops[0].meta["pitch_mm"], 0.2 * 6.0)
        # The centre runs a smaller circle than the edge: its feed is scaled by rho / (rho + r), at least a quarter.
        table = ops[0].feeds.feed_mm_min
        flat = ~helical
        for radius in (2.6, 5.0):
            on = flat & np.isclose(np.hypot(moves["x"] + 25.0, moves["y"]), radius)
            self.assertTrue(np.allclose(moves["feed"][on], round(table * max(0.25, radius / (radius + 3.0))), atol=1))
        # 5 mm per turn round the smallest (Ø5.2) circle is a 17 degree helix.
        _, ops = plan(self.bracket_part, [{"op": "helix_bore", "tool": "T1", "faces": [self.bore], "pitch_mm": 5}])
        kind, message = plan_error(ops)
        self.assertEqual("unreachable", kind)
        self.assertIn("steeper than the 3 degrees ramp_angle_deg", message)
        steepest = math.floor(2 * math.pi * 2.6 * math.tan(math.radians(3.0)) * 1e4) / 1e4
        self.assertIn(f"give pitch_mm {steepest:g} or less", message)
        _, ops = plan(self.bracket_part, [{"op": "helix_bore", "tool": "T1", "faces": [self.bore],
                                           "pitch_mm": steepest}])
        self.assertIsNone(plan_error(ops))

    def test_a_counterbores_wall_names_the_counterbore_and_the_holes_wall_the_hole_under_it(self):
        from cadgen import cam

        step = counterbore_step(self.directory)
        part = read_part(step)
        features = cam.features(step)
        wall = face_at(features, surface="cylinder", diameter_mm=COUNTERBORE["counterbore"])
        hole = face_at(features, surface="cylinder", diameter_mm=COUNTERBORE["hole"])
        # WCS zero is the stock top, 1 mm over the part's: the counterbore's shoulder at -7, the part's bottom -11.
        setup, ops = plan(part, [{"op": "helix_bore", "tool": "T1", "faces": [wall]}])
        self.assertIsNone(plan_error(ops))
        moves, _ = arcs_of(setup)
        self.assertAlmostEqual(-7.0, float(moves["z"].min()), places=6)
        self.assertAlmostEqual(11.0 / 2 - 3.0, float(np.hypot(moves["x"], moves["y"]).max()), places=6)
        setup, ops = plan(part, [{"op": "helix_bore", "tool": "T2", "faces": [hole]}])
        moves, _ = arcs_of(setup)
        self.assertAlmostEqual(-11.0, float(moves["z"].min()), places=6)
        self.assertAlmostEqual(6.6 / 2 - 2.0, float(np.hypot(moves["x"], moves["y"]).max()), places=6)
        # Both walls named: the counterbore and the hole, each once.
        _, ops = plan(part, [{"op": "helix_bore", "tool": "T2", "faces": [wall, hole]}])
        self.assertEqual(2, ops[0].meta["holes"])

    def test_a_bore_too_small_for_the_tool_is_refused(self):
        _, ops = plan(self.bracket_part, [{"op": "helix_bore", "tool": "T1", "faces": [self.taps[0]]}])
        kind, message = plan_error(ops)
        self.assertEqual("tool_too_large", kind)
        self.assertIn("is not smaller than the Ø5 hole", message)
        with self.assertRaises(CamJobError) as caught:
            plan(self.bracket_part, [{"op": "helix_bore", "tool": "T1"}])
        self.assertIn("needs the hole walls", str(caught.exception))

    def test_an_internal_thread_climbs_counter_clockwise_up_the_tap_holes_at_its_pitch(self):
        setup, ops = plan(self.bracket_part, [{"op": "thread_mill", "tool": "T4", "faces": self.taps}])
        moves, starts = arcs_of(setup)
        helix = np.abs(moves["z"] - starts[:, 2]) > 1e-9
        centres = {(round(float(i), 6), round(float(j), 6)) for i, j in zip(moves["i"][helix], moves["j"][helix])}
        self.assertEqual({(25.0, 15.0), (25.0, -15.0)}, centres)
        self.assertTrue(np.all(moves["kind"] == ARC_CCW))
        self.assertTrue(np.all(moves["z"][helix] > starts[helix, 2]))       # right hand, climb: upward
        # M6x1 from the Ø5 tap drill: the cutter's centre at 3 - 2.4 = 0.6 from the axis.
        radii = np.hypot(moves["x"][helix] - moves["i"][helix], moves["y"][helix] - moves["j"][helix])
        self.assertTrue(np.allclose(radii, 0.6, atol=1e-6))
        rise = moves["z"][helix] - starts[helix, 2]
        angles = []
        for (x0, y0), (x1, y1), cx, cy in zip(starts[helix, :2], np.column_stack([moves["x"], moves["y"]])[helix],
                                              moves["i"][helix], moves["j"][helix]):
            a = math.atan2(y1 - cy, x1 - cx) - math.atan2(y0 - cy, x0 - cx)
            angles.append(a % (2 * math.pi) or 2 * math.pi)
        self.assertTrue(np.allclose(rise / np.asarray(angles) * 2 * math.pi, 1.0, atol=1e-6))
        self.assertAlmostEqual(-13.0, float(starts[helix, 2].min()), places=6)  # through: the whole 12 mm
        self.assertAlmostEqual(-1.0, float(moves["z"][helix].max()), places=6)
        self.assertEqual(["M6x1 internal", "M6x1 internal"], ops[0].meta["threads"])
        # The holes it needs made first, for the check that an earlier operation made them: WCS, through.
        self.assertEqual(sorted([[25.0, 15.0, -1.0, -13.0, 5.0], [25.0, -15.0, -1.0, -13.0, 5.0]]),
                         sorted(ops[0].meta["needs_holes"]))
        _, ops = plan(self.bracket_part, [{"op": "thread_mill", "tool": "T4", "faces": self.taps, "depth_mm": 14}])
        kind, message = plan_error(ops)
        self.assertEqual("too_deep", kind)
        self.assertIn("is longer than", message)

    def test_an_external_thread_runs_clockwise_down_the_stud_to_its_minor_diameter(self):
        setup, ops = plan(self.boss_part, [{"op": "thread_mill", "tool": "T5", "faces": [self.stud]}])
        moves, starts = arcs_of(setup)
        helix = np.abs(moves["z"] - starts[:, 2]) > 1e-9
        self.assertTrue(np.all(moves["kind"][helix] == ARC_CW))
        self.assertTrue(np.all(moves["z"][helix] < starts[helix, 2]))
        radii = np.round(np.hypot(moves["x"][helix] - moves["i"][helix], moves["y"][helix] - moves["j"][helix]), 4)
        minor = BOSS["diameter"] - 1.22687 * 1.75
        # Two passes at 1.75 mm pitch, the last to the ISO minor diameter plus the cutter's radius.
        self.assertEqual(sorted({round((BOSS["diameter"] / 2 + 4 + minor / 2 + 4) / 2, 4), round(minor / 2 + 4, 4)}),
                         sorted(set(radii.tolist())))
        self.assertEqual(["M12x1.75 external"], ops[0].meta["threads"])
        setup, _ = plan(self.boss_part, [{"op": "thread_mill", "tool": "T5", "faces": [self.stud], "hand": "left",
                                          "passes": 1}])
        moves, starts = arcs_of(setup)
        helix = np.abs(moves["z"] - starts[:, 2]) > 1e-9
        self.assertTrue(np.all(moves["z"][helix] > starts[helix, 2]))       # left hand: clockwise rises

    def test_tap_sizes_and_refusals(self):
        self.assertEqual(6.0, nominal_major(5.0, 1.0))
        self.assertEqual(8.0, nominal_major(6.8, 1.25))
        self.assertEqual(10.0, nominal_major(8.5, 1.5))
        self.assertEqual(12.0, nominal_major(10.2, 1.75))
        _, ops = plan(self.bracket_part, [{"op": "thread_mill", "tool": "T5", "faces": self.taps}])
        self.assertEqual("tool_too_large", plan_error(ops)[0])
        self.assertIn("a thread mill must be smaller than the hole", plan_error(ops)[1])
        cases = {
            "cuts only its own pitch": [{"op": "thread_mill", "tool": "T4", "faces": self.taps, "form": "multi",
                                         "pitch_mm": 0.8}],
            "its thread is internal": [{"op": "thread_mill", "tool": "T4", "faces": self.taps, "thread": "external"}],
            "a thread_mill tool": [{"op": "thread_mill", "tool": "T1", "faces": self.taps}],
        }
        for expected, operations in cases.items():
            with self.subTest(expected=expected), self.assertRaises(CamJobError) as caught:
                plan(self.bracket_part, operations)
            self.assertIn(expected, str(caught.exception))


class PlanBracket(unittest.TestCase):
    """The whole family on one job through ``cam.plan``: ready, every row, the G-code reads back to the IR's depths."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = bracket_step(cls.directory)
        engrave_dxf(cls.directory)
        features = cam.features(cls.step)
        top = face_at(features, surface="plane", z_mm=12.0)
        slot = face_at(features, surface="plane", z_mm=8.0)
        bore = face_at(features, surface="cylinder", diameter_mm=16.0)
        taps = [h["faces"][0] for h in features.holes if abs(h["diameter_mm"] - 5.0) < 1e-6]
        cls.job = job([
            {"op": "face", "tool": "T1"},
            {"op": "slot", "tool": "T2", "faces": [slot], "stepdown_mm": 2},
            {"op": "helix_bore", "tool": "T1", "faces": [bore]},
            {"op": "thread_mill", "tool": "T4", "faces": taps},
            {"op": "chamfer", "tool": "T3", "faces": [top], "width_mm": 0.5},
            {"op": "engrave", "tool": "T6", "dxf": "mark.dxf"},
            {"op": "contour", "tool": "T1", "faces": [top], "loops": "outer", "stepdown_mm": 4,
             "tabs": {"count": 4}, "lead_in_mm": 2, "lead_out_mm": 2},
        ])
        with quiet():
            cls.result = cam.plan(cls.step, job=cls.job)

    def test_the_family_plans_ready_and_posts_arcs_at_the_right_depths(self):
        result = self.result
        self.assertTrue(result.ok, result.findings)
        errors = [f for f in result.findings if f["severity"] == "error"]
        self.assertEqual([], errors)
        self.assertEqual(["face", "slot", "helix_bore", "thread_mill", "chamfer", "engrave", "contour"],
                         [op["op"] for op in result.operations])
        self.assertTrue(result.glb.is_file())
        text = gcode_reader.posted_text(self.result, "top")
        program = gcode_reader.read(text, start=(0.0, 0.0, 6.0))
        cuts = [m for m in program.moves if m.kind != "rapid"]
        self.assertAlmostEqual(-13.0, min(m.end[2] for m in cuts), places=3)
        helical = [m for m in program.moves if m.kind in ("arc_cw", "arc_ccw") and abs(m.end[2] - m.start[2]) > 1e-6]
        self.assertGreater(len(helical), 50)
        centres = {(round(m.centre[0], 3), round(m.centre[1], 3)) for m in helical}
        self.assertTrue({(-25.0, 0.0), (25.0, 15.0), (25.0, -15.0)} <= centres)

    def test_the_tabs_hold_in_the_posted_file(self):
        text = gcode_reader.posted_text(self.result, "top")
        program = gcode_reader.read(text, start=(0.0, 0.0, 6.0))
        points, kinds = gcode_reader.sample(program, max_step=0.5)
        points = np.asarray(points)
        sx, sy, _ = BRACKET["size"]
        outside = (np.abs(points[:, 0]) > sx / 2 + 2.9) | (np.abs(points[:, 1]) > sy / 2 + 2.9)
        last = points[outside & (points[:, 2] < -9.0 - 1e-6)]
        # The outline's last level runs at the bottom except over its tabs, a third of the 13 mm cut tall (2 mm).
        self.assertAlmostEqual(-13.0, float(last[:, 2].min()), places=3)
        self.assertTrue(np.any(np.isclose(last[:, 2], -11.0, atol=1e-3)))


if __name__ == "__main__":
    unittest.main()
