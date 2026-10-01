"""The CAD Viewer's HTTP routes, served in-process for a view with no network.

A view sends exactly the requests the web client sends (``/__cad/*``,
``/__tess_cache/*``) as tool calls; this module hands each one to the viewer's
own router -- one :class:`~cadgen.viewer.http_app.CadApp` per root -- and returns
the status, headers and body bytes. There is one backend, not two: the router,
its path containment and its limits are the ones the web app uses.
"""

from __future__ import annotations

import base64
import email.utils
import io
import threading
from collections import OrderedDict
from typing import Any

from cadgen.viewer import url_norm
from cadgen.viewer.response import Request, Response

from .roots import GLOBAL, Root

MAX_REQUEST_BODY_BYTES = 256 * 1024 * 1024
_ALLOWED_METHODS = frozenset({"GET", "HEAD", "POST"})
_API_PREFIXES = ("/__cad/", "/__tess_cache")
# Routes whose effects belong to a host: the web app's reveal and clipboard, and its model library
# (a view here reaches the library through cad_recents).
_HOST_EFFECT_ROUTES = frozenset({"/__cad/reveal", "/__cad/clipboard", "/__cad/recents"})


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
    return {"status": status, "headers": headers, "body": base64.b64encode(body).decode("ascii")}


class ViewerTunnel:
    """One viewer backend per root, most recently used kept."""

    def __init__(self, *, limit: int = 8) -> None:
        self._apps: OrderedDict[tuple[str, str], Any] = OrderedDict()
        self._limit = limit
        self._lock = threading.Lock()

    def app_for(self, root: Root):
        with self._lock:
            app = self._apps.get(root.key)
            if app is not None:
                self._apps.move_to_end(root.key)
                return app
        from cadgen.viewer.http_app import create_cad_app

        created = create_cad_app(root=root.path, host="127.0.0.1", port=0, lazy=root.kind == GLOBAL)
        with self._lock:
            app = self._apps.setdefault(root.key, created)
            self._apps.move_to_end(root.key)
            while len(self._apps) > self._limit:
                self._apps.popitem(last=False)
            return app

    def serve(self, root: Root, *, method: str, url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
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
        request = Request(raw_method=method, path=path, query=query, headers=lowered, read_body=lambda: body)
        handler = _CapturedHandler()
        response = Response(handler, head_only=request.is_head)
        try:
            self.app_for(root).handle(request, response)
        except Exception:
            if not response.written:
                response.send_json(500, {"ok": False, "error": "Internal server error"})
            raise
        if not response.written:
            response.send_json(500, {"ok": False, "error": "the route wrote no response"})
        return _result(handler.status, handler.headers, handler.wfile.getvalue())
