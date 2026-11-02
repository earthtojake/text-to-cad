"""`pcb.inspect_board`: a saved board in one look (format, layers, parts, nets), as plain data, without KiCad."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_board import write_board
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.pcb import inspect_board  # noqa: E402

# A KiCad 9 board: numbered nets, a footprint turned over to the back, a DNP part left out of the BOM.
OLDER = '''(kicad_pcb (version 20241229) (generator "pcbnew") (generator_version "9.0")
 (general (thickness 1.2)) (paper "A4")
 (layers (0 "F.Cu" signal) (4 "In1.Cu" signal) (6 "In2.Cu" signal) (2 "B.Cu" signal) (44 "Edge.Cuts" user))
 (net 0 "") (net 1 "TX/RX")
 (gr_rect (start 10 20) (end 30 45) (stroke (width 0.05) (type default)) (fill none) (layer "Edge.Cuts"))
 (footprint "test:r" (layer "B.Cu") (at 15 25 180)
  (property "Reference" "R7" (at 0 0) (layer "B.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "0R" (at 0 0) (layer "B.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (attr smd dnp exclude_from_bom)
  (pad "1" smd rect (at -0.8 0) (size 0.9 1) (layers "B.Cu" "B.Mask") (net 1 "TX/RX"))
  (pad "2" smd rect (at 0.8 0) (size 0.9 1) (layers "B.Cu" "B.Mask"))))'''


class InspectBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls._tmp.name)
        cls.path = write_board(cls.folder)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_the_test_board_in_one_look(self) -> None:
        summary = inspect_board(self.path)
        self.assertEqual(summary["file"], "blinky.kicad_pcb")
        self.assertEqual(summary["format"], {"version": 20260901, "generator": "pcbnew", "generator_version": "10.99"})
        self.assertEqual(summary["thickness"], 1.6)
        self.assertEqual(summary["size"], [40.0, 30.0])
        self.assertEqual(summary["layers"]["copper"], ["F.Cu", "B.Cu"])
        layers = {layer["name"]: layer for layer in summary["layers"]["all"]}
        self.assertEqual(len(layers), 14)
        self.assertEqual(layers["F.Cu"], {"id": 0, "name": "F.Cu", "type": "signal"})
        self.assertEqual(layers["F.SilkS"], {"id": 5, "name": "F.SilkS", "type": "user", "alias": "F.Silkscreen"})
        self.assertEqual([(part["ref"], part["value"], part["side"], part["at"], part["rotation"], part["pads"])
                          for part in summary["parts"]],
                         [("D1", "LED", "top", [20.0, 24.0], 90.0, 2), ("J1", "Conn_01x02", "top", [5.0, 15.0], 0.0, 2),
                          ("R1", "10k", "top", [35.0, 15.0], 0.0, 2)])
        self.assertEqual(summary["parts"][2]["footprint"], "Resistor_SMD:R_0603_1608Metric")
        self.assertEqual({net["name"]: (net["pads"], net["tracks"], net["vias"], net["zones"])
                          for net in summary["nets"]},
                         {"GND": (2, 1, 1, 1), "LED": (2, 0, 0, 0), "VBUS": (2, 1, 0, 0)})
        self.assertEqual(summary["counts"], {"parts": 3, "pads": 6, "nets": 3, "tracks": 2, "vias": 1, "zones": 1,
                                             "holes": 0})

    def test_the_answer_is_plain_data(self) -> None:
        summary = inspect_board(self.path)
        self.assertEqual(json.loads(json.dumps(summary)), summary)

    def test_an_older_board_with_inner_layers_reads_too(self) -> None:
        path = self.folder / "older.kicad_pcb"
        path.write_text(OLDER, encoding="utf-8")
        summary = inspect_board(path)
        self.assertEqual(summary["format"]["version"], 20241229)
        self.assertEqual(summary["thickness"], 1.2)
        self.assertEqual(summary["size"], [20.0, 25.0])
        self.assertEqual(summary["layers"]["copper"], ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"])
        (part,) = summary["parts"]
        self.assertEqual((part["ref"], part["side"], part["dnp"], part["in_bom"]), ("R7", "bottom", True, False))
        self.assertEqual([net["name"] for net in summary["nets"]], ["TX/RX"])

    def test_a_board_without_an_outline_or_thickness_says_none(self) -> None:
        path = self.folder / "bare.kicad_pcb"
        path.write_text('(kicad_pcb (version 20241229) (layers (0 "F.Cu" signal)))', encoding="utf-8")
        summary = inspect_board(path)
        self.assertIsNone(summary["size"])
        self.assertIsNone(summary["thickness"])
        self.assertIsNone(summary["format"]["generator"])
        self.assertEqual((summary["parts"], summary["nets"]), ([], []))

    def test_what_is_not_a_board_is_refused(self) -> None:
        (self.folder / "notes.txt").write_text("hello", encoding="utf-8")
        (self.folder / "odd.kicad_pcb").write_text("(kicad_sch)", encoding="utf-8")
        (self.folder / "binary.kicad_pcb").write_bytes(b"\xff\xfe\x00")
        with self.assertRaisesRegex(ValueError, "notes.txt is not a KiCad board"):
            inspect_board(self.folder / "notes.txt")
        with self.assertRaisesRegex(ValueError, "odd.kicad_pcb is not a KiCad board"):
            inspect_board(self.folder / "odd.kicad_pcb")
        with self.assertRaisesRegex(ValueError, "binary.kicad_pcb is not a readable KiCad board"):
            inspect_board(self.folder / "binary.kicad_pcb")
        with self.assertRaises(FileNotFoundError):
            inspect_board(self.folder / "missing.kicad_pcb")


if __name__ == "__main__":
    unittest.main()
