"""CalculiX (``ccx``), the program every study is solved by: found, checked and run. cad meshes, writes CalculiX's input
(:mod:`._files`), runs it and reads its output; CalculiX assembles and solves.

The ``calculix`` integration's probe (``cad.registry.INTEGRATIONS["calculix"]``: the program, its minimum, its install
hint and ``CAD_CCX``), run by the library's one helper for the external programs our code runs
(``cad._internal.programs``). ``ccx`` is installed by the person: ``CAD_CCX`` names the program, else the first of :data:`NAMES` on PATH, else the
``ccx`` a FreeCAD install carries (FreeCAD's own FEM solves with it). One that is missing, or older than
:data:`CCX`'s minimum, is an error naming how to install it; cad downloads nothing and solves with nothing else.
Every run is headless, in a private folder with homes of its own (``cad._internal.programs``), and on one thread, so
the same study prints the same numbers. Stdlib only.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from cad._internal import programs
from cad.registry import INTEGRATIONS

__all__ = ["CCX", "CCX_ENV", "NAMES", "TIMEOUT_S", "CalculixMissingError", "Ccx", "find_ccx", "install_hint", "run"]

_PROBE = INTEGRATIONS["calculix"].probe
assert _PROBE is not None
#: The environment variable naming the ``ccx`` program.
CCX_ENV = _PROBE.override
#: What ``ccx`` is called on PATH: the plain name, then the versioned names some packages install.
NAMES = ("ccx", "ccx_2.23", "ccx_2.22", "ccx_2.21", "ccx_2.20")
#: The longest one solve may take (s): past it CalculiX is stopped and the study says so.
TIMEOUT_S = 3600.0
_JOB = "study"


class CalculixMissingError(programs.ProgramMissing):
    """No CalculiX program cad can run."""


def install_hint() -> str:
    return _PROBE.install_hint


def _in_freecad() -> list[str]:
    """Where each platform's FreeCAD installer puts the ``ccx`` it carries, newest first where the folder names a
    version. A Linux FreeCAD (a distribution's package, the AppImage) carries none cad can find: PATH or
    ``CAD_CCX`` names it."""
    if sys.platform == "darwin":
        apps = [Path("/Applications"), Path.home() / "Applications"]
        return [str(app / "FreeCAD.app" / "Contents" / "Resources" / "bin" / "ccx") for app in apps]
    if sys.platform == "win32":
        # The installer's folder is "FreeCAD 1.1", for every user under Program Files or for one under Programs:
        # exactly that name, newest version first by number (1.10 after 1.9), never by spelling.
        roots = [Path(os.environ[name]) / under for name, under in (("ProgramFiles", ""), ("LOCALAPPDATA", "Programs"))
                 if os.environ.get(name)]
        found = []
        for root in roots:
            for folder in (root.iterdir() if root.is_dir() else ()):
                if version := re.fullmatch(r"FreeCAD (\d+)\.(\d+)", folder.name):
                    found.append(((int(version.group(1)), int(version.group(2))), folder))
        return [str(folder / "bin" / "ccx.exe") for _version, folder in sorted(found, key=lambda each: each[0], reverse=True)]
    return []


@dataclass(frozen=True)
class Ccx:
    """A ``ccx`` program that runs: its path and the version it reports ("2.23")."""

    path: str
    version: str

    @property
    def label(self) -> str:
        """The result's ``solver``: "calculix 2.23 (C3D10)"."""
        return f"calculix {self.version} (C3D10)"


def _installed() -> list[Path]:
    """Where ``ccx`` may be, in order: :data:`NAMES` on PATH, as the engine searches it (``executables.find``: its
    absolute folders alone, never the working folder), then a FreeCAD install's."""
    from cad.engine.executables import find

    return [Path(path) for path in (*map(find, NAMES), *_in_freecad()) if path]


class _Ccx(programs.Program):
    def is_named(self, path: Path) -> bool:
        """``ccx`` or a versioned build's name (``ccx_2.24``, ``ccx_2.23_MT``), so a newer one can be named outright."""
        return re.fullmatch(r"ccx(_\d+\.\d+\w*)?(\.exe)?", path.name, re.IGNORECASE) is not None


#: ``ccx`` as the helper finds it. The oldest CalculiX cad runs is 2.20: C3D10 elements and ``*TRANSFORM`` behave as
#: written here from it. ``search_path`` is off because :func:`_installed` searches PATH, for the versioned names too.
CCX = _Ccx.from_probe(_PROBE, names=NAMES, installed=_installed, title=f"CalculiX {_PROBE.minimum}", search_path=False)


def find_ccx() -> Ccx:
    """The ``ccx`` to run: the file ``CAD_CCX`` names, else :func:`_installed`'s first. Raises
    :class:`CalculixMissingError` naming why and how to install it."""
    try:
        path = programs.find(CCX).absolute()  # relative, it would be read in the folder a solve runs in
        return Ccx(path=str(path), version=programs.check_version(CCX, path, _version(path)))
    except programs.ProgramMissing as error:
        raise CalculixMissingError(str(error)) from None


def _version(path: Path) -> str | None:
    """What ``ccx -v`` says after "This is Version": two numbers, and it exits non-zero, so the helper's own ask does
    not fit it. ``None`` when it says no version."""
    with programs.private_run("cad-ccx-") as (_folder, env):
        try:
            said = subprocess.run([str(path), "-v"], capture_output=True, text=True, errors="replace", timeout=30,
                                  env=_on_one_thread(env), stdin=subprocess.DEVNULL).stdout
        except (OSError, subprocess.SubprocessError) as error:
            raise programs.ProgramMissing(f"{path} does not run ({error}): {install_hint()}") from error
    found = re.search(r"Version\s+(\d+\.\d+)", said)
    return found.group(1) if found else None


def _on_one_thread(env: dict[str, str]) -> dict[str, str]:
    """``env`` with every CalculiX thread count set to one.

    On several threads CalculiX sums in a different order each run, so the same study printed different numbers; one
    thread was no slower on a 61k-DOF static solve, and studies solving side by side use the other cores.
    """
    return {**env, **dict.fromkeys(("OMP_NUM_THREADS", "CCX_NPROC_EQUATION_SOLVER", "CCX_NPROC_STIFFNESS",
                                    "CCX_NPROC_RESULTS"), "1")}


def run(ccx: Ccx, write) -> str:
    """CalculiX on the input ``write(path)`` writes, in a private folder of its own: its .dat. A run that fails, prints
    an error or overruns :data:`TIMEOUT_S` raises RuntimeError with what CalculiX said."""
    with programs.private_run("cad-ccx-") as (folder, env):
        write(folder / f"{_JOB}.inp")
        try:
            done = subprocess.run([ccx.path, "-i", _JOB], cwd=folder, capture_output=True, text=True, errors="replace",
                                  env=_on_one_thread(env), stdin=subprocess.DEVNULL, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"CalculiX did not finish in {TIMEOUT_S:.0f} s and was stopped; a coarser mesh "
                               "(mesh.size_mm) solves sooner") from error
        said = (done.stdout or "") + (done.stderr or "")
        errors = [line.strip() for line in said.splitlines() if "*ERROR" in line]
        dat = folder / f"{_JOB}.dat"
        if done.returncode != 0 or errors or not dat.is_file():
            detail = "; ".join(errors[:3]) or "\n  ".join(said.strip().splitlines()[-8:])
            raise RuntimeError(f"CalculiX failed (exit {done.returncode}): {detail}")
        return dat.read_text(errors="replace")
