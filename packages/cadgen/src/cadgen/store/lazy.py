"""``LazyCompound``: a child model's geometry, promised now and delivered when read.

A parent's body calls a child model and gets one of these back at once. If the
child was stale its build has been submitted to the pool (§9 in STORE.md); if it
was current there is no job at all. Either way the body keeps going — calling
its other children, placing them, labelling them — and only blocks when
something actually needs geometry: the first read of the wrapped OCCT shape.
Ordinary assembly construction reads those shapes after every sibling has been
submitted, so stale children build in parallel. Eligible plain
``Compound(children=[...])`` construction can instead keep exact references
through source publication; see :mod:`cadgen.store._references`.

Deferred without forcing: ``Pos/Rot/Location * child`` and ``.moved()`` compose
a placement; ``.label`` and ``.color`` are recorded and applied on force.
Everything else — ``.faces()``, ``.bounding_box()``, a boolean, ``.solids()``,
``copy.copy``, ``bool(child)`` — reaches the shape and forces. So does
``.children`` and every anytree view over it (``.descendants``, ``.leaves``,
``.is_leaf``, ``.height``, ``.size``): those answer from the node's child
list, which forcing fills in, and a promise that forced only on the shape
answered them with an EMPTY tree — a two-part child read as zero parts, at exit
0 — until something happened to touch geometry first. ``repr()`` is the one
node read that does not force: it says the promise is pending, because a
message (anytree formats a child into its duplicate-child error) must not
start a build. build123d reads
the shape through two names, the ``wrapped`` property and the ``_wrapped``
attribute it is backed by (its empty-shape checks are ``if self._wrapped is
None``), so ``_wrapped`` is the property here: a promise can never be mistaken
for an empty shape and answer with nothing. A build123d path not anticipated
here therefore degrades to "forced early": correct geometry, less overlap, never
wrong output.

Forcing: wait for the job's final source result (if any), then use its exact tree — a current child was
pinned at the CALL (the wrapper read its record then), a stale child's tree is the
one its job produced; the first tree a child resolves to in a build is what every
later call composes (snapshot isolation). Materialize it, apply the placement with
``TopoDS_Shape.Moved`` (which shares the TShape, so the packager still sees the
child intact and writes a link), and tag the result exactly as
:func:`cadgen.store.materialize.materialize` does.

During a model body's exact ``Compound(obj=[...])`` or tuple construction,
waiting on one input can first prepare bounded, already-pinned later inputs.
These fresh private compounds remain unexposed until ordinary ordered force,
which rechecks their exact objects before applying authored metadata/placement.
The permanent constructor hook is inactive outside a build frame; active state
is thread-local and clears at constructor exit. Plain ``Compound(children=...)``
first attempts bounded reference composition with an exact list/tuple of
unparented children and no ``obj`` or ``parent``. If that does not qualify,
its original attachment-triggered force can start preparation; anytree
validation and rollback remain unchanged. Nested constructors, generators,
subclasses, and child reparenting retain ordinary forcing without preparation.

A failed child raises when forced; the error names the child, carries the
call site of the ``child()`` call, and includes the worker's output.

INTERNAL. No author names this type; ``type(arm())`` inside a parent is the only
way anyone sees it.
"""

from __future__ import annotations

import copy
import sys
import traceback
from pathlib import Path
from typing import Any

from build123d import Compound
from build123d.topology.shape_core import downcast
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

from cadgen.store import _ready_children
from cadgen.store.materialize import PARTNER_TAG, ROOT_LOC_TAG, TREE_TAG, _Partner, materialize


class ChildBuildError(RuntimeError):
    """A child model's build failed; raised where the parent first needed it."""


class LazyCompound(Compound):
    """See the module docstring."""

    def __init__(self, model: Path | str, job: Any, *, frame: Any, label: str, tree: str | None = None) -> None:
        self._lazy_shape = None
        self._lazy_forcing = False
        Compound.__init__(self, None, label=label)
        # The child's identity: its model ref (``script::fn``; see store.index).
        self._lazy_model = str(model)
        self._lazy_job = job
        self._lazy_frame = frame
        self._lazy_label = label
        self._lazy_placement = None
        # A CURRENT child is pinned AT THE CALL: the caller read its record and hands the
        # tree in, so a rebuild of that child between this call and the force cannot change
        # what this build composes. A stale child's pin is its job's result, fixed when the
        # job was submitted; it is read when forced.
        self._lazy_tree: str | None = (
            (frame.pin(self._lazy_model, tree) if frame is not None else tree) if tree else None
        )
        # Where the parent called the child: the line a failure is reported at.
        self._lazy_call_site = _call_site()

    # --- the shape, forced on first read -----------------------------------------------

    @property
    def _wrapped(self):
        self._capture_attached_reference()
        shape = self.__dict__.get("_lazy_shape")
        if shape is None and not self.__dict__.get("_lazy_forcing", False):
            self._force()
            shape = self.__dict__.get("_lazy_shape")
        return shape

    @_wrapped.setter
    def _wrapped(self, shape) -> None:
        self._capture_attached_reference()
        self.__dict__["_lazy_shape"] = shape

    @property
    def _forced(self) -> bool:
        return self.__dict__.get("_lazy_shape") is not None

    @property
    def cad_material(self):
        raise AttributeError(
            "cad_material authoring was removed; declare named materials with "
            "@step(materials={'definitions': ..., 'assignments': ...})"
        )

    @cad_material.setter
    def cad_material(self, value) -> None:
        raise AttributeError(
            "cad_material authoring was removed; declare named materials with "
            "@step(materials={'definitions': ..., 'assignments': ...})"
        )

    @cad_material.deleter
    def cad_material(self) -> None:
        raise AttributeError("cad_material authoring was removed; remove the @step materials= assignment instead")

    @property
    def cad_face_ordinal_colors(self):
        """The pinned root face colors, with the same ownership as material."""
        if "cad_face_ordinal_colors" not in self.__dict__ and not self._forced:
            self._force()
        if "cad_face_ordinal_colors" not in self.__dict__:
            raise AttributeError("cad_face_ordinal_colors")
        return self.__dict__["cad_face_ordinal_colors"]

    @cad_face_ordinal_colors.setter
    def cad_face_ordinal_colors(self, value) -> None:
        self.__dict__["cad_face_ordinal_colors"] = value

    @cad_face_ordinal_colors.deleter
    def cad_face_ordinal_colors(self) -> None:
        if not self._forced:
            self._force()
        if "cad_face_ordinal_colors" not in self.__dict__:
            raise AttributeError("cad_face_ordinal_colors")
        del self.__dict__["cad_face_ordinal_colors"]

    # --- what the parent may do without waiting ------------------------------------

    def _capture_attached_reference(self):
        if (self.__dict__.get("_lazy_reference_attached")
                and not self.__dict__.get("_lazy_forcing")):
            from cadgen.store._references import force_parent

            # Capture the original native child before its wrapper escapes or
            # is replaced. In-place TShape edits still share the captured
            # geometry; wrapper replacement/location changes do not.
            force_parent(self.__dict__.get("_NodeMixin__parent"))

    def _force_attached_reference(self):
        self._capture_attached_reference()
        if (self.__dict__.get("_lazy_reference_attached") and not self._forced
                and not self.__dict__.get("_lazy_forcing")):
            self._force()

    def _force_node_state(self):
        """A READ of the child list forces: the list is what forcing fills in.

        ``children``, ``descendants``, ``leaves``, ``is_leaf``, ``height``, ``size``
        and ``repr()`` all answer from ``_NodeMixin__children``. A pending promise
        holds an empty one, so reading it before geometry reported a two-part
        child as zero parts at exit 0 (tom-cad FEEDBACK issue 4). Attached or
        not, a read is a read. Only a fully constructed promise forces:
        ``Compound.__init__`` runs anytree's children setter, which reads the
        list, before the job is recorded.
        """
        self._capture_attached_reference()
        if ("_lazy_job" in self.__dict__ and not self._forced
                and not self.__dict__.get("_lazy_forcing")):
            self._force()

    def __repr__(self) -> str:
        # A repr is a message, not a read. build123d's Compound.__repr__ counts
        # children, and anytree formats a child into its duplicate-child
        # TreeError before anything is attached: forcing a build to print a
        # promise would make an error message a side effect.
        if not self._forced:
            state = self.__dict__
            return f"LazyCompound(model={state.get('_lazy_model')!r}, label={state.get('label')!r}, pending)"
        return Compound.__repr__(self)

    @property
    def children(self):
        # Any read forces (see _force_node_state); once attached, ordinary
        # construction had populated this hierarchy and a reader such as the
        # native XCAF exporter must never see an empty leaf merely because its
        # private geometry is still deferred.
        self._force_node_state()
        return Compound.children.fget(self)

    @property
    def _NodeMixin__children_or_empty(self):
        # anytree's ``plain_shape.parent = child`` mutates this private list
        # without consulting the public children property or Compound hooks,
        # and ``is_leaf``/``height`` read it directly. Populate/capture the
        # existing hierarchy before that ordinary read or edit.
        self._force_node_state()
        return Compound._NodeMixin__children_or_empty.fget(self)

    @children.setter
    def children(self, children):
        self._force_attached_reference()
        Compound.children.fset(self, children)

    @children.deleter
    def children(self):
        self._force_attached_reference()
        Compound.children.fdel(self)

    def _post_attach(self, parent):
        from cadgen.store._references import attach_child

        if not attach_child(self, parent):
            return Compound._post_attach(self, parent)

    def _pre_attach(self, parent):
        from cadgen.store._references import force_parent

        Compound._pre_attach(self, parent)
        force_parent(parent)

    def _pre_detach(self, parent):
        from cadgen.store._references import force_parent

        force_parent(parent)

    def moved(self, loc):  # type: ignore[override]
        from build123d import Plane

        if isinstance(loc, Plane):
            loc = loc.location
        if self.__dict__.get("_lazy_reference_attached") and not self._forced:
            # Ordinary Compound construction had already forced this child.
            # Its later moved() must retain build123d's shared-native semantics,
            # including native edits made through either resulting wrapper.
            self._force()
        if self._forced:
            # Already forced: build123d's own moved() keeps the TShape (a link)
            # and deep-copies the wrapper's attributes, tags included.
            return Compound.moved(self, loc)
        clone = LazyCompound.__new__(LazyCompound)
        clone._lazy_shape = None
        clone._lazy_forcing = False
        Compound.__init__(clone, None, label=self.label)
        clone.__dict__.update({k: v for k, v in self.__dict__.items() if k.startswith("_lazy_")})
        clone.color = self.color
        for key in ("_cadgen_material", "_cadgen_material_id", "cad_face_ordinal_colors"):
            if key in self.__dict__:
                clone.__dict__[key] = copy.deepcopy(self.__dict__[key])
        clone._lazy_placement = loc if self._lazy_placement is None else loc * self._lazy_placement
        return clone

    def __iter__(self):
        # build123d's ``Location.__mul__`` probes its right operand with ``list(other)``
        # before giving up and letting ``Shape.__rmul__`` place it. Iterating a promise
        # would force it, so ``Pos * child`` -- the one placement form every body uses --
        # would wait for the child right there. Refusing the probe (TypeError is what a
        # non-iterable raises, and what that code catches) hands the operator to
        # ``__rmul__`` -> ``moved()``, which defers. Any OTHER iteration forces: a body
        # that walks a child's parts needs the parts.
        if not self._forced and sys._getframe(1).f_code.co_name == "__mul__":
            raise TypeError("a pending child is placed, not iterated")
        return Compound.__iter__(self)

    def __deepcopy__(self, memo):
        # ``moved()`` and ``copy.copy`` deep-copy the wrapper (then re-place the same
        # TShape). The job and the frame are not copyable and are not geometry: the copy
        # is a plain Compound of the forced result, tags included, with the same
        # TopoDS copy semantics build123d's own ``Shape.__deepcopy__`` uses.
        shape = self._wrapped  # forces
        result = Compound.__new__(Compound)
        memo[id(self)] = result
        memo[id(shape)] = downcast(BRepBuilderAPI_Copy(shape).Shape())
        result._wrapped = memo[id(shape)]
        for key, value in self.__dict__.items():
            if key.startswith("_lazy_"):
                continue
            if key == "topo_parent":
                result.topo_parent = value
            else:
                setattr(result, key, copy.deepcopy(value, memo))
            if key == "joints":
                for joint in result.joints.values():
                    joint.parent = result
        return result

    # --- forcing -----------------------------------------------------------------

    @property
    def model(self) -> str:
        return self._lazy_model

    @property
    def model_name(self) -> str:
        from cadgen.store.index import split_model_ref

        script, function = split_model_ref(self._lazy_model)
        return f"{script.name}::{function}" if function and function != script.stem else script.name

    @property
    def pending(self) -> bool:
        """True while the child's build has not been waited for."""
        return self._lazy_tree is None and self._lazy_job is not None

    def tree_hash(self) -> str:
        """The exact authored tree this call pins, independent of STEP persistence."""
        from cadgen.store.trees import tree_complete

        if self._lazy_tree is not None:
            tree = self._lazy_tree
        elif self._lazy_job is not None:
            job = self._lazy_job
            try:
                if job.result_ready:
                    tree = job.wait_result()
                else:
                    from cadgen.daemon.broker import yielded

                    with yielded():
                        tree = job.wait_result()
            except RuntimeError as exc:
                raise ChildBuildError(
                    f"child model {self.model_name} failed to build "
                    f"(called at {self._lazy_call_site}):\n{exc}"
                ) from exc
        else:
            raise ChildBuildError(
                f"child model {self.model_name} has no pinned source result "
                f"(called at {self._lazy_call_site})"
            )
        frame = self._lazy_frame
        self._lazy_tree = frame.pin(self._lazy_model, tree) if frame is not None else tree
        if not tree_complete(self._lazy_tree):
            raise ChildBuildError(f"child model {self.model_name}: pinned source geometry disappeared from the cache")
        return self._lazy_tree

    def wait_outputs(self) -> None:
        """The parent owes every called child's declared outputs, even discarded calls."""
        job = self._lazy_job
        if job is None:
            return
        if job.done:
            code = job.wait()
        else:
            from cadgen.daemon.broker import yielded

            with yielded():
                code = job.wait()
        if code != 0:
            raise ChildBuildError(
                f"child model {self.model_name} failed to build "
                f"(called at {self._lazy_call_site}):\n{job.output().rstrip()}"
            )

    def _force(self) -> None:
        if self._lazy_forcing:
            raise RuntimeError(f"child model {self.model_name} forced re-entrantly")
        _ready_children.prepare_for(self)
        self._lazy_forcing = True
        try:
            tree = self.tree_hash()
            face_colors_overridden = "cad_face_ordinal_colors" in self.__dict__
            compound = _ready_children.take_prepared(self, tree, self._lazy_label)
            if compound is None:
                compound = _materialize_tree(tree, self._lazy_label)
            shape = compound.wrapped
            if self._lazy_placement is not None:
                shape = shape.Moved(self._lazy_placement.wrapped)
            self._lazy_shape = shape
            if not self.label:
                self.label = compound.label
            if self.color is None and getattr(compound, "color", None) is not None:
                self.color = compound.color
            for key, overridden in (
                ("_cadgen_material", False),
                ("_cadgen_material_id", False),
                ("cad_face_ordinal_colors", face_colors_overridden),
            ):
                if overridden:
                    continue
                if key in compound.__dict__:
                    self.__dict__[key] = copy.deepcopy(compound.__dict__[key])
                else:
                    # No authored shell value exists, so an absent pinned value
                    # is authoritative. Never clear a model-authored override.
                    self.__dict__.pop(key, None)
            setattr(self, TREE_TAG, tree)
            # The child's own root placement rides along too: this shape is
            # ``placement * root`` and the packager divides the root back out of
            # the link it records (materialize.ROOT_LOC_TAG).
            setattr(self, ROOT_LOC_TAG, getattr(compound, ROOT_LOC_TAG, None))
            # Reads that descend (a parent inspecting the child's parts) see the
            # materialized structure; a link is written before any descent. The
            # children are transplanted, not re-attached: anytree's attach hook
            # rebuilds a Compound's shape from its children, which would replace
            # the placed shape above with an unplaced one of a different TShape.
            # build123d's own booleans move children the same way.
            kids = list(compound.__dict__.get("_NodeMixin__children") or [])
            self.__dict__["_NodeMixin__children"] = kids
            for child in kids:
                child.__dict__["_NodeMixin__parent"] = self
            holder = getattr(compound, PARTNER_TAG, None)
            setattr(self, PARTNER_TAG, holder.retarget(self) if isinstance(holder, _Partner) else _Partner(self))
        finally:
            self._lazy_forcing = False


def materialize_model(tree: str, *, label: str) -> Compound:
    """The geometry a model's tree stands for, as a plain Compound: what a
    top-level call returns after its build (cadgen.authoring)."""
    return _materialize_tree(tree, label)


def _materialize_tree(tree: str, label: str) -> Compound:
    return materialize(tree, label=label)


_CADGEN_PACKAGE = str(Path(__file__).resolve().parents[1])


def _call_site() -> str:
    """The first frame outside the cadgen package: where the model author called the child."""
    for frame in reversed(traceback.extract_stack(limit=30)):
        filename = str(frame.filename)
        if filename.startswith(_CADGEN_PACKAGE) or filename.startswith("<"):
            continue
        return f"{frame.filename}:{frame.lineno}"
    return "<unknown>"


# LazyCompound is loaded only on a kernel-owning execution path. The permanent
# hook does nothing outside a model body and keeps active state thread-local.
_ready_children.install()
