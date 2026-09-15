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
# Read-only waiters are independent of build admission and cannot block accept().
# Saturation returns an immediate ledger snapshot, never starts more threads.
_JOB_WATCH_SLOTS = threading.BoundedSemaphore(32)
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
}

from cadgen.daemon import broker as broker_mod  # noqa: E402
from cadgen.daemon import pool as pool_mod  # noqa: E402 - after _TOOL_IMPORTS, which worker.py reads

# Daemon-wide job slots and the in-flight registry (STORE.md §9). Workers reach it
# over the daemon's own socket.
_BROKER = broker_mod.Broker()
# Admission waits on the jobs holding those slots rather than refusing a spawn.
_POOL = pool_mod.Pool(in_flight=lambda: _BROKER.snapshot()["running"])


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
    preserve_work=None,
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
            if preserve_work is not None and preserve_work():
                _log(f"{tool}: producer disconnected; continuing for coalesced consumers")
                while not done.wait(CLIENT_LIVENESS_INTERVAL_SECONDS):
                    if not preserve_work():
                        _log(f"{tool}: last coalesced consumer disconnected; killing worker {worker.pid}")
                        worker.kill()
                        return
                return
            _log(f"{tool}: client disconnected mid-request; killing worker {worker.pid}")
            worker.kill()
            return


def _wait_for_inflight_consumer(conn: transport.Channel, entry: dict) -> int | None:
    """Wait for canonical work, or return None when only this consumer left.

    A request client sends no more messages, so a nonblocking receive is purely
    an EOF probe. It emits no heartbeat frames and cannot disturb other users of
    the same in-flight entry.
    """
    result_seen = False
    while True:
        event, done, code = _BROKER.wait_update(entry, result_seen=result_seen)
        try:
            if event is not None:
                _send(conn, event if entry.get("artifact") else {"event": event})
                result_seen = True
        except OSError:
            return None
        if done:
            return code
        try:
            if conn.recv(0.0) == b"":
                return None
        except (AttributeError, OSError):
            # Simple in-process test channels have no receive side. A real
            # transport.Channel normalizes peer loss to b"".
            pass


def _status_payload(startup_token: str) -> dict:
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
        "token": startup_token,
        "startedAt": _STARTED_AT,
        "requests": _REQUESTS_SERVED[0],
        "inflight": sum(1 for thread in list(_INFLIGHT) if thread.is_alive()),
    })
    return snapshot


def _serve_job_watch(conn: transport.Channel, after: str | None, scope: dict) -> None:
    try:
        with contextlib.suppress(OSError):
            _send(conn, {"status": _JOBS.watch(after, **scope)})
    finally:
        with contextlib.suppress(OSError):
            conn.close()
        _JOB_WATCH_SLOTS.release()


def _start_job_watch(conn: transport.Channel, request: dict) -> bool:
    """Transfer channel ownership to a bounded waiter, or answer immediately."""
    after = request.get("after")
    after = after if isinstance(after, str) and len(after) <= 128 else None
    output, root = request.get("output"), request.get("storeRoot")
    scope = {"output": output, "store_root": root} if (
        isinstance(output, str) and isinstance(root, str) and len(output) <= 8192 and len(root) <= 8192
    ) else {}
    limited = bool(after) and not _JOB_WATCH_SLOTS.acquire(blocking=False)
    if not after or limited:
        snapshot = _JOBS.watch(timeout=0, **scope)
        if limited:
            snapshot["jobsWatchLimited"] = True
        with contextlib.suppress(OSError):
            _send(conn, {"status": snapshot})
        return False
    try:
        threading.Thread(target=_serve_job_watch, args=(conn, after, scope), daemon=True).start()
    except BaseException:
        _JOB_WATCH_SLOTS.release()
        raise
    return True


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
    items = [str(c) for c in (candidates or ())]
    for index, text in enumerate(items):
        if text.startswith("-") or not text.endswith(".py"):
            continue
        root = str(base or "")
        script = os.path.realpath(os.path.join(root, text) if root else text)
        # A file holding several models names the one this request builds
        # (``--model fn``): each model is its own subject -- its own worker, its
        # own in-flight coalescing -- exactly as if it lived in its own file.
        if "--model" in items:
            at = items.index("--model")
            if at + 1 < len(items):
                return f"{script}::{items[at + 1]}"
        return script
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
    is_artifact = tool == "artifact"

    if (tool not in _TOOL_IMPORTS and not is_artifact) or not isinstance(argv, list):
        with send_lock:
            _send(conn, {"stream": "stderr", "data": f"cadgen-daemon: invalid request for tool {tool!r}\n"})
            _send(conn, {"exit": 1})
        return

    if is_artifact:
        from cadgen.daemon.artifacts import normalize_request, store_path

        try:
            if argv:
                raise ValueError("artifact requests have no argv or source subject")
            if not isinstance(request.get("store_root"), str) or not request["store_root"]:
                raise ValueError("artifact requests require an explicit store_root")
            artifact = normalize_request(request.get("artifact"))
            root = store_path(request.get("store_root"))
        except (ValueError, TypeError, OSError) as exc:
            _send(conn, {"stream": "stderr", "data": f"invalid artifact request: {exc}\n"})
            _send(conn, {"exit": 1})
            return
        request = {**request, "artifact": artifact, "store_root": root}

    cwd = str(request.get("cwd") or "")
    model = "" if is_artifact else _script_path(argv, cwd)
    # What in-flight coalescing keys on: the model, or for a compile job the imported
    # document (which binds no worker -- it borrows a spare -- but two compiles of one
    # file are still one job).
    subject = "" if is_artifact else model or _document_path(argv, cwd)
    closure = str(request.get("closure") or "")
    if is_artifact:
        job = _JOBS.start_artifact(artifact, store_root=root, root_id=request.get("root_id"), dependency=request.get("dependency"))
    else:
        job = _JOBS.start(
            tool=tool, subject=subject, argv=argv, store_root=str(request.get("store_root") or ""),
            editing_producer=not bool(subject and closure and request.get("coalesce")),
            adopt_announced=True,
        )
    inflight = None
    if is_artifact or (subject and closure and request.get("coalesce")):
        if is_artifact:
            owns_work, inflight = _BROKER.claim_artifact_entry(artifact, store_root=root)
        else:
            owns_work, inflight = _BROKER.claim_entry(subject, closure, store_root=str(request.get("store_root") or ""))
        if not owns_work:
            # Identical source is already building: attach, relay its exit, run nothing.
            _log(f"{tool} {model}: coalesced onto the job in flight")
            try:
                code = _wait_for_inflight_consumer(conn, inflight)
            finally:
                _BROKER.detach(inflight)
            if code is None:
                _JOBS.finish(job, 1, error="client disconnected")
                return
            if is_artifact and inflight.get("result") is not None:
                _JOBS.record_artifact_result(job, inflight["result"]["artifactResult"])
            _JOBS.finish(job, code)
            with contextlib.suppress(OSError), send_lock:
                _send(conn, {"exit": code})
            return
        if not is_artifact:
            _JOBS.accept_editing_producer(job)
    try:
        worker = _POOL.acquire(model, dependency=bool(request.get("dependency")))
    except (pool_mod.WorkerGone, pool_mod.MemoryAdmissionError) as exc:
        # Failed spawn or memory admission. Return an explicit failure; a cold
        # retry here would bypass the daemon's aggregate admission policy.
        _log(f"{tool}: could not start a worker: {exc}")
        _JOBS.finish(job, 1, error=str(exc))
        if inflight is not None:
            _BROKER.finish_entry(inflight, 1)
        with contextlib.suppress(OSError), send_lock:
            _send(conn, {"stream": "stderr", "data": f"cadgen-daemon: could not start a worker: {exc}\n"})
            _send(conn, {"exit": 1})
        return

    exit_code, healthy = 1, True
    # The tail of the job's stderr: on failure its last FAILED/exception line is the
    # reason the ledger records, so a reader (the CAD Viewer) can say why.
    stderr_tail: collections.deque[str] = collections.deque(maxlen=80)
    watchdog_done = threading.Event()
    def preserve_coalesced_work() -> bool:
        return bool(inflight is not None and _BROKER.abandon(inflight))

    watchdog = threading.Thread(
        target=_watch_client,
        args=(conn, send_lock, watchdog_done, tool, worker, preserve_coalesced_work),
        daemon=True,
    )
    watchdog.start()
    relay_connected = True
    try:
        worker.send({
            "kind": "artifact" if is_artifact else "run",
            "tool": tool,
            "prog": request.get("prog"),
            "argv": [str(a) for a in argv],
            "cwd": request.get("cwd"),
            "env": request.get("env"),
            "store_root": request.get("store_root"),
            "root_id": request.get("root_id"),
            "job_id": job["id"],
            **({"artifact": artifact} if is_artifact else {}),
        })
        for frame in worker.frames(silence_timeout=WORKER_SILENCE_TIMEOUT_SECONDS):
            if "exit" in frame:
                exit_code = int(frame.get("exit") or 0)
                break
            if frame.get("stream") == "stderr":
                stderr_tail.append(str(frame.get("data") or ""))
            if not is_artifact:
                _JOBS.observe(frame)
            if is_artifact:
                if "event" in frame:
                    raise OSError("artifact worker emitted a source event")
                if "artifactResult" in frame:
                    from cadgen.daemon.artifacts import validate_result

                    try:
                        validate_result(artifact, frame["artifactResult"])
                        if inflight.get("result") is not None:
                            raise ValueError("duplicate artifact result")
                    except (ValueError, RuntimeError, TypeError) as exc:
                        raise OSError(f"invalid artifact worker result: {exc}") from exc
                    _JOBS.record_artifact_result(job, frame["artifactResult"])
                    _BROKER.publish_artifact_result(inflight, frame["artifactResult"])
            event = frame.get("event")
            if inflight is not None and isinstance(event, dict) and event.get("job") == job["id"]:
                _BROKER.publish_result(inflight, event)
            if relay_connected:
                try:
                    with send_lock:
                        _send(conn, frame)
                except OSError:
                    if preserve_coalesced_work():
                        relay_connected = False
                    else:
                        raise
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
        if is_artifact and exit_code == 0 and inflight.get("result") is None:
            exit_code = 1
            stderr_tail.append("artifact worker completed without an artifact result")
        reason = failure_message("".join(stderr_tail))[0] if exit_code != 0 else None
        _JOBS.finish(job, exit_code, error=reason or None)
        if inflight is not None:
            _BROKER.finish_entry(inflight, exit_code)

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


def _active_requests() -> list[threading.Thread]:
    return [thread for thread in list(_INFLIGHT) if thread.is_alive()]


_DAEMON_LOCK: transport.SingletonLock | None = None


def _bind(address: str) -> transport.Server | None:
    """One daemon per address, decided by a lock -- never by probing or sweeping.

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
        authkey = transport.ensure_authkey(address)
        return transport.Server(
            address,
            authkey,
            backlog=128,
            on_authentication_error=lambda: transport.publish_authkey(address, authkey),
        )
    except OSError as exc:
        _log(f"cannot bind {address}: {exc}")
        lock.release()
        _DAEMON_LOCK = None
        return None


def serve() -> int:
    os.environ["CADGEN_DAEMON_CHILD"] = "1"
    address = daemon_address()
    token = compute_version_token()
    server = _bind(address)
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
    state = {"last_activity": time.monotonic(), "idle_exit": False, "draining": False}

    def _watch_for_idle() -> None:
        slice_seconds = max(0.5, min(idle_timeout / 4, 5.0))
        while not server.closed:
            time.sleep(slice_seconds)
            if server.closed:
                return
            _POOL.unbind_idle()
            active = _active_requests()
            if active:
                state["last_activity"] = time.monotonic()  # a long build is not idleness
                continue
            if state["draining"]:
                server.close()
                return
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
                elif state["draining"]:
                    _log("version token changed; exiting")
                return 0
            state["last_activity"] = time.monotonic()
            try:
                request = _read_request(conn)
                if request is None:
                    continue
                if request.get("kind") == "status":
                    # Answered BEFORE the token check: asking what is warm must never
                    # make the daemon exit, whichever cadgen the asker is running.
                    if request.get("jobsOnly") is True:
                        if _start_job_watch(conn, request):
                            conn = None  # the bounded watcher owns it
                    else:
                        with contextlib.suppress(OSError):
                            _send(conn, {"status": _status_payload(token)})
                    continue
                token_changed = request.get("token") != token
                dependency_finishing_old_work = bool(
                    request.get("dependency") and (state["draining"] or _active_requests())
                )
                if state["draining"] and not request.get("dependency"):
                    with contextlib.suppress(OSError):
                        _send(conn, {"restart": True})
                    continue
                if token_changed and not dependency_finishing_old_work:
                    active = _active_requests()
                    if active:
                        # Keep the old address and singleton lock together while its
                        # jobs finish. Their workers can still submit child/artifact
                        # dependencies; fresh top-level calls are sent cold until the
                        # drain completes. Closing the listener here deadlocked a long
                        # job against its own final artifact request.
                        state["draining"] = True
                        _log(f"version token changed; finishing {len(active)} job(s) in flight before exiting")
                        with contextlib.suppress(OSError):
                            _send(conn, {"restart": True})
                        continue
                    # With no work to preserve, release the address before replying so
                    # the client's respawn cannot race this daemon's cleanup.
                    server.close()
                    _release_address()
                    with contextlib.suppress(OSError):
                        _send(conn, {"restart": True})
                    conn.close()
                    conn = None
                    _log("version token changed; exiting")
                    return 0
                if token_changed:
                    state["draining"] = True
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
