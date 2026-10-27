"""``cadgen mcp``: CAD beside an agent's chat, as an MCP App.

Nothing heavy happens until a tool needs it: initialize and tools/list read no
model file and import no CAD kernel. The engine already owns this session. Everything the views share --
the open views, what was last shown -- is per-session engine memory.

One page serves every surface. The tool that opens a surface returns a
*launch* -- a model by its absolute path, or the home -- and the page renders it;
a view browses from its model's folder, so nothing says where it may browse. Once
open, a view makes ONE call each second, ``cad_sync``: it says what it shows (its
model, its selection, whether a person just touched it) and what it watches (its
model's catalog entry), and gets back the agent's requests
and what changed. Everything else -- its model, the library and the home's Open,
Reveal, the person's analytics answer and language, the update check -- it reaches
through ``cad_http``, the viewer's own HTTP routes. No call is held open
(``views.py``). Agents name models by absolute path only.

Hosts present views in one of three ways, told apart at initialize (``host.py``):

- *Tabs* (the Codex app, and any host that declares the ``dev.texttocad/tabs`` client
  extension with the ``global``, ``thread`` and ``file`` entrypoints). The host
  presents CAD as a sidebar page, a tab per thread and a file handler. The agent
  opens a tab once (``cad_open``) and then drives it (``cad_show``). A host that
  declares tabs takes on what Codex does: it starts one shim and MCP session per thread,
  since a call that names no view reaches the thread's own tab.
- *Inline* (every other MCP Apps host: Claude, VS Code, ...). Each call to a tool
  with a UI mounts a new view in the chat, and the old ones stay. So ``cad_show``
  is that tool, each launch is stamped with an order for the views to retire
  their elders by, and a view the agent reads is named by the token its
  ``cad_show`` returned: one session may serve many chats, and no host says which.
- *Text* (a client that renders no MCP Apps, so does not advertise the
  ``io.modelcontextprotocol/ui`` extension: Grok, Zed, Gemini CLI, Claude Code in a
  terminal, ...). ``cad_show`` opens the model's page in the CAD Viewer
  (``browser.py``), the one this machine runs, started if none is, in the person's
  browser -- unless a browser page reads that document already -- and answers with its URL.
  The engine never opens it: the host's stdio peer does, in the agent's own environment, from
  the request the answer carries (``browser.OPEN``), and says whether it opened
  (``browser.OPENED``), which alone counts the page as open there; a client with no peer gets
  the URL alone.

Codex declares nothing at initialize, headless or not: ``codex exec`` and its terminal UI greet the
server as the Codex app does (``codex-mcp-client``) and render no app. So whether a tab opened is
claimed only on evidence, never on that name (``host.py``): a declared extension; a view that reached
this server (only a host that shows cards draws one); a call whose turn says ``exec``; the host the
shim found among its parent processes (``codex exec`` and the terminal UI are text hosts, the app's
``codex app-server`` shows tabs). A host that shows none has ``cad_open`` and ``cad_show`` do what a
text client's ``cad_show`` does. Where nothing says yet (the name alone), ``cad_open`` claims no tab:
it says the tab opens with its answer where the host shows CAD tabs, and gives the page's URL for
the user otherwise; a ``cad_show`` after it waits for that tab, and a tab that never comes is
evidence that this host shows none.

``CADGEN_MCP_PRESENTATION=inline|text`` settles a non-Codex client that renders MCP
Apps without advertising them (the reference host, ``basic-host``, is one).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import secrets
import sys
import itertools
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from cadgen.viewer.scanner import VIEWER_EXTENSIONS

from . import host
from .protocol import INVALID_PARAMS, METHOD_NOT_FOUND, RequestContext, RpcError
from .ui import MIME, RESOURCE_META, AppPage
from .sidebar import SidebarView
from .views import CAPTURE_SECONDS, NoAnswer, ViewRegistry

LOG = logging.getLogger("cadgen.mcp")

NAME = "cad"
TITLE = "CAD"
# The launch/view protocol between this server and its page: a launch names a model by its absolute
# path (`page: viewer`) or the home (`page: home`, its recents with it), and carries what the page
# needs to start on it alone (the server's version and platform); a view makes one call a second
# (`cad_sync`) and reaches the viewer's routes through `cad_http`, by absolute path.
PROTOCOL = 9
_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
_RESOURCE_NOT_FOUND = -32002
EXTENSIONS = sorted(VIEWER_EXTENSIONS)
# The formats every surface opens, as the agent is told them: a cadgen engine document (XBF) among them.
FORMATS = "STEP, XBF, STL, GLB, 3MF, DXF, URDF, SDF, KiCad PCB"

# How long a call that reads a view waits for one the agent just opened (a tab from cad_open, a card
# from an inline cad_show) to sync for the first time: the host loads the page, then the page its
# model. An agent reads a view right after it opened it.
OPENING_SECONDS = 15.0
# How long after an agent opened a view a read that finds none still waits for it; and how many
# inline views not yet seen are remembered.
_OPENED_WITHIN = 60.0
_MOUNTING_KEPT = 64
# How many pages a session asked its stdio peer to open are kept until the peer's word on each
# (``Server.notify``): it answers before its host has the result, so only an ask whose word never
# came (its process gone mid-open) is ever let go, oldest first.
_ASKED_KEPT = 16

INSTRUCTIONS = (
    f"CAD shows local CAD models ({FORMATS}) in a viewer tab beside the chat. "
    "To show a model, call cad_show with its document id (running its script prints it) or a CAD file's absolute "
    "path: it switches an open viewer and never opens a tab. "
    "Only when cad_show reports no open viewer, call cad_open, once. "
    "Viewers follow every rebuild of a model and every save of a file, so never reopen after a rebuild. "
    "cad_view reports what the user is looking at and has selected; cad_screenshot returns what they see."
)

INLINE_INSTRUCTIONS = (
    f"CAD shows local CAD models ({FORMATS}) in interactive viewers in the chat. "
    "Call cad_show with a model's document id (running its script prints it) or a CAD file's absolute path to "
    "show it: each call adds a viewer and pauses the earlier ones. "
    "Viewers follow every rebuild of a model and every save of a file, so never show a model again after a rebuild. "
    "cad_view reports what the user is looking at and has selected in a viewer, and cad_screenshot returns "
    "what they see; both take the view that cad_show returned."
)

# What a text client's page does after it opens, true of a document and of a file alike.
FOLLOWS = ("The page follows the model: rebuilds for a document, saves for a file, so show a model once, "
           "not after every rebuild.")

TEXT_INSTRUCTIONS = (
    f"CAD opens models and local CAD files ({FORMATS}) in the CAD Viewer in the user's browser: "
    "this app cannot show CAD views itself. Call cad_show with source set to a model's document id (running its "
    "script prints it) or a file's absolute path: it opens the page in the user's browser, or says it is open "
    "already, and answers with its URL; give the user that URL. " + FOLLOWS
)

_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-0.86 -1.2 5.56 5.56" fill="currentColor">'
    '<path d="M0 0H3V1.5H1.5V2.5H3V4H0Z"/>'
    '<path opacity=".55" d="M0 0L.84-.84H3.84L3 0ZM1.5 2.5L2.34 1.66H3.84L3 2.5Z"/>'
    '<path opacity=".3" d="M3 0L3.84-.84V.66L3 1.5ZM3 2.5L3.84 1.66V3.16L3 4ZM1.5 1.5L2.34.66V1.66L1.5 2.5Z"/>'
    "</svg>"
)
ICON = {
    "src": "data:image/svg+xml;base64," + base64.b64encode(_ICON_SVG.encode("utf-8")).decode("ascii"),
    "mimeType": "image/svg+xml",
    "sizes": ["any"],
}


def _say_not_held(named: Any) -> None:
    """A document id the engine knows but holds no more (unsaved, detached): refused with the command
    that builds it again, which nothing here runs."""
    from cadgen.engine.ids import is_id

    if not is_id(named):
        return
    from cadgen.engine.client import request

    answer = request({"op": "state", "id": named}, start=False) or {}
    if answer.get("error"):
        raise ToolFailed(f"{answer['error']}. Nothing runs it for you; once it is run, show {named} again.", "no_file")


class ToolFailed(Exception):
    """A tool call that fails the way its caller should read: as the tool's result. ``reason`` is why, in
    telemetry's words (``cadgen.analytics.FAILURES``), named where it is raised: never read from the message."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


def _object(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties or {}, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


# What names a model, the one argument name every tool gives it: cad_show and cad_open as cad_export,
# cad_snapshot and cad_inspect do.
_SOURCE = {"type": "string", "description": "A CAD file's absolute path, or a document id (a model's, which running its script prints)."}
# The tools the agent calls with a model or a view, whose arguments are checked against what they take
# (``_arguments``): the host's own surfaces (``cad_file``, ...) are called with what the host sends.
_AGENT_TOOLS = ("cad_open", "cad_show", "cad_view", "cad_screenshot")
_VIEW = {"type": "string", "description": "A view id from cad_view; defaults to the most recently used viewer."}
# What a view watches: its model's catalog entry.
_WATCH = _object({"file": {"type": ["string", "null"]}})
_SHOWN_VIEW = {"type": "string", "description": "The view that cad_show returned."}
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
# Shared with agents, but the viewer routes require the capability delivered only to the UI.
_APP_TOKEN_META = "dev.texttocad/httpToken"
_APP_TOKEN_HEADER = "x-cadgen-app"
# The page's own tools (``cad_sync``, ``cad_capture_reply``) take the same capability as an argument:
# a host is asked to keep app-only tools from the model, and the server does not rely on it.
_APP_TOKEN_ARGUMENT = "app"
_APP_TOKEN_SCHEMA = {"type": "string", "description": "The view's capability, from its launch's metadata."}
# The card's Open in browser: this process opens the web viewer's page of the document the card
# shows (``_open_in_browser``), a route of the app's alone -- an agent's request never reaches it.
_BROWSER_OPEN_ROUTE = "/__cad/browser/open"
_HTTP_TOOL = {
    "name": "cad_http", "title": "CAD HTTP request", "icons": [ICON],
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    "description": ("Read CAD telemetry status with method GET and url /__cad/analytics. "
                    "Only when the user asks to opt out, POST to that URL with base64 body eyJzaGFyZSI6ZmFsc2V9 "
                    "(JSON {\"share\":false}). Opt-out removes the installation ID and requests deletion of previously "
                    "sent data; saved:false means the choice could not be persisted. Agents cannot opt in or access "
                    "other routes. CAD app requests carry a session capability. Replies contain HTTP status, headers "
                    "and a base64 body; agent replies also include readable JSON text."),
    "inputSchema": _object({"method": {"type": "string"}, "url": {"type": "string"},
                            "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                            "body": {"type": "string", "description": "Base64-encoded request body."}}, ["method", "url"]),
}


def _stamped(launch: dict[str, Any]) -> dict[str, Any]:
    """A launch with what the page needs to start on it alone: this server's version and platform,
    whether this computer has a file chooser for the home's Open, and the update notice as the
    server last read it (``cadgen/updates.py``; a launch never waits on the feed)."""
    from cadgen import __version__, updates
    from cadgen._internal.picker import available

    launch["version"] = __version__
    launch["platform"] = sys.platform if sys.platform in ("darwin", "win32") else "linux"
    launch["pick"] = available()
    launch["notice"] = updates.notice()
    updates.refresh()  # a server can run for days: a feed that is due is read in the background, for the next launch
    return launch


def _text(text: str, structured: dict[str, Any] | None = None, *, error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if structured is not None:
        result["structuredContent"] = structured
    if error:
        result["isError"] = True
    return result


def _data(structured: dict[str, Any]) -> dict[str, Any]:
    """A result only the page reads."""
    return {"content": [], "structuredContent": structured}


def file_uri_path(value: Any) -> str | None:
    """The path a ``file:`` URI names (``file:///C:/x`` names ``/C:/x``), else None."""
    if not isinstance(value, str) or not value.startswith("file:"):
        return None
    return unquote(urlparse(value).path) or None


def local_path(value: str, *, windows: bool = os.name == "nt") -> str:
    """A path a caller or host named, as this machine spells it: a ``file:`` URI is the path it names,
    ``~`` is home, and on Windows a drive path loses the slash before its drive. A file URI names
    ``/C:/x``, and Codex on Windows spells the path of a file opened from its file tree the same way
    (``openai/resource``: ``/C:/Users/...``); Windows reads ``/C:/x`` as a folder ``C:`` on the
    current drive, so that slash would name a file that is not there."""
    path = file_uri_path(value) or os.path.expanduser(value.strip())
    if windows and len(path) > 2 and path[0] == "/" and path[1].isalpha() and path[2] == ":":
        path = path[1:]
    return path


class Server:
    def __init__(self, *, page: AppPage | None = None, recents=None, tunnel=None, viewer_url=None, browser_opener=None,
                 sidebar_views=None, analytics=None, sync_document=lambda path: None, warm=lambda: None,
                 in_browser=lambda model: False, browser_opened=lambda model: None, engine_origin: str | None = None) -> None:
        self.page = page or AppPage()
        # The engine's own origin (``http://127.0.0.1:<port>``), which an inline host is asked to let
        # the card reach (``_resource_meta``): where the host carries no tool call back, the card
        # reads the engine directly with its launch's day link (``_reach``).
        self._engine_origin = engine_origin
        self.sync_document = sync_document
        self.warm = warm  # the engine's meshing pool, started when a view is launched (``Server.warm``)
        self.views = ViewRegistry()
        self._recents = recents
        self._tunnel = tunnel
        self._sidebar_views = sidebar_views
        self._model: str | None = None  # what this thread last opened or showed
        self._tools: list[dict[str, Any]] | None = None
        from .operations import Operations
        self.operations = Operations()
        self.tabs = False  # decided at initialize: see the module docstring
        self.text = False
        # Whether this host shows CAD cards (``host.presentation``): True, False, or None while nothing
        # says; ``_declared`` where the host said so itself, which nothing after overrules; and
        # ``_contacted`` once a view reached this server, which only a host that draws them does.
        self.renders: bool | None = None
        self._declared = False
        self._contacted = False
        self._viewer_url = viewer_url
        self._browser_opener = browser_opener  # what opens a page's redirect file: ``webbrowser.open``
        # Whether a browser page reads a document now (the engine's ``Server.in_page``), and telling
        # the engine a browser opened on one (``Server.page_opening``): a host with no app opens each once.
        self._in_browser = in_browser
        self._browser_opened = browser_opened
        # The stdio peer's browser (``browser.transport_browser``): it opens the page a text host's
        # cad_show names, and says whether it can; None for a client with no such peer.
        self._peer_browser: dict[str, Any] | None = None
        # The pages this session asked its peer to open (``browser.OPEN``), each model by its page's
        # URL until the peer says whether it opened (``notify``): only a page it says opened counts as
        # open in the person's browser, so a show after a failed open opens it again.
        self._asked: dict[str, str] = {}
        self._asked_lock = threading.Lock()
        self._order = itertools.count(1)
        self._analytics = analytics
        self._app_token = secrets.token_urlsafe(32)
        self._update_told = False
        # Inline views this server named that have not synced yet, oldest first; when cad_open last opened a tab,
        # and a model cad_show sent it before it opened, shown once it does.
        self._mounting: dict[str, None] = {}
        self._opened: float | None = None
        self._pending: str | None = None

    # -- lazily built parts ----------------------------------------------------

    @property
    def recents(self):
        if self._recents is None:
            from cadgen.viewer.recents import RecentStore

            self._recents = RecentStore()
        return self._recents

    @property
    def sidebar_views(self):
        """The CAD sidebar's views, which every process reaches (``sidebar.py``)."""
        if self._sidebar_views is None:
            from .sidebar import SidebarViews

            # Beside the model library: the person's state, shared by every process of theirs.
            self._sidebar_views = SidebarViews()
        return self._sidebar_views

    @property
    def analytics(self):
        """Anonymous counts of this process's tool calls, sent by default once the user was told, never after a
        no (``cadgen/analytics.py``)."""
        if self._analytics is None:
            from cadgen.analytics import Recorder
            from cadgen.settings import FILE

            # The settings beside the model library (the state directory, by default): shared by every process.
            path = Path(self._recents.root).parent / FILE if self._recents is not None else None
            self._analytics = Recorder(path=path)
        return self._analytics

    @property
    def tunnel(self):
        """The viewer's routes, served in-process for the views (``tunnel.py``), over this server's
        library and analytics."""
        if self._tunnel is None:
            from .tunnel import ViewerTunnel

            self._tunnel = ViewerTunnel(recents=self.recents, analytics=self.analytics)
        return self._tunnel

    # -- the protocol ----------------------------------------------------------

    def handle(self, method: str, params: dict[str, Any], context: RequestContext) -> Any:
        try:
            return self._dispatch(method, params, context)
        except RpcError:
            raise
        except Exception as error:
            # A request that failed for no reason its client gave: this server's crash, answered as the
            # protocol answers one (an internal error), and counted (``cadgen/analytics.py``) -- a page's
            # request (``cad_http``) by the viewer's routes, which counted it already (``tunnel.py``).
            calling = method == "tools/call"
            if not (calling and params.get("name") == "cad_http"):
                self.analytics.crashed(error, "tool" if calling else "request", tool=params.get("name") if calling else None)
            raise

    def notify(self, method: str, params: Any) -> None:
        """A notification from this session's client, which answers nothing. The one read is the stdio
        peer's word on a page this session asked it to open (``browser.OPENED``, ``{"url",
        "opened"}``): the first word on a page settles its ask, and only an open counts, from then, as
        the page open in the person's browser (``browser_opened``). A word on any page this session
        has no ask for -- never asked, another session's, or settled already -- is ignored, so no
        client can have a page counted as open that its peer was not asked to open."""
        from .browser import OPENED

        url = params.get("url") if method == OPENED and isinstance(params, dict) else None
        if not isinstance(url, str):
            return
        with self._asked_lock:
            model = self._asked.pop(url, None)
        if model is not None and params.get("opened") is True:
            self._browser_opened(model)

    def _dispatch(self, method: str, params: dict[str, Any], context: RequestContext) -> Any:
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tools()}
        if method == "tools/call":
            return self._call(params, context)
        if method == "resources/list":
            return {"resources": [{"uri": self.page.uri, "name": "CAD", "title": TITLE, "mimeType": MIME, "_meta": self._resource_meta()}]}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        if method == "resources/read":
            uri = params.get("uri")
            if not self.page.owns(uri):
                raise RpcError(_RESOURCE_NOT_FOUND, f"no resource {uri}")
            return {"contents": [{"uri": uri, "mimeType": MIME, "text": self.page.html(), "_meta": self._resource_meta()}]}
        raise RpcError(METHOD_NOT_FOUND, f"{method} is not supported")

    def _resource_meta(self) -> dict[str, Any]:
        """The page's sandbox: ``RESOURCE_META``, and for a host that mounts cards inline, the engine's
        own origin among the origins the card may fetch, so a card whose host carries no tool call
        back can read the engine directly (``apps/mcp``'s direct transport). A host that shows tabs is
        served exactly what it was (``test_codex_contract``): its card always has its channel."""
        if self.tabs or self.text or not self._engine_origin:
            return RESOURCE_META
        csp = RESOURCE_META["ui"]["csp"]
        return {"ui": {**RESOURCE_META["ui"], "csp": {**csp, "connectDomains": [*csp["connectDomains"], self._engine_origin]}}}

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        from cadgen import __version__

        client = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
        offered = params.get("capabilities") if isinstance(params.get("capabilities"), dict) else {}
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        transport = meta.get("dev.texttocad/transport") if isinstance(meta.get("dev.texttocad/transport"), dict) else {}
        presentation, self.renders, why = host.presentation(client, offered, transport.get("launcher"))
        self._peer_browser = transport.get("browser") if isinstance(transport.get("browser"), dict) else None
        self._declared = why.startswith("declared")
        self.tabs, self.text = presentation == "tabs", presentation == "text"
        if presentation == "inline":
            self.page = self.page.presenting("inline")
        self._tools = None
        extensions = sorted(offered["extensions"]) if isinstance(offered.get("extensions"), dict) else []
        LOG.info("client %s %s: %s views, %s (extensions: %s)", client.get("name"), client.get("version"), presentation,
                 why, ", ".join(extensions) or "none")
        self.analytics.started(client=client, presentation=presentation)
        capabilities: dict[str, Any] = {"tools": {"listChanged": False}, "resources": {"listChanged": False}}
        requested = params.get("protocolVersion")
        return {
            "protocolVersion": requested if requested in _PROTOCOL_VERSIONS else _PROTOCOL_VERSIONS[1],
            "capabilities": capabilities,
            "serverInfo": {"name": NAME, "title": TITLE, "version": __version__, "icons": [ICON]},
            "instructions": INSTRUCTIONS if self.tabs else TEXT_INSTRUCTIONS if self.text else INLINE_INSTRUCTIONS,
        }

    # -- the catalog -----------------------------------------------------------

    def tools(self) -> list[dict[str, Any]]:
        if self._tools is None:
            self._tools = self._tab_catalog() if self.tabs else self._text_catalog() if self.text else self._inline_catalog()
            from .operations import catalog
            self._tools += catalog()
        return self._tools

    def _tab_catalog(self) -> list[dict[str, Any]]:
        uri = self.page.uri

        def surface(entrypoint: dict[str, Any] | None = None, **ui: Any) -> dict[str, Any]:
            meta: dict[str, Any] = {"ui": {"resourceUri": uri, "visibility": ["app"]}, "openai/iconStyle": "monochrome"}
            if entrypoint is not None:
                meta["openai/ui"] = {"entrypoints": [entrypoint], **ui}
            return meta

        agent_open = {"ui": {"resourceUri": uri}, "openai/iconStyle": "monochrome",
                      "openai/ui": {"preferredModelDisplayMode": "fullscreen"}}
        return [
            {"name": "cad_home", "title": TITLE, "description": "Open CAD: recent models, and open one from disk.",
             "inputSchema": _object(), "icons": [ICON], "annotations": _READ_ONLY,
             "_meta": surface({"type": "global"}, preferredModelDisplayMode="fullscreen")},
            {"name": "cad_tab", "title": TITLE, "description": "Open this thread's CAD viewer.",
             "inputSchema": _object(), "icons": [ICON], "annotations": _READ_ONLY,
             "_meta": surface({"type": "thread"})},
            {"name": "cad_file", "title": TITLE, "description": "Open a CAD file in CAD.",
             "inputSchema": _object({"file": _object({"name": {"type": "string"}, "resourceUri": {"type": "string"}}, ["resourceUri"])}, ["file"]),
             "icons": [ICON], "annotations": _READ_ONLY,
             "_meta": surface({"type": "file", "extensions": EXTENSIONS})},
            {"name": "cad_open", "title": TITLE, "icons": [ICON], "annotations": _READ_ONLY, "_meta": agent_open,
             "description": (f"Open a NEW CAD viewer tab beside the chat showing a local model ({FORMATS}). "
                             "Every call opens another tab, so call it only when cad_show reports that no "
                             "viewer is open, and never again after a rebuild: open viewers refresh by themselves."),
             "inputSchema": _object({"source": _SOURCE}, ["source"])},
            {"name": "cad_show", "title": "Show in CAD", "icons": [ICON], "annotations": _READ_ONLY,
             "description": ("Show a model in the CAD viewer already open in this thread, switching it if another model "
                             "is showing. Never opens a tab. Reports whether a viewer took it; if none is open, call cad_open."),
             "inputSchema": _object({"source": _SOURCE, "view": _VIEW}, ["source"])},
            {"name": "cad_view", "title": "Read CAD view", "icons": [ICON], "annotations": _READ_ONLY,
             "description": ("Describe the CAD viewers open in this thread: each one's model and revision, what the user "
                             "has selected (as references you can quote back), and the camera."),
             "inputSchema": _object()},
            {"name": "cad_screenshot", "title": "Capture CAD view", "icons": [ICON], "annotations": _READ_ONLY,
             "description": "Capture a PNG of exactly what an open CAD viewer in this thread shows right now.",
             "inputSchema": _object({"view": _VIEW})},
            _HTTP_TOOL,
            *self._page_tools(),
        ]

    def _inline_catalog(self) -> list[dict[str, Any]]:
        shows = {"ui": {"resourceUri": self.page.uri}}
        return [
            {"name": "cad_show", "title": "Show in CAD", "icons": [ICON], "annotations": _READ_ONLY, "_meta": shows,
             "description": (f"Show a local CAD model ({FORMATS}) in an interactive viewer in the "
                             "chat. Each call adds a viewer and pauses the earlier ones. A viewer follows every rebuild of "
                             "its model and every save of its file, so show a model once, not after every rebuild. "
                             "The result names the view: pass it to cad_view or cad_screenshot."),
             "inputSchema": _object({"source": _SOURCE}, ["source"])},
            {"name": "cad_view", "title": "Read CAD view", "icons": [ICON], "annotations": _READ_ONLY,
             "description": ("Describe a CAD viewer in this chat: its model and revision, what the user has selected (as "
                             "references you can quote back), and the camera."),
             "inputSchema": _object({"view": _SHOWN_VIEW}, ["view"])},
            {"name": "cad_screenshot", "title": "Capture CAD view", "icons": [ICON], "annotations": _READ_ONLY,
             "description": "Capture a PNG of exactly what a CAD viewer in this chat shows right now.",
             "inputSchema": _object({"view": _SHOWN_VIEW}, ["view"])},
            _HTTP_TOOL,
            *self._page_tools(),
        ]

    def _text_catalog(self) -> list[dict[str, Any]]:
        """No page to open or read: cad_show hands over a link to the model in the CAD Viewer."""
        return [
            {"name": "cad_show", "title": "Show in CAD", "icons": [ICON], "annotations": _READ_ONLY,
             "description": ("Open a model in the CAD Viewer in the user's browser, unless its page is open there "
                             "already; this app cannot show CAD views itself. source is a model's document id (running "
                             f"its script prints it) or a local CAD file's absolute path ({FORMATS}). Answers with the "
                             "page's URL: give it to the user. " + FOLLOWS),
             "inputSchema": _object({"source": _SOURCE}, ["source"])},
            _HTTP_TOOL,
        ]

    def _page_tools(self) -> list[dict[str, Any]]:
        """The tools only the page calls: its sync and its answer to a capture."""

        def app(name: str, title: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
            return {"name": name, "title": title, "description": description, "inputSchema": schema,
                    "annotations": _READ_ONLY, "_meta": {"ui": {"visibility": ["app"]}}}

        return [
            app("cad_sync", "CAD sync", "This view's one call each second: what it shows and watches, and what is waiting for it.",
                _object({"view": {"type": "string"}, "surface": {"type": "string"}, "model": {"type": ["string", "null"]},
                         "focused": {"type": "boolean"}, "closed": {"type": "boolean"}, "state": {"type": "object"},
                         "watch": _WATCH, _APP_TOKEN_ARGUMENT: _APP_TOKEN_SCHEMA}, ["view", "surface", _APP_TOKEN_ARGUMENT])),
            app("cad_capture_reply", "Answer CAD", "Answer the server's request for a capture.",
                _object({"requestId": {"type": "string"}, "png": {"type": "string"}, "error": {"type": "string"},
                         _APP_TOKEN_ARGUMENT: _APP_TOKEN_SCHEMA}, ["requestId", _APP_TOKEN_ARGUMENT])),
        ]

    # -- calls -----------------------------------------------------------------

    def _call(self, params: dict[str, Any], context: RequestContext) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            self._refused(name, "bad_request")
            raise RpcError(INVALID_PARAMS, "arguments must be an object")
        # Only a tool this client was listed: text clients have no page tools.
        # Shared HTTP calls enforce their own route and consent authorization.
        listed = any(tool["name"] == name for tool in self.tools())
        from .operations import START
        handler = ((lambda arguments, context: self._operation(name, arguments)) if name in START else
                   getattr(self, f"_tool_{name}", None)) if listed else None
        if handler is None:
            self._refused(name, "no_view")  # a tool of cadgen's this host was not listed: a view it does not show
            raise RpcError(INVALID_PARAMS, f"unknown tool {name!r}")
        started = time.monotonic()
        ok, reason = False, "bug"  # anything a handler raises but ToolFailed is cadgen's own (``handle`` reports it)
        try:
            if name in _AGENT_TOOLS:
                self._arguments(name, arguments)
            result = handler(arguments, context)
            if not self.text and isinstance(result.get("structuredContent", {}).get("launch"), dict):
                # MCP result metadata is delivered to the app, never put in the model's context.
                result.setdefault("_meta", {})[_APP_TOKEN_META] = self._app_token
                self._reach(result["structuredContent"]["launch"])
            ok = not (isinstance(result, dict) and result.get("isError"))
            return result
        except ToolFailed as failure:
            reason = failure.reason
            return _text(str(failure), error=True)
        finally:
            self.analytics.called(name, ok, reason)
            if name not in ("cad_sync", "cad_http"):
                LOG.info("%s %.0fms", name, (time.monotonic() - started) * 1000)

    def _refused(self, name: Any, reason: str) -> None:
        """A call answered with an error before any tool ran, counted all the same (``cadgen/analytics.py``): one
        naming a tool of cadgen's -- in this host's catalog or another's -- as that tool's call failed for
        ``reason``; any other as ``cad_unknown``'s (``UNKNOWN_TOOL``), for a call no tool of cadgen's could read
        (``bad_request``): never by the name the host sent."""
        from cadgen.analytics import UNKNOWN_TOOL

        from .operations import START

        own = isinstance(name, str) and (name in START or callable(getattr(type(self), f"_tool_{name}", None)))
        self.analytics.called(name if own else UNKNOWN_TOOL, False, reason if own else "bad_request")

    def _arguments(self, name: str, arguments: dict[str, Any]) -> None:
        """An agent tool's arguments against the schema this client was listed: one it does not take is
        refused in words, with every one missing and what the tool takes (``operations.refusal``). One
        only missing is the handler's to refuse, in its own words."""
        from .operations import refusal

        schema = next(tool["inputSchema"] for tool in self.tools() if tool["name"] == name)
        unknown = sorted(key for key in arguments if key not in schema["properties"])
        if not unknown:
            return
        required = schema.get("required", [])
        missing = [key for key in required if key not in arguments]
        optional = [key for key in schema["properties"] if key not in required]
        takes = (f"{name} takes {' and '.join(required) or 'nothing'}"
                 + (f", optionally {' and '.join(optional)}" if optional else "")
                 + ("; source is a document id (running a model's script prints it) or a CAD file's absolute path"
                    if "source" in schema["properties"] else "") + ".")
        said = refusal(name, missing, unknown, takes)
        if "source" in missing:
            raise ToolFailed(said, "no_path")
        if "view" in missing:
            raise ToolFailed(said, "no_view")
        raise ToolFailed(said, "bad_request")

    def _operation(self, name, arguments):
        result = self.operations.call(name, arguments)
        return _text(json.dumps(result), result, error=result["state"] in ("failed", "rejected"))

    # launches -----------------------------------------------------------------

    def _launch(self, model: str, *, surface: str | None = None) -> dict[str, Any]:
        """The launch that shows ``model`` (absolute): the view browses from its folder, and adds the
        model to the library once it is on screen, as every CAD view does."""
        launch: dict[str, Any] = {"protocol": PROTOCOL, "page": "viewer", "model": model}
        if surface:
            launch["surface"] = surface
        self._model = model
        self.warm()  # the view's first document meshes on a pool already starting
        return _stamped(launch)

    def _home(self, *, surface: str | None = None) -> dict[str, Any]:
        """The launch that shows the home: the models opened before, which come with it so its cards
        draw at once, and Open with the desktop's chooser."""
        try:
            recents = [entry.public() for entry in self.recents.list()
                       if entry.kind != "file" or os.path.splitext(entry.path)[1].lower() in VIEWER_EXTENSIONS]
        except Exception:  # the home opens whatever the library says
            LOG.exception("could not read recents")
            recents = []
        launch: dict[str, Any] = {"protocol": PROTOCOL, "page": "home", "model": None, "recents": recents}
        if surface:
            launch["surface"] = surface
        return _stamped(launch)

    def _mounted(self, launch: dict[str, Any]) -> dict[str, Any]:
        """Stamp a launch that mounts a new inline view: its token, and its place among the views."""
        seq = next(self._order)
        launch["view"] = f"cad-{seq}-{uuid.uuid4().hex[:10]}"
        self._mounting[launch["view"]] = None
        while len(self._mounting) > _MOUNTING_KEPT:
            self._mounting.pop(next(iter(self._mounting)), None)
        # Wall-clock time orders views across restarts of this process; seq breaks a tie.
        launch["order"] = {"createdAt": int(time.time() * 1000), "seq": seq}
        return launch

    def _reach(self, launch: dict[str, Any]) -> None:
        """Stamp a launch the page is handed with the ways to the engine that need no tool call:
        ``browser``, the web viewer's page of what it shows (the home's with no model), the same day
        link a text client's ``cad_show`` gives the agent (``_browser_url``), which the card's Open
        in browser opens; and, inline, ``engine``, that page's origin (loopback: the engine binds
        nowhere else): a card whose host carries no ``tools/call`` back (the Claude app's Code tab)
        links the page, and first tries the engine directly with the link's token. A tab's card
        always has its channel, so its launches carry the page alone. The file handler's carry
        neither: it shows its file alone, with no Open in browser. Nor do launches where this server
        was given no engine (``viewer_url``), or the engine gives no page."""
        if self._viewer_url is None or launch.get("surface") == "file":
            return
        from .browser import ViewerUnavailable

        try:
            link = self._viewer_url(launch.get("model") or None)
        except ViewerUnavailable as failure:
            LOG.info("the launch carries no page: %s", failure)
            return
        launch["browser"] = link
        if not self.tabs:
            parts = urlparse(link)
            launch["engine"] = f"{parts.scheme}://{parts.netloc}"

    def _model_path(self, value: Any) -> str:
        """An existing CAD file, from the absolute path a caller named; or a document the engine holds,
        from its id: a model's id stays itself, a file's is its path. Nothing is built."""
        if not isinstance(value, str) or not value.strip():
            raise ToolFailed('Name the model in "source": a document id (running a model\'s script prints it) or a '
                             "CAD file's absolute path.", "no_path")
        from cadgen.engine.ids import is_id

        if is_id(value):
            from cadgen.engine.client import request

            answer = request({"op": "document", "id": value}, start=False)
            if not answer or "failed" in answer:
                raise ToolFailed((answer or {}).get("failed") or f"no document {value} is held", "no_file")
            return answer["document"].get("path") or value
        path = local_path(value)
        if not os.path.isabs(path):
            raise ToolFailed(f"{value} is not an absolute path: name the model by its absolute path.", "relative_path")
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            raise ToolFailed(f"No file at {path}.", "no_file")
        if os.path.splitext(path)[1].lower() not in VIEWER_EXTENSIONS:
            raise ToolFailed(f"CAD opens {', '.join(EXTENSIONS)} files; {os.path.basename(path)} is not one.", "not_cad")
        return path

    def _tool_cad_home(self, arguments, context):
        return _text("CAD is open.", {"launch": self._home(surface="sidebar")})

    def _tool_cad_tab(self, arguments, context):
        current = next((view.model for view in self.views.live(context.meta.get("threadId")) if view.model), None) or self._model
        from cadgen.engine.ids import is_id

        if current is not None and not is_id(current) and not os.path.isfile(current):
            current = None
        launch = self._launch(current, surface="tab") if current else self._home(surface="tab")
        return _text("CAD is open.", {"launch": launch})

    def _tool_cad_file(self, arguments, context):
        # Codex names the file in ``openai/resource`` (``/C:/Users/...`` on Windows: ``local_path``);
        # its ``file.resourceUri`` is a ``codex-resource://`` handle, not a file URI.
        resource = context.meta.get("openai/resource")
        path = resource.get("path") if isinstance(resource, dict) else None
        if not path:
            file = arguments.get("file")
            path = file_uri_path(file.get("resourceUri")) if isinstance(file, dict) else None
        model = self._model_path(path)
        # The host's own file tree is this surface's navigation: the page shows the file alone.
        return _text(f"{os.path.basename(model)} is open in CAD.", {"launch": self._launch(model, surface="file")})

    def _cards(self, context: RequestContext) -> bool | None:
        """Whether this call's host shows CAD views: True, False, or None where nothing says yet. The
        evidence, strongest first (``host.py``): the host's own declaration; a view that reached this
        server; the call's turn (``codex exec``); the host that launched the shim, or a tab cad_open
        launched that never came."""
        if self.text:
            return False
        if self._declared or self._contacted:
            return True
        if self.tabs and host.headless(context.meta):
            return False
        return self.renders

    def _no_app(self, context: RequestContext) -> bool:
        """Whether this call's host shows no app: a text client, or one the evidence says shows none."""
        return self._cards(context) is False

    def _contact(self) -> None:
        """A view reached this server: its host draws them, whatever it said at initialize."""
        if not self._contacted:
            self._contacted = True
            LOG.info("a view reached this server: its host shows CAD views")

    def _tool_cad_open(self, arguments, context):
        model = self._model_path(arguments.get("source"))
        cards = self._cards(context)
        if cards is False:
            return self._show_in_browser(model)
        launch = self._launch(model, surface="agent")
        self._opened = time.monotonic()
        if cards:
            return _text(f"{model} is open in a new CAD tab. From now on, use cad_show to show models in it.", {"launch": launch})
        # Nothing says whether this host shows tabs: words true either way, and the next call finds out.
        from .browser import ViewerUnavailable

        try:
            elsewhere = f"the user can see it in their browser at {self._browser_url(model)}: give them this URL"
        except ViewerUnavailable:
            elsewhere = "nothing opened"
        return _text(f"Where this app shows CAD tabs, {model} opens in a new CAD tab with this answer; where it shows "
                     f"none, {elsewhere}. Do not tell the user a tab opened. Use cad_show next: it says where a model went.",
                     {"launch": launch})

    # the agent's tools ----------------------------------------------------------

    def _target(self, context: RequestContext, view_id: Any, *, needs_model: bool, sidebar: bool = True) -> Any:
        """The view the agent means: one it names, else the one a person touched last of its thread's
        views and, with ``sidebar``, the CAD sidebar's -- which another process serves
        (``sidebar.py``), so what a person selected there is read and captured there."""
        return next(iter(self._candidates(context, view_id, needs_model=needs_model, sidebar=sidebar)), None)

    def _candidates(self, context: RequestContext, view_id: Any, *, needs_model: bool, files: bool = False,
                    sidebar: bool = True) -> list[Any]:
        own = [view for view in self.views.live(context.meta.get("threadId"))
               if files or view.surface != "file" or view.id == view_id]
        touched = [(self.views.wall(view.focused), view) for view in own]
        if self.tabs and sidebar:
            touched += [(view.touched, view) for view in self.sidebar_views.live()]
        views = [view for _, view in sorted(touched, key=lambda pair: pair[0], reverse=True)]
        if view_id:
            views = [view for view in views if view.id == view_id]
        if needs_model:
            views = [view for view in views if view.model]
        return views

    def _tool_cad_show(self, arguments, context):
        _say_not_held(arguments.get("source"))
        return self._show(arguments, context)

    def _show(self, arguments, context):
        if self._no_app(context):
            return self._show_in_browser(self._model_path(arguments.get("source")))
        if not self.tabs:
            launch = self._mounted(self._launch(self._model_path(arguments.get("source")), surface="inline"))
            return _text(f"Showing {launch['model']} in CAD (view {launch['view']}).", {"launch": launch})
        model = self._model_path(arguments.get("source"))
        # A model shown goes beside this thread: Codex keeps the sidebar page running while the
        # person is in a thread, so a model sent there lands where nobody is looking. The sidebar
        # takes one only when the agent names its view.
        def target() -> Any:
            return self._target(context, arguments.get("view"), needs_model=False, sidebar=bool(arguments.get("view")))

        view = target()
        if view is None and self._opened is not None and time.monotonic() - self._opened < _OPENED_WITHIN:
            # The tab cad_open just launched: the host creates it only once that answer arrives.
            view = self.views.wait(target, timeout=OPENING_SECONDS)
            if view is None and self._cards(context) is None:
                # No tab came: this host shows none (a later view says otherwise).
                self.renders = False
                LOG.info("the tab cad_open launched never came: its host shows no CAD views")
                return self._show_in_browser(model)
            if view is None:
                self._pending = model
                return _text(f"The CAD tab cad_open opened is still opening; it shows {model} once it opens.",
                             {"delivered": 0, "opening": True})
        if view is None:
            self._model = model
            LOG.info("cad_show: no viewer for thread %s in process %d; live here: %s", context.meta.get("threadId") or "none",
                     os.getpid(), [(view.id, view.surface, view.thread_id) for view in self.views.live()] or "none")
            return _text("No CAD viewer is open in this thread. Call cad_open to open one.", {"delivered": 0})
        if not isinstance(view, SidebarView) and view.surface == "file":
            # The host's file handler shows the file it opened, and only that: the agent reads it
            # (cad_view names it), but shows nothing in it.
            if view.model == model:
                return _text(f"That view already shows {model}, and shows each rebuild by itself.", {"delivered": 0, "view": view.id})
            raise ToolFailed(f"That view is the app's own view of {os.path.basename(view.model or '') or 'a file'}, and "
                             "shows that file alone. Call cad_show without a view to show a model in this thread's CAD tab.",
                             "wrong_view")
        launch = self._launch(model)
        self._reach(launch)
        if isinstance(view, SidebarView):
            if view.model != model:
                self.sidebar_views.post(view.id, {"type": "show", "launch": launch})
            return _text(f"Showing {model} in the CAD sidebar, which shows each rebuild by itself.",
                         {"delivered": 1, "view": view.id, "sidebar": True})
        self.views.post([view.id], {"type": "show", "launch": launch})
        return _text(f"Showing {model} in CAD.", {"delivered": 1, "view": view.id})

    def _browser_url(self, model: str | None = None) -> str:
        """The web viewer's page of ``model`` (an absolute path or a document id), or of the home
        without one: the engine's own (``browser.viewer_url``), started if none runs. Raises
        ``ViewerUnavailable`` where the engine can give none."""
        from .browser import viewer_url

        return (self._viewer_url or viewer_url)(model)

    def _open_in_browser(self, method: str, body: bytes) -> dict[str, Any]:
        """``POST /__cad/browser/open`` with ``{"model": <path or id> | null}``, the card's Open in
        browser: this process opens the web viewer's page of that document (the home's with none) in
        the person's browser, through an owner-only redirect file so the page's token is on no
        command line (``browser_open``) -- a host may not follow a link to a loopback page, and Codex
        does not. ``{"opened": true}``, or 503 in words where no page or no browser can be opened
        here (no display, a remote shell), when the card opens its launch's page (``browser``)
        through its host instead. The request names a document, never a URL."""
        from cadgen.viewer import browser_open
        from .browser import ViewerUnavailable
        from .tunnel import _result

        json_type = {"content-type": "application/json"}

        def refused(status: int, error: str) -> dict[str, Any]:
            return _result(status, json_type, json.dumps({"error": error}).encode("utf-8"))

        if method.upper() != "POST":
            return _result(405, {"allow": "POST"}, b"")
        try:
            asked = json.loads(body or b"{}")
        except ValueError:
            return refused(400, "the body is not JSON")
        model = asked.get("model") if isinstance(asked, dict) else None
        if model is not None and not isinstance(model, str):
            return refused(400, "model is a path or a document id")
        cannot = browser_open.display_refusal()  # said before a page is asked of the engine
        if cannot is not None:
            return refused(503, cannot)
        try:
            self._open_page(self._browser_url(model or None))
        except (ViewerUnavailable, browser_open.CannotOpen) as failure:
            return refused(503, str(failure))
        return _result(200, json_type, b'{"opened":true}')

    def _open_page(self, url: str) -> None:
        """Open ``url`` in the person's browser through an owner-only redirect file
        (``browser_open``); ``CannotOpen`` in words where no browser can be opened here."""
        import webbrowser

        from cadgen.viewer import browser_open

        browser_open.open_page(url, opener=self._browser_opener or webbrowser.open)

    def _show_in_browser(self, model: str) -> dict[str, Any]:
        """A host with no app: the model's page in the CAD Viewer this machine runs, started if none
        is, to be opened in the person's browser unless a browser page reads that document already;
        the answer says which, with the page's URL for the agent to give the person. This process
        opens nothing: it runs in the environment of whatever started the engine, not the agent's.
        The host's stdio peer opens the page, from the request the answer carries (``browser.OPEN``,
        ``browser.deliver``), and nothing counts it as open until the peer says it opened
        (``notify``); a client with no peer is given the URL in words."""
        from .browser import OPEN, ViewerUnavailable

        self._model = model
        try:
            link = self._browser_url(model)
        except ViewerUnavailable as failure:
            raise ToolFailed(f"This app cannot show CAD views, and the CAD Viewer did not start ({failure}). Run "
                             f"`cadgen viewer --host 127.0.0.1 --json {model}` and open the url it prints.",
                             "no_viewer") from failure
        self.warm()  # the browser page's first document meshes on a pool already starting
        name = os.path.basename(model)
        cannot = f"No browser can be opened from here ({{reason}}); {name}'s page is {link}."
        peer = self._peer_browser
        asked = None
        if self._in_browser(model):
            said = f"{name} is already open in your browser at {link}; nothing was opened."
        elif peer is None:
            said = f"{name}'s page is {link}; nothing was opened, as this client opens no browser."
        elif isinstance(peer.get("refusal"), str):
            said = cannot.replace("{reason}", peer["refusal"])
        else:
            said = f"{name} opened in your browser at {link}."
            asked = {"url": link, "said": said, "failed": cannot}
            with self._asked_lock:
                self._asked[link] = model
                while len(self._asked) > _ASKED_KEPT:
                    del self._asked[next(iter(self._asked))]
        # Text alone: an app that shows a result's structured content shows it in place of the text
        # (Claude Code does), and the agent would get neither this guidance nor the update line.
        result = self._told(_text(f"{said}\nThis app shows no CAD view itself: give the user this URL. {FOLLOWS}"))
        if asked is not None:
            result["_meta"] = {OPEN: asked}
        return result

    def _told(self, result: dict[str, Any]) -> dict[str, Any]:
        """A text-only app has no card for the update notice (``cadgen/updates.py``): this process's
        first result that can carry it does, as a line for the agent to pass on."""
        if self._update_told:
            return result
        from cadgen import updates

        found = updates.notice()
        if found is not None:
            self._update_told = True
            result["content"].append({"type": "text", "text": updates.line(found)})
        return result

    def _shown(self, view_id: Any) -> Any:
        """The inline view the agent names by the token its cad_show returned: one the chat is still
        drawing is waited for."""
        if not isinstance(view_id, str) or not view_id:
            raise ToolFailed("Name the viewer: pass the view that cad_show returned.", "no_view")

        def found() -> Any:
            return next((view for view in self.views.live() if view.id == view_id), None)

        view = found()
        if view is None and view_id in self._mounting:
            view = self.views.wait(found, timeout=OPENING_SECONDS)
            if view is None:
                raise ToolFailed("That viewer has not opened yet: the chat has not drawn it (it may be waiting for the person "
                                 "to allow it, or be collapsed or scrolled away). Ask the person to look at it, then try again.", "no_view")
        if view is None:
            raise ToolFailed("That viewer is not open: it was closed, or a newer one took its place. Show the model again "
                             "with cad_show.", "no_view")
        return view

    def _tool_cad_view(self, arguments, context):
        live = [self._shown(arguments.get("view"))] if not self.tabs else self._candidates(context, None, needs_model=False, files=True)
        if not live:
            return _text("No CAD viewer is open in this thread.", {"views": []})
        # What each view last said it shows: a view sends its state whenever it changes, on the
        # sync it makes each second, so this answers at once without asking any of them.
        views = [{"view": view.id, "surface": "sidebar" if isinstance(view, SidebarView) else view.surface,
                  "model": view.model, **view.state} for view in live]
        return _text(json.dumps({"views": views}, indent=1), {"views": views})

    def _tool_cad_screenshot(self, arguments, context):
        deadline = time.monotonic() + CAPTURE_SECONDS
        if self._no_app(context):
            raise ToolFailed("This app shows no CAD view to capture: render one headless with `cadgen snapshot`.", "no_view")
        if self.tabs:
            view = self._target(context, arguments.get("view"), needs_model=True)
            if view is None and self._opened is not None and time.monotonic() - self._opened < _OPENED_WITHIN:
                # The tab cad_open just opened: the host is loading it, and it has not synced its model yet.
                view = self.views.wait(lambda: self._target(context, arguments.get("view"), needs_model=True), timeout=OPENING_SECONDS)
        else:
            view = self._shown(arguments.get("view"))
        if view is not None and not view.model:
            raise ToolFailed("That viewer shows no model yet.", "no_view")
        if view is None:
            raise ToolFailed("No CAD viewer with a model is open in this thread. Open one with cad_open, "
                             "or render headless with `cadgen snapshot`.", "no_view")
        if isinstance(view, SidebarView):
            reply = self.sidebar_views.ask(view.id, timeout=max(1.0, deadline - time.monotonic()))
            if reply is None:
                raise ToolFailed("The CAD sidebar did not answer in time: it may be closed or out of sight. Ask the person to "
                                 "open it, then capture again.", "timeout")
            if reply.get("error"):
                raise ToolFailed(f"The CAD viewer could not capture: {reply['error']}", "view_error")
        else:
            try:
                reply = self.views.ask(view.id, "capture", timeout=max(1.0, deadline - time.monotonic()))
            except NoAnswer as failure:
                raise ToolFailed(f"The CAD viewer could not capture: {failure}", failure.reason) from failure
        png = reply.get("png")
        if not isinstance(png, str) or not png:
            raise ToolFailed("The CAD viewer answered without an image.", "view_error")
        from .tunnel import MAX_REPLY_BYTES

        if len(png) // 4 * 3 > MAX_REPLY_BYTES:
            # Sent, a message this long could close the host's connection (``tunnel.MAX_REPLY_BYTES``).
            raise ToolFailed(f"The CAD viewer's picture is {len(png) // 4 * 3 / 1e6:.1f} MB, more than one message to this "
                             "host may carry. Ask the person to make the view smaller, then capture again.", "too_large")
        return {"content": [{"type": "image", "data": png, "mimeType": "image/png"},
                            {"type": "text", "text": f"{view.model} as shown in CAD."}],
                "structuredContent": {"view": view.id, "model": view.model}}

    # the page's tools -----------------------------------------------------------

    def _app_only(self, arguments: dict[str, Any]) -> None:
        """Refuse a page tool's call that does not carry this session's app capability: only the
        page, which the launch's metadata delivered it to, reports a view or answers a capture."""
        token = arguments.get(_APP_TOKEN_ARGUMENT)
        if not isinstance(token, str) or not secrets.compare_digest(token.encode("utf-8"), self._app_token.encode("utf-8")):
            raise ToolFailed("This CAD view was opened before CAD restarted: close it and open CAD again."
                             if isinstance(token, str) and token else "Only a CAD view calls this tool.", "bad_request")

    def _register(self, arguments: dict[str, Any], context: RequestContext) -> str:
        self._app_only(arguments)
        view_id, surface = arguments.get("view"), arguments.get("surface")
        if not isinstance(view_id, str) or not view_id or not isinstance(surface, str):
            raise RpcError(INVALID_PARAMS, "view and surface are required")
        thread_id = context.meta.get("threadId")
        self._contact()
        first = view_id not in self.views
        if first:
            LOG.info("view %s (%s) syncs here, thread %s, process %d", view_id, surface, thread_id or "none", os.getpid())
        self.views.register(view_id, surface=surface, thread_id=thread_id, model=arguments.get("model"))
        if first and surface == "agent" and self._pending is not None:
            # What cad_show sent the tab cad_open launched while it was still opening.
            model, self._pending = self._pending, None
            if model != arguments.get("model"):
                self.views.post([view_id], {"type": "show", "launch": self._launch(model)})
        return view_id

    def _tool_cad_sync(self, arguments, context):
        """A view's one call each second: it reports, the server answers with what waits.

        Up: the view's model, its state when it changed (what ``cad_view`` reads), ``focused``
        when a person just touched it, and ``closed`` once a newer view took its place. Down: the
        agent's requests for it (``show``, ``capture``), and for what it watches -- its model's
        catalog entry -- the entry's revision (the view reads the catalog again only when that
        moves). A STEP or an ``.xbf`` the view shows tells it of a new version itself, through the
        engine's routes (``cadgen.viewer.documents``): no build feed rides here.
        """
        view_id = self._register(arguments, context)
        self._mounting.pop(view_id, None)
        sidebar = self.tabs and arguments.get("surface") == "sidebar"
        if arguments.get("closed") is True:  # a view a newer one replaced: the agent can no longer reach it
            self.views.forget(view_id)
            if sidebar:
                self.sidebar_views.forget(view_id)
            return _data({"events": []})
        model = arguments.get("model")
        if isinstance(model, str):
            self.sync_document(model)  # the canonical address as the view names it, never a path of it (law 14)
        state = arguments.get("state") if isinstance(arguments.get("state"), dict) else None
        focused = arguments.get("focused") is True
        # Use the agent's tools never see: a person touching the view. (The file on screen is counted
        # as the view adds it to the library, through ``cad_http``.)
        if focused:
            self.analytics.viewed()
        if state is not None or focused:
            self.views.report(view_id, model=arguments.get("model"), state=state, focused=focused)
        if focused and isinstance(arguments.get("model"), str):
            self._model = arguments["model"]
        answer: dict[str, Any] = {}
        watch = arguments.get("watch")
        if isinstance(watch, dict) and isinstance(watch.get("file"), str):
            # What the view watches never costs it the agent's requests: a catalog that will not
            # read is said here, and the events still go.
            try:
                answer["catalog"] = {"revision": self.tunnel.catalog_revision(watch["file"])}
            except Exception as error:  # noqa: BLE001 - the view shows the catalog's own failure on its next read
                answer["catalog"] = {"error": str(error) or type(error).__name__}
        if sidebar:
            # Every thread's agent can reach the sidebar (``sidebar.py``): it says what it shows
            # there, and takes what was left for it.
            view = self.views.view(view_id)
            self.sidebar_views.publish(view_id, model=view.model if view else arguments.get("model"),
                                       state=view.state if view else None, touched=focused)
        # Last, so a sync that failed before this point has taken nothing from the queue.
        answer["events"] = self.views.poll(view_id) + (self.sidebar_views.take(view_id) if sidebar else [])
        return _data(answer)

    def _tool_cad_capture_reply(self, arguments, context):
        self._app_only(arguments)
        reply: dict[str, Any] = {key: arguments[key] for key in ("png", "error") if isinstance(arguments.get(key), str)}
        request_id = str(arguments.get("requestId"))
        # A capture another thread's agent asked of this process's sidebar view goes back to it.
        accepted = self.views.reply(request_id, reply) or (self.tabs and self.sidebar_views.answer(request_id, reply))
        return _data({"accepted": bool(accepted)})

    def _tool_cad_http(self, arguments, context):
        try:
            body = base64.b64decode(arguments.get("body") or "", validate=True)
        except (ValueError, binascii.Error) as error:
            raise ToolFailed(str(error), "bad_request") from error
        headers = arguments.get("headers") if isinstance(arguments.get("headers"), dict) else {}
        headers = {name.lower(): str(value) for name, value in headers.items()}
        token = headers.pop(_APP_TOKEN_HEADER, "")
        app = not self.text and secrets.compare_digest(token.encode("utf-8"), self._app_token.encode("utf-8"))
        if app:
            self._contact()
        if token and not app:
            # A view opened in an earlier session (the engine restarted under its host) holds that one's.
            raise ToolFailed("This CAD view was opened before CAD restarted: close it and open CAD again.", "bad_request")
        method, url = str(arguments.get("method") or "GET"), str(arguments.get("url") or "")
        from cadgen.viewer import url_norm

        if app and url_norm.request_pathname(url) == _BROWSER_OPEN_ROUTE:
            return _data(self._open_in_browser(method, body))
        reply = self.tunnel.serve(method=method, url=url, headers=headers, body=body, agent=not app)
        if app:
            return _data(reply)
        return _text(base64.b64decode(reply["body"]).decode("utf-8"), reply, error=reply["status"] >= 400)
