"""Views of a tree for consumers that speak the view layout (assembly.json + components/).

Two consumers cannot read objects by hash directly: the Node builders (the
mesh exporter takes ``--package-dir``) and the browser (the viewer/snapshot
client resolves ``assembly.json`` and ``components/<cid>.surf`` RELATIVE to a
package URL). Neither gets a directory in the store — the store has no result
directories. They get a **view**:

- :func:`export_view` writes the flattened tree (assembly.json) plus every component it
  references into a TEMPORARY directory outside the store (copies; the
  objects are small and the view is short-lived). Callers own its lifetime.
- :func:`virtual_path` resolves a view-relative path (``<tree>/assembly.json``,
  ``<tree>/components/<object>.surf``) to bytes on demand, so an HTTP route can
  present a tree as if it were a view directory without writing anything.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from cadgen.store.objects import is_object_hash, object_path, read_verified_object
from cadgen.store.trees import capture_tree

DESCRIPTOR_NAME = "assembly.json"
COMPONENT_DIRNAME = "components"


def _select_producer(tree_hash: str, producer: dict | None, document_hash: str | None) -> dict:
    from cadgen.store import surfaces
    from cadgen.store.records import document_entry_for_hash, note_document_tree

    selected = producer
    if document_hash:
        entry = document_entry_for_hash(document_hash)
        if entry is None or entry.get("tree") != tree_hash:
            raise FileNotFoundError("the selected document no longer has this geometry tree")
        if selected is None:
            try:
                selected = surfaces.producer_fields(entry.get("surfaceProducer"))
            except (ValueError, TypeError):
                selected = None
    if selected is None:
        from cadgen.daemon.artifacts import resolve_artifact

        selected = resolve_artifact({"kind": "producer"})
        if document_hash:
            current = document_entry_for_hash(document_hash)
            if current is not None and current.get("tree") == tree_hash:
                note_document_tree(document_hash, tree_hash, surface_producer=selected)
    return surfaces.producer_fields(selected)


def descriptor_for_view(
    tree_hash: str, *, producer: dict | None = None, document_hash: str | None = None,
) -> dict[str, Any] | None:
    """An owned runtime view of complete geometry, before optional SURF work.

    A saved document's one index snapshot supplies its attested producer hint.
    A bare tree without a hint initializes a producer through the build pool;
    this adapter and its HTTP callers never import the kernel.
    """
    from cadgen.store import surfaces

    try:
        # Reject damaged geometry before starting even a producer-identity job.
        geometry, _ = capture_tree(tree_hash, retain_payloads=False)
        selected = _select_producer(tree_hash, producer, document_hash)
        descriptor = surfaces._view_from_geometry(tree_hash, geometry, producer=selected)
    except (OSError, ValueError):
        return None
    for cid, entry in descriptor["components"].items():
        entry["brep"] = f"{COMPONENT_DIRNAME}/{cid}.brep"
    if document_hash:
        descriptor["documentHash"] = document_hash
    return descriptor


def ready_surface_records(tree_hash: str, producer: dict, cids: list[str] | None = None) -> dict:
    """Available verified SURF derivations; a miss does no native work."""
    from cadgen.store import surfaces

    descriptor, _ = capture_tree(tree_hash, retain_payloads=False)
    selected = list(descriptor["components"]) if cids is None else cids
    if any(cid not in descriptor["components"] for cid in selected):
        raise ValueError("surface request names an unpinned component")
    result = {}
    for cid in selected:
        record = surfaces.lookup(descriptor["components"][cid], producer)
        if record is not None:
            result[cid] = record
    return result


def materialize_view_surfaces(descriptor: dict) -> dict:
    """Complete an owned static/export view via artifact-only pooled derivation."""
    from cadgen.daemon.artifacts import ArtifactJobError, resolve_artifact
    from cadgen.store import surfaces

    tree = descriptor["tree"]
    producer = surfaces.producer_fields(descriptor["surfaceProducer"])
    records = ready_surface_records(tree, producer)
    missing = [cid for cid in descriptor["components"] if cid not in records]
    if missing:
        try:
            resolve_artifact({"kind": "surfaces", "tree": tree, "cids": missing, "producer": producer})
        except ArtifactJobError as error:
            if not surfaces.producer_unavailable(error):
                raise
            current = resolve_artifact({"kind": "producer"})
            if surfaces.producer_key(current) == surfaces.producer_key(producer):
                raise
            # Static exports have no displayed revision to retain. Prepare a
            # whole new owned view; never mix an old mesh with new selectors.
            replacement = descriptor_for_view(tree, producer=current, document_hash=descriptor.get("documentHash"))
            if replacement is None:
                raise FileNotFoundError("geometry disappeared during surface producer replacement") from error
            if descriptor.get("documentHash"):
                from cadgen.store.records import document_entry_for_hash, note_document_tree
                entry = document_entry_for_hash(descriptor["documentHash"])
                if entry is not None and entry.get("tree") == tree:
                    note_document_tree(descriptor["documentHash"], tree, surface_producer=current)
            return materialize_view_surfaces(replacement)
        records = ready_surface_records(tree, producer)
    for cid, entry in descriptor["components"].items():
        record = records.get(cid)
        if record is None or record["surfaceInput"] != entry["surfaceInput"]:
            raise FileNotFoundError("surface derivation disappeared before view publication")
        entry["surfaceObject"] = record["object"]
        entry["surf"] = f"{COMPONENT_DIRNAME}/{cid}.surf"
    return descriptor


def component_object_for_ref(ref: str, descriptor: dict[str, Any] | None = None) -> tuple[str, str] | None:
    """``components/<cid>.surf`` -> (object hash, suffix) through ``assembly.json``
    (a view's assembly.json); a bare object hash in place of the cid also resolves.
    None when nothing matches."""
    name = str(ref or "").replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return None
    stem, suffix = name.rsplit(".", 1)
    if suffix not in ("surf", "brep", "glb"):
        return None
    if descriptor is not None:
        entry = (descriptor.get("components") or {}).get(stem) or {}
        digest = str(entry.get("surfaceObject" if suffix == "surf" else f"{suffix}Object") or "")
        if is_object_hash(digest):
            return digest, suffix
    if is_object_hash(stem):
        return stem, suffix
    return None


def component_object_for_tree(tree_hash: str, ref: str) -> tuple[str, str] | None:
    """Resolve a native component from its verified pinned geometry closure.

    Disposable surfaces use their separate input/output route. Neither a CID
    nor a bare object hash can expose bytes unrelated to this geometry tree.
    """
    name = str(ref or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not name.endswith(".brep"):
        return None
    stem = name[:-5]
    try:
        descriptor, _ = capture_tree(tree_hash, retain_payloads=False)
    except (OSError, ValueError, TypeError):
        return None
    components = descriptor["components"]
    entry = components.get(stem)
    if entry is not None:
        digest = entry["brep"]
    elif is_object_hash(stem) and any(item["brep"] == stem for item in components.values()):
        digest = stem
    else:
        return None
    return digest, "brep"


def views_root() -> Path:
    """Where this process's views live: under the system temp dir, per pid, so
    a served view path is always confined to one known root."""
    root = Path(tempfile.gettempdir()) / "cadgen-views" / str(os.getpid())
    root.mkdir(parents=True, exist_ok=True)
    return root


_VIEW_DIRS: dict[tuple[str, str | None], Path] = {}
_VIEW_LOCK = threading.Lock()
_VIEW_CLEANUP_REGISTERED = False


def _cleanup_views() -> None:
    shutil.rmtree(views_root(), ignore_errors=True)


def view_dir_for(tree_hash: str, *, producer: dict | None = None, document_hash: str | None = None) -> Path:
    """A view (assembly.json + components/) of ``tree_hash``, built once per process and
    removed at exit. The adapter for consumers that need a DIRECTORY (the Node
    exporters, the selector-index composer, the snapshot page)."""
    global _VIEW_CLEANUP_REGISTERED
    descriptor = descriptor_for_view(tree_hash, producer=producer, document_hash=document_hash)
    if descriptor is None:
        raise FileNotFoundError(f"tree object missing: {tree_hash}")
    # Byte-distinct saved documents may share geometry and a display producer.
    # Their owned manifests retain the selected document binding separately.
    view_key = (descriptor["viewId"], document_hash)
    with _VIEW_LOCK:
        existing = _VIEW_DIRS.get(view_key)
        if existing is not None and (existing / DESCRIPTOR_NAME).is_file():
            return existing
    # Never hold a process-wide view lock while waiting for pooled native work.
    descriptor = materialize_view_surfaces(descriptor)
    view_key = (descriptor["viewId"], document_hash)
    with _VIEW_LOCK:
        existing = _VIEW_DIRS.get(view_key)
        if existing is not None and (existing / DESCRIPTOR_NAME).is_file():
            return existing
        if not _VIEW_CLEANUP_REGISTERED:
            atexit.register(_cleanup_views)
            _VIEW_CLEANUP_REGISTERED = True
        target = views_root() / descriptor["viewId"] / (document_hash or "geometry")
        _write_view(descriptor, target)
        _VIEW_DIRS[view_key] = target
        return target


def export_view(
    tree_hash: str, dest: Path | None = None, *, producer: dict | None = None, document_hash: str | None = None,
) -> Path:
    """Write a view directory (assembly.json + components/) for ``tree_hash``; return its path.
    With ``dest`` None a fresh temporary directory is created (caller removes)."""
    descriptor = descriptor_for_view(tree_hash, producer=producer, document_hash=document_hash)
    if descriptor is None:
        raise FileNotFoundError(f"tree object missing: {tree_hash}")
    root = Path(dest) if dest is not None else Path(tempfile.mkdtemp(prefix="cadgen-view-"))
    return _write_view(materialize_view_surfaces(descriptor), root)


def _write_view(descriptor: dict, root: Path) -> Path:
    comp_dir = root / COMPONENT_DIRNAME
    comp_dir.mkdir(parents=True, exist_ok=True)
    for cid, entry in (descriptor.get("components") or {}).items():
        for key in ("surf", "brep"):
            digest = str(entry.get("surfaceObject" if key == "surf" else f"{key}Object") or "")
            if digest:
                target = comp_dir / f"{cid}.{key}"
                # The file is an owned view, not the CAS object. Always replace
                # it from verified bytes when publishing a new descriptor.
                target.write_bytes(read_verified_object(digest))
    (root / DESCRIPTOR_NAME).write_text(json.dumps(descriptor), encoding="utf-8")
    return root


def virtual_path(
    rel: str, *, producer: dict | None = None, document_hash: str | None = None,
) -> tuple[bytes | Path | None, str]:
    """Resolve ``<tree>`` (or ``<tree>/assembly.json``) and ``<tree>/components/<cid>.<suffix>``.

    Returns ``(payload, content_type)``: bytes for the assembly.json, a Path for a
    component object (streamable), or ``(None, "")`` when nothing matches."""
    parts = [p for p in str(rel or "").replace("\\", "/").split("/") if p]
    if not parts or not is_object_hash(parts[0]):
        return None, ""
    tree_hash = parts[0]
    if parts[1:] in ([], [DESCRIPTOR_NAME]):
        # The tree itself IS the "directory" the client names; its assembly.json
        # answers for both spellings.
        descriptor = descriptor_for_view(tree_hash, producer=producer, document_hash=document_hash)
        if descriptor is None:
            return None, ""
        return json.dumps(descriptor).encode("utf-8"), "application/json"
    if len(parts) == 3 and parts[1] == COMPONENT_DIRNAME:
        resolved = component_object_for_tree(tree_hash, parts[2])
        if resolved is None:
            return None, ""
        digest, suffix = resolved
        path = object_path(digest)
        if not path.is_file():
            return None, ""
        content_type = {"surf": "application/octet-stream", "brep": "application/octet-stream", "glb": "model/gltf-binary"}[suffix]
        return path, content_type
    return None, ""
