"""Reconstruct a loaded STEP scene from its tree.

The canonical tree already stores the native scene inputs: each unique
prototype's encoded BREP object and effective face-color recipe, plus the
occurrence hierarchy with names, transforms and colors. So the tree is the
warm-load cache; there is no second geometry store. ``load_step_scene_cached``
skips the text-STEP parse by reading the tree;
a STEP with no current tree pays one full parse, and the canonical document
tree then makes the next load warm. This tree holds the prototypes read from
the saved STEP; authored source result trees never participate. Saved readback
uses the same verified reconstruction when those exact emitted bytes already
have a canonical document tree.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadgen._internal.step_scene_loader import (
    _location_from_transform_matrix,
    _shape_hash,
    load_step_scene as _load_step_scene_text,
)
from cadgen._internal.step_scene_types import ColorRGBA, LoadedStepScene, OccurrenceNode

_IDENTITY_TRANSFORM = (
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
)


class _LazyShapes(Mapping):
    """Scene-owned prototypes decoded on demand from a captured byte closure."""

    def __init__(self, entries):
        self._entries = entries
        self._decoded = {}

    def __iter__(self):
        return iter(self._entries)

    def __len__(self):
        return len(self._entries)

    def __getitem__(self, key):
        if key not in self._decoded:
            from cadgen._internal.component_package import decode_geometry_component

            entry, payload = self._entries[key]
            self._decoded[key] = decode_geometry_component(entry, payload).wrapped
        return self._decoded[key]


def _face_colors_from_recipe(recipe: dict, shape: Any) -> dict[int, ColorRGBA]:
    """Map the geometry's intrinsic ordinal recipe onto its private topology."""
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    face_map = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_ShapeEnum.TopAbs_FACE, face_map)
    face_colors: dict[int, ColorRGBA] = {}
    for raw_ordinal, color in recipe.items():
        ordinal = int(raw_ordinal)
        if not 1 <= ordinal <= face_map.Extent():
            raise ValueError("geometry appearance names an absent native face")
        face_colors[_shape_hash(face_map.FindKey(ordinal))] = tuple(float(value) for value in color)
    return face_colors


def _transform_tuple(raw: object) -> tuple[float, ...]:
    if isinstance(raw, list) and len(raw) == 16:
        return tuple(float(value) for value in raw)
    return _IDENTITY_TRANSFORM


def _path_from_occurrence_id(occurrence_id: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in occurrence_id.lstrip("o").split("."))
    except ValueError:
        return (1,)


@dataclass(frozen=True)
class _DocumentReadback:
    """Call-owned native readback and, when available, its exact object closure.

    This never attaches a certificate to the mutable scene. Only the saved
    build's internal readback pipeline retains it; ordinary scene consumers
    receive geometry alone and must derive any subsequent publication anew.
    """

    scene: LoadedStepScene
    tree_hash: str | None = None
    objects: tuple[tuple[str, bytes], ...] = ()

    def canonical_maps(self) -> tuple[dict[str, list[str]], dict[str, str]]:
        if self.tree_hash is None:
            raise ValueError("raw STEP readback has no captured canonical tree")
        tree = json.loads(dict(self.objects)[self.tree_hash])
        leaves: dict[str, list[str]] = {}
        nodes: dict[str, str] = {}

        def visit(node: dict[str, Any]) -> list[str]:
            node_id = node["id"]
            descendants = ([leaf for child in node["children"] for leaf in visit(child)]
                           if node["children"] else [node_id])
            leaves[node_id] = descendants
            nodes[node_id] = node_id
            return descendants

        visit(tree["assembly"]["root"])
        return leaves, nodes

    def restore(self) -> str:
        """Repair this selected closure, components first and tree last."""
        from cadgen.store.objects import put_object

        if self.tree_hash is None:
            raise ValueError("raw STEP readback has no captured canonical tree")
        for digest, payload in self.objects:
            if digest != self.tree_hash:
                put_object(payload, repair=True)
        put_object(dict(self.objects)[self.tree_hash], repair=True)
        return self.tree_hash


def _lookup_document_readback(step_path: Path, *, step_hash: str, lazy: bool = False) -> tuple[_DocumentReadback | None, bool]:
    """Return a private canonical scene and whether an indexed closure failed.

    Only the current document-byte index participates. A missing index is an
    ordinary miss; a missing, damaged or unreadable indexed object requires
    derivation during saved-file republishing, never deleting the object that
    another writer may already have repaired.
    """
    from cadgen.store.records import tree_for_document_hash
    from cadgen._internal.component_package import NativeUnavailable
    from OCP.Standard import Standard_Failure

    tree = tree_for_document_hash(step_hash)
    if not tree:
        return None, False
    try:
        readback = _readback_from_document_tree(step_path, step_hash=step_hash, tree_hash=tree, lazy=lazy)
    except NativeUnavailable:
        # A valid eager-only component promises display, not a native codec.
        # Saved-document readers still have its exact bytes and may parse them.
        # This is neither a corrupt closure nor permission to use a source tree.
        payload = step_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != step_hash:
            return None, False
        readback = _DocumentReadback(_scene_from_selected_bytes(step_path, payload))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, Standard_Failure):
        readback = None
    return readback, readback is None


def lookup_document_scene(step_path: Path, *, step_hash: str, lazy: bool = False) -> tuple[LoadedStepScene | None, bool]:
    """Return private geometry alone; a public scene carries no reuse authority."""
    readback, damaged = _lookup_document_readback(step_path, step_hash=step_hash, lazy=lazy)
    return (readback.scene if readback is not None else None), damaged


def scene_from_render_package(step_path: Path, *, step_hash: str) -> LoadedStepScene | None:
    """A private scene from verified document objects, or None on a cache miss."""
    return lookup_document_scene(step_path, step_hash=step_hash)[0]


def _scene_from_document_tree(step_path: Path, *, step_hash: str, tree_hash: str) -> LoadedStepScene | None:
    readback = _readback_from_document_tree(step_path, step_hash=step_hash, tree_hash=tree_hash)
    return readback.scene if readback is not None else None


def _readback_from_document_tree(step_path: Path, *, step_hash: str, tree_hash: str, lazy: bool = False) -> _DocumentReadback | None:
    from cadgen._internal.component_package import decode_geometry_component
    from cadgen.store.trees import TREE_KIND, capture_tree, _validate_structure

    # Verify and flatten the SAME snapshot. Canonical byte-derived document
    # trees have no source links, so no second tree lookup may occur here.
    descriptor, captured = capture_tree(tree_hash)
    tree = json.loads(captured[tree_hash])
    if not isinstance(tree, dict) or tree.get("kind") != TREE_KIND or tree.get("links"):
        return None
    _validate_structure(tree, native=True)
    assembly = tree.get("assembly")
    if not isinstance(assembly, dict) or not isinstance(assembly.get("root"), dict):
        return None
    pending = [assembly["root"]]
    while pending:
        node = pending.pop()
        if not isinstance(node, dict) or node.get("nodeType") == "link":
            return None
        children = node.get("children") or []
        if not isinstance(children, list):
            return None
        pending.extend(children)
    if not isinstance(descriptor, dict) or descriptor.get("kind") != "assembly-package":
        return None
    components = descriptor.get("components")
    occurrences = descriptor.get("occurrences")
    if not isinstance(components, dict) or not isinstance(occurrences, list) or not occurrences:
        return None

    prototype_shapes: dict[int, Any] = {}
    prototype_names: dict[int, str | None] = {}
    prototype_colors: dict[int, ColorRGBA] = {}
    prototype_face_colors: dict[int, dict[int, ColorRGBA]] = {}
    key_by_cid: dict[str, int] = {}
    lazy_entries = {}
    for cid, entry in components.items():
        if not isinstance(entry, dict):
            return None
        # Each CID gets fresh topology, even when color variants share one
        # immutable BREP object. Nothing native survives this invocation.
        if lazy:
            from cadgen._internal.component_package import NativeUnavailable

            if entry["kind"] == "eager-only":
                raise NativeUnavailable("eager-only component requires a native STEP parse")
            key = len(key_by_cid) + 1
            lazy_entries[key] = (entry, captured[entry["brep"]])
        else:
            shape = decode_geometry_component(entry, captured[entry["brep"]]).wrapped
            key = _shape_hash(shape)
            prototype_shapes[key] = shape
        key_by_cid[str(cid)] = key
        color = entry.get("color")
        if isinstance(color, list) and len(color) == 4:
            prototype_colors[key] = tuple(float(c) for c in color)
        if not lazy:
            face_colors = _face_colors_from_recipe(entry["faceColors"], shape)
            if face_colors:
                prototype_face_colors[key] = face_colors

    occurrence_by_id: dict[str, dict[str, Any]] = {
        str(occ.get("id")): occ for occ in occurrences if isinstance(occ, dict)
    }
    if len(occurrence_by_id) != len(occurrences):
        return None

    def leaf_node(occ: dict[str, Any]) -> OccurrenceNode | None:
        key = key_by_cid.get(str(occ.get("component")))
        if key is None:
            return None
        transform = _transform_tuple(occ.get("transform"))
        name = str(occ.get("name") or "") or None
        color = occ.get("color")
        node = OccurrenceNode(
            path=_path_from_occurrence_id(str(occ.get("id") or "o1")),
            name=name,
            source_name=name,
            transform=transform,
            prototype_key=key,
            local_transform=transform,
            color=tuple(float(c) for c in color) if isinstance(color, list) and len(color) == 4 else None,
            location=_location_from_transform_matrix(transform),
        )
        if name and prototype_names.get(key) is None:
            prototype_names[key] = name
        return node

    assembly = descriptor.get("assembly")
    roots: list[OccurrenceNode]
    if isinstance(assembly, dict) and isinstance(assembly.get("root"), dict):
        def build(tree_node: dict[str, Any]) -> OccurrenceNode | None:
            children_meta = tree_node.get("children") or []
            node_id = str(tree_node.get("id") or "o1")
            if not children_meta:
                occ = occurrence_by_id.get(node_id)
                return leaf_node(occ) if occ is not None else None
            children = [build(c) for c in children_meta]
            if not children or any(child is None for child in children):
                return None
            name = str(tree_node.get("name") or "") or None
            return OccurrenceNode(
                path=_path_from_occurrence_id(node_id),
                name=name,
                source_name=name,
                transform=_IDENTITY_TRANSFORM,
                prototype_key=None,
                local_transform=_IDENTITY_TRANSFORM,
                color=None,
                location=None,
                children=children,
            )

        root = build(assembly["root"])
        if root is None:
            return None
        roots = [root]
    else:
        # Part-kind package: one occurrence holding the whole geometry.
        roots = [node for node in (leaf_node(occ) for occ in occurrences if isinstance(occ, dict)) if node]
        if not roots:
            return None

    scene = LoadedStepScene(
        step_path=step_path,
        roots=roots,
        prototype_shapes=_LazyShapes(lazy_entries) if lazy else prototype_shapes,
        prototype_names=prototype_names,
        prototype_colors=prototype_colors,
        prototype_face_colors=prototype_face_colors,
        step_hash=step_hash,
        source_kind="step",
    )
    return _DocumentReadback(scene, tree_hash, tuple(captured.items()))


def load_step_scene_exact(step_path: Path) -> LoadedStepScene:
    """Parse one immutable snapshot of ``step_path`` and bind its exact digest.

    OCCT accepts a path rather than an in-memory byte buffer.  Read the authored
    document once, parse a private temporary copy of those bytes, then restore
    the authored path on the returned scene.  Replacing the authored file at
    any point cannot make the scene's digest describe different bytes.
    """
    resolved_step_path = step_path.expanduser().resolve()
    if not resolved_step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {resolved_step_path}")
    payload = resolved_step_path.read_bytes()
    return _scene_from_selected_bytes(resolved_step_path, payload)


def _scene_from_selected_bytes(resolved_step_path: Path, payload: bytes) -> LoadedStepScene:
    """The one native parse of already-selected immutable STEP bytes."""
    step_hash = hashlib.sha256(payload).hexdigest()
    snapshot_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="cadgen-step-import-",
            suffix=resolved_step_path.suffix,
            delete=False,
        ) as snapshot:
            snapshot.write(payload)
            snapshot_path = Path(snapshot.name)
        scene = _load_step_scene_text(snapshot_path, record_read=False)
    finally:
        if snapshot_path is not None:
            try:
                os.unlink(snapshot_path)
            except OSError:
                pass
    scene.step_path = resolved_step_path
    scene.step_hash = step_hash
    return scene


def _record_consumed_hash(step_path: Path, step_hash: str) -> None:
    from cadgen.store.closure import note_consumed_file_hash

    note_consumed_file_hash(step_path, step_hash)


def load_step_scene_cached(step_path: Path, *, lazy: bool = False) -> LoadedStepScene:
    """Load a STEP scene through its document-addressed canonical tree.

    A hit reconstructs binary BREP objects (on demand when ``lazy=True``).
    The lazy scene retains its verified immutable byte closure. A miss submits the ordinary
    document compile job, yields any parent build slot while waiting, and then
    reconstructs that same representation.  The caller never returns the
    mutable scene used to publish the tree.
    """
    resolved_step_path = step_path.expanduser().resolve()
    if not resolved_step_path.is_file():
        raise FileNotFoundError(f"STEP file does not exist: {resolved_step_path}")
    # Hash the same byte buffer used to select the artifact.  The compile worker
    # takes its own immutable snapshot; if the authored path changed between
    # these reads, its tree has a different digest and this loop selects again.
    attempts_by_hash: dict[str, int] = {}
    while True:
        payload = resolved_step_path.read_bytes()
        step_hash = hashlib.sha256(payload).hexdigest()
        from_package, damaged_document = lookup_document_scene(resolved_step_path, step_hash=step_hash, lazy=lazy)
        if from_package is not None:
            _record_consumed_hash(resolved_step_path, step_hash)
            return from_package

        from cadgen.daemon import broker
        from cadgen.daemon.executors import submit_compile

        # Keep the previous index while repairing its closure. Forced compile
        # bypasses the reuse gate and atomically replaces the complete result;
        # deleting the pointer would race a writer that had already repaired it.
        job = submit_compile(resolved_step_path, force=damaged_document)
        with broker.yielded():
            code = job.wait()
        if code != 0:
            detail = job.output().rstrip()
            if detail:
                # The compile worker captures the CAD kernel's C-level output so
                # it cannot corrupt a caller's structured stdout.  Preserve that
                # diagnostic stream for people and put only the worker's concise
                # failure reason in the caller's exception/JSON result.
                print(detail, file=sys.stderr)
            from cadgen.daemon.jobs import failure_message

            reason, _error_type = failure_message(detail)
            suffix = f": {reason}" if reason else ""
            raise RuntimeError(f"Could not compile STEP cache for {resolved_step_path}{suffix}")
        from_package, _ = lookup_document_scene(resolved_step_path, step_hash=step_hash, lazy=lazy)
        if from_package is not None:
            _record_consumed_hash(resolved_step_path, step_hash)
            return from_package
        # A replacement raced the submit: the worker correctly published the
        # bytes it snapshotted. A concurrent deletion of derived geometry can
        # also race publication; retry boundedly while these bytes stay current.
        current_hash = hashlib.sha256(resolved_step_path.read_bytes()).hexdigest()
        attempts_by_hash[step_hash] = attempts_by_hash.get(step_hash, 0) + 1
        if current_hash == step_hash and attempts_by_hash[step_hash] >= 3:
            raise RuntimeError(
                f"STEP compile completed without a complete canonical tree for {resolved_step_path}"
            )
