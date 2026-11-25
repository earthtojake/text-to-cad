"""The state folder's one writer, and what the engine keeps of itself there.

``Folder`` owns every byte written under a folder of the user's (the state folder, ``places.state_dir``, and
the cache folder, ``places.cache_dir``): each write lands whole (beside its target, then
``atomic_replace.replace_atomic``), but a file made only where none is (``Folder.create``: the page token),
which is linked into place. ``lock`` is the one table of locks a read and a write of one file are held under
in this process (the library's, a file's note's: ``library``).

``State`` is the engine's own in the state folder: ``<state>/engines/token``, the user's page token, which the
version's engine serves with, each version holding its own, which a new version imports from the one before so
that a link outlives an update (``State.token``; the first engine makes it, ``make_token``), and
``<state>/engines/engine.json``, the engine's record (``State.engine``, ``put_engine``, its own
``ENGINE_SCHEMA``): while the default port is another program's, the port the engine rolled to (``port``).
Both are written this user's alone (0600). Links stay valid across restarts and updates because of them
(``daemon.bind``); ``cad server --rotate-token`` replaces the token.
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

__all__ = ["ENGINES", "ENGINE_FIELDS", "ENGINE_SCHEMA", "Folder", "State", "TOKEN", "current", "file_version", "lock"]

ENGINES = "engines"
# The engine records' own schema: 3 holds, while the default port is another's, the port the
# installation rolled to (and held the installation's token, which is the user's now: ``TOKEN``).
ENGINE_SCHEMA = 3
# What an engine record holds (``put_engine``): one carrying anything else is an earlier build's.
ENGINE_FIELDS = ("port", "schema")
# The user's page token, one for every engine of a version (each imports the one before's): a link outlives an upgrade.
TOKEN = f"{ENGINES}/token"


def file_version(path: str | os.PathLike) -> str | None:
    """The version of the file at ``path`` as the engine names a file state it read (``mtime_ns-size``, a served
    structure's ``version``), from one stat; None for none there (or no file)."""
    try:
        found = os.stat(path)
    except OSError:
        return None
    return f"{found.st_mtime_ns}-{found.st_size}" if stat.S_ISREG(found.st_mode) else None


# A page token as ``secrets.token_urlsafe`` makes one, long enough to guard anything.
_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,256}")

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_LOCK = threading.Lock()


def lock(key: str) -> threading.RLock:
    """The lock named ``key`` (a folder and what is written in it), the same one each time in this process."""
    with _LOCKS_LOCK:
        return _LOCKS.setdefault(key, threading.RLock())


def current() -> "State":
    """The engine's own in the state folder (``places.state_dir``), where it is now (``CAD_STATE_DIR`` is read
    each time)."""
    from cad.engine.places import state_dir

    return State(state_dir())


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


class State:
    """The page token and the engine's record under ``<state>/engines`` (see the module)."""

    def __init__(self, state: Folder | Path | str) -> None:
        self.state = state if isinstance(state, Folder) else Folder(state)

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
        """Replace the user's page token (``cad server --rotate-token``), this user's alone."""
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
