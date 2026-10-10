"""A schematic's index held to KiCad 10: its netlist, and its plot of each sheet.

KiCad's netlist is the truth about what connects. Pins placed by the index at every angle
and mirror carry labels KiCad must find on them; the shared fixtures' nets, sheets and
references are KiCad's (the cadgen suite reads the same fixtures without KiCad); and the
index is drawn in the frame of KiCad's SVG of the sheet. Needs KiCad 10.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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
from cadgen.kicad.install import find_kicad  # noqa: E402
from cadgen.kicad.plot import build_plot  # noqa: E402
from cadgen.kicad.schematic_index import read_index, read_schematic  # noqa: E402


def setUpModule() -> None:
    find_kicad()  # fail, never skip: KicadMissingError says how to install it


class SchematicIndexKicadTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_every_angle_and_mirror_places_pins_where_kicad_connects_them(self) -> None:
        # The same lopsided symbol at each angle and mirror; then a stub and a global label on
        # each pin where the index says the pin is. KiCad's netlist must find every label on its
        # own pin: a wrong turn or mirror lands a label on nothing, or on another pin.
        placements = [(rotation, mirror) for rotation in (0, 90, 180, 270) for mirror in (None, "x", "y")]

        def sheet(pins) -> str:
            text = SchematicText("turns", "turns", paper="A3")
            for number, (rotation, mirror) in enumerate(placements, start=1):
                at = (38.1 + 76.2 * ((number - 1) % 4), 50.8 + 76.2 * ((number - 1) // 4))
                text.symbol("Test:ODD", at, f"U{number}", rotation=rotation, mirror=mirror)
            for pin in pins:
                out = (pin.at[0] - pin.end[0], pin.at[1] - pin.end[1])
                reach = (out[0] ** 2 + out[1] ** 2) ** 0.5
                stub = (round(pin.at[0] + 2.54 * out[0] / reach, 4), round(pin.at[1] + 2.54 * out[1] / reach, 4))
                text.wire(pin.at, stub)
                text.label(f"{pin.part}_{pin.number}", stub, "global_label")
            return text.text()

        path = self.folder / "turns.kicad_sch"
        path.write_text(sheet([]), encoding="utf-8")
        placed = read_index(path)
        path.write_text(sheet(placed.pins), encoding="utf-8")
        view = read_schematic(path)
        pins = [pin for part in view.parts for pin in part.pins]
        self.assertEqual(len(pins), 48)
        self.assertEqual({pin.selector: pin.net for pin in pins}, {pin.selector: f"{pin.part}_{pin.number}" for pin in pins})
        self.assertEqual([(unit.rotation, unit.mirror) for part in view.parts for unit in part.units][:3], placements[:3])
        # Each pin ends on its body's edge, which the unit's outline is.
        for part in view.parts:
            (left, top), _, (right, bottom), _ = part.units[0].outline
            for pin in part.pins:
                x, y = pin.end
                on_edge = (round(x, 4) in (round(left, 4), round(right, 4)) and top <= y <= bottom) or (
                    round(y, 4) in (round(top, 4), round(bottom, 4)) and left <= x <= right
                )
                self.assertTrue(on_edge, (pin, part.units[0]))

    def test_what_touches_what_and_where_it_is_drawn_are_kicads(self) -> None:
        path = self.folder / "joins.kicad_sch"
        write_connections(path)
        payload = build_plot(path)
        index = payload["schematic"]
        nets = {f"{pin['part']}.{pin['number']}": pin["net"] for pin in index["pins"]}
        # The netlist the cadgen suite reads in KiCad's place is KiCad's.
        for net in sexpr.find_all(sexpr.find(sexpr.parse(CONNECTIONS_NETLIST), "nets"), "net"):
            for node in sexpr.find_all(net, "node"):
                self.assertEqual(nets[f"{sexpr.value(node, 'ref')}.{sexpr.value(node, 'pin')}"], sexpr.value(net, "name"))
        # Every wire is on the net of each pin at its ends: the index joins what KiCad joins.
        pins_at = {tuple(pin["at"]): pin["net"] for pin in index["pins"]}
        touching = [(wire["net"], pins_at[tuple(point)]) for wire in index["wires"] for point in wire["points"] if tuple(point) in pins_at]
        self.assertEqual(len(touching), 6)  # R1 to R6 each start a wire; R7 sits on one's middle
        self.assertTrue(all(wire == pin for wire, pin in touching), touching)
        # The sheet frame is the SVG's: KiCad draws the junction where the index has it.
        [junction] = index["junctions"]
        self.assertEqual(junction["net"], "TB")
        self.assertIn(f'<circle cx="{junction["at"][0]:.4f}" cy="{junction["at"][1]:.4f}"', payload["sheets"][0]["svg"])

    def test_a_hierarchy_reads_as_kicad_plots_and_nets_it(self) -> None:
        write_hierarchy(self.folder)
        project = {
            "meta": {"filename": "hier.kicad_pro", "version": 3},
            "net_settings": {
                "classes": [{"name": "Default", "priority": 2147483647}, {"name": "Power", "priority": 0}],
                "meta": {"version": 5}, "netclass_assignments": None,
                "netclass_patterns": [{"netclass": "Power", "pattern": "GND"}],
            },
        }
        (self.folder / "hier.kicad_pro").write_text(json.dumps(project), encoding="utf-8")
        payload = build_plot(self.folder / "hier.kicad_sch")
        index = payload["schematic"]
        self.assertEqual([sheet["name"] for sheet in payload["sheets"]], [name for name, _path, _file in HIERARCHY_SHEETS])
        self.assertEqual([(sheet["name"], sheet["path"], sheet["file"]) for sheet in index["sheets"]], HIERARCHY_SHEETS)
        on = {pin["net"]: [] for pin in index["pins"]}
        for pin in index["pins"]:
            on[pin["net"]].append(f"{pin['part']}.{pin['number']}")
        self.assertEqual(on, HIERARCHY_NETS)
        classes = {net["name"]: net["class"] for net in index["nets"]}
        self.assertEqual((classes["GND"], classes["RSIG"]), ("Power", "Default"))
        # A label no pin reaches names no net of KiCad's.
        self.assertEqual([label["net"] for label in index["labels"] if label["text"] == "FLOAT"], [None])


if __name__ == "__main__":
    unittest.main()
