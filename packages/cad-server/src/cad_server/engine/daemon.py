"""The engine daemon: one per device -- its engine folder's one door, lock and port file, the current
installation's engine, which every client starts or attaches to (``client``) --, started on demand,
and never stopped by a timer: it stops on ``cad stop`` (or a terminate), once it has drained for
an update (``drain``: nothing in flight, then the switch's helper starts the next release's), when its
door is gone and no one can reach it (``tend``), and with the machine. Idleness sheds memory instead.

Every process it starts is a service it declares (``services``): a model script's warm worker (the
documents worker among them) and a served document's render process. One supervisor runs them by
those declarations (``supervisor.Supervisor``, ``Daemon.supervisor``), and the daemon binds its hooks
to them by name: the drain, what a page watches, the progress that wakes pages, the cache's ``saved``.
A request leases its service's process for itself, one request at a time per process, first come
first served, keyed as the service declares: a worker by its script's path, a render process by its
document's id. A build names the Python its script was run with (``contract.interpreter``): one whose
environment is not the base the server's kernel processes run in gets a worker of that Python's own,
keyed by its script and that Python, so the packages of the environment the script was launched from
import in its worker (``caller``); one whose worker contract is not the server's is refused in one line
before any worker starts, naming which side to update and to what release (``contract.refusal``). The
services that count -- the workers -- are held to ``CAD_ENGINE_WORKERS`` processes
alive (by default, the machine's cores): a build for a script with a live worker waits for it while
it is busy; one for a script with none starts one when fewer than the cap are alive; at the cap the
least recently used idle worker no page watches is retired first (its stdin closed: it exits), and
when every idle worker is watched the new one starts past the cap; with every worker busy, the build
waits, first come first served, for the first to come free. Nothing is refused, and nothing is
predicted: no admission. A render process does not count.

No timer retires a process: memory alone does (``Supervisor.shed``). Each process's resident memory,
as it last said it (its ``ready`` frame and each answer's ``rssMb``), is held with the others' to one
cap (``CAD_ENGINE_WORKER_RSS_MB``, ``worker.rss_cap_mb``). Past it, or under the system's
memory-pressure signal (``serve.Pressure``), idle processes are retired in the order their
declarations rank them, least recently used first within a rank: the standby, then render processes,
then the workers no page watches, and a watched one only when no other is left. A process that says,
answering, that it alone is over the cap (``retire``: ``worker.retirement``) is retired once its
request is done. Before a worker is stopped, every document of it the server does not hold is taken
from it (``models.Models.drain``): a document outlives its worker. A retired script's next build is a
fresh worker's, a restart. Each such document is also kept in the engine's cache once it is idle, at
its drain and at shutdown (``cache``), so a restart of the daemon opens it at once.

The workers keep a standby with the kernel loaded (``services.WORKER``, ``Supervisor.stand``): started
with the daemon, and again each time a build takes it or starts a worker of its own while there is
room for it. A build for a script with no live worker takes the standby when its environment shapes
the interpreter as the standby's does (``places.RESTARTS``), and starts a fresh worker otherwise;
taken, the standby is that script's worker from then on (``Process.adopt``), so a new script's first
build pays no kernel load. The standby counts toward the cap, is the first retired for room or
memory, and is never a script's worker in ``status``. ``CAD_ENGINE_STANDBY=0`` keeps none
(``standby``): an operator's seam for CI and machines short of memory.

Every service speaks one protocol (``cad.engine.frames``). Requests are one JSON object per line on
the process's stdin, a request's ``bytes`` exactly that many bytes after its line. The process
answers on its original stdout in frames: a JSON object on one line and, when it says ``bytes``, that
many bytes after it. Its first frame is ``{"ready": pid, "rssMb"}``; then, for each request, its
``log``, ``notice`` and ``progress`` frames, which go to whoever asked, and one answer, which may
carry ``rssMb`` and ``retire``. What it prints goes to its stderr, its log. It exits when its stdin
closes.

It also serves documents over HTTP (``serve``), holding each loaded document and its
parts' tessellations in its memory under one budget (``serve.memory_budget``,
``CAD_ENGINE_MEMORY_MB``; past it, or on the system's memory-pressure signal, what is held
is evicted: ``serve.Server.trim``), and draws them (``draw``): each served document a
snapshot asks for is drawn by a render process of its own (``renders``), started on its first
picture, sent each new version of it at the picture that asks for it, gone with the daemon or under
the memory cap.

Its only files are the operating system's coordination, in its own folder, ``state_dir``: a lock,
and on POSIX its door, a named pipe (``door_path``), and the pipes of the connections being opened
(``door``: no socket, so a sandbox that refuses sockets still reaches it); on Windows a localhost
TCP port and a token, in a port file there. It removes them as it stops (``let_go``); those of one
killed are the next one's, which takes its lock and makes its door anew, and ``cad status`` and ``cad
stop`` remove them (``client.sweep``). Requests are one JSON object per line on a connection; answers
are JSON lines, the last of which carries ``done``, ``failed`` or ``ok``. Before it, a build
sends its caller its ``{"log"}`` lines and its ``{"progress"}`` frames as its worker sends them
(``progress.py``); the daemon keeps each busy worker's last frame for ``status``, and wakes the
pages waiting on a served document the frame's build writes (``serve.Server.building``).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from cad.engine.atomic_replace import replace_atomic
from cad.engine.client import WORKER_STDERR
from cad.engine.contract import refusal as contract_refusal
from cad.engine.previous import version
from cad.engine import places as _places
from cad.engine.door import DOOR_PROTOCOL
from cad.engine.ids import canonical, file_id, is_id
from cad.engine.places import (NAME, WINDOWS, bytecode, door_path, engine_dir, engine_root, failure_path, installation, lock, lock_path, names, port_path, pycache)
from cad_server.engine.services import SERVICES
from cad_server.engine.supervisor import Gone, Process, Supervisor

__all__ = ["DEFAULT_PORT", "PortHeld", "let_go", "main", "port_holder", "worker_cap"]


def _application(server: Any, host: str, port: int) -> Any:
    """The server's HTTP application on the engine's listener: the CAD Viewer's and the CAD app's
    (``cad_server._internal.engine_host.http_factory``, the one module that imports either)."""
    from cad_server._internal.engine_host import http_factory

    return http_factory(server, host, port)


def _kernel(make: bool) -> dict[str, Any] | None:
    """The environment the engine's kernel processes run in: the installation's base
    (``cad_server._internal.engine_host.kernel``)."""
    from cad_server._internal.engine_host import kernel as made

    return made(make)


def _making() -> Any:
    """The engine's making of the base when it is absent (``cad_server._internal.engine_host.making``)."""
    from cad_server._internal.engine_host import making

    return making()


def _halt() -> None:
    """The uv commands the engine runs now stopped (``cad_server._internal.engine_host.halt``)."""
    from cad_server._internal.engine_host import halt

    halt()


# The engine's one listener and the application it serves (``serve.Server`` binds none of its own).
HTTP_FACTORY: Callable[[Any, str, int], Any] = _application
# Every process of the engine's that loads the kernel -- a model's worker, the standby, the documents
# worker, the meshing and reading pools, the render processes -- runs in the installation's base, which
# the library's modules that start them are told here (``places.kernel``): the library knows no installation.
_places.KERNEL = _kernel

# How often the daemon tends itself (``Daemon.tend``): its door, its pipes, and its processes'
# memory against its cap. The server's pressure poller asks the system's signal more often.
TEND_SECONDS = 30.0
# The engine's HTTP port when nothing names one (0xCAD): ``--port`` on ``cad server`` (or a
# request's own), then ``CAD_ENGINE_PORT``, then the installation's remembered port, then this
# (``bind``). Held by another program, the engine rolls to the next free port and remembers it.
DEFAULT_PORT = 3245
# A test suite's own "default" (``default_port``), so no test binds or rolls from the machine's 3245.
DEFAULT_PORT_ENV = "CAD_ENGINE_DEFAULT_PORT"
# How many ports past a held default (or remembered) one the engine tries before any free one.
PORTS_TRIED = 64
# How long a build's worker is free, with no request waiting for it, before the documents the build
# made that an inspection has measured are read and measured again for the inspection after it
# (``serve.Server.measure_later``): a program calling its models one after another sends its next
# build within milliseconds of an answer, so those calls never wait on that read. The worker's own
# collection waits as long (``worker.COLLECT_IDLE``).
MEASURE_IDLE = 0.5
# How many days a folder of an installation's bytecode (``places.pycache``) no daemon started in stays.
PYCACHE_UNUSED_DAYS = 30


def prune_bytecode() -> None:
    """The bytecode folders of installations no daemon started in ``PYCACHE_UNUSED_DAYS``, removed in
    the background, when the daemon caches its own (``bytecode``): never a caller's folder, which is
    not the engine's to judge."""
    ours = pycache()
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
    """Whether the daemon keeps a standby (``Daemon.stand``): ``CAD_ENGINE_STANDBY=0`` is the
    operator's seam to keep none (CI, a machine short of memory); unset or anything else, it does."""
    return os.environ.get("CAD_ENGINE_STANDBY", "").strip() != "0"


def worker_cap() -> int:
    """The live workers' cap: ``CAD_ENGINE_WORKERS``, else the machine's cores."""
    try:
        given = int(os.environ.get("CAD_ENGINE_WORKERS", "").strip() or 0)
    except ValueError:
        given = 0
    return given if given > 0 else (os.cpu_count() or 1)


def _note_failure(reason: str, error: OSError) -> None:
    _note(f"{reason}: {error.strerror or error}", denied=isinstance(error, PermissionError))


def _note(said: str, denied: bool = False) -> None:
    """Why this daemon exits failing: on its stderr and in its note beside its lock."""
    print(f"cad: {said}", file=sys.stderr)  # ``cad server``'s terminal; nowhere when started for a client
    try:
        failure_path().write_text(json.dumps({"reason": said, "denied": denied}), encoding="utf-8")
    except OSError:
        pass  # a folder it cannot write either: the client says the daemon exited, and its code


# The requests that serve (``Daemon.serve``: the HTTP server bound on the first), each counted busy
# while it is underway (``Daemon.handle``).
SERVING = frozenset({"serve", "viewer", "http", "read", "warm"})
# The type a worker answers bytes of a held document that do not read with (``build.Unreadable``),
# as ``worker.refusal`` names it.
UNREADABLE = "cad.engine.build:Unreadable"


def refused(error: Exception) -> dict[str, Any]:
    """A refusal as the daemon answers it: its words, its type (``worker.refusal``), and for a
    document the engine does not hold (``serve.NotHeld``) its state and the command that builds it
    again, so the caller raises it as that type (``api._failed``) and the CLI exits 2."""
    from cad.engine.serve import NotHeld
    from cad.engine.worker import refusal

    found: dict[str, Any] = {"failed": str(error), **refusal(error)}
    if isinstance(error, NotHeld):
        found.update(state=error.state, rebuild=error.rebuild)
    return found


# --- the daemon ---------------------------------------------------------------------------


def environment_port() -> int | None:
    """``CAD_ENGINE_PORT`` as a port (0: any free one), or None when it names none."""
    given = os.environ.get("CAD_ENGINE_PORT", "").strip()
    if not given:
        return None
    try:
        port = int(given)
    except ValueError:
        raise ValueError(f"CAD_ENGINE_PORT={given!r} is not a port") from None
    if not 0 <= port <= 65535:
        raise ValueError(f"CAD_ENGINE_PORT={given!r} is not a port")
    return port


def default_port() -> int:
    """``DEFAULT_PORT``, or the port ``CAD_ENGINE_DEFAULT_PORT`` names (1-65535): a test's seam,
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
    from cad.engine.serve import reachable_host

    try:
        socket.create_connection((reachable_host(host).strip("[]"), port), timeout=0.5).close()
    except OSError:
        return False
    return True


class PortHeld(ValueError):
    """The engine's port is another process's (``bind``): ``who`` holds it, in words. A port named
    (``--port``, ``CAD_ENGINE_PORT``) is refused in one line that names the holder; the default
    or remembered one is rolled from."""

    def __init__(self, said: str, who: str) -> None:
        super().__init__(said)
        self.who = who


def bind(host: str, asked: int | None, listen: Callable[[int, str], Any]) -> tuple[Any, dict[str, Any]]:
    """The engine's HTTP server, listening, and where its port came from. ``listen(port, token)``
    makes it. A port named -- ``asked`` (``--port``, or the switch's: the port the engine before it
    served), else ``CAD_ENGINE_PORT`` -- is taken or refused by name (``PortHeld``). Else the
    device's port: 3245 (``DEFAULT_PORT``) when it is free, else the port it remembers, else the one it
    rolls to (``_installation_port``). Another process on it -- another engine, 0.8's among them,
    whatever it is -- is asked nothing: a port named is refused, naming it, and the device's port is
    rolled from (``_listen``). The page token is the user's (``registry.TOKEN``), one for every engine,
    made by the first to start (``_new_token``); one there that cannot be read is refused by name, and
    nothing is served.

    ``where``: ``source`` (``--port``, ``CAD_ENGINE_PORT``, ``default`` or ``rolled``), for a
    rolled port ``because`` (who holds 3245), and ``notice``, the line this start says once: a move of
    its port (a roll, or the return to 3245)."""
    from cad_server.engine import registry

    held = registry.current()
    record = held.engine(NAME) if held is not None else {}
    token = (held.token() if held is not None else None) or _new_token(held)
    remembered = record.get("port")
    if asked is not None:
        server, where = _listen(host, asked, "--port", token, listen), {"source": "--port"}
    elif (named := environment_port()) is not None:
        server, where = _listen(host, named, "CAD_ENGINE_PORT", token, listen), {"source": "CAD_ENGINE_PORT"}
    else:
        server, where = _installation_port(host, remembered, token, listen)
        remembered = server.port if where["source"] == "rolled" else None
    kept = {"port": remembered} if remembered else {}
    if held is not None and kept != record:
        try:
            held.put_engine(NAME, kept)
        except OSError:
            pass  # a state folder it cannot write: this start's links work, the next start's are new
    return server, where


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
    """The server on the device's own port, and where it came from (``bind``): 3245 when it is free (a
    remembered other port forgotten: the one time a link changes), else the remembered port, else --
    that one held too -- the next free port, ``PORTS_TRIED`` above it and then any (``_roll``),
    remembered from then on."""
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
                        "notice": f"{first} is held by {refusal.who}; the engine serves on {server.port} "
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
    """``listen(port, token)``, or ``PortHeld`` naming the process that holds ``port`` (``_holder``): no
    other process is asked anything, another engine -- 0.8's among them -- no more than any program."""
    import errno

    try:
        if port and _answers(host, port):  # a listener on every interface lets a loopback bind through
            raise OSError(errno.EADDRINUSE, os.strerror(errno.EADDRINUSE))
        return listen(port, token)
    except OSError as error:
        if not port or not _held(error):
            raise ValueError(f"cannot listen on {host}:{port}: {error.strerror or error}") from None
    raise _holder(port, source)


def _holder(port: int, source: str) -> PortHeld:
    """``port`` refused, naming who holds it as the system names it (``_who``) and what to do about it.
    ``source``: where the port came from (``bind``), which says how to name another."""
    other = "pass another --port" if source == "--port" else "start the server with another CAD_ENGINE_PORT"
    who = _who(port)
    return PortHeld(f"port {port} is held by {who}: stop it, or {other}", who)


def _who(port: int) -> str:
    """Who holds ``port``, in words, as the system names it (``port_holder``): another text-to-cad by its
    command line (``_CADGEN``), else its name and pid, else another process."""
    pid, name, command = port_holder(port)
    if pid is None:
        return "another process"
    return f"another text-to-cad ({name}, pid {pid})" if _CADGEN.search(command or "") else f"{name or 'a process'} (pid {pid})"


# A command line that runs a server's engine or viewer, this release's or an earlier one's: ``-m cad_server.…``
# or ``-m cadgen.…``, or the command's -- ``cad``, an earlier release's ``cadgen`` -- ``viewer``, ``server`` or
# ``mcp``.
_CADGEN = re.compile(r"(-m\s+(cad_server|cadgen)(\.\w+)*|[/\\](cad|cadgen)(\.exe)?\s+(viewer|server|mcp))(\s|$)")


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
    """Replace the user's page token (``cad server --rotate-token``): every link shared before
    stops working, whichever installation's engine served it. The new token; None where there is no
    state folder to keep it in."""
    import secrets

    from cad_server.engine import registry

    held = registry.current()
    if held is None:
        return None
    token = secrets.token_urlsafe(32)
    held.put_token(token)
    return token


class Daemon:
    def __init__(self, cap: int | None = None, port: int | None = None) -> None:
        self.port = port  # ``cad server --port``: the HTTP port this engine must take, or None
        self.port_source = ""  # where the HTTP port the server took came from (``bind``)
        self.port_because = ""  # a rolled port: who holds the default one
        self.port_notice = ""  # a start that moved the port: the line it says, once (``bind``)
        # That line when no request of a client bound the port -- a build's page did
        # (``models.register_page``): the next build's answer says it (``_serve``).
        self.unsaid = ""
        self.refusal: PortHeld | None = None  # its named port held by another process: it stops (``serve``)
        from cad.engine.serve import Pressure
        from cad.engine.worker import rss_cap_mb

        # The system's memory-pressure signal, the server's too once it runs (``serve``): under it the
        # supervisor sheds the standby and its least recently used processes (``Supervisor.shed``); as
        # ``CAD_ENGINE_PRESSURE`` says, where it is set (``Pressure.from_environment``).
        self.pressure = Pressure.from_environment()
        # Every process the daemon starts, by its service's declaration (``services``), its hooks bound
        # here by name: the drain (a worker's documents taken from it before it stops), what a page
        # watches, the progress that wakes pages, and the cache's ``saved``.
        self.supervisor = Supervisor(cap or worker_cap(), SERVICES, watched=self.connected,
                                     drain=lambda process: self.models.drain(process), memory=rss_cap_mb,
                                     pressed=self.pressure.under, on_progress=self.progressed,
                                     on_event={"saved": lambda process, header, payload:
                                               self.models.cache.saved(process, header, payload)})
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
        # runs), which ``status`` counts.
        self.holders = 0
        # Draining for an update (``drain``): it stops once nothing is in flight.
        self.draining = False
        self.listener: socket.socket | None = None  # on Windows, the port clients reach it by
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
        self.builders: dict[str, Process] = {}
        self.renders = None  # the served documents' pictures, by their render processes (``renders.Renders``)
        self.serving = threading.Lock()
        from cad_server.engine.models import Models

        self.models = Models(self)

    def touch(self) -> None:
        self.last = time.monotonic()

    def stand(self) -> None:
        """At the daemon's start: the engine's kernel environment, the base, made in the background when
        it is absent (``base.Making``): an engine a host's CAD app starts runs outside any sandbox, and an
        agent's sandboxed first command cannot write the cache folder -- nothing waits on the making
        (nor on the network it may ask) but what needs the kernel. Then each service's standby
        (``Supervisor.stand``) -- the workers', a worker with the kernel loaded, so a new script's first
        build pays no kernel load -- nor, on a fresh installation, the operating system's first look at
        its native libraries (macOS checks each once: 43 s measured on a new uvx environment, against 2.5 s
        loaded again), which the standby pays while nobody waits. Started in the environment of the client
        that started the daemon (``environment``), in the base, once that is made (``made_base``); each
        standby after it in that of the lease that took the last one. And the bytecode folders of
        installations no daemon started in ``PYCACHE_UNUSED_DAYS`` go, in the background
        (``prune_bytecode``). With ``CAD_ENGINE_STANDBY=0`` (``standby``) no service's standby is
        enabled: none stands by, and none replaces one."""
        prune_bytecode()
        making = _making()
        making.made = self.made_base
        making.start()
        if not standby():
            return
        for service in SERVICES:
            if service.standby is not None:
                self.supervisor.enable_standby(service.name)
                self.supervisor.stand(service.name, self.environment())

    def made_base(self) -> None:
        """The base made here (``base.Making``): each service's standby, when standbys are enabled,
        stands in it now."""
        if self.stopping.is_set():
            return
        for service in SERVICES:
            if service.standby is not None:
                self.supervisor.stand(service.name, self.environment())

    def base(self, request: dict[str, Any], send: Callable[[dict[str, Any]], None]) -> None:
        """The base, asked of the engine by a client that cannot make it (``{"op": "base", "key"}``: a
        sandboxed ``cad run``, ``base.ensure``'s ``engine``): made here when it is not -- the making
        under way followed, or one started (``base.Making.follow``) -- each of its lines a ``log`` frame,
        then ``{"ok": true, "base": true}``, or ``{"failed", "base": true}`` in one line. A base of another
        installation's (``key``) is not this engine's to make: ``{"ok": false, "other": true}``."""
        making = _making()
        if request.get("key") != making.key():
            send({"ok": False, "other": True})
            return
        error = making.follow(lambda line: send({"log": line}))
        send({"ok": True, "base": True} if error is None else {"failed": error, "base": True})

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

    def hold(self, reader: Any, send: Callable[[dict[str, Any]], None], host: Any = None, holder: Any = None) -> None:
        """A hold on the engine (``{"op": "hold", "host": ..., "holder": ...}``): answered, then kept until
        its client goes (its end of file), and counted in ``status`` (``holders``).
        ``host``, the agent host the holder serves (its MCP server says it), is counted in ``status``
        (``hosts``): the ``cad`` command in that host's shell runs this installation. ``holder``, the
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

    def connected(self, worker: Process) -> bool:
        """A page watching any model document this worker built keeps its memo warm. A file a page
        watches keeps no worker, whichever model's run wrote it: a file names no model."""
        server = self.server
        return server is not None and any(self.builders.get(ident) is worker for ident in server.watched())

    def progressed(self, _worker: Process, frame: dict[str, Any]) -> None:
        """A worker's progress frame (``progress.py``): a build's wakes the pages waiting on the model
        document it builds (``serve.Server.building``). An export's or a snapshot's is the request's,
        never its document's build, and reaches its caller alone; a file a build writes is no document
        of the build's: a page serving it follows its bytes, and hears nothing of the run."""
        server = self.server
        if server is not None and frame.get("kind") == "build":
            documents = self.models.paths(_worker, frame.get("job"))
            if documents:
                server.building(frame, documents)

    def _built(self, worker: Process, answer: dict[str, Any], *, verb: bool = False) -> None:
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
                                 settled=lambda: (self.supervisor.free_for(worker) or 0.0) >= MEASURE_IDLE)

    @staticmethod
    def _where(error: Exception, worker: Process | None) -> str:
        """A worker's failure, and where its build was when it failed: said on its first line, before
        any stderr tail (``Process._gone``)."""
        from cad.engine.progress import describe

        frame = worker.progress if worker is not None else None
        if not frame:
            return str(error)
        head, tail, detail = str(error).partition(WORKER_STDERR)
        return f"{head}, at {frame.get('job')}: {describe(frame)}{tail}{detail}"

    @staticmethod
    def contracted(request: dict[str, Any]) -> None:
        """An order that names the Python it comes from (``contract.interpreter``: a build, a handle's
        shape, a shape handed over), its worker contract checked against this server's
        (``contract.refusal``): ``ValueError`` in that one line, naming which side to update and to what
        release, when they differ. An order that names none (a script in the base, ``cad run``'s) is of
        the server's own environment."""
        if "interpreter" not in request:
            return
        said = contract_refusal(request["interpreter"])
        if said is not None:
            raise ValueError(said)

    def caller(self, request: dict[str, Any]) -> str | None:
        """The Python a build's script is built in: its contract checked first (``contracted``); then None
        -- the server's own environment, the base its kernel processes run in -- for an order that names
        no Python, or one whose environment is that base (a checkout's or an installation's own, which
        carries the kernel); else the executable the order names, its caller's, whose worker is its own
        (``Supervisor.lease``'s ``python``)."""
        self.contracted(request)
        named = request.get("interpreter")
        if named is None:
            return None
        executable, prefix = named.get("executable"), named.get("prefix")
        if not (isinstance(executable, str) and os.path.isabs(executable) and isinstance(prefix, str) and prefix):
            raise ValueError("a build names the Python it comes from by an absolute executable and its environment")
        try:
            base = _places.kernel(make=False)
        except Exception:  # noqa: BLE001 - no base to tell it from: the caller's own Python, whatever it is
            base = None
        if base is not None and base.get("prefix") and _same_place(str(base["prefix"]), prefix):
            return None
        return executable

    def lease(self, script: str, environment: dict[str, str], cwd: str | None = None,
              loading: Callable[[str], None] | None = None, python: str | None = None) -> Process:
        """The warm worker of a script (by its path, and the caller's ``python`` where its build named one:
        ``caller``) or of the documents no worker built (``documents``), for one request: waiting its turn,
        started when none is alive (``Supervisor.lease``); ``loading`` as there. ``release`` it after."""
        return self.supervisor.lease("worker", script, environment, cwd, loading, python=python)

    def release(self, worker: Process) -> None:
        self.supervisor.release(worker)

    def behind(self, key: str, send: Callable[[dict[str, Any]], None],
               python: str | None = None) -> tuple[Process, float] | None:
        """A build request that will wait for the build of its script already running (a rerun
        after a client its shell's time limit killed: that build goes on): said to its client at
        once, on stderr, and the running build's progress frames sent on to it until its own turn
        (``Supervisor.follow``). The worker and how long its build had run; None when none runs.
        Nothing is cancelled."""
        found = self.supervisor.follow("worker", key, send, "build", python)
        if found is None:
            return None
        worker, began = found
        ago = max(0.0, time.time() - began)
        send({"log": f"waiting for the build of {Path(worker.label).name} started {ago:.0f} s ago",
              "stream": "waiting"})
        if worker.progress:
            send({"progress": worker.progress})  # where it is now: the next frame may be a while
        return worker, ago

    def provenance(self, ident: str, key: str, kind: str, ordinal: int) -> dict[str, Any] | None:
        """What made one element of a served document (by its id), asked of the worker that built
        it (a ``where`` question, ``build.made_by``): None for a document no live worker built -- one
        served cold."""
        worker = self.builders.get(ident)
        if worker is None or not self.supervisor.holds(worker):
            return None
        answer = worker.question({"op": "where", "doc": ident, "key": key, "kind": kind, "ordinal": ordinal})
        return None if answer is None else answer.get("where")

    def serve(self, request: dict[str, Any]) -> Any:
        """The daemon's server, started on the first request that needs one."""
        from cad.engine.serve import MESHES, Server, memory_budget

        started = False
        with self.serving:
            if self.refusal is not None:
                raise self.refusal  # stopping: its port is another's
            if self.server is None:
                host = request.get("host") or "127.0.0.1"
                try:
                    self.server, where = bind(
                        host, int(request["port"]) if request.get("port") else self.port,
                        lambda port, token: Server(port=port, touch=self.touch,
                                                   provenance=self.provenance, cache=MESHES, isolated=True, host=host,
                                                   http_factory=HTTP_FACTORY, budget=memory_budget(), token=token))
                except PortHeld as refusal:
                    if request.get("port"):
                        # The request's own port (``cad viewer --port``): that request is refused,
                        # and the engine -- the builds and warm workers of its other clients -- runs
                        # on, unbound, for the next request that serves.
                        raise
                    # An engine whose own port is held (``cad server --port``, its
                    # ``CAD_ENGINE_PORT``) can never serve: it says why and stops, once the
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
                # One pressure signal: under it the server trims its documents and the supervisor its
                # processes.
                self.server.pressure = self.pressure
                self.server.pressed = lambda: self.supervisor.shed(True)
                self.server.lost = self.models.rebuild
                self.server.revive = self.models.adopt
                self.server.leaving = self.models.leaving
                self.server.delete = self.models.delete
                self.server.retire = self.drain
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
            if worker is not None and self.supervisor.holds(worker):
                # Asked of the worker that built it (``via``: a child model's is its parent's script's).
                return {"script": record["source"]["script"], "function": record["source"]["name"], "held": ident,
                        "via": worker.label, **({"python": worker.python} if worker.python else {})}, b""
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

    def _routed(self, request: dict[str, Any]) -> tuple[str, str | None, str | None]:
        """The worker a request goes to (its key), the folder that worker starts in, and the Python it
        runs: the caller's one a held document's worker was started in (``via``'s ``python``), else None,
        the server's own (a build's own is ``caller``'s)."""
        source = request.get("source") or {}
        if "document" in source:
            return "documents", request.get("cwd"), None  # a held document's bytes: no worker of its script
        if "path" in source:
            return "documents", request.get("cwd"), None  # a file, read as a file: no model's worker
        # A script's worker is keyed by its canonical path: a process key, not a document's id. A held
        # document is asked of the worker that built it (``via``, in the Python it runs), whatever script
        # defines its model.
        holder = source if source.get("via") else request
        python = holder.get("python") if holder.get("via") else None
        return (canonical(holder.get("via") or request.get("script") or source["script"]), None,
                python if isinstance(python, str) else None)

    def _call(self, request: dict[str, Any], order: dict[str, Any], send: Callable[[dict[str, Any]], None],
              payload: bytes = b"") -> None:
        """An export or a result asked of the worker the request routes to (with ``payload``, the
        bytes its source carries, after its line); its answer sent."""
        with self.busy_lock:
            self.busy += 1
        try:
            key, cwd, python = self._routed(request)
            if python is not None and self.supervisor.live("worker", key, python) is None:
                # Its worker is gone: only a build starts one in its caller's Python, its contract checked.
                python = None
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
                        held = self.supervisor.live("worker", key, python)
                        environment = held.environment if held else self.environment()
                        ordered = order
                        if held is None and "script" in request["source"]:
                            named = request["source"].get("held")
                            send(refused(self.models.not_held(named)) if isinstance(named, str) else
                                 {"failed": "The viewed model is no longer held. Reopen it before exporting."})
                            return
                    worker = self.lease(key, environment, cwd, python=python)
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
                    answer = worker.request(ordered, send, payload)
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
                except Gone as error:
                    # One that exited mid-request is not asked again, nor one that never said it was ready.
                    if attempt == 2 or error.during or error.unready:
                        failed = {"failed": self._where(error, worker)}
                        if worker is not None and not request.get("expected"):
                            self._built(worker, failed, verb=True)
                        send(failed)
                        return
                except RuntimeError as error:
                    if not _no_kernel(error):
                        raise
                    send({"failed": str(error)})  # no kernel environment to start the worker in: its line
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
        draws do: a drain for an update waits for it (``drain``)."""
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
            # ``cad delete`` (``cli.delete``): each id deleted by the one deletion (``models.delete``).
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
                        from cad.engine.export import ExportRefused

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
                self.contracted(request)  # its shapes are read in its caller's Python
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
            # A shape handed over (``api.hand_over``): held as a drained document is, nothing to run; its
            # document was written in its caller's Python, and is read in the server's.
            try:
                self.contracted(request)
                send(self.models.hand_over(request))
            except ValueError as error:
                send(refused(error))
            return
        if op == "build":
            try:
                # The Python the script is built in (its caller's, else the server's own), its worker
                # contract checked before any worker starts.
                python = self.caller(request)
            except ValueError as error:
                send({"failed": str(error)})
                return
            with self.busy_lock:
                self.busy += 1
            try:
                script = request["script"]
                key, cwd, _python = self._routed(request)  # a build's Python is ``caller``'s
                for attempt in (1, 2):
                    worker = None
                    ahead = self.behind(key, send, python) if attempt == 1 else None
                    waited = time.monotonic()
                    try:
                        try:
                            worker = self.lease(key, request.get("env") or {}, cwd,
                                                lambda text: send({"log": text, "stream": "notice"}), python)
                        finally:
                            if ahead is not None and send in ahead[0].followers:
                                ahead[0].followers.remove(send)
                        fresh = worker.requests == 0
                        order = {"id": 1, "op": "build", "script": script, "functions": request.get("functions"),
                                 "cwd": request.get("cwd"), "verify": bool(request.get("verify")),
                                 "profile": bool(request.get("profile")), "run": request.get("run")}
                        if request.get("env"):
                            order["env"] = request["env"]  # the run's own (``worker.adopt``)
                        cached = self.models.cache.folder()
                        if cached is not None:
                            order["cache"] = cached  # what a fresh worker takes a model from, by its key
                        answer = worker.request(order, send)
                        answer["worker"] = {"pid": worker.pid, "fresh": fresh}
                        # This server's release, which a script run in its own Python says once a run
                        # when it is another (``contract.notice``).
                        answer["release"] = version()
                        if ahead is not None:
                            # The build it waited for, the one its own replays: began how long before it asked.
                            for report in answer.get("done") or []:
                                if isinstance(report, dict):
                                    report["waited"] = {"script": Path(ahead[0].label).name, "ago": round(ahead[1]),
                                                        "seconds": round(time.monotonic() - waited, 1)}
                        # The program that asked: what a document it built names to build it again.
                        answer["program"] = request.get("program")
                        self._built(worker, answer)
                        send(answer)
                        return
                    except Gone as error:
                        # A build is never run twice, nor waited for twice on a worker that never said
                        # it was ready: refused in that one line.
                        if attempt == 2 or error.during or error.unready:
                            failed = {"failed": self._where(error, worker)}
                            if worker is not None:
                                self._built(worker, failed)
                            send(failed)
                            return
                    except RuntimeError as error:
                        if not _no_kernel(error):
                            raise
                        send({"failed": str(error)})  # no kernel environment to start the worker in: its line
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
                from cad.engine.serve import NotHeld

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
            # A document's JSON read in the engine's own vocabulary (``/api/doc/<id>...``,
            # ``cad/engine/serve.py``'s, which its HTTP API, ``/api/v1``, answers its pages from),
            # answered in process: ``inspect``'s, through the door, so it needs no loopback socket of
            # the client's.
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
        elif op == "base":
            self.base(request, send)
        elif op == "pid":
            send({"ok": True, "pid": os.getpid()})  # who answers: a client that started a daemon asks
        elif op == "stop":
            # ``drain``: an update's switch, which waits for what is in flight (``drain``); else at once.
            send({"ok": True, "draining": True} if request.get("drain") else {"ok": True})
            if request.get("drain"):
                self.drain()
            else:
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
        from cad.engine.progress import Progress
        from cad_server.engine.renders import Refused, Renders, answer_png

        with self.busy_lock:
            self.busy += 1
        said = Progress(lambda frame: send({"progress": frame}), kind="snapshot", job=Path(request["path"]).name,
                        outputs=[request["out"]] if request.get("out") else [])
        try:
            server = self.serve(request)
            with self.serving:
                if self.renders is None:
                    self.renders = Renders(server, self.supervisor)
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

    def status(self) -> dict[str, Any]:
        """The daemon, its workers (each its script, its builds, its memory after its last build
        in MiB, how long it has been busy or idle, and a busy one's last progress frame), its
        standby (never a script's worker: its process, its memory, how long it has stood by), its
        processes' memory against its cap, the builds waiting for a worker, the last retirements, and
        what it serves and draws."""
        from cad.engine.worker import rss_cap_mb

        now = time.monotonic()
        server = self.server
        supervisor = self.supervisor
        workers = [{"script": w.label, **({"python": w.python} if getattr(w, "python", None) else {}),
                    "pid": w.pid, "builds": w.requests, "alive": w.alive() and not w.retired,
                    "busy": w.leased, "rssMb": None if w.rss is None else round(w.rss),
                    "seconds": round(now - (w.since if w.leased else w.used), 1),
                    "progress": w.progress if w.leased else None} for w in supervisor.processes("worker")]
        with supervisor.lock:
            spare, readying = supervisor.standby("worker"), supervisor.readying("worker") is not None
        standby = ({"pid": spare.pid, "rssMb": None if spare.rss is None else round(spare.rss),
                    "seconds": round(time.time() - spare.started, 1)} if spare is not None
                   else {"pid": None, "rssMb": None, "seconds": None, "starting": True} if readying else None)
        # What uses it, which `cad status` says: its holds, the documents pages watch, its builds and draws,
        # and HTTP work underway.
        return {"ok": True, "pid": os.getpid(), "version": version(), "installation": installation(),
                "up": round(time.time() - self.born, 1),
                "workers": workers, "standby": standby, "cap": supervisor.cap, "waiting": supervisor.waiting("worker"),
                "rssMb": round(supervisor.resident()), "rssCapMb": rss_cap_mb(), "retired": list(supervisor.retired),
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
                "base": _making().status(),
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
        long anything has been idle. A killed client's pipes are swept, and the processes' memory is
        held to its cap and the system's pressure (``Supervisor.shed``: a worker's documents drained
        first, so they stay held); the memory budget sends unwatched documents out of memory, least recently used
        first, to the cache, as they are loaded (``serve.Server.trim``). The engine stops on ``stop``, a terminate, another installation's
        retiring it (``bind``), and here when its door is gone (its folder removed, a temporary
        folder cleaned up) or another's: no one can reach it, so it stops as ``stop`` does, saving
        what it holds to the cache."""
        if self.address is not None and _identity(self.address) != self.address_id:
            self.stopping.set()
            return
        if self.door is not None:
            self.door.sweep()
        self.supervisor.shed(self.pressure.under())
        self.models.prune()

    def working(self) -> bool:
        """Whether anything an update's drain waits for is in flight: a build, a draw, an export, a
        request that serves (``busy``), and the HTTP application's exports and agents' MCP calls
        (``serve.Server.clients_working``). Open pages and held sessions are not: a page reconnects,
        and a session is opened again on its next request."""
        with self.busy_lock:
            if self.busy:
                return True
        server = self.server
        return server is not None and bool(server.clients_working())

    def drain(self, then: Callable[[], None] | None = None) -> None:
        """Stop once nothing is in flight (``working``), for an update: in the background, so the
        request that asked for it is answered first. Its door (on Windows its port) closes once it is
        idle, so no new connection reaches it, and what came in before that is waited for too; then
        ``then`` (the update's switch helper, started) and the stop. A second drain joins the first."""
        with self.busy_lock:
            if self.draining:
                return
            self.draining = True

        def wait() -> None:
            while self.working() and not self.stopping.is_set():
                time.sleep(0.05)
            if self.door is not None:
                self.door.close()
            if self.listener is not None:
                try:
                    self.listener.close()
                except OSError:
                    pass
            while self.working() and not self.stopping.is_set():
                time.sleep(0.05)
            if then is not None:
                try:
                    then()
                except Exception as error:  # noqa: BLE001 - the stop goes on: the next client starts current's engine
                    print(f"cad: the update's switch could not start: {type(error).__name__}: {error}",
                          file=sys.stderr, flush=True)
            self.stopping.set()

        threading.Thread(target=wait, name="cad-drain", daemon=True).start()

    def shutdown(self) -> None:
        # The documents built or read in the last idle window, saved first, best effort (``cache``).
        self.models.cache.final()
        _halt()  # a making of the base under way: its uv goes with the engine
        self.supervisor.stop()  # its workers, the standby and the render processes
        if self.server is not None:
            self.server.stop()


def _same_place(one: str, other: str) -> bool:
    """Whether two paths name one folder, as the system resolves them."""
    return os.path.normcase(os.path.realpath(one)) == os.path.normcase(os.path.realpath(other))


def _no_kernel(error: BaseException) -> bool:
    """Whether ``error`` is the engine having no kernel environment to start a process in
    (``serve.KernelProcessesUnavailable``): a request's answer, in its one line."""
    from cad.engine.serve import KernelProcessesUnavailable

    return isinstance(error, KernelProcessesUnavailable)


# How long a connection to the Windows loopback port has to show its token: anyone on the machine can
# connect there, so nothing more is read, or waited for, until it has.
AUTH_SECONDS = 10.0


def _admitted(daemon: Daemon, connection: socket.socket, stream: Any) -> int | None:
    """On Windows, a connection's token shown, and the door protocol it speaks: the door's hello with
    the token where a pair's id goes (``<token> <protocol>``, ``door.hello``), greeted on the
    connection as the door greets (``door.greeting``). A peer without it -- a line that is no such
    hello, 0.8's client's request among them -- is refused after a line of ``door.HELLO_LIMIT`` bytes
    and ``AUTH_SECONDS`` at most, before a request is read or parsed. The protocol; None: refused."""
    import hmac

    from cad.engine import door

    if not daemon.token:
        return None
    token = daemon.token.encode("ascii")
    connection.settimeout(AUTH_SECONDS)
    line = stream.readline(door.HELLO_LIMIT)
    said = line.removesuffix(b"\n") if line.endswith(b"\n") else b""
    ident, protocol = door.hello_id(said), door.hello_protocol(said)
    if ident is None or protocol is None or not hmac.compare_digest(ident.encode("ascii"), token):
        return None
    stream.write(door.greeting(min(protocol, door.DOOR_PROTOCOL)))
    stream.flush()
    connection.settimeout(None)
    return protocol


def _serve(daemon: Daemon, reader: Any, writer: Any, protocol: int = DOOR_PROTOCOL) -> None:
    """One connection: its request line, and every answer line the request sends. A hold keeps the
    connection until its client goes. ``protocol``: the door protocol the client's hello spoke,
    carried for the request's handling once a later protocol number changes what it may say."""
    line = reader.readline()
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


def _serve_door(daemon: Daemon, ident: str, protocol: int) -> None:
    """A connection through the door (POSIX): the hello's pair answered (``door.answer``) in the
    protocol the hello spoke."""
    from cad.engine import door

    def serve(reader: Any, writer: Any) -> None:
        try:
            _serve(daemon, reader, writer, protocol=protocol)
        except (OSError, ValueError):
            pass  # the client went, or sent no request

    door.answer(engine_dir() / door.CLIENTS, ident, serve, protocol)


def _serve_connection(daemon: Daemon, connection: socket.socket) -> None:
    """A connection to the Windows loopback port: its token shown first, in its hello (``_admitted``),
    then served."""
    with connection:
        stream = connection.makefile("rwb")
        try:
            protocol = _admitted(daemon, connection, stream)
            if protocol is None:
                return
            _serve(daemon, stream, stream, protocol)
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
    if not WINDOWS and names(held, path):
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


def _identity(path: Path) -> tuple[int, int] | None:
    """The file at ``path`` (not a link it names): its device and inode, or None when there is none."""
    try:
        found = os.lstat(path)
    except OSError:
        return None
    return found.st_dev, found.st_ino


def main(argv: list[str] | None = None, *, port: int | None = None, rotate: bool = False,
         foreground: bool = False) -> int:
    """Run the engine here. ``port``: the HTTP port it must take (``cad server --port``);
    ``rotate``: a new page token first (``--rotate-token``), refused while another engine runs;
    ``foreground`` (``cad server``): its HTTP server bound before anything else, so a port
    another process holds fails the command at once (``bind``). An engine a client starts binds
    on the first request that serves, which may name its own port (``cad viewer --port``)."""
    from cad.engine.serve import Pressure

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
        _note_failure(f"the engine server cannot take its lock in {engine_dir()}", error)
        return 1
    if held is None:
        if rotate:
            print("cad: an engine server is running; run cad stop first, then cad server --rotate-token",
                  file=sys.stderr)
            return 1
        if foreground:  # ``cad server``: said, never a silent success that serves nothing it asked
            print("cad: the engine server is already running: `cad status` says where it "
                  "serves, `cad stop` stops it" + (f" (to serve on {port})" if port is not None else ""),
                  file=sys.stderr)
            return 1 if port is not None else 0
        return 0  # another daemon is up
    if rotate:
        try:
            if rotate_token() is None:
                raise OSError("no state folder")
        except OSError as error:
            print(f"cad: cannot replace the page token: {error.strerror or error}", file=sys.stderr)
            let_go(held)
            return 1
        print("cad: a new page token: every link shared before no longer works", file=sys.stderr)
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
    daemon = Daemon(port=port)

    # And the records from before namespace/name identity brought to it, once (``identity.migrate``:
    # JSON and file names, no XBF, independent of the closure's pass). It never keeps the engine
    # from starting.
    from cad.engine.identity import migrate

    try:
        daemon.identity = migrate(daemon.models.registry())
    except Exception as error:  # noqa: BLE001
        daemon.identity = {"filled": 0, "moved": 0, "skipped": [f"the pass failed: {type(error).__name__}: {error}"]}
        print(f"cad: identity migration failed: {type(error).__name__}: {error}", file=sys.stderr, flush=True)
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
            print(f"cad: {said}", file=sys.stderr)  # ``cad server``'s terminal
            daemon.unsaid = ""
    if not WINDOWS:
        import signal

        # A terminate (a logout, ``kill``) stops the daemon as ``cad stop`` does: its workers,
        # pools, door and listener go with it. A client gone mid-answer is a write's BrokenPipeError.
        signal.signal(signal.SIGTERM, lambda _signum, _frame: daemon.stopping.set())
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    threading.Thread(target=daemon.watch, daemon=True).start()
    failed = False  # its door could not be made: its note says why, and stays
    daemon.listener = listener
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
            from cad.engine.door import Door

            try:
                daemon.door = Door(door_path(), lambda ident, protocol: _serve_door(daemon, ident, protocol))
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
