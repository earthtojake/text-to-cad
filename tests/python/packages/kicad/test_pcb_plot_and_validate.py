"""What the viewer and ``cadgen pcb validate`` read from a board, through a real KiCad 10.

The plot payload is KiCad's own SVG of the board (with a ratsnest when it is a
draft) and of each schematic sheet; ``pcb.validate`` is KiCad's ERC and DRC of
any project, and checking never writes into it. Needs KiCad 10.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests.python.packages.kicad.test_pcb_models import board_source
from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

CADGEN_SRC = add_repo_path("packages/cadgen/src")


class PcbPlotAndValidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = generated_cad_directory(prefix="pcb-plot-")
        cls.folder = Path(cls._tmp.name)
        env = dict(os.environ, CADGEN_DAEMON="0", PYTHONPATH=str(CADGEN_SRC))
        for name, routed in (("finished", True), ("draft", False)):
            (cls.folder / name).mkdir()
            (cls.folder / name / "blinky.py").write_text(board_source(route_led=routed), encoding="utf-8")
            built = subprocess.run([sys.executable, "blinky.py"], cwd=cls.folder / name, env=env, capture_output=True, text=True, timeout=600)
            if built.returncode != 0:
                raise AssertionError(built.stderr)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_a_board_plots_as_one_sheet_and_a_draft_carries_its_ratsnest(self) -> None:
        from cadgen.kicad.plot import BOARD_BACKGROUND, build_plot

        finished = build_plot(self.folder / "finished" / "blinky.kicad_pcb")
        draft = build_plot(self.folder / "draft" / "blinky.kicad_pcb")
        self.assertEqual((finished["kind"], finished["unrouted"], len(finished["sheets"])), ("board", 0, 1))
        self.assertEqual(draft["unrouted"], 1)
        sheet = finished["sheets"][0]
        self.assertEqual(sheet["background"], BOARD_BACKGROUND)
        self.assertAlmostEqual(sheet["width"], 40.0, delta=0.05)
        self.assertTrue(sheet["svg"].lstrip().startswith("<?xml") or "<svg" in sheet["svg"][:400])
        self.assertNotIn("<title>", sheet["svg"])  # KiCad's timestamped title is gone
        # The ratsnest is drawn in the grey KiCad gives the scratch layer; a finished board has none.
        self.assertIn("#C2C2C2", draft["sheets"][0]["svg"])
        self.assertNotIn("#C2C2C2", sheet["svg"])

    def test_a_schematic_plots_one_sheet_per_page(self) -> None:
        from cadgen.kicad.plot import SCHEMATIC_BACKGROUND, build_plot

        payload = build_plot(self.folder / "finished" / "blinky.kicad_sch")
        self.assertEqual((payload["kind"], len(payload["sheets"])), ("schematic", 1))
        self.assertEqual(payload["sheets"][0]["background"], SCHEMATIC_BACKGROUND)

    def test_the_payload_is_cached_by_the_documents_bytes(self) -> None:
        from cadgen.kicad.plot import plot_payload_bytes

        board = self.folder / "finished" / "blinky.kicad_pcb"
        first = plot_payload_bytes(board)
        self.assertEqual(plot_payload_bytes(board), first)
        self.assertEqual(json.loads(first)["schemaVersion"], 1)

    def test_validate_reads_kicads_verdict_and_writes_nothing(self) -> None:
        from cadgen import pcb

        project = self.folder / "draft"
        before = sorted(path.name for path in project.iterdir())
        finished = pcb.validate(self.folder / "finished" / "blinky.kicad_pcb")
        draft = pcb.validate(project / "blinky.kicad_pcb")
        self.assertTrue(finished.ok, finished.issues)
        self.assertFalse(draft.ok)
        self.assertIn("unconnected.unconnected_items", [issue.code for issue in draft.issues])
        self.assertEqual(sorted(path.name for path in project.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
