"""The stdio shim speaks only to the endpoint the engine's Unix socket names. A loopback port the
engine has let go is anyone's: once the engine moves, the shim reads its endpoint from the socket
again and never sends the host's initialize to a port held from an earlier call."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from cadgen.mcp.protocol import RequestContext
from cadgen.mcp.shim import Proxy
from cadgen.viewer import engine_client


class Listener:
    """A loopback MCP endpoint that records what it is sent. ``engine`` answers as an engine with
    one token would (sessions it opened, 404 for any other); otherwise it answers 404 to all."""

    def __init__(self, token: str | None, port: int = 0) -> None:
        self.token, self.seen, self.sessions = token, [], set()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                message = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.seen.append((message.get("method"), self.headers.get("Authorization")))
                status, headers, body = outer.answer(message, self.headers)
                self.send_response(status)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def answer(self, message, headers):
        if self.token is None or headers.get("Authorization") != f"Bearer {self.token}":
            return 404, {}, b"{}"
        if message.get("method") == "initialize":
            session = f"{self.token}-{len(self.sessions)}"
            self.sessions.add(session)
            body = {"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": "2025-06-18"}}
            return 200, {"Mcp-Session-Id": session}, json.dumps(body).encode()
        if headers.get("Mcp-Session-Id") not in self.sessions:
            return 404, {}, b"{}"
        if "id" not in message:
            return 202, {}, b""
        body = {"jsonrpc": "2.0", "id": message["id"], "result": {"from": self.token}}
        return 200, {}, json.dumps(body).encode()

    def endpoint(self) -> dict:
        return {"ok": True, "url": f"http://127.0.0.1:{self.port}", "port": self.port, "token": self.token}

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class ShimEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.first = Listener("first")
        self.names = self.first.endpoint()  # what the engine's socket says now
        self.reads = 0

        def read(_message):
            self.reads += 1
            return self.names

        patch = mock.patch.object(engine_client, "request", side_effect=read)
        patch.start()
        self.addCleanup(patch.stop)
        self.proxy = Proxy(engine_client.EngineClient())
        self.proxy.handle("initialize", {"clientInfo": {"name": "test"}}, RequestContext(1, {}))
        self.proxy.notify("notifications/initialized", {})

    def move(self) -> tuple[Listener, int]:
        """The engine restarts on another port with another token; its old port is free."""
        old = self.first.port
        self.first.close()
        second = Listener("second")
        self.addCleanup(second.close)
        self.names = second.endpoint()
        return second, old

    def ask(self, request_id: int) -> dict:
        return self.proxy.handle("tools/list", {}, RequestContext(request_id, {}))

    def test_a_listener_on_the_freed_port_is_never_spoken_to_after_the_engine_moved(self) -> None:
        second, old = self.move()
        self.assertEqual(self.ask(2), {"from": "second"})  # refused at the old port: the socket asked
        squatter = Listener(None, port=old)
        self.addCleanup(squatter.close)
        self.assertEqual(self.ask(3), {"from": "second"})
        self.assertEqual(squatter.seen, [])
        # The old session's request, refused by the new engine; its new session; the request again.
        self.assertEqual([method for method, _token in second.seen],
                         ["tools/list", "initialize", "notifications/initialized", "tools/list", "tools/list"])

    def test_the_hosts_initialize_goes_only_to_the_endpoint_the_socket_names_now(self) -> None:
        old = self.first.port
        self.first.close()
        squatter = Listener(None, port=old)  # takes the port before the shim's next call
        self.addCleanup(squatter.close)
        second = Listener("second")
        self.addCleanup(second.close)
        self.names = second.endpoint()
        self.assertEqual(self.ask(2), {"from": "second"})
        self.assertEqual(self.ask(3), {"from": "second"})
        self.assertEqual([method for method, _token in squatter.seen], ["tools/list"],
                         "one request it refused, and no initialize")
        self.assertNotIn("Bearer second", [token for _method, token in squatter.seen])
        self.assertEqual([method for method, _token in second.seen][:2], ["initialize", "notifications/initialized"])

    def test_an_initialize_reads_the_endpoint_from_the_socket_even_with_one_held(self) -> None:
        before = self.reads
        self.proxy.handle("initialize", {"clientInfo": {"name": "test"}}, RequestContext(9, {}))
        self.assertEqual(self.reads, before + 1)


if __name__ == "__main__":
    unittest.main()
