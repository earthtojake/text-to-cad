"""KiCad's refill of a board's pours, on a copy, as the viewer's plot and the snapshot draw them: kicode's
headless api-server in the environment of ``cad[kicad]`` (``tests/python/support/kicode.py``), the person's
file never written, and the payload kept by the board's bytes."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support import kicode


class Refill(unittest.TestCase):
    def test_the_pours_are_kicads_refill_of_a_copy_and_the_payload_is_kept(self):
        from cad.engine.formats.kicad.poured import cached, key, payload
        from tests.python.support.kicad_board import write_board

        with tempfile.TemporaryDirectory(prefix="kicad-refill-") as folder, \
                mock.patch.dict(os.environ, {"CAD_CACHE_DIR": str(Path(folder) / "cache")}):
            board = write_board(Path(folder))
            saved = board.read_bytes()

            def refill(source: Path, out_dir: Path) -> Path:
                done = kicode.run_python(self, "import sys; from cad.kicad._refill import main; sys.exit(main())",
                                         str(source), str(out_dir))
                self.assertEqual(0, done.returncode, done.stderr)
                return Path(done.stdout.strip().splitlines()[-1])

            body, refilled = payload(board, refill=refill)
            self.assertTrue(refilled)
            self.assertEqual({"refilled": True}, json.loads(body)["pours"])
            self.assertEqual(saved, board.read_bytes(), "the person's file is never written")
            self.assertEqual(["blinky.kicad_pcb", "cache"], sorted(path.name for path in Path(folder).iterdir()))
            # Kept by the board's bytes: the next ask (a snapshot's render process) reads it without KiCad.
            self.assertEqual(body, cached(key(board)))
            self.assertEqual((body, True), payload(board))
            pours = [item for layer in json.loads(body)["sheets"][0]["layers"] for item in layer["items"]
                     if item.get("pour")]
            self.assertTrue(pours, "the GND pour is drawn from KiCad's fill")


if __name__ == "__main__":
    unittest.main()
