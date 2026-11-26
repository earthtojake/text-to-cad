"""What cad needs, told to the agent in the MCP channel (``cad_server.mcp.server.attention``): a global install behind
the newest release of its major whose update failed, cannot begin, is turned off or has not happened for days, and
each of the project's notices that applies; one line each, in the words the ``cad`` command says them, in the
initialize answer's instructions and once a session on the first result of a tool the agent calls. Nothing where all
is well. No test reaches the network: the feed is handed in."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cad_server
from cad_server import updates
from cad_server._internal import auto_update
from cad_server.mcp import server as mcp
from cad_server.mcp.protocol import RequestContext
from cad_server.mcp.ui import AppPage
from cad_server.viewer.recents import RecentStore

RECEIPT = '[tool]\nrequirements = [{ name = "cad" }]\nentrypoints = [{ name = "cad" }]\n'
NOTICE = {"id": "install-moved", "below": "0.2.0", "text": "cad now installs another way: run the install command again.",
          "url": "https://texttocad.dev/docs/install"}
BEHIND = "cad 0.2.0 is out and this is 0.1.0: `cad update` updates it"
T0 = 1_000_000.0


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.tool = self.tmp / "tools" / "cad"  # a uv tool's environment: a global install
        self.tool.mkdir(parents=True)
        (self.tool / "uv-receipt.toml").write_text(RECEIPT, encoding="utf-8")
        self.known = {"latest": "0.2.0", "lines": {"0": "0.2.0"}}
        for patch in (mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state), "CAD_CACHE_DIR": str(self.tmp / "cache"),
                                                   "CAD_ENGINE_DIR": str(self.tmp / "engine"), "DO_NOT_TRACK": "1"}),
                      mock.patch.object(sys, "prefix", str(self.tool)),
                      mock.patch.object(cad_server, "__version__", "0.1.0"),
                      mock.patch.object(auto_update, "find_uv", return_value="/bin/uv"),
                      mock.patch.object(updates, "checking", return_value=True),
                      mock.patch.object(updates, "feed", lambda fetch=False: self.known)):
            patch.start()
            self.addCleanup(patch.stop)

    def failed(self, cause: str = "disk_full") -> None:
        auto_update._keep(self.state / auto_update.RECORD, {
            "release": "0.2.0", "wanted": "0.2.0", "from": "0.1.0", "at": T0, "tries": 1, "installer": "uv",
            "outcome": "failed", "cause": cause, "detail": "x"})


class AttentionTest(Case):
    def test_nothing_where_all_is_well(self) -> None:
        self.known = {"latest": "0.1.0", "lines": {"0": "0.1.0"}}
        self.assertEqual(mcp.attention(T0), [], "current")
        self.known = {"latest": "0.2.0", "lines": {"0": "0.2.0"}}
        self.assertEqual(mcp.attention(T0), [], "a release out today: the update comes by itself")
        self.failed()
        with mock.patch.object(updates, "checking", return_value=False):
            self.assertEqual(mcp.attention(T0), [], "the check turned off for this process")
        with mock.patch.object(auto_update, "underway", return_value={"at": T0}):
            self.assertEqual(mcp.attention(T0), [], "an update underway")
        (self.tool / "uv-receipt.toml").unlink()
        self.assertEqual(mcp.attention(T0), [], "no global install: it never updates itself")
        with mock.patch.object(updates, "feed", side_effect=RuntimeError("x")):
            self.assertEqual(mcp.attention(T0), [], "never raises")

    def test_behind_for_days_the_stayed_behind_line_every_session(self) -> None:
        self.assertEqual(mcp.attention(T0), [], "first seen behind: noted")
        later = T0 + 3 * auto_update.DAY
        self.assertEqual(mcp.attention(later), [BEHIND])
        self.assertEqual(mcp.attention(later + 60), [BEHIND], "each session, though the command line said it today")

    def test_a_failed_or_blocked_update_at_once_with_its_advice(self) -> None:
        self.failed()
        self.assertEqual(mcp.attention(T0), [
            "this cad is 0.1.0 and has not been able to update itself to 0.2.0 (the disk is full): free room on the "
            "disk, then cad tries again by itself; `cad update` tries now"])
        (self.state / auto_update.RECORD).unlink()
        with mock.patch.object(auto_update, "pinned", return_value=True):
            self.assertEqual(mcp.attention(T0), [
                f"this cad is 0.1.0 and cannot update itself to 0.2.0 ({auto_update.in_words('pinned')}): to have cad "
                "update itself again, install it unpinned: `uv tool install --force cad`"])
        self.failed("packaged")
        self.assertIn("run `cad update` in a terminal", mcp.attention(T0)[0], "refused inside an app package")

    def test_automatic_updates_off_the_agent_asks_first(self) -> None:
        auto_update.change(False)
        self.assertEqual(mcp.attention(T0), [
            "cad 0.2.0 is out and this is 0.1.0, and automatic updates are off (`cad update auto`): ask the user before "
            "running `cad update`"])

    def test_each_notice_that_applies_as_the_viewer_gets_it(self) -> None:
        self.known = {"latest": "0.1.0", "lines": {"0": "0.1.0"}, "notices": [NOTICE]}
        said = [f"{NOTICE['text']} ({NOTICE['url']})"]
        self.assertEqual(mcp.attention(T0), said)
        self.assertEqual(mcp.attention(T0), said, "every session: no daily record is read or written")


class ChannelTest(Case):
    """The lines in the initialize answer's instructions, and once a session on the agent's first tool result."""

    def server(self) -> mcp.Server:
        page = self.tmp / "app"
        page.mkdir(exist_ok=True)
        (page / "shell.html").write_text("<!doctype html><title>CAD</title>", encoding="utf-8")
        return mcp.Server(page=AppPage(page), recents=RecentStore(self.state))

    def greet(self, server: mcp.Server) -> dict:
        launcher = {"host": "codex app-server", "renders": True, "command": "codex app-server"}
        params = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "codex-mcp-client"},
                  "_meta": {"dev.texttocad/transport": {"launcher": launcher}}}
        return server.handle("initialize", params, RequestContext(None, {}))

    def call(self, server: mcp.Server, name: str) -> list[str]:
        result = server.handle("tools/call", {"name": name, "arguments": {}}, RequestContext(1, {}))
        return [part["text"] for part in result["content"]]

    def test_said_in_the_instructions_and_once_on_the_agent_s_first_call(self) -> None:
        self.failed()
        server = self.server()
        block = "cad needs attention:\n- " + mcp.attention()[0]
        self.assertEqual(self.greet(server)["instructions"], mcp.INSTRUCTIONS + "\n\n" + block)
        with mock.patch.object(mcp.Server, "_tool_cad_view", lambda *_: mcp._text("seen")):
            self.assertEqual(self.call(server, "cad_view"), ["seen", block])
            self.assertEqual(self.call(server, "cad_view"), ["seen"], "once a session")
            self.assertEqual(self.call(self.server(), "cad_view"), ["seen", block], "a new session: again")

    def test_nothing_where_all_is_well(self) -> None:
        self.known = {"latest": "0.1.0", "lines": {"0": "0.1.0"}}
        server = self.server()
        self.assertEqual(self.greet(server)["instructions"], mcp.INSTRUCTIONS)
        with mock.patch.object(mcp.Server, "_tool_cad_view", lambda *_: mcp._text("seen")):
            self.assertEqual(self.call(server, "cad_view"), ["seen"])


if __name__ == "__main__":
    unittest.main()
