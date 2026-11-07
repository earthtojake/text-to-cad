"""The releases of text-to-cad this device keeps, each the folder an update installs it in.

``<state>/releases/<version>`` is a release's core -- the ``cad`` command, the engine, the CAD
Viewer's server, the MCP shim, without the kernel (its ``build123d`` extra goes in the base,
``cad_server._internal.base``) -- in a virtual environment of the engine's own interpreter, made by uv
as the base is (``base.make``): its files hard links into uv's cache, asked of the cache first
(``--offline``) and of the network only for what it does not hold, its marker
(``cad-release.json``) written last, a lock beside it. An update makes the folder of the release
it moves to (``make``), that release then sets itself up from there (``cad setup``, which
registers it, ``cad_server._internal.installations``), and the switch points ``current`` at it
(``cad_server._internal.switch``).

After a switch the folder of the release before stays: a session the switch did not end may still
run a process from it (Python imports lazily, so a folder must never vanish under a live one), and a
switch that fails goes back to it. The others go at that switch (``collect``), each once no process
runs from it, with the bases made for it. A switch that failed and went back leaves the release it
failed to move to for nothing: its folder goes once the release before's engine is up again and
nothing runs from it (``discard``: by the switch, else by that engine as it tends itself), and so does
any folder but the current release's and the one before's at ``cad doctor --prune`` (``kept``). The
failure stays recorded -- the switch's ``update.json``, an automatic update's attempt -- so an
automatic update does not try that release again by itself any sooner.

What is made from where: a release on the index as ``cad-server==<version>`` (the library without
its kernel comes with it, at the same release); one this installation was installed from as a wheel
(``--from`` a file, ``direct_url.json``) from that wheel again. A folder of
wheels a test names is read beside the index (``base.FIND_LINKS_ENV``).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable

from cad_server._internal import base

__all__ = ["FOLDER", "MARKER", "SCHEMA", "before", "collect", "complete", "console", "discard", "failed", "kept",
           "listing", "make", "root", "running", "where"]

FOLDER = "releases"
MARKER = "cad-release.json"
SCHEMA = "cad release/1"


def root() -> Path:
    """The releases' folder: ``releases`` in the state folder."""
    from cad.engine.places import state_dir

    return Path(state_dir()) / FOLDER


def where(version: str) -> Path:
    """The folder of release ``version``, made or not. ``ValueError`` for a name that is no version."""
    from cad_server._internal.installations import VERSION

    if not VERSION.fullmatch(version or ""):
        raise ValueError(f"not a cadgen version: {version!r}")
    return root() / version


def console(env: Path) -> Path:
    """The ``cad`` command of the environment at ``env``."""
    return env / ("Scripts/cad.exe" if os.name == "nt" else "bin/cad")


def complete(env: Path) -> dict[str, Any] | None:
    """The marker of the release folder at ``env`` when it is complete -- written last, of its version,
    its Python and its command there -- else None."""
    try:
        marker = json.loads((env / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (isinstance(marker, dict) and marker.get("schema") == SCHEMA and marker.get("version") == env.name
            and base.interpreter(env).exists() and console(env).exists()):
        return marker
    return None


def recipe(version: str, python: str, source: str | None) -> base.Recipe:
    """How release ``version``'s folder is made, on the interpreter ``python``: its server from the index
    -- the library at the same release comes with it --, or from ``source``, the server's source tree
    (editable) or the wheel it was installed from, beside the library from where this installation's
    came (``base.Installation.source``: its tree, editable, or its wheel), when that is no release."""
    if source is None:
        requirement: tuple[str, ...] = (f"{base.SERVER}=={version}",)
    else:
        library = base._own().source
        if os.path.isdir(source):
            requirement = (*(("-e", library) if library and os.path.isdir(library) else ()), "-e", source)
        else:
            requirement = (*((f"{base.LIBRARY} @ {library}",) if library and not os.path.isdir(library) else ()),
                           f"{base.SERVER} @ {source}")
    return base.Recipe(what=f"text-to-cad {version}", python=python, requirement=requirement, release=version,
                       source=source, making=f"installing text-to-cad {version} on Python {platform.python_version()}",
                       downloading=f"downloading text-to-cad {version}")


def make(version: str, *, python: str | None = None, source: str | None = None,
         told: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Release ``version``'s folder, made first when it is not complete (see the module): on ``python``
    (by default this process's interpreter, the engine's), from the index or the wheel ``source``, each
    line of the making said to ``told``. Its marker; ``base.Refused`` in one line when it cannot be made."""
    env = where(version)
    found = complete(env)
    if found is not None:
        return found

    def finish(steps: list[list[str]], seconds: float) -> dict[str, Any]:
        return {"schema": SCHEMA, "version": version, "python": str(base.interpreter(env)),
                "cad": str(console(env)), "source": source, "commands": steps, "seconds": round(seconds, 2),
                "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    return base.make(env, recipe(version, python or sys.executable, source), told or base._say, finish=finish,
                     marker=MARKER, done=complete)


def python_version(env: Path) -> str | None:
    """The version of the Python the environment at ``env`` runs, asked of it, nothing written (``-B``), or None
    when it has none that answers: its ``pyvenv.cfg`` says at most the minor version uv's folder of that Python
    goes by, whose patch release moves under it."""
    try:
        done = subprocess.run([str(base.interpreter(env)), "-B", "-I", "-S", "-c",
                               "import platform; print(platform.python_version())"], stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    said = done.stdout.strip()
    return said if done.returncode == 0 and said else None


def listing() -> list[dict[str, Any]]:
    """Every release folder on this device: its ``version``, its ``path`` and whether it is ``complete``,
    oldest made first."""
    try:
        entries = sorted((entry for entry in os.scandir(root()) if entry.is_dir(follow_symlinks=False)),
                         key=lambda entry: entry.stat(follow_symlinks=False).st_mtime)
    except OSError:
        return []
    return [{"version": entry.name, "path": entry.path, "complete": complete(Path(entry.path)) is not None}
            for entry in entries]


def running(folder: Path | str) -> bool:
    """Whether a process runs from ``folder``: one started by its Python or its command names it on its
    command line (``ps``), as written or by a link to it -- each path on the line read with its folder
    resolved, as ``folder`` is, so a worker started by an alias of an environment's Python counts. True when
    that cannot be asked: a folder is kept rather than taken from under a process. On Windows a file a
    process runs is never removed anyway (``collect``)."""
    if os.name == "nt":
        return False
    named = os.path.realpath(folder).rstrip(os.sep) + os.sep
    plain = os.path.abspath(folder).rstrip(os.sep) + os.sep
    try:
        listed = subprocess.run(["ps", "-axo", "command="], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return True
    if listed.returncode != 0:
        return True
    resolved: dict[str, str] = {}

    def within(word: str) -> bool:
        # Its folder resolved, not the word itself: a venv's python is a link out of its environment.
        head, tail = os.path.split(word)
        if head not in resolved:
            resolved[head] = os.path.realpath(head)
        return (os.path.join(resolved[head], tail) + os.sep).startswith(named)

    return any(named in line or plain in line or any(word.startswith(os.sep) and within(word) for word in line.split())
               for line in listed.stdout.splitlines())


def before(current: str | None) -> str | None:
    """The release kept as the one before ``current``, the way back: the one the last switch came from,
    where that switch went to ``current`` and held (``cad_server._internal.switch.last``), else the newest
    complete release folder older than ``current`` (as PEP 440 orders them): an incomplete one is no way
    back. None for none."""
    from cad.engine.contract import _order

    if not current:
        return None
    try:
        from cad_server._internal.switch import last

        switched = last() or {}
    except Exception:  # noqa: BLE001 - no record: the order of the releases says the one before
        switched = {}
    if switched.get("to") == current and switched.get("ok") and isinstance(switched.get("from"), str):
        return switched["from"]
    mine = _order(current)
    older = [(order, found["version"]) for found in listing()
             if found["version"] != current and found["complete"] and (order := _order(found["version"])) is not None
             and mine is not None and order < mine]
    return max(older)[1] if older else None


def kept(current: str | None = None) -> set[str]:
    """The releases whose folders stay: the current one (``current``, else the device's) and the one before
    it (``before``)."""
    from cad_server._internal import installations

    current = current or installations.current_version()
    return {release for release in (current, before(current)) if release}


def collect(keep: Iterable[str]) -> list[str]:
    """The release folders but those of ``keep`` (the current release and the one before it) removed,
    each with the bases made for it and its installation record, once no process runs from it
    (``running``): the paths removed. A folder that cannot be removed whole (on Windows, one a process
    runs from) stays, and goes at a later update."""
    kept_here = set(keep)
    removed: list[str] = []
    for found in listing():
        if found["version"] not in kept_here:
            removed += _remove(found)
    return removed


def discard(release: str, keep: Iterable[str] | None = None) -> list[str]:
    """The folder of ``release`` removed -- one a switch failed to move to --, with its bases and its
    installation record, unless it is one ``keep`` names (by default ``kept``: the current release and the
    one before it) or a process runs from it: the paths removed. Its failure is not forgotten: the
    switch's record and an automatic update's attempt are not touched."""
    if release in (kept() if keep is None else set(keep)):
        return []
    found = next((found for found in listing() if found["version"] == release), None)
    return _remove(found) if found is not None else []


def failed() -> str | None:
    """The release the last switch failed to move to, while its folder is still here and it is not the
    current release: what ``discard`` takes once nothing runs from it. None for none."""
    from cad_server._internal import installations, switch

    last = switch.last() or {}
    target = last.get("to")
    if last.get("ok") is not False or not isinstance(target, str) or target == installations.current_version():
        return None
    try:
        return target if where(target).is_dir() else None
    except ValueError:
        return None


def _remove(found: dict[str, Any]) -> list[str]:
    """One release folder of ``listing``'s removed, with its bases and its installation record, unless a
    process runs from it: the paths removed."""
    from cad_server._internal import installations

    if running(found["path"]):
        return []
    removed: list[str] = []
    folder = Path(found["path"])
    for env in _bases_of(folder):
        shutil.rmtree(env, ignore_errors=True)
        if not env.exists():
            removed.append(str(env))
    shutil.rmtree(folder, ignore_errors=True)
    if folder.exists():
        return removed
    removed.append(str(folder))
    # The lock its making held (``base.make``), empty, goes with it.
    folder.with_name(f"{folder.name}.lock").unlink(missing_ok=True)
    try:
        record = next((record for record in installations.records()
                       if installations._same_place(record["prefix"], folder)), None)
        if record is not None:
            installations.forget(record["version"])
    except (OSError, ValueError):
        pass
    return removed


def _bases_of(folder: Path) -> list[Path]:
    """The bases made for the installation in ``folder`` (``base.MARKER`` naming it as theirs)."""
    from cad.engine.places import cache_dir

    found = []
    here = os.path.normcase(os.path.realpath(folder))
    try:
        entries = list(os.scandir(Path(cache_dir()) / base.BASE))
    except OSError:
        return []
    for entry in entries:
        if not entry.is_dir(follow_symlinks=False):
            continue
        try:
            marker = json.loads((Path(entry.path) / base.MARKER).read_text(encoding="utf-8"))
            prefix = marker["installation"]["prefix"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if isinstance(prefix, str) and os.path.normcase(os.path.realpath(prefix)) == here:
            found.append(Path(entry.path))
    return found
