"""Plain sentences for KiCad's findings: what a person reads in Checks and the agent reads in a build."""

from __future__ import annotations

import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.kicad.phrasing import name_item, summarize  # noqa: E402


class NameItemTest(unittest.TestCase):
    def test_pads_pins_copper_and_parts(self):
        self.assertEqual(name_item("Pad 7 [VDD] of U2 on F.Cu"), "U2 pad 7 (VDD)")
        self.assertEqual(name_item("Symbol U2 Pin 7 [VDD, Power input, Line]"), "U2 pin 7 (VDD)")
        self.assertEqual(name_item("Track [SDA] on F.Cu, length 3.2000 mm"), "the SDA track")
        self.assertEqual(name_item("Via [GND] on F.Cu - B.Cu"), "a GND via")
        self.assertEqual(name_item("Zone [GND] on B.Cu"), "the GND pour")
        self.assertEqual(name_item("Footprint C4"), "C4")
        self.assertEqual(name_item("Pad 2 [GND] of C1 on F.Cu"), "C1 pad 2 (GND)")
        self.assertEqual(name_item("PTH pad 1 [SERVO1] of J2"), "J2 pad 1 (SERVO1)")
        self.assertEqual(name_item("PTH pad SH [GND] of J1"), "J1 pad SH (GND)")
        self.assertEqual(name_item("NPTH pad of J1"), "a J1 mounting hole")
        self.assertEqual(name_item("Via [CC2] on F.Cu - B.Cu"), "a CC2 via")
        self.assertEqual(name_item("Zone [GND] on F.Cu, priority 0"), "the GND pour")
        self.assertEqual(name_item("Segment on Edge.Cuts"), "the board edge")
        self.assertEqual(name_item("Symbol J1 Pin A5 [CC1, Bidirectional, Line]"), "J1 pin A5 (CC1)")
        self.assertEqual(name_item("Global Label 'CC1'"), "label CC1")
        self.assertEqual(name_item("Something new"), "Something new")


class SummarizeTest(unittest.TestCase):
    def test_clearance_names_both_items_and_both_distances(self):
        self.assertEqual(
            summarize("drc", "clearance", "Clearance violation (netclass 'Default' clearance 0.2000 mm; actual 0.1500 mm)",
                      ["Track [SDA] on F.Cu, length 3.2000 mm", "Track [SCL] on F.Cu, length 2.0000 mm"]),
            "The SDA track and the SCL track are 0.15 mm apart; the rules need 0.2 mm",
        )

    def test_real_kicad_rule_messages(self):
        track = "Track [+3V3] on F.Cu, length 1.1313 mm"
        self.assertEqual(
            summarize("drc", "track_width", "Track width (rule 'wide' min width 2.0000 mm; actual 0.2500 mm)", [track]),
            "The +3V3 track is 0.25 mm wide; the rules need at least 2 mm",
        )
        self.assertEqual(
            summarize("drc", "annular_width", "Annular width (rule 'ring' min annular width 1.0000 mm; actual 0.1500 mm)",
                      ["Via [CC2] on F.Cu - B.Cu"]),
            "A CC2 via has a 0.15 mm ring of copper round its hole; the rules need at least 1 mm",
        )
        self.assertEqual(
            summarize("drc", "hole_clearance", "Hole clearance violation (rule 'hole' clearance 3.0000 mm; actual 2.0221 mm)",
                      [track, "NPTH pad of J1"]),
            "The +3V3 track is 2.022 mm from a hole; the rules need 3 mm",
        )
        self.assertEqual(
            summarize("drc", "copper_edge_clearance",
                      "Board edge clearance violation (rule 'edge' clearance 5.0000 mm; actual 3.3750 mm)",
                      ["Segment on Edge.Cuts", track]),
            "The +3V3 track is 3.375 mm from the board edge; the rules need 5 mm",
        )
        self.assertEqual(
            summarize("drc", "clearance", "Clearance violation (rule 'big_clear' clearance 3.0000 mm; actual 1.4894 mm)",
                      ["Pad 2 [GND] of C1 on F.Cu", "PTH pad 1 [SERVO1] of J2"]),
            "C1 pad 2 (GND) and J2 pad 1 (SERVO1) are 1.489 mm apart; the rules need 3 mm",
        )

    def test_a_number_in_a_rule_name_is_not_the_required_value(self):
        self.assertEqual(
            summarize("drc", "track_width", "Track width (rule 'min 9 mm' min width 2.0000 mm; actual 0.2500 mm)", ["Track [A] on F.Cu"]),
            "The A track is 0.25 mm wide; the rules need at least 2 mm",
        )

    def test_unconnected_pin(self):
        self.assertEqual(
            summarize("erc", "pin_not_connected", "Pin not connected", ["Symbol U2 Pin 7 [VDD, Power input, Line]"]),
            "U2 pin 7 (VDD) isn't connected to anything",
        )

    def test_power_input_nothing_drives(self):
        self.assertEqual(
            summarize("erc", "power_pin_not_driven", "Input Power pin not driven by any Output Power pins",
                      ["Symbol U2 Pin 7 [VDD, Power input, Line]"]),
            "U2 pin 7 (VDD) is a power input that nothing powers",
        )

    def test_unrouted(self):
        self.assertEqual(
            summarize("unconnected", "unconnected_items", "Missing connection between items",
                      ["Pad 1 [VIN] of U1 on F.Cu", "Pad 2 [VIN] of C1 on F.Cu"]),
            "U1 pad 1 (VIN) and C1 pad 2 (VIN) still need a track",
        )

    def test_an_unknown_type_or_missing_numbers_reads_as_kicad_wrote_it(self):
        self.assertEqual(summarize("drc", "brand_new_check", "KiCad's words", ["Footprint C4"]), "KiCad's words")
        self.assertEqual(summarize("drc", "clearance", "Clearance violation", ["Footprint C4"]), "Clearance violation")


if __name__ == "__main__":
    unittest.main()
