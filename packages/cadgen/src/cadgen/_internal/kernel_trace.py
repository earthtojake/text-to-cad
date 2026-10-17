"""Features and lineage: what the kernel boundary saw during one model run, and
the names it gives the faces, edges and vertices of what the run made (STORE.md
§2 and §3; README law 20).

A **feature** is one call of a patched kernel construction (``kernel_memo``)
made from the model's own code: the operation, the innermost first-party
frame that called it (the file, relative to the model's folder, the line and
the enclosing function) and the features that made the shapes it was given. A
call with no first-party frame on the stack is cadgen's own and is not a
feature; a call nested inside another feature's operation belongs to that
feature. A feature is named within a part, among the features the part
descends from -- those that made it and, transitively, whatever they were
given -- in call order: ``<function>.<operation><count>``, the enclosing
function, the operation (``extrude``, ``fillet``, ``cut``, a constructor's
class in lower case) and how many of the part's features before it, this one
included, that function's calls of that operation were: ``dial.extrude1``. So
an edit elsewhere in the model -- another part's feature, a call no element of
this part descends from -- renames nothing here. An author's label pins the
name instead, in what is made of the labelled shape: a shape the model labels
and hands to another construction names the feature that made it by that label
(``lid``) in every part made from that call on that the feature is an ancestor
of, the part's first feature to claim a label keeping it -- never in a part made
before the label reached a construction, and not in the part that shape is itself:
there (an assembly's leaf) the label names the occurrence, and the elements keep
their construction's names, so identical constructions labelled apart are one
part. A function or a label that is not an ASCII identifier
is written as its ASCII form and a digest of it (``identifier``), so no two are
written alike. Lines and files are not in a name: they are where the trace
says a feature ran (the provenance entry, ``store where``).

Lineage is by identity and geometry, not by the kernel's history objects. An
element is a TShape at one place in its shape (two places of one TShape -- a
prism's two caps -- are two elements). Each element of a component is followed
back through the features: at each feature, an element of the result that an
input holds at the same place (where the operation saw it, as the kernel keeps
what an operation leaves alone, or in the shape's own frame, as a placement
keeps everything) or that an input held with the same surface (or curve, or
point) and the same extent is **unchanged** there and inherits its lineage from
that input; one on the surface of an input's element the result no longer holds,
with another extent, was **modified** by the feature; any other element was
**made** by it. Surfaces, curves and extents are compared in the frame the
operation saw them (the inputs as they were passed, the result as it was
returned), rounded absolutely, and only for the elements an operation touched.
An input that is a sub-shape of a feature's result (``bar.faces()[i]``) is
followed to that result, where the feature placed it. The walk stops at a shape
no feature made (a materialized child, an imported file, a shape built outside
the patched surface): an element the operation passed on from it as it was
has no lineage, and one it rebuilt or trimmed is made by the operation -- as is
one that traces to an input the trace cannot follow, so every element a
feature produced has a name.

An element's **name** is its lineage: ``<kind>:<feature>.<n>``, the feature that
made it and its number among the elements of that kind the feature made, in the
order of its result -- ``f:dial.extrude1.3`` -- and, where a later feature split
one element into several, each piece's number among them after a further dot,
in the component's own order: ``f:dial.extrude1.3.2``. The features that
modified an element do not rename it; the last of them is recorded beside its
name. An element with no lineage has no name here (``None``): its part names it
by its geometry (``geometric_tokens``).

``Trace.account`` is a component's whole account: its lineage, the object its
tree entry names (``component_package``) -- the feature that made the body and,
per element ordinal, its name -- and the feature each name of it stands for;
``Trace.feature_rows`` is the run's features, what the provenance entry keeps
with those names (``cadgen.store.provenance``).
"""

from __future__ import annotations

import hashlib
import math
import re
import sys
import weakref
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepTools import BRepTools
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.Precision import Precision
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedMapOfShape

from cadgen._internal.source_hash import is_first_party_source_file

__all__ = ["Feature", "Trace", "edge_signature", "face_signature", "vertex_signature"]

# Lineage compares geometry rounded absolutely: positions and lengths to a
# micron, directions to a nanoradian's worth, like an occurrence's placement
# (tree_tokens). A face or edge an operation left alone keeps its surface and
# its extent to far better than this; one it trimmed keeps the surface alone.
POSITION_QUANTUM = 1e-6
DIRECTION_QUANTUM = 1e-9
_SAMPLES = 3
_WINDOW = (-1.0, 1.0)
_HERE = Path(__file__).resolve().parent
# A kernel call reached through cadgen's own machinery before any model frame
# (a child's materialization, the store's own constructions) is cadgen's, not
# the model's: no feature. Its public helpers (``cadgen.geometry``,
# ``cadgen.assembly``) are called by the model and count as build123d does.
_OWN = tuple(_HERE.parent / name for name in ("store", "_internal", "daemon"))
# The element kinds a component names, each with its ref prefix and plural.
KINDS = (("face", TopAbs_FACE, "f", "faces"), ("edge", TopAbs_EDGE, "e", "edges"),
         ("vertex", TopAbs_VERTEX, "v", "vertices"))
_TOPABS = {kind: topabs for kind, topabs, _prefix, _plural in KINDS}
_NOT_IDENTIFIER = re.compile(r"[^A-Za-z0-9_]+")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# What a digest of a name looks like at its end, which a name written as it is never has.
_DIGESTED = re.compile(r"_[0-9a-f]{8}$")
# The frames Python names itself, each written as its word; a function of that name
# is not one of them, and takes a digest.
_FRAMES = {"<module>": "module", "<lambda>": "lambda", "<genexpr>": "genexpr", "<listcomp>": "listcomp",
           "<dictcomp>": "dictcomp", "<setcomp>": "setcomp"}
_FRAME_WORDS = frozenset(_FRAMES.values())
_IDENTITY = tuple(int(round((1.0 if row == column else 0.0) / DIRECTION_QUANTUM)) if column < 4 else 0
                  for row in (1, 2, 3) for column in (1, 2, 3, 4))


def identifier(text: str) -> str:
    """``text`` as one name segment, no two texts alike: an ASCII identifier as it is,
    and the frame Python names ``<module>`` (or ``<lambda>``, ``<genexpr>``) as its
    word. Anything else -- a name beyond ASCII, a label with a colon, an identifier
    that is one of those words or ends as a digest does -- is its ASCII form (its runs
    of anything but ASCII letters, digits and underscores one underscore, trimmed)
    and the first eight hex digits of its sha256 (``корпус`` is ``_9f1c0b2e``,
    ``mounting_eye:lower`` is ``mounting_eye_lower_`` and its digest), so it is never
    a name another text is written as."""
    text = str(text)
    word = _FRAMES.get(text)
    if word is not None:
        return word
    if _IDENTIFIER.fullmatch(text) and text not in _FRAME_WORDS and not _DIGESTED.search(text):
        return text
    form = _NOT_IDENTIFIER.sub("_", text).strip("_")
    digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()[:8]
    if not form:
        return f"_{digest}"
    return f"{'_' if form[0].isdigit() else ''}{form}_{digest}"


def operation_name(op: str) -> str:
    """A feature's operation as its name spells it: the method without its class
    (``Solid.extrude`` is ``extrude``), a constructor's class in lower case."""
    return identifier(op.rsplit(".", 1)[-1].lower())


@dataclass
class Feature:
    """One kernel construction the model's code called."""

    index: int
    op: str
    file: str
    line: int
    function: str
    # The feature of each shape the call was given, in call order; None for a
    # shape no feature of this run made.
    inputs: list[int | None]
    # The input shapes as passed and the results as returned: handle copies,
    # so a later in-place move of the object does not move what the operation
    # saw; None for an empty shape or a child model's promise not yet forced.
    # The lineage tables are computed from these on demand.
    handles: list[Any] = field(default_factory=list, repr=False)
    results: list[Any] = field(default_factory=list, repr=False)
    # The author's label for what this feature made, when one pins its name, and the
    # feature whose call pinned it: a part made before that call is named as if the
    # label had never been set.
    label: str | None = None
    pinned_at: int | None = None
    _tables: dict[tuple[int, str], dict[int, tuple]] = field(default_factory=dict, repr=False)
    # Per element kind, each element this feature made (its key where the result
    # holding it was returned: :func:`_placed`) -> its number among them, in the
    # order of the results and of each result's elements.
    _numbers: dict[str, dict[tuple, int]] = field(default_factory=dict, repr=False)
    # Functions of the feature alone, computed once: the operation as its name spells
    # it, the name without its count (``<function>.<operation>``, as written) -- every
    # part's naming reads them for each feature it descends from -- and, on first use,
    # the first position at which each TShape was returned.
    operation: str = field(init=False, repr=False)
    stem: str = field(init=False, repr=False)
    _positions: dict[Any, int] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.operation = operation_name(self.op)
        self.stem = f"{identifier(self.function)}.{self.operation}"

    def position_of(self, tshape: Any) -> int | None:
        """The first position among the results at which ``tshape`` was returned, or None."""
        positions = self._positions
        if positions is None:
            positions = self._positions = {}
            for position, result in enumerate(self.results):
                if result is not None:
                    positions.setdefault(result.TShape(), position)
        return positions.get(tshape)

    def row(self) -> dict[str, Any]:
        """The feature as the provenance entry records it: where it ran, and the
        features that made what it was given, by their place in the run."""
        return {"op": self.op, "file": self.file, "line": self.line, "function": self.function,
                "inputs": list(self.inputs)}


class Trace:
    """The features of one run, in call order, and the lineage they give."""

    def __init__(self, model_dir: Path | None) -> None:
        self.model_dir = Path(model_dir).resolve() if model_dir is not None else None
        self.features: list[Feature] = []
        self._first_party: dict[str, str] = {}
        self._display: dict[str, str] = {}
        # id(shape) -> (weakref, feature index): the feature that returned each
        # live result object. A dead reference, or a recycled id, answers nothing.
        self._by_object: dict[int, tuple[weakref.ref, int]] = {}
        # The same for the call that made each live object: the first feature that
        # returned it itself, never one that only held it (a compound it was attached to).
        self._made_object: dict[int, tuple[weakref.ref, int]] = {}
        self._signatures_by_body: dict[tuple, dict[int, tuple]] = {}
        self._chains: dict[tuple[int, int, str, int], tuple[tuple[int, int] | None, int | None]] = {}
        # (TShape, element kind) -> the map of a body's elements of that kind in
        # its own frame, each element's key (:func:`_key`) -> its ordinal there,
        # and the keys by ordinal. A body is mapped once, however many features
        # hold it and elements ask.
        self._maps: dict[tuple[Any, Any], tuple[Any, dict[tuple, int], list[tuple]]] = {}
        # (TShape, placement, element kind) -> each element's key where a shape so
        # placed has it (:func:`_placed`), by ordinal.
        self._placed: dict[tuple, list[tuple]] = {}
        # (feature index, input index) -> where that input came from (:meth:`_source`).
        self._sources: dict[tuple[int, int], tuple] = {}
        self._made_by: Callable[[Any], int | None] = lambda _tshape: None

    # --- recording ---------------------------------------------------------------------

    def frame(self) -> tuple[str, int, str] | None:
        """The innermost first-party frame of the current stack: ``(file, line,
        function)``, the file relative to the model's folder; None when the
        call is cadgen's own (one of its internal frames comes first) or no
        model code is on the stack."""
        frame = sys._getframe(1)
        while frame is not None:
            filename = frame.f_code.co_filename
            verdict = self._first_party.get(filename)
            if verdict is None:
                verdict = self._first_party[filename] = _classify(filename)
            if verdict == "model":
                return self._display_path(filename), frame.f_lineno, frame.f_code.co_name
            if verdict == "own":
                return None
            frame = frame.f_back
        return None

    def _display_path(self, filename: str) -> str:
        shown = self._display.get(filename)
        if shown is None:
            path = Path(filename)
            shown = path.as_posix()
            if self.model_dir is not None:
                try:
                    shown = path.resolve().relative_to(self.model_dir).as_posix()
                except (ValueError, OSError):
                    shown = path.as_posix()
            self._display[filename] = shown
        return shown

    def feature_of(self, shape: Any) -> int | None:
        """The feature that returned this very object, or None."""
        found = self._by_object.get(id(shape))
        if found is None:
            return None
        reference, index = found
        return index if reference() is shape else None

    def made(self, shape: Any) -> int | None:
        """The feature whose call made this very object -- the first that returned it
        itself -- or None."""
        found = self._made_object.get(id(shape))
        if found is None:
            return None
        reference, index = found
        return index if reference() is shape else None

    def given(self, shapes: list[Any], feature_of: Callable[[Any], int | None]) -> list[tuple[Any, int | None, Any]]:
        """The inputs of a call as it is given them, taken before it runs: each shape,
        the feature that made it (``feature_of``) and a handle of its ``TopoDS`` then --
        an in-place operation (``clean``) leaves its input object wrapping the result."""
        return [(shape, feature_of(shape), handle_of(shape)) for shape in shapes]

    def record(self, op: str, frame: tuple[str, int, str], inputs: list[tuple[Any, int | None, Any]],
               results: list[Any], made: list[Any] = ()) -> Feature:
        """One feature: ``inputs`` are the call's, as :meth:`given` took them,
        ``results`` the live result objects the call returned and the children they hold,
        ``made`` the objects it returned itself. A labelled input pins the name of the
        feature that made it."""
        file, line, function = frame
        feature = Feature(
            index=len(self.features), op=op, file=file, line=line, function=function,
            inputs=[index for _shape, index, _handle in inputs],
            handles=[handle for _shape, _index, handle in inputs],
            results=[handle_of(shape) for shape in results],
        )
        self.features.append(feature)
        for shape, index, _handle in inputs:
            if index is not None:
                self._pin(index, getattr(shape, "__dict__", {}).get("label"), at=feature.index)
        for shape in results:
            try:
                self._by_object[id(shape)] = (weakref.ref(shape), feature.index)
            except TypeError:
                pass
        for shape in made:
            try:
                found = self._made_object.get(id(shape))
                if found is None or found[0]() is not shape:
                    self._made_object[id(shape)] = (weakref.ref(shape), feature.index)
            except TypeError:
                pass
        return feature

    def _pin(self, index: int, label: object, *, at: int) -> None:
        """Name feature ``index`` by the author's ``label``, the first one it is
        handed on with -- by the call of feature ``at`` -- in what is made of the shape
        it made from that call on (:meth:`_names`); a label that is an occurrence token
        (a tree's, not an author's) pins nothing. Of a part's features, the first to
        claim a label keeps it."""
        from cadgen._internal.tree_tokens import is_occurrence_token

        if not isinstance(label, str) or not label or is_occurrence_token(label):
            return
        feature = self.features[self.unwrapped(index)]
        if feature.label is None:
            feature.label, feature.pinned_at = identifier(label), at

    def unwrapped(self, index: int) -> int:
        """The feature that made what feature ``index`` returned, through the features
        that only place or hold another's: a placement (``moved``, ``located``, a copy
        that keeps the shape) returns the very shape it was given, and a compound built
        of one shape (build123d wraps every part it builds in one) is that shape."""
        from OCP.TopoDS import TopoDS_Iterator

        while True:
            feature = self.features[index]
            result = feature.results[0] if len(feature.results) == 1 else None
            if result is None:
                return index
            held = result.TShape()
            if feature.operation == "compound":
                children = TopoDS_Iterator(result)
                child = children.Value() if children.More() else None
                if child is None:
                    return index
                children.Next()
                if children.More():
                    return index
                held = child.TShape()
            inner = next((feature.inputs[j] for j, handle in enumerate(feature.handles)
                          if handle is not None and feature.inputs[j] is not None and feature.inputs[j] != index
                          and handle.TShape() == held), None)
            if inner is None:
                return index
            index = inner

    # --- the payload ---------------------------------------------------------------------

    def feature_rows(self) -> list[dict[str, Any]]:
        """The run's features in call order, as the provenance entry records them."""
        return [feature.row() for feature in self.features]

    def account(self, body: Any, made_by: Callable[[Any], int | None]) -> tuple[dict[str, Any] | None, dict[str, int]]:
        """The lineage of one unlocated component ``body`` (a ``TopoDS_Shape``):
        ``{"made": <feature name or None>, "faces": [...], "edges": [...],
        "vertices": [...], "modified": {<element name>: <feature name>}}``, each
        list holding an element name or None per ``TopExp.MapShapes_s`` ordinal,
        and ``modified`` the last feature that modified each named element that
        was; None when no feature of the run made any of it. ``made_by`` answers,
        for a ``TopoDS_TShape``, the feature of this run that made it. With it, the
        feature (its index in the run) each feature name it holds stands for, with
        the features those were given: what ``store where`` answers a name of this
        part with."""
        self._made_by = made_by
        maker = self._maker(made_by, body)
        owners = self._owners(made_by, body)
        if maker is None and not owners:
            return None, {}
        traced_by_kind = []
        for kind, topabs, prefix, plural in KINDS:
            elements = self._elements(body, topabs)
            traced_by_kind.append([self._lineage(made_by, owners, elements.FindKey(ordinal), kind)
                                   for ordinal in range(1, elements.Extent() + 1)])
        # A body build123d only wrapped or placed was made by what it wraps.
        made_feature = None if maker is None else self.unwrapped(maker)
        named_features = {made[0] for traced in traced_by_kind for made, _modifier in traced if made is not None}
        named_features |= {modifier for traced in traced_by_kind for _made, modifier in traced if modifier is not None}
        if made_feature is not None:
            named_features.add(made_feature)
        roots = [index for _shape, index in owners] + sorted(named_features)
        names = self._names(roots, made_feature, made_at=max(roots))
        payload: dict[str, Any] = {"made": None if made_feature is None else names[made_feature]}
        modified: dict[str, str] = {}
        named = False
        for (kind, topabs, prefix, plural), traced in zip(KINDS, traced_by_kind):
            pieces = Counter(made for made, _modifier in traced if made is not None)
            seen: Counter = Counter()
            element_names: list[str | None] = []
            for made, modifier in traced:
                if made is None:
                    element_names.append(None)
                    continue
                name = f"{prefix}:{names[made[0]]}.{made[1]}"
                if pieces[made] > 1:
                    seen[made] += 1
                    name = f"{name}.{seen[made]}"
                element_names.append(name)
                if modifier is not None:
                    modified[name] = names[modifier]
            named = named or any(name is not None for name in element_names)
            payload[plural] = element_names
        if maker is None and not named:
            return None, {}
        payload["modified"] = modified
        stands = set(named_features)
        for index in named_features:
            stands.update(given for given in self.features[index].inputs if given is not None)
        return payload, {names[index]: index for index in sorted(stands)}

    def _names(self, roots: list[int], body: int | None, *, made_at: int) -> dict[int, str]:
        """The name of each feature a part descends from -- ``roots`` and, transitively,
        every feature that made what one of them was given -- counted among them in
        call order: a label pinned by the time the part was made (by feature ``made_at``,
        the last of its own), the first of the part's features to claim it keeping it,
        else ``<function>.<operation><count>``, every feature counting in its stem.
        ``body`` is the feature that made the part's body, whose own label names the
        occurrence and pins nothing here: identical constructions labelled apart are
        one part, named alike. A label pinned later -- set on a shape after it was given
        to the construction that made this part -- renames nothing here."""
        seen: set[int] = set()
        pending = [index for index in roots if index is not None]
        while pending:
            index = pending.pop()
            if index in seen:
                continue
            seen.add(index)
            pending.extend(given for given in self.features[index].inputs if given is not None and given not in seen)
        counts: Counter = Counter()
        labels: set[str] = set()
        names: dict[int, str] = {}
        for index in sorted(seen):
            feature = self.features[index]
            stem = feature.stem
            counts[stem] += 1
            if (feature.label is not None and feature.pinned_at is not None and feature.pinned_at <= made_at
                    and index != body and feature.label not in labels):
                labels.add(feature.label)
                names[index] = feature.label
            else:
                names[index] = f"{stem}{counts[stem]}"
        return names

    def _maker(self, made_by: Callable[[Any], int | None], body: Any) -> int | None:
        """The feature that made ``body``, or None: the one its TShape is
        registered to, unless that feature was handed the TShape it returned
        (a placement of a shape no feature made)."""
        index = made_by(body.TShape())
        if index is not None and self._passed_through(index, body.TShape()):
            return None
        return index

    def _passed_through(self, index: int, tshape: Any) -> bool:
        return any(handle is not None and handle.TShape() == tshape for handle in self.features[index].handles)

    def _owners(self, made_by: Callable[[Any], int | None], body: Any) -> list[tuple[Any, int]]:
        """The shapes of a component some feature made, with that feature: the
        body itself when it is one feature's result, else each solid or shell
        of it that is."""
        index = made_by(body.TShape())
        if index is not None:
            return [(body, index)]
        from cadgen._internal.entity_ordinals import shape_entities

        found = []
        for entity in shape_entities(body):
            index = made_by(entity.TShape())
            if index is not None:
                found.append((entity, index))
        return found

    def _lineage(self, made_by: Callable[[Any], int | None], owners: list[tuple[Any, int]], element: Any,
                 kind: str) -> tuple[tuple[int, int] | None, int | None]:
        """``(made, modified)`` for one element of a component (in the component's
        frame): ``made`` the feature that made it and its number among what that
        feature made, ``modified`` the feature that last modified it; None where
        unknown."""
        for shape, index in owners:
            local = _relative(element, shape)
            if _key(local) not in self._ordinals(shape, element.ShapeType()):
                continue
            found = self._located(index, shape)
            if found is None:
                return None, None
            position, location = found
            return self._chain(made_by, index, position, kind, local if location is None else local.Moved(location))
        return None, None

    def _located(self, index: int, shape: Any) -> tuple[int, Any] | None:
        """Where feature ``index`` returned ``shape``: ``(position, None)`` for a result
        that is it, else ``(position, location)`` for the first result holding it --
        where ``shape`` is placed, if a place of it is, else its first place -- the
        location of it inside that result (unlocated); None when no result holds it."""
        feature = self.features[index]
        position = feature.position_of(shape.TShape())
        if position is not None:
            return position, None
        tshape = shape.TShape()
        for position, result in enumerate(feature.results):
            if result is None:
                continue
            elements, _ordinals, keys = self._mapped(result, shape.ShapeType())
            places = [ordinal for ordinal, key in enumerate(keys, 1) if key[0] == tshape]
            if not places:
                continue
            relative = _transform(result.Location().Inverted().Multiplied(shape.Location()).Transformation())
            ordinal = next((ordinal for ordinal in places if keys[ordinal - 1][1] == relative), places[0])
            return position, elements.FindKey(ordinal).Location()
        return None

    def _source(self, index: int, j: int) -> tuple:
        """Where input ``j`` of feature ``index`` came from: ``("followed", feature,
        position, location)`` -- the feature that made it, where it returned it
        (:meth:`_located`); ``("foreign",)`` for a shape no other feature made;
        ``("lost",)`` for one a feature made that the trace cannot find in what it
        returned."""
        found = self._sources.get((index, j))
        if found is not None:
            return found
        feature = self.features[index]
        handle = feature.handles[j]
        found = ("foreign",)
        if handle is not None:
            makers = [up for up in dict.fromkeys((self._made_by(handle.TShape()), feature.inputs[j]))
                      if up is not None and up != index]
            if makers:
                found = ("lost",)
                for up in makers:
                    located = self._located(up, handle)
                    if located is not None:
                        found = ("followed", up, *located)
                        break
        self._sources[(index, j)] = found
        return found

    def _chain(self, made_by: Callable[[Any], int | None], index: int, position: int, kind: str,
               element: Any) -> tuple[tuple[int, int] | None, int | None]:
        """Follow ``element`` (a sub-shape of result ``position`` of feature ``index``,
        in that result's local frame) back through the features. Iterative, memoized
        per node: the chain of a body the model built step by step is as long as
        its steps."""
        path: list[tuple[int, int, str, int]] = []
        current: tuple[int, int, Any] | None = (index, position, element)
        answer: tuple[tuple[int, int] | None, int | None] = (None, None)
        while current is not None:
            index, position, element = current
            feature = self.features[index]
            ordinal = self._ordinals(feature.results[position], element.ShapeType()).get(_key(element), 0)
            node = (index, position, kind, ordinal)
            if node in self._chains:
                answer = self._chains[node]
                break
            if node in path:
                break  # the feature returned the TShape it was handed: no feature made this
            path.append(node)
            entry = self._table(feature, position, kind).get(ordinal)
            if entry is None or entry[0] == "made":
                number = self._number(feature, position, kind, ordinal) if ordinal else None
                answer = ((index, number), None) if number is not None else (None, None)
                break
            _tag, j, k, _modified = entry
            source = self._source(index, j)
            if source[0] != "followed":
                answer = (None, None)  # passed on as it was from a shape no feature made
                break
            _followed, up, up_position, location = source
            given = self._elements(feature.handles[j], element.ShapeType()).FindKey(k)
            current = (up, up_position, given if location is None else given.Moved(location))
        # Unwind: a node whose entry was "modified" is the last modification seen
        # from above, so it overrides what the chain below it answered.
        for node in reversed(path):
            index, position, kind, ordinal = node
            entry = self._table(self.features[index], position, kind).get(ordinal)
            if entry is not None and entry[0] == "from" and entry[3]:
                answer = (answer[0], index)
            self._chains[node] = answer
        return answer

    def _number(self, feature: Feature, position: int, kind: str, ordinal: int) -> int | None:
        """The number of element ``ordinal`` of result ``position`` among the
        elements of ``kind`` that ``feature`` made, counted through its results in
        order, each result's in ordinal order (an element two results hold where
        they were returned counts once)."""
        topabs = _TOPABS[kind]
        numbers = feature._numbers.get(kind)
        if numbers is None:
            numbers = {}
            for at, result in enumerate(feature.results):
                if result is None:
                    continue
                table = self._table(feature, at, kind)
                for number_at, placed in enumerate(self._placed_keys(result, topabs), 1):
                    entry = table.get(number_at)
                    if (entry is None or entry[0] == "made") and placed not in numbers:
                        numbers[placed] = len(numbers) + 1
            feature._numbers[kind] = numbers
        return numbers.get(self._placed_keys(feature.results[position], topabs)[ordinal - 1])

    def _table(self, feature: Feature, position: int, kind: str) -> dict[int, tuple]:
        """Per element ordinal of one result (its local frame): ``("made",)`` or
        ``("from", input index, input element ordinal, modified)``."""
        key = (position, kind)
        table = feature._tables.get(key)
        if table is not None:
            return table
        topabs = _TOPABS[kind]
        result = feature.results[position]
        keys = self._mapped(result, topabs)[2]
        placed = self._placed_keys(result, topabs)
        table: dict[int, tuple] = {}
        # First by identity: the kernel keeps the faces and edges an operation
        # leaves alone, where the operation saw them, and a placement keeps them
        # all, each where it was in its shape; an element an input holds either
        # way passed through unchanged.
        inputs = [(j, self._placed_ordinals(handle, topabs), self._ordinals(handle, topabs))
                  for j, handle in enumerate(feature.handles) if handle is not None]
        held: set[tuple[int, int]] = set()
        same_shape: set[int] = set()
        for ordinal in range(1, len(keys) + 1):
            found = next(((j, at[placed[ordinal - 1]]) for j, at, _local in inputs if placed[ordinal - 1] in at), None)
            if found is None:
                found = next(((j, local[keys[ordinal - 1]]) for j, _at, local in inputs if keys[ordinal - 1] in local),
                             None)
            if found is not None:
                table[ordinal] = ("from", found[0], found[1], False)
                held.add(found)
                same_shape.add(ordinal)
        if len(table) < len(keys):
            # Then by geometry, among what the operation consumed: an input
            # element the result no longer holds is where a new one came from.
            same: dict[tuple, tuple[int, int]] = {}
            surface: dict[tuple, tuple[int, int]] = {}
            for j, handle in enumerate(feature.handles):
                if handle is None:
                    continue
                signatures = self._signatures(handle, kind)
                for k in range(1, len(self._mapped(handle, topabs)[2]) + 1):
                    if (j, k) in held:
                        continue
                    signature = self._signature(signatures, handle, topabs, kind, k)
                    same.setdefault(signature, (j, k))
                    surface.setdefault(signature[0], (j, k))
            signatures = self._signatures(result, kind)
            for ordinal in range(1, len(keys) + 1):
                if ordinal in table:
                    continue
                if not surface:
                    # Nothing consumed: every element the inputs do not hold is new.
                    table[ordinal] = ("made",)
                    continue
                signature = self._signature(signatures, result, topabs, kind, ordinal)
                found = same.get(signature)
                if found is not None:
                    table[ordinal] = ("from", found[0], found[1], False)
                    continue
                found = surface.get(signature[0])
                table[ordinal] = ("from", found[0], found[1], True) if found is not None else ("made",)
        # An element that came from an input no feature made is that shape's as it was
        # passed on, and this operation's where it rebuilt or trimmed it; one from an
        # input the trace cannot follow is this operation's: every element a feature
        # produced has a name.
        for ordinal, entry in table.items():
            if entry[0] != "from":
                continue
            source = self._source(feature.index, entry[1])[0]
            if source == "lost" or (source == "foreign" and ordinal not in same_shape):
                table[ordinal] = ("made",)
        feature._tables[key] = table
        return table

    def _signatures(self, handle: Any, kind: str) -> dict[int, tuple]:
        """The signatures of a shape's faces or edges in the frame it was seen
        in, by ordinal, filled as they are asked for: one table per (body,
        placement)."""
        key = (handle.TShape(), _placement(handle), kind)
        found = self._signatures_by_body.get(key)
        if found is None:
            found = self._signatures_by_body[key] = {}
        return found

    def _signature(self, signatures: dict[int, tuple], handle: Any, topabs: Any, kind: str, ordinal: int) -> tuple:
        signature = signatures.get(ordinal)
        if signature is None:
            element = self._elements(handle, topabs).FindKey(ordinal).Moved(handle.Location())
            signature = signatures[ordinal] = _SIGNATURES[kind](element)
        return signature

    def _elements(self, shape: Any, kind: Any) -> Any:
        """``TopExp.MapShapes`` of ``shape``'s elements of ``kind``, in its own frame."""
        return self._mapped(shape, kind)[0]

    def _ordinals(self, shape: Any, kind: Any) -> dict[tuple, int]:
        """Each element's key in its shape's own frame (:func:`_key`) -> its ordinal
        in :meth:`_elements`."""
        return self._mapped(shape, kind)[1]

    def _mapped(self, shape: Any, kind: Any) -> tuple[Any, dict[tuple, int], list[tuple]]:
        key = (shape.TShape(), kind)
        found = self._maps.get(key)
        if found is None:
            elements = _map(_local(shape), kind)
            keys = [_key(elements.FindKey(i)) for i in range(1, elements.Extent() + 1)]
            ordinals: dict[tuple, int] = {}
            for ordinal, element_key in enumerate(keys, 1):
                ordinals.setdefault(element_key, ordinal)
            found = self._maps[key] = (elements, ordinals, keys)
        return found

    def _placed_keys(self, handle: Any, kind: Any) -> list[tuple]:
        """Each element's key where ``handle`` has it -- the handle's own placement
        composed with the element's in it (:func:`_placed`) -- by ordinal."""
        location = handle.Location()
        if location.IsIdentity():
            return self._mapped(handle, kind)[2]
        key = (handle.TShape(), _placement(handle), kind)
        found = self._placed.get(key)
        if found is None:
            transform = location.Transformation()
            elements = self._elements(handle, kind)
            found = self._placed[key] = [_placed(transform, elements.FindKey(i)) for i in range(1, elements.Extent() + 1)]
        return found

    def _placed_ordinals(self, handle: Any, kind: Any) -> dict[tuple, int]:
        """:meth:`_placed_keys` as a map to ordinals (the first of two alike)."""
        ordinals: dict[tuple, int] = {}
        for ordinal, placed in enumerate(self._placed_keys(handle, kind), 1):
            ordinals.setdefault(placed, ordinal)
        return ordinals


# --- helpers ----------------------------------------------------------------------------


def _classify(filename: str) -> str:
    """``"model"`` for first-party source, ``"own"`` for cadgen's internal
    frames, ``"other"`` for everything skipped (build123d, cadgen's public
    helpers, the memo itself, the standard library)."""
    if not filename or filename.startswith("<"):
        return "other"
    try:
        path = Path(filename).resolve()
    except (OSError, RuntimeError):
        return "other"
    if path.parent == _HERE:
        return "other"
    if any(root in path.parents for root in _OWN):
        return "own"
    return "model" if is_first_party_source_file(path) else "other"


def handle_of(shape: Any) -> Any:
    """A handle copy of the shape's ``TopoDS`` from its own state, or None: an
    empty shape, or a child model's promise or a reference assembly, whose
    property would force what the body only placed."""
    state = getattr(shape, "__dict__", None)
    wrapped = None if state is None else state.get("_wrapped")
    return None if wrapped is None else wrapped.Located(wrapped.Location())


def _local(handle: Any) -> Any:
    return handle.Located(TopLoc_Location())


def _placement(handle: Any) -> tuple[int, ...]:
    return _transform(handle.Location().Transformation())


def _key(element: Any) -> tuple:
    """An element's identity in the shape it was mapped from: its TShape and its
    placement there (nothing for none)."""
    location = element.Location()
    return element.TShape(), () if location.IsIdentity() else _transform(location.Transformation())


def _placed(transform: Any, element: Any) -> tuple:
    """An element's identity where a shape placed by ``transform`` has it."""
    return element.TShape(), _transform(transform.Multiplied(element.Location().Transformation()))


def _transform(transform: Any) -> tuple[int, ...]:
    """A placement rounded as positions and directions are (an identity is ``()``)."""
    values = tuple(
        int(round(transform.Value(row, column) / (POSITION_QUANTUM if column == 4 else DIRECTION_QUANTUM)))
        for row in (1, 2, 3) for column in (1, 2, 3, 4)
    )
    return () if values == _IDENTITY else values


def _relative(element: Any, shape: Any) -> Any:
    """``element`` (of a shape ``shape`` is part of, in that shape's frame) in
    ``shape``'s own frame."""
    location = shape.Location()
    return element if location.IsIdentity() else element.Moved(location.Inverted())


def _map(shape: Any, kind: Any) -> Any:
    found = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, found)
    return found


def _q(value: float, quantum: float = POSITION_QUANTUM) -> int:
    scaled = value / quantum
    if not math.isfinite(scaled):
        raise ValueError("geometry coordinate is not finite")
    return int(round(scaled))


def _point(point: Any) -> tuple[int, int, int]:
    return _q(point.X()), _q(point.Y()), _q(point.Z())


def _direction(direction: Any) -> tuple[int, int, int]:
    """A direction rounded and sign-normalized: the line it spans, not its sense."""
    values = (_q(direction.X(), DIRECTION_QUANTUM), _q(direction.Y(), DIRECTION_QUANTUM), _q(direction.Z(), DIRECTION_QUANTUM))
    for value in values:
        if value:
            return values if value > 0 else tuple(-v for v in values)
    return values


def _axis_point(axis: Any) -> tuple[int, int, int]:
    """The point of an axis closest to the origin: names the line whatever point
    the kernel parametrizes it from."""
    location, direction = axis.Location(), axis.Direction()
    along = location.X() * direction.X() + location.Y() * direction.Y() + location.Z() * direction.Z()
    return (_q(location.X() - along * direction.X()), _q(location.Y() - along * direction.Y()),
            _q(location.Z() - along * direction.Z()))


def _samples(evaluate: Callable[..., Any], bounds: tuple[float, ...], count: int = _SAMPLES) -> tuple:
    """Points of a curve (two bounds) or surface (four) at a fixed grid over its bounds."""
    def steps(first: float, last: float) -> list[float]:
        return [first + (last - first) * i / (count - 1) for i in range(count)]

    if len(bounds) == 2:
        return tuple(_point(evaluate(u)) for u in steps(bounds[0], bounds[1]))
    return tuple(_point(evaluate(u, v)) for u in steps(bounds[0], bounds[1]) for v in steps(bounds[2], bounds[3]))


def _bounded(first: float, last: float) -> tuple[float, float]:
    """A parameter's natural bounds, or a fixed window about zero where the
    kernel leaves it unbounded: its infinity is the finite float 2e100, where a
    hyperbola overflows and every offset surface samples alike. The window
    names the curve or surface the same whatever trim an edge or face takes
    from it."""
    if any(not math.isfinite(bound) or Precision.IsInfinite_s(bound) for bound in (first, last)):
        return _WINDOW
    return first, last


def face_signature(face: Any) -> tuple[tuple, tuple]:
    """``(surface, extent)`` of a face in world coordinates: the surface it lies
    on (its class and parameters, or sample points of a freeform surface) and
    where it lies on it (its vertex points, else its middle point, and its edge
    count), rounded absolutely."""
    topods_face = TopoDS.Face_s(face)
    adaptor = BRepAdaptor_Surface(topods_face, False)
    kind = adaptor.GetType()
    if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
        plane = adaptor.Plane()
        normal, origin = plane.Axis().Direction(), plane.Location()
        offset = normal.X() * origin.X() + normal.Y() * origin.Y() + normal.Z() * origin.Z()
        direction = _direction(normal)
        raw = (_q(normal.X(), DIRECTION_QUANTUM), _q(normal.Y(), DIRECTION_QUANTUM), _q(normal.Z(), DIRECTION_QUANTUM))
        surface: tuple = ("plane", direction, _q(offset if raw == direction else -offset))
    elif kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        cylinder = adaptor.Cylinder()
        surface = ("cylinder", _direction(cylinder.Axis().Direction()), _axis_point(cylinder.Axis()), _q(cylinder.Radius()))
    elif kind == GeomAbs_SurfaceType.GeomAbs_Cone:
        cone = adaptor.Cone()
        surface = ("cone", _point(cone.Apex()), _direction(cone.Axis().Direction()), _q(abs(cone.SemiAngle()), DIRECTION_QUANTUM))
    elif kind == GeomAbs_SurfaceType.GeomAbs_Sphere:
        sphere = adaptor.Sphere()
        surface = ("sphere", _point(sphere.Location()), _q(sphere.Radius()))
    elif kind == GeomAbs_SurfaceType.GeomAbs_Torus:
        torus = adaptor.Torus()
        surface = ("torus", _point(torus.Location()), _direction(torus.Axis().Direction()),
                   _q(torus.MajorRadius()), _q(torus.MinorRadius()))
    else:
        geom = BRep_Tool.Surface_s(topods_face)
        u0, u1, v0, v1 = geom.Bounds()
        bounds = (*_bounded(u0, u1), *_bounded(v0, v1))
        surface = (str(kind).rsplit("_", 1)[-1].lower(), _samples(geom.Value, bounds))
    vertices = _map(face, TopAbs_VERTEX)
    points = sorted(_point(BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertices.FindKey(i)))) for i in range(1, vertices.Extent() + 1))
    if not points:
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(topods_face)
        points = [_point(adaptor.Value((umin + umax) / 2.0, (vmin + vmax) / 2.0))]
    extent = (tuple(points), _map(face, TopAbs_EDGE).Extent())
    return surface, extent


def vertex_signature(vertex: Any) -> tuple[tuple, tuple]:
    """``(point, ())`` of a vertex in world coordinates, rounded absolutely: a
    vertex has no extent, so one at the same point is the same vertex."""
    return _point(BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertex))), ()


def edge_signature(edge: Any) -> tuple[tuple, tuple]:
    """``(curve, extent)`` of an edge in world coordinates: the curve it lies on
    (its class and parameters, or sample points of a freeform curve) and its
    end points, rounded absolutely -- its vertices', or, for an edge the kernel built
    without vertices (a closed edge of a loft or sweep), its curve's ends."""
    topods_edge = TopoDS.Edge_s(edge)
    first, last = TopExp.FirstVertex_s(topods_edge, True), TopExp.LastVertex_s(topods_edge, True)
    if first.IsNull() or last.IsNull():
        ends = BRepAdaptor_Curve(topods_edge)
        first_point, last_point = (_point(ends.Value(ends.FirstParameter())),
                                   _point(ends.Value(ends.LastParameter())))
    else:
        first_point, last_point = _point(BRep_Tool.Pnt_s(first)), _point(BRep_Tool.Pnt_s(last))
    extent = tuple(sorted((first_point, last_point)))
    if BRep_Tool.Degenerated_s(topods_edge):
        return ("degenerate", first_point), extent
    adaptor = BRepAdaptor_Curve(topods_edge)
    kind = adaptor.GetType()
    if kind == GeomAbs_CurveType.GeomAbs_Line:
        line = adaptor.Line()
        curve: tuple = ("line", _direction(line.Direction()), _axis_point(line.Position()))
    elif kind == GeomAbs_CurveType.GeomAbs_Circle:
        circle = adaptor.Circle()
        curve = ("circle", _point(circle.Location()), _direction(circle.Axis().Direction()), _q(circle.Radius()))
    elif kind == GeomAbs_CurveType.GeomAbs_Ellipse:
        ellipse = adaptor.Ellipse()
        curve = ("ellipse", _point(ellipse.Location()), _direction(ellipse.Axis().Direction()),
                 _q(ellipse.MajorRadius()), _q(ellipse.MinorRadius()))
    else:
        geom = BRep_Tool.Curve_s(topods_edge, 0.0, 0.0)
        bounds = _bounded(geom.FirstParameter(), geom.LastParameter())
        curve = (str(kind).rsplit("_", 1)[-1].lower(), _samples(geom.Value, bounds, 5))
    return curve, extent


_SIGNATURES = {"face": face_signature, "edge": edge_signature, "vertex": vertex_signature}
