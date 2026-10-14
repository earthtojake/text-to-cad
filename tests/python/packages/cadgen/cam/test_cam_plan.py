"""``cadgen cam plan`` end to end: the block faced and pocketed, its GLB and G-code read back, refusals write nothing."""

from __future__ import annotations

import contextlib
import io
import json
import unittest

import numpy as np

from tests.python.support import gcode_reader
from tests.python.support.cam_fixtures import (
    BLOCK, accessor_array, block_step, class_directory, floor_ref, mill_job, quiet, read_glb,
)


class PlanBlock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = block_step(cls.directory)
        cls.lower = floor_ref(cam.features(cls.step), BLOCK["lower"]["floor_z"])
        cls.job = mill_job([{"op": "face", "tool": "T1"}, {"op": "pocket", "tool": "T1", "faces": [cls.lower]}])
        with quiet():
            cls.result = cam.plan(cls.step, job=cls.job)

    def test_the_verdict_and_the_rows(self):
        result = self.result
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("ready", result.verdict["status"])
        self.assertRegex(result.verdict["headline"], r"^Ready to cut · \d+ min · 1 tool$")
        self.assertEqual(["face", "pocket"], [op["op"] for op in result.operations])
        self.assertEqual([0, 1], [op["index"] for op in result.operations])
        self.assertTrue(all(op["rpm"] and op["feed_mm_min"] for op in result.operations))
        checks = {f["check"] for f in result.findings}
        self.assertIn("corner_radius", checks)          # the square pocket's corners, as warnings
        self.assertTrue(all(f["severity"] != "error" for f in result.findings))
        lines = result.human_lines()
        self.assertEqual(result.verdict["headline"], lines[0])
        self.assertTrue(any(line.startswith("top 2. Pocket") for line in lines))
        self.assertTrue(lines[-1].startswith("safety:"))

    def test_the_glb_carries_the_plan_and_the_lines(self):
        document, blob = read_glb(self.result.glb)
        scene = document["scenes"][0]["extras"]
        root = document["nodes"][0]["extras"]
        for extras in (scene, root):
            self.assertEqual("cadgen cam", extras["generator"])
            self.assertEqual(1, extras["cam"]["schema"])
        cam = scene["cam"]
        self.assertEqual("block.step", cam["document"])
        self.assertEqual(self.result.verdict, cam["verdict"])
        ops = cam["setups"][0]["operations"]
        self.assertEqual([self.lower], ops[1]["faces"])
        for key in ("index", "tool", "tool_plain", "tool_diameter_mm", "plain", "summary", "t0", "t1", "time_s", "rpm",
                    "feed_mm_min"):
            self.assertIn(key, ops[1])
        self.assertEqual("+Z", cam["setups"][0]["orientation"])
        self.assertEqual([{"setup": "top", "file": "block.top.nc", "post": "grbl", "tool": None}], cam["posts"])
        kinds = {node["name"]: node.get("extras", {}).get("kind") for node in document["nodes"][1:]}
        self.assertEqual({"part": "part", "stock": "stock", "top feed": "feed", "top rapid": "rapid"}, kinds)
        feed = next(m for m in document["meshes"] if m["name"] == "top feed")["primitives"][0]
        self.assertEqual(1, feed["mode"])
        self.assertEqual({"POSITION", "_CAM_T", "_CAM_OP"}, set(feed["attributes"]))    # a 3-axis tool's axis is fixed
        t = accessor_array(document, blob, feed["attributes"]["_CAM_T"])
        op = accessor_array(document, blob, feed["attributes"]["_CAM_OP"])
        self.assertEqual({0.0, 1.0}, set(np.unique(op).tolist()))
        self.assertLessEqual(float(t.max()), cam["duration_s"] + 1e-3)
        pocket = t[op == 1]
        self.assertGreaterEqual(float(pocket.min()), ops[1]["t0"] - 1e-3)
        self.assertLessEqual(float(pocket.max()), ops[1]["t1"] + 1e-3)
        positions = accessor_array(document, blob, feed["attributes"]["POSITION"])
        # glTF is Y up, metres: the pocket floor (part z = 11) is the lowest feed point.
        self.assertAlmostEqual(0.011, float(positions[:, 1].min()), places=6)

    def test_the_gcode_reaches_the_floor_and_opens_safely(self):
        # GRBL posts one file per tool: block.top.T1.nc, block.top.T2.nc..., read back as one program.
        self.assertTrue(self.result.posts[0]["file"].startswith(str(self.directory / "block.top.")))
        text = gcode_reader.posted_text(self.result, "top")
        self.assertIn("NOT proven on a machine", text.splitlines()[2])
        program = gcode_reader.read(text, start=(0.0, 0.0, 6.0))
        self.assertIn("G54", program.offsets)
        cuts = [m for m in program.moves if m.kind != "rapid"]
        # WCS zero is the stock top, a millimetre over the part: the lower floor is 15 below it.
        self.assertAlmostEqual(-15.0, min(m.end[2] for m in cuts), places=3)
        self.assertGreaterEqual(min(m.end[2] for m in program.moves if m.kind == "rapid"), -15.0)
        self.assertTrue(any(m.kind in ("arc_cw", "arc_ccw") for m in program.moves))

    def test_the_cli_answers_one_json_line(self):
        from cadgen import cli

        out = io.StringIO()
        with contextlib.redirect_stdout(out), quiet():
            code = cli.main(["cam", "plan", str(self.step), "--job", json.dumps(self.job), "--out-dir",
                             str(self.directory / "cli"), "--json"])
        self.assertEqual(0, code)
        lines = out.getvalue().strip().splitlines()
        self.assertEqual(1, len(lines))
        payload = json.loads(lines[0])
        self.assertTrue(payload["ok"])
        self.assertTrue((self.directory / "cli" / "block.cam.glb").is_file())
        self.assertTrue((self.directory / "cli" / "block.top.nc").is_file())

    def test_a_tool_too_short_is_a_fix(self):
        from cadgen import cam

        job = mill_job([{"op": "pocket", "tool": "T1", "faces": [self.lower]}], tools=[
            {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 6, "stickout_mm": 30}])
        with quiet():
            result = cam.plan(self.step, job=job, out_dir=self.directory / "short")
        self.assertTrue(result.ok)
        self.assertEqual("fix", result.verdict["status"])
        self.assertTrue(result.verdict["headline"].startswith("1 to fix · "))
        reach = [f for f in result.findings if f["check"] == "reach"]
        self.assertEqual("error", reach[0]["severity"])
        # The upper step's walls stand 9 mm over its floor; the lower step's only 6 over its own.
        self.assertAlmostEqual(9.0, reach[0]["items"][0]["depth_mm"], places=3)
        self.assertEqual(0, reach[0]["items"][0]["operation"])

    def test_a_job_that_cannot_run_writes_nothing_and_clears_a_stale_result(self):
        from cadgen import cam

        out = self.directory / "refused"
        out.mkdir()
        stale = out / "block.cam.glb"
        stale.write_bytes(b"old")
        from cadgen._internal.cam.operations import OPERATION_NAMES, REGISTRY, available

        cases = {
            "is not a face of this part": mill_job([{"op": "pocket", "tool": "T1", "faces": ["#o1.f999"]}]),
            "unknown key 'speeed'": mill_job([{"op": "face", "tool": "T1", "speeed": 1}]),
        }
        unbuilt = [name for name in OPERATION_NAMES if not available(name) and "mill" in REGISTRY[name].machines]
        if unbuilt:
            cases["not in this cadgen yet"] = mill_job([{"op": unbuilt[0], "tool": "T1", "faces": [self.lower]}])
        for expected, job in cases.items():
            with self.subTest(expected=expected):
                with quiet():
                    result = cam.plan(self.step, job=job, out_dir=out)
                self.assertFalse(result.ok)
                self.assertIsNone(result.glb)
                self.assertIn(expected, result.findings[0]["summary"])
                self.assertEqual(("job", "error"), (result.findings[0]["check"], result.findings[0]["severity"]))
                self.assertEqual([], sorted(p.name for p in out.iterdir()))
                self.assertTrue(result.human_lines()[0].startswith("not planned:"))


if __name__ == "__main__":
    unittest.main()
