"""Harness documents through a real WireViz: the diagram the viewer draws, the BOM, what WireViz refuses.

Two boards from the tiny test library (no KiCad) and a harness between them,
in a fresh folder: ``python cable.py`` writes its document and, with ``bom=True``,
WireViz's bill of materials, the same bytes every time and the same bytes the
``cadgen harness bom`` door writes; the plot payload is WireViz's own SVG; every
field cadgen writes is one WireViz reads; a document WireViz refuses comes
back with WireViz's reason. Needs WireViz and Graphviz (scripts/test/test-harness.sh).
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tests.python.support.harness_boards import write_board
from tests.python.support.kicad_library import write_test_library
from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

CADGEN_SRC = add_repo_path("packages/cadgen/src")

CABLE = textwrap.dedent(
    '''
    from cadgen import harness

    from controller import controller
    from driver import driver


    @harness(bom=True)
    def cable():
        h = harness.Harness(title="Controller to driver")
        terminal = {"type": "Crimp terminal", "mpn": "SPH-002T-P0.5S", "qty_multiplier": "populated"}
        a = h.connector(controller(), "J1", name="CTRL_J1", type="JST PH 2.0 mm housing", mpn="PHR-2",
                        additional_components=[terminal])
        b = h.connector(driver(), "J1", name="DRV_J1", type="JST PH 2.0 mm housing", mpn="PHR-2",
                        additional_components=[terminal])
        w = h.cable("W1", colors=["RD", "BK"], gauge="24 AWG", length=300)
        h.connect([a["VBUS"], a["GND"]], w.wires, [b["VBUS"], b["GND"]])
        return h


    if __name__ == "__main__":
        cable()
    '''
)

# Not written by cadgen: WireViz's own syntax, as a person would write it.
HAND_WRITTEN = textwrap.dedent(
    """
    connectors:
      X1:
        type: D-Sub
        subtype: female
        pinlabels: [DCD, RX, TX, DTR, GND]
      X2:
        type: Molex KK 254
        pinlabels: [GND, RX, TX]
    cables:
      W1:
        gauge: 0.25 mm2
        length: 0.2
        color_code: DIN
        wirecount: 3
        shield: true
    connections:
      -
        - X1: [5, 2, 3]
        - W1: [1, 2, 3]
        - X2: [1, 3, 2]
    """
)


def _rows(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8"))))


class HarnessWirevizTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="harness-wireviz-")
        self.folder = Path(self._tmp.name)
        (self.folder / "library").mkdir()
        library = str(write_test_library(self.folder / "library"))
        for name, first, second in (("controller", "VBUS", "GND"), ("driver", "GND", "VBUS")):
            write_board(self.folder, name, first, second, library=library)
        (self.folder / "cable.py").write_text(CABLE, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cadgen(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["CADGEN_DAEMON"] = "0"
        env["PYTHONPATH"] = os.pathsep.join([str(CADGEN_SRC), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        return subprocess.run([sys.executable, *args], cwd=self.folder, env=env, capture_output=True, text=True, timeout=300)

    def test_a_harness_writes_its_bom_the_same_every_time_and_as_the_door_does(self) -> None:
        built = self.run_cadgen("cable.py")
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertIn("wrote BOM: cable.bom.csv", built.stderr)
        bom = (self.folder / "cable.bom.csv").read_bytes()
        rows = _rows(bom)
        self.assertEqual(rows[0], ["Id", "Description", "Qty", "Unit", "Designators", "MPN"])
        described = {row[1]: row for row in rows[1:]}
        self.assertEqual(described["Cable, 2 x 24 AWG"][2:4], ["0.3", "m"])
        self.assertEqual(described["Crimp terminal"][2], "4")  # one per populated pin, both housings
        self.assertEqual(described["Connector, JST PH 2.0 mm housing, 2 pins"][2], "2")
        document = (self.folder / "cable.harness.yml").read_bytes()
        forced = self.run_cadgen("cable.py", "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        self.assertEqual((self.folder / "cable.bom.csv").read_bytes(), bom)
        self.assertEqual((self.folder / "cable.harness.yml").read_bytes(), document)
        door = self.run_cadgen("-m", "cadgen.cli", "harness", "bom", "cable.harness.yml", "door.bom.csv")
        self.assertEqual(door.returncode, 0, door.stderr)
        self.assertEqual((self.folder / "door.bom.csv").read_bytes(), bom)

    def test_the_viewer_draws_wirevizs_diagram_once(self) -> None:
        from cadgen.viewer.plots import plot_payload_response

        self.assertEqual(self.run_cadgen("cable.py").returncode, 0)
        status, body = plot_payload_response(str(self.folder), "cable.harness.yml")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual((payload["schemaVersion"], payload["kind"], payload["unrouted"]), (1, "harness", None))
        [sheet] = payload["sheets"]
        self.assertEqual((sheet["name"], sheet["background"]), ("cable", "#ffffff"))
        self.assertIn("<svg", sheet["svg"])
        for text in ("CTRL_J1", "DRV_J1", "W1", "24 AWG", "VBUS"):
            self.assertIn(text, sheet["svg"])
        points = re.search(r'<svg\b[^>]*?\bwidth="([\d.]+)pt"[^>]*?\bheight="([\d.]+)pt"', sheet["svg"], re.DOTALL)
        self.assertAlmostEqual(sheet["width"], float(points.group(1)) * 25.4 / 72, places=3)  # millimetres
        self.assertAlmostEqual(sheet["height"], float(points.group(2)) * 25.4 / 72, places=3)
        self.assertEqual(plot_payload_response(str(self.folder), "cable.harness.yml")[1], body)

    def test_every_field_cadgen_writes_is_one_wireviz_reads(self) -> None:
        from cadgen import harness
        from cadgen.wireviz.bom import harness_bom
        from cadgen.wireviz.document import harness_document
        from cadgen.wireviz.plot import build_plot

        h = harness.Harness(title='Motor "A" lead')
        plug = h.connector(
            "NO", pinlabels=["A+", "A-", "B+", "B-"], type="Molex Micro-Fit 3.0", subtype="female", color="BK",
            pincolors=["RD", "BU", "GN", "BK"], hide_disconnected_pins=True, notes='keyed,\n"tab" up',
            pn="P-1", manufacturer="Molex", mpn="43025-0400", supplier="Digi-Key", spn="WM1785-ND",
            additional_components=[{"type": "Crimp terminal", "mpn": "43030-0007", "qty_multiplier": "populated"}],
        )
        lead = h.connector("M1", pins=["A1", "B1"], type="Stepper lead")
        ferrule = h.connector("F1", pincount=1, style="simple", type="Ferrule")
        shielded = h.cable(
            "W1", color_code="DIN", wirecount=3, gauge=0.5, length=250, shield=True, type="LiYCY",
            wirelabels=["A", "B", "C"], color="GY", notes="drain at the plug only",
            additional_components=[{"type": "Heat shrink", "qty": 0.05, "unit": "m"}],
        )
        loose = h.cable("W2", category="bundle", colors=["RD", "WHGN"], gauge="20 AWG", length=1000)
        h.connect([plug[1], plug[2]], [shielded[1], shielded[2]], [lead["A1"], lead["B1"]])
        h.connect(plug[3], shielded[3], ferrule[1])
        h.connect(plug[4], shielded["s"])
        tail = h.connector("X9", pincount=2, type="Screw terminal")
        h.connect(loose.wires, tail.pins)
        document = self.folder / "every.harness.yml"
        document.write_text(harness_document(h), encoding="utf-8")
        payload = build_plot(document)
        self.assertIn("LiYCY", payload["sheets"][0]["svg"])
        described = {row[1] for row in _rows(harness_bom(document.read_bytes()))[1:]}
        self.assertIn("Wire, 20 AWG, RD", described)  # a bundle lists each wire by gauge and colour
        self.assertIn("Wire, 20 AWG, WHGN", described)
        self.assertIn("Heat shrink", described)

    def test_wireviz_draws_a_hand_written_document_and_names_what_it_refuses(self) -> None:
        from cadgen.kicad.plot import PlotError
        from cadgen.wireviz.bom import harness_bom
        from cadgen.wireviz.plot import build_plot

        document = self.folder / "serial.harness.yml"
        document.write_text(HAND_WRITTEN, encoding="utf-8")
        self.assertEqual(build_plot(document)["sheets"][0]["name"], "serial")
        self.assertIn("Cable, 3 x 0.25 mm² shielded", {row[1] for row in _rows(harness_bom(document.read_bytes()))})
        document.write_text(HAND_WRITTEN.replace("- X2: [1, 3, 2]", "- X2: [1, 3, 9]"), encoding="utf-8")
        with self.assertRaisesRegex(PlotError, "WireViz could not draw serial.harness.yml: X2:9 not found"):
            build_plot(document)


if __name__ == "__main__":
    unittest.main()
