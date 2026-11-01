"""The app menu's Language: read and changed through `/api/v1/settings`, kept in the person's settings,
where every CAD view -- another viewer, the CAD app -- reads the same choice."""

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


class ViewerLanguageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.tmp / "state")})
        environment.start()
        self.addCleanup(environment.stop)
        self.state = self.tmp / "state" / "settings.json"
        server = handler_module.serve(create_cad_app(host="127.0.0.1", port=0), "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_address[1]

    def request(self, method: str, body: object = None, *, guard: bool = True) -> tuple[int, object]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            headers = {"content-type": "application/json"} if body is not None else {}
            if body is not None and guard:
                headers["x-cadgen-viewer"] = "1"
            payload = None if body is None else {"language": body}
            connection.request(method, "/api/v1/settings", body=json.dumps(payload) if payload is not None else None, headers=headers)
            response = connection.getresponse()
            data = response.read()
            answer = json.loads(data) if data else None
            return response.status, answer["language"] if response.status == 200 else answer
        finally:
            connection.close()

    def test_automatic_until_chosen_and_kept_for_every_view(self) -> None:
        self.assertEqual(self.request("GET"), (200, {"locale": None}))
        self.assertEqual(self.request("PUT", {"locale": "fr"})[0], 400)
        self.assertEqual(self.request("PUT", {"locale": "ja"}), (200, {"locale": "ja"}))
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8"))["language"], {"locale": "ja"})
        self.assertEqual(self.request("PUT", {"locale": None}), (200, {"locale": None}))
        # A change without the guard header is a cross-site one: refused, and nothing changes.
        self.assertEqual(self.request("PUT", {"locale": "ja"}, guard=False)[0], 403)
        self.assertEqual(self.request("GET"), (200, {"locale": None}))


if __name__ == "__main__":
    unittest.main()
