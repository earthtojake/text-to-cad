"""A large JSON answer compressed for a browser that accepts it: the payload routes' (a board's plot and DRC,
a drawing, a robot's structure).

``chosen(accept)`` picks the coding from the request's ``Accept-Encoding``: zstd where the standard library
has it (Python's ``compression.zstd``) and the browser asks for it, else gzip, else none. ``send`` answers
the body coded so, with ``content-encoding`` and ``vary: accept-encoding``; a body under ``SMALLEST``, a
request for a part of a body (``Range``: the CAD app's tunnel, which reassembles the identity bytes), and a
client that names no coding get the identity bytes, as before. ``Coded`` keeps each coding of one body made
once, for an answer the route holds in memory.
"""

from __future__ import annotations

import gzip
import threading
from typing import Any

__all__ = ["SMALLEST", "Coded", "chosen", "encode", "send"]

#: Bodies smaller than this go as they are: compressing them saves less than it costs.
SMALLEST = 4096
# gzip's level by size: the default for a body that compresses in moments, the fastest for a large one
# (a 72 MB board plot: 0.4 s at 1 against 1.7 s at 6, 19 MB against 16).
_GZIP_FAST_ABOVE = 8 * 1024 * 1024


def _zstd() -> Any:
    try:
        from compression import zstd
    except ImportError:
        return None
    return zstd


def chosen(accept: str) -> str | None:
    """The coding to answer with, from an ``Accept-Encoding``: ``zstd``, ``gzip`` or None."""
    named = {}
    for part in (accept or "").lower().split(","):
        name, _, params = part.strip().partition(";")
        quality = 1.0
        for param in params.split(";"):
            key, _, value = param.strip().partition("=")
            if key == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        if name:
            named[name.strip()] = quality
    if named.get("zstd", 0) > 0 and _zstd() is not None:
        return "zstd"
    if named.get("gzip", 0) > 0 or (named.get("*", 0) > 0 and "gzip" not in named):
        return "gzip"
    return None


def encode(data: bytes, coding: str) -> bytes:
    """``data`` coded as ``coding`` (``chosen``'s)."""
    if coding == "zstd":
        return _zstd().compress(data, 3)
    return gzip.compress(data, 1 if len(data) > _GZIP_FAST_ABOVE else 6, mtime=0)


class Coded:
    """One body and each coding of it, made once on first ask (thread-safe)."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self._coded: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def coded(self, coding: str) -> bytes:
        with self._lock:
            found = self._coded.get(coding)
            if found is None:
                found = self._coded[coding] = encode(self.data, coding)
            return found

    @property
    def size(self) -> int:
        return len(self.data) + sum(len(value) for value in self._coded.values())


def send(request: Any, response: Any, status: int, body: bytes | Coded, content_type: str,
         headers: tuple[tuple[str, Any], ...] = ()) -> None:
    """``body`` answered with ``status``: coded as the request accepts when it is large enough (see the
    module), else as it is."""
    coded = body if isinstance(body, Coded) else Coded(body)
    accept = request.header("accept-encoding") if hasattr(request, "header") else ""
    coding = chosen(accept) if status == 200 and len(coded.data) >= SMALLEST else None
    if coding is not None and not (request.header("range") if hasattr(request, "header") else ""):
        response.send_bytes(status, coded.coded(coding), content_type,
                            (*headers, ("content-encoding", coding), ("vary", "accept-encoding")))
        return
    response.send_bytes(status, coded.data, content_type, headers)
