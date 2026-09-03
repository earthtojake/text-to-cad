"""One warm OCP process. Reads job requests on stdin, writes framed output on stdout.

The daemon used to run tools inside itself, which capped it at one job forever: a tool
needs ``os.chdir`` and ``sys.argv``, and those are process globals. Moving the work into
subprocesses gives each job its own globals, so concurrency across workers costs nothing
to reason about — and a model that segfaults OCP takes down one worker instead of the
daemon.

The frames here are deliberately the same shape the daemon sends its client
(``{"stream": ..., "data": ...}`` then ``{"exit": ...}``), so the supervisor is a pure
relay and the client's wire protocol is untouched.

Two request kinds:

* ``run``    — a CLI tool, output streamed as frames. What the skill commands use.
* ``invoke`` — a cadgen module's ``main``, result returned as one payload. What the CAD
  Viewer needs, replacing its own warm-worker system.

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
    """Apply the requesting CLIENT's cache-resolution environment for this job.

    A worker inherits the environment of whichever build spawned the DAEMON, so
    without this the first build's cache root became every later build's,
    across projects. ``cache_paths.cache_root()`` documents ONE resolution rule
    ($CADGEN_CACHE_DIR, else the platform convention, else ~/.cache/cadgen);
    the daemon must not add a hidden second one. A var absent from the request
    is DELETED — unset for the client means unset for the job — which also
    clears a var a previous job's model code exported at import time."""
    env = request.get("env")
    if not isinstance(env, dict):
        return
    for name in FORWARDED_ENV_VARS:
        value = env.get(name)
        if isinstance(value, str):
            os.environ[name] = value
        else:
            os.environ.pop(name, None)


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


def _run(request: dict) -> int:
    tool = request.get("tool")
    argv = [str(a) for a in request.get("argv") or []]
    cwd = request.get("cwd")
    prog = str(request.get("prog") or "") or None

    if tool not in _TOOL_IMPORTS:
        _emit({"stream": "stderr", "data": f"cadgen-daemon: unknown tool {tool!r}\n"})
        return 1

    previous_argv = sys.argv
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
        _park()
        # Deterministic closure capture: the next job must see a clean first-party module
        # space or it records a different sourceClosureHash than a cold build would.
        _evict_first_party_modules()


def _module_dispatch() -> dict:
    """cadgen module name -> its in-process payload entrypoint.

    An ALLOWLIST on purpose, ported from the viewer's own worker: `invoke` names a module
    over a socket, and importing whatever it says would be both a wider surface and a
    worse failure (an unknown name would raise deep inside an import instead of here).
    Imported lazily so the OCP cost lands in this process, never in the supervisor.
    """
    from cadgen import (
        dxf_export_target,
        step_artifact_cli,
        step_export_target,
    )

    return {
        "cadgen.dxf_export_target": dxf_export_target.run_cli_payload,
        "cadgen.step_artifact_cli": step_artifact_cli.run_cli_payload,
        "cadgen.step_export_target": step_export_target.run_cli_payload,
    }


_DISPATCH: dict | None = None


def _invoke(request: dict) -> dict:
    """Run a cadgen module's payload entrypoint — the CAD Viewer's contract.

    Returns the payload dict directly rather than parsing it back out of stdout: these
    entrypoints exist precisely so a warm caller does not have to.
    """
    global _DISPATCH
    module_name = str(request.get("module") or "")
    args = [str(a) for a in request.get("args") or []]
    repo_root = request.get("repo_root")
    noise = io.StringIO()
    try:
        if _DISPATCH is None:
            _DISPATCH = _module_dispatch()
        run = _DISPATCH.get(module_name)
        if run is None:
            return {"ok": False, "error": f"Unknown cadgen module for worker: {module_name}"}
        if isinstance(repo_root, str) and repo_root:
            if not os.path.isdir(repo_root):
                # Same contract as _run's cwd: a request naming a directory that
                # is not there fails as a payload the caller can read, rather
                # than running against whatever tempdir the worker is parked in.
                return {"ok": False, "error": _missing_cwd_message(repo_root)}
            os.chdir(repo_root)
        # stderr is captured rather than streamed: the cold path reports a failure's
        # text in the payload, and warm must match.
        noise = io.StringIO()
        with contextlib.redirect_stdout(noise), contextlib.redirect_stderr(noise):
            return dict(run(args))
    except SystemExit as exc:
        # argparse exits rather than raising. Cold reports the usage text and the code,
        # so warm does too -- otherwise the same bad call reads as "SystemExit: 2" in one
        # path and a usage message in the other.
        code = exc.code if isinstance(exc.code, int) else 1
        message = noise.getvalue().strip() or f"cadgen {module_name} exited with code {code}"
        return {"ok": False, "exitCode": code, "error": message}
    except BaseException as exc:  # noqa: BLE001 - a failed build must not kill the worker
        detail = noise.getvalue().strip()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}" + (f"\n{detail}" if detail else "")}
    finally:
        _park()


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
        elif kind == "invoke":
            _apply_request_env(request)
            _emit({"result": _invoke(request), "pid": os.getpid()})
        elif kind == "shutdown":
            return 0
        else:
            _apply_request_env(request)
            _emit({"exit": _run(request), "pid": os.getpid()})
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
