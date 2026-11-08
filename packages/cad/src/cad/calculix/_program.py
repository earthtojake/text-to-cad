"""CalculiX (``ccx``), the program every study is solved by: found, checked and run. cad meshes, writes CalculiX's input
(:mod:`._files`), runs it and reads its output; CalculiX assembles and solves.

The ``calculix`` integration's probe (``cad.registry.INTEGRATIONS["calculix"]``: the program, its minimum, its install
hint and ``CAD_CCX``), run by the library's one helper for the external programs our code runs
(``cad._internal.programs``). ``ccx`` is the integration's extra's, ``cad[calculix]``: the ``cad-ccx`` package carries
CalculiX's own ``ccx``, unmodified, for each platform, and says where it is (``cad_ccx.executable()``). ``CAD_CCX`` names
another (a build of the person's own); a ``ccx`` on PATH, or a FreeCAD's, is never run, so every study on every device
solves with the pinned release. One that is missing, or older than :data:`CCX`'s minimum, is an error naming how to
install it. Every run is headless, in a private folder with homes of its own (``cad._internal.programs``), and on one
thread, so the same study prints the same numbers; the input of a run may be kept (:func:`keeping_deck`). Stdlib only:
the ``cad_ccx`` package is read when a study looks for the program, never at import.
"""

from __future__ import annotations

import contextvars
import re
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cad._internal import programs
from cad.registry import INTEGRATIONS

__all__ = ["CCX", "CCX_ENV", "NAMES", "THREAD_VARIABLES", "TIMEOUT_S", "CalculixMissingError", "Ccx", "carried",
           "find_ccx", "install_hint", "keeping_deck", "run"]

_PROBE = INTEGRATIONS["calculix"].probe
assert _PROBE is not None
#: The environment variable naming the ``ccx`` program.
CCX_ENV = _PROBE.override
#: What ``ccx`` is called: the plain name, the Windows one, and the versioned names some builds have, so one can be
#: named outright with ``CAD_CCX``.
NAMES = ("ccx", "ccx.exe")
#: The longest one solve may take (s): past it CalculiX is stopped and the study says so.
TIMEOUT_S = 3600.0
#: Every variable CalculiX reads a thread count from; a run sets each to one.
THREAD_VARIABLES = ("OMP_NUM_THREADS", "CCX_NPROC_EQUATION_SOLVER", "CCX_NPROC_STIFFNESS", "CCX_NPROC_RESULTS")
_JOB = "study"
# Where the input of each run that succeeds is copied, while a caller keeps it (``keeping_deck``).
_DECK: contextvars.ContextVar[Path | None] = contextvars.ContextVar("cad_calculix_deck", default=None)


class CalculixMissingError(programs.ProgramMissing):
    """No CalculiX program cad can run."""


def install_hint() -> str:
    return _PROBE.install_hint


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
    """The ``ccx`` the integration's extra installed: the ``cad-ccx`` package's, where this environment holds it."""
    try:
        import cad_ccx
    except ModuleNotFoundError:
        return []
    try:
        return [Path(cad_ccx.executable())]
    except FileNotFoundError:  # a cad-ccx built with no program for this platform
        return []


def carried() -> bool:
    """Whether this process can run CalculiX itself: ``CAD_CCX`` names one, or the ``cad-ccx`` package is installed here.
    Else a study runs in the environment of ``cad[calculix]``."""
    import importlib.util
    import os

    return bool(os.environ.get(CCX_ENV, "").strip()) or importlib.util.find_spec("cad_ccx") is not None


class _Ccx(programs.Program):
    def is_named(self, path: Path) -> bool:
        """``ccx`` or a versioned build's name (``ccx_2.24``, ``ccx_2.23_MT``), so a newer one can be named outright."""
        return re.fullmatch(r"ccx(_\d+\.\d+\w*)?(\.exe)?", path.name, re.IGNORECASE) is not None


#: ``ccx`` as the helper finds it. The oldest CalculiX cad runs is 2.20: C3D10 elements and ``*TRANSFORM`` behave as
#: written here from it. ``search_path`` is off: the program is the extra's, never one on PATH.
CCX = _Ccx.from_probe(_PROBE, names=NAMES, installed=_installed, title=f"CalculiX {_PROBE.minimum}", search_path=False)


def find_ccx() -> Ccx:
    """The ``ccx`` to run: the file ``CAD_CCX`` names, else the ``ccx`` package's. Raises
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
    return {**env, **dict.fromkeys(THREAD_VARIABLES, "1")}


@contextmanager
def keeping_deck(path: Path | None) -> Iterator[None]:
    """While it is open, the input of each run that succeeds is copied to ``path`` (each replacing the one before, so
    the last solve's is kept); None keeps nothing. A study's ``deck``: CalculiX's ``.inp`` of the solve it wrote."""
    token = _DECK.set(None if path is None else Path(path))
    try:
        yield
    finally:
        _DECK.reset(token)


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
        if (deck := _DECK.get()) is not None:
            deck.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(folder / f"{_JOB}.inp", deck)
        return dat.read_text(errors="replace")
