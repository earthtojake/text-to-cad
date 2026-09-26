"""``GET /__cad/drawing``: a ``.dxf`` as a flat 2D render payload.

This module is the route's two decisions — what may be opened, and what the
HTTP answer is. The payload itself is cadgen's (``cadgen.drawing_payload``),
imported inside the handler so that ezdxf never loads at ``cadgen.viewer``
import time and a cache hit never loads it at all.

Path resolution is the SAME containment rule the asset and artifact routes
apply, through the same ``require_contained``: this is the route that turns a
``?file=`` ref into a path the server will open, and the store's history has
one hole of exactly that shape in it (``backend.py``). A ``..`` walk and an
absolute path outside the root are both 403, and the containment check and the
open see one string.

Statuses, in the order they are decided:

* no ``?file=``, or a ref that does not end in ``.dxf`` -> 400 (this route
  draws drawings; a caller aiming an ``.step`` at it has made a mistake worth
  reading). The extension is checked BEFORE containment, matching the asset
  route: ``?file=/etc/passwd`` is refused for what it is, not for where it is.
* outside the served root -> ``ForbiddenAssetError`` -> 403.
* a hidden path component, or no such file -> 404, like the asset route.
* an unreadable or damaged DXF -> ``DrawingReadError`` (a ``ValueError``) ->
  400 with the teaching message, through the GET funnel's JSON error shape.
"""

from __future__ import annotations

import os

from .backend import ForbiddenAssetError, normalized_file_ref, require_contained
from .scanner import node_basename, path_relative

__all__ = ["DRAWING_ROUTE_PATH", "DRAWING_SUFFIX", "drawing_payload_response", "resolve_drawing_path"]

DRAWING_ROUTE_PATH = "/__cad/drawing"
DRAWING_SUFFIX = ".dxf"


def resolve_drawing_path(root_path: str, file_ref) -> str | None:
    """The absolute ``.dxf`` this ref names, or ``None`` for a 404.

    Raises ``ValueError`` for a ref this route will not take and
    ``ForbiddenAssetError`` for one that leaves the root.
    """
    normalized = normalized_file_ref(file_ref)
    if not normalized:
        raise ValueError(
            f"GET {DRAWING_ROUTE_PATH} needs ?file=<a .dxf inside the served directory>"
        )
    if not normalized.lower().endswith(DRAWING_SUFFIX):
        raise ValueError(
            f"{DRAWING_ROUTE_PATH} renders DXF drawings; "
            f"{node_basename(normalized)} is not a {DRAWING_SUFFIX} file"
        )
    root = os.path.abspath(str(root_path or ""))
    # abspath collapses the dot segments BEFORE the check, so the string that
    # is verified is the string that is opened.
    candidate = os.path.abspath(
        normalized if os.path.isabs(normalized) else os.path.join(root, normalized)
    )
    require_contained(root, candidate)
    relative = path_relative(root, candidate)
    if any(part and part != ".." and part.startswith(".") for part in relative.split(os.sep)):
        # A hidden root-relative component is not served, and says so as a
        # miss rather than as a refusal — the same shape the asset route uses.
        return None
    return candidate if os.path.isfile(candidate) else None


def drawing_payload_response(root_path: str, file_ref) -> tuple[int, bytes | dict]:
    """``(status, body)``: the payload's bytes at 200, or a JSON error dict."""
    candidate = resolve_drawing_path(root_path, file_ref)
    if candidate is None:
        return 404, {"error": "Not found"}
    from cadgen.drawing_payload import drawing_payload_bytes

    return 200, drawing_payload_bytes(candidate)
