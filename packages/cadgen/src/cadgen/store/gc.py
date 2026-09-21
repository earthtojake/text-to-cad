"""GC: mark and sweep over the store.

Reachable = every object referenced (transitively, through links) from a
current record or document index, plus objects pointed at by component,
op-memo and mesh entries, plus
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
from cadgen.store.records import tree_for_document_hash
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
        from cadgen.store.records import RECORD_SCHEMA_VERSION
        if not record or record.get("schemaVersion") != RECORD_SCHEMA_VERSION:
            continue
        for field_name in ("tree", "documentTree"):
            tree = str(record.get(field_name) or "")
            if tree:
                tree_objects(tree, _seen=reachable)
    for document_hash, _path in iter_entries("document"):
        tree = tree_for_document_hash(document_hash)
        if tree:
            # Saved artifacts keep their own closure after source records are
            # forgotten. The document's mesh ledger names external outputs,
            # not objects in this store, and therefore adds no GC roots.
            tree_objects(tree, _seen=reachable)
    from cadgen.store.objects import read_verified_object
    from cadgen._internal.component_package import validate_geometry_component
    from cadgen.store.surfaces import validate_surface_record
    for key, path in iter_entries("component"):
        entry = read_entry("component", key)
        if not entry or entry.get("schemaVersion") != 1:
            continue
        entry = {field: value for field, value in entry.items() if field != "schemaVersion"}
        try:
            validate_geometry_component(entry, read_verified_object(entry["brep"]), cid=key)
        except (OSError, ValueError, TypeError, KeyError):
            continue
        reachable.add(entry["brep"])
        if entry.get("eagerSurface"):
            try:
                read_verified_object(entry["eagerSurface"])
            except (OSError, ValueError, TypeError):
                pass
            else:
                reachable.add(entry["eagerSurface"])
    for key, path in iter_entries("surface"):
        entry = read_entry("surface", key)
        try:
            validate_surface_record(entry, surface_input_key=key)
        except (OSError, ValueError, TypeError, KeyError):
            continue
        reachable.add(entry["object"])
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
