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


def _track(start: str, end: str, number: int) -> str:
    return (f'(segment (start {start}) (end {end}) (width 0.25) (layer "F.Cu") (net "LED") '
            f'(uuid "7a1c0000-0000-4000-8000-{number:012x}"))')


# The test board's one unrouted net, routed: with it the board passes DRC as it is written.
LED_ROUTE = (_track("20 23.175", "28 23.175", 0xa1) + _track("28 23.175", "35.825 23.175", 0xa2)
             + _track("35.825 23.175", "35.825 15", 0xa3))
# A spur off that route that ends 0.075 mm from the 1 mm VBUS track: one clearance error, and no other.
SPUR = _track("28 23.175", "28 15.7", 0xa4)
# The project's exclusion of that error, as KiCad 10.99 saves one: the rule, the two items by uuid, and the
# marker's place, the point of the first item (the VBUS track's centre line) nearest the second.
EXCLUSION = {"comment": "a probe point, meant", "marker": {
    "error_type": "DRCET_CLEARANCE", "layer": "BL_F_Cu", "position": {"x_nm": "28000000", "y_nm": "15000000"},
    "items": [{"value": "7a1c0000-0000-4000-8000-000000000001"}, {"value": "7a1c0000-0000-4000-8000-0000000000a4"}]}}


def routed(folder: Path, more: str = "", edit=lambda text: text) -> Path:
    """The test board in ``folder`` with its LED net routed (and ``more`` items, its text through ``edit``)."""
    from tests.python.support.kicad_board import write_board

    board = write_board(folder)
    text = edit(board.read_text(encoding="utf-8")).rstrip()
    board.write_text(text[:-1] + LED_ROUTE + more + "\n)\n", encoding="utf-8")
    return board


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

    def test_drc_judges_a_pour_as_kicad_refills_it_not_as_it_was_saved(self):
        # The board as written passes only refilled: KiCad calls J1.2 in its saved fill, which has no thermal
        # spokes, a starved thermal (an error). Then the pour's outline is notched round J1.2 and the fill saved
        # with the old outline left, covering the pad: stale, as an edit that does not refill leaves it. Read as
        # saved, that fill joins J1.2 to GND; KiCad's refill does not.
        notched = lambda text: text.replace("(xy 1 16) (xy 20 16) (xy 20 29) (xy 1 29)",
                                            "(xy 10 16) (xy 20 16) (xy 20 29) (xy 1 29) (xy 1 22) (xy 10 22)")
        with tempfile.TemporaryDirectory(prefix="kicad-drc-") as folder, tempfile.TemporaryDirectory(prefix="kicad-drc-") as other:
            passing = kicode.call(self, "drc", routed(Path(folder)))
            stale = routed(Path(other), edit=notched)
            saved = stale.read_bytes()
            result = kicode.call(self, "drc", stale)
            self.assertEqual(saved, stale.read_bytes(), "refilled in memory: the file keeps the fill it was saved with")
            self.assertEqual([stale.name], [path.name for path in Path(other).iterdir()], "its folder is as it was found")
        self.assertTrue(passing["ok"], passing)
        self.assertFalse(result["ok"], result)
        [unconnected] = [finding for finding in result["findings"] if finding["code"] == "unconnected_items"]
        self.assertIn("#J1.2", {item["ref"] for item in unconnected["items"]}, unconnected)

    def test_drc_holds_the_board_to_the_schematic_beside_it(self):
        # The routed board passes on its own (the test above); its schematic gives R1 another value and joins
        # no pins, and KiCad calls each difference a warning: the check fails the board on them.
        from tests.python.support.kicad_board import write_schematic

        with tempfile.TemporaryDirectory(prefix="kicad-drc-") as folder:
            board = routed(Path(folder))
            write_schematic(Path(folder))
            result = kicode.call(self, "drc", board)
        self.assertFalse(result["ok"], result)
        parity = [found for found in result["measurements"]["drc"] if found["check"] == "parity"]
        self.assertLessEqual({("footprint_symbol_mismatch", "#R1"), ("net_conflict", "#R1.1")},
                             {(found["type"], found["items"][0]["ref"]) for found in parity}, parity)
        self.assertEqual({"warning"}, {found["severity"] for found in parity})
        failing = {finding["code"] for finding in result["findings"] if finding["severity"] == "error"}
        self.assertEqual({found["type"] for found in parity}, failing, result["findings"])

    def test_drc_passes_a_violation_the_project_excludes_and_lists_it(self):
        import json

        with tempfile.TemporaryDirectory(prefix="kicad-drc-") as folder:
            board = routed(Path(folder), SPUR)
            project = board.with_suffix(".kicad_pro")

            def checked(exclusions):
                project.write_text(json.dumps({"board": {"design_settings": {"drc_exclusions": exclusions}},
                                               "meta": {"filename": project.name, "version": 3}}), encoding="utf-8")
                return kicode.call(self, "drc", board)

            failing, result = checked([]), checked([EXCLUSION])
        self.assertEqual((False, ["clearance"]), (failing["ok"], [finding["code"] for finding in failing["findings"]
                                                                   if finding["severity"] == "error"]), failing)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["summary"].endswith(", 1 excluded)"), result["summary"])
        [listed] = [finding for finding in result["findings"] if finding["code"] == "clearance"]
        self.assertEqual("info", listed["severity"])
        self.assertTrue(listed["message"].endswith("(excluded in the project: a probe point, meant)"), listed)
        [row] = [found for found in result["measurements"]["drc"] if found["type"] == "clearance"]
        self.assertEqual(("error", True, "a probe point, meant"), (row["severity"], row["excluded"], row["comment"]))
