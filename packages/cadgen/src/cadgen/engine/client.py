"""Attach to the explicitly selected server through its private, authenticated door."""

from __future__ import annotations

import functools
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from cadgen.engine import daemon as _daemon
from cadgen.engine.atomic_replace import RETRY_DELAYS_SECONDS
from cadgen.engine.door import Connection, answering, dial

__all__ = ["converge", "hello", "hold", "holder", "Incompatible", "legacy", "request", "retire_older",
           "retired_words", "stop_legacy", "sweep"]

DAEMON_MODULE = "cadgen.engine.daemon"  # the enclosing distribution may supply an application host
# The console script of the release the device runs, when that is newer than this process's (the
# enclosing distribution's pointer, ``cadgen._internal.installations.newer``), else None: a start
# brings up that release's engine (``_start``) rather than this one's. None: the distribution says none.
CURRENT: Callable[[], str | None] | None = None
# What the engine started for another release is told so that its command runs as it is, never
# deferred again (the distribution's ``installations.NO_DEFER_ENV``; law 3: the name, not the import).
NO_DEFER_ENV = "CADGEN_NO_DEFER"

# The sandboxes known to refuse the loopback port the engine's HTTP server needs, each by a variable
# and the value it sets in the shells it runs: a daemon started there could never serve a build. The
# enclosing distribution names them (its host adapter); a sandbox none names is found by the daemon
# that cannot listen (``daemon.failure_path``), as fast.
SANDBOXES: tuple[tuple[str, str], ...] = ()
SANDBOXED = ("no engine server is running, and this shell's sandbox cannot start one: open a CAD card "
             "(the CAD plugin's server starts the engine) or run `cadgen server` outside the sandbox")
# An older release's engine -- 0.8.1 and before, protocol 3, the door's first -- named its door by
# its installation rather than by the port it serves, and takes one request a connection with no
# handshake. ``legacy`` finds the one serving a port through that door: each older door in the
# engine's folder asked its status once, read-only, at most ``LEGACY_DOORS`` of them, each answer at
# most ``LEGACY_BYTES`` and ``LEGACY_SECONDS`` (a wedged engine never wedges this process).
LEGACY_DOORS = 16
LEGACY_BYTES = 1 << 20
LEGACY_SECONDS = 3.0
_TAG = re.compile(r"[0-9a-f]{12}")
_VERSION = re.compile(r"[0-9][0-9A-Za-z.+_-]*")
# An older release's engine on the selected port is retired by a start once it is idle (``converge``,
# ``retire_older``): how long a start waits for one it cannot use to become idle before it says what
# uses it, how often it asks its status meanwhile, and how long one asked to stop has to exit.
RETIRE_SECONDS = 10.0
RETIRE_POLL = 0.1
STOP_SECONDS = 60.0
# What a refused handshake adds, where its own words name no remedy.
DIAGNOSTICS = "; run `cadgen doctor --json --python /path/to/project/python` for diagnostics"


class Incompatible(ConnectionError):
    """The engine at the selected port's door and this cadgen do not meet (``runtime.refusal``:
    another protocol, a document format the engine does not read, another native line), or it refused
    this cadgen's hello: said in one line, with ``engine``, what the engine says of itself in its
    hello's answer (``protocol``, ``release``, ``port``, ``writes``, ``reads``, ``native``, and what it
    runs as: ``installation``, ``python``, ``source``), and ``what`` differs where this cadgen can tell
    (``protocol``, ``format``, ``native``)."""

    def __init__(self, said: str, engine: dict[str, Any], what: str | None = None) -> None:
        super().__init__(said)
        self.engine, self.what = engine, what


class InUse(ConnectionError):
    """An older release's engine a start would retire (``retire_older``), still in use: said in one
    line naming what uses it and what frees it; ``found``, the engine (``_older_engine``), and ``uses``
    its uses in words."""

    def __init__(self, said: str, found: dict[str, Any], uses: list[str]) -> None:
        super().__init__(said)
        self.found, self.uses = found, uses


def _connect(address: Path | None = None) -> Connection | None:
    """A connection to the daemon at ``address`` (its door, on Windows its port file; by default
    the selected port's), or None when none answers there. ``ConnectionError`` when the system
    refuses this process the engine's folder (a sandbox that forbids writing there), and when no
    port is selected (a ``CADGEN_PORT`` that names none): said in one line, as a verb says it."""
    if address is None:
        try:
            address = _daemon.address()
        except ValueError as error:
            raise ConnectionError(str(error)) from None
    folder = address.parent
    if folder.exists() and (refusal := _daemon.folder_refusal(folder)) is not None:
        raise ConnectionError(refusal)
    try:
        if _daemon.WINDOWS:
            port, _token = _port_text(address).split()
            connection = socket.create_connection(("127.0.0.1", int(port)), timeout=5)
            connection.settimeout(None)
            stream = connection.makefile("rwb")
            return Connection(stream, stream, stream, connection)
        door = address
        if not door.exists():
            return None
        return dial(door)
    except PermissionError as error:
        raise _denied(f"opening a pipe in the engine's folder {_daemon.state_dir()}: {error.strerror or error}") from None
    except (OSError, ValueError):
        return None


def _port_text(path: Path) -> str:
    """A Windows engine's port file. Windows refuses a reader (EACCES) while the file is renamed
    into place or removed -- an engine starting, which ``connect`` polls, or stopping -- so that
    refusal waits out the ladder the writer's rename does (``atomic_replace``) before it is said to be
    the system's."""
    for delay in RETRY_DELAYS_SECONDS:
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            time.sleep(delay)
    return path.read_text(encoding="utf-8")


def _answering(address: Path) -> bool:
    """Whether a daemon answers at ``address``, asked without a request: its door takes a writer
    (on Windows, its port takes a connection)."""
    if not _daemon.WINDOWS:
        return answering(address)
    connection = _connect(address)
    if connection is None:
        return False
    connection.close()
    return True


def _sandboxed() -> bool:
    return any(os.environ.get(name) == value for name, value in SANDBOXES)


def _denied(cause: str) -> ConnectionError:
    """The engine refused by the system (a sandbox that forbids writing in the engine's folder),
    said to the agent or person who runs the command."""
    return ConnectionError(f"the system denies cadgen's local engine ({cause}); a sandbox that forbids "
                           "it does: run this command outside it, or with the sandbox's permission")


def _lock(path: Path | None = None) -> Any:
    """``daemon.lock`` taken by a client (to see a daemon gone, or its files dead): a folder refused
    (``daemon.folder_refusal``) or denied by the system said in one line, as ``connect`` says it."""
    try:
        return _daemon.lock(path)
    except PermissionError as error:
        if error.errno is None:  # ``folder_refusal``'s words
            raise ConnectionError(str(error)) from None
        raise _denied(f"taking the lock in the engine's folder {_daemon.state_dir()}: "
                      f"{error.strerror or error}") from None


def _not_started(code: int) -> ConnectionError:
    """A daemon that exited at once, failing (``daemon.main``): the reason its note gives."""
    try:
        note = json.loads(_daemon.failure_path().read_text(encoding="utf-8"))
        reason, denied = str(note["reason"]), bool(note.get("denied"))
    except (OSError, ValueError, KeyError, TypeError):
        reason, denied = f"it exited with code {code}", False
    if denied:
        return ConnectionError(f"{SANDBOXED} ({reason})")
    return ConnectionError(f"the engine server did not start: {reason}")


# Switches that govern only the process they are set in -- ``DO_NOT_TRACK`` and
# ``CADGEN_TELEMETRY`` (the distribution's ``cadgen.analytics.ENVIRONMENT``). The daemon serves
# every later client, so it is one of the "processes started for others" that go by the
# person's saved choice, never by the switch of whichever client happened to start it. The
# engine imports nothing of cadgen (law 3), so it carries the names here rather than importing them.
_PER_PROCESS_TELEMETRY = ("DO_NOT_TRACK", "CADGEN_TELEMETRY")


def environment() -> dict[str, str]:
    """This process's environment as the engine is handed it: ``os.environ``, every relative
    ``PYTHONPATH`` entry made absolute against this process's working folder, as Python resolves it
    for ``python SCRIPT`` (``site`` makes ``sys.path`` absolute at startup). The engine's processes
    stand in folders of their own (a script's, the engine's), where ``PYTHONPATH=src`` would name
    another folder, or none. An empty ``PYTHONPATH`` is no path at all, as Python reads it: left
    empty, never made this folder (an empty entry in a longer one is this folder, as there)."""
    env = dict(os.environ)
    path = env.get("PYTHONPATH")
    if path:
        cwd = os.getcwd()
        env["PYTHONPATH"] = os.pathsep.join(item if os.path.isabs(item) else os.path.join(cwd, item)
                                            for item in path.split(os.pathsep))
    return env


def _current() -> str | None:
    try:
        return CURRENT() if CURRENT is not None else None
    except Exception:  # noqa: BLE001 - a pointer that cannot be read: this release's engine starts
        return None


def _start() -> subprocess.Popen:
    """A daemon started, detached: its process. Where the device runs a newer release than this
    process's (``CURRENT``), that release's engine: its ``cadgen server --port <port>``, in this
    environment without this installation's folder on ``PYTHONPATH`` or a development name, and told
    to run as it is (``NO_DEFER_ENV``). This process attaches to it as to any engine, by protocol.
    Else this installation's daemon module, its folder first on ``PYTHONPATH``."""
    env = {name: value for name, value in environment().items() if name not in _PER_PROCESS_TELEMETRY}
    root = _daemon.engine_root()
    path = env.get("PYTHONPATH", "")
    script = _current()
    if script is not None:
        rest = [item for item in path.split(os.pathsep) if item and item != root]
        env.pop("PYTHONPATH", None)
        if rest:
            env["PYTHONPATH"] = os.pathsep.join(rest)
        for name in ("PYTHONHOME", "PYTHONPYCACHEPREFIX", _daemon.INSTALLATION_ENV):
            env.pop(name, None)
        env[NO_DEFER_ENV] = "1"
        argv = [script, "server", "--port", str(_daemon.selected_port())]
    else:
        if root not in path.split(os.pathsep):
            env["PYTHONPATH"] = os.pathsep.join(item for item in (root, path) if item)
        _daemon.bytecode(env)
        argv = [sys.executable, "-P", "-m", DAEMON_MODULE]
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               env=env, cwd=_working_folder(), **_daemon.detached())
    # Bootstrap may live as long as the server (MCP, an embedded client or a test). Reap our
    # child when it exits instead of leaving a zombie until another subprocess is started.
    if hasattr(process, "wait"):
        threading.Thread(target=process.wait, name="cadgen-server-exit", daemon=True).start()
    return process


def _working_folder() -> str | None:
    """Where the daemon (and every child it starts) stands. On POSIX the engine's own folder, which
    is this user's alone (``daemon.folder_refusal``): never the shared temporary folder above it,
    where another user could leave a file a name-resolved helper would find. On Windows the
    per-user temporary folder above it, so the engine's folder holds no process's working folder."""
    folder = _daemon.state_dir()
    if not _daemon.WINDOWS:
        return str(folder) if folder.is_dir() else None
    return str(folder.parent) if folder.parent.exists() else None


def connect(*, start: bool = False, timeout: float = 60.0, told: Callable[[str], None] | None = None,
            control: bool = False) -> Connection | None:
    """A connection to the daemon, started when ``start`` and none answers. A start first retires an
    older release's engine on the selected port once it is idle (``converge``), each line of it said to
    ``told`` (by default on stderr). In a shell whose sandbox refuses the loopback port the engine's
    HTTP server needs, none is started: that is said at once, as is a daemon that exits failing (its
    note, ``daemon.failure_path``). A ``control`` connection asks only ``status`` or ``stop`` (``hello``)."""
    if start:
        converge(told=told)
    found = _connect()
    if found is not None:
        return _greet(found, control=control)
    if not start:
        return None
    if _sandboxed():
        raise ConnectionError(SANDBOXED)
    try:
        _daemon.state_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    except PermissionError as error:
        raise _denied(f"making the engine's folder: {error.strerror or error}") from None
    refusal = _daemon.folder_refusal(_daemon.state_dir())
    if refusal is not None:  # said now, not after waiting out a daemon that cannot start there
        raise ConnectionError(refusal)
    try:  # the note is the one this start leaves
        _daemon.failure_path().unlink(missing_ok=True)
    except PermissionError as error:
        raise _denied(f"writing in the engine's folder: {error.strerror or error}") from None
    process = _start()
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        found = _connect()
        if found is not None:
            return _greet(found, control=control)
        time.sleep(0.02)
        if process.poll():  # it could not take its lock or listen: said now, not after the timeout
            raise _not_started(process.returncode)
        if time.monotonic() - started > 1.0 and process.poll() == 0:
            # A daemon that is stopping still holds the lock, and the one just started
            # left at once: start another once the lock is free.
            process = _start()
            started = time.monotonic()
    raise ConnectionError("the engine server did not start")


def missing() -> ConnectionError:
    """No engine answers at the selected port's door: what holds the port named
    (``holder``: an older release's engine, with the command that stops it, or another process);
    else the command that starts one."""
    port = _daemon.selected_port()
    found = holder(port)
    if found is not None:
        return ConnectionError(held_words(found))
    return ConnectionError(f"no cadgen server is running on port {port}; start `cadgen server --port {port}` "
                           "outside the sandbox, or start the CAD plugin. Set CADGEN_PORT to select another server; "
                           "run `cadgen doctor --json --python /path/to/project/python` for diagnostics")


def _listening(port: int) -> bool:
    """Whether something listens on loopback ``port``: a connection made and let go at once."""
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
    except OSError:
        return False
    return True


def stop_command(port: int) -> str:
    """The command that stops the engine on ``port``, as a person types it: ``--port`` only for
    a port other than the default."""
    return "cadgen stop" + ("" if port == _daemon.DEFAULT_PORT else f" --port {port}")


def legacy(port: int | None = None) -> dict[str, Any] | None:
    """The older release's engine whose HTTP server serves ``port`` (by default the selected one),
    found through its own door: ``{"port", "release", "installation"?, "pid", "address", "said"}``
    (``address`` its door, on Windows its port file; ``said`` its name in words). Once something
    listens on the port, each door in the engine's folder that no port of this protocol names
    (``daemon._tag``) is asked its status once (``_legacy_ask``); None when none serves ``port``."""
    port = _daemon.selected_port() if port is None else port
    return _older(port) if _listening(port) else None


def holder(port: int | None = None) -> dict[str, Any] | None:
    """What holds ``port`` (by default the selected one) when no engine answers at its door; None
    when nothing listens there. An older protocol's engine serving it (``legacy``: ``kind``
    ``engine``); this protocol's engine for the port while it starts or stops (``starting``:
    a cadgen holds the port and this protocol's lock for it, and its door is not there, made after
    its HTTP server binds and taken away before it closes); else the process the system names
    (``daemon.port_holder``: ``kind`` ``process``). Each with its ``pid`` and ``name`` (None where the
    system does not say) and ``cadgen``, whether its command line runs cadgen; ``said`` names it."""
    port = _daemon.selected_port() if port is None else port
    if not _listening(port):
        return None
    older = _older(port)
    if older is not None:
        return older
    pid, name, command = _daemon.port_holder(port)
    cadgen = bool(_daemon._CADGEN.search(command or ""))
    if cadgen and _locked(port):
        return {"kind": "starting", "port": port, "pid": pid, "name": name, "cadgen": True,
                "said": f"port {port}'s server ({name}, pid {pid})"}
    return {"kind": "process", "port": port, "pid": pid, "name": name, "cadgen": cadgen,
            "said": _daemon.named(pid, name, command)}


def _locked(port: int) -> bool:
    """Whether a daemon holds the lock of ``port``'s engine of this protocol: taken and let go at
    once when it is free, as ``wait_gone`` does; a lock file nobody holds is a dead engine's."""
    path = _daemon.state_dir() / f"{_daemon._tag(port=port)}.lock"
    if not path.exists():
        return False
    try:
        held = _daemon.lock(path)
    except OSError:
        return False
    if held is None:
        return True
    held.close()
    return False


def _older(port: int) -> dict[str, Any] | None:
    """``legacy``'s search of the engine's folder, once something listens on ``port``."""
    folder = _daemon.state_dir()
    if _daemon.folder_refusal(folder) is not None:
        return None  # none, or a folder another can change: nothing in it this user's engine's
    suffix, ours = (".port" if _daemon.WINDOWS else ".door"), _daemon._tag()
    try:
        tags = sorted(entry.name[:-len(suffix)] for entry in os.scandir(folder) if entry.name.endswith(suffix))
    except OSError:
        return None
    tags = [tag for tag in tags if _TAG.fullmatch(tag) and tag != ours]
    if tags:
        current = _current_tags()  # only once there is a door that may be an older engine's
        tags = [tag for tag in tags if tag not in current]
    for name in (tag + suffix for tag in tags[:LEGACY_DOORS]):
        address = folder / name
        found = _legacy_identity(_legacy_ask(address, {"op": "status"}))
        if found is not None and found["port"] == port:
            return {"kind": "engine", **found, "address": str(address), "said": _legacy_name(found)}
    return None


@functools.cache
def _current_tags() -> frozenset[str]:
    """The tag of every port's engine of this protocol: a door so named is never an older engine's,
    and is never sent a request with no handshake."""
    return frozenset(_daemon._tag(port=port) for port in range(1, 65536))


def _legacy_identity(answer: Any) -> dict[str, Any] | None:
    """What an older engine's ``status`` says of itself, and nothing else of it (its documents, its
    paths, its token): its release, the version its installation runs as, its process and the port
    its HTTP server serves; None for an answer of no such shape."""
    if not isinstance(answer, dict) or answer.get("ok") is not True:
        return None
    serving = answer.get("serving")
    port = serving.get("port") if isinstance(serving, dict) else None
    release, pid = answer.get("version"), answer.get("pid")
    if (type(port) is not int or not 1 <= port <= 65535 or not isinstance(release, str) or len(release) > 128
            or not _VERSION.fullmatch(release) or type(pid) is not int or pid <= 0):
        return None
    found: dict[str, Any] = {"port": port, "release": release, "pid": pid}
    named = answer.get("installation")
    if isinstance(named, str) and len(named) <= 128 and _VERSION.fullmatch(named):
        found["installation"] = named
    return found


def _legacy_name(found: dict[str, Any]) -> str:
    """An older engine in words: ``cadgen 0.8.1's engine (pid 83604)``."""
    return f"cadgen {found.get('installation') or found['release']}'s engine (pid {found['pid']})"


def held_words(found: dict[str, Any]) -> str:
    """The selected port held by ``found`` (``holder``), and what frees it: what ``cadgen server``,
    the MCP bootstrap and every client say. An older protocol's engine is stopped by ``cadgen stop``
    (and retired by a start once it is idle, ``retire_older``); another process is no engine this
    cadgen reaches, which it can neither use nor stop."""
    port, who = found["port"], found["said"]
    if found["kind"] == "engine":
        return f"port {port} is held by {who}: run `{stop_command(port)}` to stop it, then start again"
    if found["kind"] == "starting":
        return f"{who} holds its private lock but has not answered; it may be starting or stopping: try again once it is ready"
    if found.get("cadgen"):
        who += " that this cadgen cannot reach (another engine folder, or an older release)"
    else:
        from cadgen.engine.previous import version

        who += f", not a cadgen {version()} server"
    return f"port {port} is held by {who}: stop it or select another port with CADGEN_PORT"


def _legacy_ask(address: Path, message: dict[str, Any]) -> dict[str, Any] | None:
    """``message`` asked of the older engine at ``address`` as its protocol takes a request: a
    connection of its own, the request's line with no handshake (on Windows its token first), one
    answer line of at most ``LEGACY_BYTES``. Asked in a thread of its own and waited for at most
    ``LEGACY_SECONDS``; None when no answer comes in that time, or none of that shape."""
    answers: list[Any] = []

    def ask() -> None:
        try:
            connection = _connect(address)
        except OSError:
            return
        if connection is None:
            return
        try:
            sent = message
            if _daemon.WINDOWS:
                sent = {"token": _port_text(address).split()[1], **message}
            connection.writer.write((json.dumps(sent) + "\n").encode())
            connection.writer.flush()
            line = connection.reader.readline(LEGACY_BYTES + 1)
            if len(line) <= LEGACY_BYTES:
                answers.append(json.loads(line))
        except (OSError, ValueError, IndexError, RecursionError):
            pass
        finally:
            connection.close()

    thread = threading.Thread(target=ask, name="cadgen-older-engine", daemon=True)
    thread.start()
    thread.join(LEGACY_SECONDS)
    return answers[0] if answers and isinstance(answers[0], dict) else None


def stop_legacy(found: dict[str, Any], timeout: float = 60.0) -> bool:
    """The older engine ``found`` (``legacy``) asked to stop through its own door, as its protocol
    takes it (``{"op": "stop"}``), and waited for until it is gone, as ``sweep`` waits for this
    release's, then what its stop left of its files removed, as ``sweep`` does. False when it refuses
    the request or does not answer it; ``ConnectionError`` when it takes it and does not exit."""
    address = Path(found["address"])
    answer = _legacy_ask(address, {"op": "stop"})
    if not isinstance(answer, dict) or answer.get("ok") is not True:
        return False
    endpoint = _daemon.Endpoint(address, address.with_suffix(".lock"))
    if not wait_gone(timeout, endpoint):
        raise ConnectionError(f"{found['said']} did not exit")
    _remove_dead(endpoint)
    return True


def hello(*, control: bool = False, port: int | None = None) -> dict[str, Any]:
    """The hello this process opens a connection with: what it meets an engine by
    (``runtime.identity``: its protocol, the document format it writes, those it reads and its native
    line, with its release as information) and the port it selected (``port``, by default the selected
    one). ``control``: a connection that asks only ``status`` or ``stop`` (``daemon.CONTROL``), which an
    engine of any release, protocol, format or native line takes, so a newer cadgen can always stop an
    older engine and a person any."""
    from cadgen.engine import runtime

    message = {"op": "hello", **runtime.identity(), "port": _daemon.selected_port() if port is None else port}
    if control:
        message["control"] = True
    return message


def _greet(connection: Connection, address: Path | None = None, *, control: bool = False,
           port: int | None = None) -> Connection:
    """Validate the server before sending client environment, paths or work: what its hello's answer
    says of it (``connection.engine``: what it meets clients by, and what it runs as -- its
    ``installation``, its ``python`` line and its cadgen's ``source``, ``daemon.runs_as``; None where an
    engine from before says none) must meet this process (``runtime.refusal``: the same protocol, a
    document format it reads, the same native line; never the same release), else ``Incompatible``,
    in one line naming both sides and the remedy. A ``control`` connection (``hello``) meets any."""
    from cadgen.engine import runtime

    message = hello(control=control, port=port)
    port = message["port"]
    try:
        sent = message
        if _daemon.WINDOWS:
            sent = {"token": _port_text(address or _daemon.port_path()).split()[1], **message}
        connection.writer.write((json.dumps(sent) + "\n").encode())
        connection.writer.flush()
        answer = json.loads(connection.reader.readline() or b"{}")
        if not isinstance(answer, dict):
            raise ConnectionError("the selected cadgen server answered no handshake this cadgen knows" + DIAGNOSTICS)
        engine = {key: answer.get(key) for key in ("protocol", "release", "port", "writes", "reads", "native",
                                                   "installation", "python", "source")}
        if answer.get("failed"):
            refused = None if control else runtime.refusal(message, answer, port=port)
            if refused is not None:
                raise Incompatible(str(refused), engine, refused.what)
            if type(answer.get("protocol")) is int and isinstance(answer.get("release"), str):
                raise Incompatible(str(answer["failed"]) + DIAGNOSTICS, engine)  # it named itself, and refused
            raise ConnectionError(str(answer["failed"]) + DIAGNOSTICS)
        if (answer.get("ok") is not True or answer.get("port") != port or not isinstance(answer.get("instance"), str)
                or not answer["instance"] or type(answer.get("protocol")) is not int):
            raise ConnectionError("the selected cadgen server answered no handshake this cadgen knows" + DIAGNOSTICS)
        if not control:
            refused = runtime.refusal(message, answer, port=port)
            if refused is not None:
                raise Incompatible(str(refused), engine, refused.what)
        connection.engine_identity = {key: answer[key] for key in ("protocol", "release", "port", "instance")}
        connection.engine = engine
        return connection
    except BaseException:
        connection.close()
        raise


def converge(port: int | None = None, *, told: Callable[[str], None] | None = None) -> dict[str, Any] | None:
    """What a start does first (``connect(start=True)``, the MCP bootstrap's; ``cadgen server``'s): the
    engine of an older release serving the selected port (``port``) retired once it is idle
    (``retire_older``), so the device runs the newest engine installed on it, and said to ``told`` (by
    default on stderr): ``retired cadgen 0.8.2's engine (pid N) for 0.8.3``. One this cadgen cannot
    use -- another protocol, a format it does not read, another native line, an older protocol's door
    -- is waited for (``RETIRE_SECONDS``), and still in use refused by name (``InUse``): nothing can
    start in its place. One it can use is asked once and, in use, serves on, said to ``told``. An
    engine of this release or a newer one is never retired. The retired engine's identity
    (``retire_older``), or None."""
    port = _daemon.selected_port() if port is None else port
    say = told or _say
    found = _older_engine(port)
    if found is None:
        return None
    try:
        retired = _retire(found, port, 0.0 if found["usable"] else RETIRE_SECONDS)
    except InUse as busy:
        if not found["usable"]:
            raise
        say(f"{found['said']} on port {port} is in use by {' and '.join(busy.uses)}, so it serves on for "
            f"{_daemon.installation()}: {_freed(busy.found['status'])} or run `{stop_command(port)}` to update it")
        return None
    if retired is not None:
        say(retired_words(retired))
    return retired


def retire_older(port: int | None = None, *, wait: float = 10.0) -> dict[str, Any] | None:
    """The engine of an older cadgen release serving ``port`` (by default the selected one) retired:
    found through its own door -- this protocol's, asked over a control connection (``hello``), whose
    release is older than this installation's (``daemon.rank``), or an older protocol's (``legacy``:
    0.8.0 and 0.8.1) -- waited for, up to ``wait`` seconds, until it is idle (its ``status``: no
    holders, no page watching, no build, draw or HTTP work underway), stopped through its door (this
    protocol's engine only while still idle) and waited for until it is gone. Its
    ``{"release", "pid", "port"}`` (``release`` as it names itself: a development install's
    ``<version>-dev.<time>``), which ``retired_words`` says; None when no older engine serves the port
    (none, one of this release or a newer one: never retired). ``ConnectionError`` in one line when it
    is still in use after ``wait`` (``InUse``: what uses it, by its status's counts, and what frees
    it), and when it refuses the stop or does not exit."""
    port = _daemon.selected_port() if port is None else port
    found = _older_engine(port)
    return None if found is None else _retire(found, port, wait)


def retired_words(retired: dict[str, Any]) -> str:
    """A retirement (``retire_older``) in words, as a start says it once:
    ``retired cadgen 0.8.2's engine (pid 4242) for 0.8.3``."""
    return f"retired cadgen {retired['release']}'s engine (pid {retired['pid']}) for {_daemon.installation()}"


def _say(line: str) -> None:
    print(f"cadgen: {line}", file=sys.stderr)


def _retire(found: dict[str, Any], port: int, wait: float) -> dict[str, Any] | None:
    """``retire_older`` of the engine ``found`` (``_older_engine``)."""
    deadline = time.monotonic() + max(0.0, wait)
    status = found["status"]
    while True:
        uses = _uses(status)
        if uses is None:
            raise ConnectionError(f"port {port} is held by {found['said']}, which this cadgen cannot ask whether it "
                                  f"is in use: run `{stop_command(port)}`")
        if not uses:
            break
        if time.monotonic() >= deadline:
            raise InUse(_in_use(found, port, status, uses), {**found, "status": status}, uses)
        time.sleep(RETIRE_POLL)
        fresh = _status_of(found, port)
        if fresh is None:
            if not _answering(Path(found["address"])):
                return None  # gone meanwhile: nothing older serves the port
            continue
        status = fresh
    if not _stop_older(found, port):
        return None  # gone meanwhile, another start's retirement: nothing older serves the port
    return {"release": found["release"], "pid": found["pid"], "port": port}


def _older_engine(port: int) -> dict[str, Any] | None:
    """The engine of an older release serving ``port``, found through its own door: this protocol's,
    asked its status over a control connection (``_control``), or an older protocol's (``legacy``).
    ``{"kind": "current" | "legacy", "release", "pid", "address", "said", "status", "usable"}``: its
    release as it names itself (its installation's version, else its release), its door, its name in
    words, its status, and whether this cadgen can use it (``runtime.refusal``). None when none serves
    the port, or the one that does is of this release or a newer one."""
    from cadgen.engine import runtime

    folder = _daemon.state_dir()
    address = folder / f"{_daemon._tag(port=port)}{'.port' if _daemon.WINDOWS else '.door'}"
    answered = _control(address, port, {"op": "status"})
    if answered is not None:
        engine, status = answered
        if not isinstance(status, dict) or status.get("ok") is not True:
            return None
        release = status.get("version") if isinstance(status.get("version"), str) else engine.get("release")
        named = status.get("installation") if isinstance(status.get("installation"), str) else release
        pid = status.get("pid")
        if not isinstance(named, str) or not _VERSION.fullmatch(named) or type(pid) is not int or not _below(named, release):
            return None
        return {"kind": "current", "release": named, "pid": pid, "address": str(address),
                "said": f"cadgen {named}'s engine (pid {pid})", "status": status,
                "usable": runtime.refusal(hello(port=port), engine, port=port) is None}
    older = legacy(port)
    if older is None:
        return None
    named = older.get("installation") or older["release"]
    if not _below(named, older["release"]):
        return None
    status = _legacy_ask(Path(older["address"]), {"op": "status"})
    return {**older, "kind": "legacy", "release": named, "status": status, "usable": False}


def _below(named: str, release: Any) -> bool:
    """Whether an engine that names itself ``named`` (its installation's version) of release
    ``release`` is older than this installation (``daemon.installation``), as ``daemon.rank`` orders
    versions; by release where either name is no version; never when neither can be ordered."""
    from cadgen.engine.previous import version

    ours, theirs = _daemon.rank(_daemon.installation()), _daemon.rank(named)
    if ours is None or theirs is None:
        ours, theirs = _daemon.rank(version()), _daemon.rank(release)
    return ours is not None and theirs is not None and theirs < ours


def _control(address: Path, port: int, message: dict[str, Any]) -> tuple[dict[str, Any], Any] | None:
    """``message`` (``status``, ``stop``) asked of this protocol's engine at ``address`` over a control
    connection (``hello``), which an engine of any release, format or native line takes: what it says
    of itself in its hello's answer, and its answer. None when none answers there, or it refuses."""
    try:
        connection = _connect(address)
    except ConnectionError:
        return None
    if connection is None:
        return None
    try:
        _greet(connection, address, control=True, port=port)
    except (OSError, ValueError):
        return None  # closed by ``_greet``
    try:
        return connection.engine, _exchange(connection, message, address=address)
    except (OSError, ValueError):
        return None


def _status_of(found: dict[str, Any], port: int) -> Any:
    """The status of the engine ``found`` (``_older_engine``) asked again through its door; None when
    no answer comes."""
    address = Path(found["address"])
    if found["kind"] == "legacy":
        return _legacy_ask(address, {"op": "status"})
    answered = _control(address, port, {"op": "status"})
    return None if answered is None else answered[1]


def _uses(status: Any) -> list[str] | None:
    """What uses an engine, by its ``status``, in words: its holds (an agent host's app server), the
    pages that watch its documents, its builds, draws and HTTP work; [] when nothing does; None when
    its status does not say."""
    if not isinstance(status, dict) or not {"holders", "watched", "busy", "active"} <= status.keys():
        return None
    holders, watched, busy = status["holders"], status["watched"], status["busy"]
    if any(type(count) is not int or count < 0 for count in (holders, watched, busy)):
        return None
    counts = ((holders, "app server"), (watched, "open page"), (busy + bool(status["active"]), "request"))
    return [f"{count} {noun}{'' if count == 1 else 's'}" for count, noun in counts if count]


def _freed(status: dict[str, Any]) -> str:
    """What frees an engine in use, by its ``status``: its app quit, its page closed, else its work done."""
    return "quit that app" if status.get("holders") else "close that page" if status.get("watched") else "let it finish"


def _in_use(found: dict[str, Any], port: int, status: dict[str, Any], uses: list[str]) -> str:
    return (f"port {port} is held by {found['said']}, still in use by {' and '.join(uses)}: {_freed(status)} or run "
            f"`{stop_command(port)}`")


def _stop_older(found: dict[str, Any], port: int) -> bool:
    """The idle older engine ``found`` (``_older_engine``) stopped through its own door and waited for
    until it is gone, its door, its lock and its port let go: an older protocol's as ``stop_legacy``
    stops one; this protocol's asked to stop only while still idle (``{"op": "stop", "idle": true}``),
    and refused by it, with its uses, when anything has come to use it since (``InUse``). False when it
    went meanwhile, another start's to retire: its going waited for all the same."""
    exited = f"port {port} is held by {found['said']}, which did not exit when asked to stop: run `{stop_command(port)}`"
    address = Path(found["address"])
    endpoint = _daemon.Endpoint(address, address.with_suffix(".lock"))
    stopped = True
    if found["kind"] == "legacy":
        try:
            taken = stop_legacy(found, STOP_SECONDS)
        except ConnectionError:
            raise ConnectionError(exited) from None
        if not taken:
            if _answering(address):
                raise ConnectionError(f"port {port} is held by {found['said']}, which did not take the stop request: "
                                      f"stop it with `cadgen +{found['release']} stop`")
            stopped = False
    else:
        answered = _control(address, port, {"op": "stop", "idle": True})
        answer = None if answered is None else answered[1]
        if not isinstance(answer, dict) or answer.get("ok") is not True:
            uses = _uses(answer)
            if uses:
                raise InUse(_in_use(found, port, answer, uses), {**found, "status": answer}, uses)
            if _answering(address):
                raise ConnectionError(f"port {port} is held by {found['said']}, which did not take the stop request: "
                                      f"run `{stop_command(port)}`")
            stopped = False
    if not wait_gone(STOP_SECONDS, endpoint):
        raise ConnectionError(exited)
    _remove_dead(endpoint)
    deadline = time.monotonic() + STOP_SECONDS
    while _listening(port) and time.monotonic() < deadline:
        time.sleep(0.05)  # its HTTP server let go of the port as it stopped; a start binds it next
    return stopped


def wait_gone(timeout: float = 60.0, endpoint: _daemon.Endpoint | None = None) -> bool:
    """Wait until the daemon (by default the selected port's) is gone: its door no longer answers
    and its lock, held until its workers have stopped, is free."""
    deadline = time.monotonic() + timeout
    lock = endpoint.lock if endpoint else _daemon.lock_path()
    while time.monotonic() < deadline:
        if not _answering(endpoint.address if endpoint else _daemon.address()):
            if not lock.exists():
                return True  # it removed its lock as it let it go (``daemon.let_go``)
            held = _lock(lock)
            if held is not None:
                held.close()
                return True
        time.sleep(0.05)
    return False


def hold(*, start: bool = False, host: Callable[[], str | None] | None = None,
         holder: str | None = None, told: Callable[[str], None] | None = None) -> Connection | None:
    """A hold on the engine (``Daemon.hold``), explicitly bootstrapped only when ``start``, an older
    release's engine retired first once idle (``converge``: each line said to ``told``). The
    connection owns its MCP sessions. Reading it waits until
    the engine goes (its end of file). None when none runs and ``start`` is false. ``host()``, asked
    once the engine answers, names the agent host the holder serves (its ``status`` counts it);
    ``holder``, the name its MCP sessions are opened under, which end when the hold does."""
    connection = connect(start=start, told=told)
    if connection is None:
        return None
    try:
        message: dict[str, Any] = {"op": "hold", "engineIdentity": connection.engine_identity}
        named = host() if host is not None else None
        if named:
            message["host"] = named
        if holder:
            message["holder"] = holder
        if _daemon.WINDOWS:
            message = {"token": _daemon.port_path().read_text(encoding="utf-8").split()[1], **message}
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        if json.loads(connection.reader.readline() or b"{}").get("ok") is not True:
            raise ConnectionError("the engine server did not take the hold")
    except BaseException:
        connection.close()
        raise
    return connection


def request(message: dict[str, Any], on_log: Callable[[dict[str, Any]], None] = lambda _m: None, *,
            start: bool | None = None, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any] | None:
    """Send one request; every log line to ``on_log`` and every progress frame of its build to
    ``on_progress`` (``progress.py``); the final answer returned (None when no daemon is up and
    ``start`` is false). A ``stop`` goes over a control connection (``hello``): an explicit stop stops
    the selected port's engine of any release, protocol, format or native line."""
    connection = connect(start=start is True, control=message.get("op") == "stop")
    if connection is None:
        if start is None:
            raise missing()
        return None
    return _exchange(connection, message, on_log, on_progress)


def _exchange(connection: Connection, message: dict[str, Any], on_log: Callable[[dict[str, Any]], None] = lambda _m: None,
              on_progress: Callable[[dict[str, Any]], None] | None = None, address: Path | None = None,
              control: bool = False) -> dict[str, Any]:
    if not hasattr(connection, "engine_identity"):
        _greet(connection, address, control=control)
    message = {**message, "engineIdentity": connection.engine_identity}
    with connection:
        if _daemon.WINDOWS:
            # The token first, so the daemon checks it before reading the request body.
            message = {"token": _port_text(address or _daemon.port_path()).split()[1], **message}
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        for line in connection.reader:
            answer = json.loads(line)
            if "log" in answer:
                on_log(answer)
                continue
            if set(answer) == {"progress"}:
                if on_progress is not None:
                    on_progress(answer["progress"])
                continue
            notice = answer.pop("notice", None)
            # Diagnostic notices, when the server has any.
            for said in (notice or "").splitlines():
                print(f"cadgen: {said}", file=sys.stderr)
            return answer
    raise ConnectionError("the engine server closed the connection")


def sweep(*, stop: bool) -> dict[str, list[str]]:
    """The selected port's daemon: with ``stop``, stopped and waited for until gone;
    a live one left running listed in ``running``. The door and lock files of a dead one -- nothing
    answers there and nobody holds its lock -- are removed (``removed``). A daemon starting or
    stopping holds its lock before it listens and until it has left, so its files are never taken."""
    found: dict[str, list[str]] = {"stopped": [], "running": [], "removed": []}
    for endpoint in _daemon.endpoints():
        if _answering(endpoint.address):
            if not stop:
                found["running"].append(str(endpoint.address))
                continue
            connection = _connect(endpoint.address)
            if connection is None:
                continue  # it went meanwhile: gone, as asked
            _exchange(connection, {"op": "stop"}, address=endpoint.address, control=True)  # any release's
            if not wait_gone(endpoint=endpoint):
                raise ConnectionError(f"the engine server at {endpoint.address} did not exit")
            found["stopped"].append(str(endpoint.address))
            _remove_dead(endpoint)  # what an engine from before engines removed their own files left: its stop's
            continue
        found["removed"] += _remove_dead(endpoint)
    return found


def _remove_dead(endpoint: _daemon.Endpoint) -> list[str]:
    """The files of ``endpoint`` removed when its daemon is dead: its lock free (taken here while
    they go, so no daemon starts between) and nothing answering at its address."""
    present = [path for path in (endpoint.address, endpoint.lock) if path.exists() or path.is_symlink()]
    if not present or _daemon.folder_refusal(endpoint.lock.parent) is not None:
        return []  # nothing, or a folder another can change: none of it this user's daemon's to remove
    held = _lock(endpoint.lock)
    if held is None:
        return []  # a daemon holds it: starting, stopping or running
    removed: list[str] = []
    try:
        if _answering(endpoint.address):
            return []
        for path in present:
            if _daemon.WINDOWS and path == endpoint.lock:
                continue  # an open file is not removed on Windows: after the lock is let go
            try:
                path.unlink()
                removed.append(str(path))
            except FileNotFoundError:
                pass
    finally:
        held.close()
    if _daemon.WINDOWS and endpoint.lock in present:
        try:
            endpoint.lock.unlink()
            removed.append(str(endpoint.lock))
        except OSError:
            pass
    return removed
