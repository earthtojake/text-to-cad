"""Where the server the transport joins is older than the transport's own release (an agent app's plugin line runs the
release its skills were written for, and joins the installed cad's server, whatever its release), the agent is told
in the MCP channel, in the skills' own words: in the initialize answer's instructions, and once a session on the first
result of a tool the agent calls (``shim.older``). Nothing where the server is this release or newer."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from cad_mcp import shim
from cad_mcp.protocol import RequestContext


class Endpoint:
    """A server's MCP endpoint of release ``release``, answering every call with ``content`` and listing a tool for
    the agent and one for its views alone."""

    def __init__(self, release: str) -> None:
        self.release = release

    def __call__(self, method, path, body=b"", headers=None, timeout=None):
        message = json.loads(body)
        if message["method"] == "initialize":
            result = {"protocolVersion": "2025-06-18", "serverInfo": {"name": "cad", "version": self.release},
                      "instructions": "CAD shows models."}
            return 200, {"Mcp-Session-Id": "s1"}, json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}).encode()
        if "id" not in message:
            return 202, {}, b""
        if message["method"] == "tools/list":
            result = {"tools": [{"name": "cad_show"}, {"name": "cad_sync", "_meta": {"ui": {"visibility": ["app"]}}}]}
        else:
            result = {"content": [{"type": "text", "text": "shown"}]}
        return 200, {}, json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}).encode()


class OlderServerTest(unittest.TestCase):
    def proxy(self, release: str) -> shim.Proxy:
        patch = mock.patch.object(shim, "version", return_value="0.13.0")
        patch.start()
        self.addCleanup(patch.stop)
        proxy = shim.Proxy(call=Endpoint(release))
        self.initialized = proxy.handle("initialize", {"protocolVersion": "2025-06-18"}, RequestContext(1, {}))
        proxy.handle("tools/list", {}, RequestContext(2, {}))
        return proxy

    def texts(self, proxy: shim.Proxy, name: str) -> list[str]:
        result = proxy.handle("tools/call", {"name": name, "arguments": {}}, RequestContext(3, {}))
        return [part["text"] for part in result["content"]]

    def test_an_older_server_is_said_in_the_instructions_and_once_on_the_agent_s_first_call(self) -> None:
        line = "cad 0.12.4 is older than 0.13.0: run `cad update`"
        proxy = self.proxy("0.12.4")
        self.assertEqual(shim.older("0.12.4"), line)
        self.assertEqual(self.initialized["instructions"], "CAD shows models.\n\n" + line)
        self.assertEqual(self.texts(proxy, "cad_sync"), ["shown"], "a view's call: no agent reads it")
        self.assertEqual(self.texts(proxy, "cad_show"), ["shown", line])
        self.assertEqual(self.texts(proxy, "cad_show"), ["shown"], "once a session")

    def test_nothing_where_the_server_is_this_release_or_newer(self) -> None:
        for release in ("0.13.0", "0.13.1", "1.0.0", "not a release"):
            with self.subTest(release=release):
                proxy = self.proxy(release)
                self.assertIsNone(shim.older(release))
                self.assertEqual(self.initialized["instructions"], "CAD shows models.")
                self.assertEqual(self.texts(proxy, "cad_show"), ["shown"])
        self.assertIsNone(shim.older(None), "a server that named no release")


if __name__ == "__main__":
    unittest.main()
