"""The CAD Viewer server: ``cadgen viewer``.

A viewer serves every CAD file on the machine by absolute path, on one port: 3245
by default, or the one ``--port N`` names, as any web server does. The page opens
``?file=/abs/part.step`` and browses from that file's folder. Launching is
UNCONDITIONAL, Jupyter-style: running ``cadgen viewer`` from anywhere ends with
the URL of a live, correct Viewer. Before it binds, the launcher asks the port
who holds it (``GET /__cad/server``):

* nothing — it starts there and prints ``action:"started"``;
* this user's viewer at this identity token (version plus the runtime content
  digest — see ``identity_token``) — its URL is printed with
  ``action:"reused"`` and nothing is spawned;
* this user's viewer running other code — it is asked to exit
  (``POST /__cad/shutdown``), and once the port is free this launch starts
  there (``action:"started"``): the newest code wins;
* anything else — another program, another user's viewer — a refusal that
  names ``--port``. The bind decides that: the question only finds this
  user's viewers.

The printed URL (and the ``--json {url,port,action}`` line) is the contract.
``--new`` is the one way past all of it: an OS-assigned free port, never asked
about, never reused — for a development server and for tests.

A launch that STARTS a server is that server and stays in the foreground; a
launch that reuses one prints and exits. ``--detach`` makes both return: the
server runs in the background (its own session, its output to one log in the
state directory, ``viewer.log``, found without asking anyone) and the launcher
exits once it has announced itself — the spelling for agents and scripts,
which wait for a command to finish. ``cadgen viewer stop [--port N]`` asks the
viewer on a port to exit.

``--api-only`` serves the two API prefixes and nothing else, because Vite owns
the client — this is what lets ``npm run dev`` work on a checkout that has never
been built; ``npm run dev`` runs it with ``--new``.

A Viewer has no directory. The folder a server is started in is where the page
resolves a developer's relative ``?file=`` (``serverInfo.start``), and nothing
more: it bounds nothing, and a launch from another folder reuses the server all
the same. Launch is::

    cadgen viewer            # or: python -m cadgen.viewer

There is no interpreter discovery, and deliberately so: a search for one
(``$CADGEN_PYTHON``, ``PATH``, a ``.venv`` found in a folder) would mean that
OPENING AN UNTRUSTED FOLDER THAT SHIPS A .venv hands it the interpreter to
execute. The server IS the interpreter that installed cadgen. Do not
introduce a search in any form.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

# --- interpreter floor ---------------------------------------------------
#
# Checked HERE, at import, before a single request can arrive. macOS still
# ships Python 3.9 as `python3` — which is also the default the client's dev
# server spawns — and on 3.9 the server BOOTS, prints the URL contract, and
# then answers the very first catalog request with a raw
# `realpath() got an unexpected keyword argument 'strict'`. A tool that starts
# and then fails on first contact is worse than one that refuses to start, so
# it refuses to start. pip enforces cadgen's own floor for an installed wheel;
# this covers a source tree reached through PYTHONPATH, where nothing else does.
#
# The floor is 3.11, not the 3.10 today's code strictly needs (`strict=` landed
# in 3.10): 3.11 is what cadgen's metadata requires, and one number that is
# true everywhere beats two that drift. Everything in this block is
# deliberately 3.9-parseable, or the refusal would itself be a SyntaxError.
MINIMUM_PYTHON = (3, 11)


def unsupported_python_message(version_info=None, executable: str = "") -> str:
    """The refusal text for an interpreter below the floor; ``""`` when it is fine.

    Split from the check so it can be asserted on from a test run, which by
    construction runs on an interpreter that is ABOVE the floor.
    """
    version_info = sys.version_info if version_info is None else version_info
    if tuple(version_info)[:2] >= MINIMUM_PYTHON:
        return ""
    required = ".".join(str(part) for part in MINIMUM_PYTHON)
    running = ".".join(str(part) for part in tuple(version_info)[:3])
    newer = "python3.{}".format(MINIMUM_PYTHON[1])
    return (
        "CAD Viewer needs Python {required} or newer. This interpreter is {running}:\n"
        "    {executable}\n"
        "\n"
        "Run the server with a newer one:\n"
        "    {newer} -m cadgen.viewer\n"
        "For `npm run dev`, name it with VIEWER_PYTHON:\n"
        "    VIEWER_PYTHON={newer} npm run dev\n"
        "\n"
        "macOS ships {running_major} as `python3`; install a newer interpreter with\n"
        "Homebrew (`brew install python@3.13`), pyenv, or python.org.\n"
    ).format(
        required=required,
        running=running,
        executable=executable or sys.executable,
        newer=newer,
        running_major=".".join(str(part) for part in tuple(version_info)[:2]),
    )


_UNSUPPORTED_PYTHON = unsupported_python_message()
if _UNSUPPORTED_PYTHON:
    sys.stderr.write(_UNSUPPORTED_PYTHON)
    sys.stderr.flush()
    raise SystemExit(1)

from cadgen import assets  # noqa: E402

from . import reload as dev_reload  # noqa: E402
from .handler import CadHTTPServer, make_handler_class  # noqa: E402
from .http_app import POST_GUARD_HEADER, create_cad_app, identity_token, newest_mtime_ns, os_user  # noqa: E402

DEFAULT_PROG = "cadgen viewer"
DEFAULT_VIEWER_HOST = "127.0.0.1"
DEFAULT_VIEWER_PORT = 3245
# How long the launcher waits for the port's holder to say who it is. A viewer answers
# `/__cad/server` in a millisecond; the margin is for one busy with a large drawing.
PROBE_SECONDS = 1.0
# How long a viewer asked to exit (`POST /__cad/shutdown`) has to give up its port.
SHUTDOWN_WAIT_SECONDS = 5.0

# EADDRINUSE/EACCES are the only "taken" signals. Windows raises WSAEADDRINUSE /
# WSAEACCES, which Python maps onto these same errnos.
_PORT_TAKEN_ERRNOS = frozenset({errno.EADDRINUSE, errno.EACCES})


def _out(text: str) -> None:
    """stdout, FLUSHED.

    Python block-buffers stdout when it is not a TTY, and the serve path never
    exits. Both the launcher test and the launch smoke test poll a LONG-LIVED
    process's redirected stdout for the ``{url,port,action}`` line, so an
    unflushed write is a hang, not a late line. The documented launch command
    carries neither ``-u`` nor ``PYTHONUNBUFFERED``, so this cannot be delegated
    to the environment.
    """
    sys.stdout.write(text)
    sys.stdout.flush()


def _err(text: str) -> None:
    sys.stderr.write(text)
    sys.stderr.flush()


def _compact_json(payload) -> str:
    # JSON.stringify emits no spaces. The launch smoke test greps for the
    # literal '"action":"reused"' and '"port":<n>', which Python's default
    # separators would break.
    return json.dumps(payload, separators=(",", ":"))


# argparse prefixes this with "usage: " itself.
USAGE = """{prog} [--host HOST] [--port N | --new] [--json] [--detach]
       {pad} [--dist DIR] [--api-only]
       {prog} stop [--port N]"""

DESCRIPTION = """The CAD Viewer: one local server for every CAD file on this machine, opened by
absolute path (`?file=/abs/part.step`), on port 3245 or the one --port names. A
launch reuses this user's viewer on that port, or replaces one running other code;
the folder a viewer starts in is only where a developer's relative `?file=` links
resolve.
"""

_HELP = {
    "host": "bind address (default: 127.0.0.1)",
    "port": "the port to serve on (default: 3245); this user's viewer on it is reused or replaced",
    "new": "bind an OS-assigned free port, and neither reuse nor replace anything",
    "json": "announce the instance as one JSON line on stdout",
    "detach": "run the server in the background: print its URL, then return",
    "dist": "built client to serve (default: the bundled client; env CADGEN_VIEWER_DIST)",
    "api_only": "serve only /__cad and /__tess_cache (a dev server owns the client)",
}


def _port_number(raw: str) -> int:
    """A TCP port, or an argparse error naming what was wrong.

    ``0`` is refused rather than read as "any port": that spelling is
    ``--new``, and a launcher that quietly turned ``--port 0`` into a
    strict 3245 (as an old hand-rolled parser did) was a trap.
    """
    try:
        value = int(raw, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a port number: {raw!r}") from None
    if not (0 < value <= 65535):
        raise argparse.ArgumentTypeError(f"port out of range (1-65535): {raw}")
    return value


class _Parser(argparse.ArgumentParser):
    """argparse with the launcher's refusal shape.

    An unknown argument is a REFUSAL, not a shrug: a misspelled flag that is
    ignored starts a viewer other than the one asked for, and looks fine.
    argparse refuses too, but names every stray token in one line —
    ``--dir /tmp`` would read as two problems. The FIRST unknown is the useful
    one, so ``parse`` below reports exactly that.
    """

    def error(self, message: str) -> None:  # noqa: D401 - argparse's contract
        _err(f"{self.prog}: {message}\n")
        _err(f"run `{self.prog} --help` for the arguments this launcher takes\n")
        raise SystemExit(2)

    def parse(self, argv: list[str]) -> argparse.Namespace:
        namespace, unknown = self.parse_known_args(argv)
        if unknown:
            self.error(f"unknown argument: {unknown[0]}")
        return namespace


def build_parser(prog: str = DEFAULT_PROG) -> argparse.ArgumentParser:
    parser = _Parser(
        prog=prog,
        usage=USAGE.format(prog=prog, pad=" " * len(prog)),
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("--host", default=DEFAULT_VIEWER_HOST, help=_HELP["host"])
    binding = parser.add_mutually_exclusive_group()
    binding.add_argument("--port", type=_port_number, default=None, metavar="N", help=_HELP["port"])
    binding.add_argument("--new", action="store_true", help=_HELP["new"])
    parser.add_argument("--json", action="store_true", help=_HELP["json"])
    parser.add_argument("--detach", action="store_true", help=_HELP["detach"])
    parser.add_argument("--dist", default="", metavar="DIR", help=_HELP["dist"])
    parser.add_argument("--api-only", dest="api_only", action="store_true", help=_HELP["api_only"])
    return parser


def parse_args(argv: list[str], *, prog: str = DEFAULT_PROG) -> dict:
    """The serve arguments as a dict; exits 2 (via argparse) on a refusal."""
    namespace = build_parser(prog).parse(list(argv))
    return {
        "host": namespace.host,
        # --new binds port 0: whatever the OS hands out.
        "port": 0 if namespace.new else (namespace.port or DEFAULT_VIEWER_PORT),
        "new": namespace.new,
        "dist": namespace.dist or "",
        "json": namespace.json,
        "detach": namespace.detach,
        "api_only": namespace.api_only,
    }


def resolve_dist_dir(explicit: str) -> str:
    """The built client to serve: ``--dist``, else ``cadgen.assets.viewer_dist_dir()``.

    That resolver is env ``CADGEN_VIEWER_DIST``, then a checkout's
    ``apps/web/dist``, then the packaged ``_runtime/viewer``. A candidate
    counts only with an ``index.html`` in it; ``""`` means nothing usable.
    """
    candidates = [c for c in (str(explicit or "").strip(), str(assets.viewer_dist_dir())) if c]
    for candidate in candidates:
        resolved = os.path.abspath(candidate)
        if os.path.exists(os.path.join(resolved, "index.html")):
            return resolved
    return ""


def port_is_free(host: str, port: int) -> bool:
    """True when this process can BIND host:port.

    The same operation the server is about to perform, so the probe cannot
    disagree with reality. A definite EADDRINUSE (or EACCES, Windows's answer
    for its excluded ranges) is taken; any OTHER failure counts as free,
    because the server's own bind stays authoritative.
    """
    probe = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    try:
        if not sys.platform.startswith("win"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, port))
        probe.listen(1)
        return True
    except OSError as error:
        return error.errno not in _PORT_TAKEN_ERRNOS
    finally:
        probe.close()


def warn_when_dist_is_stale(dist_dir: str) -> None:
    """One stderr line when the built client is older than the client sources.

    A DETECTION, never a refusal: startup stays unopinionated and the stale
    bundle still serves. This exists because a stale locally-built client
    manufactured a false bug report from a sibling project — a pose-preset
    "bug" that was just an old bundle — and nothing at startup said so.

    Structurally impossible in the wheel: the check looks for the app's
    ``src/`` tree BESIDE the served dist, which exists only in checkouts — the
    packaged client ships without sources, so there is nothing to compare and
    the walk never happens. The cost in a checkout is one mtime walk of src/
    and of dist/: a few hundred stats.
    """
    if not dist_dir:
        return
    src_dir = os.path.join(os.path.dirname(dist_dir), "src")
    if not os.path.isdir(src_dir):
        return  # the packaged client ships no sources: nothing to compare
    if newest_mtime_ns(src_dir) > newest_mtime_ns(dist_dir):
        _err("dist/ is older than the client sources — rebuild with `npm run build`\n")


# --- the port's holder ---------------------------------------------------


def _loopback(host: str) -> str:
    """Where a server bound to ``host`` is reached: a wildcard bind on loopback."""
    return DEFAULT_VIEWER_HOST if host in ("", "0.0.0.0", "::") else host


def _url(host: str, port: int, path: str) -> str:
    host = _loopback(host)
    return f"http://{f'[{host}]' if ':' in host else host}:{port}{path}"


def probe(host: str, port: int, timeout: float = PROBE_SECONDS) -> dict | None:
    """What answers ``GET /__cad/server`` on ``port``, or ``None`` when nothing answers it with an
    object: nothing listening, or a program that is not a viewer (the bind finds those)."""
    try:
        with urllib.request.urlopen(_url(host, port, "/__cad/server"), timeout=timeout) as response:  # noqa: S310 - loopback
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def is_own_viewer(info: dict | None) -> bool:
    """Whether ``info`` (a ``probe``) is a CAD Viewer this OS user runs: the only kind a launch
    reuses, replaces or stops."""
    return bool(info) and info.get("app") == "cad-viewer" and info.get("user") == os_user()


def request_shutdown(host: str, port: int, *, wait: float = SHUTDOWN_WAIT_SECONDS) -> bool:
    """Ask the viewer on ``port`` to exit (``POST /__cad/shutdown``), then wait, at most ``wait``
    seconds, for the port to be free. Whether it is."""
    request = urllib.request.Request(
        _url(host, port, "/__cad/shutdown"), data=b"", method="POST", headers={POST_GUARD_HEADER: "1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=PROBE_SECONDS) as response:  # noqa: S310 - loopback
            if response.status != 202:
                return False
    except (urllib.error.URLError, OSError, ValueError):
        return False
    deadline = time.monotonic() + wait
    while not port_is_free(host, port):  # the very bind a launch on ``host`` performs
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _take_port(host: str, port: int, token: str) -> tuple[str, dict | None]:
    """What this launch does about ``port``: ``("reuse", info)`` for this user's viewer at this
    identity; ``("bind", None)`` when it binds the port itself -- nothing holds it, the holder is
    not this user's viewer (the bind refuses those), or this user's viewer running other code has
    just exited; ``("stuck", info)`` for one of those that would not exit."""
    info = probe(host, port)
    if not is_own_viewer(info):
        return "bind", None
    if str(info.get("identityToken") or "") == str(token or ""):
        return "reuse", info
    # This user's viewer, running other code: the newest wins.
    return ("bind", None) if request_shutdown(host, port) else ("stuck", info)


# --- stop ----------------------------------------------------------------


def build_stop_parser(prog: str = f"{DEFAULT_PROG} stop") -> argparse.ArgumentParser:
    parser = _Parser(prog=prog, description="Ask the CAD Viewer on a port to exit.", allow_abbrev=False)
    parser.add_argument("--port", type=_port_number, default=DEFAULT_VIEWER_PORT, metavar="N",
                        help="the port it serves on (default: 3245)")
    return parser


def stop_command(argv: list[str], *, prog: str = f"{DEFAULT_PROG} stop") -> int:
    """Ask the CAD Viewer on ``--port`` (3245) to exit, and wait for its port to be free.

    Only a viewer this OS user runs, as it says itself (``/__cad/server``): another program, or
    another user's viewer, is never asked.
    """
    port = build_stop_parser(prog).parse(list(argv)).port
    info = probe(DEFAULT_VIEWER_HOST, port)
    if not info or info.get("app") != "cad-viewer":
        _err(f"No CAD Viewer is running on port {port}.\n")
        return 1
    if not is_own_viewer(info):
        _err(f"The CAD Viewer on port {port} is another user's.\n")
        return 1
    if not request_shutdown(DEFAULT_VIEWER_HOST, port):
        _err(f"The CAD Viewer on port {port} (pid {info.get('pid')}) did not exit within {SHUTDOWN_WAIT_SECONDS:.0f}s.\n")
        return 1
    _out(f"Stopped CAD Viewer on port {port} (pid {info.get('pid')}).\n")
    return 0


# --- serve ---------------------------------------------------------------


class _LateApp:
    """Stand-in so the socket can be bound before the app knows its port.

    ``serverInfo`` must name the port actually taken, which is only known after
    the bind — so the bind comes first and the real app is attached the instant
    it succeeds, before ``serve_forever`` accepts anything. Nothing can reach
    this; answering 503 rather than raising keeps a freak race diagnosable
    instead of turning it into a stack trace.
    """

    def handle(self, request, response) -> None:  # noqa: ARG002
        response.send_json(503, {"ok": False, "error": "server starting"})


def _prewarm_daemon() -> None:
    """Start the build daemon. Best-effort: without one, the viewer serves what it did."""
    from cadgen.daemon.client import prewarm  # noqa: PLC0415 - kernel-free, needed only now

    try:
        prewarm()
    except Exception:  # noqa: BLE001 - a daemon that cannot start is the first build's to report
        pass


def _harden_streams() -> None:
    """Degrade an unencodable character to an escape instead of raising.

    The same treatment every other cadgen entry point gets, and for the same
    reason: Windows hands a process the legacy code page, and under strict
    error handling a character it cannot represent raises UnicodeEncodeError
    from the MESSAGE rather than from the work. The viewer's narration carries
    em dashes (the dist-staleness warning) and, worse, arbitrary user paths.

    Only the error HANDLER changes, never the encoding — switching the viewer's
    streams to utf-8 would make it emit bytes that no Windows consumer decodes
    the way the platform says to, which is the experiment
    ``cli._harden_std_stream_errors`` documents having tried and reverted.

    Reached from BOTH entry points: ``cadgen viewer`` arrives already hardened
    through ``cadgen.cli.main``, but ``python -m cadgen.viewer`` does not — and
    neither does the process a development restart re-executes, which is spelled
    exactly that way.
    """
    from cadgen.cli import _harden_std_stream_errors  # noqa: PLC0415

    _harden_std_stream_errors()


def main(argv: list[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    """``python -m cadgen.viewer``: serve, or ``stop`` when argv[0] says so.

    Only argv[0] is inspected, so ``--json stop`` is a SERVE invocation with an
    unknown arg, not a stop. The ``cadgen`` front door reaches the two verbs
    through ``cadgen.cli.viewer`` and ``viewer_stop`` instead, which call
    :func:`serve` and :func:`stop_command`.
    """
    _harden_streams()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "stop":
        return stop_command(argv[1:], prog=f"{prog} stop")
    return serve(argv, prog=prog)


# --- detach --------------------------------------------------------------

# How long a --detach launch waits for its server to announce itself. A launch
# takes well under a second; this bounds a wedged child, not a normal one.
DETACH_READY_TIMEOUT_SECONDS = 120.0
_DETACH_POLL_SECONDS = 0.02


def log_path() -> str:
    """Where a detached viewer's output goes: one file in the state directory (the temporary
    directory where that cannot be made), so it is found without asking anyone."""
    from .recents import state_dir  # noqa: PLC0415 - the state directory's one definition

    try:
        directory = state_dir()
        directory.mkdir(parents=True, exist_ok=True)
        return str(directory / "viewer.log")
    except OSError:
        return os.path.join(tempfile.gettempdir(), "cadgen-viewer.log")


def _announcement(line: str) -> dict | None:
    """The ``{url,port,action}`` line, parsed, or ``None`` for any other line."""
    if not line.startswith("{"):
        return None
    try:
        payload = json.loads(line)
    except ValueError:
        return None
    if isinstance(payload, dict) and {"url", "port", "action"} <= set(payload):
        return payload
    return None


def _read_lines(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()
    except OSError:
        return []


def launch_detached(argv: list[str], *, as_json: bool, prog: str = DEFAULT_PROG) -> int:
    """``--detach``: start the same launch as a background process, relay its
    announcement, and RETURN.

    Without it the launcher that starts a server IS that server and stays in
    the foreground until it is stopped — right for a person at a terminal and
    for ``npm run dev``, wrong for an agent's shell, which waits for the
    command to finish (and for ``… | tail -1``, which waits for an EOF that
    never comes). With it, both outcomes behave alike: a reused instance and a
    started one each print their lines and exit 0. A reuse that the launcher
    found itself never gets here (``serve``).

    The child is the ordinary foreground launch — the same arguments minus
    ``--detach``, plus ``--json`` — in its own session (its own process group
    on Windows), so closing the terminal or the agent's shell does not take it
    down. Its stdout and stderr go to the viewer log (``log_path``), started
    afresh, never to a pipe: this process exits, and a server writing into a
    pipe nobody reads would fail on its next line. The log outlives the server,
    so a crash can be read afterwards, until the next detached start. Readiness
    is the child's own announcement, which it writes only once it is bound and
    attached, so the URL printed here answers its first request.
    """
    child_argv = [item for item in argv if item != "--detach"]
    if "--json" not in child_argv:
        child_argv.append("--json")
    popen_options: dict = {}
    if sys.platform.startswith("win"):
        popen_options["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_options["start_new_session"] = True
    log_file = log_path()
    try:
        with open(log_file, "wb") as log:
            child = subprocess.Popen(  # noqa: S603 - our own interpreter, our own module
                [sys.executable, "-m", "cadgen.viewer", *child_argv],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                close_fds=True,
                **popen_options,
            )
    except OSError as error:
        _err(f"CAD Viewer could not start in the background: {error}\n")
        return 1

    deadline = time.monotonic() + DETACH_READY_TIMEOUT_SECONDS
    announced = None
    timed_out = False
    while True:
        exited = child.poll() is not None
        lines = _read_lines(log_file)
        announced = next((payload for payload in map(_announcement, lines) if payload), None)
        if announced is not None or exited:
            break
        if time.monotonic() >= deadline:
            child.kill()
            child.wait()
            timed_out = True
            lines = _read_lines(log_file)
            lines.append(f"(no announcement within {int(DETACH_READY_TIMEOUT_SECONDS)}s; stopped it)")
            break
        time.sleep(_DETACH_POLL_SECONDS)

    if announced is None:
        for line in lines:
            _err(f"{line}\n")
        # The child's own refusal code (1, or 2 for its argument grammar) is
        # the answer. A child this launcher killed, or one a signal took, has a
        # negative status that would wrap to a meaningless exit (-9 -> 247).
        code = child.returncode
        return code if not timed_out and code is not None and code > 0 else 1

    say = _err if as_json else _out
    for line in lines:
        if _announcement(line) is None:
            say(f"{line}\n")
    if announced.get("action") == "started":
        say(
            f"Running in the background (pid {child.pid}); its output goes to {log_file}. "
            f"Stop it with `{prog} stop --port {announced['port']}`.\n"
        )
    else:
        child.wait()
    if as_json:
        _out(f"{_compact_json({key: announced[key] for key in ('url', 'port', 'action')})}\n")
    return 0


def serve(argv: list[str], *, prog: str = DEFAULT_PROG) -> int:
    _harden_streams()
    # argparse answers --help on stdout with exit 0 and refuses an unknown
    # argument with exit 2, both before anything below runs. A launcher that
    # answered --help by starting a server read as broken.
    args = parse_args(argv, prog=prog)
    host, port = args["host"], args["port"]

    # --api-only exempts the check because in dev the CLIENT COMES FROM VITE:
    # this process serves only /__cad and /__tess_cache, and requiring a built
    # dist made `npm run dev` fail on any checkout that had not run
    # `npm run build` first — dist/ is gitignored, so that is every fresh
    # clone. The dist routes still answer 404 in that mode, which is what they
    # already do for an empty dist_dir.
    dist_dir = "" if args["api_only"] else resolve_dist_dir(args["dist"])
    if not dist_dir and not args["api_only"]:
        _err(
            "No built CAD Viewer client found. This cadgen was installed without one; "
            "in a checkout, build it with `npm run build` in apps/web, or point "
            "--dist (or CADGEN_VIEWER_DIST) at a dist directory. "
            "(--api-only serves the API alone, for a dev server that supplies its own client.)\n"
        )
        return 1

    # Ask the port who holds it, with the exact runtime requested now. Resolving dist before this
    # is load-bearing: --dist must never hand back a server serving a different client, and a
    # removed default dist is not a usable resident merely because its server is still alive.
    token = identity_token(dist_dir)
    if not args["new"]:
        action, held = _take_port(host, port, token)
        if action == "stuck":
            _err(
                f"The CAD Viewer on port {port} (pid {held.get('pid')}) runs other code and did not exit; "
                f"stop it with `{prog} stop --port {port}`, or start this one with --port N.\n"
            )
            return 1
        if action == "reuse":
            url = f"http://{host}:{port}/"
            # The same stream rule as a start: under --json, stdout is the one
            # JSON line in BOTH outcomes, so no reader needs "the last line".
            say = _err if args["json"] else _out
            say(f"Reusing CAD Viewer at {url} (pid {held.get('pid')}, started in {held.get('start')})\n")
            say(f"CAD Viewer URL: {url}\n")
            if args["json"]:
                _out(f"{_compact_json({'url': url, 'port': port, 'action': 'reused'})}\n")
            return 0

    if args["detach"]:
        return launch_detached(argv, as_json=args["json"], prog=prog)

    warn_when_dist_is_stale(dist_dir)

    try:
        placeholder = _LateApp()
        server = CadHTTPServer((host, port), make_handler_class(placeholder), placeholder)
    except OSError as error:
        if error.errno in _PORT_TAKEN_ERRNOS:
            _err(
                f"Port {port} is in use by another program (or another user's CAD Viewer); "
                f"start the viewer with --port N.\n"
            )
            return 1
        _err(f"{error}\n")
        return 1
    port = server.server_address[1]

    # Attach the real app in the same breath as the successful bind: the socket
    # is listening but serve_forever has not accepted anything, so no request
    # can be dropped in the gap, and serverInfo names the port actually taken.
    app = create_cad_app(host=host, port=port, dist_dir=dist_dir, identity=token)
    server.app = app
    server.RequestHandlerClass = make_handler_class(app)

    # Anonymous usage analytics, sent only with consent (``cadgen/analytics.py``): this process's
    # recorder, which the page asks about and reports to (``/__cad/analytics``). It never raises,
    # and no request waits on it.
    from cadgen.analytics import Recorder  # noqa: PLC0415

    analytics = Recorder()
    analytics.started(client={"name": "cadgen-viewer", "version": app.viewer_version}, presentation="browser")
    analytics.start()
    app.analytics = analytics
    # Whether a newer text-to-cad is out (``cadgen/updates.py``, ``/__cad/version``): the feed is read
    # now when it is due, so the page's first question is answered from it.
    from cadgen import updates  # noqa: PLC0415

    updates.refresh()

    def shutdown(_signum=None, _frame=None):
        # shutdown() blocks until serve_forever returns, and calling it from a
        # signal handler running ON the serving thread deadlocks. Dispatch it.
        threading.Thread(target=server.shutdown, daemon=True).start()
        # Hard-exit fallback: a launch waiting for the port waits a few seconds,
        # and an in-flight stream must not outlive that.
        timer = threading.Timer(0.5, os._exit, (0,))
        timer.daemon = True
        timer.start()

    # `POST /__cad/shutdown`: a newer launch replacing this one, or `stop`.
    app.on_shutdown = shutdown

    url = f"http://{host}:{port}/"
    started = "Starting CAD Viewer API" if args["api_only"] else "Starting CAD Viewer"
    # Like every other --json verb: stdout carries the one JSON line and nothing
    # else; the narration goes to stderr. Without --json the narration is the
    # stdout contract (the URL line is what launch scripts read).
    say = _err if args["json"] else _out
    say(f"{started} at {url} from {app.start}\n")
    say(f"CAD Viewer URL: {url}\n")
    if args["json"]:
        _out(f"{_compact_json({'url': url, 'port': port, 'action': 'started'})}\n")

    # Start the build daemon, whose workers import build123d while nobody waits: the
    # session's first build, or the viewer's first STEP import, otherwise pays for it.
    # After the announcement, never before it: the URL line is the readiness signal
    # and waits for nothing. The viewer never builds anything itself; this only warms
    # what will.
    threading.Thread(target=_prewarm_daemon, name="cadgen-viewer-prewarm", daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Development auto-reload. Only a cadgen running from a source CHECKOUT
    # watches its own Python and comes back on this same port; an installed
    # wheel never starts a watcher at all. The whole mechanism, and the one
    # predicate that gates it, is `reload.py`.
    reloader = None
    restart = {"argv": None}
    if app.auto_reload:
        def request_restart() -> None:
            restart["argv"] = dev_reload.restart_argv(argv, port=port)
            _err(f"code changed; restarting on port {port}\n")
            # From the watcher thread: shutdown() blocks until serve_forever
            # returns, and the exec happens below, on the main thread, with the
            # accept loop already stopped.
            server.shutdown()

        reloader = dev_reload.SourceReloader(
            is_idle=app.restart_is_safe, restart=request_restart
        )
        reloader.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if reloader is not None:
            reloader.stop()
        if restart["argv"] is None:
            server.server_close()  # the port is free now: a launch waiting for it starts at once
        analytics.close()  # the last send, waited for at most a couple of seconds

    if restart["argv"] is not None:
        # Returns only when the re-exec itself failed, and then the port is
        # already given up: say so and exit non-zero rather than pretending to
        # still serve.
        _restart_in_place(server, app, restart["argv"], prog=prog)
        return 1
    return 0


def _restart_in_place(server, app, argv: list[str], *, prog: str) -> None:
    """Free the port, then become the new code. Returns only if that failed.

    ``serve_forever`` has already stopped accepting, but its handler threads are
    daemons: the reloader only fires when nothing is counted in flight, and this
    drain covers the sliver between that check and the close. Then the listening
    socket is closed BEFORE the new image binds — a clean close-then-bind is
    enough because the restart pins the port explicitly, and finds it free.
    """
    deadline = time.monotonic() + 2.0
    while app.busy_requests() and time.monotonic() < deadline:
        time.sleep(0.02)
    server.server_close()
    try:
        dev_reload.execute_restart(argv)
    except OSError as error:
        _err(
            f"CAD Viewer could not restart itself ({error}) and has given up its port. "
            f"Run `{prog}` again to pick up the new code.\n"
        )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], prog="python -m cadgen.viewer"))
