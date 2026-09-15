"""Optional reuse of pure, parameterized intermediate CAD computations.

``@memo`` does not declare an output or a model. Unsupported Python and
calls inside an existing builder execute normally. Eligible calls use the
store's operation index and receive private canonical shape reconstructions.
No kernel is imported by importing or applying the decorator.

The decorator declares purity: deterministic geometry from keyed immutable
inputs, globals and helpers under an unmodified dependency runtime, with no
externally observable side effects. Eligibility checks and runtime witnesses
are conservative defenses, not a purity proof or Python security sandbox.
"""

from __future__ import annotations

import builtins
import dis
import enum
import functools
import hashlib
import inspect
import marshal
import math
import os
import struct
import types
from collections import OrderedDict

__all__ = ["memo"]

_SCHEME = 1
_CODE_LIMIT = 256
_CODE_BYTES_LIMIT = 1 << 20
_code_cache: OrderedDict[types.CodeType, tuple] = OrderedDict()
_code_bytes = 0
_trusted = None
_reuse_trusted = False
_stats = {"hits": 0, "misses": 0, "declined": 0, "unstorable": 0}

# A small geometry vocabulary, not the complete build123d export surface:
# readers, exporters, Text/font access, joints and arbitrary callbacks are out.
_CAD_NAMES = frozenset("""
Box Cylinder Sphere Cone Torus Wedge BuildPart BuildSketch BuildLine
Locations GridLocations PolarLocations Pos Rot Location Vector Plane Axis
Align Mode Select SortBy GeomType Solid Part Sketch Face Wire Edge Vertex
Compound Rectangle Circle Polygon Polyline Line ThreePointArc RadiusArc
CenterArc Spline RegularPolygon SlotOverall SlotCenterToCenter
extrude revolve loft sweep fillet chamfer offset mirror add make_face
""".split())
_CAD_ATTRIBUTES = frozenset("""
faces edges vertices solids wires sort_by filter_by filter_by_position group_by
moved located cut fuse intersect fillet chamfer extrude make_box make_cylinder
make_cone make_sphere make_torus make_loft sweep revolve center normal_at
tangent_at position_at to_tuple bounding_box volume area length radius
part sketch line face edge wire solid vertex center_location position orientation
origin x_dir y_dir z_dir X Y Z XY XZ YZ YX ZX ZY CENTER MIN MAX ADD SUBTRACT
INTERSECT PRIVATE REPLACE ALL LAST NEW REVERSED FORWARD RECTANGLE CIRCLE
CYLINDER PLANE LINE BSPLINE append extend pop
""".split())
_MATH_NAMES = frozenset("""
pi tau e inf nan sin cos tan asin acos atan atan2 sqrt hypot floor ceil trunc
fabs fmod remainder copysign radians degrees exp expm1 log log1p log2 log10
isfinite isinf isnan isclose pow prod fsum dist
""".split())
_BUILTINS = {name: getattr(builtins, name) for name in (
    "abs", "all", "any", "bool", "enumerate", "float", "int", "len", "list",
    "max", "min", "range", "round", "sorted", "sum", "tuple", "zip",
)}
_OPCODES = frozenset("""
RESUME CACHE NOP EXTENDED_ARG PUSH_NULL POP_TOP COPY SWAP
LOAD_CONST LOAD_FAST LOAD_FAST_CHECK LOAD_FAST_AND_CLEAR LOAD_FAST_LOAD_FAST
STORE_FAST STORE_FAST_LOAD_FAST STORE_FAST_STORE_FAST DELETE_FAST
LOAD_GLOBAL LOAD_DEREF LOAD_CLOSURE COPY_FREE_VARS MAKE_CELL
LOAD_ATTR LOAD_METHOD
CALL CALL_KW CALL_FUNCTION CALL_FUNCTION_KW CALL_METHOD CALL_FUNCTION_EX
PRECALL KW_NAMES RETURN_VALUE RETURN_CONST
UNARY_POSITIVE UNARY_NEGATIVE UNARY_NOT UNARY_INVERT TO_BOOL
BINARY_OP BINARY_SUBSCR BINARY_SLICE STORE_SUBSCR DELETE_SUBSCR
BUILD_TUPLE BUILD_LIST BUILD_SET BUILD_MAP BUILD_CONST_KEY_MAP BUILD_SLICE
LIST_APPEND LIST_EXTEND SET_ADD SET_UPDATE MAP_ADD DICT_UPDATE DICT_MERGE
UNPACK_SEQUENCE UNPACK_EX GET_ITER FOR_ITER END_FOR
JUMP_FORWARD JUMP_BACKWARD JUMP_BACKWARD_NO_INTERRUPT
POP_JUMP_IF_TRUE POP_JUMP_IF_FALSE POP_JUMP_IF_NONE POP_JUMP_IF_NOT_NONE
POP_JUMP_FORWARD_IF_TRUE POP_JUMP_FORWARD_IF_FALSE
POP_JUMP_FORWARD_IF_NONE POP_JUMP_FORWARD_IF_NOT_NONE
POP_JUMP_BACKWARD_IF_TRUE POP_JUMP_BACKWARD_IF_FALSE
POP_JUMP_BACKWARD_IF_NONE POP_JUMP_BACKWARD_IF_NOT_NONE
JUMP_IF_TRUE_OR_POP JUMP_IF_FALSE_OR_POP COMPARE_OP CONTAINS_OP
BEFORE_WITH WITH_EXCEPT_START PUSH_EXC_INFO POP_EXCEPT RERAISE
""".split())


class _Decline(Exception):
    pass


def _literal(value):
    """Only exact builtins: coercing a subclass can execute an unknown method."""
    kind = type(value)
    if value is None or kind in (bool, int, str, bytes):
        return (kind.__name__, value)
    if kind is float:
        if not math.isfinite(value):
            raise _Decline("nonfinite input")
        return ("float", struct.pack("!d", value))
    if kind is tuple:
        return ("tuple", tuple(_literal(item) for item in value))
    raise _Decline("mutable or protocol-bearing input")


def _stamp(value, depth=0, memo=None):
    """Compare trusted descriptors without invoking their protocols."""
    kind = type(value)
    if depth > 16:
        raise _Decline("oversized or cyclic trusted descriptor")
    if value is None or kind in (bool, int, float, str, bytes):
        if kind is float:
            return ("float", struct.pack("!d", value))
        return _literal(value)
    key = (id(value), depth)
    if memo is not None and key in memo:
        return memo[key]
    result = _compound_stamp(value, kind, depth, memo)
    if memo is not None:
        memo[key] = result
    return result


def _compound_stamp(value, kind, depth, memo):
    if kind is types.FunctionType:
        return (id(value), value.__code__, _stamp(value.__defaults__, 1, memo),
                _stamp(value.__kwdefaults__, 1, memo),
                tuple(_stamp(cell.cell_contents, depth + 1, memo)
                      for cell in value.__closure__ or ()))
    if kind in (staticmethod, classmethod):
        return (kind, _stamp(value.__func__, depth + 1, memo))
    if kind is property:
        return (kind, _stamp(value.fget, memo=memo), _stamp(value.fset, memo=memo), _stamp(value.fdel, memo=memo))
    if kind in (tuple, list):
        return (kind, tuple(_stamp(item, depth + 1, memo) for item in value))
    if kind is dict:
        return (kind, tuple((id(key), _stamp(item, depth + 1, memo)) for key, item in value.items()))
    if enum.Enum in type.__getattribute__(kind, "__mro__"):
        return (kind, id(value), _stamp(object.__getattribute__(value, "__dict__"), depth + 1, memo))
    return (kind, id(value))


def _class_stamp(cls, memo=None):
    return (type.__getattribute__(cls, "__mro__"),
            tuple((name, _stamp(value, memo=memo)) for name, value in
                  type.__getattribute__(cls, "__dict__").items()))


def _matches(value, expected, depth, memo):
    """Compare in place; do not allocate a new whole-runtime fingerprint."""
    if depth > 16:
        return False
    kind = type(value)
    if value is None or kind in (bool, int, float, str, bytes):
        return (expected[0] == kind.__name__ and
                (struct.pack("!d", value) if kind is float else value) == expected[1])
    key = (id(value), id(expected))
    if key in memo:
        return memo[key]
    result = _compound_matches(value, kind, expected, depth, memo)
    memo[key] = result
    return result


def _compound_matches(value, kind, expected, depth, memo):
    if kind is types.FunctionType:
        cells = value.__closure__ or ()
        return (expected[0] == id(value) and value.__code__ is expected[1]
                and _matches(value.__defaults__, expected[2], 1, memo)
                and _matches(value.__kwdefaults__, expected[3], 1, memo)
                and len(cells) == len(expected[4])
                and all(_matches(cell.cell_contents, item, depth + 1, memo)
                        for cell, item in zip(cells, expected[4])))
    if expected[0] is not kind:
        return False
    if kind in (staticmethod, classmethod):
        return _matches(value.__func__, expected[1], depth + 1, memo)
    if kind is property:
        return (_matches(value.fget, expected[1], 0, memo)
                and _matches(value.fset, expected[2], 0, memo)
                and _matches(value.fdel, expected[3], 0, memo))
    if kind in (tuple, list):
        return (len(value) == len(expected[1]) and
                all(_matches(item, stamp, depth + 1, memo)
                    for item, stamp in zip(value, expected[1])))
    if kind is dict:
        return (len(value) == len(expected[1]) and
                all(id(key) == key_id and _matches(item, stamp, depth + 1, memo)
                    for (key, item), (key_id, stamp) in zip(value.items(), expected[1])))
    if enum.Enum in type.__getattribute__(kind, "__mro__"):
        return (id(value) == expected[1] and
                _matches(object.__getattribute__(value, "__dict__"), expected[2], depth + 1, memo))
    return id(value) == expected[1]


def _class_matches(cls, expected, memo):
    members = type.__getattribute__(cls, "__dict__")
    return (type.__getattribute__(cls, "__mro__") is expected[0]
            and len(members) == len(expected[1])
            and all(name == saved_name and _matches(value, stamp, 0, memo)
                    for (name, value), (saved_name, stamp) in zip(members.items(), expected[1])))


def _native_defaults(values, kinds):
    """Find retained geometry values without traversing arbitrary objects."""
    found = {}
    visited = set()

    def visit(value, depth=0):
        if id(value) in visited or depth > 8:
            return
        visited.add(id(value))
        kind = type(value)
        if kind in kinds:
            found[id(value)] = value
        elif kind is types.FunctionType:
            visit(value.__defaults__, depth + 1)
            visit(value.__kwdefaults__, depth + 1)
            for cell in value.__closure__ or ():
                visit(cell.cell_contents, depth + 1)
        elif kind in (staticmethod, classmethod):
            visit(value.__func__, depth + 1)
        elif kind is property:
            for fn in (value.fget, value.fset, value.fdel):
                visit(fn, depth + 1)
        elif kind in (tuple, list):
            for item in value:
                visit(item, depth + 1)
        elif kind is dict:
            for item in value.values():
                visit(item, depth + 1)

    for value in values:
        visit(value)
    return tuple(found.values())


def install(*, trusted_worker: bool = False) -> bool:
    """Snapshot the closed runtime interface once, before any authored code.

    Only fresh daemon/transient worker bootstrap may establish reuse trust.
    A generic runner/embedding caller might already have executed authored
    module initialization; its snapshot permits canonical returns, never reuse.
    Repeated calls cannot promote a previous snapshot to trusted.
    """
    global _trusted, _reuse_trusted
    if _trusted is not None:
        return False
    from cadgen._internal import op_memo, determinism
    op_memo.install()
    determinism.install()
    import build123d as bd
    import cadgen.build123d as proxy
    # Lazy-child/reference construction is another cadgen-owned kernel patch.
    # Capture its final constructor before any authored source runs.
    import cadgen.store.lazy  # noqa: F401
    import math
    from build123d.build_common import Builder, LocationList, WorkplaneList

    cad = {name: getattr(bd, name) for name in _CAD_NAMES if hasattr(bd, name)}
    maths = {name: getattr(math, name) for name in _MATH_NAMES}
    classes = {base for value in cad.values() if isinstance(value, type)
               for base in value.__mro__ if base is not object}
    # Operators can return these intermediary container classes; their implicit
    # sequence and context protocols must be covered too.
    from build123d.topology import ShapeList
    from build123d.geometry import BoundBox
    classes.update((ShapeList, BoundBox, Builder, LocationList, WorkplaneList))
    classes.update(base for cls in tuple(classes) for base in type(cls).__mro__ if base is not object)
    from cadgen._internal.op_memo import _normalize
    native_values = _native_defaults(
        [*cad.values(), *(value for cls in classes for value in vars(cls).values())],
        {bd.Vector, bd.Axis, bd.Plane, bd.Location, bd.Pos, bd.Rot},
    )
    memo = {}
    _trusted = (bd, math, cad, maths,
                tuple((cls, _class_stamp(cls, memo)) for cls in classes),
                tuple((value, _stamp(value, memo=memo)) for value in (*cad.values(), *maths.values())),
                (Builder._current, LocationList._current, WorkplaneList._current),
                proxy, _stamp(vars(proxy).get("__getattr__"), memo=memo),
                tuple((value, _normalize(value)) for value in native_values))
    _reuse_trusted = bool(trusted_worker)
    return True


def _runtime_eligible() -> bool:
    try:
        return _check_runtime()
    except Exception:
        # A modified descriptor/default may no longer be readable. The
        # optional guard must not introduce an exception ahead of the body.
        return False


def _check_runtime() -> bool:
    if _trusted is None:
        return False
    bd, math, cad, maths, classes, values, contexts, proxy, proxy_getattr, native_values = _trusted
    memo = {}
    if not _matches(vars(proxy).get("__getattr__"), proxy_getattr, 0, memo):
        return False
    if any(vars(bd).get(name) is not value for name, value in cad.items()):
        return False
    if any(vars(math).get(name) is not value for name, value in maths.items()):
        return False
    if any(not _class_matches(cls, stamp, memo) for cls, stamp in classes):
        return False
    if any(context.get(None) is not None for context in contexts):
        return False
    if any(not _matches(value, stamp, 0, memo) for value, stamp in values):
        return False
    from cadgen._internal.op_memo import _normalize
    return all(_normalize(value) == stamp for value, stamp in native_values)


def _code_recipe(code):
    global _code_bytes
    if code in _code_cache:
        _code_cache.move_to_end(code)
        return _code_cache[code][0]
    if code.co_flags & (inspect.CO_GENERATOR | inspect.CO_COROUTINE | inspect.CO_ASYNC_GENERATOR):
        raise _Decline("generator or coroutine")
    names = set()
    attrs = set()
    for instruction in dis.get_instructions(code):
        if instruction.opname not in _OPCODES:
            raise _Decline(instruction.opname)
        if instruction.opname == "LOAD_GLOBAL":
            names.add(instruction.argval)
        elif instruction.opname in ("LOAD_ATTR", "LOAD_METHOD"):
            attrs.add(instruction.argval)
    # Nested code can close over local mutable state or create callbacks. The
    # initial implementation deliberately leaves it to ordinary execution.
    if any(type(value) is types.CodeType for value in code.co_consts):
        raise _Decline("nested code")
    if attrs - (_CAD_NAMES | _CAD_ATTRIBUTES | _MATH_NAMES):
        raise _Decline("attribute outside the closed geometry vocabulary")
    data = marshal.dumps(code)
    if len(data) > _CODE_BYTES_LIMIT:
        raise _Decline("oversized function")
    recipe = (hashlib.sha256(data).hexdigest(), tuple(sorted(names)), tuple(sorted(attrs)))
    _code_cache[code] = (recipe, len(data))
    _code_bytes += len(data)
    while len(_code_cache) > _CODE_LIMIT or _code_bytes > _CODE_BYTES_LIMIT:
        _, (_, size) = _code_cache.popitem(last=False)
        _code_bytes -= size
    return recipe


def _function_key(fn, seen, files):
    if type(fn) is not types.FunctionType or getattr(fn, "__cadgen_model__", None) is not None:
        raise _Decline("not an ordinary helper")
    if type(fn.__globals__) is not dict or type(fn.__builtins__) is not dict:
        raise _Decline("custom globals or builtins mapping")
    if "__signature__" in vars(fn) or "__wrapped__" in vars(fn):
        raise _Decline("custom callable introspection")
    if id(fn) in seen or len(seen) >= 16:
        raise _Decline("recursive or oversized helper graph")
    seen.add(id(fn))
    try:
        digest, names, attrs = _code_recipe(fn.__code__)
        from cadgen.store import closure
        path = os.path.realpath(fn.__code__.co_filename)
        source_digest = (closure._ACTIVE_HASHES or {}).get(path)
        if source_digest is None:
            raise _Decline("source was not captured by this build")
        files.add(path)
        cells = dict(zip(fn.__code__.co_freevars, fn.__closure__ or ()))
        nonlocals = tuple((name, _literal(cell.cell_contents)) for name, cell in sorted(cells.items()))
        globals_key = []
        bd, math, cad, maths, _classes, _values, _contexts, proxy, _proxy_getattr, _native = _trusted
        for name in names:
            if name in fn.__globals__:
                value = fn.__globals__[name]
            elif name in fn.__builtins__:
                value = fn.__builtins__[name]
            else:
                raise _Decline("unbound global")
            try:
                item = _literal(value)
            except _Decline:
                if type(value) is types.ModuleType and value is math:
                    for attr in attrs:
                        if attr in vars(value) and vars(value)[attr] is not maths.get(attr):
                            raise _Decline("unknown or replaced math attribute")
                    item = ("math",)
                elif value is bd or value is proxy:
                    for attr in attrs:
                        if attr not in vars(value) and attr not in vars(bd):
                            continue
                        if attr not in cad or getattr(value, attr, None) is not cad[attr]:
                            raise _Decline("replaced CAD export")
                    item = ("build123d",)
                elif any(value is expected for expected in _BUILTINS.values()):
                    item = ("builtin", next(key for key, expected in _BUILTINS.items() if value is expected))
                elif any(value is expected for expected in cad.values()):
                    item = ("cad", next(key for key, expected in cad.items() if value is expected))
                elif any(value is expected for expected in maths.values()):
                    item = ("math", next(key for key, expected in maths.items() if value is expected))
                elif type(value) is types.FunctionType:
                    item = ("helper", _function_key(value, seen, files))
                else:
                    raise _Decline("unknown global")
            globals_key.append((name, item))
        defaults = _literal(fn.__defaults__)
        kwdefaults = tuple((key, _literal(value)) for key, value in sorted((fn.__kwdefaults__ or {}).items()))
        return (digest, source_digest, tuple(globals_key), nonlocals, defaults, kwdefaults)
    finally:
        seen.remove(id(fn))


def _read(key):
    from cadgen._internal import op_memo
    from cadgen.store.index import read_entry
    from cadgen.store.objects import read_verified_object

    entry = read_entry("op", key)
    if not entry or entry.get("memoScheme") != _SCHEME:
        return None
    try:
        data = read_verified_object(entry["object"])
        return op_memo._StoredShape(entry["cls"], data, entry["recipe"])
    except (KeyError, OSError, ValueError, TypeError):
        return None


def _write(key, stored):
    from cadgen.store.index import write_entry
    from cadgen.store.objects import put_object

    write_entry("op", key, {"memoScheme": _SCHEME,
                           "object": put_object(stored.brep, repair=True),
                           "cls": stored.cls_path, "recipe": stored.recipe})


def memo(func=None):
    """Declare a pure parameterized geometry factory for reuse during builds.

    Use ``@memo`` or ``@memo()`` on a helper returning a shape. It creates
    no files. The function must compute deterministic geometry from immutable
    arguments/globals/helpers under an unmodified dependency runtime, without
    externally observable side effects. This is an author contract, not an
    automatic purity proof. Expensive builder routines benefit most.

    Supported finite scalar/tuple inputs, local CAD operations, deterministic
    helpers and math can reuse results. Unsupported Python and ambient builders
    execute normally. ``CADGEN_MEMO_CACHE=0``
    disables result reuse while preserving eligible canonical return semantics.
    """
    if func is None:
        return memo
    if type(func) is not types.FunctionType:
        raise TypeError("@memo decorates an ordinary Python function")

    @functools.wraps(func)
    def call(*args, **kwargs):
        from cadgen.authoring import current_frame
        if current_frame() is None or not _runtime_eligible():
            _stats["declined"] += 1
            return func(*args, **kwargs)
        files = set()
        try:
            function_key = _function_key(func, set(), files)
            bound = inspect.signature(func, follow_wrapped=False).bind(*args, **kwargs)
            bound.apply_defaults()
            inputs = tuple((name, _literal(value)) for name, value in bound.arguments.items())
            from cadgen._internal import op_memo
            key = op_memo._op_index_key(("memo", _SCHEME, function_key, inputs))
        except (_Decline, ValueError, TypeError):
            _stats["declined"] += 1
            return func(*args, **kwargs)
        from cadgen._internal.source_hash import note_executed_files
        note_executed_files(files)
        enabled = (_reuse_trusted and os.environ.get("CADGEN_MEMO_CACHE", "1") != "0"
                   and op_memo._enabled() and op_memo._disk_enabled())
        if enabled:
            stored = _read(key)
            if stored is not None:
                try:
                    result = op_memo._thaw_result(stored, [])
                except Exception:
                    pass
                else:
                    _stats["hits"] += 1
                    return result
        result = func(*args, **kwargs)
        _stats["misses"] += 1
        try:
            if not op_memo._is_shape(result):
                raise _Decline("not a shape")
            stored, first = op_memo._freeze_result_for_first_consumer(result, [])
        except Exception:
            _stats["unstorable"] += 1
            return result
        if enabled:
            try:
                _write(key, stored)
            except (OSError, ValueError):
                pass
        return first

    return call
