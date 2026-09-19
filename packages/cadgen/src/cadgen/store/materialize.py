"""``materialize(tree)``: a model's geometry from its tree — the contract a parent
composes against.

Rebuilds a build123d ``Compound`` from a tree: canonical component bytes are
cached within a fixed budget, each independent consumer reconstructs fresh
TShapes, and each object is decoded once per descriptor. Components are placed
per the flattened structure, nested
grouping preserved. The result is TAGGED with the tree hash
(``__cadgen_tree__``) so the packager can recognize it intact in a parent's
result and emit a link instead of copying components. The tag is metadata for
the packager, not part of the contract.

The contract a parent may rely on: tree and child order, labels, colors,
placements, exact geometry. Nothing else exists on the returned object — no
sidecar content, no mates, no kinematics.

This module is INTERNAL. Users compose by calling a decorated child; the
wrapper calls this.
"""

from __future__ import annotations

import threading
import hashlib
import weakref
from collections import Counter, OrderedDict
from dataclasses import dataclass, replace
from typing import Any

from cadgen.store.objects import has_object, read_object, read_verified_object

TREE_TAG = "__cadgen_tree__"
PARTNER_TAG = "__cadgen_tree_shape__"
# The materialized compound's OWN location, as a row-major 4x4. A part whose model
# returned a placed shape (``Pos(0, 0, 10) * body``, ``body.moved(...)``) has that
# placement as its tree's root occurrence transform, and materialize reproduces it
# as the compound's location. A parent that places the child composes onto it, so
# the placed compound's location is ``placement * root``; the packager divides the
# root back out when it records the LINK, because the child's tree applies the root
# itself when the link is expanded. Without this the root placement was applied
# twice in every parent that linked such a part.
ROOT_LOC_TAG = "__cadgen_tree_root_loc__"


@dataclass(frozen=True)
class _ComponentIdentity:
    """Canonical extraction identity carried by one materialized leaf.

    These are immutable store addresses, not permission to trust a live TShape.
    The packager may reuse them only after the owning ``_Partner`` verifies the
    complete materialized result against its private baseline.
    """

    cid: str
    content_hash: str
    brep: str
    codec: str
    face_colors: tuple[tuple[int, tuple[float, float, float, float]], ...]

    def entry(self) -> dict[str, Any]:
        return {"kind": "native", "codec": self.codec, "brep": self.brep,
                "faceColors": dict(self.face_colors), "contentHash": self.content_hash}


class _Partner:
    """Immutable evidence of the geometry and hierarchy initially handed out.

    A shared TShape alone is not evidence: native OCCT edits can mutate it,
    and Python descendant metadata can change independently of the native
    compound. Each copy gets its own baseline; no check refreshes the source
    holder in place. Only root placement, label and color are link overrides.
    """

    __slots__ = ("shape", "baseline", "_owner")

    def __init__(self, node: Any) -> None:
        self.shape = node.wrapped
        self.baseline = _capture_materialized_state(node)
        self._owner = weakref.ref(node)

    def retarget(self, node: Any) -> "_Partner":
        """Transfer already verified, freshly materialized data to a lazy shell."""
        holder = object.__new__(type(self))
        holder.shape, holder.baseline = self.shape, self.baseline
        holder._owner = weakref.ref(node)
        return holder

    def intact(self, node: Any) -> bool:
        return self.verified_baseline(node) is not None

    def verified_baseline(self, node: Any) -> "_MaterializedState | None":
        """Return the immutable baseline only when ``node`` still matches it."""
        try:
            if node.wrapped.IsPartner(self.shape) and _same_materialized_state(
                self.baseline, _capture_materialized_state(node)
            ):
                return self.baseline
            return None
        except Exception:  # an unverifiable shape becomes an own component
            return None

    def __copy__(self) -> "_Partner":
        return self

    def __deepcopy__(self, memo: dict) -> "_Partner":
        owner = self._owner()
        copied = memo.get(id(owner)) if owner is not None else None
        if copied is None:
            return self
        holder = self.retarget(copied)
        if self.intact(owner):
            # build123d.moved() deep-copies Python descendants, then restores
            # ONLY the native root's original TShape. Those copied descendants
            # can serialize differently. Bless their new representation only
            # after checking the SOURCE; copying a dirty shape cannot erase
            # the mutation. located() keeps a new root and fails IsPartner.
            copied_state = _capture_materialized_state(copied)
            holder.baseline = replace(
                copied_state, shape=self.baseline.shape,
                geometry=self.baseline.geometry,
                native_children=self.baseline.native_children,
                wrapper_keys=self.baseline.wrapper_keys,
            )
        return holder


@dataclass(frozen=True)
class _MaterializedState:
    shape: Any
    geometry: str | tuple | None
    metadata: tuple
    children: tuple["_MaterializedState", ...]
    native_children: tuple
    wrapper_keys: tuple
    component: _ComponentIdentity | None


def _native_key(shape: Any) -> tuple:
    transform = shape.Location().Transformation()
    return (
        shape.TShape(), int(shape.Orientation()),
        tuple(transform.Value(row, col) for row in (1, 2, 3) for col in (1, 2, 3, 4)),
    )


def _native_children(shape: Any) -> list[Any]:
    from OCP.TopoDS import TopoDS_Iterator

    # Root placement is deliberately absent; the walker composes it itself.
    iterator = TopoDS_Iterator(shape, False, False)
    children = []
    while iterator.More():
        children.append(iterator.Value())
        iterator.Next()
    return children


def _geometry_fingerprint(shape: Any, memo: dict | None = None) -> str | tuple | None:
    """Read geometry through a private topology copy, never change caller flags.

    copyGeom=False shares only curves/surfaces, which this function only reads.
    Every copied TShape is fresh. Meshing data is omitted and Checked is
    normalized on these private TShapes, so measurement/meshing stays intact.

    A native Compound contains only an ordered child graph. Fingerprint that
    graph explicitly, including each child's exact native identity, orientation
    and local placement. This catches structural and aliasing edits without
    serializing all geometry again at every assembly depth. Its native leaves
    are checked even when Python child wrappers no longer share their TShapes.
    The optional memo belongs to this read-only capture only.
    """
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.TopExp import TopExp
    from OCP.TopAbs import TopAbs_COMPOUND
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from cadgen._internal.component_package import _shape_brep_bytes

    if memo is None:
        memo = {}
    key = (shape.TShape(), int(shape.Orientation()))
    if key in memo:
        return memo[key]
    # Mark a native cycle unverifiable rather than recursing without a bound.
    memo[key] = None
    try:
        if shape.ShapeType() == TopAbs_COMPOUND:
            children = tuple(
                (_native_key(child), _geometry_fingerprint(child, memo))
                for child in _native_children(shape)
            )
            result = ("compound", int(shape.Orientation()), children) if all(
                fingerprint is not None for _, fingerprint in children
            ) else None
            memo[key] = result
            return result
        private = BRepBuilderAPI_Copy(shape.Located(TopLoc_Location()), False, False).Shape()
        shapes = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(private, shapes)
        for index in range(1, shapes.Extent() + 1):
            shapes.FindKey(index).Checked(False)
        result = hashlib.sha256(_shape_brep_bytes(private)).hexdigest()
        memo[key] = result
        return result
    except Exception:
        return None


def _materialized_metadata(node: Any, *, root: bool) -> tuple:
    from build123d import Color
    from cadgen._internal.component_package import _MATERIAL_KEYS

    def number(value):
        if type(value) not in (int, float, bool):
            raise ValueError("materialized metadata is not a plain numeric value")
        return float(value)

    # Reading Shape.color would cache an inherited root override onto a child.
    # Compare explicit color state instead, without mutating the source graph.
    color = node.__dict__.get("_color")
    if color is not None and type(color) is not Color:
        raise ValueError("materialized color is not a build123d Color")
    rgba = None if color is None else tuple(float(v) for v in color)
    if "cad_material" in node.__dict__:
        raise ValueError(
            "cad_material authoring was removed; declare named materials with @step(materials=...)"
        )
    authored_material = node.__dict__.get("_cadgen_material")
    if authored_material is None:
        authored_material = {}
    if type(authored_material) is not dict:
        raise ValueError("materialized material is not a plain dictionary")
    material = tuple(sorted(
        (key, min(1.0, max(0.0, number(authored_material[key]))))
        for key in _MATERIAL_KEYS if authored_material.get(key) is not None
    ))
    material_identity = (
        str(authored_material.get("name") or ""),
        str(authored_material.get("baseColor") or ""),
        str(node.__dict__.get("_cadgen_material_id") or ""),
    )
    authored_face_colors = node.__dict__.get("cad_face_ordinal_colors")
    if authored_face_colors is None:
        authored_face_colors = {}
    if type(authored_face_colors) is not dict:
        raise ValueError("materialized face colors are not a plain dictionary")
    face_colors = []
    for key, value in authored_face_colors.items():
        if type(key) is not int or type(value) not in (tuple, list):
            raise ValueError("materialized face color is not a plain ordinal/color pair")
        face_colors.append((key, tuple(number(v) for v in value)))
    face_colors = tuple(sorted(face_colors))
    # Material and per-face overrides have no root-link override surface.
    common = (material, material_identity, face_colors, node.__dict__.get("_occurrence_tree") is not None)
    if root:
        return common
    label = node.__dict__.get("label")
    if label is None:
        label = ""
    if type(label) is not str:
        raise ValueError("materialized label is not a plain string")
    return (label, rgba, _native_key(node.wrapped)[2], *common)


def _capture_materialized_state(
    node: Any, *, root: bool = True, geometry_memo: dict | None = None,
) -> _MaterializedState:
    if geometry_memo is None:
        geometry_memo = {}
    children = tuple(getattr(node, "children", ()) or ())
    shape = node.wrapped
    return _MaterializedState(
        shape=shape,
        geometry=_geometry_fingerprint(shape, geometry_memo),
        metadata=_materialized_metadata(node, root=root),
        children=tuple(
            _capture_materialized_state(child, root=False, geometry_memo=geometry_memo)
            for child in children
        ),
        native_children=tuple(_native_key(child) for child in _native_children(shape)),
        wrapper_keys=tuple(_native_key(child.wrapped) for child in children),
        component=node.__dict__.get("__cadgen_component_identity__"),
    )


def _same_materialized_state(before: _MaterializedState, after: _MaterializedState) -> bool:
    return (
        before.geometry is not None and before.geometry == after.geometry
        and before.metadata == after.metadata
        and len(before.children) == len(after.children)
        and all(_same_materialized_state(a, b) for a, b in zip(before.children, after.children))
    )


def materialized_children(
    node: Any, baseline: _MaterializedState | None,
) -> list[tuple[Any, _MaterializedState | None]]:
    """Reconcile native additions/removals with the handed-out wrapper hierarchy.

    Ordinary wrapper edits remain authoritative. If OCCT changed the same
    native container's child list, surviving original occurrences keep their
    current wrappers/metadata, removed occurrences disappear, and native
    additions get new wrappers. This is a read-only adapter for packaging;
    the author's nodes and parent relationships are never rewritten.
    """
    from OCP.TopAbs import TopAbs, TopAbs_FORWARD, TopAbs_REVERSED, TopAbs_Orientation

    children = list(getattr(node, "children", ()) or ())
    if baseline is None or not baseline.children or not node.wrapped.IsPartner(baseline.shape):
        return [(child, None) for child in children]
    native = _native_children(node.wrapped)
    keys = tuple(_native_key(child) for child in native)
    orientation = node.wrapped.Orientation()
    previous_orientation = TopAbs_Orientation(baseline.geometry[1]) if (
        isinstance(baseline.geometry, tuple) and baseline.geometry[0] == "compound"
    ) else orientation
    delta = TopAbs_FORWARD
    if orientation != previous_orientation:
        if previous_orientation not in (TopAbs_FORWARD, TopAbs_REVERSED):
            raise RuntimeError("cannot reconcile a native orientation edit of an internal/external materialized container")
        delta = orientation if previous_orientation == TopAbs_FORWARD else TopAbs.Reverse_s(orientation)

    def oriented(child: Any, target: Any) -> Any:
        if child.wrapped.Orientation() == target:
            return child
        from cadgen._internal.component_package import _build123d_shape_from_topods

        wrapped = child.wrapped.Oriented(target)
        view = _build123d_shape_from_topods(wrapped)
        view.__dict__.update(child.__dict__)
        view.wrapped = wrapped
        return view

    def placed_orientation(child: Any) -> Any:
        return oriented(child, TopAbs.Compose_s(delta, child.wrapped.Orientation()))

    if keys == baseline.native_children:
        paired = list(zip(children, baseline.children)) if len(children) == len(baseline.children) else [(child, None) for child in children]
        return [(placed_orientation(child), state) for child, state in paired]
    if len(children) != len(baseline.wrapper_keys):
        raise RuntimeError("materialized child has conflicting native and wrapper hierarchy edits")
    before_counts, after_counts = Counter(baseline.native_children), Counter(keys)
    if any(count > 1 and after_counts[key] != count for key, count in before_counts.items()):
        raise RuntimeError("materialized child has an ambiguous native edit of repeated identical occurrences")
    from cadgen._internal.component_package import _build123d_shape_from_topods

    original: dict[tuple, list[int]] = {}
    for index, key in enumerate(baseline.wrapper_keys):
        original.setdefault(key, []).append(index)
    # Reserve every exact surviving slot first. Otherwise an added reversed
    # alias earlier in the native order could steal a later unchanged slot's
    # metadata by looking like an orientation edit.
    exact_slots: list[int | None] = []
    used: set[int] = set()
    for key in keys:
        slots = original.get(key)
        index = slots.pop(0) if slots else None
        exact_slots.append(index)
        if index is not None:
            used.add(index)
    result = []
    for shape, key, index in zip(native, keys, exact_slots):
        if index is not None:
            result.append((placed_orientation(children[index]), baseline.children[index]))
        else:
            # A native orientation edit keeps the same occurrence geometry and
            # local placement. Preserve its wrapper metadata when the original
            # slot is unique; never guess among coincident duplicate slots.
            matches = [
                index for index, previous in enumerate(baseline.wrapper_keys)
                if index not in used and previous[0] == key[0] and previous[2] == key[2]
            ]
            if len(matches) > 1:
                raise RuntimeError("materialized child has an ambiguous native orientation edit")
            if matches:
                index = matches[0]
                used.add(index)
                child = oriented(children[index], shape.Orientation())
                result.append((placed_orientation(child), baseline.children[index]))
            else:
                result.append((placed_orientation(_build123d_shape_from_topods(shape)), None))
    return result

# A process-local cache of immutable canonical BREP bytes. Live OCCT prototypes
# cannot cross materialize() calls: build123d's moved() deliberately shares a
# TShape, whose meshing and bookkeeping are mutable. The old live-shape memo
# let one independent consumer alter another. Keeping bytes saves object reads
# while every consumer receives a fresh reconstruction; on the nine-component
# warm-build fixture that boundary costs about 4 ms per materialization.
#
# 64 MiB is a conservative fraction of the daemon worker's default 2 GiB
# reservation. It bounds Python-owned retention independently of persistent
# store GC; memory-pressure worker recycling reclaims the whole process.
_BREP_BYTES_MEMO_CAPACITY = 64 * 1024 * 1024
_BREP_BYTES_MEMO: OrderedDict[str, bytes] = OrderedDict()
_BREP_BYTES_MEMO_SIZE = 0
_SHAPE_MEMO_LOCK = threading.Lock()


def reset_memo() -> None:
    """Release process-owned canonical bytes and immutable appearance recipes.

    Active consumers own their reconstructed TShapes and remain valid.
    """
    global _BREP_BYTES_MEMO_SIZE
    with _SHAPE_MEMO_LOCK:
        _BREP_BYTES_MEMO.clear()
        _BREP_BYTES_MEMO_SIZE = 0


def _bytes_for_object(digest: str) -> bytes:
    """Canonical bytes for an object that still exists in the store.

    A cached payload never masks manual deletion: a new materialize call must
    fail when its pinned object is gone. Already materialized consumers remain
    self-contained through their own OCCT handles.
    """
    global _BREP_BYTES_MEMO_SIZE
    if not has_object(digest):
        with _SHAPE_MEMO_LOCK:
            stale = _BREP_BYTES_MEMO.pop(digest, None)
            if stale is not None:
                _BREP_BYTES_MEMO_SIZE -= len(stale)
        return read_object(digest)  # raises the store's ordinary missing-object error
    with _SHAPE_MEMO_LOCK:
        cached = _BREP_BYTES_MEMO.get(digest)
        if cached is not None:
            _BREP_BYTES_MEMO.move_to_end(digest)
    if cached is not None:
        return cached
    # A malformed or valid-but-wrong BREP must not enter the byte memo before
    # decoding fails: otherwise same-address atomic repair would leave every
    # later consumer reading the corrupted RAM payload until worker recycling.
    payload = read_verified_object(digest)
    if len(payload) > _BREP_BYTES_MEMO_CAPACITY:
        return payload
    with _SHAPE_MEMO_LOCK:
        existing = _BREP_BYTES_MEMO.get(digest)
        if existing is not None:
            _BREP_BYTES_MEMO.move_to_end(digest)
            return existing
        _BREP_BYTES_MEMO[digest] = payload
        _BREP_BYTES_MEMO_SIZE += len(payload)
        while _BREP_BYTES_MEMO_SIZE > _BREP_BYTES_MEMO_CAPACITY:
            _old_digest, old_payload = _BREP_BYTES_MEMO.popitem(last=False)
            _BREP_BYTES_MEMO_SIZE -= len(old_payload)
    return payload


def _native_location_from_matrix(matrix: list[float]):
    """Validate and construct a placement without importing build123d."""
    from OCP.Standard import Standard_ConstructionError
    from OCP.TopLoc import TopLoc_Location
    from OCP.gp import gp_Trsf

    trsf = gp_Trsf()
    try:
        if isinstance(matrix, (list, tuple)) and len(matrix) >= 12:
            trsf.SetValues(*[float(v) for v in matrix[:12]])
        return TopLoc_Location(trsf)
    except Standard_ConstructionError as error:
        # OCP's Python exception inheritance differs between platform wheels:
        # this error need not derive from Standard_Failure. Invalid placements
        # are a malformed recipe on every platform, so saved readers can repair
        # the derived tree from its STEP bytes instead of failing to open it.
        raise ValueError("invalid geometry transform") from error


def _location_from_matrix(matrix: list[float]):
    from build123d import Location

    return Location(_native_location_from_matrix(matrix))


def _color_from_entry(entry: dict[str, Any]):
    values = entry.get("color")
    if not isinstance(values, (list, tuple)) or len(values) < 3:
        return None
    try:
        from build123d import Color

        return Color(*[float(v) for v in values[:4]])
    except Exception:  # noqa: BLE001 - an unreadable color is no color
        return None


def _material_from_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """A private canonical copy of an occurrence's authored PBR finish."""
    from cadgen._internal.component_package import _MATERIAL_KEYS

    material = entry.get("material")
    if not isinstance(material, dict):
        material = {}
    resolved: dict[str, Any] = {}
    name = entry.get("materialName")
    if not isinstance(name, str) or not name:
        name = material.get("name")
    if isinstance(name, str) and name:
        resolved["name"] = name
    base_color = entry.get("baseColor")
    if not isinstance(base_color, str) or not base_color:
        base_color = material.get("baseColor")
    if isinstance(base_color, str) and base_color:
        resolved["baseColor"] = base_color
    for key in _MATERIAL_KEYS:
        value = material.get(key)
        if value is None:
            continue
        try:
            resolved[key] = min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            continue
    return resolved or None


def tree_tag(shape: Any) -> str | None:
    """The tree hash a materialized compound carries, or None."""
    tag = getattr(shape, TREE_TAG, None)
    return str(tag) if tag else None


def materialize(tree_hash: str, *, label: str | None = None) -> Any:
    """A ``Compound`` for the tree. Raises FileNotFoundError when the tree or a
    component object is missing (the gate should have said stale)."""
    from cadgen.store.trees import capture_tree

    descriptor, payloads = capture_tree(tree_hash)
    return materialize_descriptor(descriptor, captured_objects=payloads, label=label, tree_hash=tree_hash)


def materialize_descriptor(
    descriptor: dict[str, Any],
    *,
    shapes: dict[str, Any] | None = None,
    captured_objects: dict[str, bytes] | None = None,
    label: str | None = None,
    tree_hash: str | None = None,
) -> Any:
    """:func:`materialize` of a FLATTENED descriptor (``flatten``/``flatten_tree``).

    ``shapes`` supplies unlocated build123d shapes by cid for components that
    are not in the store yet — the build's own, before it publishes them
    (``cadgen.store.build`` assembles the STEP it writes from exactly this);
    every other component is read from its declared BREP codec and the
    immutable intrinsic face-color recipe. Each occurrence owns its metadata even when two components
    share identical BREP bytes. The result is tagged as a materialized tree
    only when ``tree_hash`` names one."""
    from build123d import Compound

    from cadgen._internal.component_package import (
        _build123d_shape_from_topods, _normalized_face_colors, decode_geometry_component,
        canonical_json_bytes, effective_face_colors, NativeUnavailable,
    )

    if descriptor.get("appearance") is not None:
        from cadgen._internal.source_sidecar import apply_appearance

        descriptor = apply_appearance(descriptor, descriptor["appearance"])
    components = descriptor.get("components") or {}
    shapes = dict(shapes or {})
    decoded_by_object: dict[str, Any] = {}
    face_colors_by_cid: dict[str, dict[int, tuple[float, float, float, float]]] = {}
    for cid, entry in components.items():
        if entry.get("kind") == "eager-only":
            raise NativeUnavailable("eager-only component has no admitted native representation")
        if entry.get("kind") != "native":
            raise ValueError("unsupported geometry component kind")
        if cid in shapes:
            # Unpublished own shapes have no SURF object yet. Their extraction
            # input is authoritative, and normalization takes a private copy.
            face_colors_by_cid[cid] = _normalized_face_colors(
                getattr(shapes[cid], "cad_face_ordinal_colors", None)
            )
            continue
        brep = str((entry or {}).get("brep") or "")
        if not brep:
            raise FileNotFoundError(f"tree {tree_hash}: component {cid} has no brep object")
        shape = decoded_by_object.get(brep)
        if shape is None:
            shape = decode_geometry_component(entry, captured_objects[brep] if captured_objects is not None else _bytes_for_object(brep))
            decoded_by_object[brep] = shape
        else:
            # Distinct component inputs can share BREP bytes while owning
            # different face colors. XCAF stores those styles on prototype
            # faces: sharing their TShapes would let the last variant overwrite
            # the first during STEP export. Decode once, then give each such
            # component private topology (read-only curves/surfaces may share).
            from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

            shape = _build123d_shape_from_topods(BRepBuilderAPI_Copy(shape.wrapped, False, False).Shape())
        shapes[cid] = shape
        colors = effective_face_colors(shape, entry["faceColors"])
        if canonical_json_bytes(colors) != canonical_json_bytes(entry["faceColors"]):
            raise ValueError("intrinsic recipe names an absent native face")
        face_colors_by_cid[cid] = colors

    placed_by_id: dict[str, Any] = {}
    for occurrence in descriptor.get("occurrences") or []:
        cid = str(occurrence.get("component") or "")
        base = shapes.get(cid)
        if base is None:
            raise FileNotFoundError(f"tree {tree_hash}: missing component {cid}")
        child = base.moved(_location_from_matrix(occurrence.get("transform")))
        child.label = str(occurrence.get("name") or occurrence.get("id") or "")
        color = _color_from_entry(occurrence) or _color_from_entry(components.get(cid) or {})
        if color is not None:
            child.color = color
        face_colors = face_colors_by_cid[cid]
        if face_colors:
            child.cad_face_ordinal_colors = dict(face_colors)
        else:
            child.__dict__.pop("cad_face_ordinal_colors", None)
        material = _material_from_entry(occurrence)
        if material is not None:
            child._cadgen_material = material
            material_id = occurrence.get("materialId")
            if isinstance(material_id, str) and material_id:
                child._cadgen_material_id = material_id
            else:
                child.__dict__.pop("_cadgen_material_id", None)
        else:
            # ``shapes`` may supply a wrapper carrying process-local metadata.
            # The descriptor is authoritative, including an absent finish.
            child.__dict__.pop("_cadgen_material", None)
            child.__dict__.pop("_cadgen_material_id", None)
        content_hash = str((components.get(cid) or {}).get("contentHash") or "")
        brep = str((components.get(cid) or {}).get("brep") or "")
        if content_hash and cid == content_hash[:16] and brep and (components[cid].get("kind") == "native"):
            child.__dict__["__cadgen_component_identity__"] = _ComponentIdentity(
                cid=cid, content_hash=content_hash, brep=brep,
                codec=components[cid]["codec"], face_colors=tuple(sorted(face_colors.items())),
            )
        else:
            child.__dict__.pop("__cadgen_component_identity__", None)
        placed_by_id[str(occurrence.get("id") or "")] = child

    def build_node(node: dict[str, Any]):
        node_type = str(node.get("nodeType") or "")
        node_id = str(node.get("id") or "")
        if node_type == "part" or (not node.get("children") and node_id in placed_by_id):
            return placed_by_id.get(node_id)
        children = [built for child in node.get("children") or [] if (built := build_node(child)) is not None]
        if not children:
            return None
        group = Compound(children=children)
        group.label = str(node.get("name") or node_id)
        return group

    root_node = (descriptor.get("assembly") or {}).get("root")
    compound = build_node(root_node) if isinstance(root_node, dict) else None
    if compound is None:
        children = list(placed_by_id.values())
        compound = children[0] if len(children) == 1 else Compound(children=children)
    compound.label = str(label or descriptor.get("label") or descriptor.get("rootName") or getattr(compound, "label", "") or "model")
    color = _color_from_entry(descriptor)
    if color is not None and getattr(compound, "color", None) is None:
        compound.color = color
    if tree_hash is None:
        return compound
    # Capture only after every descendant placement/label/color is final.
    # The native partner rejects ordinary booleans/copies cheaply; the frozen
    # evidence also catches in-place OCCT edits and Python metadata changes.
    setattr(compound, TREE_TAG, tree_hash)
    setattr(compound, PARTNER_TAG, _Partner(compound))
    setattr(compound, ROOT_LOC_TAG, _matrix_from_location(getattr(compound, "location", None)))
    return compound


def _matrix_from_location(location: Any) -> list[float]:
    from cadgen._internal.component_package import _transform_from_location

    if location is None:
        return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    return [float(v) for v in _transform_from_location(location)]
