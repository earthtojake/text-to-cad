"""The board SDK's contract, without KiCad: parts, pins, nets, placement, refusals.

Everything here runs against a tiny project-local library (``kicad_library``)
so the suite needs no KiCad install; what KiCad itself decides is the KiCad
suite's (tests/python/packages/kicad).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_library import write_test_library
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.kicad.design import Board, Circuit, DesignError  # noqa: E402


class _Outline:
    """Board(outline=...) is only read when a board is written; these tests never write."""


class PcbDesignTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.library = write_test_library(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def board(self) -> Board:
        return Board(outline=_Outline(), libraries=[self.library])

    def test_pins_by_number_or_unambiguous_name(self) -> None:
        board = self.board()
        amp = board.part("Test:AMP")
        self.assertEqual(amp[1].number, "1")
        self.assertEqual(amp["OUT"].number, "2")
        with self.assertRaisesRegex(DesignError, "2 pins named 'GND'.*3, 4"):
            amp["GND"]
        with self.assertRaisesRegex(DesignError, "has no pin 'VCC'; its pins are 1=IN, 2=OUT, 3=GND, 4=GND"):
            amp["VCC"]

    def test_references_number_themselves_and_never_collide(self) -> None:
        board = self.board()
        first = board.part("Test:R", footprint="Test:R_0603")
        board.part("Test:R", footprint="Test:R_0603", ref="R3")
        second = board.part("Test:R", footprint="Test:R_0603")
        self.assertEqual((first.ref, second.ref), ("R1", "R2"))
        with self.assertRaisesRegex(DesignError, "ref R3 is used twice"):
            board.part("Test:R", footprint="Test:R_0603", ref="R3")

    def test_a_net_carries_the_current_its_script_gives(self) -> None:
        board = self.board()
        vbus = board.net("VBUS", current=2.0)
        self.assertEqual(vbus.current, 2.0)
        self.assertIs(board.net("VBUS"), vbus)
        self.assertEqual(board.net("VBUS", current=2.0).current, 2.0)
        with self.assertRaisesRegex(DesignError, "already carries 2 A"):
            board.net("VBUS", current=3.0)
        with self.assertRaisesRegex(DesignError, "positive"):
            board.net("V3V3", current=0)
        self.assertIsNone(board.net("SDA").current)

    def test_a_pin_joins_one_net(self) -> None:
        board = self.board()
        r1 = board.part("Test:R", footprint="Test:R_0603")
        vcc, gnd = board.net("VCC"), board.net("GND")
        board.connect(vcc, r1[1])
        self.assertIs(board.net("VCC"), vcc)
        with self.assertRaisesRegex(DesignError, r"already on net VCC"):
            board.connect(gnd, r1[1])
        board.no_connect(r1[2])
        with self.assertRaisesRegex(DesignError, "marked no-connect"):
            board.connect(gnd, r1[2])

    def test_pins_drawn_at_one_point_are_one_connection(self) -> None:
        # A connector's repeated pins (a Pi header's GNDs, its two 3V3s) are stacked in KiCad's
        # symbol: one point in the schematic, so connecting one connects the stack.
        board = self.board()
        hdr = board.part("Test:HDR", ref="J1")
        self.assertEqual([pin.number for pin in hdr[2].stack], ["2", "4"])
        gnd = board.net("GND")
        board.connect(gnd, hdr[2])
        self.assertIs(hdr[4].net, gnd)
        board.no_connect(hdr[1])
        self.assertEqual(hdr.unconnected(), [])
        with self.assertRaisesRegex(DesignError, r"J1\.4 \(GND\)\) is already on net GND.*one point with Pin\(J1\.2"):
            board.connect(board.net("VCC"), hdr[4])
        with self.assertRaisesRegex(DesignError, r"J1\.3 \(3V3\)\) is marked no-connect.*stacked pins"):
            board.connect(board.net("VCC"), hdr[3])

    def test_an_unnamed_net_is_named_after_its_first_pin_as_kicad_names_one(self) -> None:
        board = self.board()
        r1 = board.part("Test:R", footprint="Test:R_0603")
        amp = board.part("Test:AMP")
        net = board.net()
        board.connect(net, amp["IN"], r1[2])
        self.assertEqual(net.name, "Net-(R1-Pad2)")

    def test_pad_positions_follow_rotation_and_side(self) -> None:
        board = self.board()
        top = board.part("Test:R", footprint="Test:R_0603")
        bottom = board.part("Test:R", footprint="Test:R_0603")
        # Pad 1 sits at x = -0.825 in the footprint. Rotated 90 degrees counter-clockwise
        # (seen from the top, y up) it lands below the part's centre.
        board.place(top, at=(10, 5), rotation=90)
        self.assertEqual(top[1].position, (10.0, 4.175))
        self.assertEqual(top[2].position, (10.0, 5.825))
        # A bottom part is flipped top-to-bottom in its own frame, as KiCad flips it:
        # pads on the x axis stay where they were.
        board.place(bottom, at=(-3, 2), side="bottom")
        self.assertEqual(bottom[1].position, (-3.825, 2.0))

    def test_unplaced_parts_and_missing_classes_stop_a_board(self) -> None:
        board = self.board()
        r1 = board.part("Test:R", footprint="Test:R_0603")
        net = board.net("SIG", netclass="Fast")
        board.connect(net, r1[1])
        problems = board.problems()
        self.assertIn("R1 is not placed: call board.place(r1, at=(x, y))", problems)
        self.assertTrue(any("never defined" in problem for problem in problems), problems)

    def test_a_footprint_must_have_a_pad_for_every_pin(self) -> None:
        board = self.board()
        with self.assertRaisesRegex(DesignError, r"pin\(s\) 2 that footprint Test:ONE_PAD has no pad for"):
            board.part("Test:R", footprint="Test:ONE_PAD")

    def test_a_board_needs_a_footprint_and_a_circuit_does_not(self) -> None:
        with self.assertRaisesRegex(DesignError, "has no default footprint"):
            self.board().part("Test:R")
        circuit = Circuit(libraries=[self.library])
        resistor = circuit.part("Test:R", value="10k")
        self.assertEqual(resistor.value, "10k")

    def test_a_derived_symbol_is_its_parent_with_its_own_fields(self) -> None:
        board = self.board()
        reg = board.part("Test:REG")  # extends AMP; default footprint from its own fields
        self.assertEqual(reg.value, "REG")
        self.assertEqual(reg["OUT"].electrical_type, "output")
        self.assertEqual(reg.footprint.lib_id, "Test:SOT4")
        self.assertEqual(reg.symbol.tree[1], "Test:REG")
        self.assertNotIn("extends", str(reg.symbol.tree))

    def test_a_power_symbol_is_a_net_not_a_part(self) -> None:
        with self.assertRaisesRegex(DesignError, "power symbol"):
            self.board().part("Test:PWR")

    def test_unknown_names_suggest_what_is_there(self) -> None:
        with self.assertRaisesRegex(DesignError, "has no 'Resistor'"):
            self.board().part("Test:Resistor", footprint="Test:R_0603")
        with self.assertRaisesRegex(DesignError, "did you mean R_0603"):
            self.board().part("Test:R", footprint="Test:R_0605")

    def test_a_board_takes_its_fabs_limits_for_its_layer_count(self) -> None:
        from cadgen.kicad.fabs import FABS, JLCPCB, OSHPARK

        self.assertEqual((self.board().fab, self.board().rules), (JLCPCB, JLCPCB.rules))
        four = Board(outline=_Outline(), layers=4, fab=OSHPARK, libraries=[self.library])
        self.assertEqual(four.rules, OSHPARK.multilayer)
        mine = OSHPARK.rules.replace(min_track_width=0.2)
        self.assertEqual(Board(outline=_Outline(), fab=OSHPARK, rules=mine, libraries=[self.library]).rules, mine)
        with self.assertRaisesRegex(DesignError, "fab= takes a pcb.Fab: one of pcb.JLCPCB"):
            Board(outline=_Outline(), fab="jlcpcb", libraries=[self.library])
        # Every preset's default tracks and vias are ones that fab makes, and a default track
        # passing a default via keeps the fab's hole clearance: what the router draws passes.
        for fab in FABS.values():
            for rules in (fab.rules, fab.multilayer):
                with self.subTest(fab=fab.name):
                    annular = (rules.via_diameter - rules.via_drill) / 2
                    self.assertGreaterEqual(rules.track_width, rules.min_track_width)
                    self.assertGreaterEqual(rules.clearance, rules.min_clearance)
                    self.assertGreaterEqual(rules.via_diameter, rules.min_via_diameter)
                    self.assertGreaterEqual(rules.via_drill, rules.min_through_hole_diameter)
                    self.assertGreaterEqual(annular + 1e-9, rules.min_via_annular_width)
                    self.assertGreaterEqual(rules.clearance + annular + 1e-9, rules.min_hole_clearance)

    def test_copper_must_be_on_a_layer_the_board_has(self) -> None:
        board = self.board()
        net = board.net("GND")
        with self.assertRaisesRegex(DesignError, "not a copper layer of this 2-layer board; use one of F.Cu, B.Cu"):
            board.track(net, [(0, 0), (1, 0)], layer="In1.Cu")
        four = Board(outline=_Outline(), layers=4, libraries=[self.library])
        self.assertEqual(four.copper_layers, ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu"))

    def test_copper_ending_on_a_pin_must_share_its_net_and_reach_its_pad(self) -> None:
        board = self.board()
        vin, gnd = board.net("VIN"), board.net("GND")
        top = board.part("Test:R", footprint="Test:R_0603", ref="R1")
        under = board.part("Test:R", footprint="Test:R_0603", ref="R2")
        board.connect(vin, top[1], under[1])
        board.connect(gnd, top[2])
        board.no_connect(under[2])
        board.place(top, at=(0, 0))
        board.place(under, at=(10, 0), side="bottom")
        board.track(vin, [top[1], (5, 3), (9.175, 3)])  # ends on its own net's pad: fine
        with self.assertRaisesRegex(DesignError, "a VIN track ends on R1 pin 2, which is on net GND, so the track would short"):
            board.track(vin, [top[2], (5, 3)])
        with self.assertRaisesRegex(DesignError, "R2 pin 2, which is marked no-connect"):
            board.track(vin, [(5, 3), under[2]])
        # A bottom part's SMD pads are copper on B.Cu only.
        with self.assertRaisesRegex(DesignError, "R2 pin 1 has copper on B.Cu only .R2 is on the bottom., so a track on F.Cu"):
            board.track(vin, [(5, 3), under[1]])
        board.track(vin, [(9, 3), under[1]], layer="B.Cu")
        with self.assertRaisesRegex(DesignError, "an arc on F.Cu cannot reach it"):
            board.arc(vin, start=(8, 4), mid=(8.5, 3), end=under[1])


if __name__ == "__main__":
    unittest.main()
