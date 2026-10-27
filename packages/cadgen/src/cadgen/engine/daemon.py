"""The engine daemon: one per installation, started on demand, and never stopped by a timer: it
stops on ``cadgen stop`` (or a terminate), when a newer installation's engine retires it
(``bind``: only while nothing uses it), when its door is gone and no one can reach it (``tend``),
and with the machine. Idleness sheds memory instead.

It holds a pool of warm workers, one per model script (``Pool``), and hands each build to its
script's worker: one build at a time per worker, builds of different scripts at once, and at
most ``CADGEN_ENGINE_WORKERS`` workers alive (by default, the machine's cores). A build for a
script with a live worker waits for it while it is busy. One for a script with none starts one
when fewer than the cap are alive; at the cap the least recently used idle worker no page
watches is retired first (its stdin closed: it exits), and when every idle worker is watched the
new one starts past the cap; with every worker busy, the build waits, first come first served,
for the first to come free. Nothing is refused, and nothing is predicted: no admission.

No timer retires a worker: memory alone does (``Pool.shed``). The workers' resident memory --
each one's as it measured it at its start and after each build, the standby's and the render
processes' with them -- is held to one cap (``CADGEN_ENGINE_WORKER_RSS_MB``, ``worker.rss_cap_mb``).
Past it, or under the system's memory-pressure signal (``serve.Pressure``), idle processes are
retired, least recently used first: the standby, then render processes, then the workers no page
watches, and a watched one only when no other is left. A worker alone over the cap after its build
is retired at once (``worker.retirement``). Before a worker is stopped, every document
of it the server does not hold is taken from it (``models.Models.drain``): a document outlives its
worker. A retired script's next build is a fresh worker's, a restart. Each such document is also
kept in the engine's cache once it is idle, at its drain and at shutdown (``cache``), so a restart
of the daemon opens it at once.

One worker stands by with the kernel loaded (``Pool.stand``): started with the daemon, and again
each time a build takes it or starts a worker of its own while the pool has room for it. A build
for a script with no live worker takes the standby when its environment shapes the interpreter as
the standby's does (``RESTARTS``), and starts a fresh worker otherwise; taken, the standby is that
script's worker from then on (``Worker.adopt``), so a new script's first build pays no kernel load.
The standby counts toward the cap, is the first retired for room or memory, and is never a
script's worker in ``status``. ``CADGEN_ENGINE_STANDBY=0`` keeps none (``standby``): an operator's
seam for CI and machines short of memory.

It also serves documents over HTTP (``serve``), holding each loaded document and its
parts' tessellations in its memory under one budget (``serve.memory_budget``,
``CADGEN_ENGINE_MEMORY_MB``; past it, or on the system's memory-pressure signal, what is held
is evicted: ``serve.Server.trim``), and draws them (``draw``): each served document a
snapshot asks for gets a render process of its own (``render/service.py``), started on its
first picture, sent each new version of it at the picture that asks for it, gone with the daemon or under the
workers' memory cap; render processes are not workers, and do not count toward the count cap.

Its only files are the operating system's coordination, in its own folder, ``state_dir``: a lock,
and on POSIX its door, a named pipe (``door_path``), and the pipes of the connections being opened
(``door``: no socket, so a sandbox that refuses sockets still reaches it); on Windows a localhost
TCP port and a token, in a port file there. It removes them as it stops (``let_go``), and a daemon
starting removes those of every engine that died without (``sweep_dead``). Requests are one JSON object per line on a connection; answers
are JSON lines, the last of which carries ``done``, ``failed`` or ``ok``. Before it, a build
sends its caller its ``{"log"}`` lines and its ``{"progress"}`` frames as its worker sends them
(``progress.py``); the daemon keeps each busy worker's last frame for ``status``, and wakes the
pages waiting on a served document the frame's build writes (``serve.Server.building``).
"""

from __future__ import annotations

import collections
import functools
import hashlib
import itertools
import json
import os
import queue
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cadgen.engine.atomic_replace import replace_atomic
from cadgen.engine.ids import canonical, file_id, is_id

__all__ = ["DEFAULT_PORT", "Endpoint", "Pool", "PortHeld", "address", "door_path", "endpoints",
           "failure_path", "let_go", "lock", "lock_path", "main", "port_holder", "state_dir", "sweep_dead",
           "worker_cap"]

HTTP_FACTORY = None  # optional application supplied by the enclosing distribution

# How often the daemon tends itself (``Daemon.tend``): its door, its pipes, and the workers'
# memory against its cap. The server's pressure poller asks the system's signal more often.
TEND_SECONDS = 30.0
# Under the system's memory pressure, the workers' resident memory is brought down to this share of
# its cap, as the server's documents are of their budget (``serve.LOW_WATER``).
PRESSURE_SHARE = 0.5
# The standby's name where a worker's script would be (``Pool.stand``): it builds no script yet.
STANDBY = "standby"
# The engine's HTTP port when nothing names one (0xCAD): ``--port`` on ``cadgen server`` (or a
# request's own), then ``CADGEN_ENGINE_PORT``, then the installation's remembered port, then this
# (``bind``). Held by another program, the engine rolls to the next free port and remembers it.
DEFAULT_PORT = 3245
# A test suite's own "default" (``default_port``), so no test binds or rolls from the machine's 3245.
DEFAULT_PORT_ENV = "CADGEN_ENGINE_DEFAULT_PORT"
# How many ports past a held default (or remembered) one the engine tries before any free one.
PORTS_TRIED = 64
# How long the engine waits for another installation's engine it asked to stop to let its port go.
RETIRE_SECONDS = 10.0
# How long the engine waits for another installation's engine to answer what it is using.
ASK_SECONDS = 5.0
# The version an installation that cannot know its own name runs as (a development install's
# ``<version>-dev.<time>``, set by its launcher and the ``cadgen`` command): the name its records
# and its engine's ``status`` give it (``installation``). The engine reads the variable, never the
# distribution's module that sets it (law 3).
INSTALLATION_ENV = "CADGEN_INSTALLATION_VERSION"
PROTOCOL = 3  # 3: the door (named pipes) in place of the Unix socket
WINDOWS = os.name == "nt"
# The retirements ``status`` lists, the latest first.
RETIRED_KEPT = 12
# How long a build's worker is free, with no request waiting for it, before the documents the build
# made that an inspection has measured are read and measured again for the inspection after it
# (``serve.Server.measure_later``): a program calling its models one after another sends its next
# build within milliseconds of an answer, so those calls never wait on that read. The worker's own
# collection waits as long (``worker.COLLECT_IDLE``).
MEASURE_IDLE = 0.5
# What a worker's environment must share with a request's for the request to use it: what shapes
# the import system of the interpreter it started (the interpreter itself is the daemon's). A run
# adopts the rest of its caller's environment (``worker.adopt``), so a caller whose PATH changes
# from one run to the next (an agent's shell) keeps its warm worker and its memo.
RESTARTS = ("PYTHONPATH", "PYTHONHOME", "PYTHONSAFEPATH", "PYTHONNOUSERSITE", "PYTHONUSERBASE", "PYTHONPLATLIBDIR")
# How the engine's processes treat bytecode (``bytecode``): one of the two, never a run's to change.
BYTECODE = ("PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE")
# The folder of the engine's bytecode in the cache folder the distribution names (``registry``):
# one folder per installation in it (``_tag``), and one no daemon started in this many days goes.
PYCACHE = "pycache"
PYCACHE_UNUSED_DAYS = 30


def bytecode(env: dict[str, str]) -> dict[str, str]:
    """``env`` (the daemon's, or a worker's), its bytecode set as the engine's processes keep it:
    cached under ``pycache/`` in the cache folder (``PYTHONPYCACHEPREFIX``), so a worker's start
    imports the kernel's pure-Python libraries from bytecode (a uvx installation compiles nothing
    on install: every start compiled them, seconds each) and nothing is written beside a library
    or a model. A ``PYTHONPYCACHEPREFIX`` already given is honoured. A caller's
    ``PYTHONDONTWRITEBYTECODE`` is not: the daemon and its workers serve every later client, and
    write their bytecode in a folder of their own, ``pycache/<installation>`` (``_tag``). With no
    cache folder this user alone can write -- no distribution to name one, or one others can write
    to -- nothing is written: ``PYTHONDONTWRITEBYTECODE``. A model's own modules are compiled from
    their source whatever this says (``build._SourceOnlyLoader``)."""
    if not env.get("PYTHONPYCACHEPREFIX"):
        env.pop("PYTHONPYCACHEPREFIX", None)
        folder = _pycache()
        if folder is None:
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            return env
        env["PYTHONPYCACHEPREFIX"] = folder
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    return env


def _pycache() -> str | None:
    """This installation's folder under ``pycache/`` in the cache folder, made this user's alone and
    marked in use (its time); None where there is none to use."""
    from cadgen.engine import registry

    held = registry.current()
    if held is None or held.cache is None:
        return None
    root = Path(held.cache.root) / PYCACHE
    folder = root / _tag()
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.mkdir(exist_ok=True, mode=0o700)
        os.utime(folder)  # in use: ``_prune`` leaves it
    except OSError:
        return None
    if not WINDOWS and not (_users_own(str(root)) and _users_own(str(folder))):
        return None  # a folder another can write to would hand them the engine's code
    return str(folder)


def prune_bytecode() -> None:
    """The bytecode folders of installations no daemon started in ``PYCACHE_UNUSED_DAYS``, removed in
    the background, when the daemon caches its own (``bytecode``): never a caller's folder, which is
    not the engine's to judge."""
    ours = _pycache()
    if ours is None or os.path.realpath(sys.pycache_prefix or "") != os.path.realpath(ours):
        return
    threading.Thread(target=_prune, args=(Path(ours),), daemon=True).start()


def _prune(ours: Path) -> None:
    """The other installations' bytecode folders beside ``ours`` that no daemon started in
    ``PYCACHE_UNUSED_DAYS``: regenerable, and each a release's worth of libraries."""
    import shutil

    unused = time.time() - PYCACHE_UNUSED_DAYS * 86400
    try:
        others = [entry for entry in ours.parent.iterdir() if entry.name != ours.name and entry.is_dir()]
    except OSError:
        return
    for entry in others:
        try:
            if entry.stat().st_mtime < unused:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError:
            pass


def standby() -> bool:
    """Whether the daemon keeps a standby (``Daemon.stand``): ``CADGEN_ENGINE_STANDBY=0`` is the
    operator's seam to keep none (CI, a machine short of memory); unset or anything else, it does."""
    return os.environ.get("CADGEN_ENGINE_STANDBY", "").strip() != "0"


def worker_cap() -> int:
    """The live workers' cap: ``CADGEN_ENGINE_WORKERS``, else the machine's cores."""
    try:
        given = int(os.environ.get("CADGEN_ENGINE_WORKERS", "").strip() or 0)
    except ValueError:
        given = 0
    return given if given > 0 else (os.cpu_count() or 1)


def state_dir() -> Path:
    """Where the daemon's door and lock live: ``CADGEN_ENGINE_DIR``, else ``default_state_dir``.
    Resolved once, here, for the client and the server alike (``os.path.realpath``): a ``..``, a
    symlink or a trailing slash in either spelling names the same door, lock and port file."""
    override = os.environ.get("CADGEN_ENGINE_DIR")
    return Path(os.path.realpath(override if override else default_state_dir()))


def default_state_dir() -> str:
    """The engine's folder when ``CADGEN_ENGINE_DIR`` names none, in a place no other user can make
    it first: ``$XDG_RUNTIME_DIR/cadgen-engine`` (Linux's per-session folder), else
    ``cadgen-engine`` in the user's temporary folder when it is this user's alone: on macOS the one
    the system names (``_darwin_temp``, ``/var/folders/...``), which a sandbox that sets its own
    ``TMPDIR`` does not move, so a client in it and the engine outside find one folder; ``TMPDIR``
    only where the system names none. Else ``/tmp/cadgen-<uid>``, which ``folder_refusal`` still
    checks. On Windows the temporary folder is the user's own: ``cadgen-engine`` in it."""
    if WINDOWS:
        return os.path.join(tempfile.gettempdir(), "cadgen-engine")
    for parent in (os.environ.get("XDG_RUNTIME_DIR"), _darwin_temp() or os.environ.get("TMPDIR")):
        if parent and os.path.isabs(parent) and _users_own(parent):
            return os.path.join(parent, "cadgen-engine")
    return f"/tmp/cadgen-{os.getuid()}"


def _darwin_temp() -> str | None:
    """macOS's per-user temporary folder as the system names it (``_CS_DARWIN_USER_TEMP_DIR``), what
    ``TMPDIR`` holds in a login session, whatever ``TMPDIR`` a sandbox sets; None elsewhere or when
    it cannot be asked."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes

        buffer = ctypes.create_string_buffer(1024)
        size = ctypes.CDLL(None, use_errno=True).confstr(65537, buffer, len(buffer))  # _CS_DARWIN_USER_TEMP_DIR
    except (OSError, AttributeError):
        return None
    return os.fsdecode(buffer.value) if 0 < size <= len(buffer) else None


def _users_own(folder: str) -> bool:
    """Whether ``folder`` is a folder of this user's that no one else can write to."""
    import stat

    try:
        found = os.stat(folder)
    except OSError:
        return False
    return stat.S_ISDIR(found.st_mode) and found.st_uid == os.getuid() and not found.st_mode & 0o022


def _tag(protocol: int | None = None, *, versioned: bool = True) -> str:
    """One daemon per installation: its environment, its interpreter's version and the engine it
    runs -- never the name the interpreter was started by (``python``, ``python3``, ``python3.12``
    of one environment are one installation) -- the protocol it speaks (``PROTOCOL``, else
    ``protocol``: an older one's daemon, which ``stop`` still finds), and the version it runs as
    (``installation``). So an upgrade into the same environment (``pip install -U``, ``uv tool
    upgrade``, a development install made again) has a door, lock and port file of its own: its
    clients start its engine, never dial the old one still running there, and that start retires
    the old one when nothing uses it (``retire_older``). ``versioned=False``: the environment alone,
    which keys what outlives an upgrade in it -- its engine record, the port it rolled to (``bind``)."""
    prefix = os.path.normcase(os.path.realpath(sys.prefix))
    material = (f"{prefix}|{sys.implementation.cache_tag}|{Path(__file__).resolve().parent}|"
                f"{PROTOCOL if protocol is None else protocol}" + (f"|{installation()}" if versioned else ""))
    return hashlib.sha256(material.encode()).hexdigest()[:12]


def folder_refusal(folder: Path) -> str | None:
    """Why ``folder`` may not hold the engine's door, lock and port file, or None when it may. On
    POSIX it must be a folder of this user's that no one else can write to: whoever owns the folder,
    or can write to it, can take the door's place, and every request carries its client's
    environment. (The default folder's name is shared by every user of a machine: another user who
    made it first owns it.)"""
    if WINDOWS:
        return None
    import stat

    try:
        found = os.lstat(folder)
    except OSError as error:
        return f"the engine's folder {folder} cannot be read: {error.strerror or error}"
    if not stat.S_ISDIR(found.st_mode):
        return f"the engine's folder {folder} is not a folder"
    if found.st_uid != os.getuid():
        return (f"the engine's folder {folder} belongs to another user (uid {found.st_uid}): "
                "set CADGEN_ENGINE_DIR to a folder of your own")
    if found.st_mode & 0o022:
        return (f"the engine's folder {folder} can be written by others (mode {stat.S_IMODE(found.st_mode):o}): "
                "run chmod go-w on it, or set CADGEN_ENGINE_DIR to a folder of your own")
    return None


def lock_path(protocol: int | None = None) -> Path:
    return state_dir() / f"{_tag(protocol)}.lock"


def port_path(protocol: int | None = None) -> Path:
    return state_dir() / f"{_tag(protocol)}.port"


def door_path(protocol: int | None = None) -> Path:
    """The daemon's door on POSIX: a named pipe beside its lock, which it reads hellos from
    (``door``). A pipe's path has no length limit but the file system's."""
    return state_dir() / f"{_tag(protocol)}.door"


def address(protocol: int | None = None) -> Path:
    """Where a client reaches the daemon: its door, on Windows its port file."""
    return port_path(protocol) if WINDOWS else door_path(protocol)


def failure_path() -> Path:
    """Why the last daemon started here could not take its lock or listen, as JSON: ``reason``, and
    ``denied`` when the system refused it (a sandbox that forbids a local port). Its stderr goes
    nowhere, so this is what the client that started it reads when it exits at once."""
    return state_dir() / f"{_tag()}.failed"


def _note_failure(reason: str, error: OSError) -> None:
    _note(f"{reason}: {error.strerror or error}", denied=isinstance(error, PermissionError))


def _note(said: str, denied: bool = False) -> None:
    """Why this daemon exits failing: on its stderr and in its note beside its lock."""
    print(f"cadgen: {said}", file=sys.stderr)  # ``cadgen server``'s terminal; nowhere when started for a client
    try:
        failure_path().write_text(json.dumps({"reason": said, "denied": denied}), encoding="utf-8")
    except OSError:
        pass  # a folder it cannot write either: the client says the daemon exited, and its code


@dataclass(frozen=True)
class Endpoint:
    """Where one protocol's daemon of this installation listens and locks: its door (on Windows,
    its port file) and its lock."""

    protocol: int
    address: Path
    lock: Path


def endpoints() -> list[Endpoint]:
    """Every daemon this installation may have running, this protocol's first and then each older
    one's (``_tag``): the files ``stop`` looks at, in the engine folder. A protocol bump never
    strands a daemon that has a door (protocol 3 on); one of an earlier protocol listened on a
    socket, which nothing reaches now, and leaves on that older cadgen's own idle timeout."""
    return [Endpoint(protocol, address(protocol), lock_path(protocol)) for protocol in range(PROTOCOL, 0, -1)]


def engine_root() -> str:
    """The folder ``cadgen`` is imported from: a worker this daemon starts imports the same."""
    return str(Path(__file__).resolve().parent.parent.parent)


# Windows' process creation flags, by number: ``subprocess`` names them on Windows alone.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def windowless() -> dict[str, Any]:
    """How the engine starts a process -- a worker, a reader, a render process -- on Windows: with
    a console of its own and no window (``CREATE_NO_WINDOW``); elsewhere as it is. A console program
    started with no console gets a new one, with a window (#597): a window per process, open as long
    as it lives, and closing one ends it."""
    return {"creationflags": CREATE_NO_WINDOW} if os.name == "nt" else {}


def detached() -> dict[str, Any]:
    """How the daemon is started: outliving the command that needed it. On Windows a console of its
    own with no window and a process group of its own, never no console at all (``DETACHED_PROCESS``),
    which would give each console program it starts a window of its own (#597); elsewhere a session
    of its own (``start_new_session`` is POSIX's: Windows takes it as nothing)."""
    if os.name == "nt":
        return {"creationflags": CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


# --- workers -----------------------------------------------------------------------------


class WorkerGone(Exception):
    pass


class Worker:
    """One warm worker process and the script it builds.

    The worker's protocol pipe (its original stdout) carries frames: a JSON object on one
    line and, when the object has ``bytes``, exactly that many bytes after the line. A
    reader thread takes every frame as it comes: a build's ``log`` lines go to that
    build's caller, and so do its ``progress`` frames (``progress.py``), the last of which it
    keeps (``progress``, what ``status`` shows) and hands to ``on_progress``; its
    ``done``/``failed`` answer to the waiting ``build`` call. ``where`` asks the worker what made
one element of a document it built (``worker``): a request of its own, answered on the
same pipe, even while a build runs. Requests reach the worker on its original stdin, which it
reads on a handle of its own; its standard input is the null device, so nothing a model loads
or reads ever touches the request pipe (on Windows a DLL's C runtime would wait on it).

A ``standby`` worker loads the kernel before it says it is ready (``worker.load_kernel``) and
builds no script until a build takes it (``adopt``)."""

    def __init__(self, script: str, environment: dict[str, str], cwd: str | None = None,
                 on_progress: Callable[["Worker", dict[str, Any]], None] = lambda _worker, _frame: None,
                 on_saved: Callable[["Worker", dict[str, Any], bytes], None] = lambda _worker, _header, _payload: None,
                 standby: bool = False) -> None:
        self.script = script
        self.environment = environment
        env = dict(environment)
        path = env.get("PYTHONPATH", "")
        root = engine_root()
        if root not in path.split(os.pathsep):
            env["PYTHONPATH"] = os.pathsep.join(item for item in (root, path) if item)
        # The daemon's bytecode, whoever's run starts the worker: it serves every later run too.
        own = {name: os.environ[name] for name in BYTECODE if name in os.environ}
        env = {name: value for name, value in env.items() if name not in BYTECODE}
        env.update(own or bytecode({}))
        env["CADGEN_ENGINE_WORKER"] = "1"
        self.process = subprocess.Popen([sys.executable, "-P", "-m", "cadgen.engine.worker",
                                         *(["--standby"] if standby else [])], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                        cwd=cwd or str(Path(script).parent), **windowless())
        self.lock = threading.Lock()
        self.writing = threading.Lock()  # one request line at a time on the worker's stdin
        self.asked: dict[str, "queue.Queue[Any]"] = {}
        self.questions = itertools.count(1)
        self.sink: Callable[[dict[str, Any]], None] | None = None
        self.on_progress = on_progress
        self.on_saved = on_saved
        self.saves = itertools.count(1)
        # The running request's last progress frame (``progress.py``: a build's, an export's or a snapshot's).
        self.progress: dict[str, Any] | None = None
        # When the running build began (``time.time()``), None while no build runs; and the requests
        # queued behind it, each sent its progress frames as its own build would be (``Daemon.behind``).
        self.building: float | None = None
        self.followers: list[Callable[[dict[str, Any]], None]] = []
        self.answers: "queue.Queue[dict[str, Any] | None]" = queue.Queue()
        self.started = time.time()
        self.builds = 0
        # Its place in the pool (``Pool``): its key, whether a request holds it, since when, and
        # when it was last let go; its resident memory at its start and after its last build, in MiB.
        self.key = os.path.normcase(script)
        self.leased = False
        self.since = 0.0
        self.used = time.monotonic()
        self.rss: float | None = None
        # Over its memory cap after a build (``worker.retirement``): it exits, and is never asked again.
        self.retired = False
        threading.Thread(target=self._stderr, daemon=True).start()
        threading.Thread(target=self._reader, daemon=True).start()
        ready = self.answers.get()
        if ready is None or "ready" not in ready:
            raise WorkerGone(f"the worker for {script} did not start")
        self.pid = ready["ready"]
        self.rss = ready.get("rssMb")

    def adopt(self, script: str, environment: dict[str, str], cwd: str | None) -> None:
        """The standby taken by a build of ``script``: from now on that script's worker, with its
        key, the environment it was asked in and the folder a fresh worker of it starts in (its
        script's, or ``cwd``), as if started for it. Its next request adopts the run's environment
        as every request does (``worker.adopt``)."""
        self._write({"op": "adopt", "home": os.path.abspath(cwd or str(Path(script).parent))})
        self.script, self.environment, self.key = script, environment, os.path.normcase(script)
        self.started = time.time()

    def _tell(self, message: dict[str, Any]) -> None:
        """``message`` to the client the running build answers, while it is there. A client gone
        (killed, or hung up) drops its sink, and the worker's output is read on all the same: a
        worker writing to a pipe nobody reads blocks, its build never ends, and the script's next
        run waits on it for ever."""
        sink = self.sink
        if sink is None:
            return
        try:
            sink(message)
        except (OSError, ValueError):
            if self.sink is sink:
                self.sink = None

    def _stderr(self) -> None:
        assert self.process.stderr is not None
        for line in iter(self.process.stderr.readline, b""):
            self._tell({"log": line.decode("utf-8", "replace").rstrip("\n"), "stream": "model"})

    def _reader(self) -> None:
        stream = self.process.stdout
        assert stream is not None
        try:
            for line in iter(stream.readline, b""):
                line = line.strip()
                if not line.startswith(b"{"):
                    continue
                message = json.loads(line)
                size = int(message.get("bytes") or 0)
                payload = _read_exactly(stream, size) if size else b""
                if "log" in message:
                    self._tell({"log": message["log"]})
                elif "notice" in message:  # said to the caller at once (``worker.kernel``)
                    self._tell({"log": message["notice"], "stream": "notice"})
                elif "progress" in message:
                    frame = self.progress = message["progress"]
                    self._tell({"progress": frame})
                    for follow in list(self.followers):
                        try:
                            follow({"progress": frame})
                        except (OSError, ValueError):
                            pass  # a waiting client gone: its request leaves on its own
                    try:
                        self.on_progress(self, frame)
                    except Exception:  # noqa: BLE001 - where a build is never fails it
                        pass
                elif "collected" in message:
                    pass  # the worker collected while idle (``worker.py``): nothing waits on it
                elif "saved" in message:
                    try:
                        self.on_saved(self, message["saved"], payload)  # the cache's (``save``)
                    except Exception:  # noqa: BLE001 - a save never fails the worker's pipe
                        pass
                elif "where" in message:
                    waiting = self.asked.pop(str(message.get("id")), None)
                    if waiting is not None:
                        waiting.put(message["where"])
                else:
                    if payload:
                        message["payload"] = payload
                    self.answers.put(message)
        except (OSError, ValueError, EOFError):
            pass
        finally:
            self.answers.put(None)  # gone: every build it held settles
            for waiting in list(self.asked.values()):
                waiting.put(None)

    def alive(self) -> bool:
        return self.process.poll() is None

    def _write(self, request: dict[str, Any], payload: bytes = b"") -> None:
        """One request, its ``payload`` (``bytes`` of them) after its line."""
        assert self.process.stdin is not None
        if payload:
            request = {**request, "bytes": len(payload)}
        with self.writing:
            self.process.stdin.write((json.dumps(request) + "\n").encode())
            if payload:
                self.process.stdin.write(payload)
            self.process.stdin.flush()

    def where(self, doc: str, key: str, kind: str, ordinal: int, timeout: float = 10.0) -> dict[str, Any] | None:
        """What made one element of a document (``doc``, its id) this worker built, as its last
        build of it named the element (``build.made_by``); None when it did not build it, or is gone."""
        ident = f"where{next(self.questions)}"
        waiting: "queue.Queue[Any]" = queue.Queue(1)
        self.asked[ident] = waiting
        try:
            self._write({"id": ident, "op": "where", "doc": doc, "key": key, "kind": kind, "ordinal": ordinal})
            return waiting.get(timeout=timeout)
        except (OSError, ValueError, queue.Empty):
            return None
        finally:
            self.asked.pop(ident, None)

    def save(self, ident: str, script: str, name: str, generation: str) -> None:
        """Ask for document ``ident`` (model ``name`` of ``script``, generation ``generation``) as the
        engine's cache keeps it: the worker answers when no other request waits, to ``on_saved``."""
        self._write({"id": f"save{next(self.saves)}", "op": "save", "ident": ident, "script": script, "name": name,
                     "generation": generation})

    def build(self, request: dict[str, Any], send: Callable[[dict[str, Any]], None],
              payload: bytes = b"") -> dict[str, Any]:
        with self.lock:
            self.sink = send
            self.progress = None
            self.building = time.time() if request.get("op") == "build" else None
            try:
                self._write(request, payload)
                message = self.answers.get()
                if message is None:
                    code = self.process.wait()
                    raise WorkerGone(f"the worker for {Path(self.script).name} exited ({code}) during the build")
                self.builds += 1
                self.rss = message.pop("rssMb", self.rss)
                done = message.get("done")
                if isinstance(done, dict):
                    reports = done.get("reports") or []
                else:
                    reports = done if isinstance(done, list) else []
                if any(isinstance(report, dict) and report.get("retired") for report in reports):
                    self.retired = True
                return message
            except (BrokenPipeError, OSError) as error:
                raise WorkerGone(str(error)) from error
            finally:
                self.sink = None
                self.building = None

    def stop(self) -> None:
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
            self.process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            self.process.kill()


# The requests that serve (``Daemon.serve``: the HTTP server bound on the first), each counted busy
# while it is underway (``Daemon.handle``).
SERVING = frozenset({"serve", "viewer", "http", "read", "warm"})
# The type a worker answers bytes of a held document that do not read with (``build.Unreadable``),
# as ``worker.refusal`` names it.
UNREADABLE = "cadgen.engine.build:Unreadable"


def refused(error: Exception) -> dict[str, Any]:
    """A refusal as the daemon answers it: its words, its type (``worker.refusal``), and for a
    document the engine does not hold (``serve.NotHeld``) its state and the command that builds it
    again, so the caller raises it as that type (``api._failed``) and the CLI exits 2."""
    from cadgen.engine.serve import NotHeld
    from cadgen.engine.worker import refusal

    found: dict[str, Any] = {"failed": str(error), **refusal(error)}
    if isinstance(error, NotHeld):
        found.update(state=error.state, rebuild=error.rebuild)
    return found


def _read_exactly(stream: Any, size: int) -> bytes:
    chunks = []
    while size:
        chunk = stream.read(size)
        if not chunk:
            raise EOFError("the worker closed its pipe inside a frame")
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


# --- the pool -----------------------------------------------------------------------------


@dataclass(eq=False)
class _Ticket:
    """A request waiting for a worker: granted the live worker of its key (``worker``), or a
    slot to start one in (``start``), retiring ``victim`` first -- or to take the standby
    (``standby``) as its worker."""

    key: str
    environment: dict[str, str]
    cwd: str | None
    worker: Any = None
    start: bool = False
    victim: Any = None
    standby: Any = None
    awaits: bool = False  # it waits for the standby being started (``Pool._grant``)

    @property
    def granted(self) -> bool:
        return self.worker is not None or self.start


def interpreter(environment: dict[str, str]) -> dict[str, str]:
    """What of ``environment`` a worker started in it is bound to (``RESTARTS``): a request whose
    differs from its script's worker's replaces that worker."""
    return {name: environment.get(name, "") for name in RESTARTS}


class Pool:
    """The daemon's live workers, one per key (a script's path, ``documents``),
    at most ``cap`` of them but for watched ones (see the module): ``lease`` a key's worker for one
    request, and ``release`` it after. Requests are granted first come first served: one whose key
    has a live worker takes it when it is free; one that needs a worker of its own takes the standby
    when its interpreter's environment is the standby's (``interpreter``), else a slot under the cap,
    else the slot of the standby, else of the least recently used idle worker no page watches -- one
    no request waits for, if there is one -- which is retired. When every idle worker is watched, the
    new worker starts past the cap: the count cap never retires a watched worker (connected means
    warm). With every worker busy the request waits, and so does every request that needs a slot
    after it. ``start(key, environment, cwd)`` starts a worker; ``drain(worker)`` is asked of every
    worker retired, out of the pool and before it is stopped (the daemon's: its documents taken from
    it, ``models.Models.drain``).

    No timer retires a worker; memory does (``shed``): ``memory()`` is the cap on the resident memory
    of the pool's processes together, in MiB (None: none), against each one's last measure (``rss``).
    ``spare(environment)``, when the daemon sets it, starts a standby: a worker with the kernel loaded
    and no script (``stand``). ``renders``, when the daemon sets it, is its render processes
    (``render.service.Renders``), counted with the workers and retired by the same rule."""

    def __init__(self, cap: int, start: Callable[[str, dict[str, str], str | None], Any],
                 connected: Callable[[Any], bool] = lambda worker: False,
                 drain: Callable[[Any], None] = lambda worker: None,
                 memory: Callable[[], float | None] = lambda: None) -> None:
        self.cap = max(1, int(cap))
        self.start = start
        self.connected = connected
        self.drain = drain
        self.memory = memory
        self.spare: Callable[[dict[str, str]], Any] | None = None
        # Whether the system is under memory pressure now (the daemon's ``serve.Pressure``): no
        # standby is started under it, which ``shed`` would retire at its next look.
        self.pressed: Callable[[], bool] = lambda: False
        self.renders: Any = None
        self.lock = threading.Condition()
        self.live: dict[str, Any] = {}  # by key
        self.starting: set[str] = set()  # the keys whose worker is being started, each holding a slot
        self.queue: list[_Ticket] = []
        self.retired: collections.deque = collections.deque(maxlen=RETIRED_KEPT)
        # The standby (``stand``): ready, or being started in the environment given; either holds a slot.
        self.standby: Any = None
        self.readying: dict[str, str] | None = None
        self.standby_mb: float | None = None  # the last standby's memory once ready: the room a next one needs
        # The environment of a build that started a worker of another interpreter while the standby
        # was being started: the standby, once ready, is replaced by one of it.
        self.follow: dict[str, str] | None = None
        self.stopped = False

    def lease(self, script: str, environment: dict[str, str], cwd: str | None = None,
              loading: Callable[[str], None] | None = None) -> Any:
        """The worker of ``script`` for one request, waiting its turn (see the class); started
        when it has none, or the standby taken for it. ``release`` it after. A request still waiting
        for the standby being started after ``worker.KERNEL_PATIENCE`` -- its kernel's first load on a
        fresh installation -- is said to ``loading``, once, while it waits (``worker.KERNEL_NOTICE``)."""
        ticket = _Ticket(os.path.normcase(script), environment, cwd)
        told = None
        with self.lock:
            self.queue.append(ticket)
            self._grant()
            if not ticket.granted and loading is not None:
                from cadgen.engine.worker import KERNEL_NOTICE, KERNEL_PATIENCE

                def tell() -> None:
                    with self.lock:
                        waits = not ticket.granted and ticket.awaits and self.readying is not None
                    if waits:
                        loading(KERNEL_NOTICE)

                told = threading.Timer(KERNEL_PATIENCE, tell)
                told.daemon = True
                told.start()
            try:
                while not ticket.granted:
                    self.lock.wait()
            finally:
                if told is not None:
                    told.cancel()
        if ticket.worker is not None:
            return ticket.worker
        if ticket.victim is not None:
            self._stop(ticket.victim)  # the worker whose slot this is exits before the new one starts
        try:
            worker = self._adopted(ticket, script) or self.start(script, environment, cwd)
        except BaseException:
            with self.lock:
                self.starting.discard(ticket.key)
                self._grant()
            raise
        with self.lock:
            self.starting.discard(ticket.key)
            worker.leased, worker.since = True, time.monotonic()
            self.live[ticket.key] = worker
            # A worker of another interpreter's started: the standby follows the latest caller's, now
            # or once it is ready.
            other = self.standby if ticket.standby is None and self.standby is not None and \
                interpreter(self.standby.environment) != interpreter(environment) else None
            if other is not None:
                self.standby = None
            elif ticket.standby is None and self.readying is not None and \
                    interpreter(self.readying) != interpreter(environment):
                self.follow = dict(environment)
        if other is not None:
            self._stop(other)
        self.stand(environment)
        return worker

    def _adopted(self, ticket: _Ticket, script: str) -> Any:
        """The standby a ticket was granted, taken as ``script``'s worker (``Worker.adopt``); None when
        it has none, or the standby is gone: a fresh worker starts instead."""
        spare = ticket.standby
        if spare is None:
            return None
        try:
            spare.adopt(script, ticket.environment, ticket.cwd)
            return spare
        except (OSError, ValueError):
            spare.stop()
            return None

    def release(self, worker: Any) -> None:
        """A request is done with its worker: it is free again, or retired when it is gone or
        over its memory cap; then the pool's memory is held to its cap (``shed``)."""
        gone = False
        with self.lock:
            worker.leased, worker.used = False, time.monotonic()
            if worker.retired or not worker.alive():
                gone = self.live.get(worker.key) is worker
                if gone:
                    del self.live[worker.key]
                    self._note(worker, "RSS" if worker.retired else "exited")
            self._grant()
        if gone:
            self._stop(worker)
        self.shed()

    def _stop(self, worker: Any) -> None:
        """A worker retired: drained (``drain``), then stopped. A drain that fails stops it all the same."""
        try:
            self.drain(worker)
        except Exception:  # noqa: BLE001 - what the drain could not take is evicted
            pass
        worker.stop()

    # --- the standby ---------------------------------------------------------------------

    def stand(self, environment: dict[str, str]) -> None:
        """A standby started in ``environment``, off the caller's thread, when the daemon gave the
        pool one to start (``spare``) and the pool has none, a slot for it under the cap and room
        for it under the memory cap (the last standby's measure), and the system not under memory
        pressure (``pressed``). A build that needs a worker of
        its own meanwhile, in an environment of the same interpreter, waits for it rather than start
        another."""
        if self.spare is None or self.pressed():
            return
        cap, drawing = self.memory(), self._drawing()
        with self.lock:
            if self.stopped or self.standby is not None or self.readying is not None:
                return
            if len(self.live) + len(self.starting) >= self.cap:
                return
            if cap is not None and self._resident(drawing) + (self.standby_mb or 0.0) > cap:
                return
            self.readying = dict(environment)
        threading.Thread(target=self._ready, args=(dict(environment),), name="cadgen-standby", daemon=True).start()

    def _ready(self, environment: dict[str, str]) -> None:
        """The standby being started (``stand``): ready, it waits for a build; failed, the build
        waiting for it starts a worker of its own."""
        spare = None
        try:
            spare = self.spare(environment) if self.spare is not None else None
        except Exception:  # noqa: BLE001 - no standby: the next build starts its own worker
            spare = None
        with self.lock:
            self.readying = None
            follow, self.follow = self.follow, None
            if follow is not None and interpreter(follow) == interpreter(environment):
                follow = None
            kept = spare is not None and not self.stopped and follow is None
            if kept:
                self.standby, self.standby_mb = spare, spare.rss
            elif spare is not None:
                self.standby_mb = spare.rss
            self._grant()
            self.lock.notify_all()
        if spare is not None and not kept:
            spare.stop()
        if follow is not None:
            self.stand(follow)
        elif kept:
            self.shed()

    # --- memory ----------------------------------------------------------------------------

    def _drawing(self) -> list[Any]:
        """The render processes alive now (``renders``): asked before the lock is taken."""
        return self.renders.processes_now() if self.renders is not None else []

    def _resident(self, drawing: list[Any]) -> float:
        """The resident memory of the pool's processes, in MiB, as each last measured it (call with
        the lock held): every live worker's, the standby's and the render processes' (``drawing``)."""
        held = [*self.live.values(), *([self.standby] if self.standby is not None else [])]
        return float(sum(process.rss or 0 for process in [*held, *drawing]))

    def resident(self) -> float:
        drawing = self._drawing()
        with self.lock:
            return self._resident(drawing)

    def shed(self, pressure: bool = False) -> list[Any]:
        """The memory rule: while the pool's resident memory is over its cap -- under the system's
        memory pressure (``pressure``), over ``PRESSURE_SHARE`` of it, and the standby retired at once
        -- idle processes are retired, least recently used first within each rank: the standby, then
        render processes (each holds a document the daemon sends again), then the workers no page
        watches, then the watched ones, which go only when no other is left. A busy process is never
        retired. A worker retired is drained first (``drain``): its documents stay ``held``. The retired."""
        cap, renders, drawing = self.memory(), self.renders, self._drawing()
        with self.lock:
            if self.stopped or (cap is None and not (pressure and self.standby is not None)):
                return []
            total = self._resident(drawing)
            target = None if cap is None else cap * (PRESSURE_SHARE if pressure else 1.0)
            idle = sorted((worker for worker in self.live.values() if not worker.leased), key=lambda w: w.used)
            unwatched = [worker for worker in idle if not self.connected(worker)]
            order = [*([self.standby] if self.standby is not None else []),
                     *sorted((render for render in drawing if not render.busy()), key=lambda r: r.used),
                     *unwatched, *[worker for worker in idle if worker not in unwatched]]
            chosen: list[Any] = []
            for held in order:
                standby = held is self.standby
                if not (standby and pressure) and (target is None or total <= target):
                    break
                if not held.rss and not standby:
                    continue  # unmeasured: retiring it frees nothing the rule can count
                total -= held.rss or 0.0
                chosen.append(held)
                reason = "pressure" if pressure else "RSS"
                if standby:
                    self.standby = None
                    self._note(held, reason)
                elif held in drawing:
                    pass  # a render process: the daemon's ``Renders`` lets it go
                else:
                    del self.live[held.key]
                    self._note(held, reason)
            if chosen:
                self._grant()
        for held in chosen:
            if held in drawing:
                renders.retire(held)
            else:
                self._stop(held)
        return chosen

    def free_for(self, worker: Any) -> float | None:
        """How long ``worker`` has been free with no request waiting for it, in seconds; None while a
        request holds it or waits for it."""
        with self.lock:
            if worker.leased or any(ticket.key == worker.key and not ticket.granted for ticket in self.queue):
                return None
            return time.monotonic() - worker.used

    def holds(self, worker: Any) -> bool:
        """Whether ``worker`` is live in the pool: neither retired nor gone."""
        with self.lock:
            return self.live.get(worker.key) is worker and not worker.retired and worker.alive()

    def workers(self) -> list[Any]:
        with self.lock:
            return list(self.live.values())

    def waiting(self) -> int:
        with self.lock:
            return sum(not ticket.granted for ticket in self.queue)

    def stop(self) -> None:
        with self.lock:
            self.stopped = True
            every = [*self.live.values(), *([self.standby] if self.standby is not None else [])]
            self.live.clear()
            self.standby = None
        for worker in every:
            worker.stop()

    def _note(self, worker: Any, reason: str) -> None:
        self.retired.appendleft({"script": worker.script, "pid": getattr(worker, "pid", None),
                                 "builds": getattr(worker, "builds", 0), "reason": reason, "at": time.time()})

    def _grant(self) -> None:
        """Grant what the waiting requests can have, in the order they came (call with the lock
        held): see the class."""
        for key, worker in list(self.live.items()):
            if not worker.leased and not worker.alive():
                del self.live[key]
                self._note(worker, "exited")
        if self.standby is not None and not self.standby.alive():
            self.standby = None
        wanted = {ticket.key for ticket in self.queue if ticket.key in self.live}
        taken: set[int] = set()  # the workers this pass granted or retired
        blocked = False  # a request before found no slot: no later one takes one
        awaited = False  # a request before waits for the standby being started
        granted = False
        for ticket in self.queue:
            worker = self.live.get(ticket.key)
            if worker is not None and interpreter(worker.environment) == interpreter(ticket.environment):
                if not worker.leased and id(worker) not in taken:
                    worker.leased, worker.since = True, time.monotonic()
                    ticket.worker = worker
                    taken.add(id(worker))
                    granted = True
                continue
            if ticket.key in self.starting:
                continue  # its key's worker is being started: it waits for that one
            if worker is not None:
                # Its script's worker, of another interpreter's environment: replaced in its slot once
                # it is free.
                if not worker.leased and id(worker) not in taken:
                    del self.live[ticket.key]
                    self._note(worker, "environment")
                    self._slot(ticket, worker)
                    taken.add(id(worker))
                    granted = True
                continue
            if blocked:
                continue
            same = interpreter(ticket.environment)
            if self.standby is not None and interpreter(self.standby.environment) == same:
                # The standby, of this request's interpreter: its slot and its loaded kernel are the
                # new worker's.
                ticket.standby, self.standby = self.standby, None
                self._slot(ticket, None)
                granted = True
                continue
            if self.readying is not None and not awaited and interpreter(self.readying) == same:
                awaited = ticket.awaits = True
                continue  # the standby being started is this request's once it is ready
            occupied = len(self.live) + len(self.starting) + (self.standby is not None) + (self.readying is not None)
            if occupied < self.cap:
                self._slot(ticket, None)
                granted = True
                continue
            if self.standby is not None:
                # Another interpreter's standby: the first to make room.
                victim, self.standby = self.standby, None
                self._slot(ticket, victim)
                granted = True
                continue
            idle = [held for held in self.live.values() if not held.leased and id(held) not in taken]
            if not idle:
                blocked = True
                continue
            # Connected means warm: a worker whose document a page watches is never the count
            # cap's victim. With only watched idle workers the cap is exceeded instead, so a
            # build never waits on an open page and never costs one its warm worker.
            unwatched = [held for held in idle if not self.connected(held)]
            if not unwatched:
                self._slot(ticket, None)
                granted = True
                continue
            victim = min(unwatched, key=lambda held: (held.key in wanted, held.used))
            del self.live[victim.key]
            self._note(victim, "LRU")
            self._slot(ticket, victim)
            taken.add(id(victim))
            granted = True
        if granted:
            self.queue = [ticket for ticket in self.queue if not ticket.granted]
            self.lock.notify_all()

    def _slot(self, ticket: _Ticket, victim: Any) -> None:
        ticket.start, ticket.victim = True, victim
        self.starting.add(ticket.key)


# --- the daemon ---------------------------------------------------------------------------


def environment_port() -> int | None:
    """``CADGEN_ENGINE_PORT`` as a port (0: any free one), or None when it names none."""
    given = os.environ.get("CADGEN_ENGINE_PORT", "").strip()
    if not given:
        return None
    try:
        port = int(given)
    except ValueError:
        raise ValueError(f"CADGEN_ENGINE_PORT={given!r} is not a port") from None
    if not 0 <= port <= 65535:
        raise ValueError(f"CADGEN_ENGINE_PORT={given!r} is not a port")
    return port


def default_port() -> int:
    """``DEFAULT_PORT``, or the port ``CADGEN_ENGINE_DEFAULT_PORT`` names (1-65535): a test's seam,
    the default it holds or frees without touching the machine's 3245."""
    given = os.environ.get(DEFAULT_PORT_ENV, "").strip()
    return int(given) if given.isdigit() and 0 < int(given) <= 65535 else DEFAULT_PORT


def _held(error: OSError) -> bool:
    """Whether a bind failed because the port is someone else's (in use, or reserved on Windows)."""
    import errno

    return error.errno in (errno.EADDRINUSE, errno.EACCES) or getattr(error, "winerror", None) in (10048, 10013)


def _answers(host: str, port: int) -> bool:
    """Whether something already listens at ``port`` where a client of ``host`` reaches it: a
    listener on every interface lets a loopback bind through on macOS, and would take its traffic."""
    from cadgen.engine.serve import reachable_host

    try:
        socket.create_connection((reachable_host(host).strip("[]"), port), timeout=0.5).close()
    except OSError:
        return False
    return True


class PortHeld(ValueError):
    """The engine's port is another process's (``bind``): ``who`` holds it, in words. A port named
    (``--port``, ``CADGEN_ENGINE_PORT``) is refused in one line that names the holder; the default
    or remembered one is rolled from."""

    def __init__(self, said: str, who: str) -> None:
        super().__init__(said)
        self.who = who


def installation() -> str:
    """The version this installation runs as -- the one name its client, its daemon and its workers
    all go by (``_tag``, ``status``): ``CADGEN_INSTALLATION_VERSION`` when it names one (the
    ``cadgen`` command sets it for a development install, which reports its release's version), else
    the version this environment is registered as (``registered``: a dev environment's
    ``python model.py`` run directly), else the release declared beside this code
    (``previous.version``)."""
    from cadgen.engine.previous import version

    named = os.environ.get(INSTALLATION_ENV, "")
    if re.fullmatch(r"[0-9][0-9A-Za-z.+_-]*", named):
        return named
    return registered() or version()


def registered() -> str | None:
    """The version this environment (``sys.prefix``) is registered as in the user's state folder
    (``installations/<version>.json``, the distribution's records: ``cadgen._internal.installations``),
    when one names its release: the one registered last. None with no state folder, or no such record
    -- and for a record of another release, left from before an upgrade into this environment
    (``pip install -U``), which is not what runs here now. Read once per process and state folder."""
    from cadgen.engine import registry
    from cadgen.engine.previous import version

    held = registry.current()
    if held is None:
        return None
    return _registered(str(held.state.root), os.path.normcase(os.path.realpath(sys.prefix)), version())


@functools.cache
def _registered(state: str, prefix: str, release: str) -> str | None:
    folder = Path(state) / "installations"
    ours = rank(release)
    found: list[tuple[float, str]] = []
    try:
        names = [entry for entry in os.scandir(folder) if entry.name.endswith(".json")]
    except OSError:
        return None
    for entry in names:
        try:
            record = json.loads(Path(entry.path).read_text(encoding="utf-8"))
            given = record["version"]
            if (isinstance(given, str) and given == entry.name[:-5] and isinstance(record.get("prefix"), str)
                    and os.path.normcase(os.path.realpath(record["prefix"])) == prefix):
                theirs = rank(given)
                if ours is not None and theirs is not None and theirs[:2] == ours[:2]:
                    found.append((entry.stat().st_mtime, given))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return max(found)[1] if found else None


# A version as PEP 440 spells it, with the spellings it normalizes (``0.8.0-dev.20261024`` is
# ``0.8.0.dev20261024``): the pattern ``packaging.version`` parses, whose order ``rank`` keeps.
_PEP440 = re.compile(r"""v?(?:(?P<epoch>[0-9]+)!)?(?P<release>[0-9]+(?:\.[0-9]+)*)
    (?:[-_.]?(?P<pre_l>alpha|a|beta|b|preview|pre|c|rc)[-_.]?(?P<pre_n>[0-9]+)?)?
    (?:-(?P<post_n1>[0-9]+)|[-_.]?(?P<post_l>post|rev|r)[-_.]?(?P<post_n2>[0-9]+)?)?
    (?:[-_.]?(?P<dev_l>dev)[-_.]?(?P<dev_n>[0-9]+)?)?
    (?:\+(?P<local>[a-z0-9]+(?:[-_.][a-z0-9]+)*))?""", re.VERBOSE | re.IGNORECASE)
_PRE = {"alpha": "a", "a": "a", "beta": "b", "b": "b", "c": "rc", "pre": "rc", "preview": "rc", "rc": "rc"}


def rank(version: Any) -> tuple | None:
    """A version's place among installations', newest highest, as ``packaging.version`` orders them:
    a release above its own pre-releases and development builds (``0.8.0`` above ``0.8.0-dev.<time>``,
    which sort by their time), and those above the release before. None for a version that is no
    PEP 440 version (the standard library only: law 3)."""
    found = _PEP440.fullmatch(version.strip()) if isinstance(version, str) else None
    if found is None:
        return None
    release = [int(part) for part in found["release"].split(".")]
    while len(release) > 1 and release[-1] == 0:
        release.pop()
    post = found["post_n1"] or (found["post_n2"] or "0" if found["post_l"] else None)
    dev = found["dev_n"] or "0" if found["dev_l"] else None
    pre = ((1, _PRE[found["pre_l"].lower()], int(found["pre_n"] or 0)) if found["pre_l"]
           else (0,) if post is None and dev is not None else (2,))
    local = found["local"]
    return (int(found["epoch"] or 0), tuple(release), pre, (0,) if post is None else (1, int(post)),
            (2,) if dev is None else (1, int(dev)),
            (0,) if local is None else (1, tuple((1, int(part), "") if part.isdigit() else (0, 0, part.lower())
                                                 for part in re.split(r"[-_.]", local))))


def _standing(status: dict[str, Any]) -> int | None:
    """How another installation's engine, by its ``status``, ranks against this one: -1 older, 0 the
    same version, 1 newer; None when it cannot be said. An engine whose ``status`` has no
    ``installation`` was built before engines said it: older than any that does, whatever its
    release (a ``0.8.0`` that would outrank every ``0.8.0-dev.*`` build). Else its installation's
    version (``rank``); one either side cannot parse is older only when its release (``version``)
    is lower than this one's."""
    from cadgen.engine.previous import version

    if "installation" not in status:
        return -1
    ours, theirs = rank(installation()), rank(status.get("installation") or status.get("version"))
    if ours is None or theirs is None:
        ours, theirs = rank(version()), rank(status.get("version"))
        return -1 if ours is not None and theirs is not None and theirs < ours else None
    return (theirs > ours) - (theirs < ours)


def _uses(status: dict[str, Any]) -> list[str] | None:
    """What uses another installation's engine, by its ``status``, in words: its holds (an agent
    host's app server), the pages that watch its documents, its requests; None when its ``status``
    does not say (one this cadgen cannot ask)."""
    if not {"watched", "active", "busy"} <= status.keys():
        return None
    holders, pages = status.get("holders") or 0, status["watched"]
    return [f"{count} {noun}{'' if count == 1 else 's'}"
            for count, noun in ((holders, "app server"), (pages, "open page"),
                                (status["busy"] + bool(status["active"]), "request")) if count]


def retire_older(host: str = "127.0.0.1") -> list[str]:
    """Every other installation's engine in this engine folder that nothing uses (``_uses``) and that
    ranks below this installation (``_standing``), asked to stop and waited for until its door and
    its port are gone (``RETIRE_SECONDS`` at most in all): so an upgrade converges on the newest
    installation's engine wherever the older one serves, and an older one never retires a newer. A
    line for each retired, the start's notice (``bind``)."""
    from cadgen.engine import client

    ours = {_tag(protocol) for protocol in range(1, PROTOCOL + 1)}
    try:
        doors = sorted(state_dir().glob("*.port" if WINDOWS else "*.door"))
    except OSError:
        return []
    asked = []
    for door in doors:
        if door.stem in ours:
            continue
        status = _ask(door, {"op": "status"})
        if status is None or _uses(status) != [] or _standing(status) != -1:
            continue
        if _ask(door, {"op": "stop"}) is None:
            continue
        serving = status.get("serving")
        port = serving.get("port") if isinstance(serving, dict) else None
        asked.append((door, port, f"retired cadgen {status.get('installation') or status.get('version')}'s idle "
                                  f"engine (pid {status.get('pid')}) for this newer installation"))
    deadline = time.monotonic() + RETIRE_SECONDS
    for door, port, _said in asked:
        while (client._answering(door) or (port and _answers(host, port))) and time.monotonic() < deadline:
            time.sleep(0.05)
    return [said for _door, _port, said in asked]


def bind(host: str, asked: int | None, listen: Callable[[int, str], Any]) -> tuple[Any, dict[str, Any]]:
    """The engine's HTTP server, listening, and where its port came from. ``listen(port, token)``
    makes it. First every other installation's engine that is older than this one and that nothing
    uses is retired, wherever it serves (``retire_older``). Then a port named -- ``asked``
    (``--port``), else ``CADGEN_ENGINE_PORT`` -- is taken or refused by name (``PortHeld``). Else the
    installation's port: 3245 (``DEFAULT_PORT``) when it is free, else the port it remembers, else
    the one it rolls to (``_installation_port``). Either way another installation's engine on it that
    nothing uses and that is not newer is retired for it (``_listen``); a newer one never is. The page
    token is the user's (``registry.TOKEN``), one for every installation, made by the first engine to
    start (``_new_token``); one there that cannot be read is refused by name, and nothing is served.

    ``where``: ``source`` (``--port``, ``CADGEN_ENGINE_PORT``, ``default`` or ``rolled``), for a
    rolled port ``because`` (who holds 3245), and ``notice``, the lines this start says once: each
    engine it retired, and a move of its port (a roll, or the return to 3245)."""
    from cadgen.engine import registry

    retired = retire_older(host)
    held = registry.current()
    environment = _tag(versioned=False)  # the environment's record: its links outlive an upgrade in it
    record = held.engine(environment) if held is not None else {}
    token = (held.token() if held is not None else None) or _new_token(held)
    remembered = record.get("port")
    if asked is not None:
        server, where = _listen(host, asked, "--port", token, listen), {"source": "--port"}
    elif (named := environment_port()) is not None:
        server, where = _listen(host, named, "CADGEN_ENGINE_PORT", token, listen), {"source": "CADGEN_ENGINE_PORT"}
    else:
        server, where = _installation_port(host, remembered, token, listen)
        remembered = server.port if where["source"] == "rolled" else None
    kept = {"port": remembered} if remembered else {}
    if held is not None and kept != record:
        try:
            held.put_engine(environment, kept)
        except OSError:
            pass  # a state folder it cannot write: this start's links work, the next start's are new
    said = "\n".join([*retired, *([where["notice"]] if where.get("notice") else [])])
    return server, {**where, "notice": said} if said else where


def _new_token(held: Any) -> str:
    """A new page token, made the user's (``registry.TOKEN``) when there is a state folder: made only
    where there is none (``Registry.make_token``), so of two engines starting at once one makes it and
    the other serves the one it reads. One that is there but cannot be read is refused by name
    (``Registry.token``), never replaced."""
    token = secrets.token_urlsafe(32)
    if held is None:
        return token
    for _attempt in range(3):
        try:
            if held.make_token(token):
                return token
        except OSError:
            return token  # a state folder it cannot write: this start's links work, the next start's are new
        found = held.token()  # another engine's, made first
        if found is not None:
            return found
    return token  # made and removed again, each time it was read: this start's links work


def _installation_port(host: str, remembered: int | None, token: str,
                       listen: Callable[[int, str], Any]) -> tuple[Any, dict[str, Any]]:
    """The server on the installation's own port, and where it came from (``bind``): 3245 when it is
    free (a remembered other port forgotten: the one time a link changes), else the remembered port,
    else -- that one held by anything but another installation's engine nothing uses -- the next
    free port, ``PORTS_TRIED`` above it and then any (``_roll``), remembered from then on."""
    default = default_port()
    first = remembered or default
    if first != default:
        server = _free(host, default, token, listen)
        if server is not None:
            return server, {"source": "default",
                            "notice": f"back on the default port {default}: links made on {first} no longer work"}
    try:
        server = _listen(host, first, "default", token, listen)
    except PortHeld as refusal:
        server = _roll(host, first, token, listen)
        return server, {"source": "rolled", "because": refusal.who if first == default else _who(default),
                        "notice": f"{first} is held by {refusal.who}; this installation serves on {server.port} "
                                  "and keeps it"}
    if first == default:
        return server, {"source": "default"}
    return server, {"source": "rolled", "because": _who(default)}


def _free(host: str, port: int, token: str, listen: Callable[[int, str], Any]) -> Any:
    """``listen(port, token)`` when nothing holds ``port``, else None."""
    if _answers(host, port):  # a listener on every interface lets a loopback bind through
        return None
    try:
        return listen(port, token)
    except OSError as error:
        if not _held(error):
            raise ValueError(f"cannot listen on {host}:{port}: {error.strerror or error}") from None
    return None


def _roll(host: str, held: int, token: str, listen: Callable[[int, str], Any]) -> Any:
    """The server on the first free port past ``held``, ``PORTS_TRIED`` at most, else on any."""
    for port in range(held + 1, min(held + 1 + PORTS_TRIED, 65536)):
        server = _free(host, port, token, listen)
        if server is not None:
            return server
    try:
        return listen(0, token)
    except OSError as error:
        raise ValueError(f"cannot listen on {host}: {error.strerror or error}") from None


def _listen(host: str, port: int, source: str, token: str, listen: Callable[[int, str], Any]) -> Any:
    """``listen(port, token)``, or ``PortHeld`` when another process holds ``port``. An engine of
    another installation that nothing uses is retired first (``_holder``), and its port waited for,
    ``RETIRE_SECONDS`` at most; any other holder is refused at once."""
    import errno

    deadline = None
    retired = ""
    while True:
        try:
            if port and _answers(host, port):  # a listener on every interface lets a loopback bind through
                raise OSError(errno.EADDRINUSE, os.strerror(errno.EADDRINUSE))
            return listen(port, token)
        except OSError as error:
            if not port or not _held(error):
                raise ValueError(f"cannot listen on {host}:{port}: {error.strerror or error}") from None
        if deadline is None:
            retired = _holder(port, source)  # refuses (``PortHeld``) unless it asked an unused engine to stop
            deadline = time.monotonic() + RETIRE_SECONDS
        elif time.monotonic() > deadline:
            raise PortHeld(f"port {port} is held by {retired}, which was asked to stop and still holds it after "
                           f"{RETIRE_SECONDS:.0f} s: run `cadgen stop` with that version", retired) from None
        time.sleep(0.1)


def _holder(port: int, source: str) -> str:
    """Who holds ``port``, when it is another installation's engine that nothing uses: asked to
    stop (its ``stop``), and named. Else ``PortHeld``, naming the holder: that engine and what uses
    it, one this cadgen cannot ask, or the process the system names (``port_holder``). ``source``:
    where the port came from (``bind``), which says how to name another."""
    other = "pass another --port" if source == "--port" else "start cadgen with another CADGEN_ENGINE_PORT"
    remedy = f"stop it, or {other}"
    found = _engine_serving(port)
    if found is not None:
        address, status = found
        who = _engine_name(status)
        uses = _uses(status)
        if uses is None:
            raise PortHeld(f"port {port} is held by {who}, which this cadgen cannot ask whether it is in use: "
                           f"run `cadgen stop` with that version, or {other}", who)
        if _standing(status) == 1:  # an older installation never retires a newer one's engine
            raise PortHeld(f"port {port} is held by {who}, a newer installation's, which this one never retires: "
                           f"use that version, or {other}", who)
        if uses:
            then = "quit that app" if (status.get("holders") or 0) else "close that page" if status["watched"] \
                else "let it finish"
            raise PortHeld(f"port {port} is held by {who}, still in use by {' and '.join(uses)}: {then} "
                           "or run `cadgen stop` with that version", who)
        if _ask(address, {"op": "stop"}) is None:
            raise PortHeld(f"port {port} is held by {who}, which did not answer when asked to stop: "
                           "run `cadgen stop` with that version", who)
        return who
    pid, name, command = port_holder(port)
    if pid is None:
        raise PortHeld(f"port {port} is held by another process: {remedy}", "another process")
    if _CADGEN.search(command or ""):
        who = f"another cadgen ({name}, pid {pid})"
        raise PortHeld(f"port {port} is held by {who}, which this one cannot ask to stop: {remedy}", who)
    who = f"{name or 'a process'} (pid {pid})"
    raise PortHeld(f"port {port} is held by {who}: {remedy}", who)


def _engine_name(status: dict[str, Any]) -> str:
    """Another installation's engine, by its ``status``: its installation's version and pid."""
    version = status.get("installation") or status.get("version")
    return (f"cadgen {version}'s engine" if version else "another cadgen's engine") + f" (pid {status.get('pid')})"


def _who(port: int) -> str:
    """Who holds ``port``, in words, as ``_holder`` names it: never refused, never asked to stop."""
    found = _engine_serving(port)
    if found is not None:
        return _engine_name(found[1])
    pid, name, command = port_holder(port)
    if pid is None:
        return "another process"
    return f"another cadgen ({name}, pid {pid})" if _CADGEN.search(command or "") else f"{name or 'a process'} (pid {pid})"


# A command line that runs cadgen's engine or viewer: ``-m cadgen.…``, or the ``cadgen`` command's
# ``viewer``, ``server`` or ``mcp``.
_CADGEN = re.compile(r"(-m\s+cadgen(\.\w+)*|[/\\]cadgen(\.exe)?\s+(viewer|server|mcp))(\s|$)")


def _engine_serving(port: int) -> tuple[Path, dict[str, Any]] | None:
    """The door (on Windows, the port file) of another installation's engine in this engine folder
    whose HTTP server is on ``port``, and its ``status``; None when no engine there answers so."""
    ours = {_tag(protocol) for protocol in range(1, PROTOCOL + 1)}
    try:
        doors = sorted(state_dir().glob("*.port" if WINDOWS else "*.door"))
    except OSError:
        return None
    for address in doors:
        if address.stem in ours:
            continue
        status = _ask(address, {"op": "status"})
        serving = (status or {}).get("serving")
        if isinstance(serving, dict) and serving.get("port") == port:
            return address, status
    return None


def _ask(address: Path, message: dict[str, Any]) -> dict[str, Any] | None:
    """``message`` asked of the engine at ``address``: its answer, or None when none answers there
    within ``ASK_SECONDS`` (a wedged engine never wedges this one)."""
    from cadgen.engine import client

    answers: list[dict[str, Any]] = []

    def ask() -> None:
        try:
            connection = client._connect(address)
            if connection is not None:
                answers.append(client._exchange(connection, message, address=address))
        except (OSError, ValueError):
            pass

    asking = threading.Thread(target=ask, daemon=True)
    asking.start()
    asking.join(ASK_SECONDS)
    return answers[0] if answers and answers[0].get("ok") else None


def port_holder(port: int) -> tuple[int | None, str | None, str | None]:
    """The process listening on TCP ``port`` here, as the system names it: its pid, its name and
    its command line, each None where the system does not say (another user's process, a tool
    missing). macOS and the BSDs ask ``lsof``; Linux reads ``/proc``; Windows asks ``netstat``."""
    try:
        if sys.platform.startswith("linux"):
            return _proc_holder(port)
        if WINDOWS:
            return _netstat_holder(port)
        return _lsof_holder(port)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None, None


def _lsof_holder(port: int) -> tuple[int | None, str | None, str | None]:
    import shutil

    lsof = shutil.which("lsof") or ("/usr/sbin/lsof" if os.path.exists("/usr/sbin/lsof") else None)
    if lsof is None:
        return None, None, None
    said = subprocess.run([lsof, "-nP", "+c", "0", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpc"], capture_output=True,
                          text=True, timeout=5).stdout
    pid = name = None
    for line in said.splitlines():
        if line.startswith("p") and pid is None:
            pid = int(line[1:])
        elif line.startswith("c") and name is None:
            name = line[1:]
    if pid is None:
        return None, None, None
    command = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True,
                             timeout=5).stdout.strip()
    return pid, name, command or None


def _proc_holder(port: int) -> tuple[int | None, str | None, str | None]:
    inodes = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            rows = Path(table).read_text().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            fields = row.split()
            if len(fields) > 9 and fields[3] == "0A" and int(fields[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(f"socket:[{fields[9]}]")
    if not inodes:
        return None, None, None
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if not any(os.readlink(fd) in inodes for fd in (entry / "fd").iterdir()):
                continue
            name = (entry / "comm").read_text().strip() or None
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        except OSError:
            continue
        return int(entry.name), name, command or None
    return None, None, None


def _netstat_holder(port: int) -> tuple[int | None, str | None, str | None]:
    said = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10).stdout
    pid = None
    for line in said.splitlines():
        fields = line.split()
        if len(fields) == 5 and fields[3] == "LISTENING" and fields[1].rsplit(":", 1)[-1] == str(port):
            pid = int(fields[4])
            break
    if pid is None:
        return None, None, None
    listed = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                            text=True, timeout=10).stdout.strip()
    name = listed.split('","', 1)[0].strip('"') if listed.startswith('"') else None
    return pid, name, None


def rotate_token() -> str | None:
    """Replace the user's page token (``cadgen server --rotate-token``): every link shared before
    stops working, whichever installation's engine served it. The new token; None where there is no
    state folder to keep it in."""
    import secrets

    from cadgen.engine import registry

    held = registry.current()
    if held is None:
        return None
    token = secrets.token_urlsafe(32)
    held.put_token(token)
    return token


def others_running() -> list[Path]:
    """The doors (on Windows, port files) of the other installations' engines that answer in this
    engine folder: each serves with the token it read at its start."""
    from cadgen.engine import client

    ours = {_tag(protocol) for protocol in range(1, PROTOCOL + 1)}
    try:
        doors = sorted(state_dir().glob("*.port" if WINDOWS else "*.door"))
    except OSError:
        return []
    return [door for door in doors if door.stem not in ours and client._answering(door)]


class Daemon:
    def __init__(self, cap: int | None = None, port: int | None = None) -> None:
        self.port = port  # ``cadgen server --port``: the HTTP port this engine must take, or None
        self.port_source = ""  # where the HTTP port the server took came from (``bind``)
        self.port_because = ""  # a rolled port: who holds the default one
        self.port_notice = ""  # a start that moved the port: the line it says, once (``bind``)
        # That line when no request of a client bound the port -- a build's page did
        # (``models.register_page``): the next build's answer says it (``_serve``).
        self.unsaid = ""
        self.refusal: PortHeld | None = None  # its named port held by another process: it stops (``serve``)
        from cadgen.engine.serve import Pressure
        from cadgen.engine.worker import rss_cap_mb

        self.pool = Pool(cap or worker_cap(), self._start, self.connected, lambda worker: self.models.drain(worker),
                         rss_cap_mb)
        # The system's memory-pressure signal, the server's too once it runs (``serve``): under it the
        # pool sheds its standby and its least recently used workers (``Pool.shed``); as
        # ``CADGEN_ENGINE_PRESSURE`` says, where it is set (``Pressure.from_environment``).
        self.pressure = Pressure.from_environment()
        self.pool.pressed = self.pressure.under
        self.workers_lock = threading.Lock()  # each worker's ``held``
        self.born = time.time()
        # What the startup identity migration did (``identity.migrate``), which ``status`` says when it
        # did anything: a started engine's stderr is no one's.
        self.identity: dict[str, Any] | None = None
        self.last = time.monotonic()
        self.busy = 0
        self.busy_lock = threading.Lock()
        self.stopping = threading.Event()
        # The connections that hold the engine (``hold``: an agent host's MCP server, while the host
        # runs): while one is open, no other installation's engine retires this one (``bind``).
        self.holders = 0
        self.hosts: dict[str, int] = {}  # the holders per agent host they serve (``hold``)
        self.door = None  # on POSIX, the door clients reach it by (``door.Door``)
        # Where clients reach it (its door; on Windows its port file) and that file's identity
        # (``reached_by``): once it is gone or another's, no one can reach this engine, and it stops.
        self.address: Path | None = None
        self.address_id: tuple[int, int] | None = None
        self.server = None
        self.token = secrets.token_hex(16) if WINDOWS else ""
        # Per model document a build made (its ``model_id``), the worker that built it last: the one
        # that holds its provenance (``provenance``). A file the build wrote is no key: it names no model.
        self.builders: dict[str, Worker] = {}
        self.renders = None  # the served documents' render processes (``render.service.Renders``)
        self.serving = threading.Lock()
        from cadgen.engine.models import Models

        self.models = Models(self)

    def touch(self) -> None:
        self.last = time.monotonic()

    def stand(self) -> None:
        """At the daemon's start: the pool's standby, a worker with the kernel loaded
        (``Pool.stand``), so a new script's first build pays no kernel load -- nor, on a fresh
        installation, the operating system's first look at its native libraries (macOS checks each
        once: 43 s measured on a new uvx environment, against 2.5 s loaded again), which the standby
        pays while nobody waits. Started in the environment of the client that started the daemon
        (``environment``); each standby after it in that of the build that took the last one. And
        the bytecode folders of installations no daemon started in ``PYCACHE_UNUSED_DAYS`` go, in
        the background (``prune_bytecode``). With ``CADGEN_ENGINE_STANDBY=0`` (``standby``) the pool
        is given no standby to start: none stands by, and none replaces one."""
        prune_bytecode()
        if not standby():
            return
        self.pool.spare = self._spare
        self.pool.stand(self.environment())

    @staticmethod
    def environment() -> dict[str, str]:
        """The environment of the client that started the daemon, as near as the daemon can tell:
        its own, without the engine's folder its starter put first on ``PYTHONPATH``
        (``client._start``), so a caller's run shapes the interpreter as the standby's does."""
        env = dict(os.environ)
        root = engine_root()
        rest = [item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item and item != root]
        if rest:
            env["PYTHONPATH"] = os.pathsep.join(rest)
        else:
            env.pop("PYTHONPATH", None)
        return env

    def _spare(self, environment: dict[str, str]) -> Worker:
        """A standby (``Pool.stand``): a worker of no script yet, standing in the daemon's folder."""
        return Worker(STANDBY, environment, cwd=os.getcwd(), on_progress=self.progressed,
                      on_saved=self.models.cache.saved, standby=True)

    def hold(self, reader: Any, send: Callable[[dict[str, Any]], None], host: Any = None, holder: Any = None) -> None:
        """A hold on the engine (``{"op": "hold", "host": ..., "holder": ...}``): answered, then kept until
        its client goes (its end of file). While any is kept, another installation's engine that wants
        the port never retires this one: it rolls past it, or refuses a port it was named (``bind``).
        ``host``, the agent host the holder serves (its MCP server says it), is counted in ``status``
        (``hosts``): the ``cadgen`` command in that host's shell runs this installation. ``holder``, the
        name an MCP server holds with and opens its sessions under: once its client is gone -- a
        server that exits, or one killed before it could say goodbye -- those sessions end
        (``serve.Server.on_hold_end``)."""
        host = host if isinstance(host, str) and 0 < len(host) <= 64 else None
        holder = holder if isinstance(holder, str) and 0 < len(holder) <= 64 else None
        with self.busy_lock:
            self.holders += 1
            if host:
                self.hosts[host] = self.hosts.get(host, 0) + 1
        try:
            send({"ok": True})
            while reader.read(4096):
                pass  # a holder says nothing more: whatever it sends is read and dropped
        finally:
            with self.busy_lock:
                self.holders -= 1
                if host:
                    self.hosts[host] -= 1
                    if not self.hosts[host]:
                        del self.hosts[host]
            server = self.server
            if holder and server is not None:
                try:
                    server.on_hold_end(holder)
                except Exception:  # noqa: BLE001 - what the sessions could not end, their idle hour ends
                    pass
            self.touch()

    def connected(self, worker: Worker) -> bool:
        """A page watching any model document this worker built keeps its memo warm. A file a page
        watches keeps no worker, whichever model's run wrote it: a file names no model."""
        server = self.server
        return server is not None and any(self.builders.get(ident) is worker for ident in server.watched())

    def _start(self, script: str, environment: dict[str, str], cwd: str | None) -> Worker:
        return Worker(script, environment, cwd=cwd, on_progress=self.progressed,
                      on_saved=self.models.cache.saved)

    def progressed(self, _worker: Worker, frame: dict[str, Any]) -> None:
        """A worker's progress frame (``progress.py``): a build's wakes the pages waiting on the model
        document it builds (``serve.Server.building``). An export's or a snapshot's is the request's,
        never its document's build, and reaches its caller alone; a file a build writes is no document
        of the build's: a page serving it follows its bytes, and hears nothing of the run."""
        server = self.server
        if server is not None and frame.get("kind") == "build":
            documents = self.models.paths(_worker, frame.get("job"))
            if documents:
                server.building(frame, documents)

    def _built(self, worker: Worker, answer: dict[str, Any], *, verb: bool = False) -> None:
        """A request of ``worker`` answered: each model document it built is built no longer, and
        one whose model failed says what failed, and where (``serve.Server.built``); a file it wrote
        is told nothing.
        ``verb``: an export, a snapshot or a result asked of a document, whose failure -- a pose
        refused, a draw that failed, the worker gone -- is the request's, never its document's
        build: no document is marked failed by it (the worker's progress frame is its last
        build's, not this request's)."""
        self.models.register(worker, answer)
        server = self.server
        if server is None or (verb and "failed" in answer):
            return
        outcomes: dict[str, Any] = {}
        done = answer.get("done")
        reports = done.get("reports") if isinstance(done, dict) else done
        for report in reports if isinstance(reports, list) else []:
            frame = report.get("progress") or {}
            failed = None if report.get("ok") else {"model": report.get("model"), "error": report.get("error"),
                                                    "progress": frame}
            for ident in self.models.paths(worker, report.get("model")):
                outcomes[ident] = failed
            # Each child model the run built is a document of its own, built as its own row says: its
            # body's progress marked it building, and only this marks it built (or failed).
            for identity, child in (report.get("child_models") or {}).items():
                if child.get("id"):
                    outcomes[child["id"]] = None if child.get("ok") else {
                        "model": identity, "error": child.get("error"), "progress": frame}
        if "failed" in answer:
            frame = worker.progress or {}
            outcomes = {path: {"model": frame.get("job"), "error": answer["failed"], "progress": frame}
                        for path in [*outcomes, *self.models.paths(worker, frame.get("job"))]}
        if outcomes:
            server.built(outcomes)
        if not verb:
            # Each document the build made that an inspection has measured: its new parts measured once
            # its worker has settled, so the inspection after the edit finds them; one never inspected is
            # left alone (``serve.Server.measure_later``).
            server.measure_later([ident for ident, failed in outcomes.items() if failed is None],
                                 settled=lambda: (self.pool.free_for(worker) or 0.0) >= MEASURE_IDLE)

    @staticmethod
    def _where(error: Exception, worker: Worker | None) -> str:
        """A worker's failure, and where its build was when it failed."""
        from cadgen.engine.progress import describe

        frame = worker.progress if worker is not None else None
        return f"{error}, at {frame.get('job')}: {describe(frame)}" if frame else str(error)

    def lease(self, script: str, environment: dict[str, str], cwd: str | None = None,
              loading: Callable[[str], None] | None = None) -> Worker:
        """The warm worker of a script (by its path) or of the documents no worker built
        (``documents``), for one request: waiting its turn in the
        pool, started when none is alive (``Pool``); ``loading`` as there. ``release`` it after."""
        return self.pool.lease(script, environment, cwd, loading)

    def release(self, worker: Worker) -> None:
        self.pool.release(worker)

    def behind(self, key: str, send: Callable[[dict[str, Any]], None]) -> tuple[Worker, float] | None:
        """A build request that will wait for the build of its script already running (a rerun
        after a client its shell's time limit killed: that build goes on): said to its client at
        once, on stderr, and the running build's progress frames sent on to it until its own turn
        (``Worker.followers``). The worker and how long its build had run; None when none runs.
        Nothing is cancelled."""
        with self.pool.lock:
            worker = self.pool.live.get(os.path.normcase(key))
            began = worker.building if worker is not None and worker.leased else None
            if worker is None or began is None:
                return None
            worker.followers.append(send)
        ago = max(0.0, time.time() - began)
        send({"log": f"waiting for the build of {Path(worker.script).name} started {ago:.0f} s ago",
              "stream": "waiting"})
        if worker.progress:
            send({"progress": worker.progress})  # where it is now: the next frame may be a while
        return worker, ago

    def provenance(self, ident: str, key: str, kind: str, ordinal: int) -> dict[str, Any] | None:
        """What made one element of a served document (by its id), asked of the worker that built
        it (``Worker.where``): None for a document no live worker built -- one served cold."""
        worker = self.builders.get(ident)
        if worker is None or not self.pool.holds(worker):
            return None
        return worker.where(ident, key, kind, ordinal)

    def serve(self, request: dict[str, Any]) -> Any:
        """The daemon's server, started on the first request that needs one."""
        from cadgen.engine.serve import MESHES, Server, memory_budget

        started = False
        with self.serving:
            if self.refusal is not None:
                raise self.refusal  # stopping: its port is another's
            if self.server is None:
                host = request.get("host") or "127.0.0.1"
                try:
                    self.server, where = bind(
                        host, int(request["port"]) if request.get("port") else self.port,
                        lambda port, token: Server(port=port, three=request.get("three"), touch=self.touch,
                                                   provenance=self.provenance, cache=MESHES, isolated=True, host=host,
                                                   http_factory=HTTP_FACTORY, budget=memory_budget(), token=token))
                except PortHeld as refusal:
                    if request.get("port"):
                        # The request's own port (``cadgen viewer --port``): that request is refused,
                        # and the engine -- the builds and warm workers of its other clients -- runs
                        # on, unbound, for the next request that serves.
                        raise
                    # An engine whose own port is held (``cadgen server --port``, its
                    # ``CADGEN_ENGINE_PORT``) can never serve: it says why and stops, once the
                    # request that found it has its answer (``_serve``).
                    self.refusal = refusal
                    _note(str(refusal))
                    raise
                self.port_source, self.port_because = where["source"], where.get("because", "")
                self.port_notice = where.get("notice", "")
                if self.port_notice and request:
                    request["_notice"] = self.port_notice  # said by the client whose request bound it (``_serve``)
                elif self.port_notice:
                    self.unsaid = self.port_notice  # bound for a build's page: that build's answer says it
                # One pressure signal: under it the server trims its documents and the pool its workers.
                self.server.pressure = self.pressure
                self.server.pressed = lambda: self.pool.shed(True)
                self.server.lost = self.models.rebuild
                self.server.revive = self.models.adopt
                self.server.leaving = self.models.leaving
                self.server.delete = self.models.delete
                self.server.start()
                started = True
            elif ((request.get("port") and int(request["port"]) != self.server.port)
                  or (request.get("host") and request["host"] != self.server.http.server_address[0])):
                raise ValueError("the installation's engine already serves another host/port; stop it before changing its bind")
            server = self.server
        if started:
            self.models.attach(server)  # the documents taken up from the cache before it ran: registered with it
        return server

    def document(self, ident: str) -> tuple[dict[str, Any], bytes]:
        """What the document ``ident`` is while this engine holds it, as an export reads it, and the
        bytes it carries: a model a live worker holds (``{"script", "function", "held"}``, read from
        that worker, never built); one whose worker is gone but whose whole document the server
        holds (``{"document", "name"}``, its xbf bytes after it: the documents worker reads them as
        an on-disk xbf, and no worker of its script starts); a file this engine serves or served
        (``{"path"}``). Refused (``Models.not_held``), naming its state and the command that
        builds it again, for any other id: the engine runs nothing. A model document held on disk
        alone (the engine's cache) is its cache file's bytes, read as a held document's."""
        self.models.prune()
        record = self.models.held(ident)
        server = self.server
        if record is not None:
            self.models.cache.touch(ident)  # a read: its idle timer starts again
            worker = record["worker"]
            if worker is not None and self.pool.holds(worker):
                # Asked of the worker that built it (``via``: a child model's is its parent's script's).
                return {"script": record["source"]["script"], "function": record["source"]["name"], "held": ident,
                        "via": worker.script}, b""
            held = self.held_document(ident)
            if held is not None:
                source, data = held
                # Historical caches did not persist the folder relative closure paths used.
                # Keep the known identity/source anchor without inventing that missing base.
                return {**source, "origin": {"kind": "document", "id": ident,
                                             "script": record["source"]["script"], "closure_base": None}}, data
        if server is not None and ident in server.served and not isinstance(server.served[ident].path, str):
            return {"path": str(server.served[ident].path)}, b""
        known = server.file_of(ident) if server is not None else None
        if known is not None:
            return {"path": known}, b""
        raise self.models.not_held(ident)

    def held_document(self, ident: str) -> tuple[dict[str, Any], bytes] | None:
        """A model document the server holds whole and no worker does, as an export reads it: its
        source and its xbf bytes -- in memory, else its cache file's. ``ValueError`` for one held for
        viewing alone (its worker exited before it was drained, and no cache file has it), naming the
        command that builds it again. None when it is not held."""
        server = self.server
        doc = None
        if server is not None:
            with server.load_lock:
                doc = server.served.get(ident)
        if doc is None or doc.xbf is None:
            data = self.models.disk_bytes(ident)
            if data is not None:
                with self.models.lock:
                    record = self.models.records.get(ident)
                return {"document": ident, "name": record["source"]["name"] if record else ident}, data
        if doc is None:
            return None
        if doc.xbf is None:
            with self.models.lock:
                record = self.models.records.get(ident)
            name = record["source"]["name"] if record else ident
            raise ValueError(f"{name} ({ident}) is held for viewing only: its worker exited before the engine "
                             f"took it whole; run `{self.models.command(ident)}` to build it again")
        return {"document": ident, "name": doc.structure.get("name") or ident}, doc.xbf

    def _routed(self, request: dict[str, Any]) -> tuple[str, str | None]:
        """The worker a request goes to (its key) and the folder that worker starts in."""
        source = request.get("source") or {}
        if "document" in source:
            return "documents", request.get("cwd")  # a held document's bytes: no worker of its script
        if "path" in source:
            return "documents", request.get("cwd")  # a file, read as a file: no model's worker
        # A script's worker is keyed by its canonical path: a process key, not a document's id. A held
        # document is asked of the worker that built it (``via``), whatever script defines its model.
        return canonical(source.get("via") or request.get("via") or request.get("script") or source["script"]), None

    def _call(self, request: dict[str, Any], order: dict[str, Any], send: Callable[[dict[str, Any]], None],
              payload: bytes = b"") -> None:
        """An export or a result asked of the worker the request routes to (with ``payload``, the
        bytes its source carries, after its line); its answer sent."""
        with self.busy_lock:
            self.busy += 1
        try:
            key, cwd = self._routed(request)
            for attempt in (1, 2):
                worker = None
                try:
                    environment = request.get("env") or {}
                    # An export runs in its caller's environment (``worker.adopt``), as a build does.
                    ordered = {**order, "env": environment} if environment and order.get("op") == "export" else order
                    if request.get("expected") or (request.get("source") or {}).get("held"):
                        # Viewer exports and a document named by its id borrow the held document's
                        # worker, including its environment: another caller's environment must not
                        # evict it (a different one starts a fresh worker, which holds nothing).
                        with self.pool.lock:
                            held = self.pool.live.get(os.path.normcase(key))
                            environment = held.environment if held else self.environment()
                        ordered = order
                        if held is None and "script" in request["source"]:
                            named = request["source"].get("held")
                            send(refused(self.models.not_held(named)) if isinstance(named, str) else
                                 {"failed": "The viewed model is no longer held. Reopen it before exporting."})
                            return
                    worker = self.lease(key, environment, cwd)
                    expected = request.get("expected") or {}
                    if "modelRevision" in expected and "document" not in request["source"]:
                        # The lease excludes a rebuild: validate the generation here. A run that
                        # changed nothing kept it (``Models.register``); any other is a new one.
                        with self.models.lock:
                            model = self.models.records.get(expected.get("id") or "")
                            matches = (model is not None and model["worker"] is worker
                                       and model["version"] == expected["modelRevision"])
                        if not matches:
                            send({"failed": "The source changed. Open Export again to use the displayed revision."})
                            return
                    answer = worker.build(ordered, send, payload)
                    held = (request.get("source") or {}).get("document")
                    if held and answer.get("kind") == UNREADABLE:
                        # The bytes a held document was read from (its cache file's) do not read.
                        answer = refused(self.models.unreadable(str(held), str(answer.get("failed"))))
                    returned = answer.pop("payload", b"")
                    if returned:
                        import base64

                        answer["payload"] = base64.b64encode(returned).decode("ascii")
                    if not request.get("expected"):
                        self._built(worker, answer, verb=True)
                    send(answer)
                    return
                except WorkerGone as error:
                    if attempt == 2 or "during the build" in str(error):
                        failed = {"failed": self._where(error, worker)}
                        if worker is not None and not request.get("expected"):
                            self._built(worker, failed, verb=True)
                        send(failed)
                        return
                finally:
                    if worker is not None:
                        self.release(worker)
        finally:
            with self.busy_lock:
                self.busy -= 1
            self.touch()

    def handle(self, request: dict[str, Any], send: Callable[[dict[str, Any]], None]) -> None:
        """One request, answered through ``send``. One that serves -- binding the HTTP server, a
        launch, a page's read -- counts in ``status``'s ``busy`` until it is answered, as builds and
        draws do: another installation's engine starting meanwhile never retires this one under it
        (``_holder``, ``retire_older``: both read ``busy`` through ``_uses``)."""
        if request.get("op") not in SERVING:
            return self._handle(request, send)
        with self.busy_lock:
            self.busy += 1
        try:
            self._handle(request, send)
        finally:
            with self.busy_lock:
                self.busy -= 1
            self.touch()

    def _handle(self, request: dict[str, Any], send: Callable[[dict[str, Any]], None]) -> None:
        self.touch()
        op = request.get("op")
        if op == "reattach":
            # A worker's models with nothing to take up, before it reads their cache (``build._reattach``).
            sources = request.get("models")
            if not isinstance(sources, list) or not all(
                    isinstance(row, dict) and isinstance(row.get("script"), str) and isinstance(row.get("name"), str)
                    for row in sources):
                send(refused(ValueError("reattach takes models: [{script, name, ...}]")))
                return
            try:
                send({"ok": True, "lines": self.models.reattach(sources, request.get("pid"))})
            except (OSError, ValueError) as error:
                send(refused(error))
            return
        if op == "models":
            send({"ok": True, "models": self.models.listing()})
            return
        if op == "delete":
            # ``cadgen delete`` (``api.delete``): each id deleted by the one deletion (``models.delete``).
            deleted = [self.models.delete(str(ident)) for ident in request.get("ids") or []]
            send({"ok": True, "deleted": [found for found in deleted if found is not None]})
            return
        if op == "model_info":
            self.models.prune()
            ident = str(request.get("id"))
            with self.models.lock:
                record = self.models.records.get(ident)
            if record is None:
                self.models.adopt(ident)  # held on disk (the engine's cache), after a restart
                with self.models.lock:
                    record = self.models.records.get(ident)
            if record is None:
                send(refused(self.models.not_held(ident)))
            else:
                model = {key: record.get(key) for key in ("id", "source", "program", "builtAt", "version", "files",
                                                          "kind")}
                model["state"] = self.models.state(ident)
                # On disk in the engine's cache, at its revision: a restart reopens it as last built.
                model["cached"] = (self.models.where(ident) or "").endswith("disk")
                if model["state"] == "held":
                    model["held"] = self.models.where(ident)
                lost = self.models.rebuild(ident)
                if lost is not None:
                    model["rebuild"] = lost["rebuild"]
                send({"model": model})
            return
        if op == "document":
            # What an id names while this engine holds it (``document``), asked without building.
            try:
                send({"ok": True, "document": self.document(str(request.get("id")))[0]})
            except ValueError as error:
                send(refused(error))
            return
        if op == "state":
            # What the engine knows of a document by its id: held or not, and what builds it again.
            ident = str(request.get("id"))
            self.models.prune()
            lost = self.models.rebuild(ident)
            state = self.models.state(ident) if lost is None else lost["state"]
            held = {"held": self.models.where(ident)} if state == "held" else {}
            send({"ok": True, "state": state, **held,
                  **({"rebuild": lost["rebuild"], "error": lost["error"]} if lost else {})})
            return
        payload = b""
        if op == "export" and "id" in (request.get("source") or {}):
            ident = str(request["source"]["id"])
            try:
                cached = self.models.cache.registry()
                if cached is not None:
                    original = cached.cache.path(self.models.cache.inside(ident)).resolve()
                    if any(Path(path).resolve() == original for path in request["destinations"]):
                        from cadgen.engine.export import ExportRefused

                        raise ExportRefused("export to a different path; the engine's cached document is preserved")
                source, payload = self.document(ident)
            except ValueError as error:
                send(refused(error))
                return
            expected = request.get("expected") or {}
            if "document" in source and "modelRevision" in expected:
                # The viewer's export of a model whose worker is gone reads the whole document the
                # server holds, at the revision the page shows: checked here, as no worker holds it.
                with self.models.lock:
                    record = self.models.records.get(ident)
                served = self.server.served.get(ident) if self.server is not None else None
                if served is None and self.server is not None and self.server.holds(ident):
                    served = self.server.document(ident)  # held on disk: read again to check its revision
                if (record is None or served is None or record["version"] != expected["modelRevision"]
                        or served.structure.get("exportRevision") != expected.get("digest")):
                    send({"failed": "The source changed. Open Export again to use the displayed revision."})
                    return
            request = {**request, "source": source}
        if op == "export" and "script" in (request.get("source") or {}) and not request["source"].get("held") \
                and not request.get("expected"):
            # A model is exported by its call's document (``api._called``): never built by an export.
            send(refused(ValueError("an export reads a document: call the model, then export its handle or id")))
            return
        if op == "export":
            order = {"id": 1, "op": "export", "source": request["source"], "destinations": request["destinations"],
                     "cwd": request.get("cwd"),
                     "draw": request.get("draw"), "draw_still": request.get("draw_still"),
                     "expected": request.get("expected"), "original": request.get("original")}
            return self._call(request, order, send, payload)
        if op == "result" and "id" in request:
            # A handle's shape (``api.Document.shape``): the document its id names, as the engine
            # holds it -- asked of the worker that holds it, or read from the bytes the engine holds --
            # and never built.
            ident = str(request["id"])
            try:
                source, payload = self.document(ident)
            except ValueError as error:
                send(refused(error))
                return
            if "document" in source:
                order = {"id": 1, "op": "result", "document": True, "name": source["name"], "cwd": request.get("cwd")}
            elif "script" in source:
                order = {"id": 1, "op": "result", "script": source["script"], "name": source["function"],
                         "cwd": request.get("cwd")}
            else:
                send({"failed": f"{ident} is a file's document: read_xbf or read_step reads its shape"})
                return
            return self._call({**request, "source": source}, order, send, payload)
        if op == "result":
            order = {"id": 1, "op": "result", "script": request["script"], "name": request["name"],
                     "cwd": request.get("cwd")}
            return self._call(request, order, send)
        if op == "shape":
            # A shape handed over (``api.hand_over``): held as a drained document is, nothing to run.
            try:
                send(self.models.hand_over(request))
            except ValueError as error:
                send(refused(error))
            return
        if op == "build":
            with self.busy_lock:
                self.busy += 1
            try:
                script = request["script"]
                key, cwd = self._routed(request)
                for attempt in (1, 2):
                    worker = None
                    ahead = self.behind(key, send) if attempt == 1 else None
                    waited = time.monotonic()
                    try:
                        try:
                            worker = self.lease(key, request.get("env") or {}, cwd,
                                                lambda text: send({"log": text, "stream": "notice"}))
                        finally:
                            if ahead is not None and send in ahead[0].followers:
                                ahead[0].followers.remove(send)
                        fresh = worker.builds == 0
                        order = {"id": 1, "op": "build", "script": script, "functions": request.get("functions"),
                                 "cwd": request.get("cwd"), "verify": bool(request.get("verify")),
                                 "profile": bool(request.get("profile")), "run": request.get("run")}
                        if request.get("env"):
                            order["env"] = request["env"]  # the run's own (``worker.adopt``)
                        cached = self.models.cache.folder()
                        if cached is not None:
                            order["cache"] = cached  # what a fresh worker takes a model from, by its key
                        answer = worker.build(order, send)
                        answer["worker"] = {"pid": worker.pid, "fresh": fresh}
                        if ahead is not None:
                            # The build it waited for, the one its own replays: began how long before it asked.
                            for report in answer.get("done") or []:
                                if isinstance(report, dict):
                                    report["waited"] = {"script": Path(ahead[0].script).name, "ago": round(ahead[1]),
                                                        "seconds": round(time.monotonic() - waited, 1)}
                        # The program that asked: what a document it built names to build it again.
                        answer["program"] = request.get("program")
                        self._built(worker, answer)
                        send(answer)
                        return
                    except WorkerGone as error:
                        if attempt == 2 or "during the build" in str(error):
                            failed = {"failed": self._where(error, worker)}
                            if worker is not None:
                                self._built(worker, failed)
                            send(failed)
                            return
                    finally:
                        if worker is not None:
                            self.release(worker)
            finally:
                with self.busy_lock:
                    self.busy -= 1
                self.touch()
        elif op == "serve":
            server = self.serve(request)
            named = str(request["path"])
            try:
                if not is_id(named):
                    ident = server.add(Path(named))
                elif self.models.held(named) is not None:
                    server, ident = self.models.serve(named)
                else:
                    found, _payload = self.document(named)  # a file this engine knows by its id, or refused
                    ident = server.add(Path(found["path"]))
            except Exception as error:  # noqa: BLE001
                from cadgen.engine.serve import NotHeld

                # A document id the engine does not hold is a refusal: its state and the command
                # that builds it again travel with it, and the caller raises it as its type.
                send(refused(error) if isinstance(error, NotHeld) else {"failed": f"cannot serve {named}: {error}"})
                return
            app = getattr(server.http, "app", None)
            token = app.token if app is not None else ""
            send({"ok": True, "url": self.models.url(server, ident), "doc": ident, "token": token,
                  "port": server.port})
        elif op in ("viewer", "http"):
            server = self.serve(request)
            application = getattr(server.http, "app", None)
            if application is None:
                send({"failed": "this engine has no application host"})
            else:
                send(application.launch(request) if op == "viewer" else application.endpoint())
        elif op == "read":
            # A document's JSON read (``/api/doc/<id>...``), answered in process: ``inspect``'s,
            # through the door, so it needs no loopback socket of the client's.
            route = str(request.get("route") or "")
            if not route.startswith("/api/doc/"):
                send({"failed": f"not a document read: {route!r}"})
                return
            # Asked with ``progress``, a read of the parts' facts says each part's as it comes in, on
            # this request's channel ahead of its answer (``serve.Server.measure``): the summary's count.
            counted = ((lambda done, total, key: send({"progress": {"done": done, "total": total, "key": key}}))
                       if request.get("progress") else None)
            status, body = self.serve(request).read(route, counted)
            send({"ok": True, "status": status, "body": body.decode("utf-8")})
        elif op == "draw":
            self.draw(request, send)
        elif op == "warm":
            # The viewer at its launch: the server, its meshing processes and a STEP reader started
            # while nobody waits, so a page's first document waits on none of them.
            self.serve(request).warm()
            send({"ok": True})
        elif op == "status":
            send(self.status())
        elif op == "pid":
            send({"ok": True, "pid": os.getpid()})  # who answers: a client that started a daemon asks
        elif op == "stop":
            send({"ok": True})
            self.stopping.set()
        else:
            send({"failed": f"unknown request {op!r}"})

    def draw(self, request: dict[str, Any], send: Callable[[dict[str, Any]], None]) -> None:
        """A picture of a document (``{"op": "draw", "path", "still", "out"}``, a ``snapshot.Still``
        and the picture's path): served, meshed by the daemon's pool, drawn by its render process;
        answered with the PNG (base64) and what was drawn, or refused by name. Where it is goes to the
        caller as it draws, a snapshot's progress frames (``progress.py``: ``scene`` while the
        document is served, meshed and held by its render process, ``draw`` while the frame is drawn),
        as a build's frames go to its caller."""
        from cadgen.engine.progress import Progress
        from cadgen.engine.render.service import Refused, Renders, answer_png

        with self.busy_lock:
            self.busy += 1
        said = Progress(lambda frame: send({"progress": frame}), kind="snapshot", job=Path(request["path"]).name,
                        outputs=[request["out"]] if request.get("out") else [])
        try:
            server = self.serve(request)
            with self.serving:
                if self.renders is None:
                    self.renders = self.pool.renders = Renders(server)
            try:
                data, report = self.renders.draw(Path(request["path"]), request["still"], said)
            except Refused as error:
                send({"refused": str(error)})
                return
            except Exception as error:  # noqa: BLE001 - a picture that could not be drawn is the answer
                send({"failed": f"{type(error).__name__}: {error}"})
                return
            send({"ok": True, "report": report, "png": answer_png(data)})
        finally:
            said.close()
            with self.busy_lock:
                self.busy -= 1
            self.touch()
            self.pool.shed()  # its render process measured again: the workers' memory to its cap

    def status(self) -> dict[str, Any]:
        """The daemon, its workers (each its script, its builds, its memory after its last build
        in MiB, how long it has been busy or idle, and a busy one's last progress frame), its
        standby (never a script's worker: its process, its memory, how long it has stood by), the
        pool's memory against its cap, the requests waiting for one, the last retirements, and what
        it serves and draws."""
        from cadgen.engine.previous import version
        from cadgen.engine.worker import rss_cap_mb

        now = time.monotonic()
        server = self.server
        workers = [{"script": w.script, "pid": w.pid, "builds": w.builds, "alive": w.alive() and not w.retired,
                    "busy": w.leased, "rssMb": None if w.rss is None else round(w.rss),
                    "seconds": round(now - (w.since if w.leased else w.used), 1),
                    "progress": w.progress if w.leased else None} for w in self.pool.workers()]
        with self.pool.lock:
            spare, readying = self.pool.standby, self.pool.readying is not None
        standby = ({"pid": spare.pid, "rssMb": None if spare.rss is None else round(spare.rss),
                    "seconds": round(time.time() - spare.started, 1)} if spare is not None
                   else {"pid": None, "rssMb": None, "seconds": None, "starting": True} if readying else None)
        # What uses it, which another installation's engine asks before it retires this one (``bind``):
        # its holds, the documents pages watch, its builds and draws, and HTTP work underway.
        return {"ok": True, "pid": os.getpid(), "version": version(), "installation": installation(),
                "up": round(time.time() - self.born, 1),
                "workers": workers, "standby": standby, "cap": self.pool.cap, "waiting": self.pool.waiting(),
                "rssMb": round(self.pool.resident()), "rssCapMb": rss_cap_mb(), "retired": list(self.pool.retired),
                "idle": round(now - self.last, 1), "holders": self.holders, "hosts": dict(self.hosts),
                "busy": self.busy, "prefix": sys.prefix,
                "watched": 0 if server is None else len(server.watched()),
                "active": server is not None and bool(server.clients_active()),
                "serving": None if self.server is None else {"url": self.server.url, "port": self.server.port,
                                                             "portSource": self.port_source,
                                                             "portBecause": self.port_because,
                                                             "portNotice": self.port_notice,
                                                             "defaultPort": default_port(),
                                                             "documents": self.server.listing(every=True),
                                                             "memory": self.server.memory()},
                "models": self.models.listing(),
                "cache": self.models.cache.status(),
                "identity": self.identity if self.identity and any(self.identity.values()) else None,
                "renders": [] if self.renders is None else self.renders.status(),
                "sessions": (self.server.http.app.sessions() if self.server is not None
                             and hasattr(self.server.http, "app") else [])}

    def watch(self) -> None:
        while not self.stopping.wait(TEND_SECONDS):
            self.tend()

    def reached_by(self, address: Path) -> None:
        """Clients reach this engine at ``address`` from now on (``tend`` watches it)."""
        self.address, self.address_id = address, _identity(address)

    def tend(self) -> None:
        """What the engine looks after, each ``TEND_SECONDS``: never the process, and nothing by how
        long anything has been idle. A killed client's pipes are swept, and the workers' memory is
        held to its cap and the system's pressure (``Pool.shed``: its documents drained first, so they
        stay held); the memory budget sends unwatched documents out of memory, least recently used
        first, to the cache, as they are loaded (``serve.Server.trim``). The engine stops on ``stop``, a terminate, another installation's
        retiring it (``bind``), and here when its door is gone (its folder removed, a temporary
        folder cleaned up) or another's: no one can reach it, so it stops as ``stop`` does, saving
        what it holds to the cache."""
        if self.address is not None and _identity(self.address) != self.address_id:
            self.stopping.set()
            return
        if self.door is not None:
            self.door.sweep()
        self.pool.shed(self.pressure.under())
        self.models.prune()

    def shutdown(self) -> None:
        # The documents built or read in the last idle window, saved first, best effort (``cache``).
        self.models.cache.final()
        self.pool.stop()
        if self.renders is not None:
            self.renders.stop()
        if self.server is not None:
            self.server.stop()


# How long a connection to the Windows loopback port has to show its token: anyone on the machine can
# connect there, so nothing more is read, or waited for, until it has.
AUTH_SECONDS = 10.0


def _admitted(daemon: Daemon, connection: socket.socket, stream: Any) -> bytes | None:
    """On Windows, the request line's first bytes: the client puts its token first
    (``{"token": "<token>", ...``, ``client._exchange``), so a peer without it is refused after
    those few bytes and ``AUTH_SECONDS`` at most, before the line is read or parsed. None: refused."""
    import hmac

    expected = b'{"token": "' + daemon.token.encode("ascii") + b'"'
    connection.settimeout(AUTH_SECONDS)
    prefix = stream.read(len(expected))
    if not daemon.token or not hmac.compare_digest(prefix, expected):
        return None
    connection.settimeout(None)
    return prefix


def _serve(daemon: Daemon, reader: Any, writer: Any, prefix: bytes = b"") -> None:
    """One connection: its request line (after ``prefix``, what the Windows check read of it), and
    every answer line the request sends. A hold keeps the connection until its client goes."""
    line = prefix + reader.readline()
    if not line:
        return
    request = json.loads(line)
    if WINDOWS and request.get("token") != daemon.token:
        return
    lock = threading.Lock()

    def send(message: dict[str, Any]) -> None:
        if "log" not in message and set(message) != {"progress"}:
            if "_notice" in request:
                message = {**message, "notice": request.pop("_notice")}  # its answer carries it: said once
            elif daemon.unsaid and request.get("op") == "build":
                notice, daemon.unsaid = daemon.unsaid, ""
                message = {**message, "notice": notice}
        with lock:
            writer.write((json.dumps(message, separators=(",", ":")) + "\n").encode())
            writer.flush()

    if request.get("op") == "hold":
        daemon.hold(reader, send, request.get("host"), request.get("holder"))
        return
    try:
        daemon.handle(request, send)
    except (OSError, ValueError) as error:
        send({"failed": str(error)})
    finally:
        if daemon.refusal is not None:
            daemon.stopping.set()  # its answer sent: the engine whose port is another's stops


def _serve_door(daemon: Daemon, ident: str) -> None:
    """A connection through the door (POSIX): the hello's pair answered (``door.answer``)."""
    from cadgen.engine import door

    def serve(reader: Any, writer: Any) -> None:
        try:
            _serve(daemon, reader, writer)
        except (OSError, ValueError):
            pass  # the client went, or sent no request

    door.answer(state_dir() / door.CLIENTS, ident, serve)


def _serve_connection(daemon: Daemon, connection: socket.socket) -> None:
    """A connection to the Windows loopback port: its token shown first (``_admitted``), then served."""
    with connection:
        stream = connection.makefile("rwb")
        try:
            admitted = _admitted(daemon, connection, stream)
            if admitted is None:
                return
            _serve(daemon, stream, stream, admitted)
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass


def _bind() -> socket.socket:
    """Windows' listener: a loopback port (its port file names it, and the token a client shows)."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    return server


def _can_listen() -> None:
    """Raise when this process may not listen on a loopback port, as the engine's HTTP server
    must: a sandbox that refuses sockets (macOS Seatbelt answers EPERM) would let a daemon make
    its door and then fail every build, so none starts there. The port is bound and let go."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", 0))  # refused where listening would be: Seatbelt refuses the bind
    finally:
        probe.close()


def lock(path: Path | None = None) -> Any:
    """The daemon's lock (or another protocol's, at ``path``), held for its life; None when
    another daemon holds it. A lock file is removed by whoever holds it (``let_go``, ``sweep_dead``),
    so a lock taken on a file whose name has gone, or names another file now, is no lock: it is let
    go and the file the name names now is taken instead (``_names``)."""
    state_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    refusal = folder_refusal(state_dir())
    if refusal is not None:
        raise PermissionError(refusal)
    path = path or lock_path()
    while True:
        handle = open(path, "a+")
        try:
            if WINDOWS:
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            gone = not _names(handle, path)  # its holder removed it as this opened it: open it again
            handle.close()
            if gone:
                continue
            return None
        if _names(handle, path):
            return handle
        handle.close()  # taken as its last holder removed it: the name is another file's, or none


def _names(handle: Any, path: Path) -> bool:
    """Whether ``path`` still names the file ``handle`` holds open. On Windows an open file is never
    removed, so it does."""
    if WINDOWS:
        return True
    try:
        held, named = os.fstat(handle.fileno()), os.lstat(path)
    except OSError:
        return False
    return (held.st_dev, held.st_ino) == (named.st_dev, named.st_ino)


def let_go(held: Any, *, failed: bool = False) -> None:
    """This daemon's files gone as it lets go of its lock: its port file and, unless it ``failed``
    (its client reads why there), its failure note, then the lock file itself -- on POSIX removed
    while it is still held, so no daemon starting meanwhile can take a lock on a file that is gone
    (``lock`` takes the one the name names); on Windows, where a file open is never removed,
    once it is let go. The door is gone already (``Door.close``)."""
    for path in (port_path(), *(() if failed else (failure_path(),))):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    _drop_lock(held, lock_path())


def _drop_lock(held: Any, path: Path) -> None:
    """The lock ``held`` (on ``path``) let go, and its file removed (see ``let_go``)."""
    if not WINDOWS and _names(held, path):
        try:
            path.unlink()
        except OSError:
            pass
    held.close()
    if WINDOWS:
        try:
            path.unlink()
        except OSError:
            pass  # another opened it meanwhile: its file now


# A file of one engine in the engine folder: its tag (``_tag``; an early engine's socket under a
# longer name) and what it is -- its lock, its door, its port file (Windows' address, or an early
# engine's), its failure note, a port file being written, an early engine's socket.
_ENGINE_FILE = re.compile(r"(?P<tag>[0-9a-f]{12}|[0-9a-f]{16})\.(?P<kind>lock|door|port|failed|tmp|sock)")
# How long a dead engine's failure note (and a port file it was writing) stays: the client that
# started it reads the note as the engine exits (``client._not_started``).
NOTE_KEPT_SECONDS = 120.0


def sweep_dead(folder: Path | None = None, now: float | None = None) -> list[str]:
    """The files in the engine folder of every engine that is dead, removed, as a daemon starts: an
    engine killed, or one before engines removed their own files (``let_go``). An engine is dead
    when its lock is free (taken here while its files go, so none starts between) and nothing
    answers at its door, port file or socket; without a lock file, when nothing answers there. A
    live engine's files are never touched, nor this daemon's, nor a failure note or a port file
    being written younger than ``NOTE_KEPT_SECONDS``. Its folder's other files (``clients/``, a
    browser's redirect page) are not an engine's. The paths removed."""
    folder = folder or state_dir()
    now = time.time() if now is None else now
    if folder_refusal(folder) is not None:
        return []  # a folder another can change: nothing in it is this user's daemon's to remove
    engines: dict[str, dict[str, Path]] = {}
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return []
    for entry in entries:
        found = _ENGINE_FILE.fullmatch(entry.name)
        if found is not None:
            engines.setdefault(found["tag"], {})[found["kind"]] = Path(entry.path)
    removed: list[str] = []
    for tag, files in sorted(engines.items()):
        if tag == _tag():
            continue  # this daemon's: it holds the lock
        held = None
        if "lock" in files:
            try:
                held = lock(files["lock"])
            except OSError:
                continue
            if held is None:
                continue  # its engine holds it: starting, running or stopping
        try:
            if _live(files):
                continue
            for kind, path in sorted(files.items()):
                if kind == "lock" or (kind in ("failed", "tmp") and _younger(path, now)):
                    continue
                try:
                    path.unlink()
                    removed.append(str(path))
                except OSError:
                    pass
        finally:
            if held is not None:
                there = files["lock"].exists()
                _drop_lock(held, files["lock"])
                if there and not files["lock"].exists():
                    removed.append(str(files["lock"]))
    return removed


def _live(files: dict[str, Path]) -> bool:
    """Whether an engine answers at any of ``files``: its door takes a writer, its port a
    connection (Windows), its socket a connection (an early engine's)."""
    from cadgen.engine import client

    if "door" in files and not WINDOWS and client._answering(files["door"]):
        return True
    if "port" in files and WINDOWS and client._answering(files["port"]):
        return True
    if "sock" in files and not WINDOWS:
        return any(_listened(files["sock"]) for _ in range(2))  # refused twice: a full backlog refuses too
    return False


def _listened(path: Path) -> bool:
    """Whether a connection to the socket at ``path`` is not refused (an early engine's)."""
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    probe.settimeout(0.5)
    try:
        probe.connect(str(path))
    except (ConnectionRefusedError, FileNotFoundError):
        time.sleep(0.1)
        return False  # nobody listens: a dead engine's
    except OSError:
        return True  # refused by the system, or too long a name: not this sweep's to judge
    finally:
        probe.close()
    return True


def _younger(path: Path, now: float) -> bool:
    try:
        return now - os.lstat(path).st_mtime < NOTE_KEPT_SECONDS
    except OSError:
        return False


def _identity(path: Path) -> tuple[int, int] | None:
    """The file at ``path`` (not a link it names): its device and inode, or None when there is none."""
    try:
        found = os.lstat(path)
    except OSError:
        return None
    return found.st_dev, found.st_ino


def main(argv: list[str] | None = None, *, port: int | None = None, rotate: bool = False,
         foreground: bool = False) -> int:
    """Run the engine here. ``port``: the HTTP port it must take (``cadgen server --port``);
    ``rotate``: a new page token first (``--rotate-token``), refused while another engine runs;
    ``foreground`` (``cadgen server``): its HTTP server bound before anything else, so a port
    another process holds fails the command at once (``bind``). An engine a client starts binds
    on the first request that serves, which may name its own port (``cadgen viewer --port``)."""
    from cadgen.engine.serve import Pressure

    try:
        Pressure.override(os.environ)
    except ValueError as error:  # refused at the start, in its one line, before anything is held
        _note(str(error))
        return 1
    bytecode(os.environ)  # its own (``client._start`` set it), or made here: a daemon run in the foreground
    sys.pycache_prefix = os.environ.get("PYTHONPYCACHEPREFIX") or None
    sys.dont_write_bytecode = sys.pycache_prefix is None
    try:
        held = lock()
    except OSError as error:
        _note_failure(f"the engine server cannot take its lock in {state_dir()}", error)
        return 1
    if held is None:
        if rotate:
            print("cadgen: an engine server is running; run cadgen stop first, then cadgen server --rotate-token",
                  file=sys.stderr)
            return 1
        if foreground:  # ``cadgen server``: said, never a silent success that serves nothing it asked
            print("cadgen: this installation's engine server is already running: `cadgen status` says where it "
                  "serves, `cadgen stop` stops it" + (f" (to serve on {port})" if port is not None else ""),
                  file=sys.stderr)
            return 1 if port is not None else 0
        return 0  # another daemon is up
    if rotate:
        others = others_running()
        if others:
            print("cadgen: another installation's engine server is running, serving with the token: stop it "
                  f"first ({', '.join(str(door) for door in others)}), then cadgen server --rotate-token", file=sys.stderr)
            let_go(held)
            return 1
        try:
            if rotate_token() is None:
                raise OSError("no state folder")
        except OSError as error:
            print(f"cadgen: cannot replace the page token: {error.strerror or error}", file=sys.stderr)
            let_go(held)
            return 1
        print("cadgen: a new page token: every link shared before no longer works", file=sys.stderr)
    try:
        listener = _bind() if WINDOWS else None
        if listener is not None:
            listener.listen(64)
        else:
            _can_listen()
    except OSError as error:
        _note_failure("the engine server cannot listen on a local port", error)
        let_go(held, failed=True)
        return 1
    # The files of engines that died without removing theirs, swept while this one starts.
    threading.Thread(target=sweep_dead, daemon=True).start()
    daemon = Daemon(port=port)

    # And the records from before namespace/name identity brought to it, once (``identity.migrate``:
    # JSON and file names, no XBF, independent of the closure's pass). It never keeps the engine
    # from starting.
    from cadgen.engine.identity import migrate

    try:
        daemon.identity = migrate(daemon.models.registry())
    except Exception as error:  # noqa: BLE001
        daemon.identity = {"filled": 0, "moved": 0, "skipped": [f"the pass failed: {type(error).__name__}: {error}"]}
        print(f"cadgen: identity migration failed: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
    daemon.stand()
    if foreground:
        try:
            daemon.serve({})
        except ValueError as error:  # a port held (``PortHeld``, noted by ``serve``) or refused
            if not isinstance(error, PortHeld):
                _note(str(error))
            daemon.shutdown()
            if listener is not None:
                listener.close()
            let_go(held, failed=True)
            return 1
        for said in daemon.port_notice.splitlines():
            print(f"cadgen: {said}", file=sys.stderr)  # ``cadgen server``'s terminal
            daemon.unsaid = ""
    if not WINDOWS:
        import signal

        # A terminate (a logout, ``kill``) stops the daemon as ``cadgen stop`` does: its workers,
        # pools, door and listener go with it. A client gone mid-answer is a write's BrokenPipeError.
        signal.signal(signal.SIGTERM, lambda _signum, _frame: daemon.stopping.set())
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    threading.Thread(target=daemon.watch, daemon=True).start()
    failed = False  # its door could not be made: its note says why, and stays
    try:
        if listener is not None:
            port = listener.getsockname()[1]
            temporary = port_path().with_suffix(".tmp")
            temporary.write_text(f"{port} {daemon.token}\n", encoding="utf-8")
            replace_atomic(temporary, port_path())
            daemon.reached_by(port_path())
            listener.settimeout(0.5)
            while not daemon.stopping.is_set():
                try:
                    connection, _address = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                connection.settimeout(None)
                threading.Thread(target=_serve_connection, args=(daemon, connection), daemon=True).start()
        else:
            from cadgen.engine.door import Door

            try:
                daemon.door = Door(door_path(), lambda ident: _serve_door(daemon, ident))
                daemon.reached_by(door_path())
            except OSError as error:
                _note_failure(f"the engine server cannot make its door {door_path()}", error)
                failed = True
                return 1
            daemon.stopping.wait()
    finally:
        if listener is not None:
            listener.close()
        if daemon.door is not None:
            daemon.door.close()  # first: no hello is taken while the rest stops
        daemon.shutdown()
        # Its port file, its failure note but a failure's, and its lock: nothing of it stays behind.
        let_go(held, failed=failed or daemon.refusal is not None)
    return 1 if daemon.refusal is not None else 0


if __name__ == "__main__":
    sys.exit(main())
