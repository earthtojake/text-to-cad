"""`cadgen mcp`: its catalog, the launches it computes, and the agent driving a view, for both kinds of host."""

from __future__ import annotations

import base64
import errno
import json
import ntpath
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
from cadgen.mcp.browser import OPEN, OPENED, deliver
from cadgen.mcp.shim import initialize_params
from cadgen.mcp.protocol import RequestContext, RpcError
from cadgen.viewer.recents import RecentStore
from cadgen.mcp.server import _AGENT_TOOLS, FOLLOWS, Server, local_path
from cadgen.mcp.operations import START, STARTS, check_arguments
from cadgen.mcp.tunnel import MAX_REPLY_BYTES
from cadgen.mcp.ui import AppPage

CODEX = {"name": "codex-mcp-client", "title": "Codex", "version": "0.159.0"}
CLAUDE = {"name": "claude-ai", "version": "0.1.0"}
# What `codex exec` 0.163 sent with a tool call (measured), less its ids: the turn renders no app.
CODEX_EXEC_TURN = {"x-codex-turn-metadata": {"thread_source": "user", "turn_trigger": "exec", "sandbox": "seatbelt"}}
# The host the shim found among its parents (``host.launcher``): the Codex app's app server, and `codex exec`.
CODEX_APP = {"host": "codex app-server", "renders": True, "command": "codex -c features.code_mode_host=true app-server"}
CODEX_EXEC = {"host": "codex exec", "renders": False, "command": "codex exec --skip-git-repo-check"}
RENDERS_APPS = {"extensions": {"io.modelcontextprotocol/ui": {"mimeTypes": ["text/html;profile=mcp-app"]}}}
OTHER_HOST = {"name": "some-desktop-app", "version": "0.1.0"}
DECLARES_TABS = {"extensions": {**RENDERS_APPS["extensions"], "dev.texttocad/tabs": {"entrypoints": ["global", "thread", "file"]}}}
STL = b"solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"
# The longest message a reply may make: its body's base64 and an envelope. 5.6 MB, under the
# 10 MiB the MCP TypeScript SDK's stdio reader stops at.
MESSAGE_BOUND = MAX_REPLY_BYTES * 4 // 3 + 4096
# What the page's client sends with every POST: the viewer refuses one without its header.
GUARDED = {"x-cadgen-viewer": "1", "content-type": "application/json"}


def as_codex_spells_it(path: str) -> str:
    """A local file's path as Codex's file tree hands it to ``cad_file``: on Windows, forward slashes
    and a slash before the drive (``/C:/Users/...``); elsewhere, the path itself."""
    return "/" + path.replace("\\", "/") if os.name == "nt" else path


def offer_an_update(test: unittest.TestCase) -> None:
    """A feed read today that offers 99.0.0 to the Claude plugin installed from GitHub (`cadgen/updates.py`)."""
    state = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, state, ignore_errors=True)
    patched = mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(state), "CADGEN_INSTALL_CHANNEL": "claude-github", "CADGEN_AUTO_UPDATED": "", "CI": "",
                                           "CADGEN_UPDATE_CHECK": ""})
    patched.start()
    test.addCleanup(patched.stop)
    (state / "versions.json").write_text(json.dumps({"checked": time.time(), "feed": {"latest": "99.0.0"}}), encoding="utf-8")


PAGE_TOOLS = ("cad_sync", "cad_capture_reply")


def as_page(server: Server, name: str, arguments: dict | None) -> dict:
    """A page tool's arguments as the page sends them: with its session's app capability, which
    its launch's metadata delivered (``createServer`` in apps/mcp)."""
    arguments = dict(arguments or {})
    if name in PAGE_TOOLS:
        arguments.setdefault("app", server._app_token)
    return arguments


class _Session(unittest.TestCase):
    """A server, a bracket in a project folder and a model elsewhere, greeted by ``client``."""

    client = CODEX
    offered: dict = {}
    launcher: dict | None = None
    viewer_url = None

    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))  # as the viewer spells every path (ids.canonical)
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
        # What is opened in a browser, recorded and never opened: through the redirect file
        # (``browser_open``) in this test's own engine folder, on a machine with a display. A text
        # host's page is opened by the stdio peer (``call`` delivers each result as it does), the
        # card's Open in browser by the server (``browser_opener``).
        self.opened: list[str] = []
        engine = self.tmp / "opener"
        engine.mkdir(mode=0o700)
        from cadgen.viewer import browser_open
        for patched in (mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(engine)}),
                        mock.patch.object(browser_open, "display_refusal", return_value=None)):
            patched.start()
            self.addCleanup(patched.stop)
        self.server = Server(page=AppPage(page), recents=RecentStore(self.tmp / "state"), viewer_url=self.viewer_url,
                             browser_opener=lambda target: self.opened.append(target) or True)
        self.initialized = self.server.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": self.offered,
                                                             "clientInfo": self.client}, self.launcher), None)

    def record(self, target: str) -> bool:
        self.opened.append(target)
        return True

    def call(self, name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        """A tool's result as the host is given it: through the stdio peer, which opens what it asks
        and tells the server whether it opened (``tell``)."""
        context = RequestContext(1, {"threadId": "t", **(meta or {})})
        return deliver(self.server.handle("tools/call", {"name": name, "arguments": as_page(self.server, name, arguments)}, context),
                       self.record, self.tell)

    def tell(self, url: str, opened: bool) -> None:
        """The stdio peer's word on a page it was asked to open, on its session (``Proxy._tell``)."""
        self.server.notify(OPENED, {"url": url, "opened": opened})

    def launch(self, name: str, arguments: dict | None = None, meta: dict | None = None) -> dict:
        return self.call(name, arguments, meta)["structuredContent"]["launch"]

    def http(self, method: str, url: str, body: bytes | dict = b"", headers: dict | None = None) -> tuple[int, dict | bytes]:
        """A request the page sends through ``cad_http``: its status, and its body (JSON decoded). A
        dict body is a JSON POST, with the header the page's client sends."""
        if isinstance(body, dict):
            body, headers = json.dumps(body).encode("utf-8"), {**GUARDED, **(headers or {})}
        reply = self.call("cad_http", {"method": method, "url": url, "headers": {"x-cadgen-app": self.server._app_token, **(headers or {})},
                                       "body": base64.b64encode(body).decode("ascii")})["structuredContent"]
        data = base64.b64decode(reply.get("body") or "")
        if reply.get("encoding") == "gzip":
            import gzip
            data = gzip.decompress(data)
        return reply["status"], json.loads(data) if reply["headers"].get("content-type", "").startswith("application/json") else data

    def poll_as(self, view: str, surface: str, answers: int, model: str | None = None, png: str = "iVBORw0KGgo=") -> threading.Thread:
        """A view syncing as the page does (every few milliseconds here): its first sync registers it
        and says what it shows; it answers ``answers`` captures with ``png``."""
        state = {"model": model, "selection": [f"{model}#f:bracket.make_box1.1"]}
        first = self.call("cad_sync", {"view": view, "surface": surface, "model": model, "state": state})["structuredContent"]["events"]

        def page() -> None:
            asked = 0
            pending = first
            while asked < answers:
                events = pending or self.call("cad_sync", {"view": view, "surface": surface, "model": model})["structuredContent"]["events"]
                pending = []
                if not events:
                    time.sleep(0.002)
                for event in events:
                    asked += 1
                    self.call("cad_capture_reply", {"requestId": event["requestId"], "png": png})

        viewer = threading.Thread(target=page, daemon=True)
        viewer.start()
        return viewer


    def waited(self) -> threading.Event:
        """Set once a call is waiting for a view to sync into being (``ViewRegistry.wait`` found none yet)."""
        waiting = threading.Event()
        real = self.server.views.wait

        def wait(found, *, timeout):
            def looked():
                result = found()
                if result is None:
                    waiting.set()
                return result

            return real(looked, timeout=timeout)

        patched = mock.patch.object(self.server.views, "wait", wait)
        patched.start()
        self.addCleanup(patched.stop)
        return waiting

    def opens_later(self, view: str, surface: str, model: str) -> threading.Thread:
        """A view the host is still loading: it syncs for the first time once a call waits for it, then
        answers one capture."""
        waiting = self.waited()

        def load() -> None:
            if waiting.wait(10):
                self.poll_as(view, surface, 1, model).join(10)

        loading = threading.Thread(target=load, daemon=True)
        loading.start()
        self.addCleanup(loading.join, 10)
        return loading

    def syncs_later(self, view: str, surface: str, model: str) -> threading.Thread:
        """A tab the host is still loading: its first sync comes once a call waits for it."""
        waiting = self.waited()

        def load() -> None:
            if waiting.wait(10):
                self.call("cad_sync", {"view": view, "surface": surface, "model": model})

        loading = threading.Thread(target=load, daemon=True)
        loading.start()
        self.addCleanup(loading.join, 10)
        return loading


class TabServerTest(_Session):
    """Codex: tab surfaces the agent opens once and then drives."""

    launcher = CODEX_APP

    def test_http_app_authority_is_in_ui_metadata_and_scoped_to_its_session(self) -> None:
        launch = self.call("cad_tab")
        token = launch["_meta"]["dev.texttocad/httpToken"]
        self.assertNotIn(token, json.dumps({key: value for key, value in launch.items() if key != "_meta"}))
        other = Server(page=self.server.page)
        other.handle("initialize", initialize_params({"clientInfo": CODEX}), None)
        def request(url, headers=None, body=None, method="GET"):
            return self.call("cad_http", {"method": method, "url": url, "headers": headers or {},
                                         "body": base64.b64encode(json.dumps(body).encode()).decode() if body is not None else ""})
        for url in ("/__cad/server", "/__cad/pick", "/__cad/recents", "/__cad/asset?file=x",
                    "/__cad/analytics/activity", "/__cad/analytics?share=true"):
            with self.subTest(url=url):
                blocked = request(url, {"x-cadgen-viewer": "1", "range": "bytes=0-20", "if-range": "guessed"})
                self.assertTrue(blocked["isError"])
                self.assertEqual(blocked["structuredContent"]["status"], 403)
        for bad in ("guessed", other._app_token):
            self.assertTrue(request("/__cad/analytics", {"x-cadgen-app": bad})["isError"])
        self.assertEqual(request("/__cad/server", {"X-Cadgen-App": token})["structuredContent"]["status"], 200)
        # App opt-in still reaches the ordinary route and its cross-site POST guard.
        self.assertEqual(request("/__cad/analytics", {"x-cadgen-app": token}, {"share": True}, "POST")["structuredContent"]["status"], 403)
        with mock.patch.object(self.server.analytics, "choose", return_value={"saved": True}) as choose:
            reply = request("/__cad/analytics", {"x-cadgen-app": token, **GUARDED}, {"share": True}, "POST")
            self.assertEqual(reply["structuredContent"]["status"], 200)
            choose.assert_called_once_with(True, by="app")
        # Removed settings routes have exactly the unknown-route behavior, even with a stale file.
        settings = self.tmp / "settings.json"
        settings.write_text('{"features":{"quickEdit":false}}', encoding="utf-8")
        with mock.patch.dict(os.environ, {"CADGEN_STATE_DIR": str(self.tmp)}):
            for method, expected in (("GET", 404), ("POST", 404)):
                self.assertEqual(request("/__cad/features", {"x-cadgen-app": token, **GUARDED}, method=method)["structuredContent"]["status"], expected)

    def test_the_page_tools_answer_only_the_page_that_holds_the_session_s_capability(self) -> None:
        # The host is asked to keep app-only tools from the model; the server does not rely on it.
        other = Server(page=self.server.page)
        other.handle("initialize", initialize_params({"clientInfo": CODEX}), None)
        context = RequestContext(1, {"threadId": "t"})
        calls = (("cad_sync", {"view": "v9", "surface": "tab", "state": {"selection": ["forged"]}}),
                 ("cad_capture_reply", {"requestId": "r1", "png": "iVBORw0KGgo="}))
        for name, arguments in calls:
            for token in (None, "", "guessed", other._app_token):
                with self.subTest(name=name, token=token):
                    sent = arguments if token is None else {**arguments, "app": token}
                    refused = self.server.handle("tools/call", {"name": name, "arguments": sent}, context)
                    self.assertTrue(refused["isError"])
        self.assertNotIn("v9", self.server.views)
        self.assertEqual(self.call("cad_sync", {"view": "v9", "surface": "tab"})["structuredContent"], {"events": []})
        self.assertIn("v9", self.server.views)

    def test_the_catalog_names_every_surface_and_keeps_page_tools_from_the_agent(self) -> None:
        tools = {tool["name"]: tool for tool in self.server.handle("tools/list", {}, None)["tools"]}
        meta = {name: tool.get("_meta", {}) for name, tool in tools.items()}
        entrypoints = {name: value["openai/ui"]["entrypoints"][0]["type"] for name, value in meta.items()
                       if "entrypoints" in value.get("openai/ui", {})}
        self.assertEqual(entrypoints, {"cad_home": "global", "cad_tab": "thread", "cad_file": "file"})
        agent = {name for name, value in meta.items() if value.get("ui", {}).get("visibility") != ["app"]}
        self.assertEqual(agent, {"cad_open", "cad_show", "cad_view", "cad_screenshot", "cad_http"} | START.keys())
        # The page's own: its sync, its answer to a capture, and the viewer's routes, which carry the rest.
        page = {name for name, value in meta.items() if value.get("ui", {}).get("visibility") == ["app"]} - set(entrypoints)
        self.assertEqual(page, {"cad_sync", "cad_capture_reply"})
        # All but one read: cad_http turns the person's telemetry off when they ask.
        self.assertEqual([name for name, tool in tools.items() if not tool["annotations"]["readOnlyHint"]], ["cad_http", "cad_export", "cad_snapshot"])
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
        opened = self.launch("cad_open", {"source": self.bracket})
        self.assertEqual({key: opened[key] for key in ("protocol", "page", "model", "surface")},
                         {"protocol": 9, "page": "viewer", "model": self.bracket, "surface": "agent"})
        # No tolerance: the page reads each part's one display mesh by its key.
        self.assertEqual(sorted(opened), ["model", "notice", "page", "pick", "platform", "protocol", "surface",
                                          "version"])
        # The thread's tab reopens on what the thread last opened.
        self.assertEqual(self.launch("cad_tab")["model"], self.bracket)
        refused = self.call("cad_open", {"source": "parts/bracket.stl"})
        self.assertTrue(refused["isError"])
        self.assertIn("is not an absolute path", refused["content"][0]["text"])
        # A file the host hands over is shown alone: the host's own file tree is its navigation.
        handed = self.launch("cad_file", {"file": {"name": "loose.stl", "resourceUri": "codex-resource://app-1"}},
                             {"openai/resource": {"path": as_codex_spells_it(self.loose)}})
        self.assertEqual((handed["model"], handed["surface"]), (self.loose, "file"))
        # A launch adds nothing to the library: the view does, once the model is on screen.
        self.assertEqual(self.server.recents.list(), [])

    def test_a_bad_path_is_the_tools_answer_not_a_protocol_error(self) -> None:
        missing = self.call("cad_open", {"source": str(self.workspace / "parts" / "nope.step")})
        self.assertTrue(missing["isError"])
        self.assertIn("No file at", missing["content"][0]["text"])
        (self.workspace / "notes.txt").write_text("x", encoding="utf-8")
        self.assertIn("is not one", self.call("cad_open", {"source": str(self.workspace / "notes.txt")})["content"][0]["text"])
        # A script is no document: refused as any file CAD does not open is, by cad_open and cad_show.
        script = self.workspace / "parts.py"
        script.write_text("print(1)\n", encoding="utf-8")
        for tool in ("cad_open", "cad_show"):
            self.assertIn("is not one", self.call(tool, {"source": str(script)})["content"][0]["text"], tool)
            self.assertIn("No file at", self.call(tool, {"source": f"{script}::cube"})["content"][0]["text"], tool)

    def test_native_board_is_shown_and_reread_through_the_file_service(self) -> None:
        from tests.python.support.kicad_board import write_board, BOARD
        from urllib.parse import urlencode
        board = write_board(self.workspace)
        self.call("cad_sync", {"view": "v1", "surface": "tab"})
        shown = self.call("cad_show", {"source": str(board)})
        self.assertEqual(shown["structuredContent"], {"delivered": 1, "view": "v1"})
        event, = self.call("cad_sync", {"view": "v1", "surface": "tab"})["structuredContent"]["events"]
        self.assertEqual(event["launch"]["model"], str(board))
        route = "/__cad/plot?" + urlencode({"file": str(board)})
        status, first = self.http("GET", route)
        self.assertEqual(status, 200)
        board.write_text(BOARD.replace('(width 1) (layer "F.Cu") (net "VBUS")',
                                       '(width 0.5) (layer "F.Cu") (net "VBUS")'), encoding="utf-8")
        status, changed = self.http("GET", route)
        self.assertEqual(status, 200)
        self.assertNotEqual(first, changed)
        self.assertEqual(self.opened, [])

    def test_cad_show_reaches_the_polling_view_without_opening_one(self) -> None:
        self.assertEqual(self.call("cad_show", {"source": self.bracket})["structuredContent"], {"delivered": 0})
        # A sync answers at once: the first registers the view, the next carries what was sent since.
        self.assertEqual(self.call("cad_sync", {"view": "v1", "surface": "tab"})["structuredContent"], {"events": []})
        shown = self.call("cad_show", {"source": self.bracket})
        self.assertEqual(shown["structuredContent"], {"delivered": 1, "view": "v1"})
        (event,) = self.call("cad_sync", {"view": "v1", "surface": "tab"})["structuredContent"]["events"]
        self.assertEqual((event["type"], event["launch"]["model"]), ("show", self.bracket))

    def test_a_tabs_launches_and_shows_carry_their_page_for_open_in_browser_and_the_file_handlers_none(self) -> None:
        asked = []

        def page(model=None) -> str:
            asked.append(model)
            return f"http://127.0.0.1:3245/{'doc' if model else ''}?token=t"

        self.server._viewer_url = page
        # The sidebar's home, the thread's tab and the agent's: each the page of what it shows, and no
        # engine origin (a tab's card always has its channel).
        for name, arguments, url in (("cad_home", {}, "http://127.0.0.1:3245/?token=t"),
                                     ("cad_open", {"source": self.bracket}, "http://127.0.0.1:3245/doc?token=t"),
                                     ("cad_tab", {}, "http://127.0.0.1:3245/doc?token=t")):
            launch = self.launch(name, arguments)
            self.assertEqual((launch.get("browser"), "engine" in launch), (url, False), name)
        # A show the sync carries to a tab carries its page too.
        self.call("cad_sync", {"view": "v1", "surface": "tab"})
        self.call("cad_show", {"source": self.loose, "view": "v1"})
        (event,) = self.call("cad_sync", {"view": "v1", "surface": "tab"})["structuredContent"]["events"]
        self.assertEqual((event["launch"]["model"], event["launch"]["browser"]), (self.loose, "http://127.0.0.1:3245/doc?token=t"))
        # The file handler shows its file alone, with no Open in browser: no page is asked for it.
        before = len(asked)
        launch = self.launch("cad_file", {"file": {"name": "bracket.stl", "resourceUri": "x"}}, {"openai/resource": {"path": self.bracket}})
        self.assertEqual((launch["surface"], "browser" in launch, "engine" in launch, len(asked)), ("file", False, False, before))

    def test_the_hosts_file_view_shows_the_file_it_opened_and_nothing_the_agent_shows(self) -> None:
        self.call("cad_sync", {"view": "f1", "surface": "file", "model": self.bracket})
        # The agent reads it by its id...
        (view,) = self.call("cad_view")["structuredContent"]["views"]
        self.assertEqual((view["view"], view["surface"]), ("f1", "file"))
        # ...but shows nothing in it: unnamed, a show finds no viewer; named, it is refused, unless
        # the view shows that file already.
        self.assertEqual(self.call("cad_show", {"source": self.loose})["structuredContent"], {"delivered": 0})
        refused = self.call("cad_show", {"source": self.loose, "view": "f1"})
        self.assertTrue(refused["isError"])
        self.assertIn("shows that file alone", refused["content"][0]["text"])
        self.assertEqual(self.call("cad_show", {"source": self.bracket, "view": "f1"})["structuredContent"], {"delivered": 0, "view": "f1"})
        self.assertEqual(self.call("cad_sync", {"view": "f1", "surface": "file", "model": self.bracket})["structuredContent"]["events"], [])

    def test_the_agent_reads_and_captures_what_the_open_view_shows(self) -> None:
        self.assertTrue(self.call("cad_screenshot")["isError"])
        model = self.bracket
        state = {"model": model, "selection": [f"{model}#f:bracket.make_box1.1"]}
        viewer = self.poll_as("v1", "tab", 1, model)
        # What the view said it shows on its sync, answered at once: nothing asks the view.
        self.assertEqual(self.call("cad_view")["structuredContent"], {"views": [{"view": "v1", "surface": "tab", **state}]})
        shot = self.call("cad_screenshot")
        viewer.join(10)
        self.assertFalse(viewer.is_alive())
        self.assertEqual(shot["content"][0], {"type": "image", "data": "iVBORw0KGgo=", "mimeType": "image/png"})
        self.assertEqual(shot["structuredContent"], {"view": "v1", "model": model})

    def test_a_capture_right_after_cad_open_waits_for_the_tab_to_open(self) -> None:
        # An agent opens a tab and captures it at once, before the host has loaded it: the capture
        # waits for its first sync rather than saying no viewer is open.
        self.call("cad_open", {"source": self.bracket})
        self.opens_later("v1", "agent", self.bracket)
        shot = self.call("cad_screenshot")
        self.assertNotIn("isError", shot)
        self.assertEqual(shot["structuredContent"], {"view": "v1", "model": self.bracket})

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
        self.assertEqual((self.http("POST", "/__cad/clipboard", {})[0], self.http("POST", "/__cad/shutdown", {})[0]), (404, 404))

    def test_a_view_keeps_the_library_and_the_persons_settings_in_this_servers_own(self) -> None:
        # The model on screen joins the library this server lists on the home (each path in this
        # platform's spelling), and is counted once, here.
        with mock.patch.object(self.server.analytics, "opened") as counted:
            status, recents = self.http("POST", "/__cad/recents", {"action": "open", "path": self.bracket.replace(os.sep, "/")})
        self.assertEqual((status, [entry["path"] for entry in recents["recents"]]), (200, [self.bracket]))
        counted.assert_called_once()
        self.assertEqual([entry["path"] for entry in self.launch("cad_home")["recents"]], [self.bracket])
        # Its picture, kept and read again by name.
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + bytes(64)).decode("ascii")
        [entry] = self.http("POST", "/__cad/recents", {"action": "thumbnail", "path": self.bracket, "png": png})[1]["recents"]
        self.assertEqual(self.http("GET", f"/__cad/thumbnail?name={entry['thumbnail']}"), (200, base64.b64decode(png)))
        # The home's Open, and the person's answer on the app menu's Share anonymous usage data: the CAD app's own.
        with mock.patch.object(FilePicker, "choose", return_value=self.loose):
            self.assertEqual(self.http("POST", "/__cad/pick", {}), (200, {"path": self.loose.replace(os.sep, "/")}))
        with mock.patch.object(self.server.analytics, "choose", return_value={}) as answered:
            self.assertEqual(self.http("POST", "/__cad/analytics", {"share": False})[0], 200)
        answered.assert_called_once_with(False, by="app")

    def test_a_sync_renews_the_lease_of_the_address_it_names(self) -> None:
        # A heartbeat names the document by its canonical address: a model address is never made a path.
        synced = []
        self.server.sync_document = synced.append
        for model in ("C:/parts/plate.py::plate", self.bracket):
            self.call("cad_sync", {"view": "v1", "surface": "tab", "model": model})
        self.assertEqual(synced, ["C:/parts/plate.py::plate", self.bracket])

    def test_a_sync_says_when_the_catalog_moved(self) -> None:
        watch = {"file": self.bracket}
        first = self.call("cad_sync", {"view": "v1", "surface": "tab", "watch": watch})["structuredContent"]
        catalog = self.http("GET", f"http://cad.invalid/__cad/catalog?file={quote(self.bracket, safe='')}")[1]
        # The revision a view compares is the one its catalog read carries.
        self.assertEqual(first["catalog"]["revision"], catalog["revision"])
        # No build feed rides on it: a document the engine serves tells its view of a new version.
        self.assertNotIn("previews", first)
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
        # The host relays every call through a few slots all its views share: an engine document's
        # wait for its next version is answered at once (the page asks again a second later), and a
        # document the engine is still reading holds a call no longer than a drawing does.
        from cadgen.mcp.tunnel import ENGINE_HOLD_SECONDS, ENGINE_RETRY_MS

        documents = self.server.tunnel.app.engine_documents
        self.assertEqual((documents.hold_seconds, documents.retry_ms), (ENGINE_HOLD_SECONDS, ENGINE_RETRY_MS))

    def test_the_sidebar_and_a_tab_with_nothing_to_show_open_the_home(self) -> None:
        self.http("POST", "/__cad/recents", {"action": "open", "path": self.bracket})
        home = self.launch("cad_home")
        self.assertEqual((home["page"], home["model"], home["surface"], [entry["path"] for entry in home["recents"]]),
                         ("home", None, "sidebar", [self.bracket]))
        fresh = Server(page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "other"))
        fresh.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": CODEX}), None)
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
    thread reads and captures the sidebar view a person touched last, as it does its own tabs. A
    model it shows goes beside its thread, though: Codex keeps the sidebar page running while the
    person is in a thread, so a model sent there lands where nobody is looking (the bug in 0.7.12:
    "open the tom2.step model" reported it shown, and no tab opened). Only a named view reaches it."""

    launcher = CODEX_APP

    def setUp(self) -> None:
        super().setUp()
        # The sidebar's own process: another server over the same state directory.
        from cadgen.mcp.sidebar import SidebarViews
        self.sidebar = Server(page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "state"),
                              sidebar_views=SidebarViews(self.server.sidebar_views.registry))
        self.sidebar.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": CODEX},
                                                            CODEX_APP), None)
        self.model = self.bracket

    def on_sidebar(self, name: str, arguments: dict) -> dict:
        context = RequestContext(1, {"threadId": "sidebar-thread"})
        return self.sidebar.handle("tools/call", {"name": name, "arguments": as_page(self.sidebar, name, arguments)},
                                   context)["structuredContent"]

    def sync_sidebar(self, **extra) -> dict:
        return self.on_sidebar("cad_sync", {"view": "s1", "surface": "sidebar", "model": self.model, **extra})

    def test_an_agent_with_no_tab_opens_one_and_reads_and_captures_the_sidebar(self) -> None:
        self.sync_sidebar(state={"model": self.model, "selection": [f"{self.model}#f:bracket.make_box1.1"]}, focused=True)
        # No tab in this thread: the agent is told to open one, and the sidebar is sent nothing.
        shown = self.call("cad_show", {"source": self.loose})
        self.assertEqual(shown["structuredContent"], {"delivered": 0})
        self.assertIn("call cad_open", shown["content"][0]["text"].lower())
        self.assertEqual(self.sync_sidebar()["events"], [])
        # What the sidebar reported, read at once.
        (view,) = self.call("cad_view")["structuredContent"]["views"]
        self.assertEqual((view["view"], view["surface"], view["selection"]), ("s1", "sidebar", [f"{self.model}#f:bracket.make_box1.1"]))
        # Named, the sidebar takes another model on its next sync.
        self.assertEqual(self.call("cad_show", {"source": self.loose, "view": "s1"})["structuredContent"],
                         {"delivered": 1, "view": "s1", "sidebar": True})
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

    def test_a_show_goes_to_the_threads_tab_whatever_was_touched_last(self) -> None:
        with mock.patch.object(self.server.views, "_clock", lambda: time.monotonic() - 1):  # touched a second ago
            self.call("cad_sync", {"view": "t1", "surface": "agent", "model": self.model})
        self.sync_sidebar(focused=True)
        # The sidebar was touched last, so it is what the agent reads; a model it shows goes to its tab.
        self.assertEqual(self.call("cad_view")["structuredContent"]["views"][0]["view"], "s1")
        self.assertEqual(self.call("cad_show", {"source": self.loose})["structuredContent"]["view"], "t1")
        self.assertEqual(self.sync_sidebar()["events"], [])
        # The sidebar's process sees no thread's tab: only sidebar views are shared.
        self.assertEqual([view["view"] for view in self.on_sidebar("cad_view", {})["views"]], ["s1"])

    def test_a_sidebar_that_stopped_syncing_is_not_reached(self) -> None:
        self.sync_sidebar(focused=True)
        self.sidebar.sidebar_views.registry._clock = lambda: time.monotonic() + 120
        self.assertEqual(self.call("cad_view")["structuredContent"]["views"], [])
        self.assertEqual(self.call("cad_show", {"source": self.bracket, "view": "s1"})["structuredContent"], {"delivered": 0})

    def test_sidebar_sync_and_capture_create_no_disk_registry(self):
        self.sync_sidebar(focused=True)
        self.call("cad_show", {"source": self.loose, "view": "s1"})
        (event,) = self.sync_sidebar()["events"]
        self.assertEqual(event["launch"]["model"], self.loose)
        self.assertFalse((self.tmp / "state" / "sidebar-views").exists())
        self.sidebar.sidebar_views.close()
        self.assertEqual(self.call("cad_view")["structuredContent"]["views"], [])


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
        server.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": partial, "clientInfo": OTHER_HOST}), None)
        tools = {tool["name"] for tool in server.handle("tools/list", {}, None)["tools"]}
        self.assertNotIn("cad_open", tools)


class InlineServerTest(_Session):
    """Claude and every other MCP Apps host: each cad_show mounts a new view in the chat."""

    client = CLAUDE
    offered = RENDERS_APPS

    def test_a_host_that_renders_apps_never_has_a_browser_opened(self) -> None:
        self.assertIn("launch", self.call("cad_show", {"source": self.bracket}, CODEX_EXEC_TURN)["structuredContent"])
        self.assertEqual(self.opened, [])

    def test_an_inline_host_shows_models_with_one_tool_and_is_told_so(self) -> None:
        tools = {tool["name"]: tool for tool in self.server.handle("tools/list", {}, None)["tools"]}
        agent = {name for name, tool in tools.items() if tool.get("_meta", {}).get("ui", {}).get("visibility") != ["app"]}
        # A chat shows files: no home.
        self.assertEqual(agent, {"cad_show", "cad_view", "cad_screenshot", "cad_http"} | START.keys())
        uri = tools["cad_show"]["_meta"]["ui"]["resourceUri"]
        self.assertFalse(any(key.startswith("openai/") for tool in tools.values() for key in tool.get("_meta", {})))
        self.assertEqual((tools["cad_view"]["inputSchema"]["required"], tools["cad_screenshot"]["inputSchema"]["required"]), (["view"], ["view"]))
        self.assertNotIn("experimental", self.initialized["capabilities"])
        self.assertIn("cad_show", self.initialized["instructions"])
        # The same app, told before it greets the host that it is shown inline.
        page = self.server.handle("resources/read", {"uri": uri}, None)["contents"][0]["text"]
        self.assertEqual(page, '<!doctype html><meta name="cad-presentation" content="inline"><title>CAD</title>')
        self.assertNotEqual(uri, AppPage(self.tmp / "app").uri)

    def test_a_cards_launch_carries_its_page_and_the_engine_s_origin_without_a_call(self) -> None:
        from cadgen.mcp.browser import ViewerUnavailable

        asked = []

        def page(model=None) -> str:
            asked.append(model)
            return "http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab?token=1.mac"

        self.server._viewer_url = page
        # Without a call: the page a text client's cad_show links, day link and all, and its origin.
        launch = self.launch("cad_show", {"source": self.bracket})
        self.assertEqual((launch["browser"], launch["engine"], asked),
                         ("http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab?token=1.mac", "http://127.0.0.1:3245", [self.bracket]))
        # The engine gives no page: the launch goes without one, and the card still mounts.

        def refuse(_model=None) -> str:
            raise ViewerUnavailable("CAD Viewer client is not built")

        self.server._viewer_url = refuse
        launch = self.launch("cad_show", {"source": self.bracket})
        self.assertNotIn("browser", launch)
        self.assertNotIn("engine", launch)
        # A tab host's launches carry the page alone, for Open in browser: its card always has its channel.
        tabs = Server(page=self.server.page, recents=self.server.recents, viewer_url=page)
        tabs.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": DECLARES_TABS,
                                                     "clientInfo": OTHER_HOST}), None)
        home = tabs.handle("tools/call", {"name": "cad_home", "arguments": as_page(tabs, "cad_home", {})},
                           RequestContext(1, {"threadId": "t"}))["structuredContent"]["launch"]
        self.assertEqual((home["page"], "browser" in home, "engine" in home), ("home", True, False))

    def test_the_cards_open_in_browser_opens_the_page_from_this_process_through_a_redirect_file(self) -> None:
        from cadgen.mcp.browser import ViewerUnavailable
        from cadgen.viewer import browser_open

        engine = self.tmp / "engine"
        engine.mkdir(mode=0o700)
        opened: list[tuple[str, str]] = []

        def opener(target: str) -> bool:
            path = Path(local_path(target))
            opened.append((target, path.read_text(encoding="utf-8")))
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            return True

        self.server._viewer_url = lambda model=None: "http://127.0.0.1:3245/" + ("doc" if model else "") + "?token=t"
        self.server._browser_opener = opener
        route = "http://cad.invalid/__cad/browser/open"
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(engine)}), \
                mock.patch.object(browser_open, "display_refusal", return_value=None):
            self.assertEqual(self.http("POST", route, {"model": self.bracket}), (200, {"opened": True}))
            self.assertEqual(self.http("POST", route, {"model": None}), (200, {"opened": True}))
            self.assertEqual(len(opened), 2)
            for (target, page), url in zip(opened, ("http://127.0.0.1:3245/doc?token=t", "http://127.0.0.1:3245/?token=t")):
                self.assertTrue(target.startswith("file:") and "token" not in target, target)
                self.assertIn(f"url={url}", page)
            # A read is refused, the body names a document and never a URL, and an agent never reaches it.
            self.assertEqual(self.http("GET", route)[0], 405)
            self.assertEqual(self.http("POST", route, {"model": 7})[0], 400)
            agent = self.call("cad_http", {"method": "POST", "url": route, "body": base64.b64encode(b"{}").decode()})
            self.assertEqual(agent["structuredContent"]["status"], 403)
            self.assertEqual(len(opened), 2)
            # No browser here, or no page: 503 in words, when the card opens its launch's page through its host.
            self.server._browser_opener = lambda _target: False
            status, answer = self.http("POST", route, {})
            self.assertEqual((status, "no browser" in answer["error"]), (503, True))

            def refuse(_model=None) -> str:
                raise ViewerUnavailable("CAD Viewer client is not built")

            self.server._viewer_url = refuse
            self.assertEqual(self.http("POST", route, {}), (503, {"error": "CAD Viewer client is not built"}))
        with mock.patch.object(browser_open, "display_refusal", return_value="there is no display to open a browser on"):
            self.assertEqual(self.http("POST", route, {}), (503, {"error": "there is no display to open a browser on"}))

    def test_an_inline_cards_sandbox_may_fetch_the_engine_s_origin_and_a_tab_s_is_served_as_it_was(self) -> None:
        # An inline host is asked to let the card fetch the engine; a server given no engine adds nothing.
        uri = self.server.handle("resources/list", {}, None)["resources"][0]["uri"]
        server = Server(page=self.server.page, recents=self.server.recents, engine_origin="http://127.0.0.1:3245")
        server.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": RENDERS_APPS,
                                                       "clientInfo": CLAUDE}), None)
        for listed in (server.handle("resources/list", {}, None)["resources"][0],
                       server.handle("resources/read", {"uri": uri}, None)["contents"][0]):
            self.assertEqual(listed["_meta"]["ui"]["csp"]["connectDomains"], ["data:", "blob:", "http://127.0.0.1:3245"])
        self.assertEqual(self.server.handle("resources/list", {}, None)["resources"][0]["_meta"]["ui"]["csp"]["connectDomains"],
                         ["data:", "blob:"])
        # A host that shows tabs is served what it was, engine or not: its card always has its channel.
        tabs = Server(page=self.server.page, recents=self.server.recents, engine_origin="http://127.0.0.1:3245")
        tabs.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": DECLARES_TABS,
                                                     "clientInfo": OTHER_HOST}), None)
        self.assertEqual(tabs.handle("resources/list", {}, None)["resources"][0]["_meta"]["ui"]["csp"]["connectDomains"],
                         ["data:", "blob:"])

    def test_a_mounted_view_warms_the_engine_s_meshing_pool(self) -> None:
        # The engine starts its pool with the first view, never with a build (law 19).
        warmed = []
        self.server.warm = lambda: warmed.append(True)
        self.launch("cad_show", {"source": self.bracket})
        self.assertEqual(warmed, [True])

    def test_each_show_mounts_a_new_view_named_and_ordered(self) -> None:
        first = self.launch("cad_show", {"source": self.bracket})
        second = self.launch("cad_show", {"source": self.loose})
        self.assertNotEqual(first["view"], second["view"])
        self.assertLess((first["order"]["createdAt"], first["order"]["seq"]), (second["order"]["createdAt"], second["order"]["seq"]))
        self.assertEqual((first["page"], first["surface"], second["model"]), ("viewer", "inline", self.loose))
        shown = self.call("cad_show", {"source": self.bracket})
        self.assertIn(shown["structuredContent"]["launch"]["view"], shown["content"][0]["text"])

    def test_a_step_and_an_engine_document_are_shown_and_the_agent_is_told_so(self) -> None:
        # The page draws both from what the cadgen engine serves of them (``cadgen.viewer.xbf``).
        tools = {tool["name"]: tool for tool in self.server.handle("tools/list", {}, None)["tools"]}
        self.assertIn("(STEP, XBF, STL, GLB, 3MF, DXF, URDF, SDF, KiCad PCB)", tools["cad_show"]["description"])
        self.assertIn("(STEP, XBF, STL, GLB, 3MF, DXF, URDF, SDF, KiCad PCB)", self.initialized["instructions"])
        for name in ("arm.xbf", "arm.step", "ARM.STP"):
            model = self.workspace / "parts" / name
            model.write_bytes(b"\0")
            with self.subTest(model=name):
                shown = self.launch("cad_show", {"source": str(model)})
                self.assertEqual((shown["page"], shown["model"]), ("viewer", str(model)))

    def test_the_agent_reads_only_the_view_it_names(self) -> None:
        model = self.bracket
        view = self.launch("cad_show", {"source": model})["view"]
        self.assertIn("pass the view", self.call("cad_view")["content"][0]["text"])
        viewer = self.poll_as(view, "inline", 1, model)
        # Another chat's view, served by the same process and touched since, is never the one read.
        self.call("cad_sync", {"view": "cad-other", "surface": "inline", "model": model, "focused": True})
        described = self.call("cad_view", {"view": view})["structuredContent"]["views"]
        self.assertEqual(described, [{"view": view, "surface": "inline", "model": model, "selection": [f"{model}#f:bracket.make_box1.1"]}])
        self.assertEqual(self.call("cad_screenshot", {"view": view})["content"][0]["data"], "iVBORw0KGgo=")
        viewer.join(10)
        # A view a newer one replaced closes itself, and is no longer there to read.
        self.call("cad_sync", {"view": view, "surface": "inline", "model": model, "closed": True})
        self.assertIn("not open", self.call("cad_view", {"view": view})["content"][0]["text"])


    def test_a_capture_right_after_cad_show_waits_for_the_card_and_says_when_it_never_opens(self) -> None:
        view = self.launch("cad_show", {"source": self.bracket})["view"]
        self.opens_later(view, "inline", self.bracket)
        self.assertEqual(self.call("cad_screenshot", {"view": view})["content"][0]["data"], "iVBORw0KGgo=")
        # A card the chat never draws (the person has not allowed it, or it is collapsed) is said so, not "closed".
        unseen = self.launch("cad_show", {"source": self.loose})["view"]
        with mock.patch("cadgen.mcp.server.OPENING_SECONDS", 0.2):
            shot = self.call("cad_screenshot", {"view": unseen})
        self.assertTrue(shot["isError"])
        self.assertIn("has not opened yet", shot["content"][0]["text"])
        # A token no cad_show of this server named is not waited for.
        with mock.patch.object(self.server.views, "wait", side_effect=AssertionError("waited for an unknown view")):
            self.assertIn("not open", self.call("cad_screenshot", {"view": "cad-9-unknown"})["content"][0]["text"])


    def test_the_app_capability_is_unguessable_ui_only_and_scoped_to_its_session(self) -> None:
        def agent(method, url, body=b"", headers=None):
            return self.call("cad_http", {"method": method, "url": url, "headers": headers or {},
                                          "body": base64.b64encode(body).decode("ascii")})
        shown = self.call("cad_show", {"source": self.bracket})
        token = shown["_meta"]["dev.texttocad/httpToken"]
        self.assertGreaterEqual(len(token), 40)
        self.assertNotIn(token, json.dumps({k: v for k, v in shown.items() if k != "_meta"}))
        self.assertNotIn(token, json.dumps(self.server.handle("resources/read", {"uri": self.server.page.uri}, None)))
        # Without it: one route, two exact requests.
        for method, url in (("GET", "/__cad/server"), ("GET", "/__cad/recents"), ("GET", "/__cad/analytics?x=1"),
                            ("POST", "/__cad/analytics/activity"), ("GET", "/__cad/./analytics/../server"),
                            ("GET", "http://cad.invalid/__cad/catalog?file=" + quote(self.bracket, safe=""))):
            with self.subTest(url=url):
                self.assertEqual(agent(method, url)["structuredContent"]["status"], 403)
        self.assertEqual(agent("HEAD", "/__cad/analytics")["structuredContent"]["status"], 405)
        self.assertEqual(agent("GET", "/__cad/analytics")["structuredContent"]["status"], 200)
        # A wrong capability is refused, not served as the agent; another session's is wrong here.
        stale = agent("GET", "/__cad/server", headers={"x-cadgen-app": token[:-1] + "x"})
        self.assertTrue(stale["isError"])
        self.assertIn("open CAD again", stale["content"][0]["text"])
        other = Server(page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "state-other"))
        other.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": self.offered,
                                                     "clientInfo": self.client}), None)
        self.assertTrue(other.handle("tools/call", {"name": "cad_http", "arguments": {"method": "GET", "url": "/__cad/server",
                        "headers": {"x-cadgen-app": token}}}, RequestContext(1, {}))["isError"])
        # With it, the page reaches every viewer route; the header never reaches the route.
        reply = agent("GET", "/__cad/server", headers={"x-cadgen-app": token})["structuredContent"]
        self.assertEqual(reply["status"], 200)


class TextServerTest(_Session):
    """A client that renders no MCP Apps: cad_show answers with the model's link in the CAD Viewer."""

    client = {"name": "some-cli", "version": "1"}
    # The engine's launch registers the model and answers its page, `/<id>`.
    viewer_url = staticmethod(lambda model=None: "http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab")

    def test_a_client_with_no_page_has_no_app_capability(self) -> None:
        self.assertNotIn("_meta", self.call("cad_show", {"source": self.bracket}))
        refused = self.call("cad_http", {"method": "GET", "url": "/__cad/server",
                                         "headers": {"x-cadgen-app": self.server._app_token}})
        self.assertTrue(refused["isError"])

    def test_cad_show_opens_the_model_in_the_browser_and_says_so_with_its_url(self) -> None:
        tools = self.server.handle("tools/list", {}, None)["tools"]
        self.assertEqual([(tool["name"], "_meta" in tool) for tool in tools], [("cad_show", False), ("cad_http", False)] + [(name, False) for name in START])
        self.assertIn("cannot show CAD views", self.initialized["instructions"])
        told = []
        self.server._browser_opened = told.append
        shown = self.call("cad_show", {"source": self.bracket})
        # Text alone: Claude Code shows a result's structured content in place of its text.
        self.assertNotIn("structuredContent", shown)
        self.assertEqual(shown["content"][0]["text"],
                         "bracket.stl opened in your browser at http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab.\n"
                         "This app shows no CAD view itself: give the user this URL. The page follows the model: "
                         "rebuilds for a document, saves for a file, so show a model once, not after every rebuild.")
        # Opened once, through a redirect file (the page's token is on no command line), and the engine
        # told by the peer that it opened.
        (target,) = self.opened
        self.assertTrue(target.startswith("file:"), target)
        self.assertEqual(told, [self.bracket])
        # The Viewer adds the model to the library once it shows it; a link alone adds nothing.
        self.assertEqual(self.server.recents.list(), [])

    def test_cad_show_takes_a_path_or_a_document_id_and_says_so(self) -> None:
        cad_show = {tool["name"]: tool for tool in self.server.handle("tools/list", {}, None)["tools"]}["cad_show"]
        for said in (cad_show["description"], cad_show["inputSchema"]["properties"]["source"]["description"],
                     self.initialized["instructions"]):
            self.assertIn("document id", said)
            self.assertIn("absolute path", said)
        refused = self.call("cad_show", {"id": "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"})
        self.assertTrue(refused["isError"])
        self.assertEqual(refused["content"][0]["text"], "cad_show: missing source; unknown id. cad_show takes source; source "
                                                        "is a document id (running a model's script prints it) or a CAD "
                                                        "file's absolute path.")

    def test_a_model_a_browser_page_shows_already_is_not_opened_again(self) -> None:
        self.server._in_browser = lambda model: model == self.bracket
        shown = self.call("cad_show", {"source": self.bracket})["content"][0]["text"]
        self.assertTrue(shown.startswith("bracket.stl is already open in your browser at "
                                         "http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab; nothing was opened."), shown)
        self.assertIn("give the user this URL", shown)
        self.assertEqual(self.opened, [])

    def test_where_no_browser_opens_the_answer_is_the_url(self) -> None:
        from cadgen.viewer import browser_open

        with mock.patch.object(browser_open, "display_refusal", return_value="there is no display to open a browser on"):
            shown = self.call("cad_show", {"source": self.bracket})["content"][0]["text"]
        self.assertTrue(shown.startswith("No browser can be opened from here (there is no display to open a browser on); "
                                         "bracket.stl's page is http://127.0.0.1:3245/"), shown)
        self.assertEqual(self.opened, [])

    def test_the_server_asks_its_stdio_peer_to_open_the_page_and_opens_nothing_itself(self) -> None:
        # The engine runs in the environment of whatever started it: its open could reach another
        # person's browser, or none. Its answer names the page; the peer opens it and strips the ask.
        import webbrowser

        from cadgen.viewer import browser_open

        def refuse(*_args, **_kwargs):
            raise AssertionError("the server opened a browser")

        told: list[str] = []
        self.server._browser_opened = told.append
        context = RequestContext(1, {"threadId": "t"})
        with mock.patch.object(webbrowser, "open", refuse), mock.patch.object(browser_open, "open_page", refuse):
            raw = self.server.handle("tools/call", {"name": "cad_show", "arguments": {"source": self.bracket}}, context)
        link = "http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"
        self.assertEqual(raw["_meta"], {OPEN: {"url": link, "said": f"bracket.stl opened in your browser at {link}.",
                                               "failed": "No browser can be opened from here ({reason}); "
                                                         f"bracket.stl's page is {link}."}})
        # Asked, not opened: nothing counts the page as open in a browser until the peer says it opened.
        self.assertEqual((self.opened, told), ([], []))
        delivered = deliver(raw, self.record, self.tell)
        self.assertNotIn("_meta", delivered)
        (target,) = self.opened
        self.assertTrue(target.startswith("file:") and "token" not in target, target)
        self.assertEqual(told, [self.bracket])
        # Where the peer's open fails, its words say so in place of the claim that it opened.
        failed = deliver(self.server.handle("tools/call", {"name": "cad_show", "arguments": {"source": self.loose}}, context),
                         lambda _target: False)["content"][0]["text"]
        self.assertTrue(failed.startswith("No browser can be opened from here (no browser could be started here"), failed)
        self.assertNotIn("opened in your browser", failed)

    def test_a_page_the_peer_opened_is_open_and_a_second_show_opens_nothing(self) -> None:
        pages: set[str] = set()
        self.server._in_browser, self.server._browser_opened = pages.__contains__, pages.add
        first = self.call("cad_show", {"source": self.bracket})["content"][0]["text"]
        self.assertTrue(first.startswith("bracket.stl opened in your browser at "), first)
        self.assertEqual(pages, {self.bracket})  # the peer said it opened
        again = self.call("cad_show", {"source": self.bracket})["content"][0]["text"]
        self.assertTrue(again.startswith("bracket.stl is already open in your browser at "), again)
        self.assertEqual(len(self.opened), 1)

    def test_a_page_the_peer_could_not_open_is_not_open_and_the_next_show_opens_it_again(self) -> None:
        pages: set[str] = set()
        self.server._in_browser, self.server._browser_opened = pages.__contains__, pages.add
        tried: list[str] = []

        def failing(target: str) -> bool:  # a BROWSER that exits non-zero
            tried.append(target)
            return False

        context = RequestContext(1, {"threadId": "t"})
        for attempt in (1, 2):
            shown = deliver(self.server.handle("tools/call", {"name": "cad_show", "arguments": {"source": self.bracket}}, context),
                            failing, self.tell)["content"][0]["text"]
            self.assertTrue(shown.startswith("No browser can be opened from here (no browser could be started here (no "
                                             "display, or no browser to open)); bracket.stl's page is "
                                             "http://127.0.0.1:3245/"), (attempt, shown))
        self.assertEqual((len(tried), pages), (2, set()))

    def test_a_word_on_a_page_this_session_did_not_ask_its_peer_for_counts_nothing_as_open(self) -> None:
        told: list[str] = []
        self.server._browser_opened = told.append
        link = "http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"
        context = RequestContext(1, {"threadId": "t"})
        # Never asked: a client's word alone counts no page as open.
        self.server.notify(OPENED, {"url": link, "opened": True})
        self.server.notify(OPENED, {"url": "http://127.0.0.1:3245/elsewhere", "opened": True})
        # Asked of this session's peer: another session's word on that page is not this one's.
        other = Server(page=self.server.page, recents=self.server.recents, viewer_url=self.viewer_url,
                       browser_opened=told.append)
        other.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": {},
                                                      "clientInfo": self.client}), None)
        self.assertIn(OPEN, self.server.handle("tools/call", {"name": "cad_show", "arguments": {"source": self.bracket}},
                                               context)["_meta"])
        other.notify(OPENED, {"url": link, "opened": True})
        self.assertEqual(told, [])
        # The peer's first word settles the ask: an open it said failed stays unopened, whatever follows.
        self.server.notify(OPENED, {"url": link, "opened": False})
        self.server.notify(OPENED, {"url": link, "opened": True})
        self.assertEqual(told, [])
        self.assertIn(OPEN, self.server.handle("tools/call", {"name": "cad_show", "arguments": {"source": self.bracket}},
                                               context)["_meta"])
        self.server.notify(OPENED, {"url": link, "opened": True})
        self.server.notify(OPENED, {"url": link, "opened": True})
        self.assertEqual(told, [self.bracket])

    def test_a_client_with_no_stdio_peer_is_given_the_url_and_nothing_opens(self) -> None:
        # A direct HTTP client: no peer said it opens a browser, so nothing does.
        told = []
        server = Server(page=self.server.page, recents=self.server.recents, viewer_url=self.viewer_url,
                        browser_opened=told.append)
        server.handle("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": self.client}, None)
        shown = server.handle("tools/call", {"name": "cad_show", "arguments": {"source": self.bracket}},
                              RequestContext(1, {"threadId": "t"}))
        self.assertNotIn("_meta", shown)
        self.assertTrue(shown["content"][0]["text"].startswith(
            "bracket.stl's page is http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab; nothing was opened, "
            "as this client opens no browser.\nThis app shows no CAD view itself: give the user this URL."), shown)
        # Its word that the page opened anyway is no open this server asked for.
        server.notify(OPENED, {"url": "http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab", "opened": True})
        self.assertEqual((self.opened, told), ([], []))

    def test_a_peer_that_can_open_no_browser_is_asked_for_none(self) -> None:
        from cadgen.viewer import browser_open

        with mock.patch.object(browser_open, "display_refusal", return_value="this is a remote session with no display to open a browser on"):
            server = Server(page=self.server.page, recents=self.server.recents, viewer_url=self.viewer_url)
            server.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": {},
                                                           "clientInfo": self.client}), None)
        shown = server.handle("tools/call", {"name": "cad_show", "arguments": {"source": self.bracket}},
                              RequestContext(1, {"threadId": "t"}))
        self.assertNotIn("_meta", shown)
        self.assertTrue(shown["content"][0]["text"].startswith(
            "No browser can be opened from here (this is a remote session with no display to open a browser on); "
            "bracket.stl's page is http://127.0.0.1:3245/"), shown)

    def test_a_text_client_reaches_no_page_tool(self) -> None:
        # No page answers a card or reaches the viewer's routes here, so neither does the agent.
        for name in ("cad_sync", "cad_open"):
            with self.assertRaises(RpcError, msg=name):
                self.call(name, {"method": "POST", "url": "/__cad/analytics", "view": "v", "surface": "tab"})

    def test_a_newer_release_comes_with_the_first_cad_show_and_only_the_first(self) -> None:
        offer_an_update(self)
        first = self.call("cad_show", {"source": self.bracket})["content"]
        self.assertIn('Ask your agent to update to the latest version ("Update text-to-cad to 99.0.0 from '
                      'https://github.com/earthtojake/text-to-cad"), or install manually', first[-1]["text"])
        self.assertEqual(len(self.call("cad_show", {"source": self.bracket})["content"]), 1)

    def test_a_viewer_that_will_not_start_leaves_the_command_to_run(self) -> None:
        from cadgen.mcp.browser import ViewerUnavailable

        def refuse(_model=None) -> str:
            raise ViewerUnavailable("no port")

        self.server._viewer_url = refuse
        failed = self.call("cad_show", {"source": self.bracket})
        self.assertTrue(failed["isError"])
        self.assertIn(f"`cadgen viewer --host 127.0.0.1 --json {self.bracket}`", failed["content"][0]["text"])

    def test_an_app_that_renders_without_advertising_it_can_be_told(self) -> None:
        from unittest import mock

        with mock.patch.dict(os.environ, {"CADGEN_MCP_PRESENTATION": "inline"}):
            server = Server(page=AppPage(self.tmp / "app"), recents=RecentStore(self.tmp / "other"))
            server.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": self.client}), None)
        self.assertIn("ui", {tool["name"]: tool for tool in server.handle("tools/list", {}, None)["tools"]}["cad_show"]["_meta"])


class CodexExecTest(_Session):
    """`codex exec` greets the server as the Codex app does, and renders no app. Its launcher says so
    (the shim's parent process is `codex exec`), and on 0.163 each call's turn metadata does too
    (``turn_trigger: exec``): its cad_open and cad_show claim no tab."""

    client = CODEX
    launcher = CODEX_APP
    viewer_url = staticmethod(lambda model=None: "http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab?token=t")
    EXEC = CODEX_EXEC_TURN
    # The Codex app's own turn (its app server's, measured): no trigger.
    APP = {"x-codex-turn-metadata": {"sandbox": "seatbelt"}}

    def greet(self, launcher: dict | None, **kwargs) -> Server:
        server = Server(page=self.server.page, recents=self.server.recents, viewer_url=self.viewer_url,
                        browser_opener=lambda target: self.opened.append(target) or True, **kwargs)
        server.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": CODEX},
                                                      launcher), None)
        return server

    def test_an_exec_turn_opens_the_browser_once_and_never_claims_a_tab(self) -> None:
        pages: set[str] = set()
        self.server._in_browser = lambda model: model in pages
        self.server._browser_opened = pages.add
        opened = self.call("cad_open", {"source": self.bracket}, self.EXEC)
        self.assertNotIn("structuredContent", opened)
        self.assertNotIn("_meta", opened)
        text = opened["content"][0]["text"]
        self.assertTrue(text.startswith("bracket.stl opened in your browser at http://127.0.0.1:3245/"), text)
        self.assertNotIn("tab", text)
        self.assertEqual(len(self.opened), 1)
        # The next turn (`codex exec resume`, a new server process: the engine still knows the page).
        again = self.greet(None, in_browser=lambda model: model in pages)
        shown = deliver(again.handle("tools/call", {"name": "cad_show", "arguments": {"source": self.bracket}},
                                     RequestContext(1, {"threadId": "t", **self.EXEC})), self.record)["content"][0]["text"]
        self.assertTrue(shown.startswith("bracket.stl is already open in your browser at http://127.0.0.1:3245/"), shown)
        self.assertEqual(len(self.opened), 1)

    def test_a_server_codex_exec_launched_is_a_text_server_whatever_its_calls_say(self) -> None:
        # codex-cli 0.153 sends no turn metadata: the launcher alone says it.
        server = self.greet(CODEX_EXEC)
        self.assertEqual([tool["name"] for tool in server.handle("tools/list", {}, None)["tools"]][:2], ["cad_show", "cad_http"])
        shown = deliver(server.handle("tools/call", {"name": "cad_show", "arguments": {"source": self.bracket}},
                                      RequestContext(1, {"threadId": "t"})), self.record)["content"][0]["text"]
        self.assertTrue(shown.startswith("bracket.stl opened in your browser at http://127.0.0.1:3245/"), shown)
        self.assertEqual(len(self.opened), 1)

    def test_the_codex_apps_own_turns_keep_their_tabs_and_open_no_browser(self) -> None:
        opened = self.call("cad_open", {"source": self.bracket}, self.APP)
        self.assertEqual(opened["content"][0]["text"],
                         f"{self.bracket} is open in a new CAD tab. From now on, use cad_show to show models in it.")
        self.assertEqual(opened["structuredContent"]["launch"]["model"], self.bracket)
        # A show in the same turn goes to the tab cad_open launched, which the host is still opening.
        self.syncs_later("tab-1", "agent", self.bracket)
        self.assertEqual(self.call("cad_show", {"source": self.loose}, self.APP)["content"][0]["text"], f"Showing {self.loose} in CAD.")
        events = self.call("cad_sync", {"view": "tab-1", "surface": "agent", "model": self.bracket})["structuredContent"]["events"]
        self.assertEqual([(event["type"], event["launch"]["model"]) for event in events], [("show", self.loose)])
        self.assertEqual(self.opened, [])

    def test_a_tab_still_opening_is_said_so_and_shown_the_model_once_it_opens(self) -> None:
        self.call("cad_open", {"source": self.bracket}, self.APP)
        with mock.patch("cadgen.mcp.server.OPENING_SECONDS", 0.1):
            shown = self.call("cad_show", {"source": self.loose}, self.APP)
        self.assertEqual(shown["content"][0]["text"], f"The CAD tab cad_open opened is still opening; it shows {self.loose} once it opens.")
        self.assertNotIn("No CAD viewer", shown["content"][0]["text"])
        events = self.call("cad_sync", {"view": "tab-1", "surface": "agent", "model": self.bracket})["structuredContent"]["events"]
        self.assertEqual([(event["type"], event["launch"]["model"]) for event in events], [("show", self.loose)])
        self.assertEqual(self.opened, [])


class UnconfirmedCodexTest(_Session):
    """A Codex client nothing else speaks for (its launcher unknown, no turn metadata): its name gives it
    Codex's catalog, never the claim that a tab opened. The next call decides from evidence."""

    client = CODEX
    viewer_url = staticmethod(lambda model=None: "http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab?token=t")

    def test_cad_open_says_where_the_model_is_either_way_and_opens_no_browser(self) -> None:
        opened = self.call("cad_open", {"source": self.bracket})
        self.assertEqual(opened["content"][0]["text"],
                         f"Where this app shows CAD tabs, {self.bracket} opens in a new CAD tab with this answer; where it "
                         "shows none, the user can see it in their browser at http://127.0.0.1:3245/6f1c2a4e-1b2c-5d3e-8f4a-"
                         "0123456789ab?token=t: give them this URL. Do not tell the user a tab opened. Use cad_show next: "
                         "it says where a model went.")
        self.assertEqual(opened["structuredContent"]["launch"]["model"], self.bracket)
        self.assertEqual(self.opened, [])

    def test_a_tab_that_never_comes_means_this_host_shows_none(self) -> None:
        self.call("cad_open", {"source": self.bracket})
        with mock.patch("cadgen.mcp.server.OPENING_SECONDS", 0.1):
            shown = self.call("cad_show", {"source": self.bracket})["content"][0]["text"]
        self.assertTrue(shown.startswith("bracket.stl opened in your browser at http://127.0.0.1:3245/"), shown)
        self.assertEqual(len(self.opened), 1)
        self.assertNotIn("tab", self.call("cad_open", {"source": self.loose})["content"][0]["text"])

    def test_a_view_reaching_the_server_proves_tabs_over_a_turn_that_says_exec(self) -> None:
        self.call("cad_open", {"source": self.bracket})
        self.syncs_later("tab-1", "agent", self.bracket)
        self.assertEqual(self.call("cad_show", {"source": self.loose})["content"][0]["text"], f"Showing {self.loose} in CAD.")
        self.assertIn("in a new CAD tab. From now on", self.call("cad_open", {"source": self.loose}, CODEX_EXEC_TURN)["content"][0]["text"])
        self.assertEqual(self.opened, [])


TEXT_CLIENT = {"name": "some-cli", "version": "1"}
# Each catalog a host is listed, by the greeting that lists it.
CATALOGS = {"tabs": (CODEX, {}), "inline": (CLAUDE, RENDERS_APPS), "text": (TEXT_CLIENT, {})}
DOCUMENT_ID = "6f1c2a4e-1b2c-5d3e-8f4a-0123456789ab"


class ToolArgumentsTest(unittest.TestCase):
    """What every tool takes, in every catalog: the schema a host is listed and what its handler takes
    agree, a model is named by ``source`` everywhere, and a refusal says what is missing and unknown."""

    def setUp(self) -> None:
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.model = self.tmp / "bracket.stl"
        self.model.write_bytes(STL)

    def served(self, catalog: str) -> Server:
        client, offered = CATALOGS[catalog]
        page = self.tmp / "app"
        page.mkdir(exist_ok=True)
        (page / "index.html").write_text("<!doctype html><title>CAD</title>", encoding="utf-8")
        server = Server(page=AppPage(page), recents=RecentStore(self.tmp / "state"))
        server.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": offered,
                                                       "clientInfo": client}, None), None)
        return server

    def call(self, server: Server, name: str, arguments: dict) -> dict:
        return server.handle("tools/call", {"name": name, "arguments": arguments}, RequestContext(1, {"threadId": "t"}))

    def sample(self, key: str, schema: dict):
        """A value the schema takes for ``key``, as an agent would send it."""
        named = {"requestId": "agreement-request-01", "operationId": "operation", "epoch": "epoch", "view": "v",
                 "source": str(self.model), "destinations": [str(self.tmp / "out.step")]}
        if key in named:
            return named[key]
        if "enum" in schema:
            return schema["enum"][0]
        kind = schema.get("type")
        kind = kind[0] if isinstance(kind, list) else kind
        return {"string": str(self.tmp / "out.png"), "integer": schema.get("minimum", 0), "boolean": False,
                "object": {}, "array": []}[kind]

    def test_every_schema_property_is_one_its_handler_takes(self) -> None:
        for catalog in CATALOGS:
            server = self.served(catalog)
            for tool in server.handle("tools/list", {}, None)["tools"]:
                name, schema = tool["name"], tool["inputSchema"]
                if name in START:
                    branches = schema["anyOf"]
                    self.assertEqual(set(schema["properties"]), {key for branch in branches for key in branch["properties"]}, name)
                    # An agent reads the whole list: all but what names an operation to follow is a start's too.
                    [start] = [branch for branch in branches if "start" in branch["properties"]["action"]["enum"]]
                    self.assertEqual(set(schema["properties"]) - set(start["properties"]), {"operationId", "epoch", "afterSequence"}, name)
                    for branch in branches:
                        for key, property_schema in branch["properties"].items():
                            if "start" in branch["properties"]["action"]["enum"]:
                                # The set of arguments that names this one, else the first: what a start needs beside it.
                                group = next((group for group in STARTS[name] if key in group), STARTS[name][0])
                                base = {need: self.sample(need, branch["properties"][need]) for need in ("requestId", *group)}
                            else:
                                base = {"action": "status", "operationId": "operation", "epoch": "epoch"}
                            arguments = {**base, key: self.sample(key, property_schema)}
                            with self.subTest(catalog=catalog, tool=name, argument=key):
                                check_arguments(name, arguments)  # raises where the handler refuses one
                elif name in _AGENT_TOOLS:
                    base = {need: self.sample(need, schema["properties"][need]) for need in schema.get("required", [])}
                    for key, property_schema in schema["properties"].items():
                        with self.subTest(catalog=catalog, tool=name, argument=key):
                            server._arguments(name, {**base, key: self.sample(key, property_schema)})

    def test_every_tool_names_its_model_source(self) -> None:
        for catalog in CATALOGS:
            for tool in self.served(catalog).handle("tools/list", {}, None)["tools"]:
                properties = tool["inputSchema"]["properties"]
                self.assertNotIn("path", properties, (catalog, tool["name"]))
                if tool["name"] in ("cad_open", "cad_show", *START):
                    self.assertIn("source", properties, (catalog, tool["name"]))

    def test_a_refusal_names_every_argument_missing_and_unknown_and_what_the_tool_takes(self) -> None:
        server = self.served("text")
        shape = ("To start: {requestId, source, output} or {requestId, packet}, optionally with display, camera, grid, "
                 "preview, pose, width, height, size_profile, annotation, measurements, waitMs. To follow one: "
                 "{action: status or cancel, operationId, epoch}, optionally with afterSequence, waitMs.")
        for arguments, said in (({"path": str(self.model)}, "missing requestId, source, output; unknown path"),
                                ({"id": DOCUMENT_ID, "out": str(self.tmp / "a.png")}, "missing requestId, source, output; unknown id, out"),
                                ({"requestId": "agreement-request-01", "packet": {}, "output": str(self.tmp / "a.png")},
                                 "a packet declares its outputs; omit output")):
            refused = self.call(server, "cad_snapshot", arguments)
            self.assertTrue(refused["isError"])
            self.assertEqual(refused["structuredContent"]["error"], f"cad_snapshot: {said}. {shape}")
        followed = self.call(server, "cad_inspect", {"action": "status", "source": str(self.model)})["structuredContent"]["error"]
        self.assertTrue(followed.startswith("cad_inspect: missing operationId, epoch; unknown source. To start: "
                                            "{requestId, source}, optionally with ref, query, waitMs."), followed)
        shown = self.call(server, "cad_show", {"path": str(self.model)})
        self.assertTrue(shown["isError"])
        self.assertEqual(shown["content"][0]["text"], "cad_show: missing source; unknown path. cad_show takes source; source "
                                                      "is a document id (running a model's script prints it) or a CAD file's "
                                                      "absolute path.")
        self.assertEqual(server.operations.jobs, {})  # nothing refused was queued

    def test_a_start_waits_for_its_result_as_long_as_wait_ms_says(self) -> None:
        server = self.served("text")
        with mock.patch("cadgen.engine.api.inspect", return_value={"faces": 6}):
            done = self.call(server, "cad_inspect", {"requestId": "inspect-and-wait-01", "source": str(self.model),
                                                     "waitMs": 10000})["structuredContent"]
        self.assertEqual((done["state"], done["result"]), ("succeeded", {"inspection": {"faces": 6}}))

    def test_inspecting_a_file_without_a_ref_answers_what_cadgen_inspect_prints(self) -> None:
        from cadgen.engine.cli import summary_text

        server = self.served("text")
        step = self.tmp / "box.step"
        step.write_text("ISO-10303-21;\n", encoding="utf-8")
        # What `cadgen inspect --json box.step` answered for a 10 x 20 x 30 mm box (``api._summary``).
        summary = {"name": "COMPOUND", "id": DOCUMENT_ID, "state": {"state": "file", "path": str(step)},
                   "parts": {"occurrences": 1, "distinct": 1, "root": "COMPOUND"},
                   "bounds": {"min": [-5.0, -10.0, -15.0], "max": [5.0, 10.0, 15.0], "size": [10.0, 20.0, 30.0]},
                   "volume": 6000.0, "materials": [], "mass": None, "unweighed": [], "joints": [], "states": [],
                   "sequences": [], "animations": [], "files": []}
        asked = []

        def inspect(**arguments):
            asked.append(arguments)
            return {"summary": summary, "closure": None} if arguments.get("query") == "summary" else {"volume": 6000.0}

        with mock.patch("cadgen.engine.api.inspect", side_effect=inspect):
            whole = self.call(server, "cad_inspect", {"requestId": "inspect-a-file-0001", "source": str(step),
                                                      "waitMs": 10000})["structuredContent"]
            part = self.call(server, "cad_inspect", {"requestId": "inspect-a-part-0001", "source": f"{step}#COMPOUND",
                                                     "waitMs": 10000})["structuredContent"]
        for call in asked:  # the engine is handed where to say its measurement's stages (``progress``)
            self.assertTrue(callable(call.pop("progress", None)))
        self.assertEqual(asked, [{"source": str(step), "query": "summary"}, {"source": f"{step}#COMPOUND"}])
        inspection = whole["result"]["inspection"]
        self.assertEqual((inspection["summary"], inspection["text"]), (summary, summary_text(summary)))
        self.assertIn("volume      6,000 mm^3", inspection["text"])
        self.assertEqual(part["result"]["inspection"], {"volume": 6000.0})
        cad_inspect = next(tool for tool in server.handle("tools/list", {}, None)["tools"] if tool["name"] == "cad_inspect")
        self.assertIn("Without a ref it answers what `cadgen inspect SOURCE` prints", cad_inspect["description"])
        self.assertIn("summary", cad_inspect["inputSchema"]["properties"]["query"]["enum"])

    def test_a_snapshot_with_no_output_is_refused_at_its_start(self) -> None:
        server = self.served("text")
        refused = self.call(server, "cad_snapshot", {"requestId": "snapshot-no-output-1", "source": str(self.model)})
        self.assertEqual(refused["structuredContent"]["state"], "rejected")
        self.assertTrue(refused["structuredContent"]["error"].startswith("cad_snapshot: missing output. To start: "))
        relative = self.call(server, "cad_snapshot", {"requestId": "snapshot-relative-01", "source": str(self.model),
                                                      "output": "picture.png"})["structuredContent"]
        self.assertEqual((relative["state"], relative["error"]), ("rejected", "Paths must be absolute on the engine host"))
        self.assertEqual(server.operations.jobs, {})

    def test_outputs_may_have_been_written_only_once_the_engine_was_asked(self) -> None:
        from cadgen.engine.export import ExportRefused
        from cadgen.engine.snapshot import SnapshotRefused

        server = self.served("text")
        out = str(self.tmp / "a.png")
        engine_refusal = ExportRefused("the second destination is 3D")
        engine_refusal._engine_refusal = True
        for error, may in ((SnapshotRefused("refused before any render"), False), (engine_refusal, True),
                           (RuntimeError("the renderer died"), True)):
            with mock.patch("cadgen.engine.api.snapshot", side_effect=error):
                failed = self.call(server, "cad_snapshot", {"requestId": f"snapshot-fails-{may}-{type(error).__name__}",
                                                            "source": str(self.model), "output": out, "waitMs": 10000})
            self.assertEqual(failed["structuredContent"]["state"], "failed")
            self.assertEqual(failed["structuredContent"]["result"], {"outputsMayHaveBeenWritten": may}, error)

    def test_a_pose_the_engine_refuses_wrote_nothing_and_is_said_in_the_tool_s_arguments(self) -> None:
        from cadgen.engine.snapshot import SnapshotRefused

        server = self.served("text")
        # As the engine's renderer refuses it (``render/service.py``), raised here as its own type (``api._failed``).
        refusal = SnapshotRefused("--pose: the document has no mechanism state 'spin'; its states: parked; its "
                                  "joints: hinge: pose one by value, --pose '{\"hinge\": 90}'")
        refusal._engine_refusal = True
        with mock.patch("cadgen.engine.api.snapshot", side_effect=refusal):
            failed = self.call(server, "cad_snapshot", {"requestId": "snapshot-bad-pose-01", "source": str(self.model),
                                                        "output": str(self.tmp / "a.png"), "pose": "spin",
                                                        "waitMs": 10000})["structuredContent"]
        self.assertEqual((failed["state"], failed["result"]), ("failed", {"outputsMayHaveBeenWritten": False}))
        self.assertEqual(failed["error"], "pose: the document has no mechanism state 'spin'; its states: parked; its "
                                          "joints: hinge: pose one by value, pose {\"hinge\": 90}")

    def test_an_export_of_a_script_says_to_run_it_and_export_its_document_by_id(self) -> None:
        server = self.served("text")
        script = self.tmp / "l_bracket.py"
        script.write_text("print(1)\n", encoding="utf-8")
        failed = self.call(server, "cad_export", {"requestId": "export-a-script-001", "source": str(script),
                                                  "destinations": [str(self.tmp / "l_bracket.step")], "waitMs": 10000})
        answer = failed["structuredContent"]
        self.assertEqual(answer["state"], "failed")
        self.assertEqual(answer["error"], "l_bracket.py is no document: an export reads an .xbf, a .step, a mesh (.glb, "
                                          f".stl, .3mf) or a document id; run `cadgen run {script}` first, then export "
                                          "its document by id")
        self.assertEqual(answer["result"], {"outputsMayHaveBeenWritten": False})  # refused before the engine was asked

    def test_a_snapshot_of_a_held_document_names_it_by_its_id_and_never_a_file_that_is_not_there(self) -> None:
        from types import SimpleNamespace
        from cadgen.engine import snapshot

        server = self.served("text")
        out = self.tmp / "_probe" / "mcp.png"
        out.parent.mkdir()

        reports = []

        def worker(order, spec, shown, daemon, progress=None):
            # What the worker holding the document does with the order: draws it from memory, no file of it.
            reports.append(snapshot.draw(SimpleNamespace(path=None), Path(order["draw"]["out"])))
            return {"reports": [], "files": [], "drawn": dict(reports[-1])}

        png = (b"\x89PNG\r\n\x1a\n" + b"\0" * 16, {"width": 4, "height": 3, "timings": {}})
        with mock.patch("cadgen.engine.api._exported", side_effect=worker), \
                mock.patch("cadgen.engine.render.service.draw_here", return_value=png):
            done = self.call(server, "cad_snapshot", {"requestId": "snapshot-held-doc-01", "source": DOCUMENT_ID,
                                                      "output": str(out), "waitMs": 10000})["structuredContent"]
        self.assertEqual(done["state"], "succeeded", done)
        [picture] = done["result"]["pictures"]
        self.assertEqual(picture["report"]["document"], DOCUMENT_ID)
        self.assertNotIn("document", reports[0])  # the worker's report names no file it drew from
        self.assertNotIn("mcp.xbf", json.dumps(done))

    def test_the_text_catalog_says_the_model_opens_in_the_browser_and_never_in_the_chat(self) -> None:
        server = self.served("text")
        instructions = server.handle("initialize", initialize_params({"protocolVersion": "2025-06-18", "capabilities": {},
                                                                      "clientInfo": TEXT_CLIENT}, None), None)["instructions"]
        tools = server.handle("tools/list", {}, None)["tools"]
        said = [instructions] + [tool["description"] for tool in tools] + [
            schema.get("description", "") for tool in tools for schema in tool["inputSchema"]["properties"].values()]
        for words in said:
            for wrong in ("chat", "card", "viewer tab"):
                self.assertNotIn(wrong, words.lower())
        cad_show = next(tool for tool in tools if tool["name"] == "cad_show")
        for words in (instructions, cad_show["description"]):
            self.assertIn("in the user's browser", words)
            self.assertIn(FOLLOWS, words)


class LocalPathTest(unittest.TestCase):
    def test_windows_reads_a_drive_path_however_a_host_spells_it(self) -> None:
        # Codex's file tree names a file /C:/Users/...; a file URI names the same path. Windows reads
        # either as a folder C: on the current drive until the slash before the drive goes.
        for spelled in ("/C:/Users/me/parts/bracket.step", "file:///C:/Users/me/parts/bracket.step",
                        "file:///c%3A/Users/me/parts/bracket.step", "C:/Users/me/parts/bracket.step",
                        "C:\\Users\\me\\parts\\bracket.step"):
            path = local_path(spelled, windows=True)
            self.assertTrue(ntpath.isabs(path), spelled)
            self.assertEqual(ntpath.normcase(ntpath.normpath(path)), "c:\\users\\me\\parts\\bracket.step", spelled)
        self.assertEqual(local_path("file:///C:/My%20Parts/a.step", windows=True), "C:/My Parts/a.step")
        # A share keeps both its slashes.
        self.assertEqual(local_path("//server/share/a.step", windows=True), "//server/share/a.step")

    def test_posix_keeps_every_path_as_named(self) -> None:
        # On POSIX /C:/x is a real absolute path: a folder named C: at the root.
        self.assertEqual(local_path("/C:/x/a.step", windows=False), "/C:/x/a.step")
        self.assertEqual(local_path("file:///home/me/a%20b.step", windows=False), "/home/me/a b.step")


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
        result = self.call("cad_http", {"method": method, "url": url, "headers": {"x-cadgen-app": self.server._app_token, **(headers or {})},
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

    def test_an_engine_part_read_in_parts_is_the_engines_one_answer(self) -> None:
        # A part's buffer the engine answered, relayed: read a range at a time, every later range
        # cut from the body the first kept, never asked of the engine again.
        body = os.urandom(2 * MAX_REPLY_BYTES + 11)
        asked = []

        def handle(request, response):
            asked.append(request.path)
            response.send_bytes(200, body, "application/octet-stream")

        url = "http://cad.invalid/__cad/api/doc/abc/part/k1"
        whole, sizes, etag = b"", [], ""
        with mock.patch.object(self.server.tunnel.app, "handle", handle):
            while len(whole) < len(body):
                headers = {"range": f"bytes={len(whole)}-{len(whole) + MAX_REPLY_BYTES - 1}", **({"if-range": etag} if etag else {})}
                reply, size = self.sized("GET", url, headers)
                self.assertEqual(reply["status"], 206)
                etag = etag or reply["headers"]["etag"]
                self.assertEqual(reply["headers"]["etag"], etag)
                whole += base64.b64decode(reply["body"])
                sizes.append(size)
        self.assertEqual((whole, asked), (body, ["/__cad/api/doc/abc/part/k1"]))
        self.assertEqual(len(sizes), 3)
        self.assertLessEqual(max(sizes), MESSAGE_BOUND)

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
                elif request.path == "/__cad/api/doc/abc/version":
                    response.send_json(200, {"version": "1-1"})
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
        for path, method, body in (("/__cad/api/doc/abc/version", "GET", b'{"version":"1-1"}'),
                                   ("/__cad/api/doc/abc/part/k1", "GET", binary), ("/__cad/catalog", "HEAD", b"")):
            reply = call(path, method)
            self.assertNotIn("encoding", reply)
            self.assertEqual(base64.b64decode(reply["body"]), body)

    def test_a_long_bodys_later_parts_are_cut_from_it_not_produced_again(self) -> None:
        from cadgen.mcp.tunnel import MAX_REPLY_BYTES, ViewerTunnel

        body = os.urandom(2 * MAX_REPLY_BYTES + 5)
        runs = []

        class Routes:
            def handle(self, request, response) -> None:
                runs.append(request.path)
                response.send_bytes(200, body, "application/octet-stream")

        tunnel = ViewerTunnel()

        def part(first: int, etag: str = "") -> dict:
            headers = {"range": f"bytes={first}-{first + MAX_REPLY_BYTES - 1}", **({"if-range": etag} if etag else {})}
            with mock.patch.object(ViewerTunnel, "app", Routes()):
                return tunnel.serve(method="GET", url="http://cad.invalid/__cad/drawing?file=/m/a.dxf", headers=headers, body=b"")

        def read() -> bytes:
            first = part(0)
            etag = first["headers"]["etag"]
            replies = [first] + [part(offset, etag) for offset in range(MAX_REPLY_BYTES, len(body), MAX_REPLY_BYTES)]
            self.assertEqual({reply["headers"]["etag"] for reply in replies}, {etag})
            return b"".join(base64.b64decode(reply["body"]) for reply in replies)

        self.assertEqual(read(), body)
        self.assertEqual(len(runs), 1, "the route ran for a later part")
        # Its last part sent, the body is not kept: the next read produces it again, once.
        self.assertEqual(read(), body)
        self.assertEqual(len(runs), 2)


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
