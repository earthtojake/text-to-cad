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

import hashlib
import hmac
import multiprocessing.connection as mpc
import os
import secrets
import stat
import sys
import tempfile
import time
from pathlib import Path

# Bump when the wire format changes. It is part of the address, so mismatched peers never
# meet rather than meeting and misreading each other.
PROTOCOL = 2

_AUTHKEY_BYTES = 32


def supported() -> bool:
    """Whether this platform offers a family we can carry the daemon over."""
    return _family() in mpc.families


def _family() -> str:
    return "AF_PIPE" if os.name == "nt" else "AF_UNIX"


def state_dir() -> Path:
    """Where the address, the auth key and the advisory progress records live.

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
    return str(Path(tempfile.gettempdir()) / f"cadgen-b{PROTOCOL}-{key}.sock")


def _authkey_path(key: str) -> Path:
    return state_dir() / f"cadgen-daemon-v{PROTOCOL}-{key}.key"


def read_authkey(key: str) -> bytes | None:
    """The shared secret for this daemon, or None if it has not been created."""
    try:
        return _authkey_path(key).read_bytes().strip() or None
    except OSError:
        return None


def ensure_authkey(key: str) -> bytes:
    """Create the shared secret if absent, and return it.

    Written before the listener exists, so a client that finds an address always finds a
    key to go with it. 0600 on POSIX; on Windows the per-user temp directory is already
    ACL'd to the owner, and the pipe itself is the real access control.
    """
    path = _authkey_path(key)
    existing = read_authkey(key)
    if existing:
        return existing
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600), "wb") as handle:
        secret = secrets.token_hex(_AUTHKEY_BYTES).encode("ascii")
        handle.write(secret)
    if os.name != "nt":
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return secret


def forget_authkey(key: str) -> None:
    try:
        _authkey_path(key).unlink()
    except OSError:
        pass


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
        try:
            self._conn.close()
        except OSError:
            pass

    def __enter__(self) -> Channel:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def connect(address: str, authkey: bytes) -> Channel:
    """Open a channel to a listening daemon. Raises OSError when there is none."""
    try:
        return Channel(mpc.Client(address, family=_family(), authkey=authkey))
    except (mpc.AuthenticationError, ValueError) as exc:
        # Callers recover on OSError; a bad key or a malformed address is the same
        # outcome for them as no daemon at all -- run cold, do not crash the command.
        raise OSError(str(exc)) from exc


class Server:
    """A listener plus the accept loop's shutdown story.

    ``Listener.accept()`` cannot take a timeout, which the idle shutdown needs. Closing the
    listener from another thread makes the pending accept raise, and that is the signal --
    portable across both families, and it does not reach into Listener's private socket.
    """

    def __init__(self, address: str, authkey: bytes, backlog: int = 8) -> None:
        self._listener = mpc.Listener(address, family=_family(), authkey=authkey, backlog=backlog)
        self.address = address
        self._closed = False

    def accept(self) -> Channel | None:
        """The next client, or None once the listener has been closed.

        A client that fails the authkey handshake (a stale key, a stranger) is ITS
        failure, not the listener's: the daemon keeps accepting. Before this, one bad
        handshake read as "listener closed" and took the whole daemon down.
        """
        while True:
            try:
                return Channel(self._listener.accept())
            except (OSError, EOFError, mpc.AuthenticationError):
                if self._closed:
                    return None
                time.sleep(0.01)  # a rejected peer; never a busy loop on a broken listener

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._listener.close()
        except OSError:
            pass

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
    "Server",
    "address_for",
    "address_is_stale",
    "clear_address",
    "connect",
    "ensure_authkey",
    "forget_authkey",
    "identity_digest",
    "keys_match",
    "read_authkey",
    "state_dir",
    "supported",
]
