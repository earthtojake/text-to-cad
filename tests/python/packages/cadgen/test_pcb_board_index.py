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

from tests.python.support.kicad_board import write_board
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.engine.formats.kicad.board_index import BoardView, Copper, Net, Pad, Part, Point, read_board, read_index  # noqa: E402
from cadgen.engine.formats.kicad.geometry import inside  # noqa: E402


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
