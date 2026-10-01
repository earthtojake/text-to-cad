"""``cadgen mcp``: CAD beside an agent's chat, as an MCP App.

Nothing heavy happens until a tool needs it: initialize and tools/list read no
store, start no daemon and import no CAD kernel. Everything the views share --
the workspace, the open views, what was last shown -- is plain process memory.

One page serves every surface. The tool that opens a surface returns a
*launch* -- which page, which model, which root to browse -- and the page renders
it; nothing in the page guesses where it is. Once open, a view makes ONE call each
second, ``cad_sync``: it says what it shows (its model, its selection, whether a
person just touched it) and what it watches (its root's catalog, a STEP's build
feed), and gets back the agent's requests and what changed. It reaches the
viewer's own HTTP routes through ``cad_http``. No call is held open (``views.py``).

Hosts present views in one of three ways, told apart at initialize:

- *Tabs* (Codex). The host starts a process per thread and presents CAD as a
  sidebar page, a tab per thread and a file handler. The agent opens a tab once
  (``cad_open``) and then drives it (``cad_show``).
- *Inline* (every other MCP Apps host: Claude, VS Code, ...). Each call to a tool
  with a UI mounts a new view in the chat, and the old ones stay. So ``cad_show``
  is that tool, each launch is stamped with an order for the views to retire
  their elders by, and a view the agent reads is named by the token its
  ``cad_show`` returned: one process may serve many chats, and no host says which.
- *Text* (a client that renders no MCP Apps, so does not advertise the
  ``io.modelcontextprotocol/ui`` extension: Grok, Zed, Gemini CLI, Claude Code, ...).
  ``cad_show`` is the only tool, and it answers with a link to the model in the CAD
  Viewer (``browser.py``), started or reused for its folder; nothing opens a browser.

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
import threading
import time
import uuid
from typing import Any
from urllib.parse import unquote, urlparse

from cadgen.viewer.scanner import SOURCE_EXTENSIONS, catalog_lists

from .protocol import INVALID_PARAMS, METHOD_NOT_FOUND, Connection, RequestContext, RpcError, claim_stdout
from .roots import WORKSPACE, Root, ThreadWorkspace, filesystem_of, home_filesystem
from .ui import MIME, RESOURCE_META, AppPage
from .views import NoAnswer, ViewRegistry

LOG = logging.getLogger("cadgen.mcp")

NAME = "text_to_cad"
TITLE = "CAD"
# The launch/view protocol between this server and its page. 2: every launch names a root, the
# home's included, and the page reveals files (`cad_reveal`). 3: only the sidebar has a home, and
# a launch browses only the thread's project. 4: a view makes one call a second (`cad_sync`), and
# every launch carries what the page needs to start (the server's version and platform; the
# home's, its recents), so it starts on the launch alone.
PROTOCOL = 4
_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
_RESOURCE_NOT_FOUND = -32002
EXTENSIONS = sorted(SOURCE_EXTENSIONS)

# Clients that present CAD as tabs (see the module docstring); every other client is shown views inline,
# or told where the Viewer has them when it renders no MCP Apps.
_TAB_HOSTS = frozenset({"codex-mcp-client"})
_UI_EXTENSION = "io.modelcontextprotocol/ui"

INSTRUCTIONS = (
    "CAD shows local CAD models (STEP, STL, GLB, 3MF, DXF, URDF, SDF) in a viewer tab beside the chat. "
    "To show a model, call cad_show: it switches an open viewer and never opens a tab. "
    "Only when cad_show reports no open viewer, call cad_open, once. "
    "Viewers refresh when files change, so never reopen after a rebuild. "
    "cad_view reports what the user is looking at and has selected; cad_screenshot returns what they see."
)

INLINE_INSTRUCTIONS = (
    "CAD shows local CAD models (STEP, STL, GLB, 3MF, DXF, URDF, SDF) in interactive viewers in the chat. "
    "Call cad_show to show one: each call adds a viewer and pauses the earlier ones. "
    "Viewers refresh when their files change, so never show a model again after a rebuild. "
    "cad_view reports what the user is looking at and has selected in a viewer, and cad_screenshot returns "
    "what they see; both take the view that cad_show returned."
)

TEXT_INSTRUCTIONS = (
    "CAD opens local CAD models (STEP, STL, GLB, 3MF, DXF, URDF, SDF) in the CAD Viewer in the user's browser: "
    "this app cannot show CAD views itself. Call cad_show with a model to get its link and share it. "
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


_PATH = {"type": "string", "description": "A CAD file: an absolute path, or relative to the thread's workspace."}
_VIEW = {"type": "string", "description": "A view id from cad_view; defaults to the most recently used viewer."}
_ROOT = _object({"kind": {"type": "string", "enum": ["workspace", "global"]}, "path": {"type": "string"}}, ["kind", "path"])
# What a view watches: its root's catalog (with the file it shows hydrated first), and the build
# feed of each STEP it shows.
_WATCH = _object({"root": _ROOT, "file": {"type": ["string", "null"]},
                  "previews": {"type": "array", "items": {"type": "string"}, "maxItems": 4}}, ["root"])
_SHOWN_PATH = {"type": "string", "description": "A CAD file: an absolute path, or relative to the project folder the chat works in."}
_SHOWN_VIEW = {"type": "string", "description": "The view that cad_show returned."}
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}


def _stamped(launch: dict[str, Any]) -> dict[str, Any]:
    """A launch with what the page needs to start on it alone: this server's version and platform."""
    from cadgen import __version__

    launch["version"] = __version__
    launch["platform"] = sys.platform if sys.platform in ("darwin", "win32") else "linux"
    return launch


def _presentation(client: dict[str, Any], offered: dict[str, Any]) -> str:
    """``tabs``, ``inline`` or ``text``: how this client shows views (see the module docstring)."""
    if client.get("name") in _TAB_HOSTS:
        return "tabs"
    forced = str(os.environ.get("CADGEN_MCP_PRESENTATION") or "").strip()
    if forced in ("inline", "text"):
        return forced
    extensions = offered.get("extensions") if isinstance(offered.get("extensions"), dict) else {}
    ui = extensions.get(_UI_EXTENSION)
    return "inline" if isinstance(ui, dict) and MIME in (ui.get("mimeTypes") or []) else "text"


def _file_uri_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.startswith("file:"):
        return None
    path = unquote(urlparse(value).path)
    if os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path or None


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


class Server:
    def __init__(self, *, launch_cwd: str | None, page: AppPage | None = None, recents=None, tunnel=None, viewer_url=None) -> None:
        excluded = tuple(path for path in (os.environ.get("PLUGIN_ROOT"), os.path.expanduser("~")) if path)
        self.workspace = ThreadWorkspace(launch_cwd, excluded=excluded)
        self.page = page or AppPage()
        self.views = ViewRegistry()
        self._recents = recents
        self._tunnel = tunnel
        self._picker = None
        self._model: str | None = None  # what this thread last opened or showed
        self._tools: list[dict[str, Any]] | None = None
        self.tabs = False  # decided at initialize: see the module docstring
        self.text = False
        self._viewer_url = viewer_url
        self._client_roots = False
        self._connection: Connection | None = None
        self._order = itertools.count(1)

    # -- lazily built parts ----------------------------------------------------

    @property
    def recents(self):
        if self._recents is None:
            from cadgen.viewer.recents import RecentStore

            self._recents = RecentStore()
        return self._recents

    @property
    def picker(self):
        if self._picker is None:
            from .picker import FilePicker

            self._picker = FilePicker()
        return self._picker

    @property
    def tunnel(self):
        if self._tunnel is None:
            from .tunnel import ViewerTunnel

            self._tunnel = ViewerTunnel()
        return self._tunnel

    # -- the protocol ----------------------------------------------------------

    def attach(self, connection: Connection) -> None:
        """The connection this server answers on, for the requests it makes of the host."""
        self._connection = connection

    def notified(self, method: str, params: dict[str, Any]) -> None:
        if method in ("notifications/initialized", "notifications/roots/list_changed") and self._client_roots:
            threading.Thread(target=self._refresh_roots, name="cadgen-mcp-roots", daemon=True).start()

    def _refresh_roots(self) -> None:
        """Adopt the folders a client that offers roots says the chat works in."""
        if self._connection is None:
            return
        try:
            result = self._connection.request("roots/list", {}, timeout=10)
        except Exception:  # a host that offers roots and then fails to list them leaves the launch folder
            LOG.info("the host did not list its roots")
            return
        roots = result.get("roots") if isinstance(result, dict) else None
        if isinstance(roots, list):
            self.workspace.adopt([root.get("uri") for root in roots if isinstance(root, dict)])

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
        self._client_roots = isinstance(offered.get("roots"), dict)
        if presentation == "inline":
            self.page = self.page.presenting("inline")
        self._tools = None
        extensions = sorted(offered["extensions"]) if isinstance(offered.get("extensions"), dict) else []
        LOG.info("client %s %s: %s views (extensions: %s)", client.get("name"), client.get("version"), presentation,
                 ", ".join(extensions) or "none")
        capabilities: dict[str, Any] = {"tools": {"listChanged": False}, "resources": {"listChanged": False}}
        if self.tabs:
            # Ask the host to say, on each agent call, which folder the thread works in.
            capabilities["experimental"] = {"codex/sandbox-state-meta": {}}
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
             "inputSchema": _object({"path": _SHOWN_PATH}, ["path"])},
            {"name": "cad_view", "title": "Read CAD view", "icons": [ICON], "annotations": _READ_ONLY,
             "description": ("Describe a CAD viewer in this chat: its model and revision, what the user has selected (as "
                             "references you can quote back), and the camera."),
             "inputSchema": _object({"view": _SHOWN_VIEW}, ["view"])},
            {"name": "cad_screenshot", "title": "Capture CAD view", "icons": [ICON], "annotations": _READ_ONLY,
             "description": "Capture a PNG of exactly what a CAD viewer in this chat shows right now.",
             "inputSchema": _object({"view": _SHOWN_VIEW}, ["view"])},
            *self._page_tools(),
        ]

    def _text_catalog(self) -> list[dict[str, Any]]:
        """No page to open or read: cad_show hands over a link to the model in the CAD Viewer."""
        return [
            {"name": "cad_show", "title": "Show in CAD", "icons": [ICON], "annotations": _READ_ONLY,
             "description": ("Get a link that opens a local CAD model (STEP, STL, GLB, 3MF, DXF, URDF, SDF) in the CAD "
                             "Viewer in the user's browser; this app cannot show CAD views itself. The Viewer refreshes "
                             "when the file changes, so share a model's link once, not after every rebuild."),
             "inputSchema": _object({"path": _SHOWN_PATH}, ["path"])},
        ]

    def _page_tools(self) -> list[dict[str, Any]]:
        """The tools only the page calls."""

        def app(name: str, title: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
            return {"name": name, "title": title, "description": description, "inputSchema": schema,
                    "annotations": _READ_ONLY, "_meta": {"ui": {"visibility": ["app"]}}}

        return [
            app("cad_release", "CAD release", "The newest CAD release, and whether it is newer than this one.", _object()),
            app("cad_launch", "Open model", "The launch for opening a model in this view.",
                _object({"model": {"type": "string"}}, ["model"])),
            app("cad_pick_model", "Open Model", "Choose a model with the desktop's file chooser. Only for an explicit Open Model action.",
                _object()),
            app("cad_sync", "CAD sync", "This view's one call each second: what it shows and watches, and what is waiting for it.",
                _object({"view": {"type": "string"}, "surface": {"type": "string"}, "model": {"type": ["string", "null"]},
                         "focused": {"type": "boolean"}, "closed": {"type": "boolean"}, "state": {"type": "object"},
                         "watch": _WATCH}, ["view", "surface"])),
            app("cad_capture_reply", "Answer CAD", "Answer the server's request for a capture.",
                _object({"requestId": {"type": "string"}, "png": {"type": "string"}, "error": {"type": "string"}}, ["requestId"])),
            app("cad_http", "CAD viewer request", "One request to the CAD viewer's routes, bodies base64.",
                _object({"root": _ROOT, "method": {"type": "string"}, "url": {"type": "string"},
                         "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                         "body": {"type": "string"}}, ["root", "method", "url"])),
            app("cad_recents", "CAD recents", "Read or change recently opened models.",
                _object({"action": {"type": "string", "enum": ["list", "pin", "unpin", "remove", "thumbnail", "thumbnails"]},
                         "path": {"type": "string"}, "png": {"type": "string"},
                         "names": {"type": "array", "items": {"type": "string"}}})),
            app("cad_reveal", "Reveal in file manager",
                "Show a file of the view's root in the desktop's file manager. Only for an explicit Reveal action.",
                _object({"root": _ROOT, "path": {"type": "string"}}, ["root", "path"])),
        ]

    # -- calls -----------------------------------------------------------------

    def _call(self, params: dict[str, Any], context: RequestContext) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise RpcError(INVALID_PARAMS, "arguments must be an object")
        handler = getattr(self, f"_tool_{name}", None) if isinstance(name, str) and name.startswith("cad_") else None
        if handler is None:
            raise RpcError(INVALID_PARAMS, f"unknown tool {name!r}")
        self.workspace.learn(context.meta)
        started = time.monotonic()
        try:
            return handler(arguments, context)
        except ToolFailed as failure:
            return _text(str(failure), error=True)
        finally:
            if name not in ("cad_sync", "cad_http"):
                LOG.info("%s %.0fms", name, (time.monotonic() - started) * 1000)

    # launches -----------------------------------------------------------------

    def _project_of(self, model: str) -> str | None:
        """The workspace folder whose catalog lists ``model``, if any.

        A model the agent writes under ``build/`` or a hidden folder is still the thread's, but the
        workspace's catalog never shows it, so it has no project around it to browse.
        """
        folder = self.workspace.contains(model)
        return folder if folder and catalog_lists(folder, model) else None

    def _root_for(self, model: str) -> Root:
        project = self._project_of(model)
        return Root("workspace", project) if project else filesystem_of(model)

    def _home_root(self) -> Root:
        """Where a view with no model sits: the thread's workspace, else the filesystem of the user's home."""
        return self.workspace.root() or home_filesystem()

    def _launch(self, model: str | None, *, surface: str | None = None, explore: bool = True) -> dict[str, Any]:
        root = self._root_for(model) if model is not None else self._home_root()
        # Only a project is browsed: the thread's workspace. A model with no project around it is
        # shown on its own, and an inline view is a card in the chat, which browses nothing.
        launch: dict[str, Any] = {"protocol": PROTOCOL, "page": "viewer", "model": model, "root": root.public(),
                                  "explore": explore and self.tabs and root.kind == WORKSPACE}
        if surface:
            launch["surface"] = surface
        if model is not None:
            self._model = model
            self._remember(model)
        return _stamped(launch)

    def _mounted(self, launch: dict[str, Any]) -> dict[str, Any]:
        """Stamp a launch that mounts a new inline view: its token, and its place among the views."""
        seq = next(self._order)
        launch["view"] = f"cad-{seq}-{uuid.uuid4().hex[:10]}"
        # Wall-clock time orders views across restarts of this process; seq breaks a tie.
        launch["order"] = {"createdAt": int(time.time() * 1000), "seq": seq}
        return launch

    def _remember(self, model: str) -> None:
        try:
            self.recents.opened(model)
        except Exception:  # opening never depends on the store
            LOG.exception("could not record %s in recents", model)

    def _model_path(self, value: Any) -> str:
        """An existing CAD file, absolute, from what a caller named."""
        if not isinstance(value, str) or not value.strip():
            raise ToolFailed("Name a CAD file by its path.")
        path = _file_uri_path(value) or os.path.expanduser(value.strip())
        if not os.path.isabs(path):
            base = self.workspace.primary
            if base is None:
                raise ToolFailed(f"{value} is relative, and this thread has no workspace folder; give an absolute path.")
            path = os.path.join(base, path)
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            raise ToolFailed(f"No file at {path}.")
        if os.path.splitext(path)[1].lower() not in SOURCE_EXTENSIONS:
            raise ToolFailed(f"CAD opens {', '.join(EXTENSIONS)} files; {os.path.basename(path)} is not one.")
        return path

    def _tool_cad_home(self, arguments, context):
        # The sidebar's home: the library, and Open with the desktop's chooser. It browses no folder,
        # so its root is the filesystem, whose catalog holds nothing until a model is shown. The
        # library comes with it, so the home draws its cards without asking first.
        try:
            recents = [entry.public() for entry in self.recents.list()]
        except Exception:  # the home opens whatever the store says
            LOG.exception("could not read recents")
            recents = []
        return _text("CAD is open.", {"launch": _stamped({"protocol": PROTOCOL, "page": "home", "surface": "sidebar",
                                                           "model": None, "root": home_filesystem().public(), "explore": False,
                                                           "recents": recents})})

    def _tool_cad_tab(self, arguments, context):
        current = next((view.model for view in self.views.live(context.meta.get("threadId")) if view.model), None) or self._model
        if current is not None and not os.path.isfile(current):
            current = None
        return _text("CAD is open.", {"launch": self._launch(current, surface="tab")})

    def _tool_cad_file(self, arguments, context):
        resource = context.meta.get("openai/resource")
        path = resource.get("path") if isinstance(resource, dict) else None
        if not path:
            file = arguments.get("file")
            path = _file_uri_path(file.get("resourceUri")) if isinstance(file, dict) else None
        model = self._model_path(path)
        launch = self._launch(model, surface="file", explore=False)
        # Shown on its own: the one file, read without the catalog of any folder.
        launch["root"] = filesystem_of(model).public()
        return _text(f"{os.path.basename(model)} is open in CAD.", {"launch": launch})

    def _tool_cad_open(self, arguments, context):
        model = self._model_path(arguments.get("path"))
        launch = self._launch(model, surface="agent")
        return _text(f"{model} is open in a new CAD tab. From now on, use cad_show to show models in it.", {"launch": launch})

    def _tool_cad_launch(self, arguments, context):
        return _data({"launch": self._launch(self._model_path(arguments.get("model")))})

    def _tool_cad_pick_model(self, arguments, context):
        from .picker import PickerFailed

        try:
            chosen = self.picker.choose()
        except PickerFailed as failure:
            raise ToolFailed(str(failure)) from failure
        if chosen is None:
            return _data({"cancelled": True})
        return _data({"launch": self._launch(self._model_path(chosen))})

    def _tool_cad_release(self, arguments, context):
        # The update button's: GitHub's latest release, asked at most every few hours and shared
        # through the state directory. The one request to the network this server makes.
        from cadgen import __version__
        from cadgen.viewer.recents import state_dir

        from .releases import latest_release

        return _data({"latest": latest_release(__version__, cache=state_dir() / "release.json")})

    # the agent's tools ----------------------------------------------------------

    def _target(self, context: RequestContext, view_id: Any, *, needs_model: bool) -> Any:
        views = [view for view in self.views.live(context.meta.get("threadId")) if view.surface != "file" or view.id == view_id]
        if view_id:
            views = [view for view in views if view.id == view_id]
        if needs_model:
            views = [view for view in views if view.model]
        return views[0] if views else None

    def _tool_cad_show(self, arguments, context):
        if self.text:
            return self._show_in_browser(self._model_path(arguments.get("path")))
        if not self.tabs:
            launch = self._mounted(self._launch(self._model_path(arguments.get("path")), surface="inline"))
            return _text(f"Showing {launch['model']} in CAD (view {launch['view']}).", {"launch": launch})
        model = self._model_path(arguments.get("path"))
        view = self._target(context, arguments.get("view"), needs_model=False)
        if view is None:
            self._model = model
            return _text("No CAD viewer is open in this thread. Call cad_open to open one.", {"delivered": 0})
        launch = self._launch(model)
        self.views.post([view.id], {"type": "show", "launch": launch})
        return _text(f"Showing {model} in CAD.", {"delivered": 1, "view": view.id})

    def _show_in_browser(self, model: str) -> dict[str, Any]:
        """The model's link in the CAD Viewer serving its folder, started if none is."""
        from urllib.parse import quote

        from .browser import ViewerUnavailable, model_link, viewer_url

        # The Viewer serves one folder and walks all of it: the project, else the model's own folder.
        folder = self._project_of(model) or os.path.dirname(model)
        self._model = model
        self._remember(model)
        try:
            url = (self._viewer_url or viewer_url)(folder)
        except ViewerUnavailable as failure:
            relative = quote(os.path.relpath(model, folder).replace(os.sep, "/"), safe="/")
            raise ToolFailed(f"This app cannot show CAD views, and the CAD Viewer did not start ({failure}). Run "
                             f"`cd \"{folder}\" && cadgen viewer --host 127.0.0.1 --json --detach` and open the url it prints "
                             f"with ?file={relative} added.") from failure
        link = model_link(url, folder, model)
        return _text(f"This app cannot show CAD views, so {os.path.basename(model)} is in the CAD Viewer: {link}\n"
                     "The Viewer refreshes when the file changes: share this link once, not after every rebuild.",
                     {"url": link, "model": model})

    def _shown(self, view_id: Any) -> Any:
        """The inline view the agent names by the token its cad_show returned."""
        if not isinstance(view_id, str) or not view_id:
            raise ToolFailed("Name the viewer: pass the view that cad_show returned.")
        view = next((view for view in self.views.live() if view.id == view_id), None)
        if view is None:
            raise ToolFailed("That viewer is not open: it was closed, or a newer one took its place. Show the model again with cad_show.")
        return view

    def _tool_cad_view(self, arguments, context):
        live = [self._shown(arguments.get("view"))] if not self.tabs else self.views.live(context.meta.get("threadId"))
        if not live:
            return _text("No CAD viewer is open in this thread.", {"views": []})
        # What each view last said it shows: a view sends its state whenever it changes, on the
        # sync it makes each second, so this answers at once without asking any of them.
        views = [{"view": view.id, "surface": view.surface, "model": view.model, **view.state} for view in live]
        return _text(json.dumps({"views": views}, indent=1), {"views": views})

    def _tool_cad_screenshot(self, arguments, context):
        view = self._target(context, arguments.get("view"), needs_model=True) if self.tabs else self._shown(arguments.get("view"))
        if view is not None and not view.model:
            raise ToolFailed("That viewer shows no model yet.")
        if view is None:
            raise ToolFailed("No CAD viewer with a model is open in this thread. Open one with cad_open, "
                             "or render headless with `cadgen snapshot`.")
        try:
            reply = self.views.ask(view.id, "capture")
        except NoAnswer as failure:
            raise ToolFailed(f"The CAD viewer could not capture: {failure}") from failure
        png = reply.get("png")
        if not isinstance(png, str) or not png:
            raise ToolFailed("The CAD viewer answered without an image.")
        return {"content": [{"type": "image", "data": png, "mimeType": "image/png"},
                            {"type": "text", "text": f"{view.model} as shown in CAD."}],
                "structuredContent": {"view": view.id, "model": view.model}}

    # the page's tools -----------------------------------------------------------

    def _register(self, arguments: dict[str, Any], context: RequestContext) -> str:
        view_id, surface = arguments.get("view"), arguments.get("surface")
        if not isinstance(view_id, str) or not view_id or not isinstance(surface, str):
            raise RpcError(INVALID_PARAMS, "view and surface are required")
        self.views.register(view_id, surface=surface, thread_id=context.meta.get("threadId"), model=arguments.get("model"))
        return view_id

    def _tool_cad_sync(self, arguments, context):
        """A view's one call each second: it reports, the server answers with what waits.

        Up: the view's model, its state when it changed (what ``cad_view`` reads), ``focused``
        when a person just touched it, and ``closed`` once a newer view took its place. Down: the
        agent's requests for it (``show``, ``capture``), and for what it watches -- its root's
        catalog and the build feed of any STEP it shows -- the catalog's revision (the view
        reads the catalog again only when that moves) and each feed's current status.
        """
        view_id = self._register(arguments, context)
        if arguments.get("closed") is True:  # a view a newer one replaced: the agent can no longer reach it
            self.views.forget(view_id)
            return _data({"events": []})
        state = arguments.get("state") if isinstance(arguments.get("state"), dict) else None
        focused = arguments.get("focused") is True
        if state is not None or focused:
            self.views.report(view_id, model=arguments.get("model"), state=state, focused=focused)
        if focused and isinstance(arguments.get("model"), str):
            self._model = arguments["model"]
        answer: dict[str, Any] = {}
        watch = arguments.get("watch")
        if isinstance(watch, dict) and isinstance(watch.get("root"), dict):
            # What the view watches never costs it the agent's requests: a root refused or a
            # catalog that will not read is said here, and the events still go.
            try:
                root = self.workspace.accept(watch["root"])
                file = watch.get("file") if isinstance(watch.get("file"), str) else None
                answer["catalog"] = {"revision": self.tunnel.catalog_revision(root, file)}
            except Exception as error:  # noqa: BLE001 - the view shows the catalog's own failure on its next read
                answer["catalog"] = {"error": str(error) or type(error).__name__}
            else:
                files = [item for item in watch.get("previews") or [] if isinstance(item, str)][:4]
                if files:
                    answer["previews"] = [{"file": item, **self.tunnel.preview(root, item)} for item in files]
        # Last, so a sync that failed before this point has taken nothing from the queue.
        answer["events"] = self.views.poll(view_id)
        return _data(answer)

    def _tool_cad_capture_reply(self, arguments, context):
        reply: dict[str, Any] = {key: arguments[key] for key in ("png", "error") if isinstance(arguments.get(key), str)}
        return _data({"accepted": self.views.reply(str(arguments.get("requestId")), reply)})

    def _tool_cad_http(self, arguments, context):
        root = arguments.get("root")
        if not isinstance(root, dict):
            raise ToolFailed("a request needs the root it browses")
        try:
            accepted = self.workspace.accept(root)
            body = base64.b64decode(arguments.get("body") or "", validate=True)
        except (ValueError, binascii.Error) as error:
            raise ToolFailed(str(error)) from error
        headers = arguments.get("headers") if isinstance(arguments.get("headers"), dict) else {}
        return _data(self.tunnel.serve(accepted, method=str(arguments.get("method") or "GET"),
                                       url=str(arguments.get("url") or ""), headers=headers, body=body))

    def _tool_cad_reveal(self, arguments, context):
        """Reveal a file of a root this thread may browse, exactly as the CAD Viewer reveals one (``cadgen.viewer.reveal``)."""
        import subprocess

        from cadgen.viewer.backend import ForbiddenAssetError
        from cadgen.viewer.reveal import reveal_path

        root = arguments.get("root")
        if not isinstance(root, dict):
            raise ToolFailed("a reveal needs the root the file is under")
        try:
            reveal_path(self.workspace.accept(root).path, arguments.get("path"))
        except ForbiddenAssetError as error:
            raise ToolFailed("That file is not under this view's folder.") from error
        except FileNotFoundError as error:
            raise ToolFailed("That file is no longer there.") from error
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            raise ToolFailed(f"The file manager could not show that file: {error}") from error
        return _data({})

    def _tool_cad_recents(self, arguments, context):
        action = arguments.get("action") or "list"
        path = arguments.get("path")
        store = self.recents
        if action == "thumbnails":
            names = [name for name in arguments.get("names") or [] if isinstance(name, str)][:64]
            found = {name: store.read_thumbnail(name) for name in names}
            return _data({"thumbnails": {name: base64.b64encode(png).decode("ascii") for name, png in found.items() if png}})
        if action != "list":
            if not isinstance(path, str) or not os.path.isabs(path):
                raise ToolFailed("name the recent model by its absolute path")
            if action in ("pin", "unpin"):
                store.pin(path, action == "pin")
            elif action == "remove":
                store.remove(path)
            elif action == "thumbnail":
                from cadgen.viewer.recents import thumbnail_png

                try:
                    store.thumbnail(path, thumbnail_png(arguments.get("png")))
                except ValueError as error:
                    raise ToolFailed(str(error)) from error
            else:
                raise ToolFailed(f"unknown action {action!r}")
        return _data({"recents": [entry.public() for entry in store.list()]})


def serve(argv: list[str] | None = None) -> int:
    """Serve MCP on this process's standard streams until the host closes them."""
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="cadgen mcp: %(message)s")
    protocol_out = claim_stdout()
    try:
        launch_cwd = os.getcwd()
    except OSError:
        launch_cwd = None
    server = Server(launch_cwd=launch_cwd)
    connection = Connection(sys.stdin.buffer, protocol_out, server.handle, on_notification=server.notified, workers=64)
    server.attach(connection)
    connection.serve()
    return 0
