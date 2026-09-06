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

from cadgen.store.objects import is_object_hash, object_path
from cadgen.store.trees import flatten

DESCRIPTOR_NAME = "assembly.json"
COMPONENT_DIRNAME = "components"


def descriptor_for_view(tree_hash: str) -> dict[str, Any] | None:
    """The flattened tree with component refs spelled as view-relative paths
    (``components/<cid>.surf``, the file name every reader derives from an
    occurrence's component id) and the object hashes beside them
    (``surfObject``/``brepObject``)."""
    descriptor = flatten(tree_hash)
    if descriptor is None:
        return None
    components = descriptor.get("components") or {}
    for cid, entry in components.items():
        for key in ("surf", "brep"):
            digest = str((entry or {}).get(key) or "")
            if digest:
                entry[f"{key}Object"] = digest
                entry[key] = f"{COMPONENT_DIRNAME}/{cid}.{key}"
    return descriptor


# A tree is a content-addressed, immutable object, so the cid -> object map
# read out of it is the same on every call and is kept per (store root, tree)
# for the process's life. The viewer server resolves one component request
# per component of an assembly through here, and flattening a 600-occurrence
# tree costs ~11 ms of CPU each time: 485 requests for one 483-component
# model spent ~5.6 s re-deriving one answer. Keyed by the store root because
# the root is read from the environment per call and a suite may move it.
# A tree that is not there yet is NOT remembered — a compile in flight will
# make it appear. Bounded so a long-lived server holding hundreds of trees
# does not grow without limit.
_COMPONENT_OBJECTS_MEMO_MAX = 64
_component_objects_memo: dict[tuple[str, str], dict[str, Any]] = {}
_component_objects_lock = threading.Lock()


def _component_objects_for_tree(tree_hash: str) -> dict[str, Any] | None:
    """A descriptor-shaped ``{"components": {cid: {"surfObject", "brepObject"}}}``
    for the tree, memoised; None when the tree is missing."""
    from cadgen.store.paths import store_root

    key = (str(store_root()), tree_hash)
    with _component_objects_lock:
        cached = _component_objects_memo.get(key)
    if cached is not None:
        return cached
    descriptor = descriptor_for_view(tree_hash)
    if descriptor is None:
        return None
    objects = {
        "components": {
            cid: {
                "surfObject": str((entry or {}).get("surfObject") or ""),
                "brepObject": str((entry or {}).get("brepObject") or ""),
            }
            for cid, entry in (descriptor.get("components") or {}).items()
        }
    }
    with _component_objects_lock:
        while len(_component_objects_memo) >= _COMPONENT_OBJECTS_MEMO_MAX:
            _component_objects_memo.pop(next(iter(_component_objects_memo)))
        _component_objects_memo[key] = objects
    return objects


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
        digest = str(entry.get(f"{suffix}Object") or "")
        if is_object_hash(digest):
            return digest, suffix
    if is_object_hash(stem):
        return stem, suffix
    return None


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
    """A view (assembly.json + components/) of ``tree_hash``, built once per process and
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
    """Write a view directory (assembly.json + components/) for ``tree_hash``; return its path.
    With ``dest`` None a fresh temporary directory is created (caller removes)."""
    descriptor = descriptor_for_view(tree_hash)
    if descriptor is None:
        raise FileNotFoundError(f"tree object missing: {tree_hash}")
    root = Path(dest) if dest is not None else Path(tempfile.mkdtemp(prefix="cadgen-view-"))
    comp_dir = root / COMPONENT_DIRNAME
    comp_dir.mkdir(parents=True, exist_ok=True)
    for cid, entry in (descriptor.get("components") or {}).items():
        for key in ("surf", "brep"):
            digest = str(entry.get(f"{key}Object") or "")
            if digest:
                target = comp_dir / f"{cid}.{key}"
                if not target.exists():
                    shutil.copyfile(object_path(digest), target)
    (root / DESCRIPTOR_NAME).write_text(json.dumps(descriptor), encoding="utf-8")
    return root


def virtual_path(rel: str) -> tuple[bytes | Path | None, str]:
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
        descriptor = descriptor_for_view(tree_hash)
        if descriptor is None:
            return None, ""
        return json.dumps(descriptor).encode("utf-8"), "application/json"
    if len(parts) == 3 and parts[1] == COMPONENT_DIRNAME:
        resolved = component_object_for_ref(parts[2], _component_objects_for_tree(tree_hash))
        if resolved is None:
            return None, ""
        digest, suffix = resolved
        path = object_path(digest)
        if not path.is_file():
            return None, ""
        content_type = {"surf": "application/octet-stream", "brep": "application/octet-stream", "glb": "model/gltf-binary"}[suffix]
        return path, content_type
    return None, ""
