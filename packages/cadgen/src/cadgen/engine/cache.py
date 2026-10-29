"""The engine's document cache: each model document it held, kept in the cache folder until a person
deletes it, so a restart opens every project at once -- with the code still the only source of truth.

For every ``model`` and ``shape`` document (never a file's document: that is its own file),
the engine keeps ``<cache>/documents/<id>/document.xbf`` -- ``<cache>`` the platform's cache folder
the distribution names (``Registry.cache``: ``CADGEN_CACHE_DIR``, else ``$XDG_CACHE_HOME/cadgen`` or
``%LOCALAPPDATA%\\cadgen``, else ``~/.cache/cadgen``), the record staying in the state folder
(``registry``) -- written through a ``registry.Folder`` (``replace_atomic``): the bytes the hold
makes of it (``document.to_bytes``: the document, its closure record and its compiled animation
tracks). It is the engine's own file, always: a model's declared ``@xbf`` or an exported xbf is the
user's artefact, never used as the cache and never pointed at by it.

When it is written, never on the run path:

- **Idle.** Each document has a timer that every build and every read of it sets again
  (``Cache.touch``). Once it has been idle ``idle()`` seconds the daemon asks the worker that holds
  it to save it (``Worker.save``), which that worker does only when no request waits for it (a
  build arriving meanwhile waits for the one serialisation). A document no worker holds is written
  from the bytes the daemon holds.
- **At retirement.** The drain (``models.Models.drain``) hands the bytes it takes to the cache.
- **At shutdown** (``cadgen stop``, a terminate): the documents whose timer has not fired yet --
  built or read in the last idle window -- are saved, best effort, within ``SHUTDOWN_SECONDS``.

The cache folder is shared: a cadgen 0.7 installation keeps its store there too, in folders of its
own. The cache reads, writes, sizes and removes only under ``documents/`` (``DOCUMENTS``; the engine's
bytecode is under ``pycache/``, ``daemon.bytecode``), and never
lists, counts or removes anything else there. The record is authoritative: a cache file missing,
or not the size its record says, is simply not cached.

Once per revision: the record gains ``cache: {revision, bytes}``, and a document
whose revision is the cache's is never written again.

The key covers the format, native material and kernel library versions, system and architecture,
the runtime's Python version and effective dependencies, along with the model's code and inputs.
The closure's separate cadgen release and platform Python fields are descriptive. An explicit build with a changed key rebuilds from source. Reading an older
supported snapshot converts its metadata in memory, leaving these bytes and its build key alone.

Read: at start the daemon indexes which records have a cache file (``Cache.ensure_index``: a listing
and a stat each, no record and no byte read). A document with one answers every verb by loading its
bytes through the documents worker, as a held document does. A run reads it too: a build is handed
the folder (``folder``), and a fresh worker takes any model from its cache file when the
key it holds is the model's (``build._previous``), with nothing run.

Kept: nothing removes a cache file on its own -- no size cap, no least recently used, no age. A
document's file goes only with the document, when a person deletes it (its record and its file
together, ``registry.Registry.delete``). Failed reads, unsupported formats and failed data
migrations preserve the original bytes and record, with a recoverable error. A successful explicit
rebuild may atomically replace an unreadable snapshot. It moves only with its record (``identity.repoint``: a moved
script's record re-attached, a ``key::`` record migrated), landed at the new id before the old goes.
The memory budget is another thing (``serve.Server.trim``): a document that leaves memory for it is
read again from here. A save that fails is logged and listed in
``cadgen status``, never raised to anyone: with the cache folder read-only, or not writable at all,
the engine does everything it did, and saves nothing.
"""
from __future__ import annotations

import collections
import os
import sys
import threading
import time
from typing import Any

__all__ = ["CACHE_IDLE_SECONDS", "FILE", "SHUTDOWN_SECONDS", "Cache", "idle"]

FILE = "document.xbf"
# How long a document sits with no build and no read before it is saved: past the gap between a
# script's calls and between an edit loop's runs (each run a new revision, saved for nothing), and
# short enough that a model a person stops at is on disk before they close the laptop.
CACHE_IDLE_SECONDS = 10.0
# How long a stop waits on the documents built in the last idle window to be saved.
SHUTDOWN_SECONDS = 10.0
# The failed saves ``status`` lists, the latest first.
FAILURES_KEPT = 12


def idle() -> float:
    """``CADGEN_ENGINE_CACHE_IDLE`` seconds (a test's seam), else ``CACHE_IDLE_SECONDS``."""
    try:
        given = float(os.environ.get("CADGEN_ENGINE_CACHE_IDLE", "").strip() or -1)
    except ValueError:
        given = -1.0
    return given if given > 0 else CACHE_IDLE_SECONDS


# --- the daemon's cache ------------------------------------------------------------------------


class Cache:
    """The daemon's half of the cache (see the module): the index of the cache files, each
    document's idle timer, the saves asked of workers, and the writes, all done on one thread of
    its own (``run``), started with the first thing it is told. ``models`` is the daemon's book of
    model documents (``models.Models``)."""

    def __init__(self, models: Any) -> None:
        self.models = models
        self.idle = idle()
        self.lock = threading.Condition()
        self.indexed = False
        self.refreshing: set[str] = set()  # rebuilt after a failed read; old bytes stay until replacement
        # Each cache file: its bytes, and its revision once known.
        self.index: dict[str, dict[str, Any]] = {}
        self.due: dict[str, float] = {}  # each document's idle deadline (monotonic)
        self.writes: collections.deque = collections.deque()  # (id, revision, bytes) to write, in order
        self.saving: dict[str, Any] = {}  # a save asked of a worker: that worker
        self.working = 0  # writes taken from the queue and not yet done
        self.failures: collections.deque = collections.deque(maxlen=FAILURES_KEPT)
        self.written = 0
        self.thread: threading.Thread | None = None

    # --- where -------------------------------------------------------------------------

    def registry(self) -> Any:
        """The registry whose records the cache's files belong to, or None: no state folder, or no
        cache folder. Its ``cache`` is the folder the bytes are in."""
        found = self.models.registry()
        return found if found is not None and found.cache is not None else None

    def folder(self) -> str | None:
        """The folder the documents' cache files are in (``documents/`` of the cache folder), which a
        build is handed: a fresh worker takes a model, whatever files it declares, from its cache file
        when it holds the key the model has now (``build._previous``). None with no cache."""
        from cadgen.engine.registry import DOCUMENTS

        held = self.registry()
        return None if held is None else str(held.cache.path(DOCUMENTS))

    @staticmethod
    def inside(ident: str) -> str:
        """Where document ``ident``'s bytes are in the cache folder: under ``documents/`` alone."""
        from cadgen.engine.ids import is_id
        from cadgen.engine.registry import DOCUMENTS

        if not is_id(ident):
            raise ValueError(f"{ident!r} is not a document id")
        return f"{DOCUMENTS}/{ident}/{FILE}"

    def ensure_index(self, *, refresh: bool = False) -> None:
        """Index saved files, refreshing only for an explicit listing/statistics request."""
        with self.lock:
            if self.indexed and not refresh:
                return
            self.indexed = True
        held = self.registry()
        if held is None:
            return
        from cadgen.engine.ids import is_id
        from cadgen.engine.registry import DOCUMENTS

        found = {}
        for ident in held.cache.names(DOCUMENTS):  # only ``documents/``: the rest of the folder is not ours
            if not is_id(ident):
                continue
            try:
                stat = held.cache.path(self.inside(ident)).stat()
            except OSError:
                continue
            found[ident] = {"bytes": stat.st_size, "revision": None}
        with self.lock:
            if refresh:
                self.index = found
            else:
                for ident, entry in found.items():
                    self.index.setdefault(ident, entry)

    def documents(self) -> list[str]:
        """The current saved ids, including documents another running engine just saved."""
        self.ensure_index(refresh=True)
        with self.lock:
            return list(self.index)

    def found(self, ident: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """The current saved record/file pair, including documents another engine just saved."""
        held = self.registry()
        if held is None:
            return None
        with held._lock(ident):
            record = held.get(ident)
            meta = (record or {}).get("cache")
            if record is None or record.get("kind") not in ("model", "shape") or not isinstance(meta, dict) \
                    or not meta.get("revision"):
                return None
            try:
                size = held.cache.path(self.inside(ident)).stat().st_size
            except OSError:
                size = None
            if size != meta.get("bytes"):
                with self.lock:
                    self.index.pop(ident, None)
                return None
            with self.lock:
                self.index[ident] = {"bytes": size, "revision": meta["revision"]}
            return record, meta

    def current(self, ident: str, revision: str | None) -> bool:
        """Whether the shared saved file is at ``revision``, checked against its current record."""
        if not revision:
            return False
        with self.lock:
            if ident in self.refreshing:
                return False
        found = self.found(ident)
        return found is not None and found[1]["revision"] == revision

    def read(self, ident: str, revision: str | None = None) -> bytes | None:
        """Read the saved bytes under the record transaction, optionally at an expected revision."""
        held = self.registry()
        if held is None:
            return None
        with held._lock(ident):
            found = self.found(ident)
            if found is None or revision is not None and found[1]["revision"] != revision:
                return None
            data = held.cache.read(self.inside(ident))
            if data is None:
                with self.lock:
                    self.index.pop(ident, None)
            return data


    # --- when ----------------------------------------------------------------------------

    def touch(self, ident: str) -> None:
        """A build or a read of document ``ident``: its idle timer starts again."""
        with self.lock:
            self.due[ident] = time.monotonic() + self.idle
            self._start()
            self.lock.notify_all()

    def keep(self, ident: str, revision: str, data: bytes) -> None:
        """Document ``ident``'s bytes at ``revision`` to write (the drain's, or the daemon's own
        hold): once, unless the cache is at that revision already."""
        if not data or self.current(ident, revision):
            return
        with self.lock:
            self.writes.append((ident, revision, data))
            self._start()
            self.lock.notify_all()

    def saved(self, worker: Any, header: dict[str, Any], payload: bytes) -> None:
        """A worker's answer to a save (``Worker.save``): written when it is the generation the
        daemon holds of that worker, else dropped (a build since made a newer one)."""
        ident = str(header.get("ident"))
        if header.get("error"):
            self.failed(ident, str(header["error"]))
        else:
            row = self.models.row(ident)
            if row is not None and row["worker"] is worker and row["version"] == header.get("generation"):
                self.keep(ident, row["revision"], payload)
        with self.lock:
            self.saving.pop(ident, None)
            self.lock.notify_all()

    def _start(self) -> None:
        """The cache's thread, started once (call with the lock held)."""
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, name="cadgen-engine-cache", daemon=True)
            self.thread.start()

    def run(self) -> None:
        """Each idle deadline as it passes (``_due``), each write as it is queued (``_write``)."""
        while True:
            with self.lock:
                while True:
                    now = time.monotonic()
                    ready = [ident for ident, at in self.due.items() if at <= now]
                    if ready or self.writes:
                        break
                    wait = min(self.due.values(), default=now + 3600) - now
                    self.lock.wait(max(wait, 0.01))
                for ident in ready:
                    del self.due[ident]
                work = list(self.writes)
                self.writes.clear()
                self.working += len(work)
            for ident in ready:
                try:
                    self._due(ident)
                except Exception as error:  # noqa: BLE001 - a save never fails anyone
                    self.failed(ident, f"{type(error).__name__}: {error}")
            for ident, revision, data in work:
                try:
                    self._write(ident, revision, data)
                except Exception as error:  # noqa: BLE001
                    self.failed(ident, f"{type(error).__name__}: {error}")
                finally:
                    with self.lock:
                        self.working -= 1
                        self.lock.notify_all()

    def _due(self, ident: str) -> None:
        """Document ``ident`` has been idle: saved by the worker that holds it, or from the bytes the
        daemon holds; nothing when the cache is at its revision already."""
        row = self.models.row(ident)
        if row is None or self.current(ident, row["revision"]):
            return
        worker = row["worker"]
        if worker is not None and self.models._working(worker):
            with self.lock:
                self.saving[ident] = worker
            try:
                worker.save(ident, row["source"]["script"], row["source"]["name"], row["version"])
            except (OSError, ValueError) as error:  # its pipe closed: it is going, and is drained first
                with self.lock:
                    self.saving.pop(ident, None)
                    self.lock.notify_all()
                self.failed(ident, str(error))
            return
        data = self.models.held_bytes(ident, row["version"])
        if data is not None:
            self.keep(ident, row["revision"], data)

    def _write(self, ident: str, revision: str, data: bytes) -> None:
        """The file and its record's ``cache`` field, when the record is still at ``revision``."""
        held = self.registry()
        if held is None:
            return
        with held._lock(ident):
            if self.current(ident, revision):
                return
            record = held.get(ident)
            if record is None or record.get("revision") != revision:
                return  # another engine or a newer build owns the shared saved revision
            meta = {"revision": revision, "bytes": len(data)}
            held.cache.write(self.inside(ident), data)
            held.update(ident, lambda found: {**found, "cache": meta}
                        if found is not None and found.get("revision") == revision else None)
            with self.lock:
                self.index[ident] = {"bytes": len(data), "revision": revision}
                self.refreshing.discard(ident)
                self.written += 1

    def refresh(self, ident: str) -> None:
        """A successful build found unreadable saved bytes: replace them on its next save,
        preserving the original file and record until the atomic write succeeds."""
        with self.lock:
            self.refreshing.add(ident)

    def forget(self, ident: str) -> None:
        """Document ``ident`` deleted (``models.delete``): nothing of it is saved from now on -- its idle
        timer, a write queued for it and its index entry go; its file is the registry's to remove
        (``Registry.delete``), and a save under way finds no record to write to."""
        with self.lock:
            self.index.pop(ident, None)
            self.refreshing.discard(ident)
            self.due.pop(ident, None)
            self.writes = collections.deque(row for row in self.writes if row[0] != ident)
            self.lock.notify_all()

    def failed(self, ident: str, error: str) -> None:
        """A save that failed: logged, and listed by ``status``; never raised."""
        with self.lock:
            self.failures.appendleft({"id": ident, "error": error, "at": time.time()})
        print(f"cadgen engine: the cache could not save {ident}: {error}", file=sys.stderr, flush=True)

    # --- the end ---------------------------------------------------------------------------

    def final(self, seconds: float = SHUTDOWN_SECONDS) -> None:
        """At shutdown: every document whose idle timer has not fired yet -- built or read in the last
        window -- saved now, best effort, for ``seconds`` at most."""
        deadline = time.monotonic() + seconds
        with self.lock:
            pending = list(self.due)
            self.due.clear()
        for ident in pending:
            try:
                self._due(ident)
            except Exception as error:  # noqa: BLE001
                self.failed(ident, f"{type(error).__name__}: {error}")
        with self.lock:
            while ((any(worker.alive() for worker in self.saving.values()) or self.writes or self.working)
                   and time.monotonic() < deadline):
                self.lock.wait(max(0.01, min(0.2, deadline - time.monotonic())))

    def status(self) -> dict[str, Any]:
        """What ``cadgen status`` says of the cache: whether there is one, its folder, the documents and
        bytes in it, the saves done since start, and the failed saves."""
        held = self.registry()
        found = {"enabled": False, "root": None if held is None else str(held.cache.root), "documents": 0, "bytes": 0,
                 "written": self.written, "failures": list(self.failures), "idleSeconds": self.idle}
        if held is None:
            return found
        self.ensure_index(refresh=True)
        with self.lock:
            return {**found, "enabled": True, "documents": len(self.index),
                    "bytes": sum(entry["bytes"] for entry in self.index.values())}
