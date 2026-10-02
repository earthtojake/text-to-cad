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
from unittest import mock

from cadgen.mcp.protocol import RequestContext
from cadgen.viewer.recents import RecentStore
from cadgen.mcp.server import Server
from cadgen.mcp.ui import AppPage

CODEX = {"name": "codex-mcp-client", "title": "Codex", "version": "0.159.0"}
CLAUDE = {"name": "claude-ai", "version": "0.1.0"}
RENDERS_APPS = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}
OTHER_HOST = {"name": "some-desktop-app", "version": "0.1.0"}
DECLARES_TABS = {"extensions": {**RENDERS_APPS["extensions"], "openai/ui": {"entrypoints": ["global", "thread", "file"]}}}
STL = b"solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"


class _Connection:
    closed = False

    def is_cancelled(self, request_id) -> bool:
        return False


class _Session(unittest.TestCase):
    """A server with a workspace holding a bracket, and a model outside it, greeted by ``client``."""

    client = CODEX
    offered: dict = {}
    viewer_url = None

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
        self.server = Server(launch_cwd=str(self.workspace), page=AppPage(page), recents=RecentStore(self.tmp / "state"),
                             viewer_url=self.viewer_url)
        self.connection = _Connection()
        self.initialized = self.server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": self.offered,
                                                             "clientInfo": self.client}, None)

    def call(self, name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        context = RequestContext(1, {"threadId": "t", **(meta or {})}, self.connection)
        return self.server.handle("tools/call", {"name": name, "arguments": arguments or {}}, context)

    def launch(self, name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        return self.call(name, arguments, meta)["structuredContent"]["launch"]

    def poll_as(self, view: str, surface: str, answers: int, model: str | None = None) -> threading.Thread:
        """A view syncing as the page does (every few milliseconds here): its first sync registers it
        and says what it shows; it answers ``answers`` captures."""
        state = {"model": model, "selection": [f"{model}#o1.f1"]}
        self.call("cad_sync", {"view": view, "surface": surface, "model": model, "state": state})

        def page() -> None:
            asked = 0
            while asked < answers:
                events = self.call("cad_sync", {"view": view, "surface": surface, "model": model})["structuredContent"]["events"]
                if not events:
                    time.sleep(0.002)
                for event in events:
                    asked += 1
                    self.call("cad_capture_reply", {"requestId": event["requestId"], "png": "iVBORw0KGgo="})

        viewer = threading.Thread(target=page, daemon=True)
        viewer.start()
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
        self.assertEqual(agent, {"cad_open", "cad_show", "cad_view", "cad_screenshot", "cad_analytics"})
        # All but one read: cad_analytics turns the person's analytics off when they ask.
        self.assertEqual([name for name, tool in tools.items() if not tool["annotations"]["readOnlyHint"]], ["cad_analytics"])
        uri = tools["cad_home"]["_meta"]["ui"]["resourceUri"]
        self.assertRegex(uri, r"^ui://cad/[0-9a-f]{16}/app\.html$")
        self.assertEqual(tools["cad_open"]["_meta"]["ui"]["resourceUri"], uri)
        read = self.server.handle("resources/read", {"uri": uri}, None)["contents"][0]
        self.assertEqual((read["mimeType"], read["text"]), ("text/html;profile=mcp-app", "<!doctype html><title>CAD</title>"))

    def test_a_thread_browses_its_workspace_and_a_model_with_no_project_is_shown_on_its_own(self) -> None:
        opened = self.launch("cad_open", {"path": "parts/bracket.stl"})
        self.assertEqual(opened["model"], str(self.workspace / "parts" / "bracket.stl"))
        self.assertEqual((opened["root"]["kind"], opened["root"]["path"], opened["explore"]), ("workspace", str(self.workspace), True))
        # The thread's tab reopens on what the thread last opened.
        self.assertEqual(self.launch("cad_tab")["model"], opened["model"])
        loose = str(self.tmp / "elsewhere" / "loose.stl")
        anchor = os.path.splitdrive(loose)[0] + os.sep
        outside = self.launch("cad_open", {"path": loose})
        self.assertEqual((outside["root"]["kind"], outside["root"]["path"], outside["explore"]), ("global", anchor, False))
        # A model in a folder the workspace's catalog skips has no project around it either.
        (self.workspace / "build").mkdir()
        (self.workspace / "build" / "out.stl").write_bytes(STL)
        built = self.launch("cad_open", {"path": "build/out.stl"})
        self.assertEqual((built["root"]["kind"], built["root"]["path"], built["explore"]), ("global", anchor, False))
        # A file the host hands over is shown on its own, with no explorer.
        handed = self.launch("cad_file", {"file": {"name": "loose.stl", "resourceUri": "x"}}, {"openai/resource": {"path": loose}})
        self.assertEqual((handed["model"], handed["explore"], handed["root"]["kind"]), (loose, False, "global"))
        self.assertEqual([entry.path for entry in self.server.recents.list()], [loose, built["model"], opened["model"]])

    def test_a_bad_path_is_the_tools_answer_not_a_protocol_error(self) -> None:
        missing = self.call("cad_open", {"path": "parts/nope.step"})
        self.assertTrue(missing["isError"])
        self.assertIn("No file at", missing["content"][0]["text"])
        (self.workspace / "notes.txt").write_text("x", encoding="utf-8")
        self.assertIn("is not one", self.call("cad_open", {"path": "notes.txt"})["content"][0]["text"])

    def test_cad_show_reaches_the_polling_view_without_opening_one(self) -> None:
        self.assertEqual(self.call("cad_show", {"path": "parts/bracket.stl"})["structuredContent"], {"delivered": 0})
        # A sync answers at once: the first registers the view, the next carries what was sent since.
        self.assertEqual(self.call("cad_sync", {"view": "v1", "surface": "tab"})["structuredContent"], {"events": []})
        shown = self.call("cad_show", {"path": "parts/bracket.stl"})
        self.assertEqual(shown["structuredContent"], {"delivered": 1, "view": "v1"})
        (event,) = self.call("cad_sync", {"view": "v1", "surface": "tab"})["structuredContent"]["events"]
        self.assertEqual((event["type"], event["launch"]["model"]), ("show", str(self.workspace / "parts" / "bracket.stl")))

    def test_the_agent_reads_and_captures_what_the_open_view_shows(self) -> None:
        self.assertTrue(self.call("cad_screenshot")["isError"])
        model = str(self.workspace / "parts" / "bracket.stl")
        state = {"model": model, "selection": [f"{model}#o1.f1"]}
        viewer = self.poll_as("v1", "tab", 1, model)
        # What the view said it shows on its sync, answered at once: nothing asks the view.
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
        for route in ("/__cad/reveal", "/__cad/recents"):  # the web app's effects; a view here has tools for them
            effect = self.call("cad_http", {"root": root, "method": "POST", "url": route, "body": ""})["structuredContent"]
            self.assertEqual(effect["status"], 404)

    def test_a_sync_says_when_the_catalog_moved_and_how_a_watched_build_stands(self) -> None:
        root = {"kind": "workspace", "path": str(self.workspace)}
        watch = {"root": root, "file": "parts/bracket.stl", "previews": ["parts/bracket.stl"]}
        first = self.call("cad_sync", {"view": "v1", "surface": "tab", "watch": watch})["structuredContent"]
        catalog = json.loads(base64.b64decode(self.call("cad_http", {"root": root, "method": "GET",
                                                                      "url": "http://cad.invalid/__cad/catalog?file=parts%2Fbracket.stl"})["structuredContent"]["body"]))
        # The revision a view compares is the one its catalog read carries.
        self.assertEqual(first["catalog"]["revision"], catalog["revision"])
        self.assertEqual(first["previews"][0]["file"], "parts/bracket.stl")
        (self.workspace / "parts" / "plate.stl").write_text((self.workspace / "parts" / "bracket.stl").read_text(encoding="utf-8"), encoding="utf-8")
        with mock.patch("cadgen.mcp.tunnel.CATALOG_REVISION_SECONDS", 0):
            moved = self.call("cad_sync", {"view": "v1", "surface": "tab", "watch": watch})["structuredContent"]
        self.assertNotEqual(moved["catalog"]["revision"], first["catalog"]["revision"])
        # A root the view may not watch is refused in the answer, and the agent's requests still reach it.
        self.server.views.post(["v1"], {"type": "show", "model": "/a.step"})
        refused = self.call("cad_sync", {"view": "v1", "surface": "tab", "watch": {"root": {"kind": "workspace", "path": str(self.tmp / "elsewhere")}}})
        self.assertFalse(refused.get("isError"))
        self.assertIn("error", refused["structuredContent"]["catalog"])
        self.assertEqual([event["type"] for event in refused["structuredContent"]["events"]], ["show"])

    def test_the_tunnel_never_holds_a_call_open(self) -> None:
        # The preview feed's ``after`` holds a request until the build ledger moves. The host relays every
        # call through a few slots all its views share, so here it is answered at once; the feed paces itself.
        root = {"kind": "workspace", "path": str(self.workspace)}
        url = "http://cad.invalid/__cad/preview?file=parts%2Fbracket.stl&after=epoch%3A1"
        with mock.patch("cadgen.viewer.preview.preview_update", return_value={"state": "disconnected"}) as update:
            reply = self.call("cad_http", {"root": root, "method": "GET", "url": url})["structuredContent"]
        self.assertEqual(reply["status"], 200)
        self.assertEqual((update.call_args.args[1], update.call_args.kwargs["after"]), ("parts/bracket.stl", None))

    def test_only_the_sidebar_has_a_home_and_a_tab_with_nothing_shown_browses_the_project_if_any(self) -> None:
        user_filesystem = ("global", os.path.splitdrive(os.path.expanduser("~"))[0] + os.sep)
        home = self.launch("cad_home")
        self.assertEqual((home["page"], home["model"], home["explore"], (home["root"]["kind"], home["root"]["path"])),
                         ("home", None, False, user_filesystem))
        tab = self.launch("cad_tab")
        self.assertEqual((tab["page"], tab["model"], tab["explore"], tab["root"]["kind"], tab["root"]["path"]),
                         ("viewer", None, True, "workspace", str(self.workspace)))
        homeless = Server(launch_cwd=None, page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "other"))
        homeless.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": CODEX}, None)
        context = RequestContext(1, {"threadId": "t"}, self.connection)
        launch = homeless.handle("tools/call", {"name": "cad_tab", "arguments": {}}, context)["structuredContent"]["launch"]
        self.assertEqual((launch["page"], launch["explore"], (launch["root"]["kind"], launch["root"]["path"])), ("viewer", False, user_filesystem))

    def test_the_page_reveals_a_file_only_under_a_root_this_thread_may_browse(self) -> None:
        root = {"kind": "workspace", "path": str(self.workspace)}
        target = (self.workspace / "parts" / "bracket.stl").resolve()
        # The desktop's file manager is never opened by a test: the call it would make is recorded.
        with mock.patch("cadgen.viewer.reveal.sys.platform", "darwin"), mock.patch("cadgen.viewer.reveal.subprocess.run") as run:
            self.assertEqual(self.call("cad_reveal", {"root": root, "path": "parts/bracket.stl"})["structuredContent"], {})
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], ["/usr/bin/open", "-R", str(target)])
            refusals = [
                {"root": {"kind": "workspace", "path": str(self.tmp / "elsewhere")}, "path": "loose.stl"},  # not this thread's
                {"root": root, "path": "../elsewhere/loose.stl"},  # out of the root
                {"root": root, "path": "parts/nope.stl"},  # not there
            ]
            for arguments in refusals:
                refused = self.call("cad_reveal", arguments)
                self.assertTrue(refused["isError"], arguments)
            run.assert_called_once()

    def test_a_global_root_catalogs_only_what_is_shown_and_lists_no_folder(self) -> None:
        # A model under a hidden folder, as an agent's worktree is: shown all the same.
        hidden = self.tmp / "elsewhere" / ".worktree"
        hidden.mkdir()
        (hidden / "part.stl").write_bytes(STL)
        loose = self.tmp / "elsewhere" / "loose.stl"
        root = self.launch("cad_open", {"path": str(loose)})["root"]

        def get(url: str) -> tuple[int, dict | bytes]:
            reply = self.call("cad_http", {"root": {"kind": root["kind"], "path": root["path"]}, "method": "GET", "url": url})["structuredContent"]
            body = base64.b64decode(reply["body"])
            return reply["status"], json.loads(body) if reply["headers"].get("content-type", "").startswith("application/json") else body

        relative = os.path.relpath(loose.parent, root["path"]).replace(os.sep, "/")
        self.assertEqual(get(f"/__cad/list?dir={relative}")[0], 404)
        status, catalog = get(f"/__cad/catalog?file={relative}/.worktree/part.stl")
        self.assertEqual((status, [entry["rootRelativeFile"] for entry in catalog["entries"]]), (200, [f"{relative}/.worktree/part.stl"]))
        self.assertEqual(get(f"/__cad/asset?file={hidden / 'part.stl'}"), (200, STL))
        # A global root is a filesystem's, never a folder a view names.
        refused = self.call("cad_http", {"root": {"kind": "global", "path": str(self.tmp)}, "method": "GET", "url": "/__cad/catalog"})
        self.assertTrue(refused["isError"])


class SidebarAcrossThreadsTest(_Session):
    """Codex runs the sidebar page in a thread, and a server process, of its own. An agent in any
    thread reaches the sidebar view a person touched last -- shown a model, read, captured -- as it
    reaches its own tabs, rather than opening a tab beside a model already on screen."""

    def setUp(self) -> None:
        super().setUp()
        # The sidebar's own process: another server over the same state directory.
        self.sidebar = Server(launch_cwd=None, page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "state"))
        self.sidebar.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": CODEX}, None)
        self.model = str(self.workspace / "parts" / "bracket.stl")

    def on_sidebar(self, name: str, arguments: dict) -> dict:
        context = RequestContext(1, {"threadId": "sidebar-thread"}, self.connection)
        return self.sidebar.handle("tools/call", {"name": name, "arguments": arguments}, context)["structuredContent"]

    def sync_sidebar(self, **extra) -> dict:
        return self.on_sidebar("cad_sync", {"view": "s1", "surface": "sidebar", "model": self.model, **extra})

    def test_an_agent_with_no_tab_shows_reads_and_captures_the_model_in_the_sidebar(self) -> None:
        self.sync_sidebar(state={"model": self.model, "selection": [f"{self.model}#o1.f1"]}, focused=True)
        # The model the sidebar shows already: no tab, and nothing to send it.
        self.assertEqual(self.call("cad_show", {"path": "parts/bracket.stl"})["structuredContent"],
                         {"delivered": 1, "view": "s1", "sidebar": True})
        self.assertEqual(self.sync_sidebar()["events"], [])
        # What the sidebar reported, read at once.
        (view,) = self.call("cad_view")["structuredContent"]["views"]
        self.assertEqual((view["view"], view["surface"], view["selection"]), ("s1", "sidebar", [f"{self.model}#o1.f1"]))
        # Another model: the sidebar takes it on its next sync.
        loose = str(self.tmp / "elsewhere" / "loose.stl")
        self.assertEqual(self.call("cad_show", {"path": loose})["structuredContent"]["view"], "s1")
        (event,) = self.sync_sidebar()["events"]
        self.assertEqual((event["type"], event["launch"]["model"]), ("show", loose))
        # A capture: the sidebar's process takes the request on a sync, and its answer comes back.

        def page() -> None:
            for _ in range(1000):
                for event in self.sync_sidebar()["events"]:
                    if event["type"] == "capture":
                        self.on_sidebar("cad_capture_reply", {"requestId": event["requestId"], "png": "iVBORw0KGgo="})
                        return
                time.sleep(0.005)

        viewer = threading.Thread(target=page, daemon=True)
        viewer.start()
        shot = self.call("cad_screenshot")
        viewer.join(10)
        self.assertEqual(shot["content"][0], {"type": "image", "data": "iVBORw0KGgo=", "mimeType": "image/png"})

    def test_the_view_a_person_touched_last_is_meant_and_a_threads_tabs_stay_its_own(self) -> None:
        self.call("cad_sync", {"view": "t1", "surface": "agent", "model": self.model})
        time.sleep(0.02)
        self.sync_sidebar(focused=True)
        self.assertEqual(self.call("cad_show", {"path": "parts/bracket.stl"})["structuredContent"]["view"], "s1")
        time.sleep(0.02)
        self.call("cad_sync", {"view": "t1", "surface": "agent", "model": self.model, "focused": True})
        self.assertEqual(self.call("cad_show", {"path": "parts/bracket.stl"})["structuredContent"]["view"], "t1")
        # The sidebar's process sees no thread's tab: only sidebar views are shared.
        self.assertEqual([view["view"] for view in self.on_sidebar("cad_view", {})["views"]], ["s1"])

    def test_a_sidebar_that_stopped_syncing_is_not_reached(self) -> None:
        self.sync_sidebar(focused=True)
        stale = time.time() - 120
        for published in (self.tmp / "state" / "sidebar-views").glob("*.json"):
            os.utime(published, (stale, stale))
        self.assertEqual(self.call("cad_show", {"path": "parts/bracket.stl"})["structuredContent"], {"delivered": 0})


class DeclaredTabServerTest(_Session):
    """Any host that declares Codex's entrypoints gets tabs, whatever it is called."""

    client = OTHER_HOST
    offered = DECLARES_TABS

    def test_a_host_that_declares_the_entrypoints_gets_the_tab_surfaces(self) -> None:
        tools = {tool["name"]: tool for tool in self.server.handle("tools/list", {}, None)["tools"]}
        entrypoints = {name: tool["_meta"]["openai/ui"]["entrypoints"][0]["type"] for name, tool in tools.items()
                       if "entrypoints" in tool.get("_meta", {}).get("openai/ui", {})}
        self.assertEqual(entrypoints, {"cad_home": "global", "cad_tab": "thread", "cad_file": "file"})
        self.assertIn("cad_open", tools)

    def test_a_partial_declaration_is_shown_inline(self) -> None:
        partial = {"extensions": {**RENDERS_APPS["extensions"], "openai/ui": {"entrypoints": ["thread"]}}}
        server = Server(launch_cwd=str(self.workspace), page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "state2"))
        server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": partial, "clientInfo": OTHER_HOST}, None)
        tools = {tool["name"] for tool in server.handle("tools/list", {}, None)["tools"]}
        self.assertNotIn("cad_open", tools)


class InlineServerTest(_Session):
    """Claude and every other MCP Apps host: each cad_show mounts a new view in the chat."""

    client = CLAUDE
    offered = RENDERS_APPS

    def test_an_inline_host_shows_models_with_one_tool_and_is_told_so(self) -> None:
        tools = {tool["name"]: tool for tool in self.server.handle("tools/list", {}, None)["tools"]}
        agent = {name for name, tool in tools.items() if tool.get("_meta", {}).get("ui", {}).get("visibility") != ["app"]}
        # A chat shows files: no home.
        self.assertEqual(agent, {"cad_show", "cad_view", "cad_screenshot", "cad_analytics"})
        uri = tools["cad_show"]["_meta"]["ui"]["resourceUri"]
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
        self.assertEqual((second["root"]["kind"], second["model"]), ("global", str(self.tmp / "elsewhere" / "loose.stl")))
        shown = self.call("cad_show", {"path": "parts/bracket.stl"})
        self.assertIn(shown["structuredContent"]["launch"]["view"], shown["content"][0]["text"])

    def test_the_agent_reads_only_the_view_it_names(self) -> None:
        model = str(self.workspace / "parts" / "bracket.stl")
        view = self.launch("cad_show", {"path": "parts/bracket.stl"})["view"]
        self.assertIn("pass the view", self.call("cad_view")["content"][0]["text"])
        viewer = self.poll_as(view, "inline", 1, model)
        # Another chat's view, served by the same process and touched since, is never the one read.
        self.call("cad_sync", {"view": "cad-other", "surface": "inline", "model": model, "focused": True})
        described = self.call("cad_view", {"view": view})["structuredContent"]["views"]
        self.assertEqual(described, [{"view": view, "surface": "inline", "model": model, "selection": [f"{model}#o1.f1"]}])
        self.assertEqual(self.call("cad_screenshot", {"view": view})["content"][0]["data"], "iVBORw0KGgo=")
        viewer.join(10)
        # A view a newer one replaced closes itself, and is no longer there to read.
        self.call("cad_sync", {"view": view, "surface": "inline", "model": model, "closed": True})
        self.assertIn("not open", self.call("cad_view", {"view": view})["content"][0]["text"])


class RootsTest(_Session):
    """A client that offers roots says which folders the chat works in."""

    client = CLAUDE
    offered = {"roots": {"listChanged": True}, **RENDERS_APPS}

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


class TextServerTest(_Session):
    """A client that renders no MCP Apps: cad_show answers with the model's link in the CAD Viewer."""

    client = {"name": "some-cli", "version": "1"}
    served: list = []

    @staticmethod
    def viewer_url(folder: str) -> str:
        TextServerTest.served.append(folder)
        return "http://127.0.0.1:3999/"

    def test_cad_show_links_the_model_in_the_viewer_serving_its_folder(self) -> None:
        tools = self.server.handle("tools/list", {}, None)["tools"]
        self.assertEqual([(tool["name"], "_meta" in tool) for tool in tools], [("cad_show", False), ("cad_analytics", False)])
        self.assertIn("cannot show CAD views", self.initialized["instructions"])
        shown = self.call("cad_show", {"path": "parts/bracket.stl"})
        self.assertEqual(shown["structuredContent"]["url"], "http://127.0.0.1:3999/?file=parts/bracket.stl")
        self.assertIn("http://127.0.0.1:3999/?file=parts/bracket.stl", shown["content"][0]["text"])
        self.assertNotIn("Showing", shown["content"][0]["text"])
        self.assertEqual(TextServerTest.served[-1], str(self.workspace))
        self.assertEqual(self.server.recents.list()[0].path, str(self.workspace / "parts" / "bracket.stl"))

    def test_a_viewer_that_will_not_start_leaves_the_command_to_run(self) -> None:
        from cadgen.mcp.browser import ViewerUnavailable

        def refuse(folder: str) -> str:
            raise ViewerUnavailable("no port")

        self.server._viewer_url = refuse
        failed = self.call("cad_show", {"path": "parts/bracket.stl"})
        self.assertTrue(failed["isError"])
        self.assertIn(f'cd "{self.workspace}" && cadgen viewer --host 127.0.0.1 --json', failed["content"][0]["text"])

    def test_an_app_that_renders_without_advertising_it_can_be_told(self) -> None:
        from unittest import mock

        with mock.patch.dict(os.environ, {"CADGEN_MCP_PRESENTATION": "inline"}):
            server = Server(launch_cwd=str(self.workspace), page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "other"))
            server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": self.client}, None)
        self.assertIn("ui", {tool["name"]: tool for tool in server.handle("tools/list", {}, None)["tools"]}["cad_show"]["_meta"])


class ImportBudgetTest(unittest.TestCase):
    def test_initialize_and_tools_list_wake_no_cad_kernel(self) -> None:
        code = (
            "import sys\n"
            "from cadgen.mcp.server import Server\n"
            "server = Server(launch_cwd='/')\n"
            "server.handle('initialize', {'protocolVersion': '2025-06-18'}, None)\n"
            "server.handle('tools/list', {}, None)\n"
            "print(','.join(name for name in ('OCP', 'build123d', 'ezdxf', 'cadgen.mcp.tunnel', 'cadgen.viewer.recents') if name in sys.modules))\n"
        )
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env={**os.environ})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
