"""Open in: the apps on this computer that open a document's files, found offline, and the opening.

A page's Open in menu (``GET /api/v1/local/open-in``, ``POST /api/v1/local/open``: the viewer's
``http_app``) offers, for each file of a document, the apps of ``APPS`` that take its kind
(``KINDS``) and that this computer has. Which it has is found without the network and never on a
request: ``DETECTED`` looks in the background -- once as the server starts (``warm``: the folders
alone), then on use, at most every ``REFRESH_SECONDS`` -- and a request reads what it last found.

Where each platform's apps are, by the platform's own conventions, each function taking where to
look as arguments so every platform's lookup runs anywhere:

* macOS (``mac``): a bundle of a known name in ``/Applications``, ``/Applications/Setapp`` or
  ``~/Applications`` (JetBrains Toolbox's PyCharm among them), else -- on use, never as the server
  starts -- one Spotlight query (``mdfind``, ``SPOTLIGHT_SECONDS`` at most) for the bundles of the
  known identifiers wherever they are.
* Windows (``windows``): the App Paths registry (the user's, then the machine's), else the
  installers' own folders under ``%LOCALAPPDATA%`` and ``%ProgramFiles%``.
* Linux (``linux``): each app's command in one of PATH's absolute folders.

``open_file`` starts the app on the file, or the operating system's own handler for it: detached,
never waited on, never through a shell, its output discarded. It is given a path and an app the
server found itself; nothing of a request is ever a command.
"""
from __future__ import annotations

import glob
import os
import plistlib
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping

from cad.engine import executables

__all__ = ["APPS", "DETECTED", "KINDS", "REFRESH_SECONDS", "Detected", "apps_for", "detect", "file_manager",
           "linux", "mac", "open_file", "windows"]

# Every app Open in offers: its id and the name the menu shows.
APPS = {"vscode": "Visual Studio Code", "cursor": "Cursor", "zed": "Zed", "pycharm": "PyCharm",
        "sublime": "Sublime Text", "fusion": "Autodesk Fusion", "freecad": "FreeCAD", "bambu": "Bambu Studio",
        "orca": "OrcaSlicer", "prusa": "PrusaSlicer", "blender": "Blender"}
# The apps that take each kind of file, in the menu's order. A kind not here takes none: the file
# manager and the default app alone.
_MESHES = ("bambu", "orca", "prusa", "freecad", "blender")
KINDS = {"script": ("vscode", "cursor", "zed", "pycharm", "sublime"),
         "step": ("fusion", "freecad", "bambu", "orca", "prusa"),
         "stl": _MESHES, "3mf": _MESHES, "glb": ("blender",)}

REFRESH_SECONDS = 300.0
SPOTLIGHT_SECONDS = 2.0
# Windows' process creation flags (``subprocess``'s own, which it defines on Windows alone).
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200

# macOS: each app's bundles, as globs under each folder of ``MAC_FOLDERS``, in order of preference,
# and its bundle identifiers, which Spotlight finds a bundle by wherever it is.
MAC_BUNDLES = {
    "vscode": ("Visual Studio Code.app",),
    "cursor": ("Cursor.app",),
    "zed": ("Zed.app",),
    "pycharm": ("PyCharm.app", "PyCharm CE.app", "PyCharm Professional Edition.app", "PyCharm*.app",
                "JetBrains Toolbox/PyCharm*.app"),
    "sublime": ("Sublime Text.app",),
    "fusion": ("Autodesk Fusion.app", "Autodesk Fusion 360.app"),
    "freecad": ("FreeCAD.app",),
    "bambu": ("BambuStudio.app", "Bambu Studio.app"),
    "orca": ("OrcaSlicer.app",),
    "prusa": ("PrusaSlicer.app", "Original Prusa Drivers/PrusaSlicer.app"),
    "blender": ("Blender.app",),
}
MAC_IDS = {
    "vscode": ("com.microsoft.VSCode",),
    "cursor": ("com.todesktop.230313mzl4w4u92",),
    "zed": ("dev.zed.Zed",),
    "pycharm": ("com.jetbrains.pycharm", "com.jetbrains.pycharm.ce"),
    "sublime": ("com.sublimetext.4", "com.sublimetext.3"),
    "fusion": ("com.autodesk.fusion360",),
    "freecad": ("org.freecad.FreeCAD", "org.freecadweb.FreeCAD"),
    "bambu": ("com.bambulab.bambu-studio",),
    "orca": ("com.orcaslicer.OrcaSlicer", "com.softfever3d.orca-slicer"),
    "prusa": ("com.prusa3d.slic3r",),
    "blender": ("org.blenderfoundation.blender",),
}
MAC_FOLDERS = ("/Applications", "/Applications/Setapp", "~/Applications")

# Windows: each app's executable as App Paths names it, then where its installers put it, each
# under the folder an environment variable names (globs: the newest file a glob finds).
WINDOWS_EXES = {"vscode": "Code.exe", "cursor": "Cursor.exe", "zed": "Zed.exe", "pycharm": "pycharm64.exe",
                "sublime": "sublime_text.exe", "fusion": "Fusion360.exe", "freecad": "FreeCAD.exe",
                "bambu": "bambu-studio.exe", "orca": "orca-slicer.exe", "prusa": "prusa-slicer.exe",
                "blender": "blender.exe"}
WINDOWS_FOLDERS = {
    "vscode": (("LOCALAPPDATA", "Programs", "Microsoft VS Code", "Code.exe"),
               ("ProgramFiles", "Microsoft VS Code", "Code.exe")),
    "cursor": (("LOCALAPPDATA", "Programs", "cursor", "Cursor.exe"), ("ProgramFiles", "Cursor", "Cursor.exe")),
    "zed": (("LOCALAPPDATA", "Programs", "Zed", "Zed.exe"), ("ProgramFiles", "Zed", "Zed.exe")),
    "pycharm": (("LOCALAPPDATA", "Programs", "PyCharm*", "bin", "pycharm64.exe"),
                ("ProgramFiles", "JetBrains", "PyCharm*", "bin", "pycharm64.exe")),
    "sublime": (("ProgramFiles", "Sublime Text", "sublime_text.exe"),
                ("ProgramFiles", "Sublime Text 3", "sublime_text.exe")),
    "fusion": (("LOCALAPPDATA", "Autodesk", "webdeploy", "production", "*", "Fusion360.exe"),),
    "freecad": (("LOCALAPPDATA", "Programs", "FreeCAD*", "bin", "FreeCAD.exe"),
                ("ProgramFiles", "FreeCAD*", "bin", "FreeCAD.exe")),
    "bambu": (("ProgramFiles", "Bambu Studio", "bambu-studio.exe"),),
    "orca": (("ProgramFiles", "OrcaSlicer", "orca-slicer.exe"),),
    "prusa": (("ProgramFiles", "Prusa3D", "PrusaSlicer", "prusa-slicer.exe"),),
    "blender": (("ProgramFiles", "Blender Foundation", "Blender*", "blender.exe"),),
}
_APP_PATHS = r"Software\Microsoft\Windows\CurrentVersion\App Paths"

# Linux: each app's commands, in order of preference (Fusion has no Linux build).
LINUX_COMMANDS = {"vscode": ("code",), "cursor": ("cursor",), "zed": ("zed", "zeditor"),
                  "pycharm": ("pycharm", "pycharm-community", "pycharm-professional"), "sublime": ("subl",),
                  "freecad": ("freecad", "FreeCAD"), "bambu": ("bambu-studio",), "orca": ("orca-slicer",),
                  "prusa": ("prusa-slicer",), "blender": ("blender",)}


def apps_for(kind: str, found: Mapping[str, str]) -> list[dict[str, str]]:
    """The apps of ``found`` (``detect``'s) that take files of ``kind``, in the menu's order."""
    return [{"id": app, "name": APPS[app]} for app in KINDS.get(kind, ()) if app in found]


def file_manager(platform: str = sys.platform) -> str:
    """The desktop's file manager, as the menu names it."""
    return {"darwin": "finder", "win32": "explorer"}.get(platform, "files")


# --- macOS -------------------------------------------------------------------------------------


def mac(folders: Iterable[str | os.PathLike], spotlight: Callable[[list[str]], list[str]] | None = None) -> dict[str, str]:
    """Each app's bundle: the first of its known names in the first folder that holds one, else,
    with ``spotlight`` (bundle identifiers in, the paths of bundles found out), one it finds."""
    found: dict[str, str] = {}
    for app, names in MAC_BUNDLES.items():
        for folder in folders:
            root = glob.escape(os.path.expanduser(os.fspath(folder)))
            hits = [path for name in names for path in sorted(glob.glob(os.path.join(root, name))) if os.path.isdir(path)]
            if hits:
                found[app] = hits[0]
                break
    missing = {ident: app for app, idents in MAC_IDS.items() if app not in found for ident in idents}
    if spotlight is not None and missing:
        for path in spotlight(list(missing)):
            app = missing.get(_bundle_id(path) or "")
            if app is not None and app not in found and os.path.isdir(path):
                found[app] = path
    return found


def _bundle_id(bundle: str) -> str | None:
    try:
        with open(os.path.join(bundle, "Contents", "Info.plist"), "rb") as handle:
            ident = plistlib.load(handle).get("CFBundleIdentifier")
    except (OSError, ValueError, plistlib.InvalidFileException, AttributeError):
        return None
    return ident if isinstance(ident, str) else None


def _spotlight(idents: list[str]) -> list[str]:
    """The bundles Spotlight knows of ``idents``: one query, ``SPOTLIGHT_SECONDS`` at most."""
    query = " || ".join(f"kMDItemCFBundleIdentifier == '{ident}'" for ident in idents)
    try:
        done = subprocess.run(["/usr/bin/mdfind", query], capture_output=True, text=True, timeout=SPOTLIGHT_SECONDS,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in done.stdout.splitlines() if line.endswith(".app")]


# --- Windows -----------------------------------------------------------------------------------


def windows(environ: Mapping[str, str], app_path: Callable[[str], str | None]) -> dict[str, str]:
    """Each app's executable: where App Paths (``app_path``: an executable's name in, its path or
    None out) says it is, else in its installers' folders under ``environ``'s."""
    found: dict[str, str] = {}
    for app, exe in WINDOWS_EXES.items():
        registered = app_path(exe)
        if registered and os.path.isfile(registered):
            found[app] = registered
            continue
        for variable, *parts in WINDOWS_FOLDERS.get(app, ()):
            base = environ.get(variable)
            if not base or not os.path.isabs(base):
                continue
            hits = [path for path in glob.glob(os.path.join(glob.escape(base), *parts)) if os.path.isfile(path)]
            if hits:
                found[app] = max(hits, key=_modified)
                break
    return found


def _modified(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except OSError:
        return 0.0


def _registry_app_path(exe: str) -> str | None:
    """The path App Paths gives ``exe``: the user's key, then the machine's."""
    import winreg  # type: ignore[import-not-found]

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, f"{_APP_PATHS}\\{exe}") as key:
                value, _kind = winreg.QueryValueEx(key, None)
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            return os.path.expandvars(value.strip().strip('"'))
    return None


# --- Linux -------------------------------------------------------------------------------------


def linux(find: Callable[[str], str | None]) -> dict[str, str]:
    """Each app's command, by its absolute path (``find``: a bare name in, its path or None out)."""
    found: dict[str, str] = {}
    for app, commands in LINUX_COMMANDS.items():
        for command in commands:
            path = find(command)
            if path:
                found[app] = path
                break
    return found


def detect(platform: str = sys.platform, *, spotlight: bool = True) -> dict[str, str]:
    """This computer's apps of ``APPS``, each by the path it is opened with. Runs a command only on
    macOS, and only with ``spotlight``: the one query for bundles outside the usual folders."""
    if platform == "darwin":
        return mac(MAC_FOLDERS, _spotlight if spotlight else None)
    if platform == "win32":
        return windows(os.environ, _registry_app_path)
    return linux(executables.find)


class Detected:
    """What ``detect`` last found, read by every request and never computed on one: ``warm`` looks in the
    background as the server starts (no command), and ``found`` starts a background look on use when
    nothing has looked fully (with Spotlight) or the last look is ``REFRESH_SECONDS`` old."""

    def __init__(self, detect: Callable[..., dict[str, str]] = detect, clock: Callable[[], float] = time.monotonic,
                 platform: str = sys.platform) -> None:
        self._detect = detect
        self._clock = clock
        self._platform = platform
        self._lock = threading.Lock()
        self._found: dict[str, str] | None = None
        self._at = 0.0
        self._full = False
        self._looking: threading.Thread | None = None

    def warm(self) -> threading.Thread | None:
        """Look now, in the background, without a command: the server's start."""
        return self._start(spotlight=False)

    def found(self) -> dict[str, str]:
        """The apps last found (none before the first look ends); a look started if one is due."""
        with self._lock:
            found, due = self._found, (self._found is None or not self._full
                                       or self._clock() - self._at >= REFRESH_SECONDS)
        if due:
            self._start(spotlight=True)
        return dict(found or {})

    def _start(self, *, spotlight: bool) -> threading.Thread | None:
        with self._lock:
            if self._looking is not None:
                return None
            thread = threading.Thread(target=self._look, args=(spotlight,), name="cad-open-in-apps", daemon=True)
            self._looking = thread
        thread.start()
        return thread

    def _look(self, spotlight: bool) -> None:
        try:
            found = self._detect(self._platform, spotlight=spotlight)
        except Exception:  # noqa: BLE001 - a look that fails leaves what was found; the next use looks again
            found = None
        with self._lock:
            if found is not None:
                self._found, self._at = found, self._clock()
                # Full: a look that asked Spotlight, or one on a platform with nothing more to ask.
                self._full = spotlight or self._platform != "darwin"
            self._looking = None


DETECTED = Detected()


# --- opening -----------------------------------------------------------------------------------


def open_file(path: str, app: str | None = None, *, platform: str = sys.platform,
              spawn: Callable[..., object] = subprocess.Popen, startfile: Callable[[str], None] | None = None) -> None:
    """Start ``app`` (a path ``detect`` found) on the file at ``path``, or, with none, the operating
    system's own handler for it. Detached and never waited on; never through a shell. Raises
    ``FileNotFoundError`` when Linux has no ``xdg-open`` for the default."""
    quiet = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if platform == "darwin":
        spawn(["/usr/bin/open", *(["-a", app] if app else []), path], start_new_session=True, **quiet)
    elif platform == "win32":
        if app is None:
            (startfile or os.startfile)(path)  # type: ignore[attr-defined]
            return
        spawn([app, path], creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP, **quiet)
    else:
        if app is None:
            app = executables.find("xdg-open")
            if app is None:
                raise FileNotFoundError("xdg-open is not installed")
        spawn([app, path], start_new_session=True, **quiet)

