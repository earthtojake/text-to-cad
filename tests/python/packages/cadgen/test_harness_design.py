"""The harness SDK's contract, without WireViz or KiCad: connectors, cables, connections, refusals.

Boards come from the tiny project-local library (``kicad_library``), so a
board connector's pins and nets are real ``pcb.Board`` pins and nets; nothing
here runs WireViz (tests/python/packages/harness does).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_library import write_test_library
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import harness  # noqa: E402
from cadgen.kicad.design import Board  # noqa: E402

HarnessError = harness.HarnessError


class _Outline:
    """Board(outline=...) is only read when a board is written; a harness never writes one."""


class HarnessDesignTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.library = write_test_library(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def board(self, title: str, order: tuple[str, str] = ("VBUS", "GND"), *, named: bool = True) -> Board:
        """A board whose two-pin connector J1 carries ``order`` on pins 1 and 2."""
        board = Board(outline=_Outline(), libraries=[self.library], title=title)
        nets = {name: board.net(name if named else None) for name in ("VBUS", "GND")}
        j1 = board.part("Test:R", footprint="Test:R_0603", ref="J1")
        load = board.part("Test:R", footprint="Test:R_0603")
        board.connect(nets[order[0]], j1[1], load[1])
        board.connect(nets[order[1]], j1[2], load[2])
        return board

    def cable(self, h: harness.Harness, name: str = "W1", **fields):
        return h.cable(name, **{"colors": ["RD", "BK"], "gauge": "24 AWG", "length": 300, **fields})

    def test_a_board_connector_takes_the_parts_pins_labelled_with_their_nets(self) -> None:
        board = self.board("controller")
        h = harness.Harness()
        by_ref = h.connector(board, "J1", type="JST PH 2.0 mm housing")
        by_part = h.connector(next(part for part in board.parts if part.ref == "J1"), name="J1_AGAIN", type="JST PH")
        for connector in (by_ref, by_part):
            self.assertEqual([(pin.id, pin.label, pin.net) for pin in connector.pins], [(1, "VBUS", "VBUS"), (2, "GND", "GND")])
        self.assertEqual(by_ref.name, "J1")  # the part's reference, unless name= says otherwise
        self.assertIs(by_ref["VBUS"], by_ref[1])  # a pin by number or by its label
        self.assertEqual(by_ref.fields["notes"], "mates J1 of controller: R_0603")

    def test_a_board_connector_needs_its_housing_named_and_its_pins_from_the_board(self) -> None:
        board = self.board("controller")
        h = harness.Harness()
        with self.assertRaisesRegex(HarnessError, r"name the housing that mates with the board's header \(Test:R_0603\)"):
            h.connector(board, "J1")
        with self.assertRaisesRegex(HarnessError, "pins come from the board"):
            h.connector(board, "J1", type="JST PH", pinlabels=["A", "B"])
        with self.assertRaisesRegex(HarnessError, "the board has no part 'J9'; its parts are J1, R1"):
            h.connector(board, "J9", type="JST PH")
        h.connector(board, "J1", type="JST PH")
        with self.assertRaisesRegex(HarnessError, "J1 is already a connector .* name=\"J1_2\""):
            h.connector(self.board("driver"), "J1", type="JST PH")

    def test_3d_geometry_is_not_a_board(self) -> None:
        # What a @pcb board with a 3D export hands another model's body: its geometry.
        lazy = type("LazyCompound", (), {})()
        with self.assertRaisesRegex(HarnessError, "got 3D geometry, not a board. Call the board's @pcb model inside the @harness"):
            harness.Harness().connector(lazy, "J1", type="JST PH")

    def test_a_free_connector_takes_pins_labels_or_a_count(self) -> None:
        h = harness.Harness()
        motor = h.connector("M1", pinlabels=["A+", "A-", "B+", "B-"], type="Stepper lead")
        self.assertEqual([pin.id for pin in motor.pins], [1, 2, 3, 4])
        self.assertIs(motor["B+"], motor[3])
        lettered = h.connector("X2", pins=["A1", "B1"])
        self.assertEqual([pin.id for pin in lettered.pins], ["A1", "B1"])
        self.assertEqual(len(h.connector("X3", pincount=3).pins), 3)
        refusals = {
            "needs its pins": lambda: h.connector("X4"),
            r"a different number of pins in each list \(pins 2, pinlabels 1\)": lambda: h.connector("X5", pins=[1, 2], pinlabels=["A"]),
            "has pin 1 twice": lambda: h.connector("X6", pins=[1, "1"]),
            "gives pin 'A' the label 'B', which is another pin's name": lambda: h.connector("X7", pins=["A", "B"], pinlabels=["B", "x"]),
            "reads it as the number 1": lambda: h.connector("X8", pins=["01"]),
            "reads it as a range of pins": lambda: h.connector("X9", pins=["1-2"]),
            "style=\"simple\", which is one pin, but it has 2": lambda: h.connector("X10", pincount=2, style="simple"),
            "a free connector is named by its first argument": lambda: h.connector("X11", pincount=1, name="Y"),
            r"has 2 pins labelled 'GND' \(pins 1, 2\)": lambda: h.connector("X12", pinlabels=["GND", "GND"])["GND"],
            "has no pin 'Z'; its pins are 1=A\\+, 2=A-": lambda: h.connector("X13", pinlabels=["A+", "A-"])["Z"],
        }
        for message, attempt in refusals.items():
            with self.subTest(message=message), self.assertRaisesRegex(HarnessError, message):
                attempt()

    def test_keywords_designators_and_text_are_closed(self) -> None:
        h = harness.Harness()
        with self.assertRaisesRegex(HarnessError, "connector\\(\\) has no 'pinlabel'; did you mean 'pinlabels'\\?"):
            h.connector("X1", pinlabel=["A"])
        with self.assertRaisesRegex(HarnessError, "cable\\(\\) has no 'colours'; did you mean 'colors'\\?"):
            h.cable("W1", colours=["RD"], gauge="24 AWG", length=10)
        for name in ("X.1", "1X", "X 1", "__X"):
            with self.subTest(name=name), self.assertRaises(HarnessError):
                h.connector(name, pincount=1)
        with self.assertRaisesRegex(HarnessError, "contains '&'.*Graphviz HTML labels"):
            h.connector("X1", pincount=1, type="Plug & socket")
        with self.assertRaisesRegex(HarnessError, "control character"):
            h.connector("X1", pincount=1, type="two\nlines")

    def test_cables_take_colours_gauges_and_lengths_wireviz_reads(self) -> None:
        h = harness.Harness()
        cable = h.cable("W1", color_code="BW", wirecount=3, gauge="22awg", length=1234.5, shield=True)
        self.assertEqual(cable.colors, ["BK", "WH", "BK"])  # a code shorter than the cable starts again
        self.assertEqual((cable.fields["gauge"], cable.fields["length"]), ("22 AWG", 1.2345))  # mm in, metres out
        self.assertEqual(h.cable("W2", colors=["WHGN"], gauge=0.25, length=10).fields["gauge"], "0.25 mm2")
        self.assertEqual(cable["s"].id, "s")
        self.assertIs(cable["WH"], cable[2])
        refusals = {
            "needs gauge=": dict(colors=["RD"], length=10),
            "needs length=": dict(colors=["RD"], gauge="24 AWG"),
            "gauge=22 reads as 22 mm²": dict(colors=["RD"], gauge=22, length=10),
            "AWG gauge is a whole number": dict(colors=["RD"], gauge="22.5 AWG", length=10),
            "'RX' is not a WireViz colour": dict(colors=["RX"], gauge="24 AWG", length=10),
            "colour codes are capitals, 'RD'": dict(colors=["rd"], gauge="24 AWG", length=10),
            "wirecount=3 but 2 colors": dict(colors=["RD", "BK"], wirecount=3, gauge="24 AWG", length=10),
            "color_code='DIN' needs wirecount=": dict(color_code="DIN", gauge="24 AWG", length=10),
            "did you mean 'DIN'": dict(color_code="DINN", wirecount=2, gauge="24 AWG", length=10),
            "length is millimetres, a number": dict(colors=["RD"], gauge="24 AWG", length="300 mm"),
            "category is \"bundle\"": dict(colors=["RD"], gauge="24 AWG", length=10, category="loose"),
        }
        for index, (message, fields) in enumerate(refusals.items()):
            with self.subTest(message=message), self.assertRaisesRegex(HarnessError, message):
                h.cable(f"X{index}", **fields)
        with self.assertRaisesRegex(HarnessError, r"2 wires coloured 'BK' \(wires 1, 3\)"):
            cable["BK"]

    def test_a_pin_takes_one_wire_and_a_wire_is_connected_once(self) -> None:
        h = harness.Harness()
        a, b = h.connector("A", pincount=3), h.connector("B", pincount=3)
        w = h.cable("W1", colors=["RD", "BK", "YE"], gauge="24 AWG", length=100)
        h.connect([a[1], a[2]], [w[1], w[2]], [b[1], b[2]])
        with self.assertRaisesRegex(HarnessError, r"A pin 1 is already wired \(A pin 1 -> W1 wire 1 \(RD\) -> B pin 1\)"):
            h.connect(a[1], w[3], b[3])
        with self.assertRaisesRegex(HarnessError, "W1 wire 2 \\(BK\\) is already connected"):
            h.connect(a[3], w[2], b[3])
        with self.assertRaisesRegex(HarnessError, "lists of 2, 1, 2 items"):
            h.connect([a[3], b[3]], [w[3]], [b[3], a[3]])
        with self.assertRaisesRegex(HarnessError, r"takes \(pin, wire, pin\), \(pin, wire\) or \(wire, pin\); got \(wire, pin, pin\)"):
            h.connect(w[3], a[3], b[3])
        with self.assertRaisesRegex(HarnessError, "takes pins: A\\[1\\], or all of A's pins as a.pins"):
            h.connect(a, w.wires, b)
        h.connect(a[3], w[3])  # a wire with a free end
        self.assertEqual(len(h.connections), 3)

    def test_a_wire_between_boards_joins_one_net(self) -> None:
        h = harness.Harness()
        a = h.connector(self.board("controller"), "J1", name="CTRL_J1", type="JST PH")
        b = h.connector(self.board("driver", ("GND", "VBUS")), "J1", name="DRV_J1", type="JST PH")
        w = self.cable(h)
        with self.assertRaisesRegex(
            HarnessError,
            r"W1 wire 1 \(RD\) runs from CTRL_J1 pin 1 \(net VBUS on its board\) to DRV_J1 pin 1 \(net GND on its board\): "
            r"the two ends carry different nets \(DRV_J1 carries VBUS on pin 2\)",
        ):
            h.connect(a.pins, w.wires, b.pins)
        self.assertEqual(h.connections, [])  # a refused call connects nothing
        h.connect([a["VBUS"], a["GND"]], w.wires, [b["VBUS"], b["GND"]])
        self.assertEqual([(c.start.net, c.end.net) for c in h.connections], [("VBUS", "VBUS"), ("GND", "GND")])

    def test_joins_says_a_wire_crosses_nets_on_purpose_and_is_checked(self) -> None:
        h = harness.Harness()
        a = h.connector(self.board("controller"), "J1", name="A", type="JST PH")
        b = h.connector(self.board("driver"), "J1", name="B", type="JST PH")
        w = self.cable(h)
        with self.assertRaisesRegex(HarnessError, r"joins=\('GND', 'VBUS'\), but .* joins= names those two nets, in that order"):
            h.connect(a[1], w[1], b[2], joins=("GND", "VBUS"))
        with self.assertRaisesRegex(HarnessError, "both ends carry VBUS: drop joins="):
            h.connect(a[1], w[1], b[1], joins=("VBUS", "VBUS"))
        with self.assertRaisesRegex(HarnessError, "joins= declares one wire's crossing"):
            h.connect([a[1], a[2]], w.wires, [b[2], b[1]], joins=("VBUS", "GND"))
        h.connect(a[1], w[1], b[2], joins=("VBUS", "GND"))
        self.assertEqual(h.connections[0].joins, ("VBUS", "GND"))

    def test_board_ends_need_named_nets(self) -> None:
        h = harness.Harness()
        a = h.connector(self.board("controller", named=False), "J1", name="A", type="JST PH")
        b = h.connector(self.board("driver", named=False), "J1", name="B", type="JST PH")
        w = self.cable(h)
        with self.assertRaisesRegex(HarnessError, "neither board names that net .* board.net\\(\"NAME\"\\)"):
            h.connect(a[1], w[1], b[1])

    def test_every_connector_and_cable_must_be_used(self) -> None:
        h = harness.Harness()
        self.assertEqual(h.problems(), ["the harness connects nothing: join pins through wires with h.connect(pin, wire, pin)"])
        a, b, spare = h.connector("A", pincount=1), h.connector("B", pincount=1), h.connector("SPARE", pincount=1)
        w, extra = self.cable(h, colors=["RD"]), self.cable(h, "W2", colors=["BK"])
        h.connect(a[1], w[1], b[1])
        problems = h.problems()
        self.assertEqual(len(problems), 2)
        self.assertIn("connector SPARE is declared but no wire reaches it", problems[0])
        self.assertIn("cable W2 is declared but connected to nothing", problems[1])
        del spare, extra


if __name__ == "__main__":
    unittest.main()
