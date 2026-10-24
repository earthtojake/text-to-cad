"""What the kernel's makers report while a feature runs: the history its elements are
named by.

A feature (``trace``) is one build123d call, and inside it build123d runs OCCT
makers -- a boolean and the clean that unifies what it left, a prism, a fillet, a wire, a
face and the fixes it gets -- each of which knows, of the shapes it was given, which of
its results it modified or generated from each of their faces, edges and vertices. This
module patches those makers once per process (``install``, called by
``memo.install``): a maker's constructor and the methods that hand it shapes
(``Add``, ``SetArguments``, ``Init`` ...) note the shapes as its inputs, and the methods
that hand back what it made (``Shape``, ``Face``, ``Result`` ...) note its result, in a
list that exists only while a feature call is open (``recording``). A maker run by a
build123d call nested inside the feature's belongs to the feature.

Right after the call, ``compose`` follows every element of the feature's inputs through
those makers, in the order their results were taken: an element a maker still holds is
itself, one it reports as modified or generated becomes what it reports, and one copied
stays itself (a copy is not a change); so the chain a boolean is -- the boolean, then
the clean -- or a face from a wire -- the fixes, the face, the fix of the face -- reads as
one step from the feature's inputs to its results, and a maker whose result never
reaches them changes nothing. Each maker is asked only about sub-shapes of its own inputs:
OCCT answers a question about a shape it never saw with an exception, which costs
milliseconds, and a list it hands back is never iterated (the same cost; ``listed``);
a clean or a fix whose history records nothing is asked nothing. The answer is the
feature's ``History``: for each face, edge and vertex of each result, by its ordinal
there, the elements of the inputs it came from -- input, kind, ordinal -- and how.
Ordinals, so the kernel memo keeps a History with its entry and a hit, which hands back
the very shapes, reads it as the miss computed it without running a maker.

How a maker reports (``_ADAPTERS``): a ``BRepBuilderAPI_MakeShape`` by ``Modified`` and
``Generated``; a prism or a revolution also by ``FirstShape``/``LastShape`` of each
sub-shape of its profile (an extrusion's top face is generated from the profile face; a
full revolution's seam is the profile edge itself); the clean
(``ShapeUpgrade_UnifySameDomain``), a ``BRepTools_ReShape`` and the fixes (``ShapeFix_*``,
through their context) by their ``History``; a sewing by ``Modified``/
``ModifiedSubShape``; a copy (``BRepBuilderAPI_Copy``) by ``Modified``, as the same
elements; a transformation (``Transform``, ``GTransform``) by ``Modified``, as modified,
so a mirrored copy is not its original; ``LocOpe_DPrism`` by ``Shapes``. A wire
(``BRepBuilderAPI_MakeWire``) reports nothing and copies every edge whose vertices it
merges: an edge of its result on the same curve object as an edge it was given, over
the same parameters, is that edge copied -- the identity of the kernel's curve, never a
measurement. A maker with no input (a primitive, an edge from a curve, a polygon from
points, a text) has nothing to report and is not patched.
"""

from __future__ import annotations

import bisect
import functools
import itertools
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS_Shape
from OCP.TopTools import TopTools_IndexedMapOfShape, TopTools_ListOfShape

__all__ = ["History", "KINDS", "by_ordinal", "compose", "install", "listed", "recording", "stats", "uninstall"]

# The element kinds named, in the order a source is preferred by (FreeCAD's NameKey: a
# vertex before an edge before a face), with the kernel's enum for each.
KINDS = (TopAbs_VERTEX, TopAbs_EDGE, TopAbs_FACE)
_KIND = {TopAbs_VERTEX: 0, TopAbs_EDGE: 1, TopAbs_FACE: 2}
# How an element came from a source: the same element copied, modified, generated.
SAME, MODIFIED, GENERATED = "I", "M", "G"
_STRENGTH = {SAME: 0, MODIFIED: 1, GENERATED: 2}

_LOCAL = threading.local()
_ORDER = itertools.count(1)
_ABSENT = object()
# An object's identity, unique among live objects as id() is, without the audit event
# id() raises: inside a build every audit hook (the file trace's, the execution hashes')
# sees each one, which made an identity lookup cost ten times its own work.
_object_key = object.__hash__
_FACE_AND_BELOW = frozenset(int(kind) for kind in (TopAbs_FACE, TopAbs_WIRE, TopAbs_EDGE, TopAbs_VERTEX))
_STATS = {"queries": 0, "raised": 0, "errors": 0}
_installed = False


def stats() -> dict[str, int]:
    """History queries asked, how many raised (the never-ask-what-it-never-saw rule makes
    that zero) and compositions that failed (the feature is then named without history)."""
    return dict(_STATS)


@dataclass
class History:
    """A feature's history: ``origins[(result position, kind, ordinal)]`` is a tuple of
    ``(input index, source kind, source ordinal, how, place)`` -- kinds by their index in
    :data:`KINDS`, ordinals in ``TopExp.MapShapes`` of the shape as given or returned,
    ``how`` one of ``I`` (copied), ``M`` (modified), ``G`` (generated), and ``place`` the
    element's position among what the maker reported of that source (a tuple, one
    position per maker of the chain that made it out of another: FreeCAD's index, which
    tells apart elements made alike from the same sources). An element no maker reported
    has no entry. ``structures`` holds only complete feature naming structures;
    ``result_rules`` separately holds complete first-input identity tables for
    individual results, computed by the trace and reused on hits (``kernel_trace``)."""

    origins: Mapping[tuple[int, int, int], tuple[tuple[int, int, int, str, tuple[int, ...]], ...]] = field(
        default_factory=dict)
    structures: dict[Any, Any] = field(default_factory=dict, repr=False)
    # Complete first-input identity tables, separately from full structures:
    # (structure key, result position) -> immutable s/x rules, or a null result.
    # Only input indices/ordinals, never native maps or a run's feature nodes.
    result_rules: dict[Any, Any] = field(default_factory=dict, repr=False)
    # A whole body copied by an actual Copy maker, not inferred from element
    # history: result position -> source body and result-to-source ordinals.
    copies: dict[int, "Copy"] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class Copy:
    """A complete bijection a ``BRepBuilderAPI_Copy`` reported for one body.

    ``ordinals[kind][result ordinal - 1]`` is the source ordinal. The source is
    an owned handle at the copy boundary; its placement does not name the body.
    This says nothing about whether that body's construction is memoizable.
    """

    source: Any
    ordinals: tuple[tuple[int, ...], ...]


class _Origins(Mapping):
    """Exact Copy origins, synthesized from frozen global-input ordinal vectors.

    Independent of certificates, with no native handles or expanding read cache.
    Sparse rows retain ordinary composition's values verbatim.
    """

    def __init__(self, vectors: dict[int, tuple], sparse: dict) -> None:
        self.vectors = vectors
        self.sparse = sparse
        self.size = len(sparse) + sum(sum(ordinal != 0 for ordinal in ordinals)
                                      for kinds in vectors.values() for _owners, ordinals in kinds)

    def __getitem__(self, key: tuple) -> tuple:
        found = self.get(key, _ABSENT)
        if found is _ABSENT:
            raise KeyError(key)
        return found

    def get(self, key: tuple, default: Any = None) -> Any:
        """``self[key]``, or ``default``: every element of a copied result is asked, and a
        miss is no exception raised and caught."""
        found = self.sparse.get(key, _ABSENT)
        if found is not _ABSENT:
            return found
        if not isinstance(key, tuple) or len(key) != 3:
            return default
        position, kind, ordinal = key
        kinds = self.vectors.get(position)
        if kinds is None or not isinstance(kind, int) or not 0 <= kind < len(KINDS) or not isinstance(ordinal, int):
            return default
        owners, ordinals = kinds[kind]
        if not 0 < ordinal <= len(ordinals) or not ordinals[ordinal - 1]:
            return default
        j = owners if isinstance(owners, int) else owners[ordinal - 1]
        return ((j, kind, ordinals[ordinal - 1], SAME, (1,)),)

    def __iter__(self) -> Iterator[tuple[int, int, int]]:
        yield from self.sparse
        for position, kinds in self.vectors.items():
            for kind, (_owners, ordinals) in enumerate(kinds):
                for ordinal, source in enumerate(ordinals, 1):
                    key = position, kind, ordinal
                    if source and key not in self.sparse:
                        yield key

    def __len__(self) -> int:
        return self.size


class _CopyRows:
    """Temporary direct-source evidence for one Copy; released after compose."""

    def __init__(self, result: Any, maps: list, local: list[list[int]], start: int) -> None:
        self.result = result
        self.maps = maps
        self.local = local
        self.start = start
        self.stop = start + sum(len(kind) for kind in local)
        self.owners = [[0] * len(kind) for kind in local]
        self.ordinals = [[0] * len(kind) for kind in local]
        self.local_frozen: tuple | None = None
        self.frozen: tuple | None = None

    def origin(self, kind: int, ordinal: int) -> tuple:
        return ((self.owners[kind][ordinal - 1], kind, self.ordinals[kind][ordinal - 1], SAME, (1,)),)

    def freeze(self) -> tuple:
        if self.frozen is None:
            kinds = []
            for kind, (owners, ordinals) in enumerate(zip(self.owners, self.ordinals)):
                owner = owners[0] if owners and all(j == owners[0] for j in owners) else tuple(owners)
                # Usually the feature input is the copied body itself. Keep
                # the same immutable vector without depending on Copy's lifetime.
                held = (self.local_frozen[kind] if self.local_frozen is not None and ordinals == self.local[kind]
                        else tuple(ordinals))
                kinds.append((owner, held))
            self.frozen = tuple(kinds)
        return self.frozen


def _compact_origins(rows: list[_CopyRows], results: list[Any], reported: Any) -> _Origins | None:
    """Bind direct/located results and prove all other output memberships now.

    Any conflicting actual/partner membership requests the ordinary placement
    merge. Only immutable integer vectors and sparse values escape this helper.
    """
    tops: dict[Any, list[_CopyRows]] = {}
    for row in rows:
        tops.setdefault(row.result.TShape(), []).append(row)
    ends = [row.stop for row in rows]

    def origin(at: int) -> tuple:
        row = rows[bisect.bisect_left(ends, at)]
        offset = row.start
        for kind, ordinals in enumerate(row.local):
            if at <= offset + len(ordinals):
                ordinal = row.maps[kind].FindIndex(reported.FindKey(at))
                return row.origin(kind, ordinal)
            offset += len(ordinals)
        raise AssertionError("reported Copy element outside its record")

    vectors: dict[int, tuple] = {}
    sparse: dict = {}
    for position, result in enumerate(results):
        if result is None:
            continue
        candidates = tops.get(result.TShape(), ())
        if len(candidates) > 1:
            return None
        row = candidates[0] if candidates else None
        if row is not None and row.result.IsSame(result):
            vectors[position] = row.freeze()
            continue
        # Legacy placement checks the actual result AND each located partner
        # map. A sole partner supplies its ordinal vector, but actual matches
        # must agree; otherwise let _places/_merged retain their exact order.
        for kind, topabs in enumerate(KINDS):
            elements = _map(result, topabs)
            if row is not None and elements.Extent() != len(row.local[kind]):
                return None
            for ordinal in range(1, elements.Extent() + 1):
                at = reported.FindIndex(elements.FindKey(ordinal))
                if not at:
                    continue
                found = origin(at)
                if row is not None:
                    if found != row.origin(kind, ordinal):
                        return None
                else:
                    sparse[(position, kind, ordinal)] = found
        if row is not None:
            vectors[position] = row.freeze()
    return _Origins(vectors, sparse)


# --- recording ------------------------------------------------------------------------------


class _Record:
    """One maker the feature ran: the shapes it was given and what it handed back."""

    __slots__ = ("maker", "adapter", "inputs", "result", "order")

    def __init__(self, maker: Any, adapter: "_Adapter") -> None:
        self.maker = maker
        self.adapter = adapter
        self.inputs: list[Any] = []
        self.result: Any = None
        self.order = 0


class recording:
    """The makers run on this thread until the block ends, in a list (``compose``'s third
    argument). The list holds them alive; it is the feature call's, and gone with it. A
    plain context manager: every feature call opens one."""

    __slots__ = ("_previous",)

    def __enter__(self) -> list[_Record]:
        self._previous = getattr(_LOCAL, "records", None), getattr(_LOCAL, "index", None)
        records: list[_Record] = []
        _LOCAL.records, _LOCAL.index = records, {}
        return records

    def __exit__(self, *exc_info: object) -> None:
        _LOCAL.records, _LOCAL.index = self._previous


def _record(maker: Any, adapter: "_Adapter") -> _Record | None:
    records = getattr(_LOCAL, "records", None)
    if records is None:
        return None
    index = _LOCAL.index
    record = index.get(_object_key(maker))
    if record is None or record.maker is not maker:
        record = index[_object_key(maker)] = _Record(maker, adapter)
        records.append(record)
    return record


def _note_inputs(record: _Record, values: Any) -> None:
    """The shapes among a call's arguments, as the maker was handed them: a list of shapes
    read without iterating it (``listed``)."""
    for value in values:
        if isinstance(value, TopoDS_Shape):
            if not value.IsNull():
                record.inputs.append(value.Located(value.Location()))
        elif isinstance(value, TopTools_ListOfShape):
            record.inputs.extend(listed(value))
        elif type(value).__name__.startswith("TopTools_") and hasattr(value, "Length") and hasattr(value, "Value"):
            for index in range(1, value.Length() + 1):
                shape = value.Value(index)
                if isinstance(shape, TopoDS_Shape) and not shape.IsNull():
                    record.inputs.append(shape.Located(shape.Location()))


def listed(shapes: Any) -> list[Any]:
    """A ``TopTools_ListOfShape``'s members, never iterated from Python (the exception that
    ends an iteration costs milliseconds): none, its first, or its first and last -- what
    nearly every answer holds -- else the list copied and taken from the copy's head."""
    size = shapes.Size()
    if size < 3:
        return [] if size == 0 else [shapes.First()] if size == 1 else [shapes.First(), shapes.Last()]
    copy = TopTools_ListOfShape()
    copy.Assign(shapes)
    found = []
    for _member in range(size):
        found.append(copy.First())
        copy.RemoveFirst()
    return found


# --- adapters: how each maker reports -------------------------------------------------------


@dataclass(frozen=True)
class _Adapter:
    """``prepare(maker)`` returns ``query(sub-shape) -> [(shape, how)]``, or None for a
    maker with nothing to report; ``generator`` makers make new elements from elements
    they keep (a prism's sides from the profile it keeps as its bottom), so every
    sub-shape of their inputs is asked about, where any other maker is asked only about
    those its result no longer holds."""

    prepare: Callable[[Any], Callable[[Any], list[tuple[Any, str]]] | None]
    generator: bool = False


def _made(maker: Any) -> Callable[[Any], list[tuple[Any, str]]]:
    def query(sub: Any) -> list[tuple[Any, str]]:
        return ([(shape, MODIFIED) for shape in listed(maker.Modified(sub))]
                + [(shape, GENERATED) for shape in listed(maker.Generated(sub))])
    return query


def _swept(maker: Any) -> Callable[[Any], list[tuple[Any, str]]]:
    """A sweep's ``FirstShape(s)`` is ``s`` where the sweep began -- itself, or the copy a
    sweep asked to copy its profile makes (build123d's revolution does) -- and its
    ``LastShape(s)`` is generated from ``s``, unless it is the first again (a full turn)."""
    made = _made(maker)

    def query(sub: Any) -> list[tuple[Any, str]]:
        found = made(sub)
        first, last = maker.FirstShape(sub), maker.LastShape(sub)
        if not first.IsNull() and not first.IsSame(sub):
            found.append((first, SAME))
        if not last.IsNull() and not last.IsSame(sub) and (first.IsNull() or not last.IsSame(first)):
            found.append((last, GENERATED))
        return found
    return query


def _from_history(history: Any) -> Callable[[Any], list[tuple[Any, str]]] | None:
    """A history's answers; None for one that recorded nothing modified or generated (a
    clean or a fix that changed nothing), which has nothing to say of any shape."""
    if history is None or not (history.HasModified() or history.HasGenerated()):
        return None

    def query(sub: Any) -> list[tuple[Any, str]]:
        return ([(shape, MODIFIED) for shape in listed(history.Modified(sub))]
                + [(shape, GENERATED) for shape in listed(history.Generated(sub))])
    return query


def _recorded(maker: Any) -> Callable[[Any], list[tuple[Any, str]]] | None:
    return _from_history(maker.History())


def _fixed(maker: Any) -> Callable[[Any], list[tuple[Any, str]]] | None:
    context = maker.Context()
    return None if context is None else _from_history(context.History())


def _sewn(maker: Any) -> Callable[[Any], list[tuple[Any, str]]]:
    def query(sub: Any) -> list[tuple[Any, str]]:
        if maker.IsModified(sub):
            shape = maker.Modified(sub)
        elif maker.IsModifiedSubShape(sub):
            shape = maker.ModifiedSubShape(sub)
        else:
            return []
        return [] if shape.IsNull() or shape.IsSame(sub) else [(shape, MODIFIED)]
    return query


def _copied(maker: Any) -> Callable[[Any], list[tuple[Any, str]]]:
    def query(sub: Any) -> list[tuple[Any, str]]:
        return [(shape, SAME) for shape in listed(maker.Modified(sub))]
    return query


def _transformed(maker: Any) -> Callable[[Any], list[tuple[Any, str]]]:
    def query(sub: Any) -> list[tuple[Any, str]]:
        return [(shape, MODIFIED) for shape in listed(maker.Modified(sub))]
    return query


def _tapered(maker: Any) -> Callable[[Any], list[tuple[Any, str]]]:
    def query(sub: Any) -> list[tuple[Any, str]]:
        return [(shape, GENERATED) for shape in listed(maker.Shapes(sub))]
    return query


_MAKER = _Adapter(_made)
_GENERATOR = _Adapter(_made, generator=True)
_COPY = _Adapter(_copied)
_WIRE = _Adapter(lambda maker: None)  # composed by its own rule (_wire_copies)

# (module, class, adapter): the makers build123d 0.11.1's topology modules construct that
# are given shapes. A class OCP no longer has is an error: the table is this version's.
_ADAPTERS = (
    ("OCP.BRepAlgoAPI", "BRepAlgoAPI_Cut", _MAKER),
    ("OCP.BRepAlgoAPI", "BRepAlgoAPI_Fuse", _MAKER),
    ("OCP.BRepAlgoAPI", "BRepAlgoAPI_Common", _MAKER),
    ("OCP.BRepAlgoAPI", "BRepAlgoAPI_Section", _MAKER),
    ("OCP.BRepAlgoAPI", "BRepAlgoAPI_Splitter", _MAKER),
    ("OCP.BOPAlgo", "BOPAlgo_Splitter", _MAKER),
    ("OCP.ShapeUpgrade", "ShapeUpgrade_UnifySameDomain", _Adapter(_recorded)),
    ("OCP.BRepTools", "BRepTools_ReShape", _Adapter(_recorded)),
    ("OCP.ShapeFix", "ShapeFix_Shape", _Adapter(_fixed)),
    ("OCP.ShapeFix", "ShapeFix_Face", _Adapter(_fixed)),
    ("OCP.ShapeFix", "ShapeFix_Wire", _Adapter(_fixed)),
    ("OCP.ShapeFix", "ShapeFix_Solid", _Adapter(_fixed)),
    ("OCP.ShapeFix", "ShapeFix_Wireframe", _Adapter(_fixed)),
    ("OCP.BRepBuilderAPI", "BRepBuilderAPI_Copy", _COPY),
    ("OCP.BRepBuilderAPI", "BRepBuilderAPI_Transform", _Adapter(_transformed)),
    ("OCP.BRepBuilderAPI", "BRepBuilderAPI_GTransform", _Adapter(_transformed)),
    ("OCP.BRepBuilderAPI", "BRepBuilderAPI_Sewing", _Adapter(_sewn)),
    ("OCP.BRepBuilderAPI", "BRepBuilderAPI_MakeWire", _WIRE),
    ("OCP.BRepBuilderAPI", "BRepBuilderAPI_MakeFace", _MAKER),
    ("OCP.BRepBuilderAPI", "BRepBuilderAPI_MakeSolid", _MAKER),
    ("OCP.BRepPrimAPI", "BRepPrimAPI_MakePrism", _Adapter(_swept, generator=True)),
    ("OCP.BRepPrimAPI", "BRepPrimAPI_MakeRevol", _Adapter(_swept, generator=True)),
    ("OCP.BRepPrimAPI", "BRepPrimAPI_MakeHalfSpace", _GENERATOR),
    ("OCP.BRepFilletAPI", "BRepFilletAPI_MakeFillet", _MAKER),
    ("OCP.BRepFilletAPI", "BRepFilletAPI_MakeChamfer", _MAKER),
    ("OCP.BRepOffsetAPI", "BRepOffsetAPI_ThruSections", _GENERATOR),
    ("OCP.BRepOffsetAPI", "BRepOffsetAPI_MakePipe", _GENERATOR),
    ("OCP.BRepOffsetAPI", "BRepOffsetAPI_MakePipeShell", _GENERATOR),
    ("OCP.BRepOffsetAPI", "BRepOffsetAPI_MakeOffset", _GENERATOR),
    ("OCP.BRepOffsetAPI", "BRepOffsetAPI_MakeThickSolid", _GENERATOR),
    ("OCP.BRepOffsetAPI", "BRepOffsetAPI_MakeFilling", _GENERATOR),
    ("OCP.BRepOffsetAPI", "BRepOffsetAPI_DraftAngle", _MAKER),
    ("OCP.BRepOffset", "BRepOffset_MakeOffset", _GENERATOR),
    ("OCP.BRepFeat", "BRepFeat_MakeDPrism", _GENERATOR),
    ("OCP.BRepFeat", "BRepFeat_SplitShape", _MAKER),
    ("OCP.LocOpe", "LocOpe_DPrism", _Adapter(_tapered, generator=True)),
)
# The methods that hand a maker shapes after it is constructed, and those that hand back
# what it made; each patched where the class has it.
_SETTERS = ("Add", "AddWire", "AddVertex", "SetArguments", "SetTools", "Init", "Initialize", "Load")
_FINISHERS = ("Shape", "Face", "Edge", "Wire", "Vertex", "Solid", "Shell", "Result", "SewedShape")


def install() -> bool:
    """Patch the makers of :data:`_ADAPTERS`, once per process. Returns installed-now."""
    global _installed
    if _installed:
        return False
    import importlib

    for module_name, class_name, adapter in _ADAPTERS:
        cls = getattr(importlib.import_module(module_name), class_name)
        _patch(cls, "__init__", _initializer(cls.__init__, adapter))
        for name in _SETTERS:
            original = cls.__dict__.get(name) or getattr(cls, name, None)
            if original is not None:
                _patch(cls, name, _setter(original, adapter))
        for name in _FINISHERS:
            original = cls.__dict__.get(name) or getattr(cls, name, None)
            if original is not None:
                _patch(cls, name, _finisher(original))
    _installed = True
    return True


def uninstall() -> bool:
    """Restore every method ``install`` replaced. Returns uninstalled-now."""
    global _installed
    if not _installed:
        return False
    import importlib

    for module_name, class_name, _adapter in _ADAPTERS:
        cls = getattr(importlib.import_module(module_name), class_name)
        for name in ("__init__", *_SETTERS, *_FINISHERS):
            patched = cls.__dict__.get(name)
            if patched is not None and getattr(patched, "__kernel_history__", False):
                setattr(cls, name, patched.__wrapped__)
    _installed = False
    return True


def _patch(cls: type, name: str, wrapper: Any) -> None:
    current = cls.__dict__.get(name)
    if current is not None and getattr(current, "__kernel_history__", False):
        return
    setattr(cls, name, wrapper)


def _initializer(original: Any, adapter: _Adapter) -> Any:
    if getattr(original, "__kernel_history__", False):
        original = original.__wrapped__

    @functools.wraps(original)
    def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
        original(self, *args, **kwargs)
        record = _record(self, adapter)
        if record is not None:
            _note_inputs(record, (*args, *kwargs.values()))

    __init__.__kernel_history__ = True
    __init__.__wrapped__ = original
    return __init__


def _setter(original: Any, adapter: _Adapter) -> Any:
    if getattr(original, "__kernel_history__", False):
        original = original.__wrapped__

    @functools.wraps(original)
    def setter(self: Any, *args: Any, **kwargs: Any) -> Any:
        answer = original(self, *args, **kwargs)
        record = _record(self, adapter)
        if record is not None:
            _note_inputs(record, (*args, *kwargs.values()))
        return answer

    setter.__kernel_history__ = True
    setter.__wrapped__ = original
    return setter


def _finisher(original: Any) -> Any:
    if getattr(original, "__kernel_history__", False):
        original = original.__wrapped__

    @functools.wraps(original)
    def finisher(self: Any, *args: Any, **kwargs: Any) -> Any:
        answer = original(self, *args, **kwargs)
        index = getattr(_LOCAL, "index", None)
        if index is not None and isinstance(answer, TopoDS_Shape) and not answer.IsNull():
            record = index.get(_object_key(self))
            if record is not None and record.maker is self and record.result is None:
                record.result = answer.Located(answer.Location())
                record.order = next(_ORDER)
        return answer

    finisher.__kernel_history__ = True
    finisher.__wrapped__ = original
    return finisher


# --- composition --------------------------------------------------------------------------


def _map(shape: Any, kind: Any) -> Any:
    found = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, found)
    return found


def _merge(by_source: dict, source: tuple[int, int, int], how: str, place: tuple[int, ...]) -> None:
    """An origin added to ``by_source`` (source element -> ``(how, place)``): one per source
    element, the stronger account kept where a source arrives twice (generated over
    modified over copied), and its first place."""
    known = by_source.get(source)
    by_source[source] = (how, place) if known is None else (
        how if _STRENGTH[how] > _STRENGTH[known[0]] else known[0], min(place, known[1]))


def _merged(found: tuple, more: tuple) -> tuple:
    """Origins ``more`` added to ``found`` (``_merge``)."""
    by_source = {(j, kind, ordinal): (how, place) for j, kind, ordinal, how, place in found}
    for j, kind, ordinal, how, place in more:
        _merge(by_source, (j, kind, ordinal), how, place)
    return tuple((j, kind, ordinal, how, place) for (j, kind, ordinal), (how, place) in by_source.items())


def _then(first: str, second: str) -> str:
    """An element that came from its source ``first`` and then from that ``second``."""
    if first == SAME:
        return second
    if second == SAME:
        return first
    return GENERATED if GENERATED in (first, second) else MODIFIED


def _held(shape: Any) -> set:
    """The TShapes a shape is made of whole: itself and every compound, solid, shell and
    face it holds -- what one maker's result can reach another's, or a feature's, as. A
    face, a wire, an edge or a vertex holds none of those but itself."""
    found = {shape.TShape()}
    if int(shape.ShapeType()) in _FACE_AND_BELOW:
        return found
    for kind in (TopAbs_COMPOUND, TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE):
        held = _map(shape, kind)
        found.update(held.FindKey(index).TShape() for index in range(1, held.Extent() + 1))
    return found


def _feeding(taken: list[_Record], results: list[Any]) -> list[_Record]:
    """The makers whose results reach the feature's results -- held by one of them, or
    by the input of a maker that does -- in order: what FreeCAD's mapper chain follows.
    build123d runs makers whose results it drops (an attempt it gives up, as a clean that
    fails), and those report nothing of the feature. A maker whose result
    is one of the shapes reached, or held whole by one, is found so: the shapes reached
    are opened (``_held``) only for a result that is not one of them, and once each, and
    that result only when no shape they hold is it."""
    tops = {shape.TShape() for shape in results if shape is not None}
    unopened = [shape for shape in results if shape is not None]
    wanted: set = set()
    feeding = []
    for at in range(len(taken) - 1, -1, -1):
        record = taken[at]
        top = record.result.TShape()
        if top not in tops:
            for shape in unopened:
                wanted |= _held(shape)
            unopened.clear()
            if top not in wanted and wanted.isdisjoint(_held(record.result)):
                continue
        feeding.append(record)
        if at:
            tops.update(shape.TShape() for shape in record.inputs)
            unopened.extend(record.inputs)
    feeding.reverse()
    return feeding


def by_ordinal(source: Any, result: Any, how: str) -> History | None:
    """The history of a maker that reported nothing, where its result maps one-to-one onto
    the one shape it was given: as many vertices, edges and faces, each face bounded by the
    edges of the same ordinals and each edge by the vertices of the same ordinals -- what a
    copy or a placement of the shape is, element for element. Each element of the result
    then comes from the element of its ordinal, ``how`` (``M`` for a transformation, ``I``
    for a copy); None where the two do not map so."""
    sources = [_map(source, kind) for kind in KINDS]
    results = [_map(result, kind) for kind in KINDS]
    if any(a.Extent() != b.Extent() for a, b in zip(sources, results)):
        return None
    for upper in (2, 1):
        for ordinal in range(1, sources[upper].Extent() + 1):
            lower = KINDS[upper - 1]
            first = _map(sources[upper].FindKey(ordinal), lower)
            second = _map(results[upper].FindKey(ordinal), lower)
            if first.Extent() != second.Extent():
                return None
            if sorted(sources[upper - 1].FindIndex(first.FindKey(at)) for at in range(1, first.Extent() + 1)) != \
                    sorted(results[upper - 1].FindIndex(second.FindKey(at)) for at in range(1, second.Extent() + 1)):
                return None
    return History(origins={(0, kind, ordinal): ((0, kind, ordinal, how, (1,)),)
                            for kind in range(len(KINDS)) for ordinal in range(1, results[kind].Extent() + 1)})


def _simple_copy_rows(taken: list[_Record]) -> list[_CopyRows] | None:
    """A compact attempt only where every feeding maker can give a direct Copy."""
    return [] if all(record.adapter is _COPY and len(record.inputs) == 1 for record in taken) else None


def compose(inputs: list[Any], results: list[Any], records: list[_Record]) -> History:
    """The feature's :class:`History`: ``inputs`` the shapes it was given as it was given
    them (None where empty), ``results`` the shapes it returned (None where empty) and
    ``records`` the makers it ran (``recording``)."""
    taken = sorted((record for record in records if record.result is not None), key=lambda record: record.order)
    if not taken or not any(shape is not None for shape in results):
        return History()
    all_taken = taken
    taken = _feeding(taken, results)
    if not taken:
        return History()
    given: list[list | None] = [None] * len(inputs)
    reported = TopTools_IndexedMapOfShape()
    # Per reported shape, by its index there: the shape, its kind (an index of ``KINDS``)
    # and its origins by source element -- (how, place), merged as they come (``_merge``).
    shapes: list[Any] = []
    kinds: list[int] = []
    origins: list[dict[tuple[int, int, int], tuple[str, tuple[int, ...]]]] = []
    compact = _simple_copy_rows(taken)

    def source(sub: Any, kind: int) -> tuple | None:
        index = reported.FindIndex(sub)
        if index:
            promote()  # prior reported history takes precedence over feature inputs
            return tuple((j, k, o, how, place) for (j, k, o), (how, place) in origins[index - 1].items())
        for j, shape in enumerate(inputs):
            if shape is None:
                continue
            maps = given[j]
            if maps is None:
                maps = given[j] = [_map(shape, topabs) for topabs in KINDS]
            ordinal = maps[kind].FindIndex(sub)
            if ordinal:
                return ((j, kind, ordinal, SAME, ()),)
        return None

    def reporting(shape: Any, kind: int) -> dict:
        """The origins of ``shape``, of ``kind``, as reported so far: new for a new one."""
        index = reported.Add(shape)
        if index > len(origins):
            shapes.append(shape)
            kinds.append(kind)
            origins.append({})
        return origins[index - 1]

    def report(shape: Any, found: tuple) -> None:
        merged = reporting(shape, _KIND[shape.ShapeType()])
        for j, k, o, how, place in found:
            _merge(merged, (j, k, o), how, place)

    def promote() -> None:
        """Expand only the already reported numeric prefix, without a query.

        Copy vectors are in target order; the eager reporter first saw them in
        source ordinal order. Include the current record's partial prefix too.
        """
        nonlocal compact
        if compact is None:
            return
        prefix, compact = compact, None
        for row in prefix:
            for kind, ordinals in enumerate(row.local):
                targets = [0] * len(ordinals)
                for target, ordinal in enumerate(ordinals, 1):
                    if ordinal and row.ordinals[kind][target - 1]:
                        targets[ordinal - 1] = target
                for target in targets:
                    if target:
                        report(row.maps[kind].FindKey(target), row.origin(kind, target))

    def answers_from(sub: Any, found: tuple, answers: list) -> None:
        for at, (made, how) in enumerate(answers, 1):
            made_kind = _KIND.get(made.ShapeType())
            if made_kind is None or made.IsSame(sub):
                continue
            merged = reporting(made, made_kind)
            for j, k, o, was, place in found:
                _merge(merged, (j, k, o), _then(was, how), (*place, at))

    copied: list[tuple[_Record, Copy]] = []
    for record in taken:
        if record.adapter is _WIRE:
            _wire_copies(record, source, report)
            continue
        query = _prepared(record)
        if query is None:
            promote()  # its result may still be a legacy located-partner alternative
            continue
        held = None if record.adapter.generator else [_map(record.result, kind) for kind in KINDS]
        # Reuse the answers needed for element history. Whole-copy identity needs
        # more than I origins: exactly one same-kind answer per source element,
        # covering every result element once, from an actual Copy maker.
        copying = record.adapter is _COPY and len(record.inputs) == 1
        copy_ordinals = [[0] * elements.Extent() for elements in held] if copying else None
        row = None
        if compact is not None:
            row = _CopyRows(record.result, held, copy_ordinals, reported.Extent())
            compact.append(row)
        for shape in record.inputs:
            for kind, topabs in enumerate(KINDS):
                subs = _map(shape, topabs)
                if copying and subs.Extent() != len(copy_ordinals[kind]):
                    copying = False
                    promote()
                for ordinal in range(1, subs.Extent() + 1):
                    sub = subs.FindKey(ordinal)
                    if held is not None and held[kind].Contains(sub):
                        copying = False
                        promote()
                        continue
                    found = source(sub, kind)
                    if found is None:
                        promote()
                        # A nested body's local frame can differ from the
                        # enclosing input's. Its actual Copy can still prove a
                        # whole-body bijection without an enclosing origin.
                        if not copying:
                            continue
                    answers = _asked(query, sub)
                    if copying:
                        target = held[kind].FindIndex(answers[0][0]) if len(answers) == 1 else 0
                        if not target or answers[0][1] != SAME or copy_ordinals[kind][target - 1]:
                            copying = False
                            promote()
                        else:
                            copy_ordinals[kind][target - 1] = ordinal
                    if found is None:
                        continue
                    if compact is not None:
                        # The source was directly resolved, never an earlier
                        # report. A shared target would need _merge, so promote
                        # before processing this already-read answer ordinarily.
                        made = answers[0][0]
                        if (len(found) == 1 and found[0][3:] == (SAME, ())
                                and not reported.Contains(made)):
                            j, _kind, global_ordinal, _how, _place = found[0]
                            row.owners[kind][target - 1] = j
                            # Share the local permutation's int object where
                            # global ordinals coincide, rather than retain two.
                            row.ordinals[kind][target - 1] = ordinal if global_ordinal == ordinal else global_ordinal
                            reported.Add(made)
                            continue
                        promote()
                    answers_from(sub, found, answers)
        if copying and all(all(ordinals) for ordinals in copy_ordinals):
            local = tuple(tuple(kind) for kind in copy_ordinals)
            copied.append((record, Copy(record.inputs[0], local)))
            if row is not None:
                row.local_frozen = local
        elif compact is not None:
            promote()
    history = History()
    history.copies = _copies(inputs, results, copied, all_taken)
    if compact is not None:
        if not reported.Extent():
            return history
        packed = _compact_origins(compact, results, reported)
        if packed is not None:
            history.origins = packed
            return history
        promote()
    if not origins:
        return history
    # Where each reported shape is among the results: in a result, at its ordinal there --
    # and, for a result that is a maker's result at another place (build123d's ``located``
    # places a copy), at the ordinal it has in that maker's result.
    held = [(position, [_map(shape, topabs) for topabs in KINDS])
            for position, result in enumerate(results) if result is not None
            for shape in [result] + [record.result for record in taken
                                     if record.result.IsPartner(result) and not record.result.IsSame(result)]]
    eager: dict = {}
    for index, places in enumerate(_places(shapes, kinds, held)):
        if not places:
            continue
        found = tuple((j, k, o, how, place) for (j, k, o), (how, place) in origins[index].items())
        kind = kinds[index]
        for position, ordinal in places:
            key = (position, kind, ordinal)
            known = eager.get(key)
            eager[key] = found if known is None else _merged(known, found)
    history.origins = eager
    return history


def _copies(inputs: list[Any], results: list[Any], copied: list[tuple[_Record, Copy]],
            records: list[_Record]) -> dict[int, Copy]:
    """Certify only whole Copy results, anchored in a whole input body.

    Element I history also describes partial copies and unchanged pieces of a
    boolean. Neither establishes body identity. The actual copy maker and its
    bijection do; a later maker touching its source or result withdraws that
    certificate. Chains compose their ordinal permutations back to the input.
    """
    if not copied:
        return {}
    tops: dict[Any, Copy | None] = {}
    given = None
    changed = None

    def tshapes(shape: Any) -> set:
        mapped = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, mapped)
        return {mapped.FindKey(at).TShape() for at in range(1, mapped.Extent() + 1)}

    for record, copy in copied:
        if record.result.ShapeType() != copy.source.ShapeType():
            continue
        source = copy.source
        previous = tops.get(source.TShape())
        if previous is not None:
            copy = Copy(previous.source, tuple(tuple(previous.ordinals[kind][at - 1] for at in ordinals)
                                              for kind, ordinals in enumerate(copy.ordinals)))
        else:
            if given is None:
                given = set().union(*(tshapes(shape) for shape in inputs if shape is not None))
            if source.TShape() not in given:
                continue
        if changed is None:
            changed = set().union(*(tshapes(shape) for other in records if other.adapter is not _COPY
                                    for shape in (*other.inputs, other.result) if shape is not None))
        if changed and not changed.isdisjoint(tshapes(source) | tshapes(record.result)):
            continue
        top = record.result.TShape()
        # Two claims to the same native result are ambiguous, even if alike.
        tops[top] = copy if top not in tops else None
    return {position: tops[result.TShape()] for position, result in enumerate(results)
            if result is not None and tops.get(result.TShape()) is not None}


def _places(shapes: list[Any], kinds: list[int], held: list[tuple[int, list[Any]]]) -> list[list[tuple[int, int]]]:
    """For each of ``shapes`` (each of its kind in ``kinds``), each ``(position, ordinal)``
    it has among ``held`` (each a result's position and its maps by kind). Asked shape by
    shape where that is cheaper -- a few shapes, a few results -- else read off one map of
    every element the results hold; the answer is the same either way."""
    count = len(shapes)
    total = sum(maps[kind].Extent() for _position, maps in held for kind in range(len(KINDS)))
    found: list[list[tuple[int, int]]] = [[] for _index in range(count)]
    if count * len(held) <= total:
        for index, (made, kind) in enumerate(zip(shapes, kinds)):
            for position, maps in held:
                ordinal = maps[kind].FindIndex(made)
                if ordinal and (position, ordinal) not in found[index]:
                    found[index].append((position, ordinal))
        return found
    every = [TopTools_IndexedMapOfShape() for _kind in KINDS]
    places: list[list[list[tuple[int, int]]]] = [[] for _kind in KINDS]
    for position, maps in held:
        for kind in range(len(KINDS)):
            elements = maps[kind]
            for ordinal in range(1, elements.Extent() + 1):
                at = every[kind].Add(elements.FindKey(ordinal))
                if at > len(places[kind]):
                    places[kind].append([])
                if (position, ordinal) not in places[kind][at - 1]:
                    places[kind][at - 1].append((position, ordinal))
    for index, (made, kind) in enumerate(zip(shapes, kinds)):
        at = every[kind].FindIndex(made)
        if at:
            found[index] = places[kind][at - 1]
    return found


def _prepared(record: _Record) -> Callable[[Any], list[tuple[Any, str]]] | None:
    try:
        return record.adapter.prepare(record.maker)
    except Exception:  # noqa: BLE001 - a maker that cannot say what it did reports nothing
        _STATS["raised"] += 1
        return None


def _asked(query: Callable[[Any], list[tuple[Any, str]]], sub: Any) -> list[tuple[Any, str]]:
    _STATS["queries"] += 1
    try:
        return query(sub)
    except Exception:  # noqa: BLE001 - counted: a maker asked about a shape it never saw
        _STATS["raised"] += 1
        return []


def _identity() -> tuple:
    from OCP.TopLoc import TopLoc_Location

    value = TopLoc_Location().Transformation().Value
    return tuple(value(row, column) for row in (1, 2, 3) for column in (1, 2, 3, 4))


# The identity placement's transformation, as an edge's signature spells a placement.
_IDENTITY = _identity()


def _wire_copies(record: _Record, source: Callable[[Any, int], tuple | None],
                 report: Callable[[Any, tuple], None]) -> None:
    """``BRepBuilderAPI_MakeWire`` reports nothing, and copies each edge whose vertices it
    merges with a neighbour's: an edge of the wire that is no edge it was given, on the
    same curve object over the same parameters as one it was, is that edge copied."""
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    def signature(edge: Any, alive: list) -> tuple | None:
        location = TopLoc_Location()
        cast = TopoDS.Edge_s(edge)
        curve = BRep_Tool.Curve_s(cast, location, 0.0, 0.0)
        if curve is None:
            return None
        alive.append(curve)  # the wrapper kept alive, so the same curve answers as the same object
        if location.IsIdentity():
            return _object_key(curve), BRep_Tool.Range_s(cast), _IDENTITY
        value = location.Transformation().Value
        return (_object_key(curve), BRep_Tool.Range_s(cast),
                tuple(value(row, column) for row in (1, 2, 3) for column in (1, 2, 3, 4)))

    held = TopTools_IndexedMapOfShape()
    inputs = []
    for shape in record.inputs:
        edges = _map(shape, TopAbs_EDGE)
        for ordinal in range(1, edges.Extent() + 1):
            edge = edges.FindKey(ordinal)
            held.Add(edge)
            inputs.append(edge)
    result = _map(record.result, TopAbs_EDGE)
    copies = [edge for edge in (result.FindKey(ordinal) for ordinal in range(1, result.Extent() + 1))
              if not held.Contains(edge)]
    if not copies:
        return  # every edge of the wire is one it was given: it copied none
    alive: list = []
    given: dict[tuple, Any] = {}
    for edge in inputs:
        key = signature(edge, alive)
        if key is not None:
            given.setdefault(key, edge)
    if not given:
        return
    for edge in copies:
        key = signature(edge, alive)
        original = given.get(key) if key is not None else None
        if original is None:
            continue
        found = source(original, _KIND[TopAbs_EDGE])
        if found is not None:
            report(edge, found)
