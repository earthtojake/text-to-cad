"""The registry: one self-describing record per document the engine knows, in the user's state folder.

``<state>/documents/<id>/document.json`` is a document's record, one shape for every kind:
``{schema, id, kind, root, home, entry, namespace, name, fingerprint?, module?, line?, declares?, relocated?,
revision, built, facts?, program?, cache?, opened?, pinned?, preview?}`` (identity's fields: ``identity``). ``kind`` is ``model``, a model built from a script (``home`` and ``entry``: the
script and the function it points at; the command that builds it again is always ``cadgen run``
of its home); ``shape``, a shape a program handed over (``home``: the script that handed it over,
or the folder it was handed over in; ``program``: that program, where there is one; nothing builds
it again); or ``file``, an on-disk CAD file the person opened (``home`` and ``opened`` alone, and
``pinned`` and ``preview``: never a ``revision``, never bytes). The registry POINTS: no geometry, no
mesh, no xbf and no memo is ever written here. A model's record may say that the engine's cache
holds its document (``cache``: ``{revision, bytes, read}``), whose bytes live in the
cache folder, not here (``Registry.cache``: ``<cache>/documents/<id>/document.xbf``, the engine's
``cache`` module): regenerable, wiped at no loss, never the source of anything; the record is
authoritative, and a cache file missing or unreadable is simply not cached. Ids are the
documents' own (``ids``: one formula of the canonical path and the name); the
registry is their reverse map, never their authority.

A record is relocatable: ``root`` is the one absolute folder in it, and ``home`` (the script, or
the file) and a shape's ``program`` are relative to it.

The interface is the ``Registry``'s: ``get``, ``put``, ``list``, ``delete`` (records in, records
out) and ``update`` (a read and a write under one lock). The filesystem implementation here is the only one; it is the seam a
hosted store would implement. Every byte written under the state folder by this module goes
through ``Folder``, and every write commits through ``atomic_replace.replace_atomic`` -- but a file
made only where none is (``Folder.create``: the page token), which is linked into place. A record is
written synchronously, and only when a field differs from the one on disk; then
each of ``OBSERVERS`` is told (a mirror uploads in the background: nothing waits on the network).
The cache folder is a second ``Folder``, written the same way; forgetting a document
(``delete``) forgets its cache file too.

Beside the documents, ``<state>/engines/token`` is the user's page token, which every engine
serves with, whatever its release (``Registry.token``; the first engine makes it, ``make_token``),
and ``<state>/engines/engine.json`` the engine's record (``Registry.engine``, ``put_engine``, its own
``ENGINE_SCHEMA``): while the default port is another program's, the port the engine rolled to
(``port``). Both are written this user's alone (0600). Links stay valid across restarts and updates
because of them (``daemon.bind``); ``cadgen server --rotate-token`` replaces the token.

A record's shape, and the words said of one (``home``, ``rerun``), are the library's (``records``): a
model's run reads a record of its own in its process, where the registry is not installed. The state and
cache folders are where ``places`` says; ``FACTORY`` makes the registry of another (a test's).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import threading
from pathlib import Path
from typing import Any, Callable

from cad.engine.atomic_replace import replace_atomic
from cad.engine.ids import is_id
from cad.engine.records import (DOCUMENTS, RECORD, SCHEMA, command, detached, home, parse, program, relative, rerun)

__all__ = ["DOCUMENTS", "ENGINES", "ENGINE_FIELDS", "ENGINE_SCHEMA", "FACTORY", "Folder", "OBSERVERS", "RECORD", "Registry", "SCHEMA", "TOKEN", "command", "current",
           "detached", "home", "program", "relative"]

ENGINES = "engines"
# The engine records' own schema: 3 holds, while the default port is another's, the port the
# installation rolled to (and held the installation's token, which is the user's now: ``TOKEN``).
ENGINE_SCHEMA = 3
# What an engine record holds (``put_engine``): one carrying anything else is an earlier build's.
ENGINE_FIELDS = ("port", "schema")
# The user's page token, one for every installation's engine: a link outlives an upgrade.
TOKEN = f"{ENGINES}/token"

# Told of every record written (one that changed), after it is on disk; never waited on for more.
OBSERVERS: list[Callable[[dict[str, Any]], None]] = []
# Makes the registry another way than of the user's state and cache folders (``current``): a test's seam.
FACTORY: Callable[[], "Registry"] | None = None

# A page token as ``secrets.token_urlsafe`` makes one, long enough to guard anything.
_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,256}")

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_LOCK = threading.Lock()


def current() -> "Registry | None":
    """The registry of the user's state folder and its cache folder (``places``), where they are now
    (``CADGEN_STATE_DIR`` and ``CADGEN_CACHE_DIR`` are read each time); ``FACTORY``'s where one is set."""
    if FACTORY is not None:
        return FACTORY()
    from cad.engine.places import cache_dir, state_dir

    return Registry(state_dir(), cache=cache_dir())


class Folder:
    """The user's state folder: the one owner of every byte written under it. Each write lands
    whole (beside its target, then ``replace_atomic``), so a reader never meets half a file."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def path(self, inside: str) -> Path:
        if Path(inside).is_absolute() or ".." in Path(inside).parts:
            raise ValueError(f"{inside} is not a path inside the state folder")
        return self.root / inside

    def write(self, inside: str, data: bytes, mode: int | None = None) -> Path:
        """``data`` at ``inside``, landed whole; with ``mode`` (``0o600``), made with that mode from
        its first byte, so no other user ever reads it."""
        if mode is None:
            return self._land(inside, lambda temporary: temporary.write_bytes(data))

        def fill(temporary: Path) -> None:
            handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), mode)
            with os.fdopen(handle, "wb") as out:
                out.write(data)

        return self._land(inside, fill)

    def create(self, inside: str, data: bytes, mode: int = 0o600) -> bool:
        """``data`` at ``inside`` when nothing is there, made with ``mode`` from its first byte; False,
        and nothing written, when something is. Exclusive and whole: the bytes go to a file of a fresh
        name first, which is then linked to ``inside`` (on Windows renamed, which refuses a name that
        is taken), so of two writers at once exactly one makes it, and no reader meets half of it."""
        target = self.path(inside)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
        handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), mode)
        try:
            with os.fdopen(handle, "wb") as out:
                out.write(data)
            try:
                (os.rename if os.name == "nt" else os.link)(temporary, target)
            except FileExistsError:
                return False
            return True
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

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

    # --- the installation's engine -------------------------------------------------------------

    def token(self) -> str | None:
        """The user's page token (``TOKEN``), or None before the first engine has made one. A token
        file that is there but is not one this user alone could have written and can read (on POSIX:
        another user's, or open to others, as in a state folder others share), cannot be read (its
        mode, its owner), or holds anything but a token's characters (it goes into a cookie and a
        URL) is refused (``ValueError``), naming the file and what is wrong with it: never taken for
        none, so never replaced, which would end every link shared before."""
        path = self.state.path(TOKEN)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as error:
            raise ValueError(f"the page token {path} cannot be read ({_unreadable(path, error)}): make it this "
                             "user's to read (mode 0600) or remove it to make a new one, which ends every link "
                             "shared before") from None
        if os.name != "nt":
            found = os.stat(path)
            if found.st_uid != os.getuid() or found.st_mode & 0o077:
                said = f"mode {stat.S_IMODE(found.st_mode):04o}"
                if found.st_uid != os.getuid():
                    said += f", owned by uid {found.st_uid}, not this user ({os.getuid()})"
                raise ValueError(f"the page token {path} is not this user's alone ({said}): make it this user's "
                                 "alone (mode 0600) or remove it to make a new one, which ends every link shared "
                                 "before")
        token = data.decode("ascii", "replace").strip()
        if _TOKEN.fullmatch(token):
            return token
        raise ValueError(f"the page token {path} holds no token ({len(data)} bytes): remove it to make a new one, "
                         "which ends every link shared before")

    def make_token(self, token: str) -> bool:
        """Make the user's page token ``token`` where there is none, this user's alone; False, and
        nothing written, when there is one (``Folder.create``): of two engines starting at once, one
        makes it and the other serves the one it reads."""
        return self.state.create(TOKEN, (token + "\n").encode("ascii"), mode=0o600)

    def put_token(self, token: str) -> None:
        """Replace the user's page token (``cadgen server --rotate-token``), this user's alone."""
        self.state.write(TOKEN, (token + "\n").encode("ascii"), mode=0o600)

    def engine(self, installation: str) -> dict[str, Any]:
        """The engine record named ``installation`` (``places.NAME``: the device's one engine, so it
        outlives an update): the ``port`` (int) it rolled to
        from a held default, where it has one; ``{}`` with none, or one this schema does not read."""
        data = self.state.read(f"{ENGINES}/{installation}.json")
        try:
            record = json.loads(data) if data is not None else {}
        except ValueError:
            return {}
        if not isinstance(record, dict) or record.get("schema") != ENGINE_SCHEMA:
            return {}
        found: dict[str, Any] = {}
        if type(record.get("port")) is int and 0 < record["port"] < 65536:  # a JSON true is no port
            found["port"] = record["port"]
        return found

    def put_engine(self, installation: str, record: dict[str, Any]) -> None:
        """Write the engine record of ``installation`` (the ``port`` it rolled to when it has one),
        this user's alone."""
        if not installation.isalnum():
            raise ValueError(f"{installation!r} is not an installation")
        kept = {key: record[key] for key in ENGINE_FIELDS if key != "schema" and record.get(key)}
        text = json.dumps({**kept, "schema": ENGINE_SCHEMA}, indent=1, sort_keys=True) + "\n"
        self.state.write(f"{ENGINES}/{installation}.json", text.encode("utf-8"), mode=0o600)

    def root(self, record: dict[str, Any]) -> Path:
        """The folder a record's paths are relative to: its ``root``."""
        return Path(record["root"])

    def _lock(self, ident: str) -> threading.RLock:
        with _LOCKS_LOCK:
            return _LOCKS.setdefault(f"{self.state.root}|{ident}", threading.RLock())


def _unreadable(path: Path, error: OSError) -> str:
    """Why a file is there and cannot be read, in words: the system's, and where it can say them,
    the file's mode and its owner when that is another user."""
    said = error.strerror or type(error).__name__
    try:
        found = os.stat(path)
    except OSError:
        return said
    said += f", mode {stat.S_IMODE(found.st_mode):04o}"
    if hasattr(os, "getuid") and found.st_uid != os.getuid():
        said += f", owned by uid {found.st_uid}, not this user ({os.getuid()})"
    return said
