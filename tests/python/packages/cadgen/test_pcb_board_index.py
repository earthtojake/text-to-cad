"""`pcb.read_board`: a KiCad board read back as what a person points at, without KiCad.

A board written with the test library is read from its `.kicad_pcb` alone and every answer is
held to the board API that made it: each pad lands where `pin.pads` says (a rotated part and a
bottom-side part included), each reference kind resolves in the script's frame, and a
reference to another file is refused. KiCad's own plot of the index is the KiCad suite's
(tests/python/packages/kicad/test_pcb_plot_and_validate.py).
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_library import write_test_library
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.kicad import sexpr  # noqa: E402
from cadgen.kicad.board_index import BoardView, Copper, Net, Pad, Part, Point, read_board, read_index, script_frame  # noqa: E402
from cadgen.kicad.design import Board  # noqa: E402
from cadgen.kicad.project import project_texts  # noqa: E402


def _inside(point, polygon) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, [*polygon[1:], polygon[0]]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


class BoardIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from cadgen import build123d as bd

        cls._tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls._tmp.name)
        (cls.folder / "lib").mkdir()
        library = write_test_library(cls.folder / "lib")
        with bd.BuildSketch() as outline:
            bd.Rectangle(40, 30)
        board = Board(outline=outline.sketch, libraries=[library])
        board.netclass("Power", track_width=0.5, clearance=0.25)
        vin, out, gnd = board.net("VIN", netclass="Power", power_flag=True), board.net("TX/RX"), board.net("GND", power_flag=True)
        cls.part_line = sys._getframe().f_lineno + 1
        amp = board.part("Test:AMP", ref="U1")
        r1 = board.part("Test:R", footprint="Test:R_0603", value="10k", ref="R1")
        r2 = board.part("Test:R", footprint="Test:R_0603", value="1k", ref="R2")
        r3 = board.part("Test:R", footprint="Test:R_0603", value="4k7", ref="R3")
        u2 = board.part("Test:AMP", ref="U2")
        board.connect(vin, amp["IN"], r1[1], u2["IN"])
        board.connect(out, amp["OUT"], r1[2], r2[1], u2["OUT"])
        board.connect(gnd, amp[3], amp[4], r2[2], r3[1], r3[2], u2[3], u2[4])
        board.place(amp, at=(-5, 0))
        board.place(r1, at=(8, 4), rotation=90)
        board.place(r2, at=(8, -4), side="bottom")
        board.place(r3, at=(-12, -8), rotation=30, side="bottom")
        board.place(u2, at=(12, 8), rotation=45)
        board.track(out, [amp["OUT"], r1[2]], width=0.3)
        board.arc(vin, start=(-18, -2), mid=(-15, 1), end=(-12, -2), width=0.25, layer="B.Cu")
        # A square cutout, x 14..18, y -14..-10, its corners microns apart as KiCad's own
        # library footprints leave theirs (KiCad's page frame: y down, the board's centre at 148.5, 105).
        for number, (start, end) in enumerate((
            ((162.5, 115), (166.5, 115)), ((166.5, 115.002), (166.5, 119)),
            ((166.501, 119), (162.5, 119)), ((162.5, 119), (162.5, 115.003)),
        )):
            board.raw(
                f'(gr_line (start {start[0]} {start[1]}) (end {end[0]} {end[1]}) (stroke (width 0.05) (type default))'
                f' (layer "Edge.Cuts") (uuid "00000000-0000-4000-8000-00000000000{number}"))'
            )
        board.via(gnd, at=(0, -8))
        board.zone(gnd, layers=["B.Cu"])
        cls.hole_line = sys._getframe().f_lineno + 1
        board.hole(at=(-15, 10), diameter=3)
        cls.board = board
        texts = project_texts(board, name="amp", script_root=Path(__file__).resolve().parent)
        (cls.folder / "amp.kicad_pcb").write_text(texts.pcb, encoding="utf-8")
        (cls.folder / "amp.kicad_pro").write_text(texts.pro, encoding="utf-8")
        cls.view = read_board(cls.folder / "amp.kicad_pcb")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_every_pad_lands_where_the_board_api_puts_it(self) -> None:
        # pin.pads is the script's own answer, in the script's frame: a rotated part, a part on the
        # bottom and one both rotated and on the bottom must read back to the same points.
        checked = 0
        for part in self.board.parts:
            read = self.view.part(part.ref)
            self.assertEqual((read.side, read.rotation), (part.side, part.rotation), part.ref)
            for pin in part.pins():
                expected = pin.pads
                found = [pad.at for pad in read.pads if pad.number == pin.number]
                self.assertEqual(len(found), len(expected), (part.ref, pin.number))
                for (x, y), (fx, fy) in zip(expected, found):
                    self.assertAlmostEqual(x, fx, places=6, msg=(part.ref, pin.number))
                    self.assertAlmostEqual(y, fy, places=6, msg=(part.ref, pin.number))
                    checked += 1
        self.assertEqual(checked, 4 + 2 + 2 + 2 + 4)

    def test_a_pads_polygon_holds_its_centre_and_turns_with_it(self) -> None:
        for pad in self.view.parts[0].pads + self.view.part("R3").pads:
            self.assertTrue(_inside(pad.at, pad.polygon), pad)
        flat, turned = self.view.part("R2").pad("1"), self.view.part("R1").pad("1")

        def extent(pad: Pad) -> tuple[float, float]:
            xs, ys = [x for x, _ in pad.polygon], [y for _, y in pad.polygon]
            return round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3)

        # The library pad is 0.8 x 0.95; R1 is turned a quarter turn, R2 is not.
        self.assertEqual(extent(flat), (0.8, 0.95))
        self.assertEqual(extent(turned), (0.95, 0.8))
        self.assertEqual((flat.side, turned.side), ("bottom", "top"))

    def test_a_part_resolves_with_the_line_that_made_it(self) -> None:
        part = self.view.resolve("#U1")
        self.assertIsInstance(part, Part)
        self.assertEqual((part.ref, part.value, part.footprint, part.at), ("U1", "AMP", "Test:SOT4", (-5.0, 0.0)))
        self.assertEqual(part.script, f"{Path(__file__).name}:{self.part_line}")
        self.assertEqual(self.view.resolve("R2").script, f"{Path(__file__).name}:{self.part_line + 2}")
        # The courtyard-less test footprint is outlined by the box round its pads.
        xs = [x for x, _ in part.outline]
        self.assertAlmostEqual(max(xs) - min(xs), 3.0 + 0.8, places=6)
        self.assertEqual(self.view.resolve("#H1").script, f"{Path(__file__).name}:{self.hole_line}")

    def test_the_outline_closes_as_kicad_chains_it(self) -> None:
        # KiCad joins outline segments whose ends are within 0.01 mm: the cutout is a hole in the board.
        self.assertEqual(sorted((len(line), line[0] == line[-1]) for line in self.view.outline), [(5, True), (5, True)])
        self.assertFalse(self.view.at(16, -12).on_board)
        self.assertTrue(self.view.at(16, -6).on_board)

    def test_a_pad_and_a_net_resolve_with_what_is_on_them(self) -> None:
        pad = self.view.resolve("#U1.2")
        self.assertEqual((pad.part, pad.number, pad.name, pad.net, pad.type), ("U1", "2", "OUT", "TX/RX", "output"))
        self.assertEqual(pad.at, self.board.parts[0]["OUT"].position)
        net = self.view.resolve("#net:TX/RX")
        self.assertIsInstance(net, Net)
        self.assertEqual((net.netclass, len(net.pads), len(net.tracks)), ("Default", 4, 1))
        self.assertEqual(self.view.resolve("#net:VIN").netclass, "Power")  # from the .kicad_pro beside the board
        gnd = self.view.resolve("#net:GND")
        self.assertEqual((len(gnd.pads), len(gnd.vias), len(gnd.zones)), (7, 1, 1))

    def test_copper_resolves_to_what_the_net_has_at_the_point(self) -> None:
        start, end = self.board.parts[0]["OUT"].position, self.board.parts[1]["2"].position
        middle = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        copper = self.view.resolve(f"#net:TX/RX@x{middle[0]:.3f}y{middle[1]:.3f}")
        self.assertIsInstance(copper, Copper)
        self.assertEqual([item.kind for item in copper.items], ["track"])
        via = self.view.resolve("#net:GND@x0.1y-8")
        self.assertEqual([item.kind for item in via.items], ["via"])
        with self.assertRaisesRegex(ValueError, r"no copper at \(0, 5\): the nearest is"):
            self.view.resolve("#net:GND@x0y5")

    def test_a_point_says_what_is_there(self) -> None:
        on_pad = self.view.resolve("#@x{0:g}y{1:g}".format(*self.board.parts[0]["IN"].position))
        self.assertIsInstance(on_pad, Point)
        self.assertTrue(on_pad.on_board)
        self.assertEqual([(pad.part, pad.number) for pad in on_pad.pads], [("U1", "1")])
        self.assertEqual([part.ref for part in on_pad.parts], ["U1"])
        hole = self.view.at(-15, 10)
        self.assertEqual([(found.diameter, found.part) for found in hole.holes], [(3.0, "H1")])
        self.assertFalse(self.view.at(30, 0).on_board)

    def test_a_reference_must_name_this_board(self) -> None:
        board = self.folder / "amp.kicad_pcb"
        # A quoted path is JSON, as a copied one is: a Windows path's backslashes are escaped.
        for ref in ("amp.kicad_pcb#U1", f"{board}#U1", f"{json.dumps(str(board))}#U1"):
            with self.subTest(ref=ref):
                self.assertEqual(self.view.resolve(ref).ref, "U1")
        with self.assertRaisesRegex(ValueError, "reference names 'other.kicad_pcb', but this board is"):
            self.view.resolve("other.kicad_pcb#U1")
        with self.assertRaisesRegex(ValueError, "reference names 'amp.kicad_sch'"):
            self.view.resolve("amp.kicad_sch#U1")

    def test_a_token_of_several_names_each_and_a_bad_one_teaches(self) -> None:
        answers = self.view.resolve_all("amp.kicad_pcb#U1,R1.2,net:GND")
        self.assertEqual([answer.kind for answer in answers], ["part", "pad", "net"])
        with self.assertRaisesRegex(ValueError, "names 3 things; resolve_all"):
            self.view.resolve("amp.kicad_pcb#U1,R1.2,net:GND")
        for ref, message in (
            ("#U9", "has no part U9; its parts are H1, R1, R2, R3, U1, U2"),
            ("#U12", "has no part U12; did you mean U1, U2"),
            ("#U1.7", "U1 has no pad 7; its pads are 1, 2, 3, 4"),
            ("#net:GNDD", "has no net 'GNDD'; did you mean GND"),
            ("#3U", "not a board reference"),
            ("amp.kicad_pcb#", "not a board reference"),
        ):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, message):
                self.view.resolve(ref)

    def test_an_items_uuid_becomes_a_reference(self) -> None:
        index = read_index((self.folder / "amp.kicad_pcb").read_text(encoding="utf-8"))
        tree = sexpr.parse((self.folder / "amp.kicad_pcb").read_text(encoding="utf-8"))
        footprint = next(node for node in sexpr.find_all(tree, "footprint") if any(p[1] == "Reference" and p[2] == "R1" for p in sexpr.find_all(node, "property")))
        pad = next(sexpr.find_all(footprint, "pad"))
        silk = sexpr.find(footprint, "fp_line")
        segment = sexpr.find(tree, "segment")
        self.assertEqual(index.item_ref(sexpr.value(pad, "uuid")), "#R1.1")
        self.assertEqual(index.item_ref(sexpr.value(silk, "uuid")), "#R1")
        self.assertEqual(index.item_ref(sexpr.value(segment, "uuid"), at=(1.5, 2.25)), "#net:TX/RX@x1.5y2.25")
        self.assertIsNone(index.item_ref(sexpr.value(sexpr.find(tree, "gr_line"), "uuid")))
        # KiCad's DRC places an arc at its centre, off its copper: the plot's reference names its middle.
        from cadgen.kicad.plot import _findings

        centre = (148.5 - 15, 105 + 2)
        report = [("drc", "warning", "track_dangling", "Track has unconnected end", (("Track (arc) [VIN] on B.Cu", sexpr.value(sexpr.find(tree, "arc"), "uuid"), centre),))]
        [item] = _findings(report, index)[0].items
        self.assertEqual((item.ref, item.at), ("#net:VIN@x-15y1", centre))
        self.assertEqual([(found.kind, found.arc) for found in self.view.resolve(item.ref).items], [("track", True)])


class OlderBoardTest(unittest.TestCase):
    def test_a_board_with_numbered_nets_reads_by_name(self) -> None:
        # KiCad 9 and before numbered nets in a table and on every item.
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
        self.assertEqual(index.origin, (100.0, 100.0))
        # Pad 1 at (-1, 0) of a footprint turned a quarter turn lands 1 mm below it (y down).
        self.assertTrue(math.isclose(part.pads[0].at[0], 110, abs_tol=1e-9) and math.isclose(part.pads[0].at[1], 91, abs_tol=1e-9))

    def test_a_number_several_pads_share_names_them_all(self) -> None:
        # A shell's or a tab's pads share one number: one pin of several pads, which the agent sees.
        text = """(kicad_pcb (version 20260206) (generator "pcbnew")
          (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))
          (setup (aux_axis_origin 100 100))
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
            self.assertEqual([pad.at for pad in board.part("J1").pads_numbered("SH")], [(6.0, 10.0), (14.0, 10.0)])
            self.assertEqual(board.resolve("#J1.1").shared, 1)

    def test_a_kicad_5_board_reads_its_modules_and_arcs(self) -> None:
        # KiCad 5 wrote a footprint as a module, and an arc as its centre, its start and an angle:
        # this outline's right side bulges out from (110, 80) round (120, 90) to (110, 100).
        text = """(kicad_pcb (version 20171130) (host pcbnew 5.1.9)
          (layers (0 F.Cu signal) (31 B.Cu signal) (44 Edge.Cuts user))
          (setup (aux_axis_origin 100 100))
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
        view = BoardView(Path("old.kicad_pcb"), index.mapped(script_frame(index.origin)))
        self.assertTrue(view.at(15, 10).on_board)
        self.assertFalse(view.at(18, 18).on_board)


if __name__ == "__main__":
    unittest.main()
