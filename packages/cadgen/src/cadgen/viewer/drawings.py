"""``GET /__cad/drawing``: a ``.dxf`` as a flat 2D render payload.

This module is the route's decisions — what may be opened, when a drawing is
rendered, and what the HTTP answer is. The payload itself is cadgen's
(``cadgen.drawing_payload``), imported inside the handler so that ezdxf never
loads at ``cadgen.viewer`` import time and a cache hit never loads it at all.

The drawing is named by its absolute path, as every file is (``backend``).
Statuses, in the order they are decided:

* no ``?file=``, a ref that is not an absolute path, or one that does not end in
  ``.dxf`` -> 400 (this route draws drawings; a caller aiming an ``.step`` at it
  has made a mistake worth reading).
* no such file -> 404, like the asset route.
* an unreadable or damaged DXF -> ``DrawingReadError`` (a ``ValueError``) ->
  400 with the teaching message, through the GET funnel's JSON error shape.
* a payload the store holds, or a render that finishes within the request's
  hold -> 200 with the payload's bytes.
* a render still running -> 202 ``{"state": "drawing", "retryMs": N}``: ask
  again after ``retryMs``.

A request never holds for a render's length. A first open renders on a thread
of its own (:class:`DrawingRenders`), and the request waits for it only as long
as the app's hold, then answers 202 and is asked again: a client bounds each
request by how long the server stays silent, never by how long a drawing takes,
so a drawing that takes a minute opens, and a server that stopped answering is
still noticed. One render per drawing: every request for the same bytes while
it runs joins it, and its answer is kept for a while after it ends, so the
request that follows it is answered even where the store could not keep it.
"""

from __future__ import annotations

import os
import threading
import time

from .backend import absolute_path
from .scanner import node_basename

__all__ = [
    "DRAWING_HOLD_SECONDS",
    "DRAWING_ROUTE_PATH",
    "DRAWING_SUFFIX",
    "DrawingRenders",
    "resolve_drawing_path",
]

DRAWING_ROUTE_PATH = "/__cad/drawing"
DRAWING_SUFFIX = ".dxf"
# How long a request waits on a render before it answers 202: a small drawing renders inside it
# and is answered by the first request, and a large one costs one request per hold.
DRAWING_HOLD_SECONDS = 2.0
# How long a finished render's answer is kept for the requests that follow it. A client asks again
# at once or within a second (``retryMs``); the rest of the margin is for a slow page.
FINISHED_SECONDS = 30.0
# Finished answers kept at most (a payload can be megabytes; the store keeps every one anyway).
FINISHED_MAX = 8


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
    """One drawing's render, which every request for its bytes joins."""

    __slots__ = ("done", "status", "body", "finished_at")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.status = 500
        self.body: bytes | dict = {"error": "the drawing's render stopped before it finished"}
        self.finished_at = 0.0


class DrawingRenders:
    """The route's renders: one per drawing's bytes, off the request, joined by every request.

    ``hold_seconds`` is how long a request waits on a render before answering 202, and
    ``retry_ms`` the wait the 202 asks of the client before it asks again. The CAD Viewer holds
    and has the client ask again at once; the CAD app's tunnel, whose calls share a host's few
    slots, holds briefly and has its page come back a moment later (``cadgen.mcp.tunnel``).
    ``on_crash`` hears a render that failed for a reason other than its drawing (a bug, not a
    bad file), once.
    """

    def __init__(self, *, hold_seconds: float = DRAWING_HOLD_SECONDS, retry_ms: int = 0,
                 on_crash=None, clock=time.monotonic) -> None:
        self.hold_seconds = hold_seconds
        self.retry_ms = retry_ms
        self._on_crash = on_crash
        self._clock = clock
        self._lock = threading.Lock()
        self._renders: dict[str, _Render] = {}

    def any_in_flight(self) -> bool:
        """Whether a render is running: work a development restart would throw away."""
        with self._lock:
            return any(not render.done.is_set() for render in self._renders.values())

    def response(self, file_ref) -> tuple[int, bytes | dict]:
        """``(status, body)``: the payload's bytes at 200, 202 while it renders, or a JSON error dict."""
        candidate = resolve_drawing_path(file_ref)
        if candidate is None:
            return 404, {"error": "Not found"}
        from cadgen.drawing_payload import cached_drawing_payload, drawing_payload_key

        key = drawing_payload_key(candidate)
        render = self._joined(key)
        if render is None:
            cached = cached_drawing_payload(key)
            if cached is not None:
                return 200, cached
            render = self._started(key, candidate)
        if render.done.wait(self.hold_seconds):
            return render.status, render.body
        return 202, {"state": "drawing", "retryMs": self.retry_ms}

    def _joined(self, key: str) -> _Render | None:
        """The render of these bytes running, or finished recently enough to answer from."""
        now = self._clock()
        with self._lock:
            finished = sorted((render.finished_at, name) for name, render in self._renders.items() if render.done.is_set())
            surplus = len(finished) - FINISHED_MAX
            for index, (finished_at, name) in enumerate(finished):
                if index < surplus or now - finished_at > FINISHED_SECONDS:
                    del self._renders[name]
            return self._renders.get(key)

    def _started(self, key: str, path: str) -> _Render:
        """The render of these bytes: the one a request started meanwhile, or a new one."""
        with self._lock:
            render = self._renders.get(key)
            if render is not None:
                return render
            render = self._renders[key] = _Render()
        threading.Thread(target=self._render, args=(render, key, path), name="cadgen-drawing", daemon=True).start()
        return render

    def _render(self, render: _Render, key: str, path: str) -> None:
        from cadgen.drawing_payload import render_drawing_payload

        try:
            render.status, render.body = 200, render_drawing_payload(path, key)
        except ValueError as error:
            # A drawing that will not read (``DrawingReadError``): its message says why and what to do.
            render.status, render.body = 400, {"error": str(error)}
        except Exception as error:  # noqa: BLE001 - answered as the GET funnel answers a route's bug
            if self._on_crash is not None:
                self._on_crash(error)
            render.status, render.body = 400, {"error": str(error) or type(error).__name__}
        finally:
            render.finished_at = self._clock()
            render.done.set()
