"""Where cadgen's things are on this computer, and how a process of the engine's is started.

Every process reads this: a model's script and its worker, in the CAD kernel environment where only the
library is installed; the engine's server; each client of it. So each finds the same folders, the same
engine and the same installation by the same rules, from the standard library alone and with no kernel.

- **The user's folders**: the device's state folder (``state_dir``), and in it one folder per installed
  version (``version_dir``: ``versions/<version>``) holding that version's code (``code_dir``: its
  environments and their bytecode) and its data (``data_dir``: settings, the documents' records, Recents, the
  page token and port, and its own caches under ``data/cache``, ``cache_dir``).
- **The engine folders** (``engines_dir``, ``engine_dir``): each version's engine's door (a named pipe; on
  Windows a port file), lock and failure note, in a folder of its own only this user can write
  (``folder_refusal``), each named ``engine`` (``NAME``).
- **The installation** a process belongs to: its version (``versioned``, below), the version it runs as
  (``installation``), the base's marker naming the installation of a process that runs in the base
  (``HOME``), and the one whose engine a client starts when none answers (``engine``).
- **Starting a process** of the engine's: with no window on Windows (``windowless``), outliving its
  starter (``detached``), its bytecode kept in a folder of the engine's (``bytecode``), and on the Python
  of the environment the kernel is in (``kernel``, which the server makes as ``KERNEL``: the installation's
  base, the library with its ``build123d`` extra).

**Whose folders a process uses** (``versioned``). A process HAS A VERSION when it is part of one installed
in the per-version layout: told its name (``CAD_INSTALLATION_VERSION``) and that version's code marker is
there (``version_record``); else its environment (``sys.prefix``, or that of the installation whose base it
runs in, ``HOME``) lies inside ``versions/<version>/code``; else a version's code marker names its
environment (a development install's checkout). A daemon with a version names it to every process it
starts (``cad_server.engine.supervisor``), so a worker on a script's own Python is that version's too. Such
a process reads and writes only under ``versions/<version>/`` -- its data, its data cache, its kernel and
extras environments and bytecode in its code -- and the engine folder ``<engines>/<version>``, plus the
device's globals (the ``cad`` command, the install lock and receipt, the plugin folder, ``installations/``),
and the engine it starts is its own version's, never another's (``engine``).

A process with NO VERSION -- a checkout or a test under ``CAD_STATE_DIR``, ``CAD_ENGINE_DIR`` and
``CAD_CACHE_DIR``; an installation of the layout before 0.12, flat in ``releases/<version>`` or made by uvx;
a development install's checkout no version's marker names -- keeps that layout, exactly: its data is the
state folder itself (``data_dir`` is ``state_dir``), its caches, environments and bytecode the cache folder
(``legacy_cache_dir``: ``CAD_CACHE_DIR``, else ``~/.cache/cad``), its engine folder the flat one every
release before 0.12 finds (``engines_dir``), and the engine it starts the current installation's
(``installations/current``). ``CAD_CACHE_DIR`` names only that layout's cache: a process with a version
keeps its caches in its own data.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

__all__ = ["BYTECODE", "DISPLAY", "EXTRAS", "HOME", "KERNEL", "SEPARATE", "NAME", "RESTARTS", "RUN_WITH", "WINDOWS", "XAUTHORITY", "Endpoint", "address",
           "alive", "appdata_cache_dir", "appdata_engine_dir", "appdata_state_dir", "bytecode", "bytecode_tag",
           "cache_dir", "code_dir", "current", "data_dir", "detached", "door_path", "earlier_cache_dir",
           "earlier_state_dir", "endpoints", "engine", "engine_dir", "engine_root", "engines_dir", "extras",
           "failure_path", "folder_refusal", "home", "installation", "kernel", "legacy_cache_dir", "lock", "lock_path",
           "make_engine_dir", "port_path", "registered", "run_with", "state_dir", "version_dir", "version_record",
           "versioned", "versions_dir", "windowless"]

WINDOWS = os.name == "nt"
# The engine's name in its engine folder: its lock, door (on Windows its port file) and failure note
# are ``engine.lock``, ``engine.door``, ``engine.port`` and ``engine.failed``. One engine a device: the
# one a client finds there, whatever release it runs, and whatever release the client is. Its record in
# the state folder (the port it rolled to) goes by the same name.
NAME = "engine"
# The version an installation that cannot know its own name runs as (a development install's
# ``<version>-dev.<time>``, set by its launcher and the ``cadgen`` command): the name its records
# and its engine's ``status`` give it (``installation``).
INSTALLATION_ENV = "CAD_INSTALLATION_VERSION"
# What a worker's environment must share with a request's for the request to use it: what shapes
# the import system of the interpreter it started (the interpreter itself is the engine's kernel
# environment's, ``kernel``). A run adopts the rest of its caller's environment (``worker.adopt``), so a
# caller whose PATH changes from one run to the next (an agent's shell) keeps its warm worker and its memo.
RESTARTS = ("PYTHONPATH", "PYTHONHOME", "PYTHONSAFEPATH", "PYTHONNOUSERSITE", "PYTHONUSERBASE", "PYTHONPLATLIBDIR")
# How the engine's processes treat bytecode (``bytecode``): one of the two, never a run's to change.
BYTECODE = ("PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE")
# The X display the engine gives each process that draws (``cad_server.engine.display``: its own, or an Xvfb
# it started), which a still is drawn on where its request names none (``render.context.display``); a run's
# never replaces it (``worker.told_display``); and the X authority file that admits a client to it, where it
# takes one.
DISPLAY = "CAD_ENGINE_DISPLAY"
XAUTHORITY = "CAD_ENGINE_XAUTHORITY"
# The folder of the engine's bytecode: a version's in its code (``code_dir``); before 0.12 one folder per
# installation in it in the cache folder (``bytecode_tag``).
PYCACHE = "pycache"
# The versions' folder in the state folder, and in each version's folder its code (disposable: its
# environments and their bytecode) and its data (what it reads and writes), its caches under ``data/cache``.
# The code's marker, written last by the install that makes the version present, names the version and the
# server environment it runs from (``version_record``).
VERSIONS = "versions"
CODE, DATA, DATA_CACHE = "code", "data", "cache"
VERSION_MARKER = "cad-version.json"
VERSION_SCHEMA = "cad version/1"
# The installations' records in the state folder, and the file naming the current one's version.
INSTALLATIONS = "installations"
CURRENT = f"{INSTALLATIONS}/current"
VERSION = re.compile(r"[0-9][0-9A-Za-z.+_-]*")
# The marker the server writes last in the environment it makes for the kernel (the base), naming the
# installation it belongs to (``home``), and the marker's schema.
MARKER = "cad-env.json"
MARKER_SCHEMA = "cad env/2"


# --- the user's folders ----------------------------------------------------------------------------

# The state folder's name in the platform's place for it (on Windows, beside the cache folder, its own
# suffix), and the earlier releases' (named for cadgen, the library's earlier name). What this release
# keeps of an earlier state folder (``ADOPTED``) it moves into its own (``adopt``): what the person owns
# -- their settings (the telemetry answer, so a no stays a no, and the language), the documents' records
# and what the homes show of them (Recents) -- and setup's receipt, which ``cad setup`` reads for the
# skills and the configs 0.8's setup touched, and ``cad uninstall`` for what it did. Not 0.8's
# installations' records, its engines' records or its page token, which only 0.8 runs by, nor its
# install channels, the locks, or the telemetry it noted and did not send. The person's telemetry no
# stays in the earlier folder too, for the earlier release still installed (``adopt``).
STATE = "cad"
EARLIER_STATE = ("cadgen", "cadgen-state")
SETTINGS = "settings.json"
ADOPTED = (SETTINGS, "documents", "recents", "install-receipt.json")
CACHE, EARLIER_CACHE = "cad", "cadgen"
# On Windows, 0.10.0 kept its folders in the local application data (``appdata_state_dir`` and the
# others), which Windows virtualizes for every process an app package (MSIX) starts -- the Claude desktop
# app's shell, its CAD app's server and the engine that server starts --: what such a process creates
# there lands in the package's private ``LocalCache``, where no other app and no terminal finds it. So
# Windows keeps them where Linux does, in the user's own folder, which no package virtualizes. What
# 0.10.0 kept there moves once (``adopt_earlier``): ``ADOPTED`` and the page token and port the engine
# remembers (``APPDATA_ADOPTED``), so every link shared before still works, and the documents' bytes.
APPDATA_STATE, APPDATA_CACHE = "cad-state", "cad"
APPDATA_ADOPTED = (*ADOPTED, "engines/token", "engines/engine.json", "install-channels.json")


def _local_state() -> Path:
    """The platform's place for state: ``~/Library/Application Support`` on macOS, else ``$XDG_STATE_HOME``
    or ``~/.local/state`` -- on Windows too, ``%USERPROFILE%\\.local\\state``, beside ``.local\\bin``."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")


def _appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")


def state_dir() -> Path:
    """The device's CAD state folder (``CAD_STATE_DIR`` overrides it): ``cad`` in the platform's place for
    state (``_local_state``). It holds the device's globals -- the install lock and receipt, the plugin folder,
    ``installations/``, ``releases/`` -- and the versions (``versions_dir``); before 0.12 it was every
    version's data too, as it still is for a process with no version (``data_dir``)."""
    override = os.environ.get("CAD_STATE_DIR")
    if override:
        return Path(override)
    return _local_state() / STATE


def versions_dir() -> Path:
    """The folder of the installed versions, ``versions`` in the state folder (not ``releases``, which the
    updaters before 0.12 own and remove folders from)."""
    return state_dir() / VERSIONS


def version_dir(name: str) -> Path:
    """Version ``name``'s folder, ``versions/<name>``, there or not. ``ValueError`` for a name that is no
    version (``VERSION``: a digit first, then ``[0-9A-Za-z.+_-]``), which could name another folder."""
    if not VERSION.fullmatch(name or ""):
        raise ValueError(f"not a version: {name!r}")
    return versions_dir() / name


def code_dir(name: str) -> Path:
    """Version ``name``'s code, ``versions/<name>/code``: its server, kernel and extras environments and their
    bytecode, made by its install and disposable (a repair makes it again whole)."""
    return version_dir(name) / CODE


def data_dir(name: str | None = None) -> Path:
    """Where a version keeps what it reads and writes -- settings, the documents' records, Recents, the page
    token and port, the telemetry spool, the version feed's cache -- ``versions/<name>/data``. With no
    ``name``, this process's: its version's (``versioned``), else, for a process with no version, the state
    folder itself, as before 0.12."""
    name = name if name is not None else versioned()
    return version_dir(name) / DATA if name is not None else state_dir()


def appdata_state_dir() -> Path | None:
    """Where 0.10.0 kept its state on Windows, ``%LOCALAPPDATA%\\cad-state``, which this release moves out of
    (``APPDATA_STATE``); None elsewhere, or where ``CAD_STATE_DIR`` names the state folder."""
    return _appdata() / APPDATA_STATE if WINDOWS and not os.environ.get("CAD_STATE_DIR") else None


def appdata_cache_dir() -> Path | None:
    """Where 0.10.0 kept its cache on Windows, ``%LOCALAPPDATA%\\cad``: its documents' bytes move with their
    records (``adopt_earlier``), the rest is left to ``cad doctor --prune``; None elsewhere, or where
    ``CAD_CACHE_DIR`` names the cache folder."""
    return _appdata() / APPDATA_CACHE if WINDOWS and not os.environ.get("CAD_CACHE_DIR", "").strip() else None


def appdata_engine_dir() -> Path | None:
    """Where 0.10.0's clients look for the engine on Windows, ``cad-engine`` in the temporary folder: the
    engine writes its port file there too for one release (``cad_server.engine.daemon``), so a CAD app's
    server of 0.10.0 still running finds it; None elsewhere, or where ``CAD_ENGINE_DIR`` names the folder."""
    return Path(tempfile.gettempdir()) / "cad-engine" if WINDOWS and not os.environ.get("CAD_ENGINE_DIR") else None


def _platform_state(names: tuple[str, str]) -> Path:
    posix, windows = names
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / posix
    if sys.platform == "win32":
        return _appdata() / windows
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / posix


def earlier_state_dir() -> Path:
    """Where the releases before 0.10 kept their state (``EARLIER_STATE``), or the folder ``CAD_STATE_DIR`` names:
    where what they left behind is looked for (``cad doctor``)."""
    override = os.environ.get("CAD_STATE_DIR")
    return Path(override) if override else _platform_state(EARLIER_STATE)


def adopt_earlier() -> list[str]:
    """What this release keeps of an earlier release's state folder moved into the layout before 0.12
    (``adopt``: the state folder and ``legacy_cache_dir``), where no state folder is named (``CAD_STATE_DIR``):
    what an installation's registration (``cad_server._internal.installations``), ``cad setup`` and ``cad
    doctor`` do before they write there. Each thing moves once: once that folder has it, the earlier one's
    stays. The names moved."""
    if os.environ.get("CAD_STATE_DIR"):
        return []
    moved: list[str] = []
    # 0.10.0's Windows folder first: what it took of 0.8's is there, and 0.8's keeps a telemetry no that is
    # no person's whole settings.
    appdata, appdata_cache = appdata_state_dir(), appdata_cache_dir()
    if appdata is not None:
        moved += adopt(appdata, state_dir(), APPDATA_ADOPTED)
    if appdata_cache is not None:  # the bytes of the documents whose records moved, so Recents still opens them
        moved += adopt(appdata_cache, legacy_cache_dir(), ("documents",))
    return moved + adopt(_platform_state(EARLIER_STATE), state_dir())


def adopt(earlier: Path, folder: Path, names: tuple[str, ...] = ADOPTED) -> list[str]:
    """What this release keeps of the state folder ``earlier`` moved into ``folder`` (``names``), each
    only where ``folder`` has none. The rest stays where it was. Moved, never copied -- a record
    names one place --, but for the person's telemetry no: an earlier release still installed (an app's
    session, its own stop command) reads settings it finds missing as never told and tells its notice
    again, which it then takes for a yes, so its folder keeps the no (``_said_no``). Quiet: a move that
    fails leaves both folders as they were, and the next registration tries again. The names moved."""
    moved: list[str] = []
    for name in names:
        source, destination = earlier / name, folder / name
        if not source.exists() or os.path.lexists(destination):
            continue
        no = _said_no(source) if name == SETTINGS else None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(source, destination)
        except OSError:
            continue
        if no is not None:
            _leave(source, {"telemetry": no})
        moved.append(name)
    return moved


def _leave(path: Path, value: dict[str, Any]) -> None:
    """``value`` written to ``path`` as JSON, whole (``atomic_replace.put``). Quiet."""
    from cad.engine.atomic_replace import put

    text = json.dumps(value, indent=2) + "\n"
    try:
        put(path, lambda staged: staged.write_text(text, encoding="utf-8"))
    except OSError:
        pass


def _said_no(settings: Path) -> dict[str, Any] | None:
    """The telemetry answer in the settings file ``settings`` when it is the person's no (its ``choice``
    ``off``), without the deletion it may still owe (``forget``: the release the settings move to sends
    that), else None."""
    try:
        section = json.loads(settings.read_text(encoding="utf-8")).get("telemetry")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(section, dict) or section.get("choice") != "off":
        return None
    return {key: value for key, value in section.items() if key != "forget"}


def cache_dir(name: str | None = None) -> Path:
    """Where a version caches what it can make again -- documents' bytes (``documents/<id>/document.xbf``),
    hulls, MJCF assets, integrations' homes --: ``versions/<name>/data/cache``, beside the records that
    point at it, which wiping it never loses. With no ``name``, this process's: its version's
    (``versioned``), else, for a process with no version, the cache folder before 0.12
    (``legacy_cache_dir``)."""
    name = name if name is not None else versioned()
    return data_dir(name) / DATA_CACHE if name is not None else legacy_cache_dir()


def legacy_cache_dir() -> Path:
    """The cache folder before 0.12, which a process with no version still uses (``cache_dir``) and a
    version imports nothing from: the platform's cache location, which the system and the person treat as
    disposable. ``CAD_CACHE_DIR`` when set (a relative one made absolute once, and written back, so a worker
    after a ``chdir`` names the same folder), else ``$XDG_CACHE_HOME/cad`` when set, else ``~/.cache/cad`` --
    on Windows too, out of the local application data an app package virtualizes (``APPDATA_STATE``). An
    earlier release's cache (named for cadgen, or 0.10.0's on Windows) is not read: it is a cache."""
    return _cache_dir(CACHE, appdata=False)


def earlier_cache_dir() -> Path:
    """Where the releases before 0.10 kept their cache (``EARLIER_CACHE``, by ``cache_dir``'s rule), or the folder
    ``CAD_CACHE_DIR`` names: where what they left behind is looked for (``cad doctor``)."""
    return _cache_dir(EARLIER_CACHE, appdata=True)


def _cache_dir(name: str, appdata: bool) -> Path:
    override = os.environ.get("CAD_CACHE_DIR", "").strip()
    if override:
        root = Path(override).expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
            os.environ["CAD_CACHE_DIR"] = str(root)
        return root
    if os.name == "nt" and appdata:
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            return Path(local) / name
    else:
        xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
        if xdg:
            return Path(xdg) / name
    return Path.home() / ".cache" / name


# --- the engine folder -----------------------------------------------------------------------------


def engines_dir() -> Path:
    """The engines' folder: ``CAD_ENGINE_DIR``, else ``default_engine_dir``. Each version's engine has a
    folder of its own in it (``engine_dir``); in it directly is the flat door, lock and port file every
    release before 0.12 finds, and every process with no version. Resolved once, here, for the client and
    the server alike (``os.path.realpath``): a ``..``, a symlink or a trailing slash in either spelling names
    the same door, lock and port file. It stays in the temporary (runtime) folder, never under the state
    folder: a sandboxed client must make its pipes there (``door.CLIENTS``), and a sandbox lets it write the
    temporary folder alone."""
    override = os.environ.get("CAD_ENGINE_DIR")
    return Path(os.path.realpath(override if override else default_engine_dir()))


def engine_dir(name: str | None = None) -> Path:
    """Where an engine's door, lock and failure note live: version ``name``'s folder in the engines' folder,
    ``<engines>/<name>``. With no ``name``, this process's: its version's (``versioned``), else, for a
    process with no version, the engines' folder itself, the flat door before 0.12 (``engines_dir``)."""
    name = name if name is not None else versioned()
    if name is None:
        return engines_dir()
    if not VERSION.fullmatch(name):
        raise ValueError(f"not a version: {name!r}")
    return engines_dir() / name


def make_engine_dir(folder: Path | None = None) -> Path:
    """The engine folder ``folder`` (this process's, ``engine_dir``) made where it is not, this user's alone
    (mode 700), and the engines' folder above it first, the same way (a version's folder is made in it):
    never a folder others can write on the way to a door. ``PermissionError`` when the system refuses."""
    folder = folder or engine_dir()
    root = engines_dir()
    if folder != root and folder.parent == root:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    return folder


def default_engine_dir() -> str:
    """The engine's folder when ``CAD_ENGINE_DIR`` names none, in a place no other user can make
    it first: ``$XDG_RUNTIME_DIR/cad-engine`` (Linux's per-session folder), else
    ``cad-engine`` in the user's temporary folder when it is this user's alone: on macOS the one
    the system names (``_darwin_temp``, ``/var/folders/...``), which a sandbox that sets its own
    ``TMPDIR`` does not move, so a client in it and the engine outside find one folder; ``TMPDIR``
    only where the system names none. Else ``/tmp/cad-<uid>``, which ``folder_refusal`` still
    checks. On Windows ``cad-engine`` beside the state folder (``_local_state``): the temporary folder
    is in the local application data an app package virtualizes, where an engine the Claude desktop
    app started would leave a port file no other app finds (0.10.0's, ``appdata_engine_dir``). 0.8 kept
    its engines in ``cadgen-engine``: neither release's clients find the other's door."""
    if WINDOWS:
        return str(_local_state() / "cad-engine")
    for parent in (os.environ.get("XDG_RUNTIME_DIR"), _darwin_temp() or os.environ.get("TMPDIR")):
        if parent and os.path.isabs(parent) and _users_own(parent):
            return os.path.join(parent, "cad-engine")
    return f"/tmp/cad-{os.getuid()}"


def _darwin_temp() -> str | None:
    """macOS's per-user temporary folder as the system names it (``_CS_DARWIN_USER_TEMP_DIR``), what
    ``TMPDIR`` holds in a login session, whatever ``TMPDIR`` a sandbox sets; None elsewhere or when
    it cannot be asked."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes

        buffer = ctypes.create_string_buffer(1024)
        size = ctypes.CDLL(None, use_errno=True).confstr(65537, buffer, len(buffer))  # _CS_DARWIN_USER_TEMP_DIR
    except (OSError, AttributeError):
        return None
    return os.fsdecode(buffer.value) if 0 < size <= len(buffer) else None


def _users_own(folder: str) -> bool:
    """Whether ``folder`` is a folder of this user's that no one else can write to."""
    import stat

    try:
        found = os.stat(folder)
    except OSError:
        return False
    return stat.S_ISDIR(found.st_mode) and found.st_uid == os.getuid() and not found.st_mode & 0o022


def folder_refusal(folder: Path) -> str | None:
    """Why ``folder`` may not hold the engine's door, lock and port file, or None when it may. On
    POSIX it must be a folder of this user's that no one else can write to: whoever owns the folder,
    or can write to it, can take the door's place, and every request carries its client's
    environment. (The default folder's name is shared by every user of a machine: another user who
    made it first owns it.)"""
    if WINDOWS:
        return None
    import stat

    try:
        found = os.lstat(folder)
    except OSError as error:
        return f"the engine's folder {folder} cannot be read: {error.strerror or error}"
    if not stat.S_ISDIR(found.st_mode):
        return f"the engine's folder {folder} is not a folder"
    if found.st_uid != os.getuid():
        return (f"the engine's folder {folder} belongs to another user (uid {found.st_uid}): "
                "set CAD_ENGINE_DIR to a folder of your own")
    if found.st_mode & 0o022:
        return (f"the engine's folder {folder} can be written by others (mode {stat.S_IMODE(found.st_mode):o}): "
                "run chmod go-w on it, or set CAD_ENGINE_DIR to a folder of your own")
    return None


def lock_path() -> Path:
    return engine_dir() / f"{NAME}.lock"


def port_path() -> Path:
    return engine_dir() / f"{NAME}.port"


def door_path() -> Path:
    """The daemon's door on POSIX: a named pipe beside its lock, which it reads hellos from
    (``door``). A pipe's path has no length limit but the file system's."""
    return engine_dir() / f"{NAME}.door"


def address() -> Path:
    """Where a client reaches the daemon: its door, on Windows its port file."""
    return port_path() if WINDOWS else door_path()


def failure_path() -> Path:
    """Why the last daemon started here could not take its lock or listen, as JSON: ``reason``, and
    ``denied`` when the system refused it (a sandbox that forbids a local port). Its stderr goes
    nowhere, so this is what the client that started it reads when it exits at once."""
    return engine_dir() / f"{NAME}.failed"


@dataclass(frozen=True)
class Endpoint:
    """Where the daemon listens and locks: its door (on Windows, its port file) and its lock."""

    address: Path
    lock: Path


def endpoints() -> list[Endpoint]:
    """The engine's endpoint in its engine folder, which ``stop`` looks at."""
    return [Endpoint(address(), lock_path())]


def lock(path: Path | None = None) -> Any:
    """The daemon's lock (or the one at ``path``), held for its life; None when
    another daemon holds it. A lock file is removed by whoever holds it (``daemon.let_go``,
    ``client.sweep``), so a lock taken on a file whose name has gone, or names another file now,
    is no lock: it is let go and the file the name names now is taken instead (``names``). Its folder is
    made first (``make_engine_dir``), and must be this user's alone (``folder_refusal``)."""
    path = path or lock_path()
    make_engine_dir(path.parent)
    refusal = folder_refusal(path.parent)
    if refusal is not None:
        raise PermissionError(refusal)
    while True:
        handle = open(path, "a+")
        try:
            if WINDOWS:
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            gone = not names(handle, path)  # its holder removed it as this opened it: open it again
            handle.close()
            if gone:
                continue
            return None
        if names(handle, path):
            return handle
        handle.close()  # taken as its last holder removed it: the name is another file's, or none


def names(handle: Any, path: Path) -> bool:
    """Whether ``path`` still names the file ``handle`` holds open. On Windows an open file is never
    removed, so it does."""
    if WINDOWS:
        return True
    try:
        held, named = os.fstat(handle.fileno()), os.lstat(path)
    except OSError:
        return False
    return (held.st_dev, held.st_ino) == (named.st_dev, named.st_ino)


# --- the installation ------------------------------------------------------------------------------


def _marker(prefix: str | None = None) -> dict[str, Any] | None:
    """The marker the server wrote in the environment at ``prefix`` (this process's), of its schema; None
    for an environment the server did not make."""
    try:
        marker = json.loads((Path(prefix or sys.prefix) / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return marker if isinstance(marker, dict) and marker.get("schema") == MARKER_SCHEMA else None


def home(prefix: str | None = None) -> dict[str, Any] | None:
    """The installation the environment at ``prefix`` (this process's, ``sys.prefix``) belongs to, as the
    marker the server wrote in it names it (``MARKER``) -- ``executable``, ``prefix``, ``root`` and the rest
    of what made it -- or None for an environment the server did not make."""
    marker = _marker(prefix)
    found = marker.get("installation") if marker is not None else None
    if not isinstance(found, dict) or not all(isinstance(found.get(name), str) for name in ("executable", "prefix", "root")):
        return None
    return found


def separate(prefix: str | None = None) -> bool:
    """Whether the environment at ``prefix`` (this process's) is one ``cad run`` made for a program beside the
    base -- its marker naming what it holds beside the base (``with``, a list, empty or not: the server's
    ``extras``) -- rather than the base itself, or an environment the server did not make."""
    marker = _marker(prefix)
    return marker is not None and isinstance(marker.get("with"), list)


def extras(prefix: str | None = None) -> tuple[str, ...]:
    """The packages the environment at ``prefix`` (this process's) holds beside the base's, as its
    marker names them (``with``: an environment ``cad run`` made for a model's own packages, the server's
    ``extras``); ``()`` for the base, and for an environment the server did not make."""
    marker = _marker(prefix)
    found = marker.get("with") if marker is not None else None
    return tuple(found) if isinstance(found, list) and all(isinstance(item, str) for item in found) else ()


# The installation this process belongs to when it runs in the base that installation made (``home``):
# ``{"executable", "prefix", "root", ...}``; None in the installation's own environment. A process there --
# a model's script ``cad run`` runs, its worker -- goes by its installation's name (``registered``) and,
# with no current installation (``engine``), starts the engine with its installation's Python
# (``client._start``).
HOME: dict[str, Any] | None = home()
# The packages this process's environment holds beside the base's, where ``cad run`` made it for a model's
# own (``extras``): its scripts name their Python, which the engine builds them in (``contract.interpreter``).
EXTRAS: tuple[str, ...] = extras()
# Whether this process's environment is one ``cad run`` made for a program beside the base (``separate``): its
# scripts name their Python, which the engine builds them in (``contract.interpreter``), whatever it holds --
# packages of its own, other integrations of cad's, another Python.
SEPARATE: bool = separate()
# How ``cad run`` named the packages of the environment it runs a program in, which it hands the program as
# JSON (``run_with``): what a document's record says builds it again (``contract.interpreter``).
RUN_WITH = "CAD_RUN_WITH"


def run_with() -> dict[str, Any]:
    """How ``cad run`` named this process's packages (``RUN_WITH``): the requirements its ``--with`` was given
    (``with``), and the script whose inline metadata named the rest (``script``) with them (``header``),
    normalized; each empty with none."""
    try:
        found = json.loads(os.environ.get(RUN_WITH) or "{}")
    except ValueError:
        found = {}
    found = found if isinstance(found, dict) else {}

    def strings(value: Any) -> list[str]:
        return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []

    script = found.get("script")
    return {"with": strings(found.get("with")), "script": script if isinstance(script, str) else None,
            "header": strings(found.get("header"))}


def installation_record(data: bytes | None) -> dict[str, Any] | None:
    """An installation's record (``installations/<version>.json``) as its bytes hold it, or None for one
    that is no record: ``version``, the absolute paths of its ``python`` and its console script
    (``cad``), its environment (``prefix``)."""
    try:
        record = json.loads(data) if data is not None else None
    except ValueError:
        return None
    if not isinstance(record, dict) or not all(isinstance(record.get(key), str)
                                               for key in ("version", "python", "cad", "prefix")):
        return None
    return record


def alive(record: dict[str, Any]) -> bool:
    """Whether the installation of ``record`` is there: its interpreter and its console script."""
    return os.path.isfile(record["python"]) and os.path.isfile(record["cad"])


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def current(state: Path | None = None) -> dict[str, Any] | None:
    """The current installation's record (``installations/current`` names its version), while its
    interpreter and console script are there (``alive``): the installation whose engine every client
    starts or attaches to. None with none current, or one that is gone."""
    folder = Path(state or state_dir())
    data = _read(folder / CURRENT)
    version = data.decode("utf-8", "replace").strip() if data is not None else ""
    if not VERSION.fullmatch(version):
        return None
    record = installation_record(_read(folder / INSTALLATIONS / f"{version}.json"))
    if record is None or record["version"] != version or not alive(record):
        return None
    return record


def engine() -> dict[str, Any] | None:
    """The installation whose engine a client starts when none answers (``client._start``), read now -- its
    Python, its environment and its version. A process with a version (``versioned``) starts its own
    version's, as its code's marker names it (``version_record``) while its Python and console script are
    there, and never another version's: None while it is not. A process with no version starts the current
    installation's (``current``), whatever release it is itself: None with none current."""
    try:
        name = versioned()
        found = version_record(name) if name is not None else current()
    except (OSError, ValueError):
        return None
    if found is None or not alive(found):
        return None
    return {"python": found["python"], "prefix": found["prefix"], "version": found["version"]}


def version_record(name: str, root: Path | None = None) -> dict[str, Any] | None:
    """Version ``name``'s code marker (``versions/<name>/code/cad-version.json``, in the versions' folder
    ``root``, ``versions_dir`` by default), written last by the install that makes the version present:
    ``schema`` (``VERSION_SCHEMA``), ``version`` (``name``), and the absolute paths of the server
    environment's ``python``, its console script (``cad``) and the environment (``prefix``) -- the shape of an
    installation's record (``installation_record``) --, with whatever else the install keeps there. None
    while there is none of that shape, or for a name that is no version."""
    if not VERSION.fullmatch(name or ""):
        return None
    record = installation_record(_read(Path(root or versions_dir()) / name / CODE / VERSION_MARKER))
    if record is None or record.get("schema") != VERSION_SCHEMA or record["version"] != name:
        return None
    return record


def versioned() -> str | None:
    """The version this process belongs to in the per-version layout, or None for a process with no
    version (the module's rule): told its name (``CAD_INSTALLATION_VERSION``) where that version's code
    marker is there (``version_record``); else the version whose ``code`` folder holds this process's
    environment or its home's (``HOME``: the server environment whose base a kernel process runs in); else
    the version whose code marker names one of those environments (a development install, which runs from
    its checkout). Read once per process, state folder and name told (``_versioned``)."""
    return _versioned(str(state_dir()), os.environ.get(INSTALLATION_ENV, ""), _prefixes(sys.prefix, _home_prefix()))


@functools.cache
def _prefixes(*given: str) -> tuple[str, ...]:
    """The environments ``given``, each resolved once (``os.path.realpath``), without repeats."""
    return tuple(dict.fromkeys(os.path.realpath(prefix) for prefix in given))


@functools.cache
def _versioned(state: str, named: str, prefixes: tuple[str, ...]) -> str | None:
    root = Path(state) / VERSIONS
    if VERSION.fullmatch(named) and version_record(named, root) is not None:
        return named
    inside = os.path.realpath(root).rstrip(os.sep) + os.sep
    for prefix in prefixes:  # ``normcase`` keeps a path's length: the name is cut from the real spelling
        if os.path.normcase(prefix).startswith(os.path.normcase(inside)):
            name, _, rest = prefix[len(inside):].partition(os.sep)
            if VERSION.fullmatch(name) and os.path.normcase(rest).split(os.sep)[0] == CODE:
                return name
    try:
        names = sorted(entry.name for entry in os.scandir(root) if VERSION.fullmatch(entry.name))
    except OSError:
        return None
    mine = {os.path.normcase(prefix) for prefix in prefixes}
    for name in names:
        record = version_record(name, root)
        if record is not None and os.path.normcase(os.path.realpath(record["prefix"])) in mine:
            return name
    return None


def _home_prefix() -> str:
    """The environment of the installation this process belongs to (``HOME``), else its own."""
    return HOME["prefix"] if HOME else sys.prefix


def installation() -> str:
    """The version this installation runs as -- the one name its client, its daemon and its workers
    all go by (``status``, its bytecode): its version where it has one (``versioned``); else, with no
    version, as before 0.12: ``CAD_INSTALLATION_VERSION`` when it names one (the ``cad`` command sets
    it for a development install, which reports its release's version), else the version this
    environment is registered as (``registered``: a dev environment's ``python model.py`` run directly),
    else the release declared beside this code (``previous.version``)."""
    from cad.engine.previous import version

    mine = versioned()
    if mine is not None:
        return mine
    named = os.environ.get(INSTALLATION_ENV, "")
    if re.fullmatch(r"[0-9][0-9A-Za-z.+_-]*", named):
        return named
    return registered() or version()


def registered() -> str | None:
    """The version this environment (``sys.prefix``, or ``HOME``'s) is registered as in the user's state folder
    (``installations/<version>.json``), when one names its release or a development build of it
    (``<release>-dev.<time>``): the one registered last. None with no such record -- and for a record of
    another release, left from before an upgrade into this environment (``pip install -U``), which is not
    what runs here now. Read once per process and state folder."""
    from cad.engine.previous import version

    return _registered(str(state_dir()), os.path.normcase(os.path.realpath(_home_prefix())), version())


@functools.cache
def _registered(state: str, prefix: str, release: str) -> str | None:
    folder = Path(state) / INSTALLATIONS
    found: list[tuple[float, str]] = []
    try:
        entries = [entry for entry in os.scandir(folder) if entry.name.endswith(".json")]
    except OSError:
        return None
    for entry in entries:
        try:
            record = json.loads(Path(entry.path).read_text(encoding="utf-8"))
            given = record["version"]
            if (isinstance(given, str) and given == entry.name[:-5] and isinstance(record.get("prefix"), str)
                    and os.path.normcase(os.path.realpath(record["prefix"])) == prefix
                    and (given == release or given.startswith(f"{release}-dev."))):
                found.append((entry.stat().st_mtime, given))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return max(found)[1] if found else None


# --- starting a process of the engine's -----------------------------------------------------------


def engine_root() -> str:
    """The folder ``cadgen`` is imported from: a process the engine starts there imports the same."""
    return str(Path(__file__).resolve().parent.parent.parent)


# Windows' process creation flags, by number: ``subprocess`` names them on Windows alone.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)


def windowless() -> dict[str, Any]:
    """How the engine starts a process -- a worker, a reader, a render process -- on Windows: with
    a console of its own and no window (``CREATE_NO_WINDOW``); elsewhere as it is. A console program
    started with no console gets a new one, with a window (#597): a window per process, open as long
    as it lives, and closing one ends it."""
    return {"creationflags": CREATE_NO_WINDOW} if os.name == "nt" else {}


def standard_input_aside() -> int:
    """A process its starter speaks to, or watches, on its standard input: that pipe taken aside, on a
    descriptor of the process's own (returned), and standard input (descriptor 0, ``sys.stdin``) the null
    device from then on. On Windows a thread blocked reading a pipe holds every other call on that pipe --
    GetFileType, which a DLL's C runtime asks of the standard handles as the DLL loads (numpy's OpenBLAS,
    say) -- so an import while the pipe is read would wait for the pipe's next line, or its end: a process
    that never gets on. And a library reading its input reads none of the pipe. Called before any thread
    reads the pipe: a worker (``worker.main``), a process a manufacturing check is measured in
    (``cad._internal.manufacturing._child``)."""
    kept = os.dup(0)
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    sys.stdin = open(os.devnull, encoding="utf-8")  # noqa: SIM115 - standard input, for the process's life
    return kept


def detached() -> dict[str, Any]:
    """How the daemon is started: outliving the command that needed it. On Windows a console of its
    own with no window and a process group of its own, never no console at all (``DETACHED_PROCESS``),
    which would give each console program it starts a window of its own (#597); elsewhere a session
    of its own (``start_new_session`` is POSIX's: Windows takes it as nothing)."""
    if os.name == "nt":
        return {"creationflags": CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def bytecode(env: dict[str, str]) -> dict[str, str]:
    """``env`` (the daemon's, or a worker's), its bytecode set as the engine's processes keep it:
    cached in a folder of the engine's (``PYTHONPYCACHEPREFIX``, ``pycache``), so a worker's start
    imports the kernel's pure-Python libraries from bytecode (a uvx installation compiles nothing
    on install: every start compiled them, seconds each) and nothing is written beside a library
    or a model. A ``PYTHONPYCACHEPREFIX`` already given is honoured. A caller's
    ``PYTHONDONTWRITEBYTECODE`` is not: the daemon and its workers serve every later client, and
    write their bytecode in a folder of their own. With no such folder this user alone can write -- one
    others can write to, or one a sandbox refuses -- nothing is written: ``PYTHONDONTWRITEBYTECODE``. A
    model's own modules are compiled from their source whatever this says (``build._SourceOnlyLoader``)."""
    if not env.get("PYTHONPYCACHEPREFIX"):
        env.pop("PYTHONPYCACHEPREFIX", None)
        folder = pycache()
        if folder is None:
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            return env
        env["PYTHONPYCACHEPREFIX"] = folder
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    return env


def pycache() -> str | None:
    """This installation's bytecode folder, made this user's alone and marked in use (its time); None where
    there is none to use. A version's is ``pycache`` in its code (``code_dir``), which goes with the version,
    each Python's files told apart by their names; with no version, this installation's folder under
    ``pycache/`` in the cache folder before 0.12 (``bytecode_tag``), which the daemon prunes."""
    mine = versioned()
    root = code_dir(mine) if mine is not None else legacy_cache_dir() / PYCACHE
    folder = root / PYCACHE if mine is not None else root / bytecode_tag()
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.mkdir(exist_ok=True, mode=0o700)
        os.utime(folder)  # in use: the daemon's prune leaves it
    except OSError:
        return None
    if not WINDOWS and not (_users_own(str(root)) and _users_own(str(folder))):
        return None  # a folder another can write to would hand them the engine's code
    return str(folder)


def bytecode_tag() -> str:
    """This installation's folder of bytecode under ``pycache/`` (``pycache``): its environment, its
    interpreter's version and the version it runs as (``installation``)."""
    prefix = os.path.normcase(os.path.realpath(_home_prefix()))
    material = f"{prefix}|{sys.implementation.cache_tag}|{installation()}"
    return hashlib.sha256(material.encode()).hexdigest()[:12]


# The environment every process of the engine's that loads the kernel runs in -- a model's worker (but
# one a script names its own Python for: ``contract.interpreter``), the standby, the documents worker,
# the meshing and reading pools, the render processes -- as the server makes it
# (``cad_server._internal.base.kernel``: the installation's base): ``KERNEL(make)`` answers
# ``{"python", "prefix", "path", "own"}``, or None when it is not made and ``make`` is false, and raises,
# saying why, when it cannot be made. None (no server in this process: a model's own process, a worker):
# this interpreter's own (``kernel``).
KERNEL: Callable[[bool], dict[str, Any] | None] | None = None


def kernel(make: bool = True) -> dict[str, Any] | None:
    """The environment the engine's kernel processes run in (``KERNEL``): ``{"python", "prefix", "path",
    "own"}`` -- ``prefix``: the environment, which a build in its caller's Python is told from (the
    server's ``Daemon.caller``); ``own``: this interpreter's environment, whose engine folder a process
    started there is given and whose import path a spawned process is handed as it is -- or None when it
    is not made and ``make`` is false. ``serve.KernelProcessesUnavailable`` when it cannot be made, saying
    why and with the cause the server gave its refusal (its ``cause``, else ``other``): no kernel process starts
    without it. What the server remembers of a failed making is the server's (``KERNEL``)."""
    if KERNEL is None:
        return {"python": sys.executable, "prefix": sys.prefix, "path": None, "own": True}
    try:
        return KERNEL(make)
    except Exception as error:  # noqa: BLE001 - the server's refusal, carried in one line
        from cad.engine.serve import KernelProcessesUnavailable

        cause = getattr(error, "cause", None)
        raise KernelProcessesUnavailable(f"the server has no CAD kernel environment: {error}",
                                         cause if isinstance(cause, str) else "other") from error
