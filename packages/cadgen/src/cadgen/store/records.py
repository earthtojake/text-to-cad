"""Records: the mutable per-model entry in ``index/model/``.

A record says what a model's build depended on and what it produced::

    {
      "model": "/abs/src/robot.py",
      "kind": "step",
      "entryKind": "assembly",
      "tree": "<tree object hash>",
      "closure": {"hash": "…", "files": ["robot.py", "lib/frame.py"]},
      "children": [{"model": "/abs/src/arm.py", "tree": "…"}],
      "outputs": {"/abs/STEP/robot.step": {"sha256": "…"}, …}
    }

``children`` is recorded from the CALLS the body made, never derived from the
tree's links — that is what makes the link/component decision in
``cadgen.store.trees`` safe. ``closure.files`` are relative to the script's
folder and hashed by ``cadgen.store.closure``.

Identity is the SCRIPT. A generated document carries no tie back to its
source (a generated file is independent of its script).

Two sides, two index kinds (STORE.md §2, the law):

- ``index/document/<sha256(document BYTES)>`` → ``{"tree": …, "kind": …}``.
  ARTIFACT → ARTIFACT. The only thing a reader (a door, the viewer, snapshot)
  consults to find the tree for a file: hash the bytes, look it up, read
  objects. Written whenever a tree is published for a document — by the
  model's build for its ``.step`` output, by a compile job for the file it
  compiled. The same bytes anywhere on disk resolve to the same tree; a file
  with no entry is compiled, never refused, and no record is opened.
- ``index/output/<sha256(output PATH)>`` → ``{"model": …}``. CODE-SIDE
  dependency memory: which model wrote the file at this path. Read by
  ``store why`` and provenance — never by the viewer or a render path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cadgen.store.index import (
    iter_entries,
    model_key,
    path_key,
    read_entry,
    remove_entry,
    resolve_model_ref,
    split_model_ref,
    write_entry,
)

RECORD_KIND = "record"


def read_record(model: Path | str) -> dict[str, Any] | None:
    data = read_entry("model", model_key(model))
    if data is None:
        # A bare script path whose file is gone (or no longer parses) cannot name
        # its function: find the record by the script it recorded, when exactly one.
        script, function = split_model_ref(model)
        if function is None and script.suffix.lower() == ".py" and not script.is_file():
            found = records_for_script(script)
            data = found[0][1] if len(found) == 1 else None
    if data is None or data.get("kind") != RECORD_KIND:
        return None
    return data


def records_for_script(script: Path | str) -> list[tuple[str, dict[str, Any]]]:
    """Every record whose model lives in ``script``: ``(model ref, record)`` pairs,
    in file order of the index."""
    import json

    resolved = _resolved(script)
    found: list[tuple[str, dict[str, Any]]] = []
    for _key, entry_file in iter_entries("model"):
        try:
            data = json.loads(entry_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("kind") == RECORD_KIND and data.get("script") == resolved:
            found.append((str(data.get("model") or resolved), data))
    return found


def write_record(model: Path | str, payload: dict[str, Any]) -> None:
    body = dict(payload)
    body["kind"] = RECORD_KIND
    ref = resolve_model_ref(model)
    script, function = split_model_ref(ref)
    body["model"] = ref
    body["script"] = str(script)
    body["function"] = function
    write_entry("model", model_key(ref), body)


def remove_record(model: Path | str) -> None:
    remove_entry("model", model_key(model))


def update_record(model: Path | str, **fields: Any) -> dict[str, Any] | None:
    """Merge ``fields`` into an existing record (atomic rewrite). None if absent."""
    record = read_record(model)
    if record is None:
        return None
    record.update(fields)
    write_record(model, record)
    return record


def _resolved(path: Path | str) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except (OSError, ValueError, RuntimeError):
        import os

        return os.path.abspath(str(path))


def note_document_tree(document_hash: str, tree: str, *, kind: str = "step") -> None:
    """``index/document/<sha256(bytes)>`` → the tree describing those bytes.
    Artifact → artifact; idempotent; atomic. Keeps the entry's mesh ledger when
    the tree is unchanged (those meshes were cut from this same tree)."""
    digest = str(document_hash or "").strip()
    tree_hash = str(tree or "").strip()
    if not digest or not tree_hash:
        return
    existing = read_entry("document", digest) or {}
    payload: dict[str, Any] = {"tree": tree_hash, "kind": str(kind or "step")}
    meshes = existing.get("meshes")
    if isinstance(meshes, dict) and str(existing.get("tree") or "") == tree_hash:
        payload["meshes"] = meshes
    write_entry("document", digest, payload)


def tree_for_document_hash(document_hash: str) -> str | None:
    """The tree a reader uses for a file with these bytes, or None (compile it)."""
    digest = str(document_hash or "").strip()
    if not digest:
        return None
    entry = read_entry("document", digest) or {}
    tree_hash = str(entry.get("tree") or "").strip()
    return tree_hash or None


def note_document_mesh(document_hash: str, variant_key: str, sha256: str) -> None:
    """A mesh door's ledger, artifact-side: the mesh cut from THESE bytes at THIS
    variant (format × tolerances × pose) has this sha. Lives on the document
    entry so a door never opens a record. Best-effort (last write wins)."""
    digest = str(document_hash or "").strip()
    if not digest or not variant_key or not sha256:
        return
    entry = read_entry("document", digest)
    if not entry or not entry.get("tree"):
        return
    meshes = dict(entry.get("meshes") or {})
    meshes[str(variant_key)] = str(sha256)
    entry["meshes"] = meshes
    write_entry("document", digest, entry)


def document_mesh_sha(document_hash: str, variant_key: str) -> str | None:
    digest = str(document_hash or "").strip()
    if not digest:
        return None
    entry = read_entry("document", digest) or {}
    meshes = entry.get("meshes") or {}
    value = meshes.get(str(variant_key)) if isinstance(meshes, dict) else None
    return str(value) if value else None


def note_output(output_path: Path | str, model: Path | str) -> None:
    """Code-side memory: ``model`` wrote the file at ``output_path``. For
    ``store why`` and provenance — never for the viewer, and never for finding
    or rendering an artifact (that is ``note_document_tree``). Idempotent; atomic."""
    write_entry("output", path_key(output_path), {"model": resolve_model_ref(model)})


def forget_output(output_path: Path | str) -> None:
    remove_entry("output", path_key(output_path))


def model_for_output(output_path: Path | str) -> str | None:
    """The model (``script::fn``) the store remembers writing ``output_path``,
    when that script still exists, else None. MODEL-SIDE: ``store why`` / provenance."""
    entry = read_entry("output", path_key(output_path)) or {}
    recorded = str(entry.get("model") or "").strip()
    if recorded:
        script, _function = split_model_ref(recorded)
        if script.is_file():
            return recorded
    return None


def source_for_document(document: Path | str) -> str:
    """MODEL-SIDE (``store why``, provenance — never the viewer or a render path): the
    model the store remembers writing ``document``, else the document itself
    (an imported source keys its own record on its path)."""
    document = Path(document)
    model = model_for_output(document)
    if model is not None:
        return model
    return _resolved(document)


def record_for_document(document: Path | str) -> dict[str, Any] | None:
    """MODEL-SIDE: the record behind a ``.step`` on disk (generated or imported),
    or None. A reader that needs a TREE uses ``tree_for_document_hash``."""
    return read_record(source_for_document(document))


def current_tree(model: Path | str) -> str | None:
    record = read_record(model)
    if record is None:
        return None
    tree = str(record.get("tree") or "").strip()
    return tree or None
