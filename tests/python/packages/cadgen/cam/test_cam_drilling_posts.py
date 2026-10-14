"""Drill cycles posted: GRBL (no canned cycles) posts the expansion, a post with canned cycles posts G8x blocks, and
both read back (tests/python/support/gcode_reader.py) to the IR's own path. End to end: a pocket then the drilling
plans ready, the posted file and the GLB carry it."""

from __future__ import annotations

import json
import unittest

import numpy as np

from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.posts import get_post
from cadgen._internal.cam.posts.base import Post, Program
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support import gcode_reader
from tests.python.support.cam_fixtures import class_directory, quiet, read_glb
from tests.python.support.cam_fixtures_drilling import (CBORE, PLATE, counterbore_plate_step, drill_job,
                                                        drill_plate_step, hole_faces)


class CannedPost(Post):
    """A Fanuc-style test post that emits every cycle the base's cycle_lines knows."""

    name = "canned-test"
    kinds = ("mill",)
    canned_cycles = frozenset({"drill", "spot", "peck", "chipbreak", "tap", "bore", "ream"})


def _same_path(test, text: str, program: Program, post, *, tolerance: float = 0.01) -> None:
    from tests.python.support.cam_fixtures_posts import with_entries

    read = gcode_reader.read(text, start=program.toolpath.start)
    # Move by move: each move's kind and feed, the spindle on through every cut, the dwells.
    path = with_entries(program.toolpath)
    native = [(e.at, e.data["end"]) for e in path.events if e.kind == "cycle" and post.emits_cycle(e.data)]
    test.assertEqual([], gcode_reader.compare_moves(read, path, native=native))
    points, _ = gcode_reader.sample(read, 0.002, max_step=0.25)
    points = np.vstack([program.toolpath.start, points])            # both from the start (a first G0 Z sits on it)
    ir = program.toolpath.sample(0.002, max_step_mm=0.25).points
    for a, b in ((points, ir), (ir, points)):
        gaps = np.min(np.linalg.norm(a[:, None, :] - b[None, :, :], axis=2), axis=1)
        test.assertLess(float(gaps.max()), tolerance)
    test.assertTrue(np.allclose(points[-1], program.toolpath.ends()[-1], atol=1e-3))


class Posted(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        with quiet():
            cls.directory = class_directory(cls)
            cls.step = drill_plate_step(cls.directory)
            cls.features = cam.features(cls.step)
            cls.part = read_part(cls.step)
        f5, f6, f4 = (hole_faces(cls.features, d) for d in (5.0, 6.0, 4.0))
        cls.ops = [
            {"op": "drill", "tool": "T4", "faces": f5 + f4},                                   # spot (G81 here)
            {"op": "drill", "tool": "T1", "faces": f5, "cycle": "peck", "peck_mm": 3},        # G83
            {"op": "drill", "tool": "T7", "faces": f4, "cycle": "chipbreak", "peck_mm": 2},   # G73, G99 in the pocket
            {"op": "drill", "tool": "T2", "faces": f6, "cycle": "dwell", "dwell_s": 0.4},     # G82 P
            {"op": "drill", "tool": "T5", "faces": f6[:1], "depth_to": "tip"},               # G85
            {"op": "drill", "tool": "T3", "faces": f5[:2]},                                   # G84
        ]

    def program(self, post_name="grbl", ops=None):
        parsed = parse_job(drill_job(self.ops if ops is None else ops))
        stock = build_stock(parsed.stock, self.part)
        setups, _, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        plan = setups[0]
        return Program(setup=plan.setup, wcs=plan.wcs, toolpath=plan.toolpath, tools={t.id: t for t in parsed.tools},
                       machine=parsed.machine, version="TEST", part="drill_plate.step", tolerance_mm=0.01)

    def test_grbl_posts_every_cycle_expanded_and_it_reads_back_to_the_ir(self):
        from cadgen._internal.cam.job_errors import PostRefusal

        program = self.program(ops=[op for op in self.ops if op["tool"] != "T3"])
        # One file per tool (GRBL has no tool table), read as one program.
        text = "".join(text for _, text in get_post("grbl", "mill").render_tool_files(program))
        for code in ("G81", "G82", "G83", "G73", "G84", "G85", "G98", "G99", "G80"):
            self.assertNotRegex(text, rf"\b{code}\b")
        self.assertIn("G4 P0.4", text)                                   # the dwell at the bottom
        self.assertNotIn("M4", text)
        _same_path(self, text, program, get_post("grbl", "mill"))
        # A tap is refused: posted as moves (feed in, M4, feed out) the feed would not follow the spindle.
        tapped = self.program()
        with self.assertRaises(PostRefusal) as caught:
            get_post("grbl", "mill").render_tool_files(tapped)
        self.assertIn("thread mill", str(caught.exception))
        tap = next(op for op in tapped.toolpath.ops if op.tool == "T3")
        self.assertEqual(tap.index, caught.exception.operation)

    def test_a_canned_post_posts_g8x_and_it_reads_back_to_the_same_path(self):
        program = self.program()
        post = CannedPost()
        text = post.render(program)
        read = gcode_reader.read(text, start=program.toolpath.start)
        # Spot (two cycles: the top holes and the pocket's), peck, chip-break, dwell, ream, tap.
        self.assertEqual(["G82", "G82", "G83", "G73", "G82", "G85", "G84"], read.cycles)
        self.assertIn("G98 G83", text)
        self.assertIn("G99 G73", text)                                  # the pocket holes return to R
        # The depth rounds toward R (-15.2015 planned posts -15.201): never deeper than planned.
        self.assertRegex(text, r"G99 G73 X\S+ Y\S+ Z-15\.201 R-3 Q2 F")
        self.assertEqual(text.count("G80"), sum(1 for e in program.toolpath.events if e.kind == "cycle"))
        self.assertNotIn("M4", text)                                     # G84 reverses the spindle itself
        _same_path(self, text, program, post)

    def test_mach3_taps_in_a_floating_holder_and_the_header_says_so(self):
        parsed = parse_job(drill_job([{"op": "drill", "tool": "T3", "faces": hole_faces(self.features, 6.0)[:1]}],
                                     post="mach3"))
        self.assertIs(False, parsed.machine.rigid_tap)
        stock = build_stock(parsed.stock, self.part)
        setups, _, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        plan = setups[0]
        program = Program(setup=plan.setup, wcs=plan.wcs, toolpath=plan.toolpath,
                          tools={t.id: t for t in parsed.tools}, machine=parsed.machine, version="TEST",
                          part="drill_plate.step", tolerance_mm=0.01)
        text = get_post("mach3", "mill").render(program)
        self.assertIn("M6x1 tap in a floating tension/compression holder", text)
        (cycle,) = [e for e in plan.toolpath.events if e.kind == "cycle"]
        self.assertIs(False, cycle.data["rigid"])
        # A rigid post's header says nothing of it.
        self.assertNotIn("floating", CannedPost().render(self.program(ops=[self.ops[-1]])))

    def test_plan_end_to_end_after_the_pocket_is_ready_and_writes_the_drilling(self):
        from cadgen._internal.cam.run import plan_job

        f4 = hole_faces(self.features, 4.0)
        floor = next(f["ref"] for f in self.features.floors if abs(f["z_mm"] - PLATE["pocket"]["floor_z"]) < 1e-6
                     and f["normal"] == "+Z")
        tools = drill_job([])["tools"] + [{"id": "T8", "type": "flat", "diameter_mm": 6, "flutes": 3,
                                           "flute_length_mm": 20, "stickout_mm": 30}]
        ops = [{"op": "face", "tool": "T8"}, {"op": "pocket", "tool": "T8", "faces": [floor]},
               {"op": "drill", "tool": "T4", "holes": "all"},
               {"op": "drill", "tool": "T7", "faces": f4, "cycle": "peck"},
               {"op": "drill", "tool": "T1", "holes": {"diameter_mm": 5}}]
        with quiet():
            result = plan_job(self.step, job=drill_job(ops, tools=tools), out_dir=self.directory)
        self.assertTrue(result.ok, result.findings)
        errors = [f for f in result.findings if f["severity"] == "error"]
        self.assertEqual([], errors)
        self.assertEqual("ready", result.verdict["status"])
        rows = [op for op in result.operations if op["op"] == "drill"]
        self.assertEqual(["Spot 8 holes with T4 6 mm spot drill", "Peck drill 2 holes with T7 4 mm drill",
                          "Drill 4 holes with T1 5 mm drill"], [row["summary"].rsplit(",", 1)[0] for row in rows])
        posted = gcode_reader.read(gcode_reader.posted_text(result), start=(0, 0, 6.0))
        lowest = min(move.end[2] for move in posted.moves)
        self.assertAlmostEqual(-13.0 - 1.0 - 2.5 / np.tan(np.radians(59)), lowest, places=3)
        document, _ = read_glb(result.glb)
        cam = document["scenes"][document.get("scene", 0)]["extras"]["cam"]
        drills = [op for setup in cam["setups"] for op in setup["operations"] if op["op"] == "drill"]
        self.assertEqual(3, len(drills))
        self.assertTrue(all(op["time_s"] > 0 for op in drills))
        json.dumps(cam)


    def test_a_drill_whose_flutes_are_shorter_than_the_hole_fails_reach(self):
        from cadgen._internal.cam.run import plan_job

        tools = [{"id": "T1", "type": "drill", "diameter_mm": 5, "flute_length_mm": 8, "stickout_mm": 30}]
        with quiet():
            result = plan_job(self.step, job=drill_job([{"op": "drill", "tool": "T1", "holes": {"diameter_mm": 5}}],
                                                       tools=tools), out_dir=self.directory / "reach")
        self.assertTrue(result.ok)
        self.assertEqual("fix", result.verdict["status"])
        (reach,) = [f for f in result.findings if f["check"] == "reach"]
        self.assertEqual("reach_flutes", reach["type"])
        self.assertGreater(reach["items"][0]["depth_mm"], 12.0)

class CounterboresPosted(unittest.TestCase):
    """The counterbore plate's counterbore (G82) and back bore (G87 on Fanuc, G77 on Haas, its moves with M19 on
    LinuxCNC, refused on Mach3 and GRBL), planned and posted."""

    TOOLS = [{"id": "T1", "type": "counterbore", "diameter_mm": 14, "pilot_diameter_mm": 10},
             {"id": "T2", "type": "boring", "diameter_mm": 14, "flute_length_mm": 3, "shank_diameter_mm": 4,
              "stickout_mm": 40}]
    OPS = [{"op": "drill", "tool": "T1", "holes": "all"},
           {"op": "drill", "tool": "T2", "holes": "all", "cycle": "back_bore", "shift_mm": 2.5}]

    @classmethod
    def setUpClass(cls):
        with quiet():
            cls.directory = class_directory(cls)
            cls.step = counterbore_plate_step(cls.directory)
            cls.part = read_part(cls.step)

    def program(self, post_name: str, ops=None):
        parsed = parse_job(drill_job(self.OPS if ops is None else ops, tools=self.TOOLS, post=post_name))
        stock = build_stock(parsed.stock, self.part)
        setups, planned, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        self.assertEqual([], [op.meta["plan_error"] for op in planned if "plan_error" in op.meta])
        plan = setups[0]
        return Program(setup=plan.setup, wcs=plan.wcs, toolpath=plan.toolpath, tools={t.id: t for t in parsed.tools},
                       machine=parsed.machine, version="TEST", part="counterbore_plate.step", tolerance_mm=0.01)

    def test_fanuc_and_haas_post_the_counterbore_as_g82_and_the_back_bore_as_their_own_cycle(self):
        first, second = CBORE["back"]                     # nearest the start (0, 0) first
        for post_name, back_bore in (
                ("fanuc", f"G98 G87 X18. Y{first[1]:g}. Z-13. R-18. Q2.5 F"),
                ("haas", f"G98 G77 X18. Y{first[1]:g}. Z-13. R-18. I2.5 J0. F")):
            with self.subTest(post=post_name):
                text = get_post(post_name, "mill").render(self.program(post_name))
                self.assertRegex(text, r"G98 G82 X-18\. Y8\. Z-14\. R2\. P200 F")       # pilot 10 under the floor
                self.assertIn(back_bore, text)
                self.assertIn(f"\nX18. Y{second[1]:g}.\nG80\n", text)
                self.assertNotIn("M19", text)

    def test_linuxcnc_posts_the_back_bore_as_its_moves_and_they_read_back_to_the_ir(self):
        program = self.program("linuxcnc")
        post = get_post("linuxcnc", "mill")
        text = post.render(program)
        self.assertNotRegex(text, r"\bG87\b")
        self.assertEqual(4, text.count("M5\nM19 R0 Q10\n"))                 # two holes, in and out of each
        self.assertIn("G1 Z-13 F", text)
        _same_path(self, text, program, post)

    def test_mach3_and_grbl_refuse_the_back_bore_and_post_the_counterbore(self):
        from cadgen._internal.cam.job_errors import PostRefusal

        for post_name in ("mach3", "grbl"):
            with self.subTest(post=post_name):
                program = self.program(post_name)
                post = get_post(post_name, "mill")
                with self.assertRaises(PostRefusal) as caught:
                    post.render_tool_files(program) if post_name == "grbl" else post.render(program)
                self.assertIn("cannot stop the spindle oriented", str(caught.exception))
                bore = next(op for op in program.toolpath.ops if op.tool == "T2")
                self.assertEqual(bore.index, caught.exception.operation)
                program = self.program(post_name, self.OPS[:1])
                text = ("".join(t for _, t in post.render_tool_files(program)) if post_name == "grbl"
                        else post.render(program))
                _same_path(self, text, program, post)

    def test_a_counterbore_job_plans_ready_and_posts(self):
        from cadgen._internal.cam.run import plan_job

        with quiet():
            result = plan_job(self.step, job=drill_job([{"op": "drill", "tool": "T3", "holes": "all"},
                                                        *self.OPS[:1]],
                                                       tools=[*self.TOOLS, {"id": "T3", "type": "drill",
                                                                            "diameter_mm": 10}], post="fanuc"),
                              out_dir=self.directory / "ready")
        self.assertTrue(result.ok, result.findings)
        self.assertEqual([], [f for f in result.findings if f["severity"] == "error"])
        self.assertEqual("ready", result.verdict["status"])
        self.assertIn("G98 G82 X-18. Y8. Z-14. R2. P200 F", gcode_reader.posted_text(result))


if __name__ == "__main__":
    unittest.main()
