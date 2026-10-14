"""``cadgen cam plan`` with 3D milling end to end on the mould: rough, finish and rest are ready to cut and read back
from their G-code; a small ball whose shank is wider than its flutes are long hits the cavity's walls and the stock."""

from __future__ import annotations

import unittest

import numpy as np

from tests.python.support import gcode_reader
from tests.python.support.cam_fixtures import class_directory, quiet, read_glb
from tests.python.support.cam_fixtures_milling3d import MOULD, mill3d_job, mould_step


class PlanMould(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = mould_step(cls.directory)
        cls.job = mill3d_job([
            {"op": "rough", "tool": "T1", "stock_to_leave_mm": 0.3, "stepdown_mm": 5},
            {"op": "parallel", "tool": "T2", "stepover_mm": 1.5},
            {"op": "rest", "of": "parallel", "tool": "T4", "from_tool_diameter_mm": 6, "stepover_mm": 0.5},
        ])
        with quiet():
            cls.result = cam.plan(cls.step, job=cls.job)

    def test_ready_with_every_3d_check_run(self):
        result = self.result
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("ready", result.verdict["status"], result.findings)
        self.assertEqual(["rough", "parallel", "rest"], [op["op"] for op in result.operations])
        for check in ("gouge", "holder_collision"):
            self.assertIn(check, result.summary["checks_ran"])
        self.assertFalse([f for f in result.findings if f["check"] in ("gouge", "holder_collision", "rapid_into_stock")])
        self.assertEqual(["T1 6 mm flat", "T2 6 mm ball", "T4 2 mm ball"],
                         [f"{op['tool']} {op['tool_plain']}" for op in result.operations])

    def test_the_gcode_reads_back_and_reaches_the_cavity_floor(self):
        text = gcode_reader.posted_text(self.result, "top")
        program = gcode_reader.read(text, start=(0.0, 0.0, 6.0))
        points, kinds = gcode_reader.sample(program, max_step=0.5)
        middle = (np.asarray(kinds) != "rapid") & (np.abs(points[:, 0]) < 10) & (np.abs(points[:, 1]) < 5)
        floor = MOULD["size"][2] - MOULD["cavity"][2] - (MOULD["size"][2] + 1.0)
        # Over the middle of the cavity the ball finishing it touches the floor with its tip, and nothing goes lower.
        self.assertGreater(int(middle.sum()), 20)
        self.assertAlmostEqual(floor, float(points[middle, 2].min()), delta=0.02)
        document, _ = read_glb(self.result.glb)
        cam = document["scenes"][0]["extras"]["cam"]
        rows = cam["setups"][0]["operations"]
        self.assertEqual("3D milling", rows[0]["family"])
        self.assertEqual("Rest machining", rows[2]["plain"])

    def test_a_shank_wider_than_short_flutes_hits_the_walls_and_the_stock(self):
        from cadgen import cam

        job = mill3d_job([{"op": "parallel", "tool": "T4", "stepover_mm": 2.0,
                           "region": {"polygon": [[-20, -15], [20, -15], [20, 15], [-20, 15]]}}])
        job["tools"][3]["flute_length_mm"] = 3
        with quiet():
            result = cam.plan(self.step, job=job, out_dir=self.directory / "short")
        self.assertTrue(result.ok)
        self.assertEqual("fix", result.verdict["status"])
        kinds = {f["type"] for f in result.findings if f["check"] == "holder_collision"}
        self.assertEqual({"shank_part", "shank_stock"}, kinds)


if __name__ == "__main__":
    unittest.main()
