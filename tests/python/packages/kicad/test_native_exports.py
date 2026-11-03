"""Real exports of a board by an installed kicad-cli (9 or newer); no samples, IPC server or user state."""
import tempfile
import unittest
from pathlib import Path

# Stable KiCad 9 syntax, so the same file loads in 9, 10 and the nightly: a 40 x 30 mm board, one 0603-like
# resistor R1 at (20, 15) and a mounting hole H1 at (5, 5) that the placement file leaves out.
BOARD = '''(kicad_pcb (version 20241229) (generator "pcbnew")
 (general (thickness 1.6)) (paper "A4")
 (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "B.SilkS" user "b.silkscreen") (37 "F.SilkS" user "f.silkscreen")
 (38 "B.Mask" user) (39 "F.Mask" user) (44 "Edge.Cuts" user) (49 "F.Fab" user))
 (setup (pad_to_mask_clearance 0))
 (gr_rect (start 0 0) (end 40 30) (stroke (width 0.05) (type default)) (fill none) (layer "Edge.Cuts"))
 (footprint "test:r" (layer "F.Cu") (at 20 15)
  (property "Reference" "R1" (at 0 -2) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "10k" (at 0 2) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (attr smd)
  (pad "1" smd rect (at -0.8 0) (size 0.9 1) (layers "F.Cu" "F.Mask"))
  (pad "2" smd rect (at 0.8 0) (size 0.9 1) (layers "F.Cu" "F.Mask")))
 (footprint "test:hole" (layer "F.Cu") (at 5 5)
  (property "Reference" "H1" (at 0 -3) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "hole" (at 0 3) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (attr board_only exclude_from_pos_files exclude_from_bom)
  (pad "" np_thru_hole circle (at 0 0) (size 2 2) (drill 2) (layers "*.Cu" "*.Mask")))
)'''


class NativeExports(unittest.TestCase):
    def test_gerbers_drill_pos_and_step_of_a_saved_board(self):
        from cad.kicad._export import EXPORTS, export
        from cad.kicad._program import check_version, find_kicad_cli, kicad_version

        cli = find_kicad_cli()
        check_version(cli, kicad_version(cli))
        with tempfile.TemporaryDirectory(prefix="kicad-export-") as folder:
            root = Path(folder)
            board = root / "board.kicad_pcb"
            board.write_text(BOARD, encoding="utf-8")
            original = board.read_bytes()
            made = {to: export(board, to, root / "fab" / to) for to in EXPORTS}
            self.assertEqual(board.read_bytes(), original)
            # The board's folder as found: kicad-cli's local settings (.kicad_prl) and project are not left.
            self.assertEqual(["board.kicad_pcb", "fab"], sorted(path.name for path in root.iterdir()))
            for to, files in made.items():
                self.assertTrue(files and all(path.is_file() and path.parent.name == to for path in files), (to, files))

            # The board's own plot settings pick the extensions (.gbr, or Protel's .gtl and .gm1).
            stems = {path.stem for path in made["gerbers"]}
            self.assertLessEqual({"board-Edge_Cuts", "board-F_Cu", "board-B_Cu", "board-job"}, stems)
            self.assertIn("board-job.gbrjob", {path.name for path in made["gerbers"]})

            drill = "".join(path.read_text(encoding="utf-8", errors="replace") for path in made["drill"]
                            if path.suffix == ".drl")
            self.assertIn("METRIC", drill)

            (pos,) = made["pos"]
            self.assertEqual(pos.name, "board-pos.csv")
            rows = [line.split(",") for line in pos.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual([cell.strip('"') for cell in rows[0][:1]], ["Ref"])
            self.assertEqual([row[0].strip('"') for row in rows[1:]], ["R1"])  # the hole is left out
            self.assertAlmostEqual(float(rows[1][3].strip('"')), 20, places=3)  # PosX, mm

            (step,) = made["step"]
            self.assertEqual(step.name, "board.step")
            self.assertTrue(step.read_text(encoding="utf-8", errors="replace").startswith("ISO-10303-21"))


class SharedTestBoard(unittest.TestCase):
    """The test board the reader, plot and command suites share is in the nightly's format (20260901)."""

    def test_a_nightly_checks_and_exports_it(self):
        from cad.kicad._export import export
        from cad.kicad._program import find_kicad_cli, kicad_version, version_tuple
        from cad_server.kicad.check import check as drc
        from tests.python.support.kicad_board import write_board

        cli = find_kicad_cli()
        if version_tuple(kicad_version(cli) or "0")[:2] < (10, 99):
            self.skipTest("the shared test board is in the format of a KiCad nightly (10.99)")
        with tempfile.TemporaryDirectory(prefix="kicad-shared-") as folder:
            board = write_board(Path(folder))
            result = drc(board)
            # No .kicad_pro beside it: checked against KiCad's defaults, and said so; nothing left beside it.
            self.assertIn("no_project", {issue.code for issue in result.issues}, result)
            self.assertEqual([board.name], sorted(path.name for path in Path(folder).iterdir()))
            # KiCad read it (a refusal is one issue, `kicad_failed`) and found the unrouted LED net's ratsnest line.
            codes = {issue.code for issue in result.issues}
            self.assertNotIn("kicad_failed", codes, result)
            self.assertIn("unconnected_items", codes, result)
            self.assertTrue(export(board, "step", Path(folder) / "fab")[0].is_file())


class StepWithoutModels(unittest.TestCase):
    """A part whose 3D model is missing, or only in VRML, leaves the STEP without that part's body: a
    warning naming it, not a failure, although kicad-cli exits 2 for it."""

    def test_missing_and_vrml_only_models_are_a_warning(self):
        import contextlib
        import io

        from cad.kicad._export import export

        with tempfile.TemporaryDirectory(prefix="kicad-step-models-") as folder:
            root = Path(folder)
            (root / "only.wrl").write_text("#VRML V2.0 utf8\nShape { geometry Box { size 1 1 1 } }\n", encoding="utf-8")
            r1 = '(attr smd)\n  (pad "1"'
            board = BOARD.replace(r1, f'(attr smd)\n  (model "{root / "gone" / "missing.step"}")\n  (pad "1"', 1)
            board = board.replace('(attr board_only', f'(model "{root / "only.wrl"}")\n  (attr board_only', 1)
            self.assertEqual(board.count("(model "), 2)
            path = root / "board.kicad_pcb"
            path.write_text(board, encoding="utf-8")
            said = io.StringIO()
            with contextlib.redirect_stderr(said):
                (step,) = export(path, "step", root / "fab")
            self.assertTrue(step.read_text(encoding="utf-8", errors="replace").startswith("ISO-10303-21"))
            self.assertIn("board.step is written", said.getvalue())
            self.assertIn("R1", said.getvalue())
            self.assertIn("VRML", said.getvalue())

    def test_an_output_folder_that_cannot_be_made_is_the_exports_error(self):
        from cad.kicad._export import export
        from cad.kicad._program import KicadRunError

        with tempfile.TemporaryDirectory(prefix="kicad-export-out-") as folder:
            root = Path(folder)
            board = root / "board.kicad_pcb"
            board.write_text(BOARD, encoding="utf-8")
            (root / "taken").write_text("a file, not a folder", encoding="utf-8")
            with self.assertRaisesRegex(KicadRunError, "cannot write the drill into"):
                export(board, "drill", root / "taken")

    def test_a_failed_export_still_fails(self):
        import subprocess

        from cad.kicad._export import _missing_models, _step_written

        step = Path(tempfile.mkdtemp(prefix="kicad-step-failed-")) / "board.step"
        step.write_text("ISO-10303-21;", encoding="utf-8")
        written = f"STEP file '{step}' created.\n"
        aborted = "** Error exporting STEP file. Export aborted. **\n"
        for code, out, ok in ((2, written, True), (2, aborted, False), (3, written, False), (2, "", False)):
            self.assertEqual(_step_written("step", subprocess.CompletedProcess([], code, out, ""), step), ok, (code, out))
        self.assertFalse(_step_written("gerbers", subprocess.CompletedProcess([], 2, written, ""), step))
        # Exit 0 with only files not found (kicad-cli's status then) still says which parts have no body.
        missing = "Could not add 3D model for C2.\nFile not found: x.step\nCould not add 3D model for C10.\n" + written
        warning = _missing_models("step", subprocess.CompletedProcess([], 0, missing, ""), step)
        self.assertIn("2 parts without a 3D model (C2, C10)", warning or "")
        self.assertIsNone(_missing_models("step", subprocess.CompletedProcess([], 0, written, ""), step))

if __name__ == "__main__":
    unittest.main()
