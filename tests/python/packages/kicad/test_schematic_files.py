"""Real KiCad on the test schematics: ERC, the exports, and the nets the reader resolves held to KiCad's own;
and the libraries a project names by KiCad's own variables, read by ERC and its board's DRC.

The schematics are the test projects (``tests/python/support/kicad_schematic.py``), written fresh in a
temporary folder; ``cad.kicad_sch.erc`` and ``export`` run where the ``cad`` command runs them, in the
environment of ``cad[kicad]`` (``tests/python/support/kicode.py``): kicode's kicad-cli, headless, in private
homes.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import kicode
from tests.python.support.engine_daemon import isolate
from tests.python.support.kicad_schematic import at, write_bus_schematic, write_schematic, write_symbol_libraries


def kicad_nets(netlist: Path) -> dict[str, set[str]]:
    """The nets of a KiCad netlist, by their shown names: the pins on each."""
    from cad.engine.formats.kicad import sexpr
    from cad.engine.formats.kicad.naming import unescape_net_name

    tree = sexpr.parse(netlist.read_text(encoding="utf-8"))
    return {unescape_net_name(str(sexpr.value(net, "name"))): {f"{sexpr.value(node, 'ref')}.{sexpr.value(node, 'pin')}"
                                                                for node in sexpr.find_all(net, "node")}
            for net in sexpr.find_all(sexpr.find(tree, "nets"), "net")}


def export(case: unittest.TestCase, schematic: Path, to: str, out: Path) -> list[Path]:
    """``cad.kicad_sch.export`` in the environment of ``cad[kicad]``: the files it wrote."""
    done = kicode.call(case, "export", schematic, to, out, document_type="kicad_sch")
    return [Path(path) for path in done["written"]]


class SchematicFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        isolate(cls.addClassCleanup)
        cls.folder = tempfile.TemporaryDirectory(prefix="kicad-sch-files-")
        cls.addClassCleanup(cls.folder.cleanup)
        cls.divider = write_schematic(Path(cls.folder.name) / "divider")
        cls.busses = write_bus_schematic(Path(cls.folder.name) / "busses")

    def test_the_reader_resolves_the_nets_kicad_does(self) -> None:
        from cad.kicad_sch import read as read_schematic

        for root in (self.divider, self.busses):
            with self.subTest(schematic=root.name):
                [netlist] = export(self, root, "netlist", root.parent / "out")
                ours = {net.name: {f"{pin.ref}.{pin.number}" for pin in net.pins} for net in read_schematic(root).nets}
                self.assertEqual(ours, kicad_nets(netlist))

    def test_kicad_joins_a_pin_and_a_wires_end_on_a_wires_span_as_the_reader_does(self) -> None:
        """What ``pin_on_wire_span`` and ``wire_end_on_wire_span`` warn of: a wire across R1's pin 1, and a wire
        from the middle of the MID wire with no junction, each carrying a global label, which names the net KiCad
        joins them into."""
        from cad.kicad_sch import read as read_schematic

        def wire(start, end, label, angle):
            (x0, y0), (x1, y1) = at(*start), at(*end)
            return (f'(wire (pts (xy {x0:g} {y0:g}) (xy {x1:g} {y1:g})) (stroke (width 0) (type default)) '
                    f'(uuid "5c4e0000-0000-4000-8000-0000000000e{angle // 90}"))'
                    f' (global_label "{label}" (shape input) (at {x1:g} {y1:g} {angle}) (fields_autoplaced yes)'
                    f' (effects (font (size 1.27 1.27)) (justify left)) (uuid "5c4e0000-0000-4000-8000-0000000000f{angle // 90}"))')

        for name, extra, net, pins in (("across", wire((86, 44), (74, 44), "X", 180), "X", {"R1.1"}),
                                       ("tee", wire((90, 51), (90, 56), "Y", 270), "Y", {"R1.2", "R2.1", "C1.1"})):
            with self.subTest(name), tempfile.TemporaryDirectory(prefix=f"kicad-sch-{name}-") as folder:
                root = write_schematic(Path(folder))
                text = root.read_text(encoding="utf-8")
                root.write_text(text.replace("  (sheet_instances", f"  {extra}\n  (sheet_instances", 1), encoding="utf-8")
                [netlist] = export(self, root, "netlist", Path(folder) / "out")
                theirs = kicad_nets(netlist)
                self.assertEqual(pins, theirs[net], "KiCad joins it")
                self.assertEqual({net.name: {f"{pin.ref}.{pin.number}" for pin in net.pins}
                                  for net in read_schematic(root).nets}, theirs)

    def test_erc_finds_what_kicad_finds_where_it_is(self) -> None:
        before = sorted(path.name for path in self.divider.parent.iterdir())
        # Any sheet: the hierarchy from its root.
        result = kicode.call(self, "erc", self.divider.with_name("load.kicad_sch"), document_type="kicad_sch")
        self.assertFalse(result["ok"])
        errors = [finding for finding in result["findings"] if finding["severity"] == "error"]
        # Neither power net has a source (no PWR_FLAG): KiCad flags +5V's and the first GND's pins.
        self.assertTrue(errors and all(finding["code"] == "power_pin_not_driven" for finding in errors),
                        result["findings"])
        x, y = at(80, 40)
        self.assertIn(f"/ ({x:g}, {y:g}) mm", [finding["location"] for finding in errors])
        self.assertEqual(sorted(path.name for path in self.divider.parent.iterdir()), before)  # nothing left beside it

    def test_exports_write_each_kind(self) -> None:
        out = Path(self.folder.name) / "exports"
        [pdf] = export(self, self.divider, "pdf", out)
        self.assertEqual(pdf.read_bytes()[:5], b"%PDF-")
        self.assertEqual(len(export(self, self.divider, "svg", out)), 2)  # a page per sheet
        [bom] = export(self, self.divider, "bom", out)
        rows = bom.read_text(encoding="utf-8").splitlines()
        self.assertEqual(rows[0], '"Refs","Value","Footprint","MPN","Qty","DNP"')
        self.assertTrue(any(row.startswith('"R1","10k"') and "RC0603FR-0710KL" in row for row in rows), rows)


# A footprint as KiCad's library holds it (``header``: its file's version) and as a board places it (``at``), the
# two copies equal; ``divider``'s R1 and R2 name it ``Resistor_SMD:R_0603_1608Metric``, C1 ``Capacitor_SMD:...``.
_FOOTPRINT = '''(footprint "{name}"{header} (layer "F.Cu"){at}
  (property "Reference" "R1" (at 0 -2) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "10k" (at 0 2) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (attr smd)
  (pad "1" smd rect (at -0.8 0) (size 0.9 1) (layers "F.Cu" "F.Mask"))
  (pad "2" smd rect (at 0.8 0) (size 0.9 1) (layers "F.Cu" "F.Mask")))'''
_BOARD = '''(kicad_pcb (version 20241229) (generator "pcbnew")
 (general (thickness 1.6)) (paper "A4")
 (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "B.SilkS" user "b.silkscreen") (37 "F.SilkS" user "f.silkscreen")
 (38 "B.Mask" user) (39 "F.Mask" user) (44 "Edge.Cuts" user) (49 "F.Fab" user))
 (setup (pad_to_mask_clearance 0))
 (gr_rect (start 0 0) (end 40 30) (stroke (width 0.05) (type default)) (fill none) (layer "Edge.Cuts"))
 {footprint}
)
'''
# What KiCad says of a library row it cannot read or of what it holds: ERC's and DRC's library checks, and the
# note of the ones not made.
_LIBRARY_CHECKS = ("lib_symbol_issues", "lib_symbol_mismatch", "footprint_link_issues", "libraries_not_checked",
                   "lib_footprint_issues", "lib_footprint_mismatch")


class KicadsOwnLibraries(unittest.TestCase):
    def test_rows_naming_kicads_libraries_read_the_installation_of_the_3d_library_the_view_reads(self) -> None:
        """A project's library tables name KiCad's own libraries by its variables, as KiCad's own tables do
        (``${KICAD10_SYMBOL_DIR}/Device.kicad_sym``; an older major's and KiCad 5's spellings too): ERC and DRC
        read them in the KiCad installation whose 3D library the board view reads -- here a test-owned one,
        which ``CAD_KICAD_3DMODELS`` names -- and never where the caller's own variables point."""
        with tempfile.TemporaryDirectory(prefix="kicad-own-libraries-") as folder:
            root = Path(folder)
            kicad = root / "kicad"  # stands for KiCad's installation: 3dmodels, symbols, footprints side by side
            (kicad / "3dmodels").mkdir(parents=True)
            self.assertEqual(sorted(write_symbol_libraries(kicad / "symbols")), ["Connector", "Device", "power"])
            for library, name in (("Resistor_SMD", "R_0603_1608Metric"), ("Capacitor_SMD", "C_0603_1608Metric")):
                (kicad / "footprints" / f"{library}.pretty").mkdir(parents=True)
                (kicad / "footprints" / f"{library}.pretty" / f"{name}.kicad_mod").write_text(
                    _FOOTPRINT.format(name=name, header=' (version 20241229) (generator "pcbnew")', at="") + "\n",
                    encoding="utf-8")
            sheet = write_schematic(root / "design")
            rows = {"sym": [("Device", "${KICAD10_SYMBOL_DIR}/Device.kicad_sym"),
                            ("Connector", "${KICAD9_SYMBOL_DIR}/Connector.kicad_sym"),
                            ("power", "${KICAD_SYMBOL_DIR}/power.kicad_sym")],
                    "fp": [("Resistor_SMD", "${KICAD10_FOOTPRINT_DIR}/Resistor_SMD.pretty"),
                           ("Capacitor_SMD", "${KISYSMOD}/Capacitor_SMD.pretty")]}
            for table, libraries in rows.items():
                (sheet.parent / f"{table}-lib-table").write_text(f"({table}_lib_table\n  (version 7)\n" + "".join(
                    f'  (lib (name "{name}")(type "KiCad")(uri "{uri}")(options "")(descr ""))\n' for name, uri in libraries)
                    + ")\n", encoding="utf-8")
            board = sheet.with_suffix(".kicad_pcb")
            board.write_text(_BOARD.format(footprint=_FOOTPRINT.format(
                name="Resistor_SMD:R_0603_1608Metric", header="", at=" (at 20 15)")), encoding="utf-8")
            elsewhere = str(root / "elsewhere")  # the caller's own, which a run never reads
            with mock.patch.dict(os.environ, {"CAD_KICAD_3DMODELS": str(kicad / "3dmodels"),
                                              "KICAD10_SYMBOL_DIR": elsewhere, "KICAD10_FOOTPRINT_DIR": elsewhere}):
                erc = kicode.call(self, "erc", sheet, document_type="kicad_sch")
                drc = kicode.call(self, "drc", board)
            found = [(finding["code"], finding["message"]) for finding in erc["findings"] + drc["findings"]
                     if finding["code"] in _LIBRARY_CHECKS]
            self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
