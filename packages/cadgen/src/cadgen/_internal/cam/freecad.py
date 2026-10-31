"""FreeCAD (``freecadcmd``): the program every toolpath is planned and posted by. cadgen reads the part, writes the job
FreeCAD runs, and checks what comes back; FreeCAD's CAM workbench plans the paths and its post processors write the
G-code.

FreeCAD is installed by the person: ``CADGEN_FREECAD`` names its ``freecadcmd`` (an absolute path, or a name found on
PATH), else the first of :data:`NAMES` on PATH, else the place each platform's installer puts it (:func:`_installed`).
PATH is searched as the engine searches it for any helper (``executables.find``): its absolute folders only, never the
working folder. One that is missing, or older than
:data:`MINIMUM`, is an error naming how to install it; cadgen downloads nothing and plans with nothing else.

:func:`run` hands ``freecad_job.py`` a plan (JSON: the part as a BREP, the stock, the tools, the operations) in a
folder of its own and reads back what FreeCAD made: each operation's path commands and the posted files. FreeCAD's own
settings and caches go in that folder too (``FREECAD_USER_HOME``), so a plan leaves nothing in the person's FreeCAD.
Stdlib, and the engine's ``executables``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cadgen.engine import executables

__all__ = ["FREECAD_ENV", "MINIMUM", "NAMES", "TIMEOUT_S", "FreeCAD", "FreecadMissingError", "find_freecad",
           "install_hint", "run"]

#: The environment variable naming the ``freecadcmd`` program.
FREECAD_ENV = "CADGEN_FREECAD"
#: What it is called on PATH: the name the installers use, then the older capitalised one some packages keep.
NAMES = ("freecadcmd", "FreeCADCmd")
#: The oldest FreeCAD cadgen runs: 1.0 renamed the Path workbench CAM and moved its operations to ``Path.Op``; 1.1
#: replaced the tool bit files with ``Path.Tool.toolbit``, which ``freecad_job.py`` builds its tools with.
MINIMUM = (1, 1)
#: The longest one plan may take (s): past it FreeCAD is stopped and the plan says so.
TIMEOUT_S = 1800.0
_SCRIPT = Path(__file__).with_name("freecad_job.py")


class FreecadMissingError(RuntimeError):
    """No FreeCAD program cadgen can run."""


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


def _installed() -> list[str]:
    """Where each platform's FreeCAD installer puts ``freecadcmd``, newest first where the folder names a version."""
    if sys.platform == "darwin":
        apps = [Path("/Applications"), Path.home() / "Applications"]
        return [str(app / "FreeCAD.app" / "Contents" / "Resources" / "bin" / "freecadcmd") for app in apps]
    if sys.platform == "win32":
        # The installer's folder is "FreeCAD 1.1", for every user under Program Files or for one under Programs.
        roots = [Path(os.environ[name]) / under for name, under in (("ProgramFiles", ""), ("LOCALAPPDATA", "Programs"))
                 if os.environ.get(name)]
        found = sorted((folder for root in roots for folder in root.glob("FreeCAD *")), key=lambda f: f.name,
                       reverse=True)
        return [str(folder / "bin" / "freecadcmd.exe") for folder in found]
    return ["/usr/bin/freecadcmd", "/usr/local/bin/freecadcmd", "/snap/bin/freecad.cmd"]


def find_freecad() -> FreeCAD:
    """The ``freecadcmd`` to run: ``CADGEN_FREECAD``, else the first of :data:`NAMES` on PATH, else an installer's
    place. Raises :class:`FreecadMissingError` naming why and how to install it."""
    setting = os.environ.get(FREECAD_ENV, "").strip()
    if setting:
        if os.path.basename(setting) == setting:
            path = executables.find(setting)
        else:
            path = setting if os.path.isabs(setting) and os.path.isfile(setting) else None
        if path is None:
            raise FreecadMissingError(f"{FREECAD_ENV} names {setting}, which is not a program (an absolute path, or "
                                      f"a name on PATH): {install_hint()}")
        return _checked(path)
    for name in NAMES:
        if found := executables.find(name):
            return _checked(found)
    for place in _installed():
        if os.path.isfile(place):
            return _checked(place)
    raise FreecadMissingError(f"FreeCAD's freecadcmd was not found: {install_hint()}")


def _checked(path: str) -> FreeCAD:
    """``freecadcmd --version`` says "FreeCAD 1.1.4 Revision: ..."; anything else, or an older version, is no
    FreeCAD cadgen runs."""
    try:
        said = subprocess.run([path, "--version"], capture_output=True, text=True, errors="replace", timeout=60,
                              stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise FreecadMissingError(f"{path} does not run ({error}): {install_hint()}") from error
    found = re.search(r"FreeCAD\s+(\d+)\.(\d+)(?:\.(\d+))?", said)
    if found is None:
        raise FreecadMissingError(f"{path} reports no FreeCAD version: {install_hint()}")
    version = (int(found.group(1)), int(found.group(2)))
    if version < MINIMUM:
        raise FreecadMissingError(f"{path} is FreeCAD {version[0]}.{version[1]}; cadgen needs "
                                  f"{MINIMUM[0]}.{MINIMUM[1]} or newer: {install_hint()}")
    return FreeCAD(path=path, version=".".join(g for g in found.groups() if g is not None))


def run(freecad: FreeCAD, plan: dict, write_part) -> tuple[dict, dict[str, str]]:
    """FreeCAD on ``plan`` in a folder of its own, the part written there by ``write_part(path)`` (a BREP): what
    ``freecad_job.py`` reports (``operations``: each one's path commands; ``posts``: the posted file names) and each
    posted file's text by name. A run that fails, reports an error or overruns :data:`TIMEOUT_S` raises RuntimeError
    with what FreeCAD said."""
    with tempfile.TemporaryDirectory(prefix="cadgen-freecad-") as tmp:
        folder = Path(tmp)
        write_part(folder / "part.brep")
        (folder / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        env = dict(os.environ, FREECAD_USER_HOME=str(folder / "home"), CADGEN_CAM_FOLDER=str(folder))
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
