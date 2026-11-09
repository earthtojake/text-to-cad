"""``cad.kicad.route`` on real boards: kicode's KiCad edits them, and KiCad's own DRC judges the copper.

The board is written here into a temporary folder with its project (two netclasses, ``VCC`` in ``Power``, 0.5 mm
wide). In one ``kicad_pcb.edit`` an agent's script places a footprint that carries its own keep-out -- moved and
turned as the pcb skill's placement reference does it (its zone's outline kept across the move), then flipped by
KiCad, so the keep-out lands on the back, in the footprint's frame -- and routes a plan round it:

- ``KEEP``, two header pins whose straight line crosses that keep-out, on the back alone: routed round it;
- ``VCC`` on the front: routed at its netclass's 0.5 mm;
- ``SIG``, two resistors on either side of a track and a via of net ``OLD`` already on the board: routed round
  them, the old copper left as it was (its uuids, ends and position);
- ``WALL``, a resistor inside a closed ring of keep-out: not routed, said by name, the rest routed all the same;
- ``TEE``, three pads: the third joins the track between the first two where it passes, a T where three tracks
  end (the router splits its own track there, as KiCad's router leaves a T), and DRC calls no end of the
  router's dangling.

KiCad's DRC of the saved board finds no error but the connections left unrouted: WALL's, and OLD's, which the
plan leaves to the agent. A copy of the placed board
with a track drawn through the keep-out where the router read it is flagged ``items_not_allowed`` by the same
DRC: the keep-out is there, so the router's going round it is the proof. The same script on a second copy of the
board writes the same copper. Runs in the KiCad job (``scripts/test/test-kicad.sh``).
"""

from __future__ import annotations

import json
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import kicode

PROJECT = {
    "board": {"design_settings": {"rules": {
        "min_clearance": 0.15, "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.25, "min_hole_to_hole": 0.5,
        "min_track_width": 0.15, "min_via_diameter": 0.6, "min_through_hole_diameter": 0.3, "min_via_annular_width": 0.1,
        "max_error": 0.005}}},
    "meta": {"filename": "route.kicad_pro", "version": 3},
    "net_settings": {
        "classes": [
            {"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.8, "via_drill": 0.4,
             "priority": 2147483647},
            {"name": "Power", "clearance": 0.25, "track_width": 0.5, "via_diameter": 0.8, "via_drill": 0.4, "priority": 0},
        ],
        "meta": {"version": 4},
        "netclass_patterns": [{"netclass": "Power", "pattern": "VCC"}],
    },
}

_COUNT = iter(range(1, 10 ** 6))


def _uuid() -> str:
    return f"0e5a0000-0000-4000-8000-{next(_COUNT):012x}"


def _reference(ref: str, side: str = "F") -> str:
    return (f'(property "Reference" "{ref}" (at 0 -2 0) (layer "{side}.SilkS") (uuid "{_uuid()}") '
            f'(effects (font (size 1 1) (thickness 0.15))))')


def _resistor(ref: str, x: float, y: float, one: str, two: str) -> str:
    pads = "".join(f'(pad "{n}" smd roundrect (at {dx} 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask") '
                   f'(roundrect_rratio 0.25) (net "{net}") (uuid "{_uuid()}"))'
                   for n, dx, net in (("1", -0.825, one), ("2", 0.825, two)))
    return (f'(footprint "R_0603" (layer "F.Cu") (uuid "{_uuid()}") (transform (translate {x} {y}) (rotate 0) '
            f'(scale 1 1)) {_reference(ref)} {pads})')


def _header(ref: str, x: float, y: float, nets: list[str]) -> str:
    pads = "".join(f'(pad "{k + 1}" thru_hole circle (at 0 {k * 2.54}) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") '
                   f'(net "{net}") (uuid "{_uuid()}"))' for k, net in enumerate(nets))
    return (f'(footprint "Header" (layer "F.Cu") (uuid "{_uuid()}") (transform (translate {x} {y}) (rotate 0) '
            f'(scale 1 1)) {_reference(ref)} {pads})')


def _keepout(points: list[tuple[float, float]], layers: str) -> str:
    return (f'(zone (net 0) (net_name "") (layers {layers}) (uuid "{_uuid()}") (hatch edge 0.5) (keepout (tracks not_allowed) '
            f'(vias not_allowed) (pads allowed) (copperpour allowed) (footprints allowed)) (polygon (pts '
            + " ".join(f"(xy {x} {y})" for x, y in points) + ")))")


#: The old copper: a track and a via of net OLD between R1 and R2, which SIG must route round and leave as they are.
OLD = {"track": "0e5a0000-0000-4000-8000-00000000f001", "via": "0e5a0000-0000-4000-8000-00000000f002"}

BOARD = (
    '(kicad_pcb (version 20260901) (generator "pcbnew") (generator_version "10.99") (general (thickness 1.6)) '
    '(paper "A4") (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user) (5 "F.SilkS" user) (7 "B.SilkS" user) '
    '(1 "F.Mask" user) (3 "B.Mask" user)) (setup (pad_to_mask_clearance 0)) '
    f'(gr_rect (start 0 0) (end 40 30) (stroke (width 0.1) (type default)) (fill no) (layer "Edge.Cuts") (uuid "{_uuid()}")) '
    + _header("J1", 5, 15, ["KEEP", "VCC"]) + _header("J2", 35, 15, ["KEEP", "OLD"])
    + _resistor("R1", 12, 25, "SIG", "VCC") + _resistor("R2", 28, 25, "SIG", "OLD")
    + _resistor("R3", 32, 5, "WALL", "N3") + _resistor("R4", 8, 5, "WALL", "N4")
    # TEE's three pads: the third joins the first two's track where it passes, a T.
    + _resistor("R5", 12, 9.5, "TEE", "N5") + _resistor("R6", 20, 9.5, "TEE", "N6")
    + _resistor("R7", 14.375, 17.5, "N7", "TEE")
    # K1 carries its own keep-out, off its centre: placed, turned and flipped in the edit.
    + f'(footprint "Keepout" (layer "F.Cu") (uuid "{_uuid()}") (transform (translate 10 25) (rotate 0) (scale 1 1)) '
    + _reference("K1") + _keepout([(-1, -6), (1, -6), (1, 2), (-1, 2)], '"F.Cu"') + ")"
    # R3 inside a closed ring of keep-out on both layers.
    + _keepout([(29.5, 2.5), (34.5, 2.5), (34.5, 7.5), (29.5, 7.5), (29.5, 6.7), (33.7, 6.7), (33.7, 3.3), (30.3, 3.3),
                (30.3, 6.7), (29.5, 6.7)], '"F.Cu" "B.Cu"')
    + f'(segment (start 20 20) (end 20 28) (width 0.25) (layer "F.Cu") (net "OLD") (uuid "{OLD["track"]}")) '
    + f'(via (at 20 20) (size 0.8) (drill 0.4) (layers "F.Cu" "B.Cu") (net "OLD") (uuid "{OLD["via"]}")) '
    + ")\n"
)

# The agent's script: K1 moved and turned keeping its keep-out's outline (KiPy would move it twice), flipped by
# KiCad, then the plan routed; the outcome as JSON.
SCRIPT = textwrap.dedent("""
    import json, sys
    from copy import deepcopy
    from cad import kicad_pcb
    from cad.kicad import route
    from kicode.board_types import Zone
    from kicode.geometry import Angle, Vector2

    with kicad_pcb.edit(sys.argv[1]) as b:
        k1 = next(fp for fp in b.get_footprints() if fp.reference_field.text.value == "K1")
        zones = [item for item in k1.definition.items if isinstance(item, Zone)]
        outlines = [deepcopy(zone.proto.outline) for zone in zones]
        k1.position = Vector2.from_xy_mm(20, 15)
        k1.orientation = Angle.from_degrees(90)
        for zone, outline in zip(zones, outlines):
            zone.proto.outline.CopyFrom(outline)
        b.update_items([k1])
        b.flip_items([k1])
        routed = route(b, [
            {"net": "KEEP", "layers": ["B.Cu"]},
            {"net": "VCC", "layers": ["F.Cu"]},
            {"net": "SIG", "layers": ["F.Cu", "B.Cu"], "vias": 2},
            {"net": "WALL", "layers": ["F.Cu", "B.Cu"]},
            {"net": "TEE", "layers": ["F.Cu"]},
        ])
    print(json.dumps({"ok": routed.ok, "lines": routed.human_lines(),
                      "routed": {c.net: c.routed for c in routed.connections},
                      "reasons": {c.net: c.reason for c in routed.connections if not c.routed}}))
""")


def _copper(board: Path) -> tuple[list, list]:
    from cad import kicad_pcb

    read = kicad_pcb.read(board)
    return (sorted((t.net, t.layer, t.width, t.points) for t in read.tracks),
            sorted((v.net, v.at, v.diameter, v.drill) for v in read.vias))


class Route(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="kicad-route-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def project(self, name: str) -> Path:
        folder = self.folder / name
        folder.mkdir()
        (folder / "route.kicad_pcb").write_text(BOARD, encoding="utf-8")
        (folder / "route.kicad_pro").write_text(json.dumps(PROJECT), encoding="utf-8")
        return folder / "route.kicad_pcb"

    def routed(self, board: Path) -> dict:
        done = kicode.run_python(self, SCRIPT, str(board), cwd=board.parent)
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_a_plan_is_routed_by_the_boards_rules_and_drc_finds_only_what_it_said(self) -> None:
        from cad import kicad_pcb

        board = self.project("a")
        outcome = self.routed(board)
        self.assertEqual({"KEEP": True, "VCC": True, "SIG": True, "WALL": False, "TEE": True}, outcome["routed"],
                         outcome["lines"])
        self.assertIn("R3.1 is walled in", outcome["reasons"]["WALL"])
        self.assertIn("NOT routed WALL: R3.1 to R4.1: R3.1 is walled in", "\n".join(outcome["lines"]))
        read = kicad_pcb.read(board)
        self.assertEqual({0.5}, {t.width for t in read.tracks if t.net == "VCC"}, "VCC at its netclass's width")
        self.assertEqual({"B.Cu"}, {t.layer for t in read.tracks if t.net == "KEEP"})
        old = [t for t in read.tracks if t.id == OLD["track"]]
        self.assertEqual([((20.0, 20.0), (20.0, 28.0))], [t.points for t in old], "the old track as it was")
        self.assertEqual([(20.0, 20.0)], [v.at for v in read.vias if v.id == OLD["via"]], "the old via as it was")
        keepout = next(zone for zone in read.rule_areas if zone.layer == "B.Cu")
        xs, ys = [p[0] for p in keepout.outline], [p[1] for p in keepout.outline]
        self.assertEqual((18.0, 26.0, 14.0, 16.0), (min(xs), max(xs), min(ys), max(ys)), "K1's keep-out, turned and flipped")

        found = kicode.call(self, "drc", board)["measurements"]["drc"]
        errors = sorted({f["type"] for f in found if f["severity"] == "error"})
        self.assertEqual(["unconnected_items"], errors, found)
        dangling = {item["description"].split("[")[1].split("]")[0] for f in found if f["type"].endswith("_dangling")
                    for item in f["items"]}
        self.assertEqual({"OLD"}, dangling, "no end the router left: OLD's own track and via join nothing")
        tee = [t for t in read.tracks if t.net == "TEE"]
        ends = [end for t in tee for end in (t.points[0], t.points[-1])]
        self.assertTrue(any(ends.count(end) == 3 for end in ends), f"a T where three TEE tracks end: {tee}")
        apart = {item["description"].split("[")[1].split("]")[0] for f in found if f["type"] == "unconnected_items"
                 for item in f["items"]}
        self.assertEqual({"WALL", "OLD"}, apart, "the connection said, and OLD's, which the plan leaves alone")

        # The keep-out is where the router read it: a track drawn through it there is DRC's error.
        control = self.project("control")
        crossing = (f'(segment (start 19 15) (end 25 15) (width 0.25) (layer "B.Cu") (net "KEEP") (uuid "{_uuid()}"))')
        text = board.read_text(encoding="utf-8")
        cut = text.rstrip().rfind(")")
        control.write_text(text[:cut] + crossing + "\n" + text[cut:], encoding="utf-8")
        found = kicode.call(self, "drc", control)["measurements"]["drc"]
        self.assertIn("items_not_allowed", {f["type"] for f in found})

        # The same script on the same board writes the same copper.
        again = self.project("b")
        self.assertEqual(outcome["routed"], self.routed(again)["routed"])
        self.assertEqual(_copper(board), _copper(again))


if __name__ == "__main__":
    unittest.main()
