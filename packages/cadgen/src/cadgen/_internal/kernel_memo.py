"""The kernel memo: one interception layer at build123d's topology layer, and
what it remembers (README law 18; STORE.md §3, Provenance).

Installed in the warm worker beside ``determinism.install()``
(``generation_runner``), idempotently, the layer patches every kernel
construction build123d's topology modules offer -- primitives, booleans,
fillets and chamfers, sweeps and lofts, faces and wires, copies and moves,
``clean``, ``is_valid``, ``split``, ``project_faces``, the constructors that
build a face from wires, a wire from edges, a shell from faces, a solid from a
shell and a compound from shapes, and the file importers -- so that every
call made from a model's own code inside a run (``run()``) is seen once, at
the boundary. Builder-mode wrappers are not patched: their inner topology
calls are the ones seen. Each call seen is a **feature** for provenance
(``kernel_trace``), whatever the memo does with it.

**Keys.** A call is keyed by its operation, every setting it runs with, its
canonical parameters and the keys of the shapes it was given. The settings are
what the parameters do not say: what a boolean's OCC operation object was set
to before the call (its fuzzy value and glue mode by build123d, the
non-destructive mode by this layer, below), the class-wide ``SkipClean``, and
the font file a text reads, by its bytes as an imported file is (a hit that
ignored one would hand back another operation's geometry).
A shape's key is where it came from: the memo key of the operation that made
its ``TShape`` (the registry, pointer to key) and its position among the
shapes that call returned (a split kept both ways returns two), or, for a
sub-shape, its ancestor's key with its kind and its index in the ancestor's
``TopExp`` map; with the shape's own location and orientation,
the attributes an operation may copy from it (label, colour, material, face
colours, ``for_construction``) and the keys of its children; and with the
effects (below) every operation so far has had on it. The n-th call with one
key in a run is its own entry, so two identical constructions in one run are
two objects, as in plain Python. A shape no operation of this process made --
a child model's materialized result, an imported file, a shape built outside
the patched surface -- has no key, and a call given one runs uncached: a hit
would hand back a result sharing the FIRST run's copy of that shape, not the
one the model holds, and ``is_same`` across that boundary would answer
differently from a run that computed it.

**Hits.** A hit requires the key and, for every shape input, the very
``TShape`` the entry was computed with, and returns the SAME Python objects
the first run made, restored to a snapshot taken when the operation returned:
``label``, ``_color``, ``topo_parent``, ``joints``, anytree parent and
children, every other object field, and ``wrapped``'s TShape, location and
orientation (a later ``move()`` mutates the location in place). Nothing is
reconstructed and nothing is copied: pointer identity holds along every chain
of hits, and every miss makes its downstream miss, since a fresh result is a
new TShape. A constructor cannot return another object, so its hit hands the
first run's ``TopoDS`` to the kernel helper the constructor calls, and the
object the model just made wraps that same TShape.

**Effects.** The kernel modifies its INPUTS: an extrusion clears its profile's
``Free`` flag and appends curve representations to the profile's edges, and
those bytes reach the components a model emits. A boolean does not: the layer
sets every boolean it sees non-destructive (``BOPAlgo_Options``), so the kernel
copies the sub-shapes it would change and shares the rest, a boolean's inputs
are left as they were given, and what it left alone keeps its identity in the
result. What an operation does is captured as each sub-shape's state -- kind,
tolerance, the seven flags, how many representations it holds, an edge's
parametric flags -- read after the operation and compared with the state
before it; the memo keeps the state it last read of every sub-shape of a
memoized shape, written when a capture reads it and when a ledger row sets it,
so an input is walked once per operation, after it. A change is a sparse delta
per sub-shape (the scalars, and the representations appended, by count), noted
in a ledger by sub-shape. A hit replays the delta, so a hot run leaves every
input as a cold run would; a hit of a shape's maker undoes, through the ledger,
every delta applied to any sub-shape of it since it returned, so an operation
edited out of the model leaves no trace. A change no delta expresses -- a
sub-shape added or removed, representations taken away -- is not replayed: the
input's maker forgets its entry, the input is rebuilt by the next run, and the
operation runs on it again, as it always could; a change outside that state (a
representation rewritten in place) is not seen. A call that runs uncached still
captures what it does to a memoized input, and a memoized shape embedded in a
foreign one that the call changed is forgotten the same way.

**Construction keys.** A key is this process's: its shape inputs are interned
ids, and an effect is numbered as it happens. ``construction_key`` restates the
key of whatever made a shape in terms no process owns -- the operation, its
settings and parameters, the output of it the shape is, and the construction
keys of its inputs and of the effects applied to them, each effect named by the
operation that had it and the input it had it on -- and hashes that: the
identity of a component's part (STORE.md §2). It is a function of the
construction alone: nothing the process accumulated enters it -- not the
sub-shapes earlier runs extracted, which a hit leaves registered (only those
some operation of this run changed are named, by kind and index), not a change
of flags alone (a compound taking its children leaves them no longer free,
which changes nothing a part is made of), not the count that tells a run's
identical calls apart (identical constructions are one part, however many
identical calls any part made before them) -- so a warm worker that built other
models, or other versions of this one, gives the key a cold run gives. A shape
whose making passes through a call the memo could not key (an effect it cannot
name, a key it no longer holds) has none, and is named by its bytes.

The memo lives in this process's memory for the life of the process,
LRU-bounded by entries; it never reaches the store and a cold run computes
everything. ``CADGEN_KERNEL_MEMO=0`` turns hits off and nothing else: every
call runs, and is keyed, traced and named as with the memo on, so a component's
identity is the same either way.
"""

from __future__ import annotations

import contextlib
import enum
import functools
import hashlib
import inspect
import itertools
import numbers
import os
import struct
import threading
import weakref
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterator

from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape

from cadgen._internal.kernel_trace import Trace

__all__ = ["CAPACITY", "clear", "construction_key", "enabled", "install", "run", "stats", "uninstall"]

# Entries of live results: a model's intermediate geometry for a few models at
# once, so an edit loop over a large model keeps every unchanged step.
CAPACITY = 32768
_SUB_MAPS = 1024
_KEYS = 8 * CAPACITY

_LOCK = threading.RLock()
_LOCAL = threading.local()
_MEMO: "OrderedDict[tuple[int, int], _Entry]" = OrderedDict()
_REGISTRY: dict[Any, "_Made"] = {}
_LEDGER: dict[Any, list["_Row"]] = {}
_KEY_IDS: "OrderedDict[tuple, int]" = OrderedDict()
_KEY_IDS_NEXT = itertools.count(1)
# The key each interned id stands for, and the construction key it restates as
# (``construction_key``), computed when first asked and forgotten with the id.
_ID_KEYS: dict[int, tuple] = {}
_STABLE: dict[int, bytes] = {}
# The effects by id, while anything holds them: a key names an input's effects by id.
_EFFECTS: "weakref.WeakValueDictionary[int, _Effect]" = weakref.WeakValueDictionary()
_MAPS: "OrderedDict[tuple[int, int], tuple[Any, Any]]" = OrderedDict()
_STATS = {"hits": 0, "misses": 0, "unkeyable": 0, "unreplayable": 0, "errors": 0}
_RUN_IDS = itertools.count(1)
_EFFECT_IDS = itertools.count(1)
# Every row applied takes the next stamp: a maker's reset undoes the rows applied
# after it returned (its ``born`` stamp) by runs before this one.
_SEQUENCE = itertools.count(1)
_installed = False
_EDGE, _VERTEX, _FACE = int(TopAbs_EDGE), int(TopAbs_VERTEX), int(TopAbs_FACE)


class _Unkeyable(Exception):
    """This call cannot be keyed or its result cannot be kept: it runs plain."""


def enabled() -> bool:
    return os.environ.get("CADGEN_KERNEL_MEMO", "1").strip() != "0"


# --- what is patched ----------------------------------------------------------------------
#
# (class, attribute, op label), enumerated from build123d 0.11.1's topology modules.
# A classmethod's label is prefixed with the class it is called on; ``_bool_op``'s
# label is the boolean it runs (cut, fuse, common, section, split); a constructor's
# is its class.

_INSTANCE_TARGETS = (
    ("Shape", "_bool_op", "bool_op"),
    ("Shape", "clean", "clean"),
    ("Shape", "located", "located"),
    ("Shape", "moved", "moved"),
    ("Shape", "mirror", "mirror"),
    ("Shape", "rotate", "rotate"),
    ("Shape", "scale", "scale"),
    ("Shape", "translate", "translate"),
    ("Shape", "transform_shape", "transform_shape"),
    ("Shape", "transform_geometry", "transform_geometry"),
    ("Shape", "transformed", "transformed"),
    ("Shape", "project_faces", "project_faces"),
    ("Shape", "split", "split"),
    ("Shape", "__copy__", "copy"),
    ("Shape", "__deepcopy__", "deepcopy"),
    ("Mixin3D", "chamfer", "chamfer"),
    ("Mixin3D", "fillet", "fillet"),
    ("Mixin3D", "hollow", "hollow"),
    ("Mixin3D", "offset_3d", "offset_3d"),
    ("Mixin3D", "dprism", "dprism"),
    ("Mixin3D", "max_fillet", "max_fillet"),
    ("Solid", "draft", "draft"),
    ("Mixin2D", "offset", "offset"),
    ("Mixin2D", "split_by_perimeter", "split_by_perimeter"),
    ("Face", "chamfer_2d", "chamfer_2d"),
    ("Face", "fillet_2d", "fillet_2d"),
    ("Face", "make_holes", "make_holes"),
    ("Face", "project_to_shape", "project_to_shape"),
    ("Face", "to_arcs", "to_arcs"),
    ("Face", "without_holes", "without_holes"),
    ("Mixin1D", "offset_2d", "offset_2d"),
    ("Mixin1D", "perpendicular_line", "perpendicular_line"),
    ("Mixin1D", "project", "project"),
    ("Wire", "chamfer_2d", "chamfer_2d"),
    ("Wire", "fillet_2d", "fillet_2d"),
    ("Wire", "fix_degenerate_edges", "fix_degenerate_edges"),
    ("Wire", "project_to_shape", "project_to_shape"),
    ("Wire", "stitch", "stitch"),
    ("Wire", "trim", "trim"),
    ("Edge", "trim", "trim"),
    ("Edge", "trim_to_length", "trim_to_length"),
    ("Edge", "project_to_shape", "project_to_shape"),
    ("Edge", "reversed", "reversed"),
    ("Edge", "close", "close"),
)
_PROPERTY_TARGETS = (("Shape", "is_valid", "is_valid"),)
_CLASSMETHOD_TARGETS = tuple(
    (cls, name, name)
    for cls, names in (
        ("Solid", ("extrude", "extrude_linear_with_rotation", "extrude_taper", "extrude_until",
                   "from_bounding_box", "make_box", "make_cone", "make_cylinder", "make_loft",
                   "make_sphere", "make_torus", "make_wedge", "revolve", "sweep", "sweep_multi", "thicken")),
        ("Face", ("extrude", "make_bezier_surface", "make_gordon_surface", "make_plane", "make_rect",
                  "make_surface", "make_surface_from_array_of_points", "make_surface_from_curves",
                  "make_surface_patch", "revolve", "sweep")),
        ("Shell", ("extrude", "make_loft", "revolve", "sweep")),
        ("Wire", ("combine", "extrude", "make_circle", "make_convex_hull", "make_ellipse", "make_polygon", "make_rect")),
        ("Edge", ("extrude", "make_bezier", "make_circle", "make_ellipse", "make_helix", "make_hyperbola",
                  "make_line", "make_mid_way", "make_parabola", "make_spline", "make_bspline",
                  "make_spline_approx", "make_tangent_arc", "make_three_point_arc")),
        ("Compound", ("extrude", "make_text", "make_triad")),
    )
    for name in names
)
# A constructor and the kernel helper it calls for the shape it builds: on a
# hit the helper hands back the first run's TopoDS instead of building one.
# ``Compound`` builds its container on every attachment of children, so its hit
# lets the constructor run and then takes the first run's container.
_CONSTRUCTOR_TARGETS = (("Face", "face"), ("Wire", "wire"), ("Shell", "shell"), ("Solid", "solid"), ("Compound", None))
_HELPER_TARGETS = (
    ("two_d", "_make_topods_face_from_wires", "face"),
    ("two_d", "_sew_topods_faces", "shell"),
)
_HELPER_CLASSMETHODS = (("Wire", "_make_wire", "wire"), ("Solid", "_make_solid", "solid"))
_IMPORTER_TARGETS = ("import_step", "import_brep")
_BOOLEANS = {"BRepAlgoAPI_Cut": "cut", "BRepAlgoAPI_Fuse": "fuse", "BRepAlgoAPI_Common": "common",
             "BRepAlgoAPI_Section": "section", "BRepAlgoAPI_Splitter": "split"}


def install() -> bool:
    """Patch the topology layer, once per process. Returns installed-now. A
    target build123d no longer has is an error: the table is this version's."""
    global _installed
    with _LOCK:
        if _installed:
            return False
        import build123d
        from build123d import importers, topology
        from build123d.topology import two_d

        for cls_name, attr, label in _INSTANCE_TARGETS:
            _patch(getattr(topology, cls_name), attr, label, "instance")
        for cls_name, attr, label in _PROPERTY_TARGETS:
            _patch(getattr(topology, cls_name), attr, label, "property")
        for cls_name, attr, label in _CLASSMETHOD_TARGETS:
            _patch(getattr(topology, cls_name), attr, label, "classmethod")
        for cls_name, _slot in _CONSTRUCTOR_TARGETS:
            _patch(getattr(topology, cls_name), "__init__", cls_name, "constructor")
        for module_name, attr, slot in _HELPER_TARGETS:
            module = {"two_d": two_d}[module_name]
            function = getattr(module, attr)
            if not getattr(function, "__kernel_memo__", False):
                setattr(module, attr, _helper(slot, function))
        for cls_name, attr, slot in _HELPER_CLASSMETHODS:
            cls = getattr(topology, cls_name)
            static = inspect.getattr_static(cls, attr)
            if not getattr(static.__func__, "__kernel_memo__", False):
                setattr(cls, attr, classmethod(_helper(slot, static.__func__)))
        for name in _IMPORTER_TARGETS:
            original = getattr(importers, name)
            if getattr(original, "__kernel_memo__", False):
                continue
            wrapped = _wrap(name, original, "function")
            setattr(importers, name, wrapped)
            if getattr(build123d, name, None) is original:
                setattr(build123d, name, wrapped)
        _installed = True
        return True


def uninstall() -> bool:
    """Restore every attribute ``install`` replaced. Returns uninstalled-now;
    the memo's entries stay (``clear`` drops them)."""
    global _installed
    with _LOCK:
        if not _installed:
            return False
        import build123d
        from build123d import importers, topology
        from build123d.topology import two_d

        targets = (_INSTANCE_TARGETS + _PROPERTY_TARGETS + _CLASSMETHOD_TARGETS
                   + tuple((cls_name, "__init__", cls_name) for cls_name, _slot in _CONSTRUCTOR_TARGETS)
                   + tuple((cls_name, attr, slot) for cls_name, attr, slot in _HELPER_CLASSMETHODS))
        for cls_name, attr, _label in targets:
            cls = getattr(topology, cls_name)
            static = inspect.getattr_static(cls, attr)
            if isinstance(static, classmethod):
                if getattr(static.__func__, "__kernel_memo__", False):
                    setattr(cls, attr, classmethod(static.__func__.__wrapped__))
            elif isinstance(static, property):
                if getattr(static.fget, "__kernel_memo__", False):
                    setattr(cls, attr, property(static.fget.__wrapped__, static.fset, static.fdel))
            elif getattr(static, "__kernel_memo__", False):
                setattr(cls, attr, static.__wrapped__)
        for module_name, attr, _slot in _HELPER_TARGETS:
            module = {"two_d": two_d}[module_name]
            function = getattr(module, attr)
            if getattr(function, "__kernel_memo__", False):
                setattr(module, attr, function.__wrapped__)
        for name in _IMPORTER_TARGETS:
            wrapped = getattr(importers, name)
            if getattr(wrapped, "__kernel_memo__", False):
                setattr(importers, name, wrapped.__wrapped__)
                if getattr(build123d, name, None) is wrapped:
                    setattr(build123d, name, wrapped.__wrapped__)
        _installed = False
        return True


def _patch(cls: type, attr: str, label: str, kind: str) -> None:
    static = inspect.getattr_static(cls, attr)
    if kind == "classmethod":
        if not isinstance(static, classmethod):
            raise TypeError(f"{cls.__name__}.{attr} is not a classmethod")
        function = static.__func__
        if not getattr(function, "__kernel_memo__", False):
            setattr(cls, attr, classmethod(_wrap(label, function, kind)))
    elif kind == "property":
        if not isinstance(static, property):
            raise TypeError(f"{cls.__name__}.{attr} is not a property")
        if not getattr(static.fget, "__kernel_memo__", False):
            setattr(cls, attr, property(_wrap(label, static.fget, kind), static.fset, static.fdel))
    else:
        if not inspect.isfunction(static):
            raise TypeError(f"{cls.__name__}.{attr} is not a plain method")
        if not getattr(static, "__kernel_memo__", False):
            setattr(cls, attr, _wrap(label, static, kind))


def _wrap(label: str, function: Any, kind: str) -> Any:
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if label == "bool_op":
            _non_destructive(args, kwargs)
        state = getattr(_LOCAL, "run", None)
        if state is None or state.depth:
            return function(*args, **kwargs)
        return _call(state, label, kind, function, args, kwargs)

    wrapper.__kernel_memo__ = True
    return wrapper


def _non_destructive(args: tuple, kwargs: dict) -> None:
    """Every boolean the layer sees runs non-destructive (``BOPAlgo_Options``):
    the kernel copies the sub-shapes it would change and shares the rest, so a
    boolean leaves its inputs as they were given, and what it leaves alone keeps
    its identity in the result (``kernel_trace``). Set before the call is keyed,
    so its key says what ran."""
    operation = args[3] if len(args) > 3 else kwargs.get("operation")
    if operation is not None:
        operation.SetNonDestructive(True)


def _helper(slot: str, function: Any) -> Any:
    """A constructor's kernel helper: hands back the TopoDS a constructor hit
    adopted, once, and otherwise builds as it always did."""
    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        adopt = getattr(_LOCAL, "adopt", None)
        if adopt is not None and adopt[0] == slot:
            _LOCAL.adopt = None
            return adopt[1]
        return function(*args, **kwargs)

    wrapper.__kernel_memo__ = True
    return wrapper


# --- the run ------------------------------------------------------------------------------


class _Run:
    """One model run: its trace, its per-key call counts, the results that are
    not memoizable (registered for the run only) and the nesting depth."""

    def __init__(self, script_path: Path | None) -> None:
        self.id = next(_RUN_IDS)
        self.trace = Trace(Path(script_path).resolve().parent if script_path is not None else None)
        self.counts: dict[int, int] = {}
        self.depth = 0
        self.transient: dict[Any, _Made] = {}

    def count(self, key_id: int) -> int:
        n = self.counts.get(key_id, 0) + 1
        self.counts[key_id] = n
        return n

    def made_by(self, tshape: Any) -> int | None:
        """The feature of this run that made ``tshape``, or None."""
        made = _made_of(tshape, self)
        if made is None:
            return None
        root = made.root()
        return root.feature if root.run == self.id else None

    def feature_of(self, shape: Any) -> int | None:
        """The feature that made ``shape``: the one that returned the object, else
        the maker of its TShape, else that of the shape it was extracted from."""
        index = self.trace.feature_of(shape)
        if index is not None:
            return index
        wrapped = _wrapped(shape)
        if wrapped is not None:
            index = self.made_by(wrapped.TShape())
            if index is not None:
                return index
        parent = shape.__dict__.get("topo_parent") if hasattr(shape, "__dict__") else None
        return self.feature_of(parent) if parent is not None and parent is not shape else None

    def account(self, shape: Any) -> tuple[str | None, dict[str, Any] | None, dict[str, int]]:
        """What names one component this run made: its construction key
        (:func:`construction_key`) and its lineage (``kernel_trace.Trace.account``),
        either None when the run cannot say, and the feature of the run, by index, each
        feature name of the lineage stands for -- the body's own, so two bodies named
        alike (made by constructions the memo cannot key) never answer for each other."""
        from OCP.TopLoc import TopLoc_Location

        wrapped = _wrapped(shape)
        if wrapped is None:
            return None, None, {}
        key = construction_key(shape)
        lineage, names = self.trace.account(wrapped.Located(TopLoc_Location()), self.made_by)
        return key, lineage, names

    def identify(self, shape: Any) -> tuple[str | None, dict[str, Any] | None]:
        """:meth:`account`'s construction key and lineage: what names a component."""
        key, lineage, _names = self.account(shape)
        return key, lineage

    def placed_by(self, shape: Any) -> int | None:
        """The feature whose call made the shape a leaf places -- the one that first
        returned the object, else the maker of its geometry -- through the features that
        only place or hold another's (``Trace.unwrapped``): for a part one construction
        made twice (one part, the second call the memo's hit), the call that made this
        occurrence of it. None where no feature of the run made it."""
        index = self.trace.made(shape)
        if index is None:
            wrapped = _wrapped(shape)
            index = self.made_by(wrapped.TShape()) if wrapped is not None else None
        return None if index is None else self.trace.unwrapped(index)


@contextlib.contextmanager
def run(script_path: Path | None = None) -> Iterator[_Run]:
    """A model run on this thread: inside it every patched call from the
    model's code is a feature, and a hit when the memo has one. ``script_path``
    is the model's script, whose folder feature paths are relative to."""
    install()
    state = _Run(script_path)
    previous = getattr(_LOCAL, "run", None)
    _LOCAL.run = state
    try:
        yield state
    finally:
        _LOCAL.run = previous


def stats() -> dict[str, int]:
    with _LOCK:
        return dict(_STATS, entries=len(_MEMO), registry=len(_REGISTRY))


def clear() -> None:
    """Forget every entry, so the next run computes everything."""
    with _LOCK:
        _MEMO.clear()
        _REGISTRY.clear()
        _LEDGER.clear()
        _KEY_IDS.clear()
        _ID_KEYS.clear()
        _STABLE.clear()
        _MAPS.clear()
        _STATE.clear()


# --- the call -----------------------------------------------------------------------------


def _call(state: _Run, label: str, kind: str, function: Any, args: tuple, kwargs: dict) -> Any:
    if kind == "constructor" and not _constructs(label, args, kwargs):
        return function(*args, **kwargs)
    frame = state.trace.frame()
    if frame is None:
        return function(*args, **kwargs)
    state.depth += 1
    try:
        op = _op_name(label, kind, args, kwargs)
        shapes = _shape_args(_key_args(label, kind, args), kwargs)
        # The memo is an optimization and never the reason a build fails: a key,
        # a capture or a snapshot that cannot be taken makes the call run plain,
        # counted under errors, and the call is still a feature. With the memo
        # off a call is keyed as ever and never hits: identity is the same either way.
        key_id = None
        try:
            key_id = _intern(_build_key(label, kind, function, args, kwargs, state))
        except _Unkeyable:
            _STATS["unkeyable"] += 1
        except Exception:  # noqa: BLE001
            _STATS["errors"] += 1
        if key_id is None:
            return _plain(state, op, frame, kind, shapes, function, args, kwargs, capture=True)
        inputs = state.trace.given(shapes, state.feature_of)
        n = state.count(key_id)
        entry = None
        if enabled():
            with _LOCK:
                entry = _MEMO.get((key_id, n))
                if entry is not None and entry.matches(shapes):
                    _MEMO.move_to_end((key_id, n))
                else:
                    entry = None
        if entry is not None:
            result = _hit(state, entry, kind, function, args, kwargs, shapes)
            feature = state.trace.record(op, frame, inputs, _result_shapes(result), _returned_shapes(result))
            entry.refresh(feature.index, state.id)
            _STATS["hits"] += 1
            return None if kind == "constructor" else result
        try:
            captured = _capture(shapes)
        except Exception:  # noqa: BLE001
            _STATS["errors"] += 1
            return _plain(state, op, frame, kind, shapes, function, args, kwargs, capture=False)
        # The inputs as given, before the call: an in-place operation (clean)
        # leaves its input wrapping the result's TShape.
        given = [_wrapped(shape).TShape() for shape in shapes]
        function_result = function(*args, **kwargs)
        result = args[0] if kind == "constructor" else function_result
        _STATS["misses"] += 1
        feature = state.trace.record(op, frame, inputs, _result_shapes(result), _returned_shapes(result))
        snapshot = None
        try:
            effects, sound = _effects(captured, state)
            if sound:
                if kind == "constructor":
                    snapshot = _Adopt(_wrapped(result), dict(_CONSTRUCTOR_TARGETS)[label])
                else:
                    snapshot = _snapshot(result)
        except _Unkeyable:
            snapshot = None
        except Exception:  # noqa: BLE001
            _STATS["errors"] += 1
            snapshot = None
            for item in captured:
                _taint(_made_of(item.handle.TShape(), state), state)
        if snapshot is None:
            _register(result, None, feature.index, state, None)
            return function_result
        for index, effect in effects:
            effect.origin = (key_id, n, index)
        entry = _Entry(key=(key_id, n), inputs=given, snapshot=snapshot, effects=effects,
                       in_place=kind != "constructor" and bool(args) and result is args[0])
        with _LOCK:
            replaced = _MEMO.pop(entry.key, None)
            if replaced is not None:
                _drop(replaced)  # the key's earlier entry, made from inputs this run no longer has
        entry.made = _register(result, entry.key, feature.index, state, entry)
        with _LOCK:
            _MEMO[entry.key] = entry
            _MEMO.move_to_end(entry.key)
            while len(_MEMO) > CAPACITY:
                _old_key, old = _MEMO.popitem(last=False)
                _drop(old)
        return function_result
    finally:
        state.depth -= 1


def _plain(state: _Run, op: str, frame: tuple, kind: str, shapes: list, function: Any, args: tuple,
           kwargs: dict, *, capture: bool) -> Any:
    """Run the call as plain build123d. It is still a feature, its results are
    this run's (so a later feature can name them as inputs), and what it does
    to a memoized shape is still accounted for."""
    inputs = state.trace.given(shapes, state.feature_of)
    try:
        captured = _capture(shapes, embedded=True) if capture else []
    except Exception:  # noqa: BLE001
        _STATS["errors"] += 1
        captured = []
    function_result = function(*args, **kwargs)
    result = args[0] if kind == "constructor" else function_result
    feature = state.trace.record(op, frame, inputs, _result_shapes(result), _returned_shapes(result))
    if captured:
        try:
            _effects(captured, state)
        except Exception:  # noqa: BLE001
            _STATS["errors"] += 1
    _register(result, None, feature.index, state, None)
    return function_result


def _hit(state: _Run, entry: "_Entry", kind: str, function: Any, args: tuple, kwargs: dict, shapes: list) -> Any:
    if kind == "constructor":
        from build123d.topology.shape_core import downcast

        adopted = entry.snapshot.restore()
        _LOCAL.adopt = (entry.snapshot.slot, adopted)
        try:
            function(*args, **kwargs)
        finally:
            _LOCAL.adopt = None
        result = args[0]
        result.__dict__["_wrapped"] = downcast(adopted.Located(adopted.Location()))
    elif entry.in_place and shapes[0] is not entry.snapshot.obj:
        from build123d.topology.shape_core import downcast

        result = shapes[0]
        wrapped = entry.snapshot.wrapped
        result.__dict__["_wrapped"] = downcast(wrapped.Located(wrapped.Location()))
    else:
        result = entry.snapshot.restore()
    for made in entry.made:
        made.reset(state.id)
    for index, effect in entry.effects:
        effect.apply(state.id)
        made = _made_of(_wrapped(shapes[index]).TShape(), state)
        if made is not None:
            made.effects.append(effect)
    for made in entry.made:
        made.born = next(_SEQUENCE)
    return result


def _constructs(label: str, args: tuple, kwargs: dict) -> bool:
    """Whether a constructor call builds a shape, rather than wrapping a
    ``TopoDS`` the kernel already holds or making an empty one."""
    from OCP.TopoDS import TopoDS_Shape

    given = [value for value in args[1:]] + [value for name, value in kwargs.items()
                                              if name in ("obj", "outer_wire", "edges", "edge", "wire", "curve", "children")]
    if not given:
        return False
    first = given[0]
    if first is None or isinstance(first, TopoDS_Shape):
        return label == "Compound" and bool(kwargs.get("children"))
    return True


def _op_name(label: str, kind: str, args: tuple, kwargs: dict) -> str:
    if label == "bool_op":
        operation = args[3] if len(args) > 3 else kwargs.get("operation")
        name = type(operation).__name__
        return _BOOLEANS.get(name, name.removeprefix("BRepAlgoAPI_").lower())
    if kind == "classmethod":
        return f"{args[0].__name__}.{label}"
    return label


def _key_args(label: str, kind: str, args: tuple) -> tuple:
    if label == "deepcopy":
        return args[:1]  # the memo dict is not a parameter
    return args[1:] if kind in ("classmethod", "constructor") else args


def _wrapped(shape: Any) -> Any:
    """The shape's ``TopoDS_Shape`` from its own state, or None for an empty shape."""
    state = getattr(shape, "__dict__", None)
    return None if state is None else state.get("_wrapped")


# --- keys -----------------------------------------------------------------------------------


def _intern(key: tuple) -> int:
    """A small id for a key tuple, so nested keys stay small. Ids are never
    reused: an entry whose key id left the table can only miss, never collide."""
    with _LOCK:
        found = _KEY_IDS.get(key)
        if found is None:
            found = _KEY_IDS[key] = next(_KEY_IDS_NEXT)
            _ID_KEYS[found] = key
            while len(_KEY_IDS) > _KEYS:
                _old, old_id = _KEY_IDS.popitem(last=False)
                _ID_KEYS.pop(old_id, None)
                _STABLE.pop(old_id, None)
        else:
            _KEY_IDS.move_to_end(key)
        return found


def _build_key(label: str, kind: str, function: Any, args: tuple, kwargs: dict, state: _Run) -> tuple:
    if label in _IMPORTER_TARGETS:
        source = args[0] if args else kwargs.get("file_name", kwargs.get("filename"))
        rest = args[1:]
        kw = {name: value for name, value in kwargs.items() if name not in ("file_name", "filename")}
        parts: tuple = (_file_key(source), *(_normalize(value, state) for value in rest))
    elif label == "make_text":
        # A text reads a font file: its bytes are the parameter, wherever the file is.
        bound = inspect.signature(function).bind(*args, **kwargs)
        bound.apply_defaults()
        arguments = dict(bound.arguments)
        arguments.pop("cls", None)
        font = _font_key(arguments.get("font"), arguments.pop("font_path", None), arguments.get("font_style"))
        parts = (("cls", args[0].__module__, args[0].__qualname__), font)
        kw = arguments
    else:
        parts = tuple(_normalize(value, state) for value in _key_args(label, kind, args))
        if kind == "classmethod":
            parts = (("cls", args[0].__module__, args[0].__qualname__), *parts)
        elif kind == "constructor":
            parts = (("cls", type(args[0]).__module__, type(args[0]).__qualname__), *parts)
        kw = kwargs
    keywords = tuple(sorted((name, _normalize(value, state)) for name, value in kw.items()))
    return (label, parts, keywords, _settings())


def _settings() -> tuple:
    """What every operation runs under besides its arguments: build123d's
    class-wide ``SkipClean``, which a boolean and a sweep read to decide whether
    to unify what they made."""
    from build123d.topology.shape_core import SkipClean

    return ("clean", bool(SkipClean.clean))


def _font_key(font: Any, font_path: Any, style: Any) -> tuple:
    """The font file a text construction reads, by its bytes: resolved as
    ``Compound.make_text`` resolves it -- a font file build123d can read is
    registered over the face it names, else the system font of that name and
    style is found -- and, like the call, leaving that registration behind."""
    from build123d.text import FONT_ASPECT, FontManager

    manager = FontManager()
    path = os.fspath(font_path) if font_path is not None else None
    if path and manager.check_font(path):
        faces = manager.register_font(path, True, False)
        font = font if font in faces else faces[0]
    try:
        found = manager.find_font(str(font), style)
        located = found.FontPath(FONT_ASPECT[style]).ToCString() if found is not None else ""
    except Exception as exc:  # noqa: BLE001 - a font the kernel cannot resolve is no key
        raise _Unkeyable(f"a font that cannot be resolved: {exc}") from exc
    if not located:
        raise _Unkeyable("a font with no file")
    return ("font", str(found.FontName().ToCString()), _file_key(located))


def _file_key(source: Any) -> tuple:
    """An imported file is its bytes."""
    if isinstance(source, (bytes, bytearray)):
        return ("bytes", hashlib.sha256(bytes(source)).hexdigest())
    try:
        return ("file", hashlib.sha256(Path(os.fspath(source)).read_bytes()).hexdigest())
    except (TypeError, OSError) as exc:
        raise _Unkeyable(str(exc)) from exc


def _normalize(value: Any, state: _Run) -> Any:
    """One parameter as a hashable, deterministic key part."""
    if value is None or isinstance(value, (bool, str, bytes)):
        return value
    if isinstance(value, numbers.Real):
        # By value, as Python compares them: a radius of 3 and one of 3.0 are
        # one parameter, and the kernel takes a double either way.
        return ("n", struct.pack("<d", float(value)))
    if isinstance(value, enum.Enum):
        return ("enum", type(value).__name__, value.name)
    if isinstance(value, Path):
        return ("path", str(value))
    if isinstance(value, (list, tuple)):
        return ("seq", tuple(_normalize(item, state) for item in value))
    if isinstance(value, dict):
        return ("map", tuple(sorted((str(key), _normalize(item, state)) for key, item in value.items())))
    from build123d.topology import Shape

    if isinstance(value, Shape):
        return ("shape", _shape_key(value, state))
    type_name = type(value).__name__
    if type_name.startswith("BRepAlgoAPI"):
        return ("occ_op", type_name, _operation_settings(value))
    module = type(value).__module__ or ""
    if module.startswith("build123d"):
        if type_name == "Axis":
            return ("Axis", _normalize(tuple(value.position), state), _normalize(tuple(value.direction), state))
        if type_name == "Plane":
            return ("Plane", _normalize(tuple(value.origin), state), _normalize(tuple(value.x_dir), state),
                    _normalize(tuple(value.z_dir), state))
        if type_name == "Matrix":
            transform = value.wrapped
            return ("Matrix", tuple(("n", struct.pack("<d", transform.Value(row, column)))
                                    for row in (1, 2, 3) for column in (1, 2, 3, 4)))
        if type_name == "BoundBox":
            return ("BoundBox", _normalize(tuple(value.min), state), _normalize(tuple(value.max), state))
        # Vector, Location, Rotation, Color: their components, in order.
        if hasattr(value, "__iter__"):
            return (type_name, _normalize(tuple(value), state))
    raise _Unkeyable(f"unkeyable argument type: {module}.{type_name}")


def _operation_settings(operation: Any) -> tuple:
    """Every setting an OCC boolean or splitter reports, as its caller left it before
    the call (build123d sets the fuzzy value and the glue mode of a fuse): a hit that
    ignored one would hand back another operation's result. Arguments and tools are
    not settings: ``_bool_op`` sets them from the shapes the key already names."""
    found = []
    for name in ("Operation", "FuzzyValue", "Glue", "NonDestructive", "CheckInverted"):
        getter = getattr(operation, name, None)
        if getter is None:
            continue
        value = getter()
        if isinstance(value, bool):
            found.append((name, value))
        elif isinstance(value, numbers.Real):
            found.append((name, struct.pack("<d", float(value))))
        else:
            found.append((name, type(value).__name__, int(value)))
    return tuple(found)


def _shape_args(args: tuple, kwargs: dict) -> list:
    """The shapes a call was given, in call order, lists and tuples opened."""
    from build123d.topology import Shape

    found: list = []

    def walk(value: Any) -> None:
        if isinstance(value, Shape):
            found.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for value in args:
        walk(value)
    for _name, value in sorted(kwargs.items()):
        walk(value)
    return found


def _location_key(wrapped: Any) -> bytes:
    transform = wrapped.Location().Transformation()
    return b"".join(struct.pack("<d", transform.Value(row, column)) for row in (1, 2, 3) for column in (1, 2, 3, 4))


def _shape_key(shape: Any, state: _Run) -> int:
    """The interned key of a shape input: its placed geometry, its attributes,
    its children."""
    placed = _placed_key(shape, state)
    state_dict = shape.__dict__
    if state_dict.get("joints"):
        raise _Unkeyable("a shape with joints")
    if "_occurrence_tree" in state_dict:
        raise _Unkeyable("a shape carrying a spliced occurrence tree")
    label = state_dict.get("label")
    if not isinstance(label, str):
        raise _Unkeyable("a label that is not a string")
    color = state_dict.get("_color")
    color_key = None if color is None else _normalize(tuple(color), state)
    material = state_dict.get("_cadgen_material")
    face_colors = state_dict.get("cad_face_ordinal_colors") or {}
    attrs = (
        "attrs", label, color_key, bool(state_dict.get("for_construction")), state_dict.get("material"),
        _normalize(material, state) if material is not None else None,
        state_dict.get("_cadgen_material_id"),
        tuple(sorted((int(ordinal), _normalize(tuple(rgba), state)) for ordinal, rgba in face_colors.items())),
    )
    children = tuple(_shape_key(child, state) for child in state_dict.get("_NodeMixin__children") or ())
    return _intern((placed, attrs, children))


def _placed_key(shape: Any, state: _Run) -> tuple:
    """Where a shape's geometry came from, with its location and orientation."""
    wrapped = _wrapped(shape)
    if wrapped is None:
        raise _Unkeyable("an empty shape")
    tshape = wrapped.TShape()
    made = _made_of(tshape, state)
    if made is None:
        made = _register_sub(shape, wrapped, tshape, state)
    return ("shape", made.base(shape, state), _location_key(wrapped), int(wrapped.Orientation()))


def _made_of(tshape: Any, state: _Run | None) -> "_Made | None":
    found = _REGISTRY.get(tshape)
    if found is None and state is not None:
        found = state.transient.get(tshape)
    return found


def _register_sub(shape: Any, wrapped: Any, tshape: Any, state: _Run) -> "_Made":
    """Key a sub-shape by its ancestor: ``topo_parent``, the shape it was
    extracted from, and its index in that shape's map of its kind."""
    from build123d.topology import Shape

    parent = shape.__dict__.get("topo_parent")
    if not isinstance(parent, Shape) or parent is shape:
        raise _Unkeyable("a shape no operation of this process made")
    parent_wrapped = _wrapped(parent)
    if parent_wrapped is None:
        raise _Unkeyable("a sub-shape of an empty shape")
    parent_made = _made_of(parent_wrapped.TShape(), state)
    if parent_made is None:
        parent_made = _register_sub(parent, parent_wrapped, parent_wrapped.TShape(), state)
    kind = int(wrapped.ShapeType())
    index = _sub_map(parent_wrapped, kind).FindIndex(wrapped)
    if index == 0:
        raise _Unkeyable("not a sub-shape of its topo_parent")
    made = _Made(tshape, key=None, feature=None, run=state.id, entry=None, parent=parent_made, kind=kind, index=index)
    parent_made.subs.append(made)
    with _LOCK:
        if parent_made.persistent():
            _REGISTRY[tshape] = made
        else:
            state.transient[tshape] = made
    return made


def _sub_map(parent_wrapped: Any, kind: int) -> Any:
    """``TopExp.MapShapes`` of a located shape for one kind, kept for the shapes
    a model keeps extracting from."""
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    key = (hash(parent_wrapped), kind)
    with _LOCK:
        found = _MAPS.get(key)
        if found is not None and found[0].IsSame(parent_wrapped):
            _MAPS.move_to_end(key)
            return found[1]
    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(parent_wrapped, TopAbs_ShapeEnum(kind), mapped)
    with _LOCK:
        _MAPS[key] = (parent_wrapped.Located(parent_wrapped.Location()), mapped)
        while len(_MAPS) > _SUB_MAPS:
            _MAPS.popitem(last=False)
    return mapped


# --- construction keys ----------------------------------------------------------------------


class _Unstable(Exception):
    """No construction key: the making passes through something no key names."""


def construction_key(shape: Any) -> str | None:
    """The construction key of ``shape``: sha256 hex of the key of the memoized
    call that made its ``TShape`` (or of the sub-shape relation that names it),
    with every shape input and every effect restated as a construction key of
    its own, the effects applied to the shape and its sub-shapes since, its
    orientation, and the cadgen release that built it (the kernel's versions
    are the part's producer). None when no memoized call of this process made it."""
    import cadgen

    wrapped = _wrapped(shape)
    if wrapped is None:
        return None
    with _LOCK:
        made = _REGISTRY.get(wrapped.TShape())
        if made is None:
            return None
        try:
            material = ("component", getattr(cadgen, "__version__", ""), _made_material(made),
                        int(wrapped.Orientation()))
        except _Unstable:
            return None
    return hashlib.sha256(repr(material).encode()).hexdigest()


def _made_material(made: "_Made") -> tuple:
    if made.parent is None:
        if made.key is None:
            raise _Unstable("a shape no memoized operation made")
        # The count of identical calls before this one is the memo's, never the key's.
        head: tuple = ("made", _stable_id(made.key[0]), made.position)
    else:
        head = ("sub", _made_material(made.parent), made.kind, made.index)
    return (*head, _effects_material(made))


_NO_EFFECTS: tuple = ((), ())


def _effects_material(made: "_Made") -> tuple:
    """The effects applied to a shape, and to each of its sub-shapes that had any, by
    kind and index: a sub-shape the memo knows only because a run extracted it (this
    one or an earlier one, whose registration a hit keeps) adds nothing."""
    subs = []
    for sub in made.subs:
        material = _effects_material(sub)
        if material != _NO_EFFECTS:
            subs.append((sub.kind, sub.index, material))
    return _effects_named(made.effects), tuple(sorted(subs, key=lambda sub: (sub[0], sub[1])))


def _effects_named(effects: Any) -> tuple:
    """The effects a construction key names. A change of flags alone -- a ``Compound``
    taking its children leaves them no longer free -- changes nothing a part is made
    of, whichever call had it, and is left out."""
    named = []
    for effect in effects:
        if effect is not None and not effect.geometric():
            continue
        named.append(_effect_material(effect))
    return tuple(named)


def _effect_material(effect: "_Effect | None") -> tuple:
    if effect is None or effect.origin is None:
        raise _Unstable("an effect no memoized call had")
    key_id, _n, index = effect.origin
    return ("effect", _stable_id(key_id), index)


def _stable_id(root: int) -> bytes:
    """The digest of an interned key restated without process-local ids: an
    operation's (its label, parameters and keyword parameters, a shape among them
    by its own) or a shape's (where it came from, its attributes, its children).
    Every id a key holds was interned before it, so the walk is a DAG; it runs
    on a stack, as a model's chain of operations can be long."""
    stack = [root]
    while stack:
        key_id = stack[-1]
        if key_id in _STABLE:
            stack.pop()
            continue
        key = _ID_KEYS.get(key_id)
        if key is None:
            raise _Unstable("a key the memo no longer holds")
        missing = [dependency for dependency in _dependencies(key) if dependency not in _STABLE]
        if missing:
            stack.extend(missing)
            continue
        if type(key[0]) is str:
            label, parts, keywords, settings = key
            material: tuple = ("op", label, _stable_value(parts), _stable_value(keywords), settings)
        else:
            placed, attrs, children = key
            material = ("shape", _stable_placed(placed), attrs, tuple(_STABLE[child] for child in children))
        _STABLE[key_id] = hashlib.sha256(repr(material).encode()).digest()
        stack.pop()
    return _STABLE[root]


def _dependencies(key: tuple) -> list[int]:
    """The interned ids a key holds: shape inputs, the call a shape came from,
    the calls that had the effects applied to it, its children."""
    found: list[int] = []

    def value(item: Any) -> None:
        if type(item) is tuple:
            if len(item) == 2 and item[0] == "shape" and type(item[1]) is int:
                found.append(item[1])
            else:
                for member in item:
                    value(member)

    def placed(item: tuple) -> None:
        base = item[1]
        if base[0] == "made":
            found.append(base[1])
        else:
            placed(base[1])
        for effect_id in base[-1]:
            effect = _EFFECTS.get(effect_id)
            if effect is not None and not effect.geometric():
                continue  # a change of flags alone: left out of the key (_effects_named)
            if effect is None or effect.origin is None:
                raise _Unstable("an effect no memoized call had")
            found.append(effect.origin[0])

    if type(key[0]) is str:
        value(key[1])
        value(key[2])
    else:
        placed(key[0])
        found.extend(key[2])
    return found


def _stable_value(item: Any) -> Any:
    if type(item) is tuple:
        if len(item) == 2 and item[0] == "shape" and type(item[1]) is int:
            return ("shape", _STABLE[item[1]])
        return tuple(_stable_value(member) for member in item)
    return item


def _stable_placed(placed: tuple) -> tuple:
    _tag, base, location, orientation = placed
    if base[0] == "made":
        _made, key_id, _n, position, applied = base
        head: tuple = ("made", _STABLE[key_id], position)
    else:
        _sub, parent, kind, index, applied = base
        head = ("sub", _stable_placed(parent), kind, index)
    return (*head, _effects_named(_EFFECTS.get(effect_id) for effect_id in applied), location, orientation)


# --- the registry ---------------------------------------------------------------------------


class _Made:
    """What the memo knows about one ``TShape``: the entry that made it and the
    position of the shape among that call's results (or the sub-shape relation
    that names it), the feature of the current run that made it, the effects
    operations have had on it since, and the sub-shapes of it that have entries
    of their own."""

    __slots__ = ("tshape", "key", "position", "feature", "run", "entry", "parent", "kind", "index", "effects",
                 "subs", "born")

    def __init__(self, tshape: Any, *, key: tuple[int, int] | None, feature: int | None, run: int,
                 entry: "_Entry | None", parent: "_Made | None" = None, kind: int | None = None,
                 index: int | None = None, position: int = 0) -> None:
        self.tshape = tshape
        self.key = key
        self.position = position
        self.feature = feature
        self.run = run
        self.entry = entry
        self.parent = parent
        self.kind = kind
        self.index = index
        self.effects: list[_Effect] = []
        self.subs: list[_Made] = []
        self.born = next(_SEQUENCE)

    def root(self) -> "_Made":
        made = self
        while made.parent is not None:
            made = made.parent
        return made

    def persistent(self) -> bool:
        return self.root().key is not None

    def base(self, shape: Any, state: _Run) -> tuple:
        """The key of this TShape as an input: the entry that made it, or the
        sub-shape relation, and the effects applied to it so far."""
        applied = tuple(effect.id for effect in self.effects)
        if self.parent is None:
            if self.key is None:
                raise _Unkeyable("a shape no memoized operation made")
            return ("made", self.key[0], self.key[1], self.position, applied)
        parent = shape.__dict__.get("topo_parent")
        if parent is None:
            raise _Unkeyable("a sub-shape that lost its topo_parent")
        return ("sub", _placed_key(parent, state), self.kind, self.index, applied)

    def handle(self) -> Any:
        return _handle_of(self.tshape)

    def reset(self, run_id: int) -> None:
        """Back to the state the operation returned: every row noted in the
        ledger on any sub-shape of this TShape by an earlier run, after this
        TShape was made, undone, latest first. Rows this run applied are its
        own operations' and stay."""
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        mapped = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(self.handle(), mapped)
        for ordinal in range(1, mapped.Extent() + 1):
            tshape = mapped.FindKey(ordinal).TShape()
            rows = _LEDGER.get(tshape)
            if not rows:
                continue
            kept = [row for row in rows if row.run == run_id or row.seq <= self.born]
            for row in reversed(rows):
                if row.run != run_id and row.seq > self.born:
                    row.set(row.before)
            if kept:
                _LEDGER[tshape] = kept
            else:
                del _LEDGER[tshape]
        pending: list[_Made] = [self]
        while pending:
            made = pending.pop()
            made.effects.clear()
            made.run = run_id
            pending.extend(made.subs)


def _handle_of(tshape: Any) -> Any:
    from OCP.TopoDS import TopoDS_Shape

    shape = TopoDS_Shape()
    shape.TShape(tshape)
    return shape


def _register(result: Any, key: tuple[int, int] | None, feature: int, state: _Run, entry: "_Entry | None") -> list[_Made]:
    """Register every shape of a result under the entry that made it, each at its
    position among the result's shapes. A TShape already registered (a move
    shares its input's) keeps its first maker."""
    created: list[_Made] = []
    for position, shape in enumerate(_result_shapes(result)):
        wrapped = _wrapped(shape)
        if wrapped is None:
            continue
        tshape = wrapped.TShape()
        if _made_of(tshape, state) is not None:
            continue
        made = _Made(tshape, key=key, feature=feature, run=state.id, entry=entry, position=position)
        with _LOCK:
            if key is None:
                state.transient[tshape] = made
            else:
                _REGISTRY[tshape] = made
                created.append(made)
    return created


def _drop(entry: "_Entry") -> None:
    """Forget an entry's registrations and the ledger rows its effects, and the
    effects on its results, hold (the entry itself is already out of the memo)."""
    for _index, effect in entry.effects:
        effect.forget()
    pending = list(entry.made)
    while pending:
        made = pending.pop()
        _REGISTRY.pop(made.tshape, None)
        for effect in made.effects:
            effect.forget()
        if made.parent is None:
            _forget_states(made.tshape)
        pending.extend(made.subs)
    entry.made = []


def _taint(made: _Made | None, state: _Run) -> None:
    """An input changed in a way no hit can replay: its maker forgets it, so
    the next run rebuilds it and runs this operation on the fresh shape."""
    if made is None:
        return
    root = made.root()
    with _LOCK:
        if root.entry is not None:
            _MEMO.pop(root.entry.key, None)
            _drop(root.entry)
        else:
            pending = [root]
            while pending:
                item = pending.pop()
                state.transient.pop(item.tshape, None)
                _REGISTRY.pop(item.tshape, None)
                pending.extend(item.subs)


def _returned_shapes(result: Any) -> list:
    """The shape objects a call returned itself: the result, or the members of a list or
    tuple it returned -- not the children they hold."""
    from build123d.topology import Shape

    found: list = []
    pending = [result]
    while pending:
        value = pending.pop()
        if isinstance(value, Shape):
            found.append(value)
        elif isinstance(value, (list, tuple)):
            pending.extend(reversed(value))
    return found


def _result_shapes(result: Any) -> list:
    """Every shape object a result holds: itself, the members of a list or
    tuple, and anytree children, read off the node state."""
    from build123d.topology import Shape

    found: list = []
    pending = [result]
    while pending:
        value = pending.pop()
        if isinstance(value, Shape):
            found.append(value)
            pending.extend(reversed(value.__dict__.get("_NodeMixin__children") or ()))
        elif isinstance(value, (list, tuple)):
            pending.extend(reversed(value))
    return found


# --- snapshots ----------------------------------------------------------------------------


class _Entry:
    __slots__ = ("key", "inputs", "snapshot", "effects", "made", "in_place")

    def __init__(self, *, key: tuple[int, int], inputs: list, snapshot: Any, effects: list,
                 in_place: bool = False) -> None:
        self.key = key
        self.inputs = inputs
        self.snapshot = snapshot
        self.effects = effects
        self.made: list[_Made] = []
        # The operation changed ``self`` and returned it (``clean``): a hit asked
        # by another object wrapping the same TShape changes THAT object, as the
        # operation would, and returns it.
        self.in_place = in_place

    def matches(self, shapes: list) -> bool:
        if len(shapes) != len(self.inputs):
            return False
        for shape, tshape in zip(shapes, self.inputs):
            wrapped = _wrapped(shape)
            if wrapped is None or wrapped.TShape() != tshape:
                return False
        return True

    def refresh(self, feature: int, run_id: int) -> None:
        for made in self.made:
            made.feature = feature
            made.run = run_id


class _ShapeState:
    """One live result object as the operation returned it."""

    __slots__ = ("obj", "attrs", "wrapped", "children")

    def __init__(self, obj: Any) -> None:
        from build123d.topology import Shape

        attrs = dict(obj.__dict__)
        wrapped = attrs.pop("_wrapped", None)
        if wrapped is None:
            raise _Unkeyable("an empty result")
        self.obj = obj
        self.wrapped = wrapped.Located(wrapped.Location())
        children = attrs.get("_NodeMixin__children")
        self.children = None
        if children is not None:
            if not all(isinstance(child, Shape) for child in children):
                raise _Unkeyable("a child that is not a shape")
            self.children = [_ShapeState(child) for child in children]
            attrs["_NodeMixin__children"] = None
        if isinstance(attrs.get("joints"), dict):
            attrs["joints"] = dict(attrs["joints"])
        self.attrs = attrs

    def restore(self) -> Any:
        from build123d.topology.shape_core import downcast

        attrs = dict(self.attrs)
        if isinstance(attrs.get("joints"), dict):
            attrs["joints"] = dict(attrs["joints"])
        if self.children is not None:
            attrs["_NodeMixin__children"] = [state.obj for state in self.children]
        obj = self.obj
        obj.__dict__.clear()
        obj.__dict__["_wrapped"] = downcast(self.wrapped.Located(self.wrapped.Location()))
        obj.__dict__.update(attrs)
        if self.children is not None:
            for state in self.children:
                state.restore()
        return obj


class _Sequence:
    __slots__ = ("container", "items")

    def __init__(self, container: type, items: list) -> None:
        self.container = container
        self.items = items

    def restore(self) -> Any:
        return self.container(item.restore() for item in self.items)


class _Literal:
    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value

    def restore(self) -> Any:
        return self.value


class _Adopt:
    """A constructor's result: the TopoDS it built, for the next construction
    of the same thing to wrap."""

    __slots__ = ("wrapped", "slot")

    def __init__(self, wrapped: Any, slot: str | None) -> None:
        if wrapped is None:
            raise _Unkeyable("an empty construction")
        self.wrapped = wrapped.Located(wrapped.Location())
        self.slot = slot

    def restore(self) -> Any:
        return self.wrapped.Located(self.wrapped.Location())


def _snapshot(value: Any) -> Any:
    from build123d.topology import Shape

    if isinstance(value, Shape):
        return _ShapeState(value)
    if isinstance(value, (list, tuple)):
        return _Sequence(type(value), [_snapshot(item) for item in value])
    if value is None or isinstance(value, (bool, int, float, str)):
        return _Literal(value)
    raise _Unkeyable(f"a result that cannot be kept: {type(value).__name__}")


# --- effects on inputs ----------------------------------------------------------------------
#
# What an operation does to its inputs is read as each sub-shape's state
# (``_state``) after the operation and compared with the state before it. The
# memo keeps the state it last read of every sub-shape of a memoized shape
# (``_STATE``): written when a capture reads it and when a ledger row sets it,
# forgotten with the entry whose result holds the sub-shape. So an input is
# walked once per operation, after it, and the state before is what the memo
# already holds.

_STATE: dict[Any, tuple] = {}


class _Captured:
    """One input before the operation: its full map, the TShape of each of its
    sub-shapes by ordinal and each one's state."""

    __slots__ = ("index", "handle", "mapped", "tshapes", "rows", "embedded", "known")

    def __init__(self, index: int, handle: Any, embedded: list[_Made], known: bool) -> None:
        self.index = index
        self.handle = handle
        self.embedded = embedded
        # A memoized shape's sub-shapes have states the memo keeps. A foreign shape,
        # captured for the memoized shapes it embeds, is read in full and kept nowhere.
        self.known = known
        self.mapped, self.tshapes = _mapped(handle)
        if known:
            rows = []
            for tshape in self.tshapes:
                state = _STATE.get(tshape)
                if state is None:
                    state = _STATE[tshape] = _state(tshape)
                rows.append(state)
            self.rows = rows
        else:
            self.rows = [_state(tshape) for tshape in self.tshapes]


def _capture(shapes: list, *, embedded: bool = False) -> list[_Captured]:
    """The inputs the operation may change: one per TShape, in call order, less
    any that is a sub-shape of another input (its ancestor's delta covers it).
    With ``embedded`` (an uncached call), an input no entry made is captured
    only for the memoized shapes it embeds, which a change taints."""
    from cadgen.store.materialize import TREE_TAG

    state = getattr(_LOCAL, "run", None)
    distinct: list[_Captured] = []
    seen: set = set()
    for index, shape in enumerate(shapes):
        wrapped = _wrapped(shape)
        if wrapped is None:
            continue
        tshape = wrapped.TShape()
        if tshape in seen:
            continue
        seen.add(tshape)
        made = _made_of(tshape, state)
        roots: list[_Made] = []
        if embedded and made is None:
            if TREE_TAG in shape.__dict__ or "__cadgen_component_identity__" in shape.__dict__:
                continue
            roots = _embedded(wrapped, state)
            if not roots:
                continue
        distinct.append(_Captured(index, wrapped.Located(wrapped.Location()), roots,
                                  known=made is not None and made.persistent()))
    return [item for item in distinct
            if not any(other is not item and other.mapped.Contains(item.handle) for other in distinct)]


def _embedded(wrapped: Any, state: _Run | None) -> list[_Made]:
    """The memoized shapes a foreign shape holds as sub-shapes."""
    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(wrapped, mapped)
    found: list[_Made] = []
    for ordinal in range(1, mapped.Extent() + 1):
        made = _made_of(mapped.FindKey(ordinal).TShape(), state)
        if made is not None and made.root() not in found:
            found.append(made.root())
    return found


def _effects(captured: list[_Captured], state: _Run) -> tuple[list[tuple[int, "_Effect"]], bool]:
    """What the operation did to its inputs, as replayable deltas noted in the
    ledger; ``sound`` is False when a change could not be captured (the input,
    or what it embeds, was tainted)."""
    effects: list[tuple[int, _Effect]] = []
    sound = True
    rowed: set = set()
    for item in captured:
        _mapped_after, tshapes = _mapped(item.handle)
        rows = [_state(tshape) for tshape in tshapes]
        if rows == item.rows:
            continue
        if item.embedded:
            for made in item.embedded:
                _taint(made, state)
            sound = False
            continue
        effect = _delta(item, tshapes, rows, rowed)
        made = _made_of(item.handle.TShape(), state)
        if effect is None:
            _STATS["unreplayable"] += 1
            sound = False
            _taint(made, state)
            continue
        effect.note(state.id)
        effects.append((item.index, effect))
        if made is not None:
            made.effects.append(effect)
    return effects, sound


def _mapped(handle: Any) -> tuple[Any, list]:
    """A shape's full ``TopExp`` map, and the TShape of each sub-shape by ordinal."""
    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(handle, mapped)
    return mapped, [mapped.FindKey(ordinal).TShape() for ordinal in range(1, mapped.Extent() + 1)]


def _state(tshape: Any) -> tuple:
    """One sub-shape's cheap state: kind, tolerance, the seven flags, how many
    representations it holds, and an edge's parametric flags."""
    kind = tshape.ShapeType()
    flags = (tshape.Free(), tshape.Modified(), tshape.Checked(), tshape.Orientable(), tshape.Closed(),
             tshape.Infinite(), tshape.Convex())
    if kind == TopAbs_EDGE:
        return (_EDGE, tshape.Tolerance(), flags, tshape.Curves().Extent(),
                (tshape.SameParameter(), tshape.SameRange(), tshape.Degenerated()))
    if kind == TopAbs_VERTEX:
        return (_VERTEX, tshape.Tolerance(), flags, tshape.Points().Extent(), None)
    if kind == TopAbs_FACE:
        return (_FACE, tshape.Tolerance(), flags, None, None)
    return (int(kind), None, flags, None, None)


def _forget_states(tshape: Any) -> None:
    """Drop the states kept of a TShape's sub-shapes: the memo no longer holds it.
    A sub-shape another entry's result shares is read again when next captured."""
    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(_handle_of(tshape), mapped)
    for ordinal in range(1, mapped.Extent() + 1):
        _STATE.pop(mapped.FindKey(ordinal).TShape(), None)


def _representations(tshape: Any, kind: int) -> Any:
    return tshape.ChangeCurves() if kind == _EDGE else tshape.ChangePoints()


def _appended(tshape: Any, kind: int, count: int) -> tuple:
    """The representations an edge or a vertex holds past the first ``count``:
    the ones the operation appended. The kernel's list reads from its head, and
    iterating it from Python costs milliseconds however short it is: it is
    reversed in place, its head taken as many times, reversed back and the tail
    put back -- nothing rebuilt, every read a step."""
    representations = _representations(tshape, kind)
    extra = representations.Extent() - count
    if extra <= 0:
        return ()
    representations.Reverse()
    taken = []
    for _ in range(extra):
        taken.append(representations.First())
        representations.RemoveFirst()
    representations.Reverse()
    taken.reverse()
    for representation in taken:
        representations.Append(representation)
    return tuple(taken)


def _truncate(representations: Any, count: int) -> None:
    """Drop the representations past the first ``count``, from the tail. The
    kernel's list removes from its head: it is reversed in place, its head
    removed as many times, and reversed back -- nothing is rebuilt."""
    extra = representations.Extent() - count
    if extra <= 0:
        return
    representations.Reverse()
    for _ in range(extra):
        representations.RemoveFirst()
    representations.Reverse()


def _delta(item: _Captured, tshapes: list, rows: list[tuple], rowed: set) -> "_Effect | None":
    """The sparse change between the input's state before and after: for each
    sub-shape whose state differs, its scalars and the representations appended,
    read past the count before. None when the change is one no delta expresses:
    a sub-shape added or removed, or standing at another's ordinal, a kind
    changed, representations taken away. A sub-shape two inputs share is rowed
    once; an input whose every change another input rowed has an empty effect."""
    if len(rows) != len(item.rows):
        return None
    changed: list[_Row] = []
    for ordinal, (before, after) in enumerate(zip(item.rows, rows)):
        if before == after:
            continue
        tshape = tshapes[ordinal]
        if tshape != item.tshapes[ordinal] or before[0] != after[0]:
            return None
        if item.known:
            _STATE[tshape] = after
        if tshape in rowed:
            continue
        appended: tuple = ()
        if before[3] is not None:
            if after[3] < before[3]:
                return None
            if after[3] > before[3]:
                appended = _appended(tshape, before[0], before[3])
        changed.append(_Row(tshape, before, after, appended))
        rowed.add(tshape)
    return _Effect(changed)


class _Row:
    """One sub-shape's state before and after an operation, settable either way."""

    __slots__ = ("tshape", "before", "after", "appended", "seq", "run")

    def __init__(self, tshape: Any, before: tuple, after: tuple, appended: tuple) -> None:
        self.tshape = tshape
        self.before = before
        self.after = after
        self.appended = appended
        self.seq = 0
        self.run = 0

    def set(self, state: tuple) -> None:
        """Set the sub-shape to ``state`` (``before`` or ``after``), touching only
        what differs between the two: the scalars set, the representations the
        operation appended put back or dropped from the tail."""
        tshape, before, after = self.tshape, self.before, self.after
        if before[1] != after[1]:
            tshape.Tolerance(state[1])
        if before[2] != after[2]:
            free, modified, checked, orientable, closed, infinite, convex = state[2]
            tshape.Free(free)
            tshape.Modified(modified)
            tshape.Checked(checked)
            tshape.Orientable(orientable)
            tshape.Closed(closed)
            tshape.Infinite(infinite)
            tshape.Convex(convex)
        if before[4] != after[4]:
            same_parameter, same_range, degenerated = state[4]
            tshape.SameParameter(same_parameter)
            tshape.SameRange(same_range)
            tshape.Degenerated(degenerated)
        if before[3] != after[3]:
            representations = _representations(tshape, before[0])
            if state is after:
                for representation in self.appended:
                    representations.Append(representation)
            else:
                _truncate(representations, before[3])
        _STATE[tshape] = state


class _Effect:
    """One operation's change to one input, as sparse rows, replayable."""

    __slots__ = ("rows", "id", "origin", "__weakref__")

    def __init__(self, rows: list[_Row]) -> None:
        self.rows = rows
        self.id = next(_EFFECT_IDS)
        # ``(key id, n, input index)`` of the memoized call that had this effect;
        # None for a call that ran plain, which no construction key can name.
        self.origin: tuple[int, int, int] | None = None
        _EFFECTS[self.id] = self

    def geometric(self) -> bool:
        """Whether the change reaches past the shapes' flags: a tolerance, a
        representation, an edge's parametric flags (``_effects_named``)."""
        return any(row.before[1] != row.after[1] or row.before[3] != row.after[3] or row.appended
                   or row.before[4] != row.after[4] for row in self.rows)

    def note(self, run_id: int) -> None:
        """Into the ledger as applied by ``run_id``, the shapes already as the
        operation left them."""
        for row in self.rows:
            row.seq = next(_SEQUENCE)
            row.run = run_id
            _LEDGER.setdefault(row.tshape, []).append(row)

    def apply(self, run_id: int) -> None:
        for row in self.rows:
            row.set(row.after)
        self.note(run_id)

    def forget(self) -> None:
        """Out of the ledger without touching the shapes: the memo no longer
        holds what these rows were applied to."""
        for row in self.rows:
            rows = _LEDGER.get(row.tshape)
            if rows is None:
                continue
            kept = [other for other in rows if other is not row]
            if kept:
                _LEDGER[row.tshape] = kept
            else:
                del _LEDGER[row.tshape]
