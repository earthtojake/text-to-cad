"""Warm-process daemon supervisor for the CAD skill CLIs.

The supervisor owns a socket and a pool of warm workers (``cadgen.daemon.pool``),
each a subprocess that imported cadgen / OCP / build123d once. It services
directly-run @step/@dxf model scripts ("run") plus ``cadgen step build`` /
``cadgen stl|3mf|glb build`` / ``cadgen step inspect`` / ``cadgen snapshot``
invocations over a per-install unix socket (named pipe on Windows), so every
call skips the multi-second interpreter+OCP startup. The supervisor itself never
imports OCP: no amount of model badness can take it down.

Protocol — one JSON request per connection, JSON-lines response:

  request : {"tool": <a key of _TOOL_IMPORTS below>,
             "argv": [...], "cwd": "...", "prog": "...",
             "store_root": "...", "root_id": "..." | null,
             "env": {...}, "token": <client version token>}
  response: {"stream": "stdout"|"stderr", "data": "..."} chunks and
            {"event": {...}} build-tree events, then {"exit": <int>} — or
            {"restart": true} when the client's version token differs from the
            daemon's startup token, after which the daemon finishes the jobs it
            is running and exits so the client can respawn a fresh one.

Routing: a request that names a model script goes to THAT model's worker
(STORE.md §9). A busy worker means an extra, never a wait; a model with no
worker binds a spare; no spare means a spawn. Requests that name no script
borrow a spare for one job. Nothing here caps, counts memory or queues.
"""

from __future__ import annotations

import collections
import contextlib
import json
import os
import signal
import sys
import threading
import time
import traceback

from cadgen.daemon import transport
from cadgen.daemon.jobs import JobLedger, failure_message
from cadgen.daemon.client import (
    compute_version_token,
    daemon_address,
    daemon_identity,
)

DEFAULT_IDLE_TIMEOUT_SECONDS = 3600.0
REQUEST_READ_TIMEOUT_SECONDS = 30.0
CLIENT_LIVENESS_INTERVAL_SECONDS = 0.5
# A worker that produces NO frame for this long mid-job is treated as wedged. Generous:
# a large model can legitimately be silent for many minutes inside one OCCT boolean.
WORKER_SILENCE_TIMEOUT_SECONDS = 3600.0

# Parser modules are imported by the WORKERS, never by this process. They are ordinary
# cadgen modules, so a worker imports them from the same distribution this file was
# loaded from.
_TOOL_IMPORTS = {
    # "run" is the @step/@dxf decorator's warm-dispatch target (a directly
    # executed model script hands its argv here) — internal, not a user CLI.
    # DXF models are safe to serve warm because their bytes are a function of
    # the drawing's geometry, not of the process that wrote them.
    "run": "cadgen.cli._run_model",
    "step-build": "cadgen.cli.step_build",
    "step-compile": "cadgen.cli.step_compile",
    # One warm tool per mesh door. `step export` served all three formats from a
    # single spawn; three doors are three spawns, which is exactly the cost the
    # warm workers exist to remove.
    "stl-build": "cadgen.cli.stl_build",
    "3mf-build": "cadgen.cli.threemf_build",
    "glb-build": "cadgen.cli.glb_build",
    "inspect": "cadgen.cli.step_inspect.cli",
    "snapshot": "cadgen.cli.step_snapshot",
}

from cadgen.daemon import broker as broker_mod  # noqa: E402
from cadgen.daemon import pool as pool_mod  # noqa: E402 - after _TOOL_IMPORTS, which worker.py reads

_POOL = pool_mod.Pool()
# Daemon-wide job slots and the in-flight registry (STORE.md §9). Workers reach it
# over the daemon's own socket.
_BROKER = broker_mod.Broker()


class _DaemonShutdown(BaseException):
    """Raised from the SIGTERM/SIGINT handler. A BaseException subclass distinct
    from SystemExit so a signal arriving mid-request cannot be mistaken for the
    running tool's own exit and swallowed by the per-request catches."""


def _send(conn: transport.Channel, frame: dict) -> None:
    conn.send(json.dumps(frame, separators=(",", ":")).encode("utf-8"))


def _log(message: str) -> None:
    print(f"[cadgen-daemon] {message}", file=sys.__stderr__, flush=True)


def _idle_timeout() -> float:
    try:
        return max(1.0, float(os.environ.get("CADGEN_DAEMON_IDLE_TIMEOUT", "")))
    except ValueError:
        return DEFAULT_IDLE_TIMEOUT_SECONDS


def _evict_first_party_modules() -> None:
    # Warm-process hygiene, run by each WORKER after a job: generation already
    # evicts first-party modules PRE-run for deterministic closure capture; this
    # post-request pass keeps model modules from lingering between requests
    # (inspect/snapshot paths included).
    try:
        from cadgen._internal.source_hash import evict_first_party_modules
    except Exception:  # noqa: BLE001
        return
    with contextlib.suppress(Exception):
        evict_first_party_modules()


def _read_request(conn: transport.Channel) -> dict | None:
    """The client's single request frame, or None if it never arrived.

    A message boundary says "request over", which is what the old protocol needed a
    half-close for; there is no partial-read buffering left to do.
    """
    try:
        raw = conn.recv(REQUEST_READ_TIMEOUT_SECONDS)
    except (OSError, EOFError):
        return None
    if not raw:
        return None
    try:
        request = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    return request if isinstance(request, dict) else None


def _watch_client(
    conn: transport.Channel,
    send_lock: threading.Lock,
    done: threading.Event,
    tool: str,
    worker,
) -> None:
    """Kill the WORKER when the requesting client vanishes mid-job.

    A client sends one request frame and then only reads, so having nothing to read from
    it is the normal state rather than a symptom. The reliable death signal is a FAILED
    SEND: the channel raises as soon as the peer is gone. An empty stdout chunk is a no-op
    for every client, so it doubles as the liveness probe.

    Killing the one worker leaves the supervisor and every other job alone; the pool
    binds a fresh worker to that model on its next request.
    """
    while not done.wait(CLIENT_LIVENESS_INTERVAL_SECONDS):
        try:
            with send_lock:
                _send(conn, {"stream": "stdout", "data": ""})
        except OSError:
            if done.is_set():
                return
            _log(f"{tool}: client disconnected mid-request; killing worker {worker.pid}")
            worker.kill()
            return


def _status_payload() -> dict:
    """What the supervisor knows that nothing else can: which workers exist, which
    model each is bound to, and what it is doing. A socket file on disk proves none
    of it."""
    from cadgen import __version__

    snapshot = _POOL.snapshot()
    snapshot.update({
        "jobsRunning": _BROKER.snapshot(),
        # Every job, whoever asked: state, phase n/total and declared outputs
        # (cadgen.daemon.jobs). The CAD Viewer's progress feed.
        "jobs": _JOBS.snapshot(),
        "pid": os.getpid(),
        "socket": str(daemon_address()),
        "identity": daemon_identity(),
        "version": __version__,
        "token": compute_version_token(),
        "startedAt": _STARTED_AT,
        "requests": _REQUESTS_SERVED[0],
        "inflight": sum(1 for thread in list(_INFLIGHT) if thread.is_alive()),
    })
    return snapshot


def _script_path(candidates, base: object) -> str:
    """The model a request is about: the absolute path of the script it names.

    ROUTING LIVES HERE, not in the client: the protocol is unchanged, and a
    client cannot be trusted to answer "which model is this" consistently
    across the front doors that reach the daemon. The script is the only
    argument that names code the worker will EXECUTE, and a model's identity is
    its script path (STORE.md §Identity), so the worker is bound to exactly that.

    "" when no argument names a ``.py`` file: the request has no model subject
    and borrows a spare without binding it.
    """
    for candidate in candidates or ():
        text = str(candidate)
        if text.startswith("-") or not text.endswith(".py"):
            continue
        root = str(base or "")
        return os.path.realpath(os.path.join(root, text) if root else text)
    return ""


def _document_path(candidates, base: object) -> str:
    """The imported document a compile job names (``.step``/``.stp``), or "".

    A coalescing key only: a document binds no worker (the request borrows a
    spare), but two requests compiling the same bytes are one job."""
    for candidate in candidates or ():
        text = str(candidate)
        if text.startswith("-") or not text.lower().endswith((".step", ".stp")):
            continue
        root = str(base or "")
        return os.path.realpath(os.path.join(root, text) if root else text)
    return ""


def _handle_request(conn: transport.Channel, request: dict) -> None:
    """Relay one job to a warm worker and stream its frames back to the client."""
    send_lock = threading.Lock()
    started = time.perf_counter()

    if request.get("kind") in {"slot", "inflight"}:
        # A worker asking for a job slot or registering a job in flight. Blocks for the
        # lease's lifetime on this request thread.
        _BROKER.handle(conn, request)
        return

    tool = request.get("tool")
    argv = request.get("argv")

    if tool not in _TOOL_IMPORTS or not isinstance(argv, list):
        with send_lock:
            _send(conn, {"stream": "stderr", "data": f"cadgen-daemon: invalid request for tool {tool!r}\n"})
            _send(conn, {"exit": 1})
        return

    cwd = str(request.get("cwd") or "")
    model = _script_path(argv, cwd)
    # What in-flight coalescing keys on: the model, or for a compile job the imported
    # document (which binds no worker -- it borrows a spare -- but two compiles of one
    # file are still one job).
    subject = model or _document_path(argv, cwd)
    closure = str(request.get("closure") or "")
    job = _JOBS.adopt(_JOBS.start(tool=tool, subject=subject, argv=argv), subject=subject, tool=tool, argv=argv)
    inflight = None
    if subject and closure and request.get("coalesce"):
        inflight = _BROKER.claim(subject, closure)
        if inflight is not None:
            # Identical source is already building: attach, relay its exit, run nothing.
            _log(f"{tool} {model}: coalesced onto the job in flight")
            inflight["done"].wait()
            code = inflight["exit"] if inflight["exit"] is not None else 1
            _JOBS.finish(job, code)
            with contextlib.suppress(OSError), send_lock:
                _send(conn, {"exit": code})
            return
    try:
        worker = _POOL.acquire(model)
    except pool_mod.WorkerGone as exc:
        # A spawn that never announced itself. There is no worker to blame and nothing
        # to retry warm; the client sees the failure and can run cold.
        _log(f"{tool}: could not start a worker: {exc}")
        _JOBS.finish(job, 1)
        if subject and closure and request.get("coalesce"):
            _BROKER.finish(subject, closure, 1)
        with contextlib.suppress(OSError), send_lock:
            _send(conn, {"stream": "stderr", "data": f"cadgen-daemon: could not start a worker: {exc}\n"})
            _send(conn, {"exit": 1})
        return

    exit_code, healthy = 1, True
    # The tail of the job's stderr: on failure its last FAILED/exception line is the
    # reason the ledger records, so a reader (the CAD Viewer) can say why.
    stderr_tail: collections.deque[str] = collections.deque(maxlen=80)
    watchdog_done = threading.Event()
    watchdog = threading.Thread(
        target=_watch_client, args=(conn, send_lock, watchdog_done, tool, worker), daemon=True
    )
    watchdog.start()
    try:
        worker.send({
            "kind": "run",
            "tool": tool,
            "prog": request.get("prog"),
            "argv": [str(a) for a in argv],
            "cwd": request.get("cwd"),
            "env": request.get("env"),
            "store_root": request.get("store_root"),
            "root_id": request.get("root_id"),
        })
        for frame in worker.frames(silence_timeout=WORKER_SILENCE_TIMEOUT_SECONDS):
            if "exit" in frame:
                exit_code = int(frame.get("exit") or 0)
                break
            if frame.get("stream") == "stderr":
                stderr_tail.append(str(frame.get("data") or ""))
            _JOBS.observe(frame)
            with send_lock:
                _send(conn, frame)
    except pool_mod.WorkerGone as exc:
        # Its own frame, not a stderr chunk: the client owns the wording (it knows
        # how the user invoked it) and pins it by test; the supervisor supplies the
        # evidence. Note the log line too -- `cadgen daemon status` cannot show a
        # worker that is gone.
        healthy = False
        _log(f"{tool}: worker {worker.pid} died mid-job: {exc}")
        with contextlib.suppress(OSError), send_lock:
            _send(conn, {"workerDied": {"pid": worker.pid, "detail": str(exc),
                                        "exitStatus": exc.exit_status}})
    except OSError:
        # The CLIENT went away mid-job: a relay send failed before the watchdog's probe
        # did. Same answer as the watchdog's -- the orphaned job's worker is killed, never
        # released back to the pool mid-job (it would take the next request on a stdin
        # that is still inside this one).
        if worker.alive():
            _log(f"{tool}: client disconnected mid-request; killing worker {worker.pid}")
            worker.kill()
        healthy = False
    finally:
        watchdog_done.set()
        watchdog.join(timeout=CLIENT_LIVENESS_INTERVAL_SECONDS + 1.0)
        # A killed worker is not reusable; release() drops it and the pool respawns.
        _POOL.release(worker, healthy=healthy and worker.alive())
        reason = failure_message("".join(stderr_tail))[0] if exit_code != 0 else None
        _JOBS.finish(job, exit_code, error=reason or None)
        if subject and closure and request.get("coalesce"):
            _BROKER.finish(subject, closure, exit_code)

    _REQUESTS_SERVED[0] += 1
    _log(f"{tool} {argv!r} -> exit {exit_code} in {time.perf_counter() - started:.2f}s "
         f"(worker {worker.pid}{' extra' if worker.extra else ''})")
    with contextlib.suppress(OSError), send_lock:
        _send(conn, {"exit": exit_code})


_INFLIGHT: set[threading.Thread] = set()
_JOBS = JobLedger()
_STARTED_AT = time.time()
_REQUESTS_SERVED = [0]


def _serve_connection(conn, request) -> None:
    try:
        _handle_request(conn, request)
    except Exception:  # noqa: BLE001 - a job must never kill the supervisor
        _log("unhandled error serving a job:\n" + traceback.format_exc())
    finally:
        _INFLIGHT.discard(threading.current_thread())
        with contextlib.suppress(OSError):
            conn.close()


def _drain_inflight(reason: str) -> None:
    """Let the jobs already running finish before this process exits.

    A token mismatch means a NEW daemon is wanted, not that the builds in flight are
    wrong: they run the code they started with and their clients are waiting on them.
    """
    threads = [thread for thread in list(_INFLIGHT) if thread.is_alive()]
    if not threads:
        return
    _log(f"{reason}; finishing {len(threads)} job(s) in flight before exiting")
    for thread in threads:
        thread.join()


_DAEMON_LOCK: transport.SingletonLock | None = None


def _bind(address: str, authkey: bytes) -> transport.Server | None:
    """One daemon per identity, decided by a lock -- never by probing or sweeping.

    Probing a leftover socket was a race: twenty clients starting at once spawn twenty
    daemons, the losers' probes against a backlog-8 listener are REFUSED, each reads
    refusal as "stale file", unlinks the winner's live socket and binds its own -- four
    daemons "serving" one path, the earlier ones orphaned with their workers. So the
    decision is a process-lifetime exclusive lock (transport.SingletonLock, released by
    the kernel when the holder dies): the loser stands down at once, touching nothing;
    the winner is by construction the only daemon, so a socket file it finds is dead
    and may be removed before binding.
    """
    global _DAEMON_LOCK
    lock = transport.daemon_lock(address)
    if not lock.acquire():
        _log(f"another daemon holds the lock for {address}; standing down")
        return None
    _DAEMON_LOCK = lock  # held for the daemon's whole life
    if transport.address_is_stale(address):
        transport.clear_address(address)
    try:
        return transport.Server(address, authkey, backlog=128)
    except OSError as exc:
        _log(f"cannot bind {address}: {exc}")
        lock.release()
        _DAEMON_LOCK = None
        return None


def serve() -> int:
    os.environ["CADGEN_DAEMON_CHILD"] = "1"
    address = daemon_address()
    token = compute_version_token()
    authkey = transport.ensure_authkey(daemon_identity())
    server = _bind(address, authkey)
    if server is None:
        return 0
    bound = {"address": True}

    def _release_address() -> None:
        if bound["address"]:
            bound["address"] = False
            transport.clear_address(address)

    def _shutdown_handler(*_args) -> None:
        raise _DaemonShutdown

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, _shutdown_handler)
    idle_timeout = _idle_timeout()
    _log(f"pid {os.getpid()} serving {address} (token {token}, idle timeout {idle_timeout:.0f}s)")
    # The spares import build123d now, in the background, so the first requests find a
    # warm worker rather than paying the import on their own clock.
    _POOL.ensure_spares()

    # accept() cannot take a timeout the way a socket could, so idleness is watched from
    # the side: the watchdog closes the listener, which makes the pending accept return.
    # Closing is portable across both families and does not reach into Listener internals.
    state = {"last_activity": time.monotonic(), "idle_exit": False}

    def _watch_for_idle() -> None:
        slice_seconds = max(0.5, min(idle_timeout / 4, 5.0))
        while not server.closed:
            time.sleep(slice_seconds)
            if server.closed:
                return
            _POOL.unbind_idle()
            if any(thread.is_alive() for thread in list(_INFLIGHT)):
                state["last_activity"] = time.monotonic()  # a long build is not idleness
                continue
            if time.monotonic() - state["last_activity"] >= idle_timeout:
                state["idle_exit"] = True
                server.close()
                return

    threading.Thread(target=_watch_for_idle, daemon=True).start()

    try:
        while True:
            conn = server.accept()
            if conn is None:
                if state["idle_exit"]:
                    _log("idle timeout; exiting")
                return 0
            state["last_activity"] = time.monotonic()
            try:
                request = _read_request(conn)
                if request is None:
                    continue
                if request.get("kind") == "status":
                    # Answered BEFORE the token check: asking what is warm must never
                    # make the daemon exit, whichever cadgen the asker is running.
                    with contextlib.suppress(OSError):
                        _send(conn, {"status": _status_payload()})
                    continue
                if request.get("token") != token:
                    # Close and release the address BEFORE replying so the client's
                    # respawn cannot race this daemon's cleanup and lose the fresh
                    # daemon's address; then finish what is running.
                    server.close()
                    _release_address()
                    with contextlib.suppress(OSError):
                        _send(conn, {"restart": True})
                    conn.close()
                    conn = None
                    _drain_inflight("version token changed")
                    _log("version token changed; exiting")
                    return 0
                # One thread per job so a second client is served rather than queued.
                worker_thread = threading.Thread(
                    target=_serve_connection, args=(conn, request), daemon=True
                )
                _INFLIGHT.add(worker_thread)
                worker_thread.start()
                conn = None  # the thread owns it now
            except OSError:
                continue  # client vanished mid-request; keep serving
            finally:
                if conn is not None:
                    with contextlib.suppress(OSError):
                        conn.close()
            _POOL.reap_dead()
    except _DaemonShutdown:
        _log("signal received; exiting")
        return 0
    finally:
        _POOL.shutdown()
        server.close()
        _release_address()


USAGE = """\
cadgen-daemon takes no arguments.

It is the warm-process server, started for you by cadgen.daemon.client when
CADGEN_DAEMON=1 -- not a command to run by hand. It sits in scripts/ beside the
CLIs you probably meant: python <model>.py, cadgen step build, cadgen stl build,
cadgen step inspect, cadgen snapshot. Each of those takes --help.\
"""


def main(argv: list[str] | None = None) -> int:
    # Without this, ANY argument -- including a typo on a real daemon start --
    # fell through to serve() and bound the socket, so the caller got a resident
    # server for the full idle timeout instead of an answer.
    #
    # --help is the one argument that IS an answer. `daemon` is a registered
    # `cadgen` command, and every registered command answers --help on stdout
    # with 0 -- a help request that exits 2 reads as "this command is broken",
    # and it failed the installed-mode check, which walks the registry.
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"-h", "--help"}:
        print(USAGE)
        return 0
    if args:
        print(USAGE, file=sys.stderr)
        return 2
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
