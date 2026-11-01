"""0.8's reload probe, answered through 0.10 and gone in 0.11: a CAD Viewer tab of 0.8 left open across
the upgrade asks ``GET /__cad/server`` (and ``/__cad/version`` once it started an update), and the
engine answers as ``GET /api/v1/server`` does, behind the same gate, so the tab sees another ``pid``,
``identityToken`` and ``release`` and reloads itself. Nothing else under ``/__cad/`` is a route."""
from __future__ import annotations

import http.client
import json
import unittest

from cad_server.viewer.engine_app import sign

KEYS = ("pid", "identityToken", "release", "instance", "notice", "update")


class ReloadProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from cad_server._internal.engine_host import http_factory
        from cad.engine.serve import Server

        cls.server = Server(isolated=True, mesh_mode="inline", http_factory=http_factory)
        cls.server.start()
        cls.app = cls.server.http.app

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def ask(self, path: str, headers: dict | None = None) -> tuple[int, str, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=20)
        try:
            conn.request("GET", path, headers={"Host": f"127.0.0.1:{self.server.port}", **(headers or {})})
            response = conn.getresponse()
            return response.status, response.getheader("content-type") or "", response.read()
        finally:
            conn.close()

    def test_the_probe_answers_as_the_server_route_does_behind_the_viewers_gate(self) -> None:
        session = {"Cookie": f"{self.app.cookie}={sign(self.app.token, 'session', 600)}", "Sec-Fetch-Site": "same-origin"}
        token = {"Authorization": f"Bearer {self.app.token}"}
        status, _, body = self.ask("/api/v1/server", token)
        self.assertEqual(status, 200)
        expected = json.loads(body)
        for path in ("/__cad/server", "/__cad/version"):
            for name, headers in (("the page's session", session), ("the token", token)):
                with self.subTest(path=path, credential=name):
                    status, kind, body = self.ask(path, headers)
                    self.assertEqual((status, kind.split(";")[0]), (200, "application/json"))
                    answer = json.loads(body)
                    for key in KEYS:
                        self.assertIn(key, answer)
                    self.assertEqual({key: answer[key] for key in ("pid", "identityToken", "release", "instance")},
                                     {key: expected[key] for key in ("pid", "identityToken", "release", "instance")})
            with self.subTest(path=path, credential=None):
                status, _, body = self.ask(path)
                self.assertEqual((status, json.loads(body)), (403, {"error": "engine token required"}))

    def test_nothing_else_under_the_old_prefix_answers_json(self) -> None:
        status, kind, _ = self.ask("/__cad/other", {"Authorization": f"Bearer {self.app.token}"})
        self.assertNotEqual(kind.split(";")[0], "application/json", status)


def setUpModule() -> None:
    # The registry and cache of the engine this module starts are its own, never the developer's.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
