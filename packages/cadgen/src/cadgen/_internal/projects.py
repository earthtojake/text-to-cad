"""The environment ``cadgen run`` runs a model script in: the script's project, its declared
dependencies, and a virtual environment uv makes of them with the engine's own cadgen.

- **The project** (``find``) is the nearest folder, from the script's own up, holding
  ``pyproject.toml``, ``uv.lock`` or ``requirements.txt``; with none, the script's folder. Its
  dependencies are ``requirements.txt``, the project itself -- installed editable when its
  ``pyproject.toml`` builds a package (a ``[build-system]``, or ``tool.uv.package``), its
  ``[project]`` dependencies alone when it builds none, as uv reads a project without a build system
  -- and the script's inline metadata (PEP 723's ``# /// script`` block). The project's own ``.venv``
  is never read or written.
- **The Python** (``python_for``) is the project's choice when it declares one: its
  ``.python-version`` (uv's file), else the newest line cadgen runs on (``supported``) that its
  ``requires-python`` -- its ``pyproject.toml``'s and the script's inline one -- admits; else the
  engine's own line. A project that asks for a line cadgen does not run on is refused by name.
- **The environment** (``ensure``) holds those dependencies and the engine's cadgen -- the release
  it runs, or the source it runs from (``Engine``) -- in one resolution, so a conflict surfaces at
  once and the script, its worker and the engine run one cadgen by construction. uv makes it, with
  uv's managed Python, at ``<cache>/envs/<key>``: ``key`` is a digest of the project's folder (when it
  has one of the files above), the engine's installation and source, the Python chosen and the
  bytes of the dependency inputs, so a dependency change, another Python or an engine upgrade makes
  a new environment and the old one is left behind. Its marker, ``cadgen-env.json``, written last,
  makes it complete: a run of an unchanged project reads the inputs and the marker, and resolves
  nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

__all__ = ["Engine", "Project", "Refused", "SCHEMA", "commands", "complete", "declared", "ensure", "environment",
           "envs", "failure", "find", "find_uv", "inputs", "interpreter", "key", "python_for", "supported"]

# The files that make a folder a project, nearest first.
MARKERS = ("pyproject.toml", "uv.lock", "requirements.txt")
PYTHON_VERSION = ".python-version"
# The environments' folder in the cache folder, and the marker that makes one complete.
ENVS = "envs"
MARKER = "cadgen-env.json"
# The file in an environment that holds the engine's cadgen against every other requirement on cadgen --
# the project's own (``cadgen==0.8.2``), or a dependency's: uv's ``--override``.
OVERRIDE = "cadgen-override.txt"
SCHEMA = "cadgen env/1"
# The CPython lines cadgen runs on when the installed metadata cannot say (``supported``): from its
# floor, its ``requires-python``, to the newest its kernel (OCP, build123d) ships wheels for.
PYTHONS = ("3.11", "3.12", "3.13", "3.14")
# The distributions whose ``Requires-Python`` bounds the lines a project environment may run: cadgen,
# its kernel's OCP (whichever provides it) and build123d.
BOUNDED_BY = ("cadgen", ("cadquery-ocp-novtk", "cadquery-ocp"), "build123d")
# How an environment's installed files are made from uv's cache: hard links, as uv makes them on Linux and
# Windows anyway. On macOS uv clones them, new files each, and the system looks at each native library
# a process first loads once per file: a new environment's first kernel load measured 44 s with clones,
# against 32 s for the first environment of hard links and 7.6 s for each one after it (one-box model's
# imports, OCP 8.0, Apple silicon). Nothing writes into an environment's installed files.
LINK = "hardlink"
# The waits between the tries at removing an environment on Windows, where a scanner reading a file just
# written refuses its removal for a moment (``_remove``): the test suite's cleanup ladder's first six.
REMOVE_DELAYS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)
# What uv says when it cannot reach an index or a download: the network, not the project.
NETWORK = re.compile(r"error sending request|network was disabled|dns error|tcp connect error|failed to lookup address"
                     r"|Connection refused|Network is unreachable|timed out|Could not connect", re.I)
# What uv says when the system refuses it a file it writes (its cache, the environment): a sandbox's.
DENIED = re.compile(r"Operation not permitted|Permission denied|Access is denied|os error (?:1|13)\)")


class Refused(Exception):
    """Why ``cadgen run`` cannot run the script in its project's environment: one line."""


# --- the engine's cadgen ------------------------------------------------------------------------


@dataclass(frozen=True)
class Engine:
    """The engine a model will run on, as its hello says it (``client.connect``'s ``engine``): its
    ``release``, the ``installation`` it runs as, its Python's line and where its cadgen installs from
    (``daemon.runs_as``). An engine from before says neither of the last three: its installation is its
    release, its Python this process's line."""

    release: str
    installation: str
    python: str
    source: str | None = None
    arch: str | None = None

    @classmethod
    def said(cls, engine: dict[str, Any]) -> "Engine":
        release = engine.get("release")
        if not isinstance(release, str) or not re.fullmatch(r"[0-9][0-9A-Za-z.+_-]*", release):
            raise Refused(f"the engine on port {engine.get('port')} names no cadgen release this cadgen can install")
        installation = engine.get("installation")
        python = engine.get("python")
        source = engine.get("source")
        native = engine.get("native") if isinstance(engine.get("native"), dict) else {}
        return cls(release, installation if isinstance(installation, str) and installation else release,
                   python if isinstance(python, str) and re.fullmatch(r"[0-9]+\.[0-9]+", python)
                   else f"{sys.version_info[0]}.{sys.version_info[1]}",
                   source if isinstance(source, str) and source else None,
                   native.get("arch") if isinstance(native.get("arch"), str) else None)

    def requirement(self) -> list[str]:
        """What installs this engine's cadgen: its source tree editable, its wheel, or its release."""
        if self.source is None:
            return [f"cadgen=={self.release}"]
        return ["-e", self.source] if os.path.isdir(self.source) else [self.source]

    def override(self) -> str:
        """The same as a line of uv's overrides (``OVERRIDE``), which stands in place of every requirement
        on cadgen, the install's own among them: so a path is a ``file:`` URL, and a tree stays editable."""
        if self.source is None:
            return f"cadgen=={self.release}"
        uri = Path(self.source).resolve().as_uri()
        return f"-e {uri}" if os.path.isdir(self.source) else f"cadgen @ {uri}"

    def words(self) -> str:
        return f"cadgen {self.installation}"


# --- the project ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Project:
    """A script's project (``find``): its folder and what it declares."""

    script: Path
    root: Path
    # Whether the folder is a project's (it holds one of ``MARKERS``), not a script's folder alone.
    marked: bool
    # ``requirements.txt`` and its bytes (None without one).
    requirements: Path | None
    listed: bytes | None
    # ``pyproject.toml``'s bytes and its ``[project]`` table (None without one).
    pyproject: bytes | None
    table: dict[str, Any] | None
    # Whether the project installs as a package, editable: it has a build system (or says so).
    package: bool
    lock: bytes | None
    # The script's ``# /// script`` block as written, and its TOML.
    inline: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    # The first version ``.python-version`` names, and where it is.
    pinned: str | None = None
    pinned_at: Path | None = None

    def dependencies(self) -> list[str]:
        """The requirements the script declares inline (PEP 723), as uv takes them."""
        return list(self.metadata.get("dependencies") or [])

    def requires_python(self) -> list[str]:
        """The ``requires-python`` specifiers the project declares: its ``pyproject.toml``'s and the
        script's inline one."""
        found = [] if self.table is None else [self.table.get("requires-python")]
        return [spec for spec in (*found, self.metadata.get("requires-python")) if spec]


def find(script: Path | str) -> Project:
    """The project of ``script`` (see the module): ``Refused`` when what it declares cannot be read."""
    script = Path(script).resolve()
    folder = script.parent
    root = next((candidate for candidate in (folder, *folder.parents)
                 if any((candidate / name).is_file() for name in MARKERS)), None)
    marked = root is not None
    root = root or folder
    pyproject = _read(root / "pyproject.toml")
    data = _toml(pyproject, root / "pyproject.toml") if pyproject is not None else {}
    table = data.get("project") if isinstance(data.get("project"), dict) else None
    if table is not None:
        _strings(table.get("dependencies", []), "[project] dependencies", root / "pyproject.toml")
        if not isinstance(table.get("requires-python", ""), str):
            raise Refused(f"{root / 'pyproject.toml'}: requires-python is not a string")
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    told = (tool.get("uv") if isinstance(tool.get("uv"), dict) else {}).get("package")
    package = table is not None and (told if isinstance(told, bool) else "build-system" in data)
    inline, metadata = _inline(script)
    pinned = pinned_at = None
    for candidate in (folder, *folder.parents):
        if (candidate / PYTHON_VERSION).is_file():
            pinned_at = candidate / PYTHON_VERSION
            pinned = _pinned(pinned_at)
            break
        if candidate == root:
            break
    listed = _read(root / "requirements.txt")
    return Project(script, root, marked, None if listed is None else root / "requirements.txt", listed, pyproject,
                   table, package, _read(root / "uv.lock"), inline, metadata, pinned, pinned_at)


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None
    except OSError as error:
        raise Refused(f"cannot read {path}: {error.strerror or error}") from None


def _toml(data: bytes, path: Path) -> dict[str, Any]:
    import tomllib

    try:
        return tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise Refused(f"{path} is not TOML cadgen can read: {error}") from None


def _strings(value: Any, what: str, where: Path) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise Refused(f"{where}: {what} is not a list of requirements")


# PEP 723's reference expression: a ``# /// TYPE`` block of comment lines, ended by ``# ///``.
_BLOCK = re.compile(r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$")


def _inline(script: Path) -> tuple[str | None, dict[str, Any]]:
    """The script's ``# /// script`` block as written, and its TOML (PEP 723); ``(None, {})`` without
    one."""
    text = (_read(script) or b"").decode("utf-8", errors="replace").replace("\r\n", "\n")
    blocks = [found for found in _BLOCK.finditer(text) if found["type"] == "script"]
    if not blocks:
        return None, {}
    if len(blocks) > 1:
        raise Refused(f"{script} has more than one `# /// script` block")
    content = "".join(line[2:] if line.startswith("# ") else line[1:]
                      for line in blocks[0]["content"].splitlines(keepends=True))
    metadata = _toml(content.encode("utf-8"), script)
    _strings(metadata.get("dependencies", []), "its inline dependencies", script)
    if not isinstance(metadata.get("requires-python", ""), str):
        raise Refused(f"{script}: its inline requires-python is not a string")
    return blocks[0].group(0), metadata


def _pinned(path: Path) -> str:
    """The version ``.python-version`` names: its first line that is no comment, as written."""
    text = (_read(path) or b"").decode("utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    raise Refused(f"{path} names no Python version")


# --- the Python ---------------------------------------------------------------------------------

_CLAUSE = re.compile(r"(~=|===|==|!=|<=|>=|<|>)\s*([0-9]+(?:\.[0-9]+)*)(\.\*)?")
_ASKED = re.compile(r"(?:cpython[-@]?|python)?([0-9]+)\.([0-9]+)(?:\.([0-9]+))?", re.I)


def clauses(spec: str) -> list[tuple[str, tuple[int, ...], bool]] | None:
    """A version specifier (``>=3.11,<3.15``) as its clauses -- each its operator, its version and
    whether it ends in ``.*`` -- or None for one this cannot read."""
    found = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        match = _CLAUSE.fullmatch(part)
        if match is None or (match[3] and match[1] not in ("==", "!=")) or (match[1] == "~=" and "." not in match[2]):
            return None
        found.append((match[1], tuple(int(number) for number in match[2].split(".")), bool(match[3])))
    return found


def _holds(op: str, wanted: tuple[int, ...], prefix: bool, version: tuple[int, ...]) -> bool:
    if prefix:
        same = version[:len(wanted)] == wanted
        return same if op == "==" else not same
    width = max(len(wanted), len(version))
    have, want = version + (0,) * (width - len(version)), wanted + (0,) * (width - len(wanted))
    if op == "~=":
        return have >= want and version[:len(wanted) - 1] == wanted[:-1]
    return {"==": have == want, "===": have == want, "!=": have != want, "<": have < want,
            "<=": have <= want, ">": have > want, ">=": have >= want}[op]


def admits(found: list[tuple[str, tuple[int, ...], bool]], line: str) -> bool:
    """Whether some release of the Python ``line`` (``3.12``: 3.12.0, 3.12.1, ...) meets every clause:
    asked of its first release, its last, and those beside each patch a clause names."""
    major, minor = (int(part) for part in line.split("."))
    patches = {0, 999}
    for _op, wanted, _prefix in found:
        if len(wanted) > 2:
            patches.update((max(0, wanted[2] - 1), wanted[2], wanted[2] + 1))
    return any(all(_holds(op, wanted, prefix, (major, minor, patch)) for op, wanted, prefix in found)
               for patch in sorted(patches))


def supported() -> tuple[str, ...]:
    """The CPython lines a project environment may run, oldest first: every 3.N that cadgen's own
    ``Requires-Python``, its OCP's and build123d's all admit, as the installed metadata says them;
    ``PYTHONS`` when one is not installed or says none, and up to its newest when none bounds them."""
    from importlib import metadata

    found = []
    for names in BOUNDED_BY:
        spec = None
        for name in (names,) if isinstance(names, str) else names:
            try:
                spec = metadata.metadata(name).get("Requires-Python")
            except metadata.PackageNotFoundError:
                continue
            break
        parsed = clauses(spec) if isinstance(spec, str) else None
        if not parsed:
            return PYTHONS
        found.append(parsed)
    lines = tuple(f"3.{minor}" for minor in range(100) if all(admits(each, f"3.{minor}") for each in found))
    if not lines:
        return PYTHONS
    if "3.99" in lines:  # nothing bounds them above: the newest cadgen names
        newest = int(PYTHONS[-1].split(".")[1])
        lines = tuple(line for line in lines if int(line.split(".")[1]) <= newest)
    return lines or PYTHONS


def span(lines: tuple[str, ...]) -> str:
    """The lines cadgen runs on, in words: ``3.11–3.14`` (each named where they skip one)."""
    minors = [int(line.split(".")[1]) for line in lines]
    if len(lines) > 1 and minors == list(range(minors[0], minors[-1] + 1)):
        return f"{lines[0]}–{lines[-1]}"
    return ", ".join(lines)


def python_for(project: Project, engine: Engine) -> str:
    """The Python the project's environment runs, as uv is asked for it (see the module): the version
    ``.python-version`` names (``3.12``, ``3.12.4``), else the newest line cadgen runs on that the
    project's ``requires-python`` admits, else the engine's line. ``Refused`` when the project asks for
    a line cadgen does not run on."""
    if project.pinned is None and not project.requires_python():
        return engine.python
    lines = supported()
    remedy = f"cadgen runs on {span(lines)}: change requires-python or .python-version"
    if project.pinned is not None:
        asked = _ASKED.fullmatch(project.pinned)
        if asked is None or f"{asked[1]}.{asked[2]}" not in lines:
            raise Refused(f"this project asks for Python {project.pinned}; {remedy}")
        return ".".join(part for part in asked.groups() if part)
    specs = project.requires_python()
    parsed = [clauses(spec) for spec in specs]
    for spec, found in zip(specs, parsed):
        if found is None:
            raise Refused(f"this project's requires-python {spec!r} is no version specifier cadgen can read")
    admitted = [line for line in lines if all(admits(found, line) for found in parsed if found is not None)]
    if not admitted:
        raise Refused(f"this project asks for Python {' and '.join(specs)}; {remedy}")
    return admitted[-1]


# --- the environment ----------------------------------------------------------------------------


def envs() -> Path:
    """The project environments' folder: ``envs`` in the cache folder, which is regenerable."""
    from cadgen.viewer.recents import cache_dir

    return cache_dir() / ENVS


def inputs(project: Project, engine: Engine, python: str) -> dict[str, Any]:
    """What makes the environment, which its key digests (``key``) and its marker holds: the project's
    folder when it has one of ``MARKERS`` (only then does the environment name it: the project installed
    editable, the paths its requirements give), the engine's installation, source and architecture, the
    Python asked for, and the digests of ``requirements.txt``, ``pyproject.toml`` and ``uv.lock`` and
    the script's inline block as written."""
    def digest(data: bytes | None) -> str | None:
        return None if data is None else hashlib.sha256(data).hexdigest()

    return {"schema": SCHEMA, "root": str(project.root) if project.marked else None,
            "installation": engine.installation, "source": engine.source, "arch": engine.arch, "python": python,
            "requirements.txt": digest(project.listed), "pyproject.toml": digest(project.pyproject),
            "uv.lock": digest(project.lock), "inline": project.inline}


def key(project: Project, engine: Engine, python: str) -> str:
    """The environment's key: a short digest of its ``inputs``."""
    return hashlib.sha256(json.dumps(inputs(project, engine, python), sort_keys=True).encode("utf-8")).hexdigest()[:16]


def environment(project: Project, engine: Engine, python: str) -> Path:
    """Where the project's environment is: ``envs/<key>`` in the cache folder."""
    return envs() / key(project, engine, python)


def interpreter(env: Path) -> Path:
    """The environment's Python."""
    return env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def complete(env: Path, wanted: str) -> bool:
    """Whether the environment at ``env`` is complete: its marker, written last, is of key ``wanted``,
    and its Python is there."""
    try:
        marker = json.loads((env / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (isinstance(marker, dict) and marker.get("schema") == SCHEMA and marker.get("key") == wanted
            and interpreter(env).exists())


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
    from cadgen.updates import command

    raise Refused("cadgen run makes the project's environment with uv, and finds none: cadgen depends on the uv "
                  f"package, which carries it; install cadgen again: run `{command()}`")


def commands(uv: str, env: Path, python: str, engine: Engine, project: Project) -> list[list[str]]:
    """The uv commands that make the environment: a virtual environment of uv's managed Python, then
    the engine's cadgen and the project's dependencies, in one resolution, their files hard links to
    uv's cache (``LINK``), and the engine's cadgen in place of any other requirement on cadgen
    (``OVERRIDE``: a project or a dependency that names its own cadgen still runs the engine's)."""
    install = [uv, "pip", "install", "--python", str(interpreter(env)), "--link-mode", LINK,
               "--override", str(env / OVERRIDE), *engine.requirement()]
    if project.requirements is not None:
        install += ["-r", str(project.requirements)]
    if project.package:
        install += ["-e", str(project.root)]
    elif project.table is not None:  # its [project] dependencies, as uv reads them (its tool.uv.sources too)
        install += ["-r", str(project.root / "pyproject.toml")]
    install += project.dependencies()
    return [[uv, "venv", "--no-project", "--managed-python", "--python", python, str(env)], install]


def declared(project: Project) -> list[str]:
    """The requirements on cadgen the project declares itself, each as written, but a bare ``cadgen``:
    in its ``requirements.txt``, its ``[project]`` dependencies, the script's inline ones. Each gives
    way to the engine's cadgen (``OVERRIDE``)."""
    listed = [line.split(" #", 1)[0].strip() for line in (project.listed or b"").decode("utf-8", "replace").splitlines()]
    named = [line for line in listed if line and not line.startswith(("#", "-"))]
    named += list((project.table or {}).get("dependencies") or []) + list(project.metadata.get("dependencies") or [])
    found = [(re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement), requirement) for requirement in named]
    return [requirement.strip() for match, requirement in found
            if match and re.sub(r"[-_.]+", "-", match[1]).lower() == "cadgen" and requirement.strip() != match[1]]


def _say(line: str) -> None:
    print(f"cadgen: {line}", file=sys.stderr, flush=True)


def ensure(project: Project, engine: Engine, python: str, *, refresh: bool = False,
           told: Callable[[str], None] = _say) -> Path:
    """The project's environment (``environment``), made first when it is not complete or ``refresh``
    asks: what was there removed, then uv's ``commands`` run in the project's folder, and the marker
    written last. One run makes it while another waits (a lock beside it). ``Refused`` in one line
    when uv cannot (``failure``), or a file of it cannot be removed or written (``_cannot``: a sandbox
    that forbids writing outside its folder refuses all of it, a complete environment's run aside)."""
    import contextlib

    from cadgen.engine.file_lock import exclusive

    wanted = key(project, engine, python)
    env = envs() / wanted
    if not refresh and complete(env, wanted):
        return env

    def waiting() -> None:
        told("waiting for another run that is making this project's environment")

    with contextlib.ExitStack() as held:
        try:
            env.parent.mkdir(parents=True, exist_ok=True)
            held.enter_context(exclusive(env.parent / f"{wanted}.lock", waiting=waiting))
        except OSError as error:
            raise Refused(_cannot(f"the environments' folder {env.parent}", error)) from None
        if not refresh and complete(env, wanted):
            return env  # made meanwhile, by the run this one waited for
        _remove(env)
        steps = commands(find_uv(), env, python, engine, project)
        told(f"making this project's environment, once: Python {python}, {engine.words()} and the project's "
             f"dependencies, in {env}")
        own = declared(project)
        if own:
            told(f"the project's own {' and '.join(own)} gives way to the engine's {engine.words()}")
        started = time.monotonic()
        for index, step in enumerate(steps):
            if index == 1:  # in the environment uv just made
                try:
                    (env / OVERRIDE).write_text(engine.override() + "\n", encoding="utf-8")
                except OSError as error:
                    raise Refused(_cannot(str(env / OVERRIDE), error)) from None
            done = _uv(step, project.root)
            if done.returncode != 0 and index == 1 and engine.source is None and _unlisted(done, engine):
                # uv reads an index page it cached (ten minutes, PyPI's): one from before the engine's release
                # was listed says there is none. Asked again, that page alone fetched anew.
                steps[1] = step = [*step, "--refresh-package", "cadgen"]
                done = _uv(step, project.root)
            if done.returncode != 0:
                raise Refused(failure(step, done.stderr or done.stdout, engine, python))
        from cadgen._internal.atomic_replace import write_bytes_atomic

        marker = {"schema": SCHEMA, "key": wanted, "inputs": inputs(project, engine, python), "release": engine.release,
                  "commands": steps, "seconds": round(time.monotonic() - started, 2),
                  "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        try:
            write_bytes_atomic(env / MARKER, (json.dumps(marker, indent=1) + "\n").encode("utf-8"))
        except OSError as error:
            raise Refused(_cannot(str(env / MARKER), error)) from None
    return env


def _cannot(what: str, error: OSError) -> str:
    """That ``what`` (a file or folder of the environment) cannot be written, in one line: a denial as a
    sandbox's, which this once outside it, or with its permission, makes."""
    if isinstance(error, PermissionError):
        return (f"the system denies cadgen {what} ({error.strerror or error}); a sandbox that forbids it does: "
                "run this once outside it, or with its permission")
    return f"cannot write {what}: {error.strerror or error}"


def _uv(step: list[str], folder: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(step, cwd=folder, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as error:
        raise Refused(f"cannot run uv ({step[0]}): {error.strerror or error}") from None


def _unlisted(done: subprocess.CompletedProcess, engine: Engine) -> bool:
    """Whether uv found no ``cadgen==<release>`` of the engine's on its index."""
    said = " ".join((done.stderr or done.stdout or "").split())
    return f"no version of cadgen=={engine.release}" in said


def _remove(env: Path) -> None:
    """What is at ``env`` removed, before an environment is made there. On Windows a file another process
    reads a moment (a scanner, an indexer) refuses its removal (``WinError 32``, ``5``): the removal goes
    on after a wait (``REMOVE_DELAYS``), from where it stopped."""
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
                    raise Refused(_cannot(f"the environment at {env}", error)) from None
                raise Refused(f"cannot remove the environment at {env} to make it again: "
                              f"{error.strerror or error}") from None
            time.sleep(delay)


# --- what uv said -------------------------------------------------------------------------------


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


def _kernel(release: str) -> str | None:
    """What cadgen ``release`` needs of its kernel, in words (``build123d>=0.13.0,<0.14 and
    cadquery-ocp-novtk>=8.0,<8.1``), as this installation's metadata says when it is that release."""
    from importlib import metadata

    try:
        if metadata.version("cadgen") != release:
            return None
        requires = metadata.requires("cadgen") or []
    except metadata.PackageNotFoundError:
        return None
    named = []
    for requirement in requires:
        found = re.match(r"\s*(build123d|cadquery-ocp(?:-novtk)?)\s*([^;]*)", requirement, re.I)
        if found and found[2].strip():
            ordered = sorted((part.strip() for part in found[2].split(",")), key=lambda part: not part.startswith(">"))
            named.append(found[1] + ",".join(ordered))
    return " and ".join(named) or None


_KERNEL_PIN = re.compile(r"^\s*((?:build123d|cadquery-ocp(?:-novtk)?|cadgen)\s*(?:\[[^\]]*\])?\s*[=<>!~]=?[^\s;#]+)", re.I)


def _declared_kernel_pins(step: list[str]) -> list[str]:
    """The kernel and cadgen pins a uv install step would install from the project's own files and
    inline requirements (``-r FILE`` entries read, comments and blank lines skipped; bare requirement
    arguments as given), each as ``name==version``-style text with its spaces removed."""
    found: list[str] = []
    arguments = iter(step)
    for argument in arguments:
        lines: list[str] = []
        if argument in ("-r", "--requirement", "--requirements"):
            path = next(arguments, None)
            if path is None:
                break
            try:
                lines = pathlib.Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
        elif not argument.startswith("-") and not argument.endswith(".toml"):
            lines = [argument]
        for line in lines:
            matched = _KERNEL_PIN.match(line.split("#", 1)[0])
            if matched:
                found.append(re.sub(r"\s+", "", matched[1]))
    return list(dict.fromkeys(found))


def failure(step: list[str], said: str, engine: Engine, python: str) -> str:
    """Why uv could not make the environment, in one line of cadgen's: a file the system denies it (a
    sandbox's); the network it needs once; a Python it cannot provide; the project's dependencies
    against the engine's cadgen (what cadgen needs of its kernel, and what the project pins); else uv's
    own words."""
    explained = _explained(said)
    words = explained or _last(said)
    if DENIED.search(said) and not explained:
        return (f"the system denies uv what the project's environment needs ({_last(said)}); a sandbox that forbids "
                "it does: run this once outside it, or with its permission")
    if NETWORK.search(said):
        return f"the project's environment needs the network once: {_last(said)}"
    if step[1] == "venv":
        return f"uv cannot provide Python {python} for this project's environment: {words}"
    if f"no version of cadgen=={engine.release}" in explained and engine.source is None:
        return f"cadgen {engine.release}, the engine's, is on no package index uv reads: {explained}"
    unsolved = "No solution found when resolving dependencies" in said
    if (explained and re.search(r"\bcadgen\b", explained)) or unsolved:
        # uv's resolver failed: with its explanation when it printed one (it does not always), else
        # its header alone; either way this is the project's dependencies against the engine's.
        mine = {" ".join(engine.requirement()), f"cadgen=={engine.release}"}
        # What the project asked for, as uv names it ("you require build123d==0.1"), not what uv concluded
        # it requires ("we can conclude that you require build123d>=0.13.0,<0.14").
        asked = re.findall(r"(?<!conclude that )you require ([A-Za-z0-9._-]+(?:\[[^\]]*\])?[=<>!~]=?[^\s,]+)", explained)
        pins = [pin for pin in dict.fromkeys(pin.rstrip(".") for pin in asked) if pin not in mine]
        if not pins:
            # uv does not always print its explanation: the project's own words then, the kernel
            # and cadgen pins among what the step installs (its -r files and its inline requirements).
            pins = [pin for pin in _declared_kernel_pins(step) if pin not in mine]
        needs = _kernel(engine.release)
        said_of = "; ".join(part for part in (f"cadgen {engine.release} needs {needs}" if needs else None,
                                              f"the project pins {', '.join(pins)}" if pins else None) if part)
        return (f"the project's dependencies conflict with {engine.words()}"
                + (f": {said_of}" if said_of else "") + f" (uv: {explained or _last(said)})")
    return f"uv could not make this project's environment: {words}"
