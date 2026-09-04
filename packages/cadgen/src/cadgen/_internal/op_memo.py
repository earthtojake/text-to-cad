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
- Keys hash input shapes by their BinTools BREP bytes: location-stripped bytes
  memoized per TShape, combined with the shape's location matrix. Fresh
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

Kill switch: ``CADGEN_OP_MEMO=0`` (and ``CADGEN_OP_MEMO_DISK=0`` for just the
disk tier).

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

from cadgen._internal.atomic_replace import replace_atomic

# Salt: bump _OP_MEMO_VERSION whenever keying or hit semantics change.
_OP_MEMO_VERSION = 3

_lock = threading.RLock()
_cache: OrderedDict[tuple, object] = OrderedDict()
# Digest per TShape, so a shape that is an input to several ops serializes once.
# BOUNDED and LRU, not "clear when huge": the keys are strong references to
# OCCT TShapes, so every entry keeps a whole solid alive. Unbounded (it cleared
# only past 4x the result cache, 131072 entries) it pinned every intermediate
# boolean result of a 1400-part engine for the run's lifetime -- one input to
# a process the OS killed at 200+ GB. Recent shapes are the ones re-hashed; a
# miss costs one BinTools write.
_TSHAPE_DIGEST_CAPACITY = 2048
_tshape_bytes_memo: OrderedDict[object, str] = OrderedDict()
# NOTE: an earlier revision stamped op-result TShapes with their producing
# key so chained inputs could key without serialization. It destabilized
# keys on movement-class models (1444 re-misses per warm run vs ~25
# without): stamps assume a result's content never changes after return,
# and real pipelines violate that. Digest keying keys the actual
# first-seen content of every TShape, which is what stays stable.
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
    """Location-stripped BREP digest of a TopoDS_Shape, memoized per TShape."""
    from OCP.BinTools import BinTools
    from OCP.TopLoc import TopLoc_Location

    tshape = wrapped.TShape()
    cached = _tshape_bytes_memo.get(tshape)
    if cached is not None:
        _tshape_bytes_memo.move_to_end(tshape)
        return cached
    stream = io.BytesIO()
    BinTools.Write_s(wrapped.Located(TopLoc_Location()), stream)
    digest = hashlib.sha256(stream.getvalue()).hexdigest()
    _tshape_bytes_memo[tshape] = digest
    while len(_tshape_bytes_memo) > _TSHAPE_DIGEST_CAPACITY:
        _tshape_bytes_memo.popitem(last=False)
    return digest


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


def _store(key: tuple, result: object) -> None:
    with _lock:
        _cache[key] = result
        _cache.move_to_end(key)
        capacity = _capacity()
        while len(_cache) > capacity:
            _cache.popitem(last=False)
    _disk_put(key, result)


def _lookup(key: tuple):
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    stored = _disk_get(key)
    if stored is not None:
        with _lock:
            _cache[key] = stored
            _cache.move_to_end(key)
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


def _op_index_key(key: tuple) -> str:
    """The op-memo entry key: the op key plus the memo scheme and the kernel
    version, so a changed scheme or build123d simply misses (no salted
    directories to sweep)."""
    import build123d

    scheme = f"v{_OP_MEMO_VERSION}-b123d{getattr(build123d, '__version__', 'unknown')}"
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
    # A build123d Shape: has a TopoDS under `wrapped`. Vector/Axis/Location also
    # carry a `wrapped` (gp_*), and must not count — they have no `_wrapped`.
    return hasattr(value, "_wrapped") and getattr(value, "_wrapped", None) is not None


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
    if isinstance(result, (tuple, list)):
        return ("seq", type(result), tuple(_freeze_result(r, shape_args) for r in result))
    if _is_shape(result):
        data = _write_brep(result.wrapped)
        # Prove the bytes read back before anything is stored.
        reconstruction = _read_brep(data)
        recipe = _attribute_recipe(result, shape_args, reconstruction)
        return _StoredShape(_class_path(type(result)), data, recipe)
    if result is None or isinstance(result, (bool, int, float, str, bytes)):
        return result
    raise _Unkeyable(f"unstorable result type: {type(result).__name__}")


def _thaw_result(stored, shape_args: list):
    """Produce a fresh, independent reconstruction of a stored result, with its
    attributes replayed against this call's arguments."""
    if isinstance(stored, tuple) and stored and stored[0] == "seq":
        _, seq_type, items = stored
        return seq_type(_thaw_result(item, shape_args) for item in items)
    if isinstance(stored, _StoredShape):
        cls = _resolve_shape_class(stored.cls_path)
        clone = cls(_downcast(_read_brep(stored.brep)))
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
    on a warm one, and the package hash changed with the cache state.

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
            stored = _freeze_result(result, shape_args)
        except _Unkeyable:
            _stats["unstorable"] += 1
            return result
        except Exception:
            _stats["errors"] += 1
            return result
        _store(key, stored)
        # The caller gets the same canonical reconstruction a future hit
        # would: package output must not depend on cache state.
        try:
            return _thaw_result(stored, shape_args)
        except Exception:
            _stats["errors"] += 1
            return result

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

        _installed = True
        return True


def stats() -> dict:
    with _lock:
        return dict(_stats, entries=len(_cache))


def clear() -> None:
    with _lock:
        _cache.clear()
        _tshape_bytes_memo.clear()

