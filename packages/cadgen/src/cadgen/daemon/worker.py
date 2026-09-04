"""One warm OCP process. Reads job requests on stdin, writes framed output on stdout.

The daemon used to run tools inside itself, which capped it at one job forever: a tool
needs ``os.chdir`` and ``sys.argv``, and those are process globals. Moving the work into
subprocesses gives each job its own globals, so concurrency across workers costs nothing
to reason about — and a model that segfaults OCP takes down one worker instead of the
daemon.

The frames here are deliberately the same shape the daemon sends its client
(``{"stream": ..., "data": ...}`` then ``{"exit": ...}``), so the supervisor is a pure
relay and the client's wire protocol is untouched. A third frame, ``{"event": ...}``,
carries build-tree events (STORE.md §Lazy children): a child a model's body submits
from inside this worker reports through the same channel as the worker's own output.

One request kind, ``run`` — a CLI tool, output streamed as frames. The store root
arrives on every request (``store_root``) and is applied per job, so one daemon serves
any number of isolated stores and a worker never inherits the root of whichever build
spawned the daemon.

Exits when stdin closes, so a supervisor that dies cannot leave a 274 MB OCP process
behind.
"""

from __future__ import annotations

import contextlib
import importlib
import inspect
import io
import json
import os
import sys
import tempfile
import traceback

# Same registry the supervisor validates against; imported rather than duplicated.
from cadgen.daemon.client import FORWARDED_ENV_VARS
from cadgen.daemon.server import _TOOL_IMPORTS, _evict_first_party_modules


def _apply_request_env(request: dict) -> None:
    """Apply the requesting CLIENT's environment for this job.

    A worker inherits the environment of whichever build spawned the DAEMON, so
    without this the first build's store became every later build's, across
    projects. The store root is an explicit request field and wins; the
    forwarded vars cover the rest of ``store.paths.store_root()``'s resolution
    rule so the daemon adds no hidden second one. A var absent from the request
    is DELETED — unset for the client means unset for the job — which also
    clears a var a previous job's model code exported at import time.

    ``root_id`` names the build tree this job belongs to; a child this job
    submits inherits it through the environment so its events tag the same tree.
    """
    env = request.get("env")
    if not isinstance(env, dict):
        env = {}
    for name in FORWARDED_ENV_VARS:
        value = env.get(name)
        if isinstance(value, str):
            os.environ[name] = value
        else:
            os.environ.pop(name, None)
    store_root = request.get("store_root")
    if isinstance(store_root, str) and store_root:
        os.environ["CADGEN_CACHE_DIR"] = store_root
    root_id = request.get("root_id")
    if isinstance(root_id, str) and root_id:
        os.environ["CADGEN_ROOT_ID"] = root_id
    else:
        os.environ.pop("CADGEN_ROOT_ID", None)


def _emit(frame: dict) -> None:
    """One JSON line on the real stdout. Never the redirected one."""
    sys.__stdout__.write(json.dumps(frame, separators=(",", ":")) + "\n")
    sys.__stdout__.flush()


class _FrameWriter(io.TextIOBase):
    """File-like sink that turns a tool's writes into stream frames."""

    def __init__(self, stream: str) -> None:
        self._stream = stream

    def write(self, data) -> int:
        text = data if isinstance(data, str) else str(data)
        if text:
            _emit({"stream": self._stream, "data": text})
        return len(text)

    def isatty(self) -> bool:
        return False


def _park() -> None:
    """Leave the job's directory for one that cannot be deleted out from under us.

    A worker outlives the directories it builds in, and it inherits its starting cwd from
    whichever client happened to spawn the daemon. Holding either means a later
    ``os.getcwd()`` raises once that directory is removed, failing every subsequent job on
    this worker with no useful message. The single-process daemon never hit this because
    it restored the daemon's own cwd; a pooled worker is long-lived across many clients.
    """
    with contextlib.suppress(OSError):
        os.chdir(tempfile.gettempdir())


def _missing_cwd_message(cwd: str) -> str:
    return f"working directory does not exist: {cwd}"


def _enter(cwd: object, err: _FrameWriter) -> bool:
    """Move into the request's working directory, or fail the REQUEST loudly.

    Relative paths in a request resolve against the process cwd — that is the
    native contract every cadgen path argument keeps — and a worker is parked in
    a tempdir between jobs (see ``_park``). Skipping the chdir when the directory
    is gone therefore does not "fall back" to anything: it silently resolves the
    caller's relative paths under the tempdir, so the job reads nothing, writes
    into the tempdir, or invents an artifact somewhere the caller will never look.

    Failing here costs one request. The worker itself is fine — it never left the
    parked directory — so the daemon stays up and the next request is served.
    """
    if not isinstance(cwd, str) or not cwd:
        return True
    if not os.path.isdir(cwd):
        err.write(_missing_cwd_message(cwd) + "\n")
        return False
    os.chdir(cwd)
    return True


def _tool_main(tool: str):
    return getattr(importlib.import_module(_TOOL_IMPORTS[tool]), "main")


def _warm_imports() -> None:
    """Pay every import a job will need BEFORE announcing readiness.

    A spare exists to make a model's first build import-free, and "imported build123d"
    is only half of that: the pipeline behind each tool (generation, the STEP writer,
    the packagers) is another few hundred milliseconds a fresh worker paid on its first
    job. Spares fill in the background, so the cost lands where nobody is waiting.
    """
    with contextlib.suppress(Exception):
        importlib.import_module("cadgen.generation")
    for tool in _TOOL_IMPORTS:
        with contextlib.suppress(Exception):
            _tool_main(tool)


def _run(request: dict) -> int:
    tool = request.get("tool")
    argv = [str(a) for a in request.get("argv") or []]
    cwd = request.get("cwd")
    prog = str(request.get("prog") or "") or None

    if tool not in _TOOL_IMPORTS:
        _emit({"stream": "stderr", "data": f"cadgen-daemon: unknown tool {tool!r}\n"})
        return 1

    previous_argv = sys.argv
    # A build seeds the model's folder onto sys.path for its whole run (normal script
    # semantics); the next job on this worker starts from the worker's own path again.
    previous_sys_path = list(sys.path)
    out, err = _FrameWriter("stdout"), _FrameWriter("stderr")
    try:
        if not _enter(cwd, err):
            return 1
        sys.argv = [prog or f"cadgen {tool}", *argv]
        main = _tool_main(tool)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            # Pass the caller's name where the parser takes one, so a command reports the
            # same usage warm as cold.
            if prog and "prog" in inspect.signature(main).parameters:
                result = main(argv, prog=prog)
            else:
                result = main(argv)
        return 0 if result is None else int(result)
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, str):
            err.write(code + "\n")
            return 1
        return int(code or 0)
    except BaseException:  # noqa: BLE001 - a failed build must not kill the worker
        err.write(traceback.format_exc())
        return 1
    finally:
        sys.argv = previous_argv
        sys.path[:] = previous_sys_path
        _park()
        # Deterministic closure capture: the next job must see a clean first-party module
        # space or it records a different sourceClosureHash than a cold build would.
        _evict_first_party_modules()


def serve() -> int:
    os.environ["CADGEN_DAEMON_CHILD"] = "1"
    # This process's stdout is not a console, it is the pool's FRAME CHANNEL, so
    # its encoding belongs to the protocol rather than to the platform. Windows
    # would otherwise hand it the ANSI code page: a job whose message carries a
    # character that page cannot represent would either arrive mangled or, with
    # strict handling, kill the frame mid-write. Both ends say utf-8 (see
    # pool.Worker's Popen) and neither infers it.
    for stream in (sys.stdout, sys.stdin):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding="utf-8", errors="backslashreplace")
    # Child-build events from this worker's jobs ride the frame channel; the
    # supervisor relays them to the requesting client verbatim.
    from cadgen.daemon import executors

    executors.set_event_sink(lambda event: _emit({"event": event}))
    _warm_imports()
    _emit({"ready": os.getpid()})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            _emit({"exit": 1, "error": "malformed request"})
            continue
        kind = request.get("kind")
        if kind == "ping":
            _emit({"pong": os.getpid()})
        elif kind == "shutdown":
            return 0
        else:
            _apply_request_env(request)
            _emit({"exit": _run(request), "pid": os.getpid()})
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
