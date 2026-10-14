"""Face and pocket on the block: the path stays in its region, reaches its floors, rounds the island, enters by helix."""

from __future__ import annotations

import unittest

import numpy as np

from cadgen._internal.cam.ir import RAPID
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures import BLOCK, block_step, class_directory, floor_ref, mill_job


class BlockOperations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.step = block_step(class_directory(cls))
        cls.features = cam.features(cls.step)
        cls.part = read_part(cls.step)
        cls.lower = floor_ref(cls.features, BLOCK["lower"]["floor_z"])
        cls.upper = floor_ref(cls.features, BLOCK["upper"]["floor_z"])

    def plan(self, operations, **job):
        parsed = parse_job(mill_job(operations, **job))
        stock = build_stock(parsed.stock, self.part)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        return setups[0], ops

    def cutting(self, plan, op_index):
        op = next(o for o in plan.toolpath.ops if o.index == op_index)
        samples = plan.toolpath.slice(op.start, op.end).sample(0.01, max_step_mm=0.5)
        keep = samples.kind != RAPID
        keep[0] = False
        return samples.points[keep], op

    def test_the_pocket_reaches_its_floors_and_keeps_off_the_walls_and_the_island(self):
        plan, ops = self.plan([{"op": "pocket", "tool": "T1", "faces": [self.lower]}])
        points, op = self.cutting(plan, 0)
        # WCS zero is the stock's top (the part's top + 1): the lower floor is at -15, the upper at -9.
        self.assertAlmostEqual(-15.0, float(points[:, 2].min()), places=6)
        on_upper = points[np.isclose(points[:, 2], -9.0)]
        self.assertTrue(len(on_upper) and on_upper[:, 0].max() > 15.0, "the upper step is cleared too")
        island = np.hypot(points[:, 0] - 14.0, points[:, 1])
        above_upper = points[:, 2] > -9.0 - 1e-6
        self.assertGreaterEqual(float(island[above_upper].min()), 4.0 + 3.0 - 0.02)
        # Nowhere does the tool come closer to the material at its height than its radius.
        for z in np.unique(np.round(points[:, 2], 6)):
            group = points[np.isclose(points[:, 2], z)]
            material = plan.sections.at(float(z) + 1e-3)
            if material.is_empty:
                continue
            import shapely

            distance = shapely.distance(shapely.points(group[:, :2]), material)
            self.assertGreaterEqual(float(distance.min()), 3.0 - 0.02, f"at z {z}")
        meta = ops[0].meta
        self.assertEqual(meta["levels"], meta["entries"]["helix"])
        self.assertEqual(8, len(meta["unreachable"]))           # the eight square inside corners

    def test_stock_to_leave_holds_off_walls_and_floor(self):
        plan, _ = self.plan([{"op": "pocket", "tool": "T1", "faces": [self.upper], "stock_to_leave_mm": 0.5}])
        points, _ = self.cutting(plan, 0)
        self.assertAlmostEqual(-8.5, float(points[:, 2].min()), places=6)
        self.assertLessEqual(float(points[:, 0].max()), 25.0 - 3.0 - 0.5 + 0.02)

    def test_face_takes_the_top_down_to_the_part_from_outside_the_stock(self):
        plan, ops = self.plan([{"op": "face", "tool": "T1"}])
        points, _ = self.cutting(plan, 0)
        sx, sy, _ = BLOCK["size"]
        # Every pass is at Z -1; above it is only the fed last millimetre of a descent beside the stock (top at 0).
        above = points[points[:, 2] > -1.0 + 1e-6]
        self.assertTrue(len(above) and np.all(above[:, 2] <= 1.0 + 1e-6))
        self.assertTrue(np.all((np.abs(above[:, 0]) > sx / 2 + 2) | (np.abs(above[:, 1]) > sy / 2 + 2)))
        self.assertTrue(np.allclose(points[points[:, 2] <= -1.0 + 1e-6][:, 2], -1.0))
        self.assertLess(float(points[:, 0].min()), -(sx / 2 + 2 + 3))     # passes start beyond the stock
        self.assertLessEqual(float(points[:, 1].min()), -(sy / 2 + 2) + 1e-6)
        self.assertGreaterEqual(float(points[:, 1].max()), sy / 2 + 2 - 1e-6)
        rapids = plan.toolpath.moves[plan.toolpath.moves["kind"] == RAPID]
        self.assertGreaterEqual(float(rapids["z"].min()), -1.0)
        self.assertNotIn("plunges", ops[0].meta)

    def test_a_pocket_on_a_wall_teaches(self):
        wall = next(f["ref"] for f in self.features.faces if f.get("normal") and abs(f["normal"][0]) == 1.0)
        with self.assertRaises(CamJobError) as caught:
            self.plan([{"op": "pocket", "tool": "T1", "faces": [wall]}])
        self.assertIn("names flat floors facing the tool", str(caught.exception))
        with self.assertRaises(CamJobError) as caught:
            parse_operations(parse_job(mill_job([{"op": "pocket", "tool": "T1", "faces": [self.lower], "entry": "dive"}])))
        self.assertIn("entry is 'dive'; use one of helix, ramp, plunge", str(caught.exception))
        with self.assertRaises(CamJobError) as caught:
            parse_operations(parse_job(mill_job([{"op": "pocket", "tool": "T2", "faces": [self.lower]}])))
        self.assertIn("T2 is a drill", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
