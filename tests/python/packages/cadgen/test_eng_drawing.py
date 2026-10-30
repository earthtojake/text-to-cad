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

import math
import sys
import unittest
from pathlib import Path
from tests.python.support.tmp_root import temporary_directory


def _facts():
    """An empty record of what a drawing states, for _render_sheet and _unstated."""
    from cadgen._internal.drawing_report import _Facts

    return _Facts()


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
    top.diameter((10, 5, 10), text="%%c6 THRU")
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
        from cadgen._internal.drawing_render import _render_sheet

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
        self.assertEqual(by_layer.get("CENTER", 0), 3, "one centre mark (two lines) and the bore's axis in the front view")
        # Measured, not typed: the overall dimensions read the box.
        texts = _dim_texts(doc)
        self.assertIn("40", texts)
        self.assertIn("30", texts)
        self.assertIn("10", texts)
        self.assertEqual(_callouts(doc), ["%%c6 THRU"])
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
        for caption, value in (("DWG NO.", "T-1"), ("REV", "B"), ("SHEET", "1 OF 2"), ("SCALE", "1:1"),
                               ("SIZE", "A4"), ("UNITS", "MM")):
            self.assertIn(caption, title_text)
            self.assertIn(value, title_text)

    def test_every_layer_linetype_exists_in_the_table(self) -> None:
        """A layer naming a linetype the document does not define draws continuous.

        ezdxf's `setup=True` table has DASHED and CENTER and no HIDDEN, and it
        substitutes silently (the audit reports "Replaced undefined linetype"),
        so hidden edges printed solid. Asserting the NAME on the layer cannot
        catch that; asserting the table can.
        """
        from cadgen._internal.drawing_base import _LAYERS
        from cadgen._internal.drawing_render import _render_sheet

        doc = _render_sheet(_sheet(_part()), index=1, count=1, label="t")
        defined = {lt.dxf.name.upper() for lt in doc.linetypes}
        for name, (_color, linetype, _weight) in _LAYERS.items():
            self.assertIn(linetype.upper(), defined, f"layer {name} names an undefined linetype")
        auditor = doc.audit()
        self.assertEqual(list(auditor.errors), [])
        self.assertEqual([str(fix) for fix in auditor.fixes], [])

    def test_the_hidden_line_pass_writes_each_edge_once(self) -> None:
        """The kernel returns a hidden edge once per face that hides it."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        part = Box(80, 50, 10, align=(Align.CENTER, Align.CENTER, Align.MIN))
        sheet = Sheet("A3", scale=0.5)
        front = sheet.view(part, "front", at=(210, 150))
        front.dim((-40, -25, 0), (40, -25, 0), offset=-14, tol=0.1)
        texts = _dim_texts(_render_sheet(sheet, index=1, count=1, label="tol"))
        self.assertTrue(any("80" in t and "±0.1}" in t for t in texts), texts)

    def test_an_unplaced_dimension_takes_the_next_free_row_on_its_own_side(self) -> None:
        """`dim()` used to default to the row `overall()` writes into, and then to
        the top of the view whatever it measured: a pitch along the bottom edge ran
        its extension lines up across the whole part to a row above it."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        part = _part()
        sheet = Sheet("A4")
        top = sheet.view(part, "top", at=(150, 105))
        top.overall()
        top.dim((-20, 15, 10), (20, 15, 10))
        top.dim((-20, -15, 10), (20, -15, 10))
        doc = _render_sheet(sheet, index=1, count=1, label="rows")
        rows = sorted(round(d.dxf.defpoint.y, 3) for d in doc.modelspace().query("DIMENSION")
                      if abs(float(d.dxf.angle)) < 1e-9)
        self.assertEqual(len(rows), 3)
        below, above = [r for r in rows if r < 105], [r for r in rows if r > 105]
        self.assertEqual(len(below), 1, "the bottom edge's dimension sits below the view")
        self.assertEqual(len(above), 2, "the top edge's, and the overall width, above it")
        self.assertAlmostEqual(above[1] - above[0], 12.0, places=3, msg="one clear row apart, overall outermost")
        self.assertAlmostEqual(105 - 15 - below[0], 12.0, places=3, msg="the first row under the view")

    def test_views_that_run_off_the_frame_are_refused_with_a_scale_that_fits(self) -> None:
        from build123d import Align, Box
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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
        from cadgen._internal.drawing_base import _MIN_TEXT_MM, _text_width
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_sheet import _TITLE_FIT
        from cadgen.eng_drawing import Sheet

        cell = _TITLE_FIT
        for title in ("ENCLOSURE",
                      "ELECTRONICS ENCLOSURE BASE",
                      "ELECTRONICS ENCLOSURE BASE, LOWER HALF, REVISION C, MACHINED FROM 6061-T6 BILLET",
                      "M" * 400):
            with self.subTest(title=title):
                sheet = Sheet("A4", title=title)
                sheet.view(_part(), "top", at=(150, 120))
                doc = _render_sheet(sheet, index=1, count=1, label="long")
                drawn = next(e for e in doc.modelspace().query("TEXT[layer=='TITLE']")
                             if len(e.dxf.text.rstrip("…")) >= 4 and title.startswith(e.dxf.text.rstrip("…")))
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
        from cadgen._internal.drawing_views import _Projection
        from cadgen.eng_drawing import VIEW_DIRECTIONS

        part = _part()
        top, bottom = _Projection(part, VIEW_DIRECTIONS["top"]), _Projection(part, VIEW_DIRECTIONS["bottom"])

        def axes(proj):
            origin = proj.point((0, 0, 0))
            return [tuple(round(a - b, 6) for a, b in zip(proj.point(p), origin))
                    for p in ((1, 0, 0), (0, 1, 0))]

        self.assertEqual(axes(top), [(1.0, 0.0), (0.0, 1.0)])
        self.assertEqual(axes(bottom), [(1.0, 0.0), (0.0, -1.0)], "+X must stay right; +Y flips")

    def test_every_side_view_maps_up_to_up(self) -> None:
        """A model point higher in Z lands higher on the sheet in every view that
        looks along a horizontal direction; the right and left views once mirrored."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        part = _part()
        sheet = Sheet("A4")
        front = sheet.view(part, "front", at=(100, 100))
        front.dim((-20, -15, 0), (20, -15, 0), offset=-12)
        doc = _render_sheet(sheet, index=1, count=1, label="label")
        label = next(e for e in doc.modelspace().query("TEXT[layer=='NOTES']") if e.dxf.text == "FRONT")
        dim = doc.modelspace().query("DIMENSION")[0]
        self.assertLess(label.dxf.insert.y, dim.dxf.defpoint.y - 3, "the label hangs under the dimension line")

    def test_round_edges_are_written_as_circles_and_arcs(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_part(), "top", at=(100, 120))
        doc = _render_sheet(sheet, index=1, count=1, label="round")
        circles = [c for c in doc.modelspace().query("CIRCLE") if c.dxf.layer == "VISIBLE"]
        self.assertEqual(len(circles), 1, "the hole seen from above is one CIRCLE")
        self.assertAlmostEqual(circles[0].dxf.radius, 3.0, places=3)

    def test_shop_annotations_are_written(self) -> None:
        from cadgen._internal.drawing_annotation import hole_callout_text
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        part = _part()
        sheet = Sheet("A4", title="TAGGED", general_tolerance="ISO 2768-m",
                      revisions=[("A", "2026-09-01", "INITIAL RELEASE"), ("B", "2026-09-17", "HOLE MOVED")])
        top = sheet.view(part, "top", at=(100, 140))
        front = sheet.view(part, "front", at=(100, 75))
        front.dim((20, -15, 0), (20, -15, 10), offset=12, tol=0.1)
        front.dim((-20, -15, 0), (20, -15, 0), offset=-12, fit="h6")
        top.hole((10, 5, 10), thread="M6x1 - 6H")
        doc = _render_sheet(sheet, index=1, count=1, label="tagged")
        msp = doc.modelspace()
        texts = _dim_texts(doc)
        self.assertTrue(any("±0.1}" in t for t in texts), texts)
        self.assertTrue(any("40 h6" in t for t in texts), texts)
        notes = [e.dxf.text for e in msp.query("TEXT[layer=='NOTES']")]
        self.assertTrue(any("ISO 2768-m" in n for n in notes), notes)
        title_texts = [e.dxf.text for e in msp.query("TEXT[layer=='TITLE']")]
        self.assertIn("DESCRIPTION", title_texts)
        self.assertIn("HOLE MOVED", title_texts)
        callouts = _callouts(doc)
        # The ⌀6 bore is modelled at the thread's size: the thread is the bore,
        # one hole is not "1×", and THRU is still the part's.
        self.assertEqual(callouts, ["M6x1 - 6H THRU"])
        self.assertEqual(hole_callout_text({"diameter": 6.6, "depth": 12, "thru": False, "cbore": (11, 6.5), "csk": None,
                                            "thread": "M6x1 - 6H", "count": None}), "M6x1 - 6H ↧12   ⌴ %%c11 ↧6.5")
        self.assertEqual(hole_callout_text({"diameter": 5, "depth": 12, "thru": False, "cbore": None, "csk": None,
                                            "thread": "M6x1 - 6H", "count": 2, "tap_drill": True,
                                            "thread_depth": 10}), "2× %%c5 ↧12   M6x1 - 6H ↧10")

    def test_an_angular_dimension_is_written(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        front = sheet.view(_part(), "front", at=(100, 100))
        front.angle((-20, -15, 0), (20, -15, 0), (-20, -15, 10), offset=14)
        doc = _render_sheet(sheet, index=1, count=1, label="angle")
        dims = doc.modelspace().query("DIMENSION")
        self.assertTrue(any(d.dimtype == 5 for d in dims), "an angular dimension on the DIM layer")


class SheetWarningTests(unittest.TestCase):
    """What the sheet draws but a reader should look at. Found by running the
    skill on parts it was not written against."""

    def test_a_dimension_whose_points_miss_the_geometry_is_refused(self) -> None:
        """A part built from a corner, dimensioned as if it were centred.

        The dimension rendered perfectly and measured blank paper, which is the
        one error a shop cannot catch from the print: it was a warning beside it.
        """
        from build123d import Align, Box
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        part = Box(120, 30, 30, align=(Align.MIN, Align.CENTER, Align.CENTER))  # X runs 0..120
        for name, call in (("dim 1", lambda v: v.dim((-60, 0, 15), (-30, 0, 15))),   # as if it were centred
                           ("note 1", lambda v: v.note("BORE", (-55, 0, 0)))):
            sheet = Sheet("A3")
            front = sheet.view(part, "front", at=(210, 150))
            front.dim((0, 0, 15), (30, 0, 15))          # on the part
            call(front)
            with self.subTest(name), self.assertRaisesRegex(
                    ValueError, rf"front {name}: \d of \d point\(s\) fall outside the view's geometry .* would "
                                "measure blank paper"):
                _render_sheet(sheet, index=1, count=1, label="off")

    def test_a_clean_sheet_warns_about_nothing(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet

        notices: list[str] = []
        _render_sheet(_sheet(_part()), index=1, count=1, label="clean", warnings=notices)
        self.assertEqual(notices, [])

    def test_annotation_printed_over_annotation_is_refused(self) -> None:
        """Two views are laid out knowing only where the views are, so one view's
        outermost dimension can land on the view label of the view above it."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        def build(gap):
            # A fixed gap of 47 mm reserves two dimension rows. Asking the front
            # view for three puts its outermost row where the top view's label hangs.
            sheet = Sheet("A3")
            _top, front, _right = sheet.three_views(_part(), gap=gap)
            front.overall()
            # Both along the top edge, so both take rows above the view.
            front.dim((-20, -15, 10), (0, -15, 10))
            front.dim((0, -15, 10), (20, -15, 10))
            try:
                _render_sheet(sheet, index=1, count=1, label="rows")
            except ValueError as exc:
                return [str(exc)] if "annotation overlaps" in str(exc) else []
            return []

        crowded = build(47)
        self.assertTrue(crowded, "three rows into a two-row gap is refused")
        self.assertIn("three_views(gap=", crowded[0])
        self.assertEqual(build(70), [], "given the room, the same sheet is quiet")
        self.assertEqual(build(None), [], "left to itself, the layout makes the room")


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
        with self.assertRaisesRegex(ValueError, "size"):
            self.view.diameter((0, 0, 0), size=0)
        with self.assertRaisesRegex(TypeError, "positional argument"):   # law 15: no word of the retired size
            self.view.diameter((0, 0, 0), 3)

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
        from cadgen.engine.export.dxf import validate_drawing_document

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
        from cadgen._internal.drawing_base import _mtext_extent, _text_width

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
        from cadgen._internal.drawing_base import _font, _text_width

        font = _font(5.0)
        if font is None:
            self.skipTest("no font machinery here; the conservative ratio applies")
        for value in ("ELECTRONICS ENCLOSURE BASE", "+0.10", "\u00d86 THRU", "R18"):
            with self.subTest(value=value):
                self.assertAlmostEqual(_text_width(value, 5.0), float(font.text_width(value)),
                                       delta=1e-6)

    def test_width_grows_with_the_string_and_the_height(self) -> None:
        from cadgen._internal.drawing_base import _text_width

        self.assertEqual(0.0, _text_width("", 3.5))
        self.assertLess(_text_width("12", 3.5), _text_width("1234", 3.5))
        self.assertAlmostEqual(_text_width("1234", 7.0), 2 * _text_width("1234", 3.5), delta=1e-6)

class ChainDimensionTests(unittest.TestCase):
    """The overlap refusal has to survive the commonest idiom in drafting."""

    def _warnings(self, pitch: float, tol) -> list:
        from build123d import Box
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        span = 160.0
        sheet = Sheet("A3", title="CHAIN")
        top, _front, _right = sheet.three_views(Box(span, 60, 10))
        for i in range(int(span // pitch)):
            top.dim((-span / 2 + pitch * i, 30, 0), (-span / 2 + pitch * (i + 1), 30, 0),
                    tol=tol, offset=14.0)
        try:
            _render_sheet(sheet, index=1, count=1, label="chain")
        except ValueError as exc:
            return [str(exc)] if "overlaps" in str(exc) else []
        return []

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

    def test_values_that_really_do_collide_are_refused(self) -> None:
        """The pitch comes from the measurement, so this is a collision on any
        font: values packed at half the width of the value itself."""
        from cadgen._internal.drawing_base import _mtext_extent

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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

        from cadgen._internal.drawing_base import _STANDARD_SCALES, _scale_label

        sheet = Sheet("A3", title="ISO", scale=2.0)
        iso = sheet.three_views(Box(150, 90, 60), iso=True)[3]
        self.assertIsNotNone(iso.scale)
        self.assertLess(iso.scale, 2.0, "too big for the corner at the sheet's 2:1")
        self.assertIn(iso.scale, _STANDARD_SCALES, "a pictorial still states a scale a reader can use")
        self.assertEqual(iso.label, f"ISOMETRIC {_scale_label(iso.scale)}")

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

    def test_notes_stand_on_the_frame_beside_the_title_block(self) -> None:
        from cadgen._internal.drawing_base import _MARGIN, _TITLE_W
        from cadgen._internal.drawing_sheet import _notes_box
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0, notes=["BREAK SHARP EDGES.", "DEBURR."])
        ((x0, x1, y0, y1),) = _notes_box(sheet)
        self.assertLess(y0, _MARGIN + 6.0, "on the frame's foot: no empty strip under them")
        self.assertLessEqual(x1, sheet.width - _MARGIN - _TITLE_W, "beside the title block, not under it")

    def test_a_long_note_wraps_beside_the_title_block(self) -> None:
        from cadgen._internal.drawing_base import _MARGIN, _TITLE_W
        from cadgen._internal.drawing_sheet import _notes_box
        from cadgen.eng_drawing import Sheet

        note = "BREAK ALL SHARP EDGES AND REMOVE BURRS " * 4
        sheet = Sheet("A4", 1.0, notes=[note.strip()])
        rows = sheet._note_rows()
        self.assertGreater(len(rows), 1, "wrapped, not refused")
        self.assertEqual(" ".join(text.replace("NOTES:  1. ", "").strip() for _dx, text, _note, _first in rows),
                         note.strip(), "every word once, in order")
        ((x0, x1, y0, y1),) = _notes_box(sheet)
        self.assertLessEqual(x1, sheet.width - _MARGIN - _TITLE_W)

    def test_a_word_wider_than_the_sheet_is_refused(self) -> None:
        from cadgen.eng_drawing import Sheet

        with self.assertRaisesRegex(ValueError, "wider than"):
            Sheet("A4", notes=["X" * 200])

    def test_an_ordinary_shop_note_is_accepted(self) -> None:
        """The inverse of the guard above, and the case it used to refuse.

        The guard measured `8. {note}` at `text_height` while the sheet drew
        `NOTES:  1. {note}` at 2.5 mm against the full width of the paper, so
        it refused a 44-character note with 130 mm of room to spare.
        """
        from cadgen.eng_drawing import Sheet

        for note in (
            "BREAK ALL SHARP EDGES 0.3 MAX AND DEBURR THOROUGHLY",
            "REMOVE ALL BURRS AND SHARP EDGES BEFORE FINISHING",
            "ANODISE CLEAR PER MIL-A-8625 TYPE II CLASS 1",
        ):
            with self.subTest(note=note):
                Sheet("A4", notes=[note])

    def test_the_general_tolerance_is_measured_as_it_is_spelled_out(self) -> None:
        """It reaches the paper as a whole sentence, so that is what is measured."""
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4", general_tolerance="ISO 2768-m")
        self.assertEqual(
            sheet.drawn_notes()[0],
            "TOLERANCES PER ISO 2768-m UNLESS OTHERWISE SPECIFIED.",
        )
        long = Sheet("A4", 1.0, general_tolerance="ISO 2768-m AND " + "ASME Y14.5 " * 12)
        self.assertGreater(len(long._note_rows()), 1, "as long as it reads, wrapped at its words")

    def test_every_accepted_note_fits_between_the_frame_edges(self) -> None:
        """The guard and the ink agree: what it passes, the paper holds."""
        from cadgen._internal.drawing_base import _MARGIN, _NOTE_HEIGHT, _text_width
        from cadgen.eng_drawing import Sheet

        sheet = Sheet(
            "A4",
            general_tolerance="ISO 2768-fH AND ASME Y14.5-2018 WHERE APPLICABLE",
            notes=["BREAK ALL SHARP EDGES 0.3 MAX AND DEBURR THOROUGHLY"],
        )
        room = sheet.width - 2 * _MARGIN
        for line in sheet.note_lines():
            self.assertLessEqual(_text_width(line, _NOTE_HEIGHT), room)

    def test_notes_given_as_a_generator_still_reach_the_sheet(self) -> None:
        """They are read twice, by the guard and by the draw."""
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4", notes=iter(["FIRST NOTE", "SECOND NOTE"]))
        self.assertEqual(sheet.drawn_notes(), ["FIRST NOTE", "SECOND NOTE"])
        self.assertEqual(len(sheet.note_lines()), 2)

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
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

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

    def test_overall_extension_lines_reach_the_part(self) -> None:
        """A part that does not fill its view's box -- a base with a tab at one
        end -- has nothing at the box's top-left corner; the overall height's
        extension line starts on the tab, not at the corner, short of it."""
        from build123d import Align, Box, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(100, 20, 8, align=align) + Pos(45, 0, 0) * Box(10, 20, 40, align=align)
        sheet = Sheet("A3", 1.0)
        _top, front, _right = sheet.three_views(part)
        front.overall()
        doc = _render_sheet(sheet, index=1, count=1, label="ends")
        height = next(d for d in doc.modelspace().query("DIMENSION") if abs(d.dxf.angle - 90) < 1e-6)
        width = next(d for d in doc.modelspace().query("DIMENSION")
                     if abs(d.dxf.angle) < 1e-6 and d.dxf.defpoint.y > front.at[1])
        low, high = sorted((height.dxf.defpoint2, height.dxf.defpoint3), key=lambda p: p.y)
        self.assertAlmostEqual(high.x, front.at[0] + 40, delta=0.1, msg="the top's on the tab, at x = 40")
        self.assertAlmostEqual(low.x, front.at[0] - 50, delta=0.1, msg="the bottom's at the left end")
        left, right = sorted((width.dxf.defpoint2, width.dxf.defpoint3), key=lambda p: p.x)
        self.assertAlmostEqual(left.y, front.at[1] - 20 + 8, delta=0.1, msg="the left end is the base's top")
        self.assertAlmostEqual(right.y, front.at[1] + 20, delta=0.1, msg="the right end is the tab's top")


def _plate():
    """80 x 50 x 6 with four ⌀5.5 holes at (±30, ±18) and a ⌀20 bore in the middle."""
    from build123d import Align, Box, Cylinder, Pos

    align = (Align.CENTER, Align.CENTER, Align.MIN)
    part = Box(80, 50, 6, align=align) - Cylinder(10, 6, align=align)
    for x in (-30, 30):
        for y in (-18, 18):
            part -= Pos(x, y, 0) * Cylinder(2.75, 6, align=align)
    return part


def _counterbored():
    from build123d import Align, Box, BuildPart, CounterBoreHole, Locations, Pos

    with BuildPart() as part:
        Box(60, 40, 12, align=(Align.CENTER, Align.CENTER, Align.MIN))
        with Locations(Pos(-15, 0, 12), Pos(15, 0, 12)):
            CounterBoreHole(radius=3.3, counter_bore_radius=5.5, counter_bore_depth=6.5)
    return part.part


def _shaft():
    from build123d import Align, Cylinder, Pos, Rot

    align = (Align.CENTER, Align.CENTER, Align.MIN)
    along_x = Rot(0, 90, 0)
    return (Pos(-50, 0, 0) * along_x * Cylinder(10, 30, align=align)
            + Pos(-20, 0, 0) * along_x * Cylinder(15, 40, align=align)
            + Pos(20, 0, 0) * along_x * Cylinder(10, 30, align=align))


def _callouts(doc, h: float = 3.5) -> list[str]:
    """Each callout as a reader reads it: its text runs and its drawn symbols, left
    to right along one line, the symbols spelled the way hole_callout_text spells
    them. A symbol is line work on the DIM layer with its own stroke weight; which
    one it is follows from its shape."""
    rows: dict[float, list[tuple[float, str]]] = {}

    def put(mid: float, x: float, piece: str) -> None:
        key = next((k for k in rows if abs(k - mid) < h * 0.3), round(mid, 3))
        rows.setdefault(key, []).append((x, piece))

    msp = doc.modelspace()
    for text in msp.query("TEXT[layer=='DIM']"):
        put(text.dxf.insert.y, text.dxf.insert.x, text.dxf.text)
    for circle in msp.query("CIRCLE[layer=='DIM']"):
        put(circle.dxf.center.y, circle.dxf.center.x - 0.5 * h, "%%c")
    for line in msp.query("LWPOLYLINE[layer=='DIM']"):
        points = list(line.get_points("xy"))
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        if len(points) == 4:
            put(min(ys) + h / 2, min(xs) - 0.12 * h, "\u2334")
        elif len(points) == 3 and max(xs) - min(xs) > 0.6 * h:
            put(min(ys) + h / 2, min(xs) - 0.1 * h, "\u2335")
        elif len(points) == 3:
            put(min(ys) + h / 2, min(xs) - 0.18 * h, "\u21a7")
    return ["".join(piece for _x, piece in sorted(row)) for _y, row in sorted(rows.items(), reverse=True)]


class FromThePartTests(unittest.TestCase):
    """A callout's numbers are the part's: read off it, or checked against it."""

    def test_holes_leaves_a_kind_a_hole_call_states_to_that_call(self) -> None:
        """A first pass's holes() and the fit the person gave one bore: one callout."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, _front, _right = sheet.three_views(_part())
        top.holes()
        top.hole((10, 5, 10), fit="H7")
        self.assertEqual(_callouts(_render_sheet(sheet, index=1, count=1, label="fit")), ["%%c6 H7 THRU"])

    def test_a_hole_callout_reads_every_size_off_the_part(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_counterbored(), "top", at=(140, 120)).hole((15, 0, 12))
        self.assertEqual(_callouts(_render_sheet(sheet, index=1, count=1, label="cb")),
                         ["2× %%c6.6 THRU   ⌴ %%c11 ↧6.5"])

    def test_a_typed_size_the_part_contradicts_is_refused(self) -> None:
        """A callout that says ⌀6 over a ⌀6.6 bore is machined faithfully, and wrong."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        for given, named in (({"diameter": 6}, "diameter=6"), ({"count": 3}, "count=3"),
                             ({"depth": 8}, "depth=8"), ({"cbore": (12, 6.5)}, "cbore=(12, 6.5)")):
            with self.subTest(given=given):
                sheet = Sheet("A4")
                sheet.view(_counterbored(), "top", at=(140, 120)).hole((15, 0, 12), **given)
                with self.assertRaises(ValueError) as caught:
                    _render_sheet(sheet, index=1, count=1, label="cb")
                self.assertIn(named, str(caught.exception))
                self.assertIn("2× ⌀6.6 THRU", str(caught.exception), "the message states what the part has")
        # What agrees with the part is accepted and changes nothing.
        sheet = Sheet("A4")
        sheet.view(_counterbored(), "top", at=(140, 120)).hole((15, 0, 12), 6.6, thru=True, count=2,
                                                               cbore=(11, 6.5))
        self.assertEqual(_callouts(_render_sheet(sheet, index=1, count=1, label="cb")),
                         ["2× %%c6.6 THRU   ⌴ %%c11 ↧6.5"])

    def test_a_callout_where_there_is_no_hole_names_the_holes_there_are(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_counterbored(), "top", at=(140, 120)).hole((0, 0, 12))
        with self.assertRaisesRegex(ValueError, r"no hole runs along .* at \(-15, 0, 12\)"):
            _render_sheet(sheet, index=1, count=1, label="none")
        sheet = Sheet("A4")
        sheet.view(_counterbored(), "front", at=(140, 120)).hole((15, 0, 12))
        with self.assertRaisesRegex(ValueError, "looks down no hole"):
            _render_sheet(sheet, index=1, count=1, label="side")

    def test_a_typed_hole_over_a_boss_is_refused_not_printed(self) -> None:
        # A ⌀15 boss draws a ⌀15 circle: a callout typed over it once printed "4× ⌀15 THRU" on a solid boss.
        import build123d as bd

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        bottom = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
        part = bd.Box(80, 60, 10, align=bottom) + bd.Pos(25, 0, 10) * bd.Cylinder(7.5, 6, align=bottom)
        sheet = Sheet("A3")
        sheet.view(part, "top", at=(200, 150)).hole((25, 0, 16), 15, thru=True, count=4)
        with self.assertRaisesRegex(ValueError, r"no hole runs along the top view's line of sight there, so a "
                                                r"callout there states what nothing checks"):
            _render_sheet(sheet, index=1, count=1, label="boss")

    def test_a_counterbore_on_the_far_side_belongs_to_the_other_view(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_counterbored(), "bottom", at=(140, 120)).hole((15, 0, 0))
        with self.assertRaisesRegex(ValueError, "top view"):
            _render_sheet(sheet, index=1, count=1, label="far")

    def test_holes_calls_out_each_kind_of_hole_once(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_plate(), "top", at=(140, 120)).holes()
        self.assertEqual(sorted(_callouts(_render_sheet(sheet, index=1, count=1, label="all"))),
                         sorted(["4× %%c5.5 THRU", "%%c20 THRU"]))

    def test_diameter_and_radius_are_measured_off_the_view(self) -> None:
        from build123d import Align, Box, fillet, Axis
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        right = sheet.view(_shaft(), "right", at=(140, 120))
        right.diameter((0, 0, 0))
        with self.assertRaisesRegex(ValueError, r"share that centre \(⌀20, ⌀30\); pass size="):
            _render_sheet(sheet, index=1, count=1, label="d")
        sheet = Sheet("A4")
        sheet.view(_shaft(), "right", at=(140, 120)).diameter((0, 0, 0), size=30)
        self.assertEqual(_callouts(_render_sheet(sheet, index=1, count=1, label="d")), ["%%c30"])
        sheet = Sheet("A4")
        sheet.view(_shaft(), "right", at=(140, 120)).diameter((0, 0, 0), size=25)
        with self.assertRaisesRegex(ValueError, "no circle of that size"):
            _render_sheet(sheet, index=1, count=1, label="d")

        corners = fillet(Box(60, 40, 5, align=(Align.CENTER, Align.CENTER, Align.MIN)).edges().filter_by(Axis.Z), 6)
        sheet = Sheet("A4")
        sheet.view(corners, "top", at=(140, 120)).radius((24, 14, 5))
        self.assertEqual(_callouts(_render_sheet(sheet, index=1, count=1, label="r")), ["R6"])

    def test_a_leader_points_at_the_centre_of_its_circle(self) -> None:
        """ISO 128 and ASME Y14.2 both: a leader to a circle is radial."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_plate(), "top", at=(140, 120)).hole((30, 18, 6), angle=70)
        doc = _render_sheet(sheet, index=1, count=1, label="radial")
        leader = doc.modelspace().query("LEADER")[0]
        start, knee = leader.vertices[0], leader.vertices[1]
        centre = (140 + 30, 120 + 18)
        self.assertAlmostEqual(math.hypot(start[0] - centre[0], start[1] - centre[1]), 2.75, places=4,
                               msg="the arrow stops on the circle")
        cross = (start[0] - centre[0]) * (knee[1] - centre[1]) - (start[1] - centre[1]) * (knee[0] - centre[0])
        self.assertAlmostEqual(cross, 0.0, places=6, msg="and its line runs through the centre")


class ReviewFindingTests(unittest.TestCase):
    """Plausible-wrong output the first review of the hole reader found."""

    def test_holes_drilled_from_the_other_face_are_their_own_callout(self) -> None:
        from build123d import Align, Box, Cylinder, Pos
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import Sheet

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(80, 40, 20, align=align)
        for x in (-30, -10):
            part -= Pos(x, 0, 12) * Cylinder(3, 8, align=align)
        for x in (10, 30):
            part -= Pos(x, 0, 0) * Cylinder(3, 8, align=align)
        sheet = Sheet("A3")
        top, front, _right = sheet.three_views(part)
        top.holes()
        top.overall()
        front.overall(width=False)
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="faces", facts=facts)
        self.assertEqual(_callouts(_render_sheet(sheet, index=1, count=1, label="faces")), ["2× %%c6 ↧8"])
        missing = [line for line in _unstated(facts) if "not called out" in line]
        self.assertEqual(len(missing), 1, missing)
        self.assertIn("2× ⌀6 ↧8 is not called out", missing[0], "the pair drilled from below")

    def test_a_section_calls_out_only_the_holes_it_keeps(self) -> None:
        from build123d import Align, Box, Cylinder, Pos, Rot
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(60, 40, 20, align=align) - Pos(10, -20, 10) * Rot(-90, 0, 0) * Cylinder(3, 6, align=align)
        sheet = Sheet("A3")
        _top, front, _right = sheet.three_views(part)
        front.section("A")
        front.holes()
        notices: list[str] = []
        doc = _render_sheet(sheet, index=1, count=1, label="kept", warnings=notices)
        self.assertEqual(_callouts(doc), [], "the hole is in the half the section took away")
        self.assertTrue(any("looks down no hole" in n for n in notices), notices)

    def test_a_hole_callout_does_not_state_a_boss_of_its_radius(self) -> None:
        from build123d import Align, Box, Cylinder, Pos
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import Sheet

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(80, 60, 10, align=align) - Pos(-20, 0, 0) * Cylinder(15, 10, align=align) \
            + Pos(25, 0, 10) * Cylinder(7.5, 6, align=align)
        sheet = Sheet("A3")
        top, front, _right = sheet.three_views(part)
        top.overall()
        top.holes()
        front.overall(width=False)
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="boss", facts=facts)
        self.assertTrue(any("⌀15" in line for line in _unstated(facts)), "the ⌀15 boss is still unstated")

    def test_an_isometric_the_author_relabelled_keeps_its_label(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        iso = sheet.three_views(_plate(), iso=True)[3]
        iso.label = "PICTORIAL (REF)"
        texts = [e.dxf.text for e in _render_sheet(sheet, index=1, count=1, label="iso").modelspace().query("TEXT")]
        self.assertIn("PICTORIAL (REF)", texts)
        self.assertEqual(iso.label, "PICTORIAL (REF)")


def _drilled(spots, diameter: float = 5.0, depth: float | None = None):
    """A 60 × 40 × 20 plate with identical holes at ``spots``, down from its top:
    through, or ``depth`` deep."""
    from build123d import Align, Box, Cylinder, Pos

    align = (Align.CENTER, Align.CENTER, Align.MIN)
    plate = Box(60, 40, 20, align=align)
    run = depth or 20
    for x, y in spots:
        plate -= Pos(x, y, 20 - run) * Cylinder(diameter / 2, run, align=align)
    return plate


_FOUR = ((-20, -10), (20, -10), (-20, 10), (20, 10))


class ThreadCalloutTests(unittest.TestCase):
    """A tapped hole's callout: the thread is the one size the part does not
    carry, so what it can check -- the bore under it, the count, the depth -- is
    checked, and what it cannot is asked for, never assumed."""

    def _callouts(self, part, call) -> list[str]:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        call(sheet.view(part, "top", at=(100, 150)))
        return [c for c in _callouts(_render_sheet(sheet, index=1, count=1, label="thread")) if c.strip()]

    def test_the_thread_must_fit_the_bore(self) -> None:
        with self.assertRaisesRegex(ValueError, r"thread='M10x1.5 - 6H' does not fit the part's hole, which reads "
                                                r"⌀5 THRU"):
            self._callouts(_drilled([(0, 0)]), lambda v: v.hole((0, 0, 20), thread="M10x1.5 - 6H"))
        # The tap drill (⌀5 for M6x1) and the thread's own size (⌀6) both carry it.
        self.assertEqual(self._callouts(_drilled([(0, 0)]), lambda v: v.hole((0, 0, 20), thread="M6x1 - 6H")),
                         ["M6x1 - 6H THRU"])
        self.assertEqual(self._callouts(_drilled([(0, 0)], 6.0), lambda v: v.hole((0, 0, 20), thread="M6")),
                         ["M6 THRU"])

    def test_a_thread_is_a_metric_or_unified_one_or_refused(self) -> None:
        from cadgen.eng_drawing import Sheet

        view = Sheet("A4").view(_drilled([(0, 0)]), "top", at=(100, 150))
        for thread, message in (("", "is not a thread this drawing can check"), ("hello", "is not a thread this drawing"),
                                ("M50", "ISO 261 gives M50 no coarse pitch to assume"),
                                ("M6x7", r"ISO 261 gives M6 the pitches 1, 0.75, not 7"),
                                ("M6x5", r"ISO 261 gives M6 the pitches 1, 0.75, not 5"),
                                ("M6x0.5", r"ISO 261 gives M6 the pitches 1, 0.75, not 0.5"),
                                ("M13", "M13 is not an ISO 261 size"),
                                ("M6x1 - 6g", "external thread's tolerance class"),
                                ("M6x1 - 6E", "6E is not an ISO 965-1 class for a tapped hole"),
                                ("M6x1 - 9H", "9H is not an ISO 965-1 class"),
                                ("1/4-28 UNC", r"ASME B1.1 gives 1/4 UNC 20, UNF 28, UNEF 32 threads per inch, so "
                                               r"1/4-28 UNC is no unified thread; write one of 1/4-20 UNC"),
                                ("#10-28 UNF", "gives #10 UNC 24, UNF 32"),
                                ("3/8-20 UNS", "3/8-20 UNS is no unified thread"),
                                ("1/4-20 UNC-2A", "2A is an external thread's class"),
                                ("#14-20 UNC", "#14 is not an ASME B1.1 unified size"),
                                ("0.375-24 UNF", "is not a thread this drawing can check")):
            with self.subTest(thread=thread), self.assertRaisesRegex(ValueError, message):
                view.hole((0, 0, 20), thread=thread)

    def test_a_special_pitch_or_an_inch_thread_is_checked_against_its_tap_drill(self) -> None:
        # Fine metric pitches and unified inch threads print as given over the bore their pitch takes: M6x0.75
        # over ⌀5.2, 1/4-20 UNC over its #7 drill (⌀5.11), #10-32 UNF over its #21 drill (⌀4.04), 1-8 UNC (the
        # inch, since #1 has no 8) over ⌀22.25 and 10-24 UNC (the numbered size) over its #25 drill (⌀3.8).
        for bore, thread in ((5.2, "M6x0.75 - 6H"), (5.11, "1/4-20 UNC-2B"), (4.04, "#10-32 UNF"),
                             (22.25, "1-8 UNC"), (3.8, "10-24 UNC"), (5.2, "M6x0.75 - 5H6H LH")):
            with self.subTest(thread=thread):
                self.assertEqual(self._callouts(_drilled([(0, 0)], bore), lambda v, t=thread: v.hole((0, 0, 20), thread=t)),
                                 [f"{thread} THRU"])
        with self.assertRaisesRegex(ValueError, r"thread='1/4-20 UNC' does not fit the part's hole"):
            self._callouts(_drilled([(0, 0)], 4.04), lambda v: v.hole((0, 0, 20), thread="1/4-20 UNC"))

    def test_a_thread_takes_no_diameter_tolerance_or_fit(self) -> None:
        from cadgen.eng_drawing import Sheet

        view = Sheet("A4").view(_drilled([(0, 0)]), "top", at=(100, 150))
        for given, named in (({"diameter": 8}, "diameter"), ({"tol": 0.1, "fit": "H7"}, "tol, fit")):
            with self.subTest(given=given), self.assertRaisesRegex(ValueError, f"takes no {named}"):
                view.hole((0, 0, 20), thread="M6x1 - 6H", **given)

    def test_the_count_is_the_tapped_holes_not_every_identical_bore(self) -> None:
        part = _drilled(_FOUR)
        # One of four identical bores: which are tapped is the author's to say.
        with self.assertRaisesRegex(ValueError, "4 holes that read ⌀5 THRU, and nothing in it says which are "
                                                "tapped. Pass count=4"):
            self._callouts(part, lambda v: v.hole((-20, -10, 20), thread="M6x1 - 6H"))
        self.assertEqual(self._callouts(part, lambda v: v.hole((-20, -10, 20), thread="M6x1 - 6H", count=1)),
                         ["M6x1 - 6H THRU"])
        self.assertEqual(self._callouts(part, lambda v: v.hole((-20, -10, 20), thread="M6x1 - 6H", count=4)),
                         ["4× M6x1 - 6H THRU"])
        with self.assertRaisesRegex(ValueError, "count=2 taps some of the 4 identical holes"):
            self._callouts(part, lambda v: v.hole((-20, -10, 20), thread="M6x1 - 6H", count=2))
        # holes() calls out the rest, plain, and the count is theirs.
        self.assertEqual(sorted(self._callouts(part, lambda v: (v.holes(), v.hole((-20, -10, 20), thread="M6",
                                                                                 count=1)))),
                         ["3× %%c5 THRU", "M6 THRU"])

    def test_a_blind_tapped_hole_states_the_drill_and_the_thread_depth(self) -> None:
        part = _drilled([(0, 0)], depth=12)
        with self.assertRaisesRegex(ValueError, "pass depth= for the thread's depth"):
            self._callouts(part, lambda v: v.hole((0, 0, 20), thread="M6x1 - 6H"))
        self.assertEqual(self._callouts(part, lambda v: v.hole((0, 0, 20), thread="M6x1 - 6H", depth=10)),
                         ["%%c5 ↧12   M6x1 - 6H ↧10"])
        with self.assertRaisesRegex(ValueError, "a thread runs no deeper than its bore"):
            self._callouts(part, lambda v: v.hole((0, 0, 20), thread="M6x1 - 6H", depth=14))
        # Tapped part of the way through a through hole.
        self.assertEqual(self._callouts(_drilled([(0, 0)]), lambda v: v.hole((0, 0, 20), thread="M6", depth=8)),
                         ["%%c5 THRU   M6 ↧8"])
        # A bore at the thread's own size is the thread: its depth is the bore's.
        with self.assertRaisesRegex(ValueError, "it is the thread, and depth=10 contradicts it"):
            self._callouts(_drilled([(0, 0)], 6.0, depth=12), lambda v: v.hole((0, 0, 20), thread="M6", depth=10))

    def test_one_hole_takes_one_callout(self) -> None:
        with self.assertRaisesRegex(ValueError, r"top.hole\(\(0, 0, 20\)\) and top.hole\(\(0, 0, 20\)\) both call out "
                                                r"the hole at \(0, 0, 20\)"):
            self._callouts(_drilled([(0, 0)]), lambda v: (v.hole((0, 0, 20)), v.hole((0, 0, 20), thread="M6")))

    def test_a_hole_table_lists_a_tapped_hole_with_its_thread(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        top = sheet.view(_drilled([(-20, -10), (20, 10)]), "top", at=(100, 150))
        top.hole_table()
        top.hole((-20, -10, 20), thread="M6x1 - 6H", count=1)
        doc = _render_sheet(sheet, index=1, count=1, label="table")
        sizes = [e.dxf.text for e in doc.modelspace().query("TEXT[layer=='NOTES']")]
        self.assertIn("M6x1 - 6H THRU", sizes, "the tapped hole's row gives its thread")
        self.assertIn("5 THRU", sizes, "the plain one keeps its own row (its ⌀ drawn as a symbol)")
        self.assertEqual(_callouts(doc), ["A1", "B1", "Y", "0,0X"], "each tagged on the view, no leader callout")
        sheet = Sheet("A4")
        top = sheet.view(_drilled([(-20, -10), (20, 10)]), "top", at=(100, 150))
        top.hole_table()
        top.hole((-20, -10, 20))
        with self.assertRaisesRegex(ValueError, "both tabulates its holes and calls them out"):
            _render_sheet(sheet, index=1, count=1, label="table")


class SteppedHoleCalloutTests(unittest.TestCase):
    """A hole no one callout states is refused where a callout would state it,
    and named, not called out wrong, where the drawing leaves it unstated."""

    def test_a_chamfered_counterbore_is_refused_not_called_a_countersink(self) -> None:
        from build123d import Align, Axis, Box, Cylinder, GeomType, Pos, SortBy

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _Facts, _unstated
        from cadgen.eng_drawing import Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(40, 40, 12, align=up) - Cylinder(3.3, 12, align=up) - Pos(0, 0, 5.5) * Cylinder(5.5, 6.5, align=up)
        mouth = part.edges().filter_by(GeomType.CIRCLE).filter_by_position(Axis.Z, 11.9, 12.1).sort_by(SortBy.RADIUS)
        part = part.chamfer(0.5, None, mouth[-1:])
        for call in (lambda v: v.holes(), lambda v: v.hole((0, 0, 12)), lambda v: v.hole_table()):
            sheet = Sheet("A3")
            call(sheet.view(part, "top", at=(200, 150)))
            with self.subTest(call=call), self.assertRaisesRegex(ValueError, "cannot be stated in one callout: its "
                                                                             "mouth opens out in 2 steps"):
                _render_sheet(sheet, index=1, count=1, label="stepped")
        sheet = Sheet("A3")
        sheet.view(part, "top", at=(200, 150))
        facts = _Facts()
        _render_sheet(sheet, index=1, count=1, label="stepped", facts=facts)
        self.assertTrue(any("the hole at (0, 0, 12) (its mouth opens out in 2 steps" in line
                            for line in _unstated(facts)), _unstated(facts))

    def test_a_blind_slot_over_a_through_hole_is_called_blind(self) -> None:
        from build123d import Align, Box, Cylinder, Pos, SlotCenterToCenter, extrude

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(60, 40, 10, align=up) - Pos(0, 0, 5) * extrude(SlotCenterToCenter(20, 8), 5) - Cylinder(2, 10)
        sheet = Sheet("A3")
        sheet.view(part, "top", at=(200, 150)).holes()
        self.assertEqual(sorted(_callouts(_render_sheet(sheet, index=1, count=1, label="slot"))),
                         ["%%c4 THRU", "8 × 28 SLOT ↧5"])


class ConsoleTests(unittest.TestCase):
    def test_a_notice_prints_on_a_console_that_cannot_encode_its_symbols(self) -> None:
        """Windows CI's cp1252 console has no ⌀: the notice raised after the PDF
        was written, and the drawing failed from the message, not the work."""
        import io
        from unittest import mock

        from cadgen.eng_drawing import Sheet, eng_drawing

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as tmp:
            out = Path(tmp) / "plate.pdf"

            @eng_drawing(out=str(out))
            def plate():
                sheet = Sheet("A4")
                sheet.view(_plate(), "top", at=(140, 110))  # its holes are never called out
                return sheet

            console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
            with mock.patch.object(sys, "stdout", console):
                self.assertEqual(plate(), [out])
                console.flush()
                printed = console.buffer.getvalue().decode("cp1252")
            self.assertIn("\\u2300", printed, "the diameter sign as an escape, not an exception")
            self.assertTrue(out.exists())


class ColdTrialTests(unittest.TestCase):
    """What an agent given only the skill tripped over."""

    def test_a_bore_chamfered_at_both_ends_is_called_out_both_ends(self) -> None:
        from build123d import Align, Box, Cone, Cylinder, Pos
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        part = (Box(40, 40, 12, align=align) - Cylinder(5, 12, align=align)
                - Pos(0, 0, 11) * Cone(5, 6, 1, align=align) - Cone(6, 5, 1, align=align))
        sheet = Sheet("A4")
        sheet.view(part, "top", at=(140, 110)).holes()
        # Wider than a line holds (_CALLOUT_WRAP), it stacks a stage a line, as drafters write one.
        self.assertEqual(_callouts(_render_sheet(sheet, index=1, count=1, label="both")),
                         ["%%c10 THRU", "⌵ %%c12 × 90° BOTH ENDS"])

    def test_a_hole_inside_a_break_is_refused_not_left_off(self) -> None:
        # A ⌀1 hole is under the break's own check, so holes() once dropped it with only a warning.
        import build123d as bd

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        up = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
        bar = bd.Box(600, 40, 10, align=up) - bd.Pos(250, 0, 0) * bd.Cylinder(3, 10, align=up) \
            - bd.Cylinder(0.5, 10, align=up)
        sheet = Sheet("A3")
        top = sheet.view(bar, "top", at=(200, 150))
        top.broken((-150, 0, 5), (150, 0, 5))
        top.holes()
        with self.assertRaisesRegex(ValueError, r"top\.holes\(\): 1 hole\(s\) or slot\(s\) at \(0, 0, 10\) are "
                                                r"inside the break"):
            _render_sheet(sheet, index=1, count=1, label="lost")

    def test_a_section_whose_plane_no_view_shows_is_refused(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_counterbored(), "front", at=(140, 110)).section("A")
        with self.assertRaisesRegex(ValueError, r"SECTION A-A has no view on this sheet that sees its cutting plane "
                                                r"edge-on, so nothing shows where it cuts; add the top view"):
            _render_sheet(sheet, index=1, count=1, label="alone")

    def test_a_dimension_that_could_measure_either_span_is_refused(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        front = sheet.view(_plate(), "front", at=(140, 110))
        front.dim((-40, -25, 0), (40, -25, 6))  # 80 across, 6 up: no doubt which
        _render_sheet(sheet, index=1, count=1, label="clear")
        front.dim((40, -25, 0), (34, -25, 6))   # 6 across, 6 up: either
        with self.assertRaisesRegex(ValueError, r"front dim 1: its points are 6 apart across and 6 up, so it could "
                                                r"measure either\. Pass orientation="):
            _render_sheet(sheet, index=1, count=1, label="either")
        sheet = Sheet("A4")
        sheet.view(_plate(), "front", at=(140, 110)).dim((40, -25, 0), (34, -25, 6), orientation="v")
        _render_sheet(sheet, index=1, count=1, label="said")

    def test_a_part_that_is_several_solids_is_refused(self) -> None:
        from build123d import Align, Box, Pos
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        split = Box(30, 20, 10, align=align) - Box(4, 30, 20, align=(Align.CENTER, Align.CENTER, Align.CENTER))
        sheet = Sheet("A4")
        sheet.view(split, "top", at=(140, 110))
        with self.assertRaisesRegex(ValueError, "the part in the top view is 2 separate solids"):
            _render_sheet(sheet, index=1, count=1, label="split")

    def test_a_dimension_to_a_hole_centre_extends_the_centre_line(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_plate(), "top", at=(140, 110)).dim((-30, -18, 6), (-40, -18, 6))
        doc = _render_sheet(sheet, index=1, count=1, label="ext")
        dim = doc.modelspace().query("DIMENSION")[0]
        types = {e.dxf.linetype.upper() for e in doc.blocks.get(dim.dxf.geometry)
                 if e.dxftype() == "LINE" and e.dxf.hasattr("linetype")}
        self.assertIn("CENTER", types, "the extension line from the hole centre is a centre line")


class AssemblyEdgeTests(unittest.TestCase):
    """What a whole assembly brought out that single parts never did. The case was
    a motorcycle shock absorber, whose coil spring is 156 tilted cylinders fused
    into one solid -- too slow to build here, so each failure is forced."""

    def test_a_curve_occt_cannot_measure_is_sampled_by_its_parameter(self) -> None:
        from unittest import mock

        from build123d import Edge
        from cadgen._internal.drawing_views import _edge_polyline

        arc = Edge.make_spline([(0, 0, 0), (5, 3, 0), (10, 0, 0)])
        with mock.patch.object(type(arc), "position_at", side_effect=RuntimeError("Standard_Failure")):
            points = _edge_polyline(arc, samples=5)
        self.assertEqual(len(points), 5)
        self.assertAlmostEqual(points[0][0], 0.0, places=6)
        self.assertAlmostEqual(points[-1][0], 10.0, places=6)

    def test_an_edge_seen_end_on_draws_nothing(self) -> None:
        """A point is not a line; written, it is a zero-length entity the drawing
        checks refuse, and the whole sheet with it."""
        from unittest import mock

        import cadgen._internal.drawing_render as render
        from cadgen.engine.export.dxf import validate_drawing_document
        from cadgen.eng_drawing import Sheet

        real = render._edge_polyline

        def collapse(edge, samples=24):
            points = real(edge, samples)
            return [points[0]] * len(points) if len(points) > 2 else points

        sheet = Sheet("A4")
        sheet.view(_shaft(), "iso", at=(150, 110), hidden=False)
        with mock.patch.object(render, "_edge_polyline", collapse):
            doc = render._render_sheet(sheet, index=1, count=1, label="point")
        errors = [f.code for f in validate_drawing_document(doc, drawing=True) if f.severity == "error"]
        self.assertNotIn("zero_length_entity", errors)

    def test_a_coil_seen_from_the_top_projects_no_sliver_edge(self) -> None:
        """Not forced: three turns of the shock's coil, 18 tilted cylinders fused,
        seen from the top. Hidden-line removal hands back one ellipse 4e-8 mm long
        (the last 1.3e-7 rad before its seam); OCCT cannot measure along it, and the
        top view's overall dimensions, sampling the outline, failed the sheet with
        Standard_Failure. The sliver is a point and is not drawn; the coil is."""
        from cadgen._internal.drawing_base import VIEW_DIRECTIONS
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_views import _POINT_EDGE, _Projection
        from cadgen.eng_drawing import Sheet

        coil = _coil(turns=3, links_per_turn=6)
        proj = _Projection(coil, VIEW_DIRECTIONS["top"])
        edges = [*proj.visible, *proj.hidden]
        self.assertGreater(len(edges), 400, "the coil is drawn")
        self.assertTrue(all(edge.length >= _POINT_EDGE for edge in edges))
        for edge in edges:
            edge.position_at(0.5)  # every kept edge can be sampled along its length

        sheet = Sheet("A3")
        sheet.view(coil, "top", at=(150, 150)).overall()
        doc = _render_sheet(sheet, index=1, count=1, label="coil")
        size = coil.bounding_box().size
        self.assertEqual(sorted(_dim_texts(doc)), sorted([f"{size.X:.2f}", f"{size.Y:.2f}"]),
                         "both overall sizes, read off the whole coil")


def _coil(turns: float, links_per_turn: int):
    """The shock absorber's coil spring, built the same way and fewer turns: a
    ⌀75 mean helix of ⌀9 wire as straight cylinders, each one wire diameter longer
    than its step so it overlaps its neighbours, fused into one solid."""
    from build123d import Cylinder, Plane, Vector

    count = round(turns * links_per_turn)
    points = [Vector(37.5 * math.cos(turns * math.tau * i / count), 37.5 * math.sin(turns * math.tau * i / count),
                     100.0 / 6.5 * turns * i / count) for i in range(count + 1)]
    links = [Cylinder(4.5, (b - a).length + 9.0).moved(
        Plane(origin=tuple((a + b) * 0.5), z_dir=tuple((b - a).normalized())).location)
        for a, b in zip(points, points[1:])]
    return links[0].fuse(*links[1:])


class SymbolTests(unittest.TestCase):
    def test_drawing_symbols_are_line_work_not_glyphs(self) -> None:
        """⌴ and ⌵ are missing from common fonts and ezdxf fills Ø solid in the
        ones that have it, so no symbol reaches the page as a glyph."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        turned = Sheet("A3")
        _top, front, _right = turned.three_views(_shaft())
        front.dim((0, 0, -15), (0, 0, 15), text="%%c<>")
        cbored = Sheet("A4")
        cbored.view(_counterbored(), "top", at=(140, 120)).hole((15, 0, 12))
        for sheet in (turned, cbored):
            doc = _render_sheet(sheet, index=1, count=1, label="symbols")
            texts = [e.dxf.text for e in doc.modelspace().query("TEXT")]
            for dim in doc.modelspace().query("DIMENSION"):
                texts += [e.text for e in doc.blocks.get(dim.dxf.geometry) if e.dxftype() == "MTEXT"]
            for glyph in ("%%c", "\u00d8", "\u2300", "\u21a7", "\u2334", "\u2335"):
                self.assertFalse(any(glyph in text for text in texts), f"{glyph!r} set as a glyph: {texts}")
        doc = _render_sheet(turned, index=1, count=1, label="symbols")
        dim = next(d for d in doc.modelspace().query("DIMENSION")
                   if any(e.dxftype() == "CIRCLE" for e in doc.blocks.get(d.dxf.geometry)))
        values = [e.text for e in doc.blocks.get(dim.dxf.geometry) if e.dxftype() == "MTEXT"]
        self.assertEqual(values, ["30"], "the number stays text; the ⌀ beside it is drawn")

    def test_a_crowded_sheet_says_what_gives_it_room(self) -> None:
        from build123d import Align, Box
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        top, front, _right = sheet.three_views(Box(120, 60, 50, align=(Align.CENTER, Align.CENTER, Align.MIN)))
        top.overall()
        front.overall()
        for i in range(5):
            front.dim((-60 + 8 * i, -30, 50), (60, -30, 50))
        notices: list[str] = []
        _render_sheet(sheet, index=1, count=1, label="crowded", warnings=notices)
        crowded = [n for n in notices if n.startswith("views crowded")]
        self.assertEqual(len(crowded), 1, notices)
        self.assertIn('Sheet("A3")', crowded[0])
        self.assertIn("the largest ask is the front view's top side", crowded[0].lower())


class LayoutTests(unittest.TestCase):
    def test_dimensions_nest_shortest_nearest_the_view(self) -> None:
        """Given longest first, they would cross: the long one's extension lines
        through the short one's dimension line."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_plate(), "top", at=(140, 100)).dim((-40, 25, 6), (40, 25, 6)).dim((-30, 25, 6), (30, 25, 6))
        doc = _render_sheet(sheet, index=1, count=1, label="nest")
        rows = {round(abs(d.dxf.defpoint3.x - d.dxf.defpoint2.x)): d.dxf.defpoint.y
                for d in doc.modelspace().query("DIMENSION")}
        self.assertLess(rows[60], rows[80])

    def test_a_vertical_dimension_goes_on_its_own_side(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_plate(), "top", at=(140, 100)).dim((-30, -18, 6), (-30, 18, 6))
        dim = _render_sheet(sheet, index=1, count=1, label="left").modelspace().query("DIMENSION")[0]
        self.assertLess(dim.dxf.defpoint.x, 140 - 40, "left of the view, beside the holes it measures")

    def test_views_are_spaced_for_the_annotation_they_carry(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        def top_view_lift(rows: int) -> float:
            sheet = Sheet("A3")
            top, front, _right = sheet.three_views(_plate())
            front.overall()
            for i in range(rows):
                front.dim((-40 + 5 * i, -25, 6), (40, -25, 6))
            notices: list[str] = []
            _render_sheet(sheet, index=1, count=1, label="room", warnings=notices)
            self.assertEqual([n for n in notices if "overlaps" in n], [])
            return top.at[1] - front.at[1]

        self.assertGreater(top_view_lift(4), top_view_lift(0) + 4 * 12 - 1e-6,
                           "four more rows above the front view push the top view up by four rows")

    def test_a_value_wider_than_its_extension_lines_is_set_beside_them(self) -> None:
        """Centred, "3 WALL" printed with both witness lines through its glyphs."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        right = sheet.view(_plate(), "right", at=(140, 100))
        right.dim((40, -25, 0), (40, -25, 3), text="<> FLOOR")
        right.dim((40, 25, 0), (40, 25, 6))
        doc = _render_sheet(sheet, index=1, count=1, label="narrow")
        for dim in doc.modelspace().query("DIMENSION"):
            low, high = sorted((dim.dxf.defpoint2.y, dim.dxf.defpoint3.y))
            mtext = next(e for e in doc.blocks.get(dim.dxf.geometry) if e.dxftype() == "MTEXT")
            inside = low < mtext.dxf.insert.y < high
            if "FLOOR" in mtext.text:
                self.assertFalse(inside, "the wide value moved beside its 3 mm")
            else:
                self.assertTrue(inside, "a value that fits stays centred; only its arrows go outside")

    def test_a_value_set_beside_its_dimension_sits_on_its_dimension_line(self) -> None:
        """A 6 mm thickness with stacked deviations: the line runs on to the value, which starts just past it."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        right = sheet.view(_plate(), "right", at=(140, 100))
        right.dim((40, 25, 0), (40, 25, 6), tol=(0, 0.2))
        doc = _render_sheet(sheet, index=1, count=1, label="thin")
        dim = doc.modelspace().query("DIMENSION")[0]
        block = list(doc.blocks.get(dim.dxf.geometry))
        mtext = next(e for e in block if e.dxftype() == "MTEXT")
        top = max(dim.dxf.defpoint2.y, dim.dxf.defpoint3.y)
        self.assertGreater(mtext.dxf.insert.y, top, "set beside, past the 6 mm")
        self.assertLess(mtext.dxf.insert.y - top, 12, "close to the dimension it states")
        x = dim.dxf.defpoint.x
        run = max((max(e.dxf.start.y, e.dxf.end.y) for e in block if e.dxftype() == "LINE"
                   and abs(e.dxf.start.x - x) < 1e-6 and abs(e.dxf.end.x - x) < 1e-6), default=top)
        self.assertGreater(run, mtext.dxf.insert.y, "the dimension line runs on under the value")

    def test_a_turned_part_seen_from_the_side_has_one_centre_line_end_to_end(self) -> None:
        from cadgen._internal.drawing_base import _CENTRE_OVERSHOOT
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_shaft(), "front", at=(140, 100))
        lines = [e for e in _render_sheet(sheet, index=1, count=1, label="axis").modelspace().query("LINE")
                 if e.dxf.layer == "CENTER"]
        self.assertEqual(len(lines), 1, "three steps, one axis")
        xs = sorted((lines[0].dxf.start.x, lines[0].dxf.end.x))
        self.assertAlmostEqual(xs[1] - xs[0], 100 + 2 * _CENTRE_OVERSHOOT, places=6)
        self.assertAlmostEqual(lines[0].dxf.start.y, 100, places=6, msg="on the axis")


class SheetFurnitureTests(unittest.TestCase):
    def test_the_border_is_zoned(self) -> None:
        """ISO 5457: numbered columns and lettered rows, about 50 mm each, so a
        note or a phone call can say "see C4"."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", revision="X1")  # not a zone letter, so every A..F below is a zone's
        sheet.view(_plate(), "top", at=(200, 150))
        texts = [e.dxf.text for e in _render_sheet(sheet, index=1, count=1, label="z").modelspace().query("TEXT")]
        for label in [str(n) for n in range(1, 9)] + list("ABCDEF"):
            self.assertEqual(texts.count(label), 2, f"zone {label} marked on both edges")
        self.assertNotIn("G", texts)

    def test_the_projection_symbol_is_drawn_in_the_projection_it_names(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        def symbol(projection: str) -> tuple[float, float]:
            sheet = Sheet("A3", projection=projection)
            sheet.view(_plate(), "top", at=(200, 150))
            msp = _render_sheet(sheet, index=1, count=1, label="p").modelspace()
            circles = [c for c in msp.query("CIRCLE") if c.dxf.layer == "TITLE"]
            cone = next(p for p in msp.query("LWPOLYLINE") if p.dxf.layer == "TITLE" and len(p) == 4
                        and len({round(y, 3) for _x, y in p.get_points("xy")}) == 4)
            self.assertEqual(sorted(round(c.dxf.radius, 3) for c in circles), [1.5, 3.0])
            xs = [x for x, _y in cone.get_points("xy")]
            return circles[0].dxf.center.x, sum(xs) / len(xs)

        circles_x, cone_x = symbol("THIRD ANGLE")
        self.assertGreater(circles_x, cone_x, "third angle: the end view right of the cone")
        circles_x, cone_x = symbol("FIRST ANGLE")
        self.assertLess(circles_x, cone_x, "first angle: the end view left of it")

    def test_a_field_not_given_is_an_empty_captioned_cell(self) -> None:
        """No material is not "ABS": the cell says the drawing states none."""
        from cadgen._internal.drawing_base import _MARGIN, _TITLE_W
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_sheet import _TITLE_CELLS
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", title="T")
        sheet.view(_plate(), "top", at=(200, 150))
        msp = _render_sheet(sheet, index=1, count=1, label="m").modelspace()
        x, y, w, h = _TITLE_CELLS["MATERIAL"]
        x0, y0 = 420 - _MARGIN - _TITLE_W + x, _MARGIN + y
        inside = [e.dxf.text for e in msp.query("TEXT")
                  if x0 <= e.dxf.insert.x <= x0 + w and y0 <= e.dxf.insert.y <= y0 + h]
        self.assertEqual(inside, ["MATERIAL"])

    def test_a_unit_the_sheet_does_not_measure_in_is_refused(self) -> None:
        from cadgen.eng_drawing import Sheet

        with self.assertRaisesRegex(ValueError, "25.4"):
            Sheet("A3", units="in")


class UnstatedTests(unittest.TestCase):
    """The drawing says what it leaves out, read off the part."""

    def _unstated(self, build) -> list[str]:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated

        facts = _facts()
        _render_sheet(build(), index=1, count=1, label="u", facts=facts)
        return _unstated(facts)

    def test_holes_and_sizes_left_out_are_named_with_the_call_that_states_them(self) -> None:
        from cadgen.eng_drawing import Sheet

        def build():
            sheet = Sheet("A3")
            top, _front, _right = sheet.three_views(_plate())
            top.overall()
            return sheet

        lines = self._unstated(build)
        self.assertEqual(len(lines), 3, lines)
        self.assertTrue(any("4× ⌀5.5 THRU is not called out" in line and "top.holes()" in line for line in lines))
        self.assertTrue(any("⌀20 THRU is not called out" in line for line in lines))
        self.assertTrue(any("along Z (6)" in line and "front.overall()" in line for line in lines))

    def test_a_drawing_that_states_the_part_reports_nothing(self) -> None:
        from cadgen.eng_drawing import Sheet

        def build():
            sheet = Sheet("A3")
            top, front, _right = sheet.three_views(_plate())
            top.overall()
            top.holes()
            top.dim((-40, -18, 6), (-30, -18, 6))      # the pattern from the left edge
            top.dim((-30, -25, 6), (-30, -18, 6))      # and from the front edge
            top.dim((-30, 18, 6), (30, 18, 6))
            top.dim((30, -18, 6), (30, 18, 6))
            top.symmetric("h")
            top.symmetric("v")                         # the bore is centred
            front.overall(width=False)
            return sheet

        self.assertEqual(self._unstated(build), [])

    def test_a_turned_diameter_is_stated_and_states_the_width_across_it(self) -> None:
        from cadgen.eng_drawing import Sheet

        def build(stated: bool):
            def make():
                sheet = Sheet("A3")
                _top, front, _right = sheet.three_views(_shaft())
                front.overall(height=False)
                if stated:
                    front.dim((-35, 0, -10), (-35, 0, 10), text="%%c<>")
                    front.dim((0, 0, -15), (0, 0, 15), text="%%c<>")
                    front.dim((-50, 0, 10), (-20, 0, 10))      # the shoulders, placed
                    front.dim((20, 0, 10), (50, 0, 10))
                return sheet
            return make

        lines = self._unstated(build(False))
        self.assertTrue(any("⌀30" in line for line in lines) and any("⌀20" in line for line in lines), lines)
        self.assertEqual(self._unstated(build(True)), [], "⌀30 is the shaft's size in Y and in Z too")


class SectionTests(unittest.TestCase):
    """A section shows what hidden lines can only hint at."""

    def _sheet(self, part=None, **section):
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        top, front, _right = sheet.three_views(part if part is not None else _counterbored())
        front.section("A", **section)
        return sheet, top, front

    def test_a_section_hatches_what_it_cuts_and_leaves_hidden_lines_out(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet

        sheet, _top, front = self._sheet()
        doc = _render_sheet(sheet, index=1, count=1, label="sec")
        msp = doc.modelspace()
        hatches = list(msp.query("HATCH"))
        self.assertEqual(len(hatches), 3, "two counterbores split the cut face into three")
        self.assertTrue(all(h.dxf.pattern_name == "ANSI31" for h in hatches))
        labels = [e.dxf.text for e in msp.query("TEXT[layer=='NOTES']")]
        self.assertIn("SECTION A-A", labels)
        hidden_in_section = [e for e in msp.query("LINE LWPOLYLINE") if e.dxf.layer == "HIDDEN"
                             and all(abs(x - front.at[0]) <= 31 and abs(y - front.at[1]) <= 7
                                     for x, y in _points(e))]
        self.assertEqual(hidden_in_section, [], "a section draws no hidden lines")
        self.assertEqual(list(doc.audit().errors), [])

    def test_the_cutting_plane_is_drawn_where_it_is_seen_edge_on(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet

        sheet, top, _front = self._sheet(through=(0, 5, 0))
        msp = _render_sheet(sheet, index=1, count=1, label="sec").modelspace()
        plane_y = top.at[1] + 5  # the top view draws model Y up, at 1:1
        chain = [e for e in msp.query("LINE") if e.dxf.layer == "CENTER"
                 and abs(e.dxf.start.y - plane_y) < 1e-6 and abs(e.dxf.end.y - plane_y) < 1e-6]
        self.assertEqual(len(chain), 1, "one chain line across the top view, at the plane")
        self.assertGreater(abs(chain[0].dxf.end.x - chain[0].dxf.start.x), 60, "across the whole view")
        letters = [e for e in msp.query("TEXT[layer=='NOTES']") if e.dxf.text == "A"]
        self.assertEqual(len(letters), 2, "the letter at both ends")
        arrows = [l for l in msp.query("LEADER") if abs(l.vertices[1][1] - plane_y) < 1e-6]
        self.assertEqual(len(arrows), 2)
        for arrow in arrows:
            self.assertGreater(arrow.vertices[0][1], plane_y, "the front section is looked at toward +Y")

    def test_a_section_lines_up_with_the_view_above_it(self) -> None:
        """The half it keeps need not be symmetric; the drawing still aligns."""
        from build123d import Align, Box, Pos
        from cadgen._internal.drawing_render import _render_sheet

        align = (Align.MIN, Align.MIN, Align.MIN)
        step = Box(60, 20, 10, align=align) + Pos(0, 20, 0) * Box(30, 20, 25, align=align)
        sheet, top, front = self._sheet(step, through=(0, 30, 0))
        msp = _render_sheet(sheet, index=1, count=1, label="sec").modelspace()

        def xs(view):
            return [x for e in msp.query("LINE LWPOLYLINE") if e.dxf.layer == "VISIBLE"
                    for x, y in _points(e) if abs(y - view.at[1]) < 20 and abs(x - view.at[0]) < 40]

        self.assertAlmostEqual(min(xs(front)), min(xs(top)), places=6)
        self.assertLess(max(xs(front)), max(xs(top)) - 20, "it keeps only the 30 mm step, not the 60 mm base")

    def test_a_section_that_cannot_be_drawn_is_refused(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet, _top, _front = self._sheet(through=(0, 500, 0))
        with self.assertRaisesRegex(ValueError, "does not cut the part"):
            _render_sheet(sheet, index=1, count=1, label="miss")
        view = Sheet("A4").view(_plate(), "front", at=(150, 100))
        with self.assertRaisesRegex(ValueError, "ISO 128-40"):
            view.section("I")
        with self.assertRaisesRegex(ValueError, "isometric"):
            Sheet("A4").view(_plate(), "iso", at=(150, 100)).section()


class SlotAndBoltCircleTests(unittest.TestCase):
    def _plate(self):
        from build123d import Align, Box, Pos, SlotCenterToCenter, extrude

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        return _plate() - Pos(30, 0, 0) * extrude(SlotCenterToCenter(10, 6), 6) \
            - Pos(-30, 0, 0) * extrude(SlotCenterToCenter(10, 6), 6)

    def test_a_slot_is_called_out_from_the_part(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(self._plate(), "top", at=(140, 110)).holes()
        self.assertEqual(sorted(_callouts(_render_sheet(sheet, index=1, count=1, label="slot"))),
                         sorted(["2× 6 × 16 SLOT THRU", "4× %%c5.5 THRU", "%%c20 THRU"]))
        sheet = Sheet("A4")
        sheet.view(self._plate(), "top", at=(140, 110)).slot((35, 0, 6), width=8)
        with self.assertRaisesRegex(ValueError, r"reads 2× 6 × 16 SLOT THRU, but the callout was given width=8"):
            _render_sheet(sheet, index=1, count=1, label="slot")
        sheet = Sheet("A4")
        sheet.view(self._plate(), "top", at=(140, 110)).hole((30, 0, 6))
        with self.assertRaisesRegex(ValueError, r"that is a slot, not a hole; call it out with top.slot"):
            _render_sheet(sheet, index=1, count=1, label="slot")

    def test_a_slot_gets_its_centre_lines(self) -> None:
        """One down its length, past both rounded ends, and one across each end."""
        from cadgen._internal.drawing_base import _CENTRE_OVERSHOOT
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(self._plate(), "top", at=(140, 110))  # slots along X, ends at x = 25 and 35
        lines = [e for e in _render_sheet(sheet, index=1, count=1, label="slot").modelspace().query("LINE")
                 if e.dxf.layer == "CENTER"]
        along = [e for e in lines if abs(e.dxf.start.y - 110) < 1e-6 and abs(e.dxf.end.y - 110) < 1e-6
                 and min(e.dxf.start.x, e.dxf.end.x) < 170 < max(e.dxf.start.x, e.dxf.end.x)]
        self.assertEqual(len(along), 1)
        xs = sorted((along[0].dxf.start.x, along[0].dxf.end.x))
        self.assertAlmostEqual(xs[1] - xs[0], 16 + 2 * _CENTRE_OVERSHOOT, places=6)
        across = sorted(round(e.dxf.start.x, 6) for e in lines
                        if abs(e.dxf.start.x - e.dxf.end.x) < 1e-6 and abs(e.dxf.start.y - 110) < 12)
        self.assertIn(165.0, across)
        self.assertIn(175.0, across)

    def test_an_unstated_slot_is_reported(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        top, front, _right = sheet.three_views(self._plate())
        top.overall()
        top.hole((30, 18, 6))
        top.hole((0, 0, 6))
        front.overall(width=False)
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="slot", facts=facts)
        lines = [line for line in _unstated(facts) if "not called out" in line]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("2× 6 × 16 SLOT THRU is not called out", lines[0])
        self.assertIn("top.slot(", lines[0])

    def test_a_bolt_circle_is_stated_and_drawn(self) -> None:
        import math

        from build123d import Align, Cylinder, Pos
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        flange = Cylinder(40, 10, align=align) - Cylinder(15, 10, align=align)
        for k in range(6):
            a = 2 * math.pi * k / 6
            flange -= Pos(30 * math.cos(a), 30 * math.sin(a), 0) * Cylinder(3, 10, align=align)
        sheet = Sheet("A4")
        sheet.view(flange, "top", at=(140, 110)).holes()
        doc = _render_sheet(sheet, index=1, count=1, label="pcd")
        self.assertIn("6× %%c6 THRU EQ SP ON %%c60", _callouts(doc))
        pitch = [c for c in doc.modelspace().query("CIRCLE") if c.dxf.layer == "CENTER"]
        self.assertEqual([round(c.dxf.radius, 6) for c in pitch], [30.0], "the pitch circle as a chain line")

    def test_an_isometric_looks_down_no_hole(self) -> None:
        import math

        from build123d import Align, Cylinder, Pos
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        flange = Cylinder(40, 10, align=align) - Cylinder(15, 10, align=align)
        for k in range(6):
            a = 2 * math.pi * k / 6
            flange -= Pos(30 * math.cos(a), 30 * math.sin(a), 0) * Cylinder(3, 10, align=align)
        sheet = Sheet("A4")
        iso = sheet.view(flange, "iso", at=(140, 110))
        msp = _render_sheet(sheet, index=1, count=1, label="iso").modelspace()
        self.assertFalse(list(msp.query("CIRCLE LINE[layer=='CENTER']")),
                         "no pitch circle or centre marks: the isometric sees every hole slantwise")
        for call in (iso.holes, lambda: iso.hole((30, 0, 10)), lambda: iso.slot((30, 0, 10))):
            with self.assertRaisesRegex(ValueError, "isometric looks down no hole"):
                call()

    def test_overlapping_centre_lines_are_one_line(self) -> None:
        """Chain lines struck over each other out of phase print solid."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        sheet.view(_plate(), "top", at=(140, 110))
        lines = [e for e in _render_sheet(sheet, index=1, count=1, label="merge").modelspace().query("LINE")
                 if e.dxf.layer == "CENTER"]
        keys = {}
        for e in lines:
            a, b = e.dxf.start, e.dxf.end
            if abs(a.y - b.y) < 1e-6:
                keys.setdefault(("h", round(a.y, 4)), []).append(sorted((a.x, b.x)))
            elif abs(a.x - b.x) < 1e-6:
                keys.setdefault(("v", round(a.x, 4)), []).append(sorted((a.y, b.y)))
        for spans in keys.values():
            spans.sort()
            for (_a0, a1), (b0, _b1) in zip(spans, spans[1:]):
                self.assertGreater(b0, a1, "two centre lines on one line overlap")


class DetailTests(unittest.TestCase):
    def test_the_detail_letter_on_its_parent_stands_off_the_part(self) -> None:
        from build123d import Align, Box

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        _top, front = sheet.three_views(Box(120, 30, 40, align=(Align.CENTER, Align.CENTER, Align.MIN)),
                                        views=("top", "front"))
        sheet.detail(front, (20, 0, 0), 6, letter="C")     # on the bottom edge: up and right of it is the bar
        msp = _render_sheet(sheet, index=1, count=1, label="detail", warnings=[]).modelspace()
        lines = [e for e in msp.query("LINE LWPOLYLINE") if e.dxf.layer == "VISIBLE"]
        xs = [p[0] for e in lines for p in ([e.dxf.start, e.dxf.end] if e.dxftype() == "LINE" else e.get_points())]
        ys = [p[1] for e in lines for p in ([e.dxf.start, e.dxf.end] if e.dxftype() == "LINE" else e.get_points())]
        (letter,) = [e for e in msp.query("TEXT") if e.dxf.text == "C"
                     and min(xs) - 20 < e.dxf.align_point.x < max(xs) + 20 and min(ys) - 20 < e.dxf.align_point.y]
        x, y = letter.dxf.align_point.x, letter.dxf.align_point.y
        bottom = min(py for px, py in zip(xs, ys) if abs(px - x) < 60)   # the front view's lower edge
        self.assertLess(y, bottom, "below the bar, just off its edge, not on it")


    def _sheet(self, **detail):
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        top, front, right, iso = sheet.three_views(_shaft(), iso=True)
        front.overall(height=False)
        return sheet, front, sheet.detail(front, (50, 0, 10), 4, **detail)

    def test_a_detail_is_drawn_larger_clipped_and_marked(self) -> None:
        from cadgen._internal.drawing_base import _MARGIN
        from cadgen._internal.drawing_render import _render_sheet

        sheet, front, detail = self._sheet()
        msp = _render_sheet(sheet, index=1, count=1, label="detail").modelspace()
        self.assertEqual(detail.scale, 5.0, "the largest standard scale that keeps the circle within 60 mm")
        labels = [e.dxf.text for e in msp.query("TEXT[layer=='NOTES']")]
        self.assertIn("DETAIL B (5:1)", labels)
        self.assertIn("B", labels, "the letter beside the circle on the parent")
        rings = sorted(round(c.dxf.radius, 6) for c in msp.query("CIRCLE") if c.dxf.layer == "NOTES")
        self.assertEqual(rings, [4.0, 20.0], "the parent's circle at 1:1, the detail's boundary at 5:1")
        cx, cy = detail.at
        for entity in msp.query("LINE LWPOLYLINE"):
            if entity.dxf.layer != "VISIBLE":
                continue
            for x, y in _points(entity):
                if abs(x - cx) < 30 and abs(y - cy) < 30:
                    self.assertLessEqual(math.hypot(x - cx, y - cy), 20 + 1e-6, "geometry outside the circle")
        self.assertTrue(_MARGIN < cx - 20 and cx + 20 < 420 - _MARGIN and _MARGIN < cy - 20 and cy + 20 < 297 - _MARGIN)

    def test_a_detail_is_cut_by_cutting_its_parent(self) -> None:
        _sheet, _front, detail = self._sheet()
        with self.assertRaisesRegex(ValueError, "cut the parent view"):
            detail.section("A")

    def test_a_detail_steps_down_when_the_paper_is_short(self) -> None:
        """A scale the sheet chose gives way to the next standard one down; the
        label says the scale it was drawn at."""
        from unittest import mock

        import cadgen._internal.drawing_render as render
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        _top, front, _right = sheet.three_views(_shaft())
        detail = sheet.detail(front, (50, 0, 10), 2.5)
        self.assertEqual(detail.scale, 10.0)
        real = render._place_detail
        with mock.patch.object(render, "_place_detail",
                               side_effect=lambda sh, size, *a: None if size > 30 else real(sh, size, *a)):
            render._render_sheet(sheet, index=1, count=1, label="detail")
        self.assertEqual(detail.scale, 5.0)
        self.assertEqual(detail.label, "DETAIL B (5:1)")

    def test_a_detail_given_its_scale_is_refused_when_it_cannot_fit(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A4")
        _top, front, _right = sheet.three_views(_shaft())
        sheet.detail(front, (50, 0, 10), 10, scale=10)
        with self.assertRaisesRegex(ValueError, "no free paper"):
            _render_sheet(sheet, index=1, count=1, label="detail")

    def test_a_detail_of_a_section_keeps_the_hatching(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        _top, front, right = sheet.three_views(_counterbored())
        front.section("A")
        detail = sheet.detail(front, (15, 0, 12), 6, letter="C")
        doc = _render_sheet(sheet, index=1, count=1, label="detail")
        hatches = [h for h in doc.modelspace().query("HATCH")
                   if all(math.hypot(x - detail.at[0], y - detail.at[1]) <= 6 * detail.scale + 1e-3
                          for path in h.paths for x, y, *_ in path.vertices)]
        self.assertTrue(hatches, "the section's hatch, clipped to the detail")
        self.assertEqual(sum(1 for e in doc.modelspace().query("TEXT[layer=='NOTES']") if e.dxf.text == "A"), 2,
                         "one cutting plane, not one per view of the section")

    def test_a_detail_states_only_what_it_holds(self) -> None:
        """One identical hole in the circle is one callout; the other three are
        still unstated."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        top, front, _right = sheet.three_views(_plate())
        top.overall()
        top.hole((0, 0, 6))
        front.overall(width=False)
        sheet.detail(top, (30, 18, 6), 5).holes()
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="d", facts=facts)
        missing = [line for line in _unstated(facts) if "not called out" in line]
        self.assertEqual(len(missing), 1, missing)
        self.assertIn("3× ⌀5.5 THRU is not called out", missing[0])

    def test_a_detail_follows_a_section_made_after_it(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        _top, front, _right = sheet.three_views(_counterbored())
        detail = sheet.detail(front, (15, 0, 12), 6, letter="C")
        front.section("A")
        doc = _render_sheet(sheet, index=1, count=1, label="d")
        self.assertTrue(any(all(math.hypot(x - detail.at[0], y - detail.at[1]) <= 6 * detail.scale + 1e-3
                                for path in h.paths for x, y, *_ in path.vertices)
                            for h in doc.modelspace().query("HATCH")))

    def test_a_letter_names_one_view(self) -> None:
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        _top, front, right = sheet.three_views(_shaft())
        front.section("A")
        sheet.detail(front, (50, 0, 10), 4)
        with self.assertRaisesRegex(ValueError, "already names DETAIL B"):
            sheet.detail(front, (-50, 0, 10), 4)
        with self.assertRaisesRegex(ValueError, "already names SECTION A-A"):
            sheet.detail(right, (0, 0, 0), 4, letter="A")
        with self.assertRaisesRegex(ValueError, "already names SECTION A-A"):
            right.section("A")

    def test_a_detail_of_an_isometric_is_refused(self) -> None:
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        iso = sheet.three_views(_shaft(), iso=True)[3]
        with self.assertRaisesRegex(ValueError, "isometric"):
            sheet.detail(iso, (0, 0, 0), 5)
        with self.assertRaisesRegex(ValueError, "ISO 128-40"):
            sheet.detail(sheet.views[1], (0, 0, 0), 5, letter="O")

    def test_cutting_plane_letters_keep_clear_of_the_view_label(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        _top, front, right = sheet.three_views(_shaft())
        right.section("A", through=(0, 0, 0))
        msp = _render_sheet(sheet, index=1, count=1, label="letters").modelspace()
        label = next(e for e in msp.query("TEXT[layer=='NOTES']") if e.dxf.text == "FRONT")
        letters = [e for e in msp.query("TEXT[layer=='NOTES']") if e.dxf.text == "A"]
        lowest = min(e.dxf.insert.y for e in letters)
        self.assertLess(label.dxf.insert.y, lowest - 3, "the label hangs under the cutting plane's letter")


def _assembly():
    """A plate, two identical pins standing in its holes, a closed housing on it
    and a core sealed inside the housing, which no view can show."""
    from build123d import Align, Box, Compound, Cylinder, Pos

    base_align = (Align.CENTER, Align.CENTER, Align.MIN)
    base = Box(80, 50, 6, align=base_align) - Pos(25, 0, 0) * Cylinder(3, 6, align=base_align) \
        - Pos(-25, 0, 0) * Cylinder(3, 6, align=base_align)
    base.label = "base"
    pins = []
    for x in (-25, 25):
        pin = Pos(x, 0, 0) * Cylinder(3, 20, align=base_align)
        pin.label = "pin"
        pins.append(pin)
    housing = Pos(0, 0, 6) * (Box(20, 20, 10, align=base_align) - Pos(0, 0, 2) * Box(16, 16, 6, align=base_align))
    housing.label = "housing"
    core = Pos(0, 0, 9) * Box(4, 4, 4, align=base_align)
    core.label = "core"
    return Compound(children=[base, *pins, housing, core], label="fixture")


def _balloons(doc):
    """Each balloon as (item number, its centre, the point its leader keys)."""
    from cadgen._internal.drawing_assembly import _BALLOON_R, _BALLOON_TEXT

    msp = doc.modelspace()
    circles = [e for e in msp.query("CIRCLE[layer=='NOTES']") if abs(e.dxf.radius - _BALLOON_R) < 1e-9]
    numbers = [e for e in msp.query("TEXT[layer=='NOTES']") if abs(e.dxf.height - _BALLOON_TEXT) < 1e-9]
    lines = list(msp.query("LINE[layer=='NOTES']"))
    out = []
    for circle in circles:
        c = (circle.dxf.center.x, circle.dxf.center.y)
        number = next(int(t.dxf.text) for t in numbers
                      if math.hypot(t.dxf.align_point.x - c[0], t.dxf.align_point.y - c[1]) < 1e-6)
        leader = next(e for e in lines if abs(math.hypot(e.dxf.start.x - c[0], e.dxf.start.y - c[1]) - _BALLOON_R)
                      < 1e-6)
        out.append((number, c, (leader.dxf.end.x, leader.dxf.end.y)))
    return out


class AssemblyDrawingTests(unittest.TestCase):
    """An assembly drawn as one: a parts list read off it, balloons keyed to that
    list, and a sheet per part."""

    def test_the_parts_list_counts_copies_and_keeps_named_and_mirrored_parts_apart(self) -> None:
        from build123d import Box, Compound, Cylinder, Plane, Pos

        from cadgen.eng_drawing import parts_list

        parts = parts_list(_assembly())
        self.assertEqual([(i.number, i.description, i.quantity) for i in parts],
                         [(1, "BASE", 1), (2, "PIN", 2), (3, "HOUSING", 1), (4, "CORE", 1)])
        self.assertIs(parts["pin"], parts[2])
        self.assertEqual(len(parts[2].occurrences), 2)
        # Mirror images share a name and a volume, never a part number; and one
        # shape under two names may be two materials.
        bracket = Box(20, 10, 5) - Pos(5, 2, 0) * Cylinder(1.5, 5)
        left, right = Pos(0, 0, 0) * bracket, Pos(40, 0, 0) * bracket.mirror(Plane.YZ)
        left.label, right.label = "bracket:left", "bracket:right"
        spacer_a, spacer_b = Pos(0, 30, 0) * Box(5, 5, 5), Pos(10, 30, 0) * Box(5, 5, 5)
        spacer_a.label, spacer_b.label = "spacer_steel", "spacer_brass"
        kept = parts_list(Compound(children=[left, right, spacer_a, spacer_b]))
        self.assertEqual([i.quantity for i in kept], [1, 1, 1, 1])
        self.assertEqual([i.description for i in kept], ["BRACKET, LEFT", "BRACKET, RIGHT", "SPACER STEEL",
                                                         "SPACER BRASS"])

    def test_items_are_found_by_number_or_name_and_filled_in_only_where_asked(self) -> None:
        from cadgen.eng_drawing import parts_list

        parts = parts_list(_assembly())
        parts.set("base", material="6061-T6", part_number="FX-101").set(3, description="SEALED HOUSING")
        self.assertEqual((parts[1].material, parts[1].part_number), ("6061-T6", "FX-101"))
        self.assertEqual(parts[3].description, "SEALED HOUSING")
        self.assertEqual((parts[2].material, parts[2].part_number), ("", ""), "nothing invented")
        with self.assertRaisesRegex(KeyError, "its items are 1 base"):
            parts["washer"]
        with self.assertRaisesRegex(KeyError, "numbers 1 to 4"):
            parts[5]
        with self.assertRaisesRegex(TypeError, "not finish"):
            parts.set(1, finish="ANODISE")
        with self.assertRaisesRegex(TypeError, "single part"):
            parts_list(_plate())

    def test_a_read_assembly_counts_shared_prototypes(self) -> None:
        from build123d import Box, Compound, Cylinder, Location, export_step

        import cadgen
        from cadgen.eng_drawing import parts_list

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as tmp:
            pin = Cylinder(3, 20)
            placed = []
            for x in (-10.0, 10.0, 30.0):
                copy = pin.moved(Location((x, 0, 0)))
                copy.label = "pin"
                placed.append(copy)
            plate = Box(60, 20, 4)
            plate.label = "plate"
            # One geometry, two names: they are still two parts (a steel spacer is
            # not a brass one), listed as twins.
            steel, brass = Box(5, 5, 5).moved(Location((0, 30, 0))), Box(5, 5, 5).moved(Location((20, 30, 0)))
            steel.label, brass.label = "spacer_steel", "spacer_brass"
            path = Path(tmp) / "fixture.step"
            export_step(Compound(children=[plate, *placed, steel, brass], label="fixture"), str(path))
            # What a STEP reads back as: a compound tree, the pin one prototype placed three times.
            parts = parts_list(cadgen.read_step(path))
        self.assertEqual([(i.description, i.quantity) for i in parts],
                         [("PLATE", 1), ("PIN", 3), ("SPACER STEEL", 1), ("SPACER BRASS", 1)])
        self.assertEqual(parts[2].refs, ("pin.1", "pin.2", "pin.3"), "each as a ref names that occurrence")
        self.assertEqual(len(parts[2].prototypes), 1, "the three pins are one geometry, placed three times")
        self.assertEqual(parts.twins, ((3, 4),))
        parts.merge(3, 4, description="SPACER")
        self.assertEqual([(i.number, i.description, i.quantity) for i in parts],
                         [(1, "PLATE", 1), (2, "PIN", 3), (3, "SPACER", 2)])
        with self.assertRaisesRegex(ValueError, "not the same shape"):
            parts.merge(1, 2)

    def test_balloons_key_each_part_it_shows_once_with_a_dot_on_the_part(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        parts = parts_list(_assembly())
        sheet = Sheet("A3", title="FIXTURE")
        sheet.parts_list(parts)
        front = sheet.view(parts.assembly, "front", at=(110, 200), hidden=False)
        iso = sheet.view(parts.assembly, "iso", at=(110, 90), hidden=False)
        front.balloons(parts)
        iso.balloons(parts)
        warnings: list = []
        facts = _facts()
        doc = _render_sheet(sheet, index=1, count=1, label="balloons", warnings=warnings, facts=facts)
        found = _balloons(doc)
        self.assertEqual(sorted(n for n, _c, _p in found), [1, 2, 3], "the sealed core has no balloon")
        for _n, centre, point in found:
            self.assertGreater(math.hypot(centre[0] - point[0], centre[1] - point[1]), 5.0)
        dots = [e for e in doc.modelspace().query("HATCH[layer=='NOTES']")]
        self.assertEqual(len(dots), 3)
        self.assertFalse([w for w in warnings if "separate solids" in w], warnings)
        from cadgen._internal.drawing_report import _unstated

        report = _unstated(facts)
        self.assertTrue(any("item 4 (CORE) has no balloon" in line for line in report), report)
        self.assertFalse([line for line in report if "turned diameter" in line or "not called out" in line],
                         "an assembly's holes are its parts' to state")

    def test_a_column_of_balloons_keeps_its_leaders_in_order(self) -> None:
        from build123d import Box, Compound, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        stack = []
        for k in range(6):
            block = Pos(0, 0, 12 * k) * Box(30 - 2 * k, 30 - 2 * k, 10)
            block.label = f"block_{k}"
            stack.append(block)
        parts = parts_list(Compound(children=stack))
        sheet = Sheet("A3")
        sheet.parts_list(parts)
        sheet.view(parts.assembly, "front", at=(120, 180), hidden=False).overall().balloons(parts)
        doc = _render_sheet(sheet, index=1, count=1, label="column")
        found = _balloons(doc)
        self.assertEqual(len(found), 6)
        # No leader runs through the overall height's value, which reads up the
        # dimension line beside the left column.
        value = next(m for d in doc.modelspace().query("DIMENSION") for m in doc.blocks.get(d.dxf.geometry)
                     if m.dxftype() == "MTEXT" and abs(float(m.dxf.get("rotation", 0) or 0) - 90) < 1e-6)
        half = len(value.text) * 0.7 * value.dxf.char_height / 2
        x, y = value.dxf.insert.x, value.dxf.insert.y
        for _n, c, p in found:
            through = [(c[0] + (p[0] - c[0]) * t / 50, c[1] + (p[1] - c[1]) * t / 50) for t in range(51)]
            self.assertFalse([q for q in through if abs(q[0] - x) < 1.5 and abs(q[1] - y) < half],
                             "a leader runs through the height's value")
        for side in (-1, 1):
            column = sorted((c[1], p[1]) for _n, c, p in found if (c[0] - 120) * side > 0)
            self.assertEqual([p for _c, p in column], sorted(p for _c, p in column), "leaders cross")
        self.assertLessEqual(abs(sum(1 for _n, c, _p in found if c[0] < 120) - 3), 1, "columns are even")

    def test_a_vertical_dimension_value_claims_the_paper_it_reads_up(self) -> None:
        """A height's value is turned with its line. Measured unturned, its box was
        wide and short, and a balloon's leader or a note over its digits went
        unnoticed."""
        from build123d import Box

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        tall = Box(20, 20, 150)
        probe = Sheet("A3")
        probe.view(tall, "front", at=(150, 150)).overall()
        doc = _render_sheet(probe, index=1, count=1, label="probe")
        value = next(m for d in doc.modelspace().query("DIMENSION") for m in doc.blocks.get(d.dxf.geometry)
                     if m.dxftype() == "MTEXT" and m.text == "150")
        x, y = value.dxf.insert.x, value.dxf.insert.y
        # A note whose text starts just above the value's middle: on its digits,
        # clear of the box an unturned value would claim. Its model point is
        # drawn at (140, 225); a note leading left ends its text 4 short of the
        # leader's end, 1 above it.
        sheet = Sheet("A3")
        sheet.view(tall, "front", at=(150, 150)).overall().note("X", (-10, -10, 75),
                                                                  offset=(x + 5.25 - 140.0, y + 1.5 - 225.0))
        with self.assertRaisesRegex(ValueError, "'X' would print over '150'"):
            _render_sheet(sheet, index=1, count=1, label="over")

    def test_a_separate_solids_refusal_points_an_assembly_at_the_parts_list(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3")
        sheet.view(_assembly(), "front", at=(150, 150), hidden=False)
        with self.assertRaisesRegex(ValueError, r"separate solids.*assembly_sheets\(parts_list\("):
            _render_sheet(sheet, index=1, count=1, label="solids")

    def test_balloons_refuse_another_shape_a_section_or_a_detail(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        parts = parts_list(_assembly())
        sheet = Sheet("A3")
        with self.assertRaisesRegex(ValueError, "parts.assembly"):
            sheet.view(_plate(), "front", at=(150, 150)).balloons(parts)
        front = sheet.view(parts.assembly, "front", at=(150, 150))
        front.section("A")
        with self.assertRaisesRegex(ValueError, r"parts=parts"):
            front.balloons(parts)                      # cut whole: no part's cut to land in
        sheet = Sheet("A3")
        front = sheet.view(parts.assembly, "front", at=(150, 150)).balloons(parts)
        front.section("A")
        with self.assertRaisesRegex(ValueError, r"parts=parts"):
            _render_sheet(sheet, index=1, count=1, label="cut")
        detail = sheet.detail(front, (0, 0, 0), 10)
        with self.assertRaisesRegex(ValueError, "is a detail"):
            detail.balloons(parts)

    def test_the_parts_list_stands_on_the_title_block_and_reads_upward(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        parts = parts_list(_assembly())
        parts.set(1, material="6061-T6")
        sheet = Sheet("A3")
        sheet.parts_list(parts)
        msp = _render_sheet(sheet, index=1, count=1, label="list").modelspace()
        rows = {e.dxf.text: e.dxf.align_point.y for e in msp.query("TEXT[layer=='TITLE']")}
        self.assertLess(rows["DESCRIPTION"], rows["BASE"])
        self.assertLess(rows["BASE"], rows["PIN"])
        self.assertLess(rows["PIN"], rows["CORE"])
        self.assertIn("6061-T6", rows)
        self.assertLess(rows["DESCRIPTION"], 10 + 40 + 7, "the header sits on the title block")

    def test_a_part_drawn_lying_down_takes_points_in_its_own_frame(self) -> None:
        """The rod is drawn lying down; the author still gives points along its own Z."""
        from build123d import Box, Compound, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import assembly_sheets, parts_list

        rod, base = Cylinder(5, 60), Pos(0, 0, -35) * Box(30, 30, 10)
        rod.label, base.label = "rod", "base"
        sheets = assembly_sheets(parts_list(Compound(children=[rod, base])), title="ROD")
        sheet = sheets.part("rod")
        side = next(v for v in sheet.views if v.name == "front")
        side.dim((0, 5, -30), (0, 5, 30), orientation="h")
        warnings: list = []
        doc = _render_sheet(sheet, index=2, count=3, label="rod", warnings=warnings)
        self.assertFalse([w for w in warnings if "blank paper" in w], warnings)
        self.assertEqual(_dim_texts(doc).count("60"), 2, "the overall length and the author's, both along the rod")

    def test_the_parts_list_carries_spec_and_supplier(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, assembly_sheets, parts_list

        parts = parts_list(_assembly())
        parts.set("base", material="AL 6061-T6", spec="AMS 4027", supplier="ACME METALS", family="aluminium")
        self.assertEqual(parts[1].family, "aluminium")
        sheet = Sheet("A3")
        sheet.parts_list(parts)
        texts = [e.dxf.text for e in _render_sheet(sheet, index=1, count=1, label="list").modelspace()
                 .query("TEXT[layer=='TITLE']")]
        for value in ("SPEC", "SUPPLIER", "AL 6061-T6", "AMS 4027", "ACME METALS"):
            self.assertIn(value, texts)
        base = assembly_sheets(parts, title="FIXTURE").part("base")
        self.assertEqual(base._material_label(), "AL 6061-T6 PER AMS 4027", "the part's sheet joins its spec")

    def test_the_parts_list_names_each_items_detail_sheet(self) -> None:
        from cadgen._internal.drawing_assembly import _continuations
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, assembly_sheets, parts_list

        made = assembly_sheets(parts_list(_assembly()), title="FIXTURE")
        sheets = list(made)
        doc = _render_sheet(sheets[0], index=1, count=len(sheets), label="ga",
                            continued=_continuations(sheets).get(1))
        texts = [(e.dxf.insert.x, round(e.dxf.insert.y, 2), e.dxf.text)
                 for e in doc.modelspace().query("TEXT[layer=='TITLE']")]
        head = next(y for _x, y, t in texts if t == "QTY")
        column = {t: x for x, y, t in texts if y == head}
        self.assertIn("SHEET", column, "the list's header names the column")
        numbers = {y: int(t) for x, y, t in texts if abs(x - column["ITEM"]) < 0.01 and y != head}
        named = {numbers[y]: t for x, y, t in texts if abs(x - column["SHEET"]) < 0.01 and y in numbers}
        self.assertEqual(named, {item.number: str(sheets.index(made.part(item.number)) + 1)
                                 for item in made.parts if item.shape is not None})
        # A list with no detail sheets in its set has nothing to point at.
        alone = Sheet("A3")
        alone.parts_list(made.parts)
        plain = [e.dxf.text for e in _render_sheet(alone, index=1, count=1, label="list").modelspace()
                 .query("TEXT[layer=='TITLE']")]
        self.assertEqual(plain.count("SHEET"), 1, "the title block's caption only")

    def test_an_item_the_model_lacks_is_listed_as_required(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import assembly_sheets, parts_list

        parts = parts_list(_assembly())
        loctite = parts.add("LOCTITE 243", spec="MIL-S-46163 TYPE II")
        self.assertEqual((loctite.number, loctite.quantity, loctite.shape), (5, "AR", None))
        sheets = assembly_sheets(parts, title="FIXTURE")
        self.assertEqual(len(sheets), 1 + 4, "the arrangement and a sheet per modelled part")
        with self.assertRaisesRegex(KeyError, "not in the model"):
            sheets.part(5)
        facts = _facts()
        msp = _render_sheet(sheets[0], index=1, count=5, label="ga", facts=facts).modelspace()
        texts = [e.dxf.text for e in msp.query("TEXT[layer=='TITLE']")]
        self.assertIn("LOCTITE 243", texts)
        self.assertIn("AR", texts)
        self.assertFalse([line for line in _unstated(facts) if "item 5" in line])
        fresh = parts_list(_assembly())
        with self.assertRaisesRegex(ValueError, "AR"):
            fresh.add("GREASE", quantity=0)
        fresh.add("GREASE")
        with self.assertRaisesRegex(ValueError, "not in the model"):
            fresh.merge(4, 5)

    def test_the_parts_list_columns_take_the_room_their_entries_need(self) -> None:
        """Fixed widths refused MCMASTER-CARR and a forty-letter description."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        parts = parts_list(_assembly())
        parts.set(1, description="BASE PLATE, MACHINED FROM SOLID, ANODISED", supplier="MCMASTER-CARR")
        sheet = Sheet("A3")
        sheet.parts_list(parts)
        texts = [e.dxf.text for e in _render_sheet(sheet, index=1, count=1, label="wide").modelspace()
                 .query("TEXT[layer=='TITLE']")]
        self.assertIn("MCMASTER-CARR", texts)
        self.assertIn("BASE PLATE, MACHINED FROM SOLID, ANODISED", texts)

    def test_a_spec_too_long_for_its_column_is_refused(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        parts = parts_list(_assembly())
        parts.set(1, spec="AMS 4027 AND AMS-QQ-A-250/11 AND ASTM B209 TEMPER T651 OR EN 485-2 OR JIS H4000 "
                          "A6061P-T651 AS SUPPLIED UNDER THE CUSTOMER'S APPROVED SOURCE LIST")
        sheet = Sheet("A3")
        sheet.parts_list(parts)
        with self.assertRaisesRegex(ValueError, r"item 1's SPEC .* does not fit .* parts\.set\(1, spec=\.\.\.\)"):
            _render_sheet(sheet, index=1, count=1, label="long")

    def test_an_unknown_family_is_refused(self) -> None:
        from cadgen.eng_drawing import parts_list

        with self.assertRaisesRegex(ValueError, "aluminium, copper_alloy"):
            parts_list(_assembly()).set(1, family="unobtainium")

    def test_a_long_parts_list_is_refused_with_where_to_split_it(self) -> None:
        from build123d import Box, Compound, Pos

        from cadgen.eng_drawing import Sheet, parts_list

        blocks = []
        for k in range(40):
            block = Pos(0, 0, 12 * k) * Box(10, 10, 10 + k * 0.1)
            block.label = f"block_{k}"
            blocks.append(block)
        parts = parts_list(Compound(children=blocks))
        with self.assertRaisesRegex(ValueError, r"parts_list\(parts, last=\d+\).*parts_list\(parts, first=\d+\)"):
            Sheet("A4").parts_list(parts)

    def test_a_split_parts_list_says_where_it_continues(self) -> None:
        from cadgen.eng_drawing import Sheet, eng_drawing, parts_list

        parts = parts_list(_assembly())
        with temporary_directory(prefix="tmp-cad-eng-drawing-") as tmp:
            seen = {}

            @eng_drawing(out=str(Path(tmp) / "split.pdf"))
            def split():
                first, rest = Sheet("A4"), Sheet("A4")
                first.parts_list(parts, last=2)
                rest.parts_list(parts, first=3)
                return [first, rest]

            import cadgen.eng_drawing as drawing

            real = drawing._render_sheet

            def capture(sheet, **kwargs):
                doc = real(sheet, **kwargs)
                seen[kwargs["index"]] = [e.dxf.text for e in doc.modelspace().query("TEXT")]
                return doc

            from unittest import mock

            with mock.patch.object(drawing, "_render_sheet", capture):
                split()
        self.assertIn("PARTS LIST, CONTINUED ON SHEET 2", seen[1])
        self.assertIn("PARTS LIST, CONTINUED FROM SHEET 1", seen[2])

    def test_a_view_over_the_parts_list_or_a_note_under_it_is_refused(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        parts = parts_list(_assembly())
        sheet = Sheet("A3")
        sheet.parts_list(parts)
        sheet.view(_plate(), "top", at=(330, 70))
        with self.assertRaisesRegex(ValueError, "over the parts list"):
            _render_sheet(sheet, index=1, count=1, label="over")
        from cadgen._internal.drawing_base import _MARGIN, _TITLE_W
        from cadgen._internal.drawing_sheet import _notes_box

        sheet = Sheet("A4", notes=["A NOTE LONG ENOUGH TO RUN PAST THE LEFT HALF OF AN A4 SHEET AND UNDER IT"])
        sheet.parts_list(parts)
        sheet.view(_plate(), "top", at=(60, 140))
        _render_sheet(sheet, index=1, count=1, label="note")
        ((_x0, x1, _y0, _y1),) = _notes_box(sheet)
        self.assertLessEqual(x1, sheet.width - _MARGIN - _TITLE_W - 4.0, "wrapped to end before the list")
        sheet = Sheet("A4", notes=["UNBROKEN" + "X" * 70])
        sheet.parts_list(parts)
        with self.assertRaisesRegex(ValueError, "runs under the parts list"):
            _render_sheet(sheet, index=1, count=1, label="note")

    def test_assembly_sheets_draws_an_arrangement_and_a_sheet_per_part(self) -> None:
        from cadgen.eng_drawing import assembly_sheets, eng_drawing, parts_list

        parts = parts_list(_assembly())
        sheets = assembly_sheets(parts, title="FIXTURE", part_number="FX-100")
        self.assertEqual(len(sheets), 1 + len(parts))
        ga, pin = sheets[0], sheets.part("pin")
        self.assertEqual([v.name for v in ga.views], ["front", "top", "iso"])
        self.assertTrue(all(not v.hidden for v in ga.views))
        self.assertEqual((pin.title, pin.subtitle, pin.part_number), ("PIN", "ITEM 2 (QTY 2) OF FIXTURE", "FX-100"))
        base = sheets.part(1)
        # Turned to face the front, the view looking down its holes, as a turned part
        # lies down; the points an author gives its views stay in its own frame.
        self.assertEqual([v.name for v in base.views], ["front", "right", "iso"])
        self.assertAlmostEqual(base.views[0].shape.bounding_box().size.Y, 6)
        self.assertIsNotNone(base.views[0]._turn)
        with temporary_directory(prefix="tmp-cad-eng-drawing-") as tmp:
            printed: list[str] = []

            @eng_drawing(out=str(Path(tmp) / "fixture.pdf"))
            def fixture():
                return sheets

            from unittest import mock

            with mock.patch("builtins.print", side_effect=lambda line: printed.append(str(line))):
                fixture()
        self.assertFalse([line for line in printed if "separate solids" in line or "holes():" in line], printed)
        self.assertTrue(any("item 4 (CORE) has no balloon" in line for line in printed), printed)
        self.assertFalse([line for line in printed if "incomplete: sheet" in line and any(
                             words in line for words in ("not called out", "overall size", "turned diameter",
                                                         "not located along"))],
                         "a first pass states every part's overall sizes and holes, and where the holes are")

    def test_a_round_parts_sheet_has_one_side_view_and_states_its_diameters(self) -> None:
        from build123d import Align, Box, Compound, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import assembly_sheets, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        plate = Box(60, 40, 8, align=up)
        plate.label = "plate"
        pin = Pos(15, 0, 8) * (Cylinder(3, 20, align=up) + Pos(0, 0, 20) * Cylinder(5, 4, align=up))
        pin.label = "pin"
        sheets = assembly_sheets(parts_list(Compound(children=[plate, pin])), title="RIG")
        sheet = sheets.part("pin")
        names = [v.name for v in sheet.views]
        self.assertEqual(names, ["front", "right", "iso"], "one side view and the end view; no repeat")
        size = sheet.views[0].shape.bounding_box().size
        self.assertGreater(size.X, size.Z, "a long turned part is drawn lying down, its axis across the sheet")
        facts = _facts()
        doc = _render_sheet(sheet, index=1, count=1, label="pin", facts=facts)
        # The ⌀ is drawn as line work beside each value, so the text is the number.
        self.assertEqual(sorted(_dim_texts(doc)), ["10", "20", "24", "6"],
                         "two diameters, the shoulder and the length, once each")
        self.assertFalse([line for line in _unstated(facts) if "overall size" in line or "turned diameter" in line],
                         "the diameters state the sizes across the axis")

    def test_a_flat_turned_part_keeps_its_face_view(self) -> None:
        from build123d import Align, Box, Compound, Cylinder

        from cadgen.eng_drawing import assembly_sheets, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        base = Box(80, 80, 6, align=up)
        base.label = "base"
        washer = Cylinder(20, 3, align=up) - Cylinder(8, 3, align=up)
        washer.label = "washer"
        sheet = assembly_sheets(parts_list(Compound(children=[base, washer])), title="RIG").part("washer")
        self.assertEqual([v.name for v in sheet.views], ["top", "front", "iso"], "a disc stays flat: face and edge")

    def test_a_cones_widest_diameter_states_its_size_across_the_axis(self) -> None:
        from build123d import Align, Box, Compound, Cone

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import assembly_sheets, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        base = Box(80, 80, 6, align=up)
        base.label = "base"
        seat = Cone(36, 20, 12, align=up)
        seat.label = "seat"
        sheet = assembly_sheets(parts_list(Compound(children=[base, seat])), title="RIG").part("seat")
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="seat", facts=facts)
        self.assertFalse([line for line in _unstated(facts) if "overall size" in line], _unstated(facts))

    def test_on_a_drawing_of_several_parts_each_gap_names_its_sheet(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import Sheet

        facts = _facts()
        for index, (title, part) in enumerate((("SHAFT", _shaft()), ("PLATE", _plate())), start=1):
            sheet = Sheet("A3", title=title)
            sheet.three_views(part)
            _render_sheet(sheet, index=index, count=2, label="two", facts=facts)
        report = _unstated(facts)
        self.assertTrue(report)
        self.assertTrue(all(line.startswith(("incomplete: sheet 1 (SHAFT): ", "incomplete: sheet 2 (PLATE): "))
                            for line in report), report)

    def test_a_sheet_that_chose_its_scale_steps_down_rather_than_refusing(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        def bracket(sheet):
            part, point = _inclined()
            top, front, _right, _iso = sheet.three_views(part, iso=True)
            top.overall()
            top.holes()
            front.overall(width=False)
            sheet.auxiliary(front, point).holes()
            return sheet

        chosen = bracket(Sheet("A4", None))
        _render_sheet(chosen, index=1, count=1, label="fit")
        self.assertLess(chosen._scale(), 1.0, "no room for VIEW C at 1:1 on A4, so the next scale down")
        with self.assertRaisesRegex(ValueError, "no free paper"):
            _render_sheet(bracket(Sheet("A4", 1.0)), index=1, count=1, label="fixed")

    def test_balloons_spread_clear_of_each_other_and_of_text_beside_them(self) -> None:
        from cadgen._internal.drawing_assembly import spread

        self.assertEqual(spread([0, 1, 2], 10, -100, 100), [-9.0, 1.0, 11.0])
        self.assertEqual(spread([0, 1, 2], 10, 0, 100), [0, 10, 20])
        for desired, gap, avoid in (([0, 10, 20, 30], 10, [(5, 15)]), ([0, 1, 2, 26], 12, [(15, 25)]),
                                    ([40, 41, 42, 43, 44], 12, [(45, 55)])):
            placed = spread(desired, gap, 0 if gap == 12 else -100, 100, avoid=avoid)
            self.assertFalse([y for y in placed for a, b in avoid if a < y < b], placed)
            self.assertTrue(all(b - a >= gap - 1e-9 for a, b in zip(placed, placed[1:])), placed)
        # A run that cannot fit runs past the end, for the caller to refuse.
        self.assertGreater(spread([0, 1, 2], 12, 0, 20)[-1], 20)

    def test_balloons_stay_on_the_paper_clear_of_the_parts_list_or_are_refused(self) -> None:
        from build123d import Box, Compound, Pos

        from cadgen._internal.drawing_base import _MARGIN, _TITLE_H, _TITLE_W
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_sheet import _list_height
        from cadgen.eng_drawing import Sheet, parts_list

        def stack(count):
            kids = []
            for k in range(count):
                block = Pos(-20 + (k % 2) * 40, 0, 6 * k) * Box(6 + 0.1 * k, 6, 3)
                block.label = f"block_{k}"
                kids.append(block)
            return parts_list(Compound(children=kids))

        parts = stack(16)
        sheet = Sheet("A3", scale=0.5)  # the view is shorter than its balloon columns
        sheet.parts_list(parts)
        sheet.view(parts.assembly, "front", at=(150, 250), hidden=False).balloons(parts)
        found = _balloons(_render_sheet(sheet, index=1, count=1, label="off"))
        self.assertEqual(len(found), 16)
        table = (sheet.width - _MARGIN - _TITLE_W, _MARGIN + _TITLE_H + _list_height(sheet))
        for _n, c, _p in found:
            self.assertTrue(_MARGIN + 5 <= c[1] <= sheet.height - _MARGIN - 5, c)
            self.assertFalse(c[0] + 5 > table[0] and c[1] - 5 < table[1], "a balloon on the parts list")
        crowd = stack(40)
        crowded = Sheet("A4", scale=0.5)
        crowded.view(crowd.assembly, "front", at=(100, 140), hidden=False).balloons(crowd)
        with self.assertRaisesRegex(ValueError, "do not fit"):
            _render_sheet(crowded, index=1, count=1, label="crowded")

    def test_leaders_neither_cross_nor_run_through_a_value(self) -> None:
        from build123d import Box, Compound, Pos
        from shapely.geometry import LineString

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        post = Pos(100, 0, 150) * Box(10, 10, 300)
        post.label = "post"
        kids = [post]
        for name, x, z in (("near", -100, 150.0), ("far", -30, 150.1), ("b", -90, 150.2), ("c", -80, 150.3)):
            block = Pos(x, 0, z) * Box(8, 8, 8)
            block.label = name
            kids.append(block)
        parts = parts_list(Compound(children=kids))
        sheet = Sheet("A3", scale=0.5)
        sheet.parts_list(parts)
        sheet.view(parts.assembly, "front", at=(120, 170), hidden=False).overall().balloons(parts)
        doc = _render_sheet(sheet, index=1, count=1, label="cross")
        leaders = [LineString([c, p]) for _n, c, p in _balloons(doc)]
        self.assertFalse([(a, b) for i, a in enumerate(leaders) for b in leaders[i + 1:] if a.crosses(b)])
        value = next(m for d in doc.modelspace().query("DIMENSION") for m in doc.blocks.get(d.dxf.geometry)
                     if m.dxftype() == "MTEXT" and abs(float(m.dxf.get("rotation", 0) or 0) - 90) < 1e-6)
        x, y, half = value.dxf.insert.x, value.dxf.insert.y, len(value.text) * 0.7 * value.dxf.char_height / 2
        from shapely.geometry import box

        self.assertFalse([path for path in leaders if path.intersects(box(x - 1.75, y - half, x + 1.75, y + half))])

    def test_a_part_showing_a_narrow_band_is_still_ballooned(self) -> None:
        from build123d import Align, Compound, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        rod = Cylinder(4, 100, align=up)
        rod.label = "rod"
        body = Cylinder(12, 82, align=up) - Cylinder(4, 82, align=up)
        body.label = "body"
        eye = Pos(0, 0, 100) * Cylinder(10, 20, align=up)
        eye.label = "eye"
        parts = parts_list(Compound(children=[body, rod, eye]))
        sheet = Sheet("A3")
        sheet.parts_list(parts)
        sheet.view(parts.assembly, "front", at=(120, 170), hidden=False).balloons(parts)
        self.assertEqual(sorted(n for n, _c, _p in _balloons(_render_sheet(sheet, index=1, count=1, label="rod"))),
                         [1, 2, 3], "18 mm of the rod shows between the body and the eye")

    def test_balloons_stand_outside_the_hole_callouts(self) -> None:
        from build123d import Box, Compound, Cylinder, Pos, Rot
        from shapely.geometry import LineString, Point

        from cadgen._internal.drawing_assembly import _BALLOON_R
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        plate = Box(40, 10, 150) - Pos(-10, 0, 40) * Rot(90, 0, 0) * Cylinder(4, 10)
        plate.label = "plate"
        block = Pos(0, 0, 85) * Box(20, 20, 20)
        block.label = "block"
        lug = Pos(-25, 0, 44) * Box(6, 6, 6)
        lug.label = "lug"
        parts = parts_list(Compound(children=[plate, block, lug]))
        sheet = Sheet("A3")
        sheet.parts_list(parts)
        front = sheet.view(parts.assembly, "front", at=(140, 170), hidden=False)
        front.hole((-10, -5, 40))
        front.balloons(parts)
        doc = _render_sheet(sheet, index=1, count=1, label="callout")
        callouts = [LineString([(v[0], v[1]) for v in e.vertices]) for e in doc.modelspace().query("LEADER[layer=='DIM']")]
        for _n, c, _p in _balloons(doc):
            self.assertTrue(all(path.distance(Point(c)) > _BALLOON_R for path in callouts))

    def test_the_general_arrangement_refuses_paper_too_small_for_it(self) -> None:
        from build123d import Box, Compound, Pos

        from cadgen.eng_drawing import assembly_sheets, parts_list

        post = Box(20, 20, 120)
        post.label = "post"
        cap = Pos(0, 0, 65) * Box(30, 30, 10)
        cap.label = "cap"
        with self.assertRaisesRegex(ValueError, "larger size="):
            assembly_sheets(parts_list(Compound(children=[post, cap])), title="POST", size="A4")

    def test_a_value_too_long_for_its_column_is_refused_not_cut(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        parts = parts_list(_assembly()).set(1, part_number="MSA-100-0042-REV-C-ALT-STEEL-OPTION-77-" * 4)
        sheet = Sheet("A3")
        sheet.parts_list(parts)
        with self.assertRaisesRegex(ValueError, r"parts.set\(1, part_number=\.\.\.\)"):
            _render_sheet(sheet, index=1, count=1, label="long")

    def test_runs_of_one_list_may_not_overlap_or_climb_into_the_revisions(self) -> None:
        from cadgen._internal.drawing_assembly import _continuations
        from cadgen.eng_drawing import Sheet, parts_list

        parts = parts_list(_assembly())
        first, second = Sheet("A3"), Sheet("A3")
        first.parts_list(parts, last=3)
        second.parts_list(parts, first=2)
        with self.assertRaisesRegex(ValueError, "items 2 to 3"):
            _continuations([first, second])
        from build123d import Box, Compound, Pos

        many = []
        for k in range(18):
            block = Pos(12 * k, 0, 0) * Box(10, 10, 10 + k * 0.1)
            block.label = f"block_{k}"
            many.append(block)
        crowded = Sheet("A4", revisions=[("A", "", "ONE"), ("B", "", "TWO"), ("C", "", "THREE"), ("D", "", "FOUR")])
        with self.assertRaisesRegex(ValueError, "Draw items 1 to"):
            crowded.parts_list(parts_list(Compound(children=many)))

    def test_part_sheets_follow_the_list_and_keep_a_scale_the_author_sets(self) -> None:
        from build123d import Box, Compound, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import assembly_sheets, parts_list

        plate, block = Box(60, 40, 10), Pos(100, 0, 0) * Box(10, 10, 10)
        plate.label, block.label = "plate", "block"
        parts = parts_list(Compound(children=[plate, block]))
        sheets = assembly_sheets(parts, title="T")
        parts.set("plate", description="BASE PLATE", material="6061-T6")
        texts = {e.dxf.text for e in _render_sheet(sheets.part(1), index=2, count=3, label="t")
                 .modelspace().query("TEXT[layer=='TITLE']")}
        self.assertTrue({"BASE PLATE", "6061-T6"} <= texts, "the part's sheet reads the list when it renders")
        with self.assertRaisesRegex(ValueError, "merge before"):
            parts.merge(1, 2)
        sheet = sheets.part("block")
        sheet.scale = 2.0
        _render_sheet(sheet, index=3, count=3, label="t")
        self.assertEqual(sheet.scale, 2.0, "a scale the author set is theirs")
        plate_sheet = sheets.part("plate")
        plate_sheet.material = "AL 6061-T6"
        _render_sheet(plate_sheet, index=2, count=3, label="t")
        self.assertEqual(plate_sheet.material, "AL 6061-T6", "a material the author set on the sheet is theirs")


def _perforated():
    """A plate with three kinds of hole and a slot, for a hole table."""
    from build123d import Align, Box, Cylinder, Pos, SlotCenterToCenter, extrude

    up = (Align.CENTER, Align.CENTER, Align.MIN)
    plate = Box(160, 100, 8, align=up)
    for x in (-60, -30, 0, 30, 60):
        for y in (-35, 35):
            plate -= Pos(x, y, 0) * Cylinder(3, 8, align=up)
    for x in (-60, 60):
        plate -= Pos(x, 0, 0) * Cylinder(5, 8, align=up)
    plate -= Cylinder(12, 8, align=up)
    plate -= Pos(30, 0, 0) * extrude(SlotCenterToCenter(16, 8), 8)
    return plate


def _inclined():
    """A base plate with a tab leaning 30 degrees, a hole square through the tab;
    and a point on the tab's inner face."""
    from build123d import Align, Box, Cylinder, Location, Pos, Rot

    up = (Align.CENTER, Align.CENTER, Align.MIN)
    base = Box(80, 50, 8, align=up) - Pos(-25, 0, 0) * Cylinder(4, 8, align=up)
    tab = Box(8, 50, 40, align=(Align.MAX, Align.CENTER, Align.MIN)) - Pos(-4, 0, 25) * Rot(0, 90, 0) * Cylinder(5, 8)
    return (base + Location((40, 0, 0), (0, 1, 0), 30) * tab).clean(), (44.164, 0, 23.212)




def _clevis():
    """A clevis on a base plate: two ears with a pin bore, four mounting holes
    and two slots."""
    from build123d import Align, Axis, Box, Cylinder, Pos, Rot, SlotCenterToCenter, extrude, fillet

    up = (Align.CENTER, Align.CENTER, Align.MIN)
    part = fillet(Box(100, 64, 8, align=up).edges().filter_by(Axis.Z), 4)
    for sign in (-1, 1):
        y = sign * 16
        part += Pos(0, y, 8) * Box(30, 8, 28, align=up) + Pos(0, y, 36) * Rot(90, 0, 0) * Cylinder(15, 8)
    part -= Pos(0, 0, 36) * Rot(90, 0, 0) * Cylinder(6, 40)
    for x, y in ((-40, -24), (-40, 24), (40, -24), (40, 24)):
        part -= Pos(x, y, 0) * Cylinder(3.3, 8, align=up)
    for x in (-32, 32):
        part -= Pos(x, 0, 0) * Rot(0, 0, 90) * extrude(SlotCenterToCenter(18, 12), 8)
    return part.clean()


def _dimension_lines(doc) -> list:
    """Each DIMENSION's dimension line, as shapely lines: in its block, the lines
    that run the way the dimension measures (its extension lines run across)."""
    from shapely.geometry import LineString

    found = []
    for dim in doc.modelspace().query("DIMENSION"):
        horizontal = abs(math.sin(math.radians(dim.dxf.get("angle", 0.0)))) < 0.5
        for e in doc.blocks.get(dim.dxf.geometry):
            if e.dxftype() != "LINE":
                continue
            a, b = e.dxf.start, e.dxf.end
            if (abs(b.y - a.y) < 1e-6) == horizontal and math.hypot(b.x - a.x, b.y - a.y) > 1e-6:
                found.append(LineString([(a.x, a.y), (b.x, b.y)]))
    return found

def _bar():
    """A 600 mm bar, 20 mm square, with a turned spigot on its end and a cross hole
    near each end. Square, not round: hidden-line removal on a round bar's cross
    holes takes seconds a view, and the break does not care."""
    from build123d import Align, Box, Cylinder, Pos, Rot

    bar = Box(600, 20, 20, align=(Align.MIN, Align.CENTER, Align.CENTER))
    bar += Pos(600, 0, 0) * Rot(0, 90, 0) * Cylinder(6, 30, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for x in (20, 580):
        bar -= Pos(x, 0, 0) * Cylinder(3, 40)
    return bar


class ChosenSheetTests(unittest.TestCase):
    """Sheet(size=None, scale=None): the sheet picks its paper and scale."""

    def test_the_smallest_sheet_at_full_size_else_a3_reduced(self) -> None:
        from build123d import Box, Cylinder

        from cadgen.eng_drawing import Sheet

        for part, size, at_least in ((Cylinder(7, 11), "A4", 1.0), (Box(600, 40, 40), "A3", 0.0),
                                     (Box(1500, 800, 300), "A3", 0.0)):
            sheet = Sheet(None, None)
            sheet.three_views(part, iso=True)
            self.assertEqual(sheet._size(), size)
            self.assertGreaterEqual(sheet._scale(), at_least)
        fixed = Sheet("A3", None)
        fixed.three_views(Cylinder(7, 11), iso=True)
        self.assertEqual(fixed._scale(), 5.0, "a given size takes the largest scale that fits it")
        full = Sheet(None, 1.0)
        full.three_views(Box(600, 40, 40), iso=True)
        self.assertEqual(full._size(), "A1", "a given scale takes the smallest sheet that fits it")

    def test_a_hand_placed_view_needs_a_known_sheet(self) -> None:
        from cadgen.eng_drawing import Sheet

        with self.assertRaisesRegex(ValueError, "three_views"):
            Sheet(None, None).view(_plate(), "top", at=(100, 100))

    def test_running_out_of_paper_tries_a_larger_sheet_before_a_smaller_scale(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        part, point = _inclined()
        sheet = Sheet(None, None)
        top, front, _right, _iso = sheet.three_views(part, iso=True)
        top.overall()
        top.holes()
        front.overall(width=False)
        sheet.auxiliary(front, point).holes()
        _render_sheet(sheet, index=1, count=1, label="chosen")
        self.assertEqual((sheet._size(), sheet._scale()), ("A3", 1.0), "A4 has no room left for VIEW C at 1:1")

    def test_a_chosen_size_grows_for_paper_a_fixed_scale_needs(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        part, point = _inclined()
        sheet = Sheet(None, 1.0)
        top, front, _right, _iso = sheet.three_views(part, iso=True)
        top.overall()
        top.holes()
        front.overall(width=False)
        sheet.auxiliary(front, point).holes()
        _render_sheet(sheet, index=1, count=1, label="size")
        self.assertEqual((sheet._size(), sheet._scale()), ("A3", 1.0))

    def test_two_arrangements_on_a_chosen_sheet_settle_rather_than_loop(self) -> None:
        from build123d import Box

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet(None, None)
        sheet.three_views(Box(20, 20, 20))
        sheet.three_views(Box(300, 200, 100))
        try:
            _render_sheet(sheet, index=1, count=1, label="two")
        except ValueError as refused:
            self.assertIn("off the frame", str(refused))

    def test_a_value_the_author_sets_is_kept_even_when_it_matches_the_choice(self) -> None:
        from build123d import Cylinder

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet(None, None)
        sheet.three_views(Cylinder(7, 11), iso=True)
        sheet.size, sheet.scale = "A3", 1.0
        _render_sheet(sheet, index=1, count=1, label="pinned")
        self.assertEqual((sheet._size(), sheet._scale()), ("A3", 1.0))




class WhiteSpaceTests(unittest.TestCase):
    def test_an_enlarged_sheet_out_of_paper_draws_smaller_before_taking_a_bigger_sheet(self) -> None:
        """A small part drawn enlarged that runs out of paper is drawn at the next
        scale down on its own sheet, down to 1:1, not at the same scale on a sheet
        twice the size that it then leaves mostly empty."""
        from unittest import mock

        from build123d import Align, Box, Cylinder, Pos

        import cadgen._internal.drawing_render as render
        from cadgen._internal.drawing_sheet import _OffFrame
        from cadgen.eng_drawing import Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        block = Box(24, 16, 6, align=up) - Pos(-7, 0, 0) * Cylinder(2, 6, align=up) - Pos(7, 0, 0) * Cylinder(2, 6, align=up)
        sheet = Sheet(size=None, scale=None)
        top, _front, _right = sheet.three_views(block)
        top.hole_table()
        real = render._place_hole_tables

        def tables(sheet, *args):
            if sheet._scale() > 1:
                raise _OffFrame("no room for the table", None)
            return real(sheet, *args)

        with mock.patch.object(render, "_place_hole_tables", tables):
            render._render_sheet(sheet, index=1, count=1, label="small")
        self.assertEqual((sheet._size(), sheet._scale()), ("A4", 1.0))


class CrossingTests(unittest.TestCase):
    """A reviewing engineer: dimension lines crossing other dimension lines are not acceptable."""

    def test_no_leader_or_dimension_line_crosses_a_dimension_line(self) -> None:
        from shapely.geometry import LineString

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A2", 2.0)
        top, front, right = sheet.three_views(_clevis())
        top.overall()
        top.radius((-46, 28, 8), size=4, angle=135)
        front.overall(width=False)
        front.holes()
        front.dim((-50, -32, 0), (-50, -32, 8))
        front.dim((15, -24, 0), (15, -24, 36))
        front.radius((0, -24, 36), size=15, angle=135)
        doc = _render_sheet(sheet, index=1, count=1, label="crossing", warnings=[])
        lines = _dimension_lines(doc)
        leaders = [LineString([(v[0], v[1]) for v in e.vertices]) for e in doc.modelspace().query("LEADER")]
        crossing = [(i, j) for i, a in enumerate(lines) for j, b in enumerate(lines) if i < j and a.crosses(b)]
        self.assertFalse(crossing, "two dimension lines cross")
        crossing = [(i, j) for i, a in enumerate(leaders) for j, b in enumerate(lines) if a.crosses(b)]
        self.assertFalse(crossing, "a leader crosses a dimension line")
        crossing = [(i, j) for i, a in enumerate(leaders) for j, b in enumerate(leaders) if i < j and a.crosses(b)]
        self.assertFalse(crossing, "two leaders cross")


class DimensionKindTests(unittest.TestCase):
    """Toleranced, basic and reference dimensions each mean what Y14.5 says."""

    def _block_sheet(self):
        from build123d import Align, Box

        from cadgen.eng_drawing import GENERIC, Sheet

        sheet = Sheet("A3", 1.0, profile=GENERIC)
        top, front, right = sheet.three_views(Box(40, 30, 10, align=(Align.CENTER, Align.CENTER, Align.MIN)))
        return sheet, top, front

    def test_a_reference_dimension_prints_in_parentheses_and_states_nothing(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated

        sheet, top, front = self._block_sheet()
        top.dim((-20, -15, 10), (20, -15, 10), reference=True)
        facts = _facts()
        doc = _render_sheet(sheet, index=1, count=1, label="ref", facts=facts)
        self.assertIn("(40)", _dim_texts(doc))
        self.assertTrue(any("overall size along X (40)" in line for line in _unstated(facts)),
                        "a reference dimension is information, not the requirement")

    def test_a_basic_dimensions_value_is_boxed(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet

        from cadgen.eng_drawing import Frame

        sheet, top, front = self._block_sheet()
        top.dim((-20, -15, 10), (20, -15, 10), basic=True)
        top.frame((0, 10, 10), Frame("flatness", 0.05))     # what bounds it
        doc = _render_sheet(sheet, index=1, count=1, label="basic", warnings=[])
        (dim,) = doc.modelspace().query("DIMENSION")
        self.assertLess(dim.override().get("dimgap"), 0, "the DXF says basic too")
        block = list(doc.blocks.get(dim.dxf.geometry))
        (value,) = [e for e in block if e.dxftype() == "MTEXT"]
        frames = [e for e in block if e.dxftype() == "LWPOLYLINE" and e.closed]
        self.assertEqual(len(frames), 1)
        xs, ys = zip(*[(p[0], p[1]) for p in frames[0].get_points()])
        self.assertTrue(min(xs) < value.dxf.insert.x < max(xs) and min(ys) < value.dxf.insert.y < max(ys))

    def test_limits_print_the_two_limits_the_part_lies_between(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet

        sheet, top, front = self._block_sheet()
        top.dim((-20, -15, 10), (20, -15, 10), limits=(39.98, 40.02))
        doc = _render_sheet(sheet, index=1, count=1, label="limits")
        (dim,) = doc.modelspace().query("DIMENSION")
        self.assertIn("\\S40.02^ 39.98;", dim.dxf.text, "the two limits, stacked where the value prints")
        text = " ".join(_dim_texts(doc))
        self.assertIn("40.02", text)
        self.assertIn("39.98", text)
        sheet, top, front = self._block_sheet()
        top.dim((-20, -15, 10), (20, -15, 10), limits=(40.1, 40.2))
        with self.assertRaisesRegex(ValueError, "measures 40"):
            _render_sheet(sheet, index=1, count=1, label="outside")

    @staticmethod
    def _ink(doc, dimension, x0: float, x1: float):
        """What ``dimension`` draws between sheet x0 and x1, as the PDF's renderer
        lays it out: the bounding boxes of its glyphs (and any line work) there."""
        from ezdxf.addons.drawing import Frontend, RenderContext, config
        from ezdxf.addons.drawing.recorder import Recorder

        recorder = Recorder()
        context = RenderContext(doc)
        context.set_current_layout(doc.modelspace())
        Frontend(context, recorder, config=config.Configuration()).draw_entities([dimension])
        boxes = []
        for record, _properties in recorder.player().recordings():
            box = record.bbox()
            if box.has_data and box.extmin.x > x0 and box.extmax.x < x1:
                boxes.append((box.extmin.x, box.extmin.y, box.extmax.x, box.extmax.y))
        return boxes

    @staticmethod
    def _line_y(doc, dimension) -> float:
        """The height of a horizontal dimension's dimension line."""
        lines = [e for e in doc.blocks.get(dimension.dxf.geometry) if e.dxftype() == "LINE"
                 and abs(e.dxf.start.y - e.dxf.end.y) < 1e-9]
        return lines[0].dxf.start.y

    def test_a_stacked_value_stands_clear_of_its_dimension_line(self) -> None:
        """Two limits, or unequal deviations, print one over the other about the
        middle a one-line value has: the lower half ran through the line."""
        from cadgen._internal.drawing_render import _render_sheet

        for kind in ({"limits": (39.98, 40.02)}, {"tol": (0.05, 0.02)}, {}):
            with self.subTest(**kind):
                sheet, top, front = self._block_sheet()
                top.dim((-20, -15, 10), (20, -15, 10), **kind)
                doc = _render_sheet(sheet, index=1, count=1, label="stack", warnings=[])
                (dim,) = doc.modelspace().query("DIMENSION")
                line, (x, _y) = self._line_y(doc, dim), top.at
                glyphs = self._ink(doc, dim, x - 15, x + 15)
                self.assertTrue(glyphs)
                self.assertGreater(min(g[1] for g in glyphs), line + 1.0, "no glyph on the line")

    def test_limits_keep_the_values_prefix(self) -> None:
        """⌀ before a bore's limits: without it, ⌀12.000-12.025 read as a width."""
        from cadgen._internal.drawing_render import _render_sheet

        sheet, top, front = self._block_sheet()
        top.dim((-20, -15, 10), (20, -15, 10), text="%%c<> THRU", limits=(39.98, 40.02))
        doc = _render_sheet(sheet, index=1, count=1, label="prefix", warnings=[])
        (dim,) = doc.modelspace().query("DIMENSION")
        self.assertEqual(dim.dxf.text, "%%c{\\H0.70x;\\S40.02^ 39.98;} THRU")
        block = list(doc.blocks.get(dim.dxf.geometry))
        (value,) = [e for e in block if e.dxftype() == "MTEXT"]
        (symbol,) = [e for e in block if e.dxftype() == "CIRCLE"]
        self.assertLess(symbol.dxf.center.x, value.dxf.insert.x, "the ⌀ drawn before the limits")
        self.assertAlmostEqual(symbol.dxf.center.y, value.dxf.insert.y, places=6, msg="and centred on their stack")

    def test_a_key_mark_after_limits_clears_the_extension_lines(self) -> None:
        """The stack's width was not counted, and the mark's never was: a short
        dimension kept its limits centred and its mark sat on the extension line."""
        from cadgen._internal.drawing_render import _render_sheet

        for start, limits in ((-10, (9.98, 10.02)), (-6, (13.98, 14.02))):
            with self.subTest(span=start + 20):
                sheet, top, front = self._block_sheet()
                top.dim((-20, -15, 10), (start, -15, 10), text="%%c<>", limits=limits, key=True)
                doc = _render_sheet(sheet, index=1, count=1, label="keyed", warnings=[])
                (dim,) = doc.modelspace().query("DIMENSION")
                (mark,) = [e for e in doc.modelspace().query("LWPOLYLINE[layer=='DIM']") if e.closed]
                xs = [p[0] for p in mark.get_points()]
                arrow = sheet.text_height * 0.85
                extensions = sorted({e.dxf.start.x for e in doc.blocks.get(dim.dxf.geometry) if e.dxftype() == "LINE"
                                     and abs(e.dxf.start.x - e.dxf.end.x) < 1e-9})
                far = top.at[0] + start * sheet.scale
                self.assertAlmostEqual(extensions[-1], far, places=6)
                self.assertGreater(min(xs), far + arrow, "the mark beyond the far extension line and its arrow")
                glyphs = self._ink(doc, dim, far + 0.1, min(xs))
                self.assertTrue(glyphs, "the value set beside, between the arrow and the mark")

    def test_kinds_that_cannot_combine_are_refused(self) -> None:
        sheet, top, front = self._block_sheet()
        a, b = (-20, -15, 10), (20, -15, 10)
        for kinds, words in (({"basic": True, "tol": 0.1}, "basic"), ({"reference": True, "fit": "H7"}, "reference"),
                             ({"basic": True, "reference": True}, "basic"), ({"limits": (39, 41), "tol": 0.1}, "limits"),
                             ({"limits": (41, 39)}, "limits")):
            with self.assertRaisesRegex(ValueError, words):
                top.dim(a, b, **kinds)
        with self.assertRaisesRegex(ValueError, "basic"):
            top.diameter((0, 0, 10), basic=True, reference=True)

    def test_round_callouts_and_overall_sizes_take_the_kinds_too(self) -> None:
        from build123d import Align, Box, Cylinder

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import GENERIC, Frame, Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        sheet = Sheet("A3", 1.0, profile=GENERIC)
        top, front, right = sheet.three_views(Box(60, 40, 10, align=up) - Cylinder(8, 10, align=up))
        top.diameter((0, 0, 10), reference=True)
        front.overall(reference=True)
        top.angle((-30, -20, 10), (30, -20, 10), (-30, 20, 10), basic=True)
        top.frame((20, 10, 10), Frame("flatness", 0.05))    # what bounds it
        doc = _render_sheet(sheet, index=1, count=1, label="kinds", warnings=[])
        self.assertIn("(%%c16)", _callouts(doc))
        self.assertTrue({"(60)", "(10)"} <= set(_dim_texts(doc)), _dim_texts(doc))
        (angle,) = [d for d in doc.modelspace().query("DIMENSION") if d.dxf.dimtype & 0x0F == 5]  # 3-point angular
        self.assertTrue([e for e in doc.blocks.get(angle.dxf.geometry) if e.dxftype() == "LWPOLYLINE" and e.closed],
                        "a basic angle is boxed too")

    def test_a_stated_tolerance_prints_exactly_as_given(self) -> None:
        """Rounded, 0.005 printed 0.01: a tolerance nobody gave."""
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Frame

        sheet, top, front = self._block_sheet()
        top.dim((-20, -15, 10), (20, -15, 10), tol=0.005)
        front.dim((-20, 0, 0), (20, 0, 0), limits=(39.985, 40.015))
        top.frame((0, 10, 10), Frame("flatness", 0.0125))
        doc = _render_sheet(sheet, index=1, count=1, label="exact", warnings=[])
        values = " ".join(_dim_texts(doc))
        self.assertIn("0.005", values)
        self.assertIn("40.015", values)
        self.assertIn("39.985", values)
        self.assertIn("0.0125", [e.dxf.text for e in doc.modelspace().query("TEXT[layer=='DIM']")])
        from cadgen._internal.drawing_annotation import _tol_suffix

        self.assertEqual(_tol_suffix((0.005, 0.0025)), " +0.0050/-0.0025", "a hole callout's, both to one precision")
        with self.assertRaisesRegex(ValueError, "4 decimal places"):
            Frame("flatness", 0.00001)
        with self.assertRaisesRegex(ValueError, "4 decimal places"):
            top.dim((-20, -15, 10), (20, -15, 10), tol=0.000125)
        with self.assertRaisesRegex(ValueError, "4 decimal places"):
            front.dim((-20, 0, 0), (20, 0, 0), limits=(39.99995, 40.0))

    def test_a_basic_dimension_without_a_frame_is_refused(self) -> None:
        # It is exact by definition: with no frame to bound it, it prints a size nobody can make.
        from cadgen._internal.drawing_render import _render_sheet

        sheet, top, front = self._block_sheet()
        top.dim((-20, -15, 10), (20, -15, 10), basic=True)
        with self.assertRaisesRegex(ValueError, r"top dim 0: a basic dimension, and no GD&T frame on the sheet"):
            _render_sheet(sheet, index=1, count=1, label="lonely")

    def test_a_fit_is_an_iso_286_class_and_the_whole_tolerance(self) -> None:
        # fit= printed whatever it was given after the size ("80 banana"), and beside tol= it printed two tolerances.
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet, top, front = self._block_sheet()
        a, b = (-20, -15, 10), (20, -15, 10)
        for fit in ("banana", "H", "7", "H19", "I7", "h7/H7", "H7/G6", "H7/g6/f7", "Hh7"):
            with self.subTest(fit=fit), self.assertRaisesRegex(ValueError, "not an ISO 286-1 tolerance class or fit"):
                top.dim(a, b, fit=fit)
        with self.assertRaisesRegex(TypeError, "fit= takes"):
            top.dim(a, b, fit=7)
        for kinds in ({"fit": "H7", "tol": 0.1}, {"fit": "g6", "limits": (39.9, 40.0)}):
            with self.subTest(kinds=kinds), self.assertRaisesRegex(ValueError, r"is the size's tolerance.*not both"):
                top.dim(a, b, **kinds)
        for fit in ("H7", "g6", "JS9", "js6", "CD10", "zc11", "h01", "H7/g6", "H7/k6"):
            top.dim(a, b, fit=fit)
        plate = Sheet("A4").view(_drilled([(0, 0)]), "top", at=(100, 150))
        with self.assertRaisesRegex(ValueError, r"hole\(\) takes fit='H7' or tol=, not both"):
            plate.hole((0, 0, 20), fit="H7", tol=0.1)
        with self.assertRaisesRegex(ValueError, r"fit='g6' is a shaft's tolerance class .*\(G6\)"):
            plate.hole((0, 0, 20), fit="g6")
        plate.hole((0, 0, 20), fit="H7/g6")
        self.assertEqual(_callouts(_render_sheet(plate.sheet, index=1, count=1, label="fit")), ["%%c5 H7/g6 THRU"])


class GdtTests(unittest.TestCase):
    """Feature control frames and datum feature symbols, every value the person's."""

    def _plate(self):
        from build123d import Align, Box, Cylinder, Pos

        from cadgen.eng_drawing import GENERIC, Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(80, 50, 10, align=up) - Pos(20, 0, 0) * Cylinder(5, 10, align=up)
        sheet = Sheet("A3", 1.0, profile=GENERIC)
        top, front, right = sheet.three_views(part)
        return sheet, top, front, right

    def test_a_frame_its_sheets_standard_dropped_is_refused(self) -> None:
        # Y14.5-2018 has no concentricity or symmetry; ISO 1101, which GENERIC reads by, has both.
        from build123d import Align, Box, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import GENERIC, Frame, Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(80, 50, 10, align=up) - Pos(20, 0, 0) * Cylinder(5, 10, align=up)
        for profile in (_aero(), GENERIC):
            sheet = Sheet("A3", 1.0, profile=profile)
            top, front, _right = sheet.three_views(part)
            front.datum("A", (0, -25, 5))
            top.frame((0, 25, 10), Frame("symmetry", 0.1, ("A",)))
            if profile is GENERIC:
                _render_sheet(sheet, index=1, count=1, label="iso")
                continue
            with self.assertRaisesRegex(ValueError, r"top frame 0: ASME Y14.5-2018, the standard its profile AERO "
                                                    r"reads the drawing by, has no symmetry; state position, or "
                                                    r"surface_profile instead"):
                _render_sheet(sheet, index=1, count=1, label="y14")

    def test_a_frame_on_a_sheet_that_names_no_standard_is_refused(self) -> None:
        # ISO GPS and Y14.5 read one frame differently (Rule #1): it printed under neither name, read as ISO.
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Frame, Sheet

        part = self._plate()[1].shape
        sheet = Sheet("A3", 1.0)
        top, front, _right = sheet.three_views(part)
        front.datum("A", (0, -25, 0))
        top.hole((20, 0, 10), frame=Frame("position", 0.1, ("A",), diameter=True))
        with self.assertRaisesRegex(ValueError, r"sheet 1 \(UNTITLED\), top hole 0: a GD&T frame is read by ISO GPS "
                                                r"or ASME Y14.5-2018.*the sheet names neither; give it profile=GENERIC"):
            _render_sheet(sheet, index=1, count=1, label="unnamed")
        general = Sheet("A3", 1.0, general_profile=Frame("surface_profile", 0.2))
        general.view(part, "top", at=(150, 150))
        with self.assertRaisesRegex(ValueError, "the general profile: a GD&T frame"):
            _render_sheet(general, index=1, count=1, label="general")
        # Named, the standard prints as a note of the sheet.
        named = self._plate()
        named[2].datum("A", (0, -25, 0))
        named[1].hole((20, 0, 10), frame=Frame("position", 0.1, ("A",), diameter=True))
        notes = [e.dxf.text for e in _render_sheet(named[0], index=1, count=1, label="named").modelspace()
                 .query("TEXT[layer=='NOTES']")]
        self.assertTrue(any("TOLERANCING ISO 8015." in n for n in notes), notes)

    def test_frame_vocabulary_is_closed_and_follows_y14_5(self) -> None:
        from cadgen.eng_drawing import Frame

        for args, kwargs, words in ((("roundness", 0.1), {}, "unknown characteristic"),
                                    (("flatness", 0.1, ("A",)), {}, "names no datum"),
                                    (("perpendicularity", 0.1), {}, "measured from a datum"),
                                    (("flatness", 0.1), {"diameter": True}, "not a diameter"),
                                    (("flatness", 0.1), {"modifier": "M"}, "no material condition"),
                                    (("position", 0.1, ("A",)), {"modifier": "X"}, "modifier"),
                                    (("position", 0.0, ("A",)), {}, "positive"),
                                    (("position", 0.1, ("A", "I")), {}, "letters"),
                                    (("position", 0.1, ("A", "A")), {}, "letters")):
            with self.assertRaisesRegex(ValueError, words):
                Frame(*args, **kwargs)
        frame = Frame("position", 0.1, ("a", "b"), diameter=True, modifier="M")
        self.assertEqual(frame.datums, ("A", "B"))

    def test_a_hole_carries_its_position_frame(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Frame

        sheet, top, front, right = self._plate()
        front.datum("A", (0, -25, 0))
        top.datum("B", (-40, 0, 10))
        top.hole((20, 0, 10), frame=Frame("position", 0.1, ("A", "B"), diameter=True, modifier="M"))
        doc = _render_sheet(sheet, index=1, count=1, label="frame", warnings=[])
        texts = [e.dxf.text for e in doc.modelspace().query("TEXT[layer=='DIM']")]
        for value in ("0.1", "M", "A", "B"):
            self.assertIn(value, texts)
        frames = [e for e in doc.modelspace().query("LWPOLYLINE[layer=='DIM']") if e.closed and len(e) == 4]
        self.assertGreaterEqual(len(frames), 3, "the frame and the two datum squares")
        self.assertTrue(doc.modelspace().query("HATCH[layer=='DIM']"), "each datum's filled triangle")

    def test_a_frame_naming_an_undefined_datum_is_refused(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Frame

        sheet, top, front, right = self._plate()
        front.datum("A", (0, -25, 0))
        top.hole((20, 0, 10), frame=Frame("position", 0.1, ("A", "C"), diameter=True))
        with self.assertRaisesRegex(ValueError, "datum C"):
            _render_sheet(sheet, index=1, count=1, label="undefined")

    def test_a_datum_counts_on_its_own_sheet_only_and_the_refusal_names_the_sheet(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import GENERIC, Frame, Sheet

        sheet, top, front, right = self._plate()
        detail = sheet.detail(front, (0, -25, 0), 8)
        detail.datum("A", (0, -25, 0))                   # defined in a detail of the sheet
        top.hole((20, 0, 10), frame=Frame("position", 0.1, ("A",), diameter=True))
        _render_sheet(sheet, index=1, count=2, label="first", warnings=[])
        second = Sheet("A3", 1.0, title="SECOND", profile=GENERIC)
        other = second.three_views(self._plate()[1].shape)[0]
        other.hole((20, 0, 10), frame=Frame("position", 0.1, ("A",), diameter=True))
        with self.assertRaisesRegex(ValueError, r"sheet 2 \(SECOND\).*datum A"):
            _render_sheet(second, index=2, count=2, label="second")

    def test_a_datum_letter_names_one_feature_per_sheet(self) -> None:
        sheet, top, front, right = self._plate()
        front.datum("A", (0, -25, 0))
        with self.assertRaisesRegex(ValueError, "datum A"):
            top.datum("A", (-40, 0, 10))
        with self.assertRaisesRegex(ValueError, "letter"):
            top.datum("O", (-40, 0, 10))

    def test_the_general_profile_note_is_note_1(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import GENERIC, Frame, Sheet

        with self.assertRaisesRegex(ValueError, "surface_profile"):
            Sheet("A3", 1.0, general_profile=Frame("flatness", 0.1))
        sheet = Sheet("A3", 1.0, general_profile=Frame("surface_profile", 0.2, ("A", "B")),
                      general_tolerance="ISO 2768-m", profile=GENERIC)
        top, front, right = sheet.three_views(self._plate()[1].shape)
        front.datum("A", (0, -25, 0))
        top.datum("B", (-40, 0, 10))
        self.assertTrue(sheet.note_lines()[0].endswith("1. UNLESS OTHERWISE SPECIFIED, ALL SURFACES"))
        doc = _render_sheet(sheet, index=1, count=1, label="profile", warnings=[])
        notes = [e.dxf.text for e in doc.modelspace().query("TEXT")]
        self.assertIn("0.2", notes, "the frame drawn at the end of note 1")

    def test_a_free_frame_points_at_a_surface_and_keeps_clear_of_other_text(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Frame

        sheet, top, front, right = self._plate()
        front.datum("A", (0, -25, 0))
        top.frame((0, 20, 10), Frame("flatness", 0.05))
        top.frame((-30, -20, 10), Frame("parallelism", 0.1, ("A",)), offset=(-12, -12))
        front.overall()
        warnings: list = []
        doc = _render_sheet(sheet, index=1, count=1, label="free", warnings=warnings)
        texts = [e.dxf.text for e in doc.modelspace().query("TEXT[layer=='DIM']")]
        self.assertEqual((texts.count("0.05"), texts.count("0.1")), (1, 1), "both frames drawn")
        self.assertEqual(len(doc.modelspace().query("LEADER")), 2, "each frame's leader to its surface")
        self.assertFalse([w for w in warnings if "overlaps" in w], warnings)

    def test_a_dimension_carries_its_frame_and_the_datum_it_defines(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Frame

        sheet, top, front, right = self._plate()
        front.datum("A", (0, -25, 0))
        front.dim((-40, -25, 0), (-40, -25, 10), frame=Frame("parallelism", 0.05, ("A",)), datum="B")
        top.dim((-40, -25, 10), (40, -25, 10), frame=Frame("perpendicularity", 0.1, ("A", "B")))
        warnings: list = []
        doc = _render_sheet(sheet, index=1, count=1, label="dim frames", warnings=warnings)
        texts = [e.dxf.text for e in doc.modelspace().query("TEXT[layer=='DIM']")]
        self.assertEqual((texts.count("0.05"), texts.count("0.1"), texts.count("B")), (1, 1, 2),
                         "both frames, and B as a symbol and in a frame")
        self.assertFalse([w for w in warnings if "overlaps" in w or "crosses" in w], warnings)


class StageProfileTests(unittest.TestCase):
    """A stage says how much a drawing must define; a profile, whose conventions it follows."""

    def _sheet(self, hole_key: bool = False, **kwargs):
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0, title="STAGED", **kwargs)
        top, front, right = sheet.three_views(_part())
        top.overall()
        front.overall()
        top.hole((10, 5, 10), key=hole_key)
        return sheet, top, front

    def _texts(self, sheet, layer: str | None = None) -> list[str]:
        from cadgen._internal.drawing_render import _render_sheet

        doc = _render_sheet(sheet, index=1, count=1, label="staged", warnings=[])
        query = f"TEXT[layer=='{layer}']" if layer else "TEXT"
        return [e.dxf.text for e in doc.modelspace().query(query)]

    def _report(self, sheet, kind: str = "unstated") -> list[str]:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _requirements, _unstated

        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="staged", warnings=[], facts=facts)
        return _unstated(facts) if kind == "unstated" else _requirements(facts)

    def test_stage_is_closed_and_prints_in_the_title_block(self) -> None:
        from cadgen.eng_drawing import Sheet

        for stage, printed in (("prototype", "PROTOTYPE"), ("concept", "CONCEPT, NOT FOR MANUFACTURE")):
            texts = self._texts(self._sheet(stage=stage)[0])
            self.assertIn("STAGE", texts)
            self.assertIn(printed, texts)
        with self.assertRaisesRegex(ValueError, "concept, prototype, production"):
            Sheet("A3", stage="beta")

    def test_a_category_maps_to_its_stage(self) -> None:
        from cadgen.eng_drawing import Profile, Sheet

        acme = Profile("ACME", "ASME Y14.5-2018", {"TYPE B": "production"})
        sheet = self._sheet(profile=acme, category="TYPE B")[0]
        self.assertIn("TYPE B", self._texts(sheet))
        self.assertTrue(any("no datum" in line for line in self._report(sheet)), "checked as production")
        with self.assertRaisesRegex(ValueError, "TYPE B"):
            Sheet("A3", profile=acme, category="TYPE B", stage="prototype")
        with self.assertRaisesRegex(ValueError, "TYPE B"):
            Sheet("A3", profile=acme, category="TYPE Z")
        with self.assertRaisesRegex(ValueError, "profile"):
            Sheet("A3", category="TYPE B")
        with self.assertRaisesRegex(ValueError, "concept, prototype, production"):
            Profile("ACME", "ASME Y14.5-2018", {"TYPE B": "release"})
        with self.assertRaisesRegex(ValueError, "ISO GPS"):
            Profile("ACME", "DIN 7167", {})

    def test_a_general_tolerance_from_the_other_standard_is_refused(self) -> None:
        from cadgen.eng_drawing import GENERIC, Sheet

        with self.assertRaisesRegex(ValueError, "ASME Y14.5-2018"):
            Sheet("A3", profile=_aero(), general_tolerance="ISO 2768-m")
        with self.assertRaisesRegex(ValueError, "ISO GPS"):
            Sheet("A3", profile=GENERIC, general_tolerance="ASME Y14.5 BLOCK")
        notes = Sheet("A3", profile=_aero(), general_tolerance="±0.1").drawn_notes()
        self.assertEqual(notes, ["DIMENSIONS AND TOLERANCES PER ASME Y14.5-2018.",
                                 "UNLESS OTHERWISE SPECIFIED, TOLERANCES ARE ±0.1."])

    def test_what_each_stage_requires_is_reported(self) -> None:
        from cadgen.eng_drawing import eng_drawing

        concept = self._report(self._sheet(stage="concept")[0])
        self.assertFalse([line for line in concept if "tolerance" in line or "material" in line], concept)
        prototype = self._report(self._sheet(stage="prototype")[0])
        self.assertEqual(len([line for line in prototype if "general tolerance" in line]), 1, prototype)
        self.assertEqual(len([line for line in prototype if "material" in line]), 1, prototype)
        production = self._report(self._sheet(stage="production")[0])
        for words in ("no datum", "general profile", "spec", "finish"):
            self.assertEqual(len([line for line in production if words in line]), 1, (words, production))
        with temporary_directory(prefix="tmp-cad-eng-drawing-") as td:
            out = Path(td) / "bare.pdf"

            @eng_drawing(out=str(out))
            def bare():
                return self._sheet(stage="production")[0]

            self.assertEqual(bare(), [out])
            self.assertTrue(out.read_bytes().startswith(b"%PDF"))

    def test_the_report_says_what_is_required_apart_from_what_is_drawn(self) -> None:
        """"All features dimensioned" can stand beside "no tolerance stated": the
        report says both, so a handoff cannot confuse one for the other."""
        from cadgen.eng_drawing import GENERIC, Frame

        nominal = self._report(self._sheet(stage="concept")[0], "required")
        self.assertEqual(len(nominal), 1, nominal)
        for words in ("concept", "all nominal", "no general tolerance", "no datums", "⌀6 THRU"):
            self.assertIn(words, nominal[0])
        sheet, top, front = self._sheet(stage="production", material="AL 6061-T6", spec="AMS 4027", finish="NONE",
                                        general_tolerance="ISO 2768-m", hole_key=True, profile=GENERIC)
        front.datum("A", (0, -15, 0))
        top.dim((-20, -15, 10), (10, -15, 10), basic=True)
        top.dim((-20, 15, 10), (20, 15, 10), tol=0.1)
        top.frame((0, 0, 10), Frame("flatness", 0.05))
        stated = self._report(sheet, "required")
        self.assertEqual(len(stated), 1, stated)
        for words in ("production", "1 toleranced", "1 basic", "nominal under ISO 2768-m", "datums A", "1 frame",
                      "1 key characteristic"):
            self.assertIn(words, stated[0])

    def test_a_finished_production_sheet_reports_nothing_of_its_stage(self) -> None:
        from cadgen.eng_drawing import GENERIC, Frame

        sheet, top, front = self._sheet(stage="production", material="AL 6061-T6", spec="AMS 4027",
                                        finish="ANODISE CLEAR", general_profile=Frame("surface_profile", 0.2, ("A",)),
                                        profile=GENERIC)
        front.datum("A", (0, -15, 0))
        top.dim((-20, -15, 10), (10, -15, 10), key=True)
        self.assertFalse([line for line in self._report(sheet) if "production" in line])

    def test_notes_running_under_the_title_block_stand_above_its_band(self) -> None:
        from cadgen._internal.drawing_base import _MARGIN, _TITLE_W
        from cadgen._internal.drawing_sheet import _notes_box
        from cadgen.eng_drawing import Sheet

        for notes in (["BREAK SHARP EDGES."], ["EXAMPLE REQUIREMENTS FOR DEMONSTRATION; NOT A RELEASED DESIGN."]):
            sheet = Sheet("A4", 1.0, stage="prototype", notes=notes)
            ((x0, x1, y0, y1),) = _notes_box(sheet)
            title = (297 - _MARGIN - _TITLE_W, _MARGIN + sheet._title_height())
            self.assertTrue(x1 <= title[0] or y0 >= title[1], (notes, x1, y0, title))
        self.assertLess(y0 - 1.0, _MARGIN + sheet._title_height() + 4.0 + 1e-6, "no higher than it must")

    def test_material_and_spec_print_together(self) -> None:
        from cadgen.eng_drawing import Sheet

        sheet = self._sheet(material="AL 6061-T6", spec="AMS 4027")[0]
        self.assertIn("AL 6061-T6 PER AMS 4027", self._texts(sheet))
        with self.assertRaisesRegex(ValueError, "material="):
            Sheet("A3", spec="AMS 4027")

    def test_a_title_block_value_too_long_for_its_cell_is_refused_not_cut(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet

        sheet = self._sheet(material="ALUMINUM ALLOY 7075-T7351 PLATE", spec="AMS-QQ-A-250/12")[0]
        with self.assertRaisesRegex(ValueError, r"MATERIAL 'ALUMINUM.*does not fit"):
            _render_sheet(sheet, index=1, count=1, label="long")

    def test_a_profiles_extra_fields_print_blank_until_given(self) -> None:
        from cadgen.eng_drawing import Sheet

        texts = self._texts(self._sheet(profile=_aero(), company="ACME AERO")[0], "TITLE")
        for caption in ("COMPANY", "ACME AERO", "STAGE", "CAGE CODE", "DISTRIBUTION"):
            self.assertIn(caption, texts)
        texts = self._texts(self._sheet(profile=_aero(), fields={"CAGE CODE": "1ABC2"})[0], "TITLE")
        self.assertIn("1ABC2", texts)
        with self.assertRaisesRegex(ValueError, "CAGE CODE"):
            Sheet("A3", fields={"CAGE CODE": "1ABC2"})
        with self.assertRaisesRegex(ValueError, "EXPORT"):
            Sheet("A3", profile=_aero(), fields={"EXPORT": "EAR99"})

    def test_a_key_characteristic_is_marked(self) -> None:
        from cadgen.eng_drawing import Profile

        sheet, top, front = self._sheet(profile=_aero(), stage="production")
        self.assertTrue(any(line.startswith("note:") and "key characteristic" in line
                            for line in self._report(sheet)))
        sheet, top, front = self._sheet(profile=_aero(), stage="production", hole_key=True)
        top.dim((-20, -15, 10), (10, -15, 10), key=True)
        texts = self._texts(sheet, "DIM")
        self.assertEqual(texts.count("KC"), 2, "the dimension's mark and the callout's")
        self.assertFalse([line for line in self._report(sheet) if "key characteristic" in line])
        own = Profile("OWN", "ISO GPS", {}, characteristic_mark="CC")
        sheet, top, front = self._sheet(profile=own)
        top.dim((-20, -15, 10), (10, -15, 10), key=True)
        self.assertIn("CC", self._texts(sheet, "DIM"))


class FlagNoteTests(unittest.TestCase):
    """What an assembly requires once it is put together, flagged where it applies."""

    @staticmethod
    def _triangles(doc, layer: str) -> int:
        return len([e for e in doc.modelspace().query(f"LWPOLYLINE[layer=='{layer}']") if e.closed and len(e) == 3])

    def test_a_flag_note_numbers_its_flag_and_its_note(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0, notes=["BREAK SHARP EDGES."])
        top, front, _right = sheet.three_views(_part())
        top.flag("TORQUE TO 9 NM", at=(10, 5, 10))
        front.flag("LOCTITE 401", at=(0, -15, 5), joint="bond")
        top.flag("TORQUE TO 9 NM", at=(-10, 0, 10))
        self.assertEqual(sheet.drawn_notes(), ["BREAK SHARP EDGES.", "TORQUE TO 9 NM", "BOND: LOCTITE 401"])
        doc = _render_sheet(sheet, index=1, count=1, label="flags", warnings=[])
        field = [e.dxf.text for e in doc.modelspace().query("TEXT[layer=='DIM']")]
        self.assertEqual((field.count("2"), field.count("3")), (2, 1), "a flag numbered as its note, twice for two places")
        self.assertEqual(self._triangles(doc, "DIM"), 3)
        self.assertEqual(self._triangles(doc, "NOTES"), 2, "notes 2 and 3 carry their flags")
        lines = [e.dxf.text for e in doc.modelspace().query("TEXT[layer=='NOTES']")]
        self.assertTrue(any(line.endswith("BOND: LOCTITE 401") for line in lines), lines)
        with self.assertRaisesRegex(ValueError, "one of at= or item="):
            top.flag("TORQUE TO 9 NM")

    def test_an_unplaced_flag_keeps_clear_of_the_dimensions(self) -> None:
        from shapely.geometry import LineString, Polygon, box

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front, _right = sheet.three_views(_part())
        top.overall()
        front.overall()
        top.dim((-20, -15, 10), (10, -15, 10))
        top.flag("TORQUE TO 9 NM", at=(-5, 0, 10))
        top.flag("STAKE 3 PLACES", at=(-20, 15, 10))
        warnings: list = []
        doc = _render_sheet(sheet, index=1, count=1, label="clear", warnings=warnings)
        self.assertFalse([w for w in warnings if "overlaps" in w or "flag" in w], warnings)
        lines = _dimension_lines(doc)
        for leader in doc.modelspace().query("LEADER[layer=='DIM']"):
            path = LineString([(v[0], v[1]) for v in leader.vertices])
            self.assertFalse([line for line in lines if path.crosses(line)], "a flag's leader crosses a dimension")
        # Each view's extent, from its visible lines: views stand apart, so boxes
        # that touch are one view.
        views: list[list[float]] = []
        for line in doc.modelspace().query("LINE LWPOLYLINE[layer=='VISIBLE']"):
            x0, y0, x1, y1 = LineString(_points(line)).bounds
            hit = [v for v in views if x0 <= v[2] + 1 and x1 >= v[0] - 1 and y0 <= v[3] + 1 and y1 >= v[1] - 1]
            merged = [min([x0, *(v[0] for v in hit)]), min([y0, *(v[1] for v in hit)]),
                      max([x1, *(v[2] for v in hit)]), max([y1, *(v[3] for v in hit)])]
            views = [v for v in views if v not in hit] + [merged]
        flags = [Polygon(e.get_points("xy")) for e in doc.modelspace().query("LWPOLYLINE[layer=='DIM']")
                 if e.closed and len(e) == 3]
        self.assertEqual(len(flags), 2)
        self.assertFalse([f for f in flags if any(f.intersects(box(*v)) for v in views)], "a flag on a view")

    def test_a_flag_keyed_to_an_item_lands_on_that_item(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        parts = parts_list(_assembly())
        sheet = Sheet("A3", 1.0)
        front = sheet.view(parts.assembly, "front", at=(160, 170), hidden=False)
        front.balloons(parts)
        front.flag("PRESS WITH LOCTITE 609", item="pin", joint="press_fit")
        doc = _render_sheet(sheet, index=1, count=1, label="keyed", warnings=[])
        flag = next(e for e in doc.modelspace().query("LEADER[layer=='DIM']"))
        start = flag.vertices[0]
        pin = next(point for number, _centre, point in _balloons(doc) if number == 2)
        self.assertLess(math.hypot(start[0] - pin[0], start[1] - pin[1]), 0.5, "on the pin, where its balloon keys it")
        from shapely.geometry import LineString

        path = LineString([(v[0], v[1]) for v in flag.vertices])
        balloon_leaders = [LineString([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)])
                           for e in doc.modelspace().query("LINE[layer=='NOTES']")]
        self.assertFalse([b for b in balloon_leaders if path.crosses(b)], "the flag's leader crosses a balloon's")
        lonely = Sheet("A3", 1.0)
        bare = lonely.view(parts.assembly, "front", at=(160, 170), hidden=False)
        bare.flag("PRESS", item="pin")
        with self.assertRaisesRegex(ValueError, "balloons"):
            _render_sheet(lonely, index=1, count=1, label="unkeyed")

    def test_an_unknown_joint_kind_is_refused(self) -> None:
        from cadgen.eng_drawing import Sheet

        top = Sheet("A3", 1.0).three_views(_part())[0]
        with self.assertRaisesRegex(ValueError, "weld, braze"):
            top.flag("GLUE IT", at=(0, 0, 10), joint="glue")

    def test_the_general_arrangements_overall_sizes_are_reference(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import GENERIC, assembly_sheets, parts_list

        sheets = assembly_sheets(parts_list(_assembly()), title="FIXTURE", stage="prototype", profile=GENERIC,
                                 company="EXAMPLE CO.")
        self.assertTrue(all((s.stage, s.profile, s.company) == ("prototype", GENERIC, "EXAMPLE CO.") for s in sheets))
        texts = _dim_texts(_render_sheet(sheets[0], index=1, count=len(sheets), label="ga"))
        self.assertTrue(texts and all(t.startswith("(") and t.endswith(")") for t in texts), texts)

    def test_a_detail_of_the_general_arrangement_draws(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import assembly_sheets, parts_list

        sheets = assembly_sheets(parts_list(_assembly()), title="FIXTURE")
        ga = sheets[0]
        front = next(v for v in ga.views if v.name == "front")
        ga.detail(front, (-25, 0, 6), 6)
        labels = [e.dxf.text for e in _render_sheet(ga, index=1, count=len(sheets), label="ga").modelspace()
                  .query("TEXT[layer=='NOTES']")]
        self.assertTrue(any(label.startswith("DETAIL") for label in labels), labels)


def _stack(*layers):
    """Layers stacked up Z from 0, each (label, thickness, family), as an assembly
    with its parts list, families stated."""
    from build123d import Align, Box, Compound, Pos

    from cadgen.eng_drawing import parts_list

    children, z = [], 0.0
    for label, thickness, _family in layers:
        layer = Pos(0, 0, z) * Box(40, 30, thickness, align=(Align.CENTER, Align.CENTER, Align.MIN))
        layer.label = label
        children.append(layer)
        z += thickness
    parts = parts_list(Compound(children=children, label="stack"))
    for label, _thickness, family in layers:
        parts.set(label, family=family, material=label.upper())
    return parts


class AssemblySectionTests(unittest.TestCase):
    """A section through an assembly, as drafters draw one: every part in one
    general-purpose hatch, neighbours told apart by its angle and spacing, solid
    round parts cut along their axis left uncut, and the parts keyed by balloons."""

    @staticmethod
    def _rig():
        from build123d import Align, Box, Compound, Cylinder, Pos

        from cadgen.eng_drawing import parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        housing = Box(60, 40, 30, align=up) - Cylinder(10, 30, align=up)
        sleeve = Cylinder(10, 30, align=up) - Cylinder(6, 30, align=up)
        rod = Pos(0, 0, -10) * Cylinder(6, 50, align=up)
        housing.label, sleeve.label, rod.label = "housing", "sleeve", "rod"
        parts = parts_list(Compound(children=[housing, sleeve, rod], label="rig"))
        parts.set("housing", family="aluminium")
        parts.set("sleeve", family="copper_alloy")
        parts.set("rod", family="steel")
        return parts

    def _sheet(self, parts, **section):
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 2.0)
        front = sheet.view(parts.assembly, "front", at=(150, 140), hidden=False).section("A", parts=parts, **section)
        sheet.view(parts.assembly, "top", at=(150, 240), hidden=False)
        return sheet, front

    def test_every_part_takes_one_hatch_and_neighbours_differ(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet

        sheet, _front = self._sheet(self._rig())
        doc = _render_sheet(sheet, index=1, count=1, label="rig", warnings=[])
        hatches = list(doc.modelspace().query("HATCH[layer=='HATCH']"))
        self.assertTrue(hatches)
        self.assertEqual({h.dxf.pattern_name for h in hatches}, {"ANSI31"}, "materials are the parts list's")
        looks = {(round(h.dxf.pattern_angle) % 180, round(h.dxf.pattern_scale, 3)) for h in hatches}
        self.assertEqual(len(looks), 2, "the housing and the sleeve touch, so they differ")
        self.assertNotIn("MATERIAL KEY", [e.dxf.text for e in doc.modelspace().query("TEXT")])

    def test_a_solid_rod_cut_along_its_axis_is_not_hatched(self) -> None:
        from shapely.geometry import Point, Polygon

        from cadgen._internal.drawing_render import _render_sheet

        sheet, front = self._sheet(self._rig())
        doc = _render_sheet(sheet, index=1, count=1, label="rig", warnings=[])
        regions = [Polygon([(v[0], v[1]) for v in path.vertices]) for h in doc.modelspace().query("HATCH[layer=='HATCH']")
                   for path in h.paths if hasattr(path, "vertices")]
        middle = Point(front.at[0], front.at[1])
        self.assertFalse([r for r in regions if r.contains(middle)], "the rod on the axis: drawn uncut (ISO 128-50)")

    def test_a_pin_with_a_cotter_hole_is_still_drawn_uncut(self) -> None:
        from build123d import Align, Box, Compound, Cylinder, Pos, Rot

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        block = Box(40, 40, 20, align=up) - Cylinder(5, 20, align=up)
        pin = Pos(0, 0, -5) * Cylinder(5, 40, align=up) - Pos(0, 0, 28) * Rot(0, 90, 0) * Cylinder(1, 20)
        block.label, pin.label = "block", "pin"
        parts = parts_list(Compound(children=[block, pin], label="pinned"))
        sheet = Sheet("A3", 2.0)
        front = sheet.view(parts.assembly, "front", at=(150, 140), hidden=False).section("A", parts=parts)
        sheet.view(parts.assembly, "top", at=(150, 240), hidden=False)
        msp = _render_sheet(sheet, index=1, count=1, label="pin", warnings=[]).modelspace()
        from shapely.geometry import Point, Polygon

        regions = [Polygon([(v[0], v[1]) for v in path.vertices]) for h in msp.query("HATCH[layer=='HATCH']")
                   for path in h.paths if hasattr(path, "vertices")]
        self.assertFalse([r for r in regions if r.contains(Point(front.at[0], front.at[1]))],
                         "a cross hole does not make a pin a part to hatch")

    def test_a_section_carries_balloons_inside_each_parts_cut(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet

        parts = self._rig()
        sheet, front = self._sheet(parts)
        front.balloons(parts)
        doc = _render_sheet(sheet, index=1, count=1, label="rig", warnings=[])
        from cadgen._internal.drawing_assembly import _BALLOON_R

        circles = [c for c in doc.modelspace().query("CIRCLE") if abs(c.dxf.radius - _BALLOON_R) < 1e-6]
        self.assertEqual(len(circles), 3, "each part the section cuts, keyed")

    def test_materials_true_hatches_each_part_as_its_material(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet

        sheet, _front = self._sheet(self._rig(), materials=True)
        doc = _render_sheet(sheet, index=1, count=1, label="rig", warnings=[])
        self.assertEqual({h.dxf.pattern_name for h in doc.modelspace().query("HATCH[layer=='HATCH']")},
                         {"ANSI38", "ANSI33"}, "aluminium and copper alloy; the rod still uncut")
        self.assertIn("MATERIAL KEY", [e.dxf.text for e in doc.modelspace().query("TEXT")])


class MaterialSectionTests(unittest.TestCase):
    """A section hatched by material (``materials=True``): each cut as what it is,
    for a layered part where the materials are the point."""

    def _cut(self, parts, scale: float = 2.0):
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", scale)
        front = sheet.view(parts.assembly, "front", at=(150, 120), hidden=False).section("A", parts=parts,
                                                                                         materials=True)
        sheet.view(parts.assembly, "top", at=(150, 210), hidden=False)
        warnings: list = []
        doc = _render_sheet(sheet, index=1, count=1, label="layers", warnings=warnings)
        return doc, front, warnings

    @staticmethod
    def _hatches(doc):
        return list(doc.modelspace().query("HATCH[layer=='HATCH']"))

    def test_each_item_in_a_section_is_hatched_by_its_family(self) -> None:
        doc, _front, _warnings = self._cut(_stack(("shell", 4, "aluminium"), ("base", 6, "plastic")))
        self.assertEqual(sorted(h.dxf.pattern_name for h in self._hatches(doc)), ["ANSI34", "ANSI38"])

    @staticmethod
    def _look(hatch) -> tuple:
        return round(hatch.dxf.pattern_angle) % 180, round(hatch.dxf.pattern_scale, 3)

    def test_neighbours_of_one_family_differ_in_angle_then_spacing(self) -> None:
        doc, _front, _warnings = self._cut(_stack(("lower", 4, "steel"), ("middle", 4, "steel"), ("upper", 4, "steel")))
        hatches = sorted(self._hatches(doc), key=lambda h: min(v[1] for v in h.paths[0].vertices))
        self.assertEqual(sorted({look[0] for look in map(self._look, hatches)}), [0, 90],
                         "turned a right angle, never 45 (its lines would read as edges)")
        lower, middle, upper = map(self._look, hatches)
        self.assertNotEqual(lower, middle)
        self.assertNotEqual(middle, upper)

    def test_parts_that_touch_never_look_alike_whatever_their_order(self) -> None:
        """Item 5 sits on item 1: in item order they took the same look."""
        from build123d import Align, Box, Compound, Pos

        from cadgen.eng_drawing import parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        places = {"a": (0, 0, 40), "b": (60, 0, 20), "c": (60, 4, 20), "d": (60, 8, 20), "e": (0, 4, 40)}
        children = []
        for label, (x, z, width) in places.items():
            block = Pos(x, 0, z) * Box(width, 30, 4, align=up)
            block.label = label
            children.append(block)
        parts = parts_list(Compound(children=children, label="blocks"))
        for label in places:
            parts.set(label, family="steel", material=f"STEEL {label.upper()}")
        doc, _front, _warnings = self._cut(parts, scale=1.0)
        left = sorted((h for h in self._hatches(doc) if max(v[0] for v in h.paths[0].vertices) < 160),
                      key=lambda h: min(v[1] for v in h.paths[0].vertices))
        self.assertEqual(len(left), 2, "items 1 and 5, one on the other")
        self.assertNotEqual(self._look(left[0]), self._look(left[1]), "items 1 and 5 touch")
        swatches = [h for h in doc.modelspace().query("HATCH[layer=='DIM']")]
        self.assertEqual(len(swatches), 5, "a key row per part, all one family")
        texts = [e.dxf.text for e in doc.modelspace().query("TEXT")]
        self.assertTrue({"1", "5", "STEEL A", "STEEL E"} <= set(texts), "each row names its item and material")
        self.assertEqual({round(h.dxf.pattern_angle) % 180 for h in swatches},
                         {self._look(h)[0] for h in self._hatches(doc)}, "the key shows the turns the regions have")

    def test_a_thin_layer_is_filled_solid(self) -> None:
        doc, _front, _warnings = self._cut(_stack(("shell", 4, "plastic"), ("tape", 0.2, "general"),
                                                  ("lining", 2, "fabric")), scale=1.0)
        solid = [h for h in self._hatches(doc) if h.dxf.solid_fill]
        self.assertEqual(len(solid), 1, "the 0.2 mm tape, too thin to hatch")
        texts = [e.dxf.text for e in doc.modelspace().query("TEXT")]
        self.assertIn("THIN, SOLID", texts, "the key says so")
        self.assertEqual(texts.count("TAPE"), 2, "the key row, and the callout on the layer itself")
        callout = next(e for e in doc.modelspace().query("LEADER[layer=='NOTES']"))
        tape = next(h for h in self._hatches(doc) if h.dxf.solid_fill)
        from shapely.geometry import Point, Polygon

        region = Polygon([(v[0], v[1]) for v in tape.paths[0].vertices])
        self.assertLess(region.distance(Point(callout.vertices[0][0], callout.vertices[0][1])), 0.05,
                        "the leader ends on the tape")

    def test_overlapping_items_are_hatched_once(self) -> None:
        from build123d import Box, Compound, Pos
        from shapely.geometry import Polygon
        from shapely.ops import unary_union

        from cadgen.eng_drawing import parts_list

        a, b = Pos(-5, 0, 0) * Box(20, 10, 10), Pos(5, 0, 0) * Box(20, 10, 10)
        a.label, b.label = "stud", "nut"
        parts = parts_list(Compound(children=[a, b], label="joint"))
        doc, _front, _warnings = self._cut(parts, scale=1.0)
        regions = [Polygon([(v[0], v[1]) for v in path.vertices]) for h in self._hatches(doc)
                   for path in h.paths if hasattr(path, "vertices")]
        self.assertAlmostEqual(sum(r.area for r in regions), unary_union(regions).area, delta=1.0)
        self.assertAlmostEqual(unary_union(regions).area, 30 * 10, delta=1.0)

    def test_a_material_key_appears_with_two_families(self) -> None:
        doc, _front, _warnings = self._cut(_stack(("shell", 4, "aluminium"), ("base", 6, "plastic")))
        texts = [e.dxf.text for e in doc.modelspace().query("TEXT")]
        for words in ("MATERIAL KEY", "ALUMINIUM", "PLASTIC", "SHELL", "BASE"):
            self.assertIn(words, texts)
        from build123d import Box, Compound

        from cadgen.eng_drawing import parts_list

        lone = Box(40, 30, 10)
        lone.label = "block"
        doc, _front, _warnings = self._cut(parts_list(Compound(children=[lone])))
        self.assertNotIn("MATERIAL KEY", [e.dxf.text for e in doc.modelspace().query("TEXT")], "one part needs none")

    def test_a_section_by_parts_is_of_the_parts_lists_assembly(self) -> None:
        from cadgen.eng_drawing import Sheet

        parts = _stack(("shell", 4, "aluminium"), ("base", 6, "plastic"))
        with self.assertRaisesRegex(ValueError, "parts.assembly"):
            Sheet("A3").view(_part(), "front", at=(100, 100)).section("A", parts=parts)


def _aero(**changes):
    """An aerospace company's profile, as its project writes one: Y14.5, and the CAGE CODE and
    DISTRIBUTION cells."""
    from cadgen.eng_drawing import Profile

    return Profile(**{"name": "AERO", "standard": "ASME Y14.5-2018", "fields": ("CAGE CODE", "DISTRIBUTION"),
                      **changes})


def _bushed_plate():
    """A 100 x 70 x 10 plate built from its datum corner (C at X = 0, B at Y = 0, A at
    Z = 0): four ⌀6.6 holes 12 in from its edges and a ⌀16 bore in the middle, with a
    lined bushing pressed in flush -- a sleeve to ⌀12.5 and a 0.25 liner in it -- each a
    part, as the pivot mount plate example draws it."""
    from build123d import Align, Box, Compound, Cylinder, Pos

    from cadgen.eng_drawing import parts_list

    corner, up = (Align.MIN, Align.MIN, Align.MIN), (Align.CENTER, Align.CENTER, Align.MIN)
    plate = Box(100, 70, 10, align=corner)
    for x, y in ((12, 12), (88, 12), (12, 58), (88, 58)):
        plate -= Pos(x, y, 0) * Cylinder(3.3, 10, align=up)
    plate -= Pos(50, 35, 0) * Cylinder(8, 10, align=up)
    sleeve = Pos(50, 35, 0) * (Cylinder(8, 10, align=up) - Cylinder(6.25, 10, align=up))
    liner = Pos(50, 35, 0) * (Cylinder(6.25, 10, align=up) - Cylinder(6, 10, align=up))
    plate.label, sleeve.label, liner.label = "mount_plate", "bushing", "liner"
    parts = parts_list(Compound(children=[plate, sleeve, liner], label="pivot_mount_plate"))
    parts.set("mount_plate", material="AL 7075-T651", spec="AMS 4045", family="aluminium")
    parts.set("bushing", material="CRES 303", spec="AMS 5640", family="steel")
    parts.set("liner", material="PTFE FABRIC", spec="AS81934", family="fabric")
    return parts


class AerospaceExampleTests(unittest.TestCase):
    """Every requirement the vocabulary has, on one released aerospace drawing: a
    company's own Y14.5 profile, datums on real faces, frames, basic, toleranced and
    limit sizes, key characteristics, and the installed bushing cut and hatched by
    material."""

    def _drawing(self):
        from cadgen.eng_drawing import Frame, Sheet

        parts = _bushed_plate()
        aero = _aero(name="EXAMPLE AERO", categories={"PRELIMINARY": "prototype", "RELEASED": "production"})
        release = dict(profile=aero, category="RELEASED", company="EXAMPLE AERO CO.",
                       fields={"CAGE CODE": "0ABC1", "DISTRIBUTION": "A"})
        assembly = Sheet("A3", 2.0, title="PIVOT MOUNT PLATE ASSY", **release)
        front, right = assembly.three_views(parts.assembly, views=("front", "right"))
        front.section("A", through=(50, 35, 0), parts=parts, materials=True)
        front.overall(reference=True)
        right.overall(height=False, reference=True)
        front.balloons(parts)
        front.dim((44, 35, 10), (56, 35, 10), text="%%c<>", limits=(12.0, 12.025), key=True)
        wall = assembly.detail(front, (57.125, 35, 5), 4)
        wall.flag("ITEM 2 INTO ITEM 1", at=(58, 35, 5), joint="press_fit")
        wall.flag("ITEM 3 TO ITEM 2 PER AS81934", at=(56.25, 35, 5), joint="bond")
        assembly.parts_list(parts)

        plate = Sheet(size=None, scale=None, title="MOUNT PLATE", material="AL 7075-T651", spec="AMS 4045",
                      finish="CHEM FILM", general_tolerance="±0.1", **release)
        top, side, end, _iso = plate.three_views(parts["mount_plate"].shape, iso=True)
        side.datum("A", (25, 35, 0))
        side.frame((75, 35, 0), Frame("flatness", 0.05), offset=(12, -12))
        end.datum("B", (50, 0, 5))
        end.frame((50, 0, 10), Frame("perpendicularity", 0.05, ("A",)), offset=(-10, 12))
        side.datum("C", (0, 35, 5))
        side.frame((0, 35, 7.5), Frame("perpendicularity", 0.05, ("A", "B")))
        top.overall()
        side.overall(width=False)
        top.dim((0, 65, 10), (12, 58, 10), orientation="h", basic=True)
        top.dim((12, 58, 10), (88, 58, 10), basic=True)
        top.dim((0, 5, 10), (50, 35, 10), orientation="h", basic=True)
        top.dim((95, 0, 10), (88, 12, 10), orientation="v", basic=True)
        top.dim((88, 12, 10), (88, 58, 10), basic=True)
        top.dim((5, 0, 10), (50, 35, 10), orientation="v", basic=True)
        top.hole((88, 58, 10), frame=Frame("position", 0.25, ("A", "B", "C"), diameter=True, modifier="M"))
        top.hole((50, 35, 10), fit="H7", frame=Frame("position", 0.05, ("A", "B", "C"), diameter=True), key=True)
        return assembly, plate

    def _render(self):
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _requirements, _unstated

        sheets, facts, warnings = self._drawing(), _facts(), []
        docs = [_render_sheet(sheet, index=i, count=2, label="pivot", warnings=warnings, facts=facts)
                for i, sheet in enumerate(sheets, start=1)]
        return docs, warnings, _unstated(facts), _requirements(facts)

    def test_it_states_everything_a_released_drawing_asks(self) -> None:
        _docs, warnings, unstated, requirements = self._render()
        self.assertEqual([line for line in unstated if line.startswith(("incomplete:", "note:"))], [])
        self.assertFalse([w for w in warnings if "overlap" in w or "crowded" in w or "crosses" in w], warnings)
        (line,) = requirements
        self.assertIn("production", line)
        self.assertIn("datums A B C", line)
        self.assertIn("5 frames", line)
        self.assertIn("1 key characteristic", line)
        self.assertNotIn("no fit, tolerance or position", line)

    def test_the_plate_carries_its_datums_and_frames(self) -> None:
        (_assembly, plate), *_rest = self._render()
        msp = plate.modelspace()
        texts = [e.dxf.text for e in msp.query("TEXT[layer=='DIM']")]
        for letter in "ABC":
            self.assertGreaterEqual(texts.count(letter), 3, f"datum {letter}: its symbol and the frames naming it")
        for value in ("0.25", "0.05", "M", "KC"):
            self.assertIn(value, texts)
        self.assertGreaterEqual(len(msp.query("HATCH[layer=='DIM']")), 3, "each datum's filled triangle")
        basic = [d for d in msp.query("DIMENSION") if (d.override().get("dimgap") or 0) < 0]
        self.assertEqual(len(basic), 6, "the pattern and the bore located by basic dimensions")
        titles = [e.dxf.text for e in msp.query("TEXT[layer=='TITLE']")]
        for words in ("RELEASED", "0ABC1", "EXAMPLE AERO CO.", "AL 7075-T651 PER AMS 4045"):
            self.assertIn(words, titles)

    def test_the_assembly_is_cut_and_hatched_by_material(self) -> None:
        ((assembly, _plate), *_rest) = self._render()
        msp = assembly.modelspace()
        hatches = list(msp.query("HATCH[layer=='HATCH']"))
        patterns = {h.dxf.pattern_name for h in hatches if not h.dxf.solid_fill}
        self.assertTrue({"ANSI38", "ANSI32", "ANSI37"} <= patterns,
                        "the plate as aluminium, the sleeve as steel, the liner as fabric in the detail")
        self.assertTrue([h for h in hatches if h.dxf.solid_fill], "the liner, too thin to hatch at 2:1")
        texts = [e.dxf.text for e in msp.query("TEXT")]
        for words in ("MATERIAL KEY", "AS81934", "KC"):
            self.assertIn(words, texts)
        limits = [d.dxf.text for d in msp.query("DIMENSION") if "\\S" in d.dxf.text]
        self.assertEqual(limits, ["%%c{\\H0.70x;\\S12.025^ 12.000;}"], "the installed bore's ⌀, between its limits")
        dims = " ".join(_dim_texts(assembly))
        self.assertIn("12.025", dims)
        self.assertIn("12.000", dims)


def _flange():
    """A ⌀80 x 10 flange: a ⌀30 bore, six ⌀6 holes equally spaced on ⌀60."""
    import math

    from build123d import Align, Cylinder, Pos

    up = (Align.CENTER, Align.CENTER, Align.MIN)
    flange = Cylinder(40, 10, align=up) - Cylinder(15, 10, align=up)
    for k in range(6):
        a = 2 * math.pi * k / 6
        flange -= Pos(30 * math.cos(a), 30 * math.sin(a), 0) * Cylinder(3, 10, align=up)
    return flange


def _mounting_plate():
    """A 100 x 70 x 8 plate: four corner holes on a 76 x 48 pattern, a central bore."""
    from build123d import Align, Box, Cylinder, Pos

    up = (Align.CENTER, Align.CENTER, Align.MIN)
    plate = Box(100, 70, 8, align=up) - Pos(0, 0, 0) * Cylinder(14, 8, align=up)
    for x in (-38, 38):
        for y in (-24, 24):
            plate -= Pos(x, y, 0) * Cylinder(2.75, 8, align=up)
    return plate


class LocationTests(unittest.TestCase):
    """A feature is drawn where it is only when a dimension says where: its size
    alone, or a spacing tied to nothing, leaves it anywhere on the part."""

    def _report(self, sheet) -> list[str]:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated

        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="where", warnings=[], facts=facts)
        return [line for line in _unstated(facts) if "not located" in line]

    def _plate(self):
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(_mounting_plate(), views=("top", "front"))
        top.overall()
        front.overall(width=False)
        top.holes()
        top.dim((-38, -24, 8), (38, -24, 8))               # the pattern's spacing, tied to nothing
        top.dim((38, -24, 8), (38, 24, 8))
        return sheet, top, front

    def test_a_spacing_tied_to_nothing_leaves_the_pattern_unlocated(self) -> None:
        sheet, top, _front = self._plate()
        lines = self._report(sheet)
        pattern = [line for line in lines if "4× ⌀5.5 THRU" in line]
        bore = [line for line in lines if "⌀28 THRU" in line]
        self.assertEqual(len(pattern), 1, lines)
        self.assertIn("along X and Y", pattern[0])
        self.assertEqual(len(bore), 1, lines)
        self.assertIn("top.symmetric(", bore[0], "the fix names the call")

    def test_an_edge_dimension_or_stated_symmetry_locates_it(self) -> None:
        sheet, top, _front = self._plate()
        top.dim((-50, -24, 8), (-38, -24, 8))              # the pattern from the left edge
        top.dim((-38, -35, 8), (-38, -24, 8))              # and from the front edge
        top.symmetric("h")
        top.symmetric("v")                                 # the bore is centred: stated, not assumed
        self.assertEqual(self._report(sheet), [])

    def test_a_spacing_centred_on_a_stated_centre_line_locates_both_ends(self) -> None:
        sheet, top, _front = self._plate()
        # Symmetric about both centre lines, a spacing across one puts each hole
        # half of it from the line (ISO 129-1): the pattern needs no edge dimension.
        top.symmetric("h")
        top.symmetric("v")
        self.assertEqual(self._report(sheet), [])

    def test_symmetry_the_part_does_not_have_is_refused(self) -> None:
        from build123d import Align, Box, Cylinder, Pos

        from cadgen.eng_drawing import Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        lopsided = Box(100, 60, 10, align=up) - Pos(-30, 0, 0) * Cylinder(4, 10, align=up) \
            - Pos(40, 20, 0) * Box(20, 20, 10, align=up)
        sheet = Sheet("A3", 1.0)
        top, _front = sheet.three_views(lopsided, views=("top", "front"))
        with self.assertRaisesRegex(ValueError, "not symmetric"):
            top.symmetric("v")
        detail = sheet.detail(top, (-30, 0, 10), 8)
        with self.assertRaisesRegex(ValueError, "detail"):
            detail.symmetric("v")

    def test_one_small_hole_off_the_centre_line_is_not_symmetric(self) -> None:
        # Judged by its share of the part's volume, a ⌀2 hole 30 off centre in a 300 × 200 × 10 plate (31 of
        # 600 000 mm³) was within 1e-4, and symmetric("v") placed a hole on the far side that is not there.
        from build123d import Align, Box, Cylinder, Pos

        from cadgen._internal.drawing_features import mirror_symmetric
        from cadgen.eng_drawing import Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        plate = Box(300, 200, 10, align=up) - Pos(30, 0, 0) * Cylinder(1, 10, align=up)
        sheet = Sheet("A2", 1.0)
        top, _front = sheet.three_views(plate, views=("top", "front"))
        with self.assertRaisesRegex(ValueError, r"top.symmetric\('v'\): the part is not symmetric"):
            top.symmetric("v")
        top.symmetric("h")                                 # on the X axis: its mirror across Y is itself
        pair = plate - Pos(-30, 0, 0) * Cylinder(1, 10, align=up)
        self.assertTrue(mirror_symmetric(pair, 0), "the hole's mirror image added: symmetric")

    def test_the_symmetry_line_runs_through_the_parts_middle_on_a_broken_view(self) -> None:
        from build123d import Align, Box, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        bar = Box(300, 30, 10, align=up) - Pos(-140, 0, 0) * Cylinder(3, 10, align=up) \
            - Pos(140, 0, 0) * Cylinder(3, 10, align=up)
        sheet = Sheet("A3", 1.0)
        top, _front = sheet.three_views(bar, views=("top", "front"))
        top.broken((20, 0, 10), (120, 0, 10))              # off the middle: the view's box is not centred on it
        top.symmetric("v")
        msp = _render_sheet(sheet, index=1, count=1, label="bar", warnings=[]).modelspace()
        holes = sorted(c.dxf.center.x for c in msp.query("CIRCLE") if abs(c.dxf.radius - 3) < 0.01)
        middle = holes[0] + 140                            # 1:1, and the left hole is short of the break
        (line,) = [e for e in msp.query("LINE[layer=='CENTER']") if abs(e.dxf.start.x - e.dxf.end.x) < 1e-6
                   and abs(e.dxf.start.y - e.dxf.end.y) > 40]
        self.assertAlmostEqual(line.dxf.start.x, middle, places=3)

    def test_stated_symmetry_is_drawn(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet

        sheet, top, _front = self._plate()
        top.symmetric("v")
        msp = _render_sheet(sheet, index=1, count=1, label="sym", warnings=[]).modelspace()
        marks = [e for e in msp.query("LINE[layer=='NOTES']")]
        self.assertEqual(len(marks), 4, "the symmetry symbol, two short strokes at each end of the centre line")
        from cadgen.eng_drawing import Sheet

        bare = Sheet("A3", 1.0)
        plain, _front = bare.three_views(_mounting_plate(), views=("top", "front"))
        plain.symmetric("v")                               # nothing else below the view
        msp = _render_sheet(bare, index=1, count=1, label="sym", warnings=[]).modelspace()
        (label,) = [e for e in msp.query("TEXT") if e.dxf.text == "TOP"]
        x, y = label.dxf.align_point.x, label.dxf.align_point.y
        line = [e for e in msp.query("LINE[layer=='CENTER']") if abs(e.dxf.start.x - x) < 0.5
                and abs(e.dxf.end.x - x) < 0.5 and max(e.dxf.start.y, e.dxf.end.y) > y]
        self.assertTrue(line)
        self.assertLess(y, min(min(e.dxf.start.y, e.dxf.end.y) for e in line),
                        "the view's label hangs below the symmetry line, not through it")
        with self.assertRaisesRegex(ValueError, "'h' or 'v'"):
            top.symmetric("x")

    def test_a_bore_on_a_coned_parts_axis_is_located_by_it(self) -> None:
        from build123d import Align, Cone, Cylinder

        from cadgen.eng_drawing import Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        seat = Cone(29, 36, 6, align=up) - Cylinder(6.5, 6, align=up)   # a spring perch round a rod
        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(seat, views=("top", "front"))
        top.holes()
        front.overall()
        self.assertEqual(self._report(sheet), [], "turned whole, its axis locates its bore")

    def test_a_hole_table_or_a_turned_axis_locates_what_it_holds(self) -> None:
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, _front = sheet.three_views(_mounting_plate(), views=("top", "front"))
        top.hole_table()
        self.assertEqual(self._report(sheet), [], "the table gives every hole's X and Y")
        flange = Sheet("A3", 1.0)
        ftop, _ffront = flange.three_views(_flange(), views=("top", "front"))
        ftop.holes()
        self.assertEqual(self._report(flange), [], "a bolt circle and a bore on a turned part's axis")


def _ramp():
    """A 60 x 40 block profile in XZ: an 8-high base, a slope rising to a 30-high
    top 0..10 along X."""
    from build123d import Plane, Polygon, extrude

    profile = Plane.XZ * Polygon((0, 0), (60, 0), (60, 8), (20, 8), (10, 30), (0, 30), align=None)
    return extrude(profile, amount=-40)


class FaceTests(unittest.TestCase):
    """A step is somewhere and a slope is at some angle only when a dimension says so."""

    def _report(self, sheet, words: str = "face") -> list[str]:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated

        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="faces", warnings=[], facts=facts)
        return [line for line in _unstated(facts) if words in line]

    def _sheet(self):
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(_ramp(), views=("top", "front"))
        top.overall()
        front.overall(width=False)
        return sheet, top, front

    def test_an_unplaced_step_and_an_unstated_slope_are_reported(self) -> None:
        sheet, _top, _front = self._sheet()
        lines = self._report(sheet)
        self.assertTrue(any("at Z = 8" in line and "front." in line for line in lines), lines)
        self.assertTrue(any("inclined face" in line and "front.angle(" in line for line in lines), lines)

    def test_an_angle_is_the_one_between_its_legs_in_either_order(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        for legs in (((60, 0, 8), (10, 0, 30)), ((10, 0, 30), (60, 0, 8))):
            sheet = Sheet("A3", 1.0)
            _top, front = sheet.three_views(_ramp(), views=("top", "front"))
            front.angle((20, 0, 8), *legs)
            doc = _render_sheet(sheet, index=1, count=1, label="angle", warnings=[])
            self.assertEqual(_dim_texts(doc), ["114.44°"], "never the reflex angle outside the legs")

    def test_an_aligned_dimension_measures_along_an_inclined_edge(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        _top, front = sheet.three_views(_ramp(), views=("top", "front"))
        front.dim((20, 0, 8), (10, 0, 30), orientation="aligned", tol=0.1)   # the slope's true length
        warnings: list[str] = []
        doc = _render_sheet(sheet, index=1, count=1, label="aligned", warnings=warnings)
        (value,) = _dim_texts(doc)
        self.assertTrue(value.startswith("\\A0;24.17") and "±0.1" in value,
                        f"√(10² + 22²), not its width or height on the sheet: {value!r}")
        line = next(iter(doc.modelspace().query("DIMENSION")))
        self.assertAlmostEqual(abs(math.tan(math.radians(line.dxf.angle))), 2.2, places=6, msg="along the slope")
        self.assertFalse([w for w in warnings if "guessed" in w], warnings)
        with self.assertRaisesRegex(ValueError, "aligned dimension takes no frame"):
            front.dim((20, 0, 8), (10, 0, 30), orientation="aligned", key=True)

    def test_many_unstated_slopes_on_one_part_make_one_line(self) -> None:
        from build123d import RegularPolygon, extrude

        from cadgen.eng_drawing import Sheet

        bar = extrude(RegularPolygon(20, 8), amount=10)    # an octagon on its corners: every side leans
        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(bar, views=("top", "front"))
        top.overall()
        front.overall(width=False)
        lines = [line for line in self._report(sheet) if "inclined" in line]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("8 inclined faces", lines[0])
        self.assertIn("top.angle(", lines[0])

    def test_one_side_of_a_part_stated_symmetric_places_the_other(self) -> None:
        from build123d import Align, Box, Pos

        from cadgen.eng_drawing import Sheet

        tray = Box(60, 40, 10, align=(Align.CENTER, Align.CENTER, Align.MIN)) \
            - Pos(0, 0, 5) * Box(50, 30, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))
        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(tray, views=("top", "front"))
        top.overall()
        front.overall(width=False)
        top.dim((-30, 0, 10), (-25, 0, 10))                # the left wall
        top.dim((0, -20, 10), (0, -15, 10))                # the front wall
        front.dim((30, 0, 10), (30, 0, 5))                 # the pocket's depth
        self.assertEqual(sorted(line.split(" (")[0] for line in self._report(sheet)),
                         ["incomplete: the face at X = 25", "incomplete: the face at Y = 15"])
        top.symmetric("h")
        top.symmetric("v")                                 # the right and back walls mirror them
        self.assertEqual(self._report(sheet), [])

    def test_a_size_a_slope_fixes_may_be_given_as_reference(self) -> None:
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(_ramp(), views=("top", "front"))
        top.overall(width=False)
        front.overall(reference=True)                      # the 60 and the 30 follow from the rest
        front.dim((0, 0, 30), (10, 0, 30))                 # the top's width
        front.dim((60, 0, 8), (20, 0, 8))                  # the slope's foot from the right
        front.dim((60, 0, 0), (60, 0, 8))
        front.angle((20, 0, 8), (60, 0, 8), (10, 0, 30))
        self.assertEqual(len(self._report(sheet, "only as a reference")), 2,
                         "an angle alone gives the slope's direction, not its length")
        front.dim((20, 0, 8), (10, 0, 30), orientation="aligned")   # its length: now its run and rise follow
        self.assertEqual(self._report(sheet, "overall size"), [])

    def test_an_angle_somewhere_does_not_excuse_a_reference_size(self) -> None:
        from build123d import Polygon, extrude

        from cadgen.eng_drawing import Sheet

        plate = extrude(Polygon((-50, -30), (50, -30), (50, 20), (40, 30), (-50, 30), align=None), 10)
        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(plate, views=("top", "front"))
        top.overall(reference=True)
        front.overall(width=False)
        top.dim((50, 20, 10), (50, 30, 10))                # the corner cut's leg
        top.angle((40, 30, 10), (-50, 30, 10), (50, 20, 10))
        self.assertEqual(len(self._report(sheet, "only as a reference")), 2,
                         "a 45° corner cut fixes neither the 100 nor the 60")

    def test_an_aligned_dimension_on_a_broken_view_states_its_true_length(self) -> None:
        from build123d import Plane, Polygon, extrude

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        bar = extrude(Plane.XZ * Polygon((0, 0), (290, 0), (300, 20), (0, 20), align=None), amount=-20)
        sheet = Sheet("A3", 1.0)
        _top, front = sheet.three_views(bar, views=("top", "front"))
        front.broken((50, 0, 10), (250, 0, 10))
        front.dim((290, 0, 0), (300, 0, 20), orientation="aligned")    # the bevel, beyond the break
        doc = _render_sheet(sheet, index=1, count=1, label="bevel", warnings=[])
        self.assertEqual(_dim_texts(doc), ["22.36"], "√(10² + 20²), not the bevel's rise")
        front.dim((0, 0, 0), (300, 0, 20), orientation="aligned")      # inclined across the break: the wrong angle
        with self.assertRaisesRegex(ValueError, "aligned.*break"):
            _render_sheet(sheet, index=1, count=1, label="bevel", warnings=[])

    def test_a_height_and_an_angle_state_them(self) -> None:
        sheet, _top, front = self._sheet()
        front.dim((60, 0, 0), (60, 0, 8))
        front.angle((20, 0, 8), (60, 0, 8), (10, 0, 30))
        self.assertEqual(self._report(sheet), [])

    def test_a_slope_placed_by_its_ends_needs_no_angle(self) -> None:
        sheet, _top, front = self._sheet()
        front.dim((60, 0, 0), (60, 0, 8))
        front.dim((60, 0, 8), (20, 0, 8))                  # the slope's foot from the right edge
        front.dim((0, 0, 30), (10, 0, 30))                 # and its head from the left
        self.assertEqual(self._report(sheet), [], "both ends placed: the slope is defined")

    def test_a_slots_walls_are_the_slots(self) -> None:
        from build123d import Align, Box, Pos, SlotCenterToCenter, extrude

        from cadgen.eng_drawing import Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        plate = Box(80, 50, 6, align=up) - Pos(20, 0, 0) * extrude(SlotCenterToCenter(16, 8), 6)
        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(plate, views=("top", "front"))
        top.overall()
        front.overall(width=False)
        top.holes()
        top.dim((40, 0, 6), (20, 0, 6))
        top.symmetric("h")
        self.assertEqual(self._report(sheet), [], "its width and centre place its walls")

    def test_the_faces_a_hole_or_a_chamfer_owns_ask_nothing(self) -> None:
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front, _right = sheet.three_views(_counterbored())
        top.overall()
        front.overall(width=False)
        top.holes()
        self.assertFalse([line for line in self._report(sheet) if "Z =" in line], "the counterbore's floor is the hole's")


def _spigot():
    """A turned part along Z: a ⌀30 x 40 body, a taper from ⌀30 down to ⌀20 over
    20, and an R1.5 groove round the body 12 from its foot."""
    from build123d import Align, Cone, Cylinder, Pos, Torus

    up = (Align.CENTER, Align.CENTER, Align.MIN)
    body = Cylinder(15, 40, align=up) + Pos(0, 0, 40) * Cone(15, 10, 20, align=up)
    return body - Pos(0, 0, 12) * Torus(15, 1.5)


class TurnedShapeTests(unittest.TestCase):
    """A taper has two ends and a groove a size and a place; a drawing states both."""

    def test_a_tapers_small_end_and_a_groove_are_reported_until_stated(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(_spigot(), views=("top", "front"))
        front.overall()
        front.dim((0, 15, 0), (0, -15, 0), text="%%c<>")
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="spigot", warnings=[], facts=facts)
        lines = _unstated(facts)
        self.assertTrue(any("taper" in line and "⌀20" in line for line in lines), lines)
        self.assertTrue(any("groove" in line and "R1.5" in line for line in lines), lines)

    def test_a_taper_and_groove_stated_leave_nothing_reported(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(_spigot(), views=("top", "front"))
        front.overall()
        front.dim((15, 0, 20), (-15, 0, 20), text="%%c<>")
        front.dim((10, 0, 60), (-10, 0, 60), text="%%c<>")
        front.dim((15, 0, 0), (15, 0, 40))
        front.dim((-15, 0, 0), (-15, 0, 12))
        # The groove's outline on this side is the hidden-line pass's spline, not
        # a circle: the callout finds it all the same.
        front.radius((-15, 0, 12))
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="spigot", warnings=[], facts=facts)
        self.assertEqual([line for line in _unstated(facts) if "taper" in line or "groove" in line], [])

    def test_a_first_pass_leaves_a_counterbores_floor_to_its_callout(self) -> None:
        from build123d import Align, Box, Compound, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import assembly_sheets, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        tube = Cylinder(15, 120, align=up) - Pos(0, 0, 90) * Cylinder(10, 30, align=up) - Cylinder(6, 120, align=up)
        base = Pos(0, 0, -5) * Box(60, 60, 5, align=up)
        tube.label, base.label = "tube", "base"
        sheets = assembly_sheets(parts_list(Compound(children=[tube, base])), title="TUBE")
        facts = _facts()
        doc = _render_sheet(sheets.part("tube"), index=2, count=3, label="tube", warnings=[], facts=facts)
        self.assertNotIn("90", _dim_texts(doc), "the floor is the callout's ↧30, not a second statement of it")
        self.assertEqual(_unstated(facts), [])

    def test_a_cross_drilled_pins_first_pass_is_a_turned_parts(self) -> None:
        from build123d import Align, Box, Compound, Cylinder, Pos, Rot

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import assembly_sheets, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        pin = Cylinder(6, 80, align=up) + Pos(0, 0, 80) * Cylinder(4, 20, align=up) \
            - Pos(0, 0, 70) * Rot(0, 90, 0) * Cylinder(1, 20)              # a cotter hole across it
        base = Pos(0, 0, -5) * Box(60, 60, 5, align=up)
        pin.label, base.label = "pin", "base"
        sheets = assembly_sheets(parts_list(Compound(children=[pin, base])), title="PIN")
        facts = _facts()
        doc = _render_sheet(sheets.part("pin"), index=2, count=3, label="pin", warnings=[], facts=facts)
        self.assertEqual(_unstated(facts), [], "its diameters, its shoulder and the cotter hole's place")
        self.assertIn("8", _dim_texts(doc), "the ⌀8 step, as a turned part states it")

    def test_a_first_pass_sheet_states_a_turned_parts_shape(self) -> None:
        from build123d import Align, Box, Compound, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import assembly_sheets, parts_list

        spigot, base = _spigot(), Pos(0, 0, -5) * Box(60, 60, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))
        spigot.label, base.label = "spigot", "base"
        sheets = assembly_sheets(parts_list(Compound(children=[spigot, base])), title="SPIGOT")
        facts = _facts()
        _render_sheet(sheets.part("spigot"), index=2, count=3, label="spigot", warnings=[], facts=facts)
        self.assertEqual(_unstated(facts), [], "diameters, the taper's ends, the groove and every step placed")


class RedundancyTests(unittest.TestCase):
    """A size the other dimensions already fix is stated twice: a shop meets two
    requirements on one size, and their tolerances cannot both hold."""

    @staticmethod
    def _plate_lines(**last) -> list[str]:
        from build123d import Align, Box

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _redundant
        from cadgen.eng_drawing import GENERIC, Frame, Sheet

        sheet = Sheet("A3", 1.0, profile=GENERIC)
        top, front = sheet.three_views(Box(60, 40, 8, align=(Align.MIN, Align.MIN, Align.MIN)),
                                       views=("top", "front"))
        front.overall()
        front.dim((0, 0, 8), (20, 0, 8))
        front.dim((20, 0, 8), (60, 0, 8), **last)
        if last.get("basic"):
            top.frame((30, 20, 8), Frame("flatness", 0.05))  # what bounds a basic one
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="plate", warnings=[], facts=facts)
        return _redundant(facts)

    def test_a_chain_that_adds_up_to_the_overall_size_is_reported(self) -> None:
        lines = self._plate_lines()
        self.assertEqual(len(lines), 1, lines)
        self.assertTrue(lines[0].startswith("redundant:") and "along X" in lines[0] and "40" in lines[0], lines)

    def test_a_reference_or_basic_dimension_closes_no_loop(self) -> None:
        self.assertEqual(self._plate_lines(reference=True), [])
        self.assertEqual(self._plate_lines(basic=True), [])

    def test_two_hole_pairs_at_one_spacing_are_two_sizes(self) -> None:
        from build123d import Align, Box, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _redundant
        from cadgen.eng_drawing import Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        plate = Box(80, 50, 8, align=up)
        for x in (-25, 25):
            for y in (-12, 12):
                plate -= Pos(x, y, 0) * Cylinder(3, 8, align=up)
        sheet = Sheet("A3", 1.0)
        top, _front = sheet.three_views(plate, views=("top", "front"))
        top.holes()
        top.dim((-25, -12, 8), (25, -12, 8))               # the front pair's spacing
        top.dim((-25, 12, 8), (25, 12, 8))                 # the back pair's: another size, at the same X
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="pairs", warnings=[], facts=facts)
        self.assertEqual(_redundant(facts), [])
        top.dim((-40, -12, 8), (-25, -12, 8))
        top.dim((-40, -12, 8), (25, -12, 8))               # with the spacing, one size twice
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="pairs", warnings=[], facts=facts)
        self.assertEqual(len(_redundant(facts)), 1)

    def test_two_bosses_of_one_height_are_two_sizes(self) -> None:
        from build123d import Align, Box, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _redundant
        from cadgen.eng_drawing import Sheet

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        part = Box(100, 40, 10, align=up) + Pos(-35, 0, 10) * Box(20, 40, 10, align=up) \
            + Pos(35, 0, 10) * Box(20, 40, 10, align=up)

        def lines(*more):
            sheet = Sheet("A3", 1.0)
            _top, front = sheet.three_views(part, views=("top", "front"))
            front.dim((-45, 0, 10), (-45, 0, 20), orientation="v")     # the left boss's height
            front.dim((45, 0, 10), (45, 0, 20), orientation="v")       # the right one's: another feature
            for call in more:
                call(front)
            facts = _facts()
            _render_sheet(sheet, index=1, count=1, label="bosses", warnings=[], facts=facts)
            return _redundant(facts)

        self.assertEqual(lines(), [], "their tops are coplanar, but each boss's height is its own size")
        closed = lines(lambda v: v.dim((-50, 0, 0), (-50, 0, 10)), lambda v: v.overall(width=False))
        self.assertEqual(len(closed), 1, closed)
        self.assertIn("front overall", closed[0], "the base and a boss add up to the overall height")
        self.assertNotIn("front dim 1", closed[0], "the right boss stands on its own")

    def test_two_steps_of_one_diameter_are_two_sizes(self) -> None:
        from build123d import Align, Cylinder, Pos, Rot

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _redundant
        from cadgen.eng_drawing import Sheet

        up, along_x = (Align.CENTER, Align.CENTER, Align.MIN), Rot(0, 90, 0)
        shaft = (along_x * Cylinder(10, 30, align=up) + Pos(30, 0, 0) * along_x * Cylinder(15, 60, align=up)
                 + Pos(90, 0, 0) * along_x * Cylinder(10, 30, align=up))
        sheet = Sheet("A3", 1.0)
        _top, front = sheet.three_views(shaft, views=("top", "front"))
        front.dim((15, 0, -10), (15, 0, 10), text="%%c<>")
        front.dim((105, 0, -10), (105, 0, 10), text="%%c<>")   # the other end: another ⌀20
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="shaft", warnings=[], facts=facts)
        self.assertEqual(_redundant(facts), [])

    def test_an_overall_size_the_chain_fixes_is_stated_as_reference(self) -> None:
        from build123d import Align, Box

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _redundant, _unstated
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front = sheet.three_views(Box(60, 40, 8, align=(Align.MIN, Align.MIN, Align.MIN)),
                                       views=("top", "front"))
        front.overall(reference=True)                      # (60) and (8): information
        front.dim((0, 0, 8), (20, 0, 8))
        front.dim((20, 0, 8), (60, 0, 8))
        front.dim((60, 0, 0), (60, 0, 8))
        top.overall(width=False)
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="plate", warnings=[], facts=facts)
        self.assertEqual(_redundant(facts), [])
        self.assertFalse([line for line in _unstated(facts) if "overall size" in line],
                         "a reference size tells the shop the stock: the size is on the drawing")


class InterfaceTests(unittest.TestCase):
    """Where two parts meet, the drawing set must say how: a pin in a bore at one
    nominal size is a fit nobody has chosen, and faces that touch leave no end play."""

    @staticmethod
    def _lines(sleeve_bore: float = 12.0) -> list[str]:
        from build123d import Align, Box, Compound, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _interfaces
        from cadgen.eng_drawing import assembly_sheets, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        plate = Box(60, 40, 8, align=up) - Pos(-15, 0, 0) * Cylinder(6, 8, align=up) \
            - Pos(15, 0, 0) * Cylinder(10, 8, align=up)
        # A headed pin through the left bore, its head down on the plate; a sleeve
        # in the right bore; a rod far smaller than the hole it stands in.
        pin = Pos(-15, 0, -4) * (Cylinder(6, 12, align=up) + Pos(0, 0, 12) * Cylinder(9, 3, align=up))
        sleeve = Pos(15, 0, -2) * (Cylinder(9.9, 12, align=up) - Cylinder(sleeve_bore / 2, 12, align=up))
        rod = Pos(15, 0, -6) * Cylinder(2, 20, align=up)
        plate.label, pin.label, sleeve.label, rod.label = "plate", "pin", "sleeve", "rod"
        sheets = assembly_sheets(parts_list(Compound(children=[plate, pin, sleeve, rod])), title="RIG")
        facts = _facts()
        _render_sheet(list(sheets)[0], index=1, count=1, label="rig", warnings=[], facts=facts)
        return _interfaces(facts)

    def test_a_pin_in_a_bore_of_its_own_size_and_faces_that_touch_are_named(self) -> None:
        lines = self._lines()
        fits = [line for line in lines if "PIN" in line and "PLATE" in line and "⌀12" in line]
        self.assertEqual(len(fits), 1, lines)
        self.assertIn("no clearance", fits[0])
        touching = [line for line in lines if "touch" in line and "PIN" in line and "PLATE" in line]
        self.assertEqual(len(touching), 1, lines)
        self.assertIn("end play", touching[0])

    def test_a_sleeve_with_clearance_says_how_much_and_a_loose_rod_is_no_fit(self) -> None:
        lines = self._lines()
        sleeve = [line for line in lines if "SLEEVE" in line and "PLATE" in line]
        self.assertEqual(len(sleeve), 1, lines)
        self.assertIn("0.2 clearance", sleeve[0])
        self.assertFalse([line for line in lines if "ROD" in line], "⌀4 in a ⌀12 bore is a gap, not a fit")

    def test_one_part_used_four_times_is_one_joint(self) -> None:
        from build123d import Align, Box, Compound, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _interfaces
        from cadgen.eng_drawing import assembly_sheets, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        corners = [(x, y) for x in (-30, 30) for y in (-20, 20)]
        plate = Box(80, 60, 6, align=up)
        for x, y in corners:
            plate -= Pos(x, y, 0) * Cylinder(3.2, 6, align=up)
        plate.label = "plate"
        bolts = []
        for x, y in corners:
            bolt = Pos(x, y, -4) * (Cylinder(3, 10, align=up) + Pos(0, 0, 10) * Cylinder(5, 3, align=up))
            bolt.label = "bolt"
            bolts.append(bolt)
        sheets = assembly_sheets(parts_list(Compound(children=[plate, *bolts])), title="PLATE")
        facts = _facts()
        _render_sheet(list(sheets)[0], index=1, count=1, label="plate", warnings=[], facts=facts)
        lines = _interfaces(facts)
        self.assertEqual(len([line for line in lines if "touch" in line]), 1, lines)
        self.assertEqual(len([line for line in lines if "in item" in line]), 1, lines)
        self.assertTrue(all("4 places" in line for line in lines), lines)

    def test_a_rod_running_in_a_looser_bore_is_a_joint(self) -> None:
        from build123d import Align, Box, Compound, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _interfaces
        from cadgen.eng_drawing import assembly_sheets, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        guide = Box(40, 40, 10, align=up) - Cylinder(6.5, 10, align=up)   # a ⌀13 guide
        rod = Pos(0, 0, -20) * Cylinder(6, 60, align=up)                   # a ⌀12 rod that strokes through it
        guide.label, rod.label = "guide", "rod"
        sheets = assembly_sheets(parts_list(Compound(children=[guide, rod])), title="GUIDE")
        facts = _facts()
        _render_sheet(list(sheets)[0], index=1, count=1, label="guide", warnings=[], facts=facts)
        lines = _interfaces(facts)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("1 clearance", lines[0])

    def test_an_interference_is_called_out(self) -> None:
        lines = self._lines()
        self.assertTrue(all(line.startswith("interface:") for line in lines), lines)
        squeezed = self._lines(sleeve_bore=3.9)
        self.assertTrue([line for line in squeezed if "ROD" in line and "interference" in line], squeezed)


class AssemblySetReviewTests(unittest.TestCase):
    """Plausible-wrong parts lists, flags and interface counts the second review found."""

    def test_two_materials_are_two_parts(self) -> None:
        from bd_materials import metals
        from build123d import Box, Compound, Pos

        from cadgen.eng_drawing import parts_list

        grades = list(metals.MildSteel)
        a, b = Box(10, 10, 10), Pos(30, 0, 0) * Box(10, 10, 10)
        a.label = b.label = "spacer"
        a.material, b.material = metals.mild_steel(grades[0]), metals.mild_steel(grades[-1])
        parts = parts_list(Compound(children=[a, b]))
        self.assertEqual([(item.description, item.quantity) for item in parts], [("SPACER", 1), ("SPACER", 1)],
                         "alike to the eye, two grades of steel")
        self.assertEqual(parts.twins, ((1, 2),))
        with self.assertRaisesRegex(ValueError, "is not made of what item 1 .* is, in the model"):
            parts.merge(1, 2)

    def test_merge_keeps_what_set_stated_or_refuses(self) -> None:
        from build123d import Box, Compound, Pos

        from cadgen.eng_drawing import parts_list

        def eyes():
            shapes = [Pos(30 * k, 0, 0) * Box(10, 10, 10) for k in range(3)]
            for shape, label in zip(shapes, ("eye:lower", "eye:upper", "eye:middle")):
                shape.label = label
            return parts_list(Compound(children=shapes))

        parts = eyes().set(1, part_number="PN-100", material="STEEL").set(2, part_number="PN-200", material="BRASS")
        with self.assertRaisesRegex(ValueError, r"differ in part_number \(item 1 'PN-100', item 2 'PN-200'\)"):
            parts.merge(1, 2)
        parts = eyes().set(1, part_number="PN-100").set(2, material="STEEL")
        parts.merge(1, 2)
        self.assertEqual([(i.number, i.quantity, i.part_number, i.material) for i in parts],
                         [(1, 2, "PN-100", "STEEL"), (2, 1, "", "")], "one statement each is kept, not dropped")

    def test_a_flag_on_a_section_points_into_its_items_cut(self) -> None:
        from build123d import Align, Box, Compound, Cylinder

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet, parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        housing = Box(60, 40, 40, align=up) - Cylinder(10, 40, align=up)
        sleeve = Cylinder(10, 55, align=up) - Cylinder(6, 55, align=up)
        rod = Cylinder(6, 60, align=up)
        housing.label, sleeve.label, rod.label = "housing", "sleeve", "rod"
        parts = parts_list(Compound(children=[housing, sleeve, rod], label="rig"))
        sheet = Sheet("A3", 2.0)
        front = sheet.view(parts.assembly, "front", at=(150, 100), hidden=False).section("A", parts=parts)
        sheet.view(parts.assembly, "top", at=(150, 240), hidden=False)    # where the plane is shown
        front.balloons(parts)
        front.flag("BOND SLEEVE", item="sleeve")
        doc = _render_sheet(sheet, index=1, count=1, label="flag")
        keyed = {number: point for number, _centre, point in _balloons(doc)}
        starts = [(leader.vertices[0].x, leader.vertices[0].y) for leader in doc.modelspace().query("LEADER")]
        self.assertTrue(any(math.dist(start, keyed[parts["sleeve"].number]) < 1e-6 for start in starts),
                        "the flag's leader starts where the sleeve's balloon keys its cut, not on the half cut away")

    def test_interfaces_count_each_contact(self) -> None:
        from build123d import Align, Box, Compound, Cylinder, Pos

        from cadgen._internal.drawing_assembly import interfaces
        from cadgen.eng_drawing import parts_list

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        housing = Box(40, 40, 60, align=up) - Cylinder(8, 60, align=up)
        bushings = [Pos(0, 0, z) * (Cylinder(8, 15, align=up) - Cylinder(5, 15, align=up)) for z in (0, 45)]
        shaft = Pos(0, 0, -5) * Cylinder(4.95, 70, align=up)
        housing.label, shaft.label = "housing", "shaft"
        for bushing in bushings:
            bushing.label = "bushing"
        fits, _abutments = interfaces(parts_list(Compound(children=[housing, *bushings, shaft])))
        self.assertEqual(sorted((f.inner, f.outer, f.places) for f in fits), [(2, 1, 2), (3, 2, 2)],
                         "two bushings in one bore are two places, and the shaft runs in both")
        plates = [Pos(0, 0, z) * Box(80, 50, 6, align=up) for z in (0, 6)]
        spots = ((-30, -15), (30, -15), (-30, 15), (30, 15))
        for k, plate in enumerate(plates):
            for x, y in spots:
                plates[k] = plates[k] - Pos(x, y, 6 * k) * Cylinder(3, 6, align=up)
        plates[0].label, plates[1].label = "bottom_plate", "top_plate"
        pins = [Pos(x, y, 0) * Cylinder(2.9, 20, align=up) for x, y in spots]
        for pin in pins:
            pin.label = "pin"
        fits, abutments = interfaces(parts_list(Compound(children=[*plates, *pins])))
        self.assertEqual(sorted(f.places for f in fits), [4, 4], "four pins in each plate")
        self.assertEqual([(a.items, a.places) for a in abutments], [((1, 2), 1)],
                         "the plates touch once, however many pin axes cross where they do")


class HoleTableTests(unittest.TestCase):
    def test_a_hole_table_tags_each_hole_and_states_where_and_what(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A2", 1.0)
        top, _front, _right = sheet.three_views(_perforated())
        top.hole_table()
        facts = _facts()
        doc = _render_sheet(sheet, index=1, count=1, label="table", facts=facts)
        texts = [e.dxf.text for e in doc.modelspace().query("TEXT")]
        for tag in ("A1", "B1", "B2", "C1", "C10", "D1"):
            self.assertEqual(texts.count(tag), 2, f"{tag} tags its hole and heads its row")
        cells = {e.dxf.text for e in doc.modelspace().query("TEXT[layer=='NOTES']")}
        self.assertTrue({"24 THRU", "10 THRU", "6 THRU", "8 × 24 SLOT THRU"} <= cells, cells)
        # Positions from the lower-left corner: the bore is at the plate's middle.
        self.assertTrue({"80", "50", "140"} <= set(texts))
        from cadgen._internal.drawing_report import _requirements, _unstated

        self.assertFalse([line for line in _unstated(facts) if "called out" in line], "the table states each hole")
        (required,) = _requirements(facts)
        self.assertIn("10× ⌀6 THRU", required, "tabulated holes counted, as a reader reads them")
        self.assertNotIn("%%c", required)

    def test_the_tags_and_the_origin_stand_clear_of_the_line_work(self) -> None:
        import re

        from ezdxf import path
        from shapely.geometry import LineString, box

        from cadgen._internal.drawing_base import _text_box
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A2", 1.0)
        top, _front, _right = sheet.three_views(_perforated())
        top.hole_table()
        msp = _render_sheet(sheet, index=1, count=1, label="tags").modelspace()
        lines = [LineString([(v.x, v.y) for v in path.make_path(e).flattening(0.05)])
                 for e in msp.query("LINE ARC CIRCLE LWPOLYLINE SPLINE ELLIPSE[layer=='VISIBLE' | layer=='CENTER']")]
        tags = [e for e in msp.query("TEXT[layer=='DIM']") if re.fullmatch(r"[A-Z]\d+|X|Y|0,0", e.dxf.text)]
        self.assertEqual(len(tags), 17)  # A1, B1-B2, C1-C10, D1, and the origin's X, Y and 0,0
        for tag in tags:
            align, at, _end = tag.get_placement()
            ink = box(*_text_box(tag.dxf.text, at.x, at.y, tag.dxf.height, align))
            self.assertFalse([line for line in lines if line.intersects(ink)], f"{tag.dxf.text} is printed on line work")

    def test_a_hole_table_and_callouts_do_not_share_a_view(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A2", 1.0)
        top, front, _right = sheet.three_views(_perforated())
        top.hole_table()
        top.holes()
        with self.assertRaisesRegex(ValueError, "both tabulates"):
            _render_sheet(sheet, index=1, count=1, label="both")
        sheet = Sheet("A2", 1.0)
        _top, front, _right = sheet.three_views(_perforated())
        front.hole_table()
        with self.assertRaisesRegex(ValueError, "looks down no hole"):
            _render_sheet(sheet, index=1, count=1, label="none")

    def test_a_hole_table_on_a_broken_view_measures_the_part_and_refuses_a_hole_in_the_break(self) -> None:
        from build123d import Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A0", 1.0)  # no tag reads A0, so the size cell cannot be counted as one
        top, front, _right = sheet.three_views(_bar())
        front.broken((100, 0, 0), (500, 0, 0))
        top.hole_table()
        texts = [e.dxf.text for e in _render_sheet(sheet, index=1, count=1, label="broken").modelspace().query("TEXT")]
        self.assertIn("580", texts, "X is measured on the whole bar, not on the shortened drawing")
        self.assertEqual((texts.count("A1"), texts.count("A2"), texts.count("A3")), (2, 2, 0))
        # A hole in the stretch the break takes out would be neither drawn nor
        # listed: the drawing would say the bar has two.
        sheet = Sheet("A0", 1.0)
        top, front, _right = sheet.three_views(_bar() - Pos(300, 0, 0) * Cylinder(3, 40))
        front.broken((100, 0, 0), (500, 0, 0))
        top.hole_table()
        with self.assertRaisesRegex(ValueError, "hides some of the part"):
            _render_sheet(sheet, index=1, count=1, label="hidden")

    def test_a_hole_table_placed_by_hand_must_be_on_the_paper(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A2", 1.0)
        top, _front, _right = sheet.three_views(_perforated())
        top.hole_table(at=(800, 900))
        with self.assertRaisesRegex(ValueError, "runs off"):
            _render_sheet(sheet, index=1, count=1, label="off")
        sheet = Sheet("A2", 1.0, revisions=[("A", "2026-10-01", "FIRST ISSUE")])
        top, _front, _right = sheet.three_views(_perforated())
        top.hole_table(at=(480, 405))  # under the revision table, top right
        with self.assertRaisesRegex(ValueError, "revision table"):
            _render_sheet(sheet, index=1, count=1, label="revisions")


class EdgeNoteTests(unittest.TestCase):
    """Fillets, rounds and chamfers: read off the part, stated by a general note
    only where the note is true."""

    def _block(self, *, chamfer_bottom: bool):
        from build123d import Align, Axis, Box, chamfer, fillet

        block = Box(60, 40, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
        block = fillet(block.edges().filter_by(Axis.Z), 5)
        block = chamfer(block.edges().group_by(Axis.Z)[-1], 1)
        return chamfer(block.edges().group_by(Axis.Z)[0], 1) if chamfer_bottom else block

    def test_a_general_note_is_written_only_when_no_edge_of_its_kind_is_left_sharp(self) -> None:
        from build123d import Align, Axis, Box, Pos, fillet

        from cadgen.eng_drawing import geometry_notes

        self.assertEqual(geometry_notes(self._block(chamfer_bottom=True)),
                         ["CHAMFERS 1 × 45° UNLESS OTHERWISE SPECIFIED."], "every outside edge is broken")
        self.assertEqual(geometry_notes(self._block(chamfer_bottom=False)), [],
                         "the bottom edges are sharp, so no note may govern the outside edges")
        up = (Align.CENTER, Align.CENTER, Align.MIN)
        pocket = Box(80, 50, 15, align=up) - Pos(0, 0, 5) * Box(40, 20, 10, align=up)
        inside = [e for e in pocket.edges() if abs(e.center().X) <= 20 + 1e-6 and abs(e.center().Y) <= 10 + 1e-6
                  and 5 - 1e-6 <= e.center().Z < 15 - 1e-6]
        self.assertEqual(geometry_notes(fillet(inside, 3)), ["FILLETS R3 UNLESS OTHERWISE SPECIFIED."])
        walls_only = fillet(pocket.edges().filter_by(Axis.Z).group_by(lambda e: abs(e.center().X))[0], 3)
        self.assertEqual(geometry_notes(walls_only), [], "the pocket's floor corners are sharp")

    def test_unstated_blends_and_chamfers_are_reported_until_stated(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import Sheet, geometry_notes

        part = self._block(chamfer_bottom=True)
        for notes, corner_radius, expected in (((), False, 2), (geometry_notes(part), False, 1),
                                               (geometry_notes(part), True, 0)):
            sheet = Sheet("A3", notes=list(notes))
            top, front, _right = sheet.three_views(part)
            top.overall()
            front.overall(width=False)
            if corner_radius:
                top.radius((25, 15, 20), size=5)
            facts = _facts()
            _render_sheet(sheet, index=1, count=1, label="edges", facts=facts)
            lines = [line for line in _unstated(facts) if "round" in line or "chamfer" in line]
            self.assertEqual(len(lines), expected, lines)
        sheet = Sheet("A3", notes=["CHAMFERS 0.1 × 45° UNLESS OTHERWISE SPECIFIED."])
        sheet.three_views(part)
        facts = _facts()
        _render_sheet(sheet, index=1, count=1, label="edges", facts=facts)
        self.assertTrue(any("chamfers 1 × 45°" in line for line in _unstated(facts)), "0.1 × 45° is not 1 × 45°")


class AuxiliaryViewTests(unittest.TestCase):
    def test_an_auxiliary_view_shows_an_inclined_face_true_and_calls_out_its_hole(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        part, point = _inclined()
        sheet = Sheet("A3", 1.0)
        _top, front, _right = sheet.three_views(part)
        view = sheet.auxiliary(front, point)
        view.holes()
        doc = _render_sheet(sheet, index=1, count=1, label="aux")
        self.assertIn("%%c10 THRU", _callouts(doc))
        notes = [e.dxf.text for e in doc.modelspace().query("TEXT[layer=='NOTES']")]
        self.assertIn("VIEW C", notes)
        self.assertIn("C", notes, "the parent view's arrow carries the letter")

    def test_an_auxiliary_view_needs_an_inclined_flat_face(self) -> None:
        from cadgen.eng_drawing import Sheet

        part, point = _inclined()
        sheet = Sheet("A3", 1.0)
        top, front, _right = sheet.three_views(part)
        with self.assertRaisesRegex(ValueError, "faces the top view"):
            sheet.auxiliary(front, (0, 0, 8))
        with self.assertRaisesRegex(ValueError, "no flat face"):
            sheet.auxiliary(front, (0, 0, 100))
        view = sheet.auxiliary(front, point)
        with self.assertRaisesRegex(ValueError, "drawn whole"):
            view.section("A")

    def test_an_auxiliary_view_projects_from_a_view_that_sees_the_face_edge_on(self) -> None:
        from build123d import Box, Plane

        from cadgen.eng_drawing import Sheet

        corner = Box(40, 40, 40).split(Plane((10, -10, 10), z_dir=(1, -1, 1)))
        sheet = Sheet("A3", 1.0)
        _top, front, _right = sheet.three_views(corner)
        with self.assertRaisesRegex(ValueError, "not seen edge-on"):
            sheet.auxiliary(front, (10, -10, 10))

    def test_an_auxiliary_views_label_states_a_scale_unlike_the_sheets(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        part, point = _inclined()
        sheet = Sheet("A3", 0.5)
        _top, front, _right = sheet.three_views(part)
        front.scale = 1.0
        view = sheet.auxiliary(front, point)
        _render_sheet(sheet, index=1, count=1, label="label")
        self.assertEqual(view.label, "VIEW C (1:1)")
        view.label = "VIEW C (TAB)"
        _render_sheet(sheet, index=1, count=1, label="label")
        self.assertEqual(view.label, "VIEW C (TAB)", "a label the author set is theirs")

    def test_a_hole_opening_away_from_an_auxiliary_view_names_where_to_call_it_out(self) -> None:
        from build123d import Align, Box, Cylinder, Location, Pos, Rot

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        # The inclined tab with a blind hole drilled from its outer face, which
        # VIEW C, looking at the inner face, sees from behind.
        up = (Align.CENTER, Align.CENTER, Align.MIN)
        tab = Box(8, 50, 40, align=(Align.MAX, Align.CENTER, Align.MIN)) \
            - Pos(-2, 0, 25) * Rot(0, 90, 0) * Cylinder(3, 4)
        part = (Box(80, 50, 8, align=up) + Location((40, 0, 0), (0, 1, 0), 30) * tab).clean()
        sheet = Sheet("A3", 1.0)
        _top, front, _right = sheet.three_views(part)
        view = sheet.auxiliary(front, _inclined()[1])
        hole = Location((40, 0, 0), (0, 1, 0), 30) * Pos(-2, 0, 25)
        view.hole((hole.position.X, hole.position.Y, hole.position.Z))
        with self.assertRaisesRegex(ValueError, "opens on the far side .* a view that looks into it"):
            _render_sheet(sheet, index=1, count=1, label="far")


class BrokenViewTests(unittest.TestCase):
    def test_a_broken_view_draws_both_ends_and_states_true_lengths(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front, _right = sheet.three_views(_bar())
        front.broken((100, 0, 0), (500, 0, 0))
        front.overall()
        front.dim((0, 0, -10), (580, 0, -10))
        doc = _render_sheet(sheet, index=1, count=1, label="broken")
        values = _dim_texts(doc)
        self.assertIn("630", values)
        self.assertIn("580", values)
        zigzags = [e for e in doc.modelspace().query("LWPOLYLINE[layer=='NOTES']") if len(e) == 6]
        self.assertEqual(len(zigzags), 4, "a break line across each end, in both views")

    def test_a_break_where_the_part_changes_is_refused(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        # Drawn, the shortened view reads as one section all along: the shoulder
        # inside the break would be missed by whoever makes the part.
        sheet = Sheet("A3", 1.0)
        _top, front, _right = sheet.three_views(_bar())
        front.broken((10, 0, 0), (500, 0, 0))
        with self.assertRaisesRegex(ValueError, "hides some of the part"):
            _render_sheet(sheet, index=1, count=1, label="hides", warnings=[])
        with self.assertRaisesRegex(ValueError, "hides some of the part"):
            _render_sheet(sheet, index=1, count=1, label="hides")

    def test_a_break_across_a_fork_draws_both_arms(self) -> None:
        from build123d import Box, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        fork = Box(300, 60, 10) - Pos(20, 0, 0) * Box(280, 30, 10)  # the cut crosses two arms
        sheet = Sheet("A3", 1.0)
        top, _front, _right = sheet.three_views(fork)
        top.broken((-50, 0, 0), (50, 0, 0))
        top.overall()
        values = _dim_texts(_render_sheet(sheet, index=1, count=1, label="fork"))
        self.assertIn("300", values)

    def test_a_break_leaves_both_ends_of_the_part(self) -> None:
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        _top, front, _right = sheet.three_views(_bar())
        with self.assertRaisesRegex(ValueError, "leaves both ends"):
            front.broken((-200, 0, 0), (500, 0, 0))
        with self.assertRaisesRegex(ValueError, "leaves both ends"):
            front.broken((100, 0, 0), (2000, 0, 0))

    def test_a_break_needs_a_length_the_view_shows(self) -> None:
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front, right, iso = sheet.three_views(_bar(), iso=True)
        with self.assertRaisesRegex(ValueError, "looks along X"):
            right.broken((100, 0, 0), (500, 0, 0))
        with self.assertRaisesRegex(ValueError, "isometric"):
            iso.broken((100, 0, 0), (500, 0, 0))
        with self.assertRaisesRegex(ValueError, "differ along X and Z"):
            front.broken((100, 0, -10), (500, 0, 10))

    def test_a_section_and_a_break_do_not_share_a_view(self) -> None:
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        top, front, _right = sheet.three_views(_bar())
        front.section("A")
        with self.assertRaisesRegex(ValueError, "is a section"):
            top.broken((100, 0, 0), (500, 0, 0))
        sheet = Sheet("A3", 1.0)
        top, front, _right = sheet.three_views(_bar())
        top.broken((100, 0, 0), (500, 0, 0))
        with self.assertRaisesRegex(ValueError, "broken"):
            front.section("A")

    def test_a_dimension_into_the_break_is_refused(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        _top, front, _right = sheet.three_views(_bar())
        front.broken((100, 0, 0), (500, 0, 0))
        front.dim((0, 0, 10), (300, 0, 10))
        with self.assertRaisesRegex(ValueError, r"front dim 0: \(300, 0, 10\) is inside the break"):
            _render_sheet(sheet, index=1, count=1, label="into", warnings=[])

    def test_a_break_takes_two_points(self) -> None:
        from cadgen.eng_drawing import Sheet

        _top, front, _right = Sheet("A3", 1.0).three_views(_bar())
        with self.assertRaisesRegex(TypeError, r"broken\(\) takes two model points like \(x, y, z\)"):
            front.broken(-5, 5)

    def test_a_hole_inside_the_break_is_refused(self) -> None:
        from build123d import Align, Box, Cylinder, Pos

        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        align = (Align.CENTER, Align.CENTER, Align.MIN)
        plate = Box(400, 40, 10, align=align)
        for x in (-180, 0, 180):
            plate -= Pos(x, 0, 0) * Cylinder(4 if x else 3, 10, align=align)
        sheet = Sheet("A3", 1.0)
        top, _front, _right = sheet.three_views(plate)
        top.broken((-100, 0, 0), (100, 0, 0))   # takes out the middle hole, the only ⌀6
        top.holes()
        # The shortened view would draw a plate with no ⌀6 hole in it.
        with self.assertRaisesRegex(ValueError, "top.broken\\(\\): the break from X = -100 to 100 hides"):
            _render_sheet(sheet, index=1, count=1, label="lost", warnings=[])



class ViewChoiceTests(unittest.TestCase):
    """The views a part needs, and no repeat of one it already has."""

    def test_three_views_draws_only_the_views_asked_for(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        sheet = Sheet("A3", 1.0)
        front, right = sheet.three_views(_shaft(), views=("front", "right"))
        self.assertEqual([v.name for v in sheet.views], ["front", "right"])
        self.assertEqual((front.name, right.name), ("front", "right"))
        labels = [e.dxf.text for e in _render_sheet(sheet, index=1, count=1, label="v").modelspace()
                  .query("TEXT[layer=='NOTES']")]
        self.assertNotIn("TOP", labels)
        self.assertIn("FRONT", labels)

    def test_a_bad_choice_of_views_is_refused(self) -> None:
        from cadgen.eng_drawing import Sheet

        for views in ((), ("front", "front"), ("iso",), ("side",)):
            with self.assertRaisesRegex(ValueError, "views"):
                Sheet("A3", 1.0).three_views(_shaft(), views=views)

    def test_two_views_of_the_same_picture_are_reported(self) -> None:
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen.eng_drawing import Sheet

        warnings: list = []
        sheet = Sheet("A3", 1.0)
        sheet.three_views(_shaft())  # turned about X: the top and front views draw the same lines
        _render_sheet(sheet, index=1, count=1, label="same", warnings=warnings)
        self.assertTrue(any("top and front views draw the same picture" in w for w in warnings), warnings)
        warnings = []
        sheet = Sheet("A2", 1.0)
        sheet.three_views(_perforated())  # a plate: no two of its views alike
        _render_sheet(sheet, index=1, count=1, label="unlike", warnings=warnings)
        self.assertFalse([w for w in warnings if "same picture" in w], warnings)

def _joining_plate(holes=((10, 10), (30, 10), (50, 10), (50, 30), (50, 50)), *, ends: int = 2):
    """A 60 x 60 x 4 plate with one corner cut at 45 degrees, 40 along each edge,
    and 5.5 mm holes chamfered 0.5 at both ends (``ends=1``: the top alone): the
    shape of a T-slot joining plate."""
    from build123d import Axis, Cylinder, GeomType, Polygon, Pos, chamfer, extrude

    plate = extrude(Polygon((0, 0), (60, 0), (60, 60), (40, 60), (0, 20), align=None), 4)
    for x, y in holes:
        plate -= Pos(x, y, 2) * Cylinder(2.75, 4)
    rims = plate.edges().filter_by(GeomType.CIRCLE)
    return chamfer(rims if ends == 2 else rims.group_by(Axis.Z)[-1], 0.5)


def _staircase(steps: int = 8):
    """``steps`` steps, each 10 along X and 5 higher than the last, 20 deep."""
    from build123d import Align, Box, Pos

    lowest = (Align.MIN, Align.MIN, Align.MIN)
    part = Box(10, 20, 5, align=lowest)
    for at in range(1, steps):
        part += Pos(10 * at, 0, 0) * Box(10, 20, 5 * (at + 1), align=lowest)
    return part


class PartSheetTests(unittest.TestCase):
    """``part_sheet``: one call draws a part's first pass, which states its
    geometry and leaves its requirements to the person."""

    def _drawn(self, part, **fields):
        from cadgen._internal.drawing_render import _render_sheet
        from cadgen._internal.drawing_report import _unstated
        from cadgen.eng_drawing import part_sheet

        sheet = part_sheet(part, title="PART", **fields)
        facts = _facts()
        doc = _render_sheet(sheet, index=1, count=1, label="first", facts=facts)
        return sheet, doc, _unstated(facts)

    def test_a_plate_s_first_pass_states_all_of_it(self) -> None:
        """Paul Fremantle's Draftwright drew this plate from its STEP with one call;
        so does this: one edge view (a plate's two say one thing), the holes called
        out once and located from the edges, the cut corner placed by both its
        ends, and the chamfers in a note. Nothing is left unstated."""
        sheet, doc, unstated = self._drawn(_joining_plate())
        # Its holes are seen from above: it is turned to face the front, the edge view beside.
        self.assertEqual([v.name for v in sheet.views], ["front", "right", "iso"])
        self.assertEqual(sheet._size(), "A4")
        self.assertEqual(unstated, [])
        self.assertEqual(_callouts(doc), ["5× %%c5.5 THRU", "⌵ %%c6.5 × 90° BOTH ENDS"])  # stacked
        self.assertIsNone(sheet.views[0]._table)
        self.assertEqual(sorted(_dim_texts(doc)), sorted(["10", "10", "20", "30", "30", "4", "40", "50", "50",
                                                          "60", "60"]))

    def test_more_holes_than_a_few_go_in_a_table(self) -> None:
        grid = tuple((x, y) for x in (10, 25, 40) for y in (5, 15, 25))  # nine, clear of the cut corner
        sheet, _doc, unstated = self._drawn(_joining_plate(grid))
        self.assertIsNotNone(sheet.views[0]._table)
        self.assertEqual(unstated, [])

    def test_steps_past_a_few_are_left_to_the_report(self) -> None:
        """Placing every step of a long ladder shrinks the part more than it helps:
        the largest six go on, and the report names the step it leaves."""
        sheet, _doc, unstated = self._drawn(_staircase())
        self.assertEqual([v.name for v in sheet.views], ["front", "right", "iso"])  # the right for its depth
        self.assertEqual(len(unstated), 1, unstated)
        self.assertIn("is not located", unstated[0])
        self.assertEqual(self._drawn(_staircase(6))[2], [], "five risers and five treads each fit")

    def test_a_view_repeating_one_chosen_goes_last_on_a_tie(self) -> None:
        """A square column's right view is its front again; its top shows what the
        front does not, so the top is the one drawn."""
        from build123d import Align, Box

        sheet, _doc, _unstated = self._drawn(Box(30, 30, 60, align=(Align.MIN, Align.MIN, Align.MIN)))
        self.assertEqual([v.name for v in sheet.views], ["top", "front", "iso"])

    def test_edges_of_several_sizes_are_each_noted(self) -> None:
        from build123d import Align, Axis, Box, fillet

        block = Box(40, 30, 10, align=(Align.MIN, Align.MIN, Align.MIN))
        block = fillet(block.edges().filter_by(Axis.Z).sort_by(Axis.X)[:2], 2)
        part = fillet(block.edges().filter_by(Axis.Z).sort_by(Axis.X)[-2:], 5)
        sheet, _doc, unstated = self._drawn(part)
        self.assertEqual([n for n in sheet.notes if "ROUND" in n], ["2× ROUNDS R2.", "2× ROUNDS R5."])
        self.assertEqual(unstated, [])

    def test_a_through_hole_opened_out_alike_at_both_ends_is_seen_from_either(self) -> None:
        from cadgen._internal.drawing_annotation import _looks_into
        from cadgen._internal.drawing_features import holes

        hole = holes(_joining_plate(((30, 30),)))[0]
        self.assertEqual((hole.csk, hole.far_csk), ((6.5, 90.0), (6.5, 90.0)))
        self.assertTrue(_looks_into(hole, (0.0, 0.0, 1.0)) and _looks_into(hole, (0.0, 0.0, -1.0)))
        one_end = holes(_joining_plate(((30, 30),), ends=1))[0]
        self.assertEqual((one_end.csk, one_end.far_csk), ((6.5, 90.0), None))
        self.assertFalse(_looks_into(one_end, one_end.axis), "a chamfer at one end alone is not what the far view shows")


class CrowdedSheetTests(unittest.TestCase):
    """Two values in one place on a sheet choosing its size take a larger sheet;
    on a sheet whose size the author fixed, they are refused, as before."""

    def test_a_sheet_choosing_its_size_takes_the_next_one_up(self) -> None:
        from unittest import mock

        from cadgen._internal import drawing_render
        from cadgen._internal.drawing_sheet import _Crowded
        from cadgen.eng_drawing import Sheet

        tried = []

        def draw(sheet, *, floor, ceiling, **_kwargs):
            tried.append((floor, ceiling))
            sheet._chosen_size, sheet._chosen_scale = ("A4", "A3", "A2")[min(floor, 2)], 1.0
            if floor < 2:
                raise _Crowded("annotation overlaps")
            return "drawn"

        with mock.patch.object(drawing_render, "_draw_sheet", side_effect=draw):
            self.assertEqual(drawing_render._render_sheet(Sheet(None, None), index=1, count=1, label="c"), "drawn")
            self.assertEqual(tried, [(0, None), (1, None), (2, None)])
            tried.clear()
            with self.assertRaises(_Crowded):
                drawing_render._render_sheet(Sheet("A4", None), index=1, count=1, label="c")
            self.assertEqual(tried, [(0, None)])


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
