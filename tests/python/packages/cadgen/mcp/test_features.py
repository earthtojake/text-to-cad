"""The CAD app's Settings' Features (`cad_features`): read and changed by the page alone, and kept in the
person's settings, where the browser viewer reads the same choice."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen import features
from cadgen.analytics import UNCOUNTED, Recorder
from cadgen.mcp.protocol import RequestContext
from cadgen.mcp.server import Server
from cadgen.mcp.ui import AppPage
from cadgen.viewer.recents import RecentStore


class FeaturesToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.tmp / "state"), "DO_NOT_TRACK": "1"})
        environment.start()
        self.addCleanup(environment.stop)
        (self.tmp / "app").mkdir()

    def serve(self, client: str = "codex-mcp-client") -> Server:
        server = Server(launch_cwd=str(self.tmp), page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "state"),
                        analytics=Recorder(path=self.tmp / "analytics.json", send=lambda payload: True))
        server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": client, "version": "0.159.0"}}, None)
        return server

    def call(self, server: Server, arguments: dict | None = None) -> dict:
        context = RequestContext(1, {"threadId": "t"}, None)
        return server.handle("tools/call", {"name": "cad_features", "arguments": arguments or {}}, context)

    def test_the_page_reads_and_turns_off_quick_edit_once_for_every_cad_view(self) -> None:
        server = self.serve()
        tool = {tool["name"]: tool for tool in server.handle("tools/list", {}, None)["tools"]}["cad_features"]
        self.assertEqual(tool["_meta"], {"ui": {"visibility": ["app"]}})  # the page's alone, as cad_consent is
        self.assertEqual(self.call(server)["structuredContent"], {"quickEdit": True})
        self.assertEqual(self.call(server, {"quickEdit": False})["structuredContent"], {"quickEdit": False})
        # Another view's server process -- another thread's tab, the sidebar -- and the browser viewer read the same choice.
        self.assertEqual(self.call(self.serve())["structuredContent"], {"quickEdit": False})
        self.assertEqual(features.read(), {"quickEdit": False})
        settings = json.loads((self.tmp / "state" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["features"], {"quickEdit": False})
        # A choice that is not on or off, or of a feature there is not, is refused, and nothing is kept.
        self.assertTrue(self.call(server, {"quickEdit": "off"}).get("isError"))
        self.assertTrue(self.call(server, {"somethingElse": False}).get("isError"))
        self.assertEqual(features.read(), {"quickEdit": False})
        # Reading it is the page's plumbing, never counted as use.
        self.assertIn("cad_features", UNCOUNTED)

    def test_a_client_with_no_page_cannot_change_it(self) -> None:
        server = self.serve("some-terminal-agent")
        self.assertEqual(self.call(server, {"quickEdit": False})["structuredContent"], {"quickEdit": True})
        self.assertEqual(features.read(), {"quickEdit": True})


if __name__ == "__main__":
    unittest.main()
