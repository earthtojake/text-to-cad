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
installation's base's inputs, its release among them, and the requirements normalized and sorted,
``normalized``), its marker naming the installation and the requirements (``with``), so a process there
reaches its installation's engine as a process in the base does, and names its Python in its orders
(``cad.engine.contract.interpreter``): the engine builds the script in a warm worker of it, of one release
with the engine, so no update notice is said. A header's ``requires-python`` the server's Python does not
meet is refused in one line. With no packages named, ``cad run`` runs the base, as ever.

Environments of other releases go when one is made (``_collect``), but one a process runs from, which goes
at a later making. What uv cannot do is said in one line (``base.failure``): requirements it cannot resolve
beside the kernel's pins, with its reason; a package its cache lacks where the network cannot be reached, by
name.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import posixpath
import re
import sys
import threading
import time
import tomllib
from pathlib import Path
from typing import Any, Callable

from cad_server._internal import base

__all__ = ["Making", "Refused", "admits", "arguments", "ensure", "header", "key", "making", "normalized", "split",
           "tell", "where"]

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
# A version specifier's clause, as ``requires-python`` writes one.
_CLAUSE = re.compile(r"\s*(~=|===|==|!=|<=|>=|<|>)\s*([0-9]+(?:\.[0-9]+)*)(\.\*)?\s*")


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
    """Whether the Python ``version`` (``3.14.6``) meets ``spec`` (``>=3.11,<3.15``), each clause as PEP 440
    reads it (``~=``, ``==`` and ``!=`` with ``.*``, the comparisons); None for a spec that does not read."""
    have = [int(part) for part in re.findall(r"\d+", version)[:3]]
    for clause in spec.split(","):
        if not clause.strip():
            continue
        found = _CLAUSE.fullmatch(clause)
        if found is None:
            return None
        operator, text, star = found.groups()
        want = [int(part) for part in text.split(".")]
        if star:
            if operator not in ("==", "!="):
                return None
            same = have[:len(want)] == want
            admitted = same if operator == "==" else not same
        elif operator == "~=":
            if len(want) < 2:
                return None
            size = max(len(have), len(want))
            admitted = _padded(have, size) >= _padded(want, size) and have[:len(want) - 1] == want[:-1]
        else:
            size = max(len(have), len(want))
            mine, theirs = _padded(have, size), _padded(want, size)
            admitted = {"==": mine == theirs, "===": mine == theirs, "!=": mine != theirs, "<=": mine <= theirs,
                        ">=": mine >= theirs, "<": mine < theirs, ">": mine > theirs}[operator]
        if not admitted:
            return False
    return True


def _padded(numbers: list[int], size: int) -> list[int]:
    return numbers + [0] * (size - len(numbers))


def tell(given: list[str]) -> None:
    """The program ``cad run`` runs told the requirements its ``--with`` was given, normalized
    (``places.RUN_WITH``, as JSON; with none, unset): what a document it builds names to build it again
    (``contract.interpreter``'s ``with``). A header's are its script's, which ``cad run`` reads again."""
    from cad.engine.places import RUN_WITH

    if given:
        os.environ[RUN_WITH] = json.dumps(given)
    else:
        os.environ.pop(RUN_WITH, None)


# --- the key -----------------------------------------------------------------------------------------


def _path_like(text: str) -> bool:
    """Whether a requirement is a local path -- a project folder, a wheel or an archive -- rather than a
    named one: it starts as a path does (``./``, ``../``, ``/``, ``~``, ``C:\\``, ``\\\\server``), or is a
    file of a distribution's kind with no name before an ``@``."""
    return (text.startswith((".", "/", "~", "\\")) or re.match(r"[A-Za-z]:[\\/]", text) is not None
            or ("@" not in text and text.lower().endswith((".whl", ".tar.gz", ".zip"))))


def normalized(requirement: str, folder: str) -> str:
    """A requirement as its environment's key has it, and as ``cad run --with`` is said again: a local path
    absolute against ``folder`` (``--with``'s, the working folder; a header's, its script's), as this
    platform spells a path; a named one with its project's name normalized (PEP 503: lower case, each run of
    ``-``, ``_`` and ``.`` one ``-``), its extras sorted, and no spaces in its version specifier. ``Refused``
    for an option of uv's (``--index-url=...``), which no requirement is."""
    text = requirement.strip()
    if text.startswith("-"):
        raise Refused(f"{text} is no requirement: name a package, a pin, extras, or a local path or wheel")
    if _path_like(text):
        paths = ntpath if WINDOWS else posixpath
        return paths.normpath(paths.join(folder, paths.expanduser(text)))
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
    if rest.startswith("@"):  # a direct reference: its URL as written
        return f"{name}{extras} @ {rest[1:].strip()}"
    specifier, marked, marker = rest.partition(";")
    specifier = re.sub(r"\s+", "", specifier)
    return f"{name}{extras}{specifier}" + (f"; {marker.strip()}" if marked else "")


def key(installation: base.Installation, requirements: list[str]) -> str:
    """The environment's key: its installation's base's inputs (the release, its source, its Python and
    the architecture among them) and the requirements, normalized (``normalized``), each once and sorted."""
    material = json.dumps({"base": base._inputs(installation), "with": sorted(set(requirements))}, sort_keys=True)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def where(installation: base.Installation, requirements: list[str]) -> Path:
    """The folder of the environment of ``requirements`` (normalized), made or not: beside the base."""
    from cad.engine.places import cache_dir

    return cache_dir() / base.BASE / key(installation, requirements)


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
    env = where(installation, requirements)
    marker = _complete(env, requirements)
    if marker is not None:
        return base._found(env, marker)
    if engine:
        marker = _by_the_engine(env, requirements, told)
        if marker is not None:
            return base._found(env, marker)
    return base._found(env, _make(env, installation, requirements, told))


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


def recipe(installation: base.Installation, requirements: list[str]) -> base.Recipe:
    """The environment's recipe: the base's (``cad[build123d]`` as the installation installs it, on its
    Python) and the requirements, resolved together."""
    named, kernel = ", ".join(requirements), f"{base.LIBRARY}[{base.EXTRA}] {installation.release}"
    return base.Recipe(what=WHAT, python=installation.executable,
                       requirement=(*installation.requirement(), *requirements), release=installation.release,
                       source=installation.source, making=f"making {WHAT}, once: {named} beside {kernel}",
                       downloading=f"downloading what {named} needs, once",
                       unsatisfiable=f"{named} cannot be resolved beside {kernel}")


def _make(env: Path, installation: base.Installation, requirements: list[str],
          told: Callable[[str], None]) -> dict[str, Any]:
    """The environment at ``env`` made (``base.make``), its marker naming its installation, as the base's
    does, and the requirements it holds (``with``); then the environments of other releases collected."""
    import dataclasses

    def finish(steps: list[list[str]], seconds: float) -> dict[str, Any]:
        return {"schema": base.SCHEMA, "key": env.name, "inputs": base._inputs(installation),
                "installation": dataclasses.asdict(installation), "with": requirements, "path": base._path(env),
                "commands": steps, "seconds": round(seconds, 2), "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    marker = base.make(env, recipe(installation, requirements), told, finish=finish, marker=base.MARKER,
                       done=lambda folder: _complete(folder, requirements))
    _collect(env.parent, installation.release)
    return marker


def _collect(folder: Path, release: str) -> list[str]:
    """The environments of a model's packages of other releases than ``release`` in ``folder`` removed,
    but one a process runs from (``releases.running``), which goes at a later making: the paths removed.
    The bases are their releases' to remove (``releases.collect``)."""
    from cad_server._internal.releases import running

    removed = []
    try:
        entries = [Path(entry.path) for entry in os.scandir(folder) if entry.is_dir(follow_symlinks=False)]
    except OSError:
        return removed
    for env in entries:
        marker = base.complete(env)
        if (marker is None or not isinstance(marker.get("with"), list)
                or (marker.get("inputs") or {}).get("release") == release or running(env)):
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
    """The engine's making of the environment of ``requirements`` (normalized): one per environment."""
    found = Making(requirements)
    named = found.key() or ""
    with _MAKINGS_LOCK:
        return _MAKINGS.setdefault(named, found)
