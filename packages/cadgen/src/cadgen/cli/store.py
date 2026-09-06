"""``cadgen store`` — inspect, explain and collect the store.

    cadgen store info              what is in the store, by kind
    cadgen store why <model.py>    why the gate says stale (or current), clause by clause
    cadgen store forget <target>…  drop one model's record or one document's tree entry
    cadgen store gc [--dry-run]    mark and sweep unreachable objects

``why`` is the debugging surface STORE.md describes: it prints the record, then
each gate clause's verdict with its evidence, then the tree's links and
components. Stdlib + the store modules only; it never imports the CAD kernel.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from cadgen.store import store_root
from cadgen.store.gate import stale
from cadgen.store.index import iter_entries
from cadgen.store.objects import iter_objects
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


def _cmd_info(as_json: bool) -> int:
    objects = 0
    object_bytes = 0
    for _digest, path in iter_objects():
        objects += 1
        try:
            object_bytes += path.stat().st_size
        except OSError:
            pass
    from cadgen.store.paths import INDEX_KINDS

    counts = {kind: sum(1 for _ in iter_entries(kind)) for kind in INDEX_KINDS}
    payload = {
        "root": str(store_root()),
        "objects": {"count": objects, "bytes": object_bytes},
        "index": counts,
    }
    if as_json:
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    print(f"store  {payload['root']}")
    print(f"objects  {objects} ({_human(object_bytes)})")
    labels = {
        "model": "records",
        "document": "document entries (bytes -> tree)",
        "output": "output entries (path -> model)",
        "component": "component entries",
        "op": "op-memo entries",
        "mesh": "mesh entries",
    }
    for kind, count in counts.items():
        print(f"index/{kind:<10} {count} {labels[kind]}")
    return 0


def _resolve_models(target: str) -> list[str]:
    """The model identities a ``why`` target names: one for ``script.py::fn`` or a
    document, every model of the file for a bare script."""
    from cadgen.store.index import MODEL_REF_SEP, model_ref, split_model_ref

    if MODEL_REF_SEP in target:
        script, function = split_model_ref(target)
        return [model_ref(script, function)]
    path = Path(target).expanduser()
    if path.suffix.lower() in {".step", ".stp"}:
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


def _why_one(model: str, as_json: bool) -> int:
    verdict = stale(model)
    record = read_record(model)
    tree = get_tree(str(record.get("tree"))) if record and record.get("tree") else None
    if as_json:
        print(json.dumps({"model": str(model), "stale": verdict.stale, "clauses": verdict.clauses, "record": record}, separators=(",", ":")))
        return 0 if not verdict.stale else 1
    print(f"model   {model}")
    print(f"verdict {'STALE' if verdict.stale else 'current'}  ({verdict.reason()})")
    for clause in verdict.clauses:
        number = clause.get("clause")
        mark = "x" if clause.get("stale") else "ok"
        if number == 1:
            print(f"  [{mark}] 1 record {'missing' if clause.get('stale') else 'present'}")
        elif number == 2:
            detail = clause.get("why") or f"{clause.get('files', 0)} files unchanged"
            print(f"  [{mark}] 2 closure {detail}")
        elif number == 3:
            children = clause.get("children") or []
            print(f"  [{mark}] 3 children ({len(children)})")
            for child in children:
                cmark = "x" if child.get("stale") else "ok"
                print(f"        [{cmark}] {child.get('model')}  pinned {str(child.get('pinned'))[:12]}  current {str(child.get('current'))[:12]}  {child.get('why') or ''}")
        elif number == 4:
            print(f"  [{mark}] 4 tree {str(clause.get('tree'))[:12]} {'complete' if not clause.get('stale') else clause.get('why')}")
        elif number == 5:
            outputs = clause.get("outputs") or []
            print(f"  [{mark}] 5 outputs ({len(outputs)})")
            for output in outputs:
                omark = "x" if output.get("stale") else "ok"
                print(f"        [{omark}] {output.get('path')}  {output.get('why') or ''}")
    if record:
        closure = record.get("closure") or {}
        print(f"closure {str(closure.get('hash'))[:12]}  files: {', '.join(closure.get('files') or [])}")
    if tree:
        print(f"tree    components {len(tree.get('components') or {})}  occurrences {len(tree.get('occurrences') or [])}  links {len(tree.get('links') or [])}")
        for link in tree.get("links") or []:
            print(f"        link {link.get('name')} -> {str(link.get('tree'))[:12]}")
    return 0 if not verdict.stale else 1


def _cmd_gc(dry_run: bool, grace_hours: float, as_json: bool) -> int:
    from cadgen.store.gc import collect

    report = collect(grace_seconds=grace_hours * 3600.0, dry_run=dry_run)
    payload = {
        "dryRun": report.dry_run,
        "records": report.records,
        "reachable": report.reachable,
        "keptByGrace": report.kept_by_grace,
        "removed": report.removed,
        "removedBytes": report.removed_bytes,
    }
    if as_json:
        print(json.dumps(payload, separators=(",", ":")))
        return 0
    verb = "would remove" if dry_run else "removed"
    print(f"{report.records} records, {report.reachable} reachable objects, {report.kept_by_grace} kept by grace; {verb} {report.removed} objects ({_human(report.removed_bytes)})")
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
    gc = sub.add_parser("gc", help="mark and sweep unreachable objects")
    gc.add_argument("--dry-run", action="store_true")
    gc.add_argument("--grace-hours", type=float, default=1.0, help="keep objects touched within this window (default 1h)")
    gc.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None, prog: str | None = None) -> int:
    args = build_parser(prog).parse_args(list(argv) if argv is not None else sys.argv[1:])
    if args.command == "info":
        return _cmd_info(bool(args.json))
    if args.command == "why":
        return _cmd_why(args.model, bool(args.json))
    if args.command == "forget":
        return _cmd_forget(list(args.targets), bool(args.dry_run), bool(args.json))
    if args.command == "gc":
        return _cmd_gc(bool(args.dry_run), float(args.grace_hours), bool(args.json))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
