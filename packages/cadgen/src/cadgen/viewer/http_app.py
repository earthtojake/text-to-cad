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

import os
import stat
import threading
import time
from pathlib import Path

from .backend import ForbiddenAssetError, LocalAssetBackend
from .cadgen_ops import create_cadgen_ops
from .content_types import content_type_for_static_asset
from .encoding import UriError, strict_decode_uri_component
from .scanner import path_relative
from .store_paths import store_packages_dir
from .tess_cache import read_tess_cache_batch, read_tess_cache_entry, write_tess_cache_entry

__all__ = [
    "CadApp",
    "ForbiddenAssetError",
    "POST_GUARD_HEADER",
    "LOCAL_SERVER_FEATURES",
    "hostname_only",
    "host_is_allowed",
    "read_viewer_version",
    "newest_mtime_ns",
    "identity_token",
    "create_cad_app",
]

POST_GUARD_HEADER = "x-cadgen-viewer"
LOCAL_SERVER_FEATURES = ["path-directory"]
_LOOPBACK_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})

TESS_CACHE_ROUTE_PREFIX = "/__tess_cache/"
TESS_CACHE_BATCH_PATH = "/__tess_cache/batch"

_PACKAGE_DIR = str(Path(__file__).resolve().parent)


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
    mtime salt does all the work.
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


def identity_token() -> str:
    """This code's identity: the cadgen version SALTED with its files' newest mtime.

    The daemon's shape (``compute_version_token`` in cadgen/daemon/client.py):
    ``<version>:<newest mtime_ns>``, over BOTH halves of the viewer — this
    package's ``.py`` files and the built client at its DEFAULT location
    (``cadgen.assets.viewer_dist_dir()``, never a ``--dist`` override: both
    sides of a reuse comparison must salt with the same directory, and the
    relauncher does not know what the resident was pointed at). The version
    alone is frozen between releases, so in a checkout it made reuse
    source-blind: a ``git pull`` followed by a launch reused a resident server
    running last week's code. The mtime salt ends that — a pull or rebuild
    changes the token, the resident's recorded token no longer matches, and a
    fresh instance starts. In an installed wheel the files never change after
    install, so the token is constant and behavior is exactly version-keyed
    reuse.

    Computed identically at announce time (``/__cad/server``), registry write,
    and the reuse probe — but the running server ANSWERS with the token it
    computed at its own start (held on ``CadApp``), never a re-read: a re-read
    would let a stale resident claim freshness after a pull.

    The walk covers ~20 server files and ~25 dist files: well under a
    millisecond, paid once per launch.
    """
    from cadgen import assets

    newest = max(
        newest_mtime_ns(Path(__file__).resolve().parent, suffix=".py"),
        newest_mtime_ns(assets.viewer_dist_dir()),
    )
    return f"{read_viewer_version()}:{newest}"


def _is_ascii_digits(value: str) -> bool:
    """JS ``/^\\d+$/``: ASCII only.

    ``str.isdigit()`` is Unicode-aware and would treat ``[::1]:٢`` as a port.
    """
    return bool(value) and value.isascii() and value.isdigit()


class CadApp:
    """``handle(request, response)`` writes exactly one response.

    Unlike the Node app there is no "not mine" return: the Python server always
    serves the client itself, and the dev proxy forwards only the two API
    prefixes, so nothing else can be waiting behind this.
    """

    def __init__(self, *, root: str, host: str, port: int, dist_dir: str = ""):
        self.backend = LocalAssetBackend(root)
        root_path = self.backend.root_path
        self.root_path = root_path
        self.root_name = self.backend.root_name
        self.host = host
        self.port = port
        # dist_dir is compared as a string prefix, so resolve it ONCE here and
        # never re-resolve at request time.
        self.dist_dir = os.path.abspath(dist_dir) if dist_dir else ""
        self.viewer_version = read_viewer_version()
        # Computed ONCE, at start: the identity this instance announces and
        # registers is the identity of the code it is actually running.
        self.identity_token = identity_token()
        self.started_at = time.time()
        self.lock = threading.Lock()
        self.ops = create_cadgen_ops(root_path)

    # --- server info ------------------------------------------------------

    def server_info(self) -> dict:
        return {
            "app": "cad-viewer",
            "viewerVersion": self.viewer_version,
            # The start-time token, NOT identity_token() re-evaluated: a
            # resident answering a reuse probe must report the code it runs,
            # not the code now on disk.
            "identityToken": self.identity_token,
            "serverMode": "serve",
            "serverFeatures": LOCAL_SERVER_FEATURES,
            "backend": "local-fs",
            # path.resolve(), NOT realpath: the launcher's registry and the
            # client both compare the spelling the operator gave.
            "rootPath": self.root_path,
            "rootName": self.root_name,
            "port": self.port,
            "pid": os.getpid(),
            # The viewer is a static visualization tool: it never runs
            # generators or exports. The CLIs own those; this stays false.
            "stepArtifactGenerationAvailable": False,
            "packageDir": _PACKAGE_DIR,
            "startedAt": self.started_at,
            "url": f"http://{self.host}:{self.port}",
        }

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
                    self._handle_catalog(request, response)
                elif pathname == "/__cad/artifact":
                    self._handle_artifact_status(request, response, query)
                elif pathname == "/__cad/store":
                    self._handle_store_asset(request, response, query)
                elif pathname == "/__cad/asset":
                    self._handle_asset(request, response, query)
                else:
                    # An unrecognised /__cad/* path is a bad API call, not a
                    # page. Falling through to the SPA answered typo'd and
                    # retired routes with index.html at 200, so a client doing
                    # res.json() got an HTML parse error instead of a status.
                    response.send_json(404, {"error": "Not found"})
            except ForbiddenAssetError:
                response.send_json(403, {"error": "Forbidden"})
            except Exception as error:  # noqa: BLE001
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
                elif pathname == TESS_CACHE_BATCH_PATH:
                    # Matched BEFORE the prefix branch: /__tess_cache/batch
                    # matches both.
                    self._handle_tess_batch(request, response)
                elif pathname.startswith(TESS_CACHE_ROUTE_PREFIX):
                    self._handle_tess_post(request, response)
                else:
                    response.send_empty(405, [("allow", "POST")])
            except ForbiddenAssetError:
                response.send_json(403, {"error": "Forbidden"})
            except Exception as error:  # noqa: BLE001
                # Note the asymmetry with the GET funnel: this one carries
                # ok:false and that one does not.
                response.send_json(400, {"ok": False, "error": str(error)})
            return

        # Unreachable: handler.py answers 405 for every other method before
        # dispatch ever runs.
        response.send_empty(405, [("allow", "GET, HEAD, POST")])

    # --- placeholders filled by later steps of the port -------------------

    def _handle_catalog(self, request, response):
        response.send_json(200, self.backend.read_catalog())

    def _entry_ref_for_status(self, file_ref, catalog=None) -> str:
        """The catalog URL for this ref, or ``""``.

        A full catalog scan unless the caller hands one in, and the client polls
        the status route every 400ms during a build. The scanner's content-hash
        memo is what keeps it off the hot path; without that this would re-read
        every model in the root per tick.
        """
        if catalog is None:
            catalog = self.backend.read_catalog()
        entry = self.backend.catalog_entry_for_file_ref(catalog, file_ref)
        return str((entry or {}).get("url") or "")

    def _handle_artifact_status(self, request, response, query):
        """Always 200, even for state 'error'.

        The status of an artifact is information, not an outcome: a client
        polling for a badge should read the state out of the body, not out of
        an HTTP failure it has to special-case.
        """
        file_ref = query.get("file") or ""
        status = self.ops.artifact_status(file_ref)
        response.send_json(200, {**status, "ref": self._entry_ref_for_status(file_ref)})

    def _handle_artifact_build(self, request, response, query):
        """``ref`` and ``catalog`` both come from ONE post-build scan.

        The Node backend scanned twice and disagreed with itself: ``ref`` came
        from a scan taken BEFORE the build and ``catalog`` from one taken after,
        so a cold import answered with a ref pointing at the pre-import URL —
        no ``&v=`` cache-buster — while the catalog it shipped in the same body
        carried the post-import one. DECIDED, deliberately, to keep the port's
        post-build ref rather than restore that: the import is precisely the
        event that changes this entry's URL, and two fields of one payload
        describing two different moments is a bug that happened to be
        unobserved (no client reads ``ref`` today) rather than a contract.

        Folding both onto a single scan is the other half of the decision. Node
        paid for two full directory walks per build POST; this pays for one, and
        it is the one that makes the two fields agree by construction rather
        than by care.
        """
        file_ref = query.get("file") or ""
        # Only the literal string "1" forces; anything else is a normal build.
        result = self.ops.build_artifact(file_ref, force=query.get("force") == "1")
        # Scanned AFTER the build, success or failure, and republished by the
        # client — the import is precisely the event that changes what the
        # catalog says about this entry.
        catalog = self.backend.read_catalog()
        payload = {
            **result,
            "ref": self._entry_ref_for_status(file_ref, catalog),
            "catalog": catalog,
        }
        response.send_json(500 if result.get("ok") is False else 200, payload)

    def _handle_store_asset(self, request, response, query):
        """Render-package assets, confined to the store's ``packages/`` tier.

        Everything that fails here is 404, never 403: the containment failure is
        folded into "there is no stat" rather than raised. Leading slashes are
        STRIPPED because the client's resolvePackageAssetUrl emits
        ``file=/<key>/components/c0.surf``; that also means ``file=/etc/hosts``
        resolves under the tier and 404s rather than reading /etc/hosts.
        """
        rel = str(query.get("file") or "").replace("\\", "/")
        base = os.path.abspath(store_packages_dir())
        candidate = os.path.abspath(os.path.join(base, rel.lstrip("/")))
        contained = candidate == base or candidate.startswith(base + os.sep)
        hidden = any(
            part and part != ".." and part.startswith(".")
            for part in path_relative(base, candidate).split(os.sep)
        )
        stat_result = None
        if contained and not hidden:
            try:
                stat_result = os.stat(candidate)
            except (OSError, ValueError):
                stat_result = None
        # One stat answers both existence and regular-ness; re-statting would
        # open a window where the two disagree.
        if stat_result is None or not stat.S_ISREG(stat_result.st_mode):
            response.send_json(404, {"error": "Not found"})
            return
        content_type = self.backend.content_type_for_path(candidate) or "application/octet-stream"
        response.stream_file(candidate, stat_result, content_type)

    def _handle_asset(self, request, response, query):
        candidate = self.backend.asset_path_for_file_ref(query.get("file") or "")
        stat_result = None
        if candidate:
            try:
                stat_result = os.stat(candidate)
            except (OSError, ValueError):
                stat_result = None
        if not candidate or stat_result is None or not stat.S_ISREG(stat_result.st_mode):
            response.send_json(404, {"error": "Not found"})
            return
        content_type = self.backend.content_type_for_path(candidate) or "application/octet-stream"
        response.stream_file(candidate, stat_result, content_type)

    def _handle_tess_get(self, request, response):
        """403 refused name, 404 miss, 200 hit.

        The non-200 answers carry ONLY content-length: 0 — no content-type and
        no cache-control. A miss is an ordinary outcome here, not an error page.
        """
        status, body = read_tess_cache_entry(request.path)
        if status != 200:
            response.send_empty(status)
            return
        response.send_bytes(200, body, "application/octet-stream")

    def _handle_tess_post(self, request, response):
        response.send_empty(write_tess_cache_entry(request.path, request.body()))

    def _handle_tess_batch(self, request, response):
        """One round trip for a whole assembly's hit set.

        A non-ok answer here permanently demotes the client's provider to
        per-key GETs for the life of the page, so a malformed request must be a
        clean 400 and everything else must be a valid container — misses
        included, which ride as zero-length entries rather than errors.
        """
        container = read_tess_cache_batch(request.body())
        if container is None:
            response.send_json(400, {"error": "bad batch request"})
            return
        response.send_bytes(200, container, "application/octet-stream")


def create_cad_app(*, root: str, host: str, port: int, dist_dir: str = "") -> CadApp:
    return CadApp(root=root, host=host, port=port, dist_dir=dist_dir)
