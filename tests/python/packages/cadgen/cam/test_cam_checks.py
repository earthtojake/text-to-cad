"""The checks cadgen stands behind, on paths written by hand (no FreeCAD): a face the tool cannot see is refused
before planning, and a move into the part, a rapid through the stock, an operation that cuts nothing or a face it
names and never reaches after."""

from __future__ import annotations

import math
import re
import unittest

from tests.python.support.cam_fixtures import (BLOCK, BRIDGE, PLATE, TSLOT, block_step, bridge_step, class_directory,
                                               floor_ref, mill_job, plate_step, tslot_step)

from cadgen._internal.cam import checks
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.toolpath import Moves


def moves(points, rapid, op=0):
    import numpy as np

    return Moves(points=np.asarray(points, dtype=float), rapid=np.asarray(rapid, dtype=bool),
                 op=np.full(len(points), op, dtype=np.int64), t=np.arange(len(points), dtype=float))


class Reach(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam
        from cadgen._internal.cam.part import read_part

        directory = class_directory(cls)
        cls.part = read_part(bridge_step(directory))
        cls.floors = {f["kind"]: f["ref"] for f in cam.features(cls.part.document).floors}

    def reach(self, op_raw, tool="T1"):
        job = parse_job(mill_job([op_raw]))
        (op,) = job.setups[0].operations
        faces = [self.part.face(ref) for ref in op.faces]
        top = float(self.part.bbox[1][2]) + 1.0
        return checks.reach(op, faces, {}, (self.part.vertices, self.part.triangles), self.part.face_of_triangle,
                            job.tools[tool], top, min(f.center_mm[2] for f in faces))

    def test_a_floor_partly_under_a_bridge_is_refused_with_how_much(self):
        (found,) = self.reach({"op": "pocket", "tool": "T1", "faces": [self.floors["floor"]]})
        self.assertEqual(("reach", "error", "unreachable"), (found["check"], found["severity"], found["type"]))
        import re

        share = BRIDGE["bar"] / BRIDGE["pocket"][0]                 # the bar is 8 mm of the pocket's 30
        said = float(re.search(r"(\d+)% of", found["summary"]).group(1)) / 100
        self.assertAlmostEqual(share, said, delta=0.03)
        x = found["items"][0]["at"][0]
        self.assertLessEqual(abs(x), BRIDGE["bar"] / 2)          # it points under the bar

    def test_the_top_is_in_reach_and_the_underside_does_not_face_the_tool(self):
        self.assertEqual([], self.reach({"op": "face", "tool": "T1", "faces": [self.floors["top"]]}))
        (found,) = self.reach({"op": "pocket", "tool": "T1", "faces": [self.floors["underside"]]})
        self.assertEqual("not_facing", found["type"])

    def test_a_cut_deeper_than_the_flutes(self):
        job = mill_job([{"op": "pocket", "tool": "T1", "faces": [self.floors["floor"]]}],
                       tools=[{"id": "T1", "type": "flat", "number": 1, "diameter_mm": 6, "flutes": 3,
                               "flute_length_mm": 8, "stickout_mm": 15, "shank_diameter_mm": 6}])
        (op,) = parse_job(job).setups[0].operations
        found = checks.reach(op, [], {}, (self.part.vertices, self.part.triangles), self.part.face_of_triangle,
                             parse_job(job).tools["T1"], 21.0, 8.0)
        self.assertEqual(["too_deep"], [f["type"] for f in found])
        self.assertIn("13.00 mm below the stock top, past T1's 8 mm of flutes", found[0]["summary"])


class WallReach(unittest.TestCase):
    """A wall is judged from just off it, along its outward normal: a slot's walls are in reach from above, and the
    walls of a T-slot's wide bottom, under the narrow neck's lips, are not."""

    @classmethod
    def setUpClass(cls):
        from cadgen._internal.cam.part import read_part

        cls.part = read_part(tslot_step(class_directory(cls)))

    def walls(self, half_width: float) -> list[str]:
        return [info.ref for info in self.part.faces.values() if info.normal is not None
                and abs(abs(info.normal[1]) - 1.0) < 1e-6 and abs(abs(info.center_mm[1]) - half_width) < 1e-6]

    def reach(self, faces):
        job = parse_job(mill_job([{"op": "profile", "tool": "T1", "side": "inside", "faces": faces}],
                                 tools=[{"id": "T1", "type": "flat", "number": 1, "diameter_mm": 3, "flutes": 2,
                                         "flute_length_mm": 30, "stickout_mm": 35, "shank_diameter_mm": 3}]))
        (op,) = job.setups[0].operations
        return checks.reach(op, [self.part.face(ref) for ref in op.faces], {}, (self.part.vertices, self.part.triangles),
                            self.part.face_of_triangle, job.tools["T1"], TSLOT["size"][2] + 1.0, None)

    def test_the_necks_walls_are_in_reach_and_the_undercut_is_not(self):
        neck, head = self.walls(TSLOT["neck"]["width"] / 2), self.walls(TSLOT["head"]["width"] / 2)
        self.assertEqual((2, 2), (len(neck), len(head)))
        self.assertEqual([], self.reach(neck))
        found = self.reach(head)
        self.assertEqual(["unreachable"] * 2, [f["type"] for f in found])
        self.assertTrue(all("100% of" in f["summary"] for f in found), found)


class FlatInside(unittest.TestCase):
    """An inside profile runs along walls: one pocket's floor stands for its walls, and any other flat face is
    refused, naming the walls round its inner loops."""

    def test_the_plates_top_and_its_pockets_floor(self):
        from cadgen._internal.cam.features import pocket_walls, walls_in
        from cadgen._internal.cam.part import read_part

        part = read_part(plate_step(class_directory(type(self))))
        by_z = {round(info.center_mm[2], 3): info for info in part.faces.values()
                if info.normal is not None and info.normal[2] > 0.99 and info.area_mm2 > 200}
        top, floor = by_z[PLATE["size"][2]], by_z[PLATE["pocket"]["floor_z"]]
        self.assertEqual(4, len(walls_in(part, floor.ordinal)))              # the pocket's four sides
        self.assertEqual(10, len(walls_in(part, top.ordinal)))               # bore 1, slot 4, pocket 4, hole 1
        self.assertEqual(walls_in(part, floor.ordinal), pocket_walls(part, floor.ordinal))
        self.assertIsNone(pocket_walls(part, top.ordinal))                   # many holes open in it: not one pocket
        named = parse_job(mill_job([{"op": "profile", "tool": "T1", "side": "inside",
                                     "faces": pocket_walls(part, floor.ordinal)}]))
        (walls,) = named.setups[0].operations
        self.assertEqual([], checks.reach(walls, [part.face(ref) for ref in walls.faces], {},
                                          (part.vertices, part.triangles), part.face_of_triangle, named.tools["T1"],
                                          PLATE["size"][2] + 1.0, None))
        job = parse_job(mill_job([{"op": "profile", "tool": "T1", "side": "inside", "faces": [top.ref]}]))
        (op,) = job.setups[0].operations
        (found,) = checks.reach(op, [top], {}, (part.vertices, part.triangles), part.face_of_triangle, job.tools["T1"],
                                PLATE["size"][2] + 1.0, None, walls={top.ref: walls_in(part, top.ordinal)})
        self.assertEqual(("error", "not_facing"), (found["severity"], found["type"]))
        self.assertIn("the walls round it: " + ", ".join(walls_in(part, top.ordinal)), found["summary"])
        outside = parse_job(mill_job([{"op": "profile", "tool": "T1", "faces": [top.ref]}])).setups[0].operations[0]
        self.assertEqual([], checks.reach(outside, [top], {}, (part.vertices, part.triangles), part.face_of_triangle,
                                          job.tools["T1"], PLATE["size"][2] + 1.0, None))


class Moves_(unittest.TestCase):
    """On the block (80 x 60 x 25, a pocket floor at z 17), in its own coordinates: the tool comes down -Z."""

    @classmethod
    def setUpClass(cls):
        import numpy as np

        from cadgen._internal.cam.part import read_part

        cls.part = read_part(block_step(class_directory(cls)))
        cls.mesh = (cls.part.vertices, cls.part.triangles)
        cls.job = parse_job(mill_job([{"op": "face", "tool": "T1"}, {"op": "drill", "tool": "T2",
                                                                     "faces": ["face 1"]}]))
        cls.stock = (np.array([-42.0, -32.0, 0.0]), np.array([42.0, 32.0, 26.0]))

    def check(self, path, op=0, targets=None):
        operation = self.job.setups[0].operations[op]
        return checks.check_moves("top", path, [operation], self.job.tools, self.mesh, *self.stock, self.job.machine,
                                  {operation.index: targets or []})

    def target(self, ordinal: int, final_z: float, wall: bool = False):
        mine = self.part.face_of_triangle == ordinal
        return checks.Target(ref=self.part.faces[ordinal].ref, final_z=final_z, wall=wall,
                             points=checks.face_points(*self.mesh, mine, 0.5),
                             edges=None if wall else checks.face_edges(*self.mesh, mine))

    def types(self, found):
        return sorted(f["type"] for f in found)

    def test_a_pass_over_the_top_and_down_into_the_pocket_is_clean(self):
        path = moves([[0, 0, 40], [0, 0, 28], [0, 0, 25.0], [30, 0, 25.0], [0, 0, 25], [0, 0, 17.0], [-15, 0, 17.0],
                      [-15, 0, 40]], [True, True, False, False, False, False, False, True])
        self.assertEqual([], self.check(path))

    def test_a_move_through_the_wall_is_a_gouge_where_it_happens(self):
        # Along y = -15, clear of the island at (14, 0), out through the pocket's wall at x = 25.
        path = moves([[0, -15, 40], [0, -15, 17.0], [30, -15, 17.0], [30, -15, 40]], [True, False, False, True])
        (found,) = self.check(path)
        self.assertEqual("gouge", found["type"])
        self.assertIn("8.00 mm into the part", found["summary"])          # 25 - 17 at the wall
        self.assertGreaterEqual(found["items"][0]["at"][0], 25.0 - 3.0)   # where the tool first meets the wall

    def test_a_drill_the_size_of_its_hole_down_the_hole_is_clean(self):
        x, y = -33.0, -23.0
        drill = self.job.tools["T2"]
        self.assertEqual(5.0, drill.diameter_mm)
        path = moves([[x, y, 40], [x, y, 28], [x, y, -1 - drill.tip_length_mm], [x, y, 40]], [True, True, False, True],
                     op=1)
        self.assertEqual([], self.check(path, op=1))
        off = moves([[x + 1, y, 40], [x + 1, y, 28], [x + 1, y, 10], [x + 1, y, 40]], [True, True, False, True], op=1)
        self.assertEqual(["gouge"], self.types(self.check(off, op=1)))

    def test_a_rapid_into_uncut_stock_but_not_a_retract_or_a_link_inside_a_cleared_pass(self):
        retract = moves([[0, 0, 40], [0, 0, 28], [0, 0, 25.0], [0, 0, 40]], [True, True, False, True])
        self.assertEqual([], self.check(retract))
        plunge = moves([[0, 0, 40], [0, 0, 20.0], [5, 0, 20.0]], [True, True, False])
        self.assertEqual(["rapid_into_stock"], self.types(self.check(plunge)))
        # Cut a pass at z 25.5 along y = 0 from x 0 to -15, then link back along it at that depth: already cut.
        link = moves([[0, 0, 40], [0, 0, 26.5], [0, 0, 25.5], [-15, 0, 25.5], [0, 0, 25.5], [0, 0, 40]],
                     [True, True, False, False, True, True])
        self.assertEqual([], self.check(link))
        # The same link 5 mm to the side runs through stock no pass has cut.
        aside = moves([[0, 0, 40], [0, 0, 26.5], [0, 0, 25.5], [-15, 0, 25.5], [-15, 5, 25.5], [-15, 5, 40]],
                      [True, True, False, False, True, True])
        (found,) = self.check(aside)
        self.assertEqual("rapid_into_stock", found["type"])
        self.assertIn("0.50 mm into stock not yet cut", found["summary"])

    def test_a_hole_is_drilled_only_by_a_plunge_down_its_axis_to_its_depth(self):
        x, y = BLOCK["holes"]["centers"][0]
        bottom = -1 - self.job.tools["T2"].tip_length_mm
        hole = checks.Target(ref="block/face 7", final_z=bottom, axis_xy=(x, y))
        down = moves([[x, y, 40], [x, y, 28], [x, y, bottom], [x, y, 40]], [True, True, False, True], op=1)
        self.assertEqual([], self.check(down, op=1, targets=[hole]))
        short = moves([[x, y, 40], [x, y, 28], [x, y, 10.0], [x, y, 40]], [True, True, False, True], op=1)
        (found,) = self.check(short, op=1, targets=[hole])
        self.assertEqual(("coverage", "error", "uncut"), (found["check"], found["severity"], found["type"]))
        self.assertIn("FreeCAD drilled nothing down block/face 7", found["summary"])
        (x2, y2) = BLOCK["holes"]["centers"][1]
        other = moves([[x2, y2, 40], [x2, y2, 28], [x2, y2, bottom], [x2, y2, 40]], [True, True, False, True], op=1)
        self.assertEqual(["uncut"], self.types(self.check(other, op=1, targets=[hole])))

    def test_a_floor_or_a_wall_no_move_reaches_at_the_depth_is_uncut(self):
        from cadgen import cam

        lower = self.part.face(floor_ref(cam.features(self.part.document), 11.0)).ordinal
        floor = self.target(lower, 11.0)
        # The lower step, 24 x 20 round (-10, 0): passes 4 mm apart with the 6 mm tool, then once round them as
        # FreeCAD's pocket ends, clear all of it but the corners, which no round tool reaches.
        rows = [[x, y, 11.0] for k, y in enumerate((-7, -3, 1, 5, 7)) for x in ((-19, -1) if k % 2 == 0 else (-1, -19))]
        rows += [[-1, -7, 11.0], [-19, -7, 11.0], [-19, 7, 11.0]]
        clear = moves([[-19, -7, 40], [-19, -7, 28], *rows, [rows[-1][0], 7, 40]],
                      [True, True, *[False] * len(rows), True])
        self.assertEqual([], self.check(clear, targets=[floor]))
        # One stroke across part of it: what the tool fits and FreeCAD left is said, not passed.
        stroke = moves([[-10, 0, 40], [-10, 0, 28], [-10, 0, 11.0], [-15, 0, 11.0], [-15, 0, 40]],
                       [True, True, False, False, True])
        (found,) = self.check(stroke, targets=[floor])
        self.assertEqual("uncut", found["type"])
        self.assertRegex(found["summary"], r"FreeCAD left \d+% of what the tool fits uncut on")
        above = moves([[-10, 0, 40], [-10, 0, 28], [-10, 0, 12.0], [-15, 0, 12.0], [-15, 0, 40]],
                      [True, True, False, False, True])
        self.assertEqual(["uncut"], self.types(self.check(above, targets=[floor])))
        # The upper step's wall at x = 25: a tool run beside it at the depth reaches it, one 25 mm off does not.
        (ordinal,) = [o for o, info in self.part.faces.items() if info.normal is not None and info.normal[0] < -0.99
                      and abs(info.center_mm[0] - 25.0) < 1e-6]
        wall = self.target(ordinal, 17.0, wall=True)
        beside = moves([[21.98, -10, 40], [21.98, -10, 28], [21.98, -10, 17.0], [21.98, 10, 17.0], [21.98, 10, 40]],
                       [True, True, False, False, True])
        self.assertEqual([], self.check(beside, targets=[wall]))
        away = moves([[0, -10, 40], [0, -10, 28], [0, -10, 17.0], [0, 10, 17.0], [0, 10, 40]],
                     [True, True, False, False, True])
        self.assertEqual(["uncut"], self.types(self.check(away, targets=[wall])))

    def test_a_ball_s_passes_too_far_apart_leave_its_scallop_standing_uncut(self):
        # A 6 mm ball at a stepover of 0.7 (4.2 mm) leaves ridges 3 - sqrt(9 - 2.1²) = 0.86 mm high between its
        # passes; the flat end mill's same passes cut the floor flat, and the ball's 0.875 mm apart cut it to within
        # 0.05 mm (its scallop, 0.03 mm).
        import numpy as np

        from cadgen import cam

        job = parse_job(mill_job([{"op": "pocket", "tool": "B1", "faces": ["face 1"]}], tools=[
            {"id": "B1", "type": "ball", "number": 3, "diameter_mm": 6, "flutes": 2, "flute_length_mm": 20,
             "stickout_mm": 30, "shank_diameter_mm": 6},
            *mill_job([])["tools"]]))
        (operation,) = job.setups[0].operations
        floor = self.target(self.part.face(floor_ref(cam.features(self.part.document), 11.0)).ordinal, 11.0)

        def passes(ys):
            rows = [[x, y, 11.0] for k, y in enumerate(ys) for x in ((-19, -1) if k % 2 == 0 else (-1, -19))]
            rows += [[rows[-1][0], -7, 11.0], [-20 - rows[-1][0], -7, 11.0], [-20 - rows[-1][0], 7, 11.0]]
            return moves([[-19, -7, 40], [-19, -7, 28], *rows, [rows[-1][0], 7, 40]],
                         [True, True, *[False] * len(rows), True])

        def check(path, tools):
            return checks.check_moves("top", path, [operation], tools, self.mesh, *self.stock, job.machine,
                                      {operation.index: [floor]})

        wide = passes(np.arange(-7.0, 7.01, 4.2).tolist() + [7.0])
        (found,) = check(wide, job.tools)
        self.assertEqual(("coverage", "uncut"), (found["check"], found["type"]))
        ridge = float(re.search(r"standing up to (\d+\.\d+) mm between its passes", found["summary"]).group(1))
        self.assertGreater(ridge, 0.6)
        self.assertLessEqual(ridge, 3 - math.sqrt(9 - 2.1 ** 2) + 0.01)
        flat = dict(job.tools, B1=self.job.tools["T1"])
        self.assertEqual([], check(wide, flat))
        self.assertEqual([], check(passes(np.linspace(-7.0, 7.0, 17).tolist()), job.tools))

    def test_a_face_operation_is_held_to_the_whole_face(self):
        # Facing passes 2.4 mm apart over the whole top cut it; leave one out and the strip under it is uncut.
        top = max((o for o, info in self.part.faces.items() if info.normal is not None and info.normal[2] > 0.99
                   and abs(info.center_mm[2] - BLOCK["size"][2]) < 1e-6), key=lambda o: self.part.faces[o].area_mm2)
        mine = self.part.face_of_triangle == top
        face = checks.Target(ref=self.part.faces[top].ref, final_z=25.0, points=checks.face_points(*self.mesh, mine, 0.5))
        ys = [-33.0 + 2.4 * k for k in range(29)]

        def facing(rows):
            path = [[x, y, 25.0] for k, y in enumerate(rows) for x in ((-45, 45) if k % 2 == 0 else (45, -45))]
            return moves([[-45, -33, 40], [-45, -33, 26], *path, [path[-1][0], path[-1][1], 40]],
                         [True, True, *[False] * len(path), True])

        self.assertEqual([], self.check(facing(ys), targets=[face]))
        (found,) = self.check(facing(ys[:12] + ys[14:]), targets=[face])
        self.assertEqual("uncut", found["type"])
        self.assertRegex(found["summary"], r"FreeCAD left \d+% of what the tool fits uncut on COMPOUND/face \d+$")

    def test_a_tool_run_0_2_mm_into_a_wall_is_a_gouge_that_deep(self):
        # Along the upper step's wall at x = 25 with the 6 mm end mill's edge 0.2 mm into it: the grid the part
        # was once read on, 0.5 mm, passed it, and called it 8 mm deep (the wall's height over the tool).
        beside = moves([[21.98, -10, 40], [21.98, -10, 28], [21.98, -10, 17.0], [21.98, 10, 17.0], [21.98, 10, 40]],
                       [True, True, False, False, True])
        self.assertEqual([], self.check(beside))
        into = moves([[22.2, -10, 40], [22.2, -10, 28], [22.2, -10, 17.0], [22.2, 10, 17.0], [22.2, 10, 40]],
                     [True, True, False, False, True])
        (found,) = self.check(into)
        self.assertEqual("gouge", found["type"])
        self.assertIn("the tool comes 0.20 mm into the part", found["summary"])
        self.assertAlmostEqual(22.2, found["items"][0]["at"][0], places=3)

    def test_an_operation_with_no_cut_and_a_setup_past_the_travel(self):
        self.assertEqual(["empty_operation"], self.types(self.check(moves([[0, 0, 40], [5, 0, 40]], [True, True]))))
        wide = moves([[-200, 0, 40], [200, 0, 40], [200, 0, 26.0], [210, 0, 26.0]], [True, True, True, False])
        self.assertEqual(["travel"], self.types(self.check(wide)))


if __name__ == "__main__":
    unittest.main()


class ReadBack(unittest.TestCase):
    """What FreeCAD holds after recomputing, and what its post wrote, held to what cadgen set."""

    SPEC = {"index": 0, "op": "drill", "feeds": {"rpm": 9000.0, "feed_mm_min": 600.0, "plunge_mm_min": 200.0},
            "stepdown_mm": None, "peck_mm": 1.5, "final_z": -4.0}

    def setUp(self):
        self.job = parse_job(mill_job([{"op": "drill", "tool": "T2", "faces": ["face 1"], "peck_mm": 1.5}]))

    def test_a_value_freecad_put_back_over_cadgen_s_is_refused(self):
        operations = self.job.setups[0].operations
        same = {"rpm": 9000.0, "feed_mm_min": 600.0, "plunge_mm_min": 200.0, "peck_mm": 1.5, "final_z": -4.0}
        self.assertEqual([], checks.held("top", operations, [self.SPEC], [{"held": same}]))
        (found,) = checks.held("top", operations, [self.SPEC], [{"held": {**same, "peck_mm": 3.75}}])
        self.assertEqual(("post", "error", "overridden"), (found["check"], found["severity"], found["type"]))
        self.assertIn("FreeCAD holds a peck of 3.75 mm where cadgen set 1.5", found["summary"])

    def test_a_posted_speed_feed_or_peck_cadgen_did_not_set_is_refused(self):
        program = ("(cadgen cam: S1 F2 Q3)\nG54\nM3 S9000\nG0 X1 Y2\nG83 X1 Y2 Z-4.000 R3.000 Q1.500 F200.000 ; F7\n"
                   "G1 X5 F600.0\n")
        self.assertEqual([], checks.posted("top", "part.top.ngc", program, [self.SPEC], "G54"))
        found = checks.posted("top", "part.top.ngc", program.replace("S9000", "S12000").replace("Q1.500", "Q3.750"),
                              [self.SPEC], "G54")
        self.assertEqual([("post", "posted")] * 2, [(f["check"], f["type"]) for f in found])
        self.assertIn("part.top.ngc: the posted program says S12000, a spindle speed cadgen set for none of its "
                      "operations (9000)", found[0]["summary"])
        self.assertIn("Q3.750, a peck", found[1]["summary"])

    def test_a_move_in_any_work_offset_but_the_setups_is_refused(self):
        # Fanuc's post, given G55, selected G54 again in its tool length offset line after every tool change.
        fanuc = ("G17 G54 G40 G49 G80 G90 G94\nG55\nM6 T2\nG91 G0 G43 G54 Z-[#[2000+#4120]] H#4120\nG90\nM3 S9000\n"
                 "G0 X1 Y2\nG17 G54 G90 G80 G40\nM30\n")
        (found,) = checks.posted("top", "part.top.nc", fanuc, [self.SPEC], "G55")
        self.assertEqual(("post", "error", "posted"), (found["check"], found["severity"], found["type"]))
        self.assertIn("part.top.nc: the posted program moves in G54, where the setup's work offset is G55",
                      found["summary"])
        # The preamble's and the postamble's G54 move nothing: only the offset each move is made in counts.
        self.assertEqual([], checks.posted("top", "part.top.nc", fanuc.replace("G43 G54", "G43 G55"), [self.SPEC],
                                           "G55"))
        (unset,) = checks.posted("top", "part.top.nc", "M3 S9000\nG0 X1 Y2\n", [self.SPEC], "G55")
        self.assertIn("moves in no work offset it selects", unset["summary"])
