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
from urllib.parse import quote

from cadgen._internal.picker import FilePicker
from cadgen.mcp.protocol import RequestContext, RpcError
from cadgen.viewer.recents import RecentStore
from cadgen.mcp.server import Server
from cadgen.mcp.tunnel import MAX_REPLY_BYTES
from cadgen.mcp.ui import AppPage

CODEX = {"name": "codex-mcp-client", "title": "Codex", "version": "0.159.0"}
CLAUDE = {"name": "claude-ai", "version": "0.1.0"}
RENDERS_APPS = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}
OTHER_HOST = {"name": "some-desktop-app", "version": "0.1.0"}
DECLARES_TABS = {"extensions": {**RENDERS_APPS["extensions"], "dev.texttocad/tabs": {"entrypoints": ["global", "thread", "file"]}}}
STL = b"solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"
# The longest message a reply may make: its body's base64 and an envelope. 5.6 MB, under the
# 10 MiB the MCP TypeScript SDK's stdio reader stops at.
MESSAGE_BOUND = MAX_REPLY_BYTES * 4 // 3 + 4096
# What the page's client sends with every POST: the viewer refuses one without its header.
GUARDED = {"x-cadgen-viewer": "1", "content-type": "application/json"}


def offer_an_update(test: unittest.TestCase) -> None:
    """A feed read today that offers 99.0.0 to the Claude plugin installed from GitHub (`cadgen/updates.py`)."""
    state = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, state, ignore_errors=True)
    patched = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(state), "CADGEN_INSTALL_CHANNEL": "claude-github", "CADGEN_AUTO_UPDATED": "", "CI": "",
                                           "CADGEN_UPDATE_CHECK": ""})
    patched.start()
    test.addCleanup(patched.stop)
    (state / "versions.json").write_text(json.dumps({"checked": time.time(), "feed": {"latest": "99.0.0"}}), encoding="utf-8")


class _Session(unittest.TestCase):
    """A server, a bracket in a project folder and a model elsewhere, greeted by ``client``."""

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
        self.bracket = str(self.workspace / "parts" / "bracket.stl")
        self.loose = str(self.tmp / "elsewhere" / "loose.stl")
        page = self.tmp / "app"
        page.mkdir()
        (page / "index.html").write_text("<!doctype html><title>CAD</title>", encoding="utf-8")
        self.server = Server(page=AppPage(page), recents=RecentStore(self.tmp / "state"), viewer_url=self.viewer_url)
        self.initialized = self.server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": self.offered,
                                                             "clientInfo": self.client}, None)

    def call(self, name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        context = RequestContext(1, {"threadId": "t", **(meta or {})})
        return self.server.handle("tools/call", {"name": name, "arguments": arguments or {}}, context)

    def launch(self, name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        return self.call(name, arguments, meta)["structuredContent"]["launch"]

    def http(self, method: str, url: str, body: bytes | dict = b"", headers: dict | None = None) -> tuple[int, dict | bytes]:
        """A request the page sends through ``cad_http``: its status, and its body (JSON decoded). A
        dict body is a JSON POST, with the header the page's client sends."""
        if isinstance(body, dict):
            body, headers = json.dumps(body).encode("utf-8"), {**GUARDED, **(headers or {})}
        reply = self.call("cad_http", {"method": method, "url": url, "headers": headers or {},
                                       "body": base64.b64encode(body).decode("ascii")})["structuredContent"]
        data = base64.b64decode(reply.get("body") or "")
        return reply["status"], json.loads(data) if reply["headers"].get("content-type", "").startswith("application/json") else data

    def poll_as(self, view: str, surface: str, answers: int, model: str | None = None, png: str = "iVBORw0KGgo=") -> threading.Thread:
        """A view syncing as the page does (every few milliseconds here): its first sync registers it
        and says what it shows; it answers ``answers`` captures with ``png``."""
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
                    self.call("cad_capture_reply", {"requestId": event["requestId"], "png": png})

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
        # The page's own: its sync, its answer to a capture, and the viewer's routes, which carry the rest.
        page = {name for name, value in meta.items() if value.get("ui", {}).get("visibility") == ["app"]} - set(entrypoints)
        self.assertEqual(page, {"cad_sync", "cad_capture_reply", "cad_http"})
        # All but one read: cad_analytics turns the person's analytics off when they ask.
        self.assertEqual([name for name, tool in tools.items() if not tool["annotations"]["readOnlyHint"]], ["cad_analytics"])
        uri = tools["cad_home"]["_meta"]["ui"]["resourceUri"]
        self.assertRegex(uri, r"^ui://cad/[0-9a-f]{16}/app\.html$")
        self.assertEqual(tools["cad_open"]["_meta"]["ui"]["resourceUri"], uri)
        read = self.server.handle("resources/read", {"uri": uri}, None)["contents"][0]
        self.assertEqual((read["mimeType"], read["text"]), ("text/html;profile=mcp-app", "<!doctype html><title>CAD</title>"))

    def test_the_page_reads_whether_a_newer_release_is_out_and_nothing_is_kept(self) -> None:
        offer_an_update(self)
        for _ in range(2):  # the update button stays while this install is behind
            notice = self.http("GET", "/__cad/version")[1]["notice"]
            self.assertEqual(notice["prompt"], "Update text-to-cad to 99.0.0 from https://github.com/earthtojake/text-to-cad")
        # A launch carries it, as the server last read it, so the button draws with the page.
        self.assertEqual(self.launch("cad_home")["notice"], notice)

    def test_an_agent_names_a_model_by_its_absolute_path_and_a_tab_reopens_on_it(self) -> None:
        opened = self.launch("cad_open", {"path": self.bracket})
        self.assertEqual({key: opened[key] for key in ("protocol", "page", "model", "surface")},
                         {"protocol": 5, "page": "viewer", "model": self.bracket, "surface": "agent"})
        self.assertEqual(sorted(opened), ["model", "notice", "page", "pick", "platform", "protocol", "surface", "version"])
        # The thread's tab reopens on what the thread last opened.
        self.assertEqual(self.launch("cad_tab")["model"], self.bracket)
        refused = self.call("cad_open", {"path": "parts/bracket.stl"})
        self.assertTrue(refused["isError"])
        self.assertIn("is not an absolute path", refused["content"][0]["text"])
        # A file the host hands over is shown alone: the host's own file tree is its navigation.
        handed = self.launch("cad_file", {"file": {"name": "loose.stl", "resourceUri": "x"}}, {"openai/resource": {"path": self.loose}})
        self.assertEqual((handed["model"], handed["surface"]), (self.loose, "file"))
        # A launch adds nothing to the library: the view does, once the model is on screen.
        self.assertEqual(self.server.recents.list(), [])

    def test_a_bad_path_is_the_tools_answer_not_a_protocol_error(self) -> None:
        missing = self.call("cad_open", {"path": str(self.workspace / "parts" / "nope.step")})
        self.assertTrue(missing["isError"])
        self.assertIn("No file at", missing["content"][0]["text"])
        (self.workspace / "notes.txt").write_text("x", encoding="utf-8")
        self.assertIn("is not one", self.call("cad_open", {"path": str(self.workspace / "notes.txt")})["content"][0]["text"])

    def test_cad_show_reaches_the_polling_view_without_opening_one(self) -> None:
        self.assertEqual(self.call("cad_show", {"path": self.bracket})["structuredContent"], {"delivered": 0})
        # A sync answers at once: the first registers the view, the next carries what was sent since.
        self.assertEqual(self.call("cad_sync", {"view": "v1", "surface": "tab"})["structuredContent"], {"events": []})
        shown = self.call("cad_show", {"path": self.bracket})
        self.assertEqual(shown["structuredContent"], {"delivered": 1, "view": "v1"})
        (event,) = self.call("cad_sync", {"view": "v1", "surface": "tab"})["structuredContent"]["events"]
        self.assertEqual((event["type"], event["launch"]["model"]), ("show", self.bracket))

    def test_the_agent_reads_and_captures_what_the_open_view_shows(self) -> None:
        self.assertTrue(self.call("cad_screenshot")["isError"])
        model = self.bracket
        state = {"model": model, "selection": [f"{model}#o1.f1"]}
        viewer = self.poll_as("v1", "tab", 1, model)
        # What the view said it shows on its sync, answered at once: nothing asks the view.
        self.assertEqual(self.call("cad_view")["structuredContent"], {"views": [{"view": "v1", "surface": "tab", **state}]})
        shot = self.call("cad_screenshot")
        viewer.join(10)
        self.assertFalse(viewer.is_alive())
        self.assertEqual(shot["content"][0], {"type": "image", "data": "iVBORw0KGgo=", "mimeType": "image/png"})
        self.assertEqual(shot["structuredContent"], {"view": "v1", "model": model})

    def test_the_tunnel_serves_the_viewer_by_absolute_path_and_keeps_the_hosts_effects_the_hosts(self) -> None:
        # A model under a hidden folder, as an agent's worktree is: shown all the same.
        hidden = self.tmp / "elsewhere" / ".worktree"
        hidden.mkdir()
        (hidden / "part.stl").write_bytes(STL)
        part = str(hidden / "part.stl")
        status, catalog = self.http("GET", f"http://cad.invalid/__cad/catalog?file={quote(part, safe='')}")
        self.assertEqual((status, [entry["file"] for entry in catalog["entries"]]), (200, [part.replace(os.sep, "/")]))
        self.assertEqual(self.http("GET", f"/__cad/asset?file={quote(part, safe='')}"), (200, STL))
        # The explorer lists a folder; hidden ones stay out of it.
        status, folder = self.http("GET", f"/__cad/folder?path={quote(str(self.tmp / 'elsewhere'), safe='')}")
        self.assertEqual((status, folder["entries"]), (200, [{"name": "loose.stl", "kind": "file"}]))
        self.assertEqual(self.http("GET", "/__cad/catalog?file=parts%2Fbracket.stl")[0], 400)
        # A view copies through its host's frame, and no view stops a viewer (this app has no shutdown).
        self.assertEqual((self.http("POST", "/__cad/clipboard", {})[0], self.http("POST", "/__cad/shutdown", {})[0]), (404, 405))

    def test_a_view_keeps_the_library_and_the_persons_settings_in_this_servers_own(self) -> None:
        # The model on screen joins the library this server lists on the home, and is counted once, here.
        with mock.patch.object(self.server.analytics, "opened") as counted:
            status, recents = self.http("POST", "/__cad/recents", {"action": "open", "path": self.bracket})
        self.assertEqual((status, [entry["path"] for entry in recents["recents"]]), (200, [self.bracket.replace(os.sep, "/")]))
        counted.assert_called_once()
        self.assertEqual([entry["path"] for entry in self.launch("cad_home")["recents"]], [self.bracket.replace(os.sep, "/")])
        # Its picture, kept and read back by name.
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes(64)).decode("ascii")
        [entry] = self.http("POST", "/__cad/recents", {"action": "thumbnail", "path": self.bracket, "png": png})[1]["recents"]
        self.assertEqual(self.http("GET", f"/__cad/thumbnail?name={entry['thumbnail']}"), (200, base64.b64decode(png)))
        # The home's Open, and the person's answer on the analytics card: the CAD app's own.
        with mock.patch.object(FilePicker, "choose", return_value=self.loose):
            self.assertEqual(self.http("POST", "/__cad/pick", {}), (200, {"path": self.loose.replace(os.sep, "/")}))
        with mock.patch.object(self.server.analytics, "choose", return_value={}) as answered:
            self.assertEqual(self.http("POST", "/__cad/analytics", {"share": False})[0], 200)
        answered.assert_called_once_with(False, by="app")

    def test_a_sync_says_when_the_catalog_moved_and_how_a_watched_build_stands(self) -> None:
        watch = {"file": self.bracket, "previews": [self.bracket]}
        first = self.call("cad_sync", {"view": "v1", "surface": "tab", "watch": watch})["structuredContent"]
        catalog = self.http("GET", f"http://cad.invalid/__cad/catalog?file={quote(self.bracket, safe='')}")[1]
        # The revision a view compares is the one its catalog read carries.
        self.assertEqual(first["catalog"]["revision"], catalog["revision"])
        self.assertEqual(first["previews"][0]["file"], self.bracket)
        Path(self.bracket).write_bytes(STL.replace(b"vertex 1 0 0", b"vertex 2 0 0"))
        with mock.patch("cadgen.mcp.tunnel.CATALOG_REVISION_SECONDS", 0):
            moved = self.call("cad_sync", {"view": "v1", "surface": "tab", "watch": watch})["structuredContent"]
        self.assertNotEqual(moved["catalog"]["revision"], first["catalog"]["revision"])
        # A watch that will not read is said in the answer, and the agent's requests still reach the view.
        self.server.views.post(["v1"], {"type": "show", "model": "/a.step"})
        refused = self.call("cad_sync", {"view": "v1", "surface": "tab", "watch": {"file": "parts/bracket.stl"}})
        self.assertFalse(refused.get("isError"))
        self.assertIn("error", refused["structuredContent"]["catalog"])
        self.assertEqual([event["type"] for event in refused["structuredContent"]["events"]], ["show"])

    def test_the_tunnel_never_holds_a_call_open(self) -> None:
        # The preview feed's ``after`` holds a request until the build ledger moves. The host relays every
        # call through a few slots all its views share, so here it is answered at once; the feed paces itself.
        url = f"http://cad.invalid/__cad/preview?file={quote(self.bracket, safe='')}&after=epoch%3A1"
        with mock.patch("cadgen.viewer.preview.preview_update", return_value={"state": "disconnected"}) as update:
            self.assertEqual(self.http("GET", url)[0], 200)
        self.assertEqual((update.call_args.args[0], update.call_args.kwargs["after"]), (self.bracket, None))

    def test_the_sidebar_and_a_tab_with_nothing_to_show_open_the_home(self) -> None:
        self.http("POST", "/__cad/recents", {"action": "open", "path": self.bracket})
        home = self.launch("cad_home")
        self.assertEqual((home["page"], home["model"], home["surface"], [entry["path"] for entry in home["recents"]]),
                         ("home", None, "sidebar", [self.bracket.replace(os.sep, "/")]))
        fresh = Server(page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "other"))
        fresh.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": CODEX}, None)
        context = RequestContext(1, {"threadId": "t"})
        tab = fresh.handle("tools/call", {"name": "cad_tab", "arguments": {}}, context)["structuredContent"]["launch"]
        self.assertEqual((tab["page"], tab["model"], tab["surface"], tab["recents"]), ("home", None, "tab", []))

    def test_the_page_reveals_a_file_by_its_absolute_path(self) -> None:
        target = Path(self.bracket).resolve()
        # The desktop's file manager is never opened by a test: the call it would make is recorded.
        with mock.patch("cadgen.viewer.reveal.sys.platform", "darwin"), mock.patch("cadgen.viewer.reveal.subprocess.run") as run:
            self.assertEqual(self.http("POST", "/__cad/reveal", {"path": self.bracket})[0], 204)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0], ["/usr/bin/open", "-R", str(target)])
            for path in ("parts/bracket.stl", str(self.workspace / "parts" / "nope.stl")):  # relative; not there
                self.assertGreaterEqual(self.http("POST", "/__cad/reveal", {"path": path})[0], 400, path)
            run.assert_called_once()


class SidebarAcrossThreadsTest(_Session):
    """Codex runs the sidebar page in a thread, and a server process, of its own. An agent in any
    thread reaches the sidebar view a person touched last -- shown a model, read, captured -- as it
    reaches its own tabs, rather than opening a tab beside a model already on screen."""

    def setUp(self) -> None:
        super().setUp()
        # The sidebar's own process: another server over the same state directory.
        self.sidebar = Server(page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "state"))
        self.sidebar.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": CODEX}, None)
        self.model = self.bracket

    def on_sidebar(self, name: str, arguments: dict) -> dict:
        context = RequestContext(1, {"threadId": "sidebar-thread"})
        return self.sidebar.handle("tools/call", {"name": name, "arguments": arguments}, context)["structuredContent"]

    def sync_sidebar(self, **extra) -> dict:
        return self.on_sidebar("cad_sync", {"view": "s1", "surface": "sidebar", "model": self.model, **extra})

    def test_an_agent_with_no_tab_shows_reads_and_captures_the_model_in_the_sidebar(self) -> None:
        self.sync_sidebar(state={"model": self.model, "selection": [f"{self.model}#o1.f1"]}, focused=True)
        # The model the sidebar shows already: no tab, and nothing to send it.
        self.assertEqual(self.call("cad_show", {"path": self.bracket})["structuredContent"],
                         {"delivered": 1, "view": "s1", "sidebar": True})
        self.assertEqual(self.sync_sidebar()["events"], [])
        # What the sidebar reported, read at once.
        (view,) = self.call("cad_view")["structuredContent"]["views"]
        self.assertEqual((view["view"], view["surface"], view["selection"]), ("s1", "sidebar", [f"{self.model}#o1.f1"]))
        # Another model: the sidebar takes it on its next sync.
        self.assertEqual(self.call("cad_show", {"path": self.loose})["structuredContent"]["view"], "s1")
        (event,) = self.sync_sidebar()["events"]
        self.assertEqual((event["type"], event["launch"]["model"]), ("show", self.loose))
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
        self.assertEqual(self.call("cad_show", {"path": self.bracket})["structuredContent"]["view"], "s1")
        time.sleep(0.02)
        self.call("cad_sync", {"view": "t1", "surface": "agent", "model": self.model, "focused": True})
        self.assertEqual(self.call("cad_show", {"path": self.bracket})["structuredContent"]["view"], "t1")
        # The sidebar's process sees no thread's tab: only sidebar views are shared.
        self.assertEqual([view["view"] for view in self.on_sidebar("cad_view", {})["views"]], ["s1"])

    def test_a_sidebar_that_stopped_syncing_is_not_reached(self) -> None:
        self.sync_sidebar(focused=True)
        stale = time.time() - 120
        for published in (self.tmp / "state" / "sidebar-views").glob("*.json"):
            os.utime(published, (stale, stale))
        self.assertEqual(self.call("cad_show", {"path": self.bracket})["structuredContent"], {"delivered": 0})


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
        partial = {"extensions": {**RENDERS_APPS["extensions"], "dev.texttocad/tabs": {"entrypoints": ["thread"]}}}
        server = Server(page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "state2"))
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
        first = self.launch("cad_show", {"path": self.bracket})
        second = self.launch("cad_show", {"path": self.loose})
        self.assertNotEqual(first["view"], second["view"])
        self.assertLess((first["order"]["createdAt"], first["order"]["seq"]), (second["order"]["createdAt"], second["order"]["seq"]))
        self.assertEqual((first["page"], first["surface"], second["model"]), ("viewer", "inline", self.loose))
        shown = self.call("cad_show", {"path": self.bracket})
        self.assertIn(shown["structuredContent"]["launch"]["view"], shown["content"][0]["text"])

    def test_the_agent_reads_only_the_view_it_names(self) -> None:
        model = self.bracket
        view = self.launch("cad_show", {"path": model})["view"]
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


class TextServerTest(_Session):
    """A client that renders no MCP Apps: cad_show answers with the model's link in the CAD Viewer."""

    client = {"name": "some-cli", "version": "1"}
    viewer_url = staticmethod(lambda: "http://127.0.0.1:3245/")

    def test_cad_show_links_the_model_in_this_machines_viewer(self) -> None:
        tools = self.server.handle("tools/list", {}, None)["tools"]
        self.assertEqual([(tool["name"], "_meta" in tool) for tool in tools], [("cad_show", False), ("cad_analytics", False)])
        self.assertIn("cannot show CAD views", self.initialized["instructions"])
        shown = self.call("cad_show", {"path": self.bracket})
        # Text alone: Claude Code shows a result's structured content in place of its text.
        self.assertNotIn("structuredContent", shown)
        self.assertIn(f"http://127.0.0.1:3245/?file={quote(self.bracket.replace(os.sep, '/'), safe='/:')}", shown["content"][0]["text"])
        self.assertNotIn("Showing", shown["content"][0]["text"])
        # The Viewer adds the model to the library once it shows it; a link alone adds nothing.
        self.assertEqual(self.server.recents.list(), [])

    def test_a_text_client_reaches_no_page_tool(self) -> None:
        # No page answers a card or reaches the viewer's routes here, so neither does the agent.
        for name in ("cad_http", "cad_sync", "cad_open"):
            with self.assertRaises(RpcError, msg=name):
                self.call(name, {"method": "POST", "url": "/__cad/analytics", "view": "v", "surface": "tab"})

    def test_a_newer_release_comes_with_the_first_cad_show_and_only_the_first(self) -> None:
        offer_an_update(self)
        first = self.call("cad_show", {"path": self.bracket})["content"]
        self.assertIn('Ask your agent to update to the latest version ("Update text-to-cad to 99.0.0 from '
                      'https://github.com/earthtojake/text-to-cad"), or install manually', first[-1]["text"])
        self.assertEqual(len(self.call("cad_show", {"path": self.bracket})["content"]), 1)

    def test_a_viewer_that_will_not_start_leaves_the_command_to_run(self) -> None:
        from cadgen.mcp.browser import ViewerUnavailable

        def refuse() -> str:
            raise ViewerUnavailable("no port")

        self.server._viewer_url = refuse
        failed = self.call("cad_show", {"path": self.bracket})
        self.assertTrue(failed["isError"])
        self.assertIn("`cadgen viewer --host 127.0.0.1 --json --detach`", failed["content"][0]["text"])

    def test_an_app_that_renders_without_advertising_it_can_be_told(self) -> None:
        from unittest import mock

        with mock.patch.dict(os.environ, {"CADGEN_MCP_PRESENTATION": "inline"}):
            server = Server(page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "other"))
            server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": self.client}, None)
        self.assertIn("ui", {tool["name"]: tool for tool in server.handle("tools/list", {}, None)["tools"]}["cad_show"]["_meta"])


class ImportBudgetTest(unittest.TestCase):
    def test_initialize_and_tools_list_wake_no_cad_kernel(self) -> None:
        code = (
            "import sys\n"
            "from cadgen.mcp.server import Server\n"
            "server = Server()\n"
            "server.handle('initialize', {'protocolVersion': '2025-06-18'}, None)\n"
            "server.handle('tools/list', {}, None)\n"
            "print(','.join(name for name in ('OCP', 'build123d', 'ezdxf', 'cadgen.mcp.tunnel', 'cadgen.viewer.recents') if name in sys.modules))\n"
        )
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env={**os.environ})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "")


class TunnelBoundTest(_Session):
    """However long a body, no ``cad_http`` reply carries more than one message holds: a host's
    stdio reader stops at its ceiling and closes the connection (``tunnel.MAX_REPLY_BYTES``)."""

    def sized(self, method: str, url: str, headers: dict | None = None, body: bytes = b"") -> tuple[dict, int]:
        """The reply, and the length of the message that carried it."""
        result = self.call("cad_http", {"method": method, "url": url, "headers": headers or {},
                                        "body": base64.b64encode(body).decode("ascii")})
        return result["structuredContent"], len(json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}, separators=(",", ":")))

    def read(self, url: str, part: int = MAX_REPLY_BYTES, after_first=lambda: None) -> tuple[bytes, list[int], set[str]]:
        """``url`` read as the page reads it, ``part`` bytes a range: the body, each message's length,
        and the etags of its parts."""
        whole, sizes, etags = b"", [], set()
        while True:
            reply, size = self.sized("GET", url, {"range": f"bytes={len(whole)}-{len(whole) + part - 1}"})
            sizes.append(size)
            whole += base64.b64decode(reply["body"])
            if reply["status"] == 200:
                return whole, sizes, etags
            self.assertEqual(reply["status"], 206)
            etags.add(reply["headers"]["etag"])
            if len(whole) == int(reply["headers"]["content-range"].rsplit("/", 1)[1]):
                return whole, sizes, etags
            if len(sizes) == 1:
                after_first()

    def test_a_body_three_times_the_bound_travels_in_parts_none_longer_than_one_message(self) -> None:
        model = self.workspace / "parts" / "big.stl"
        body = os.urandom(3 * MAX_REPLY_BYTES + 7)
        model.write_bytes(body)
        url = f"http://cad.invalid/__cad/asset?file={quote(str(model), safe='')}"
        whole, sizes, etags = self.read(url)
        self.assertEqual((whole, len(sizes), len(etags)), (body, 4, 1))
        self.assertLessEqual(max(sizes), MESSAGE_BOUND)
        # Rewritten between two parts, it is another body: its next part says so, and the page's read fails.
        _, _, etags = self.read(url, after_first=lambda: model.write_bytes(body[::-1]))
        self.assertEqual(len(etags), 2)
        # An answer the page did not ask for in parts is refused rather than sent.
        reply, size = self.sized("GET", url)
        self.assertEqual((reply["status"], size < 1024), (502, True))

    def test_a_tessellation_body_read_in_parts_is_the_body_its_object_names(self) -> None:
        from tests.python.support.tessellation import tessellation_fixture

        fixture = tessellation_fixture()
        body = base64.b64decode(fixture["bytes"])
        digest = fixture["facts"]["object"]
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.tmp / "store")}):
            from cadgen.store.tess_cache import write_tessellation_cache

            write_tessellation_cache(fixture["key"], body)
            whole, sizes, etags = self.read(f"http://cad.invalid/__tess_cache/{fixture['key']}.tess?object={digest}&maxBytes={len(body)}", part=256)
        self.assertEqual((whole, etags), (body, {f'"{digest}"'}))
        self.assertGreaterEqual(len(sizes), 3)

    def test_a_screenshot_longer_than_one_message_is_refused_not_sent(self) -> None:
        viewer = self.poll_as("v1", "tab", 1, self.bracket, png=base64.b64encode(b"\x89PNG" + bytes(MAX_REPLY_BYTES)).decode("ascii"))
        shot = self.call("cad_screenshot")
        viewer.join(10)
        self.assertTrue(shot["isError"])
        self.assertIn("more than one message", shot["content"][0]["text"])
        self.assertLess(len(json.dumps(shot)), 1024)

class TunnelBodyTest(unittest.TestCase):
    """A large JSON body crosses the host's channel gzipped and says so; nothing else changes."""

    def test_only_a_large_json_body_travels_gzipped(self) -> None:
        import gzip

        from cadgen.mcp.tunnel import GZIP_JSON_MIN_BYTES, ViewerTunnel

        catalog = {"entries": [{"file": f"/parts/part-{index}.step", "hash": f"{index:064x}"} for index in range(200)]}
        binary = bytes(range(256)) * 256

        class Routes:
            def handle(self, request, response) -> None:
                if request.path == "/__cad/catalog":
                    response.send_json(200, catalog)
                elif request.path == "/__cad/preview":
                    response.send_json(200, {"state": "idle"})
                else:
                    response.send_bytes(200, binary, "application/octet-stream")

        tunnel = ViewerTunnel()

        def call(path: str, method: str = "GET") -> dict:
            with mock.patch.object(ViewerTunnel, "app", Routes()):
                return tunnel.serve(method=method, url=f"http://cad.invalid{path}", headers={}, body=b"")

        written = json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertGreater(len(written), GZIP_JSON_MIN_BYTES)
        reply = call("/__cad/catalog")
        self.assertEqual(reply["encoding"], "gzip")
        self.assertEqual(gzip.decompress(base64.b64decode(reply["body"])), written)
        self.assertEqual(int(reply["headers"]["content-length"]), len(written))
        self.assertLess(len(reply["body"]), len(base64.b64encode(written)) // 4)
        for path, method, body in (("/__cad/preview", "GET", b'{"state":"idle"}'),
                                   ("/__tess_cache/a.tess", "GET", binary), ("/__cad/catalog", "HEAD", b"")):
            reply = call(path, method)
            self.assertNotIn("encoding", reply)
            self.assertEqual(base64.b64decode(reply["body"]), body)


if __name__ == "__main__":
    unittest.main()
