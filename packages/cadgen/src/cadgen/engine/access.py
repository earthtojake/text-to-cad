"""Who may read a served document from another origin: a page on this machine.

The CAD Viewer's page (``cadgen viewer``, on its own port) and the snapshot's headless page
(``http://localhost``) read a document's structure and part buffers from the engine directly,
so the bytes never pass through a second server. Their origin is not the engine's, so the
engine says which origins may read its answers: loopback ones alone (``localhost``,
``127.0.0.1``, ``[::1]``, any port). A page from anywhere else gets no such header, and its
browser keeps the answer from it. Every route is a GET a page sends without custom headers, so
no preflight is ever asked for.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

__all__ = ["allow_origin", "loopback_origin"]

_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


def loopback_origin(origin: str | None) -> bool:
    """Whether ``origin`` (a request's ``Origin`` header) is a page on this machine."""
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
        host = parsed.hostname
        parsed.port  # noqa: B018 - a malformed port raises
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and host is not None and (host in _LOOPBACK or host.endswith(".localhost"))


def allow_origin(handler: Any) -> None:
    """Name the request's origin as one that may read the answer, when it is a loopback page."""
    origin = handler.headers.get("Origin")
    if loopback_origin(origin):
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Vary", "Origin")
