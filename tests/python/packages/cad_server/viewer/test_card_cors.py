"""The engine's one cross-origin allowance: a CAD card whose host carries none of its calls back
(``apps/mcp``'s direct transport) reads the engine from its sandbox's origin with the link its
launch carries, as a Bearer credential. That request, and its preflight, are answered with the card's
origin; nothing else is -- not the cookie, not a link in the URL, not the user's token, not ``/mcp``."""
from __future__ import annotations

import http.client
import unittest

from cad_server.viewer.engine_app import sign

CARD = "https://4f2a.claudemcpcontent.com"


class CardCorsTest(unittest.TestCase):
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

    def ask(self, method: str, path: str, headers: dict | None = None) -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=20)
        try:
            conn.request(method, path, headers={"Host": f"127.0.0.1:{self.server.port}", **(headers or {})})
            response = conn.getresponse()
            response.read()
            return response.status, {name.lower(): value for name, value in response.getheaders()}
        finally:
            conn.close()

    def cors(self, headers: dict) -> dict:
        return {name: value for name, value in headers.items() if name.startswith("access-control-")}

    def test_a_cards_link_bearing_request_and_its_preflight_are_answered_for_its_origin_alone(self) -> None:
        link = self.app.link()
        status, headers = self.ask("OPTIONS", "/api/v1/server", {
            "Origin": CARD, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization",
            "Access-Control-Request-Private-Network": "true"})
        self.assertEqual(status, 204)
        self.assertEqual(self.cors(headers), {
            "access-control-allow-origin": CARD, "access-control-allow-methods": "GET, HEAD, POST, PUT, PATCH, DELETE",
            "access-control-allow-headers": "authorization, content-type, range, if-range, x-cadgen-viewer",
            "access-control-max-age": "600", "access-control-allow-private-network": "true"})
        self.assertEqual(headers["vary"], "Origin")
        # A change's preflight -- a POST, a PUT, a PATCH, a DELETE -- with the guard header and a JSON body's type.
        for method, path in (("POST", "/api/v1/documents"), ("PUT", "/api/v1/settings"), ("PATCH", "/api/v1/documents"),
                             ("DELETE", "/api/v1/documents/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab")):
            with self.subTest(method=method):
                status, _ = self.ask("OPTIONS", path, {
                    "Origin": CARD, "Access-Control-Request-Method": method,
                    "Access-Control-Request-Headers": "authorization,content-type,x-cadgen-viewer"})
                self.assertEqual(status, 204)
        for origin in (CARD, "null"):  # an opaque sandbox's origin is "null", echoed as such
            with self.subTest(origin=origin):
                status, headers = self.ask("GET", "/api/v1/server", {"Origin": origin, "Authorization": f"Bearer {link}"})
                self.assertEqual(status, 200)
                self.assertEqual(self.cors(headers), {"access-control-allow-origin": origin,
                                                      "access-control-expose-headers": "content-length, content-range, etag"})
                self.assertNotIn("set-cookie", headers)

    def test_every_other_cross_origin_request_or_preflight_gets_no_allowance(self) -> None:
        link = self.app.link()
        preflights = {
            "no credential header asked": {"Origin": CARD, "Access-Control-Request-Method": "GET"},
            "a header outside the card's": {"Origin": CARD, "Access-Control-Request-Method": "GET",
                                            "Access-Control-Request-Headers": "authorization, x-other"},
            "a method outside the card's": {"Origin": CARD, "Access-Control-Request-Method": "TRACE",
                                            "Access-Control-Request-Headers": "authorization"},
            "no origin": {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"},
            "a foreign Host": {"Host": "attacker.example", "Origin": CARD, "Access-Control-Request-Method": "GET",
                               "Access-Control-Request-Headers": "authorization"},
        }
        for name, headers in preflights.items():
            with self.subTest(preflight=name):
                status, answer = self.ask("OPTIONS", "/api/v1/server", headers)
                self.assertEqual((status, self.cors(answer)), (405, {}))
                # The methods the engine serves, as every other 405 of it names them.
                self.assertEqual(answer["allow"], "GET, HEAD, POST, PUT, PATCH, DELETE")
        status, answer = self.ask("OPTIONS", "/mcp", {"Origin": CARD, "Access-Control-Request-Method": "POST",
                                                      "Access-Control-Request-Headers": "authorization, content-type"})
        self.assertEqual((status, self.cors(answer)), (405, {}))
        requests = {
            # The user's token is a native client's, which needs no CORS.
            "the user's token": ("/api/v1/server", {"Origin": CARD, "Authorization": f"Bearer {self.app.token}"}),
            # A link in the URL rides by itself, wherever the URL goes: no CORS for it.
            "a link in the URL": (f"/api/v1/server?token={link}", {"Origin": CARD}),
            "a link past its day": ("/api/v1/server", {"Origin": CARD, "Authorization": f"Bearer {sign(self.app.token, 'link', -60)}"}),
            "a session cookie": ("/api/v1/server", {"Origin": CARD, "Sec-Fetch-Site": "cross-site",
                                                   "Cookie": f"{self.app.cookie}={sign(self.app.token, 'session', 600)}"}),
            "a link with no origin": ("/api/v1/server", {"Authorization": f"Bearer {link}"}),
            "MCP": ("/mcp", {"Origin": CARD, "Authorization": f"Bearer {link}"}),
        }
        for name, (path, headers) in requests.items():
            with self.subTest(request=name):
                status, answer = self.ask("GET", path, headers)
                self.assertEqual(self.cors(answer), {}, status)


def setUpModule() -> None:
    # The registry and cache of the engine this module starts are its own, never the developer's.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
