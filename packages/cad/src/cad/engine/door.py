"""The engine's door: how a client reaches the daemon on POSIX, through named pipes (FIFOs) in the
engine's folder and never a socket, so every command works in a sandbox that refuses sockets but
lets a process make and open files in a folder it may write (macOS Seatbelt, deny by default).

The daemon makes one FIFO, the door (``<tag>.door``, beside its lock), and holds it open for
reading and for writing (its own writer, so the door never reads as closed). A client:

1. makes a pair of FIFOs in ``clients/`` in the engine's folder, named by a random id:
   ``<id>.up`` (client to daemon) and ``<id>.down`` (daemon to client), and opens each for
   reading and writing, which never blocks and keeps either from reading as closed before the
   daemon has opened it;
2. writes one hello into the door, its id, a space, the door protocol it speaks and a newline
   (``<id> <protocol>\n``, ``hello``): far below ``PIPE_BUF`` (512 bytes on macOS), so hellos
   written at once never interleave. A door nobody reads refuses the open (``ENXIO``): no engine;
3. waits for the daemon's greeting on ``down`` (``ok <protocol>\n``, ``greeting``), then opens each
   FIFO again for its one direction alone and lets the read-write ends go, so either side's leaving
   is the other's end of file, as a socket's would be; and unlinks the pair's names, which no one
   opens again.

The daemon reads the door in one thread and answers each hello in a thread of its own: it opens
``down`` for writing and ``up`` for reading without blocking or following a link, refuses either
unless it is a FIFO of its own user's, greets, and serves the request and response stream as one
connection. A pair left by a client killed before its greeting is swept, by its age, without being
opened. Nothing here signals or probes a process: liveness is end of file, and a door that refuses
a writer.

Windows has no FIFOs: a client connects to the daemon's loopback port (its port file names it and a
token) and sends the same hello there, the port file's token where a pair's id goes, and the daemon
greets it on the same connection.

The door protocol (``DOOR_PROTOCOL``) is how the hello and greeting can change without a cutover,
since a client and an engine of different releases meet on every device that has kept an app's copy
of an older plugin, or gone back a release. Within one number, only additions: to the hello, to the
greeting and to the operations a connection carries, each new field at the end of its line, which a
reader of that number skips. A removal or a rename takes a new number. Each side reads the other's
number first: the daemon greets with the number the connection speaks, the lower of its own and the
hello's (one it no longer serves: no greeting, the connection closed), and the client speaks that one
or hangs up. The bare forms, ``<id>\n`` and ``ok\n``, are protocol 0: what engines and clients
before the number spoke (0.8's), which both sides still read, and which the daemon answers a bare
hello with.
"""

from __future__ import annotations

import os
import secrets
import selectors
import stat
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable

__all__ = ["CLIENTS", "DOOR_PROTOCOL", "Connection", "Door", "answer", "answering", "dial", "greeted", "greeting",
           "hello", "hello_id", "hello_protocol", "sweep"]

CLIENTS = "clients"
# The door protocol this side speaks: the hello's and the greeting's number (the module's docstring).
DOOR_PROTOCOL = 1
ID_CHARACTERS = 32  # a hello's id: 16 random bytes, in lower-case hex
HELLO_LIMIT = 512  # POSIX's PIPE_BUF floor, macOS's own: a write this size or smaller is atomic
# A pair no connection holds, older than this, is a killed client's: past any client's wait.
STALE_SECONDS = 120.0
# How long a client waits for the daemon's greeting: the door's reader starts a thread and opens
# two FIFOs, so only a wedged daemon takes anywhere near it (a stopping one takes its door away).
GREETING_SECONDS = 15.0

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


def hello(ident: str, protocol: int = DOOR_PROTOCOL) -> bytes:
    """A client's hello: its pair's id, a space and the door protocol it speaks, and a newline, one
    atomic write into the door. Protocol 0 is the bare form, the id alone, which engines before the
    number read."""
    line = (f"{ident} {protocol}\n" if protocol else f"{ident}\n").encode("ascii")
    assert len(line) < HELLO_LIMIT
    return line


def _number(field: bytes) -> int | None:
    """A protocol number: ASCII digits, a few of them."""
    return int(field) if 0 < len(field) <= 6 and field.isdigit() else None


def _hello(line: bytes) -> tuple[str, int] | None:
    """A hello's id and protocol (0 for the bare id), or None for a line that is no hello. Fields
    after the protocol are a later release's additions, skipped."""
    ident, spaced, rest = line.partition(b" ")
    if len(ident) != ID_CHARACTERS or ident.strip(b"0123456789abcdef"):
        return None
    if not spaced:
        return ident.decode("ascii"), 0
    protocol = _number(rest.split(b" ", 1)[0])
    return None if protocol is None else (ident.decode("ascii"), protocol)


def hello_id(line: bytes) -> str | None:
    """The pair id a hello names (the line without its newline), or None for a line that is no hello:
    ``<id>`` (protocol 0) or ``<id> <protocol>``."""
    found = _hello(line)
    return None if found is None else found[0]


def hello_protocol(line: bytes) -> int | None:
    """The door protocol a hello speaks (the line without its newline): 0 for the bare id, None for a
    line that is no hello."""
    found = _hello(line)
    return None if found is None else found[1]


def greeting(protocol: int = DOOR_PROTOCOL) -> bytes:
    """The daemon's greeting for a connection that speaks ``protocol``: ``ok <protocol>`` and a
    newline; protocol 0's is the bare ``ok``, the greeting a bare hello's client reads."""
    return f"ok {protocol}\n".encode("ascii") if protocol else b"ok\n"


def greeted(line: bytes) -> int | None:
    """The door protocol a greeting says the connection speaks (with or without its newline): 0 for
    the bare ``ok``, None for a line that is no greeting. Fields after the protocol are a later
    release's additions, skipped."""
    line = line.removesuffix(b"\n")
    if line == b"ok":
        return 0
    word, spaced, rest = line.partition(b" ")
    return _number(rest.split(b" ", 1)[0]) if word == b"ok" and spaced else None


def pair(folder: Path, ident: str) -> tuple[Path, Path]:
    """A connection's two FIFOs in ``folder`` (the engine's ``clients/``): up to the daemon, down
    to the client."""
    return folder / f"{ident}.up", folder / f"{ident}.down"


def _private(folder: Path) -> bool:
    """Whether ``folder`` (made when missing) is a real folder, this user's, closed to everyone else.
    A folder of this user's opened to others is closed again: it is in the engine's folder, which
    is this user's alone (``places.folder_refusal``), so only this user made it so."""
    folder.mkdir(mode=0o700, exist_ok=True)
    found = os.lstat(folder)
    if stat.S_ISDIR(found.st_mode) and found.st_uid == os.getuid() and found.st_mode & 0o077:
        os.chmod(folder, 0o700)  # a real folder (lstat): no link followed
        found = os.lstat(folder)
    return stat.S_ISDIR(found.st_mode) and found.st_uid == os.getuid() and not found.st_mode & 0o077


def _ours(fd: int) -> bool:
    """Whether an open file is a FIFO of this user's: never a file, a device or another's pipe."""
    found = os.fstat(fd)
    return stat.S_ISFIFO(found.st_mode) and found.st_uid == os.getuid()


def _open(path: Path, flags: int) -> int:
    return os.open(path, flags | _NOFOLLOW | _CLOEXEC)


def answering(door: Path) -> bool:
    """Whether a daemon reads ``door``: a FIFO of this user's that takes a writer. Opened and let go
    at once, writing nothing; no process is signalled."""
    try:
        fd = _open(door, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        return False  # ENXIO: nobody reads it; ENOENT: no door
    try:
        return _ours(fd)
    finally:
        os.close(fd)


class Connection:
    """One connection to the daemon: the lines it reads (``reader``) and writes (``writer``), and the
    door protocol it speaks (``protocol``, the greeting's)."""

    def __init__(self, reader: BinaryIO, writer: BinaryIO, *closing: Any, protocol: int = DOOR_PROTOCOL) -> None:
        self.reader = reader
        self.writer = writer
        self.closing = closing or (reader, writer)
        self.protocol = protocol

    def close(self) -> None:
        for each in self.closing:
            try:
                each.close()
            except OSError:
                pass

    def __enter__(self) -> "Connection":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def dial(door: Path, timeout: float = GREETING_SECONDS, protocol: int = DOOR_PROTOCOL) -> Connection | None:
    """A connection to the daemon reading ``door``, or None when none reads it, it never greets, or
    it greets in a protocol this side does not speak. ``protocol``: the hello's, 0 for the bare form
    an earlier release's engine reads. ``PermissionError`` when this process may not make its pair in
    the engine's folder (a sandbox that forbids writing there)."""
    folder = door.parent / CLIENTS
    ident = secrets.token_hex(ID_CHARACTERS // 2)
    up, down = pair(folder, ident)
    opened: list[int] = []

    def take(path: Path, flags: int) -> int:
        fd = _open(path, flags)
        opened.append(fd)
        return fd

    try:
        if not _private(folder):
            return None
        os.mkfifo(up, 0o600)
        os.mkfifo(down, 0o600)
        hold = take(down, os.O_RDWR)  # reads the greeting; never end of file before it
        early = take(up, os.O_RDWR)  # a writer before the daemon reads: its reads wait, never end
        if not _knock(door, hello(ident, protocol), timeout):
            return None
        spoken = _greeted(hold, door, timeout)
        if spoken is None or spoken > DOOR_PROTOCOL:
            return None
        reader = take(down, os.O_RDONLY | os.O_NONBLOCK)
        writer = take(up, os.O_WRONLY | os.O_NONBLOCK)  # the daemon reads up before it greets
        if not (_ours(reader) and _ours(writer)):
            return None
        os.set_blocking(reader, True)
        os.set_blocking(writer, True)
        for fd in (hold, early):
            opened.remove(fd)
            os.close(fd)
        opened.clear()
        return Connection(open(reader, "rb"), open(writer, "wb"), protocol=spoken)
    except PermissionError:
        raise
    except OSError:
        return None
    finally:
        for fd in opened:
            os.close(fd)
        for path in (up, down):
            try:
                path.unlink()
            except OSError:
                pass


def _knock(door: Path, line: bytes, timeout: float) -> bool:
    """The hello ``line`` written into ``door``; False when no daemon reads it."""
    try:
        fd = _open(door, os.O_WRONLY | os.O_NONBLOCK)
    except PermissionError:
        raise
    except OSError:
        return False  # ENXIO, ENOENT: no engine
    try:
        if not _ours(fd):
            return False
        deadline = time.monotonic() + timeout
        while True:
            try:
                return os.write(fd, line) == len(line)  # all of it or none: below PIPE_BUF
            except BlockingIOError:  # the door's buffer is full of others' hellos, for an instant
                if time.monotonic() > deadline:
                    return False
                time.sleep(0.001)
    finally:
        os.close(fd)


def _greeted(fd: int, door: Path, timeout: float) -> int | None:
    """The door protocol of the daemon's greeting read from ``fd`` (``greeted``), or None. Read a
    byte at a time, to its newline and never past it: what follows on ``down`` is the connection's.
    While it waits, a door that went (its daemon is stopping, and reads no more hellos) ends the
    wait at once."""
    try:
        identity = os.stat(door).st_ino
    except OSError:
        return None
    deadline = time.monotonic() + timeout
    got = b""
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        while not got.endswith(b"\n"):
            if len(got) >= HELLO_LIMIT:
                return None  # no greeting is this long
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            if selector.select(min(left, 0.2)):
                got += os.read(fd, 1)
                continue
            try:
                if os.stat(door).st_ino != identity:
                    return None
            except OSError:
                return None
            if not answering(door):
                return None  # its daemon died after reading the hello: nobody reads the door now
    return greeted(got)


def answer(folder: Path, ident: str, serve: Callable[[BinaryIO, BinaryIO], None], protocol: int = DOOR_PROTOCOL) -> None:
    """The daemon's half of a connection whose hello named ``ident`` and spoke ``protocol``: its pair
    in ``folder`` opened without blocking or following a link, each refused unless it is a FIFO of
    this user's, the greeting sent in the protocol the connection speaks (the lower of the hello's and
    ``DOOR_PROTOCOL``), and ``serve(reader, writer)`` run over it. A client gone before its pair was
    opened is no connection. The pair's names go with it."""
    up, down = pair(folder, ident)
    opened: list[int] = []
    try:
        try:
            # The client holds down open to read before it says hello: a writer's open never waits.
            writer = _open(down, os.O_WRONLY | os.O_NONBLOCK)
            opened.append(writer)
            reader = _open(up, os.O_RDONLY | os.O_NONBLOCK)
            opened.append(reader)
            if not (_ours(writer) and _ours(reader)):
                return
            os.set_blocking(writer, True)
            os.set_blocking(reader, True)
            os.write(writer, greeting(min(protocol, DOOR_PROTOCOL)))
        except OSError:
            return  # ENXIO, ENOENT: the client is gone; ELOOP: a link where a pair should be
        opened.clear()
        with open(reader, "rb") as reading, open(writer, "wb") as writing:
            serve(reading, writing)
    finally:
        for fd in opened:
            os.close(fd)
        for path in (up, down):
            try:
                path.unlink()
            except OSError:
                pass


def sweep(folder: Path, holding: set[str], now: float | None = None, age: float = STALE_SECONDS) -> list[str]:
    """The pairs in ``folder`` no connection holds (``holding``: the ids being answered) and older
    than ``age`` seconds, removed: a client killed before its greeting left them. Each is looked at
    and unlinked, never opened, so a sweep never waits on one."""
    now = time.time() if now is None else now
    removed: list[str] = []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return removed
    for entry in entries:
        ident, _, end = entry.name.partition(".")
        if end not in ("up", "down") or ident in holding:
            continue
        try:
            if now - entry.stat(follow_symlinks=False).st_mtime < age:
                continue
            os.unlink(entry.path)
            removed.append(entry.name)
        except OSError:
            pass
    return removed


class Door:
    """The daemon's door at ``path``: made, read by one thread, each hello answered by
    ``on_hello(ident, protocol)`` in a thread of its own; ``close`` takes it away."""

    def __init__(self, path: Path, on_hello: Callable[[str, int], None]) -> None:
        self.path = path
        self.on_hello = on_hello
        self.clients = path.parent / CLIENTS
        self.holding: set[str] = set()
        self.lock = threading.Lock()
        self.closed = threading.Event()
        path.unlink(missing_ok=True)  # a dead daemon's, whose lock this one holds now
        os.mkfifo(path, 0o600)
        self.read_fd = _open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.write_fd = _open(path, os.O_WRONLY | os.O_NONBLOCK)  # its own writer: never end of file
        os.set_blocking(self.read_fd, True)
        self.identity = os.fstat(self.read_fd).st_ino
        _private(self.clients)
        self.sweep()
        self.thread = threading.Thread(target=self._read, name="cad-door", daemon=True)
        self.thread.start()

    def _read(self) -> None:
        pending = b""
        while not self.closed.is_set():
            try:
                pending += os.read(self.read_fd, 4096)
            except OSError:
                return
            *lines, pending = pending.split(b"\n")
            if len(pending) > HELLO_LIMIT:
                pending = b""  # no hello is this long: dropped up to the next newline
            for line in lines:
                found = _hello(line)
                if found is None or self.closed.is_set():
                    continue
                ident, protocol = found
                with self.lock:
                    if ident in self.holding:
                        continue  # one answer a pair: a second would greet twice and split its stream
                    self.holding.add(ident)
                threading.Thread(target=self._answer, args=(ident, protocol), daemon=True).start()

    def _answer(self, ident: str, protocol: int) -> None:
        try:
            self.on_hello(ident, protocol)
        finally:
            with self.lock:
                self.holding.discard(ident)

    def sweep(self) -> list[str]:
        """The pairs killed clients left (``sweep``), none this door is answering."""
        with self.lock:
            holding = set(self.holding)
        return sweep(self.clients, holding)

    def close(self) -> None:
        """The door taken away: unlinked while it is still this daemon's, its reader woken and
        gone. A client whose hello it did not read sees the door go and stops waiting."""
        if self.closed.is_set():
            return
        self.closed.set()
        try:
            if os.stat(self.path).st_ino == self.identity:
                self.path.unlink()
        except OSError:
            pass
        try:
            os.write(self.write_fd, b"\n")  # wakes the reader, which sees ``closed``
        except OSError:
            pass
        self.thread.join(5)
        for fd in (self.read_fd, self.write_fd):
            try:
                os.close(fd)
            except OSError:
                pass
