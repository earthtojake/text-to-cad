"""A saved KiCad schematic through the commands: ``cad kicad_sch snapshot --sheet`` draws one sheet as it is
now, ``cad kicad_sch inspect`` says what it holds and what a reference names, and ``cad kicad_sch check``
without a kicad-cli to run says how to get one.

The schematic is the test project (``tests/python/support/kicad_schematic.py``), written fresh. ERC and the
exports with a real KiCad are the KiCad suite's (``tests/python/packages/kicad``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from tests.python.support.engine_daemon import isolate
from tests.python.support.kicad_schematic import write_schematic

CLI = [sys.executable, "-c", "from cad_server.cli import main; raise SystemExit(main())"]


def cad(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([*CLI, *args], env=env or dict(os.environ), capture_output=True, text=True, timeout=120)


class SchematicCommands(unittest.TestCase):
    def setUp(self) -> None:
        isolate(self.addCleanup)
        self._folder = tempfile.TemporaryDirectory(prefix="sch-commands-")
        self.addCleanup(self._folder.cleanup)
        self.root = Path(self._folder.name)
        self.schematic = write_schematic(self.root)

    def test_snapshot_draws_the_sheet_it_names_as_the_file_is_now(self) -> None:
        png = self.root / "load.png"
        done = cad("kicad_sch", "snapshot", str(self.schematic), str(png), "--sheet", "/Load/", "--width", "320",
                   "--height", "240", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        drawn = json.loads(done.stdout)
        self.assertEqual((drawn["sheet"], drawn["page"]), ("/Load/", "2"))
        with Image.open(png) as image:
            self.assertEqual(image.size, (320, 240))
        refused = cad("kicad_sch", "snapshot", str(self.schematic), str(png), "--sheet", "/Power/")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("has no sheet /Power/; its sheets are /, /Load/", refused.stderr)

    def test_inspect_says_what_it_holds_and_what_a_reference_names(self) -> None:
        done = cad("kicad_sch", "inspect", str(self.schematic.with_name("load.kicad_sch")), "#R1.2", "--json")
        self.assertEqual(done.returncode, 0, done.stderr)
        found = json.loads(done.stdout)
        self.assertEqual([sheet["path"] for sheet in found["sheets"]], ["/", "/Load/"])
        self.assertEqual(found["resolved"], {**found["resolved"], "kind": "pin", "ref": "R1", "net": "/MID"})
        other = cad("kicad_sch", "inspect", str(self.root / "board.kicad_pcb"))
        self.assertEqual(other.returncode, 2)
        self.assertIn("is a kicad_pcb, not a kicad_sch: use cad kicad_pcb inspect", other.stderr)

    def test_erc_without_kicad_fails_saying_how_to_install_it(self) -> None:
        done = cad("kicad_sch", "check", str(self.schematic), "--json",
                   env={**os.environ, "CAD_KICAD_CLI": str(self.root / "no-kicad-cli")})
        self.assertEqual(done.returncode, 1, done.stderr)
        [issue] = json.loads(done.stdout)["findings"]
        self.assertEqual(issue["code"], "kicad_missing")
        self.assertIn("CAD_KICAD_CLI names", issue["message"])
        self.assertIn("cad[kicad]", issue["message"])


if __name__ == "__main__":
    unittest.main()
