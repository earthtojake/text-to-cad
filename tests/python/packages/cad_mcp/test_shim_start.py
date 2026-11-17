"""``cad mcp`` starts this release's server once, as ``cad server start`` does (``shim.start_server``), answers every
request within its bound while that start runs, and after it reaches the server running only where it is this
release's: none, or another release's, is said in cad's one line. Nothing is started for real."""

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
    def test_the_start_is_cad_server_start_s_and_holds_later_requests_to_this_release(self) -> None:
        with mock.patch.object(client, "RELEASE", None), \
                mock.patch.object(client, "start", return_value="started the cad server") as start:
            self.assertEqual(shim.start_server(), "started the cad server")
            self.assertEqual(client.RELEASE, version())
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


class DeclaredLogTest(unittest.TestCase):
    def test_what_the_app_declared_and_what_it_was_offered_go_to_the_app_s_log(self) -> None:
        # The line to read where an app shows no views: what it said at initialize, and the server's answer.
        def call(method, path, body=b"", headers=None):
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
