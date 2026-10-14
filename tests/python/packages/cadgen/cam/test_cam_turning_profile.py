"""Turning geometry: the turned profile read off the exact solid, the lathe tools' shapes, the bar's placement, the
lathe stock simulator, and the job's lathe teaching errors."""

from __future__ import annotations

import math
import unittest

import numpy as np
import shapely

from cadgen._internal.cam.ir import ToolpathBuilder
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations
from cadgen._internal.cam.stock import build_stock
from cadgen._internal.cam.stock_lathe import LatheSim, pappus, revolve
from cadgen._internal.cam.tools import parse_tool
from cadgen._internal.cam.turn_profile import envelope, minkowski, read_profile, tool_shape
from cadgen._internal.cam.wcs import build_wcs
from tests.python.support.cam_fixtures import class_directory
from tests.python.support.cam_fixtures_turning import SECTION, SHAFT, block_step, lathe_job, shaft_step

#: The shaft's part z in the lathe WCS (zero at the bar's front, 1 mm proud of the part).
def W(z: float) -> float:
    return z - 61.0


def setup_for(part, job):
    stock = build_stock(job.stock, part)
    wcs = build_wcs(job.setups[0], stock_points=stock.vertices, part_points=part.vertices, machine=job.machine)
    return stock, wcs


class Profile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = class_directory(cls)
        cls.part = read_part(shaft_step(folder))
        cls.cross = read_part(shaft_step(folder, "cross", cross_hole=True))
        cls.block = read_part(block_step(folder))
        cls.along_x = read_part(shaft_step(folder, "along_x", along_x=True))
        cls.job = parse_job(lathe_job([{"op": "turn_face", "tool": "T1"}]))

    def test_the_envelope_is_the_revolved_section(self):
        stock, wcs = setup_for(self.part, self.job)
        profile = read_profile(self.part, wcs)
        self.assertAlmostEqual(W(60.0), profile.z_front, places=4)
        self.assertAlmostEqual(W(0.0), profile.z_back, places=4)
        self.assertAlmostEqual(18.0, profile.r_max, places=4)
        exact = shapely.Polygon(SECTION)
        zs = np.linspace(0.3, 59.7, 200)
        for z, r in zip(zs, profile.r_out([W(z) for z in zs])):
            outer = shapely.intersection(exact, shapely.LineString([(0, z), (100, z)])).bounds[2]
            self.assertAlmostEqual(outer, r, delta=0.01, msg=f"OD at part z {z}")
        bore = profile.r_in([W(52.0), W(46.0), W(30.0)])
        self.assertEqual([5.0, 5.0, 0.0], [round(float(v), 4) for v in bore])
        self.assertLess(shapely.symmetric_difference(profile.region, shapely.affinity.translate(exact, 0, -61)).area,
                        0.05)
        self.assertEqual((), profile.off_axis)
        self.assertIsNone(profile.note)

    def test_off_axis_features_are_named_and_vanish_from_the_envelope(self):
        stock, wcs = setup_for(self.cross, self.job)
        profile = read_profile(self.cross, wcs)
        self.assertEqual(1, len(profile.off_axis))
        self.assertIn("cross holes", profile.note)
        self.assertIn(profile.off_axis[0], profile.note)
        # Through the hole's height the OD is still the full Ø30.
        self.assertAlmostEqual(15.0, float(profile.r_out([W(36.0)])[0]), places=3)

    def test_a_part_not_turned_about_the_axis_is_refused_in_a_sentence(self):
        stock, wcs = setup_for(self.block, self.job)
        with self.assertRaisesRegex(CamJobError, "not a body of revolution about this setup's spindle axis"):
            read_profile(self.block, wcs)

    def test_a_shaft_along_x_turned_about_z_says_to_turn_it_about_x(self):
        job = parse_job(lathe_job([{"op": "turn_face", "tool": "T1"}],
                                  stock={"kind": "cylinder", "diameter_mm": 80, "length_mm": 75}))
        stock, wcs = setup_for(self.along_x, job)
        with self.assertRaisesRegex(CamJobError, r"orientation to \+X \(and stock.axis to \"x\"\)"):
            read_profile(self.along_x, wcs)

    def test_the_bar_stands_proud_of_the_front_on_the_turning_axis(self):
        stock, wcs = setup_for(self.cross, self.job)
        cylinder = stock.cylinder
        self.assertEqual([0.0, 0.0], [round(v, 6) + 0.0 for v in cylinder["center"][:2]])
        self.assertAlmostEqual(61.0, cylinder["end"], places=6)
        self.assertAlmostEqual(61.0 - 75.0, cylinder["start"], places=6)
        with self.assertRaisesRegex(CamJobError, "shorter than the part plus face_stock_mm"):
            build_stock(parse_job(lathe_job([{"op": "turn_face", "tool": "T1"}], stock={
                "kind": "cylinder", "diameter_mm": 40, "length_mm": 60.5})).stock, self.part)


class Shapes(unittest.TestCase):
    def tool(self, **raw):
        return parse_tool({"id": "T1", **raw}, 0)

    def test_an_od_insert_touches_off_at_its_lowest_x_and_z(self):
        for insert in ("C", "D", "V", "W"):
            shape = tool_shape(self.tool(type="turn", insert=insert, nose_radius_mm=0.8), "od")[0]
            nose = shape[:24]
            self.assertAlmostEqual(0.0, float(nose[:, 0].min()), places=9)
            self.assertAlmostEqual(0.0, float(nose[:, 1].min()), places=9)
            self.assertGreater(float(shape[:, 0].max()), 100.0, "the holder runs out radially")

    def test_a_boring_bar_mirrors_it_and_its_bar_runs_out_along_z(self):
        shape = tool_shape(self.tool(type="turn", insert="D", nose_radius_mm=0.4), "id", reach_mm=4.0)[0]
        self.assertAlmostEqual(0.0, float(shape[:24, 0].max()), places=9)
        self.assertAlmostEqual(0.0, float(shape[:, 1].min()), places=9)
        self.assertGreater(float(shape[:, 1].max()), 100.0)
        self.assertLess(float(shape[:, 0].min()), -3.5)

    def test_the_insert_angle_limits_how_steeply_a_profile_can_fall_away(self):
        # A 30° back taper (radius falling towards the chuck): a C insert (5° end clearance) cannot follow it, a V
        # (52°) can. The envelope of the part grown by the reflected tool shows which.
        taper = shapely.Polygon([(0, 0), (10, 0), (10 - 10 * math.tan(math.radians(30)), -10), (0, -10)])
        for insert, follows in (("C", False), ("V", True)):
            shape = tool_shape(self.tool(type="turn", insert=insert, nose_radius_mm=0.2), "od")
            forbidden = minkowski(taper, [-s for s in shape])
            path = envelope(forbidden, side="max", z_low=-9.0, z_high=-1.0)
            fall = path[0, 0] - path[-1, 0]
            self.assertEqual(follows, fall > 4.0, f"{insert}: falls {fall:.2f} mm over 8 mm")

    def test_a_grooving_blade_spans_its_width_from_its_chuck_side_corner(self):
        shape = tool_shape(self.tool(type="groove", width_mm=3.0), "groove")[0]
        self.assertEqual((0.0, 0.0), (float(shape[:, 0].min()), float(shape[:, 1].min())))
        self.assertAlmostEqual(3.0, float(shape[:, 1].max()), places=9)


class LatheStock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.part = read_part(shaft_step(class_directory(cls)))
        cls.job = parse_job(lathe_job([{"op": "turn_face", "tool": "T1"}]))
        cls.stock, cls.wcs = setup_for(cls.part, cls.job)
        cls.tools = {tool.id: tool for tool in cls.job.tools}

    def path(self, moves, tool="T1", role="od"):
        from cadgen._internal.cam.ir import OpRange, Toolpath

        b = ToolpathBuilder((25.0, 0.0, 5.0), lathe=True)
        for kind, x, z in moves:
            getattr(b, kind)(x=x, z=z, **({} if kind == "rapid" else {"f": 100.0}))
        built = b.build()
        return Toolpath(built.moves, built.events, [OpRange(0, "turn", "turn_rough", "Rough turn", tool, 0,
                                                            len(built.moves), {"lathe": {"role": role}})],
                        start=built.start, lathe=True)

    def test_a_pass_removes_the_ring_it_sweeps_and_pappus_measures_it(self):
        sim = LatheSim(self.stock, self.part)
        before = sim.volume()
        self.assertAlmostEqual(math.pi * 20 ** 2 * 75, before, delta=1e-6 * before)
        report = sim.cut(self.path([("rapid", 18.0, 2.0), ("feed", 18.0, -30.0), ("rapid", 25.0, -30.0)]),
                         self.tools, self.wcs)
        # A ring from r 18 to 20 over 32 mm, less the nose's rounding at its end.
        ring = math.pi * (20 ** 2 - 18 ** 2) * 30.0
        self.assertAlmostEqual(ring, report.removed_mm3_by_op[0], delta=0.01 * ring)
        self.assertAlmostEqual(before - sim.volume(), report.removed_mm3_by_op[0], delta=1e-6 * before)
        vertices, triangles = sim.mesh()
        tri = vertices[triangles]
        mesh_volume = float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)
        self.assertAlmostEqual(sim.volume(), mesh_volume, delta=0.01 * sim.volume())
        self.assertEqual([], report.rapid_hits)

    def test_a_rapid_through_the_bar_is_a_hit(self):
        sim = LatheSim(self.stock, self.part)
        report = sim.cut(self.path([("rapid", 15.0, 2.0), ("rapid", 15.0, -10.0), ("rapid", 25.0, -10.0)]),
                         self.tools, self.wcs)
        self.assertEqual(1, len(report.rapid_hits))
        self.assertGreater(report.rapid_hits[0]["depth_mm"], 1.0)

    def test_material_left_is_the_stock_proud_of_the_turned_section(self):
        sim = LatheSim(self.stock, self.part)
        sim.cut(self.path([("rapid", 25.0, 2.0)]), self.tools, self.wcs)
        left = sim.material_left(self.part, stock_to_leave_mm=0.0, tolerance_mm=0.01)
        # Everything between the bar and the part, ahead of the part's back end (behind it is bar, not part).
        bar = shapely.box(0, W(0.0), 20, 0.0)
        expected = pappus(shapely.difference(bar, shapely.affinity.translate(shapely.Polygon(SECTION), 0, -61)))
        self.assertAlmostEqual(expected, left.volume_mm3, delta=0.01 * expected)
        # The proudest point is the bar's front corner, sqrt(10² + 2²) from the thread's chamfer.
        self.assertAlmostEqual(math.hypot(10.0, 2.0), left.max_mm, delta=0.02)

    def test_revolve_closes_a_ring(self):
        vertices, triangles = revolve(shapely.box(2.0, 0.0, 3.0, 10.0), 2, np.zeros(3), segments=96)
        tri = vertices[triangles]
        volume = float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)
        self.assertAlmostEqual(math.pi * (9 - 4) * 10, volume, delta=0.01 * volume)


class LatheJobs(unittest.TestCase):
    def refuse(self, pattern, operations, **job):
        with self.assertRaisesRegex(CamJobError, pattern):
            parse_operations(parse_job(lathe_job(operations, **job)))

    def test_lathe_teaching_errors(self):
        self.refuse("a lathe turns bar stock", [{"op": "turn_face", "tool": "T1"}],
                    stock={"kind": "box", "margin_mm": 1})
        self.refuse(r"the bar runs along x; set stock.axis to \"z\"", [{"op": "turn_face", "tool": "T1"}],
                    stock={"kind": "cylinder", "diameter_mm": 40, "length_mm": 75, "axis": "x"})
        self.refuse("a lathe's work zero sits on the spindle axis", [{"op": "turn_face", "tool": "T1"}],
                    setups=[{"id": "t", "origin": "stock-top-corner", "operations": [{"op": "turn_face", "tool": "T1"}]}])
        self.refuse("left-hand turning tool", [{"op": "turn_rough", "tool": "L1"}],
                    tools=[{"id": "L1", "type": "turn", "side": "left"}])
        self.refuse("a turn_rough cuts with a turn tool", [{"op": "turn_rough", "tool": "T3"}])
        self.refuse("side is 'in'", [{"op": "turn_rough", "tool": "T1", "side": "in"}])
        self.refuse("unknown key 'depth'", [{"op": "turn_rough", "tool": "T1", "depth": 1}])
        self.refuse("name the threaded cylinder", [{"op": "turn_thread", "tool": "T4"}])
        self.refuse("z_end_mm must be behind z_start_mm", [{"op": "turn_thread", "tool": "T4", "z_start_mm": -5,
                                                             "z_end_mm": 0, "major_diameter_mm": 20}])
        self.refuse("give depth_mm or z_mm, not both", [{"op": "turn_drill", "tool": "T6", "depth_mm": 5,
                                                          "z_mm": -5}])
        self.refuse("spring_passes must be a whole number", [{"op": "turn_finish", "tool": "T2",
                                                               "spring_passes": 1.5}])


if __name__ == "__main__":
    unittest.main()
