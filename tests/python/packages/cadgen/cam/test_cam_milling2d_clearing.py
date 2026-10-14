"""Adaptive clearing on the block's stepped pocket: floors reached, walls and the island kept, helix entries, and the
engagement capped: the material cut per millimetre of path stays near the stepover, far from a full-width slot."""

from __future__ import annotations

import math
import unittest

import numpy as np
import shapely
from shapely.ops import substring

from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, PLUNGE, RAPID
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures import BLOCK, block_step, class_directory, floor_ref, mill_job
from tests.python.support.cam_fixtures_milling2d import plan_error

#: T1 the core's 6 mm flat; T9 a 30 mm flat, too wide for the block's 24 x 20 lower pocket.
BIG = [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 30},
       {"id": "T9", "type": "flat", "diameter_mm": 30, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 40}]


class Adaptive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.step = block_step(class_directory(cls))
        cls.features = cam.features(cls.step)
        cls.part = read_part(cls.step)
        cls.lower = floor_ref(cls.features, BLOCK["lower"]["floor_z"])
        cls.upper = floor_ref(cls.features, BLOCK["upper"]["floor_z"])
        cls.result = cls.plan([{"op": "adaptive", "tool": "T1", "faces": [cls.lower]}])

    @classmethod
    def plan(cls, operations):
        parsed = parse_job(mill_job(operations))
        stock = build_stock(parsed.stock, cls.part)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), cls.part, stock)
        return setups[0], ops

    def test_it_reaches_both_floors_and_keeps_off_the_walls_and_the_island(self):
        plan, ops = self.result
        samples = plan.toolpath.sample(0.005, max_step_mm=0.25)
        cutting = samples.kind != RAPID
        cutting[0] = False
        points = samples.points[cutting]
        # WCS zero is the stock top, a millimetre over the part: the lower floor at -15, the upper at -9.
        self.assertAlmostEqual(-15.0, float(points[:, 2].min()), places=6)
        self.assertTrue(np.any(np.isclose(points[:, 2], -9.0) & (points[:, 0] > 18.0)), "the upper step is cleared")
        for z in np.unique(np.round(points[:, 2], 4)):
            group = points[np.isclose(points[:, 2], z, atol=1e-4)]
            material = plan.sections.at(float(z) + 1e-3)
            if material.is_empty:
                continue
            distance = shapely.distance(shapely.points(group[:, :2]), material)
            self.assertGreaterEqual(float(distance.min()), 3.0 - 0.02, f"at z {z}")
        meta = ops[0].meta
        self.assertEqual(meta["levels"], meta["entries"]["helix"])
        self.assertNotIn("plunges", meta)
        self.assertFalse(np.any(plan.toolpath.moves["kind"] == PLUNGE))
        self.assertEqual(0.9, meta["stepover_mm"])                     # 0.15 of the 6 mm tool
        self.assertEqual(6.0, meta["stepdown_mm"])                     # twice aluminium's half diameter
        self.assertEqual(8, len(meta["unreachable"]))
        self.assertEqual("lite", ops[0].operation.status)
        self.assertTrue(ops[0].operation.limits)

    def test_the_engagement_stays_near_the_stepover(self):
        plan, ops = self.result
        r, stepover = 3.0, ops[0].meta["stepover_mm"]
        moves = plan.toolpath.moves
        samples = plan.toolpath.sample(0.01, max_step_mm=0.5)
        # The deepest level, the lower step's own: cut from its helix outward.
        level = np.isclose(samples.points[:, 2], -15.0)
        arcs = level & np.isin(samples.kind, (ARC_CW, ARC_CCW))
        feeds = level & ~np.isin(samples.kind, (ARC_CW, ARC_CCW, RAPID))
        cleared = shapely.LineString(samples.points[arcs][:, :2]).buffer(r)
        rates = []
        points = samples.points
        index = np.nonzero(feeds)[0]
        # Walk the level's feed moves in runs of consecutive samples, in windows of about 2 mm of path each (a fixed
        # length, so a window's rate does not depend on how the moves happen to be sampled).
        runs = np.split(index, np.nonzero(np.diff(index) > 1)[0] + 1)
        for run in runs:
            if len(run) < 2:
                continue
            line = shapely.LineString(points[np.r_[run[0] - 1, run]][:, :2])
            count = max(1, int(line.length // 2.0))
            for k in range(count):
                path = substring(line, k * line.length / count, (k + 1) * line.length / count)
                if path.length < 0.5:
                    continue
                swept = path.buffer(r)
                rates.append(swept.difference(cleared).area / path.length)
                cleared = cleared.union(swept)
        rates = np.asarray(rates)
        self.assertGreater(len(rates), 20)
        # A full-width slot would cut 6 mm² per mm. A ring of radius p growing outward by the stepover s cuts
        # s (p + r) / p per mm of its centre line: about 2 s on the first ring round the helix, nearer s further out.
        self.assertLess(float(rates.max()), 2.2 * stepover)
        self.assertLess(float(np.median(rates)), 1.4 * stepover)
        self.assertGreater(len(moves), 100)

    def test_a_stepover_past_half_the_diameter_is_refused(self):
        with self.assertRaises(CamJobError) as caught:
            parse_operations(parse_job(mill_job([{"op": "adaptive", "tool": "T1", "faces": [self.lower],
                                                  "stepover": 0.6}])))
        self.assertIn("keep it at most half the tool's diameter (3 mm)", str(caught.exception))
        with self.assertRaises(CamJobError) as caught:
            parse_operations(parse_job(mill_job([{"op": "adaptive", "tool": "T1"}])))
        self.assertIn("needs its floor faces", str(caught.exception))


class Pocket(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.step = block_step(class_directory(cls))
        cls.features = cam.features(cls.step)
        cls.part = read_part(cls.step)
        cls.lower = floor_ref(cls.features, BLOCK["lower"]["floor_z"])

    def plan(self, operations, **kwargs):
        parsed = parse_job(mill_job(operations, **kwargs))
        stock = build_stock(parsed.stock, self.part)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        return setups[0], ops

    def cutting_at(self, plan, z):
        samples = plan.toolpath.sample(0.005, max_step_mm=0.25)
        keep = (samples.kind != RAPID) & np.isclose(samples.points[:, 2], z)
        keep[0] = False
        return samples.points[keep]

    def wall_gap(self, plan, points, z):
        material = plan.sections.at(z + 1e-3)
        return float(shapely.distance(shapely.points(points[:, :2]), material).min())

    def test_a_tool_that_cannot_enter_the_pocket_is_refused_not_cut_short(self):
        # The 30 mm tool fits the upper step (50 x 40) but never the 24 x 20 lower pocket below it.
        for op in ("pocket", "adaptive"):
            with self.subTest(op=op):
                _, ops = self.plan([{"op": op, "tool": "T9", "faces": [self.lower]}], tools=BIG)
                kind, message = plan_error(ops)
                self.assertEqual("tool_too_large", kind)
                self.assertIn("does not fit", message)
                self.assertIn("Z -15.000", message)

    def test_the_length_cut_at_full_width_is_a_fact(self):
        _, ops = self.plan([{"op": "pocket", "tool": "T1", "faces": [self.lower]},
                            {"op": "adaptive", "tool": "T1", "faces": [self.lower]}])
        # Offset rings a 0.4 stepover apart step out into material the ring before half cut: hardly any full width.
        self.assertGreaterEqual(ops[0].meta["full_slot_mm"], 0.0)
        self.assertLess(ops[0].meta["full_slot_mm"], 5 * 6.0)
        self.assertEqual(0.0, ops[1].meta["full_slot_mm"])
        _, ops = self.plan([{"op": "pocket", "tool": "T1", "faces": [self.lower], "entry": "plunge"}])
        # Entered by plunging, each level's first ring is cut at full width.
        self.assertGreater(ops[0].meta["full_slot_mm"], 0.0)

    def test_finish_mm_leaves_the_walls_for_one_ring_at_the_floor(self):
        plan, ops = self.plan([{"op": "pocket", "tool": "T1", "faces": [self.lower], "finish_mm": 0.5}])
        self.assertIsNone(plan_error(ops))
        self.assertEqual(0.5, ops[0].meta["finish_mm"])
        # Above the floor the levels ride 3.5 mm off the walls; at the floor one ring comes to 3.
        self.assertGreaterEqual(self.wall_gap(plan, self.cutting_at(plan, -12.0), -12.0), 3.5 - 0.02)
        self.assertAlmostEqual(3.0, self.wall_gap(plan, self.cutting_at(plan, -15.0), -15.0), delta=0.02)
        self.assertFalse(np.any(plan.toolpath.moves["kind"] == PLUNGE))
        plan, ops = self.plan([{"op": "pocket", "tool": "T1", "faces": [self.lower], "finish_mm": 0.5,
                                "finish_floor_mm": 0.4}])
        self.assertEqual(0.4, ops[0].meta["finish_floor_mm"])
        # The roughing stops 0.4 mm over the floor; a level of its own takes the floor and the walls.
        self.assertGreaterEqual(self.wall_gap(plan, self.cutting_at(plan, -14.6), -14.6), 3.5 - 0.02)
        self.assertAlmostEqual(3.0, self.wall_gap(plan, self.cutting_at(plan, -15.0), -15.0), delta=0.02)


class Linking(unittest.TestCase):
    def test_a_helix_is_found_ahead_along_the_path_when_none_fits_behind_the_start(self):
        from cadgen._internal.cam import linking
        from cadgen._internal.cam.ir import ToolpathBuilder

        region = shapely.box(0.0, 0.0, 10.0, 10.0)
        b = ToolpathBuilder((1.0, 5.0, 5.0), op=0)
        kind = linking.entry(b, region, (1.0, 5.0), 0.0, -2.0, tool_radius=2.0, angle_deg=3.0, f=500.0, plunge_f=200.0,
                             path=np.array([[1.0, 5.0], [9.0, 5.0]]))
        self.assertEqual("helix", kind)
        moves = b.build().moves
        arcs = moves[np.isin(moves["kind"], (ARC_CW, ARC_CCW))]
        self.assertTrue(np.allclose(arcs["i"], 2.5) and np.allclose(arcs["j"], 5.0))   # 1.5 mm ahead of the start
        # A start in a corner, its run along the edge: no circle through it fits; the region's most open point does.
        b = ToolpathBuilder((0.5, 0.5, 5.0), op=0)
        kind = linking.entry(b, region, (0.5, 0.5), 0.0, -2.0, tool_radius=2.0, angle_deg=3.0, f=500.0,
                             plunge_f=200.0, path=np.array([[0.5, 0.5], [9.0, 0.5]]))
        self.assertEqual("helix", kind)
        moves = b.build().moves
        arcs = moves[np.isin(moves["kind"], (ARC_CW, ARC_CCW))]
        self.assertTrue(np.allclose(arcs["i"], 5.0, atol=0.01) and np.allclose(arcs["j"], 5.0, atol=0.01))
        self.assertTrue(np.allclose([moves[-1]["x"], moves[-1]["y"], moves[-1]["z"]], [0.5, 0.5, -2.0]))

    def test_ramp_points_zig_zag_down_no_steeper_than_the_angle_and_end_on_the_start(self):
        from cadgen._internal.cam.linking import ramp_points

        row = np.array([[0.0, 0.0, -2.0], [40.0, 0.0, -2.0]])
        legs = np.asarray(ramp_points(row, 0.0, angle_deg=3.0))
        path = np.vstack([[0.0, 0.0, 0.0], legs])
        across = np.hypot(*np.diff(path[:, :2], axis=0).T)
        drop = -np.diff(path[:, 2])
        self.assertTrue(np.all(drop <= across * math.tan(math.radians(3.0)) + 1e-9))
        self.assertTrue(np.allclose(legs[-1], row[0]))
        self.assertTrue(np.all(legs[:, 2] >= -2.0 - 1e-9))
        self.assertEqual([], ramp_points(row, -2.0, angle_deg=3.0))


if __name__ == "__main__":
    unittest.main()
