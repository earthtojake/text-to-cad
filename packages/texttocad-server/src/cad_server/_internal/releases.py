"""The releases of cadgen this device keeps, each the folder an update installs it in.

``<state>/releases/<version>`` is a release's core -- the ``cadgen`` command, the engine, the CAD
Viewer's server, the MCP shim, without the kernel (its ``kernel`` extra goes in the base,
``cad_server._internal.base``) -- in a virtual environment of the engine's own interpreter, made by uv
as the base is (``base.make``): its files hard links into uv's cache, asked of the cache first
(``--offline``) and of the network only for what it does not hold, its marker
(``cadgen-release.json``) written last, a lock beside it. An update makes the folder of the release
it moves to (``make``), that release then sets itself up from there (``cad setup``, which
registers it, ``cad_server._internal.installations``), and the switch points ``current`` at it
(``cad_server._internal.switch``).

After a switch the folder of the release before stays: a session the switch did not end may still
run a process from it (Python imports lazily, so a folder must never vanish under a live one), and a
switch that fails goes back to it. The others go at that switch (``collect``), each once no process
runs from it, with the bases made for it.

What is made from where: a release on the index as ``texttocad-server==<version>`` (the library without
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

__all__ = ["FOLDER", "MARKER", "SCHEMA", "collect", "complete", "console", "listing", "make", "root", "running",
           "where"]

FOLDER = "releases"
MARKER = "cadgen-release.json"
SCHEMA = "cadgen release/1"


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
    """The ``cadgen`` command of the environment at ``env``."""
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
                "cadgen": str(console(env)), "source": source, "commands": steps, "seconds": round(seconds, 2),
                "made": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    return base.make(env, recipe(version, python or sys.executable, source), told or base._say, finish=finish,
                     marker=MARKER, done=complete)


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
    command line (``ps``). True when that cannot be asked: a folder is kept rather than taken from
    under a process. On Windows a file a process runs is never removed anyway (``collect``)."""
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
    return any(named in line or plain in line for line in listed.stdout.splitlines())


def collect(keep: Iterable[str]) -> list[str]:
    """The release folders but those of ``keep`` (the current release and the one before it) removed,
    each with the bases made for it and its installation record, once no process runs from it
    (``running``): the paths removed. A folder that cannot be removed whole (on Windows, one a process
    runs from) stays, and goes at a later update."""
    from cad_server._internal import installations

    kept = set(keep)
    removed: list[str] = []
    for found in listing():
        if found["version"] in kept or running(found["path"]):
            continue
        folder = Path(found["path"])
        for env in _bases_of(folder):
            shutil.rmtree(env, ignore_errors=True)
            if not env.exists():
                removed.append(str(env))
        shutil.rmtree(folder, ignore_errors=True)
        if folder.exists():
            continue
        removed.append(str(folder))
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
