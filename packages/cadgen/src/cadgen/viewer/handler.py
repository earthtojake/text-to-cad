"""Sockets only: the ``ThreadingHTTPServer`` and its request handler.

No routing lives here. The handler builds a :class:`~server.response.Request`,
hands it to ``app.handle(request, response)`` and manages the connection.

Why threads rather than a selector loop: this workload is sendfile-shaped IO
plus one long-lived POST, and a selector loop would have to reimplement
HTTP/1.1 framing, keep-alive and chunked bodies — every one of those a place to
diverge from a contract with 20+ header-level pins. Threads cost nothing here:
a single-user loopback tool sees roughly six browser connections.

Measured on a 483-component package over loopback (967 files, 7.2MB): Node
65ms at concurrency 6, this 86ms. 1.3x slower and imperceptible, because the
bottleneck was never component fetch — it is client-side tessellation.
"""

from __future__ import annotations

import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import url_norm
from .response import Request, Response

__all__ = ["CadHTTPServer", "make_handler_class", "MAX_REQUEST_BODY_BYTES"]

# The tess-cache POSTs are the only body-carrying routes; everything else rides
# the query string. The largest legitimate payload is one component's
# tessellation entry.
MAX_REQUEST_BODY_BYTES = 256 * 1024 * 1024

_ALLOWED_METHODS = ("GET", "HEAD", "POST")


class CadHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    # socketserver sets this to 1 unconditionally. On Windows SO_REUSEADDR
    # permits binding a port another process is actively LISTENING on, which
    # silently defeats both the strict --port refusal and the roll loop. Node
    # does not set it there. On POSIX it cannot steal a listening port, so True
    # matches Node.
    allow_reuse_address = not sys.platform.startswith("win")

    # NOT disable_nagle_algorithm. Measured: TCP_NODELAY made a 483-file fetch
    # 30% SLOWER at concurrency 6 (112ms vs 86ms), because with two small
    # writes per response Nagle coalesces headers and body into one segment.
    # It only broke even at concurrency 12.

    def __init__(self, address, handler_class, app):
        self.app = app
        super().__init__(address, handler_class)

    def handle_error(self, request, client_address):  # noqa: D102
        # A client that hangs up mid-stream is routine, not an incident. Only
        # genuine faults reach stderr; the launcher's stdout must stay clean
        # because the launch smoke test parses it.
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def make_handler_class(app):
    class CadRequestHandler(BaseHTTPRequestHandler):
        # Python defaults to HTTP/1.0, which means no keep-alive. The client
        # fetches many .surf components in parallel; without keep-alive every
        # component pays a fresh connection. Safe because every response here
        # carries an explicit content-length.
        protocol_version = "HTTP/1.1"

        # No Server header is emitted anywhere: every response goes through
        # send_response_only + explicit send_header, and version_string() feeds
        # only send_response(), which is never called. Node sends none either.
        # Overriding version_string() to "" would be WRONG — it produces a
        # literal `Server: ` with an empty value, which is present, not absent.

        # --- diagnostics ---------------------------------------------------

        def log_message(self, fmt, *args):  # noqa: D102, ARG002
            # Silent by default: the launcher's stdout carries a machine-read
            # contract and an access log would corrupt it.
            return

        def log_error(self, fmt, *args):  # noqa: D102, ARG002
            return

        def send_response_only(self, code, message=None):
            """Always emit a status line.

            The stdlib suppresses it whenever ``request_version`` is
            ``HTTP/0.9`` — which is the class DEFAULT, still in place when
            ``parse_request`` rejects a bad version. A request like
            ``GET / HTTP/9.9`` would then get no response bytes at all, where
            Node answers a normal status. Nothing speaks 0.9 to this server, so
            unconditional framing is both safe and the only consistent answer.
            """
            if self.request_version == "HTTP/0.9":
                self.request_version = "HTTP/1.0"
                self.close_connection = True
            super().send_response_only(code, message)

        def send_error(self, code, message=None, explain=None):  # noqa: ARG002
            """Status plus ``content-length: 0``, never HTML.

            ``BaseHTTPRequestHandler`` reaches this on its own for a malformed
            request line, an unsupported HTTP version, an over-long request
            line and an over-long header block, and its default emits a
            361-byte ``text/html`` body with ``Server``/``Date``/``Connection``
            headers that appear on no other route. That would break the
            byte-level header contract in a place no status-code assertion can
            see.
            """
            self.close_connection = True
            try:
                self.send_response_only(code)
                self.send_header("date", self.date_time_string())
                self.send_header("content-length", "0")
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        # --- body ----------------------------------------------------------

        def _read_body(self) -> bytes:
            # Framing was validated at dispatch, so content-length is present,
            # numeric and within the cap by the time anything reads a body.
            raw_length = self.headers.get("content-length")
            if not raw_length:
                return b""
            return self.rfile.read(int(raw_length))

        def _drain_body(self) -> None:
            """Discard an unread body so the NEXT request on this connection parses.

            ``POST /__cad/artifact`` never reads its body — every parameter
            rides the query string, so a body sent with it goes unread.
            Node discards them harmlessly; an HTTP/1.1 handler that leaves
            content-length bytes in the buffer mis-parses the next request, and
            the symptom is intermittent garbage under the client's parallel
            component fetches rather than a clean failure.
            """
            raw_length = self.headers.get("content-length")
            if not raw_length:
                return
            try:
                remaining = int(raw_length)
            except ValueError:
                self.close_connection = True
                return
            if remaining < 0 or remaining > MAX_REQUEST_BODY_BYTES:
                self.close_connection = True
                return
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 64 * 1024))
                if not chunk:
                    self.close_connection = True
                    return
                remaining -= len(chunk)

        # --- dispatch ------------------------------------------------------

        def _raw_target(self) -> str:
            """The request target as it arrived on the wire.

            NOT ``self.path``: ``parse_request`` collapses a leading ``//`` to
            ``/`` (a 3.11 open-redirect fix for SimpleHTTPRequestHandler), which
            turns ``//evil.example/__cad/server`` into a path segment instead of
            an authority Node would discard. Routing on it would answer the SPA
            where Node answers the API.
            """
            try:
                parts = self.raw_requestline.decode("iso-8859-1").rstrip("\r\n").split()
            except (AttributeError, UnicodeDecodeError):
                return self.path
            return parts[1] if len(parts) >= 2 else self.path

        def _validate_body_framing(self, response) -> bool:
            """Refuse a body we cannot frame, BEFORE routing.

            Doing this at dispatch rather than inside a body reader makes the
            guarantee route-independent: a route that never reads its body
            still cannot leave unframed bytes in the buffer for the next
            request on this connection.
            """
            transfer_encoding = (self.headers.get("transfer-encoding") or "").lower()
            if "chunked" in transfer_encoding:
                # The stdlib decodes no chunked framing at all: content-length
                # is None and rfile sits on the chunk header. Refuse rather
                # than silently mangle — a mangled /__tess_cache/batch body
                # permanently demotes the client's provider to per-key gets for
                # the life of the page.
                response.send_json(400, {"ok": False, "error": "chunked request bodies are not supported"})
                self.close_connection = True
                return False
            raw_length = self.headers.get("content-length")
            if raw_length:
                try:
                    length = int(raw_length)
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_REQUEST_BODY_BYTES:
                    # Answer FIRST, then close. Node's req.destroy() races the
                    # 400 and the client usually never sees it.
                    response.send_json(400, {"ok": False, "error": "request body too large"})
                    self.close_connection = True
                    return False
            return True

        def _dispatch(self) -> None:
            target = url_norm.target_from_request_line(self._raw_target())
            request = Request(
                raw_method=self.command,
                path=url_norm.request_pathname(target),
                query=url_norm.request_query(target),
                headers=self.headers,
                read_body=self._read_body,
            )
            response = Response(self, head_only=request.is_head)
            if not self._validate_body_framing(response):
                return
            try:
                app.handle(request, response)
            except Exception:  # noqa: BLE001 - a handler fault must not kill the connection silently
                if not response.written:
                    response.send_json(500, {"ok": False, "error": "Internal server error"})
                self.close_connection = True
                raise
            finally:
                if not request.body_was_read and not self.close_connection:
                    self._drain_body()

        def do_GET(self):  # noqa: N802
            self._dispatch()

        def do_HEAD(self):  # noqa: N802
            self._dispatch()

        def do_POST(self):  # noqa: N802
            self._dispatch()

        def handle_one_request(self):
            # Everything other than GET/HEAD/POST answers 405 instead of
            # hanging. The Node server dropped handle()'s false return on the
            # floor, so OPTIONS/PUT/DELETE/PATCH stalled until Node's 300s
            # requestTimeout — unpinned, unused by any client, and a trivial
            # connection-exhaustion vector against an unbounded threading
            # server. This is the ONE deliberate behaviour change in the port.
            try:
                self.raw_requestline = self.rfile.readline(65537)
                if len(self.raw_requestline) > 65536:
                    self.requestline = ""
                    self.request_version = ""
                    self.command = ""
                    self.send_error(414)
                    return
                if not self.raw_requestline:
                    self.close_connection = True
                    return
                if not self.parse_request():
                    return
                if self.command not in _ALLOWED_METHODS:
                    if "chunked" in (self.headers.get("transfer-encoding") or "").lower():
                        # Nothing here can frame a chunked body, so the only
                        # safe answer is to stop reusing the connection.
                        self.close_connection = True
                    else:
                        self._drain_body()
                    Response(self).send_empty(405, [("allow", "GET, HEAD, POST")])
                    self.wfile.flush()
                    return
                method = getattr(self, f"do_{self.command}", None)
                if method is None:
                    self.send_error(501)
                    return
                method()
                self.wfile.flush()
            except socket.timeout:
                self.close_connection = True
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

    return CadRequestHandler


def serve(app, host: str, port: int) -> CadHTTPServer:
    """Bind and return the server. Requests are only accepted by serve_forever.

    Binding in the constructor and only then attaching the app reproduces the
    Node launcher's guarantee that the handler is in place in the same tick as
    the successful bind, so ``serverInfo().port`` always names the port the
    process actually took.
    """
    return CadHTTPServer((host, port), make_handler_class(app), app)
