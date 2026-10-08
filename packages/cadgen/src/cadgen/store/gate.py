"""The gate: one ``stale(model)`` for every model, root or leaf.

``stale(x)`` is true if any of:

1. no record;
2. ``sha256(closure.files as they are now) != closure.hash`` — a file the
   record sliced (``closure.names``) keeps its recorded slice while its
   whole-file hash is the recorded one (``closure.wholes``) and is re-sliced
   by those names when it moved, every other file hashed whole — or a constant
   the model imported by value (``record.constants``) no longer hashes the same;
3. for any recorded child: ``stale(child)`` **or** its current tree hash != the
   pinned hash;
4. the tree object or any object it (transitively) references is missing;
5. any declared output does not match ``outputs``.

Evaluated once in the requesting process (fast, no kernel import) and again on
the worker immediately before building. Recursion in (3) is memoized per request.
Clauses 4 and 5 verify an object or an output once per process, while its file
keeps the settled identity that verification observed (STORE.md §4).
Mesh tolerances and argv flags are not inputs.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from cadgen._internal import filetrace
from cadgen.store.closure import changed_constant, current_closure_hash
from cadgen.store.index import resolve_model_ref, split_model_ref
from cadgen.store.records import read_record
from cadgen.store.trees import _stamp, _stamp_is_settled, tree_complete


@dataclass
class Verdict:
    model: str
    stale: bool
    clauses: list[dict[str, Any]] = field(default_factory=list)
    #: The source's closure hash as it is NOW (the script's own sha when there is no
    #: record to name a closure): what in-flight coalescing keys on.
    closure: str | None = None
    #: Exact result from the record this verdict checked, never a later lookup.
    tree: str | None = None

    def reason(self) -> str:
        """The first stale clause as a phrase: ``no record``, ``closure changed: <file>``,
        ``constant changed: <NAME> in <file>``, ``child stale: <child.py>``,
        ``child result moved: <child.py>``, ``tree or components missing``,
        ``never written: <path>`` / ``output missing: <path>`` / ``output changed: <path>``."""
        for clause in self.clauses:
            if not clause.get("stale"):
                continue
            number = clause.get("clause")
            if number == 3:
                for child in clause.get("children") or []:
                    if child.get("stale"):
                        name = Path(str(child.get("model") or "")).name or "?"
                        return f"{child.get('why') or 'child stale'}: {name}"
            if number == 5:
                for output in clause.get("outputs") or []:
                    if output.get("stale"):
                        why = str(output.get("why") or "output changed")
                        label = {"missing": "output missing", "changed": "output changed"}.get(why, why)
                        return f"{label}: {output.get('path')}"
            return str(clause.get("why") or f"clause {number}")
        return "current"


# One rebuild evaluates the gate many times over the same files, and a large
# assembly's STEP is hundreds of megabytes. A digest is reused while its file
# keeps the identity -- device, inode, size, mtime and ctime -- observed on both
# sides of the read that produced it, once that read is settled: the rule the
# metadata capture applies to store objects (STORE.md §10). Deletion,
# replacement, truncation and any rewrite a later stat can see hash it again.
_DIGESTS_CAPACITY = 4096
_DIGESTS: OrderedDict[str, tuple[tuple, str]] = OrderedDict()
_DIGESTS_LOCK = threading.Lock()


def _file_stamp(path: Path) -> tuple | None:
    """The fingerprint ``trees._object_stamp`` takes, of a file outside the store."""
    try:
        return _stamp(str(path), Path(path))
    except OSError:
        return None


def _sha256_file(path: Path) -> str | None:
    key = str(path)
    before = _file_stamp(path)
    with _DIGESTS_LOCK:
        cached = _DIGESTS.get(key)
        if cached is not None:
            if cached[0] == before:
                _DIGESTS.move_to_end(key)
                return cached[1]
            del _DIGESTS[key]
    digest = _hash_file(path)
    after = _file_stamp(path)
    if digest is not None and before is not None and before == after and _stamp_is_settled(after):
        with _DIGESTS_LOCK:
            _DIGESTS[key] = (after, digest)
            if len(_DIGESTS) > _DIGESTS_CAPACITY:
                _DIGESTS.popitem(last=False)
    return digest


def remember_renamed_digest(path: Path, digest: str, staged: tuple | None) -> None:
    """Seed the memo for ``path``, which this process wrote under another name,
    hashed as ``digest``, and renamed into place.

    ``staged`` is the written file's stamp (:func:`file_stamp`) taken just
    before the rename. A rename keeps a file's device, inode, size and mtime and
    moves only its ctime, so a ``path`` that still shows the staged identity is
    those bytes, and nothing reads them again. The staged stamp must already be
    settled, so any write after it would have shown; otherwise this does
    nothing and the next lookup reads the file."""
    if staged is None or not _stamp_is_settled(staged):
        return
    after = _file_stamp(path)
    if after is None or after[1:5] != staged[1:5]:
        return
    with _DIGESTS_LOCK:
        _DIGESTS[str(path)] = (after, digest)
        _DIGESTS.move_to_end(str(path))
        if len(_DIGESTS) > _DIGESTS_CAPACITY:
            _DIGESTS.popitem(last=False)


def file_stamp(path: Path) -> tuple | None:
    """The identity :func:`remember_renamed_digest` compares, or None when absent."""
    return _file_stamp(path)


def _hash_file(path: Path) -> str | None:
    from cadgen._internal.atomic_replace import open_with_ladder

    digest = hashlib.sha256()
    try:
        # Through the ladder: a peer build publishing the same model may be
        # renaming over this file, which Windows refuses an open for (STORE.md §7).
        with open_with_ladder(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def stale(model: Path | str, *, memo: dict[str, Verdict] | None = None) -> Verdict:
    # What the gate reads -- a child's files and outputs, inside a parent's build --
    # is its own bookkeeping, never the build's input.
    with filetrace.paused():
        return _stale(model, memo=memo)


def _stale(model: Path | str, *, memo: dict[str, Verdict] | None = None) -> Verdict:
    memo = memo if memo is not None else {}
    key = resolve_model_ref(model)
    script, _function = split_model_ref(key)
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
        verdict.closure = _sha256_file(script)
        return verdict
    clauses.append({"clause": 1, "stale": False})
    verdict.tree = str(record.get("tree") or "") or None

    # Clause 2's left-hand side: the record's closure entries as they hash now.
    closure = record.get("closure") or {}
    recorded_hash = str(closure.get("hash") or "")
    files = list(closure.get("files") or [])
    if closure.get("static"):
        # A closure with no source files to re-hash (a re-emitted document: its
        # source is another document's bytes plus an annotation, both compared
        # by the door that owns it). The hash stands as recorded.
        now: str | None = recorded_hash
    elif files:
        # Sliced files keep their recorded slice while their whole-file hash is
        # unchanged, and are re-sliced by their recorded names when it moved; the
        # rest are hashed whole.
        now = current_closure_hash(script, files, dict(closure.get("names") or {}),
                                   shas=closure.get("shas") or {}, wholes=closure.get("wholes") or {})
    else:
        now = None
    verdict.closure = now or _sha256_file(script)
    if not recorded_hash or now != recorded_hash:
        clauses.append(
            {
                "clause": 2,
                "stale": True,
                "why": _closure_why(script, closure, now),
                "recorded": recorded_hash,
                "current": now,
            }
        )
        verdict.stale = True
    else:
        # Constants by value: a literal imported from a model file is compared as
        # a value, not as that file's bytes (the file itself is not in the closure).
        constant = changed_constant(script, record.get("constants") or {})
        if constant is not None:
            rel, _, name = str(constant).rpartition(":")
            clauses.append({"clause": 2, "stale": True, "why": f"constant changed: {name} in {rel}", "constant": constant})
            verdict.stale = True
        else:
            clauses.append({"clause": 2, "stale": False, "files": len(files)})

    child_clauses: list[dict[str, Any]] = []
    for child in record.get("children") or []:
        child_model = str((child or {}).get("model") or "")
        pinned = str((child or {}).get("tree") or "")
        child_verdict = stale(child_model, memo=memo) if child_model else None
        current_tree = child_verdict.tree if child_verdict is not None else None
        moved = current_tree != pinned
        child_stale = child_verdict is None or child_verdict.stale or moved
        child_clauses.append(
            {
                "model": child_model,
                "stale": child_stale,
                "why": (
                    "child stale" if child_verdict is None or child_verdict.stale
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
    clauses.append({"clause": 4, "stale": not complete, "why": None if complete else "tree or components missing", "tree": tree or None})
    if not complete:
        verdict.stale = True

    output_clauses: list[dict[str, Any]] = []
    for path, meta in (record.get("outputs") or {}).items():
        expected = str((meta or {}).get("sha256") or "")
        actual = _sha256_file(Path(path))
        ok = bool(expected) and actual == expected
        why = None if ok else "never written" if not expected else "missing" if actual is None else "changed"
        output_clauses.append({"path": path, "stale": not ok, "why": why})
        if not ok:
            verdict.stale = True
    clauses.append({"clause": 5, "stale": any(c["stale"] for c in output_clauses), "outputs": output_clauses})
    return verdict


def _closure_why(script: Path, closure: Mapping[str, Any], now: str | None) -> str:
    """Clause 2's phrase: name the files that moved when the record can say."""
    from cadgen.store.closure import changed_closure_files, source_files

    changed = changed_closure_files(script, closure.get("shas") or {}, closure.get("names") or {},
                                    closure.get("wholes") or {})
    if now is None:
        # Only a file can be missing: an absent, roots or listing entry changed.
        missing = [rel for rel in source_files(changed) if not (Path(script).resolve().parent / rel).exists()]
        return f"closure file missing: {', '.join(missing or changed)}" if (missing or changed) else "closure file missing"
    return f"closure changed: {', '.join(changed)}" if changed else "closure changed"


def is_current(model: Path | str) -> bool:
    return not stale(model).stale
