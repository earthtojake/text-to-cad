"""Asynchronous document acquisition in the engine's HTTP application; no relay."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from cadgen.engine.addresses import document_id
from cadgen.engine.ids import is_id

from .backend import absolute_path
from .scanner import node_basename

ENGINE_DOCUMENTS = (".xbf", ".step", ".stp")
SERVE_HOLD_SECONDS = 2.0
FINISHED_SECONDS = 30.0


def engine_document_path(file_ref):
    """The engine document a request names: a document's id as it is, or an on-disk ``.xbf`` or
    STEP's absolute path. A script is no document."""
    if not file_ref:
        raise ValueError("GET /__cad/xbf needs ?file=<a document id, or an absolute document path>")
    if is_id(file_ref):
        return file_ref
    path = absolute_path(file_ref)
    if os.path.splitext(path)[1].lower() not in ENGINE_DOCUMENTS:
        raise ValueError(f"{node_basename(path)} is not a document the cadgen engine reads (.xbf, .step, .stp)")
    if not os.path.isfile(path):
        raise ValueError(f"no document {path}")
    return path


class _Serve:
    """One file's serve, which every request for it joins."""

    __slots__ = ("done", "status", "body", "finished_at")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.status = 500
        self.body: dict = {"error": "the engine's serve stopped before it answered"}
        self.finished_at = 0.0


class EngineDocuments:
    """Acquire each document once in the engine, off the HTTP request thread.

    Concurrent requests for one document -- by its id, however its path is spelled -- join one
    read. ``hold_seconds`` bounds the time a caller waits before a 202 response; the client uses
    ``retry_ms`` to request again.
    ``on_crash`` hears unexpected failures once.
    """

    def __init__(self, *, hold_seconds: float = SERVE_HOLD_SECONDS, retry_ms: int = 0,
                 server=None, on_crash=None, clock=time.monotonic) -> None:
        self.hold_seconds = hold_seconds
        self.retry_ms = retry_ms
        self.server = server
        self._on_crash = on_crash
        self._clock = clock
        self._lock = threading.Lock()
        self._serves: dict[str, _Serve] = {}  # by document id

    def any_in_flight(self) -> bool:
        """Whether a serve is running: a page is waiting on it."""
        with self._lock:
            return any(not serve.done.is_set() for serve in self._serves.values())

    # --- the serve -------------------------------------------------------------------------

    def response(self, file_ref) -> tuple[int, dict]:
        """``(status, body)``: ``{"doc", "url"}`` at 200, 202 while the engine reads the file, or
        the engine's refusal at 400. ``ValueError`` for a request that names no engine document."""
        path = engine_document_path(file_ref)
        ident = document_id(path)
        serve = self._joined(ident) or self._started(ident, path)
        if serve.done.wait(self.hold_seconds):
            return serve.status, serve.body
        return 202, {"state": "reading", "retryMs": self.retry_ms}

    def held(self, file_ref) -> dict:
        """``{"held": bool}``: whether the engine serves the document now (its daemon lists it),
        asked without starting the daemon or a read."""
        ident = document_id(engine_document_path(file_ref))
        return {"held": self.server is not None and self.server.holds(ident)}

    def _joined(self, ident: str) -> _Serve | None:
        now = self._clock()
        with self._lock:
            for name, serve in list(self._serves.items()):
                if serve.done.is_set() and now - serve.finished_at > FINISHED_SECONDS:
                    del self._serves[name]
            return self._serves.get(ident)

    def _started(self, ident: str, path: str) -> _Serve:
        with self._lock:
            serve = self._serves.get(ident)
            if serve is not None:
                return serve
            serve = self._serves[ident] = _Serve()
        threading.Thread(target=self._run, args=(serve, path), name="cadgen-engine-serve", daemon=True).start()
        return serve

    def _run(self, serve: _Serve, path: str) -> None:
        try:
            serve.status, serve.body = 200, self.serve(path)
        except (ConnectionError, OSError, ValueError) as error:
            # The engine's own words for a file it will not serve, or a daemon that would not start.
            serve.status, serve.body = 400, {"error": str(error) or type(error).__name__}
        except Exception as error:  # noqa: BLE001 - answered as the GET funnel answers a route's bug
            if self._on_crash is not None:
                self._on_crash(error)
            serve.status, serve.body = 400, {"error": str(error) or type(error).__name__}
        finally:
            serve.finished_at = self._clock()
            serve.done.set()

    def serve(self, path: str) -> dict:
        if self.server is None:
            raise ValueError("documents are served by the installation's engine")
        if is_id(path):
            # Served as the engine holds it, by its daemon: never built (``Daemon`` ``serve``).
            from cadgen.engine.client import request

            answer = request({"op": "serve", "path": path})
            if not answer or "failed" in answer:
                raise ValueError((answer or {}).get("failed", "engine did not answer"))
            ident = answer["doc"]
        else:
            ident = self.server.add(Path(path))
        return {"doc": ident, "url": f"/__cad/api/doc/{ident}"}
