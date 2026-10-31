"""The stdio shim speaks only to the endpoint the engine's door names. A loopback port the
engine has let go is anyone's, and the page token every call carries outlives the engine: once
the engine that named the endpoint is gone (its door no longer answers, or is another's), the
shim reads its endpoint from the door again before it sends anything, so a listener on the
freed port is sent neither a request nor the token."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from cad_mcp.protocol import RequestContext
from cad_mcp.shim import Proxy
from cad_mcp import engine as engine_client


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
        self.names = self.first.endpoint()  # what the engine's door says now
        self.reads = 0
        self.starts: list[bool] = []  # each read's ``start``: whether it could start an engine

        def read(_message, start=True):
            self.reads += 1
            self.starts.append(start)
            return self.names if self.names is not None or start else None

        patch = mock.patch.object(engine_client, "request", side_effect=read)
        patch.start()
        self.addCleanup(patch.stop)
        # The door's identity (``engine_client._door``): one per engine run, None with none.
        self.door: object = object()
        doors = mock.patch.object(engine_client, "_door", side_effect=lambda _address=None: self.door)
        doors.start()
        self.addCleanup(doors.stop)
        self.proxy = Proxy(engine_client.EngineClient())
        self.proxy.handle("initialize", {"clientInfo": {"name": "test"}}, RequestContext(1, {}))
        self.proxy.notify("notifications/initialized", {})

    def move(self) -> tuple[Listener, int]:
        """The engine restarts on another port with another token; its old port is free."""
        old = self.first.port
        self.first.close()
        second = Listener("second")
        self.addCleanup(second.close)
        self.names, self.door = second.endpoint(), object()
        return second, old

    def ask(self, request_id: int) -> dict:
        return self.proxy.handle("tools/list", {}, RequestContext(request_id, {}))

    def test_a_listener_on_the_freed_port_is_never_spoken_to_after_the_engine_moved(self) -> None:
        second, old = self.move()
        self.assertEqual(self.ask(2), {"from": "second"})  # refused at the old port: the door asked
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
        self.names, self.door = second.endpoint(), object()
        self.assertEqual(self.ask(2), {"from": "second"})
        self.assertEqual(self.ask(3), {"from": "second"})
        self.assertEqual(squatter.seen, [], "no request, and so no token, reached the freed port")
        self.assertEqual([method for method, _token in second.seen][:2], ["tools/list", "initialize"])

    def test_an_engine_gone_with_its_port_squatted_is_sent_nothing(self) -> None:
        # `cadgen stop`, or a crash: the door answers no more and another process binds the port.
        # The token it would carry is the user's, valid at the engine's next start.
        old = self.first.port
        self.first.close()
        squatter = Listener(None, port=old)
        self.addCleanup(squatter.close)
        self.names, self.door = None, None
        with self.assertRaises(Exception):
            self.ask(2)
        self.assertEqual(squatter.seen, [])

    def test_a_host_closing_after_the_engine_stopped_starts_none(self) -> None:
        self.first.close()  # `cadgen stop`: nothing listens, and the socket names no engine
        self.names, self.starts = None, []
        self.proxy.close()
        self.assertEqual(self.starts, [False], "the session's end is told to an engine, never one started to hear it")

    def test_an_initialize_reads_the_endpoint_from_the_socket_even_with_one_held(self) -> None:
        before = self.reads
        self.proxy.handle("initialize", {"clientInfo": {"name": "test"}}, RequestContext(9, {}))
        self.assertEqual(self.reads, before + 1)


if __name__ == "__main__":
    unittest.main()


class HolderTest(unittest.TestCase):
    """The server's hold on the engine (``shim.Holder``): taken at its start, and after the engine
    goes held again only at the host's next request -- a stop is obeyed."""

    def test_a_request_while_the_hold_is_taken_never_holds_again_after_a_stop(self) -> None:
        from cad_mcp.shim import Holder

        gone, taking, calls = threading.Event(), threading.Event(), []

        class Held:
            def __init__(self) -> None:
                self.reader = self

            def read(self, _size):
                gone.wait(10)
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return None

        def hold(host=None, holder=None):
            calls.append(host)
            taking.wait(10)  # the engine starting: the host's initialize arrives meanwhile
            return Held()

        holder = Holder()
        with mock.patch("cad_mcp.shim.hold", hold):
            holder.start()
            holder.want()  # Proxy._send, while the first hold starts the engine
            taking.set()
            self.assertTrue(holder.tried.wait(10))
            # The request was served by the hold it waited for: none is left wanting another, which
            # the engine's going (cadgen stop) would take as a request and start an engine for.
            self.assertFalse(holder.wanted.is_set())
            gone.set()
        self.assertEqual(len(calls), 1)

    def test_a_hold_that_fails_unexpectedly_is_tried_again_at_the_next_request(self) -> None:
        calls = []

        def hold(host=None, holder=None):
            calls.append(host)
            raise RuntimeError("an answer of no shape")

        from cad_mcp.shim import Holder

        holder = Holder()
        with mock.patch("cad_mcp.shim.hold", hold):
            holder.start()
            self.assertTrue(holder.tried.wait(10), "the server's exit never waits a minute on it")
            holder.want()
            for _ in range(500):
                if len(calls) == 2:
                    break
                threading.Event().wait(0.01)
        self.assertEqual(len(calls), 2)
        self.assertTrue(holder.thread.is_alive())
