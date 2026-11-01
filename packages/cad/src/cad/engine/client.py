"""Reaching the daemon: connect through its door (on Windows, its loopback port), starting it first
when none answers."""

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
from cad.engine.door import DOOR_PROTOCOL, GREETING_SECONDS, HELLO_LIMIT, Connection, answering, dial, greeted, hello

__all__ = ["hold", "request", "sweep"]

# The module the server runs its engine as: the daemon with its application host installed. Named, never
# imported: a client in the CAD kernel environment has only the library, and starts the engine with the
# Python of an installation that has the server (``_start``).
DAEMON_MODULE = "cad_server._internal.engine_daemon"
# Called once a connection reaches a daemon this process started (``connect``): a command that
# starts the engine says so (``cli.answered``); None, the default, says nothing.
on_started: Callable[[], None] | None = None

# The sandboxes known to refuse the loopback port the engine's HTTP server needs, each by a variable
# and the value it sets in the shells it runs: a daemon started there could never serve a build (an agent
# app's shell sandbox, in its default mode, with its network disabled). A sandbox none names is found by the
# daemon that cannot listen (``places.failure_path``), as fast.
SANDBOXES: tuple[tuple[str, str], ...] = (("CODEX_SANDBOX_NETWORK_DISABLED", "1"),)
# The words a worker's failure carries its stderr's tail under (``supervisor.Process``): local detail, which
# no observer's facts carry (``api._error``), even when a startup failure or a broken pipe has no exit
# status to tell it from a Python traceback.
WORKER_STDERR = "\nWorker stderr (last 16384 characters):\n"
SANDBOXED = ("no engine server is running, and this shell's sandbox cannot start one: open a CAD card "
             "(the CAD plugin's server starts the engine) or run `cad server` outside the sandbox")


def _connect(address: Path | None = None) -> Connection | None:
    """A connection to the daemon at ``address`` (its door, on Windows its port file; by default
    the engine's), or None when none answers there or it greets in a protocol this side does not
    speak. ``ConnectionError`` when the system refuses this process the engine's folder (a sandbox
    that forbids writing there)."""
    try:
        if places.WINDOWS:
            port, token = _port_text(address or places.port_path()).split()
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
        door = address or places.door_path()
        if places.folder_refusal(door.parent) is not None or not door.exists():
            return None
        return dial(door)
    except PermissionError as error:
        raise _denied(f"opening a pipe in the engine's folder {places.engine_dir()}: {error.strerror or error}") from None
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
    if not places.WINDOWS:
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
    return ConnectionError(f"the system denies text-to-cad's local engine ({cause}); a sandbox that forbids "
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


def _start() -> subprocess.Popen:
    """A daemon started, detached: its process, whose ``pid`` says whether the daemon that answers
    is the one this process started (``_told_started``). It is the current installation's engine
    (``places.engine``, read now), started with that installation's Python whatever release this client
    is -- a client of another release is handed nothing of its own import path --; with none current,
    the installation's own: this process's, or, in the base the installation made (``places.HOME``),
    the installation's, the engine's folder first on its ``PYTHONPATH`` only where that Python's
    environment would not find it -- a source tree --, so no process the daemon starts in the base
    inherits it."""
    env = {name: value for name, value in environment().items() if name not in _PER_PROCESS_TELEMETRY}
    found = places.engine()
    home = places.HOME
    if found is not None:
        python = found["python"]
        if not _same(found["prefix"], home["prefix"] if home else sys.prefix):
            env.pop("PYTHONPATH", None)  # the current installation's engine imports its own cadgen
    else:
        python, root, prefix = ((home["executable"], home["root"], home["prefix"]) if home
                                else (sys.executable, places.engine_root(), sys.prefix))
        path = env.get("PYTHONPATH", "")
        inside = os.path.normcase(os.path.realpath(prefix)).rstrip(os.sep) + os.sep
        if not os.path.normcase(os.path.realpath(root)).startswith(inside) and root not in path.split(os.pathsep):
            env["PYTHONPATH"] = os.pathsep.join(item for item in (root, path) if item)
    places.bytecode(env)
    return subprocess.Popen([python, "-P", "-m", DAEMON_MODULE], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=_working_folder(),
                            **places.detached())


def _same(one: str, other: str) -> bool:
    return os.path.normcase(os.path.realpath(one)) == os.path.normcase(os.path.realpath(other))


def _working_folder() -> str | None:
    """Where the daemon (and every child it starts) stands. On POSIX the engine's own folder, which
    is this user's alone (``places.folder_refusal``): never the shared temporary folder above it,
    where another user could leave a file a name-resolved helper would find. On Windows the
    per-user temporary folder above it, so the engine's folder holds no process's working folder."""
    folder = places.engine_dir()
    if not places.WINDOWS:
        return str(folder) if folder.is_dir() else None
    return str(folder.parent) if folder.parent.exists() else None


def connect(*, start: bool = True, timeout: float = 60.0) -> Connection | None:
    """A connection to the daemon, started when ``start`` and none answers. In a shell whose
    sandbox refuses the loopback port the engine's HTTP server needs, none is started: that is
    said at once, as is a daemon that exits failing (its note, ``places.failure_path``)."""
    found = _connect()
    if found is not None or not start:
        return found
    if _sandboxed():
        raise ConnectionError(SANDBOXED)
    try:
        places.engine_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    except PermissionError as error:
        raise _denied(f"making the engine's folder: {error.strerror or error}") from None
    refusal = places.folder_refusal(places.engine_dir())
    if refusal is not None:  # said now, not after waiting out a daemon that cannot start there
        raise ConnectionError(refusal)
    try:  # the note is the one this start leaves
        places.failure_path().unlink(missing_ok=True)
    except PermissionError as error:
        raise _denied(f"writing in the engine's folder: {error.strerror or error}") from None
    process = _start()
    mine = [process]
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        found = _connect()
        if found is not None:
            _told_started(mine)
            return found
        time.sleep(0.02)
        if process.poll():  # it could not take its lock or listen: said now, not after the timeout
            raise _not_started(process.returncode)
        if time.monotonic() - started > 1.0 and process.poll() == 0:
            # A daemon that is stopping still holds the lock, and the one just started
            # left at once: start another once the lock is free.
            process = _start()
            mine.append(process)
            started = time.monotonic()
    raise ConnectionError("the engine server did not start")


def _told_started(mine: list[subprocess.Popen]) -> None:
    """``on_started``, when the daemon that answers is one of ``mine`` (the daemons this process
    started): a command racing this one may have started the one that won the lock."""
    if on_started is None:
        return
    connection = _connect()
    try:
        answer = _exchange(connection, {"op": "pid"}) if connection is not None else {}
    except (OSError, ValueError):
        return
    if answer.get("pid") in {process.pid for process in mine}:
        on_started()


def wait_gone(timeout: float = 60.0, endpoint: places.Endpoint | None = None) -> bool:
    """Wait until the daemon is gone: its door no longer answers and its lock, held until its workers
    have stopped, is free."""
    deadline = time.monotonic() + timeout
    lock = endpoint.lock if endpoint else places.lock_path()
    while time.monotonic() < deadline:
        if not _answering(endpoint.address if endpoint else places.address()):
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
    """A hold on the engine (``Daemon.hold``), started when ``start`` and none runs: while the
    connection returned stays open, the engine does not stop for idleness. Reading it waits until
    the engine goes (its end of file). None when none runs and ``start`` is false. ``host()``, asked
    once the engine answers, names the agent host the holder serves (its ``status`` counts it);
    ``holder``, the name its MCP sessions are opened under, which end when the hold does."""
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
            start: bool = True, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any] | None:
    """Send one request; every log line to ``on_log`` and every progress frame of its build to
    ``on_progress`` (``progress.py``); the final answer returned (None when no daemon is up and
    ``start`` is false)."""
    connection = connect(start=start)
    if connection is None:
        return None
    return _exchange(connection, message, on_log, on_progress)


def _exchange(connection: Connection, message: dict[str, Any], on_log: Callable[[dict[str, Any]], None] = lambda _m: None,
              on_progress: Callable[[dict[str, Any]], None] | None = None, address: Path | None = None) -> dict[str, Any]:
    if places.WINDOWS:  # the token in the request too, which the daemon checks as it did the hello's
        message = {"token": (address or places.port_path()).read_text(encoding="utf-8").split()[1], **message}
    with connection:
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
            # The request that bound the engine's port, when that start retired an older engine or
            # moved the port (``daemon.bind``): a line each.
            for said in (notice or "").splitlines():
                print(f"cad: {said}", file=sys.stderr)
            return answer
    raise ConnectionError("the engine server closed the connection")


def sweep(*, stop: bool) -> dict[str, list[str]]:
    """The engine of this engine folder (``places.endpoints``): with ``stop``, stopped if it lives and
    waited for until gone (``stopped``, its door or port file); a live one left running listed in
    ``running``. The door and lock files of a dead one -- nothing answers there and nobody holds its
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
            if not wait_gone(endpoint=endpoint):
                raise ConnectionError(f"the engine server at {endpoint.address} did not exit")
            found["stopped"].append(str(endpoint.address))
            _remove_dead(endpoint)  # what an engine from before engines removed their own files left: its stop's
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
