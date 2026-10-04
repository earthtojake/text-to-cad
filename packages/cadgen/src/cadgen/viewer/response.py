"""Request/response value types and the four response writers.

Everything is written through ``send_response_only()`` plus explicit
``send_header()`` calls — never ``send_response()``, which injects ``Server``
and ``Date`` defaults of its own and would put a ``Server:`` header on some
responses but not others. The header set on the wire is part of the contract:

* ``send_json`` / ``send_bytes`` / ``stream_file`` carry ``cache-control:
  no-store`` and an explicit ``content-length``; ``content-type`` appears only
  when truthy. ``send_bytes`` and ``stream_file`` add the caller's
  ``extra_headers`` (the raw-file routes' sandbox, ``http_app.RAW_FILE_HEADERS``).
* ``send_empty`` (the tess 403/404/204 and the method-not-allowed 405) carries
  ONLY ``content-length: 0`` — no content-type, no cache-control.
* NO ``Access-Control-*`` header is ever emitted, on any route, at any status.
  Their absence is what makes the same-origin policy block cross-origin reads
  and what makes the POST preflight fail. Do not add them.

A response can be given a GET's ``Range`` (``byte_range``; ``cadgen mcp``'s
tunnel gives it one, to carry a long body in parts). Every writer of a 200
answers ``bytes=<first>-<last>`` inside the body with ``206``, that part,
``content-range: bytes <first>-<last>/<length>`` and an ``etag`` naming the
whole body, so parts put together can be told to be of one body. Any other
range is ignored, as RFC 9110 allows: the body is sent whole.

HEAD suppression lives in each writer rather than at method dispatch. Under
HTTP/1.1 keep-alive a HEAD that ships a body does not merely waste bytes — it
desynchronises the connection exactly like an undrained request body.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Iterable

__all__ = ["Request", "Response", "STREAM_CHUNK_BYTES"]

STREAM_CHUNK_BYTES = 64 * 1024
_BYTE_RANGE = re.compile(r"bytes=([0-9]{1,16})-([0-9]{1,16})")


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

    __slots__ = ("_handler", "_head_only", "_range", "written")

    def __init__(self, handler, head_only: bool = False, byte_range: str | None = None):
        self._handler = handler
        self._head_only = head_only
        self._range = byte_range
        self.written = False

    def _span(self, length: int) -> tuple[int, int] | None:
        """The part of a ``length``-byte body the range asks for; None for the whole body."""
        match = _BYTE_RANGE.fullmatch(self._range or "")
        if match is None:
            return None
        first, last = int(match.group(1)), min(int(match.group(2)), length - 1)
        return (first, last) if first <= last and (first, last) != (0, length - 1) else None

    def _send_part(self, data: bytes, content_type: str, extra_headers: Iterable[tuple[str, Any]]) -> bool:
        """206 with the part of ``data`` the range asks for; False when it asks for all of it."""
        span = self._span(len(data))
        if span is None:
            return False
        first, last = span
        headers: list[tuple[str, Any]] = [
            ("cache-control", "no-store"),
            ("content-length", last - first + 1),
            ("content-range", f"bytes {first}-{last}/{len(data)}"),
            ("etag", f'"{hashlib.sha256(data).hexdigest()}"'),
        ]
        if content_type:
            headers.append(("content-type", content_type))
        headers.extend(extra_headers)
        self._begin(206, headers)
        self._write(data[first:last + 1])
        return True

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
        if status == 200 and self._send_part(body, "application/json; charset=utf-8", ()):
            return
        self._begin(
            status,
            [
                ("content-type", "application/json; charset=utf-8"),
                ("cache-control", "no-store"),
                ("content-length", len(body)),
            ],
        )
        self._write(body)

    def send_bytes(self, status: int, data: bytes, content_type: str = "",
                   extra_headers: Iterable[tuple[str, Any]] = ()) -> None:
        if status == 200 and self._send_part(data, content_type, extra_headers):
            return
        headers: list[tuple[str, Any]] = [
            ("cache-control", "no-store"),
            ("content-length", len(data)),
        ]
        if content_type:
            headers.append(("content-type", content_type))
        headers.extend(extra_headers)
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

    def stream_file(self, file_path, stat_result: os.stat_result, content_type: str = "",
                    extra_headers: Iterable[tuple[str, Any]] = ()) -> None:
        """200 (206 for a range: read from where it starts), chunked, never buffered whole.

        A 500MB GLB must not become 500MB of RSS, and 200 concurrent asset GETs
        must stay bounded at ``STREAM_CHUNK_BYTES`` per thread. The stat answers
        existence and content-length up front, so the status line is always
        correct. A part's ``etag`` is the file's inode, size and time: a rewrite
        changes it.
        """
        span = self._span(stat_result.st_size)
        first, last = span or (0, stat_result.st_size - 1)
        headers: list[tuple[str, Any]] = [
            ("cache-control", "no-store"),
            ("content-length", last - first + 1),
        ]
        if span:
            headers += [("content-range", f"bytes {first}-{last}/{stat_result.st_size}"),
                        ("etag", f'"{stat_result.st_ino:x}-{stat_result.st_size:x}-{stat_result.st_mtime_ns:x}"')]
        if content_type:
            headers.append(("content-type", content_type))
        headers.extend(extra_headers)
        self._begin(206 if span else 200, headers)
        if self._head_only:
            return
        try:
            with open(file_path, "rb") as handle:
                handle.seek(first)
                remaining = last - first + 1
                while remaining:
                    chunk = handle.read(min(STREAM_CHUNK_BYTES, remaining))
                    if not chunk:
                        raise OSError("the file is shorter than it was")
                    self._handler.wfile.write(chunk)
                    remaining -= len(chunk)
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
