"""The Viewer's model library: the recents every CAD view shares, as one Viewer shows them."""

from __future__ import annotations

import base64
import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cadgen.viewer import handler as handler_module
from cadgen.viewer.http_app import create_cad_app
from cadgen.viewer.recents import RecentStore

STL = b"solid t\nendsolid t\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class LibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = self.tmp / "models"
        (self.root / "parts").mkdir(parents=True)
        (self.root / "parts" / "a.stl").write_bytes(STL)
        (self.tmp / "elsewhere.stl").write_bytes(STL)
        state = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.tmp / "state")})
        state.start()
        self.addCleanup(state.stop)
        app = create_cad_app(root=str(self.root), host="127.0.0.1", port=0)
        server = handler_module.serve(app, "127.0.0.1", 0)
        self.port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            headers = {"x-cadgen-viewer": "1", "content-type": "application/json"} if body is not None else {}
            connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def change(self, action: str, file: str, **extra) -> tuple[int, dict]:
        status, body = self.request("POST", "/__cad/recents", {"action": action, "file": file, **extra})
        return status, json.loads(body)

    def test_a_viewer_records_what_it_opens_and_shows_only_the_models_it_lists(self) -> None:
        RecentStore().opened(str(self.tmp / "elsewhere.stl"))  # opened in another view: not this Viewer's to show
        status, library = self.change("open", "parts/a.stl")
        shown = [(model["file"], model["folder"], model["path"]) for model in library["recents"]]
        self.assertEqual((status, shown), (200, [("parts/a.stl", "models/parts", str(self.root / "parts" / "a.stl"))]))
        self.assertEqual(json.loads(self.request("GET", "/__cad/recents")[1]), library)
        self.assertTrue(self.change("pin", "parts/a.stl")[1]["recents"][0]["pinned"])
        thumbnail = self.change("thumbnail", "parts/a.stl", png=base64.b64encode(PNG).decode("ascii"))[1]["recents"][0]["thumbnail"]
        self.assertEqual(self.request("GET", f"/__cad/recents/thumbnail?name={thumbnail}"), (200, PNG))
        self.assertEqual(self.change("remove", "parts/a.stl"), (200, {"recents": []}))
        # Once no model this Viewer lists has it, the picture is not this Viewer's to hand out.
        self.assertEqual(self.request("GET", f"/__cad/recents/thumbnail?name={thumbnail}")[0], 404)

    def test_a_viewer_records_only_models_in_its_folder(self) -> None:
        self.assertEqual(self.change("open", str(self.tmp / "elsewhere.stl"))[0], 403)
        (self.root / "notes.txt").write_text("x", encoding="utf-8")
        self.assertEqual(self.change("open", "notes.txt")[0], 400)
        self.assertEqual(self.change("thumbnail", "parts/a.stl", png=base64.b64encode(b"GIF89a").decode("ascii"))[0], 400)


if __name__ == "__main__":
    unittest.main()
