"""A model's own packages: the environment ``cad run --with`` and a script's inline metadata make, beside
the base.

A model that needs a package the base lacks (it holds ``cad[build123d]`` alone) names it, in its script's
inline metadata (PEP 723)::

    # /// script
    # dependencies = ["pandas"]
    # ///

or, for a one-off, on the command line: ``cad run --with pandas model.py`` (``--with`` repeats, and takes a
comma-separated list, as ``uv run --with`` does). ``cad run`` reads both (``arguments``, ``header``) and runs
the script in an environment that holds ``cad[build123d]`` at the installation's own release and those
packages, resolved together by uv with the base's link mode, find-links and index settings (``ensure``): made
once, by the device's engine when one runs -- outside any sandbox, its lines followed as it makes it -- else
here, and used again after. It lives in the cache folder beside the base (``base/<key>``: the key digests the
installation's base's inputs, its release among them, the requirements normalized and sorted
(``normalized``: a local package's path, or a name's direct reference to one, absolute), and what each local
package is now (``fingerprint``: its files' paths, sizes and modification times), so an edit to one makes
the environment anew, said in the line that makes it), its marker naming the installation and the
requirements (``with``), so a process there reaches its installation's engine as a process in the base does,
and names its Python in its orders (``cad.engine.contract.interpreter``): the engine builds the script in a
warm worker of it, of one release with the engine, so no update notice is said. A header's
``requires-python`` the server's Python does not meet is refused in one line. With no packages named, ``cad
run`` runs the base, as ever.

When one is made, the environments of other releases go, and the one its local packages' edit superseded
(``_collect``), but one a process runs from, which goes at a later making. Those of other requirements stay,
one per set a model named, until ``cad doctor --prune`` removes those unused for a week (``leftovers``,
each use marking its marker) or a release change does. What uv cannot do is said in one line
(``base.failure``): requirements it cannot resolve beside the kernel's pins, with its reason; a package its
cache lacks where the network cannot be reached, by name.
"""

from __future__ import annotations

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
from pathlib import Path
from typing import Any, Callable

from cad_server._internal import base

__all__ = ["SKIPPED", "Making", "Refused", "admits", "arguments", "ensure", "fingerprint", "fingerprints", "header",
           "key", "local_package", "making", "normalized", "refusal", "split", "tell", "where"]

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


def arguments(argv: list[str]) -> tuple[list[str], list[str]]:
    """``cad run``'s own options, ahead of what it runs: each ``--with REQ`` (``--with=REQ``) split into its
    requirements (``split``), and the rest -- ``SCRIPT.py [ARGS]``, ``-m MODULE [ARGS]``, ``-c CODE`` -- as
    given; ``--`` ends the options. ``Refused`` for a ``--with`` with no requirement."""
    found: list[str] = []
    rest = list(argv)
    while rest:
        head = rest[0]
        if head == "--with" or head.startswith("--with="):
            value = head[len("--with="):] if head.startswith("--with=") else (rest[1] if len(rest) > 1 else "")
            named = split(value)
            if not named:
                raise Refused("--with takes a requirement: a name, a pin, extras, or a local path or wheel")
            found += named
            rest = rest[1:] if head.startswith("--with=") else rest[2:]
        elif head == "--":
            return found, rest[1:]
        else:
            break
    return found, rest


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
    """The program ``cad run`` runs told how it named the packages of its environment (``places.RUN_WITH``,
    as JSON; with none, unset), normalized: the requirements its ``--with`` was given, and the ``script``
    whose inline metadata ``named`` the rest. What a document it builds names to build it again
    (``contract.interpreter``, ``models.Models.register``): ``--with``'s, and the header's but for a model
    that script defines, whose header ``cad run`` reads again."""
    from cad.engine.places import RUN_WITH

    if given or named:
        os.environ[RUN_WITH] = json.dumps({"with": list(given), "script": script, "header": list(named or ())})
    else:
        os.environ.pop(RUN_WITH, None)


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


def _absolute(path: str, folder: str) -> str:
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
    """Why ``requirement`` is none uv may be handed -- an option of its own (``--index-url=...``) -- or None."""
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
        return _absolute(_file_path(text), folder)
    if _path_like(text):
        return _absolute(text, folder)
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
            reference = _absolute(_file_path(reference), folder)
        elif not _url(reference):
            reference = _absolute(reference, folder)
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


def fingerprint(path: str) -> str:
    """What a local package is now, cheaply: a wheel's or an archive's size and modification time; a project
    folder's files' paths in it, sizes and modification times (``mtime_ns``), passing over the folders no
    build reads (``SKIPPED``, and each ``*.egg-info``). ``missing`` where there is none, which uv says."""
    try:
        found = os.stat(path)
    except OSError:
        return "missing"
    if not stat.S_ISDIR(found.st_mode):
        return f"{found.st_size}:{found.st_mtime_ns}"
    digest = hashlib.sha256()
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


def fingerprints(requirements: list[str]) -> dict[str, str]:
    """Each local package's fingerprint (``fingerprint``), by its path (``local_package``)."""
    found: dict[str, str] = {}
    for requirement in requirements:
        path = local_package(requirement)
        if path is not None:
            found[path] = fingerprint(path)
    return found


def key(installation: base.Installation, requirements: list[str], prints: dict[str, str] | None = None) -> str:
    """The environment's key: its installation's base's inputs (the release, its source, its Python and
    the architecture among them), the requirements, normalized (``normalized``), each once and sorted, and
    what each local package among them is now (``prints``, ``fingerprints`` by default): an edit to one is
    another environment."""
    requirements = sorted(set(requirements))
    material = json.dumps({"base": base._inputs(installation), "with": requirements,
                           "local": fingerprints(requirements) if prints is None else prints}, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def where(installation: base.Installation, requirements: list[str], prints: dict[str, str] | None = None) -> Path:
    """The folder of the environment of ``requirements`` (normalized), made or not: beside the base."""
    from cad.engine.places import cache_dir

    return cache_dir() / base.BASE / key(installation, requirements, prints)


# --- making it ---------------------------------------------------------------------------------------


def _complete(env: Path, requirements: list[str]) -> dict[str, Any] | None:
    """The environment's marker when it is complete (``base.complete``) and holds ``requirements``."""
    marker = base.complete(env)
    return marker if marker is not None and marker.get("with") == sorted(set(requirements)) else None


def ensure(installation: base.Installation, requirements: list[str], *, told: Callable[[str], None],
           engine: bool = False) -> base.Environment:
    """The environment of ``requirements`` (normalized) beside ``installation``'s base: made first when it
    is not complete -- by the device's engine with ``engine`` (``cad run``) when one runs, its lines said to
    ``told``, else here. ``Refused`` in one line when uv cannot make it."""
    requirements = sorted(set(requirements))
    prints = fingerprints(requirements)
    env = where(installation, requirements, prints)
    marker = _complete(env, requirements)
    if marker is not None:
        _used(env)
        return base._found(env, marker)
    if engine:
        marker = _by_the_engine(env, requirements, told)
        if marker is not None:
            return base._found(env, marker)
    return base._found(env, _make(env, installation, requirements, prints, told))


def _used(env: Path) -> None:
    """The environment's marker marked used now (its modification time), which ``cad doctor`` reads: one
    unused for a week is a leftover (``leftovers.package_environments``). Where the cache folder cannot be
    written (an agent's sandbox), nothing is marked."""
    try:
        os.utime(env / base.MARKER)
    except OSError:
        pass


def _by_the_engine(env: Path, requirements: list[str], told: Callable[[str], None]) -> dict[str, Any] | None:
    """The environment made by the device's engine when one runs and it is this installation's (``{"op":
    "base", "key", "with"}``, ``making``), its lines said to ``told``; None when none answers, or one of
    another installation's, which this process makes it for. ``Refused`` in the engine's words."""
    from cad.engine import client

    try:
        answer = client.request({"op": "base", "key": env.name, "with": requirements}, start=False,
                                on_log=lambda frame: told(str(frame.get("log", ""))))
    except (ConnectionError, OSError, ValueError):
        return None
    if not answer or answer.get("base") is not True:
        return None
    if answer.get("failed"):
        raise Refused(str(answer["failed"]))
    return _complete(env, requirements)


def recipe(installation: base.Installation, requirements: list[str], changed: list[str] | None = None) -> base.Recipe:
    """The environment's recipe: the base's (``cad[build123d]`` as the installation installs it, on its
    Python) and the requirements, resolved together. ``changed``: the local packages whose edit makes it
    anew, which its line names."""
    named, kernel = ", ".join(requirements), f"{base.LIBRARY}[{base.EXTRA}] {installation.release}"
    making = (f"making {WHAT} again, as {', '.join(changed)} changed: {named} beside {kernel}" if changed
              else f"making {WHAT}, once: {named} beside {kernel}")
    return base.Recipe(what=WHAT, python=installation.executable,
                       requirement=(*installation.requirement(), *requirements), release=installation.release,
                       source=installation.source, making=making, downloading=f"downloading what {named} needs, once",
                       unsatisfiable=f"{named} cannot be resolved beside {kernel}")


def _make(env: Path, installation: base.Installation, requirements: list[str], prints: dict[str, str],
          told: Callable[[str], None]) -> dict[str, Any]:
    """The environment at ``env`` made (``base.make``), its marker naming its installation, as the base's
    does, the requirements it holds (``with``) and its local packages' fingerprints (``local``), its line
    naming those an edit made it anew for (``_changed``); then the environments of other releases, and the
    one it supersedes, collected."""
    import dataclasses

    inputs = base._inputs(installation)

    def finish(steps: list[list[str]], seconds: float) -> dict[str, Any]:
        return {"schema": base.SCHEMA, "key": env.name, "inputs": inputs,
                "installation": dataclasses.asdict(installation), "with": requirements, "local": prints,
                "path": base._path(env), "commands": steps, "seconds": round(seconds, 2),
                "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    changed = _changed(env.parent, inputs, requirements, prints)
    marker = base.make(env, recipe(installation, requirements, changed), told, finish=finish, marker=base.MARKER,
                       done=lambda folder: _complete(folder, requirements))
    _collect(env.parent, installation.release, made=env, requirements=requirements, inputs=inputs)
    return marker


def _changed(folder: Path, inputs: dict[str, Any], requirements: list[str], prints: dict[str, str]) -> list[str]:
    """The local packages an edit makes the environment of ``requirements`` anew for: those a complete one
    beside it, of the same installation's base and requirements, knew otherwise."""
    changed: set[str] = set()
    try:
        entries = [Path(entry.path) for entry in os.scandir(folder) if entry.is_dir(follow_symlinks=False)]
    except OSError:
        return []
    for env in entries:
        marker = base.complete(env)
        if marker is None or marker.get("with") != requirements or marker.get("inputs") != inputs:
            continue
        before = marker.get("local") if isinstance(marker.get("local"), dict) else {}
        changed.update(path for path, now in prints.items() if before.get(path) != now)
    return sorted(changed)


def _collect(folder: Path, release: str, made: Path | None = None, requirements: list[str] | None = None,
             inputs: dict[str, Any] | None = None) -> list[str]:
    """The environments of a model's packages in ``folder`` of other releases than ``release`` removed, and
    those the one just ``made`` supersedes -- of its installation's base (``inputs``) and ``requirements``,
    a local package since edited --, but one a process runs from (``releases.running``), which goes at a
    later making: the paths removed. The bases are their releases' to remove (``releases.collect``)."""
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
        other = (marker.get("inputs") or {}).get("release") != release
        superseded = made is not None and marker.get("with") == requirements and marker.get("inputs") == inputs
        if not (other or superseded) or running(env):
            continue
        try:
            base._remove(env)
        except Refused:
            continue  # held by a process (Windows): a later making takes it
        removed.append(str(env))
    return removed


class Making(base.Making):
    """The environment of one set of requirements made in the engine's background, for whoever asks
    (``Daemon.base``'s ``with``): ``base.Making``'s, of that environment."""

    def __init__(self, requirements: list[str]) -> None:
        super().__init__()
        self.requirements = sorted(set(requirements))

    def key(self) -> str | None:
        return key(base.Installation.here(), self.requirements)

    def start(self) -> bool:
        with self.changed:
            if self.state == "making":
                return True
            installation = base.Installation.here()
            if _complete(where(installation, self.requirements), self.requirements) is not None:
                return False
            self.state, self.lines, self.error, self.since = "making", [], None, time.time()
        threading.Thread(target=self._make, name="cad-extras", daemon=True).start()
        return True

    def _make(self) -> None:
        try:
            ensure(base.Installation.here(), self.requirements, told=self._said)
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


def making(requirements: list[str]) -> Making:
    """The engine's making of the environment of ``requirements`` (normalized): one per environment.
    ``Refused`` for an option of uv's among them (``refusal``): only the door reaches this, and uv is handed
    requirements alone."""
    for requirement in requirements:
        refused = refusal(requirement)
        if refused is not None:
            raise Refused(refused)
    found = Making(requirements)
    named = found.key() or ""
    with _MAKINGS_LOCK:
        return _MAKINGS.setdefault(named, found)
