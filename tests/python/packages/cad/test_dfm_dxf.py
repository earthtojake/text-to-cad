#!/usr/bin/env python3

"""A sheet's cut file checked (``cad.dxf.dfm(path, process="sheet")``, ``cad.build123d._dfm_dxf``): units,
closed contours, curves cut twice, crossings, degenerate loops, annotation and stray geometry on cut layers,
curves drawn as chords, islands that fall out, and the features measured against the thickness and the
kerf -- each planted in a file written here with ezdxf, beside a clean control, with the place it was
planted at.
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import ezdxf

from cad import dxf

CLEAN_CODES = {"rules_generic"}


def _plate(msp, width=120.0, height=80.0, layer="CUT"):
    msp.add_lwpolyline([(0, 0), (width, 0), (width, height), (0, height)], close=True, dxfattribs={"layer": layer})


class CutFileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def write(self, name: str, build, units=ezdxf.units.MM) -> Path:
        document = ezdxf.new()
        if units is not None:
            document.units = units
        else:
            document.header["$INSUNITS"] = 0
        build(document.modelspace(), document)
        path = Path(self.folder.name) / f"{name}.dxf"
        document.saveas(path)
        return path

    def check(self, path: Path, **options):
        return dxf.dfm(path, process="sheet", **options)

    def codes(self, result) -> set[str]:
        return {finding.code for finding in result.findings}

    def test_a_clean_plate_passes_and_is_measured(self) -> None:
        def build(msp, _):
            _plate(msp)
            msp.add_circle((20, 20), 3)
            msp.add_circle((100, 60), 3)
            # a slot of two lines and two half-circle bulges
            msp.add_lwpolyline([(50, 40, 0, 0, 0), (70, 40, 0, 0, 1), (70, 46, 0, 0, 0), (50, 46, 0, 0, 1)],
                               format="xyseb", close=True)
        result = self.check(self.write("clean", build), thickness=2.0)
        self.assertTrue(result.ok, [f.human_line() for f in result.findings])
        self.assertEqual(self.codes(result) - CLEAN_CODES, set())
        measured = result.measurements
        (part,) = measured["parts"]["items"]
        self.assertEqual((part["flat_length_mm"], part["flat_width_mm"], part["hole_count"]), (120.0, 80.0, 3))
        self.assertEqual(sorted(item["kind"] for item in measured["holes"]["items"]), ["round", "round", "slot"])
        slot = next(item for item in measured["holes"]["items"] if item["kind"] == "slot")
        self.assertAlmostEqual(slot["size_mm"], 6.0, delta=0.005)
        self.assertAlmostEqual(slot["length_mm"], 26.0, delta=0.005)
        circle = min((i for i in measured["holes"]["items"] if i["kind"] == "round"), key=lambda i: i["xyz"][0])
        self.assertAlmostEqual(circle["edge_distance_mm"], 17.0, places=6)
        self.assertEqual(circle["location"], f"layer 0, CIRCLE #{circle['location'].split('#')[1]}")
        self.assertEqual(measured["cut_file"]["unit"], "mm")
        self.assertIn("OK", result.summary)

    def test_planted_file_defects_are_found_where_they_were_planted(self) -> None:
        def build(msp, _):
            _plate(msp, 200, 100)
            # open: three sides of a square
            for start, end in (((10, 10), (20, 10)), ((20, 10), (20, 20)), ((20, 20), (10, 20))):
                msp.add_line(start, end)
            # a square of lines with one side drawn twice, partly overlapping
            for start, end in (((40, 10), (60, 10)), ((60, 10), (60, 30)), ((60, 30), (40, 30)), ((40, 30), (40, 10)),
                               ((45, 10), (55, 10))):
                msp.add_line(start, end)
            msp.add_lwpolyline([(80, 10), (95, 25), (95, 10), (80, 25)], close=True)   # a bowtie
            msp.add_lwpolyline([(110, 10), (130, 10), (110, 10)], close=True)          # a doubled-back line
            msp.add_text("PART 7", dxfattribs={"layer": "0", "insert": (150, 80)})
            msp.add_circle((170, 30), 12)
            msp.add_circle((170, 30), 4)                                                # an island in a hole
            centre, radius = (150, 50), 8.0                                             # a circle as 72 chords
            points = [(centre[0] + radius * math.cos(math.radians(a)), centre[1] + radius * math.sin(math.radians(a)))
                      for a in range(0, 360, 5)]
            for a, b in zip(points, points[1:] + points[:1]):
                msp.add_line(a, b)
            # two contours crossing
            msp.add_circle((100, 70), 6)
            msp.add_circle((108, 70), 6)
        result = self.check(self.write("defects", build), thickness=2.0)
        self.assertFalse(result.ok)
        by_code: dict[str, list] = {}
        for finding in result.findings:
            by_code.setdefault(finding.code, []).append(finding)
        planted = {"sheet.open_contour", "sheet.overlapping_curves", "sheet.self_intersecting",
                   "sheet.zero_area_loop", "sheet.annotation_on_cut_layer", "sheet.floating_interior",
                   "sheet.short_line_run", "sheet.crossing_contours",
                   "sheet.hole_spacing"}  # the crossing circles' holes are 0 mm apart: planted too
        self.assertEqual(set(by_code) - CLEAN_CODES, planted)  # every planted defect, and nothing else
        measured = result.measurements
        ends = sorted(tuple(item["xyz"][:2]) for item in measured["open_geometry"]["items"])
        # the open square's two ends, and the doubled line's own two ends mid-side
        self.assertEqual(ends, [(10.0, 10.0), (10.0, 20.0), (45.0, 10.0), (55.0, 10.0)])
        overlap = next(item for item in measured["overlaps"]["items"] if item["kind"] == "partial")
        self.assertAlmostEqual(overlap["length_mm"], 10.0, places=6)
        self.assertEqual(overlap["xyz"][:2], [50.0, 10.0])
        (cross,) = measured["self_intersections"]["items"]
        self.assertAlmostEqual(cross["xyz"][0], 87.5, places=6)
        self.assertEqual(len(measured["floating_interiors"]["items"]), 1)
        (run,) = measured["short_line_runs"]["items"]
        self.assertGreaterEqual(run["segments"], 60)
        self.assertEqual(len(measured["contour_crossings"]["items"]), 2)  # two circles cross twice
        self.assertTrue(all(item["location"].startswith("layer 0, ") for item in measured["overlaps"]["items"]))

    def test_units_inches_scale_and_unset_units_withhold_every_size_rule(self) -> None:
        def build(msp, _):
            _plate(msp, 4.0, 3.0)
            msp.add_circle((1.0, 1.0), 0.02)     # a 0.04 in (1.016 mm) hole
        inch = self.check(self.write("inch", build, ezdxf.units.IN), thickness=2.0)
        holes = inch.measurements["holes"]["items"]
        self.assertAlmostEqual(holes[0]["size_mm"], 1.016, places=6)
        self.assertEqual(inch.measurements["parts"]["items"][0]["flat_length_mm"], 101.6)
        self.assertIn("sheet.hole_diameter", self.codes(inch))  # 1.016 mm under the 2 mm sheet's 1 t
        unset = self.check(self.write("unset", build, None), thickness=2.0)
        codes = self.codes(unset)
        self.assertIn("units_not_set", codes)
        self.assertIn("units_suspect", codes)
        self.assertNotIn("sheet.hole_diameter", codes)
        self.assertFalse(unset.ok)

    def test_features_against_the_thickness_the_kerf_and_the_sheet(self) -> None:
        def build(msp, _):
            _plate(msp, 300, 100)
            msp.add_circle((10, 50), 0.4)                 # 0.8 mm hole, 9.6 mm from the edge
            msp.add_circle((50, 2.5), 1.5)                # 1 mm from the edge
            msp.add_circle((100, 50), 2)
            msp.add_circle((105, 50), 2)                  # 1 mm apart edge to edge
        path = self.write("features", build)
        result = self.check(path, thickness=2.0, kerf=0.3, sheet_size="250x200")
        codes = self.codes(result)
        for code in ("sheet.hole_diameter", "sheet.hole_to_edge", "sheet.hole_spacing", "sheet.flat_length"):
            self.assertIn(code, codes)
        failed = {o["rule"]: o for o in result.measurements["rules"]["outcomes"] if o["status"] == "failed"}
        self.assertEqual([round(f["value"], 4) for f in failed["sheet.hole_to_edge"]["failures"]], [1.0])
        self.assertEqual([round(f["value"], 4) for f in failed["sheet.hole_spacing"]["failures"]], [1.0])
        self.assertNotIn("sheet.under_kerf", codes)
        tight = self.check(path, thickness=2.0, kerf=0.9)
        self.assertIn("sheet.under_kerf", self.codes(tight))  # the 0.8 mm hole is narrower than the beam

    def test_a_notch_a_tab_a_bend_layer_and_sendcutsends_layers(self) -> None:
        def build(msp, document):
            document.layers.add("BEND")
            msp.add_lwpolyline([(0, 0), (100, 0), (100, 40), (54, 40), (54, 25), (52, 25), (52, 40), (0, 40)],
                               close=True, dxfattribs={"layer": "CUT"})   # a notch 2 wide, 15 deep
            msp.add_line((0, 20), (100, 20), dxfattribs={"layer": "BEND"})
            msp.add_circle((20, 23), 1.5, dxfattribs={"layer": "CUT"})   # 1.5 mm from the bend line
            msp.add_circle((80, 10), 2, dxfattribs={"layer": "ETCH_CUT"})
        result = self.check(self.write("notched", build), thickness=2.0, rules="generic")
        notch = min(result.measurements["notches"]["items"], key=lambda item: item["width_mm"])
        self.assertAlmostEqual(notch["width_mm"], 2.0, places=6)
        self.assertAlmostEqual(notch["length_mm"], 15.0, places=6)
        self.assertIn("sheet.notch_length", self.codes(result))
        (near,) = [item for item in result.measurements["hole_to_bend"]["items"] if item["xyz"][:2] == [20.0, 23.0]]
        self.assertAlmostEqual(near["distance_centerline_mm"], 1.5, places=6)
        scs = self.check(self.write("notched2", build), thickness=0.125 * 25.4, material="aluminum",
                         rules="sendcutsend")
        self.assertIn("sheet.cut_layers", self.codes(scs))  # CUT and ETCH_CUT both hold cut geometry
        self.assertIn("sheet.hole_to_bend", self.codes(scs))  # under half the 0.630 in die

    def test_an_unfolded_part_written_by_build123d_is_a_clean_cut_file(self) -> None:
        import build123d as bd

        from cad.build123d._dfm_sheet import unfold

        part = bd.extrude(bd.Plane.XZ * bd.make_face(bd.Polyline((0, 0), (40, 0), (40, 2), (0, 2), close=True)),
                          amount=-30)
        part = part - bd.Pos(20, 15, 1) * bd.Cylinder(3, 10)
        flat = unfold(part)
        exporter = bd.ExportDXF(unit=bd.Unit.MM)
        exporter.add_layer("CUT")
        exporter.add_shape(flat, layer="CUT")
        path = Path(self.folder.name) / "flat.dxf"
        exporter.write(str(path))
        result = self.check(path, thickness=2.0)
        self.assertTrue(result.ok, [f.human_line() for f in result.findings])
        (hole,) = result.measurements["holes"]["items"]
        self.assertAlmostEqual(hole["size_mm"], 6.0, places=6)
        self.assertAlmostEqual(hole["edge_distance_mm"], 12.0, places=6)


if __name__ == "__main__":
    unittest.main()
