"""``cad.kicad._export``: the exports of a saved board by kicad-cli, headless, in private homes; and
``cad.kicad._destination``: where a KiCad file's export goes, what its destination says.

The command each export builds, the files it reports and what it refuses; what each destination writes, what it
refuses before KiCad runs, and the files put there. No KiCad: ``subprocess.run`` is replaced by a function that
writes what kicad-cli would. (The real runs are ``tests/python/packages/kicad``.)
"""

from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from cad._internal.refused import ArgumentRefused
from cad.kicad import _destination as destination
from cad.kicad import _export as export
from cad.kicad._program import KicadRunError

CLI = Path("/opt/kicad/bin/kicad-cli")


class Commands(unittest.TestCase):
    def setUp(self) -> None:
        self.board = Path("boards") / "uart.kicad_pcb"
        self.out = Path("out")

    def command(self, to: str) -> list[str]:
        (command,) = export.commands(CLI, self.board, to, self.out)
        self.assertEqual(command[:4], [str(CLI), "pcb", "export", to])
        self.assertEqual(command[-1], str(self.board))
        return command

    def test_the_list_is_fixed(self) -> None:
        self.assertEqual(export.EXPORTS, ("gerbers", "drill", "pos", "bom", "step", "glb", "odb", "ipc2581", "pdf", "dxf"))
        for to in ("svg", "stl", "", "Gerbers"):
            with self.subTest(to=to), self.assertRaisesRegex(ValueError, "choose one of gerbers, drill, pos, bom, step"):
                export.commands(CLI, self.board, to, self.out)

    def test_gerbers_and_drill_write_a_folder(self) -> None:
        folder = os.path.join(self.out, "")
        self.assertEqual(self.command("gerbers")[4:-1], ["--board-plot-params", "-o", folder])
        self.assertEqual(self.command("drill")[4:-1],
                         ["--format", "excellon", "--excellon-units", "mm", "-o", folder])

    def test_pos_is_csv_in_millimetres_for_both_sides(self) -> None:
        self.assertEqual(self.command("pos")[4:-1], ["--format", "csv", "--units", "mm", "--side", "both",
                                                     "-o", str(self.out / "uart-pos.csv")])

    def test_step_and_glb_substitute_step_models_for_vrml_ones(self) -> None:
        for to in ("step", "glb"):
            command = self.command(to)
            self.assertIn("--subst-models", command)
            self.assertEqual(command[command.index("-o") + 1], str(self.out / f"uart.{to}"))

    def test_a_boards_glb_carries_its_layers_and_its_step_does_not(self) -> None:
        layers = ["--include-tracks", "--include-pads", "--include-zones", "--include-inner-copper",
                  "--include-silkscreen", "--include-soldermask"]
        self.assertEqual([flag for flag in self.command("glb") if flag.startswith("--include")], layers)
        self.assertEqual([flag for flag in self.command("step") if flag.startswith("--include")], [])

    def test_odb_ipc2581_and_the_outline_are_millimetres(self) -> None:
        self.assertEqual(self.command("odb")[4:-1], ["--units", "mm", "--compression", "zip",
                                                     "-o", str(self.out / "uart-odb.zip")])
        # Uncompressed, KiCad's tree of it, into the folder itself.
        (tree,) = export.commands(CLI, self.board, "odb", self.out, compressed=False)
        self.assertEqual(tree[4:-1], ["--units", "mm", "--compression", "none", "-o", os.path.join(self.out, "")])
        self.assertEqual(self.command("ipc2581")[4:-1], ["--units", "mm", "--version", "C",
                                                         "-o", str(self.out / "uart-ipc2581.xml")])
        dxf = self.command("dxf")
        self.assertEqual(dxf[dxf.index("--layers") + 1], "Edge.Cuts")
        self.assertEqual(dxf[dxf.index("--output-units") + 1], "mm")
        self.assertEqual(dxf[dxf.index("-o") + 1], str(self.out / "uart-outline.dxf"))

    def test_the_pdf_is_a_page_a_side_the_back_mirrored(self) -> None:
        front, back = export.commands(CLI, self.board, "pdf", self.out)
        self.assertEqual(front[front.index("--layers") + 1], "F.Cu,F.Silkscreen,F.Fab,Edge.Cuts")
        self.assertEqual(back[back.index("--layers") + 1], "B.Cu,B.Silkscreen,B.Fab,Edge.Cuts")
        self.assertNotIn("--mirror", front)
        self.assertIn("--mirror", back)
        self.assertEqual([front[front.index("-o") + 1], back[back.index("-o") + 1]],
                         [str(self.out / "uart-front.pdf"), str(self.out / "uart-back.pdf")])

    def test_the_bom_reads_the_schematic_grouped_by_value_and_footprint(self) -> None:
        (command,) = export.commands(CLI, self.board, "bom", self.out, Path("scratch"))
        self.assertEqual(command[:4], [str(CLI), "sch", "export", "bom"])
        self.assertEqual(command[-1], str(self.board.with_suffix(".kicad_sch")))
        self.assertEqual(command[command.index("--group-by") + 1], "Value,Footprint")
        self.assertEqual(command[command.index("--ref-range-delimiter") + 1], "")
        self.assertIn("--exclude-dnp", command)
        self.assertEqual(command[command.index("-o") + 1], str(Path("scratch") / "uart-bom-kicad.csv"))


class Run(unittest.TestCase):
    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-kicad-export-")
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name)
        self.board = self.root / "uart.kicad_pcb"
        self.board.write_text("(kicad_pcb)", encoding="utf-8")
        self.out = self.root / "fab" / "out"  # made by the export
        self.seen: list[dict] = []

    def fake(self, *, returncode: int = 0, files: tuple[str, ...] = ("a.gtl", "b.gbl"), stderr: str = ""):
        def run(command, *, env, **_options):
            self.seen.append(dict(command=command, env=env))
            if returncode == 0:
                for name in files:
                    (self.out / name).write_text(name, encoding="utf-8")
            return mock.Mock(returncode=returncode, stdout="", stderr=stderr)

        return mock.patch.object(export.subprocess, "run", run)

    def test_it_returns_the_files_it_wrote_and_only_those(self) -> None:
        self.out.mkdir(parents=True)
        (self.out / "older.txt").write_text("not ours", encoding="utf-8")
        with mock.patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}), self.fake():
            written = export.export(self.board, "gerbers", self.out, cli=CLI)
        self.assertEqual(written, [(self.out / "a.gtl").resolve(), (self.out / "b.gbl").resolve()])
        (call,) = self.seen
        self.assertNotIn("DISPLAY", call["env"])
        self.assertNotIn("WAYLAND_DISPLAY", call["env"])
        scratch = Path(call["env"]["HOME"]).parent
        self.assertTrue(scratch.name.startswith("cad-export-"), scratch)
        self.assertFalse(scratch.exists(), "the private homes are removed after the run")
        self.assertEqual(self.board.read_text(encoding="utf-8"), "(kicad_pcb)")

    def test_a_run_that_changes_a_file_reports_it(self) -> None:
        self.out.mkdir(parents=True)
        (self.out / "a.gtl").write_text("old", encoding="utf-8")
        with self.fake(files=("a.gtl",)):
            self.assertEqual([path.name for path in export.export(self.board, "gerbers", self.out, cli=CLI)],
                             ["a.gtl"])

    def test_kicad_refusing_the_board_says_what_it_said(self) -> None:
        with self.fake(returncode=1, stderr="Fontconfig error: x\nFailed to load board\n"), \
                self.assertRaisesRegex(KicadRunError, "export pos failed on .*uart.kicad_pcb: Failed to load board$"):
            export.export(self.board, "pos", self.out, cli=CLI)

    def test_a_run_that_writes_nothing_is_an_error(self) -> None:
        with self.fake(files=()), self.assertRaisesRegex(KicadRunError, "wrote no file"):
            export.export(self.board, "drill", self.out, cli=CLI)

    def test_the_bom_keeps_its_columns_and_the_part_numbers_any_part_has(self) -> None:
        import csv

        raw, out = self.root / "raw.csv", self.root / "bom.csv"
        header = ["Reference", "Value", "Footprint", "${QUANTITY}", *(name for names in export.BOM_FIELDS.values()
                                                                    for name in names)]
        rows = [["C1,C2", "100nF", "C_0603", "2", *[""] * (len(header) - 4)],
                ["R1", "10k", "R_0603", "1", *[""] * (len(header) - 4)]]
        rows[1][header.index("LCSC Part")] = "C25804"
        with raw.open("w", newline="", encoding="utf-8") as file:
            csv.writer(file).writerows([header, *rows])
        export._bom(raw, out)
        with out.open(newline="", encoding="utf-8") as file:
            read = list(csv.reader(file))
        self.assertEqual(read, [["Reference", "Value", "Footprint", "Quantity", "LCSC"],
                                ["C1,C2", "100nF", "C_0603", "2", ""], ["R1", "10k", "R_0603", "1", "C25804"]])

    def test_a_bom_without_a_schematic_is_refused_in_one_line(self) -> None:
        with self.fake(), self.assertRaisesRegex(KicadRunError, "no uart.kicad_sch beside uart.kicad_pcb"):
            export.export(self.board, "bom", self.out, cli=CLI)
        self.assertEqual(self.seen, [])

    def test_only_a_saved_board_is_exported(self) -> None:
        with self.fake():
            for target in (self.root / "missing.kicad_pcb", self.root / "uart.step"):
                with self.subTest(target=target.name), self.assertRaisesRegex(KicadRunError, "not a saved KiCad board"):
                    export.export(target, "gerbers", self.out, cli=CLI)
            with self.assertRaisesRegex(ValueError, "choose one of"):
                export.export(self.board, "stl", self.out, cli=CLI)
        self.assertEqual(self.seen, [])


class Destinations(unittest.TestCase):
    """``cad export FILE DST [--as KIND]``: DST says what is written -- a file by its suffix, a folder (a path that
    ends in a separator, or a folder that is there) or a ``.zip`` -- and ``--as`` names the kind only where DST cannot:
    a board's folder or ``.zip``, and its ``.csv``. Every refusal names what fits, before KiCad runs."""

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory(prefix="tmp-kicad-destination-")
        self.addCleanup(self._tempdir.cleanup)
        self.root = Path(self._tempdir.name)
        self.board, self.schematic = self.root / "uart.kicad_pcb", self.root / "uart.kicad_sch"
        (self.root / "there").mkdir()

    def plan(self, document_type: str, dst: str, as_: str | None = None) -> tuple[str, str, Path, dict]:
        source = self.board if document_type == "kicad_pcb" else self.schematic
        found = destination.resolve(document_type, source, dst, as_)
        return found.kind, found.form, found.dst, found.options

    def test_each_destination_says_what_is_written(self) -> None:
        root = self.root
        for dst, as_, kind, form in (
                ("uart.step", None, "step", "file"), ("uart.stp", "step", "step", "file"),
                ("3d/uart.glb", None, "glb", "file"), ("outline.dxf", "dxf", "dxf", "file"),
                ("uart.xml", None, "ipc2581", "file"), ("pos.csv", "pos", "pos", "file"),
                ("bom.CSV", "bom", "bom", "file"), ("fab/", "gerbers", "gerbers", "folder"),
                (str(root / "there"), "drill", "drill", "folder"), ("fab/pdf.zip", "pdf", "pdf", "zip"),
                ("fab/odb.zip", "odb", "odb", "zip")):
            with self.subTest(dst=dst, as_=as_):
                self.assertEqual(self.plan("kicad_pcb", os.path.join(root, dst), as_)[:2], (kind, form))
        # A folder holds the ODB++ uncompressed, its tree; a .zip is KiCad's own zip of it.
        self.assertEqual(self.plan("kicad_pcb", f"{root}/odb/", "odb")[3], {"compressed": False})
        self.assertEqual(self.plan("kicad_pcb", str(root / "odb.zip"), "odb")[3], {})
        for dst, as_, kind, form in (("sheets.pdf", None, "pdf", "file"), ("uart.net", "netlist", "netlist", "file"),
                                     ("bom.csv", None, "bom", "file"), ("sheets/", None, "svg", "folder"),
                                     ("sheets.zip", "svg", "svg", "zip")):
            with self.subTest(dst=dst, as_=as_):
                self.assertEqual(self.plan("kicad_sch", os.path.join(root, dst), as_)[:2], (kind, form))
        # A destination is where it says, made absolute; ``~`` is the home folder.
        self.assertEqual(self.plan("kicad_pcb", "~/uart.step")[2], Path.home() / "uart.step")
        self.assertTrue(self.plan("kicad_pcb", "fab/uart.step")[2].is_absolute())

    def test_a_destination_that_cannot_say_or_says_otherwise_is_refused_naming_what_fits(self) -> None:
        root = self.root
        for document_type, dst, as_, said in (
                ("kicad_pcb", "fab/", None, "fab/ is a folder, which takes a board's Gerbers, drill files, ODB++ or "
                                            "PDF: name which, --as gerbers, --as drill, --as odb or --as pdf"),
                ("kicad_pcb", "fab.zip", None, "fab.zip is a .zip, which takes a board's Gerbers"),
                ("kicad_pcb", "fab.csv", None, "fab.csv is a .csv, which takes a board's placement or BOM: name "
                                               "which, --as pos or --as bom"),
                ("kicad_pcb", "fab/", "glb", "fab/ is a folder, and a board's GLB is one file: name the file "
                                             "(fab/uart.glb)"),
                ("kicad_pcb", "fab.zip", "step", "fab.zip is a .zip, and a board's STEP is one file: name the file "
                                                 "(fab.step)"),
                ("kicad_pcb", "uart.glb", "step", "uart.glb is a board's GLB, and --as step names its STEP: they must "
                                                  "agree"),
                ("kicad_pcb", "pos.csv", "step", "pos.csv is a board's placement or BOM, and --as step names its "
                                                 "STEP: they must agree"),
                ("kicad_pcb", "uart.glb", "gerbers", "--as gerbers writes several files: name a folder (ending in /) "
                                                     "or a .zip, not uart.glb"),
                ("kicad_pcb", "uart.pdf", None, "uart.pdf: a board's PDF is two files, a drawing of each side: name a "
                                                "folder or a .zip, with --as pdf"),
                ("kicad_pcb", "uart.txt", None, "uart.txt: a board's export is a .step, .stp, .glb, .dxf, .xml or "
                                                ".csv file, a folder or a .zip"),
                ("kicad_pcb", "uart.step", "svg", "--as svg: a board's export is one of gerbers, drill, pos, bom"),
                ("kicad_pcb", "", None, "a board's export names its destination: a file, a folder or a .zip"),
                ("kicad_sch", "sheets/", "pdf", "sheets/ is a folder, and a schematic's PDF is one file: name the "
                                                "file (sheets/uart.pdf)"),
                ("kicad_sch", "sheet.svg", None, "sheet.svg: a schematic's export is a .pdf, .net or .csv file, a "
                                                 "folder or a .zip"),
                ("kicad_sch", "uart.net", "bom", "uart.net is a schematic's netlist, and --as bom names its BOM: they "
                                                 "must agree")):
            with self.subTest(dst=dst, as_=as_):
                with self.assertRaises(ArgumentRefused) as refused:  # each destination as typed, in the folder
                    self.plan(document_type, dst, as_)
                self.assertTrue(str(refused.exception).startswith(said), refused.exception)

    def test_an_export_never_writes_over_its_source_and_the_library_spells_its_keyword(self) -> None:
        with self.assertRaisesRegex(ArgumentRefused, "is the board itself: an export never writes over its source"):
            destination.resolve("kicad_pcb", self.board, str(self.root / "." / "uart.kicad_pcb"), "step")
        with self.assertRaisesRegex(ArgumentRefused, "name which, as_=gerbers, as_=drill, as_=odb or as_=pdf"):
            destination.resolve("kicad_pcb", self.board, f"{self.root}/fab/", flag="as_=")

    @staticmethod
    def wrote(folder: Path, *names: str) -> list[Path]:
        """What KiCad would have written into its folder: each file holding its own name."""
        for name in names:
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text(name, encoding="utf-8")
        return [folder / name for name in names]

    def test_what_kicad_wrote_is_put_where_the_destination_says(self) -> None:
        wrote = self.wrote
        root = self.root
        with destination.scratch() as made:
            plan = destination.resolve("kicad_pcb", self.board, f"{root}/fab/gerbers/", "gerbers")
            placed = destination.place(plan, wrote(Path(made), "uart-F_Cu.gbr", "uart-job.gbrjob"), made)
        self.assertEqual(placed, [root / "fab" / "gerbers" / "uart-F_Cu.gbr", root / "fab" / "gerbers" / "uart-job.gbrjob"])
        with destination.scratch() as made:
            plan = destination.resolve("kicad_pcb", self.board, f"{root}/fab/odb/", "odb")
            placed = destination.place(plan, wrote(Path(made), "matrix/matrix", "steps/pcb/profile"), made)
        self.assertEqual(placed, [root / "fab" / "odb" / "matrix" / "matrix", root / "fab" / "odb" / "steps" / "pcb" /
                                  "profile"])
        with destination.scratch() as made:
            plan = destination.resolve("kicad_pcb", self.board, str(root / "3d" / "board.step"))
            self.assertEqual(destination.place(plan, wrote(Path(made), "uart.step"), made), [root / "3d" / "board.step"])
        self.assertEqual("uart.step", (root / "3d" / "board.step").read_text(encoding="utf-8"))
        with destination.scratch() as made:  # KiCad's own zip of an ODB++, moved there as it is
            plan = destination.resolve("kicad_pcb", self.board, str(root / "odb.zip"), "odb")
            destination.place(plan, wrote(Path(made), "uart-odb.zip"), made)
        self.assertEqual("uart-odb.zip", (root / "odb.zip").read_text(encoding="utf-8"))
        # A .zip holds the files by their paths in KiCad's folder, each dated alike: the same files, the same zip.
        zips = []
        for name in ("a.zip", "b.zip"):
            with destination.scratch() as made:
                plan = destination.resolve("kicad_sch", self.schematic, str(root / name))
                self.assertEqual(destination.place(plan, wrote(Path(made), "uart.svg", "uart-power.svg"), made),
                                 [root / name])
            zips.append((root / name).read_bytes())
            with zipfile.ZipFile(root / name) as archive:
                self.assertEqual(archive.namelist(), ["uart-power.svg", "uart.svg"])
                self.assertEqual({entry.date_time for entry in archive.infolist()}, {(1980, 1, 1, 0, 0, 0)})
        self.assertEqual(zips[0], zips[1])
        with destination.scratch() as made, self.assertRaisesRegex(RuntimeError, "KiCad wrote no GLB"):
            destination.place(destination.resolve("kicad_pcb", self.board, str(root / "x.glb")), [], made)

    def test_a_destination_that_cannot_be_written_is_said_and_keeps_what_it_held(self) -> None:
        import errno
        import shutil

        root = self.root
        (root / "taken").write_text("a file, not a folder", encoding="utf-8")
        with destination.scratch() as made:
            plan = destination.resolve("kicad_pcb", self.board, f"{root}/taken/gerbers/", "gerbers")
            with self.assertRaisesRegex(RuntimeError, "cannot write the Gerbers to .*taken"):
                destination.place(plan, self.wrote(Path(made), "uart-F_Cu.gbr"), made)
        # A folder's files are all made beside their places before the first is renamed over what is there: one that
        # cannot be made changes none of them, and leaves nothing of its own behind.
        fab = root / "fab"
        fab.mkdir()
        (fab / "uart-F_Cu.gbr").write_text("earlier", encoding="utf-8")
        copy = shutil.copyfile

        def full(source: str, target: str, **options: object) -> object:
            if Path(source).name == "uart-job.gbrjob":
                raise OSError(errno.ENOSPC, "No space left on device")
            return copy(source, target, **options)

        with destination.scratch() as made, mock.patch.object(shutil, "copyfile", full):
            plan = destination.resolve("kicad_pcb", self.board, f"{fab}/", "gerbers")
            with self.assertRaisesRegex(RuntimeError, "cannot write the Gerbers to .*fab: No space left on device"):
                destination.place(plan, self.wrote(Path(made), "uart-F_Cu.gbr", "uart-job.gbrjob"), made)
        self.assertEqual("earlier", (fab / "uart-F_Cu.gbr").read_text(encoding="utf-8"))
        self.assertEqual(["uart-F_Cu.gbr"], [path.name for path in fab.iterdir()])


if __name__ == "__main__":
    unittest.main()
