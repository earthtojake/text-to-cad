"""Adaptive clearing cuts where material stands: the air report's own measure on paths whose answer is known, a second
adaptive over what the first cleared, an adaptive after a pocket took the upper step, and adaptive_3d round the mould,
alone and after a rough. Every plan's descents and rapids are sound (tests/python/support/cam_soundness.py)."""

from __future__ import annotations

import math
import unittest
from types import SimpleNamespace

import numpy as np
import shapely

from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock

from tests.python.support.cam_fixtures import BLOCK, block_step, class_directory, floor_ref, mill_job, quiet
from tests.python.support.cam_fixtures_milling3d import MOULD, mill3d_job, mould_step
from tests.python.support.cam_soundness import bad_descents, rapids_below


def plan(part, raw):
    from cadgen._internal.cam.part import read_part

    parsed = parse_job(raw)
    shape = read_part(part)
    stock = build_stock(parsed.stock, shape)
    with quiet():
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), shape, stock)
    return setups[0], ops, stock


def seconds(planned, index: int) -> float:
    """Operation ``index``'s time in its setup's program (default rapid rate)."""
    t0, t1 = planned[0].toolpath.op_times()[index]
    return t1 - t0


class AirReport(unittest.TestCase):
    """Straight passes and rings at 2 mm deep in a slab of stock, with a 6 mm flat."""

    @classmethod
    def setUpClass(cls):
        from cadgen._internal.cam.tools import parse_tool

        cls.ctx = SimpleNamespace(tool=parse_tool({"id": "T1", "type": "flat", "diameter_mm": 6}, 0),
                                  tolerance_mm=0.01, stock_outline=shapely.box(-50, -50, 50, 50),
                                  heights=SimpleNamespace(stock_top=0.0))

    def report(self, *passes):
        from cadgen._internal.cam.air import air_report
        from cadgen._internal.cam.ir import ToolpathBuilder

        b = ToolpathBuilder((0, -30, 5))
        for points in passes:
            b.rapid(x=points[0][0], y=points[0][1])
            b.rapid(z=-2)
            b.polyline(np.column_stack([points[1:], np.full(len(points) - 1, -2.0)]), f=1000)
            b.rapid(z=5)
        # A slab of stock 50 mm round, its top at Z 0, and no part in it.
        slab = SimpleNamespace(
            surface_at=lambda xy: np.where(np.abs(np.asarray(xy)).max(axis=1) < 50.0, 0.0, -np.inf),
            part_surface_at=lambda xy: np.full(len(xy), -np.inf))
        return air_report(self.ctx, b.build(), stock_now=slab)

    def test_a_pass_that_removes_nothing_is_air_and_one_that_removes_a_sliver_is_not(self):
        line = lambda y: np.column_stack([np.linspace(-20, 20, 200), np.full(200, y)])  # noqa: E731
        self.assertEqual(0.0, self.report(line(0))["air_fraction"])
        self.assertEqual(0.5, self.report(line(0), line(0))["air_fraction"])
        self.assertEqual(0.0, self.report(line(0), line(0.3))["air_fraction"])

    def test_finely_pointed_rings_a_stepover_apart_are_cutting(self):
        def ring(radius):
            angle = np.linspace(0.0, 2.0 * math.pi, 400)
            return np.column_stack([radius * np.cos(angle), radius * np.sin(angle)])

        self.assertLess(self.report(*[ring(1.0 + 0.9 * k) for k in range(10)])["air_fraction"], 0.05)


class Adaptive2d(unittest.TestCase):
    """The block's stepped pocket cleared by adaptive: once, twice, and after a pocket took its upper step."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = block_step(cls.directory)
        features = cam.features(cls.step)
        cls.lower = floor_ref(features, BLOCK["lower"]["floor_z"])
        upper = floor_ref(features, BLOCK["upper"]["floor_z"])
        adaptive = {"op": "adaptive", "tool": "T1", "faces": [cls.lower]}
        cls.twice = plan(cls.step, mill_job([adaptive, adaptive]))
        cls.after = plan(cls.step, mill_job([{"op": "pocket", "tool": "T1", "faces": [upper]}, adaptive]))
        # A region inside the upper step, clear of its walls and the island, down to its floor (WCS: the stock top,
        # 1 mm over the block, is Z0).
        inside = {"op": "adaptive", "tool": "T1", "region": {"polygon": [[-20, -12], [-2, -12], [-2, 12], [-20, 12]],
                                                             "bottom_z": BLOCK["upper"]["floor_z"] - 26.0}}
        cls.cleared = plan(cls.step, mill_job([{"op": "pocket", "tool": "T1", "faces": [upper]}, inside]))

    def test_a_second_adaptive_over_what_the_first_cleared_cuts_almost_nothing(self):
        setup, ops, stock = self.twice
        first, second = ops[0].meta, ops[1].meta
        self.assertLess(second["air_mm"] + second["cut_mm"], 0.15 * (first["air_mm"] + first["cut_mm"]))
        self.assertLess(seconds(self.twice, 1), 0.15 * seconds(self.twice, 0))
        for op in ops:
            with self.subTest(op=op.index):
                self.assertEqual([], bad_descents(setup, ops, op.index, stock=stock))
                self.assertEqual([], rapids_below(setup, op.index))

    def test_after_a_pocket_it_cuts_what_the_pocket_left(self):
        setup, ops, stock = self.after
        meta = ops[1].meta
        self.assertLess(seconds(self.after, 1), 0.5 * seconds(self.twice, 0))
        self.assertLess(meta["air_fraction"], 0.6)
        self.assertEqual([], bad_descents(setup, ops, 1, stock=stock))
        self.assertEqual([], rapids_below(setup, 1))

    def test_a_region_the_pocket_already_cleared_is_skipped_level_by_level(self):
        setup, ops, _ = self.cleared
        meta = ops[1].meta
        self.assertEqual(0, meta["levels"])
        self.assertGreater(meta["levels_already_clear"], 0)
        self.assertIn("nothing left to clear", meta["note"])
        self.assertEqual(0.0, meta["cut_mm"])


class Adaptive3d(unittest.TestCase):
    """The mould (a block with a filleted cavity, 2 mm of stock round it) roughed by adaptive_3d, alone and after a
    coarse rough."""

    @classmethod
    def setUpClass(cls):
        cls.directory = class_directory(cls)
        cls.step = mould_step(cls.directory)
        clear = {"op": "adaptive_3d", "tool": "T1", "stock_to_leave_mm": 0.3}
        cls.alone = plan(cls.step, mill3d_job([clear]))
        cls.after = plan(cls.step, mill3d_job([{"op": "rough", "tool": "T1", "stock_to_leave_mm": 0.3,
                                                "stepdown_mm": 5}, clear]))

    def test_it_clears_the_cavity_to_its_floor_from_a_helix_and_the_outside_from_the_air(self):
        setup, ops, stock = self.alone
        meta = ops[0].meta
        self.assertGreater(meta["entries"]["helix"], 0)      # the closed cavity
        self.assertGreater(meta["entries"]["air"], 0)        # the stock round the block, come into from beside it
        tp = setup.toolpath
        rng = next(o for o in tp.ops if o.index == 0)
        ends = tp.positions()[rng.start + 1:rng.end + 1]
        cavity = (np.abs(ends[:, 0]) < MOULD["cavity"][0] / 2 - 4) & (np.abs(ends[:, 1]) < MOULD["cavity"][1] / 2 - 4)
        # The cavity floor plus the stock to leave, in the setup's WCS (stock top at Z0, 1 mm over the part).
        floor = MOULD["size"][2] - MOULD["cavity"][2] + 0.3 - (MOULD["size"][2] + 1.0)
        self.assertAlmostEqual(floor, float(ends[cavity, 2].min()), places=3)
        self.assertEqual([], bad_descents(setup, ops, 0, stock=stock))
        self.assertEqual([], rapids_below(setup, 0))

    def test_after_a_rough_it_cuts_only_what_the_rough_left(self):
        setup, ops, stock = self.after
        _, alone, _ = self.alone
        self.assertLess(seconds(self.after, 1), 0.3 * seconds(self.alone, 0))
        self.assertLess(ops[1].meta["air_mm"], 0.5 * alone[0].meta["air_mm"])
        self.assertEqual([], bad_descents(setup, ops, 1, stock=stock))
        self.assertEqual([], rapids_below(setup, 1))


if __name__ == "__main__":
    unittest.main()
