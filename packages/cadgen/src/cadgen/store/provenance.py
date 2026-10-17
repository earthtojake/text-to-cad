"""Provenance: the build's account of its own code, on the store's code side
(STORE.md §3, Provenance; README law 20).

``index/provenance/<sha256(model ref)>-v<PROVENANCE_SCHEMA_VERSION>``, one
entry per model beside its record, written by the build right after the
record for the result tree the record names::

    {
      "kind": "provenance", "schemaVersion": 5,
      "model": "/abs/src/bracket.py::bracket",
      "tree": "<the record's tree>",
      "features": [{"op": "cut", "file": "src/bracket.py", "line": 12, "function": "bracket",
                    "inputs": [0, 1]}, …],
      "components": {"<cid>": {"bracket.make_box1": 0, "bracket.cut1": 2, …}, …},
      "occurrences": {"<token>": 2, …}
    }

``features`` are the kernel constructions the model's code called, in call
order (``_internal/kernel_trace.py``), each with the frame it ran in and the
features, by place, that made what it was given (null: made outside the run);
``components`` are the components the build made, each with the feature every
feature name of its lineage stands for and the features those were given (a
feature is named among the features its part descends from, so one feature may
have another name in another part); ``occurrences`` are the result's occurrences
of those components, each with the feature whose call made the shape it places
(null: none of the run's) -- a part one construction made twice is one part, and
each of its occurrences was made by its own call. A line and a file are here and
nowhere else: a name holds neither, so an edit that moves code renames nothing.

Readers never open it (STORE.md §2, the two sides). Its one reader is
``cadgen store where <document> <ref>``: path → ``index/output`` → the model
→ its record and this entry, the file's hash checked against the record's output
entry, then the ref resolved in the tree the record names (by the one resolver every
ref goes through, ``cadgen.refs``) to its occurrence and component, and the entry
that describes that occurrence -- the model's, or, through each link it sits under,
a child's -- where the feature the element's name (or, for an occurrence, its
body's lineage) names is looked up, among the calls that made that occurrence, with
the one the lineage says last modified it. Without an entry, or with one for other
bytes, it says it does not know; nothing here finds or renders geometry. The entry
goes with ``store forget`` and is never evicted (§8); like a record, one at a key
this cadgen does not own is obsolete.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Iterator

from cadgen.store.index import model_key, read_entry, remove_entry, resolve_model_ref, versioned_key, write_entry

PROVENANCE_KIND = "provenance"
_PLURAL = {"face": "faces", "edge": "edges", "vertex": "vertices"}
# A format change bumps it and lands on new keys; another version's entries are
# never read, and are retired a week after their last write (gc, STORE.md §8).
# 2: features by name, and the components the build made, whose lineage names
# their elements by them. 3: features by place in the run, and each component with
# the feature each name of its lineage stands for (a part names its features among
# its own). 4: no document digest: the entry is written with the record, before the
# file exists, and the record's output entry says which bytes are the model's. 5: each
# occurrence of a component the build made, with the feature whose call made its shape.
PROVENANCE_SCHEMA_VERSION = 5

__all__ = [
    "PROVENANCE_KIND",
    "PROVENANCE_SCHEMA_VERSION",
    "Where",
    "describe",
    "provenance_key",
    "read_provenance",
    "remove_provenance",
    "where",
    "write_provenance",
]


def provenance_key(model: Path | str) -> str:
    """A model's provenance key: its identity's hash under this cadgen's schema."""
    return versioned_key(model_key(model), PROVENANCE_SCHEMA_VERSION)


def write_provenance(model: Path | str, payload: dict[str, Any], *, tree: str) -> None:
    """The entry for ``model``'s build that published ``tree``: ``payload`` holds its
    ``features``, ``components`` and ``occurrences``. Written after the record, and
    kept with the result stored under the record's key (``store.results``), which
    restores it. Idempotent; atomic."""
    ref = resolve_model_ref(model)
    body = {
        "kind": PROVENANCE_KIND,
        "schemaVersion": PROVENANCE_SCHEMA_VERSION,
        "model": ref,
        "tree": str(tree or ""),
        "features": list(payload.get("features") or []),
        "components": {str(cid): dict(names) for cid, names in sorted(dict(payload.get("components") or {}).items())},
        "occurrences": {str(token): index for token, index in sorted(dict(payload.get("occurrences") or {}).items())},
    }
    write_entry(PROVENANCE_KIND, provenance_key(ref), body)
    from cadgen.store.records import read_record
    from cadgen.store.results import write_result_provenance

    record = read_record(ref)
    if record and record.get("key"):
        write_result_provenance(str(record["key"]), body)


def read_provenance(model: Path | str) -> dict[str, Any] | None:
    data = read_entry(PROVENANCE_KIND, provenance_key(model))
    if data is None or data.get("kind") != PROVENANCE_KIND or data.get("schemaVersion") != PROVENANCE_SCHEMA_VERSION:
        return None
    return data


def remove_provenance(model: Path | str) -> None:
    remove_entry(PROVENANCE_KIND, provenance_key(model))


# --- where ------------------------------------------------------------------------------------


@dataclasses.dataclass
class Where:
    """What ``store where`` answers for one ref of one document."""

    document: str
    ref: str
    kind: str = "occurrence"
    known: bool = False
    reason: str | None = None
    model: str | None = None
    component: str | None = None
    made: dict[str, Any] | None = None
    modified: dict[str, Any] | None = None
    inputs: list[dict[str, Any]] = dataclasses.field(default_factory=list)

    def unknown(self, reason: str) -> "Where":
        self.known = False
        self.reason = reason
        return self


def where(document: Path | str, ref: str) -> Where:
    """Which feature made, and which last modified, what ``ref`` names in
    ``document``. A ref that cannot be read or that names another file raises
    ``ValueError``; a question the store cannot answer is a ``Where`` that is
    not ``known``, with its ``reason``."""
    from cadgen._internal.component_package import read_lineage
    from cadgen._internal.step_hash import step_file_hash
    from cadgen.cad_ref_syntax import element_feature, element_kind
    from cadgen.refs import descriptor_space, locate, resolve
    from cadgen.store.objects import read_verified_object
    from cadgen.store.parts import element_tokens
    from cadgen.store.records import document_entry_for_hash, model_for_output, read_record
    from cadgen.store.trees import flatten

    path = Path(document).expanduser().resolve()
    answer = Where(document=str(path), ref=str(ref))
    if not path.is_file():
        return answer.unknown(f"no file at {path}")
    model = model_for_output(path)
    if model is None:
        return answer.unknown("the store does not remember a model writing this file")
    answer.model = model
    record = read_record(model)
    if record is None:
        return answer.unknown("the model has no record; run it")
    entry = read_provenance(model)
    if entry is None:
        return answer.unknown("the model has no provenance entry; run it again")
    if entry.get("tree") != record.get("tree"):
        return answer.unknown("the provenance entry describes another build of the model; run it again")
    digest = step_file_hash(path)
    if ((record.get("outputs") or {}).get(str(path)) or {}).get("sha256") != digest:
        return answer.unknown("the file's bytes are not the ones the model's build wrote; run the model")
    document = document_entry_for_hash(digest) or {}
    if document.get("differ"):
        return answer.unknown("the file does not hold the result it was written from, so it shows its own "
                              "content" + ("" if document.get("plain") else
                                           "; run the model again, which writes it without names"))
    # The file is an export of the record's tree: the file's tokens are the tree's.
    flat = flatten(str(record.get("tree") or ""))
    if flat is None:
        return answer.unknown("the model's result is missing from the store; run it again")

    rows = {str(occ.get("id")): occ for occ in flat.get("occurrences") or []}
    components = flat.get("components") or {}

    def component_of(token: str) -> dict[str, Any]:
        return components.get(str((rows.get(token) or {}).get("component") or "")) or {}

    lineages: dict[str, dict[str, Any]] = {}

    def elements(token: str, kind: str) -> list[str | None]:
        return list((lineages.get(token) or {}).get(_PLURAL[kind]) or [])

    def tokens(token: str, kind: str) -> list[str]:
        # A ref by geometry (a token copied before the element had a name) names the
        # element of this body with that geometry, whatever names it now.
        return element_tokens(component_of(token))[_PLURAL[kind]]

    space = descriptor_space(flat, elements=elements, tokens=tokens, document=str(path))
    occurrence_id, element = locate(ref, space)
    answer.kind = "occurrence" if element is None else element_kind(element)
    answer.ref = "#" + (f"{occurrence_id}/{element}" if element else occurrence_id)
    row = rows.get(occurrence_id)
    if row is None:
        if element is not None:
            raise ValueError(f"#{occurrence_id} is a group; enumerate its entities or specify a leaf occurrence")
        return answer.unknown("a group is made of its occurrences; ask about one of them")
    cid = str(row.get("component") or "")
    component = component_of(occurrence_id)
    answer.component = cid
    if not component.get("lineage"):
        return answer.unknown("no feature of a model's run made this body: it was read from a file, or "
                              "built outside the kernel's constructions")
    found = _described(model, record, entry, occurrence_id, cid)
    if found is None:
        return answer.unknown("no build the store remembers made this body; run the model again")
    answer.model, described, placed = found
    feature_rows = described.get("features") or []
    stands = {str(name): index for name, index in (described["components"][cid] or {}).items()
              if isinstance(index, int) and 0 <= index < len(feature_rows)}
    try:
        lineage = lineages[occurrence_id] = read_lineage(read_verified_object(str(component["lineage"])))
    except (OSError, ValueError):
        return answer.unknown("the body's lineage is no longer in the store; run the model again")
    # A part one construction made twice is named by its first making; this occurrence
    # was made by its own calls, called as those were.
    first = stands.get(str(lineage.get("made")))
    if isinstance(placed, int) and first is not None and placed != first:
        counterparts = _parallel(feature_rows, first, placed)
        if counterparts is not None:
            stands = {name: counterparts.get(index, index) for name, index in stands.items()}
    named = {index: name for name, index in stands.items()}

    def feature(name: Any) -> dict[str, Any] | None:
        index = stands.get(str(name)) if name is not None else None
        return None if index is None else {**feature_rows[index], "name": str(name)}

    if element is None:
        made_by, modified_by = lineage.get("made"), None
    else:
        try:
            resolved = resolve(ref, space)
        except (OSError, RuntimeError):
            return answer.unknown("the body's geometry is no longer in the store; run the model again")
        except ValueError:
            return answer.unknown("the body has no element of that name: the ref names a build "
                                  "this document is not")
        element = str(resolved.element)
        if element_feature(element) is None:
            return answer.unknown("no feature of the model's run made this element: the run took it, as it "
                                  "was, from a shape no feature made (a child's or a file's)")
        answer.ref = f"#{occurrence_id}/{element}"
        made_by = element_feature(element)
        modified_by = (lineage.get("modified") or {}).get(element)
    answer.made = feature(made_by)
    answer.modified = feature(modified_by)
    if answer.made is None:
        return answer.unknown("this geometry came from outside the run: a file read, or a shape built "
                              "outside the kernel's constructions" + (
                                  f"; last modified by {answer.modified['name']}" if answer.modified else ""))
    answer.inputs = [{**feature_rows[index], "name": named[index]}
                     for index in dict.fromkeys(answer.made.get("inputs") or []) if index in named]
    answer.known = True
    return answer


def _described(model: str, record: dict[str, Any], entry: dict[str, Any], token: str,
               cid: str) -> tuple[str, dict[str, Any], int | None] | None:
    """The build that made the occurrence ``token`` of the model's flattened result, whose
    component is ``cid``: its model, its entry, and the feature whose call made the shape
    the occurrence places (None where the entry does not say). An occurrence the model's
    run placed is in its entry; one a link placed is followed into the child's
    entry, through each link it sits under (``trees.flatten_tree``'s origins), by its
    token there. Else the first entry listing the component answers."""
    from cadgen.store.trees import flatten_tree, get_tree

    current = (model, record, entry, token)
    while True:
        owner, owner_record, described, node = current
        occurrences = described.get("occurrences") or {}
        if node in occurrences and cid in (described.get("components") or {}):
            placed = occurrences[node]
            return owner, described, placed if isinstance(placed, int) else None
        tree = get_tree(str(owner_record.get("tree") or ""))
        origins: dict[str, tuple[str, str]] = {}
        if tree is not None:
            try:
                flatten_tree(tree, origins=origins)
            except (OSError, ValueError, TypeError, KeyError):
                origins = {}
        if node not in origins:
            break
        linked, child_token = origins[node]
        child = next(((child_model, child_record, child_entry)
                      for child_model, child_record, child_entry in _composed(owner_record)
                      if child_record.get("tree") == linked), None)
        if child is None:
            break
        current = (*child, child_token)
    for owner, described in _entries(model, record, entry):
        if cid in (described.get("components") or {}):
            return owner, described, None
    return None


def _parallel(rows: list[dict[str, Any]], first: int, other: int) -> dict[int, int] | None:
    """Each feature the feature ``first`` descends from (itself included) mapped to its
    counterpart among those ``other`` descends from, where the two were called alike --
    the same operations of the same functions, each given its counterpart's
    counterparts, in call order -- as the calls of a part one construction made twice
    are; None where they were not."""
    def descent(index: int) -> list[int]:
        seen: set[int] = set()
        pending = [index]
        while pending:
            current = pending.pop()
            if current in seen or not 0 <= current < len(rows):
                continue
            seen.add(current)
            pending.extend(given for given in rows[current].get("inputs") or [] if isinstance(given, int))
        return sorted(seen)

    ours, theirs = descent(first), descent(other)
    if len(ours) != len(theirs):
        return None
    counterparts = dict(zip(ours, theirs))
    for one, two in counterparts.items():
        mine, yours = rows[one], rows[two]
        if (mine.get("op"), mine.get("function")) != (yours.get("op"), yours.get("function")):
            return None
        if [counterparts.get(given) if isinstance(given, int) else None for given in mine.get("inputs") or []] \
                != list(yours.get("inputs") or []):
            return None
    return counterparts


def _composed(record: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any], dict[str, Any]]]:
    """Each child ``record`` names, with its record and entry, while the child's record
    still holds the key the parent composed and its entry describes its tree."""
    from cadgen.store.records import read_record

    for child in record.get("children") or []:
        child_model, key = str(child.get("model") or ""), str(child.get("key") or "")
        if not child_model:
            continue
        child_record = read_record(child_model)
        child_entry = read_provenance(child_model)
        if child_record is None or child_entry is None:
            continue
        if child_record.get("key") != key or child_entry.get("tree") != child_record.get("tree"):
            continue
        yield child_model, child_record, child_entry


def _entries(model: str, record: dict[str, Any], entry: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """The model's entry, then each composed child's (``_composed``), children first-called
    first, their own children after them."""
    yield model, entry
    seen = {model}
    pending = [record]
    while pending:
        current = pending.pop(0)
        for child_model, child_record, child_entry in _composed(current):
            if child_model in seen:
                continue
            seen.add(child_model)
            yield child_model, child_entry
            pending.append(child_record)


def _frame(feature: dict[str, Any]) -> str:
    return f"{feature.get('file')}:{feature.get('line')} in {feature.get('function')} ({feature.get('op')})"


def describe(answer: Where) -> list[str]:
    """``store where``'s lines for one answer."""
    lines = [f"document  {answer.document}", f"ref       {answer.ref}"]
    if answer.model:
        lines.append(f"model     {answer.model}")
    if not answer.known:
        lines.append(f"unknown   {answer.reason}")
        return lines
    assert answer.made is not None
    lines.append(f"{answer.kind:<9} made by {_frame(answer.made)}   {answer.made.get('name')}")
    if answer.inputs:
        lines.append("          inputs " + ", ".join(str(feature.get("name")) for feature in answer.inputs))
    if answer.kind != "occurrence":
        if answer.modified is not None:
            lines.append(f"          last modified by {_frame(answer.modified)}   {answer.modified.get('name')}")
        else:
            lines.append("          not modified since")
    return lines
