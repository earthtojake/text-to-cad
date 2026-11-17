"""Reaching the server: connect through its door (on Windows, its loopback port). Nothing here starts one but
``start`` (``cad server start``, ``cad mcp``): a client that finds none is told so in one line (``NotRunning``), and a
``cad`` command that finds one of another release is too (``OtherRelease``, ``RELEASE``)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from cad.engine import places
from cad.engine.atomic_replace import RETRY_DELAYS_SECONDS
from cad.engine.door import DOOR_PROTOCOL, GREETING_SECONDS, HELLO_LIMIT, Connection, answering, dial, greeted, hello, \
    released
from cad.engine.previous import version
from cad.engine.said import COMMAND, SERVER

__all__ = ["hold", "make_way", "request", "start", "sweep"]

# The module the server runs as: the daemon with its application host installed. Named, never imported: the
# library's engine imports nothing of the server's (``start`` runs it in this process's own environment).
DAEMON_MODULE = "cad_server._internal.engine_daemon"
# The sandboxes known to refuse the loopback port the engine's HTTP server needs, each by a variable
# and the value it sets in the shells it runs: a daemon started there could never serve a build (an agent
# app's shell sandbox, in its default mode, with its network disabled). A sandbox none names is found by the
# daemon that cannot listen (``places.failure_path``), as fast.
SANDBOXES: tuple[tuple[str, str], ...] = (("CODEX_SANDBOX_NETWORK_DISABLED", "1"),)
# The words a worker's failure carries its stderr's tail under (``supervisor.Process``): local detail, which
# no observer's facts carry (``api._error``), even when a startup failure or a broken pipe has no exit
# status to tell it from a Python traceback.
WORKER_STDERR = "\nWorker stderr (last 16384 characters):\n"
# The command that starts the server, and the one line a client says where none answers.
START = f"{COMMAND} server start"
NOT_RUNNING = f"the {COMMAND} server is not running: run `{START}`"
SANDBOXED = (f"the {COMMAND} server is not running, and this shell's sandbox cannot start one: run `{START}` outside "
             "the sandbox, and every later command finds it running")
# How long a start waits for a server of another release to go once told to stop: an agent app gives the server
# line that starts one 30 seconds in all. And how long it waits for its own server's door.
STOP_SECONDS = 10.0
START_SECONDS = 60.0
# The release a ``cad`` command holds the server it reaches to: its own, which the command line sets
# (``cad_server.cli``). None, every other process's -- a person's own Python, a model ``cad run`` runs, a worker --
# reaches a server of any release, whose builds the worker contract alone refuses (``contract.refusal``).
RELEASE: str | None = None


class NotRunning(ConnectionError):
    """No server answers: ``NOT_RUNNING``, which every command says as its failure (``not_running``)."""


class OtherRelease(ConnectionError):
    """A ``cad`` command's server is of another release (``RELEASE``): both said, and the two ways on."""


def _other(theirs: str | None, mine: str) -> str:
    """``OtherRelease``'s line: this release, the server's -- one of 0.11.10 or earlier names none -- and the ways on."""
    if theirs is None:
        return f"{COMMAND} here is {mine}; the running server is an earlier release's: run `{START}` to run {mine}'s server"
    return (f"{COMMAND} here is {mine}; the running server is {theirs}: install {COMMAND} {theirs}, or run `{START}` "
            f"to run {mine}'s server")


def _connect(address: Path | None = None, *, stopping: bool = False) -> Connection | None:
    """A connection to the daemon at ``address`` (its door, on Windows its port file; by default
    the engine's), or None when none answers there or it greets in a protocol this side does not
    speak. ``ConnectionError`` when the system refuses this process the engine's folder (a sandbox
    that forbids writing there); None instead for a daemon told to stop (``stopping``: ``wait_gone``),
    whose stop a sandbox would have refused already: Windows refuses every open of a file being removed
    until the last handle on it closes, however long that takes, so its port file refused then is
    going with it."""
    try:
        if places.WINDOWS:
            port, token = _port_text(address or places.port_path()).split()
            connection = socket.create_connection(("127.0.0.1", int(port)), timeout=5)
            stream = connection.makefile("rwb")
            try:  # the door's hello and greeting on the port: the token where a pair's id goes
                connection.settimeout(GREETING_SECONDS)
                stream.write(hello(token))
                stream.flush()
                line = stream.readline(HELLO_LIMIT)
                connection.settimeout(None)
            except OSError:
                line = b""
            spoken = greeted(line)
            if spoken is None or spoken > DOOR_PROTOCOL:
                stream.close()
                connection.close()
                return None
            return Connection(stream, stream, stream, connection, protocol=spoken, release=released(line))
        door = address or places.door_path()
        if places.folder_refusal(door.parent) is not None or not door.exists():
            return None
        return dial(door)
    except PermissionError as error:
        if stopping:
            return None
        raise _denied(f"opening a pipe in the engine's folder {places.engine_dir()}: {error.strerror or error}") from None
    except (OSError, ValueError):
        return None


def _port_text(path: Path) -> str:
    """A Windows engine's port file. Windows refuses a reader (EACCES) while the file is renamed
    into place or removed -- an engine starting, which ``start`` polls, or stopping -- so that
    refusal waits out the ladder the writer's rename does (``atomic_replace``) before it is said to be
    the system's."""
    for delay in RETRY_DELAYS_SECONDS:
        try:
            return path.read_text(encoding="utf-8")
        except PermissionError:
            time.sleep(delay)
    return path.read_text(encoding="utf-8")


def _answering(address: Path, *, stopping: bool = False) -> bool:
    """Whether a daemon answers at ``address``, asked without a request: its door takes a writer
    (on Windows, its port takes a connection). ``stopping``: ``_connect``'s."""
    if not places.WINDOWS:
        return answering(address)
    connection = _connect(address, stopping=stopping)
    if connection is None:
        return False
    connection.close()
    return True


def _sandboxed() -> bool:
    return any(os.environ.get(name) == value for name, value in SANDBOXES)


def _denied(cause: str) -> ConnectionError:
    """The engine refused by the system (a sandbox that forbids writing in the engine's folder),
    said to the agent or person who runs the command."""
    return ConnectionError(f"the system denies {SERVER}'s engine ({cause}); a sandbox that forbids "
                           "it does: run this command outside it, or with the sandbox's permission")


def _lock(path: Path | None = None) -> Any:
    """``places.lock`` taken by a client (to see a daemon gone, or its files dead): a folder refused
    (``places.folder_refusal``) or denied by the system said in one line, as ``connect`` says it."""
    try:
        return places.lock(path)
    except PermissionError as error:
        if error.errno is None:  # ``folder_refusal``'s words
            raise ConnectionError(str(error)) from None
        raise _denied(f"taking the lock in the engine's folder {places.engine_dir()}: "
                      f"{error.strerror or error}") from None


def _not_started(code: int) -> ConnectionError:
    """A daemon that exited at once, failing (``daemon.main``): the reason its note gives."""
    try:
        note = json.loads(places.failure_path().read_text(encoding="utf-8"))
        reason, denied = str(note["reason"]), bool(note.get("denied"))
    except (OSError, ValueError, KeyError, TypeError):
        reason, denied = f"it exited with code {code}", False
    if denied:
        return ConnectionError(f"{SANDBOXED} ({reason})")
    return ConnectionError(f"the engine server did not start: {reason}")


# Switches that govern only the process they are set in -- ``DO_NOT_TRACK`` and
# ``CAD_TELEMETRY`` (the distribution's ``cad_server.analytics.ENVIRONMENT``). The daemon serves
# every later client, so it is one of the "processes started for others" that go by the
# person's saved choice, never by the switch of whichever client happened to start it. The
# engine imports nothing of cadgen (law 3), so it carries the names here rather than importing them.
_PER_PROCESS_TELEMETRY = ("DO_NOT_TRACK", "CAD_TELEMETRY")


def environment() -> dict[str, str]:
    """This process's environment as the engine is handed it: ``os.environ``, every relative
    ``PYTHONPATH`` entry made absolute against this process's working folder, as Python resolves it
    for ``python SCRIPT`` (``site`` makes ``sys.path`` absolute at startup). The engine's processes
    stand in folders of their own (a script's, the engine's), where ``PYTHONPATH=src`` would name
    another folder, or none."""
    env = dict(os.environ)
    path = env.get("PYTHONPATH")
    if path:
        cwd = os.getcwd()
        env["PYTHONPATH"] = os.pathsep.join(item if not item or os.path.isabs(item) else os.path.join(cwd, item)
                                            for item in path.split(os.pathsep))
    return env


def _spawn(port: int | None) -> subprocess.Popen:
    """A server started, detached, by this process's own Python (``sys.executable``: the environment's
    interpreter, never the ``cad`` launcher), its standard streams the null device and a session of its own --
    on Windows a process group and a console of its own, with no window (``places.detached``) -- so it holds
    nothing of the command that started it, and that command, and on Windows its ``cad.exe``, exits as soon as
    the server answers. ``port``: the HTTP port it must take. The engine's folder is first on its ``PYTHONPATH``
    only where this environment would not find it -- a source tree --, so no process the daemon starts in the
    base inherits it."""
    env = {name: value for name, value in environment().items() if name not in _PER_PROCESS_TELEMETRY}
    root, path = places.engine_root(), env.get("PYTHONPATH", "")
    inside = os.path.normcase(os.path.realpath(sys.prefix)).rstrip(os.sep) + os.sep
    if not os.path.normcase(os.path.realpath(root)).startswith(inside) and root not in path.split(os.pathsep):
        env["PYTHONPATH"] = os.pathsep.join(item for item in (root, path) if item)
    places.bytecode(env)
    return subprocess.Popen([sys.executable, "-P", "-m", DAEMON_MODULE, *(["--port", str(port)] if port is not None
                                                                         else [])],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                            cwd=_working_folder(), **places.detached())


def _working_folder() -> str | None:
    """Where the daemon (and every child it starts) stands. On POSIX the engine's own folder, which
    is this user's alone (``places.folder_refusal``): never the shared temporary folder above it,
    where another user could leave a file a name-resolved helper would find. On Windows the
    per-user temporary folder above it, so the engine's folder holds no process's working folder."""
    folder = places.engine_dir()
    if not places.WINDOWS:
        return str(folder) if folder.is_dir() else None
    return str(folder.parent) if folder.parent.exists() else None


def make_way() -> str | None:
    """Room made for this release's server, as ``start`` makes it, and ``cad server start --foreground`` before it
    runs one in its own process: a server of another release -- or one whose greeting names none, of 0.11.10 or
    earlier -- told to stop at once, its work cut short, and waited for, ``STOP_SECONDS`` at most (``sweep``). Where a
    server of this release answers, nothing is done, and that is said in one line (returned); else None.
    ``ConnectionError`` in one line where room cannot be made: in a shell whose sandbox refuses the loopback port a
    server needs (``SANDBOXED``), before anything is stopped, and where the server told to stop did not go."""
    found = _connect()
    if found is not None:
        found.close()
        if found.release == version():
            return f"the {COMMAND} server ({COMMAND} {version()}) is already running"
    if _sandboxed():
        raise ConnectionError(SANDBOXED)
    if found is not None:
        sweep(stop=True, seconds=STOP_SECONDS)
    return None


def start(port: int | None = None) -> str:
    """This release's server running: the one function that starts a server (``cad server start``, ``cad mcp``),
    once room is made for it (``make_way``) -- started (``_spawn``; ``port``, the HTTP port it must take) and waited
    for until its door answers. Starts at the same moment end with one server, by the daemon's lock. What was done,
    in one line. ``ConnectionError`` in one line where it could not be: room not made (``make_way``), a server that
    did not start (its note, ``places.failure_path``), and one of another release that a start at the same moment
    started (``OtherRelease``)."""
    running = make_way()
    if running is not None:
        return running
    try:
        places.make_engine_dir()
    except PermissionError as error:
        raise _denied(f"making the engine's folder: {error.strerror or error}") from None
    refusal = places.folder_refusal(places.engine_dir())
    if refusal is not None:  # said now, not after waiting out a daemon that cannot start there
        raise ConnectionError(refusal)
    try:  # the note is the one this start leaves
        places.failure_path().unlink(missing_ok=True)
    except PermissionError as error:
        raise _denied(f"writing in the engine's folder: {error.strerror or error}") from None
    process = _spawn(port)
    began = time.monotonic()
    deadline = began + START_SECONDS
    while (answered := _connect()) is None:
        if time.monotonic() > deadline:
            raise ConnectionError("the engine server did not start")
        time.sleep(0.02)
        if process.poll():  # it could not take its lock or listen: said now, not after the timeout
            raise _not_started(process.returncode)
        if time.monotonic() - began > 1.0 and process.poll() == 0:
            # A daemon that is stopping still holds the lock, and the one just started left at once: started
            # again once the lock is free.
            process = _spawn(port)
            began = time.monotonic()
    answered.close()
    if answered.release != version():
        raise OtherRelease(_other(answered.release, version()))
    if _joined(process):
        return f"the {COMMAND} server ({COMMAND} {version()}) is already running"
    return f"started the {COMMAND} server ({COMMAND} {version()})"


def _joined(process: subprocess.Popen) -> bool:
    """Whether the server that answered a start is another start's, not the one ``process`` is: that process has
    exited (a daemon that finds the lock taken exits 0), or, on POSIX, where the process started is the server, the
    server answers with another process id. On Windows the process started may be an environment's launcher whose
    child serves, so its id says nothing."""
    if process.poll() is not None:
        return True
    if places.WINDOWS:
        return False
    try:
        answer = request({"op": "pid"}, start=False)
    except ConnectionError:
        return False
    return isinstance(answer, dict) and answer.get("pid") not in (None, process.pid)


def connect(*, start: bool = True) -> Connection | None:
    """A connection to the server, which a connection never starts (the module's ``start()`` alone does): with none
    answering, ``NotRunning`` in its one line -- or None, with ``start`` false, for a client that needs none and
    asks whether one runs. In a ``cad`` command (``RELEASE``) a server of another release is refused too, in the one
    line that says both releases (``OtherRelease``)."""
    found = _connect()
    if found is None:
        if not start:
            return None
        raise NotRunning(NOT_RUNNING)
    if RELEASE is not None and found.release != RELEASE:
        found.close()
        raise OtherRelease(_other(found.release, RELEASE))
    return found


def wait_gone(timeout: float = 60.0, endpoint: places.Endpoint | None = None) -> bool:
    """Wait until the daemon, told to stop, is gone: its door no longer answers -- its port file,
    refused as it is removed, does not (``_connect``) -- and its lock, held until its workers have
    stopped, is free."""
    deadline = time.monotonic() + timeout
    lock = endpoint.lock if endpoint else places.lock_path()
    while time.monotonic() < deadline:
        if not _answering(endpoint.address if endpoint else places.address(), stopping=True):
            if not lock.exists():
                return True  # it removed its lock as it let it go (``daemon.let_go``)
            held = _lock(lock)
            if held is not None:
                held.close()
                return True
        time.sleep(0.05)
    return False


def hold(*, start: bool = True, host: Callable[[], str | None] | None = None,
         holder: str | None = None) -> Connection | None:
    """A hold on the server (``Daemon.hold``): while the connection returned stays open, the engine does not stop
    for idleness. Reading it waits until the engine goes (its end of file). With none running, ``NotRunning`` -- or
    None, with ``start`` false (``connect``). ``host()``, asked once the engine answers, names the agent host the
    holder serves (its ``status`` counts it); ``holder``, the name its MCP sessions are opened under, which end when
    the hold does."""
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
        if places.WINDOWS:
            message = {"token": places.port_path().read_text(encoding="utf-8").split()[1], **message}
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        if json.loads(connection.reader.readline() or b"{}").get("ok") is not True:
            raise ConnectionError("the engine server did not take the hold")
    except BaseException:
        connection.close()
        raise
    return connection


def request(message: dict[str, Any], on_log: Callable[[dict[str, Any]], None] = lambda _m: None, *,
            start: bool = True, on_progress: Callable[[dict[str, Any]], None] | None = None,
            timeout: float | None = None) -> dict[str, Any] | None:
    """Send one request; every log line to ``on_log`` and every progress frame of its build to
    ``on_progress`` (``progress.py``); the final answer returned. With no server running, ``NotRunning`` -- or
    None, with ``start`` false (``connect``). ``timeout``: the seconds the whole request, its connection and its
    answer, may take, past which ``Unanswered`` says so (the request is left to end by itself, on a thread of its
    own); None, as long as it takes."""
    if timeout is not None:
        return _within(timeout, lambda: request(message, on_log, start=start, on_progress=on_progress))
    connection = connect(start=start)
    if connection is None:
        return None
    return _exchange(connection, message, on_log, on_progress)


class Unanswered(ConnectionError):
    """A request the server did not answer within its time limit (``request``'s ``timeout``)."""


def _within(seconds: float, work: Callable[[], Any]) -> Any:
    """What ``work`` returns or raises, run on a thread of its own and waited for ``seconds`` at most: past them,
    ``Unanswered``."""
    import threading

    done: list[tuple[bool, Any]] = []

    def run() -> None:
        try:
            done.append((True, work()))
        except BaseException as error:  # noqa: BLE001 - raised again in the caller's thread
            done.append((False, error))

    thread = threading.Thread(target=run, name="cad-request", daemon=True)
    thread.start()
    thread.join(seconds)
    if not done:
        raise Unanswered(f"the {COMMAND} server did not answer within {seconds:g} s")
    answered, value = done[0]
    if answered:
        return value
    raise value


def _exchange(connection: Connection, message: dict[str, Any], on_log: Callable[[dict[str, Any]], None] = lambda _m: None,
              on_progress: Callable[[dict[str, Any]], None] | None = None, address: Path | None = None) -> dict[str, Any]:
    if places.WINDOWS:  # the token in the request too, which the daemon checks as it did the hello's
        message = {"token": (address or places.port_path()).read_text(encoding="utf-8").split()[1], **message}
    with connection:
        connection.writer.write((json.dumps(message) + "\n").encode())
        connection.writer.flush()
        for line in connection.reader:
            answer = json.loads(line)
            if answer.get("stream") == "making":  # an environment the request waits on, made meanwhile: said here
                print(f"cad: {answer.get('log', '')}", file=sys.stderr, flush=True)
                continue
            if "log" in answer:
                on_log(answer)
                continue
            if set(answer) == {"progress"}:
                if on_progress is not None:
                    on_progress(answer["progress"])
                continue
            _notice(answer.pop("notice", None))
            return answer
    raise ConnectionError("the engine server closed the connection")


def _notice(notice: str | None) -> None:
    """The request that bound the engine's port, when that start moved the port (``daemon.bind``): a line each on
    stderr, after whatever the command has printed on stdout so far (flushed first) and before anything it prints
    next, so that a terminal reading both, or a pipe of ``2>&1``, never has the note inside a command's output."""
    lines = (notice or "").splitlines()
    if not lines:
        return
    sys.stdout.flush()
    for said in lines:
        print(f"cad: {said}", file=sys.stderr)
    sys.stderr.flush()


def sweep(*, stop: bool, seconds: float = 60.0) -> dict[str, list[str]]:
    """The engine of this engine folder (``places.endpoints``): with ``stop``, stopped if it lives and
    waited for until gone, ``seconds`` at most (``stopped``, its door or port file); a live one left running
    listed in ``running``. The door and lock files of a dead one -- nothing answers there and nobody holds its
    lock -- are removed (``removed``). A daemon starting or stopping holds its lock before it listens
    and until it has left, so its files are never taken."""
    found: dict[str, list[str]] = {"stopped": [], "running": [], "removed": []}
    for endpoint in places.endpoints():
        if _answering(endpoint.address):
            if not stop:
                found["running"].append(str(endpoint.address))
                continue
            connection = _connect(endpoint.address)
            if connection is None:
                continue  # it went meanwhile: gone, as asked
            _exchange(connection, {"op": "stop"}, address=endpoint.address)
            if not wait_gone(seconds, endpoint=endpoint):
                raise ConnectionError(f"the engine server at {endpoint.address} did not exit")
            found["stopped"].append(str(endpoint.address))
            _remove_dead(endpoint)  # what it left, should it have died before removing its files
            continue
        found["removed"] += _remove_dead(endpoint)
    return found


def _remove_dead(endpoint: places.Endpoint) -> list[str]:
    """The files of ``endpoint`` removed when its daemon is dead: its lock free (taken here while
    they go, so no daemon starts between) and nothing answering at its address."""
    present = [path for path in (endpoint.address, endpoint.lock) if path.exists() or path.is_symlink()]
    if not present or places.folder_refusal(endpoint.lock.parent) is not None:
        return []  # nothing, or a folder another can change: none of it this user's daemon's to remove
    held = _lock(endpoint.lock)
    if held is None:
        return []  # a daemon holds it: starting, stopping or running
    removed: list[str] = []
    try:
        if _answering(endpoint.address):
            return []
        for path in present:
            if places.WINDOWS and path == endpoint.lock:
                continue  # an open file is not removed on Windows: after the lock is let go
            try:
                path.unlink()
                removed.append(str(path))
            except FileNotFoundError:
                pass
    finally:
        held.close()
    if places.WINDOWS and endpoint.lock in present:
        try:
            endpoint.lock.unlink()
            removed.append(str(endpoint.lock))
        except OSError:
            pass
    return removed
