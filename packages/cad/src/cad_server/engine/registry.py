"""The registry: one self-describing record per document the engine knows, in the state folder
(``places.state_dir``), called ``<state>`` here.

``<state>/documents/<id>/document.json`` is a document's record, one shape for every kind:
``{schema, id, kind, root, home, entry, namespace, name, fingerprint?, module?, relocated?, revision, built,
created?, facts?, saved?, version?, aliases?, program?, opened?, pinned?, preview?}`` (identity's fields:
``identity``). A model's document is its ``.xbf``, and its record is that file's (its id ``ids.file_id`` of it):
``kind`` is ``model``, a model built from a script (``home`` and ``entry``: the script and the function it points
at; the command that builds it again is always ``cad run`` of its home; ``saved``: its ``.xbf``; ``version``: that
file's version as the engine last wrote or kept it, ``mtime_ns-size``, which a run takes it from while the file is
that version: ``build._written_by_engine``); ``shape``, a shape a program handed over (``home``: the script that
handed it over, or the folder it was handed over in; ``program``: that program, where there is one; ``saved``: its
``.xbf``; nothing builds it again); or ``file``, any other CAD file the person opened (``home`` and ``opened``
alone, and ``pinned``, ``preview`` and, where the engine wrote it or read it for a page, ``facts``: its parts'
occurrences and the file's version they are of, ``{parts, version}``, ``Registry.counted``; never a ``revision``,
never bytes). A record from before a model's id was its ``.xbf``'s is carried to that id, its old id one of its
``aliases`` (``identity.carry``, ``Registry.resolve``). The registry POINTS: no geometry, no mesh, no xbf and no
memo is ever written here. Ids are the documents' own (``ids``: one formula of the canonical path and the name);
the registry is their reverse map, never their authority.

A record is relocatable: ``root`` is the one absolute folder in it, and ``home`` (the script, or
the file) and a shape's ``program`` are relative to it.

The interface is the ``Registry``'s: ``get``, ``put``, ``list``, ``delete`` (records in, records
out) and ``update`` (a read and a write under one lock). The filesystem implementation here is the only one; it is the seam a
hosted store would implement. Every byte written under the state folder by this module goes
through ``Folder``, and every write commits through ``atomic_replace.replace_atomic`` -- but a file
made only where none is (``Folder.create``: the page token), which is linked into place. A record is
written synchronously, and only when a field differs from the one on disk; then
each of ``OBSERVERS`` is told (a mirror uploads in the background: nothing waits on the network).
The cache folder is a second ``Folder``, written the same way, which holds the views derived from a file's
bytes (a KiCad board's plots, kept checks: ``documents/<id>/...``); forgetting a document (``delete``) forgets
them too, and its Recents pictures (``preview``: PNGs under
``PICTURES``, which Recents writes and bounds, ``cad_server.viewer.recents``) that no other record names.

Beside the documents, ``<state>/engines/token`` is the user's page token, which the version's engine
serves with, each version holding its own, which a new version imports from the one before so that a link
outlives an update (``Registry.token``; the first engine makes it, ``make_token``), and ``<state>/engines/engine.json`` the engine's record (``Registry.engine``, ``put_engine``, its own
``ENGINE_SCHEMA``): while the default port is another program's, the port the engine rolled to
(``port``). Both are written this user's alone (0600). Links stay valid across restarts and updates
because of them (``daemon.bind``); ``cad server --rotate-token`` replaces the token.

A record's shape, and the words said of one (``home``, ``rerun``), are the library's (``records``): a
model's run reads a record of its own in its process, where the registry is not installed. The state and
cache folders are where ``places`` says (``state_dir``, ``cache_dir``); ``FACTORY`` makes the registry of another (a test's).
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable

from cad.engine.ids import is_id
from cad.engine.records import (DOCUMENTS, RECORD, SCHEMA, command, detached, home, parse, program, relative, rerun,
                                 xbf)
from cad_server.engine.state import _LOCKS_LOCK, Folder, file_version
from cad_server.engine.state import lock as _lock_of

__all__ = ["DOCUMENTS", "FACTORY", "FORGOTTEN", "Folder", "OBSERVERS", "PICTURES", "RECORD", "Registry", "SCHEMA",
           "command", "current", "detached", "file_record", "file_version", "home", "pictures", "program", "relative", "xbf"]

# Where a record's Recents picture is (its ``preview``'s ``thumbnail``: a file name).
PICTURES = "recents/thumbnails"
_PICTURE = re.compile(r"[0-9a-f]{32}\.png")


def file_record(path: str) -> dict[str, Any]:
    """A new record of the CAD file at the canonical path ``path``: where it is, and no time (a page's open
    gives it ``created`` and ``opened``)."""
    from cad.engine.ids import file_id

    folder, name = os.path.dirname(path), os.path.basename(path)
    return {"id": file_id(path), "kind": "file", "root": folder, "home": name, "namespace": folder, "name": name}



def pictures(record: dict[str, Any] | None) -> set[str]:
    """The picture a record's ``preview`` names: its PNG's name under ``PICTURES``, alone, or nothing.
    Anything else in it is not read: a picture only an earlier release's record names (the dark theme's
    it kept beside a board's) is one no record names, which goes once old (``RecentStore``)."""
    preview = (record or {}).get("preview")
    name = preview.get("thumbnail") if isinstance(preview, dict) else None
    return {name} if isinstance(name, str) and _PICTURE.fullmatch(name) else set()


# Told of every record written (one that changed), after it is on disk; never waited on for more.
OBSERVERS: list[Callable[[dict[str, Any]], None]] = []
# Told of every document id deleted (``Registry.delete``), under its lock, its folders gone: what the engine
# keeps of it elsewhere goes too (``checks.Checks.deleted``).
FORGOTTEN: list[Callable[[str], None]] = []
# Makes the registry another way than of the user's state and cache folders (``current``): a test's seam.
FACTORY: Callable[[], "Registry"] | None = None

# Per state folder, each alias a record keeps and that record's id (``Registry.resolve``).
_ALIASES: dict[str, dict[str, str]] = {}


def current() -> "Registry | None":
    """The registry of the state folder and the cache folder (``places.state_dir``, ``places.cache_dir``), where
    they are now (``CAD_STATE_DIR`` and ``CAD_CACHE_DIR`` are read each time); ``FACTORY``'s where one is set."""
    if FACTORY is not None:
        return FACTORY()
    from cad.engine.places import cache_dir, state_dir

    return Registry(state_dir(), cache=cache_dir())


class Registry:
    """The documents' records under ``<state>/documents`` (see the module)."""

    def __init__(self, state: Folder | Path | str, cache: Folder | Path | str | None = None) -> None:
        self.state = state if isinstance(state, Folder) else Folder(state)
        # Where the engine's cache keeps what it derived of documents (``documents/<id>/...``), or None: nothing is.
        self.cache = cache if isinstance(cache, Folder) or cache is None else Folder(cache)

    # --- records ----------------------------------------------------------------------------

    def get(self, ident: str) -> dict[str, Any] | None:
        """The record of document ``ident``, or None (none, or a file this schema does not read)."""
        if not is_id(ident):
            return None
        return parse(ident, self.state.read(f"{DOCUMENTS}/{ident}/{RECORD}"))

    def put(self, record: dict[str, Any]) -> bool:
        """Write ``record`` (its ``id`` names it); False, and nothing written, when every field is
        what is on disk."""
        ident = record["id"]
        if not is_id(ident):
            raise ValueError(f"{ident!r} is not a document id")
        with self._lock(ident):
            record = {**record, "schema": SCHEMA}
            if self.get(ident) == record:
                return False
            text = json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
            self.state.write(f"{DOCUMENTS}/{ident}/{RECORD}", text.encode("utf-8"))
            with _LOCKS_LOCK:
                index = _ALIASES.get(str(self.state.root))
                if index is not None:
                    index.update({alias: ident for alias in record.get("aliases") or [] if is_id(alias)})
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

    def counted(self, ident: str, parts: int, version: str, make: str | None = None) -> None:
        """How many part occurrences the CAD file of id ``ident`` holds, and the file's ``version`` they are of,
        on its record (``facts``: ``{parts, version}``), written only when it differs; with ``make`` (the file's
        canonical path), on a record made for it (``file_record``: no ``opened``, so Recents does not list it) where
        it has none. The count is always one the engine had in hand: the document it wrote the file from (an
        export), or its read of the file. Nothing is read for it here. A model's or a shape's record is its build's:
        never counted here."""
        facts = {"parts": int(parts), "version": str(version)}

        def change(record: dict[str, Any] | None) -> dict[str, Any] | None:
            if record is None and make is not None:
                record = file_record(make)
            if record is None or record.get("kind") != "file":
                return None
            found = {**record, "facts": facts}
            return None if found == record else found

        self.update(ident, change)

    def resolve(self, ident: str) -> str:
        """The id document ``ident`` is known by now: ``ident`` itself where a record is there, or no record keeps
        it; else the id of the record that keeps it among its ``aliases`` -- an id from before a model's id was its
        ``.xbf``'s, or from before its script moved (``identity.carry``). Asked only of an id no record has: the
        records are read once for it, those whose text holds an alias, and then kept up as records are written."""
        if not is_id(ident) or self.state.path(f"{DOCUMENTS}/{ident}/{RECORD}").exists():
            return ident
        found = self._aliases().get(ident)
        record = self.get(found) if found is not None else None
        return found if record is not None and ident in (record.get("aliases") or []) else ident

    def _aliases(self) -> dict[str, str]:
        """Each alias a record keeps, and that record's id: read once a state folder, then kept up (``put``)."""
        key = str(self.state.root)
        with _LOCKS_LOCK:
            index = _ALIASES.get(key)
        if index is not None:
            return index
        index = {}
        for name in self.state.names(DOCUMENTS):
            data = self.state.read(f"{DOCUMENTS}/{name}/{RECORD}") if is_id(name) else None
            if data is None or b'"aliases"' not in data:
                continue
            record = parse(name, data)
            for alias in (record or {}).get("aliases") or []:
                if is_id(alias):
                    index[alias] = name
        with _LOCKS_LOCK:
            return _ALIASES.setdefault(key, index)

    def list(self) -> list[dict[str, Any]]:
        """Every record the registry holds, in no order."""
        return [record for record in (self.get(name) for name in self.state.names(DOCUMENTS)) if record is not None]

    def delete(self, ident: str) -> bool:
        """Forget document ``ident``: its folder, whole, what the cache folder keeps of it (``documents/<id>``), and its
        Recents pictures that no other record names (``forget_pictures``: a record re-pointed under a
        new id keeps the pictures it names)."""
        if not is_id(ident):
            return False
        with self._lock(ident):
            named = pictures(self.get(ident))
            there = self.state.path(f"{DOCUMENTS}/{ident}").exists()
            self.state.remove(f"{DOCUMENTS}/{ident}")
            if self.cache is not None:
                self.cache.remove(f"{DOCUMENTS}/{ident}")
            for forget in list(FORGOTTEN):
                try:
                    forget(ident)
                except Exception:  # noqa: BLE001 - what holds it elsewhere never fails the deletion
                    pass
        self.forget_pictures(named)
        return there

    def forget_pictures(self, names: set[str]) -> None:
        """The pictures ``names`` removed from ``PICTURES``, but those a record still names."""
        names = {name for name in names if _PICTURE.fullmatch(name)}
        if names:
            for name in names - {name for record in self.list() for name in pictures(record)}:
                self.state.remove(f"{PICTURES}/{name}")

    # --- the installation's engine -------------------------------------------------------------

    def root(self, record: dict[str, Any]) -> Path:
        """The folder a record's paths are relative to: its ``root``."""
        return Path(record["root"])

    def lock(self, ident: str) -> threading.RLock:
        """Document ``ident``'s lock, which its writes and its deletion hold: what is written into its folder
        elsewhere (its kept checks, ``checks.Disk``) holds it too, so no write lands in a folder deleted under it."""
        return self._lock(ident)

    def _lock(self, ident: str) -> threading.RLock:
        return _lock_of(f"{self.state.root}|{ident}")
