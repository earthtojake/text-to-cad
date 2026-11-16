"""What ``cad kicad_pcb drc`` says of each finding beyond KiCad's report, read off the saved board (``cad.kicad._located``).

KiCad's JSON report names a finding's items by uuid, position and a sentence; the check adds what the board says
each is -- its kind, layers, net and the board reference that names it -- and the layer the description ends
with. A copper sliver, which KiCad reports with no item and no position, is found again in its layer's saved
copper. No KiCad here: the findings are made as ``_findings`` reads KiCad's report (the KiCad suite runs the real
check, ``tests/python/packages/kicad``), on the test board (``tests/python/support/kicad_board.py``) with a spike
of copper added: a corner of 3 degrees at (34, 4.25), and a sharp corner a second polygon covers.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_board import UUIDS, write_board
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

# A 3-degree spike on F.Cu, and a sharp corner at (10, 4.25) with a square of copper over it (no sliver of the
# merged copper). Eight points each: KiCad's checker passes over an outline of five or fewer.
SPIKE = ('(gr_poly (pts (xy 24 4) (xy 34 4.25) (xy 24 4.5) (xy 23.5 6) (xy 23 6) (xy 22.5 5) (xy 22.5 3.5) (xy 23 3)) '
         '(stroke (width 0) (type solid)) (fill yes) (layer "F.Cu") (uuid "5117e000-0000-4000-8000-000000000001"))')
COVERED = ('(gr_poly (pts (xy 20 4) (xy 10 4.25) (xy 20 4.5) (xy 20.5 6) (xy 21 6) (xy 21.5 5) (xy 21.5 3.5) (xy 21 3)) '
           '(stroke (width 0) (type solid)) (fill yes) (layer "F.Cu") (uuid "5117e000-0000-4000-8000-000000000002"))'
           '(gr_rect (start 9 3) (end 11 5.5) (stroke (width 0) (type solid)) (fill yes) (layer "F.Cu") '
           '(uuid "5117e000-0000-4000-8000-000000000003"))')


def finding(type_: str, description: str, items: list[dict], severity: str = "warning"):
    from cad.kicad._check import _findings

    entry = {"type": type_, "description": description, "severity": severity, "items": items}
    [found] = _findings({"violations": [entry]})
    return found


class LocatedFindings(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = tempfile.TemporaryDirectory(prefix="drc-located-")
        cls.addClassCleanup(cls.folder.cleanup)
        cls.board = write_board(Path(cls.folder.name))
        text = cls.board.read_text(encoding="utf-8").rstrip()
        cls.board.write_text(text[:-1] + SPIKE + COVERED + "\n)\n", encoding="utf-8")

    def test_each_item_says_what_the_board_holds_under_its_uuid_or_its_pad_s_words(self) -> None:
        from cad.kicad._check import issues, with_board

        found = finding("clearance", "Clearance violation (netclass 'Default' clearance 0.2 mm; actual 0.1 mm)", [
            {"uuid": UUIDS["vbus track"], "description": "Track [VBUS] on F.Cu, length 29.2 mm", "pos": {"x": 5, "y": 15}},
            # A pad saved without a uuid gets a new one at each load: found by the report's words instead.
            {"uuid": "0e1d7fab-3e9e-4f1a-bb7e-b6e058405e88", "description": "Pad 2 [LED] of D1 on F.Cu",
             "pos": {"x": 20, "y": 23.175}},
            {"uuid": UUIDS["pour"], "description": "Zone 'GND pour' [GND] on B.Cu", "pos": {"x": 1, "y": 16}},
            {"uuid": "00000000-dead-4000-8000-000000000000", "description": "Something else", "pos": {"x": 1, "y": 1}},
        ])
        [checked] = with_board([finding_ for finding_ in [found]], self.board)
        track, pad, zone, unknown = checked.located
        self.assertEqual(("track", ["F.Cu"], "VBUS", f"#track:{UUIDS['vbus track']}"),
                         (track["kind"], track["layers"], track["net"], track["ref"]))
        self.assertEqual(("pad", "LED", "#D1.2", "D1"), (pad["kind"], pad["net"], pad["ref"], pad["part"]))
        self.assertIn("F.Cu", pad["layers"])
        self.assertEqual(("zone", ["B.Cu"], f"#zone:{UUIDS['pour']}"), (zone["kind"], zone["layers"], zone["ref"]))
        self.assertEqual((None, [], None), (unknown["kind"], unknown["layers"], unknown["ref"]))
        # KiCad's words and position are kept as they were; the finding's own position is still KiCad's.
        self.assertEqual(([5.0, 15.0], "Track [VBUS] on F.Cu, length 29.2 mm"), (track["pos"], track["description"]))
        data = checked.as_data()
        self.assertEqual(([5.0, 15.0], "kicad", None), (data["at"], data["at_source"], data["note"]))
        # The command's findings carry the same items, beside their message and location.
        [issue] = issues([checked])
        self.assertEqual("(5, 15) mm", issue.location)
        self.assertEqual("#D1.2", issue.items[1]["ref"])

    def test_a_finding_s_layer_is_the_one_its_description_ends_with_by_the_file_s_name(self) -> None:
        from cad.kicad._check import with_board

        named = [finding("connection_width", "Copper connection too narrow (minimum 0.15 mm; actual 0.03 mm) (F.Cu)", []),
                 finding("silk_overlap", "Silkscreen clearance (F.Silkscreen)", []),
                 finding("clearance", "Clearance violation (netclass 'Default' clearance 0.2 mm)", [])]
        self.assertEqual(["F.Cu", "F.SilkS", None], [found.layer for found in with_board(named, self.board)])

    def test_a_copper_sliver_is_found_in_its_layer_s_saved_copper_and_says_so(self) -> None:
        from cad.kicad._check import issues, with_board
        from cad.kicad._located import slivers

        self.assertEqual([(34.0, 4.25)], slivers(self.board, "F.Cu"), "the covered corner is no sliver")
        self.assertEqual([], slivers(self.board, "B.Cu"))
        [sliver] = with_board([finding("copper_sliver", "Copper sliver (F.Cu)", [])], self.board)
        data = sliver.as_data()
        self.assertEqual(([34.0, 4.25], "board", "F.Cu"), (data["at"], data["at_source"], data["layer"]))
        self.assertIn("KiCad's report gives a copper sliver no position", data["note"])
        [issue] = issues([sliver])
        self.assertEqual("(34, 4.25) mm", issue.location)
        # More slivers than the copper shows: no pairing guessed; the corners found and the reason said instead.
        two = with_board([finding("copper_sliver", "Copper sliver (F.Cu)", []),
                          finding("copper_sliver", "Copper sliver (F.Cu)", [])], self.board)
        self.assertEqual([None, None], [found.at for found in two])
        self.assertIn("1 corner(s) sharper than 20 degrees for KiCad's 2: (34, 4.25) mm", two[0].note)
        [none] = with_board([finding("copper_sliver", "Copper sliver (B.Cu)", [])], self.board)
        self.assertIsNone(none.as_data()["at"])
        self.assertIn("none was found in B.Cu's saved copper", none.note)


if __name__ == "__main__":
    unittest.main()
