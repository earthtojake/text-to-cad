"""Views of a tree for consumers that speak the legacy package layout.

Two consumers cannot read objects by hash directly: the Node builders (the
mesh exporter takes ``--package-dir``) and the browser (the viewer/snapshot
client resolves ``assembly.json`` and ``components/<cid>.surf`` RELATIVE to a
package URL). Neither gets a directory in the store — the store has no result
directories. They get a **view**:

- :func:`export_view` writes the flattened descriptor plus every component it
  references into a TEMPORARY directory outside the store (copies; the
  objects are small and the view is short-lived). Callers own its lifetime.
- :func:`virtual_path` resolves a package-relative path (``<tree>/assembly.json``,
  ``<tree>/components/<object>.surf``) to bytes on demand, so an HTTP route can
  present a tree as if it were a package directory without writing anything.
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

from cadgen.store.objects import is_object_hash, object_path
from cadgen.store.trees import flatten

DESCRIPTOR_NAME = "assembly.json"
COMPONENT_DIRNAME = "components"


def descriptor_for_view(tree_hash: str) -> dict[str, Any] | None:
    """The flattened descriptor with component refs spelled as package-relative
    paths (``components/<object>.surf``), the shape the JS client expects."""
    descriptor = flatten(tree_hash)
    if descriptor is None:
        return None
    components = descriptor.get("components") or {}
    for cid, entry in components.items():
        for key in ("surf", "brep"):
            digest = str((entry or {}).get(key) or "")
            if digest:
                entry[f"{key}Object"] = digest
                entry[key] = f"{COMPONENT_DIRNAME}/{digest}.{key}"
    return descriptor


def component_object_for_ref(ref: str) -> tuple[str, str] | None:
    """``components/<object>.surf`` -> (object hash, suffix), or None."""
    name = str(ref or "").replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in name:
        return None
    digest, suffix = name.rsplit(".", 1)
    if not is_object_hash(digest) or suffix not in ("surf", "brep", "glb"):
        return None
    return digest, suffix


def views_root() -> Path:
    """Where this process's views live: under the system temp dir, per pid, so
    a served view path is always confined to one known root."""
    root = Path(tempfile.gettempdir()) / "cadgen-views" / str(os.getpid())
    root.mkdir(parents=True, exist_ok=True)
    return root


_VIEW_DIRS: dict[str, Path] = {}
_VIEW_LOCK = threading.Lock()
_VIEW_CLEANUP_REGISTERED = False


def _cleanup_views() -> None:
    shutil.rmtree(views_root(), ignore_errors=True)


def view_dir_for(tree_hash: str) -> Path:
    """A package-shaped view of ``tree_hash``, built once per process and
    removed at exit. The adapter for consumers that need a DIRECTORY (the Node
    exporters, the selector-index composer, the snapshot page)."""
    global _VIEW_CLEANUP_REGISTERED
    with _VIEW_LOCK:
        existing = _VIEW_DIRS.get(tree_hash)
        if existing is not None and (existing / DESCRIPTOR_NAME).is_file():
            return existing
        if not _VIEW_CLEANUP_REGISTERED:
            atexit.register(_cleanup_views)
            _VIEW_CLEANUP_REGISTERED = True
        target = views_root() / tree_hash
        export_view(tree_hash, target)
        _VIEW_DIRS[tree_hash] = target
        return target


def export_view(tree_hash: str, dest: Path | None = None) -> Path:
    """Write a package-shaped directory for ``tree_hash``; return its path.
    With ``dest`` None a fresh temporary directory is created (caller removes)."""
    descriptor = descriptor_for_view(tree_hash)
    if descriptor is None:
        raise FileNotFoundError(f"tree object missing: {tree_hash}")
    root = Path(dest) if dest is not None else Path(tempfile.mkdtemp(prefix="cadgen-view-"))
    comp_dir = root / COMPONENT_DIRNAME
    comp_dir.mkdir(parents=True, exist_ok=True)
    for entry in (descriptor.get("components") or {}).values():
        for key in ("surf", "brep"):
            digest = str(entry.get(f"{key}Object") or "")
            if digest:
                target = comp_dir / f"{digest}.{key}"
                if not target.exists():
                    shutil.copyfile(object_path(digest), target)
    (root / DESCRIPTOR_NAME).write_text(json.dumps(descriptor), encoding="utf-8")
    return root


def ingest_view(view_dir: Path, *, base_tree: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Read a view's (possibly rewritten) ``assembly.json`` back into a tree.

    Used after a kinematics bake rewrites placements in the view. The result is
    a fully INLINE tree (links expanded): a baked pose may move a leaf inside a
    child, so the child is no longer intact and cannot be linked. Component refs
    map back to the object hashes the view carried (``surfObject``/``brepObject``).
    """
    from cadgen.store.trees import put_tree

    descriptor = json.loads((Path(view_dir) / DESCRIPTOR_NAME).read_text(encoding="utf-8"))
    components: dict[str, Any] = {}
    for cid, entry in (descriptor.get("components") or {}).items():
        entry = dict(entry)
        for key in ("surf", "brep"):
            digest = str(entry.pop(f"{key}Object", "") or "")
            if not digest:
                resolved = component_object_for_ref(str(entry.get(key) or ""))
                digest = resolved[0] if resolved else ""
            entry[key] = digest
        components[cid] = entry
    tree = {
        key: value
        for key, value in base_tree.items()
        if key not in {"kind", "components", "occurrences", "links", "assembly", "stats", "bbox", "tree"}
    }
    tree["components"] = components
    tree["occurrences"] = list(descriptor.get("occurrences") or [])
    tree["links"] = []
    if isinstance(descriptor.get("assembly"), dict):
        tree["assembly"] = descriptor["assembly"]
    if descriptor.get("bbox") is not None:
        tree["bbox"] = descriptor["bbox"]
    tree["stats"] = {"occurrenceCount": len(tree["occurrences"]), "linkCount": 0}
    return put_tree(tree), tree


def virtual_path(rel: str) -> tuple[bytes | Path | None, str]:
    """Resolve ``<tree>/assembly.json`` or ``<tree>/components/<object>.<suffix>``.

    Returns ``(payload, content_type)``: bytes for the descriptor, a Path for a
    component object (streamable), or ``(None, "")`` when nothing matches."""
    parts = [p for p in str(rel or "").replace("\\", "/").split("/") if p]
    if len(parts) < 2 or not is_object_hash(parts[0]):
        return None, ""
    tree_hash = parts[0]
    if parts[1:] == [DESCRIPTOR_NAME]:
        descriptor = descriptor_for_view(tree_hash)
        if descriptor is None:
            return None, ""
        return json.dumps(descriptor).encode("utf-8"), "application/json"
    if len(parts) == 3 and parts[1] == COMPONENT_DIRNAME:
        resolved = component_object_for_ref(parts[2])
        if resolved is None:
            return None, ""
        digest, suffix = resolved
        path = object_path(digest)
        if not path.is_file():
            return None, ""
        content_type = {"surf": "application/octet-stream", "brep": "application/octet-stream", "glb": "model/gltf-binary"}[suffix]
        return path, content_type
    return None, ""
