"""The HTTP contract: both browser gates, route dispatch, and the SPA.

Security / trust model, unchanged from the Node backend: the server binds
loopback and serves UNAUTHENTICATED — the loopback bind is the trust boundary
against other processes and machines. Loopback is NOT a boundary against the
user's own browser, so two gates defend against that specifically:

* Host validation refuses a request whose Host names anything but
  127.0.0.1/localhost/::1 — the DNS-rebinding case, where an attacker domain
  re-resolves to loopback and the browser treats us as same-origin. Skipped when
  bound non-loopback, matching Jupyter's ``allow_remote_access``.
* Every POST requires an ``x-cadgen-viewer`` header. ``POST /__cad/artifact``
  compiles the target, and since all params ride the query string with no body,
  a cross-origin POST is otherwise a no-preflight "simple request". A custom
  header forces a preflight instead.

No ``Access-Control-*`` headers are served, deliberately: their absence is what
makes the same-origin policy block cross-origin reads and what makes that
preflight fail. Do not add them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import threading
from pathlib import Path

from . import reload as dev_reload
from .backend import absolute_path, asset_path
from .cadgen_ops import CadgenOps
from .content_types import content_type_for_path, content_type_for_static_asset, extension_of
from .encoding import UriError, strict_decode_uri_component
from .scanner import CAD_CATALOG_SCHEMA_VERSION, SOURCE_EXTENSIONS, catalog_entry, to_posix_path
from .store_paths import virtual_store_asset
from .tess_cache import (
    TESS_CACHE_METADATA_MAX_BYTES, parse_tess_cache_admission,
    read_tess_cache_batch, read_tess_cache_entry, read_tess_cache_probe, write_tess_cache_entry,
)

__all__ = [
    "CadApp",
    "POST_GUARD_HEADER",
    "hostname_only",
    "host_is_allowed",
    "read_viewer_version",
    "newest_mtime_ns",
    "identity_token",
    "os_user",
    "create_cad_app",
]

POST_GUARD_HEADER = "x-cadgen-viewer"
# A thumbnail travels as base64 in the change's JSON: 512 KiB of PNG, and room for the rest.
_LIBRARY_BODY_LIMIT = 768 * 1024
# A thumbnail's name is its content's (``recents.RecentStore.thumbnail``): nothing else is read.
_THUMBNAIL_NAME = re.compile(r"[0-9a-f]{32}\.png")
_CAD_EXTENSIONS = ", ".join(sorted(SOURCE_EXTENSIONS))
_LOOPBACK_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})

TESS_CACHE_ROUTE_PREFIX = "/__tess_cache/"
TESS_CACHE_BATCH_PATH = "/__tess_cache/batch"
TESS_CACHE_PROBE_PATH = "/__tess_cache/probe"

# Routes that do NOT hold the development auto-reload back (``reload.py``).
# `/__cad/server` is what the browser's own reload watcher polls — counting it
# would let that watcher defer the very restart it is waiting for — and the
# other two PARK, waiting on the daemon's ledger or a pooled derivation rather
# than doing work. Interrupting a parked poll costs the client one re-poll
# after it reloads; interrupting a compile would cost a build, which is why
# every other route, `POST /__cad/artifact` above all, is counted.
_UNCOUNTED_ROUTES = frozenset({"/__cad/server", "/__cad/preview", "/__cad/surfaces", "/__cad/surfaces/cancel",
                               "/__cad/analytics", "/__cad/analytics/activity", "/__cad/version"})


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

    One half of the launcher's reuse key (see ``identity_token``): both sides
    of that comparison must read the version the same way. Metadata, not
    ``cadgen.__version__``: the reuse probe runs in a launcher that has not
    imported anything heavy, and ``.dist-info`` is what an installed wheel
    carries. ``""`` is a source tree on ``PYTHONPATH`` with no install behind
    it, which is how this repo's own test runners supply cadgen -- there the
    runtime digest does all the work.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return str(version("cadgen") or "")
    except PackageNotFoundError:
        return ""
    except Exception:  # noqa: BLE001 - a metadata read that fails tells us nothing
        return ""


def newest_mtime_ns(base_dir, *, suffix: str = "") -> int:
    """The newest ``st_mtime_ns`` under ``base_dir`` (``suffix``-filtered), 0 when empty.

    ``__pycache__`` is skipped — a byte-identical tree must not read newer
    because an interpreter recompiled it. Unreadable files count as absent:
    a freshness signal must never stop a viewer from starting.
    """
    newest = 0
    for dirpath, dirnames, filenames in os.walk(base_dir):
        dirnames[:] = [name for name in dirnames if name != "__pycache__"]
        for filename in filenames:
            if suffix and not filename.endswith(suffix):
                continue
            try:
                mtime = os.stat(os.path.join(dirpath, filename)).st_mtime_ns
            except OSError:
                continue
            newest = max(newest, mtime)
    return newest


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

    Computed ONCE per launch, on both sides of the launcher's reuse comparison,
    and never re-read by a running server. Whether a running server's code has
    since changed is a separate question with a separate answer — and it is
    asked only in a source checkout, by ``reload.py``.

    The Viewer imports cadgen runtime modules outside ``cadgen.viewer`` — in
    particular the daemon client, transport and store. Fingerprinting only the
    viewer package let an old resident survive changes to those modules while
    serving a newly rebuilt browser client. The token therefore covers every
    Python file in the installed cadgen package, the Viewer's data table, and
    the exact dist directory selected by this launch (including its realpath).

    Content, rather than the newest mtime, is the identity. This catches any
    changed member even when another file has a later timestamp, and does not
    restart a correct server after a byte-identical rebuild.
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
    account name on Windows. A launch reuses, replaces or stops only a viewer that names its own."""
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


def _working_folder() -> str:
    """The folder this process runs in, or the home folder once that one has been deleted."""
    try:
        return os.getcwd()
    except OSError:
        return os.path.expanduser("~")


class CadApp:
    """``handle(request, response)`` writes exactly one response.

    Unlike the Node app there is no "not mine" return: the Python server always
    serves the client itself, and the dev proxy forwards only the two API
    prefixes, so nothing else can be waiting behind this.

    One app serves every file on this machine, by absolute path (``backend``). ``start`` is the
    folder it was started in (the working folder by default): the page resolves a developer's
    relative ``?file=`` against it, and it bounds nothing.
    """

    def __init__(self, *, host: str, port: int, dist_dir: str = "", start: str | None = None, identity: str | None = None):
        from cadgen._internal.picker import available

        from .drawings import DrawingRenders
        from .surfaces import SurfaceSubscribers
        from .warm import CatalogWarmer

        self.surface_subscribers = SurfaceSubscribers()
        # The drawing route's renders, off the request and one per drawing (``drawings.py``).
        self.drawings = DrawingRenders(on_crash=lambda error: self._crashed(error, bugs_only=True))
        # What a watched build saves, its catalog row computed before a read asks (``warm.py``).
        self.catalog_warm = CatalogWarmer()
        self.start = to_posix_path(os.path.abspath(start if start is not None else _working_folder()))
        # Whether this computer has a file chooser for the home's Open (``POST /__cad/pick``).
        self.pick = available()
        self.host = host
        self.port = port
        # dist_dir is compared as a string prefix, so resolve it ONCE here and
        # never re-resolve at request time.
        self.dist_dir = os.path.abspath(dist_dir) if dist_dir else ""
        self.viewer_version = read_viewer_version()
        # Computed ONCE, at start (or handed in by the launcher, which computed it to ask the port):
        # the identity this instance announces is the identity of the code it is actually running.
        self.identity_token = identity if identity is not None else identity_token(self.dist_dir)
        # The single development predicate (reload.py). In an installed wheel
        # this is False and the whole mechanism is absent: nothing is watched,
        # no request is counted, and the browser never polls for a restart.
        self.auto_reload = dev_reload.running_from_source_checkout()
        self._request_lock = threading.Lock()
        self._busy_requests = 0
        self.ops = CadgenOps()
        self._recents = None
        self._picker = None
        # What ``POST /__cad/shutdown`` calls, after it answers: the `cadgen viewer` process's own
        # shutdown (``main.py``). An app with none -- the CAD app's tunnel builds them -- has no
        # such route.
        self.on_shutdown = None
        # Anonymous usage analytics (``cadgen/analytics.py``): the `cadgen viewer` process attaches
        # its recorder here (``main.py``), and the CAD app's server its own to the app its tunnel
        # builds. ``consent_by`` says, with a person's answer, which of them asked.
        self.analytics = None
        self.consent_by = "viewer"

    # --- development auto-reload accounting -------------------------------

    def busy_requests(self) -> int:
        """Requests in flight that a restart would interrupt (see ``_UNCOUNTED_ROUTES``)."""
        with self._request_lock:
            return self._busy_requests

    def restart_is_safe(self) -> bool:
        """``SourceReloader``'s idle gate: nothing this restart would destroy -- no request
        in flight, no compile the build route started and left running, and no drawing it is
        rendering."""
        return self.busy_requests() == 0 and not self.ops.client.any_in_flight() and not self.drawings.any_in_flight()

    # --- server info ------------------------------------------------------

    def server_info(self) -> dict:
        return {
            "app": "cad-viewer",
            # The start-time token, NOT identity_token() re-evaluated: a
            # resident answering a reuse probe must report the code it runs,
            # not the code now on disk. It is also what the browser's
            # development reload watcher compares against to notice that this
            # server has become a NEW process on the same port.
            "identityToken": self.identity_token,
            # Whether this server watches its own code and restarts itself.
            # False in every installed wheel; the client polls only when true.
            "autoReload": self.auto_reload,
            # Which file manager Reveal opens: darwin, win32 or linux.
            "platform": sys.platform if sys.platform in ("darwin", "win32") else "linux",
            # Whose viewer this is: a launch reuses, replaces or stops only its own user's.
            "user": os_user(),
            # Where a developer's relative ?file= resolves, in the page. Not a boundary.
            "start": self.start,
            "pick": self.pick,
            "port": self.port,
            "pid": os.getpid(),
        }

    def read_catalog(self, file=None) -> dict:
        """The catalog of ``file``, an absolute path: its row, or none when it has none (or no file
        is named), and its revision -- a digest of the entries, which a client that only watches for
        change compares instead of reading the catalog again."""
        entry = catalog_entry(absolute_path(file)) if file else None
        entries = [entry] if entry else []
        return {"schemaVersion": CAD_CATALOG_SCHEMA_VERSION, "entries": entries, "revision": catalog_revision(entries)}

    def build_status(self, file, *, after=None) -> dict:
        """What a build of ``file`` (a STEP's absolute path) is doing (``GET /__cad/preview``,
        ``preview.py``). The file its builds have saved has its catalog row started on a thread
        meanwhile (``warm.py``), so the catalog read that follows the build finds it."""
        from .preview import preview_update

        return preview_update(file, after=after, on_saved=self.catalog_warm.saved)

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
        response.stream_file(file_path, stat_result, content_type or "")
        return True

    def _serve_dist(self, request, response) -> None:
        """Static dist + SPA fallback.

        The page lives at ``/`` and nothing else here is a directory, so this is
        an ordinary static server: serve the file if the bundle has it,
        otherwise fall back to index.html — EXCEPT under ``/assets/``, where a
        miss must be a 404 rather than HTML, or a stale hashed bundle reference
        turns into an ES-module parse error instead of a readable status. The
        drawing editor's fonts under ``/excalidraw/`` are the same: a family the
        bundle leaves out must read as missing, not as an HTML "font".
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
        if request_path.startswith(("/assets/", "/excalidraw/")):
            response.send_plain(404, "Not found")
            return
        index_html = os.path.join(self.dist_dir, "index.html")
        if not self._serve_file(response, index_html, content_type_for_static_asset(index_html)):
            response.send_plain(404, "Not found")

    # --- dispatch ---------------------------------------------------------

    def handle(self, request, response) -> None:
        """Count the request, then dispatch it.

        The counting exists only for the development auto-reload, so an
        installed wheel takes no lock and keeps no counter: ``auto_reload`` is
        False there and this is a straight call.
        """
        try:
            if not self.auto_reload or request.path in _UNCOUNTED_ROUTES:
                self._dispatch(request, response)
                return
            with self._request_lock:
                self._busy_requests += 1
            try:
                self._dispatch(request, response)
            finally:
                with self._request_lock:
                    self._busy_requests -= 1
        except (BrokenPipeError, ConnectionResetError):
            raise  # the page left: no crash of ours
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
            if pathname.startswith(TESS_CACHE_ROUTE_PREFIX):
                # Shared component-tessellation cache. Checked BEFORE the dist
                # fallthrough: this is an API family, not a page asset.
                self._handle_tess_get(request, response)
                return
            if not pathname.startswith("/__cad/"):
                # Note "/__cad" without the trailing slash is NOT an API path
                # and falls through to the SPA at 200, while "/__cad/" is and
                # answers 404 JSON. Both are the shipped behaviour.
                self._serve_dist(request, response)
                return
            try:
                if pathname == "/__cad/server":
                    response.send_json(200, self.server_info())
                elif pathname == "/__cad/catalog":
                    response.send_json(200, self.read_catalog(query.get("file")))
                elif pathname in ("/__cad/folder", "/__cad/search"):
                    self._handle_folder(response, pathname, query)
                elif pathname == "/__cad/recents":
                    response.send_json(200, self._recents_payload())
                elif pathname == "/__cad/thumbnail":
                    self._handle_thumbnail(response, query)
                elif pathname == "/__cad/artifact":
                    # Always 200, even for state 'failed': the status of an artifact is information,
                    # not an outcome, so a client polling for a badge reads it out of the body.
                    response.send_json(200, self.ops.artifact_status(query.get("file") or ""))
                elif pathname == "/__cad/preview":
                    response.send_json(200, self.build_status(query.get("file") or "", after=query.get("after")))
                elif pathname == "/__cad/drawing":
                    self._handle_drawing(request, response, query)
                elif pathname == "/__cad/store":
                    self._handle_store_asset(request, response, query)
                elif pathname == "/__cad/asset":
                    self._handle_asset(request, response, query)
                elif pathname == "/__cad/analytics" and self.analytics is not None:
                    response.send_json(200, self._consent())
                elif pathname == "/__cad/features":
                    from cadgen import features

                    response.send_json(200, features.read())
                elif pathname == "/__cad/version":
                    response.send_json(200, self._version())
                else:
                    # An unrecognised /__cad/* path is a bad API call, not a
                    # page. Falling through to the SPA answered typo'd and
                    # retired routes with index.html at 200, so a client doing
                    # res.json() got an HTML parse error instead of a status.
                    response.send_json(404, {"error": "Not found"})
            except Exception as error:  # noqa: BLE001
                self._crashed(error, bugs_only=True)  # a bad request is the caller's; a mistake in our code is a crash
                response.send_json(400, {"error": str(error)})
            return

        if method == "POST":
            # Gated before dispatch, not per route, so a POST route added later
            # is covered by construction.
            if self._rejected_by_host_check(request, response):
                return
            if self._rejected_as_cross_site_post(request, response):
                return
            try:
                if pathname == "/__cad/artifact":
                    self._handle_artifact_build(request, response, query)
                elif pathname in ("/__cad/analytics", "/__cad/analytics/activity") and self.analytics is not None:
                    # A page's crash report carries its frames (``_report_activity``): room for them, and no more.
                    if int(request.headers.get("content-length") or 0) > (16384 if pathname.endswith("/activity") else 4096):
                        response.send_empty(413, [("connection", "close")])
                        return
                    payload = json.loads(request.body() or b"{}")
                    if type(payload) is not dict:
                        raise ValueError("an analytics request is an object")
                    if pathname == "/__cad/analytics":
                        response.send_json(200, self._consent(payload.get("share")))
                    else:
                        self._report_activity(payload)
                        response.send_empty(204)
                elif pathname == "/__cad/features":
                    # The app menu's features: the person's choices, one for every CAD view (``cadgen/features.py``).
                    from cadgen import features

                    if int(request.headers.get("content-length") or 0) > 4096:
                        response.send_empty(413, [("connection", "close")])
                        return
                    response.send_json(200, features.change(json.loads(request.body() or b"{}")))
                elif pathname == "/__cad/recents":
                    if int(request.headers.get("content-length") or 0) > _LIBRARY_BODY_LIMIT:
                        response.send_empty(413, [("connection", "close")])
                        return
                    response.send_json(200, self._change_recents(json.loads(request.body())))
                elif pathname == "/__cad/pick":
                    self._handle_pick(response)
                elif pathname == "/__cad/shutdown" and self.on_shutdown is not None:
                    # A newer launch replacing this viewer, or `cadgen viewer stop`: answered, then
                    # the server stops and gives its port up (``main.py``).
                    response.send_json(202, {"ok": True})
                    self.on_shutdown()
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
                elif pathname == "/__cad/sketches":
                    # A Quick Edit's sketch, saved for a copied prompt to name (`sketches.py`).
                    from .sketches import MAX_PNG_BYTES as MAX_SKETCH_BYTES, save_sketch
                    if int(request.headers.get("content-length") or 0) > MAX_SKETCH_BYTES:
                        response.send_empty(413, [("connection", "close")])
                        return
                    response.send_json(200, {"ok": True, "path": save_sketch(request.body(), str(query.get("name") or ""))})
                elif pathname == "/__cad/surfaces":
                    if int(request.headers.get("content-length") or 0) > 128 * 1024:
                        response.send_empty(413, [("connection", "close")])
                        return
                    response.send_json(200, self.surface_subscribers.resolve(request.body()))
                elif pathname == "/__cad/surfaces/cancel":
                    if int(request.headers.get("content-length") or 0) > 128 * 1024:
                        response.send_empty(413, [("connection", "close")])
                        return
                    payload = json.loads(request.body())
                    if type(payload) is not dict or set(payload) != {"job"} or type(payload["job"]) is not str:
                        raise ValueError("surface cancellation requires a subscriber token")
                    self.surface_subscribers.cancel(payload["job"])
                    response.send_empty(204)
                elif pathname == TESS_CACHE_PROBE_PATH:
                    self._handle_tess_probe(request, response)
                elif pathname == TESS_CACHE_BATCH_PATH:
                    # Matched BEFORE the prefix branch: /__tess_cache/batch
                    # matches both.
                    self._handle_tess_batch(request, response)
                elif pathname.startswith(TESS_CACHE_ROUTE_PREFIX):
                    self._handle_tess_post(request, response)
                else:
                    response.send_empty(405, [("allow", "POST")])
            except Exception as error:  # noqa: BLE001
                self._crashed(error, bugs_only=True)  # a bad request is the caller's; a mistake in our code is a crash
                # Note the asymmetry with the GET funnel: this one carries
                # ok:false and that one does not.
                response.send_json(400, {"ok": False, "error": str(error)})
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
        return {"recents": [entry.public() for entry in self.recents.list()]}

    def _change_recents(self, payload) -> dict:
        """A change to the library -- ``{action, path, png?}``, the model by its absolute path --
        answered with the library as it now is. A model opened is also counted for analytics."""
        from .recents import thumbnail_png

        if type(payload) is not dict:
            raise ValueError("a recents change is {action, path}")
        action, path = payload.get("action"), absolute_path(payload.get("path"))
        if action == "open":
            if extension_of(path) not in SOURCE_EXTENSIONS or not os.path.isfile(path):
                raise ValueError(f"no CAD file at {path}")
            self.recents.opened(path)
            if self.analytics is not None:
                self.analytics.opened(path)
        elif action in ("pin", "unpin"):
            self.recents.pin(path, action == "pin")
        elif action == "remove":
            self.recents.remove(path)
        elif action == "thumbnail":
            self.recents.thumbnail(path, thumbnail_png(payload.get("png")))
        else:
            raise ValueError(f"unknown recents action {action!r}")
        return self._recents_payload()

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
        elif extension_of(chosen) not in SOURCE_EXTENSIONS:
            response.send_json(400, {"error": f"CAD opens {_CAD_EXTENSIONS} files; {os.path.basename(chosen)} is not one."})
        else:
            response.send_json(200, {"path": to_posix_path(os.path.abspath(chosen))})

    # --- usage stats (telemetry) --------------------------------------------

    def _consent(self, share=None) -> dict:
        """The app menu's Share usage stats toggle: whether sharing is on and why, and, from the person's
        click, their answer, which changes it whenever. Nothing asks: telemetry is on by default once a
        ``cadgen`` command has said so (``cadgen/analytics.py``)."""
        from cadgen.analytics import PRIVACY_URL

        if isinstance(share, bool):
            self.analytics.choose(share, by=self.consent_by)
        found = self.analytics.status()
        return {"sharing": found["sharing"], "reason": found["reason"], "policy": PRIVACY_URL}

    def _version(self) -> dict:
        """The page's update button (``cadgen/updates.py``): whether a newer text-to-cad is out, from
        the feed as last read. A feed that is due is read in the background: the page never waits."""
        from cadgen import updates

        updates.refresh()
        return {"notice": updates.notice()}

    def _report_activity(self, payload: dict) -> None:
        """What the page did: a person touched it (``touched``), a Quick Edit was sent (``quickEdit``), or
        the page crashed (``crash``: its signature, made by the page as ``cadgen.analytics.signature``
        makes one, and taken only if it is one). Noted in memory, and sent only with consent. (A model it
        shows is counted when it joins the library: ``_change_recents``.)"""
        if payload.get("touched") is True:
            self.analytics.viewed()
        if payload.get("quickEdit") is True:
            self.analytics.used("quick_edit")
        crash = payload.get("crash")
        if isinstance(crash, dict) and crash.get("where") == "page":
            self.analytics.crashed(crash)

    # --- routes ----------------------------------------------------------

    def _handle_artifact_build(self, request, response, query):
        """Start the document's compile and answer at once.

        The compile is a job in the pool; this request is never held for its
        length (a host relaying requests through a few shared slots would lose
        one for that long). The answer is ``compiling``, and the client follows
        the job through the status route -- its progress, then ``compiled``, or
        ``failed`` with the job's own reason -- and reads the catalog again when it
        ends. An entry that needs no compile answers ``compiled`` at once.
        """
        file_ref = query.get("file") or ""
        # Only the literal string "1" forces; anything else is a normal build.
        result = self.ops.build_artifact(file_ref, force=query.get("force") == "1")
        response.send_json(500 if result.get("ok") is False else 200, result)

    def _handle_store_asset(self, request, response, query):
        """A tree served as if it were a directory: ``<tree>/assembly.json`` is
        the flattened tree, ``<tree>/components/<object>.surf`` streams the
        object. Nothing here touches a path the client names: the ``file``
        param is parsed into (tree hash, object hash) and each is looked up by
        HASH in the store, so ``file=/etc/hosts`` is simply not a tree.

        Everything that fails is 404, never 403. Leading slashes are STRIPPED
        because the client's resolvePackageAssetUrl emits
        ``file=/<tree>/components/<object>.surf``.
        """
        rel = str(query.get("file") or "").replace("\\", "/").lstrip("/")
        if query.get("surfaceInput") is not None or query.get("object") is not None:
            from .surfaces import pinned_surface_object

            payload = pinned_surface_object(query.get("tree"), query.get("surfaceInput"), query.get("object"))
            content_type = "application/octet-stream"
        else:
            producer = json.loads(query.get("surfaceProducer")) if query.get("surfaceProducer") else None
            payload, content_type = virtual_store_asset(
                rel, producer=producer, document_hash=query.get("documentHash"),
            )
        if payload is None:
            response.send_json(404, {"error": "Not found"})
            return
        if isinstance(payload, bytes):
            response.send_bytes(200, payload, content_type, RAW_FILE_HEADERS)
            return
        try:
            stat_result = os.stat(payload)
        except (OSError, ValueError):
            response.send_json(404, {"error": "Not found"})
            return
        response.stream_file(str(payload), stat_result, content_type, RAW_FILE_HEADERS)

    def _handle_drawing(self, request, response, query):
        """A ``.dxf`` flattened to 2D primitives (``drawings.py`` owns the rules).

        NOT in ``_UNCOUNTED_ROUTES``: that set is for polls and parked waits,
        and this one starts real work — a render that a development restart
        would throw away, exactly like a compile (``restart_is_safe`` waits
        for it as well).

        The payload is already JSON bytes from the store's ``drawing`` index,
        so it goes out through ``send_bytes`` rather than being decoded and
        re-encoded on the way past.
        """
        status, body = self.drawings.response(query.get("file") or "")
        if isinstance(body, bytes):
            response.send_bytes(status, body, "application/json; charset=utf-8")
            return
        response.send_json(status, body)

    def _handle_asset(self, request, response, query):
        candidate = asset_path(query.get("file") or "")
        stat_result = None
        if candidate:
            try:
                stat_result = os.stat(candidate)
            except (OSError, ValueError):
                stat_result = None
        if not candidate or stat_result is None or not stat.S_ISREG(stat_result.st_mode):
            response.send_json(404, {"error": "Not found"})
            return
        content_type = content_type_for_path(candidate)
        response.stream_file(candidate, stat_result, content_type, RAW_FILE_HEADERS)

    def _handle_tess_get(self, request, response):
        """403 refused name, 404 miss, 200 hit.

        The non-200 answers carry ONLY content-length: 0 — no content-type and
        no cache-control. A miss is an ordinary outcome here, not an error page.
        """
        query = request.query
        try:
            digest, limit = parse_tess_cache_admission(query.get("object"), query.get("maxBytes"))
        except (TypeError, ValueError):
            response.send_empty(400)
            return
        status, body = read_tess_cache_entry(request.path, expected_object=digest, max_bytes=limit)
        if status != 200:
            response.send_empty(status)
            return
        response.send_bytes(200, body, "application/octet-stream")

    def _handle_tess_post(self, request, response):
        response.send_empty(write_tess_cache_entry(request.path, request.body()))

    def _handle_tess_probe(self, request, response):
        if int(request.headers.get("content-length") or 0) > TESS_CACHE_METADATA_MAX_BYTES:
            response.send_empty(413, [("connection", "close")])
            return
        result = read_tess_cache_probe(request.body())
        if result is None:
            response.send_json(400, {"error": "bad tessellation probe request"})
            return
        response.send_json(200, result)

    def _handle_tess_batch(self, request, response):
        """One round trip for a whole assembly's hit set.

        A non-ok answer here permanently demotes the client's provider to
        per-key GETs for the life of the page, so a malformed request must be a
        clean 400 and everything else must be a valid container — misses
        included, which ride as zero-length entries rather than errors.
        """
        if int(request.headers.get("content-length") or 0) > TESS_CACHE_METADATA_MAX_BYTES:
            response.send_empty(413, [("connection", "close")])
            return
        container = read_tess_cache_batch(request.body())
        if container is None:
            response.send_json(400, {"error": "bad batch request"})
            return
        response.send_bytes(200, container, "application/octet-stream")


def create_cad_app(*, host: str, port: int, dist_dir: str = "", start: str | None = None, identity: str | None = None) -> CadApp:
    return CadApp(host=host, port=port, dist_dir=dist_dir, start=start, identity=identity)
