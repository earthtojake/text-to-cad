"""What's new through `/api/v1/settings`: an updated device's view reads the release it runs and none
seen, and its dismissal, kept in the person's settings, holds for every CAD view."""

from __future__ import annotations

import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cad_server.viewer import handler as handler_module
from cad_server.viewer.http_app import create_cad_app


class ViewerWhatsNewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        state = self.tmp / "state"
        environment = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(state), "CAD_INSTALLATION_VERSION": "0.11.0-dev.0"})
        environment.start()
        self.addCleanup(environment.stop)
        # The release before's record, as an update leaves it: this device was updated.
        (state / "installations").mkdir(parents=True)
        (state / "installations" / "0.10.3.json").write_text(json.dumps(
            {"version": "0.10.3", "python": "/gone/python", "cad": "/gone/cad", "prefix": "/gone"}), encoding="utf-8")
        self.settings = state / "settings.json"
        server = handler_module.serve(create_cad_app(host="127.0.0.1", port=0), "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_address[1]

    def request(self, method: str, body: object = None) -> tuple[int, object]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            headers = {"content-type": "application/json", "x-cad-viewer": "1"} if body is not None else {}
            payload = None if body is None else json.dumps({"whats_new": body})
            connection.request(method, "/api/v1/settings", body=payload, headers=headers)
            response = connection.getresponse()
            answer = json.loads(response.read() or b"null")
            return response.status, answer["whats_new"] if response.status == 200 else answer
        finally:
            connection.close()

    def test_an_update_shows_its_release_until_dismissed_in_any_view(self) -> None:
        self.assertEqual(self.request("GET"), (200, {"seen": [], "release": "0.11"}))
        self.assertEqual(self.request("PUT", {"seen": ["v0.11"]})[0], 400)
        self.assertEqual(self.request("PUT", {"seen": ["0.11"], "release": "0.11"}), (200, {"seen": ["0.11"], "release": "0.11"}))
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8"))["whats_new"], {"seen": ["0.11"]})
        self.assertEqual(self.request("GET"), (200, {"seen": ["0.11"], "release": "0.11"}))


if __name__ == "__main__":
    unittest.main()
