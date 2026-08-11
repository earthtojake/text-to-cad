"""Warm-process daemon server for the CAD skill CLIs.

One long-lived process imports cadgen / OCP / build123d ONCE and then services
``scripts/gen`` / ``scripts/export`` / ``scripts/artifact`` / ``scripts/inspect``
/ ``scripts/snapshot`` invocations over a per-worktree unix socket, so opted-in
sessions (``CADGEN_WARM=1``) skip the multi-second interpreter+OCP startup on
every call. The daemon runs with ``CADGEN_DAEMON_CHILD=1`` so the launcher shim
never recurses into it.

Protocol — one JSON request per connection, JSON-lines response:

  request : {"tool": "gen"|"export"|"artifact"|"inspect"|"snapshot",
             "argv": [...], "cwd": "...",
             "token": <client version token>}
  response: {"stream": "stdout"|"stderr", "data": "..."} chunks, then
            {"exit": <int>} — or {"restart": true} when the client's version
            token differs from the daemon's startup token, after which the
            daemon exits so the client can respawn a fresh one.

Requests are handled strictly sequentially: OCP is single-threaded, and the cold
per-invocation CLIs this replaces were serialized anyway. Warm-process
determinism rides on cadgen's pre-run first-party module eviction (see
``cadgen._internal.generation.run_script_generator``); the daemon additionally
drops first-party modules after each request so model code never lingers
between requests. Python-level stdout/stderr are streamed to the client;
C-level OCP prints and daemon lifecycle logs land in the log file next to the
socket.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import signal
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

if __package__ in {None, ""}:
    daemon_dir = Path(__file__).resolve().parent
    if str(daemon_dir) not in sys.path:
        sys.path.insert(0, str(daemon_dir))
    from client import compute_version_token, socket_path
else:
    from .client import compute_version_token, socket_path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
PACKAGES_DIR = SCRIPTS_DIR / "packages"
CADPY_SRC_DIR = PACKAGES_DIR / "cadgen" / "src"
INSPECT_DIR = SCRIPTS_DIR / "inspect"
# Mirror the launchers' lookup paths (snapshot/__main__.py inserts the first
# three; the inspect tool dir hosts the inspect_refs package).
for runtime_path in (SCRIPTS_DIR, PACKAGES_DIR, INSPECT_DIR, CADPY_SRC_DIR):
    runtime_path_text = str(runtime_path)
    if runtime_path_text not in sys.path:
        sys.path.insert(0, runtime_path_text)

DEFAULT_IDLE_TIMEOUT_SECONDS = 600.0
REQUEST_READ_TIMEOUT_SECONDS = 30.0
CLIENT_LIVENESS_INTERVAL_SECONDS = 0.5

# Tool cli modules are imported directly (not the launcher __main__ files) so
# the daemon skips the launchers' CADGEN_WARM shim and their name-colliding
# top-level `cli` modules.
_TOOL_IMPORTS = {
    "gen": "gen.cli",
    "export": "export.cli",
    "artifact": "artifact.cli",
    "inspect": "inspect_refs.cli",
    "snapshot": "snapshot.__main__",
}
_TOOL_MAINS: dict[str, object] = {}


class _DaemonShutdown(BaseException):
    """Raised from the SIGTERM/SIGINT handler. A BaseException subclass distinct
    from SystemExit so a signal arriving mid-request cannot be mistaken for the
    running tool's own exit and swallowed by the per-request catches."""


class _StreamProxy(io.TextIOBase):
    """``sys.stdout``/``sys.stderr`` stand-in whose destination swaps per request.

    Installed BEFORE the tool modules are imported so def-time default bindings
    (e.g. snapshot's ``run_render_cli(stdout=sys.stdout, ...)``) capture the
    proxy and keep routing to the current request's client stream instead of
    the daemon log."""

    def __init__(self, fallback) -> None:
        self._fallback = fallback
        self._target = fallback

    def set_target(self, target) -> None:
        self._target = target

    def reset(self) -> None:
        self._target = self._fallback

    @property
    def encoding(self) -> str:  # TextIOBase declares encoding read-only
        return getattr(self._target, "encoding", None) or "utf-8"

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:
        return self._target.write(data)

    def flush(self) -> None:
        flush = getattr(self._target, "flush", None)
        if callable(flush):
            flush()

    def isatty(self) -> bool:
        return False


class _ChunkWriter:
    """File-like sink that forwards writes to the client as protocol frames.

    Shares ``send_lock`` with the liveness watchdog so job output and probe
    frames cannot interleave bytes on the socket."""

    def __init__(self, conn: socket.socket, stream: str, send_lock: threading.Lock) -> None:
        self._conn = conn
        self._stream = stream
        self._send_lock = send_lock

    def write(self, data) -> int:
        text = data if isinstance(data, str) else str(data)
        if text:
            with self._send_lock:
                _send(self._conn, {"stream": self._stream, "data": text})
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def _send(conn: socket.socket, frame: dict) -> None:
    conn.sendall(json.dumps(frame, separators=(",", ":")).encode("utf-8") + b"\n")


def _log(message: str) -> None:
    print(f"[cadgen-daemon] {message}", file=sys.__stderr__, flush=True)


def _idle_timeout() -> float:
    try:
        return max(1.0, float(os.environ.get("CADGEN_DAEMON_IDLE_TIMEOUT", "")))
    except ValueError:
        return DEFAULT_IDLE_TIMEOUT_SECONDS


def _tool_main(tool: str):
    main = _TOOL_MAINS.get(tool)
    if main is None:
        main = getattr(importlib.import_module(_TOOL_IMPORTS[tool]), "main")
        _TOOL_MAINS[tool] = main
    return main


def _warm_imports() -> None:
    """Pay the heavy import cost before the socket exists — the client treats
    socket presence as readiness."""
    importlib.import_module("cadgen.generation")
    for tool in _TOOL_IMPORTS:
        try:
            _tool_main(tool)
        except Exception:  # noqa: BLE001 — surfaces per-request instead
            _log(f"warm import failed for {tool}:\n{traceback.format_exc()}")


def _evict_first_party_modules() -> None:
    # Same warm-process hygiene the viewer worker relies on: generation already
    # evicts first-party modules PRE-run for deterministic closure capture; this
    # post-request pass keeps model modules from lingering in the daemon between
    # requests (inspect/snapshot paths included).
    try:
        from cadgen._internal.source_hash import evict_first_party_modules
    except Exception:  # noqa: BLE001
        return
    with contextlib.suppress(Exception):
        evict_first_party_modules()


def _read_request(conn: socket.socket) -> dict | None:
    conn.settimeout(REQUEST_READ_TIMEOUT_SECONDS)
    chunks: list[bytes] = []
    try:
        while b"\n" not in (chunks[-1] if chunks else b""):
            data = conn.recv(65536)
            if not data:
                break
            chunks.append(data)
    except OSError:
        return None
    finally:
        conn.settimeout(None)
    raw = b"".join(chunks).split(b"\n", 1)[0].strip()
    if not raw:
        return None
    try:
        request = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    return request if isinstance(request, dict) else None


def _exit_code(exc: SystemExit, err: _ChunkWriter) -> int:
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    err.write(f"{code}\n")
    return 1


def _watch_client(
    conn: socket.socket,
    send_lock: threading.Lock,
    done: threading.Event,
    tool: str,
) -> None:
    """Abort the daemon when the requesting client vanishes mid-job.

    Clients half-close their write side right after the request, so read-side
    EOF is normal and the only reliable death signal is a FAILED SEND (AF_UNIX
    raises immediately once the peer socket is gone). An empty stdout chunk is
    a no-op for every client, so it doubles as the liveness probe. Requests
    are strictly sequential, so the only in-flight work belongs to the dead
    requester: exiting hard is correct — the killed client's job stops burning
    CPU, and the next invocation transparently respawns a fresh daemon (the
    client already treats a missing/refused socket that way) instead of
    queueing silently behind an orphaned build."""
    while not done.wait(CLIENT_LIVENESS_INTERVAL_SECONDS):
        try:
            with send_lock:
                _send(conn, {"stream": "stdout", "data": ""})
        except OSError:
            if done.is_set():
                return
            _log(f"{tool}: client disconnected mid-request; aborting orphaned job "
                 "(next call spawns a fresh daemon)")
            with contextlib.suppress(OSError):
                os.unlink(socket_path())
            os._exit(0)


def _handle_request(
    conn: socket.socket,
    request: dict,
    stdout_proxy: _StreamProxy,
    stderr_proxy: _StreamProxy,
) -> None:
    tool = request.get("tool")
    argv = request.get("argv")
    cwd = request.get("cwd")
    send_lock = threading.Lock()
    out = _ChunkWriter(conn, "stdout", send_lock)
    err = _ChunkWriter(conn, "stderr", send_lock)
    previous_cwd = os.getcwd()
    previous_argv = sys.argv
    stdout_proxy.set_target(out)
    stderr_proxy.set_target(err)
    exit_code = 1
    started = time.perf_counter()
    watchdog_done = threading.Event()
    watchdog: threading.Thread | None = None
    try:
        if tool not in _TOOL_IMPORTS or not isinstance(argv, list):
            err.write(f"cadgen-daemon: invalid request for tool {tool!r}\n")
        else:
            if isinstance(cwd, str) and os.path.isdir(cwd):
                os.chdir(cwd)
            argv = [str(arg) for arg in argv]
            sys.argv = [f"scripts/{tool}", *argv]
            watchdog = threading.Thread(
                target=_watch_client,
                args=(conn, send_lock, watchdog_done, str(tool)),
                daemon=True,
            )
            watchdog.start()
            try:
                result = _tool_main(tool)(argv)
                exit_code = 0 if result is None else int(result)
            except _DaemonShutdown:
                raise
            except SystemExit as exc:
                exit_code = _exit_code(exc, err)
            except BaseException:  # noqa: BLE001 — a failed build must not kill the daemon
                err.write(traceback.format_exc())
    finally:
        watchdog_done.set()
        if watchdog is not None:
            watchdog.join(timeout=CLIENT_LIVENESS_INTERVAL_SECONDS + 1.0)
        stdout_proxy.reset()
        stderr_proxy.reset()
        sys.argv = previous_argv
        with contextlib.suppress(OSError):
            os.chdir(previous_cwd)
        _evict_first_party_modules()
    _log(f"{tool} {argv!r} -> exit {exit_code} in {time.perf_counter() - started:.2f}s")
    with send_lock:
        _send(conn, {"exit": exit_code})


def serve() -> int:
    os.environ["CADGEN_DAEMON_CHILD"] = "1"
    sock_path = socket_path()
    token = compute_version_token()
    stdout_proxy = _StreamProxy(sys.stdout)
    stderr_proxy = _StreamProxy(sys.stderr)
    sys.stdout = stdout_proxy
    sys.stderr = stderr_proxy
    _warm_imports()
    with contextlib.suppress(FileNotFoundError):
        os.unlink(sock_path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(sock_path))
    except OSError as exc:
        _log(f"cannot bind {sock_path}: {exc}")
        return 1
    server.listen(8)

    def _shutdown_handler(*_args) -> None:
        raise _DaemonShutdown

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, _shutdown_handler)
    idle_timeout = _idle_timeout()
    _log(f"pid {os.getpid()} serving {sock_path} (token {token}, idle timeout {idle_timeout:.0f}s)")
    try:
        while True:
            server.settimeout(idle_timeout)
            try:
                conn, _ = server.accept()
            except TimeoutError:
                _log("idle timeout; exiting")
                return 0
            try:
                request = _read_request(conn)
                if request is None:
                    continue
                if request.get("token") != token:
                    # Unlink BEFORE replying so the client's respawn cannot race
                    # this daemon's cleanup and lose the fresh daemon's socket.
                    server.close()
                    with contextlib.suppress(OSError):
                        os.unlink(sock_path)
                    with contextlib.suppress(OSError):
                        _send(conn, {"restart": True})
                    _log("version token changed; restarting")
                    return 0
                _handle_request(conn, request, stdout_proxy, stderr_proxy)
            except OSError:
                continue  # client vanished mid-request; keep serving
            finally:
                with contextlib.suppress(OSError):
                    conn.close()
    except _DaemonShutdown:
        _log("signal received; exiting")
        return 0
    finally:
        with contextlib.suppress(OSError):
            server.close()
        with contextlib.suppress(OSError):
            os.unlink(sock_path)


USAGE = """\
cadgen-daemon takes no arguments.

It is the warm-process server, started for you by cadgen_daemon.client when
CADGEN_WARM=1 -- not a command to run by hand. It sits in scripts/ beside the
CLIs you probably meant: scripts/gen, scripts/export, scripts/inspect,
scripts/artifact, scripts/snapshot. Each of those takes --help.\
"""


def main(argv: list[str] | None = None) -> int:
    # Without this, ANY argument -- including --help, and including a typo on a real daemon
    # start -- fell through to serve() and bound the socket, so the caller got a resident
    # server for the full idle timeout instead of an answer.
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print(USAGE, file=sys.stderr)
        return 2
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
