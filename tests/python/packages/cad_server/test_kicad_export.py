"""``cad_server.kicad.export``: the exports of a saved board by kicad-cli, headless, in private homes.

The command each export builds, the files it reports and what it refuses. No KiCad: ``subprocess.run``
is replaced by a function that writes what kicad-cli would. (The real runs are
``tests/python/packages/kicad``.)
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad_server.kicad import export
from cad_server.kicad.cli import KicadRunError

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
        self.assertEqual(export.EXPORTS, ("gerbers", "drill", "pos", "step"))
        for to in ("pdf", "stl", "", "Gerbers"):
            with self.subTest(to=to), self.assertRaisesRegex(ValueError, "choose one of gerbers, drill, pos, step"):
                export.commands(CLI, self.board, to, self.out)

    def test_gerbers_and_drill_write_a_folder(self) -> None:
        folder = os.path.join(self.out, "")
        self.assertEqual(self.command("gerbers")[4:-1], ["--board-plot-params", "-o", folder])
        self.assertEqual(self.command("drill")[4:-1],
                         ["--format", "excellon", "--excellon-units", "mm", "-o", folder])

    def test_pos_is_csv_in_millimetres_for_both_sides(self) -> None:
        self.assertEqual(self.command("pos")[4:-1], ["--format", "csv", "--units", "mm", "--side", "both",
                                                     "-o", str(self.out / "uart-pos.csv")])

    def test_step_substitutes_step_models_for_vrml_ones(self) -> None:
        command = self.command("step")
        self.assertIn("--subst-models", command)
        self.assertEqual(command[command.index("-o") + 1], str(self.out / "uart.step"))


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

    def test_only_a_saved_board_is_exported(self) -> None:
        with self.fake():
            for target in (self.root / "missing.kicad_pcb", self.root / "uart.step"):
                with self.subTest(target=target.name), self.assertRaisesRegex(KicadRunError, "not a saved KiCad board"):
                    export.export(target, "gerbers", self.out, cli=CLI)
            with self.assertRaisesRegex(ValueError, "choose one of"):
                export.export(self.board, "stl", self.out, cli=CLI)
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main()
