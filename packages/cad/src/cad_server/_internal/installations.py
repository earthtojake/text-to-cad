"""BRIDGE-ONLY: the installation records the clients of 0.10.0 to 0.11.11 read, and the ``cad`` command they wrote.

- ``<state>/installations/<version>.json``, an installation's record: ``version``, the absolute paths of its
  ``python`` and of its console script (``cad``), its environment (``prefix``) and when it registered
  (``registered``); and ``<state>/installations/current``, the version whose server every client of 0.11.11 and
  earlier starts or attaches to (their CAD app's line, the library in a person's own Python, their ``cad``
  command). ``cad setup --engine-update`` and the server of a uv tool write them (``cad_server.cli.setup``): the
  record, and ``current`` pointed at it (``point``), so those clients start this release's server.
- ``~/.local/bin/cad`` (``CAD_LAUNCHER_DIR`` moves the folder, ``proxy_path``), the ``cad`` command 0.10.0 to
  0.11.11 wrote: an ``sh`` script (``cad.cmd``, then ``cad.exe`` on Windows) that runs the current installation's
  Python with ``-m cad_server._internal.proxy``. Nothing here writes or removes it: the install command replaces
  it with the uv tool's ``cad``.
- What 0.8 and 0.10.0 on Windows left of their records (``earlier``, ``appdata``), read only.

A development install names its own version (``CAD_INSTALLATION_VERSION``), which the old ``cad`` command sets for
it as it runs it (``named``, ``cad_server._internal.proxy``).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from cad.engine.places import VERSION, alive, installation_record

DIR_ENV = "CAD_LAUNCHER_DIR"
NAME_ENV = "CAD_INSTALLATION_VERSION"
FOLDER = "installations"  # ``cad.engine.places.INSTALLATIONS``, which clients read
WINDOWS = os.name == "nt"
# The ``cad`` command's file on Windows (0.11.x's; 0.10.x wrote ``cad.cmd``).
EXE = "cad.exe"
# The file that names the current installation's version, in the state folder.
CURRENT = f"{FOLDER}/current"
# A release's version, as a wheel reports it of itself (``cad_server.__version__``). Any other version a
# record names -- a development install's ``<version>-dev.<time>``, a source tree's -- is a name the
# installation cannot know by itself: the ``cad`` command gives it (``named``).
RELEASE = re.compile(r"[0-9]+(\.[0-9]+)*((a|b|rc)[0-9]+)?(\.post[0-9]+)?")

OK = "ok"
REGISTERED = "registered"


def proxy_folder() -> str:
    """uv's user bin folder, ``~/.local/bin`` (``%USERPROFILE%\\.local\\bin`` on Windows)."""
    return os.environ.get(DIR_ENV) or os.path.join(os.path.expanduser("~"), ".local", "bin")


def proxy_path(where: str | None = None, windows: bool = WINDOWS) -> str:
    """Where 0.10.0 to 0.11.11 wrote the ``cad`` command, and where uv puts the uv tool's."""
    return os.path.join(where or proxy_folder(), EXE if windows else "cad")


# A folder uv keeps an archive in, in its cache (``archive-v0``); and the marker of a server environment cad
# made (``releases.MARKER``).
_UV_ARCHIVE = re.compile(r"archive-v\d+")
_RELEASE_MARKER = "cad-release.json"


def _within(path: str, folder: str) -> bool:
    path, folder = os.path.normcase(path), os.path.normcase(folder.rstrip("/\\"))
    return bool(folder) and (path == folder or path.startswith(folder + os.sep))


def transient(path: object) -> bool:
    """Whether ``path`` (a program, or a folder on PATH) is in an environment that comes and goes, never one
    the person keeps: this process's own virtual environment (``sys.prefix``: uvx's, as ``uvx ... cad setup``
    runs), one uv keeps in its cache (``archive-v<N>``), or a server environment of cad's."""
    plain = os.path.abspath(str(path))
    own = {sys.prefix, os.path.realpath(sys.prefix)} if sys.prefix != sys.base_prefix else set()
    for where in {plain, os.path.realpath(plain)}:
        if any(_within(where, prefix) for prefix in own):
            return True
        if any(_UV_ARCHIVE.fullmatch(part) for part in Path(where).parts):
            return True
        parent = os.path.dirname(where)
        if any(os.path.isfile(os.path.join(folder, _RELEASE_MARKER)) for folder in (parent, os.path.dirname(parent))):
            return True
    return False


def lasting(path: str) -> str:
    """A PATH without its transient folders (``transient``): where the person's own commands are found."""
    return os.pathsep.join(entry for entry in path.split(os.pathsep) if entry and not transient(entry))


def state():
    """The user's state folder (``cad.engine.places.state_dir``), as its ``Folder``."""
    from cad_server.engine.registry import Folder
    from cad.engine.places import state_dir

    return Folder(state_dir())


def targets() -> tuple[str, str, str] | None:
    """This installation's console script, python and environment, or ``None`` without a console
    script. The python is the environment's own path, never resolved: resolving it reaches the base
    interpreter, which is not this environment."""
    if sys.prefix != sys.base_prefix:
        scripts = os.path.join(sys.prefix, "Scripts" if WINDOWS else "bin")
        python = os.path.join(scripts, "python.exe" if WINDOWS else "python")
        if not os.path.isfile(python):
            python = sys.executable
    else:  # not a virtual environment: rare, and sysconfig costs a few milliseconds
        import sysconfig

        scripts = sysconfig.get_path("scripts")
        python = sys.executable
    console = os.path.join(scripts, "cad.exe" if WINDOWS else "cad")
    if not (python and os.path.isfile(console)):
        return None
    return os.path.abspath(console), os.path.abspath(python), os.path.abspath(sys.prefix)


def _inside(version: str) -> str:
    if not VERSION.fullmatch(version or ""):
        raise ValueError(f"not a version: {version!r}")
    return f"{FOLDER}/{version}.json"


def register(version: str, found: tuple[str, str, str] | None = None, folder=None) -> tuple[str, str]:
    """Write the record of this installation as ``version``: ``(path, status)``, ``REGISTERED`` or
    ``OK`` when the record already names it. ``OSError`` when the state folder cannot be written."""
    folder = folder or state()
    found = found or targets()
    inside = _inside(version)
    path = str(folder.path(inside))
    if found is None:
        raise OSError(f"this installation has no console script to register ({sys.prefix})")
    console, python, prefix = found
    before = installation_record(folder.read(inside))
    if before and (before["cad"], before["python"], before["prefix"]) == (console, python, prefix):
        return path, OK
    record = {"version": version, "python": python, "cad": console, "prefix": prefix,
              "registered": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    # One key a line, the python's alone: the sh of 0.10.0 to 0.11.11 reads that line.
    text = json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    folder.write(inside, text.encode("utf-8"))
    # An environment holds one cadgen: the record of another version in it (an upgrade in place,
    # ``pip install -U``, ``uv tool upgrade``) names code that is gone, and would run this one as it.
    for other in records(folder):
        if other["version"] != version and _same_place(other["prefix"], prefix):
            folder.remove(_inside(other["version"]))
    _forget_read()
    return path, REGISTERED


def _forget_read() -> None:
    """The records changed in this process: the version its environment is registered as
    (``cad.engine.places.registered``, read once per process) is read again."""
    from cad.engine import places

    places._registered.cache_clear()


def _same_place(one: str, other: str) -> bool:
    return os.path.normcase(os.path.realpath(one)) == os.path.normcase(os.path.realpath(other))


def records(folder=None) -> list[dict]:
    """Every installation's record, each with its file (``path``)."""
    folder = folder or state()
    found = []
    for name in folder.names(FOLDER):
        if name.endswith(".json") and VERSION.fullmatch(name[:-5]):
            record = installation_record(folder.read(f"{FOLDER}/{name}"))
            if record is not None and record["version"] == name[:-5]:
                found.append({**record, "path": str(folder.path(f"{FOLDER}/{name}"))})
    return found


def named(record: dict) -> str | None:
    """The version the ``cad`` command tells the installation of ``record`` it runs as
    (``NAME_ENV``): a development or source registration's, which it cannot know by itself (it
    reports its release's); None for a release, which knows."""
    return None if RELEASE.fullmatch(record["version"]) else record["version"]


# The key 0.8's installation records name their console script by (this release's say ``cad``).
EARLIER_CONSOLE = "cadgen"


def appdata() -> list[dict]:
    """0.10.0's installations on Windows, each by its record in the state folder it kept in the local
    application data (``cad.engine.places.appdata_state_dir``), as ``earlier`` reads 0.8's. Read to stop 0.10.0's
    servers by their own stop command (``cad_server.cli.setup.stop_appdata``) and for its releases' What's new
    (``whats_new``)."""
    from cad.engine.places import appdata_state_dir

    folder = appdata_state_dir()
    return earlier(folder, console="cad") if folder is not None else []


def earlier(folder: Path | None = None, console: str = EARLIER_CONSOLE) -> list[dict]:
    """0.8's installations, each by its record where 0.8 left it: ``installations/<version>.json`` in 0.8's
    state folder (``folder``; by default where what 0.8 left is looked for,
    ``cad.engine.places.earlier_state_dir``), its ``version``, ``python``, console script
    (``EARLIER_CONSOLE``) and environment (``prefix``), with its file (``path``). Read only to tell what 0.8 and
    0.10.0 left: 0.10.0's servers to stop by their own stop command (``cli.setup.stop_appdata``), and their
    releases' What's new (``whats_new``)."""
    from cad.engine.places import earlier_state_dir

    where = Path(folder or earlier_state_dir()) / FOLDER
    try:
        names = sorted(os.listdir(where))
    except OSError:
        return []
    found = []
    for name in names:
        if not (name.endswith(".json") and VERSION.fullmatch(name[:-5])):
            continue
        try:
            record = json.loads((where / name).read_bytes())
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and record.get("version") == name[:-5] and all(
                isinstance(record.get(key), str) for key in ("python", console, "prefix")):
            found.append({**record, "path": str(where / name)})
    return found


def forget(version: str, folder=None) -> None:
    """Remove the record of ``version`` (a development install's, as it is taken out)."""
    (folder or state()).remove(_inside(version))
    _forget_read()


# --- current ----------------------------------------------------------------------------------


def current_version(folder=None) -> str | None:
    """The version ``current`` names, whether or not its installation is there, or None."""
    folder = folder or state()
    data = folder.read(CURRENT)
    named = data.decode("utf-8", "replace").strip() if data is not None else ""
    return named if VERSION.fullmatch(named) else None


def current(folder=None) -> dict | None:
    """The current installation's record, while its interpreter and console script are there
    (``alive``): the one every client of 0.11.11 and earlier starts. None with none current, or one that is
    gone (its folder removed, uv's cache cleaned)."""
    folder = folder or state()
    version = current_version(folder)
    if version is None:
        return None
    record = installation_record(folder.read(_inside(version)))
    if record is None or record["version"] != version or not alive(record):
        return None
    return {**record, "path": str(folder.path(_inside(version)))}


def point(version: str, folder=None) -> None:
    """``current`` pointed at ``version`` (registered), replaced whole: a reader sees the one before or this
    one. The file is the version alone, no line end: ``cmd``'s ``set /p`` reads it as it is."""
    folder = folder or state()
    _inside(version)  # a version, or ValueError
    folder.write(CURRENT, version.encode("utf-8"))
