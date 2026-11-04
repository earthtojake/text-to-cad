"""``GET /api/v1/documents/kicad_pcb/<id>/glb``: a KiCad board in 3D, KiCad's own GLB of it (its body, copper,
silkscreen, solder mask and parts' 3D models: ``cad_server._internal.boards.model``), for the CAD Viewer's 3D
view of the board.

It is made in the background and never in the way of the board: never on a request's thread, in KiCad's
environment (made on first need, as for an export), at a low priority, and ONE board's at a time, by one
worker. What waits is a queue of boards, the one asked for last first: a board's 2D view asks for it once
it has drawn (``?prepare=1``), so 3D is usually ready by the time a person switches to it, and the 3D view
asks again as it waits, which brings its board to the front. A board whose bytes change (its key,
``plots.BoardAnswers.key``) is made again from its new bytes: the make of the old bytes is stopped (its
process killed) if it is the one running, and its answer, if it lands anyway, is nobody's.

* ``?prepare=1``: never waits. ``200 {"state": "ready", "key", "modelled", "missing"}`` once the model is
  kept (``modelled``: the parts it has a body of, by reference; ``missing``: those whose model file was not
  found, which KiCad draws as nothing, as its own 3D viewer does); ``202 {"state": "queued" | "exporting",
  "progress": {"kind": "board-model", "stage"}, "retryMs"}`` while it waits or is made (``stage`` one of the
  engine's ``progress.STAGES["board-model"]``); 400 with KiCad's reason when it cannot be made (said again
  until the board changes or the server restarts).
* without: the model's bytes, ``model/gltf-binary`` (gzip-coded where the browser takes it: it is kept
  gzipped), ``etag: "<key>"`` and 304 for it; else the same 202 or 400 as ``prepare``.

The model is kept on disk beside the board's plot, by the same key (``boards.MODEL``), and pruned with it: a
reload of an unchanged board is a file read.
"""

from __future__ import annotations

import gzip
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .plots import resolve_plot_path
from .scanner import node_basename

__all__ = ["RETRY_MS", "BoardModels"]

#: How soon a client asks again while a board's model is made.
RETRY_MS = 500
# How long the idle worker waits for another board before it ends (one starts again on the next ask).
_IDLE_SECONDS = 30.0


class BoardModels:
    """The 3D models' queue, worker and answers (see the module). ``key`` is the board's key of a path
    (``BoardAnswers.key``); ``make(board, key, cancel, stage)`` makes and keeps the model and answers what it
    holds, ``kept(board, key)`` what a kept one holds or None, ``read(board, key)`` its gzipped bytes:
    ``boards``' by default, stand-ins in a test."""

    def __init__(self, *, key: Callable[[str], str], make=None, kept=None, read=None, retry_ms: int = RETRY_MS,
                 on_crash=None) -> None:
        from cad_server._internal import boards

        self._key = key
        self._make = make or (lambda board, board_key, cancel, stage: boards.model(board, board_key, cancel=cancel,
                                                                                    stage=stage))
        self._kept = kept or boards.model_kept
        self._read = read or boards.model_bytes
        self.retry_ms = retry_ms
        self._on_crash = on_crash
        self._cond = threading.Condition()
        # The boards waiting, by path, the one asked for last first; each one's state by path.
        self._queue: list[str] = []
        self._state: dict[str, dict[str, Any]] = {}
        self._running: dict[str, Any] | None = None
        self._worker: threading.Thread | None = None

    # ---- the answers -------------------------------------------------------------------------------

    def _board(self, file_ref) -> tuple[str | None, str]:
        candidate = resolve_plot_path(file_ref)
        if candidate is None:
            return None, ""
        if not candidate.lower().endswith(".kicad_pcb"):
            raise ValueError(f"a board's 3D model is a .kicad_pcb's; {node_basename(candidate)} is not one")
        return candidate, self._key(candidate)

    def status(self, file_ref) -> tuple[int, dict[str, Any], str]:
        """``(status, body, key)``: ``prepare``'s answer (the module), the board queued when it is not made."""
        try:
            candidate, board_key = self._board(file_ref)
        except OSError as error:
            return 400, {"error": f"the board could not be read ({error})"}, ""
        if candidate is None:
            return 404, {"error": "Not found"}, ""
        with self._cond:
            state = self._state.get(candidate)
            if state is None or state["key"] != board_key:
                running = self._running
                if running is not None and running["path"] == candidate and running["key"] != board_key:
                    running["cancel"].set()
                state = self._state[candidate] = {"key": board_key, "stage": "queued", "meta": None, "error": None}
            if state["meta"] is None and state["error"] is None:
                found = self._kept(Path(candidate), board_key)
                if found is not None:
                    state["meta"] = found
            if state["meta"] is not None:
                return 200, {"state": "ready", "key": board_key, **state["meta"]}, board_key
            if state["error"] is not None:
                return 400, {"error": state["error"]}, board_key
            running = self._running
            if not (running is not None and running["path"] == candidate and running["key"] == board_key):
                if candidate in self._queue:
                    self._queue.remove(candidate)
                self._queue.insert(0, candidate)
                self._start()
                self._cond.notify_all()
            answer = {"state": "exporting" if state["stage"] != "queued" else "queued",
                      "progress": {"kind": "board-model", "stage": state["stage"]}, "retryMs": self.retry_ms}
        return 202, answer, board_key

    def response(self, file_ref, *, if_none_match: str = "") -> tuple[int, Any, str]:
        """``(status, body, key)``: the model's gzipped bytes at 200, 304 for the key named, else ``status``'s."""
        status, body, board_key = self.status(file_ref)
        if status != 200:
            return status, body, board_key
        if if_none_match and if_none_match.strip() in (f'"{board_key}"', f'W/"{board_key}"'):
            return 304, b"", board_key
        data = self._read(Path(resolve_plot_path(file_ref) or ""), board_key)
        if data is None:
            # Pruned or removed under it: made again.
            with self._cond:
                candidate = resolve_plot_path(file_ref)
                if candidate in self._state:
                    del self._state[candidate]
            return self.status(file_ref)
        return 200, data, board_key

    @staticmethod
    def identity(data: bytes) -> bytes:
        """The model's bytes as they are, from the gzipped ones kept."""
        return gzip.decompress(data)

    # ---- the worker ----------------------------------------------------------------------------------

    def _start(self) -> None:
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._work, name="cad-board-model", daemon=True)
            self._worker.start()

    def _work(self) -> None:
        while True:
            with self._cond:
                if not self._queue:
                    self._cond.wait(_IDLE_SECONDS)
                if not self._queue:
                    self._worker = None
                    return
                path = self._queue.pop(0)
                state = self._state.get(path)
                if state is None or state["meta"] is not None or state["error"] is not None:
                    continue
                board_key, cancel = state["key"], threading.Event()
                self._running = {"path": path, "key": board_key, "cancel": cancel}

            def stage(name: str, path: str = path, board_key: str = board_key) -> None:
                with self._cond:
                    now = self._state.get(path)
                    if now is not None and now["key"] == board_key:
                        now["stage"] = name

            meta, error = None, None
            try:
                meta = self._make(Path(path), board_key, cancel, stage)
            except Exception as failure:  # noqa: BLE001 - KiCad's or the environment's, said to the page
                from cad_server._internal.boards import Cancelled

                if not isinstance(failure, Cancelled):
                    error = str(failure).strip() or type(failure).__name__
                    if self._on_crash is not None and not isinstance(failure, (RuntimeError, OSError)):
                        self._on_crash(failure)
            with self._cond:
                self._running = None
                now = self._state.get(path)
                if now is not None and now["key"] == board_key:
                    if meta is not None:
                        now["meta"] = meta
                    elif error is not None:
                        now["error"] = f"KiCad could not draw the board in 3D: {error}"
                    else:
                        now["stage"] = "queued"  # let go of, its bytes still wanted: asked for again
                self._cond.notify_all()
