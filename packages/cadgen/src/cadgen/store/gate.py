"""The gate: one ``stale(model)`` for every model, root or leaf.

``stale(x)`` is true if any of:

1. no record;
2. ``sha256(closure.files as they are now) != closure.hash`` — a file the
   record sliced (``closure.names``) keeps its recorded slice while its
   whole-file hash is the recorded one (``closure.wholes``) and is re-sliced
   by those names when it moved, every other file hashed whole, a listed
   folder by its entry names less the model's own outputs (``closure.own``), a
   file recorded absent by whether it still is, an environment variable the
   model read by its value in this process's environment (a daemon job's is
   its caller's) — or a constant the model imported by value
   (``record.constants``) no longer hashes the same;
3. for any recorded child: its stored result does not stand (``child stale``)
   **or** stands under another key than the one recorded (``child rebuilt``) -- a
   child stands under its record's key or, once its source moved on and came back,
   under the key its source has now when a stored result answers for it (its
   candidate, below), which its parent's hit restores;
4. the tree object or any object it (transitively) references is missing;
5. any declared output does not match ``outputs``;
6. the producer that built the record -- cadgen, the kernel -- is not this one.

A model's stored result is in the store when clauses 1–4 and 6 hold
(``Verdict.stored``, the record's key). It STANDS when clause 5 then finds at most a
STEP, its sidecar or a declared mesh to owe -- each written again from the stored
result and its record, never by a run: ``Verdict.key`` is that key, a decorated call
takes the result as it is, exporting what the files owe without running the body,
and a parent depends on the child by it (clause 3); a missing drawing is a run's, as
is anything else the gate finds, and a child that owes one does not stand for its
parent, whose run calls it. The verdict also names the key the source has
NOW (``Verdict.candidate``): what a result would be keyed by if this source were
built, from this model, the record's closure as it hashes now, its constants as
they read now, its children's keys as they stand now and this producer -- what a
stored result is looked up by before the body runs (``store.results``); a record
whose result is in the store is that candidate itself, never restored over what it
owes a run for.

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
from cadgen._internal.source_sidecar import SOURCE_SIDECAR_SUFFIX
from cadgen.store.closure import current_closure_hash
from cadgen.store.index import resolve_model_ref, split_model_ref
from cadgen.store.records import read_record
from cadgen.store.trees import _stamp, _stamp_is_settled, tree_complete


#: The outputs a standing result still owes without a run (``generation._hit``): its
#: STEP, exported again from the stored result, and its declared meshes, cut again --
#: and the STEP's sidecar, ``<document>.json``, written again from the record.
_EXPORTED_SUFFIXES = frozenset({".step", ".stp", ".stl", ".glb", ".3mf"})


def _exported(path: str) -> bool:
    """Whether a standing result owes ``path`` without a run (``_EXPORTED_SUFFIXES``). A
    drawing, or any other output, comes only from a run."""
    name = Path(path).name.lower()
    if name.endswith(SOURCE_SIDECAR_SUFFIX):
        name = name[: -len(SOURCE_SIDECAR_SUFFIX)]
    return Path(name).suffix in _EXPORTED_SUFFIXES


@dataclass
class Verdict:
    model: str
    stale: bool
    clauses: list[dict[str, Any]] = field(default_factory=list)
    #: Exact result from the record this verdict checked, never a later lookup.
    tree: str | None = None
    #: The record's key while its stored result is in the store (the module docstring:
    #: clauses 1-4 and 6); None when the source has moved on from it.
    stored: str | None = None
    #: ``stored`` while the files owe at most an export (the module docstring); None
    #: when the model must run.
    key: str | None = None
    #: Every verdict this evaluation took, by model ref -- this one and its descendants'
    #: (clause 3), each asked once -- for a caller that heals what a current model's
    #: children owe without asking again (``generation._hit``).
    descendants: dict[str, "Verdict"] = field(default_factory=dict, repr=False)
    #: The key the source has now, when the record can say (the module docstring);
    #: None without a record, when a child's result does not stand, or when a
    #: constant's module cannot be read.
    candidate: str | None = None

    def reason(self) -> str:
        """The first stale clause as a phrase: ``no record``, ``closure changed: <file>``,
        ``closure changed: <file> appeared``, ``environment variable <NAME> changed``,
        ``constant changed: <NAME> in <file>``, ``child stale: <child.py>``,
        ``child rebuilt: <child.py>``, ``tree or components missing``,
        ``never written: <path>`` / ``output missing: <path>`` / ``output changed: <path>``,
        ``producer changed: <name> <recorded> -> <now>``."""
        for clause in self.clauses:
            if not clause.get("stale"):
                continue
            number = clause.get("clause")
            if number == 3:
                for child in clause.get("children") or []:
                    if child.get("stale"):
                        name = Path(str(child.get("model") or "").split("::", 1)[0]).name or "?"
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
    memo = memo if memo is not None else {}
    with filetrace.paused():
        verdict = _stale(model, memo=memo)
    verdict.descendants = memo
    return verdict


def _stale(model: Path | str, *, memo: dict[str, Verdict] | None = None) -> Verdict:
    memo = memo if memo is not None else {}
    ref = resolve_model_ref(model)
    script, _function = split_model_ref(ref)
    cached = memo.get(ref)
    if cached is not None:
        return cached
    verdict = Verdict(model=ref, stale=False)
    memo[ref] = verdict  # cycle guard: a self-referencing graph reads "current" mid-walk
    clauses = verdict.clauses

    record = read_record(ref)
    if record is None:
        clauses.append({"clause": 1, "stale": True, "why": "no record"})
        verdict.stale = True
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
                                   shas=closure.get("shas") or {}, wholes=closure.get("wholes") or {},
                                   own=closure.get("own") or {})
    else:
        now = None
    # The constants as they read now, by recorded name, each module imported once
    # kernel-free: clause 2 compares them, and the candidate key is made of them.
    recorded_constants = record.get("constants") or {}
    constants_now = _constants_now(script, recorded_constants)
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
        # A module gone, or a name no longer bound to a literal, counts as changed.
        constant = next((f"{rel}:{name}" for rel, names in sorted(recorded_constants.items())
                         for name, recorded in sorted(names.items())
                         if (constants_now.get(rel) or {}).get(name) != recorded), None)
        if constant is not None:
            rel, _, name = str(constant).rpartition(":")
            clauses.append({"clause": 2, "stale": True, "why": f"constant changed: {name} in {rel}", "constant": constant})
            verdict.stale = True
        else:
            clauses.append({"clause": 2, "stale": False, "files": len(files)})

    # Clause 3, by key: a child's stored result must stand, under the very key the
    # parent composed. A child rebuilt from an edited source stands under another key
    # -- whatever its geometry -- and the parent follows it (STORE.md §4); one whose
    # source came back to a state already built stands under that state's key before
    # anything restores it (_standing_key).
    child_clauses: list[dict[str, Any]] = []
    child_keys: list[str] = []
    for child in record.get("children") or []:
        child_model = str((child or {}).get("model") or "")
        recorded = str((child or {}).get("key") or "")
        child_verdict = stale(child_model, memo=memo) if child_model else None
        current_key = _standing_key(child_verdict) if child_verdict is not None else None
        rebuilt = current_key is not None and current_key != recorded
        child_stale = current_key is None or rebuilt
        child_clauses.append(
            {
                "model": child_model,
                "stale": child_stale,
                "why": "child stale" if current_key is None else "child rebuilt" if rebuilt else None,
                "recorded": recorded,
                "current": current_key,
            }
        )
        if current_key is not None:
            child_keys.append(current_key)
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
    owed_a_run = False
    for path, meta in (record.get("outputs") or {}).items():
        expected = str((meta or {}).get("sha256") or "")
        actual = _sha256_file(Path(path))
        ok = bool(expected) and actual == expected
        why = None if ok else "never written" if not expected else "missing" if actual is None else "changed"
        output_clauses.append({"path": path, "stale": not ok, "why": why})
        if not ok:
            verdict.stale = True
            # A STEP, its sidecar or a declared mesh is written again from the stored
            # result and its record; any other output (a drawing) comes only from a run.
            owed_a_run = owed_a_run or not _exported(path)
    clauses.append({"clause": 5, "stale": any(c["stale"] for c in output_clauses), "outputs": output_clauses})

    from cadgen.store.results import producer_versions, result_key

    recorded_producer = {str(k): str(v) for k, v in (record.get("producer") or {}).items()}
    producer_now = producer_versions()
    changed = next((name for name in sorted(set(recorded_producer) | set(producer_now))
                    if recorded_producer.get(name) != producer_now.get(name)), None)
    clauses.append({
        "clause": 6, "stale": changed is not None,
        "why": (f"producer changed: {changed} {recorded_producer.get(changed) or '?'} -> {producer_now.get(changed) or '?'}"
                if changed is not None else None),
        "recorded": recorded_producer, "current": producer_now,
    })
    if changed is not None:
        verdict.stale = True

    key = str(record.get("key") or "")
    stands = bool(key) and not any(clause["stale"] for clause in clauses if clause["clause"] in (1, 2, 3, 4, 6))
    verdict.stored = key if stands else None
    verdict.key = key if stands and not owed_a_run else None
    readable = all(constants_now.get(rel) is not None and all(name in constants_now[rel] for name in names)
                   for rel, names in recorded_constants.items())
    if now and readable and len(child_keys) == len(child_clauses):
        verdict.candidate = result_key(
            model=ref, closure_hash=now, children=child_keys, producer=producer_now,
            constants={rel: {name: constants_now[rel][name] for name in names} for rel, names in recorded_constants.items()},
        )
    return verdict


def _standing_key(verdict: Verdict) -> str | None:
    """The key a model's result stands under for its parent: its record's, while that
    stands (``Verdict.key``); else, for a record its source has moved on from, the key
    the source has NOW when a stored result answers for it (``Verdict.candidate``,
    ``store.results``) -- a source brought back to a state already built stands for its
    parent before anything restores it, and the parent's hit restores it
    (``generation._hit``) instead of running its own body. A read: nothing is written
    until a run takes the result."""
    if verdict.key is not None:
        return verdict.key
    if verdict.stored is not None or not verdict.candidate:
        return None
    from cadgen.store.results import read_result

    tree = str((read_result(verdict.candidate) or {}).get("tree") or "")
    return verdict.candidate if tree and tree_complete(tree) else None


def _constants_now(script: Path, constants: Mapping[str, Mapping[str, str]]) -> dict[str, dict[str, str] | None]:
    """The record's constants as their modules hold them now, by module: each name's
    hash (``closure.module_constant_hashes``), a name no longer a literal absent, a
    module that cannot be read kernel-free None."""
    from cadgen.store.closure import _resolve_relative, module_constant_hashes

    base = Path(script).resolve().parent
    now: dict[str, dict[str, str] | None] = {}
    for rel, names in sorted(constants.items()):
        resolved = _resolve_relative(str(rel), base)
        now[str(rel)] = module_constant_hashes(resolved, names) if resolved is not None else None
    return now


def _closure_why(script: Path, closure: Mapping[str, Any], now: str | None) -> str:
    """Clause 2's phrase: name what moved when the record can say -- a file
    edited or gone, one that appeared where an import would find it, an
    environment variable the model reads."""
    from cadgen.store.closure import changed_closure_files, describe_changes, source_files

    changed = changed_closure_files(script, closure.get("shas") or {}, closure.get("names") or {},
                                    closure.get("wholes") or {}, closure.get("own") or {})
    if now is None:
        # Only a file can be missing: an absent, roots, environment or listing entry changed.
        missing = [rel for rel in source_files(changed) if not (Path(script).resolve().parent / rel).exists()]
        return f"closure file missing: {', '.join(missing or changed)}" if (missing or changed) else "closure file missing"
    return describe_changes(changed)
