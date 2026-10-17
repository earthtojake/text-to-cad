"""Reconstruct a loaded STEP scene from its tree.

The tree a document's bytes map to (``index/document``) already stores the native
scene inputs: each unique prototype's encoded BREP object and effective face-color
recipe, plus the occurrence hierarchy with names, transforms and colors. So the tree
is the warm-load cache; there is no second geometry store. ``load_step_scene_cached``
skips the text-STEP parse by reading the tree; a STEP with no current tree pays one
full parse, and the tree its compile publishes then makes the next load warm. The
tree is the result a build wrote the file from, read flattened -- the hierarchy the
writer wrote -- or, for a file that does not hold it or that no build of this store
wrote, the compile of the file's own bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cadgen._internal.atomic_replace import read_bytes_with_ladder
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


def lookup_document_scene(step_path: Path, *, step_hash: str, lazy: bool = False) -> tuple[LoadedStepScene | None, bool]:
    """A private scene of the tree the bytes ``step_hash`` map to, and whether that tree
    failed to read: ``(None, False)`` for bytes no entry maps, ``(None, True)`` for a
    missing, damaged or unreadable tree (the caller compiles the bytes again, never
    deleting an object another writer may already have repaired). A scene carries no
    reuse authority: its consumers derive any publication anew."""
    from cadgen.store.records import tree_for_document_hash
    from cadgen._internal.component_package import NativeUnavailable
    from OCP.Standard import Standard_Failure

    tree = tree_for_document_hash(step_hash)
    if not tree:
        return None, False
    try:
        scene = _scene_from_document_tree(step_path, step_hash=step_hash, tree_hash=tree, lazy=lazy)
    except NativeUnavailable:
        # A valid eager-only component promises display, not a native codec.
        # Saved-document readers still have its exact bytes and may parse them.
        # This is neither a corrupt closure nor permission to use a source tree.
        payload = read_bytes_with_ladder(step_path)
        if hashlib.sha256(payload).hexdigest() != step_hash:
            return None, False
        return _scene_from_selected_bytes(step_path, payload), False
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, Standard_Failure):
        scene = None
    return scene, scene is None


def scene_from_render_package(step_path: Path, *, step_hash: str) -> LoadedStepScene | None:
    """A private scene from verified document objects, or None on a cache miss."""
    return lookup_document_scene(step_path, step_hash=step_hash)[0]


def _scene_from_document_tree(step_path: Path, *, step_hash: str, tree_hash: str,
                              lazy: bool = False) -> LoadedStepScene | None:
    from cadgen._internal.component_package import decode_geometry_component
    from cadgen.store.trees import TREE_KIND, capture_tree, _validate_structure

    # Verify and flatten the SAME snapshot. A tree that links its children's reads
    # flattened: the hierarchy the file was written with.
    descriptor, captured = capture_tree(tree_hash)
    tree = json.loads(captured[tree_hash])
    if not isinstance(tree, dict) or tree.get("kind") != TREE_KIND:
        return None
    _validate_structure(tree, native=True)
    if not isinstance(descriptor, dict) or descriptor.get("kind") != "assembly-package":
        return None
    components = descriptor.get("components")
    occurrences = descriptor.get("occurrences")
    if not isinstance(components, dict) or not isinstance(occurrences, list) or not occurrences:
        return None

    from cadgen._internal.component_package import read_lineage

    prototype_shapes: dict[int, Any] = {}
    prototype_names: dict[int, str | None] = {}
    prototype_identity: dict[int, tuple[str | None, dict[str, Any] | None]] = {}
    prototype_components: dict[int, tuple[str, str]] = {}
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
        prototype_components[key] = (str(entry["codec"]), str(entry["brep"]))
        if entry.get("construction") or entry.get("lineage"):
            prototype_identity[key] = (entry.get("construction"),
                                       read_lineage(captured[entry["lineage"]]) if entry.get("lineage") else None)
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

    def leaf_node(occ: dict[str, Any], path: tuple[int, ...]) -> OccurrenceNode | None:
        key = key_by_cid.get(str(occ.get("component")))
        if key is None:
            return None
        transform = _transform_tuple(occ.get("transform"))
        name = str(occ.get("name") or "") or None
        color = occ.get("color")
        node = OccurrenceNode(
            path=path,
            name=name,
            source_name=name,
            transform=transform,
            prototype_key=key,
            local_transform=transform,
            color=tuple(float(c) for c in color) if isinstance(color, list) and len(color) == 4 else None,
            location=_location_from_transform_matrix(transform),
            id=str(occ.get("id") or "") or None,
        )
        if name and prototype_names.get(key) is None:
            prototype_names[key] = name
        return node

    assembly = descriptor.get("assembly")
    roots: list[OccurrenceNode]
    if isinstance(assembly, dict) and isinstance(assembly.get("root"), dict):
        # A scene names its nodes by position (the STEP reader's paths); the tree's
        # tokens are the document's names for them, and the two are joined by position.
        def build(tree_node: dict[str, Any], path: tuple[int, ...]) -> OccurrenceNode | None:
            children_meta = tree_node.get("children") or []
            node_id = str(tree_node.get("id") or "")
            if not children_meta:
                occ = occurrence_by_id.get(node_id)
                return leaf_node(occ, path) if occ is not None else None
            children = [build(c, (*path, index)) for index, c in enumerate(children_meta, start=1)]
            if not children or any(child is None for child in children):
                return None
            name = str(tree_node.get("name") or "") or None
            return OccurrenceNode(
                path=path,
                name=name,
                source_name=name,
                transform=_IDENTITY_TRANSFORM,
                prototype_key=None,
                local_transform=_IDENTITY_TRANSFORM,
                color=None,
                location=None,
                children=children,
                id=node_id or None,
            )

        root = build(assembly["root"], (1,))
        if root is None:
            return None
        roots = [root]
    else:
        # Part-kind package: one occurrence holding the whole geometry.
        roots = [node for node in (leaf_node(occ, (index,)) for index, occ in enumerate(occurrences, start=1)
                                   if isinstance(occ, dict)) if node]
        if not roots:
            return None

    return LoadedStepScene(
        step_path=step_path,
        roots=roots,
        prototype_shapes=_LazyShapes(lazy_entries) if lazy else prototype_shapes,
        prototype_names=prototype_names,
        prototype_colors=prototype_colors,
        prototype_face_colors=prototype_face_colors,
        prototype_identity=prototype_identity,
        prototype_components=prototype_components,
        step_hash=step_hash,
        source_kind="step",
    )


def scene_tokens(scene: LoadedStepScene) -> None:
    """Name every node of a parsed scene by the token the document tree built from it
    would give it (``cadgen.store.build._document_walk``'s structure and names:
    ``part``, ``group`` and ``model`` for products the STEP gives no name, several free
    roots under a synthetic ``model`` root), on each node's ``id``; a file of one placed
    part is that part, its wrapper dropped from the scene's roots
    (``step_scene_loader.document_roots``). A scene from a document tree already carries
    them."""
    from cadgen._internal.step_scene_loader import document_roots
    from cadgen._internal.tree_tokens import assign_tokens

    occurrences: list[dict] = []
    counter = [0]

    def provisional() -> str:
        counter[0] += 1
        return f"p{counter[0]}"

    def collect(node: OccurrenceNode) -> dict:
        node_id = provisional()
        if node.children:
            return {"id": node_id, "node": node, "name": str(node.name or node.source_name or "group"),
                    "children": [collect(child) for child in node.children]}
        occurrences.append({"id": node_id, "transform": list(node.transform)})
        return {"id": node_id, "node": node, "name": str(node.name or node.source_name or "part"), "children": []}

    roots = scene.roots = document_roots(scene.roots)
    if not roots:
        return
    if len(roots) == 1:
        root = collect(roots[0])
        if roots[0].children:
            root["name"] = str(roots[0].name or roots[0].source_name or "model")
    else:
        root = {"id": provisional(), "node": None, "name": "model", "children": [collect(node) for node in roots]}
    mapping = assign_tokens(root, occurrences, [], label=root["name"])

    def apply(entry: dict) -> None:
        if entry["node"] is not None:
            entry["node"].id = mapping[entry["id"]]
        for child in entry["children"]:
            apply(child)

    apply(root)


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
    # On Windows a program saving, replacing or scanning the document refuses this read for a
    # moment (`[Errno 13]`): the ladder waits that out, as it does for every STEP cadgen reopens.
    payload = read_bytes_with_ladder(resolved_step_path)
    return _scene_from_selected_bytes(resolved_step_path, payload)


def _scene_from_selected_bytes(resolved_step_path: Path, payload: bytes) -> LoadedStepScene:
    """The one native parse of already-selected immutable STEP bytes."""
    from cadgen._internal.temp_leftovers import STEP_IMPORT_PREFIX, owned_prefix

    step_hash = hashlib.sha256(payload).hexdigest()
    snapshot_path: Path | None = None
    try:
        # Named after this process: a worker killed mid-parse (its caller left) never
        # reaches the unlink below, and the next worker's sweep removes the copy.
        with tempfile.NamedTemporaryFile(
            prefix=owned_prefix(STEP_IMPORT_PREFIX),
            suffix=resolved_step_path.suffix,
            delete=False,
        ) as snapshot:
            snapshot_path = Path(snapshot.name)
            snapshot.write(payload)
        # The kernel reads our private snapshot; a failure names the USER's file.
        scene = _load_step_scene_text(snapshot_path, named=resolved_step_path)
    finally:
        if snapshot_path is not None:
            try:
                os.unlink(snapshot_path)
            except OSError:
                pass
    scene.step_path = resolved_step_path
    scene.step_hash = step_hash
    return scene


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
        payload = read_bytes_with_ladder(resolved_step_path)
        step_hash = hashlib.sha256(payload).hexdigest()
        # An export's entry is pending until its verify answers: confirmed first; one whose
        # verify could not answer is compiled, as for a miss.
        from cadgen.store.exports import confirm_document
        from cadgen.store.records import tree_for_document_hash

        damaged_document = False
        tree = tree_for_document_hash(step_hash)
        if tree is None or confirm_document(resolved_step_path, step_hash, tree) is not None:
            from_package, damaged_document = lookup_document_scene(resolved_step_path, step_hash=step_hash, lazy=lazy)
            if from_package is not None:
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
            return from_package
        # A replacement raced the submit: the worker correctly published the
        # bytes it snapshotted. A concurrent deletion of derived geometry can
        # also race publication; retry boundedly while these bytes stay current.
        current_hash = hashlib.sha256(read_bytes_with_ladder(resolved_step_path)).hexdigest()
        attempts_by_hash[step_hash] = attempts_by_hash.get(step_hash, 0) + 1
        if current_hash == step_hash and attempts_by_hash[step_hash] >= 3:
            raise RuntimeError(
                f"STEP compile completed without a complete canonical tree for {resolved_step_path}"
            )
