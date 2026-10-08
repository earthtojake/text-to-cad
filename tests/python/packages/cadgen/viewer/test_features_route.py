"""The browser viewer's Settings' Features: read and changed through `/__cad/features`, kept in the
person's settings, where every CAD view -- another viewer, the CAD app -- reads the same choice."""

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

from cadgen import features
from cadgen.viewer import handler as handler_module
from cadgen.viewer.http_app import create_cad_app


class ViewerFeaturesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.tmp / "state")})
        environment.start()
        self.addCleanup(environment.stop)
        self.state = self.tmp / "state" / "settings.json"
        self.port = self.serve()

    def serve(self) -> int:
        server = handler_module.serve(create_cad_app(host="127.0.0.1", port=0), "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def request(self, method: str, body: object = None, *, port: int | None = None, guard: bool = True) -> tuple[int, object]:
        connection = http.client.HTTPConnection("127.0.0.1", port or self.port, timeout=10)
        try:
            headers = {"content-type": "application/json"} if body is not None else {}
            if body is not None and guard:
                headers["x-cadgen-viewer"] = "1"
            connection.request(method, "/__cad/features", body=json.dumps(body) if body is not None else None, headers=headers)
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data) if data else None
        finally:
            connection.close()

    def test_quick_edit_is_on_until_turned_off_and_the_choice_holds_for_every_cad_view(self) -> None:
        self.assertEqual(self.request("GET"), (200, {"quickEdit": True}))
        self.assertEqual(self.request("POST", {"quickEdit": False}), (200, {"quickEdit": False}))
        self.assertEqual(self.request("GET"), (200, {"quickEdit": False}))
        # In the person's settings, which another viewer -- another port, a reload, a restart -- and
        # the CAD app read alike.
        self.assertEqual(json.loads(self.state.read_text(encoding="utf-8"))["features"], {"quickEdit": False})
        self.assertEqual(self.request("GET", port=self.serve()), (200, {"quickEdit": False}))
        self.assertEqual(features.read(), {"quickEdit": False})
        self.assertEqual(self.request("POST", {"quickEdit": True})[1], {"quickEdit": True})

    def test_a_web_page_cannot_change_it_and_nothing_unknown_is_kept(self) -> None:
        self.assertEqual(self.request("POST", {"quickEdit": False}, guard=False)[0], 403)
        self.assertEqual(self.request("POST", {"quickEdit": "off"})[0], 400)
        self.assertEqual(self.request("POST", {"somethingElse": False})[0], 400)
        self.assertFalse(self.state.exists())
        self.assertEqual(self.request("GET"), (200, {"quickEdit": True}))


if __name__ == "__main__":
    unittest.main()
