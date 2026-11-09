"""The manufacturing checks' results the daemon keeps, so the same check of an unchanged document
measures nothing (``Daemon.check``), and the checks processes that measure the checks no warm worker does
(``Pool``).

A result is kept under its document and the version of it that was measured: a model document by its
id and its generation (``models.Models``' ``version``: a token of its build's own, kept by a run that
changed nothing in the worker that holds it, new for anything else), a file by its path and the digest of
its bytes. Beside that, the check itself: the document type, the process, the resolved options, the
candidates flag and, with no process, the options given, the release of the library that measured it, the
caller's (``Daemon.check`` measures nothing in another's), and the digest of that library's code
(``contract.measuring``'s ``code``), so a checkout's edited copy of a release and the published one never share
a result. What measured it -- that code and the versions of the libraries a check measures with, the measuring
process's ``contract.measuring`` -- is kept with the result (``by``), and the result is served to a caller that
process measures for (``contract.measures_for``: one of other library versions is measured again, the new
result in the old one's place; a caller with no kernel, which names no library, is served whatever its code
measured), so who asks -- a command with no kernel, a script, a restarted engine that has heard from no
process yet -- never decides whether a kept result is found. Only a clean result is kept: never a
document that did not read, a refusal, or a family not measured. A document holds the
results of one version alone: a result of another version is dropped the moment one of the new version
is kept or asked for, so none outlives the document it describes. In memory the store is bounded by
``LIMIT`` results and ``BYTES`` of them (their JSON), the least recently used going first. A part of an
assembly left untouched by an edit is measured again with the rest: a check measures the document whole (its
findings, build volume and rules are the document's), so per-part reuse would be a second, finer key, not
this one.

**On disk** (``Disk``): each kept result is written beside the engine's model cache, under its document's
folder there as every view derived from a document is (``<cache>/documents/<id>/checks/``: a model's id, a
file's document id, ``ids.file_id``), so deleting the document removes them with it
(``registry.Registry.delete``), and a restarted engine answers the same check of the same document from it.
Its version there is one that outlives the engine: a model's revision (its build closure's key, the same code
and inputs the same revision in any process: the key its cache file is kept by; a build with no key has none,
and keeps nothing on disk), a file's bytes' digest. A file's name is the digest of that version and of the
check; it holds both, the result and what measured it. Each is written whole (``registry.Folder.write``), a
document keeps one
version's (a result of another version is removed as one of the new is written), and the whole store is held
to ``DISK_LIMIT`` results and ``DISK_BYTES``, the least recently used (by its time on disk, set again by each
read) going first. One that does not read -- not JSON, not the shape written, another version's or check's under
its name -- is removed, never served, and a document's ``checks/`` folder left empty goes with its last. A cache
folder that cannot be written keeps nothing on disk, and is not tried again until the cache folder is another.
A document's cache file found unreadable takes its folder, and the results in it, with it (``cache.Cache.remove``,
which tells ``Checks.dropped``). A result is
written under the registry's lock of its document (``Registry.lock``), which its deletion holds, and a document
deleted since its check began (``Checks.deleted``, told by ``Registry.delete``) keeps nothing; a deletion drops
the document's entries from the index, and a cache folder wiped (the mark the index was made against, ``MARK``,
gone) is indexed again, the half-written files a stopped engine left (``*.json.*.tmp``) swept as it is.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

__all__ = ["BYTES", "DISK_BYTES", "DISK_LIMIT", "LIMIT", "POOL", "Checks", "Disk", "Pool", "digest", "pool_size"]

# At most this many results kept in memory, and this many bytes of them (their JSON).
LIMIT = 128
BYTES = 64 * 2**20
# At most this many results kept on disk, and this many bytes of them.
DISK_LIMIT = 1024
DISK_BYTES = 256 * 2**20
# The format of a result's file on disk: another is a file that does not read.
FORMAT = 1
# The cache folder's mark the disk's index was made against (``Disk._indexed``): a token, in ``documents/``.
MARK = "documents/.checks-index"


def digest(path: Path) -> str | None:
    """A file's version as a check's key holds it: the digest of its bytes; None when it does not read."""
    found = hashlib.blake2b(digest_size=20)
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                found.update(block)
    except OSError:
        return None
    return found.hexdigest()


class Disk:
    """The kept results on disk (the module's **On disk**), in ``folder()``'s ``documents/``: the engine's
    registry, whose cache folder holds them and whose lock of a document each write holds (``Registry.lock``),
    or a ``registry.Folder`` alone (a test's); None: nothing is kept on disk."""

    def __init__(self, folder: Callable[[], Any], limit: int = DISK_LIMIT, budget: int = DISK_BYTES) -> None:
        self.folder, self.limit, self.budget = folder, limit, budget
        self.lock = threading.Lock()
        # Each result's file, by its place in the cache folder: its size and its time, indexed at the first use,
        # and again once the cache folder's mark (``MARK``) is not the one indexed against (``place``): gone with a
        # folder wiped, or another engine's, made since.
        self.index: dict[str, tuple[int, float]] | None = None
        self.place: bytes | None = None
        self.bytes = 0
        # The cache folder whose mark could not be written (its root): nothing is kept there, nor indexed, until
        # the cache folder is another.
        self.unwritable: Any = None

    def _held(self) -> tuple[Any, Any]:
        """The cache folder and the lock of a document's writes there (``Registry.lock``; none for a folder
        alone), or ``(None, None)``."""
        found = self.folder()
        if found is None:
            return None, None
        if hasattr(found, "lock") and hasattr(found, "cache"):
            return found.cache, found.lock
        return found, None

    @staticmethod
    def _name(version: str, check: str) -> tuple[str, str]:
        found = [hashlib.blake2b(text.encode("utf-8"), digest_size=10).hexdigest() for text in (version, check)]
        return found[0], f"{found[0]}-{found[1]}.json"

    @staticmethod
    def _inside(ident: str, name: str = "") -> str:
        from cad.engine.ids import is_id
        from cad_server.engine.registry import DOCUMENTS

        if not is_id(ident):
            raise ValueError(f"{ident!r} is not a document id")
        return f"{DOCUMENTS}/{ident}/checks" + (f"/{name}" if name else "")

    def _indexed(self, held: Any) -> dict[str, tuple[int, float]]:
        """The index (call with the lock held): every result's file, listed and stated once, nothing read; listed
        again once the folder's mark is gone (a person wiped the cache folder) or not the one it was indexed
        against, the half-written files there swept, and the mark made where there is none."""
        place = held.read(MARK)
        if self.index is not None and place is not None and place == self.place:
            return self.index
        from cad.engine.ids import is_id
        from cad_server.engine.registry import DOCUMENTS

        if place is None:
            place = os.urandom(8).hex().encode("ascii")
            try:
                held.write(MARK, place)
            except OSError:
                # A folder that takes no mark keeps nothing: remembered, so no later use walks it again.
                self.unwritable, self.index, self.bytes, self.place = _root(held), {}, 0, None
                return self.index
        self.unwritable = None
        self.index, self.bytes, self.place = {}, 0, place
        for ident in held.names(DOCUMENTS):
            if not is_id(ident):
                continue
            for name in held.names(self._inside(ident)):
                inside = self._inside(ident, name)
                if ".json." in name and name.endswith(".tmp"):
                    try:
                        held.remove(inside)  # a write a stopped engine left half done
                    except OSError:
                        pass
                    continue
                if not name.endswith(".json"):
                    continue
                try:
                    stat = held.path(inside).stat()
                except OSError:
                    continue
                self.index[inside] = (stat.st_size, stat.st_mtime)
                self.bytes += stat.st_size
        return self.index

    def _remove(self, held: Any, inside: str) -> None:
        try:
            held.remove(inside)
        except OSError:
            pass
        self._remove_entry(inside)
        try:
            os.rmdir(held.path(inside.rsplit("/", 1)[0]))  # the document's ``checks/``, gone with its last result
        except (OSError, ValueError):
            pass  # not empty, or gone already

    def _remove_entry(self, inside: str) -> None:
        found = (self.index or {}).pop(inside, None)
        if found is not None:
            self.bytes -= found[0]

    def get(self, ident: str, version: str, check: str) -> tuple[dict[str, Any], Any] | None:
        """The result kept on disk of ``check`` of document ``ident`` at ``version`` and what measured it
        (``by``), or None; a file that does not read as one is removed."""
        held, _locks = self._held()
        if held is None or (self.unwritable is not None and self.unwritable == _root(held)):
            return None
        _prefix, name = self._name(version, check)
        inside = self._inside(ident, name)
        with self.lock:
            data = held.read(inside)
            if data is None:
                return None
            try:
                found = json.loads(data.decode("utf-8"))
                good = (isinstance(found, dict) and found.get("format") == FORMAT and found.get("version") == version
                        and found.get("check") == check and isinstance(found.get("result"), dict)
                        and isinstance(found.get("by"), dict))
            except (UnicodeDecodeError, ValueError):
                good = False
            if not good:
                self._indexed(held)
                self._remove(held, inside)  # never served: the next check measures and writes it again
                return None
            now = time.time()
            try:
                os.utime(held.path(inside), (now, now))  # read: the most recently used
            except OSError:
                pass
            index = self._indexed(held)
            if inside in index:
                index[inside] = (index[inside][0], now)
            return found["result"], found["by"]

    def keep(self, ident: str, version: str, check: str, result: dict[str, Any], by: Any = None,
             still: Callable[[], bool] = lambda: True) -> None:
        """``result`` written as ``check``'s of document ``ident`` at ``version``, measured ``by``, whole, under
        the registry's lock of the document -- unless ``still()``, asked under it, says the document was deleted
        meanwhile; the document's results of any other version removed, the store held to its bounds. A folder
        that cannot be written keeps nothing, and is not tried again (``unwritable``)."""
        held, locks = self._held()
        if held is None or (self.unwritable is not None and self.unwritable == _root(held)):
            return
        prefix, name = self._name(version, check)
        data = json.dumps({"format": FORMAT, "version": version, "check": check, "result": result,
                           "by": by if isinstance(by, dict) else {}}, separators=(",", ":")).encode("utf-8")
        if len(data) > self.budget:
            return
        inside = self._inside(ident, name)
        with (locks(ident) if locks is not None else contextlib.nullcontext()), self.lock:
            if not still():
                return  # deleted since the check began: its folder is gone, and stays gone
            index = self._indexed(held)
            if self.unwritable is not None:
                return  # no mark could be written: nothing is kept there
            for other in held.names(self._inside(ident)):
                if other.endswith(".json") and not other.startswith(f"{prefix}-"):
                    self._remove(held, self._inside(ident, other))
            try:
                held.write(inside, data)
            except OSError:
                return
            self._remove_entry(inside)
            index[inside] = (len(data), time.time())
            self.bytes += len(data)
            while index and (len(index) > self.limit or self.bytes > self.budget):
                self._remove(held, min(index, key=lambda place: index[place][1]))

    def deleted(self, ident: str) -> None:
        """Document ``ident``'s entries dropped from the index: its folder went with it (``Registry.delete``)."""
        with self.lock:
            if self.index is None:
                return
            mine = f"{self._inside(ident)}/"
            for inside in [inside for inside in self.index if inside.startswith(mine)]:
                self._remove_entry(inside)

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {"held": None if self.index is None else len(self.index), "bytes": self.bytes,
                    **({"unwritable": True} if self.unwritable is not None else {})}


def _root(held: Any) -> Any:
    """A cache folder as ``Disk.unwritable`` remembers it: its root."""
    return getattr(held, "root", held)


class Checks:
    def __init__(self, limit: int = LIMIT, budget: int = BYTES, folder: Callable[[], Any] | None = None) -> None:
        self.limit, self.budget = limit, budget
        self.lock = threading.Lock()
        # (document, check) -> (version, the result's JSON, the document id it is kept on disk under or None, and
        # what measured it), least recently used first.
        self.kept: "OrderedDict[tuple[str, str], tuple[str, str, str | None, Any]]" = OrderedDict()
        self.bytes = 0
        self.measured = 0
        self.reused = 0
        self.restored = 0
        self.read = 0
        self.waited = 0
        # How many times each document id was deleted (``deleted``): a check that began before one keeps nothing.
        self.deletions: dict[str, int] = {}
        # The results on disk, in the engine's cache folder (``folder()``), or none.
        self.disk = Disk(folder) if folder is not None else None

    @staticmethod
    def key(check: dict[str, Any], release: str, code: Any = None) -> str:
        """The check's half of a key: what it asks, which library answers it and the digest of that library's
        code (``contract.measuring``'s ``code``) -- never its token, the caller's ``measures`` it carries, nor the
        libraries' versions, which the result is kept with (``by``) and served by (``get``'s ``serves``)."""
        asked = {name: value for name, value in check.items() if name not in ("token", "measures")}
        return json.dumps({"check": asked, "release": release, "code": code}, sort_keys=True,
                          separators=(",", ":"))

    def _drop(self, document: str, version: str | None = None) -> None:
        for held in [held for held, (kept, _text, _ident, _by) in self.kept.items()
                     if held[0] == document and (version is None or kept != version)]:
            self.bytes -= len(self.kept.pop(held)[1])

    def get(self, document: str, version: str, check: str, durable: tuple[str, str] | None = None,
            serves: Callable[[Any], bool] = lambda _by: True) -> dict[str, Any] | None:
        """The result kept of ``check`` of ``document`` at ``version`` whose measuring process measures for the
        caller (``serves(by)``), or None; results of any other version of it dropped. ``durable``: the document's
        id and the version of it that outlives the engine (the module's **On disk**), where a result is looked
        for when memory holds none, and taken into it."""
        with self.lock:
            self._drop(document, version)
            found = self.kept.get((document, check))
            if found is not None:
                self.kept.move_to_end((document, check))
                if not serves(found[3]):
                    return None  # measured with other libraries than the caller's: measured again, in its place
                self.reused += 1
                return json.loads(found[1])
        if durable is None or self.disk is None:
            return None
        kept = self.disk.get(durable[0], durable[1], check)
        if kept is None:
            return None
        result, by = kept
        self._memory(document, version, check, result, durable[0], by)
        if not serves(by):
            return None
        with self.lock:
            self.reused += 1
            self.restored += 1
        return result

    def epoch(self, ident: str | None) -> int:
        """How many times document ``ident`` was deleted so far: what ``keep``'s ``since`` names."""
        with self.lock:
            return self.deletions.get(ident or "", 0)

    def keep(self, document: str, version: str, check: str, result: dict[str, Any],
             durable: tuple[str, str] | None = None, since: int | None = None, by: Any = None) -> None:
        """``result`` kept as ``check``'s of ``document`` at ``version``, measured ``by`` (the measuring process's
        ``contract.measuring``), the store held to its bounds; on disk too under ``durable`` (``get``'s), where
        one is given. ``since``: the document's ``epoch`` as its check began -- deleted since (``deleted``),
        nothing is kept."""
        ident = durable[0] if durable is not None else None

        def still() -> bool:
            return since is None or self.epoch(ident) == since

        if not still():
            return
        self._memory(document, version, check, result, ident, by)
        if durable is not None and self.disk is not None:
            self.disk.keep(durable[0], durable[1], check, result, by, still)

    def _memory(self, document: str, version: str, check: str, result: dict[str, Any], ident: str | None,
                by: Any = None) -> None:
        text = json.dumps(result, separators=(",", ":"))
        with self.lock:
            if len(text) > self.budget:
                return
            self._drop(document, version)
            old = self.kept.pop((document, check), None)
            if old is not None:
                self.bytes -= len(old[1])
            self.kept[(document, check)] = (version, text, ident, by)
            self.bytes += len(text)
            while self.kept and (len(self.kept) > self.limit or self.bytes > self.budget):
                self.bytes -= len(self.kept.popitem(last=False)[1][1])

    def counted(self, read: bool = False) -> None:
        """One check measured in a process, kept or not; ``read``: it read its document, none held."""
        with self.lock:
            self.measured += 1
            self.read += int(read)

    def attached(self) -> None:
        """One check that waited for the same one running, measuring nothing."""
        with self.lock:
            self.waited += 1

    def forget(self, document: str) -> None:
        """Every result of ``document`` dropped from memory (it was deleted: its folder, and the results on
        disk in it, went with it)."""
        with self.lock:
            self._drop(document)

    def deleted(self, ident: str) -> None:
        """Document id ``ident`` deleted (``Registry.delete``, told under its lock): its results dropped from
        memory and from the disk's index, and a check of it that began before keeps nothing (``epoch``)."""
        with self.lock:
            self.deletions[ident] = self.deletions.get(ident, 0) + 1
            for held in [held for held, (_version, _text, kept, _by) in self.kept.items()
                         if kept == ident or held[0] == f"model:{ident}"]:
                self.bytes -= len(self.kept.pop(held)[1])
        if self.disk is not None:
            self.disk.deleted(ident)

    def dropped(self, ident: str) -> None:
        """Document id ``ident``'s folder in the cache gone with its cache file, which did not read
        (``cache.Cache.remove``): its results on disk went with it, so they leave the disk's index. The document
        is not deleted, and what memory keeps of it stays."""
        if self.disk is not None:
            self.disk.deleted(ident)

    def status(self) -> dict[str, Any]:
        with self.lock:
            found = {"held": len(self.kept), "bytes": self.bytes, "measured": self.measured, "reused": self.reused,
                     "restored": self.restored, "read": self.read, "waited": self.waited}
        found["disk"] = None if self.disk is None else self.disk.status()
        return found


# --- the checks processes ---------------------------------------------------------------------------


# The most checks processes a pool holds by default (``pool_size``).
POOL = 4


def pool_size() -> tuple[int, str | None]:
    """How many checks processes measure at once, and the line said when ``CAD_ENGINE_CHECKS`` was held to its
    bounds: ``CAD_ENGINE_CHECKS`` (one to the machine's cores), else half the machine's cores, one at least and
    ``POOL`` at most -- a small pool, as each is a kernel process of its own."""
    cores = os.cpu_count() or 1
    given = os.environ.get("CAD_ENGINE_CHECKS", "").strip()
    if not given:
        return min(POOL, max(1, cores // 2)), None
    try:
        asked = int(given)
    except ValueError:
        size = min(POOL, max(1, cores // 2))
        return size, f"CAD_ENGINE_CHECKS={given!r} is no number: {size} checks processes"
    size = min(cores, max(1, asked))
    if size != asked:
        return size, f"CAD_ENGINE_CHECKS={asked} held to {size}: one at least, and at most this machine's {cores} cores"
    return size, None


# The key of the checks process of a pool's first slot; the others' are it and their number (``checks-2``).
SLOT = "checks"


class Pool:
    """The checks processes (``services.CHECKS``): ``size`` slots, each a process of its own key, leased one
    check at a time (``take``, ``give``), so as many checks run at once as there are slots. A check takes a free
    slot whose process last measured its document (what it read is still held there: ``worker._file``,
    ``_document``), else a free slot whose process is alive, else a free slot whose process is to start -- where
    the engine's memory has room for one more of a checks process's size beside those being started, and the
    system is not under memory pressure; with no room, it waits for a busy one, as it does when every slot is busy,
    saying so once. While every slot is busy, a check whose caller is still there asks its ``reap`` each time it
    wakes: a check whose callers have all gone gives up its slot to it (``Daemon._reap``). A process is started,
    held to the memory caps and shed by the supervisor as every service's is: an idle one is retired for memory
    with the render processes, and none on a timer."""

    def __init__(self, supervisor: Any, size: int, note: str | None = None) -> None:
        self.supervisor, self.size, self.note = supervisor, max(1, size), note
        self.lock = threading.Condition()
        self.busy: dict[str, float] = {}  # each slot measuring, since when (``time.time``)
        self.last: dict[str, str] = {}  # each slot's last document
        self.rss = 0.0  # the last resident memory a checks process said, in MiB (``size_of``)

    def slots(self) -> list[str]:
        return [SLOT if number == 1 else f"{SLOT}-{number}" for number in range(1, self.size + 1)]

    def _free(self, document: str) -> str | None:
        """The slot a check of ``document`` takes now, or None (call with the lock held)."""
        free = [slot for slot in self.slots() if slot not in self.busy]
        if not free:
            return None
        live = {process.key: process for process in self.supervisor.processes("checks")
                if process.alive() and not process.retired}
        for slot in free:
            if slot in live and self.last.get(slot) == document:
                return slot
        for slot in free:
            if slot in live:
                return slot
        if self.busy and not self._room(live):
            return None
        return free[0]

    def size_of(self, live: dict[str, Any]) -> float:
        """A checks process's resident memory, as the engine knows it (MiB): the largest a live one said, else
        the last one any said (``rss``, kept after it is gone), else the standby's -- a kernel process with the
        kernel loaded and nothing built, what a fresh checks process is -- else the smallest a live worker said;
        0 when no kernel process has said its memory."""
        said = [float(process.rss) for process in live.values() if process.rss]
        if said:
            self.rss = max(said)
            return self.rss
        if self.rss:
            return self.rss
        spare = self.supervisor.standby("worker") if hasattr(self.supervisor, "standby") else None
        if spare is not None and spare.rss:
            return float(spare.rss)
        workers = [float(process.rss) for process in self.supervisor.processes("worker")
                   if process.rss and process.alive() and not process.retired]
        return min(workers, default=0.0)

    def _room(self, live: dict[str, Any]) -> bool:
        """Whether the engine's memory has room for another checks process beside those being started (a busy
        slot whose process is not live yet), each of a checks process's size (``size_of``)."""
        if self.supervisor.pressed():
            return False
        cap = self.supervisor.memory()
        if cap is None:
            return True
        starting = sum(1 for slot in self.busy if slot not in live)
        return self.supervisor.resident() + self.size_of(live) * (starting + 1) <= cap

    def take(self, document: str, gave_up: Callable[[], bool] | None = None,
             waiting: Callable[[str], None] | None = None, reap: Callable[[], None] | None = None,
             defer: Callable[[], bool] | None = None) -> str:
        """A slot for a check of ``document``, waiting for one as long as it takes; ``waiting`` told once, at
        once, what it waits for. ``gave_up``, asked while it waits: true, it waits no more (``Withdrawn``).
        ``reap``, called each time it wakes while every slot is busy: an abandoned check's slot made free.
        ``defer``, asked before it takes a free slot: true (its callers have gone, and a check someone waits for
        waits too), it leaves the slot to that one and waits on."""
        from cad_server.engine.supervisor import GAVE_UP_SECONDS, Withdrawn

        told = False
        while True:
            deferring = defer is not None and defer()
            with self.lock:
                slot = None if deferring else self._free(document)
                if slot is not None:
                    self.busy[slot] = time.time()
                    self.last[slot] = document
                    return slot
                if gave_up is not None and gave_up():
                    raise Withdrawn
                full = len(self.busy) >= self.size
                said = None
                if not told and waiting is not None:
                    ago = max(0.0, time.time() - min(self.busy.values(), default=time.time()))
                    said = (f"waiting for another manufacturing check, started {ago:.0f} s ago: "
                            + (f"the {self.size} checks processes are all busy" if full else
                               "the engine's memory has no room for another checks process"))
            if said is not None:
                told = True
                assert waiting is not None
                waiting(said)
            if full and reap is not None:
                reap()
            with self.lock:
                if deferring or self._free(document) is None:
                    self.lock.wait(GAVE_UP_SECONDS)

    def give(self, slot: str) -> None:
        """A slot free again."""
        with self.lock:
            self.busy.pop(slot, None)
            self.lock.notify_all()

    def status(self) -> dict[str, Any]:
        with self.lock:
            busy = dict(self.busy)
        processes = [{"slot": process.key, "pid": process.pid, "alive": process.alive() and not process.retired,
                      "rssMb": None if process.rss is None else round(process.rss), "busy": process.key in busy}
                     for process in self.supervisor.processes("checks")]
        return {"size": self.size, "busy": len(busy), "processes": processes,
                **({"note": self.note} if self.note else {})}
