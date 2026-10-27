"""``GET /__cad/plot``'s decisions: what may be opened, and what the answer is.

The route is two rules over ``cadgen.plot``: a ref must be the absolute path of a
``.kicad_pcb`` (anything else is 400, a missing file 404), and a readable board answers
its payload's bytes, from the store once it has been read. The board is the test board
(``tests/python/support/kicad_board.py``), written fresh; the store is a temporary one.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.kicad_board import write_board
from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.plot import PLOT_SCHEMA_VERSION  # noqa: E402
from cadgen.viewer.plots import plot_payload_response  # noqa: E402


class PlotRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name)
        self.board = write_board(self.folder)
        self._env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.folder / "cache")})
        self._env.start()

    def tearDown(self) -> None:
        self._env.stop()
        self._tmp.cleanup()

    def test_a_board_answers_its_saved_file_again_without_cache(self) -> None:
        status, body = plot_payload_response(str(self.board))
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual((payload["schemaVersion"], payload["kind"], payload["unrouted"]), (PLOT_SCHEMA_VERSION, "board", 1))
        self.assertEqual([part["ref"] for part in payload["board"]["parts"]], ["D1", "J1", "R1"])
        self.assertEqual(plot_payload_response(str(self.board)), (200, body))
        self.assertFalse((self.folder / "cache").exists())

    def test_what_the_route_will_not_take(self) -> None:
        self.assertEqual(plot_payload_response(str(self.folder / "other.kicad_pcb")), (404, {"error": "Not found"}))
        for ref, message in (("", r"needs \?file="), ("blinky.kicad_pcb", r"absolute"), (str(self.folder / "part.step"), r"KiCad boards; part\.step is not a \.kicad_pcb file")):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, message):
                plot_payload_response(ref)
        (self.folder / "broken.kicad_pcb").write_text("(kicad_sch)", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, r"broken\.kicad_pcb is not a KiCad board"):
            plot_payload_response(str(self.folder / "broken.kicad_pcb"))


if __name__ == "__main__":
    unittest.main()
