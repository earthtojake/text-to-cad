"""``GET /__cad/drawing``: a ``.dxf`` as a flat 2D render payload.

This module is the route's decisions — what may be opened, when a drawing is
rendered, what the HTTP answer is, and which answers it keeps. The payload
itself is cadgen's (``cadgen.drawing_payload``), imported inside the render so
that ezdxf never loads at ``cadgen.viewer`` import time and a held answer never
loads it at all.

The drawing is named by its absolute path, as every file is (``backend``), and
read whole on every request: its answer is held by those bytes, in this
process's memory and nowhere else -- the last ``HELD`` answers, the one asked
for least recently going first. The same bytes again, the file touched, copied
or put back, are answered from memory; other bytes are rendered, from the bytes
read, so an answer is always the payload of the bytes it is held by. Every DXF
is drawn this one way, one a model wrote and a vendor's alike.
Statuses, in the order they are decided:

* no ``?file=``, a ref that is not an absolute path, or one that does not end in
  ``.dxf`` -> 400 (this route draws drawings; a caller aiming an ``.step`` at it
  has made a mistake worth reading).
* no such file -> 404, like the asset route.
* an unreadable or damaged DXF -> ``DrawingReadError`` (a ``ValueError``) ->
  400 with the teaching message, through the GET funnel's JSON error shape.
* an answer held for the file's bytes, or a render that finishes within the
  request's hold -> its status, 200 with the payload's bytes.
* a render still running -> 202 ``{"state": "drawing", "retryMs": N}``: ask
  again after ``retryMs``.

A request never holds for a render's length. A first open renders on a thread
of its own (:class:`DrawingRenders`), and the request waits for it only as long
as the app's hold, then answers 202 and is asked again: a client bounds each
request by how long the server stays silent, never by how long a drawing takes,
so a drawing that takes a minute opens, and a server that stopped answering is
still noticed. One render per drawing's bytes: every request for them while it
runs joins it, and its answer is held when it ends.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict

from .backend import absolute_path
from .scanner import node_basename

__all__ = [
    "DRAWING_HOLD_SECONDS",
    "DRAWING_ROUTE_PATH",
    "DRAWING_SUFFIX",
    "HELD",
    "DrawingRenders",
    "resolve_drawing_path",
]

DRAWING_ROUTE_PATH = "/__cad/drawing"
DRAWING_SUFFIX = ".dxf"
# How long a request waits on a render before it answers 202: a small drawing renders inside it
# and is answered by the first request, and a large one costs one request per hold.
DRAWING_HOLD_SECONDS = 2.0
# Answers held, by the bytes they answer for (a payload can be megabytes).
HELD = 8


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


class _Render:
    """One drawing's render, which every request for its bytes joins, and its answer."""

    __slots__ = ("done", "status", "body")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.status = 500
        self.body: bytes | dict = {"error": "the drawing's render stopped before it finished"}


class DrawingRenders:
    """The route's renders, one per drawing's bytes, off the request, and the answers they made.

    ``hold_seconds`` is how long a request waits on a render before answering 202, and
    ``retry_ms`` the wait the 202 asks of the client before it asks again. The CAD Viewer holds
    and has the client ask again at once; the CAD app's tunnel, whose calls share a host's few
    slots, holds briefly and has its page come back a moment later (``cadgen.mcp.tunnel``).
    ``on_crash`` hears a render that failed for a reason other than its drawing (a bug, not a
    bad file), once per bytes held.
    """

    def __init__(self, *, hold_seconds: float = DRAWING_HOLD_SECONDS, retry_ms: int = 0, on_crash=None) -> None:
        self.hold_seconds = hold_seconds
        self.retry_ms = retry_ms
        self._on_crash = on_crash
        self._lock = threading.Lock()
        # Renders running, and the answers held (the most recently asked for last), by bytes.
        self._renders: dict[str, _Render] = {}
        self._held: OrderedDict[str, _Render] = OrderedDict()

    def any_in_flight(self) -> bool:
        """Whether a render is running: work a development restart would throw away."""
        with self._lock:
            return bool(self._renders)

    def response(self, file_ref) -> tuple[int, bytes | dict]:
        """``(status, body)``: the payload's bytes at 200, 202 while it renders, or a JSON error dict."""
        candidate = resolve_drawing_path(file_ref)
        if candidate is None:
            return 404, {"error": "Not found"}
        try:
            with open(candidate, "rb") as handle:
                data = handle.read()
        except FileNotFoundError:
            return 404, {"error": "Not found"}
        except OSError as error:
            return 400, {"error": f"{node_basename(candidate)} could not be read ({error}); "
                                  "check that it is a file this user may read"}
        key = hashlib.blake2b(data, digest_size=16).hexdigest()
        with self._lock:
            render = self._held.get(key)
            if render is not None:
                self._held.move_to_end(key)
                return render.status, render.body
            render = self._renders.get(key)
            if render is None:
                render = self._renders[key] = _Render()
                threading.Thread(target=self._render, args=(render, key, candidate, data), name="cadgen-drawing",
                                 daemon=True).start()
        if render.done.wait(self.hold_seconds):
            return render.status, render.body
        return 202, {"state": "drawing", "retryMs": self.retry_ms}

    def _render(self, render: _Render, key: str, path: str, data: bytes) -> None:
        from cadgen.drawing_payload import build_drawing_payload, encode_drawing_payload

        try:
            render.status, render.body = 200, encode_drawing_payload(build_drawing_payload(path, data))
        except ValueError as error:
            # A drawing that will not read (``DrawingReadError``): its message says why and what to do.
            render.status, render.body = 400, {"error": str(error)}
        except Exception as error:  # noqa: BLE001 - answered as the GET funnel answers a route's bug
            if self._on_crash is not None:
                self._on_crash(error)
            render.status, render.body = 400, {"error": str(error) or type(error).__name__}
        finally:
            with self._lock:
                self._renders.pop(key, None)
                self._held[key] = render
                while len(self._held) > HELD:
                    self._held.popitem(last=False)
            render.done.set()
