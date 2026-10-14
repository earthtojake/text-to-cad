"""The tri-dexel stock simulator against analytic and Monte-Carlo volumes: a vertical slot, a slot cut from the side,
a tilted ball sweep, rapids into stock, material left, a closed drawing of the stock and a 4th-axis bar. No CAD."""

from __future__ import annotations

import math
import unittest
from types import SimpleNamespace

import numpy as np

from cadgen._internal.cam.ir import FEED, ToolpathBuilder
from cadgen._internal.cam.multiaxis import MoveList
from cadgen._internal.cam.stock import StockGeometry, _box_mesh, _cylinder_mesh, create_stock_sim
from cadgen._internal.cam.stock_dexel import DexelSim
from cadgen._internal.cam.tools import parse_tool
from cadgen._internal.cam.wcs import WCS

FLAT = parse_tool({"id": "T1", "type": "flat", "diameter_mm": 6}, 0)
BALL = parse_tool({"id": "T2", "type": "ball", "diameter_mm": 6}, 1)
TOOLS = {"T1": FLAT, "T2": BALL}
TOP = WCS("top", ((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0.0, 0.0, 0.0))


def box(low=(-20, -15, 0), high=(20, 15, 20)):
    vertices, triangles = _box_mesh(low, high)
    return StockGeometry("box", tuple(low), tuple(high), vertices, triangles, float(np.prod(np.subtract(high, low))))


def part_box(low, high):
    vertices, triangles = _box_mesh(low, high)
    return SimpleNamespace(vertices=vertices, triangles=triangles)


def signed_volume(vertices, triangles):
    tri = np.asarray(vertices)[np.asarray(triangles)]
    return float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)


def one_op(build, tool="T1", setup="top", start=(0, 0, 30)):
    b = ToolpathBuilder(start)
    b.begin_op(index=0, setup=setup, op="test", plain="Test", tool=tool)
    build(b)
    b.end_op()
    return b.build()


class Dexel(unittest.TestCase):
    def test_mill4_and_mill5_simulate_with_it(self):
        for kind in ("mill4", "mill5"):
            sim, adapted = create_stock_sim(kind, box(), None, cell_mm=0.5, tolerance_mm=0.01)
            self.assertIsInstance(sim, DexelSim)
            self.assertEqual([], adapted)
            self.assertAlmostEqual(40 * 30 * 20, sim.volume(), delta=1e-6)

    def test_a_vertical_slot_removes_its_analytic_volume(self):
        sim = DexelSim(box(), cell_mm=0.25)

        def slot(b):
            b.rapid(-10, 0)
            b.rapid(z=21)
            b.plunge(z=15, f=100)
            b.feed(x=10, f=500)
            b.rapid(z=30)

        report = sim.cut(one_op(slot), TOOLS, TOP)
        expected = (20 * 6 + math.pi * 9) * 5
        self.assertAlmostEqual(expected, report.removed_mm3_by_op[0], delta=expected * 0.01)
        self.assertAlmostEqual(5.0, report.depth_by_op[0]["depth_mm"], delta=0.05)
        self.assertEqual([], report.rapid_hits)

    def test_a_slot_cut_from_the_side_is_simulated(self):
        # A setup whose tool comes from part +X (WCS z = part x).
        side = WCS("side", ((0, 1, 0), (0, 0, 1), (1, 0, 0)), (0.0, 0.0, 0.0))
        sim = DexelSim(box(), cell_mm=0.25)

        def plunge(b):
            b.feed(z=15, f=100)       # 5 mm into the +X face at part (y, z) = (0, 10)
            b.feed(x=5, f=100)        # along part +Y by 5
            b.rapid(z=40)

        report = sim.cut(one_op(plunge, start=(0, 10, 40)), TOOLS, side)
        expected = (5 * 6 + math.pi * 9) * 5
        self.assertAlmostEqual(expected, report.removed_mm3_by_op[0], delta=expected * 0.015)
        self.assertAlmostEqual(5.0, report.depth_by_op[0]["depth_mm"], delta=0.05)

    def test_a_tilted_ball_sweep_matches_a_monte_carlo_volume(self):
        sim = DexelSim(box(), cell_mm=0.25)
        tilt = math.radians(30)
        axis = np.array([0.0, math.sin(tilt), math.cos(tilt)])       # A = 30 on a trunnion
        start = np.array([-10.0, 0.0, 17.0])
        end = np.array([10.0, 0.0, 17.0])
        moves = MoveList(start + 20 * axis, (30.0, 0, 0), ("a", "c"))
        moves.go(FEED, start, (30.0, 0, 0), f=200)
        moves.go(FEED, end, (30.0, 0, 0), f=500)
        moves.go(0, end + 20 * axis, (30.0, 0, 0))
        path = moves.build()
        from cadgen._internal.cam.ir import OpRange, Toolpath

        path = Toolpath(path.moves, (), [OpRange(0, "top", "t", "T", "T2", 0, len(path.moves))], start=path.start,
                        rotary=path.rotary)
        report = sim.cut(path, TOOLS, TOP)
        # Monte Carlo: a point is cut when it is within the ball's radius of the axis ray above some ball centre.
        rng = np.random.default_rng(7)
        low, high = np.array([-14.0, -4.0, 13.0]), np.array([14.0, 15.0, 20.0])
        points = low + rng.random((120_000, 3)) * (high - low)
        centres = np.linspace(start, end, 161) + 3.0 * axis
        inside = np.zeros(len(points), dtype=bool)
        for c in centres:
            rel = points - c
            h = np.maximum(rel @ axis, 0.0)
            inside |= np.linalg.norm(rel - h[:, None] * axis, axis=1) <= 3.0
        expected = inside.mean() * np.prod(high - low)
        self.assertAlmostEqual(expected, report.removed_mm3_by_op[0], delta=expected * 0.03)

    def test_a_rapid_through_the_stock_is_a_hit(self):
        sim = DexelSim(box(), cell_mm=0.5)

        def crash(b):
            b.rapid(-30, 0)
            b.rapid(z=10)
            b.rapid(x=30)
            b.rapid(z=30)

        report = sim.cut(one_op(crash), TOOLS, TOP)
        self.assertEqual(1, len(report.rapid_hits))
        self.assertGreater(report.rapid_hits[0]["depth_mm"], 1.0)
        self.assertAlmostEqual(40 * 30 * 20, sim.volume(), delta=1e-6)       # rapids never cut

    def test_a_move_with_the_spindle_stopped_cuts_nothing_and_is_a_crash(self):
        sim = DexelSim(box(), cell_mm=0.5)

        def stopped(b):
            b.rapid(-10, 0)
            b.rapid(z=21)
            b.event("spindle", dir="off")
            b.plunge(z=15, f=100)
            b.feed(x=10, f=500)
            b.event("spindle", rpm=8000, dir="cw")
            b.rapid(z=30)

        report = sim.cut(one_op(stopped), TOOLS, TOP)
        self.assertAlmostEqual(40 * 30 * 20, sim.volume(), delta=1e-6)
        self.assertEqual({}, report.depth_by_op)
        (hit,) = report.rapid_hits
        self.assertGreater(hit["depth_mm"], 1.0)
        self.assertNotIn("neck_diameter_mm", hit)

    def test_a_back_bore_cuts_up_into_the_back_face_and_its_neck_passes_through_the_hole(self):
        bar = parse_tool({"id": "T3", "type": "boring", "diameter_mm": 8, "flute_length_mm": 3,
                          "shank_diameter_mm": 2, "stickout_mm": 40}, 2)
        tools = {**TOOLS, "T3": bar}

        def path(drilled: bool):
            # A Ø6 hole through the 20 mm stock at (0, 0) (when drilled), then a Ø8 x 3 head on a Ø2 neck: down
            # through it shifted, spindle stopped, R 5 mm under the stock, up until the head's top is 1 mm into
            # the back face, and out.
            b = ToolpathBuilder((0, 0, 30))
            if drilled:
                b.begin_op(index=0, setup="top", op="drill", plain="Drill", tool="T1")
                b.rapid(z=21)
                b.plunge(z=-2, f=100)
                b.rapid(z=30)
                b.end_op()
            b.begin_op(index=1, setup="top", op="drill", plain="Back bore", tool="T3")
            handle = b.begin_cycle(cycle="back_bore", holes=[[0, 0, 20]], z_bottom=-2.0, r_plane=-5.0,
                                   retract="initial", initial_z=30.0, shift_mm=1.5, shift_xy=[1.0, 0.0])
            for z_to in (-5.0, 30.0):
                b.event("spindle", dir="off", orient=True)
                b.rapid(x=1.5)
                b.rapid(z=z_to)
                b.rapid(x=0.0)
                b.event("spindle", rpm=2000, dir="cw")
                if z_to < 0:
                    b.feed(z=-2.0, f=100)
                    b.feed(z=-5.0, f=100)
            b.end_cycle(handle)
            b.end_op()
            return b.build()

        sim = DexelSim(box(), cell_mm=0.25)
        report = sim.cut(path(drilled=True), tools, TOP)
        self.assertEqual([], report.rapid_hits)
        self.assertNotIn(1, report.depth_by_op)          # reach judges a back bore from its plan
        ring = math.pi * (16 - 9) * 1.0
        self.assertAlmostEqual(ring, report.removed_mm3_by_op[1], delta=0.1 * ring)
        # The material over the head is still there: the Z ray at x = 3.5 runs from the back face's new 1 mm to 20.
        ray = sim.grids[2].ray_at(3.5, 0.1)
        self.assertEqual([[1.0, 20.0]], [[round(float(lo), 3), round(float(hi), 3)]
                                         for lo, hi in zip(sim.grids[2].lo[ray], sim.grids[2].hi[ray])
                                         if hi > lo])
        # Without the hole the stopped bar's Ø2 neck goes through uncut stock: a crash, and it cuts nothing (only
        # the turning head does, its Ø8 disc 1 mm up into the back face).
        sim = DexelSim(box(), cell_mm=0.25)
        report = sim.cut(path(drilled=False), tools, TOP)
        (hit,) = report.rapid_hits
        self.assertEqual(2.0, hit["neck_diameter_mm"])
        self.assertAlmostEqual(math.pi * 16, 40 * 30 * 20 - sim.volume(), delta=0.1 * math.pi * 16)

    def test_material_left_over_the_part_reads_its_thickness(self):
        stock = box(high=(20, 15, 12))
        sim = DexelSim(stock, cell_mm=0.5)
        part = part_box((-20, -15, 0), (20, 15, 10))
        left = sim.material_left(part, stock_to_leave_mm=0.0, tolerance_mm=0.01)
        self.assertAlmostEqual(2.0, left.max_mm, delta=0.01)
        self.assertAlmostEqual(40 * 30 * 2, left.volume_mm3, delta=40 * 30 * 2 * 0.02)
        self.assertIsNone(sim.material_left(part, stock_to_leave_mm=2.5, tolerance_mm=0.01).at)
        # Stock beside the part (off its footprint) is not judged, as the heightfield does not judge it.
        narrow = part_box((-10, -15, 0), (10, 15, 12))
        fresh = DexelSim(stock, cell_mm=0.5)
        self.assertIsNone(fresh.material_left(narrow, stock_to_leave_mm=0.0, tolerance_mm=0.01).at)

    def test_the_drawing_is_closed_and_holds_the_simulated_volume(self):
        sim = DexelSim(box(), cell_mm=0.5)

        def pocket(b):
            b.rapid(-8, -4)
            b.rapid(z=21)
            b.plunge(z=12, f=100)
            b.feed(x=8, f=500)
            b.feed(y=4, f=500)
            b.feed(x=-8, f=500)
            b.rapid(z=30)

        # Untouched, the box is drawn as its six faces: faces at one height or one span merge into rectangles.
        self.assertEqual(12, len(sim.mesh()[1]))
        sim.cut(one_op(pocket), TOOLS, TOP)
        vertices, triangles = sim.mesh()
        self.assertAlmostEqual(sim.volume(), signed_volume(vertices, triangles), delta=1e-6 * sim.volume())
        self.assertLess(len(triangles), 2000)

    def test_a_cylinder_bar_is_ray_cast_to_its_volume(self):
        vertices, triangles = _cylinder_mesh("x", (0.0, 0.0, 0.0), 15.0, -30.0, 30.0, segments=192)
        stock = StockGeometry("cylinder", (-30, -15, -15), (30, 15, 15), vertices, triangles,
                              math.pi * 225 * 60, cylinder={"axis": "x", "center": [0, 0, 0], "radius": 15.0})
        sim = DexelSim(stock, cell_mm=0.25)
        polygon = 0.5 * 192 * 225 * math.sin(2 * math.pi / 192) * 60
        self.assertAlmostEqual(polygon, sim.volume(), delta=polygon * 0.005)

    def test_a_big_stock_coarsens_its_grid_and_says_so(self):
        sim = DexelSim(box((-200, -200, 0), (200, 200, 100)), cell_mm=0.1, max_rays=50_000)
        self.assertGreater(sim.cell, 0.1)
        self.assertEqual("stock_grid", sim.adapted[0]["step"])


if __name__ == "__main__":
    unittest.main()
