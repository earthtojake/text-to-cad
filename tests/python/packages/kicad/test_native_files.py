"""Real KiCad file commands (kicode's kicad-cli, in the environment of ``cad[kicad]``) and ordinary CAD exports;
no samples, IPC server or user state."""
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.python.support import kicode
from tests.python.support.engine_daemon import isolate

# Stable KiCad 9 syntax, a 40 x 30 mm board, 1.6 mm total stack including copper/mask at (10,20), one off-centre 2 mm hole.
BOARD = '''(kicad_pcb (version 20241229) (generator "pcbnew")
 (general (thickness 1.6)) (paper "A4")
 (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "B.SilkS" user "b.silkscreen")
 (37 "F.SilkS" user "f.silkscreen") (38 "B.Mask" user) (39 "F.Mask" user) (44 "Edge.Cuts" user) (49 "F.Fab" user))
 (setup (pad_to_mask_clearance 0))
 (gr_rect (start 10 20) (end 50 50) (stroke (width 0.05) (type default)) (fill none) (layer "Edge.Cuts"))
 (footprint "test:hole" (layer "F.Cu") (at 17 29)
  (property "Reference" "H1" (at 0 -3) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "hole" (at 0 3) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (attr board_only exclude_from_pos_files exclude_from_bom)
  (pad "" np_thru_hole circle (at 0 0) (size 2 2) (drill 2) (layers "*.Cu" "*.Mask")))
)'''

class NativeFiles(unittest.TestCase):
    def test_drc_step_mesh_and_same_path_edit(self):
        isolate(self.addCleanup)
        with tempfile.TemporaryDirectory(prefix="kicad-native-") as folder:
            root = Path(folder)
            board = root / "board.kicad_pcb"
            board.write_text(BOARD, encoding="utf-8")
            from cad.kicad_pcb import read as read_board
            from cad.engine.api import export
            import build123d as bd
            def drc(path):
                return kicode.call(self, "drc", path)
            cli = kicode.kicad_cli(self)
            original = board.read_bytes()
            result = drc(board)
            self.assertTrue(result["ok"], result)
            self.assertEqual(board.read_bytes(), original)
            self.assertEqual(read_board(board).part("H1").at, (17, 29))
            step = root / "board.step"
            env = kicode.environment(self, root / "kicad")  # no homes of the person's
            def exported():
                subprocess.run([str(cli), "pcb", "export", "step", "--force", "--board-only",
                    "--user-origin", "10x20mm", "-o", str(step), str(board)], env=env,
                    capture_output=True, text=True, check=True, timeout=90)
                return bd.import_step(step)
            # --board-only excludes the default 0.035 mm copper and 0.01 mm mask on each face.
            shape = exported()
            bounds = shape.bounding_box()
            for actual, expected in zip(bounds.size, (40, 30, 1.51)):
                self.assertAlmostEqual(actual, expected, places=4)
            self.assertAlmostEqual(bounds.min.X, 0, places=4)
            self.assertAlmostEqual(bounds.max.Y, 0, places=4)
            self.assertAlmostEqual(shape.volume, (40*30-math.pi)*1.51, places=3)
            cylinder = shape.faces().filter_by(bd.GeomType.CYLINDER)[0].bounding_box().center()
            self.assertAlmostEqual(cylinder.X, 7, places=4)
            self.assertAlmostEqual(cylinder.Y, -9, places=4)
            mesh = root / "board.stl"
            export(step, mesh, daemon=False)
            import struct
            data = mesh.read_bytes()
            count, = struct.unpack_from("<I", data, 80)
            self.assertEqual(len(data), 84 + count * 50)
            vertices = [struct.unpack_from("<3f", data, 84 + face * 50 + 12 + corner * 12)
                        for face in range(count) for corner in range(3)]
            for axis, expected in enumerate((40, 30, 1.51)):
                extent = max(v[axis] for v in vertices) - min(v[axis] for v in vertices)
                self.assertAlmostEqual(extent, expected, places=4)
            # The native file is editable independently; the same path must be reread on export.
            board.write_text(BOARD.replace('(end 50 50)', '(end 55 50)').replace('(at 17 29)', '(at 19 31)'), encoding="utf-8")
            self.assertEqual(read_board(board).part("H1").at, (19, 31))
            self.assertTrue(drc(board)["ok"])
            changed = exported()
            self.assertAlmostEqual(changed.bounding_box().size.X, 45, places=4)
            cylinder = changed.faces().filter_by(bd.GeomType.CYLINDER)[0].bounding_box().center()
            self.assertAlmostEqual(cylinder.X, 9, places=4)
            self.assertAlmostEqual(cylinder.Y, -11, places=4)
            self.assertAlmostEqual(changed.volume, (45*30-math.pi)*1.51, places=3)
            # KiCad 11 also writes its local project state (.kicad_prl) during export.
            self.assertLessEqual({p.suffix for p in root.iterdir() if p.is_file()},
                                 {'.kicad_pcb', '.kicad_prl', '.step', '.stl'})

    def test_drc_names_each_item_on_the_board_and_finds_its_copper_sliver(self):
        # KiCad's report names a finding's items by uuid and words, and a copper sliver by its layer alone: the
        # check adds what the board says each item is, and finds the sliver in the layer's saved copper.
        from tests.python.support.kicad_board import write_board

        spike = ('(gr_poly (pts (xy 24 4) (xy 34 4.25) (xy 24 4.5) (xy 23.5 6) (xy 23 6) (xy 22.5 5) (xy 22.5 3.5) '
                 '(xy 23 3)) (stroke (width 0) (type solid)) (fill yes) (layer "F.Cu"))')
        with tempfile.TemporaryDirectory(prefix="kicad-drc-") as folder:
            board = write_board(Path(folder))
            text = board.read_text(encoding="utf-8").rstrip()
            board.write_text(text[:-1] + spike + "\n)\n", encoding="utf-8")
            result = kicode.call(self, "drc", board)
        by_code = {finding["code"]: finding for finding in result["findings"]}
        sliver = by_code["copper_sliver"]
        self.assertEqual("(34, 4.25) mm", sliver["location"], sliver)
        [measured] = [found for found in result["measurements"]["drc"] if found["type"] == "copper_sliver"]
        self.assertEqual(([34.0, 4.25], "board", "F.Cu"), (measured["at"], measured["at_source"], measured["layer"]))
        unrouted = by_code["unconnected_items"]
        self.assertEqual({"#D1.2", "#R1.2"}, {item["ref"] for item in unrouted["items"]}, unrouted)
        self.assertTrue(all(item["kind"] == "pad" and item["net"] == "LED" and len(item["pos"]) == 2
                            for item in unrouted["items"]), unrouted)
