"""The HTTP contract: both browser gates, the API's routes (``/api/v1``, ``kinds.py``), and the SPA.

The engine authenticates network requests before this router runs. MCP calls
reach the same router in process through an authenticated session. Two additional
browser gates defend against cross-origin requests:

* Host validation refuses a request whose Host names anything but
  127.0.0.1/localhost/::1 — the DNS-rebinding case, where an attacker domain
  re-resolves to loopback and the browser treats us as same-origin. Skipped when
  bound non-loopback, matching Jupyter's ``allow_remote_access``.
* Every request that changes something -- a POST, PUT, PATCH or DELETE (``CHANGING_METHODS``:
  the model library, a person's settings, a prompt's files) -- requires an ``x-cadgen-viewer``
  header. A cross-origin POST whose params ride the query string is otherwise a no-preflight
  "simple request"; a custom header forces a preflight instead.

No ``Access-Control-*`` headers are served here, deliberately: their absence is what
makes the same-origin policy block cross-origin reads and what makes that
preflight fail. Do not add them. The engine in front of this router makes one
exception, outside it: a CAD card's request that carries a day link in its
``Authorization`` header, and that request's preflight, are answered with the
card's own origin and no credentials (``engine_app.EngineApp.preflight``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
from pathlib import Path

from cad.engine.ids import canonical, file_id, is_id

from .backend import absolute_path, asset_path
from .content_types import content_type_for_path, content_type_for_static_asset, extension_of
from .encoding import UriError, strict_decode_uri_component
from .scanner import CAD_CATALOG_SCHEMA_VERSION, VIEWER_EXTENSIONS, catalog_entry, node_basename, to_posix_path
from .documents import EngineDocuments
from .kinds import API, ENGINE_KINDS, EXPORTS, KINDS, ROBOT_KINDS, document_api, file_kind

__all__ = [
    "ApiError",
    "CadApp",
    "POST_GUARD_HEADER",
    "hostname_only",
    "host_is_allowed",
    "read_viewer_version",
    "identity_token",
    "os_user",
    "create_cad_app",
]

import threading

_EXPORTS_LOCK = threading.Lock()

POST_GUARD_HEADER = "x-cadgen-viewer"
# A thumbnail travels as base64 in the change's JSON: 512 KiB of PNG, and room for the rest.
_LIBRARY_BODY_LIMIT = 768 * 1024
# A thumbnail's name is its content's (``recents.RecentStore.thumbnail``): nothing else is read.
_THUMBNAIL_NAME = re.compile(r"[0-9a-f]{32}\.png")
_CAD_EXTENSIONS = ", ".join(sorted(VIEWER_EXTENSIONS))
_LOOPBACK_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})

def hostname_only(host_header) -> str:
    value = str(host_header or "").strip()
    if value.startswith("["):
        end = value.find("]")
        return (value[1:end] if end != -1 else value).lower()
    index = value.rfind(":")
    if index != -1 and _is_ascii_digits(value[index + 1 :]):
        return value[:index].lower()
    return value.lower()


def host_is_allowed(host_header, bound_host) -> bool:
    """DNS-rebinding defense.

    The NAME is compared, never the port: the attack requires a non-local name,
    and ignoring the port keeps odd-port instances and the dev proxy working.
    Skipped when the operator bound a non-loopback interface — they have
    deliberately left the loopback trust model. An absent Host header is
    allowed: HTTP/1.0 clients omit it, and the browser (the threat this exists
    for) always sends it.
    """
    if hostname_only(bound_host) not in _LOOPBACK_NAMES:
        return True
    if not str(host_header or "").strip():
        return True
    return hostname_only(host_header) in _LOOPBACK_NAMES


def read_viewer_version() -> str:
    """The installed server distribution's version, ``""`` when there is no metadata.

    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return str(version("cad-server") or "")
    except PackageNotFoundError:
        return ""
    except Exception:  # noqa: BLE001 - a metadata read that fails tells us nothing
        return ""


def _identity_files(base_dir, suffix: str) -> tuple[str, list[str]]:
    base = os.path.realpath(os.fspath(base_dir))
    files = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(name for name in dirnames if name != "__pycache__")
        for filename in filenames:
            if not suffix or filename.endswith(suffix):
                files.append(os.path.join(dirpath, filename))
    return base, sorted(files)


def _update_identity_digest(digest, base_dir, *, suffix: str = "") -> None:
    """Add one runtime tree's path, names and bytes to ``digest``."""
    base, files = _identity_files(base_dir, suffix)
    digest.update(os.fsencode(base))
    digest.update(b"\0")
    for file_path in files:
        digest.update(os.fsencode(os.path.relpath(file_path, base)))
        digest.update(b"\0")
        try:
            with open(file_path, "rb") as handle:
                while chunk := handle.read(64 * 1024):
                    digest.update(chunk)
        except OSError as error:
            # A tree changing under the walk must not accidentally match a
            # resident. The next stable launch computes the stable identity.
            digest.update(f"!{type(error).__name__}:{error.errno}".encode("ascii"))
        digest.update(b"\0")


def identity_token(dist_dir: str) -> str:
    """Identity of the Python runtime and exact built client this server uses.

    Computed once per page session. It lets a page notice a changed backend
    or built client; it does not select, replace or restart a process.
    """
    package_dir = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    _update_identity_digest(digest, package_dir, suffix=".py")
    collation = package_dir / "viewer" / "collation.json"
    if collation.is_file():
        _update_identity_digest(digest, collation.parent, suffix=".json")
    if dist_dir:
        _update_identity_digest(digest, dist_dir)
    else:
        digest.update(b"no-client\0")
    return f"{read_viewer_version()}:{digest.hexdigest()}"


def os_user():
    """This process's OS user, as ``/api/v1/server`` names it (``user``): the uid on POSIX, the
    account name on Windows."""
    if hasattr(os, "getuid"):
        return os.getuid()
    import getpass

    return getpass.getuser()


def _is_ascii_digits(value: str) -> bool:
    """JS ``/^\\d+$/``: ASCII only.

    ``str.isdigit()`` is Unicode-aware and would treat ``[::1]:٢`` as a port.
    """
    return bool(value) and value.isascii() and value.isdigit()


def catalog_revision(entries) -> str:
    """A digest of a catalog's entries: it moves whenever anything a client would see in them does."""
    return hashlib.sha256(json.dumps(entries, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:24]


# A project's files are served as data, never as pages. Opened straight in the browser, one is a
# sandboxed document that runs no script and has an origin of its own -- a robot description's XML
# can carry an XHTML <script>, which would otherwise run as the viewer, its routes and their guard
# header in reach -- and ``nosniff`` keeps a browser from reading it as anything but its type. The
# viewer's renderers fetch these bytes, and neither header applies to a fetch.
RAW_FILE_HEADERS = (("x-content-type-options", "nosniff"), ("content-security-policy", "default-src 'none'; sandbox"))
# Every page the server answers may be framed by its own origin alone.
PAGE_HEADERS = (("content-security-policy", "frame-ancestors 'self'"),)


def _working_folder() -> str:
    """The folder this process runs in, or the home folder once that one has been deleted."""
    try:
        return os.getcwd()
    except OSError:
        return os.path.expanduser("~")


# The methods that change something: each must carry the guard header (``POST_GUARD_HEADER``).
CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# What to do, said with an error of each status the routes' funnel answers.
_ROUTES_HINT = "the engine's routes are under /api/v1; GET /api/v1/server says what this engine reads"
_FUNNEL_HINTS = {400: "fix the request as the error says", 404: "check the path or id", 413: "send less",
                 500: "this is a bug in the CAD server: report it with the error"}
# A part's elements, as their routes name them and as the engine's reads do.
_ELEMENTS = {"faces": "face", "edges": "edge", "vertices": "vertex"}
_ENGINE_ROUTES = ("structure, parts/<key> (/faces|edges|vertices/<ordinal>, /groups, /volume), measure, "
                  "kinematics, POST pose, POST mesh")
_KIND_ROUTES = {"model": _ENGINE_ROUTES, "xbf": _ENGINE_ROUTES + ", source", "step": _ENGINE_ROUTES + ", source",
                "dxf": "drawing, source", "urdf": "structure, parts/<digest>, source",
                "srdf": "structure, parts/<digest>, source", "sdf": "structure, parts/<digest>, source",
                "stl": "source", "glb": "source", "3mf": "source"}
# This start of the engine: a page that sees another one (``GET /api/v1/server``'s ``instance``) is
# served by an engine that restarted since it loaded. One per process, the engine's.
INSTANCE = secrets.token_hex(8)


def send_json(response, status: int, payload, headers=()) -> None:
    """``payload`` as the JSON answer of ``status``, with ``headers`` beside it."""
    headers = tuple(headers)
    if not headers:
        return response.send_json(status, payload)
    response.send_bytes(status, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                        "application/json; charset=utf-8", headers)


class ApiError(Exception):
    """An API request refused: its status, what is wrong (``error``) and what to do (``hint``), the
    answer every route gives (``{"error", "hint"}``, and any ``extra`` keys)."""

    def __init__(self, status: int, error: str, hint: str, headers=(), **extra) -> None:
        super().__init__(error)
        self.status, self.error, self.hint, self.headers, self.extra = status, error, hint, tuple(headers), extra

    @classmethod
    def method(cls, method: str, path: str, allowed) -> "ApiError":
        """The 405 of a route ``method`` does not reach, naming the methods it takes."""
        allowed = tuple(allowed)
        named = ", ".join((*allowed, "HEAD") if "GET" in allowed else allowed)
        return cls(405, f"{method} is not allowed on {path}", f"use {' or '.join(allowed)}", [("allow", named)])

    def send(self, response) -> None:
        send_json(response, self.status, {"error": self.error, "hint": self.hint, **self.extra}, self.headers)


class CadApp:
    """``handle(request, response)`` writes exactly one response.

    Unlike the Node app there is no "not mine" return: the Python server always
    serves the client itself, and the dev proxy forwards only the API (``/api``), so
    nothing else can be waiting behind this.

    One app serves every file on this machine, by absolute path (``backend``). The page names
    each document it shows by id, ``/<id>`` (``cad.engine.ids``): a model's, or a file's once it
    is registered here (``remember``: by the launcher, or by the catalog's answer for its path).
    ``start`` is the folder of the most recent launch (the working folder by default): what its
    relative files were read from; the explorer never opens there, and it bounds nothing.
    """

    def __init__(self, *, host: str, port: int, dist_dir: str = "", start: str | None = None, identity: str | None = None, documents=None):
        from cad_server._internal.picker import available

        from .drawings import DrawingRenders
        from .prompt_files import PromptFiles

        # The drawing route's renders, off the request and one per drawing (``drawings.py``).
        self.drawings = DrawingRenders(on_crash=lambda error: self._crashed(error, bugs_only=True))
        # The engine's documents (an .xbf, a STEP): each served off the request, and the page's
        # reads dispatched directly to its document server (``documents.py``).
        self.engine_documents = documents or EngineDocuments(on_crash=lambda error: self._crashed(error, bugs_only=True))
        self.prompt_files = PromptFiles()
        self._exports = None
        self.start = to_posix_path(os.path.abspath(start if start is not None else _working_folder()))
        # Whether this computer has a file chooser for the home's Open (``POST /api/v1/local/pick``).
        self.pick = available()
        self.host = host
        self.port = port
        # dist_dir is compared as a string prefix, so resolve it ONCE here and
        # never re-resolve at request time.
        self.dist_dir = os.path.abspath(dist_dir) if dist_dir else ""
        # Computed ONCE, at start (or handed in by the launcher, which computed it to ask the port):
        # the identity this instance announces is the identity of the code it is actually running.
        self.identity_token = identity if identity is not None else identity_token(self.dist_dir)
        self._recents = None
        self._picker = None
        # The files this app knows by id (``remember``); the engine's app keeps them in its server.
        self._files: dict[str, str] = {}
        # Each document's kind, by its id, once known (``kind_of``): an id never changes kind.
        self._kinds: dict[str, str] = {}
        # The engine shares one recorder across its page and MCP sessions.
        self.analytics = None
        self.consent_by = "viewer"

    @property
    def exports(self):
        # CadApp handles concurrent requests; construct exactly one coordinator per session.
        from .exports import ExportJobs
        with _EXPORTS_LOCK:
            if self._exports is None:
                self._exports = ExportJobs(self.engine_documents.server)
            return self._exports

    # --- server info ------------------------------------------------------

    def server_info(self) -> dict:
        from cad_server import __version__

        return {
            "app": "cad-viewer",
            # The release this server runs: a page that sees another answer after its engine came back
            # reloads into it (an update).
            "release": __version__,
            # The start-time token, NOT identity_token() re-evaluated: a
            # session reports the code it was created with,
            # not the code now on disk. It is also what the browser's reload
            # watcher compares against to notice that this server has become
            # other code on the same port (a restarted checkout, an upgrade).
            "identityToken": self.identity_token,
            # Which file manager Reveal opens: darwin, win32 or linux.
            "platform": sys.platform if sys.platform in ("darwin", "win32") else "linux",
            # The OS identity of the engine serving this page.
            "user": os_user(),
            # The person's home folder: where the explorer starts with nowhere else to start.
            "home": to_posix_path(os.path.expanduser("~")),
            # The folder of the most recent launch, its relative files' folder. Not a boundary.
            "start": self.start,
            "pick": self.pick,
            "port": self.port,
            "pid": os.getpid(),
        }

    def remember(self, path) -> str:
        """An on-disk file the page or a launcher opens, known by its id from now on: its id."""
        found = canonical(path)
        ident = file_id(found)
        self._files[ident] = found
        return ident

    def file_of(self, ident: str) -> str | None:
        """The canonical path of the on-disk file of id ``ident`` this app knows, else None."""
        return self._files.get(ident)

    def _file_of(self, ident: str) -> str | None:
        """A file's path by its id: one registered here, else one in Recents (a page reloaded after
        the engine restarted)."""
        found = self.file_of(ident)
        if found is not None:
            return found
        try:
            record = self.recents.registry.get(ident)
        except OSError:
            record = None
        if record is not None and record.get("kind") == "file":
            from cad_server.engine.registry import home

            return self.file_of(self.remember(home(self.recents.registry, record)))
        return None

    def read_catalog(self, file=None, ident=None) -> dict:
        """The catalog of one document -- ``file``, an absolute path, registered by its id
        (``remember``), or ``ident``, a document's id: a file's or a model's the engine holds -- its
        row, with its ``id``, or none when it has none (``missing`` says why for an id, and
        ``missingState`` is the engine's state for it), and its
        revision -- a digest of the entries, which a client that only watches for change compares
        instead of reading the catalog again. A file is written whole, by rename, by every writer
        cadgen has, so a read never meets one half written."""
        return self._catalog(file, ident)[0]

    def _catalog(self, file=None, ident=None) -> tuple[dict, dict | None]:
        """``read_catalog``'s answer, and the model the engine holds where the row is a model's
        (``model_catalog.held``), else None."""
        from .model_catalog import held, row

        missing = state = ""
        entry = model = None
        if ident:
            if not is_id(ident):
                raise ValueError(f"{ident} is not a document id")
            path = self._file_of(ident)
            if path is not None:
                entry = catalog_entry(path)
            else:
                model, why, found_state = held(ident)
                if model is not None:
                    entry = row(ident, model)
                elif self.engine_documents.server is not None:
                    missing, state = why, found_state
                else:
                    missing = f"no document {ident} is held"
        elif file:
            path = absolute_path(file)
            entry = catalog_entry(path)
            if entry is not None:
                self.remember(path)
        if entry is not None and "id" not in entry:
            entry["id"] = file_id(entry["file"])
        entries = [entry] if entry else []
        answer = {"schemaVersion": CAD_CATALOG_SCHEMA_VERSION, "entries": entries, "revision": catalog_revision(entries)}
        if missing:
            answer["missing"] = missing
        if state:
            # The engine's state for the model it does not hold (``unsaved``, ``detached``): the
            # page's title for it.
            answer["missingState"] = state
        return answer, model

    # --- gates ------------------------------------------------------------

    def _rejected_by_host_check(self, request, response) -> bool:
        host_header = request.header("host")
        if host_is_allowed(host_header, self.host):
            return False
        response.send_json(
            403,
            {
                "error": (
                    f"Host header '{hostname_only(host_header)}' is not a local name; "
                    "refusing (DNS-rebinding defense)"
                ),
                "hint": "open the CAD Viewer at 127.0.0.1 or localhost",
            },
        )
        return True

    def _rejected_as_cross_site_post(self, request, response) -> bool:
        if request.header(POST_GUARD_HEADER):
            return False
        response.send_json(
            403,
            {
                "error": f"missing {POST_GUARD_HEADER} header (cross-site {request.method} blocked)",
                "hint": f"send '{POST_GUARD_HEADER}: 1'",
            },
        )
        return True

    # --- static dist + SPA ------------------------------------------------

    def _serve_file(self, response, file_path, content_type) -> bool:
        try:
            stat_result = os.stat(file_path)
        except (OSError, ValueError):
            # ValueError: a path carrying a NUL byte. Node's statSync throws
            # and the throw is caught, falling through to the SPA at 200.
            return False
        if not os.path.isfile(file_path):
            return False
        page = (content_type or "").startswith("text/html")
        response.stream_file(file_path, stat_result, content_type or "", PAGE_HEADERS if page else ())
        return True

    def _serve_dist(self, request, response) -> None:
        """Static dist + SPA fallback.

        The page lives at ``/`` and nothing else here is a directory, so this is
        an ordinary static server: serve the file if the bundle has it,
        otherwise fall back to index.html — EXCEPT under ``/assets/``, where a
        miss must be a 404 rather than HTML, or a stale hashed bundle reference
        turns into an ES-module parse error instead of a readable status.
        """
        if not self.dist_dir:
            # No built client. Answering here rather than joining against an
            # empty base is load-bearing: os.path.join("", x) resolves against
            # the CURRENT WORKING DIRECTORY, which would silently turn the
            # viewer into a static server for wherever it was launched from.
            response.send_plain(404, "Not found")
            return
        pathname = request.path
        request_path = "/index.html" if pathname == "/" else pathname
        try:
            decoded = strict_decode_uri_component(request_path)
        except UriError:
            response.send_plain(400, "Bad request")
            return
        file_path = os.path.abspath(os.path.join(self.dist_dir, decoded.lstrip("/")))
        if not (file_path == self.dist_dir or file_path.startswith(self.dist_dir + os.sep)):
            response.send_plain(403, "Forbidden")
            return
        if self._serve_file(response, file_path, content_type_for_static_asset(file_path)):
            return
        if request_path.startswith("/assets/"):
            response.send_plain(404, "Not found")
            return
        index_html = os.path.join(self.dist_dir, "index.html")
        if not self._serve_file(response, index_html, content_type_for_static_asset(index_html)):
            response.send_plain(404, "Not found")

    # --- dispatch ---------------------------------------------------------

    def handle(self, request, response) -> None:
        """Dispatch one request and record unexpected route failures."""
        try:
            self._dispatch(request, response)
        except ConnectionError:
            raise  # the page left mid-request (a Response's own writes never raise it): no crash of ours
        except Exception as error:
            # Past every route's own answer: a crash of this server's, answered as each front end answers
            # one (a 500), and counted by telemetry (``cad_server/analytics.py``).
            self._crashed(error)
            raise

    def _crashed(self, error: BaseException, *, bugs_only: bool = False) -> None:
        """A route that failed: counted as a crash when it is one (``analytics.signature``), never failing it."""
        if self.analytics is not None:
            self.analytics.crashed(error, "route", bugs_only=bugs_only)

    def _dispatch(self, request, response) -> None:
        method = request.method
        pathname = request.path
        if self._rejected_by_host_check(request, response):
            return
        # Gated before dispatch, not per route, so a route that changes something added later is
        # covered by construction.
        if method in CHANGING_METHODS and self._rejected_as_cross_site_post(request, response):
            return
        if pathname == "/api" or pathname.startswith("/api/"):
            try:
                self._api(request, response)
            except ApiError as refusal:
                refusal.send(response)
            except Exception as error:  # noqa: BLE001
                self._crashed(error, bugs_only=True)  # a bad request is the caller's; a mistake in our code is a crash
                status = 400 if isinstance(error, (ValueError, TypeError)) else 404 if isinstance(error, FileNotFoundError) else 500
                send_json(response, status, {"error": str(error) or type(error).__name__, "hint": _FUNNEL_HINTS[status]})
            return
        if pathname == "/app":
            if method != "GET":
                return ApiError.method(method, pathname, ("GET",)).send(response)
            # The CAD app as one module, which a card's shell imports (``cad_server.assets``): the
            # engine's release, whatever release the host kept the shell of.
            from cad_server.assets import cad_app_code

            code = cad_app_code()
            if code is None:
                send_json(response, 404, {"error": "this install has no CAD app build",
                                          "hint": "run the install command again: `curl -fsSL https://texttocad.dev/install.sh | sh`"})
            else:
                response.send_bytes(200, code, "text/javascript; charset=utf-8")
            return
        if method == "GET":
            self._serve_dist(request, response)
            return
        # A page answers GET alone: anything else at a page's path is no route, never the SPA.
        send_json(response, 404, {"error": f"no route {method} {pathname}", "hint": _ROUTES_HINT})

    # --- the API: /api/v1 ---------------------------------------------------

    def _api(self, request, response) -> None:
        """One request of ``/api/v1`` (``kinds.py``), answered by its family; ``ApiError`` for one no
        route answers, or one its route refuses."""
        pathname = request.path
        if not pathname.startswith(API + "/"):
            raise ApiError(404, f"no route {pathname}", _ROUTES_HINT)
        parts = pathname[len(API) + 1:].split("/")
        head, rest = parts[0], parts[1:]
        if head == "server" and not rest:
            return self._methods(request, {"GET": lambda: send_json(response, 200, self.api_server())})
        if head == "settings" and not rest:
            return self._methods(request, {"GET": lambda: send_json(response, 200, self.settings()),
                                           "PUT": lambda: send_json(response, 200, self._change_settings(request))})
        if head == "look" and rest in ([], ["environment"]):
            # The look the regular display modes draw in, and its environment, as the engine serves them.
            return self._methods(request, {"GET": lambda: self._relay(request, response, "/api/v1/look" + "".join(
                "/" + part for part in rest))})
        if head == "documents":
            return self._documents(request, response, rest)
        if head == "exports":
            return self._export_jobs(request, response, rest)
        if head == "local":
            return self._local(request, response, rest)
        raise ApiError(404, f"no route {pathname}", _ROUTES_HINT)

    def _methods(self, request, routes: dict) -> None:
        """The route's answer to the request's method, or a 405 naming the methods it takes."""
        answer = routes.get(request.method)
        if answer is None:
            raise ApiError.method(request.method, request.path, tuple(routes))
        return answer()

    def api_server(self) -> dict:
        """``GET /api/v1/server``: who this engine is (``server_info``), the token of this start of it
        (``instance``: a page that sees another one reloads), the kinds of documents it reads and
        what each exports, whether a newer text-to-cad is out (``notice``) and where an update a click
        started is (``update``)."""
        return {**self.server_info(), **self._version(),
                "kinds": {"reads": list(KINDS), "exports": {kind: list(formats) for kind, formats in EXPORTS.items()}}}

    def settings(self, share=None) -> dict:
        """``GET /api/v1/settings``: the person's settings every CAD view reads -- the language they
        chose (``cad_server/language.py``) and whether usage stats are shared (``telemetry``: null
        where this server keeps none)."""
        from cad_server import language

        return {"language": language.read(), "telemetry": self._consent(share) if self.analytics is not None else None}

    def _change_settings(self, request) -> dict:
        """``PUT /api/v1/settings`` with part of the settings -- ``{"language": {"locale"}}``,
        ``{"telemetry": {"share"}}`` or both -- answered with the settings as they now are. It takes
        what ``GET`` answers: the telemetry's read-only ``reason``, ``policy`` and ``saved`` ride along
        and are ignored, and a null telemetry (a server that keeps none) changes nothing, so a page
        that puts back what it read, one value changed, changes that value."""
        from cad_server import language

        self._limit(request, 4096)
        payload = json.loads(request.body() or b"{}")
        if type(payload) is not dict or not set(payload) <= {"language", "telemetry"}:
            raise ValueError("a settings change is {\"language\"?: {\"locale\"}, \"telemetry\"?: {\"share\"}}")
        if "language" in payload:
            language.change(payload["language"])
        share = None
        if payload.get("telemetry") is not None:
            telemetry = payload["telemetry"]
            if type(telemetry) is not dict or not isinstance(telemetry.get("share"), bool) \
                    or not set(telemetry) <= {"share", "reason", "policy", "saved"}:
                raise ValueError("a telemetry change is {\"share\": true or false}")
            if self.analytics is None:
                raise ApiError(409, "this server keeps no usage stats", "change it in the CAD Viewer's app menu")
            share = telemetry["share"]
        return self.settings(share)

    @staticmethod
    def _limit(request, limit: int) -> None:
        """A body over ``limit`` bytes is refused (413) before it is read."""
        if int(request.header("content-length") or 0) > limit:
            raise ApiError(413, f"the request's body is over {limit} bytes", "send less", [("connection", "close")])

    # --- documents ------------------------------------------------------------

    def _documents(self, request, response, rest) -> None:
        if not rest:
            return self._methods(request, {
                "GET": lambda: send_json(response, 200, self.documents(request.query)),
                "POST": lambda: self._open(request, response),
                "PATCH": lambda: self._patch_documents(request, response)})
        first = rest[0]
        if first in KINDS:
            if len(rest) == 1:
                return self._methods(request, {"GET": lambda: send_json(response, 200, self.documents(request.query, first))})
            return self._kind_route(request, response, first, rest[1], rest[2:])
        ident = first
        if len(rest) == 1:
            return self._methods(request, {"GET": lambda: send_json(response, 200, self.envelope(ident)),
                                           "DELETE": lambda: self._forget(response, ident)})
        if rest[1:] == ["version"]:
            # Waited on by a page: answered as soon as the document's version is not ``after``.
            return self._methods(request, {"GET": lambda: self._relay(request, response, f"/api/doc/{ident}/version",
                                                                      request.query)})
        if rest[1:] == ["thumbnail"]:
            return self._methods(request, {"GET": lambda: self._thumbnail(response, ident)})
        if rest[1:] == ["exports"]:
            return self._methods(request, {"POST": lambda: self._export(request, response, ident)})
        raise ApiError(404, f"no route {request.path}", _ROUTES_HINT)

    def documents(self, query, kind=None) -> dict:
        """``GET /api/v1/documents``: Recents -- the CAD files pages opened and the models the engine
        built (``recents.py``), each its row with its document's ``id``, ``kind`` and ``api`` (the
        record's own kind, ``file``, ``model`` or ``shape``, is ``record``) -- of one ``kind``, whose
        name or path holds ``q``, at most ``limit``. With ``path``, the file at that absolute path
        alone, as its envelope (``envelope``), known by its id from then on; none for a file no page
        reads."""
        kind = kind or query.get("kind") or None
        if kind is not None and kind not in KINDS:
            raise ApiError(404, f"no kind {kind}", f"the kinds are {', '.join(KINDS)}")
        if query.get("path") is not None:
            catalog, model = self._catalog(query.get("path"), None)
            found = [self._envelope(catalog, model)] if catalog["entries"] else []
            return {"documents": [row for row in found if kind is None or row["kind"] == kind]}
        limit = query.get("limit")
        if limit is not None and not (limit.isascii() and limit.isdigit() and int(limit) > 0):
            raise ValueError("limit is a whole number above 0")
        needle = (query.get("q") or "").lower()
        rows = []
        for entry in self.recents.list():
            row = entry.row()
            if row is None or (kind is not None and row["kind"] != kind):
                continue
            if needle and needle not in f"{row['name']}\n{row['path']}".lower():
                continue
            rows.append(row)
        return {"documents": rows[:int(limit)] if limit is not None else rows}

    def envelope(self, ident) -> dict:
        """``GET /api/v1/documents/<id>``: what the document of id ``ident`` is (``_envelope``); 404
        for an id no document has, its reason the engine's -- naming the command that builds it
        again -- and its ``state`` where the engine names one (``unsaved``, ``detached``)."""
        if not is_id(ident):
            raise ApiError(404, f"{ident} is not a document id", "a document's id is the one its page, /<id>, names")
        catalog, model = self._catalog(None, ident)
        if not catalog["entries"]:
            extra = {"state": catalog["missingState"]} if catalog.get("missingState") else {}
            raise ApiError(404, catalog.get("missing") or f"no document {ident}",
                           "run the model's script again, or open the file from where it is now", **extra)
        return self._envelope(catalog, model)

    def _envelope(self, catalog: dict, model: dict | None) -> dict:
        """A document as every page reads it first: its ``id`` and ``kind``, its ``name``, its
        ``version``, its ``state`` (a model's, the engine's: ``live`` while a worker holds it,
        ``held``, ``building``, ``failed``; a file's ``live``: it follows its disk), its ``source``
        (the script and function that build a model, a file's path), who made it (``producers``),
        where its kind's reads are (``api``), the formats it exports (``exports``) -- and its catalog
        row as the page shows it (``entry``) with that row's digest (``revision``, which a page that
        only watches for change compares). A document the engine serves (a model's, an ``.xbf``'s,
        a STEP's) says whether the engine holds its read now (``held``), asked without starting one."""
        from cad_server import __version__

        row = catalog["entries"][0]
        ident = row["id"]
        if model is not None:
            source = model.get("source") or {}
            state = str(model.get("state") or "held")
            kind = "model"
            found = {"name": str(source.get("name") or row.get("name") or ""),
                     "version": str(model.get("version") if model.get("version") is not None else row.get("hash") or ""),
                     "state": state,
                     "source": {"type": "script", "path": source.get("script"), "function": source.get("name")},
                     "producers": [{"tool": "cad", "release": __version__ if state == "live" else None,
                                    "at": model.get("builtAt")}]}
        else:
            kind = file_kind(row["file"])
            found = {"name": node_basename(row["file"]), "version": str(row.get("hash") or ""), "state": "live",
                     "source": {"type": "file", "path": row["file"]}, "producers": []}
        if kind in ENGINE_KINDS:
            # Held: read and served now (``serve.Server.listing``), or a live model's, registered; a
            # file only known by its id is not.
            server = self.engine_documents.server
            found["held"] = server is not None and (ident in server.served or ident in server.model_loaders)
        return {"id": ident, "kind": kind, **found, "api": document_api(kind, ident), "exports": list(EXPORTS[kind]),
                "schemaVersion": catalog["schemaVersion"], "entry": row, "revision": catalog["revision"]}

    def _open(self, request, response) -> None:
        """``POST /api/v1/documents``: a file opened as a document -- ``{"path"}``, its absolute path
        -- or a model the engine holds made served -- ``{"id"}`` -- answered ``201 {"id", "kind",
        "api"}``. An ``.xbf`` or a STEP is read by the engine first, off the request (``documents.py``):
        while it reads, ``202`` with the same body, its ``state`` ``reading``, the last frame of its
        import (``building``) and when to ask again (``retryMs``, and ``Retry-After``)."""
        self._limit(request, 8192)
        payload = json.loads(request.body() or b"{}")
        if type(payload) is not dict or len(payload) != 1 or not set(payload) <= {"path", "id"}:
            raise ValueError("a document opened is {\"path\": its absolute path} or {\"id\": a model's id}")
        if "id" in payload:
            ident = payload["id"]
            if not isinstance(ident, str) or not is_id(ident):
                raise ValueError(f"{ident!r} is not a document id")
            kind = self.kind_of(ident)
            if kind is None:
                self.envelope(ident)  # its 404, the engine's reason
                raise ApiError(404, f"no document {ident}", "run the model's script again")
            target = ident
        else:
            target = absolute_path(payload["path"])
            kind = file_kind(target)
            if kind is None or extension_of(target) not in VIEWER_EXTENSIONS:
                raise ApiError(400, f"CAD opens {_CAD_EXTENSIONS} files; {node_basename(target)} is not one.",
                               "name a CAD file by its absolute path")
            if not os.path.isfile(target):
                raise ApiError(404, f"no CAD file at {target}", "name a file that exists, by its absolute path")
            ident = self.remember(target)
        if kind in ENGINE_KINDS:
            status, body = self.engine_documents.response(target)
            if status == 202:
                retry = max(1, -(-int(body.get("retryMs") or 0) // 1000))
                return send_json(response, 202, {"id": ident, "kind": kind, "api": document_api(kind, ident), **body},
                                 [("retry-after", retry)])
            if status != 200:
                raise ApiError(status, str(body.get("error") or "the engine would not serve it"),
                               "check that the file is whole, then open it again")
            ident = body["doc"]
        send_json(response, 201, {"id": ident, "kind": kind, "api": document_api(kind, ident)})

    def _patch_documents(self, request, response) -> None:
        """``PATCH /api/v1/documents``: a change to Recents (``_change_recents``), answered with Recents
        as it now is."""
        self._limit(request, _LIBRARY_BODY_LIMIT)
        self._change_recents(json.loads(request.body() or b"{}"))
        send_json(response, 200, self.documents(request.query))

    def _forget(self, response, ident) -> None:
        """``DELETE /api/v1/documents/<id>``: a model's document deleted (``delete_document``: its
        record and its document in the engine's cache), a file's record forgotten, the file untouched."""
        kind = self.kind_of(ident)
        if kind is None:
            self.envelope(ident)  # its 404, the engine's reason
            raise ApiError(404, f"no document {ident}", _ROUTES_HINT)
        if kind == "model":
            self.delete_document(ident)
        else:
            self.recents.registry.delete(ident)
        response.send_empty(204)

    def _export(self, request, response, ident) -> None:
        """``POST /api/v1/documents/<id>/exports``: an export of that document, its job answered at
        once (202, ``exports.ExportJobs``), read at ``/api/v1/exports/<job>``. The request names the
        document as the page shows it (``source``: ``{doc, revision}``, a mesh file's ``doc`` its
        path), which must be this one."""
        self._limit(request, 65536)
        payload = json.loads(request.body() or b"{}")
        doc = (payload.get("source") or {}).get("doc") if type(payload) is dict else None
        if not isinstance(doc, str) or not (doc == ident or (not is_id(doc) and self._same_file(doc, ident))):
            raise ApiError(400, f"the export's source is not document {ident}", "export the document the page shows")
        self.exports.answer(response, lambda jobs: (202, jobs.create(payload)))

    def _same_file(self, path, ident) -> bool:
        try:
            return canonical(absolute_path(path)) == self._file_of(ident)
        except (OSError, ValueError):
            return False

    def _export_jobs(self, request, response, rest) -> None:
        """``/api/v1/exports``: the session's epoch (``GET``), a job's state (``GET <job>``) and its
        file (``GET <job>/file``, a browser download)."""
        if len(rest) <= 2 and (len(rest) < 2 or rest[1] == "file") and all(rest):
            return self._methods(request, {"GET": lambda: self.exports.handle(request, response, rest)})
        raise ApiError(404, f"no route {request.path}", _ROUTES_HINT)

    # --- a kind's documents: /api/v1/documents/<kind>/<id>/... --------------------------

    def kind_of(self, ident) -> str | None:
        """The kind of the document ``ident`` names (a pose's id, ``<id>~<digest>``, its document's):
        a file's by its extension, a model's ``model``; None for no document."""
        base = str(ident or "").split("~", 1)[0]
        if not is_id(base):
            return None
        kind = self._kinds.get(base)
        if kind is None:
            path = self._file_of(base)
            kind = file_kind(path) if path is not None else "model" if self._holds_model(base) else None
            if kind is not None:
                self._kinds[base] = kind
        return kind

    def _holds_model(self, ident) -> bool:
        """Whether the engine holds a model of id ``ident`` (``model_catalog.held``)."""
        from .model_catalog import held

        return held(ident)[0] is not None

    def _kind_route(self, request, response, kind, ident, rest) -> None:
        actual = self.kind_of(ident)
        if actual is None:
            self.envelope(ident.split("~", 1)[0])  # its 404, the engine's reason
            raise ApiError(404, f"no document {ident}", _ROUTES_HINT)
        if actual != kind:
            raise ApiError(404, f"{ident} is a {actual}", f"read it at {document_api(actual, ident)}")
        # A pose's id (``<id>~<digest>``) reads its document's file.
        path = None if kind == "model" else self._file_of(ident.split("~", 1)[0])
        if rest == ["source"] and path is not None:
            return self._methods(request, {"GET": lambda: self._stream(response, path)})
        if kind in ENGINE_KINDS:
            return self._engine_route(request, response, kind, ident, rest)
        if kind == "dxf" and rest == ["drawing"]:
            return self._methods(request, {"GET": lambda: self._handle_drawing(response, path)})
        if kind in ROBOT_KINDS and (rest == ["structure"] or (len(rest) == 2 and rest[0] == "parts")):
            mesh = rest[1] if len(rest) == 2 else None
            return self._methods(request, {"GET": lambda: self._handle_robot(response, path, mesh, document_api(kind, ident))})
        raise ApiError(404, f"no route {request.path}", f"a {kind}'s routes are {_KIND_ROUTES[kind]}")

    def _engine_route(self, request, response, kind, ident, rest) -> None:
        """A model's, an ``.xbf``'s or a STEP's read, answered by the engine that serves it
        (``cad/engine/serve.py``'s routes, in process: ``_relay``)."""
        doc = f"/api/doc/{ident}"
        query = request.query
        if rest == ["structure"]:
            return self._methods(request, {"GET": lambda: self._relay(request, response, doc, query)})
        if rest == ["kinematics"]:
            return self._methods(request, {"GET": lambda: self._kinematics(request, response, doc)})
        if rest == ["measure"]:
            return self._methods(request, {"GET": lambda: self._relay(request, response, f"{doc}/volumes", query)})
        if rest == ["pose"]:
            return self._methods(request, {"POST": lambda: self._pose(request, response, kind, doc)})
        if rest == ["mesh"]:
            return self._methods(request, {"POST": lambda: self._relay(request, response, f"{doc}/mesh", query)})
        if len(rest) >= 2 and rest[0] == "parts" and rest[1]:
            part = f"{doc}/part/{rest[1]}"
            if len(rest) == 2:
                return self._methods(request, {"GET": lambda: self._relay(request, response, part, query)})
            if len(rest) == 3 and rest[2] in ("groups", "volume"):
                return self._methods(request, {"GET": lambda: self._relay(request, response, f"{part}/{rest[2]}")})
            if len(rest) == 4 and rest[2] in _ELEMENTS and rest[3].isascii() and rest[3].isdigit():
                return self._methods(request, {"GET": lambda: self._relay(
                    request, response, f"{part}/{_ELEMENTS[rest[2]]}/{rest[3]}")})
        raise ApiError(404, f"no route {request.path}", f"a {kind}'s routes are {_KIND_ROUTES[kind]}")

    def _read(self, request, route: str, query=(), prefetch=True) -> tuple[int, str, dict, bytes]:
        """The engine's answer to one of its document reads (``route``: ``/api/doc/<id>...``,
        ``/api/v1/look...``): ``(status, content type, headers, body)``; ``prefetch``: a structure read
        starts meshing its parts, which a page reads next. Documents are the engine's: an
        application with none under it serves none."""
        raise ApiError(404, "documents are served by the installation's engine",
                       "open the document in the CAD Viewer: `cad viewer <file>`")

    def _relay(self, request, response, route: str, query=()) -> None:
        """The engine's answer to ``route``, sent on: its error, a JSON object, gains a ``hint``
        (the command that builds the document again, where the engine names one)."""
        self._send_read(response, self._read(request, route, query))

    @staticmethod
    def _send_read(response, answer) -> None:
        """One of the engine's answers (``_read``) sent on, its error with a ``hint``."""
        status, content_type, headers, body = answer
        if status >= 400 and content_type.startswith("application/json"):
            try:
                found = json.loads(body)
            except ValueError:
                found = None
            if isinstance(found, dict) and "hint" not in found:
                found["hint"] = found.get("rebuild") or _FUNNEL_HINTS.get(status, _ROUTES_HINT)
                body = json.dumps(found, separators=(",", ":")).encode("utf-8")
        response.send_bytes(status, body, content_type, list(headers.items()))

    def _kinematics(self, request, response, doc) -> None:
        """``GET .../kinematics``: the document's mechanism (``mechanism.block``), which its structure
        carries; 404 for a document with no joints."""
        answer = self._read(request, doc, prefetch=False)
        if answer[0] != 200:
            return self._send_read(response, answer)
        block = json.loads(answer[3]).get("kinematics")
        if block is None:
            raise ApiError(404, "the document has no joints", "a model's joints are its assembly's mates")
        send_json(response, 200, block)

    def _pose(self, request, response, kind, doc) -> None:
        """``POST .../pose`` with ``{"pose": NAME | {joint: value}}``: the document served at that pose
        under an id of its own, answered with that id, where it is read (``api``) and the values it
        stands at."""
        answer = self._read(request, f"{doc}/pose")
        if answer[0] != 200:
            return self._send_read(response, answer)
        found = json.loads(answer[3])
        found.pop("url", None)
        send_json(response, 200, {**found, "api": document_api(kind, found["id"])})

    def _stream(self, response, path) -> None:
        """A file's bytes, as data (``RAW_FILE_HEADERS``); 404 once it is gone."""
        try:
            stat_result = os.stat(path)
        except (OSError, ValueError):
            stat_result = None
        if stat_result is None or not stat.S_ISREG(stat_result.st_mode):
            raise ApiError(404, f"No file at {path}", "the file was moved or deleted: open it from where it is now")
        response.stream_file(path, stat_result, content_type_for_path(path), RAW_FILE_HEADERS)

    # --- local: this computer's -------------------------------------------------

    def _local(self, request, response, rest) -> None:
        """``/api/v1/local``: what a local engine does on this computer -- the update, the explorer,
        files by path, Quick Edit's files, Reveal, the clipboard, Open's chooser, the page's activity."""
        route = rest[0] if rest else ""
        if rest == ["update"]:
            return self._methods(request, {"GET": lambda: send_json(response, 200, self._version()),
                                           "POST": lambda: send_json(response, *self._update())})
        if rest == ["folder"]:
            return self._methods(request, {"GET": lambda: self._handle_folder(response, request.query)})
        if rest == ["files"]:
            return self._methods(request, {"GET": lambda: self._handle_file(response, request.query)})
        if rest == ["prompt-files"]:
            return self._methods(request, {"POST": lambda: self._create_prompt_files(request, response)})
        if route == "prompt-files" and len(rest) == 2 and rest[1]:
            return self._methods(request, {"GET": lambda: self._handle_prompt_files_get(request, response, rest[1])})
        if rest == ["reveal"]:
            return self._methods(request, {"POST": lambda: self._reveal(request, response)})
        if rest == ["clipboard"]:
            return self._methods(request, {"POST": lambda: self._clipboard(request, response)})
        if rest == ["pick"]:
            return self._methods(request, {"POST": lambda: self._handle_pick(response)})
        if rest == ["activity"] and self.analytics is not None:
            return self._methods(request, {"POST": lambda: self._activity(request, response)})
        raise ApiError(404, f"no route {request.path}", _ROUTES_HINT)

    def _create_prompt_files(self, request, response) -> None:
        from .prompt_files import MAX_BODY_BYTES

        self._limit(request, MAX_BODY_BYTES)
        status, body = self.prompt_files.create(request.body())
        send_json(response, status, body)

    def _reveal(self, request, response) -> None:
        from .reveal import reveal_path

        self._limit(request, 8192)
        payload = json.loads(request.body())
        if type(payload) is not dict or set(payload) != {"path"}:
            raise ValueError("Reveal requires a path")
        try:
            reveal_path(payload["path"])
        except FileNotFoundError:
            raise ApiError(404, "That file is no longer there.", "open it from where it is now") from None
        response.send_empty(204)

    def _clipboard(self, request, response) -> None:
        from .clipboard import MAX_PNG_BYTES, copy_png

        self._limit(request, MAX_PNG_BYTES)
        copy_png(request.body())
        response.send_empty(204)

    def _activity(self, request, response) -> None:
        # A page's crash report carries its frames (``_report_activity``): room for them, and no more.
        self._limit(request, 16384)
        payload = json.loads(request.body() or b"{}")
        if type(payload) is not dict:
            raise ValueError("an activity report is an object")
        self._report_activity(payload)
        response.send_empty(204)

    # --- the model library, the explorer and the home's Open -------------

    @property
    def recents(self):
        """The one library every CAD view writes (``recents.py``), read lazily; or the store the
        process serving this app already keeps (the CAD app's server hands its own in)."""
        if self._recents is None:
            from .recents import RecentStore

            self._recents = RecentStore()
        return self._recents

    @recents.setter
    def recents(self, store) -> None:
        self._recents = store

    @property
    def picker(self):
        """The desktop's file chooser (``cad_server._internal.picker``), one for this app."""
        if self._picker is None:
            from cad_server._internal.picker import FilePicker

            self._picker = FilePicker()
        return self._picker

    def _change_recents(self, payload) -> None:
        """A change to the library -- ``{action, path, png?}``, a file by its absolute path, a model by
        its id (its entry's ``path``). A file opened is
        also counted for analytics, and so is a model's page, under its own ``model`` kind; a model's entry
        is the engine's, written when it builds, so only when a page opened it (``open``), pinning, its
        picture and its deletion (``delete``: the document, ``delete_document``) change it. A file's
        entry is removed (``remove``), its file untouched."""
        from .recents import thumbnail_png

        if type(payload) is not dict:
            raise ValueError("a recents change is {action, path}")
        action = payload.get("action")
        if is_id(payload.get("path")):
            ident = payload["path"]
            if action in ("pin", "unpin"):
                self.recents.pin(ident, action == "pin")
            elif action == "delete":
                self.delete_document(ident)
            elif action == "thumbnail":
                self.recents.thumbnail(ident, thumbnail_png(payload.get("png")))
            elif action == "open":
                # The page of a document the library holds: a file shown, as a file's is (``files``).
                if self.recents.opened(ident) is not None and self.analytics is not None:
                    self.analytics.opened_document(ident)
            else:
                raise ValueError(f"unknown recents action {action!r}")
            return
        path = absolute_path(payload.get("path"))
        # The library keys a model by its canonical path, the engine's (``ids.canonical``): a
        # symlink, its target and a case variant of one file are one entry.
        key = canonical(path)
        if action == "open":
            if extension_of(path) not in VIEWER_EXTENSIONS or not os.path.isfile(path):
                raise ValueError(f"no CAD file at {path}")
            self.recents.opened(key)
            if self.analytics is not None:
                self.analytics.opened(path)
        elif action in ("pin", "unpin"):
            self.recents.pin(key, action == "pin")
        elif action == "remove":
            self.recents.remove(key)
        elif action == "thumbnail":
            self.recents.thumbnail(key, thumbnail_png(payload.get("png")))
        else:
            raise ValueError(f"unknown recents action {action!r}")

    def delete_document(self, ident):
        """A model's Delete: the one deletion ``cad delete`` is too (``cad_server.engine.models.delete``)
        -- its record and its document in the engine's cache, and, from the engine's own page
        (``engine_app.ViewerApp``), what the engine holds of it first. Never a file of the person's."""
        from cad_server.engine.models import delete

        delete(self.recents.registry, ident)

    def _thumbnail(self, response, ident):
        """``GET /api/v1/documents/<id>/thumbnail``: the picture the library keeps of the document, by
        its record (the PNG named by its content: ``recents.RecentStore.thumbnail``)."""
        try:
            record = self.recents.registry.get(ident) if is_id(ident) else None
        except OSError:
            record = None
        name = str(((record or {}).get("preview") or {}).get("thumbnail") or "")
        png = self.recents.read_thumbnail(name) if _THUMBNAIL_NAME.fullmatch(name) else None
        if png is None:
            raise ApiError(404, f"no picture of {ident}", "a document's picture is taken when its page shows it")
        response.send_bytes(200, png, "image/png", RAW_FILE_HEADERS)

    def _handle_folder(self, response, query):
        """``GET /api/v1/local/folder``: the explorer's reads (``folders.py``): one folder's entries,
        or, with ``q``, the CAD files under it whose path holds ``q``. A path that is not absolute
        is ``folders``' ValueError: a 400, through the funnel."""
        from .folders import list_folder, search_folder

        path = query.get("path")
        try:
            answer = search_folder(path, query.get("q")) if query.get("q") is not None else list_folder(path)
        except FileNotFoundError:
            raise ApiError(404, f"No folder at {path}", "name a folder that exists, by its absolute path") from None
        except PermissionError:
            raise ApiError(403, f"{path} cannot be read", "choose a folder this account may read") from None
        response.send_json(200, answer)

    def _handle_pick(self, response):
        """The home's Open: the desktop's own chooser, held open for as long as the person takes (one
        at a time: the picker refuses a second while one is open)."""
        from cad_server._internal.picker import PickerFailed

        try:
            chosen = self.picker.choose()
        except PickerFailed as failure:
            raise ApiError(500, str(failure), "open the file with `cad viewer <file>` instead") from None
        if chosen is None:
            response.send_json(200, {"cancelled": True})
        elif extension_of(chosen) not in VIEWER_EXTENSIONS:
            raise ApiError(400, f"CAD opens {_CAD_EXTENSIONS} files; {os.path.basename(chosen)} is not one.",
                           "choose a CAD file")
        else:
            response.send_json(200, {"path": to_posix_path(os.path.abspath(chosen))})

    # --- usage stats (telemetry) --------------------------------------------

    def _consent(self, share=None) -> dict:
        """The app menu's Share anonymous usage data toggle: whether usage stats are shared (``share``,
        the key a change names too) and why, and, from the person's click, their answer, which changes it whenever. Nothing asks: telemetry is on by default once a
        ``cadgen`` command has said so (``cad_server/analytics.py``)."""
        from cad_server.analytics import PRIVACY_URL

        changed = self.analytics.choose(share, by=self.consent_by) if isinstance(share, bool) else None
        found = self.analytics.status()
        return {"share": found["sharing"], "reason": found["reason"], "policy": PRIVACY_URL,
                **({"saved": bool(changed.get("saved"))} if changed is not None else {})}

    def _version(self) -> dict:
        """The page's update button (``cad_server/updates.py``): whether a newer text-to-cad is out, from
        the feed as last read -- a feed that is due is read in the background: the page never waits --,
        the release this engine runs, which a page compares with its own to reload into a new one, and
        where an update a click started is (``cad_server._internal.update``)."""
        from cad_server import __version__, updates
        from cad_server._internal.update import UPDATE

        updates.refresh()
        return {"notice": updates.notice(), "release": __version__, "instance": INSTANCE, "update": UPDATE.snapshot()}

    def _update(self) -> tuple[int, dict]:
        """``POST /api/v1/local/update``: the update button's click. The update starts in the background (or the
        one running is joined) and the request is answered at once with ``_version``'s answer, its state
        ``working``; with no newer release, ``idle``. Only the engine's application updates: one with no
        engine under it (a test's) answers 409."""
        from cad_server._internal.update import UPDATE

        server = getattr(self, "server", None)
        if server is None or not callable(getattr(server, "retire", None)):
            return 409, {"error": "no engine serves this page: nothing to update",
                         "hint": "update with the install command: `curl -fsSL https://texttocad.dev/install.sh | sh`"}
        UPDATE.start(server)
        return 202, self._version()

    def _report_activity(self, payload: dict) -> None:
        """What the page did: a person touched it (``touched``), a Quick Edit was sent (``quickEdit``), used its
        controls (``controls``: each ``{control, count, seconds}``, a name of ``cad_server.analytics.CONTROLS`` and
        how often and how long, taken only as that), or the page crashed (``crash``: its signature, made by the
        page as ``cad_server.analytics.signature`` makes one, and taken only if it is one). Noted in memory, and sent
        only with consent. (A model it shows is counted when it joins the library: ``_change_recents``.)"""
        from cad_server.analytics import CONTROLS

        if payload.get("touched") is True:
            self.analytics.viewed()
        if payload.get("quickEdit") is True:
            self.analytics.used("quick_edit")
        controls = payload.get("controls")
        for entry in controls[:len(CONTROLS)] if isinstance(controls, list) else ():
            if isinstance(entry, dict) and set(entry) <= {"control", "count", "seconds"}:
                self.analytics.controlled(entry.get("control"), entry.get("count"), entry.get("seconds", 0))
        crash = payload.get("crash")
        if isinstance(crash, dict) and crash.get("where") == "page":
            self.analytics.crashed(crash)

    # --- routes ----------------------------------------------------------

    def _handle_drawing(self, response, path):
        """``GET /api/v1/documents/dxf/<id>/drawing``: the ``.dxf`` flattened to 2D primitives
        (``drawings.py`` owns the rules); 202 while it renders.

        The payload is already JSON bytes, held in memory by the file's bytes,
        so it goes out through ``send_bytes`` rather than being decoded and
        re-encoded on the way past.
        """
        status, body = self.drawings.response(path or "")
        if isinstance(body, bytes):
            response.send_bytes(status, body, "application/json; charset=utf-8")
            return
        if status >= 400 and "hint" not in body:
            body = {**body, "hint": _FUNNEL_HINTS.get(status, _ROUTES_HINT)}
        response.send_json(status, body)

    def _handle_robot(self, response, path, mesh, api):
        """``GET /api/v1/documents/<urdf|srdf|sdf>/<id>/structure``: the robot description resolved
        for the page, or ``.../parts/<digest>`` one of the primitive meshes cadgen made for it
        (``robots.py`` owns both rules; ``api`` is where the document's reads are). Real work on a
        miss -- the validators, the frame graph, meshing a shape -- so it is counted, as the drawing
        route is."""
        from .robots import robot_response

        status, body, content_type = robot_response(path or "", mesh, api=api)
        if isinstance(body, bytes):
            response.send_bytes(status, body, content_type, RAW_FILE_HEADERS if content_type.startswith("model/") else ())
            return
        if status >= 400 and "hint" not in body:
            body = {**body, "hint": _FUNNEL_HINTS.get(status, _ROUTES_HINT)}
        response.send_json(status, body)

    def _handle_prompt_files_get(self, request, response, name):
        """Read a prompt JSON file; every request carries the viewer guard."""
        if not request.header(POST_GUARD_HEADER):
            raise ApiError(403, f"missing {POST_GUARD_HEADER} header", f"send '{POST_GUARD_HEADER}: 1'")
        found = self.prompt_files.file(name)
        if found is None:
            raise ApiError(404, f"no prompt file {name}", "a prompt's files are read by the name its packet gives")
        data, content_type = found
        response.send_bytes(200, data, content_type, RAW_FILE_HEADERS)

    def _handle_file(self, response, query):
        """``GET /api/v1/local/files?path=<abs>``: a CAD file's bytes, by absolute path (a robot's link
        meshes, a file a model's file names beside it). A 404 names the path and why: the page shows
        the sentence as the reason a model did not load (a robot's missing link mesh among them),
        and a bare "Not found" left nothing to fix."""
        ref = query.get("path") or ""
        candidate = asset_path(ref)
        if not candidate:
            raise ApiError(404, f"{ref} is not a file the viewer sends: it sends CAD files "
                                f"({_CAD_EXTENSIONS}) whose names are not hidden", "name a CAD file by its absolute path")
        self._stream(response, candidate)


def create_cad_app(*, host: str, port: int, dist_dir: str = "", start: str | None = None, identity: str | None = None) -> CadApp:
    return CadApp(host=host, port=port, dist_dir=dist_dir, start=start, identity=identity)
