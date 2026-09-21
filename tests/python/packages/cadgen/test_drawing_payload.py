"""``cadgen.drawing_payload``: what a DXF becomes, and what it costs twice.

Every fixture here is generated with ezdxf into a fresh temporary directory —
nothing reads the sample corpus, and nothing shares a store with another test
file. The drawings are deliberately tiny and deliberately varied: the module's
whole claim is that it does not need a case per entity type, and the only way
to hold it to that is to feed it one of each.

The store side gets its own ``CADGEN_CACHE_DIR`` per test class, and the
"does not re-run ezdxf" property is checked by COUNTING renders rather than by
timing one, because a timing assertion is a flake waiting for a busy machine.
"""

from __future__ import annotations

import json
import os
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
    drawing_payload_bytes,
    encode_drawing_payload,
)

PRIMITIVE_TYPES = frozenset(
    {"point", "lines", "path", "filled-paths", "filled-polygon"}
)


class DrawingFixture(unittest.TestCase):
    """A temp directory and a private store for one test class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = temporary_directory(prefix="drawing-payload-")
        cls.tmp = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def setUp(self) -> None:
        # A store PER TEST, not per class. These drawings are tiny and several
        # of them render to byte-identical payloads, which is one object in the
        # store: a test that damages it on purpose would otherwise decide what
        # the next test sees.
        self._previous_cache = os.environ.get("CADGEN_CACHE_DIR")
        self.cache = self.tmp / "store" / self.id().rsplit(".", 1)[-1]
        os.environ["CADGEN_CACHE_DIR"] = str(self.cache)

    def tearDown(self) -> None:
        if self._previous_cache is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = self._previous_cache

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

    def test_text_is_outlined_into_filled_paths(self) -> None:
        payload = self.payload(
            "text.dxf", lambda doc, msp: msp.add_text("AB", height=2).set_placement((0, 0))
        )
        self.assertDrawn(payload, {"filled-paths"})

    def test_mtext_is_outlined_into_filled_paths(self) -> None:
        payload = self.payload(
            "mtext.dxf",
            lambda doc, msp: msp.add_mtext("AB\nCD", dxfattribs={"char_height": 2}),
        )
        self.assertDrawn(payload, {"filled-paths"})

    def test_a_rendered_dimension_brings_its_lines_arrows_and_text(self) -> None:
        payload = self.payload(
            "dim.dxf",
            lambda doc, msp: msp.add_linear_dim(base=(0, -5), p1=(0, 0), p2=(10, 0)).render(),
        )
        # The arrow heads are filled polygons and the measurement text is
        # outlined: a dimension that arrived as bare lines would have lost both.
        self.assertDrawn(payload, {"lines", "filled-polygon", "filled-paths"})

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
        self.assertEqual(payload["layers"], [{"name": "NOPE", "color": None, "count": 1}])

    def test_no_primitive_carries_the_sentinel_or_a_stroke_width(self) -> None:
        def build(doc, msp):
            doc.layers.add("CUT", color=1)
            msp.add_line((0, 0), (1, 0), dxfattribs={"layer": "CUT"})
            msp.add_line((0, 1), (1, 1))

        payload = self.payload("shape.dxf", build)
        for primitive in payload["primitives"]:
            self.assertEqual(set(primitive), {"type", "layer", "color", "geometry"})
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
                {"name": "PLAIN", "color": None, "count": 1},
                {"name": "CUT", "color": "#ff0000", "count": 2},
            ],
            "first-seen order, and a layer nothing drew on is not a row",
        )

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


class TheStoreAnswersTheSecondTime(DrawingFixture):
    def drawing(self, name: str) -> Path:
        def build(doc, msp):
            doc.layers.add("CUT", color=1)
            for index in range(20):
                msp.add_line((index, 0), (index, 5), dxfattribs={"layer": "CUT"})

        return self.write_drawing(name, build)

    def test_unchanged_bytes_do_not_re_enter_ezdxf(self) -> None:
        path = self.drawing("cached.dxf")
        with mock.patch.object(
            drawing_payload, "_render", wraps=drawing_payload._render
        ) as render:
            first = drawing_payload_bytes(path)
            second = drawing_payload_bytes(path)
            third = drawing_payload_bytes(path)
        self.assertEqual(render.call_count, 1, "the store did not answer the repeat requests")
        self.assertEqual(first, second)
        self.assertEqual(second, third)

    def test_the_cached_bytes_are_the_payload_and_not_something_near_it(self) -> None:
        path = self.drawing("cached_shape.dxf")
        cached = json.loads(drawing_payload_bytes(path))
        self.assertEqual(cached, build_drawing_payload(path))

    def test_changed_bytes_are_a_different_entry(self) -> None:
        path = self.drawing("changing.dxf")
        before = drawing_payload_bytes(path)
        document = ezdxf.readfile(str(path))
        document.modelspace().add_circle((50, 50), 4)
        document.saveas(str(path))
        with mock.patch.object(
            drawing_payload, "_render", wraps=drawing_payload._render
        ) as render:
            after = drawing_payload_bytes(path)
        self.assertEqual(render.call_count, 1)
        self.assertNotEqual(before, after)

    def test_the_entry_lives_in_the_drawing_index_and_points_at_an_object(self) -> None:
        from cadgen.store import drawings as drawing_index
        from cadgen.store.index import read_entry
        from cadgen.store.objects import read_verified_object
        from cadgen.store.paths import index_dir

        path = self.drawing("indexed.dxf")
        data = drawing_payload_bytes(path)
        keys = sorted(entry.name for entry in index_dir("drawing").iterdir())
        self.assertTrue(keys)
        entry = read_entry("drawing", keys[0])
        self.assertEqual(entry["schemaVersion"], drawing_index.DRAWING_ENTRY_SCHEMA_VERSION)
        self.assertEqual(read_verified_object(entry["object"]), data)

    def test_the_key_changes_with_the_extraction_scheme(self) -> None:
        from cadgen.store import drawings as drawing_index

        document_hash = "a" * 64
        first = drawing_index.drawing_input_key(document_hash, scheme="one")
        second = drawing_index.drawing_input_key(document_hash, scheme="two")
        self.assertNotEqual(first, second)
        self.assertEqual(
            first, drawing_index.drawing_input_key(document_hash.upper(), scheme="one")
        )

    def test_a_damaged_object_reads_as_a_miss_rather_than_as_a_payload(self) -> None:
        from cadgen.store import drawings as drawing_index
        from cadgen.store.index import read_entry
        from cadgen.store.objects import object_path
        from cadgen.store.paths import index_dir

        path = self.drawing("damaged_object.dxf")
        expected = drawing_payload_bytes(path)
        key = next(entry.name for entry in index_dir("drawing").iterdir())
        object_path(read_entry("drawing", key)["object"]).write_bytes(b"{}")
        self.assertIsNone(drawing_index.read(key))
        self.assertEqual(drawing_payload_bytes(path), expected)

    def test_the_sweeper_keeps_a_cached_payload_reachable(self) -> None:
        from cadgen.store.gc import reachable_objects
        from cadgen.store.index import read_entry
        from cadgen.store.paths import index_dir

        drawing_payload_bytes(self.drawing("swept.dxf"))
        key = next(entry.name for entry in index_dir("drawing").iterdir())
        self.assertIn(read_entry("drawing", key)["object"], reachable_objects())


if __name__ == "__main__":
    unittest.main()
