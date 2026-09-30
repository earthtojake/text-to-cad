"""``cadgen mcp``: CAD beside an agent's chat, as an MCP App.

The host starts one of these processes per thread (and briefly, many more that
only list tools), so everything a thread's views share -- its workspace, its
open views, what it last showed -- is plain process memory, and nothing heavy
happens until a tool needs it: initialize and tools/list read no store, start no
daemon and import no CAD kernel.

One page serves every surface. The tool that opens a surface returns a
*launch* -- which page, which model, which root to browse -- and the page renders
it; nothing in the page guesses where it is. Once open, a view long-polls
``cad_events`` so the agent can drive it (``cad_show``) without opening tabs,
and reaches the viewer's own HTTP routes through ``cad_http``.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import json
import logging
import os
import sys
import threading
import time
from typing import Any
from urllib.parse import unquote, urlparse

from cadgen.viewer.scanner import SOURCE_EXTENSIONS

from .protocol import INVALID_PARAMS, METHOD_NOT_FOUND, Connection, RequestContext, RpcError, claim_stdout
from .roots import Root, ThreadWorkspace, folder_of, listed_under
from .ui import MIME, RESOURCE_META, AppPage
from .views import POLL_SECONDS, NoAnswer, ViewRegistry

LOG = logging.getLogger("cadgen.mcp")

NAME = "text_to_cad"
TITLE = "CAD"
# The launch/view protocol between this server and its page.
PROTOCOL = 1
_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
_RESOURCE_NOT_FOUND = -32002
EXTENSIONS = sorted(SOURCE_EXTENSIONS)
_MAX_THUMBNAIL_BYTES = 512 * 1024
_DESCRIBE_SECONDS = 2.0

INSTRUCTIONS = (
    "CAD shows local CAD models (STEP, STL, GLB, 3MF, DXF, URDF, SDF) in a viewer tab beside the chat. "
    "To show a model, call cad_show: it switches an open viewer and never opens a tab. "
    "Only when cad_show reports no open viewer, call cad_open, once. "
    "Viewers refresh when files change, so never reopen after a rebuild. "
    "cad_view reports what the user is looking at and has selected; cad_screenshot returns what they see."
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
_ROOT = _object({"kind": {"type": "string", "enum": ["workspace", "folder"]}, "path": {"type": "string"}}, ["kind", "path"])
_READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}


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
    def __init__(self, *, launch_cwd: str | None, page: AppPage | None = None, recents=None, tunnel=None) -> None:
        excluded = tuple(path for path in (os.environ.get("PLUGIN_ROOT"), os.path.expanduser("~")) if path)
        self.workspace = ThreadWorkspace(launch_cwd, excluded=excluded)
        self.page = page or AppPage()
        self.views = ViewRegistry()
        self._recents = recents
        self._tunnel = tunnel
        self._picker = None
        self._model: str | None = None  # what this thread last opened or showed
        self._tools: list[dict[str, Any]] | None = None

    # -- lazily built parts ----------------------------------------------------

    @property
    def recents(self):
        if self._recents is None:
            from .recents import RecentStore

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

        requested = params.get("protocolVersion")
        return {
            "protocolVersion": requested if requested in _PROTOCOL_VERSIONS else _PROTOCOL_VERSIONS[1],
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False},
                # Ask the host to say, on each agent call, which folder the thread works in.
                "experimental": {"codex/sandbox-state-meta": {}},
            },
            "serverInfo": {"name": NAME, "title": TITLE, "version": __version__, "icons": [ICON]},
            "instructions": INSTRUCTIONS,
        }

    # -- the catalog -----------------------------------------------------------

    def tools(self) -> list[dict[str, Any]]:
        if self._tools is None:
            self._tools = self._catalog()
        return self._tools

    def _catalog(self) -> list[dict[str, Any]]:
        uri = self.page.uri

        def surface(entrypoint: dict[str, Any] | None = None, **ui: Any) -> dict[str, Any]:
            meta: dict[str, Any] = {"ui": {"resourceUri": uri, "visibility": ["app"]}, "openai/iconStyle": "monochrome"}
            if entrypoint is not None:
                meta["openai/ui"] = {"entrypoints": [entrypoint], **ui}
            return meta

        def app(name: str, title: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
            return {"name": name, "title": title, "description": description, "inputSchema": schema,
                    "annotations": _READ_ONLY, "_meta": {"ui": {"visibility": ["app"]}}}

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
            app("cad_session", "CAD session", "The server's build, protocol and this thread's workspace.", _object()),
            app("cad_launch", "Open model", "The launch for opening a model in this view.",
                _object({"model": {"type": "string"}}, ["model"])),
            app("cad_pick_model", "Open Model", "Choose a model with the desktop's file chooser. Only for an explicit Open Model action.",
                _object()),
            app("cad_events", "CAD events", "Long-poll for this view's events.",
                _object({"view": {"type": "string"}, "surface": {"type": "string"}, "model": {"type": ["string", "null"]}},
                        ["view", "surface"])),
            app("cad_view_report", "Report CAD view", "Tell the server what this view shows.",
                _object({"view": {"type": "string"}, "surface": {"type": "string"}, "model": {"type": ["string", "null"]},
                         "state": {"type": "object"}, "focused": {"type": "boolean"}}, ["view", "surface"])),
            app("cad_capture_reply", "Answer CAD", "Answer the server's question: a capture or a description.",
                _object({"requestId": {"type": "string"}, "png": {"type": "string"}, "error": {"type": "string"},
                         "state": {"type": "object"}}, ["requestId"])),
            app("cad_http", "CAD viewer request", "One request to the CAD viewer's routes, bodies base64.",
                _object({"root": _ROOT, "method": {"type": "string"}, "url": {"type": "string"},
                         "headers": {"type": "object", "additionalProperties": {"type": "string"}},
                         "body": {"type": "string"}}, ["root", "method", "url"])),
            app("cad_recents", "CAD recents", "Read or change recently opened models.",
                _object({"action": {"type": "string", "enum": ["list", "pin", "unpin", "remove", "thumbnail", "thumbnails"]},
                         "path": {"type": "string"}, "png": {"type": "string"},
                         "names": {"type": "array", "items": {"type": "string"}}})),
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
            if name not in ("cad_events", "cad_http"):
                LOG.info("%s %.0fms", name, (time.monotonic() - started) * 1000)

    # launches -----------------------------------------------------------------

    def _root_for(self, model: str) -> Root:
        folder = self.workspace.contains(model)
        return Root("workspace", folder) if folder and listed_under(folder, model) else folder_of(model)

    def _launch(self, model: str | None, *, surface: str | None = None, explore: bool = True) -> dict[str, Any]:
        launch: dict[str, Any] = {"protocol": PROTOCOL, "page": "viewer", "model": model, "explore": explore}
        if surface:
            launch["surface"] = surface
        if model is not None:
            launch["root"] = self._root_for(model).public()
            self._model = model
            self._remember(model)
        else:
            root = self.workspace.root()
            launch["root"] = root.public() if root else None
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
        return _text("CAD is open.", {"launch": {"protocol": PROTOCOL, "page": "home", "surface": "sidebar",
                                                  "model": None, "root": None, "explore": False}})

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
        launch["root"] = folder_of(model).public()
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
            chosen = self.picker.choose(EXTENSIONS)
        except PickerFailed as failure:
            raise ToolFailed(str(failure)) from failure
        if chosen is None:
            return _data({"cancelled": True})
        return _data({"launch": self._launch(self._model_path(chosen))})

    def _tool_cad_session(self, arguments, context):
        from cadgen import __version__

        return _data({"protocol": PROTOCOL, "build": self.page.build, "version": __version__, "platform": sys.platform,
                      "workspace": [Root("workspace", path).public() for path in self.workspace.paths]})

    # the agent's tools ----------------------------------------------------------

    def _target(self, context: RequestContext, view_id: Any, *, needs_model: bool) -> Any:
        views = [view for view in self.views.live(context.meta.get("threadId")) if view.surface != "file" or view.id == view_id]
        if view_id:
            views = [view for view in views if view.id == view_id]
        if needs_model:
            views = [view for view in views if view.model]
        return views[0] if views else None

    def _tool_cad_show(self, arguments, context):
        model = self._model_path(arguments.get("path"))
        view = self._target(context, arguments.get("view"), needs_model=False)
        if view is None:
            self._model = model
            return _text("No CAD viewer is open in this thread. Call cad_open to open one.", {"delivered": 0})
        launch = self._launch(model)
        self.views.post([view.id], {"type": "show", "launch": launch})
        return _text(f"Showing {model} in CAD.", {"delivered": 1, "view": view.id})

    def _tool_cad_view(self, arguments, context):
        live = self.views.live(context.meta.get("threadId"))
        if not live:
            return _text("No CAD viewer is open in this thread.", {"views": []})
        answers: dict[str, dict[str, Any]] = {}

        def describe(view) -> None:
            with contextlib.suppress(NoAnswer):
                state = self.views.ask(view.id, "describe", timeout=_DESCRIBE_SECONDS).get("state")
                if isinstance(state, dict):
                    answers[view.id] = state

        askers = [threading.Thread(target=describe, args=(view,), daemon=True) for view in live]
        for asker in askers:
            asker.start()
        for asker in askers:
            asker.join(_DESCRIBE_SECONDS + 0.5)
        # A view that did not answer is described by what it last reported.
        views = [{"view": view.id, "surface": view.surface, **(answers.get(view.id) or {"model": view.model, **view.state})} for view in live]
        return _text(json.dumps({"views": views}, indent=1), {"views": views})

    def _tool_cad_screenshot(self, arguments, context):
        view = self._target(context, arguments.get("view"), needs_model=True)
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

    def _tool_cad_events(self, arguments, context):
        view_id = self._register(arguments, context)
        events = self.views.poll(view_id, timeout=POLL_SECONDS, cancelled=lambda: context.cancelled or context.connection.closed)
        return _data({"events": events})

    def _tool_cad_view_report(self, arguments, context):
        view_id = self._register(arguments, context)
        state = arguments.get("state") if isinstance(arguments.get("state"), dict) else {}
        focused = bool(arguments.get("focused"))
        self.views.report(view_id, model=arguments.get("model"), state=state, focused=focused)
        if focused and isinstance(arguments.get("model"), str):
            self._model = arguments["model"]
        return _data({})

    def _tool_cad_capture_reply(self, arguments, context):
        reply: dict[str, Any] = {key: arguments[key] for key in ("png", "error") if isinstance(arguments.get(key), str)}
        if isinstance(arguments.get("state"), dict):
            reply["state"] = arguments["state"]
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
                try:
                    png = base64.b64decode(arguments.get("png") or "", validate=True)
                except (ValueError, binascii.Error) as error:
                    raise ToolFailed("the thumbnail is not base64") from error
                if not png.startswith(b"\x89PNG") or len(png) > _MAX_THUMBNAIL_BYTES:
                    raise ToolFailed("a thumbnail is a PNG of at most 512 KiB")
                store.thumbnail(path, png)
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
    Connection(sys.stdin.buffer, protocol_out, server.handle, workers=64).serve()
    return 0
