"""What a KiCad schematic's plot reads and is cached by, and which of a board's DRC findings it keeps, without KiCad.

A plot reads its root and every sheet under it, wherever the sheets lie (a subfolder, a folder
beside the root's), and nothing else a document names; KiCad plots a copy of those files staged
as they lie, and the store keys the payload on the same files' names and bytes. So two roots in
one folder are two plots, and an edit to a sheet is its root's alone. KiCad's own plot of the
same hierarchy is the KiCad suite's (tests/python/packages/kicad/test_pcb_schematic_index.py).
"""

from __future__ import annotations

import json

import tempfile
import unittest
from pathlib import Path

from tests.python.support.kicad_schematics import HIERARCHY_SHEETS, write_hierarchy
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.kicad.plot import _drc_report, _inputs  # noqa: E402
from cadgen.kicad.cli import stage_files  # noqa: E402
from cadgen.kicad.schematic_index import read_index  # noqa: E402


class PlotInputsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_each_root_in_a_folder_is_its_own_plot(self) -> None:
        # Four schematics in one folder and its subfolder, none with a project of its own.
        write_hierarchy(self.folder)
        names = ("hier.kicad_sch", "power.kicad_sch", "sheets/child.kicad_sch", "sheets/deep.kicad_sch")
        keys = {name: _inputs(self.folder / name).key() for name in names}
        self.assertEqual(len(set(keys.values())), 4)
        deep = self.folder / "sheets" / "deep.kicad_sch"
        deep.write_text(deep.read_text(encoding="utf-8").replace('"GND"', '"GND2"'), encoding="utf-8")
        self.assertNotEqual(_inputs(self.folder / "hier.kicad_sch").key(), keys["hier.kicad_sch"])
        self.assertEqual(_inputs(self.folder / "power.kicad_sch").key(), keys["power.kicad_sch"])

    def test_a_hierarchy_is_staged_as_it_lies(self) -> None:
        # The power sheet lies beside the project's folder, as a sheet two projects share can.
        project, common = self.folder / "project", self.folder / "common"
        project.mkdir()
        common.mkdir()
        write_hierarchy(project)
        (project / "power.kicad_sch").rename(common / "power.kicad_sch")
        root = project / "hier.kicad_sch"
        root.write_text(root.read_text(encoding="utf-8").replace('"power.kicad_sch"', '"../common/power.kicad_sch"'), encoding="utf-8")
        (project / "hier.kicad_pro").write_text("{}", encoding="utf-8")
        inputs = _inputs(root)
        self.assertEqual(
            [path.relative_to(self.folder).as_posix() for path, _data in inputs.files],
            ["project/hier.kicad_sch", "project/sheets/child.kicad_sch", "common/power.kicad_sch",
             "project/sheets/deep.kicad_sch", "project/hier.kicad_pro"],
        )
        with tempfile.TemporaryDirectory() as stage:
            staged = stage_files(inputs.files, Path(stage))
            self.assertEqual([sheet.name for sheet in read_index(staged).sheets], [name for name, _path, _file in HIERARCHY_SHEETS])

    def test_a_sheet_that_is_no_schematic_is_never_read(self) -> None:
        write_hierarchy(self.folder)
        notes = self.folder / "notes.txt"
        notes.write_text("not a schematic", encoding="utf-8")
        root = self.folder / "hier.kicad_sch"
        root.write_text(root.read_text(encoding="utf-8").replace('"power.kicad_sch"', '"notes.txt"'), encoding="utf-8")
        self.assertNotIn(notes, [path for path, _data in _inputs(root).files])
        self.assertNotIn("Power Stäge", [sheet.name for sheet in read_index(root).sheets])

    def test_a_boards_findings_leave_out_where_its_footprints_came_from(self) -> None:
        # The plot's DRC has no library tables: "not in the library" says nothing about the board.
        report = self.folder / "drc.json"
        violation = lambda kind: {"type": kind, "severity": "warning", "description": kind, "items": [{"description": "J1", "uuid": "u", "pos": {"x": 1, "y": 2}}]}
        report.write_text(json.dumps({"violations": [violation("lib_footprint_issues"), violation("lib_footprint_mismatch"), violation("clearance")]}), encoding="utf-8")
        self.assertEqual([finding[2] for finding in _drc_report(report)], ["clearance"])


if __name__ == "__main__":
    unittest.main()
