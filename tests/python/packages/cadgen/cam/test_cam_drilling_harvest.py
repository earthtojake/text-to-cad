"""The drill operation on the hole block: a counterbored or countersunk hole is drilled from where it opens on the
part, a spot is its countersink's width, a hole under a roof is not reached, a hole that ends in a cross bore is
drilled into it, a drawn point is a hard floor; and the whole job plans without a gouge or a rapid into stock."""

from __future__ import annotations

import math
import unittest

from cadgen._internal.cam.ir import PLUNGE
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures import class_directory, quiet
from tests.python.support.cam_fixtures_drilling import BLOCK, drill_job, hole_block_step

#: WCS z = part z - 21 (stock-top-center, 1 mm of stock over the 20 mm block).
TOP = -1.0
TOOLS = [
    {"id": "T1", "type": "drill", "diameter_mm": 5},
    {"id": "T2", "type": "drill", "diameter_mm": 6},
    {"id": "T4", "type": "spot", "diameter_mm": 6},
    {"id": "T8", "type": "spot", "diameter_mm": 10},
]


def tip(diameter: float, angle: float = 118.0) -> float:
    return diameter / 2 / math.tan(math.radians(angle / 2))


class HoleBlock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        with quiet():
            cls.directory = class_directory(cls)
            cls.step = hole_block_step(cls.directory)
            cls.features = cam.features(cls.step)
            cls.part = read_part(cls.step)
        cls.at = {(round(h["center_mm"][0], 3), round(h["center_mm"][1], 3)): h for h in cls.features.holes}
        cls.cbore = cls.at[BLOCK["counterbore"]["center"]]
        cls.csink = cls.at[BLOCK["countersink"]["center"]]
        cls.pointed = cls.at[BLOCK["pointed"]["center"]]
        cls.flat = cls.at[BLOCK["flat"]["center"]]
        cls.down = cls.at[BLOCK["cross"]["down"]]
        cls.cave = cls.at[BLOCK["cave"]["hole"]]

    def plan(self, operations, **job):
        job.setdefault("tools", TOOLS)
        parsed = parse_job(drill_job(operations, **job))
        stock = build_stock(parsed.stock, self.part)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        return setups, ops

    def one(self, op, **job):
        setups, ops = self.plan([op], **job)
        path = setups[0].toolpath
        rng = next(o for o in path.ops if o.index == 0)
        return path, rng, ops[0]

    @staticmethod
    def cycles(path, rng):
        return [e for e in path.events if e.kind == "cycle" and rng.start <= e.at < rng.end]

    @staticmethod
    def lowest(path, rng) -> float:
        moves = path.moves[rng.start:rng.end]
        return float(moves[moves["kind"] == PLUNGE]["z"].min())

    def test_a_counterbored_hole_is_fed_from_over_the_part_not_from_its_shoulder(self):
        refs = self.cbore["faces"]          # the Ø5 wall, the counterbore's wall, its shoulder: each names the hole
        for ref in refs:
            with self.subTest(ref=ref):
                path, rng, op = self.one({"op": "drill", "tool": "T1", "faces": [ref]})
                (cycle,) = self.cycles(path, rng)
                (hole,) = cycle.data["holes"]
                self.assertAlmostEqual(TOP, hole[2], places=6)                 # opens at the block's top
                self.assertAlmostEqual(cycle.data["initial_z"], cycle.data["r_plane"], places=6)
                self.assertGreater(cycle.data["r_plane"], TOP)
                self.assertAlmostEqual(TOP - 20.0 - 1.0 - tip(5.0), self.lowest(path, rng), places=6)
                self.assertEqual([refs[0]], [h["faces"][0] for h in op.meta["holes"]])

    def test_a_countersunk_hole_opens_at_its_top_and_a_spot_is_the_countersinks_width(self):
        path, rng, _ = self.one({"op": "drill", "tool": "T1", "faces": self.csink["faces"][:1]})
        (cycle,) = self.cycles(path, rng)
        self.assertAlmostEqual(TOP, cycle.data["holes"][0][2], places=6)
        self.assertGreater(cycle.data["r_plane"], TOP)
        # The 10 mm spot drill makes the Ø10 countersink: 5 mm deep at 90°.
        path, rng, _ = self.one({"op": "drill", "tool": "T8", "faces": self.csink["faces"][:1]})
        self.assertAlmostEqual(TOP - 5.0, self.lowest(path, rng), places=6)
        # A 6 mm spot drill cannot: refused, unless the job names a spot it can make.
        _, _, op = self.one({"op": "drill", "tool": "T4", "faces": self.csink["faces"][:1]})
        self.assertEqual("tool_too_small", op.meta["plan_error"]["kind"])
        self.assertIn("wants a Ø10 spot (its countersink)", op.meta["plan_error"]["message"])
        path, rng, _ = self.one({"op": "drill", "tool": "T4", "faces": self.csink["faces"][:1],
                                 "spot_diameter_mm": 6})
        self.assertAlmostEqual(TOP - 3.0, self.lowest(path, rng), places=6)

    def test_a_hole_under_a_roof_is_unreachable_and_all_leaves_it_out(self):
        _, _, op = self.one({"op": "drill", "tool": "T1", "faces": self.cave["faces"][:1]})
        error = op.meta["plan_error"]
        self.assertEqual("unreachable", error["kind"])
        self.assertIn(f"{self.cave['faces'][0]} is a Ø5 x 3 blind hole whose opening the part covers",
                      error["message"])
        self.assertIn("nothing reaches it along its axis", error["message"])
        path, rng, op = self.one({"op": "drill", "tool": "T1", "holes": {"diameter_mm": 5}})
        drilled = {tuple(round(v, 3) for v in h["at"]) for h in op.meta["holes"]}
        self.assertNotIn(BLOCK["cave"]["hole"], drilled)
        self.assertEqual(3, len(drilled))
        self.assertIn("1 matching hole along this setup's Z left out: the part covers its opening", op.meta["note"])

    def test_a_hole_ending_in_a_cross_bore_is_drilled_through_into_it_from_the_top_only(self):
        path, rng, _ = self.one({"op": "drill", "tool": "T1", "faces": self.down["faces"][:1]})
        exit_z = self.down["bottom_mm"][2] - 21.0
        lowest = self.lowest(path, rng)
        self.assertAlmostEqual(exit_z - 1.0 - tip(5.0), lowest, places=6)
        cross = BLOCK["cross"]
        self.assertGreater(lowest, cross["z"] - cross["diameter"] / 2 - 21.0)   # the tip stays in the bore's air
        # From underneath, its end is inside the bore: the part covers it.
        drill = {"op": "drill", "tool": "T1", "faces": self.down["faces"][:1]}
        setups = [{"id": "top", "orientation": "+Z", "origin": "stock-top-center", "operations": [drill]},
                  {"id": "under", "orientation": "-Z", "origin": "stock-top-center", "operations": [drill]}]
        _, ops = self.plan([], setups=setups)
        self.assertNotIn("plan_error", ops[0].meta)
        self.assertEqual("unreachable", ops[1].meta["plan_error"]["kind"])
        self.assertIn("drill it in setup 'top'", ops[1].meta["plan_error"]["message"])

    def test_a_drawn_point_shorter_than_the_drills_is_a_hard_floor(self):
        floor = BLOCK["size"][2] - BLOCK["pointed"]["depth"] - 21.0
        point = 3.0 / math.tan(math.radians(BLOCK["pointed"]["point_angle"] / 2))
        path, rng, op = self.one({"op": "drill", "tool": "T2", "faces": self.pointed["faces"][:1]})
        self.assertAlmostEqual(floor - point, self.lowest(path, rng), places=3)
        (found,) = op.meta["findings"]
        self.assertEqual("hole_floor", found["type"])
        self.assertIn(f"stops {tip(6.0) - point:.3g} mm short of the floor", found["summary"])
        self.assertIn(f"a {point:.3g} mm drawn point", found["description"])

    def test_the_block_plans_with_no_gouge_and_no_rapid_into_stock(self):
        from cadgen._internal.cam.run import plan_job

        ops = [{"op": "drill", "tool": "T1", "faces": [self.cbore["faces"][0], self.csink["faces"][0],
                                                       self.down["faces"][0]]},
               {"op": "drill", "tool": "T8", "faces": self.csink["faces"][:1]},
               {"op": "drill", "tool": "T2", "faces": self.pointed["faces"][:1]},
               {"op": "drill", "tool": "T2", "faces": self.flat["faces"][:1], "depth_to": "shoulder"}]
        with quiet():
            result = plan_job(self.step, job=drill_job(ops, tools=TOOLS, post="fanuc"), out_dir=self.directory / "out")
        self.assertTrue(result.ok, result.findings)
        errors = [(f["type"], f["summary"]) for f in result.findings if f["severity"] == "error"]
        self.assertEqual([], errors)
        floors = [f for f in result.findings if f["type"] == "hole_floor"]
        self.assertEqual(2, len(floors))


if __name__ == "__main__":
    unittest.main()
