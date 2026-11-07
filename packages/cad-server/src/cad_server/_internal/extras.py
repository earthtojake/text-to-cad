"""The environments ``cad run`` makes for a program: cad pinned at the device's release with the
integrations the program uses, the packages it names, and the options it hands uv -- each made once,
outside any sandbox, beside the base, and used again while the same set recurs.

**What one holds** (``Spec``): ``cad[<integrations>]==<release>`` -- or the installation's source tree or
wheel, as the base installs it (``base.Installation.requirement``) -- and beside it:

- the integrations, worked out in one place (``integrations``): a script's ``# /// script`` header that
  names ``cad[...]`` decides them outright; else a static scan of the program's imports, and the local
  modules it imports (``cad_server._internal.scan``), with what ``--with`` and a project add;
- the packages a script's header names (PEP 723's ``dependencies``) -- and then any project around it is
  not read, as ``uv run`` reads none for a script with a header -- else, inside a uv project (a
  ``pyproject.toml`` with a ``[project]`` table, found from the working folder up, or named by
  ``--project``), that project's: the project itself, editable, when it is packaged, else its
  dependencies (``-r pyproject.toml``); and on top, in either case, ``--with``, ``--with-editable`` and
  ``--with-requirements``;
- a project's lock: where the project has a ``uv.lock``, exactly its locked set, exported by uv (``uv export
  --format requirements-txt``, the project's extras and groups as given; ``--locked`` and ``--frozen`` with
  uv's meaning), in place of a resolution of its ``pyproject.toml``, cad's own line taken out for the pin;
- the options of uv's it was given (``options``: indexes, find-links, resolution, build settings -- handed
  to uv as given, so ``cad run`` never drifts from uv), uv's settings in the caller's environment
  (``environment``: ``base.UV_SETTINGS``, an allowlist of how uv resolves), the uv configuration it reads
  (``config``: the project's ``[tool.uv]``, or a ``uv.toml``, found as uv finds one -- uv runs in the
  project's folder, so a project's private index works), and the Python it is made on (``--python``, as uv
  reads it; by default the engine's own).

A header, a project or a project's lock that pins cad to another release than the device's is refused in
one line, before anything is made (``pinned``, ``locked_cad``); the device's release is fine, and an unpinned ``cad`` is given it. So PyPI's
unrelated ``cad`` 1.x is never resolved.

**The key** digests the installation's base's inputs (the release among them), the spec, and what each
local package, editable folder and requirements file is now (``fingerprints``): an edit to a local package
is another environment, said in the line that makes it; an editable folder is keyed by its metadata alone,
its code read as it is; a lock, a project's ``pyproject.toml`` and a uv configuration by their contents. ``places.RUN_WITH`` tells the program how it was named, which a document it
builds says builds it again.

**Making one** (``ensure``): by the device's engine when one runs -- outside any sandbox, its lines
followed as it makes it (``{"op": "base", "key", "spec"}``, ``making``) -- else here, with uv, as the base
is made (``base.make``: offline first, from uv's cache, the base's link mode, find-links and index
settings, a lock for one maker, the marker written last). After uv installs it, the distributions it holds
are read: one of an integration it was not given (``build123d``, pulled in by a package that depends on
it) adds that integration's extra, and uv resolves again, so cad's pins decide its version. Once made it is
never changed. A script's ``requires-python`` the Python cannot meet is refused in one line; what uv cannot
do is said in one line (``base.failure``): requirements it cannot resolve beside cad's pins, with its
reason; a package its cache lacks where the network cannot be reached, by name.

**Its releases**: environments are tied to the release (cad is pinned in each). When one is made, the
environments of releases older than the one before the current go -- the current release's and the one
before's stay, the way back, as ``releases/`` keeps the release before (``kept``) -- and the one its local
packages' edit superseded (``_collect``), but one a process runs from, which goes at a later making. Those
of other sets stay until ``cad doctor --prune`` removes those unused for a week (``leftovers``, each use
marking its marker). Nothing is made ahead of a run: after an update, a new release's environments are
made as its runs ask for them, from uv's cache.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import ntpath
import os
import posixpath
import re
import stat
import sys
import threading
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from cad_server._internal import base

__all__ = ["SKIPPED", "Making", "Project", "Refused", "Spec", "admits", "ensure", "fingerprint", "fingerprints",
           "header", "integrations", "key", "kept", "local_package", "locked_cad", "making", "normalized",
           "pinned", "project", "refusal", "split", "tell", "uv_config", "uv_settings", "where"]
# uv's settings that say how it reaches an index, never what it resolves: a run that differs from the base's
# only by them still runs in the base, made with the engine's own.
HOW = frozenset({"UV_NATIVE_TLS", "UV_SYSTEM_CERTS", "UV_HTTP_TIMEOUT", "UV_KEYRING_PROVIDER", "UV_INSECURE_HOST"})

Refused = base.Refused
WINDOWS = os.name == "nt"
# What the environment is called in the lines said of it (``base.Recipe.what``).
WHAT = "the environment of the model's packages"
# The inline metadata block (PEP 723's reference expression): ``# /// TYPE`` to ``# ///``, each line between
# a comment.
_BLOCK = re.compile(r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$")
# A requirement's leading project name and extras, as PEP 508 spells them.
_NAMED = re.compile(r"(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)\s*(?P<extras>\[[^\]]*\])?\s*(?P<rest>.*)",
                    re.S)
# A version as PEP 440 spells one: its release, and a pre-release, a post-release or a development build of
# it (``3.11.0rc1``).
_VERSION = (r"(?P<release>[0-9]+(?:\.[0-9]+)*)"
            r"(?:[-_.]?(?P<pre>alpha|beta|preview|pre|rc|a|b|c)[-_.]?(?P<pre_n>[0-9]*))?"
            r"(?:[-_.]?(?P<post>post|rev|r)[-_.]?(?P<post_n>[0-9]*))?(?:[-_.]?(?P<dev>dev)[-_.]?(?P<dev_n>[0-9]*))?")
# A version specifier's clause, as ``requires-python`` writes one.
_CLAUSE = re.compile(rf"\s*(?P<operator>~=|===|==|!=|<=|>=|<|>)\s*(?P<version>{_VERSION})(?P<star>\.\*)?\s*", re.I)
# The pre-releases in PEP 440's order.
_PRE = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}
# A URL's scheme, and a Windows drive, which a scheme's spelling also matches.
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
_DRIVE = re.compile(r"[A-Za-z]:[\\/]")
# The folders a local package's fingerprint passes over (and each ``*.egg-info``): version control's, caches,
# build output and environments -- what no build of it reads.
SKIPPED = frozenset({".git", ".hg", ".svn", "__pycache__", "build", "dist", ".venv", "venv", "node_modules", ".tox",
                     ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache"})
# The files an editable folder is keyed by: its metadata, never its code, which it reads as it is.
METADATA = ("pyproject.toml", "setup.cfg", "setup.py")


# --- what the command and the script name ----------------------------------------------------------


def split(value: str) -> list[str]:
    """One ``--with`` value as uv reads it: requirements separated by commas -- but a comma inside an
    extras' brackets, or one a version operator follows (``pandas>=2,<3``), is the requirement's own."""
    parts, depth, current = [], 0, ""
    for char in value:
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        current += char
    parts.append(current)
    found: list[str] = []
    for part in (piece.strip() for piece in parts):
        if not part:
            continue
        if found and part[0] in "<>=!~":
            found[-1] = f"{found[-1]},{part}"
        else:
            found.append(part)
    return found


def header(script: Path) -> dict[str, Any]:
    """The script's inline metadata (PEP 723): its ``script`` block's ``dependencies`` (``[]`` with none)
    and ``requires-python`` (None); ``{}`` for a script with no block, or one that cannot be read.
    ``Refused`` in one line for two blocks, or a block that is no TOML or names them otherwise."""
    try:
        text = Path(script).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    blocks = [found for found in _BLOCK.finditer(text) if found.group("type") == "script"]
    if not blocks:
        return {}
    name = Path(script).name
    if len(blocks) > 1:
        raise Refused(f"{name} has more than one `# /// script` block: its packages are named in one")
    content = "".join(line[2:] if line.startswith("# ") else line[1:]
                      for line in blocks[0].group("content").splitlines(keepends=True))
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise Refused(f"{name}'s `# /// script` block is no TOML: {error}") from None
    dependencies = data.get("dependencies", [])
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        raise Refused(f"{name}'s `# /// script` block names its dependencies as a list of requirement strings")
    wanted = data.get("requires-python")
    if wanted is not None and not isinstance(wanted, str):
        raise Refused(f"{name}'s `# /// script` block names requires-python as a string: '>=3.12'")
    return {"dependencies": list(dependencies), "requires-python": wanted}


def admits(spec: str, version: str) -> bool | None:
    """Whether the Python ``version`` (``3.14.6``: its release, as pip reads an interpreter's) meets ``spec``
    (``>=3.11,<3.15``, ``>=3.11.0rc1``), each clause as PEP 440 reads it (``~=``, ``==`` and ``!=`` with
    ``.*``, the comparisons, a pre-release, post-release or development build in the version); None for a
    spec that does not read."""
    have = [int(part) for part in re.findall(r"\d+", version)[:3]]
    mine = _ordered(".".join(map(str, have)))
    for clause in spec.split(","):
        if not clause.strip():
            continue
        found = _CLAUSE.fullmatch(clause)
        if found is None:
            return None
        operator, text, star = found["operator"], found["version"], found["star"]
        release = [int(part) for part in found["release"].split(".")]
        plain = text == found["release"]  # no pre-release, post-release or development build
        if star:
            if operator not in ("==", "!=") or not plain:
                return None
            same = _padded(have, len(release))[:len(release)] == release
            admitted = same if operator == "==" else not same
        elif operator == "~=":
            if len(release) < 2:
                return None
            prefix = release[:-1]
            admitted = mine >= _ordered(text) and _padded(have, len(prefix))[:len(prefix)] == prefix
        else:
            theirs = _ordered(text)
            admitted = {"==": mine == theirs, "===": mine == theirs, "!=": mine != theirs, "<=": mine <= theirs,
                        ">=": mine >= theirs, "<": mine < theirs, ">": mine > theirs}[operator]
        if not admitted:
            return False
    return True


def _padded(numbers: list[int], size: int) -> list[int]:
    return numbers + [0] * (size - len(numbers))


def _ordered(version: str) -> tuple[Any, ...]:
    """A version (``_VERSION``) as PEP 440 orders it: ``3.11.dev1`` before ``3.11a1`` before ``3.11rc1``
    before ``3.11`` (``3.11.0``) before ``3.11.post1``."""
    found = re.fullmatch(_VERSION, version.strip().lower())
    assert found is not None
    numbers = [int(part) for part in found["release"].split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    post, dev = found["post"] is not None, found["dev"] is not None
    first, last = float("-inf"), float("inf")
    if found["pre"] is not None:
        pre: tuple[Any, ...] = (_PRE[found["pre"]], int(found["pre_n"] or 0))
    else:
        pre = (first,) if dev and not post else (last,)  # a release's own development builds come first
    return (tuple(numbers), pre, (int(found["post_n"] or 0),) if post else (first,),
            (int(found["dev_n"] or 0),) if dev else (last,))


def tell(given: list[str], script: str | None = None, named: list[str] | None = None) -> None:
    """The program ``cad run`` runs told how it named its environment (``places.RUN_WITH``, as JSON; with
    none, unset), normalized: the options and requirements its command line was given (``given``: each
    option one word, ``--python=3.13``, a requirement as it is), and the ``script`` whose inline metadata
    ``named`` the rest. What a document it builds names to build it again (``contract.interpreter``,
    ``models.Models.register``): the command line's, and the header's but for a model that script defines,
    whose header ``cad run`` reads again."""
    from cad.engine.places import RUN_WITH

    if given or named:
        os.environ[RUN_WITH] = json.dumps({"with": list(given), "script": script, "header": list(named or ())})
    else:
        os.environ.pop(RUN_WITH, None)


# --- cad's own requirement ---------------------------------------------------------------------------


def _name(requirement: str) -> str | None:
    """A requirement's project name, as PEP 503 normalizes it; None for a path or a URL."""
    if _path_like(requirement) or _url(requirement):
        return None
    found = _NAMED.fullmatch(requirement.strip())
    return re.sub(r"[-_.]+", "-", found["name"]).lower() if found else None


def pinned(requirement: str, release: str, where: str) -> tuple[str, ...] | None:
    """cad's extras a requirement names when it is cad's (``cad[kicad]``: ``("kicad",)``; a bare ``cad``:
    ``()``), else None. A requirement of cad's that pins another release than the device's ``release`` --
    any version specifier but ``==<release>``, or a direct reference -- is refused in one line naming the
    device's release (``where`` says whose requirement it is): a header names cad's extras, never its
    version, and the device decides it."""
    if _name(requirement) != base.LIBRARY:
        return None
    found = _NAMED.fullmatch(requirement.strip())
    assert found is not None
    extras = tuple(sorted({re.sub(r"[-_.]+", "-", extra.strip()).lower()
                           for extra in (found["extras"] or "[]")[1:-1].split(",") if extra.strip()}))
    rest = found["rest"].split(";", 1)[0].strip().replace(" ", "")
    if rest and rest not in (f"=={release}", f"==={release}"):
        raise Refused(f"{where} pins cad to {rest}, and this device runs cad {release}: drop the pin, as "
                      f"`cad[{','.join(extras) or base.EXTRA}]` -- a script names cad's integrations, never its "
                      "version, which the device decides")
    return extras


def integrations(*, header_cad: tuple[str, ...] | None, given_cad: Iterable[str] = (),
                 project_cad: Iterable[str] = (), scanned: Callable[[], set[str]] = set,
                 requirements: Iterable[str] = ()) -> tuple[str, ...]:
    """The integrations (cad's extras) an environment is made with, chosen here alone: a script's header
    that names ``cad[...]`` (``header_cad``) decides them outright, with no scan; else the program's own
    (``scanned``: ``cad_server._internal.scan``), what its project's requirement of cad names
    (``project_cad``), and those a requirement it names is a distribution of (``requirements``: ``--with
    build123d``, a header's ``build123d``), so cad's pins decide its version. ``--with cad[...]``
    (``given_cad``) adds to either. None found: the core alone. A resolution that pulls one in through
    another package adds it at the making (``_pulled``)."""
    from cad._internal.integrations import for_distribution

    if header_cad is not None:
        return tuple(sorted({*header_cad, *given_cad}))
    named = {key for requirement in requirements if (name := _name(requirement)) is not None
             and (key := for_distribution(name)) is not None}
    return tuple(sorted({*scanned(), *project_cad, *given_cad, *named}))


# --- a project ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Project:
    """A uv project a program runs in: its folder, its ``pyproject.toml``'s dependencies, and whether it is
    packaged (a ``[build-system]``: installed itself, editable, as ``uv run`` installs it; else its
    dependencies alone)."""

    root: str
    dependencies: tuple[str, ...]
    packaged: bool


def project(start: str | os.PathLike, explicit: str | None = None) -> Project | None:
    """The uv project at ``explicit`` (``--project``), else the nearest folder from ``start`` up holding a
    ``pyproject.toml`` with a ``[project]`` table, as uv discovers one; None where there is none.
    ``Refused`` in one line for a named folder that is no project, or a ``pyproject.toml`` that is no TOML."""
    folders = [Path(explicit)] if explicit else [Path(start), *Path(start).parents]
    for folder in folders:
        found = folder / "pyproject.toml"
        if not found.is_file():
            if explicit:
                raise Refused(f"--project {explicit}: no pyproject.toml there")
            continue
        try:
            data = tomllib.loads(found.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
            raise Refused(f"{found} is no TOML: {error}") from None
        table = data.get("project")
        if not isinstance(table, dict):
            if explicit:
                raise Refused(f"--project {explicit}: its pyproject.toml has no [project] table")
            continue
        dependencies = table.get("dependencies") or []
        if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
            raise Refused(f"{found} names its dependencies as a list of requirement strings")
        return Project(str(folder.resolve()), tuple(dependencies), isinstance(data.get("build-system"), dict))
    return None


# --- the key -----------------------------------------------------------------------------------------


def _url(text: str) -> bool:
    """Whether ``text`` is a URL -- an index's, a VCS's, a ``file:`` one -- rather than a path."""
    return _SCHEME.match(text) is not None and _DRIVE.match(text) is None


def _path_like(text: str) -> bool:
    """Whether a requirement is a local path -- a project folder, a wheel or an archive -- rather than a
    named one or a URL: it starts as a path does (``./``, ``../``, ``/``, ``~``, ``C:\\``, ``\\\\server``), or
    is a file of a distribution's kind with no name before an ``@``."""
    if _url(text):
        return False
    return (text.startswith((".", "/", "~", "\\")) or _DRIVE.match(text) is not None
            or ("@" not in text and text.lower().endswith((".whl", ".tar.gz", ".zip"))))


def absolute(path: str, folder: str) -> str:
    """``path`` absolute against ``folder``, as this platform spells a path."""
    paths = ntpath if WINDOWS else posixpath
    return paths.normpath(paths.join(folder, paths.expanduser(path)))


def _file_path(url: str) -> str:
    """The path a ``file:`` URL names, its escapes undone: ``file:./x`` and ``file:x`` relative,
    ``file:///abs`` (on Windows ``file:///C:/abs``) absolute, ``file://host/share/x`` a share's."""
    import urllib.parse

    rest = url[len("file:"):]
    if not rest.startswith("//"):
        return urllib.parse.unquote(rest)
    host, _slash, path = rest[2:].partition("/")
    path = urllib.parse.unquote("/" + path)
    if WINDOWS and re.match(r"/[A-Za-z]:", path):
        path = path[1:]
    return f"//{host}{path}" if host and host.lower() != "localhost" else path


def refusal(requirement: str) -> str | None:
    """Why ``requirement`` is none uv may be handed as one -- an option of its own (``--index-url=...``) --
    or None."""
    text = requirement.strip()
    return (f"{text} is no requirement: name a package, a pin, extras, or a local path or wheel"
            if text.startswith("-") else None)


def normalized(requirement: str, folder: str) -> str:
    """A requirement as its environment's key has it, and as ``cad run --with`` is said again: a local path
    -- a ``file:`` URL's too, and a name's direct reference to one (``gears @ ./vendor/gears``,
    ``gears @ file:./vendor/gears``) -- absolute against ``folder`` (``--with``'s, the working folder; a
    header's, its script's), as this platform spells a path, so it keys and resolves the same from any
    process; a named one with its project's name normalized (PEP 503: lower case, each run of ``-``, ``_``
    and ``.`` one ``-``), its extras sorted, and no spaces in its version specifier; any other URL as
    written. ``Refused`` for an option of uv's (``refusal``), which no requirement is."""
    text = requirement.strip()
    refused = refusal(text)
    if refused is not None:
        raise Refused(refused)
    if text.lower().startswith("file:"):
        return absolute(_file_path(text), folder)
    if _path_like(text):
        return absolute(text, folder)
    found = _NAMED.fullmatch(text)
    if found is None:
        return text
    name = re.sub(r"[-_.]+", "-", found["name"]).lower()
    extras = ""
    if found["extras"]:
        names = sorted({re.sub(r"[-_.]+", "-", extra.strip()).lower()
                        for extra in found["extras"][1:-1].split(",") if extra.strip()})
        extras = f"[{','.join(names)}]" if names else ""
    rest = found["rest"].strip()
    if rest.startswith("@"):  # a direct reference: a local one's path absolute, a URL as written
        reference, *marker = re.split(r"\s+;", rest[1:].strip(), maxsplit=1)
        reference = reference.strip()
        if reference.lower().startswith("file:"):
            reference = absolute(_file_path(reference), folder)
        elif not _url(reference):
            reference = absolute(reference, folder)
        return f"{name}{extras} @ {reference}" + (f" ; {marker[0].strip()}" if marker else "")
    specifier, marked, marker = rest.partition(";")
    specifier = re.sub(r"\s+", "", specifier)
    return f"{name}{extras}{specifier}" + (f"; {marker.strip()}" if marked else "")


def local_package(requirement: str) -> str | None:
    """The local package a requirement (normalized) installs -- a project folder, a wheel or an archive, by
    its path or a name's direct reference to it -- or None for one an index or a URL serves."""
    if _path_like(requirement):
        return requirement
    found = _NAMED.fullmatch(requirement)
    rest = found["rest"].strip() if found is not None else ""
    if rest.startswith("@"):
        reference = re.split(r"\s+;", rest[1:].strip(), maxsplit=1)[0].strip()
        if not _url(reference):
            return reference
    return None


def fingerprint(path: str, metadata: bool = False) -> str:
    """What a local package is now, cheaply: a file's (a wheel, an archive, a requirements file) size and
    modification time; a project folder's files' paths in it, sizes and modification times (``mtime_ns``),
    passing over the folders no build reads (``SKIPPED``, and each ``*.egg-info``) -- with ``metadata`` (an
    editable folder, whose code is read as it is) its metadata files' alone (``METADATA``). ``missing`` where
    there is none, which uv says."""
    try:
        found = os.stat(path)
    except OSError:
        return "missing"
    if not stat.S_ISDIR(found.st_mode):
        return f"{found.st_size}:{found.st_mtime_ns}"
    digest = hashlib.sha256()
    if metadata:
        for name in METADATA:
            digest.update(f"{name}\0{fingerprint(os.path.join(path, name))}\n".encode("utf-8"))
        return digest.hexdigest()[:16]
    for folder, folders, files in os.walk(path):
        folders[:] = sorted(name for name in folders if name not in SKIPPED and not name.endswith(".egg-info"))
        for name in sorted(files):
            each = os.path.join(folder, name)
            try:
                seen = os.stat(each)
            except OSError:
                continue
            relative = os.path.relpath(each, path).replace(os.sep, "/")
            digest.update(f"{relative}\0{seen.st_size}\0{seen.st_mtime_ns}\n".encode("utf-8", "surrogateescape"))
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class Spec:
    """What one environment holds (see the module), normalized: cad's ``integrations`` (its extras, sorted),
    the ``requirements`` beside it (sorted, each once), the folders installed editable (``editable``: an
    editable folder with its extras, ``/w/project[x]``), the requirements files (``files``), the options of
    uv's it is made with (``options``, as given, in order), uv's settings from the caller's environment
    (``environment``: ``NAME=value``, sorted), the uv configuration files it reads (``config``), a project's
    lock (``lock``: its ``uv.lock``) and the options its export takes (``lock_options``: ``--frozen``,
    ``--locked``, the extras and groups), the Python it is made on (``python``: uv's request; None, the
    engine's) and the options uv's ``venv`` takes for it (``python_options``). And what only its making
    reads, which no key holds: ``transient`` (``--upgrade``, ``--refresh``, ``--offline``, the verbosity),
    and the folder uv runs in (``folder``: the project's, or the run's)."""

    integrations: tuple[str, ...] = (base.EXTRA,)
    requirements: tuple[str, ...] = ()
    editable: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    python: str | None = None
    python_options: tuple[str, ...] = ()
    environment: tuple[str, ...] = ()
    config: tuple[str, ...] = ()
    lock: str | None = None
    lock_options: tuple[str, ...] = ()
    transient: tuple[str, ...] = field(default=(), compare=False)
    folder: str | None = field(default=None, compare=False)

    def default(self) -> bool:
        """Whether it is the installation's base: the build123d integration alone, on the engine's Python, with
        no setting of uv's but those that say how it reaches an index (``HOW``)."""
        what = tuple(item for item in self.environment if item.partition("=")[0] not in HOW)
        return dataclasses.replace(self, environment=what) == Spec()

    def keyed(self) -> dict[str, Any]:
        """What its key and its marker hold of it: all but what only its making reads."""
        found = dataclasses.asdict(self)
        found.pop("transient")
        found.pop("folder")
        return {name: list(value) if isinstance(value, tuple) else value for name, value in found.items()}

    def as_dict(self) -> dict[str, Any]:
        return {**self.keyed(), "transient": list(self.transient), "folder": self.folder}

    def settings(self) -> tuple[tuple[str, str], ...]:
        """uv's settings from the caller's environment, as ``base.make`` runs uv with them."""
        return tuple((name, value) for name, _eq, value in (item.partition("=") for item in self.environment))

    @classmethod
    def from_dict(cls, given: Any) -> "Spec":
        """A spec as the door carries it; ``Refused`` for one that is no spec: a key it does not hold, a value
        of another kind, a requirement that is an option of uv's or an option that is none."""
        if not isinstance(given, dict) or not set(given) <= {item.name for item in dataclasses.fields(cls)}:
            raise Refused("no environment's spec: unknown keys")
        values: dict[str, Any] = {}
        for item in dataclasses.fields(cls):
            if item.name not in given:
                continue
            value = given[item.name]
            if item.name in ("python", "lock", "folder"):
                if value is not None and not isinstance(value, str):
                    raise Refused(f"no environment's spec: {item.name} is a string")
                values[item.name] = value
                continue
            if not isinstance(value, list) or not all(isinstance(each, str) for each in value):
                raise Refused(f"no environment's spec: {item.name} is a list of strings")
            values[item.name] = tuple(value)
        found = cls(**values)
        for requirement in (*found.requirements, *found.editable, *found.files):
            refused = refusal(requirement)
            if refused is not None:
                raise Refused(refused)
        for option in (*found.options, *found.python_options, *found.transient, *found.lock_options):
            if not option.startswith("-"):
                raise Refused(f"{option} is no option of uv's")
        for setting in found.environment:
            if setting.partition("=")[0] not in base.UV_SETTINGS:
                raise Refused(f"{setting.partition('=')[0]} is no setting of uv's cad run hands on")
        return found


def _locals(spec: Spec) -> dict[str, tuple[str, str]]:
    """Each local thing a spec reads, by its path, and how it is keyed: ``tree`` (its files' sizes and times),
    ``metadata`` (an editable folder's metadata files), ``content`` (a lock, a project's metadata, a uv
    configuration: its bytes)."""
    found: dict[str, tuple[str, str]] = {}
    for requirement in spec.requirements:
        path = local_package(requirement)
        if path is not None:
            found[path] = (path, "tree")
    for folder in spec.editable:
        path = re.sub(r"\[[^\]]*\]$", "", folder)
        found[path] = (path, "metadata")
    for path in spec.files:
        found[path] = (path, "tree")
    for path in spec.config:
        found[path] = (path, "content")
    if spec.lock:
        found[spec.lock] = (spec.lock, "content")
        project = str(Path(spec.lock).parent / "pyproject.toml")
        found[project] = (project, "content")
    return found


def _content(path: str) -> str:
    """A file's bytes, digested; ``missing`` where there is none."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]
    except OSError:
        return "missing"


def fingerprints(spec: Spec | list[str]) -> dict[str, str]:
    """Each local package's, editable folder's, requirements file's, lock's and uv configuration's
    fingerprint (``fingerprint``, ``_content``), by its path; a list of requirements is a spec of them."""
    spec = spec if isinstance(spec, Spec) else Spec(requirements=tuple(spec))
    return {path: _content(where) if mode == "content" else fingerprint(where, mode == "metadata")
            for path, (where, mode) in _locals(spec).items()}


def uv_settings(environ: dict[str, str] | None = None) -> tuple[str, ...]:
    """uv's resolution settings in an environment (``base.UV_SETTINGS``), as ``NAME=value``, sorted: those
    ``cad run`` hands the making from its caller's."""
    environ = os.environ if environ is None else environ
    return tuple(sorted(f"{name}={value}" for name, value in environ.items() if name in base.UV_SETTINGS))


def uv_config(folder: str | os.PathLike, environ: dict[str, str] | None = None) -> tuple[str, ...]:
    """The uv configuration a run in ``folder`` reads, as uv finds it: the file ``UV_CONFIG_FILE`` names, and
    the nearest folder from ``folder`` up holding a ``uv.toml`` (which wins) or a ``pyproject.toml`` with a
    ``[tool.uv]`` table -- none with ``UV_NO_CONFIG``. The user's own configuration is the engine's."""
    environ = os.environ if environ is None else environ
    if environ.get("UV_NO_CONFIG", "").strip() not in ("", "0", "false"):
        return ()
    found: list[str] = []
    named = environ.get("UV_CONFIG_FILE", "").strip()
    if named:
        found.append(os.path.abspath(named))
    start = Path(folder).resolve()
    for each in (start, *start.parents):
        if (each / "uv.toml").is_file():
            found.append(str(each / "uv.toml"))
            break
        project = each / "pyproject.toml"
        if project.is_file():
            try:
                table = tomllib.loads(project.read_text(encoding="utf-8")).get("tool", {})
            except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
                table = {}
            if isinstance(table, dict) and isinstance(table.get("uv"), dict):
                found.append(str(project))
                break
    return tuple(dict.fromkeys(found))


def locked_cad(lock: str | os.PathLike, release: str) -> None:
    """A project's lock that pins cad to another release than the device's, refused in one line, as a header
    is (``pinned``); one of the device's release, or none, passes."""
    try:
        data = tomllib.loads(Path(lock).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise Refused(f"{lock} is no lock uv reads: {error}") from None
    for package in data.get("package") or []:
        if isinstance(package, dict) and _name(str(package.get("name") or "")) == base.LIBRARY:
            version = str(package.get("version") or "")
            if version:
                pinned(f"{base.LIBRARY}=={version}", release, str(lock))


def key(installation: base.Installation, spec: Spec | list[str], prints: dict[str, str] | None = None) -> str:
    """The environment's key: its installation's base's inputs (the release, its source, its Python and
    the architecture among them), the spec (``Spec.keyed``), and what each local thing among it is now
    (``prints``, ``fingerprints`` by default): an edit to one is another environment. A list of
    requirements is a spec of them, with the build123d integration."""
    spec = spec if isinstance(spec, Spec) else Spec(requirements=tuple(sorted(set(spec))))
    material = json.dumps({"base": base._inputs(installation), "spec": spec.keyed(),
                           "local": fingerprints(spec) if prints is None else prints}, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def where(installation: base.Installation, spec: Spec | list[str], prints: dict[str, str] | None = None) -> Path:
    """The folder of the environment of ``spec``, made or not: beside the base."""
    from cad.engine.places import cache_dir

    return cache_dir() / base.BASE / key(installation, spec, prints)


# --- making it ---------------------------------------------------------------------------------------


def _complete(env: Path, spec: Spec) -> dict[str, Any] | None:
    """The environment's marker when it is complete (``base.complete``) and holds ``spec``."""
    marker = base.complete(env)
    return marker if marker is not None and marker.get("spec") == spec.keyed() else None


def ensure(installation: base.Installation, spec: Spec | list[str], *, told: Callable[[str], None],
           engine: bool = False) -> base.Environment:
    """The environment of ``spec`` beside ``installation``'s base: made first when it is not complete -- by
    the device's engine with ``engine`` (``cad run``) when one runs, its lines said to ``told``, else here.
    ``Refused`` in one line when uv cannot make it. A list of requirements is a spec of them."""
    spec = spec if isinstance(spec, Spec) else Spec(requirements=tuple(sorted(set(spec))))
    prints = fingerprints(spec)
    env = where(installation, spec, prints)
    marker = _complete(env, spec)
    if marker is not None:
        _used(env)
        return base._found(env, marker)
    if engine:
        marker = _by_the_engine(env, spec, told)
        if marker is not None:
            return base._found(env, marker)
    return base._found(env, _make(env, installation, spec, prints, told))


def marker(env: base.Environment) -> dict[str, Any]:
    """The marker of an environment ``ensure`` gave (``{}`` for the installation's own)."""
    return base.complete(Path(env.prefix)) or {}


def _used(env: Path) -> None:
    """The environment's marker marked used now (its modification time), which ``cad doctor`` reads: one
    unused for a week is a leftover (``leftovers.package_environments``). Where the cache folder cannot be
    written (an agent's sandbox), nothing is marked."""
    try:
        os.utime(env / base.MARKER)
    except OSError:
        pass


def _by_the_engine(env: Path, spec: Spec, told: Callable[[str], None]) -> dict[str, Any] | None:
    """The environment made by the device's engine when one runs and it is this installation's (``{"op":
    "base", "key", "spec"}``, ``making``), its lines said to ``told``; None when none answers, or one of
    another installation's, which this process makes it for. ``Refused`` in the engine's words."""
    from cad.engine import client

    try:
        answer = client.request({"op": "base", "key": env.name, "spec": spec.as_dict(),
                                 "with": list(spec.requirements)}, start=False,
                                on_log=lambda frame: told(str(frame.get("log", ""))))
    except (ConnectionError, OSError, ValueError):
        return None
    if not answer or answer.get("base") is not True:
        return None
    if answer.get("failed"):
        raise Refused(str(answer["failed"]))
    return _complete(env, spec)


def _cad(installation: base.Installation, extras: Iterable[str]) -> tuple[str, ...]:
    """cad's own requirement, pinned at the installation's release (or its source tree or wheel), with
    ``extras``."""
    return tuple(installation.requirement(tuple(sorted(set(extras)))))


def _options(spec: Spec, extras: Iterable[str]) -> tuple[str, ...]:
    """What uv is handed beside the requirements: the spec's options and making's, and the indexes and
    folders of wheels of its integrations (``cad._internal.integrations``: a hook, none today)."""
    from cad._internal.integrations import INTEGRATIONS

    found: list[str] = []
    for extra in sorted(set(extras)):
        known = INTEGRATIONS.get(extra)
        for index in known.indexes if known else ():
            found += ["--index", index]
        for links in known.find_links if known else ():
            found += ["--find-links", links]
    return (*found, *spec.options, *spec.transient)


def _named(spec: Spec) -> str:
    """The spec's own packages in words, for the lines said of its making."""
    every = [*spec.requirements, *(f"-e {each}" for each in spec.editable), *(f"-r {each}" for each in spec.files),
             *([f"the locked set of {spec.lock}"] if spec.lock else [])]
    return ", ".join(every) or "nothing more"


def _distributions(path: list[str], prefix: Path) -> set[str]:
    """The distributions installed in the environment at ``prefix`` (its import path ``path``), by their
    names as PEP 503 normalizes them."""
    found: set[str] = set()
    inside = os.path.normcase(os.path.realpath(prefix))
    for entry in path:
        if not os.path.normcase(os.path.realpath(entry)).startswith(inside):
            continue
        try:
            names = os.listdir(entry)
        except OSError:
            continue
        for name in names:
            if name.endswith(".dist-info"):
                found.add(re.sub(r"[-_.]+", "-", name[:-len(".dist-info")].rsplit("-", 1)[0]).lower())
    return found


def _pulled(env: Path, extras: Iterable[str]) -> list[str]:
    """The integrations the environment just installed at ``env`` holds a distribution of but was not given
    (``cad._internal.integrations.for_distribution``): pulled in through another package."""
    from cad._internal.integrations import for_distribution

    given = set(extras)
    return sorted({key for name in _distributions(base._path(env), env)
                   if (key := for_distribution(name)) is not None and key not in given})


def recipe(installation: base.Installation, spec: Spec | list[str], changed: list[str] | None = None,
           made: dict[str, Any] | None = None) -> base.Recipe:
    """The environment's recipe: cad pinned with its integrations, and the spec's packages and options,
    resolved together on its Python. ``changed``: the local packages whose edit makes it anew, which its
    line names. Its revision adds an integration a resolution pulled in (``_pulled``), and says the
    integrations it was made with in ``made`` (``integrations``)."""
    spec = spec if isinstance(spec, Spec) else Spec(requirements=tuple(sorted(set(spec))))
    named = _named(spec)
    extras = ",".join(spec.integrations)
    kernel = f"{base.LIBRARY}[{extras}] {installation.release}" if extras else f"{base.LIBRARY} {installation.release}"
    making = (f"making {WHAT} again, as {', '.join(changed)} changed: {named} beside {kernel}" if changed
              else f"making {WHAT}, once: {named} beside {kernel}")
    rest = (*spec.requirements, *(word for each in spec.editable for word in ("-e", each)),
            *(word for each in spec.files for word in ("-r", each)))

    def revise(env: Path) -> tuple[tuple[str, ...], str] | None:
        pulled = _pulled(env, spec.integrations)
        if not pulled:
            return None
        every = sorted({*spec.integrations, *pulled})
        if made is not None:
            made["integrations"] = every
        return ((*_cad(installation, every), *rest),
                f"{', '.join(pulled)} came in through another package: resolving again with "
                f"{base.LIBRARY}[{','.join(every)}] {installation.release}, so cad's pins decide it")

    return base.Recipe(what=WHAT, python=spec.python or installation.executable,
                       requirement=(*_cad(installation, spec.integrations), *rest), release=installation.release,
                       source=installation.source, making=making, downloading=f"downloading what {named} needs, once",
                       unsatisfiable=f"{named} cannot be resolved beside {kernel}",
                       options=_options(spec, spec.integrations), venv_options=spec.python_options, revise=revise,
                       environment=spec.settings(), folder=spec.folder,
                       before=(lambda env: _export(env, spec, installation.release)) if spec.lock else None)


# The file a project's lock is exported to, in the environment it makes.
EXPORTED = "cad-lock-requirements.txt"


def _export(env: Path, spec: Spec, release: str) -> tuple[str, ...]:
    """A project's lock exported by uv as requirements (``uv export --format requirements-txt``, no hashes:
    cad's pin has none), in the project's folder with the caller's uv settings, the options it was given
    (``--frozen``: the lock as it is; ``--locked``: refused when it is out of date; neither: as ``uv run``
    takes it, made current first where it is not) -- from uv's cache first, then the network --; cad's own
    line taken out for the pin, after it is checked to be the device's release. What ``uv pip install`` is
    handed for it: ``-r`` and the file, in the environment. ``Refused`` in one line, with uv's reason."""
    assert spec.lock is not None
    root = Path(spec.lock).parent
    command = [base.find_uv(), "export", "--project", str(root), "--format", "requirements-txt", "--no-hashes",
               "--no-header", "--no-annotate", *spec.lock_options]
    settings = spec.settings()
    frozen = "--frozen" in spec.lock_options
    result = base._uv(command if frozen else [*command, "--offline"], root, settings)
    if result.returncode != 0 and not frozen:
        result = base._uv(command, root, settings)
    if result.returncode != 0:
        raise Refused(f"uv could not export {spec.lock}: {base._last(result.stderr or result.stdout)}")
    kept = []
    for line in result.stdout.splitlines():
        if _name(line.strip()) == base.LIBRARY:
            pinned(line.strip().split(";", 1)[0], release, spec.lock)
            continue
        kept.append(line)
    path = env / EXPORTED
    try:
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    except OSError as error:
        raise Refused(f"cannot write {path}: {error.strerror or error}") from None
    return ("-r", str(path))


def _make(env: Path, installation: base.Installation, spec: Spec, prints: dict[str, str],
          told: Callable[[str], None]) -> dict[str, Any]:
    """The environment at ``env`` made (``base.make``), its marker naming its installation, as the base's
    does, the requirements it holds (``with``), its spec, the integrations it was made with, its Python's
    version and its local things' fingerprints (``local``), its line naming those an edit made it anew for
    (``_changed``); then the environments of releases before the one before, and the one it supersedes,
    collected."""
    inputs = base._inputs(installation)
    made: dict[str, Any] = {"integrations": list(spec.integrations)}

    def finish(steps: list[list[str]], seconds: float) -> dict[str, Any]:
        path, version = base._probe(env)
        return {"schema": base.SCHEMA, "key": env.name, "inputs": inputs,
                "installation": dataclasses.asdict(installation), "with": list(spec.requirements),
                "spec": spec.keyed(), "integrations": made["integrations"], "local": prints,
                "path": path, "python_version": version, "commands": steps, "seconds": round(seconds, 2),
                "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    changed = _changed(env.parent, inputs, spec, prints)
    marker = base.make(env, recipe(installation, spec, changed, made), told, finish=finish, marker=base.MARKER,
                       done=lambda folder: _complete(folder, spec))
    _collect(env.parent, kept(env.parent, installation.release), made=env, spec=spec, inputs=inputs)
    return marker


def _changed(folder: Path, inputs: dict[str, Any], spec: Spec, prints: dict[str, str]) -> list[str]:
    """The local packages an edit makes the environment of ``spec`` anew for: those a complete one beside
    it, of the same installation's base and spec, knew otherwise."""
    changed: set[str] = set()
    try:
        entries = [Path(entry.path) for entry in os.scandir(folder) if entry.is_dir(follow_symlinks=False)]
    except OSError:
        return []
    for env in entries:
        marker = base.complete(env)
        if marker is None or marker.get("spec") != spec.keyed() or marker.get("inputs") != inputs:
            continue
        before = marker.get("local") if isinstance(marker.get("local"), dict) else {}
        changed.update(path for path, now in prints.items() if before.get(path) != now)
    return sorted(changed)


def _releases(folder: Path) -> set[str]:
    """The releases the environments of models' packages in ``folder`` are of, as their markers say."""
    found: set[str] = set()
    try:
        entries = [Path(entry.path) for entry in os.scandir(folder) if entry.is_dir(follow_symlinks=False)]
    except OSError:
        return found
    for env in entries:
        marker = base.complete(env)
        release = ((marker or {}).get("inputs") or {}).get("release")
        if marker is not None and isinstance(marker.get("with"), list) and isinstance(release, str):
            found.add(release)
    return found


def kept(folder: Path, current: str) -> set[str]:
    """The releases whose environments of models' packages stay: the current one, and the one before it --
    the release the last update switched from, where that switch went to ``current``
    (``cad_server._internal.switch.last``), else the newest of the environments' releases older than
    ``current`` (as PEP 440 orders them) -- the way back, as ``releases.collect`` keeps it."""
    from cad.engine.contract import _order

    try:
        from cad_server._internal.switch import last

        switched = last() or {}
    except Exception:  # noqa: BLE001 - no record: the order of the releases says the one before
        switched = {}
    if switched.get("to") == current and switched.get("ok") and isinstance(switched.get("from"), str):
        return {current, switched["from"]}
    mine = _order(current)
    older = [(_order(release), release) for release in _releases(folder) if release != current]
    older = [(order, release) for order, release in older if order is not None and mine is not None and order < mine]
    return {current, *([max(older)[1]] if older else [])}


def _collect(folder: Path, keep: set[str], made: Path | None = None, spec: Spec | None = None,
             inputs: dict[str, Any] | None = None) -> list[str]:
    """The environments of a model's packages in ``folder`` of releases other than ``keep`` (``kept``: the
    current one and the one before it) removed, and those the one just ``made`` supersedes -- of its
    installation's base (``inputs``) and ``spec``, a local package since edited --, but one a process runs
    from (``releases.running``), which goes at a later making: the paths removed. The bases are their
    releases' to remove (``releases.collect``)."""
    from cad_server._internal.releases import running

    removed = []
    try:
        entries = [Path(entry.path) for entry in os.scandir(folder) if entry.is_dir(follow_symlinks=False)]
    except OSError:
        return removed
    for env in entries:
        marker = base.complete(env) if env != made else None
        if marker is None or not isinstance(marker.get("with"), list):
            continue
        other = (marker.get("inputs") or {}).get("release") not in keep
        superseded = (made is not None and spec is not None and marker.get("spec") == spec.keyed()
                      and marker.get("inputs") == inputs)
        if not (other or superseded) or running(env):
            continue
        try:
            base._remove(env)
        except Refused:
            continue  # held by a process (Windows): a later making takes it
        removed.append(str(env))
    return removed


class Making(base.Making):
    """The environment of one spec made in the engine's background, for whoever asks (``Daemon.base``'s
    ``spec``): ``base.Making``'s, of that environment."""

    def __init__(self, spec: Spec) -> None:
        super().__init__()
        self.spec = spec

    def key(self) -> str | None:
        return key(base.Installation.here(), self.spec)

    def start(self) -> bool:
        with self.changed:
            if self.state == "making":
                return True
            installation = base.Installation.here()
            if _complete(where(installation, self.spec), self.spec) is not None:
                return False
            self.state, self.lines, self.error, self.since = "making", [], None, time.time()
        threading.Thread(target=self._make, name="cad-extras", daemon=True).start()
        return True

    def _make(self) -> None:
        try:
            ensure(base.Installation.here(), self.spec, told=self._said)
            state, error = "made", None
        except Refused as refused:
            state, error = "failed", str(refused)
        except Exception as failure:  # noqa: BLE001 - said, and the next asker tries again
            state, error = "failed", f"{type(failure).__name__}: {failure}"
        if error is not None:
            print(f"cad: {error}", file=sys.stderr, flush=True)  # the engine's log
        with self.changed:
            self.state, self.error = state, error
            self.changed.notify_all()


# The engine's makings of models' environments, one per key (``making``).
_MAKINGS: dict[str, Making] = {}
_MAKINGS_LOCK = threading.Lock()


def making(spec: Spec | dict[str, Any] | list[str]) -> Making:
    """The engine's making of the environment of ``spec`` (as the door carries it, or a list of requirements
    normalized): one per environment. ``Refused`` for one that is no spec (``Spec.from_dict``): only the door
    reaches this, and uv is handed options only as options, requirements only as requirements."""
    if isinstance(spec, list):
        for requirement in spec:
            refused = refusal(requirement)
            if refused is not None:
                raise Refused(refused)
        spec = Spec(requirements=tuple(sorted(set(spec))))
    elif isinstance(spec, dict):
        spec = Spec.from_dict(spec)
    found = Making(spec)
    named = found.key() or ""
    with _MAKINGS_LOCK:
        return _MAKINGS.setdefault(named, found)
