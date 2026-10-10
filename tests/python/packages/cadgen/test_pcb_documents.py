"""The KiCad documents a board writes, without KiCad: their frame, their links, their bytes.

A board script works in millimetres with y up; KiCad's files are y down on a
page. These tests pin how the writers map one to the other (the script's origin
becomes the board's drill/place origin), how a bottom-side part is stored (as
KiCad's own flip leaves it), that the schematic labels every connected pin and
flags every no-connect, that each footprint points at its symbol, and that the
same board always writes the same bytes. KiCad's verdict on the documents is the
KiCad suite's (tests/python/packages/kicad).
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_library import write_test_library
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.kicad import sexpr  # noqa: E402
from cadgen.kicad.design import Board  # noqa: E402
from cadgen.kicad.project import project_texts  # noqa: E402


def _footprint(tree: list, ref: str) -> list:
    for node in sexpr.find_all(tree, "footprint"):
        if any(prop[1] == "Reference" and prop[2] == ref for prop in sexpr.find_all(node, "property")):
            return node
    raise AssertionError(f"no footprint {ref}")


class PcbDocumentsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.library = write_test_library(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def board(self) -> Board:
        from cadgen import build123d as bd

        with bd.BuildSketch() as outline:
            bd.Rectangle(40, 30)
        board = Board(outline=outline.sketch, libraries=[self.library])
        vin, out, gnd = board.net("VIN", power_flag=True), board.net("OUT"), board.net("GND", power_flag=True)
        amp = board.part("Test:AMP", ref="U1")
        r1 = board.part("Test:R", footprint="Test:R_0603", value="10k")
        r2 = board.part("Test:R", footprint="Test:R_0603", value="1k", properties={"LCSC": "C25804"})
        board.connect(vin, amp["IN"], r1[1])
        board.connect(out, amp["OUT"], r1[2], r2[1])
        board.connect(gnd, amp[3], amp[4], r2[2])
        board.place(amp, at=(-5, 0))
        board.place(r1, at=(8, 4), rotation=90)
        board.place(r2, at=(8, -4), side="bottom")
        board.track(out, [amp["OUT"], r1[2]], width=0.3)
        board.via(gnd, at=(0, -8))
        board.zone(gnd, layers=["B.Cu"])
        return board

    def test_the_same_board_writes_the_same_bytes(self) -> None:
        first, second = project_texts(self.board(), name="amp"), project_texts(self.board(), name="amp")
        self.assertEqual((first.pro, first.sch, first.pcb), (second.pro, second.sch, second.pcb))

    def test_the_script_origin_is_the_drill_origin_and_y_flips(self) -> None:
        tree = project_texts(self.board(), name="amp").pcb_tree
        origin = sexpr.find(sexpr.find(tree, "setup"), "aux_axis_origin")[1:]
        at = sexpr.find(_footprint(tree, "R1"), "at")[1:]
        # R1 is at (8, 4) in the script: KiCad's x grows to the right, its y downwards.
        self.assertEqual((at[0] - origin[0], origin[1] - at[1], at[2]), (8, 4, 90))
        segment = sexpr.find(tree, "segment")
        self.assertEqual(sexpr.value(segment, "net"), "OUT")
        self.assertEqual(sexpr.value(segment, "width"), 0.3)

    def test_pad_angles_are_absolute_and_carry_their_nets(self) -> None:
        tree = project_texts(self.board(), name="amp").pcb_tree
        pads = {str(pad[1]): pad for pad in sexpr.find_all(_footprint(tree, "R1"), "pad")}
        self.assertEqual(sexpr.find(pads["1"], "at")[1:], [-0.825, 0, 90])
        self.assertEqual(sexpr.value(pads["1"], "net"), "VIN")
        self.assertEqual(sexpr.value(pads["2"], "net"), "OUT")

    def test_a_bottom_part_is_stored_as_kicad_flips_it(self) -> None:
        tree = project_texts(self.board(), name="amp").pcb_tree
        r2 = _footprint(tree, "R2")
        self.assertEqual(sexpr.value(r2, "layer"), "B.Cu")
        pad = next(sexpr.find_all(r2, "pad"))
        self.assertEqual(sexpr.find(pad, "layers")[1:], ["B.Cu", "B.Mask", "B.Paste"])
        reference = next(prop for prop in sexpr.find_all(r2, "property") if prop[1] == "Reference")
        # Library text at (0, -1.5, 0) on F.SilkS: mirrored to y = 1.5, on the back,
        # read upside down and mirrored (angle 180 - a), as KiCad's own flip stores it.
        self.assertEqual(sexpr.find(reference, "at")[1:], [0, 1.5, 180])
        self.assertEqual(sexpr.value(reference, "layer"), "B.SilkS")
        self.assertIn("mirror", str(sexpr.find(reference, "effects")))
        lcsc = next(prop for prop in sexpr.find_all(r2, "property") if prop[1] == "LCSC")
        self.assertEqual(lcsc[2], "C25804")

    def test_each_footprint_points_at_its_symbol(self) -> None:
        texts = project_texts(self.board(), name="amp")
        schematic = sexpr.parse(texts.sch)
        symbols = {}
        for symbol in sexpr.find_all(schematic, "symbol"):
            reference = next((prop[2] for prop in sexpr.find_all(symbol, "property") if prop[1] == "Reference"), None)
            symbols.setdefault(reference, f"/{sexpr.value(symbol, 'uuid')}")
        for ref in ("U1", "R1", "R2"):
            self.assertEqual(sexpr.value(_footprint(texts.pcb_tree, ref), "path"), symbols[ref])

    def test_the_schematic_labels_every_connected_pin_and_flags_power(self) -> None:
        schematic = sexpr.parse(project_texts(self.board(), name="amp").sch)
        labels = sorted(str(label[1]) for label in sexpr.find_all(schematic, "global_label"))
        # Nine connected pins, and one PWR_FLAG on each of the two powered nets.
        self.assertEqual(labels, sorted(["VIN"] * 2 + ["OUT"] * 3 + ["GND"] * 3 + ["VIN", "GND"]))
        flags = [
            symbol for symbol in sexpr.find_all(schematic, "symbol") if sexpr.value(symbol, "lib_id") == "power:PWR_FLAG"
        ]
        self.assertEqual(len(flags), 2)

    def test_a_no_connect_pin_is_flagged_and_gets_kicads_own_net(self) -> None:
        board = self.board()
        spare = board.part("Test:R", footprint="Test:R_0603", value="0R")
        board.place(spare, at=(-15, 10))
        board.connect(board.net("GND"), spare[1])
        board.no_connect(spare[2])
        texts = project_texts(board, name="amp")
        self.assertEqual(len(list(sexpr.find_all(sexpr.parse(texts.sch), "no_connect"))), 1)
        pads = {str(pad[1]): pad for pad in sexpr.find_all(_footprint(texts.pcb_tree, spare.ref), "pad")}
        self.assertEqual(sexpr.value(pads["2"], "net"), f"unconnected-({spare.ref}-Pad2)")

    def test_an_open_stack_of_pins_is_one_net_named_as_kicad_names_it(self) -> None:
        # KiCad joins pins drawn at one point and names an open stack after its least name:
        # both pads must carry that one net, or parity reports a conflict.
        board = self.board()
        hdr = board.part("Test:HDR", ref="J1")
        board.connect(board.net("GND"), hdr["2"])
        board.no_connect(hdr[1])
        board.place(hdr, at=(-12, 8))
        footprint = _footprint(project_texts(board, name="amp").pcb_tree, "J1")
        pads = {str(pad[1]): sexpr.value(pad, "net") for pad in sexpr.find_all(footprint, "pad")}
        self.assertEqual(pads, {"1": "unconnected-(J1-3V3-Pad1)", "2": "GND", "3": "unconnected-(J1-3V3-Pad1)", "4": "GND"})

    def test_net_names_are_escaped_and_unit_lettered_as_kicad_derives_them(self) -> None:
        # KiCad escapes "/" in a net name (it separates sheets), and names an open pin's net with
        # its unit's letter on a symbol of several units; the pads must agree or parity fails.
        board = self.board()
        dual = board.part("Test:DUAL", ref="U2")
        r3 = board.part("Test:R", footprint="Test:R_0603", ref="R3")
        board.connect(board.net("TX/RX"), r3[1], r3[2])
        board.no_connect(dual[1], dual[2])
        board.place(dual, at=(-12, 8))
        board.place(r3, at=(-12, -8))
        texts = project_texts(board, name="amp")

        def pad_nets(ref: str) -> list[str]:
            return [sexpr.value(pad, "net") for pad in sexpr.find_all(_footprint(texts.pcb_tree, ref), "pad")]

        self.assertEqual(pad_nets("R3"), ["TX{slash}RX", "TX{slash}RX"])
        self.assertEqual(pad_nets("U2"), ["unconnected-(U2A-IN{slash}A-Pad1)", "unconnected-(U2B-IN{slash}B-Pad2)"])
        labels = {str(node[1]) for node in sexpr.find_all(sexpr.parse(texts.sch), "global_label")}
        self.assertIn("TX{slash}RX", labels)
        self.assertEqual(board.net("TX/RX").name, "TX/RX")  # the script keeps its own name

    def test_a_footprints_zone_lands_where_its_pads_do(self) -> None:
        # KiCad stores a placed footprint's zone in board coordinates, not the footprint's own:
        # a keepout corner drawn on pad 1's centre must land on pad 1, whatever the placement.
        from cadgen.kicad.board_writer import Frame

        for side, rotation in (("top", 0), ("top", 90), ("bottom", 30)):
            board = self.board()
            part = board.part("Test:FIDUCIAL", footprint="Test:ZONED", ref="FID1")
            board.no_connect(part[1])
            board.place(part, at=(-12, 6), rotation=rotation, side=side)
            texts = project_texts(board, name="amp")
            zone = sexpr.find(_footprint(texts.pcb_tree, "FID1"), "zone")
            corners = [tuple(point[1:3]) for point in sexpr.find_all(sexpr.find(sexpr.find(zone, "polygon"), "pts"), "xy")]
            frame = Frame.for_outline(board.outline)
            self.assertEqual(corners[0], frame.point(part[1].position), (side, rotation))
            self.assertEqual(sexpr.find(zone, "layers")[1], "B.Cu" if side == "bottom" else "F.Cu")

    def test_the_bill_of_materials_flag_is_the_symbols(self) -> None:
        # KiCad's update from the schematic gives a footprint its symbol's "exclude from BOM",
        # whatever the library footprint said; otherwise its parity check reports the mismatch.
        board = self.board()
        point = board.part("Test:TP", ref="TP1")  # in the BOM; Test:TEST_PAD says exclude_from_bom
        mark = board.part("Test:FIDUCIAL", footprint="Test:ONE_PAD", ref="FID1")  # (in_bom no)
        board.no_connect(point[1], mark[1])
        board.place(point, at=(-12, 8))
        board.place(mark, at=(-12, -8))
        texts = project_texts(board, name="amp")

        def attr(ref: str) -> list[str]:
            return [str(flag) for flag in sexpr.find(_footprint(texts.pcb_tree, ref), "attr")[1:]]

        self.assertEqual(attr("TP1"), ["smd", "exclude_from_pos_files"])
        self.assertEqual(attr("FID1"), ["smd", "exclude_from_bom"])
        in_bom = {
            next(prop[2] for prop in sexpr.find_all(node, "property") if prop[1] == "Reference"): sexpr.value(node, "in_bom")
            for node in sexpr.find_all(sexpr.parse(texts.sch), "symbol")
            if sexpr.find(node, "lib_id") is not None
        }
        self.assertEqual((in_bom["TP1"], in_bom["FID1"]), ("yes", "no"))

    def test_a_library_symbols_own_fields_reach_its_symbol_and_footprint(self) -> None:
        # KiCad copies a library symbol's fields (a model's Sim.*) onto the placed symbol, and its
        # parity check wants each on the footprint too; a part's properties= win over them.
        board = self.board()
        mark = board.part("Test:FIDUCIAL", footprint="Test:ONE_PAD", ref="FID1", properties={"LCSC": "C1"})
        board.no_connect(mark[1])
        board.place(mark, at=(-12, -8))
        self.assertEqual(mark.fields, {"Sim.Enable": "0", "LCSC": "C1"})
        texts = project_texts(board, name="amp")

        def fields(node: list) -> dict[str, str]:
            return {str(prop[1]): str(prop[2]) for prop in sexpr.find_all(node, "property")}

        symbol = next(
            node for node in sexpr.find_all(sexpr.parse(texts.sch), "symbol")
            if sexpr.find(node, "lib_id") is not None and fields(node).get("Reference") == "FID1"
        )
        for carried in (fields(symbol), fields(_footprint(texts.pcb_tree, "FID1"))):
            self.assertEqual((carried["Sim.Enable"], carried["LCSC"]), ("0", "C1"))
        overridden = self.board().part("Test:FIDUCIAL", footprint="Test:ONE_PAD", properties={"Sim.Enable": "1"})
        self.assertEqual(overridden.fields, {"Sim.Enable": "1"})

    def test_each_part_and_hole_names_the_script_line_that_made_it(self) -> None:
        # board.part() and board.hole() remember the first line outside cadgen that called them,
        # and both documents carry it as a hidden Script field: the symbol's and the footprint's
        # agree, so KiCad's parity check stays clean.
        board = self.board()
        part_line = sys._getframe().f_lineno + 1
        spare = board.part("Test:R", footprint="Test:R_0603", value="0R", ref="R9")
        board.no_connect(spare[1], spare[2])
        board.place(spare, at=(-15, 10))
        hole_line = sys._getframe().f_lineno + 1
        board.hole(at=(15, 10), diameter=2)
        here = Path(__file__).resolve()
        self.assertEqual((Path(spare.script[0]).resolve(), spare.script[1]), (here, part_line))

        def script_fields(texts) -> tuple[str, str, str]:
            symbol = next(
                node for node in sexpr.find_all(sexpr.parse(texts.sch), "symbol")
                if sexpr.find(node, "lib_id") is not None
                and any(prop[1] == "Reference" and prop[2] == "R9" for prop in sexpr.find_all(node, "property"))
            )
            found = []
            for node in (symbol, _footprint(texts.pcb_tree, "R9"), _footprint(texts.pcb_tree, "H1")):
                [field] = [prop for prop in sexpr.find_all(node, "property") if prop[1] == "Script"]
                self.assertEqual(sexpr.value(field, "hide"), "yes")
                found.append(field[2])
            return tuple(found)

        # Relative to the model script's folder, with / between folders; the file's name alone
        # when no folder is known or the line lies outside it.
        nested = script_fields(project_texts(board, name="amp", script_root=here.parent.parent))
        self.assertEqual(nested, (f"cadgen/{here.name}:{part_line}",) * 2 + (f"cadgen/{here.name}:{hole_line}",))
        for root in (None, Path(self._tmp.name)):
            with self.subTest(root=root):
                self.assertEqual(
                    script_fields(project_texts(board, name="amp", script_root=root)),
                    (f"{here.name}:{part_line}",) * 2 + (f"{here.name}:{hole_line}",),
                )

    def test_the_script_field_is_cadgens(self) -> None:
        from cadgen.kicad.design import DesignError

        with self.assertRaisesRegex(DesignError, "cannot set Script"):
            self.board().part("Test:R", footprint="Test:R_0603", properties={"Script": "elsewhere.py:1"})

    def test_the_project_carries_the_rules_and_net_classes(self) -> None:
        board = self.board()
        board.netclass("Power", track_width=0.5, clearance=0.25)
        board.net("VIN", netclass="Power")
        project = json.loads(project_texts(board, name="amp").pro)
        classes = {entry["name"]: entry for entry in project["net_settings"]["classes"]}
        self.assertEqual((classes["Power"]["track_width"], classes["Default"]["track_width"]), (0.5, board.rules.track_width))
        self.assertEqual(project["net_settings"]["netclass_patterns"], [{"netclass": "Power", "pattern": "VIN"}])
        self.assertEqual(project["board"]["design_settings"]["rules"]["min_clearance"], board.rules.min_clearance)

    def test_the_project_keeps_each_nets_current(self) -> None:
        board = self.board()
        board.net("VIN", current=2.0)  # VIN is on two pins, so it is a used net
        document = json.loads(project_texts(board, name="amp").pro)
        self.assertEqual(document["cadgen"], {"net_currents": {"VIN": 2.0}})

    def test_a_project_without_currents_has_no_cadgen_section(self) -> None:
        self.assertNotIn("cadgen", json.loads(project_texts(self.board(), name="amp").pro))

    def test_custom_rules_are_the_projects_kicad_dru(self) -> None:
        from cadgen.kicad.design import DesignError

        board = self.board()
        self.assertEqual(project_texts(board, name="amp").dru, "(version 1)\n")  # written even when empty
        board.rule("""(rule "U1 pads" (constraint hole_clearance (min 0.15mm)) (condition "A.memberOfFootprint('U1')"))""")
        rules = sexpr.parse(project_texts(board, name="amp").dru.split("\n", 1)[1])
        self.assertEqual((rules[1], sexpr.value(rules, "condition")), ("U1 pads", "A.memberOfFootprint('U1')"))
        for text, message in (
            ("(rule unclosed", "takes one KiCad rule"),
            ('(constraint clearance (min 1mm))', "takes one \\(rule NAME"),
            ('(rule "no constraint" (condition "A.Type == \'Pad\'"))', "has no \\(constraint"),
            ('(rule "U1 pads" (constraint clearance (min 1mm)))', "already has a rule named"),
        ):
            with self.assertRaisesRegex(DesignError, message):
                board.rule(text)


if __name__ == "__main__":
    unittest.main()
