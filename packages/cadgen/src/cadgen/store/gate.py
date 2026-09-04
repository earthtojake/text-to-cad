"""The gate: one ``stale(model)`` for every model, root or leaf.

``stale(x)`` is true if any of:

1. no record;
2. ``sha256(closure.files as they are now) != closure.hash``, or a constant the
   model imported by value (``record.constants``) no longer hashes the same;
3. for any recorded child: ``stale(child)`` **or** its current tree hash != the
   pinned hash;
4. the tree object or any object it (transitively) references is missing;
5. any declared output does not match ``outputs``.

Evaluated once in the requesting process (fast, no kernel import) and again on
the worker immediately before building. Recursion in (3) is memoized per request
through ``memo``. Mesh tolerances and argv flags are not inputs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cadgen.store.closure import changed_constant, current_closure_hash
from cadgen.store.records import read_record
from cadgen.store.trees import tree_complete


@dataclass
class Verdict:
    model: str
    stale: bool
    clauses: list[dict[str, Any]] = field(default_factory=list)
    #: The source's closure hash as it is NOW (the script's own sha when there is no
    #: record to name a closure): what in-flight coalescing keys on.
    closure: str | None = None

    def reason(self) -> str:
        for clause in self.clauses:
            if clause.get("stale"):
                return str(clause.get("why") or clause.get("clause"))
        return "current"


def _sha256_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def stale(model: Path | str, *, memo: dict[str, Verdict] | None = None) -> Verdict:
    memo = memo if memo is not None else {}
    try:
        key = str(Path(model).expanduser().resolve())
    except (OSError, RuntimeError):
        key = str(model)
    cached = memo.get(key)
    if cached is not None:
        return cached
    verdict = Verdict(model=key, stale=False)
    memo[key] = verdict  # cycle guard: a self-referencing graph reads "current" mid-walk
    clauses = verdict.clauses

    record = read_record(key)
    if record is None:
        clauses.append({"clause": 1, "stale": True, "why": "no record"})
        verdict.stale = True
        verdict.closure = _sha256_file(Path(key))
        return verdict
    clauses.append({"clause": 1, "stale": False})

    closure = record.get("closure") or {}
    recorded_hash = str(closure.get("hash") or "")
    files = list(closure.get("files") or [])
    if closure.get("static"):
        # A closure with no source files to re-hash (a re-emitted document: its
        # source is another document's bytes plus an annotation, both compared
        # by the door that owns it). The hash stands as recorded.
        now = recorded_hash
    else:
        now = current_closure_hash(Path(key), files) if files else None
    verdict.closure = now or _sha256_file(Path(key))
    if not recorded_hash or now != recorded_hash:
        clauses.append(
            {
                "clause": 2,
                "stale": True,
                "why": "a closure file is missing" if now is None else "source changed",
                "recorded": recorded_hash,
                "current": now,
            }
        )
        verdict.stale = True
    else:
        # Constants by value: a literal imported from a model file is compared as
        # a value, not as that file's bytes (the file itself is not in the closure).
        constant = changed_constant(Path(key), record.get("constants") or {})
        if constant is not None:
            clauses.append({"clause": 2, "stale": True, "why": f"constant changed: {constant}", "constant": constant})
            verdict.stale = True
        else:
            clauses.append({"clause": 2, "stale": False, "files": len(files)})

    child_clauses: list[dict[str, Any]] = []
    for child in record.get("children") or []:
        child_model = str((child or {}).get("model") or "")
        pinned = str((child or {}).get("tree") or "")
        child_verdict = stale(child_model, memo=memo) if child_model else None
        current_tree = None
        child_record = read_record(child_model) if child_model else None
        if child_record is not None:
            current_tree = str(child_record.get("tree") or "")
        moved = current_tree != pinned
        child_stale = child_verdict is None or child_verdict.stale or moved
        child_clauses.append(
            {
                "model": child_model,
                "stale": child_stale,
                "why": (
                    "child is stale" if child_verdict is None or child_verdict.stale
                    else "child result moved" if moved else None
                ),
                "pinned": pinned,
                "current": current_tree,
            }
        )
        if child_stale:
            verdict.stale = True
    clauses.append({"clause": 3, "stale": any(c["stale"] for c in child_clauses), "children": child_clauses})

    if "tree" in record and record.get("tree") is None:
        # A drawing (@dxf): its output is the .dxf and it has no tree. Vacuous.
        tree, complete = "", True
    else:
        tree = str(record.get("tree") or "")
        complete = bool(tree) and tree_complete(tree)
    clauses.append({"clause": 4, "stale": not complete, "why": None if complete else "tree or component object missing", "tree": tree or None})
    if not complete:
        verdict.stale = True

    output_clauses: list[dict[str, Any]] = []
    for path, meta in (record.get("outputs") or {}).items():
        expected = str((meta or {}).get("sha256") or "")
        actual = _sha256_file(Path(path))
        ok = bool(expected) and actual == expected
        output_clauses.append({"path": path, "stale": not ok, "why": None if ok else ("missing" if actual is None else "changed")})
        if not ok:
            verdict.stale = True
    clauses.append({"clause": 5, "stale": any(c["stale"] for c in output_clauses), "outputs": output_clauses})
    return verdict


def is_current(model: Path | str) -> bool:
    return not stale(model).stale
