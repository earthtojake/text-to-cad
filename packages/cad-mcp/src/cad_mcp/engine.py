"""The CAD server of this transport's own version, as the stdio transport reaches it: with the standard library
alone.

The server's own clients find it by one rule (the library's ``cad.engine.places`` and
``cad.engine.client``, which this package does not import: an agent app installs it alone), and this
reads it the same way:

- **Its version** (``Pin``, ``configure``): this package's own release (a development install names its build in
  ``CAD_INSTALLATION_VERSION``). ``--channel`` labels where this copy came from (none: ours), for the server's
  counts alone. A source tree has no version (a checkout's tests): it reaches the server its own environment
  carries, by the flat door (below).
- **Its version installed where it is missing** (``prepare``, at start, in the background, outside any sandbox):
  installed when its marker is there (``version_record``); else installed by its own release's line,
  ``uvx --no-config --managed-python --python 3.14 --from cad-server==<version> cad setup`` (``setup_command``),
  bounded by ``PREPARE_SECONDS``. Until it is done the transport is not ready (``unavailable``: being installed,
  ``installing_line``); where the install fails (a sandbox with no network, uv missing), it says so in one line
  (``failed``), with that command to run.
- **The engine folder** (``engine_dir``): the server's door (a named pipe; on Windows a port file) and
  lock, named ``engine``, in a folder only this user can write (``folder_refusal``): a version's is
  ``<engines>/<version>`` (``engine_dir(version)``), its data ``versions/<version>`` in the state folder
  (``version_dir``), its installed marker ``versions/<version>/code/cad-version.json`` (``version_record``); the
  flat one directly in the engines' folder (``engines_dir``) is a server's with no version -- the library's rules
  (``cad.engine.places``), copied and held equal by a test. A transport with a version reaches its own version's
  door and no other. A request is one JSON line through the door, answered by JSON lines (``request``); the door
  is the one way to the server's HTTP endpoint and its token (``op: http``), which a loopback port alone could not
  vouch for.
- **Starting it** (``_start``): with a version, that version's server, from its own Python; with none, the server
  this transport's own environment carries.
- **Every wait bounded**: a request waits for the version a few seconds at most (``unavailable``), the app's
  ``initialize`` 20 seconds, or 80% of the app's own startup timeout where its server config gives it
  (``--startup-timeout``, ``shim.initialize_seconds``: the rest is uvx starting this transport before, and the
  server's start and its own answer after), a server's
  answer through the door ``DOOR_SECONDS`` a line (``_line``), its start 60 seconds, its HTTP answer 10 minutes;
  ``prepare``'s install is bounded by ``PREPARE_SECONDS``, which bounds every wait for it (``READY_LIMIT``).
- **The hold** (``hold``): a connection the server keeps while it is open, under a name the transport's
  MCP sessions are opened by, which end when it drops.
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import os
import re
import secrets
import selectors
import socket
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable
from urllib.parse import urlsplit

WINDOWS = os.name == "nt"
NAME = "engine"
# The server's distribution, whose release is this transport's own, its import name, and the module it runs its
# engine as.
SERVER = "cad-server"
SERVER_PACKAGE = "cad_server"
DAEMON_MODULE = "cad_server._internal.engine_daemon"
# How a version of the server is installed: uv's tool run, as the agent app started this transport, with the Python
# line the server runs on.
LAUNCHER = ("uvx", "--no-config", "--managed-python", "--python", "3.14", "--from")
# The installed versions' folder in the state folder, and a version's name: a digit first.
VERSIONS = "versions"
VERSION = r"[0-9][0-9A-Za-z.+_-]*"
# Switches that govern only the process they are set in: the server serves every later client, so it
# goes by the person's saved choice, never by the switch of whichever client happened to start it.
PER_PROCESS = ("DO_NOT_TRACK", "CAD_TELEMETRY")
# The sandboxes known to refuse the loopback port the server's HTTP listener needs, each by a variable and
# the value it sets in the shells it runs: Codex's Seatbelt, in its default workspace-write mode.
SANDBOXES: tuple[tuple[str, str], ...] = (("CODEX_SANDBOX_NETWORK_DISABLED", "1"),)
SANDBOXED = ("no engine server is running, and this shell's sandbox cannot start one: open a CAD card "
             "(its server starts the engine) or run `cad server` outside the sandbox")
# How long a reader waits on a port file Windows refuses while it is renamed into place: the writer's ladder.
RETRY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4)


# --- where things are -----------------------------------------------------------------------------


def _local_state() -> Path:
    """The platform's place for state: macOS's Application Support, else ``$XDG_STATE_HOME`` or
    ``~/.local/state`` -- on Windows too, out of the local application data an app package (the Claude
    desktop app, which starts this server) virtualizes."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")


def state_dir() -> Path:
    """Where this user's CAD state lives (``CAD_STATE_DIR`` overrides it)."""
    override = os.environ.get("CAD_STATE_DIR")
    if override:
        return Path(override)
    return _local_state() / "cad"


def version_dir(version: str) -> Path:
    """Version ``version``'s folder, ``versions/<version>`` in the state folder. ``ValueError`` for a name that
    is no version."""
    if not re.fullmatch(VERSION, version or ""):
        raise ValueError(f"not a version: {version!r}")
    return state_dir() / VERSIONS / version


def engines_dir() -> Path:
    """The engines' folder: ``CAD_ENGINE_DIR``, else ``default_engine_dir``; the flat door of a server with no
    version is in it directly, each version's engine in a folder of its own (``engine_dir``)."""
    override = os.environ.get("CAD_ENGINE_DIR")
    return Path(os.path.realpath(override if override else default_engine_dir()))


def engine_dir(version: str | None = None) -> Path:
    """Where a server's door and lock live: version ``version``'s folder in the engines' folder; with none named,
    this transport's own version's (``PIN``), and for a transport with no version the engines' folder itself."""
    version = version if version is not None else PIN.version
    if version is None:
        return engines_dir()
    version_dir(version)  # the same refusal of a name that is no version
    return engines_dir() / version


# --- this transport's version ----------------------------------------------------------------------

# A delivery label's name (the library's ``places.CHANNEL``); ``default`` is none.
CHANNEL = r"[a-z0-9][a-z0-9._-]{0,31}"
DEFAULT_CHANNEL = "default"
# The installed marker of a version, its schema, and the variable a development install names its build by.
VERSION_MARKER = "cad-version.json"
VERSION_SCHEMA = "cad version/1"
INSTALLATION_ENV = "CAD_INSTALLATION_VERSION"
# A release's name, as PyPI has one: what ``prepare`` can install.
RELEASED = r"[0-9.abcoprst]+"
# How long a version's install may take, and so every wait for it.
PREPARE_SECONDS = 3600.0
READY_LIMIT = PREPARE_SECONDS + 60.0
# How long a request waits for its version to be ready before it is answered here (``unavailable``).
READY_SECONDS = 5.0
# How long a line the server sends through its door is waited for (``_line``).
DOOR_SECONDS = 30.0
# Why a transport cannot reach its server now (``unavailable``): its version is being installed, or could not be.
INSTALLING, FAILED = "installing", "failed"


class Pin:
    """This transport's version (None: a source tree, which has none) and delivery label (None: none), set once at
    start (``configure``), and what preparing it found (``prepare``): ``ready`` once done, ``failed`` the one line
    saying why it cannot serve."""

    def __init__(self, version: str | None = None, channel: str | None = None) -> None:
        self.version = version
        self.channel = channel
        self.ready = threading.Event()
        self.failed: str | None = None
        if version is None:
            self.ready.set()


# With no version until ``configure``: the flat door, a source tree's.
PIN = Pin()


def channel_name(text: str | None) -> str | None:
    """``text`` as a delivery label (None, or ``default``: none), or ``ValueError`` saying the rule."""
    if text is None or text == DEFAULT_CHANNEL:
        return None
    if re.fullmatch(CHANNEL, text):
        return text
    raise ValueError(f"not a channel: {text!r} (a channel is a lower-case letter or digit, then up to 31 lower-case "
                     "letters, digits, '.', '_' or '-')")


def own_version() -> str | None:
    """This transport's version: the build a development install names (``INSTALLATION_ENV``), else this package's
    own release; None for a source tree (a checkout: its tests), which has no version."""
    from cad_mcp import __version__, source_tree

    named = os.environ.get(INSTALLATION_ENV, "").strip()
    if re.fullmatch(VERSION, named):
        return named
    if source_tree() or not re.fullmatch(RELEASED, __version__):
        return None
    return __version__


def configure(channel: str | None) -> Pin:
    """This transport's pin: its version (``own_version``) and delivery label ``channel``, which it reaches the
    server by from now on."""
    global PIN
    PIN = Pin(own_version(), channel_name(channel))
    return PIN


def version_record(version: str) -> dict[str, Any] | None:
    """Version ``version``'s installed marker (``versions/<version>/code/cad-version.json``) while its Python and
    ``cad`` are there, else None: the library's ``places.version_record``, copied."""
    try:
        record = json.loads(_read(version_dir(version) / "code" / VERSION_MARKER) or b"null")
    except ValueError:
        return None
    if (not isinstance(record, dict) or record.get("schema") != VERSION_SCHEMA or record.get("version") != version
            or not all(isinstance(record.get(key), str) for key in ("python", "cad", "prefix"))):
        return None
    return record if os.path.isfile(record["python"]) and os.path.isfile(record["cad"]) else None


def setup_command(version: str) -> list[str]:
    """The line that installs ``version`` of cad: that release's own ``cad setup``, through uvx."""
    return [*LAUNCHER, f"{SERVER}=={version}", "cad", "setup"]


def installing_line(version: str) -> str:
    """What a transport answers while its version is being installed (``prepare``)."""
    return f"cad {version} is being installed on this computer: try again shortly"


def unavailable(wait: float = 0.0) -> tuple[str, str] | None:
    """Why this transport cannot reach its server now, as ``(INSTALLING | FAILED, line)``, or None when it can: its
    version waited for at most ``wait`` seconds, and still being installed past them, or not installed."""
    if not PIN.ready.wait(wait):
        return INSTALLING, installing_line(PIN.version or "")
    if PIN.failed is not None:
        return FAILED, PIN.failed
    return None


def prepare(pin: Pin | None = None) -> Pin:
    """This transport's version installed where it is missing (see the module), once, in the background, as the app
    starts it: ``pin.ready`` set when done, with ``failed`` where it is not installed and could not be. Nothing for a
    transport with no version, or a version already installed."""
    pin = pin or PIN
    try:
        if pin.version is None or version_record(pin.version) is not None:
            return pin
        if not re.fullmatch(RELEASED, pin.version):
            pin.failed = (f"cad {pin.version} is not installed, and it is no release: a development "
                          "version is installed from its own checkout alone")
            return pin
        command = setup_command(pin.version)
        said = _run(command, os.environ.copy())
        if version_record(pin.version) is None:
            pin.failed = (f"cad {pin.version} is not installed, and it could not be installed here "
                          f"({said or 'uvx failed'}): run {' '.join(command)} outside any sandbox")
        return pin
    finally:
        pin.ready.set()


def _run(command: list[str], env: dict[str, str]) -> str:
    """``command`` run, quiet, for ``PREPARE_SECONDS`` at most: the last line it said on stderr."""
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", env=env, timeout=PREPARE_SECONDS, **_windowless())
    except (OSError, subprocess.SubprocessError) as error:
        return f"{type(error).__name__}: {error}"
    lines = [line.strip() for line in (done.stderr or "").splitlines() if line.strip()]
    return (lines[-1] if lines else "").removeprefix("cad: ")


def default_engine_dir() -> str:
    """The engine folder when ``CAD_ENGINE_DIR`` names none: ``$XDG_RUNTIME_DIR/cad-engine``, else
    ``cad-engine`` in the user's own temporary folder (on macOS the one the system names, whatever
    ``TMPDIR`` a sandbox sets), else ``/tmp/cad-<uid>``; on Windows ``cad-engine`` beside the state folder,
    out of the local application data an app package virtualizes. 0.8's engines are in ``cadgen-engine``,
    which this never reads."""
    if WINDOWS:
        return str(_local_state() / "cad-engine")
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


# --- files ----------------------------------------------------------------------------------------


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


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
    return ConnectionError(f"the system denies {SERVER}'s engine ({cause}); a sandbox that forbids "
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


def _start() -> subprocess.Popen:
    """The server started, detached. With a version (``PIN``): that version's, from its own Python, told its name,
    and never another version's -- ``ConnectionError`` while it is not installed. With none: the server this
    transport's own environment carries."""
    if PIN.version is not None:
        record = version_record(PIN.version)
        if record is None:
            raise ConnectionError(PIN.failed or f"cad {PIN.version} is not installed on this computer: run "
                                                 f"{' '.join(setup_command(PIN.version))}")
        env = {name: value for name, value in os.environ.items() if name not in ("PYTHONPATH", "PYTHONHOME")}
        env[INSTALLATION_ENV] = PIN.version
        python = record["python"]
    elif importlib.util.find_spec(SERVER_PACKAGE) is not None:
        env, python = dict(os.environ), sys.executable
    else:
        raise ConnectionError(f"no CAD server is installed with this transport, which has no version: install {SERVER}")
    env = {name: value for name, value in env.items() if name not in PER_PROCESS}
    # Nothing written beside a library: the server keeps its bytecode in its own folders once it runs.
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
# server at first, and two starts would race for one door.
_STARTING = threading.Lock()


def connect(*, start: bool = True, timeout: float = 60.0, wait: float = 0.0) -> Connection | None:
    """A connection to the server, started when ``start`` and none answers: by one thread of this process
    at a time, a thread that waited for another's start taking the server it started. With a version, only once it
    is installed (``prepare``, waited for at most ``wait`` seconds): ``ConnectionError`` saying why where it cannot
    serve now (``unavailable``)."""
    why = unavailable(wait)
    if why is not None:
        raise ConnectionError(why[1])
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


def _line(connection: Connection, seconds: float | None = None) -> bytes:
    """The next line the server sends on ``connection`` (empty once it closed it), waited for at most ``seconds``
    (``DOOR_SECONDS``): ``ConnectionError`` past them, so a server that stopped answering never holds a request. Read
    a byte at a time, never past its newline, so whatever reads the connection next reads from where it ends."""
    seconds = DOOR_SECONDS if seconds is None else seconds
    deadline = time.monotonic() + seconds
    late = ConnectionError(f"the engine server did not answer within {seconds:g} seconds")
    if WINDOWS:  # the port's socket: its own timeout, and none again after
        sock = next((each for each in connection.closing if isinstance(each, socket.socket)), None)
        if sock is None:
            return connection.reader.readline()
        sock.settimeout(seconds)
        try:
            return connection.reader.readline()
        except TimeoutError:
            raise late from None
        finally:
            try:
                sock.settimeout(None)
            except OSError:
                pass
    fd = connection.reader.fileno()
    got = b""
    with selectors.DefaultSelector() as selector:
        selector.register(fd, selectors.EVENT_READ)
        while not got.endswith(b"\n"):
            left = deadline - time.monotonic()
            if left <= 0 or not selector.select(left):
                raise late
            byte = os.read(fd, 1)
            if not byte:
                break
            got += byte
    return got


def _exchange(connection: Connection, message: dict[str, Any], where: Path | None = None) -> dict[str, Any]:
    if WINDOWS:  # the token in the request too, first, which the server checks as it did the hello's
        message = {"token": (where or port_path()).read_text(encoding="utf-8").split()[1], **message}
    with connection:
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        while line := _line(connection):
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
        if PIN.channel:
            message["channel"] = PIN.channel  # the copy's delivery label, as a labelled command says it
        if WINDOWS:
            message = {"token": port_path().read_text(encoding="utf-8").split()[1], **message}
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        if json.loads(_line(connection) or b"{}").get("ok") is not True:
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
