"""GC: mark and sweep over the store.

Reachable = every object referenced (transitively, through links) from a
current record, plus objects pointed at by op-memo and mesh entries, plus
anything modified within a grace period (default 1 h — the window in which a
build may still hold a pin to a child's previous tree). No age-sweeps, no
per-tier rules. Best-effort: deleting an object costs a rebuild, never
correctness.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from cadgen.store.index import iter_entries, read_entry
from cadgen.store.objects import iter_objects
from cadgen.store.trees import tree_objects

DEFAULT_GRACE_SECONDS = 3600.0


@dataclass
class GcReport:
    reachable: int = 0
    kept_by_grace: int = 0
    removed: int = 0
    removed_bytes: int = 0
    records: int = 0
    dry_run: bool = False
    removed_paths: list[str] = field(default_factory=list)


def reachable_objects() -> set[str]:
    reachable: set[str] = set()
    for _name, path in iter_entries("model"):
        record = read_entry("model", path.name)
        if not record:
            continue
        tree = str(record.get("tree") or "")
        if tree:
            tree_objects(tree, _seen=reachable)
    for kind in ("op", "mesh"):
        for _name, path in iter_entries(kind):
            entry = read_entry(kind, path.name)
            if entry and entry.get("object"):
                reachable.add(str(entry["object"]))
    return reachable


def collect(*, grace_seconds: float = DEFAULT_GRACE_SECONDS, dry_run: bool = False) -> GcReport:
    report = GcReport(dry_run=dry_run)
    reachable = reachable_objects()
    report.reachable = len(reachable)
    report.records = sum(1 for _ in iter_entries("model"))
    cutoff = time.time() - max(0.0, float(grace_seconds))
    for digest, path in iter_objects():
        if digest in reachable:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > cutoff:
            report.kept_by_grace += 1
            continue
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        report.removed += 1
        report.removed_bytes += size
        report.removed_paths.append(str(path))
        if not dry_run:
            try:
                os.unlink(path)
            except OSError:
                pass
    return report
