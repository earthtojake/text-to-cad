"""``cad mcp`` starts this release's server once, as ``cad server start`` does (``shim.start_server``), answers every
request within its bound while that start runs, and after it reaches the server running only where it is this
release's or a newer one's: none, or another release's, is said in cad's one line. Nothing is started for real."""

from __future__ import annotations

import io
import json
import sys
import threading
import types
import unittest
from unittest import mock

from cad.engine import client
from cad.engine.previous import version
from cad_mcp import shim
from cad_mcp.protocol import RequestContext, RpcError


def starting():
    """A stand-in for the transport's ``Holder`` whose start has not finished."""
    return types.SimpleNamespace(started=threading.Event(), ident="held", want=lambda: None)


def refuse(*args, **kwargs):
    raise AssertionError(f"nothing is sent: {args}")


class StartTest(unittest.TestCase):
    def test_the_start_is_cad_server_start_s_and_holds_later_requests_to_this_release_or_a_newer_one(self) -> None:
        """No uv tool ``cad`` installed and this process not run from uv's cache, or this process is the tool: this
        release's server, as ``cad server start`` (the install from uv's cache: ``test_shim_install``)."""
        for tool in (None, sys.prefix):
            with self.subTest(tool=tool), mock.patch.object(shim, "installed_tool", return_value=tool), \
                    mock.patch.object(shim, "from_uv_cache", return_value=False), \
                    mock.patch.object(shim, "installed", side_effect=AssertionError("the installed cad's start")), \
                    mock.patch.object(client, "AT_LEAST", None), mock.patch.object(client, "RELEASE", None), \
                    mock.patch.object(client, "start", return_value="started the cad server") as start:
                self.assertEqual(shim.start_server(), "started the cad server")
                self.assertEqual((client.AT_LEAST, client.RELEASE), (version(), None))
            start.assert_called_once_with()

    def test_a_server_of_another_release_found_later_is_said_in_cad_s_one_line(self) -> None:
        other = types.SimpleNamespace(release="0.0.1", close=lambda: None)
        with mock.patch.object(client, "RELEASE", "9.9.9"), mock.patch.object(client, "_connect", return_value=other), \
                mock.patch.object(client, "start", side_effect=AssertionError("never started")):
            answer = shim.Proxy().handle("tools/call", {"name": "cad_show"}, RequestContext(1, {}))
        self.assertTrue(answer["isError"])
        self.assertEqual(answer["content"][0]["text"], client._other("0.0.1", "9.9.9"))


class ArgumentsTest(unittest.TestCase):
    def test_an_old_startup_timeout_is_taken_and_ignored_and_nothing_else_is(self) -> None:
        with mock.patch.object(shim, "serve", return_value=0) as serve:
            for args in ([], ["--startup-timeout", "300"], ["--startup-timeout=12.5"]):
                with self.subTest(args=args):
                    self.assertEqual(shim.main(args), 0)
        self.assertEqual(serve.call_count, 3)
        for args in (["--startup-timeout"], ["--channel", "codex"], ["--other"]):
            with self.subTest(args=args), mock.patch.object(sys, "stderr", io.StringIO()) as err, \
                    mock.patch.object(shim, "serve", side_effect=AssertionError("never serves")):
                self.assertEqual(shim.main(args), 2)
            self.assertIn("unrecognized arguments", err.getvalue())


class StartingTest(unittest.TestCase):
    """While the start runs, every request is answered here within its bound, nothing reaching a server."""

    def test_every_request_is_answered_here_within_its_bound(self) -> None:
        holder = starting()
        told: list[str] = []
        announced = threading.Event()
        proxy = shim.Proxy(call=refuse, holder=holder)
        proxy.tell = lambda method, params: (told.append(method), len(told) == 2 and announced.set())
        with mock.patch.object(shim, "INITIALIZE_SECONDS", 0.01), mock.patch.object(shim, "READY_SECONDS", 0.01):
            greeting = proxy.handle("initialize", {"protocolVersion": "2025-06-18"}, RequestContext(0, {}))
            self.assertEqual(greeting["capabilities"], {"tools": {"listChanged": True}, "resources": {"listChanged": True}})
            self.assertEqual(greeting["serverInfo"], {"name": "cad", "title": "CAD", "version": version()})
            proxy.notify("notifications/initialized", {})
            proxy.notify("notifications/cancelled", {"requestId": 9})
            for method, answer in (("tools/list", {"tools": []}), ("resources/list", {"resources": []}),
                                   ("resources/templates/list", {"resourceTemplates": []}), ("ping", {}),
                                   ("tools/call", {"content": [{"type": "text", "text": shim.STARTING}],
                                                   "isError": True})):
                with self.subTest(method=method):
                    self.assertEqual(proxy.handle(method, {}, RequestContext(1, {})), answer)
            for method in ("resources/read", "completion/complete"):
                with self.subTest(method=method), self.assertRaises(RpcError) as refused:
                    proxy.handle(method, {"uri": "ui://cad/app"}, RequestContext(2, {}))
                self.assertEqual((refused.exception.code, refused.exception.message), (shim.UNAVAILABLE, shim.STARTING))
        self.assertEqual(told, [], "nothing is announced before the start is done")
        holder.started.set()
        self.assertTrue(announced.wait(30), told)
        self.assertEqual(told, ["notifications/resources/list_changed", "notifications/tools/list_changed"])

    def test_an_initialize_answered_here_opens_the_session_at_the_next_request(self) -> None:
        holder = starting()
        sent: list[str] = []

        def call(method, path, body=b"", headers=None):
            message = json.loads(body)
            sent.append(message.get("method"))
            if message.get("method") == "initialize":
                return 200, {"Mcp-Session-Id": "s1"}, json.dumps(
                    {"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": "2025-06-18"}}).encode()
            if "id" not in message:
                return 202, {}, b""
            return 200, {}, json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"tools": []}}).encode()

        proxy = shim.Proxy(call=call, holder=holder)
        with mock.patch.object(shim, "INITIALIZE_SECONDS", 0.01):
            proxy.handle("initialize", {"protocolVersion": "2025-06-18"}, RequestContext(1, {}))
        proxy.notify("notifications/initialized", {})
        self.assertEqual(sent, [], "nothing reaches the server before the start is done")
        holder.started.set()
        self.assertEqual(proxy.handle("tools/list", {}, RequestContext(2, {})), {"tools": []})
        self.assertEqual(sent, ["initialize", "notifications/initialized", "tools/list"])


class JoinedTest(unittest.TestCase):
    """A start whose own daemon lost to a start at the same moment says the server is already running, never that
    it started it (``client.start``)."""

    def start(self, process, pid):
        answered = types.SimpleNamespace(release=version(), close=lambda: None)
        with mock.patch.object(client, "make_way", return_value=None), \
                mock.patch.object(client.places, "make_engine_dir"), \
                mock.patch.object(client.places, "folder_refusal", return_value=None), \
                mock.patch.object(client, "_spawn", return_value=process), \
                mock.patch.object(client, "_connect", return_value=answered), \
                mock.patch.object(client, "request", return_value={"ok": True, "pid": pid}):
            return client.start()

    def test_a_start_that_joined_another_s_server_says_it_was_already_running(self) -> None:
        running = f"the cad server (cad {version()}) is already running"
        lost = types.SimpleNamespace(pid=10, poll=lambda: 0)  # found the lock taken, and left
        self.assertEqual(self.start(lost, 11), running)
        if not client.places.WINDOWS:  # still leaving as the other's server answers
            self.assertEqual(self.start(types.SimpleNamespace(pid=10, poll=lambda: None), 11), running)
        self.assertEqual(self.start(types.SimpleNamespace(pid=10, poll=lambda: None), 10),
                         f"started the cad server (cad {version()})")


class StoppingTest(unittest.TestCase):
    """Starts at the same moment that replace a server of another release both tell it to stop: the one whose
    connection the server, stopping already, closes unanswered finds it gone as asked, and carries on
    (``client.sweep``, through ``make_way``)."""

    def test_a_server_that_closes_the_connection_as_it_is_told_to_stop_is_waited_for_and_gone(self) -> None:
        import io

        endpoint = client.places.Endpoint(client.places.address(), client.places.lock_path())
        closing = client.Connection(io.BytesIO(b""), io.BytesIO())  # takes the stop, then its end of file: no answer
        # Asked first where it serves pages (``_note_pages``), it says nothing either: nothing is noted, and it stops.
        silent = client.Connection(io.BytesIO(b""), io.BytesIO())
        older = types.SimpleNamespace(release="0.0.1", close=lambda: None)
        with mock.patch.object(client.places, "endpoints", return_value=[endpoint]), \
                mock.patch.object(client, "_answering", return_value=True), \
                mock.patch.object(client, "_connect", side_effect=[older, silent, closing, None]), \
                mock.patch.object(client, "wait_gone", return_value=True) as waited, \
                mock.patch.object(client, "_remove_dead", return_value=[]), \
                mock.patch.object(client, "_sandboxed", return_value=False):
            self.assertIsNone(client.make_way())  # gone, and none answers after it: this start starts its own
        waited.assert_called_once_with(client.STOP_SECONDS, endpoint=endpoint, leave=version())


class UnansweredTest(unittest.TestCase):
    """A server that takes a request and never answers it: the host's initialize is still answered within its
    bound, greeted here, and a tool call ends with cad's line, never hanging. A healthy server's slow tool call is
    not cut by the door's bound."""

    def setUp(self) -> None:
        import os

        ends: list[int] = []
        self.addCleanup(lambda: [os.close(end) for end in ends])

        def silent(**_kw):
            read, write = os.pipe()  # nobody writes: an answer that never comes
            ends.append(write)
            return client.Connection(os.fdopen(read, "rb"), open(os.devnull, "wb"))

        self.silent = silent

    def test_a_request_past_its_time_limit_is_unanswered_and_one_within_it_is_answered(self) -> None:
        with mock.patch.object(client, "connect", side_effect=self.silent), self.assertRaises(client.Unanswered):
            client.request({"op": "http"}, timeout=0.2)
        with mock.patch.object(client, "_exchange", return_value={"ok": True}), \
                mock.patch.object(client, "connect", return_value=object()):
            self.assertEqual(client.request({"op": "http"}, timeout=5), {"ok": True})

    def test_initialize_is_answered_in_its_bound_and_a_tool_call_ends_with_cad_s_line(self) -> None:
        import time

        holder = starting()
        holder.started.set()
        proxy = shim.Proxy(holder=holder)
        with mock.patch.object(client, "connect", side_effect=self.silent), \
                mock.patch.object(shim, "ANSWER_SECONDS", 0.3), mock.patch.object(shim, "DOOR_SECONDS", 0.2):
            began = time.monotonic()
            greeting = proxy.handle("initialize", {"protocolVersion": "2025-06-18"}, RequestContext(1, {}))
            self.assertLess(time.monotonic() - began, 5)
            self.assertEqual(greeting["serverInfo"]["name"], "cad")
            answer = proxy.handle("tools/call", {"name": "cad_show"}, RequestContext(2, {}))
        self.assertEqual(answer, {"content": [{"type": "text", "text": "the cad server did not answer within 0.2 s"}],
                                  "isError": True})

    def test_a_slow_answer_of_a_healthy_server_s_endpoint_is_not_cut_by_the_door_s_bound(self) -> None:
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        class Slow(BaseHTTPRequestHandler):
            def do_POST(self):
                threading.Event().wait(0.5)  # past the door's bound
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        endpoint = {"url": f"http://127.0.0.1:{server.server_address[1]}", "token": "t"}
        with mock.patch.object(client, "request", return_value=endpoint) as asked, \
                mock.patch.object(shim, "DOOR_SECONDS", 0.2):
            self.assertEqual(shim.call("POST", "/mcp", b"{}")[0], 200)
        self.assertEqual(asked.call_args.kwargs, {"timeout": 0.2})


class DeclaredLogTest(unittest.TestCase):
    def test_what_the_app_declared_and_what_it_was_offered_go_to_the_app_s_log(self) -> None:
        # The line to read where an app shows no views: what it said at initialize, and the server's answer.
        def call(method, path, body=b"", headers=None, timeout=None):
            message = json.loads(body)
            if message.get("method") == "initialize":
                return 200, {"Mcp-Session-Id": "s1"}, json.dumps(
                    {"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": "2025-06-18"}}).encode()
            return 200, {}, json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"tools": []}}).encode()

        proxy = shim.Proxy(call=call, launcher=lambda: {"host": "gemini", "renders": None})
        ui = {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}
        with self.assertLogs("cad_mcp", "INFO") as logged:
            proxy.handle("initialize", {"clientInfo": {"name": "some-app", "version": "1.2"},
                                        "capabilities": {"extensions": ui}}, RequestContext(1, {}))
            proxy.handle("tools/list", {}, RequestContext(2, {}))
        self.assertEqual(logged.output, [
            'INFO:cad_mcp:some-app 1.2 declares io.modelcontextprotocol/ui {"mimeTypes": ["text/html;profile=mcp-app"]}; '
            "launched by gemini",
            "INFO:cad_mcp:the server offers this app no tools"])


if __name__ == "__main__":
    unittest.main()
