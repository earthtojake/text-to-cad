"""Bounded private preparation during a model's ordered Compound construction.

The constructor hook is permanent and idempotent. Its only active state belongs
to one constructor on one thread, inside an existing authoring build frame.
Prepared shapes never become a native cache or an exposed LazyCompound early.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import functools
import json
import threading
from typing import Any

_MAX_INPUTS = 128
_MAX_PREPARED = 8
_MAX_BREP_BYTES = 768 * 1024
_MAX_SURF_BYTES = 4 * 1024 * 1024
_MAX_TREE_BYTES = 64 * 1024
_MAX_COMPONENTS = 16
_MAX_OCCURRENCES = 64
_STATE = threading.local()
_INSTALL_LOCK = threading.Lock()


@dataclass
class _Prepared:
    owner: Any
    tree: str
    label: str
    private: Any
    objects: tuple[str, ...]


@dataclass
class _Construction:
    inputs: tuple
    frame: Any
    unparented: bool = False
    prepared: dict[int, _Prepared] = field(default_factory=dict)
    attempted: bool = False
    brep_bytes: int = 0
    surf_bytes: int = 0


def _budget(tree: str):
    """Admit a small, unlinked tree using verified immutable byte lengths.

    Serialized size and shape counts bound speculative work, not native RSS.
    The verified root snapshot also becomes the materializer's exact input.
    """
    from cadgen.store.objects import object_path, read_verified_object

    if object_path(tree).stat().st_size > _MAX_TREE_BYTES:
        return None
    payload = read_verified_object(tree)
    if len(payload) > _MAX_TREE_BYTES:
        return None
    data = json.loads(payload)
    from cadgen.store.trees import _validate_structure
    _validate_structure(data)
    if data.get("links"):
        return None
    components = data.get("components") or {}
    occurrences = data.get("occurrences") or []
    if not components or len(components) > _MAX_COMPONENTS or len(occurrences) > _MAX_OCCURRENCES:
        return None
    breps, surfs = set(), set()
    for entry in components.values():
        breps.add(entry["brep"])
        if entry.get("eagerSurface"):
            surfs.add(entry["eagerSurface"])

    def verified_size(digests, limit):
        total = 0
        for digest in sorted(digests):
            remaining = limit - total
            # Reject ordinary oversized inputs cheaply, but charge actual bytes:
            # a short corrupt file may be repaired or coexist with a larger,
            # previously verified BREP byte entry in memory.
            if object_path(digest).stat().st_size > remaining:
                return None
            payload = read_verified_object(digest)
            if len(payload) > remaining:
                return None
            total += len(payload)
        return total

    brep_bytes = verified_size(breps, _MAX_BREP_BYTES)
    if brep_bytes is None:
        return None
    surf_bytes = verified_size(surfs, _MAX_SURF_BYTES)
    if surf_bytes is None:
        return None
    from cadgen._internal.component_package import validate_geometry_component
    for cid, entry in components.items():
        validate_geometry_component(entry, read_verified_object(entry["brep"]), cid=cid)
    return brep_bytes, surf_bytes, (tree, *sorted(breps | surfs)), data


def _materialize_snapshot(tree, label, snapshot):
    from cadgen.store.materialize import materialize_descriptor
    from cadgen.store.trees import flatten_tree

    return materialize_descriptor(flatten_tree(snapshot, tree_hash=tree), label=label, tree_hash=tree)


def _active_construction():
    construction = getattr(_STATE, "construction", None)
    if construction is not None:
        from cadgen.authoring import current_frame

        if construction.frame is current_frame():
            return construction
    return None


def prepare_for(waiting) -> None:
    """Prepare later pinned inputs before the original input yields its slot."""
    construction = _active_construction()
    if construction is None:
        return
    state = waiting.__dict__
    job = state.get("_lazy_job")
    if (construction.attempted or state.get("_lazy_forcing")
            or state.get("_lazy_tree") is not None or job is None or job.result_ready):
        return
    index = next((i for i, child in enumerate(construction.inputs) if child is waiting), None)
    if index is None or state.get("_lazy_frame") is not construction.frame:
        return
    construction.attempted = True
    attempts = 0
    for child in construction.inputs[index + 1:]:
        if attempts >= _MAX_PREPARED:
            break
        if id(child) in construction.prepared:
            continue
        raw = child.__dict__
        tree, label = raw.get("_lazy_tree"), raw.get("_lazy_label")
        if (type(tree) is not str or type(label) is not str or raw.get("_lazy_shape") is not None
                or raw.get("_lazy_forcing") or raw.get("_lazy_frame") is not construction.frame):
            continue
        if construction.unparented and raw.get("_NodeMixin__parent") is not None:
            continue
        # Only internal captured pins are read. Authored placement and metadata,
        # and unresolved job results, remain untouched until ordinary forcing.
        attempts += 1
        try:
            budget = _budget(tree)
            if budget is None:
                continue
            brep_bytes, surf_bytes, objects, snapshot = budget
            if (construction.brep_bytes + brep_bytes > _MAX_BREP_BYTES
                    or construction.surf_bytes + surf_bytes > _MAX_SURF_BYTES):
                continue
            private = _materialize_snapshot(tree, label, snapshot)
        except Exception:
            # The original ordered force still decides whether this child fails.
            # A repair may make that later read succeed at the same exact pin.
            continue
        construction.prepared[id(child)] = _Prepared(child, tree, label, private, objects)
        construction.brep_bytes += brep_bytes
        construction.surf_bytes += surf_bytes


def take_prepared(owner, tree: str, label: str):
    """Consume only this wrapper's exact preparation after its normal pin check."""
    construction = _active_construction()
    if construction is None:
        return None
    prepared = construction.prepared.pop(id(owner), None)
    if (prepared is None or prepared.owner is not owner or prepared.tree != tree
            or type(label) is not str or prepared.label != label):
        return None
    from cadgen.store.objects import read_verified_object

    try:
        for digest in prepared.objects:
            read_verified_object(digest)
    except Exception:
        # Current object loss/corruption cannot be hidden by prepared geometry.
        # The caller follows its ordinary materialization path at the same pin.
        return None
    return prepared.private


def install() -> bool:
    """Install once; no build installs/restores process-global methods."""
    from build123d import Compound

    with _INSTALL_LOCK:
        original = Compound.__init__
        if getattr(original, "__cadgen_ready_children__", False):
            return False

        @functools.wraps(original)
        def construct(self, *args, **kwargs):
            if type(self) is not Compound or getattr(_STATE, "construction", None) is not None:
                return original(self, *args, **kwargs)
            from cadgen.store._references import try_construct

            if try_construct(self, original, args, kwargs):
                return None
            obj = args[0] if args else kwargs.get("obj")
            unparented = False
            if type(obj) in (list, tuple):
                supplied = obj
            elif obj is None:
                parent = args[5] if len(args) > 5 else kwargs.get("parent")
                children = args[6] if len(args) > 6 else kwargs.get("children")
                if parent is not None or type(children) not in (list, tuple):
                    return original(self, *args, **kwargs)
                supplied, unparented = children, True
            else:
                return original(self, *args, **kwargs)
            if not 1 < len(supplied) <= _MAX_INPUTS:
                return original(self, *args, **kwargs)
            from cadgen.authoring import current_frame
            from cadgen.store.lazy import LazyCompound

            frame = current_frame()
            if frame is None:
                return original(self, *args, **kwargs)
            inputs = tuple(supplied)
            if not 1 < len(inputs) <= _MAX_INPUTS or not all(type(child) is LazyCompound for child in inputs):
                return original(self, *args, **kwargs)
            if unparented and (
                len({id(child) for child in inputs}) != len(inputs)
                or any(child.__dict__.get("_NodeMixin__parent") is not None for child in inputs)
            ):
                return original(self, *args, **kwargs)
            # The original children setter still validates and attaches in its
            # own order. Only its actual force starts private preparation.
            construction = _Construction(inputs, frame, unparented)
            _STATE.construction = construction
            try:
                return original(self, *args, **kwargs)
            finally:
                construction.prepared.clear()
                _STATE.construction = None

        construct.__cadgen_ready_children__ = True
        Compound.__init__ = construct
        return True
