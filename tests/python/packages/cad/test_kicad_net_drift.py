"""``kicad_pcb.edit``'s check of the nets KiCad moved (``cad.kicad._drift``), on board text of the test's own.

KiCad gives copper the net of a pad it overlaps when it loads, commits and saves a board; the edit holds each
track, via, copper shape and zone of the saved board to the net the block asked for, else the one the file had,
and names each that differs with the pad it overlaps or the moved item it touches. The files are read by their
top-level lines in KiCad's layout and parsed whole otherwise, alike. What KiCad really does is
``tests/python/packages/kicad/test_edit.py``'s; this is the comparison, with no KiCad.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_board import BOARD
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.engine.formats.kicad import sexpr  # noqa: E402
from cad.kicad._drift import Watch, board_nets  # noqa: E402

VIA, RING, LONE = ("7a1c0000-0000-4000-8000-0000000000a1", "7a1c0000-0000-4000-8000-0000000000a2",
                   "7a1c0000-0000-4000-8000-0000000000a3")
# A ground via through R1's VBUS pad (F.Cu, at 34.175 15), a ground polygon on B.Cu joined to it, and a ground
# via of its own clear of every pad.
EXTRA = (f'(via (at 34.175 15) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND") (uuid "{VIA}"))'
         f'(gr_poly (pts (xy 33.5 14) (xy 35.5 14) (xy 35.5 16) (xy 33.5 16)) (stroke (width 0) (type solid))'
         f' (fill yes) (layer "B.Cu") (net "GND") (uuid "{RING}"))'
         f'(via (at 30 5) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND") (uuid "{LONE}"))')


def board(extra: str = EXTRA) -> str:
    """The test board with ``extra``, in KiCad's layout (``sexpr.dumps``: a tab a level)."""
    tree = sexpr.parse(BOARD)
    tree.extend(sexpr.parse(f"(x {extra})")[1:])
    return sexpr.dumps(tree)


def moved(text: str, *uuids: str, to: str = "VBUS") -> str:
    """``text`` with the items ``uuids`` saved on ``to``, as KiCad saves a net it moved them to."""
    tree = sexpr.parse(text)
    for node in tree[1:]:
        if isinstance(node, list) and any(sexpr.value(node, "uuid") == uuid for uuid in uuids):
            sexpr.find(node, "net")[1] = to
    return sexpr.dumps(tree)


class NetDrift(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="net-drift-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.before = board()

    def check(self, after: str, watch: Watch | None = None) -> list:
        path = self.folder / "blinky.kicad_pcb"
        path.write_text(after, encoding="utf-8")
        return (watch or Watch()).check(self.before, path)

    def test_kicads_layout_reads_as_the_whole_parse_does(self) -> None:
        laid_out, one_line = board_nets(self.before)[0], board_nets(BOARD.rstrip()[:-1] + EXTRA + ")\n")[0]
        self.assertEqual(one_line, laid_out)
        self.assertEqual(("via", "GND"), laid_out[VIA])
        self.assertEqual(("shape", "GND"), laid_out[RING])
        self.assertEqual(("track", "VBUS"), laid_out["7a1c0000-0000-4000-8000-000000000001"])
        self.assertNotIn("7a1c0000-0000-4000-8000-000000000005", laid_out, "a board text carries no net")
        older = '(kicad_pcb\n\t(net 0 "")\n\t(net 1 "TX{slash}RX")\n\t(via\n\t\t(at 1 1)\n\t\t(net 1)\n\t\t(uuid "ab-cd")\n\t)\n)\n'
        self.assertEqual({"ab-cd": ("via", "TX/RX")}, board_nets(older)[0], "an older board's numbered net, as KiCad shows it")

    def test_an_item_kicad_moved_names_the_pad_it_overlaps_and_what_it_dragged_along(self) -> None:
        changes = self.check(moved(self.before, VIA, RING))
        self.assertEqual([("via", "GND", "VBUS", "#R1.1", None), ("shape", "GND", "VBUS", None, f"#via:{VIA}")],
                         [(change.kind, change.was, change.now, change.pad, change.joined) for change in changes])
        self.assertEqual(f"#via:{VIA}", changes[0].ref)
        line = changes[0].line("blinky.kicad_pcb")
        self.assertTrue(line.startswith(f"warning: blinky.kicad_pcb: KiCad saved via #via:{VIA} on VBUS, not GND: "
                                        "it overlaps pad #R1.1 of VBUS; move it clear"), line)

    def test_a_net_the_block_asked_for_is_no_change_and_one_kicad_overrode_is(self) -> None:
        watch = Watch()
        watch.asked[LONE] = "LED"
        self.assertEqual([], self.check(moved(self.before, LONE, to="LED"), watch))
        watch.asked[VIA] = "LED"  # asked, then taken onto R1.1's net all the same
        self.assertEqual([(VIA, "LED", "VBUS")],
                         [(change.id, change.was, change.now)
                          for change in self.check(moved(moved(self.before, LONE, to="LED"), VIA), watch)])

    def test_a_net_renamed_whole_and_a_netless_item_are_no_change(self) -> None:
        self.assertEqual([], self.check(self.before.replace('"GND"', '"/GND"')), "a netlist's rename: GND is gone")
        netless = EXTRA.replace(f'(net "GND") (uuid "{LONE}")', f'(uuid "{LONE}")')
        self.before = board(netless)
        self.assertEqual([], self.check(board(netless.replace(f'(uuid "{LONE}")', f'(net "LED") (uuid "{LONE}")'))),
                         "KiCad naming a netless via by what it touches is how it connects one")

if __name__ == "__main__":
    unittest.main()
