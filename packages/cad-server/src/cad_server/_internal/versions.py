"""The versions of cad installed on this computer: making one present, the use each one records, and the
cleanup that removes the old ones.

Each version lives in ``versions/<version>`` in the state folder (``cad.engine.places``): its ``code/``, its
``data/`` (its own settings and store) and its use record (``USED``). Versions sit side by side and nothing moves
between them: no version is "the" one, nothing points at one, and no version refuses another's commands. The
``cad`` command runs the version a pin names, or the newest installed with none (``installations``).

**Installed** (``present``). A version is installed when its "complete" marker, ``code/cad-version.json``, is there
and names a server environment whose Python and ``cad`` are (``places.version_record``). The newest installed is the
highest version number (``order``, ``newest``).

**Making one present** (``make_present``), under the computer's install lock (``install_lock``), changes nothing
outside ``versions/<version>/code``:

1. ``code/``, this user's and no one else's to write, with a ``CACHEDIR.TAG``; a marker left by a broken code
   folder removed first, so the version is not present while it is made again;
2. ``code/server``, the server environment: ``cad-server==<version>`` from the index, or, for this process's
   own version, from where this process's server came (its wheel, or its source tree for a development
   install: ``base.server_source``), made by uv as every environment is (``base.make``: uv's cache first, the
   network only for what it lacks, a folder of wheels a test names read beside the index,
   ``base.FIND_LINKS_ENV``, its marker ``cad-release.json`` written last);
3. the proof that it runs (``_probe``): its own Python asked, in a process of its own, which version it is and
   where its kernel environment goes, as it works them out itself;
4. the kernel environment, ``cad[build123d]`` at the version, made now in ``code/base/<key>`` (``base``) rather
   than on first need: a present version has nothing left to make, since a command of it in an agent's sandbox
   cannot write its code;
5. the code marker, last.

Each step is skipped when it is done already, so running it twice, or again after an interruption, finishes
what is left; a second caller waits on the install lock and finds it present. Where it cannot run from this
shell -- no uv, no network for what uv's cache lacks, a folder the system will not let it write (an agent's
sandbox) -- it says so as a result (``Present.cannot``), never a traceback: ``cad setup`` says it in one line.

A version's data -- its settings and store -- is copied ONCE, at its first setup (or its first start, for a
development version), from the newest older installed version, or, on a computer coming from 0.11.10 and earlier,
from that layout (``cad_server._internal.imports``). Nothing is carried between versions after that.

**Servers** (``endpoint``, ``ask``). Each version's server is reached through its own door alone,
``<engines>/<version>``: asked whether work is in flight (``connected``) and asked to stop (``stop_server``). The
one whose version ``installations/current`` names also holds the flat door every client of 0.11.10 and earlier
finds (``flat``, ``cad_server.engine.daemon.Bridge``).

**Use** (``used``, ``last_used``). Each version records its own last use by an agent: a ``cad`` command run for it,
a request its server takes from a command, an MCP tool call other than the page's own. The record is a file,
``versions/<version>/used``, whose modification time is the use, written at most once an hour.

**Cleanup** (``clean``). The server of the newest installed version, as it starts and then every 24 hours
(``CLEAN_SECONDS``, ``due``), removes every older installed version no agent has used for 2 days
(``UNUSED_SECONDS``; one never used, 2 days from when it was installed: its marker's time): its server stopped where
nothing is in flight there, then its folder renamed aside and removed. One with work in flight, a process running
from its folder, or a folder the system refuses to move (Windows: a file in use) stays for the next pass. A version
that is not the newest cleans nothing. The same pass removes what the layout of 0.11.10 and earlier left, once that
is safe (``cad_server._internal.legacy``); while that layout is there, the server tries that part again every minute
between passes (``clean_legacy``).
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cad.engine import places
from cad_server._internal import base

__all__ = ["CANNOT", "CLEAN_SECONDS", "LEGACY_SECONDS", "LOCK", "UNUSED_SECONDS", "USED", "Present", "ask",
           "ask_flat", "clean", "clean_legacy", "connected", "development", "due", "endpoint", "flat",
           "flat_endpoint", "folders", "gone", "install_lock", "last_used", "make_present", "newest", "older",
           "order", "present", "quiet", "remove", "serves", "serving", "stop_server", "used"]

# The computer's install lock, in the state folder: every install and every cleanup holds it (``cad setup``'s too).
LOCK = "install.lock"
SERVER = "server"
TRASH = ".trash-"
# In a version's folder: its last use by an agent, as the file's modification time (``used``).
USED = "used"
# How often a use is written again (``used``): the cleanup counts in days.
USE_SECONDS = 60.0 * 60
# How often the newest version's server cleans (``due``), and how long an older version may go unused before it does.
CLEAN_SECONDS = 24 * 60 * 60.0
UNUSED_SECONDS = 2 * 24 * 60 * 60.0
CACHEDIR_TAG = ("Signature: 8a477f597d28d172789f06886806bc55\n"
                "# This file is a cache directory tag created by cad: a version's code, made again whole\n"
                "# by its install.\n")
# The causes (``base.Refused.cause``) that mean making a version cannot run from this shell, not that it failed.
CANNOT = frozenset({"uv", "network", "denied"})
# What a process of a version's own Python says of itself (``_probe``): its version as it works it out, its
# release, and its installation and kernel environment's folder as its base works them out.
PROBE = ("import dataclasses, json\n"
         "import cad_server\n"
         "from cad.engine import places\n"
         "from cad_server._internal import base\n"
         "own = base._own()\n"
         "print(json.dumps({'version': places.versioned(), 'release': cad_server.__version__,\n"
         "                  'installation': dataclasses.asdict(own), 'inputs': base._inputs(own),\n"
         "                  'base': str(base.where(own))}))\n")

_HELD = threading.local()


# --- the install lock --------------------------------------------------------------------------------


@contextlib.contextmanager
def install_lock(waiting: Callable[[], None] | None = None) -> Iterator[None]:
    """The computer's install lock (``LOCK`` in the state folder), waiting for any other holder -- another process,
    or another thread here. Taken again by the thread that holds it, it is already held. ``PermissionError`` when
    the state folder cannot be written."""
    if getattr(_HELD, "depth", 0):
        _HELD.depth += 1
        try:
            yield
        finally:
            _HELD.depth -= 1
        return
    from cad_server._internal.file_lock import exclusive

    state = places.state_dir()
    state.mkdir(parents=True, exist_ok=True)
    with exclusive(state / LOCK, waiting=waiting):
        _HELD.depth = 1
        try:
            yield
        finally:
            _HELD.depth = 0


# --- which are here ----------------------------------------------------------------------------------


# A development build's name, ``<release>-dev.<YYYYmmddHHMMSS>`` (``dev_install``).
DEVELOPMENT = re.compile(r"(?P<release>.+)-dev\.(?P<stamp>[0-9]+)")


def order(name: str) -> tuple[Any, ...] | None:
    """Where version ``name`` sorts among versions, or None for a name that is no release: the one key every
    question of which version is older asks (``older``, ``folders``, ``newest``, ``imports.source``). Releases sort
    as PEP 440 sorts them. A development build, ``<release>-dev.<stamp>``, is NEWER than the release whose numbers it
    carries -- it is a checkout made after that release -- and older than the next release; two builds of one
    release sort by their stamps. (PEP 440 would read ``-dev.N`` as a development release, before its release.)"""
    from cad.engine.contract import _order

    found = DEVELOPMENT.fullmatch(name or "")
    base = _order(found["release"] if found else name)
    if base is None:
        return None
    return (*base, (1, int(found["stamp"])) if found else (0, 0))


def older(one: str, other: str) -> bool:
    """Whether version ``one`` is older than ``other`` (``order``); a name that is no release is older than none
    and newer than none."""
    first, second = order(one), order(other)
    return first is not None and second is not None and first < second


def _order_key(name: str) -> tuple[Any, ...]:
    found = order(name)
    return (found is not None, found or (), name)


def folders(state: Path | None = None) -> list[str]:
    """Every version's folder in ``versions/``, installed or not, oldest first (``order``)."""
    try:
        names = [entry.name for entry in os.scandir(_root(state)) if entry.is_dir(follow_symlinks=False)
                 and places.VERSION.fullmatch(entry.name)]
    except OSError:
        return []
    return sorted(names, key=_order_key)


def _root(state: Path | None = None) -> Path:
    return (state or places.state_dir()) / places.VERSIONS


def _alive(name: str, state: Path | None = None) -> dict[str, Any] | None:
    found = places.version_record(name, _root(state))
    return found if found is not None and places.alive(found) else None


def present(state: Path | None = None) -> list[str]:
    """The versions installed on this computer -- each code marker there, its Python and ``cad`` with it -- oldest
    first (``order``; a name that orders as no release first)."""
    return [name for name in folders(state) if _alive(name, state) is not None]


def newest(state: Path | None = None) -> str | None:
    """The newest version installed (the highest version number), the one the ``cad`` command runs with no pin and
    whose server cleans (``clean``); None with none installed."""
    found = present(state)
    return found[-1] if found else None


# --- making one present --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Present:
    """What ``make_present`` found: the version's code marker when it is present (``record``), whether this call
    made it (``made``), and when it is not, why in one line (``error``) and, where it cannot be made from this
    shell, the cause (``cannot``: ``uv``, ``network`` or ``denied``)."""

    version: str
    record: dict[str, Any] | None
    made: bool = False
    cannot: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.record is not None


def make_present(name: str, *, told: Callable[[str], None] | None = None) -> Present:
    """Version ``name`` made present (see the module), each line of the making said to ``told``; nothing done
    when it is present already."""
    say = told or base._say
    try:
        places.version_dir(name)
    except ValueError as error:
        return Present(name, None, error=str(error))
    found = _alive(name)
    if found is not None:
        return Present(name, found)
    try:
        with install_lock(waiting=lambda: say("waiting for another install of cad to finish")):
            found = _alive(name)
            if found is not None:
                return Present(name, found)  # made meanwhile, by the process this one waited for
            record = _make(name, say)
    except base.Refused as refused:
        return Present(name, None, cannot=refused.cause if refused.cause in CANNOT else None, error=str(refused))
    except PermissionError as error:
        return Present(name, None, cannot="denied", error=base._cannot(f"cad {name}'s folder", error,
                                                                       f"cad {name}"))
    except OSError as error:
        return Present(name, None, error=f"cad {name} could not be installed: {error.strerror or error}")
    return Present(name, record, made=True)


def _make(name: str, say: Callable[[str], None]) -> dict[str, Any]:
    from cad._internal.atomic_replace import write_bytes_atomic
    from cad_server._internal import installations, releases

    code = places.code_dir(name)
    for folder in (places.versions_dir(), places.version_dir(name), code):
        _private(folder)
    (code / places.VERSION_MARKER).unlink(missing_ok=True)  # broken code: not present while it is made again
    tag = code / "CACHEDIR.TAG"
    if not tag.is_file():
        write_bytes_atomic(tag, CACHEDIR_TAG.encode("utf-8"))
    source = _source(name)
    server = code / SERVER

    def finish(steps: list[list[str]], seconds: float) -> dict[str, Any]:
        return {"schema": releases.SCHEMA, "version": name, "python": str(base.interpreter(server)),
                "cad": str(releases.console(server)), "source": source, "commands": steps,
                "seconds": round(seconds, 2), "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    base.make(server, releases.recipe(name, sys.executable, source), say, finish=finish, marker=releases.MARKER,
              done=lambda env: _server(env, name))
    probe = _probe(name)
    kernel = _kernel(name, probe, say)
    record = {"schema": places.VERSION_SCHEMA, "version": name, "python": str(base.interpreter(server)),
              "cad": str(releases.console(server)), "prefix": str(server), "release": probe.get("release"),
              "kernel": kernel, "source": source, "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    # A key a line, its paths as they are (not escaped): the ``cad`` command's sh reads its ``python`` and ``cad``
    # lines (``installations``).
    write_bytes_atomic(code / places.VERSION_MARKER,
                       (json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    installations._forget_read()
    return record


def _private(folder: Path) -> None:
    """``folder`` made where it is not, and written by this user alone (the engine's bytecode is kept in a
    version's code only where no one else can write it, ``places.pycache``)."""
    folder.mkdir(mode=0o700, exist_ok=True)
    if os.name != "nt":
        mode = os.stat(folder).st_mode
        if mode & 0o022:
            os.chmod(folder, mode & 0o755)


def _source(name: str) -> str | None:
    """Where version ``name``'s server installs from: the index (None), but for this process's own version --
    the release its server is, or the development version it is named (``places.INSTALLATION_ENV``) --, which
    installs from where this process's came (``base.server_source``). ``Refused`` for a development version of
    another checkout's: it is made only by its own."""
    import cad_server
    from cad_server._internal import installations

    if name in (cad_server.__version__, os.environ.get(places.INSTALLATION_ENV)):
        return base.server_source()
    if installations.RELEASE.fullmatch(name):
        return None
    raise base.Refused(f"cad {name} is a development version: only its own checkout installs it")


def _server(env: Path, name: str) -> dict[str, Any] | None:
    """The marker of version ``name``'s server environment at ``env`` when it is complete, else None."""
    from cad_server._internal import releases

    try:
        marker = json.loads((env / releases.MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (isinstance(marker, dict) and marker.get("schema") == releases.SCHEMA and marker.get("version") == name
            and base.interpreter(env).exists() and releases.console(env).exists()):
        return marker
    return None


def _probe(name: str, python: str | None = None) -> dict[str, Any]:
    """Version ``name``'s server environment asked, in a process of its Python (``PROBE``; ``python``, else the one
    in its ``code/server``), nothing written there: its version, release, installation and kernel environment's
    folder as it works them out. ``Refused`` when it does not run, or says it is another version."""
    server = places.code_dir(name) / SERVER
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
    environment[places.INSTALLATION_ENV] = name
    said = ""
    try:
        done = subprocess.run([python or str(base.interpreter(server)), "-B", "-I", "-c", PROBE], env=environment,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120, **places.windowless())
        said = (done.stderr or done.stdout).strip()
        found = json.loads(done.stdout.strip().splitlines()[-1]) if done.returncode == 0 else None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as error:
        found, said = None, str(error)
    if not isinstance(found, dict) or found.get("version") != name or not isinstance(found.get("installation"), dict):
        last = said.splitlines()[-1] if said else "it said nothing"
        raise base.Refused(f"cad {name} in {server} does not run: {last}", "probe")
    return found


def development(name: str, python: str, cad: str, prefix: str) -> dict[str, Any]:
    """A development version, ``name`` (``<release>-dev.<stamp>``), whose code is a checkout's environment elsewhere
    (``prefix``, its ``python`` and ``cad``): its code marker written in ``versions/<name>/code`` naming that
    environment, which carries the kernel itself, so nothing is made and nothing of the checkout is copied
    (``scripts/install/dev_install.py``). Its record. ``ValueError`` for a name that is no development version."""
    from cad._internal.atomic_replace import write_bytes_atomic
    from cad_server._internal import installations

    if DEVELOPMENT.fullmatch(name or "") is None:
        raise ValueError(f"not a development version: {name!r}")
    for path in (python, cad, prefix):
        # The ``cad`` command's sh reads a development version's paths from its marker as they are written there.
        if os.name != "nt" and any(character in path for character in '"\\') or any(ord(c) < 32 for c in path):
            raise ValueError(f"the cad command cannot read the path {path!r}: move the checkout to a folder whose path "
                             "has no double quote, backslash or control character")
    code = places.code_dir(name)
    with install_lock():
        for folder in (places.versions_dir(), places.version_dir(name), code):
            _private(folder)
        record = {"schema": places.VERSION_SCHEMA, "version": name, "python": python, "cad": cad, "prefix": prefix,
                  "release": None, "kernel": None, "source": prefix, "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        write_bytes_atomic(code / places.VERSION_MARKER,
                           (json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
        installations._forget_read()
    return record


def _kernel(name: str, probe: dict[str, Any], say: Callable[[str], None]) -> str | None:
    """Version ``name``'s kernel environment made, where the version's own Python said it goes (``probe``):
    its folder, or None for a server environment that carries the kernel itself."""
    installation = base.Installation(**{key: probe["installation"][key] for key in
                                        base.Installation.__dataclass_fields__})
    if installation.kernel:
        return None
    env = Path(probe["base"])
    inside = os.path.normcase(os.path.realpath(places.code_dir(name))).rstrip(os.sep) + os.sep
    if not os.path.normcase(os.path.realpath(env)).startswith(inside):
        raise base.Refused(f"cad {name}'s kernel environment would be made outside its code: {env}", "probe")
    base._make(env, installation, say, inputs=probe.get("inputs"))
    return str(env)


# --- a version's server, asked through its own door ----------------------------------------------------

# How long a version's server is given to answer one question (``ask``), and to stop once asked (``stop_server``).
ASK_SECONDS = 10.0
SERVES_SECONDS = 5.0
STOP_SECONDS = 30.0


def endpoint(name: str) -> places.Endpoint:
    """Version ``name``'s server's door (on Windows its port file) and lock, in ``<engines>/<name>``: the one way
    to it. Never the flat door of 0.11.10 and earlier, which only clients of those releases use."""
    folder = places.engine_dir(name)
    return places.Endpoint(folder / f"{places.NAME}.{'port' if places.WINDOWS else 'door'}",
                           folder / f"{places.NAME}.lock")


def ask(name: str, message: dict[str, Any], *, seconds: float = ASK_SECONDS) -> dict[str, Any] | None:
    """``message`` asked of version ``name``'s running server through its own door (``endpoint``), nothing
    started: its answer, or None when none answers there, or none comes within ``seconds``."""
    return _ask_at(endpoint(name).address, message, seconds)


def flat_endpoint() -> places.Endpoint:
    """The flat door of 0.11.10 and earlier and its lock, in the engines' folder itself: held by the default
    version's server beside its own (``daemon.Bridge``), or by a server of those releases as its own."""
    folder = places.engines_dir()
    return places.Endpoint(folder / f"{places.NAME}.{'port' if places.WINDOWS else 'door'}",
                           folder / f"{places.NAME}.lock")


def ask_flat(message: dict[str, Any], *, seconds: float = ASK_SECONDS) -> dict[str, Any] | None:
    """``message`` asked of whichever server holds the flat door (``flat_endpoint``), nothing started: its answer,
    or None."""
    return _ask_at(flat_endpoint().address, message, seconds)


def _ask_at(door: Path, message: dict[str, Any], seconds: float) -> dict[str, Any] | None:
    """``message`` asked at ``door``, marked ``internal``: what one server, updater or command asks another of the
    device's servers is no command of the person's, which the last command's time never counts
    (``daemon.Daemon.ended``); a server of 0.11.10 or earlier reads past the mark."""
    from cad.engine import client

    message = {**message, "internal": True}
    answers: list[Any] = []

    def asking() -> None:
        try:
            connection = client._connect(door)
            if connection is not None:
                answers.append(client._exchange(connection, message, address=door))
        except (OSError, ValueError, ConnectionError, IndexError):
            pass

    thread = threading.Thread(target=asking, name="cad-ask", daemon=True)
    thread.start()
    thread.join(seconds)
    return answers[0] if answers and isinstance(answers[0], dict) else None


def connected(name: str) -> bool:
    """Whether anything is connected to the running server of version ``name``: work in flight there -- a build,
    a draw, an export, a request that serves, an agent's tool call (its ``working``) --, asked of it through its
    own door. An attached but idle app (a CAD app's hold) and an open page are not. A server that cannot say --
    it does not answer, or answers something else -- counts as connected: a server that runs keeps its version."""
    answer = ask(name, {"op": "working"})
    return not (isinstance(answer, dict) and answer.get("working") is False)


def stop_server(name: str) -> bool:
    """Version ``name``'s server, asked through its own door to stop once nothing is in flight (``{"op": "stop",
    "drain": true}``, the drain every release since 0.10 speaks), and waited for until it is gone (``gone``):
    whether it is. One that cannot be asked, or is not gone in time, is not stopped: False."""
    if ask(name, {"op": "stop", "drain": True}) is None:
        return False
    return gone(name)


def gone(name: str, seconds: float = STOP_SECONDS, *, besides: int | None = None) -> bool:
    """Whether version ``name``'s server, asked to stop (by this process or another, answered or not: a server on
    its way out answers nothing more), is gone within ``seconds``: its lock free -- held until its workers have
    stopped -- and then no process left running from its folder (``quiet``; ``besides`` as there). What every removal
    waits for before it tries the folder."""
    from cad.engine import client

    began = time.monotonic()
    try:
        if not client.wait_gone(timeout=seconds, endpoint=endpoint(name)):
            return False
    except ConnectionError:
        return False
    return quiet(places.version_dir(name), max(0.0, seconds - (time.monotonic() - began)), besides=besides)


# How long a removal waits for the processes of a version whose server has let its lock go to end (``quiet``): a
# server exits a moment after it lets go, its workers with it.
QUIET_SECONDS = 10.0


def quiet(folder: Path, seconds: float | None = None, *, besides: int | None = None) -> bool:
    """Whether no process runs from ``folder`` (``releases.running``), awaited for ``seconds`` at most
    (``QUIET_SECONDS``): a server lets its lock go, and removes it, before its process, and its workers', have ended.
    ``besides``: a process that does not count, nor its descendants: the one asking, where it runs from the folder
    itself (``cad uninstall`` typed in a terminal runs from the version it removes)."""
    from cad_server._internal import releases

    deadline = time.monotonic() + (QUIET_SECONDS if seconds is None else seconds)
    while releases.running(folder, besides=besides):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def serving(name: str) -> int | None:
    """The HTTP port version ``name``'s running server serves pages on, as its ``status`` says it; None while it
    serves none, or does not answer."""
    answer = ask(name, {"op": "status"})
    found = answer.get("serving") if isinstance(answer, dict) else None
    port = found.get("port") if isinstance(found, dict) else None
    return port if type(port) is int and 0 < port < 65536 else None


def serves(name: str) -> bool:
    """Whether version ``name``'s server runs, asked without making or taking anything: its door answers who it is
    (``{"op": "pid"}``). No engine folder, no lock file, or no answer: it does not (a server still starting, its lock
    taken and its door not made yet, among them: a removal takes the lock itself, ``_take``)."""
    found = endpoint(name)
    if not found.lock.exists() or not found.address.exists():
        return False
    return ask(name, {"op": "pid"}, seconds=SERVES_SECONDS) is not None


def flat(name: str | None) -> bool:
    """Whether version ``name``'s server holds the flat door of 0.11.10 and earlier (``places.engines_dir``'s own
    ``engine.door``, on Windows ``engine.port``, and ``engine.lock``) beside its own, and answers every client of
    those releases there: it is the version ``installations/current`` names, the record those clients start a server
    by. Only the hand-over from a shipped release (``cad setup --engine-update``) and a registration where none is
    current (``installations.bootstrap``) write that file."""
    from cad_server._internal import installations

    return name is not None and installations.current_version() == name


# --- use --------------------------------------------------------------------------------------------------


def used(name: str | None = None, *, now: float | None = None) -> bool:
    """Version ``name`` (this process's own, ``places.versioned``, by default) marked used by an agent at ``now``:
    its ``USED`` file's time set, where it is installed and that time is older than ``USE_SECONDS``. Quiet: a
    folder that cannot be written (an agent's sandbox) marks nothing, and its server marks the use as it takes the
    command's requests. Whether it was marked."""
    name = name or places.versioned()
    if name is None:
        return False
    now = time.time() if now is None else now
    try:
        folder = places.version_dir(name)
        if not (folder / places.CODE / places.VERSION_MARKER).is_file():
            return False
        path = folder / USED
        try:
            if 0 <= now - os.stat(path).st_mtime < USE_SECONDS:
                return False
        except FileNotFoundError:
            pass
        with open(path, "ab"):
            pass
        os.utime(path, (now, now))
    except (OSError, ValueError):
        return False
    return True


def last_used(name: str) -> float:
    """When version ``name`` was last used by an agent (``used``), or, never used, when it was installed (its code
    marker's time): the later of the two. 0 where neither can be read."""
    folder = places.version_dir(name)
    found = []
    for path in (folder / USED, folder / places.CODE / places.VERSION_MARKER):
        try:
            found.append(os.stat(path).st_mtime)
        except OSError:
            pass
    return max(found) if found else 0.0


# --- cleanup ----------------------------------------------------------------------------------------------


def due(last: float | None, now: float) -> bool:
    """Whether a server whose last cleanup was at ``last`` (monotonic; None: it has not cleaned since it started)
    cleans at ``now``: as it starts, then every ``CLEAN_SECONDS``."""
    return last is None or now - last >= CLEAN_SECONDS


def clean(*, now: float | None = None, told: Callable[[str], None] | None = None) -> dict[str, str]:
    """The cleanup (see the module), run by a process of the newest installed version (its server, ``daemon``):
    every older installed version no agent has used for ``UNUSED_SECONDS`` by ``now`` (``last_used``) removed
    (``_remove``); what earlier removals left aside; and the layout of 0.11.10 and earlier once that is safe
    (``legacy.remove``). Each line said to ``told``. What was done with each older version, by name: ``removed``,
    ``used`` (used lately: kept), or why it stays (``connected``, ``in use``, ``refused``). Nothing for a process that
    is not the newest installed version."""
    from cad_server._internal import legacy

    say = told or (lambda _line: None)
    now = time.time() if now is None else now
    own = places.versioned()
    done: dict[str, str] = {}
    if own is None or newest() != own:
        return done
    with install_lock():
        if newest() != own:  # a newer one installed meanwhile: its server cleans
            return done
        for name in present():
            if name == own or not older(name, own):
                continue
            done[name] = "used" if now - last_used(name) < UNUSED_SECONDS else _remove(name, say)
        root = places.versions_dir()
        for entry in _names(root):
            if entry.startswith(TRASH):
                shutil.rmtree(root / entry, ignore_errors=True)
        engines = places.engines_dir()
        for entry in _names(engines):
            if (places.VERSION.fullmatch(entry) and not os.path.lexists(root / entry)
                    and (engines / entry).is_dir()):
                try:
                    held = _take(engines / entry)
                except OSError:
                    continue
                if held is not None:
                    _drop(held, engines / entry)
                    shutil.rmtree(engines / entry, ignore_errors=True)
        if legacy.removable():
            legacy.remove(own, say)
    return done


# How often the newest version's server tries again to remove the layout of 0.11.10 and earlier between its cleanups,
# while that layout is there and was not safe to remove (``clean_legacy``).
LEGACY_SECONDS = 60.0


def clean_legacy(*, told: Callable[[str], None] | None = None) -> bool:
    """The layout of 0.11.10 and earlier removed (``legacy.remove``) by a process of the newest installed version once
    that is safe, between its cleanups (``clean``): its server tries every ``LEGACY_SECONDS`` while the layout is
    there. The cleanup as the server starts often finds it unsafe -- the shipped updater's helper that started this
    server still runs from that layout --, and a day is long to keep a kernel's worth of folders. Quiet while it is not
    safe (``legacy.unsafe``). Whether nothing of the layout is left."""
    from cad_server._internal import legacy

    own = places.versioned()
    if not legacy.removable():
        return True
    if own is None or newest() != own or legacy.unsafe(own) is not None:
        return False
    with install_lock():
        if newest() != own:
            return False
        return legacy.remove(own, told)


def _take(folder: Path) -> Any:
    """The engine lock in ``folder`` (``places.lock``): held, or None while a server holds it. ``OSError`` when
    the folder cannot hold it."""
    return places.lock(folder / f"{places.NAME}.lock")


def _drop(held: Any, folder: Path) -> None:
    """The engine lock ``held`` in ``folder`` let go and its file removed (``cad_server.engine.daemon.let_go``'s
    order: on POSIX removed while held)."""
    path = folder / f"{places.NAME}.lock"
    if os.name != "nt" and places.names(held, path):
        with contextlib.suppress(OSError):
            path.unlink()
    held.close()
    if os.name == "nt":
        with contextlib.suppress(OSError):
            path.unlink()


def _stopped(name: str, folder: Path, engine: Path, say: Callable[[str], None]) -> tuple[Any, str | None]:
    """Version ``name``'s server's lock taken for a removal: ``(held, None)``, or ``(None, why not)`` -- ``in use``
    (another process runs from its folder: its server is left alone), ``connected`` (work in flight there, or it did
    not stop in time), ``refused`` (the lock cannot be taken). A server with nothing in flight is stopped first
    (``stop_server``, which waits, bounded, for it and its workers to be gone); then one look (``releases.running``),
    never a wait: a process still running from the folder keeps it for the next pass."""
    from cad_server._internal import releases

    try:
        held = _take(engine)
        if held is None:
            # Its server runs. Another process running from the folder keeps it whatever the server does: the server
            # is left alone. Its own processes (it, its workers) do not count.
            answer = ask(name, {"op": "pid"})
            pid = answer.get("pid") if isinstance(answer, dict) else None
            if releases.running(folder, besides=pid if type(pid) is int else None):
                return None, "in use"
            if not connected(name) and stop_server(name):
                held = _take(engine)
    except OSError as error:
        say(f"cad {name} is kept: its server's lock cannot be taken ({error.strerror or error})")
        return None, "refused"
    if held is None:
        return None, "connected"
    if releases.running(folder):  # one look: a cleanup never waits on a process that runs from it
        _drop(held, engine)
        return None, "in use"
    return held, None


def remove(name: str, *, told: Callable[[str], None] | None = None) -> str:
    """Version ``name`` removed now, whenever it was last used: its server stopped where nothing is in flight there,
    its folder removed, as the cleanup removes one (``_remove``), under the install lock. What a development install
    going back to the release does with its development versions (``scripts/install/dev_install.py --release``), which
    sort after their release and would otherwise stay the newest installed. ``removed``, ``absent``, or why it stays
    (``connected``, ``in use``, ``refused``)."""
    with install_lock():
        return _remove(name, told or (lambda _line: None), because="")


def _remove(name: str, say: Callable[[str], None], *,
            because: str = f", which no agent has used for {round(UNUSED_SECONDS / 86400)} days") -> str:
    """Version ``name``'s folder removed, its data with it: its server stopped where nothing is in flight
    (``_stopped``), the folder renamed aside (``versions/.trash-*``), which a refusal (Windows: a file in use) turns
    into a skip, then removed, and the records naming it forgotten. ``removed``, ``absent``, or why it stays
    (``connected``, ``in use``, ``refused``)."""
    folder = places.version_dir(name)
    if not os.path.lexists(folder):
        return "absent"
    engine = places.engine_dir(name)
    held, why = _stopped(name, folder, engine, say)
    if held is None:
        return why or "connected"
    try:
        aside = places.versions_dir() / f"{TRASH}{name}-{os.getpid()}-{os.urandom(4).hex()}"
        try:
            os.rename(folder, aside)
        except OSError as error:
            say(f"cad {name} is kept for now: {error.strerror or error}")
            return "refused"
    finally:
        _drop(held, engine)
    shutil.rmtree(engine, ignore_errors=True)
    shutil.rmtree(aside, ignore_errors=True)
    _forget_records(folder)
    say(f"removed cad {name}{because}")
    return "removed"


def _forget_records(folder: Path) -> None:
    """The installation records (``installations/``, read by clients of 0.11.10 and earlier) naming an environment
    in ``folder``, a version's gone, removed."""
    from cad_server._internal import installations

    inside = os.path.normcase(os.path.abspath(folder)).rstrip(os.sep) + os.sep
    for record in installations.records():
        if os.path.normcase(os.path.abspath(record["prefix"])).startswith(inside):
            installations.forget(record["version"])


def _names(folder: Path) -> list[str]:
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []
