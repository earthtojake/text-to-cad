"""``LazyCompound``: a child model's geometry, promised now and delivered when read.

A parent's body calls a child model and gets one of these back at once. If the
child was stale its build has been submitted to the pool (§Pool in STORE.md);
if it was current there is no job at all. Either way the body keeps going —
calling its other children, placing them, labelling them — and only blocks when
something actually needs geometry: the first read of ``wrapped``, which OCCT
and build123d cannot avoid. In the common body that read happens once, at the
closing ``Compound(children=[...])``, after every sibling has been submitted, so
stale children build in parallel.

Deferred without forcing: ``Pos/Rot/Location * child`` and ``.moved()`` compose
a placement; ``.label`` and ``.color`` are recorded and applied on force.
Everything else — ``.faces()``, ``.bounding_box()``, a boolean, ``.solids()``,
``copy.copy`` — reaches ``wrapped`` and forces. A build123d path not anticipated
here therefore degrades to "forced early": correct geometry, less overlap, never
wrong output.

Forcing: wait for the job (if any), read the child's record, pin the tree the
FIRST call resolved to (snapshot isolation: every later call in this build
composes that tree), materialize it, apply the placement with
``TopoDS_Shape.Moved`` (which shares the TShape, so the packager still sees the
child intact and writes a link), and tag the result exactly as
:func:`cadgen.store.materialize.materialize` does.

A failed child raises when forced; the error names the child, carries the
call site of the ``child()`` call, and includes the worker's output.

INTERNAL. No author names this type; ``type(arm())`` inside a parent is the only
way anyone sees it.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from build123d import Compound

from cadgen.store.materialize import PARTNER_TAG, TREE_TAG, _Partner, materialize


class ChildBuildError(RuntimeError):
    """A child model's build failed; raised where the parent first needed it."""


class LazyCompound(Compound):
    """See the module docstring."""

    def __init__(self, model: Path, job: Any, *, frame: Any, label: str) -> None:
        Compound.__init__(self, None, label=label)
        self._lazy_model = Path(model)
        self._lazy_job = job
        self._lazy_frame = frame
        self._lazy_label = label
        self._lazy_placement = None
        self._lazy_tree: str | None = None
        self._lazy_forcing = False
        # Where the parent called the child: the line a failure is reported at.
        self._lazy_call_site = _call_site()

    # --- what the parent may do without waiting ------------------------------------

    def moved(self, loc):  # type: ignore[override]
        from build123d import Plane

        if isinstance(loc, Plane):
            loc = loc.location
        if self._wrapped is not None:
            # Already forced: build123d's own moved() keeps the TShape (a link)
            # and deep-copies the wrapper's attributes, tags included.
            return Compound.moved(self, loc)
        clone = LazyCompound.__new__(LazyCompound)
        Compound.__init__(clone, None, label=self.label)
        clone.__dict__.update({k: v for k, v in self.__dict__.items() if k.startswith("_lazy_")})
        clone.color = self.color
        clone._lazy_placement = loc if self._lazy_placement is None else loc * self._lazy_placement
        return clone

    # --- forcing -----------------------------------------------------------------

    @property
    def wrapped(self):  # type: ignore[override]
        if self._wrapped is None:
            self._force()
        return self._wrapped

    @wrapped.setter
    def wrapped(self, shape) -> None:
        self._wrapped = shape

    @property
    def model(self) -> Path:
        return self._lazy_model

    @property
    def pending(self) -> bool:
        """True while the child's build has not been waited for."""
        return self._lazy_tree is None and self._lazy_job is not None

    def tree_hash(self) -> str:
        """The tree this child resolves to in this build. Waits for the job."""
        if self._lazy_tree is not None:
            return self._lazy_tree
        job = self._lazy_job
        if job is not None:
            code = job.wait()
            if code != 0:
                raise ChildBuildError(
                    f"child model {self._lazy_model.name} failed to build "
                    f"(called at {self._lazy_call_site}):\n{job.output().rstrip()}"
                )
        from cadgen.store.records import read_record

        record = read_record(self._lazy_model) or {}
        tree = str(record.get("tree") or "")
        if not tree:
            raise ChildBuildError(
                f"child model {self._lazy_model.name} built but left no record "
                f"(called at {self._lazy_call_site})"
            )
        frame = self._lazy_frame
        self._lazy_tree = frame.pin(self._lazy_model, tree) if frame is not None else tree
        return self._lazy_tree

    def _force(self) -> None:
        if self._lazy_forcing:
            raise RuntimeError(f"child model {self._lazy_model.name} forced re-entrantly")
        self._lazy_forcing = True
        try:
            tree = self.tree_hash()
            compound = materialize(tree, label=self._lazy_label)
            shape = compound.wrapped
            if self._lazy_placement is not None:
                shape = shape.Moved(self._lazy_placement.wrapped)
            self._wrapped = shape
            if not self.label:
                self.label = compound.label
            if self.color is None and getattr(compound, "color", None) is not None:
                self.color = compound.color
            setattr(self, TREE_TAG, tree)
            setattr(self, PARTNER_TAG, _Partner(compound.wrapped))
            # Reads that descend (a parent inspecting the child's parts) see the
            # materialized structure; a link is written before any descent.
            for child in list(compound.children):
                child.parent = self
        finally:
            self._lazy_forcing = False


def _call_site() -> str:
    """The first frame outside cadgen: where the model author called the child."""
    for frame in reversed(traceback.extract_stack(limit=30)):
        filename = str(frame.filename).replace("\\", "/")
        if "/cadgen/" in filename or filename.startswith("<"):
            continue
        return f"{frame.filename}:{frame.lineno}"
    return "<unknown>"
