"""Tests for the generation-time DXF drawing checks."""

import re
import unittest
from pathlib import Path

import ezdxf

from cadgen import drawing_checks
from cadgen.drawing_checks import (
    DrawingValidationError,
    layer_allows_open_geometry,
    layer_intent,
    raise_on_error_findings,
    validate_drawing_document,
    validate_dxf_file,
)
from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory


def _new_document():
    document = ezdxf.new("R2010")
    document.units = ezdxf.units.MM
    return document


def _codes(findings):
    return sorted(finding.code for finding in findings)


class LayerIntentTests(unittest.TestCase):
    def test_whole_token_matching(self) -> None:
        self.assertEqual("bend", layer_intent("BEND"))
        self.assertEqual("bend", layer_intent("bend-lines"))
        self.assertEqual("engrave", layer_intent("ENGRAVE_TEXT"))
        self.assertEqual("reference", layer_intent("REF_GEOMETRY"))
        # Substrings must NOT match: PREFORM contains "ref", KEYNOTES contains "note".
        self.assertEqual("cut", layer_intent("PREFORM"))
        self.assertEqual("cut", layer_intent("KEYNOTES"))
        self.assertEqual("cut", layer_intent("CUT"))
        self.assertFalse(layer_allows_open_geometry("PREFORM"))
        self.assertTrue(layer_allows_open_geometry("BEND"))

    def test_render_kind_matches_validation_intent(self) -> None:
        from cadgen.drawing_render import _semantic_kind_for_layer

        for name in ("BEND", "PREFORM", "ENGRAVE", "NOTES", "CUT"):
            self.assertEqual(layer_intent(name), _semantic_kind_for_layer(name))


class DrawingChecksTests(unittest.TestCase):
    def test_full_circle_arc_is_valid(self) -> None:
        document = _new_document()
        document.modelspace().add_arc((0, 0), 5, 0, 360, dxfattribs={"layer": "CUT"})

        self.assertEqual([], validate_drawing_document(document))

    def test_closed_profiles_and_bend_lines_pass(self) -> None:
        document = _new_document()
        modelspace = document.modelspace()
        modelspace.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True, dxfattribs={"layer": "CUT"})
        modelspace.add_circle((20, 10), 3, dxfattribs={"layer": "CUT"})
        modelspace.add_line((10, 0), (10, 20), dxfattribs={"layer": "BEND"})

        self.assertEqual([], validate_drawing_document(document))

    def test_open_polyline_on_cut_layer_is_error(self) -> None:
        document = _new_document()
        document.modelspace().add_lwpolyline([(0, 0), (40, 0), (40, 20)], dxfattribs={"layer": "CUT"})

        self.assertIn("open_cut_profile", _codes(validate_drawing_document(document)))

    def test_chained_lines_closing_a_loop_pass(self) -> None:
        document = _new_document()
        modelspace = document.modelspace()
        for start, end in [((0, 0), (10, 0)), ((10, 0), (10, 10)), ((10, 10), (0, 0))]:
            modelspace.add_line(start, end, dxfattribs={"layer": "CUT"})

        self.assertEqual([], validate_drawing_document(document))

    def test_dangling_line_on_cut_layer_is_error(self) -> None:
        document = _new_document()
        modelspace = document.modelspace()
        modelspace.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True, dxfattribs={"layer": "CUT"})
        modelspace.add_line((100, 100), (120, 100), dxfattribs={"layer": "CUT"})

        self.assertIn("open_cut_profile", _codes(validate_drawing_document(document)))

    def test_zero_length_and_duplicate_entities_are_errors(self) -> None:
        document = _new_document()
        modelspace = document.modelspace()
        modelspace.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True, dxfattribs={"layer": "CUT"})
        modelspace.add_line((5, 5), (5, 5), dxfattribs={"layer": "BEND"})
        modelspace.add_circle((20, 10), 3, dxfattribs={"layer": "CUT"})
        modelspace.add_circle((20, 10), 3, dxfattribs={"layer": "CUT"})

        codes = _codes(validate_drawing_document(document))
        self.assertIn("zero_length_entity", codes)
        self.assertIn("duplicate_entity", codes)

    def test_empty_drawing_is_error(self) -> None:
        document = _new_document()

        self.assertIn("empty_drawing", _codes(validate_drawing_document(document)))

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


if __name__ == "__main__":
    unittest.main()


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

    def test_the_python_and_js_classifiers_agree(self) -> None:
        # Two hand-copied tables with a comment saying they mirror each other, and nothing
        # pinning them: validation would accept a drawing the viewer then renders as cut paths.
        source = (
            REPO_ROOT / "packages" / "cadjs" / "src" / "lib" / "dxf" / "parseDxf.js"
        ).read_text(encoding="utf-8")
        block = re.search(r"LAYER_INTENT_BY_TOKEN = new Map\(\[(.*?)\]\);", source, re.DOTALL)
        self.assertIsNotNone(block, "cadjs must declare LAYER_INTENT_BY_TOKEN")
        js_pairs = dict(re.findall(r'\["([a-z0-9]+)",\s*"([a-z]+)"\]', block.group(1)))
        self.assertEqual(
            drawing_checks._LAYER_INTENT_BY_TOKEN,
            js_pairs,
            "cadgen and cadjs disagree on layer intent; validation and rendering would classify "
            "the same drawing differently",
        )
def _drawing_with_dimensions():
    """The reporter's shape: open views, annotation layers with local names, dimensions."""
    document = ezdxf.new("R2010", setup=True)
    document.units = ezdxf.units.MM
    modelspace = document.modelspace()
    for name in ("FRONTEN", "KORPUS", "REFERENZ"):
        document.layers.add(name)
    modelspace.add_lwpolyline([(0, 0), (600, 0), (600, 720)], dxfattribs={"layer": "KORPUS"})
    modelspace.add_line((0, 360), (600, 360), dxfattribs={"layer": "REFERENZ"})
    modelspace.add_linear_dim(base=(0, -40), p1=(0, 0), p2=(600, 0)).render()
    return document


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

    def test_dimensions_make_it_a_drawing(self) -> None:
        is_drawing, evidence = drawing_checks.document_is_drawing(_drawing_with_dimensions())
        self.assertTrue(is_drawing)
        self.assertIn("dimension", evidence)

    def test_a_drawing_does_not_have_to_close_its_contours(self) -> None:
        findings = validate_drawing_document(_drawing_with_dimensions())
        self.assertEqual([], [f for f in findings if f.severity == "error"])
        # And it says why, rather than passing silently.
        self.assertEqual(
            ["drawing_document"],
            [f.code for f in findings if f.severity == "info"],
        )

    def test_a_cut_layout_with_an_open_profile_still_fails(self) -> None:
        # The check this feature must not become a bypass for. No dimensions, no viewports:
        # nothing says "drawing", so an unclosed cut path is what it looks like -- an error.
        findings = validate_drawing_document(_cut_layout_with_an_open_profile())
        self.assertIn("open_cut_profile", [f.code for f in findings if f.severity == "error"])

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
        from cadgen.drawing_checks import _open_endpoints

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
        from cadgen.drawing_checks import _open_endpoints

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
        from cadgen.drawing_checks import _open_endpoints

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

    def test_a_non_plotting_layer_is_annotation(self) -> None:
        document = ezdxf.new("R2010", setup=True)
        document.layers.add("KORPUS").dxf.plot = 0
        self.assertEqual("reference", drawing_checks.layer_table_intents(document)["KORPUS"])

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
