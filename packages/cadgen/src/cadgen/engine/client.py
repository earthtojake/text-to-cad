"""Reaching the daemon: connect to its socket, starting it first when none answers."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from cadgen.engine import daemon as _daemon

__all__ = ["request", "sweep"]

DAEMON_MODULE = "cadgen.engine.daemon"  # the enclosing distribution may supply an application host


def _connect(address: Path | None = None) -> socket.socket | None:
    """A connection to the daemon at ``address`` (its socket, on Windows its port file; by default
    this protocol's), or None when none answers there."""
    try:
        if _daemon.WINDOWS:
            port, _token = (address or _daemon.port_path()).read_text(encoding="utf-8").split()
            return socket.create_connection(("127.0.0.1", int(port)), timeout=5)
        path = address or _daemon.socket_path()
        if not path.exists() or not _daemon.socket_folder_ok(path):
            return None
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            client.connect(str(path))
        except OSError:
            client.close()  # a failed connect leaves no socket open
            raise
        return client
    except (OSError, ValueError):
        return None


# Switches that govern only the process they are set in -- ``DO_NOT_TRACK`` and
# ``CADGEN_TELEMETRY`` (the distribution's ``cadgen.analytics.ENVIRONMENT``). The daemon serves
# every later client, so it is one of the "processes started for others" that go by the
# person's saved choice, never by the switch of whichever client happened to start it. The
# engine imports nothing of cadgen (law 3), so it carries the names here rather than importing them.
_PER_PROCESS_TELEMETRY = ("DO_NOT_TRACK", "CADGEN_TELEMETRY")


def _start() -> None:
    env = {name: value for name, value in os.environ.items() if name not in _PER_PROCESS_TELEMETRY}
    root = _daemon.engine_root()
    path = env.get("PYTHONPATH", "")
    if root not in path.split(os.pathsep):
        env["PYTHONPATH"] = os.pathsep.join(item for item in (root, path) if item)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.Popen([sys.executable, "-P", "-m", DAEMON_MODULE], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=_working_folder(),
                     **_daemon.detached())


def _working_folder() -> str | None:
    """Where the daemon (and every child it starts) stands. On POSIX the engine's own folder, which
    is this user's alone (``daemon.folder_refusal``): never the shared temporary folder above it,
    where another user could leave a file a name-resolved helper would find. On Windows the
    per-user temporary folder above it, so the engine's folder holds no process's working folder."""
    folder = _daemon.state_dir()
    if not _daemon.WINDOWS:
        return str(folder) if folder.is_dir() else None
    return str(folder.parent) if folder.parent.exists() else None


def connect(*, start: bool = True, timeout: float = 60.0) -> socket.socket | None:
    """A connection to the daemon, started when ``start`` and none answers."""
    found = _connect()
    if found is not None or not start:
        return found
    _daemon.state_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    refusal = _daemon.folder_refusal(_daemon.state_dir())
    if refusal is not None:  # said now, not after waiting out a daemon that cannot start there
        raise ConnectionError(refusal)
    _start()
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        found = _connect()
        if found is not None:
            return found
        time.sleep(0.05)
        if time.monotonic() - started > 1.0:
            # A daemon that is stopping still holds the lock, and the one just started
            # left at once: start another once the lock is free.
            _start()
            started = time.monotonic()
    raise ConnectionError("the engine server did not start")


def wait_gone(timeout: float = 60.0, endpoint: _daemon.Endpoint | None = None) -> bool:
    """Wait until the daemon (by default this protocol's) is gone: its socket no longer connects
    and its lock, held until its workers have stopped, is free."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = _connect(endpoint.address if endpoint else None)
        if found is None:
            held = _daemon.lock(endpoint.lock if endpoint else None)
            if held is not None:
                held.close()
                return True
        else:
            found.close()
        time.sleep(0.05)
    return False


def request(message: dict[str, Any], on_log: Callable[[dict[str, Any]], None] = lambda _m: None, *,
            start: bool = True, on_progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any] | None:
    """Send one request; every log line to ``on_log`` and every progress frame of its build to
    ``on_progress`` (``progress.py``); the final answer returned (None when no daemon is up and
    ``start`` is false)."""
    connection = connect(start=start)
    if connection is None:
        return None
    return _exchange(connection, message, on_log, on_progress)


def _exchange(connection: socket.socket, message: dict[str, Any], on_log: Callable[[dict[str, Any]], None] = lambda _m: None,
              on_progress: Callable[[dict[str, Any]], None] | None = None, address: Path | None = None) -> dict[str, Any]:
    if _daemon.WINDOWS:
        # The token first, so the daemon checks it in the line's first bytes, before it reads the rest.
        message = {"token": (address or _daemon.port_path()).read_text(encoding="utf-8").split()[1], **message}
    with connection:
        connection.settimeout(None)
        stream = connection.makefile("rwb")
        stream.write((json.dumps(message) + "\n").encode())
        stream.flush()
        for line in stream:
            answer = json.loads(line)
            if "log" in answer:
                on_log(answer)
                continue
            if set(answer) == {"progress"}:
                if on_progress is not None:
                    on_progress(answer["progress"])
                continue
            return answer
    raise ConnectionError("the engine server closed the connection")


def sweep(*, stop: bool) -> dict[str, list[str]]:
    """Every daemon of this installation, whatever protocol it speaks (``daemon.endpoints``): with
    ``stop``, each live one stopped and waited for until gone (``stopped``, its socket or port file);
    a live one left running listed in ``running``. The socket and lock files of a dead one -- nothing
    answers there and nobody holds its lock -- are removed (``removed``). A daemon starting or
    stopping holds its lock before it listens and until it has left, so its files are never taken."""
    found: dict[str, list[str]] = {"stopped": [], "running": [], "removed": []}
    for endpoint in _daemon.endpoints():
        connection = _connect(endpoint.address)
        if connection is not None:
            if not stop:
                connection.close()
                found["running"].append(str(endpoint.address))
                continue
            _exchange(connection, {"op": "stop"}, address=endpoint.address)
            if not wait_gone(endpoint=endpoint):
                raise ConnectionError(f"the engine server at {endpoint.address} did not exit")
            found["stopped"].append(str(endpoint.address))
            _remove_dead(endpoint)  # the lock file a stopped daemon leaves is part of its stop, not stale
            continue
        found["removed"] += _remove_dead(endpoint)
    return found


def _remove_dead(endpoint: _daemon.Endpoint) -> list[str]:
    """The files of ``endpoint`` removed when its daemon is dead: its lock free (taken here while
    they go, so no daemon starts between) and nothing answering at its address."""
    present = [path for path in (endpoint.address, endpoint.lock) if path.exists() or path.is_symlink()]
    if not present or _daemon.folder_refusal(endpoint.lock.parent) is not None:
        return []  # nothing, or a folder another can change: none of it this user's daemon's to remove
    held = _daemon.lock(endpoint.lock)
    if held is None:
        return []  # a daemon holds it: starting, stopping or running
    removed: list[str] = []
    try:
        answering = _connect(endpoint.address)
        if answering is not None:
            answering.close()
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
