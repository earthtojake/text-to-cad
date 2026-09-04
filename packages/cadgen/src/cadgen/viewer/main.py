"""Single-port CAD Viewer server and instance manager: ``cadgen viewer``.

Launching is UNCONDITIONAL, Jupyter-style: running ``cadgen viewer`` from a
directory always ends with the URL of a live, correct Viewer for that directory.
If an identity-probed instance already serves ``realpath(cwd)`` at this identity
token (version salted with the code's newest mtime — see ``identity_token``),
its URL is printed with ``action:"reused"`` and nothing is spawned (``--new``
skips the lookup); otherwise the server binds the first free port from 3245
upward and prints ``action:"started"``. An EXPLICIT ``--port`` stays strict — it
exits 1 when taken — because then the port was the ask. The printed URL (and the
``--json {url,port,action}`` line) is the contract; the port is an output of
launch, never something the caller reasons about.

Also the instance manager: ``cadgen viewer list [--json]`` shows every running
Viewer (identity-probed, stale entries reaped) and ``cadgen viewer stop --port
<n>`` / ``--pid <n>`` terminates one. These live here rather than in a separate
tool because the registry the server writes is the only source of truth. Dev
never registers (``--no-registry``): the registry is installed instances only.

Three flags exist for the dev server and nowhere else: ``--ephemeral`` (bind any
free port), ``--no-registry`` (stay out of reuse), and ``--api-only`` (serve the
two API prefixes and nothing else, because Vite owns the client — this is what
lets ``npm run dev`` work on a checkout that has never been built).

A Viewer serves ONE directory: the one it is launched from. There is no flag
for it — the cwd IS the served directory, so the caller chooses what to serve
by choosing where to run. The page is always the bare origin; ``?file=``
selects a file inside that directory. To serve a second directory, just launch
again from it.

Launch is::

    cd <the directory to serve>
    cadgen viewer            # or: python -m cadgen.viewer

There is no interpreter discovery, and deliberately so: an earlier backend
searched ``$CADGEN_PYTHON``, ``PATH``, and ``<servedRoot>/.venv/bin/python``,
which meant OPENING AN UNTRUSTED FOLDER THAT SHIPS A .venv handed it the
interpreter to execute. The server IS the interpreter that installed cadgen.
Do not reintroduce a search in any form.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

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

from . import registry  # noqa: E402
from .handler import CadHTTPServer, make_handler_class  # noqa: E402
from .http_app import create_cad_app, identity_token, newest_mtime_ns  # noqa: E402

DEFAULT_PROG = "cadgen viewer"
DEFAULT_VIEWER_HOST = "127.0.0.1"
DEFAULT_VIEWER_PORT = 3245
# How far past the default the launcher will roll looking for a free port
# before giving up. Far beyond any plausible number of live Viewers.
PORT_ROLL_LIMIT = 100
STOP_WAIT_SECONDS = 3.0

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
USAGE = """{prog} [--host HOST] [--port N | --ephemeral] [--new] [--json]
       {pad} [--dist DIR] [--api-only] [--no-registry]
       {prog} list [--json]
       {prog} stop (--port N | --pid N)"""

DESCRIPTION = """Serve ONE directory of CAD artifacts: the directory you run it from. There is
no flag for it — cd there first. The page is the bare origin; `?file=` selects
an artifact inside that directory.
"""

_HELP = {
    "host": "bind address (default: 127.0.0.1)",
    "port": (
        "strict: this port or fail. Default rolls from 3245 upward and reuses a "
        "live viewer already serving this directory."
    ),
    "ephemeral": "bind an OS-assigned port; never reuse, never register",
    "new": "start a fresh instance instead of reusing a live one",
    "json": "announce the instance as one JSON line on stdout",
    "dist": "built client to serve (default: the bundled client; env CADGEN_VIEWER_DIST)",
    "api_only": "serve only /__cad and /__tess_cache (a dev server owns the client)",
    "no_registry": "do not record this instance for `list`/`stop`/reuse",
}


def _port_number(raw: str) -> int:
    """A TCP port, or an argparse error naming what was wrong.

    ``0`` is refused rather than read as "any port": that spelling is
    ``--ephemeral``, and a launcher that quietly turned ``--port 0`` into a
    strict 3245 (as the old hand-rolled parser did) was a trap.
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

    An unknown argument is a REFUSAL, not a shrug: a misspelled flag once started
    a viewer on the wrong directory and served an empty catalog while looking
    fine. argparse refuses too, but names every stray token in one line —
    ``--dir /tmp`` would read as two problems. The FIRST unknown is the useful
    one, so ``parse`` below reports exactly that. This also catches the retired
    ``--root <dir>``: the served directory is the cwd now.
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
    # Explicit --port means "this port or fail"; the default (None) means "any
    # free port from the base" and enables the reuse lookup + roll.
    binding = parser.add_mutually_exclusive_group()
    binding.add_argument("--port", type=_port_number, default=None, metavar="N", help=_HELP["port"])
    binding.add_argument("--ephemeral", action="store_true", help=_HELP["ephemeral"])
    parser.add_argument("--new", dest="fresh", action="store_true", help=_HELP["new"])
    parser.add_argument("--json", action="store_true", help=_HELP["json"])
    parser.add_argument("--dist", default="", metavar="DIR", help=_HELP["dist"])
    parser.add_argument("--api-only", dest="api_only", action="store_true", help=_HELP["api_only"])
    parser.add_argument("--no-registry", dest="no_registry", action="store_true", help=_HELP["no_registry"])
    return parser


def parse_args(argv: list[str], *, prog: str = DEFAULT_PROG) -> dict:
    """The serve arguments as a dict; exits 2 (via argparse) on a refusal."""
    namespace = build_parser(prog).parse(list(argv))
    return {
        "host": namespace.host,
        "port": namespace.port if namespace.port is not None else DEFAULT_VIEWER_PORT,
        "port_explicit": namespace.port is not None,
        "dist": namespace.dist or "",
        "json": namespace.json,
        "fresh": namespace.fresh,
        # Additive flags, all three for dev (see the client's vite.config.mjs).
        "ephemeral": namespace.ephemeral,
        "no_registry": namespace.no_registry,
        "api_only": namespace.api_only,
    }


def served_directory() -> str:
    """The directory this Viewer serves: the cwd, full stop.

    No flag, no environment variable, no special cases. Serving the app's own
    directory is a legitimate thing to ask for — it is how you look at the
    Viewer's own fixtures — so nothing here has opinions about where you stand.
    Callers choose what to serve by choosing where to launch; the cad-viewer
    skill instructs exactly that (cd into the model workspace first).

    ``os.getcwd()`` can fail: a cwd deleted underneath the shell raises
    ``FileNotFoundError``. That is surfaced as a clean refusal by ``main`` —
    booting a viewer for a directory that no longer exists would answer every
    request with a 404 that looks like a missing model rather than a missing
    directory.
    """
    return os.path.abspath(os.getcwd())


def resolve_dist_dir(explicit: str) -> str:
    """The built client to serve: ``--dist``, else ``cadgen.assets.viewer_dist_dir()``.

    That resolver is env ``CADGEN_VIEWER_DIST``, then a checkout's
    ``apps/viewer/dist``, then the packaged ``_runtime/viewer``. A candidate
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
    disagree with reality. This used to probe by CONNECTING, with only
    ECONNREFUSED counting as free; on Windows a connect to a closed port
    routinely fails some other way (Hyper-V/WSL port exclusions, loopback
    filtering, refusals arriving as timeouts), so free ports read as occupied.
    A definite EADDRINUSE (or EACCES, Windows's answer for its excluded ranges)
    keeps the friendly rerun-without---port message; any OTHER failure counts as
    free, because this probe exists only for that message — the server's own
    bind stays authoritative.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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

    Structurally impossible in a published bundle: the check looks for the
    app's ``src/`` tree BESIDE the served dist, which exists only in checkouts
    — the skill bundle and the mirrored repo ship ``dist/`` without sources,
    so there is nothing to compare and the walk never happens. The cost in a
    checkout is one mtime walk of src/ (~150 files, well under a millisecond).
    """
    if not dist_dir:
        return
    src_dir = os.path.join(os.path.dirname(dist_dir), "src")
    if not os.path.isdir(src_dir):
        return  # published bundles ship no client sources: nothing to compare
    if newest_mtime_ns(src_dir) > newest_mtime_ns(dist_dir):
        _err("dist/ is older than the client sources — rebuild with `npm run build`\n")


def _realpath_or(candidate) -> str:
    try:
        return os.path.realpath(str(candidate or ""), strict=True)
    except OSError:
        return str(candidate or "")


def find_reusable(directory: str, token: str) -> dict | None:
    """The reuse key: realpath(root) x identity token, over identity-probed entries.

    Never port, never pid — keying on the port was the old source-blind reuse
    bug, and pid-liveness is the probe's job. Dev instances never register, so
    nothing here can hand back a Vite proxy target.

    The token is the version SALTED with the app files' newest mtime (see
    ``identity_token`` in http_app.py). The entry's token was recorded when
    that instance STARTED, so an instance running last week's code — the
    version number is frozen between releases — fails the match after a
    ``git pull`` or rebuild, and a fresh launch starts fresh instead of
    reusing stale resident code.
    """
    root_real = _realpath_or(directory)
    for entry in registry.live_entries():  # probes pids, reaps stale files
        if _realpath_or(entry.get("root")) == root_real and str(entry.get("token") or "") == str(
            token or ""
        ):
            return entry
    return None


# --- list / stop ---------------------------------------------------------


def _format_age(started_at) -> str:
    if not started_at:
        return ""
    seconds = max(0, int(time.time() - started_at))
    if seconds >= 3600:
        return f"  up {seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"  up {seconds // 60}m"


def _format_entry(entry: dict) -> str:
    url = f"http://{entry.get('host') or '127.0.0.1'}:{entry.get('port')}/"
    return (
        f"  port {entry.get('port')}  pid {entry.get('pid')}  "
        f"viewer {entry.get('version') or '?'}{_format_age(entry.get('startedAt'))}\n"
        f"    {url}\n"
        f"    serving  {entry.get('root') or '?'}\n"
        f"    code     {entry.get('packageDir') or '?'}"
    )


def build_list_parser(prog: str = f"{DEFAULT_PROG} list") -> argparse.ArgumentParser:
    parser = _Parser(prog=prog, description="Show running CAD Viewers and what each serves.", allow_abbrev=False)
    parser.add_argument("--json", action="store_true", help="print the registry entries as JSON")
    return parser


def list_command(argv: list[str], *, prog: str = f"{DEFAULT_PROG} list") -> int:
    """What CAD Viewers are running, and whose code answers each port.

    A viewer serves one directory fixed at startup, so instances differ both by
    what they serve and by WHICH INSTALL'S CODE holds the port.
    """
    as_json = build_list_parser(prog).parse(list(argv)).json
    entries = registry.live_entries()  # also reaps anything that fails its identity probe
    if as_json:
        _out(f"{_compact_json(entries)}\n")
        return 0
    if not entries:
        _out("No CAD Viewer is running.\n")
        return 0
    _out(f"{len(entries)} CAD Viewer{'' if len(entries) == 1 else 's'} running:\n")
    for entry in entries:
        _out(f"{_format_entry(entry)}\n")
    return 0


def build_stop_parser(prog: str = f"{DEFAULT_PROG} stop") -> argparse.ArgumentParser:
    parser = _Parser(prog=prog, description="Terminate a running CAD Viewer.", allow_abbrev=False)
    which = parser.add_mutually_exclusive_group()
    which.add_argument("--port", type=int, default=None, metavar="N", help="the viewer answering this port")
    which.add_argument("--pid", type=int, default=None, metavar="N", help="the viewer with this process id")
    return parser


def stop_command(argv: list[str], *, prog: str = f"{DEFAULT_PROG} stop") -> int:
    """Terminate a running CAD Viewer.

    Only ever signals a process the registry can still identify: ``live_entries``
    probes each recorded port and requires the answering pid to match.
    """
    selected = build_stop_parser(prog).parse(list(argv))
    port = selected.port
    pid = selected.pid
    if not port and not pid:
        _err("Specify which viewer to stop: --port <n> or --pid <n>.\n")
        return 2
    entries = registry.live_entries()
    described = f"port {port}" if port else f"pid {pid}"
    target = None
    for entry in entries:
        if (entry.get("port") == int(port)) if port else (entry.get("pid") == int(pid)):
            target = entry
            break
    if not target:
        _err(f"No running CAD Viewer for {described}.\n")
        return 1
    try:
        os.kill(int(target["pid"]), signal.SIGTERM)
    except OSError as error:
        _err(f"Could not stop pid {target['pid']}: {error}\n")
        return 1
    deadline = time.monotonic() + STOP_WAIT_SECONDS
    while time.monotonic() < deadline:
        if not registry.probe(target, 0.25):
            # Unregister from the CALLER side. On Windows os.kill(SIGTERM) maps
            # to TerminateProcess: no signal handler runs and no atexit fires,
            # so this is the only thing that removes the entry.
            registry.unregister(target["pid"])
            _out(f"Stopped CAD Viewer on port {target['port']} (pid {target['pid']}).\n")
            return 0
        time.sleep(0.1)
    _err(f"CAD Viewer pid {target['pid']} did not exit within {int(STOP_WAIT_SECONDS)}s.\n")
    return 1


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


def _bind(host: str, port: int, args: dict) -> CadHTTPServer:
    """Bind, rolling by BINDING rather than pre-probing.

    The bind is the only check that cannot disagree with reality, and a lost
    race just moves to the next candidate. Explicit ``--port`` gets a single
    attempt; ``--ephemeral`` binds port 0 and reports what the OS gave.
    """
    placeholder = _LateApp()
    if args["ephemeral"]:
        return CadHTTPServer((host, 0), make_handler_class(placeholder), placeholder)
    last_candidate = port if args["port_explicit"] else port + PORT_ROLL_LIMIT
    while True:
        try:
            return CadHTTPServer((host, port), make_handler_class(placeholder), placeholder)
        except OSError as error:
            taken = error.errno in _PORT_TAKEN_ERRNOS
            if not taken or args["port_explicit"] or port >= last_candidate:
                raise
            port += 1


def main(argv: list[str] | None = None, *, prog: str = DEFAULT_PROG) -> int:
    """``python -m cadgen.viewer``: serve, or ``list``/``stop`` when argv[0] says so.

    Only argv[0] is inspected, so ``--json list`` is a SERVE invocation with an
    unknown arg, not a list. The ``cadgen`` front door reaches the three verbs
    through ``cadgen.cli.viewer``, ``viewer_list`` and ``viewer_stop`` instead,
    which call :func:`serve`, :func:`list_command` and :func:`stop_command`.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "list":
        return list_command(argv[1:], prog=f"{prog} list")
    if argv and argv[0] == "stop":
        return stop_command(argv[1:], prog=f"{prog} stop")
    return serve(argv, prog=prog)


def serve(argv: list[str], *, prog: str = DEFAULT_PROG) -> int:
    # argparse answers --help on stdout with exit 0 and refuses an unknown
    # argument with exit 2, both before anything below runs. A launcher that
    # answered --help by starting a server read as broken.
    args = parse_args(argv, prog=prog)

    try:
        directory = served_directory()
    except OSError as error:
        # A cwd deleted underneath the shell. Booting a viewer for a directory
        # that no longer exists would answer every request with a 404 that
        # looks like a missing model rather than a missing directory.
        _err(f"CAD Viewer cannot serve the current directory — it no longer exists ({error}).\n")
        return 1

    # Reuse before spawn: a live, identity-probed instance already serving this
    # realpath(root) at this identity token IS the requested viewer. Explicit
    # --port opts out (you asked for a port, not a viewer), --new forces fresh.
    # Ephemeral dev backends never reuse and never register.
    if not args["fresh"] and not args["port_explicit"] and not args["ephemeral"]:
        held = find_reusable(directory, identity_token())
        if held:
            url = f"http://{held.get('host') or DEFAULT_VIEWER_HOST}:{held['port']}/"
            _out(f"Reusing CAD Viewer at {url} (serving {held.get('root')}, pid {held['pid']})\n")
            _out(f"CAD Viewer URL: {url}\n")
            if args["json"]:
                _out(f"{_compact_json({'url': url, 'port': held['port'], 'action': 'reused'})}\n")
            return 0

    # Checked AFTER the reuse lookup, so a reuse succeeds with no client on disk.
    #
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
            "in a checkout, build it with `npm run build` in apps/viewer, or point "
            "--dist (or CADGEN_VIEWER_DIST) at a dist directory. "
            "(--api-only serves the API alone, for a dev server that supplies its own client.)\n"
        )
        return 1

    host = args["host"]
    port = args["port"]
    if args["port_explicit"]:
        # An explicit port is a demand, not a preference: refuse when taken, and
        # say who has it so the collision is diagnosable.
        if not port_is_free(host, port):
            holder = registry.find_by_port(port)
            if holder:
                _err(
                    f"Port {port} on {host} is already serving a CAD Viewer: "
                    f"pid {holder.get('pid')}, viewer {holder.get('version') or '?'}, "
                    f"from {holder.get('packageDir') or '?'}.\n"
                    f"Stop it with `{prog} stop --port {port}`, "
                    f"or rerun without --port to take any free port.\n"
                )
            else:
                _err(f"Port {port} on {host} is already in use. Rerun without --port to take any free port.\n")
            return 1

    warn_when_dist_is_stale(dist_dir)

    try:
        server = _bind(host, port, args)
    except OSError as error:
        _err(f"{error}\n")
        return 1
    port = server.server_address[1]

    # Attach the real app in the same breath as the successful bind: the socket
    # is listening but serve_forever has not accepted anything, so no request
    # can be dropped in the gap, and serverInfo names the port actually taken.
    app = create_cad_app(root=directory, host=host, port=port, dist_dir=dist_dir)
    server.app = app
    server.RequestHandlerClass = make_handler_class(app)

    url = f"http://{host}:{port}/"
    started = "Starting CAD Viewer API" if args["api_only"] else "Starting CAD Viewer"
    # Like every other --json verb: stdout carries the one JSON line and nothing
    # else; the narration goes to stderr. Without --json the narration is the
    # stdout contract (the URL line is what launch scripts read).
    say = _err if args["json"] else _out
    say(f"{started} at {url} (serving {directory})\n")
    say(f"CAD Viewer URL: {url}\n")
    if args["json"]:
        _out(f"{_compact_json({'url': url, 'port': port, 'action': 'started'})}\n")

    # Announce this instance so `main.py list` can find it — after the bind, so
    # we never advertise a port we failed to take. Dev skips it: a registered
    # dev backend would be REUSED by a later real launch on the same root,
    # handing an agent a URL served by Vite's proxy target.
    if not args["no_registry"]:
        # The token is the one the app computed AT ITS OWN START (CadApp
        # holds it), never re-read from disk here: a re-read would let a
        # stale resident claim freshness after a pull.
        registry.register(
            host=host,
            port=port,
            root=directory,
            viewer_version=app.viewer_version,
            token=app.identity_token,
        )

        import atexit  # noqa: PLC0415

        atexit.register(registry.unregister)

    def shutdown(_signum=None, _frame=None):
        if not args["no_registry"]:
            registry.unregister()
        # shutdown() blocks until serve_forever returns, and calling it from a
        # signal handler running ON the serving thread deadlocks. Dispatch it.
        threading.Thread(target=server.shutdown, daemon=True).start()
        # Hard-exit fallback: `stop` gives the process 3s, and an in-flight
        # stream must not outlive that.
        timer = threading.Timer(0.5, os._exit, (0,))
        timer.daemon = True
        timer.start()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if not args["no_registry"]:
            registry.unregister()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], prog="python -m cadgen.viewer"))
