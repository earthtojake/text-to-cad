"""Find OpenSCAD's command line and ask it its version; the environment every run of it gets.

The ``openscad`` integration's probe (``cad.registry.INTEGRATIONS["openscad"]``), run by the library's one
helper for the external programs our code runs (``cad._internal.programs``), the standard library alone, so
``cad.scad``'s reader and operations and the server's commands and viewer find and run it the same way. The
program is the person's own OpenSCAD -- there is no package of it to carry -- found by ``CAD_OPENSCAD``
(refused unless it names an ``openscad``: ``openscad.exe`` on Windows, ``OpenSCAD`` the macOS bundle's binary),
then on ``PATH``, then where its installer puts it (``installed``). Only a file of the program's own name is
ever run, and every run is headless: no display to reach, and OpenSCAD's own settings, cache and temp files in
a private folder of the run's (``programs.headless_env``), so a run neither opens a window nor touches the
person's preferences. One thing is kept of the person's: their OpenSCAD libraries. An ``include <MCAD/...>`` or
``use <BOSL2/...>`` resolves through ``OPENSCADPATH`` and the user library folder of their real home, which
the private home would hide, so a run's ``OPENSCADPATH`` names the caller's entries and that folder
(``libraries``): a library is an input of the program, as a Python package is of a script.

OpenSCAD's version is two components in a release (``2021.01``) and three in a snapshot (``2025.03.07``),
which the helper's three-number pattern would not read: ``version`` reads it here, and
``programs.version_tuple`` compares it with the minimum as it compares any.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cad.registry import INTEGRATIONS

from cad._internal import programs

__all__ = ["NAMES", "OPENSCAD", "OpenscadMissing", "check_version", "find", "headless_env", "install_hint",
           "installed", "libraries", "private_run", "quiet", "ready", "version"]

_PROBE = INTEGRATIONS["openscad"].probe
assert _PROBE is not None
#: The program by its file name on each platform: the command, Windows's, and the macOS bundle's own binary.
NAMES = ("openscad", "openscad.exe", "OpenSCAD")
_VERSION = re.compile(r"(\d{4}\.\d{2}(?:\.\d+)?)")
# OpenSCAD's own noise, which says nothing about the program: Qt's and fontconfig's lines on a headless run.
_NOISE = ("Fontconfig", "QStandardPaths", "qt.qpa", "QXcbConnection", "Qt: Session management")


class OpenscadMissing(programs.ProgramMissing):
    """No usable OpenSCAD: its words end in the install hint."""


def install_hint() -> str:
    return _PROBE.install_hint


def installed() -> list[Path]:
    """Where OpenSCAD's installer puts its program: the macOS bundle's binary (in ``/Applications`` or the
    person's), Program Files on Windows, ``/usr/bin`` and ``/usr/local/bin`` elsewhere."""
    if sys.platform == "darwin":
        bundle = Path("OpenSCAD.app") / "Contents" / "MacOS" / "OpenSCAD"
        return [Path("/Applications") / bundle, Path(os.path.expanduser("~")) / "Applications" / bundle]
    if sys.platform.startswith("win"):
        places = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                  os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
        return [Path(place) / "OpenSCAD" / "openscad.exe" for place in places]
    return [Path("/usr/bin/openscad"), Path("/usr/local/bin/openscad")]


#: OpenSCAD as the helper runs it: the override, then PATH (the person's own OpenSCAD IS what is run,
#: headless), then its installer's places.
OPENSCAD = programs.Program.from_probe(_PROBE, names=NAMES, installed=lambda: installed(), version_args=("--version",),
                                        title="OpenSCAD 2021.01")


def _missing(error: programs.ProgramMissing) -> OpenscadMissing:
    return OpenscadMissing(str(error))


def find() -> Path:
    """The OpenSCAD to run: ``CAD_OPENSCAD`` when it is set (a file of the program's name, else refused), else the
    one on ``PATH``, else the one in its installer's place; else ``OpenscadMissing`` saying how to install it."""
    try:
        return programs.find(OPENSCAD)
    except OpenscadMissing:
        raise
    except programs.ProgramMissing as error:
        raise _missing(error) from None


def libraries() -> list[str]:
    """Where OpenSCAD looks for a library this process would: the caller's ``OPENSCADPATH`` entries, in their
    order, then the user library folder of the person's real home where it is a folder --
    ``$XDG_DATA_HOME/OpenSCAD/libraries`` (``~/.local/share/OpenSCAD/libraries``) on Linux,
    ``~/Documents/OpenSCAD/libraries`` on macOS and Windows -- each once. OpenSCAD's own installation
    libraries (MCAD) it finds beside itself, and the program's folder it searches first, so neither is named."""
    found = [entry for entry in os.environ.get("OPENSCADPATH", "").split(os.pathsep) if entry.strip()]
    home = Path(os.path.expanduser("~"))
    if sys.platform.startswith("win") or sys.platform == "darwin":
        user = home / "Documents" / "OpenSCAD" / "libraries"
    else:
        data = os.environ.get("XDG_DATA_HOME", "").strip()
        user = (Path(data) if data else home / ".local" / "share") / "OpenSCAD" / "libraries"
    if user.is_dir():
        found.append(str(user))
    return list(dict.fromkeys(found))


def headless_env(root: str | os.PathLike) -> dict[str, str]:
    """The environment a run gets (``programs.headless_env``: no display, every home inside ``root``), with
    the person's libraries kept reachable (``libraries``, as ``OPENSCADPATH``), worked out from this process's
    environment and home before the private ones stand in for them."""
    paths = libraries()
    env = programs.headless_env(root)
    env.pop("OPENSCADPATH", None)
    if paths:
        env["OPENSCADPATH"] = os.pathsep.join(paths)
    return env


@contextmanager
def private_run(prefix: str = "cad-openscad-") -> Iterator[tuple[Path, dict[str, str]]]:
    """A private folder and the headless environment inside it (``headless_env``), for one run; the folder is
    removed afterwards. Yields ``(folder, env)``."""
    with tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True) as scratch:
        yield Path(scratch), headless_env(scratch)


def quiet(text: str) -> str:
    """What OpenSCAD said, without Qt's and fontconfig's noise."""
    return "\n".join(line for line in (text or "").splitlines()
                     if line.strip() and not any(line.lstrip().startswith(noise) for noise in _NOISE))


def version(path: Path) -> str | None:
    """What OpenSCAD at ``path`` says its version is (``2021.01``, ``2025.03.07``), asked headless; None when it
    does not run or says none."""
    with private_run("cad-openscad-version-") as (_folder, env):
        try:
            done = subprocess.run([str(path), "--version"], env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, timeout=120, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
    if done.returncode != 0:
        return None
    match = _VERSION.search(f"{done.stdout}\n{done.stderr}")
    return match.group(1) if match else None


def check_version(path: Path, found: str | None) -> str:
    """``found`` when it is OpenSCAD 2021.01 or newer; else ``OpenscadMissing``, saying both."""
    try:
        return programs.check_version(OPENSCAD, path, found)
    except programs.ProgramMissing as error:
        raise _missing(error) from None


# The programs found and checked in this process, by their path and stamp: a render asks once, not per call;
# a program that is missing is looked for again each time (no process is run to find one).
_READY: dict[tuple[str, int, int], str] = {}


def ready() -> tuple[Path, str]:
    """The OpenSCAD to run, found and its version checked: ``(path, version)``. A program checked once in
    this process is not asked again while its file is the same."""
    path = find()
    try:
        info = path.stat()
        stamp = (str(path), info.st_size, info.st_mtime_ns)
    except OSError:
        stamp = (str(path), -1, 0)
    known = _READY.get(stamp)
    if known is None:
        known = _READY[stamp] = check_version(path, version(path))
    return path, known
