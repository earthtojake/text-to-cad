"""``cadgen.drawing_payload``: what a DXF becomes.

Every fixture here is generated with ezdxf into a fresh temporary directory --
nothing reads the sample corpus. The drawings are deliberately tiny and
deliberately varied: the module's whole claim is that it does not need a case
per entity type, and the only way to hold it to that is to feed it one of each.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

import ezdxf  # noqa: E402

from cadgen import drawing_payload  # noqa: E402
from cadgen.drawing_payload import (  # noqa: E402
    DRAWING_PAYLOAD_SCHEMA_VERSION,
    DrawingReadError,
    build_drawing_payload,
    encode_drawing_payload,
)

PRIMITIVE_TYPES = frozenset(
    {"point", "lines", "path", "filled-paths", "filled-polygon", "text"}
)


class DrawingFixture(unittest.TestCase):
    """A temp directory for one test class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = temporary_directory(prefix="drawing-payload-")
        cls.tmp = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def write_drawing(self, name: str, build, *, setup: bool = True) -> Path:
        """Save a drawing built by ``build(document, modelspace)``."""
        document = ezdxf.new("R2010", setup=setup)
        document.header["$INSUNITS"] = 4
        build(document, document.modelspace())
        path = self.tmp / name
        document.saveas(str(path))
        return path

    def payload(self, name: str, build, **kwargs) -> dict:
        return build_drawing_payload(self.write_drawing(name, build, **kwargs))

    def types(self, payload) -> set[str]:
        return {primitive["type"] for primitive in payload["primitives"]}


class EveryEntityKindSurvives(DrawingFixture):
    """The entity types a real drawing carries, one file each.

    Failing here means ezdxf stopped flattening something we relied on it
    flattening — not that this module lost a branch, because it has none.
    """

    def assertDrawn(self, payload, expected_types) -> None:
        self.assertTrue(payload["primitives"], "nothing was drawn")
        self.assertLessEqual(self.types(payload), PRIMITIVE_TYPES)
        self.assertLessEqual(set(expected_types), self.types(payload))
        self.assertIsNotNone(payload["bounds"])

    def test_text_is_a_text_primitive(self) -> None:
        payload = self.payload(
            "text.dxf", lambda doc, msp: msp.add_text("AB", height=2).set_placement((0, 0))
        )
        self.assertDrawn(payload, {"text"})

    def test_mtext_is_one_text_primitive_per_line(self) -> None:
        payload = self.payload(
            "mtext.dxf",
            lambda doc, msp: msp.add_mtext("AB\nCD", dxfattribs={"char_height": 2}),
        )
        self.assertDrawn(payload, {"text"})
        self.assertEqual([primitive["text"] for primitive in payload["primitives"]], ["AB", "CD"])

    def test_a_rendered_dimension_brings_its_lines_arrows_and_text(self) -> None:
        payload = self.payload(
            "dim.dxf",
            lambda doc, msp: msp.add_linear_dim(base=(0, -5), p1=(0, 0), p2=(10, 0)).render(),
        )
        # The arrow heads are filled polygons and the measurement is text: a
        # dimension that arrived as bare lines would have lost both.
        self.assertDrawn(payload, {"lines", "filled-polygon", "text"})

    def test_a_solid_hatch_is_a_filled_path(self) -> None:
        def build(doc, msp):
            hatch = msp.add_hatch(color=2)
            hatch.paths.add_polyline_path([(0, 0), (5, 0), (5, 5), (0, 5)], is_closed=True)

        payload = self.payload("hatch_solid.dxf", build)
        self.assertDrawn(payload, {"filled-paths"})
        self.assertEqual(payload["primitives"][0]["color"], "#ffff00")

    def test_a_pattern_hatch_becomes_its_pattern_lines(self) -> None:
        def build(doc, msp):
            hatch = msp.add_hatch()
            hatch.set_pattern_fill("ANSI31", scale=0.5, color=5)
            hatch.paths.add_polyline_path([(0, 0), (5, 0), (5, 5), (0, 5)], is_closed=True)

        payload = self.payload("hatch_pattern.dxf", build)
        self.assertDrawn(payload, {"lines"})
        self.assertEqual(payload["primitives"][0]["color"], "#0000ff")
        self.assertGreater(len(payload["primitives"][0]["geometry"]), 1)

    def test_a_block_insert_brings_the_blocks_geometry(self) -> None:
        def build(doc, msp):
            block = doc.blocks.new("PART")
            block.add_line((0, 0), (1, 1))
            block.add_circle((0, 0), 1)
            msp.add_blockref("PART", (10, 10))

        payload = self.payload("insert.dxf", build)
        self.assertDrawn(payload, {"lines", "path"})
        # Placed at the insert point, not at the block's own origin.
        self.assertGreater(payload["bounds"][2], 9)

    def test_a_spline_becomes_a_cubic_path(self) -> None:
        payload = self.payload(
            "spline.dxf",
            lambda doc, msp: msp.add_spline([(0, 0), (5, 5), (10, 0), (15, 5)]),
        )
        self.assertDrawn(payload, {"path"})
        self.assertIn("C", {command[0] for command in payload["primitives"][0]["geometry"]})

    def test_an_lwpolyline_with_a_bulge_keeps_its_arc(self) -> None:
        payload = self.payload(
            "bulge.dxf",
            lambda doc, msp: msp.add_lwpolyline(
                [(0, 0, 0, 0, 0.5), (5, 0), (5, 5)], format="xyseb"
            ),
        )
        self.assertDrawn(payload, {"path"})
        commands = {command[0] for command in payload["primitives"][0]["geometry"]}
        self.assertTrue(commands & {"C", "Q"}, "the bulge arrived as straight segments")

    def test_an_ellipse_becomes_a_path(self) -> None:
        payload = self.payload(
            "ellipse.dxf",
            lambda doc, msp: msp.add_ellipse((0, 0), major_axis=(4, 0), ratio=0.5),
        )
        self.assertDrawn(payload, {"path"})

    def test_a_point_entity_becomes_a_point(self) -> None:
        payload = self.payload("point.dxf", lambda doc, msp: msp.add_point((1, 2)))
        self.assertDrawn(payload, {"point"})
        self.assertEqual(payload["primitives"][0]["geometry"], [1, 2])

    def test_an_empty_modelspace_draws_nothing_and_has_no_bounds(self) -> None:
        payload = self.payload("empty.dxf", lambda doc, msp: None, setup=False)
        self.assertEqual(payload["primitives"], [])
        self.assertEqual(payload["layers"], [])
        self.assertIsNone(
            payload["bounds"],
            "an empty drawing has no extent; [0,0,0,0] is a box a client would zoom to",
        )
        self.assertEqual(payload["schemaVersion"], DRAWING_PAYLOAD_SCHEMA_VERSION)


class TextStaysText(DrawingFixture):
    """A string arrives as its characters, placed by ezdxf, never as glyph outlines."""

    def texts(self, payload):
        return [primitive for primitive in payload["primitives"] if primitive["type"] == "text"]

    def test_a_text_carries_its_string_font_size_width_and_placement(self) -> None:
        def build(doc, msp):
            msp.add_text("NOTE %%c10", height=2.5, dxfattribs={"color": 1}).set_placement((10, 20))

        payload = self.payload("note.dxf", build)
        (text,) = self.texts(payload)
        self.assertEqual(text["text"], "NOTE Ø10", "a control code is the character it stands for")
        self.assertEqual((text["color"], text["height"]), ("#ff0000", 2.5))
        self.assertEqual(text["transform"], [1, 0, 0, 1, 10, 20], "baseline-left at the insert point")
        self.assertGreater(text["width"], 2.5 * 4, "the advance ezdxf measured for eight characters")
        self.assertEqual(set(payload["fonts"][text["font"]]), {"family", "weight", "italic"})
        # The box a fit holds: from the insert point along the advance and up the cap height.
        minimum_x, minimum_y, maximum_x, maximum_y = payload["bounds"]
        self.assertEqual(minimum_x, 10)
        self.assertLess(minimum_y, 20)
        self.assertAlmostEqual(maximum_x, 10 + text["width"], places=3)
        self.assertGreaterEqual(maximum_y, 22.5)

    def test_rotation_alignment_and_width_factor_are_in_the_transform(self) -> None:
        from ezdxf.enums import TextEntityAlignment

        def build(doc, msp):
            msp.add_text("UP", height=2, rotation=90, dxfattribs={"width": 0.5}).set_placement((5, 5))
            msp.add_text("MID", height=2).set_placement((50, 0), align=TextEntityAlignment.CENTER)

        up, middle = self.texts(self.payload("placed.dxf", build))
        self.assertEqual(up["transform"], [0, 0.5, -1, 0, 5, 5], "turned a quarter, squeezed along its baseline")
        self.assertAlmostEqual(middle["transform"][4] + middle["width"] / 2, 50, places=3)

    def test_a_clipped_block_keeps_its_text_outlined_so_the_clip_applies(self) -> None:
        from ezdxf import xclip

        def build(doc, msp):
            block = doc.blocks.new("TAG")
            block.add_text("CLIPPED", height=2).set_placement((0, 0))
            insert = msp.add_blockref("TAG", (0, 0))
            xclip.XClip(insert).set_block_clipping_path([(0, -1), (4, -1), (4, 3), (0, 3)])

        payload = self.payload("clipped.dxf", build)
        self.assertEqual(self.texts(payload), [])
        self.assertIn("filled-paths", self.types(payload))

    def test_a_sheet_of_notes_costs_bytes_per_character_not_per_outline(self) -> None:
        def build(doc, msp):
            for row in range(40):
                msp.add_text(f"NOTE {row:03d}: BREAK ALL SHARP EDGES 0.2 MAX", height=2.5).set_placement((0, row * 5))

        encoded = encode_drawing_payload(self.payload("notes.dxf", build))
        # Outlined, each of these lines was ~20 KB of glyph paths.
        self.assertLess(len(encoded) / 40, 300)


class ColourResolution(DrawingFixture):
    """``null`` means the theme's foreground; anything else is a literal pen."""

    def colors(self, payload):
        return [primitive["color"] for primitive in payload["primitives"]]

    def test_aci_7_and_bylayer_to_7_and_byblock_are_all_the_default_pen(self) -> None:
        def build(doc, msp):
            doc.layers.add("PLAIN")  # no colour given: ACI 7
            msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "PLAIN", "color": 7})
            msp.add_line((0, 1), (1, 1), dxfattribs={"layer": "PLAIN"})  # BYLAYER -> 7
            msp.add_line((0, 2), (1, 2), dxfattribs={"layer": "PLAIN", "color": 0})  # BYBLOCK

        self.assertEqual(self.colors(self.payload("default_pen.dxf", build)), [None, None, None])

    def test_bylayer_to_a_coloured_layer_takes_the_layers_colour(self) -> None:
        def build(doc, msp):
            doc.layers.add("CUT", color=1)
            msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "CUT"})

        self.assertEqual(self.colors(self.payload("bylayer.dxf", build)), ["#ff0000"])

    def test_an_explicit_aci_and_a_true_colour_are_literal_hex(self) -> None:
        def build(doc, msp):
            msp.add_line((0, 0), (1, 0), dxfattribs={"color": 3})
            msp.add_line((0, 1), (1, 1), dxfattribs={"true_color": 0xFF00FF})

        self.assertEqual(self.colors(self.payload("literal.dxf", build)), ["#00ff00", "#ff00ff"])

    def test_byblock_inside_a_block_takes_the_inserts_colour(self) -> None:
        def build(doc, msp):
            block = doc.blocks.new("PART")
            block.add_line((0, 0), (1, 1), dxfattribs={"color": 0})  # BYBLOCK
            msp.add_blockref("PART", (0, 0), dxfattribs={"color": 1})

        self.assertEqual(self.colors(self.payload("byblock_inside.dxf", build)), ["#ff0000"])

    def test_bylayer_inside_a_block_still_resolves_through_the_layer(self) -> None:
        def build(doc, msp):
            doc.layers.add("CUT", color=1)
            block = doc.blocks.new("PART")
            block.add_line((0, 0), (1, 1), dxfattribs={"color": 256})  # BYLAYER
            msp.add_blockref("PART", (0, 0), dxfattribs={"layer": "CUT"})

        self.assertEqual(self.colors(self.payload("bylayer_inside.dxf", build)), ["#ff0000"])

    def test_an_undefined_layer_draws_with_the_default_pen(self) -> None:
        """Not ezdxf's hard-coded white, which is invisible on a light theme."""
        payload = self.payload(
            "undefined_layer.dxf",
            lambda doc, msp: msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "NOPE"}),
        )
        self.assertEqual(self.colors(payload), [None])
        self.assertEqual(payload["layers"], [{"name": "NOPE", "color": None, "entities": 1}])

    def test_no_primitive_carries_the_sentinel_or_a_stroke_width(self) -> None:
        def build(doc, msp):
            doc.layers.add("CUT", color=1)
            msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "CUT"})
            msp.add_line((0, 1), (1, 1))

        payload = self.payload("shape.dxf", build)
        for primitive in payload["primitives"]:
            self.assertEqual(set(primitive), {"type", "layer", "color", "entity", "geometry"})
            self.assertNotEqual(primitive["color"], drawing_payload._DEFAULT_PEN_SENTINEL)


class LayersAndUnits(DrawingFixture):
    def test_layers_are_listed_in_first_seen_order_with_counts_and_colours(self) -> None:
        def build(doc, msp):
            doc.layers.add("CUT", color=1)
            doc.layers.add("PLAIN")
            doc.layers.add("UNUSED", color=5)
            msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "PLAIN"})
            msp.add_line((0, 1), (1, 1), dxfattribs={"layer": "CUT"})
            msp.add_line((0, 2), (1, 2), dxfattribs={"layer": "CUT"})

        payload = self.payload("layers.dxf", build)
        self.assertEqual(
            payload["layers"],
            [
                {"name": "PLAIN", "color": None, "entities": 1},
                {"name": "CUT", "color": "#ff0000", "entities": 2},
            ],
            "first-seen order, and a layer nothing drew on is not a row",
        )

    def test_a_layer_counts_entities_not_the_primitives_they_became(self) -> None:
        def build(doc, msp):
            doc.layers.add("CUT", color=1)
            msp.add_circle((0, 0), 2, dxfattribs={"layer": "CUT"})
            msp.add_lwpolyline([(0, 0), (1, 0), (1, 1)], dxfattribs={"layer": "CUT"})

        payload = self.payload("layer_entities.dxf", build)
        self.assertEqual(payload["layers"], [{"name": "CUT", "color": "#ff0000", "entities": 2}])

    def test_units_report_the_code_the_name_and_the_millimetre_factor(self) -> None:
        payload = self.payload("mm.dxf", lambda doc, msp: msp.add_line((0, 0), (1, 1)))
        self.assertEqual(
            payload["units"], {"insunits": 4, "name": "Millimeters", "toMillimetres": 1.0}
        )

    def test_inches_convert_without_the_conversion_tables_noise_digits(self) -> None:
        def build(doc, msp):
            doc.header["$INSUNITS"] = 1
            msp.add_line((0, 0), (1, 1))

        self.assertEqual(self.payload("inch.dxf", build)["units"]["toMillimetres"], 25.4)

    def test_an_unitless_drawing_has_no_millimetre_factor(self) -> None:
        def build(doc, msp):
            doc.header["$INSUNITS"] = 0
            msp.add_line((0, 0), (1, 1))

        units = self.payload("unitless.dxf", build)["units"]
        self.assertEqual(units["insunits"], 0)
        self.assertIsNone(units["toMillimetres"])


class CoordinatesAndEncoding(DrawingFixture):
    def test_coordinates_are_rounded_and_never_carry_a_negative_zero(self) -> None:
        def build(doc, msp):
            msp.add_line((0.000000001, 1.123456789), (-0.00000004, 2.0))

        encoded = encode_drawing_payload(self.payload("round.dxf", build))
        self.assertNotIn(b"-0.0", encoded)
        self.assertNotIn(b"e-", encoded, "a coordinate escaped rounding in exponent form")
        self.assertIn(b"1.1235", encoded)

    def test_the_encoding_is_compact_utf8(self) -> None:
        def build(doc, msp):
            doc.layers.add("Ø-CUT", color=1)
            msp.add_line((0, 0), (1, 1), dxfattribs={"layer": "Ø-CUT"})

        encoded = encode_drawing_payload(self.payload("compact.dxf", build))
        self.assertNotIn(b", ", encoded)
        self.assertNotIn(b'": ', encoded)
        self.assertIn("Ø-CUT".encode("utf-8"), encoded)

    def test_bounds_come_from_the_emitted_geometry(self) -> None:
        def build(doc, msp):
            msp.add_line((-3, -4), (7, 11))

        payload = self.payload("bounds.dxf", build)
        self.assertEqual(payload["bounds"], [-3, -4, 7, 11])

    def test_the_same_bytes_encode_to_the_same_bytes(self) -> None:
        """Byte stability, over the drawing whose renderer is randomised.

        ezdxf jiggles a pattern hatch's base lines from the process-wide random
        module; without the module's seeding this assertion fails every run.
        """

        def build(doc, msp):
            hatch = msp.add_hatch()
            hatch.set_pattern_fill("ANSI31", scale=0.4, color=5)
            hatch.paths.add_polyline_path([(0, 0), (9, 0), (9, 9), (0, 9)], is_closed=True)
            msp.add_text("STABLE", height=2).set_placement((0, 12))
            msp.add_spline([(0, 20), (5, 25), (10, 20)])

        path = self.write_drawing("stable.dxf", build)
        first = encode_drawing_payload(build_drawing_payload(path))
        second = encode_drawing_payload(build_drawing_payload(path))
        self.assertEqual(first, second)
        self.assertEqual(json.loads(first)["schemaVersion"], DRAWING_PAYLOAD_SCHEMA_VERSION)

    def test_the_render_leaves_the_processes_random_stream_alone(self) -> None:
        import random

        random.seed(1234)
        expected = [random.random() for _ in range(3)]
        random.seed(1234)
        first = random.random()
        self.payload("stream.dxf", lambda doc, msp: msp.add_line((0, 0), (1, 1)))
        self.assertEqual([first, random.random(), random.random()], expected)


class UnreadableDrawings(DrawingFixture):
    def test_a_missing_file_says_so(self) -> None:
        with self.assertRaises(DrawingReadError) as caught:
            build_drawing_payload(self.tmp / "absent.dxf")
        self.assertIn("absent.dxf", str(caught.exception))

    def test_a_file_that_is_not_a_dxf_at_all_names_the_repair(self) -> None:
        path = self.tmp / "garbage.dxf"
        path.write_text("this is not a DXF\n" * 20, encoding="utf-8")
        with self.assertRaises(DrawingReadError) as caught:
            build_drawing_payload(path)
        message = str(caught.exception)
        self.assertIn("garbage.dxf", message)
        self.assertIn("audit", message, "the error must say what to do about it")

    def test_a_damaged_dxf_is_recovered_rather_than_refused(self) -> None:
        """``ezdxf.recover`` is the second attempt, and it has to be reached."""
        path = self.write_drawing(
            "damaged.dxf", lambda doc, msp: msp.add_line((0, 0), (10, 10))
        )
        text = path.read_text(encoding="utf-8")
        # A trailing EOF is what a truncated write leaves behind; strict
        # readfile rejects the structure and recover puts it back together.
        path.write_text(text.replace("\nENDSEC\n  0\nEOF\n", "\n"), encoding="utf-8")
        payload = build_drawing_payload(path)
        self.assertTrue(payload["primitives"])

    def test_bytes_read_already_draw_what_their_file_draws(self) -> None:
        """The viewer renders the bytes it read (``data``): an ASCII drawing with text, an R12
        one whose header names a code page, a binary one, and a damaged one, recovered."""
        def notes(doc, msp) -> None:
            msp.add_line((0, 0), (10, 0))
            msp.add_text("ÄÖÜ ß", height=2).set_placement((0, 2))

        paths = [self.write_drawing("ascii.dxf", notes)]
        for name, version, fmt in (("r12.dxf", "R12", "asc"), ("binary.dxf", "R2010", "bin")):
            document = ezdxf.new(version)
            notes(document, document.modelspace())
            document.saveas(str(self.tmp / name), fmt=fmt)
            paths.append(self.tmp / name)
        damaged = self.write_drawing("broken.dxf", lambda doc, msp: msp.add_line((0, 0), (10, 10)))
        damaged.write_text(damaged.read_text(encoding="utf-8").replace("\nENDSEC\n  0\nEOF\n", "\n"),
                           encoding="utf-8")
        for path in [*paths, damaged]:
            with self.subTest(path=path.name):
                self.assertEqual(build_drawing_payload(path, path.read_bytes()), build_drawing_payload(path))
        r12 = build_drawing_payload(paths[1], paths[1].read_bytes())
        self.assertIn("ÄÖÜ ß", json.dumps(r12, ensure_ascii=False), "decoded in the code page its header names")
        garbage = b"this is not a DXF\n" * 20
        with self.assertRaisesRegex(DrawingReadError, "garbage.dxf.*audit"):
            build_drawing_payload(self.tmp / "garbage.dxf", garbage)

    def test_an_unknown_primitive_type_is_a_loud_failure_not_a_dropped_shape(self) -> None:
        path = self.write_drawing("kind.dxf", lambda doc, msp: msp.add_line((0, 0), (1, 1)))
        with mock.patch.object(
            drawing_payload,
            "_render",
            return_value=(None, [{"type": "hologram", "properties": {"layer": "0"}, "geometry": []}]),
        ):
            with self.assertRaises(DrawingReadError) as caught:
                build_drawing_payload(path)
        self.assertIn("hologram", str(caught.exception))


class EntitiesNameWhatDrew(DrawingFixture):
    """Every primitive names its modelspace entity by handle, and ``entities`` says what each is."""

    def test_each_primitive_names_its_entity_and_each_entity_is_listed_once(self) -> None:
        handles = {}

        def build(doc, msp):
            doc.layers.add("CUT", color=1)
            handles["line"] = msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "CUT"}).dxf.handle
            handles["circle"] = msp.add_circle((5, 5), 1.5, dxfattribs={"layer": "CUT"}).dxf.handle

        payload = self.payload("entities.dxf", build)
        self.assertEqual({primitive["entity"] for primitive in payload["primitives"]}, set(handles.values()))
        self.assertEqual(payload["entities"], [
            {"handle": handles["line"], "type": "LINE", "layer": "CUT"},
            {"handle": handles["circle"], "type": "CIRCLE", "layer": "CUT", "center": [5, 5], "radius": 1.5},
        ])

    def test_a_block_reference_draws_under_its_insert_handle_on_its_contents_layers(self) -> None:
        handles = {}

        def build(doc, msp):
            block = doc.blocks.new("BOLT")
            block.add_circle((0, 0), 2)
            block.add_line((-2, 0), (2, 0), dxfattribs={"layer": "CENTRE"})
            handles["insert"] = msp.add_blockref("BOLT", (20, 20), dxfattribs={"layer": "HARDWARE"}).dxf.handle

        payload = self.payload("insert.dxf", build)
        self.assertEqual({primitive["entity"] for primitive in payload["primitives"]}, {handles["insert"]})
        self.assertEqual(payload["entities"], [{"handle": handles["insert"], "type": "INSERT", "layer": "HARDWARE", "block": "BOLT"}])
        # The block's circle is on "0", which takes the INSERT's layer; its line keeps its own.
        self.assertEqual({row["name"]: row["entities"] for row in payload["layers"]}, {"HARDWARE": 1, "CENTRE": 1})

    def test_a_dimension_is_one_entity_however_many_primitives_draw_it(self) -> None:
        handles = {}

        def build(doc, msp):
            dimension = msp.add_linear_dim(base=(0, -5), p1=(0, 0), p2=(10, 0))
            dimension.render()
            handles["dimension"] = dimension.dimension.dxf.handle

        payload = self.payload("dimension_entity.dxf", build)
        self.assertGreater(len(payload["primitives"]), 1)
        self.assertEqual([row["handle"] for row in payload["entities"]], [handles["dimension"]])
        self.assertEqual(payload["entities"][0]["type"], "DIMENSION")


if __name__ == "__main__":
    unittest.main()
