"""The HTTP contract: both browser gates, route dispatch, and the SPA.

The engine authenticates network requests before this router runs. MCP calls
reach the same router in process through an authenticated session. Two additional
browser gates defend against cross-origin requests:

* Host validation refuses a request whose Host names anything but
  127.0.0.1/localhost/::1 — the DNS-rebinding case, where an attacker domain
  re-resolves to loopback and the browser treats us as same-origin. Skipped when
  bound non-loopback, matching Jupyter's ``allow_remote_access``.
* Every POST requires an ``x-cadgen-viewer`` header. A POST changes something (the
  model library, a person's settings, a prompt's files), and a cross-origin POST
  whose params ride the query string is otherwise a no-preflight "simple
  request". A custom header forces a preflight instead.

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
import stat
import sys
from pathlib import Path

from cadgen.engine.ids import canonical, file_id, is_id

from .backend import absolute_path, asset_path
from .content_types import content_type_for_path, content_type_for_static_asset, extension_of
from .encoding import UriError, strict_decode_uri_component
from .scanner import CAD_CATALOG_SCHEMA_VERSION, VIEWER_EXTENSIONS, catalog_entry, to_posix_path
from .documents import EngineDocuments

__all__ = [
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
    """The installed cadgen distribution's version, ``""`` when there is no metadata.

    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return str(version("cadgen") or "")
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
    """This process's OS user, as ``/__cad/server`` names it (``user``): the uid on POSIX, the
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


# Routes one method reaches: the other one answers 405 naming it, never a 404 that reads as no route.
_GET_ONLY_ROUTES = frozenset({"/__cad/server", "/__cad/catalog", "/__cad/folder", "/__cad/search",
                              "/__cad/thumbnail", "/__cad/drawing", "/__cad/robot", "/__cad/xbf", "/__cad/asset",
                              "/__cad/version"})
_POST_ONLY_ROUTES = frozenset({"/__cad/pick", "/__cad/reveal", "/__cad/clipboard",
                               "/__cad/analytics/activity"})


class CadApp:
    """``handle(request, response)`` writes exactly one response.

    Unlike the Node app there is no "not mine" return: the Python server always
    serves the client itself, and the dev proxy forwards only the two API
    prefixes, so nothing else can be waiting behind this.

    One app serves every file on this machine, by absolute path (``backend``). The page names
    each document it shows by id, ``/<id>`` (``cadgen.engine.ids``): a model's, or a file's once it
    is registered here (``remember``: by the launcher, or by the catalog's answer for its path).
    ``start`` is the folder of the most recent launch (the working folder by default): what its
    relative files were read from; the explorer never opens there, and it bounds nothing.
    """

    def __init__(self, *, host: str, port: int, dist_dir: str = "", start: str | None = None, identity: str | None = None, documents=None):
        from cadgen._internal.picker import available

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
        # Whether this computer has a file chooser for the home's Open (``POST /__cad/pick``).
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
        return {
            "app": "cad-viewer",
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
            from cadgen.engine.registry import home

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
        from .model_catalog import entry as model_entry, held

        missing = state = ""
        entry = None
        if ident:
            if not is_id(ident):
                raise ValueError(f"{ident} is not a document id")
            path = self._file_of(ident)
            if path is not None:
                entry = catalog_entry(path)
            else:
                entry = model_entry(ident)
                if entry is None:
                    if self.engine_documents.server is not None:
                        _model, missing, state = held(ident)
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
        return answer

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
                )
            },
        )
        return True

    def _rejected_as_cross_site_post(self, request, response) -> bool:
        if request.header(POST_GUARD_HEADER):
            return False
        response.send_json(
            403,
            {
                "error": (
                    f"missing {POST_GUARD_HEADER} header (cross-site POST blocked); "
                    f"send '{POST_GUARD_HEADER}: 1'"
                )
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
            # one (a 500), and counted by telemetry (``cadgen/analytics.py``).
            self._crashed(error)
            raise

    def _crashed(self, error: BaseException, *, bugs_only: bool = False) -> None:
        """A route that failed: counted as a crash when it is one (``analytics.signature``), never failing it."""
        if self.analytics is not None:
            self.analytics.crashed(error, "route", bugs_only=bugs_only)

    def _dispatch(self, request, response) -> None:
        method = request.method
        pathname = request.path
        query = request.query

        if method == "GET":
            if self._rejected_by_host_check(request, response):
                return
            if not pathname.startswith("/__cad/"):
                # Note "/__cad" without the trailing slash is NOT an API path
                # and falls through to the SPA at 200, while "/__cad/" is and
                # answers 404 JSON. Both are the shipped behaviour.
                self._serve_dist(request, response)
                return
            try:
                if pathname == "/__cad/exports" or pathname.startswith("/__cad/exports/"):
                    return self.exports.handle(request, response)
                if pathname == "/__cad/server":
                    response.send_json(200, self.server_info())
                elif pathname == "/__cad/catalog":
                    response.send_json(200, self.read_catalog(query.get("file"), query.get("id")))
                elif pathname in ("/__cad/folder", "/__cad/search"):
                    self._handle_folder(response, pathname, query)
                elif pathname == "/__cad/recents":
                    response.send_json(200, self._recents_payload())
                elif pathname == "/__cad/thumbnail":
                    self._handle_thumbnail(response, query)
                elif pathname == "/__cad/drawing":
                    self._handle_drawing(request, response, query)
                elif pathname == "/__cad/robot":
                    self._handle_robot(request, response, query)
                elif pathname == "/__cad/xbf":
                    # An engine document (an .xbf, a STEP): where the page reads it, once the
                    # engine serves it; 202 while the engine reads it (``documents.py``).
                    if query.get("held") == "1":
                        response.send_json(200, self.engine_documents.held(query.get("file") or ""))
                    else:
                        status, body = self.engine_documents.response(query.get("file") or "")
                        response.send_json(status, body)
                elif pathname.startswith("/__cad/prompt-files/"):
                    self._handle_prompt_files_get(request, response, pathname, query)
                elif pathname == "/__cad/asset":
                    self._handle_asset(request, response, query)
                elif pathname == "/__cad/analytics" and self.analytics is not None:
                    response.send_json(200, self._consent())
                elif pathname == "/__cad/language":
                    from cadgen import language

                    response.send_json(200, language.read())
                elif pathname == "/__cad/version":
                    response.send_json(200, self._version())
                elif pathname in _POST_ONLY_ROUTES:
                    response.send_bytes(405, b'{"ok":false,"error":"Method not allowed"}',
                                        "application/json", [("allow", "POST")])
                else:
                    # An unrecognised /__cad/* path is a bad API call, not a
                    # page: a 404 a client doing res.json() can read, never the
                    # SPA's index.html at 200.
                    response.send_json(404, {"error": "Not found"})
            except Exception as error:  # noqa: BLE001
                self._crashed(error, bugs_only=True)  # a bad request is the caller's; a mistake in our code is a crash
                response.send_json(400 if isinstance(error, (ValueError, TypeError)) else 404 if isinstance(error, FileNotFoundError) else 500,
                                   {"ok": False, "error": str(error)})
            return

        if method == "POST":
            # Gated before dispatch, not per route, so a POST route added later
            # is covered by construction.
            if self._rejected_by_host_check(request, response):
                return
            if self._rejected_as_cross_site_post(request, response):
                return
            try:
                if pathname == "/__cad/exports" or pathname.startswith("/__cad/exports/"):
                    return self.exports.handle(request, response)
                if pathname in ("/__cad/analytics", "/__cad/analytics/activity") and self.analytics is not None:
                    # A page's crash report carries its frames (``_report_activity``): room for them, and no more.
                    if int(request.headers.get("content-length") or 0) > (16384 if pathname.endswith("/activity") else 4096):
                        response.send_empty(413, [("connection", "close")])
                        return
                    payload = json.loads(request.body() or b"{}")
                    if type(payload) is not dict:
                        raise ValueError("an analytics request is an object")
                    if pathname == "/__cad/analytics":
                        response.send_json(200, self._consent(payload.get("share"), by=request.consent_by))
                    else:
                        self._report_activity(payload)
                        response.send_empty(204)
                elif pathname == "/__cad/language":
                    # The app menu's Language: the person's choice, one for every CAD view (``cadgen/language.py``).
                    from cadgen import language

                    if int(request.headers.get("content-length") or 0) > 4096:
                        response.send_empty(413, [("connection", "close")])
                        return
                    response.send_json(200, language.change(json.loads(request.body() or b"{}")))
                elif pathname == "/__cad/recents":
                    if int(request.headers.get("content-length") or 0) > _LIBRARY_BODY_LIMIT:
                        response.send_empty(413, [("connection", "close")])
                        return
                    response.send_json(200, self._change_recents(json.loads(request.body())))
                elif pathname == "/__cad/pick":
                    self._handle_pick(response)
                elif pathname == "/__cad/reveal":
                    from .reveal import reveal_path
                    if int(request.headers.get("content-length") or 0) > 8192:
                        response.send_empty(413, [("connection", "close")])
                        return
                    payload = json.loads(request.body())
                    if type(payload) is not dict or set(payload) != {"path"}:
                        raise ValueError("Reveal requires a path")
                    try:
                        reveal_path(payload["path"])
                    except FileNotFoundError:
                        response.send_json(404, {"ok": False, "error": "That file is no longer there."})
                        return
                    response.send_empty(204)
                elif pathname == "/__cad/clipboard":
                    from .clipboard import MAX_PNG_BYTES, copy_png
                    if int(request.headers.get("content-length") or 0) > MAX_PNG_BYTES:
                        response.send_empty(413, [("connection", "close")])
                        return
                    copy_png(request.body())
                    response.send_empty(204)
                elif pathname == "/__cad/prompt-files":
                    from .prompt_files import MAX_BODY_BYTES
                    if int(request.headers.get("content-length") or 0) > MAX_BODY_BYTES:
                        response.send_empty(413, [("connection", "close")])
                        return
                    status, body = self.prompt_files.create(request.body())
                    response.send_json(status, body)
                elif pathname in _GET_ONLY_ROUTES:
                    response.send_bytes(405, b'{"ok":false,"error":"Method not allowed"}',
                                        "application/json", [("allow", "GET, HEAD")])
                else:
                    response.send_json(404, {"error": "Not found"})
            except Exception as error:  # noqa: BLE001
                self._crashed(error, bugs_only=True)  # a bad request is the caller's; a mistake in our code is a crash
                response.send_json(400 if isinstance(error, (ValueError, TypeError)) else 404 if isinstance(error, FileNotFoundError) else 500,
                                   {"ok": False, "error": str(error)})
            return

        # Unreachable: handler.py answers 405 for every other method before
        # dispatch ever runs.
        response.send_empty(405, [("allow", "GET, HEAD, POST")])

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
        """The desktop's file chooser (``cadgen._internal.picker``), one for this app."""
        if self._picker is None:
            from cadgen._internal.picker import FilePicker

            self._picker = FilePicker()
        return self._picker

    def _recents_payload(self) -> dict:
        # Recents, the registry's view (``recents.py``): the CAD files the viewer opens, and the models.
        return {"recents": [entry.public() for entry in self.recents.list()
                            if entry.kind != "file" or extension_of(entry.path) in VIEWER_EXTENSIONS]}

    def _change_recents(self, payload) -> dict:
        """A change to the library -- ``{action, path, png?}``, a file by its absolute path, a model by
        its id (its entry's ``path``) -- answered with the library as it now is. A file opened is
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
            return self._recents_payload()
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
        return self._recents_payload()

    def delete_document(self, ident):
        """A model's Delete: the one deletion ``cadgen delete`` is too (``cadgen.engine.models.delete``)
        -- its record and its document in the engine's cache, and, from the engine's own page
        (``engine_app.ViewerApp``), what the engine holds of it first. Never a file of the person's."""
        from cadgen.engine.models import delete

        delete(self.recents.registry, ident)

    def _handle_thumbnail(self, response, query):
        """A library picture, by the content name the library gives it."""
        name = query.get("name") or ""
        png = self.recents.read_thumbnail(name) if _THUMBNAIL_NAME.fullmatch(name) else None
        if png is None:
            response.send_json(404, {"error": "Not found"})
            return
        response.send_bytes(200, png, "image/png", RAW_FILE_HEADERS)

    def _handle_folder(self, response, pathname, query):
        """The explorer's reads (``folders.py``): one folder's entries (``/__cad/folder``), or the
        CAD files under it whose path holds ``q`` (``/__cad/search``). A path that is not absolute
        is ``folders``' ValueError: a 400, through the GET funnel."""
        from .folders import list_folder, search_folder

        path = query.get("path")
        try:
            answer = search_folder(path, query.get("q")) if pathname == "/__cad/search" else list_folder(path)
        except FileNotFoundError:
            response.send_json(404, {"error": f"No folder at {path}"})
            return
        except PermissionError:
            response.send_json(403, {"error": f"{path} cannot be read"})
            return
        response.send_json(200, answer)

    def _handle_pick(self, response):
        """The home's Open: the desktop's own chooser, held open for as long as the person takes (one
        at a time: the picker refuses a second while one is open)."""
        from cadgen._internal.picker import PickerFailed

        try:
            chosen = self.picker.choose()
        except PickerFailed as failure:
            response.send_json(500, {"error": str(failure)})
            return
        if chosen is None:
            response.send_json(200, {"cancelled": True})
        elif extension_of(chosen) not in VIEWER_EXTENSIONS:
            response.send_json(400, {"error": f"CAD opens {_CAD_EXTENSIONS} files; {os.path.basename(chosen)} is not one."})
        else:
            response.send_json(200, {"path": to_posix_path(os.path.abspath(chosen))})

    # --- usage stats (telemetry) --------------------------------------------

    def _consent(self, share=None, *, by=None) -> dict:
        """The app menu's Share anonymous usage data toggle: whether sharing is on and why, and, from the person's
        click, their answer, which changes it whenever. Nothing asks: telemetry is on by default once a
        ``cadgen`` command has said so (``cadgen/analytics.py``)."""
        from cadgen.analytics import PRIVACY_URL

        changed = self.analytics.choose(share, by=by or self.consent_by) if isinstance(share, bool) else None
        found = self.analytics.status()
        return {"sharing": found["sharing"], "reason": found["reason"], "policy": PRIVACY_URL,
                **({"saved": bool(changed.get("saved"))} if changed is not None else {})}

    def _version(self) -> dict:
        """The page's update button (``cadgen/updates.py``): whether a newer text-to-cad is out, from
        the feed as last read. A feed that is due is read in the background: the page never waits."""
        from cadgen import updates

        updates.refresh()
        return {"notice": updates.notice()}

    def _report_activity(self, payload: dict) -> None:
        """What the page did: a person touched it (``touched``), a Quick Edit was sent (``quickEdit``), used its
        controls (``controls``: each ``{control, count, seconds}``, a name of ``cadgen.analytics.CONTROLS`` and
        how often and how long, taken only as that), or the page crashed (``crash``: its signature, made by the
        page as ``cadgen.analytics.signature`` makes one, and taken only if it is one). Noted in memory, and sent
        only with consent. (A model it shows is counted when it joins the library: ``_change_recents``.)"""
        from cadgen.analytics import CONTROLS

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

    def _handle_drawing(self, request, response, query):
        """A ``.dxf`` flattened to 2D primitives (``drawings.py`` owns the rules).

        The payload is already JSON bytes, held in memory by the file's bytes,
        so it goes out through ``send_bytes`` rather than being decoded and
        re-encoded on the way past.
        """
        status, body = self.drawings.response(query.get("file") or "")
        if isinstance(body, bytes):
            response.send_bytes(status, body, "application/json; charset=utf-8")
            return
        response.send_json(status, body)

    def _handle_robot(self, request, response, query):
        """A robot description resolved for the page, or one of the primitive meshes cadgen made for
        it (``robots.py`` owns both rules). Real work on a miss -- the validators, the frame graph,
        meshing a shape -- so it is counted, as the drawing route is."""
        from .robots import robot_response

        status, body, content_type = robot_response(query.get("file") or "", query.get("mesh"))
        if isinstance(body, bytes):
            response.send_bytes(status, body, content_type, RAW_FILE_HEADERS if content_type.startswith("model/") else ())
            return
        response.send_json(status, body)

    def _handle_prompt_files_get(self, request, response, pathname, query):
        """Read a prompt JSON file; every request carries the viewer guard."""
        if not request.header(POST_GUARD_HEADER):
            response.send_json(403, {"ok": False, "error": f"missing {POST_GUARD_HEADER} header; send '{POST_GUARD_HEADER}: 1'"})
            return
        found = self.prompt_files.file(pathname[len("/__cad/prompt-files/"):])
        if found is None:
            response.send_json(404, {"ok": False, "error": "Not found"})
            return
        data, content_type = found
        response.send_bytes(200, data, content_type, RAW_FILE_HEADERS)

    def _handle_asset(self, request, response, query):
        """A CAD file's bytes, by absolute path. A 404 names the path and why: the page shows the
        sentence as the reason a model did not load (a robot's missing link mesh among them), and a
        bare "Not found" left nothing to fix."""
        ref = query.get("file") or ""
        candidate = asset_path(ref)
        if not candidate:
            response.send_json(404, {"error": f"{ref} is not a file the viewer sends: it sends CAD files "
                                              f"({_CAD_EXTENSIONS}) whose names are not hidden"})
            return
        try:
            stat_result = os.stat(candidate)
        except (OSError, ValueError):
            stat_result = None
        if stat_result is None or not stat.S_ISREG(stat_result.st_mode):
            response.send_json(404, {"error": f"No file at {candidate}"})
            return
        content_type = content_type_for_path(candidate)
        response.stream_file(candidate, stat_result, content_type, RAW_FILE_HEADERS)


def create_cad_app(*, host: str, port: int, dist_dir: str = "", start: str | None = None, identity: str | None = None) -> CadApp:
    return CadApp(host=host, port=port, dist_dir=dist_dir, start=start, identity=identity)
