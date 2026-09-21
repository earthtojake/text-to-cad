"""Unexposed child references during one ordinary assembly construction.

Only exact, unparented ``LazyCompound`` inputs qualify.  The ordinary constructor
still attaches and validates its children, and resolves their pins in order.
Its native container is postponed until native access.  No retained native
shape is shared: forcing uses the same private children as normal construction.

The packager can read exact links while neither container nor child has exposed
native geometry.  A native read/write, copy, or ordinary hierarchy edit ends
that opportunity.  This is process state, never a persistent cache or an author
API.  The small subclass is replaced with plain Compound only after installing
the same native container the original constructor would have made.
"""

from __future__ import annotations

import inspect
import threading
from typing import Any

from build123d import Compound

_ENABLED = True
_MAX_CHILDREN = 64
_SIGNATURE = inspect.signature(Compound.__init__)
_STATE = threading.local()


def _plain_child(child: Any, frame: Any) -> bool:
    from build123d import Color, Location, Pos, Rot
    from cadgen.store.lazy import LazyCompound

    if type(child) is not LazyCompound:
        return False
    raw = child.__dict__
    return (
        raw.get("_lazy_frame") is frame
        and raw.get("_lazy_shape") is None
        and not raw.get("_lazy_forcing")
        and type(raw.get("label")) is str
        and (raw.get("_color") is None or type(raw["_color"]) is Color)
        and (raw.get("_lazy_placement") is None or type(raw["_lazy_placement"]) in (Location, Pos, Rot))
        and not raw.get("_NodeMixin__children")
        and not any(key in raw for key in (
            "cad_material", "_cadgen_material", "_cadgen_material_id",
            "cad_face_ordinal_colors", "_occurrence_tree",
            "__cadgen_tree__", "__cadgen_tree_shape__", "__cadgen_tree_root_loc__",
            "__cadgen_component_identity__",
        ))
    )


def initial_attachment(parent: Any) -> bool:
    """Only suppress the original hooks while their native inputs are hidden."""
    return type(parent) is _ReferenceCompound and parent.__dict__.get("_reference_initializing", False)


def attach_child(child: Any, parent: Any) -> bool:
    """Resolve in the original attach order and apply ordinary root metadata."""
    if not initial_attachment(parent):
        return False
    from build123d import Location
    from OCP.TopLoc import TopLoc_Location
    from cadgen.store.materialize import _location_from_matrix, _matrix_from_location
    from cadgen._internal.component_package import _transform_from_location
    from cadgen.store.trees import capture_tree

    # A current pin was resolved at the decorated call.  One verified snapshot
    # owns every use of that exact tree within this private construction.  A
    # queued job still resolves in ordinary order, even if another input already
    # captured the tree it eventually returns.
    tree = child.__dict__.get("_lazy_tree")
    if tree is None:
        tree = child.tree_hash()
    descriptors = parent.__dict__["_reference_descriptors"]
    snapshot = descriptors.get(tree)
    if snapshot is None:
        try:
            snapshot = capture_tree(tree)
        except (OSError, ValueError):
            child.tree_hash()  # preserve the ordinary missing-pin diagnostic
            raise
        descriptors[tree] = snapshot
    descriptor = snapshot[0]
    parent.__dict__["_reference_pins"].append(tree)
    if not child.label:
        child.label = child.__dict__["_lazy_label"] or descriptor.get("label") or descriptor.get("rootName") or "model"
    if child.color is None:
        color = _root_color(descriptor)
        if color is not None:
            child.color = color
    placement = child.__dict__.get("_lazy_placement")
    if placement is not None:
        # Location is mutable.  The original constructor consumed its value at
        # this point; later edits to the author's Location must not move a child
        # already attached to this assembly.
        placement = Location(placement.wrapped.Multiplied(TopLoc_Location()))
        child.__dict__["_lazy_placement"] = placement
    root = (descriptor.get("assembly") or {}).get("root") or {}
    root_loc = Location()
    if root.get("nodeType") == "part":
        for occurrence in descriptor.get("occurrences") or ():
            if occurrence.get("id") == root.get("id"):
                root_loc = _location_from_matrix(occurrence["transform"])
                break
    # Preserve the exact arithmetic of ordinary _walk/_add_link, including
    # cancelling the child's native root location through its serialized tag.
    world = Location() * ((placement * root_loc) if placement is not None else root_loc)
    transform = world * _location_from_matrix(_matrix_from_location(root_loc)).inverse()
    parent.__dict__["_reference_transforms"].append(_transform_from_location(transform))
    child.__dict__["_lazy_reference_attached"] = True
    return True


def force_parent(parent: Any) -> None:
    if (type(parent) is _ReferenceCompound and not initial_attachment(parent)
            and not parent.__dict__.get("_reference_forcing", False)):
        parent._force_reference()


class _ReferenceCompound(Compound):
    @property
    def _wrapped(self):
        if self.__dict__.get("_reference_initializing", False):
            return self.__dict__.get("_reference_shape")
        self._force_reference()
        return self.__dict__["_wrapped"]

    @_wrapped.setter
    def _wrapped(self, shape):
        if self.__dict__.get("_reference_initializing", False):
            self.__dict__["_reference_shape"] = shape
        else:
            self._become_native(shape)

    @_wrapped.deleter
    def _wrapped(self):
        self._force_reference()
        del self.__dict__["_wrapped"]

    def _become_native(self, shape):
        # No author callback runs between installing the native value and
        # restoring its normal class.  Existing children/parents keep identity.
        for key in tuple(self.__dict__):
            if key.startswith("_reference_"):
                del self.__dict__[key]
        self.__dict__["_wrapped"] = shape
        self.__class__ = Compound

    def _force_reference(self):
        from build123d.topology.utils import _make_topods_compound_from_shapes

        if self.__dict__.get("_reference_forcing", False):
            raise RuntimeError("reference assembly forced re-entrantly")
        self.__dict__["_reference_forcing"] = True
        try:
            # These are the initial native inputs.  A direct plain-Shape parent
            # edit can alter only anytree metadata in build123d; preserve that
            # distinction until an ordinary attachment hook rebuilds the native
            # container.  Compound/LazyCompound hierarchy edits force first.
            shape = self.__dict__.get("_reference_shape")
            if shape is None:
                shape = _make_topods_compound_from_shapes([
                    child.wrapped for child in self.__dict__["_reference_inputs"]
                ])
            self._become_native(shape)
        finally:
            self.__dict__.pop("_reference_forcing", None)

    @property
    def children(self):
        return Compound.children.fget(self)

    @children.setter
    def children(self, values):
        if not initial_attachment(self):
            self._force_reference()
        Compound.children.fset(self, values)

    @children.deleter
    def children(self):
        if not initial_attachment(self):
            self._force_reference()
        Compound.children.fdel(self)

    def _post_attach_children(self, children):
        if not initial_attachment(self):
            return Compound._post_attach_children(self, children)

    def __deepcopy__(self, memo):
        self._force_reference()
        return Compound.__deepcopy__(self, memo)

    def __reduce_ex__(self, protocol):
        self._force_reference()
        return self.__reduce_ex__(protocol)


def try_construct(owner: Any, original: Any, args: tuple, kwargs: dict) -> bool:
    """Initialize an eligible Compound, otherwise leave it wholly untouched."""
    if not _ENABLED or type(owner) is not Compound or getattr(_STATE, "constructing", False):
        return False
    obj = args[0] if args else kwargs.get("obj")
    parent = args[5] if len(args) > 5 else kwargs.get("parent")
    children = args[6] if len(args) > 6 else kwargs.get("children")
    if obj is not None or parent is not None or type(children) not in (list, tuple):
        return False
    if not 2 <= len(children) <= _MAX_CHILDREN:
        return False
    from cadgen.authoring import current_frame

    frame = current_frame()
    if frame is None:
        return False
    inputs = tuple(children)
    if len({id(child) for child in inputs}) != len(inputs) or not all(
        _plain_child(child, frame) and child.__dict__.get("_NodeMixin__parent") is None
        for child in inputs
    ):
        return False
    # Validate the complete Python call before changing the instance class.
    _SIGNATURE.bind(owner, *args, **kwargs)
    owner.__class__ = _ReferenceCompound
    owner.__dict__.update(_reference_initializing=True, _reference_inputs=inputs,
                          _reference_frame=frame, _reference_shape=None,
                          _reference_descriptors={}, _reference_transforms=[],
                          _reference_pins=[])
    _STATE.constructing = True
    try:
        original(owner, *args, **kwargs)
    except BaseException:
        # Construction failed; no lazy subclass with half-attached ownership
        # escapes.  The original constructor owns its anytree rollback rules.
        owner._become_native(owner.__dict__.get("_reference_shape"))
        raise
    finally:
        owner.__dict__.pop("_reference_initializing", None)
        owner.__dict__.pop("_reference_descriptors", None)
        _STATE.constructing = False
    return True


def _root_color(descriptor: dict) -> Any:
    """The root color materialize_descriptor would expose, without geometry."""
    from cadgen.store.materialize import _color_from_entry

    root = (descriptor.get("assembly") or {}).get("root") or {}
    if root.get("nodeType") == "part":
        for occurrence in descriptor.get("occurrences") or ():
            if occurrence.get("id") == root.get("id"):
                entry = (descriptor.get("components") or {}).get(occurrence["component"], {})
                return _color_from_entry(occurrence) or _color_from_entry(entry) or _color_from_entry(descriptor)
    return _color_from_entry(descriptor)


def _inputs(owner: Any) -> tuple | None:
    """Current unexposed wrappers, without reading their disk geometry."""
    if type(owner) is not _ReferenceCompound:
        return None
    from cadgen.authoring import current_frame

    raw = owner.__dict__
    frame = raw.get("_reference_frame")
    children = tuple(owner.children)
    initial = raw["_reference_inputs"]
    active_frame = current_frame()
    if ((active_frame is not None and frame is not active_frame) or len(children) != len(initial)
            or raw.get("_reference_shape") is not None
            or any(a is not b for a, b in zip(children, initial))
            or not all(_plain_child(child, frame) for child in children)
            or any(child.__dict__.get("_lazy_tree") != tree for child, tree in zip(children, raw["_reference_pins"]))
            or raw.get("_occurrence_tree") is not None
            or any(key in raw for key in ("__cadgen_tree__", "__cadgen_tree_shape__", "__cadgen_tree_root_loc__"))):
        return None
    return children


def links(owner: Any) -> list[dict] | None:
    """Current link rows for an entirely unexposed initial assembly, or None.

    A new packaging snapshot verifies every unique pin again; retained
    references cannot conceal deletion, corruption, or a child job's failure.
    Repeated occurrences in this one read share that same verified snapshot.
    The final source publisher separately validates its full required closure.
    """
    children = _inputs(owner)
    if children is None:
        return None
    from cadgen._internal.component_package import _occurrence_color

    raw = owner.__dict__
    verified = set()
    result = []
    for index, child in enumerate(children, 1):
        tree = child.__dict__["_lazy_tree"]
        if tree not in verified:
            child.tree_hash()
            verified.add(tree)
        row = {"id": f"o1.{index}", "name": child.label or f"o1.{index}",
               "tree": tree, "transform": list(raw["_reference_transforms"][index - 1])}
        color = _occurrence_color(child)
        if color is not None:
            row["color"] = color
        result.append(row)
    return result


def source_scene(owner: Any, output_path: Any):
    """An invocation-owned source scene for the explicit publication pipeline.

    Native scene/export callers do not opt in.  The build pipeline needs real
    occurrence/topology/appearance data for its adaptive edge policy, but no
    initial XCAF document.  One private native decode per component supplies
    it.  Separate child calls keep separate prototype keys, just as their
    ordinary private materializations would, so topology counts do not change.
    The only consumers before final publication read these native shapes;
    saving reconstructs its own private canonical document as before.
    """
    children = _inputs(owner)
    if children is None:
        return None
    from build123d import Location
    from cadgen._internal.component_package import decode_geometry_component
    from cadgen._internal.step_scene_loader import _location_transform_matrix
    from cadgen._internal.step_scene_package import _face_colors_from_recipe
    from cadgen._internal.step_scene_types import LoadedStepScene, OccurrenceNode, _identity_transform_matrix
    from cadgen.store.materialize import _location_from_matrix
    from cadgen.store.trees import capture_tree

    scene = LoadedStepScene(output_path.expanduser().resolve(), [], {}, source_kind="python")
    descriptors, decoded = {}, {}
    groups = []
    for child_index, child in enumerate(children, 1):
        tree = child.__dict__["_lazy_tree"]
        if tree not in descriptors:
            try:
                descriptors[tree] = capture_tree(tree)
            except (OSError, ValueError):
                child.tree_hash()  # preserve the ordinary missing-pin diagnostic
                raise
        descriptor, payloads = descriptors[tree]
        occurrences = {row["id"]: row for row in descriptor["occurrences"]}
        keys = {}
        placement = child.__dict__.get("_lazy_placement")
        placement = placement if placement is not None else Location()
        for cid, entry in descriptor["components"].items():
            identity = entry["contentHash"]
            if identity not in decoded:
                decoded[identity] = decode_geometry_component(entry, payloads[entry["brep"]]).wrapped
            native = decoded[identity]
            key = len(scene.prototype_shapes) + 1
            keys[cid] = key
            scene.prototype_shapes[key] = native
            if entry.get("color") is not None:
                scene.prototype_colors[key] = tuple(entry["color"])
            colors = _face_colors_from_recipe(entry["faceColors"], native)
            if colors:
                scene.prototype_face_colors[key] = colors

        def group(node, path, *, child_root=False):
            occurrence = occurrences.get(node["id"])
            name = child.label if child_root else node.get("name")
            if occurrence is not None:
                key = keys[occurrence["component"]]
                local = _location_from_matrix(occurrence["transform"])
                world = placement * local
                color = child.color if child_root else None
                color = tuple(color) if color is not None else occurrence.get("color")
                if color is None:
                    color = scene.prototype_colors.get(key)
                if color is None and child.color is not None:
                    color = tuple(child.color)
                scene.prototype_names.setdefault(key, name)
                return OccurrenceNode(
                    path=path, name=name, source_name=name,
                    transform=_location_transform_matrix(world.wrapped),
                    local_transform=_location_transform_matrix((world if child_root else local).wrapped),
                    prototype_key=key, color=tuple(color) if color is not None else None,
                    location=world.wrapped,
                )
            children = [group(item, (*path, index)) for index, item in enumerate(node.get("children") or (), 1)]
            return OccurrenceNode(
                path=path, name=name, source_name=name, prototype_key=None,
                transform=_location_transform_matrix(placement.wrapped),
                local_transform=_location_transform_matrix(placement.wrapped) if child_root else _identity_transform_matrix(),
                color=tuple(child.color) if child_root and child.color is not None else None,
                location=placement.wrapped, children=children,
            )

        groups.append(group(descriptor["assembly"]["root"], (1, child_index), child_root=True))
    scene.roots = [OccurrenceNode(
        path=(1,), name=owner.label or None, source_name=owner.label or None,
        transform=_identity_transform_matrix(), prototype_key=None,
        color=tuple(owner.color) if owner.color is not None else None, children=groups,
    )]
    return scene
