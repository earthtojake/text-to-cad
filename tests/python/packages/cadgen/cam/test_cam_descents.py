"""Every 2.5D milling operation, planned on the suites' parts, goes down into material no steeper than its ramp angle,
never rapids sideways under the retract plane and feeds the last millimetre down beside the stock:
:func:`~tests.python.support.cam_soundness.bad_descents`, :func:`~tests.python.support.cam_soundness.rapids_below` and
:func:`~tests.python.support.cam_soundness.rapids_down_beside_stock`, measured on the IR independently of the
planners.

Each operation is planned on its own (nothing an earlier operation cut hides a bad descent), except where the job
needs an earlier one: a chamfer, an engraving or a V-carve after the facing that takes the stock off the part's top,
a thread after the hole is drilled, an external thread after the stud is cleared round. What the harness passes for a
reason of its own is written in :data:`EXCUSED`, each with that reason, and nothing else.
"""

from __future__ import annotations

import unittest

from cadgen._internal.cam.ir import PLUNGE
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures import BLOCK, block_step, floor_ref, mill_job
from tests.python.support.cam_fixtures_milling2d import (
    boss_step, bracket_step, class_directory, engrave_dxf, face_at, job, plan_error, tools,
)
from tests.python.support.cam_soundness import bad_descents, rapids_below, rapids_down_beside_stock

#: The descents the harness passes for a reason of its own, and why each is sound.
EXCUSED = {
    "engrave": "an engraving tool enters its line by plunging its point straight down at the plunge feed: a pointed "
               "tool cuts at its centre, and the line is only depth_mm deep (a fraction of a millimetre); the run "
               "does not count these as plunges to warn of",
    "vcarve": "a V-bit goes down along its own carve no steeper than its cone's flank (the cone's side, not its point, "
              "meets the material ahead), to depths where the cone's edge stays inside the shape's outline: how a "
              "V-carve runs down its medial axis from a corner, ramps into a ring or spirals into a dot",
}

#: The operations whose soundness this suite owns: every 2.5D milling operation the bracket, block and boss plan.
MILLING_2D = ("face", "contour", "pocket", "adaptive", "slot", "chamfer", "engrave", "vcarve", "helix_bore",
              "thread_mill")

DRILL = {"id": "T7", "type": "drill", "diameter_mm": 5, "flute_length_mm": 20, "stickout_mm": 30}
REGION = {"polygon": [[-20, -10], [20, -10], [20, 10], [-20, 10]]}


def _excuse(op, start, end, kind) -> str | None:
    """The :data:`EXCUSED` key that passes this descent, else None."""
    straight_down = abs(start[0] - end[0]) < 1e-9 and abs(start[1] - end[1]) < 1e-9
    if op.spec.op == "engrave" and kind == PLUNGE and straight_down:
        return "engrave"
    if op.spec.op == "vcarve" and kind != PLUNGE and _along_the_cone(op, start, end):
        return "vcarve"
    return None


def _along_the_cone(op, start, end) -> bool:
    """A V-carve's descent (its job gives a ``region`` and ``surface_z``) that ends with the cone's edge inside the
    region's outline and drops no more than ``1 / tan(half angle)`` per millimetre across."""
    import math

    import shapely

    tan = math.tan(math.radians(op.tool.angle_deg / 2.0))
    depth = op.params["surface_z"] - end[2]
    inside = op.params["region"].boundary.distance(shapely.Point(end[0], end[1]))
    across = math.hypot(end[0] - start[0], end[1] - start[1])
    return (op.tool.tip_diameter_mm / 2.0 + depth * tan <= inside + 1e-3
            and start[2] - end[2] <= across / tan * (1 + 1e-3) + 1e-9)


class Sound(unittest.TestCase):
    """Plans ``self.cases`` once per class: {name: (part, job)}; one test per name checks every 2.5D op in it."""

    cases: dict = {}

    @classmethod
    def plan(cls, part, raw):
        parsed = parse_job(raw)
        stock = build_stock(parsed.stock, part)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), part, stock)
        return setups[0], ops, stock

    def assert_sound(self, name: str) -> None:
        part, raw = self.cases[name]
        setup, ops, stock = self.plan(part, raw)
        checked = 0
        for op in ops:
            self.assertIsNone(plan_error(ops, op.index), f"{name}: {op.spec.op}")
            if op.spec.op not in MILLING_2D:
                continue
            checked += 1
            with self.subTest(case=name, op=op.spec.op, index=op.index):
                self.assertEqual([], bad_descents(setup, ops, op.index, stock=stock, excuse=_excuse))
                self.assertEqual([], rapids_below(setup, op.index))
                self.assertEqual([], rapids_down_beside_stock(setup, op.index, stock))
        self.assertGreater(checked, 0)


class Bracket(Sound):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        directory = class_directory(cls)
        step = bracket_step(directory)
        engrave_dxf(directory)
        features = cam.features(step)
        part = read_part(step)
        top = face_at(features, surface="plane", z_mm=12.0)
        slot = face_at(features, surface="plane", z_mm=8.0)
        bore = face_at(features, surface="cylinder", diameter_mm=16.0)
        taps = [h["faces"][0] for h in features.holes if abs(h["diameter_mm"] - 5.0) < 1e-6]
        kit = tools(T7=DRILL)
        cls.cases = {name: (part, job(operations, tools=kit)) for name, operations in {
            "face_zigzag": [{"op": "face", "tool": "T1"}],
            "face_one_way": [{"op": "face", "tool": "T1", "pattern": "one_way", "angle_deg": 90}],
            "face_region_zigzag": [{"op": "face", "tool": "T1", "region": REGION, "depth_mm": 0.5}],
            "face_region_one_way": [{"op": "face", "tool": "T1", "region": REGION, "pattern": "one_way",
                                     "stepdown_mm": 0.5}],
            "contour_tabs": [{"op": "contour", "tool": "T1", "faces": [top], "loops": "outer", "stepdown_mm": 4,
                              "tabs": {"count": 4, "width_mm": 5, "height_mm": 2}}],
            "contour_leads_finish": [{"op": "contour", "tool": "T1", "faces": [top], "stepdown_mm": 4,
                                      "lead_in_mm": 2, "lead_out_mm": 2, "finish_mm": 0.5, "finish_passes": 2}],
            "contour_slot_inside": [{"op": "contour", "tool": "T2", "faces": [slot], "stepdown_mm": 2}],
            "contour_region": [{"op": "contour", "tool": "T1", "stepdown_mm": 3,
                                "region": {"polygon": [[-10, -5], [10, -5], [10, 5], [-10, 5]], "bottom_z": -4}}],
            "pocket_slot": [{"op": "pocket", "tool": "T2", "faces": [slot], "finish_mm": 0.3}],
            "adaptive_slot": [{"op": "adaptive", "tool": "T2", "faces": [slot]}],
            "slot_floor": [{"op": "slot", "tool": "T2", "faces": [slot], "stepdown_mm": 2}],
            "slot_path": [{"op": "slot", "tool": "T1", "stepdown_mm": 1,
                           "path": {"points": [[-10, -20], [10, -20], [15, -15]], "bottom_z": -3}}],
            "helix_bore": [{"op": "helix_bore", "tool": "T1", "faces": [bore]}],
            "chamfer_after_face": [{"op": "face", "tool": "T1"},
                                   {"op": "chamfer", "tool": "T3", "faces": [top], "width_mm": 0.5}],
            "thread_after_drill": [{"op": "drill", "tool": "T7", "faces": taps},
                                   {"op": "thread_mill", "tool": "T4", "faces": taps}],
            "engrave_after_face": [{"op": "face", "tool": "T1"}, {"op": "engrave", "tool": "T6", "dxf": "mark.dxf"}],
            "vcarve_after_face": [{"op": "face", "tool": "T1"},
                                  {"op": "vcarve", "tool": "T3", "surface_z": -1, "stepdown_mm": 2,
                                   "region": {"polygon": [[-12, 10], [12, 10], [12, 20], [-12, 20]]}}],
        }.items()}

    def test_face_zigzag(self):
        self.assert_sound("face_zigzag")

    def test_face_one_way(self):
        self.assert_sound("face_one_way")

    def test_face_region_zigzag(self):
        self.assert_sound("face_region_zigzag")

    def test_face_region_one_way(self):
        self.assert_sound("face_region_one_way")

    def test_contour_tabs(self):
        self.assert_sound("contour_tabs")

    def test_contour_leads_finish(self):
        self.assert_sound("contour_leads_finish")

    def test_contour_slot_inside(self):
        self.assert_sound("contour_slot_inside")

    def test_contour_region(self):
        self.assert_sound("contour_region")

    def test_pocket_slot(self):
        self.assert_sound("pocket_slot")

    def test_adaptive_slot(self):
        self.assert_sound("adaptive_slot")

    def test_slot_floor(self):
        self.assert_sound("slot_floor")

    def test_slot_path(self):
        self.assert_sound("slot_path")

    def test_helix_bore(self):
        self.assert_sound("helix_bore")

    def test_chamfer_after_face(self):
        self.assert_sound("chamfer_after_face")

    def test_thread_after_drill(self):
        self.assert_sound("thread_after_drill")

    def test_engrave_after_face(self):
        self.assert_sound("engrave_after_face")

    def test_vcarve_after_face(self):
        self.assert_sound("vcarve_after_face")


class Block(Sound):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        step = block_step(class_directory(cls))
        features = cam.features(step)
        part = read_part(step)
        lower = floor_ref(features, BLOCK["lower"]["floor_z"])
        upper = floor_ref(features, BLOCK["upper"]["floor_z"])
        cls.cases = {name: (part, mill_job(operations)) for name, operations in {
            "pocket_lower": [{"op": "pocket", "tool": "T1", "faces": [lower]}],
            "pocket_upper_island": [{"op": "pocket", "tool": "T1", "faces": [upper], "finish_floor_mm": 0.5}],
            "adaptive_lower": [{"op": "adaptive", "tool": "T1", "faces": [lower]}],
            "contour_upper_inside": [{"op": "contour", "tool": "T1", "faces": [upper], "stepdown_mm": 3}],
        }.items()}

    def test_pocket_lower(self):
        self.assert_sound("pocket_lower")

    def test_pocket_upper_island(self):
        self.assert_sound("pocket_upper_island")

    def test_adaptive_lower(self):
        self.assert_sound("adaptive_lower")

    def test_contour_upper_inside(self):
        self.assert_sound("contour_upper_inside")


class Boss(Sound):
    @classmethod
    def setUpClass(cls):
        from cadgen import cam

        step = boss_step(class_directory(cls))
        features = cam.features(step)
        part = read_part(step)
        stud = face_at(features, surface="cylinder", diameter_mm=12.0)
        base = face_at(features, surface="plane", z_mm=5.0)
        cls.cases = {"thread_after_clearing": (part, job([{"op": "pocket", "tool": "T1", "faces": [base]},
                                                          {"op": "thread_mill", "tool": "T5", "faces": [stud]}]))}

    def test_thread_after_clearing(self):
        self.assert_sound("thread_after_clearing")


if __name__ == "__main__":
    unittest.main()
