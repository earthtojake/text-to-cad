"""The shop-practice checks harvested from the parallel cam build: a long stickout, a cut through the stock's bottom,
a tap with no hole made before it, an operation that cuts nothing, a full-width cut, a tool no operation runs, the
spindle and feed clamps said per tool, and the tool changes, warnings and fixtures the GLB carries."""

from __future__ import annotations

import types
import unittest
from unittest import mock

from tests.python.support.cam_fixtures import BLOCK, block_step, class_directory, floor_ref, mill_job, quiet, read_glb

_SHORT = {"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 18, "stickout_mm": 24}
_DRILL = {"id": "T2", "type": "drill", "diameter_mm": 5}
_TAP = {"id": "T3", "type": "tap", "diameter_mm": 6, "pitch_mm": 1}


class PracticeChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = block_step(cls.directory)
        cls.lower = floor_ref(cam.features(cls.step), BLOCK["lower"]["floor_z"])

    def plan(self, operations, *, tools=None, machine=None, setups=None):
        from cadgen import cam

        job = mill_job(operations, tools=tools or [_SHORT, _DRILL], machine=machine, setups=setups)
        with quiet():
            result = cam.plan(self.step, job=job, out_dir=self.directory)
        self.assertTrue(result.ok, result.findings)
        return result

    def of(self, result, kind):
        return [f for f in result.findings if f["type"] == kind]

    def test_a_long_stickout_is_one_warning_per_tool_naming_its_operations(self):
        long = dict(_SHORT, stickout_mm=30)                     # 5 diameters
        result = self.plan([{"op": "face", "tool": "T1"}, {"op": "pocket", "tool": "T1", "faces": [self.lower]}],
                           tools=[long, _DRILL])
        (found,) = self.of(result, "long_stickout")
        self.assertEqual("warning", found["severity"])
        self.assertIn("5.0 times its diameter", found["summary"])
        self.assertIn("operations 1, 2", found["summary"])
        self.assertEqual([0, 1], [item["operation"] for item in found["items"]])
        self.assertEqual([], self.of(self.plan([{"op": "face", "tool": "T1"}]), "long_stickout"))   # 4 diameters

    def test_a_through_drill_below_the_stock_bottom_is_said_and_a_tool_no_one_runs_is_noted(self):
        result = self.plan([{"op": "drill", "tool": "T2", "holes": "all"}],
                           tools=[_SHORT, _DRILL, dict(_TAP, id="T9")])
        (below,) = self.of(result, "through_stock_bottom")
        self.assertEqual("warning", below["severity"])
        self.assertIn("below the stock's bottom", below["summary"])
        self.assertGreater(below["items"][0]["depth_mm"], 0.5)
        (unused,) = self.of(result, "unused_tool")
        self.assertEqual("info", unused["severity"])
        self.assertEqual([{"tool": "T1"}, {"tool": "T9"}], unused["items"])
        self.assertIn("Tools T1 (6 mm flat), T9", unused["summary"])
        self.assertEqual("ready", result.verdict["status"])     # notes and warnings, no errors

    def test_a_tap_with_no_hole_made_before_it_is_said_and_one_drilled_first_is_not(self):
        alone = self.plan([{"op": "drill", "tool": "T3", "holes": "all"}], tools=[_DRILL, _TAP])
        (found,) = self.of(alone, "assumes_prepared_hole")
        self.assertEqual(("prepared_hole", "warning"), (found["check"], found["severity"]))
        self.assertIn("taps 4 holes no earlier operation makes", found["summary"])
        self.assertEqual(4, len(found["items"]))
        drilled = self.plan([{"op": "drill", "tool": "T2", "holes": "all"}, {"op": "drill", "tool": "T3", "holes": "all"}],
                            tools=[_DRILL, _TAP])
        self.assertEqual([], self.of(drilled, "assumes_prepared_hole"))
        self.assertEqual({"count": 1, "order": ["T2", "T3"]}, drilled.summary["tool_changes"])
        self.assertIn("1 tool change: T2 then T3", drilled.human_lines())

    def test_an_operation_that_cuts_nothing_where_the_job_named_faces_is_an_error(self):
        def rapids_only(_self, ctx, params):
            builder = ctx.builder()
            builder.rapid(z=ctx.heights.clearance)
            return builder.build()

        with mock.patch("cadgen._internal.cam.operations.pocket.PocketOp.plan", rapids_only):
            result = self.plan([{"op": "face", "tool": "T1"}, {"op": "pocket", "tool": "T1", "faces": [self.lower]}])
        (found,) = self.of(result, "empty_operation")
        self.assertEqual("error", found["severity"])
        self.assertEqual([{"setup": "top", "operation": 1}], found["items"])
        self.assertEqual("fix", result.verdict["status"])
        self.assertEqual((), result.posts)

    def test_a_facing_pass_with_nothing_to_face_is_only_a_warning(self):
        def rapids_only(_self, ctx, params):
            builder = ctx.builder()
            builder.rapid(z=ctx.heights.clearance)
            return builder.build()

        with mock.patch("cadgen._internal.cam.operations.face.FaceOp.plan", rapids_only):
            result = self.plan([{"op": "face", "tool": "T1"}, {"op": "pocket", "tool": "T1", "faces": [self.lower]}])
        (found,) = self.of(result, "empty_operation")
        self.assertEqual("warning", found["severity"])
        self.assertEqual([{"setup": "top", "operation": 0}], found["items"])

    def test_a_stated_feed_under_a_spindle_clamp_says_the_chip_grows_once_per_tool(self):
        machine = {"kind": "mill", "post": "grbl", "max_rpm": 6000, "travel_mm": [300, 200, 80]}
        result = self.plan([{"op": "face", "tool": "T1", "feed": 900},
                            {"op": "pocket", "tool": "T1", "faces": [self.lower], "feed": 900}], machine=machine)
        (found,) = [f for f in self.of(result, "limits") if f["items"][0]["limit"] == "spindle"]
        self.assertIn("T1 (6 mm flat)", found["summary"])
        self.assertIn("operations 1, 2", found["summary"])
        self.assertIn("bigger chip", found["description"])
        self.assertIn("keeps the planned chip", found["description"])
        self.assertEqual([("T1", 0), ("T1", 1)], [(i["tool"], i["operation"]) for i in found["items"]])
        table = self.plan([{"op": "face", "tool": "T1"}], machine=machine)
        (found,) = self.of(table, "limits")
        self.assertIn("chip load is kept", found["description"])

    def test_a_spindle_raised_to_the_machines_slowest_says_so_and_what_to_check(self):
        # A 6 mm cutter wants ~13300 rpm in aluminium; this spindle turns no slower than 15000.
        machine = {"kind": "mill", "post": "grbl", "min_rpm": 15000, "max_rpm": 24000, "travel_mm": [300, 200, 80]}
        result = self.plan([{"op": "face", "tool": "T1"}], machine=machine)
        (found,) = self.of(result, "limits")
        self.assertEqual("raised", found["items"][0]["limit"])
        self.assertIn("min_rpm (15000)", found["description"])
        self.assertIn("Check the tool maker's chart at this speed", found["description"])

    def test_the_glb_carries_tool_changes_warnings_and_fixtures(self):
        setups = [{"id": "top", "orientation": "+Z", "origin": "stock-top-center",
                   "fixture": [{"min_mm": [-60, -50, 0], "max_mm": [-45, 50, 10], "name": "jaw"}],
                   "operations": [{"op": "face", "tool": "T1"}, {"op": "drill", "tool": "T2", "holes": "all"}]}]
        result = self.plan([], setups=setups)
        cam = read_glb(result.glb)[0]["scenes"][0]["extras"]["cam"]
        self.assertEqual({"count": 1, "order": ["T1", "T2"]}, cam["tool_changes"])
        self.assertEqual([{"name": "jaw", "min_mm": [-60.0, -50.0, 0.0], "max_mm": [-45.0, 50.0, 10.0]}],
                         cam["setups"][0]["fixtures"])
        self.assertEqual(list(result.warnings), cam["warnings"])


class Features(unittest.TestCase):
    """``uncut_feature`` names a hole or pocket a setup reaches that nothing cuts; ``thin_wall`` a cut feature with
    under a millimetre of wall to the outside."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Box, Cylinder, Pos, export_step

        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.block = block_step(cls.directory)
        cls.lower = floor_ref(cam.features(cls.block), BLOCK["lower"]["floor_z"])
        base = (Align.CENTER, Align.CENTER, Align.MIN)
        # A 40 x 30 x 10 plate with a Ø6 hole whose wall to the +X side is 0.6 mm, and one well inside.
        plate = Box(40, 30, 10, align=base)
        plate -= Pos(20 - 0.6 - 3, 0, 0) * Cylinder(3, 10, align=base)
        plate -= Pos(-8, 0, 0) * Cylinder(3, 10, align=base)
        cls.plate = cls.directory / "thin.step"
        export_step(plate, str(cls.plate))

    def plan(self, step, operations, tools):
        from cadgen import cam

        with quiet():
            result = cam.plan(step, job=mill_job(operations, tools=tools), out_dir=self.directory)
        self.assertTrue(result.ok, result.findings)
        return result

    def test_holes_and_a_pocket_no_operation_cuts_are_named(self):
        result = self.plan(self.block, [{"op": "face", "tool": "T1"}], [_SHORT, _DRILL])
        found = [f for f in result.findings if f["type"] == "uncut_feature"]
        self.assertEqual("warning", found[0]["severity"])
        holes = next(f for f in found if "Ø5 holes" in f["summary"])
        self.assertIn("No operation cuts 4 Ø5 holes", holes["summary"])
        self.assertIn("which setup top reaches", holes["summary"])
        self.assertEqual(4, len(holes["items"]))
        self.assertTrue(any("pocket on floor" in f["summary"] for f in found))
        cut = self.plan(self.block, [{"op": "face", "tool": "T1"}, {"op": "pocket", "tool": "T1", "faces": [self.lower]},
                                     {"op": "drill", "tool": "T2", "holes": "all"}], [_SHORT, _DRILL])
        self.assertEqual([], [f["summary"] for f in cut.findings if f["type"] == "uncut_feature"])

    def test_a_drilled_hole_with_under_a_millimetre_to_the_outside_is_a_thin_wall(self):
        drill = {"id": "T2", "type": "drill", "diameter_mm": 6}
        result = self.plan(self.plate, [{"op": "drill", "tool": "T2", "holes": "all"}], [_SHORT, drill])
        (found,) = [f for f in result.findings if f["type"] == "thin_wall"]
        self.assertEqual("warning", found["severity"])
        self.assertIn("leaves 0.60 mm of wall", found["summary"])
        self.assertAlmostEqual(0.6, found["items"][0]["wall_mm"], delta=0.02)


class CounterboreIsNotAPocket(unittest.TestCase):
    def test_a_counterbores_shoulder_is_its_holes_face_not_a_pocket_floor(self):
        from cadgen._internal.cam.checks._features import pockets
        from cadgen._internal.cam.features import holes, read_features
        from cadgen._internal.cam.part import read_part
        from tests.python.support.cam_fixtures_drilling import counterbore_plate_step

        part = read_part(counterbore_plate_step(class_directory(type(self))))
        found = holes(part)
        shoulders = {ref for hole in found if hole.get("counterbore") for ref in hole["faces"]}
        floors = read_features(part)["floors"]
        self.assertTrue(shoulders & {p["ref"] for p in pockets(part, floors)})      # read alone, a "pocket"
        self.assertFalse(shoulders & {p["ref"] for p in pockets(part, floors, found)})


class FullSlot(unittest.TestCase):
    """The check reads an operation's own ``full_slot_mm`` fact; a slot is meant to cut full width."""

    def ctx(self, op_name, length):
        tool = types.SimpleNamespace(id="T1", diameter_mm=6.0)
        op = types.SimpleNamespace(index=0, setup="top", summary="Pocket with T1", tool=tool, meta={"full_slot_mm": length},
                                   operation=types.SimpleNamespace(name=op_name))
        return types.SimpleNamespace(ops=[op])

    def test_past_five_diameters_of_full_width_cutting_it_warns(self):
        from cadgen._internal.cam.checks import full_slot

        (found,) = full_slot.run(self.ctx("pocket", 45.0))
        self.assertEqual(("full_slot", "warning"), (found["type"], found["severity"]))
        self.assertIn("45 mm at T1's full width (8 diameters)", found["summary"])
        self.assertEqual([], full_slot.run(self.ctx("pocket", 29.0)))
        self.assertEqual([], full_slot.run(self.ctx("slot", 200.0)))


if __name__ == "__main__":
    unittest.main()
