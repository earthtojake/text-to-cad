"""Multi-axis kinematics: rotary positions per machine, 3+2 reachability, tool axes from A/B/C, the rotary position
held on every move, the travel check's rotary limits and the posts keeping A/B/C words. No CAD: fast."""

from __future__ import annotations

import math
import re
import unittest
from types import SimpleNamespace

import numpy as np

from cadgen._internal.cam import multiaxis
from cadgen._internal.cam.ir import FEED, ToolpathBuilder
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.wcs import build_wcs, rotation_for

DIRECTIONS = {"+Z": (0, 0, 1), "-Z": (0, 0, -1), "+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0)}


def machine(kind="mill5", kinematics="ac_trunnion", limits=None):
    return SimpleNamespace(kind=kind, kinematics=kinematics if kind == "mill5" else None,
                           rotary_limits_deg=limits or {})


def job(kind="mill5", orientation="+Z", **machine_keys):
    return {"machine": {"kind": kind, "post": "linuxcnc", **machine_keys}, "material": "aluminum-6061",
            "stock": {"kind": "box", "margin_mm": 1},
            "tools": [{"id": "T1", "type": "flat", "diameter_mm": 6}],
            "setups": [{"id": "s", "orientation": orientation, "operations": [{"op": "face", "tool": "T1"}]}]}


class RotaryPositions(unittest.TestCase):
    def test_every_fixed_orientation_a_rotary_axis_reaches_points_the_tool_that_way(self):
        reached = {}
        for kind, kinematics in (("mill4", None), ("mill5", "ac_trunnion"), ("mill5", "bc_head")):
            m = machine(kind, kinematics)
            for name, direction in DIRECTIONS.items():
                position = multiaxis.orientation_rotary(name, m)
                reached[(kind, kinematics, name)] = position is not None
                if position is None:
                    continue
                self.assertEqual({f"{a}_deg" for a in multiaxis.rotary_axes(m)}, set(position))
                tool = np.asarray(rotation_for(position))[2]
                np.testing.assert_allclose(direction, tool, atol=1e-9, err_msg=f"{kind} {kinematics} {name}")
        # A 4th axis turns about X, so the part's X can never face the tool: those stay a re-fixture by hand.
        self.assertFalse(reached[("mill4", None, "+X")])
        self.assertFalse(reached[("mill4", None, "-X")])
        self.assertTrue(all(v for (kind, _, _), v in reached.items() if kind == "mill5"))

    def test_rotary_limits_pick_the_reachable_solution_or_none(self):
        trunnion = machine(limits={"a": (-30.0, 110.0)})
        self.assertEqual({"a_deg": 90.0, "c_deg": 180.0}, multiaxis.orientation_rotary("-Y", trunnion))
        self.assertIsNone(multiaxis.orientation_rotary("-Z", trunnion))          # A 180 is beyond the trunnion

    def test_a_3_plus_2_setup_names_every_axis_and_its_wcs_is_the_turned_part(self):
        parsed = parse_job(job(orientation={"a_deg": 30}))
        setup = parsed.setups[0]
        self.assertEqual({"a_deg": 30.0, "c_deg": 0.0}, setup.orientation)
        corners = np.array([[x, y, z] for x in (-5, 5) for y in (-5, 5) for z in (0, 10)], float)
        wcs = build_wcs(setup, stock_points=corners, part_points=corners, machine=parsed.machine)
        self.assertEqual((("a", 30.0), ("c", 0.0)), wcs.rotary_deg)
        np.testing.assert_allclose((0, math.sin(math.radians(30)), math.cos(math.radians(30))), wcs.tool_axis)
        # A fixed orientation on a mill4 becomes its A position.
        parsed = parse_job(job(kind="mill4", orientation="-Y"))
        wcs = build_wcs(parsed.setups[0], stock_points=corners, part_points=corners, machine=parsed.machine)
        self.assertEqual((("a", -90.0),), wcs.rotary_deg)
        np.testing.assert_allclose((0, -1, 0), wcs.tool_axis, atol=1e-12)

    def test_unreachable_3_plus_2_orientations_are_teaching_errors(self):
        cases = {
            "this mill4 turns only A (about X), so c_deg cannot be reached; use a_deg, or a mill5":
                job(kind="mill4", orientation={"a_deg": 10, "c_deg": 30}),
            "turns only B and C, so a_deg cannot be reached": job(orientation={"a_deg": 10}, kinematics="bc_head"),
            "a_deg 130 is outside the machine's A range -30..110 (machine.rotary_limits_deg)":
                job(orientation={"a_deg": 130}, rotary_limits_deg={"a": [-30, 110]}),
            "the same tilt is a_deg -20 with c_deg 180, which it can reach":
                job(orientation={"a_deg": 20}, rotary_limits_deg={"a": [-30, 10]}),
            "machine.rotary_limits_deg.a must be [low, high]": job(rotary_limits_deg={"a": [10, -10]}),
        }
        for message, raw in cases.items():
            with self.subTest(message=message), self.assertRaises(CamJobError) as caught:
                parse_job(raw)
            self.assertIn(message, str(caught.exception))


class ToolAxes(unittest.TestCase):
    def test_solved_positions_reproduce_their_directions_and_stay_continuous(self):
        angles = np.radians(np.linspace(0, 720, 145))
        around_x = np.column_stack([np.zeros_like(angles), np.sin(angles), np.cos(angles)])
        for m in (machine("mill4"), machine()):
            abc = multiaxis.solve_abc(around_x, m)
            self.assertFalse(np.isnan(abc).any())
            np.testing.assert_allclose(around_x, multiaxis.unit_axes(abc), atol=1e-9)
            self.assertLess(np.abs(np.diff(abc, axis=0)).max(), 5.1)     # no jump: unwound turn by turn
        self.assertAlmostEqual(720.0, multiaxis.solve_abc(around_x, machine("mill4"))[-1, 0], places=6)
        cone = np.column_stack([0.3 * np.cos(angles), 0.3 * np.sin(angles), np.full_like(angles, math.sqrt(0.91))])
        abc = multiaxis.solve_abc(cone, machine(kinematics="bc_head"))
        np.testing.assert_allclose(cone, multiaxis.unit_axes(abc), atol=1e-9)
        # A 4th axis cannot lean the tool along X; limits leave rows unreachable too.
        self.assertTrue(np.isnan(multiaxis.solve_abc([[0.5, 0, math.sqrt(0.75)]], machine("mill4"))).all())
        limited = machine(limits={"a": (-10.0, 10.0)})
        self.assertTrue(np.isnan(multiaxis.solve_abc([[0, 1, 0]], limited)).all())

    def test_tool_axes_in_a_tilted_setup_are_relative_to_its_rotary_position(self):
        m = machine()
        setup = SimpleNamespace(id="s", orientation={"a_deg": 30.0, "c_deg": 45.0}, origin="stock-top-center")
        corners = np.array([[x, y, z] for x in (-5, 5) for y in (-5, 5) for z in (0, 10)], float)
        wcs = build_wcs(setup, stock_points=corners, part_points=corners, machine=m)
        at_setup = multiaxis.tool_axes([[30.0, 0.0, 45.0]], wcs)[0]
        np.testing.assert_allclose(wcs.tool_axis, at_setup, atol=1e-12)
        other = multiaxis.tool_axes([[10.0, 0.0, 0.0]], wcs)[0]
        np.testing.assert_allclose(multiaxis.unit_axes([[10.0, 0.0, 0.0]])[0], other, atol=1e-12)
        flat = SimpleNamespace(id="f", orientation="+Z", origin="stock-top-center")
        fixed = build_wcs(flat, stock_points=corners, part_points=corners)
        np.testing.assert_allclose([[0, 0, 1]], multiaxis.tool_axes([[50.0, 0, 0]], fixed, rotary=False))


class HeldRotary(unittest.TestCase):
    def wcs(self, orientation, kind="mill5"):
        setup = SimpleNamespace(id="s", orientation=orientation, origin="stock-top-center")
        corners = np.array([[x, y, z] for x in (-5, 5) for y in (-5, 5) for z in (0, 10)], float)
        return build_wcs(setup, stock_points=corners, part_points=corners, machine=machine(kind))

    def test_a_plain_operation_in_a_3_plus_2_setup_carries_the_setup_position_on_every_move(self):
        wcs = self.wcs({"a_deg": 30.0, "c_deg": 90.0})
        b = ToolpathBuilder((0, 0, 5))
        b.rapid(1, 1)
        b.feed(z=-2, f=100)
        tail = ToolpathBuilder((1, 1, -2))
        tail.rapid(z=5)
        joined = multiaxis.hold_rotary(b.build(), tail.build(), wcs)
        self.assertEqual(("a", "c"), joined.rotary)
        self.assertTrue((joined.moves["a"] == 30.0).all() and (joined.moves["c"] == 90.0).all())

    def test_a_continuous_operation_keeps_its_own_positions_and_the_tail_holds_the_last(self):
        wcs = self.wcs("+Z", kind="mill4")
        moves = multiaxis.MoveList((0, 0, 5), (0, 0, 0), ("a",))
        moves.go(FEED, (0, 1, 4), (20.0, 0, 0), f=100)
        moves.go(FEED, (0, 2, 3), (40.0, 0, 0), f=100)
        tail = ToolpathBuilder((0, 2, 3))
        tail.rapid(z=5)
        joined = multiaxis.hold_rotary(moves.build(), tail.build(), wcs)
        self.assertEqual([20.0, 40.0, 40.0], list(joined.moves["a"]))
        self.assertEqual(("a",), joined.rotary)

    def test_a_setup_without_rotary_axes_passes_through(self):
        setup = SimpleNamespace(id="s", orientation="+Z", origin="stock-top-center")
        corners = np.array([[x, y, z] for x in (-5, 5) for y in (-5, 5) for z in (0, 10)], float)
        wcs = build_wcs(setup, stock_points=corners, part_points=corners)
        b = ToolpathBuilder((0, 0, 5))
        b.feed(z=1, f=100)
        joined = multiaxis.hold_rotary(b.build(), ToolpathBuilder((0, 0, 1)).build(), wcs)
        self.assertEqual((), joined.rotary)

    def test_machine_positions_turn_the_tip_about_the_pivot(self):
        wcs = self.wcs("+Z", kind="mill4")
        moves = multiaxis.MoveList((0, 0, 5), (0, 0, 0), ("a",))
        moves.go(FEED, (3, 0, -2), (0, 0, 0), f=100)
        moves.go(FEED, (3, 0, -2), (90.0, 0, 0), f=100)
        pivot = wcs.from_wcs([[0, 0, -7]])[0]          # the A axis 7 mm under the WCS zero
        out = multiaxis.machine_positions(moves.build(), wcs, pivot)
        np.testing.assert_allclose([3, 0, -2], out[0], atol=1e-9)
        # Turned 90° about X: the tip 5 mm over the axis swings to 5 mm along -Y (R(90°) takes +Z to -Y).
        np.testing.assert_allclose([3, -5, -7], out[1], atol=1e-9)


class RotaryTravelAndPosts(unittest.TestCase):
    def test_a_move_beyond_the_rotary_limits_is_a_travel_error(self):
        from cadgen._internal.cam.checks import travel

        moves = multiaxis.MoveList((0, 0, 5), (0, 0, 0), ("a", "c"))
        moves.go(FEED, (0, 0, 4), (20.0, 0, 0), f=100)
        moves.go(FEED, (0, 0, 3), (130.0, 0, 0), f=100)
        path = moves.build()
        ctx = SimpleNamespace(job=SimpleNamespace(machine=SimpleNamespace(travel_mm=None, kind="mill5",
                                                                          rotary_limits_deg={"a": (-30.0, 110.0)})),
                              setups=[SimpleNamespace(toolpath=path, setup=SimpleNamespace(id="s"))],
                              tolerance_mm=0.01)
        found = travel.run(ctx)
        self.assertEqual(1, len(found))
        self.assertEqual("rotary_travel", found[0]["type"])
        self.assertEqual(130.0, found[0]["items"][0]["value_deg"])

    def test_feed_moves_that_turn_a_rotary_axis_post_every_a_word(self):
        from cadgen._internal.cam.posts import get_post
        from cadgen._internal.cam.posts.base import Program
        from cadgen._internal.cam.tools import parse_tool

        # Points on a circle at one height (an arc fitter's favourite) while A turns.
        moves = multiaxis.MoveList((10, 0, 0), (0, 0, 0), ("a",))
        for k in range(1, 25):
            t = math.radians(k * 5)
            moves.go(FEED, (10 * math.cos(t), 10 * math.sin(t), 0), (k * 2.0, 0, 0), f=500)
        path = moves.build()
        tool = parse_tool({"id": "T1", "type": "ball", "diameter_mm": 4}, 0)
        parsed = parse_job(job(kind="mill4"))
        setup = parsed.setups[0]
        wcs = SimpleNamespace(rotary_deg=(("a", 0.0),), setup_id="s")
        program = Program(setup=setup, wcs=wcs, toolpath=path, tools={"T1": tool}, machine=parsed.machine,
                          version="test")
        text = get_post("linuxcnc", "mill4").render(program)
        a_words = [line for line in text.splitlines() if line.startswith(("G1", "X", "Y")) and " A" in line]
        self.assertGreaterEqual(len(a_words), 24, text)
        self.assertIsNone(re.search(r"\bG0?[23]\b", text), text)


if __name__ == "__main__":
    unittest.main()
