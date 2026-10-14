"""The Toolpath IR (times, sampling, events), 2D sections and offsets, and linking (helix, ramp, tabs, leads)."""

from __future__ import annotations

import math
import unittest

import numpy as np

from cadgen._internal.cam import geom2d, linking
from cadgen._internal.cam.ir import ARC_CCW, FEED, RAPID, ToolpathBuilder, concat


class Machine:
    rapid_mm_min = 6000.0
    tool_change_s = 10.0


class Ir(unittest.TestCase):
    def test_times_lengths_and_events(self):
        b = ToolpathBuilder((0, 0, 10))
        b.event("tool", tool="T1", number=1)
        b.rapid(x=60)                                     # 60 mm at 6000 mm/min: 0.6 s
        b.feed(z=0, f=600)                                # 10 mm at 600: 1 s
        b.arc(60, 0, 0, centre=(50, 0, 0), clockwise=False, f=600 * math.pi * 2 / 6)  # full circle r=10: 6 s
        b.dwell(0.5)
        path = b.build()
        lengths = path.lengths()
        self.assertAlmostEqual(60.0, lengths[0])
        self.assertAlmostEqual(2 * math.pi * 10, lengths[2])
        self.assertEqual(0.0, lengths[3])
        self.assertAlmostEqual(10.0 + 0.6 + 1.0 + 6.0 + 0.5, path.time_s(Machine()), places=6)

    def test_a_spindle_start_from_standstill_costs_the_spin_up_wait(self):
        class Slow(Machine):
            spindle_spinup_s = 2.0

        b = ToolpathBuilder((0, 0, 10))
        b.event("tool", tool="T1", number=1)
        b.event("spindle", rpm=1000, dir="cw")            # from standstill: 2 s
        b.rapid(x=60)
        b.event("spindle", rpm=1000, dir="ccw")           # a reversal: no wait
        b.rapid(x=0)
        b.event("stop", optional=True)                    # started again after the stop: 2 s
        b.rapid(x=60)
        b.event("tool", tool="T2", number=2)              # a tool change stops it
        b.event("spindle", rpm=1000, dir="cw")            # 2 s
        b.rapid(x=0)
        path = b.build()
        self.assertAlmostEqual(4 * 0.6 + 2 * 10.0 + 3 * 2.0, path.time_s(Slow()), places=6)
        self.assertAlmostEqual(4 * 0.6 + 2 * 10.0, path.time_s(Machine()), places=6)   # none set: no wait

    def test_sampling_keeps_arcs_within_the_chord_tolerance_and_times_increase(self):
        b = ToolpathBuilder((10, 0, 0))
        b.arc(-10, 0, -2, centre=(0, 0, 0), clockwise=True, f=1000)   # a helical half turn
        b.feed(x=-10, y=-30, z=-2, f=1000)
        path = b.build()
        samples = path.sample(0.01, machine=Machine(), max_step_mm=1.0)
        on_arc = samples.points[samples.move == 0]
        radii = np.linalg.norm(on_arc[:, :2], axis=1)
        self.assertTrue(np.allclose(radii, 10.0))
        chords = np.diff(np.vstack([[10, 0, 0], on_arc])[:, :2], axis=0)
        sagitta = 10.0 - np.sqrt(100.0 - (np.linalg.norm(chords, axis=1) / 2) ** 2)
        self.assertLessEqual(float(sagitta.max()), 0.01 + 1e-9)
        # Clockwise from +X goes through -Y.
        self.assertLess(on_arc[len(on_arc) // 2][1], 0)
        self.assertTrue(np.all(np.diff(samples.t) >= 0))
        self.assertTrue(np.allclose(samples.points[-1], [-10, -30, -2]))
        self.assertLessEqual(np.diff(samples.points[samples.move == 1], axis=0).max(), 1.0 + 1e-9)
        points, t, op, kind = samples
        self.assertEqual(len(points), len(t))

    def test_concat_shifts_ops_and_cycle_events(self):
        a = ToolpathBuilder((0, 0, 5))
        a.begin_op(index=0, setup="top", op="face", plain="Face", tool="T1")
        a.feed(x=10, f=100)
        a.end_op()
        b = ToolpathBuilder((10, 0, 5))
        b.begin_op(index=1, setup="top", op="drill", plain="Drill", tool="T2")
        handle = b.begin_cycle(cycle="drill", holes=[[0, 0, 0]])
        b.feed(z=-5, f=100)
        b.rapid(z=5)
        b.end_cycle(handle)
        b.end_op()
        joined = concat([a.build(), b.build()])
        self.assertEqual([(0, 1), (1, 3)], [(op.start, op.end) for op in joined.ops])
        cycle = next(e for e in joined.events if e.kind == "cycle")
        self.assertEqual((1, 3), (cycle.at, cycle.data["end"]))
        self.assertEqual([FEED, FEED, RAPID], list(joined.moves["kind"]))


class TwoD(unittest.TestCase):
    def test_a_box_mesh_sections_to_its_rectangle_with_a_hole(self):
        import shapely

        from cadgen._internal.cam.part import _read_dxf  # noqa: F401 (the DXF extruder shares the mesh shape)

        outer = shapely.box(-20, -10, 20, 10).difference(shapely.Point(0, 0).buffer(4, quad_segs=32))
        vertices, triangles = _extrude(outer, 5.0)
        section = geom2d.Sections(vertices, triangles).at(2.5)
        self.assertAlmostEqual(outer.area, section.area, places=6)
        self.assertEqual(1, len(section.interiors) if section.geom_type == "Polygon" else -1)
        self.assertTrue(geom2d.Sections(vertices, triangles).at(6.0).is_empty)

    def test_offsets_and_ring_orientation(self):
        import shapely

        square = shapely.box(0, 0, 20, 20).difference(shapely.box(8, 8, 12, 12))
        inset = geom2d.offset(square, -3, tolerance=0.001)
        # The inset square's sides are 3 from the walls; the island grew by 3 with round corners.
        x0, y0, x1, y1 = inset.bounds
        self.assertAlmostEqual(3.0, x0)
        self.assertAlmostEqual(17.0, x1)
        self.assertAlmostEqual(3.0, float(inset.interiors[0].distance(shapely.box(8, 8, 12, 12))), delta=0.0011)
        rings = geom2d.rings(inset, climb=True)
        signed = [_signed_area(ring) for ring in rings]
        self.assertGreater(signed[0], 0)    # the pocket wall: counter-clockwise (material on the right)
        self.assertLess(signed[1], 0)       # around the island: clockwise
        conventional = [_signed_area(ring) for ring in geom2d.rings(inset, climb=False)]
        self.assertEqual([-1, 1], [int(math.copysign(1, a)) for a in conventional])
        circle = geom2d.offset(shapely.Point(0, 0), 5.0, tolerance=0.001)
        coords = np.asarray(circle.exterior.coords)
        self.assertTrue(np.all(np.abs(np.linalg.norm(coords, axis=1) - 5.0) < 1e-9))
        self.assertLess(abs(circle.area - math.pi * 25.0) / (math.pi * 25.0), 1e-3)


class Linking(unittest.TestCase):
    def test_a_helix_keeps_its_pitch_and_ends_flat(self):
        b = ToolpathBuilder((3, 0, 10))
        linking.helix(b, (0, 0), 3.0, 10.0, 4.0, angle_deg=3.0, f=500)
        path = b.build()
        arcs = path.moves[path.moves["kind"] == ARC_CCW]
        pitch = 2 * math.pi * 3.0 * math.tan(math.radians(3.0))
        drops = -np.diff(np.concatenate([[10.0], arcs["z"]]))
        self.assertLessEqual(float(drops.max()), pitch / 2 + 1e-9)
        self.assertAlmostEqual(4.0, float(arcs["z"][-1]))
        self.assertAlmostEqual(0.0, float(drops[-1]))           # the last circle is flat
        self.assertTrue(np.allclose(path.ends()[-1], [3, 0, 4]))

    def test_a_ramp_zigzags_down_at_its_angle(self):
        b = ToolpathBuilder((0, 0, 5))
        self.assertTrue(linking.ramp(b, [[0, 0], [40, 0]], 0.0, -3.0, angle_deg=5.0, f=500))
        path = b.build()
        pos = path.positions()
        rise = np.abs(np.diff(pos[:, 2]))
        run = np.linalg.norm(np.diff(pos[:, :2], axis=0), axis=1)
        sloped = run > 1e-9
        self.assertTrue(np.all(rise[sloped] / run[sloped] <= math.tan(math.radians(5.0)) + 1e-9))
        self.assertTrue(np.allclose(pos[-1], [0, 0, -3]))

    def test_tabs_lift_the_path_over_their_span(self):
        square = np.array([[0, 0, -6], [100, 0, -6], [100, 100, -6], [0, 100, -6], [0, 0, -6]], dtype=float)
        tabbed = linking.apply_tabs(square, tab_top=-4.0, count=4, width=4.0, tool_diameter=6.0)
        lifted = tabbed[np.isclose(tabbed[:, 2], -4.0)]
        self.assertTrue(len(lifted) >= 8)
        segments = np.linalg.norm(np.diff(tabbed[:, :2], axis=0), axis=1)
        on_tab = (np.isclose(tabbed[:-1, 2], -4.0) & np.isclose(tabbed[1:, 2], -4.0))
        self.assertAlmostEqual(4 * 10.0, float(segments[on_tab].sum()), places=6)

    def test_a_lead_arc_is_tangent_and_away_from_the_material(self):
        start, centre, clockwise = linking.lead_arc((0, 0), (1, 0), radius=2.0, material_on_right=True)
        self.assertEqual((0.0, 2.0), tuple(round(v, 9) for v in centre))   # left of travel, away from material
        self.assertEqual((-2.0, 2.0), tuple(round(v, 9) for v in start))
        self.assertFalse(clockwise)


def _signed_area(ring) -> float:
    ring = np.asarray(ring)
    return 0.5 * float(np.sum(ring[:-1, 0] * ring[1:, 1] - ring[1:, 0] * ring[:-1, 1]))


def _extrude(polygon, height: float):
    """A closed, outward-wound prism mesh of a polygon (the DXF extruder's shape)."""
    import shapely

    vertices, triangles = [], []
    for tri in shapely.get_parts(shapely.constrained_delaunay_triangles(polygon)):
        coords = np.asarray(tri.exterior.coords)[:3]
        e1, e2 = coords[1] - coords[0], coords[2] - coords[0]
        if e1[0] * e2[1] - e1[1] * e2[0] < 0:
            coords = coords[[0, 2, 1]]
        for z, order in ((height, [0, 1, 2]), (0.0, [0, 2, 1])):
            triangles.append(np.arange(3) + len(vertices))
            vertices.extend([[*coords[i], z] for i in order])
    oriented = shapely.geometry.polygon.orient(polygon, 1.0)
    for ring in (oriented.exterior, *oriented.interiors):
        coords = np.asarray(ring.coords)
        for a, b in zip(coords[:-1], coords[1:]):
            base = len(vertices)
            vertices.extend([[a[0], a[1], 0], [b[0], b[1], 0], [b[0], b[1], height], [a[0], a[1], height]])
            triangles.extend([np.array([0, 1, 2]) + base, np.array([0, 2, 3]) + base])
    return np.asarray(vertices, dtype=float), np.asarray(triangles)


if __name__ == "__main__":
    unittest.main()
