"""Input-keyed memoization of build123d/OCCT kernel operations.

The incremental-generation design (design/incremental-generation.md) keeps the
deterministic full re-execution of model scripts and makes it cheap by caching
kernel operations on their INPUTS: an op call whose (operation, parameters,
input shapes) match a prior call returns the previously built shape instead of
re-running OCCT. Re-execution + op memoization recomputes exactly what a
dependency-graph system would: an edit re-runs only the ops whose inputs
changed, and everything downstream of them.

Scope and placement:

- Patches install at the TOPOLOGY layer (``Shape._bool_op``, ``Mixin3D``
  fillet/chamfer, ``Face``/``Solid``/``Wire`` factory classmethods) — pure
  shape-in/shape-out functions. The ``operations_*`` wrappers (``extrude()``,
  ``fillet()``…) mutate builder context and are deliberately NOT patched; their
  inner topology calls are the memo points.
- The cache lives in this module, which survives the generation runner's
  first-party module eviction (cadgen and site-packages are never evicted), so
  a warm daemon worker keeps its cache across requests.
  Computed results and disk hits share the same least-recently-used RAM limit.
  Evicting a RAM entry neither deletes its disk entry nor changes an owned result.
- Keys hash current input shapes by their BinTools BREP bytes: bytes stripped
  of location, orientation and triangulation, combined with the shape's own
  location matrix and orientation. A native edit can change a TShape without
  changing its pointer, so input digests are recomputed -- see
  ``_tshape_digest``. Fresh
  rebuilds of identical geometry serialize byte-identically (verified in the
  design doc's Phase 0 spike), so keys hit across full re-executions.
- Every consumer — the missing caller, a warm in-memory hit, a disk hit —
  receives the SAME reconstruction: a fresh wrapper read back from the
  canonical bytes, with its Python-level attributes (``topo_parent``,
  ``label``, ``_color``, ``joints``, anytree children, ...) replayed from an
  ATTRIBUTE RECIPE recorded against the call's shape arguments (see
  ``_StoredShape``). build123d derives those attributes from the inputs
  (``_bool_op`` copies ``self``'s onto the result; ``chamfer`` constructs a
  bare one), and downstream code steers on them — ``bd.chamfer(edges, …)``
  targets ``edges[0].topo_parent`` — so a hit that reconstructed a bare
  wrapper while a miss preserved the live one made geometry depend on cache
  state (the juno shin chamfered on a disk hit and not on a cold run).

Sub-shape identity is by CONTENT while the memo is installed. Canonical
reconstruction has a price: every op result is a fresh read-back, so a
sub-shape the op did not touch still comes out with a new TShape, and
build123d's identity is the TShape pointer (``Shape.is_same`` is OCCT
``IsSame``; ``__eq__`` routes through it; ``__hash__`` is the pointer hash).
Model code that holds a sub-shape across an op and re-selects it afterwards --
``edge.is_same(candidate)``, ``edge in shape.edges()``, a ``set`` of edges, a
sequential fillet loop that re-finds each junction edge in the current solid --
silently found nothing (twelve junction edges, plain build123d filleted six,
under the memo one). So ``install()`` also patches ``Shape.is_same``,
``__eq__`` and ``__hash__``: the TShape+location check stays the fast path, and
on a mismatch the two shapes compare by a GEOMETRIC SIGNATURE -- shape type,
sub-shape counts, and the world-space vertex points plus one sample point per
face (or per edge, below faces), rounded to 1e-6 (``_signature``). Not the
BREP bytes the memo keys with: those are a function of how a shape's location
chain is SPLIT between its TShape and its ``Location()``, and neither
``BRepBuilderAPI_Copy`` (input protection) nor a BinTools round trip
(reconstruction) preserves that split for located sub-shapes -- on a 236
sub-shape test part, Copy kept 114 sub-shapes byte-identical and a second
round trip 219 -- so bytes tell one edge apart from itself. World geometry
is what survives every re-expression, and rounding absorbs the ULP noise a
re-composed rotation leaves. Orientation is not in the signature, matching
``IsSame``. Hashing uses a subset of that signature, so sets and dicts agree
with ``==`` without sampling every curve and surface on insertion.
Two coincident, identical sub-shapes (an edge fused onto itself, two faces
sharing one plane and outline) therefore compare equal, where the pointer
check told them apart; that is the semantics a model sees under the memo.
Hashing uses only the signature's type and rounded vertex points. Equal full
signatures necessarily hash equally; curves/surfaces sharing those vertices
are distinguished by full equality when hashes collide.

Kill switch: ``CADGEN_OP_MEMO=0`` (and ``CADGEN_OP_MEMO_DISK=0`` for just the
disk tier). It disables the identity shims too: without the memo every op
returns its live result and pointer identity holds on its own.

Anything unkeyable — an argument type the normalizer does not understand, a
shape that fails to serialize — falls through to the original call, uncached.
Correctness never depends on a cache hit.
"""

from __future__ import annotations

import hashlib
import io
import os
import struct
import threading
from collections import OrderedDict
from functools import lru_cache


# Salt: bump _OP_MEMO_VERSION whenever keying or hit semantics change.
_OP_MEMO_VERSION = 7

_lock = threading.RLock()
_cache: OrderedDict[tuple, object] = OrderedDict()
# Retain only canonical result bytes and recipes. In particular, a TShape
# pointer is not an input digest: native geometry/descendants can mutate while
# the pointer remains unchanged, and retaining pointer keys also pins topology.
_stats = {"hits": 0, "misses": 0, "disk_hits": 0, "unkeyable": 0,
          "unstorable": 0, "evicted": 0, "errors": 0}
_installed = False


class _Unkeyable(Exception):
    """An argument cannot participate in a memo key; skip caching this call."""


def _enabled() -> bool:
    return os.environ.get("CADGEN_OP_MEMO", "1") != "0"


def _capacity() -> int:
    # Entries are canonical BREP bytes plus a JSON attribute recipe,
    # so a large cache is cheap — and a cap below a model's op count makes
    # every run thrash the disk tier (the moonwatch alone has ~6k keyable
    # ops, which is how the old 4096 default was caught).
    try:
        return 32768
    except ValueError:
        return 32768


def _tshape_digest(wrapped) -> str:
    """Digest the TShape's current content without retaining mutable topology.

    The first-seen digest of a TShape is not reusable: native vertex, curve,
    surface or descendant edits need not replace its pointer. Recompute from
    the actual bytes on every call. Normalizing handle-only properties keeps
    placement/orientation expressions independent of encounter order.

    The geometry-independent properties normalized here are:

    - **Location.** Stripped, and folded back in separately by
      :func:`_location_key`, so moved copies share the content digest.
    - **Orientation.** Forced FORWARD. A reversed shape SHARES its TShape with
      the forward one, so writing ``wrapped`` as it came in baked whichever
      orientation arrived first into the shared digest: hashing the forward
      solid first gave one digest for both, hashing the reversed one first gave
      a different digest for both. Orientation is not lost -- ``_shape_key``
      carries ``wrapped.Orientation()`` as its own key part, which is where a
      distinction that must not alias belongs.
    - **Triangulation and normals.** Written off. The two-argument
      ``BinTools.Write_s`` alias writes triangulation data, so a shape acquired
      a different digest the moment anything meshed it (a bounding box, a
      tessellation, an STL pass) -- and, memoized per TShape, whether that had
      happened yet was the run's history rather than the model's geometry. The
      explicit form matches the canonical bytes :func:`_write_brep` and the
      component store already write.

    - **Free and Checked bookkeeping.** Attaching a shape to a container can
      clear Free, and meshing clears Checked. Neither changes geometry. Copy
      the topology without copying its geometry or mesh, then normalize only
      these flags on that private topology. No caller-owned flag or geometry
      is changed and no live shape is retained by key construction.
    """
    from OCP.BinTools import BinTools, BinTools_FormatVersion
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.TopAbs import TopAbs_Orientation
    from OCP.TopExp import TopExp
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopTools import TopTools_IndexedMapOfShape

    private = BRepBuilderAPI_Copy(
        wrapped.Located(TopLoc_Location()).Oriented(TopAbs_Orientation.TopAbs_FORWARD),
        False, False,
    ).Shape()
    shapes = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(private, shapes)
    for index in range(1, shapes.Extent() + 1):
        shape = shapes.FindKey(index)
        shape.Free(False)
        shape.Checked(False)
    stream = io.BytesIO()
    BinTools.Write_s(
        private,
        stream,
        False,  # theWithTriangles
        False,  # theWithNormals
        BinTools_FormatVersion.BinTools_FormatVersion_CURRENT,
    )
    return hashlib.sha256(stream.getvalue()).hexdigest()


def _location_key(wrapped) -> tuple:
    trsf = wrapped.Location().Transformation()
    values = []
    for row in (1, 2, 3):
        for col in (1, 2, 3, 4):
            values.append(struct.pack("<d", trsf.Value(row, col)))
    return (b"".join(values),)


def _shape_key(shape) -> tuple:
    wrapped = shape.wrapped
    if wrapped is None:
        raise _Unkeyable("shape with no wrapped TopoDS")
    # The full TopoDS_Shape triple: TShape (content-identified), Location, and
    # Orientation. Orientation must be explicit — a reversed shape shares its
    # TShape with the forward one, and aliasing them flips downstream geometry.
    return ("shape", _tshape_digest(wrapped), _location_key(wrapped),
            int(wrapped.Orientation()))


def _normalize(value) -> object:
    """Normalize one argument into a hashable, deterministic key component."""
    if value is None or isinstance(value, (bool, str, bytes)):
        return value
    if isinstance(value, float):
        return ("f", struct.pack("<d", value))
    if isinstance(value, int):
        return ("i", value)
    if isinstance(value, (tuple, list)):
        return ("seq", tuple(_normalize(v) for v in value))
    if isinstance(value, dict):
        return ("map", tuple(sorted((k, _normalize(v)) for k, v in value.items())))

    type_name = type(value).__name__

    # OCCT algo builder instances (Shape._bool_op's `operation` param): the
    # class fully identifies the operation as build123d constructs them.
    if type_name.startswith("BRepAlgoAPI"):
        return ("occ_op", type_name)

    # build123d geometry value types, normalized through their float tuples.
    # Value types come FIRST: Vector/Axis/Location also carry a ``wrapped``
    # (gp_Vec/gp_Ax1/TopLoc_Location), so testing for ``wrapped`` before the
    # value normalizers routed them into the shape branch, where the TShape
    # digest raised and every such call — hundreds per builder-heavy model —
    # fell through unkeyable.
    module = type(value).__module__ or ""
    if module.startswith("build123d"):
        if type_name == "Axis":
            return (type_name, _normalize(value.position.to_tuple()),
                    _normalize(value.direction.to_tuple()))
        if type_name == "Plane":
            return (type_name, _normalize(value.origin.to_tuple()),
                    _normalize(value.x_dir.to_tuple()),
                    _normalize(value.z_dir.to_tuple()))
        if type_name == "Location":
            return (type_name, _normalize(tuple(value.to_tuple()[0])),
                    _normalize(tuple(value.to_tuple()[1])))
        to_tuple = getattr(value, "to_tuple", None)
        if callable(to_tuple):
            return (type_name, _normalize(to_tuple()))
        wrapped = getattr(value, "wrapped", None)
        if wrapped is not None and hasattr(wrapped, "TShape"):
            try:
                return _shape_key(value)
            except _Unkeyable:
                raise
            except Exception as exc:  # serialization failure => uncacheable
                raise _Unkeyable(str(exc)) from exc
    if module.startswith("enum") or hasattr(value, "name") and isinstance(getattr(type(value), "__members__", None), dict):
        return ("enum", type_name, value.name)

    # One-shot iterables cannot be keyed without consuming them, and the memo
    # layer never alters or consumes what the caller passed.
    raise _Unkeyable(f"unkeyable argument type: {module}.{type_name}")


def _reject_lazy(value) -> None:
    """Refuse to key arguments that keying would have to consume.

    A generator (or other one-shot iterable) can only be keyed by
    materializing it, and handing the op a materialized copy measurably
    changes results for some ops — the memo layer must NEVER alter what the
    caller passed. Concrete types (shapes, build123d value types, str/bytes,
    tuples/lists/dicts, numbers) are keyable in place; everything else lazy
    raises _Unkeyable and the call passes through uncached, verbatim.
    """
    if value is None or isinstance(value, (str, bytes, bool, int, float,
                                           tuple, list, dict)):
        return
    if hasattr(value, "wrapped"):
        return
    if (type(value).__module__ or "").startswith("build123d"):
        return
    if hasattr(value, "__iter__"):
        raise _Unkeyable(f"lazy iterable argument: {type(value).__name__}")


def _build_key(op_name: str, args: tuple, kwargs: dict) -> tuple:
    """Build the memo key from the caller's arguments, never mutating or
    consuming them."""
    key_parts = []
    for arg in args:
        _reject_lazy(arg)
        key_parts.append(_normalize(arg))
    kw_parts = []
    for name, val in sorted(kwargs.items()):
        _reject_lazy(val)
        kw_parts.append((name, _normalize(val)))
    return (_OP_MEMO_VERSION, op_name, tuple(key_parts), tuple(kw_parts))


def _remember(key: tuple, result: object) -> None:
    """Apply the same RAM limit to computed results and persistent-cache hits."""
    with _lock:
        _cache[key] = result
        _cache.move_to_end(key)
        capacity = _capacity()
        while len(_cache) > capacity:
            _cache.popitem(last=False)
            _stats["evicted"] += 1


def _store(key: tuple, result: object) -> None:
    _remember(key, result)
    _disk_put(key, result)


def _lookup(key: tuple):
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    stored = _disk_get(key)
    if stored is not None:
        _remember(key, stored)
        _stats["disk_hits"] += 1
    return stored


# --- persistent tier -------------------------------------------------------
#
# The canonical bytes ARE the durable representation, so persisting them gives
# a cold process (fresh daemon worker, CLI run, worktree, or a different model
# reusing the same part) the same skip a warm one gets. Keys are pure
# functions of op + inputs, content-addressed and salted, so the tier is
# shared safely across processes and checkouts; writes are atomic
# temp+rename, and any read problem falls back to executing the op.

def _disk_enabled() -> bool:
    return os.environ.get("CADGEN_OP_MEMO_DISK", "1") != "0"


@lru_cache(maxsize=1)
def _runtime_versions() -> tuple[str, str, str]:
    """Resolve loaded bindings and their distribution only on a kernel path.

    Unknown versions decline the optional disk tier; they must not create a
    shared persistent namespace for unrelated kernel builds.
    """
    from importlib.metadata import PackageNotFoundError, version

    import OCP
    import build123d

    try:
        distribution = version("cadquery-ocp-novtk")
    except PackageNotFoundError as error:
        # OCP imported from some other distribution. That is an unknown
        # version like any other, so decline the disk tier the same way --
        # and as a ValueError, because PackageNotFoundError is an ImportError
        # and callers that mean to decline do not catch those.
        raise ValueError("op memo requires the cadquery-ocp-novtk distribution "
                         "for persistent reuse") from error

    versions = (getattr(build123d, "__version__", None),
                getattr(OCP, "__version__", None), distribution)
    if any(not isinstance(value, str) or not value.strip() or "unknown" in value.lower()
           for value in versions):
        raise ValueError("op memo requires known build123d and OCP versions for persistent reuse")
    return versions


def _op_index_key(key: tuple) -> str:
    """Bind disk entries to the operation, scheme, loaded OCP and distribution."""
    build123d_version, ocp_version, distribution_version = _runtime_versions()
    scheme = (f"v{_OP_MEMO_VERSION}-b123d{build123d_version}"
              f"-ocp{ocp_version}-cadquery-ocp-novtk{distribution_version}")
    return hashlib.sha256((scheme + "\0" + repr(key)).encode("utf-8")).hexdigest()


def _disk_put(key: tuple, stored) -> None:
    """The result bytes become an OBJECT (content-addressed); the entry under
    ``index/op/<key>`` maps the op key to it plus the class/recipe header."""
    if not _disk_enabled() or not isinstance(stored, _StoredShape):
        return
    try:
        from cadgen.store.index import write_entry
        from cadgen.store.objects import put_object

        write_entry(
            "op",
            _op_index_key(key),
            {"object": put_object(stored.brep), "cls": stored.cls_path, "recipe": stored.recipe},
        )
    except Exception:
        _stats["errors"] += 1


def _resolve_shape_class(dotted: str):
    import importlib

    module_name, _, qualname = dotted.rpartition(".")
    if not module_name.startswith("build123d"):
        raise ValueError(f"refusing non-build123d class {dotted}")
    obj = importlib.import_module(module_name)
    for part in qualname.split("."):
        obj = getattr(obj, part)
    return obj


def _disk_get(key: tuple):
    if not _disk_enabled():
        return None
    try:
        from cadgen.store.index import read_entry
        from cadgen.store.objects import has_object, read_object

        entry = read_entry("op", _op_index_key(key))
        if not entry:
            return None
        digest = str(entry.get("object") or "")
        if not digest or not has_object(digest):
            return None
        # Resolve the class now so a foreign entry fails here (falls back to
        # executing the op) rather than at thaw.
        _resolve_shape_class(entry["cls"])
        return _StoredShape(entry["cls"], read_object(digest), entry["recipe"])
    except Exception:
        _stats["errors"] += 1
        return None


# --- pure VALUES over the same tiers -----------------------------------------
#
# Not every memoizable kernel result is a shape. A measurement of a placed
# shape -- a bounding box, an area -- is a pure function of the same inputs an
# op patch keys on, and it wants the same two tiers: the memory cache a warm
# worker keeps and the disk entry a cold process reads. Values ride the ``op``
# index as ``{"value": ...}`` rather than an object reference, because they are
# smaller than the digest that would point at them.
#
# Keying is the op patches' own: ``_build_key`` through ``_normalize``, so the
# key parts must be normalizable (numbers, strings, bytes, sequences, maps,
# build123d value types, shapes). Callers keying on a PLACED shape want
# ``placed_shape_key``. An op_name identifies the FUNCTION, so a caller that
# changes what it computes must change its op_name (or _OP_MEMO_VERSION moves
# every key at once).


def placed_shape_key(wrapped) -> tuple:
    """Key parts for a placed ``TopoDS_Shape``: the location-stripped content
    digest plus the location matrix -- the same two an op patch keys a shape
    input by, minus orientation, which no measurement depends on."""
    return (_tshape_digest(wrapped), _location_key(wrapped))


def memoized_value(op_name: str, key_args: tuple, compute):
    """``compute()``, memoized on ``key_args`` in memory and on disk.

    ``compute`` must be pure and return something JSON-round-trippable (the
    disk tier is a JSON entry); it takes no arguments, so its shape inputs stay
    out of the key and the caller states the key exactly. Anything unkeyable,
    or a disabled memo, calls straight through -- correctness never depends on
    a hit.
    """
    if not _enabled():
        return compute()
    try:
        key = _build_key(op_name, tuple(key_args), {})
    except _Unkeyable:
        _stats["unkeyable"] += 1
        return compute()
    except Exception:  # noqa: BLE001 - an unkeyable call is still a correct call
        _stats["errors"] += 1
        return compute()

    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            _stats["hits"] += 1
            return _cache[key]
    from_disk = _value_disk_get(key)
    if from_disk is not None:
        value = from_disk[0]
        _remember(key, value)
        _stats["disk_hits"] += 1
        _stats["hits"] += 1
        return value

    value = compute()
    _stats["misses"] += 1
    _remember(key, value)
    _value_disk_put(key, value)
    return value


def _value_disk_put(key: tuple, value) -> None:
    if not _disk_enabled():
        return
    try:
        from cadgen.store.index import write_entry

        write_entry("op", _op_index_key(key), {"value": value})
    except Exception:  # noqa: BLE001 - a store that cannot be written still computes
        _stats["errors"] += 1


def _value_disk_get(key: tuple):
    """``(value,)`` on a hit, None on a miss -- so a stored ``None`` is a hit."""
    if not _disk_enabled():
        return None
    try:
        from cadgen.store.index import read_entry

        entry = read_entry("op", _op_index_key(key))
        if not entry or "value" not in entry:
            return None
        return (entry["value"],)
    except Exception:  # noqa: BLE001
        _stats["errors"] += 1
        return None


class _StoredShape:
    """A cached op result: class path + canonical BREP bytes + attribute recipe.

    Cache correctness rests on CANONICAL RECONSTRUCTION. Cached shapes cannot
    be handed out live: downstream consumers mutate them (booleans and lofts
    bump input tolerances; meshing and bounding_box attach triangulation), so
    a live master is polluted by its own first use, and every isolation
    mechanism that preserves the live shape loses byte fidelity
    (BRepBuilderAPI_Copy re-serializes differently; BinTools write→read→write
    is not byte-stable for ~65% of real shapes).

    Instead, a cacheable result is serialized ONCE at op time (its canonical
    bytes), and EVERY consumer — the missing caller included — receives a
    fresh reconstruction read back from those bytes. All runs, cold or warm,
    therefore flow byte-identical shapes derived deterministically from the
    canonical bytes, which makes package output independent of cache state.
    Reconstructed inputs produce byte-identical downstream op results
    (validated empirically); a shape whose bytes fail to read back is simply
    not cached and the caller gets the original, exactly as un-memoized
    execution would.

    The bytes are only half of a build123d result. The wrapper's Python-level
    attributes are the other half, and they are NOT a function of the bytes:
    ``_bool_op`` copies ``self``'s ``topo_parent``/``label``/``_color``/
    ``joints`` onto its result and builds anytree children for a multi-solid
    compound, while ``chamfer`` returns a bare ``self.__class__(shape)``.
    Downstream code steers on them (``bd.chamfer(edges, …)`` targets
    ``edges[0].topo_parent``; the packager walks ``children``). So the entry
    also carries an ATTRIBUTE RECIPE: every attribute of the live result,
    encoded either as a literal or as a reference INTO THE CALL'S SHAPE
    ARGUMENTS ("the same object as argument 0's ``topo_parent``"), plus one
    recipe per anytree child, keyed to the reconstruction's top-level
    sub-shapes in order. Thawing replays the recipe against the CURRENT call's
    arguments, so a miss, a warm hit and a disk hit hand back wrappers that
    are indistinguishable from one another and from un-memoized execution. A
    result whose attributes cannot be expressed that way (a ``topo_parent``
    reachable from no argument, non-empty joints of unknown origin, nested
    children) is Unkeyable: the op runs uncached, as it always could.

    Relative to memo-OFF execution, canonicalization may change the exact
    bytes of some leaf components (geometrically identical). That is an
    accepted, versioned change: content addressing absorbs it as a one-time
    re-key, per the no-backwards-compatibility policy.
    """

    __slots__ = ("cls_path", "brep", "recipe")

    def __init__(self, cls_path: str, brep: bytes, recipe: dict):
        self.cls_path = cls_path
        self.brep = brep
        self.recipe = recipe


def _write_brep(wrapped) -> bytes:
    """Canonical geometry-only serialization (no triangulation/normals —
    mirrors component_package._shape_brep_bytes), location kept as-is."""
    from OCP.BinTools import BinTools, BinTools_FormatVersion

    stream = io.BytesIO()
    BinTools.Write_s(
        wrapped,
        stream,
        False,  # theWithTriangles
        False,  # theWithNormals
        BinTools_FormatVersion.BinTools_FormatVersion_CURRENT,
    )
    return stream.getvalue()


def _read_brep(data: bytes):
    from OCP.BinTools import BinTools
    from OCP.TopoDS import TopoDS_Shape

    shape = TopoDS_Shape()
    BinTools.Read_s(shape, io.BytesIO(data))
    if shape.IsNull():
        raise ValueError("BinTools read produced a null shape")
    return shape


def _downcast(wrapped):
    from build123d.topology import downcast

    return downcast(wrapped)


def _class_path(cls) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _is_shape(value) -> bool:
    # Geometry values can also own `_wrapped` (Vector now stores a gp_Vec
    # there). Only topology Shapes participate in protection and recipes.
    from build123d.topology import Shape

    return isinstance(value, Shape) and value._wrapped is not None


def _shape_args(key_args: tuple, kwargs: dict) -> list:
    """The call's shape arguments in a stable order: positional (recursing into
    lists/tuples, e.g. ``_bool_op``'s tool tuples and chamfer's edge lists),
    then keyword by name. Recipe references index into this list, so the
    flattening must be identical on the miss that records and the hit that
    replays — it is, because both see the same call signature."""
    found: list = []

    def walk(value) -> None:
        if _is_shape(value):
            found.append(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for arg in key_args:
        walk(arg)
    for _name, value in sorted(kwargs.items()):
        walk(value)
    return found


# Attributes anytree keeps on a node. Children are recorded as their own
# recipes; a parent link is only ever the result itself (for its children).
_ANYTREE_CHILDREN = "_NodeMixin__children"
_ANYTREE_PARENT = "_NodeMixin__parent"
_MISSING = object()


def _encode_attr(name: str, value, shape_args: list, owner) -> list:
    """One attribute of a live result as a JSON-safe recipe entry."""
    if value is None or isinstance(value, (bool, int, str)):
        return ["lit", value]
    if isinstance(value, float):
        return ["float", struct.pack("<d", value).hex()]
    for index, shape in enumerate(shape_args):
        if value is shape:
            return ["arg", index]
    for index, shape in enumerate(shape_args):
        if getattr(shape, name, _MISSING) is value:
            return ["arg_attr", index, name]
    if name == "joints" and isinstance(value, dict):
        if not value:
            return ["lit_joints"]
        # copy_attributes_to deep-copies the base's joints and re-parents them
        # onto the result; recognize exactly that shape of origin.
        for index, shape in enumerate(shape_args):
            source = getattr(shape, "joints", None)
            if (
                isinstance(source, dict)
                and set(source) == set(value)
                and all(getattr(joint, "parent", None) is owner for joint in value.values())
            ):
                return ["arg_joints", index]
        raise _Unkeyable("joints of unknown origin")
    from build123d.geometry import Color

    if isinstance(value, Color):
        return ["color", [struct.pack("<d", float(c)).hex() for c in value]]
    raise _Unkeyable(f"unstorable result attribute {name!r} ({type(value).__name__})")


def _attrs_recipe(node, shape_args: list, *, parent) -> list:
    """Recipe for every attribute of ``node`` except its geometry and anytree
    links. ``parent`` is the result that owns ``node`` as a child (None for the
    result itself); a parent link pointing anywhere else is unstorable."""
    entries: list = []
    for name, value in node.__dict__.items():
        if name == "_wrapped" or name == _ANYTREE_CHILDREN:
            continue
        if name == _ANYTREE_PARENT:
            if value is not None and value is not parent:
                raise _Unkeyable("result has a foreign anytree parent")
            continue
        entries.append([name, _encode_attr(name, value, shape_args, node)])
    return entries


def _attribute_recipe(result, shape_args: list, reconstruction) -> dict:
    """The full recipe: the result's attributes plus one per anytree child.

    Children are matched positionally to the top-level sub-shapes of the
    result — the order ``make_composite`` built them in — and must be the same
    TopoDS sub-shapes; BinTools preserves compound order, so the k-th top-level
    shape of the reconstruction is the k-th child's geometry on thaw."""
    from build123d.topology.shape_core import get_top_level_topods_shapes

    recipe = {"attrs": _attrs_recipe(result, shape_args, parent=None)}
    children = list(getattr(result, "children", ()) or ())
    if children:
        tops = get_top_level_topods_shapes(result.wrapped)
        # The enumerator dispatches on the Python class, so the raw read-back
        # must be downcast (a TopoDS_Shape-typed compound counts as ONE shape).
        if len(tops) != len(children) or len(get_top_level_topods_shapes(_downcast(reconstruction))) != len(children):
            raise _Unkeyable("children do not map onto the top-level sub-shapes")
        specs = []
        for child, top in zip(children, tops):
            if not _is_shape(child) or not child.wrapped.IsSame(top):
                raise _Unkeyable("child is not the matching top-level sub-shape")
            if list(getattr(child, "children", ()) or ()):
                raise _Unkeyable("nested children")
            specs.append(
                {"cls": _class_path(type(child)), "attrs": _attrs_recipe(child, shape_args, parent=result)}
            )
        recipe["children"] = specs
    return recipe


def _decode_attr(entry: list, shape_args: list):
    kind = entry[0]
    if kind == "lit":
        return entry[1]
    if kind == "float":
        return struct.unpack("<d", bytes.fromhex(entry[1]))[0]
    if kind == "arg":
        return shape_args[entry[1]]
    if kind == "arg_attr":
        return getattr(shape_args[entry[1]], entry[2])
    if kind == "lit_joints":
        return {}
    if kind == "color":
        from build123d.geometry import Color

        return Color(*(struct.unpack("<d", bytes.fromhex(c))[0] for c in entry[1]))
    raise ValueError(f"unknown recipe entry {kind!r}")


def _apply_attrs(node, entries: list, shape_args: list) -> None:
    import copy

    for name, entry in entries:
        if entry[0] == "arg_joints":
            node.joints = copy.deepcopy(shape_args[entry[1]].joints)
            for joint in node.joints.values():
                joint.parent = node
            continue
        setattr(node, name, _decode_attr(entry, shape_args))


def _freeze_result(result, shape_args: list):
    """Convert an op result into its stored form, verifying its bytes read
    back and its attributes are expressible. Raises _Unkeyable when the result
    cannot be cached."""
    return _freeze_result_for_first_consumer(result, shape_args)[0]


def _thaw_stored_shape(stored: _StoredShape, shape_args: list, reconstruction=None):
    """Replay one stored shape, optionally using its just-verified BREP read."""
    cls = _resolve_shape_class(stored.cls_path)
    wrapped = reconstruction if reconstruction is not None else _read_brep(stored.brep)
    clone = cls(_downcast(wrapped))
    _apply_attrs(clone, stored.recipe["attrs"], shape_args)
    specs = stored.recipe.get("children")
    if specs:
        from build123d.topology.shape_core import get_top_level_topods_shapes

        tops = get_top_level_topods_shapes(clone.wrapped)
        if len(tops) != len(specs):
            raise ValueError("reconstruction has a different top-level shape count")
        children = []
        for spec, top in zip(specs, tops):
            child = _resolve_shape_class(spec["cls"])(_downcast(top))
            _apply_attrs(child, spec["attrs"], shape_args)
            children.append(child)
        clone.children = children
    return clone


def _freeze_result_for_first_consumer(result, shape_args: list):
    """Stored bytes plus the miss caller's already-verified reconstruction.

    Only canonical bytes and the attribute recipe enter either cache. The
    ephemeral value avoids reading those bytes a second time on a miss; later
    RAM and disk hits still reconstruct independently.
    """
    if isinstance(result, (tuple, list)):
        pairs = [_freeze_result_for_first_consumer(item, shape_args) for item in result]
        stored = ("seq", type(result), tuple(pair[0] for pair in pairs))
        first = type(result)(pair[1] for pair in pairs)
        return stored, first
    if _is_shape(result):
        data = _write_brep(result.wrapped)
        reconstruction = _read_brep(data)
        recipe = _attribute_recipe(result, shape_args, reconstruction)
        stored = _StoredShape(_class_path(type(result)), data, recipe)
        return stored, _thaw_stored_shape(stored, shape_args, reconstruction)
    if result is None or isinstance(result, (bool, int, float, str, bytes)):
        return result, result
    raise _Unkeyable(f"unstorable result type: {type(result).__name__}")


def _thaw_result(stored, shape_args: list):
    """Produce a fresh, independent reconstruction of a stored result, with its
    attributes replayed against this call's arguments."""
    if isinstance(stored, tuple) and stored and stored[0] == "seq":
        _, seq_type, items = stored
        return seq_type(_thaw_result(item, shape_args) for item in items)
    if isinstance(stored, _StoredShape):
        return _thaw_stored_shape(stored, shape_args)
    return stored


def _rewrapped(shape, topods):
    """A wrapper sharing ``shape``'s attributes over a different TopoDS."""
    clone = object.__new__(type(shape))
    clone.__dict__.update(shape.__dict__)
    clone.wrapped = _downcast(topods)
    return clone


def _protect_inputs(op_name: str, args: tuple, kwargs: dict, *, is_classmethod: bool):
    """The arguments a MISS runs the real op on, arranged so it leaves the
    caller's objects in the same state a HIT does.

    A hit never runs OCCT, so the inputs come back untouched. A miss runs the
    real op, and OCCT algorithms modify their INPUT sub-shapes in place
    (booleans bump tool tolerances, ``hollow``/``extrude``/``make_loft`` fix up
    what they consume). A model that feeds a solid to a boolean as a tool and
    ALSO emits that solid as its own part — the juno cores, cut out of their
    shells — therefore serialized different component bytes on a cold run than
    on a warm one, and the tree hash changed with the cache state.

    - Booleans: the operands and tools run as exact copies
      (``BRepBuilderAPI_Copy``); ``self`` is passed as given because the op
      copies its attributes onto the result and never rewrites its geometry.
      NOT ``SetNonDestructive``: that flag does not merely protect the inputs,
      it changes the RESULT. A ring with two bosses fused on tangentially, then
      bored and halved, is a valid solid destructively and an invalid,
      self-intersecting one non-destructively (the w16 rod caps, every one of
      them, under ``inspect validate``). Copying costs a fraction of the
      boolean it precedes and leaves OCCT running the algorithm it was
      validated with.
    - Every other op runs on exact copies (``BRepBuilderAPI_Copy``). An
      instance op's other shape arguments are sub-shapes of ``self`` (the
      edges to fillet, the faces to hollow), so they are mapped THROUGH the
      copier onto the copy — a standalone copy would orphan them. A shape the
      copier does not know is foreign to ``self`` and is passed as given, so
      the op fails exactly as it would un-memoized. Factory classmethods take
      standalone profiles, copied one by one.

    Uniform rather than probe-based (fillet and chamfer happened not to modify
    their inputs on OCCT 7.8) so the guarantee does not rot with a kernel
    upgrade; the copy is a small fraction of the op it precedes, and only a
    miss pays it."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

    if op_name == "bool_op":

        def copied(value):
            if _is_shape(value):
                return _rewrapped(value, BRepBuilderAPI_Copy(value.wrapped).Shape())
            if isinstance(value, (list, tuple)):
                return type(value)(copied(item) for item in value)
            return value

        # (self, args, tools, operation): self stays, the operand and tool
        # iterables are copied element by element, the OCCT builder passes through.
        return (args[0], *(copied(arg) for arg in args[1:])), {k: copied(v) for k, v in kwargs.items()}

    if is_classmethod:

        def protect(value):
            if _is_shape(value):
                return _rewrapped(value, BRepBuilderAPI_Copy(value.wrapped).Shape())
            if isinstance(value, (list, tuple)):
                return type(value)(protect(item) for item in value)
            return value

        return (args[0], *(protect(arg) for arg in args[1:])), {k: protect(v) for k, v in kwargs.items()}

    owner = args[0]
    if not _is_shape(owner):
        return args, kwargs
    copier = BRepBuilderAPI_Copy(owner.wrapped)

    def protect(value):
        if _is_shape(value):
            mapped = copier.ModifiedShape(value.wrapped)
            return value if mapped.IsNull() else _rewrapped(value, mapped)
        if isinstance(value, (list, tuple)):
            return type(value)(protect(item) for item in value)
        return value

    return (
        (_rewrapped(owner, copier.Shape()), *(protect(arg) for arg in args[1:])),
        {k: protect(v) for k, v in kwargs.items()},
    )


def _memoized(op_name: str, fn, *, is_classmethod: bool):
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not _enabled():
            return fn(*args, **kwargs)
        try:
            # For classmethods, `cls` identifies the constructed type and must
            # be part of the key but not hashed as a shape.
            key_args = ((args[0].__name__,) + args[1:]) if is_classmethod else args
            key = _build_key(op_name, key_args, kwargs)
            shape_args = _shape_args(key_args, kwargs)
        except _Unkeyable:
            _stats["unkeyable"] += 1
            return fn(*args, **kwargs)
        except Exception:
            _stats["errors"] += 1
            return fn(*args, **kwargs)

        cached = _lookup(key)
        if cached is not None:
            try:
                value = _thaw_result(cached, shape_args)
            except Exception:
                # An entry this process cannot replay (foreign class, shape
                # count drift) is treated as a miss and overwritten below.
                _stats["errors"] += 1
            else:
                _stats["hits"] += 1
                return value

        try:
            run_args, run_kwargs = _protect_inputs(op_name, args, kwargs, is_classmethod=is_classmethod)
        except Exception:
            _stats["errors"] += 1
            run_args, run_kwargs = args, kwargs
        result = fn(*run_args, **run_kwargs)
        _stats["misses"] += 1
        try:
            stored, first_value = _freeze_result_for_first_consumer(result, shape_args)
        except _Unkeyable:
            _stats["unstorable"] += 1
            return result
        except Exception:
            _stats["errors"] += 1
            return result
        _store(key, stored)
        # The caller gets the same canonical reconstruction a future hit
        # would. It is the ephemeral BREP read already verified while freezing;
        # no live object enters either cache.
        return first_value

    wrapper.__op_memo__ = True
    return wrapper


# (class, attribute, op label). Instance methods and classmethods listed
# separately because classmethod rebinding differs.
_INSTANCE_TARGETS = (
    ("Shape", "_bool_op", "bool_op"),
    ("Mixin3D", "fillet", "fillet"),
    ("Mixin3D", "chamfer", "chamfer"),
    ("Mixin3D", "shell", "shell"),
    ("Mixin3D", "offset_3d", "offset_3d"),
    ("Mixin3D", "hollow", "hollow"),
)
_CLASSMETHOD_TARGETS = (
    ("Face", "make_surface", "face.make_surface"),
    ("Face", "make_surface_from_curves", "face.make_surface_from_curves"),
    ("Face", "make_surface_from_array_of_points", "face.make_surface_from_points"),
    ("Face", "make_bezier_surface", "face.make_bezier_surface"),
    ("Face", "revolve", "face.revolve"),
    ("Face", "sweep", "face.sweep"),
    ("Solid", "make_loft", "solid.make_loft"),
    ("Solid", "extrude", "solid.extrude"),
    ("Solid", "revolve", "solid.revolve"),
    ("Solid", "sweep", "solid.sweep"),
    ("Solid", "sweep_multi", "solid.sweep_multi"),
    ("Solid", "extrude_taper", "solid.extrude_taper"),
    ("Solid", "extrude_linear_with_rotation", "solid.extrude_rot"),
    ("Solid", "thicken", "solid.thicken"),
    ("Wire", "make_convex_hull", "wire.make_convex_hull"),
    ("Wire", "offset_2d", "wire.offset_2d"),
    ("Wire", "fillet_2d", "wire.fillet_2d"),
    ("Wire", "chamfer_2d", "wire.chamfer_2d"),
)


# --- sub-shape identity ------------------------------------------------------
#
# The memo's reconstructions give untouched sub-shapes new TShapes, so the
# pointer identity build123d compares by no longer survives an op (module
# docstring). These replace ``Shape.is_same``/``__eq__``/``__hash__`` with
# geometric identity: the pointer check first, the signature on a mismatch.
# Vertex keeps determinism.py's hash, which calls the same live signature hash
# below so native edits and nearly coincident vertices agree with ``__eq__``.

_SIGNATURE_DECIMALS = 6


@lru_cache(maxsize=8192)
def _rounded_coordinate_bytes(bits: bytes) -> tuple[float, float, float]:
    """Bounded pure numeric work; keys contain no shape, pointer or signature."""
    x, y, z = struct.unpack("<ddd", bits)
    return round(x, _SIGNATURE_DECIMALS), round(y, _SIGNATURE_DECIMALS), round(z, _SIGNATURE_DECIMALS)


def _rounded_coordinates(coordinates: tuple) -> tuple[float, float, float]:
    """Round freshly read coordinates, preserving signed zero and NaNs.

    Native vertices/surfaces are always read again. Only rounding their exact
    immutable IEEE754 values is memoized. Packed keys distinguish +0 and -0;
    NaNs bypass the cache so tuple identity cannot change NaN equality.
    """
    x, y, z = coordinates
    if type(x) is not float or type(y) is not float or type(z) is not float:
        # A numeric subclass may implement __round__ differently from its
        # conversion to IEEE754. Preserve those callbacks on the ordinary path.
        return round(x, _SIGNATURE_DECIMALS), round(y, _SIGNATURE_DECIMALS), round(z, _SIGNATURE_DECIMALS)
    if x != x or y != y or z != z:
        return round(x, _SIGNATURE_DECIMALS), round(y, _SIGNATURE_DECIMALS), round(z, _SIGNATURE_DECIMALS)
    return _rounded_coordinate_bytes(struct.pack("<ddd", x, y, z))


def _signature(wrapped) -> tuple:
    """World-space geometric signature of a TopoDS_Shape (module docstring).

    ``(shape type, (vertices, edges, faces), sorted vertex points, sorted
    sample points)``, every coordinate rounded to ``_SIGNATURE_DECIMALS``. The
    samples are the mid-parameter point of each face's surface, or of each
    edge's curve when the shape has no faces: the vertices fix a shape's
    corners, the samples fix what runs between them (an arc and its chord,
    a plane and a bulge share vertices and nothing else). ``BRepAdaptor``
    evaluates in world coordinates, location applied, so two expressions of
    the same geometry sign identically however their locations are split.

    Only immutable OCCT callables are reused. A signature is always computed
    from the shape's current geometry: a TShape can change between the
    builder's pre/post selections, even within one ``_add_to_context`` call.
    """
    return _signature_evaluator()(wrapped)


def _signature_hash(wrapped) -> int:
    """A cheap hash consistent with full geometric equality.

    Equal signatures necessarily have the same type and rounded vertex points.
    Hashing those fields avoids evaluating every curve/surface merely to put a
    shape in a builder's set. An arc and its chord may collide here; ``is_same``
    still compares their complete signatures, so a collision cannot substitute
    geometry. Read current vertices on every call: no mutable shape is memoized.
    """
    return _signature_hash_evaluator()(wrapped)


@lru_cache(maxsize=1)
def _signature_hash_evaluator():
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    vertex_kind = TopAbs_ShapeEnum.TopAbs_VERTEX
    vertex_point, as_vertex = BRep_Tool.Pnt_s, TopoDS.Vertex_s
    map_shapes = TopExp.MapShapes_s
    def rounded(vertex):
        return _rounded_coordinates(vertex_point(as_vertex(vertex)).Coord())

    def signature_hash(wrapped):
        kind = wrapped.ShapeType()
        if kind == vertex_kind:
            points = (rounded(wrapped),)
        else:
            vertices = TopTools_IndexedMapOfShape()
            map_shapes(wrapped, vertex_kind, vertices)
            points = tuple(sorted(rounded(vertices.FindKey(i)) for i in range(1, vertices.Extent() + 1)))
        return hash((int(kind), points))

    return signature_hash


@lru_cache(maxsize=1)
def _signature_evaluator():
    """Bind the kernel lazily, without retaining any shape or signature.

    OCCT's topology hierarchy fixes the trivial searches: a vertex contains
    itself; an edge contains itself and vertices; a wire contains edges; a
    face contains itself, wires, edges and vertices. Skipping the impossible
    descendants and singleton maps preserves the full signature, including
    unique vertices/edges on seams, closed curves and degenerate edges. The
    larger containers still use OCCT's maps rather than assuming manifold
    topology or a fixed number of descendants.
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape

    vertex_kind = TopAbs_ShapeEnum.TopAbs_VERTEX
    edge_kind = TopAbs_ShapeEnum.TopAbs_EDGE
    wire_kind = TopAbs_ShapeEnum.TopAbs_WIRE
    face_kind = TopAbs_ShapeEnum.TopAbs_FACE
    map_shapes = TopExp.MapShapes_s
    vertex_point = BRep_Tool.Pnt_s
    is_degenerate = BRep_Tool.Degenerated_s
    as_vertex = TopoDS.Vertex_s
    as_edge = TopoDS.Edge_s
    as_face = TopoDS.Face_s
    def rounded(point) -> tuple:
        return _rounded_coordinates(point.Coord())

    def sub_shapes(wrapped, kind):
        found = TopTools_IndexedMapOfShape()
        map_shapes(wrapped, kind, found)
        return found

    def signature(wrapped) -> tuple:
        kind = wrapped.ShapeType()
        if kind == vertex_kind:
            return (int(kind), (1, 0, 0), (rounded(vertex_point(as_vertex(wrapped))),), ())

        vertices = sub_shapes(wrapped, vertex_kind)
        vertex_count = vertices.Extent()
        points = sorted(
            rounded(vertex_point(as_vertex(vertices.FindKey(i))))
            for i in range(1, vertex_count + 1)
        )

        if kind == edge_kind:
            edge_count, faces = 1, ()
        else:
            edges = sub_shapes(wrapped, edge_kind)
            edge_count = edges.Extent()
            if kind == wire_kind:
                faces = ()
            elif kind == face_kind:
                faces = (wrapped,)
            else:
                face_map = sub_shapes(wrapped, face_kind)
                faces = tuple(face_map.FindKey(i) for i in range(1, face_map.Extent() + 1))

        samples = []
        if faces:
            for face in faces:
                surface = BRepAdaptor_Surface(as_face(face))
                samples.append(rounded(surface.Value(
                    (surface.FirstUParameter() + surface.LastUParameter()) / 2,
                    (surface.FirstVParameter() + surface.LastVParameter()) / 2,
                )))
        else:
            sample_edges = (wrapped,) if kind == edge_kind else (
                edges.FindKey(i) for i in range(1, edge_count + 1)
            )
            for edge in sample_edges:
                edge = as_edge(edge)
                if is_degenerate(edge):
                    continue
                curve = BRepAdaptor_Curve(edge)
                samples.append(rounded(curve.Value(
                    (curve.FirstParameter() + curve.LastParameter()) / 2
                )))
        return (int(kind), (vertex_count, edge_count, len(faces)), tuple(points), tuple(sorted(samples)))

    return signature


def _identity(attr: str, original):
    """One identity method, passing through to build123d's when disabled."""
    import functools

    def is_same(self, other) -> bool:
        if not _enabled():
            return original(self, other)
        if self._wrapped is None or not other:
            return False
        mine, theirs = self.wrapped, other.wrapped
        if mine.IsSame(theirs):
            return True
        if mine.ShapeType() != theirs.ShapeType():
            return False
        try:
            return _signature(mine) == _signature(theirs)
        except Exception:  # a shape that will not evaluate is only itself
            return False

    def eq(self, other):
        if not _enabled():
            return original(self, other)
        from build123d.topology import Shape

        if isinstance(other, Shape):
            return self.is_same(other)
        return NotImplemented

    def hash_(self) -> int:
        if self._wrapped is None:
            return 0
        if not _enabled():
            return original(self)
        try:
            return _signature_hash(self.wrapped)
        except Exception:
            return hash(self.wrapped)

    method = {"is_same": is_same, "__eq__": eq, "__hash__": hash_}[attr]
    functools.update_wrapper(method, original)
    method.__op_memo__ = True
    return method


_IDENTITY_TARGETS = ("is_same", "__eq__", "__hash__")


def install() -> bool:
    """Idempotently patch the build123d choke points. Returns installed-now."""
    global _installed
    with _lock:
        # Install even when CADGEN_OP_MEMO=0: the wrapper passes through when
        # disabled, and installing unconditionally keeps in-process toggling
        # (tests, validation runs) honest.
        if _installed:
            return False
        import inspect

        from build123d import topology

        for cls_name, attr, label in _INSTANCE_TARGETS:
            cls = getattr(topology, cls_name, None)
            fn = None if cls is None else inspect.getattr_static(cls, attr, None)
            if fn is None or getattr(fn, "__op_memo__", False):
                continue
            setattr(cls, attr, _memoized(label, fn, is_classmethod=False))

        for cls_name, attr, label in _CLASSMETHOD_TARGETS:
            cls = getattr(topology, cls_name, None)
            static = None if cls is None else inspect.getattr_static(cls, attr, None)
            if static is None or not isinstance(static, classmethod):
                continue
            fn = static.__func__
            if getattr(fn, "__op_memo__", False):
                continue
            setattr(cls, attr, classmethod(_memoized(label, fn, is_classmethod=True)))

        for attr in _IDENTITY_TARGETS:
            fn = inspect.getattr_static(topology.Shape, attr, None)
            if fn is None or getattr(fn, "__op_memo__", False):
                continue
            setattr(topology.Shape, attr, _identity(attr, fn))

        _installed = True
        return True


def uninstall() -> bool:
    """Restore every build123d attribute ``install()`` replaced. Returns
    uninstalled-now. The caches are left alone (``clear()`` empties them)."""
    global _installed
    with _lock:
        if not _installed:
            return False
        import inspect

        from build123d import topology

        for cls_name, attr, _label in _INSTANCE_TARGETS + _CLASSMETHOD_TARGETS:
            cls = getattr(topology, cls_name, None)
            static = None if cls is None else inspect.getattr_static(cls, attr, None)
            fn = static.__func__ if isinstance(static, classmethod) else static
            if fn is None or not getattr(fn, "__op_memo__", False):
                continue
            original = fn.__wrapped__
            setattr(cls, attr, classmethod(original) if isinstance(static, classmethod) else original)

        for attr in _IDENTITY_TARGETS:
            fn = inspect.getattr_static(topology.Shape, attr, None)
            if fn is not None and getattr(fn, "__op_memo__", False):
                setattr(topology.Shape, attr, fn.__wrapped__)

        _installed = False
        return True


def stats() -> dict:
    with _lock:
        return dict(_stats, entries=len(_cache))


def clear() -> None:
    with _lock:
        _cache.clear()
        _rounded_coordinate_bytes.cache_clear()
