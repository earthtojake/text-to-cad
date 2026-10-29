"""The stdio shim speaks only to the endpoint the engine's door names. A loopback port the
engine has let go is anyone's, and the page token every call carries outlives the engine: once
the engine that named the endpoint is gone (its door no longer answers, or is another's), the
shim reads its endpoint from the door again before it sends anything, so a listener on the
freed port is sent neither a request nor the token. Its bootstrap retires an older release's
engine on the port once it is idle, and says so once on its log."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
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
        from cadgen.mcp.shim import Holder

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

        def hold(host=None, holder=None, start=False, told=None):
            self.assertTrue(start, 'the MCP bootstrap explicitly starts its engine')
            calls.append(host)
            taking.wait(10)  # the engine starting: the host's initialize arrives meanwhile
            return Held()

        holder = Holder()
        with mock.patch("cadgen.engine.client.hold", hold):
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

        def hold(host=None, holder=None, start=False, told=None):
            self.assertTrue(start, 'the MCP bootstrap explicitly starts its engine')
            calls.append(host)
            raise RuntimeError("an answer of no shape")

        from cadgen.mcp.shim import Holder

        holder = Holder()
        with mock.patch("cadgen.engine.client.hold", hold):
            holder.start()
            self.assertTrue(holder.tried.wait(10), "the server's exit never waits a minute on it")
            holder.want()
            for _ in range(500):
                if len(calls) == 2:
                    break
                threading.Event().wait(0.01)
        self.assertEqual(len(calls), 2)
        self.assertTrue(holder.thread.is_alive())

    def test_a_bootstrap_that_could_not_hold_the_engine_tells_the_host_why(self) -> None:
        from cadgen.mcp.protocol import RpcError
        from cadgen.mcp.shim import Holder

        why = ("the engine server did not start: port 3245 is held by cadgen 0.8.1's engine (pid 4242): run "
               "`cadgen stop` to stop it, then start again")

        def hold(host=None, holder=None, start=False, told=None):
            raise ConnectionError(why)

        class Unreached:
            def call(self, *_args, **_kwargs):
                raise ConnectionError("no cadgen server is running on port 3245")

        holder = Holder()
        with mock.patch("cadgen.engine.client.hold", hold):
            holder.start()
            self.assertTrue(holder.tried.wait(10))
            with self.assertRaises(RpcError) as said:
                Proxy(Unreached(), holder=holder).handle("initialize", {}, RequestContext(1, {}))
        self.assertEqual(said.exception.message, why, "the host's initialize says why, not only that none answers")


@unittest.skipIf(os.name == "nt", "an older engine's door is a POSIX engine's")
class BootstrapConvergesTest(unittest.TestCase):
    """The MCP bootstrap (``Holder``: ``hold(start=True)``) finds an older release's engine on its port
    (0.8.1's, protocol 3): once it is idle it is retired through its own door, said once on the
    server's log, and the engine started in its place is held; in use, it is never displaced and the
    host is told what uses it."""

    def setUp(self) -> None:
        from tests.python.support import engine_daemon

        self.engine = Path(tempfile.mkdtemp(prefix="eng-", dir="/tmp")).resolve()
        self.addCleanup(shutil.rmtree, self.engine, True)
        folder = Path(tempfile.mkdtemp(prefix="cadgen-shim-"))
        self.addCleanup(shutil.rmtree, folder, True)
        self.port = engine_daemon.free_port()
        patch = mock.patch.dict(os.environ, {
            "CADGEN_ENGINE_DIR": str(self.engine), "CADGEN_PORT": str(self.port), "CADGEN_ENGINE_STANDBY": "0",
            "CADGEN_STATE_DIR": str(folder / "state"), "CADGEN_CACHE_DIR": str(folder / "cache")})
        patch.start()
        self.addCleanup(patch.stop)

    def older(self, **options):
        from tests.python.packages.cadgen.engine.test_daemon import OlderEngine

        engine = OlderEngine(self.engine, "111111111111", self.port, **options)
        self.addCleanup(engine.close)
        return engine

    def stop(self) -> None:
        from cadgen.engine import client

        if client.request({"op": "stop"}, start=False) is not None:
            self.assertTrue(client.wait_gone())

    def test_an_idle_older_engine_is_retired_said_once_and_its_successor_held(self) -> None:
        from cadgen.engine import client, daemon
        from cadgen.mcp.shim import Holder

        older = self.older()
        holder = Holder(host=lambda: "test-host")
        self.addCleanup(self.stop)
        with self.assertLogs("cadgen.mcp", level="INFO") as logged:
            holder.start()
            self.assertTrue(holder.tried.wait(120), "the bootstrap held an engine, or said why not")
        self.assertIsNone(holder.failure)
        self.assertTrue(older.gone.is_set(), "stopped through its own door")
        retired = [line for line in logged.output if "retired" in line]
        self.assertEqual(retired, [f"INFO:cadgen.mcp:retired cadgen 0.8.1's engine (pid 4242) for {daemon.installation()}"])
        status = client.request({"op": "status"})
        self.assertEqual((status["holders"], status["hosts"], status["serving"]["port"]), (1, {"test-host": 1}, self.port))

    def test_an_older_engine_in_use_is_never_displaced_and_the_host_is_told_what_uses_it(self) -> None:
        from cadgen.engine import client
        from cadgen.mcp.shim import Holder

        older = self.older(uses={"watched": 1})
        holder = Holder()
        with mock.patch.object(client, "RETIRE_SECONDS", 0), mock.patch.object(client, "_start") as start:
            holder.start()
            self.assertTrue(holder.tried.wait(60))
        start.assert_not_called()
        self.assertEqual(holder.failure, f"port {self.port} is held by cadgen 0.8.1's engine (pid 4242), still in use by "
                                         f"1 open page: close that page or run `cadgen stop --port {self.port}`")
        self.assertFalse(older.gone.is_set())
        self.assertEqual({request["op"] for request in older.requests}, {"status"})
