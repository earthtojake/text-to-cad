"""The CAM job's closed vocabulary: every teaching error, the tool profiles, the feeds rules, the WCS."""

from __future__ import annotations

import copy
import math
import unittest

from cadgen._internal.cam.feeds import for_cut, for_op
from cadgen._internal.cam.job import CamJobError, parse_job
from cadgen._internal.cam.wcs import build_wcs, rotation_for

BASE = {
    "machine": {"kind": "mill", "post": "grbl", "max_rpm": 24000},
    "material": "aluminum-6061",
    "stock": {"kind": "box", "margin_mm": [2, 2, 1]},
    "tools": [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 18}],
    "setups": [{"id": "top", "operations": [{"op": "face", "tool": "T1"}]}],
}


def job(**changes):
    out = copy.deepcopy(BASE)
    for path, value in changes.items():
        target = out
        keys = path.split("__")
        for key in keys[:-1]:
            target = target[int(key)] if key.isdigit() else target[key]
        last = keys[-1]
        if value is DELETE:
            del target[int(last) if last.isdigit() else last]
        else:
            target[int(last) if last.isdigit() else last] = value
    return out


DELETE = object()


class JobParsing(unittest.TestCase):
    def test_a_good_job_parses_with_its_defaults(self):
        parsed = parse_job(BASE)
        self.assertEqual("grbl", parsed.machine.post)
        self.assertEqual((2.0, 2.0, 2.0, 2.0, 0.0, 1.0), parsed.stock.margin_mm)
        tool = parsed.tool("T1")
        self.assertEqual(1, tool.number)
        self.assertEqual("6 mm flat", tool.plain)
        self.assertEqual("Top", parsed.setups[0].plain)
        self.assertEqual("G54", parsed.setups[0].wcs)
        self.assertEqual(0.01, parsed.tolerance_mm)

    def test_inline_json_and_a_post_left_out_is_assumed_never_silent(self):
        text = ('{"machine": {"kind": "lathe"}, "material": "brass", "stock": {"kind": "cylinder", '
                '"diameter_mm": 20, "length_mm": 50}, "tools": [{"id": "T1", "type": "turn"}], '
                '"setups": [{"operations": [{"op": "turn_face", "tool": "T1"}]}]}')
        parsed = parse_job(text)
        self.assertEqual("fanuc", parsed.machine.post)
        (post,) = [entry for entry in parsed.assumed if entry["key"] == "machine.post"]
        self.assertEqual("fanuc", post["value"])
        self.assertIn("check your controller reads it", post["why"])
        parsed = parse_job(text.replace('"kind": "lathe"', '"kind": "lathe", "post": "linuxcnc"'))
        self.assertEqual("linuxcnc", parsed.machine.post)
        self.assertNotIn("machine.post", [entry["key"] for entry in parsed.assumed])
        self.assertEqual("setup1", parsed.setups[0].id)

    def test_every_teaching_error_names_what_to_change(self):
        cases = {
            "not valid JSON": "{nope",
            "unknown key 'machin'": job(machin={}),
            "needs \"stock\"": job(stock=DELETE),
            "machine.kind is 'mil' (did you mean 'mill'?); use one of mill, mill4": job(machine__kind="mil"),
            "unknown post 'grbI'": job(machine__post="grbI"),
            "the marlin post does not serve a mill": job(machine__post="marlin"),
            "material is 'unobtainium'; use one of aluminum-6061": job(material="unobtainium"),
            "material needs chipload_mm": job(material={"sfm": 800}),
            "stock.kind is 'blob'": job(stock={"kind": "blob"}),
            "give margin_mm or size_mm, not both": job(stock={"kind": "box", "margin_mm": 1, "size_mm": [1, 2, 3]}),
            "tools[0].type is 'endmill'": job(tools__0__type="endmill"),
            "unknown key 'corner_radius_mm'": job(tools__0__corner_radius_mm=1),
            "needs \"corner_radius_mm\"": job(tools__0__type="bull"),
            "two tools are called 'T1'": job(tools=[BASE["tools"][0], BASE["tools"][0]]),
            "stickout_mm (10) is shorter than flute_length_mm": job(tools__0__stickout_mm=10),
            "setups[0].orientation is '+Q'": job(setups__0__orientation="+Q"),
            "tilts the part (3+2), which needs a mill4 or mill5": job(setups__0__orientation={"a_deg": 30}),
            "setups[0].origin is 'middle'": job(setups__0__origin="middle"),
            "unknown operation 'pockt' (did you mean 'pocket'?)": job(setups__0__operations__0__op="pockt"),
            "a mill cannot rough turn": job(setups__0__operations__0__op="turn_rough"),
            "tool is 'T9', which is not in tools": job(setups__0__operations__0__tool="T9"),
            "faces must be a list of face refs": job(setups__0__operations__0__faces=["f12"]),
            "give stepover (a fraction of the tool diameter) or stepover_mm": job(
                setups__0__operations__0__stepover=0.4, setups__0__operations__0__stepover_mm=2),
            "stepover must be at most 1": job(setups__0__operations__0__stepover=3),
            "setups[0].operations[0].coolant is 'lots'": job(setups__0__operations__0__coolant="lots"),
            "max_mm must be more than min_mm": job(setups__0__fixture={"min_mm": [0, 0, 0], "max_mm": [1, 0, 1]}),
            "fixture[0].type is 'vice' (did you mean 'vise'?)": job(setups__0__fixture={"type": "vice"}),
            "an edge: a setup looks down a flat face's outward normal": job(setups__0__orientation="#o1.e2"),
            "setup ids must be different": job(setups=[BASE["setups"][0], BASE["setups"][0]]),
            "both post as T1": job(tools=[BASE["tools"][0], {"id": "T1b", "type": "drill", "diameter_mm": 5, "number": 1}]),
            "a plan needs a job": None,
        }
        for expected, raw in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaises(CamJobError) as caught:
                    parse_job(raw)
                self.assertIn(expected, str(caught.exception))


class Tools(unittest.TestCase):
    def tool(self, **raw):
        return parse_job(job(tools=[{"id": "T1", **raw}])).tool("T1")

    def test_profiles_against_their_geometry(self):
        ball = self.tool(type="ball", diameter_mm=6)
        self.assertAlmostEqual(0.0, ball.height_at(0.0))
        self.assertAlmostEqual(3.0, ball.height_at(3.0))
        self.assertAlmostEqual(3 - math.sqrt(9 - 4), ball.height_at(2.0))
        self.assertAlmostEqual(math.sqrt(9 - 4), ball.radius_at(1.0))
        self.assertEqual(math.inf, ball.height_at(3.5))
        bull = self.tool(type="bull", diameter_mm=10, corner_radius_mm=1)
        self.assertEqual(0.0, bull.height_at(4.0))
        self.assertAlmostEqual(1.0, bull.height_at(5.0))
        vee = self.tool(type="vee", diameter_mm=10, angle_deg=90)
        self.assertAlmostEqual(2.0, vee.height_at(2.0))
        self.assertAlmostEqual(5.0, vee.radius_at(7.0))
        drill = self.tool(type="drill", diameter_mm=5)
        self.assertAlmostEqual(2.5 / math.tan(math.radians(59)), drill.height_at(2.5))
        flat = self.tool(type="flat", diameter_mm=6)
        self.assertEqual([0.0, 0.0], list(flat.height_at(__import__("numpy").array([0.0, 3.0]))))


class Feeds(unittest.TestCase):
    def test_a_6mm_three_flute_in_6061_is_a_sane_starting_point(self):
        parsed = parse_job(BASE)
        feeds = for_op(parsed.material, parsed.tool("T1"), "rough", parsed.machine)
        self.assertTrue(10000 <= feeds.rpm <= 20000, feeds)
        self.assertTrue(800 <= feeds.feed_mm_min <= 3000, feeds)
        self.assertLess(feeds.plunge_mm_min, feeds.feed_mm_min)
        self.assertEqual((), feeds.clamped)

    def test_the_machine_clamps_and_says_so(self):
        parsed = parse_job(job(machine__max_rpm=6000, machine__max_feed_mm_min=500))
        feeds = for_op(parsed.material, parsed.tool("T1"), "rough", parsed.machine)
        self.assertEqual(6000, feeds.rpm)
        self.assertEqual(500, feeds.feed_mm_min)
        self.assertEqual(2, len(feeds.clamped))

    def test_a_tap_feeds_at_rpm_times_pitch_and_overrides_win(self):
        parsed = parse_job(job(tools=[{"id": "T1", "type": "tap", "diameter_mm": 6, "pitch_mm": 1}]))
        tap = for_op(parsed.material, parsed.tool("T1"), "tap", parsed.machine)
        self.assertAlmostEqual(tap.rpm * 1.0, tap.feed_mm_min)
        override = for_op(parsed.material, parsed.tool("T1"), "tap", parsed.machine, speed=300)
        self.assertEqual(300, override.rpm)

    def test_light_stepovers_thin_the_chip(self):
        parsed = parse_job(BASE)
        full = for_op(parsed.material, parsed.tool("T1"), "rough", parsed.machine, stepover_mm=3)
        light = for_op(parsed.material, parsed.tool("T1"), "finish", parsed.machine, stepover_mm=0.3)
        self.assertGreater(light.feed_mm_min, full.feed_mm_min)

    def test_cutting_speeds_fall_with_thickness(self):
        self.assertGreater(for_cut("steel-1018", "laser", 2), for_cut("steel-1018", "laser", 5))
        self.assertIsNone(for_cut("foam", "plasma", 3))


class WorkCoordinates(unittest.TestCase):
    def test_every_orientation_is_a_proper_rotation_with_its_tool_axis(self):
        import numpy as np

        for orientation, axis in {"+Z": (0, 0, 1), "-Z": (0, 0, -1), "+X": (1, 0, 0), "-X": (-1, 0, 0),
                                  "+Y": (0, 1, 0), "-Y": (0, -1, 0)}.items():
            with self.subTest(orientation=orientation):
                r = np.asarray(rotation_for(orientation))
                self.assertAlmostEqual(1.0, float(np.linalg.det(r)))
                self.assertEqual(axis, tuple(int(round(v)) for v in r[2]))

    def test_origins_and_the_round_trip(self):
        import numpy as np

        parsed = parse_job(BASE)
        stock = np.array([[-10, -5, 0], [10, 5, 21]], dtype=float)
        part = np.array([[-8, -3, 0], [8, 3, 20]], dtype=float)
        wcs = build_wcs(parsed.setups[0], stock_points=stock, part_points=part)
        self.assertEqual([0.0, 0.0, 21.0], wcs.origin_part_mm)
        self.assertTrue(np.allclose([[0, 0, 0]], wcs.to_wcs([[0, 0, 21]])))
        flipped = parse_job(job(setups__0__orientation="-Z", setups__0__origin="stock-top-corner")).setups[0]
        wcs = build_wcs(flipped, stock_points=stock, part_points=part)
        points = np.array([[1.0, 2.0, 3.0], [-4.0, 0.5, 9.0]])
        self.assertTrue(np.allclose(points, wcs.from_wcs(wcs.to_wcs(points))))
        # Flipped, the stock's bottom (z = 0) is the WCS top, and every stock point sits at or below WCS z = 0.
        self.assertTrue(np.all(wcs.to_wcs(stock)[:, 2] <= 1e-9))
        self.assertTrue(np.all(wcs.to_wcs(stock)[:, :2] >= -1e-9))

    def test_a_face_orientation_turns_the_frame_and_the_origin_sits_in_it(self):
        import dataclasses

        import numpy as np

        from cadgen._internal.cam.wcs import FaceOrientation

        stock = np.array([[x, y, z] for x in (-10, 10) for y in (-5, 5) for z in (0, 20)], dtype=float)
        setup = parse_job(job(setups__0__orientation="#o1.f4")).setups[0]
        with self.assertRaisesRegex(CamJobError, "names a face: read the part first"):
            build_wcs(setup, stock_points=stock, part_points=stock)
        normal = (math.sin(math.radians(30)), 0.0, math.cos(math.radians(30)))
        setup = dataclasses.replace(setup, orientation=FaceOrientation("#o1.f4", normal))
        wcs = build_wcs(setup, stock_points=stock, part_points=stock)
        self.assertTrue(np.allclose(normal, wcs.tool_axis))
        # stock-top-center in the turned frame: the stock's +X top edge is the highest the tool sees, at WCS z 0.
        self.assertAlmostEqual(0.0, float(wcs.to_wcs(stock)[:, 2].max()))
        self.assertAlmostEqual(0.0, float(wcs.to_wcs([[10, 0, 20]])[0][2]))


if __name__ == "__main__":
    unittest.main()
