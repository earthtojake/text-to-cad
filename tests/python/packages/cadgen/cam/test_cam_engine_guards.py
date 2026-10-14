"""Engine guards from review: plausible-wrong plans the engine must refuse, flag or get right (law 10), and keys it
must not accept and ignore (law 9). Each test is one fixed bug, on a small part built in a temporary directory."""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.python.support.cam_fixtures import class_directory, mill_job, quiet


def _twin_holes_step(directory):
    """40 x 40 x 30 with a Ø5 x 10 blind hole from the top and one from the bottom on the same axis: a 10 mm web."""
    from build123d import Align, Box, Cylinder, Pos, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    part = Box(40, 40, 30, align=base)
    part -= Pos(0, 0, 20) * Cylinder(2.5, 10, align=base)
    part -= Pos(0, 0, 0) * Cylinder(2.5, 10, align=base)
    path = directory / "twin.step"
    export_step(part, str(path))
    return path


def _slotted_hole_step(directory):
    """40 x 40 x 30 with a Ø5 through hole crossed by a slot (z 10..20) open front to back: one hole across air."""
    from build123d import Align, Box, Cylinder, Pos, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    part = Box(40, 40, 30, align=base)
    part -= Pos(0, 0, 10) * Box(12, 40, 10, align=base)
    part -= Cylinder(2.5, 30, align=base)
    path = directory / "slotted.step"
    export_step(part, str(path))
    return path


def _plate_with_hole_step(directory):
    from build123d import Align, Box, Cylinder, export_step

    base = (Align.CENTER, Align.CENTER, Align.MIN)
    path = directory / "holed.step"
    export_step(Box(40, 40, 10, align=base) - Cylinder(2.5, 10, align=base), str(path))
    return path


def _errors(result, check: str) -> list[dict]:
    return [f for f in result.findings if f["severity"] == "error" and f["check"] == check]


class CoaxialHoles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = class_directory(cls)
        cls.twin = _twin_holes_step(cls.directory)

    def test_blind_holes_either_side_of_a_web_are_two_blind_holes(self):
        from cadgen import cam

        holes = cam.features(self.twin).holes
        self.assertEqual(2, len(holes))
        self.assertEqual(["+Z", "-Z"], sorted(h["axis_word"] for h in holes))
        for hole in holes:
            self.assertFalse(hole["through"])
            self.assertAlmostEqual(10.0, hole["depth_mm"], places=3)

    def test_a_hole_crossing_a_slot_is_still_one_through_hole(self):
        from cadgen import cam

        holes = cam.features(_slotted_hole_step(self.directory)).holes
        self.assertEqual(1, len(holes))
        self.assertTrue(holes[0]["through"])
        self.assertAlmostEqual(30.0, holes[0]["depth_mm"], places=3)
        self.assertEqual(2, len(holes[0]["faces"]))

    def test_a_tap_stops_in_its_blind_hole_and_one_driven_through_the_web_is_a_gouge(self):
        from cadgen import cam

        tap = [{"id": "T1", "type": "tap", "diameter_mm": 6, "pitch_mm": 1, "flute_length_mm": 40, "stickout_mm": 50}]
        with quiet():
            blind = cam.plan(self.twin, job=mill_job([{"op": "drill", "tool": "T1", "holes": "all"}], tools=tap),
                             out_dir=self.directory / "blind")
        self.assertTrue(blind.ok)
        self.assertEqual(1, blind.operations[0]["facts"]["hole_count"])
        # Stock top is z 31 (1 mm on top): the hole's floor is z 20, WCS -11; the tap stops a pitch above it.
        self.assertAlmostEqual(-10.0, blind.operations[0]["facts"]["bottom_z"], places=3)
        self.assertEqual([], _errors(blind, "gouge"))
        with quiet():
            deep = cam.plan(self.twin, job=mill_job([{"op": "drill", "tool": "T1", "points": [[0, 0]],
                                                      "depth_mm": 16, "top_z": -1}], tools=tap),
                            out_dir=self.directory / "deep")
        self.assertTrue(deep.ok)
        self.assertEqual("fix", deep.verdict["status"])
        self.assertTrue(_errors(deep, "gouge"))


class DrillBodyGouge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = class_directory(cls)
        cls.step = _plate_with_hole_step(cls.directory)

    def _plan(self, tool: dict, name: str):
        from cadgen import cam

        with quiet():
            return cam.plan(self.step, job=mill_job([{"op": "drill", "tool": "T1", "holes": "all"}],
                                                    tools=[{"id": "T1", **tool}]), out_dir=self.directory / name)

    def test_a_drill_bigger_than_its_hole_is_refused_and_never_drilled(self):
        # Every hole of the plate is too small for it, so ``holes: all`` has nothing left to drill.
        result = self._plan({"type": "drill", "diameter_mm": 8}, "big")
        self.assertEqual("fix", result.verdict["status"])
        self.assertEqual(["empty_operation"], [f["type"] for f in result.findings if f["severity"] == "error"])
        self.assertEqual([], _errors(result, "gouge"))

    def test_the_right_drill_is_not(self):
        result = self._plan({"type": "drill", "diameter_mm": 5}, "right")
        self.assertEqual([], _errors(result, "gouge"))



class StaleOutputs(unittest.TestCase):
    """A plan never leaves the last run's GLB or G-code standing beside a refusal, a crash or a smaller job."""

    @classmethod
    def setUpClass(cls):
        from tests.python.support.cam_fixtures import plate_step

        cls.root = class_directory(cls)
        cls.step = plate_step(cls.root)

    def setUp(self):
        import shutil
        import tempfile

        self.out = Path(tempfile.mkdtemp(prefix="out-", dir=self.root))
        self.addCleanup(shutil.rmtree, self.out, True)

    def plan(self, job):
        from cadgen import cam

        with quiet():
            return cam.plan(self.step, job=job, out_dir=self.out)

    def names(self) -> list[str]:
        return sorted(path.name for path in self.out.iterdir())

    def test_a_refused_job_leaves_nothing_of_the_last_run(self):
        self.assertTrue(self.plan(mill_job([{"op": "face", "tool": "T1"}])).ok)
        self.assertEqual(["plate.cam.glb", "plate.top.nc"], self.names())
        bad = mill_job([{"op": "face", "tool": "T1"}])
        bad["tolerence_mm"] = 0.01
        self.assertFalse(self.plan(bad).ok)
        self.assertEqual([], self.names())

    def test_a_crash_leaves_nothing_of_the_last_run(self):
        from unittest import mock

        self.assertTrue(self.plan(mill_job([{"op": "face", "tool": "T1"}])).ok)
        with mock.patch("cadgen._internal.cam.part.read_part", side_effect=RuntimeError("boom")):
            result = self.plan(mill_job([{"op": "face", "tool": "T1"}]))
        # A crash is a refusal that says it is cadgen's bug (law 10: never a traceback), and leaves nothing.
        self.assertFalse(result.ok)
        self.assertEqual("internal_error", result.findings[0]["type"])
        self.assertIn("RuntimeError: boom", result.findings[0]["summary"])
        self.assertEqual([], self.names())

    def test_a_setup_dropped_since_loses_its_file_and_only_cadgen_files_are_swept(self):
        # Stock under the plate too, so the bottom setup's facing has something to cut (one that cuts nothing is an
        # empty_operation error, and posts nothing).
        both = mill_job([], setups=[{"id": "top", "orientation": "+Z", "operations": [{"op": "face", "tool": "T1"}]},
                                    {"id": "bottom", "orientation": "-Z", "operations": [{"op": "face", "tool": "T1"}]}],
                        stock={"kind": "box", "margin_mm": [2, 2, 2, 2, 1, 1]})
        self.assertTrue(self.plan(both).ok)
        self.assertEqual(["plate.bottom.nc", "plate.cam.glb", "plate.top.nc"], self.names())
        (self.out / "plate.old.nc").write_text("(plate.step - setup old Top, 1 of 1)\n(Generated by cadgen 0.5 cam)\n", encoding="utf-8")
        (self.out / "plate.notes.nc").write_text("(my own notes)\n", encoding="utf-8")
        (self.out / "other.top.nc").write_text("(other.step - setup top Top, 1 of 1)\n(Generated by cadgen)\n", encoding="utf-8")
        self.assertTrue(self.plan(mill_job([{"op": "face", "tool": "T1"}])).ok)
        self.assertEqual(["other.top.nc", "plate.cam.glb", "plate.notes.nc", "plate.top.nc"], self.names())

    def test_a_failed_rename_midway_leaves_none_of_the_new_set(self):
        import os
        from unittest import mock

        real = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError("disk full")
            return real(src, dst)

        with mock.patch("cadgen._internal.cam.run.os.replace", side_effect=flaky):
            result = self.plan(mill_job([{"op": "face", "tool": "T1"}]))
        # A write that fails is a refusal that says so, with nothing of the new set left.
        self.assertFalse(result.ok)
        self.assertIn("disk full", result.findings[0]["summary"])
        self.assertEqual(2, len(calls))
        self.assertEqual([], self.names())

    def test_a_post_that_splits_by_tool_writes_one_file_per_tool(self):
        from unittest import mock

        from cadgen._internal.cam import posts
        from tests.python.support.cam_fixtures import read_glb

        real_get = posts.get_post

        class Split:
            split_by_tool = True

            def __init__(self, inner):
                self._inner = inner

            def __getattr__(self, name):
                return getattr(self._inner, name)

            def render_tool_files(self, program):
                text = self._inner.render(program)
                return [("T1", "(T1)\n" + text), ("T3", "(T3)\n" + text)]

        tools = [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 30},
                 {"id": "T3", "type": "flat", "diameter_mm": 10, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 30}]
        # A stub over a post with a tool changer, so the same job also posts as one file without it.
        job = mill_job([{"op": "face", "tool": "T3"}, {"op": "face", "tool": "T1"}], tools=tools,
                       machine={"kind": "mill", "post": "linuxcnc", "max_rpm": 24000})
        with mock.patch.object(posts, "get_post", lambda *a, **k: Split(real_get(*a, **k))):
            result = self.plan(job)
        self.assertTrue(result.ok)
        self.assertEqual(["plate.cam.glb", "plate.top.T1.ngc", "plate.top.T3.ngc"], self.names())
        self.assertEqual([("top", "T1", "plate.top.T1.ngc"), ("top", "T3", "plate.top.T3.ngc")],
                         [(p["setup"], p["tool"], Path(p["file"]).name) for p in result.posts])
        cam = read_glb(result.glb)[0]["scenes"][0]["extras"]["cam"]
        self.assertEqual(["T1", "T3"], [p["tool"] for p in cam["posts"]])
        self.assertEqual(["plate.top.T1.ngc", "plate.top.T3.ngc"], cam["setups"][0]["posts"])
        # Planned again with a post that does not split: the per-tool files go with the last run.
        self.assertTrue(self.plan(job).ok)
        self.assertEqual(["plate.cam.glb", "plate.top.ngc"], self.names())


class StockGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.python.support.cam_fixtures import plate_step
        from tests.python.support.cam_fixtures_cutting import bracket_dxf

        cls.directory = class_directory(cls)
        cls.step = plate_step(cls.directory)
        cls.dxf = bracket_dxf(cls.directory)

    def plan(self, document, job, name: str):
        from cadgen import cam

        with quiet():
            return cam.plan(document, job=job, out_dir=self.directory / name)

    def test_a_box_size_bigger_than_the_part_is_taken_and_a_smaller_one_refused(self):
        bigger = self.plan(self.step, mill_job([{"op": "face", "tool": "T1"}],
                                               stock={"kind": "box", "size_mm": [70, 50, 8]}), "bigger")
        self.assertTrue(bigger.ok)
        self.assertTrue(bigger.verdict)
        smaller = self.plan(self.step, mill_job([{"op": "face", "tool": "T1"}],
                                                stock={"kind": "box", "size_mm": [50, 50, 8]}), "smaller")
        self.assertFalse(smaller.ok)
        self.assertIn("smaller than the part", smaller.findings[0]["summary"])

    def test_a_drawing_is_cut_from_a_sheet_that_names_its_thickness(self):
        from tests.python.support.cam_fixtures_cutting import cut_job

        job = cut_job("plasma", thickness=6.0)
        self.assertTrue(self.plan(self.dxf, job, "six").ok)
        for stock, words in (({"kind": "sheet"}, "thickness_mm"), ({"kind": "box", "margin_mm": 5}, "from a sheet")):
            refused = self.plan(self.dxf, {**job, "stock": stock}, stock["kind"])
            self.assertFalse(refused.ok)
            self.assertIn(words, refused.findings[0]["summary"])


class DrawingReader(unittest.TestCase):
    """A DXF's blocks are cut where they are placed; annotation is counted; anything else is refused."""

    @classmethod
    def setUpClass(cls):
        cls.directory = class_directory(cls)

    def drawing(self, name: str, extra=None):
        import ezdxf

        document = ezdxf.new("R2010")
        document.header["$INSUNITS"] = 4
        square = document.blocks.new("SQ")
        square.add_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10)], close=True)
        outer = document.blocks.new("OUTER")
        outer.add_blockref("SQ", (100, 0))
        space = document.modelspace()
        space.add_blockref("SQ", (50, 0), dxfattribs={"rotation": 90, "xscale": 2})
        space.add_blockref("OUTER", (0, 100))
        space.add_text("PART 7", dxfattribs={"insert": (0, -10), "height": 3})
        if extra is not None:
            extra(space)
        path = self.directory / f"{name}.dxf"
        document.saveas(path)
        return path

    def test_blocks_are_expanded_with_their_placement_and_text_is_counted(self):
        from cadgen._internal.cam.part import read_dxf_drawing

        profiles, skipped = read_dxf_drawing(self.drawing("blocks"))
        bounds = sorted(tuple(round(v, 3) for v in p.bounds) for p in profiles)
        self.assertEqual([(40.0, 0.0, 50.0, 20.0), (100.0, 100.0, 110.0, 110.0)], bounds)
        self.assertEqual({"TEXT": 1}, skipped)

    def test_the_plan_says_what_it_skipped(self):
        from cadgen import cam
        from tests.python.support.cam_fixtures_cutting import cut_job

        with quiet():
            result = cam.plan(self.drawing("said"), job=cut_job("laser", thickness=2.0),
                              out_dir=self.directory / "said")
        self.assertTrue(result.ok)
        self.assertTrue(any("1 TEXT skipped" in w for w in result.warnings), result.warnings)

    def test_an_entity_that_is_not_a_curve_is_refused_by_handle(self):
        from cadgen._internal.cam.job_errors import CamJobError
        from cadgen._internal.cam.part import read_dxf_drawing

        handles = []
        path = self.drawing("point", lambda space: handles.append(space.add_point((5, 5)).dxf.handle))
        with self.assertRaises(CamJobError) as caught:
            read_dxf_drawing(path)
        self.assertIn(f"POINT {handles[0]}", str(caught.exception))



class ChecksSayWhatTheyDidNotJudge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.python.support.cam_fixtures import plate_step

        cls.directory = class_directory(cls)
        cls.step = plate_step(cls.directory)

    def plan(self, job, name: str):
        from cadgen import cam

        with quiet():
            return cam.plan(self.step, job=job, out_dir=self.directory / name)

    def test_a_side_setup_the_heightfield_cannot_simulate_is_a_warning_and_skipped_entries(self):
        from tests.python.support.cam_fixtures import read_glb

        job = mill_job([], setups=[{"id": "top", "orientation": "+Z", "operations": [{"op": "face", "tool": "T1"}]},
                                   {"id": "side", "orientation": "+X", "operations": [{"op": "face", "tool": "T1"}]}])
        result = self.plan(job, "side")
        self.assertTrue(result.ok)
        (warning,) = [f for f in result.findings if f["type"] == "setup_not_simulated"]
        self.assertEqual("warning", warning["severity"])
        self.assertIn("'side'", warning["summary"])
        self.assertIn("rapid_into_stock", warning["items"][0]["checks"])
        checks = read_glb(result.glb)[0]["scenes"][0]["extras"]["cam"]["checks"]
        skipped = {(entry["check"], entry.get("setup")) for entry in checks["skipped"]}
        self.assertIn(("rapid_into_stock", "side"), skipped)
        self.assertNotIn(("rapid_into_stock", "top"), skipped)
        self.assertIn("rapid_into_stock", checks["ran"])                  # it judged the top setup

    def test_a_turned_section_the_gouge_check_cannot_read_is_said_and_anything_else_raises(self):
        from types import SimpleNamespace
        from unittest import mock

        from cadgen._internal.cam.checks._turning import gouges
        from cadgen._internal.cam.job_errors import CamJobError
        from cadgen._internal.cam.tools import parse_tool

        op = SimpleNamespace(tool=parse_tool({"id": "T1", "type": "turn"}, 0), operation=SimpleNamespace(
            family="Turning"), start=0, end=4, meta={}, setup="lathe", index=0, summary="Rough turn with T1")
        ctx = SimpleNamespace(job=SimpleNamespace(machine=SimpleNamespace(kind="lathe")), part=None,
                              tolerance_mm=0.01, ops=[op], setup_plan=lambda _: SimpleNamespace(wcs=None))
        with mock.patch("cadgen._internal.cam.turn_profile.read_profile", side_effect=CamJobError("not round")):
            (found,) = gouges(ctx)
        self.assertEqual(("gouge", "warning", "not_judged"), (found["check"], found["severity"], found["type"]))
        self.assertIn("not round", found["summary"])
        with mock.patch("cadgen._internal.cam.turn_profile.read_profile", side_effect=RuntimeError("bug")):
            with self.assertRaises(RuntimeError):
                gouges(ctx)

    def test_a_shank_the_stock_replay_cannot_judge_is_said(self):
        tools = [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 30,
                  "shank_diameter_mm": 8}]
        job = mill_job([{"op": "face", "tool": "T1"}], tools=tools,
                       machine={"kind": "mill4", "post": "linuxcnc", "max_rpm": 24000})
        result = self.plan(job, "mill4")
        self.assertTrue(result.ok)
        (note,) = [f for f in result.findings if f["check"] == "holder_collision" and f["type"] == "not_judged"]
        self.assertEqual("info", note["severity"])
        self.assertEqual([{"setup": "top", "operation": 0}], note["items"])

    def test_material_left_is_judged_by_the_last_operation_over_each_place(self):
        # A roughing face leaves 0.5; a ball finish with leave 0 runs after it at a wide stepover and leaves
        # scallops about 0.3 high. The finish's 0 judges them, not the roughing's 0.5.
        tools = [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20, "stickout_mm": 30},
                 {"id": "T4", "type": "ball", "diameter_mm": 6, "flutes": 2, "flute_length_mm": 20, "stickout_mm": 30}]
        rough = {"op": "face", "tool": "T1", "stock_to_leave_mm": 0.5}
        finished = self.plan(mill_job([rough, {"op": "parallel", "tool": "T4", "stepover": 0.44}], tools=tools),
                             "finished")
        (left,) = [f for f in finished.findings if f["check"] == "material_left"]
        self.assertGreater(left["items"][0]["max_mm"], 0.1)
        self.assertLess(left["items"][0]["max_mm"], 0.5)
        # The roughing alone, its allowance asked for: not a finding.
        alone = self.plan(mill_job([rough], tools=tools), "alone")
        self.assertEqual([], [f for f in alone.findings if f["check"] == "material_left"])



class SharedKeysAreRead(unittest.TestCase):
    """Law 9: a shared key an operation never reads is refused, never accepted and ignored."""

    def test_every_operation_refuses_each_shared_key_it_does_not_read(self):
        from cadgen._internal.cam.job import OpSpec
        from cadgen._internal.cam.job_errors import CamJobError
        from cadgen._internal.cam.operations import OPERATION_NAMES, available, get_operation
        from cadgen._internal.cam.operations.base import SHARED

        refused = 0
        for name in OPERATION_NAMES:
            if not available(name):
                continue
            operation = get_operation(name, "op")
            for of in (("rough", "parallel", "waterline") if name == "rest" else (None,)):
                extra = {"of": of} if of else {}
                allowed = operation.shared_keys(OpSpec(op=name, where="op", index=0, extra=extra))
                for key in SHARED:
                    if key in allowed:
                        continue
                    spec = OpSpec(op=name, where="op", index=0, tool="T1", extra=extra, given=frozenset({key}))
                    with self.subTest(op=name, of=of, key=key):
                        with self.assertRaises(CamJobError) as caught:
                            operation.parse(spec, None)
                        self.assertIn(f"does not use {key}", str(caught.exception))
                        refused += 1
        self.assertGreater(refused, 30)

    def test_a_stock_to_leave_on_a_drill_is_refused_in_the_plan(self):
        from cadgen import cam
        from tests.python.support.cam_fixtures import plate_step

        directory = class_directory(type(self))
        job = mill_job([{"op": "drill", "tool": "T2", "points": [[0, 0]], "depth_mm": 3, "stock_to_leave_mm": 0.2}])
        with quiet():
            result = cam.plan(plate_step(directory), job=job, out_dir=directory)
        self.assertFalse(result.ok)
        self.assertIn("a drill does not use stock_to_leave_mm", result.findings[0]["summary"])



class StockMeshSize(unittest.TestCase):
    """The simulated stock in the GLB is merged into planar blocks: hundreds of kilobytes, not megabytes."""

    def test_a_pocketed_block_s_stock_is_small_and_the_same_solid(self):
        import numpy as np

        from cadgen import cam
        from cadgen._internal.cam.stock_heightfield import _block_triangles
        from tests.python.support.cam_fixtures import block_step, floor_ref, read_glb

        directory = class_directory(type(self))
        step = block_step(directory)
        features = cam.features(step)
        job = mill_job([{"op": "face", "tool": "T1"},
                        {"op": "pocket", "tool": "T1", "faces": [floor_ref(features, 17.0)]},
                        {"op": "pocket", "tool": "T1", "faces": [floor_ref(features, 11.0)]}])
        with quiet():
            result = cam.plan(step, job=job, out_dir=directory)
        document, blob = read_glb(result.glb)
        stock = next(m for m in document["meshes"] if m["name"] == "stock")["primitives"][0]
        size = sum(document["bufferViews"][document["accessors"][index]["bufferView"]]["byteLength"]
                   for index in (*stock["attributes"].values(), stock["indices"]))
        self.assertLess(size, 400_000)
        # A flat grid is one block; a bump keeps its vertex and the cells round it, the rest still merges.
        heights = np.full((9, 9), 3.0)
        quad = np.ones((8, 8), dtype=bool)
        self.assertEqual(2, len(_block_triangles(heights, quad, 9)))
        heights[4, 4] = 3.5
        merged = _block_triangles(heights, quad, 9)
        self.assertLess(len(merged), 2 * 64)
        self.assertEqual({4 * 9 + 4}, {4 * 9 + 4} & set(merged.ravel()))


if __name__ == "__main__":
    unittest.main()
