"""``cut`` on a laser, a plasma, a waterjet and a router: kerf on the waste side, holes first, pierces off corners."""

from __future__ import annotations

import math
import unittest

import numpy as np

from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, FEED, PLUNGE, RAPID
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.part import read_part
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures import class_directory, quiet, read_glb
from tests.python.support.cam_fixtures_cutting import (
    BRACKET, bracket_area, bracket_dxf, cut_job, plate_step, pocketed_plate_step,
)

MARGIN = 5.0     # cut_job's sheet margin: with origin stock-top-corner, WCS = part + (5, 5)


def design_wcs():
    """The bracket's two parts as shapely polygons in the job's WCS."""
    import shapely

    from cadgen._internal.cam.part import read_dxf_profiles

    return [shapely.affinity.translate(p, MARGIN, MARGIN) for p in read_dxf_profiles(BracketCut.dxf)]


def beam_groups(path):
    """Per beam-on: (move indices it covers, the cutting points (M, 2) WCS)."""
    ons = [e.at for e in path.events if e.kind == "beam" and e.data.get("on")]
    offs = [e.at for e in path.events if e.kind == "beam" and not e.data.get("on")]
    groups = []
    for start in ons:
        end = min(o for o in offs if o >= start)
        rows = path.moves[start:end]
        cutting = np.isin(rows["kind"], (FEED, ARC_CW, ARC_CCW))
        points = np.column_stack([rows["x"], rows["y"]])[cutting]
        groups.append((start, end, points))
    return groups


class BracketCut(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = class_directory(cls)
        cls.dxf = bracket_dxf(cls.directory)
        cls.part = read_part(cls.dxf, sheet_thickness_mm=3.0)

    def plan(self, kind, operation=None, **job):
        parsed = parse_job(cut_job(kind, operation, **job))
        part = read_part(self.dxf, sheet_thickness_mm=parsed.stock.thickness_mm)
        stock = build_stock(parsed.stock, part)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), part, stock)
        return parsed, part, stock, setups[0], ops[0]

    def sim(self, parsed, part, stock, setup):
        from cadgen._internal.cam.stock_sheet import SheetSim

        sim = SheetSim(stock, part, tolerance_mm=parsed.tolerance_mm)
        sim.cut(setup.toolpath, {t.id: t for t in parsed.tools}, setup.wcs)
        return sim

    def test_the_kerf_is_on_the_waste_side_so_each_part_comes_out_at_its_design_size(self):
        import shapely

        from cadgen._internal.cam.geom2d import polygons_of

        design = design_wcs()
        union = shapely.union_all(design)
        for kind, kerf in (("laser", 0.2), ("plasma", 1.5), ("waterjet", 0.9)):
            with self.subTest(kind=kind):
                parsed, part, stock, setup, op = self.plan(kind)
                # Every cutting move keeps half the kerf off the part: a hole cut on the wrong side would sit in it.
                samples = setup.toolpath.sample(0.01)
                cutting = np.isin(samples.kind, (FEED, ARC_CW, ARC_CCW))
                points = shapely.points(samples.points[cutting][:, :2])
                distance = shapely.distance(points, union)
                self.assertGreaterEqual(float(distance.min()), kerf / 2 - 0.011)
                self.assertAlmostEqual(kerf / 2, float(np.median(distance)), delta=0.011)
                # The simulated sheet: each part's piece is the part, within the corners the kerf cannot reach.
                sim = self.sim(parsed, part, stock, setup)
                pieces = polygons_of(sim.sheet.difference(sim.removed))
                for polygon in (shapely.affinity.translate(p, -MARGIN, -MARGIN) for p in design):
                    piece = max(pieces, key=lambda q: q.intersection(polygon).area)
                    corners = 6 * (1 - math.pi / 4) * (kerf / 2) ** 2
                    self.assertLess(abs(piece.area - polygon.area), corners + 0.02 * polygon.length)
                    self.assertLess(shapely.symmetric_difference(piece, polygon).area, corners + 0.02 * polygon.length)
                self.assertAlmostEqual(bracket_area(), sum(p.area for p in design), delta=1.0)
                self.assertEqual({"parts": 2, "parts_free": 2, "parts_held": 0},
                                 {k: op.meta["cut"][k] for k in ("parts", "parts_free", "parts_held")})

    def test_holes_are_cut_before_the_outline_that_holds_them(self):
        import shapely

        design = design_wcs()
        _, _, _, setup, _ = self.plan("laser")
        order = []
        for _, _, points in beam_groups(setup.toolpath):
            cloud = shapely.points(points)
            for index, polygon in enumerate(design):
                holes = [shapely.Polygon(ring) for ring in polygon.interiors]
                if any(np.mean(shapely.contains(hole, cloud)) > 0.5 for hole in holes):
                    order.append((index, "hole"))
                elif np.median(shapely.distance(cloud, polygon.exterior)) < 1.0:
                    order.append((index, "outside"))
        self.assertEqual(8, len(order))
        for index in (0, 1):
            mine = [k for k, (part, _) in enumerate(order) if part == index]
            outside = [k for k in mine if order[k][1] == "outside"]
            self.assertEqual([mine[-1]], outside, order)

    def test_pierces_and_lead_ins_sit_off_the_corners(self):
        parsed, _, _, setup, op = self.plan("laser")
        corners = [np.add(c, MARGIN) for c in BRACKET["outline"]]
        cx, cy = BRACKET["square_hole"]["center"]
        h = BRACKET["square_hole"]["size"] / 2
        corners += [np.add((cx + sx * h, cy + sy * h), MARGIN) for sx in (-1, 1) for sy in (-1, 1)]
        moves = setup.toolpath.moves
        for start, end, _ in beam_groups(setup.toolpath):
            # After the beam comes on: the drop to the cut height, then the lead-in, which ends on the profile.
            k = next(i for i in range(start, end) if int(moves[i]["kind"]) not in (PLUNGE, RAPID))
            joint = np.array([moves[k]["x"], moves[k]["y"]])
            self.assertGreaterEqual(min(np.hypot(*(joint - c)) for c in corners), 1.0, joint)
        self.assertEqual(8, op.meta["cut"]["leads_in"])
        self.assertTrue(all(e.data["pierce_s"] > 0 for e in setup.toolpath.events if e.kind == "beam"
                            and e.data.get("on")))

    def test_corners_slow_down_and_straights_run_at_speed(self):
        parsed, _, _, setup, op = self.plan("plasma")
        speed = op.meta["cut"]["speed_mm_min"]
        feeds = setup.toolpath.moves["feed"][setup.toolpath.moves["kind"] == FEED]
        self.assertAlmostEqual(speed, float(feeds.max()), places=3)
        # A square corner turns 90°: cos²(45°) = half speed.
        self.assertIn(round(speed * 0.5, 1), set(np.round(feeds, 1).tolist()))
        self.assertGreater(op.meta["cut"]["corners_slowed"], 8)

    def test_microjoints_hold_the_parts_and_the_beam_jumps_each_one(self):
        parsed, part, stock, setup, op = self.plan("laser", {"tabs": {"count": 2, "width_mm": 0.5}})
        cut = op.meta["cut"]
        self.assertEqual((4, 0, 2), (cut["tabs"], cut["parts_free"], cut["parts_held"]))
        ons = [e for e in setup.toolpath.events if e.kind == "beam" and e.data.get("on")]
        self.assertEqual(8 + 4, len(ons))
        # Each gap is a rapid over the joint's width plus the kerf.
        moves = setup.toolpath.moves
        positions = setup.toolpath.positions()
        jumps = [float(np.hypot(*(positions[i + 1][:2] - positions[i][:2]))) for i in range(len(moves))
                 if int(moves[i]["kind"]) == RAPID and abs(positions[i][2] - positions[i + 1][2]) < 1e-9
                 and 0 < np.hypot(*(positions[i + 1][:2] - positions[i][:2])) < 2]
        self.assertEqual(4, len(jumps))
        self.assertTrue(all(abs(j - 0.7) < 0.02 for j in jumps), jumps)
        left = self.sim(parsed, part, stock, setup).material_left(part, stock_to_leave_mm=0.0, tolerance_mm=0.01)
        self.assertLess(left.volume_mm3, 1.0)

    def test_small_plasma_holes_are_slowed_and_flagged(self):
        parsed, _, _, setup, op = self.plan("plasma", thickness=6.0)
        # Ø6 and the washer's Ø8 are under 1.5 x 6 mm; the 8 mm square and the slot are not.
        self.assertEqual(4, op.meta["cut"]["small_holes"])
        self.assertIn("4 holes under 1.5x the 6 mm thickness", op.meta["note"])
        speed = op.meta["cut"]["speed_mm_min"]
        group = beam_groups(setup.toolpath)[0]
        rows = setup.toolpath.moves[group[0]:group[1]]
        self.assertAlmostEqual(0.6 * speed, float(rows["feed"][rows["kind"] == FEED].max()), delta=1.0)

    def test_a_router_steps_down_through_the_sheet_and_lifts_over_tabs(self):
        parsed, _, stock, setup, op = self.plan("router", material="plywood", thickness=12.0)
        heights = setup.heights
        moves = setup.toolpath.moves
        cutting = moves[moves["kind"] != RAPID]
        self.assertAlmostEqual(heights.stock_bottom - 0.3, float(cutting["z"].min()), places=6)
        cut = op.meta["cut"]
        self.assertGreater(cut["depths"], 1)
        tab_top = heights.stock_bottom + cut["tab_height_mm"]
        self.assertAlmostEqual(3.0, cut["tab_height_mm"])
        self.assertTrue(np.any(np.isclose(cutting["z"], tab_top)))
        self.assertGreater(cut["tabs"], 0)
        # The three Ø6 holes are the bit's own size: plunged, at each depth; everything else is ramped into, the
        # washer's round hole by helical arcs.
        self.assertEqual(3 * cut["depths"], op.meta["plunges"])
        helical = moves[np.isin(moves["kind"], (ARC_CW, ARC_CCW))]
        self.assertGreater(len(helical), cut["depths"])
        # The bit's radius leaves the square hole's four corners and the outline's inside corner.
        self.assertEqual(5, len(op.meta["unreachable"]))

    def test_job_errors_teach(self):
        cases = {
            "a plasma cuts conductive metal only": cut_job("plasma", material="acrylic"),
            "a laser cuts with a beam tool": cut_job("laser", tool={"id": "T1", "type": "flat", "diameter_mm": 6}),
            "a router cuts sheet with a flat end mill": cut_job("router", tool={"id": "T1", "type": "beam",
                                                                                "kerf_mm": 1}),
            "unknown key 'quality'": cut_job("laser", {"quality": 2}),
            "quality is a waterjet's edge quality": cut_job("waterjet", {"quality": 7}),
            "machine.amps is a plasma's setting": cut_job("laser", machine={"kind": "laser", "amps": 45}),
            "a laser has no spindle": cut_job("laser", {"speed": 1000}),
        }
        for expected, job in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaises(CamJobError) as caught:
                    parsed = parse_job(job)
                    part = read_part(self.dxf, sheet_thickness_mm=parsed.stock.thickness_mm)
                    plan_setups(parsed, parse_operations(parsed), part, build_stock(parsed.stock, part))
                self.assertIn(expected, str(caught.exception))
        job = cut_job("laser")
        job["setups"][0]["orientation"] = "+X"
        with self.assertRaisesRegex(CamJobError, "a sheet is cut from above"):
            parse_operations(parse_job(job))

    def test_cam_plan_writes_the_program_and_the_cut_sheet(self):
        from cadgen import cam

        from tests.python.support import gcode_reader

        with quiet():
            result = cam.plan(self.dxf, job=cut_job("laser"), out_dir=self.directory / "laser")
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("ready", result.verdict["status"])
        row = result.operations[0]
        self.assertIsNone(row["rpm"])
        self.assertEqual(3000.0, row["feed_mm_min"])
        self.assertEqual(2, row["facts"]["cut"]["parts_free"])
        document, _ = read_glb(result.glb)
        stock = document["scenes"][0]["extras"]["cam"]["stock"]
        self.assertEqual("sheet", stock["kind"])
        text = (self.directory / "laser" / "bracket.sheet.nc").read_text(encoding="utf-8")
        self.assertIn("M4 S1000", text)
        program = gcode_reader.read(text, start=(0.0, 0.0, 5.0))
        cuts = np.array([m.end for m in program.moves if m.kind != "rapid"])
        # The bracket and the washer, inside the sheet's 5 mm margin.
        self.assertGreater(float(cuts[:, 0].min()), 0.0)
        self.assertLess(float(cuts[:, 0].max()), 115.0 + 2 * MARGIN)


class PlateCut(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = class_directory(cls)
        cls.directory = directory
        cls.step = plate_step(directory)
        cls.pocketed = pocketed_plate_step(directory)

    def test_a_step_plate_is_cut_from_its_outline(self):
        from cadgen import cam

        with quiet():
            result = cam.plan(self.step, job=cut_job("waterjet", thickness=5.0, material="aluminum-6061"),
                              out_dir=self.directory / "plate")
        self.assertTrue(result.ok, result.findings)
        cut = result.operations[0]["facts"]["cut"]
        # The outline, four holes and the slot.
        self.assertEqual((6, 1, 5), (cut["profiles"], cut["outsides"], cut["holes"]))
        self.assertEqual(1, cut["parts_free"])
        self.assertEqual(5, cut["slugs_drop"])

    def test_a_plate_with_a_pocket_is_refused(self):
        from cadgen import cam

        with quiet():
            result = cam.plan(self.pocketed, job=cut_job("laser", thickness=5.0), out_dir=self.directory / "no")
        self.assertFalse(result.ok)
        self.assertIn("is not a flat plate", result.findings[0]["summary"])


class CuttingSpeeds(unittest.TestCase):
    def test_speeds_scale_with_the_machine(self):
        from types import SimpleNamespace as Machine

        from cadgen._internal.cam.feeds import cut_speed

        laser = cut_speed("steel-1018", Machine(kind="laser", power_w=None, laser_source=None), 3).speed_mm_min
        doubled = cut_speed("steel-1018", Machine(kind="laser", power_w=3000, laser_source=None), 3).speed_mm_min
        self.assertAlmostEqual(2 * laser, doubled)
        self.assertGreater(cut_speed("steel-1018", Machine(kind="plasma", amps=85), 6).speed_mm_min,
                           cut_speed("steel-1018", Machine(kind="plasma", amps=45), 6).speed_mm_min)
        fast = cut_speed("aluminum-6061", Machine(kind="waterjet", abrasive=True), 6, quality=1).speed_mm_min
        fine = cut_speed("aluminum-6061", Machine(kind="waterjet", abrasive=True), 6, quality=5).speed_mm_min
        self.assertAlmostEqual(2.0 / 0.6, fast / fine, places=2)
        self.assertIn("pure water does not cut metal",
                      cut_speed("steel-1018", Machine(kind="waterjet", abrasive=False), 3).why)
        self.assertIn("diode laser does not cut metal",
                      cut_speed("steel-1018", Machine(kind="laser", power_w=10, laser_source="diode"), 1).why)
        thick = cut_speed("steel-1018", Machine(kind="plasma", amps=45), 30)
        self.assertIn("extrapolated", thick.notes[0])


if __name__ == "__main__":
    unittest.main()
