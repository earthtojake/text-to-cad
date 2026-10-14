"""Circular and trace: a round pocket spiralled out to its wall and a boss spiralled in to its own, a chain of edges
followed on, inside, outside, left or right of it at a depth; every descent into material a ramp or a helix, the
refusals, and both planned end to end through ``cam.plan`` with no gouge."""

from __future__ import annotations

import math
import unittest

import numpy as np

from cadgen._internal.cam.ir import ARC_CCW, ARC_CW
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures import quiet
from tests.python.support.cam_fixtures_milling2d import boss_step, class_directory, face_at, job, tools
from tests.python.support.cam_soundness import bad_descents, rapids_below

#: The round part: a 70 x 50 x 12 plate on z = 0, centred, with a Ø20 round pocket 5 deep (floor z = 7) at (-15, 0),
#: a Ø14 through hole at (20, 0) and a Ø6 through hole at (20, 17). In the job's WCS (stock-top-center, 1 mm of stock
#: on top) the plate's top is Z -1, the pocket's floor Z -6 and its bottom Z -13.
ROUND = {"pocket": (-15.0, 0.0, 20.0, 7.0), "hole": (20.0, 0.0, 14.0), "small": (20.0, 17.0, 6.0)}
#: The crowded boss: a 50 x 30 x 5 base, a Ø10 boss 10 tall at (0, 0), and a block 8 mm from the boss's wall
#: (x 13 to 20) standing 15 tall.
CROWDED = {"boss": 10.0, "gap": 8.0}
EXTRA = {"T7": {"id": "T7", "type": "flat", "diameter_mm": 10, "flutes": 3, "flute_length_mm": 25, "stickout_mm": 40},
         "T8": {"id": "T8", "type": "flat", "diameter_mm": 22, "flutes": 3, "flute_length_mm": 25, "stickout_mm": 40},
         "T9": {"id": "T9", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 35}}


def round_step(directory):
    from build123d import Align, Box, Cylinder, Pos, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    x, y, d, floor = ROUND["pocket"]
    part = Box(70, 50, 12, align=base) - Pos(x, y, floor) * Cylinder(d / 2, 12 - floor, align=base)
    for hx, hy, hd in (ROUND["hole"], ROUND["small"]):
        part -= Pos(hx, hy, 0) * Cylinder(hd / 2, 12, align=base)
    path = directory / "round.step"
    export_step(part, str(path))
    return path


def crowded_step(directory):
    from build123d import Align, Box, Cylinder, Pos, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    part = Box(50, 30, 5, align=base) + Pos(0, 0, 5) * Cylinder(CROWDED["boss"] / 2, 10, align=base)
    part += Pos(16.5, 0, 0) * Box(7, 30, 15, align=base)
    path = directory / "crowded.step"
    export_step(part, str(path))
    return path


def edges(step, test) -> list[str]:
    """The part's edge refs whose (bounding box min, max, length) pass ``test``, in ordinal order."""
    from cadgen.step_scene import read_scene

    leaf = next(iter(read_scene(step).leaves()))
    out = []
    for selection in leaf.entities("edge"):
        shape = selection.shape()
        box = shape.bounding_box()
        low, high = (box.min.X, box.min.Y, box.min.Z), (box.max.X, box.max.Y, box.max.Z)
        if test(np.round(low, 6), np.round(high, 6), round(shape.length, 6)):
            out.append(selection.ref)
    return out


def plan(part, operations, extra_tools=None):
    parsed = parse_job(job(operations, tools=tools(**(extra_tools or {}))))
    stock = build_stock(parsed.stock, part)
    setups, ops, _ = plan_setups(parsed, parse_operations(parsed), part, stock)
    return setups[0], ops, stock


def op_path(setup, index=0):
    rng = next(o for o in setup.toolpath.ops if o.index == index)
    return setup.toolpath.slice(rng.start, rng.end)


def cut_points(setup, index=0, z=None):
    """The sampled points of an operation's cutting moves (feeds and arcs), at height ``z`` when given."""
    path = op_path(setup, index)
    samples = path.sample(0.005)
    keep = samples.kind != 0
    points = samples.points[keep]
    if z is not None:
        points = points[np.abs(points[:, 2] - z) < 1e-6]
    return points


class Circular(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.round = round_step(cls.directory)
        cls.boss = boss_step(cls.directory)
        cls.crowded = crowded_step(cls.directory)
        cls.round_part = read_part(cls.round)
        cls.boss_part = read_part(cls.boss)
        cls.crowded_part = read_part(cls.crowded)
        features = cam.features(cls.round)
        cls.pocket = face_at(features, surface="cylinder", diameter_mm=20.0)
        cls.hole = face_at(features, surface="cylinder", diameter_mm=14.0)
        cls.small = face_at(features, surface="cylinder", diameter_mm=6.0)
        cls.stud = face_at(cam.features(cls.boss), surface="cylinder", diameter_mm=12.0)
        cls.crowded_boss = face_at(cam.features(cls.crowded), surface="cylinder", diameter_mm=10.0)

    def sound(self, setup, ops, stock, index=0):
        self.assertEqual([], bad_descents(setup, ops, index, stock=stock))
        self.assertEqual([], rapids_below(setup, index))

    def test_a_round_pocket_helixes_in_at_its_centre_and_spirals_out_to_its_wall(self):
        setup, ops, stock = plan(self.round_part, [{"op": "circular", "tool": "T1", "faces": [self.pocket],
                                                   "stepdown_mm": 3}])
        self.assertNotIn("plan_error", ops[0].meta)
        path = op_path(setup)
        arcs = path.moves[(path.moves["kind"] == ARC_CW) | (path.moves["kind"] == ARC_CCW)]
        self.assertTrue(np.all(arcs["kind"] == ARC_CCW))                    # climb inside a pocket
        cx, cy = ROUND["pocket"][:2]
        points = cut_points(setup)
        reach = np.hypot(points[:, 0] - cx, points[:, 1] - cy)
        # The tool's centre reaches the wall less its radius (10 - 3), never past it.
        self.assertAlmostEqual(7.0, float(reach.max()), places=4)
        self.assertAlmostEqual(-6.0, float(points[:, 2].min()), places=6)  # the pocket's floor
        self.assertEqual(2, ops[0].meta["levels"])                          # 0 -> -6 at 3: two levels
        self.assertEqual({"helix": 2}, ops[0].meta["entries"])
        self.assertEqual("pocket", ops[0].meta["kind"])
        # The finishing circles at the wall run at the edge's feed: the table's x 7 / 10.
        finish = arcs[np.isclose(np.hypot(arcs["x"] - cx, arcs["y"] - cy), 7.0)
                      & np.isclose(arcs["i"], cx) & np.isclose(arcs["j"], cy)]
        feed = ops[0].feeds.feed_mm_min
        self.assertTrue(np.allclose(finish["feed"], round(feed * 0.7)))
        self.sound(setup, ops, stock)

    def test_a_through_pocket_goes_through_mm_past_its_bottom(self):
        setup, ops, stock = plan(self.round_part, [{"op": "circular", "tool": "T1", "faces": [self.hole],
                                                   "through_mm": 0.5}])
        points = cut_points(setup)
        self.assertAlmostEqual(-13.5, float(points[:, 2].min()), places=6)
        reach = np.hypot(points[:, 0] - 20.0, points[:, 1])
        self.assertAlmostEqual(4.0, float(reach.max()), places=4)
        self.sound(setup, ops, stock)

    def test_a_region_pocket_is_its_largest_circle_and_one_on_the_part_is_a_gouge(self):
        square = [[-25, -10], [-5, -10], [-5, 10], [-25, 10]]
        setup, ops, stock = plan(self.round_part, [{"op": "circular", "tool": "T1",
                                                   "region": {"polygon": square, "bottom_z": -6}}])
        points = cut_points(setup)
        self.assertAlmostEqual(7.0, float(np.hypot(points[:, 0] + 15.0, points[:, 1]).max()), places=3)
        self.sound(setup, ops, stock)
        solid = [[5, -20], [25, -20], [25, -5], [5, -5]]
        _, ops, _ = plan(self.round_part, [{"op": "circular", "tool": "T1",
                                            "region": {"polygon": solid, "bottom_z": -4}}])
        self.assertEqual("gouge", ops[0].meta["plan_error"]["kind"])

    def test_a_boss_is_cleared_from_the_stock_edge_in_to_its_wall(self):
        setup, ops, stock = plan(self.boss_part, [{"op": "circular", "tool": "T1", "faces": [self.stud]}])
        self.assertNotIn("plan_error", ops[0].meta)
        path = op_path(setup)
        arcs = path.moves[(path.moves["kind"] == ARC_CW) | (path.moves["kind"] == ARC_CCW)]
        self.assertTrue(np.all(arcs["kind"] == ARC_CW))                     # climb round a boss
        points = cut_points(setup)
        reach = np.hypot(points[:, 0], points[:, 1])
        self.assertAlmostEqual(9.0, float(reach.min()), places=4)          # the boss's wall plus the tool's radius
        self.assertAlmostEqual(-16.0, float(points[:, 2].min()), places=6)  # its foot (Z 5 under a Z 21 stock top)
        # Out past the stock's corner, so every level comes down in air.
        self.assertGreater(float(reach.max()), math.hypot(22, 22) + 3.0)
        self.assertEqual({"air": ops[0].meta["levels"]}, ops[0].meta["entries"])
        self.assertEqual("boss", ops[0].meta["kind"])
        self.sound(setup, ops, stock)

    def test_a_boss_cleared_clear_mm_round_comes_down_on_a_helix_along_its_outer_ring(self):
        setup, ops, stock = plan(self.boss_part, [{"op": "circular", "tool": "T1", "faces": [self.stud],
                                                  "boss": True, "clear_mm": 8}])
        points = cut_points(setup)
        reach = np.hypot(points[:, 0], points[:, 1])
        self.assertAlmostEqual(11.0, float(reach.max()), places=4)          # 6 + 8 - the tool's radius
        self.assertAlmostEqual(9.0, float(reach.min()), places=4)
        self.assertEqual({"helix": ops[0].meta["levels"]}, ops[0].meta["entries"])
        self.assertAlmostEqual(8.0, ops[0].meta["cleared_mm"], places=6)
        self.sound(setup, ops, stock)

    def test_a_boss_with_the_part_beside_it_clears_up_to_the_part_and_no_further(self):
        setup, ops, stock = plan(self.crowded_part, [{"op": "circular", "tool": "T1", "faces": [self.crowded_boss]}])
        self.assertNotIn("plan_error", ops[0].meta)
        self.assertLess(ops[0].meta["cleared_mm"], CROWDED["gap"])
        self.assertGreater(ops[0].meta["cleared_mm"], CROWDED["gap"] - 0.1)
        self.sound(setup, ops, stock)
        _, ops, _ = plan(self.crowded_part, [{"op": "circular", "tool": "T1", "faces": [self.crowded_boss],
                                              "clear_mm": 12}])
        self.assertEqual("unreachable", ops[0].meta["plan_error"]["kind"])
        self.assertIn("give clear_mm 8 or less", ops[0].meta["plan_error"]["message"])
        _, ops, _ = plan(self.crowded_part, [{"op": "circular", "tool": "T7", "faces": [self.crowded_boss]}], EXTRA)
        self.assertEqual("tool_too_large", ops[0].meta["plan_error"]["kind"])

    def test_refusals(self):
        _, ops, _ = plan(self.round_part, [{"op": "circular", "tool": "T1", "faces": [self.small]}])
        self.assertEqual("tool_too_large", ops[0].meta["plan_error"]["kind"])
        _, ops, _ = plan(self.round_part, [{"op": "circular", "tool": "T1", "faces": [self.pocket], "bottom_z": -8}])
        self.assertEqual("too_deep", ops[0].meta["plan_error"]["kind"])
        cases = {
            "is a hole's wall, not a boss": (self.round_part, {"faces": [self.pocket], "boss": True}),
            "not a pocket": (self.boss_part, {"faces": [self.stud], "boss": False}),
            "a round pocket has none": (self.round_part, {"faces": [self.pocket], "boss": False, "clear_mm": 3}),
            "is a round pocket's wall (remove clear_mm)": (self.round_part, {"faces": [self.pocket], "clear_mm": 3}),
            "needs \"bottom_z\"": (self.round_part, {"region": {"polygon": [[0, 0], [5, 0], [5, 5]]}}),
            "one of them": (self.round_part, {}),
            "must be true": (self.round_part, {"faces": [self.pocket], "boss": "yes"}),
            "unknown key": (self.round_part, {"faces": [self.pocket], "depth_mm": 3}),
        }
        for expected, (part, keys) in cases.items():
            with self.subTest(expected=expected), self.assertRaises(CamJobError) as caught:
                plan(part, [{"op": "circular", "tool": "T1", **keys}])
            self.assertIn(expected, str(caught.exception))


class Trace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = class_directory(cls)
        cls.step = round_step(cls.directory)
        cls.part = read_part(cls.step)
        top = lambda lo, hi, n: lo[2] == 12 and hi[2] == 12                     # noqa: E731
        cls.outline = edges(cls.step, lambda lo, hi, n: top(lo, hi, n) and (abs(lo[0]) == 35 or abs(lo[1]) == 25)
                            and (abs(hi[0]) == 35 or abs(hi[1]) == 25) and n in (50.0, 70.0))
        cls.back = edges(cls.step, lambda lo, hi, n: top(lo, hi, n) and lo[1] == 25 and hi[1] == 25)[0]     # y = 25
        cls.right = edges(cls.step, lambda lo, hi, n: top(lo, hi, n) and lo[0] == 35 and hi[0] == 35)[0]    # x = 35
        cls.front = edges(cls.step, lambda lo, hi, n: top(lo, hi, n) and lo[1] == -25 and hi[1] == -25)[0]  # y = -25
        cls.rim = edges(cls.step, lambda lo, hi, n: top(lo, hi, n) and abs(n - 20 * math.pi) < 1e-3)[0]
        cls.floor_rim = edges(cls.step, lambda lo, hi, n: lo[2] == 7 and hi[2] == 7 and abs(n - 20 * math.pi) < 1e-3)[0]
        cls.bottom = edges(cls.step, lambda lo, hi, n: lo[2] == 0 and hi[2] == 0 and n in (50.0, 70.0))
        cls.upright = edges(cls.step, lambda lo, hi, n: lo[2] == 0 and hi[2] == 12 and n == 12.0)[0]
        assert len(cls.outline) == 4 and len(cls.bottom) == 4, (cls.outline, cls.bottom)

    def trace(self, **keys):
        return plan(self.part, [{"op": "trace", "tool": "T1", "depth_mm": 2, **keys}], EXTRA)

    def sound(self, setup, ops, stock, index=0):
        self.assertNotIn("plan_error", ops[index].meta)
        self.assertEqual([], bad_descents(setup, ops, index, stock=stock))
        self.assertEqual([], rapids_below(setup, index))

    def test_a_loop_outside_runs_the_tools_radius_off_the_edges_clockwise_level_by_level(self):
        import shapely

        setup, ops, stock = self.trace(edges=self.outline, offset="outside", stepdown_mm=1.5)
        self.sound(setup, ops, stock)
        self.assertEqual(2, ops[0].meta["levels"])                     # Z 0 down to the top (-1) less 2, at 1.5
        points = cut_points(setup, z=-3.0)
        self.assertGreater(len(points), 10)
        plate = shapely.box(-35, -25, 35, 25)
        gaps = shapely.distance(plate, shapely.points(points[:, :2]))
        self.assertTrue(np.allclose(gaps, 3.0, atol=0.01), (gaps.min(), gaps.max()))
        ring = points[:, :2]
        area = 0.5 * float(np.dot(ring[:-1, 0], ring[1:, 1]) - np.dot(ring[1:, 0], ring[:-1, 1]))
        self.assertLess(area, 0)                                       # clockwise: climb round the plate
        self.assertEqual({"ramp": 2}, ops[0].meta["entries"])
        self.assertNotIn("no_gouge_check", ops[0].meta)

    def test_a_loop_inside_and_on(self):
        setup, ops, stock = self.trace(edges=[self.rim], offset="inside")
        self.sound(setup, ops, stock)
        points = cut_points(setup, z=-3.0)
        self.assertTrue(np.allclose(np.hypot(points[:, 0] + 15.0, points[:, 1]), 7.0, atol=0.01))
        setup, ops, stock = self.trace(edges=[self.rim], offset="on", depth_mm=0.5)
        self.sound(setup, ops, stock)
        points = cut_points(setup, z=-1.5)
        self.assertTrue(np.allclose(np.hypot(points[:, 0] + 15.0, points[:, 1]), 10.0, atol=0.01))
        self.assertTrue(ops[0].meta["no_gouge_check"])

    def test_an_open_chain_left_or_right_of_its_direction_from_its_start(self):
        chain = [self.back, self.right]                  # (-35, 25) -> (35, 25) -> (35, -25)
        for start, side, y, x in (([-35, 25], "left", 28.0, 38.0), ([-35, 25], "right", 22.0, 32.0),
                                  (self.back, "left", 28.0, 38.0), ([35, -25], "left", 22.0, 32.0),
                                  (self.right, "right", 28.0, 38.0)):
            with self.subTest(start=start, side=side):
                setup, ops, stock = self.trace(edges=chain, offset=side, start=start)
                self.assertNotIn("plan_error", ops[0].meta)
                points = cut_points(setup, z=-3.0)
                along = points[points[:, 0] < 20.0]
                across = points[points[:, 1] < 10.0]
                self.assertTrue(np.allclose(along[:, 1], y, atol=1e-6), (side, along[:, 1].min(), along[:, 1].max()))
                self.assertTrue(np.allclose(across[:, 0], x, atol=1e-6))
                if x > 35:                                       # off the plate: sound, no gouge
                    self.assertEqual([], bad_descents(setup, ops, 0, stock=stock))
        # The direction stated is kept: the tool first comes down at the start's end.
        setup, ops, _ = self.trace(edges=chain, offset="left", start=[-35, 25])
        path = op_path(setup)
        first = int(np.argmax(path.moves["kind"] != 0))
        self.assertTrue(np.allclose(path.positions()[first][:2], (-35.0, 28.0), atol=1e-6))

    def test_the_start_must_be_an_end_of_the_open_chain(self):
        chain = [self.front, self.right, self.back]
        cases = {
            "is not an end of the chain": {"start": self.right},
            "is not an end of the open chain": {"start": [0, 0]},
            "say where it starts": {},
            "is not one of the edges traced": {"start": self.rim},
        }
        for expected, keys in cases.items():
            with self.subTest(expected=expected), self.assertRaises(CamJobError) as caught:
                self.trace(edges=chain, offset="right", **keys)
            self.assertIn(expected, str(caught.exception))
        setup, ops, stock = self.trace(edges=chain, offset="left", start=self.front)
        self.assertNotIn("plan_error", ops[0].meta)

    def test_offsets_must_suit_the_chain(self):
        rim = {"op": "trace", "tool": "T1", "depth_mm": 2, "edges": [self.rim]}
        cases = {
            "is a closed loop; offset it inside or outside": {**rim, "edges": self.outline, "offset": "left"},
            "with no inside": {**rim, "edges": [self.back, self.right], "offset": "inside", "start": [-35, 25]},
            "a closed loop has no start": {**rim, "offset": "inside", "start": [-25, 0]},
            "use one of on, inside, outside, left, right": {**rim, "offset": "around"},
            "needs \"depth_mm\"": {"op": "trace", "tool": "T1", "edges": [self.rim]},
            "needs \"edges\"": {"op": "trace", "tool": "T1", "depth_mm": 2},
            "must be a list of edge refs": {**rim, "edges": ["#o1.f3"]},
            "does not use stepover": {**rim, "stepover": 0.5},
        }
        for expected, operation in cases.items():
            with self.subTest(expected=expected), self.assertRaises(CamJobError) as caught:
                plan(self.part, [operation])
            self.assertIn(expected, str(caught.exception))

    def test_what_the_tool_cannot_reach_is_refused(self):
        for keys, kind in (({"edges": [self.upright]}, "unreachable"),                       # climbs
                           ({"edges": [self.floor_rim]}, "unreachable"),                     # under the pocket's wall
                           ({"edges": self.bottom, "offset": "inside"}, "unreachable"),      # under the plate
                           ({"edges": [self.rim], "offset": "inside", "tool": "T8"}, "tool_too_large")):
            with self.subTest(keys=keys):
                _, ops, _ = plan(self.part, [{"op": "trace", "tool": "T1", "depth_mm": 1, **keys}], EXTRA)
                self.assertEqual(kind, ops[0].meta["plan_error"]["kind"], ops[0].meta)
        # Inside the pocket's floor edge the tool clears the wall: reached once the pocket is cleared.
        setup, ops, stock = plan(self.part, [
            {"op": "circular", "tool": "T1", "faces": [face_of(self.step, 20.0)]},
            {"op": "trace", "tool": "T1", "depth_mm": 1, "edges": [self.floor_rim], "offset": "inside"},
        ])
        self.assertNotIn("plan_error", ops[1].meta)
        self.assertEqual([], bad_descents(setup, ops, 1, stock=stock))
        points = cut_points(setup, 1, z=-7.0)
        self.assertTrue(np.allclose(np.hypot(points[:, 0] + 15.0, points[:, 1]), 7.0, atol=0.01))


def face_of(step, diameter):
    from cadgen import cam

    return face_at(cam.features(step), surface="cylinder", diameter_mm=diameter)


class PlanEndToEnd(unittest.TestCase):
    """Both through ``cam.plan``: ready, no gouge, the G-code written."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = round_step(cls.directory)
        cls.boss = boss_step(cls.directory)
        outline = edges(cls.step, lambda lo, hi, n: lo[2] == 12 and hi[2] == 12 and n in (50.0, 70.0))
        rim = edges(cls.step, lambda lo, hi, n: lo[2] == 12 and hi[2] == 12 and abs(n - 20 * math.pi) < 1e-3)
        with quiet():
            cls.result = cam.plan(cls.step, job=job([
                {"op": "circular", "tool": "T1", "faces": [face_of(cls.step, 20.0)]},
                {"op": "circular", "tool": "T1", "faces": [face_of(cls.step, 14.0)], "through_mm": 0.3},
                {"op": "trace", "tool": "T1", "edges": rim, "offset": "inside", "depth_mm": 1},
                {"op": "trace", "tool": "T1", "edges": outline, "offset": "outside", "depth_mm": 4},
                {"op": "trace", "tool": "T3", "edges": rim, "depth_mm": 0.5},
            ]), out_dir=cls.directory)
            stud = face_at(cam.features(cls.boss), surface="cylinder", diameter_mm=12.0)
            cls.boss_result = cam.plan(cls.boss, job=job([{"op": "circular", "tool": "T9", "faces": [stud]}],
                                                         tools=tools(**EXTRA)), out_dir=cls.directory)

    def test_they_plan_ready_with_no_gouge(self):
        for result in (self.result, self.boss_result):
            with self.subTest(part=str(result.glb)):
                self.assertTrue(result.ok, result.findings)
                errors = [f for f in result.findings if f["severity"] == "error"]
                self.assertEqual([], errors)
                self.assertNotIn("gouge", {f["type"] for f in result.findings})
                self.assertTrue(result.posts)
        self.assertEqual(["circular", "circular", "trace", "trace", "trace"],
                         [op["op"] for op in self.result.operations])
        rows = {row["index"]: row for row in self.result.operations}
        self.assertEqual("Circular", rows[0]["plain"])
        self.assertEqual("Trace", rows[2]["plain"])


if __name__ == "__main__":
    unittest.main()
