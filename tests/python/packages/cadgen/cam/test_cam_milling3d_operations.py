"""The 3D milling operations on the domed boss and the mould: off the part by the stock to leave, on the surface where
they finish, waterlines on the contact, slope limits, pencil in the corner, rest only where material is left, and the
3D gouge check catching a move pushed into the part."""

from __future__ import annotations

import math
import unittest

import numpy as np

from cadgen._internal.cam.dropcutter import drop
from cadgen._internal.cam.ir import PLUNGE, RAPID
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures import class_directory
from tests.python.support.cam_fixtures_milling3d import DOME, MOULD, dome_step, mill3d_job, mould_step

#: The stock top is the part's top plus 1 mm (margin_mm [2, 2, 1]): WCS z = part z - (top + 1).
TOL = 0.02


class Planned(unittest.TestCase):
    step_builder = None
    top = 0.0

    @classmethod
    def setUpClass(cls):
        cls.step = cls.step_builder(class_directory(cls))
        cls.part = read_part(cls.step)

    def plan(self, operations, **job):
        parsed = parse_job(mill3d_job(operations, **job))
        stock = build_stock(parsed.stock, self.part)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        self.parsed = parsed
        return setups[0], ops

    def samples(self, plan, index, *, plunges=True):
        op = next(o for o in plan.toolpath.ops if o.index == index)
        samples = plan.toolpath.slice(op.start, op.end).sample(0.01, max_step_mm=0.25)
        keep = samples.kind != RAPID
        if not plunges:
            keep &= samples.kind != PLUNGE
        keep[0] = False
        return samples.points[keep], samples.points[(samples.kind == RAPID)][1:]

    def tool(self, tool_id):
        return next(t for t in self.parsed.tools if t.id == tool_id)

    def assert_off_the_part(self, plan, points, tool_id, leave=0.0):
        mesh = self.part.mesh_in(plan.wcs)
        allowed = drop(points[:, :2], self.tool(tool_id), mesh, leave=leave - TOL)
        self.assertGreaterEqual(float((points[:, 2] - allowed).min()), -1e-9)


class Dome(Planned):
    step_builder = staticmethod(dome_step)
    top = DOME["top"] + 1.0

    def test_rough_leaves_the_stock_to_leave_and_reaches_the_bottom(self):
        plan, ops = self.plan([{"op": "rough", "tool": "T1", "stock_to_leave_mm": 0.5, "stepdown_mm": 3}])
        points, rapids = self.samples(plan, 0)
        self.assert_off_the_part(plan, points, "T1", leave=0.5)
        self.assert_off_the_part(plan, rapids, "T1")
        self.assertAlmostEqual(-self.top, float(points[:, 2].min()), places=6)
        # The plate's top is a level of its own, the stock to leave over it.
        plate = DOME["plate"][2] - self.top + 0.5
        self.assertTrue(np.any(np.isclose(points[:, 2], plate)))
        meta = ops[0].meta
        self.assertGreaterEqual(meta["levels"], 9)
        self.assertNotIn("plunge", meta["entries"])

    def test_parallel_rides_the_dome(self):
        plan, ops = self.plan([{"op": "parallel", "tool": "T2", "stepover_mm": 1.0, "angle_deg": 30}])
        points, rapids = self.samples(plan, 0, plunges=False)
        self.assert_off_the_part(plan, points, "T2")
        self.assert_off_the_part(plan, rapids, "T2")
        r = np.hypot(points[:, 0], points[:, 1])
        over = r < 15.0
        self.assertGreater(int(over.sum()), 100)
        # A ball on a sphere: its centre stays the sphere's radius plus its own from the sphere's centre.
        ball = 3.0
        z_sphere = DOME["sphere_z"] - self.top
        exact = z_sphere + np.sqrt((DOME["sphere_radius"] + ball) ** 2 - r[over] ** 2) - ball
        self.assertLess(float(np.abs(points[over, 2] - exact).max()), TOL)
        self.assertAlmostEqual(-1.0, float(points[:, 2].max()), delta=TOL)
        self.assertEqual(0, ops[0].meta["links"]["retracts"])

    def test_parallel_keeps_to_shallow_slopes(self):
        plan, _ = self.plan([{"op": "parallel", "tool": "T2", "stepover_mm": 1.0, "max_slope_deg": 20}])
        points, _ = self.samples(plan, 0, plunges=False)
        r = np.hypot(points[:, 0], points[:, 1])
        on_dome = (r < 17.0) & (points[:, 2] > DOME["wall_top"] - self.top)
        # A 20° slope on the R30 sphere is at r = 30 sin 20°; the ball's centre is 33/30 of that out.
        self.assertLess(float(r[on_dome].max()), 33 * math.sin(math.radians(20)) + 0.6)

    def test_waterline_loops_touch_the_boss_wall(self):
        plan, ops = self.plan([{"op": "waterline", "tool": "T2", "stepdown_mm": 2.0, "min_slope_deg": 60}])
        points, rapids = self.samples(plan, 0, plunges=False)
        self.assert_off_the_part(plan, points, "T2")
        self.assert_off_the_part(plan, rapids, "T2")
        wall = (points[:, 2] < DOME["wall_top"] - self.top - 0.5) & (points[:, 2] > DOME["plate"][2] - self.top + 0.5)
        r = np.hypot(points[wall, 0], points[wall, 1])
        self.assertGreater(len(r), 100)
        # On the contact: the ball's centre 3 mm off the R18 wall, within the tolerance (never nearer than the
        # tessellation's chords, which sit up to its deflection inside the true wall).
        self.assertGreaterEqual(float(r.min()), 21.0 - self.part.deflection_mm - 1e-6)
        self.assertLess(float(r.max()), 21.0 + TOL)
        levels = np.unique(np.round(points[wall, 2], 6))
        self.assertGreaterEqual(len(levels), 5)

    def test_scallop_is_lite_and_stays_off_the_part(self):
        plan, ops = self.plan([{"op": "scallop", "tool": "T2", "stepover_mm": 1.5}])
        points, _ = self.samples(plan, 0)
        self.assert_off_the_part(plan, points, "T2")
        self.assertEqual("lite", ops[0].operation.status)
        self.assertTrue(ops[0].operation.limits)
        self.assertEqual(0, ops[0].meta["links"]["retracts"])

    def test_the_3d_gouge_check_catches_a_move_into_the_part(self):
        from cadgen._internal.cam.checks._gouge3d import gouges_3d
        from cadgen._internal.cam.checks.base import CheckContext

        plan, ops = self.plan([{"op": "parallel", "tool": "T2", "stepover_mm": 2.0}])
        ctx = CheckContext(job=self.parsed, part=self.part, stock=None, sim=None, sim_reports={}, setups=[plan],
                           ops=ops, tolerance_mm=0.01)
        for op in ops:
            op.start, op.end = plan.toolpath.ops[0].start, plan.toolpath.ops[0].end
        self.assertEqual([], gouges_3d(ctx, TOL))
        moves = plan.toolpath.moves
        feeds = np.nonzero(moves["kind"] == 1)[0]
        hit = feeds[len(feeds) // 2]
        moves["z"][hit] -= 0.5
        found = gouges_3d(ctx, TOL)
        self.assertEqual(1, len(found))
        self.assertEqual("gouge_3d", found[0]["type"])
        self.assertGreater(found[0]["items"][0]["depth_mm"], 0.1)
        self.assertLessEqual(found[0]["items"][0]["depth_mm"], 0.5 + TOL)


class Mould(Planned):
    step_builder = staticmethod(mould_step)
    top = MOULD["size"][2] + 1.0

    def test_rough_clears_the_cavity_by_helix_and_the_outside_from_the_air(self):
        plan, ops = self.plan([{"op": "rough", "tool": "T3", "stock_to_leave_mm": 0.3, "stepdown_mm": 2.5}])
        points, rapids = self.samples(plan, 0)
        self.assert_off_the_part(plan, points, "T3", leave=0.3)
        self.assert_off_the_part(plan, rapids, "T3")
        floor = MOULD["size"][2] - MOULD["cavity"][2] - self.top
        inside = (np.abs(points[:, 0]) < 10) & (np.abs(points[:, 1]) < 5)
        self.assertAlmostEqual(floor + 0.3, float(points[inside, 2].min()), places=6)
        self.assertIn("helix", ops[0].meta["entries"])

    def test_pencil_runs_round_the_cavity_floor(self):
        plan, ops = self.plan([{"op": "pencil", "tool": "T2"}])
        points, _ = self.samples(plan, 0, plunges=False)
        self.assertEqual("lite", ops[0].operation.status)
        self.assertGreaterEqual(ops[0].meta["passes"], 1)
        floor = MOULD["size"][2] - MOULD["cavity"][2] - self.top
        self.assertLess(float(np.abs(points[:, 2] - floor).max()), TOL)
        # Along the corner: as close to the walls as a 6 mm ball goes over the R3 floor fillet.
        half_x, half_y = MOULD["cavity"][0] / 2, MOULD["cavity"][1] / 2
        margin = np.minimum(half_x - np.abs(points[:, 0]), half_y - np.abs(points[:, 1]))
        self.assertLess(float(np.median(margin)), 3.0 + 0.3)
        self.assert_off_the_part(plan, points, "T2")

    def test_rest_from_a_bigger_tool_keeps_to_the_corners(self):
        plan, ops = self.plan([{"op": "rest", "of": "parallel", "tool": "T4", "from_tool_diameter_mm": 6,
                                "stepover_mm": 0.3}])
        points, _ = self.samples(plan, 0, plunges=False)
        self.assertGreater(len(points), 50)
        self.assert_off_the_part(plan, points, "T4")
        self.assertGreater(ops[0].meta["rest_area_mm2"], 1.0)
        # Nothing in the open middle of the cavity floor, where the 6 mm ball reached.
        self.assertGreater(float(np.hypot(points[:, 0], points[:, 1]).min()), 5.0)
        self.assertIn("Rest machining (parallel)", ops[0].summary)

    def test_rest_after_finishing_reads_the_simulated_stock(self):
        plan, ops = self.plan([{"op": "rough", "tool": "T1", "stock_to_leave_mm": 0.3, "stepdown_mm": 5},
                               {"op": "waterline", "tool": "T2", "stepdown_mm": 1.5},
                               {"op": "rest", "of": "waterline", "tool": "T4", "stepdown_mm": 1.5}])
        rest = ops[2]
        self.assertEqual("the simulated stock", rest.meta["rest_from"])
        self.assertGreater(rest.meta["rest_area_mm2"], 0.0)
        points, _ = self.samples(plan, 2, plunges=False)
        self.assert_off_the_part(plan, points, "T4")

    def test_teaching_errors(self):
        cases = [
            ({"op": "rest", "tool": "T4"}, "needs \"of\""),
            ({"op": "rest", "tool": "T4", "of": "parallel", "bottom_z": -3}, "'bottom_z' is not a key of a parallel"),
            ({"op": "rest", "tool": "T4", "of": "parallel", "from_tool_diameter_mm": 1}, "must be more than"),
            ({"op": "parallel", "tool": "T2", "min_slope_deg": 50, "max_slope_deg": 40}, "must be less than"),
            ({"op": "rough", "tool": "T1", "faces": ["#o1.f1"]}, "takes no faces"),
            ({"op": "waterline", "tool": "T2", "angle_deg": 10}, "unknown key 'angle_deg'"),
            ({"op": "pencil", "tool": "T2", "crease_deg": 0}, "crease_deg must be more than 0"),
        ]
        for op, words in cases:
            with self.subTest(op=op):
                with self.assertRaises(CamJobError) as caught:
                    parse_operations(parse_job(mill3d_job([op])))
                self.assertIn(words, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
