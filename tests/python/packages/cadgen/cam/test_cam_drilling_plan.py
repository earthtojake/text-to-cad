"""The drill operation on the drill plate: holes hit at their exact centres, depths from the hole's kind and the
tool's point, every cycle expanded the way a controller runs it, shortest order, R planes, and its teaching errors
and findings."""

from __future__ import annotations

import math
import unittest

import numpy as np

from cadgen._internal.cam.ir import DWELL, FEED, PLUNGE, RAPID
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures import class_directory, quiet
from tests.python.support.cam_fixtures_drilling import (CBORE, PLATE, counterbore_plate_step, drill_job,
                                                        drill_plate_step, hole_faces)

#: WCS z = part z - 13 (stock-top-center, 1 mm of stock over the 12 mm plate).
TOP = -1.0
BOTTOM = -13.0


def tip(diameter: float, angle: float = 118.0) -> float:
    return diameter / 2 / math.tan(math.radians(angle / 2))


class DrillPlate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        with quiet():
            cls.step = drill_plate_step(class_directory(cls))
            cls.features = cam.features(cls.step)
            cls.part = read_part(cls.step)
        cls.f5 = hole_faces(cls.features, 5.0)
        cls.f6 = hole_faces(cls.features, 6.0)
        cls.f8 = hole_faces(cls.features, 8.0)
        cls.f68 = hole_faces(cls.features, 6.8)
        cls.f4 = hole_faces(cls.features, 4.0)
        cls.side = hole_faces(cls.features, 4.0, axis="+X")

    def plan(self, operations, **job):
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
    def bottoms(path, rng):
        """(x, y, lowest z) of every plunge run's end inside the op."""
        moves = path.moves[rng.start:rng.end]
        out = {}
        for m in moves[moves["kind"] == PLUNGE]:
            key = (round(float(m["x"]), 6), round(float(m["y"]), 6))
            out[key] = min(out.get(key, math.inf), float(m["z"]))
        return out

    # --- which holes, where, how deep ------------------------------------------------------------------------

    def test_all_holes_from_the_top_are_hit_at_their_exact_centres(self):
        path, rng, op = self.one({"op": "drill", "tool": "T4", "holes": "all"})
        found = sorted(self.bottoms(path, rng))
        # The 6 mm spot drill cannot make the Ø6.8 and Ø8 holes' spots: left out, and the note says so.
        expected = sorted([*PLATE["through5"], *PLATE["blind6"]["centers"], *PLATE["pocket"]["holes"]])
        self.assertEqual(len(expected), len(found))
        for (x, y), (ex, ey) in zip(found, expected):
            self.assertAlmostEqual(ex, x, places=6)
            self.assertAlmostEqual(ey, y, places=6)
        self.assertIn("1 matching hole along another axis", op.meta["note"])
        self.assertIn("2 matching holes (Ø6.8, Ø8) left out: T4 cannot make a spot as wide as them", op.meta["note"])
        # Each moves only along Z under its R plane: no sideways feed anywhere.
        moves = path.moves[rng.start:rng.end]
        cuts = moves[(moves["kind"] == PLUNGE) | (moves["kind"] == FEED)]
        starts = path.positions()[rng.start:rng.end][(moves["kind"] == PLUNGE) | (moves["kind"] == FEED)]
        self.assertTrue(np.allclose(starts[:, :2], np.column_stack([cuts["x"], cuts["y"]])))

    def test_a_through_hole_goes_past_its_exit_by_the_breakthrough_plus_the_point(self):
        path, rng, _ = self.one({"op": "drill", "tool": "T1", "faces": self.f5[:1]})
        (z,) = self.bottoms(path, rng).values()
        self.assertAlmostEqual(BOTTOM - 1.0 - tip(5.0), z, places=6)
        path, rng, _ = self.one({"op": "drill", "tool": "T1", "faces": self.f5[:1], "breakthrough_mm": 2.5})
        (z,) = self.bottoms(path, rng).values()
        self.assertAlmostEqual(BOTTOM - 2.5 - tip(5.0), z, places=6)

    def test_a_blind_hole_with_a_drawn_point_drills_to_its_shoulder_else_to_its_tip(self):
        floor6 = TOP - PLATE["blind6"]["depth"]
        path, rng, _ = self.one({"op": "drill", "tool": "T2", "faces": self.f6})
        self.assertTrue(np.allclose(list(self.bottoms(path, rng).values()), [floor6 - tip(6.0)] * 2))
        path, rng, _ = self.one({"op": "drill", "tool": "T2", "faces": self.f6, "depth_to": "tip"})
        self.assertTrue(np.allclose(list(self.bottoms(path, rng).values()), floor6))
        floor8 = TOP - PLATE["blind8"]["depth"]
        path, rng, _ = self.one({"op": "drill", "tool": "T6", "faces": self.f8, "cycle": "bore"})
        self.assertAlmostEqual(floor8, list(self.bottoms(path, rng).values())[0], places=6)

    def test_a_tap_stops_a_pitch_short_of_a_blind_floor_and_leads_through_a_through_hole(self):
        path, rng, _ = self.one({"op": "drill", "tool": "T3", "faces": self.f6[:1]})
        self.assertAlmostEqual(TOP - 8.0 + 1.0, list(self.bottoms(path, rng).values())[0], places=6)
        path, rng, _ = self.one({"op": "drill", "tool": "T3", "faces": self.f5[:1]})
        self.assertAlmostEqual(BOTTOM - 1.0 - 3 * 1.0, list(self.bottoms(path, rng).values())[0], places=6)
        # A floating holder gives and the spindle coasts on the reverse: three pitches short.
        path, rng, _ = self.one({"op": "drill", "tool": "T3", "faces": self.f6[:1], "rigid": False})
        self.assertAlmostEqual(TOP - 8.0 + 3.0, list(self.bottoms(path, rng).values())[0], places=6)

    def test_a_spot_makes_a_cone_as_wide_as_the_hole(self):
        path, rng, op = self.one({"op": "drill", "tool": "T4", "faces": self.f5[:1] + self.f4[:1]})
        bottoms = self.bottoms(path, rng)
        self.assertAlmostEqual(TOP - 2.5, bottoms[PLATE["through5"][0]], places=6)        # 90°: depth = radius
        self.assertAlmostEqual(PLATE["pocket"]["floor_z"] - 13 - 2.0, bottoms[PLATE["pocket"]["holes"][0]],
                               places=6)
        self.assertEqual("spot", self.cycles(path, rng)[0].data["cycle"])

    def test_points_take_their_top_from_the_part_and_their_depth_from_the_job(self):
        path, rng, _ = self.one({"op": "drill", "tool": "T1", "points": [[0, -15], [12, 0]], "depth_mm": 3})
        bottoms = self.bottoms(path, rng)
        self.assertAlmostEqual(TOP - 3.0, bottoms[(0.0, -15.0)], places=6)
        self.assertAlmostEqual(PLATE["pocket"]["floor_z"] - 13 - 3.0, bottoms[(12.0, 0.0)], places=6)
        path, rng, _ = self.one({"op": "drill", "tool": "T1", "points": [[0, -15]], "depth_mm": 3, "top_z": -2,
                                 "depth_to": "shoulder"})
        self.assertAlmostEqual(-5.0 - tip(5.0), list(self.bottoms(path, rng).values())[0], places=6)

    def test_a_setup_from_the_side_drills_the_side_hole(self):
        setups = [{"id": "side", "orientation": "+X", "origin": "stock-top-center",
                   "operations": [{"op": "drill", "tool": "T7", "holes": "all"}]}]
        setups_out, ops = self.plan([], setups=setups)
        path = setups_out[0].toolpath
        rng = path.ops[0]
        (point,) = [setups_out[0].wcs.from_wcs([[k[0], k[1], z]])[0] for k, z in self.bottoms(path, rng).items()]
        side = PLATE["side"]
        self.assertAlmostEqual(side["y"], point[1], places=6)
        self.assertAlmostEqual(side["z"], point[2], places=6)
        self.assertAlmostEqual(30.0 - side["depth"], point[0], places=6)          # tip on the flat floor
        self.assertIn("10 matching holes along another axis", ops[0].meta["note"])

    def test_a_flipped_setup_drills_a_through_hole_from_its_other_end_and_refuses_a_blind_one(self):
        flipped = [{"id": "under", "orientation": "-Z", "origin": "stock-top-center",
                    "operations": [{"op": "drill", "tool": "T1", "faces": self.f5[:1]}]}]
        setups, _ = self.plan([], setups=flipped)
        path = setups[0].toolpath
        ((key, z),) = self.bottoms(path, path.ops[0]).items()
        # Flipped, the hole's exit is the plate's top face (part z 12).
        exit_z = setups[0].wcs.to_wcs([[0.0, 0.0, 12.0]])[0][2]
        self.assertAlmostEqual(exit_z - 1.0 - tip(5.0), z, places=6)
        point = setups[0].wcs.from_wcs([[key[0], key[1], z]])[0]
        self.assertTrue(np.allclose(point[:2], PLATE["through5"][0]))
        flipped[0]["operations"] = [{"op": "drill", "tool": "T2", "faces": self.f6[:1]}]
        flipped.append({"id": "top", "orientation": "+Z", "origin": "stock-top-center",
                        "operations": [{"op": "drill", "tool": "T1", "faces": self.f5[:1]}]})
        with self.assertRaises(CamJobError) as caught:
            self.plan([], setups=flipped)
        self.assertIn("drill it in setup 'top'", str(caught.exception))

    def test_points_in_solid_material_say_so_once_instead_of_gouging(self):
        _, _, op = self.one({"op": "drill", "tool": "T1", "points": [[0, -15], [-24, -14]], "depth_mm": 3})
        (found,) = op.meta["findings"]
        self.assertEqual("no_hole_in_model", found["type"])
        self.assertEqual(1, len(found["items"]))                       # (-24, -14) is one of the plate's holes
        self.assertTrue(op.meta["no_gouge_check"])

    # --- cycles --------------------------------------------------------------------------------------------

    def test_peck_comes_back_to_r_between_pecks_and_chipbreak_backs_off_a_little(self):
        path, rng, _ = self.one({"op": "drill", "tool": "T1", "faces": self.f5[:1], "cycle": "peck", "peck_mm": 4})
        (cycle,) = self.cycles(path, rng)
        r_plane, bottom = cycle.data["r_plane"], cycle.data["z_bottom"]
        self.assertEqual(("peck", 4.0), (cycle.data["cycle"], cycle.data["peck_mm"]))
        moves = path.moves[cycle.at:cycle.data["end"]]
        depths = [float(m["z"]) for m in moves if m["kind"] == PLUNGE]
        self.assertEqual(depths, sorted(depths, reverse=True))
        self.assertTrue(np.allclose(np.diff([r_plane] + depths)[:-1], -4.0))
        self.assertAlmostEqual(bottom, depths[-1], places=5)
        rapids = [float(m["z"]) for m in moves if m["kind"] == RAPID]
        self.assertEqual(len(depths) - 1, sum(1 for z in rapids if abs(z - r_plane) < 1e-9) - 1)
        path, rng, _ = self.one({"op": "drill", "tool": "T1", "faces": self.f5[:1], "cycle": "chipbreak",
                                 "peck_mm": 3, "retract_mm": 0.3})
        (cycle,) = self.cycles(path, rng)
        moves = path.moves[cycle.at:cycle.data["end"]]
        rises = []
        for k in range(1, len(moves)):
            if moves[k]["kind"] == RAPID and moves[k - 1]["kind"] == PLUNGE and moves[k]["z"] > moves[k - 1]["z"] \
                    and moves[k]["z"] < cycle.data["r_plane"] - 1e-9:
                rises.append(float(moves[k]["z"] - moves[k - 1]["z"]))
        self.assertTrue(rises and np.allclose(rises, 0.3), rises)
        self.assertEqual((3.0, 0.3), (cycle.data["peck_mm"], cycle.data["retract_mm"]))

    def test_a_deep_hole_pecks_by_default(self):
        _, _, op = self.one({"op": "drill", "tool": "T7", "faces": self.f4[:1]})       # 8 deep, 2 diameters
        self.assertEqual("drill", op.meta["cycle"])
        _, _, op = self.one({"op": "drill", "tool": "T1", "faces": self.f5[:1]})       # 12 deep, 2.4 diameters
        self.assertEqual("drill", op.meta["cycle"])
        _, _, op = self.one({"op": "drill", "tool": "T7", "faces": self.f5[:1]})       # 12 deep: 3 diameters
        self.assertEqual("peck", op.meta["cycle"])

    def test_dwell_and_bore_modes(self):
        path, rng, _ = self.one({"op": "drill", "tool": "T2", "faces": self.f6[:1], "cycle": "dwell", "dwell_s": 0.8})
        (cycle,) = self.cycles(path, rng)
        self.assertEqual(("spot", 0.8), (cycle.data["cycle"], cycle.data["dwell_s"]))        # G82
        moves = path.moves[cycle.at:cycle.data["end"]]
        self.assertEqual([0.8], [float(m["p"]) for m in moves if m["kind"] == DWELL])
        for mode, ir_cycle, out_kind in (("feed", "bore", FEED), ("dwell", "bore_dwell", FEED),
                                         ("stop", "bore_stop", RAPID), ("fine", "fine_bore", RAPID)):
            with self.subTest(mode=mode):
                path, rng, _ = self.one({"op": "drill", "tool": "T6", "faces": self.f8, "cycle": "bore",
                                         "bore_mode": mode})
                (cycle,) = self.cycles(path, rng)
                self.assertEqual(ir_cycle, cycle.data["cycle"])
                moves = path.moves[cycle.at:cycle.data["end"]]
                k = int(np.argmin(moves["z"]))
                after = [m for m in moves[k + 1:] if m["kind"] != DWELL][0]
                self.assertEqual(out_kind, int(after["kind"]))
                spindle = [e.data.get("dir") for e in path.events
                           if e.kind == "spindle" and cycle.at < e.at <= cycle.data["end"]]
                self.assertEqual(["off", "cw"] if mode in ("stop", "fine") else [], spindle)
                if mode == "fine":
                    self.assertEqual(0.1, cycle.data["shift_mm"])
                if mode == "dwell":
                    self.assertEqual(0.5, cycle.data["dwell_s"])

    def test_a_tap_feeds_at_rpm_times_pitch_and_reverses_at_the_bottom(self):
        path, rng, op = self.one({"op": "drill", "tool": "T3", "faces": self.f5[:2]})
        (cycle,) = self.cycles(path, rng)
        self.assertEqual(op.feeds.rpm * 1.0, cycle.data["feed"])
        self.assertEqual(1.0, cycle.data["pitch_mm"])
        # A tap is gouge-checked as its core (its thread form cuts the wall on purpose), not skipped.
        self.assertNotIn("no_gouge_check", op.meta)
        dirs = [e.data["dir"] for e in path.events if e.kind == "spindle" and rng.start <= e.at < rng.end]
        self.assertEqual(["cw", "ccw", "cw", "ccw", "cw"], dirs)
        moves = path.moves[cycle.at:cycle.data["end"]]
        cutting = moves[(moves["kind"] == PLUNGE) | (moves["kind"] == FEED)]
        self.assertTrue(np.allclose(cutting["feed"], op.feeds.rpm * 1.0))

    def test_a_left_hand_tap_runs_the_spindle_backwards_in(self):
        tools = [{"id": "T3", "type": "tap", "diameter_mm": 6, "pitch_mm": 1, "hand": "left"},
                 {"id": "T1", "type": "drill", "diameter_mm": 5}]
        setups, ops = self.plan([{"op": "drill", "tool": "T3", "faces": self.f5[:1]},
                                 {"op": "drill", "tool": "T1", "faces": self.f5[:1]}], tools=tools)
        path = setups[0].toolpath
        dirs = [e.data["dir"] for e in path.events if e.kind == "spindle"]
        self.assertEqual(["ccw", "cw", "ccw", "cw"], dirs)            # in, reverse out, restored; the drill cw
        (cycle,) = [e for e in path.events if e.kind == "cycle" and e.data["cycle"] == "tap"]
        self.assertTrue(cycle.data["left_hand"])
        self.assertEqual("M6x1 LH tap", ops[0].tool.plain)

    def test_holes_at_r_return_to_r_inside_a_pocket_and_to_the_initial_level_across_the_top(self):
        path, rng, op = self.one({"op": "drill", "tool": "T7", "holes": {"diameter_mm": 4}})
        (cycle,) = self.cycles(path, rng)
        self.assertEqual("r", cycle.data["retract"])
        self.assertAlmostEqual(PLATE["pocket"]["floor_z"] - 13 + 2.0, cycle.data["r_plane"])
        self.assertAlmostEqual(2.0, cycle.data["initial_z"])
        path, rng, op = self.one({"op": "drill", "tool": "T1", "faces": self.f5})
        (cycle,) = self.cycles(path, rng)
        self.assertEqual(("initial", 2.0, 2.0), (cycle.data["retract"], cycle.data["r_plane"], cycle.data["initial_z"]))
        # Pocket holes and top holes are separate cycles: different R planes.
        path, rng, op = self.one({"op": "drill", "tool": "T7", "faces": self.f4 + self.f5, "cycle": "drill"})
        groups = self.cycles(path, rng)
        self.assertGreaterEqual(len(groups), 2)
        for event in groups:
            self.assertEqual(1, len({(h[2]) for h in event.data["holes"]}))
        # Between cycles the tool climbs to the initial level before it moves across.
        for event in groups[1:]:
            before = path.positions()[event.at]
            self.assertAlmostEqual(2.0, before[2])

    def test_a_link_at_r_is_judged_by_the_box_a_dog_leg_rapid_can_take(self):
        from types import SimpleNamespace

        import shapely

        from cadgen._internal.cam.operations.drill import DrillOp

        # Material in the corner of the box between two holes: clear of the straight line, in the dog-leg's way.
        corner = shapely.box(8.0, 0.0, 10.0, 2.0)
        ctx = SimpleNamespace(sections=SimpleNamespace(at=lambda z: corner), tool=SimpleNamespace(radius=1.0))
        group = [(SimpleNamespace(x=0.0, y=0.0), None, None), (SimpleNamespace(x=10.0, y=10.0), None, None)]
        self.assertGreater(shapely.LineString([(0, 0), (10, 10)]).distance(corner), 1.5)
        self.assertEqual("initial", DrillOp._return_to(None, ctx, "auto", group, -3.0, 2.0))
        clear = SimpleNamespace(sections=SimpleNamespace(at=lambda z: shapely.box(20.0, 0.0, 22.0, 2.0)),
                                tool=ctx.tool)
        self.assertEqual("r", DrillOp._return_to(None, clear, "auto", group, -3.0, 2.0))

    def test_order_is_shorter_than_the_order_given(self):
        from cadgen._internal.cam.drilling import path_length

        faces = [self.f5[0], self.f5[3], self.f6[0], self.f5[1], self.f68[0], self.f5[2], self.f6[1]]
        lengths = {}
        for order in ("given", "shortest"):
            path, rng, op = self.one({"op": "drill", "tool": "T4", "faces": faces, "order": order,
                                      "spot_diameter_mm": 5})
            lengths[order] = path_length((0, 0), [h["at"] for h in op.meta["holes"]])
        self.assertLess(lengths["shortest"], lengths["given"] - 1.0)

    # --- findings ------------------------------------------------------------------------------------------

    def test_a_drill_off_the_hole_size_is_a_warning_and_a_tap_checks_its_thread(self):
        _, _, op = self.one({"op": "drill", "tool": "T1", "faces": self.f68})
        (found,) = op.meta["findings"]
        self.assertEqual(("drill", "warning", "hole_size"), (found["check"], found["severity"], found["type"]))
        self.assertIn("smaller than the Ø6.8", found["summary"])
        _, _, op = self.one({"op": "drill", "tool": "T1", "faces": self.f5})
        self.assertNotIn("findings", op.meta)
        _, _, op = self.one({"op": "drill", "tool": "T3", "faces": self.f68})
        (found,) = op.meta["findings"]
        self.assertEqual("tap_thread", found["type"])
        self.assertIn("M8x1.25", found["summary"])
        tools = [{"id": "T3", "type": "tap", "diameter_mm": 6, "pitch_mm": 1.25}]
        _, _, op = self.one({"op": "drill", "tool": "T3", "faces": self.f5[:1]}, tools=tools)
        self.assertIn("pitch of 1 or 0.75", op.meta["findings"][0]["summary"])

    def test_a_flat_floor_stops_the_tip_and_says_how_far_short_the_full_diameter_ends(self):
        tools = [{"id": "T1", "type": "drill", "diameter_mm": 8}]
        floor8 = TOP - PLATE["blind8"]["depth"]
        for depth_to in (None, "shoulder"):
            with self.subTest(depth_to=depth_to):
                op = {"op": "drill", "tool": "T1", "faces": self.f8}
                if depth_to:
                    op["depth_to"] = depth_to
                path, rng, planned = self.one(op, tools=tools)
                # Never past the flat floor, whatever depth_to asks.
                self.assertAlmostEqual(floor8, list(self.bottoms(path, rng).values())[0], places=6)
                (found,) = planned.meta["findings"]
                self.assertEqual(("drill", "warning", "hole_floor"), (found["check"], found["severity"], found["type"]))
                self.assertIn(f"stops {tip(8.0):.3g} mm short of the floor of 1 blind hole", found["summary"])
                self.assertIn("a flat floor", found["description"])
        # A drawn point as long as the drill's: the full diameter reaches the floor, no warning.
        _, _, planned = self.one({"op": "drill", "tool": "T2", "faces": self.f6})
        self.assertNotIn("findings", planned.meta)

    def test_a_depth_past_a_blind_holes_bottom_is_too_deep(self):
        floor6 = TOP - PLATE["blind6"]["depth"]
        _, _, op = self.one({"op": "drill", "tool": "T2", "faces": self.f6[:1], "depth_mm": 11})
        self.assertEqual("too_deep", op.meta["plan_error"]["kind"])
        self.assertIn("depth_mm: 11 mm puts the tool's tip below the bottom of", op.meta["plan_error"]["message"])
        # Down to the drawn point's tip is in the hole; the full diameter past the floor is not.
        path, rng, _ = self.one({"op": "drill", "tool": "T2", "faces": self.f6[:1], "depth_mm": 9.5})
        self.assertAlmostEqual(TOP - 9.5, list(self.bottoms(path, rng).values())[0], places=6)
        _, _, op = self.one({"op": "drill", "tool": "T2", "faces": self.f6[:1], "depth_mm": 8.5,
                             "depth_to": "shoulder"})
        self.assertEqual("too_deep", op.meta["plan_error"]["kind"])
        path, rng, _ = self.one({"op": "drill", "tool": "T2", "faces": self.f6[:1], "depth_mm": 8,
                                 "depth_to": "shoulder"})
        self.assertAlmostEqual(floor6 - tip(6.0), list(self.bottoms(path, rng).values())[0], places=6)
        _, _, op = self.one({"op": "drill", "tool": "T3", "faces": self.f6[:1], "depth_mm": 10})
        self.assertEqual("too_deep", op.meta["plan_error"]["kind"])
        # A through hole has no bottom to pass.
        _, _, op = self.one({"op": "drill", "tool": "T1", "faces": self.f5[:1], "depth_mm": 14})
        self.assertNotIn("plan_error", op.meta)

    def test_a_tool_bigger_than_its_hole_is_refused_and_all_leaves_those_holes_out(self):
        _, _, op = self.one({"op": "drill", "tool": "T2", "faces": self.f5[:1]})
        error = op.meta["plan_error"]
        self.assertEqual("tool_too_large", error["kind"])
        self.assertIn(f"{self.f5[0]} is a Ø5 hole and T2 (6 mm drill) is 1 mm bigger, so it would cut the part",
                      error["message"])
        # Within size_tolerance_mm it drills; the reamer the same.
        _, _, op = self.one({"op": "drill", "tool": "T2", "faces": self.f5[:1], "size_tolerance_mm": 1.0})
        self.assertNotIn("plan_error", op.meta)
        _, _, op = self.one({"op": "drill", "tool": "T5", "faces": self.f5[:1]})
        self.assertEqual("tool_too_large", op.meta["plan_error"]["kind"])
        # "all": the Ø5 and Ø4 holes are left out and said in the note; the Ø6, Ø6.8 and Ø8 ones are drilled.
        path, rng, op = self.one({"op": "drill", "tool": "T2", "holes": "all"})
        self.assertEqual(4, len(self.bottoms(path, rng)))
        self.assertIn("6 matching holes (Ø4, Ø5) left out: T2 is bigger than they are", op.meta["note"])
        undersize = [f for f in op.meta["findings"] if f["type"] == "hole_size"]
        self.assertTrue(undersize and all("undersize" in f["summary"] for f in undersize))
        _, _, op = self.one({"op": "drill", "tool": "T2", "holes": {"diameter_mm": 5}})
        self.assertEqual("empty_operation", op.meta["plan_error"]["kind"])
        self.assertIn("none of the 4 matching holes this setup reaches suits T2", op.meta["plan_error"]["message"])
        # A tap whose tap drill is bigger than the hole: an M8x1.25 (6.75) in a Ø5 hole; a Ø6.8 one is its own.
        tools = [{"id": "T9", "type": "tap", "diameter_mm": 8, "pitch_mm": 1.25}]
        _, _, op = self.one({"op": "drill", "tool": "T9", "faces": self.f5[:1]}, tools=tools)
        self.assertEqual("tool_too_large", op.meta["plan_error"]["kind"])
        self.assertIn("under T9's (M8x1.25 tap) Ø6.75 tap drill", op.meta["plan_error"]["message"])
        _, _, op = self.one({"op": "drill", "tool": "T9", "faces": self.f68}, tools=tools)
        self.assertNotIn("plan_error", op.meta)

    def test_a_spot_takes_its_diameter_and_refuses_one_it_cannot_make(self):
        path, rng, _ = self.one({"op": "drill", "tool": "T4", "faces": self.f5[:1], "spot_diameter_mm": 4})
        self.assertAlmostEqual(TOP - 2.0, list(self.bottoms(path, rng).values())[0], places=6)     # 90°: half of 4
        (cycle,) = self.cycles(path, rng)
        self.assertEqual(0.2, cycle.data["dwell_s"])                     # the spot's pause by default (G82)
        path, rng, _ = self.one({"op": "drill", "tool": "T4", "faces": self.f5[:1], "dwell_s": 0})
        self.assertNotIn("dwell_s", self.cycles(path, rng)[0].data)
        _, _, op = self.one({"op": "drill", "tool": "T4", "faces": self.f8})
        self.assertEqual("tool_too_small", op.meta["plan_error"]["kind"])
        self.assertIn("wants a Ø8 spot (its diameter), wider than T4 (6 mm spot drill) can make",
                      op.meta["plan_error"]["message"])
        _, _, op = self.one({"op": "drill", "tool": "T4", "faces": self.f6[:1], "depth_mm": 10})
        self.assertEqual("too_deep", op.meta["plan_error"]["kind"])
        with self.assertRaises(CamJobError) as caught:
            parse_operations(parse_job(drill_job([{"op": "drill", "tool": "T4", "holes": "all",
                                                   "spot_diameter_mm": 7}])))
        self.assertIn("a Ø7 spot is wider than T4", str(caught.exception))

    def test_a_reamer_with_a_dwell_is_g89(self):
        path, rng, _ = self.one({"op": "drill", "tool": "T5", "faces": self.f6[:1], "dwell_s": 0.3})
        (cycle,) = self.cycles(path, rng)
        self.assertEqual(("bore_dwell", 0.3), (cycle.data["cycle"], cycle.data["dwell_s"]))
        moves = path.moves[cycle.at:cycle.data["end"]]
        self.assertEqual([0.3], [float(m["p"]) for m in moves if m["kind"] == DWELL])
        k = int(np.argmin(moves["z"]))
        self.assertEqual(FEED, int([m for m in moves[k + 1:] if m["kind"] != DWELL][0]["kind"]))

    def test_a_fine_bore_shifts_off_the_wall_along_shift_xy_and_back(self):
        x, y = PLATE["blind8"]["center"]
        path, rng, _ = self.one({"op": "drill", "tool": "T6", "faces": self.f8, "cycle": "bore", "bore_mode": "fine",
                                 "shift_mm": 0.2, "shift_xy": [0, -3]})
        (cycle,) = self.cycles(path, rng)
        self.assertEqual((0.2, [0.0, -1.0]), (cycle.data["shift_mm"], cycle.data["shift_xy"]))
        moves = path.moves[cycle.at:cycle.data["end"]]
        k = int(np.argmin(moves["z"]))
        after = [(float(m["x"]), float(m["y"]), float(m["z"])) for m in moves[k + 1:]]
        bottom = float(moves[k]["z"])
        self.assertTrue(np.allclose(after[0], (x, y - 0.2, bottom)))                       # off the wall at the bottom
        self.assertTrue(np.allclose(after[1], (x, y - 0.2, cycle.data["r_plane"])))        # out, shifted
        self.assertTrue(np.allclose(after[2], (x, y, cycle.data["r_plane"])))              # back on the axis
        self.assertTrue(all(m["kind"] == RAPID for m in moves[k + 1:k + 4]))
        stop = [e.data for e in path.events if e.kind == "spindle" and cycle.at < e.at <= cycle.data["end"]]
        self.assertEqual([{"dir": "off", "orient": True}], stop[:1])
        # The default way is +X; a shift of the hole's radius or more runs the bar into the far wall.
        path, rng, _ = self.one({"op": "drill", "tool": "T6", "faces": self.f8, "cycle": "bore", "bore_mode": "fine"})
        self.assertEqual((0.1, [1.0, 0.0]), (self.cycles(path, rng)[0].data["shift_mm"],
                                             self.cycles(path, rng)[0].data["shift_xy"]))
        _, _, op = self.one({"op": "drill", "tool": "T6", "faces": self.f8, "cycle": "bore", "bore_mode": "fine",
                             "shift_mm": 4})
        self.assertEqual("gouge", op.meta["plan_error"]["kind"])

    # --- teaching errors -----------------------------------------------------------------------------------

    def test_a_hole_along_another_axis_names_the_setup_that_reaches_it(self):
        with self.assertRaises(CamJobError) as caught:
            self.plan([{"op": "drill", "tool": "T7", "faces": self.side}])
        self.assertIn("along +X", str(caught.exception))
        self.assertIn("\"orientation\": \"+X\"", str(caught.exception))
        setups = [{"id": "top", "orientation": "+Z", "origin": "stock-top-center",
                   "operations": [{"op": "drill", "tool": "T7", "faces": self.side}]},
                  {"id": "right", "orientation": "+X", "origin": "stock-top-center",
                   "operations": [{"op": "drill", "tool": "T7", "holes": "all"}]}]
        with self.assertRaises(CamJobError) as caught:
            self.plan([], setups=setups)
        self.assertIn("drill it in setup 'right'", str(caught.exception))

    def test_faces_that_are_not_holes_and_filters_that_find_none_teach(self):
        plane = next(f["ref"] for f in self.features.floors if f["kind"] == "top")
        with self.assertRaises(CamJobError) as caught:
            self.plan([{"op": "drill", "tool": "T1", "faces": [plane]}])
        self.assertIn("not a hole wall", str(caught.exception))
        with self.assertRaises(CamJobError) as caught:
            self.plan([{"op": "drill", "tool": "T1", "holes": {"diameter_mm": 3}}])
        self.assertIn("no Ø3 ±0.05 hole", str(caught.exception))
        self.assertIn("Ø6.8 along +Z", str(caught.exception))

    def test_malformed_drill_ops_are_refused_before_planning(self):
        cases = {
            "names its holes one way": {"op": "drill", "tool": "T1", "holes": "all", "points": [[0, 0]]},
            "needs \"depth_mm\"": {"op": "drill", "tool": "T1", "points": [[0, 0]]},
            "a tap cycle cuts with a tap": {"op": "drill", "tool": "T1", "holes": "all", "cycle": "tap"},
            "peck_mm is for the peck and chipbreak": {"op": "drill", "tool": "T1", "holes": "all", "cycle": "drill",
                                                      "peck_mm": 2},
            "set \"speed\" (rpm) instead": {"op": "drill", "tool": "T3", "holes": "all", "feed": 300},
            "shift_mm is for": {"op": "drill", "tool": "T6", "holes": "all", "shift_mm": 0.2},
            "shift_xy is for": {"op": "drill", "tool": "T6", "holes": "all", "bore_mode": "stop", "shift_xy": [1, 0]},
            "[0, 0] is no way": {"op": "drill", "tool": "T6", "holes": "all", "bore_mode": "fine", "shift_xy": [0, 0]},
            "spot_diameter_mm is for the spot cycle": {"op": "drill", "tool": "T1", "holes": "all",
                                                       "spot_diameter_mm": 3},
            "not both": {"op": "drill", "tool": "T4", "holes": "all", "spot_diameter_mm": 3, "depth_mm": 1},
            "a drill does not use stock_to_leave_mm": {"op": "drill", "tool": "T1", "holes": "all",
                                                       "stock_to_leave_mm": 0.2},
            "top_z is for holes given as points": {"op": "drill", "tool": "T1", "holes": "all", "top_z": 0},
            "unknown key 'pecks'": {"op": "drill", "tool": "T1", "holes": "all", "pecks": 2},
            "\"all\" or": {"op": "drill", "tool": "T1", "holes": "some"},
            "use one of drill, dwell, peck": {"op": "drill", "tool": "T1", "holes": "all", "cycle": "boring"},
        }
        for words, op in cases.items():
            with self.subTest(words=words):
                with self.assertRaises(CamJobError) as caught:
                    parse_operations(parse_job(drill_job([op])))
                self.assertIn(words, str(caught.exception))
        with self.assertRaises(CamJobError) as caught:
            parse_job(drill_job([], tools=[{"id": "T3", "type": "tap", "diameter_mm": 6, "pitch_mm": 1,
                                            "hand": "sinister"}]))
        self.assertIn("use one of right, left", str(caught.exception))

    def test_a_tap_is_rigid_only_where_the_job_or_the_machine_says_so(self):
        # (the tap's rigid, machine.rigid_tap) -> the cycle's rigid: None is the controller's own tapping cycle (M29
        # on Fanuc, which alarms where it cannot); a tap that does not say runs in a floating holder only on a machine
        # known not to tap rigidly, and the controller's own cycle with the machine unknown is an assumption.
        cases = {(None, None): None, (True, None): True, (False, None): False, (None, True): None,
                 (False, True): False, (None, False): False}
        for (rigid, machine_rigid), expected in cases.items():
            with self.subTest(rigid=rigid, machine_rigid=machine_rigid):
                op = {"op": "drill", "tool": "T3", "faces": self.f5[:1]}
                if rigid is not None:
                    op["rigid"] = rigid
                machine = {} if machine_rigid is None else {"rigid_tap": machine_rigid}
                path, rng, _ = self.one(op, machine=machine)
                (cycle,) = self.cycles(path, rng)
                self.assertEqual(expected, cycle.data.get("rigid"))
                self.assertEqual(expected is None, "rigid" not in cycle.data)
                assumed = [entry["key"] for entry in parse_job(drill_job([op], machine=machine)).assumed]
                self.assertEqual(rigid is None and machine_rigid is None, "machine.rigid_tap" in assumed)
        with self.assertRaises(CamJobError) as caught:
            parse_operations(parse_job(drill_job([{"op": "drill", "tool": "T3", "holes": "all", "rigid": True}],
                                                 machine={"rigid_tap": False})))
        self.assertIn("this machine does not tap rigidly", str(caught.exception))
        cases = {"rigid is for the tap cycle": {"op": "drill", "tool": "T1", "holes": "all", "rigid": True},
                 "rigid is true (rigid tapping": {"op": "drill", "tool": "T3", "holes": "all", "rigid": "yes"}}
        for words, op in cases.items():
            with self.subTest(words=words):
                with self.assertRaises(CamJobError) as caught:
                    parse_operations(parse_job(drill_job([op])))
                self.assertIn(words, str(caught.exception))


#: The counterbore plate's WCS: z = part z - 13 (stock-top-center, 1 mm of stock over the 12 mm plate, none under).
CB_TOOLS = [
    {"id": "T1", "type": "counterbore", "diameter_mm": 14, "pilot_diameter_mm": 10},
    # A back-boring bar: a Ø14 head 3 mm tall on a Ø4 neck.
    {"id": "T2", "type": "boring", "diameter_mm": 14, "flute_length_mm": 3, "shank_diameter_mm": 4,
     "stickout_mm": 40},
    {"id": "T3", "type": "flat", "diameter_mm": 14},
    {"id": "T4", "type": "drill", "diameter_mm": 10},
    {"id": "T5", "type": "counterbore", "diameter_mm": 14, "pilot_diameter_mm": 5},
]


class Counterbores(unittest.TestCase):
    """The ``counterbore`` cycle (G82, a pilot down the hole) and the ``back_bore`` cycle (G87: a bar's head through
    the hole, up into a counterbore on the far side) on the counterbore plate."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        with quiet():
            cls.step = counterbore_plate_step(class_directory(cls))
            cls.features = cam.features(cls.step)
            cls.part = read_part(cls.step)
        at = {(round(h["center_mm"][0], 3), round(h["center_mm"][1], 3)): h["faces"] for h in cls.features.holes}
        cls.top = at[CBORE["top"]]
        cls.back = [at[c] for c in CBORE["back"]]
        cls.blind = at[CBORE["blind"]["center"]]
        cls.plain = at[CBORE["plain"]]

    def one(self, op, tools=CB_TOOLS, **job):
        parsed = parse_job(drill_job([op], tools=tools, **job))
        stock = build_stock(parsed.stock, self.part)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        path = setups[0].toolpath
        rng = next(o for o in path.ops if o.index == 0)
        return path, rng, ops[0]

    def error(self, op, tools=CB_TOOLS):
        _, _, planned = self.one(op, tools)
        return planned.meta["plan_error"]["kind"], planned.meta["plan_error"]["message"]

    # --- counterbore ----------------------------------------------------------------------------------------

    def test_a_counterbore_stops_its_face_on_the_floor_with_its_pilot_down_the_hole_and_dwells(self):
        path, rng, op = self.one({"op": "drill", "tool": "T1", "faces": self.top[:1]})
        self.assertEqual("counterbore", op.meta["cycle"])
        self.assertTrue(op.summary.startswith("Counterbore 1 hole with T1 14 mm counterbore"))
        (cycle,) = DrillPlate.cycles(path, rng)
        # G82: the face on the floor 3 mm under the top (z -1), the 10 mm pilot (as long as it is wide) below it.
        self.assertEqual(("spot", 0.2), (cycle.data["cycle"], cycle.data["dwell_s"]))
        self.assertAlmostEqual(-1.0 - 3.0 - 10.0, cycle.data["z_bottom"], places=6)
        self.assertGreater(cycle.data["r_plane"], -1.0)
        moves = path.moves[cycle.at:cycle.data["end"]]
        self.assertEqual([PLUNGE, DWELL, RAPID], [int(m["kind"]) for m in moves])        # R is the initial level
        self.assertAlmostEqual(0.2, float(moves[1]["p"]))
        # A flat end mill its size is a counterbore with no pilot; depth_mm and dwell_s override.
        path, rng, _ = self.one({"op": "drill", "tool": "T3", "faces": self.top[:1], "cycle": "counterbore"})
        self.assertAlmostEqual(-4.0, DrillPlate.cycles(path, rng)[0].data["z_bottom"], places=6)
        path, rng, _ = self.one({"op": "drill", "tool": "T3", "faces": self.top[:1], "cycle": "counterbore",
                                 "depth_mm": 2.5, "dwell_s": 0.5})
        (cycle,) = DrillPlate.cycles(path, rng)
        self.assertAlmostEqual(-3.5, cycle.data["z_bottom"], places=6)
        self.assertEqual(0.5, cycle.data["dwell_s"])

    def test_all_counterbores_the_holes_it_suits_and_says_what_it_left(self):
        path, rng, op = self.one({"op": "drill", "tool": "T1", "holes": "all"})
        self.assertEqual([list(CBORE["top"])], [h["at"] for h in op.meta["holes"]])
        note = op.meta["note"]
        self.assertIn("1 matching hole (Ø10) left out: they have no counterbore", note)
        self.assertIn("2 matching holes (Ø10) left out: their counterbore is on the far side (back_bore them)", note)
        self.assertIn("1 matching hole (Ø10) left out: T1's pilot goes past their bottom", note)
        # A 5 mm pilot fits the blind hole's 5 mm under its counterbore's floor.
        path, rng, op = self.one({"op": "drill", "tool": "T5", "holes": "all"})
        self.assertEqual(2, op.meta["hole_count"])
        self.assertEqual({-1.0 - 3.0 - 5.0}, {round(h["bottom_z"], 6) for h in op.meta["holes"]})

    def test_a_named_hole_a_counterbore_cannot_cut_is_refused_with_its_reason(self):
        cases = [
            ({"faces": self.plain[:1]}, CB_TOOLS, "empty_operation", "with no counterbore"),
            ({"faces": self.back[0][:1]}, CB_TOOLS, "unreachable", "\"cycle\": \"back_bore\""),
            ({"faces": self.blind[:1]}, CB_TOOLS, "too_deep", "would go 5 mm past its bottom"),
            ({"faces": self.top[:1]}, [{"id": "T1", "type": "counterbore", "diameter_mm": 16,
                                        "pilot_diameter_mm": 10}], "tool_too_large", "2 mm bigger"),
            ({"faces": self.top[:1]}, [{"id": "T1", "type": "counterbore", "diameter_mm": 12,
                                        "pilot_diameter_mm": 10}], "tool_too_small", "2 mm smaller"),
            ({"faces": self.top[:1]}, [{"id": "T1", "type": "counterbore", "diameter_mm": 14,
                                        "pilot_diameter_mm": 11}], "tool_too_large", "Ø11 pilot"),
        ]
        for extra, tools, kind, words in cases:
            with self.subTest(kind=kind, words=words):
                found, message = self.error({"op": "drill", "tool": "T1", **extra}, tools)
                self.assertEqual(kind, found)
                self.assertIn(words, message)
        # Nothing on the part a 16 mm counterbore suits: an empty operation.
        found, message = self.error({"op": "drill", "tool": "T1", "holes": "all"},
                                    [{"id": "T1", "type": "counterbore", "diameter_mm": 16, "pilot_diameter_mm": 10}])
        self.assertEqual("empty_operation", found)

    # --- back bore ------------------------------------------------------------------------------------------

    def test_a_back_bore_goes_down_through_the_hole_oriented_and_shifted_and_feeds_up_into_the_counterbore(self):
        path, rng, op = self.one({"op": "drill", "tool": "T2", "faces": self.back[0][:1], "cycle": "back_bore",
                                  "shift_mm": 2.5, "shift_xy": [0, 2], "dwell_s": 0.3})
        self.assertEqual("back_bore", op.meta["cycle"])
        self.assertTrue(op.meta["no_gouge_check"])
        (cycle,) = DrillPlate.cycles(path, rng)
        data = cycle.data
        # R under the stock's bottom (z -13) by retract_mm (2) and the head (3); Z puts the head's top on the
        # shoulder, 3 mm up from the bottom face.
        self.assertEqual(("back_bore", "initial", 2.5, [0.0, 1.0], 0.3),
                         (data["cycle"], data["retract"], data["shift_mm"], data["shift_xy"], data["dwell_s"]))
        self.assertAlmostEqual(-13.0 - 2.0 - 3.0, data["r_plane"], places=6)
        self.assertAlmostEqual(-13.0 + 3.0 - 3.0, data["z_bottom"], places=6)
        x, y = CBORE["back"][0]
        r, z, top = data["r_plane"], data["z_bottom"], data["initial_z"]
        moves = path.moves[cycle.at:data["end"]]
        got = [(int(m["kind"]), round(float(m["x"]), 6), round(float(m["y"]), 6), round(float(m["z"]), 6))
               for m in moves]
        self.assertEqual([(RAPID, x, y + 2.5, top), (RAPID, x, y + 2.5, r), (RAPID, x, y, r), (FEED, x, y, z),
                          (DWELL, x, y, z), (FEED, x, y, r), (RAPID, x, y + 2.5, r), (RAPID, x, y + 2.5, top),
                          (RAPID, x, y, top)], got)
        spindle = [(e.at - cycle.at, e.data.get("dir"), e.data.get("orient", False)) for e in path.events
                   if e.kind == "spindle" and cycle.at <= e.at <= data["end"]]
        self.assertEqual([(0, "off", True), (3, "cw", False), (6, "off", True), (9, "cw", False)], spindle)

    def test_all_back_bores_the_far_counterbores_in_one_cycle_and_leaves_the_rest(self):
        path, rng, op = self.one({"op": "drill", "tool": "T2", "holes": "all", "cycle": "back_bore",
                                  "shift_mm": 2.5})
        (cycle,) = DrillPlate.cycles(path, rng)
        self.assertEqual(sorted(CBORE["back"]), sorted((h[0], h[1]) for h in cycle.data["holes"]))
        self.assertEqual(([1.0, 0.0], "initial"), (cycle.data["shift_xy"], cycle.data["retract"]))
        self.assertNotIn("dwell_s", cycle.data)
        note = op.meta["note"]
        self.assertIn("left out: they have no counterbore", note)
        self.assertIn("left out: their counterbore opens toward the tool", note)
        self.assertIn("left out: they are blind", note)
        self.assertAlmostEqual(-18.0, op.meta["bottom_z"], places=6)

    def test_a_back_bore_refuses_holes_shifts_and_bars_that_cannot_work(self):
        base = {"op": "drill", "tool": "T2", "cycle": "back_bore", "shift_mm": 2.5}
        bar = CB_TOOLS[1]
        cases = [
            ({"faces": self.plain[:1]}, None, "empty_operation", "with no counterbore"),
            ({"faces": self.blind[:1]}, None, "unreachable", "is a blind hole"),
            ({"faces": self.top[:1]}, None, "unreachable", "\"cycle\": \"counterbore\""),
            ({"faces": self.back[0][:1], "shift_mm": 2.0}, None, "tool_too_large", "at least 2.1 mm"),
            ({"faces": self.back[0][:1], "shift_mm": 5}, None, "gouge", "at least its radius"),
            ({"faces": self.back[0][:1]}, {**bar, "shank_diameter_mm": 6}, "tool_too_large", "shank_diameter_mm"),
            ({"faces": self.back[0][:1]}, {k: v for k, v in bar.items() if k != "shank_diameter_mm"},
             "tool_too_large", "at most Ø5 at this shift"),
            ({"faces": self.back[0][:1]}, {**bar, "diameter_mm": 15}, "tool_too_large", "1 mm bigger"),
            ({"faces": self.back[0][:1]}, {**bar, "diameter_mm": 13}, "tool_too_small", "1 mm smaller"),
        ]
        for extra, tool, kind, words in cases:
            with self.subTest(kind=kind, words=words):
                found, message = self.error({**base, **extra}, [tool or bar])
                self.assertEqual(kind, found)
                self.assertIn(words, message)

    def test_a_back_bore_job_plans_ready_and_posts_g87_and_its_real_errors_are_still_caught(self):
        from cadgen import cam
        from tests.python.support import gcode_reader

        faces = [hole[0] for hole in self.back]
        drill = {"op": "drill", "tool": "T4", "faces": faces}
        bore = {"op": "drill", "tool": "T2", "faces": faces, "cycle": "back_bore", "shift_mm": 2.5}
        bar = CB_TOOLS[1]

        def plan(name, operations, tool=bar):
            with quiet():
                return cam.plan(self.step, job=drill_job(operations, tools=[CB_TOOLS[3], tool], post="fanuc"),
                                out_dir=class_directory(type(self)) / name)

        # The holes drilled through, then back bored: the bar's neck passes through them, the head cuts only the
        # counterbores under the part, and the bar's 40 mm reaches down to R under the plate.
        result = plan("ready", [drill, bore])
        self.assertEqual("ready", result.verdict["status"], result.findings)
        self.assertEqual([], [f for f in result.findings if f["severity"] == "error"])
        text = gcode_reader.posted_text(result, "top")
        self.assertIn("G87 ", text)
        self.assertIn("Q2.5", text)
        # Not drilled first: the stopped bar's Ø4 neck crashes into the plate.
        result = plan("undrilled", [bore])
        self.assertEqual("fix", result.verdict["status"])
        (crash,) = [f for f in result.findings if f["severity"] == "error"]
        self.assertEqual(("rapid_into_stock", 4.0), (crash["check"], crash["items"][0]["neck_diameter_mm"]))
        # A bar too short for the holder to clear the stock's top with the head at R.
        result = plan("short", [drill, bore], {**bar, "stickout_mm": 12})
        (short,) = [f for f in result.findings if f["severity"] == "error"]
        self.assertEqual(("reach", "reach_holder"), (short["check"], short["type"]))
        # A head too big for the counterbore is still refused by the planner.
        result = plan("big", [drill, bore], {**bar, "diameter_mm": 15})
        (big,) = [f for f in result.findings if f["severity"] == "error"]
        self.assertEqual(("plan", "tool_too_large"), (big["check"], big["type"]))
        self.assertEqual("fix", result.verdict["status"])

    def test_malformed_counterbore_and_back_bore_ops_are_refused_before_planning(self):
        cases = {
            "needs \"shift_mm\"": {"op": "drill", "tool": "T2", "holes": "all", "cycle": "back_bore"},
            "a back bore names its holes by": {"op": "drill", "tool": "T2", "points": [[0, 0]], "depth_mm": 3,
                                               "cycle": "back_bore", "shift_mm": 2.5},
            "depth_mm does not apply to a back bore": {"op": "drill", "tool": "T2", "holes": "all",
                                                       "cycle": "back_bore", "shift_mm": 2.5, "depth_mm": 3},
            "returns to the initial level": {"op": "drill", "tool": "T2", "holes": "all", "cycle": "back_bore",
                                             "shift_mm": 2.5, "return_to": "r_plane"},
            "depth_to does not apply to a counterbore": {"op": "drill", "tool": "T1", "holes": "all",
                                                         "depth_to": "tip"},
            "breakthrough_mm does not apply to a back_bore": {"op": "drill", "tool": "T2", "holes": "all",
                                                              "cycle": "back_bore", "shift_mm": 2.5,
                                                              "breakthrough_mm": 1},
            "a counterbore cycle cuts with a counterbore or flat": {"op": "drill", "tool": "T4", "holes": "all",
                                                                    "cycle": "counterbore"},
            "a back_bore cycle cuts with a boring": {"op": "drill", "tool": "T1", "holes": "all",
                                                     "cycle": "back_bore", "shift_mm": 2.5},
            "shift_mm is for the bore and back_bore cycles": {"op": "drill", "tool": "T1", "holes": "all",
                                                              "shift_mm": 2.5},
        }
        for words, op in cases.items():
            with self.subTest(words=words):
                with self.assertRaises(CamJobError) as caught:
                    parse_operations(parse_job(drill_job([op], tools=CB_TOOLS)))
                self.assertIn(words, str(caught.exception))


class Ordering(unittest.TestCase):
    def test_two_opt_leaves_no_improving_swap_and_beats_nearest_neighbour(self):
        from cadgen._internal.cam.drilling import order_shortest, path_length

        rng = np.random.default_rng(7)
        points = rng.uniform(0, 100, size=(60, 2))
        order, improved = order_shortest(points, (0, 0))
        self.assertEqual(sorted(order), list(range(60)))
        nearest, _ = order_shortest(points, (0, 0), max_two_opt=0)
        self.assertTrue(improved)
        best = path_length((0, 0), points[order])
        self.assertLess(best, path_length((0, 0), points[nearest]))
        route = np.vstack([[0, 0], points[order]])
        for i in range(1, len(route) - 1):
            for j in range(i + 1, len(route)):
                old = np.linalg.norm(route[i - 1] - route[i]) + (np.linalg.norm(route[j] - route[j + 1])
                                                                 if j + 1 < len(route) else 0.0)
                new = np.linalg.norm(route[i - 1] - route[j]) + (np.linalg.norm(route[i] - route[j + 1])
                                                                 if j + 1 < len(route) else 0.0)
                self.assertGreaterEqual(new, old - 1e-6)

    def test_a_grid_of_holes_is_ordered_without_backtracking_and_a_big_one_stays_quick(self):
        import time

        from cadgen._internal.cam.drilling import order_shortest, path_length

        grid = np.array([(x, y) for x in range(0, 50, 10) for y in range(0, 40, 10)], dtype=float)
        order, _ = order_shortest(grid[::-1], (0, 0))
        self.assertAlmostEqual(190.0, path_length((0, 0), grid[::-1][order]))
        many = np.random.default_rng(3).uniform(0, 500, size=(1500, 2))
        started = time.perf_counter()
        order, _ = order_shortest(many, (0, 0), max_passes=8)
        self.assertEqual(1500, len(set(order)))
        self.assertLess(time.perf_counter() - started, 20.0)


if __name__ == "__main__":
    unittest.main()
