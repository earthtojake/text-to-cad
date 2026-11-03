"""The plot payload: a KiCad board as the picture the viewer and `cad <type> snapshot` draw, from the file.

Built from the test board (`tests/python/support/kicad_board.py`, in the format KiCad 11's
headless API saves) without KiCad: the sheet and its layers in the order KiCad's PCB editor draws
them (the front copper active), pads on every copper layer they flash on with their numbers and
nets, tracks, the via's rings and the holes, the pour's saved fill and border hatch, text in the
permissive stroke font, mask and paste derived from the pads, the outline, the board's area, the
ratsnest from the engine's own connectivity (no drawing sheet). The payload is a function of
the file's bytes, and the store caches it by them. The JavaScript renderer's fixture
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

add_repo_path("packages/cad/src")

from cad.engine.formats.kicad.connectivity import Copper, ratsnest  # noqa: E402
from cad.engine.formats.kicad.plot import BOARD_BACKGROUND, build_plot, payload_bytes, plot_payload_bytes  # noqa: E402
from cad.engine.formats.kicad.stroke_font import GLYPHS, glyph_strokes, text_strokes  # noqa: E402
from cad.engine.formats.kicad import PLOT_SCHEMA_VERSION, PlotError  # noqa: E402


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

    def test_the_sheet_is_the_outline_and_the_layers_stack_as_kicad_draws_them(self) -> None:
        self.assertEqual((self.payload["schemaVersion"], self.payload["kind"], self.payload["generator"]), (PLOT_SCHEMA_VERSION, "board", "pcbnew 10.99"))
        self.assertEqual((self.sheet["name"], self.sheet["width"], self.sheet["height"], self.sheet["background"]), ("blinky", 40.0, 30.0, BOARD_BACKGROUND))
        # KiCad's PCB editor with the front copper active: the page and the board's area under all, the back
        # side, the user layers and the outline, the front side up to its copper, what goes through on top.
        self.assertEqual(
            [(layer["id"], layer["kind"], layer["side"]) for layer in self.sheet["layers"]],
            [("area", "area", "both"), ("B.Mask", "mask", "back"), ("B.Cu", "copper", "back"),
             ("Edge.Cuts", "outline", "both"), ("F.Fab", "fab", "front"), ("F.CrtYd", "courtyard", "front"), ("F.Paste", "paste", "front"),
             ("F.SilkS", "silk", "front"), ("F.Mask", "mask", "front"), ("F.Cu", "copper", "front"),
             ("drills", "drill", "both"), ("vias", "via", "both"), ("ratsnest", "ratsnest", "both"), ("names", "names", "both")],
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
        # A via is a ring on each copper layer it flashes on, its annular width wide, and its hole on `vias`:
        # golden in a plated wall, KiCad's 20 um of plating painted half as thick again.
        for layer in ("F.Cu", "B.Cu"):
            self.assertEqual(self.items(layer, t="circle"), [{"t": "circle", "at": [18.0, 27.0], "r": 0.225, "w": 0.15, "via": "through", "net": "GND"}])
        [hole] = self.layers["vias"]["items"]
        self.assertEqual(hole, {"t": "circle", "at": [18.0, 27.0], "r": 0.15, "w": 0.03, "hole": "via", "via": "through"})
        # A pad's hole is on `drills`, its wall as wide.
        self.assertEqual(sorted((item["hole"], item["r"], item["w"]) for item in self.layers["drills"]["items"]), [("pad", 0.5, 0.03), ("pad", 0.5, 0.03)])
        [fill] = self.items("B.Cu", pour=True)
        self.assertEqual((fill["t"], fill["net"], fill["pts"]), ("poly", "GND", [[1.5, 16.5], [19.5, 16.5], [19.5, 28.5], [1.5, 28.5]]))
        # The pour's drawn outline is a hairline, shown whether or not the fill is, with KiCad's edge hatch:
        # short strokes in from the outline every 0.5 mm, as point pairs.
        [outline] = self.items("B.Cu", t="path", closed=True)
        self.assertEqual((outline["w"], outline["pts"][0]), (0.0, [1.0, 16.0]))
        [hatch] = self.items("B.Cu", pairs=True)
        self.assertEqual((hatch["w"], len(hatch["pts"]) % 2), (0.0, 0))
        self.assertTrue(all(1 - 1e-6 <= x <= 20 + 1e-6 and 16 - 1e-6 <= y <= 29 + 1e-6 for x, y in hatch["pts"]))
        [edge] = self.layers["Edge.Cuts"]["items"]
        self.assertEqual((edge["t"], edge["w"], edge["closed"], len(edge["pts"])), ("path", 0.1, True, 4))
        # The board's area is the outline filled, under everything.
        self.assertEqual(self.layers["area"]["items"], [{"t": "poly", "pts": [[0.0, 0.0], [40.0, 0.0], [40.0, 30.0], [0.0, 30.0]]}])

    def test_pads_and_vias_are_named_as_kicad_names_them(self) -> None:
        # A through-hole pad's number above its net, centred on it, over everything (`names`).
        names = {(item["text"], tuple(item["at"])): item for item in self.layers["names"]["items"]}
        number, net = names[("1", (5.0, 14.6))], names[("VBUS", (5.0, 15.4857))]
        self.assertEqual((number["kind"], number["angle"], number["size"]), ("pad", 0.0, [0.578, 0.5202]))
        self.assertEqual(net["size"], [0.4335, 0.3901])
        # Shown once the view reads the pad: half a millimetre at KiCad's zoom 1 (91 dpi), over its 1.7 mm.
        self.assertAlmostEqual(number["lod"], 0.5 * 91 / 25.4 / 1.7, places=3)
        # A surface pad's names are on its copper; R1's pads stand taller than wide, so theirs read upwards,
        # the number left of the net name.
        r1 = [item for item in self.items("F.Cu", t="label") if 33 < item["at"][0] < 37]
        self.assertEqual(sorted((item["text"], item["angle"]) for item in r1), [("1", 90.0), ("2", 90.0), ("LED", 90.0), ("VBUS", 90.0)])
        by_text = {item["text"]: item["at"] for item in r1}
        self.assertLess(by_text["1"][0], 34.175)
        self.assertGreater(by_text["VBUS"][0], 34.175)
        # The via's net, in it, once its 0.6 mm reads (10 mm at zoom 1).
        [via] = [item for item in self.layers["names"]["items"] if item["kind"] == "via"]
        self.assertEqual((via["text"], via["at"]), ("GND", [18.0, 27.0]))
        self.assertAlmostEqual(via["lod"], 10 * 91 / 25.4 / 0.6, places=3)
        # The front copper's pads carry their clearance (the net class's default here), for KiCad's outline of it.
        self.assertEqual({item.get("clearance") for item in self.items("F.Cu", t="poly")}, {0.2})
        self.assertFalse(any("clearance" in item for item in self.items("B.Cu", t="poly")))

    def test_no_drawing_sheet_is_drawn_the_board_is_the_board_alone(self) -> None:
        # KiCad's page border and title block are not drawn: no sheet layer, and no page to frame.
        self.assertNotIn("sheet", self.layers)
        self.assertNotIn("page", self.sheet)

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
        [front] = [layer for layer in payload["sheets"][0]["layers"] if layer["id"] == "F.Cu"]
        [track] = [item for item in front["items"] if item["t"] == "path" and item.get("net") == "VBUS"]
        self.assertEqual(track["pts"], [[15.0, -5.0], [44.175, -5.0]])

    def test_every_request_reads_the_saved_file_without_a_cache(self) -> None:
        with tempfile.TemporaryDirectory() as cache, mock.patch.dict(os.environ, {"CAD_CACHE_DIR": cache}):
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


def _board(body: str, layers: str = '(0 "F.Cu" signal) (2 "B.Cu" signal)', version: str = "20241229",
           nets: str = '(net 0 "") (net 1 "A")') -> str:
    """A KiCad 9 board around ``body``: its copper ``layers``, ``nets``, a 30 x 20 mm outline."""
    return (f'(kicad_pcb (version {version}) (generator "pcbnew") (general (thickness 1.6)) (paper "A4")\n'
            f' (layers {layers} (25 "Edge.Cuts" user))\n {nets}\n'
            ' (gr_rect (start 0 0) (end 30 20) (stroke (width 0.1) (type solid)) (fill no) (layer "Edge.Cuts"))\n'
            f'{body}\n)')


def _pad(ref: str, at: str, pad: str) -> str:
    return (f'(footprint "t:{ref}" (layer "F.Cu") (at {at})\n'
            f'  (property "Reference" "{ref}" (at 0 -2) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))\n'
            f'  {pad})')


class ReaderEdgesTest(unittest.TestCase):
    """What KiCad's own demo boards showed the reader missing: pours that do not touch decided by their
    edges near each other, copper graphics on a net, a pad's drill offset, buried vias, KiCad 5's
    renamed copper layers."""

    def plot(self, text: str) -> dict:
        with tempfile.TemporaryDirectory(prefix="pcb-edges-") as folder:
            path = Path(folder) / "edge.kicad_pcb"
            path.write_text(text, encoding="utf-8")
            return build_plot(path)

    def test_polygons_overlap_answers_as_every_edge_pair_would(self) -> None:
        import math
        import random

        from cad.engine.formats.kicad.geometry import _segments_cross, inside, polygons_overlap

        def every_pair(first, second):
            if inside(first[0], second) or inside(second[0], first):
                return True
            edges = list(zip(second, [*second[1:], second[0]]))
            return any(_segments_cross(a, b, c, d) for a, b in zip(first, [*first[1:], first[0]]) for c, d in edges)

        def ring(cx, cy, count, radius, rng):
            return [(cx + radius * (0.6 + 0.4 * rng.random()) * math.cos(2 * math.pi * k / count),
                     cy + radius * (0.6 + 0.4 * rng.random()) * math.sin(2 * math.pi * k / count)) for k in range(count)]

        rng = random.Random(756)
        for _ in range(300):
            count = rng.choice([4, 12, 80, 400])  # 80 x 400 edges: bucketed
            first = ring(0, 0, count, 10, rng)
            second = ring(rng.uniform(-22, 22), rng.uniform(-22, 22), rng.choice([4, 80, 400]), 10, rng)
            self.assertEqual(polygons_overlap(first, second), every_pair(first, second))

    def test_a_copper_graphic_on_a_net_joins_what_it_covers(self) -> None:
        pads = (_pad("P1", "5 10", '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net 1 "A"))') + "\n" +
                _pad("P2", "15 10", '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net 1 "A"))'))
        self.assertEqual(1, self.plot(_board(pads))["unrouted"])
        joined = self.plot(_board(pads + '\n(gr_rect (start 4 9) (end 16 11) (stroke (width 0) (type solid)) '
                                          '(fill yes) (layer "F.Cu") (net 1))'))
        self.assertEqual(0, joined["unrouted"])
        layers = {layer["id"]: layer for layer in joined["sheets"][0]["layers"]}
        self.assertIn("A", {item.get("net") for item in layers["F.Cu"]["items"] if item["t"] == "poly" and "ref" not in item})

    def test_a_drill_offset_moves_the_copper_and_leaves_the_hole(self) -> None:
        payload = self.plot(_board(_pad("J1", "10 10", '(pad "1" thru_hole oval (at 0 0) (size 3 1.5) '
                                                       '(drill 0.8 (offset 0.6 0)) (layers "*.Cu" "*.Mask") (net 1 "A"))')))
        layers = {layer["id"]: layer for layer in payload["sheets"][0]["layers"]}
        [hole] = layers["drills"]["items"]
        self.assertEqual([10.0, 10.0], hole["at"])
        [shape] = [item for item in layers["F.Cu"]["items"] if item.get("ref") == "#J1.1"]
        left, _, right, _ = _extent(shape["pts"])
        self.assertAlmostEqual(10.6, (left + right) / 2, places=6)

    def test_a_buried_via_joins_only_its_own_layers(self) -> None:
        def board(kind: str) -> str:
            return _board(
                _pad("P1", "5 10", '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net 1 "A"))') + "\n" +
                _pad("P2", "15 10", '(pad "1" thru_hole circle (at 0 0) (size 1.6 1.6) (drill 0.8) (layers "*.Cu") (net 1 "A"))') +
                '\n(segment (start 5 10) (end 10 10) (width 0.25) (layer "F.Cu") (net 1))'
                '\n(segment (start 10 10) (end 15 10) (width 0.25) (layer "In2.Cu") (net 1))'
                f'\n(via {kind} (at 10 10) (size 0.6) (drill 0.3) (layers "In1.Cu" "In2.Cu") (net 1))',
                layers='(0 "F.Cu" signal) (4 "In1.Cu" signal) (6 "In2.Cu" signal) (2 "B.Cu" signal)')

        self.assertEqual(0, self.plot(board(""))["unrouted"], "a through via joins F.Cu to In2.Cu")
        self.assertEqual(1, self.plot(board("buried"))["unrouted"], "a buried via reaches no F.Cu")
        self.assertEqual(1, self.plot(board("blind"))["unrouted"])

    def test_kicad_5_renamed_copper_layers_are_the_copper(self) -> None:
        text = ('(kicad_pcb (version 20171130) (host pcbnew 5.1.0)\n'
                ' (layers (0 top_layer signal) (31 bottom_layer signal) (44 Edge.Cuts user))\n'
                ' (net 0 "") (net 1 GND)\n'
                ' (gr_line (start 0 0) (end 30 0) (layer Edge.Cuts) (width 0.1))\n'
                ' (gr_line (start 30 0) (end 30 20) (layer Edge.Cuts) (width 0.1))\n'
                ' (gr_line (start 30 20) (end 0 20) (layer Edge.Cuts) (width 0.1))\n'
                ' (gr_line (start 0 20) (end 0 0) (layer Edge.Cuts) (width 0.1))\n'
                ' (segment (start 5 5) (end 25 5) (width 0.25) (layer top_layer) (net 1))\n'
                ' (segment (start 5 15) (end 25 15) (width 0.25) (layer bottom_layer) (net 1)))')
        layers = {layer["id"]: layer for layer in self.plot(text)["sheets"][0]["layers"]}
        self.assertEqual(1, len([item for item in layers["F.Cu"]["items"] if item["t"] == "path"]))
        self.assertEqual(1, len([item for item in layers["B.Cu"]["items"] if item["t"] == "path"]))
        from cad.engine.formats.kicad.board_index import read_index

        self.assertEqual(2, len(read_index(text).tracks))


class KiCadDrawingTest(unittest.TestCase):
    """What KiCad's PCB editor draws that the file does not spell out: copper a pad or via keeps only
    where something joins it, the lines of a dimension, KiCad 5's shorthand, teardrops, rule areas,
    knocked-out text and text kept upright."""

    plot = ReaderEdgesTest.plot

    @staticmethod
    def layers(payload: dict) -> dict:
        return {layer["id"]: layer for layer in payload["sheets"][0]["layers"]}

    def test_a_via_with_its_unused_copper_removed_keeps_it_where_it_is_joined(self) -> None:
        board = _board(
            '(via (at 10 10) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (remove_unused_layers yes) (keep_end_layers yes)'
            ' (zone_layer_connections "In1.Cu") (net 1))\n'
            '(via (at 20 10) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (remove_unused_layers yes) (net 1))\n'
            '(via (at 25 15) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (remove_unused_layers no) (net 1))\n'
            '(segment (start 20 10) (end 25 10) (width 0.25) (layer "In2.Cu") (net 1))',
            layers='(0 "F.Cu" signal) (4 "In1.Cu" signal) (6 "In2.Cu" signal) (2 "B.Cu" signal)')
        layers = self.layers(self.plot(board))
        rings = {at: sorted(layer for layer, entry in layers.items() for item in entry["items"]
                            if item.get("via") and not item.get("hole") and item["at"] == [x, y])
                 for at, (x, y) in (("ends+zone", (10.0, 10.0)), ("track", (20.0, 10.0)), ("all", (25.0, 15.0)))}
        self.assertEqual(rings["ends+zone"], ["B.Cu", "F.Cu", "In1.Cu"])
        self.assertEqual(rings["track"], ["In2.Cu"])
        self.assertEqual(rings["all"], ["B.Cu", "F.Cu", "In1.Cu", "In2.Cu"])
        self.assertEqual(3, len(layers["vias"]["items"]), "every via's hole is drawn, whatever copper it keeps")

    def test_dimensions_are_the_lines_kicad_draws_for_them(self) -> None:
        text = '(gr_text "20.0000 mm" (at 15 0.8 0) (layer "Dwgs.User") (effects (font (size 1 1) (thickness 0.15))))'
        modern = _board('(dimension (type aligned) (layer "Dwgs.User") (pts (xy 5 5) (xy 25 5)) (height -3)'
                        ' (style (thickness 0.15) (arrow_length 1.27) (text_position_mode 0) (extension_height 0.58642)'
                        f' (extension_offset 0) keep_text_aligned) {text})', layers='(0 "F.Cu" signal) (2 "B.Cu" signal) (17 "Dwgs.User" user)')
        # KiCad 5 stored what it drew; KiCad reads it back as the same aligned dimension.
        legacy = _board(f'(dimension 20 (width 0.15) (layer Dwgs.User) {text}'
                        ' (feature1 (pts (xy 5 5) (xy 5 1.41358))) (feature2 (pts (xy 25 5) (xy 25 1.41358)))'
                        ' (crossbar (pts (xy 25 2) (xy 5 2))) (arrow1a (pts (xy 5 2) (xy 6 1.4))) (arrow1b (pts (xy 5 2) (xy 6 2.6)))'
                        ' (arrow2a (pts (xy 25 2) (xy 24 1.4))) (arrow2b (pts (xy 25 2) (xy 24 2.6))))',
                        layers='(0 "F.Cu" signal) (2 "B.Cu" signal) (17 "Dwgs.User" user)')
        drawn = []
        for board in (modern, legacy):
            items = self.layers(self.plot(board))["Dwgs.User"]["items"]
            segments = sorted(tuple(tuple(round(v, 3) for v in point) for point in item["pts"]) for item in items if item["t"] == "path")
            self.assertEqual(["20.0000 mm"], [item["text"] for item in items if item["t"] == "text"])
            drawn.append(segments)
        self.assertEqual(drawn[0], drawn[1])
        # Two extension lines up past the crossbar, the crossbar 3 mm out, and an arrowhead at each end.
        self.assertIn(((5.0, 5.0), (5.0, 1.414)), drawn[0])
        self.assertIn(((25.0, 5.0), (25.0, 1.414)), drawn[0])
        self.assertIn(((5.0, 2.0), (25.0, 2.0)), drawn[0])
        self.assertIn(((5.0, 2.0), (6.127, 1.414)), drawn[0])
        self.assertIn(((25.0, 2.0), (23.873, 2.586)), drawn[0])
        self.assertEqual(7, len(drawn[0]))
        # An orthogonal one measures along its axis: its second extension line runs to the point it measures.
        orthogonal = _board('(dimension (type orthogonal) (layer "Dwgs.User") (pts (xy 5 5) (xy 25 10)) (height 3) (orientation 0)'
                            f' (style (thickness 0.15) (arrow_length 1.27) (extension_height 0.58642) (extension_offset 0)) {text})',
                            layers='(0 "F.Cu" signal) (2 "B.Cu" signal) (17 "Dwgs.User" user)')
        lines = [tuple(tuple(round(v, 3) for v in point) for point in item["pts"])
                 for item in self.layers(self.plot(orthogonal))["Dwgs.User"]["items"] if item["t"] == "path"]
        self.assertIn(((5.0, 8.0), (25.0, 8.0)), lines)
        self.assertIn(((25.0, 7.414), (25.0, 10.0)), lines)

    def test_kicad_5_shorthand_is_read_as_kicad_reads_it(self) -> None:
        text = ('(kicad_pcb (version 20171130) (host pcbnew 5.1.0)\n'
                ' (layers (0 F.Cu signal) (31 B.Cu signal) (37 F.SilkS user) (44 Edge.Cuts user))\n'
                ' (net 0 "") (net 1 GND)\n'
                ' (net_class Default "default" (clearance 0.2) (trace_width 0.25) (via_dia 0.8) (via_drill 0.4) (uvia_dia 0.3)'
                ' (uvia_drill 0.1) (add_net GND))\n'
                ' (module R_0603 (layer F.Cu) (at 10 10)\n'
                '  (fp_text reference R7 (at 0 -1.5) (layer F.SilkS) (effects (font (size 1 1) (thickness 0.15))))\n'
                '  (fp_text user %R (at 0 1.5) (layer F.SilkS) (effects (font (size 1 1) (thickness 0.15)))))\n'
                ' (via (at 20 10) (size 0.8) (layers F.Cu B.Cu) (net 1))\n'
                ' (gr_line (start 0 0) (end 30 0) (layer Edge.Cuts) (width 0.1)) (gr_line (start 30 0) (end 30 20) (layer Edge.Cuts) (width 0.1))\n'
                ' (gr_line (start 30 20) (end 0 20) (layer Edge.Cuts) (width 0.1)) (gr_line (start 0 20) (end 0 0) (layer Edge.Cuts) (width 0.1)))')
        layers = self.layers(self.plot(text))
        # %R is the reference; a via with no drill takes its net class's.
        self.assertEqual(["R7", "R7"], [item["text"] for item in layers["F.SilkS"]["items"] if item["t"] == "text"])
        [hole] = layers["vias"]["items"]
        self.assertEqual(0.2, hole["r"])
        [ring] = [item for item in layers["F.Cu"]["items"] if item.get("via")]
        self.assertEqual((0.3, 0.2), (ring["r"], ring["w"]))

    def test_teardrops_rule_areas_and_knocked_out_text(self) -> None:
        board = _board(
            '(zone (net 1) (net_name "A") (layer "F.Cu") (hatch full 0.1) (attr (teardrop (type padvia)))'
            ' (polygon (pts (xy 10 10) (xy 12 10) (xy 11 12))) (filled_polygon (layer "F.Cu") (pts (xy 10 10) (xy 12 10) (xy 11 12))))\n'
            '(zone (net 0) (net_name "") (layers "F.Cu" "B.Cu") (hatch edge 0.5) (keepout (tracks not_allowed) (vias not_allowed)'
            ' (pads allowed) (copperpour not_allowed) (footprints allowed)) (polygon (pts (xy 2 2) (xy 8 2) (xy 8 8) (xy 2 8))))\n'
            '(gr_text "KO" (at 20 15 0) (layer "F.SilkS" knockout) (effects (font (size 1 1) (thickness 0.15))))',
            layers='(0 "F.Cu" signal) (2 "B.Cu" signal) (5 "F.SilkS" user)')
        layers = self.layers(self.plot(board))
        front = layers["F.Cu"]["items"]
        # A teardrop is a pour drawn opaque, with no outline of its own.
        [tear] = [item for item in front if item.get("pour")]
        self.assertTrue(tear["teardrop"])
        self.assertFalse(any(item["t"] == "path" and item["pts"][0] == [10.0, 10.0] for item in front))
        # A rule area is its outline and hatch on each layer it keeps out of, and no fill.
        for layer in ("F.Cu", "B.Cu"):
            outline = [item for item in layers[layer]["items"] if item.get("closed") and item["pts"][0] == [2.0, 2.0]]
            self.assertEqual(1, len(outline), layer)
            self.assertTrue(any(item.get("pairs") for item in layers[layer]["items"]), layer)
        # Knocked-out text carries the box the letters are cut from, round them.
        [ko] = [item for item in layers["F.SilkS"]["items"] if item["t"] == "text"]
        corners = ko["knockout"]
        xs, ys = [x for x, _ in corners], [y for _, y in corners]
        stroke_xs = [x for stroke in ko["strokes"] for x, _ in stroke]
        self.assertLess(min(xs), min(stroke_xs))
        self.assertGreater(max(xs), max(stroke_xs))
        self.assertLess(min(ys), 14.5)
        self.assertGreater(max(ys), 15.5)

    def test_the_index_carries_rule_areas_apart_and_what_kicad_saved_locked(self) -> None:
        from cad.engine.formats.kicad.board_index import BoardView, read_index
        board = _board(
            '(zone (net 0) (net_name "") (layers "F.Cu" "B.Cu") (uuid "0a000000-0000-4000-8000-000000000001") (name "keep")'
            ' (hatch edge 0.5) (keepout (tracks not_allowed) (vias not_allowed) (pads allowed) (copperpour not_allowed) (footprints allowed))'
            ' (polygon (pts (xy 2 2) (xy 8 2) (xy 8 8) (xy 2 8))))\n'
            '(segment (start 1 1) (end 9 1) (width 0.25) (layer "F.Cu") (net 1) (locked yes) (uuid "0a000000-0000-4000-8000-000000000002"))\n'
            '(gr_line (start 1 3) (end 9 3) (stroke (width 0.1) (type solid)) (layer "F.SilkS") (locked yes) (uuid "0a000000-0000-4000-8000-000000000003"))\n'
            + _pad("U1", "15 10", '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))').replace('(layer "F.Cu")', '(locked yes) (layer "F.Cu")', 1),
            layers='(0 "F.Cu" signal) (2 "B.Cu" signal) (5 "F.SilkS" user)')
        payload = self.plot(board)
        zones = payload["board"]["zones"]
        # A rule area is no pour: one entry per layer it keeps out of, marked, with no net and no fill.
        self.assertEqual([(zone["layer"], zone.get("rule"), zone["net"]) for zone in zones], [("F.Cu", True, None), ("B.Cu", True, None)])
        self.assertEqual([part.get("locked") for part in payload["board"]["parts"]], [True])
        self.assertEqual([track.get("locked") for track in payload["board"]["tracks"]], [True])
        [line] = [item for item in self.layers(payload)["F.SilkS"]["items"] if item.get("id") == "0a000000-0000-4000-8000-000000000003"]
        self.assertTrue(line["locked"])
        view = BoardView(Path("rules.kicad_pcb"), read_index(board))
        self.assertEqual(view.zones, ())
        area = view.resolve("#zone:0a000000-0000-4000-8000-000000000001")
        self.assertTrue(area.rule)
        self.assertEqual((area.name, area.layers), ("keep", ("F.Cu", "B.Cu")))

    def test_a_part_carries_the_schematic_sheet_that_placed_it(self) -> None:
        from cad.engine.formats.kicad.board_index import read_index
        board = _board(
            _pad("U1", "5 5", '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))').replace('(at 5 5)', '(at 5 5) (sheetname "/power/") (sheetfile "power.kicad_sch")', 1)
            + _pad("U2", "10 5", '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))').replace('(at 10 5)', '(at 10 5) (sheetname "buspci.sch")', 1)
            + _pad("U3", "15 5", '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))').replace('(at 15 5)', '(at 15 5) (sheetname "/power/ldo/")', 1)
            + _pad("U4", "20 5", '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu"))'))
        self.assertEqual({part.ref: part.sheet for part in read_index(board).parts}, {"U1": "power", "U2": "buspci", "U3": "power/ldo", "U4": None})
        parts = {part["ref"]: part for part in self.plot(board)["board"]["parts"]}
        self.assertEqual((parts["U1"]["sheet"], "sheet" in parts["U4"]), ("power", False))

    def test_footprint_text_reads_upright_unless_unlocked(self) -> None:
        def strokes(angle: str, unlocked: str = "") -> list:
            board = _board(_pad("U1", "15 10", f'(fp_text user "AB" (at 0 2 {angle}) {unlocked}(layer "F.SilkS") '
                                               '(effects (font (size 1 1) (thickness 0.15))))'),
                           layers='(0 "F.Cu" signal) (2 "B.Cu" signal) (5 "F.SilkS" user)')
            return [item["strokes"] for item in self.layers(self.plot(board))["F.SilkS"]["items"] if item.get("text") == "AB"][0]

        self.assertEqual(strokes("0"), strokes("180"), "turned half a turn, it is turned back to read")
        self.assertNotEqual(strokes("0"), strokes("180", "(unlocked yes) "))


class TrackNameTest(unittest.TestCase):
    """A track's net name, which the plot does not carry: the renderers lay it out as KiCad does, by one rule."""

    def test_a_track_s_name_is_laid_out_as_the_viewer_lays_it(self) -> None:
        from cad.engine.formats.kicad.labels import KICAD_PX_PER_MM, is_track, track_labels, track_name_detail

        # plot2d/trackNames.test.js reads the same numbers.
        def laid(pts, net="CLK", viewport=(30, 20)):
            return [(label["text"], [round(v, 3) for v in label["at"]], [round(v, 3) for v in label["size"]], round(label["angle"], 3),
                     round(label["w"], 3)) for label in track_labels({"pts": pts, "w": 0.25, "net": net}, viewport)]

        self.assertEqual(laid([[0, 0], [10, 0]], "/cpu/CLK"), [("CLK", [5, 0], [0.138, 0.138], 0, 0.021)])
        self.assertEqual([label[3] for label in laid([[0, 10], [0, 0]])], [90])
        self.assertEqual([label[3] for label in laid([[0, 0], [4, 4]])], [-45])
        self.assertEqual([label[3] for label in laid([[4, 0], [0, 4]])], [45])
        self.assertEqual(laid([[0, 0], [0.7, 0]]), [], "shorter than its name")
        self.assertEqual([label[1] for label in laid([[0, 0], [90, 0]])], [[22.5, 0], [45, 0], [67.5, 0]])
        self.assertEqual(len(laid([[0, 0], [0, 50]])), 3, "KiCad rounds a half away from zero")
        self.assertEqual(len(laid([[0, 0], [40, 40]])), 2)
        self.assertEqual(laid([[0, 0], [3, 1], [6, 0]]), [("CLK", [3, 1], [0.138, 0.138], -18.435, 0.021)])
        self.assertTrue(is_track({"t": "path", "pts": [[0, 0], [1, 0]], "w": 0.25, "net": "GND"}))
        self.assertFalse(is_track({"t": "path", "pts": [[0, 0], [1, 0], [1, 1]], "w": 0, "closed": True, "net": "GND"}))
        self.assertFalse(is_track({"t": "path", "pts": [[0, 0], [1, 1]], "w": 0.1, "pairs": True, "net": "GND"}))
        self.assertAlmostEqual(track_name_detail(0.25), 16 * KICAD_PX_PER_MM)

    def test_the_snapshot_writes_a_track_s_name_once_the_view_reads_it(self) -> None:
        import numpy
        from PIL import Image

        from cad.engine.render.board import _Painter

        layer = {"id": "F.Cu", "kind": "copper", "items": [{"t": "path", "pts": [[0, 2], [20, 2]], "w": 1, "net": "VIN"}]}

        def lettered(scale: float) -> int:
            image = Image.new("RGB", (round(20 * scale), round(4 * scale)), BOARD_BACKGROUND)
            _Painter(image, lambda point: (point[0] * scale, point[1] * scale), scale, 1, BOARD_BACKGROUND).layer(
                layer, poured=True, vias=True, names=True, mirrored=False, viewport=(image.width / scale, image.height / scale))
            # The track is KiCad's red (its green 52); its name, KiCad's light name colour over it, is far greener.
            return int((numpy.asarray(image)[..., 1] > 150).sum())

        self.assertEqual(lettered(10), 0, "4 mm over the 1 mm track: 14.3 px per mm before it reads")
        self.assertGreater(lettered(40), 0)


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
        # Italic leans right as KiCad slants it: an eighth of the height above the baseline.
        [upright], [leaning] = text_strokes("l", size=(1, 1)), text_strokes("l", size=(1, 1), italic=True)
        self.assertAlmostEqual((leaning[0][0] - leaning[-1][0]) - (upright[0][0] - upright[-1][0]), (upright[-1][1] - upright[0][1]) / 8, places=6)

    def test_the_viewer_lays_labels_out_in_the_same_font(self) -> None:
        # The board view lays a pad's names out itself (`@cad/core`'s plot2d/strokeFont.js): its table is this one.
        source = repo_path("packages", "core", "src", "lib", "plot2d", "strokeFont.js").read_text(encoding="utf-8")
        table = source[source.index("export const GLYPHS = Object.freeze(["):]
        table = table[:table.index("]);")]
        self.assertEqual(tuple(json.loads(f"[{table.split('[', 1)[1].rstrip().rstrip(',')}]")), GLYPHS)


if __name__ == "__main__":
    unittest.main()
