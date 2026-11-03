"""Real KiCad on the test schematics: ERC, the exports, and the nets the reader resolves held to KiCad's own.

The schematics are the test projects (``tests/python/support/kicad_schematic.py``), written fresh in a
temporary folder; ``kicad-cli`` runs headless in private homes, found as ``cad kicad_sch check`` finds it.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.python.support.engine_daemon import isolate
from tests.python.support.kicad_schematic import at, write_bus_schematic, write_schematic


def kicad_nets(netlist: Path) -> dict[str, set[str]]:
    """The nets of a KiCad netlist, by their shown names: the pins on each."""
    from cad.engine.formats.kicad import sexpr
    from cad.engine.formats.kicad.naming import unescape_net_name

    tree = sexpr.parse(netlist.read_text(encoding="utf-8"))
    return {unescape_net_name(str(sexpr.value(net, "name"))): {f"{sexpr.value(node, 'ref')}.{sexpr.value(node, 'pin')}"
                                                                for node in sexpr.find_all(net, "node")}
            for net in sexpr.find_all(sexpr.find(tree, "nets"), "net")}


class SchematicFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        isolate(cls.addClassCleanup)
        cls.folder = tempfile.TemporaryDirectory(prefix="kicad-sch-files-")
        cls.addClassCleanup(cls.folder.cleanup)
        cls.divider = write_schematic(Path(cls.folder.name) / "divider")
        cls.busses = write_bus_schematic(Path(cls.folder.name) / "busses")

    def test_the_reader_resolves_the_nets_kicad_does(self) -> None:
        from cad.kicad_sch import read_schematic
        from cad_server.kicad.schematic import export

        for root in (self.divider, self.busses):
            with self.subTest(schematic=root.name):
                [netlist] = export(root, "netlist", root.parent / "out")
                ours = {net.name: {f"{pin.ref}.{pin.number}" for pin in net.pins} for net in read_schematic(root).nets}
                self.assertEqual(ours, kicad_nets(netlist))

    def test_erc_finds_what_kicad_finds_where_it_is(self) -> None:
        from cad_server.kicad.schematic import check

        before = sorted(path.name for path in self.divider.parent.iterdir())
        result = check(self.divider.with_name("load.kicad_sch"))  # any sheet: the hierarchy from its root
        self.assertFalse(result.ok)
        errors = [finding for finding in result.findings if finding.severity == "error"]
        # Neither power net has a source (no PWR_FLAG): KiCad flags +5V's and the first GND's pins.
        self.assertTrue(errors and all(finding.code == "power_pin_not_driven" for finding in errors), result.findings)
        x, y = at(80, 40)
        self.assertIn(f"/ ({x:g}, {y:g}) mm", [finding.location for finding in errors])
        self.assertEqual(sorted(path.name for path in self.divider.parent.iterdir()), before)  # nothing left beside it

    def test_exports_write_each_kind(self) -> None:
        from cad_server.kicad.schematic import export

        out = Path(self.folder.name) / "exports"
        [pdf] = export(self.divider, "pdf", out)
        self.assertEqual(pdf.read_bytes()[:5], b"%PDF-")
        self.assertEqual(len(export(self.divider, "svg", out)), 2)  # a page per sheet
        [bom] = export(self.divider, "bom", out)
        rows = bom.read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[0], '"Refs","Value","Footprint","MPN","Qty","DNP"')
        self.assertTrue(any(row.startswith('"R1","10k"') and "RC0603FR-0710KL" in row for row in rows), rows)


if __name__ == "__main__":
    unittest.main()
