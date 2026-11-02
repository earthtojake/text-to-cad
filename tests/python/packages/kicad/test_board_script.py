"""A real ``@kicad_pcb`` round trip: KiCad's headless api-server, kipy and kicad-cli's STEP, on a nightly.

The board is the test's own (``tests/python/support/kicad_board.py``, in a KiCad nightly's format), written
into a temporary folder; the script reads it through kipy, the board is saved, and the ``@step`` stacked
on it is written from the saved board. Runs in the KiCad job, which installs the nightly and the kicad
extra; anywhere without them it says why it skips.
"""

import tempfile
import unittest
from pathlib import Path


class BoardScriptRoundTrip(unittest.TestCase):
    def test_a_board_script_reads_saves_and_exports_its_board(self):
        from cad.kicad._program import KicadMissingError, find_kicad_cli, kicad_version, version_tuple

        try:
            import kipy  # noqa: F401
        except ImportError:
            self.skipTest("the kicad extra (kicad-python) is not installed")
        try:
            cli = find_kicad_cli()
        except KicadMissingError as error:
            self.skipTest(str(error))
        if version_tuple(kicad_version(cli) or "0")[:2] < (10, 99):
            self.skipTest("kicad-cli api-server is a KiCad nightly's (10.99)")
        from cad import kicad_pcb, step
        from cad.kicad._session import run
        from tests.python.support.kicad_board import write_board

        with tempfile.TemporaryDirectory(prefix="kicad-script-") as folder:
            board = write_board(Path(folder))
            seen = []

            @step(str(Path(folder) / "STEP" / "board.step"))
            @kicad_pcb(str(board))
            def script(opened):
                seen.append(sorted(footprint.reference_field.text.value for footprint in opened.get_footprints()))

            ran = run(script, cli=cli)
            self.assertEqual([["D1", "J1", "R1"]], seen)
            self.assertEqual(board, ran.board)
            (step_file,) = ran.written
            self.assertTrue(step_file.read_text(encoding="utf-8", errors="replace").startswith("ISO-10303-21"))
            from cad.kicad_pcb import inspect

            self.assertEqual(3, inspect(board)["counts"]["parts"], "the saved board reads as it did")


if __name__ == "__main__":
    unittest.main()
