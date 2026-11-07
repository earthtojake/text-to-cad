"""Real exports of a board by kicode's kicad-cli, run where the ``cad`` command runs them: in the environment
of ``cad[kicad]`` (``tests/python/support/kicode.py``). No samples, IPC server or user state."""
import tempfile
import unittest
from pathlib import Path

from cad.engine.formats.kicad import sexpr
from tests.python.support import kicode

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
        with tempfile.TemporaryDirectory(prefix="kicad-export-") as folder:
            root = Path(folder)
            board = root / "board.kicad_pcb"
            board.write_text(BOARD, encoding="utf-8")
            original = board.read_bytes()
            made = {to: [Path(path) for path in kicode.call(self, "export", board, to, root / "fab" / to)["written"]]
                    for to in ("gerbers", "drill", "pos", "step")}
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
    """The test board the reader, plot and command suites share is in the nightly's format (20260901), with its
    schematic: kicode's kicad-cli checks it and writes each of the newer exports of it."""

    @classmethod
    def setUpClass(cls):
        from tests.python.support.kicad_board import write_board, write_schematic

        cls._folder = tempfile.TemporaryDirectory(prefix="kicad-shared-")
        cls.root = Path(cls._folder.name)
        cls.board = write_board(cls.root)
        write_schematic(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._folder.cleanup()

    def exported(self, to):
        found = kicode.call(self, "export", self.board, to, self.root / "fab" / to)
        self.assertEqual(to, found["to"])
        written = [Path(path) for path in found["written"]]
        self.assertTrue(written and all(path.is_file() and path.parent.name == to for path in written), written)
        return written, found["warnings"]

    def test_a_nightly_checks_it(self):
        result = kicode.call(self, "drc", self.board)
        codes = {finding["code"] for finding in result["findings"]}
        # No .kicad_pro beside it: checked against KiCad's defaults, and said so.
        self.assertIn("no_project", codes, result)
        # KiCad read it (a refusal is one finding, `kicad_failed`) and found the unrouted LED net's ratsnest line.
        self.assertNotIn("kicad_failed", codes, result)
        self.assertIn("unconnected_items", codes, result)
        # Each finding as KiCad reported it: its items' uuids and positions in board millimetres.
        (unrouted,) = [found for found in result["measurements"]["drc"] if found["type"] == "unconnected_items"]
        self.assertTrue(all(item["uuid"] and len(item["pos"]) == 2 for item in unrouted["items"]), unrouted)

    def test_bom(self):
        import csv

        (bom,), _ = self.exported("bom")
        self.assertEqual("blinky-bom.csv", bom.name)
        with bom.open(newline="", encoding="utf-8") as file:
            rows = list(csv.reader(file))
        self.assertEqual(["Reference", "Value", "Footprint", "Quantity", "LCSC"], rows[0])
        self.assertIn(["R1", "1k", "Resistor_SMD:R_0603_1608Metric", "1", "C21190"], rows[1:])
        self.assertEqual({"D1", "J1", "R1"}, {row[0] for row in rows[1:]})

    def test_glb(self):
        (glb,), _ = self.exported("glb")
        self.assertEqual("blinky.glb", glb.name)
        self.assertEqual(b"glTF", glb.read_bytes()[:4])

    def test_odb(self):
        import zipfile

        (odb,), _ = self.exported("odb")
        self.assertEqual("blinky-odb.zip", odb.name)
        self.assertTrue(any(name.endswith("matrix/matrix") for name in zipfile.ZipFile(odb).namelist()))

    def test_ipc2581(self):
        (xml,), _ = self.exported("ipc2581")
        self.assertIn("<IPC-2581", xml.read_text(encoding="utf-8", errors="replace")[:2000])

    def test_pdf(self):
        written, _ = self.exported("pdf")
        self.assertEqual(["blinky-back.pdf", "blinky-front.pdf"], [path.name for path in written])
        self.assertTrue(all(path.read_bytes()[:5] == b"%PDF-" for path in written))

    def test_dxf(self):
        (dxf,), _ = self.exported("dxf")
        text = dxf.read_text(encoding="utf-8", errors="replace")
        self.assertIn("Edge.Cuts", text)
        # J1's two drilled holes beside the outline (a via is no hole an enclosure sees: not drawn).
        self.assertEqual(2, text.count("\nCIRCLE\n"))
        self.assertEqual([self.board.name, "blinky.kicad_sch", "fab"],
                         sorted(path.name for path in self.root.iterdir()), "the board's folder as found")


class StepWithoutModels(unittest.TestCase):
    """A part whose 3D model is missing, or only in VRML, leaves the STEP without that part's body: a
    warning naming it, not a failure, although kicad-cli exits 2 for it."""

    def test_missing_and_vrml_only_models_are_a_warning(self):
        with tempfile.TemporaryDirectory(prefix="kicad-step-models-") as folder:
            root = Path(folder)
            (root / "only.wrl").write_text("#VRML V2.0 utf8\nShape { geometry Box { size 1 1 1 } }\n", encoding="utf-8")
            r1 = '(attr smd)\n  (pad "1"'
            # The paths are written as KiCad writes a string: a Windows path's backslashes escaped.
            gone, vrml = (sexpr.quote(str(path)) for path in (root / "gone" / "missing.step", root / "only.wrl"))
            board = BOARD.replace(r1, f'(attr smd)\n  (model {gone})\n  (pad "1"', 1)
            board = board.replace('(attr board_only', f'(model {vrml})\n  (attr board_only', 1)
            self.assertEqual(board.count("(model "), 2)
            path = root / "board.kicad_pcb"
            path.write_text(board, encoding="utf-8")
            found = kicode.call(self, "export", path, "step", root / "fab")
            (step,) = [Path(written) for written in found["written"]]
            self.assertTrue(step.read_text(encoding="utf-8", errors="replace").startswith("ISO-10303-21"))
            said = " ".join(found["warnings"])
            self.assertIn("board.step is written", said)
            self.assertIn("R1", said)
            self.assertIn("VRML", said)

    def test_an_output_folder_that_cannot_be_made_is_the_exports_error(self):
        from cad_server._internal.integration_env import Failed

        with tempfile.TemporaryDirectory(prefix="kicad-export-out-") as folder:
            root = Path(folder)
            board = root / "board.kicad_pcb"
            board.write_text(BOARD, encoding="utf-8")
            (root / "taken").write_text("a file, not a folder", encoding="utf-8")
            with self.assertRaisesRegex(Failed, "cannot write the drill into"):
                kicode.call(self, "export", board, "drill", root / "taken")

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


class StepWithLibraryModels(unittest.TestCase):
    """A part whose 3D model names KiCad's 3D library: kicad-cli is given the library the board's view reads."""

    def test_library_models_are_read_where_the_board_view_reads_them(self):
        """A model named in KiCad's 3D library is in the STEP, read in the folders the board's 3D view reads
        (here two that ``CAD_KICAD_3DMODELS`` names, standing for KiCad's installed library), never where the
        caller's own ``KICAD10_3DMODEL_DIR`` points: any library variable, a KiCad 8 ``.wrl`` name read as
        the STEP beside it, each in whichever folder holds it. ``cad run kicad-cli`` reads the first folder."""
        import os
        import re
        import shutil
        from unittest import mock

        def parts(step):
            text = step.read_text(encoding="utf-8", errors="replace")
            return sorted(set(re.findall(r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\('[^']*','(R\d+)'", text)))

        with tempfile.TemporaryDirectory(prefix="kicad-step-library-") as folder:
            root = Path(folder)
            (root / "plain").mkdir()
            (root / "plain" / "board.kicad_pcb").write_text(BOARD, encoding="utf-8")
            (model,) = [Path(path) for path in
                        kicode.call(self, "export", root / "plain" / "board.kicad_pcb", "step", root / "plain")["written"]]
            first, second, elsewhere = root / "library", root / "more", root / "elsewhere"
            for library, name in ((first, "R_0603_1608Metric.step"), (first, "R_0805_2012Metric.step"),
                                  (second, "R_1206_3216Metric.step"), (elsewhere, "R_0603_1608Metric.step")):
                (library / "Resistor_SMD.3dshapes").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(model, library / "Resistor_SMD.3dshapes" / name)
            named = {"R1": "${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_1608Metric.step",
                     "R2": "${KICAD8_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0805_2012Metric.wrl",
                     "R3": "${KISYS3DMOD}/Resistor_SMD.3dshapes/R_1206_3216Metric.step"}
            footprints = "".join(f'''
 (footprint "test:r" (layer "F.Cu") (at {10 * index} 15)
  (property "Reference" "{ref}" (at 0 -2) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (attr smd)
  (model "{name}")
  (pad "1" smd rect (at -0.8 0) (size 0.9 1) (layers "F.Cu" "F.Mask")))''' for index, (ref, name) in enumerate(named.items(), 1))
            board = root / "board" / "board.kicad_pcb"
            board.parent.mkdir()
            board.write_text(BOARD.split(" (footprint", 1)[0] + footprints + "\n)\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"CAD_KICAD_3DMODELS": os.pathsep.join([str(first), str(second)]),
                                              "KICAD10_3DMODEL_DIR": str(elsewhere / "none")}):
                found = kicode.call(self, "export", board, "step", root / "fab")
                (step,) = [Path(path) for path in found["written"]]
                self.assertEqual((parts(step), found["warnings"]), (["R1", "R2", "R3"], []))
                run = kicode.run_python(self, "import sys; from cad.kicad._command import main; raise SystemExit(main())",
                                        "kicad-cli", "pcb", "export", "step", "--subst-models", "--force", "-o",
                                        str(root / "run.step"), str(board))
            self.assertIn("R1", parts(root / "run.step"), run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
