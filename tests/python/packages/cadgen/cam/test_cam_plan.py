"""``cadgen cam plan`` end to end, through the FreeCAD installed here: the block planned, posted and drawn; a face
under a bridge refused with no G-code; a setup turned over; GRBL's program split by tool; a bore and a slot cut by an
inside profile of their walls; a floor the tool cannot enter, and a hole named by any of its faces; a failure that
leaves the earlier files as they were."""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.cam_fixtures import (BLOCK, HOLE_BLOCK, PLATE, block_step, bridge_step, class_directory,
                                               floor_ref, glb_cam, hole_block_step, mill_job, needs_freecad,
                                               plate_step, quiet, read_glb)


#: Tools long enough to profile the block's 26 mm, stock top to bottom.
LONG_FLUTES = [{"id": "T1", "type": "flat", "number": 1, "diameter_mm": 6, "flutes": 3, "flute_length_mm": 30,
                "stickout_mm": 40, "shank_diameter_mm": 6},
               {"id": "T2", "type": "drill", "number": 2, "diameter_mm": 5, "flute_length_mm": 50, "stickout_mm": 60,
                "point_angle": 118}]


def plan(step: Path, job: dict, **options):
    from cadgen import cam

    with quiet():
        return cam.plan(step, job=job, **options)


def plan_moves(step: Path, job: dict, **options):
    """The plan, and the moves FreeCAD planned for each setup (setup coordinates), as the checks read them."""
    from cadgen._internal.cam import toolpath

    seen = []
    real = toolpath.read

    def read(*args):
        seen.append(real(*args))
        return seen[-1]

    with mock.patch.object(toolpath, "read", read):
        return plan(step, job, **options), seen


def cuts(moves, op: int):
    """The points an operation's cutting moves end at."""
    return moves.points[(moves.op == op) & ~moves.rapid]


def z_words(text: str) -> list[float]:
    return [float(z) for z in re.findall(r"\bZ(-?\d+(?:\.\d+)?)", text)]


@needs_freecad
class Block(unittest.TestCase):
    """Face, pocket (around the island), adaptive (the lower step), profile and drill: one LinuxCNC program."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.step = block_step(class_directory(cls))
        features = cam.features(cls.step)
        holes = [hole["faces"][0] for hole in features.holes]
        cls.job = mill_job(tools=LONG_FLUTES, operations=[
            {"op": "face", "tool": "T1"},
            {"op": "pocket", "tool": "T1", "faces": [floor_ref(features, 17.0)]},
            {"op": "adaptive", "tool": "T1", "faces": [floor_ref(features, 11.0)]},
            {"op": "profile", "tool": "T1", "through_mm": 0.5},
            {"op": "drill", "tool": "T2", "faces": holes},
        ])
        cls.result = plan(cls.step, cls.job)
        cls.cam = glb_cam(cls.result.glb) if cls.result.glb else None

    def test_it_is_ready_to_cut_and_posts_one_program(self):
        self.assertTrue(self.result.ok, self.result.findings)
        self.assertEqual("ready", self.result.verdict["status"], self.result.findings)
        (post,) = self.result.posts
        self.assertEqual(("top", "linuxcnc", None), (post["setup"], post["post"], post["tool"]))
        self.assertEqual("block.top.ngc", Path(post["file"]).name)
        self.assertTrue(self.cam["planner"].startswith("freecad 1."))

    def test_the_program_is_in_work_coordinates_and_cuts_at_real_feeds(self):
        text = Path(self.result.posts[0]["file"]).read_text(encoding="utf-8")
        depth = BLOCK["size"][2]
        zs = z_words(text)
        self.assertAlmostEqual(-(depth + 1.0 + 0.5), min(z for z in zs if z > -(depth + 3)), places=3)  # profile
        self.assertGreater(max(zs), 0.0)                                       # clearance above the stock top
        self.assertIn("G54", text)
        speeds = {float(s) for s in re.findall(r"\bS(\d+(?:\.\d+)?)", text)}
        self.assertTrue(speeds and all(s > 1000 for s in speeds), speeds)
        feeds = {float(f) for f in re.findall(r"\bF(\d+(?:\.\d+)?)", text)}
        self.assertTrue(feeds and min(feeds) > 10, feeds)                      # never FreeCAD's 0 mm/min
        self.assertIn("T2", text)                                             # the tool change to the drill

    def test_each_operation_is_drawn_and_timed_in_order(self):
        ops = self.cam["setups"][0]["operations"]
        self.assertEqual(["face", "pocket", "adaptive", "profile", "drill"], [op["op"] for op in ops])
        times = [(op["t0"], op["t1"]) for op in ops]
        self.assertTrue(all(t0 < t1 for t0, t1 in times), times)
        self.assertTrue(all(a[1] <= b[0] + 1e-6 for a, b in zip(times, times[1:])), times)
        document, blob = read_glb(self.result.glb)
        kinds = {node["extras"].get("kind") for node in document["nodes"] if "extras" in node}
        self.assertTrue({"part", "stock", "feed", "rapid"} <= kinds, kinds)

    def test_the_drill_goes_through_by_its_point_and_the_break_through(self):
        drill = self.job["tools"][1]
        import math

        tip = drill["diameter_mm"] / 2 / math.tan(math.radians(59))
        expected = -(BLOCK["size"][2] + 1.0) - 1.0 - tip
        text = Path(self.result.posts[0]["file"]).read_text(encoding="utf-8")
        self.assertIn(round(expected, 3), [round(z, 3) for z in z_words(text)])


@needs_freecad
class Bridge(unittest.TestCase):
    """A floor a quarter under a bar: refused before FreeCAD plans it, and the earlier program goes."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = bridge_step(cls.directory)
        cls.floors = {f["kind"]: f["ref"] for f in cam.features(cls.step).floors}

    def test_a_ready_plan_then_one_that_is_not_leaves_no_program(self):
        first = plan(self.step, mill_job([{"op": "face", "tool": "T1"}]))
        self.assertEqual("ready", first.verdict["status"], first.findings)
        program = Path(first.posts[0]["file"])
        self.assertTrue(program.is_file())
        second = plan(self.step, mill_job([{"op": "face", "tool": "T1"},
                                           {"op": "pocket", "tool": "T1", "faces": [self.floors["floor"]]}]))
        self.assertTrue(second.ok)
        self.assertEqual("fix", second.verdict["status"])
        self.assertEqual((), second.posts)
        self.assertFalse(program.exists())                 # no "ready" program beside a plan that is not
        (error,) = [f for f in second.findings if f["severity"] == "error"]
        self.assertEqual(("reach", "unreachable"), (error["check"], error["type"]))
        cam = glb_cam(second.glb)
        self.assertEqual("fix", cam["verdict"]["status"])
        self.assertIn("G-code not written", cam["verdict"]["gcode"])

    def test_the_bottom_turned_over_is_faced_from_its_own_side(self):
        result = plan(self.step, mill_job([], setups=[
            {"id": "bottom", "orientation": "-Z", "operations": [{"op": "face", "tool": "T1"}]}]))
        self.assertEqual("ready", result.verdict["status"], result.findings)
        (op,) = result.operations
        self.assertEqual([self.floors["bottom"]], op["faces"])
        setup = glb_cam(result.glb)["setups"][0]
        self.assertEqual([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]], setup["matrix"])
        self.assertEqual(0.0, setup["origin_part_mm"][2])  # the work zero is the stock's face toward the tool


@needs_freecad
class Grbl(unittest.TestCase):
    def test_a_setup_with_two_tools_posts_one_file_per_tool(self):
        from cadgen import cam

        directory = class_directory(type(self))
        step = block_step(directory)
        holes = [hole["faces"][0] for hole in cam.features(step).holes]
        job = mill_job([{"op": "face", "tool": "T1"}, {"op": "drill", "tool": "T2", "faces": holes}],
                       machine={"post": "grbl", "max_rpm": 24000})
        result = plan(step, job)
        self.assertEqual("ready", result.verdict["status"], result.findings)
        self.assertEqual([("block.top.1-T1.nc", "T1"), ("block.top.2-T2.nc", "T2")],
                         [(Path(p["file"]).name, p["tool"]) for p in result.posts])
        first, second = (Path(p["file"]).read_text(encoding="utf-8") for p in result.posts)
        self.assertNotIn("G81", re.sub(r"\(.*?\)", "", second))   # GRBL has no drilling cycle: written out as moves

    def test_every_other_post_posts_what_cadgen_set_in_the_setups_work_offset(self):
        # Each program read back (S, F, Q, and the work offset of every move) and found clean; Fanuc's once failed on
        # the work offset's object, and once cut in G54 after its tool change whatever the job's offset. The part's
        # name, as a download names a copy, once nested a comment in the header cadgen writes; the job's name heads it.
        step = block_step(class_directory(type(self)), name="block (1)")
        for post in ("mach3", "fanuc", "centroid", "uccnc", "smoothie"):
            with self.subTest(post=post):
                job = mill_job([{"op": "face", "tool": "T1"}], machine={"post": post, "max_rpm": 24000, "work_offset": "G55"})
                result = plan(step, {**job, "name": "bracket (rev B)"})
                self.assertEqual("ready", result.verdict.get("status"), result.findings)
                text = Path(result.posts[0]["file"]).read_text(encoding="utf-8")
                self.assertTrue(text.startswith("(cadgen cam: bracket [rev B], from block [1].step, setup top,"), text[:80])
                nested = [line for line in text.splitlines() if not re.fullmatch(r"[^()]*(?:\([^()]*\)[^()]*)*", line)]
                self.assertEqual([], nested)
                self.assertIn("G55", text)
                if post == "fanuc":
                    self.assertIn("G43 G55", text)              # its tool length offset line, after the tool change
                    self.assertNotIn("G43 G54", text)

    def test_a_spindle_the_machine_holds_is_one_warning_a_tool(self):
        step = block_step(class_directory(type(self)))
        result = plan(step, mill_job([{"op": "face", "tool": "T1"},
                                      {"op": "profile", "tool": "T1", "through_mm": 0.5}],
                                     tools=LONG_FLUTES, machine={"post": "grbl", "max_rpm": 6000}))
        (clamped,) = [f for f in result.findings if f["type"] == "clamped"]
        self.assertTrue(clamped["summary"].startswith("T1 "), clamped)
        self.assertEqual([{"operation": 0}, {"operation": 1}], clamped["items"])


#: A 6 mm end mill for the bore and the pocket, a 3 mm one for the slot, a 6 mm drill.
PLATE_TOOLS = [{"id": "T1", "type": "flat", "number": 1, "diameter_mm": 6, "flutes": 3, "flute_length_mm": 20,
                "stickout_mm": 30, "shank_diameter_mm": 6},
               {"id": "T3", "type": "flat", "number": 3, "diameter_mm": 3, "flutes": 2, "flute_length_mm": 15,
                "stickout_mm": 25, "shank_diameter_mm": 3},
               {"id": "T2", "type": "drill", "number": 2, "diameter_mm": 6, "flute_length_mm": 50, "stickout_mm": 60,
                "point_angle": 118}]


@needs_freecad
class Plate(unittest.TestCase):
    """A Ø22.2 bore and a 5.5 mm slot, too wide to drill, cut out by an inside profile naming their walls; a pocket
    floor, and a blind hole's floor no 6 mm tool enters. The stock's top is the work zero, 1 mm over the part's."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.step = plate_step(class_directory(cls))
        features = cam.features(cls.step)
        cls.bore = next(h for h in features.holes if abs(h["diameter_mm"] - PLATE["bore"]["diameter"]) < 1e-3)
        cls.blind = next(h for h in features.holes if abs(h["diameter_mm"] - PLATE["blind"]["diameter"]) < 1e-3)
        sx, sy = PLATE["slot"]["center"]
        reach = PLATE["slot"]["length"] / 2 + PLATE["slot"]["width"]
        cls.slot = [f["ref"] for f in features.faces if abs(f["center_mm"][0] - sx) < reach
                    and abs(f["center_mm"][1] - sy) < PLATE["slot"]["width"] and abs(f.get("normal", [0, 0, 0])[2]) < 0.5]
        in_holes = {ref for hole in features.holes for ref in hole["faces"]}
        floor = next(f for f in features.floors if f["kind"] == "floor" and f["ref"] not in in_holes)
        cls.pocket, cls.pocket_walls = floor["ref"], floor["pocket"]["walls"]
        cls.top = next(f["ref"] for f in features.floors if f["kind"] == "top")
        cls.top_z = -1.0                                    # the part's top under the 1 mm margin
        cls.bottom_z = cls.top_z - PLATE["size"][2]

    def job(self, operations):
        return mill_job(operations, tools=PLATE_TOOLS, stock={"margin_mm": [2, 2, 1]})

    def test_an_inside_profile_cuts_a_through_bore_and_a_slot_by_their_walls(self):
        import numpy as np

        self.assertEqual(4, len(self.slot))                  # two flat walls and two round ends
        result, (moves,) = plan_moves(self.step, self.job([
            {"op": "profile", "tool": "T1", "side": "inside", "faces": [self.bore["faces"][0]], "through_mm": 0.5},
            {"op": "profile", "tool": "T3", "side": "inside", "faces": self.slot, "through_mm": 0.5}]))
        self.assertEqual("ready", result.verdict["status"], result.findings)
        self.assertEqual(1, len(result.posts))
        bore = cuts(moves, 0)
        bore = bore[bore[:, 2] < self.top_z]
        radius = PLATE["bore"]["diameter"] / 2 - 3.0               # the 6 mm tool's centre, its radius off the wall
        self.assertTrue(np.allclose(np.hypot(bore[:, 0], bore[:, 1]), radius, atol=0.02))
        self.assertAlmostEqual(self.bottom_z - 0.5, float(bore[:, 2].min()), places=3)
        slot = cuts(moves, 1)
        slot = slot[slot[:, 2] < self.top_z]
        half = PLATE["slot"]["width"] / 2 - 1.5
        y = PLATE["slot"]["center"][1]
        self.assertAlmostEqual(y - half, float(slot[:, 1].min()), places=2)
        self.assertAlmostEqual(y + half, float(slot[:, 1].max()), places=2)
        self.assertAlmostEqual(self.bottom_z - 0.5, float(slot[:, 2].min()), places=3)

    def test_each_pass_steps_down_as_far_as_the_job_says_not_the_tools_diameter(self):
        import numpy as np

        result, (moves,) = plan_moves(self.step, self.job([
            {"op": "profile", "tool": "T1", "through_mm": 0.5, "stepdown_mm": 2}]))
        self.assertEqual("ready", result.verdict["status"], result.findings)
        levels = np.unique(np.round(cuts(moves, 0)[:, 2], 3))
        self.assertAlmostEqual(self.bottom_z - 0.5, float(levels.min()), places=3)
        self.assertLessEqual(float(np.diff(levels).max()), 2.0 + 1e-3, levels)

    def test_a_drill_pecks_as_far_as_the_job_says(self):
        result = plan(self.step, self.job([{"op": "drill", "tool": "T2", "faces": [self.blind["faces"][0]],
                                            "peck_mm": 1.5}]))
        text = Path(result.posts[0]["file"]).read_text(encoding="utf-8")
        self.assertEqual({"1.500"}, set(re.findall(r"G83 .*\bQ(\d+\.\d+)", text)))

    def test_an_inside_profile_of_a_flat_face_is_refused_naming_its_walls(self):
        # Inside the top face, FreeCAD traces the outline through the stock over it and cuts nothing of the part.
        result = plan(self.step, self.job([{"op": "profile", "tool": "T3", "side": "inside", "faces": [self.top]}]))
        self.assertEqual("fix", result.verdict["status"])
        self.assertEqual((), result.posts)
        (error,) = [f for f in result.findings if f["severity"] == "error"]
        self.assertEqual(("reach", "not_facing"), (error["check"], error["type"]))
        self.assertIn("an inside profile runs along walls", error["summary"])
        for ref in [self.bore["faces"][0], *self.slot, *self.pocket_walls, self.blind["faces"][0]]:
            self.assertIn(ref, error["summary"])
        outside = plan(self.step, self.job([{"op": "profile", "tool": "T1", "faces": [self.top], "through_mm": 0.5}]))
        self.assertEqual("ready", outside.verdict["status"], outside.findings)

    def test_an_inside_profile_of_a_blind_pocket_stops_at_its_floor(self):
        result, (moves,) = plan_moves(self.step, self.job([
            {"op": "profile", "tool": "T3", "side": "inside", "faces": self.pocket_walls, "through_mm": 0.5}]))
        self.assertEqual("ready", result.verdict["status"], result.findings)
        floor = self.top_z - (PLATE["size"][2] - PLATE["pocket"]["floor_z"])
        self.assertAlmostEqual(floor, float(cuts(moves, 0)[:, 2].min()), places=3)

    def test_an_inside_profile_of_a_pockets_floor_cuts_its_walls(self):
        # One pocket's floor stands for its four walls: the plan names them, and cuts them down to the floor.
        import numpy as np

        floor = self.top_z - (PLATE["size"][2] - PLATE["pocket"]["floor_z"])
        named, (by_walls,) = plan_moves(self.step, self.job([
            {"op": "profile", "tool": "T3", "side": "inside", "faces": self.pocket_walls, "through_mm": 0.5}]))
        for faces in ([self.pocket], [self.pocket, *self.pocket_walls[:2]]):    # with its own walls: cut once
            result, (moves,) = plan_moves(self.step, self.job([
                {"op": "profile", "tool": "T3", "side": "inside", "faces": faces, "through_mm": 0.5}]))
            self.assertEqual("ready", result.verdict["status"], result.findings)
            (op,) = result.operations
            self.assertEqual(4, len(self.pocket_walls))
            self.assertEqual(sorted(self.pocket_walls), sorted(op["faces"]))
            self.assertIn(f"for pocket floor {self.pocket}: its walls {', '.join(self.pocket_walls)}", op["summary"])
            self.assertAlmostEqual(floor, float(cuts(moves, 0)[:, 2].min()), places=3)
            self.assertEqual(len(cuts(by_walls, 0)), len(cuts(moves, 0)))
            np.testing.assert_allclose(cuts(by_walls, 0), cuts(moves, 0), atol=1e-6)

    def test_a_floor_the_tool_cannot_enter_is_uncut_and_no_g_code_is_written(self):
        floor = self.blind["faces"][-1]                      # the Ø6 hole's flat floor, at the pocket's height
        result = plan(self.step, self.job([{"op": "pocket", "tool": "T1", "faces": [self.pocket, floor]}]))
        self.assertEqual("fix", result.verdict["status"])
        self.assertEqual((), result.posts)
        (error,) = [f for f in result.findings if f["severity"] == "error"]
        self.assertEqual(("coverage", "uncut", floor), (error["check"], error["type"], error["items"][0]["face"]))

    def test_a_flat_floored_hole_drilled_with_a_pointed_drill_says_what_it_leaves(self):
        result = plan(self.step, self.job([{"op": "drill", "tool": "T2", "faces": [self.blind["faces"][0]]}]))
        self.assertEqual("ready", result.verdict["status"], result.findings)
        (found,) = result.findings
        self.assertEqual(("drill_point", "warning"), (found["type"], found["severity"]))
        self.assertIn("drawn with a flat floor: its bottom 1.80 mm is left a cone", found["summary"])


@needs_freecad
class HoleBlock(unittest.TestCase):
    """A hole is named by any of its faces, and drilled as its wall; a drawn point flatter than the drill's says so."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.step = hole_block_step(class_directory(cls))
        with quiet():
            features = cam.features(cls.step)
        surface = {face["ref"]: face["surface"] for face in features.faces}
        at = {(round(h["center_mm"][0], 3), round(h["center_mm"][1], 3)): h for h in features.holes}
        cls.shoulder = next(ref for ref in at[HOLE_BLOCK["counterbore"]["center"]]["faces"] if surface[ref] == "plane")
        cls.countersunk = at[HOLE_BLOCK["countersink"]["center"]]["faces"][0]
        cls.pointed = at[HOLE_BLOCK["pointed"]["center"]]

    def test_a_counterbores_shoulder_drills_its_hole(self):
        result = plan(self.step, mill_job([{"op": "drill", "tool": "T2", "faces": [self.shoulder, self.countersunk]}]))
        self.assertEqual("ready", result.verdict["status"], result.findings)
        text = Path(result.posts[0]["file"]).read_text(encoding="utf-8")
        drilled = sorted((float(x), float(y)) for x, y in re.findall(r"G8[123] X(-?[\d.]+) Y(-?[\d.]+)", text))
        self.assertEqual(sorted([HOLE_BLOCK["counterbore"]["center"], HOLE_BLOCK["countersink"]["center"]]), drilled)

    def test_a_drill_point_longer_than_the_drawn_one_is_a_warning_with_how_much(self):
        import math

        tools = [{"id": "T2", "type": "drill", "number": 2, "diameter_mm": 6, "flute_length_mm": 50,
                  "stickout_mm": 60, "point_angle": 118}]
        result = plan(self.step, mill_job([{"op": "drill", "tool": "T2", "faces": [self.pointed["faces"][0]]}],
                                          tools=tools))
        self.assertEqual("ready", result.verdict["status"], result.findings)
        (found,) = result.findings
        short = 3.0 / math.tan(math.radians(59)) - 3.0 / math.tan(math.radians(HOLE_BLOCK["pointed"]["point_angle"] / 2))
        self.assertEqual("drill_point", found["type"])
        self.assertIn(f"its bottom {short:.2f} mm is left a cone", found["summary"])


class Refused(unittest.TestCase):
    def test_no_freecad_is_refused_with_how_to_install_it_and_writes_nothing(self):
        from cadgen._internal.cam import freecad

        directory = class_directory(type(self))
        step = block_step(directory)
        with mock.patch.dict(os.environ, {freecad.FREECAD_ENV: str(directory / "no-freecad")}):
            result = plan(step, mill_job([{"op": "face", "tool": "T1"}]))
        self.assertFalse(result.ok)
        (found,) = result.findings
        self.assertEqual(("job", "freecad"), (found["check"], found["type"]))
        self.assertIn("install FreeCAD 1.1 or newer", found["summary"])
        self.assertEqual(["block.step"], sorted(p.name for p in directory.iterdir()))


@needs_freecad
class FailedWrite(unittest.TestCase):
    def test_a_write_that_fails_leaves_the_earlier_files_byte_for_byte(self):
        directory = class_directory(type(self))
        step = block_step(directory)
        job = mill_job([{"op": "face", "tool": "T1"}], tools=LONG_FLUTES)
        first = plan(step, job)
        self.assertEqual("ready", first.verdict["status"], first.findings)
        before = {path.name: path.read_bytes() for path in directory.iterdir()}
        job["setups"][0]["operations"].append({"op": "profile", "tool": "T1"})
        real = __import__("cadgen._internal.cam.run", fromlist=["replace_atomic"]).replace_atomic
        calls = []

        def second_fails(tmp, final):
            calls.append(final)
            if len(calls) == 2:
                raise OSError(28, "No space left on device")
            real(tmp, final)

        with mock.patch("cadgen._internal.cam.run.replace_atomic", second_fails):
            result = plan(step, job)
        self.assertFalse(result.ok)
        self.assertIn("No space left on device", result.findings[0]["summary"])
        # The GLB went into place, the program failed, and the earlier GLB was put back.
        self.assertEqual([".glb", ".ngc", ".glb"], [path.suffix for path in calls])
        after = {path.name: path.read_bytes() for path in directory.iterdir()}
        self.assertEqual(before, after)                    # every earlier file back, no temporary left


if __name__ == "__main__":
    unittest.main()


class EarlierPosts(unittest.TestCase):
    def test_only_a_program_named_as_a_plan_names_one_is_taken_for_an_earlier_post(self):
        # An earlier GLB's list of posts is a file the person can open and edit: a name in it that is not a
        # program's is never deleted beside the part.
        from cadgen._internal.cam import run

        glb = class_directory(type(self)) / "bracket.cam.glb"
        glb.write_bytes(b"")
        listed = {"posts": [{"file": name} for name in ("bracket.top.ngc", "bracket.top.1-T1.nc", "bracket.step",
                                                        "bracket.cam.json", "../bracket.top.nc", "other.top.nc")]}
        with mock.patch.object(run, "_glb_cam", return_value=listed):
            found = [path.name for path in run._previous_posts(glb, "bracket")]
        self.assertEqual(["bracket.top.ngc", "bracket.top.1-T1.nc"], found)
