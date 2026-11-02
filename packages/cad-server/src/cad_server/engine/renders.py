"""The daemon's pictures of the documents it serves (``Daemon.draw``): each drawn by a render process,
a process of the supervisor's ``render`` service (``services.RENDER``, the library's
``cad.engine.render.service``), one per served document by its id on the server, and one per file no
document by ``file:`` and its path, leased for each picture.

A picture of a version the process does not hold -- a model built again, a file rewritten -- sends
it that version first (``_sync``: the structure and the buffers of the parts it lacks, every part
meshed by the daemon's pool first; a file opened again whenever a file its reader read has
changed), and what the process holds is kept in its ``state``. A process gone before its picture
is asked again of a fresh one, once: a picture is drawn whole or not at all.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any, Callable

from cad_server.engine.supervisor import Gone

__all__ = ["Refused", "Renders", "answer_png"]


class Refused(ValueError):
    """A request the document does not offer, refused by name before anything was drawn."""


class Renders:
    """The served documents' render processes, leased from ``supervisor`` for each picture."""

    def __init__(self, server: Any, supervisor: Any) -> None:
        self.server = server
        self.supervisor = supervisor

    def _sync(self, render: Any, doc: Any) -> dict[str, int]:
        """The process holds the served version: every part meshed (the daemon's pool, for any
        part its cache lacks), and the buffers of the parts the process lacks sent with the
        structure."""
        timings: dict[str, int] = {}
        state = render.state
        if state.get("version") == doc.version:
            return timings
        clock = time.perf_counter()
        meshed = self.server.mesh_all(doc, None)
        structure = self.server.structure(doc)
        timings["meshMs"] = round((time.perf_counter() - clock) * 1000)
        clock = time.perf_counter()
        lacking = sorted({p["key"] for p in structure["prototypes"]} - state.get("keys", set()))
        buffers = []
        for key in lacking:
            data = self.server.cache.get(key)
            if data is None:  # dropped from the cache since: meshed again from the document's shape
                data = self.server._submit(key, self.server.shape_of(doc, key), None).result()[0]
            buffers.append(data)
        answer = render.request({"op": "hold", "path": str(doc.path), "structure": structure,
                                 "meshes": [[key, len(data)] for key, data in zip(lacking, buffers)]},
                                None, b"".join(buffers))
        if "held" not in answer:
            raise RuntimeError(answer.get("failed") or "the renderer would not hold the document")
        state.update(version=doc.version, keys={p["key"] for p in structure["prototypes"]}, held=answer["held"])
        timings["holdMs"] = round((time.perf_counter() - clock) * 1000)
        state["meshed"] = {key: meshed.get(key) for key in ("parts", "meshed", "seconds", "triangles", "mode")}
        return timings

    def _open(self, render: Any, path: Path) -> dict[str, int]:
        """The process holds the file no document at ``path`` as it is now: read again by its
        reader whenever a file it read has changed (``formats.stale``)."""
        from cad.engine.formats import stale

        timings: dict[str, int] = {}
        state = render.state
        if state.get("version") is None or stale(state.get("files") or {}):
            clock = time.perf_counter()
            answer = render.request({"op": "open", "path": str(path)})
            if "refused" in answer:
                raise Refused(answer["refused"])
            if "opened" not in answer:
                raise RuntimeError(answer.get("failed") or f"the renderer could not read {path.name}")
            opened = answer["opened"]
            state.update(version="opened", files=opened["files"], held=opened)
            timings.update(openMs=round((time.perf_counter() - clock) * 1000), readMs=opened["readMs"])
        return timings

    def _frame(self, key: str, label: str, still: dict[str, Any], hold: Callable[[Any], dict[str, int]],
               progress: Any) -> tuple[Any, dict[str, Any], dict[str, int]]:
        """A frame of ``still`` from the render process of ``key`` (``label``, its path), once it holds
        what it draws (``hold``): the process, its answer and what holding took. A process gone is
        asked again of a fresh one, once."""
        for attempt in (1, 2):
            render = self.supervisor.lease("render", key, {}, label=label)
            try:
                timings = hold(render)
                if progress is not None:
                    progress.stage("draw")
                return render, render.request({"op": "frame", "still": still}), timings
            except Gone:
                if attempt == 2:
                    raise
            finally:
                self.supervisor.release(render)
        raise AssertionError("unreachable")

    @staticmethod
    def _drawn(render: Any, answer: dict[str, Any], timings: dict[str, int]) -> tuple[bytes, dict[str, Any]]:
        if "refused" in answer:
            raise Refused(answer["refused"])
        if "done" not in answer:
            raise RuntimeError(answer.get("failed") or "the renderer drew nothing")
        report = answer["done"]
        render.state["frames"] = render.state.get("frames", 0) + 1
        report["timings"] = {**timings, **report.get("timings", {})}
        return answer.get("payload", b""), report

    def _file(self, path: Path, still: dict[str, Any], progress: Any = None) -> tuple[bytes, dict[str, Any]]:
        """A picture of a file no document (``foreign``): its render process, which reads it with
        its reader, asked for a frame. ``progress`` as ``draw`` takes it."""
        if progress is not None:
            progress.stage("scene", detail=path.name)
        render, answer, timings = self._frame(f"file:{path}", str(path), still, lambda held: self._open(held, path),
                                              progress)
        return self._drawn(render, answer, timings)

    def draw(self, path: Path, still: dict[str, Any], progress: Any = None) -> tuple[bytes, dict[str, Any]]:
        """A picture of the served document at ``path``: its render process started, or patched
        to the version served, and asked for a frame. Raises ``Refused`` by name. A file no
        document is read and drawn by a render process of its own (``_file``). ``progress``, a
        ``progress.Progress`` of kind ``snapshot``, is told the stages as they begin: ``scene`` while
        the document is served, meshed and held by its process, ``draw`` while the frame is drawn."""
        from cad.engine.render.service import foreign

        if foreign(Path(path)):
            return self._file(Path(path).resolve(), still, progress)
        started = time.perf_counter()
        if progress is not None:
            progress.stage("scene", detail=Path(path).name)
        ident = self.server.add(Path(path))
        doc = self.server.document(ident)
        served = {"serveMs": round((time.perf_counter() - started) * 1000)}
        render, answer, timings = self._frame(ident, str(doc.path), still, lambda held: self._sync(held, doc), progress)
        data, report = self._drawn(render, answer, {**served, **timings})
        report["mesh"] = render.state.get("meshed")
        return data, report

    def status(self) -> list[dict[str, Any]]:
        """The render processes alive now, a row each."""
        return [{"document": render.label, "pid": render.pid, "version": render.state.get("version"),
                 "held": render.state.get("held"), "frames": render.state.get("frames", 0), "rssMb": render.rss,
                 "alive": True, "busy": render.leased}
                for render in self.supervisor.processes("render") if render.alive() and not render.retired]


def answer_png(data: bytes) -> str:
    """A picture as the daemon's answer carries it on its JSON line."""
    return base64.b64encode(data).decode("ascii")
