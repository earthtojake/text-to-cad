"""``@eng_drawing``: a PDF sheet derived from a part.

The part is built with build123d so every expected number is known from the
construction: a 40 x 30 x 10 box with one 6 mm hole dimensioned overall reads
40 and 30 because it was built that way, and its hole gets a centre mark
because the projected outline contains a full circle.

``_render_sheet`` returns the in-memory ezdxf document the PDF is rendered
from, so the sheet's content is asserted there; the decorator's own tests
cover the document that reaches disk.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tests.python.support.tmp_root import temporary_directory


def _part():
    from build123d import Align, Box, Cylinder, Pos

    align = (Align.CENTER, Align.CENTER, Align.MIN)
    return Box(40, 30, 10, align=align) - Pos(10, 5, 0) * Cylinder(3, 10, align=align)


def _sheet(part):
    from cadgen.eng_drawing import Sheet

    sheet = Sheet("A4", title="TEST BLOCK", part_number="T-1", revision="B", notes=["ONE", "TWO"])
    top = sheet.view(part, "top", at=(100, 120))
    front = sheet.view(part, "front", at=(100, 50))
    top.overall()
    top.diameter((10, 5, 10), 3, text="%%c6 THRU")
    front.dim((20, -15, 0), (20, -15, 10), offset=12)
    return sheet


def _dim_texts(doc):
    texts = []
    for dim in doc.modelspace().query("DIMENSION"):
        block = doc.blocks.get(dim.dxf.geometry)
        texts.extend(e.text for e in block if e.dxftype() == "MTEXT")
    return texts


class DrawingSheetTests(unittest.TestCase):
    def test_a_sheet_writes_views_dimensions_marks_frame_and_title(self) -> None:
        from cadgen.eng_drawing import _render_sheet

        doc = _render_sheet(_sheet(_part()), index=1, count=2, label="t")
        msp = doc.modelspace()
        kinds = {}
        for entity in msp:
            kinds[entity.dxftype()] = kinds.get(entity.dxftype(), 0) + 1
        self.assertEqual(kinds.get("DIMENSION"), 3, "overall width + height, the front height")
        self.assertEqual(kinds.get("LEADER"), 1, "the hole callout is a leader to text outside the view")
        self.assertGreaterEqual(kinds.get("TEXT", 0), 6, "title block, notes and two view labels")
        by_layer = {}
        for entity in msp:
            by_layer.setdefault(entity.dxf.layer, 0)
            by_layer[entity.dxf.layer] += 1
        self.assertGreater(by_layer.get("VISIBLE", 0), 0)
        self.assertGreater(by_layer.get("HIDDEN", 0), 0, "the hole is hidden in the front view")
        self.assertEqual(by_layer.get("CENTER", 0), 2, "one centre mark: two lines")
        # Measured, not typed: the overall dimensions read the box.
        texts = _dim_texts(doc)
        self.assertIn("40", texts)
        self.assertIn("30", texts)
        self.assertIn("10", texts)
        callouts = [e.dxf.text for e in msp.query("TEXT") if e.dxf.layer == "DIM"]
        self.assertEqual(callouts, ["%%c6 THRU"])
        # The callout text sits outside the view's extent, not across the part.
        callout = next(e for e in msp.query("TEXT") if e.dxf.layer == "DIM")
        outline_x = [p[0] for e in msp.query("LWPOLYLINE LINE") if e.dxf.layer == "VISIBLE" for p in _points(e)]
        self.assertTrue(callout.dxf.insert.x > max(outline_x) or callout.dxf.insert.x < min(outline_x))
        # A4 landscape frame at the margin.
        frame = [e for e in msp if e.dxftype() == "LWPOLYLINE" and e.dxf.layer == "SHEET"]
        self.assertEqual(len(frame), 1)
        xs = [p[0] for p in frame[0].get_points("xy")]
        self.assertAlmostEqual(max(xs) - min(xs), 297 - 20, places=6)
        title_text = [e.dxf.text for e in msp.query("TEXT")]
        self.assertIn("TEST BLOCK", title_text)
        self.assertTrue(any("SHEET 1 OF 2" in t and "REV B" in t for t in title_text))

    def test_every_layer_linetype_exists_in_the_table(self) -> None:
        """A layer naming a linetype the document does not define draws continuous.

        ezdxf's `setup=True` table has DASHED and CENTER and no HIDDEN, and it
        substitutes silently (the audit reports "Replaced undefined linetype"),
        so hidden edges printed solid. Asserting the NAME on the layer cannot
        catch that; asserting the table can.
        """
        from cadgen.eng_drawing import _LAYERS, _render_sheet

        doc = _render_sheet(_sheet(_part()), index=1, count=1, label="t")
        defined = {lt.dxf.name.upper() for lt in doc.linetypes}
        for name, (_color, linetype, _weight) in _LAYERS.items():
            self.assertIn(linetype.upper(), defined, f"layer {name} names an undefined linetype")
        auditor = doc.audit()
        self.assertEqual(list(auditor.errors), [])
        self.assertEqual([str(fix) for fix in auditor.fixes], [])

    def test_the_hidden_line_pass_writes_each_edge_once(self) -> None:
        """The kernel returns a hidden edge once per face that hides it."""
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = _part()
        sheet = Sheet("A4")
        sheet.view(part, "front", at=(150, 105))
        doc = _render_sheet(sheet, index=1, count=1, label="dupes")
        drawn: dict[str, list] = {}
        for entity in doc.modelspace().query("LINE LWPOLYLINE CIRCLE ARC"):
            if entity.dxf.layer not in ("VISIBLE", "HIDDEN"):
                continue
            key = (entity.dxftype(), tuple(sorted(tuple(round(v, 6) for v in p) for p in _points(entity))))
            drawn.setdefault(entity.dxf.layer, []).append(key)
        for layer, keys in drawn.items():
            self.assertEqual(len(keys), len(set(keys)), f"{layer} holds duplicate geometry")
        self.assertGreater(len(drawn.get("HIDDEN", [])), 0, "the bore is hidden in the front view")

    def test_dimension_points_land_on_the_projected_geometry(self) -> None:
        """A dimension between the box's top corners spans exactly the drawn outline."""
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = _part()
        sheet = Sheet("A4")
        top = sheet.view(part, "top", at=(100, 100))
        top.dim((-20, 15, 10), (20, 15, 10), offset=10)
        doc = _render_sheet(sheet, index=1, count=1, label="t")
        msp = doc.modelspace()
        dim = list(msp.query("DIMENSION"))[0]
        p1, p2 = dim.dxf.defpoint2, dim.dxf.defpoint3
        self.assertAlmostEqual(abs(p2.x - p1.x), 40.0, places=5)
        xs = [p[0] for e in msp.query("LWPOLYLINE LINE") if e.dxf.layer == "VISIBLE" for p in _points(e)]
        self.assertAlmostEqual(min(p1.x, p2.x), min(xs), places=4)
        self.assertAlmostEqual(max(p1.x, p2.x), max(xs), places=4)

    def test_a_scaled_sheet_prints_true_size_values(self) -> None:
        """At 1:2 an 80 x 50 x 10 plate still reads 80, 50 and 10.

        The dimension measures SHEET millimetres, which are the model's only at
        1:1, so each view sets dimlfac to the inverse of its own scale.
        """
        from build123d import Align, Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = Box(80, 50, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
        for scale in (1.0, 0.5, 0.25):
            with self.subTest(scale=scale):
                sheet = Sheet("A3", scale=scale, title="PLATE")
                top, front, _right = sheet.three_views(part)
                top.overall()
                front.dim((-40, -25, 0), (-40, -25, 10), offset=-14)
                doc = _render_sheet(sheet, index=1, count=1, label="s")
                texts = _dim_texts(doc)
                self.assertIn("80", texts)
                self.assertIn("50", texts)
                self.assertIn("10", texts)
        # A view drawn at its own scale reads true size too.
        sheet = Sheet("A3", scale=1.0)
        sheet.view(part, "top", at=(210, 150), scale=0.5).overall()
        self.assertEqual(sorted(_dim_texts(_render_sheet(sheet, index=1, count=1, label="s"))), ["50", "80"])

    def test_a_tolerance_prints_the_authors_deviation_at_any_scale(self) -> None:
        from build123d import Align, Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = Box(80, 50, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
        sheet = Sheet("A3", scale=0.5)
        front = sheet.view(part, "front", at=(210, 150))
        front.dim((-40, -25, 0), (40, -25, 0), offset=-14, tol=0.1)
        texts = _dim_texts(_render_sheet(sheet, index=1, count=1, label="tol"))
        self.assertTrue(any("80" in t and "±0.10" in t for t in texts), texts)

    def test_an_unplaced_dimension_takes_the_next_free_row(self) -> None:
        """`dim()` used to default to the row `overall()` writes into."""
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = _part()
        sheet = Sheet("A4")
        top = sheet.view(part, "top", at=(150, 105))
        top.overall()
        top.dim((-20, 15, 10), (20, 15, 10))
        top.dim((-20, -15, 10), (20, -15, 10))
        doc = _render_sheet(sheet, index=1, count=1, label="rows")
        # The three horizontal dimensions: the overall width and the two unplaced ones.
        rows = sorted(round(d.dxf.defpoint.y, 3) for d in doc.modelspace().query("DIMENSION")
                      if abs(float(d.dxf.angle)) < 1e-9)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(set(rows)), 3, f"two dimensions share a row: {rows}")
        self.assertEqual([round(b - a, 3) for a, b in zip(rows, rows[1:])], [12.0, 12.0],
                         "one clear row apart")

    def test_views_that_run_off_the_frame_are_refused_with_a_scale_that_fits(self) -> None:
        from build123d import Align, Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = Box(3000, 1200, 200, align=(Align.CENTER, Align.CENTER, Align.MIN))
        sheet = Sheet("A3")
        sheet.three_views(part)
        with self.assertRaises(ValueError) as caught:
            _render_sheet(sheet, index=1, count=1, label="big")
        message = str(caught.exception)
        self.assertIn("off the frame", message)
        suggested = float(message.split("Sheet(scale=")[1].split(")")[0])
        self.assertLess(suggested, 1.0)
        # The suggestion has to be one that actually works.
        fits = Sheet("A3", scale=suggested)
        fits.three_views(part)
        _render_sheet(fits, index=1, count=1, label="big")

    def test_a_title_longer_than_its_cell_is_cut_not_overrun(self) -> None:
        """Measured the way it is drawn, whatever font this machine resolves.

        A character is not a fixed fraction of the cap height, and which
        fraction it is depends on the font the renderer finds: proportional
        here, near-monospace on a runner with no system fonts. Whether a given
        title has to be cut or merely shrunk is that font's business. That it
        ends up inside its cell is not.
        """
        from cadgen.eng_drawing import _MIN_TEXT_MM, Sheet, _render_sheet, _text_width

        cell = min(180.0, 297 - 20) * 0.6 - 6
        for title in ("ENCLOSURE",
                      "ELECTRONICS ENCLOSURE BASE",
                      "ELECTRONICS ENCLOSURE BASE, LOWER HALF, REVISION C, MACHINED FROM 6061-T6 BILLET",
                      "M" * 400):
            with self.subTest(title=title):
                sheet = Sheet("A4", title=title)
                sheet.view(_part(), "top", at=(150, 120))
                doc = _render_sheet(sheet, index=1, count=1, label="long")
                drawn = next(e for e in doc.modelspace().query("TEXT[layer=='TITLE']")
                             if e.dxf.text and title.startswith(e.dxf.text.rstrip("…")[:4]))
                self.assertGreaterEqual(drawn.dxf.height, _MIN_TEXT_MM, "still legible")
                self.assertLessEqual(_text_width(drawn.dxf.text, drawn.dxf.height), cell + 1e-6,
                                     f"{drawn.dxf.text!r} at {drawn.dxf.height} runs into the SCALE cell")
                if drawn.dxf.text != title:
                    self.assertTrue(drawn.dxf.text.endswith("…"),
                                    f"{drawn.dxf.text!r} was shortened without saying so")

    def test_first_angle_lays_the_views_out_first_angle(self) -> None:
        """The label and the arrangement are the same decision."""
        from cadgen.eng_drawing import Sheet

        part = _part()
        third = Sheet("A3")
        t_top, t_front, t_right = third.three_views(part)
        self.assertGreater(t_top.at[1], t_front.at[1], "third angle: the plan sits above the front")
        self.assertGreater(t_right.at[0], t_front.at[0], "third angle: the view from the right sits right")
        first = Sheet("A3", projection="FIRST ANGLE")
        f_top, f_front, f_right = first.three_views(part)
        self.assertLess(f_top.at[1], f_front.at[1], "first angle: the plan sits below the front")
        self.assertLess(f_right.at[0], f_front.at[0], "first angle: the view from the right sits left")

    def test_the_bottom_view_lines_up_under_the_front_view(self) -> None:
        """Third angle draws the bottom view as the top view mirrored, not rotated."""
        from cadgen.eng_drawing import _Projection

        part = _part()
        top, bottom = _Projection(part, "top"), _Projection(part, "bottom")

        def axes(proj):
            origin = proj.point((0, 0, 0))
            return [tuple(round(a - b, 6) for a, b in zip(proj.point(p), origin))
                    for p in ((1, 0, 0), (0, 1, 0))]

        self.assertEqual(axes(top), [(1.0, 0.0), (0.0, 1.0)])
        self.assertEqual(axes(bottom), [(1.0, 0.0), (0.0, -1.0)], "+X must stay right; +Y flips")

    def test_every_side_view_maps_up_to_up(self) -> None:
        """A model point higher in Z lands higher on the sheet in every view that
        looks along a horizontal direction; the right and left views once mirrored."""
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = _part()
        for name in ("front", "back", "right", "left"):
            with self.subTest(view=name):
                sheet = Sheet("A3")
                view = sheet.view(part, name, at=(210, 150))
                view.dim((0, 0, 0), (0, 0, 10), offset=12)
                doc = _render_sheet(sheet, index=1, count=1, label="sides")
                dim = doc.modelspace().query("DIMENSION")[0]
                self.assertGreater(dim.dxf.defpoint3.y, dim.dxf.defpoint2.y, "z=10 should sit above z=0")
                self.assertGreater(dim.dxf.defpoint3.y, view.at[1], "the top of the part is above the centre")

    def test_view_label_sits_below_bottom_dimensions(self) -> None:
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = _part()
        sheet = Sheet("A4")
        front = sheet.view(part, "front", at=(100, 100))
        front.dim((-20, -15, 0), (20, -15, 0), offset=-12)
        doc = _render_sheet(sheet, index=1, count=1, label="label")
        label = next(e for e in doc.modelspace().query("TEXT[layer=='NOTES']") if e.dxf.text == "FRONT")
        dim = doc.modelspace().query("DIMENSION")[0]
        self.assertLess(label.dxf.insert.y, dim.dxf.defpoint.y - 3, "the label hangs under the dimension line")

    def test_round_edges_are_written_as_circles_and_arcs(self) -> None:
        from cadgen.eng_drawing import Sheet, _render_sheet

        sheet = Sheet("A4")
        sheet.view(_part(), "top", at=(100, 120))
        doc = _render_sheet(sheet, index=1, count=1, label="round")
        circles = [c for c in doc.modelspace().query("CIRCLE") if c.dxf.layer == "VISIBLE"]
        self.assertEqual(len(circles), 1, "the hole seen from above is one CIRCLE")
        self.assertAlmostEqual(circles[0].dxf.radius, 3.0, places=3)

    def test_shop_annotations_are_written(self) -> None:
        from cadgen.eng_drawing import Sheet, _render_sheet, hole_callout_text

        part = _part()
        sheet = Sheet("A4", title="TAGGED", general_tolerance="ISO 2768-m",
                      revisions=[("A", "2026-09-01", "INITIAL RELEASE"), ("B", "2026-09-17", "HOLE MOVED")])
        top = sheet.view(part, "top", at=(100, 120))
        front = sheet.view(part, "front", at=(100, 50))
        front.dim((20, -15, 0), (20, -15, 10), offset=12, tol=0.1)
        front.dim((-20, -15, 0), (20, -15, 0), offset=-12, tol=(0.05, 0.02), fit="h6")
        top.hole((10, 5, 10), 6, thru=True, count=1)
        top.hole((10, 5, 10), 6.6, depth=12, cbore=(11, 6.5), thread="M6x1 - 6H")
        doc = _render_sheet(sheet, index=1, count=1, label="tagged")
        msp = doc.modelspace()
        texts = _dim_texts(doc)
        self.assertTrue(any("±0.10" in t for t in texts), texts)
        self.assertTrue(any("+0.05" in t and "0.02" in t and "h6" in t for t in texts), texts)
        notes = [e.dxf.text for e in msp.query("TEXT[layer=='NOTES']")]
        self.assertTrue(any("ISO 2768-m" in n for n in notes), notes)
        title_texts = [e.dxf.text for e in msp.query("TEXT[layer=='TITLE']")]
        self.assertIn("DESCRIPTION", title_texts)
        self.assertIn("HOLE MOVED", title_texts)
        callouts = [e.dxf.text for e in msp.query("TEXT[layer=='DIM']")]
        self.assertIn("1× %%c6 THRU", callouts)
        self.assertEqual(hole_callout_text({"diameter": 6.6, "depth": 12, "thru": False, "cbore": (11, 6.5), "csk": None,
                                            "thread": "M6x1 - 6H", "count": None}), "M6x1 - 6H ↧12   ⌴ %%c11 ↧6.5")

    def test_an_angular_dimension_is_written(self) -> None:
        from cadgen.eng_drawing import Sheet, _render_sheet

        sheet = Sheet("A4")
        front = sheet.view(_part(), "front", at=(100, 100))
        front.angle((-20, -15, 0), (20, -15, 0), (-20, -15, 10), offset=14)
        doc = _render_sheet(sheet, index=1, count=1, label="angle")
        dims = doc.modelspace().query("DIMENSION")
        self.assertTrue(any(d.dimtype == 5 for d in dims), "an angular dimension on the DIM layer")


class SheetWarningTests(unittest.TestCase):
    """What the sheet draws but a reader should look at. Found by running the
    skill on parts it was not written against."""

    def test_a_dimension_whose_points_miss_the_geometry_says_so(self) -> None:
        """A part built from a corner, dimensioned as if it were centred.

        The dimension renders perfectly and measures blank paper, which is the
        one error a shop cannot catch from the print.
        """
        from build123d import Align, Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = Box(120, 30, 30, align=(Align.MIN, Align.CENTER, Align.CENTER))  # X runs 0..120
        sheet = Sheet("A3")
        front = sheet.view(part, "front", at=(210, 150))
        front.dim((0, 0, 15), (30, 0, 15))          # on the part
        front.dim((-60, 0, 15), (-30, 0, 15))       # as if it were centred: off in space
        front.note("BORE", (-55, 0, 0))
        notices: list[str] = []
        _render_sheet(sheet, index=1, count=1, label="off", warnings=notices)

        self.assertEqual(len(notices), 2, notices)
        self.assertTrue(any("dim 1" in n for n in notices), notices)
        self.assertTrue(any("note 2" in n for n in notices), notices)
        self.assertTrue(all("measures blank paper" in n for n in notices), notices)

    def test_a_clean_sheet_warns_about_nothing(self) -> None:
        from cadgen.eng_drawing import _render_sheet

        notices: list[str] = []
        _render_sheet(_sheet(_part()), index=1, count=1, label="clean", warnings=notices)
        self.assertEqual(notices, [])

    def test_annotation_printed_over_annotation_says_so(self) -> None:
        """Two views are laid out knowing only where the views are, so one view's
        outermost dimension can land on the view label of the view above it."""
        from cadgen.eng_drawing import Sheet, _render_sheet

        def build(gap):
            # The default gap reserves two dimension rows. Asking the front view
            # for three puts its outermost row where the top view's label hangs.
            sheet = Sheet("A3")
            _top, front, _right = sheet.three_views(_part(), gap=gap)
            front.overall()
            front.dim((-20, -15, 0), (20, -15, 0))
            front.dim((-20, -15, 10), (20, -15, 10))
            notices: list[str] = []
            _render_sheet(sheet, index=1, count=1, label="rows", warnings=notices)
            return [n for n in notices if "annotation overlaps" in n]

        crowded = build(None)
        self.assertTrue(crowded, "three rows into a two-row gap should be reported")
        self.assertIn("three_views(gap=", crowded[0])
        self.assertEqual(build(70), [], "given the room, the same sheet is quiet")


class DrawingVocabularyTests(unittest.TestCase):
    """Every argument is checked where it is written, not at render time."""

    def setUp(self) -> None:
        from cadgen.eng_drawing import Sheet

        self.view = Sheet("A4").view(_part(), "top", at=(100, 100))

    def test_unknown_view_sheet_and_projection_are_refused(self) -> None:
        from cadgen.eng_drawing import Sheet

        with self.assertRaises(ValueError):
            Sheet("Letter")
        with self.assertRaises(ValueError):
            Sheet("A4").view(_part(), "diagonal", at=(0, 0))
        with self.assertRaisesRegex(ValueError, "projection"):
            Sheet("A4", projection="THIRD-ANGLE")

    def test_an_unknown_orientation_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "orientation"):
            self.view.dim((0, 0, 0), (1, 0, 0), orientation="x")

    def test_a_hole_that_cannot_be_made_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "diameter"):
            self.view.hole((0, 0, 0), -5)
        with self.assertRaisesRegex(ValueError, "diameter"):
            self.view.hole((0, 0, 0), 0)
        with self.assertRaisesRegex((TypeError, ValueError), "cbore"):
            self.view.hole((0, 0, 0), 6, cbore=5)
        with self.assertRaisesRegex(ValueError, "cbore"):
            self.view.hole((0, 0, 0), 6, cbore=(11, -2))
        with self.assertRaisesRegex(ValueError, "THRU"):
            self.view.hole((0, 0, 0), 6, thru=True, depth=12)
        with self.assertRaisesRegex(ValueError, "radius"):
            self.view.diameter((0, 0, 0), 0)

    def test_a_tolerance_that_is_not_a_tolerance_is_refused(self) -> None:
        with self.assertRaises(TypeError):
            self.view.dim((0, 0, 0), (1, 0, 0), tol="abc")
        with self.assertRaises(TypeError):
            self.view.dim((0, 0, 0), (1, 0, 0), tol=(1, 2, 3))

    def test_an_offset_that_is_not_a_number_is_refused(self) -> None:
        with self.assertRaises(TypeError):
            self.view.dim((0, 0, 0), (1, 0, 0), offset="far")


class DrawingDocumentTests(unittest.TestCase):
    """What reaches disk: one PDF, at the path the caller named, byte-stable."""

    def test_running_the_decorated_function_writes_one_deterministic_pdf(self) -> None:
        from cadgen.eng_drawing import eng_drawing

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as td:
            out = Path(td) / "PDF" / "block.pdf"

            @eng_drawing(out=str(out))
            def block_drawing():
                return _sheet(_part())

            written = block_drawing()
            self.assertEqual(written, [out])
            self.assertEqual(sorted(p.name for p in out.parent.iterdir()), ["block.pdf"],
                             "no DXF, and no half-written file left behind")
            payload = out.read_bytes()
            self.assertTrue(payload.startswith(b"%PDF"))
            self.assertNotIn(b"CreationDate", payload, "a clock stamp would make the bytes differ per run")
            block_drawing()
            self.assertEqual(out.read_bytes(), payload, "an unchanged drawing rebuilds to identical bytes")

    def test_a_sheet_per_page(self) -> None:
        from cadgen.eng_drawing import Sheet, eng_drawing

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as td:
            out = Path(td) / "pair.pdf"
            part = _part()

            @eng_drawing(out=str(out))
            def pair():
                a = Sheet("A4", title="ONE"); a.view(part, "top", at=(150, 105))
                b = Sheet("A4", title="TWO"); b.view(part, "front", at=(150, 105))
                return [a, b]

            self.assertEqual(pair(), [out])
            # matplotlib writes the page tree uncompressed: the tree's /Count is the page count.
            self.assertIn(b"/Count 2", out.read_bytes())

    def test_the_output_path_is_required_and_names_a_pdf(self) -> None:
        from cadgen.eng_drawing import eng_drawing

        with self.assertRaisesRegex(ValueError, "out="):
            @eng_drawing
            def no_path():
                return _sheet(_part())

        with self.assertRaisesRegex(ValueError, r"\.pdf"):
            @eng_drawing(out="../DXF/wrong.dxf")
            def wrong_suffix():
                return _sheet(_part())

    def test_a_missing_renderer_fails_loudly_and_writes_nothing(self) -> None:
        """The PDF is the drawing: no renderer is a failure, not a skipped half."""
        from cadgen.eng_drawing import eng_drawing

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as td:
            out = Path(td) / "PDF" / "block.pdf"

            @eng_drawing(out=str(out))
            def block_drawing():
                return _sheet(_part())

            # Only this key is swapped and restored: `patch.dict` on sys.modules
            # rebuilds the whole mapping on exit and would drop every submodule
            # imported inside the block, the CAD kernel's included.
            missing = object()
            previous = sys.modules.get("matplotlib", missing)
            sys.modules["matplotlib"] = None  # `import matplotlib` now raises ImportError
            try:
                with self.assertRaisesRegex(RuntimeError, "PDF"):
                    block_drawing()
            finally:
                if previous is missing:
                    sys.modules.pop("matplotlib", None)
                else:
                    sys.modules["matplotlib"] = previous
            self.assertFalse(out.exists())

    def test_a_function_that_returns_no_sheet_is_refused(self) -> None:
        from cadgen.eng_drawing import eng_drawing

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as td:
            @eng_drawing(out=str(Path(td) / "x.pdf"))
            def not_a_sheet():
                return 42

            with self.assertRaises(TypeError):
                not_a_sheet()


class UndimensionedSheetTests(unittest.TestCase):
    """A sheet is a drawing before its author has written a dimension."""

    def test_views_alone_with_curved_geometry_still_write_a_pdf(self) -> None:
        """The cut-profile checks graded it as a broken laser-cut file.

        `document_is_drawing` needs a DIMENSION or a LEADER before it will
        believe a document is a document, which is right for a DXF that arrived
        from elsewhere and wrong for one @eng_drawing just built. A projected
        outline with a fillet in it does not close, so every part that was not a
        plain box failed the first time it was drawn -- which is step 3 of the
        skill's own workflow, before step 4 says to dimension anything.
        """
        from build123d import Axis, Box, Cylinder, fillet
        from cadgen.eng_drawing import Sheet, eng_drawing

        parts = {
            "filleted": fillet(Box(80, 50, 10).edges().filter_by(Axis.Z), 8),
            "cylinder": Cylinder(20, 40),
        }
        with temporary_directory(prefix="tmp-cad-eng-drawing-") as tmp:
            for name, part in parts.items():
                target = Path(tmp) / f"{name}.pdf"

                @eng_drawing(out=str(target))
                def undimensioned(part=part):
                    sheet = Sheet("A3", title=name.upper())
                    sheet.three_views(part)
                    return sheet

                undimensioned()
                self.assertTrue(target.exists(), f"{name} wrote no PDF")
                self.assertGreater(target.stat().st_size, 1000)

    def test_the_duplicate_and_empty_checks_still_run(self) -> None:
        """Exempting the cut-profile checks must not exempt the rest."""
        from cadgen.drawing_checks import validate_drawing_document

        import ezdxf

        doc = ezdxf.new("R2010", setup=True)
        doc.units = ezdxf.units.MM
        msp = doc.modelspace()
        square = [(0, 0), (10, 0), (10, 10), (0, 10)]
        msp.add_lwpolyline(square, close=True, dxfattribs={"layer": "VISIBLE"})
        msp.add_lwpolyline(square, close=True, dxfattribs={"layer": "VISIBLE"})
        msp.add_lwpolyline([(0, 0), (10, 0), (10, 10)], dxfattribs={"layer": "VISIBLE"})
        codes = {f.code for f in validate_drawing_document(doc, drawing=True)}
        self.assertIn("duplicate_entity", codes, "the check that caught the doubled hidden lines")
        self.assertNotIn("open_cut_profile", codes)
        # And the open polyline IS still a finding when nobody vouches for the file.
        self.assertIn("open_cut_profile", {f.code for f in validate_drawing_document(doc)})

        empty = ezdxf.new("R2010", setup=True)
        self.assertIn("empty_drawing", {f.code for f in validate_drawing_document(empty, drawing=True)})


class TextMeasurementTests(unittest.TestCase):
    """The markup is not the text.

    Everything here is asserted against the font this machine resolves, never
    against a millimetre figure. The frontend turns text into glyph paths
    through the same font machinery the measurement asks, so the two agree by
    construction -- on a workstation full of typefaces and on a runner with
    none. Baking in one font's numbers tests the runner, not the code.
    """

    def test_mtext_is_measured_by_the_glyphs_it_draws(self) -> None:
        r"""A toleranced 30 is `\A0;30{\H0.70x;±0.10}`: 15 characters, 7 of
        which draw nothing and 5 of which draw at 0.7 of the height. Counted raw
        at full height that was 37.8 mm of ink where about 14 mm exists."""
        from cadgen.eng_drawing import _mtext_extent, _text_width

        plain, _ = _mtext_extent("\\A0;30", 3.5)
        toleranced, _ = _mtext_extent("\\A0;30{\\H0.70x;\u00b10.10}", 3.5)
        stacked, _ = _mtext_extent("\\A0;30{\\H0.70x;\\S+0.05^-0.02;}", 3.5)

        # The control codes draw nothing, so the plain value is exactly its digits.
        self.assertAlmostEqual(plain, _text_width("30", 3.5), delta=0.01)
        # And the deviation is charged at 0.7 of the height, as it is drawn.
        self.assertAlmostEqual(toleranced, plain + _text_width("\u00b10.10", 3.5 * 0.7), delta=0.01)
        # Far short of the raw count that produced the false positives: fifteen
        # characters at full height, braces and \H0.70x; included.
        self.assertLess(toleranced, _text_width("30\\H0.70x;\u00b10.10", 3.5) * 0.6)
        # A stacked deviation prints its halves one above the other, so it is as
        # wide as the wider half and not as wide as both.
        self.assertLess(stacked, plain + 2 * _text_width("+0.05", 3.5))

    def test_the_measurement_is_the_font_the_renderer_will_use(self) -> None:
        """No fixed fraction of the cap height serves every string: the ratio
        that fits "ELECTRONICS ENCLOSURE BASE" runs "+0.10" 25% over in a
        proportional font, and a machine with no system fonts resolves a
        different one again. Ask the font, do not assume it."""
        from cadgen.eng_drawing import _font, _text_width

        font = _font(5.0)
        if font is None:
            self.skipTest("no font machinery here; the conservative ratio applies")
        for value in ("ELECTRONICS ENCLOSURE BASE", "+0.10", "\u00d86 THRU", "R18"):
            with self.subTest(value=value):
                self.assertAlmostEqual(_text_width(value, 5.0), float(font.text_width(value)),
                                       delta=1e-6)

    def test_width_grows_with_the_string_and_the_height(self) -> None:
        from cadgen.eng_drawing import _text_width

        self.assertEqual(0.0, _text_width("", 3.5))
        self.assertLess(_text_width("12", 3.5), _text_width("1234", 3.5))
        self.assertAlmostEqual(_text_width("1234", 7.0), 2 * _text_width("1234", 3.5), delta=1e-6)

class ChainDimensionTests(unittest.TestCase):
    """The overlap warning has to survive the commonest idiom in drafting."""

    def _warnings(self, pitch: float, tol) -> list:
        from build123d import Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        span = 160.0
        sheet = Sheet("A3", title="CHAIN")
        top, _front, _right = sheet.three_views(Box(span, 60, 10))
        for i in range(int(span // pitch)):
            top.dim((-span / 2 + pitch * i, 30, 0), (-span / 2 + pitch * (i + 1), 30, 0),
                    tol=tol, offset=14.0)
        notices: list = []
        _render_sheet(sheet, index=1, count=1, label="chain", warnings=notices)
        return [n for n in notices if "overlaps" in n]

    def test_a_toleranced_chain_with_clear_paper_does_not_warn(self) -> None:
        """Five values about 14 mm wide at 30 mm pitch: 16 mm of clear paper.

        The same chain without `tol=` warned about nothing, which is what gave
        the false positive away: the tolerance changed the measurement, not the
        drawing. A warning that cries on a correct sheet is one an agent learns
        to ignore, and that costs the cases where it is right.
        """
        for pitch in (25.0, 30.0, 36.0, 40.0):
            with self.subTest(pitch=pitch):
                self.assertEqual([], self._warnings(pitch, 0.1))
                self.assertEqual([], self._warnings(pitch, None))

    def test_values_that_really_do_collide_still_warn(self) -> None:
        """The pitch comes from the measurement, so this is a collision on any
        font: values packed at half the width of the value itself."""
        from cadgen.eng_drawing import _mtext_extent

        width, _ = _mtext_extent("\\A0;30{\\H0.70x;±0.10}", 3.5)
        self.assertNotEqual([], self._warnings(round(width / 2, 1), 0.1))


class InkTests(unittest.TestCase):
    def test_no_edge_is_drawn_on_both_visible_and_hidden(self) -> None:
        """HIDDEN was written second, so it drew over every visible line.

        HLR returns an edge from each face that bounds it, so a silhouette edge
        comes back in both passes. One `seen` set per pass caught the repeats
        inside each pass and none across them: a 600 dpi crop of one view in
        colour was 34,842 grey pixels against 2,635 black -- the outline
        printing grey-dashed, the visible/hidden distinction gone. In mono it is
        black over black, which is why it went unnoticed.
        """
        from build123d import Box, Cylinder, Pos
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = Box(60, 40, 20) - Cylinder(6, 40) - Pos(0, 0, 6) * Cylinder(9, 8)
        sheet = Sheet("A3", title="INK")
        sheet.three_views(part)
        doc = _render_sheet(sheet, index=1, count=1, label="ink")

        drawn: dict[str, set] = {"VISIBLE": set(), "HIDDEN": set()}
        for entity in doc.modelspace():
            layer = entity.dxf.layer
            if layer not in drawn:
                continue
            points = tuple((round(x, 6), round(y, 6)) for x, y in _points(entity))
            drawn[layer].add(min(points, points[::-1]))

        self.assertTrue(drawn["VISIBLE"] and drawn["HIDDEN"], "both passes drew something")
        self.assertEqual(set(), drawn["VISIBLE"] & drawn["HIDDEN"])

    def test_a_tangent_transition_is_not_drawn_as_a_hidden_edge(self) -> None:
        """A drawing has no tangent transition line, and one behind material
        marks nothing a shop can look at.

        `project_to_viewport` bundles OCCT's smooth edges into the hidden half
        along with sharp edges and silhouettes. A cylindrical face carries a
        SEAM where it closes on itself, the seam is smooth, and it lands in that
        bundle -- so wherever the seam happens to face the camera it prints as
        an extra dashed line the length of the feature. On this disc the right
        view drew two, the full width of the part, inside its real edges; on a
        bore the same line runs down the hole's own axis.

        Which view shows it is an accident of where the kernel put the seam, so
        every view is checked.
        """
        from build123d import Cylinder, GeomType, Pos, fillet
        from cadgen.eng_drawing import Sheet, _render_sheet

        radius, height, blend = 40.0, 10.0, 1.5
        blank = Pos(0, 0, height / 2) * Cylinder(radius, height)
        part = fillet(blank.edges().filter_by(GeomType.CIRCLE), blend)
        tangent = round(height / 2 - blend, 3)

        def spans(name: str) -> list:
            sheet = Sheet("A3", title="FLANGE")
            view = sheet.view(part, name, at=(200, 150))
            doc = _render_sheet(sheet, index=1, count=1, label="flange")
            found = []
            for entity in doc.modelspace():
                if entity.dxf.layer != "HIDDEN":
                    continue
                points = _points(entity)
                ys = {round(y - view.at[1], 2) for _x, y in points}
                xs = [x for x, _y in points]
                if len(ys) == 1 and max(xs) - min(xs) > radius:
                    found.append(ys.pop())
            return found

        for name in ("front", "right"):
            with self.subTest(view=name):
                drawn = spans(name)
                self.assertNotIn(tangent, drawn, f"{name}: a seam is drawn as a hidden edge")
                self.assertNotIn(-tangent, drawn, f"{name}: a seam is drawn as a hidden edge")

    def test_real_hidden_edges_and_silhouettes_survive(self) -> None:
        """Dropping tangents must not drop a bore's walls or a sharp edge."""
        from build123d import Box, Cylinder, Pos
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = Box(60, 40, 20) - Cylinder(6, 40) - Pos(0, 0, 6) * Cylinder(9, 8)
        sheet = Sheet("A3", title="BORES")
        front = sheet.view(part, "front", at=(200, 150))
        doc = _render_sheet(sheet, index=1, count=1, label="bores")

        walls = set()
        for entity in doc.modelspace().query("LINE[layer=='HIDDEN']"):
            a, b = entity.dxf.start, entity.dxf.end
            if abs(a.x - b.x) < 1e-6:
                walls.add(round(a.x - front.at[0], 2))
        # Both bores, both walls each: the silhouettes a hole is read from.
        for x in (-9.0, -6.0, 6.0, 9.0):
            self.assertIn(x, walls, f"the bore wall at {x} is missing: {sorted(walls)}")

    def test_the_layer_weights_reach_the_pdf(self) -> None:
        """The backend clamps every width to 72/dpi unless given a floor.

        The sample PDF carried one non-zero width operator: 0.72, 180 times.
        Thick against thin is most of what makes a print readable at a glance.
        """
        import re
        import zlib

        from cadgen.eng_drawing import Sheet, eng_drawing

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as tmp:
            target = Path(tmp) / "weights.pdf"

            @eng_drawing(out=str(target))
            def weights():
                sheet = Sheet("A3", title="WEIGHTS")
                top, _f, _r = sheet.three_views(_part())
                top.overall()
                return sheet

            weights()
            raw = target.read_bytes()

        widths = set()
        for match in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
            data = match.group(1)
            try:
                data = zlib.decompress(data)
            except zlib.error:
                continue
            widths.update(float(w.group(1)) for w in re.finditer(rb"([\d.]+) w\b", data))
        widths.discard(0.0)

        self.assertGreaterEqual(len(widths), 4, f"one width per layer, not one for all: {sorted(widths)}")
        self.assertIn(0.5, widths, "VISIBLE, the heavy outline")
        self.assertIn(0.18, widths, "CENTER and DIM, the thin ones")
        self.assertNotEqual({0.72}, widths, "0.72 is 72/dpi, the clamp")

    def test_a_counterbore_gets_one_centre_mark(self) -> None:
        """Two crosses drawn over each other fill the CENTER gaps in.

        The centre line then prints solid, which is the one thing its dashes are
        there to say it is not.
        """
        from build123d import Box, Cylinder, Pos
        from cadgen.eng_drawing import Sheet, _render_sheet

        part = Box(60, 40, 20) - Cylinder(4, 40) - Pos(0, 0, 6) * Cylinder(8, 8)
        sheet = Sheet("A3", title="CBORE")
        sheet.view(part, "top", at=(150, 150))
        doc = _render_sheet(sheet, index=1, count=1, label="cbore")

        marks = [e for e in doc.modelspace().query("LINE") if e.dxf.layer == "CENTER"]
        self.assertEqual(2, len(marks), "one horizontal and one vertical arm, not two of each")


class ScaleSuggestionTests(unittest.TestCase):
    def test_the_scale_the_refusal_names_actually_fits(self) -> None:
        """Dividing the overflow out treats the whole sheet as if it scaled.

        The 47 mm between views and the 27 mm of annotation reach do not, so the
        ratio overstated what a smaller scale buys: three of four ordinary sizes
        needed two refusals, each naming another scale that did not fit either.
        """
        import re

        from build123d import Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        def attempt(dims, scale, iso):
            sheet = Sheet("A3", title="BIG", scale=scale)
            sheet.three_views(Box(*dims), iso=iso)
            try:
                _render_sheet(sheet, index=1, count=1, label="big")
            except ValueError as exc:
                return str(exc)
            return None

        for dims in ((450, 270, 112), (600, 400, 200), (320, 260, 90)):
            for iso in (False, True):
                with self.subTest(dims=dims, iso=iso):
                    message = attempt(dims, 1.0, iso)
                    self.assertIsNotNone(message, "this part does not fit at 1:1")
                    named = re.search(r"Sheet\(scale=([0-9.eE+-]+)\)", message)
                    self.assertIsNotNone(named, message)
                    self.assertIsNone(attempt(dims, float(named.group(1)), iso),
                                      f"{message}\n...and the scale it named did not fit either")

    def test_a_part_no_standard_scale_fits_says_so(self) -> None:
        from build123d import Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        sheet = Sheet("A4", title="ENORMOUS")
        sheet.three_views(Box(4_000_000, 3_000_000, 1_000_000))
        with self.assertRaisesRegex(ValueError, "No standard scale"):
            _render_sheet(sheet, index=1, count=1, label="enormous")

    def test_the_isometric_label_states_the_scale_it_drew_at(self) -> None:
        """It stated its RATIO to the sheet, not the scale it drew at.

        On a 2:1 sheet an isometric that fitted itself to 1.96 is very nearly
        full size, and the label read "ISOMETRIC (1:1.02)" -- a reduction from
        full size that never happened. A view's scale is the shop's number.
        """
        from build123d import Box
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", title="ISO", scale=2.0)
        iso = sheet.three_views(Box(90, 60, 40), iso=True)[3]
        self.assertIsNotNone(iso.scale)
        self.assertGreater(iso.scale, 1.0, "drawn larger than full size")
        self.assertTrue(iso.label.endswith(":1"), f"{iso.label} reads as a reduction")

        full = Sheet("A3", title="ISO", scale=2.0).three_views(Box(30, 20, 10), iso=True)[3]
        self.assertIsNone(full.scale, "it fitted at the sheet's own scale")
        self.assertEqual("ISOMETRIC", full.label)


class MoreVocabularyTests(unittest.TestCase):
    """The holes left in the class the vocabulary checks closed."""

    def setUp(self) -> None:
        from cadgen.eng_drawing import Sheet

        self.view = Sheet("A4").view(_part(), "top", at=(100, 100))

    def test_a_bare_string_of_notes_is_refused(self) -> None:
        """notes="BREAK EDGES" printed eleven notes reading B, R, E, A, K...

        A str is a Sequence[str] of its own characters, and the wrong spelling
        cannot be told from the right one after the fact.
        """
        from cadgen.eng_drawing import Sheet

        with self.assertRaisesRegex(TypeError, "notes"):
            Sheet("A4", notes="BREAK EDGES")
        with self.assertRaisesRegex(TypeError, "revisions"):
            Sheet("A4", revisions="A")
        Sheet("A4", notes=["BREAK EDGES"])  # the right spelling still works

    def test_a_note_wider_than_the_sheet_is_refused(self) -> None:
        from cadgen.eng_drawing import Sheet

        with self.assertRaisesRegex(ValueError, "wider than"):
            Sheet("A4", notes=["BREAK ALL SHARP EDGES AND REMOVE BURRS " * 4])

    def test_angle_checks_its_arguments_like_every_other_verb(self) -> None:
        """It was the one verb whose arguments went unread."""
        with self.assertRaisesRegex(ValueError, "collinear"):
            self.view.angle((0, 0, 0), (1, 0, 0), (2, 0, 0))
        with self.assertRaisesRegex(ValueError, "collinear"):
            self.view.angle((0, 0, 0), (1, 0, 0), (-3, 0, 0))
        with self.assertRaisesRegex(ValueError, "non-zero length"):
            self.view.angle((0, 0, 0), (0, 0, 0), (1, 0, 0))
        with self.assertRaises(ValueError):
            self.view.angle((0, 0, 0), (1, 0, 0), (0, 1, 0), offset=float("nan"))
        with self.assertRaises(ValueError):
            self.view.angle((0, 0, 0), (1, 0, 0), (0, 1, 0), offset=0)
        self.view.angle((0, 0, 0), (1, 0, 0), (0, 1, 0))  # a real angle still works

    def test_a_note_offset_that_is_not_a_pair_is_refused(self) -> None:
        with self.assertRaises(TypeError):
            self.view.note("HI", (0, 0, 0), offset="over there")
        with self.assertRaises(ValueError):
            self.view.note("HI", (0, 0, 0), offset=(float("inf"), 10))

    def test_a_non_finite_view_position_is_refused(self) -> None:
        """It compared False against every frame edge, so the off-frame guard
        passed it and the sheet rendered blank at exit 0."""
        from cadgen.eng_drawing import Sheet

        with self.assertRaisesRegex(ValueError, "finite"):
            Sheet("A4").view(_part(), "top", at=(float("nan"), 100))
        with self.assertRaises(TypeError):
            Sheet("A4").view(_part(), "top", at="middle")


class OverallRowTests(unittest.TestCase):
    def test_overall_clears_an_explicitly_placed_dimension(self) -> None:
        """Counting only the UNPLACED dimensions put them on the same row.

        overall() is the outermost row on its side, and an offset= the author
        wrote occupies a row just as surely as one the sheet handed out.
        """
        from build123d import Box
        from cadgen.eng_drawing import Sheet, _render_sheet

        sheet = Sheet("A3", title="ROWS")
        top, _front, _right = sheet.three_views(Box(60, 40, 10))
        top.dim((-30, 20, 0), (0, 20, 0), offset=24.0)   # the author places this one
        top.dim((0, 20, 0), (30, 20, 0))                 # and lets the sheet place this one
        top.overall()
        doc = _render_sheet(sheet, index=1, count=1, label="rows")

        # Every horizontal dimension line above the top view, by the height it
        # was drawn at. Three dimensions, three rows: the overall pair is the
        # outermost, and no two share.
        rows = [round(d.dxf.defpoint.y, 2) for d in doc.modelspace().query("DIMENSION")
                if d.dxf.defpoint.y > top.at[1] and abs(d.dxf.angle) < 1e-6]
        self.assertGreaterEqual(len(rows), 3)
        self.assertEqual(len(rows), len(set(rows)), f"two dimension lines share a row: {sorted(rows)}")
        self.assertGreater(max(rows) - sorted(rows)[-2], 1.0,
                           "overall() is outermost, and clear of the row below it")


def _points(entity):
    kind = entity.dxftype()
    if kind == "LINE":
        return [(entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)]
    if kind == "CIRCLE":
        return [(entity.dxf.center.x, entity.dxf.center.y), (entity.dxf.radius, entity.dxf.radius)]
    if kind == "ARC":
        return [(entity.dxf.center.x, entity.dxf.center.y), (entity.dxf.radius, entity.dxf.radius),
                (entity.dxf.start_angle, entity.dxf.end_angle)]
    return list(entity.get_points("xy"))


if __name__ == "__main__":
    unittest.main()
