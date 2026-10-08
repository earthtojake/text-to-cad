"""The sweeper: retire, evict, then mark and sweep (STORE.md §8).

One pass scans the store once (names, sizes, mtimes), marks once, and removes
three kinds of thing:

- **Retired kinds and obsolete entries.** The ``index/`` folders in
  ``RETIRED_KINDS`` (the operation cache's ``index/op``) go, with every object
  only their entries named; so do the surface and mesh entries an older
  extractor or mesher of cadgen's wrote, which no reader of this cadgen asks
  for again (``surfaces.obsolete_entry``, ``meshes.obsolete_key``, and a mesh
  keyed by such a surface's input), once last written
  ``OBSOLETE_RETIRE_AFTER_SECONDS`` ago (a week): an older cadgen sharing the
  store may still read them, and a read never writes.
- **Evicted entries**, only under a cap: derived entries (``DERIVED_KINDS``),
  least recently written first, until the store fits ``LOW_WATERMARK`` of the
  cap. A record, a document entry or an output entry is never evicted.
- **Unreachable objects**: not in the closure of a current record's or
  document entry's tree, not named by a surviving derived entry, and not
  written or claimed within the grace window (default 1 h).

A store a newer cadgen writes to is left alone. A record, document entry or
tree in a newer format than this cadgen's, or an ``index/`` folder it does not
know, written within ``NEWER_CADGEN_SECONDS``, and the pass deletes nothing:
this cadgen cannot read what that one still needs, so that one collects. Past
the window, the newer cadgen is taken to be gone. A folder under ``index/``
that this cadgen does not know is never touched, and neither is anything
outside its own folders.

Recently used means recently written. No reader writes: an entry's mtime is
when a build or a derivation last wrote it, and an object's is when a publish
last wrote or claimed it (``objects.claim_object``). Objects are deleted only by
``objects.delete_unclaimed``, rename then recheck, so a claim made while a pass
runs is never lost, and nothing takes a lock.

The mark reads JSON only: records, document entries, derived entries, and each
tree they reach once, verified against its address. A leaf object counts by
being there; its bytes are verified by whoever reads it. Deleting anything
here costs a recomputation, never a wrong answer.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import stat
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from cadgen.store.index import entry_path, read_entry
from cadgen._internal.atomic_replace import move_atomic
from cadgen.store.objects import delete_unclaimed, is_object_hash, object_path, swept_address
from cadgen.store.paths import DERIVED_KINDS, INDEX_KINDS, RETIRED_KINDS, store_root

DEFAULT_GRACE_SECONDS = 3600.0
# How long a newer cadgen's last write keeps this one's passes off the store.
NEWER_CADGEN_SECONDS = 30 * 24 * 3600.0
# How old an obsolete entry is before a pass retires it. An older cadgen still in
# use on the store derives what it reads again at most once a week per entry, and
# an upgrade's leftovers go within about a week.
OBSOLETE_RETIRE_AFTER_SECONDS = 7 * 24 * 3600.0
# A pass over the cap brings the store down to this fraction of it, so the
# next one waits for a fifth of the cap of growth rather than the next build.
LOW_WATERMARK = 0.8
ENV_MAX = "CADGEN_STORE_MAX"
# Two orders of magnitude above a heavy project's working set and a fraction
# of any developer disk. Fixed rather than a share of free space: the number
# ``store info`` shows must not move because something else filled the disk.
DEFAULT_MAX_BYTES = 20 * 1024**3

_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?)(?:i?b)?\s*$", re.IGNORECASE)
# objects/ab/cdef...: only names an object can have are the sweeper's.
_SHARD = re.compile(r"^[0-9a-f]{2}$")
_OBJECT_NAME = re.compile(r"^[0-9a-f]{62}$")
_UNITS = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
# What each derived kind names in objects/. A retired kind's entries are read
# for any top-level object pointer: their readers are gone with their schema.
_NAMED_FIELDS = {
    "component": ("brep", "eagerSurface"),
    "surface": ("object",),
    "mesh": ("object",),
    "drawing": ("object",),
    "skin": ("object",),
    "bounds": (),
}
_STOP_EVERY = 256


def parse_size(text: str) -> int:
    """``"20G"``, ``"500MB"``, ``"1.5 GiB"``, ``"0"`` (no cap) -> bytes, binary units."""
    match = _SIZE.match(str(text))
    if not match:
        raise ValueError(f"not a size: {text!r} (examples: 20G, 500M, 1.5GiB, 0 for no cap)")
    return int(float(match[1]) * _UNITS[match[2].lower()])


def configured_cap(env: dict[str, str] | None = None) -> int | None:
    """The cap in force: ``CADGEN_STORE_MAX`` when set (``0`` means none), else the default."""
    raw = str((os.environ if env is None else env).get(ENV_MAX, "") or "").strip()
    if not raw:
        return DEFAULT_MAX_BYTES
    try:
        return parse_size(raw) or None
    except ValueError as error:
        raise ValueError(f"{ENV_MAX}={raw!r} is {error}") from None


class _Stopped(Exception):
    """A job arrived: the pass ends where it is, which is always safe."""


class _Deferred(Exception):
    """A newer cadgen writes to this store: the pass leaves it to that one.
    Carries ``{"evidence": [...], "lastWritten": mtime}``."""


@dataclass
class Scan:
    """One stat walk of the store: every object and every index entry."""

    objects: dict[str, tuple[int, float]] = field(default_factory=dict)  # digest -> (size, mtime)
    entries: dict[str, dict[str, tuple[int, float]]] = field(default_factory=dict)  # kind -> key -> (size, mtime)
    leftovers: list[tuple[Path, int, float]] = field(default_factory=list)  # temp files a writer or a pass left
    # Folders under index/ this cadgen neither defines nor retires -> their newest file's mtime.
    # Never counted, read or touched.
    unknown: dict[str, float] = field(default_factory=dict)
    total: int = 0

    @property
    def retired(self) -> list[str]:
        return [kind for kind in RETIRED_KINDS if kind in self.entries]


def _listing(folder: Path | str):
    try:
        with os.scandir(folder) as it:
            yield from it
    except OSError:
        return


def _file_stat(item: os.DirEntry) -> os.stat_result | None:
    try:
        found = item.stat(follow_symlinks=False)
    except OSError:
        return None
    return found if stat.S_ISREG(found.st_mode) else None


def _newest_file(folder: os.DirEntry) -> float | None:
    newest = None
    for item in _listing(folder.path):
        file = _file_stat(item)
        if file is not None and (newest is None or file.st_mtime > newest):
            newest = file.st_mtime
    return newest


def scan(root: Path | str | None = None, *, keep: bool = True) -> Scan:
    """Names, sizes and mtimes of everything in the store's own folders, from
    one stat walk that reads no file: object shards, and the ``index/`` folders
    this cadgen defines or retires. Any other ``index/`` folder is only noted,
    with its newest file's mtime. ``keep=False`` keeps nothing per file -- only
    the total and the kinds present, which is all the daemon's idle look needs."""
    root = store_root() if root is None else Path(root)
    found = Scan()

    def counted(item: os.DirEntry, file: os.stat_result, listing: dict | None, name: str | None) -> None:
        found.total += file.st_size
        if not keep:
            return
        if listing is None:
            found.leftovers.append((Path(item.path), file.st_size, file.st_mtime))
        else:
            listing[name] = (file.st_size, file.st_mtime)

    for shard in _listing(root / "objects"):
        if not _SHARD.match(shard.name) or not shard.is_dir(follow_symlinks=False):
            continue
        for item in _listing(shard.path):
            file = _file_stat(item)
            if file is None:
                continue
            if item.name.startswith("."):
                if item.name.endswith(".tmp"):
                    counted(item, file, None, None)
            elif _OBJECT_NAME.match(item.name):
                counted(item, file, found.objects, shard.name + item.name)
    for folder in _listing(root / "index"):
        if folder.name.startswith(".") or not folder.is_dir(follow_symlinks=False):
            continue
        if folder.name not in INDEX_KINDS and folder.name not in RETIRED_KINDS:
            newest = _newest_file(folder)
            if newest is not None:
                found.unknown[folder.name] = newest
            continue
        listing = found.entries.setdefault(folder.name, {})
        for item in _listing(folder.path):
            file = _file_stat(item)
            if file is None:
                continue
            if not item.name.startswith("."):
                counted(item, file, listing, item.name)
            elif item.name.endswith(".tmp"):
                counted(item, file, None, None)
    for kind in INDEX_KINDS:
        found.entries.setdefault(kind, {})
    return found


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def named_objects(kind: str, entry: dict | None) -> tuple[str, ...]:
    """The objects an index entry keeps: what its current reader would read."""
    if not entry:
        return ()
    if kind == "component" and entry.get("schemaVersion") != 1:
        return ()
    if kind == "surface":
        from cadgen.store.surfaces import SURFACE_SCHEMA

        if entry.get("schemaVersion") != SURFACE_SCHEMA:
            return ()
    fields = _NAMED_FIELDS.get(kind)
    values = entry.values() if fields is None else (entry.get(name) for name in fields)
    return tuple(dict.fromkeys(value for value in values if is_object_hash(value)))


def _newer(version: object, current: int) -> bool:
    return isinstance(version, int) and not isinstance(version, bool) and version > current


def _defer_if_recent(newer: dict[str, float], since: float) -> None:
    recent = {what: mtime for what, mtime in newer.items() if mtime > since}
    if recent:
        raise _Deferred({"evidence": sorted(recent), "lastWritten": max(recent.values())})


def _read_roots(found: Scan, should_stop: Callable[[], bool], newer_since: float | None) -> list[object]:
    """The protected trees: every current-format record's ``tree`` and
    ``documentTree``, and every current-format document entry's tree.

    With ``newer_since``, a store a newer cadgen wrote to after it raises
    :class:`_Deferred` instead: an ``index/`` folder this cadgen does not know,
    or a record or document entry in a newer format than this cadgen reads.
    """
    from cadgen.store.records import DOCUMENT_SCHEMA_VERSION, RECORD_SCHEMA_VERSION

    newer = {f"index/{name}, a folder this cadgen does not know": mtime for name, mtime in found.unknown.items()}
    roots: list[object] = []
    for kind, current, fields in (("model", RECORD_SCHEMA_VERSION, ("tree", "documentTree")),
                                  ("document", DOCUMENT_SCHEMA_VERSION, ("tree",))):
        for count, (key, (_size, mtime)) in enumerate(found.entries[kind].items()):
            if count % _STOP_EVERY == 0 and should_stop():
                raise _Stopped
            entry = read_entry(kind, key)
            if not entry:
                continue
            version = entry.get("schemaVersion")
            if version == current:
                roots.extend(entry.get(name) for name in fields)
            elif _newer(version, current):
                what = f"index/{kind} entries in format {version} (this cadgen reads {current})"
                newer[what] = max(mtime, newer.get(what, mtime))
    if newer_since is not None:
        _defer_if_recent(newer, newer_since)
    return roots


def _tree_version(digest: str) -> object:
    """The format a tree this cadgen cannot read declares, when it is a tree."""
    from cadgen.store.objects import read_verified_object
    from cadgen.store.trees import TREE_KIND

    try:
        data = json.loads(read_verified_object(digest))
    except (OSError, ValueError, TypeError):
        return None
    return data.get("schemaVersion") if isinstance(data, dict) and data.get("kind") == TREE_KIND else None


def newer_cadgen(found: Scan | None = None) -> dict | None:
    """Why a pass would leave this store to a newer cadgen -- ``{"evidence",
    "lastWritten"}`` -- or None. Reads records and document entries; a pass
    also recognises a tree in a newer format while it marks."""
    found = scan() if found is None else found
    try:
        _read_roots(found, lambda: False, time.time() - NEWER_CADGEN_SECONDS)
    except _Deferred as deferred:
        return deferred.args[0]
    return None


def protected_objects(found: Scan, *, should_stop: Callable[[], bool] = lambda: False,
                      newer_since: float | None = None) -> set[str]:
    """Every object a current record's or document entry's tree reaches.

    These are what eviction may never free: the result trees, saved-document
    trees and the components they place, each tree read and verified once.
    With ``newer_since``, raises :class:`_Deferred` on evidence that a newer
    cadgen wrote to the store after it (:func:`_read_roots`), or on a tree in
    a newer format written after it.
    """
    from cadgen.store.trees import TREE_SCHEMA, get_tree

    roots = _read_roots(found, should_stop, newer_since)
    marked: set[str] = set()
    pending = [root for root in roots if isinstance(root, str) and root in found.objects]
    visited = 0
    while pending:
        digest = pending.pop()
        if digest in marked or digest not in found.objects:
            continue
        visited += 1
        if visited % _STOP_EVERY == 0 and should_stop():
            raise _Stopped
        tree = get_tree(digest)
        if tree is None:
            written = found.objects[digest][1]
            if newer_since is not None and written > newer_since:
                version = _tree_version(digest)
                if _newer(version, TREE_SCHEMA):
                    raise _Deferred({"evidence": [f"trees in format {version} (this cadgen reads {TREE_SCHEMA})"],
                                     "lastWritten": written})
            continue
        marked.add(digest)
        for component in tree["components"].values():
            if isinstance(component, dict):
                marked.update(component.get(name) for name in ("brep", "eagerSurface")
                              if component.get(name) in found.objects)
        pending.extend(link["tree"] for link in tree["links"])
    return marked


@dataclass
class _Entry:
    kind: str
    key: str
    size: int
    mtime: float
    named: tuple[str, ...]
    obsolete: bool = False


def _obsolete(kind: str, key: str, entry: dict | None) -> bool:
    if kind == "mesh":
        from cadgen.store.meshes import obsolete_key

        return obsolete_key(key)
    if kind == "surface":
        from cadgen.store.surfaces import obsolete_entry

        return obsolete_entry(key, entry)
    return False


def _read_entries(found: Scan, kinds, should_stop: Callable[[], bool]) -> list[_Entry]:
    rows: list[_Entry] = []
    for kind in kinds:
        folder = store_root() / "index" / kind
        for key, (size, mtime) in found.entries.get(kind, {}).items():
            if len(rows) % _STOP_EVERY == 0 and should_stop():
                raise _Stopped
            entry = None if kind == "bounds" else _read_json(folder / key)
            named = named_objects(kind, entry)
            rows.append(_Entry(kind, key, size, mtime, tuple(d for d in named if d in found.objects),
                               _obsolete(kind, key, entry)))
    return rows


def _split_obsolete(rows: list[_Entry], retire_before: float) -> tuple[list[_Entry], list[_Entry]]:
    """``rows`` as (kept, retiring): the obsolete entries last written by
    ``retire_before``, and the rest. A mesh keyed by an obsolete surface's input
    is obsolete with it: no reader of this cadgen computes that input again. A
    younger obsolete entry stays like a current one, with its objects, and so
    does an obsolete surface while a mesh keyed by it is younger: that mesh is
    known obsolete only by its surface."""
    gone = {row.key for row in rows if row.kind == "surface" and row.obsolete}
    for row in rows:
        row.obsolete = row.obsolete or (row.kind == "mesh" and row.key[:64] in gone)
    held = {row.key[:64] for row in rows if row.kind == "mesh" and row.obsolete and row.mtime > retire_before}
    current: list[_Entry] = []
    obsolete: list[_Entry] = []
    for row in rows:
        retiring = row.obsolete and row.mtime <= retire_before and not (row.kind == "surface" and row.key in held)
        (obsolete if retiring else current).append(row)
    return current, obsolete


def producer_versions() -> dict[str, list[int]]:
    """The versions an entry is obsolete against. The daemon notes, per store and
    per these versions, when its last retiring pass ran (``daemon/housekeeping.py``)."""
    from cadgen.store.meshes import PAYLOAD_VERSION, TESSELLATOR_VERSION
    from cadgen.store.surfaces import EXTRACTION_SCHEME, SURF_FORMAT

    return {"surface": [EXTRACTION_SCHEME, SURF_FORMAT], "mesh": [TESSELLATOR_VERSION, PAYLOAD_VERSION]}


@dataclass
class GcReport:
    records: int = 0
    reachable: int = 0
    kept_by_grace: int = 0
    removed: int = 0
    removed_bytes: int = 0
    dry_run: bool = False
    removed_paths: list[str] = field(default_factory=list)
    # Retired index kinds: entries removed (or that would be), by kind.
    retired: dict[str, int] = field(default_factory=dict)
    # Obsolete surface and mesh entries removed (or that would be), by kind.
    obsolete: dict[str, int] = field(default_factory=dict)
    # Both of the above, in index bytes.
    retired_bytes: int = 0
    # Present when a cap was given.
    cap: int | None = None
    bytes_before: int = 0
    bytes_after: int = 0
    protected_bytes: int = 0
    target_bytes: int | None = None
    evicted: dict[str, int] = field(default_factory=dict)
    evicted_bytes: int = 0
    stopped: bool = False
    # Set when a newer cadgen writes to this store and the pass left it alone.
    deferred: dict | None = None


def eviction_target(cap: int, floor: int) -> int:
    """The size a pass brings the store down to: the low watermark, unless what
    no pass may remove (``floor``) leaves less than the fifth of the cap above
    it -- then the most recently written derived entries keep that fifth, so a
    cap the records and documents outgrew never empties every derived cache."""
    low = int(cap * LOW_WATERMARK)
    return max(low, floor + (cap - low))


def _plan_eviction(found: Scan, derived: list[_Entry], keep: set[str], cutoff: float,
                   cap: int, other_bytes: int) -> tuple[list[_Entry], int]:
    """Derived entries to drop, least recently written first, so the store fits
    :func:`eviction_target`; and that target.

    Sized by what would remain, deduplicated: an object goes only when no
    protected tree, no fresh object and no surviving entry still needs it, so
    an entry whose objects a current tree also places frees only itself.
    ``other_bytes`` is every index entry that stays regardless of eviction.
    """
    fixed = set(keep)
    candidates: list[_Entry] = []
    refs: Counter[str] = Counter()
    leased = 0
    for row in derived:
        if row.mtime > cutoff:
            fixed.update(row.named)
            leased += row.size
        else:
            candidates.append(row)
            refs.update(row.named)
    floor = other_bytes + leased + sum(found.objects[d][0] for d in fixed)
    target = eviction_target(cap, floor)
    projected = (floor + sum(row.size for row in candidates)
                 + sum(found.objects[d][0] for d in set(refs) - fixed))
    victims: list[_Entry] = []
    for row in sorted(candidates, key=lambda row: (row.mtime, row.kind, row.key)):
        if projected <= target:
            break
        victims.append(row)
        projected -= row.size
        for digest in row.named:
            refs[digest] -= 1
            if refs[digest] == 0 and digest not in fixed:
                projected -= found.objects[digest][0]
    return victims, target


def collect(
    *,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    dry_run: bool = False,
    max_bytes: int | None = None,
    retired_only: bool = False,
    should_stop: Callable[[], bool] | None = None,
    found: Scan | None = None,
) -> GcReport:
    """One pass. ``max_bytes`` adds eviction, when the store is over that cap,
    down to :func:`eviction_target`. ``retired_only`` retires ``RETIRED_KINDS``
    and the obsolete entries a week old, and sweeps only the objects their entries
    named -- the daemon's automatic retirement, which collects nothing else. ``should_stop`` is polled
    throughout; stopping early leaves a consistent store, as every step does.
    ``found`` is a scan the caller just took. A store a newer cadgen writes to
    is left alone: nothing is removed, and ``deferred`` says why."""
    stop = should_stop or (lambda: False)
    report = GcReport(dry_run=dry_run, cap=max_bytes)
    now = time.time()
    grace = max(0.0, float(grace_seconds))
    # No window keeps nothing back, however recent: Windows' time.time() can trail a file's mtime
    # by a clock step (~16 ms), and ``now - 0`` would keep what was written a moment ago.
    cutoff = now - grace if grace else math.inf
    found = scan() if found is None else found
    report.records = len(found.entries["model"])
    report.bytes_before = report.bytes_after = found.total
    if retired_only and not found.retired and not (found.entries["surface"] or found.entries["mesh"]):
        return report
    try:
        if stop():
            raise _Stopped
        protected = protected_objects(found, should_stop=stop, newer_since=now - NEWER_CADGEN_SECONDS)
        report.protected_bytes = sum(found.objects[d][0] for d in protected)
        derived, obsolete = _split_obsolete(_read_entries(found, DERIVED_KINDS, stop), now - OBSOLETE_RETIRE_AFTER_SECONDS)
        retired = _read_entries(found, found.retired, stop) + obsolete
        fresh = {digest for digest, (_, mtime) in found.objects.items() if mtime > cutoff}

        victims: list[_Entry] = []
        if max_bytes is not None and not retired_only and report.bytes_before > max_bytes:
            other = sum(size for kind, listing in found.entries.items()
                        if kind not in DERIVED_KINDS and kind in INDEX_KINDS for size, _ in listing.values())
            victims, report.target_bytes = _plan_eviction(found, derived, protected | fresh, cutoff, max_bytes, other)
        evicted = _evict(victims, dry_run, stop, report)
        survivors = [row for row in derived if (row.kind, row.key) not in evicted]
        live = protected | {digest for row in survivors for digest in row.named}
        report.reachable = len(live)

        if retired_only:
            candidates = {digest for row in retired for digest in row.named}
        else:
            candidates = set(found.objects)
        kept = _sweep(found, sorted(candidates - live), cutoff, dry_run, stop, report)
        _retire(found.retired, retired, live, kept, dry_run, stop, report)
        _clear_leftovers(found, cutoff, dry_run, stop, report)
    except _Stopped:
        report.stopped = True
    except _Deferred as deferred:
        report.deferred = deferred.args[0]
    report.bytes_after = max(0, report.bytes_before - report.removed_bytes - report.evicted_bytes - report.retired_bytes)
    return report


def _evict(victims: list[_Entry], dry_run: bool, stop: Callable[[], bool], report: GcReport) -> set[tuple[str, str]]:
    """Unlink the planned entries, oldest first. An entry written again since
    the scan is in use, and stays."""
    gone: set[tuple[str, str]] = set()
    for count, row in enumerate(victims):
        if count % _STOP_EVERY == 0 and stop():
            raise _Stopped
        path = entry_path(row.kind, row.key)
        try:
            if path.stat().st_mtime != row.mtime:
                continue
            if not dry_run:
                path.unlink()
        except OSError:
            continue
        gone.add((row.kind, row.key))
        report.evicted[row.kind] = report.evicted.get(row.kind, 0) + 1
        report.evicted_bytes += row.size
    return gone


def _sweep(found: Scan, digests: list[str], cutoff: float, dry_run: bool,
           stop: Callable[[], bool], report: GcReport) -> set[str]:
    """Delete the unreachable objects nothing claimed since ``cutoff``; return
    those the grace window kept."""
    kept: set[str] = set()
    for count, digest in enumerate(digests):
        if count % _STOP_EVERY == 0 and stop():
            raise _Stopped
        size, mtime = found.objects[digest]
        path = object_path(digest)
        if mtime > cutoff:
            kept.add(digest)
            report.kept_by_grace += 1
            continue
        if dry_run:
            freed = size
        else:
            freed = delete_unclaimed(path, cutoff)
            if not freed and path.exists():
                kept.add(digest)
                report.kept_by_grace += 1
                continue
        report.removed += 1
        report.removed_bytes += freed
        report.removed_paths.append(str(path))
    return kept


def _retire(kinds: list[str], retired: list[_Entry], live: set[str], kept: set[str], dry_run: bool,
            stop: Callable[[], bool], report: GcReport) -> None:
    """Remove the retired kinds' entries and the obsolete ones, then the
    retired kinds' folders once empty.

    An entry naming an object the grace window kept, and that nothing else
    reaches, stays for the pass after it, so that object still goes with its
    kind instead of waiting for a full sweep. So does an entry written again
    since the scan: an older cadgen sharing the store still uses it.
    """
    folders = {store_root() / "index" / kind for kind in kinds}
    for count, row in enumerate(retired):
        if count % _STOP_EVERY == 0 and stop():
            raise _Stopped
        if any(digest in kept and digest not in live for digest in row.named):
            continue
        path = store_root() / "index" / row.kind / row.key
        try:
            if path.stat().st_mtime != row.mtime:
                continue
            if not dry_run:
                path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            continue
        counts = report.obsolete if row.obsolete else report.retired
        counts[row.kind] = counts.get(row.kind, 0) + 1
        report.retired_bytes += row.size
    for folder in folders if not dry_run else ():
        try:
            folder.rmdir()
        except OSError:
            pass


def _clear_leftovers(found: Scan, cutoff: float, dry_run: bool, stop: Callable[[], bool], report: GcReport) -> None:
    """Temp files a crashed writer left, past the grace window, and objects a pass
    that died was holding: one claimed since goes back to its address."""
    for count, (path, size, mtime) in enumerate(found.leftovers):
        if count % _STOP_EVERY == 0 and stop():
            raise _Stopped
        address = swept_address(path)
        if mtime > cutoff and address is None:
            continue
        if dry_run:
            if mtime <= cutoff:
                report.removed_bytes += size
            continue
        if mtime > cutoff and not address.exists():
            with contextlib.suppress(OSError):
                move_atomic(path, address)
            continue
        try:
            path.unlink()
        except OSError:
            continue
        report.removed_bytes += size


def reachable_objects() -> set[str]:
    """What a sweep keeps regardless of age: the protected trees' closures and
    every object a derived entry no pass retires yet names."""
    found = scan()
    live = protected_objects(found)
    rows = _read_entries(found, DERIVED_KINDS, lambda: False)
    for row in _split_obsolete(rows, time.time() - OBSOLETE_RETIRE_AFTER_SECONDS)[0]:
        live.update(row.named)
    return live


def main(argv: list[str] | None = None) -> int:
    """``python -m cadgen.store.gc``: one pass for the daemon's housekeeping, in a
    process of its own so the pass's memory leaves with it. The store is
    ``CADGEN_CACHE_DIR``. The pass stops at its next step once stdin closes --
    how the daemon takes its idle moment back -- and prints its report as one
    JSON line."""
    import argparse
    import dataclasses
    import sys
    import threading

    parser = argparse.ArgumentParser(prog="python -m cadgen.store.gc", description=main.__doc__)
    parser.add_argument("--max-bytes", type=int, default=None, help="evict to this cap")
    parser.add_argument("--retired-only", action="store_true",
                        help="retire, and sweep only what the retired kinds and week-old obsolete entries named")
    args = parser.parse_args(argv)
    released = threading.Event()

    def watch_stdin() -> None:
        try:
            sys.stdin.read()
        except (OSError, ValueError, AttributeError):
            return
        released.set()

    threading.Thread(target=watch_stdin, name="cadgen-store-gc-stdin", daemon=True).start()
    report = collect(max_bytes=args.max_bytes, retired_only=args.retired_only, should_stop=released.is_set)
    payload = {name: value for name, value in dataclasses.asdict(report).items() if name != "removed_paths"}
    print(json.dumps(payload, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
