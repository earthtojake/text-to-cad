"""The device's CAD server, as the stdio transport reaches it: with the standard library alone.

The server's own clients find it by one rule (the library's ``cad.engine.places`` and
``cad.engine.client``, which this package does not import: an agent app installs it alone), and this
reads it the same way:

- **The engine folder** (``engine_dir``): the server's door (a named pipe; on Windows a port file) and
  lock, named ``engine``, in a folder only this user can write (``folder_refusal``). A request is one JSON
  line through the door, answered by JSON lines (``request``); the door is the one way to the server's
  HTTP endpoint and its token (``op: http``), which a loopback port alone could not vouch for.
- **The current installation** (``current``): ``<state>/installations/current`` names the release whose
  server the device runs, and its record that release's Python. When no server answers, that one is
  started (``connect``), whatever release this transport is.
- **The first one** (``register``): on a device with no installation current, the server this
  transport's environment carries registers itself -- a checkout's -- else the server of this
  transport's own release is installed by uvx (``SERVER``) and registered, once.
- **The hold** (``hold``): a connection the server keeps while it is open, under a name the transport's
  MCP sessions are opened by, which end when it drops.
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import os
import secrets
import selectors
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable
from urllib.parse import urlsplit

WINDOWS = os.name == "nt"
NAME = "engine"
# The server's distribution, whose release is this transport's own, its import name, the module it
# registers an installation by and the one it runs its engine as.
SERVER = "cad-server"
SERVER_PACKAGE = "cad_server"
REGISTER = "cad_server._internal.installations"
DAEMON_MODULE = "cad_server._internal.engine_daemon"
# How the server of this release is installed when the device has none: uv's tool run, as the agent app
# started this transport, with the Python line the server runs on.
LAUNCHER = ("uvx", "--no-config", "--managed-python", "--python", "3.14", "--from")
INSTALLATIONS = "installations"
CURRENT = f"{INSTALLATIONS}/current"
# Switches that govern only the process they are set in: the server serves every later client, so it
# goes by the person's saved choice, never by the switch of whichever client happened to start it.
PER_PROCESS = ("DO_NOT_TRACK", "CAD_TELEMETRY")
# The sandboxes known to refuse the loopback port the server's HTTP listener needs, each by a variable and
# the value it sets in the shells it runs: Codex's Seatbelt, in its default workspace-write mode.
SANDBOXES: tuple[tuple[str, str], ...] = (("CODEX_SANDBOX_NETWORK_DISABLED", "1"),)
SANDBOXED = ("no engine server is running, and this shell's sandbox cannot start one: open a CAD card "
             "(the CAD plugin's server starts the engine) or run `cad server` outside the sandbox")
# How long a reader waits on a port file Windows refuses while it is renamed into place: the writer's ladder.
RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4)


# --- where things are -----------------------------------------------------------------------------


def state_dir() -> Path:
    """Where this user's CAD state lives (``CAD_STATE_DIR`` overrides it)."""
    override = os.environ.get("CAD_STATE_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "cad"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "cad-state"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "cad"


def engine_dir() -> Path:
    """Where the server's door and lock live: ``CAD_ENGINE_DIR``, else ``default_engine_dir``."""
    override = os.environ.get("CAD_ENGINE_DIR")
    return Path(os.path.realpath(override if override else default_engine_dir()))


def default_engine_dir() -> str:
    """The engine folder when ``CAD_ENGINE_DIR`` names none: ``$XDG_RUNTIME_DIR/cad-engine``, else
    ``cad-engine`` in the user's own temporary folder (on macOS the one the system names, whatever
    ``TMPDIR`` a sandbox sets), else ``/tmp/cad-<uid>``; on Windows ``cad-engine`` in the temporary
    folder. 0.8's engines are in ``cadgen-engine``, which this never reads."""
    if WINDOWS:
        return os.path.join(tempfile.gettempdir(), "cad-engine")
    for parent in (os.environ.get("XDG_RUNTIME_DIR"), _darwin_temp() or os.environ.get("TMPDIR")):
        if parent and os.path.isabs(parent) and _users_own(parent):
            return os.path.join(parent, "cad-engine")
    return f"/tmp/cad-{os.getuid()}"


def _darwin_temp() -> str | None:
    """macOS's per-user temporary folder as the system names it (``_CS_DARWIN_USER_TEMP_DIR``)."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes

        buffer = ctypes.create_string_buffer(1024)
        size = ctypes.CDLL(None, use_errno=True).confstr(65537, buffer, len(buffer))
    except (OSError, AttributeError):
        return None
    return os.fsdecode(buffer.value) if 0 < size <= len(buffer) else None


def _users_own(folder: str) -> bool:
    try:
        found = os.stat(folder)
    except OSError:
        return False
    return stat.S_ISDIR(found.st_mode) and found.st_uid == os.getuid() and not found.st_mode & 0o022


def folder_refusal(folder: Path) -> str | None:
    """Why ``folder`` may not hold the server's door, or None: on POSIX it must be this user's alone."""
    if WINDOWS:
        return None
    try:
        found = os.lstat(folder)
    except OSError as error:
        return f"the engine's folder {folder} cannot be read: {error.strerror or error}"
    if not stat.S_ISDIR(found.st_mode):
        return f"the engine's folder {folder} is not a folder"
    if found.st_uid != os.getuid():
        return (f"the engine's folder {folder} belongs to another user (uid {found.st_uid}): "
                "set CAD_ENGINE_DIR to a folder of your own")
    if found.st_mode & 0o022:
        return (f"the engine's folder {folder} can be written by others (mode {stat.S_IMODE(found.st_mode):o}): "
                "run chmod go-w on it, or set CAD_ENGINE_DIR to a folder of your own")
    return None


def door_path() -> Path:
    return engine_dir() / f"{NAME}.door"


def port_path() -> Path:
    return engine_dir() / f"{NAME}.port"


def failure_path() -> Path:
    return engine_dir() / f"{NAME}.failed"


def address() -> Path:
    """Where the server is reached: its door, on Windows its port file."""
    return port_path() if WINDOWS else door_path()


# --- the installation the device runs ---------------------------------------------------------------


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def current() -> dict[str, Any] | None:
    """The current installation's record while its Python and console script are there, else None."""
    import re

    folder = state_dir()
    data = _read(folder / CURRENT)
    version = data.decode("utf-8", "replace").strip() if data is not None else ""
    if not re.fullmatch(r"[0-9][0-9A-Za-z.+_-]*", version):
        return None
    try:
        record = json.loads(_read(folder / INSTALLATIONS / f"{version}.json") or b"null")
    except ValueError:
        return None
    if not isinstance(record, dict) or record.get("version") != version or not all(
            isinstance(record.get(key), str) for key in ("python", "cadgen", "prefix")):
        return None
    return record if os.path.isfile(record["python"]) and os.path.isfile(record["cadgen"]) else None


def register() -> None:
    """On a device with no installation current: the server this transport's environment carries registers
    itself (a release's makes itself current; a checkout's registers nothing), else this transport's own
    release of the server is installed by uvx and registered -- the device's first. Quiet: its words are
    nobody's here, and a failure is the next start's to find (no installation, said by ``connect``)."""
    from cad_mcp import __version__

    if importlib.util.find_spec(SERVER_PACKAGE) is not None:
        command = [sys.executable, "-P", "-m", REGISTER]
    else:
        command = [*LAUNCHER, f"{SERVER}=={__version__}", "python", "-P", "-m", REGISTER]
    try:
        subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       **_windowless())
    except OSError:
        pass


# --- the door: a client's half ----------------------------------------------------------------------

CLIENTS = "clients"
# The door protocol this transport speaks (the library's ``cad.engine.door``, which it does not import):
# its hello is ``<id> <protocol>`` and a newline, and the server's greeting ``ok <protocol>`` and a newline,
# the protocol the connection speaks, from 1 (0.8's bare ``ok`` is no greeting). Within a number only
# additions, each a field at the end of its line, which a reader of that number skips; a removal or a
# rename takes a new number.
DOOR_PROTOCOL = 1
ID_CHARACTERS = 32
HELLO_LIMIT = 512
GREETING_SECONDS = 15.0
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


class Connection:
    """One connection to the server: the lines it reads (``reader``) and writes (``writer``), and the door
    protocol it speaks (``protocol``, the greeting's)."""

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


def _open(path: Path, flags: int) -> int:
    return os.open(path, flags | _NOFOLLOW | _CLOEXEC)


def _ours(fd: int) -> bool:
    found = os.fstat(fd)
    return stat.S_ISFIFO(found.st_mode) and found.st_uid == os.getuid()


def _private(folder: Path) -> bool:
    folder.mkdir(mode=0o700, exist_ok=True)
    found = os.lstat(folder)
    if stat.S_ISDIR(found.st_mode) and found.st_uid == os.getuid() and found.st_mode & 0o077:
        os.chmod(folder, 0o700)
        found = os.lstat(folder)
    return stat.S_ISDIR(found.st_mode) and found.st_uid == os.getuid() and not found.st_mode & 0o077


def _door_answering(door: Path) -> bool:
    """Whether a server reads ``door``: a FIFO of this user's that takes a writer."""
    try:
        fd = _open(door, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        return _ours(fd)
    finally:
        os.close(fd)


def hello(ident: str) -> bytes:
    """The hello: the pair's id (on Windows, the port file's token), a space, this transport's door
    protocol and a newline."""
    return f"{ident} {DOOR_PROTOCOL}\n".encode("ascii")


def greeted(line: bytes) -> int | None:
    """The door protocol the server's greeting says the connection speaks (with or without its
    newline), 1 or more, or None for a line that is no greeting; fields after the number, a later
    release's additions, skipped."""
    word, spaced, rest = line.removesuffix(b"\n").partition(b" ")
    field = rest.split(b" ", 1)[0]
    number = int(field) if word == b"ok" and spaced and 0 < len(field) <= 6 and field.isdigit() else 0
    return number or None


def _knock(door: Path, ident: str, timeout: float) -> bool:
    try:
        fd = _open(door, os.O_WRONLY | os.O_NONBLOCK)
    except PermissionError:
        raise
    except OSError:
        return False
    try:
        if not _ours(fd):
            return False
        line = hello(ident)
        deadline = time.monotonic() + timeout
        while True:
            try:
                return os.write(fd, line) == len(line)
            except BlockingIOError:
                if time.monotonic() > deadline:
                    return False
                time.sleep(0.001)
    finally:
        os.close(fd)


def _greeted(fd: int, door: Path, timeout: float) -> int | None:
    """The door protocol of the server's greeting (``greeted``), read a byte at a time to its newline
    and never past it; None when none comes, or the door goes while it waits."""
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
                return None
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
            if not _door_answering(door):
                return None
    return greeted(got)


def dial(door: Path, timeout: float = GREETING_SECONDS) -> Connection | None:
    """A connection to the server reading ``door``: a pair of FIFOs in its ``clients`` folder, a hello
    through the door, the greeting, then each FIFO opened for its one direction (the server's door
    protocol). None when none reads it or it never greets."""
    folder = door.parent / CLIENTS
    ident = secrets.token_hex(ID_CHARACTERS // 2)
    up, down = folder / f"{ident}.up", folder / f"{ident}.down"
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
        hold = take(down, os.O_RDWR)
        early = take(up, os.O_RDWR)
        if not _knock(door, ident, timeout):
            return None
        spoken = _greeted(hold, door, timeout)
        if spoken is None or spoken > DOOR_PROTOCOL:  # a protocol this transport does not speak
            return None
        reader = take(down, os.O_RDONLY | os.O_NONBLOCK)
        writer = take(up, os.O_WRONLY | os.O_NONBLOCK)
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


# --- reaching the server ----------------------------------------------------------------------------


def _port_text(path: Path) -> str:
    for delay in RETRY_DELAYS_SECONDS:
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            time.sleep(delay)
    return path.read_text(encoding="utf-8")


def _denied(cause: str) -> ConnectionError:
    return ConnectionError(f"the system denies text-to-cad's local engine ({cause}); a sandbox that forbids "
                           "it does: run this command outside it, or with the sandbox's permission")


def _connect(where: Path | None = None) -> Connection | None:
    """A connection to the server at ``where`` (its door, on Windows its port file; by default the
    device's), or None when none answers there."""
    try:
        if WINDOWS:
            port, token = _port_text(where or port_path()).split()
            connection = socket.create_connection(("127.0.0.1", int(port)), timeout=5)
            stream = connection.makefile("rwb")
            try:  # the door's hello and greeting on the port: the token where a pair's id goes
                connection.settimeout(GREETING_SECONDS)
                stream.write(hello(token))
                stream.flush()
                spoken = greeted(stream.readline(HELLO_LIMIT))
                connection.settimeout(None)
            except OSError:
                spoken = None
            if spoken is None or spoken > DOOR_PROTOCOL:
                stream.close()
                connection.close()
                return None
            return Connection(stream, stream, stream, connection, protocol=spoken)
        door = where or door_path()
        if folder_refusal(door.parent) is not None or not door.exists():
            return None
        return dial(door)
    except PermissionError as error:
        raise _denied(f"opening a pipe in the engine's folder {engine_dir()}: {error.strerror or error}") from None
    except (OSError, ValueError):
        return None


def answering(where: Path) -> bool:
    """Whether a server answers at ``where``, asked without a request."""
    if not WINDOWS:
        return _door_answering(where)
    connection = _connect(where)
    if connection is None:
        return False
    connection.close()
    return True


def _windowless() -> dict[str, Any]:
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)} if WINDOWS else {}


def _detached() -> dict[str, Any]:
    if WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)}
    return {"start_new_session": True}


def _same(one: str, other: str) -> bool:
    return os.path.normcase(os.path.realpath(one)) == os.path.normcase(os.path.realpath(other))


def _start() -> subprocess.Popen:
    """The server started, detached: the current installation's, with its Python; on a device with none,
    one registered first (``register``); and with none still, the one this environment carries, if any."""
    found = current()
    if found is None:
        register()
        found = current()
    if found is not None:
        python, own = found["python"], _same(found["prefix"], sys.prefix)
    elif importlib.util.find_spec(SERVER_PACKAGE) is not None:
        python, own = sys.executable, True
    else:
        raise ConnectionError(f"no CAD server is installed on this computer, and installing {SERVER} "
                              "failed: run the install command, `curl -fsSL https://texttocad.dev/install.sh | sh`")
    env = {name: value for name, value in os.environ.items() if name not in PER_PROCESS}
    if not own:
        env.pop("PYTHONPATH", None)  # another installation imports its own server
    # Nothing written beside a library: the server keeps its bytecode in the cache folder once it runs.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    folder = engine_dir()
    cwd = (str(folder) if folder.is_dir() else None) if not WINDOWS else (
        str(folder.parent) if folder.parent.exists() else None)
    return subprocess.Popen([python, "-P", "-m", DAEMON_MODULE], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=cwd, **_detached())


def _not_started(code: int) -> ConnectionError:
    try:
        note = json.loads(failure_path().read_text(encoding="utf-8"))
        reason, denied = str(note["reason"]), bool(note.get("denied"))
    except (OSError, ValueError, KeyError, TypeError):
        reason, denied = f"it exited with code {code}", False
    if denied:
        return ConnectionError(f"{SANDBOXED} ({reason})")
    return ConnectionError(f"the engine server did not start: {reason}")


# One start at a time in this process: the hold (``shim.Holder``) and the host's first request both find no
# server on a device's first start, and two starts would register two installations at once.
_STARTING = threading.Lock()


def connect(*, start: bool = True, timeout: float = 60.0) -> Connection | None:
    """A connection to the server, started when ``start`` and none answers: by one thread of this process
    at a time, a thread that waited for another's start taking the server it started."""
    found = _connect()
    if found is not None or not start:
        return found
    if any(os.environ.get(name) == value for name, value in SANDBOXES):
        raise ConnectionError(SANDBOXED)
    with _STARTING:
        found = _connect()
        if found is not None:
            return found
        return _started(timeout)


def _started(timeout: float) -> Connection:
    """The server started (``_start``) and a connection to it once it answers."""
    try:
        engine_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    except PermissionError as error:
        raise _denied(f"making the engine's folder: {error.strerror or error}") from None
    refusal = folder_refusal(engine_dir())
    if refusal is not None:
        raise ConnectionError(refusal)
    try:
        failure_path().unlink(missing_ok=True)
    except PermissionError as error:
        raise _denied(f"writing in the engine's folder: {error.strerror or error}") from None
    process = _start()
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        found = _connect()
        if found is not None:
            return found
        time.sleep(0.02)
        if process.poll():
            raise _not_started(process.returncode)
        if time.monotonic() - started > 1.0 and process.poll() == 0:
            process = _start()  # one stopping held the lock, and the one started left at once
            started = time.monotonic()
    raise ConnectionError("the engine server did not start")


def _exchange(connection: Connection, message: dict[str, Any], where: Path | None = None) -> dict[str, Any]:
    if WINDOWS:  # the token in the request too, first, which the server checks as it did the hello's
        message = {"token": (where or port_path()).read_text(encoding="utf-8").split()[1], **message}
    with connection:
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        for line in connection.reader:
            answer = json.loads(line)
            if "log" in answer or set(answer) == {"progress"}:
                continue
            answer.pop("notice", None)
            return answer
    raise ConnectionError("the engine server closed the connection")


def request(message: dict[str, Any], *, start: bool = True) -> dict[str, Any] | None:
    """One request and its answer; None when no server runs and ``start`` is false."""
    connection = connect(start=start)
    if connection is None:
        return None
    return _exchange(connection, message)


def hold(*, start: bool = True, host: Callable[[], str | None] | None = None,
         holder: str | None = None) -> Connection | None:
    """A hold on the server, started when ``start`` and none runs: while the connection returned stays open
    the server counts this transport, and when it drops the server ends the sessions opened under
    ``holder``. ``host()``, asked once the server answers, names the agent app it serves."""
    connection = connect(start=start)
    if connection is None:
        return None
    try:
        message: dict[str, Any] = {"op": "hold"}
        named = host() if host is not None else None
        if named:
            message["host"] = named
        if holder:
            message["holder"] = holder
        if WINDOWS:
            message = {"token": port_path().read_text(encoding="utf-8").split()[1], **message}
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        if json.loads(connection.reader.readline() or b"{}").get("ok") is not True:
            raise ConnectionError("the engine server did not take the hold")
    except BaseException:
        connection.close()
        raise
    return connection


# --- its HTTP endpoint ------------------------------------------------------------------------------


def _door(where: Path | None = None) -> Any:
    """Which server the door at ``where`` names now (its identity), or None when none answers there."""
    where = where or address()
    try:
        found = os.stat(where)
    except OSError:
        return None
    if WINDOWS:
        return found.st_ino, found.st_mtime_ns, found.st_size
    return (found.st_dev, found.st_ino) if answering(where) else None


class EngineClient:
    """The server's loopback endpoint as its door last named it, used only while that door still answers:
    a loopback port is anyone's once the server has let it go, and every call carries the user's page
    token. It is read from the door again whenever it may be stale: the server gone or replaced, after any
    answer that is not a success, after a connection error, and for a call that asks for a ``fresh`` one
    (an MCP ``initialize``)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.endpoint: dict[str, Any] | None = None
        self.door: Any = None
        self.address: Path | None = None

    def connect(self, *, fresh: bool = False, start: bool = True) -> dict[str, Any]:
        with self.lock:
            if self.endpoint is not None and not fresh and (self.door is None or _door(self.address) != self.door):
                self.endpoint = None
            if self.endpoint is None or fresh:
                self.endpoint = None
                answer = request({"op": "http"}, start=start)
                if not answer or "failed" in answer:
                    raise ConnectionError((answer or {}).get("failed", "engine did not answer"))
                self.address = address()
                self.endpoint, self.door = answer, _door(self.address)
            return self.endpoint

    def forget(self) -> None:
        with self.lock:
            self.endpoint = None

    def _forget(self, endpoint: dict[str, Any]) -> None:
        with self.lock:
            if self.endpoint is endpoint:
                self.endpoint = None

    def call(self, method: str, path: str, body: bytes = b"", headers: dict[str, str] | None = None, *,
             fresh: bool = False, start: bool = True) -> tuple[int, dict[str, str], bytes]:
        endpoint = self.connect(fresh=fresh, start=start)
        for attempt in (1, 2):
            parsed = urlsplit(endpoint["url"])
            conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=600)
            try:
                conn.request(method, path, body=body, headers={**(headers or {}),
                             "Authorization": "Bearer " + endpoint["token"]})
                response = conn.getresponse()
                answer = response.status, dict(response.getheaders()), response.read()
            except ConnectionRefusedError:
                self._forget(endpoint)
                if attempt == 2:
                    raise
                endpoint = self.connect(fresh=True, start=start)
                continue
            except (OSError, http.client.HTTPException):
                self._forget(endpoint)
                raise
            finally:
                conn.close()
            if not 200 <= answer[0] < 300:
                self._forget(endpoint)
                if attempt == 1 and answer[0] == 403 and b"engine token required" in answer[2]:
                    endpoint = self.connect(fresh=True, start=start)
                    continue
            return answer
        raise ConnectionError("the engine server did not answer")
