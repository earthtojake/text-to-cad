"""The sweeper: retire, evict, then mark and sweep (STORE.md §8).

One pass scans the store once (names, sizes, mtimes), marks once, and removes
three kinds of thing:

- **Retired kinds.** A folder under ``index/`` that is not in ``INDEX_KINDS``
  (the operation cache's ``index/op``) goes, with every object only its
  entries named.
- **Evicted entries**, only under a cap: derived entries (``DERIVED_KINDS``),
  least recently written first, until the store fits ``LOW_WATERMARK`` of the
  cap. A record, a document entry or an output entry is never evicted.
- **Unreachable objects**: not in the closure of a current record's or
  document entry's tree, not named by a surviving derived entry, and not
  written or claimed within the grace window (default 1 h).

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
from cadgen.store.paths import DERIVED_KINDS, INDEX_KINDS, store_root

DEFAULT_GRACE_SECONDS = 3600.0
# A pass over the cap brings the store down to this fraction of it, so the
# next one waits for a fifth of the cap of growth rather than the next build.
LOW_WATERMARK = 0.8
ENV_MAX = "CADGEN_STORE_MAX"
# Two orders of magnitude above a heavy project's working set and a fraction
# of any developer disk. Fixed rather than a share of free space: the number
# ``store info`` shows must not move because something else filled the disk.
DEFAULT_MAX_BYTES = 20 * 1024**3

_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?)(?:i?b)?\s*$", re.IGNORECASE)
_UNITS = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
# What each derived kind names in objects/. A retired kind's entries are read
# for any top-level object pointer: their readers are gone with their schema.
_NAMED_FIELDS = {
    "component": ("brep", "eagerSurface"),
    "surface": ("object",),
    "mesh": ("object",),
    "drawing": ("object",),
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


@dataclass
class Scan:
    """One stat walk of the store: every object and every index entry."""

    objects: dict[str, tuple[int, float]] = field(default_factory=dict)  # digest -> (size, mtime)
    entries: dict[str, dict[str, tuple[int, float]]] = field(default_factory=dict)  # kind -> key -> (size, mtime)
    leftovers: list[tuple[Path, int, float]] = field(default_factory=list)  # temp files a writer or a pass left
    total: int = 0

    @property
    def retired(self) -> list[str]:
        return sorted(kind for kind in self.entries if kind not in INDEX_KINDS)


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


def scan(root: Path | str | None = None, *, keep: bool = True) -> Scan:
    """Names, sizes and mtimes of everything under the store, from one stat walk
    that reads no file. ``keep=False`` keeps nothing per file -- only the total
    and the kinds present, which is all the daemon's idle look needs."""
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
        if len(shard.name) != 2 or not shard.is_dir(follow_symlinks=False):
            continue
        for item in _listing(shard.path):
            file = _file_stat(item)
            if file is None:
                continue
            if item.name.startswith("."):
                if item.name.endswith(".tmp"):
                    counted(item, file, None, None)
            elif is_object_hash(shard.name + item.name):
                counted(item, file, found.objects, shard.name + item.name)
    for folder in _listing(root / "index"):
        if folder.name.startswith(".") or not folder.is_dir(follow_symlinks=False):
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


def protected_objects(found: Scan, *, should_stop: Callable[[], bool] = lambda: False) -> set[str]:
    """Every object a current record's or document entry's tree reaches.

    These are what eviction may never free: the result trees, saved-document
    trees and the components they place, each tree read and verified once.
    """
    from cadgen.store.records import DOCUMENT_SCHEMA_VERSION, RECORD_SCHEMA_VERSION
    from cadgen.store.trees import get_tree

    roots: list[object] = []
    for count, key in enumerate(found.entries["model"]):
        if count % _STOP_EVERY == 0 and should_stop():
            raise _Stopped
        record = read_entry("model", key)
        if record and record.get("schemaVersion") == RECORD_SCHEMA_VERSION:
            roots.extend(record.get(name) for name in ("tree", "documentTree"))
    for count, key in enumerate(found.entries["document"]):
        if count % _STOP_EVERY == 0 and should_stop():
            raise _Stopped
        entry = read_entry("document", key)
        if entry and entry.get("schemaVersion") == DOCUMENT_SCHEMA_VERSION:
            roots.append(entry.get("tree"))
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


def _read_entries(found: Scan, kinds, should_stop: Callable[[], bool]) -> list[_Entry]:
    rows: list[_Entry] = []
    for kind in kinds:
        folder = store_root() / "index" / kind
        for key, (size, mtime) in found.entries.get(kind, {}).items():
            if len(rows) % _STOP_EVERY == 0 and should_stop():
                raise _Stopped
            named = () if kind == "bounds" else named_objects(kind, _read_json(folder / key))
            rows.append(_Entry(kind, key, size, mtime, tuple(d for d in named if d in found.objects)))
    return rows


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
    down to :func:`eviction_target`. ``retired_only`` retires the kinds this
    cadgen does not define and sweeps only the objects their entries named --
    the daemon's automatic retirement, which collects nothing else.
    ``should_stop`` is polled throughout; stopping early leaves a consistent
    store, as every step does. ``found`` is a scan the caller just took."""
    stop = should_stop or (lambda: False)
    report = GcReport(dry_run=dry_run, cap=max_bytes)
    cutoff = time.time() - max(0.0, float(grace_seconds))
    found = scan() if found is None else found
    report.records = len(found.entries["model"])
    report.bytes_before = report.bytes_after = found.total
    if retired_only and not found.retired:
        return report
    try:
        if stop():
            raise _Stopped
        protected = protected_objects(found, should_stop=stop)
        report.protected_bytes = sum(found.objects[d][0] for d in protected)
        derived = _read_entries(found, DERIVED_KINDS, stop)
        retired = _read_entries(found, found.retired, stop)
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
        _retire(retired, live, kept, dry_run, stop, report)
        _clear_leftovers(found, cutoff, dry_run, stop, report)
    except _Stopped:
        report.stopped = True
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


def _retire(retired: list[_Entry], live: set[str], kept: set[str], dry_run: bool,
            stop: Callable[[], bool], report: GcReport) -> None:
    """Remove the retired kinds' entries, then their folders once empty.

    An entry naming an object the grace window kept, and that nothing else
    reaches, stays for the pass after it, so that object still goes with its
    kind instead of waiting for a full sweep.
    """
    folders: set[Path] = set()
    for count, row in enumerate(retired):
        if count % _STOP_EVERY == 0 and stop():
            raise _Stopped
        if any(digest in kept and digest not in live for digest in row.named):
            continue
        path = store_root() / "index" / row.kind / row.key
        folders.add(path.parent)
        if not dry_run:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                continue
        report.retired[row.kind] = report.retired.get(row.kind, 0) + 1
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
    every object a derived entry names."""
    found = scan()
    live = protected_objects(found)
    for row in _read_entries(found, DERIVED_KINDS, lambda: False):
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
    parser.add_argument("--retired-only", action="store_true", help="retire, and sweep only what the retired kinds named")
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
