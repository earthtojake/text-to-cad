"""Turning operations on the shaft: faced, roughed and finished to the revolved section within tolerance without
touching it, grooves plunged at their walls, the thread's passes and cycle, the drill to the bore's floor, the part
cut off at its back end; refusals that teach; one plan end to end through a lathe post."""

from __future__ import annotations

import math
import unittest
from pathlib import Path

import numpy as np
import shapely

from cadgen._internal.cam.ir import DWELL, FEED, RAPID
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from cadgen._internal.cam.stock_lathe import LatheSim
from cadgen._internal.cam.turn_profile import read_profile, sweep, tool_shape
from tests.python.support.cam_fixtures import class_directory, quiet
from tests.python.support.cam_fixtures_turning import BUSH, SECTION, bush_step, face_ref, lathe_job, shaft_step


def W(z: float) -> float:
    """The shaft's part z in the lathe's WCS (zero at the bar's front, 1 mm proud of the part's)."""
    return z - 61.0


PART = shapely.affinity.translate(shapely.Polygon(SECTION), 0.0, -61.0)
FULL = [{"op": "turn_face", "tool": "T1"}, {"op": "turn_drill", "tool": "T6", "peck_mm": 5},
        {"op": "turn_rough", "tool": "T1"}, {"op": "turn_rough", "tool": "T7", "side": "id"},
        {"op": "turn_finish", "tool": "T2", "face": True}, {"op": "turn_finish", "tool": "T7", "side": "id"},
        {"op": "turn_groove", "tool": "T3"}]
TURNED = [{"op": "turn_rough", "tool": "T1"}, {"op": "turn_finish", "tool": "T2"}]


class Turning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.folder = class_directory(cls)
        cls.step = shaft_step(cls.folder)
        cls.part = read_part(cls.step)
        cls.features = cam.features(cls.step)

    def plan(self, operations, **job):
        parsed = parse_job(lathe_job(operations, **job))
        stock = build_stock(parsed.stock, self.part)
        setups, ops, warnings = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        plan = setups[0]
        for op in ops:
            found = next(r for r in plan.toolpath.ops if r.index == op.index)
            op.start, op.end = found.start, found.end
        return plan, ops, parsed, stock

    @staticmethod
    def moves(plan, op):
        return plan.toolpath.moves[op.start:op.end]

    @staticmethod
    def cutting(plan, op):
        """(N, 2) ``(x, z)`` runs of an op's cutting moves, each run a list of points."""
        pos = plan.toolpath.positions()[:, [0, 2]]
        kinds = plan.toolpath.moves["kind"]
        runs, run = [], []
        for i in range(op.start, op.end):
            if kinds[i] == DWELL:
                continue
            if kinds[i] == RAPID:
                if len(run) > 1:
                    runs.append(np.asarray(run))
                run = []
                continue
            if not run:
                run = [pos[i]]
            run.append(pos[i + 1])
        if len(run) > 1:
            runs.append(np.asarray(run))
        return runs

    def swept(self, plan, op, tool, role, **params):
        shapes = tool_shape(tool, role, **params)
        return shapely.union_all([sweep(run, shapes) for run in self.cutting(plan, op)])

    # --- face, rough, finish -------------------------------------------------------------------------

    def test_face_takes_the_bar_to_the_front_face_from_outside_it(self):
        plan, ops, _, _ = self.plan([{"op": "turn_face", "tool": "T1"}])
        runs = self.cutting(plan, ops[0])
        self.assertEqual(1, len(runs))
        run = runs[0]
        self.assertTrue(np.allclose(run[:, 1], W(60.0)))
        self.assertGreater(run[0, 0], 20.0)
        self.assertAlmostEqual(-0.4, run[-1, 0], places=9)          # past the centre by the nose radius
        self.assertEqual(1, ops[0].meta["passes"])

    def test_rough_steps_down_and_keeps_its_allowance_off_the_part(self):
        plan, ops, parsed, _ = self.plan([{"op": "turn_rough", "tool": "T1"}])
        op = ops[0]
        runs = self.cutting(plan, op)
        levels = [run for run in runs if len(run) == 3 and abs(run[0, 0] - run[1, 0]) < 1e-9]
        radii = sorted({round(float(run[0, 0]), 6) for run in levels}, reverse=True)
        self.assertEqual(18.0, radii[0])
        self.assertTrue(all(a - b <= 2.0 + 1e-9 for a, b in zip(radii, radii[1:])), radii)
        swept = self.swept(plan, op, parsed.tool("T1"), "od")
        clearance = float(shapely.distance(swept, PART))
        self.assertGreaterEqual(clearance, 0.1 - 0.005)             # allowance x 0.2, z 0.1
        self.assertEqual([0.2, 0.1], op.meta["allowance_mm"])
        self.assertIn("2 grooves or undercuts", op.meta["note"])

    def test_finish_is_compensated_for_the_nose_and_lands_on_the_profile(self):
        plan, ops, parsed, _ = self.plan([{"op": "turn_rough", "tool": "T1"},
                                          {"op": "turn_finish", "tool": "T2", "face": True}])
        op = ops[1]
        tool = parsed.tool("T2")
        r = tool.nose_radius_mm
        points = np.vstack([shapely.get_coordinates(shapely.segmentize(shapely.LineString(run), 0.05))
                            for run in self.cutting(plan, op)])
        on = lambda x0, z0, z1: points[(np.abs(points[:, 0] - x0) < 1e-6) & (points[:, 1] <= z0) & (points[:, 1] >= z1)]  # noqa: E731
        self.assertTrue(len(on(10.0, W(59.0), W(44.0))), "the Ø20 runs at its radius")
        self.assertTrue(len(on(15.0, W(40.0), W(32.0))), "the Ø30 runs at its radius")
        self.assertTrue(np.any(np.isclose(points[:, 1], W(60.0)) & (points[:, 0] < 5.0)), "the face pass")
        # Along the front chamfer the nose (centre at the point plus (r, r)) rolls on the chamfer's line.
        chamfer = shapely.LineString([(9.0, W(60.0)), (10.0, W(59.0))])
        on_chamfer = points[(points[:, 1] < W(60.0) - 0.3) & (points[:, 1] > W(59.0) + 0.3)]
        self.assertTrue(len(on_chamfer))
        centres = shapely.points(on_chamfer + r)
        self.assertTrue(np.allclose(shapely.distance(centres, chamfer), r, atol=2e-3))
        swept = self.swept(plan, op, tool, "od")
        self.assertLess(shapely.intersection(swept, PART.buffer(-0.01)).area, 1e-9, "the finish never cuts the part")

    def test_the_whole_program_turns_the_revolved_section_within_tolerance(self):
        plan, ops, parsed, stock = self.plan(FULL)
        sim = LatheSim(stock, self.part)
        report = sim.cut(plan.toolpath, {t.id: t for t in parsed.tools}, plan.wcs)
        self.assertEqual([], report.rapid_hits)
        material = shapely.affinity.translate(sim.material, 0.0, -61.0)
        gouged = shapely.difference(PART.buffer(-0.02), material)
        self.assertLess(gouged.area, 1e-6, "no cut reaches into the part")
        left = sim.material_left(self.part, stock_to_leave_mm=0.0, tolerance_mm=0.01)
        # Only the drill's point is left, at the bore's floor (a flat bottom needs a smaller bar).
        self.assertIsNotNone(left)
        self.assertLess(left.volume_mm3, 200.0)
        big = [g for g in shapely.get_parts(shapely.difference(material, PART.buffer(0.03))) if g.area > 0.01]
        for piece in big:
            x0, z0, x1, z1 = piece.bounds
            if z1 < W(0.0) + 1e-6:
                continue                                              # the bar behind the part
            self.assertLessEqual(x1, 5.0 + 1e-6, f"left outside the bore's floor: {piece.bounds}")
            self.assertGreaterEqual(z0, W(45.0) - 1e-6)
            self.assertLessEqual(z1, W(47.5))
        removed = sum(report.removed_mm3_by_op.values())
        self.assertGreater(removed, 0.0)

    # --- grooves -------------------------------------------------------------------------------------

    def test_grooves_are_plunged_from_wall_to_wall(self):
        plan, ops, _, _ = self.plan([{"op": "turn_groove", "tool": "T3"}])
        op = ops[0]
        moves = self.moves(plan, op)
        self.assertEqual([[W(41.0), W(44.0)], [W(28.0), W(32.0)]], op.meta["grooves"])
        bottoms = moves[(moves["kind"] == FEED)]
        plunges = sorted({(round(float(m["z"]), 6), round(float(m["x"]), 6)) for m in bottoms})
        # The relief groove (3 wide) in one plunge, the 4 mm groove in two: front wall, then back wall.
        self.assertEqual([(W(28.0), 13.0), (W(29.0), 13.0), (W(41.0), 8.5)], plunges)
        self.assertEqual(3, int(np.sum(moves["kind"] == DWELL)))
        self.assertEqual(3, op.meta["passes"])

    def test_a_named_groove_and_a_blade_too_wide(self):
        plan, ops, _, _ = self.plan([{"op": "turn_groove", "tool": "T8", "faces": [face_ref(self.features, 26.0)]}])
        self.assertEqual([[W(28.0), W(32.0)]], ops[0].meta["grooves"])
        with self.assertRaisesRegex(CamJobError, "is 3 mm wide, narrower than W5's 4 mm blade"):
            self.plan([{"op": "turn_groove", "tool": "W5", "z_mm": W(42.5)}],
                      tools=[{"id": "W5", "type": "groove", "width_mm": 4}])
        with self.assertRaisesRegex(CamJobError, "there is no groove at Z-10"):
            self.plan([{"op": "turn_groove", "tool": "T3", "z_mm": -10}])

    # --- thread --------------------------------------------------------------------------------------

    def test_the_thread_cuts_to_depth_in_shrinking_passes_and_carries_its_cycle(self):
        ref = face_ref(self.features, 20.0)
        plan, ops, _, _ = self.plan([*TURNED, {"op": "turn_thread", "tool": "T4", "faces": [ref]}])
        op = ops[-1]
        cycles = [e for e in plan.toolpath.events if e.kind == "cycle" and op.start <= e.at < op.end]
        self.assertEqual(1, len(cycles))
        data = cycles[0].data
        depth = 0.6134 * 1.5
        self.assertEqual("thread", data["cycle"])
        self.assertTrue(data["external"])
        self.assertAlmostEqual(depth, data["depth_mm"], places=3)
        self.assertEqual((10.0, W(44.0), 1.5), (data["x_crest"], data["z_end"], data["pitch_mm"]))
        self.assertAlmostEqual(W(59.0) + 4.5, data["z_start"], places=6)   # three pitches of run-up
        passes = data["pass_list"]
        radii = [x for x, _ in passes]
        cuts = -np.diff([10.0] + radii[:data["passes"]])
        self.assertTrue(np.all(cuts[1:] <= cuts[:-1] + 1e-9), cuts)      # each pass takes no more than the last
        self.assertAlmostEqual(10.0 - depth, radii[-1], places=3)
        self.assertEqual(radii[-1], radii[-2])                            # the spring pass
        starts = [z for _, z in passes[:data["passes"]]]
        self.assertTrue(np.all(np.diff(starts) < 0), "flank infeed shifts each deeper pass towards the chuck")
        threading = self.moves(plan, op)
        feeds = threading[threading["kind"] == FEED]
        rpm = op.feeds.rpm
        self.assertTrue(np.allclose(feeds["feed"], 1.5 * rpm))
        self.assertTrue(np.allclose(feeds["z"], W(44.0)))
        self.assertEqual(data["passes"] + 1, len(feeds))
        # The expansion starts and ends at (x_clear, z_start).
        pos = plan.toolpath.positions()
        self.assertTrue(np.allclose(pos[cycles[0].at][[0, 2]], [data["x_clear"], data["z_start"]]))
        self.assertTrue(np.allclose(pos[data["end"]][[0, 2]], [data["x_clear"], data["z_start"]]))

    def test_a_thread_into_a_shoulder_is_refused(self):
        with self.assertRaisesRegex(CamJobError, "runs into a shoulder"):
            self.plan([{"op": "turn_thread", "tool": "T4", "z_start_mm": W(40.0), "z_end_mm": W(20.5),
                        "major_diameter_mm": 30}])

    # --- drill and part off --------------------------------------------------------------------------

    def test_the_drill_goes_to_the_bore_floor_in_pecks(self):
        plan, ops, _, _ = self.plan([{"op": "turn_face", "tool": "T1"},
                                     {"op": "turn_drill", "tool": "T6", "peck_mm": 5}])
        op = ops[1]
        moves = self.moves(plan, op)
        cutting = moves[moves["kind"] == FEED]
        self.assertTrue(np.allclose(cutting["x"], 0.0))
        self.assertAlmostEqual(W(45.0), float(cutting["z"].min()), places=6)    # the point on the floor
        self.assertEqual(3, len(cutting))                                       # 5 + 5 + 5 mm
        cycle = next(e for e in plan.toolpath.events if e.kind == "cycle" and op.start <= e.at < op.end)
        self.assertEqual(("peck", W(45.0), 5.0), (cycle.data["cycle"], cycle.data["z_bottom"], cycle.data["peck_mm"]))
        with self.assertRaisesRegex(CamJobError, r"is wider than the bore it would make \(Ø10"):
            self.plan([{"op": "turn_drill", "tool": "D12"}], tools=[{"id": "D12", "type": "drill", "diameter_mm": 12}])

    def test_part_off_at_the_back_end_slows_near_the_centre(self):
        plan, ops, parsed, _ = self.plan([{"op": "turn_partoff", "tool": "T5"}])
        op = ops[0]
        moves = self.moves(plan, op)
        cutting = moves[moves["kind"] == FEED]
        self.assertTrue(np.allclose(cutting["z"], W(0.0) - 3.0))               # the blade cuts behind the part
        self.assertAlmostEqual(-0.2, float(cutting["x"][-1]), places=9)
        self.assertAlmostEqual(cutting["feed"][0] / 2.0, cutting["feed"][-1], places=6)
        self.assertAlmostEqual(5.0, float(cutting["x"][0]), places=9)           # slows below Ø10
        with self.assertRaisesRegex(CamJobError, "no room to part off"):
            self.plan([{"op": "turn_partoff", "tool": "T5"}],
                      stock={"kind": "cylinder", "diameter_mm": 40, "length_mm": 62})

    # --- bores, feeds, checks ------------------------------------------------------------------------

    def test_a_bore_rough_needs_a_hole_and_then_bores_to_its_allowance(self):
        with self.assertRaisesRegex(CamJobError, "needs a hole on the axis to start in"):
            self.plan([{"op": "turn_rough", "tool": "T7", "side": "id"}])
        plan, ops, parsed, _ = self.plan([{"op": "turn_face", "tool": "T1"},
                                          {"op": "turn_drill", "tool": "T6"},
                                          {"op": "turn_rough", "tool": "T7", "side": "id"},
                                          {"op": "turn_finish", "tool": "T7", "side": "id"}])
        tool = parsed.tool("T7")
        rough = np.vstack(self.cutting(plan, ops[2]))
        finish = np.vstack(self.cutting(plan, ops[3]))
        inside = rough[rough[:, 1] < W(59.0)]
        self.assertAlmostEqual(4.8, float(inside[:, 0].max()), places=3)       # the bore less 0.2
        wall = finish[(finish[:, 1] < W(59.0)) & (finish[:, 1] > W(49.0))]
        self.assertTrue(np.allclose(wall[:, 0], 5.0))
        swept = self.swept(plan, ops[3], tool, "id", reach_mm=3.0)
        self.assertLess(shapely.intersection(swept, PART.buffer(-0.01)).area, 1e-9)

    def test_spindle_events_carry_constant_surface_speed_and_feed_per_rev(self):
        plan, ops, _, _ = self.plan([*TURNED, {"op": "turn_thread", "tool": "T4",
                                                "faces": [face_ref(self.features, 20.0)]}])
        spindles = [e.data for e in plan.toolpath.events if e.kind == "spindle"]
        self.assertEqual({"rpm", "dir", "feed_per_rev", "css_m_min", "max_rpm"}, set(spindles[0]))
        self.assertEqual(300.0, spindles[0]["css_m_min"])
        self.assertEqual(4000.0, spindles[0]["max_rpm"])
        self.assertNotIn("css_m_min", spindles[-1])                            # a thread at a constant rpm
        self.assertTrue(spindles[-1]["feed_per_rev"])

    def test_the_gouge_check_catches_a_face_into_the_part(self):
        from cadgen._internal.cam.checks._turning import gouges
        from cadgen._internal.cam.checks.base import CheckContext

        plan, ops, parsed, stock = self.plan([{"op": "turn_face", "tool": "T1", "z_mm": W(58.0)}])
        self.assertIn("into the part", ops[0].meta["note"])
        ctx = CheckContext(job=parsed, part=self.part, stock=stock, sim=None, sim_reports={}, setups=[plan], ops=ops,
                           tolerance_mm=parsed.tolerance_mm)
        found = gouges(ctx)
        self.assertEqual(1, len(found))
        self.assertAlmostEqual(2.0, found[0]["items"][0]["depth_mm"], delta=0.05)
        plan, ops, parsed, stock = self.plan(FULL)
        ctx = CheckContext(job=parsed, part=self.part, stock=stock, sim=None, sim_reports={}, setups=[plan], ops=ops,
                           tolerance_mm=parsed.tolerance_mm)
        self.assertEqual([], gouges(ctx))

    def test_parted_off_and_flipped_the_part_alone_goes_to_its_second_setup(self):
        parsed = parse_job(lathe_job([], setups=[
            {"id": "first", "orientation": "+Z", "operations": [
                {"op": "turn_face", "tool": "T1"}, {"op": "turn_rough", "tool": "T1"},
                {"op": "turn_partoff", "tool": "T5", "z_mm": W(-1.0)}]},
            {"id": "second", "orientation": "-Z", "operations": [{"op": "turn_face", "tool": "T1"}]}]))
        stock = build_stock(parsed.stock, self.part)
        plans, ops, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        sim = LatheSim(stock, self.part)
        tools = {t.id: t for t in parsed.tools}
        sim.cut(plans[0].toolpath, tools, plans[0].wcs)
        self.assertAlmostEqual(-1.0, sim.material.bounds[1], places=6)        # the bar behind the cut stayed
        # Flipped, the part's back end is its front: faced from the 1 mm the part-off left, down to the part.
        face = np.vstack(self.cutting(plans[1], next(r for r in plans[1].toolpath.ops if r.op == "turn_face")))
        self.assertTrue(np.allclose(face[:, 1], -14.0))                        # part z 0 in the flipped WCS
        sim.cut(plans[1].toolpath, tools, plans[1].wcs)
        self.assertAlmostEqual(0.0, sim.material.bounds[1], places=6)

    def test_a_cross_hole_is_named_once_and_left(self):
        part = read_part(shaft_step(self.folder, "cross", cross_hole=True))
        parsed = parse_job(lathe_job([{"op": "turn_face", "tool": "T1"}, {"op": "turn_rough", "tool": "T1"}]))
        stock = build_stock(parsed.stock, part)
        _, ops, _ = plan_setups(parsed, parse_operations(parsed), part, stock)
        self.assertIn("not turned about the spindle axis", ops[0].meta["note"])
        self.assertNotIn("spindle axis", ops[1].meta.get("note", ""))


class Bore(unittest.TestCase):
    """The bushing: bored in levels from a drilled hole, grooved and threaded inside."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        step = bush_step(class_directory(cls))
        cls.part = read_part(step)
        cls.features = cam.features(step)

    def test_bored_grooved_and_threaded_inside_without_touching_the_part(self):
        part_region = shapely.affinity.translate(shapely.Polygon(BUSH), 0.0, -61.0)
        bore = face_ref(self.features, 16.0, hole=True)
        parsed = parse_job(lathe_job([
            {"op": "turn_face", "tool": "T1"}, {"op": "turn_drill", "tool": "T6", "peck_mm": 8},
            {"op": "turn_rough", "tool": "T7", "side": "id"}, {"op": "turn_finish", "tool": "T7", "side": "id"},
            {"op": "turn_groove", "tool": "T8", "side": "id"},
            {"op": "turn_thread", "tool": "T4", "side": "id", "faces": [bore]}],
            stock={"kind": "cylinder", "diameter_mm": 32, "length_mm": 70}))
        stock = build_stock(parsed.stock, self.part)
        plans, ops, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        plan = plans[0]
        self.assertGreaterEqual(ops[2].meta["passes"], 3, "the bore is roughed in levels")
        self.assertEqual([[W(47.0), W(50.0)]], ops[4].meta["grooves"])
        sim = LatheSim(stock, self.part)
        report = sim.cut(plan.toolpath, {t.id: t for t in parsed.tools}, plan.wcs)
        self.assertEqual([], report.rapid_hits)
        material = shapely.affinity.translate(sim.material, 0.0, -61.0)
        self.assertLess(shapely.difference(part_region.buffer(-0.02), material).area, 1e-6)
        # The bore is open to the part everywhere a boring bar and a grooving blade can reach.
        bore_left = shapely.intersection(material, shapely.box(0.0, W(30.0), 9.5, W(60.0)))
        proud = shapely.difference(bore_left, part_region.buffer(0.03))
        self.assertLess(proud.area, 0.05, proud.bounds)
        cycle = next(e.data for e in plan.toolpath.events if e.kind == "cycle" and e.data["cycle"] == "thread")
        self.assertFalse(cycle["external"])
        self.assertAlmostEqual(8.0 + 0.5413 * 1.5, cycle["pass_list"][-1][0], places=3)
        self.assertLess(cycle["x_clear"], 8.0)


class EndToEnd(unittest.TestCase):
    def test_a_turned_shaft_plans_posts_and_writes_its_glb(self):
        from cadgen import cam
        from cadgen._internal.cam import posts

        if not posts.available("linuxcnc"):
            self.skipTest("the linuxcnc post is not in this cadgen yet")
        folder = class_directory(type(self))
        step = shaft_step(folder)
        features = cam.features(step)
        job = lathe_job([*FULL, {"op": "turn_thread", "tool": "T4", "faces": [face_ref(features, 20.0)]},
                         {"op": "turn_partoff", "tool": "T5"}])
        with quiet():
            result = cam.plan(step, job=job)
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("ready", result.verdict["status"], result.findings)
        self.assertTrue(Path(result.glb).is_file())
        text = Path(result.posts[0]["file"]).read_text(encoding="utf-8")
        self.assertIn("NOT proven on a machine", text)
        self.assertIn("G76", text)
        self.assertIn("G96", text)
        kinds = {f["check"] for f in result.findings if f["severity"] == "error"}
        self.assertEqual(set(), kinds)
        self.assertEqual(9, len(result.operations))
        self.assertTrue(math.isfinite(result.verdict["duration_s"]))
        self.assertIn("gouge", result.summary["checks_ran"])


if __name__ == "__main__":
    unittest.main()
