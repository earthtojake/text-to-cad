"""What Codex is served, pinned: other hosts' support must not change a byte of it.

The server answers Codex (its client names itself ``codex-mcp-client``) with tab surfaces the agent
opens once and then drives. ``codex_contract.json`` records that conversation -- initialize, the
catalog, the resource, and the launches each surface returns -- with the page's build and this run's
paths replaced by placeholders. A change to Codex's side has to change that file on purpose.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from cadgen.mcp.protocol import RequestContext
from cadgen.mcp.recents import RecentStore
from cadgen.mcp.server import Server
from cadgen.mcp.ui import AppPage

CONTRACT = Path(__file__).with_name("codex_contract.json")
CODEX_INITIALIZE = {"protocolVersion": "2025-06-18",
                    "capabilities": {"elicitation": {"form": {}, "url": {}}, "experimental": {"codex/auth-change": {}},
                                     "extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}},
                    "clientInfo": {"name": "codex-mcp-client", "title": "Codex", "version": "0.159.0"}}
STL = b"solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"


class _Connection:
    closed = False

    def is_cancelled(self, request_id) -> bool:
        return False


def converse(tmp: Path) -> dict:
    """Codex's side of a session: what it is told, listed, served and launched."""
    workspace = tmp / "project"
    (workspace / "parts").mkdir(parents=True)
    (workspace / "parts" / "bracket.stl").write_bytes(STL)
    page = tmp / "app"
    page.mkdir()
    (page / "index.html").write_text("<!doctype html><head><title>CAD</title></head>", encoding="utf-8")
    server = Server(launch_cwd=str(workspace), page=AppPage(page), recents=RecentStore(tmp / "state"))
    connection = _Connection()

    def call(name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        context = RequestContext(1, {"threadId": "t", **(meta or {})}, connection)
        return server.handle("tools/call", {"name": name, "arguments": arguments or {}}, context)

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
            "cad_open": call("cad_open", {"path": "parts/bracket.stl"}),
            "cad_tab": call("cad_tab"),
            "cad_file": call("cad_file", {"file": {"name": "bracket.stl", "resourceUri": "x"}},
                             {"openai/resource": {"path": str(workspace / "parts" / "bracket.stl")}}),
            "cad_launch": call("cad_launch", {"model": "parts/bracket.stl"}),
            "cad_show": call("cad_show", {"path": "parts/bracket.stl"}),
            "cad_view": call("cad_view"),
            "cad_screenshot": call("cad_screenshot"),
        },
    }
    text = json.dumps(record, indent=1, sort_keys=True).replace(str(tmp), "<tmp>")
    return json.loads(re.sub(r"ui://cad/[0-9a-f]{16}/", "ui://cad/<build>/", text))


class CodexContractTest(unittest.TestCase):
    def test_codex_is_served_exactly_what_it_was(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.assertEqual(converse(tmp), json.loads(CONTRACT.read_text(encoding="utf-8")))

    def test_the_processes_codex_starts_only_to_list_tools_are_served_the_same_catalog(self) -> None:
        # They advertise no UI extension; being Codex, they still get Codex's catalog, not the text one.
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        server = Server(launch_cwd=str(tmp), page=AppPage(tmp), recents=RecentStore(tmp / "state"))
        server.handle("initialize", {**CODEX_INITIALIZE, "capabilities": {"elicitation": {"form": {}, "url": {}}}}, None)
        names = [tool["name"] for tool in json.loads(CONTRACT.read_text(encoding="utf-8"))["tools"]]
        self.assertEqual([tool["name"] for tool in server.handle("tools/list", {}, None)["tools"]], names)


if __name__ == "__main__":
    unittest.main()
