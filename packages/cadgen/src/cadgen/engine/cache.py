"""The engine's document cache: each model document it held, kept in its own state folder, so a
restart opens every project at once -- with the code still the only source of truth.

For every ``pointer`` and ``shape`` model document (never a file's document: that is its own file),
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
own. The engine reads, writes, sizes and evicts only under ``documents/`` (``DOCUMENTS``), and never
lists, counts or removes anything else there. The record is authoritative: a cache file missing,
or not the size its record says, is simply not cached.

Once per revision: the record gains ``cache: {revision, bytes, written_at, read}``, and a document
whose revision is the cache's is never written again. ``read`` is what the build read, with digests
(``reads``): the script and every module its model reached (each file's bytes, SHA-256) and the
files its bodies read (the closure's own digests), which is what staleness compares (``changes``).

Read: at start the daemon indexes which records have a cache file (``Cache.ensure_index``: a listing
and a stat each, no record and no byte read). A document with one answers every verb by loading its
bytes through the documents worker, as a held document does; loaded, it is in the memory budget's
first tier (read again from disk: evicted first). Bound, as 0.7's store was: past ``cap()`` bytes
(``CADGEN_ENGINE_CACHE_GB``, default ``CACHE_GB``; ``0``: no cache at all), the least recently used
files go down to ``LOW_WATER`` of it, so a pass does not run on every save; never the file of a
document a live worker holds or a page watches. A save that fails is
logged and listed in ``cadgen status``, never raised to anyone: with the state folder read-only the
engine does everything it did, and caches nothing.
"""
from __future__ import annotations

import collections
import hashlib
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

__all__ = ["CACHE_GB", "CACHE_IDLE_SECONDS", "FILE", "SHUTDOWN_SECONDS", "Cache", "cap", "changes", "idle", "reads"]

FILE = "document.xbf"
# How long a document sits with no build and no read before it is saved: past the gap between a
# script's calls and between an edit loop's runs (each run a new revision, saved for nothing), and
# short enough that a model a person stops at is on disk before they close the laptop.
CACHE_IDLE_SECONDS = 10.0
# The cache's size before its least recently used documents go: a few large assemblies.
CACHE_GB = 4.0
# How long a stop waits on the documents built in the last idle window to be saved.
SHUTDOWN_SECONDS = 10.0
# Past the cap, eviction goes down to this share of it.
LOW_WATER = 0.8
# The failed saves ``status`` lists, the latest first.
FAILURES_KEPT = 12


def idle() -> float:
    """``CADGEN_ENGINE_CACHE_IDLE`` seconds (a test's seam), else ``CACHE_IDLE_SECONDS``."""
    try:
        given = float(os.environ.get("CADGEN_ENGINE_CACHE_IDLE", "").strip() or -1)
    except ValueError:
        given = -1.0
    return given if given > 0 else CACHE_IDLE_SECONDS


def cap() -> int:
    """The cache's size cap in bytes: ``CADGEN_ENGINE_CACHE_GB`` (``0``: no cache), else ``CACHE_GB``."""
    try:
        given = float(os.environ.get("CADGEN_ENGINE_CACHE_GB", "").strip() or -1)
    except ValueError:
        given = -1.0
    return int((given if given >= 0 else CACHE_GB) * 2**30)


# --- what a build read, and whether it is what it was -----------------------------------------

_DIGESTS: dict[tuple, str] = {}  # (kind, path, size, mtime_ns) -> digest: a file is hashed once per version
_DIGESTS_KEPT = 4096


def _digest(kind: str, path: str) -> str | None:
    """A file's digest as the build named it: SHA-256 of its bytes for a source and a file read
    through the engine (``memo._file_key``), BLAKE2b-256 for one a body opened itself
    (``memo._read_digest``); None for a file that is not there."""
    try:
        stat = os.stat(path)
    except OSError:
        return None
    version = (kind, path, stat.st_size, stat.st_mtime_ns)
    found = _DIGESTS.get(version)
    if found is not None:
        return found
    hasher = hashlib.blake2b(digest_size=32) if kind == "read" else hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 22), b""):
                hasher.update(chunk)
    except OSError:
        return None
    if len(_DIGESTS) >= _DIGESTS_KEPT:
        _DIGESTS.clear()
    found = _DIGESTS[version] = hasher.hexdigest()
    return found


def reads(closure: dict[str, Any] | None) -> list[list[Any]]:
    """What a build read, by absolute path, from its report's closure (``previous.located``): each
    module its model reached, the script among them (``["source", path, sha256]``, digested now, as
    the build answers), and each file its bodies read (``["file" | "read", path, digest]``, the
    closure's own digests, taken as they were read). A font is named by a family, not read by a
    path the engine can check without the kernel: it is left out."""
    found: list[list[Any]] = []
    for path, _symbols in (closure or {}).get("modules") or []:
        found.append(["source", path, _digest("source", path)])
    for row in (closure or {}).get("inputs") or []:
        if row[0] in ("file", "read") and row[1]:
            found.append([row[0], row[1], row[2]])
    return found


def changes(read: list[list[Any]], root: Path | str) -> list[str]:
    """What differs now from what a build read (``reads``), each said by name, relative to
    ``root``: ``parts.py changed``, ``data/plate.csv is missing``. Empty: the code is as built."""
    said = []
    for kind, path, digest in read:
        now = _digest(kind, path)
        if now == digest:
            continue
        try:
            shown = Path(os.path.relpath(path, root)).as_posix()
        except ValueError:  # another drive
            shown = Path(path).as_posix()
        said.append(f"{shown} is missing" if now is None else f"{shown} changed")
    return said


# --- the daemon's cache ------------------------------------------------------------------------


class Cache:
    """The daemon's half of the cache (see the module): the index of the cache files, each
    document's idle timer, the saves asked of workers, and the writes, all done on one thread of
    its own (``run``), started with the first thing it is told. ``models`` is the daemon's book of
    model documents (``models.Models``)."""

    def __init__(self, models: Any) -> None:
        self.models = models
        self.cap = cap()
        self.idle = idle()
        self.lock = threading.Condition()
        self.indexed = False
        # Each cache file: its bytes, its revision once known, when it was last used (for LRU).
        self.index: dict[str, dict[str, Any]] = {}
        self.due: dict[str, float] = {}  # each document's idle deadline (monotonic)
        self.writes: collections.deque = collections.deque()  # (id, revision, bytes) to write, in order
        self.saving: dict[str, Any] = {}  # a save asked of a worker: that worker
        self.working = 0  # writes taken from the queue and not yet done
        self.failures: collections.deque = collections.deque(maxlen=FAILURES_KEPT)
        self.written = 0
        self.evictions = 0
        self.thread: threading.Thread | None = None

    # --- where -------------------------------------------------------------------------

    def registry(self) -> Any:
        """The registry whose records the cache's files belong to, or None: no state folder, no
        cache folder, or the cache is off (``cap`` 0). Its ``cache`` is the folder the bytes are in."""
        if self.cap <= 0:
            return None
        found = self.models.registry()
        return found if found is not None and found.cache is not None else None

    @staticmethod
    def inside(ident: str) -> str:
        """Where document ``ident``'s bytes are in the cache folder: under ``documents/`` alone."""
        from cadgen.engine.ids import is_id
        from cadgen.engine.registry import DOCUMENTS

        if not is_id(ident):
            raise ValueError(f"{ident!r} is not a document id")
        return f"{DOCUMENTS}/{ident}/{FILE}"

    def ensure_index(self) -> None:
        """Index the cache files once (the module): a listing and a stat each, nothing read."""
        with self.lock:
            if self.indexed:
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
            found[ident] = {"bytes": stat.st_size, "revision": None, "used": stat.st_mtime}
        with self.lock:
            for ident, entry in found.items():
                self.index.setdefault(ident, entry)

    def documents(self) -> list[str]:
        """The ids of the documents with a cache file."""
        self.ensure_index()
        with self.lock:
            return list(self.index)

    def found(self, ident: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Document ``ident``'s record and its ``cache`` field when its cache file is there and is the
        one the record names (its size); None otherwise -- a missing file is forgotten."""
        self.ensure_index()
        with self.lock:
            if ident not in self.index:
                return None
        held = self.registry()
        record = held.get(ident) if held is not None else None
        meta = (record or {}).get("cache")
        if record is None or record.get("kind") != "model" or not isinstance(meta, dict) or not meta.get("revision"):
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
            entry = self.index.get(ident)
            if entry is not None:
                entry["revision"] = meta["revision"]
        return record, meta

    def current(self, ident: str, revision: str | None) -> bool:
        """Whether the cache file of document ``ident`` is at ``revision``."""
        if not revision or self.cap <= 0:
            return False
        self.ensure_index()
        with self.lock:
            entry = self.index.get(ident)
            known = None if entry is None else entry["revision"]
        if entry is None:
            return False
        if known is None:
            found = self.found(ident)
            known = found[1]["revision"] if found is not None else None
        return known == revision

    def read(self, ident: str) -> bytes | None:
        """The bytes of document ``ident``'s cache file, its use noted (least recently used goes
        first); None when it is gone."""
        held = self.registry()
        data = held.cache.read(self.inside(ident)) if held is not None else None
        if data is None:
            with self.lock:
                self.index.pop(ident, None)
            return None
        now = time.time()
        with self.lock:
            entry = self.index.get(ident)
            if entry is not None:
                entry["used"] = now
        try:
            held.cache.touch(self.inside(ident))  # its recency outlives the process
        except OSError:
            pass
        return data

    # --- when ----------------------------------------------------------------------------

    def touch(self, ident: str) -> None:
        """A build or a read of document ``ident``: its idle timer starts again."""
        if self.cap <= 0:
            return
        with self.lock:
            self.due[ident] = time.monotonic() + self.idle
            self._start()
            self.lock.notify_all()

    def keep(self, ident: str, revision: str, data: bytes) -> None:
        """Document ``ident``'s bytes at ``revision`` to write (the drain's, or the daemon's own
        hold): once, unless the cache is at that revision already."""
        if self.cap <= 0 or not data or self.current(ident, revision):
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
        if row is None or row["store"] == "memory" or self.current(ident, row["revision"]):
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
        """The file and its record's ``cache`` field, when the record is still at ``revision``; then
        the least recently used past the cap go."""
        held = self.registry()
        if held is None or self.current(ident, revision):
            return
        record = held.get(ident)
        if record is None or record.get("revision") != revision:
            return  # a build since recorded a newer revision: its own save follows
        if len(data) > self.cap:
            self.failed(ident, f"{len(data)} bytes is past the cache's cap ({self.cap} bytes)")
            return
        row = self.models.row(ident)
        read = (row or {}).get("read") if (row or {}).get("revision") == revision else None
        from cadgen.engine.registry import relative

        root = held.root(record)
        meta = {"revision": revision, "bytes": len(data), "written_at": time.time(),
                "read": [[kind, relative(path, root), digest] for kind, path, digest in read or []]}
        held.cache.write(self.inside(ident), data)
        held.update(ident, lambda found: {**found, "cache": meta}
                    if found is not None and found.get("revision") == revision else None)
        with self.lock:
            self.index[ident] = {"bytes": len(data), "revision": revision, "used": time.time()}
            self.written += 1
        self.models.on_disk(ident, revision)
        self._bound(ident)

    def _bound(self, spare: str) -> None:
        """Past the cap, the least recently used cache files go down to ``LOW_WATER`` of it -- never
        ``spare`` (just written), nor the file of a document a live worker holds or a page watches."""
        with self.lock:
            total = sum(entry["bytes"] for entry in self.index.values())
            if total <= self.cap:
                return
            order = sorted((ident for ident in self.index if ident != spare), key=lambda ident: self.index[ident]["used"])
        kept = self.models.in_use()
        for ident in order:
            if total <= int(self.cap * LOW_WATER):
                break
            if ident in kept:
                continue
            with self.lock:
                entry = self.index.get(ident)
            if entry is None:
                continue
            with self.lock:
                self.evictions += 1  # counted before its file goes: a file gone is an eviction counted
            self.remove(ident)
            total -= entry["bytes"]

    def remove(self, ident: str) -> None:
        """Document ``ident``'s cache file, gone; its record kept, saying so (no ``cache``). The record
        stops naming the file before the file goes, so no record ever names a file that is not there
        (``_write`` writes the file before its record names it)."""
        held = self.registry()
        with self.lock:
            self.index.pop(ident, None)
        if held is None:
            return
        self.models.on_disk(ident, None)
        held.update(ident, lambda found: {key: value for key, value in found.items() if key != "cache"}
                    if found is not None and "cache" in found else None)
        held.cache.remove(f"{self.inside(ident).rsplit('/', 1)[0]}")  # documents/<id>, nothing outside it

    def failed(self, ident: str, error: str) -> None:
        """A save that failed: logged, and listed by ``status``; never raised."""
        with self.lock:
            self.failures.appendleft({"id": ident, "error": error, "at": time.time()})
        print(f"cadgen engine: the cache could not save {ident}: {error}", file=sys.stderr, flush=True)

    # --- the end ---------------------------------------------------------------------------

    def final(self, seconds: float = SHUTDOWN_SECONDS) -> None:
        """At shutdown: every document whose idle timer has not fired yet -- built or read in the last
        window -- saved now, best effort, for ``seconds`` at most."""
        if self.cap <= 0:
            return
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
        """What ``cadgen status`` says of the cache: on or off, its cap, the documents and bytes in it,
        the saves done and the documents evicted for room since start, and the failed saves."""
        held = self.registry()
        found = {"enabled": False, "root": None if held is None else str(held.cache.root), "capBytes": self.cap, "documents": 0, "bytes": 0, "written": self.written,
                 "evictions": self.evictions, "failures": list(self.failures), "idleSeconds": self.idle}
        if held is None:
            return found
        self.ensure_index()
        with self.lock:
            return {**found, "enabled": True, "documents": len(self.index),
                    "bytes": sum(entry["bytes"] for entry in self.index.values())}
