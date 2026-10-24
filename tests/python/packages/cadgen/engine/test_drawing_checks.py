"""The DXF drawing checks the engine runs on every drawing it writes (`cadgen.engine.export.dxf`),
beyond what `test_dxf.DrawingChecksTest` pins: full-circle arcs and open polylines, the file
round trip, the layer names a drawing's furniture uses, the evidence a file is a drawing,
malformed splines and the layer table's linetypes."""

import unittest
from pathlib import Path

import ezdxf

from cadgen.engine.export import dxf as drawing_checks
from cadgen.engine.export.dxf import (
    DrawingValidationError,
    layer_allows_open_geometry,
    layer_intent,
    raise_on_error_findings,
    validate_drawing_document,
    validate_dxf_file,
)
from tests.python.support.tmp_root import temporary_directory


def _new_document():
    document = ezdxf.new("R2010")
    document.units = ezdxf.units.MM
    return document


def _codes(findings):
    return sorted(finding.code for finding in findings)


class PathChecksTest(unittest.TestCase):
    def test_full_circle_arc_is_valid(self) -> None:
        document = _new_document()
        document.modelspace().add_arc((0, 0), 5, 0, 360, dxfattribs={"layer": "CUT"})

        self.assertEqual([], validate_drawing_document(document))


    def test_open_polyline_on_cut_layer_is_error(self) -> None:
        document = _new_document()
        document.modelspace().add_lwpolyline([(0, 0), (40, 0), (40, 20)], dxfattribs={"layer": "CUT"})

        self.assertIn("open_cut_profile", _codes(validate_drawing_document(document)))


    def test_raise_on_error_findings(self) -> None:
        document = _new_document()
        findings = validate_drawing_document(document)

        with self.assertRaises(DrawingValidationError):
            raise_on_error_findings(findings, label="empty")

    def test_validate_dxf_file_roundtrip(self) -> None:
        document = _new_document()
        document.modelspace().add_lwpolyline(
            [(0, 0), (40, 0), (40, 20), (0, 20)], close=True, dxfattribs={"layer": "CUT"}
        )
        with temporary_directory(prefix="dxf-checks") as root:
            path = Path(root) / "outline.dxf"
            document.saveas(str(path))

            self.assertEqual([], validate_dxf_file(path))


class LayerIntentTokenTest(unittest.TestCase):
    """The classifier decides which layers must hold CLOSED contours.

    A dimensioned drawing's furniture -- sections, hidden lines, centre lines, a title block,
    dimensions -- is not a cut path, and every one of those layer names used to be classified as
    one, so a plan-and-sections drawing could not generate at all (issue #246).
    """

    def test_drawing_furniture_is_not_a_cut_layer(self) -> None:
        for name in (
            "SECTION", "SECTIONS", "HIDDEN", "CENTER", "CENTRELINE", "PHANTOM",
            "TITLEBLOCK", "TITLE", "BORDER", "FRAME", "VIEWPORT", "HATCH",
            "DIM", "DIMS", "DIMENSION_100", "TEXT", "LABELS", "LEADER", "AXIS",
        ):
            with self.subTest(layer=name):
                self.assertEqual("reference", layer_intent(name))
                self.assertTrue(layer_allows_open_geometry(name))

    def test_an_explicit_cut_token_wins_over_a_view_token(self) -> None:
        # A layer called CUT_SECTION is a cut path whose name mentions a view. Classifying it as
        # annotation would skip the closure check on the layer that most needs it.
        for name in ("CUT_SECTION", "SECTION_CUT", "PROFILE_HIDDEN", "cut-dim"):
            with self.subTest(layer=name):
                self.assertEqual("cut", layer_intent(name))
                self.assertFalse(layer_allows_open_geometry(name))

    def test_matching_is_still_on_whole_tokens(self) -> None:
        # The rule that keeps this safe: PREFORM is not "ref", SECTIONAL is not "section".
        for name in ("PREFORM", "SECTIONAL", "DIMPLE", "CENTERED", "NOTED", "FRAMEWORK"):
            with self.subTest(layer=name):
                self.assertEqual("cut", layer_intent(name))


def _cut_layout_with_an_open_profile():
    document = ezdxf.new("R2010", setup=True)
    document.units = ezdxf.units.MM
    document.layers.add("CUT")
    document.modelspace().add_lwpolyline(
        [(0, 0), (100, 0), (100, 60)], dxfattribs={"layer": "CUT"}
    )
    return document


class DrawingDetectionTest(unittest.TestCase):
    """A drawing is recognised from the FILE, not from a field a generator sets.

    Issue #246: a workshop drawing -- plan, elevations, sections, title block, 37 dimensions --
    could not generate, because a layer matching no known intent must hold closed contours. The
    signal is the DXF's own apparatus: dimensions, leaders, paper-space viewports. A laser-cut
    layout is model-space geometry at 1:1 with none of it. Deciding from the file means an
    imported .dxf from AutoCAD validates by the same rule as a generated one.
    """


    def test_absence_of_closure_is_never_the_evidence(self) -> None:
        # "Nothing closes, so it must be a drawing" would excuse every broken cut layout.
        is_drawing, evidence = drawing_checks.document_is_drawing(
            _cut_layout_with_an_open_profile()
        )
        self.assertFalse(is_drawing)
        self.assertEqual("", evidence)

    def test_paper_space_geometry_counts_as_apparatus(self) -> None:
        document = ezdxf.new("R2010", setup=True)
        document.units = ezdxf.units.MM
        document.layers.add("CUT")
        document.modelspace().add_lwpolyline(
            [(0, 0), (10, 0), (10, 10), (0, 10)], close=True, dxfattribs={"layer": "CUT"}
        )
        layout = document.layout("Layout1")
        layout.add_text("TITLE BLOCK", height=5).set_placement((0, 0))
        is_drawing, evidence = drawing_checks.document_is_drawing(document)
        self.assertTrue(is_drawing)
        self.assertIn("paper-space", evidence)


class MalformedSplineTests(unittest.TestCase):
    """A SPLINE whose control_points are unusable must degrade to \"skip\", not fail the doc.

    ezdxf yields Vec3, but third-party files and ezdxf API drift (issue #246) can expose a
    malformed entity; _open_endpoints must survive AttributeError (missing attributes),
    TypeError (scalars instead of points) and IndexError (too-short tuples) alike.
    """

    def test_unusable_spline_control_points_skip_the_entity(self) -> None:
        from cadgen.engine.export.dxf import _open_endpoints

        _MISSING = object()

        class _FakeSpline:
            def __init__(self, control_points=_MISSING):
                self.closed = False
                self._control_points = control_points

            def dxftype(self) -> str:
                return "SPLINE"

            @property
            def control_points(self):
                if self._control_points is _MISSING:
                    raise AttributeError("no control_points attribute")
                return self._control_points

        self.assertIsNone(_open_endpoints(_FakeSpline()))  # AttributeError: missing attribute
        self.assertIsNone(_open_endpoints(_FakeSpline([1.0, 2.0])))  # TypeError: scalars
        self.assertIsNone(_open_endpoints(_FakeSpline([(0,), (1,)])))  # IndexError: short tuples
        self.assertIsNone(_open_endpoints(_FakeSpline([None, None])))  # TypeError: None points

    def test_usable_spline_control_points_give_open_endpoints(self) -> None:
        from cadgen.engine.export.dxf import _open_endpoints

        class _PointySpline:
            closed = False

            def dxftype(self) -> str:
                return "SPLINE"

            @property
            def control_points(self):
                return [(0.0, 0.0, 0.0), (10.0, 20.0, 30.0)]

        self.assertEqual(
            ((0.0, 0.0), (10.0, 20.0)),
            _open_endpoints(_PointySpline()),
        )

    def test_a_closed_spline_has_no_endpoints(self) -> None:
        from cadgen.engine.export.dxf import _open_endpoints

        class _ClosedSpline:
            closed = True

            def dxftype(self) -> str:
                return "SPLINE"

            @property
            def control_points(self):
                return [(0.0, 0.0), (1.0, 1.0)]

        self.assertIsNone(_open_endpoints(_ClosedSpline()))


class LayerTableIntentTest(unittest.TestCase):
    """Two standard layer properties say "not a cut path" without naming the layer so."""


    def test_a_hidden_or_centre_linetype_is_annotation(self) -> None:
        document = ezdxf.new("R2010", setup=True)
        document.layers.add("VERDECKT", linetype="HIDDEN")
        document.layers.add("MITTE", linetype="CENTER")
        intents = drawing_checks.layer_table_intents(document)
        self.assertEqual("reference", intents["VERDECKT"])
        self.assertEqual("reference", intents["MITTE"])

    def test_a_dashed_BEND_layer_stays_a_bend(self) -> None:
        # Bend lines are conventionally dashed, and bend is not the same intent as annotation:
        # the bend checks want to know it is a bend.
        document = ezdxf.new("R2010", setup=True)
        document.layers.add("BEND", linetype="DASHED")
        self.assertEqual("bend", drawing_checks.layer_table_intents(document).get("BEND", "bend"))

    def test_a_plain_cut_layer_declares_nothing(self) -> None:
        document = ezdxf.new("R2010", setup=True)
        document.layers.add("CUT")
        self.assertNotIn("CUT", drawing_checks.layer_table_intents(document))


if __name__ == "__main__":
    unittest.main()
