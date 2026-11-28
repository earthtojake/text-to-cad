"""The HTTP contract: both browser gates, the API's routes (``/api/v1``, ``kinds.py``), and the SPA.

The engine authenticates network requests before this router runs. MCP calls
reach the same router in process through an authenticated session. Two additional
browser gates defend against cross-origin requests:

* Host validation refuses a request whose Host names anything but
  127.0.0.1/localhost/::1 — the DNS-rebinding case, where an attacker domain
  re-resolves to loopback and the browser treats us as same-origin. Skipped when
  bound non-loopback, matching Jupyter's ``allow_remote_access``.
* Every request that changes something -- a POST, PUT, PATCH or DELETE (``CHANGING_METHODS``:
  the model library, a person's settings, an export) -- requires an ``x-cad-viewer``
  header. A cross-origin POST whose params ride the query string is otherwise a no-preflight
  "simple request"; a custom header forces a preflight instead.

No ``Access-Control-*`` headers are served here, deliberately: their absence is what
makes the same-origin policy block cross-origin reads and what makes that
preflight fail. Do not add them. The engine in front of this router makes one
exception, outside it: a CAD card's request that carries a link in its
``Authorization`` header, and that request's preflight, are answered with the
card's own origin and no credentials (``engine_app.EngineApp.preflight``).
"""

from __future__ import annotations

import hashlib
import json
import os
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
from cad.registry import DOCUMENT_TYPES

from .kinds import API, ENGINE_KINDS, EXPORTS, KINDS, ROBOT_KINDS, XBF, document_api, exports_of, file_format, file_kind
from .kinds import kind as current_kind
from .projects import NoFolder, Projects, Refused, locate, public

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

POST_GUARD_HEADER = "x-cad-viewer"
# A thumbnail travels as base64 in the change's JSON: 512 KiB of PNG, and room for the rest, an earlier
# release's page's second picture included (its dark theme's, which is not read).
_LIBRARY_BODY_LIMIT = 1536 * 1024


_CAD_EXTENSIONS = ", ".join(sorted(VIEWER_EXTENSIONS))
_LOOPBACK_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})


def _is_file(path: object) -> bool:
    """Whether ``path`` names a file there now (a model's script may be ephemeral, or gone since)."""
    return isinstance(path, str) and bool(path) and os.path.isfile(path)

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
        return str(version("cad") or "")
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


# What a page's address answers where no client is built (``_serve_dist``): the sentence ``cad viewer`` says.
NOT_BUILT = "The viewer client is not built; build apps/web or install the cad wheel"


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
_ENGINE_ROUTES = ("structure, parts/<key> (/faces|edges|vertices/<ordinal>, /elements, /groups, /volume), measure, "
                  "kinematics, POST pose, POST mesh")
# A model's own: its parameters set in its script, and a look at other values of them (a preview), for one built
# from code; its source, for its .xbf opened from disk.
_MODEL_ROUTES = _ENGINE_ROUTES + ", POST parameters, POST preview (built from code), source (its .xbf)"
# What a preview (``<id>~preview-<token>``, the engine's ``parameters.Previewing``) is read at: what a page draws
# and measures of it, nothing else.
_PREVIEW_ROUTES = "structure, parts/<key> (/faces|edges|vertices/<ordinal>, /elements, /groups, /volume), measure"
PREVIEW_MARK = "~preview-"
# What each kind's collection answers, by how its document type is viewed (``cad.registry``).
_VIEW_ROUTES = {"document": _ENGINE_ROUTES + ", source", "drawing": "drawing, source",
                "robot": "structure, parts/<digest>, source", "mesh": "source", "plot": "plot, models, drc, source"}
# The status a refused change of a model's parameters is answered with, by its ``code``
# (``cad.engine.parameters.CODES``): 400 for a request that names what the model has not or gives a value it
# does not take -- the same request fails again --; 409 for one the model's state refuses now -- no live worker
# that recorded where its parameters are, one the code does not spell as a number, a script changed since its
# run, a build of it running, a build at the new values that failed (the script put back as it was).
PARAMETER_STATUS = {"unknown_parameter": 400, "not_a_number": 400, "out_of_range": 400, "no_worker": 409,
                    "not_writable": 409, "script_changed": 409, "busy": 409, "build_failed": 409}
# An xbf's: a held model's and its file's (``_MODEL_ROUTES``); an alias (``model``) its kind's.
_KIND_ROUTES = {entry.wire: _MODEL_ROUTES if entry.held else _VIEW_ROUTES[entry.view] for entry in DOCUMENT_TYPES.values()}
_KIND_ROUTES.update({named: _KIND_ROUTES[current_kind(named)] for named in KINDS if named not in _KIND_ROUTES})
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
    relative files were read from; it bounds nothing. Nothing here browses the disk: a page reads the
    files it is named and lists the folders of the projects a person opened (``projects.py``).
    """

    # The link for the engine's page (``GET /api/v1/local/link``): the page's own address
    # (``EngineApp.default_app``) and a CAD app card's Copy link (``mcp/http.py``). None: no link here.
    issue_link = None

    def __init__(self, *, host: str, port: int, dist_dir: str = "", start: str | None = None, identity: str | None = None, documents=None):
        from cad_server._internal.picker import available, takes_either

        from .drawings import DrawingRenders
        from .plots import BoardAnswers
        from .reveal import available as reveal_available

        # The drawing route's renders, off the request and one per drawing (``drawings.py``).
        self.drawings = DrawingRenders(on_crash=lambda error: self._crashed(error, bugs_only=True))
        # A board's plot and DRC, made with KiCad off the request and kept by its bytes (``plots.py``).
        self.boards = BoardAnswers(on_crash=lambda error: self._crashed(error, bugs_only=True))
        # The engine's documents (an .xbf, a STEP): each served off the request, and the page's
        # reads dispatched directly to its document server (``documents.py``).
        self.engine_documents = documents or EngineDocuments(on_crash=lambda error: self._crashed(error, bugs_only=True))
        self._exports = None
        self.start = to_posix_path(os.path.abspath(start if start is not None else _working_folder()))
        # Whether this computer has a chooser for the home's Import (``POST /api/v1/local/pick``), and whether
        # one chooser takes a file or a folder there (a Mac's: ``{"any": true}``), so Import is one button; and
        # whether it has a file manager Reveal can open (``reveal.available``).
        self.pick = available()
        self.pick_any = self.pick and takes_either()
        self.reveal = reveal_available()
        self.host = host
        self.port = port
        # dist_dir is compared as a string prefix, so resolve it ONCE here and
        # never re-resolve at request time.
        self.dist_dir = os.path.abspath(dist_dir) if dist_dir else ""
        # Computed ONCE, at start (or handed in by the launcher, which computed it to ask the port):
        # the identity this instance announces is the identity of the code it is actually running.
        self.identity_token = identity if identity is not None else identity_token(self.dist_dir)
        self._library = None
        self._notes = None
        self._projects_store = None
        self._picker = None
        # The files this app knows by id (``remember``); the engine's app keeps them in its server.
        self._files: dict[str, str] = {}
        # A file a project's folder lists through a linked folder in it, by its id: the path it was reached by
        # (``projects.Projects.holding``), which its page and its library entry say it is in.
        self._reached_by: dict[str, str] = {}
        # A file a project's folder lists that is no document, by its id: its path, for Open in alone (``open_in``).
        self._listed: dict[str, str] = {}
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
            # The person's home folder: a page says a path in it from ``~``, and it is no project.
            "home": to_posix_path(os.path.expanduser("~")),
            # The folder of the most recent launch, its relative files' folder. Not a boundary.
            "start": self.start,
            "pick": self.pick,
            # Whether this computer has a file manager Reveal can open: the page offers it only where it does.
            "reveal": self.reveal,
            # Whether that chooser takes a file or a folder in one (a Mac's): the home's Import is one button.
            "pickAny": self.pick_any,
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
        """The path of the file of id ``ident`` while it is there (``projects.locate``: a file this app was
        named, the library's, a project folder's), else None."""
        return locate(ident, self, self.library, self.projects)

    def _reached(self, file, ident) -> str | None:
        """The path the file of id ``ident`` was reached by: the one a page names (``file``) where it is not
        where the file is (a linked folder's), else the one a project's folder listed it by or its library entry
        keeps, either while it still reaches the file (``library.reaching``); None for none."""
        from cad_server.engine.library import reaching

        if file:
            given = os.path.normpath(absolute_path(file))
            if os.path.normcase(given) != os.path.normcase(canonical(given)):
                return given
        path = self.file_of(ident) or ""
        entry = self.library.read()["files"].get(ident) or {}
        return reaching(self._reached_by.get(ident), path) or reaching(entry.get("reached"), path)

    def read_catalog(self, file=None, ident=None) -> dict:
        """The catalog of one document -- ``file``, an absolute path, registered by its id
        (``remember``), or ``ident``, a document's id: a file's or a model's the engine holds -- its
        row, with its ``id`` and the project it is in (``project``: ``{id, name, root, folder}``, null for a
        standalone one), or none when it has none (``missing`` says why for an id), and its
        revision -- a digest of the entries, which a client that only watches for change compares
        instead of reading the catalog again. A file is written whole, by rename, by every writer
        cadgen has, so a read never meets one half written."""
        return self._catalog(file, ident)[0]

    def _catalog(self, file=None, ident=None) -> tuple[dict, dict | None]:
        """``read_catalog``'s answer, and the model the engine holds where the row is a model's
        (``model_catalog.held``), else None."""
        from .model_catalog import held, row

        missing = ""
        entry = model = None
        if ident:
            if not is_id(ident):
                raise ValueError(f"{ident} is not a document id")
            path = self._file_of(ident)
            # A model a live worker holds is the model; else its .xbf, read as the file it is.
            if path is None or path.lower().endswith(".xbf"):
                model = held(ident)
            entry = row(ident, model) if model is not None else catalog_entry(path) if path is not None else None
            if entry is None:
                missing = f"no document {ident} is held"
        elif file:
            path = absolute_path(file)
            entry = catalog_entry(path)
            if entry is not None:
                found = self.remember(path)
                if path.lower().endswith(".xbf"):
                    model = held(found)  # opened by its path: the model, live, while a worker holds it
                    if model is not None:
                        entry = row(found, model)
        if entry is not None and "id" not in entry:
            entry["id"] = file_id(entry["file"])
        if entry is not None:
            # The project it is in (``projects.py``) and the folder of it the document is in, by the path it was
            # reached by (the page's, else the one its library entry keeps: a file in a linked folder inside a
            # project's is that project's), else by where it is.
            source = (model.get("source") or {}).get("xbf") if model is not None else entry["file"]
            where = canonical(source) if source else None
            reached = self._reached(file, entry["id"]) if model is None else None
            found = self.projects.holding(reached, where)
            if found is not None:
                at = reached if reached and self.projects.of(reached, [found]) else where
                folder = to_posix_path(os.path.relpath(os.path.dirname(at), found["root"]))
                entry["project"] = {**{key: value for key, value in public(found).items() if key in ("id", "name", "root")},
                                    "folder": "" if folder == "." else folder}
            else:
                entry["project"] = None
        entries = [entry] if entry else []
        answer = {"schemaVersion": CAD_CATALOG_SCHEMA_VERSION, "entries": entries, "revision": catalog_revision(entries)}
        if missing:
            answer["missing"] = missing
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
                "hint": "open this page at 127.0.0.1 or localhost",
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
        turns into an ES-module parse error instead of a readable status, and
        at an address below the root (``/a/b``, ``/<id>/``): the page reads its
        scripts at ``./assets/`` (the build's base is relative, so the share
        service and the CAD app can serve it from roots of their own), which from
        there is a folder that does not exist, and the page would be blank.
        """
        if not self.dist_dir:
            # No built client. Answering here rather than joining against an
            # empty base is load-bearing: os.path.join("", x) resolves against
            # the CURRENT WORKING DIRECTORY, which would silently turn the
            # viewer into a static server for wherever it was launched from.
            # It says why, as ``cad viewer`` does: a build's ``view:`` link leads here in a
            # checkout whose client is not built, and a bare "Not found" named nothing to fix.
            response.send_plain(404, NOT_BUILT)
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
        if "/" in pathname[1:]:
            response.send_plain(404, "Not found: the viewer's pages are / and /<document id>")
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
                from cad_server._internal.launch import reinstall_command

                send_json(response, 404, {"error": "this install has no CAD app build",
                                          "hint": f"install cad again: `{reinstall_command()}`"})
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
        if head == "projects":
            return self._projects(request, response, rest)
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
        what each exports, and the release this server runs (``release``)."""
        return {**self.server_info(), **self._version(),
                "kinds": {"reads": list(KINDS), "exports": {kind: list(formats) for kind, formats in EXPORTS.items()}}}

    def settings(self, share=None) -> dict:
        """``GET /api/v1/settings``: the person's settings every CAD view reads -- the language they
        chose (``cad_server/language.py``), whether usage stats are shared (``telemetry``: null
        where this server keeps none), and the releases whose What's new they have seen, with the one
        this installation runs (``whats_new``, ``cad_server/whats_new.py``)."""
        from cad_server import language, whats_new

        return {"language": language.read(), "telemetry": self._consent(share) if self.analytics is not None else None,
                "whats_new": whats_new.read()}

    def _change_settings(self, request) -> dict:
        """``PUT /api/v1/settings`` with part of the settings -- ``{"language": {"locale"}}``,
        ``{"telemetry": {"share"}}``, ``{"whats_new": {"seen"}}`` or several -- answered with the settings as
        they now are. It takes what ``GET`` answers: the telemetry's read-only ``reason``, ``policy`` and
        ``saved`` and What's new's ``release`` ride along and are ignored, a null telemetry (a server that keeps
        none) changes nothing, and What's new's ``seen`` is added to what is kept, never taken from it, so a
        page that puts back what it read, one value changed, changes that value."""
        from cad_server import language, whats_new

        self._limit(request, 4096)
        payload = json.loads(request.body() or b"{}")
        if type(payload) is not dict or not set(payload) <= {"language", "telemetry", "whats_new"}:
            raise ValueError("a settings change is {\"language\"?: {\"locale\"}, \"telemetry\"?: {\"share\"}, "
                             "\"whats_new\"?: {\"seen\"}}")
        if "language" in payload:
            language.change(payload["language"])
        if "whats_new" in payload:
            whats_new.change(payload["whats_new"])
        share = None
        if payload.get("telemetry") is not None:
            telemetry = payload["telemetry"]
            if type(telemetry) is not dict or not isinstance(telemetry.get("share"), bool) \
                    or not set(telemetry) <= {"share", "reason", "policy", "saved"}:
                raise ValueError("a telemetry change is {\"share\": true or false}")
            if self.analytics is None:
                raise ApiError(409, "this server keeps no usage stats", "change it in the app menu of CAD's page in your browser")
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
        if PREVIEW_MARK in ident:
            # A page's preview is no document: it has no envelope, version, thumbnail or export.
            raise ApiError(404, f"no route {request.path}", f"a preview's routes are {_PREVIEW_ROUTES}, "
                           "under /api/v1/documents/model/<id>~preview-<token>/")
        if len(rest) == 1:
            return self._methods(request, {"GET": lambda: send_json(response, 200, self.envelope(ident))})
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
        """``GET /api/v1/documents``: Recents (``recents.py``: the library's files that are there, a model its
        ``.xbf``), each its row with its document's ``id``, ``kind`` and ``api`` and the id of the project it is in
        (``project``: ``projects.py``; null for a standalone one) -- of one ``kind``, whose name or path holds
        ``q``, at most ``limit``. With ``path``, the file at that absolute path alone, as its envelope
        (``envelope``), known by its id from then on; none for a file no page reads."""
        from .recents import listing

        kind = kind or query.get("kind") or None
        if kind is not None and kind not in KINDS:
            raise ApiError(404, f"no kind {kind}", f"the kinds are {', '.join(KINDS)}")
        if kind is not None:
            kind = current_kind(kind)  # ``model``: the ``xbf`` kind's, a model's, its file and every other
        if query.get("path") is not None:
            catalog, model = self._catalog(query.get("path"), None)
            found = [self._envelope(catalog, model)] if catalog["entries"] else []
            return {"documents": [row for row in found if kind is None or row["kind"] == kind]}
        limit = query.get("limit")
        if limit is not None and not (limit.isascii() and limit.isdigit() and int(limit) > 0):
            raise ValueError("limit is a whole number above 0")
        needle = (query.get("q") or "").lower()
        rows = [row for row in listing(self.library, self.notes, self.projects)
                if (kind is None or row["kind"] == kind) and needle in f"{row['name']}\n{row['path']}".lower()]
        return {"documents": rows[:int(limit)] if limit is not None else rows}

    def envelope(self, ident) -> dict:
        """``GET /api/v1/documents/<id>``: what the document of id ``ident`` is (``_envelope``); 404
        for an id that names nothing: no worker holds it and its file is not there."""
        return self._envelope(*self._known(ident))

    def _known(self, ident) -> tuple[dict, dict | None]:
        """``_catalog`` of the document of id ``ident``; 404 for an id no document has (``envelope``), with the
        ``path`` of the file it named where this server knows it (``_named``): a page says that file is gone."""
        if not is_id(ident):
            raise ApiError(404, f"{ident} is not a document id", "a document's id is the one its page, /<id>, names")
        catalog, model = self._catalog(None, ident)
        if not catalog["entries"]:
            named = self._named(ident)
            raise ApiError(404, catalog["missing"], "run the model's script again, or open the file from where it is now",
                           **({"path": to_posix_path(named)} if named else {}))
        return catalog, model

    def _named(self, ident) -> str | None:
        """The file document ``ident`` was, there or not: the one this app was named for it, else its library entry's."""
        return self.file_of(ident) or (self.library.read()["files"].get(ident) or {}).get("path") or None

    def _envelope(self, catalog: dict, model: dict | None) -> dict:
        """A document as every page reads it first: its ``id`` and ``kind``, its ``name``, its
        ``version``, its ``state`` (a model's, the engine's: ``live`` while a worker holds it,
        ``held``, ``building``, ``failed``; a file's ``live``: it follows its disk), its ``source``
        (the script and function that build a model, a file's path, and whether that file is there
        now, ``present``: a page offers what acts on the file only then), who made it (``producers``),
        where its kind's reads are (``api``), the formats it exports (``exports``) -- and its catalog
        row as the page shows it (``entry``) with that row's digest (``revision``, which a page that
        only watches for change compares). A document the engine serves (a model's, an ``.xbf``'s,
        a STEP's) says whether the engine holds its read now (``held``), asked without starting one. An
        ``.xbf`` is a model's document opened from disk (kind ``xbf``): its ``source`` the file, no producer,
        and what that file exports (``kinds.exports_of``)."""
        from cad_server import __version__

        row = catalog["entries"][0]
        ident = row["id"]
        if model is not None:
            source = model.get("source") or {}
            state = str(model.get("state") or "held")
            kind = XBF
            # Named by its .xbf's file name, as its row is and as the same document read from that file is.
            found = {"name": str(row.get("name") or source.get("name") or ""),
                     "version": str(model.get("version") if model.get("version") is not None else row.get("hash") or ""),
                     "state": state,
                     # `/`-separated, as a file's path is (its row's ``file``), whichever way its id was found.
                     "source": {"type": "script", "path": to_posix_path(source["script"]) if source.get("script") else None,
                                "function": source.get("name"),
                                "present": _is_file(source.get("script"))},
                     "producers": [{"tool": "cad", "release": __version__ if state == "live" else None,
                                    "at": model.get("builtAt")}]}
        else:
            kind = file_kind(row["file"])
            found = {"name": node_basename(row["file"]), "version": str(row.get("hash") or ""), "state": "live",
                     "source": {"type": "file", "path": row["file"], "present": _is_file(row["file"])}, "producers": []}
        if kind in ENGINE_KINDS:
            # Held: read and served now (``serve.Server.listing``), or a live model's, registered; a
            # file only known by its id is not.
            server = self.engine_documents.server
            found["held"] = server is not None and (ident in server.served or ident in server.model_loaders)
        return {"id": ident, "kind": kind, **found, "api": document_api(kind, ident),
                "exports": exports_of(kind, model is None),
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
            if "path" in payload:
                self._counted(ident)
        send_json(response, 201, {"id": ident, "kind": kind, "api": document_api(kind, ident)})

    def _counted(self, ident) -> None:
        """How many part occurrences the file of id ``ident`` holds, noted (``library.Notes.count``) from the
        read the engine holds of it now (an ``.xbf``'s, a STEP's): a row lists it from then on, while the file is
        the version that read was of. Nothing is read for it."""
        server = self.engine_documents.server
        served = server.served.get(ident) if server is not None else None
        if served is not None and not isinstance(served.path, str):  # a file's read, not a model's document
            self.notes.count(served.path, len(served.structure.get("instances") or []),
                             str(served.structure.get("version") or "") or None)

    def _patch_documents(self, request, response) -> None:
        """``PATCH /api/v1/documents``: a change to Recents (``_change_recents``), answered with Recents
        as it now is."""
        self._limit(request, _LIBRARY_BODY_LIMIT)
        self._change_recents(json.loads(request.body() or b"{}"))
        send_json(response, 200, self.documents(request.query))

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
        a file's by its extension (a model's ``.xbf``, ``xbf``), a model's the engine holds ``xbf``; None for
        no document."""
        base = str(ident or "").split("~", 1)[0]
        if not is_id(base):
            return None
        kind = self._kinds.get(base)
        if kind is None:
            path = self._file_of(base)
            kind = file_kind(path) if path is not None else XBF if self._holds_model(base) else None
            if kind is not None:
                self._kinds[base] = kind
        return kind

    def _holds_model(self, ident) -> bool:
        """Whether the engine holds a model of id ``ident`` (``model_catalog.held``)."""
        from .model_catalog import held

        return held(ident) is not None

    def _kind_route(self, request, response, kind, ident, rest) -> None:
        actual = self.kind_of(ident)
        if actual is None:
            self.envelope(ident.split("~", 1)[0])  # its 404, the engine's reason
            raise ApiError(404, f"no document {ident}", _ROUTES_HINT)
        if actual != current_kind(kind):
            raise ApiError(404, f"{ident} is a {actual}", f"read it at {document_api(actual, ident)}")
        kind = actual  # an alias (``model``) answers as the kind it names: the same bodies
        # A pose's id (``<id>~<digest>``) reads its document's file: a model's its .xbf.
        path = self._file_of(ident.split("~", 1)[0])
        if rest == ["source"] and path is not None:
            return self._methods(request, {"GET": lambda: self._stream(response, path)})
        if kind in ENGINE_KINDS:
            return self._engine_route(request, response, kind, ident, rest)
        if kind == "dxf" and rest == ["drawing"]:
            return self._methods(request, {"GET": lambda: self._handle_drawing(request, response, path)})
        if kind == "kicad_pcb" and rest in (["plot"], ["drc"]):
            return self._methods(request, {"GET": lambda: self._handle_board(request, response, path, rest[0])})
        if kind == "kicad_pcb" and rest == ["models"]:
            return self._methods(request, {"GET": lambda: self._handle_board_models(response, path)})
        if kind == "kicad_sch" and rest == ["plot"]:
            return self._methods(request, {"GET": lambda: self._handle_schematic(request, response, path)})
        if kind in ROBOT_KINDS and (rest == ["structure"] or (len(rest) == 2 and rest[0] == "parts")):
            mesh = rest[1] if len(rest) == 2 else None
            return self._methods(request, {"GET": lambda: self._handle_robot(request, response, path, mesh,
                                                                             document_api(kind, ident))})
        raise ApiError(404, f"no route {request.path}", f"a {kind}'s routes are {_KIND_ROUTES[kind]}")

    def _engine_route(self, request, response, kind, ident, rest) -> None:
        """A model's (live, or its ``.xbf``) or a STEP's read, answered by the engine that serves it
        (``cad/engine/serve.py``'s routes, in process: ``_relay``); a model alone has its parameters set and
        previewed, which the engine refuses while no live worker holds it (``no_worker``)."""
        doc = f"/api/doc/{ident}"
        query = request.query
        if PREVIEW_MARK in ident and not (rest in (["structure"], ["measure"]) or (len(rest) >= 2 and rest[0] == "parts")):
            raise ApiError(404, f"no route {request.path}", f"a preview's routes are {_PREVIEW_ROUTES}")
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
        if rest == ["parameters"] and kind == XBF:
            return self._methods(request, {"POST": lambda: self._parameters(request, response, ident)})
        if rest == ["preview"] and kind == XBF:
            return self._methods(request, {"POST": lambda: self._preview(request, response, ident)})
        if len(rest) >= 2 and rest[0] == "parts" and rest[1]:
            part = f"{doc}/part/{rest[1]}"
            if len(rest) == 2:
                return self._methods(request, {"GET": lambda: self._relay(request, response, part, query)})
            if len(rest) == 3 and rest[2] in ("groups", "elements", "volume"):
                return self._methods(request, {"GET": lambda: self._relay(request, response, f"{part}/{rest[2]}")})
            if len(rest) == 4 and rest[2] in _ELEMENTS and rest[3].isascii() and rest[3].isdigit():
                return self._methods(request, {"GET": lambda: self._relay(
                    request, response, f"{part}/{_ELEMENTS[rest[2]]}/{rest[3]}")})
        raise ApiError(404, f"no route {request.path}", f"a {kind}'s routes are {_KIND_ROUTES[kind]}")

    def _parameters(self, request, response, ident) -> None:
        """``POST /api/v1/documents/model/<id>/parameters`` with ``{"values": {name: number, ...}}``: the
        model's parameters written into its script and the model built again (``set_parameters``: the engine's
        ``set``, the Parameters tab's Save), answered ``200 {"id", "written", "rebuilt"}`` once it is built.
        A change refused is the routes' answer (``{"error", "hint"}``) with its ``code`` (``PARAMETER_STATUS``
        says each one's status) and, for ``not_writable``, the parameter's ``reason``; ``build_failed`` carries
        the build's whole words too (``detail``). The request names parameters and numbers alone: never a
        path, never text."""
        self._limit(request, 65536)
        payload = json.loads(request.body() or b"{}")
        if type(payload) is not dict or set(payload) != {"values"} or type(payload["values"]) is not dict:
            raise ValueError('a change of parameters is {"values": {name: number, ...}}')
        self._parameter_answer(response, lambda: self.set_parameters(ident, payload["values"]))

    def _preview(self, request, response, ident) -> None:
        """``POST /api/v1/documents/model/<id>/preview`` with ``{"values": {name: number, ...}, "page": token}``:
        the model at those values, built in its worker and held for that page alone (``preview_parameters``: the
        engine's ``parameters.Previewing``), never written to its script or its document. Answered ``200`` with
        ``{"id", "preview": {"id", "version", "basis", "values", "seconds", "memo"}}`` -- the preview's own id, read
        at ``/api/v1/documents/model/<that id>/structure`` and its parts' routes --, ``{"id", "preview": null}``
        for values that are the document's (the page's previews let go: Reset, a Save that landed), or ``{"id",
        "superseded": true}`` for a request a newer one replaced before it built. Refused as ``parameters`` is,
        by the same ``code``s and statuses. The request names parameters, numbers and the page's own token alone:
        never a path, never text the engine runs."""
        self._limit(request, 65536)
        payload = json.loads(request.body() or b"{}")
        if type(payload) is not dict or set(payload) != {"values", "page"} or type(payload["values"]) is not dict:
            raise ValueError('a preview is {"values": {name: number, ...}, "page": token}')
        self._parameter_answer(response, lambda: self.preview_parameters(ident, payload["values"], payload["page"]))

    def preview_parameters(self, ident, values, page) -> dict:
        """A model's preview (``_preview``): the engine's, so an application with none under it has none."""
        raise ApiError(404, "documents are served by the installation's engine",
                       "open the document in the CAD Viewer: `cad viewer <file>`")

    def _parameter_answer(self, response, asked) -> None:
        """The answer of a change of parameters or a preview (``asked``), or its refusal as the routes answer one:
        ``{"error", "hint"}`` with its ``code`` (``PARAMETER_STATUS`` says each one's status), the parameter's
        ``reason`` for ``not_writable``, and a failed build's whole words (``detail``); a document the engine
        does not hold is a 404."""
        from cad.engine.parameters import ParameterRefused

        try:
            answer = asked()
        except ParameterRefused as refused:
            extra = {"code": refused.code}
            if refused.code == "not_writable":
                extra["reason"] = refused.reason
            if isinstance(getattr(refused, "detail", None), str):
                extra["detail"] = refused.detail
            raise ApiError(PARAMETER_STATUS.get(str(refused.code), 409), str(refused),
                           refused.hint or "run the model's script again", **extra) from None
        except ValueError as error:
            if type(error).__name__ != "NotHeld":  # the engine's, for a document it does not hold
                raise
            raise ApiError(404, str(error), "run the model's script again") from None
        send_json(response, 200, answer)

    def set_parameters(self, ident, values) -> dict:
        """A model's parameters set (``_parameters``): the engine's, so an application with none under it has
        no model to set."""
        raise ApiError(404, "documents are served by the installation's engine",
                       "open the document in the CAD Viewer: `cad viewer <file>`")

    def _read(self, request, route: str, query=(), prefetch=True) -> tuple[int, str, dict, bytes]:
        """The engine's answer to one of its document reads (``route``: ``/api/doc/<id>...``,
        ``/api/v1/look...``): ``(status, content type, headers, body)``; ``prefetch``: a structure read
        starts meshing its parts, which a page reads next. Documents are the engine's: an
        application with none under it serves none."""
        raise ApiError(404, "documents are served by the installation's engine",
                       "open the document in the viewer: `cad viewer <file>`")

    def _relay(self, request, response, route: str, query=()) -> None:
        """The engine's answer to ``route``, sent on: its error, a JSON object, gains a ``hint``."""
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
                found["hint"] = _FUNNEL_HINTS.get(status, _ROUTES_HINT)
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

    # --- projects: /api/v1/projects ---------------------------------------------

    def _projects(self, request, response, rest) -> None:
        if not rest:
            return self._methods(request, {"GET": lambda: send_json(response, 200, self.project_list()),
                                           "POST": lambda: self._open_project(request, response)})
        if len(rest) == 1:
            return self._methods(request, {"GET": lambda: send_json(response, 200, self.project(rest[0], request.query)),
                                           "DELETE": lambda: self._remove_project(response, rest[0])})
        raise ApiError(404, f"no route {request.path}", _ROUTES_HINT)

    def project_list(self) -> dict:
        """``GET /api/v1/projects``: every project (``projects.py``), the one with the latest activity first:
        when it was last opened as one, or a file in it was opened. No folder is read."""
        from cad_server.engine.library import reaching

        records = self.projects.list()
        activity = {record["id"]: record.get("opened") or 0 for record in records}
        for entry in self.library.read()["files"].values():
            found = self.projects.holding(reaching(entry.get("reached"), entry["path"]), entry["path"], records) \
                if entry.get("opened") else None
            if found is not None:
                activity[found["id"]] = max(activity[found["id"]], entry["opened"])
        return {"projects": [public(record) for record in sorted(records, key=lambda record: activity[record["id"]],
                                                                 reverse=True)]}

    def project(self, ident, query) -> dict:
        """``GET /api/v1/projects/<id>``: one folder of the project (``projects.Projects.folder``) -- ``path``,
        below its root; none: the root -- or, with ``q``, the files anywhere below that folder whose path
        holds every word (``Projects.search``). Each CAD file answered is known by its id from now on
        (``remember``): a row's ``id`` opens its page and reads its envelope whether a page opened the file before
        or not. Any other file answered is no document, and its id names it to Open in alone (``_listed``)."""
        record = self.projects.get(ident)
        if record is None:
            raise ApiError(404, f"no project {ident}", "GET /api/v1/projects lists the projects")
        words = (query.get("q") or "").strip()
        try:
            found = self.projects.search(record, query.get("path"), words, self.notes) if words \
                else self.projects.folder(record, query.get("path"), self.notes)
        except NoFolder as error:
            raise ApiError(404, str(error), "list the project's folder: leave path out") from None
        for row in found["documents"]:
            if row["kind"] is None:
                self._listed[row["id"]] = os.path.normpath(row["path"])
                continue
            if self.file_of(row["id"]) is None:
                self.remember(row["path"])
            reached = os.path.normpath(row["path"])
            if os.path.normcase(reached) != os.path.normcase(self.file_of(row["id"]) or reached):
                self._reached_by[row["id"]] = reached
        return found

    def _open_project(self, request, response) -> None:
        """``POST /api/v1/projects`` with ``{"path"}``, a folder's absolute path: that folder opened as a
        project, answered ``201 {"project", "made": true}`` -- or ``200 {"project", "made": false}`` with the
        project it already is, or is inside (projects do not nest by accident). 400 for a folder that is no
        project (the home folder, one above it, a disk's root), 404 for a path that is no folder."""
        self._limit(request, 8192)
        payload = json.loads(request.body() or b"{}")
        if type(payload) is not dict or set(payload) != {"path"}:
            raise ValueError("a project opened is {\"path\": its folder's absolute path}")
        try:
            record, made = self.projects.add(payload["path"])
        except FileNotFoundError:
            raise ApiError(404, f"no folder at {payload['path']}", "name a folder that exists, by its absolute path") from None
        except Refused as refusal:
            raise ApiError(400, str(refusal), refusal.hint) from None
        send_json(response, 201 if made else 200, {"project": public(record), "made": made})

    def _remove_project(self, response, ident) -> None:
        """``DELETE /api/v1/projects/<id>``: the project forgotten; nothing in its folder changes,
        and its documents are standalone again. Answered with the projects as they now are, as
        ``GET /api/v1/projects`` lists them."""
        if not self.projects.remove(ident):
            raise ApiError(404, f"no project {ident}", "GET /api/v1/projects lists the projects")
        send_json(response, 200, self.project_list())

    # --- local: this computer's -------------------------------------------------

    def _local(self, request, response, rest) -> None:
        """``/api/v1/local``: what a local engine does on this computer -- a folder's entries, files by path,
        Reveal, Open in, the clipboard, Import's chooser, the page's link, the page's activity, cad's update (the update
        button)."""
        if rest == ["folder"]:
            return self._methods(request, {"GET": lambda: self._handle_folder(response, request.query)})
        if rest == ["files"]:
            return self._methods(request, {"GET": lambda: self._handle_file(response, request.query)})
        if rest == ["reveal"]:
            return self._methods(request, {"POST": lambda: self._reveal(request, response)})
        if rest == ["open-in"]:
            return self._methods(request, {"GET": lambda: send_json(response, 200, self.open_in(request.query.get("id")))})
        if rest == ["open"]:
            return self._methods(request, {"POST": lambda: self._open_with(request, response)})
        if rest == ["clipboard"]:
            return self._methods(request, {"POST": lambda: self._clipboard(request, response)})
        if rest == ["pick"]:
            return self._methods(request, {"POST": lambda: self._handle_pick(request, response)})
        if rest == ["link"] and self.issue_link is not None:
            return self._methods(request, {"GET": lambda: send_json(response, 200, self.issue_link())})
        if rest == ["activity"] and self.analytics is not None:
            return self._methods(request, {"POST": lambda: self._activity(request, response)})
        if rest == ["update"]:
            return self._methods(request, {"POST": lambda: send_json(response, *self._update(request))})
        raise ApiError(404, f"no route {request.path}", _ROUTES_HINT)

    def _reveal(self, request, response) -> None:
        from .reveal import CannotReveal, reveal_path

        self._limit(request, 8192)
        payload = json.loads(request.body())
        if type(payload) is not dict or set(payload) != {"path"}:
            raise ValueError("Reveal requires a path")
        try:
            reveal_path(payload["path"])
        except CannotReveal:
            # Not the file's fault: there is nothing here to show it in (`reveal` in /api/v1/server says so).
            raise ApiError(501, "No file manager can be opened on this computer.",
                           "copy the file's path and open its folder another way") from None
        except FileNotFoundError:
            raise ApiError(404, "That file is no longer there.", "open it from where it is now") from None
        response.send_empty(204)

    # Open in: a document's files, each in an app this computer has (``cad_server._internal.apps``).

    def _open_targets(self, ident) -> list[dict]:
        """The files of document ``ident`` Open in offers, each ``{target, kind, path}``: its ``source``
        -- a model's script (kind ``script``), a file's own path -- then, for a model, one
        ``export:<kind>`` for each kind of file its last build wrote, as the engine holds the build
        (``model_info``'s ``files``: none for a model taken up from the cache, which no build wrote
        yet). A file a project's folder listed that is no document is its one target, its kind its
        extension's (``apps.kind_of``). The paths are the server's own: a request only ever names one of
        these. 404 for an id neither names."""
        if ident in self._listed:
            from cad_server._internal.apps import kind_of

            return [{"target": "source", "kind": kind_of(self._listed[ident]), "path": self._listed[ident]}]
        catalog, model = self._known(ident)
        envelope = self._envelope(catalog, model)
        path = envelope["source"].get("path")
        # Each by its file's format: a model's .xbf is an ``xbf`` (``kinds.file_format``).
        targets = [{"target": "source", "kind": "script" if model is not None else file_format(path) or envelope["kind"],
                    "path": path if isinstance(path, str) and path else None}]
        for written in (model or {}).get("files") or ():
            kind = file_format(written)
            if kind is not None and all(target["kind"] != kind for target in targets[1:]):
                targets.append({"target": f"export:{kind}", "kind": kind, "path": str(written)})
        return targets

    def open_in(self, ident) -> dict:
        """``GET /api/v1/local/open-in?id=<id>``: the document's files, or the one file a folder listed
        (``_open_targets``), each with its ``name``, whether it is there now (``present``) and the apps this
        computer has that take its kind (``apps``, as last found: never looked for on a request; a KiCad that
        cannot read the file listed with ``refuses: "newer"``), whether the operating system's own handler may
        not open it (``default: false``: every file but those ``apps.defaults`` lists by extension -- code, a
        KiCad file, an extension no list names -- and every file on a computer that has no handler, a Linux
        without ``xdg-open``: ``Detected.handles``), and the desktop's file manager (``fileManager``)."""
        from cad_server._internal.apps import DETECTED, apps_for, defaults, file_manager

        found = DETECTED.found()
        handles = DETECTED.handles(found)
        return {"targets": [{"target": target["target"], "kind": target["kind"],
                             "name": node_basename(target["path"]) if target["path"] else "",
                             "present": _is_file(target["path"]),
                             "apps": apps_for(target["kind"], found, target["path"]),
                             **({} if handles and defaults(target["path"]) else {"default": False})}
                            for target in self._open_targets(ident)],
                "fileManager": file_manager()}

    def _open_with(self, request, response) -> None:
        """``POST /api/v1/local/open`` with ``{"id", "target", "app"}``: one of the document's files, or the
        file a folder listed (``_open_targets``), in an app found for its kind, or the operating system's own
        handler (``"default"``), started detached (``apps.open_file``). 404 for an id or a file not there,
        400 for a target the id does not have, an app not found for that file, a KiCad that cannot
        read it, the default handler of a file it may not open (``apps.defaults``) or on a computer that has
        none (``Detected.handles``), whatever the request says, and an app that could not be started."""
        from cad_server._internal import apps

        self._limit(request, 8192)
        payload = json.loads(request.body() or b"{}")
        if type(payload) is not dict or set(payload) != {"id", "target", "app"} \
                or not all(isinstance(value, str) for value in payload.values()):
            raise ValueError('Open takes {"id", "target", "app"}: a document, one of its targets and an app')
        targets = {target["target"]: target for target in self._open_targets(payload["id"])}
        chosen = targets.get(payload["target"])
        if chosen is None:
            raise ApiError(400, f"the document has no target {payload['target']!r}",
                           f"name one of {', '.join(targets)}: GET /api/v1/local/open-in?id= lists them")
        found = apps.DETECTED.found()
        takes_default = apps.defaults(chosen["path"]) and apps.DETECTED.handles(found)
        app = None
        if payload["app"] == "default":
            if not apps.defaults(chosen["path"]) and chosen["path"]:
                raise ApiError(400, f"{node_basename(chosen['path'])} is never opened in its default app from here",
                               "open it in an app Open in lists for it, or reveal it in the file manager and open it there")
            if not apps.DETECTED.handles(found):
                raise ApiError(400, "this computer has no default app to start: xdg-open is not installed",
                               "open it in an app Open in lists for it, or from the file manager")
        else:
            listed = apps.apps_for(chosen["kind"], found, chosen["path"])
            entry = next((item for item in listed if item["id"] == payload["app"]), None)
            if entry is None:
                offered = [item["id"] for item in listed if "refuses" not in item] + (["default"] if takes_default else [])
                raise ApiError(400, f"{payload['app']!r} is not an app found here for {chosen['kind']} files",
                               f"name one of {', '.join(offered)}" if offered else "reveal it in the file manager and open it there")
            if "refuses" in entry:
                raise ApiError(400, f"{entry['name']} cannot open {node_basename(chosen['path'])}: a newer KiCad saved it",
                               "open it in a KiCad as new as the one that saved it")
            app = found[payload["app"]]
        # The catalog keeps a file's path `/`-separated; an app is handed this system's own spelling
        # (backslashes on Windows, where some apps refuse the other).
        path = os.path.normpath(chosen["path"]) if chosen["path"] else chosen["path"]
        if not _is_file(path):
            raise ApiError(404, "That file is no longer there.", "build the model again, or open the file from where it is now")
        try:
            apps.open_file(path, app, app_id=payload["app"])
        except OSError as error:  # a program missing on the person's computer: not the server's fault
            raise ApiError(400, f"the app could not be started: {error}", "open the file from the file manager instead") from None
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

    # --- the model library and Import's chooser -----------------------------

    @property
    def library(self):
        """The one library every CAD view writes (``cad_server.engine.library``), read lazily; or the one the
        process serving this app already keeps (the CAD app's server hands its own in)."""
        if self._library is None:
            from cad_server.engine.library import Library

            self._library = Library()
        return self._library

    @library.setter
    def library(self, library) -> None:
        self._library = library

    @property
    def notes(self):
        """What the cache notes of each file (``cad_server.engine.library.Notes``): its count, its picture."""
        if self._notes is None:
            from cad_server.engine.library import Notes

            self._notes = Notes()
        return self._notes

    @property
    def projects(self):
        """The folders opened as projects (``projects.py``), the library's."""
        if self._projects_store is None:
            self._projects_store = Projects(self.library)
        return self._projects_store

    @property
    def picker(self):
        """The desktop's chooser of a file or a folder (``cad_server._internal.picker``), one for this app."""
        if self._picker is None:
            from cad_server._internal.picker import FilePicker

            self._picker = FilePicker()
        return self._picker

    def _change_recents(self, payload) -> None:
        """A change to the library -- ``{action, path, png?}``, a file by its absolute path or its document's id:
        opened on a page (``open``: its entry, made where it had none; counted for analytics, a document a live
        worker holds under its own ``model`` kind), pinned or not (``pin``, ``unpin``), forgotten (``remove``:
        ``forget``; no file changes), or pictured (``thumbnail``: the cache's note of it, no entry)."""
        from .recents import present, thumbnail_png

        if type(payload) is not dict:
            raise ValueError("a recents change is {action, path}")
        action, named = payload.get("action"), payload.get("path")
        ident = named if is_id(named) else None
        path = self._file_of(ident) if ident is not None else absolute_path(named)
        if action == "remove":
            self.forget(ident or file_id(path))
        elif action not in ("open", "pin", "unpin", "thumbnail"):
            raise ValueError(f"unknown recents action {action!r}")
        elif path is None:
            raise ValueError(f"no document {ident} is held")  # an id whose file is gone names nothing
        elif action == "unpin":
            self.library.pin(path, False)
        elif present(path) is None:
            raise ValueError(f"no CAD file at {path}")
        elif action == "pin":
            self.library.pin(path, True)
        elif action == "thumbnail":
            self.notes.picture(path, thumbnail_png(payload.get("png")))
        else:
            # Its entry is its canonical path's, and says the path it was reached by: the page's, or a project's listing's.
            key = ident or file_id(path)
            self.library.opened(path, reached=self._reached_by.get(key))
            self._counted(key)  # the read the engine holds of it
            if self.analytics is not None:
                if ident is not None and self._holds_model(ident):
                    self.analytics.opened_document(ident)
                else:
                    self.analytics.opened(path)

    def forget(self, ident) -> None:
        """Document ``ident`` forgotten (the home's Remove): its library entry -- and, from the engine's own page
        (``engine_app.ViewerApp``), what the engine holds of it first. Never a file of the person's, nor the cache's
        note of it, which is the file's (``library.Notes``)."""
        self.library.forget(ident)
        self._files.pop(ident, None)

    def _thumbnail(self, response, ident):
        """``GET /api/v1/documents/<id>/thumbnail``: the picture the cache keeps of the document's file as it is
        now (``library.Notes.png``), the one picture in either theme."""
        from cad_server.engine.state import file_version

        path = self._file_of(ident) if is_id(ident) else None
        png = self.notes.png(ident, file_version(path)) if path is not None else None
        if png is None:
            raise ApiError(404, f"no picture of {ident}", "a document's picture is taken when its page shows it")
        response.send_bytes(200, png, "image/png", RAW_FILE_HEADERS)

    def _handle_folder(self, response, query):
        """``GET /api/v1/local/folder``: one folder's entries, or, with ``q``, the CAD files under it whose path holds
        ``q`` (``folders.py``). A route of v1, which only ever adds one: no view of this release reads it (a view moves
        within a project, ``projects.py``). A path that is not absolute is ``folders``' ValueError: a 400, through the
        funnel."""
        from .folders import list_folder, search_folder

        path = query.get("path")
        try:
            answer = search_folder(path, query.get("q")) if query.get("q") is not None else list_folder(path)
        except FileNotFoundError:
            raise ApiError(404, f"No folder at {path}", "name a folder that exists, by its absolute path") from None
        except PermissionError:
            raise ApiError(403, f"{path} cannot be read", "choose a folder this account may read") from None
        response.send_json(200, answer)

    def _handle_pick(self, request, response):
        """Import's chooser: the desktop's own, held open for as long as the person takes (one at a time:
        the picker refuses a second while one is open). A file, or with ``{"folder": true, "start"?}`` a
        folder, the chooser starting at ``start`` (an absolute folder) where one is named; or with
        ``{"any": true}``, where the desktop's one chooser takes either (``pickAny``: a Mac's), whichever the
        person chose, answered with whether it is a folder."""
        from cad_server._internal.picker import PickerFailed, takes_either

        self._limit(request, 8192)
        payload = json.loads(request.body() or b"{}")
        if type(payload) is not dict or not set(payload) <= {"folder", "start", "any"} \
                or any(type(payload.get(flag, False)) is not bool for flag in ("folder", "any")) \
                or (payload.get("folder") and payload.get("any")):
            raise ValueError("a pick is {} for a file, {\"folder\": true, \"start\"?: a folder's absolute path} for a "
                             "folder, or {\"any\": true} for either")
        folder, either = payload.get("folder", False), payload.get("any", False)
        if either and not takes_either():
            raise ApiError(400, "This computer's chooser takes a file or a folder, not either in one.",
                           "ask for a file ({}) or a folder ({\"folder\": true}); `pickAny` in /api/v1/server says which it has")
        # A file's chooser starts where the desktop last left it: ``start`` is the folder chooser's alone.
        start = absolute_path(payload["start"]) if folder and payload.get("start") is not None else None
        if start is not None and not os.path.isdir(start):
            start = None  # gone since the page named it: the chooser starts where it would
        try:
            chosen = self.picker.choose(folder=folder, start=start, either=either)
        except PickerFailed as failure:
            command = "`cad viewer <file>` or `cad viewer <folder>`" if either else "`cad viewer <folder>`" if folder else "`cad viewer <file>`"
            raise ApiError(500, str(failure), f"open it with {command} instead") from None
        if chosen is None:
            response.send_json(200, {"cancelled": True})
            return
        # One chooser of either: a folder is a folder's answer, anything else a file's.
        chose_folder = folder or (either and os.path.isdir(chosen))
        if chose_folder:
            if not os.path.isdir(chosen):
                raise ApiError(400, f"{chosen} is not a folder", "choose a folder")
        elif extension_of(chosen) not in VIEWER_EXTENSIONS:
            raise ApiError(400, f"CAD opens {_CAD_EXTENSIONS} files; {os.path.basename(chosen)} is not one.",
                           "choose a CAD file, or a folder" if either else "choose a CAD file")
        answer = {"path": to_posix_path(os.path.abspath(chosen))}
        response.send_json(200, {**answer, "folder": chose_folder} if either else answer)

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
        """The release this engine runs, which a page compares with its own to reload into a new one, the token
        of this start of it (``instance``), what the update button shows (``cadUpdate``: ``auto_update.button``,
        null where cad cannot update itself), and the project's notices for this cad, each a card until the person
        dismisses it (``cadNotices``: ``notices.for_viewer``, ``[{id, text, url?}]``, ``[]`` where there is none)."""
        from cad_server import __version__, notices
        from cad_server._internal import auto_update

        return {"release": __version__, "instance": INSTANCE, "cadUpdate": auto_update.button(),
                "cadNotices": notices.for_viewer()}

    def _update(self, request) -> tuple[int, dict]:
        """``POST /api/v1/local/update``: the update button. ``{}``: a person's update of cad, as ``cad update`` asks it
        of the engine (``Daemon.update``: PyPI asked now, the attempt underway joined, else begun at once, never past
        this cad's major; ``asked`` in its record, so it spends none of the automatic tries),
        answered ``202`` with ``GET /api/v1/server``'s ``release``, ``instance`` and ``cadUpdate``. ``{"dismiss": at}``:
        the failure of the attempt begun at ``at`` put away (``auto_update.dismiss``), answered ``200`` the same way.
        Refused (409, its ``cause`` where it is one of ``auto_update.SAID``: ``no_installer``, with what
        to do as its ``hint``, ``auto_update.advice``) where cad cannot update itself, or where no engine serves this page (a test's server of its own). Behind every check a route that changes something has."""
        from cad_server import updates
        from cad_server._internal import auto_update

        self._limit(request, 1024)
        payload = json.loads(request.body() or b"{}")
        if type(payload) is not dict or not set(payload) <= {"dismiss"} or (
                "dismiss" in payload and (type(payload["dismiss"]) not in (int, float))):
            raise ValueError('an update is {} (update cad now) or {"dismiss": <the attempt\'s at>}')
        if "dismiss" in payload:
            auto_update.dismiss(payload["dismiss"])
            return 200, self._version()
        hint = "run `cad update` in a terminal"
        ask = getattr(getattr(self, "server", None), "update", None)
        if not callable(ask):
            raise ApiError(409, "no engine serves this page: nothing to update", hint)
        found = auto_update.global_install()
        if found is None:
            raise ApiError(409, auto_update.NOT_THE_TOOL, hint)
        if not updates.checking():
            raise ApiError(409, auto_update.CHECK_OFF, hint)
        blocked = auto_update.blocked(found)
        if blocked is not None:
            said = auto_update.in_words(blocked)
            raise ApiError(409, said, auto_update.advice(blocked), cause=blocked, said=said)
        answer = ask(True)
        if "failed" in answer:
            raise ApiError(409, str(answer["failed"]), hint)
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

    def _handle_drawing(self, request, response, path):
        """``GET /api/v1/documents/dxf/<id>/drawing``: the ``.dxf`` flattened to 2D primitives
        (``drawings.py`` owns the rules); 202 while it renders.

        The payload is already JSON bytes, held in memory by the file's bytes,
        so it goes out through ``send_bytes`` rather than being decoded and
        re-encoded on the way past, compressed where the browser takes it (``compressed``).
        """
        from .compressed import send

        status, body = self.drawings.response(path or "")
        if isinstance(body, bytes):
            send(request, response, status, body, "application/json; charset=utf-8")
            return
        if status >= 400 and "hint" not in body:
            body = {**body, "hint": _FUNNEL_HINTS.get(status, _ROUTES_HINT)}
        response.send_json(status, body)

    def _handle_schematic(self, request, response, path):
        """``GET /api/v1/documents/kicad_sch/<id>/plot``: a KiCad schematic, its hierarchy read from its files,
        every sheet a page of layers (``plots.py``); ``?sheet=/Power/`` that sheet's page alone, ``index=0``
        without the hierarchy's index. Each request reads the files as they are now, and the answer is
        compressed where the browser takes it (``compressed``). A sheet the hierarchy has not is a 400."""
        from .compressed import send
        from .plots import schematic_payload_response

        query = request.query
        sheet = query.get("sheet") or None
        index = (query.get("index") or "1") not in ("0", "false")
        status, body = schematic_payload_response(path or "", sheet=sheet, index=index)
        if isinstance(body, bytes):
            send(request, response, status, body, "application/json; charset=utf-8")
            return
        if status >= 400 and "hint" not in body:
            body = {**body, "hint": _FUNNEL_HINTS.get(status, _ROUTES_HINT)}
        response.send_json(status, body)

    def _handle_board(self, request, response, path, product):
        """``GET /api/v1/documents/kicad_pcb/<id>/plot`` (the board as geometry per layer, its pours KiCad's
        refill) and ``.../drc`` (KiCad's design rule check of it): ``plots.py`` owns the rules. Each is made
        off the request and kept by the board's bytes, answered 202 while it is made, 304 for the key a
        request names (``If-None-Match``), compressed where the browser takes it (``compressed``). A file
        that is not a readable board is a 400 saying why (``PlotError``)."""
        from .compressed import Coded, send

        status, body, key = self.boards.response(product, path or "", if_none_match=request.header("if-none-match"))
        tag = (("etag", f'"{key}"'),) if key else ()
        if status == 304:
            response.send_bytes(304, b"", "", tag)
            return
        if isinstance(body, Coded):
            send(request, response, status, body, "application/json; charset=utf-8", tag)
            return
        if status >= 400 and "hint" not in body:
            body = {**body, "hint": _FUNNEL_HINTS.get(status, _ROUTES_HINT)}
        response.send_json(status, body)

    def _handle_board_models(self, response, path):
        """``GET /api/v1/documents/kicad_pcb/<id>/models``: the board's 3D models table (``plots.BoardAnswers.models``):
        each model a footprint names, the STEP it is by a document id (known from now on, ``remember``) or why
        it has none. It reads the board and ``stat``s the model files, and writes nothing."""
        status, body = self.boards.models(path or "", self.remember)
        if status >= 400 and "hint" not in body:
            body = {**body, "hint": _FUNNEL_HINTS.get(status, _ROUTES_HINT)}
        response.send_json(status, body)

    def _handle_robot(self, request, response, path, mesh, api):
        """``GET /api/v1/documents/<urdf|srdf>/<id>/structure``: the robot description resolved
        for the page, or ``.../parts/<digest>`` one of the primitive meshes cadgen made for it
        (``robots.py`` owns both rules; ``api`` is where the document's reads are). Real work on a
        miss -- the validators, the frame graph, meshing a shape -- so it is counted, as the drawing
        route is."""
        from .robots import robot_response

        status, body, content_type = robot_response(path or "", mesh, api=api)
        if isinstance(body, bytes) and content_type.startswith("application/json"):
            from .compressed import send

            send(request, response, status, body, content_type)
            return
        if isinstance(body, bytes):
            response.send_bytes(status, body, content_type, RAW_FILE_HEADERS if content_type.startswith("model/") else ())
            return
        if status >= 400 and "hint" not in body:
            body = {**body, "hint": _FUNNEL_HINTS.get(status, _ROUTES_HINT)}
        response.send_json(status, body)

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
