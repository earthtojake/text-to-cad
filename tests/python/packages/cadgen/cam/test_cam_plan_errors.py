"""An operation that cannot be planned, or a post that cannot write it, is an error finding of a known kind on that
operation: every other operation still plans, the GLB is written and no G-code is (from the parallel cam build)."""

from __future__ import annotations

import unittest
from unittest import mock

from tests.python.support.cam_fixtures import BLOCK, block_step, class_directory, floor_ref, mill_job, quiet, read_glb


class PlanErrors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = block_step(cls.directory)
        cls.lower = floor_ref(cam.features(cls.step), BLOCK["lower"]["floor_z"])
        cls.job = mill_job([{"op": "face", "tool": "T1"}, {"op": "pocket", "tool": "T1", "faces": [cls.lower]}])

    def plan(self, **patches):
        from cadgen import cam

        with quiet(), contextlib_patches(patches):
            return cam.plan(self.step, job=self.job, out_dir=self.directory)

    def test_a_plan_error_is_a_finding_of_its_kind_on_its_operation(self):
        from cadgen._internal.cam.job_errors import PlanError

        def refuse(_self, ctx, params):
            raise PlanError("tool_too_large", "T1 (6 mm) does not fit the pocket")

        result = self.plan(**{"cadgen._internal.cam.operations.pocket.PocketOp.plan": refuse})
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("fix", result.verdict["status"])
        found = [f for f in result.findings if f["type"] == "tool_too_large"]
        self.assertEqual(1, len(found))
        self.assertEqual("error", found[0]["severity"])
        self.assertEqual([{"setup": "top", "operation": 1}], found[0]["items"])
        self.assertIn("operation 2 (Pocket with T1, setup top)", found[0]["summary"])
        self.assertIn("does not fit the pocket", found[0]["summary"])
        self.assertEqual((), result.posts)                      # no G-code while an error stands
        self.assertTrue(result.glb.is_file())                   # the GLB shows the rest
        rows = {row["index"]: row for row in result.operations}
        self.assertGreater(rows[0]["moves"], 0)                  # the face still planned
        self.assertEqual(0, rows[1]["moves"])
        self.assertNotIn("plan_error", rows[1].get("facts", {}))
        cam = read_glb(result.glb)[0]["scenes"][0]["extras"]["cam"]
        self.assertIn("tool_too_large", {f["type"] for f in cam["findings"]})

    def test_a_plan_error_kind_is_closed(self):
        from cadgen._internal.cam.job_errors import PLAN_ERROR_KINDS, PlanError

        self.assertIn("empty_operation", PLAN_ERROR_KINDS)
        with self.assertRaises(ValueError):
            PlanError("too_big", "x")

    def test_a_post_refusal_is_no_post_support_on_its_operation(self):
        from cadgen._internal.cam.job_errors import PostRefusal

        def refuse(_self, program):
            raise PostRefusal("grbl has no tapping cycle and cannot hold the feed to the spindle", operation=1)

        with mock.patch("cadgen._internal.cam.posts.grbl.GrblPost.render_tool_files",
                        lambda _self, program: refuse(_self, program)):
            result = self.plan(**{"cadgen._internal.cam.posts.grbl.GrblPost.render": refuse})
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("fix", result.verdict["status"])
        found = [f for f in result.findings if f["type"] == "no_post_support"]
        self.assertEqual(1, len(found), result.findings)
        self.assertEqual("post", found[0]["check"])
        self.assertEqual([{"setup": "top", "operation": 1}], found[0]["items"])
        self.assertIn("no tapping cycle", found[0]["summary"])
        self.assertEqual((), result.posts)
        self.assertEqual([], sorted(p.name for p in self.directory.glob("block.top*")))
        self.assertTrue(result.glb.is_file())

    def test_durations_round_before_they_are_worded(self):
        from cadgen._internal.cam.run import _duration_words

        cases = {12.4: "12 s", 59.6: "1 min", 89: "1 min", 3570: "1 h 00 min", 3600: "1 h 00 min",
                 7170: "2 h 00 min", 3900: "1 h 05 min", 0.2: "1 s"}
        for seconds, words in cases.items():
            with self.subTest(seconds=seconds):
                self.assertEqual(words, _duration_words(seconds))


class OperationHeights(unittest.TestCase):
    """An operation's own ``clearance_mm`` and ``retract_mm`` are the heights it plans with; it ends at or above the
    setup's clearance, so the next operation starts safe."""

    def test_an_operation_travels_at_its_own_clearance(self):
        import numpy as np

        from cadgen._internal.cam.ir import RAPID
        from cadgen._internal.cam.job import parse_job
        from cadgen._internal.cam.part import read_part
        from cadgen._internal.cam.run import parse_operations, plan_setups
        from cadgen._internal.cam.stock import build_stock

        directory = class_directory(type(self))
        step = block_step(directory)
        lower = floor_ref(__import__("cadgen.cam", fromlist=["features"]).features(step), BLOCK["lower"]["floor_z"])
        job = parse_job(mill_job([{"op": "pocket", "tool": "T1", "faces": [lower], "clearance_mm": 20,
                                   "retract_mm": 8},
                                  {"op": "pocket", "tool": "T1", "faces": [lower]}]))
        part = read_part(step)
        stock = build_stock(job.stock, part, base_dir=job.base_dir)
        with quiet():
            (setup,), ops, _ = plan_setups(job, parse_operations(job), part, stock)
        top = setup.heights.stock_top
        moves = setup.toolpath.moves
        ranges = setup.toolpath.ops                 # the op plans' own ranges are the caller's to fill
        first, second = (moves[r.start:r.end] for r in ranges)
        self.assertAlmostEqual(top + 20.0, float(np.max(first[first["kind"] == RAPID]["z"])), places=6)
        self.assertTrue(np.any(np.isclose(first["z"], top + 8.0)))           # its retract plane
        self.assertGreaterEqual(float(first["z"][-1]), setup.heights.clearance - 1e-9)   # ends clear for the next
        # The next operation, with no heights of its own, travels at the setup's clearance between its cuts.
        self.assertTrue(np.any(np.isclose(second[second["kind"] == RAPID]["z"], setup.heights.clearance)))
        self.assertFalse(np.any(np.isclose(second["z"], top + 8.0)))


class PostOverride(unittest.TestCase):
    """``--post`` writes the same job for another controller under the same checks as ``machine.post``; the cycle
    time's assumed inputs are said."""

    @classmethod
    def setUpClass(cls):
        cls.directory = class_directory(cls)
        cls.step = block_step(cls.directory)

    def plan(self, job, **keys):
        from cadgen import cam

        with quiet():
            return cam.plan(self.step, job=job, out_dir=self.directory, **keys)

    def test_post_replaces_the_jobs_post_under_the_same_checks(self):
        job = mill_job([{"op": "face", "tool": "T1"}])
        haas = self.plan(job, post="haas")
        self.assertTrue(haas.ok, haas.findings)
        self.assertEqual(["haas"], [p["post"] for p in haas.posts])
        self.assertEqual("haas", haas.summary["post"])
        self.assertIn("post haas", (self.directory / "block.top.nc").read_text(encoding="utf-8"))
        wrong = self.plan(job, post="marlin")              # a laser post, not a mill's
        self.assertFalse(wrong.ok)
        self.assertIn("marlin", wrong.findings[0]["summary"])
        keyed = mill_job([{"op": "face", "tool": "T1"}], machine={"kind": "mill", "post": "fanuc", "cycles": True})
        refused = self.plan(keyed, post="grbl")             # fanuc's own key is not grbl's
        self.assertFalse(refused.ok)
        self.assertIn("cycles", refused.findings[0]["summary"])

    def test_the_cycle_times_assumed_rates_are_said(self):
        result = self.plan(mill_job([{"op": "face", "tool": "T1"}]))
        rates = {entry["key"]: entry["value"] for entry in result.assumed}
        self.assertEqual((5000.0, 10.0), (rates["machine.rapid_mm_min"], rates["machine.tool_change_s"]))
        cam = read_glb(result.glb)[0]["scenes"][0]["extras"]["cam"]
        self.assertEqual([dict(entry) for entry in result.assumed], cam["assumed"])
        stated = mill_job([{"op": "face", "tool": "T1"}], machine={"kind": "mill", "post": "grbl",
                                                                  "rapid_mm_min": 4000, "tool_change_s": 20})
        self.assertFalse({"machine.rapid_mm_min", "machine.tool_change_s"}
                         & {entry["key"] for entry in self.plan(stated).assumed})

    def test_the_generated_cli_takes_the_flag(self):
        from cadgen.cli.cam_plan import build_parser

        self.assertIn("--post", build_parser().format_help())


class PlanOneOccurrence(unittest.TestCase):
    """``cam plan`` takes ``--occurrence`` as ``cam features`` does, so one part of an assembly can be machined."""

    def test_an_assembly_plans_the_occurrence_it_names(self):
        from build123d import Align, Box, Compound, Pos, export_step

        from cadgen import cam

        directory = class_directory(type(self))
        base = (Align.CENTER, Align.CENTER, Align.MIN)
        parts = [Box(20, 20, 10, align=base), Pos(40, 0, 0) * Box(30, 20, 12, align=base)]
        for k, part in enumerate(parts):
            part.label = f"p{k}"
        path = directory / "asm.step"
        export_step(Compound(children=parts, label="asm"), str(path))
        job = mill_job([{"op": "face", "tool": "T1"}])
        with quiet():
            refused = cam.plan(path, job=job)
            planned = cam.plan(path, job=job, occurrence="#o1.2")
        self.assertFalse(refused.ok)
        self.assertIn("--occurrence", refused.findings[0]["summary"])
        self.assertTrue(planned.ok, planned.findings)
        stock = read_glb(planned.glb)[0]["scenes"][0]["extras"]["cam"]["stock"]
        self.assertIn("#o1.2", read_glb(planned.glb)[0]["scenes"][0]["extras"]["cam"]["occurrence"])
        self.assertTrue(stock)

    def test_the_generated_cli_takes_the_flag(self):
        from cadgen.cli.cam_plan import build_parser

        self.assertIn("--occurrence", build_parser().format_help())


def contextlib_patches(patches: dict):
    import contextlib

    stack = contextlib.ExitStack()
    for target, value in patches.items():
        stack.enter_context(mock.patch(target, value))
    return stack


if __name__ == "__main__":
    unittest.main()
