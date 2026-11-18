"""The stdio transport speaks only to the endpoint the server's door names at each call. A loopback port the
server has let go is anyone's, and the page token every call carries outlives the server: so the endpoint is read
from the door for every request (``shim.call``), and a listener on a freed port is sent neither a request nor the
token. Its hold (``shim.Holder``) starts the server once, at its own start, and never again."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from cad.engine import client
from cad_mcp import shim
from cad_mcp.protocol import RequestContext


class Listener:
    """A loopback MCP endpoint that records what it is sent. ``token`` answers as a server with one token would
    (sessions it opened, 404 for any other); with none it answers 404 to all."""

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
        self.addCleanup(self.first.close)
        self.names = self.first.endpoint()  # what the server's door says now; None: no server runs
        self.reads = 0

        def read(_message, timeout=None):
            self.reads += 1
            if self.names is None:
                raise client.NotRunning(client.NOT_RUNNING)
            return self.names

        patch = mock.patch.object(client, "request", side_effect=read)
        patch.start()
        self.addCleanup(patch.stop)
        self.proxy = shim.Proxy()
        self.proxy.handle("initialize", {"clientInfo": {"name": "test"}}, RequestContext(1, {}))
        self.proxy.notify("notifications/initialized", {})

    def move(self) -> tuple[Listener, int]:
        """The server restarts on another port with another token; its old port is free."""
        old = self.first.port
        self.first.close()
        second = Listener("second")
        self.addCleanup(second.close)
        self.names = second.endpoint()
        return second, old

    def ask(self, request_id: int) -> dict:
        return self.proxy.handle("tools/list", {}, RequestContext(request_id, {}))

    def test_every_call_reads_the_endpoint_from_the_door(self) -> None:
        before = self.reads
        self.ask(2)
        self.ask(3)
        self.assertEqual(self.reads, before + 2)

    def test_a_listener_on_the_freed_port_is_never_spoken_to_after_the_server_moved(self) -> None:
        second, old = self.move()
        squatter = Listener(None, port=old)
        self.addCleanup(squatter.close)
        self.assertEqual(self.ask(2), {"from": "second"})
        self.assertEqual(self.ask(3), {"from": "second"})
        self.assertEqual(squatter.seen, [], "no request, and so no token, reached the freed port")
        # The old session's request, refused by the new server; its new session; the request again; the next.
        self.assertEqual([method for method, _token in second.seen],
                         ["tools/list", "initialize", "notifications/initialized", "tools/list", "tools/list"])

    def test_a_server_gone_with_its_port_squatted_is_sent_nothing_and_the_call_says_so(self) -> None:
        # `cad server stop`, or a crash: the door answers no more and another process binds the port. The token it
        # would carry is the user's, valid at the server's next start.
        old = self.first.port
        self.first.close()
        squatter = Listener(None, port=old)
        self.addCleanup(squatter.close)
        self.names = None
        self.assertEqual(self.proxy.handle("tools/call", {"name": "cad_show"}, RequestContext(2, {})),
                         {"content": [{"type": "text", "text": client.NOT_RUNNING}], "isError": True})
        self.assertEqual(squatter.seen, [])

    def test_a_host_closing_after_the_server_stopped_starts_none(self) -> None:
        self.names = None
        with mock.patch.object(client, "start", side_effect=AssertionError("never started")):
            self.proxy.close()


class Held:
    """A hold the stood-in server keeps until ``gone`` is set."""

    def __init__(self, gone: threading.Event) -> None:
        self.gone, self.reader = gone, self

    def read(self, _size):
        self.gone.wait(10)
        return b""

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None


class HolderTest(unittest.TestCase):
    """The transport's start and hold (``shim.Holder``): the server started once, at its start, then held; after
    the server goes, held again only at the host's next request, and never started again -- a stop is obeyed.

    A holder's thread lives as long as its process, so one an earlier test made can still be on its way to
    ``client.hold`` while a later test's fake stands in for it: a fake that counts holds counts only its own
    holder's (by ``ident``) and answers any other as no server running."""

    def until(self, condition) -> None:
        for _ in range(1000):
            if condition():
                return
            threading.Event().wait(0.01)
        self.fail("the hold never came to it")

    def test_it_starts_the_server_once_then_holds_it_and_after_a_stop_starts_none(self) -> None:
        gone, holds, starts = threading.Event(), [], []
        attempts = threading.Semaphore(0)
        holder = shim.Holder()

        def hold(**said):
            if said.get("holder") != holder.ident:
                raise client.NotRunning(client.NOT_RUNNING)  # an earlier test's holder: not this one's to count
            holds.append(said["holder"])
            attempts.release()
            if len(holds) == 1:
                return Held(gone)
            raise client.NotRunning(client.NOT_RUNNING)

        with mock.patch.object(shim, "start_server", side_effect=lambda: starts.append(1) or "started"), \
                mock.patch.object(client, "hold", side_effect=hold):
            holder.start()
            self.assertTrue(holder.started.wait(10))
            self.assertTrue(attempts.acquire(timeout=10))
            self.until(lambda: holder.holding)
            gone.set()  # `cad server stop`
            self.until(lambda: not holder.holding)
            holder.want()  # the host's next request
            self.assertTrue(attempts.acquire(timeout=10))
        self.assertEqual((len(starts), holds), (1, [holder.ident, holder.ident]))
        self.assertTrue(holder.thread.is_alive())

    def test_a_start_that_fails_still_lets_every_request_be_answered(self) -> None:
        holder = shim.Holder()
        with mock.patch.object(shim, "start_server", side_effect=ConnectionError("the engine server did not start")), \
                mock.patch.object(client, "hold", side_effect=client.NotRunning(client.NOT_RUNNING)), \
                mock.patch.object(client, "request", side_effect=client.NotRunning(client.NOT_RUNNING)):
            holder.start()
            self.assertTrue(holder.started.wait(10))
            proxy = shim.Proxy(holder=holder)
            with self.assertRaises(shim.RpcError) as refused:
                proxy.handle("initialize", {"protocolVersion": "2025-06-18"}, RequestContext(1, {}))
            self.assertEqual(refused.exception.message, client.NOT_RUNNING)
            self.assertEqual(proxy.handle("tools/call", {"name": "cad_show"}, RequestContext(2, {})),
                             {"content": [{"type": "text", "text": client.NOT_RUNNING}], "isError": True})


if __name__ == "__main__":
    unittest.main()
