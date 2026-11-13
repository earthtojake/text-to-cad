"""A version's data at its first start: what it cannot make again, copied in from the version it replaces.

A version keeps everything it reads and writes in ``versions/<version>/data`` (``places.data_dir``). The first
time a process of it needs that folder and finds it not imported (no ``MARKER``), it imports (``ensure``):
what cannot be made again, copied from a source and never changed there, the source only read --

- ``settings.json``: every setting, the telemetry answer and the install's id among them;
- ``documents/<id>/document.json``: each document's record (the rest of a record's folder is the cache's);
- ``recents/``: what the homes show of the records, their pictures;
- ``engines/token``: the page token, so every link shared before still opens (only a token the server would
  serve with, ``registry.Registry.token``; this user's alone, 0600);
- ``engines/engine.json``: the port the server rolled to, rewritten in this version's schema with the port alone
  (``registry.Registry.put_engine``), 0600;
- each imported record's document bytes, ``cache/documents/<id>/document.xbf`` (``records.FILE``): a shape a
  program handed over has no other source, and a model's would wait on a build no one asked for (the viewer never
  builds one by itself), so Recents opens every entry after an update. A hard link where both are on one volume,
  else a copy (``_bytes``);
- ``telemetry-batches.jsonl``: the batches exiting processes kept, each line a whole batch as it is sent (its
  schema, release, channel, install id, and events with ids, which the receiver takes once however often sent),
  so the new version sends what the old one had not.

Not imported: the other caches (a document's kept checks and derived views, hulls, MJCF assets, homes), the
telemetry spool (``telemetry-spool.jsonl``: each row is the answer, a time and bare counts, which a sender merges
into its own batch under its own release and channel; a row does not say the release, channel or process it was
counted in, so another version would send it as its own), the version feed's cache (``versions.json``), the install channels (``install-channels.json``), the updater's
records (``update-automatic.json``, ``update.json``, ``update.log``), the lock (``settings.lock``) and the
source's own ``MARKER``. Every format but the engine record's is this release's own already, so nothing else
is converted; the server's own migrations at its start (``identity.migrate``) run on the copy as on any data.

**The source** (``source``): what the channel leaves (``versions.move`` names it) -- a version, where it is
older and its data is imported; the layout before 0.12, for the default channel's first move on a device with it
--; for a channel's first use, or a start that names none, the highest older version present whose data is;
failing that the layout before 0.12 (``cad_server._internal.legacy``), which ranks below every
version; failing that nothing, and the data starts empty. Never a newer version.

**How**, under the version's import lock (``versions/<version>/import.lock``): any ``data.importing-*`` a crash
left removed; the items copied into a new ``data.importing-*`` beside ``data``; that folder renamed to
``data``, or, where ``data`` is there already without its marker (a command of the version wrote a file
first), each copied file moved in where ``data`` has none; then the marker written last. A crash anywhere
before the marker leaves no marker, and the next start does it again. An item that cannot be read is skipped and
said in one line; the import never stops a start: the server's start (``cad_server.engine.daemon``) and a
channel's move (``versions.move``) both call ``ensure``, the first before it serves anything.

The marker, ``data/format.json``: ``{"schema", "version", "imported": {"kind": "version"|"legacy", "version"} or
None, "at", "skipped"}``. The layout before 0.12 is removed only once the default channel's version has it
(``legacy.unsafe``).
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from cad.engine import places

__all__ = ["MARKER", "SCHEMA", "Imported", "Source", "ensure", "imported", "marker", "source"]

MARKER = "format.json"
SCHEMA = "cad data/1"
LOCK = "import.lock"
STAGING = "data.importing-"
SETTINGS, DOCUMENTS, RECENTS, TOKEN, PORT = ("settings.json", "documents", "recents", "engines/token",
                                             "engines/engine.json")
# The batches exiting processes kept for sending (``analytics.KEPT``): each line a whole batch, as it is sent.
BATCHES = "telemetry-batches.jsonl"
CACHE = "cache"


@dataclass(frozen=True)
class Source:
    """What a version imports from: an older version's data (``kind`` ``version``), or the layout before 0.12
    (``legacy``, its ``version`` the one its ``current`` named, if any), at ``root``, its document cache at
    ``cache`` (a version's ``data/cache``, the layout's cache folder before 0.12)."""

    kind: str
    version: str | None
    root: Path
    cache: Path

    def words(self) -> str:
        if self.kind == "legacy":
            return "the data of releases before 0.12"
        return f"text-to-cad {self.version}'s data"


@dataclass
class Imported:
    """A version's data as ``ensure`` left it: ``source`` copied from now (None: nothing was, or it was
    imported before -- ``done`` False), and the lines said of what was skipped."""

    version: str
    done: bool
    source: Source | None = None
    said: list[str] = field(default_factory=list)


def _data(name: str) -> Path:
    return places.data_dir(name)


def marker(name: str) -> dict[str, Any] | None:
    """Version ``name``'s data marker, when its data is imported; else None."""
    try:
        found = json.loads((_data(name) / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) and found.get("schema") == SCHEMA else None


def imported(name: str) -> bool:
    """Whether version ``name``'s data is imported (its marker is there)."""
    return marker(name) is not None


def source(name: str, leaving: str | None = None, *, legacy_left: bool = False) -> Source | None:
    """Where version ``name`` imports from (see the module): what its channel leaves -- ``leaving``, a version,
    when it is older and imported; the layout before 0.12 when ``legacy_left`` (the default channel's first move
    on a device with it) and it holds anything to import --; else the highest older version present whose data
    is imported; else the layout before 0.12 where it holds anything to import; else None."""
    from cad_server._internal import installations, legacy, versions

    def older(other: str) -> bool:
        return versions.older(other, name)

    if leaving is not None and leaving != name and older(leaving) and imported(leaving):
        return Source("version", leaving, _data(leaving), places.cache_dir(leaving))
    if legacy_left and legacy.importable():
        return Source("legacy", installations.current_version(), legacy.root(), legacy.cache_root())
    candidates = [other for other in versions.present() if other != name and older(other) and imported(other)]
    if candidates:
        best = max(candidates, key=versions.order)
        return Source("version", best, _data(best), places.cache_dir(best))
    if legacy.importable():
        return Source("legacy", installations.current_version(), legacy.root(), legacy.cache_root())
    return None


def ensure(name: str, leaving: str | None = None, *, legacy_left: bool = False,
           told: Callable[[str], None] | None = None) -> Imported:
    """Version ``name``'s data imported, if it is not (see the module): from ``source(name, leaving,
    legacy_left=...)``, each item that cannot be read skipped and said to ``told``. What was done; nothing when it
    was imported already."""
    from cad_server._internal.file_lock import exclusive

    say = told or (lambda _line: None)
    folder = places.version_dir(name)
    if imported(name):
        return Imported(name, False)
    folder.mkdir(parents=True, exist_ok=True)
    with exclusive(folder / LOCK):
        if imported(name):
            return Imported(name, False)  # imported meanwhile, by the process this one waited for
        for stale in _names(folder):
            if stale.startswith(STAGING):
                shutil.rmtree(folder / stale, ignore_errors=True)
        found = source(name, leaving, legacy_left=legacy_left)
        said: list[str] = []
        staging = folder / f"{STAGING}{os.getpid()}-{os.urandom(4).hex()}"
        staging.mkdir()
        if found is not None:
            _copy(found, staging, said)
        data = _data(name)
        if os.path.lexists(data):
            _merge(staging, data)
            shutil.rmtree(staging, ignore_errors=True)
        else:
            os.rename(staging, data)
        record = {"schema": SCHEMA, "version": name, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "skipped": said,
                  "imported": None if found is None else {"kind": found.kind, "version": found.version}}
        from cad._internal.atomic_replace import write_bytes_atomic

        write_bytes_atomic(data / MARKER, (json.dumps(record, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    for line in said:
        say(line)
    return Imported(name, True, found, said)


def _names(folder: Path) -> list[str]:
    try:
        return sorted(os.listdir(folder))
    except OSError:
        return []


def _copy(found: Source, staging: Path, said: list[str]) -> None:
    """What ``found`` holds that a version imports, copied into ``staging``; each item it cannot read said in
    ``said`` and skipped."""
    from cad.engine.ids import is_id
    from cad.engine.records import FILE, RECORD
    from cad_server.engine.registry import ENGINE_SCHEMA, Registry
    from cad_server.engine.registry import Folder

    root = found.root
    _file(root / SETTINGS, staging / SETTINGS, said)
    _file(root / BATCHES, staging / BATCHES, said)
    for ident in _names(root / DOCUMENTS):
        if is_id(ident) and os.path.isfile(root / DOCUMENTS / ident / RECORD):
            if _file(root / DOCUMENTS / ident / RECORD, staging / DOCUMENTS / ident / RECORD, said):
                _bytes(found.cache / DOCUMENTS / ident / FILE, staging / CACHE / DOCUMENTS / ident / FILE, said)
    recents = root / RECENTS
    for folder, _dirs, files in os.walk(recents):
        for name in sorted(files):
            path = Path(folder) / name
            if not path.is_symlink():
                _file(path, staging / path.relative_to(root), said)
    source_registry, copy = Registry(root), Registry(Folder(staging))
    if os.path.lexists(root / TOKEN):
        try:
            token = source_registry.token()
        except ValueError as error:
            said.append(f"the page token was not imported: {error}")
            token = None
        if token is not None:
            copy.make_token(token)
    if os.path.lexists(root / PORT):
        port = source_registry.engine(places.NAME).get("port")
        if port is not None:
            copy.put_engine(places.NAME, {"port": port, "schema": ENGINE_SCHEMA})


def _file(path: Path, target: Path, said: list[str]) -> bool:
    """The file at ``path`` copied to ``target``, its mode and times kept: whether it was. One that cannot be read
    said in ``said``."""
    try:
        data = path.read_bytes()
        found = os.stat(path)
    except FileNotFoundError:
        return False
    except OSError as error:
        said.append(f"{path} was not imported: {error.strerror or error}")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), found.st_mode & 0o777)
    with os.fdopen(handle, "wb") as out:
        out.write(data)
    os.utime(target, ns=(found.st_atime_ns, found.st_mtime_ns))
    return True


def _bytes(path: Path, target: Path, said: list[str]) -> None:
    """A document's cached bytes at ``path`` given to the new version at ``target``: a hard link where the two
    are on one volume -- safe, as every writer of the document cache writes a new file and renames it over, never
    a file in place (``registry.Folder``, ``atomic_replace.put``), so neither version ever changes the other's
    bytes --, else a copy. One that cannot be read said in ``said``; the record stays, its document unsaved."""
    import shutil

    if not path.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(path, target)
        return
    except OSError:
        pass
    try:
        shutil.copy2(path, target)
    except OSError as error:
        said.append(f"{path} was not imported: {error.strerror or error}")
        with contextlib.suppress(OSError):
            target.unlink()


def _merge(staging: Path, data: Path) -> None:
    """Each file copied into ``staging`` moved into ``data`` where ``data`` has none: what a command of the
    version wrote there first is newer than the copy."""
    from cad._internal.atomic_replace import replace_atomic

    for folder, _dirs, files in os.walk(staging):
        for name in files:
            path = Path(folder) / name
            target = data / path.relative_to(staging)
            if os.path.lexists(target):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            replace_atomic(path, target)
