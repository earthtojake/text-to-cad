"""The plot payload: a KiCad board as the picture the viewer and `cadgen pcb snapshot` draw, from the file.

Built from the test board (`tests/python/support/kicad_board.py`, in the format KiCad 11's
headless API saves) without KiCad: the sheet and its layers in KiCad's stacking order, pads
on every copper layer they are on, tracks, the via and the holes, the pour's saved fill, text
in the permissive stroke font, mask and paste derived from the pads, the outline, and the
ratsnest from cadgen's own connectivity. The payload is a function of the file's bytes, and
the store caches it by them. The JavaScript renderer's fixture
(`packages/ui/src/renderers/board/__fixtures__/board.plot.json`) is this same board's payload.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.kicad_board import BOARD, write_board
from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cadgen/src")

from cadgen.engine.formats.kicad.connectivity import Copper, ratsnest  # noqa: E402
from cadgen.engine.formats.kicad.plot import BOARD_BACKGROUND, build_plot, payload_bytes, plot_payload_bytes  # noqa: E402
from cadgen.engine.formats.kicad.stroke_font import GLYPHS, glyph_strokes, text_strokes  # noqa: E402
from cadgen.plot import PLOT_SCHEMA_VERSION, PlotError  # noqa: E402


def _extent(points):
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


class PlotPayloadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls._tmp.name)
        cls.path = write_board(cls.folder)
        cls.payload = build_plot(cls.path)
        cls.sheet = cls.payload["sheets"][0]
        cls.layers = {layer["id"]: layer for layer in cls.sheet["layers"]}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def items(self, layer: str, **where):
        return [item for item in self.layers[layer]["items"] if all(item.get(key) == value for key, value in where.items())]

    def test_the_sheet_is_the_outline_and_the_layers_stack_back_to_front(self) -> None:
        self.assertEqual((self.payload["schemaVersion"], self.payload["kind"], self.payload["generator"]), (PLOT_SCHEMA_VERSION, "board", "pcbnew 10.99"))
        self.assertEqual((self.sheet["name"], self.sheet["width"], self.sheet["height"], self.sheet["background"]), ("blinky", 40.0, 30.0, BOARD_BACKGROUND))
        self.assertEqual(
            [(layer["id"], layer["kind"], layer["side"]) for layer in self.sheet["layers"]],
            [("B.Mask", "mask", "back"), ("B.Cu", "copper", "back"), ("F.Cu", "copper", "front"), ("F.Mask", "mask", "front"),
             ("F.Paste", "paste", "front"), ("F.SilkS", "silk", "front"), ("F.Fab", "fab", "front"), ("F.CrtYd", "courtyard", "front"),
             ("Edge.Cuts", "outline", "both"), ("vias", "via", "both"), ("ratsnest", "ratsnest", "both"), ("drills", "drill", "both")],
        )
        # The board's index rides beside the picture, in sheet millimetres; KiCad's origin is the sheet's corner here.
        self.assertEqual(self.payload["board"]["origin"], [0.0, 0.0])
        self.assertEqual([part["ref"] for part in self.payload["board"]["parts"]], ["D1", "J1", "R1"])

    def test_pads_are_polygons_on_every_copper_layer_they_are_on_with_their_reference_and_net(self) -> None:
        top = {item["ref"]: item for item in self.items("F.Cu", t="poly")}
        self.assertEqual(sorted(top), ["#D1.1", "#D1.2", "#J1.1", "#J1.2", "#R1.1", "#R1.2"])
        self.assertEqual((top["#R1.2"]["net"], top["#J1.2"]["net"]), ("LED", "GND"))
        self.assertEqual(_extent(top["#J1.1"]["pts"]), (4.15, 14.15, 5.85, 15.85))
        # Through-hole pads reach the bottom copper too; surface-mount pads do not.
        self.assertEqual(sorted(item["ref"] for item in self.items("B.Cu", t="poly") if "ref" in item), ["#J1.1", "#J1.2"])
        # D1 is turned a quarter turn: its 0.8 x 0.95 pad lies on its side, and its pads stand along y.
        left, top_, right, bottom = _extent(top["#D1.1"]["pts"])
        self.assertAlmostEqual(right - left, 0.95, places=6)
        self.assertAlmostEqual(bottom - top_, 0.8, places=6)
        self.assertEqual([round(top[ref]["pts"][0][0], 3) > 19 for ref in ("#D1.1", "#D1.2")], [True, True])

    def test_tracks_vias_pours_and_holes(self) -> None:
        [track] = self.items("F.Cu", t="path", net="VBUS")
        self.assertEqual((track["w"], track["pts"]), (1.0, [[5.0, 15.0], [34.175, 15.0]]))
        [via] = self.layers["vias"]["items"]
        self.assertEqual(via, {"t": "circle", "at": [18.0, 27.0], "r": 0.3, "w": 0.0, "via": "through", "net": "GND"})
        holes = sorted((item["hole"], item["r"]) for item in self.layers["drills"]["items"])
        self.assertEqual(holes, [("pad", 0.5), ("pad", 0.5), ("via", 0.15)])
        [fill] = self.items("B.Cu", pour=True)
        self.assertEqual((fill["t"], fill["net"], fill["pts"]), ("poly", "GND", [[1.5, 16.5], [19.5, 16.5], [19.5, 28.5], [1.5, 28.5]]))
        # The pour's drawn outline is a hairline, shown whether or not the fill is.
        [outline] = self.items("B.Cu", t="path")
        self.assertEqual((outline["w"], outline["closed"], outline["pts"][0]), (0.0, True, [1.0, 16.0]))
        [edge] = self.layers["Edge.Cuts"]["items"]
        self.assertEqual((edge["t"], edge["w"], edge["closed"], len(edge["pts"])), ("path", 0.1, True, 4))

    def test_mask_and_paste_are_derived_from_the_pads(self) -> None:
        self.assertEqual(sorted(item["ref"] for item in self.layers["F.Mask"]["items"]), ["#D1.1", "#D1.2", "#J1.1", "#J1.2", "#R1.1", "#R1.2"])
        self.assertEqual(sorted(item["ref"] for item in self.layers["B.Mask"]["items"]), ["#J1.1", "#J1.2"])
        # Paste goes on the surface-mount pads alone, as their layers say.
        self.assertEqual(sorted(item["ref"] for item in self.layers["F.Paste"]["items"]), ["#D1.1", "#D1.2", "#R1.1", "#R1.2"])
        self.assertNotIn("B.Paste", self.layers)
        # A mask margin grows the opening: the board's clearance is 0 here, so the opening is the pad.
        [opening] = self.items("F.Mask", ref="#R1.1")
        self.assertEqual(opening["pts"], self.items("F.Cu", ref="#R1.1")[0]["pts"])
        self.assertNotIn("w", opening)

    def test_text_is_drawn_in_strokes_where_kicad_puts_it(self) -> None:
        texts = {item["text"]: item for item in self.layers["F.SilkS"]["items"] if item["t"] == "text"}
        self.assertEqual(sorted(texts), ["D1", "J1", "R1", "blinky"])
        title = texts["blinky"]
        left, top, right, bottom = _extent([point for stroke in title["strokes"] for point in stroke])
        # 1.5 mm capitals, centred on (20, 5), 0.3 mm strokes; a hole in the 'b' and the 'k' make it several strokes.
        self.assertEqual(title["w"], 0.3)
        self.assertAlmostEqual((left + right) / 2, 20.0, delta=0.1)  # centred on its advance, as KiCad centres it
        self.assertAlmostEqual(top, 5 - 0.75, delta=0.1)  # the capitals' box; the font's ascenders stand a shade taller
        self.assertGreater(len(title["strokes"]), 6)
        # D1's reference turns with its part: taller than wide, and it names the part.
        left, top, right, bottom = _extent([point for stroke in texts["D1"]["strokes"] for point in stroke])
        self.assertGreater(bottom - top, right - left)
        self.assertEqual(texts["D1"]["ref"], "#D1")
        # Hidden fields (Datasheet, Description) are not drawn; the fabrication layer carries the values and
        # the `${REFERENCE}` texts the two 0603 footprints draw there.
        self.assertEqual(sorted(item["text"] for item in self.layers["F.Fab"]["items"] if item["t"] == "text"), ["10k", "Conn_01x02", "D1", "LED", "R1"])

    def test_the_ratsnest_is_the_one_connection_copper_does_not_make(self) -> None:
        self.assertEqual(self.payload["unrouted"], 1)
        [line] = self.layers["ratsnest"]["items"]
        self.assertEqual(line["t"], "path")
        self.assertEqual(sorted(line["pts"]), [[20.0, 23.175], [35.825, 15.0]])  # D1.2 to R1.2, the LED net

    def test_the_payload_is_a_function_of_the_file(self) -> None:
        first = payload_bytes(self.payload)
        self.assertEqual(first, payload_bytes(build_plot(self.path)))
        self.assertEqual(json.loads(first)["schemaVersion"], PLOT_SCHEMA_VERSION)
        # Moving the outline moves the sheet, and KiCad's origin with it: a reference stays in KiCad's frame.
        moved = self.folder / "moved.kicad_pcb"
        moved.write_text(BOARD.replace("(gr_rect (start 0 0) (end 40 30)", "(gr_rect (start -10 20) (end 30 50)"), encoding="utf-8")
        payload = build_plot(moved)
        self.assertEqual((payload["sheets"][0]["width"], payload["sheets"][0]["height"], payload["board"]["origin"]), (40.0, 30.0, [10.0, -20.0]))
        [track] = [item for item in payload["sheets"][0]["layers"][2]["items"] if item["t"] == "path" and item.get("net") == "VBUS"]
        self.assertEqual(track["pts"], [[15.0, -5.0], [44.175, -5.0]])

    def test_every_request_reads_the_saved_file_without_a_cache(self) -> None:
        with tempfile.TemporaryDirectory() as cache, mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": cache}):
            path = Path(cache) / "edited.kicad_pcb"
            path.write_bytes(self.path.read_bytes())
            first = plot_payload_bytes(path)
            self.assertEqual(first, payload_bytes(build_plot(path)))
            path.write_text(BOARD.replace('(width 1) (layer "F.Cu") (net "VBUS")',
                                               '(width 0.5) (layer "F.Cu") (net "VBUS")'), encoding="utf-8")
            self.assertNotEqual(plot_payload_bytes(path), first)
            self.assertEqual(list(Path(cache).iterdir()), [path])

    def test_what_is_not_a_board_is_refused_with_the_reason(self) -> None:
        for name, text, message in (
            ("notes.step", "ISO-10303-21;", r"notes\.step is not a KiCad board \(\.kicad_pcb\)"),
            ("sch.kicad_pcb", "(kicad_sch (version 20231120))", r"a \.kicad_pcb starts with \(kicad_pcb"),
            ("broken.kicad_pcb", "(kicad_pcb (version", r"not a readable KiCad board \("),
        ):
            path = self.folder / name
            path.write_text(text, encoding="utf-8")
            with self.subTest(name=name), self.assertRaisesRegex(PlotError, message):
                build_plot(path)
        (self.folder / "bytes.kicad_pcb").write_bytes(b"\xff\xfe(kicad_pcb)")
        with self.assertRaisesRegex(PlotError, "not UTF-8 text"):
            build_plot(self.folder / "bytes.kicad_pcb")
        with self.assertRaisesRegex(PlotError, "does not exist"):
            build_plot(self.folder / "missing.kicad_pcb")

    def test_the_javascript_fixture_is_this_boards_payload(self) -> None:
        fixture = repo_path("packages", "ui", "src", "renderers", "board", "__fixtures__", "board.plot.json")
        self.assertEqual(json.loads(fixture.read_text(encoding="utf-8")), self.payload, "regenerate the fixture: see its README")


class ConnectivityTest(unittest.TestCase):
    """The ratsnest joins what copper leaves apart: touching copper on a shared layer is one piece."""

    @staticmethod
    def pad(net, at, layers=("F.Cu",), size=1.0):
        x, y = at
        h = size / 2
        return Copper.polygon(net, layers, [(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)], anchor=at, pad=True)

    def test_a_track_joins_pads_on_its_layer_and_a_via_joins_layers(self) -> None:
        a, b = self.pad("N", (0, 0)), self.pad("N", (10, 0))
        self.assertEqual(ratsnest([a, b]), [((0, 0), (10, 0))])
        self.assertEqual(ratsnest([a, b, Copper.segment("N", "F.Cu", (0, 0), (10, 0), 0.25)]), [])
        # A track that stops short of the pad leaves the connection to make; one on the other layer too.
        self.assertEqual(len(ratsnest([a, b, Copper.segment("N", "F.Cu", (0, 0), (9, 0), 0.25)])), 1)
        self.assertEqual(len(ratsnest([a, b, Copper.segment("N", "B.Cu", (0, 0), (10, 0), 0.25)])), 1)
        below = self.pad("N", (10, 0), layers=("B.Cu",))
        via = Copper.disc("N", ("F.Cu", "B.Cu"), (5, 0), 0.6)
        self.assertEqual(ratsnest([a, below, via, Copper.segment("N", "F.Cu", (0, 0), (5, 0), 0.25), Copper.segment("N", "B.Cu", (5, 0), (10, 0), 0.25)]), [])

    def test_a_pour_joins_the_pads_it_holds_and_the_tree_spans_the_rest(self) -> None:
        pads = [self.pad("GND", at) for at in ((0, 0), (20, 0), (40, 0), (0, 30))]
        fill = Copper.polygon("GND", ["F.Cu"], [(-5, -5), (25, -5), (25, 5), (-5, 5)])
        lines = ratsnest([*pads, fill])
        # The pour joins the first two pads; two lines remain, each to the nearest pad of the tree.
        self.assertEqual(len(lines), 2)
        self.assertIn(((20, 0), (40, 0)), lines)
        self.assertIn(((0, 0), (0, 30)), lines)
        # A net of one pad, and copper on no net, draw nothing.
        self.assertEqual(ratsnest([self.pad("ONE", (0, 0)), Copper.segment("", "F.Cu", (0, 0), (1, 0), 0.2)]), [])


class StrokeFontTest(unittest.TestCase):
    def test_the_font_covers_ascii_and_stands_a_capital_at_the_text_size(self) -> None:
        self.assertEqual(len(GLYPHS), 95)
        left, right, strokes = glyph_strokes("H")
        self.assertEqual((left, right, len(strokes)), (-11.0, 11.0, 3))
        for text, size, at, justify, box in (
            ("H", (1, 1), (10, 20), (), (9.667, 19.5, 10.333, 20.5)),  # centred on the anchor, 1 mm tall
            ("H", (1, 1), (10, 20), ("left", "top"), (10.0, 20.0, 0.667, 21.0)),
            ("H", (2, 1), (0, 0), (), (-0.333, -1.0, 0.333, 1.0)),  # twice as tall, as wide as before
        ):
            with self.subTest(text=text, justify=justify):
                points = [point for stroke in text_strokes(text, size=size, at=at, justify=justify) for point in stroke]
                left, top, right, bottom = _extent(points)
                self.assertAlmostEqual(left, box[0] if box[2] > box[0] else left, places=3)
                self.assertAlmostEqual(top, box[1], places=3)
                self.assertAlmostEqual(bottom, box[3], places=3)
        # Turned a quarter turn the text stands along y; mirrored it reads the other way.
        turned = _extent([point for stroke in text_strokes("H", size=(1, 1), at=(10, 20), angle=90) for point in stroke])
        self.assertAlmostEqual(turned[2] - turned[0], 1.0, places=3)
        plain = text_strokes("L", size=(1, 1), justify=("left",))
        mirrored = text_strokes("L", size=(1, 1), justify=("left",), mirror=True)
        self.assertAlmostEqual(_extent([p for s in plain for p in s])[0], -_extent([p for s in mirrored for p in s])[2], places=6)
        # A character the font lacks is a box, and an empty size draws nothing.
        self.assertEqual(len(text_strokes("é", size=(1, 1))), 1)
        self.assertEqual(text_strokes("x", size=(0, 0)), [])


if __name__ == "__main__":
    unittest.main()
