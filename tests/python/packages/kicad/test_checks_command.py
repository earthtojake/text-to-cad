"""KiCad's own checks and exports through the ``cad`` command, as a person types them: ``cad kicad drc BOARD``,
``cad kicad erc SCHEMATIC`` and ``cad export FILE DST [--as KIND]``, run by the Python of the environment of
``cad[kicad]`` (``tests/python/support/kicode.py``), where the command runs KiCad itself. Each answer is the one the
library's call gives (``cad.kicad.drc``, ``cad.kicad.erc``), the same findings; an export writes what DST says, each
board kind of several files into a folder and a ``.zip``, and the library's ``cad.export(file, dst, as_=...)`` the
same; and ``cad dfm`` of either file is refused, naming its KiCad check."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.python.support import kicode
from tests.python.support.kicad_board import write_board, write_schematic


class KicadChecksCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._folder = tempfile.TemporaryDirectory(prefix="kicad-checks-")
        cls.root = Path(cls._folder.name).resolve()  # the folder the command runs in, as its working folder names it
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

    def exported(self, *argv: str) -> dict:
        """``cad export ARGV --json``'s answer, which must be a success."""
        done = self.cad("export", *argv, "--json")
        self.assertEqual(0, done.returncode, done.stderr)
        return json.loads(done.stdout)

    def test_export_writes_what_dst_says(self) -> None:
        fab = self.root / "fab"
        # One file at the file named, its kind by its suffix, or by --as where a .csv holds either.
        answer = self.exported(str(self.board), "fab/placement.csv", "--as", "pos")
        self.assertEqual((answer["as"], answer["written"]), ("pos", [str(fab / "placement.csv")]))
        self.assertTrue((fab / "placement.csv").read_text(encoding="utf-8").startswith("Ref,Val,Package"))
        answer = self.exported(str(self.board), "fab/board.step")
        self.assertEqual((answer["as"], answer["written"]), ("step", [str(fab / "board.step")]))
        self.assertTrue((fab / "board.step").read_text(encoding="utf-8").startswith("ISO-10303-21"))
        # Several files into the folder named, by KiCad's names, or zipped into the .zip.
        answer = self.exported(str(self.board), "fab/gerbers/", "--as", "gerbers")
        names = sorted(Path(path).relative_to(fab / "gerbers").as_posix() for path in answer["written"])
        self.assertIn("blinky-Edge_Cuts.gbr", names)
        self.assertIn("blinky-job.gbrjob", names)
        answer = self.exported(str(self.board), "fab/gerbers.zip", "--as", "gerbers")
        self.assertEqual(answer["written"], [str(fab / "gerbers.zip")])
        with zipfile.ZipFile(fab / "gerbers.zip") as archive:
            self.assertEqual(sorted(archive.namelist()), names)
        # An ODB++ into a .zip is KiCad's compressed ODB++; into a folder, its tree.
        self.exported(str(self.board), "fab/odb.zip", "--as", "odb")
        with zipfile.ZipFile(fab / "odb.zip") as archive:
            self.assertIn("blinky/matrix/matrix", archive.namelist())
        self.exported(str(self.board), "fab/odb/", "--as", "odb")
        self.assertTrue((fab / "odb" / "matrix" / "matrix").is_file())
        # A schematic's: its netlist at the file named, its SVGs (one a sheet) into a folder or a .zip.
        answer = self.exported(str(self.schematic), "fab/blinky.net")
        self.assertEqual((answer["as"], answer["written"]), ("netlist", [str(fab / "blinky.net")]))
        answer = self.exported(str(self.schematic), "fab/sheets/")
        self.assertEqual(answer["as"], "svg")
        self.assertEqual([Path(path).suffix for path in answer["written"]], [".svg"])
        self.exported(str(self.schematic), "fab/sheets.zip")
        with zipfile.ZipFile(fab / "sheets.zip") as archive:
            self.assertEqual(archive.namelist(), [Path(answer["written"][0]).name])
        # Said in words, each file written; a destination that cannot say the kind is refused, nothing written.
        done = self.cad("export", str(self.board), "fab/outline.dxf")
        self.assertEqual((done.returncode, done.stdout), (0, f"wrote {fab / 'outline.dxf'}\n"), done.stderr)
        done = self.cad("export", str(self.board), "refused/")
        self.assertEqual(2, done.returncode)
        self.assertIn("refused/ is a folder, which takes a board's Gerbers", done.stderr)
        self.assertFalse((self.root / "refused").exists())

    def test_the_library_s_export_is_the_command_s(self) -> None:
        """``cad.export(file, dst, as_=...)`` in a script, as ``cad run`` runs one: the drill files and the PDF, each
        into a folder and a ``.zip``; the GLB, the IPC-2581, the BOM and a schematic's PDF at the file named; and a
        one-file kind into a folder refused by name, ``as_`` spelled as the library spells it."""
        code = """
import json, sys, zipfile
from pathlib import Path
import cad
board, schematic = sys.argv[1:3]
said = {}
for dst, kind in (("lib/drill/", "drill"), ("lib/drill.zip", "drill"), ("lib/pdf/", "pdf"), ("lib/pdf.zip", "pdf"),
                  ("lib/board.glb", None), ("lib/board.xml", "ipc2581"), ("lib/bom.csv", "bom")):
    done = cad.export(board, dst, as_=kind)
    said[dst] = [done.to, [Path(path).relative_to(Path.cwd()).as_posix() for path in done.written]]
    if dst.endswith(".zip"):
        said[dst].append(sorted(zipfile.ZipFile(dst).namelist()))
done = cad.export(schematic, "lib/sheets.pdf")
said["lib/sheets.pdf"] = [done.to, [Path(path).relative_to(Path.cwd()).as_posix() for path in done.written]]
try:
    cad.export(board, "lib/", as_="glb")
except ValueError as refused:
    said["refused"] = str(refused)
print(json.dumps(said))
"""
        done = kicode.run_python(self, code, str(self.board), str(self.schematic), cwd=self.root,
                                 env={**os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(0, done.returncode, done.stderr)
        said = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual(said["lib/drill/"], ["drill", ["lib/drill/blinky.drl"]])
        self.assertEqual(said["lib/drill.zip"], ["drill", ["lib/drill.zip"], ["blinky.drl"]])
        self.assertEqual(said["lib/pdf/"], ["pdf", ["lib/pdf/blinky-back.pdf", "lib/pdf/blinky-front.pdf"]])
        self.assertEqual(said["lib/pdf.zip"], ["pdf", ["lib/pdf.zip"], ["blinky-back.pdf", "blinky-front.pdf"]])
        for dst, kind in (("lib/board.glb", "glb"), ("lib/board.xml", "ipc2581"), ("lib/bom.csv", "bom"),
                          ("lib/sheets.pdf", "pdf")):
            self.assertEqual(said[dst], [kind, [dst]])
        self.assertTrue((self.root / "lib" / "bom.csv").read_text(encoding="utf-8").startswith("Reference,Value"))
        self.assertEqual(said["refused"], "lib/ is a folder, and a board's GLB is one file: name the file "
                                          "(lib/blinky.glb)")


if __name__ == "__main__":
    unittest.main()
