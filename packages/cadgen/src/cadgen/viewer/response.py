"""Request/response value types and the four response writers.

Everything is written through ``send_response_only()`` plus explicit
``send_header()`` calls — never ``send_response()``, which injects ``Server``
and ``Date`` defaults of its own and would put a ``Server:`` header on some
responses but not others. The header set on the wire is part of the contract:

* ``send_json`` / ``send_bytes`` / ``stream_file`` carry ``cache-control:
  no-store`` and an explicit ``content-length``; ``content-type`` appears only
  when truthy.
* ``send_empty`` (the tess 403/404/204 and the method-not-allowed 405) carries
  ONLY ``content-length: 0`` — no content-type, no cache-control.
* NO ``Access-Control-*`` header is ever emitted, on any route, at any status.
  Their absence is what makes the same-origin policy block cross-origin reads
  and what makes the POST preflight fail. Do not add them.

HEAD suppression lives in each writer rather than at method dispatch. Under
HTTP/1.1 keep-alive a HEAD that ships a body does not merely waste bytes — it
desynchronises the connection exactly like an undrained request body.
"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any, Iterable

__all__ = ["Request", "Response", "STREAM_CHUNK_BYTES"]

STREAM_CHUNK_BYTES = 64 * 1024


class Request:
    """One parsed request, with no socket in sight.

    Keeping routing socket-free is what lets the suites drive the router
    directly, without binding a port.
    """

    __slots__ = ("method", "raw_method", "path", "query", "headers", "_read_body", "_body")

    def __init__(self, *, raw_method, path, query, headers, read_body):
        self.raw_method = raw_method
        # HEAD is handled as GET throughout; only the writers know the difference.
        self.method = "GET" if raw_method == "HEAD" else raw_method
        self.path = path
        self.query = query
        self.headers = headers
        self._read_body = read_body
        self._body: bytes | None = None

    @property
    def is_head(self) -> bool:
        return self.raw_method == "HEAD"

    def header(self, name: str, default: str = "") -> str:
        value = self.headers.get(name)
        return default if value is None else value

    def body(self) -> bytes:
        """Read and cache the request body. Raises for an over-cap body."""
        if self._body is None:
            self._body = self._read_body()
        return self._body

    @property
    def body_was_read(self) -> bool:
        return self._body is not None


class Response:
    """Writes one response onto a ``BaseHTTPRequestHandler``."""

    __slots__ = ("_handler", "_head_only", "written")

    def __init__(self, handler, head_only: bool = False):
        self._handler = handler
        self._head_only = head_only
        self.written = False

    # --- header plumbing ---------------------------------------------------

    def _begin(self, status: int, headers: Iterable[tuple[str, Any]]) -> None:
        handler = self._handler
        handler.send_response_only(status)
        # Node sends Date on every response and no Server header at all.
        handler.send_header("date", handler.date_time_string())
        for name, value in headers:
            handler.send_header(name, str(value))
        handler.end_headers()
        self.written = True

    def _write(self, data: bytes) -> None:
        if self._head_only or not data:
            return
        try:
            self._handler.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            # An abandoned fetch is routine (the client cancels component loads
            # constantly). Do not let it print a traceback into the launcher's
            # stdout, which the launch smoke test parses.
            self._handler.close_connection = True

    # --- writers -----------------------------------------------------------

    def send_json(self, status: int, payload) -> None:
        # Compact, non-escaped UTF-8: JSON.stringify's exact bytes, which
        # content-length is then derived from.
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._begin(
            status,
            [
                ("content-type", "application/json; charset=utf-8"),
                ("cache-control", "no-store"),
                ("content-length", len(body)),
            ],
        )
        self._write(body)

    def send_bytes(self, status: int, data: bytes, content_type: str = "") -> None:
        headers: list[tuple[str, Any]] = [
            ("cache-control", "no-store"),
            ("content-length", len(data)),
        ]
        if content_type:
            headers.append(("content-type", content_type))
        self._begin(status, headers)
        self._write(data)

    def send_plain(self, status: int, text: str) -> None:
        """``sendPlain``: a content-type ONLY for 404.

        400 "Bad request" and 403 "Forbidden" go out with no content-type at
        all. Unpinned but shipped, and harmonising it is a separate decision.
        """
        self.send_bytes(
            status,
            text.encode("utf-8"),
            "text/plain; charset=utf-8" if status == 404 else "",
        )

    def send_empty(self, status: int, extra_headers: Iterable[tuple[str, Any]] = ()) -> None:
        """Status plus ``content-length: 0`` and nothing else."""
        self._begin(status, [*extra_headers, ("content-length", 0)])

    def stream_file(self, file_path, stat_result: os.stat_result, content_type: str = "") -> None:
        """Always 200, chunked, never buffered whole.

        A 500MB GLB must not become 500MB of RSS, and 200 concurrent asset GETs
        must stay bounded at ``STREAM_CHUNK_BYTES`` per thread. The stat answers
        existence and content-length up front, so the status line is always
        correct.
        """
        headers: list[tuple[str, Any]] = [
            ("cache-control", "no-store"),
            ("content-length", stat_result.st_size),
        ]
        if content_type:
            headers.append(("content-type", content_type))
        self._begin(200, headers)
        if self._head_only:
            return
        try:
            with open(file_path, "rb") as handle:
                shutil.copyfileobj(handle, self._handler.wfile, STREAM_CHUNK_BYTES)
        except (BrokenPipeError, ConnectionResetError):
            self._handler.close_connection = True
        except OSError:
            # Headers are already gone, so a clean end() would present a
            # TRUNCATED body as a complete response — and content-length would
            # be a lie some clients accept silently. Kill the socket instead, so
            # the failure is unambiguous.
            self._handler.close_connection = True
            try:
                self._handler.connection.shutdown(2)
            except OSError:
                pass
