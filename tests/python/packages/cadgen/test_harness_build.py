"""``python cable.py`` for a @harness, through the one source door, without WireViz or KiCad.

Two boards from the tiny test library and a harness between their connectors,
in a fresh folder. A harness build checks and writes its WireViz document,
then is current; a board's edit reaches it (the board script is its source);
a swapped connection fails and writes nothing; a board with a 3D export gives
a harness its netlist all the same, and a part, which has none, is refused at
the call. WireViz only draws and lists a document, so none of this needs it
(tests/python/packages/harness does).
"""

from __future__ import annotations

import json
import os
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


    @harness
    def cable():
        h = harness.Harness()
        a = h.connector(controller(), "J1", name="CTRL_J1", type="JST PH 2.0 mm housing")
        b = h.connector(driver(), "J1", name="DRV_J1", type="JST PH 2.0 mm housing")
        w = h.cable("W1", colors=["RD", "BK"], gauge="24 AWG", length=300)
        {connect}
        return h


    if __name__ == "__main__":
        cable()
    '''
)

BY_NET = 'h.connect([a["VBUS"], a["GND"]], w.wires, [b["VBUS"], b["GND"]])'
BY_NUMBER = "h.connect(a.pins, w.wires, b.pins)"


class HarnessBuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = generated_cad_directory(prefix="harness-build-")
        self.folder = Path(self._tmp.name)
        (self.folder / "library").mkdir()
        self.library = str(write_test_library(self.folder / "library"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def board(self, name: str, first: str, second: str, *, decorators: str = "@pcb", imports: str = "pcb") -> None:
        write_board(self.folder, name, first, second, library=self.library, decorators=decorators, imports=imports)

    def cable(self, connect: str = BY_NET) -> None:
        (self.folder / "cable.py").write_text(CABLE.format(connect=connect), encoding="utf-8")

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["CADGEN_DAEMON"] = "0"
        env["PYTHONPATH"] = os.pathsep.join([str(CADGEN_SRC), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        return subprocess.run(
            [sys.executable, "cable.py", *args], cwd=self.folder, env=env, capture_output=True, text=True, timeout=300
        )

    def test_a_harness_is_written_then_current_and_a_boards_edit_reaches_it(self) -> None:
        self.board("controller", "VBUS", "GND")
        self.board("driver", "GND", "VBUS")  # pinned out the other way round
        self.cable()
        built = self.run_script("--json")
        self.assertEqual(built.returncode, 0, built.stderr)
        result = json.loads(built.stdout.strip().splitlines()[-1])
        self.assertEqual((result["outcome"], result["kind"], result["tree"]), ("built", "harness", None))
        document = self.folder / "cable.harness.yml"
        self.assertEqual(Path(result["document"]), document.resolve())
        first = document.read_text(encoding="utf-8")
        self.assertIn('    pinlabels: ["GND", "VBUS"]\n', first)
        self.assertIn('    - "DRV_J1": [2, 1]\n', first)  # VBUS to VBUS, GND to GND
        again = self.run_script()
        self.assertEqual(again.stdout.strip().splitlines()[-1], "current cable.harness.yml")
        # The board script is the harness's source: re-pinning the driver's connector
        # makes the harness stale, and it follows the nets.
        self.board("driver", "VBUS", "GND")
        rebuilt = self.run_script()
        self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
        self.assertEqual(rebuilt.stdout.strip().splitlines()[-1], "built cable.harness.yml")
        self.assertIn('    - "DRV_J1": [1, 2]\n', document.read_text(encoding="utf-8"))

    def test_a_swapped_connection_fails_and_writes_nothing(self) -> None:
        self.board("controller", "VBUS", "GND")
        self.board("driver", "GND", "VBUS")
        self.cable(BY_NUMBER)
        failed = self.run_script()
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn(
            "W1 wire 1 (RD) runs from CTRL_J1 pin 1 (net VBUS on its board) to DRV_J1 pin 1 (net GND on its board)",
            failed.stderr,
        )
        self.assertIn("DRV_J1 carries VBUS on pin 2", failed.stderr)
        self.assertFalse((self.folder / "cable.harness.yml").exists())

    def test_a_board_with_a_3d_export_gives_its_netlist_and_a_part_is_refused(self) -> None:
        # The driver is a part to its enclosure (it has a 3D export); a harness still reads its netlist.
        self.board("controller", "VBUS", "GND")
        self.board("driver", "GND", "VBUS", decorators="@step\n@pcb", imports="pcb, step")
        self.cable()
        built = self.run_script()
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertIn('    - "DRV_J1": [2, 1]\n', (self.folder / "cable.harness.yml").read_text(encoding="utf-8"))
        # A part has no netlist to read.
        (self.folder / "driver.py").write_text(
            "from cadgen import build123d as bd\nfrom cadgen import step\n\n\n@step\ndef driver():\n    return bd.Box(1, 1, 1)\n",
            encoding="utf-8",
        )
        failed = self.run_script()
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("cable() is a @harness, which reads boards' netlists", failed.stderr)
        self.assertIn("driver() is a geometry model, which has none", failed.stderr)


if __name__ == "__main__":
    unittest.main()
