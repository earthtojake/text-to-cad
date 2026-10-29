"""The update card's one action (``cadgen/updates.py``): ``POST /__cad/update`` starts the engine's
self-update now (``auto_update.run_now``), answering JSON, and is no GET. There is nothing to restart:
no route asks the engine to hand over, and the notice is the same for every page and card."""

from __future__ import annotations

import http.client
import json
import threading
import unittest
from unittest import mock

from cadgen.viewer import handler as handler_module
from cadgen.viewer.http_app import create_cad_app


class UpdateRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_cad_app(host="127.0.0.1", port=0)
        server = handler_module.serve(self.app, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_address[1]

    def request(self, method: str, path: str, headers: dict | None = None) -> tuple[int, dict | None]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.request(method, path, body=b"{}" if method == "POST" else None,
                               headers={"x-cadgen-viewer": "1", "content-type": "application/json", **(headers or {})})
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data) if data else None
        finally:
            connection.close()

    def test_update_starts_the_self_update_and_answers_what_it_said(self) -> None:
        from cadgen._internal import auto_update

        answers = [{"started": True}, {"started": False, "reason": "an update is already under way"}]
        with mock.patch.object(auto_update, "run_now", side_effect=answers) as run_now:
            self.assertEqual(self.request("POST", "/__cad/update"), (200, {"started": True}))
            self.assertEqual(self.request("POST", "/__cad/update"),
                             (200, {"started": False, "reason": "an update is already under way"}))
        self.assertEqual(run_now.call_count, 2)
        self.assertEqual(self.request("GET", "/__cad/update")[0], 405)

    def test_there_is_no_restart_and_every_page_reads_one_notice(self) -> None:
        from cadgen import updates
        from cadgen.engine import client

        with mock.patch.object(client, "request") as request:
            self.assertEqual(self.request("POST", "/__cad/restart")[0], 404)
        self.assertEqual(request.call_count, 0)
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        connection.request("POST", "/__cad/update", body=b"{}")  # no guard header: a cross-site POST
        self.assertEqual(connection.getresponse().status, 403)
        connection.close()
        notices: list[tuple] = []
        with mock.patch.object(updates, "notice", lambda *args, **kwargs: notices.append((args, kwargs))), \
                mock.patch.object(updates, "refresh", lambda: None):
            self.request("GET", "/__cad/version")
            self.request("GET", "/__cad/version", {"origin": "https://claude.ai"})
        self.assertEqual(notices, [((), {}), ((), {})])


if __name__ == "__main__":
    unittest.main()
