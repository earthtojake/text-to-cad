"""A board built through ``@pcb`` on a real KiCad, then checked by KiCad's DRC.

The one door, ``python <board>.py``, on a script this test writes (a header, a
resistor and an LED on a 40 x 30 mm board, with its ``fp-lib-table`` naming
the three stock libraries), in its own directory: the files KiCad writes, the
report line with KiCad's DRC counts, the ``CADGEN_BUILD`` record in the board and
its project, a rebuild passing the record (``--no-drc``), a hand-edited board
refused until ``--force``, then ``cadgen pcb drc`` clean. A missing footprint is
the other contract: the script fails, names the library rows, and writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path
from tests.python.support.tmp_root import temporary_directory

SCRIPT = """\
from cadgen import pcb
from cadgen.kipy.board_types import BoardLayer, BoardPolygon, Net, Track, Via, Zone
from cadgen.kipy.geometry import Angle, PolygonWithHoles, PolyLineNode, Vector2
from cadgen.kipy.util.units import from_mm

PARTS = {
    "J1": ("Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical", (-15, 0), 0, {"1": "VBUS", "2": "GND"}),
    "R1": ("Resistor_SMD:R_0603_1608Metric", (0, 5), -90, {"1": "VBUS", "2": "LED"}),
    "D1": ("%(led)s", (8, -5), 0, {"1": "GND", "2": "LED"}),
}
TRACKS = {
    "VBUS": (0.3, [(-15, 0), (0, 0), (0, 4.2125)]),
    "LED": (0.25, [(0, 5.7875), (0, 8), (12, 8), (12, -5), (8.7875, -5)]),
    "GND": (0.25, [(7.2125, -5), (7.2125, -8)]),
}


def polygon(points):
    shape = PolygonWithHoles()
    for x, y in points:
        shape.outline.append(PolyLineNode.from_xy(from_mm(x), from_mm(y)))
    shape.outline.closed = True
    return shape


@pcb
def blinky(board):
    placed = []
    for reference, (footprint, (x, y), rotation, nets) in PARTS.items():
        part = board.place_footprint_from_library(footprint, Vector2.from_xy_mm(x, y), Angle.from_degrees(rotation))
        part.reference_field.text.value = reference
        for pad in part.definition.pads:
            pad.net = Net(name=nets[pad.number])
        placed.append(part)
    board.update_items(placed)
    edge = BoardPolygon()
    edge.polygons.append(polygon(((-20, -15), (20, -15), (20, 15), (-20, 15))))
    edge.layer = BoardLayer.BL_Edge_Cuts
    edge.attributes.stroke.width = from_mm(0.1)
    items = [edge]
    for net, (width, points) in TRACKS.items():
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            track = Track()
            track.start, track.end = Vector2.from_xy_mm(x1, y1), Vector2.from_xy_mm(x2, y2)
            track.width, track.layer, track.net = from_mm(width), BoardLayer.BL_F_Cu, Net(name=net)
            items.append(track)
    via = Via()
    via.position, via.net = Vector2.from_xy_mm(7.2125, -8), Net(name="GND")
    via.diameter, via.drill_diameter = from_mm(0.6), from_mm(0.3)
    items.append(via)
    pour = Zone()
    pour.outline, pour.layers, pour.net, pour.name = polygon(((-19.5, -14.5), (19.5, -14.5), (19.5, 14.5), (-19.5, 14.5))), [BoardLayer.BL_B_Cu], Net(name="GND"), "GND pour"
    items.append(pour)
    board.create_items(items)


if __name__ == "__main__":
    blinky()
"""

TABLE = """\
(fp_lib_table
  (version 7)
  (lib (name "Connector_PinHeader_2.54mm") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Connector_PinHeader_2.54mm.pretty") (options "") (descr ""))
  (lib (name "Resistor_SMD") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Resistor_SMD.pretty") (options "") (descr ""))
  (lib (name "LED_SMD") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/LED_SMD.pretty") (options "") (descr ""))
)
"""


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(repo_path("packages/cadgen/src")), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=600)


def _api_servers() -> list[str]:
    """Every live ``kicad-cli api-server`` on this (Linux) machine, by its command line."""
    found = []
    for entry in Path("/proc").glob("[0-9]*/cmdline") if Path("/proc").is_dir() else ():
        try:
            words = [word for word in entry.read_bytes().split(b"\0") if word]
        except OSError:
            continue
        if len(words) > 1 and words[0].endswith(b"kicad-cli") and words[1] == b"api-server":
            found.append(b" ".join(words).decode(errors="replace"))
    return found


class HeadlessBuild(unittest.TestCase):
    def _project(self, prefix: str, led: str) -> Path:
        tempdir = temporary_directory(prefix=prefix)
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        (root / "blinky.py").write_text(SCRIPT % {"led": led}, encoding="utf-8")
        (root / "fp-lib-table").write_text(TABLE, encoding="utf-8")
        return root

    def test_the_script_writes_kicads_files_and_the_board_passes_drc(self) -> None:
        root = self._project("pcb-smoke-", "LED_SMD:LED_0603_1608Metric")
        servers = _api_servers()
        built = _run([sys.executable, "blinky.py"], root)
        self.assertEqual(0, built.returncode, built.stderr)
        # The server a build starts dies with it: Ubuntu's kicad-cli-nightly is a shell wrapper
        # that would keep it alive past the signal that stops it (cadgen.kicad.install.unwrap).
        self.assertEqual(servers, _api_servers(), "a build left its API server running")
        self.assertRegex(built.stdout, r"^blinky\.kicad_pcb: 3 parts, 7 tracks, 1 via, 1 zone, 0 unconnected, DRC 0 errors 0 warnings, \d+\.\d s\n$")
        for suffix in (".kicad_pcb", ".kicad_pro", ".kicad_prl"):
            self.assertTrue((root / f"blinky{suffix}").is_file(), suffix)
        board = (root / "blinky.kicad_pcb").read_text(encoding="utf-8")
        self.assertIn('(generator "pcbnew")', board)
        self.assertEqual(3, len(re.findall(r'\(footprint "', board)))
        # The record KiCad saved into the board and its project, verifying the board's bytes.
        [record] = re.findall(r'\(property "CADGEN_BUILD" "([0-9a-f]{64})"\)', board)
        project = json.loads((root / "blinky.kicad_pro").read_text(encoding="utf-8"))
        self.assertEqual({"CADGEN_BUILD": record}, project["text_variables"])
        self.assertEqual(record, hashlib.sha256(board.replace(f'\t(property "CADGEN_BUILD" "{record}")\n', "").encode("utf-8")).hexdigest())

        rebuilt = _run([sys.executable, "blinky.py", "--no-drc"], root)
        self.assertEqual(0, rebuilt.returncode, rebuilt.stderr)
        self.assertRegex(rebuilt.stdout, r"^blinky\.kicad_pcb: 3 parts, 7 tracks, 1 via, 1 zone, 0 unconnected, \d+\.\d s\n$")

        with (root / "blinky.kicad_pcb").open("a", encoding="utf-8") as handle:
            handle.write("\n")
        edited = (root / "blinky.kicad_pcb").read_bytes()
        refused = _run([sys.executable, "blinky.py"], root)
        self.assertEqual(1, refused.returncode)
        self.assertIn("blinky.kicad_pcb was last saved by something other than this script", refused.stderr)
        self.assertIn("pass --force to overwrite it", refused.stderr)
        self.assertEqual(edited, (root / "blinky.kicad_pcb").read_bytes())
        forced = _run([sys.executable, "blinky.py", "--force", "--no-drc"], root)
        self.assertEqual(0, forced.returncode, forced.stderr)
        self.assertNotEqual(edited, (root / "blinky.kicad_pcb").read_bytes())

        checked = _run([sys.executable, "-m", "cadgen.cli", "pcb", "drc", "blinky.kicad_pcb", "--json"], root)
        self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
        report = json.loads(checked.stdout.splitlines()[-1])
        self.assertEqual(([], True), (report["issues"], report["ok"]))
        self.assertIn("DRC clean", report["summary"])

    def test_a_footprint_no_declared_library_has_fails_the_script_and_writes_nothing(self) -> None:
        root = self._project("pcb-missing-", "LED_SMD:LED_0603_NOT_A_FOOTPRINT")
        built = _run([sys.executable, "blinky.py"], root)
        self.assertEqual(1, built.returncode)
        for text in ("footprint 'LED_SMD:LED_0603_NOT_A_FOOTPRINT' not found", "fp-lib-table", "LED_SMD (LLS_LOADED)"):
            self.assertIn(text, built.stderr)
        self.assertEqual({"blinky.py", "fp-lib-table"}, {path.name for path in root.iterdir()})


if __name__ == "__main__":
    unittest.main()
