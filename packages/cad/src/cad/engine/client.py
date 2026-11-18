"""Reaching the server: connect through its door (on Windows, its loopback port). Nothing here starts one but
``start`` (``cad server start``, ``cad mcp``): a client that finds none is told so in one line (``NotRunning``), and a
``cad`` command that finds one of another release is too (``OtherRelease``, ``RELEASE``). A start never replaces a
server of its own release or a newer one, whenever it finds it: it joins it (forward only)."""

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
# The release a process reaches a server of, or of a newer one (``cad mcp``, which joins a newer server).
AT_LEAST: str | None = None
# The exit status of a server that handed its start to cad's own update (``cad_server._internal.auto_update``): its
# starter waits for the server the update starts, never starts another.
UPDATING = 75


def newer(theirs: str | None, mine: str) -> bool:
    """Whether release ``theirs`` is later than ``mine``, each a plain ``X.Y.Z``; False for anything else."""
    import re

    found = [re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value or "") for value in (theirs, mine)]
    return all(found) and tuple(map(int, found[0].groups())) > tuple(map(int, found[1].groups()))


class NotRunning(ConnectionError):
    """No server answers: ``NOT_RUNNING``, which every command says as its failure (``not_running``)."""


class OtherRelease(ConnectionError):
    """A ``cad`` command's server is of another release (``RELEASE``): both said, and the two ways on."""


def _other(theirs: str | None, mine: str) -> str:
    """``OtherRelease``'s line: this release, the server's -- one of 0.11.11 or earlier names none -- and the ways on."""
    if theirs is None:
        return f"{COMMAND} here is {mine}; the running server is an earlier release's: run `{START}` to run {mine}'s server"
    if newer(theirs, mine):  # a start joins a newer server: installing is the one way on
        return f"{COMMAND} here is {mine}; the running server is {theirs}: install {COMMAND} {theirs}"
    return (f"{COMMAND} here is {mine}; the running server is {theirs}: install {COMMAND} {theirs}, or run `{START}` "
            f"to run {mine}'s server")


def _joined(release: str | None) -> str:
    """What a start says that found a server running and left it: this release's, or a newer one's."""
    if release == version():
        return f"the {COMMAND} server ({COMMAND} {version()}) is already running"
    return f"the {COMMAND} server ({COMMAND} {release}, newer than this {COMMAND} {version()}) is already running"


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
            return Connection(stream, stream, stream, connection, protocol=spoken, release=released(line),
                              token=token)
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
    """Whether this process may not listen on a loopback port, as the server it would start must: an agent app's
    shell sandbox with its network off refuses it (macOS Seatbelt the bind, Linux's seccomp the socket), and a server
    started there could never serve a build. Asked of the system, never read from a variable: an app that runs a
    command outside its sandbox, approved, may still hand it the sandbox's variables (one that says its network is
    off). A sandbox that forbids writing the engine's folder is found as its door or
    folder is (``_denied``). The port is bound and let go, as the daemon's own check does (``daemon._can_listen``)."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return True
    try:
        probe.bind(("127.0.0.1", 0))
    except OSError:
        return True
    finally:
        probe.close()
    return False


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


def _at_least(theirs: str | None, mine: str) -> bool:
    """Whether release ``theirs`` is ``mine`` or a newer one: a server a start of ``mine`` joins, never replaces."""
    return theirs == mine or newer(theirs, mine)


def make_way() -> str | None:
    """Room made for this release's server, as ``start`` makes it, and ``cad server start --foreground`` before it
    runs one in its own process: a server of an older release -- or one whose greeting names none, of 0.11.11 or
    earlier -- told to stop at once, its work cut short, and waited for, ``STOP_SECONDS`` at most (``sweep``). Where a
    server of this release or a newer one answers, nothing is done, and that is said in one line (returned); else None.
    So it is too where one answers by the time of the stop or while the older one goes -- a start at the same moment
    started it --: the stop is asked of the server it reaches only once that server's own greeting names an older
    release (``sweep``'s ``leave``), so no start stops a server of this release or a newer one, however the moments
    fall. ``ConnectionError`` in one line where room cannot be made: in a shell whose sandbox refuses the loopback port
    a server needs (``SANDBOXED``), before anything is stopped, and where the server told to stop did not go."""
    found = _connect()
    if found is not None:
        found.close()
        if _at_least(found.release, version()):
            return _joined(found.release)
    if _sandboxed():
        raise ConnectionError(SANDBOXED)
    if found is not None:
        sweep(stop=True, seconds=STOP_SECONDS, leave=version())
        found = _connect()
        if found is not None:
            found.close()
            if _at_least(found.release, version()):
                return _joined(found.release)
    return None


def start(port: int | None = None) -> str:
    """This release's server running: the one function that starts a server (``cad server start``, ``cad mcp``),
    once room is made for it (``make_way``) -- started (``_spawn``; ``port``, the HTTP port it must take) and waited
    for until its door answers. Starts at the same moment end with one server, by the daemon's lock, and none of them
    stops the server another of them started (``make_way``): each says it ran or joined it. A server that
    hands its start to cad's own update (``UPDATING``) is not started again: the update's server is waited for, and
    joined where it is newer. What was done, in one line. ``ConnectionError`` in one line where it could not be: room
    not made (``make_way``), a server that did not start (its note, ``places.failure_path``), and one of an older
    release that a start at the same moment started (``OtherRelease``)."""
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
    updating = False
    while (answered := _connect()) is None:
        if time.monotonic() > deadline:
            raise ConnectionError(f"the engine server did not start{': cad is updating' if updating else ''}")
        time.sleep(0.02)
        if updating:
            continue
        code = process.poll()
        updating = code == UPDATING
        if code and not updating:  # it could not take its lock or listen: said now, not after the timeout
            raise _not_started(code)
        if code == 0 and time.monotonic() - began > 1.0:
            # A daemon that is stopping still holds the lock, and the one just started left at once: started
            # again once the lock is free.
            process = _spawn(port)
            began = time.monotonic()
    answered.close()
    if newer(answered.release, version()):
        return _joined(answered.release)
    if answered.release != version():
        raise OtherRelease(_other(answered.release, version()))
    if _another_s(process):
        return _joined(version())
    return f"started the {COMMAND} server ({COMMAND} {version()})"


def _another_s(process: subprocess.Popen) -> bool:
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
    if AT_LEAST is not None and found.release != AT_LEAST and not newer(found.release, AT_LEAST):
        found.close()
        raise OtherRelease(_other(found.release, AT_LEAST))
    return found


def wait_gone(timeout: float = 60.0, endpoint: places.Endpoint | None = None, *, leave: str | None = None) -> bool:
    """Wait until the daemon, told to stop, is gone: its door no longer answers -- its port file,
    refused as it is removed, does not (``_connect``) -- and its lock, held until its workers have
    stopped, is free. With ``leave`` (``sweep``'s), a server of that release or a newer one answering in its place
    -- a start at the same moment started it, once the one told to stop had gone -- says it is gone too."""
    deadline = time.monotonic() + timeout
    lock = endpoint.lock if endpoint else places.lock_path()
    address = endpoint.address if endpoint else places.address()
    while time.monotonic() < deadline:
        if not _answering(address, stopping=True):
            if not lock.exists():
                return True  # it removed its lock as it let it go (``daemon.let_go``)
            held = _lock(lock)
            if held is not None:
                held.close()
                return True
        elif leave is not None and (found := _connect(address, stopping=True)) is not None:
            found.close()
            if _at_least(found.release, leave):
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
            message = {"token": connection.token, **message}
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
              on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    if places.WINDOWS:  # the token in the request too, which the daemon checks as it did the hello's: the hello's own,
        # never the port file read again, which a server stopping meanwhile has removed and one starting rewritten
        message = {"token": connection.token, **message}
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


def _note_pages(address: Path) -> None:
    """Where the server at ``address`` serves pages, noted before it is told to stop (``places.pages_path``), for the
    server that comes next to serve them there at once (``daemon.resumed``): a page open in a browser then reconnects
    by itself, whichever way its server was replaced -- cad's own update and the bridge's move (``cad server stop``,
    then ``cad server start``), a start that replaces an older server (``make_way``). Asked as no command
    (``internal``), of a server of any release (0.11.10's ``status`` says it too), ``PAGES_SECONDS`` at most; nothing
    noted where it serves no pages or does not say, and nothing here ever fails the stop."""
    try:
        connection = _connect(address)
        if connection is None:
            return
        answer = _within(PAGES_SECONDS, lambda: _exchange(connection, {"op": "status", "internal": True}))
        serving = answer.get("serving") if isinstance(answer, dict) else None
        port = serving.get("port") if isinstance(serving, dict) else None
        if type(port) is not int or not 0 < port < 65536:
            return
        from cad.engine.atomic_replace import replace_atomic

        path = places.pages_path()
        temporary = path.with_suffix(".pages-tmp")
        temporary.write_text(json.dumps({"port": port}), encoding="utf-8")
        replace_atomic(temporary, path)
    except (ConnectionError, OSError, ValueError):
        pass


# How long a stop waits to hear where the server serves pages (``_note_pages``).
PAGES_SECONDS = 5.0


def sweep(*, stop: bool, seconds: float = 60.0, leave: str | None = None) -> dict[str, list[str]]:
    """The engine of this engine folder (``places.endpoints``): with ``stop``, stopped if it lives and
    waited for until gone, ``seconds`` at most (``stopped``, its door or port file), the port it served pages on
    noted first for the next server (``_note_pages``); a live one left running listed in ``running``. The door and
    lock files of a dead one -- nothing answers there and nobody holds its lock -- are removed (``removed``). A
    daemon starting or stopping holds its lock before it listens and until it has left, so its files are never
    taken. ``leave``: a release whose servers, and a newer one's, are left running, never told to stop (``make_way``,
    this release): read from the greeting of the very connection the stop would go by, and a server of it answering
    while the one told to stop goes is that one gone (``wait_gone``)."""
    found: dict[str, list[str]] = {"stopped": [], "running": [], "removed": []}
    for endpoint in places.endpoints():
        if _answering(endpoint.address):
            if not stop:
                found["running"].append(str(endpoint.address))
                continue
            _note_pages(endpoint.address)
            connection = _connect(endpoint.address)
            if connection is None:
                continue  # it went meanwhile: gone, as asked
            if leave is not None and _at_least(connection.release, leave):
                connection.close()  # one to join, not the one to replace: a start at the same moment started it
                found["running"].append(str(endpoint.address))
                continue
            try:
                _exchange(connection, {"op": "stop"})
            except ConnectionError:
                pass  # it closed the connection unanswered: stopping already (another start told it), as asked
            if not wait_gone(seconds, endpoint=endpoint, leave=leave):
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
