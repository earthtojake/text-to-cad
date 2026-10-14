"""Profile, slot, chamfer and engrave on the bracket: loops at the tool's radius on the right side, depths reached and
not passed, tabs, leads, climb, ramps, chamfer and engraving geometry, and the teaching errors."""

from __future__ import annotations

import math
import unittest

import numpy as np
import shapely

from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, FEED, PLUNGE, RAPID
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures_milling2d import (
    BRACKET, bracket_step, class_directory, engrave_dxf, face_at, job, plan_error, tools,
)
from tests.python.support.cam_soundness import bad_descents

# The stock is the bracket plus 2 mm round and 1 mm on top; WCS zero is the stock's top centre, so the bracket's
# top is at -1 and its bottom at -13.
TOP, BOTTOM = -1.0, -13.0


class Bracket(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = bracket_step(cls.directory)
        cls.dxf = engrave_dxf(cls.directory)
        cls.features = cam.features(cls.step)
        cls.part = read_part(cls.step)
        cls.top = face_at(cls.features, surface="plane", z_mm=12.0)
        cls.slot_floor = face_at(cls.features, surface="plane", z_mm=8.0)
        cls.bore = face_at(cls.features, surface="cylinder", diameter_mm=16.0)
        cls.outline_wall = face_at(cls.features, surface="plane", x_mm=40.0)

    def plan(self, operations, **kwargs):
        parsed = parse_job(job(operations, **kwargs))
        stock = build_stock(parsed.stock, self.part)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        self.stock = stock
        return setups[0], ops

    def op_moves(self, plan, index=0):
        """(starts (N, 3), moves) of operation ``index``."""
        op = next(o for o in plan.toolpath.ops if o.index == index)
        path = plan.toolpath.slice(op.start, op.end)
        return path.positions()[:-1], path.moves

    def cutting(self, plan, index=0, step=0.25):
        op = next(o for o in plan.toolpath.ops if o.index == index)
        samples = plan.toolpath.slice(op.start, op.end).sample(0.005, max_step_mm=step)
        keep = samples.kind != RAPID
        keep[0] = False
        return samples.points[keep]

    def assert_clear_of_part(self, plan, points, radius, tolerance=0.02):
        """No cutting point comes closer to the part's material at its height than the tool's radius."""
        for z in np.unique(np.round(points[:, 2], 4)):
            group = points[np.isclose(points[:, 2], z, atol=1e-4)]
            material = plan.sections.at(float(z) + 1e-3)
            if material.is_empty:
                continue
            distance = shapely.distance(shapely.points(group[:, :2]), material)
            self.assertGreaterEqual(float(distance.min()), radius - tolerance, f"at z {z}")


class Profile(Bracket):
    def test_an_outside_profile_cuts_the_outline_through_the_bore_round_and_the_slot_to_its_floor(self):
        plan, ops = self.plan([{"op": "contour", "tool": "T1", "faces": [self.top], "stepdown_mm": 4,
                                "tabs": {"count": 4, "width_mm": 5, "height_mm": 2}}])
        points = self.cutting(plan)
        self.assert_clear_of_part(plan, points, 3.0)
        sx, sy, _ = BRACKET["size"]
        outline = shapely.box(-sx / 2, -sy / 2, sx / 2, sy / 2).exterior
        bore = shapely.Point(*BRACKET["bore"]["center"]).buffer(8.0, quad_segs=64)
        slot = BRACKET["slot"]
        slot_shape = shapely.LineString([(slot["center"][0] - 11, 0), (slot["center"][0] + 11, 0)]).buffer(4.0)
        in_slot = shapely.contains_xy(slot_shape, points[:, 0], points[:, 1])
        in_bore = shapely.contains_xy(bore, points[:, 0], points[:, 1])
        # The slot's mouth is a blind loop: cut down to its floor (z 8 -> -5), never through.
        self.assertAlmostEqual(-5.0, float(points[in_slot, 2].min()), places=6)
        # The bore and the outline go through, the outline's ring 3 mm off the walls.
        self.assertAlmostEqual(BOTTOM, float(points[in_bore, 2].min()), places=6)
        outer = points[~in_slot & ~in_bore]
        self.assertAlmostEqual(BOTTOM, float(outer[:, 2].min()), places=6)
        level = outer[np.isclose(outer[:, 2], BOTTOM)]
        self.assertTrue(np.allclose(shapely.distance(shapely.points(level[:, :2]), outline), 3.0, atol=0.02))
        radii = np.hypot(points[in_bore, 0] + 25.0, points[in_bore, 1])
        self.assertAlmostEqual(5.0, float(radii[np.isclose(points[in_bore, 2], BOTTOM)].max()), places=2)
        # Four tabs 2 mm tall on the outline's last level: four lifted runs.
        ring = outer[outer[:, 2] < -9.0 + 1e-6]
        lifted = np.isclose(ring[:, 2], BOTTOM + 2.0)
        self.assertEqual(4, int(np.sum(lifted[1:] & ~lifted[:-1])) + int(lifted[0]))
        # The Ø5 tap holes are smaller than the 6 mm tool: skipped, said, and left for the corner check.
        self.assertIn("2 loop(s)", ops[0].meta["note"])
        self.assertEqual(2, sum(1 for u in ops[0].meta["unreachable"] if abs(u["area_mm2"] - math.pi * 6.25) < 0.5))

    def test_climb_runs_clockwise_round_the_outline_and_counter_clockwise_in_the_bore(self):
        for direction, outline_cw in (("climb", True), ("conventional", False)):
            with self.subTest(direction=direction):
                plan, _ = self.plan([{"op": "contour", "tool": "T1", "faces": [self.top], "loops": "outer",
                                      "stepdown_mm": 13, "direction": direction}])
                points = self.cutting(plan, step=1.0)
                level = points[np.isclose(points[:, 2], BOTTOM)]
                area = 0.5 * float(np.sum(level[:-1, 0] * level[1:, 1] - level[1:, 0] * level[:-1, 1]))
                self.assertEqual(outline_cw, area < 0)
        plan, _ = self.plan([{"op": "contour", "tool": "T1", "faces": [self.bore], "stepdown_mm": 13}])
        points = self.cutting(plan, step=1.0)
        level = points[np.isclose(points[:, 2], BOTTOM)]
        area = 0.5 * float(np.sum(level[:-1, 0] * level[1:, 1] - level[1:, 0] * level[:-1, 1]))
        self.assertGreater(area, 0)
        self.assertTrue(np.allclose(np.hypot(level[:, 0] + 25.0, level[:, 1]), 5.0, atol=0.02))

    def test_levels_ramp_in_along_the_loop_and_a_finish_pass_takes_the_last_of_it_with_leads(self):
        plan, ops = self.plan([{"op": "contour", "tool": "T1", "faces": [self.outline_wall], "stepdown_mm": 4}])
        moves = plan.toolpath.moves
        self.assertFalse(np.any(moves["kind"] == PLUNGE))
        self.assertEqual({"ramp": 4}, ops[0].meta["entries"])
        plan, ops = self.plan([{"op": "contour", "tool": "T1", "faces": [self.top], "loops": "outer",
                                "stepdown_mm": 7, "finish_mm": 0.3, "lead_in_mm": 2, "lead_out_mm": 2}])
        points = self.cutting(plan)
        self.assert_clear_of_part(plan, points, 3.0)
        sx, sy, _ = BRACKET["size"]
        outline = shapely.box(-sx / 2, -sy / 2, sx / 2, sy / 2).exterior
        distance = shapely.distance(shapely.points(points[:, :2]), outline)
        # Roughing rides 3.3 mm off the walls, the finish pass 3.0; nothing comes closer.
        self.assertAlmostEqual(3.0, float(distance.min()), delta=0.015)   # round corners: chords within 0.01
        self.assertTrue(np.any(np.isclose(distance, 3.3, atol=0.02)))
        arcs = plan.toolpath.moves[(plan.toolpath.moves["kind"] == ARC_CW) | (plan.toolpath.moves["kind"] == ARC_CCW)]
        self.assertGreaterEqual(len(arcs), 2 * 3)          # a lead in and out on two levels and the finish pass
        self.assertEqual(0.3, ops[0].meta["finish_mm"])
        # In the slot's mouth the loop is 2 mm wide: a 2 mm lead would swing into the far wall, so it shrinks.
        plan, ops = self.plan([{"op": "contour", "tool": "T1", "faces": [self.top], "stepdown_mm": 7,
                                "lead_in_mm": 2, "lead_out_mm": 2}])
        self.assert_clear_of_part(plan, self.cutting(plan), 3.0)

    def test_a_wall_names_its_whole_loop_and_a_region_its_polygon(self):
        plan, _ = self.plan([{"op": "contour", "tool": "T1", "faces": [self.outline_wall], "stepdown_mm": 13}])
        points = self.cutting(plan, step=1.0)
        self.assertGreater(float(np.ptp(points[:, 1])), 50.0)       # all the way round, not just the +X wall
        plan, _ = self.plan([{"op": "contour", "tool": "T1", "stepdown_mm": 6, "side": "inside",
                              "region": {"polygon": [[-10, -20], [10, -20], [10, -10], [-10, -10]], "bottom_z": -3}}])
        points = self.cutting(plan, step=1.0)
        self.assertAlmostEqual(-3.0, float(points[:, 2].min()), places=6)
        self.assertLessEqual(float(points[:, 0].max()), 7.0 + 1e-6)

    def test_tabs_are_left_by_ramping_down_off_their_ends_never_dropping_into_the_material(self):
        plan, ops = self.plan([{"op": "contour", "tool": "T1", "faces": [self.top], "loops": "outer",
                                "stepdown_mm": 4, "tabs": {"count": 4, "width_mm": 5, "height_mm": 2}}])
        starts, moves = self.op_moves(plan)
        down = (moves["kind"] == FEED) & (starts[:, 2] - moves["z"] > 1e-6) & (moves["z"] < -9.0)
        across = np.hypot(moves["x"] - starts[:, 0], moves["y"] - starts[:, 1])
        drop = starts[:, 2] - moves["z"]
        # Off each tab's end (z -11 to -13) along the ring ahead at no more than the 3 degree ramp angle.
        self.assertTrue(np.any(down))
        self.assertTrue(np.all(drop[down] <= math.tan(math.radians(3.0)) * across[down] * 1.001 + 1e-9))
        self.assertEqual([], bad_descents(plan, ops, 0, stock=self.stock))
        # The tabs still stand: four lifted runs at z -11 on the last level.
        points = self.cutting(plan)
        last = points[points[:, 2] < -9.0 + 1e-6]
        lifted = np.isclose(last[:, 2], BOTTOM + 2.0)
        self.assertEqual(4, int(np.sum(lifted[1:] & ~lifted[:-1])) + int(lifted[0]))

    def test_finish_passes_split_the_finish_or_spring_at_the_final_offset(self):
        sx, sy, _ = BRACKET["size"]
        outline = shapely.box(-sx / 2, -sy / 2, sx / 2, sy / 2).exterior
        plan, ops = self.plan([{"op": "contour", "tool": "T1", "faces": [self.top], "loops": "outer",
                                "stepdown_mm": 13, "finish_mm": 0.5, "finish_passes": 2}])
        points = self.cutting(plan)
        level = points[np.isclose(points[:, 2], BOTTOM)]
        distance = np.round(shapely.distance(shapely.points(level[:, :2]), outline), 2)
        for offset in (3.5, 3.25, 3.0):          # the rough pass, then 0.25 mm and the last 0.25 mm
            self.assertTrue(np.any(np.isclose(distance, offset, atol=0.02)), offset)
        self.assertEqual(2, ops[0].meta["finish_passes"])
        lengths = []
        for extra in ({}, {"finish_passes": 1}):
            plan, ops = self.plan([{"op": "contour", "tool": "T1", "faces": [self.top], "loops": "outer",
                                    "stepdown_mm": 13, **extra}])
            starts, moves = self.op_moves(plan)
            at_bottom = (moves["kind"] == FEED) & np.isclose(moves["z"], BOTTOM) & np.isclose(starts[:, 2], BOTTOM)
            lengths.append(float(np.hypot(moves["x"] - starts[:, 0], moves["y"] - starts[:, 1])[at_bottom].sum()))
        # A spring pass goes round the same ring once more at the bottom: the outline 3 mm out, round corners.
        ring = 2 * (sx + sy) + 2 * math.pi * 3.0
        self.assertAlmostEqual(ring, lengths[1] - lengths[0], delta=0.5)
        with self.assertRaises(CamJobError) as caught:
            self.plan([{"op": "contour", "tool": "T1", "faces": [self.top], "finish_mm": 0.5, "finish_passes": 0}])
        self.assertIn("needs at least one finish pass", str(caught.exception))

    def test_a_lead_that_would_swing_into_a_fixture_is_left_out(self):
        contour = {"op": "contour", "tool": "T1", "faces": [self.top], "loops": "outer", "stepdown_mm": 13,
                   "lead_in_mm": 2, "lead_out_mm": 2}
        # Clamps all round the stock, 3.1 mm off its sides, standing over the cut: the ring clears them, a lead not.
        boxes = [{"min_mm": [-60, 31.1, 0], "max_mm": [60, 60, 14]},
                 {"min_mm": [-60, -60, 0], "max_mm": [60, -31.1, 14]},
                 {"min_mm": [43.1, -60, 0], "max_mm": [60, 60, 14]},
                 {"min_mm": [-60, -60, 0], "max_mm": [-43.1, 60, 14]}]
        setups = [{"id": "top", "orientation": "+Z", "origin": "stock-top-center", "fixture": boxes,
                   "operations": [contour]}]
        free, _ = self.plan([contour])
        self.assertTrue(np.any(np.isin(free.toolpath.moves["kind"], (ARC_CW, ARC_CCW))))
        plan, ops = self.plan([], setups=setups)
        self.assertFalse(np.any(np.isin(plan.toolpath.moves["kind"], (ARC_CW, ARC_CCW))))
        self.assertIn("2 lead(s) did not fit", ops[0].meta["note"])

    def test_teaching_errors(self):
        cases = {
            "runs on its air side": [{"op": "contour", "tool": "T1", "faces": [self.outline_wall], "side": "inside"}],
            "tabs.count must be a whole number": [{"op": "contour", "tool": "T1", "faces": [self.top],
                                                   "tabs": {"count": 0}}],
            "faces or a region, not both": [{"op": "contour", "tool": "T1", "faces": [self.top],
                                             "region": {"polygon": [[0, 0], [1, 0], [1, 1]]}}],
            "side is 'out'": [{"op": "contour", "tool": "T1", "faces": [self.top], "side": "out"}],
        }
        for expected, operations in cases.items():
            with self.subTest(expected=expected), self.assertRaises(CamJobError) as caught:
                self.plan(operations)
            self.assertIn(expected, str(caught.exception))


class Face(Bracket):
    REGION = {"polygon": [[-20, -10], [20, -10], [20, 10], [-20, 10]]}

    def test_a_region_keeps_the_tool_a_tenth_of_its_diameter_over_its_edge_and_ramps_in(self):
        for pattern in ("zigzag", "one_way"):
            with self.subTest(pattern=pattern):
                plan, ops = self.plan([{"op": "face", "tool": "T1", "region": self.REGION, "pattern": pattern}])
                points = self.cutting(plan)
                cut = points[points[:, 2] < -1e-6]
                # The 6 mm tool's centre stays 2.4 mm inside the region: it reaches 0.6 mm past its edge.
                self.assertAlmostEqual(17.6, float(np.abs(cut[:, 0]).max()), delta=0.02)
                self.assertAlmostEqual(7.6, float(np.abs(cut[:, 1]).max()), delta=0.02)
                self.assertNotIn("plunges", ops[0].meta)
                self.assertFalse(np.any(plan.toolpath.moves["kind"] == PLUNGE))
                self.assertEqual([], bad_descents(plan, ops, 0, stock=self.stock))
                if pattern == "zigzag":
                    # Down across every turn: one entry for the one level.
                    self.assertEqual({"ramp": 1}, ops[0].meta["entries"])
                else:
                    # Every row ramped onto from 0.5 mm over the material, after going back over the row before.
                    self.assertEqual({"ramp": ops[0].meta["passes"]}, ops[0].meta["entries"])
                    self.assertLessEqual(float(cut[:, 2].max()), 0.5 + 1e-6)
                    hover = points[np.isclose(points[:, 2], 0.5)]
                    self.assertGreater(len(hover), 10)

    def test_the_default_stepover_is_four_tenths_of_an_end_mill_and_seven_of_a_face_mill(self):
        _, ops = self.plan([{"op": "face", "tool": "T1"}])
        self.assertEqual(2.4, ops[0].meta["stepover_mm"])
        self.assertEqual(-1.0, ops[0].meta["faced_z"])
        # A face mill's inserts sweep most of its width: 0.7 of it.
        mill = {"id": "T8", "type": "face_mill", "diameter_mm": 20, "flute_length_mm": 6, "stickout_mm": 40}
        _, ops = self.plan([{"op": "face", "tool": "T8"}], tools=tools(T8=mill))
        self.assertIsNone(plan_error(ops))
        self.assertEqual(14.0, ops[0].meta["stepover_mm"])

    def test_facing_into_the_part_and_a_region_too_small_are_refused(self):
        _, ops = self.plan([{"op": "face", "tool": "T1", "depth_mm": 3}])
        kind, message = plan_error(ops)
        self.assertEqual("too_deep", kind)
        self.assertIn("cuts into the part", message)
        # Inside the Ø16 bore, below the part's top, the rows meet no part.
        _, ops = self.plan([{"op": "face", "tool": "T1", "depth_mm": 3,
                             "region": {"polygon": [[-30, -4], [-20, -4], [-20, 4], [-30, 4]]}}])
        self.assertIsNone(plan_error(ops))
        _, ops = self.plan([{"op": "face", "tool": "T1", "region": {"polygon": [[0, 0], [3, 0], [3, 3], [0, 3]]}}])
        self.assertEqual("tool_too_large", plan_error(ops)[0])
        _, ops = self.plan([{"op": "face", "tool": "T1"}], stock={"kind": "box", "margin_mm": [2, 2, 0]})
        self.assertEqual("empty_operation", plan_error(ops)[0])

    def test_a_fixture_standing_over_the_cut_beside_the_stock_is_never_rapided_down_onto(self):
        # A vise jaw past the stock's -X edge (part X -40, the stock -42), standing 2 mm over the part's top.
        jaw = {"min_mm": [-60.0, -40.0, -5.0], "max_mm": [-43.0, 40.0, 14.0], "name": "jaw"}
        setups = [{"id": "top", "orientation": "+Z", "origin": "stock-top-center", "fixture": jaw,
                   "operations": [{"op": "face", "tool": "T1", "pattern": "one_way"}]}]
        plan, ops = self.plan([], setups=setups)
        starts, moves = self.op_moves(plan)
        down = (starts[:, 2] - moves["z"] > 1e-6) & (moves["x"] < -43.0 + 3.0)
        # Every row starts over the jaw, so not in air: no rapid comes down there; each row is ramped into.
        self.assertFalse(np.any(down & (moves["kind"] == RAPID) & (moves["z"] < 1.0)))
        self.assertEqual({"ramp": ops[0].meta["passes"]}, ops[0].meta["entries"])


class Slot(Bracket):
    def test_a_slot_floor_is_cut_along_its_centreline_and_widened_to_its_walls(self):
        plan, ops = self.plan([{"op": "slot", "tool": "T2", "faces": [self.slot_floor], "stepdown_mm": 2}])
        points = self.cutting(plan)
        self.assert_clear_of_part(plan, points, 2.0)
        self.assertAlmostEqual(-5.0, float(points[:, 2].min()), places=6)
        slot = BRACKET["slot"]
        centre = shapely.LineString([(slot["center"][0] - 11, 0), (slot["center"][0] + 11, 0)])
        distance = shapely.distance(shapely.points(points[:, :2]), centre)
        self.assertAlmostEqual(2.0, float(distance.max()), places=2)     # the 4 mm tool's edge on the 8 mm walls
        self.assertEqual(8.0, ops[0].meta["width_mm"])
        self.assertAlmostEqual(22.0, ops[0].meta["length_mm"], places=3)
        # The centreline is cut at the tool's full width on every level: the full_slot check's fact.
        self.assertAlmostEqual(22.0 * ops[0].meta["levels"], ops[0].meta["full_slot_mm"], places=2)
        self.assertEqual({"ramp": 3}, ops[0].meta["entries"])
        self.assertFalse(np.any(plan.toolpath.moves["kind"] == PLUNGE))

    def test_a_path_slot_goes_back_and_forth_and_a_wide_tool_or_a_round_floor_is_refused(self):
        path = {"points": [[-10, -20], [10, -20], [15, -15]], "bottom_z": -3}
        plan, ops = self.plan([{"op": "slot", "tool": "T1", "path": path, "stepdown_mm": 1}])
        points = self.cutting(plan, step=0.5)
        line = shapely.LineString(path["points"])
        self.assertLess(float(shapely.distance(shapely.points(points[:, :2]), line).max()), 1e-6)
        self.assertEqual(3, ops[0].meta["levels"])
        _, ops = self.plan([{"op": "slot", "tool": "T7", "faces": [self.slot_floor]}],
                           tools=tools(T7={"id": "T7", "type": "flat", "diameter_mm": 10}))
        kind, message = plan_error(ops)
        self.assertEqual("tool_too_large", kind)
        self.assertIn("wider than the 8 mm slot", message)
        cases = {
            "not a straight slot": ([{"op": "slot", "tool": "T1", "faces": [self.top]}], {}),
            "needs one of": ([{"op": "slot", "tool": "T1"}], {}),
        }
        for expected, (operations, extra) in cases.items():
            with self.subTest(expected=expected), self.assertRaises(CamJobError) as caught:
                self.plan(operations, tools=tools(**extra))
            self.assertIn(expected, str(caught.exception))


class Chamfer(Bracket):
    def test_a_vee_breaks_every_top_edge_at_the_width_the_cone_gives(self):
        plan, ops = self.plan([{"op": "face", "tool": "T1"},
                               {"op": "chamfer", "tool": "T3", "faces": [self.top], "width_mm": 1.0}])
        ops = ops[1:]
        points = self.cutting(plan, index=1, step=0.5)
        # A 90° vee: 1 mm wide is 1 mm deep, the tip 0.2 mm lower and 0.2 mm off the edge on the air side.
        level = points[np.isclose(points[:, 2], TOP - 1.2)]
        self.assertGreater(len(level), 100)
        material = plan.sections.at(TOP - 0.5)
        distance = shapely.distance(shapely.points(level[:, :2]), material.boundary)
        self.assertTrue(np.allclose(distance, 0.2, atol=0.02))
        self.assertFalse(np.any(shapely.contains_xy(material, level[:, 0], level[:, 1])))
        self.assertEqual(1.0, ops[0].meta["depth_mm"])
        self.assertTrue(ops[0].meta["no_gouge_check"])
        # Outline, bore, two tap holes and the slot's mouth.
        self.assertEqual(5, ops[0].meta["loops"])

    def test_a_chamfer_wider_than_the_cone_is_refused(self):
        with self.assertRaises(CamJobError) as caught:
            self.plan([{"op": "chamfer", "tool": "T3", "faces": [self.top], "width_mm": 5.0}])
        self.assertIn("chamfers at most 4.8 mm wide", str(caught.exception))
        with self.assertRaises(CamJobError) as caught:
            self.plan([{"op": "chamfer", "tool": "T1", "faces": [self.top], "width_mm": 1.0}])
        self.assertIn("T1 is a flat", str(caught.exception))


    def test_a_chamfer_starts_from_a_faced_top_and_ramps_into_the_edge(self):
        _, ops = self.plan([{"op": "chamfer", "tool": "T3", "faces": [self.top], "width_mm": 0.5}])
        kind, message = plan_error(ops)
        self.assertEqual("unreachable", kind)
        self.assertIn("face the stock first", message)
        plan, ops = self.plan([{"op": "face", "tool": "T1"},
                               {"op": "chamfer", "tool": "T3", "faces": [self.top], "width_mm": 0.5}])
        self.assertIsNone(plan_error(ops, 1))
        starts, moves = self.op_moves(plan, 1)
        self.assertFalse(np.any(moves["kind"] == PLUNGE))
        self.assertNotIn("plunges", ops[1].meta)
        self.assertEqual({"ramp": ops[1].meta["loops"]}, ops[1].meta["entries"])
        self.assertEqual([], bad_descents(plan, ops, 1, stock=self.stock))
        # A stock with no top allowance needs no facing.
        _, ops = self.plan([{"op": "chamfer", "tool": "T3", "faces": [self.top], "width_mm": 0.5}],
                           stock={"kind": "box", "margin_mm": [2, 2, 0]})
        self.assertIsNone(plan_error(ops))

    def test_a_tip_that_would_touch_the_part_under_the_chamfer_is_refused(self):
        # A region's outline in the middle of the solid top: under the chamfer it is all part.
        region = {"polygon": [[-10, -20], [0, -20], [0, -12], [-10, -12]], "bottom_z": TOP}
        _, ops = self.plan([{"op": "face", "tool": "T1"},
                            {"op": "chamfer", "tool": "T3", "region": region, "width_mm": 0.5}])
        kind, message = plan_error(ops, 1)
        self.assertEqual("gouge", kind)
        self.assertIn("would touch the part", message)


class Engrave(Bracket):
    def test_a_dxf_is_engraved_at_its_depth_where_its_origin_is_placed(self):
        plan, ops = self.plan([{"op": "engrave", "tool": "T6", "dxf": str(self.dxf), "depth_mm": 0.3,
                                "origin_mm": [1, 2]}])
        points = self.cutting(plan, step=0.2)
        self.assertAlmostEqual(TOP - 0.3, float(points[:, 2].min()), places=6)
        floor = points[np.isclose(points[:, 2], TOP - 0.3)]
        circle = np.abs(np.hypot(floor[:, 0] - 21.0, floor[:, 1] - 12.0) - 4.0) < 0.02
        self.assertGreater(int(circle.sum()), 50)
        line = (np.abs(floor[:, 1] + 13.0) < 1e-6) & (floor[:, 0] >= -29.0 - 1e-6) & (floor[:, 0] <= -9.0 + 1e-6)
        self.assertGreater(int(line.sum()), 10)
        self.assertEqual(4, ops[0].meta["passes"])
        self.assertIn("mark.dxf: 1 TEXT skipped", ops[0].meta["note"])
        self.assertAlmostEqual(0.1 + 2 * 0.3 * math.tan(math.radians(15)), ops[0].meta["line_width_mm"], places=4)

    def test_a_relative_dxf_is_found_beside_the_part_and_a_missing_one_teaches(self):
        plan, _ = self.plan([{"op": "engrave", "tool": "T6", "dxf": self.dxf.name}])
        self.assertAlmostEqual(TOP - 0.2, float(self.cutting(plan)[:, 2].min()), places=6)
        with self.assertRaises(CamJobError) as caught:
            self.plan([{"op": "engrave", "tool": "T6", "dxf": "nothing.dxf"}])
        self.assertIn("no DXF at", str(caught.exception))
        with self.assertRaises(CamJobError) as caught:
            self.plan([{"op": "engrave", "tool": "T6", "faces": [self.bore]}])
        self.assertIn("not a flat face facing the tool", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
