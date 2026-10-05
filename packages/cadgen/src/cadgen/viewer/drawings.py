"""``GET /__cad/drawing``: a ``.dxf`` as a flat 2D render payload.

This module is the route's two decisions — what may be opened, and what the
HTTP answer is. The payload itself is cadgen's (``cadgen.drawing_payload``),
imported inside the handler so that ezdxf never loads at ``cadgen.viewer``
import time and a cache hit never loads it at all.

The drawing is named by its absolute path, as every file is (``backend``).
Statuses, in the order they are decided:

* no ``?file=``, a ref that is not an absolute path, or one that does not end in
  ``.dxf`` -> 400 (this route draws drawings; a caller aiming an ``.step`` at it
  has made a mistake worth reading).
* no such file -> 404, like the asset route.
* an unreadable or damaged DXF -> ``DrawingReadError`` (a ``ValueError``) ->
  400 with the teaching message, through the GET funnel's JSON error shape.
"""

from __future__ import annotations

import os

from .backend import absolute_path
from .scanner import node_basename

__all__ = ["DRAWING_ROUTE_PATH", "DRAWING_SUFFIX", "drawing_payload_response", "resolve_drawing_path"]

DRAWING_ROUTE_PATH = "/__cad/drawing"
DRAWING_SUFFIX = ".dxf"


def resolve_drawing_path(file_ref) -> str | None:
    """The absolute ``.dxf`` this ref names, or ``None`` for a 404.

    Raises ``ValueError`` for a ref this route will not take.
    """
    if not file_ref:
        raise ValueError(f"GET {DRAWING_ROUTE_PATH} needs ?file=<the absolute path of a .dxf>")
    candidate = absolute_path(file_ref)
    if not candidate.lower().endswith(DRAWING_SUFFIX):
        raise ValueError(
            f"{DRAWING_ROUTE_PATH} renders DXF drawings; "
            f"{node_basename(candidate)} is not a {DRAWING_SUFFIX} file"
        )
    return candidate if os.path.isfile(candidate) else None


def drawing_payload_response(file_ref) -> tuple[int, bytes | dict]:
    """``(status, body)``: the payload's bytes at 200, or a JSON error dict."""
    candidate = resolve_drawing_path(file_ref)
    if candidate is None:
        return 404, {"error": "Not found"}
    from cadgen.drawing_payload import drawing_payload_bytes

    return 200, drawing_payload_bytes(candidate)
