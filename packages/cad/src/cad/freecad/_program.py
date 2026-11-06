"""FreeCAD (``freecadcmd``), the program every toolpath is planned and posted by: found, checked and run. cad cam reads
the part, writes the job FreeCAD runs, and checks what comes back; FreeCAD's CAM workbench plans the paths and its post
processors write the G-code.

FreeCAD is installed by the person: ``CAD_FREECAD`` names the ``freecadcmd`` program, else the first of :data:`NAMES` on
PATH, else the place each platform's installer puts it (:func:`_installed`). One that is missing, or older than
:data:`FREECADCMD`'s minimum, is an error naming how to install it; cad downloads nothing and plans with nothing else.

:func:`run` hands ``_job.py`` a plan (JSON: the part as a BREP, the stock, the tools, the operations) in a private
folder with homes of its own (``cad._internal.programs``) and reads back what FreeCAD made: each operation's path
commands and the posted files. FreeCAD's own settings and caches go in that folder too (``FREECAD_USER_HOME``), so a
plan leaves nothing in the person's FreeCAD. Stdlib, and the engine's ``executables``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from cad._internal import programs
from cad.engine import executables

__all__ = ["FREECADCMD", "FREECAD_ENV", "NAMES", "TIMEOUT_S", "FreeCAD", "FreecadMissingError", "find_freecad",
           "install_hint", "run"]

#: The environment variable naming the ``freecadcmd`` program.
FREECAD_ENV = "CAD_FREECAD"
#: What it is called on PATH: the name the installers use, then the older capitalised one some packages keep.
NAMES = ("freecadcmd", "FreeCADCmd")
#: The longest one plan may take (s): past it FreeCAD is stopped and the plan says so.
TIMEOUT_S = 1800.0
_SCRIPT = Path(__file__).with_name("_job.py")
#: FreeCAD's own settings and caches, a folder of the private run's.
_HOMES = {"FREECAD_USER_HOME": "freecad"}


class FreecadMissingError(programs.ProgramMissing):
    """No FreeCAD program cad can run."""


def install_hint() -> str:
    return ("install FreeCAD 1.1 or newer from https://www.freecad.org/downloads.php (macOS: the .dmg into "
            "Applications; Windows: the installer; Linux: the AppImage, unpacked with --appimage-extract, its "
            f"squashfs-root/usr/bin/freecadcmd named by {FREECAD_ENV}), or set {FREECAD_ENV} to a freecadcmd "
            "program")


@dataclass(frozen=True)
class FreeCAD:
    """A ``freecadcmd`` that runs: its path and the version it reports ("1.1.4")."""

    path: str
    version: str

    @property
    def label(self) -> str:
        """The result's ``planner``: "freecad 1.1.4"."""
        return f"freecad {self.version}"


def _in_installers() -> list[str]:
    """Where each platform's FreeCAD installer puts ``freecadcmd``, newest first where the folder names a version."""
    if sys.platform == "darwin":
        apps = [Path("/Applications"), Path.home() / "Applications"]
        return [str(app / "FreeCAD.app" / "Contents" / "Resources" / "bin" / "freecadcmd") for app in apps]
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
        return [str(folder / "bin" / "freecadcmd.exe") for _version, folder in sorted(found, key=lambda each: each[0], reverse=True)]
    return ["/usr/bin/freecadcmd", "/usr/local/bin/freecadcmd"]


def _installed() -> list[Path]:
    """Where ``freecadcmd`` may be, in order: :data:`NAMES` on PATH, as the engine searches it (``executables.find``: its
    absolute folders alone, never the working folder), then an installer's place."""
    return [Path(path) for path in (*map(executables.find, NAMES), *_in_installers()) if path]


class _Freecadcmd(programs.Program):
    def is_named(self, path: Path) -> bool:
        """``freecadcmd`` in either spelling, on Windows with its ``.exe``: never ``FreeCAD``, the desktop app."""
        return re.fullmatch(r"freecadcmd(\.exe)?", path.name, re.IGNORECASE) is not None


#: ``freecadcmd`` as the helper finds it. The oldest FreeCAD cad runs is 1.1: 1.0 renamed the Path workbench CAM and
#: moved its operations to ``Path.Op``; 1.1 replaced the tool bit files with ``Path.Tool.toolbit``, which ``_job.py``
#: builds its tools with. ``search_path`` is off because :func:`_installed` searches PATH, as the engine does.
FREECADCMD = _Freecadcmd("freecadcmd", (1, 1), install_hint(), FREECAD_ENV, NAMES, installed=lambda: _installed(),
                         homes=_HOMES, title="FreeCAD 1.1", search_path=False)


def find_freecad() -> FreeCAD:
    """The ``freecadcmd`` to run: the file ``CAD_FREECAD`` names, else :func:`_installed`'s first. Raises
    :class:`FreecadMissingError` naming why and how to install it."""
    try:
        path = programs.find(FREECADCMD).absolute()  # relative, it would be read in the folder a plan runs in
        return FreeCAD(path=str(path), version=programs.check_version(FREECADCMD, path, _version(path)))
    except programs.ProgramMissing as error:
        raise FreecadMissingError(str(error)) from None


def _version(path: Path) -> str | None:
    """What ``freecadcmd --version`` says, "FreeCAD 1.1.4 Revision: ...": two numbers or three, so the helper's own ask
    does not fit it. ``None`` when it says no version."""
    with programs.private_run("cad-freecad-", _HOMES) as (_folder, env):
        try:
            said = subprocess.run([str(path), "--version"], capture_output=True, text=True, errors="replace", timeout=60,
                                  env=env, stdin=subprocess.DEVNULL).stdout
        except (OSError, subprocess.SubprocessError) as error:
            raise programs.ProgramMissing(f"{path} does not run ({error}): {install_hint()}") from error
    found = re.search(r"FreeCAD\s+(\d+\.\d+(?:\.\d+)?)", said)
    return found.group(1) if found else None


def run(freecad: FreeCAD, plan: dict, write_part) -> tuple[dict, dict[str, str]]:
    """FreeCAD on ``plan`` in a private folder of its own, the part written there by ``write_part(path)`` (a BREP): what
    ``_job.py`` reports (``operations``: each one's path commands; ``posts``: the posted file names) and each
    posted file's text by name. A run that fails, reports an error or overruns :data:`TIMEOUT_S` raises RuntimeError
    with what FreeCAD said."""
    with programs.private_run("cad-freecad-", _HOMES) as (folder, env):
        write_part(folder / "part.brep")
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        env["CAD_CAM_FOLDER"] = str(folder)
        try:
            done = subprocess.run([freecad.path, str(_SCRIPT)], cwd=folder, capture_output=True, text=True,
                                  errors="replace", env=env, stdin=subprocess.DEVNULL, timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"FreeCAD did not finish planning in {TIMEOUT_S:.0f} s and was stopped") from error
        result = folder / "result.json"
        if not result.is_file():
            said = (done.stdout or "") + (done.stderr or "")
            lines = [line.strip() for line in said.replace("\r", "\n").splitlines() if line.strip() and "%)" not in line]
            raise RuntimeError(f"FreeCAD failed (exit {done.returncode}): " + "\n  ".join(lines[-8:]))
        report = json.loads(result.read_text(encoding="utf-8"))
        if report.get("error"):
            raise RuntimeError(f"FreeCAD failed: {report['error']}")
        posted = {name: (folder / name).read_text(encoding="utf-8") for name in report.get("posts", ())}
        return report, posted
