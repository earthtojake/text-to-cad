"""The CadQuery memo: one interception layer at CadQuery's topology layer, and what it remembers, in
the CadQuery worker's memory for the worker's life (law 5: the memo is the only build cache, and it
lives in the worker).

Where the engine's kernel memo (``cad.engine.kernel.memo``) sits on build123d's topology modules, this
one sits on CadQuery's (``cadquery.occ_impl.shapes``), patched in place on its classes and module
(``install``, idempotent): the primitive makers (``Solid.makeBox``, ``makeCylinder``, ``makeSphere``,
``makeCone``, ``makeTorus``, ``makeWedge``, ``makeLoft``, ``makeSolid``), the sweeps and extrusions
(``extrudeLinear``, ``extrudeLinearWithRotation``, ``revolve``, ``sweep``, ``sweep_multi``), the
booleans (``Shape.fuse``, ``cut``, ``intersect``, and ``Compound``'s), fillets and chamfers (``Mixin3D``'s,
a wire's and a face's 2D ones), ``clean``, ``mirror``, the copies and placements (``copy``, ``located``,
``moved``, ``transformShape``, ``transformGeometry``), the 2D makers a ``Workplane`` draws with (``Wire``'s
and ``Edge``'s circles, polygons, splines and lines, ``Face.makeFromWires`` and the rest), ``Shell`` and
``Compound``'s constructors, and the module's free functions (``fuse``, ``cut``, ``intersect``, ``fillet``,
``chamfer``, ``shell``, ``clean``). Every call a CadQuery program makes through them inside a run (``run``)
is seen once, at the boundary; ``Workplane`` and ``Sketch`` call into them, so their chains are seen too.

**Keys.** A call is keyed by its operation, its canonical parameters -- plain values by value, CadQuery's
``Vector``, ``Location``, ``Plane`` and ``Matrix`` by their numbers, enums by name -- and the keys of the
shapes it was given. A shape's key is where it came from: the key of the operation that made its
``TShape`` (the registry, pointer to key) and its position among that call's results, with its own
location and orientation; a sub-shape a selector cast out of a result (the edges a fillet takes, the face
a workplane stands on) is keyed as its root's sub-shape, by its kind and its index in the root's
``TopExp`` map (``_SUBS``). A shape no operation of this process made (an import, a shape cast from raw
OCP) has no key, and a call given one runs plain, counted (``unkeyable``). The n-th call with one key in a
run is its own entry (``(key, n)``), so two identical constructions in one body are two objects.

**Hits.** A hit requires the key and, for every shape input, the very ``TShape`` the entry was computed
with, and hands back the geometry the first run made: a fresh wrapper of the same class on the SAME
``TopoDS_Shape`` -- as CadQuery would return a new object -- with the ``forConstruction`` flag and the
``label`` the first result had. Nothing is reconstructed: pointer identity holds along every chain of
hits, and every miss makes its downstream miss, since a fresh result is a new ``TShape``. So a replay
returns geometry equal to a cold run (the same bytes: the same kernel objects), which a test holds.

**Memory.** Entries live in this process, never on disk, and the sweep after each outermost run drops
what the last ``RUNS_KEPT`` runs did not use (``_sweep``). ``CAD_ENGINE_MEMO=0`` turns hits off and
nothing else: every call is keyed and counted as ever, and runs.

The memo is an optimization and never the reason a build fails: a key that cannot be made, a result it
cannot keep (a value that is no shape), runs the call plain and counts it. ``install`` takes the module
to patch, CadQuery's by default; the tests patch a stand-in with CadQuery's names on build123d's shapes.
"""

from __future__ import annotations

import enum
import hashlib
import itertools
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

__all__ = ["RUNS_KEPT", "TARGETS", "clear", "enabled", "install", "run", "stats", "uninstall"]

#: What the sweep keeps: every entry the last RUNS_KEPT outermost runs used.
RUNS_KEPT = 4
#: Sub-shapes mapped per result at most: past it a result's sub-shapes are unkeyable, and a call given
#: one runs plain.
SUB_SHAPES = 20000
#: What is patched, by class (None: the module's own functions) and attribute. A class's own attribute
#: alone: an inherited one is its base's.
TARGETS: tuple[tuple[str | None, str], ...] = (
    *((("Solid", name) for name in ("makeBox", "makeCone", "makeCylinder", "makeTorus", "makeWedge", "makeSphere",
                                     "makeLoft", "makeSolid", "extrudeLinear", "extrudeLinearWithRotation", "revolve",
                                     "sweep", "sweep_multi"))),
    *((("Face", name) for name in ("makeFromWires", "makePlane", "makeRuledSurface", "makeNSidedSurface",
                                    "makeSplineApprox", "fillet2D", "chamfer2D", "thicken"))),
    *((("Wire", name) for name in ("makePolygon", "makeCircle", "makeEllipse", "makeHelix", "assembleEdges", "combine",
                                    "close", "offset2D", "fillet", "fillet2D", "chamfer2D"))),
    *((("Edge", name) for name in ("makeCircle", "makeEllipse", "makeSpline", "makeSplineApprox", "makeThreePointArc",
                                    "makeTangentArc", "makeLine", "makeBezier"))),
    ("Vertex", "makeVertex"),
    ("Shell", "makeShell"),
    *((("Compound", name) for name in ("makeCompound", "makeText", "cut", "fuse", "intersect"))),
    *((("Shape", name) for name in ("cut", "fuse", "intersect", "split", "clean", "fix", "mirror", "copy",
                                     "transformShape", "transformGeometry", "translate", "rotate", "scale", "located",
                                     "moved"))),
    *((("Mixin3D", name) for name in ("fillet", "chamfer", "shell", "dprism"))),
    *(((None, name) for name in ("fuse", "cut", "intersect", "fillet", "chamfer", "shell", "clean"))),
)

_LOCK = threading.RLock()
_LOCAL = threading.local()
_MEMO: "OrderedDict[tuple[int, int], _Entry]" = OrderedDict()
_REGISTRY: dict[Any, "_Made"] = {}
_SUBS: dict[Any, tuple["_Made", int, int]] = {}
_KEY_IDS: dict[tuple, int] = {}
_KEY_IDS_NEXT = itertools.count(1)
_RUN_IDS = itertools.count(1)
_STATS = {"hits": 0, "misses": 0, "unkeyable": 0, "errors": 0, "runs": 0}
_PATCHED: list[tuple[Any, str, Any]] = []  # (owner, attribute, original), to uninstall
_installed: dict[str, Any] = {}


class _Unkeyable(Exception):
    pass


@dataclass
class _Made:
    """A ``TShape`` an operation made: the entry's key and its position among the results."""

    key: tuple[int, int]
    index: int


@dataclass
class _Kept:
    """One result of an entry: the class to wrap it in again, the ``TopoDS_Shape`` itself, and the
    attributes CadQuery sets on a wrapper."""

    cls: type
    topods: Any
    for_construction: bool
    label: str


@dataclass
class _Entry:
    key: tuple[int, int]
    inputs: tuple
    results: list[_Kept]
    shape: str  # "one" (a shape), "list" or "tuple" (of shapes)
    used: int = 0


@dataclass
class _Run:
    id: int
    depth: int = 0
    tally: dict[str, int] = field(default_factory=lambda: {"hits": 0, "misses": 0, "unkeyable": 0, "errors": 0})
    counts: dict[int, int] = field(default_factory=dict)
    unkeyable: list[str] = field(default_factory=list)  # each call that ran plain, and why (the first few)
    missed: list[str] = field(default_factory=list)  # each operation that missed, in order


def enabled() -> bool:
    return os.environ.get("CAD_ENGINE_MEMO", "1").strip() not in ("0", "false", "no", "off")


def stats() -> dict[str, int]:
    """The memo's counts for this process, and the running run's (``run``)."""
    state = getattr(_LOCAL, "run", None)
    return {**_STATS, "entries": len(_MEMO), **({f"run_{name}": count for name, count in state.tally.items()}
                                                 if state is not None else {})}


def clear() -> None:
    """Forget everything (a test's)."""
    with _LOCK:
        _MEMO.clear()
        _REGISTRY.clear()
        _SUBS.clear()
        _KEY_IDS.clear()


# --- the run --------------------------------------------------------------------------------------


class run:
    """A run: the calls inside it are keyed and may hit; nested runs are one run. ``tally`` (after the
    block) is what this run did: ``hits``, ``misses``, ``unkeyable``, ``errors``."""

    def __init__(self) -> None:
        self.tally: dict[str, int] = {}
        self.unkeyable: list[str] = []
        self.missed: list[str] = []
        self._outer = False

    def __enter__(self) -> "run":
        state = getattr(_LOCAL, "run", None)
        if state is None:
            _LOCAL.run = _Run(next(_RUN_IDS))
            self._outer = True
            _STATS["runs"] += 1
        return self

    def __exit__(self, *_exc: Any) -> None:
        state = getattr(_LOCAL, "run", None)
        if state is not None:
            self.tally = dict(state.tally)
            self.unkeyable = list(state.unkeyable[:20])
            self.missed = list(state.missed)
        if self._outer and state is not None:
            _LOCAL.run = None
            _sweep(state.id)


def _sweep(current: int) -> None:
    """Drop every entry the last ``RUNS_KEPT`` runs did not use, and what the registry holds of it."""
    with _LOCK:
        gone = [key for key, entry in _MEMO.items() if entry.used <= current - RUNS_KEPT]
        for key in gone:
            del _MEMO[key]
        if gone:
            dropped = set(gone)
            for tshape in [tshape for tshape, made in _REGISTRY.items() if made.key in dropped]:
                del _REGISTRY[tshape]
            for tshape in [tshape for tshape, (made, _kind, _index) in _SUBS.items() if made.key in dropped]:
                del _SUBS[tshape]


# --- keys -----------------------------------------------------------------------------------------


def _intern(key: tuple) -> int:
    with _LOCK:
        found = _KEY_IDS.get(key)
        if found is None:
            found = _KEY_IDS[key] = next(_KEY_IDS_NEXT)
        return found


def _location_key(topods: Any) -> tuple:
    transformation = topods.Location().Transformation()
    return tuple(round(transformation.Value(row, column), 9) for row in (1, 2, 3) for column in (1, 2, 3, 4))


def _is_shape(value: Any) -> bool:
    return any(cls.__name__ == "Shape" and str(cls.__module__).split(".")[0] == _installed.get("package", "cadquery")
               for cls in type(value).__mro__)


def _shape_key(shape: Any) -> tuple:
    topods = getattr(shape, "wrapped", None)
    if topods is None or topods.IsNull():
        raise _Unkeyable("an empty shape")
    tshape = topods.TShape()
    made = _REGISTRY.get(tshape)
    if made is not None:
        head: tuple = ("made", made.key, made.index)
    else:
        sub = _SUBS.get(tshape)
        if sub is None:
            raise _Unkeyable(f"a {type(shape).__name__} no operation of this process made")
        root, kind, index = sub
        head = ("sub", root.key, root.index, kind, index)
    return ("shape", head, _location_key(topods), int(topods.Orientation()))


def _value_key(value: Any) -> Any:
    kind = type(value)
    if value is None or kind in (bool, int, str, bytes):
        return (kind.__name__, value)
    if kind is float:
        return ("float", repr(value))
    if kind in (tuple, list):
        return (kind.__name__, tuple(_value_key(item) for item in value))
    if kind is dict:
        return ("dict", tuple(sorted((repr(name), _value_key(item)) for name, item in value.items())))
    if isinstance(value, enum.Enum):
        return ("enum", f"{kind.__module__}.{kind.__qualname__}", value.name)
    if _is_shape(value):
        return _shape_key(value)
    name = kind.__name__
    if name in ("Vector", "Location") and hasattr(value, "toTuple"):
        return (name, _value_key(value.toTuple()))
    if name == "Plane" and all(hasattr(value, attr) for attr in ("origin", "xDir", "zDir")):
        return ("Plane", _value_key(value.origin.toTuple()), _value_key(value.xDir.toTuple()),
                _value_key(value.zDir.toTuple()))
    if name == "Matrix" and hasattr(value, "transposed_list"):
        return ("Matrix", _value_key(list(value.transposed_list())))
    if callable(value):
        raise _Unkeyable(f"a callable argument ({kind.__module__}.{kind.__qualname__})")
    raise _Unkeyable(f"an argument the memo does not key ({kind.__module__}.{kind.__qualname__})")


def _shapes_in(values: Any) -> Iterator[Any]:
    """Every shape among ``values`` (a tuple of arguments, lists and tuples among them, one level of dict)."""
    for value in values:
        if _is_shape(value):
            yield value
        elif isinstance(value, (tuple, list)):
            yield from _shapes_in(value)
        elif isinstance(value, dict):
            yield from _shapes_in(value.values())


def _tshapes(shapes: list) -> tuple:
    return tuple(shape.wrapped.TShape() for shape in shapes)


# --- results --------------------------------------------------------------------------------------


def _keep(result: Any) -> tuple[str, list[_Kept]]:
    """What a result is kept as: a shape, or a list or tuple of shapes; anything else is unkeepable."""
    if _is_shape(result):
        return "one", [_kept(result)]
    if isinstance(result, (list, tuple)) and result and all(_is_shape(item) for item in result):
        return type(result).__name__, [_kept(item) for item in result]
    raise _Unkeyable(f"a result the memo does not keep ({type(result).__name__})")


def _copy(topods: Any) -> Any:
    """A value copy of a ``TopoDS_Shape``: the same ``TShape`` at the same location and orientation, in an
    object of its own -- CadQuery's ``move`` and ``locate`` change a shape's object in place, so what is
    kept, and what a hit hands out, is never the object the program holds."""
    return topods.Located(topods.Location())


def _kept(shape: Any) -> _Kept:
    topods = shape.wrapped
    if topods is None or topods.IsNull():
        raise _Unkeyable("an empty result")
    return _Kept(type(shape), _copy(topods), bool(getattr(shape, "forConstruction", False)),
                 str(getattr(shape, "label", "")))


def _register(entry: _Entry) -> None:
    """Every result's ``TShape`` under the entry, and each sub-shape below it that no root holds yet."""
    from OCP.TopAbs import (TopAbs_COMPSOLID, TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX,
                            TopAbs_WIRE)
    from OCP.TopExp import TopExp

    try:  # OCP 8.0 names the indexed map by its hasher; 7.9 (CadQuery's) by TopTools' name
        from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as IndexedMap
    except ImportError:
        from OCP.TopTools import TopTools_IndexedMapOfShape as IndexedMap

    with _LOCK:
        for index, kept in enumerate(entry.results):
            tshape = kept.topods.TShape()
            if tshape in _REGISTRY:
                continue  # handed back an input, or a shape another entry made first: it keeps its maker
            made = _REGISTRY[tshape] = _Made(entry.key, index)
            _SUBS.pop(tshape, None)
            counted = 0
            # Every kind a selector casts out of a result: a compound's solids and shells, a solid's faces,
            # a face's wires and edges, the vertices.
            for kind in (TopAbs_COMPSOLID, TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE, TopAbs_WIRE, TopAbs_EDGE, TopAbs_VERTEX):
                found = IndexedMap()
                TopExp.MapShapes_s(kept.topods, kind, found)
                counted += found.Extent()
                if counted > SUB_SHAPES:
                    break
                for at in range(1, found.Extent() + 1):
                    sub = found.FindKey(at).TShape()
                    if sub not in _REGISTRY and sub not in _SUBS:
                        _SUBS[sub] = (made, int(kind), at)


def _restore(entry: _Entry) -> Any:
    """A hit's result: fresh wrappers on the first run's shapes."""
    made = []
    for kept in entry.results:
        wrapper = kept.cls(_copy(kept.topods))
        wrapper.forConstruction = kept.for_construction
        wrapper.label = kept.label
        made.append(wrapper)
    if entry.shape == "one":
        return made[0]
    return made if entry.shape == "list" else tuple(made)


# --- the call -------------------------------------------------------------------------------------


def _call(label: str, function: Callable[..., Any], args: tuple, kwargs: dict, skip: int = 0) -> Any:
    """One call seen at the boundary: ``args[skip:]`` are its parameters (a classmethod's ``cls`` is
    its label's, not a parameter)."""
    state = getattr(_LOCAL, "run", None)
    if state is None or state.depth:
        # Outside a run, or inside a call this layer is already seeing: the inner calls are its own.
        return function(*args, **kwargs)
    shapes = list(_shapes_in(args[skip:])) + list(_shapes_in(kwargs.values()))
    try:
        key = (label, tuple(_value_key(value) for value in args[skip:]),
               tuple((name, _value_key(value)) for name, value in sorted(kwargs.items())))
        key_id = _intern(key)
    except _Unkeyable as error:
        _STATS["unkeyable"] += 1
        state.tally["unkeyable"] += 1
        state.unkeyable.append(f"{label}: {error}")
        return _plain(state, function, args, kwargs)
    except Exception:  # noqa: BLE001 - the memo never fails a call
        _STATS["errors"] += 1
        state.tally["errors"] += 1
        return _plain(state, function, args, kwargs)
    n = state.counts.get(key_id, 0)
    state.counts[key_id] = n + 1
    given = _tshapes(shapes)
    entry = None
    why = "new key"
    if enabled():
        with _LOCK:
            entry = _MEMO.get((key_id, n))
            if entry is not None and entry.inputs == given:
                _MEMO.move_to_end((key_id, n))
            else:
                why = "inputs differ" if entry is not None else ("ordinal" if any(k[0] == key_id for k in _MEMO) else "new key")
                entry = None
    if entry is not None:
        entry.used = state.id
        _STATS["hits"] += 1
        state.tally["hits"] += 1
        return _restore(entry)
    result = _plain(state, function, args, kwargs)
    _STATS["misses"] += 1
    state.tally["misses"] += 1
    state.missed.append(f"{label} ({why})")
    try:
        shape, kept = _keep(result)
    except _Unkeyable:
        return result
    except Exception:  # noqa: BLE001
        _STATS["errors"] += 1
        state.tally["errors"] += 1
        return result
    entry = _Entry((key_id, n), given, kept, shape, used=state.id)
    try:
        _register(entry)
    except Exception as error:  # noqa: BLE001 - a result it cannot register is not kept
        _STATS["errors"] += 1
        state.tally["errors"] += 1
        state.unkeyable.append(f"{label}: not kept ({type(error).__name__}: {error})")
        return result
    with _LOCK:
        _MEMO[(key_id, n)] = entry
    return result


def _plain(state: _Run, function: Callable[..., Any], args: tuple, kwargs: dict) -> Any:
    state.depth += 1
    try:
        return function(*args, **kwargs)
    finally:
        state.depth -= 1


# --- installation ---------------------------------------------------------------------------------


def _wrap(label: str, original: Any, kind: str) -> Any:
    if kind == "classmethod":
        function = original.__func__

        def patched_classmethod(cls: type, *args: Any, **kwargs: Any) -> Any:
            return _call(f"{cls.__name__}.{label}", function, (cls, *args), kwargs, skip=1)

        patched_classmethod.__name__ = getattr(function, "__name__", label)
        patched_classmethod.__doc__ = getattr(function, "__doc__", None)
        return classmethod(patched_classmethod)
    if kind == "staticmethod":
        function = original.__func__

        def patched_staticmethod(*args: Any, **kwargs: Any) -> Any:
            return _call(label, function, args, kwargs)

        return staticmethod(patched_staticmethod)

    def patched(*args: Any, **kwargs: Any) -> Any:
        return _call(label, original, args, kwargs)

    patched.__name__ = getattr(original, "__name__", label)
    patched.__doc__ = getattr(original, "__doc__", None)
    patched.__wrapped__ = original  # type: ignore[attr-defined]
    return patched


def install(module: Any = None) -> int:
    """Patch ``module`` (CadQuery's ``cadquery.occ_impl.shapes`` by default) in place, once: every
    ``TARGETS`` attribute the module and its classes define. The count patched. Idempotent."""
    with _LOCK:
        if _installed:
            return _installed["count"]
        if module is None:
            import importlib

            module = importlib.import_module("cadquery.occ_impl.shapes")
        count = 0
        for owner_name, attribute in TARGETS:
            owner = module if owner_name is None else getattr(module, owner_name, None)
            if owner is None:
                continue
            original = owner.__dict__.get(attribute) if owner_name is not None else getattr(owner, attribute, None)
            if original is None:
                continue
            kind = ("classmethod" if isinstance(original, classmethod) else "staticmethod"
                    if isinstance(original, staticmethod) else "function")
            # A classmethod's label names the class it is called on (a subclass's own result class).
            label = attribute if owner_name is None or kind == "classmethod" else f"{owner_name}.{attribute}"
            setattr(owner, attribute, _wrap(label, original, kind))
            _PATCHED.append((owner, attribute, original))
            count += 1
        _installed.update({"module": module, "count": count, "package": str(module.__name__).split(".")[0]})
        return count


def uninstall() -> None:
    """Every patch undone (a test's)."""
    with _LOCK:
        for owner, attribute, original in reversed(_PATCHED):
            setattr(owner, attribute, original)
        _PATCHED.clear()
        _installed.clear()
        clear()
