"""KiCad's own checks and exports through the ``cad`` command, as a person types them: ``cad kicad drc BOARD``,
``cad kicad erc SCHEMATIC`` and ``cad export BOARD DIR --to KIND``, run by the Python of the environment of
``cad[kicad]`` (``tests/python/support/kicode.py``), where the command runs KiCad itself. Each answer is the one the
library's call gives (``cad.kicad.drc``, ``cad.kicad.erc``), the same findings; and ``cad dfm`` of either file is
refused, naming its KiCad check."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.python.support import kicode
from tests.python.support.kicad_board import write_board, write_schematic


class KicadChecksCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._folder = tempfile.TemporaryDirectory(prefix="kicad-checks-")
        cls.root = Path(cls._folder.name)
        cls.board = write_board(cls.root)
        cls.schematic = write_schematic(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._folder.cleanup()

    def cad(self, *argv: str) -> subprocess.CompletedProcess:
        """``cad ARGV`` run by the kicad environment's Python, in the board's folder."""
        return subprocess.run([kicode.python(self), "-m", "cad_server.cli", *argv], cwd=self.root,
                              env={**os.environ, "PYTHONUTF8": "1"}, capture_output=True, text=True,
                              encoding="utf-8", timeout=600, check=False)

    def test_drc_of_a_board_is_kicad_s_and_the_library_s(self) -> None:
        done = self.cad("kicad", "drc", str(self.board), "--json")
        self.assertEqual(1, done.returncode, done.stderr)  # the LED's net is not routed: an unconnected item fails it
        answer = json.loads(done.stdout)
        codes = [finding["code"] for finding in answer["findings"]]
        self.assertIn("unconnected_items", codes, answer)
        self.assertNotIn("kicad_failed", codes, answer)
        called = kicode.call(self, "drc", self.board)
        self.assertEqual(sorted(codes), sorted(finding["code"] for finding in called["findings"]))
        self.assertEqual(len(answer["measurements"]["drc"]), len(called["measurements"]["drc"]))

    def test_erc_of_a_schematic_is_kicad_s_and_the_library_s(self) -> None:
        done = self.cad("kicad", "erc", str(self.schematic), "--json")
        self.assertIn(done.returncode, (0, 1), done.stderr)
        answer = json.loads(done.stdout)
        self.assertEqual(answer["ok"], done.returncode == 0)
        called = kicode.call(self, "erc", self.schematic, document_type="kicad_sch")
        self.assertEqual(sorted(finding["code"] for finding in answer["findings"]),
                         sorted(finding["code"] for finding in called["findings"]))
        self.assertNotIn("kicad_failed", {finding["code"] for finding in answer["findings"]})

    def test_dfm_of_a_kicad_file_names_its_kicad_check(self) -> None:
        for file, check in ((self.board, "drc"), (self.schematic, "erc")):
            with self.subTest(file=file.name):
                done = self.cad("dfm", str(file))
                self.assertEqual(2, done.returncode, done.stderr)
                self.assertIn(f"KiCad's own check of it is cad kicad {check}", done.stderr)

    def test_export_writes_kicad_s_outputs_into_the_folder_dst(self) -> None:
        out = self.root / "fab" / "pos"
        done = self.cad("export", str(self.board), str(out), "--to", "pos", "--json")
        self.assertEqual(0, done.returncode, done.stderr)
        answer = json.loads(done.stdout)
        self.assertEqual("pos", answer["to"])
        self.assertEqual([str(out / "blinky-pos.csv")], answer["written"])
        self.assertTrue((out / "blinky-pos.csv").is_file())


if __name__ == "__main__":
    unittest.main()
