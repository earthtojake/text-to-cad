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
its first start (``first_start``: its data imported, ``cad_server._internal.imports``, and the proof it runs),
then the pointer written -- the one write that is the update --, then every version no pointer names and nothing
is connected to removed (``sweep``). A failure before the pointer is written changes no pointer and no other
version. The default channel's first move on a device with the layout of 0.11.10 and earlier imports from that layout,
and
the sweep removes the layout's code, records and caches as soon as that is safe (``cad_server._internal.legacy``).
Whether the automatic updates are on plays no part: a newer version asked for is moved to.

**Removal** (``remove``, ``sweep``). Garbage is a version no pointer names (nor the default channel's version as
``pointers.default`` resolves it, where it has no pointer). One is removed under the install lock: its server's
lock taken (the one its server takes to start, in ``<engines>/<version>``), so none starts meanwhile; a server
that runs is asked whether anything is connected to it (``connected``: a running server that cannot say counts
as connected, and stays) and stopped when nothing is (``stop_server``); a folder a process still runs from
stays; the folder renamed aside (``versions/.trash-*``), which a refusal (Windows: a file in use) turns into a
skip, then removed. ``sweep`` does that for every such version, removes the layout of 0.11.10 and earlier once the
default channel has left it and that is safe (``legacy.remove``), and clears what an earlier removal left: every
move, the stop of a server that goes idle unnamed and ``cad doctor --prune`` call it.
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

__all__ = ["CANNOT", "LOCK", "Moved", "Present", "add", "add_command", "connected", "first_start", "folders",
           "install_lock", "make_present", "move", "older", "order", "present", "proof", "remove", "serves", "stop_server", "sweep"]

# The device's install lock, in the state folder: every install, move and removal holds it (``cad setup``'s too).
LOCK = "install.lock"
SERVER = "server"
TRASH = ".trash-"
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


def _probe(name: str) -> dict[str, Any]:
    """Version ``name``'s server environment asked, in a process of its Python (``PROBE``), nothing written
    there: its version, release, installation and kernel environment's folder as it works them out. ``Refused``
    when it does not run, or says it is another version."""
    server = places.code_dir(name) / SERVER
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
    environment[places.INSTALLATION_ENV] = name
    said = ""
    try:
        done = subprocess.run([str(base.interpreter(server)), "-B", "-I", "-c", PROBE], env=environment,
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


def proof(name: str) -> dict[str, Any]:
    """That present version ``name`` runs (``_probe``): what its own Python says of it. ``Refused`` when not."""
    return _probe(name)


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
    (``imports.ensure``, from what its channel is ``leaving``), then the proof it runs (``proof``). What the import
    did (``imports.Imported``); ``Refused`` when the version does not run."""
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


def move(channel: str | None, new: str, *, told: Callable[[str], None] | None = None) -> Moved:
    """Channel ``channel`` (None: the default) moved to version ``new`` (see the module): what was done
    (``Moved``). ``ValueError`` for a name that is no channel or no version."""
    from cad_server._internal import legacy, pointers

    said: list[str] = []

    def say(line: str) -> None:
        said.append(line)
        if told is not None:
            told(line)

    channel = None if channel is None else pointers.channel_name(channel)  # ``default`` is the default
    places.version_dir(new)
    with install_lock(waiting=lambda: say("waiting for another install of text-to-cad to finish")):
        first_default = channel is None and pointers.read(None) is None
        old = (pointers.leaving().version if channel is None else pointers.read(channel))
        legacy_left = first_default and legacy.present()
        if old == new and not first_default:
            return Moved("same", channel, new, old, said=said)
        if old is not None and older(new, old):
            return Moved("stale", channel, new, old, said=said)
        made = make_present(new, told=say)
        if not made.ok:
            return Moved("cannot" if made.cannot else "failed", channel, new, old, made.error, made, said=said)
        try:
            imported = first_start(new, None if legacy_left else old, legacy_left=legacy_left, told=say)
        except base.Refused as refused:
            return Moved("failed", channel, new, old, str(refused), made, said=said)
        try:
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
        removed = sweep(told=say)
        return Moved("moved", channel, new, old, None, made, imported, removed, said)


# --- removing one -----------------------------------------------------------------------------------------


def serves(name: str) -> bool:
    """Whether version ``name``'s server runs: its lock in ``<engines>/<name>`` is held. Read, nothing changed."""
    engine = places.engine_dir(name)
    try:
        held = _take(engine)
    except OSError:
        return False
    if held is None:
        return True
    _drop(held, engine)
    return False


def connected(name: str) -> bool:
    """Whether anything is connected to the running server of version ``name``: asked of the server where it can
    answer; until then, and for a server that cannot say, True -- a server that runs keeps its version."""
    return True


def stop_server(name: str) -> bool:
    """Version ``name``'s server stopped, nothing being connected to it (``connected``): whether it stopped and
    let its lock go. A server that cannot be asked is not stopped: False."""
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
    """The versions no removal takes: those a pointer names, and the default channel's as it resolves with no
    pointer (``pointers.default``: the one a command with no pin runs)."""
    from cad_server._internal import pointers

    found = pointers.named(state)
    default = pointers.default(state).version
    return found | ({default} if default else set())


def remove(name: str, *, told: Callable[[str], None] | None = None) -> str:
    """Version ``name`` removed when no pointer names it (see the module): ``removed``, or why not -- ``named``,
    ``connected`` (its server runs and something is connected, or it cannot say), ``in use`` (a process runs from
    its folder), ``refused`` (the system refused the rename or the lock) -- or ``absent``."""
    say = told or (lambda _line: None)
    with install_lock():
        if name in _kept():
            return "named"
        return _remove(name, say)


def _remove(name: str, say: Callable[[str], None]) -> str:
    from cad_server._internal import releases

    folder = places.version_dir(name)
    if not os.path.lexists(folder):
        return "absent"
    engine = places.engine_dir(name)
    try:
        held = _take(engine)
        if held is None and not connected(name) and stop_server(name):
            held = _take(engine)
    except OSError as error:
        say(f"text-to-cad {name} is kept: its server's lock cannot be taken ({error.strerror or error})")
        return "refused"
    if held is None:
        return "connected"
    try:
        if releases.running(folder):
            return "in use"
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
    say(f"removed text-to-cad {name}, which nothing uses now")
    return "removed"


def _forget_records(folder: Path) -> None:
    """The installation records (``installations/``, the mirror for clients of 0.11.10 and earlier) naming an
    environment in
    ``folder``, a version's gone, removed."""
    from cad_server._internal import installations

    inside = os.path.normcase(os.path.abspath(folder)).rstrip(os.sep) + os.sep
    for record in installations.records():
        if os.path.normcase(os.path.abspath(record["prefix"])).startswith(inside):
            installations.forget(record["version"])


def sweep(*, told: Callable[[str], None] | None = None) -> dict[str, str]:
    """Every version no pointer names removed where nothing is connected to it (``remove``), and what an earlier
    removal left (``versions/.trash-*``, the engine folders of versions gone): what was done with each version
    removal was tried on. The stop of a server that goes idle unnamed, every move and ``cad doctor --prune`` call
    it."""
    from cad_server._internal import legacy, pointers

    say = told or (lambda _line: None)
    done: dict[str, str] = {}
    with install_lock():
        default = pointers.read(None)
        if default is not None and legacy.removable():
            legacy.remove(default, say)  # the default channel has left it: gone once that is safe
        kept = _kept()
        for name in folders():
            if name not in kept:
                done[name] = _remove(name, say)
        root = places.versions_dir()
        for entry in _names(root):
            if entry.startswith(TRASH):
                shutil.rmtree(root / entry, ignore_errors=True)
        engines = places.engines_dir()
        for entry in _names(engines):
            if places.VERSION.fullmatch(entry) and not os.path.lexists(root / entry) and (engines / entry).is_dir():
                try:
                    held = _take(engines / entry)
                except OSError:
                    continue
                if held is not None:
                    _drop(held, engines / entry)
                    shutil.rmtree(engines / entry, ignore_errors=True)
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
