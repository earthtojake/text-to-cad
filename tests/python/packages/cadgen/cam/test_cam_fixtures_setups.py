"""Typed fixtures (a vise, a plate) built into keep-out boxes around the stock, and a setup turned onto a face."""

from __future__ import annotations

import copy
import dataclasses
import math
import unittest

import numpy as np

from tests.python.support import gcode_reader
from tests.python.support.cam_fixtures import (
    BLOCK, block_step, class_directory, floor_ref, mill_job, quiet, read_glb,
)

from cadgen._internal.cam.job import CamJobError, parse_job
from cadgen._internal.cam.wcs import FaceOrientation, build_wcs, rotation_to
from cadgen._internal.cam.workholding import holding_boxes

BASE = {
    "machine": {"kind": "mill", "post": "grbl"},
    "material": "aluminum-6061",
    "stock": {"kind": "box", "margin_mm": [2, 2, 1]},
    "tools": [{"id": "T1", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 18}],
    "setups": [{"id": "top", "operations": [{"op": "face", "tool": "T1"}]}],
}
#: The block's stock (margin 2, 2, 1): 84 x 64 x 26 mm, its bottom on z = 0.
STOCK = np.array([[x, y, z] for x in (-42.0, 42.0) for y in (-32.0, 32.0) for z in (0.0, 26.0)])
#: The chamfered block: 40 x 30 x 20 mm, its top +X edge cut back 10 mm at 30 degrees (the face's normal is 30 degrees
#: off +Z towards +X).
CHAMFER_NORMAL = (0.5, 0.0, math.sqrt(3) / 2)


def job(fixture=None, *, machine=None, orientation=None):
    out = copy.deepcopy(BASE)
    if machine:
        out["machine"] = machine
    if fixture is not None:
        out["setups"][0]["fixture"] = fixture
    if orientation is not None:
        out["setups"][0]["orientation"] = orientation
    return out


def boxes_of(raw_job, stock=STOCK):
    """``({name: (min, max)}, assumed)`` of the job's first setup's fixtures, built around ``stock``."""
    parsed = parse_job(raw_job)
    setup = parsed.setups[0]
    wcs = build_wcs(setup, stock_points=stock, part_points=stock, machine=parsed.machine)
    boxes, assumed = holding_boxes(setup, wcs, stock)
    return {box.name: (box.min_mm, box.max_mm) for box in boxes}, assumed


class FixtureVocabulary(unittest.TestCase):
    def test_a_box_a_typed_box_a_vise_and_a_plate_parse(self):
        setup = parse_job(job([{"min_mm": [0, 0, 0], "max_mm": [1, 1, 1]},
                               {"type": "box", "min_mm": [2, 0, 0], "max_mm": [3, 1, 1], "name": "clamp"},
                               {"type": "vise", "grip_mm": 8, "jaws_along": "x"},
                               {"type": "plate", "name": "spoilboard"}])).setups[0]
        self.assertEqual(["", "clamp"], [box.name for box in setup.fixtures])
        self.assertEqual([("vise", {"grip_mm": 8.0, "jaws_along": "x"}), ("plate", {})],
                         [(held.type, held.stated) for held in setup.holding])
        self.assertEqual("setups[0].fixture[3]", setup.holding[1].where)

    def test_every_refusal_teaches(self):
        lathe = {"kind": "lathe", "post": "linuxcnc"}
        cases = {
            "type is 'clamp'; use one of box, vise, plate": job({"type": "clamp"}),
            "cadgen does not model a chuck": job({"type": "chuck"}),
            "unknown key 'zz'; the keys for a plate are type, name, thickness_mm, border_mm": job(
                {"type": "plate", "zz": 3}),
            "jaws_along is 'z'; use one of x, y": job({"type": "vise", "jaws_along": "z"}),
            "grip_mm is 0: the jaws would hold none of the stock": job({"type": "vise", "grip_mm": 0}),
            "grip_mm is -2": job({"type": "vise", "grip_mm": -2}),
            "no taller than the parallels (12 mm)": job({"type": "vise", "jaw_height_mm": 12, "parallels_mm": 12}),
            "grip_mm (10) must be jaw_height_mm (40) less parallels_mm (25), 15": job(
                {"type": "vise", "jaw_height_mm": 40, "parallels_mm": 25, "grip_mm": 10}),
            "grip_mm (50) is more than jaw_height_mm (40)": job({"type": "vise", "jaw_height_mm": 40, "grip_mm": 50}),
            "parallels_mm must be at least 0": job({"type": "vise", "parallels_mm": -1}),
            "thickness_mm must be more than 0": job({"type": "plate", "thickness_mm": 0}),
            "a lathe holds its bar in the chuck": dict(job({"type": "vise"}), machine=lathe, stock={
                "kind": "cylinder", "diameter_mm": 20, "length_mm": 40},
                tools=[{"id": "T1", "type": "turn"}], setups=[{"id": "turn", "fixture": {"type": "vise"},
                                                               "operations": [{"op": "turn_face", "tool": "T1"}]}]),
            "a laser cuts a sheet lying flat on its bed": dict(
                job(), machine={"kind": "laser", "post": "grbl"}, stock={"kind": "sheet", "thickness_mm": 3},
                tools=[{"id": "B1", "type": "beam", "kerf_mm": 0.2}],
                setups=[{"id": "cut", "fixture": {"type": "plate"}, "operations": [{"op": "cut", "tool": "B1"}]}]),
        }
        for expected, raw in cases.items():
            with self.subTest(expected=expected), self.assertRaises(CamJobError) as caught:
                parse_job(raw)
            self.assertIn(expected, str(caught.exception))

    def test_three_vise_sizes_agreeing_within_a_hundredth_parse(self):
        held = parse_job(job({"type": "vise", "jaw_height_mm": 40, "parallels_mm": 30, "grip_mm": 10.005})).setups[0]
        self.assertEqual(10.005, held.holding[0].stated["grip_mm"])


class ViseAndPlateBoxes(unittest.TestCase):
    def test_a_vise_with_every_default_grips_across_the_narrower_side_and_says_what_it_assumed(self):
        boxes, assumed = boxes_of(job({"type": "vise"}))
        # 84 x 64 stock: the jaws close along Y. Grip 10 (under half the 26 mm stock), jaws 40, so parallels 30.
        self.assertEqual(((-75.0, -52.0, -30.0), (75.0, -32.0, 10.0)), boxes["vise -Y jaw"])
        self.assertEqual(((-75.0, 32.0, -30.0), (75.0, 52.0, 10.0)), boxes["vise +Y jaw"])
        self.assertEqual(((-75.0, -52.0, -40.0), (75.0, 52.0, -30.0)), boxes["vise floor"])
        self.assertEqual(((-42.0, -32.0, -30.0), (42.0, -26.0, 0.0)), boxes["vise -Y parallel"])
        self.assertEqual(((-42.0, 26.0, -30.0), (42.0, 32.0, 0.0)), boxes["vise +Y parallel"])
        self.assertEqual([{"fixture": "vise", "type": "vise", "assumed": {
            "jaws_along": "y", "jaw_height_mm": 40.0, "grip_mm": 10.0, "parallels_mm": 30.0, "jaw_width_mm": 150.0,
            "jaw_thickness_mm": 20.0, "floor_thickness_mm": 10.0, "parallel_width_mm": 6.0}}], assumed)

    def test_any_two_of_jaw_height_grip_and_parallels_give_the_third(self):
        for stated, (jaw_top, floor) in {
            (("jaw_height_mm", 30), ("grip_mm", 8)): (8.0, -22.0),
            (("grip_mm", 8), ("parallels_mm", 5)): (8.0, -5.0),
            (("jaw_height_mm", 30), ("parallels_mm", 20)): (10.0, -20.0),
        }.items():
            with self.subTest(stated=stated):
                raw = {"type": "vise", "jaws_along": "x", "jaw_width_mm": 100, "jaw_thickness_mm": 15,
                       "floor_thickness_mm": 8, "parallel_width_mm": 4, **dict(stated)}
                boxes, assumed = boxes_of(job(raw))
                self.assertEqual(((-57.0, -50.0, floor), (-42.0, 50.0, jaw_top)), boxes["vise -X jaw"])
                self.assertEqual(((-42.0, -32.0, floor), (-38.0, 32.0, 0.0)), boxes["vise -X parallel"])
                self.assertEqual([], assumed)        # the third is worked out, not assumed

    def test_a_vise_on_the_floor_has_no_parallels_and_a_short_stock_a_shorter_grip(self):
        boxes, assumed = boxes_of(job({"type": "vise", "parallels_mm": 0, "name": "kurt"}),
                                  stock=STOCK * [1, 1, 0.2])
        self.assertEqual({"kurt -Y jaw", "kurt +Y jaw", "kurt floor"}, set(boxes))
        # A 5.2 mm stock: half of it is gripped, and the jaws are that tall standing on the floor at its bottom.
        self.assertEqual(((-75.0, -52.0, 0.0), (75.0, -32.0, 2.6)), boxes["kurt -Y jaw"])
        self.assertEqual({"jaws_along": "y", "jaw_height_mm": 2.6, "grip_mm": 2.6, "jaw_width_mm": 150.0,
                          "jaw_thickness_mm": 20.0, "floor_thickness_mm": 10.0}, assumed[0]["assumed"])

    def test_a_plate_lies_under_the_stock_with_its_border(self):
        boxes, assumed = boxes_of(job({"type": "plate", "thickness_mm": 8}))
        self.assertEqual({"plate": ((-67.0, -57.0, -8.0), (67.0, 57.0, 0.0))}, boxes)
        self.assertEqual([{"fixture": "plate", "type": "plate", "assumed": {"border_mm": 25.0}}], assumed)
        _, assumed = boxes_of(job({"type": "plate", "thickness_mm": 8, "border_mm": 5}))
        self.assertEqual([], assumed)

    def test_a_flipped_setup_holds_the_stock_from_its_top_and_a_rotary_setup_from_the_table(self):
        boxes, _ = boxes_of(job({"type": "plate", "thickness_mm": 8, "border_mm": 5}, orientation="-Z"))
        # Turned over, the stock's top (z = 26) rests on the plate.
        self.assertEqual({"plate": ((-47.0, -37.0, 26.0), (47.0, 37.0, 34.0))}, boxes)
        mill5 = {"kind": "mill5", "post": "linuxcnc"}
        tilted, _ = boxes_of(job({"type": "plate", "thickness_mm": 8, "border_mm": 5}, machine=mill5,
                                 orientation={"a_deg": 30, "c_deg": 90}))
        # The plate is bolted to the table and tilts with the part: square to the part's own axes, under its bottom.
        self.assertEqual({"plate": ((-47.0, -37.0, -8.0), (47.0, 37.0, 0.0))}, tilted)

    def test_a_vise_on_a_setup_turned_to_a_sloping_face_is_refused(self):
        parsed = parse_job(job({"type": "vise"}))
        setup = dataclasses.replace(parsed.setups[0], orientation=FaceOrientation("#o1.f4", CHAMFER_NORMAL))
        wcs = build_wcs(setup, stock_points=STOCK, part_points=STOCK)
        with self.assertRaisesRegex(CamJobError, r"setups\[0\]\.fixture\[0\]: setup top turns the part onto "
                                                 r"#o1\.f4, at an angle to the part's axes"):
            holding_boxes(setup, wcs, STOCK)
        # A face square to the part's axes keeps the vise.
        square = dataclasses.replace(setup, orientation=FaceOrientation("#o1.f2", (0.0, 1.0, 0.0)))
        boxes, _ = holding_boxes(square, build_wcs(square, stock_points=STOCK, part_points=STOCK), STOCK)
        self.assertEqual(5, len(boxes))


class FaceOrientationParsing(unittest.TestCase):
    def test_a_face_names_the_setup_and_waits_for_the_part(self):
        setup = parse_job(job(orientation="#o1.f4")).setups[0]
        self.assertEqual("#o1.f4", setup.orientation)
        self.assertEqual("Face #o1.f4 up", setup.plain)

    def test_an_edge_a_lathe_and_a_cutting_machine_are_refused(self):
        cases = {
            "'#o1.e3', an edge: a setup looks down a flat face's outward normal": job(orientation="#o1.e3"),
            "'#o1.v2', a vertex": job(orientation="#o1.v2"),
            "a planar face's selector like \"#o1.f4\"": job(orientation="#nope"),
            "a lathe's setup is its spindle axis": dict(
                job(), machine={"kind": "lathe", "post": "linuxcnc"},
                stock={"kind": "cylinder", "diameter_mm": 20, "length_mm": 40}, tools=[{"id": "T1", "type": "turn"}],
                setups=[{"id": "turn", "orientation": "#o1.f4", "operations": [{"op": "turn_face", "tool": "T1"}]}]),
            "a laser cuts through the sheet lying flat, so it cannot be turned onto a face": dict(
                job(), machine={"kind": "laser", "post": "grbl"}, stock={"kind": "sheet", "thickness_mm": 3},
                tools=[{"id": "B1", "type": "beam", "kerf_mm": 0.2}],
                setups=[{"id": "cut", "orientation": "#o1.f4", "operations": [{"op": "cut", "tool": "B1"}]}]),
        }
        for expected, raw in cases.items():
            with self.subTest(expected=expected), self.assertRaises(CamJobError) as caught:
                parse_job(raw)
            self.assertIn(expected, str(caught.exception))

    def test_the_smallest_rotation_brings_the_normal_to_the_tool(self):
        for normal in (CHAMFER_NORMAL, (0.0, 0.0, 1.0), (0.0, 0.0, -1.0), (1.0, 0.0, 0.0), (0.3, -0.4, -0.866)):
            with self.subTest(normal=normal):
                r = np.asarray(rotation_to(normal))
                unit = np.asarray(normal) / np.linalg.norm(normal)
                self.assertTrue(np.allclose(r @ r.T, np.eye(3)))
                self.assertAlmostEqual(1.0, float(np.linalg.det(r)))
                self.assertTrue(np.allclose(r[2], unit))
                # The turn is about Z x n: that axis stays where it is (no spin about the tool).
                pivot = np.cross([0.0, 0.0, 1.0], unit)
                if np.linalg.norm(pivot) > 1e-9:
                    self.assertTrue(np.allclose(r @ pivot, pivot))
        self.assertEqual(((1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, -1.0)), rotation_to((0, 0, -1)))


def chamfer_step(directory):
    from build123d import Polyline, export_step, extrude, make_face

    slope = math.tan(math.radians(30))
    outline = [(-20, 0), (20, 0), (20, 20 - 10 * slope), (10, 20), (-20, 20), (-20, 0)]
    solid = extrude(make_face(Polyline(*[(x, 0, z) for x, z in outline])), amount=15, both=True, dir=(0, 1, 0))
    path = directory / "chamfer.step"
    export_step(solid, str(path))
    return path


class SetupOnAFace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam
        from cadgen._internal.cam.part import read_part

        cls.directory = class_directory(cls)
        cls.step = chamfer_step(cls.directory)
        cls.part = read_part(cls.step)
        faces = cls.part.faces.values()
        cls.chamfer = next(f.ref for f in faces if f.normal and np.allclose(f.normal, CHAMFER_NORMAL, atol=1e-6))
        cls.side = next(f.ref for f in faces if f.normal and np.allclose(f.normal, (0, -1, 0)))
        cls.job = mill_job([], stock={"kind": "box", "margin_mm": [1, 1, 1]},
                           setups=[{"id": "chamfer", "orientation": cls.chamfer,
                                    "operations": [{"op": "face", "tool": "T1"}]}])
        with quiet():
            cls.result = cam.plan(cls.step, job=cls.job, out_dir=cls.directory / "plan")

    def plan(self, raw):
        from cadgen._internal.cam.run import parse_operations, plan_setups
        from cadgen._internal.cam.stock import build_stock

        parsed = parse_job(raw)
        with quiet():
            return plan_setups(parsed, parse_operations(parsed), self.part, build_stock(parsed.stock, self.part))

    def test_a_face_op_cuts_flat_on_the_face_the_setup_looks_down(self):
        (plan,), ops, _ = self.plan(self.job)
        wcs = plan.wcs
        self.assertTrue(np.allclose(wcs.tool_axis, CHAMFER_NORMAL, atol=1e-6))
        self.assertEqual((), wcs.rotary_deg)
        face = self.part.face(self.chamfer)
        plane_z = float(wcs.to_wcs([face.center_mm])[0][2])
        # Every point of the face sits at that WCS height: the setup's Z is square to it.
        on_face = self.part.triangles[self.part.face_of_triangle == face.ordinal].ravel()
        self.assertTrue(np.allclose(wcs.to_wcs(self.part.vertices[on_face])[:, 2], plane_z, atol=1e-6))
        cuts = plan.toolpath.moves[plan.toolpath.moves["kind"] != 0]
        self.assertAlmostEqual(plane_z, float(cuts["z"].min()), places=6)
        self.assertAlmostEqual(plane_z, ops[0].meta["faced_z"], places=3)
        # stock-top-center, in the turned frame: zero on the highest stock point the tool sees.
        from cadgen._internal.cam.stock import build_stock

        stock = build_stock(parse_job(self.job).stock, self.part)
        self.assertAlmostEqual(0.0, float(wcs.to_wcs(stock.vertices)[:, 2].max()), places=6)

    def test_the_plan_is_ready_and_the_program_and_glb_name_the_face(self):
        result = self.result
        self.assertEqual("ready", result.verdict["status"], result.findings)
        self.assertFalse([f for f in result.findings if f["check"] == "gouge"])
        header = gcode_reader.posted_text(result, "chamfer").splitlines()[0]
        self.assertIn(f"setup chamfer Face {self.chamfer} up", header)
        cam = read_glb(result.glb)[0]["scenes"][0]["extras"]["cam"]
        self.assertEqual(self.chamfer, cam["setups"][0]["orientation"])
        self.assertEqual(f"Face {self.chamfer} up", cam["setups"][0]["plain"])

    def test_on_a_mill5_the_face_is_a_rotary_position_and_on_a_mill4_out_of_reach_a_refixture(self):
        mill5 = mill_job([], machine={"kind": "mill5", "post": "linuxcnc"}, stock={"kind": "box", "margin_mm": 1},
                         setups=[{"id": "chamfer", "orientation": self.chamfer,
                                  "operations": [{"op": "face", "tool": "T1"}]}])
        (plan,), _, _ = self.plan(mill5)
        self.assertEqual({"a": 30.0, "c": 90.0}, {k: round(v, 6) for k, v in plan.wcs.rotary_deg})
        self.assertTrue(np.allclose(plan.wcs.tool_axis, CHAMFER_NORMAL, atol=1e-6))
        # A 4th axis turns about X only: a face sloping along X is a re-fixture, the part turned the smallest way.
        mill4 = dict(mill5, machine={"kind": "mill4", "post": "linuxcnc"})
        (plan,), _, _ = self.plan(mill4)
        self.assertEqual((), plan.wcs.rotary_deg)
        self.assertTrue(np.allclose(plan.wcs.rotation, rotation_to(CHAMFER_NORMAL), atol=1e-6))
        # A face the A axis reaches (the -Y side) is indexed: A -90.
        mill4["setups"] = [dict(mill4["setups"][0], orientation=self.side)]
        (plan,), _, _ = self.plan(mill4)
        self.assertEqual({"a": -90.0}, {k: round(v, 6) for k, v in plan.wcs.rotary_deg})

    def test_a_face_not_on_the_part_or_not_flat_is_refused(self):
        from cadgen import cam
        from cadgen._internal.cam.part import read_part

        block = block_step(self.directory)
        cylinder = next(f.ref for f in read_part(block).faces.values() if f.surface == "cylinder")
        cases = {(self.step, "#o1.f99"): "setups[0].orientation: #o1.f99 is not a face of this part",
                 (block, cylinder): f"setups[0].orientation: {cylinder} is a cylinder face, which has no one "
                                    "normal to look down"}
        for (step, ref), expected in cases.items():
            with self.subTest(ref=ref):
                raw = mill_job([], setups=[{"id": "s", "orientation": ref,
                                            "operations": [{"op": "face", "tool": "T1"}]}])
                with quiet():
                    result = cam.plan(step, job=raw, out_dir=self.directory / "refused")
                self.assertFalse(result.ok)
                self.assertIn(expected, result.findings[0]["summary"])


class FixturesInThePlan(unittest.TestCase):
    """The block (80 x 60 x 25, stock 84 x 64 x 26) held in a vise and on a plate."""

    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        cls.directory = class_directory(cls)
        cls.step = block_step(cls.directory)
        cls.top = floor_ref(cam.features(cls.step), BLOCK["size"][2])

    def plan(self, name, fixture, operations):
        from cadgen import cam

        raw = mill_job([], setups=[{"id": "top", "fixture": fixture, "operations": operations}])
        with quiet():
            return cam.plan(self.step, job=raw, out_dir=self.directory / name)

    @staticmethod
    def of(result, kind):
        return [f for f in result.findings if f["type"] == kind]

    def test_a_contour_round_the_outline_runs_into_the_vise_jaws(self):
        contour = {"op": "contour", "tool": "T1", "faces": [self.top], "loops": "outer"}
        result = self.plan("vise", {"type": "vise", "grip_mm": 8}, [contour])
        hits = self.of(result, "fixture")
        self.assertEqual({"vise -Y jaw", "vise +Y jaw"}, {f["items"][0]["fixture"] for f in hits})
        self.assertTrue(all(f["severity"] == "error" and f["items"][0]["operation"] == 0 for f in hits))
        self.assertEqual("fix", result.verdict["status"])
        (note,) = self.of(result, "assumed_fixture")
        self.assertEqual(("fixture", "info"), (note["check"], note["severity"]))
        self.assertIn("Setup top's vise is modelled with sizes the job does not state: jaws_along y, "
                      "jaw_height_mm 40, parallels_mm 32", note["summary"])
        self.assertNotIn("grip_mm", note["items"][0]["assumed"])
        cam = read_glb(result.glb)[0]["scenes"][0]["extras"]["cam"]
        jaws = {box["name"]: box for box in cam["setups"][0]["fixtures"]}
        self.assertEqual({"name": "vise -Y jaw", "min_mm": [-75.0, -52.0, -32.0], "max_mm": [75.0, -32.0, 8.0]},
                         jaws["vise -Y jaw"])
        # Facing the top clears the jaws, which stand under it.
        clear = self.plan("vise-face", {"type": "vise", "grip_mm": 8}, [{"op": "face", "tool": "T1"}])
        self.assertEqual([], self.of(clear, "fixture"))

    def test_a_through_drill_runs_into_the_plate_and_a_cut_resting_on_it_does_not(self):
        drill = {"op": "drill", "tool": "T2", "holes": "all"}
        contour = {"op": "contour", "tool": "T1", "faces": [self.top], "loops": "outer"}
        result = self.plan("plate", [{"type": "plate", "thickness_mm": 10, "border_mm": 20}], [contour, drill])
        hits = self.of(result, "fixture")
        self.assertEqual([("plate", 1)], [(f["items"][0]["fixture"], f["items"][0]["operation"]) for f in hits])
        # The drill's point goes 2.5 mm under the stock (1 mm breakthrough and its point), into the plate.
        self.assertAlmostEqual(2.5, hits[0]["items"][0]["depth_mm"], delta=0.05)
        self.assertEqual([], self.of(result, "assumed_fixture"))
        # Through the stock's bottom into the plate is said once, as the fixture error.
        self.assertEqual([], self.of(result, "through_stock_bottom"))
        # A cut 0.5 mm through is 0.5 mm into the plate: what rises past the tip bounds the depth.
        deeper = self.plan("plate-through", {"type": "plate"}, [dict(contour, through_mm=0.5)])
        (hit,) = self.of(deeper, "fixture")
        self.assertAlmostEqual(0.5, hit["items"][0]["depth_mm"], places=3)


if __name__ == "__main__":
    unittest.main()
