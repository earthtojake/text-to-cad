"""Store fixtures for tests: build a tree and lay a view of it, or seed a
document's result straight into the store without a kernel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def build_view(
    compound: Any,
    *,
    package_dir: Path,
    root_name: str,
    force: bool = False,
    provenance: Mapping[str, Any] | None = None,
    progress: Any | None = None,
) -> dict[str, Any]:
    """Build ``compound``'s tree into the store and lay a view of it at
    ``package_dir`` (the directory shape the older readers consume). Returns the
    build stats plus the tree hash under ``tree``."""
    from cadgen.store.build import build_tree_from_compound
    from cadgen.store.view import export_view

    tree_hash, _tree, stats = build_tree_from_compound(
        compound,
        root_name=root_name,
        force=force,
        progress=progress,
    )
    export_view(tree_hash, Path(package_dir))
    result = dict(stats)
    result["tree"] = tree_hash
    return result


def seed_result(
    document: Path | str,
    descriptor: Mapping[str, Any] | None = None,
    *,
    model: Path | str | None = None,
    surf: bytes = b"SURF\x00",
    components: tuple[str, ...] = ("c0",),
    kind: str = "assembly-package",
    entry_kind: str = "part",
    sidecar: Mapping[str, Any] | None = None,
) -> str:
    """Make ``document`` resolve as built: a tree object whose components are
    ``surf`` bytes, a record for ``model`` (the document itself when None, i.e.
    an imported source) that pins it, and the document entry. Returns the tree
    hash. ``descriptor`` may supply ``components``/``occurrences``/``assembly``
    /``kind``/``entryKind`` in the flat shape; components named there get the
    same ``surf`` bytes unless the entry already names an object."""
    from cadgen.store.objects import put_object
    from cadgen.store.records import note_document_tree, note_output, write_record
    from cadgen.store.trees import put_tree

    document = Path(document)
    descriptor = dict(descriptor or {})
    surf_hash = put_object(surf)
    raw_components = descriptor.get("components")
    if not isinstance(raw_components, dict):
        raw_components = {cid: {} for cid in components}
    tree_components: dict[str, Any] = {}
    for cid, entry in raw_components.items():
        entry = dict(entry or {})
        entry["surf"] = entry.get("surfObject") or surf_hash
        entry["brep"] = entry.get("brepObject") or surf_hash
        entry.pop("surfObject", None)
        entry.pop("brepObject", None)
        entry.setdefault("contentHash", cid)
        tree_components[cid] = entry
    occurrences = descriptor.get("occurrences")
    if not isinstance(occurrences, list):
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        occurrences = [
            {"id": f"o1.{i}" if len(tree_components) > 1 else "o1", "name": cid, "component": cid, "transform": identity}
            for i, cid in enumerate(tree_components, start=1)
        ]
    tree: dict[str, Any] = {
        "label": descriptor.get("label") or "model",
        "entryKind": descriptor.get("entryKind") or entry_kind,
        "units": "mm",
        "components": tree_components,
        "occurrences": occurrences,
        "links": [],
        "stats": {"occurrenceCount": len(occurrences), "linkCount": 0},
    }
    if isinstance(descriptor.get("assembly"), dict):
        tree["assembly"] = descriptor["assembly"]
    if descriptor.get("kind") not in (None, kind):
        tree["kind"] = descriptor["kind"]
    for key in ("bbox", "capabilities", "edgeRendering", "color"):
        if key in descriptor:
            tree[key] = descriptor[key]
    tree_hash = put_tree(tree)
    try:
        sha = hashlib.sha256(document.read_bytes()).hexdigest()
    except OSError:
        sha = ""
    owner = Path(model) if model is not None else document
    record = {
        "entryKind": tree["entryKind"],
        "sourceKind": "python" if model is not None else "step",
        "tree": tree_hash,
        "closure": {"hash": sha, "files": [], "static": True},
        "children": [],
        "outputs": {str(document.resolve()): {"sha256": sha}},
        "stepHash": sha,
    }
    if sidecar:
        record.update(sidecar)
    write_record(owner, record)
    # Artifact side: these bytes → this tree (what every reader consults).
    # Code side: which model wrote the path (the badge's question only).
    if sha:
        note_document_tree(sha, tree_hash, kind=str(tree.get("kind") or kind))
    if model is not None:
        note_output(document, owner)
    return tree_hash


def read_view_descriptor(view_dir: Path | str) -> dict[str, Any]:
    return json.loads((Path(view_dir) / "assembly.json").read_text(encoding="utf-8"))
