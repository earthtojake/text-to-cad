"""``wire_edm`` (lite): the wire offset on the waste side, start holes, skims back and forth, the hold, the taper."""

from __future__ import annotations

import math
import unittest

import numpy as np

from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, FEED
from cadgen._internal.cam.job import parse_job
from cadgen._internal.cam.job_errors import CamJobError
from cadgen._internal.cam.part import read_part, read_dxf_profiles
from cadgen._internal.cam.run import parse_operations, plan_setups
from cadgen._internal.cam.stock import build_stock
from tests.python.support.cam_fixtures import accessor_array, class_directory, quiet, read_glb
from tests.python.support.cam_fixtures_cutting import bracket_dxf, cut_job

MARGIN = 5.0
WIRE = 0.25
GAP = 0.03


class BracketWire(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shapely

        cls.directory = class_directory(cls)
        cls.dxf = bracket_dxf(cls.directory)
        cls.design = [shapely.affinity.translate(p, MARGIN, MARGIN) for p in read_dxf_profiles(cls.dxf)]
        cls.union = shapely.union_all(cls.design)

    def plan(self, operation=None, **job):
        job.setdefault("thickness", 20.0)
        job.setdefault("material", "tool-steel")
        parsed = parse_job(cut_job("wire_edm", operation, **job))
        part = read_part(self.dxf, sheet_thickness_mm=parsed.stock.thickness_mm)
        setups, ops, _ = plan_setups(parsed, parse_operations(parsed), part, build_stock(parsed.stock, part))
        return setups[0], ops[0]

    def passes(self, path):
        """The cutting points of each pass: split at the beam-on events (one per start hole, skim and hold)."""
        ons = sorted(e.at for e in path.events if e.kind == "beam" and e.data.get("on"))
        offs = sorted(e.at for e in path.events if e.kind == "beam" and not e.data.get("on"))
        bounds = sorted(set(ons + offs + [len(path.moves)]))
        out = []
        for start in ons:
            end = next(b for b in bounds if b > start)
            rows = path.moves[start:end]
            keep = np.isin(rows["kind"], (FEED, ARC_CW, ARC_CCW))
            out.append((start, np.column_stack([rows["x"], rows["y"]])[keep], rows[keep]))
        return out

    def test_each_pass_runs_at_its_offset_on_the_waste_side(self):
        import shapely

        setup, op = self.plan({"skims": 2, "profiles": "holes", "hold_mm": 0})
        cut = op.meta["cut"]
        finish = WIRE / 2 + GAP
        self.assertEqual([round(finish + extra, 4) for extra in (0.08, 0.02, 0.0)], cut["offsets_mm"])
        events = [e for e in setup.toolpath.events if e.kind == "beam" and e.data.get("on")]
        groups = self.passes(setup.toolpath)
        self.assertEqual(len(events), len(groups))
        for event, (_, points, _) in zip(events, groups):
            # Skip the approach from the start hole: the first cutting move.
            distance = shapely.distance(shapely.points(points[1:]), self.union)
            self.assertAlmostEqual(event.data["offset_mm"], float(np.median(distance)), delta=0.006)
            self.assertGreaterEqual(float(distance.min()), finish - 0.011)
        self.assertEqual([6.0, 18.0, 30.0], cut["feeds_mm_min"])

    def test_start_holes_sit_inside_the_openings_and_the_approach_stays_in_them(self):
        import shapely

        setup, op = self.plan({"profiles": "holes", "skims": 0})
        starts = op.meta["cut"]["start_holes"]
        self.assertEqual(6, len(starts))
        holes = [shapely.Polygon(ring) for polygon in self.design for ring in polygon.interiors]
        for start in starts:
            self.assertTrue(any(hole.contains(shapely.Point(start)) for hole in holes), start)
        moves = setup.toolpath.moves
        for event in (e for e in setup.toolpath.events if e.kind == "beam" and e.data.get("on")):
            approach = moves[event.at]
            self.assertEqual(FEED, int(approach["kind"]))
            begin = setup.toolpath.positions()[event.at]
            line = shapely.LineString([begin[:2], (approach["x"], approach["y"])])
            self.assertGreaterEqual(shapely.distance(line, self.union), WIRE / 2 + GAP - 0.011)

    def test_skims_go_back_and_forth_and_the_hold_waits_for_a_stop(self):
        import shapely

        from cadgen._internal.cam import stock_sheet

        setup, op = self.plan({"skims": 2, "hold_mm": 3.0, "profiles": "outside"})
        path = setup.toolpath
        events = [e for e in path.events if e.kind == "beam" and e.data.get("on")]
        # Two outside profiles (the bracket's and the washer's): rough, skim back, skim forward, the hold.
        self.assertEqual(["left", "right", "left", "left"] * 2, [e.data["offset_side"] for e in events])
        self.assertEqual([0, 1, 2, "hold"] * 2, [e.data["pass"] for e in events])
        stops = [e.at for e in path.events if e.kind == "stop"]
        self.assertEqual(2, len(stops))
        # Before the first stop the bracket is still held by the uncut 3 mm; after its hold cut it falls free.
        sheet = shapely.box(0, 0, 200, 200)
        width = WIRE + 2 * GAP
        before = stock_sheet.swept([r[:, :2] for r in stock_sheet.cutting_runs(path.slice(0, stops[0]),
                                                                               tolerance=0.01)], width)
        after = stock_sheet.swept([r[:, :2] for r in stock_sheet.cutting_runs(path, tolerance=0.01)], width)
        outlines = [shapely.Polygon(p.exterior) for p in self.design]
        held = stock_sheet.analyse(sheet, before, outlines[:1], tolerance=0.01)
        freed = stock_sheet.analyse(sheet, after, outlines, tolerance=0.01)
        self.assertEqual([0], held["not_free"])
        self.assertEqual([0, 1], freed["free"])
        self.assertEqual(2, op.meta["cut"]["holds"])

    def test_a_taper_leans_the_wire_by_thickness_times_tan(self):
        setup, op = self.plan({"skims": 1, "hold_mm": 2.0, "taper_deg": 1.5, "profiles": "outside"})
        lean = 20.0 * math.tan(math.radians(1.5))
        self.assertAlmostEqual(lean, op.meta["cut"]["uv_mm"], places=4)
        for _, points, rows in self.passes(setup.toolpath):
            uv = np.hypot(rows["a"][1:], rows["b"][1:])
            self.assertTrue(np.allclose(uv, lean, atol=1e-6), uv)
        events = [e for e in setup.toolpath.events if e.kind == "beam" and e.data.get("on")]
        self.assertEqual([1.5, -1.5, -1.5] * 2, [e.data["taper_deg"] for e in events])
        self.assertEqual((), setup.toolpath.rotary)

    def test_cam_plan_posts_it_and_the_sheet_shows_what_was_not_cut(self):
        from cadgen import cam

        with quiet():
            result = cam.plan(self.dxf, job=cut_job("wire_edm", {"profiles": "outside", "taper_deg": 1.0},
                                                   thickness=10.0, material="tool-steel"),
                              out_dir=self.directory / "wire")
        self.assertTrue(result.ok, result.findings)
        self.assertEqual("lite", result.operations[0]["status"])
        self.assertTrue(result.operations[0]["limits"])
        text = (self.directory / "wire" / "bracket.sheet.nc").read_text(encoding="utf-8")
        self.assertIn("G51 A1.", text)
        self.assertIn("M0", text)
        # The GLB carries the wire's lean on every vertex: 1° off the plate's normal (glTF +Y) while it cuts.
        document, blob = read_glb(result.glb)
        feed = next(m for m in document["meshes"] if m["name"] == "sheet feed")["primitives"][0]
        axis = accessor_array(document, blob, feed["attributes"]["_CAM_AXIS"])
        np.testing.assert_allclose(1.0, np.linalg.norm(axis, axis=1), atol=1e-6)
        tilt = np.degrees(np.arccos(np.clip(axis[:, 1], -1, 1)))
        self.assertAlmostEqual(1.0, float(tilt.max()), places=4)
        # Only the outsides were meant to be cut (a punch): its openings are not material left.
        self.assertEqual([], [f for f in result.findings if f["check"] == "material_left"])
        # A die (only the openings cut): the plate is the part, and nothing is left in its openings.
        with quiet():
            die = cam.plan(self.dxf, job=cut_job("wire_edm", {"profiles": "holes", "skims": 0}, thickness=10.0,
                                                material="tool-steel"), out_dir=self.directory / "die")
        self.assertEqual([], [f for f in die.findings if f["check"] == "material_left"])
        self.assertEqual(6, die.operations[0]["facts"]["cut"]["slugs_drop"])

    def test_the_sheet_simulation_finds_openings_a_job_meant_to_free_left_uncut(self):
        from dataclasses import replace

        from cadgen._internal.cam.ir import Toolpath
        from cadgen._internal.cam.stock_sheet import SheetSim

        setup, op = self.plan({"profiles": "outside", "skims": 0})
        path = setup.toolpath
        # The same cut, judged as if it were meant to free whole parts (holes and all).
        ops = [replace(r, meta={**r.meta, "sheet_cuts": "all"}) for r in path.ops]
        path = Toolpath(path.moves, path.events, ops, start=path.start)
        parsed = parse_job(cut_job("wire_edm", thickness=20.0, material="tool-steel"))
        part = read_part(self.dxf, sheet_thickness_mm=20.0)
        sim = SheetSim(build_stock(parsed.stock, part), part)
        sim.cut(path, {t.id: t for t in parsed.tools}, setup.wcs)
        left = sim.material_left(part, stock_to_leave_mm=0.0, tolerance_mm=0.01)
        holes = 3 * math.pi * 9 + 64 + (15 * 6 + math.pi * 9) + math.pi * 16
        self.assertAlmostEqual(holes, left.area_mm2, delta=3.0)
        self.assertAlmostEqual(holes * 20.0, left.volume_mm3, delta=60.0)
        self.assertEqual({"parts": 2, "free": [], "not_free": [0, 1]},
                         {k: v for k, v in sim.pieces(part).items() if k in ("parts", "free", "not_free")})

    def test_job_errors_teach(self):
        cases = {
            "skims is the number of skim passes": cut_job("wire_edm", {"skims": 4}),
            "skim_stock_mm must be a list of 2 numbers": cut_job("wire_edm", {"skims": 2, "skim_stock_mm": [0.1]}),
            "no removal rate for acrylic": cut_job("wire_edm", material="acrylic"),
            "a wire_edm cuts with a wire tool": cut_job("wire_edm", tool={"id": "T1", "type": "beam", "kerf_mm": 0.3}),
            "a wire_edm does not use stepdown_mm": cut_job("wire_edm", {"stepdown_mm": 2}),
        }
        for expected, job in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaises(CamJobError) as caught:
                    parsed = parse_job(job)
                    part = read_part(self.dxf, sheet_thickness_mm=parsed.stock.thickness_mm)
                    plan_setups(parsed, parse_operations(parsed), part, build_stock(parsed.stock, part))
                self.assertIn(expected, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
