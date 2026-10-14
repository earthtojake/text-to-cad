"""V-carve: closed shapes carved with a V-bit along their medial axis, the depth at each point the cone's
``(distance to the outline - tip radius) / tan(half angle)`` so the cone's edge touches the outline; ``max_depth_mm``
flattening it; entries along the cone from the surface or from what is already cut (the soundness harness); the
refusals; and a plan end to end through ``cadgen.cam.plan``."""

from __future__ import annotations

import math
import unittest

import numpy as np
import shapely

from cadgen._internal.cam.ir import PLUNGE, RAPID
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.operations import vcarve
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures import class_directory, mill_job, quiet
from tests.python.support.cam_fixtures_milling2d import plan_error
from tests.python.support.cam_soundness import bad_descents, rapids_below

#: The part: a 70 x 50 x 10 block on z = 0, centred; with no stock over its top, the WCS's Z 0 is its top.
SIZE = (70.0, 50.0, 10.0)
SURFACE = 0.0
#: T1 a 90° vee 12 mm across (its cone 6 mm tall), T2 a 60° engraver with a 0.2 mm tip, T3 a 6 mm flat, T4 T1 with
#: 3 mm flutes.
TOOLS = [
    {"id": "T1", "type": "vee", "diameter_mm": 12, "angle_deg": 90, "flute_length_mm": 8, "stickout_mm": 25},
    {"id": "T2", "type": "engraver", "diameter_mm": 6, "angle_deg": 60, "tip_diameter_mm": 0.2,
     "flute_length_mm": 6, "stickout_mm": 20},
    {"id": "T3", "type": "flat", "diameter_mm": 6, "flutes": 3, "flute_length_mm": 15, "stickout_mm": 30},
    {"id": "T4", "type": "vee", "diameter_mm": 12, "angle_deg": 90, "flute_length_mm": 3, "stickout_mm": 25},
]
#: The drawing's shapes, WCS: an L of 4 mm strokes, a ring 3 mm wide (two circles, even-odd) and a dot Ø4.
L_SHAPE = [(-25, -15), (-13, -15), (-13, -11), (-21, -11), (-21, 5), (-25, 5)]
RING = {"centre": (5.0, 0.0), "outer": 6.0, "inner": 3.0}
DOT = {"centre": (20.0, 10.0), "radius": 2.0}
#: The widest circle in the L sits in its corner, touching both outer sides and the inside corner.
L_WIDEST = 4.0 * math.sqrt(2.0) / (1.0 + math.sqrt(2.0))
#: How far the DXF's flattened circles may sit from true ones, and so the cone from the outline (mm).
TOL = 0.02


def block_step(directory):
    from build123d import Align, Box, export_step

    path = directory / "block.step"
    export_step(Box(*SIZE, align=(Align.CENTER, Align.CENTER, Align.MIN)), str(path))
    return path


def letters_dxf(directory, *, closed: bool = True):
    """The L, the ring and the dot (and an open line, which closes nothing); ``closed=False``: open lines only."""
    import ezdxf

    document = ezdxf.new()
    document.header["$INSUNITS"] = 4
    space = document.modelspace()
    space.add_line((-30, 20), (-10, 20))
    if closed:
        space.add_lwpolyline(L_SHAPE, close=True)
        space.add_circle(RING["centre"], radius=RING["outer"])
        space.add_circle(RING["centre"], radius=RING["inner"])
        space.add_circle(DOT["centre"], radius=DOT["radius"])
    path = directory / ("letters.dxf" if closed else "open.dxf")
    document.saveas(path)
    return path


def letters():
    """The drawing's shapes as true polygons (the circles finely), to measure the carve against."""
    ring = shapely.Point(RING["centre"]).buffer(RING["outer"], quad_segs=256).difference(
        shapely.Point(RING["centre"]).buffer(RING["inner"], quad_segs=256))
    dot = shapely.Point(DOT["centre"]).buffer(DOT["radius"], quad_segs=256)
    return shapely.union_all([shapely.Polygon(L_SHAPE), ring, dot])


def job(operations, *, top_mm: float = 0.0):
    return mill_job(operations, tools=TOOLS, stock={"kind": "box", "margin_mm": [3, 3, top_mm]},
                    material="hardwood")


def cone(tool):
    return math.tan(math.radians(tool["angle_deg"] / 2.0)), tool.get("tip_diameter_mm", 0.0) / 2.0


class VCarve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = class_directory(cls)
        cls.step = block_step(cls.directory)
        cls.dxf = letters_dxf(cls.directory)
        cls.part = read_part(cls.step)

    def plan(self, operations, **kwargs):
        parsed = parse_job(job(operations, **kwargs))
        stock = build_stock(parsed.stock, self.part)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), self.part, stock)
        return setups[0], ops, stock

    def moves(self, plan, index=0, step=0.1):
        """The op's cutting points (samples of every move but rapids, ``step`` apart) and its moves' kinds."""
        op = next(o for o in plan.toolpath.ops if o.index == index)
        path = plan.toolpath.slice(op.start, op.end)
        samples = path.sample(0.005, max_step_mm=step)
        keep = samples.kind != RAPID
        keep[0] = False
        return samples.points[keep], path.moves["kind"]

    def assert_cone_inside(self, points, shapes, tool, *, surface=SURFACE, tolerance=TOL):
        """No cutting point's cone crosses the outline: ``tip + depth x tan <= distance to it``, inside the shapes."""
        tan, tip = cone(tool)
        depth = surface - points[:, 2]
        down = points[depth > 1e-6]
        distance = shapely.distance(shapely.points(down[:, :2]), shapes.boundary)
        self.assertTrue(bool(shapely.contains_xy(shapes.buffer(tolerance), down[:, 0], down[:, 1]).all()))
        over = tip + (surface - down[:, 2]) * tan - distance
        self.assertLessEqual(float(over.max()), tolerance, f"the cone crosses the outline by {over.max():.4f} mm")

    def assert_cone_reaches(self, points, shapes, tool, *, surface=SURFACE, tolerance=TOL):
        """Every point of the outline is touched by the cone somewhere: some cutting point's cone edge reaches it."""
        tan, tip = cone(tool)
        reach = tip + np.maximum(surface - points[:, 2], 0.0) * tan
        for ring in [shapes] if shapes.geom_type == "Polygon" else shapely.get_parts(shapes):
            for line in (ring.exterior, *ring.interiors):
                edge = shapely.line_interpolate_point(line, np.arange(0.0, line.length, 0.25))
                xy = shapely.get_coordinates(edge)
                gaps = []
                for chunk in np.array_split(xy, max(1, len(xy) // 64)):
                    d = np.hypot(chunk[:, None, 0] - points[None, :, 0], chunk[:, None, 1] - points[None, :, 1])
                    gaps.append((d - reach[None, :]).min(axis=1))
                gap = np.concatenate(gaps)
                self.assertLessEqual(float(gap.max()), tolerance, f"the outline at {xy[int(np.argmax(gap))]} is "
                                     f"{gap.max():.4f} mm from the cone")

    def assert_sound(self, plan, ops, stock, shapes, tool, *, surface=SURFACE):
        """The descents go into material no steeper than the cone's flank, within the cone (the harness passes
        exactly those, :func:`cone_excuse`); no rapid sideways under the retract plane; no plunge."""
        excused: list = []
        self.assertEqual([], bad_descents(plan, ops, 0, stock=stock,
                                          excuse=cone_excuse(shapes, tool, surface, excused)))
        self.assertEqual([], rapids_below(plan, 0))
        _, kinds = self.moves(plan)
        self.assertNotIn(PLUNGE, set(kinds.tolist()))
        self.assertNotIn("plunges", ops[0].meta)
        return excused


def cone_excuse(shapes, tool, surface, excused):
    """The harness's excuse for a V-carve: a descent that ends within the cone (its edge inside the outline) and is no
    steeper than the cone's flank, so the cone's side meets the material ahead of the tip; or one straight down onto
    the surface (a corner, where the carve starts at no depth)."""
    tan, tip = cone(tool)

    def excuse(op, start, end, kind):
        if kind == PLUNGE:
            return None
        depth = surface - end[2]
        distance = shapes.boundary.distance(shapely.Point(end[0], end[1]))
        if depth * tan + tip > distance + TOL and depth > 1e-6:
            return None
        across = math.hypot(end[0] - start[0], end[1] - start[1])
        drop = start[2] - end[2]
        reason = None
        if drop <= across / tan * (1 + 1e-3) + 1e-9:
            reason = "along the cone"
        elif across < 1e-9 and depth <= 0.01:
            reason = "down onto the surface"
        if reason:
            excused.append(reason)
        return reason

    return excuse


class Carve(VCarve):
    def test_a_dxf_is_carved_along_its_medial_axis_at_the_cone_depth(self):
        plan, ops, stock = self.plan([{"op": "vcarve", "tool": "T1", "dxf": str(self.dxf)}])
        self.assertIsNone(plan_error(ops))
        points, _ = self.moves(plan)
        shapes = letters()
        tan, _ = cone(TOOLS[0])
        # The deepest of each shape: its widest circle's radius / tan(45°).
        for shape, deepest in ((shapely.Polygon(L_SHAPE), L_WIDEST),
                               (shapely.Point(DOT["centre"]).buffer(DOT["radius"]), DOT["radius"]),
                               (shapes.intersection(shapely.Point(RING["centre"]).buffer(RING["outer"] + 0.5)),
                                (RING["outer"] - RING["inner"]) / 2)):
            inside = shapely.contains_xy(shape.buffer(TOL), points[:, 0], points[:, 1])
            self.assertAlmostEqual(SURFACE - deepest / tan, float(points[inside, 2].min()), delta=TOL)
        # The ring's axis is the circle midway: carved all round at the ring's half width.
        on_axis = np.abs(np.hypot(points[:, 0] - RING["centre"][0], points[:, 1] - RING["centre"][1]) - 4.5) < 0.02
        self.assertGreater(int(on_axis.sum()), 200)
        self.assertGreaterEqual(float(points[on_axis, 2].min()), SURFACE - 1.5 - TOL)
        full = on_axis & (np.abs(points[:, 2] - (SURFACE - 1.5)) < TOL)
        angles = np.degrees(np.arctan2(points[full, 1] - RING["centre"][1], points[full, 0] - RING["centre"][0]))
        self.assertEqual(72, len(np.unique(np.floor((angles + 180.0) / 5.0) % 72)))
        # The L's straight strokes are 4 wide: 2 deep down their middle.
        stroke = (np.abs(points[:, 0] + 23.0) < 1e-3) & (points[:, 1] > -8) & (points[:, 1] < 0)
        self.assertGreater(int(stroke.sum()), 20)
        np.testing.assert_allclose(points[stroke, 2], SURFACE - 2.0, atol=1e-3)
        self.assert_cone_inside(points, shapes, TOOLS[0])
        self.assert_cone_reaches(points, shapes, TOOLS[0])
        meta = ops[0].meta
        self.assertEqual(3, meta["shapes"])
        self.assertAlmostEqual(L_WIDEST, meta["max_depth_mm"], delta=TOL)
        self.assertGreater(meta["runs"], 3)
        self.assertGreater(meta["length_mm"], 60)
        self.assertTrue(meta["no_gouge_check"])
        self.assertIn("open curve", meta["note"])
        self.assertEqual("warning", meta["note_level"])

    def test_a_tipped_engraver_carves_a_region_the_tip_radius_shallower(self):
        region = [[-10, -2], [10, -2], [10, 2], [-10, 2]]
        plan, ops, stock = self.plan([{"op": "vcarve", "tool": "T2", "region": {"polygon": region}}])
        points, _ = self.moves(plan)
        tan, tip = cone(TOOLS[1])
        polygon = shapely.Polygon(region)
        self.assertAlmostEqual(SURFACE - (2.0 - tip) / tan, float(points[:, 2].min()), places=4)
        middle = (np.abs(points[:, 1]) < 1e-6) & (np.abs(points[:, 0]) < 7)
        np.testing.assert_allclose(points[middle, 2], SURFACE - (2.0 - tip) / tan, atol=1e-6)
        self.assert_cone_inside(points, polygon, TOOLS[1], tolerance=3e-3)
        # A flat tip cannot carve a sharp corner at the surface: it rounds a square corner by tip x (sqrt 2 - 1).
        self.assert_cone_reaches(points, polygon, TOOLS[1], tolerance=tip * (math.sqrt(2.0) - 1.0) + 0.01)
        self.assertEqual("info", ops[0].meta["note_level"])

    def test_max_depth_flattens_the_bottom_and_leaves_it_for_a_pocket(self):
        region = {"polygon": [[-15, -8], [15, -8], [15, 8], [-15, 8]]}
        plan, ops, _ = self.plan([{"op": "vcarve", "tool": "T1", "region": region}])
        self.assertEqual("tool_too_small", plan_error(ops)[0])
        self.assertIn("max_depth_mm up to 6", plan_error(ops)[1])
        plan, ops, stock = self.plan([{"op": "vcarve", "tool": "T1", "region": region, "max_depth_mm": 2}])
        self.assertIsNone(plan_error(ops))
        points, _ = self.moves(plan)
        polygon = shapely.Polygon(region["polygon"])
        self.assertAlmostEqual(SURFACE - 2.0, float(points[:, 2].min()), places=6)
        # The walls' foot: the outline inset 2 mm (the cone's half width at 2 mm), carved at the cap all round.
        floor = points[np.isclose(points[:, 2], SURFACE - 2.0)]
        foot = shapely.box(-13, -6, 13, 6).boundary
        on_foot = shapely.distance(shapely.points(floor[:, :2]), foot) < 1e-3
        self.assertGreater(int(on_foot.sum()), 300)
        self.assertLess(float(shapely.distance(foot, shapely.MultiPoint(floor[on_foot, :2]).buffer(0.2))), 1e-9)
        self.assert_cone_inside(points, polygon, TOOLS[0], tolerance=3e-3)
        self.assert_cone_reaches(points, polygon, TOOLS[0], tolerance=0.01)
        meta = ops[0].meta
        self.assertEqual(2.0, meta["max_depth_mm"])
        self.assertEqual((-2.0, 2.0, 312.0), (meta["flat_bottom_z"], meta["flat_inset_mm"], meta["flat_area_mm2"]))
        self.assertEqual("warning", meta["note_level"])
        self.assertIn("a pocket with a flat tool", meta["note"])
        self.assert_sound(plan, ops, stock, polygon, TOOLS[0])

    def test_a_round_shape_is_carved_by_one_spiral_in_from_the_surface(self):
        region = {"polygon": [[3 * math.cos(a), 3 * math.sin(a)] for a in np.linspace(0, 2 * math.pi, 96,
                                                                                      endpoint=False)]}
        plan, ops, stock = self.plan([{"op": "vcarve", "tool": "T1", "region": region}])
        points, _ = self.moves(plan)
        polygon = shapely.Polygon(region["polygon"])
        apothem = 3 * math.cos(math.pi / 96)
        self.assertAlmostEqual(SURFACE - apothem, float(points[:, 2].min()), delta=0.01)
        self.assertEqual((1, {"surface": 1}), (ops[0].meta["runs"], ops[0].meta["entries"]))
        self.assert_cone_inside(points, polygon, TOOLS[0], tolerance=3e-3)
        self.assert_cone_reaches(points, polygon, TOOLS[0], tolerance=0.01)
        self.assert_sound(plan, ops, stock, polygon, TOOLS[0])

    def test_a_flat_face_is_carved_from_its_height(self):
        from cadgen import cam
        from tests.python.support.cam_fixtures_milling2d import face_at

        top = face_at(cam.features(self.step), surface="plane", z_mm=SIZE[2])
        plan, ops, stock = self.plan([{"op": "vcarve", "tool": "T1", "faces": [top], "max_depth_mm": 1}])
        self.assertIsNone(plan_error(ops))
        points, _ = self.moves(plan)
        face = shapely.box(-SIZE[0] / 2, -SIZE[1] / 2, SIZE[0] / 2, SIZE[1] / 2)
        self.assertAlmostEqual(SURFACE - 1.0, float(points[:, 2].min()), places=6)
        self.assert_cone_inside(points, face, TOOLS[0], tolerance=3e-3)
        self.assert_cone_reaches(points, face, TOOLS[0], tolerance=0.01)
        self.assertEqual((1.0, (SIZE[0] - 2) * (SIZE[1] - 2)), (ops[0].meta["flat_inset_mm"],
                                                                 ops[0].meta["flat_area_mm2"]))
        self.assert_sound(plan, ops, stock, face, TOOLS[0])

    def test_entries_along_the_cone_pass_the_harness_in_one_pass_and_in_levels(self):
        for extra in ({}, {"stepdown_mm": 0.75}):
            with self.subTest(**extra):
                plan, ops, stock = self.plan([{"op": "vcarve", "tool": "T1", "dxf": str(self.dxf), **extra}])
                excused = self.assert_sound(plan, ops, stock, letters(), TOOLS[0])
                self.assertIn("along the cone", excused)
                entries = ops[0].meta["entries"]
                self.assertGreater(entries.get("surface", 0), 0)
                # The ring's axis has no end at the surface and the dot's is one point: they ramp or spiral down.
                self.assertGreater(entries.get("ramp", 0), 0)
                if extra:
                    self.assertEqual(4, ops[0].meta["levels"])
                    self.assertGreater(entries.get("cut", 0), 0)
                points, _ = self.moves(plan)
                self.assert_cone_inside(points, letters(), TOOLS[0])

    def test_the_top_must_be_faced_first(self):
        region = {"polygon": [[-10, -2], [10, -2], [10, 2], [-10, 2]]}
        plan, ops, _ = self.plan([{"op": "vcarve", "tool": "T1", "region": region}], top_mm=1.0)
        self.assertEqual("unreachable", plan_error(ops)[0])
        plan, ops, stock = self.plan([{"op": "face", "tool": "T3"},
                                      {"op": "vcarve", "tool": "T1", "region": region}], top_mm=1.0)
        self.assertIsNone(plan_error(ops, 1))
        op = next(o for o in plan.toolpath.ops if o.index == 1)
        z = plan.toolpath.slice(op.start, op.end).positions()[:, 2]
        self.assertAlmostEqual(-1.0 - 2.0, float(z.min()), places=6)


class Refusals(VCarve):
    def test_plan_errors(self):
        def rect(w, h):
            return {"polygon": [[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]]}

        cases = [
            ("empty_operation", "no closed profile", {"tool": "T1", "dxf": str(letters_dxf(self.directory,
                                                                                         closed=False))}),
            ("tool_too_large", "narrower than T2's 0.2 mm tip", {"tool": "T2", "region": rect(0.15, 5)}),
            ("empty_operation", "too small to carve", {"tool": "T1", "region": rect(0.01, 5)}),
            ("too_deep", "deeper than T1's cone", {"tool": "T1", "region": rect(30, 16), "max_depth_mm": 7}),
            ("too_deep", "past T4's 3 mm flutes", {"tool": "T4", "region": rect(8, 8)}),
        ]
        for kind, words, extra in cases:
            with self.subTest(kind=kind, words=words):
                _, ops, _ = self.plan([{"op": "vcarve", **extra}])
                found = plan_error(ops)
                self.assertIsNotNone(found)
                self.assertEqual(kind, found[0])
                self.assertIn(words, found[1])

    def test_job_errors(self):
        region = {"polygon": [[-10, -2], [10, -2], [10, 2], [-10, 2]]}
        cases = [
            ({"tool": "T3", "region": region}, "cuts with a vee, engraver, chamfer tool"),
            ({"tool": "T1", "region": region, "depth_mm": 1}, "unknown key 'depth_mm'"),
            ({"tool": "T1"}, "needs one of \"dxf\""),
            ({"tool": "T1", "region": region, "dxf": str(self.dxf)}, "needs one of \"dxf\""),
            ({"tool": "T1", "region": region, "origin_mm": [1, 2]}, "origin_mm places a DXF"),
            ({"tool": "T1", "dxf": str(self.dxf), "origin_mm": [1]}, "origin_mm must be a list of 2"),
            ({"tool": "T1", "region": {**region, "bottom_z": -1}}, "remove bottom_z"),
            ({"tool": "T1", "region": region, "max_depth_mm": -1}, "max_depth_mm must be more than 0"),
            ({"tool": "T1", "region": region, "stepover": 0.5}, "does not use stepover"),
            ({"tool": "T1", "dxf": "nothing.dxf"}, "no DXF at"),
        ]
        for extra, words in cases:
            with self.subTest(words=words):
                with self.assertRaises(CamJobError) as caught:
                    self.plan([{"op": "vcarve", **extra}])
                self.assertIn(words, str(caught.exception))


class EndToEnd(VCarve):
    def test_a_job_plans_ready_and_posts_the_carve(self):
        from cadgen import cam
        from tests.python.support import gcode_reader

        with quiet():
            result = cam.plan(self.step, job=job([{"op": "vcarve", "tool": "T1", "dxf": self.dxf.name,
                                                   "origin_mm": [1, -1]}]), out_dir=self.directory / "out")
        self.assertTrue(result.ok, result.findings)
        self.assertEqual([], [f for f in result.findings if f["severity"] == "error"])
        self.assertEqual([], [f for f in result.findings if f["check"] == "gouge"])
        row = result.operations[0]
        self.assertEqual(("vcarve", "V-carve", "lite"), (row["op"], row["plain"], row["status"]))
        self.assertEqual(len(vcarve.VCarveOp.limits), len(row["limits"]))
        facts = row["facts"]
        self.assertEqual(3, facts["shapes"])
        self.assertGreater(facts["runs"], 3)
        self.assertAlmostEqual(L_WIDEST, facts["max_depth_mm"], delta=TOL)
        program = gcode_reader.read(gcode_reader.posted_text(result), start=(0.0, 0.0, 6.0))
        cuts = [m for m in program.moves if m.kind != "rapid"]
        self.assertAlmostEqual(SURFACE - facts["max_depth_mm"], min(m.end[2] for m in cuts), delta=2e-3)
        lowest = min(cuts, key=lambda m: m.end[2]).end
        # The deepest point is in the L's corner, moved by origin_mm.
        self.assertTrue(shapely.Polygon(L_SHAPE).contains(shapely.Point(lowest[0] - 1, lowest[1] + 1)))


class MedialAxis(unittest.TestCase):
    def test_the_axis_of_a_rectangle_a_ring_and_a_circle(self):
        rect = vcarve.medial_axis(shapely.box(0, 0, 20, 4))
        self.assertEqual(5, len(rect))                      # the middle and a branch into each corner
        ends = {tuple(np.round(chain[i, :2], 6)) for chain in rect for i in (0, -1)}
        self.assertTrue({(0.0, 0.0), (20.0, 0.0), (20.0, 4.0), (0.0, 4.0)} <= ends)
        middle = max(rect, key=len)
        np.testing.assert_allclose(middle[:, 1], 2.0, atol=1e-6)
        np.testing.assert_allclose(middle[:, 2], 2.0, atol=1e-6)
        ring = vcarve.medial_axis(shapely.Point(0, 0).buffer(5, quad_segs=64).difference(
            shapely.Point(0, 0).buffer(3, quad_segs=64)))
        self.assertEqual(1, len(ring))
        np.testing.assert_allclose(ring[0][0, :2], ring[0][-1, :2])
        np.testing.assert_allclose(np.hypot(ring[0][:, 0], ring[0][:, 1]), 4.0, atol=0.01)
        circle = vcarve.medial_axis(shapely.Point(1, 2).buffer(5, quad_segs=64))
        self.assertEqual(1, len(circle))
        self.assertEqual(1, len(circle[0]))
        np.testing.assert_allclose(circle[0][0], [1, 2, 5], atol=0.01)


if __name__ == "__main__":
    unittest.main()
