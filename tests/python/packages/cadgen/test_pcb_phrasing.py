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
        self.assertEqual(name_item("Something new"), "Something new")


class SummarizeTest(unittest.TestCase):
    def test_clearance_names_both_items_and_both_distances(self):
        self.assertEqual(
            summarize("drc", "clearance", "Clearance violation (netclass 'Default' clearance 0.2000 mm; actual 0.1500 mm)",
                      ["Track [SDA] on F.Cu, length 3.2000 mm", "Track [SCL] on F.Cu, length 2.0000 mm"]),
            "The SDA track and the SCL track are 0.15 mm apart; the rules need 0.2 mm",
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
