"""Open in: the apps on this computer that open a document's files, found offline, and the opening.

A page's Open in menu (``GET /api/v1/local/open-in``, ``POST /api/v1/local/open``: the viewer's
``http_app``) offers, for each file of a document, the apps of ``APPS`` that take its kind
(``KINDS``) and that this computer has. Which it has is found without the network and never on a
request: ``DETECTED`` looks in the background -- once as the server starts (``warm``: no command is
run), then on use, at most every ``REFRESH_SECONDS`` -- and a request reads what it last found.

Where each platform's apps are, by the platform's own conventions, each function taking where to
look as arguments so every platform's lookup runs anywhere:

* macOS (``mac``): a bundle of a known name in ``/Applications``, ``/Applications/Setapp`` or
  ``~/Applications`` (JetBrains Toolbox's PyCharm among them), else -- on use, never as the server
  starts -- one Spotlight query (``mdfind``, ``SPOTLIGHT_SECONDS`` at most) for the bundles of the
  known identifiers wherever they are.
* Windows (``windows``): the App Paths registry (the user's, then the machine's), else the
  installers' own folders under ``%LOCALAPPDATA%`` and ``%ProgramFiles%``.
* Linux (``linux``): each app's command in one of PATH's absolute folders.

KiCad is two apps, its stable and its nightly channel, and a record (``KiCad``) rather than a path: a
KiCad is opened through its editors alone, its board editor on a board and its schematic editor on a
schematic, since its project manager takes neither, and an installation without both is not offered.
Each channel's newest installation is the one offered, under a label naming its version, and one that
cannot read a file's format (``kicad_reads``) is listed saying so (``refuses``) rather than hidden.
Where KiCads are, each platform's way:

* macOS: both channels are ``KiCad.app`` of one identifier, so the bundles of the folders' ``KiCad*``
  and Spotlight's are told apart by their versions, which their ``Info.plist`` says.
* Windows: the installers' ``KiCad <major.minor>`` Uninstall keys, which say the version and any
  custom folder, and the installers' own folders.
* Linux: ``pcbnew`` and ``eeschema``, and ``pcbnew-nightly`` and ``eeschema-nightly``, each pair's
  version asked of its ``kicad-cli``, the one thing here run to learn something and only on a full look:
  headless, with homes of its own (``_kicad_about``). A look that may run no command does not see a
  KiCad on Linux, as one without Spotlight misses a Mac app outside the usual folders.

MuJoCo Studio is the one app the installation runs itself, its web viewer on an MJCF: ``cad run
mujoco-studio``, the command the mujoco integration's extra brings, offered where that environment is here
(``studio.find``, looked for with the rest: ``found_here``) and started as that command (``studio.start``),
its page opened in the browser once Studio prints its URL.

``open_file`` starts the app on the file, or the operating system's own handler for it: detached,
never waited on, never through a shell, its output discarded. It is given a path and an app the
server found itself; nothing of a request is ever a command.
"""
from __future__ import annotations

import glob
import os
import plistlib
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

from cad.engine import executables
from cad_server._internal.studio import Studio

__all__ = ["APPS", "DETECTED", "KINDS", "REFRESH_SECONDS", "Detected", "KiCad", "NEVER_OPENED", "Studio", "apps_for",
           "detect", "file_manager", "found_here", "kicad_label", "kicad_reads", "linux", "mac", "open_file", "opens", "windows"]

# Every app Open in offers: its id and the name the menu shows.
APPS = {"vscode": "Visual Studio Code", "cursor": "Cursor", "zed": "Zed", "pycharm": "PyCharm",
        "sublime": "Sublime Text", "fusion": "Autodesk Fusion", "freecad": "FreeCAD", "bambu": "Bambu Studio",
        "orca": "OrcaSlicer", "prusa": "PrusaSlicer", "blender": "Blender", "kicad": "KiCad",
        "kicad-nightly": "KiCad nightly", "mujoco-studio": "MuJoCo Studio"}
# The apps that take each kind of file, in the menu's order. A kind not here takes none: the file
# manager and the default app alone.
_MESHES = ("bambu", "orca", "prusa", "freecad", "blender")
KINDS = {"script": ("vscode", "cursor", "zed", "pycharm", "sublime"),
         "step": ("fusion", "freecad", "bambu", "orca", "prusa"),
         "stl": _MESHES, "3mf": _MESHES, "glb": ("blender",),
         "kicad_pcb": ("kicad", "kicad-nightly"), "kicad_sch": ("kicad", "kicad-nightly"),
         "mjcf": ("mujoco-studio",)}

# Files no app but a KiCad record is started on, the operating system's default handler included (we cannot
# show that it resolves to a KiCad that can open the file). The server never starts KiCad by itself (its work
# runs KiCad's command line alone, headless: ``cad.kicad``, kicode's); Open in hands a person's own KiCad a file
# at their click. The file manager still reveals such a file's folder.
NEVER_OPENED = (".kicad_",)

REFRESH_SECONDS = 300.0
SPOTLIGHT_SECONDS = 2.0
KICAD_ABOUT_SECONDS = 10.0
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
# KiCad's installer's folder, and what it may be renamed, under each of those; its bundle's identifier.
MAC_KICAD_BUNDLES = ("KiCad*/KiCad.app", "KiCad*.app")
MAC_KICAD_ID = "org.kicad.kicad"

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
# KiCad's installers: where each puts a <major.minor>'s bin folder, and their Uninstall keys, ``KiCad <major.minor>``.
WINDOWS_KICAD_FOLDERS = (("ProgramFiles", "KiCad"), ("LOCALAPPDATA", "Programs", "KiCad"))
_UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"

# Linux: each app's commands, in order of preference (Fusion has no Linux build).
LINUX_COMMANDS = {"vscode": ("code",), "cursor": ("cursor",), "zed": ("zed", "zeditor"),
                  "pycharm": ("pycharm", "pycharm-community", "pycharm-professional"), "sublime": ("subl",),
                  "freecad": ("freecad", "FreeCAD"), "bambu": ("bambu-studio",), "orca": ("orca-slicer",),
                  "prusa": ("prusa-slicer",), "blender": ("blender",)}
# Linux: each KiCad channel's board editor, schematic editor and command line, and whether it is the nightly.
LINUX_KICADS = (("pcbnew", "eeschema", "kicad-cli", False), ("pcbnew-nightly", "eeschema-nightly", "kicad-cli-nightly", True))


def apps_for(kind: str, found: Mapping[str, str | KiCad | Studio], file: str | os.PathLike | None = None) -> list[dict[str, str]]:
    """The apps of ``found`` (``detect``'s) that take files of ``kind``, in the menu's order, each
    with its id and the name the menu shows: a KiCad's its label, with ``refuses: "newer"`` where it
    cannot read ``file``, which is read only when a KiCad is there to ask about it."""
    takes = [app for app in KINDS.get(kind, ()) if app in found]
    asks = file is not None and any(isinstance(found[app], KiCad) for app in takes)
    stamp = _file_stamp(file) if asks else None
    offered: list[dict[str, str]] = []
    for app in takes:
        entry = found[app]
        if not isinstance(entry, KiCad):
            offered.append({"id": app, "name": APPS[app]})
        elif kicad_reads(entry, stamp, kind):
            offered.append({"id": app, "name": kicad_label(entry)})
        else:
            offered.append({"id": app, "name": kicad_label(entry), "refuses": "newer"})
    return offered


def file_manager(platform: str = sys.platform) -> str:
    """The desktop's file manager, as the menu names it."""
    return {"darwin": "finder", "win32": "explorer"}.get(platform, "files")


# --- KiCad -------------------------------------------------------------------------------------


class KiCad(NamedTuple):
    """An installed KiCad: its version (None where it could not be read), the day it was built (None
    where unknown), its board and schematic editors' paths, and whether it is a nightly."""

    version: str | None
    built: date | None
    board: str
    schematic: str
    nightly: bool


# The file formats each stable major reads, (board, schematic): none ever changed within a major. KiCad 5
# has no ``.kicad_sch`` of any format.
KICAD_FORMATS = {5: (20171130, 0), 6: (20211014, 20211123), 7: (20221018, 20230121), 8: (20240108, 20231120),
                 9: (20241229, 20250114), 10: (20260206, 20260306)}
_KICAD_FILES = {"kicad_pcb": 0, "kicad_sch": 1}
_NIGHTLY_MINOR = 99
_KICAD_EDITORS = {".kicad_pcb": "board", ".kicad_sch": "schematic"}

# What a version says: major.minor, any further numbers, any -rcN, and a nightly's -<commits>-g<hash>.
_VERSION = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?(?:\.\d+)*(?:-rc(\d+))?(?:-(\d+)-g[0-9a-f]+)?", re.IGNORECASE)
_VERSION_PREFIX = re.compile(r"\d+(?:\.\d+)*(?:-rc\d+)?", re.IGNORECASE)
# Windows' DisplayVersion of a nightly, dots for the dashes every other platform has.
_DOTTED_NIGHTLY = re.compile(r"^(\d+\.\d+\.\d+)\.(\d+)\.(g[0-9a-f]+)", re.IGNORECASE)
_ABOUT_VERSION = re.compile(r"^\s*Version:\s*\(?(\d[^\s,)]*)", re.MULTILINE)
_ABOUT_DATE = re.compile(r"^\s*Date:\s*([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})", re.MULTILINE)
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def _kicad_version(said: object) -> str | None:
    """A version a KiCad's packaging says, one way on every platform; None for what is not a version."""
    if not isinstance(said, str):
        return None
    text = _DOTTED_NIGHTLY.sub(r"\1-\2-\3", said.strip())
    return text if _VERSION.match(text) else None


def _version_key(version: str | None) -> tuple[int, ...]:
    """``version`` to compare: numbers, a release after its release candidates, a nightly by its commits."""
    match = _VERSION.match(version or "")
    if match is None:
        return ()
    major, minor, patch, candidate, commits = match.groups()
    return (int(major), int(minor), int(patch or 0), 0 if candidate else 1, int(candidate or 0), int(commits or 0))


def _installed(version: object, built: date | None, board: str, schematic: str, *, nightly: bool = False) -> KiCad:
    """The record of an installation. Its channel is its version's (a nightly's minor is 99), else what
    found it says (``nightly``)."""
    readable = _kicad_version(version)
    if readable is not None:
        nightly = _version_key(readable)[1] == _NIGHTLY_MINOR
    return KiCad(readable, built, board, schematic, nightly)


def _newest(installed: Iterable[KiCad]) -> dict[str, KiCad]:
    """Each channel's newest installation, by version, then by build: a newer KiCad reads all an older does."""
    found: dict[str, KiCad] = {}
    for kicad in installed:
        channel = "kicad-nightly" if kicad.nightly else "kicad"
        held = found.get(channel)
        if held is None or _newness(kicad) > _newness(held):
            found[channel] = kicad
    return found


def _newness(kicad: KiCad) -> tuple[tuple[int, ...], date]:
    return _version_key(kicad.version), kicad.built or date.min


def _built_day(path: str) -> date | None:
    """The UTC day ``path`` was last written: an installed KiCad's build, as its installers keep it."""
    try:
        return datetime.fromtimestamp(os.stat(path).st_mtime, timezone.utc).date()
    except (OSError, OverflowError, ValueError):
        return None


def kicad_label(kicad: KiCad) -> str:
    """What the menu calls ``kicad``: ``KiCad 9.0.6``, ``KiCad 10.0.8-rc1``, ``KiCad 10.99 nightly``, or
    the channel's plain name where its version could not be read."""
    prefix = _VERSION_PREFIX.match(kicad.version or "")
    if prefix is None:
        return APPS["kicad-nightly" if kicad.nightly else "kicad"]
    if kicad.nightly:
        major, minor, *_rest = _version_key(kicad.version)
        return f"KiCad {major}.{minor} nightly"
    return f"KiCad {prefix.group(0)}"


def _stamp_day(stamp: str | None) -> date | None:
    """The day a ``(version YYYYMMDD)`` names; None for what is not one."""
    try:
        return datetime.strptime(stamp, "%Y%m%d").date() if stamp and len(stamp) == 8 else None
    except ValueError:
        return None


# Whether a KiCad reads a file of the format ``stamp`` (a ``(version YYYYMMDD)``). A KiCad refuses a file
# whose stamp is past its own constant, saying a more recent version made it, so the question is that constant.
# A stable major's is in the table. A nightly says only the day it was built, and its format moves under it:
# over 106 format bumps in three years the commit came a median of 1 day after its stamp's date, 17 at the 90th
# percentile, 54 at most, and never before it. So a build before the stamp cannot have that format (the one day
# here is committers' and builders' timezones); one from the stamp on usually has, and 54 days on always did.
# In that uncertain band a nightly is offered: a wrong offer gets KiCad's own clear message and costs a click,
# while a wrong refusal blocks a person's only way in. What cannot be known is offered for the same reason.
def kicad_reads(kicad: KiCad, stamp: str | None, kind: str) -> bool:
    """Whether ``kicad`` can open a file of ``kind`` (``kicad_pcb``, ``kicad_sch``) of the format ``stamp``."""
    day = _stamp_day(stamp)
    version = _version_key(kicad.version)
    if day is None or not version:
        return True
    if kicad.nightly:
        return kicad.built is None or kicad.built + timedelta(days=1) >= day
    major = version[0]
    if major > max(KICAD_FORMATS):
        return True
    if major < min(KICAD_FORMATS):
        return False
    return int(stamp or 0) <= KICAD_FORMATS[major][_KICAD_FILES[kind]]


def _file_stamp(file: str | os.PathLike) -> str | None:
    """The format of the KiCad file at ``file``; None where it cannot be read."""
    from cad.kicad._session import format_of

    try:
        return format_of(Path(file))
    except OSError:
        return None


# --- macOS -------------------------------------------------------------------------------------


def mac(folders: Iterable[str | os.PathLike], spotlight: Callable[[list[str]], list[str]] | None = None) -> dict[str, str | KiCad]:
    """Each app's bundle: the first of its known names in the first folder that holds one, else,
    with ``spotlight`` (bundle identifiers in, the paths of bundles found out), one it finds. And each
    KiCad channel's newest installation, of those in the folders and those Spotlight finds."""
    found: dict[str, str | KiCad] = {}
    for app, names in MAC_BUNDLES.items():
        for folder in folders:
            root = glob.escape(os.path.expanduser(os.fspath(folder)))
            hits = [path for name in names for path in sorted(glob.glob(os.path.join(root, name))) if os.path.isdir(path)]
            if hits:
                found[app] = hits[0]
                break
    missing = {ident: app for app, idents in MAC_IDS.items() if app not in found for ident in idents}
    spotted = spotlight([*missing, MAC_KICAD_ID]) if spotlight is not None else []
    for path in spotted:
        app = missing.get(_bundle_id(path) or "")
        if app is not None and app not in found and os.path.isdir(path):
            found[app] = path
    found.update(_mac_kicads(folders, spotted))
    return found


def _mac_kicads(folders: Iterable[str | os.PathLike], spotted: Iterable[str]) -> dict[str, KiCad]:
    """The newest KiCad of each channel, among the folders' and the found bundles: stable and nightly are
    one name and one identifier, so each is every bundle that says the identifier and holds both editors."""
    bundles = list(spotted)
    for folder in folders:
        root = glob.escape(os.path.expanduser(os.fspath(folder)))
        for name in MAC_KICAD_BUNDLES:
            bundles += sorted(glob.glob(os.path.join(root, name)))
    seen: set[str] = set()
    installed: list[KiCad] = []
    for bundle in bundles:
        real = os.path.realpath(bundle)
        if real in seen:
            continue
        seen.add(real)
        info = _bundle_info(bundle)
        editors = os.path.join(bundle, "Contents", "Applications")
        board, schematic = os.path.join(editors, "pcbnew.app"), os.path.join(editors, "eeschema.app")
        if info.get("CFBundleIdentifier") != MAC_KICAD_ID or not (os.path.isdir(board) and os.path.isdir(schematic)):
            continue
        version = _kicad_version(info.get("CFBundleShortVersionString")) or info.get("CFBundleVersion")
        installed.append(_installed(version, _built_day(os.path.join(bundle, "Contents", "MacOS", "kicad")), board, schematic))
    return _newest(installed)


def _bundle_info(bundle: str) -> dict:
    """The bundle's ``Info.plist``; empty where it cannot be read."""
    try:
        with open(os.path.join(bundle, "Contents", "Info.plist"), "rb") as handle:
            info = plistlib.load(handle)
    except (OSError, ValueError, plistlib.InvalidFileException, AttributeError):
        return {}
    return info if isinstance(info, dict) else {}


def _bundle_id(bundle: str) -> str | None:
    ident = _bundle_info(bundle).get("CFBundleIdentifier")
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


def windows(environ: Mapping[str, str], app_path: Callable[[str], str | None],
            kicad_installs: Callable[[], Iterable[tuple[str, str | None, str | None]]] | None = None) -> dict[str, str | KiCad]:
    """Each app's executable: where App Paths (``app_path``: an executable's name in, its path or
    None out) says it is, else in its installers' folders under ``environ``'s. And each KiCad channel's
    newest installation, from the installers' folders and ``kicad_installs``'s list of
    ``(major.minor, display version, install location)``."""
    found: dict[str, str | KiCad] = {}
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
    found.update(_windows_kicads(environ, list(kicad_installs()) if kicad_installs is not None else []))
    return found


def _windows_kicads(environ: Mapping[str, str], installs: list[tuple[str, str | None, str | None]]) -> dict[str, KiCad]:
    """The newest KiCad of each channel: each custom folder the registry names, its version its key's, then
    each folder the installers put one in, its version its major.minor's key's, else the folder's name."""
    by_minor = {minor: display for minor, display, _location in installs if _kicad_version(display)}
    folders = [(os.path.join(location, "bin"), minor, display) for minor, display, location in installs
               if location and os.path.isdir(location)]
    for variable, *parts in WINDOWS_KICAD_FOLDERS:
        base = environ.get(variable)
        if base and os.path.isabs(base):
            for bin_folder in sorted(glob.glob(os.path.join(glob.escape(base), *parts, "*", "bin"))):
                minor = os.path.basename(os.path.dirname(bin_folder))
                folders.append((bin_folder, minor, by_minor.get(minor)))
    seen: set[str] = set()
    installed: list[KiCad] = []
    for bin_folder, minor, display in folders:
        real = os.path.normcase(os.path.realpath(bin_folder))
        board, schematic = os.path.join(bin_folder, "pcbnew.exe"), os.path.join(bin_folder, "eeschema.exe")
        if real in seen or not (os.path.isfile(board) and os.path.isfile(schematic)):
            continue
        seen.add(real)
        installed.append(_installed(_kicad_version(display) or minor, _built_day(board), board, schematic))
    return _newest(installed)


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


def _registry_kicads() -> list[tuple[str, str | None, str | None]]:
    """The KiCads the Uninstall keys name, the user's then the machine's: each ``KiCad <major.minor>``
    key's major.minor, its DisplayVersion and its InstallLocation (None where a value is not there)."""
    import winreg  # type: ignore[import-not-found]

    def value(key, name: str) -> str | None:
        try:
            said, _kind = winreg.QueryValueEx(key, name)
        except OSError:
            return None
        return said.strip().strip('"') or None if isinstance(said, str) else None

    installs: list[tuple[str, str | None, str | None]] = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, _UNINSTALL) as keys:
                count = winreg.QueryInfoKey(keys)[0]
                for index in range(count):
                    try:
                        name = winreg.EnumKey(keys, index)
                        if not name.startswith("KiCad "):
                            continue
                        with winreg.OpenKey(keys, name) as key:
                            installs.append((name[len("KiCad "):].strip(), value(key, "DisplayVersion"), value(key, "InstallLocation")))
                    except OSError:
                        continue
        except OSError:
            continue
    return installs


# --- Linux -------------------------------------------------------------------------------------


def linux(find: Callable[[str], str | None],
          kicad_about: Callable[[str], tuple[str | None, date | None]] | None = None) -> dict[str, str | KiCad]:
    """Each app's command, by its absolute path (``find``: a bare name in, its path or None out). And,
    with ``kicad_about`` (a ``kicad-cli`` command's path in, its version and build day out), each KiCad
    channel's installation: without it none, so a menu never offers a KiCad it knows no version of."""
    found: dict[str, str | KiCad] = {}
    for app, commands in LINUX_COMMANDS.items():
        for command in commands:
            path = find(command)
            if path:
                found[app] = path
                break
    if kicad_about is not None:
        found.update(_linux_kicads(find, kicad_about))
    return found


def _linux_kicads(find: Callable[[str], str | None],
                  about: Callable[[str], tuple[str | None, date | None]]) -> dict[str, KiCad]:
    installed: list[KiCad] = []
    for board_command, schematic_command, cli_command, nightly in LINUX_KICADS:
        board, schematic = find(board_command), find(schematic_command)
        if not (board and schematic):
            continue
        cli = find(cli_command)
        version, built = about(cli) if cli else (None, None)
        if cli and built is None:
            built = _built_day(os.path.realpath(board))
        installed.append(_installed(version, built, board, schematic, nightly=nightly))
    return _newest(installed)


def _parse_kicad_about(text: str) -> tuple[str | None, date | None]:
    """The version and the build day in what ``kicad-cli version --format about`` says, tolerantly:
    ``Version: 10.99.0-5334-ge37c27a8ce, release build`` and ``Date: Oct 13 2026 01:37:00``, C's own
    ``__DATE__``, English whatever the locale and its day space-padded."""
    said = _ABOUT_VERSION.search(text)
    day = _ABOUT_DATE.search(text)
    built = None
    if day is not None and day.group(1).lower() in _MONTHS:
        try:
            built = date(int(day.group(3)), _MONTHS.index(day.group(1).lower()) + 1, int(day.group(2)))
        except ValueError:
            built = None
    return _kicad_version(said.group(1)) if said is not None else None, built


def _kicad_about(cli: str) -> tuple[str | None, date | None]:
    """What a person's ``kicad-cli`` (a stable or a nightly's wrapper) says of itself: the one run of their
    KiCad, for its version alone, headless, with homes of its own that are removed afterwards. Nothing where
    it does not answer within ``KICAD_ABOUT_SECONDS``."""
    from cad._internal.programs import private_run
    from cad.kicad._program import KICAD

    try:
        with private_run("cad-kicad-about-", KICAD.homes) as (_folder, env):
            done = subprocess.run([cli, "version", "--format", "about"], env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=KICAD_ABOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError):
        return None, None
    return _parse_kicad_about(f"{done.stdout}\n{done.stderr}") if done.returncode == 0 else (None, None)


def detect(platform: str = sys.platform, *, commands: bool = True) -> dict[str, str | KiCad]:
    """This computer's apps of ``APPS``, each by the path it is opened with, a KiCad by its record.
    Runs a command only with ``commands``: macOS's one query for bundles outside the usual folders,
    Linux's question to each ``kicad-cli``."""
    if platform == "darwin":
        return mac(MAC_FOLDERS, _spotlight if commands else None)
    if platform == "win32":
        return windows(os.environ, _registry_app_path, _registry_kicads)
    return linux(executables.find, _kicad_about if commands else None)


def found_here(platform: str = sys.platform, *, commands: bool = True) -> dict[str, str | KiCad | Studio]:
    """This computer's apps (``detect``) and MuJoCo Studio where the installation runs it with nothing
    fetched (``studio.find``: files read, nothing run)."""
    from cad_server._internal import studio

    found: dict[str, str | KiCad | Studio] = {**detect(platform, commands=commands)}
    mujoco = studio.find()
    if mujoco is not None:
        found["mujoco-studio"] = mujoco
    return found


class Detected:
    """What ``detect`` last found, read by every request and never computed on one: ``warm`` looks in the
    background as the server starts (no command), and ``found`` starts a background look on use when
    nothing has looked fully (with commands) or the last look is ``REFRESH_SECONDS`` old."""

    def __init__(self, detect: Callable[..., dict[str, str | KiCad | Studio]] = found_here, clock: Callable[[], float] = time.monotonic,
                 platform: str = sys.platform) -> None:
        self._detect = detect
        self._clock = clock
        self._platform = platform
        self._lock = threading.Lock()
        self._found: dict[str, str | KiCad | Studio] | None = None
        self._at = 0.0
        self._full = False
        self._looking: threading.Thread | None = None

    def warm(self) -> threading.Thread | None:
        """Look now, in the background, without a command: the server's start."""
        return self._start(commands=False)

    def found(self) -> dict[str, str | KiCad | Studio]:
        """The apps last found (none before the first look ends); a look started if one is due."""
        with self._lock:
            found, due = self._found, (self._found is None or not self._full
                                       or self._clock() - self._at >= REFRESH_SECONDS)
        if due:
            self._start(commands=True)
        return dict(found or {})

    def _start(self, *, commands: bool) -> threading.Thread | None:
        with self._lock:
            if self._looking is not None:
                return None
            thread = threading.Thread(target=self._look, args=(commands,), name="cad-open-in-apps", daemon=True)
            self._looking = thread
        thread.start()
        return thread

    def _look(self, commands: bool) -> None:
        try:
            found = self._detect(self._platform, commands=commands)
        except Exception:  # noqa: BLE001 - a look that fails leaves what was found; the next use looks again
            found = None
        with self._lock:
            if found is not None:
                self._found, self._at = found, self._clock()
                # Full: a look that may run commands, or one on the platform that has none to run.
                self._full = commands or self._platform == "win32"
            self._looking = None


DETECTED = Detected()


# --- opening -----------------------------------------------------------------------------------


def opens(path: str | None) -> bool:
    """Whether an app other than a KiCad, or the default handler, may be started on the file at ``path``
    (``NEVER_OPENED``)."""
    return not os.path.splitext(str(path or ""))[1].lower().startswith(NEVER_OPENED)


def open_file(path: str, app: str | KiCad | Studio | None = None, *, platform: str = sys.platform,
              spawn: Callable[..., object] = subprocess.Popen, startfile: Callable[[str], None] | None = None) -> None:
    """Start ``app`` (a path ``detect`` found, or a KiCad, by its editor for the file's extension) on the
    file at ``path``, or, with none, the operating system's own handler for it. Detached and never waited
    on; never through a shell. Raises ``FileNotFoundError`` when Linux has no ``xdg-open`` for the default,
    and ``PermissionError`` for a file no app is started on (``opens``), a KiCad alone being started on one
    of its editors' files. MuJoCo Studio is started as ``cad run mujoco-studio --model PATH`` (``studio.start``),
    its page opened in the browser once it prints its URL."""
    if isinstance(app, Studio):
        from cad_server._internal import studio

        studio.start(path, platform=platform)
        return
    editor = _KICAD_EDITORS.get(os.path.splitext(path)[1].lower())
    if isinstance(app, KiCad) and editor is not None:
        app = getattr(app, editor)
    elif isinstance(app, KiCad) or not opens(path):
        raise PermissionError(f"{os.path.basename(path)} is never opened in that app from here")
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

