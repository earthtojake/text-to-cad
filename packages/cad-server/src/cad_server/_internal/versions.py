"""The versions of text-to-cad installed on this device: making one present, moving a channel to one, and
removing one no pointer names.

Each version lives in ``versions/<version>`` in the state folder (``cad.engine.places``): its ``code/`` and its
``data/``. Which version each delivery channel runs is its pointer (``cad_server._internal.pointers``).

**Present** (``make_present``). A version is present when its code marker, ``code/cad-version.json``, is there
and names a server environment whose Python and ``cad`` are (``places.version_record``, ``present``). Making it
present, under the device's install lock (``install_lock``), changes nothing outside ``versions/<version>/code``:

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
sandbox) -- it says so as a result (``Present.cannot``), never a traceback: the dispatcher and ``cad setup
--add`` turn it into one line naming the command to run outside the sandbox (``add_command``).

**Move** (``move``): every update of a channel, under the install lock. Equal: nothing to do. Older than the
channel's: stale, returned for the caller to say. Newer, or the channel's first use: the version made present,
its first start (``first_start``: its data imported, ``cad_server._internal.imports``, and the proof it runs:
``proof``, its server's own start sequence up to ready to serve, then gone), what the channel leaves carried over
into it (``imports.carry``: what the version left wrote after it was imported, or since another channel's move
imported it), the version left told where its data goes (``successor``), then the pointer written -- the one write
that is the update --, then every version no pointer names and nothing is connected to removed (``sweep``), then
what the version left held handed to the new one (``handover``: the flat door of 0.11.10 and earlier follows the
default channel, and the pages' port goes to the new version's server where the old one's stopped). A failure
before the pointer is written changes no pointer and no other version. A pointer that is there and cannot be read
now fails the move (``pointers.Unreadable``); one a crash emptied is written again. The default channel's first
move on a device with the layout of 0.11.10 and earlier imports from that layout, and the sweep removes the layout's
code, records and caches as soon as that is safe (``cad_server._internal.legacy``). Whether the automatic updates
are on plays no part: a newer version asked for is moved to.

**Servers** (``endpoint``, ``ask``). Each version's server is reached through its own door alone,
``<engines>/<version>``: asked whether work is in flight (``connected``), asked to stop (``stop_server``), started
(``start_server``). Work in flight is what keeps a version: a build, a draw, an export, a request that serves, an
agent's tool call. An app attached and idle, or a page open, does not.

**Removal** (``remove``, ``sweep``). Garbage is a version no pointer names (nor the default channel's version as
``pointers.default`` resolves it, where it has no pointer, nor the one the mirror names) that a pointer has named
once (``NAMED``, written before the pointer that first names it: ``used``). A version installed and never named --
an update's target before its setup runs, a release the ``cad`` command or a launcher installs before it moves its
channel, one ``cad setup --add`` installs, one whose proof failed after it imported a copy of another's data -- is
never removed by a sweep, nor is a folder whose code is incomplete (no code marker: an install cut short); ``cad
doctor`` lists them and ``cad doctor --prune`` removes them (``sweep(unused=True)``), and an updater removes its own
earlier target once it prepares a newer one (``remove_unused``). Every pointer, and the mirror, is read as it is:
one that cannot be read stops every removal for that pass (``pointers.Unreadable``), said.

A used version's data goes to its successor before its folder goes: the version the channel that last left it
moved to (``successor``, written by that move, ``SUCCESSOR`` in the version's folder; by an import that took its
data, where none was; when that version goes in turn, those naming it are told its own). Only a process of that
successor carries the data and removes the folder (``_acts_for``): it writes the records, Recents and ledger in its
own formats; any other leaves the version for it (``fate``: ``heir``), its server's next tending or its next move.
Where none is known, it is gone, or it is older (going back from a development build), the folder stays, and ``cad
doctor`` says why.

``cad uninstall`` without ``--purge`` takes the default channel off its version and removes that version's code
alone (``remove_code``): its data stays (``UNINSTALLED``), every sweep keeps it, and the default channel's next first
use leaves it, as a move leaves a version: the same release finds its data, a newer one has it carried in and the
folder goes. ``fate`` has the table of every state a version folder can be in and what each removal does with it.

One is removed under the install lock: its server's lock taken (the one its server takes to start, in
``<engines>/<version>``), so none starts meanwhile; a running server is left alone where another process runs from
the folder (``releases.running``, its own processes aside: the folder would stay all the same), and is otherwise
asked whether anything is connected to it (``connected``: a running server that cannot say counts as connected,
and stays) and stopped when nothing is (``stop_server``, the one bounded wait); then one look, never a wait, for a
process still running from the folder, which keeps it for the next pass; what the folder holds that its successor
lacks carried over (``imports.carry``: a carry-over that could not read or write all of it keeps the folder for the
next pass), what it kept for sending handed on (``_hand_on``); the folder renamed aside (``versions/.trash-*``),
which a refusal (Windows: a file in use) turns into a skip, then removed. ``sweep`` does that for every such
version, removes the layout of 0.11.10 and earlier once the default channel has left it and that is safe, in a
process of the default channel's version (``legacy.remove``, which carries it over too), and clears what an earlier
removal left.

Who removes a folder: every move (run by the version moved to: the heir of what its channel leaves), ``cad doctor
--prune``, and every running server as it tends itself (``garbage``, then ``sweep`` sparing its own version). A
server whose version no pointer names stops itself once nothing is in flight (``retiring``), handing the port it
served pages on to its heir's server as it goes (``hand_port``); it never removes its own folder, which it runs from:
its heir's server, or a later move, does.
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cad.engine import places
from cad_server._internal import base

__all__ = ["CANNOT", "LOCK", "NAMED", "SUCCESSOR", "UNINSTALLED", "Moved", "Present", "Refusal", "add", "add_command",
           "answered_port", "ask", "ask_flat", "connected", "development", "endpoint", "fate", "first_start", "flat",
           "flat_endpoint", "folders", "garbage", "hand_port", "handover", "install_lock", "make_present", "mend",
           "move", "older", "order", "present", "proof", "prune", "prune_plan", "remove", "remove_code", "remove_now",
           "remove_unused", "retiring", "runs_from", "serves", "serving", "start_server", "stop_server", "successor",
           "sweep", "used"]

# The device's install lock, in the state folder: every install, move and removal holds it (``cad setup``'s too).
LOCK = "install.lock"
SERVER = "server"
TRASH = ".trash-"
# In a version's folder: the version the channel that last left it moved to, where its data goes (``successor``).
SUCCESSOR = "successor"
# In a version's folder: a pointer has named it -- written, durably, before the pointer that first names it
# (``move``) --, so it has been a channel's and its data goes only by way of its successor (``used``).
NAMED = "named"
# In a version's folder: ``cad uninstall`` (no ``--purge``) took the default channel off it and removed its code, and
# kept its data for a later install (``remove_code``): the default channel's next first use leaves it (``move``). Where
# the system refused the code's removal (Windows: the uninstall ran from it), the next sweep removes the code.
# A move to it clears this.
UNINSTALLED = "uninstalled"
CACHEDIR_TAG = ("Signature: 8a477f597d28d172789f06886806bc55\n"
                "# This file is a cache directory tag created by text-to-cad: a version's code, made again whole\n"
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
    """The device's install lock (``LOCK`` in the state folder), waiting for any other holder -- another process,
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
    question of which version is older asks (``older``, ``folders``, ``imports.source``, ``move``). Releases sort as
    PEP 440 sorts them. A development build, ``<release>-dev.<stamp>``, is NEWER than the release whose numbers it
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
    """Every version's folder in ``versions/``, present or not, oldest first (``order``)."""
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
    """The versions present on this device -- each code marker there, its Python and ``cad`` with it -- oldest
    first (``order``; a name that orders as no release first)."""
    return [name for name in folders(state) if _alive(name, state) is not None]


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
        with install_lock(waiting=lambda: say("waiting for another install of text-to-cad to finish")):
            found = _alive(name)
            if found is not None:
                return Present(name, found)  # made meanwhile, by the process this one waited for
            record = _make(name, say)
    except base.Refused as refused:
        return Present(name, None, cannot=refused.cause if refused.cause in CANNOT else None, error=str(refused))
    except PermissionError as error:
        return Present(name, None, cannot="denied", error=base._cannot(f"text-to-cad {name}'s folder", error,
                                                                       f"text-to-cad {name}"))
    except OSError as error:
        return Present(name, None, error=f"text-to-cad {name} could not be installed: {error.strerror or error}")
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
    raise base.Refused(f"text-to-cad {name} is a development version: only its own checkout installs it")


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
        raise base.Refused(f"text-to-cad {name} in {server} does not run: {last}", "probe")
    return found


def proof(name: str, *, timeout: float | None = None) -> None:
    """That present version ``name`` starts (``Refused`` in one line when not): its server's own start sequence run
    up to ready to serve (``cad_server.engine.daemon.proof``: its data imported, its engine folder, its lock and its
    door made, the server built over its data), in a process of its own Python that then exits, binding no port and
    leaving no process. A server of it that runs already has started: nothing is run."""
    if serves(name):
        return
    record = places.version_record(name)
    python = record["python"] if record is not None else str(base.interpreter(places.code_dir(name) / SERVER))
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
    environment[places.INSTALLATION_ENV] = name
    said = ""
    try:
        done = subprocess.run([python, "-B", "-P", "-m", "cad_server._internal.engine_daemon", "--proof"],
                              env=environment, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout or START_SECONDS,
                              **places.windowless())
        code, said = done.returncode, (done.stderr or done.stdout).strip()
    except (OSError, subprocess.SubprocessError) as error:
        code, said = None, str(error)
    if code != 0:
        last = said.splitlines()[-1] if said else f"it exited {code}"
        raise base.Refused(f"text-to-cad {name} does not start: {last.removeprefix('cad: ')}", "probe")


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
        raise base.Refused(f"text-to-cad {name}'s kernel environment would be made outside its code: {env}", "probe")
    base._make(env, installation, say, inputs=probe.get("inputs"))
    return str(env)


# --- a version's first start ----------------------------------------------------------------------------


def first_start(name: str, leaving: str | None = None, *, legacy_left: bool = False,
                told: Callable[[str], None] | None = None) -> Any:
    """Present version ``name``'s first start: its data imported where it is not
    (``imports.ensure``, from what its channel is ``leaving``), then the proof it starts (``proof``: its server's own
    start sequence). What the import did (``imports.Imported``); ``Refused`` when the version does not start."""
    from cad_server._internal import imports

    found = imports.ensure(name, leaving, legacy_left=legacy_left, told=told)
    proof(name)
    return found


# --- moving a channel -----------------------------------------------------------------------------------


@dataclass
class Moved:
    """What ``move`` did: ``kind`` ``same`` (the channel is on that version: run it), ``stale`` (the version is
    older than the channel's, ``old``: the caller says so), ``moved`` (the pointer names ``new`` now),
    ``cannot`` (``new`` cannot be installed from this shell: ``error``, ``present.cannot``) or ``failed`` (nothing
    changed: ``error``). ``imported``: what the first start imported; ``removed``: what the sweep did with each
    version no pointer names; ``said``: what was said along the way."""

    kind: str
    channel: str | None
    new: str
    old: str | None
    error: str | None = None
    present: Present | None = None
    imported: Any = None
    removed: dict[str, str] = field(default_factory=dict)
    said: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.kind in ("same", "moved")


def move(channel: str | None, new: str, *, told: Callable[[str], None] | None = None,
         from_development: bool = False, mend: bool = False) -> Moved:
    """Channel ``channel`` (None: the default) moved to version ``new`` (see the module): what was done
    (``Moved``). ``from_development``: a release may replace a development version newer than it (``cad setup``,
    a person's install command, going back from ``scripts/install/dev_install.py``); nothing else moves a channel
    to an older version. ``mend`` (``cad setup`` and the updater alone): a pointer that names no version is written
    again, to ``new`` where that is no older than the newest version a channel has been on (``_newest_named``), else the
    move is ``stale``; without it such a pointer fails the move, as one that cannot be read now always does. The
    default channel's first use where ``cad uninstall`` left its data (``UNINSTALLED``) leaves that version: its data
    carried into ``new`` where ``new`` is newer, and it goes. ``ValueError`` for a name that is no channel or no
    version."""
    from cad_server._internal import legacy, pointers

    said: list[str] = []

    def say(line: str) -> None:
        said.append(line)
        if told is not None:
            told(line)

    channel = None if channel is None else pointers.channel_name(channel)  # ``default`` is the default
    places.version_dir(new)
    with install_lock(waiting=lambda: say("waiting for another install of text-to-cad to finish")):
        mended = False
        try:
            current = pointers.read(channel)
        except pointers.Unreadable as unreadable:
            # There and not readable now, or naming no version: nothing moves on a guess of which version it names.
            # Only ``cad setup`` and the updater write one that names no version again (``mend``), never to an older
            # version than the newest a channel has been on.
            if not (mend and unreadable.corrupt):
                return Moved("failed", channel, new, None, f"{unreadable}: run the command again, and if it still "
                             "cannot be read, cad doctor says why", said=said)
            floor = _newest_named()
            if floor is not None and floor != new and older(new, floor) and not (
                    from_development and DEVELOPMENT.fullmatch(floor) and not DEVELOPMENT.fullmatch(new)):
                return Moved("stale", channel, new, floor, said=said)
            say(f"{unreadable}: it is written again")
            current, mended = None, True
        first_default = channel is None and current is None and not mended
        old = current
        if first_default:
            leaving = pointers._current(None)  # the layout of 0.11.10 and earlier, where the install command ran
            old = leaving[0] if leaving is not None and leaving[1] else None
        legacy_left = first_default and legacy.present()
        if first_default and old is None and not legacy_left:
            # The data ``cad uninstall`` kept: the default channel leaves it now, unless ``new`` is older (a fresh
            # start then, and its data stays for a newer one).
            old = _uninstalled_left()
            if old is not None and older(new, old):
                old = None
        if old == new and not first_default:
            if channel is None:
                _repair(new, say)  # what a move cut short after its pointer left: the mirror, the sweep
            return Moved("same", channel, new, old, said=said)
        if old is not None and older(new, old) and not (
                from_development and DEVELOPMENT.fullmatch(old) and not DEVELOPMENT.fullmatch(new)):
            return Moved("stale", channel, new, old, said=said)
        made = make_present(new, told=say)
        if not made.ok:
            return Moved("cannot" if made.cannot else "failed", channel, new, old, made.error, made, said=said)
        try:
            imported = first_start(new, None if legacy_left else old, legacy_left=legacy_left, told=say)
        except base.Refused as refused:
            return Moved("failed", channel, new, old, str(refused), made, said=said)
        source = getattr(getattr(imported, "source", None), "version", None) if getattr(imported, "done", False) \
            and getattr(getattr(imported, "source", None), "kind", None) == "version" else None
        # What the channel leaves wrote since it was imported (or since another channel's move imported it): carried
        # over, never from a newer version into an older one (going back from a development build).
        from cad_server._internal import imports

        if legacy_left:
            imports.carry(imports.of_legacy(), new, told=say)
        elif old is not None and old != new and older(old, new) and imports.imported(old):
            imports.carry(imports.of_version(old), new, told=say)
        with contextlib.suppress(OSError):
            (places.version_dir(new) / UNINSTALLED).unlink()  # a channel is on it again: its data is kept
        if old is not None and old != new and not legacy_left:
            try:
                _succeed(old, new)  # before the pointer: a version left never lacks where its data goes
            except OSError as error:
                say(f"text-to-cad {old} could not be told where its data goes ({error.strerror or error}): once no "
                    "channel is on it, its folder stays, and cad doctor says why")
        if source not in (None, old, new) and successor(source)[0] is None:
            # Its data imported from a version no channel is on (one ``cad uninstall`` or a channel left with nowhere
            # for its data to go): that version's data goes here, and it goes after the carry.
            try:
                if source not in pointers.named():
                    _succeed(source, new)
            except OSError:
                pass
        try:
            for name in ({current} if current is not None else set()) | {new}:
                _name(name)  # before the pointer: a version a pointer named never passes for one never used
            pointers.write(channel, new, mirrored=False)
        except OSError as error:
            return Moved("failed", channel, new, old, f"the pointer could not be written: {error.strerror or error}",
                         made, imported, said=said)
        # The pointer moved: from here a failure leaves both versions, and the next move or sweep finishes.
        if channel is None:
            try:
                pointers.mirror(new)
            except OSError as error:
                say("the record clients of 0.11.10 and earlier find the server by could not be written: "
                    f"{error.strerror or error}")
        # The port the version left serves pages on, read before the sweep may stop it (``handover``). The layout
        # of 0.11.10 and earlier is never asked: its server leaves by its own update or ``cad stop``.
        port = serving(old) if old is not None and old != new and not legacy_left else None
        removed = sweep(told=say, acting=new if _own() in (None, new) else None)
        handover(channel, None if legacy_left else old, new, port, told=say)
        return Moved("moved", channel, new, old, None, made, imported, removed, said)


def _repair(name: str, say: Callable[[str], None]) -> None:
    """The default channel on ``name`` already, as a move that was cut short after its pointer leaves it: the mirror
    for 0.11.10 and earlier written where it names another version, and the sweep it did not reach. Quiet when there
    is nothing to do."""
    from cad_server._internal import installations, pointers

    if installations.current_version() != name:
        try:
            pointers.mirror(name)
        except OSError as error:
            say("the record clients of 0.11.10 and earlier find the server by could not be written: "
                f"{error.strerror or error}")
            return
    sweep(told=say, acting=name if _own() in (None, name) else None)


def handover(channel: str | None, old: str | None, new: str, port: int | None, *,
             told: Callable[[str], None] | None = None) -> bool:
    """After channel ``channel`` moved from ``old`` to ``new`` and the sweep that followed: what the old version's
    server held, handed to the new one's.

    - The flat door of 0.11.10 and earlier follows the default channel's version (``flat``): each server running
      asked to look again (``{"op": "bridge"}``), the one left first, so it lets go and the new one takes it.
    - The pages' port: where ``old``'s server served pages on ``port`` and is gone now -- nothing was in flight, and
      no other pointer names ``old`` --, ``new``'s server, started for it, serves on that port, with the page token
      it imported from ``old``, so a page open on it reloads into ``new`` and a link from before still opens.
      Where ``old``'s server still runs (busy, or another channel's), it keeps its port and pages, and ``new``
      takes the next free port when it first serves (``daemon.bind``).

    Whether the port was handed over. Nothing here fails a move: what did not happen is said."""
    say = told or (lambda _line: None)
    if channel is None:
        if old is not None and serves(old):
            ask(old, {"op": "bridge"})
        if serves(new):
            ask(new, {"op": "bridge"})
    if port is None or old is None or serves(old):
        return False
    if not start_server(new):
        say(f"text-to-cad {new}'s server did not start to serve on port {port}: it serves when it is next asked")
        return False
    answer = ask(new, {"op": "http", "port": port}, seconds=START_SECONDS)
    if not isinstance(answer, dict) or "failed" in answer or not answer.get("url"):
        why = (answer or {}).get("failed") or "it did not answer"
        say(f"text-to-cad {new}'s server could not take port {port} from {old}'s: {why}")
        return False
    got = answered_port(answer)
    if got != port:  # the port still held, as a server slow to exit holds it: that server hands it on as it goes
        say(f"text-to-cad {new} serves pages on port {got}: port {port} is still held, and {old}'s server hands it on "
            "as it stops (hand_port)")
        return False
    say(f"text-to-cad {new} serves pages on port {port}, as {old} did")
    return True


def answered_port(answer: dict[str, Any] | None) -> int | None:
    """The port an ``{"op": "http"}`` answer says pages are served on: its ``port``, else its ``url``'s; None."""
    if not isinstance(answer, dict):
        return None
    port = answer.get("port")
    if type(port) is int:
        return port
    from urllib.parse import urlsplit

    try:
        return urlsplit(str(answer.get("url") or "")).port
    except ValueError:
        return None


# How long a server stopping gives its heir's server to take the port it served pages on (``hand_port``).
HAND_SECONDS = 10.0


def hand_port(name: str, port: int | None) -> bool:
    """A server of version ``name`` as it stops, its pages' listener closed, that served pages on ``port`` while no
    pointer names its version any more (its channel moved on): its heir's server (``successor``), where that runs,
    asked to take that port too (``{"op": "http", "port"}``), so a page open on it reloads into the version its channel
    moved to however long this server took to exit after the move's handover asked (``handover``). Nothing where a
    pointer still names it (``cad stop``), where the pointers cannot be read, or where the heir's server does not run
    (``handover`` then gives it the port as it starts it). Whether it was asked. Never raises."""
    try:
        if not port or name in _kept():
            return False
        heir = successor(name)[0]
        if heir is None or not serves(heir):
            return False
        return ask(heir, {"op": "http", "port": port}, seconds=HAND_SECONDS) is not None
    except Exception:  # noqa: BLE001 - a server's last act never fails its stop
        return False


# --- removing one -----------------------------------------------------------------------------------------


def serves(name: str) -> bool:
    """Whether version ``name``'s server runs, asked without making or taking anything: its door answers who it is
    (``{"op": "pid"}``). No engine folder, no lock file, or no answer: it does not (a server still starting, its lock
    taken and its door not made yet, among them: a removal takes the lock itself, ``_take``)."""
    found = endpoint(name)
    if not found.lock.exists() or not found.address.exists():
        return False
    return ask(name, {"op": "pid"}, seconds=SERVES_SECONDS) is not None


# --- a version's server, asked through its own door ----------------------------------------------------

# How long a version's server is given to answer one question (``ask``), to stop once asked (``stop_server``),
# and to answer at its door once started (``start_server``).
ASK_SECONDS = 10.0
SERVES_SECONDS = 5.0
STOP_SECONDS = 30.0
START_SECONDS = 60.0


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
    device's servers is no command of the person's, which the quiet hour an automatic update waits for counts
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


def start_server(name: str, *, timeout: float = START_SECONDS) -> bool:
    """Present version ``name``'s server started, as a client of that version starts it (``client._start``):
    detached, its own Python, its name told (``places.INSTALLATION_ENV``), nothing of this process's import
    path; whether it answers at its door within ``timeout``. One running already is not started again."""
    from cad.engine import client

    if ask(name, {"op": "pid"}) is not None:
        return True
    record = _alive(name)
    if record is None or client._sandboxed():  # a shell whose sandbox refuses the port a server needs: none started
        return False
    folder = places.make_engine_dir(places.engine_dir(name))
    env = {key: value for key, value in os.environ.items()
           if key not in ("PYTHONPATH", "PYTHONHOME", "PYTHONPYCACHEPREFIX", "DO_NOT_TRACK", "CAD_TELEMETRY")}
    env[places.INSTALLATION_ENV] = name
    try:
        process = subprocess.Popen([record["python"], "-P", "-m", "cad_server._internal.engine_daemon"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env=env, cwd=str(folder if not places.WINDOWS else folder.parent),
                                   **places.detached())
    except OSError:
        return False
    # Reaped when it exits, however long after: the server outlives the request that started it.
    threading.Thread(target=process.wait, name="cad-reap", daemon=True).start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ask(name, {"op": "pid"}, seconds=2.0) is not None:
            return True
        if process.poll() not in (None, 0):
            return False
        time.sleep(0.05)
    return False


def serving(name: str) -> int | None:
    """The HTTP port version ``name``'s running server serves pages on, as its ``status`` says it; None while it
    serves none, or does not answer."""
    answer = ask(name, {"op": "status"})
    found = answer.get("serving") if isinstance(answer, dict) else None
    port = found.get("port") if isinstance(found, dict) else None
    return port if type(port) is int and 0 < port < 65536 else None


def flat(name: str | None, state: Path | None = None) -> bool:
    """Whether version ``name``'s server holds the flat door of 0.11.10 and earlier (``places.engines_dir``'s own
    ``engine.door``, on Windows ``engine.port``, and ``engine.lock``) beside its own, and answers every client of
    those releases there: it is the default channel's version as a command with no pin resolves it
    (``pointers.default``). A named channel's version never does, unless the default channel is on it too."""
    from cad_server._internal import pointers

    return name is not None and pointers.default(state).version == name


def retiring(name: str, working: bool) -> bool:
    """Whether version ``name``'s running server, with work in flight or not (``working``), stops now: no pointer
    names its version, it is not the default channel's as resolved with no pointer, and nothing is in flight.
    Decided under the install lock, never waited for: while a move or an install holds it (a pointer about to
    name this version, among them), it is not decided now (False); nor while a pointer cannot be read."""
    from cad_server._internal.file_lock import attempt

    if working:
        return False
    try:
        state = places.state_dir()
        if not state.is_dir():
            return False
        with attempt(state / LOCK) as held:
            return held and name not in _kept()
    except OSError:  # a pointer that cannot be read (``pointers.Unreadable``) among them
        return False


def used(name: str) -> bool:
    """Whether version ``name`` has been a channel's: a pointer has named it (``NAMED``, written before the pointer that
    first named it), so its folder goes only by way of its successor (``successor``), its data carried there first.
    One installed and never named -- an update's target waiting for its setup, a release a launcher or the ``cad``
    command installed before moving its channel, one whose proof failed after its import -- has none: its data, where
    it has any, is a copy of another version's."""
    return os.path.lexists(places.version_dir(name) / NAMED)


def _name(name: str) -> None:
    """Version ``name`` marked as a pointer's (``NAMED``), durably, where it is not yet. ``OSError`` when it cannot be."""
    from cad_server._internal.pointers import _land

    path = places.version_dir(name) / NAMED
    if os.path.isdir(places.version_dir(name)) and not os.path.lexists(path):
        _land(path, b"")


def _newest_named(*, present_only: bool = False) -> str | None:
    """The newest version a pointer has named (``used``; with ``present_only``, one present too): no pointer is written
    again naming an older one (``move``'s ``mend``, ``mend``). None where there is none."""
    found = [name for name in folders() if used(name) and (not present_only or _alive(name) is not None)]
    return max(found, key=_order_key) if found else None


def _own() -> str | None:
    """The version this process is (``places.versioned``): None for a checkout's or a test's process."""
    return places.versioned()


def _acts_for(heir: str, acting: str | None = None) -> bool:
    """Whether this process may carry a version's data into ``heir`` and remove it: only a process of ``heir`` itself
    (``acting``, else this process's version), which writes ``heir``'s records, Recents and ledger in ``heir``'s own
    formats. Any other leaves that version for ``heir``'s server, or ``heir``'s next move (``fate``: ``heir``). A move
    acts as the version it moves to (``move``): every move runs in that version's own process (a pinned command of
    it, its setup, its launcher's), or in a test's, which has none."""
    return (acting or _own()) == heir


def successor(name: str) -> tuple[str | None, str]:
    """Where version ``name``'s data goes when its folder does: the version the channel that last left it moved to
    (``SUCCESSOR``), while it is there with its data and not older; else None and why, in words."""
    from cad_server._internal import imports

    path = places.version_dir(name) / SUCCESSOR
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None, "no channel has moved from it to another version, so where its data would go is unknown"
    except OSError as error:
        return None, f"{path} cannot be read ({error.strerror or error})"
    if not places.VERSION.fullmatch(text):
        return None, f"{path} names no version"
    if not os.path.isdir(places.version_dir(text)) or not imports.imported(text):
        return None, f"text-to-cad {text}, where its data would go, is gone"
    if older(text, name):
        return None, f"text-to-cad {text}, where its data would go, is older: data never goes back to an older version"
    return text, ""


def _succeed(old: str, new: str) -> None:
    """Version ``old`` told its data goes to ``new`` (``SUCCESSOR``), durably: a channel leaves it for ``new`` now."""
    from cad_server._internal.pointers import _land

    if os.path.isdir(places.version_dir(old)):
        _land(places.version_dir(old) / SUCCESSOR, f"{new}\n".encode("utf-8"))


def _forward(gone: str, heir: str | None) -> None:
    """Version ``gone`` removed: each other version whose data went to it told to send it to ``heir``, where it went."""
    if heir is None:
        return
    for name in folders():
        path = places.version_dir(name) / SUCCESSOR
        try:
            if path.read_text(encoding="utf-8").strip() == gone:
                _succeed(name, heir)
        except OSError:
            continue


def _uninstalled_left() -> str | None:
    """The version ``cad uninstall`` took the default channel off and kept the data of (``UNINSTALLED``), which the
    default channel's next first use leaves (``move``): the newest such, whose data is there and that no pointer
    names. None where there is none."""
    from cad_server._internal import imports, pointers

    try:
        named = pointers.named()
    except OSError:
        return None
    found = [name for name in folders() if os.path.lexists(places.version_dir(name) / UNINSTALLED)
             and name not in named and imports.imported(name)]
    return max(found, key=_order_key) if found else None


def _code_left(name: str) -> bool:
    """Whether ``cad uninstall`` removed version ``name`` and the system refused its code then (``UNINSTALLED``, its
    ``code/`` still there): the next sweep removes the code and keeps the data."""
    folder = places.version_dir(name)
    return os.path.lexists(folder / UNINSTALLED) and os.path.lexists(folder / places.CODE)


# What a sweep does with a version that no pointer names (``fate``), and what ``remove`` answers, in a report's words.
FATES = ("named", "unused", "partial", "heir", "uninstalled", "successor")


def fate(name: str, kept: set[str], *, unused: bool = False, acting: str | None = None) -> str | None:
    """What a sweep does with version ``name``'s folder, given the versions no removal takes (``kept``): None, it goes;
    else why not -- ``named``; ``unused`` (installed and never a pointer's, ``used``) or ``partial`` (that, its code
    incomplete), which ``cad doctor --prune`` removes (``unused``: then None); ``heir`` (a pointer's once, its data
    going to a successor that is not this process's version, ``_acts_for``: left for that version's server or next
    move); ``uninstalled`` (its data kept by ``cad uninstall`` for a later install); ``successor`` (a pointer's once,
    and where its data would go is not known, ``successor``). The states, and what each removal does with each:

    ============================  ==============  ==============  =================  ===============  ==============
    version folder                sweep, tend     doctor --prune  cad uninstall      a move           later install
    ============================  ==============  ==============  =================  ===============  ==============
    named (a pointer)             kept            kept            default's: code    the channel      --
                                                                  goes, data kept    leaves it: a
                                                                  (uninstalled)      successor
    installed, never named        kept (unused)   removed whole   left               to it: named     --
    (data, if any, a copy)
    data only, after uninstall    kept            kept            --purge removes    default's first  same version:
    (``UNINSTALLED``)             (uninstalled)                                      use leaves it    its data found;
                                                                                                      newer: carried,
                                                                                                      it goes
    named once, left, heir H      H's process:    as a sweep      --purge removes    --               --
                                  carried, gone;
                                  another: left
    named once, left, no heir     kept, said      kept, said      --purge removes    an import from   as a move
    (successor)                                                                      it names its
                                                                                     heir
    its channel forgotten by      --              the default's   --                 --               --
    --prune                                       its heir where
                                                  it can be, else
                                                  removed whole
    ============================  ==============  ==============  =================  ===============  ==============

    A sweep takes nothing while a pointer cannot be read, and never a folder a process runs from or whose server has
    work in flight."""
    if name in kept:
        return "named"
    if not used(name):
        if unused:
            return None
        return "unused" if places.version_record(name) is not None else "partial"
    heir = successor(name)[0]
    if heir is not None:
        return None if _acts_for(heir, acting) else "heir"
    if os.path.lexists(places.version_dir(name) / UNINSTALLED):
        return "uninstalled"
    return "successor"


def garbage(spare: str | None = None) -> bool:
    """Whether a ``sweep`` would find anything to do, read without the install lock: a version folder it removes
    (``fate``: no pointer names it but ``spare``, the asker's own; a pointer's once, and this process its heir), the
    code ``cad uninstall`` could not remove, a removal's leftovers, or the layout of 0.11.10 and earlier once the
    default channel has left it and this process is that channel's version. False while a pointer cannot be read. A
    running server asks it at each tending before it sweeps."""
    from cad_server._internal import legacy, pointers

    try:
        kept = _kept() | ({spare} if spare else set())
        for name in folders():
            if fate(name, kept) is None or (name not in kept and _code_left(name)):
                return True
        if any(entry.startswith(TRASH) for entry in _names(places.versions_dir())):
            return True
        default = pointers.read(None)
        return default is not None and _acts_for(default) and legacy.removable()
    except OSError:
        return False


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


def _kept(state: Path | None = None) -> set[str]:
    """The versions no removal takes: those a pointer names, the default channel's as it resolves with no pointer
    (``pointers.default``: the one a command with no pin runs), and the one the mirror for 0.11.10 and earlier names
    (``installations/current``): it follows the default pointer, and names another version only while a move that
    could not write it has left it behind, when a client of those releases still starts that version.
    ``pointers.Unreadable`` when a pointer, or the mirror, is there and cannot be read: then nothing is removed."""
    from cad_server._internal import installations, pointers

    found = pointers.named(state)
    default = pointers.default(state).version
    mirrored = installations.current_version(pointers._folder(state), strict=True)
    mirrored = mirrored if mirrored and places.version_record(mirrored, _root(state)) is not None else None
    return found | ({default} if default else set()) | ({mirrored} if mirrored else set())


def remove(name: str, *, told: Callable[[str], None] | None = None) -> str:
    """Version ``name`` removed as a sweep removes it (see the module): ``removed``, or why not -- ``named``,
    ``unused``, ``partial``, ``heir``, ``uninstalled``, ``successor`` (``fate``), ``connected`` (its server runs and
    something is connected, or it cannot say), ``in use`` (a process runs from its folder), ``carry`` (what it holds
    could not all be carried over), ``refused`` (the system refused the rename or the lock) -- or ``absent``."""
    say = told or (lambda _line: None)
    with install_lock():
        if not os.path.lexists(places.version_dir(name)):
            return "absent"
        why = fate(name, _kept())
        if why is not None:
            return why
        return _remove(name, say)


def remove_unused(name: str, *, told: Callable[[str], None] | None = None) -> str:
    """Version ``name`` removed where no pointer names it and none ever did (``used``): an updater's own earlier
    target, which it made and never moved to, as it prepares a newer one -- its data, where its proof imported some, a
    copy. ``removed``, ``absent``, or why not (``named``, ``used``, ``connected``, ``in use``, ``refused``)."""
    say = told or (lambda _line: None)
    with install_lock():
        if not os.path.lexists(places.version_dir(name)):
            return "absent"
        if name in _kept():
            return "named"
        if used(name):
            return "used"
        return _remove(name, say)


def _hand_on(name: str, acting: str | None = None) -> None:
    """What version ``name`` kept for sending and has not sent -- its telemetry spool and kept batches, each row saying
    who counted it -- moved, as it goes, to the version that sends next (``analytics.hand_on``): this process's own
    version, which writes them in its own format (its heir, the one process that removes a version a pointer named);
    for a process of no version (a checkout's, a test's), the default channel's, else the newest other version a
    pointer names. Nothing goes where no other version is there to take it."""
    from cad_server import analytics
    from cad_server._internal import imports, pointers
    from cad_server.settings import FILE

    own = acting or _own()
    if own is not None:
        if own != name and imports.imported(own):
            analytics.hand_on(places.data_dir(name) / FILE, places.data_dir(own) / FILE)
        return
    named = [pointer.version for pointer in pointers.listing() if pointer.version != name and imports.imported(pointer.version)]
    if not named:
        return
    default = pointers.read(None)
    target = default if default in named else max(named, key=_order_key)
    analytics.hand_on(places.data_dir(name) / FILE, places.data_dir(target) / FILE)


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
        say(f"text-to-cad {name} is kept: its server's lock cannot be taken ({error.strerror or error})")
        return None, "refused"
    if held is None:
        return None, "connected"
    if releases.running(folder):  # one look: a sweep never waits on a process that runs from it
        _drop(held, engine)
        return None, "in use"
    return held, None


def _remove(name: str, say: Callable[[str], None], *, whole: bool = False, acting: str | None = None) -> str:
    """Version ``name``'s folder removed (see the module), its fate decided already: its successor, where it has been
    a pointer's, given what it holds first, by a process of that successor alone (``_acts_for``). ``whole`` (``cad doctor
    --prune`` forgetting a channel whose version nothing can take the data of): removed with its data, no carry."""
    from cad_server._internal import imports

    folder = places.version_dir(name)
    if not os.path.lexists(folder):
        return "absent"
    heir = None
    if used(name) and not whole:
        heir, why = successor(name)
        if heir is None:
            say(f"text-to-cad {name} is kept: {why}")
            return "uninstalled" if os.path.lexists(folder / UNINSTALLED) else "successor"
        if not _acts_for(heir, acting):
            return "heir"  # its data is carried by a process of its heir, in that version's formats
    engine = places.engine_dir(name)
    held, why = _stopped(name, folder, engine, say)
    if held is None:
        return why or "connected"
    try:
        if heir is not None:
            try:
                carried = imports.carry(imports.of_version(name), heir, told=say)
            except OSError as error:
                say(f"text-to-cad {name} is kept for now: {error.strerror or error}")
                return "carry"
            if not carried.complete:
                say(f"text-to-cad {name} is kept for now: what it holds could not all be carried into {heir}")
                return "carry"
        _hand_on(name, acting)
        aside = places.versions_dir() / f"{TRASH}{name}-{os.getpid()}-{os.urandom(4).hex()}"
        try:
            os.rename(folder, aside)
        except OSError as error:
            say(f"text-to-cad {name} is kept for now: {error.strerror or error}")
            return "refused"
    finally:
        _drop(held, engine)
    shutil.rmtree(engine, ignore_errors=True)
    shutil.rmtree(aside, ignore_errors=True)
    _forget_records(folder)
    _forward(name, heir)
    say(f"removed text-to-cad {name}, which nothing uses now" + (f" (its data carried into {heir})" if heir else
                                                                 " with its data" if whole else ""))
    return "removed"


def runs_from(folder: Path) -> bool:
    """Whether this process runs from ``folder``: its interpreter or its environment (``sys.prefix``) inside it, each
    resolved. Where this process is, never what the system lists: ``cad uninstall`` typed in a terminal runs from the
    version it removes, which Windows will not let it remove while it runs, however long it waits."""
    inside = os.path.normcase(os.path.realpath(folder)).rstrip(os.sep) + os.sep
    return any((os.path.normcase(os.path.realpath(path)).rstrip(os.sep) + os.sep).startswith(inside)
               for path in (sys.executable, sys.prefix) if path)


@dataclass(frozen=True)
class Refusal:
    """Why a removal was refused (``refused``), in a person's words, the system's own among them; ``here``: the
    system refused it because this process runs from the folder (``runs_from``), which no wait changes."""

    words: str
    here: bool = False


def _aside(source: Path, aside: Path, folder: Path, wait: float | None) -> OSError | None:
    """``source`` renamed to ``aside``: None, or the system's refusal. With ``wait`` (seconds: an uninstall's, a person
    waiting on it), a refusal is tried again until that long has passed -- on Windows a stopped server's process keeps
    its files for a moment after it has let its lock go -- unless this process runs from ``folder`` (``runs_from``),
    which no wait changes. Without one, once: a sweep tries again at its next pass."""
    deadline = time.monotonic() + (wait or 0.0)
    while True:
        try:
            os.rename(source, aside)
            return None
        except OSError as error:
            if wait is None or time.monotonic() >= deadline or runs_from(folder):
                return error
        time.sleep(0.05)


def _refused(error: OSError, folder: Path) -> Refusal:
    """The system's refusal of a removal, said as it is: its words, and that this process runs from ``folder`` where it
    does."""
    here = runs_from(folder)
    return Refusal(f"the system refused to remove it ({error.strerror or error})"
                   + (": this command runs from it" if here else ""), here)


def _strip(name: str, say: Callable[[str], None], *, wait: float | None = None,
           why: list[Refusal] | None = None) -> str:
    """The code of version ``name`` removed, its data kept: what ``cad uninstall`` does to the default channel's
    version (``remove_code``), and what a sweep finishes where the system refused it then (``_code_left``). Its server's
    lock taken first (its server stopped by the caller; one that still runs keeps it), no other process running from
    it but this one (``cad uninstall`` typed in a terminal runs from the version it uninstalls), ``code/`` renamed
    aside (``_aside``: ``wait``, an uninstall's) and removed. ``removed``, ``absent``, ``connected``, ``in use`` or
    ``refused``: why, a ``Refusal`` appended to ``why`` where it is given (an uninstall says it in its own line), else
    said, as a sweep's (on Windows, a file in use: the next sweep removes it)."""
    from cad_server._internal import releases

    folder = places.version_dir(name)
    code = places.code_dir(name)
    if not os.path.lexists(code):
        return "absent"
    engine = places.engine_dir(name)
    try:
        held = _take(engine)
    except OSError as error:
        refusal = Refusal(f"its server's lock could not be taken ({error.strerror or error})")
        if why is not None:
            why.append(refusal)
        else:
            say(f"text-to-cad {name}'s code stays: {refusal.words}")
        return "refused"
    if held is None:
        return "connected"
    try:
        if releases.running(folder, besides=os.getpid()):
            say(f"text-to-cad {name}'s code stays for now: a process still runs from {folder}")
            return "in use"
        aside = places.versions_dir() / f"{TRASH}{name}-code-{os.getpid()}-{os.urandom(4).hex()}"
        error = _aside(code, aside, folder, wait)
        if error is not None:
            if why is not None:
                why.append(_refused(error, folder))
            else:
                say(f"text-to-cad {name}'s code stays until the next sweep: {error.strerror or error}")
            return "refused"
    finally:
        _drop(held, engine)
    shutil.rmtree(engine, ignore_errors=True)
    shutil.rmtree(aside, ignore_errors=True)
    _forget_records(folder)
    places._versioned.cache_clear()
    return "removed"


def remove_code(name: str, *, told: Callable[[str], None] | None = None, wait: float | None = None,
                why: list[Refusal] | None = None) -> str:
    """``cad uninstall`` without ``--purge``: version ``name``, the default channel's, taken out but its data -- its
    settings, Recents, documents' records, page token and port -- kept for a later install (``UNINSTALLED``, written
    first: the default channel's next first use leaves it, ``move``), under the install lock: its code removed
    (``_strip``; ``wait`` and ``why`` as there). ``removed``, ``absent``, ``connected``, ``in use`` or ``refused`` (on
    Windows the uninstall may run from it: its code goes at the next sweep, a later install's, or when the person
    deletes it)."""
    from cad_server._internal.pointers import _land

    say = told or (lambda _line: None)
    with install_lock():
        folder = places.version_dir(name)
        if not os.path.lexists(folder):
            return "absent"
        _land(folder / UNINSTALLED, b"")
        done = _strip(name, say, wait=wait, why=why)
        if done == "removed":
            say(f"removed text-to-cad {name}'s code; its data stays for a later install")
        return done


def remove_now(name: str, *, told: Callable[[str], None] | None = None, wait: float | None = None,
               why: list[Refusal] | None = None) -> str:
    """Version ``name``'s folder removed whole, its data with it, at a person's word (``cad uninstall --purge``),
    whatever names it: under the install lock, its server's lock taken (its server stopped by the caller first; one
    that still runs keeps it: ``connected``), no other process running from it (``in use``; this process may: ``cad
    uninstall`` typed in a terminal runs from the version it removes, and nothing is imported from it after), the
    folder renamed aside (``_aside``: ``wait`` as there) and removed, and the records naming it forgotten. ``removed``,
    ``absent``, ``connected``, ``in use`` or ``refused`` (the lock could not be taken, or the system refused the rename:
    on Windows, a file in use; a ``Refusal`` appended to ``why`` where it is given, else said)."""
    from cad_server._internal import releases

    say = told or (lambda _line: None)
    with install_lock():
        folder = places.version_dir(name)
        if not os.path.lexists(folder):
            return "absent"
        engine = places.engine_dir(name)
        try:
            held = _take(engine)
        except OSError as error:
            refusal = Refusal(f"its server's lock could not be taken ({error.strerror or error})")
            if why is not None:
                why.append(refusal)
            else:
                say(f"text-to-cad {name} is kept: {refusal.words}")
            return "refused"
        if held is None:
            return "connected"
        try:
            if releases.running(folder, besides=os.getpid()):
                say(f"text-to-cad {name} is kept: a process still runs from {folder}")
                return "in use"
            aside = places.versions_dir() / f"{TRASH}{name}-{os.getpid()}-{os.urandom(4).hex()}"
            error = _aside(folder, aside, folder, wait)
            if error is not None:
                if why is not None:
                    why.append(_refused(error, folder))
                else:
                    say(f"text-to-cad {name} could not be removed: {error.strerror or error}")
                return "refused"
        finally:
            _drop(held, engine)
        shutil.rmtree(engine, ignore_errors=True)
        shutil.rmtree(aside, ignore_errors=True)
        _forget_records(folder)
        say(f"removed text-to-cad {name}")
        return "removed"


def _forget_records(folder: Path) -> None:
    """The installation records (``installations/``, the mirror for clients of 0.11.10 and earlier) naming an
    environment in ``folder``, a version's gone, removed."""
    from cad_server._internal import installations

    inside = os.path.normcase(os.path.abspath(folder)).rstrip(os.sep) + os.sep
    for record in installations.records():
        if os.path.normcase(os.path.abspath(record["prefix"])).startswith(inside):
            installations.forget(record["version"])


def sweep(*, told: Callable[[str], None] | None = None, spare: str | None = None,
          unused: bool = False, acting: str | None = None) -> dict[str, str]:
    """Every version no pointer names that has been a pointer's removed where this process is its heir and nothing
    is connected to it, its data carried into that heir first (``fate``, ``_remove``); the code ``cad uninstall`` could
    not remove (``_code_left``); and what an earlier removal left (``versions/.trash-*``, the engine folders of versions
    gone): what was done with each version removal was tried on, and each version kept for want of a successor, left
    for its heir, or kept by ``cad uninstall``. Every move calls it, each running server as it tends itself (``spare``:
    its own version, whose folder a process never removes while it runs from it) and ``cad doctor --prune``
    (``unused``: the versions never a pointer's, and incomplete folders, go too). Every version a pointer names is
    marked so (``NAMED``) where an older move did not. ``acting``: the version this sweep acts as (``_acts_for``), a
    move's. A pointer that cannot be read removes nothing this pass, said."""
    from cad_server._internal import legacy, pointers

    say = told or (lambda _line: None)
    done: dict[str, str] = {}
    with install_lock():
        try:
            kept = _kept() | ({spare} if spare else set())
            named = pointers.named()
            default = pointers.read(None)
        except pointers.Unreadable as unreadable:
            say(f"nothing is removed this time: {unreadable}")
            return done
        for name in named:
            with contextlib.suppress(OSError):
                _name(name)
        if default is not None and _acts_for(default, acting) and legacy.removable():
            legacy.remove(default, say)  # the default channel has left it: gone once that is safe
        for name in folders():
            if name not in kept and _code_left(name):
                _strip(name, say)
            why = fate(name, kept, unused=unused, acting=acting)
            if why is None:
                done[name] = _remove(name, say, acting=acting)
            elif why in ("successor", "heir", "uninstalled"):
                done[name] = why
        root = places.versions_dir()
        for entry in _names(root):
            if entry.startswith(TRASH):
                shutil.rmtree(root / entry, ignore_errors=True)
        engines = places.engines_dir()
        for entry in _names(engines):
            if (places.VERSION.fullmatch(entry) and entry != spare and not os.path.lexists(root / entry)
                    and (engines / entry).is_dir()):
                try:
                    held = _take(engines / entry)
                except OSError:
                    continue
                if held is not None:
                    _drop(held, engines / entry)
                    shutil.rmtree(engines / entry, ignore_errors=True)
    return done


def mend(*, told: Callable[[str], None] | None = None) -> list[str]:
    """``cad doctor``'s repair of the pointers (not ``--check``): each that names no version (``pointers.Unreadable``,
    ``corrupt``: emptied by a crash, or a form this release does not know) written again, under the install lock,
    naming the newest version present that a pointer has named (``_newest_named``) -- never an older one, so no old
    chat's pin moves its channel back. One that cannot be read now is said, never written. What was said."""
    from cad_server._internal import pointers

    said: list[str] = []

    def say(line: str) -> None:
        said.append(line)
        if told is not None:
            told(line)

    with install_lock():
        channels: list[str | None] = [None]
        try:
            channels += [entry for entry in pointers._entries(pointers._folder().path(pointers.CHANNELS))
                         if pointers._channel_file(entry)]
        except pointers.Unreadable:
            pass
        for channel in channels:
            try:
                pointers.read(channel)
                continue
            except pointers.Unreadable as unreadable:
                if not unreadable.corrupt:
                    continue
                newest, target = _newest_named(), _newest_named(present_only=True)
                if target is None or (newest is not None and older(target, newest)):
                    say(f"{unreadable}: no installed version can be named in its place; the install command writes "
                        "it again")
                    continue
                try:
                    pointers.write(channel, target)
                except OSError as error:
                    say(f"{unreadable}: it could not be written again ({error.strerror or error})")
                    continue
                say(f"{unreadable}: it names text-to-cad {target} now, the newest version a channel has been on")
    return said


# --- cad doctor --prune -----------------------------------------------------------------------------------


@dataclass
class Prune:
    """What ``cad doctor --prune`` removes, read before it asks and done exactly (``prune``): the named channels
    unused for ``pointers.FORGOTTEN_DAYS`` it forgets (``channels``); each version folder it removes and why, in words
    (``versions``: no channel on it and its data carried into its successor; installed and never a pointer's; an
    incomplete install; a forgotten channel's that no version can take the data of, removed whole with its settings
    and Recents, ``whole``); the code ``cad uninstall`` could not remove (``code``); each version no channel is on that
    it keeps, and why (``kept``); and whether the layout of 0.11.10 and earlier goes (``legacy``)."""

    channels: list[Any] = field(default_factory=list)
    versions: dict[str, str] = field(default_factory=dict)
    kept: dict[str, str] = field(default_factory=dict)
    whole: set[str] = field(default_factory=set)
    code: list[str] = field(default_factory=list)
    legacy: bool = False

    def __bool__(self) -> bool:
        return bool(self.channels or self.versions or self.code or self.legacy)


def prune_plan(now: float | None = None) -> Prune:
    """``cad doctor --prune``'s plan, read and nothing changed (see ``Prune``). A version a forgotten channel was on goes
    to the default channel's version where that can take its data (``_heir``), else to its successor where it has one;
    with neither it goes whole. Only a process of a version's heir carries and removes it: one whose heir is another
    version is kept, said. ``pointers.Unreadable`` when a pointer cannot be read: then nothing is pruned."""
    from cad_server._internal import legacy, pointers

    plan = Prune(channels=pointers.unused(now))
    forgotten = {pointer.channel for pointer in plan.channels}
    left = {pointer.version for pointer in plan.channels}
    kept = {pointer.version for pointer in pointers.listing() if pointer.channel not in forgotten}
    kept |= _kept() - pointers.named()
    default = pointers.read(None)
    for name in folders():
        if name in kept:
            continue
        if _code_left(name):
            plan.code.append(name)
        if not used(name) and name not in left:
            plan.versions[name] = ("installed and never a channel's" if places.version_record(name) is not None
                                   else "its install is incomplete")
            continue
        heir = successor(name)[0]
        if name in left and default not in (None, name) and _heir(default, name):
            heir = default
        if heir is not None:
            if _acts_for(heir):
                plan.versions[name] = f"no channel is on it: its data goes into text-to-cad {heir} first"
            else:
                plan.kept[name] = (f"its data goes into text-to-cad {heir}, whose own server or next move carries it "
                                   "in and removes it")
        elif name in left:
            plan.versions[name] = ("its channel is forgotten and no version can take its data: removed whole, its "
                                   "settings and Recents with it")
            plan.whole.add(name)
        elif os.path.lexists(places.version_dir(name) / UNINSTALLED):
            plan.kept[name] = ("cad uninstall kept its data for a later install, which takes it; cad uninstall --purge "
                               "removes it")
        else:
            plan.kept[name] = f"its data is kept: {successor(name)[1]}"
    plan.legacy = (default is not None and _acts_for(default) and legacy.removable()
                   and legacy.unsafe(default) is None)
    return plan


def _heir(heir: str, name: str) -> bool:
    """Whether version ``heir`` can take version ``name``'s data: there, with its data, and not older."""
    from cad_server._internal import imports

    return os.path.isdir(places.version_dir(heir)) and imports.imported(heir) and not older(heir, name)


def prune(plan: Prune, *, told: Callable[[str], None] | None = None) -> dict[str, str]:
    """``plan`` done, and nothing else, under the install lock: its channels forgotten (each one's version marked a
    pointer's, and told its data goes to the default channel's version where that can take it and no other channel is
    on it), the layout of 0.11.10 and earlier removed where planned (``legacy.remove``), the code ``cad uninstall`` left
    removed, and each version planned removed (``_remove``: one with work in flight, or a process running from it,
    stays; one planned ``whole``, with its data). What was done with each version, by name."""
    from cad_server._internal import legacy, pointers

    say = told or (lambda _line: None)
    done: dict[str, str] = {}
    with install_lock():
        default = pointers.read(None)
        for pointer in plan.channels:
            try:
                _name(pointer.version)
            except OSError:
                pass
            pointers.forget(pointer.channel)
            say(f"forgot the {pointer.channel} channel (text-to-cad {pointer.version}), unused since "
                f"{time.strftime('%Y-%m-%d', time.localtime(pointers.last_used(pointer) or 0))}")
            if (default not in (None, pointer.version) and pointer.version not in pointers.named()
                    and _heir(default, pointer.version)):
                try:
                    _succeed(pointer.version, default)
                except OSError as error:
                    say(f"text-to-cad {pointer.version} could not be told where its data goes "
                        f"({error.strerror or error})")
        if plan.legacy and default is not None:
            legacy.remove(default, say)
        kept = _kept()
        for name in plan.code:
            if name not in kept and _code_left(name):
                _strip(name, say)
        for name in plan.versions:
            if not os.path.lexists(places.version_dir(name)):
                continue
            if name in plan.whole:
                done[name] = "named" if name in kept else _remove(name, say, whole=True)
                continue
            why = fate(name, kept, unused=True)
            done[name] = _remove(name, say) if why is None else why
        root = places.versions_dir()
        for entry in _names(root):
            if entry.startswith(TRASH):
                shutil.rmtree(root / entry, ignore_errors=True)
    return done


def _names(folder: Path) -> list[str]:
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


# --- cad setup --add ------------------------------------------------------------------------------------


def add_command(version: str, system: str | None = None) -> str:
    """The install command that makes ``version`` present and changes nothing else, for this computer (or
    ``system``, an ``os.name``): the line to run outside an agent's sandbox."""
    from cad_server.updates import INSTALL

    if (system or os.name) == "nt":
        return f"& ([scriptblock]::Create((irm https://www.texttocad.dev/install.ps1))) --add {version}"
    return f"{INSTALL} -s -- --add {version}"


def add(*, quiet: bool = False, out: Any = None, err: Any = None) -> int:
    """``cad setup --add [--quiet]``: this process's own version made present (``make_present``), and the ``cad``
    command written where it is missing or of an older revision (``installations.write_proxy``: a later one, or a
    file of that name not text-to-cad's, is left alone), and nothing else -- no pointer, no app, no setting, no
    receipt --, said in one or two lines on ``out`` (each line of the making on ``err`` unless ``quiet``). A
    failure is one line on ``err``: with ``quiet`` (the ``cad`` command's own run of it) its reason alone, which
    that command says in its own line. Exit 0 present; ``cli_errors.REASONS['cannot_install_here']`` when it
    cannot be installed from this shell; 1 when it failed, or the ``cad`` command could not be written."""
    import cad_server
    from cad_server._internal import installations
    from cad_server._internal.cli_errors import FAILED, REASONS

    out, err = out or sys.stdout, err or sys.stderr
    name = os.environ.get(places.INSTALLATION_ENV) or cad_server.__version__
    if not os.environ.get(places.INSTALLATION_ENV) and installations.editable():
        err.write(f"cad setup --add: this cad-server is a source tree, added only as a version it is named "
                  f"({places.INSTALLATION_ENV})\n")
        return FAILED
    found = make_present(name, told=(lambda _line: None) if quiet else (lambda line: err.write(f"cad: {line}\n")))
    if not found.ok:
        if quiet:
            err.write(f"{found.error}\n")
        elif found.cannot is not None:
            from cad_server._internal import pins

            err.write(f"cad: {pins.not_installed(name, found.error or found.cannot)}\n")
        else:
            err.write(f"text-to-cad {name} could not be installed: {found.error}\n")
        return REASONS["cannot_install_here"] if found.cannot is not None else FAILED
    path, status, error = installations.write_proxy()
    if error is not None or status == installations.FOREIGN:
        why = error or "a file of that name there is not text-to-cad's, and is left alone"
        err.write(f"text-to-cad {name} is installed, but the cad command could not be written at {path}: {why}\n")
        return FAILED
    if not quiet:
        out.write(f"text-to-cad {name} is {'installed now' if found.made else 'installed'}: "
                  f"{places.version_dir(name)}\n")
    return 0
