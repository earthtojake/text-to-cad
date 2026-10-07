"""``cadgen mcp``: CAD beside an agent's chat, as an MCP App.

Nothing heavy happens until a tool needs it: initialize and tools/list read no
store, start no daemon and import no CAD kernel. Everything the views share --
the open views, what was last shown -- is plain process memory.

One page serves every surface. The tool that opens a surface returns a
*launch* -- a model by its absolute path, or the home -- and the page renders it;
a view browses from its model's folder, so nothing says where it may browse. Once
open, a view makes ONE call each second, ``cad_sync``: it says what it shows (its
model, its selection, whether a person just touched it) and what it watches (its
model's catalog entry, a STEP's build feed), and gets back the agent's requests
and what changed. Everything else -- its model, the library and the home's Open,
Reveal, the person's analytics answer and features, the update check -- it reaches
through ``cad_http``, the viewer's own HTTP routes. No call is held open
(``views.py``). Agents name models by absolute path only.

Hosts present views in one of three ways, told apart at initialize:

- *Tabs* (Codex, and any host that declares the ``dev.texttocad/tabs`` client
  extension with the ``global``, ``thread`` and ``file`` entrypoints). The host
  presents CAD as a sidebar page, a tab per thread and a file handler. The agent
  opens a tab once (``cad_open``) and then drives it (``cad_show``). A host that
  declares tabs takes on what Codex does: it starts one server process per thread,
  since a call that names no view reaches the thread's own tab.
- *Inline* (every other MCP Apps host: Claude, VS Code, ...). Each call to a tool
  with a UI mounts a new view in the chat, and the old ones stay. So ``cad_show``
  is that tool, each launch is stamped with an order for the views to retire
  their elders by, and a view the agent reads is named by the token its
  ``cad_show`` returned: one process may serve many chats, and no host says which.
- *Text* (a client that renders no MCP Apps, so does not advertise the
  ``io.modelcontextprotocol/ui`` extension: Grok, Zed, Gemini CLI, Claude Code in a
  terminal, ...). ``cad_show`` is the only tool, and it answers with a link to the
  model in the CAD Viewer (``browser.py``), the one this machine runs, started
  if none is; nothing opens a browser.

``CADGEN_MCP_PRESENTATION=inline|text`` settles a non-Codex client that renders MCP
Apps without advertising them (the reference host, ``basic-host``, is one).
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import sys
import itertools
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from cadgen.viewer.scanner import SOURCE_EXTENSIONS

from .protocol import INVALID_PARAMS, METHOD_NOT_FOUND, Connection, RequestContext, RpcError, claim_stdout
from .ui import MIME, RESOURCE_META, AppPage
from .sidebar_views import SidebarView
from .views import NoAnswer, ViewRegistry

LOG = logging.getLogger("cadgen.mcp")

NAME = "cad"
TITLE = "CAD"
# The launch/view protocol between this server and its page: a launch names a model by its absolute
# path (`page: viewer`) or the home (`page: home`, its recents with it), and carries what the page
# needs to start on it alone (the server's version and platform); a view makes one call a second
# (`cad_sync`) and reaches the viewer's routes through `cad_http`, by absolute path.
PROTOCOL = 5
_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
_RESOURCE_NOT_FOUND = -32002
EXTENSIONS = sorted(SOURCE_EXTENSIONS)

# Clients that present CAD as tabs (see the module docstring): Codex by name, since it declares nothing,
# and any client that declares every entrypoint CAD uses under cadgen's own extension. Every other
# client is shown views inline, or told where the Viewer has them when it renders no MCP Apps.
_TAB_HOSTS = frozenset({"codex-mcp-client"})
_UI_EXTENSION = "io.modelcontextprotocol/ui"
_TABS_EXTENSION = "dev.texttocad/tabs"
_TAB_ENTRYPOINTS = frozenset({"global", "thread", "file"})

INSTRUCTIONS = (
    "CAD shows local CAD models (STEP, STL, GLB, 3MF, DXF, URDF, SDF) in a viewer tab beside the chat. "
    "To show a model, call cad_show with its absolute path: it switches an open viewer and never opens a tab. "
    "Only when cad_show reports no open viewer, call cad_open, once. "
    "Viewers refresh when files change, so never reopen after a rebuild. "
    "cad_view reports what the user is looking at and has selected; cad_screenshot returns what they see."
)

INLINE_INSTRUCTIONS = (
    "CAD shows local CAD models (STEP, STL, GLB, 3MF, DXF, URDF, SDF) in interactive viewers in the chat. "
    "Call cad_show with a model's absolute path to show it: each call adds a viewer and pauses the earlier ones. "
    "Viewers refresh when their files change, so never show a model again after a rebuild. "
    "cad_view reports what the user is looking at and has selected in a viewer, and cad_screenshot returns "
    "what they see; both take the view that cad_show returned."
)

TEXT_INSTRUCTIONS = (
    "CAD opens local CAD models (STEP, STL, GLB, 3MF, DXF, URDF, SDF) in the CAD Viewer in the user's browser: "
    "this app cannot show CAD views itself. Call cad_show with a model's absolute path to get its link and share it. "
    "The Viewer refreshes when the file changes, so share a model's link once, not after every rebuild."
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


class ToolFailed(Exception):
    """A tool call that fails the way its caller should read: as the tool's result."""


def _object(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties or {}, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


_PATH = {"type": "string", "description": "A CAD file's absolute path."}
_VIEW = {"type": "string", "description": "A view id from cad_view; defaults to the most recently used viewer."}
# What a view watches: its model's catalog entry, and the build feed of each STEP it shows.
_WATCH = _object({"file": {"type": ["string", "null"]}, "previews": {"type": "array", "items": {"type": "string"}, "maxItems": 4}})
_SHOWN_VIEW = {"type": "string", "description": "The view that cad_show returned."}
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
# Every client's: the agent reports CAD's telemetry setting, or turns sharing off when the user asks.
_TELEMETRY_TOOL = {
    "name": "cad_telemetry", "title": "CAD telemetry", "icons": [ICON],
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
    "description": ("Report whether cadgen sends usage stats (counts of tool calls, view activity, files shown, builds "
                    "and snapshots, tagged with a random ID; never file names, paths, contents or prompts), or turn "
                    "them off. Call with action off only when the user asks."),
    "inputSchema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["status", "off"]}},
                    "additionalProperties": False},
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


def _presentation(client: dict[str, Any], offered: dict[str, Any]) -> str:
    """``tabs``, ``inline`` or ``text``: how this client shows views (see the module docstring)."""
    extensions = offered.get("extensions") if isinstance(offered.get("extensions"), dict) else {}
    declared = extensions.get(_TABS_EXTENSION)
    entrypoints = declared.get("entrypoints") if isinstance(declared, dict) else None
    if client.get("name") in _TAB_HOSTS or (isinstance(entrypoints, list) and _TAB_ENTRYPOINTS <= set(entrypoints)):
        return "tabs"
    forced = str(os.environ.get("CADGEN_MCP_PRESENTATION") or "").strip()
    if forced in ("inline", "text"):
        return forced
    ui = extensions.get(_UI_EXTENSION)
    return "inline" if isinstance(ui, dict) and MIME in (ui.get("mimeTypes") or []) else "text"


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
    """The local path a ``file:`` URI names (``file:///C:/x`` is ``C:/x`` on Windows), else None."""
    if not isinstance(value, str) or not value.startswith("file:"):
        return None
    path = unquote(urlparse(value).path)
    if os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path or None


class Server:
    def __init__(self, *, page: AppPage | None = None, recents=None, tunnel=None, viewer_url=None,
                 sidebar_views=None, analytics=None) -> None:
        self.page = page or AppPage()
        self.views = ViewRegistry()
        self._recents = recents
        self._tunnel = tunnel
        self._sidebar_views = sidebar_views
        self._model: str | None = None  # what this thread last opened or showed
        self._tools: list[dict[str, Any]] | None = None
        self.tabs = False  # decided at initialize: see the module docstring
        self.text = False
        self._viewer_url = viewer_url
        self._order = itertools.count(1)
        self._analytics = analytics
        self._update_told = False

    # -- lazily built parts ----------------------------------------------------

    @property
    def recents(self):
        if self._recents is None:
            from cadgen.viewer.recents import RecentStore

            self._recents = RecentStore()
        return self._recents

    @property
    def sidebar_views(self):
        """The CAD sidebar's views, which every process reaches (``sidebar_views.py``)."""
        if self._sidebar_views is None:
            from .sidebar_views import SidebarViews

            # Beside the model library: the person's state, shared by every process of theirs.
            self._sidebar_views = SidebarViews(Path(self.recents.root).parent / "sidebar-views")
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
        if method == "initialize":
            return self._initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tools()}
        if method == "tools/call":
            return self._call(params, context)
        if method == "resources/list":
            return {"resources": [{"uri": self.page.uri, "name": "CAD", "title": TITLE, "mimeType": MIME, "_meta": RESOURCE_META}]}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        if method == "resources/read":
            uri = params.get("uri")
            if not self.page.owns(uri):
                raise RpcError(_RESOURCE_NOT_FOUND, f"no resource {uri}")
            return {"contents": [{"uri": uri, "mimeType": MIME, "text": self.page.html(), "_meta": RESOURCE_META}]}
        raise RpcError(METHOD_NOT_FOUND, f"{method} is not supported")

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        from cadgen import __version__

        client = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
        offered = params.get("capabilities") if isinstance(params.get("capabilities"), dict) else {}
        presentation = _presentation(client, offered)
        self.tabs, self.text = presentation == "tabs", presentation == "text"
        if presentation == "inline":
            self.page = self.page.presenting("inline")
        self._tools = None
        extensions = sorted(offered["extensions"]) if isinstance(offered.get("extensions"), dict) else []
        LOG.info("client %s %s: %s views (extensions: %s)", client.get("name"), client.get("version"), presentation,
                 ", ".join(extensions) or "none")
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
             "description": ("Open a NEW CAD viewer tab beside the chat showing a local model (STEP, STL, GLB, 3MF, DXF, "
                             "URDF, SDF). Every call opens another tab, so call it only when cad_show reports that no "
                             "viewer is open, and never again after a rebuild: open viewers refresh by themselves."),
             "inputSchema": _object({"path": _PATH}, ["path"])},
            {"name": "cad_show", "title": "Show in CAD", "icons": [ICON], "annotations": _READ_ONLY,
             "description": ("Show a model in the CAD viewer already open in this thread, switching it if another model "
                             "is showing. Never opens a tab. Reports whether a viewer took it; if none is open, call cad_open."),
             "inputSchema": _object({"path": _PATH, "view": _VIEW}, ["path"])},
            {"name": "cad_view", "title": "Read CAD view", "icons": [ICON], "annotations": _READ_ONLY,
             "description": ("Describe the CAD viewers open in this thread: each one's model and revision, what the user "
                             "has selected (as references you can quote back), and the camera."),
             "inputSchema": _object()},
            {"name": "cad_screenshot", "title": "Capture CAD view", "icons": [ICON], "annotations": _READ_ONLY,
             "description": "Capture a PNG of exactly what an open CAD viewer in this thread shows right now.",
             "inputSchema": _object({"view": _VIEW})},
            _TELEMETRY_TOOL,
            *self._page_tools(),
        ]

    def _inline_catalog(self) -> list[dict[str, Any]]:
        shows = {"ui": {"resourceUri": self.page.uri}}
        return [
            {"name": "cad_show", "title": "Show in CAD", "icons": [ICON], "annotations": _READ_ONLY, "_meta": shows,
             "description": ("Show a local CAD model (STEP, STL, GLB, 3MF, DXF, URDF, SDF) in an interactive viewer in the "
                             "chat. Each call adds a viewer and pauses the earlier ones. A viewer refreshes by itself when "
                             "its file changes, so show a model once, not after every rebuild. The result names the view: "
                             "pass it to cad_view or cad_screenshot."),
             "inputSchema": _object({"path": _PATH}, ["path"])},
            {"name": "cad_view", "title": "Read CAD view", "icons": [ICON], "annotations": _READ_ONLY,
             "description": ("Describe a CAD viewer in this chat: its model and revision, what the user has selected (as "
                             "references you can quote back), and the camera."),
             "inputSchema": _object({"view": _SHOWN_VIEW}, ["view"])},
            {"name": "cad_screenshot", "title": "Capture CAD view", "icons": [ICON], "annotations": _READ_ONLY,
             "description": "Capture a PNG of exactly what a CAD viewer in this chat shows right now.",
             "inputSchema": _object({"view": _SHOWN_VIEW}, ["view"])},
            _TELEMETRY_TOOL,
            *self._page_tools(),
        ]

    def _text_catalog(self) -> list[dict[str, Any]]:
        """No page to open or read: cad_show hands over a link to the model in the CAD Viewer."""
        return [
            {"name": "cad_show", "title": "Show in CAD", "icons": [ICON], "annotations": _READ_ONLY,
             "description": ("Get a link that opens a local CAD model (STEP, STL, GLB, 3MF, DXF, URDF, SDF) in the CAD "
                             "Viewer in the user's browser; this app cannot show CAD views itself. The Viewer refreshes "
                             "when the file changes, so share a model's link once, not after every rebuild."),
             "inputSchema": _object({"path": _PATH}, ["path"])},
            _TELEMETRY_TOOL,
        ]

    def _page_tools(self) -> list[dict[str, Any]]:
        """The tools only the page calls: its sync, its answer to a capture, and the viewer's routes."""

        def app(name: str, title: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
            return {"name": name, "title": title, "description": description, "inputSchema": schema,
                    "annotations": _READ_ONLY, "_meta": {"ui": {"visibility": ["app"]}}}

        return [
            app("cad_sync", "CAD sync", "This view's one call each second: what it shows and watches, and what is waiting for it.",
                _object({"view": {"type": "string"}, "surface": {"type": "string"}, "model": {"type": ["string", "null"]},
                         "focused": {"type": "boolean"}, "closed": {"type": "boolean"}, "state": {"type": "object"},
                         "watch": _WATCH}, ["view", "surface"])),
            app("cad_capture_reply", "Answer CAD", "Answer the server's request for a capture.",
                _object({"requestId": {"type": "string"}, "png": {"type": "string"}, "error": {"type": "string"}}, ["requestId"])),
            app("cad_http", "CAD viewer request", "One request to the CAD viewer's routes, bodies base64.",
                _object({"method": {"type": "string"}, "url": {"type": "string"},
                         "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                         "body": {"type": "string"}}, ["method", "url"])),
        ]

    # -- calls -----------------------------------------------------------------

    def _call(self, params: dict[str, Any], context: RequestContext) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise RpcError(INVALID_PARAMS, "arguments must be an object")
        # Only a tool this client was listed: a text client has no page, so no one there answers a
        # card or reaches the viewer's routes for the person.
        listed = any(tool["name"] == name for tool in self.tools())
        handler = getattr(self, f"_tool_{name}", None) if listed else None
        if handler is None:
            raise RpcError(INVALID_PARAMS, f"unknown tool {name!r}")
        started = time.monotonic()
        ok = False
        try:
            result = handler(arguments, context)
            ok = not (isinstance(result, dict) and result.get("isError"))
            return result
        except ToolFailed as failure:
            return _text(str(failure), error=True)
        finally:
            self.analytics.called(name, ok)
            if name not in ("cad_sync", "cad_http"):
                LOG.info("%s %.0fms", name, (time.monotonic() - started) * 1000)

    # launches -----------------------------------------------------------------

    def _launch(self, model: str, *, surface: str | None = None) -> dict[str, Any]:
        """The launch that shows ``model`` (absolute): the view browses from its folder, and adds the
        model to the library once it is on screen, as every CAD view does."""
        launch: dict[str, Any] = {"protocol": PROTOCOL, "page": "viewer", "model": model}
        if surface:
            launch["surface"] = surface
        self._model = model
        return _stamped(launch)

    def _home(self, *, surface: str | None = None) -> dict[str, Any]:
        """The launch that shows the home: the models opened before, which come with it so its cards
        draw at once, and Open with the desktop's chooser."""
        try:
            recents = [entry.public() for entry in self.recents.list()]
        except Exception:  # the home opens whatever the store says
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
        # Wall-clock time orders views across restarts of this process; seq breaks a tie.
        launch["order"] = {"createdAt": int(time.time() * 1000), "seq": seq}
        return launch

    def _model_path(self, value: Any) -> str:
        """An existing CAD file, from the absolute path a caller named."""
        if not isinstance(value, str) or not value.strip():
            raise ToolFailed("Name a CAD file by its absolute path.")
        path = file_uri_path(value) or os.path.expanduser(value.strip())
        if not os.path.isabs(path):
            raise ToolFailed(f"{value} is not an absolute path: name the model by its absolute path.")
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            raise ToolFailed(f"No file at {path}.")
        if os.path.splitext(path)[1].lower() not in SOURCE_EXTENSIONS:
            raise ToolFailed(f"CAD opens {', '.join(EXTENSIONS)} files; {os.path.basename(path)} is not one.")
        return path

    def _tool_cad_home(self, arguments, context):
        return _text("CAD is open.", {"launch": self._home(surface="sidebar")})

    def _tool_cad_tab(self, arguments, context):
        current = next((view.model for view in self.views.live(context.meta.get("threadId")) if view.model), None) or self._model
        if current is not None and not os.path.isfile(current):
            current = None
        launch = self._launch(current, surface="tab") if current else self._home(surface="tab")
        return _text("CAD is open.", {"launch": launch})

    def _tool_cad_file(self, arguments, context):
        resource = context.meta.get("openai/resource")
        path = resource.get("path") if isinstance(resource, dict) else None
        if not path:
            file = arguments.get("file")
            path = file_uri_path(file.get("resourceUri")) if isinstance(file, dict) else None
        model = self._model_path(path)
        # The host's own file tree is this surface's navigation: the page shows the file alone.
        return _text(f"{os.path.basename(model)} is open in CAD.", {"launch": self._launch(model, surface="file")})

    def _tool_cad_open(self, arguments, context):
        model = self._model_path(arguments.get("path"))
        launch = self._launch(model, surface="agent")
        return _text(f"{model} is open in a new CAD tab. From now on, use cad_show to show models in it.", {"launch": launch})

    def _tool_cad_telemetry(self, arguments, context):
        # The agent may report the setting or turn sharing off for the person; only the person turns it on.
        from cadgen.analytics import PRIVACY_URL

        if arguments.get("action") == "off":
            if not self.analytics.choose(False, by="agent").get("saved"):
                return _text("CAD telemetry could not be turned off for good: cadgen's state directory could not be "
                             "written. This CAD app sends nothing more until it restarts; DO_NOT_TRACK=1 in the agent "
                             "app's environment keeps telemetry off.", {"sharing": False})
            return _text("CAD telemetry is off. The install id was deleted, and the data sent under it is being deleted.",
                         {"sharing": False})
        found = self.analytics.status()
        why = {"environment": "set by the environment (DO_NOT_TRACK or CADGEN_TELEMETRY)",
               "choice": "the user's choice",
               "default": "on by default: a cadgen command told the user once",
               "untold": "not on: no cadgen command has told the user, and none does in CI or from a development install"}.get(
                   found["reason"], "off: the setting could not be read")
        state = "on" if found["sharing"] else "off"
        return _text(f"cadgen's usage stats are {state} ({why}). They count CAD tool calls, view activity, files shown, "
                     "builds and snapshots, tagged with a random ID; never file names, paths, contents or prompts. The user "
                     "turns them off in the CAD app's menu (the logo at the top left of a view) or with "
                     f"`cadgen telemetry off`. Policy: {PRIVACY_URL}",
                     {"sharing": found["sharing"], "reason": found["reason"]})

    # the agent's tools ----------------------------------------------------------

    def _target(self, context: RequestContext, view_id: Any, *, needs_model: bool, sidebar: bool = True) -> Any:
        """The view the agent means: one it names, else the one a person touched last of its thread's
        views and, with ``sidebar``, the CAD sidebar's -- which another process serves
        (``sidebar_views.py``), so what a person selected there is read and captured there."""
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
        if self.text:
            return self._show_in_browser(self._model_path(arguments.get("path")))
        if not self.tabs:
            launch = self._mounted(self._launch(self._model_path(arguments.get("path")), surface="inline"))
            return _text(f"Showing {launch['model']} in CAD (view {launch['view']}).", {"launch": launch})
        model = self._model_path(arguments.get("path"))
        # A model shown goes beside this thread: Codex keeps the sidebar page running while the
        # person is in a thread, so a model sent there lands where nobody is looking. The sidebar
        # takes one only when the agent names its view.
        view = self._target(context, arguments.get("view"), needs_model=False, sidebar=bool(arguments.get("view")))
        if view is None:
            self._model = model
            LOG.info("cad_show: no viewer for thread %s in process %d; live here: %s", context.meta.get("threadId") or "none",
                     os.getpid(), [(view.id, view.surface, view.thread_id) for view in self.views.live()] or "none")
            return _text("No CAD viewer is open in this thread. Call cad_open to open one.", {"delivered": 0})
        launch = self._launch(model)
        if isinstance(view, SidebarView):
            if view.model != model:
                self.sidebar_views.post(view.id, {"type": "show", "launch": launch})
            return _text(f"Showing {model} in the CAD sidebar, which shows each rebuild by itself.",
                         {"delivered": 1, "view": view.id, "sidebar": True})
        self.views.post([view.id], {"type": "show", "launch": launch})
        return _text(f"Showing {model} in CAD.", {"delivered": 1, "view": view.id})

    def _show_in_browser(self, model: str) -> dict[str, Any]:
        """The model's link in the CAD Viewer this machine runs, started if none is."""
        from .browser import ViewerUnavailable, model_link, viewer_url

        self._model = model
        try:
            url = (self._viewer_url or viewer_url)()
        except ViewerUnavailable as failure:
            raise ToolFailed(f"This app cannot show CAD views, and the CAD Viewer did not start ({failure}). Run "
                             f"`cadgen viewer --host 127.0.0.1 --json --detach` and open {model_link('<the url it prints>', model)}.") from failure
        link = model_link(url, model)
        # Text alone: an app that shows a result's structured content shows it in place of the text
        # (Claude Code does), and the agent would get neither this guidance nor the update line.
        return self._told(_text(f"This app cannot show CAD views, so {os.path.basename(model)} is in the CAD Viewer: {link}\n"
                                "The Viewer refreshes when the file changes: share this link once, not after every rebuild."))

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
        """The inline view the agent names by the token its cad_show returned."""
        if not isinstance(view_id, str) or not view_id:
            raise ToolFailed("Name the viewer: pass the view that cad_show returned.")
        view = next((view for view in self.views.live() if view.id == view_id), None)
        if view is None:
            raise ToolFailed("That viewer is not open: it was closed, or a newer one took its place. Show the model again with cad_show.")
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
        view = self._target(context, arguments.get("view"), needs_model=True) if self.tabs else self._shown(arguments.get("view"))
        if view is not None and not view.model:
            raise ToolFailed("That viewer shows no model yet.")
        if view is None:
            raise ToolFailed("No CAD viewer with a model is open in this thread. Open one with cad_open, "
                             "or render headless with `cadgen snapshot`.")
        if isinstance(view, SidebarView):
            reply = self.sidebar_views.ask(view.id)
            if reply is None:
                raise ToolFailed("The CAD sidebar did not answer in time; is it still open?")
            if reply.get("error"):
                raise ToolFailed(f"The CAD viewer could not capture: {reply['error']}")
        else:
            try:
                reply = self.views.ask(view.id, "capture")
            except NoAnswer as failure:
                raise ToolFailed(f"The CAD viewer could not capture: {failure}") from failure
        png = reply.get("png")
        if not isinstance(png, str) or not png:
            raise ToolFailed("The CAD viewer answered without an image.")
        from .tunnel import MAX_REPLY_BYTES

        if len(png) // 4 * 3 > MAX_REPLY_BYTES:
            # Sent, a message this long could close the host's connection (``tunnel.MAX_REPLY_BYTES``).
            raise ToolFailed(f"The CAD viewer's picture is {len(png) // 4 * 3 / 1e6:.1f} MB, more than one message to this "
                             "host may carry. Ask the person to make the view smaller, then capture again.")
        return {"content": [{"type": "image", "data": png, "mimeType": "image/png"},
                            {"type": "text", "text": f"{view.model} as shown in CAD."}],
                "structuredContent": {"view": view.id, "model": view.model}}

    # the page's tools -----------------------------------------------------------

    def _register(self, arguments: dict[str, Any], context: RequestContext) -> str:
        view_id, surface = arguments.get("view"), arguments.get("surface")
        if not isinstance(view_id, str) or not view_id or not isinstance(surface, str):
            raise RpcError(INVALID_PARAMS, "view and surface are required")
        thread_id = context.meta.get("threadId")
        if view_id not in self.views:
            LOG.info("view %s (%s) syncs here, thread %s, process %d", view_id, surface, thread_id or "none", os.getpid())
        self.views.register(view_id, surface=surface, thread_id=thread_id, model=arguments.get("model"))
        return view_id

    def _tool_cad_sync(self, arguments, context):
        """A view's one call each second: it reports, the server answers with what waits.

        Up: the view's model, its state when it changed (what ``cad_view`` reads), ``focused``
        when a person just touched it, and ``closed`` once a newer view took its place. Down: the
        agent's requests for it (``show``, ``capture``), and for what it watches -- its model's
        catalog entry and the build feed of any STEP it shows -- the entry's revision (the view
        reads the catalog again only when that moves) and each feed's current status.
        """
        view_id = self._register(arguments, context)
        sidebar = self.tabs and arguments.get("surface") == "sidebar"
        if arguments.get("closed") is True:  # a view a newer one replaced: the agent can no longer reach it
            self.views.forget(view_id)
            if sidebar:
                self.sidebar_views.forget(view_id)
            return _data({"events": []})
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
            else:
                files = [item for item in watch.get("previews") or [] if isinstance(item, str)][:4]
                if files:
                    answer["previews"] = [{"file": item, **self.tunnel.preview(item)} for item in files]
        if sidebar:
            # Every thread's agent can reach the sidebar (``sidebar_views.py``): it says what it shows
            # there, and takes what was left for it.
            view = self.views.view(view_id)
            self.sidebar_views.publish(view_id, model=view.model if view else arguments.get("model"),
                                       state=view.state if view else None, touched=focused)
        # Last, so a sync that failed before this point has taken nothing from the queue.
        answer["events"] = self.views.poll(view_id) + (self.sidebar_views.take(view_id) if sidebar else [])
        return _data(answer)

    def _tool_cad_capture_reply(self, arguments, context):
        reply: dict[str, Any] = {key: arguments[key] for key in ("png", "error") if isinstance(arguments.get(key), str)}
        request_id = str(arguments.get("requestId"))
        # A capture another thread's agent asked of this process's sidebar view goes back to it.
        accepted = self.views.reply(request_id, reply) or (self.tabs and self.sidebar_views.answer(request_id, reply))
        return _data({"accepted": bool(accepted)})

    def _tool_cad_http(self, arguments, context):
        try:
            body = base64.b64decode(arguments.get("body") or "", validate=True)
        except (ValueError, binascii.Error) as error:
            raise ToolFailed(str(error)) from error
        headers = arguments.get("headers") if isinstance(arguments.get("headers"), dict) else {}
        return _data(self.tunnel.serve(method=str(arguments.get("method") or "GET"), url=str(arguments.get("url") or ""),
                                       headers=headers, body=body))


def serve(argv: list[str] | None = None) -> int:
    """Serve MCP on this process's standard streams until the host closes them."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="cadgen mcp: %(message)s")
    protocol_out = claim_stdout()
    from cadgen import updates
    from cadgen.analytics import Recorder

    analytics = Recorder()
    analytics.start()
    updates.refresh()
    server = Server(analytics=analytics)
    connection = Connection(sys.stdin.buffer, protocol_out, server.handle, workers=64)
    try:
        connection.serve()
    finally:
        analytics.close()
    return 0
