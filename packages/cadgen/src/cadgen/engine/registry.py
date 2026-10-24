"""The registry: one self-describing record per document the engine knows, in the user's state folder.

``<state>/documents/<id>/document.json`` is a document's record: a model built from a script
(``kind: "model"``, ``store: "pointer"``: the script and the function it points at), a shape a
program handed over (``kind: "model"``, ``store: "shape"``: the script that handed it over, or the
folder it was handed over in, its name, and no command that builds it again -- ``run`` empty, and
``shown`` says so in words), or an on-disk CAD file the person opened (``kind: "file"``). The registry POINTS: no geometry, no
mesh, no xbf and no memo is ever written here. A model's record may say that the engine's cache
holds its document (``cache``: ``{revision, bytes, written_at, read}``), whose bytes live in the
cache folder, not here (``Registry.cache``: ``<cache>/documents/<id>/document.xbf``, the engine's
``cache`` module): regenerable, wiped at no loss, never the source of anything; the record is
authoritative, and a cache file missing or unreadable is simply not cached. A ``memory`` document
has no record. Ids are the
documents' own (``ids``: one formula of the canonical path and the name, or a ``key=``'s); the
registry is their reverse map, never their authority.

A record is relocatable: ``root`` is the one absolute folder in it, and ``home`` (the script, or
the file) and ``run`` (the command that builds it again, ``["python", program]``) are relative to it.

The interface is the ``Registry``'s: ``get``, ``put``, ``list``, ``delete`` (records in, records
out) and ``update`` (a read and a write under one lock). The filesystem implementation here is the only one; it is the seam a
hosted store would implement. Every byte written under the state folder by this module goes
through ``Folder``, and every write commits through ``atomic_replace.replace_atomic``. A record is
written synchronously, and only when a field but ``changed`` differs from the one on disk; then
each of ``OBSERVERS`` is told (a mirror uploads in the background: nothing waits on the network).
The cache folder is a second ``Folder``, written the same way; forgetting a document
(``delete``) forgets its cache file too.

The engine imports nothing outside itself (law 3): where the state folder is is the
distribution's to say, through ``FACTORY`` (``cadgen._internal.engine_host``). With none, the
engine records nothing and caches nothing (``current`` is None).
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable

from cadgen.engine.atomic_replace import replace_atomic
from cadgen.engine.ids import is_id

__all__ = ["DOCUMENTS", "FACTORY", "Folder", "OBSERVERS", "RECORD", "Registry", "SCHEMA", "command", "current",
           "detached", "home", "program", "relative"]

SCHEMA = 1
DOCUMENTS = "documents"
RECORD = "document.json"

# Told of every record written (one that changed), after it is on disk; never waited on for more.
OBSERVERS: list[Callable[[dict[str, Any]], None]] = []
# The distribution's: makes the registry of the user's state folder (``cadgen._internal.engine_host``).
FACTORY: Callable[[], "Registry"] | None = None

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_LOCK = threading.Lock()


def current() -> "Registry | None":
    """The registry of the user's state folder, as the distribution makes it; None with none."""
    return FACTORY() if FACTORY is not None else None


class Folder:
    """The user's state folder: the one owner of every byte written under it. Each write lands
    whole (beside its target, then ``replace_atomic``), so a reader never meets half a file."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def path(self, inside: str) -> Path:
        if Path(inside).is_absolute() or ".." in Path(inside).parts:
            raise ValueError(f"{inside} is not a path inside the state folder")
        return self.root / inside

    def write(self, inside: str, data: bytes) -> Path:
        """``data`` at ``inside``, landed whole."""
        return self._land(inside, lambda temporary: temporary.write_bytes(data))

    def copy_in(self, inside: str, source: Path | str) -> Path:
        """``source``'s bytes at ``inside``, landed whole."""
        return self._land(inside, lambda temporary: shutil.copyfile(source, temporary))

    def _land(self, inside: str, fill: Callable[[Path], Any]) -> Path:
        target = self.path(inside)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
        try:
            fill(temporary)
            replace_atomic(temporary, target)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # on Windows the handle that blocked the rename blocks this too: the rename's error is the one
        return target

    def read(self, inside: str) -> bytes | None:
        try:
            return self.path(inside).read_bytes()
        except OSError:
            return None

    def touch(self, inside: str) -> None:
        """A file's modification time, now: when it was last used (the cache's least recently used)."""
        os.utime(self.path(inside))

    def remove(self, inside: str) -> None:
        """A file or a folder, whole; nothing when it is not there."""
        target = self.path(inside)
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target, ignore_errors=True)
            return
        try:
            target.unlink()
        except FileNotFoundError:
            pass

    def names(self, inside: str) -> list[str]:
        try:
            return sorted(os.listdir(self.path(inside)))
        except OSError:
            return []


class Registry:
    """The documents' records under ``<state>/documents`` (see the module)."""

    def __init__(self, state: Folder | Path | str, cache: Folder | Path | str | None = None) -> None:
        self.state = state if isinstance(state, Folder) else Folder(state)
        # Where the engine's cache keeps documents' bytes (``cache``), or None: nothing is cached.
        self.cache = cache if isinstance(cache, Folder) or cache is None else Folder(cache)

    # --- records ----------------------------------------------------------------------------

    def get(self, ident: str) -> dict[str, Any] | None:
        """The record of document ``ident``, or None (none, or a file this schema does not read)."""
        if not is_id(ident):
            return None
        data = self.state.read(f"{DOCUMENTS}/{ident}/{RECORD}")
        if data is None:
            return None
        try:
            record = json.loads(data)
        except ValueError:
            return None
        if not isinstance(record, dict) or record.get("schema") != SCHEMA or record.get("id") != ident:
            return None
        return record

    def put(self, record: dict[str, Any]) -> bool:
        """Write ``record`` (its ``id`` names it); False, and nothing written, when every field but
        ``changed`` is what is on disk. ``created`` is kept from the record it replaces."""
        ident = record["id"]
        if not is_id(ident):
            raise ValueError(f"{ident!r} is not a document id")
        with self._lock(ident):
            old = self.get(ident)
            now = time.time()
            record = {**record, "schema": SCHEMA,
                      "created": (old or {}).get("created") or record.get("created") or now}
            if old is not None and _same(old, record):
                return False
            record["changed"] = now
            text = json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
            self.state.write(f"{DOCUMENTS}/{ident}/{RECORD}", text.encode("utf-8"))
        for observer in list(OBSERVERS):
            try:
                observer(record)
            except Exception:  # noqa: BLE001 - an observer never fails the write it hears
                pass
        return True

    def update(self, ident: str, change: Callable[[dict[str, Any] | None], dict[str, Any] | None]
               ) -> dict[str, Any] | None:
        """``change(the record, or None)`` gives the record to write (None: nothing is), the read and
        the write under one lock; the record as it is then."""
        with self._lock(ident):
            found = change(self.get(ident))
            if found is not None:
                self.put(found)
            return self.get(ident)

    def list(self) -> list[dict[str, Any]]:
        """Every record the registry holds, in no order."""
        return [record for record in (self.get(name) for name in self.state.names(DOCUMENTS)) if record is not None]

    def delete(self, ident: str) -> bool:
        """Forget document ``ident``: its folder, whole, and its cache file in the cache folder."""
        if not is_id(ident):
            return False
        with self._lock(ident):
            there = self.state.path(f"{DOCUMENTS}/{ident}").exists()
            self.state.remove(f"{DOCUMENTS}/{ident}")
            if self.cache is not None:
                self.cache.remove(f"{DOCUMENTS}/{ident}")
        return there

    def root(self, record: dict[str, Any]) -> Path:
        """The folder a record's paths are relative to: its ``root``."""
        return Path(record["root"])

    def _lock(self, ident: str) -> threading.RLock:
        with _LOCKS_LOCK:
            return _LOCKS.setdefault(f"{self.state.root}|{ident}", threading.RLock())


def _same(old: dict[str, Any], new: dict[str, Any]) -> bool:
    return ({key: value for key, value in old.items() if key != "changed"}
            == {key: value for key, value in new.items() if key != "changed"})


def relative(path: Path | str, root: Path | str) -> str:
    """``path`` as a record keeps it: relative to ``root``, with ``/``; absolute where it cannot be
    (another drive)."""
    try:
        return Path(os.path.relpath(os.fspath(path), os.fspath(root))).as_posix()
    except ValueError:
        return Path(path).as_posix()


def home(registry: Registry, record: dict[str, Any]) -> Path:
    """A record's script (a model's) or file (a file's), absolute."""
    return Path(os.path.normpath(registry.root(record) / record["home"]))


def program(registry: Registry, record: dict[str, Any]) -> Path | None:
    """The program whose run builds a model's document again, absolute; None for a file's."""
    run = record.get("run") or []
    return Path(os.path.normpath(registry.root(record) / run[-1])) if run else None


def command(registry: Registry, record: dict[str, Any]) -> str | None:
    """The command that builds a model's document again, as a person types it: ``python`` and the
    program, absolute. The engine never runs it."""
    found = program(registry, record)
    return None if found is None else f"python {shlex.quote(str(found))}"


def detached(registry: Registry, record: dict[str, Any]) -> bool:
    """Whether the script or the file a record points at is gone (moved, deleted). A shape handed
    over points at nothing that builds it: never detached."""
    return record.get("store") != "shape" and not home(registry, record).is_file()
