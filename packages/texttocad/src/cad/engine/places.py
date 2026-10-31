"""Where cadgen's things are on this computer, and how a process of the engine's is started.

Every process reads this: a model's script and its worker, in the CAD kernel environment where only the
library is installed; the engine's server; each client of it. So each finds the same folders, the same
engine and the same installation by the same rules, from the standard library alone and with no kernel.

- **The user's folders**: the state folder (``state_dir``: settings, the documents' records, the
  installations' records, the page token) and the cache folder (``cache_dir``: each model document's
  bytes, the bytecode the engine's processes compile, the kernel environment).
- **The engine folder** (``engine_dir``): the device's one engine's door (a named pipe; on Windows a
  port file), lock and failure note, in a folder only this user can write (``folder_refusal``), each named
  ``engine`` (``NAME``) whatever release runs it.
- **The installation** a process belongs to: the version it runs as (``installation``), the base's
  marker naming the installation of a process that runs in the base (``HOME``), and the current one,
  whose engine a client starts when none answers (``current``, ``engine``).
- **Starting a process** of the engine's: with no window on Windows (``windowless``), outliving its
  starter (``detached``), its bytecode kept in the cache folder (``bytecode``), and on the Python of the
  environment the kernel is in (``kernel``, which the server makes as ``KERNEL``: the installation's base).
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

__all__ = ["BYTECODE", "HOME", "KERNEL", "NAME", "RESTARTS", "WINDOWS", "Endpoint", "address", "alive", "bytecode",
           "bytecode_tag", "cache_dir", "current", "detached", "door_path", "endpoints", "engine", "engine_dir",
           "engine_root", "failure_path", "folder_refusal", "home", "installation", "kernel", "lock", "lock_path",
           "port_path", "registered", "state_dir", "windowless"]

WINDOWS = os.name == "nt"
# The engine's name in its engine folder: its lock, door (on Windows its port file) and failure note
# are ``engine.lock``, ``engine.door``, ``engine.port`` and ``engine.failed``. One engine a device: the
# one a client finds there, whatever release it runs, and whatever release the client is. Its record in
# the state folder (the port it rolled to) goes by the same name.
NAME = "engine"
# The version an installation that cannot know its own name runs as (a development install's
# ``<version>-dev.<time>``, set by its launcher and the ``cadgen`` command): the name its records
# and its engine's ``status`` give it (``installation``).
INSTALLATION_ENV = "CADGEN_INSTALLATION_VERSION"
# What a worker's environment must share with a request's for the request to use it: what shapes
# the import system of the interpreter it started (the interpreter itself is the engine's kernel
# environment's, ``kernel``). A run adopts the rest of its caller's environment (``worker.adopt``), so a
# caller whose PATH changes from one run to the next (an agent's shell) keeps its warm worker and its memo.
RESTARTS = ("PYTHONPATH", "PYTHONHOME", "PYTHONSAFEPATH", "PYTHONNOUSERSITE", "PYTHONUSERBASE", "PYTHONPLATLIBDIR")
# How the engine's processes treat bytecode (``bytecode``): one of the two, never a run's to change.
BYTECODE = ("PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE")
# The folder of the engine's bytecode in the cache folder: one folder per installation in it
# (``bytecode_tag``).
PYCACHE = "pycache"
# The installations' records in the state folder, and the file naming the current one's version.
INSTALLATIONS = "installations"
CURRENT = f"{INSTALLATIONS}/current"
VERSION = re.compile(r"[0-9][0-9A-Za-z.+_-]*")
# The marker the server writes last in the environment it makes for the kernel (the base), naming the
# installation it belongs to (``home``), and the marker's schema.
MARKER = "cadgen-env.json"
MARKER_SCHEMA = "cadgen env/2"


# --- the user's folders ----------------------------------------------------------------------------


def state_dir() -> Path:
    """Where this user's CAD state lives (``CADGEN_STATE_DIR`` overrides it)."""
    override = os.environ.get("CADGEN_STATE_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "cadgen"
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "cadgen-state"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "cadgen"


def cache_dir() -> Path:
    """Where the engine caches documents' bytes (``documents/<id>/document.xbf``): the platform's
    cache location, which the system and the person treat as disposable -- wiping it loses no
    state, the records stay in ``state_dir``. ``CADGEN_CACHE_DIR`` when set (a relative one made
    absolute once, and written back, so a worker after a ``chdir`` names the same folder), else
    ``$XDG_CACHE_HOME/cadgen`` on POSIX or ``%LOCALAPPDATA%\\cadgen`` on Windows when set, else
    ``~/.cache/cadgen``: the folder cadgen 0.7 kept its store in, by the same rule."""
    override = os.environ.get("CADGEN_CACHE_DIR", "").strip()
    if override:
        root = Path(override).expanduser()
        if not root.is_absolute():
            root = (Path.cwd() / root).resolve()
            os.environ["CADGEN_CACHE_DIR"] = str(root)
        return root
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            return Path(local) / "cadgen"
    else:
        xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
        if xdg:
            return Path(xdg) / "cadgen"
    return Path.home() / ".cache" / "cadgen"


# --- the engine folder -----------------------------------------------------------------------------


def engine_dir() -> Path:
    """Where the engine's door and lock live: ``CADGEN_ENGINE_DIR``, else ``default_engine_dir``.
    Resolved once, here, for the client and the server alike (``os.path.realpath``): a ``..``, a
    symlink or a trailing slash in either spelling names the same door, lock and port file."""
    override = os.environ.get("CADGEN_ENGINE_DIR")
    return Path(os.path.realpath(override if override else default_engine_dir()))


def default_engine_dir() -> str:
    """The engine's folder when ``CADGEN_ENGINE_DIR`` names none, in a place no other user can make
    it first: ``$XDG_RUNTIME_DIR/cadgen-engine`` (Linux's per-session folder), else
    ``cadgen-engine`` in the user's temporary folder when it is this user's alone: on macOS the one
    the system names (``_darwin_temp``, ``/var/folders/...``), which a sandbox that sets its own
    ``TMPDIR`` does not move, so a client in it and the engine outside find one folder; ``TMPDIR``
    only where the system names none. Else ``/tmp/cadgen-<uid>``, which ``folder_refusal`` still
    checks. On Windows the temporary folder is the user's own: ``cadgen-engine`` in it."""
    if WINDOWS:
        return os.path.join(tempfile.gettempdir(), "cadgen-engine")
    for parent in (os.environ.get("XDG_RUNTIME_DIR"), _darwin_temp() or os.environ.get("TMPDIR")):
        if parent and os.path.isabs(parent) and _users_own(parent):
            return os.path.join(parent, "cadgen-engine")
    return f"/tmp/cadgen-{os.getuid()}"


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
                "set CADGEN_ENGINE_DIR to a folder of your own")
    if found.st_mode & 0o022:
        return (f"the engine's folder {folder} can be written by others (mode {stat.S_IMODE(found.st_mode):o}): "
                "run chmod go-w on it, or set CADGEN_ENGINE_DIR to a folder of your own")
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
    ``daemon.sweep_dead``), so a lock taken on a file whose name has gone, or names another file now,
    is no lock: it is let go and the file the name names now is taken instead (``names``)."""
    engine_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    refusal = folder_refusal(engine_dir())
    if refusal is not None:
        raise PermissionError(refusal)
    path = path or lock_path()
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


def home(prefix: str | None = None) -> dict[str, Any] | None:
    """The installation the environment at ``prefix`` (this process's, ``sys.prefix``) belongs to, as the
    marker the server wrote in it names it (``MARKER``) -- ``executable``, ``prefix``, ``root`` and the rest
    of what made it -- or None for an environment the server did not make."""
    try:
        marker = json.loads((Path(prefix or sys.prefix) / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    found = marker.get("installation") if isinstance(marker, dict) and marker.get("schema") == MARKER_SCHEMA else None
    if not isinstance(found, dict) or not all(isinstance(found.get(name), str) for name in ("executable", "prefix", "root")):
        return None
    return found


# The installation this process belongs to when it runs in the base that installation made (``home``):
# ``{"executable", "prefix", "root", ...}``; None in the installation's own environment. A process there --
# a model's script ``cadgen run`` runs, its worker -- goes by its installation's name (``registered``) and,
# with no current installation (``engine``), starts the engine with its installation's Python
# (``client._start``).
HOME: dict[str, Any] | None = home()


def installation_record(data: bytes | None) -> dict[str, Any] | None:
    """An installation's record (``installations/<version>.json``) as its bytes hold it, or None for one
    that is no record: ``version``, the absolute paths of its ``python`` and its console script
    (``cadgen``), its environment (``prefix``)."""
    try:
        record = json.loads(data) if data is not None else None
    except ValueError:
        return None
    if not isinstance(record, dict) or not all(isinstance(record.get(key), str)
                                               for key in ("version", "python", "cadgen", "prefix")):
        return None
    return record


def alive(record: dict[str, Any]) -> bool:
    """Whether the installation of ``record`` is there: its interpreter and its console script."""
    return os.path.isfile(record["python"]) and os.path.isfile(record["cadgen"])


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
    """The installation whose engine a client starts when none answers (``client._start``): the current
    one (``current``), read now -- its Python, its environment and its version; None with none current. A
    client of any release starts that one, never its own."""
    try:
        found = current()
    except (OSError, ValueError):
        return None
    return None if found is None else {"python": found["python"], "prefix": found["prefix"], "version": found["version"]}


def _home_prefix() -> str:
    """The environment of the installation this process belongs to (``HOME``), else its own."""
    return HOME["prefix"] if HOME else sys.prefix


def installation() -> str:
    """The version this installation runs as -- the one name its client, its daemon and its workers
    all go by (``status``, its bytecode): ``CADGEN_INSTALLATION_VERSION`` when it names one (the
    ``cadgen`` command sets it for a development install, which reports its release's version), else
    the version this environment is registered as (``registered``: a dev environment's
    ``python model.py`` run directly), else the release declared beside this code
    (``previous.version``)."""
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


def windowless() -> dict[str, Any]:
    """How the engine starts a process -- a worker, a reader, a render process -- on Windows: with
    a console of its own and no window (``CREATE_NO_WINDOW``); elsewhere as it is. A console program
    started with no console gets a new one, with a window (#597): a window per process, open as long
    as it lives, and closing one ends it."""
    return {"creationflags": CREATE_NO_WINDOW} if os.name == "nt" else {}


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
    cached under ``pycache/`` in the cache folder (``PYTHONPYCACHEPREFIX``), so a worker's start
    imports the kernel's pure-Python libraries from bytecode (a uvx installation compiles nothing
    on install: every start compiled them, seconds each) and nothing is written beside a library
    or a model. A ``PYTHONPYCACHEPREFIX`` already given is honoured. A caller's
    ``PYTHONDONTWRITEBYTECODE`` is not: the daemon and its workers serve every later client, and
    write their bytecode in a folder of their own, ``pycache/<installation>`` (``bytecode_tag``). With no
    cache folder this user alone can write -- one others can write to -- nothing is written:
    ``PYTHONDONTWRITEBYTECODE``. A model's own modules are compiled from their source whatever this
    says (``build._SourceOnlyLoader``)."""
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
    """This installation's folder under ``pycache/`` in the cache folder, made this user's alone and
    marked in use (its time); None where there is none to use."""
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


# The environment every process of the engine's that loads the kernel runs in -- a model's worker, the
# standby, the documents worker, the meshing and reading pools, the render processes -- as the server
# makes it (``cad_server._internal.base.kernel``: the installation's base): ``KERNEL(make)`` answers
# ``{"python", "path", "own"}``, or None when it is not made and ``make`` is false, and raises, saying
# why, when it cannot be made. None (no server in this process: a model's own process, a worker): this
# interpreter's own (``kernel``).
KERNEL: Callable[[bool], dict[str, Any] | None] | None = None


def kernel(make: bool = True) -> dict[str, Any] | None:
    """The environment the engine's kernel processes run in (``KERNEL``): ``{"python", "path", "own"}``
    -- ``own``: this interpreter's environment, whose engine folder a process started there is given and
    whose import path a spawned process is handed as it is -- or None when it is not made and ``make``
    is false. ``serve.KernelProcessesUnavailable`` when it cannot be made, saying why: no kernel process
    starts without it, and nothing remembers the failure."""
    if KERNEL is None:
        return {"python": sys.executable, "path": None, "own": True}
    try:
        return KERNEL(make)
    except Exception as error:  # noqa: BLE001 - the server's refusal, carried in one line
        from cad.engine.serve import KernelProcessesUnavailable

        raise KernelProcessesUnavailable(f"cadgen has no CAD kernel environment: {error}") from error
