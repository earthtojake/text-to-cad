"""``cadgen store`` — inspect, explain and collect the store.

    cadgen store info              what is in the store, by kind, and its size against the cap
    cadgen store why <model.py>    why the gate says stale (or current), clause by clause
    cadgen store where <doc> <ref> which operation at which source line made a part or one of its elements
    cadgen store forget <target>…  drop one model's record or one document's tree entry
    cadgen store gc [--dry-run]    retire old index kinds, mark and sweep unreachable objects
    cadgen store gc --max-size [SIZE]   evict least recently written entries to the cap, then sweep

``why`` is the debugging surface STORE.md describes: it prints the record, then
each gate clause's verdict with its evidence, then the tree's links and
components. ``where`` is its sibling for provenance (README law 20): the one
reader of ``index/provenance``, walking path → output entry → model → record and
provenance entry, with the document's bytes checked against the entry's. Both
are code-side status commands, outside the format/verb mirror of law 6. Stdlib +
the store modules only; neither imports the CAD kernel.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Sequence

from cadgen._internal.doors import STEP_SUFFIXES
from cadgen.store import store_root
from cadgen.store.gate import stale
from cadgen.store.records import read_record, source_for_document
from cadgen.store.trees import get_tree

DEFAULT_PROG = "cadgen store"


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _when(timestamp: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))


def _deferred_lines(deferred: dict) -> list[str]:
    from cadgen.store.gc import NEWER_CADGEN_SECONDS

    days = round(NEWER_CADGEN_SECONDS / 86400)
    return [
        "a newer cadgen writes to this store, and this one cannot tell what that one still needs:",
        *(f"  {what}" for what in deferred["evidence"]),
        f"last written {_when(deferred['lastWritten'])}. That cadgen's `cadgen store gc` collects this store; "
        f"this one leaves it alone until {days} days after that.",
    ]


def _cmd_info(as_json: bool) -> int:
    from cadgen.store.gc import configured_cap, newer_cadgen, scan
    from cadgen.store.paths import INDEX_KINDS

    found = scan()
    deferred = newer_cadgen(found)
    object_bytes = sum(size for size, _ in found.objects.values())
    try:
        cap, cap_error = configured_cap(), None
    except ValueError as error:
        cap, cap_error = None, str(error)
    payload = {
        "root": str(store_root()),
        "objects": {"count": len(found.objects), "bytes": object_bytes},
        "index": {kind: len(found.entries[kind]) for kind in INDEX_KINDS},
        "bytes": found.total,
        "cap": cap,
        "retired": {kind: len(found.entries[kind]) for kind in found.retired},
        "unknown": sorted(found.unknown),
        "deferred": deferred,
    }
    if cap_error:
        payload["capError"] = cap_error
    if as_json:
        print(json.dumps(payload, separators=(",", ":")))
        return 2 if cap_error else 0
    print(f"store  {payload['root']}")
    print(f"objects  {len(found.objects)} ({_human(object_bytes)})")
    if cap_error:
        print(f"size     {_human(found.total)}; {cap_error}")
    elif cap is None:
        print(f"size     {_human(found.total)}; no cap (CADGEN_STORE_MAX=0)")
    else:
        state = "over the cap: the daemon evicts when idle, or `cadgen store gc --max-size` now" if found.total > cap else "under the cap"
        print(f"size     {_human(found.total)} of {_human(cap)} cap; {state}")
    labels = {
        "model": "records",
        "document": "document entries (bytes -> tree)",
        "output": "output entries (path -> model)",
        "provenance": "provenance entries (which operation at which line made each part, face and edge)",
        "result": "results by key (a record and its provenance under the key of everything it was built from)",
        "component": "component entries",
        "bounds": "bounding boxes and leaf layouts",
        "part": "part entries (a part's display mesh and selector table)",
        "drawing": "drawing render payloads",
        "skin": "tube skins (a document's bending tubes, bound)",
        "robot": "robot entries (a description -> its payload and primitive meshes)",
    }
    for kind, count in payload["index"].items():
        print(f"index/{kind:<10} {count} {labels[kind]}")
    for kind, count in payload["retired"].items():
        print(f"index/{kind:<10} {count} entries of a kind this cadgen retired; each goes a week after its last write "
              "(the daemon when idle, or `cadgen store gc`)")
    for kind in payload["unknown"]:
        print(f"index/{kind:<10} a folder this cadgen does not know; it never touches it")
    if deferred:
        for line in _deferred_lines(deferred):
            print(line)
    return 2 if cap_error else 0


def _resolve_models(target: str) -> list[str]:
    """The model identities a ``why`` target names: one for ``script.py::fn`` or a
    document, every model of the file for a bare script."""
    from cadgen.store.index import MODEL_REF_SEP, model_ref, split_model_ref

    if MODEL_REF_SEP in target:
        script, function = split_model_ref(target)
        return [model_ref(script, function)]
    path = Path(target).expanduser()
    if path.suffix.lower() in STEP_SUFFIXES:
        return [source_for_document(path)]
    resolved = path.resolve()
    if resolved.suffix.lower() == ".py":
        from cadgen.metadata import model_function_names

        names = model_function_names(resolved)
        if names:
            return [model_ref(resolved, name) for name in names]
    return [str(resolved)]


def _cmd_why(target: str, as_json: bool) -> int:
    code = 0
    for model in _resolve_models(target):
        code = max(code, _why_one(model, as_json))
    return code


def _closure_file_label(rel: str, names: dict, own: dict) -> str:
    """``lib/geo.py[plane, cyl_along]`` for a sliced file (its reached names,
    the first six), the bare path for a file tracked whole, ``lib/__init__.py
    (must stay absent)`` for a file the imports rely on not existing,
    ``./ (listing, less part.step)`` for a listed folder, less its own outputs,
    and ``SIZE (environment variable)`` for a variable the model reads."""
    from cadgen.store.closure import environment_name

    variable = environment_name(rel)
    if variable is not None:
        return f"{variable} (environment variable)"
    if rel.startswith("!"):
        return f"{rel[1:]} (must stay absent)"
    if rel.endswith("/"):
        return f"{rel} (listing, less {', '.join(own[rel])})" if own.get(rel) else f"{rel} (listing)"
    if rel not in names:
        return rel
    reached = list(names[rel])
    shown = ", ".join(reached[:6]) + (f", +{len(reached) - 6}" if len(reached) > 6 else "")
    return f"{rel}[{shown}]"


def _shown(record: dict | None) -> dict[str, dict]:
    """What each STEP the record names shows, by path, where its verify has not found it
    to be the result (STORE.md §3): ``{"verified": False}`` while it is pending, and the
    differences of a file that shows its own content (``differ``)."""
    from cadgen.store.records import document_entry_for_hash

    shown: dict[str, dict] = {}
    for path, output in ((record or {}).get("outputs") or {}).items():
        digest = str((output or {}).get("sha256") or "")
        entry = document_entry_for_hash(digest) if digest else None
        if entry is not None and (entry.get("verified") is False or entry.get("differ")):
            shown[path] = {key: entry[key] for key in ("verified", "differ") if key in entry}
    return shown


def _why_one(model: str, as_json: bool) -> int:
    verdict = stale(model)
    record = read_record(model)
    tree = get_tree(str(record.get("tree"))) if record and record.get("tree") else None
    shown = _shown(record)
    if as_json:
        print(json.dumps({"model": str(model), "stale": verdict.stale, "clauses": verdict.clauses, "record": record,
                          "documents": shown}, separators=(",", ":")))
        return 0 if not verdict.stale else 1
    print(f"model   {model}")
    print(f"verdict {'STALE' if verdict.stale else 'current'}  ({verdict.reason()})")
    for clause in verdict.clauses:
        number = clause.get("clause")
        mark = "x" if clause.get("stale") else "ok"
        if number == 1:
            print(f"  [{mark}] 1 record {'missing' if clause.get('stale') else 'present'}")
        elif number == 2:
            why = clause.get("why") or f"{clause.get('files', 0)} files unchanged"
            print(f"  [{mark}] 2 closure {why}")
        elif number == 3:
            children = clause.get("children") or []
            print(f"  [{mark}] 3 children ({len(children)})")
            for child in children:
                cmark = "x" if child.get("stale") else "ok"
                print(f"        [{cmark}] {child.get('model')}  key {str(child.get('recorded'))[:12]}  now {str(child.get('current'))[:12]}  {child.get('why') or ''}")
        elif number == 4:
            print(f"  [{mark}] 4 tree {str(clause.get('tree'))[:12]} {'complete' if not clause.get('stale') else clause.get('why')}")
        elif number == 5:
            outputs = clause.get("outputs") or []
            print(f"  [{mark}] 5 outputs ({len(outputs)})")
            for output in outputs:
                omark = "x" if output.get("stale") else "ok"
                print(f"        [{omark}] {output.get('path')}  {output.get('why') or ''}")
                document = shown.get(str(output.get("path")))
                if document is not None and document.get("differ"):
                    print(f"              shows its own content: {'; '.join(document['differ'])}")
                elif document is not None:
                    print("              verify pending")
        elif number == 6:
            print(f"  [{mark}] 6 producer {clause.get('why') or 'this cadgen and kernel'}")
    if record:
        print(f"key     {str(record.get('key'))[:12]}")
        closure = record.get("closure") or {}
        names = closure.get("names") or {}
        own = closure.get("own") or {}
        print(f"closure {str(closure.get('hash'))[:12]}  files: {', '.join(_closure_file_label(rel, names, own) for rel in closure.get('files') or [])}")
    if tree:
        print(f"tree    components {len(tree.get('components') or {})}  occurrences {len(tree.get('occurrences') or [])}  links {len(tree.get('links') or [])}")
        for link in tree.get("links") or []:
            print(f"        link {link.get('name')} -> {str(link.get('tree'))[:12]}")
    return 0 if not verdict.stale else 1


def _cmd_where(document: str, ref: str, as_json: bool) -> int:
    """0 when the store knows which feature made what the ref names, 1 when it
    does not (no entry, other bytes, a body no feature made), 2 for a ref that
    cannot be read or names another file."""
    import dataclasses

    from cadgen.store.provenance import describe, where

    try:
        answer = where(document, ref)
    except ValueError as error:
        print(f"cadgen store where: {error}", file=sys.stderr)
        return 2
    if as_json:
        print(json.dumps(dataclasses.asdict(answer), separators=(",", ":")))
    else:
        for line in describe(answer):
            print(line)
    return 0 if answer.known else 1


def _cmd_gc(dry_run: bool, grace_hours: float, max_size: str | None, as_json: bool) -> int:
    from cadgen.store.gc import collect, configured_cap, parse_size

    max_bytes = None
    if max_size is not None:
        try:
            max_bytes = configured_cap() if max_size == "" else (parse_size(max_size) or None)
        except ValueError as error:
            print(f"cadgen store gc: {error}", file=sys.stderr)
            return 2
    report = collect(grace_seconds=grace_hours * 3600.0, dry_run=dry_run, max_bytes=max_bytes)
    payload = {
        "dryRun": report.dry_run,
        "records": report.records,
        "reachable": report.reachable,
        "keptByGrace": report.kept_by_grace,
        "removed": report.removed,
        "removedBytes": report.removed_bytes,
        "retired": report.retired,
        "obsolete": report.obsolete,
        "retiredBytes": report.retired_bytes,
        "bytesBefore": report.bytes_before,
        "bytesAfter": report.bytes_after,
        "deferred": report.deferred,
    }
    if max_size is not None:
        payload.update({"cap": report.cap, "evicted": report.evicted, "evictedBytes": report.evicted_bytes,
                        "protectedBytes": report.protected_bytes})
    if as_json:
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    if report.deferred:
        for line in _deferred_lines(report.deferred):
            print(line)
        print("nothing was removed")
        return 0
    verb = "would remove" if dry_run else "removed"
    for kind, count in sorted(report.retired.items()):
        print(f"index/{kind} is retired: {verb} {count} entries a week old, then the objects only they named")
    for kind, count in sorted(report.obsolete.items()):
        print(f"{kind} entries another version of cadgen wrote are obsolete: {verb} {count}, then the objects only they named")
    if max_size is not None:
        if report.cap is None:
            print("no cap (0): nothing is evicted")
        else:
            parts = ", ".join(f"{count} {kind}" for kind, count in sorted(report.evicted.items())) or "nothing"
            evict_verb = "would evict" if dry_run else "evicted"
            print(f"cap {_human(report.cap)}: {evict_verb} {parts}, least recently written first; "
                  f"records and documents hold {_human(report.protected_bytes)}")
    print(f"{report.records} records, {report.reachable} reachable objects, {report.kept_by_grace} kept by grace; {verb} {report.removed} objects ({_human(report.removed_bytes)})")
    after = "would be" if dry_run else "now"
    print(f"store {_human(report.bytes_before)}, {after} {_human(report.bytes_after)}")
    return 0


def _cmd_forget(targets: Sequence[str], dry_run: bool, as_json: bool) -> int:
    from cadgen.store.forget import describe, forget

    reports = [forget(target, dry_run=dry_run) for target in targets]
    if as_json:
        print(json.dumps({"dryRun": dry_run, "targets": reports}, separators=(",", ":")))
        return 0
    for report in reports:
        for line in describe(report):
            print(line)
    return 0


def build_parser(prog: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog or DEFAULT_PROG, description="Inspect, explain and collect the cadgen store.")
    sub = parser.add_subparsers(dest="command", required=True)
    info = sub.add_parser("info", help="what is in the store, by kind")
    info.add_argument("--json", action="store_true")
    why = sub.add_parser("why", help="why the gate says a model is stale (or current)")
    why.add_argument("model", help="a model script, script.py::function for one model of a file holding several, or a generated .step (the store remembers which model wrote it)")
    why.add_argument("--json", action="store_true")
    where = sub.add_parser(
        "where",
        help="which operation at which source line made a part, a face, an edge or a vertex of a generated STEP",
        description=(
            "The build's account of its code (provenance): for a part, the feature that made its body; for a "
            "face, an edge or a vertex, the feature its name says made it and the one that last modified it, "
            "each as file:line in function (operation), with the features it was given. A feature is one "
            "kernel construction the model's code called. The ref is one the CAD viewer copies or read_scene "
            "resolves: #o:<token>, #o:<token>/f:<name>, #label/e:<name>. Answered from the model's "
            "provenance entry, written with its record; for other bytes, or without an entry, it says it "
            "does not know."
        ),
    )
    where.add_argument("document", help="a STEP file a model of this cadgen wrote")
    where.add_argument("ref", help="an occurrence, face, edge or vertex ref in that document")
    where.add_argument("--json", action="store_true")
    forget = sub.add_parser(
        "forget",
        help="drop one model's record, or one document's tree entry, so the next run or open redoes it",
        description=(
            "A surgical reset. A model script drops its record (the next run rebuilds it; children and parents "
            "are untouched). A document (.step/.dxf/mesh) drops its bytes' tree entry so the next open or door "
            "call compiles it again, and the record that wrote it. Objects are never deleted (that is gc); an "
            "unknown target is 'nothing to forget'."
        ),
    )
    forget.add_argument("targets", nargs="+", metavar="TARGET", help="a model script or a document path")
    forget.add_argument("--dry-run", action="store_true", help="report what would be forgotten")
    forget.add_argument("--json", action="store_true")
    gc = sub.add_parser(
        "gc",
        help="retire old index kinds, mark and sweep unreachable objects; with --max-size, evict to a cap first",
        description=(
            "Removes the entries of the index kinds this cadgen no longer defines (index/op, index/surface, "
            "index/selector, index/mesh) once a week old, and every object nothing reaches: "
            "not a record's or a document's tree, not named by a part, component, bounds, drawing, skin or robot "
            "entry, and not written or claimed within the grace window. --max-size first evicts those derived "
            "entries, least recently written first, until the store fits 80% of the cap (the newest keep a "
            "fifth of the cap when records and documents leave less room); records, document entries, "
            "output entries and provenance entries are never evicted. The daemon does the same when idle. A store a newer cadgen "
            "wrote to in the last 30 days is left to that cadgen, and nothing is removed."
        ),
    )
    gc.add_argument("--dry-run", action="store_true", help="report what would go; delete nothing")
    gc.add_argument("--grace-hours", type=float, default=1.0, help="keep objects touched within this window (default 1h)")
    gc.add_argument(
        "--max-size", nargs="?", const="", default=None, metavar="SIZE",
        help="evict to this cap (20G, 500M, 0 for none) before sweeping; bare --max-size uses CADGEN_STORE_MAX (default 20G)",
    )
    gc.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(list(argv) if argv is not None else sys.argv[1:])
    if args.command == "info":
        return _cmd_info(bool(args.json))
    if args.command == "why":
        return _cmd_why(args.model, bool(args.json))
    if args.command == "where":
        return _cmd_where(args.document, args.ref, bool(args.json))
    if args.command == "forget":
        return _cmd_forget(list(args.targets), bool(args.dry_run), bool(args.json))
    if args.command == "gc":
        return _cmd_gc(bool(args.dry_run), float(args.grace_hours), args.max_size, bool(args.json))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
