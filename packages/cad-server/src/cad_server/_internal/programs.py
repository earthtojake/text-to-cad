"""The external programs our code runs: found, checked and run headless, one way for every integration.

An integration of kind C (an external program our code runs, ``cad.registry``) declares a ``Probe``: the
program's name, the oldest version our code supports, what to say when it is missing, and the variable
that names it outright. This module is the one way the server finds and runs such a program:

* **Found**, by the probe's variable first (refused unless the file it names has the program's own
  name: never a desktop app, a wrapper or a launcher), then ``PATH``, then the places the program's own
  installer puts it (``Program.installed``). Only a file of the program's name is ever returned.
* **Checked**: its version, asked of it headless, at least the probe's minimum.
* **Run headless**: no display to reach (``DISPLAY``, ``WAYLAND_DISPLAY`` removed), and every home it
  reads or writes inside a private folder removed afterwards (``private_run``), so a run neither opens a
  window nor touches the person's settings, data, cache, documents or locks.
* **Missing**: one result, ``ProgramMissing``, whose words end in the probe's install hint.

KiCad's ``kicad-cli`` is its first user (``cad_server.kicad.install``).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["DISPLAY", "Program", "ProgramMissing", "check_version", "find", "headless_env", "private_run",
           "version", "version_tuple"]

# What a child would need to reach a desktop: never handed to a program we run.
DISPLAY = ("DISPLAY", "WAYLAND_DISPLAY")


class ProgramMissing(RuntimeError):
    """No usable copy of an external program: its words end in the program's install hint."""


@dataclass(frozen=True)
class Program:
    """One external program, as its integration's probe declares it (``cad.registry.Probe``), with the
    file names it has on each platform, where its installer puts it, the extra homes it reads (its own
    variables, each a folder under the private root), and how its version is asked."""

    name: str
    minimum: tuple[int, ...]
    install_hint: str
    override: str
    names: tuple[str, ...]
    installed: Callable[[], list[Path]] = field(default=lambda: [], compare=False)
    homes: Mapping[str, str] = field(default_factory=dict)
    version_args: tuple[str, ...] = ("version",)

    @classmethod
    def from_probe(cls, probe, **options) -> "Program":
        return cls(probe.program, version_tuple(probe.minimum), probe.install_hint, probe.override, **options)

    def is_named(self, path: Path) -> bool:
        """Whether ``path`` is a file of this program's own name (case-insensitively on Windows)."""
        if sys.platform.startswith("win"):
            return path.name.lower() in {name.lower() for name in self.names}
        return path.name in self.names


def find(program: Program) -> Path:
    """The copy of ``program`` to run: its override when that is set (a file of the program's name, else
    refused), else the program on ``PATH``, else the one its installer put in the usual place."""
    explicit = os.environ.get(program.override, "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not program.is_named(path):
            raise ProgramMissing(f"{program.override} names {path}, which is not {program.name}: name the "
                                 f"program itself, never an app or a launcher; {program.install_hint}")
        if path.is_file():
            return path
        raise ProgramMissing(f"{program.override} names {path}, which is not a file: {program.install_hint}")
    found = shutil.which(program.name)
    if found and program.is_named(Path(found)):
        return Path(found)
    for candidate in program.installed():
        if program.is_named(candidate) and candidate.is_file():
            return candidate
    raise ProgramMissing(f"{program.name} was not found: {program.install_hint}")


def headless_env(root: str | os.PathLike, homes: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment a run gets: this process's, with no display to reach and every home inside
    ``root``, a private folder the caller removes afterwards; the folders are made here.

    - ``HOME``: never empty, and where macOS keeps its ``~/Library`` folders, so it covers them.
      ``TMPDIR`` holds a program's instance locks.
    - Linux and other POSIX: ``XDG_CONFIG_HOME``, ``XDG_DATA_HOME``, ``XDG_CACHE_HOME`` and
      ``XDG_STATE_HOME``.
    - Windows: ``USERPROFILE``, ``APPDATA``, ``LOCALAPPDATA`` and ``TEMP`` / ``TMP``.
    - ``homes``: the program's own variables, each a folder under ``root`` by the name given."""
    root = Path(root)
    home, tmp = root / "home", root / "tmp"
    folders = [home, tmp]
    env = {key: value for key, value in os.environ.items() if key not in DISPLAY}
    env.update(HOME=os.fspath(home), TMPDIR=os.fspath(tmp))
    for variable, folder in (homes or {}).items():
        folders.append(root / folder)
        env[variable] = os.fspath(root / folder)
    if sys.platform.startswith("win"):
        roaming, local = home / "AppData" / "Roaming", home / "AppData" / "Local"
        folders += [roaming, local]
        env.update(USERPROFILE=os.fspath(home), APPDATA=os.fspath(roaming), LOCALAPPDATA=os.fspath(local),
                   TEMP=os.fspath(tmp), TMP=os.fspath(tmp))
    elif sys.platform != "darwin":
        xdg = {"XDG_CONFIG_HOME": home / ".config", "XDG_DATA_HOME": home / ".local" / "share",
               "XDG_CACHE_HOME": home / ".cache", "XDG_STATE_HOME": home / ".local" / "state"}
        folders += list(xdg.values())
        env.update({name: os.fspath(path) for name, path in xdg.items()})
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
    return env


@contextmanager
def private_run(prefix: str = "cad-program-", homes: Mapping[str, str] | None = None
                ) -> Iterator[tuple[Path, dict[str, str]]]:
    """A private folder and the headless environment inside it, for one run; the folder (with whatever
    the program left in it) is removed afterwards. Yields ``(folder, env)``."""
    with tempfile.TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=True) as scratch:
        yield Path(scratch), headless_env(scratch, homes)


def version_tuple(version: str) -> tuple[int, ...]:
    """The first three numbers of ``version``, to compare with a minimum: ``(9, 0, 1)``."""
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])


def version(program: Program, path: Path) -> str | None:
    """What the program says its version is (``9.0.1``), asked headless; None when it does not run."""
    with private_run(f"cad-{program.name}-", program.homes) as (_scratch, env):
        try:
            done = subprocess.run([str(path), *program.version_args], env=env, capture_output=True, text=True,
                                  timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
    if done.returncode != 0:
        return None
    match = re.search(r"(\d+\.\d+\.\d+)", f"{done.stdout}\n{done.stderr}")
    return match.group(1) if match else None


def check_version(program: Program, path: Path, found: str | None) -> str:
    """``found`` when it is at least the program's minimum; else ``ProgramMissing``, saying both."""
    if found is not None and version_tuple(found)[:len(program.minimum)] >= program.minimum:
        return found
    minimum = ".".join(str(part) for part in program.minimum)
    raise ProgramMissing(f"{path} reports {found or 'no version'}; cad needs {program.name} {minimum} or newer: "
                         f"{program.install_hint}")
