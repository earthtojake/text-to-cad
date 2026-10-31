"""The plugin folder: text-to-cad's agent-app plugin as this installation of the server carries it,
written where every agent app on the device is pointed at it.

``<state>/plugin`` (``folder``) is the repository root's plugin layout, as the ``latest`` branch
carries it but its README: the catalog (``.claude-plugin/marketplace.json``, listing the plugin at
``./``), each host's manifest (``.claude-plugin``, ``.codex-plugin``, ``.cursor-plugin``,
``gemini-extension.json``, and the Agent Plugins standard's ``plugin.json`` and ``mcp.json``), the
server configs they name, the icons, the licence, and ``skills/`` -- written from the server's own copy
of them (``source``: ``_runtime/plugin`` in its wheel, which ``scripts/bundle`` builds; a checkout's
root in a source tree). Three things change on the way (``tree``): every version is this
distribution's, the catalog is a local one of its own (``MARKETPLACE``), and each host's CAD server
is the line the installer gives that host: ``uvx ... --from texttocad-mcp==<version> cad-mcp``, told
the install channel it always was (``CHANNELS``). There is no root ``.mcp.json``: Claude Code reads
one in place of the server config its manifest names.

It is a stable path, regenerated in place (``write``): a file that differs is written to a hidden
temporary file beside it and renamed over it, a file the plugin no longer holds is removed, and
nothing else is touched -- never a symlink, never the folder replaced whole. Claude Code (a
local-directory marketplace) and Gemini CLI (a linked extension) read the folder where it is, so a
regenerated folder is what their next session reads; Codex and Cursor keep copies of it, which the
installer refreshes, and Codex drops a symlink without a word.

The folder follows the release that is current. It is written at a registration of the current
installation (``installations.setup``), by ``cad setup`` before the apps are pointed at it, and after
every switch of the device's engine, by the release then current (``cad plugin``, run by
``cad_server._internal.switch``); ``cad plugin`` prints its path.

Nothing here imports the packages at module scope, so a test reads this file by its path: what it
borrows -- the one atomic rename, the state folder, the lock, this release's version and its bundled
copy of the plugin -- it imports when it is asked for it.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

NAME = "text-to-cad"
FOLDER = "plugin"
# The catalog the folder is, as Claude Code and Codex name it: a local one of its own, apart from the
# repository's catalog on GitHub (``earthtojake``) and a checkout's development install's.
MARKETPLACE = "texttocad"
PLUGIN_ID = f"{NAME}@{MARKETPLACE}"
SKILLS = "skills"
CATALOG = ".claude-plugin/marketplace.json"
MANIFEST = ".claude-plugin/plugin.json"
# The plugin's files beside its skills: the repository root's plugin layout (scripts/release/plugin_branch.py's
# `latest`, less its README), which scripts/bundle/cadgen-runtime.sh copies into the wheel. A test holds the
# three lists equal.
FILES = (
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".claude-plugin/icon.png",
    ".codex-plugin/plugin.json",
    ".codex-plugin/logo.png",
    ".cursor-plugin/plugin.json",
    "gemini-extension.json",
    "plugin.json",
    "mcp.json",
    "claude.mcp.json",
    "codex.mcp.json",
    "cursor.mcp.json",
    "LICENSE",
)
# The manifests that carry the plugin's version.
MANIFESTS = (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json",
             "gemini-extension.json", "plugin.json")
# Each file that starts CAD's server, and the install channel the server is told there
# (``cad_server._internal.channel``): the ones the installer gave each host before the folder, the
# `latest` branch's. None is auto-updated: an update is the person's.
CHANNELS = {
    "claude.mcp.json": "claude-github",
    "codex.mcp.json": "codex-github",
    "cursor.mcp.json": "cursor-github",
    "gemini-extension.json": "gemini-github",
    "mcp.json": "agent-plugins",
}
CHANNEL_ENV = "CAD_INSTALL_CHANNEL"
AUTO_UPDATED_ENV = "CAD_AUTO_UPDATED"
# The CAD app's transport, as the plugin's server configs run it (``cad_server._internal.launch``).
SHIM, SHIM_COMMAND = "texttocad-mcp", "cad-mcp"
# The lock two writers of the folder take, beside it.
LOCK = "plugin.lock"
# What a checkout's skills folder may hold that the plugin never carries: a wheel's package data
# takes no hidden file either.
_IGNORED_DIRS = ("__pycache__",)
_IGNORED_SUFFIXES = (".pyc", ".pyo")


class Missing(Exception):
    """The server's copy of the plugin is not there: a source tree never bundled, or a broken install."""


# --- where things are -------------------------------------------------------------------------------


def folder(state: Optional[Path] = None) -> Path:
    """``<state>/plugin``: the state folder's (``cad.engine.places.state_dir``), or ``state``'s."""
    if state is None:
        from cad.engine.places import state_dir

        state = Path(state_dir())
    return Path(state) / FOLDER


def release() -> str:
    """This distribution's version (``cad_server.__version__``): the plugin's, whatever name a
    development install registers under."""
    from cad_server import __version__

    return __version__


def source() -> Path:
    """The server's own copy of the plugin: a checkout's root when the server is imported from the
    checkout that builds it (as ``cad_server.assets`` serves a checkout's built viewer), else
    ``_runtime/plugin`` in its wheel. ``Missing`` when neither holds it."""
    from cad_server import assets

    root = assets.checkout_root()
    if root is not None and (root / MANIFEST).is_file() and (root / SKILLS).is_dir():
        return root
    built = assets.runtime_root() / FOLDER
    if (built / MANIFEST).is_file():
        return built
    raise Missing(f"text-to-cad's plugin is not in this installation. {assets.runtime_build_hint(built)}")


# --- what the folder holds ---------------------------------------------------------------------------


def _skill_files(root: Path) -> Iterator[Tuple[str, Path]]:
    """Every file of ``root/skills``, as ``(skills/<path>, path)``, sorted: no hidden file or folder, no
    bytecode. A symlink is read through: the folder holds real files."""
    base = root / SKILLS
    if not base.is_dir():
        raise Missing(f"{base} is missing: the plugin has no skills")
    for directory, folders, files in os.walk(base):
        folders[:] = sorted(name for name in folders if not name.startswith(".") and name not in _IGNORED_DIRS)
        for name in sorted(files):
            if name.startswith(".") or name.endswith(_IGNORED_SUFFIXES):
                continue
            path = Path(directory) / name
            yield (Path(SKILLS) / path.relative_to(base)).as_posix(), path


def _mode(path: Path) -> int:
    """0o755 for a file someone may run, else 0o644."""
    return 0o755 if os.stat(path).st_mode & 0o111 else 0o644


def _server(entry: Any, version: str, channel: str, where: str) -> Dict[str, Any]:
    """A server entry that runs the CAD app's transport, its pin this ``version``'s and its install channel
    ``channel``; ``ValueError`` for one that is not."""
    arguments = entry.get("args") if isinstance(entry, dict) else None
    pins = [index for index, word in enumerate(arguments or []) if isinstance(word, str) and word.startswith(f"{SHIM}==")]
    if not pins or arguments[-1:] != [SHIM_COMMAND]:
        raise ValueError(f"{where}: its server does not run {SHIM}'s {SHIM_COMMAND}")
    arguments = list(arguments)
    arguments[pins[0]] = f"{SHIM}=={version}"
    environment = {key: value for key, value in (entry.get("env") or {}).items() if key != AUTO_UPDATED_ENV}
    environment[CHANNEL_ENV] = channel
    return {**entry, "args": arguments, "env": environment}


def _transform(relative: str, data: bytes, version: str) -> bytes:
    """A plugin file as the folder holds it: its version this one, the catalog a local one listing the
    plugin at ``./``, and each CAD server this version's, told its channel. Other files as they are."""
    if relative not in MANIFESTS and relative not in CHANNELS and relative != CATALOG:
        return data
    try:
        document = json.loads(data.decode("utf-8"))
    except ValueError as error:
        raise ValueError(f"{relative} is not JSON: {error}") from error
    if relative in MANIFESTS:
        document["version"] = version
    if relative == CATALOG:
        document["name"] = MARKETPLACE
        document["version"] = version
        for entry in document.get("plugins") or []:
            if isinstance(entry, dict) and entry.get("name") == NAME:
                entry.update({"version": version, "source": "./"})
    if relative in CHANNELS:
        servers = document.get("mcpServers")
        if not isinstance(servers, dict) or not servers:
            raise ValueError(f"{relative} names no server")
        document["mcpServers"] = {key: _server(entry, version, CHANNELS[relative], relative)
                                  for key, entry in servers.items()}
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def tree(origin: Path, version: str) -> Dict[str, Tuple[bytes, int]]:
    """The folder's files from the plugin at ``origin``, ``{path: (bytes, mode)}``: ``FILES`` as the
    folder holds them (``_transform``), and every skill file as it is."""
    origin = Path(origin)
    files: Dict[str, Tuple[bytes, int]] = {}
    for relative in FILES:
        path = origin / relative
        try:
            data = path.read_bytes()
        except OSError as error:
            raise Missing(f"{path} cannot be read ({type(error).__name__})") from error
        files[relative] = (_transform(relative, data, version), 0o644)
    for relative, path in _skill_files(origin):
        files[relative] = (path.read_bytes(), _mode(path))
    return files


# --- writing it --------------------------------------------------------------------------------------


def _holds(path: Path, data: bytes, mode: int) -> bool:
    """Whether ``path`` is a real file holding ``data`` with ``mode`` (the mode where it has one)."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size != len(data):
            return False
        if os.name != "nt" and path.stat().st_mode & 0o777 != mode:
            return False
        return path.read_bytes() == data
    except OSError:
        return False


def _replace(temporary: Path, path: Path) -> None:
    """The one atomic rename (``cad._internal.atomic_replace``), which waits out a Windows reader's
    handle; the plain one when this file is read by its path, without the library."""
    try:
        from cad._internal.atomic_replace import replace_atomic
    except ImportError:
        replace_atomic = os.replace
    replace_atomic(temporary, path)


def _clear(target: Path, relative: str) -> None:
    """Make room for the file ``relative``: whatever stands at one of its folders' places that is not a
    folder (a file, a symlink), or at its own place that is a folder or a symlink, goes."""
    import shutil

    place = target
    parts = relative.split("/")
    for part in parts[:-1]:
        place = place / part
        if place.is_symlink() or (place.exists() and not place.is_dir()):
            place.unlink()
    path = target / relative
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _put(target: Path, relative: str, data: bytes, mode: int) -> None:
    """``data`` written to ``target/relative`` whole: a hidden temporary file beside it, its mode set,
    renamed over it."""
    _clear(target, relative)
    path = target / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        with open(temporary, "wb") as out:
            out.write(data)
        os.chmod(temporary, mode)
        _replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass


def _stale(target: Path, wanted: Dict[str, Tuple[bytes, int]]) -> List[Path]:
    """What in ``target`` the plugin does not hold, deepest first: every file and symlink not in
    ``wanted`` (a temporary file a write left included); folders are emptied, not listed."""
    found = []
    for directory, folders, files in os.walk(target):
        for name in folders + files:
            path = Path(directory) / name
            relative = path.relative_to(target).as_posix()
            if path.is_symlink() or (path.is_file() and relative not in wanted):
                found.append(path)
    return sorted(found, key=lambda path: len(path.parts), reverse=True)


def _sync(target: Path, wanted: Dict[str, Tuple[bytes, int]], version: str) -> Dict[str, Any]:
    created = not target.is_dir() or target.is_symlink()
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        target.unlink()  # the folder is a real one
    target.mkdir(parents=True, exist_ok=True)
    removed = []
    for path in _stale(target, wanted):  # a symlink first: nothing is written through one
        path.unlink()
        removed.append(path.relative_to(target).as_posix())
    changed = []
    for relative, (data, mode) in sorted(wanted.items()):
        if not _holds(target / relative, data, mode):
            _put(target, relative, data, mode)
            changed.append(relative)
    for directory, _folders, _files in sorted(os.walk(target, topdown=False), key=lambda entry: -len(entry[0])):
        place = Path(directory)
        if place != target and not any(place.iterdir()):
            place.rmdir()
    return {"path": str(target), "version": version, "created": created, "changed": changed,
            "removed": sorted(removed)}


def _locked(target: Path):
    """The folder's lock (``LOCK`` beside it), held while it is written: the state folder's lock helper
    (``cad_server._internal.file_lock``), or none when this file is read by its path."""
    import contextlib

    try:
        from cad_server._internal.file_lock import exclusive
    except ImportError:
        return contextlib.nullcontext()
    target.parent.mkdir(parents=True, exist_ok=True)
    return exclusive(target.parent / LOCK)


def write(target: Optional[Path] = None, *, origin: Optional[Path] = None,
          version: Optional[str] = None) -> Dict[str, Any]:
    """The folder written from the plugin at ``origin`` (``source()``) as ``version`` (``release()``),
    into ``target`` (``folder()``), in place (see the module): what was done, ``{path, version, created,
    changed, removed}``, ``changed`` and ``removed`` the relative paths written and taken out.
    ``Missing`` when the plugin is not there to write from, ``OSError`` when the folder cannot be
    written."""
    target = Path(target) if target is not None else folder()
    wanted = tree(Path(origin) if origin is not None else source(), version or release())
    with _locked(target):
        return _sync(target, wanted, version or release())


def pending(target: Optional[Path] = None, *, origin: Optional[Path] = None,
            version: Optional[str] = None) -> Dict[str, Any]:
    """What ``write`` would do, done nothing: ``{path, version, created, changed, removed}``."""
    target = Path(target) if target is not None else folder()
    version = version or release()
    wanted = tree(Path(origin) if origin is not None else source(), version)
    if not target.is_dir() or target.is_symlink():
        return {"path": str(target), "version": version, "created": True, "changed": sorted(wanted), "removed": []}
    removed = [path.relative_to(target).as_posix() for path in _stale(target, wanted)]
    changed = [relative for relative, (data, mode) in sorted(wanted.items())
               if not _holds(target / relative, data, mode)]
    return {"path": str(target), "version": version, "created": False, "changed": changed, "removed": sorted(removed)}


def written(target: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """The folder as it is: ``{path, version, at}`` (its manifest's version, and when that was last
    written), or None when it holds no plugin."""
    target = Path(target) if target is not None else folder()
    manifest = target / MANIFEST
    try:
        version = json.loads(manifest.read_text(encoding="utf-8")).get("version")
        at = manifest.stat().st_mtime
    except (OSError, ValueError, AttributeError):
        return None
    return {"path": str(target), "version": version if isinstance(version, str) else None,
            "at": time.strftime("%Y-%m-%d %H:%M", time.localtime(at))}


def remove(target: Optional[Path] = None) -> bool:
    """The folder taken out, with its lock: whether there was one."""
    import shutil

    target = Path(target) if target is not None else folder()
    if target.is_symlink() or target.is_file():
        target.unlink()
        return True
    there = target.exists()
    shutil.rmtree(target, ignore_errors=True)
    try:
        (target.parent / LOCK).unlink()
    except OSError:
        pass
    return there


def say_written(done: Dict[str, Any], say: Callable[[str], None], shown: Callable[[str], str] = str) -> None:
    """One line for what ``write`` did."""
    count = len(done["changed"]) + len(done["removed"])
    if done["created"]:
        say(f"wrote {shown(done['path'])}: text-to-cad {done['version']}")
    elif count:
        say(f"{shown(done['path'])}: text-to-cad {done['version']}, {count} file{'s' if count != 1 else ''} changed")
    else:
        say(f"{shown(done['path'])}: text-to-cad {done['version']}, up to date")
