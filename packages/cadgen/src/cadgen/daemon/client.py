"""Stdlib-only client for the warm CAD CLI daemon.

The tool launchers' ``CADGEN_DAEMON`` shim imports this module BEFORE any heavy
import, so it must stay dependency-free and cheap to import. Everything here
falls back to ``None`` (caller runs inline, cold) on any spawn or protocol
problem — the daemon is a fast path, never a requirement.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from cadgen.daemon import transport

# The installed cadgen package directory. Everything the daemon holds resident lives under
# it, so it is both the identity of "which cadgen is this" and the thing to watch for edits.
# It resolves correctly either way: an editable install points at a checkout's source, a
# wheel install at site-packages.
CADGEN_DIR = Path(__file__).resolve().parents[1]

SPAWN_WAIT_SECONDS = 30.0  # first daemon start pays the full OCP import

# The daemon handles requests STRICTLY SEQUENTIALLY. A client that connects while
# the daemon is still finishing someone else's build — including an orphaned one
# whose client was killed — is accepted by the listen backlog and then simply
# waits. Without a deadline that wait is unbounded, which is how a warm call ends
# up hanging for minutes on a model that builds cold in seconds. Bound it: a
# legitimate large build can be silent for a long time, so the default is
# generous, but it is finite, so the documented cold fallback actually happens.
DEFAULT_REQUEST_TIMEOUT_SECONDS = 600.0
# What makes a running daemon stale. The distribution version alone is not enough in a
# checkout, where an editable install keeps one version across every edit; .py mtimes alone
# are not enough for a wheel, where they are fixed at install time and two versions can be
# installed in turn without any file changing under a given path. Use both.
# Skill code is deliberately NOT watched any more: the skills hold thin shims that the
# daemon never imports, so editing one cannot make the resident process stale.

_RESTART = object()
# A frame did not arrive in time, as distinct from the channel closing.
_TIMED_OUT = object()

# Cache resolution is per-CLIENT, never per-daemon. A worker inherits the
# environment of whichever build spawned the daemon, so without forwarding
# these the first build's cache root silently became every later build's,
# across projects (a model that set XDG_CACHE_HOME at import relocated the
# cache for every other project on the machine until the daemon recycled).
# They travel with every request and the worker applies them per JOB —
# a name absent here means "unset for this job" (see worker._apply_request_env).
FORWARDED_ENV_VARS = ("CADGEN_CACHE_DIR", "XDG_CACHE_HOME", "LOCALAPPDATA")


def forwarded_env() -> dict[str, str]:
    """The requesting process's cache-resolution environment, for the payload."""
    return {name: os.environ[name] for name in FORWARDED_ENV_VARS if name in os.environ}


def daemon_supported() -> bool:
    """Whether this platform can reach a daemon at all.

    Delegated to the transport, which answers for the family it would actually use:
    AF_UNIX on POSIX, AF_PIPE on Windows. It stays a CHECK rather than a caught exception
    because the callers' fallbacks are keyed on OSError or on a None return, and an absent
    address family raises neither.
    """
    return transport.supported()


def daemon_identity() -> str:
    """The short name this checkout's daemon is known by."""
    return transport.identity_digest(str(CADGEN_DIR))


def daemon_address() -> str:
    """Where this checkout's daemon listens.

    CADGEN_DAEMON_SOCKET still overrides it, and still means "the address" -- a filesystem
    path on POSIX, a pipe name on Windows. The default carries a protocol version, so a
    client never reaches a daemon speaking the older newline-JSON format.
    """
    override = os.environ.get("CADGEN_DAEMON_SOCKET")
    if override:
        return str(override)
    return transport.address_for(daemon_identity())


def log_path(address: str | None = None) -> Path:
    """Where the daemon's lifecycle and OCP noise go.

    Derived from the identity rather than from the address: a pipe name is not a path, so
    there is nothing to hang a sibling .log off on Windows.
    """
    if address and os.name != "nt":
        return Path(address).with_suffix(".log")
    return transport.state_dir() / f"cadgen-daemon-{daemon_identity()}.log"


def request_timeout() -> float:
    """Seconds to wait for the daemon before giving up and running cold."""
    return DEFAULT_REQUEST_TIMEOUT_SECONDS


def compute_version_token(root: Path | None = None) -> str:
    """The running daemon's identity: cadgen's version plus the newest ``.py`` mtime under
    it. Client and server compute this identically; inequality means restart."""
    base = Path(root) if root is not None else CADGEN_DIR
    newest = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [name for name in dirnames if name != "__pycache__"]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            try:
                mtime = os.stat(os.path.join(dirpath, filename)).st_mtime_ns
            except OSError:
                continue
            newest = max(newest, mtime)

    from cadgen import __version__

    return f"{__version__}:{newest}"


def _request_payload(
    tool: str,
    argv: list[str],
    cwd: str | None,
    prog: str | None,
    *,
    store_root: str | None = None,
    root_id: str | None = None,
    closure: str | None = None,
    coalesce: bool = False,
) -> dict:
    from cadgen.store.paths import store_root as default_store_root

    return {
        "tool": str(tool),
        # The name the caller is known by. Without it the daemon invented
        # "scripts/<tool>", so `cadgen step gen --help` printed a different
        # usage line warm than cold -- the same command answering to two names
        # depending on whether a daemon happened to be running.
        "prog": str(prog) if prog else None,
        "argv": [str(arg) for arg in argv],
        "cwd": str(cwd) if cwd else os.getcwd(),
        "env": forwarded_env(),
        # The store this job reads and writes: an explicit request field, never
        # the worker's ambient environment, so one daemon serves isolated stores.
        "store_root": str(store_root) if store_root else str(default_store_root()),
        # The top-level request this job belongs to; child-build events carry it
        # so the root's build tree can place them.
        "root_id": str(root_id) if root_id else None,
        # In-flight coalescing (cadgen.daemon.broker): a child submit carries its source's
        # closure hash and may join a job already building the same thing. A top-level
        # request never does -- the model the user asked for runs.
        "closure": str(closure) if closure else None,
        "coalesce": bool(coalesce and closure),
        "token": compute_version_token(),
    }


def run_via_daemon(
    tool: str, argv: list[str], cwd: str | None = None, prog: str | None = None
) -> int | None:
    """Run one CLI invocation on the warm daemon; ``None`` means run inline instead."""
    # Warm by DEFAULT. It was opt-in while the daemon could only hold one job, because
    # turning it on serialised parallel builds -- the moonwatch README told people to
    # avoid it for exactly that. The pool removed the reason: a burst spawns workers up
    # to the cap and overflows cold rather than queueing. An optimisation nobody enables
    # is the same as not having one.
    if os.environ.get("CADGEN_DAEMON") == "0" or os.environ.get("CADGEN_DAEMON_CHILD"):
        return None
    if not daemon_supported():
        return None
    argv = [str(arg) for arg in argv]
    if "-" in argv:
        # "-" conventionally reads a payload from stdin (e.g. snapshot --job -);
        # the daemon has no stdin channel, so run those inline.
        return None
    from cadgen.daemon.executors import emit_event

    payload = _request_payload(tool, argv, cwd, prog, root_id=os.environ.get("CADGEN_ROOT_ID"))
    return _run_with_retry(payload, on_event=emit_event)


def run_nested(
    tool: str,
    argv: list[str],
    cwd: str | None,
    *,
    prog: str | None = None,
    store_root: str | None = None,
    root_id: str | None = None,
    closure: str | None = None,
    on_stream: Callable[[str], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> int | None:
    """A child build submitted from INSIDE a build (a worker or a client).

    Unlike :func:`run_via_daemon` this ignores ``CADGEN_DAEMON_CHILD``: a worker
    submitting a child is the pool's nesting, not recursion into itself. Stream
    frames go to ``on_stream`` (captured for the error path), events to
    ``on_event``. ``None`` still means "the daemon could not take it".
    """
    if os.environ.get("CADGEN_DAEMON") == "0" or not daemon_supported():
        return None
    payload = _request_payload(
        tool, argv, cwd, prog, store_root=store_root, root_id=root_id, closure=closure, coalesce=True
    )
    return _run_with_retry(payload, on_stream=on_stream, on_event=on_event)


def _run_with_retry(payload: dict, *, on_stream=None, on_event=None) -> int | None:
    address = daemon_address()
    for attempt in range(2):
        conn = _connect_or_spawn(address)
        if conn is None:
            return None
        try:
            outcome = _run_request(conn, payload, on_stream=on_stream, on_event=on_event)
        finally:
            try:
                conn.close()
            except OSError:
                pass
        if outcome is _RESTART and attempt == 0:
            continue  # stale daemon exited; respawn once and retry
        return outcome if isinstance(outcome, int) else None
    return None


def _connect(address: str) -> transport.Channel:
    key = transport.read_authkey(daemon_identity())
    if not key:
        # No key means no daemon has started under this identity, so there is nothing to
        # connect to. Raising keeps this indistinguishable from a refused connection.
        raise OSError("no daemon key")
    return transport.connect(address, key)


def _connect_or_spawn(address: str) -> transport.Channel | None:
    try:
        return _connect(address)
    except OSError:
        pass
    # Never unlink the address here. Only the daemon that holds the singleton lock
    # may remove a leftover socket (server._bind). And only ONE client spawns: the
    # first to take the spawn lock starts the daemon; the others just wait for the
    # address to answer. Twenty concurrent clients used to start twenty daemons.
    election = transport.spawn_lock(daemon_identity())
    spawner = election.acquire()
    process = None
    try:
        if spawner:
            process = _spawn_daemon(address)
            if process is None:
                return None
        deadline = time.monotonic() + SPAWN_WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                return _connect(address)
            except OSError:
                if process is not None and process.poll() is not None:
                    # Our daemon exited: it failed, or it stood down because one is
                    # already bound. One more connect tells the two apart.
                    try:
                        return _connect(address)
                    except OSError:
                        return None
                time.sleep(0.05)
        return None
    finally:
        if spawner:
            election.release()


def _detach_kwargs() -> dict:
    """How to start a daemon that outlives the command that needed it.

    start_new_session is POSIX-only and Windows does not merely ignore it politely -- it
    is named `unused_start_new_session` in subprocess, so passing it there is silently
    nothing and the daemon would share its parent's console and die with it.
    """
    if os.name == "nt":
        return {
            "creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        }
    return {"start_new_session": True}


def _spawn_daemon(address: str) -> subprocess.Popen | None:
    from cadgen.daemon.executors import worker_env

    # The daemon and its workers must import THIS cadgen from whatever directory they
    # run in; a relative PYTHONPATH entry would otherwise pick the installed one.
    env = worker_env()
    env["CADGEN_DAEMON_CHILD"] = "1"
    env.setdefault("CADGEN_DAEMON_SOCKET", str(address))
    try:
        # Before the daemon exists, so a client that finds an address always finds the key
        # that goes with it.
        transport.ensure_authkey(daemon_identity())
        log_file_path = log_path(address)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file_path, "ab") as log_file:
            return subprocess.Popen(
                [sys.executable, "-m", "cadgen.daemon"],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                **_detach_kwargs(),
            )
    except OSError:
        return None


def _send_json(channel: transport.Channel, payload: dict) -> bool:
    try:
        channel.send(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    except (OSError, ValueError):
        return False
    return True


def _recv_json(channel: transport.Channel, timeout: float | None):
    """One frame: a dict, ``_TIMED_OUT``, or None for a closed or unreadable channel."""
    try:
        raw = channel.recv(timeout)
    except (OSError, EOFError):
        return None
    if raw is None:
        return _TIMED_OUT
    if not raw:
        return None
    try:
        message = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    return message if isinstance(message, dict) else None


def _job_words(payload: dict) -> tuple[str, list[str], list[str]]:
    """``(how the user spelled the command, its arguments, the cold argv)``.

    The ``run`` tool is the decorator's warm handoff for ``python <script>``: its
    argv carries the SCRIPT PATH first and its prog is ``python <name>``, so the
    job reads ``python <name> <args>`` and the rerun is ``python <path> <args>``.
    Every other tool is a ``cadgen`` command whose argv is exactly what follows it.
    """
    argv = [str(arg) for arg in payload.get("argv") or []]
    tool = str(payload.get("tool") or "")
    prog = str(payload.get("prog") or f"cadgen {tool}")
    if tool == "run" and argv:
        return prog, argv[1:], ["python", *argv]
    return prog, argv, [*prog.split(), *argv]


def cold_rerun_command(payload: dict) -> str:
    """The job's command alone, quoted for this platform's shell -- no env prefix.

    The prefix is the caller's business because it is shell-specific, and this
    function cannot know the shell: `set X=0 && cmd` is cmd.exe only, and in
    PowerShell it assigns a variable literally named `X=0` and then fails on
    `&&` (a syntax error in 5.1). Guessing produces a line the user pastes and
    that silently does the wrong thing, at the worst possible moment.
    """
    import shlex

    _prog, _args, cold = _job_words(payload)
    return subprocess.list2cmdline(cold) if os.name == "nt" else shlex.join(cold)


def cold_rerun_instructions(payload: dict) -> str:
    """The rerun, spelled for whatever shell the user is in.

    POSIX keeps the one-liner. Windows gets a shell-neutral instruction first --
    which is what makes Git Bash, fish and csh users safe without enumerating
    them -- and then both paste-able forms, because the two shells that ship
    with Windows need different syntax and no signal reliably distinguishes them.
    """
    command = cold_rerun_command(payload)
    if os.name != "nt":
        return f"  CADGEN_DAEMON=0 {command}\n"
    return (
        "  Set CADGEN_DAEMON=0 in the environment, then run:\n"
        f"    {command}\n"
        "  Or in one line:\n"
        f"    cmd.exe      set CADGEN_DAEMON=0 && {command}\n"
        f"    PowerShell   $env:CADGEN_DAEMON='0'; {command}\n"
    )


def worker_died_message(payload: dict, death: dict) -> str:
    """What the user reads when the warm worker running THEIR job dies.

    Says that the worker died and how (the pool's evidence: exit code or signal),
    names the job, suspects the likely causes, states that nothing was retried --
    a 35-minute job silently re-running cold is worse than the failure -- and
    gives the rerun verbatim. Every clause is load-bearing; the test pins them.
    """
    prog, args, _cold = _job_words(payload)
    job = " ".join([prog, *args])
    detail = str(death.get("detail") or "worker closed the connection")
    return (
        f"cadgen-daemon: the warm worker running `{job}` died mid-job ({detail}) -- "
        "most likely out of memory, or a crash in the geometry kernel. The job was NOT "
        "retried. Run it cold, in its own process, to see the failure directly:\n"
        f"{cold_rerun_instructions(payload)}"
    )


def _run_request(
    channel: transport.Channel, payload: dict, *, on_stream=None, on_event=None
) -> int | object | None:
    """Send one request and stream the response; int exit code, ``_RESTART``, or
    ``None`` on any protocol fault.

    Stream frames go to the process's own stdout/stderr unless ``on_stream`` is
    given (a nested child build captures them); ``event`` frames — the build
    tree's model transitions — go to ``on_event``."""
    if not _send_json(channel, payload):
        return None
    # Applies per frame, not to the whole request: a daemon that is streaming output keeps
    # resetting it, so only genuine silence trips the deadline.
    timeout = request_timeout() or None
    streams = {"stdout": sys.stdout, "stderr": sys.stderr}
    while True:
        message = _recv_json(channel, timeout)
        if message is _TIMED_OUT:
            # Silent past the deadline: either the daemon is wedged, or it is still
            # grinding through a queued build we cannot see. Either way, fall back to
            # a cold in-process run so THIS invocation still completes. Say so on
            # stderr — a silent 10-minute stall that then "just works" is the exact
            # confusion this deadline exists to prevent.
            print(
                f"cadgen-daemon: no response for {timeout:.0f}s; running cold",
                file=sys.stderr,
                flush=True,
            )
            return None
        if message is None:
            return None  # closed without an exit frame
        if message.get("restart"):
            return _RESTART
        if "exit" in message:
            return int(message["exit"])
        if "event" in message:
            if on_event is not None and isinstance(message["event"], dict):
                on_event(message["event"])
            continue
        if "workerDied" in message:
            # The worker running this job is gone. The supervisor follows with the exit
            # frame; this is the one place the loss is explained, and it is never a
            # silent cold retry -- the caller's job may have run for half an hour.
            text = worker_died_message(payload, message["workerDied"] or {})
            if on_stream is not None:
                on_stream(text)
            else:
                sys.stderr.write(text)
                sys.stderr.flush()
            continue
        data = message.get("data")
        stream = message.get("stream")
        if stream not in streams or not isinstance(data, str):
            return None
        if on_stream is not None:
            on_stream(data)
            continue
        target = streams[stream]
        target.write(data)
        target.flush()




def status() -> dict | None:
    """The running daemon's state, or None if there is none.

    Deliberately does NOT spawn one: "is anything warm?" must be answerable without
    changing the answer.
    """
    if not daemon_supported():
        return None
    try:
        channel = _connect(daemon_address())
    except OSError:
        return None
    try:
        if not _send_json(channel, {"kind": "status", "token": compute_version_token()}):
            return None
        while True:
            message = _recv_json(channel, 10.0)
            if message is _TIMED_OUT or message is None:
                return None
            if message.get("restart"):
                return None  # a stale daemon is on its way out; report nothing warm
            if "status" in message:
                return message["status"]
    finally:
        with contextlib.suppress(OSError):
            channel.close()
