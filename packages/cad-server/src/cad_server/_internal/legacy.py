"""The layout before 0.12, as the default channel's old version: what a version imports from where it has no
version to import from, and what goes once the default channel has left it and it is safe to remove.

Before 0.12 every release on a device shared one data folder, the state folder itself, one cache folder
(``places.legacy_cache_dir``), and kept its code flat in ``releases/<release>``. A version of 0.12 or later
imports from it (``cad_server._internal.imports``: the same relative names as a version's ``data/``) and never
writes it. The default channel's first move on a device with this layout imports from it; once the default
channel has a pointer, the layout's bulk goes as soon as it is safe (``unsafe`` says why not yet): right after
that move, and else at every ``versions.sweep`` (the next move, a server going idle, ``cad doctor --prune``).

Safe means all of: the default's version has its data imported (its marker); it has started and its server
runs (``versions.serves``); no server but that version's own holds the flat engine folder every client before 0.12
finds (``flat_server``: one started by uvx outside ``releases/`` among them); no process runs from the layout (``releases.running`` on its release folders and its
kernel environments; on Windows, where that cannot be asked, a rename that the system refuses for a file in use
keeps the folder). Nothing of an agent app's is read for it, and no record is kept: the layout's own folders are
the record.

What ``remove`` removes, by name (``REMOVED``, ``CACHES``): each flat ``releases/<release>`` (renamed aside first)
with its making's lock and its installation's record, and ``releases/`` once empty; the shared ``documents/``
(the records) and ``recents/`` in the state folder; in the cache folder before 0.12 the kernel and ``cad run``
environments (``base``), compiled Python (``pycache``), documents' bytes (``documents``), ``hulls``, ``mjcf`` and
``homes``, and the cache folder once nothing else is in it.

What it keeps, because a client before 0.12 may still read it and it is small, or it is the device's: the
shared ``settings.json`` (a telemetry no is written there too), ``engines/`` (the page token and port where a
client before 0.12 finds them), the other small files there (``settings.lock``, ``install-channels.json``,
``versions.json``, the telemetry spool, the updater's records), ``installations/`` (the mirror,
``pointers.mirror``), and every global file: the pointers, ``install.lock``, ``install-receipt.json``,
``install-aside/``, ``plugin/``, ``plugin.lock``, ``versions/``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

from cad.engine import places

__all__ = ["CACHES", "IMPORTED", "REMOVED", "cache_root", "importable", "present", "remove", "removable", "root",
           "unsafe"]

# What a version imports from it (``imports`` names the same, relative to a data folder).
IMPORTED = ("settings.json", "documents", "recents", "engines/token", "engines/engine.json", "telemetry-batches.jsonl")
# What goes from the state folder, beside the flat release folders.
REMOVED = ("documents", "recents")
# What goes from the cache folder before 0.12: documents' bytes and their kept checks, convex hulls, MJCF assets,
# integrations' homes, the kernel and ``cad run`` environments, compiled Python.
CACHES = ("documents", "hulls", "mjcf", "homes", "base", "pycache")
RELEASES = "releases"
# How long the flat engine folder's server is given to say what it is (``flat_server``).
ASK_SECONDS = 5.0


def root() -> Path:
    """The layout's data folder: the state folder itself."""
    return places.state_dir()


def cache_root() -> Path:
    """The layout's cache folder (``places.legacy_cache_dir``)."""
    return places.legacy_cache_dir()


def importable() -> bool:
    """Whether the layout holds anything a version imports (``IMPORTED``)."""
    return any(os.path.lexists(root() / name) for name in IMPORTED)


def _releases() -> list[str]:
    try:
        return sorted(entry.name for entry in os.scandir(root() / RELEASES) if entry.is_dir(follow_symlinks=False))
    except OSError:
        return []


def removable() -> bool:
    """Whether anything ``remove`` removes is here."""
    return (bool(_releases()) or any(os.path.lexists(root() / name) for name in REMOVED)
            or any(os.path.lexists(cache_root() / name) for name in CACHES))


def present() -> bool:
    """Whether this device has the layout: anything a version imports, or anything ``remove`` removes."""
    return importable() or removable()


def unsafe(version: str) -> str | None:
    """Why the layout cannot be removed yet now that the default channel is on ``version``, in words; None when it
    is safe: ``version``'s data is imported, its server runs, and no process runs from the layout (see the
    module)."""
    from cad_server._internal import imports, releases, versions

    if not imports.imported(version):
        return f"text-to-cad {version}'s data is not imported yet"
    if not versions.serves(version):
        return f"text-to-cad {version} has not started yet"
    flat = flat_server()
    if flat is not None and not _within(flat, places.code_dir(version)):
        return f"a server other than text-to-cad {version}'s holds the flat engine folder {places.engines_dir()}"
    for folder in (*(root() / RELEASES / name for name in _releases()), cache_root() / "base"):
        if folder.exists() and releases.running(folder):
            return f"a process of a release before 0.12 still runs from {folder}"
    return None


def flat_server() -> str | None:
    """The environment of the server that holds the flat engine folder every client before 0.12 finds
    (``places.engines_dir``: its ``engine.lock``, and its door, on Windows its port file), as it says it in its
    ``status`` (``prefix``), read and nothing started; ``""`` for one that holds the lock and does not answer or
    say; None when none holds it. The default version's own server holds it too, as the bridge."""
    import threading

    from cad.engine import client
    from cad_server._internal.versions import _drop, _take

    engines = places.engines_dir()
    try:
        held = _take(engines)
    except OSError:
        return ""
    if held is not None:
        _drop(held, engines)
        return None
    answers: list = []
    address = engines / f"{places.NAME}.{'port' if places.WINDOWS else 'door'}"

    def ask() -> None:
        try:
            connection = client._connect(address)
            if connection is not None:
                answers.append(client._exchange(connection, {"op": "status"}, address=address))
        except (OSError, ValueError, ConnectionError, IndexError):
            pass

    asking = threading.Thread(target=ask, daemon=True)
    asking.start()
    asking.join(ASK_SECONDS)
    answer = answers[0] if answers and isinstance(answers[0], dict) else {}
    prefix = answer.get("prefix")
    return prefix if isinstance(prefix, str) else ""


def _within(prefix: str, folder: Path) -> bool:
    inside = os.path.normcase(os.path.realpath(folder)).rstrip(os.sep) + os.sep
    return bool(prefix) and os.path.normcase(os.path.realpath(prefix)).startswith(inside)


def remove(version: str, told: Callable[[str], None] | None = None) -> bool:
    """The layout's bulk removed (see the module) when the default channel is on ``version`` and it is safe
    (``unsafe``): whether nothing of it is left to remove. Each folder is renamed aside before it is removed: one
    the system refuses to rename (a file in use, on Windows) stays, said to ``told``, for the next sweep. Run
    under the install lock (``versions.sweep``)."""
    say = told or (lambda _line: None)
    if not removable():
        return True
    why = unsafe(version)
    if why is not None:
        say(f"the code and caches of releases before 0.12 stay for now: {why}")
        return False
    from cad_server._internal import installations

    current = installations.current()
    complete = True
    folder = root() / RELEASES
    for name in _releases():
        path = folder / name
        if current is not None and installations._same_place(current["prefix"], path):
            say(f"release {name} before 0.12 stays: it is current")
            complete = False
            continue
        if _gone(path, say):
            (folder / f"{name}.lock").unlink(missing_ok=True)
            for record in installations.records():
                if installations._same_place(record["prefix"], path):
                    installations.forget(record["version"])
        else:
            complete = False
    for entry in _names(folder):  # the locks of releases gone already
        if entry.endswith(".lock") and not (folder / entry[:-5]).exists():
            (folder / entry).unlink(missing_ok=True)
    _rmdir(folder)
    for parent in (root(), cache_root()):  # what an earlier removal cut short left aside
        for entry in _names(parent):
            if entry.startswith(".removing-"):
                shutil.rmtree(parent / entry, ignore_errors=True)
    for path in (*(root() / name for name in REMOVED), *(cache_root() / name for name in CACHES)):
        complete = _gone(path, say) and complete
    _rmdir(cache_root())
    if complete:
        say("removed the code, records and caches of releases before 0.12")
    return complete


def _names(folder: Path) -> list[str]:
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


def _rmdir(folder: Path) -> None:
    try:
        folder.rmdir()  # only when nothing else is in it
    except OSError:
        pass


def _gone(path: Path, say: Callable[[str], None]) -> bool:
    """What is at ``path`` renamed aside, then removed: whether nothing is left there. A rename the system refuses
    leaves it."""
    if not os.path.lexists(path):
        return True
    aside = path.with_name(f".removing-{path.name}-{os.getpid()}-{os.urandom(4).hex()}")
    try:
        os.rename(path, aside)
    except OSError as error:
        say(f"{path} stays for now: {error.strerror or error}")
        return False
    if aside.is_dir() and not aside.is_symlink():
        shutil.rmtree(aside, ignore_errors=True)
    else:
        aside.unlink(missing_ok=True)
    return True
