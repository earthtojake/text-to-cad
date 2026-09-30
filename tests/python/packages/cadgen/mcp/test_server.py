"""`cadgen mcp`: its catalog, the launches it computes, and the agent driving a view, for both kinds of host."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cadgen.mcp.protocol import RequestContext
from cadgen.mcp.recents import RecentStore
from cadgen.mcp.server import Server
from cadgen.mcp.ui import AppPage

CODEX = {"name": "codex-mcp-client", "title": "Codex", "version": "0.159.0"}
CLAUDE = {"name": "claude-ai", "version": "0.1.0"}
STL = b"solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"


class _Connection:
    closed = False

    def is_cancelled(self, request_id) -> bool:
        return False


class _Session(unittest.TestCase):
    """A server with a workspace holding a bracket, and a model outside it, greeted by ``client``."""

    client = CODEX
    offered: dict = {}

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.workspace = self.tmp / "project"
        (self.workspace / "parts").mkdir(parents=True)
        (self.workspace / "parts" / "bracket.stl").write_bytes(STL)
        (self.tmp / "elsewhere").mkdir()
        (self.tmp / "elsewhere" / "loose.stl").write_bytes(STL)
        page = self.tmp / "app"
        page.mkdir()
        (page / "index.html").write_text("<!doctype html><title>CAD</title>", encoding="utf-8")
        self.server = Server(launch_cwd=str(self.workspace), page=AppPage(page), recents=RecentStore(self.tmp / "state"))
        self.connection = _Connection()
        self.initialized = self.server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": self.offered,
                                                             "clientInfo": self.client}, None)

    def call(self, name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        context = RequestContext(1, {"threadId": "t", **(meta or {})}, self.connection)
        return self.server.handle("tools/call", {"name": name, "arguments": arguments or {}}, context)

    def launch(self, name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        return self.call(name, arguments, meta)["structuredContent"]["launch"]

    def poll_as(self, view: str, surface: str, answers: int, model: str | None = None) -> threading.Thread:
        """A view long-polling as the page does, answering ``answers`` questions (describe or capture)."""

        def page() -> None:
            asked = 0
            while asked < answers:
                for event in self.call("cad_events", {"view": view, "surface": surface, "model": model})["structuredContent"]["events"]:
                    asked += 1
                    answer = {"png": "iVBORw0KGgo="} if event["type"] == "capture" else {"state": {"model": model, "selection": [f"{model}#o1.f1"]}}
                    self.call("cad_capture_reply", {"requestId": event["requestId"], **answer})

        viewer = threading.Thread(target=page, daemon=True)
        viewer.start()
        deadline = time.monotonic() + 10
        while view not in {live.id for live in self.server.views.live()}:  # the poll registers, then waits
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.001)
        return viewer


class TabServerTest(_Session):
    """Codex: tab surfaces the agent opens once and then drives."""

    def test_the_catalog_names_every_surface_and_keeps_page_tools_from_the_agent(self) -> None:
        tools = {tool["name"]: tool for tool in self.server.handle("tools/list", {}, None)["tools"]}
        meta = {name: tool.get("_meta", {}) for name, tool in tools.items()}
        entrypoints = {name: value["openai/ui"]["entrypoints"][0]["type"] for name, value in meta.items()
                       if "entrypoints" in value.get("openai/ui", {})}
        self.assertEqual(entrypoints, {"cad_home": "global", "cad_tab": "thread", "cad_file": "file"})
        agent = {name for name, value in meta.items() if value.get("ui", {}).get("visibility") != ["app"]}
        self.assertEqual(agent, {"cad_open", "cad_show", "cad_view", "cad_screenshot"})
        self.assertTrue(all(tool["annotations"]["readOnlyHint"] for tool in tools.values()))
        uri = tools["cad_home"]["_meta"]["ui"]["resourceUri"]
        self.assertRegex(uri, r"^ui://cad/[0-9a-f]{16}/app\.html$")
        self.assertEqual(tools["cad_open"]["_meta"]["ui"]["resourceUri"], uri)
        read = self.server.handle("resources/read", {"uri": uri}, None)["contents"][0]
        self.assertEqual((read["mimeType"], read["text"]), ("text/html;profile=mcp-app", "<!doctype html><title>CAD</title>"))

    def test_a_thread_browses_its_workspace_and_anything_else_browses_its_own_folder(self) -> None:
        opened = self.launch("cad_open", {"path": "parts/bracket.stl"})
        self.assertEqual(opened["model"], str(self.workspace / "parts" / "bracket.stl"))
        self.assertEqual((opened["root"]["kind"], opened["root"]["path"], opened["explore"]), ("workspace", str(self.workspace), True))
        # The thread's tab reopens on what the thread last opened.
        self.assertEqual(self.launch("cad_tab")["model"], opened["model"])
        loose = str(self.tmp / "elsewhere" / "loose.stl")
        outside = self.launch("cad_open", {"path": loose})
        self.assertEqual((outside["root"]["kind"], outside["root"]["path"]), ("folder", str(self.tmp / "elsewhere")))
        # A model in a folder the workspace's catalog skips is browsed from its own folder.
        (self.workspace / "build").mkdir()
        (self.workspace / "build" / "out.stl").write_bytes(STL)
        built = self.launch("cad_open", {"path": "build/out.stl"})
        self.assertEqual((built["root"]["kind"], built["root"]["path"]), ("folder", str(self.workspace / "build")))
        # A file the host hands over is shown on its own, with no explorer.
        handed = self.launch("cad_file", {"file": {"name": "loose.stl", "resourceUri": "x"}}, {"openai/resource": {"path": loose}})
        self.assertEqual((handed["model"], handed["explore"], handed["root"]["kind"]), (loose, False, "folder"))
        self.assertEqual([entry.path for entry in self.server.recents.list()], [loose, built["model"], opened["model"]])

    def test_a_bad_path_is_the_tools_answer_not_a_protocol_error(self) -> None:
        missing = self.call("cad_open", {"path": "parts/nope.step"})
        self.assertTrue(missing["isError"])
        self.assertIn("No file at", missing["content"][0]["text"])
        (self.workspace / "notes.txt").write_text("x", encoding="utf-8")
        self.assertIn("is not one", self.call("cad_open", {"path": "notes.txt"})["content"][0]["text"])

    def test_cad_show_reaches_the_polling_view_without_opening_one(self) -> None:
        self.assertEqual(self.call("cad_show", {"path": "parts/bracket.stl"})["structuredContent"], {"delivered": 0})
        polled: list = []
        poller = threading.Thread(target=lambda: polled.append(self.call("cad_events", {"view": "v1", "surface": "tab"})))
        poller.start()
        deadline = time.monotonic() + 10
        while "v1" not in {view.id for view in self.server.views.live("t")}:  # the poll registers, then waits
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.001)
        shown = self.call("cad_show", {"path": "parts/bracket.stl"})
        poller.join(10)
        self.assertEqual(shown["structuredContent"], {"delivered": 1, "view": "v1"})
        (event,) = polled[0]["structuredContent"]["events"]
        self.assertEqual((event["type"], event["launch"]["model"]), ("show", str(self.workspace / "parts" / "bracket.stl")))

    def test_the_agent_reads_and_captures_what_the_open_view_shows(self) -> None:
        self.assertTrue(self.call("cad_screenshot")["isError"])
        model = str(self.workspace / "parts" / "bracket.stl")
        state = {"model": model, "selection": [f"{model}#o1.f1"]}
        viewer = self.poll_as("v1", "tab", 2, model)
        self.assertEqual(self.call("cad_view")["structuredContent"], {"views": [{"view": "v1", "surface": "tab", **state}]})
        shot = self.call("cad_screenshot")
        viewer.join(10)
        self.assertFalse(viewer.is_alive())
        self.assertEqual(shot["content"][0], {"type": "image", "data": "iVBORw0KGgo=", "mimeType": "image/png"})
        self.assertEqual(shot["structuredContent"], {"view": "v1", "model": model})

    def test_the_tunnel_serves_the_viewer_routes_only_for_roots_this_thread_owns(self) -> None:
        root = {"kind": "workspace", "path": str(self.workspace)}
        reply = self.call("cad_http", {"root": root, "method": "GET", "url": "http://cad.invalid/__cad/catalog"})["structuredContent"]
        catalog = json.loads(base64.b64decode(reply["body"]))
        self.assertEqual((reply["status"], [entry["rootRelativeFile"] for entry in catalog["entries"]]), (200, ["parts/bracket.stl"]))
        refused = self.call("cad_http", {"root": {"kind": "workspace", "path": str(self.tmp / "elsewhere")}, "method": "GET", "url": "/__cad/catalog"})
        self.assertTrue(refused["isError"])
        effect = self.call("cad_http", {"root": root, "method": "POST", "url": "/__cad/reveal", "body": ""})["structuredContent"]
        self.assertEqual(effect["status"], 404)


class InlineServerTest(_Session):
    """Claude and every other MCP Apps host: each cad_show mounts a new view in the chat."""

    client = CLAUDE

    def test_an_inline_host_shows_models_with_one_tool_and_is_told_so(self) -> None:
        tools = {tool["name"]: tool for tool in self.server.handle("tools/list", {}, None)["tools"]}
        agent = {name for name, tool in tools.items() if tool.get("_meta", {}).get("ui", {}).get("visibility") != ["app"]}
        self.assertEqual(agent, {"cad_show", "cad_home", "cad_view", "cad_screenshot"})
        uri = tools["cad_show"]["_meta"]["ui"]["resourceUri"]
        self.assertEqual(tools["cad_home"]["_meta"]["ui"]["resourceUri"], uri)
        self.assertFalse(any(key.startswith("openai/") for tool in tools.values() for key in tool.get("_meta", {})))
        self.assertEqual((tools["cad_view"]["inputSchema"]["required"], tools["cad_screenshot"]["inputSchema"]["required"]), (["view"], ["view"]))
        self.assertNotIn("experimental", self.initialized["capabilities"])
        self.assertIn("cad_show", self.initialized["instructions"])
        # The same app, told before it greets the host that it is shown inline.
        page = self.server.handle("resources/read", {"uri": uri}, None)["contents"][0]["text"]
        self.assertEqual(page, '<!doctype html><meta name="cad-presentation" content="inline"><title>CAD</title>')
        self.assertNotEqual(uri, AppPage(self.tmp / "app").uri)

    def test_each_show_mounts_a_new_view_named_and_ordered(self) -> None:
        first = self.launch("cad_show", {"path": "parts/bracket.stl"})
        second = self.launch("cad_show", {"path": str(self.tmp / "elsewhere" / "loose.stl")})
        self.assertNotEqual(first["view"], second["view"])
        self.assertLess((first["order"]["createdAt"], first["order"]["seq"]), (second["order"]["createdAt"], second["order"]["seq"]))
        self.assertEqual((first["surface"], first["explore"], first["root"]["kind"]), ("inline", False, "workspace"))
        self.assertEqual((second["root"]["kind"], second["model"]), ("folder", str(self.tmp / "elsewhere" / "loose.stl")))
        shown = self.call("cad_show", {"path": "parts/bracket.stl"})
        self.assertIn(shown["structuredContent"]["launch"]["view"], shown["content"][0]["text"])
        self.assertEqual(self.launch("cad_home")["page"], "home")

    def test_the_agent_reads_only_the_view_it_names(self) -> None:
        model = str(self.workspace / "parts" / "bracket.stl")
        view = self.launch("cad_show", {"path": "parts/bracket.stl"})["view"]
        self.assertIn("pass the view", self.call("cad_view")["content"][0]["text"])
        viewer = self.poll_as(view, "inline", 2, model)
        # Another chat's view, served by the same process and touched since, is never the one read.
        self.call("cad_view_report", {"view": "cad-other", "surface": "inline", "model": model, "state": {}, "focused": True})
        described = self.call("cad_view", {"view": view})["structuredContent"]["views"]
        self.assertEqual(described, [{"view": view, "surface": "inline", "model": model, "selection": [f"{model}#o1.f1"]}])
        self.assertEqual(self.call("cad_screenshot", {"view": view})["content"][0]["data"], "iVBORw0KGgo=")
        viewer.join(10)
        # A view a newer one replaced closes itself, and is no longer there to read.
        self.call("cad_view_report", {"view": view, "surface": "inline", "model": model, "state": {"closed": True}})
        self.assertIn("not open", self.call("cad_view", {"view": view})["content"][0]["text"])


class RootsTest(_Session):
    """A client that offers roots says which folders the chat works in."""

    client = CLAUDE
    offered = {"roots": {"listChanged": True}}

    def test_a_host_that_offers_roots_sets_the_workspace(self) -> None:
        other = self.tmp / "other"
        (other / "parts").mkdir(parents=True)
        (other / "parts" / "bracket.stl").write_bytes(STL)

        class Host:
            def request(self, method, params, timeout=None):
                assert method == "roots/list"
                return {"roots": [{"uri": other.as_uri(), "name": "other"}]}

        self.server.attach(Host())
        self.server.notified("notifications/initialized", {})
        deadline = time.monotonic() + 10
        while self.server.workspace.primary != str(other):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.001)
        self.assertEqual(self.launch("cad_show", {"path": "parts/bracket.stl"})["model"], str(other / "parts" / "bracket.stl"))


class ImportBudgetTest(unittest.TestCase):
    def test_initialize_and_tools_list_wake_no_cad_kernel(self) -> None:
        code = (
            "import sys\n"
            "from cadgen.mcp.server import Server\n"
            "server = Server(launch_cwd='/')\n"
            "server.handle('initialize', {'protocolVersion': '2025-06-18'}, None)\n"
            "server.handle('tools/list', {}, None)\n"
            "print(','.join(name for name in ('OCP', 'build123d', 'ezdxf', 'cadgen.mcp.tunnel', 'cadgen.mcp.recents') if name in sys.modules))\n"
        )
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env={**os.environ})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
