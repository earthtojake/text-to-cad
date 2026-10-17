"""A model's STEP as an export of its stored result, and the check it is verified by
(STORE.md §3, *Exports*).

A build publishes its result tree before anything is written from it. Its STEP is then
written from that tree by the build pool -- the export job, :func:`export_step` -- and a
parse of the file is compared with the tree, by the pool too -- the verify job,
:func:`verify_document`. Both are artifact jobs (``daemon/artifacts.py``): a request names
a tree, a staged file or a document and its digest, never a script.

- :func:`export_step` materializes the tree (``store.materialize``) and writes it with the
  names writer (``step_export.export_build123d_step_file``): each component's part key, on
  its product, and its faces' and edges' names, on the entities written for them
  (``step_names``) -- or, written plain, none of them, so that its bytes claim nothing
  about the store it came from. The file is a function of the tree and the writer
  (``step_export.STEP_WRITER_SCHEME``) alone.
- :func:`verify_document` compares a parse of the written bytes with the tree
  (``_internal/step_verify.py``): the occurrences a compile of the file names, by token,
  each holding the tree's part, every part's faces and edges named and placed as the tree
  has them, drawn in its colours. A file that verifies is the tree: its document entry
  names it, confirmed. A file that does not is its own content: its entry names the tree a
  compile of the file publishes -- read as any file is, its elements named by their
  geometry -- and lists what differs (``differ``). The model's next run writes it plain.

A document entry an export wrote is pending until its verify answers (``verified:
false``): a door confirms it first (:func:`confirm_document`), and a view draws it at once.
A verify that cannot compare the file with the tree (a component of the tree the store
cannot decode, a tree swept from under its entry) has not verified the file: it answers as
for one that does not hold the tree, saying why, so no entry stays pending on a verify that
ran. One that cannot parse the file raises -- there is nothing to map the bytes to -- which
the build hears as a warning (:func:`verify_warnings`); a door given that entry compiles the
file's bytes, as for a miss.
"""

from __future__ import annotations

import hashlib
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

__all__ = ["confirm_document", "export_step", "file_warning", "verify_document", "verify_warnings"]

# How many of the differences a document entry lists, and a warning shows.
_LISTED = 50


class _Spans:
    """What a writer's logger is told (``CliLogger``'s ``timed`` and ``warning``), kept to
    hand back: each step and the seconds it took, and the warnings, which the build that
    asked relays to its own logger."""

    def __init__(self) -> None:
        self.rows: list[list[Any]] = []
        self.warnings: list[str] = []

    @contextmanager
    def timed(self, label: str) -> Iterator[None]:
        started = time.perf_counter()
        try:
            yield
        finally:
            self.rows.append([label, time.perf_counter() - started])

    def warning(self, message: str) -> None:
        self.warnings.append(str(message))

    def debug(self, message: str) -> None:
        pass


def export_step(tree_hash: str, out: Path, *, names: bool = True,
                shapes: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Write the stored tree ``tree_hash`` to ``out`` and return the file's ``sha256``, the
    producer whose part keys it carries (``producer``, None when written plain) and the
    writer's ``spans`` and ``warnings``. ``names`` False writes it plain: no part key and no
    element name. ``shapes`` gives the build's own live shapes by cid for components the
    store cannot decode (an eager-only component's), which only the build's own process
    holds (STORE.md §3)."""
    from cadgen.store.parts import producer_identity
    from cadgen.store.trees import capture_tree

    spans = _Spans()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    producer = None
    if names:
        try:
            producer = producer_identity()
        except ValueError:
            # A part key names its producer: a runtime that cannot name its own writes
            # the file plain, as a named export never fails where a plain one succeeds.
            names = False
    from cadgen.step_export import export_build123d_step_file
    from cadgen.store.materialize import materialize_descriptor

    with spans.timed("materialize"):
        descriptor, payloads = capture_tree(tree_hash)
        placed: dict[int, str] = {}
        # Written, never handed to model code: untagged, so nothing is captured to tell an
        # edit of it apart (``materialize``'s partner evidence).
        document = materialize_descriptor(descriptor, captured_objects=payloads, shapes=shapes, placed=placed)
    namer = _namer(descriptor, payloads, placed, producer) if names else None
    digest = export_build123d_step_file(document, out, logger=spans, names=namer)
    return {"sha256": digest, "producer": producer, "spans": spans.rows, "warnings": spans.warnings}


def _namer(descriptor: Mapping[str, Any], payloads: Mapping[str, bytes], placed: Mapping[int, str],
           producer: dict) -> Callable[[Any], Any]:
    """What the file names each placed leaf of the materialized ``descriptor`` by: its
    component's part key under ``producer`` and its lineage's names for its faces and edges
    (``step_names.ComponentNames``); None for a shape no component placed."""
    from cadgen._internal.component_package import read_lineage
    from cadgen._internal.step_names import ComponentNames
    from cadgen.store.parts import part_key

    components = descriptor["components"]
    found: dict[str, Any] = {}

    def names(shape: Any) -> Any:
        cid = placed.get(id(shape))
        if cid is None:
            return None
        if cid not in found:
            entry = components[cid]
            lineage = read_lineage(payloads[entry["lineage"]]) if entry.get("lineage") else None
            found[cid] = ComponentNames(part=part_key(entry, producer),
                                        faces=tuple(lineage["faces"]) if lineage else (),
                                        edges=tuple(lineage["edges"]) if lineage else ())
        return found[cid]

    return names


def verify_document(tree_hash: str, document: Path, sha256: str, *, producer: dict | None) -> dict[str, Any]:
    """Whether the document at ``document``, whose bytes hash to ``sha256``, holds the tree
    ``tree_hash`` it was written from, and its entry made to say so: ``{"ok": True}`` when it
    does (the entry confirmed), ``{"ok": False, "differ": [...]}`` when it does not (the entry
    names the file's own content and what differs), ``{"ok": None}`` when the file no longer
    has those bytes (nothing is written). ``producer`` is the one whose part keys the file was
    written with, None for a file written plain: it is then verified by its occurrences
    alone (``step_verify``). A file the comparison cannot be made for -- a component of the
    tree the store cannot decode, a tree swept from under its entry -- is not verified: it
    answers as one that does not hold the tree, ``differ`` saying why. A file that does not
    parse raises."""
    from cadgen._internal.atomic_replace import read_bytes_with_ladder
    from cadgen._internal.step_scene_package import _scene_from_selected_bytes
    from cadgen.store.records import document_entry_for_hash

    path = Path(document).expanduser().resolve()
    payload = read_bytes_with_ladder(path)
    if hashlib.sha256(payload).hexdigest() != sha256:
        return {"ok": None}
    scene = _scene_from_selected_bytes(path, payload)
    del payload
    try:
        differ = _compared(scene, tree_hash, producer)
    except MemoryError:
        raise
    except Exception as error:  # noqa: BLE001 - not verified: the file is its own content, and its entry says why
        differ = [f"the file could not be verified against the result ({type(error).__name__}: {error})"]
    answer = {"ok": True} if not differ else {"ok": False, "differ": differ}
    entry = document_entry_for_hash(sha256)
    if entry is None or entry.get("tree") != tree_hash or entry.get("verified") is not False:
        # The entry is not this export's to settle: another export of equal bytes wrote it
        # since (the last one wins), or a verify already did.
        return answer
    from cadgen.store.records import note_document_tree

    if not differ:
        note_document_tree(sha256, tree_hash, kind=str(entry.get("kind") or "step"), producer=entry.get("producer"))
        return answer
    from cadgen.store.build import build_document_tree

    own, _tree, _stats = build_document_tree(scene)
    note_document_tree(sha256, own, kind=str(entry.get("kind") or "step"), producer=entry.get("producer"),
                       plain=producer is None, differ=differ)
    return answer


def _compared(scene: Any, tree_hash: str, producer: dict | None) -> list[str]:
    """What differs between the parse ``scene`` of a file and the tree ``tree_hash`` it was
    written from (:func:`verify_document`), as its entry lists it; empty when the file holds
    the tree."""
    from cadgen._internal.component_package import read_lineage
    from cadgen._internal.step_names import ComponentNames
    from cadgen._internal.step_verify import expected_component, verify_scene
    from cadgen.store.parts import _decoded, part_key
    from cadgen.store.trees import capture_tree

    descriptor, payloads = capture_tree(tree_hash)
    components = descriptor["components"]
    # A plain file is verified by its occurrences: its parts are told apart by their content.
    keys = {cid: part_key(entry, producer) if producer is not None else f"{entry['contentHash']}-v1"
            for cid, entry in components.items()}
    expected = {}
    for cid, entry in components.items():
        if keys[cid] in expected:
            continue
        lineage = read_lineage(payloads[entry["lineage"]]) if producer is not None and entry.get("lineage") else None
        names = ComponentNames(part=keys[cid], faces=tuple(lineage["faces"]) if lineage else (),
                               edges=tuple(lineage["edges"]) if lineage else ())
        topods, _colors = _decoded(entry)
        expected[keys[cid]] = expected_component(topods, names, entry["faceColors"])
    rows = descriptor["occurrences"]
    occurrences = {row["id"]: keys[row["component"]] for row in rows}
    # Each occurrence is drawn in its own colour, else its component's, as it is written.
    colors = {row["id"]: color for row in rows
              if (color := row.get("color") or components[row["component"]].get("color")) is not None}
    mismatches = verify_scene(scene, expected.values(), occurrences, colors, named=producer is not None)
    return _differ(mismatches, rows, keys)


def _differ(mismatches: list[Any], rows: list[Mapping[str, Any]], keys: Mapping[str, str]) -> list[str]:
    """What differs, as a document entry lists it: each difference by the occurrence it
    concerns, by its name and token, or by every occurrence placing the part it concerns."""
    placing: dict[str, list[str]] = {}
    for row in rows:
        placing.setdefault(keys[row["component"]], []).append(f"{row.get('name') or 'part'} (#{row['id']})")
    named = {row["id"]: f"{row.get('name') or 'part'} (#{row['id']})" for row in rows}
    found: list[str] = []
    for mismatch in mismatches:
        if mismatch.occurrence is not None:
            where = named.get(mismatch.occurrence) or f"#{mismatch.occurrence}"
        elif mismatch.part in placing:
            where = ", ".join(placing[mismatch.part])
        else:
            where = "the file"
        found.append(f"{where}: {mismatch.message}")
    if len(found) > _LISTED:
        found[_LISTED:] = [f"and {len(found) - _LISTED} more"]
    return found


def confirm_document(document: Path, digest: str, tree: str) -> str | None:
    """The tree a door answers with for the bytes ``digest`` of ``document``, having found
    ``tree`` for them: ``tree`` itself where nothing was pending. An entry an export wrote
    that no verify has answered is verified first, by the build pool -- one job for every
    door asking about the same bytes, and a job that read another copy of them, replaced
    meanwhile, is asked again for this one -- and the door answers with the tree the entry
    names after. A file that does not hold the result it was written from is reported once:
    it shows its own content. None where the entry is still pending after that -- its verify
    could not answer (it raised, reported once, naming the error), or ``document`` no longer
    holds those bytes -- and the door compiles the file's bytes, as for a miss."""
    from cadgen.store.records import document_entry_for_hash

    path = Path(document).expanduser().resolve()
    entry = document_entry_for_hash(digest)
    pending = entry is not None and entry.get("verified") is False
    while entry is not None and entry.get("verified") is False:
        from cadgen.daemon.artifacts import resolve_artifact

        try:
            answer = resolve_artifact({"kind": "verify", "tree": entry["tree"], "document": str(path), "sha256": digest,
                                       "producer": None if entry.get("plain") else entry.get("producer")})
        except Exception as error:  # noqa: BLE001 - the door compiles the file's bytes instead
            _warn_once(digest, f"{path.name} could not be verified against the result it was written from "
                               f"({type(error).__name__}: {error}); it is compiled from its bytes")
            return None
        entry = document_entry_for_hash(digest)
        if answer.get("ok") is not None or not _holds(path, digest):
            break
    if pending and (entry is None or entry.get("verified") is False):
        return None
    if entry is not None and entry.get("differ"):
        _warn_once(digest, file_warning(path, entry["differ"], plain=bool(entry.get("plain"))))
    return str(entry["tree"]) if pending else tree


def verify_warnings(job: Any, document: Path, *, plain: bool) -> list[str]:
    """What a build says of its verify ``job`` (``daemon.artifacts.ArtifactFuture``), waited
    for where it is not done: the file's warning where it does not hold the result it was
    written from (:func:`file_warning`), that the verify could not answer, naming the error,
    or nothing."""
    try:
        answer = job.result()
    except Exception as error:  # noqa: BLE001 - the file is published; a verify that raised is a warning
        return [f"{Path(document).name} could not be verified against the result it was written from "
                f"({type(error).__name__}: {error})"]
    return [file_warning(document, answer["differ"], plain=plain)] if answer.get("differ") else []


_WARNED: set[str] = set()


def _warn_once(digest: str, text: str) -> None:
    """``text`` on the build's done event, else stderr: once per process for the bytes
    ``digest``, however many doors ask about them."""
    if digest in _WARNED:
        return
    _WARNED.add(digest)
    from cadgen._internal.build_timing import note_warning

    if not note_warning(text):
        print(f"[cadgen] warning: {text}", file=sys.stderr)


def _holds(path: Path, digest: str) -> bool:
    """Whether the file at ``path`` still has the bytes ``digest``."""
    from cadgen._internal.atomic_replace import read_bytes_with_ladder

    try:
        return hashlib.sha256(read_bytes_with_ladder(path)).hexdigest() == digest
    except OSError:
        return False


def file_warning(document: Path, differ: list[str], *, plain: bool) -> str:
    """What a build or a door says of a file that does not hold the result it was written
    from: that it shows its own content, what differs, and -- for a file written with
    names -- that the next run writes it plain. A file written plain is kept as it is: the
    same result is written plain to the same bytes."""
    then = "" if plain else "; the model's next run writes it without names"
    return (f"{Path(document).name} does not hold the result it was written from, so it shows its own "
            f"content{then}: {'; '.join(differ)}")
