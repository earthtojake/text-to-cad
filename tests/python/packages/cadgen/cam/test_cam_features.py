"""``cadgen cam features``: the block's holes, floors and pocket, read off the exact part."""

from __future__ import annotations

import unittest

from tests.python.support.cam_fixtures import BLOCK, block_step, class_directory, floor_ref


class BlockFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = block_step(cls.directory)
        cls.result = cam.features(cls.step)

    def test_the_four_through_holes_at_their_centres(self):
        holes = self.result.holes
        self.assertEqual(4, len(holes))
        centres = sorted((round(h["center_mm"][0], 3), round(h["center_mm"][1], 3)) for h in holes)
        self.assertEqual(sorted(BLOCK["holes"]["centers"]), centres)
        for hole in holes:
            self.assertAlmostEqual(5.0, hole["diameter_mm"], places=4)
            self.assertAlmostEqual(25.0, hole["depth_mm"], places=3)
            self.assertTrue(hole["through"])
            self.assertEqual("+Z", hole["axis_word"])
            self.assertAlmostEqual(25.0, hole["center_mm"][2], places=3)

    def test_floors_top_bottom_and_the_stepped_pocket(self):
        kinds = sorted((f["kind"], f["z_mm"]) for f in self.result.floors)
        self.assertIn(("top", 25.0), kinds)
        self.assertIn(("bottom", 0.0), kinds)
        self.assertIn(("floor", 17.0), kinds)
        self.assertIn(("floor", 11.0), kinds)
        upper = next(f for f in self.result.floors if f["ref"] == floor_ref(self.result, 17.0))
        self.assertAlmostEqual(8.0, upper["pocket"]["depth_mm"], places=3)
        self.assertEqual(1, upper["pocket"]["islands"])
        lower = next(f for f in self.result.floors if f["ref"] == floor_ref(self.result, 11.0))
        self.assertAlmostEqual(6.0, lower["pocket"]["depth_mm"], places=3)

    def test_every_face_has_a_reading_and_the_box(self):
        self.assertTrue(self.result.ok)
        self.assertEqual([80.0, 60.0, 25.0], [round(v, 3) for v in self.result.bbox_mm["size"]])
        self.assertTrue(all(face["reading"] for face in self.result.faces))
        hole_faces = [f for f in self.result.faces if f.get("hole")]
        self.assertTrue(hole_faces and all("hole wall Ø5 along Z" in f["reading"] for f in hole_faces))
        island = [f for f in self.result.faces if f["surface"] == "cylinder" and f.get("hole") is False]
        self.assertTrue(island and "(outside)" in island[0]["reading"])
        lines = self.result.human_lines()
        self.assertIn("80 x 60 x 25 mm", lines[0])

    def test_the_mesh_faces_match_the_scene_ordinals(self):
        import numpy as np

        from cadgen._internal.cam.part import read_part

        part = read_part(self.step)
        for ordinal, info in part.faces.items():
            with self.subTest(face=info.ref):
                selection = part._scene.resolve(info.ref)
                centre = selection.shape().center()
                rows = np.asarray(part.triangles)[np.asarray(part.face_of_triangle) == ordinal]
                points = np.asarray(part.vertices)[np.unique(rows)]
                low, high = points.min(axis=0) - 1e-6, points.max(axis=0) + 1e-6
                self.assertTrue(np.all(low <= [centre.X, centre.Y, centre.Z]) or info.surface != "plane")
                self.assertTrue(np.all([centre.X, centre.Y, centre.Z] <= high) or info.surface != "plane")

    def test_a_ref_that_is_not_a_face_teaches(self):
        from cadgen._internal.cam.job_errors import CamJobError
        from cadgen._internal.cam.part import read_part

        part = read_part(self.step)
        with self.assertRaises(CamJobError) as caught:
            part.face("#o1.f999")
        self.assertIn("cadgen cam features lists them", str(caught.exception))


class HoleBlockFeatures(unittest.TestCase):
    """Counterbores, countersinks and drawn points are part of their hole; a hole under a roof is not reached."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam
        from tests.python.support.cam_fixtures import quiet
        from tests.python.support.cam_fixtures_drilling import hole_block_step

        with quiet():
            cls.result = cam.features(hole_block_step(class_directory(cls)))

    def hole(self, x, y):
        (hole,) = [h for h in self.result.holes
                   if abs(h["center_mm"][0] - x) < 1e-3 and abs(h["center_mm"][1] - y) < 1e-3]
        return hole

    def faces_of(self, hole, surface):
        kinds = {face["ref"]: face for face in self.result.faces}
        return [ref for ref in hole["faces"] if kinds[ref]["surface"] == surface]

    def test_a_counterbored_hole_is_one_hole_opening_at_the_top_of_its_counterbore(self):
        from tests.python.support.cam_fixtures_drilling import BLOCK

        top = BLOCK["size"][2]
        holes_here = [h for h in self.result.holes if abs(h["center_mm"][0] + 30) < 1e-3]
        self.assertEqual(1, len(holes_here))                          # not a Ø9 blind hole and a Ø5 one under it
        hole = holes_here[0]
        self.assertAlmostEqual(5.0, hole["diameter_mm"], places=4)
        self.assertTrue(hole["through"])
        self.assertAlmostEqual(top, hole["center_mm"][2], places=4)   # opens at the part's top, not the shoulder
        self.assertAlmostEqual(top, hole["depth_mm"], places=4)
        self.assertEqual({"diameter_mm": 9.0, "depth_mm": 4.0}, hole["counterbore"])
        self.assertIn("counterbore Ø9 x 4", hole["reading"])
        # Its refs: the Ø5 wall first (it names the hole), the counterbore's wall and its shoulder.
        walls = self.faces_of(hole, "cylinder")
        self.assertEqual(2, len(walls))
        self.assertEqual(hole["faces"][0], walls[0])
        (shoulder,) = self.faces_of(hole, "plane")
        self.assertEqual(top - 4.0, next(f["z_mm"] for f in self.result.floors if f["ref"] == shoulder))
        self.assertEqual(["+Z", "-Z"], hole["reach"])

    def test_a_countersunk_hole_opens_at_the_top_of_its_countersink(self):
        hole = self.hole(-15, 12)
        self.assertAlmostEqual(20.0, hole["center_mm"][2], places=4)
        self.assertEqual({"diameter_mm": 10.0, "angle_deg": 90.0}, hole["countersink"])
        self.assertEqual(1, len(self.faces_of(hole, "cone")))
        self.assertNotIn("point_mm", hole)

    def test_a_drawn_point_is_measured_and_a_flat_floor_is_a_ref(self):
        import math

        pointed = self.hole(0, 12)
        self.assertAlmostEqual(3.0 / math.tan(math.radians(70)), pointed["point_mm"], places=3)
        self.assertAlmostEqual(8.0, pointed["depth_mm"], places=4)
        self.assertEqual(1, len(self.faces_of(pointed, "cone")))
        flat = self.hole(15, 12)
        self.assertNotIn("point_mm", flat)
        self.assertEqual(1, len(self.faces_of(flat, "plane")))        # its floor

    def test_reach_is_where_a_ray_out_of_the_opening_leaves_the_part(self):
        cave = self.hole(28, 0)
        self.assertFalse(cave["through"])
        self.assertEqual([], cave["reach"])                            # the roof covers it
        self.assertIn("no tool reaches it", cave["reading"])
        # A hole down from the top that ends in a cross bore: through (it breaks into air), reached from the top only.
        down = self.hole(-20, -12)
        self.assertTrue(down["through"])
        self.assertEqual(["+Z"], down["reach"])
        cross = next(h for h in self.result.holes if h["axis_word"] in ("+X", "-X"))
        self.assertEqual(["+X", "-X"], cross["reach"])


class PartCylinders(unittest.TestCase):
    """A plate with an R2-cornered pocket, a slot with round ends, and a Ø6.6 and a Ø10 hole through it."""

    @classmethod
    def setUpClass(cls):
        from build123d import Align, Axis, Box, Cylinder, Pos, SlotCenterToCenter, export_step, extrude, fillet

        from cadgen import cam

        base = (Align.CENTER, Align.CENTER, Align.MIN)
        pocket = fillet((Pos(-10, 0, 5) * Box(30, 20, 6, align=base)).edges().filter_by(Axis.Z), 2)
        slot = Pos(-10, 0, 0) * extrude(SlotCenterToCenter(14, 6), 10)
        part = (Box(76, 44, 10, align=base) - pocket - slot - Pos(25, 10, 0) * Cylinder(3.3, 10, align=base)
                - Pos(25, -10, 0) * Cylinder(5, 10, align=base))
        step = class_directory(cls) / "bracket.step"
        export_step(part, str(step))
        cls.result = cam.features(step)

    def test_a_rounded_corner_or_a_slots_end_is_not_a_hole(self):
        self.assertEqual([(6.6, True), (10.0, True)],
                         sorted((round(h["diameter_mm"], 3), h["through"]) for h in self.result.holes))
        corners = [f for f in self.result.faces if f["reading"].startswith("rounded corner R2 along Z")]
        self.assertEqual(4, len(corners))
        self.assertFalse(any(f["hole"] for f in corners))


class Direction(unittest.TestCase):
    """``direction`` lists what a tool from one side can work; the generated CLI takes ``--direction -Z``."""

    @classmethod
    def setUpClass(cls):
        cls.step = block_step(class_directory(cls))

    def test_from_below_only_the_bottom_and_the_through_holes(self):
        from cadgen import cam

        under = cam.features(self.step, direction="-Z")
        self.assertTrue(under.ok, under.findings)
        self.assertEqual(["bottom"], [f["kind"] for f in under.floors])
        self.assertEqual(4, len(under.holes))
        self.assertTrue(all(f["surface"] != "plane" or f["normal"][2] < 0 for f in under.faces))
        above = cam.features(self.step, direction="+Z")
        self.assertIn("floor", [f["kind"] for f in above.floors])
        self.assertEqual((), cam.features(self.step, direction="+X").holes)
        wrong = cam.features(self.step, direction="Z")
        self.assertFalse(wrong.ok)
        self.assertIn("+Z, -Z", wrong.findings[0]["summary"])

    def test_the_cli_takes_a_direction_that_starts_with_a_dash(self):
        import contextlib
        import io
        import json

        from cadgen.cli.cam_features import main

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([str(self.step), "--direction", "-Z", "--json"])
        self.assertEqual(0, code)
        self.assertEqual(["bottom"], [f["kind"] for f in json.loads(out.getvalue())["floors"]])


if __name__ == "__main__":
    unittest.main()
