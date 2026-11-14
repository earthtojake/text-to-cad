"""A version's data at its first start, copied in from the version it replaces; and what that version, or the
layout of 0.11.10 and earlier, writes afterwards, carried over before it is removed.

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
  else a copy (``_bytes``).

Not imported: the other caches (a document's kept checks and derived views, hulls, MJCF assets, homes); what was
kept for sending and not sent -- the telemetry spool (``telemetry-spool.jsonl``) and the batches exiting processes
kept (``telemetry-batches.jsonl``) --, which has one owner at a time: the version it replaces may still be running
and sending it, and it moves once, whole, to the version that sends next as that version's folder is removed
(``versions._hand_on``; the layout's kept batches as it is removed, ``legacy.remove``), never copied; the version
feed's cache (``versions.json``), the updater's
records (``update-automatic.json``, ``update.json``, ``update.log``), the lock (``settings.lock``) and the
source's own ``MARKER``. A telemetry no the device keeps is taken into the copy (``analytics.inherit_no``). Every
format but the engine record's is this release's own already, so nothing else
is converted; the server's own migrations at its start (``identity.migrate``) run on the copy as on any data.

**The source** (``source``), never a newer version: what the channel leaves (``versions.move`` names it) -- a
version, where it is older and its data is imported; the layout of 0.11.10 and earlier, for the default channel's
first move on a device with it --; else the highest older version a pointer has named whose data is there (its code
there or not: ``cad uninstall`` keeps the data alone); else the layout
of 0.11.10 and earlier while it still has what it imports (``legacy.importable``: its records, Recents, release
folders); else, once that layout's bulk is removed, the settings it keeps (``legacy.SETTINGS``: a client of 0.11.10
or earlier reads them, and they carry the device's telemetry no) and nothing else; else nothing, and the data
starts empty.

**How**, under the version's import lock (``versions/<version>/import.lock``): any ``data.importing-*`` a crash
left removed; the items copied into a new ``data.importing-*`` beside ``data``; that folder renamed to
``data``, or, where ``data`` is there already without its marker -- a process of the version wrote there before its
first start was marked, which never happens by design (``pins.first_use``) but does where an import failed and the
server started on what data there was -- each copied file moved in where ``data`` has none, and over what is there
for the settings, the page token and the port record (``WINS``: the copy is the person's, what was written first a
fresh default); then the marker written last. A crash anywhere before the marker leaves no marker, and the next
start does it again. Each item that cannot be read is skipped and said in one line; the import never stops a
start: the server's start (``cad_server.engine.daemon``) and a channel's move (``versions.move``) both call
``ensure``, the first before it serves anything.

The marker, ``data/format.json``: ``{"schema", "version", "imported": {"kind": "version"|"legacy", "version"} or
None, "at", "skipped"}``. It also says the version has been a channel's: only such a version is ever removed
by itself (``versions.sweep``). The layout of 0.11.10 and earlier is removed only once the default channel's version
has it (``legacy.unsafe``).

**The carry-over** (``carry``): what the source holds that the target lacks, added to the target and nothing of
the target's changed, so the import is not the last word on a version that goes on being written: the version a
channel leaves keeps serving its work in flight after the new one imported, and the layout of 0.11.10 and earlier
can stay the default's for hours while another channel moved first. It runs in ``versions.move`` whenever the
channel leaves something with data (the target has data already or not), and again immediately before any
removal of a version that has been a channel's or of the layout, when nothing runs from it any more, into the
version its channel moved to (``versions.successor``; for the layout, the default channel's). Never from a newer
version into an older one. Additive and idempotent -- run twice, the second adds nothing -- and safe to cut
anywhere: each item is added whole (a file made where none is, ``registry.Folder.create``) or not at all, so the
next run adds the rest. What "the target lacks" means, per item:

- a document record, by its id: added with its document's bytes and its Recents pictures where the target has no
  record of that id and never had one from this source (``LEDGER``: an id the target took from this source once
  and has not now was deleted there, and stays deleted). Where the target has the record, the target's stays as
  it is but for its Recents use: the later ``opened`` of the two wins, so an entry opened in the old version
  after the import sorts as recently in the new;
- a setting, by its key: a section the target's settings lack, and a key a section of the target's lacks, where the
  target never had it from a source (``LEDGER`` again: a section or key the person removed since stays removed, as
  ``cad language`` back to the browser's removes its section); never the telemetry section's own keys, whose answer
  is the person's in each version, and whose no is said in every version at once (``analytics.everywhere``,
  ``inherit_no``).

The ledger goes with an import: a version imported from another takes that version's ledger into its own, so a
record the source took from the layout of 0.11.10 and earlier and then deleted stays deleted when the layout is
carried into the copy. A ledger that is there and cannot be read stops the carry-over whole: nothing carried, the
source not removed, said (``cad doctor`` says why its folder stays).

Lost all the same: a record the old version changed after the import whose id the target has (its record stays
as the target holds it), and a setting the old version changed whose key the target has.
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

__all__ = ["LEDGER", "MARKER", "SCHEMA", "Carried", "Imported", "Source", "carry", "ensure", "imported", "marker",
           "source"]

MARKER = "format.json"
SCHEMA = "cad data/1"
LOCK = "import.lock"
STAGING = "data.importing-"
SETTINGS, DOCUMENTS, RECENTS, TOKEN, PORT = ("settings.json", "documents", "recents", "engines/token",
                                             "engines/engine.json")
CACHE = "cache"
# What an import or a carry-over took from each source (``carry``): ``{"schema", "from": {"<source>": {"documents":
# [ids], "settings": [[section], [section, key]]}}}``, so what the target deleted since is never added again.
LEDGER = "carried.json"
LEDGER_SCHEMA = "cad carried/1"
# What a version wrote before its first start was marked loses to the copy (``_merge``).
WINS = frozenset({"settings.json", "engines/token", "engines/engine.json", LEDGER})


@dataclass(frozen=True)
class Source:
    """What a version imports from: an older version's data (``kind`` ``version``), or the layout of 0.11.10 and earlier
    (``legacy``, its ``version`` the one its ``current`` named, if any), at ``root``, its document cache at
    ``cache`` (a version's ``data/cache``, the layout's cache folder of 0.11.10 and earlier); ``settings_only``: the
    layout's kept settings alone, its bulk removed."""

    kind: str
    version: str | None
    root: Path
    cache: Path
    settings_only: bool = False

    def words(self) -> str:
        if self.kind == "legacy":
            return "the settings of 0.11.10 and earlier" if self.settings_only else "the data of 0.11.10 and earlier"
        return f"text-to-cad {self.version}'s data"

    @property
    def key(self) -> str:
        """Its name in a target's ``LEDGER``."""
        return "legacy" if self.kind == "legacy" else f"version {self.version}"


def of_version(name: str) -> Source:
    """Version ``name``'s data as a source."""
    return Source("version", name, _data(name), places.cache_dir(name))


def of_legacy() -> Source:
    """The layout of 0.11.10 and earlier as a source: whole while it has what a version imports
    (``legacy.importable``), its kept settings alone once its bulk is removed."""
    from cad_server._internal import installations, legacy

    return Source("legacy", installations.current_version(), legacy.root(), legacy.cache_root(),
                  settings_only=not legacy.importable())


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
    when it is older and imported; the layout of 0.11.10 and earlier when ``legacy_left`` (the default channel's first
    move on a device with it) and it holds anything to import --; else the highest older version present whose data
    is imported; else the layout of 0.11.10 and earlier while it holds what a version imports; else its kept
    settings alone; else None."""
    from cad_server._internal import legacy, versions

    def older(other: str) -> bool:
        return versions.older(other, name)

    if leaving is not None and leaving != name and older(leaving) and imported(leaving):
        return of_version(leaving)
    if legacy_left and legacy.importable():
        return of_legacy()
    # A version a pointer has named (``versions.used``), its code there or not (``cad uninstall`` keeps the data
    # alone): one never named holds a copy of another's data at best.
    candidates = [other for other in versions.folders() if other != name and older(other) and imported(other)
                  and versions.used(other)]
    if candidates:
        return of_version(max(candidates, key=versions.order))
    if legacy.importable() or os.path.isfile(legacy.root() / SETTINGS):
        return of_legacy()
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
        # A no the device keeps (``analytics.everywhere``), newer than the answer imported or with none imported, is
        # this version's too: a version made present after a no sends nothing, whatever it imported from.
        from cad_server import analytics

        analytics.inherit_no(data / SETTINGS)
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
    """What ``found`` holds that a version imports, copied into ``staging``, with what was taken of it in the
    copy's ``LEDGER``; each item it cannot read said in ``said`` and skipped, the rest copied."""
    from cad.engine.ids import is_id
    from cad.engine.records import FILE, RECORD
    from cad_server.engine.registry import ENGINE_SCHEMA, Folder, Registry

    root = found.root
    _item(lambda: _file(root / SETTINGS, staging / SETTINGS, said), root / SETTINGS, said)
    taken: dict[str, list[Any]] = {"documents": [], "settings": _setting_keys(staging / SETTINGS)}
    if found.settings_only:
        _item(lambda: _write_ledger(staging, {found.key: taken}), staging / LEDGER, said)
        return
    for ident in _listed(root / DOCUMENTS, said):
        if is_id(ident) and os.path.isfile(root / DOCUMENTS / ident / RECORD):
            record = root / DOCUMENTS / ident / RECORD
            if _item(lambda: _file(record, staging / DOCUMENTS / ident / RECORD, said), record, said):
                taken["documents"].append(ident)
                _item(lambda: _bytes(found.cache / DOCUMENTS / ident / FILE,
                                     staging / CACHE / DOCUMENTS / ident / FILE, said), found.cache, said)

    def recents() -> None:
        for folder, _dirs, files in os.walk(root / RECENTS):
            for name in sorted(files):
                path = Path(folder) / name
                if not path.is_symlink():
                    _item(lambda: _file(path, staging / path.relative_to(root), said), path, said)

    _item(recents, root / RECENTS, said)
    source_registry, copy = Registry(root), Registry(Folder(staging))

    def token() -> None:
        if os.path.lexists(root / TOKEN):
            try:
                found_token = source_registry.token()
            except ValueError as error:
                said.append(f"the page token was not imported: {error}")
                return
            if found_token is not None:
                copy.make_token(found_token)

    def port() -> None:
        if os.path.lexists(root / PORT):
            found_port = source_registry.engine(places.NAME).get("port")
            if found_port is not None:
                copy.put_engine(places.NAME, {"port": found_port, "schema": ENGINE_SCHEMA})

    _item(token, root / TOKEN, said)
    _item(port, root / PORT, said)

    def ledger() -> None:
        # What the source took from its own sources and has not now was deleted there: the copy knows it too, so a
        # later carry-over from those sources does not add it again.
        earlier: dict[str, dict[str, list[str]]] = {}
        if found.kind == "version":
            try:
                earlier = _read_ledger(root)
            except OSError as error:
                said.append(f"{root / LEDGER} was not imported: {error.strerror or error}")
        _write_ledger(staging, {**earlier, found.key: taken})

    _item(ledger, staging / LEDGER, said)


def _setting_keys(path: Path) -> list[list[str]]:
    """Every section of the settings at ``path``, and every key of each, as a ledger lists them (``LEDGER``): none
    where there are none or they cannot be read."""
    from cad_server.settings import _load

    try:
        held = _load(path)
    except OSError:
        return []
    found: list[list[str]] = []
    for section, value in sorted(held.items()):
        found.append([section])
        if isinstance(value, dict):
            found += [[section, key] for key in sorted(value)]
    return found


def _item(step: Callable[[], Any], path: Path, said: list[str]) -> Any:
    """One item's ``step``: its result, or None with what stopped it said in ``said`` (an ``OSError``: a file that
    cannot be read or written now), never an import stopped."""
    try:
        return step()
    except OSError as error:
        said.append(f"{path} was not imported: {error.strerror or error}")
        return None


def _listed(folder: Path, said: list[str]) -> list[str]:
    """The names in ``folder``, sorted; none where it is not there; said in ``said`` where it cannot be listed."""
    try:
        return sorted(os.listdir(folder))
    except FileNotFoundError:
        return []
    except OSError as error:
        said.append(f"{folder} was not imported: {error.strerror or error}")
        return []


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
    """Each file copied into ``staging`` moved into ``data``, which a process of the version wrote before its first
    start was marked: where ``data`` has none, and over what is there for the settings, the page token, the port
    record and the ledger (``WINS``): those were a fresh default written for want of the import, and the copy is
    the person's (a telemetry no among it). A record or a picture written first stays: it is newer than the copy."""
    from cad._internal.atomic_replace import replace_atomic

    for folder, _dirs, files in os.walk(staging):
        for name in files:
            path = Path(folder) / name
            inside = path.relative_to(staging)
            target = data / inside
            if os.path.lexists(target) and inside.as_posix() not in WINS:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            replace_atomic(path, target)


# --- the carry-over -----------------------------------------------------------------------------------------


@dataclass
class Carried:
    """What ``carry`` did: a line for each kind of item it added (``added``), and each item it could not read or
    write (``failed``). ``complete``: nothing failed, so the source may go."""

    added: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.failed


def _read_ledger(data: Path) -> dict[str, dict[str, list[str]]]:
    """A data folder's ``LEDGER``: ``{source: {"documents": [...]}}``; ``{}`` with none. ``OSError`` when it is there
    and cannot be read, is no JSON, or is in a form this release does not read: never taken for none, which would let
    every record deleted since come back (``carry`` then carries nothing, and nothing is removed for want of it)."""
    path = data / LEDGER
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except ValueError as error:
        raise OSError(f"{path} is no ledger this release reads ({error})") from None
    taken = found.get("from") if isinstance(found, dict) and found.get("schema") == LEDGER_SCHEMA else None
    if not isinstance(taken, dict):
        raise OSError(f"{path} is no ledger this release reads")
    return {key: value for key, value in taken.items() if isinstance(value, dict)}


def _write_ledger(data: Path, taken: dict[str, dict[str, list[str]]]) -> None:
    from cad._internal.atomic_replace import write_bytes_atomic

    data.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(data / LEDGER, (json.dumps({"schema": LEDGER_SCHEMA, "from": taken}, indent=1, sort_keys=True)
                                       + "\n").encode("utf-8"))


def carry(found: Source, name: str, *, told: Callable[[str], None] | None = None) -> Carried:
    """What ``found`` holds that version ``name``'s data lacks, added to it (see the module), each item it cannot read
    or write said to ``told`` and in the result. Never what was kept for sending, which moves once, at a removal
    (``versions._hand_on``). Nothing for a target with no data yet (``imported``), and never from a newer version into
    an older one: both are failures, so nothing is removed for want of them."""
    from cad.engine.ids import is_id
    from cad.engine.records import RECORD
    from cad_server._internal import versions
    from cad_server._internal.file_lock import state
    from cad_server.engine.registry import Folder, Registry, pictures

    say = told or (lambda _line: None)
    done = Carried()

    def failed(line: str) -> None:
        done.failed.append(line)
        say(line)

    if not imported(name):
        failed(f"text-to-cad {name} has no data yet: nothing of {found.words()} was carried over")
        return done
    if found.kind == "version" and found.version is not None and versions.older(name, found.version):
        failed(f"text-to-cad {found.version} is newer than {name}: its data is never carried into an older version")
        return done
    data, cache = _data(name), places.cache_dir(name)
    root = found.root
    target, target_cache = Folder(data), Folder(cache)
    try:
        ledger = _read_ledger(data)
    except OSError as error:
        failed(f"{data / LEDGER} cannot be read ({error.strerror or error}): nothing was carried over")
        return done
    taken = ledger.setdefault(found.key, {})
    documents = set(taken.get("documents") or ())
    # What the target took from any source: an id it took once and lacks now was deleted there (sources share ids).
    ever = set().union(*(set(each.get("documents") or ()) for each in ledger.values()))
    keys = {tuple(key) for key in taken.get("settings") or () if isinstance(key, list)}
    ever_keys = set().union(*({tuple(key) for key in each.get("settings") or () if isinstance(key, list)}
                              for each in ledger.values()))

    # Settings: a section, or a key of a section, the target lacks and never had from a source.
    added = _carry_settings(root / SETTINGS, data / SETTINGS, failed, keys, ever_keys)
    if added:
        done.added.append(f"{added} setting{'s' if added != 1 else ''}")

    # Records, by id; their bytes and Recents pictures with them; the later Recents use where both have one.
    records = opened = 0
    registry = Registry(target, cache=target_cache)
    for ident in _listed(root / DOCUMENTS, done.failed) if not found.settings_only else []:  # noqa: B007
        path = root / DOCUMENTS / ident / RECORD
        if not is_id(ident) or not path.is_file():
            continue
        try:
            raw = path.read_bytes()
            mode = os.stat(path).st_mode & 0o777
            record = json.loads(raw)
        except (OSError, ValueError) as error:
            failed(f"{path} was not carried over: {getattr(error, 'strerror', None) or error}")
            continue
        try:
            if (data / DOCUMENTS / ident / RECORD).is_file():
                if _later_use(registry, ident, record):
                    opened += 1
                documents.add(ident)
                continue
            if ident in ever:
                continue  # taken once and deleted since: it stays deleted
            from cad.engine.records import FILE

            _new_bytes(found.cache / DOCUMENTS / ident / FILE, cache / DOCUMENTS / ident / FILE)
            for picture in pictures(record if isinstance(record, dict) else None):
                source = root / "recents" / "thumbnails" / picture
                if source.is_file():
                    target.create(f"recents/thumbnails/{picture}", source.read_bytes(), mode=0o644)
            target.create(f"{DOCUMENTS}/{ident}/{RECORD}", raw, mode=mode or 0o644)
        except OSError as error:
            failed(f"{path} was not carried over: {error.strerror or error}")
            continue
        documents.add(ident)
        records += 1
    if records:
        done.added.append(f"{records} document record{'s' if records != 1 else ''}")
    if opened:
        done.added.append(f"{opened} later Recents use{'s' if opened != 1 else ''}")

    taken["documents"] = sorted(documents)
    taken["settings"] = [list(key) for key in sorted(keys)]
    try:
        with state(data):
            on_disk = _read_ledger(data)
            on_disk[found.key] = taken
            _write_ledger(data, on_disk)
    except OSError as error:
        failed(f"{data / LEDGER} could not be written: {error.strerror or error}")
    if done.added:
        say(f"carried over into text-to-cad {name} from {found.words()}: {', '.join(done.added)}")
    return done


def _carry_settings(source: Path, target: Path, failed: Callable[[str], None], keys: set[tuple[str, ...]] | None = None,
                    ever: set[tuple[str, ...]] | None = None) -> int:
    """The settings at ``source`` the settings at ``target`` lack, added under the target's lock (a section it
    lacks; a key a section of its lacks, but the telemetry section's), unless the target had it from a source once
    (``ever``: the person removed it since); how many. Each section and key the source has that the target holds now
    is noted in ``keys`` (what the target took from this source, ``LEDGER``). A file that cannot be read fails."""
    from cad._internal.atomic_replace import write_bytes_atomic
    from cad_server._internal.file_lock import state
    from cad_server.settings import _load

    try:
        given = _load(source)
    except OSError as error:
        failed(f"{source} was not carried over: {error.strerror or error}")
        return 0
    if not given:
        return 0
    added = 0
    keys = set() if keys is None else keys
    ever = set() if ever is None else ever
    try:
        with state(target.parent):
            held = _load(target)
            for section, value in given.items():
                if section not in held:
                    if (section,) in ever:
                        continue  # had once, and removed since: it stays removed
                    held[section] = value
                    added += 1
                    keys.add((section,))
                    if isinstance(value, dict):
                        keys.update((section, key) for key in value)
                    continue
                keys.add((section,))
                if section != "telemetry" and isinstance(held[section], dict) and isinstance(value, dict):
                    for key, inner in value.items():
                        if key not in held[section]:
                            if (section, key) in ever:
                                continue
                            held[section][key] = inner
                            added += 1
                        keys.add((section, key))
            if added:
                write_bytes_atomic(target, (json.dumps(held, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    except OSError as error:
        failed(f"{target} could not be carried into: {error.strerror or error}")
        return 0
    from cad_server import analytics

    analytics.inherit_no(target)
    return added


def _later_use(registry: Any, ident: str, record: Any) -> bool:
    """The target's record ``ident`` given the source's Recents use (``opened``) where it is later than its own:
    whether it was."""
    given = record.get("opened") if isinstance(record, dict) else None
    if not isinstance(given, (int, float)) or isinstance(given, bool):
        return False
    changed: list[bool] = []

    def later(held: dict[str, Any] | None) -> dict[str, Any] | None:
        if held is None:
            return None
        mine = held.get("opened")
        if isinstance(mine, (int, float)) and not isinstance(mine, bool) and mine >= given:
            return None
        changed.append(True)
        return {**held, "opened": given}

    registry.update(ident, later)
    return bool(changed)


def _new_bytes(path: Path, target: Path) -> None:
    """A document's cached bytes at ``path`` given to ``target`` where it has none: a hard link (one volume), else a
    copy made beside it and linked into place, so a document the target saved meanwhile is never replaced."""
    if not path.is_file() or os.path.lexists(target):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(path, target)
        return
    except FileExistsError:
        return
    except OSError:
        pass
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        shutil.copy2(path, temporary)
        try:
            (os.rename if os.name == "nt" else os.link)(temporary, target)
        except FileExistsError:
            pass
    finally:
        with contextlib.suppress(OSError):
            temporary.unlink()
