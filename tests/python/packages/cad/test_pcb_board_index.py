"""`pcb.read_board`: a KiCad board read back as what a person points at, without KiCad.

The test board (`tests/python/support/kicad_board.py`) is in the format KiCad 11's headless
API saves: footprints placed by a `transform`, one of them turned and one through-hole, a
saved zone fill. Every answer is in KiCad's own frame (millimetres, y down), the frame a
script's `Vector2.from_xy_mm` takes, so a reference the viewer copies pastes straight back.
Older boards KiCad still opens read too: numbered nets, a KiCad 5 board's modules and arcs.
"""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_board import UUIDS, write_board
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.engine.formats.kicad.board_index import (  # noqa: E402
    Area, BoardView, Copper, Dimension, Net, Pad, Part, Point, Shape, Text, Track, Via, Zone, item_id, read_board, read_index,
)
from cad.engine.formats.kicad.geometry import inside  # noqa: E402
from cad.engine.formats.kicad.plot import build_plot  # noqa: E402
from cad.engine.formats.kicad import sexpr  # noqa: E402


class BoardIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls._tmp.name)
        cls.path = write_board(cls.folder)
        cls.view = read_board(cls.path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_parts_are_placed_by_their_transform_in_kicads_frame(self) -> None:
        placed = {part.ref: (part.at, part.rotation, part.side) for part in self.view.parts}
        self.assertEqual(placed, {"J1": ((5.0, 15.0), 0.0, "top"), "R1": ((35.0, 15.0), 0.0, "top"), "D1": ((20.0, 24.0), 90.0, "top")})
        pads = {f"{pad.part}.{pad.number}": pad for part in self.view.parts for pad in part.pads}
        for name, at in {
            "J1.1": (5.0, 15.0), "J1.2": (5.0, 17.54), "R1.1": (34.175, 15.0), "R1.2": (35.825, 15.0),
            # D1 is turned a quarter turn counter-clockwise: its pads lie along y, pad 1 below the centre.
            "D1.1": (20.0, 24.825), "D1.2": (20.0, 23.175),
        }.items():
            with self.subTest(pad=name):
                self.assertAlmostEqual(pads[name].at[0], at[0], places=6)
                self.assertAlmostEqual(pads[name].at[1], at[1], places=6)
        self.assertEqual((pads["J1.1"].side, pads["J1.1"].drill, pads["R1.1"].side, pads["R1.1"].drill), ("both", 1.0, "top", None))

    def test_a_pads_polygon_holds_its_centre_and_turns_with_its_part(self) -> None:
        def extent(pad: Pad) -> tuple[float, float]:
            xs, ys = [x for x, _ in pad.polygon], [y for _, y in pad.polygon]
            return round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)

        for pad in self.view.pads:
            self.assertTrue(inside(pad.at, pad.polygon), pad)
        # The library pad is 0.8 x 0.95; D1 is turned a quarter turn, R1 is not.
        self.assertEqual(extent(self.view.part("R1").pad("1")), (0.8, 0.95))
        self.assertEqual(extent(self.view.part("D1").pad("1")), (0.95, 0.8))
        self.assertEqual(extent(self.view.part("J1").pad("1")), (1.7, 1.7))

    def test_a_part_resolves_with_its_fields(self) -> None:
        part = self.view.resolve("#R1")
        self.assertIsInstance(part, Part)
        self.assertEqual((part.ref, part.value, part.footprint, part.at), ("R1", "10k", "Resistor_SMD:R_0603_1608Metric", (35.0, 15.0)))
        self.assertEqual(part.fields, {})  # the hidden Datasheet and Description are empty
        # The courtyard is the part's outline: the 0603's is 2.96 x 1.46.
        xs = [x for x, _ in part.outline]
        self.assertAlmostEqual(max(xs) - min(xs), 2.96, places=6)

    def test_the_outline_closes_and_says_what_is_on_the_board(self) -> None:
        self.assertEqual([(len(line), line[0] == line[-1]) for line in self.view.outline], [(5, True)])
        self.assertTrue(self.view.at(20, 15).on_board)
        self.assertFalse(self.view.at(45, 15).on_board)

    def test_a_pad_and_a_net_resolve_with_what_is_on_them(self) -> None:
        pad = self.view.resolve("#R1.2")
        self.assertEqual((pad.part, pad.number, pad.net, pad.side), ("R1", "2", "LED", "top"))
        gnd = self.view.resolve("#net:GND")
        self.assertIsInstance(gnd, Net)
        self.assertEqual(gnd.netclass, "Default")
        self.assertEqual(sorted(f"{pad.part}.{pad.number}" for pad in gnd.pads), ["D1.1", "J1.2"])
        self.assertEqual((len(gnd.tracks), len(gnd.vias), len(gnd.zones)), (1, 1, 1))
        self.assertEqual(gnd.zones[0].layer, "B.Cu")
        self.assertEqual(len(gnd.zones[0].fills), 1)

    def test_copper_resolves_to_what_the_net_has_at_the_point(self) -> None:
        track = self.view.resolve("#net:VBUS@x20y15")
        self.assertIsInstance(track, Copper)
        self.assertEqual([item.kind for item in track.items], ["track"])
        at_via = self.view.resolve("#net:GND@x18y27")  # the track ends on the via, in the pour
        self.assertEqual(sorted(item.kind for item in at_via.items), ["track", "via", "zone"])
        with self.assertRaisesRegex(ValueError, r"no copper at \(30, 5\): the nearest is"):
            self.view.resolve("#net:VBUS@x30y5")

    def test_a_point_says_what_is_there(self) -> None:
        on_pad = self.view.resolve("#@x5y15")
        self.assertIsInstance(on_pad, Point)
        self.assertTrue(on_pad.on_board)
        self.assertEqual([(pad.part, pad.number) for pad in on_pad.pads], [("J1", "1")])
        self.assertEqual([part.ref for part in on_pad.parts], ["J1"])
        self.assertEqual([item.kind for item in self.view.at(10, 20).copper], ["zone"])

    def test_a_reference_must_name_this_board(self) -> None:
        # A quoted path is JSON, as a copied one is: a Windows path's backslashes are escaped.
        for ref in ("blinky.kicad_pcb#J1", f"{self.path}#J1", f"{json.dumps(str(self.path))}#J1"):
            with self.subTest(ref=ref):
                self.assertEqual(self.view.resolve(ref).ref, "J1")
        with self.assertRaisesRegex(ValueError, "reference names 'other.kicad_pcb', but this board is"):
            self.view.resolve("other.kicad_pcb#J1")

    def test_a_token_of_several_names_each_and_a_bad_one_teaches(self) -> None:
        answers = self.view.resolve_all("blinky.kicad_pcb#J1,R1.2,net:GND")
        self.assertEqual([answer.kind for answer in answers], ["part", "pad", "net"])
        with self.assertRaisesRegex(ValueError, "names 3 things; resolve_all"):
            self.view.resolve("blinky.kicad_pcb#J1,R1.2,net:GND")
        for ref, message in (
            ("#U9", "has no part U9; its parts are D1, J1, R1"),
            ("#R12", "has no part R12; did you mean R1"),
            ("#R1.7", "R1 has no pad 7; its pads are 1, 2"),
            ("#net:GNDD", "has no net 'GNDD'; did you mean GND"),
            ("#3U", "not a board reference"),
            ("blinky.kicad_pcb#", "not a board reference"),
        ):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, message):
                self.view.resolve(ref)


    def test_every_item_resolves_by_the_uuid_it_was_saved_with(self) -> None:
        track = self.view.resolve(f"#track:{UUIDS['vbus track']}")
        self.assertIsInstance(track, Track)
        self.assertEqual((track.net, track.layer, track.width, round(track.length, 3)), ("VBUS", "F.Cu", 1.0, 29.175))
        via = self.view.resolve(f"blinky.kicad_pcb#via:{UUIDS['via'].upper()}")  # a uuid in any case
        self.assertIsInstance(via, Via)
        self.assertEqual((via.net, via.layers, via.type, via.selector), ("GND", ("F.Cu", "B.Cu"), "through", f"#via:{UUIDS['via']}"))
        zone = self.view.resolve(f"#zone:{UUIDS['pour']}")
        self.assertIsInstance(zone, Zone)
        self.assertEqual((zone.net, zone.name, zone.layers, zone.priority, zone.filled_area), ("GND", "GND pour", ("B.Cu",), 0, 216.0))
        text = self.view.resolve(f"#text:{UUIDS['blinky']}")
        self.assertIsInstance(text, Text)
        self.assertEqual((text.text, text.layer, text.size, text.part), ("blinky", "F.SilkS", 1.5, None))
        # Its box holds its letters, centred on where KiCad puts it.
        self.assertTrue(inside((20, 5), text.polygon))
        outline = self.view.resolve(f"#shape:{UUIDS['outline']}")
        self.assertIsInstance(outline, Shape)
        self.assertEqual((outline.shape, outline.layer, outline.width, outline.closed, outline.part), ("rect", "Edge.Cuts", 0.1, True, None))
        with self.assertRaisesRegex(ValueError, "has no track 0123: a track is named by the uuid"):
            self.view.resolve("#track:0123")

    def test_a_footprints_text_and_graphics_are_its_own(self) -> None:
        texts = {(text.part, text.text, text.layer) for text in self.view.texts}
        # Each part's reference and value as shown, the fab's ${REFERENCE} substituted; the hidden fields left out.
        self.assertLessEqual({("R1", "R1", "F.SilkS"), ("R1", "10k", "F.Fab"), ("R1", "R1", "F.Fab"), ("D1", "D1", "F.SilkS")}, texts)
        self.assertFalse(any(text.text in ("", "Datasheet") for text in self.view.texts))
        reference = next(text for text in self.view.texts if text.part == "R1" and text.layer == "F.SilkS")
        self.assertIs(self.view.resolve(reference.selector), reference)
        silk = [shape for shape in self.view.shapes if shape.part == "J1" and shape.layer == "F.SilkS"]
        self.assertEqual(len(silk), 6)
        self.assertEqual({shape.shape for shape in self.view.shapes if shape.part == "R1"}, {"line", "rect"})

    def test_a_point_on_a_layer_holds_what_that_layer_holds_there(self) -> None:
        anywhere = self.view.resolve("#@x10y20")  # over the bottom pour
        self.assertEqual([item.kind for item in anywhere.copper], ["zone"])
        on_top = self.view.resolve("#F.Cu@x10y20")
        self.assertIsInstance(on_top, Point)
        self.assertEqual((on_top.layer, on_top.copper, on_top.selector), ("F.Cu", (), "#F.Cu@x10y20"))
        self.assertEqual([item.kind for item in self.view.resolve("#B.Cu@x10y20").copper], ["zone"])
        # A through-hole pad is on every copper layer; a part on its side's layers.
        self.assertEqual([pad.number for pad in self.view.resolve("#B.Cu@x5y15").pads], ["1"])
        self.assertEqual([part.ref for part in self.view.resolve("#F.SilkS@x35y15").parts], ["R1"])
        self.assertEqual(self.view.resolve("#B.SilkS@x35y15").parts, ())
        self.assertEqual([text.text for text in self.view.resolve("#F.SilkS@x20y5").texts], ["blinky"])
        with self.assertRaisesRegex(ValueError, "has no layer In1.Cu; its layers are F.Cu, B.Cu"):
            self.view.resolve("#In1.Cu@x10y20")

    def test_an_area_holds_what_lies_wholly_inside_it(self) -> None:
        area = self.view.resolve("#@x30y10..x40y20")  # round R1
        self.assertIsInstance(area, Area)
        self.assertEqual((area.box, area.size, area.selector), (((30.0, 10.0), (40.0, 20.0)), (10.0, 10.0), "#@x30y10..x40y20"))
        self.assertEqual([part.ref for part in area.parts], ["R1"])
        self.assertEqual(sorted(f"{pad.part}.{pad.number}" for pad in area.pads), ["R1.1", "R1.2"])
        self.assertEqual(area.tracks, (), "the VBUS track runs out of it")
        self.assertIn("1 parts", repr(area))
        # From either corner, it is one box; on a layer, what that layer holds in it.
        self.assertEqual(self.view.resolve("#@x40y20..x30y10").box, area.box)
        whole = self.view.resolve("#F.Cu@x0y0..x40y30")
        self.assertEqual([track.net for track in whole.tracks], ["VBUS", "GND"])
        self.assertEqual((whole.layer, whole.texts, [via.net for via in whole.vias]), ("F.Cu", (), ["GND"]))
        self.assertEqual(sorted(part.ref for part in whole.parts), ["D1", "J1", "R1"])
        self.assertEqual([zone.net for zone in self.view.resolve("#B.Cu@x0y0..x40y30").zones], ["GND"])
        self.assertTrue(all(inside(point, area.polygon) for pad in area.pads for point in pad.polygon))

    def test_the_plot_names_each_graphic_as_the_index_does(self) -> None:
        payload = build_plot(self.path)
        drawn = {item["id"]: (layer["id"], item.get("shape", "line")) for layer in payload["sheets"][0]["layers"]
                 for item in layer["items"] if "id" in item}
        self.assertEqual(drawn, {shape.id: (shape.layer, shape.shape) for shape in self.view.shapes})
        board = payload["board"]
        self.assertEqual([track["id"] for track in board["tracks"]], [UUIDS["vbus track"], UUIDS["gnd track"]])
        self.assertEqual(board["vias"][0] | {"at": None}, {"net": "GND", "at": None, "diameter": 0.6, "drill": 0.3, "id": UUIDS["via"],
                                                          "layers": ["F.Cu", "B.Cu"], "type": "through"})
        self.assertEqual({key: board["zones"][0][key] for key in ("id", "name", "filled")}, {"id": UUIDS["pour"], "name": "GND pour", "filled": 216.0})
        self.assertEqual(sorted(text["text"] for text in board["texts"]), ["10k", "Conn_01x02", "D1", "D1", "J1", "LED", "R1", "R1", "blinky"])


class ItemsTest(unittest.TestCase):
    """What a board reference names by uuid, on boards written for each case."""

    def test_an_items_uuid_is_its_uuid_or_an_older_boards_tstamp(self) -> None:
        for text, expected in (
            ('(segment (uuid "AB12CD34-0000-4000-8000-00000000000F"))', "ab12cd34-0000-4000-8000-00000000000f"),
            ("(gr_line (tstamp 5C1F2A3B))", "5c1f2a3b"),
            ("(gr_line (tstamp 00012345))", "00012345"),  # all digits: read as a number, written back as eight
            ("(gr_line (tstamp 0))", None),
            ('(gr_line (uuid "00000000-0000-0000-0000-000000000000"))', None),
            ("(gr_line (layer F.Cu))", None),
        ):
            with self.subTest(text=text):
                self.assertEqual(item_id(sexpr.parse(text)), expected)

    def test_dimensions_read_their_value_and_where_they_are_drawn(self) -> None:
        text = """(kicad_pcb (version 20241229) (generator "pcbnew")
          (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user) (17 "Dwgs.User" user))
          (dimension (type aligned) (layer "Dwgs.User") (uuid "d1000000-0000-4000-8000-000000000001")
            (pts (xy 0 0) (xy 0 20)) (height -3)
            (gr_text "20.0000 mm" (at 4.5 10 90) (layer "Dwgs.User") (uuid "d1000000-0000-4000-8000-000000000001")
              (effects (font (size 1 1) (thickness 0.15)))))
          (dimension (type orthogonal) (layer "Dwgs.User") (uuid "d1000000-0000-4000-8000-000000000002")
            (pts (xy 0 0) (xy 30 5)) (height 8) (orientation 0)
            (gr_text "30" (at 15 7 0) (layer "Dwgs.User") (effects (font (size 1 1) (thickness 0.15)))))
          (dimension 12.5 (width 0.15) (layer Dwgs.User) (tstamp 5C1F2A3B)
            (gr_text "12.500 mm" (at 6 -3) (layer Dwgs.User) (effects (font (size 1 1) (thickness 0.15))))
            (feature1 (pts (xy 12.5 0) (xy 12.5 -2))) (feature2 (pts (xy 0 0) (xy 0 -2))) (crossbar (pts (xy 0 -2) (xy 12.5 -2)))))"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dims.kicad_pcb"
            path.write_text(text, encoding="utf-8")
            board = read_board(path)
            aligned = board.resolve("#dimension:d1000000-0000-4000-8000-000000000001")
            self.assertIsInstance(aligned, Dimension)
            # KiCad's crossbar stands `height` off the measured line: here 3 mm to its right (+x, y down).
            self.assertEqual((aligned.type, aligned.value, aligned.lines[1]), ("aligned", "20.0000 mm", ((3.0, 0.0), (3.0, 20.0))))
            self.assertTrue(inside((4.5, 10), aligned.polygon))
            orthogonal = board.resolve("#dimension:d1000000-0000-4000-8000-000000000002")
            self.assertEqual((orthogonal.value, orthogonal.lines[1]), ("30", ((0.0, 8.0), (30.0, 8.0))))
            older = board.resolve("#dimension:5c1f2a3b")
            self.assertEqual((older.value, len(older.lines)), ("12.500 mm", 3))
            self.assertEqual([item.id for item in board.resolve("#Dwgs.User@x-1y-5..x31y21").dimensions],
                             ["d1000000-0000-4000-8000-000000000001", "d1000000-0000-4000-8000-000000000002", "5c1f2a3b"])

    def test_copies_of_a_footprint_that_share_uuids_are_named_under_their_footprints(self) -> None:
        def footprint(uid: str, x: int) -> str:
            return f"""(footprint "Logo" (layer "F.Cu") (uuid "{uid}") (at {x} 10)
              (property "Reference" "" (at 0 0 0) (layer "F.SilkS"))
              (fp_text user "OSHW" (at 0 2 0) (layer "F.SilkS") (uuid "5aa00000-0000-4000-8000-000000000001") (effects (font (size 1 1) (thickness 0.15))))
              (fp_line (start -1 0) (end 1 0) (stroke (width 0.2) (type solid)) (layer "F.SilkS") (uuid "5aa00000-0000-4000-8000-000000000002")))"""
        text = f"""(kicad_pcb (version 20241229) (generator "pcbnew")
          (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (5 "F.SilkS" user))
          {footprint("f1000000-0000-4000-8000-000000000001", 10)}
          {footprint("f1000000-0000-4000-8000-000000000002", 30)})"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "logos.kicad_pcb"
            path.write_text(text, encoding="utf-8")
            board = read_board(path)
            self.assertEqual(sorted(shape.id for shape in board.shapes), [
                "f1000000-0000-4000-8000-000000000001/5aa00000-0000-4000-8000-000000000002",
                "f1000000-0000-4000-8000-000000000002/5aa00000-0000-4000-8000-000000000002"])
            second = board.resolve("#shape:f1000000-0000-4000-8000-000000000002/5aa00000-0000-4000-8000-000000000002")
            self.assertEqual(second.points[0], (29.0, 10.0))
            self.assertEqual(board.resolve("#text:F1000000-0000-4000-8000-000000000001/5AA00000-0000-4000-8000-000000000001").at, (10.0, 12.0))
            with self.assertRaisesRegex(ValueError, "has 2 texts with uuid 5aa00000-0000-4000-8000-000000000001, on copies of one footprint"):
                board.resolve("#text:5aa00000-0000-4000-8000-000000000001")
            # The plot names what it draws as the index does.
            drawn = sorted(item["id"] for layer in build_plot(path)["sheets"][0]["layers"] for item in layer["items"] if "id" in item)
            self.assertEqual(drawn, sorted(shape.id for shape in board.shapes))


class OlderBoardTest(unittest.TestCase):
    def test_a_board_with_numbered_nets_reads_by_name(self) -> None:
        # KiCad 9 and before numbered nets in a table and on every item, and placed a footprint by (at ...).
        text = """(kicad_pcb (version 20241229) (generator "pcbnew")
          (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))
          (setup (aux_axis_origin 100 100))
          (net 0 "") (net 1 "GND") (net 2 "/SDA{slash}x")
          (footprint "Lib:Two" (layer "F.Cu") (at 110 90 90)
            (property "Reference" "J7" (at 0 0 0) (layer "F.SilkS"))
            (property "Value" "conn" (at 0 0 0) (layer "F.Fab"))
            (pad "1" smd rect (at -1 0 90) (size 1 2) (layers "F.Cu") (net 1 "GND"))
            (pad "2" smd circle (at 1 0 90) (size 1 1) (layers "F.Cu") (net 2 "/SDA{slash}x")))
          (segment (start 109 90) (end 105 90) (width 0.25) (layer "F.Cu") (net 2))
          (zone (net 1) (net_name "GND") (layer "B.Cu") (polygon (pts (xy 100 80) (xy 120 80) (xy 120 100) (xy 100 100)))))"""
        index = read_index(text)
        [part] = index.parts
        self.assertEqual([(pad.number, pad.net) for pad in part.pads], [("1", "GND"), ("2", "/SDA/x")])
        self.assertEqual([track.net for track in index.tracks], ["/SDA/x"])
        self.assertEqual([zone.net for zone in index.zones], ["GND"])
        # KiCad's own frame, whatever drill/place origin the board sets.
        self.assertEqual((index.origin, part.at), ((0.0, 0.0), (110.0, 90.0)))
        # Pad 1 at (-1, 0) of a footprint turned a quarter turn lands 1 mm below it (y down).
        self.assertTrue(math.isclose(part.pads[0].at[0], 110, abs_tol=1e-9) and math.isclose(part.pads[0].at[1], 91, abs_tol=1e-9))

    def test_a_number_several_pads_share_names_them_all(self) -> None:
        # A shell's or a tab's pads share one number: one pin of several pads, which the agent sees.
        text = """(kicad_pcb (version 20260206) (generator "pcbnew")
          (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))
          (footprint "Lib:Shell" (layer "F.Cu") (at 110 90)
            (property "Reference" "J1" (at 0 0 0) (layer "F.SilkS"))
            (pad "SH" thru_hole oval (at -4 0) (size 1 2) (drill 0.6) (layers "*.Cu") (net "GND"))
            (pad "SH" thru_hole oval (at 4 0) (size 1 2) (drill 0.6) (layers "*.Cu") (net "GND"))
            (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net "VBUS"))))"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shell.kicad_pcb"
            path.write_text(text, encoding="utf-8")
            board = read_board(path)
            shell = board.resolve("#J1.SH")
            self.assertIn("one of 2 pads numbered SH", repr(shell))
            self.assertEqual([pad.at for pad in board.part("J1").pads_numbered("SH")], [(106.0, 90.0), (114.0, 90.0)])
            self.assertEqual(board.resolve("#J1.1").shared, 1)

    def test_a_kicad_5_board_reads_its_modules_and_arcs(self) -> None:
        # KiCad 5 wrote a footprint as a module, and an arc as its centre, its start and an angle:
        # this outline's right side bulges out from (110, 80) round (120, 90) to (110, 100).
        text = """(kicad_pcb (version 20171130) (host pcbnew 5.1.9)
          (layers (0 F.Cu signal) (31 B.Cu signal) (44 Edge.Cuts user))
          (net 0 "") (net 1 GND)
          (module R_0603 (layer F.Cu) (at 104 90 90)
            (fp_text reference R1 (at 0 -1.43 90) (layer F.SilkS))
            (fp_text value 10k (at 0 1.43 90) (layer F.Fab))
            (pad 1 smd rect (at -0.8 0 90) (size 0.8 0.95) (layers F.Cu F.Paste F.Mask) (net 1 GND)))
          (gr_line (start 100 80) (end 110 80) (layer Edge.Cuts) (width 0.1))
          (gr_arc (start 110 90) (end 110 80) (angle 180) (layer Edge.Cuts) (width 0.1))
          (gr_line (start 110 100) (end 100 100) (layer Edge.Cuts) (width 0.1))
          (gr_line (start 100 100) (end 100 80) (layer Edge.Cuts) (width 0.1)))"""
        index = read_index(text)
        [part] = index.parts
        self.assertEqual((part.ref, part.value, [(pad.number, pad.net) for pad in part.pads]), ("R1", "10k", [("1", "GND")]))
        view = BoardView(Path("old.kicad_pcb"), index)
        self.assertTrue(view.at(115, 90).on_board)
        self.assertFalse(view.at(118, 82).on_board)


if __name__ == "__main__":
    unittest.main()
