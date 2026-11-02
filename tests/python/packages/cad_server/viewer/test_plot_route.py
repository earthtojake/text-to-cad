"""A KiCad board's ``plot`` (``GET /api/v1/documents/kicad_pcb/<id>/plot``) against a real launched
server, and the route's rules (``cad_server.viewer.plots``).

A board is opened by its absolute path, as every file is, and its plot is read from the file on
every request: an edit saved under the same path is the next answer, and nothing is cached. The
board is the test board (``tests/python/support/kicad_board.py``), written fresh into a temporary
folder.
"""

from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from tests.python.support.kicad_board import BOARD, write_board

from cad.engine.formats.kicad import PLOT_SCHEMA_VERSION
from cad_server.viewer import handler as handler_module
from cad_server.viewer.http_app import create_cad_app
from cad_server.viewer.plots import plot_payload_response


class PlotRules(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.board = write_board(self.folder)

    def test_a_board_answers_its_saved_file_again(self) -> None:
        status, body = plot_payload_response(str(self.board))
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual((payload["schemaVersion"], payload["kind"], payload["unrouted"]), (PLOT_SCHEMA_VERSION, "board", 1))
        self.assertEqual([part["ref"] for part in payload["board"]["parts"]], ["D1", "J1", "R1"])
        self.assertEqual(plot_payload_response(str(self.board)), (200, body))

    def test_what_the_route_will_not_take(self) -> None:
        self.assertEqual(plot_payload_response(str(self.folder / "other.kicad_pcb")), (404, {"error": "Not found"}))
        for ref, message in (("", r"absolute path of a \.kicad_pcb"), ("blinky.kicad_pcb", r"absolute"),
                             (str(self.folder / "part.step"), r"part\.step is not a \.kicad_pcb file")):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, message):
                plot_payload_response(ref)
        (self.folder / "broken.kicad_pcb").write_text("(kicad_sch)", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, r"broken\.kicad_pcb is not a KiCad board"):
            plot_payload_response(str(self.folder / "broken.kicad_pcb"))


class PlotRoute(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.board = write_board(self.folder)
        app = create_cad_app(host="127.0.0.1", port=0, dist_dir="")
        server = handler_module.serve(app, "127.0.0.1", 0)
        self.port = server.server_address[1]
        app.port = self.port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def request(self, method: str, target: str, body: dict | None = None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            conn.request(method, target, body=None if body is None else json.dumps(body).encode(),
                         headers={"x-cad-viewer": "1"} if method == "POST" else {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def opened(self, path: Path) -> str:
        status, _, body = self.request("POST", "/api/v1/documents", {"path": str(path)})
        self.assertEqual(status, 201, body[:400])
        reply = json.loads(body)
        self.assertEqual(reply["kind"], "kicad_pcb")
        return reply["api"]

    def test_a_board_opened_by_its_path_answers_its_plot_as_the_file_is_now(self) -> None:
        api = self.opened(self.board)
        status, headers, first = self.request("GET", f"{api}/plot")
        self.assertEqual(status, 200, first[:400])
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        self.assertEqual(json.loads(first)["kind"], "board")
        self.board.write_text(BOARD.replace('(width 1) (layer "F.Cu") (net "VBUS")',
                                            '(width 0.5) (layer "F.Cu") (net "VBUS")'), encoding="utf-8")
        status, _, changed = self.request("GET", f"{api}/plot")
        self.assertEqual(status, 200)
        self.assertNotEqual(first, changed)
        # Its routes are its plot and its source; another kind's read is a 404 naming them.
        status, _, body = self.request("GET", f"{api}/drawing")
        self.assertEqual((status, json.loads(body)["hint"]), (404, "a kicad_pcb's routes are plot, source"))

    def test_a_file_that_is_no_board_is_a_400_saying_why(self) -> None:
        broken = self.folder / "broken.kicad_pcb"
        broken.write_text("(kicad_sch)", encoding="utf-8")
        status, _, body = self.request("GET", f"{self.opened(broken)}/plot")
        self.assertEqual(status, 400, body[:400])
        self.assertIn("broken.kicad_pcb is not a KiCad board", json.loads(body)["error"])


if __name__ == "__main__":
    unittest.main()
