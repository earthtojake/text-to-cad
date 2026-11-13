"""The flat release folders of 0.11.10 and earlier, and the recipe a version's server environment is made by.

``<state>/releases/<version>`` is where 0.11.10 and earlier installed a release: its core in a virtual environment,
made by uv, its marker (``cad-release.json``) written last. Those releases' updaters make one for the release they
move to (an updater of 0.11.10 runs that folder's ``cad setup --engine-update``: ``cad_server.cli.setup``). From
the first pinned release on, a release lives in ``versions/<version>`` (``cad_server._internal.versions``), whose server environment is
made by the same recipe (``recipe``) and carries the same marker; the flat folders are the layout of 0.11.10 and
earlier, removed with it once nothing runs from them (``cad_server._internal.legacy``), and by ``cad uninstall``.

What is made from where: a release on the index as ``cad-server==<version>`` (the library without its kernel comes
with it, at the same release); one this installation was installed from as a wheel (``--from`` a file,
``direct_url.json``) from that wheel again. A folder of wheels a test names is read beside the index
(``base.FIND_LINKS_ENV``).
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

from cad_server._internal import base

__all__ = ["FOLDER", "MARKER", "SCHEMA", "complete", "console", "listing", "recipe", "root", "running"]

FOLDER = "releases"
MARKER = "cad-release.json"
SCHEMA = "cad release/1"


def root() -> Path:
    """The releases' folder: ``releases`` in the state folder."""
    from cad.engine.places import state_dir

    return Path(state_dir()) / FOLDER


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
    return base.Recipe(what=f"cad-server {version}", python=python, requirement=requirement, release=version,
                       source=source, making=f"installing cad-server {version} on Python {platform.python_version()}",
                       downloading=f"downloading cad-server {version}")


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


def running(folder: Path | str, *, besides: int | None = None) -> bool:
    """Whether a process runs from ``folder``: one started by its Python or its command names it on its
    command line (``ps``), as written or by a link to it -- each path on the line read with its folder
    resolved, as ``folder`` is, so a worker started by an alias of an environment's Python counts. ``besides``: a
    process whose own, and its descendants', do not count (a version's server and its workers, asked before the
    server is stopped; this process, which may run from the folder it removes). True when that cannot be asked: a
    folder is kept rather than taken from under a process. On Windows, where it cannot be asked, False: there a
    folder is renamed aside before it is removed, which the system refuses for a file in use (``versions.remove``,
    ``legacy.remove``)."""
    if os.name == "nt":
        return False
    named = os.path.realpath(folder).rstrip(os.sep) + os.sep
    plain = os.path.abspath(folder).rstrip(os.sep) + os.sep
    try:
        listed = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return True
    if listed.returncode != 0:
        return True
    rows: list[tuple[int, int, str]] = []
    for line in listed.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    spared: set[int] = set()
    if besides is not None:
        spared.add(besides)
        grew = True
        while grew:
            grew = False
            for pid, parent, _command in rows:
                if parent in spared and pid not in spared:
                    spared.add(pid)
                    grew = True
    resolved: dict[str, str] = {}

    def within(word: str) -> bool:
        # Its folder resolved, not the word itself: a venv's python is a link out of its environment.
        head, tail = os.path.split(word)
        if head not in resolved:
            resolved[head] = os.path.realpath(head)
        return (os.path.join(resolved[head], tail) + os.sep).startswith(named)

    return any(named in line or plain in line or any(word.startswith(os.sep) and within(word) for word in line.split())
               for pid, _parent, line in rows if pid not in spared)
