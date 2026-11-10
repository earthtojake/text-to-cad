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

# what every clean cut file says: whose the rules are, and what a flat drawing holds none of (its bends, reliefs,
# hems and thickness: the bent part's check judges them)
CLEAN_CODES = {"rules_general", "families_not_measured"}


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
        # the open square's two ends; the doubled line's own two ends lie on the side it overlaps, which is that
        # one defect (overlaps), not open geometry to close
        self.assertEqual(ends, [(10.0, 10.0), (10.0, 20.0)])
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

    def test_a_side_drawn_twice_is_one_overlap_and_the_outline_stays_the_part(self) -> None:
        def build(msp, _):
            _plate(msp, 100, 60)
            msp.add_line((0, 0), (100, 0))   # the outline's bottom side again, end to end
        result = self.check(self.write("doubled", build), thickness=2.0)
        self.assertEqual(self.codes(result) - CLEAN_CODES, {"sheet.overlapping_curves"})  # no open contour to close
        self.assertEqual(result.measurements["open_geometry"]["items"], [])
        (part,) = result.measurements["parts"]["items"]
        self.assertEqual((part["flat_length_mm"], part["flat_width_mm"]), (100.0, 60.0))

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

    def test_a_cut_file_with_no_thickness_says_its_rules_waited(self) -> None:
        def build(msp, _):
            _plate(msp)
            msp.add_circle((20, 20), 0.25)   # half a millimetre across: under any sheet's thickness
        result = self.check(self.write("bare", build))
        (waited,) = [f for f in result.findings if f.code == "sheet.thickness_unknown"]
        self.assertEqual(waited.severity, "warning")
        self.assertIn("hole_to_edge", waited.message)
        # not evaluated is not evaluated: no rule ran on a thickness nobody gave
        self.assertNotIn("sheet.hole_diameter", self.codes(result))
        outcomes = {o["rule"]: o["status"] for o in result.measurements["rules"]["outcomes"]}
        self.assertEqual((outcomes["sheet.hole_diameter"], outcomes["sheet.hole_to_edge"]),
                         ("not_evaluated", "not_evaluated"))
        self.assertNotIn("rule_thickness_mm", result.measurements["holes"]["items"][0])
        self.assertIn("no --thickness", result.summary)  # an OK that does not read as a pass of them

    def test_inch_geometry_declared_in_millimetres_is_suspect(self) -> None:
        def build(msp, _):
            _plate(msp, 4.0, 3.0)
            msp.add_circle((1.0, 1.0), 0.0625)
        result = self.check(self.write("inch_as_mm", build), thickness=2.0)
        (suspect,) = [f for f in result.findings if f.code == "units_suspect"]
        self.assertIn("read as inches it is 101.6 x 76.2 mm", suspect.message)
        self.assertIn("$INSUNITS to 1", suspect.message)
        self.assertEqual(result.measurements["parts"]["items"][0]["flat_length_mm"], 4.0)  # judged as declared

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

    def test_a_notch_a_tab_and_a_bend_layer(self) -> None:
        def build(msp, document):
            document.layers.add("BEND")
            msp.add_lwpolyline([(0, 0), (100, 0), (100, 40), (54, 40), (54, 25), (52, 25), (52, 40), (0, 40)],
                               close=True, dxfattribs={"layer": "CUT"})   # a notch 2 wide, 15 deep
            msp.add_line((0, 20), (100, 20), dxfattribs={"layer": "BEND"})
            msp.add_circle((20, 23), 1.5, dxfattribs={"layer": "CUT"})   # 1.5 mm from the bend line
            msp.add_circle((80, 10), 2, dxfattribs={"layer": "ETCH_CUT"})
        result = self.check(self.write("notched", build), thickness=2.0)
        notch = min(result.measurements["notches"]["items"], key=lambda item: item["width_mm"])
        self.assertAlmostEqual(notch["width_mm"], 2.0, places=6)
        self.assertAlmostEqual(notch["length_mm"], 15.0, places=6)
        self.assertIn("sheet.notch_length", self.codes(result))
        (near,) = [item for item in result.measurements["hole_to_bend"]["items"] if item["xyz"][:2] == [20.0, 23.0]]
        self.assertAlmostEqual(near["distance_centerline_mm"], 1.5, places=6)
        # CUT and ETCH_CUT both hold cut geometry: a fact (a shop's own file rules read it), no general rule
        self.assertEqual(result.measurements["cut_file"]["cut_layer_count"], 2)

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

    # --- nothing measured is never a pass ------------------------------------------------------------------

    def errors(self, result) -> list[str]:
        return sorted(finding.code for finding in result.findings if finding.severity == "error")

    def test_a_stray_dimension_does_not_blank_the_check(self) -> None:
        def broken(msp, _):
            msp.add_lwpolyline([(0, 0), (100, 0), (100, 60), (0, 60)], close=False)  # a side missing
            msp.add_circle((20, 30), 0.05)
            msp.add_linear_dim(base=(0, -10), p1=(0, 0), p2=(100, 0)).render()
        result = self.check(self.write("dimensioned", broken), thickness=2.0, kerf=0.2)
        self.assertEqual(set(self.errors(result)), {"sheet.open_contour", "sheet.under_kerf"})
        self.assertIn("sheet.annotation_on_cut_layer", self.codes(result))  # the dimension, on a cut layer
        self.assertNotIn("drawing_document", self.codes(result))
        self.assertIn("open geometry at 2 place(s)", result.summary)  # no "1 part" read off the hole left closed

        def clean(msp, document):
            document.layers.add("DIMENSIONS")
            _plate(msp)
            msp.add_circle((20, 20), 3)
            msp.add_linear_dim(base=(0, -10), p1=(0, 0), p2=(120, 0), dxfattribs={"layer": "DIMENSIONS"}).render()
        result = self.check(self.write("annotated", clean), thickness=2.0)
        self.assertTrue(result.ok)
        self.assertEqual(self.codes(result) - CLEAN_CODES, set())  # measured as any cut file is
        self.assertEqual(result.measurements["cut_file"]["contour_count"], 2)
        self.assertTrue(result.measurements["cut_file"]["is_drawing"])  # a fact, no excuse

    def test_a_file_with_nothing_to_cut_is_not_checked(self) -> None:
        def dimension_only(msp, _):
            msp.add_linear_dim(base=(0, -10), p1=(0, 0), p2=(100, 0)).render()
            msp.add_text("NOTES", dxfattribs={"insert": (5, 5)})
        for name, build, said in (("empty", lambda msp, _: None, "its modelspace is empty"),
                                  ("notes", dimension_only, "annotation(s) on cut layers cut nothing")):
            result = self.check(self.write(name, build), thickness=2.0)
            self.assertFalse(result.ok)
            (finding,) = result.findings
            self.assertEqual((finding.severity, finding.code), ("error", "no_cut_geometry"))
            self.assertIn(said, finding.message)

    def test_a_block_reference_is_exploded_where_it_is_placed(self) -> None:
        def build(msp, document):
            block = document.blocks.new("PART")
            _plate(block, 100, 60, layer="0")
            block.add_circle((98, 30), 2.5)                # breaks through the edge at x = 100
            block.add_text("PART 7", dxfattribs={"insert": (10, 10)})
            # placed turned, mirrored and moved: the hole still breaks the same edge
            msp.add_blockref("PART", (300, 200), dxfattribs={"rotation": 30, "xscale": -1, "layer": "CUT"})
        result = self.check(self.write("block", build), thickness=2.0)
        self.assertEqual(self.errors(result), ["sheet.crossing_contours"] * 2)
        self.assertIn("sheet.annotation_on_cut_layer", self.codes(result))  # the block's text, on the cut layer
        self.assertEqual(result.measurements["cut_file"]["cut_layers"], ["CUT"])  # layer 0 of a block is its reference's
        crossing = result.measurements["contour_crossings"]["items"][0]
        self.assertTrue(crossing["location"].startswith("layer CUT, INSERT #"))

        def opened(msp, document):
            block = document.blocks.new("OPEN")
            block.add_lwpolyline([(0, 0), (100, 0), (100, 60), (0, 60)], close=False)
            msp.add_blockref("OPEN", (0, 0))
        self.assertIn("sheet.open_contour", self.errors(self.check(self.write("open_block", opened), thickness=2.0)))

    def test_a_flat_3d_polyline_is_read_and_a_curve_off_the_plane_is_said_not_read(self) -> None:
        def flat(msp, _):
            msp.add_polyline3d([(0, 0, 0), (100, 0, 0), (100, 60, 0), (0, 60, 0)], close=True)
        result = self.check(self.write("polyline3d", flat), thickness=2.0)
        self.assertTrue(result.ok)
        (part,) = result.measurements["parts"]["items"]
        self.assertEqual((part["flat_length_mm"], part["flat_width_mm"]), (100.0, 60.0))

        def tilted(msp, _):
            _plate(msp, layer="0")
            msp.add_polyline3d([(10, 10, 0), (30, 10, 5), (30, 30, 5), (10, 30, 0)], close=True)   # off the plane
            msp.add_circle((60, 40), 4, dxfattribs={"extrusion": (0, 1, 0)})                       # in the XZ plane
        result = self.check(self.write("tilted", tilted), thickness=2.0)
        self.assertFalse(result.ok)  # the plate is clean, and what was not read is no pass
        (missed,) = [f for f in result.findings if f.code == "measurement_failed"]
        self.assertIn("cut_entities was not measured: 2 entities on a cut layer not read", missed.message)
        self.assertIn("not flat in the sheet's plane", missed.message)
        self.assertIn("drawn in a plane off the sheet's", missed.message)
        self.assertEqual(result.measurements["cut_file"]["unread_count"], 2)
        self.assertEqual(result.measurements["cut_file"]["contour_count"], 1)

    def test_arcs_and_circles_in_a_mirrored_ocs_are_read_where_they_lie(self) -> None:
        mirrored = {"extrusion": (0, 0, -1)}   # as a mirrored copy is written: OCS x is the world's -x

        def filleted(msp, _):
            for start, end in (((0, 0), (100, 0)), ((100, 0), (100, 50)), ((90, 60), (0, 60)), ((0, 60), (0, 0))):
                msp.add_line(start, end)
            msp.add_arc((-90, 50), 10, 90, 180, dxfattribs=mirrored)       # the corner's fillet, about (90, 50)
            # a slot of two lines and two half-circle bulges, drawn mirrored: it lies at x = 20 to 40
            msp.add_lwpolyline([(-20, 30, 0, 0, 0), (-40, 30, 0, 0, -1), (-40, 36, 0, 0, 0), (-20, 36, 0, 0, -1)],
                               format="xyseb", close=True, dxfattribs=mirrored)
        result = self.check(self.write("mirrored_fillet", filleted), thickness=2.0)
        self.assertTrue(result.ok, [f.human_line() for f in result.findings])
        self.assertEqual(result.measurements["cut_file"]["contour_count"], 2)
        (slot,) = result.measurements["holes"]["items"]
        self.assertEqual((slot["kind"], slot["xyz"][:2]), ("slot", [30.0, 33.0]))
        self.assertAlmostEqual(slot["length_mm"], 26.0, delta=0.02)

        def crossing(msp, _):
            _plate(msp, 100, 60, layer="0")
            msp.add_circle((-98, 30), 2.5, dxfattribs=mirrored)            # at (98, 30): through the edge at x = 100
        self.assertEqual(self.errors(self.check(self.write("mirrored_circle", crossing), thickness=2.0)),
                         ["sheet.crossing_contours"] * 2)

    def test_contours_that_cross_through_a_sampled_point_or_touch_are_found(self) -> None:
        def plate_and(*cuts):
            def build(msp, _):
                _plate(msp, 100, 60, layer="0")
                for cut in cuts:
                    cut(msp)
            return build

        def crossed(result) -> list[str]:
            return [item["kind"] for item in result.measurements["contour_crossings"]["items"]]

        # a circle centred on the edge crosses it a quarter turn from its first point, whatever its radius
        for radius in (1.0, 2.0, 2.5, 3.0, 5.0, 10.0):
            result = self.check(self.write(f"on_edge{radius}", plate_and(
                lambda msp, radius=radius: msp.add_circle((100, 30), radius))), thickness=2.0)
            self.assertEqual(self.errors(result), ["sheet.crossing_contours"] * 2, radius)
            self.assertEqual(sorted(item["xyz"][:2] for item in result.measurements["contour_crossings"]["items"]),
                             [[100.0, 30.0 - radius], [100.0, 30.0 + radius]])
        # the circle a hole near the edge is, reaching 5 mm past it: where its equation says, not its chords
        through = self.check(self.write("through", plate_and(lambda msp: msp.add_circle((95, 30), 10))), thickness=2.0)
        self.assertEqual(sorted(item["xyz"][:2] for item in through.measurements["contour_crossings"]["items"]),
                         [[100.0, 21.3397], [100.0, 38.6603]])
        # two holes 5 mm across each other's centres cross 60 degrees round each: both holes of the one part
        holes = self.check(self.write("holes", plate_and(lambda msp: msp.add_circle((50, 30), 5),
                                                         lambda msp: msp.add_circle((55, 30), 5))), thickness=2.0)
        self.assertEqual(crossed(holes), ["crosses", "crosses"])
        self.assertEqual(holes.measurements["parts"]["items"][0]["hole_count"], 2)
        self.assertEqual(holes.measurements["floating_interiors"]["items"], [])
        # a diamond with two corners on the edge's line passes through it there
        diamond = self.check(self.write("diamond", plate_and(lambda msp: msp.add_lwpolyline(
            [(90, 30), (100, 20), (110, 30), (100, 40)], close=True))), thickness=2.0)
        self.assertEqual(crossed(diamond), ["crosses", "crosses"])
        # a hole tangent to the edge from inside is a hole of the part, with no material between it and the edge
        tangent = self.check(self.write("tangent", plate_and(lambda msp: msp.add_circle((95, 30), 5))), thickness=2.0)
        self.assertEqual(self.errors(tangent), ["sheet.crossing_contours"])
        self.assertEqual(crossed(tangent), ["touches"])
        (hole,) = tangent.measurements["holes"]["items"]
        self.assertEqual(hole["edge_distance_mm"], 0.0)
        # two parts corner to corner touch; a hole a hair inside the edge is a hole, and only close to it
        corner = self.check(self.write("corner", plate_and(lambda msp: msp.add_lwpolyline(
            [(100, 30), (120, 10), (140, 30), (120, 50)], close=True))), thickness=2.0)
        self.assertEqual(crossed(corner), ["touches"])
        clear = self.check(self.write("clear", plate_and(lambda msp: msp.add_circle((94.9, 30), 5))), thickness=2.0)
        self.assertEqual((self.errors(clear), clear.measurements["holes"]["count"]), ([], 1))

    def test_ends_a_hair_apart_are_joined_and_said_and_a_real_gap_is_open(self) -> None:
        def gapped(gap):
            def build(msp, _):
                for start, end in (((0, 0), (100, 0)), ((100, 0), (100, 60)), ((100, 60), (0, 60)), ((0, 60), (0, gap))):
                    msp.add_line(start, end)
            return build
        for gap in (0.0005, 0.005):   # an inch file rounded to four decimals leaves ends 0.0025 mm apart
            result = self.check(self.write(f"gap{gap}", gapped(gap)), thickness=2.0)
            self.assertTrue(result.ok, gap)
            (joined,) = [f for f in result.findings if f.severity == "warning"]
            self.assertEqual(joined.code, "sheet.joined_gap")
            self.assertIn(f"up to {gap:.3g} mm", joined.message)
            self.assertEqual(result.measurements["cut_file"]["contour_count"], 1)
        # a real gap: the outline's two ends, and with no contour closed there is no part to measure
        self.assertEqual(self.errors(self.check(self.write("gap", gapped(0.05)), thickness=2.0)),
                         ["measurement_failed", "sheet.open_contour", "sheet.open_contour"])

    def test_a_circle_drawn_twice_is_cut_twice_and_is_one_hole(self) -> None:
        def build(msp, _):
            _plate(msp)
            for _ in range(2):
                msp.add_circle((20, 20), 5)
            msp.add_circle((60, 40), 5)
        result = self.check(self.write("doubled_circle", build), thickness=2.0)
        self.assertEqual(self.codes(result) - CLEAN_CODES, {"sheet.overlapping_curves"})  # no holes 0 mm apart
        self.assertEqual(result.measurements["holes"]["count"], 2)

    # --- bend lines ----------------------------------------------------------------------------------------

    def bent_plate(self, name: str, holes=(), bend_x=50.0, split=None, turn=0.0):
        """A 100 x 60 plate with a bend line at ``bend_x`` (in two, either side of ``split``, a y range) and
        round ``holes`` (x, y, diameter), the whole drawing turned ``turn`` degrees about a point off it."""
        c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))

        def at(x, y):
            return (17 + c * x - s * y, -9 + s * x + c * y)

        def build(msp, document):
            document.layers.add("BEND")
            msp.add_lwpolyline([at(0, 0), at(100, 0), at(100, 60), at(0, 60)], close=True)
            for y0, y1 in ([(0, split[0]), (split[1], 60)] if split else [(0, 60)]):
                msp.add_line(at(bend_x, y0), at(bend_x, y1), dxfattribs={"layer": "BEND"})
            if split:  # a window across the bend line
                msp.add_lwpolyline([at(bend_x - 7, split[0]), at(bend_x + 7, split[0]), at(bend_x + 7, split[1]),
                                    at(bend_x - 7, split[1])], close=True)
            for x, y, d in holes:
                msp.add_circle(at(x, y), d / 2)
        return self.check(self.write(name, build), thickness=2.0)

    def test_bend_lines_are_judged_by_the_least_any_bend_needs(self) -> None:
        clean = self.bent_plate("bend_clean", holes=[(20, 30, 5)])
        self.assertTrue(clean.ok)
        self.assertEqual(self.codes(clean) - CLEAN_CODES, {"sheet.bend_lines_read"})  # an info: what they were held to
        self.assertIn("1 bend line(s)", clean.summary)
        self.assertEqual(sorted(item["length_centerline_mm"] for item in clean.measurements["flanges"]["items"]),
                         [50.0, 50.0])
        for turn in (0.0, 37.0):  # the same wherever the drawing lies on the sheet
            near = self.bent_plate(f"bend_near{turn}", holes=[(46.5, 30, 5)], turn=turn)   # 1 mm from the line
            self.assertEqual(self.errors(near), ["sheet.hole_to_bend"])
            (item,) = near.measurements["hole_to_bend"]["items"]
            self.assertAlmostEqual(item["distance_centerline_mm"], 1.0, places=6)
            self.assertIn("1 mm is under the 4 mm minimum", next(f.message for f in near.findings
                                                                 if f.code == "sheet.hole_to_bend"))
            on = self.bent_plate(f"bend_on{turn}", holes=[(50, 30, 5)], turn=turn)
            self.assertEqual(self.errors(on), ["sheet.hole_to_bend"])
            self.assertIn("sheet.hole_in_bend", self.codes(on))
            short = self.bent_plate(f"bend_short{turn}", bend_x=99.0, turn=turn)           # a 1 mm flange
            self.assertEqual(self.errors(short), ["sheet.flange_length"])
            # exactly 2 t from the line is at the limit, and passes
            self.assertEqual(self.errors(self.bent_plate(f"bend_at{turn}", holes=[(43.5, 30, 5)], turn=turn)), [])

    def test_a_window_across_a_bend_line_ends_the_bend_and_is_no_hole_beside_it(self) -> None:
        result = self.bent_plate("bend_window", split=(27, 33))
        self.assertTrue(result.ok, [f.human_line() for f in result.findings])
        self.assertEqual(result.measurements["hole_to_bend"]["items"], [])
        self.assertEqual(result.measurements["cut_file"]["bend_line_count"], 2)

    # --- bounded -------------------------------------------------------------------------------------------

    def test_a_panel_of_two_thousand_holes_is_measured(self) -> None:
        def build(msp, _):
            _plate(msp, 965, 965)
            for i in range(45):
                for j in range(45):
                    msp.add_circle((20 + 21 * i, 20 + 21 * j), 5)
        result = self.check(self.write("perforated", build), thickness=2.0)
        self.assertTrue(result.ok)
        self.assertEqual(result.measurements["holes"]["count"], 2025)
        self.assertEqual(result.measurements["cut_file"]["contour_count"], 2026)
        nearest = result.measurements["hole_spacing"]["items"][0]
        self.assertAlmostEqual(nearest["distance_mm"], 11.0, places=6)  # 21 mm apart, 10 mm across


if __name__ == "__main__":
    unittest.main()
