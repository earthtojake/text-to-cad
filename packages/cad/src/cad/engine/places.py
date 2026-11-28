"""Where cad's things are on this computer, and how a process of the engine's is started.

Every process reads this: a model's script and its worker, in the CAD kernel environment where only the
library is installed; the engine's server; each client of it. So each finds the same folders, the same
engine and the same installation by the same rules, from the standard library alone and with no kernel.

- **The user's folders**: the state folder (``state_dir``: settings, the library, the
  installations' records, the page token) and the cache folder (``cache_dir``: what the engine derived of each
  file, the bytecode the engine's processes compile, the kernel environment). One of each a user, whatever
  release of cad runs: the layout of 0.11.11 and earlier, kept as it was.
- **The engine folder** (``engine_dir``): the device's one engine's door (a named pipe; on Windows a
  port file), lock, failure note and pages note, in a folder only this user can write (``folder_refusal``), each named
  ``engine`` (``NAME``) whatever release runs it.
- **The installation** a process belongs to: the version it runs as (``installation``), the base's
  marker naming the installation of a process that runs in the base (``HOME``), and the current one the
  clients of 0.11.11 and earlier start (``current``).
- **Starting a process** of the engine's: with no window on Windows (``windowless``), outliving its
  starter (``detached``), on Windows outside any app package by Task Scheduler (``outside_package``: the server and
  cad's update; its go-between, ``cad.engine.handoff``), its bytecode kept in the cache folder (``bytecode``), and
  on the Python of the environment the kernel is in (``kernel``, which the server makes as ``KERNEL``: the installation's base,
  the library with its ``build123d`` extra).
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

__all__ = ["BYTECODE", "DISPLAY", "EXTRAS", "HOME", "KERNEL", "SEPARATE", "NAME", "RESTARTS", "WINDOWS", "XAUTHORITY", "Endpoint", "address",
           "alive", "appdata_cache_dir", "appdata_engine_dir", "appdata_state_dir", "bytecode", "bytecode_tag",
           "cache_dir", "current", "detached", "door_path", "earlier_cache_dir", "earlier_state_dir", "endpoints",
           "engine_dir", "engine_root", "extras", "failure_path", "folder_refusal", "home", "installation",
           "kernel", "lock", "lock_path", "make_engine_dir", "outside_package", "packaged", "port_path", "registered",
           "state_dir", "tidy_handoff", "used", "windowless"]

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
# The folder of the engine's bytecode in the cache folder: one folder per installation in it
# (``bytecode_tag``).
PYCACHE = "pycache"
# The installations' records in the state folder, and the file naming the current one's version: what the
# clients of 0.11.11 and earlier start a server by (``current``).
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
# and what the homes show of them (Recents) -- and the receipt 0.8's setup wrote, by which ``cad setup --engine-update``
# tells a computer our own setup reached. Not 0.8's
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
    """Where this user's CAD state lives (``CAD_STATE_DIR`` overrides it): ``cad`` in the platform's
    place for state (``_local_state``). Every release of cad reads and writes the same one: settings, the
    library, the page token and port, the telemetry spool, the version feed's cache, the
    installations' records."""
    override = os.environ.get("CAD_STATE_DIR")
    if override:
        return Path(override)
    return _local_state() / STATE


def appdata_state_dir() -> Path | None:
    """Where 0.10.0 kept its state on Windows, ``%LOCALAPPDATA%\\cad-state``, which this release moves out of
    (``APPDATA_STATE``); None elsewhere, or where ``CAD_STATE_DIR`` names the state folder."""
    return _appdata() / APPDATA_STATE if WINDOWS and not os.environ.get("CAD_STATE_DIR") else None


def appdata_cache_dir() -> Path | None:
    """Where 0.10.0 kept its cache on Windows, ``%LOCALAPPDATA%\\cad``: its documents' bytes move with their
    records (``adopt_earlier``), the rest is left where it is; None elsewhere, or where
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
    """What this release keeps of an earlier release's state folder moved into its own (``adopt``: the state
    folder and ``cache_dir``), where no state folder is named (``CAD_STATE_DIR``): what ``cad setup
    --engine-update`` does as it takes over from 0.10.0 on Windows before it writes there. Each thing moves
    once: once this release's folder has it, the earlier one's stays. The names moved."""
    if os.environ.get("CAD_STATE_DIR"):
        return []
    moved: list[str] = []
    # 0.10.0's Windows folder first: what it took of 0.8's is there, and 0.8's keeps a telemetry no that is
    # no person's whole settings.
    appdata, appdata_cache = appdata_state_dir(), appdata_cache_dir()
    if appdata is not None:
        moved += adopt(appdata, state_dir(), APPDATA_ADOPTED)
    if appdata_cache is not None:  # the bytes of the documents whose records moved, so Recents still opens them
        moved += adopt(appdata_cache, cache_dir(), ("documents",))
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


def cache_dir() -> Path:
    """Where cad caches what it can make again -- what it derived of a document (``documents/<id>/...``, a shared
    file's last view bundle among it), hulls, MJCF assets, integrations' homes, the kernel environments, the engine's
    bytecode --: the platform's cache location, which the system and the person treat as disposable -- wiping it
    loses no state, the library and the shares' records stay in ``state_dir``. ``CAD_CACHE_DIR`` when set (a
    relative one made absolute once, and written back, so
    a worker after a ``chdir`` names the same folder), else ``$XDG_CACHE_HOME/cad`` when set, else
    ``~/.cache/cad`` -- on Windows too, out of the local application data an app package virtualizes
    (``APPDATA_STATE``). An earlier release's cache (named for cadgen, or 0.10.0's on Windows) is not read: it
    is a cache."""
    return _cache_dir(CACHE, appdata=False)


def used(path: str | os.PathLike) -> None:
    """A file of the cache folder read: its access time set to now, its modification time kept, so that what goes
    first where the cache is held to a size is what was used longest ago -- the later of its last read and its last
    write (``cad cache prune``: the meshes kept by the geometry they are of) -- while what tells a file written again
    by its modification time (a view bundle's writer) still can. Two calls that write no byte of the file; one that
    cannot be touched (gone meanwhile, another user's) keeps its times."""
    try:
        os.utime(path, ns=(time.time_ns(), os.stat(path).st_mtime_ns))
    except OSError:
        pass


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


def engine_dir() -> Path:
    """Where the engine's door and lock live: ``CAD_ENGINE_DIR``, else ``default_engine_dir`` -- the folder every
    release of cad finds, 0.11.11 and earlier among them. Resolved once, here, for the client and the server
    alike (``os.path.realpath``): a ``..``, a symlink or a trailing slash in either spelling names the same
    door, lock and port file. It stays in the temporary (runtime) folder, never under the state folder: a
    sandboxed client must make its pipes there (``door.CLIENTS``), and a sandbox lets it write the temporary
    folder alone."""
    override = os.environ.get("CAD_ENGINE_DIR")
    return Path(os.path.realpath(override if override else default_engine_dir()))


def make_engine_dir() -> Path:
    """The engine folder (``engine_dir``) made where it is not, this user's alone (mode 700). ``PermissionError``
    when the system refuses."""
    folder = engine_dir()
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


def pages_path() -> Path:
    """The port the last server stopped here served pages on, as JSON (``{"port": N}``): noted by the client that
    stopped it (``client.sweep``), taken by the next server as it starts, which serves pages there at once
    (``daemon.resumed``), so a page open in a browser reconnects to the server that replaced its own."""
    return engine_dir() / f"{NAME}.pages"


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
    made first, and must be this user's alone (``folder_refusal``)."""
    path = path or lock_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    refusal = folder_refusal(path.parent)
    if refusal is not None:
        raise PermissionError(refusal)
    while True:
        handle = _opened(path)
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


def _opened(path: Path) -> Any:
    """The lock file opened, to take the lock on. Windows refuses to open a file (EACCES) while it is being
    removed -- its last holder letting it go (``daemon.let_go``, ``client.sweep``) as another start opens it
    -- so there that refusal waits out the ladder a rename's does (``atomic_replace``) before it is the
    system's: starts at the same moment end with one server, none of them refused."""
    if WINDOWS:
        from cad.engine.atomic_replace import RETRY_DELAYS_SECONDS

        for delay in RETRY_DELAYS_SECONDS:
            try:
                return open(path, "a+")
            except PermissionError:
                time.sleep(delay)
    return open(path, "a+")


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
    interpreter and console script are there (``alive``): the installation whose engine every client of
    0.11.11 and earlier starts or attaches to. None with none current, or one that is gone."""
    folder = Path(state or state_dir())
    data = _read(folder / CURRENT)
    version = data.decode("utf-8", "replace").strip() if data is not None else ""
    if not VERSION.fullmatch(version):
        return None
    record = installation_record(_read(folder / INSTALLATIONS / f"{version}.json"))
    if record is None or record["version"] != version or not alive(record):
        return None
    return record


def _home_prefix() -> str:
    """The environment of the installation this process belongs to (``HOME``), else its own."""
    return HOME["prefix"] if HOME else sys.prefix


def installation() -> str:
    """The version this installation runs as -- the one name its client, its daemon and its workers
    all go by (``status``, its bytecode): ``CAD_INSTALLATION_VERSION`` when it names one (a development
    build's name, which reports its release's version), else the version this environment is registered as
    (``registered``: a dev environment's ``python model.py`` run directly), else the release declared beside
    this code (``previous.version``)."""
    from cad.engine.previous import version

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
CREATE_BREAKAWAY_FROM_JOB = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)


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


def detached(*, breakaway: bool = False) -> dict[str, Any]:
    """How the daemon is started: outliving the command that needed it. On Windows a console of its
    own with no window and a process group of its own, never no console at all (``DETACHED_PROCESS``),
    which would give each console program it starts a window of its own (#597); with ``breakaway``,
    out of the job its starter is in too (``CREATE_BREAKAWAY_FROM_JOB``: an agent app that closes the
    job of the commands it ran ends every process in it), which only ``outside_package`` is handed,
    since it starts again without it where the job allows no breakaway. Elsewhere a session of its own
    (``start_new_session`` is POSIX's: Windows takes it as nothing)."""
    if os.name == "nt":
        return {"creationflags": CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
                | (CREATE_BREAKAWAY_FROM_JOB if breakaway else 0)}
    return {"start_new_session": True}


# Windows: ``GetCurrentPackageFullName``'s answer for a process no app package started (APPMODEL_ERROR_NO_PACKAGE).
NO_PACKAGE = 15700
# What ``outside_package`` hands Task Scheduler: the folder in the state folder where a start's request, its task's
# definition and the go-between's answer are kept while it lasts (never under AppData, which a packaged caller sees
# a private copy of and the task does not), and how long the go-between is waited for, from ``/Run`` to its answer:
# measured, 0.8 to 1.6 s from the task's creation to the go-between's first line.
HANDOFF = "handoff"
HANDOFF_SECONDS = 5.0
# How long the go-between is waited for to end, once it has answered, before its task is deleted; and how old a file
# in ``HANDOFF`` is when it is a crash's leftover (``tidy_handoff``): no hand-off lasts a minute.
BETWEEN_MS = 2000
HANDOFF_STALE_SECONDS = 60.0
# The task's definition: Task Scheduler's schema, and the access a handle on a process started needs (``Started``).
TASK = "http://schemas.microsoft.com/windows/2004/02/mit/task"
SYNCHRONIZE, PROCESS_QUERY_LIMITED_INFORMATION = 0x00100000, 0x1000
LOG = logging.getLogger("cad.engine.places")


def packaged() -> bool:
    """Whether this process runs inside a Windows app package (an MSIX app such as a desktop app from the Store, or a
    process one started): ``GetCurrentPackageFullName`` says a package. False elsewhere, and where it cannot be
    asked."""
    if not WINDOWS:
        return False
    try:
        import ctypes

        length = ctypes.c_uint32(0)
        return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None) != NO_PACKAGE
    except (AttributeError, OSError):
        return False


class Started:
    """The process ``outside_package`` had Task Scheduler start, as much of ``subprocess.Popen`` as a starter asks of
    it: ``pid``, ``poll``. ``handle``: a handle on it (``SYNCHRONIZE``, ``PROCESS_QUERY_LIMITED_INFORMATION``), or
    None where none could be opened, and then ``poll`` says it runs: its door says the rest."""

    def __init__(self, handle: Any, pid: int, kernel: Any) -> None:
        self.handle, self.pid, self.kernel, self.returncode = handle, pid, kernel, None

    def poll(self) -> int | None:
        import ctypes
        from ctypes import wintypes

        if self.returncode is None and self.handle and self.kernel.WaitForSingleObject(self.handle, 0) == 0:
            code = wintypes.DWORD(0)
            self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code))
            self.returncode = code.value
            self.kernel.CloseHandle(self.handle)
        return self.returncode


def outside_package(command: list[str], **options: Any) -> Any:
    """``command`` started as ``subprocess.Popen(command, ..., **options)`` starts it -- but on Windows, from inside an
    app package (``packaged``), outside it: inside one, new files under AppData land in the app's private copy while
    deletes are real, so a server or an update started there would leave cad broken for every other program. Task
    Scheduler starts it (``_hand_off``): a task's process is the scheduler's, never the app's child, so no package
    holds it. Its standard streams are the null device, as every caller's are. Where the hand-off cannot be made (no
    ``schtasks``, a policy that refuses it, no session the task can start in, a go-between that never answers), that
    is logged once and ``command`` is started as it would be elsewhere (cad's update then refuses by itself). Out of
    the starter's job where ``creationflags`` asks it (``detached(breakaway=True)``) and the job allows it: where it
    does not, Windows refuses the start and ``command`` starts in the job, as ``cad.engine.handoff`` does. The
    process started: what ``poll`` and ``pid`` are asked of. Raises only as ``subprocess.Popen`` does."""
    flags = options.get("creationflags", 0)
    if packaged():
        env = options.get("env")
        try:
            # The go-between asks for the breakaway itself, and starts without it where it is refused.
            return _hand_off(command, env=dict(os.environ) if env is None else env,
                             cwd=options.get("cwd") or os.getcwd(), flags=flags & ~CREATE_BREAKAWAY_FROM_JOB)
        except Exception as error:  # noqa: BLE001 - started as elsewhere: what runs there refuses what it must not do
            LOG.warning("Task Scheduler could not start %s outside this Windows app package, so it starts inside it: "
                        "%s: %s", Path(command[0]).name, type(error).__name__, error)
    try:
        return subprocess.Popen(command, **options)
    except OSError:
        if not flags & CREATE_BREAKAWAY_FROM_JOB:
            raise
    return subprocess.Popen(command, **{**options, "creationflags": flags & ~CREATE_BREAKAWAY_FROM_JOB})


def _hand_off(command: list[str], *, env: dict[str, str], cwd: str | None, flags: int,
              run: Callable[..., Any] | None = None, kernel: Any = None, seconds: float = HANDOFF_SECONDS) -> Started:
    """``command`` started by Task Scheduler (``outside_package``): its request (``argv``, ``env`` -- only the variables
    cad and the tools it runs need, ``handoff.carried``, never the whole environment --, ``cwd``, ``flags``) written
    to ``HANDOFF`` in the state folder, what a crash left there first removed (``tidy_handoff``), a task of the
    current user's that runs it registered from a definition (``_task_definition``: no trigger, run only by ``/Run``),
    run, and its go-between (``cad.engine.handoff``) waited for until it says the process it started (``seconds`` at
    most); then the task deleted and every file of it removed, whatever happened. ``run``: ``schtasks`` with its
    arguments (``_schtasks``; a test's stand-in), ``kernel``: kernel32 (a test's). ``OSError`` where a ``schtasks``
    call fails or the go-between could not start ``command``, ``TimeoutError`` where it never answered."""
    from cad.engine.handoff import carried

    run = run or _schtasks
    kernel = kernel or _kernel32()
    folder = state_dir() / HANDOFF
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    tidy_handoff()
    name = f"cad-{os.getpid()}-{secrets.token_hex(6)}"
    request, definition, reply = (folder / f"{name}{suffix}" for suffix in (".json", ".xml", ".pid"))
    made = False
    try:
        told = {"argv": command, "env": {name: value for name, value in env.items() if carried(name)}, "cwd": cwd,
                "flags": flags, "reply": str(reply), "wait": seconds}
        with open(os.open(request, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as handle:
            json.dump(told, handle)  # its owner's alone where the system says so: on Windows the folder's permissions
        definition.write_bytes(_task_definition(_between(request), user=_user()))
        run("/Create", "/XML", str(definition), "/TN", name, "/F")
        made = True
        run("/Run", "/TN", name)
        answer = _answer(request, reply, seconds)
        if "error" in answer:
            raise OSError(f"the go-between could not start it: {answer['error']}")
        pid, middle = answer["pid"], _open(kernel, answer.get("between"))
        started = Started(_open(kernel, pid), pid, kernel)
        reply.unlink(missing_ok=True)  # the go-between's word to end
        if middle:
            kernel.WaitForSingleObject(middle, BETWEEN_MS)
            kernel.CloseHandle(middle)
        return started
    finally:
        for path in (request, definition, reply, reply.with_name(f"{reply.name}.part"),
                     request.with_name(f"{request.name}.taken")):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        if made:
            try:
                run("/Delete", "/TN", name, "/F")
            except Exception:  # noqa: BLE001 - a task left behind runs only on /Run
                pass


def tidy_handoff(now: float | None = None) -> list[Path]:
    """What a hand-off that crashed left in ``HANDOFF`` (a request, which can carry a proxy's credentials, a definition,
    an answer): each file older than ``HANDOFF_STALE_SECONDS`` removed, at each hand-off and at the server's start.
    The paths removed. Never raises."""
    removed, now = [], time.time() if now is None else now
    try:
        entries = list(os.scandir(state_dir() / HANDOFF))
    except OSError:
        return removed
    for entry in entries:
        try:
            if entry.is_file(follow_symlinks=False) and now - entry.stat(follow_symlinks=False).st_mtime > \
                    HANDOFF_STALE_SECONDS:
                os.remove(entry.path)
                removed.append(Path(entry.path))
        except OSError:
            continue  # in use: the next tidying
    return removed


def _between(request: Path) -> list[str]:
    """The go-between's command (``cad.engine.handoff``), its ``request`` file named: this environment's ``pythonw.exe``
    where there is one (no console, so no window flashes), else its Python, running the module's file isolated
    (``-I``), so nothing of the caller's environment or of a ``PYTHONPATH`` decides what it imports."""
    python = Path(sys.executable)
    windowless_python = python.with_name("pythonw.exe")
    return [str(windowless_python if WINDOWS and windowless_python.is_file() else python), "-I",
            str(Path(__file__).with_name("handoff.py")), str(request)]


def _task_definition(command: list[str], *, user: str | None = None) -> bytes:
    """The task ``_hand_off`` registers (``schtasks /Create /XML``, which reads UTF-16), running ``command``: no
    trigger, so it runs only when ``/Run`` asks; ``user`` (the current one, ``DOMAIN\\name``) by an interactive token,
    with least privilege and no password stored, so it runs in their session while they are logged on and never
    elevated; on battery as on mains; instances in parallel; hidden; a minute at most (the go-between ends at once);
    and at normal priority (a task's default, 7, is below normal, and the processes it starts would inherit it)."""
    from xml.sax.saxutils import escape

    def quoted(part: str) -> str:
        return f'"{part}"' if " " in part else part

    executable, arguments = quoted(command[0]), subprocess.list2cmdline(command[1:])
    named = f"<UserId>{escape(user)}</UserId>" if user else ""
    text = ('<?xml version="1.0" encoding="UTF-16"?>\n'
            f'<Task version="1.2" xmlns="{TASK}">'
            "<RegistrationInfo><Description>cad starts a process of its own outside an app package</Description>"
            "</RegistrationInfo>"
            f'<Principals><Principal id="Author">{named}<LogonType>InteractiveToken</LogonType>'
            "<RunLevel>LeastPrivilege</RunLevel></Principal></Principals>"
            "<Settings><MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy>"
            "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
            "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate>"
            "<StartWhenAvailable>false</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>"
            "<IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>"
            "<AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><Hidden>true</Hidden>"
            "<RunOnlyIfIdle>false</RunOnlyIfIdle><WakeToRun>false</WakeToRun>"
            "<ExecutionTimeLimit>PT1M</ExecutionTimeLimit><Priority>5</Priority></Settings>"
            f'<Actions Context="Author"><Exec><Command>{escape(executable)}</Command>'
            f"<Arguments>{escape(arguments)}</Arguments></Exec></Actions>"
            "</Task>\n")
    return b"\xff\xfe" + text.encode("utf-16-le")


def _answer(request: Path, reply: Path, seconds: float) -> dict[str, Any]:
    """The go-between's answer (``reply``), awaited ``seconds`` at most. Where none came, the request is taken back
    (deleted) so no go-between that starts later starts ``command`` too; where the go-between took it first (renamed
    it), it is waited for as long again. ``TimeoutError`` where no answer comes."""
    deadline, extended = time.monotonic() + seconds, False
    while True:
        try:
            answer = json.loads(reply.read_text(encoding="utf-8"))
            if isinstance(answer, dict):
                return answer
        except (OSError, ValueError):
            pass
        if time.monotonic() > deadline:
            try:
                request.unlink()
            except FileNotFoundError:  # taken: the go-between is starting it
                if not extended:
                    deadline, extended = time.monotonic() + seconds, True
                    continue
            raise TimeoutError(f"Task Scheduler's task did not answer within {seconds:g} s")
        time.sleep(0.02)


def _schtasks(*arguments: str) -> None:
    """Windows' ``schtasks.exe`` run with ``arguments``, with no window; ``OSError`` saying its last line where it
    fails."""
    program = Path(os.environ.get("SystemRoot") or r"C:\Windows") / "System32" / "schtasks.exe"
    done = subprocess.run([str(program), *arguments], stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                          check=False, **windowless())
    if done.returncode != 0:
        said = (done.stderr or done.stdout or b"").decode(errors="replace").strip().splitlines()
        raise OSError(f"schtasks {arguments[0]} exited {done.returncode}: {said[-1] if said else 'nothing said'}")


def _user() -> str | None:
    """The current user as Task Scheduler names them, ``DOMAIN\\name`` (``GetUserNameExW``, else the environment);
    None where neither says."""
    try:
        import ctypes

        size = ctypes.c_ulong(512)
        buffer = ctypes.create_unicode_buffer(size.value)
        if ctypes.windll.secur32.GetUserNameExW(2, buffer, ctypes.byref(size)):  # NameSamCompatible
            return buffer.value
    except (AttributeError, OSError):
        pass
    domain, name = os.environ.get("USERDOMAIN"), os.environ.get("USERNAME")
    return f"{domain}\\{name}" if domain and name else None


def _kernel32() -> Any:
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    return kernel


def _open(kernel: Any, pid: Any) -> Any:
    """A handle on process ``pid`` (``SYNCHRONIZE``, ``PROCESS_QUERY_LIMITED_INFORMATION``), or None."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    return kernel.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid) or None


def bytecode(env: dict[str, str]) -> dict[str, str]:
    """``env`` (the daemon's, or a worker's), its bytecode set as the engine's processes keep it:
    cached under ``pycache/`` in the cache folder (``PYTHONPYCACHEPREFIX``, ``pycache``), so a worker's start
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
    """This installation's folder under ``pycache/`` in the cache folder (``bytecode_tag``), made this user's
    alone and marked in use (its time), which the daemon prunes; None where there is none to use."""
    root = cache_dir() / PYCACHE
    folder = root / bytecode_tag()
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
