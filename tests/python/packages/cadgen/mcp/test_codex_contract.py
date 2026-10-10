"""What Codex is served, pinned: other hosts' support must not change a byte of it.

The server answers Codex (its client names itself ``codex-mcp-client``) with tab surfaces the agent
opens once and then drives. ``codex_contract.json`` records that conversation -- initialize, the
catalog, the resource, and the launches each surface returns -- with the page's build and this run's
paths replaced by placeholders. A change to Codex's side has to change that file on purpose.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen.mcp.protocol import RequestContext
from cadgen.viewer.recents import RecentStore
from cadgen.mcp.server import Server
from cadgen.mcp.ui import AppPage

CONTRACT = Path(__file__).with_name("codex_contract.json")
CODEX_INITIALIZE = {"protocolVersion": "2025-06-18",
                    "capabilities": {"elicitation": {"form": {}, "url": {}}, "experimental": {"codex/auth-change": {}},
                                     "extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}},
                    "clientInfo": {"name": "codex-mcp-client", "title": "Codex", "version": "0.159.0"}}
STL = b"solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"


def converse(tmp: Path) -> dict:
    """Codex's side of a session: what it is told, listed, served and launched."""
    bracket = tmp / "project" / "parts" / "bracket.stl"
    bracket.parent.mkdir(parents=True)
    bracket.write_bytes(STL)
    page = tmp / "app"
    page.mkdir()
    (page / "index.html").write_text("<!doctype html><head><title>CAD</title></head>", encoding="utf-8")
    server = Server(page=AppPage(page), recents=RecentStore(tmp / "state"))

    def call(name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        context = RequestContext(1, {"threadId": "t", **(meta or {})})
        return server.handle("tools/call", {"name": name, "arguments": arguments or {}}, context)

    def unwaited(name: str) -> dict:
        with mock.patch("cadgen.mcp.server.OPENING_SECONDS", 0.0):
            return call(name)

    initialized = server.handle("initialize", CODEX_INITIALIZE, None)
    initialized["serverInfo"]["version"] = "<version>"
    uri = server.handle("resources/list", {}, None)["resources"][0]["uri"]
    record = {
        "initialize": initialized,
        "tools": server.handle("tools/list", {}, None)["tools"],
        "resources": server.handle("resources/list", {}, None)["resources"],
        "read": {key: value for key, value in server.handle("resources/read", {"uri": uri}, None)["contents"][0].items()},
        "launches": {
            "cad_home": call("cad_home"),
            "cad_open": call("cad_open", {"path": str(bracket)}),
            "cad_tab": call("cad_tab"),
            "cad_file": call("cad_file", {"file": {"name": "bracket.stl", "resourceUri": "x"}}, {"openai/resource": {"path": str(bracket)}}),
            "cad_show": call("cad_show", {"path": str(bracket)}),
            "cad_view": call("cad_view"),
            # A tab cad_open opened and that never syncs: what the capture answers once it stops waiting for it.
            "cad_screenshot": unwaited("cad_screenshot"),
        },
    }
    for result in record["launches"].values():
        launch = (result.get("structuredContent") or {}).get("launch")
        if isinstance(launch, dict):  # this run's install and machine, not the contract
            launch.update({key: f"<{key}>" for key in ("version", "platform", "pick", "notice") if key in launch})
    text = json.dumps(record, indent=1, sort_keys=True).replace(str(tmp), "<tmp>")
    return json.loads(re.sub(r"ui://cad/[0-9a-f]{16}/", "ui://cad/<build>/", text))


class CodexContractTest(unittest.TestCase):
    # The record is the exchange as text, its paths spelled as POSIX spells them under <tmp>. Windows
    # spells the same paths with a drive and (JSON-escaped) backslashes, so it cannot read as the
    # same text; the record is pinned where it was recorded, and the catalog test below runs everywhere.
    @unittest.skipIf(os.name == "nt", "the record spells its paths as POSIX does")
    def test_codex_is_served_exactly_what_it_was(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.assertEqual(converse(tmp), json.loads(CONTRACT.read_text(encoding="utf-8")))

    def test_the_processes_codex_starts_only_to_list_tools_are_served_the_same_catalog(self) -> None:
        # They advertise no UI extension; being Codex, they still get Codex's catalog, not the text one.
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        server = Server(page=AppPage(tmp), recents=RecentStore(tmp / "state"))
        server.handle("initialize", {**CODEX_INITIALIZE, "capabilities": {"elicitation": {"form": {}, "url": {}}}}, None)
        names = [tool["name"] for tool in json.loads(CONTRACT.read_text(encoding="utf-8"))["tools"]]
        self.assertEqual([tool["name"] for tool in server.handle("tools/list", {}, None)["tools"]], names)


if __name__ == "__main__":
    unittest.main()
