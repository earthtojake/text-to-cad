"""The CAD Viewer's HTTP routes, served in-process for a view with no network.

A view sends exactly the requests the web client sends (``/__cad/*``,
``/__tess_cache/*``) as tool calls; this module hands each one to the viewer's
own router -- one :class:`~cadgen.viewer.http_app.CadApp`, made on the first
request, for every view of this server -- and returns the status, headers and
body bytes. There is one backend, not two: the router, its checks and its limits
are the ones the web app uses, the model library, the home's Open, Reveal, the
person's analytics answer and features, and the update check included. The app
keeps the server's own library and analytics, so a model a view opens is
counted once, by this process.

A body travels base64 inside the host's JSON, and a JSON body of more than
``GZIP_JSON_MIN_BYTES`` travels gzipped as well, flagged ``encoding: "gzip"``: the
page inflates it before the client sees it, and the headers describe the inflated
body. A large model's descriptor is 1.43 MB of base64 as it is and 0.28 MB gzipped,
for about 5 ms of level-1 compression. Binary bodies (tessellations, SURF objects)
barely shrink, so they travel as they are.

A reply is one message on the host's channel, and a host reads that channel with
a ceiling on one message: past it, the connection closes, and this process and
every view on it end. So no reply carries more than ``MAX_REPLY_BYTES`` of body.
The page asks for every GET as a byte range of at most that (``Range``), and a
longer body answers with its first part, ``content-range`` and an ``etag``
(``cadgen.viewer.response``): the page reads the rest a range at a time, from
the same body. Any reply still longer is not sent: that request fails (502).

A long body is produced once. The reply carrying its first part keeps the whole
of it, and the page asks for every later part naming it (``if-range: <its
etag>``): those parts are cut from what was kept, never by running the route
again, which re-read the file and the store and hashed the whole body for every
4 MiB. A kept body goes when its last part is sent, after
``KEPT_BODY_SECONDS``, or to make room under ``KEPT_BODIES_MAX_BYTES``; a part
asked for after that runs the route, as every part once did.

A drawing the store has not drawn yet renders off the request
(``cadgen.viewer.drawings``): here a request waits on it only briefly
(``DRAWING_HOLD_SECONDS``), since calls share a host's few slots, and the 202
has the page ask again a moment later (``DRAWING_RETRY_MS``).
"""

from __future__ import annotations

import base64
import email.utils
import gzip
import io
import re
import threading
import time
from collections import OrderedDict
from typing import Any

from cadgen.viewer import url_norm
from cadgen.viewer.response import Request, Response

MAX_REQUEST_BODY_BYTES = 256 * 1024 * 1024
_ALLOWED_METHODS = frozenset({"GET", "HEAD", "POST"})
_API_PREFIXES = ("/__cad/", "/__tess_cache")
# The one route whose effect belongs to the host: a view copies through its host's frame, never
# through the server's clipboard. (No app here has a shutdown: it refuses `/__cad/shutdown` itself.)
_HOST_EFFECT_ROUTES = frozenset({"/__cad/clipboard"})
# How long one catalog read answers every view of a file that asks for its revision: views sync
# each second, and N of them on one file then cost one read, not N.
CATALOG_REVISION_SECONDS = 0.75
# A JSON body above this size travels gzipped (the module docstring); one below it gains too
# little to be worth the page's inflating it.
GZIP_JSON_MIN_BYTES = 4 * 1024
# The most body one reply carries (the module docstring): its base64, and so the message, is under
# 5.6 MB. The MCP TypeScript SDK's stdio reader takes 10 MiB a message unless a host sets more
# (Claude Code reads 16 MiB, Claude Desktop sets 32 MiB). The page's `TUNNEL_REPLY_MAX_BYTES`.
MAX_REPLY_BYTES = 4 * 1024 * 1024
# A long body kept for its later parts (the module docstring): for how long, and in all at most.
KEPT_BODY_SECONDS = 60.0
KEPT_BODIES_MAX_BYTES = 256 * 1024 * 1024
# How long a drawing request waits on its render, and when the page asks again (the module
# docstring): about one call a second while a large drawing renders, as a view's sync makes.
DRAWING_HOLD_SECONDS = 0.25
DRAWING_RETRY_MS = 750
_CONTENT_RANGE = re.compile(r"bytes [0-9]+-([0-9]+)/([0-9]+)")


class _CapturedHandler:
    """The slice of ``BaseHTTPRequestHandler`` a viewer Response writes to."""

    def __init__(self) -> None:
        self.status = 500
        self.headers: dict[str, str] = {}
        self.wfile = io.BytesIO()
        self.close_connection = False
        self.connection = self

    def send_response_only(self, status: int, message: str | None = None) -> None:
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        self.headers[name.lower()] = value

    def date_time_string(self) -> str:
        return email.utils.formatdate(usegmt=True)

    def end_headers(self) -> None:
        pass

    def shutdown(self, how: int) -> None:
        pass


def _result(status: int, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    reply: dict[str, Any] = {"status": status, "headers": headers}
    media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type == "application/json" and len(body) > GZIP_JSON_MIN_BYTES:
        body = gzip.compress(body, compresslevel=1, mtime=0)
        reply["encoding"] = "gzip"
    if len(body) > MAX_REPLY_BYTES:
        # Sent, it would close the host's connection (the module docstring).
        return _result(502, {"content-type": "application/json; charset=utf-8"},
                       b'{"ok":false,"error":"the answer is longer than one cad_http reply carries"}')
    reply["body"] = base64.b64encode(body).decode("ascii")
    return reply


class ViewerTunnel:
    """The viewer backend every view of this server shares, made when the first one asks."""

    def __init__(self, *, recents=None, analytics=None, clock=time.monotonic) -> None:
        self._app = None
        self._recents = recents
        self._analytics = analytics
        self._lock = threading.Lock()
        self._clock = clock
        self._revisions: dict[str, tuple[float, str]] = {}
        # Long bodies kept for their later parts, by etag: (bytes, content type, extra headers, when).
        self._kept: OrderedDict[str, tuple[bytes, str, tuple, float]] = OrderedDict()

    @property
    def app(self):
        with self._lock:
            if self._app is None:
                from cadgen.viewer.http_app import create_cad_app

                app = create_cad_app(host="127.0.0.1", port=0)
                if self._recents is not None:
                    app.recents = self._recents
                # The server's recorder: a person's answer on a card here is the CAD app's.
                app.analytics, app.consent_by = self._analytics, "app"
                app.drawings.hold_seconds, app.drawings.retry_ms = DRAWING_HOLD_SECONDS, DRAWING_RETRY_MS
                self._app = app
            return self._app

    # What a view watches, answered on its sync (``cad_sync``) rather than as requests of its own.

    def catalog_revision(self, file: str) -> str:
        """A digest of the catalog the view reads (``/__cad/catalog?file=``): it moves whenever
        anything the view would see in it does, and the view reads the catalog again only then."""
        now = self._clock()
        with self._lock:
            cached = self._revisions.get(file)
            if cached is not None and now - cached[0] < CATALOG_REVISION_SECONDS:
                return cached[1]
        revision = str(self.app.read_catalog(file).get("revision") or "")
        with self._lock:
            if len(self._revisions) > 64:
                self._revisions = {name: value for name, value in self._revisions.items() if now - value[0] < 60.0}
            self._revisions[file] = (now, revision)
        return revision

    def preview(self, file: str) -> dict[str, Any]:
        """One file's build feed, now (the route's ``after`` would hold the request; the view
        asks again on its next sync)."""
        try:
            return self.app.build_status(file)
        except Exception as error:  # noqa: BLE001 - the feed's failure is the view's to show, as the route's 4xx was
            return {"error": str(error) or type(error).__name__}

    def serve(self, *, method: str, url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        # ``url`` is already text (the view's fetch URL, often absolute against
        # a placeholder origin); the router's own parser drops the authority.
        method = method.upper()
        path = url_norm.request_pathname(url)
        if method not in _ALLOWED_METHODS:
            return _result(405, {"allow": "GET, HEAD, POST", "content-length": "0"}, b"")
        if not path.startswith(_API_PREFIXES) or path in _HOST_EFFECT_ROUTES:
            return _result(404, {"content-type": "text/plain; charset=utf-8"}, b"Not found")
        if len(body) > MAX_REQUEST_BODY_BYTES:
            return _result(400, {"content-type": "application/json; charset=utf-8"}, b'{"ok":false,"error":"request body too large"}')
        lowered = {name.lower(): str(value) for name, value in headers.items()}
        lowered.pop("host", None)  # a loopback name the router accepts; absent is accepted too
        if body:
            lowered["content-length"] = str(len(body))
        query = url_norm.request_query(url)
        if path == "/__cad/preview":
            # The preview feed's ``after`` holds the request until the build ledger moves (up to a
            # second). Here it answers at once: the host relays every call through a few slots all of
            # its views share, and a held one keeps another view's model load waiting. The feed paces
            # an answer that brings nothing new itself.
            query = url_norm.Query([pair for pair in query if pair[0] != "after"])
        byte_range = lowered.get("range") if method == "GET" else None
        if byte_range and lowered.get("if-range"):
            part = self._kept_part(lowered["if-range"], byte_range)
            if part is not None:
                return part
        request = Request(raw_method=method, path=path, query=query, headers=lowered, read_body=lambda: body)
        handler = _CapturedHandler()
        response = Response(handler, head_only=request.is_head, byte_range=byte_range, on_parts=self._keep)
        try:
            self.app.handle(request, response)
        except Exception:
            if not response.written:
                response.send_json(500, {"ok": False, "error": "Internal server error"})
            raise
        if not response.written:
            response.send_json(500, {"ok": False, "error": "the route wrote no response"})
        if handler.close_connection:
            return _result(502, {"content-type": "application/json; charset=utf-8"},
                           b'{"ok":false,"error":"the file changed or could not be read completely"}')
        return _result(handler.status, handler.headers, handler.wfile.getvalue())

    # A long body's later parts, cut from the body its first part kept (the module docstring).

    def _keep(self, etag: str, data: bytes, content_type: str, extra_headers: tuple) -> None:
        if len(data) > KEPT_BODIES_MAX_BYTES:
            return
        with self._lock:
            self._kept.pop(etag, None)
            self._kept[etag] = (data, content_type, extra_headers, self._clock())
            self._prune_kept()

    def _prune_kept(self) -> None:
        now = self._clock()
        total = sum(len(kept[0]) for kept in self._kept.values())
        for etag in list(self._kept):
            data, _type, _extra, when = self._kept[etag]
            if total <= KEPT_BODIES_MAX_BYTES and now - when <= KEPT_BODY_SECONDS:
                continue
            del self._kept[etag]
            total -= len(data)

    def _kept_part(self, etag: str, byte_range: str) -> dict[str, Any] | None:
        with self._lock:
            self._prune_kept()
            kept = self._kept.get(etag)
        if kept is None:
            return None
        data, content_type, extra_headers, _when = kept
        handler = _CapturedHandler()
        Response(handler, byte_range=byte_range).send_bytes(200, data, content_type, extra_headers, etag=etag)
        sent = _CONTENT_RANGE.fullmatch(handler.headers.get("content-range", ""))
        if sent is None or int(sent.group(1)) + 1 == int(sent.group(2)):
            # The last part (or the whole body): nothing will ask for this body again.
            with self._lock:
                self._kept.pop(etag, None)
        return _result(handler.status, handler.headers, handler.wfile.getvalue())
