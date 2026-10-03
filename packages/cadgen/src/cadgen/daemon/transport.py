"""The client/supervisor channel: AF_UNIX on POSIX, AF_PIPE on Windows.

One implementation for both, through ``multiprocessing.connection``. Two transports would
mean two sets of bugs and a POSIX path that drifts as the Windows one gets fixed.

Why not a raw AF_UNIX socket any more: CPython does not expose ``socket.AF_UNIX`` on
Windows, so the daemon could not run there at all. Why not loopback TCP, which would have
kept the socket API: a Unix socket is a filesystem object and gets its access control from
file permissions, so only the owning user can reach it. A TCP port has no such property --
any local process could connect to a channel whose entire purpose is running code. A named
pipe is ACL'd to its creator, so AF_PIPE keeps the guarantee AF_UNIX already gave, and the
authkey handshake below is belt to that braces.

FRAMING. ``Connection`` is message-oriented, so a send is a frame and there is no
newline-delimited parsing, no partial-read buffering, and no half-close: the old protocol
used ``shutdown(SHUT_WR)`` to say "request over", which a message boundary states by
itself. A dead peer is still detected by a failed send rather than by EOF.

VERSIONING. The wire format differs from the newline-JSON one that came before, so the
address carries PROTOCOL. A new client cannot reach an old daemon and misparse it; it
simply finds nothing at the new address and starts its own. The old one idles out and
exits on its own timer.
"""

from __future__ import annotations

import collections
import contextlib
import hashlib
import hmac
import multiprocessing.connection as mpc
import os
import secrets
import socket
import stat
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

# Bump when the wire format changes. It is part of the address, so mismatched peers never
# meet rather than meeting and misreading each other.
PROTOCOL = 2

_AUTHKEY_BYTES = 32

# How long a connected peer has to finish the authkey handshake. Each peer runs it on a
# thread of its own (Server.accept), so this paces no one else: it frees the thread and
# connection of a peer that will never answer -- one whose challenge another thread of
# its own process read off a reused descriptor waits for it forever. A live client
# answers in microseconds; a slow one is a thread whose interpreter a long native call
# holds (a worker submitting children while its body computes), and it answers when that
# call returns.
HANDSHAKE_TIMEOUT_SECONDS = 10.0
# How long accept() waits on one peer's handshake before it accepts the next. Responsive
# clients finish well inside it, so they are still handed out one at a time, in the order
# they connected; a slower one finishes in the background (Server).
HANDSHAKE_HOLD_SECONDS = 0.1


def supported() -> bool:
    """Whether this platform offers a family we can carry the daemon over."""
    return _family() in mpc.families


def _family() -> str:
    return "AF_PIPE" if os.name == "nt" else "AF_UNIX"


def state_dir() -> Path:
    """Where the address, the auth key and the log live.

    ONE derivation, owned by ``cadgen.coordination.paths`` (stdlib-only, imported by the
    viewer too); this is the daemon's spelling of it.
    """
    from cadgen.coordination.paths import state_dir as _state_dir

    return _state_dir()


def address_for(key: str) -> str:
    """The listening address for a given daemon identity.

    A pipe name is not a filesystem path -- it lives in the kernel's pipe namespace, which
    conveniently also sidesteps the ~104 character ceiling on Unix socket paths that the
    hashed name was working around in the first place.
    """
    if os.name == "nt":
        return rf"\\.\pipe\cadgen-daemon-v{PROTOCOL}-{key}"
    return str(state_dir() / f"cadgen-daemon-v{PROTOCOL}-{key}.sock")


def private_address(key: str) -> str:
    """An address for a broker that lives exactly as long as one process.

    Not under :func:`state_dir`: a test's or a checkout's state directory can be deep
    enough to push a Unix socket path past its ~104-byte ceiling, and nothing needs to
    find this address on disk -- the process hands it to its children in their env.
    """
    if os.name == "nt":
        return rf"\\.\pipe\cadgen-b{PROTOCOL}-{key}"
    name = f"cadgen-b{PROTOCOL}-{key}.sock"
    address = Path(tempfile.gettempdir()) / name
    # tempfile honors TMPDIR, which callers may deliberately point at a deep
    # private profile. Keep enough room for macOS' 104-byte sockaddr_un limit;
    # the random authenticated name remains private even in the shared /tmp.
    if len(os.fsencode(address)) >= 100:
        address = Path("/tmp") / name
    return str(address)


def _authkey_path(address: str) -> Path:
    """The credential owned by exactly one daemon address."""
    if os.name != "nt":
        return Path(str(address) + ".key")
    return state_dir() / f"cadgen-daemon-v{PROTOCOL}-{_lock_name(address)}.key"


def read_authkey(address: str) -> bytes | None:
    """The shared secret for this daemon, or None if it has not been created.

    Read unseen by a build's file trace: a parent submitting a child reads it,
    on whichever thread connects, and the daemon's key is never a model's input.
    """
    from cadgen._internal.filetrace import paused

    try:
        with paused():
            return _authkey_path(address).read_bytes().strip() or None
    except OSError:
        return None


def ensure_authkey(address: str) -> bytes:
    """Create the shared secret if absent, and return it -- atomically.

    The daemon calls this only after taking the address's singleton lock and before
    creating its listener. The secret is written to a private temp file and LINKED into
    place: os.link is create-if-absent on every platform. A raced existing file must be
    readable and nonempty; the function never returns a secret that clients cannot read
    from the published path. 0600 on POSIX; on Windows the per-user temp directory is
    already ACL'd to the owner, and the pipe itself is the real access control.
    """
    path = _authkey_path(address)
    existing = read_authkey(address)
    if existing:
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_hex(_AUTHKEY_BYTES).encode("ascii")
    temp = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    with os.fdopen(os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "wb") as handle:
        handle.write(secret)
    try:
        os.link(temp, path)
    except FileExistsError:
        # Someone else created it first; theirs is THE key.
        for _ in range(200):
            existing = read_authkey(address)
            if existing:
                secret = existing
                break
            time.sleep(0.005)
        else:
            raise OSError(f"daemon key exists but is empty or unreadable: {path}")
    finally:
        with contextlib.suppress(OSError):
            temp.unlink()
    if os.name != "nt":
        with contextlib.suppress(OSError):
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return secret


def publish_authkey(address: str, authkey: bytes) -> None:
    """Atomically restore a live lock owner's credential after external damage."""
    from cadgen._internal.atomic_replace import replace_atomic

    if not authkey:
        raise ValueError("daemon authkey must not be empty")
    if keys_match(read_authkey(address), authkey):
        return
    path = _authkey_path(address)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        with os.fdopen(os.open(temp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "wb") as handle:
            handle.write(authkey)
        replace_atomic(temp, path)
        if os.name != "nt":
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        with contextlib.suppress(OSError):
            temp.unlink()


class SingletonLock:
    """An exclusive, non-blocking, process-lifetime lock on a small file.

    The one lock cadgen keeps. It is not a build lock (STORE.md §No locks): it makes the
    daemon a SINGLETON per identity, so two daemons starting at once cannot both bind, and
    it elects the one client that spawns a daemon when none is running. The kernel releases
    it when the holder dies -- no pid file, no liveness inference. POSIX ``flock``; Windows
    ``msvcrt.locking`` on the first byte (mandatory there, which is fine for a file whose
    only content is the lock).
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fd: int | None = None

    def acquire(self) -> bool:
        """True if this process now holds the lock; False if another process does."""
        if self._fd is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        return True

    @property
    def held(self) -> bool:
        return self._fd is not None

    def release(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                with contextlib.suppress(OSError):
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _lock_name(address: str) -> str:
    return hashlib.sha256(str(address).encode("utf-8")).hexdigest()[:16]


def daemon_lock(address: str) -> SingletonLock:
    """The lock a daemon holds while it serves an address: one daemon per ADDRESS. Keyed by
    the socket, not the identity, so a private socket (a test's, a pilot's) is a
    private daemon even when it serves the same cadgen as the user's."""
    return SingletonLock(state_dir() / f"cadgen-daemon-v{PROTOCOL}-{_lock_name(address)}.lock")


def spawn_lock(address: str) -> SingletonLock:
    """The lock the ONE spawning client holds while it starts the daemon for ``address``."""
    return SingletonLock(state_dir() / f"cadgen-daemon-v{PROTOCOL}-{_lock_name(address)}.spawn.lock")


def address_is_stale(address: str) -> bool:
    """Whether a leftover address can be cleaned up before binding.

    Only meaningful on POSIX, where a dead daemon leaves its socket FILE behind and the
    next bind fails with EADDRINUSE until it is removed. A named pipe has no filesystem
    entry: it vanishes with the process that served it, so there is nothing to sweep.
    """
    return os.name != "nt" and Path(address).exists()


def clear_address(address: str) -> None:
    if os.name == "nt":
        return
    try:
        Path(address).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        pass


class Channel:
    """A duplex message channel. Wraps a Connection so callers never see the family."""

    def __init__(self, conn) -> None:
        self._conn = conn
        self._close_guard = threading.Lock()
        self._closed = False

    def send(self, payload: bytes) -> None:
        self._conn.send_bytes(payload)

    def recv(self, timeout: float | None = None) -> bytes | None:
        """One message, or None if nothing arrived within ``timeout``.

        ``poll`` replaces the socket timeout the old code set per read: a daemon that is
        streaming output keeps resetting the clock, so only genuine silence trips it.

        A dead peer is END-OF-STREAM (``b""``), never an exception, and the two platforms
        report it differently: POSIX as EOFError from ``recv_bytes``, Windows as
        BrokenPipeError — an OSError, not an EOFError — raised by ``recv_bytes`` OR by
        ``poll`` itself (PeekNamedPipe fails once the write end is gone and the buffer is
        drained). One shape for callers on both.
        """
        try:
            if timeout is not None and not self._conn.poll(timeout):
                return None
            return self._conn.recv_bytes()
        except EOFError:
            return b""
        except OSError:
            return b""

    def close(self) -> None:
        # Connection.close() is idempotent only when calls are serialized: it
        # clears its integer handle AFTER closing it. Two concurrent callers can
        # therefore both close the same number, and the second can close an
        # unrelated descriptor if the OS reused that number in between. Claim
        # close ownership here, then release the guard before the underlying
        # close so a cancellation never waits behind a blocked receive.
        with self._close_guard:
            if self._closed:
                return
            self._closed = True
        try:
            self._conn.close()
        except OSError:
            pass

    def __enter__(self) -> Channel:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class AuthenticationError(OSError):
    """A live peer rejected the key; never spawn another daemon over it."""


def connect(address: str, authkey: bytes) -> Channel:
    """Open a channel to a listening daemon. Raises OSError when there is none -- including one
    that closes the connection while it is being opened, as a daemon on its way out does (its
    version changed, or it idled out): the caller then spawns or waits for its successor."""
    try:
        return Channel(mpc.Client(address, family=_family(), authkey=authkey))
    except EOFError as exc:
        raise OSError("the geometry service closed the connection while it was opening") from exc
    except mpc.AuthenticationError as exc:
        raise AuthenticationError(
            "The geometry service rejected its local connection key. Its running "
            "process and saved key no longer match; restart the geometry service "
            "after active builds finish."
        ) from exc
    except ValueError as exc:
        raise OSError(str(exc)) from exc


def _wake_pipe_listener(address: str) -> None:
    """Connect and disconnect without waiting for a free pipe or authentication."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    GENERIC_READ = 0x80000000
    GENERIC_WRITE = 0x40000000
    OPEN_EXISTING = 3
    FILE_FLAG_OVERLAPPED = 0x40000000
    ERROR_PIPE_BUSY = 231
    handles = []
    try:
        # CPython PipeListener owns one pending instance and one queued instance.
        # Keep both clients open until connected so a queued instance cannot consume
        # the only wakeup. CreateFile returns PIPE_BUSY immediately; do not use
        # WaitNamedPipe or multiprocessing.Client's retry/authentication loops.
        for _ in range(2):
            handle = create(address, GENERIC_READ | GENERIC_WRITE, 0, None,
                            OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
            if handle == ctypes.c_void_p(-1).value:
                error = ctypes.get_last_error()
                if error == ERROR_PIPE_BUSY:
                    break
                # The Server guard retains the listener through this wakeup, so
                # even a missing pipe is unexpected rather than a close race.
                raise ctypes.WinError(error)
            handles.append(handle)
    finally:
        for handle in handles:
            close(handle)


def _wake_listener(address: str, family: str) -> None:
    if family == "AF_PIPE":
        _wake_pipe_listener(address)
        return
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as wakeup:
        wakeup.settimeout(0.1)
        with contextlib.suppress(OSError):
            wakeup.connect(address)


class _Deadline:
    """A connection whose handshake reads must all arrive before one deadline.

    The stdlib handshake calls ``send_bytes`` and ``recv_bytes`` and nothing else.
    Polling before each read turns silence into TimeoutError; a message that has begun
    to arrive is read whole, as every handshake message is one small write (one pipe
    message).
    """

    def __init__(self, connection, timeout: float) -> None:
        self._connection = connection
        self._deadline = time.monotonic() + timeout

    def send_bytes(self, payload) -> None:
        self._connection.send_bytes(payload)

    def recv_bytes(self, maxlength=None) -> bytes:
        if not self._connection.poll(max(0.0, self._deadline - time.monotonic())):
            raise TimeoutError("the peer did not finish the authkey handshake in time")
        return self._connection.recv_bytes(maxlength)


def _authenticate(connection, authkey: bytes, timeout: float) -> None:
    """What ``mpc.Listener.accept`` runs after its native accept, within ``timeout``.

    The same two stdlib calls in the same order, so the challenges, their MACs and the
    wire format are the stdlib's own: the peer proves it holds the key, then we do.
    """
    peer = _Deadline(connection, timeout)
    mpc.deliver_challenge(peer, authkey)
    mpc.answer_challenge(peer, authkey)


class _Handshake:
    """One accepted peer, authenticating on its own thread."""

    __slots__ = ("connection", "finished")

    def __init__(self, connection) -> None:
        self.connection = connection
        self.finished = False


class Server:
    """A listener that authenticates each peer off its accept loop, with a bounded,
    unauthenticated shutdown wakeup.

    The accept owner closes the listener after its native wait returns: closing it
    concurrently does not cancel Windows' pending pipe and can race pipe creation.
    The wakeup immediately disconnects and can never become an application channel.

    The stdlib Listener authenticates inside accept(), on the accept thread, with no
    deadline: one peer that never answered stopped the daemon serving anyone. Here a
    peer is accepted natively and authenticated on a thread of its own, within
    HANDSHAKE_TIMEOUT_SECONDS. accept() waits HANDSHAKE_HOLD_SECONDS for that and then
    accepts the next peer. A peer that answers later is handed out by a later accept(),
    which its handshake wakes if it is waiting natively. close() waits for no handshake;
    one that finishes after it is closed unused.
    """

    def __init__(
        self,
        address: str,
        authkey: bytes,
        backlog: int = 8,
        on_authentication_error: Callable[[], None] | None = None,
        handshake_timeout: float = HANDSHAKE_TIMEOUT_SECONDS,
    ) -> None:
        if not isinstance(authkey, bytes):
            raise TypeError("authkey must be bytes")
        self._family = _family()
        # No authkey for the stdlib Listener: its accept() would authenticate inline.
        self._listener = mpc.Listener(address, family=self._family, backlog=backlog)
        self.address = address
        self._authkey = authkey
        self._handshake_timeout = handshake_timeout
        self._on_authentication_error = on_authentication_error
        self._guard = threading.Lock()
        self._changed = threading.Condition(self._guard)
        self._accept_guard = threading.Lock()
        # Authenticated peers not yet handed out, in the order they finished.
        self._ready: collections.deque = collections.deque()
        self._accepting = False
        self._woken = False
        self._closed = False
        self._wake_failed = False

    def accept(self) -> Channel | None:
        """The next authenticated client, or None once the listener has been closed.

        A client that fails the authkey handshake (a stale key, a stranger), or never
        finishes it, is ITS failure, not the listener's: the daemon keeps accepting.
        Before this, one bad handshake read as "listener closed" and took the whole
        daemon down.
        """
        with self._accept_guard:
            while True:
                connection = None
                try:
                    with self._guard:
                        if self._closed:
                            return None
                        if self._ready:
                            return Channel(self._ready.popleft())
                        self._accepting = True
                    connection = self._listener.accept()
                except (OSError, EOFError):
                    pass
                finally:
                    with self._guard:
                        was_accepting = self._accepting
                        self._accepting = self._woken = False
                        if was_accepting and self._closed:
                            with contextlib.suppress(OSError):
                                self._listener.close()
                            self._wake_failed = False
                with self._guard:
                    if self._closed:
                        if connection is not None:
                            with contextlib.suppress(OSError):
                                connection.close()
                        return None
                if connection is None:
                    time.sleep(0.01)  # never a busy loop on a broken listener
                    continue
                handshake = _Handshake(connection)
                try:
                    threading.Thread(target=self._run_handshake, args=(handshake,),
                                     name="cadgen-handshake", daemon=True).start()
                except BaseException:
                    with contextlib.suppress(OSError):
                        connection.close()
                    raise
                with self._changed:
                    self._changed.wait_for(lambda: handshake.finished or self._ready or self._closed,
                                           HANDSHAKE_HOLD_SECONDS)

    def _run_handshake(self, handshake: _Handshake) -> None:
        """One peer's handshake, on its own thread: queue it for accept(), or drop it."""
        authenticated = False
        try:
            _authenticate(handshake.connection, self._authkey, self._handshake_timeout)
            authenticated = True
        except mpc.AuthenticationError:
            if self._on_authentication_error is not None:
                with contextlib.suppress(OSError):
                    self._on_authentication_error()
        except (OSError, EOFError):
            pass  # it hung up, or never answered
        finally:
            with self._guard:
                queued = authenticated and not self._closed
                if queued:
                    self._ready.append(handshake.connection)
                else:
                    with contextlib.suppress(OSError):
                        handshake.connection.close()
                handshake.finished = True
                self._changed.notify_all()
                if queued and self._accepting and not self._woken:
                    # accept() moved on and waits natively for the next peer: wake it to
                    # hand this one out. Under the guard, as close() wakes it. If the
                    # wakeup fails, the next peer to connect hands this one out.
                    self._woken = True
                    try:
                        _wake_listener(self.address, self._family)
                    except OSError:
                        self._woken = False

    def close(self) -> None:
        unused = ()
        try:
            with self._guard:
                if self._closed and not self._wake_failed:
                    return
                self._closed = True
                unused, self._ready = self._ready, collections.deque()
                self._changed.notify_all()
                if self._accepting:
                    # Hold the guard through the bounded wakeup so accept cannot close
                    # and release this address for another listener before we connect.
                    # An unexpected failure remains loud and admission stays closed;
                    # a later close may retry without abandoning the listener owner.
                    self._wake_failed = True
                    _wake_listener(self.address, self._family)
                    self._wake_failed = False
                else:
                    with contextlib.suppress(OSError):
                        self._listener.close()
                    self._wake_failed = False
        finally:
            for connection in unused:
                with contextlib.suppress(OSError):
                    connection.close()

    @property
    def closed(self) -> bool:
        return self._closed


def identity_digest(text: str) -> str:
    """The short, stable name a daemon is known by."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:12]


def keys_match(left: bytes | None, right: bytes | None) -> bool:
    if not left or not right:
        return False
    return hmac.compare_digest(left, right)


__all__ = [
    "PROTOCOL",
    "Channel",
    "AuthenticationError",
    "Server",
    "address_for",
    "address_is_stale",
    "clear_address",
    "connect",
    "ensure_authkey",
    "identity_digest",
    "keys_match",
    "publish_authkey",
    "SingletonLock",
    "daemon_lock",
    "spawn_lock",
    "read_authkey",
    "state_dir",
    "supported",
]
