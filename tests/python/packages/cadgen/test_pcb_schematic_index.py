"""A KiCad schematic read back as what a person points at, without KiCad.

A schematic cadgen's writer makes from a board of the test library is read from its file
alone: every symbol but a power flag is a part, with its Script field and every unit it
places; each pin lands where the writer drew its stub, and takes the net its label names.
Small hand-written schematics pin how things connect (as KiCad connects them: a label or a
junction joins a wire's middle, a wire end or a pin there does not) and how a hierarchy reads
(each instance of a sheet with its own references, sheets named as KiCad names their
plots). KiCad's own netlist and plot of the same are the KiCad suite's
(tests/python/packages/kicad/test_pcb_schematic_index.py).
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_library import write_test_library
from tests.python.support.kicad_schematics import (
    CONNECTIONS_NETLIST,
    HIERARCHY_NETS,
    HIERARCHY_SHEETS,
    SchematicText,
    write_connections,
    write_hierarchy,
)
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.kicad import sexpr  # noqa: E402
from cadgen.kicad.design import Board  # noqa: E402
from cadgen.kicad.ids import Ids  # noqa: E402
from cadgen.kicad.project_writer import project_document  # noqa: E402
from cadgen.kicad.schematic_index import Net, Part, Pin, SchematicView, erc_payload, read_index, read_schematic  # noqa: E402
from cadgen.kicad.schematic_writer import schematic_document  # noqa: E402


class _Outline:
    """Board(outline=...) is only read when a board is written; the schematic writer never reads it."""


class CadgenSchematicTest(unittest.TestCase):
    """A schematic as cadgen's writer makes it: net labels, every unit on one sheet."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls._tmp.name)
        (cls.folder / "lib").mkdir()
        library = write_test_library(cls.folder / "lib")
        board = Board(outline=_Outline(), libraries=[library])
        board.netclass("Power", track_width=0.5, clearance=0.25)
        vin, out, gnd = board.net("VIN", netclass="Power", power_flag=True), board.net("TX/RX"), board.net("GND", power_flag=True)
        cls.part_line = sys._getframe().f_lineno + 1
        amp = board.part("Test:AMP", ref="U1")
        r1 = board.part("Test:R", footprint="Test:R_0603", value="10k", ref="R1", properties={"LCSC": "C25804"})
        dual = board.part("Test:DUAL", ref="U2")
        header = board.part("Test:HDR", ref="J1")
        board.connect(vin, amp["IN"], r1[1], dual[1], header[1])
        board.connect(out, amp["OUT"], r1[2])
        board.connect(gnd, amp[3], amp[4], header[2])
        board.no_connect(dual[2])

        def net_of_pin(part, number):
            net = part[number].net
            return net.name if net is not None else None

        tree, _paths = schematic_document(
            board, project="amp", net_of_pin=net_of_pin, power_flag_nets=["VIN", "GND"], script_root=Path(__file__).parent
        )
        cls.path = cls.folder / "amp.kicad_sch"
        cls.path.write_text(sexpr.dumps(tree), encoding="utf-8")
        (cls.folder / "amp.kicad_pro").write_text(project_document(board, project="amp", root_uuid=Ids("amp").of("sheet:/")), encoding="utf-8")
        cls.tree = tree
        cls.index = read_index(cls.path, project=cls.folder / "amp.kicad_pro")
        cls.view = SchematicView(cls.path, cls.index)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_every_symbol_but_a_power_flag_is_a_part_with_its_script_line(self) -> None:
        self.assertEqual([part.ref for part in self.index.parts], ["J1", "R1", "U1", "U2"])
        self.assertEqual([sheet.name for sheet in self.index.sheets], ["amp"])
        u1, r1, u2 = self.view.part("U1"), self.view.part("R1"), self.view.part("U2")
        self.assertEqual(u1.script, f"{Path(__file__).name}:{self.part_line}")
        self.assertEqual((r1.value, r1.lib, r1.footprint, r1.fields["LCSC"]), ("10k", "Test:R", "Test:R_0603", "C25804"))
        self.assertNotIn("Reference", r1.fields)
        # The two units of U2 stand apart, each with its own pin.
        self.assertEqual([unit.unit for unit in u2.units], [1, 2])
        self.assertNotEqual(u2.units[0].at, u2.units[1].at)
        self.assertEqual([(pin.unit, pin.number, pin.name) for pin in u2.pins], [(1, "1", "IN/A"), (2, "2", "IN/B")])
        # A power flag is drawn as one, never a part.
        flags = [label for label in self.index.labels if label.kind == "power"]
        self.assertEqual(sorted((label.text, label.net) for label in flags), [("PWR_FLAG", "GND"), ("PWR_FLAG", "VIN")])

    def test_every_pin_lands_where_the_writer_drew_its_stub(self) -> None:
        # The writer puts each connected pin's stub at the pin, independently of the index.
        stubs = {}
        for node in sexpr.find_all(self.tree, "wire"):
            start = sexpr.find(sexpr.find(node, "pts"), "xy")
            stubs[(start[1], start[2])] = node
        connected = [pin for pin in self.index.pins if pin.net is not None]
        self.assertEqual(len(connected), 11)  # every pin but U2's flagged one
        for pin in connected:
            self.assertIn(pin.at, stubs, pin)
        # A pin's body end is inside its unit's outline, its connection point outside it.
        for part in self.index.parts:
            for pin in part.pins:
                (left, top), _, (right, bottom), _ = next(unit.outline for unit in part.units if unit.unit == pin.unit)
                self.assertTrue(left <= pin.end[0] <= right and top <= pin.end[1] <= bottom, pin)

    def test_pins_wires_and_labels_take_the_net_their_labels_name(self) -> None:
        nets = {pin.selector: pin.net for pin in self.index.pins}
        self.assertEqual(
            nets,
            {
                "#J1.1": "VIN", "#J1.3": "VIN", "#J1.2": "GND", "#J1.4": "GND", "#R1.1": "VIN", "#R1.2": "TX/RX",
                "#U1.1": "VIN", "#U1.2": "TX/RX", "#U1.3": "GND", "#U1.4": "GND", "#U2.1": "VIN", "#U2.2": None,
            },
        )
        self.assertTrue(all(wire.net for wire in self.index.wires))
        self.assertIn("TX/RX", {label.text for label in self.index.labels if label.kind == "global"})
        [flag] = self.index.no_connects
        self.assertEqual((flag.part, flag.pin, flag.at), ("U2", "2", self.view.part("U2").pin("2").at))
        self.assertEqual(self.index.nets, (("GND", "Default"), ("TX/RX", "Default"), ("VIN", "Power")))

    def test_the_payload_shape(self) -> None:
        data = self.index.as_json()
        self.assertEqual(list(data), ["sheets", "parts", "pins", "wires", "labels", "junctions", "noConnects", "nets"])
        self.assertEqual(data["sheets"], [{"name": "amp", "path": "/", "file": "amp.kicad_sch", "title": "amp"}])
        part = data["parts"][2]
        self.assertEqual(list(part), ["ref", "value", "lib", "footprint", "fields", "script", "dnp", "units"])
        self.assertEqual(list(part["units"][0]), ["unit", "sheet", "at", "rotation", "mirror", "outline"])
        self.assertEqual((part["ref"], part["units"][0]["rotation"], part["units"][0]["mirror"]), ("U1", 0, None))
        self.assertEqual(list(data["pins"][0]), ["part", "number", "name", "type", "unit", "sheet", "net", "at", "end", "hidden"])
        self.assertEqual(list(data["wires"][0]), ["net", "sheet", "points"])
        self.assertEqual(list(data["labels"][0]), ["net", "sheet", "text", "kind", "at", "outline"])
        self.assertEqual(data["noConnects"], [{"sheet": 0, "at": list(self.view.part("U2").pin("2").at), "part": "U2", "pin": "2"}])
        self.assertEqual(data["nets"][2], {"name": "VIN", "class": "Power"})
        # Every label has a box to pick, round its anchor's end of the text.
        for label in data["labels"]:
            xs, ys = [x for x, _ in label["outline"]], [y for _, y in label["outline"]]
            self.assertEqual(len(label["outline"]), 4)
            self.assertTrue(min(xs) <= label["at"][0] <= max(xs) and min(ys) <= label["at"][1] <= max(ys), label)

    def test_a_reference_resolves_to_what_it_names(self) -> None:
        from cadgen import pcb

        self.assertIs(pcb.read_schematic, read_schematic)  # what an agent calls; it runs KiCad, so the KiCad suite does
        part = self.view.resolve("#U1")
        self.assertIsInstance(part, Part)
        pin = self.view.resolve("amp.kicad_sch#U1.2")
        self.assertIsInstance(pin, Pin)
        self.assertEqual((pin.part, pin.number, pin.name, pin.type, pin.net), ("U1", "2", "OUT", "output", "TX/RX"))
        net = self.view.resolve("#net:VIN")
        self.assertIsInstance(net, Net)
        self.assertEqual((net.netclass, net.nodes), ("Power", ("J1.1", "J1.3", "R1.1", "U1.1", "U2.1")))
        self.assertEqual([found.ref for found in net.parts], ["J1", "R1", "U1", "U2"])
        self.assertEqual([answer.kind for answer in self.view.resolve_all(f"{self.path}#U1,R1.2,net:GND")], ["part", "pin", "net"])

    def test_a_reference_it_cannot_answer_says_why(self) -> None:
        for ref, message in (
            ("#U12", "has no part U12; did you mean U1, U2"),
            ("#Q1", "has no part Q1; its parts are J1, R1, U1, U2"),
            ("#U1.7", "U1 has no pin 7; its pins are 1, 2, 3, 4"),
            ("#net:VINN", "has no net 'VINN'; did you mean VIN"),
            ("#net:VIN@x1y2", "names a point, and points belong to boards"),
            ("#@x1y2", "names a point, and points belong to boards"),
            ("amp.kicad_pcb#U1", "reference names 'amp.kicad_pcb', but this schematic is"),
            ("#3U", "not a schematic reference"),
            ("amp.kicad_sch#U1,R1", "names 2 things; resolve_all"),
        ):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, message):
                self.view.resolve(ref)


class ConnectionsTest(unittest.TestCase):
    """What touches what, as KiCad decides it (its netlist of the same sheet is in CONNECTIONS_NETLIST)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls._tmp.name) / "joins.kicad_sch"
        write_connections(cls.path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _wire_nets(self, index) -> dict[tuple, str | None]:
        return {wire.points: wire.net for wire in index.wires}

    def test_labels_and_junctions_join_a_wires_middle_and_ends_and_pins_do_not(self) -> None:
        index = read_index(self.path)
        nets = {pin.selector: pin.net for pin in index.pins}
        self.assertEqual(
            {ref: nets[ref] for ref in ("#R1.1", "#R2.1", "#R3.1", "#R4.1", "#R5.1", "#R6.1", "#R7.1", "#R8.1")},
            {"#R1.1": "TA", "#R2.1": None, "#R3.1": "TB", "#R4.1": "TB", "#R5.1": "/MID", "#R6.1": "PD", "#R7.1": None, "#R8.1": "+5V"},
        )
        wires = self._wire_nets(index)
        self.assertEqual(wires[((30.48, 35.56), (30.48, 25.4))], None)  # the T with no junction
        self.assertEqual(wires[((30.48, 66.04), (30.48, 55.88))], "TB")
        self.assertEqual(wires[((76.2, 25.4), (86.36, 25.4))], "/FLOAT")  # its label names it
        [junction] = index.junctions
        self.assertEqual(junction.net, "TB")
        [flag] = index.no_connects
        self.assertEqual((flag.part, flag.pin), ("R8", "2"))
        [power] = [label for label in index.labels if label.kind == "power"]
        self.assertEqual((power.text, power.net, power.at), ("+5V", "+5V", (76.2, 55.88)))

    def test_a_label_on_a_long_wires_middle_names_it(self) -> None:
        # A wire across most of the sheet, its middle far from its ends: a label there joins it.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long.kicad_sch"
            sheet = SchematicText("long", "long", paper="A3")
            sheet.symbol("Test:R", (25.4, 30.48), "R1")
            sheet.wire((25.4, 25.4), (279.4, 279.4))
            sheet.label("FAR", (152.4, 152.4), "global_label")
            path.write_text(sheet.text(), encoding="utf-8")
            nets = {pin.selector: pin.net for pin in read_index(path).pins}
        self.assertEqual((nets["#R1.1"], nets["#R1.2"]), ("FAR", None))

    def test_kicads_netlist_names_every_pin_and_what_is_wired_to_it(self) -> None:
        index = read_index(self.path, netlist=CONNECTIONS_NETLIST)
        nets = {pin.selector: pin.net for pin in index.pins}
        self.assertEqual((nets["#R2.1"], nets["#R8.2"]), ("unconnected-(R2-~-Pad1)", "unconnected-(R8-~-Pad2)"))
        wires = self._wire_nets(index)
        self.assertEqual(wires[((30.48, 35.56), (30.48, 25.4))], "unconnected-(R2-~-Pad1)")
        self.assertEqual(wires[((25.4, 25.4), (35.56, 25.4))], "TA")
        # A label no pin reaches names no net KiCad has.
        self.assertEqual(wires[((76.2, 25.4), (86.36, 25.4))], None)
        self.assertEqual([label.net for label in index.labels if label.text == "FLOAT"], [None])
        self.assertIn(("unconnected-(R7-~-Pad1)", "Default"), index.nets)


class HierarchyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls._tmp.name)
        write_hierarchy(cls.folder)
        cls.index = read_index(cls.folder / "hier.kicad_sch")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_each_instance_of_a_sheet_is_a_sheet_named_as_its_plot(self) -> None:
        self.assertEqual([(sheet.name, sheet.path, sheet.file) for sheet in self.index.sheets], HIERARCHY_SHEETS)
        self.assertEqual([sheet.title for sheet in self.index.sheets], ["Hier root", "Child", "Child", "Power", "", ""])
        on = {part.ref: self.index.sheets[part.units[0].sheet].name for part in self.index.parts}
        self.assertEqual(on, {"R1": "hier", "R2": "Left", "R3": "Right", "R4": "Left-Deep", "R5": "Right-Deep", "R6": "Power Stäge"})
        # One file, two instances: the same place on each sheet.
        self.assertEqual(self.index.parts[1].units[0].at, self.index.parts[2].units[0].at)

    def test_labels_join_across_sheets_as_kicad_names_them(self) -> None:
        view = SchematicView(self.folder / "hier.kicad_sch", self.index)
        self.assertEqual({net.name: list(net.nodes) for net in view.nets if net.nodes}, HIERARCHY_NETS)
        # Unconnected pins and the floating label have no KiCad netlist to name them here.
        self.assertEqual(view.net("/Power Stäge/FLOAT").nodes, ())

    def test_aligned_to_a_plots_sheets(self) -> None:
        aligned = self.index.aligned(["hier", "Right", "Missing"])
        self.assertEqual([sheet.name for sheet in aligned.sheets], ["hier", "Right", "Missing"])
        self.assertEqual([(part.ref, part.units[0].sheet) for part in aligned.parts], [("R1", 0), ("R3", 1)])
        self.assertEqual({pin.sheet for pin in aligned.pins}, {0, 1})
        self.assertEqual(aligned.as_json()["sheets"][2], {"name": "Missing", "path": "", "file": "", "title": ""})


class ErcPayloadTest(unittest.TestCase):
    """KiCad's ERC report, each item pointed at the pin or net it names. KiCad's ERC JSON writes a
    position as page millimetres divided by 100 (verified on KiCad 10), as these inputs do."""

    INDEX = {
        "sheets": [{"name": "t", "path": "/", "file": "t.kicad_sch", "title": ""}],
        "pins": [{"part": "U2", "number": "7", "name": "VDD", "type": "power_in", "unit": 1, "sheet": 0,
                  "net": "VDD", "at": [50.8, 25.4], "end": [53.34, 25.4], "hidden": False}],
        "labels": [{"net": "SDA", "sheet": 0, "text": "SDA", "kind": "local", "at": [76.2, 30.48], "outline": []}],
    }

    def report(self, violations, path="/"):
        folder = tempfile.mkdtemp()
        report = Path(folder) / "erc.json"
        report.write_text(json.dumps({"coordinate_units": "mm", "sheets": [{"path": path, "violations": violations}]}))
        return report

    def test_a_pin_finding_names_the_pin(self):
        (found,) = erc_payload(self.report([{"severity": "error", "type": "power_pin_not_driven",
            "description": "Input Power pin not driven by any Output Power pins",
            "items": [{"description": "Symbol U2 Pin 7 [VDD, Power input, Line]", "pos": {"x": 0.508, "y": 0.254}}]}]), self.INDEX)
        self.assertEqual(found["items"][0]["ref"], "#U2.7")
        self.assertEqual(found["items"][0]["at"], [50.8, 25.4])
        self.assertEqual(found["items"][0]["sheet"], 0)
        self.assertEqual(found["summary"], "U2 pin 7 (VDD) is a power input that nothing powers")

    def test_a_label_finding_names_its_net(self):
        (found,) = erc_payload(self.report([{"severity": "warning", "type": "label_dangling", "description": "Label not connected",
            "items": [{"description": "Label 'SDA'", "pos": {"x": 0.762, "y": 0.3048}}]}]), self.INDEX)
        self.assertEqual(found["items"][0]["ref"], "#net:SDA")

    def test_no_position_or_an_undrawn_sheet_still_lists(self):
        (a,) = erc_payload(self.report([{"severity": "error", "type": "x", "description": "d",
            "items": [{"description": "Symbol U9"}]}]), self.INDEX)
        self.assertEqual(a["items"][0], {"text": "Symbol U9", "ref": "#U9", "at": None, "sheet": 0})
        (b,) = erc_payload(self.report([{"severity": "error", "type": "x", "description": "d",
            "items": [{"description": "Something", "pos": {"x": 0.01, "y": 0.01}}]}], path="/elsewhere/"), self.INDEX)
        self.assertEqual(b["items"][0], {"text": "Something", "ref": None, "at": None, "sheet": None})


if __name__ == "__main__":
    unittest.main()
