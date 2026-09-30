"""`cadgen mcp`: its catalog, the launches it computes, and the agent driving a view."""

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

STL = b"solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"


class _Connection:
    closed = False

    def is_cancelled(self, request_id) -> bool:
        return False


class ServerTest(unittest.TestCase):
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

    def call(self, name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        context = RequestContext(1, {"threadId": "t", **(meta or {})}, self.connection)
        return self.server.handle("tools/call", {"name": name, "arguments": arguments or {}}, context)

    def launch(self, name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        return self.call(name, arguments, meta)["structuredContent"]["launch"]

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
        # A file the host hands over is shown on its own, with no explorer.
        handed = self.launch("cad_file", {"file": {"name": "loose.stl", "resourceUri": "x"}}, {"openai/resource": {"path": loose}})
        self.assertEqual((handed["model"], handed["explore"], handed["root"]["kind"]), (loose, False, "folder"))
        self.assertEqual([entry.path for entry in self.server.recents.list()], [loose, opened["model"]])

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

    def test_the_tunnel_serves_the_viewer_routes_only_for_roots_this_thread_owns(self) -> None:
        root = {"kind": "workspace", "path": str(self.workspace)}
        reply = self.call("cad_http", {"root": root, "method": "GET", "url": "http://cad.invalid/__cad/catalog"})["structuredContent"]
        catalog = json.loads(base64.b64decode(reply["body"]))
        self.assertEqual((reply["status"], [entry["rootRelativeFile"] for entry in catalog["entries"]]), (200, ["parts/bracket.stl"]))
        refused = self.call("cad_http", {"root": {"kind": "workspace", "path": str(self.tmp / "elsewhere")}, "method": "GET", "url": "/__cad/catalog"})
        self.assertTrue(refused["isError"])
        effect = self.call("cad_http", {"root": root, "method": "POST", "url": "/__cad/reveal", "body": ""})["structuredContent"]
        self.assertEqual(effect["status"], 404)


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
