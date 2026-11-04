"""A saved KiCad board through the commands: ``cad <type> snapshot`` and the CAD app's ``cad_snapshot`` draw the
file as it is now, and ``cad kicad_pcb drc`` on a machine without KiCad says how to get it.

The board is the test board (``tests/python/support/kicad_board.py``), written fresh: no corpus model.
DRC with a real KiCad is the KiCad suite's (``tests/python/packages/kicad``).
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
from tests.python.support.kicad_board import write_board

CLI = [sys.executable, "-c", "from cad_server.cli import main; raise SystemExit(main())"]


class NativeBoardCommands(unittest.TestCase):
    def setUp(self) -> None:
        isolate(self.addCleanup)
        self._folder = tempfile.TemporaryDirectory(prefix="pcb-commands-")
        self.addCleanup(self._folder.cleanup)
        self.root = Path(self._folder.name)
        self.board = write_board(self.root)

    def test_cli_and_mcp_snapshot_use_the_current_native_file(self) -> None:
        from cad_server.jobs import TERMINAL
        from cad_server.mcp.operations import Operations

        png = self.root / "cli.png"
        done = subprocess.run([*CLI, "kicad_pcb", "snapshot", str(self.board), str(png), "--width", "320", "--height", "240", "--json"],
                              env=dict(os.environ), capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        json.loads(done.stdout)
        with Image.open(png) as image:
            self.assertEqual(image.size, (320, 240))
        first = png.read_bytes()
        self.board.write_text(self.board.read_text(encoding="utf-8").replace(
            '(width 1) (layer "F.Cu") (net "VBUS")', '(width 3) (layer "F.Cu") (net "VBUS")'), encoding="utf-8")
        jobs = Operations()
        started = jobs.call("cad_snapshot", {"requestId": "native-board-snapshot-1", "source": str(self.board),
                                             "output": str(png), "width": 320, "height": 240})
        with jobs.changed:
            self.assertTrue(jobs.changed.wait_for(lambda: jobs.jobs[started["id"]]["state"] in TERMINAL, timeout=60))
        result = jobs.get(started["id"])
        self.assertEqual(result["state"], "succeeded", result)
        self.assertNotEqual(png.read_bytes(), first)

    def test_a_board_display_takes_board_modes_alone(self) -> None:
        done = subprocess.run([*CLI, "kicad_pcb", "snapshot", str(self.board), str(self.root / "x.png"), "--display", "wireframe"],
                              env=dict(os.environ), capture_output=True, text=True, timeout=120)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("a board's modes are board, copper, assembly, placement", done.stderr)

    def test_drc_without_kicad_fails_saying_how_to_install_it(self) -> None:
        env = {**os.environ, "CAD_KICAD_CLI": str(self.root / "no-kicad-cli")}
        done = subprocess.run([*CLI, "kicad_pcb", "drc", str(self.board), "--json"], env=env, capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(done.returncode, 1, done.stderr)
        result = json.loads(done.stdout)
        self.assertFalse(result["ok"])
        [issue] = result["findings"]
        self.assertEqual(issue["code"], "kicad_missing")
        self.assertIn("CAD_KICAD_CLI names", issue["message"])
        self.assertIn("cad[kicad]", issue["message"])


if __name__ == "__main__":
    unittest.main()
