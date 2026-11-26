"""The library: the one file of what a person keeps in cad, and the note the cache keeps of each file.

``<state>/library.json`` (``places.state_dir``) is one JSON object, written whole::

    {"schema": 1,
     "projects": {"<project id>": {"root": "/abs/folder", "created": 1764000000.0, "opened": 1764000100.0}},
     "files": {"<file id>": {"path": "/abs/file.xbf", "created": 1764000000.0, "opened": 1764000100.0,
                             "pinned": true, "reached": "/abs/as/a/page/named/it.xbf",
                             "shares": {"https://cad.fun": {"link": "https://cad.fun/<share id>",
                                                            "write": "<write secret>", "delete": "<delete secret>",
                                                            "expires": "2026-12-01T10:00:00Z",
                                                            "root": "/abs/project", "entry": "arm.py"}},
                             "imported": "https://cad.fun/<share id>"}}}

A project is a folder a person opened as one, keyed by ``ids.derived_id`` of its canonical ``root``. A file is
a CAD file a page opened, a person pinned, a run wrote as a model's ``.xbf``, ``cad share`` shared or ``cad import``
wrote, keyed by ``ids.file_id`` of its canonical ``path``: ``created`` when the library first knew it, ``opened``
once a page opened it, ``pinned`` only when true, ``reached`` only while a page named it by another path that still
reaches it (a file in a linked folder); ``shares`` only while it is shared, by each share service's origin: the
share's view link, its two keys (the secrets that write and delete it), when it expires, and where the files that
made it are on this computer (their ``root``, and a model's script among them, ``entry``), which
``cad_server.sharing`` keeps; ``imported`` only for a shared file an import wrote, the share's view link it came from,
which then names it here. Nothing else is kept of a document: it is its file, and everything said of it is read
from the file or worked out from its path. An entry goes when it is forgotten (``Library.forget``: a shared
file's keys with it), and with any write once its file is gone, unless it is pinned or a share of it is live: a
pinned file comes back with its file. A share past its expiry goes from its entry as the library is written. The
file is this user's alone to read or write (0600 where the system has modes), since it holds the shares' keys.

``<cache>/documents/<id>/note.json`` (``places.cache_dir``) is what was last seen of the file of that id, with
``picture.png`` beside it::

    {"schema": 1, "version": "1764000000123456789-20480", "parts": 3, "pictured": 1764000100.5}

``version`` is the file's (``state.file_version``) when the note was written, and a note is read only while it
is the file's version now: a file that changed has no count and no picture until one is in hand again (a page
opens it, a run builds it), which replaces the note whole. Nothing is read to fill one. The cache folder
deleted loses nothing that is not made again.

One process writes both, the engine's: a command that shares or imports a file asks it to (``{"op": "share"}``), and
writes the library itself only where no engine answers. A change is a read and a write under one lock of this
process (``state.lock``), landed whole (``state.Folder.write``), so no reader meets half a file; two processes
writing at once (a CAD app's server with no engine under it) can lose one of the two changes (an open's time, a
pin) and corrupt nothing. A library file that does not read is set aside as ``library.json.unreadable`` and
started again.

What an earlier release kept, a record per document (``<state>/documents/<id>/document.json``) and per project
(``<state>/projects/<id>.json``), is carried into the library the first time it is read with them there, and
removed (``Library.migrate``).
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from cad.engine.ids import canonical, derived_id, file_id, is_id
from cad_server.engine.state import Folder, file_version, lock

__all__ = ["LIBRARY", "Library", "Notes", "live", "reaching"]

LIBRARY = "library.json"
SCHEMA = 1
# The library holds the keys of the person's shares: this user's alone to read or write.
MODE = 0o600
# Where the cache keeps what it derived of the file of an id: its note and picture here, its kept checks and a
# board's plots beside them.
DOCUMENTS = "documents"
NOTE = "note.json"
PICTURE = "picture.png"
# What an earlier release kept in the state folder (``Library.migrate``).
_EARLIER = ("documents", "projects", "recents")

# Per state folder: the library as last read, by its file's stamp; and whether its earlier records were looked for.
_READ: dict[str, tuple[Any, dict[str, Any]]] = {}
_LOOKED: set[str] = set()
# Per cache folder and id: the note as last read or written.
_NOTES: dict[tuple[str, str], dict[str, Any]] = {}


def reaching(given: Any, path: str) -> str | None:
    """``given`` while it is another spelling of the file at canonical ``path`` that still reaches it (a path
    through a linked folder); else None."""
    if not isinstance(given, str) or not given or os.path.normcase(given) == os.path.normcase(path):
        return None
    try:
        return given if os.path.normcase(canonical(given)) == os.path.normcase(path) else None
    except (OSError, ValueError):
        return None


def live(share: Any) -> bool:
    """Whether ``share`` (an entry's of ``shares``) is before its expiry, as the share service said it."""
    try:
        when = datetime.fromisoformat(str((share or {}).get("expires")).replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when > datetime.now(timezone.utc)


def _kept(entry: dict[str, Any]) -> bool:
    """Whether a file's ``entry`` stays as the library is written: pinned, its file there, or a share of it live.
    Its shares past their expiry go from it here."""
    shares = entry.get("shares")
    if isinstance(shares, dict):
        for service in [service for service, share in shares.items() if not live(share)]:
            del shares[service]
        if not shares:
            del entry["shares"]
    return bool(entry.get("pinned")) or os.path.isfile(entry["path"]) or bool(entry.get("shares"))


def _empty() -> dict[str, Any]:
    return {"schema": SCHEMA, "projects": {}, "files": {}}


def _parsed(raw: bytes) -> dict[str, Any] | None:
    """The library ``raw`` holds, its entries that name no absolute path left out; None for bytes that are
    no library of this schema."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    found = _empty()
    for section, key in (("projects", "root"), ("files", "path")):
        rows = data.get(section)
        for ident, entry in (rows.items() if isinstance(rows, dict) else ()):
            if is_id(ident) and isinstance(entry, dict) and isinstance(entry.get(key), str) \
                    and os.path.isabs(entry[key]):
                found[section][ident] = entry
    return found


class Library:
    """The library file of the state folder ``state`` (``places.state_dir`` by default); ``cache``: the cache
    folder an earlier release's copies are removed from (``migrate``); ``clock`` says when."""

    def __init__(self, state: Folder | Path | str | None = None, cache: Path | str | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        from cad.engine.places import state_dir

        self.state = state if isinstance(state, Folder) else Folder(state or state_dir())
        self._cache = cache
        self.clock = clock
        # What ``migrate`` did when this object's read ran it: ``{"files", "projects", "skipped"}``; None: nothing.
        self.carried: dict[str, Any] | None = None

    def _lock(self):
        return lock(f"{self.state.root}|library")

    # --- read and change ---------------------------------------------------------------------

    def read(self) -> dict[str, Any]:
        """The library as its file holds it now, parsed once per state of the file. Not to be changed in place:
        ``change`` changes it."""
        with self._lock():
            return self._read()

    def _read(self) -> dict[str, Any]:
        key = str(self.state.root)
        if key not in _LOOKED:
            _LOOKED.add(key)
            if any(self.state.path(name).is_dir() for name in _EARLIER):
                self.migrate()
        path = self.state.path(LIBRARY)
        try:
            found = os.stat(path)
            stamp = (found.st_ino, found.st_mtime_ns, found.st_size)
        except OSError:
            stamp = None
        kept = _READ.get(key)
        if kept is not None and kept[0] == stamp:
            return kept[1]
        data = self._load() if stamp is not None else _empty()
        _READ[key] = (stamp, data)
        return data

    def _load(self) -> dict[str, Any]:
        """The file, parsed; one that does not read set aside (the module) and read as empty."""
        raw = self.state.read(LIBRARY)
        if raw is None:
            return _empty()
        data = _parsed(raw)
        if data is None:
            data = _empty()
            try:
                self.state.write(f"{LIBRARY}.unreadable", raw, MODE)
            except OSError:
                pass
            print(f"cad: {self.state.path(LIBRARY)} does not read: set aside as {LIBRARY}.unreadable, and started "
                  "again", file=sys.stderr, flush=True)
        return data

    def change(self, fn: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
        """``fn(the library)`` changes it in place; written when it differs, without the entries that are not
        pinned, whose file is gone and of which no share is live (``_kept``), and readable by this user alone
        (``MODE``). The read and the write are under one lock. The library as it is then."""
        with self._lock():
            before = self._read()
            data = copy.deepcopy(before)
            fn(data)
            if data == before:
                return before
            data["files"] = {ident: entry for ident, entry in data["files"].items() if _kept(entry)}
            text = json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
            path = self.state.write(LIBRARY, text.encode("utf-8"), MODE)
            found = os.stat(path)
            _READ[str(self.state.root)] = ((found.st_ino, found.st_mtime_ns, found.st_size), data)
            return data

    # --- files -------------------------------------------------------------------------------

    def path_of(self, ident: str) -> str | None:
        """The path of the file of id ``ident``, where the library knows it."""
        entry = self.read()["files"].get(ident)
        return entry["path"] if entry is not None else None

    def know(self, path: str | os.PathLike) -> bool:
        """The file at ``path`` known from now on (``created``), where it was not; whether it was made now."""
        found = canonical(path)
        ident = file_id(found)
        if ident in self.read()["files"]:
            return False
        self.change(lambda data: data["files"].setdefault(ident, {"path": found, "created": self.clock()}))
        return True

    def opened(self, path: str | os.PathLike, reached: str | None = None) -> dict[str, Any]:
        """The file at ``path`` opened on a page now: its entry, made now where it had none. ``reached``: the
        path it was reached by where the page names it by its canonical one (a project's listing knows)."""
        found = canonical(path)
        ident, now = file_id(found), self.clock()
        named = reaching(os.path.normpath(os.path.abspath(path)), found) or reaching(reached, found)

        def change(data: dict[str, Any]) -> None:
            entry = data["files"].setdefault(ident, {"path": found, "created": now})
            entry["opened"] = now
            kept = named or reaching(entry.get("reached"), found)
            if kept:
                entry["reached"] = kept
            else:
                entry.pop("reached", None)

        return self.change(change)["files"][ident]

    def pin(self, path: str | os.PathLike, on: bool) -> None:
        """The file at ``path`` pinned (its entry made where it had none) or not."""
        found = canonical(path)
        ident = file_id(found)

        def change(data: dict[str, Any]) -> None:
            if on:
                data["files"].setdefault(ident, {"path": found, "created": self.clock()})["pinned"] = True
            elif ident in data["files"]:
                data["files"][ident].pop("pinned", None)

        self.change(change)

    def forget(self, ident: str) -> None:
        """The entry of the file of id ``ident`` removed. The file stays."""
        self.change(lambda data: data["files"].pop(ident, None))

    # --- an earlier release's records ----------------------------------------------------------

    def migrate(self) -> dict[str, Any]:
        """What an earlier release recorded, carried into the library and removed: each document record that
        names a file that is there (a file's ``root/home``; a model's or a shape's ``root/saved``) becomes
        that file's entry, with when it was made and opened and whether it was pinned; each project record
        its project. An entry the library has stays as it is. Then the records, the pictures kept beside them
        (``recents/``) and each copy of a model's document in the cache (``documents/<id>/document.xbf``)
        are removed, only once the library has landed. A record that names no file -- 0.11.17's of a model
        names none -- is not carried: its model is listed again, by its ``.xbf``, when its script next runs.
        What was done: ``{"files", "projects", "skipped"}``, the ids of the records not carried."""
        with self._lock():
            now = self.clock()
            found: dict[str, dict[str, Any]] = {"files": {}, "projects": {}}
            skipped: list[str] = []
            for name in self.state.names("documents"):
                record = _record(self.state.read(f"documents/{name}/document.json"))
                root, named = record.get("root"), record.get("home" if record.get("kind") == "file" else "saved")
                try:
                    path = canonical(os.path.join(root, named)) if os.path.isabs(root) else ""
                except (OSError, TypeError, ValueError):
                    path = ""
                if not os.path.isfile(path):
                    skipped.append(name)
                    continue
                times = _times(record)
                found["files"][file_id(path)] = {"path": path, "created": times.get("opened", now), **times,
                                                 **({"pinned": True} if record.get("pinned") is True else {})}
            for name in self.state.names("projects"):
                record = _record(self.state.read(f"projects/{name}"))
                root = record.get("root")
                if isinstance(root, str) and os.path.isabs(root) and f"{derived_id(root)}.json" == name:
                    found["projects"][name[:-5]] = {"root": root, **_times(record)}

            def merge(data: dict[str, Any]) -> None:
                for section, entries in found.items():
                    for ident, entry in entries.items():
                        data[section].setdefault(ident, entry)

            _LOOKED.add(str(self.state.root))
            self.change(merge)
            for name in _EARLIER:
                self.state.remove(name)
            from cad.engine.places import cache_dir

            cache = Folder(self._cache or cache_dir())
            for name in cache.names(DOCUMENTS):
                cache.remove(f"{DOCUMENTS}/{name}/document.xbf")
            self.carried = {"files": len(found["files"]), "projects": len(found["projects"]), "skipped": skipped}
            if any(self.carried.values()):
                print(f"cad: {said(self.carried)}", file=sys.stderr, flush=True)
            return self.carried


def said(carried: dict[str, Any]) -> str:
    """What ``Library.migrate`` did, in one line."""
    return (f"library: carried {carried['files']} files and {carried['projects']} projects from the records of an "
            f"earlier release; {len(carried['skipped'])} not carried")


def _record(raw: bytes | None) -> dict[str, Any]:
    """An earlier release's record as its file holds it; ``{}`` for one that does not read."""
    try:
        record = json.loads(raw or b"")
    except ValueError:
        return {}
    return record if isinstance(record, dict) and record.get("schema") == 1 else {}


def _times(record: dict[str, Any]) -> dict[str, float]:
    """When an earlier release's ``record`` was made and opened, each where it says."""
    return {key: float(record[key]) for key in ("created", "opened")
            if type(record.get(key)) in (int, float) and record[key] > 0}


class Notes:
    """The notes of the cache folder ``cache`` (``places.cache_dir`` by default): see the module."""

    def __init__(self, cache: Folder | Path | str | None = None) -> None:
        from cad.engine.places import cache_dir

        self.cache = cache if isinstance(cache, Folder) else Folder(cache or cache_dir())

    def _lock(self, ident: str):
        return lock(f"{self.cache.root}|{ident}")

    def _kept(self, ident: str) -> dict[str, Any]:
        """The note of id ``ident`` as its file holds it (``{}``: none), read once until it is written."""
        key = (str(self.cache.root), ident)
        note = _NOTES.get(key)
        if note is None:
            try:
                note = json.loads(self.cache.read(f"{DOCUMENTS}/{ident}/{NOTE}") or b"{}")
            except ValueError:
                note = {}
            if not isinstance(note, dict) or note.get("schema") != SCHEMA:
                note = {}
            _NOTES[key] = note
        return note

    def read(self, ident: str, version: str | None) -> dict[str, Any]:
        """What the note of id ``ident`` says of its file at ``version`` (the file's now): ``parts``,
        ``pictured``, each where known; nothing of a file at another version."""
        note = self._kept(ident) if is_id(ident) and version else {}
        return note if note.get("version") == version else {}

    def count(self, path: str | os.PathLike, parts: int, version: str | None = None) -> None:
        """The file at ``path`` holds ``parts`` part occurrences at ``version`` (its version now, by default)."""
        self._fill(path, version, {"parts": int(parts)})

    def picture(self, path: str | os.PathLike, png: bytes) -> None:
        """``png`` kept as the picture of the file at ``path`` as it is now."""
        self._fill(path, None, {"pictured": time.time()}, png)

    def _fill(self, path: str | os.PathLike, version: str | None, fields: dict[str, Any],
              png: bytes | None = None) -> None:
        """``fields`` merged into the file's note where it is of ``version``, else a new note of them alone,
        the picture of the other version gone. A cache folder that cannot be written keeps nothing."""
        found = canonical(path)
        ident = file_id(found)
        version = version or file_version(found)
        if version is None:
            return
        inside = f"{DOCUMENTS}/{ident}"
        with self._lock(ident):
            old = self._kept(ident)
            note = {**(old if old.get("version") == version else {}), "schema": SCHEMA, "version": version, **fields}
            try:
                if png is not None:
                    self.cache.write(f"{inside}/{PICTURE}", png)
                elif "pictured" not in note:
                    self.cache.remove(f"{inside}/{PICTURE}")
                if note != old:
                    text = json.dumps(note, indent=1, sort_keys=True) + "\n"
                    self.cache.write(f"{inside}/{NOTE}", text.encode("utf-8"))
            except OSError:
                return
            _NOTES[(str(self.cache.root), ident)] = note

    def png(self, ident: str, version: str | None) -> bytes | None:
        """The picture of the file of id ``ident`` at ``version``; None where there is none of that version."""
        if "pictured" not in self.read(ident, version):
            return None
        return self.cache.read(f"{DOCUMENTS}/{ident}/{PICTURE}")
