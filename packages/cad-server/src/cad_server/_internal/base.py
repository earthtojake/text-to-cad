"""The base: the one environment models and the engine's kernel processes run in.

The ``cadgen`` wheel's required dependencies are the core -- the engine's server, the ``cadgen``
command, the CAD Viewer's server, the MCP shim --, and the CAD kernel (OCP, build123d and the rest) is
its ``build123d`` extra. So an installation of the core, as uvx makes the plugin's server, runs no model
itself: the engine makes one environment per installation, the base, and every process that loads
the kernel starts from it -- the script ``cad run`` runs, its worker, and the engine's own kernel
processes (the standby, the documents worker, the meshing and reading pools, the render processes:
``kernel``, which the engine is handed as ``cad.engine.places.KERNEL``).

- **What it is**: ``cad[build123d]`` at the installation's own release -- or the source tree, or the
  wheel, the installation was made from (``Installation.requirement``) -- on the installation's own
  Python (the line ``cad_server._internal.launch.PYTHON`` names, for one uvx made), so the engine and the
  base are one Python. uv makes it at ``base/<key>`` in the cache folder, its files hard links into
  uv's cache (``LINK``). An installation whose own environment carries the kernel (installed with the
  extra: ``pip install 'cad[build123d]==<release>'``, a checkout's development environment) is its own base, and
  none is made.
- **The key** digests the installation (its environment, the version it runs as, its release and
  where its cadgen installs from), its Python and the architecture: an upgrade makes a base of its
  own, from uv's cache, and nothing is made twice.
- **The marker**, ``cad-env.json``, written last, makes it complete: a later use reads the marker
  and resolves nothing. It names the installation the base belongs to (``home``), so a process
  running there reaches that installation's engine and starts it with that installation's Python, and
  it records the base's own import path, which the engine's spawned kernel processes start with.
- **One maker**: a lock beside it, so a process that finds another making it waits for it.
- **The network** waits on nothing it need not: uv is asked ``--offline`` first, from its cache, and
  online only for what the cache does not hold, said in a line before it starts.
- **The engine makes it** when it starts and finds none (``Making``, in the background): an engine a
  host's CAD app starts runs outside any sandbox, so an agent's sandboxed first ``cad run``, which cannot
  write the cache folder, asks it over its door (``ensure``'s ``engine``) and follows its making; with no
  engine to ask, the command makes it itself.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cad.engine import places

__all__ = ["BASE", "EXTRA", "FIND_LINKS_ENV", "MAKING", "Environment", "Installation", "MARKER", "Making", "Recipe",
           "Refused", "SCHEMA", "complete", "ensure", "failure", "find_uv", "halt", "interpreter", "kernel", "make", "where"]

# The bases' folder in the cache folder, and the marker that makes one complete, written last: the one a
# process in the base reads its installation from (``places.home``).
BASE = "base"
MARKER = places.MARKER
SCHEMA = places.MARKER_SCHEMA
# The library, which the base installs with its kernel (its extra, ``EXTRA``), and the server, which a release
# folder holds.
LIBRARY = "cad"
EXTRA = "build123d"
SERVER = "cad-server"
# The modules whose presence makes an environment carry the CAD kernel.
KERNEL_MODULES = ("OCP", "build123d")
# How the base's installed files are made from uv's cache: hard links, as uv makes them on Linux and
# Windows anyway. On macOS uv clones them, new files each, and the system looks at each native library
# a process first loads once per file: a new environment's first kernel load measured 44 s with clones,
# against 32 s for the first environment of hard links and 7.6 s for each one after it (one-box model's
# imports, OCP 8.0, Apple silicon). Nothing writes into an environment's installed files.
LINK = "hardlink"
# The waits between the tries at removing an environment on Windows, where a scanner reading a file just
# written refuses its removal for a moment (``_remove``): the test suite's cleanup ladder's first six.
REMOVE_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)
# What uv says when it cannot reach an index or a download: the network, not the installation.
NETWORK = re.compile(r"error sending request|network was disabled|dns error|tcp connect error|failed to lookup address"
                     r"|Connection refused|Network is unreachable|timed out|Could not connect", re.I)
# What uv says when the system refuses it a file it writes (its cache, the environment): a sandbox's.
DENIED = re.compile(r"Operation not permitted|Permission denied|Access is denied|os error (?:1|13)\)")
WHAT = "the CAD kernel environment"
# A folder of wheels uv reads beside its index for every cadgen it installs (``--find-links``): a test's
# seam, a local release a test publishes there, never a setting of a person's.
FIND_LINKS_ENV = "CAD_UPDATE_FIND_LINKS"


class Refused(Exception):
    """Why the base cannot be made: one line."""


# --- the installation ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Installation:
    """The installation whose engine the base serves: what it installs and belongs to."""

    release: str  # the library's release, as its metadata says it (the server's own: one release)
    name: str  # the version it runs as (``cad.engine.places.installation``)
    python: str  # its Python's version, ``3.14.0``
    executable: str  # its Python, as its environment names it (never resolved: that reaches the base interpreter)
    prefix: str  # its environment
    root: str  # the folder its server (``cad_server``) is imported from
    source: str | None  # the library's source tree, or the wheel it was installed from (a URL); None: its release
    # on the index
    arch: str
    kernel: bool  # whether its own environment carries the kernel: then it is its own base

    @classmethod
    def here(cls) -> "Installation":
        """This process's installation: the one the environment it runs in belongs to (``places.home``),
        else its own environment's."""
        found = places.home()
        if found is not None:
            try:
                return cls(**{name.name: found[name.name] for name in dataclasses.fields(cls)})
            except (KeyError, TypeError):
                pass
        return _own()

    def requirement(self) -> list[str]:
        """What installs this installation's library with its kernel: the library's source tree editable,
        the wheel it was installed from, or its release."""
        if self.source is None:
            return [f"{LIBRARY}[{EXTRA}]=={self.release}"]
        if os.path.isdir(self.source):
            return ["-e", f"{self.source}[{EXTRA}]"]
        return [f"{LIBRARY}[{EXTRA}] @ {self.source}"]


@functools.cache
def _own() -> Installation:
    """This environment's installation, read once a process."""
    import cad
    import cad_server
    from cad.engine.previous import version

    package = Path(cad_server.__file__).resolve().parent
    prefix = os.path.abspath(sys.prefix)
    return Installation(release=version(), name=places.installation(), python=platform.python_version(),
                        executable=os.path.abspath(sys.executable), prefix=prefix, root=str(package.parent),
                        source=_source(Path(cad.__file__).resolve().parent, prefix, LIBRARY), arch=_machine(),
                        kernel=_carries_kernel())


def server_source() -> str | None:
    """Where this installation's server installs from again (``releases.make``): its source tree, the wheel
    it was installed from, or None, its release on the index (``_source``)."""
    import cad_server

    return _source(Path(cad_server.__file__).resolve().parent, os.path.abspath(sys.prefix), SERVER)


def _machine() -> str:
    """The machine's architecture, as ``platform.machine()`` says it -- on Windows read where that reads
    it, the environment the system sets, since ``platform.machine()`` may first run ``cmd /c ver``: a
    console window, from an engine that has none."""
    if os.name == "nt":
        return os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE") or ""
    return platform.machine()


def _carries_kernel() -> bool:
    """Whether this environment has the kernel installed (its modules found, none of them loaded)."""
    import importlib.util

    try:
        return all(importlib.util.find_spec(name) is not None for name in KERNEL_MODULES)
    except (ImportError, ValueError):
        return False


def _source(package: Path, prefix: str, distribution: str) -> str | None:
    """Where the package at ``package`` (of ``distribution``) installs from: the source tree it is imported
    from when that lies outside its environment (an editable install, or a path on ``PYTHONPATH``), else the
    archive it was installed from (``direct_url.json``, PEP 610: a wheel's file, a URL), else None: its
    release, from the index."""
    here = os.path.normcase(os.path.realpath(package))
    inside = os.path.normcase(os.path.realpath(prefix)).rstrip(os.sep) + os.sep
    if not here.startswith(inside):
        tree = package.parent.parent
        return str(tree) if (tree / "pyproject.toml").is_file() else None
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import distribution as distribution_of

    try:
        recorded = json.loads(distribution_of(distribution).read_text("direct_url.json") or "null")
    except (PackageNotFoundError, OSError, ValueError):
        return None
    if isinstance(recorded, dict) and isinstance(recorded.get("archive_info"), dict) \
            and isinstance(recorded.get("url"), str) and recorded["url"]:
        return recorded["url"]
    return None


# --- the base --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Environment:
    """The base as a process is started in it: its Python, its folder, whether it is the installation's
    own, and the import path its interpreter starts with (None for the installation's own: it is this
    process's)."""

    python: str
    prefix: str
    own: bool
    path: tuple[str, ...] | None = None


def interpreter(env: Path) -> Path:
    """The environment's Python."""
    return env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _inputs(installation: Installation) -> dict[str, Any]:
    """What makes the base, which its key digests and its marker holds."""
    return {"schema": SCHEMA, "installation": installation.name, "release": installation.release,
            "prefix": os.path.normcase(os.path.realpath(installation.prefix)), "source": installation.source,
            "python": installation.python, "arch": installation.arch}


def where(installation: Installation | None = None) -> Path:
    """The folder of the installation's base, made or not: ``base/<key>`` in the cache folder."""
    from cad.engine.places import cache_dir

    found = installation or Installation.here()
    return cache_dir() / BASE / hashlib.sha256(json.dumps(_inputs(found), sort_keys=True).encode("utf-8")).hexdigest()[:16]


def complete(env: Path) -> dict[str, Any] | None:
    """The marker of the base at ``env`` when it is complete -- written last, of its key, and its Python
    there -- else None."""
    try:
        marker = json.loads((env / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (isinstance(marker, dict) and marker.get("schema") == SCHEMA and marker.get("key") == env.name
            and interpreter(env).exists()):
        return marker
    return None


def _found(env: Path, marker: dict[str, Any]) -> Environment:
    path = marker.get("path")
    return Environment(str(interpreter(env)), str(env), False,
                       tuple(path) if isinstance(path, list) and all(isinstance(item, str) for item in path) else None)


def ensure(installation: Installation | None = None, *, make: bool = True,
           told: Callable[[str], None] | None = None, engine: bool = False) -> Environment | None:
    """The installation's base (see the module): the installation's own environment when it carries the
    kernel; else ``base/<key>`` in the cache folder, made first when it is not complete and ``make``
    (None when it is not, and ``make`` is false), each line of the making said to ``told`` -- with
    ``engine`` (``cad run``), made by the device's engine when one runs (``_by_the_engine``), else here.
    ``Refused`` in one line when it cannot be made."""
    installation = installation or Installation.here()
    if installation.kernel:
        return Environment(installation.executable, installation.prefix, True)
    env = where(installation)
    marker = complete(env)
    if marker is not None:
        return _found(env, marker)
    if not make:
        return None
    if engine:
        marker = _by_the_engine(env, told or _say)
        if marker is not None:
            return _found(env, marker)
    return _found(env, _make(env, installation, told or _say))


def _by_the_engine(env: Path, told: Callable[[str], None]) -> dict[str, Any] | None:
    """The base at ``env`` made by the device's engine, when one runs and it is this installation's
    (``{"op": "base"}``, ``Making``): its making followed, each line said to ``told``, and the base's
    marker once made. None when no engine answers, or one makes no base of this installation's (another
    installation's, a release before this one): the caller makes the base itself. ``Refused`` in the
    engine's words when it could not make it."""
    from cad.engine import client

    try:
        answer = client.request({"op": "base", "key": env.name}, start=False,
                                on_log=lambda frame: told(str(frame.get("log", ""))))
    except (ConnectionError, OSError, ValueError):
        return None
    if not answer or answer.get("base") is not True:
        return None
    if answer.get("failed"):
        raise Refused(str(answer["failed"]))
    return complete(env)


def kernel(make: bool = True) -> dict[str, Any] | None:
    """The environment the engine's kernel processes run in, as the engine is handed it
    (``cad.engine.places.KERNEL``): the base's Python, its import path and whether it is this
    installation's own; None when it is not made and ``make`` is false. ``Refused`` when it cannot be."""
    found = ensure(make=make, told=lambda _line: None)
    if found is None:
        return None
    return {"python": found.python, "path": None if found.path is None else list(found.path), "own": found.own}


class Making:
    """The installation's base made in this process's background: the engine's, at its start when the base
    is absent (``start``), and again for whoever needs it later (``follow``: a client's ``cad run`` over the
    engine's door). One making at a time, under the base's own lock as every maker's (a lease that needs the
    kernel meanwhile waits on it); its lines go to the engine's log and are kept for whoever follows it and for
    ``status``; ``made`` is told when it is made (the engine stands its standby). Nothing remembers a
    failure: the next start or follower makes it again."""

    def __init__(self) -> None:
        self.changed = threading.Condition()
        self.state: str | None = None  # None: nothing made here; "making", "made" or "failed"
        self.lines: list[str] = []
        self.error: str | None = None
        self.since: float | None = None
        self.made: Callable[[], None] | None = None

    def key(self) -> str | None:
        """The name of this installation's base folder (``where``), which a client names the base it
        needs by; None for an installation that carries the kernel."""
        installation = Installation.here()
        return None if installation.kernel else where(installation).name

    def start(self) -> bool:
        """The base made on a thread of its own when it is absent and none is being made here: whether it
        is being made now."""
        with self.changed:
            if self.state == "making":
                return True
            installation = Installation.here()
            if installation.kernel or complete(where(installation)) is not None:
                return False
            self.state, self.lines, self.error, self.since = "making", [], None, time.time()
        threading.Thread(target=self._make, name="cad-base", daemon=True).start()
        return True

    def _said(self, line: str) -> None:
        print(f"cad: {line}", file=sys.stderr, flush=True)  # the engine's log
        with self.changed:
            self.lines.append(line)
            self.changed.notify_all()

    def _make(self) -> None:
        try:
            ensure(told=self._said)
            state, error = "made", None
        except Refused as refused:
            state, error = "failed", str(refused)
        except Exception as failure:  # noqa: BLE001 - said, and the next asker tries again
            state, error = "failed", f"{type(failure).__name__}: {failure}"
        if error is not None:
            print(f"cad: {error}", file=sys.stderr, flush=True)
        with self.changed:
            self.state, self.error = state, error
            self.changed.notify_all()
        if state == "made" and self.made is not None:
            self.made()

    def follow(self, told: Callable[[str], None]) -> str | None:
        """The base made, by the making under way here or one started now: each of its lines said to
        ``told``, from its first, as it comes. None once the base is made, else why not, in one line."""
        if not self.start():
            return None  # made already, or this installation's own environment
        said = 0
        while True:
            with self.changed:
                while len(self.lines) == said and self.state == "making":
                    self.changed.wait()
                lines, state, error = self.lines[said:], self.state, self.error
            for line in lines:
                told(line)
            said += len(lines)
            if state != "making":  # every line it said is among those told
                return error if state == "failed" else None

    def status(self) -> dict[str, Any] | None:
        """The making as ``status`` says it: its state, its last line, how long it has run, and why it
        failed; None when nothing was made here."""
        with self.changed:
            if self.state is None:
                return None
            return {"state": self.state, "line": self.lines[-1] if self.lines else None, "error": self.error,
                    "seconds": round(time.time() - (self.since or time.time()), 1)}


# The engine's making of its base (``Making``): one a process.
MAKING = Making()


# --- making it -------------------------------------------------------------------------------------


def find_uv() -> str:
    """uv: the one on ``PATH``, else the one cadgen's ``uv`` dependency carries."""
    found = shutil.which("uv")
    if found:
        return found
    try:
        from uv import find_uv_bin

        return find_uv_bin()
    except (ImportError, FileNotFoundError):
        pass
    from cad_server.updates import command

    raise Refused("the server makes its CAD kernel environment with uv, and finds none: it depends on the uv "
                  f"package, which carries it; install text-to-cad again: run `{command()}`")


@dataclass(frozen=True)
class Recipe:
    """What makes an environment with uv (``make``): the Python of its virtual environment, what is
    installed in it, and the words said of it. ``release`` and ``source`` are the cadgen it installs, as
    an installation names them (``Installation``): a release on the index (``source`` None) is asked for
    again with its index page fetched anew when uv's cached page predates it."""

    what: str  # the environment, in words: "the CAD kernel environment", "text-to-cad 0.9.1"
    python: str  # the interpreter its virtual environment is made of
    requirement: tuple[str, ...]  # what ``uv pip install`` installs
    release: str
    source: str | None
    making: str  # said before uv starts
    downloading: str  # said before uv is asked online, for what its cache did not hold


def commands(uv: str, env: Path, recipe: Recipe) -> list[list[str]]:
    """The uv commands that make an environment: a virtual environment of the recipe's Python, then what
    it installs, the files hard links to uv's cache (``LINK``), and a folder of wheels a test names read
    beside the index (``FIND_LINKS_ENV``)."""
    found = os.environ.get(FIND_LINKS_ENV, "").strip()
    links = ["--find-links", found] if found else []
    return [[uv, "venv", "--no-project", "--python", recipe.python, str(env)],
            [uv, "pip", "install", "--python", str(interpreter(env)), "--link-mode", LINK, *links, *recipe.requirement]]


def recipe(installation: Installation) -> Recipe:
    """The base's recipe: ``cad[build123d]`` as the installation installs it, on its own Python."""
    return Recipe(what=WHAT, python=installation.executable, requirement=tuple(installation.requirement()),
                  release=installation.release, source=installation.source,
                  making=f"making {WHAT}, once: {LIBRARY}[{EXTRA}] {installation.release} on Python {installation.python}",
                  downloading="downloading the CAD kernel (about 220 MB) and what it needs, once")


def _say(line: str) -> None:
    print(f"cad: {line}", file=sys.stderr, flush=True)


def _make(env: Path, installation: Installation, told: Callable[[str], None]) -> dict[str, Any]:
    """The base at ``env`` made (``make``): the import path its Python starts with asked of it, and its
    marker, naming the installation it belongs to, written last."""

    def finish(steps: list[list[str]], seconds: float) -> dict[str, Any]:
        return {"schema": SCHEMA, "key": env.name, "inputs": _inputs(installation),
                "installation": dataclasses.asdict(installation), "path": _path(env), "commands": steps,
                "seconds": round(seconds, 2), "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    return make(env, recipe(installation), told, finish=finish, marker=MARKER, done=complete)


def make(env: Path, recipe: Recipe, told: Callable[[str], None], *,
         finish: Callable[[list[list[str]], float], dict[str, Any]], marker: str,
         done: Callable[[Path], dict[str, Any] | None]) -> dict[str, Any]:
    """An environment at ``env`` made with uv (``commands``): what was there removed, the virtual
    environment made, the recipe installed -- from uv's cache first, ``--offline``, and from the network
    only for what it does not hold, said in a line first -- and its marker (``finish``'s, written to
    ``marker`` in it) written last, so ``done`` reads it complete. One process makes it while another
    waits (a lock beside it), and one that finds it made meanwhile takes that one. Its marker;
    ``Refused`` in one line when uv cannot make it (``failure``), or a file of it cannot be removed or
    written (``_cannot``). The base (``ensure``) and a release's folder (``cad_server._internal.releases``)
    are both made by it."""
    import contextlib

    from cad_server._internal.file_lock import exclusive

    def waiting() -> None:
        told(f"waiting for another process that is making {recipe.what}")

    with contextlib.ExitStack() as held:
        try:
            env.parent.mkdir(parents=True, exist_ok=True)
            held.enter_context(exclusive(env.parent / f"{env.name}.lock", waiting=waiting))
        except OSError as error:
            raise Refused(_cannot(f"the folder {env.parent}", error, recipe.what)) from None
        found = done(env)
        if found is not None:
            return found  # made meanwhile, by the process this one waited for
        _remove(env, recipe.what)
        steps = commands(find_uv(), env, recipe)
        told(f"{recipe.making}, in {env}")
        started = time.monotonic()
        venv, install = steps
        result = _uv(venv, env.parent)
        if result.returncode == 0:
            result = _uv([*install, "--offline"], env.parent)
            if result.returncode != 0:
                # uv's cache did not hold all of it: from the network, once.
                told(recipe.downloading)
                result = _uv(install, env.parent)
                if result.returncode != 0 and recipe.source is None and _unlisted(result, recipe.release):
                    # uv reads an index page it cached (ten minutes, PyPI's): one from before the release
                    # was listed says there is none. Asked again, that page alone fetched anew.
                    steps[1] = install = [*install, "--refresh-package", LIBRARY, "--refresh-package", SERVER]
                    result = _uv(install, env.parent)
            step = install
        else:
            step = venv
        if result.returncode != 0:
            raise Refused(failure(step, result.stderr or result.stdout, recipe))
        written = finish(steps, time.monotonic() - started)
        from cad._internal.atomic_replace import write_bytes_atomic

        try:
            write_bytes_atomic(env / marker, (json.dumps(written, indent=1) + "\n").encode("utf-8"))
        except OSError as error:
            raise Refused(_cannot(str(env / marker), error, recipe.what)) from None
    return written


def _path(env: Path) -> list[str]:
    """The import path the base's Python starts with: what a process of the engine's pools, started in
    it, imports from (``cad.engine.serve``'s spawn pools take it from the marker)."""
    try:
        done = subprocess.run([str(interpreter(env)), "-I", "-c", "import json, sys; print(json.dumps(sys.path))"],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120)
        found = json.loads(done.stdout.strip().splitlines()[-1]) if done.returncode == 0 else None
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as error:
        raise Refused(f"{WHAT} made at {env} does not run: {error}") from None
    if not isinstance(found, list) or not all(isinstance(item, str) for item in found):
        said = (done.stderr or done.stdout).strip().splitlines()
        raise Refused(f"{WHAT} made at {env} does not run: {said[-1] if said else 'it said nothing'}")
    return found


def _cannot(what: str, error: OSError, environment: str = WHAT) -> str:
    """That ``what`` (a file or folder of ``environment``) cannot be written, in one line: a denial as a
    sandbox's, which this once outside it, or with its permission, makes."""
    if isinstance(error, PermissionError):
        return (f"the system denies text-to-cad {what} ({error.strerror or error}); a sandbox that forbids it does: "
                "run this once outside it, or with its permission")
    return f"cannot write {what}: {error.strerror or error}"


# The uv commands this process runs now (``_uv``): an engine that stops takes them with it (``halt``), so
# none goes on writing an environment the next maker removes and makes again.
_RUNNING: set[subprocess.Popen] = set()
_RUNNING_LOCK = threading.Lock()


def _uv(step: list[str], folder: Path) -> subprocess.CompletedProcess:
    """A uv command run in the environments' folder, where no project's uv settings are read."""
    try:
        process = subprocess.Popen(step, cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    except OSError as error:
        raise Refused(f"cannot run uv ({step[0]}): {error.strerror or error}") from None
    with _RUNNING_LOCK:
        _RUNNING.add(process)
    try:
        out, err = process.communicate()
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(process)
    return subprocess.CompletedProcess(step, process.returncode, out, err)


def halt() -> None:
    """The uv commands this process runs now killed: the engine is stopping (a making of its base is cut
    short, and made again by the next asker)."""
    with _RUNNING_LOCK:
        running = list(_RUNNING)
    for process in running:
        try:
            process.kill()
        except OSError:
            pass


def _unlisted(done: subprocess.CompletedProcess, release: str) -> bool:
    """Whether uv found no ``cad==<release>`` (or the server's) on its index."""
    said = " ".join((done.stderr or done.stdout or "").split())
    return any(f"no version of {name}=={release}" in said for name in (LIBRARY, f"{LIBRARY}[{EXTRA}]", SERVER))


def _remove(env: Path, what: str = WHAT) -> None:
    """What is at ``env`` removed, before an environment is made there (``what``, in words). On Windows a file another process reads
    a moment (a scanner, an indexer) refuses its removal (``WinError 32``, ``5``): the removal goes on
    after a wait (``REMOVE_DELAYS``), from where it stopped."""
    for delay in (*REMOVE_DELAYS, None):
        if not os.path.lexists(env):
            return
        try:
            if env.is_dir() and not env.is_symlink():
                shutil.rmtree(env)
            else:
                env.unlink()
            return
        except OSError as error:
            if delay is None or getattr(error, "winerror", None) not in (5, 32):
                if isinstance(error, PermissionError) and getattr(error, "winerror", None) is None:
                    raise Refused(_cannot(f"{what} at {env}", error, what)) from None
                raise Refused(f"cannot remove {what} at {env} to make it again: {error.strerror or error}") from None
            time.sleep(delay)


def _explained(said: str) -> str:
    """uv's resolver explanation (the lines after ``╰─▶``), unwrapped into one line; else ''."""
    lines = said.splitlines()
    at = next((index for index, line in enumerate(lines) if "╰─▶" in line), None)
    if at is None:
        return ""
    found = [lines[at].split("╰─▶", 1)[1].strip()]
    for line in lines[at + 1:]:
        if not line.strip() or line.lstrip().startswith("hint:"):
            break
        found.append(line.strip())
    return " ".join(found)


def _last(said: str) -> str:
    """uv's error in one line: its ``error:`` line, and the last ``Caused by:`` beneath it or else its
    hint; else its last line."""
    lines = [line.strip() for line in said.splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith("error:")]
    causes = [line.removeprefix("Caused by:").strip() for line in lines if line.startswith("Caused by:")]
    hints = [line for line in lines if line.startswith("hint:")]
    if errors:
        words = errors[0].removeprefix("error:").strip()
        return f"{words} ({causes[-1]})" if causes else f"{words} ({hints[0]})" if hints else words
    return lines[-1] if lines else "uv said nothing"


def failure(step: list[str], said: str, recipe: Recipe) -> str:
    """Why uv could not make an environment (``recipe``'s), in one line of cadgen's: a file the system
    denies it (a sandbox's); the network it needs once; a Python it cannot use; a release no index it
    reads has; else uv's own words."""
    explained = _explained(said)
    words = explained or _last(said)
    what = recipe.what
    if DENIED.search(said) and not explained:
        return (f"the system denies uv what {what} needs ({_last(said)}); a sandbox that forbids it does: run this "
                "once outside it, or with its permission")
    if NETWORK.search(said):
        return f"{what} needs the network once: {_last(said)}"
    if step[1] == "venv":
        return f"uv cannot make {what} on {recipe.python}: {words}"
    release = recipe.release
    if recipe.source is None and any(f"no version of {name}=={release}" in explained
                                     for name in (LIBRARY, f"{LIBRARY}[{EXTRA}]", SERVER)):
        return f"release {release} is on no package index uv reads: {explained}"
    return f"uv could not make {what}: {words}"
