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
        from cad_server.kicad.export import EXPORTS, export
        from cad_server.kicad.install import check_version, find_kicad_cli, kicad_version

        cli = find_kicad_cli()
        check_version(cli, kicad_version(cli))
        with tempfile.TemporaryDirectory(prefix="kicad-export-") as folder:
            root = Path(folder)
            board = root / "board.kicad_pcb"
            board.write_text(BOARD, encoding="utf-8")
            original = board.read_bytes()
            made = {to: export(board, to, root / "fab" / to) for to in EXPORTS}
            self.assertEqual(board.read_bytes(), original)
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


if __name__ == "__main__":
    unittest.main()
