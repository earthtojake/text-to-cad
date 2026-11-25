"""The store: the releases cad's update keeps beside the installed cad, each in a folder of its own.

**Why.** An installer that updates a tool changes its files where they are. On Windows a file a process holds cannot
be replaced, so an update met by a running ``cad`` stopped halfway and left a cad that no longer ran; anywhere, a
process that started before an update and imported a module after it ran two releases at once. So cad's own update
changes no file of a cad that is installed. It installs the newer release whole into a new folder here (``build``),
runs it once before it counts (``verify``), gives it its name (``publish``), and only then says, in one small file
written whole, that the environment runs it (``point``). A process that started before that keeps the release it
started with, to its end. What reads the pointer is ``_cad_release``, as each interpreter of the environment starts.

**A stored release** is a folder ``<state folder>/store/<release>-<python>`` (``folder``): what ``uv pip install
--target`` makes for the environment's own interpreter -- cad and every package it needs, nothing shared with the
environment's own packages -- and, written last, its marker (``MARKER``: ``{"store": 1, "release", "python",
"built"}``). Without its marker a folder is no release. Nothing writes into one after that but Python's own bytecode.
The files are linked from uv's cache where the file system allows (``LINK``), so a release costs little room.

**The pointer** (``POINTER``, in the environment: ``sys.prefix``) names the stored release the environment runs,
and the install of cad it was written for (``own``: that cad's ``RECORD``, with its time and size). ``_cad_release``
takes it only for that very install, so installing cad again, by its installer or by hand, always runs what was
installed, and the pointer of the install before means nothing (``pointed``). With no pointer the environment runs
its own packages: a fresh install, and the first release after one.

**In use.** Every process that runs a stored release keeps its marker open (``_cad_release.HELD``). ``remove`` takes
a release only where no process does: on Windows by renaming its folder, which the system refuses while a file in
it is open; elsewhere by taking the marker's lock alone, which no process shares. A folder is renamed aside before it
is deleted, so a release is whole or gone, and what cannot be deleted yet (on Windows a library another release's
process has loaded through a link to the same file) waits in its ``.trash-`` folder for the next ``clean``.

Everything here asks ``sys.modules`` for ``_cad_release`` and never imports it: it acts as the interpreter starts,
and only then.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

__all__ = ["BUILDING", "FOLDER", "Failed", "LINK", "MARKER", "POINTER", "TRASH", "active", "build", "clean", "folder",
           "marker", "own", "packages", "point", "pointed", "pointer", "publish", "remove", "restore", "root",
           "running", "switches", "tag", "verify"]

FOLDER = "store"
# ``_cad_release``'s names, which never change (``tests/python/packages/cad_server/test_store.py`` holds them equal).
POINTER = "cad-pointer.json"
MARKER = "cad-store.json"
# A release being built, and one being removed: neither is a release.
BUILDING, TRASH = ".building-", ".trash-"
# How a release's files are made from uv's cache, as the kernel's environment's are (``base.LINK``): hard links where
# the file system makes them, copies where it does not.
LINK = "hardlink"
# How long a build may take, and the one run of a release before it counts. Stopping either changes nothing that
# runs: the folder is not a release yet.
BUILD_SECONDS, VERIFY_SECONDS = 900.0, 180.0
# How old a ``.building-`` folder is before ``clean`` takes it for one whose build died.
ABANDONED_SECONDS = 3600.0
# What a release is run with before it counts (``verify``): nothing on the import path but the standard library and
# its own folder, as ``_cad_release`` runs it, then its own check of itself (``cad_server._internal.selftest``).
VERIFY = ("import runpy, sys; sys.path.append(sys.argv[1]); "
          "runpy.run_module('cad_server._internal.selftest', run_name='__main__', alter_sys=True)")
# The waits between tries at a rename Windows refuses for a moment (a scanner reading a file just written).
RENAME_WAITS = (0.0, 0.1, 0.3, 0.9)

Run = Callable[[list[str], float], "tuple[int | None, str]"]


class Failed(Exception):
    """A release could not be built or did not run: ``step`` (``build``, ``verify``), the exit status of the command
    that failed (None: it could not run, or did not end in time) and all it printed."""

    def __init__(self, step: str, code: int | None, output: str) -> None:
        super().__init__(f"{step}: exit {code}")
        self.step, self.code, self.output = step, code, output


# --- where things are --------------------------------------------------------------------------------------------------


def root() -> Path:
    """The store: ``store`` in the state folder."""
    from cad.engine.places import state_dir

    return Path(state_dir()) / FOLDER


def tag() -> str:
    """The interpreter a stored release is made for and a pointer is read by: ``sys.implementation.cache_tag``."""
    return sys.implementation.cache_tag


def folder(release: str) -> Path:
    """Where release ``release`` is stored for this interpreter."""
    return root() / f"{release}-{tag()}"


def marker(path: str | os.PathLike[str]) -> dict[str, Any] | None:
    """The marker of the stored release at ``path``, or None for a folder that is none (not there, half built, made
    for another interpreter)."""
    try:
        found = json.loads((Path(path) / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    whole = isinstance(found, dict) and found.get("store") == 1 and isinstance(found.get("release"), str)
    return found if whole and found.get("python") == tag() else None


def _bootstrap() -> Any:
    return sys.modules.get("_cad_release")


def packages() -> Path | None:
    """This environment's own packages folder, where ``_cad_release`` ran as this interpreter started
    (``_cad_release.HERE``); None where it did not (a checkout, a Python that reads no ``.pth`` line)."""
    found = _bootstrap()
    return Path(found.HERE) if found is not None else None


def switches() -> bool:
    """Whether a pointer written now is read by the next process of this environment: ``_cad_release`` ran as this
    interpreter started, from this environment's own packages. Where it did not, an update would build a release
    nothing runs."""
    here = packages()
    if here is None:
        return False
    inside = os.path.normcase(os.path.realpath(sys.prefix)).rstrip(os.sep) + os.sep
    return os.path.normcase(os.path.realpath(here)).startswith(inside)


def running() -> Path | None:
    """The stored release this process runs, or None: it runs the environment's own packages."""
    found = _bootstrap()
    stored = getattr(found, "STORED", None)
    return Path(stored) if stored else None


def own(packages_folder: str | os.PathLike[str]) -> tuple[str, Path] | None:
    """The cad installed in the environment whose own packages folder is ``packages_folder``: ``(its release, its
    RECORD)``, or None. A ``cad-<release>.dist-info`` counts only with its ``RECORD`` and ``METADATA`` (an install
    stopped midway leaves a folder with neither); of several, the one written last is the install that is there."""
    found = []
    try:
        entries = list(os.scandir(packages_folder))
    except OSError:
        return None
    for entry in entries:
        name = entry.name
        if not (name.startswith("cad-") and name.endswith(".dist-info")):
            continue
        record = Path(entry.path) / "RECORD"
        try:
            if not (Path(entry.path) / "METADATA").is_file():
                continue
            found.append((record.stat().st_mtime_ns, name[len("cad-"):-len(".dist-info")], record))
        except OSError:
            continue
    if not found:
        return None
    _at, release, record = max(found)
    return release, record


def _packages_of(prefix: str | os.PathLike[str]) -> Path | None:
    """The own packages folder of the environment at ``prefix``: this process's as ``_cad_release`` names it, else the
    one ``cad`` is installed in under ``prefix``."""
    here = packages()
    if here is not None and os.path.normcase(os.path.realpath(prefix)) == os.path.normcase(os.path.realpath(sys.prefix)):
        return here
    for pattern in ("Lib/site-packages", "lib/python*/site-packages"):
        for found in sorted(Path(prefix).glob(pattern)):
            if own(found) is not None:
                return found
    return None


# --- the pointer -------------------------------------------------------------------------------------------------------


def pointer(prefix: str | os.PathLike[str] | None = None) -> dict[str, Any] | None:
    """The pointer as the environment at ``prefix`` (this one) keeps it, whatever it is for; None with none."""
    try:
        found = json.loads((Path(prefix or sys.prefix) / POINTER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def pointed(prefix: str | os.PathLike[str] | None = None) -> dict[str, Any] | None:
    """The pointer of the environment at ``prefix`` (this one) where a process started there now would take it, by
    ``_cad_release``'s own rules: its format, this interpreter, the install it was written for still the one there,
    and the stored release it names whole. With ``"release"``, the release that marker names. Else None."""
    prefix = Path(prefix or sys.prefix)
    found = pointer(prefix)
    here = _packages_of(prefix)
    if found is None or here is None or found.get("pointer") != 1 or found.get("python") != tag():
        return None
    try:
        installed = (here / str(found["record"])).stat()
        if [installed.st_mtime_ns, installed.st_size] != found["stamp"]:
            return None
        kept = marker(found["path"])
    except (OSError, KeyError, TypeError):
        return None
    return {**found, "release": kept["release"]} if kept is not None else None


def active(prefix: str | os.PathLike[str] | None = None) -> str | None:
    """The release of cad a process of the environment at ``prefix`` (this one) runs, started now: the stored
    release its pointer names (``pointed``), else the cad installed there (``own``). None where neither is."""
    prefix = Path(prefix or sys.prefix)
    found = pointed(prefix)
    if found is not None:
        return found["release"]
    here = _packages_of(prefix)
    installed = own(here) if here is not None else None
    return installed[0] if installed is not None else None


def point(path: str | os.PathLike[str] | None, *, previous: str | None = None,
          prefix: str | os.PathLike[str] | None = None) -> dict[str, Any] | None:
    """The environment at ``prefix`` (this one) pointed at the stored release at ``path``, for the cad installed there
    now (``own``); ``previous``: the stored release it ran before, kept for the way back and from ``clean``. With no
    ``path``, the pointer removed: the environment runs its own packages. Written whole or not at all: a process
    starting meanwhile reads the pointer before or this one. What was written. ``OSError`` where it cannot be, or
    where ``path`` is no stored release or the environment holds no cad to write it for."""
    from cad._internal.atomic_replace import write_bytes_atomic

    prefix = Path(prefix or sys.prefix)
    target = prefix / POINTER
    if path is None:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return None
    kept = marker(path)
    here = _packages_of(prefix)
    installed = own(here) if here is not None else None
    if kept is None:
        raise OSError(f"{path} is no stored release")
    if here is None or installed is None:
        raise OSError(f"{prefix} holds no cad to point from")
    record = installed[1]
    stamp = record.stat()
    written = {"pointer": 1, "python": tag(), "record": record.relative_to(here).as_posix(),
               "stamp": [stamp.st_mtime_ns, stamp.st_size], "path": str(Path(path)), "release": kept["release"],
               "previous": previous, "at": time.time()}
    write_bytes_atomic(target, json.dumps(written, sort_keys=True).encode("utf-8"))
    return written


def restore(kept: dict[str, Any] | None, *, prefix: str | os.PathLike[str] | None = None) -> None:
    """The pointer put back as it was read before a switch (``pointer``'s answer: None, none)."""
    from cad._internal.atomic_replace import write_bytes_atomic

    target = Path(prefix or sys.prefix) / POINTER
    if kept is None:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return
    write_bytes_atomic(target, json.dumps(kept, sort_keys=True).encode("utf-8"))


# --- a release built, run once, and named -----------------------------------------------------------------------------


def build(requirement: str, *, uv: str, run: Run, timeout: float = BUILD_SECONDS) -> Path:
    """``requirement`` (``cad==<release>``, or a range) installed whole into a new folder of the store, for this
    environment's interpreter: ``uv pip install --target``, cad's index entry read afresh, the person's uv settings
    as they are. The folder, which is no release yet (``verify``, ``publish``). ``Failed`` where uv did not end well:
    the folder is gone, and nothing that runs was touched."""
    store = root()
    store.mkdir(parents=True, exist_ok=True)
    staged = store / f"{BUILDING}{os.getpid()}-{os.urandom(4).hex()}"
    code, said = run([uv, "pip", "install", "--python", sys.executable, "--target", str(staged), "--link-mode", LINK,
                      "--refresh-package", "cad", requirement], timeout)
    if code != 0:
        _delete(staged)
        raise Failed("build", code, said)
    return staged


def verify(staged: str | os.PathLike[str], *, run: Run, timeout: float = VERIFY_SECONDS) -> str:
    """The release built at ``staged`` run once, as a process of this environment would run it: this interpreter,
    nothing on its import path but the standard library and that folder, and the release's own check of itself
    (``cad_server._internal.selftest``: it imports what its command and its server import, and says ``cad
    <release>`` last). The release it says. ``Failed`` where it does not end well or says none: the folder is
    gone."""
    code, said = run([sys.executable, "-I", "-S", "-c", VERIFY, str(staged)], timeout)
    lines = [line.strip() for line in (said or "").splitlines() if line.strip()]
    release = lines[-1][len("cad "):] if lines and lines[-1].startswith("cad ") else ""
    if code != 0 or not release or own(staged) is None or own(staged)[0] != release:  # type: ignore[index]
        _delete(Path(staged))
        raise Failed("verify", code, said)
    return release


def publish(staged: str | os.PathLike[str], release: str) -> Path:
    """The verified build at ``staged`` made the stored release ``release``: its marker written, then the folder
    renamed to its name (``folder``). Where that release is stored already, whole, it stays and ``staged`` goes; a
    folder of that name with no marker is moved out of the way first. The stored release. ``OSError`` where the
    rename is refused for good."""
    from cad._internal.atomic_replace import write_bytes_atomic

    staged, final = Path(staged), folder(release)
    if marker(final) is not None:
        _delete(staged)
        return final
    if final.exists():
        _aside(final)
    write_bytes_atomic(staged / MARKER, json.dumps(
        {"store": 1, "release": release, "python": tag(), "built": time.time()}, sort_keys=True).encode("utf-8"))
    try:
        _rename(staged, final)
    except OSError:
        if marker(final) is None:
            raise
        _delete(staged)  # another build of the same release was named first: that one is the release
    return final


# --- releases removed -------------------------------------------------------------------------------------------------


def _rename(source: Path, target: Path) -> None:
    for wait in RENAME_WAITS:
        time.sleep(wait)
        try:
            os.rename(source, target)
            return
        except PermissionError:
            if os.name != "nt":
                raise
    os.rename(source, target)


def _aside(path: Path) -> Path:
    """``path`` renamed to a ``.trash-`` name beside it, then deleted as far as it can be (``_delete``). ``OSError``
    where the rename is refused: on Windows, a file in it is open."""
    trash = path.with_name(f"{TRASH}{path.name}-{os.urandom(4).hex()}")
    os.rename(path, trash)
    _delete(trash)
    return trash


def _delete(path: Path) -> bool:
    """``path`` deleted, as far as the system allows; whether it is gone."""
    shutil.rmtree(path, ignore_errors=True)
    return not path.exists()


def remove(path: str | os.PathLike[str]) -> bool:
    """The stored release at ``path`` removed, unless a process runs it (see the module): whether it was taken. A
    folder with no marker is no release, and goes."""
    path = Path(path)
    if os.name == "nt":
        try:
            _aside(path)
        except OSError:
            return False
        return True
    try:
        handle = open(path / MARKER, "rb")  # noqa: SIM115 - held while the folder is renamed
    except FileNotFoundError:
        handle = None
    except OSError:
        return False
    try:
        if handle is not None:
            import fcntl

            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False  # a process runs it
            except OSError:
                pass  # a file system with no locks: nothing can say it is in use
        try:
            _aside(path)
        except OSError:
            return False
        return True
    finally:
        if handle is not None:
            handle.close()


def clean(keep: Iterable[str | os.PathLike[str] | None] = (), *, now: float | None = None) -> list[str]:
    """The store tidied. First a pointer of this environment that no process would take (``pointed``: written for
    an install of cad that has been replaced since, or naming a release that is gone) is removed: it means nothing.
    Then each stored release is removed that is not one of ``keep``, not the one this environment's pointer names
    nor the one it ran before (``"previous"``), not the one this process runs, and that no process runs
    (``remove``); each ``.trash-`` folder is deleted as far as it can be; and each ``.building-`` folder older than
    ``ABANDONED_SECONDS``, whose build died. The names removed. Never raises."""
    now = time.time() if now is None else now
    removed: list[str] = []
    try:
        if pointer() is not None and pointed() is None:
            point(None)
        found = pointer() or {}
        kept = {os.path.normcase(os.path.abspath(str(path))) for path in
                (*keep, found.get("path"), found.get("previous"), running()) if path}
        entries = sorted(os.scandir(root()), key=lambda entry: entry.name)
    except OSError:
        return removed
    for entry in entries:
        path = Path(entry.path)
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name.startswith(TRASH):
                if _delete(path):
                    removed.append(entry.name)
            elif entry.name.startswith(BUILDING):
                if now - entry.stat().st_mtime > ABANDONED_SECONDS and _delete(path):
                    removed.append(entry.name)
            elif os.path.normcase(os.path.abspath(entry.path)) not in kept and remove(path):
                removed.append(entry.name)
        except OSError:
            continue
    return removed
