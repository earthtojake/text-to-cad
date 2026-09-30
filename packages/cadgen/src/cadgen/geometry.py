"""Small, exact geometry queries for Python checks.

Inputs are native build123d geometry in a common coordinate system. Lengths
use the input unit; areas, volumes and inertia use its corresponding powers.
No function selects assembly parts, assigns tolerances, repairs inputs or
decides whether a design passes. Kernel failures raise ``GeometryError``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from build123d import Edge, Shape, Shell, Solid, Vector

__all__ = [
    "GeometryError", "GeometryIssue", "ClosestPoints", "MassProperties",
    "closest_points", "overlap_volume", "is_valid", "is_sound", "topology_errors",
    "boundary_edges", "self_intersections", "mass_properties",
]

Matrix3 = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


class GeometryError(RuntimeError):
    """The kernel could not establish the requested geometric result."""


@dataclass(frozen=True)
class ClosestPoints:
    distance: float
    point_a: Vector
    point_b: Vector


@dataclass(frozen=True)
class GeometryIssue:
    code: str
    entities: tuple[Shape, ...]


@dataclass(frozen=True)
class MassProperties:
    volume: float
    mass: float
    center_of_mass: Vector
    inertia: Matrix3


def _wrapped(shape, expected=None):
    from build123d import Shape
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX

    if not isinstance(shape, expected or Shape):
        raise TypeError(f"expected {(expected or Shape).__name__}, got {type(shape).__name__}")
    try:
        wrapped = shape.wrapped
    except AssertionError as exc:  # build123d's empty wrappers have no TopoDS object
        raise ValueError("geometry must be nonempty") from exc
    if wrapped is None or wrapped.IsNull() or not any(
        TopExp_Explorer(wrapped, kind).More() for kind in (TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX)
    ):
        raise ValueError("geometry must be nonempty")
    return wrapped


def _copy(shape):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

    copier = BRepBuilderAPI_Copy(shape, True, False)
    if not copier.IsDone() or copier.Shape().IsNull():
        raise GeometryError("could not copy geometry")
    return copier.Shape()


def _cast(shape):
    from build123d import Compound

    return Compound.cast(shape)


def _items(collection) -> list:
    """An OCCT list's elements, taking exactly ``Size()`` from its iterator.

    Exhausting the binding's iterator ends in a C++ exception that pybind
    turns into StopIteration; unwinding it costs ~2.4 ms on macOS arm64, which
    a check paid once per issue, per status list, per sub-shape.
    """
    iterator = iter(collection)
    return [next(iterator) for _ in range(collection.Size())]


def _properties(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props, False, False, False)
    if not isfinite(props.Mass()):
        raise GeometryError("volume integration returned a nonfinite result")
    return props


def _distance_members(shape):
    """Unpack containers without turning solid interiors into boundaries."""
    from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID
    from OCP.TopoDS import TopoDS_Iterator

    members, pending = [], [shape]
    while pending:
        current = pending.pop()
        if current.ShapeType() in (TopAbs_COMPOUND, TopAbs_COMPSOLID):
            children = TopoDS_Iterator(current, True, True)
            while children.More():
                pending.append(children.Value())
                children.Next()
        else:
            members.append(current)
    return members


def closest_points(a: Shape, b: Shape) -> ClosestPoints:
    """Minimum set distance and one minimizing pair, in the input frame.

    Solid interiors count: contact, overlap and containment have distance
    zero. Witnesses need not be on both boundaries or unique. This is not
    penetration depth. Pass faces/shells to ask about their boundaries.
    """
    from build123d import Vector
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    def measure(left, right):
        query = BRepExtrema_DistShapeShape(left, right)
        if not query.IsDone() or query.NbSolution() < 1:
            raise GeometryError("closest point computation did not complete")
        distance = float(query.Value())
        pa, pb = Vector(query.PointOnShape1(1)), Vector(query.PointOnShape2(1))
        if not all(isfinite(v) for v in (distance, *pa, *pb)) or distance < 0:
            raise GeometryError("closest point computation returned an invalid result")
        return ClosestPoints(distance, pa, pb)

    left, right = _wrapped(a), _wrapped(b)
    try:
        # OCCT's interior check recognizes top-level solids, but not solids
        # nested in compounds. Query their union member by member, preserving
        # shells, wires and other loose geometry as well as solids. Iterator
        # locations/orientations include every containing assembly placement.
        left_members, right_members = _distance_members(left), _distance_members(right)
        if len(left_members) == len(right_members) == 1:
            return measure(left_members[0], right_members[0])

        from OCP.BRepBndLib import BRepBndLib
        from OCP.Bnd import Bnd_Box

        def bounds(shape):
            box = Bnd_Box()
            BRepBndLib.Add_s(shape, box, False)
            return box

        right_bounds = [bounds(member) for member in right_members]
        best = None
        for member in left_members:
            box = bounds(member)
            candidates = sorted((box.Distance(other), i) for i, other in enumerate(right_bounds))
            for lower_bound, i in candidates:
                if best is not None and lower_bound >= best.distance:
                    break
                result = measure(member, right_members[i])
                if best is None or result.distance < best.distance:
                    best = result
                    if best.distance == 0:
                        return best
        if best is None:
            raise GeometryError("closest point computation found no geometry members")
        return best
    except Exception as exc:
        raise GeometryError(f"closest point computation failed: {exc}") from exc


def overlap_volume(a: Solid, b: Solid) -> float:
    """Intersection volume of two finite, positively oriented solids.

    Contact has zero volume. Assembly pair selection, intentional overlaps
    and acceptance thresholds belong to the caller. Inputs are never fused
    or modified; a failed boolean is an error, never a zero-volume answer.
    """
    from build123d import Solid
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.Bnd import Bnd_Box

    left, right = _wrapped(a, Solid), _wrapped(b, Solid)
    try:
        if _properties(left).Mass() <= 0 or _properties(right).Mass() <= 0:
            raise ValueError("overlap_volume requires positively oriented solids with positive volume")
        boxes = (Bnd_Box(), Bnd_Box())
        for shape, bounds in zip((left, right), boxes):
            BRepBndLib.Add_s(shape, bounds, False)
        if boxes[0].IsOut(boxes[1]):
            return 0.0
        boolean = BRepAlgoAPI_Common(_copy(left), _copy(right))
        if not boolean.IsDone():
            raise GeometryError("intersection boolean did not complete")
        common = boolean.Shape()
        if common.IsNull() or not BRepCheck_Analyzer(common).IsValid():
            raise GeometryError("intersection boolean returned invalid geometry")
        volume = float(_properties(common).Mass())
        if volume < 0:
            raise GeometryError("intersection boolean returned negative volume")
        return volume
    except ValueError:
        raise
    except Exception as exc:
        raise GeometryError(f"intersection computation failed: {exc}") from exc


# --- Reused verdicts ------------------------------------------------------------
#
# The checks below are pure functions of the shape they are handed: its
# geometry, placement and orientation. The op memo's value tier already keys
# exactly that identity -- the location-stripped BREP digest and the location
# matrix, bound to the loaded build123d/OCP runtime -- in its RAM and disk
# tiers, so an identical shape gets the stored verdict instead of a rerun.
# ``is_valid`` and ``is_sound`` store a bare boolean (``op_memo.memoized_check``);
# build123d's own ``Shape.is_valid`` property is plain and stores nothing. The
# diagnostics store more: a
# verdict holds only issue codes and, per affected entity, its index in the
# checked copy's ``TopExp.MapShapes`` order and its orientation; never native
# geometry. A hit decodes it against a fresh private copy of the caller's
# shape: the same owned entities, placements and orientations the kernel named
# on the miss (``MapShapes`` order is a function of the BREP the key digests).
# A check that raises stores nothing. An entity the index cannot address
# stores None, which reruns the check on every call. The op name names the
# check: change what one computes and change its name with it.
#
# A verdict is stored only for a shape worth its key (``_stored``): the key
# digests the whole BREP and a miss writes an index entry, which for a small
# shape costs more than the check. Median ms, direct / stored miss / disk hit
# (macOS arm64, OCP 7.9.3):
#
#                        is_valid          is_sound
#   edge                 0.009/0.37/0.08   0.022/0.40/0.09
#   plane face           0.08/0.44/0.10    0.12/0.47/0.10
#   cylinder solid       0.10/0.48/0.11    0.89/1.30/0.11
#   box solid            0.30/0.78/0.18    0.62/1.21/0.20
#   face with 16 holes   0.70/1.21/0.26    0.78/1.41/0.26
#   plate with 64 holes  14.2/18.7/2.9     84.7/92.3/3.2
#
# A wire's digest outgrows its check at every size (512 edges: 2.0 direct,
# 2.6 per disk hit), so a shape without faces is checked directly, as is one
# with fewer than ``_STORED_EDGE_USES`` edge uses: a tiny gate never pays a
# miss, at the price of the odd small solid's ``is_sound`` hit (the cylinder).
# The diagnostics run the same kernel checks and follow the same rule.

# Edge uses: each face's boundary edges as ``TopExp_Explorer`` visits them.
# A box has 24, a cylinder 6, a plane face 4.
_STORED_EDGE_USES = 16


def _stored(wrapped) -> bool:
    """Whether a verdict on ``wrapped`` is worth its key: faces and at least
    ``_STORED_EDGE_USES`` edge uses. Counting stops at the threshold."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer

    if wrapped.ShapeType() in (TopAbs_ShapeEnum.TopAbs_VERTEX, TopAbs_ShapeEnum.TopAbs_EDGE,
                               TopAbs_ShapeEnum.TopAbs_WIRE):
        return False
    if not TopExp_Explorer(wrapped, TopAbs_FACE).More():
        return False
    uses = TopExp_Explorer(wrapped, TopAbs_EDGE)
    for _ in range(_STORED_EDGE_USES):
        if not uses.More():
            return False
        uses.Next()
    return True


def _verdict_input(shape):
    """The native shape a pass/fail verdict is about, or None for a null shape.

    Unlike the measurements, ``is_valid`` and ``is_sound`` accept null and
    empty geometry: build123d's ``is_valid`` answers for it, and a gate in a
    model body must not crash on an empty intermediate.
    """
    from build123d import Shape

    if not isinstance(shape, Shape):
        raise TypeError(f"expected Shape, got {type(shape).__name__}")
    wrapped = shape._wrapped
    return None if wrapped is None or wrapped.IsNull() else wrapped


def _entity_map(private):
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    entities = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(private, entities)
    return entities


def _encode(entities, shapes) -> list | None:
    codes = []
    for shape in shapes:
        index = entities.FindIndex(shape)
        if not index:
            return None
        codes.append([index, int(shape.Orientation())])
    return codes


def _decode(entities, codes) -> tuple:
    from OCP.TopAbs import TopAbs_Orientation

    return tuple(_cast(entities.FindKey(index).Oriented(TopAbs_Orientation(orientation)))
                 for index, orientation in codes)


def _reused(op_name: str, wrapped, run, decode):
    """``run(private)`` returns ``(answer, encoded)``; memoize ``encoded``.

    ``private`` is a fresh owned copy of ``wrapped``. A miss returns the
    kernel's own answer; a hit decodes the stored one against a fresh copy.
    A shape the op memo cannot key is checked directly, as is a stored None
    and a shape too small to be worth a key (``_stored``).
    """
    from cadgen._internal import op_memo

    live = []

    def compute():
        private = _copy(wrapped)
        answer, encoded = run(private)
        live.append((private, answer))
        return encoded

    try:
        # CADGEN_OP_MEMO=0 skips the key: its digest serializes the whole shape.
        key = op_memo.oriented_shape_key(wrapped) if op_memo._enabled() and _stored(wrapped) else None
    except Exception:  # noqa: BLE001 - an unkeyable shape is still checkable
        key = None
    if key is None:
        compute()
        return live[0][1]
    encoded = op_memo.memoized_value(op_name, key, compute)
    if live:
        return live[0][1]
    if encoded is None:
        compute()
        return live[0][1]
    return decode(_copy(wrapped), encoded) if encoded else ()


def is_valid(shape: Shape) -> bool:
    """``BRepCheck_Analyzer``'s verdict on the shape: the same answer as
    build123d's ``Shape.is_valid`` property, including for null and empty
    shapes (a null shape is valid; an empty one gets BRepCheck's verdict:
    an empty compound or solid passes, an empty shell or wire fails). A
    shape with faces and enough edges stores its verdict and an identical
    one (geometry, placement, orientation) reuses it; a smaller shape is
    checked directly, which is cheaper than the key. A kernel failure raises
    ``GeometryError`` and stores nothing. What is invalid, and where, is
    ``topology_errors``'s question.
    """
    from cadgen._internal import op_memo
    from OCP.BRepCheck import BRepCheck_Analyzer

    wrapped = _verdict_input(shape)
    if wrapped is None:
        return True

    def check() -> bool:
        analyzer = BRepCheck_Analyzer(wrapped)
        analyzer.SetParallel(True)
        return bool(analyzer.IsValid())

    try:
        if not _stored(wrapped):
            return check()
        return op_memo.memoized_check("geometry.is_valid.v1", wrapped, check)
    except GeometryError:
        raise
    except Exception as exc:
        raise GeometryError(f"validity check failed: {exc}") from exc


def is_sound(shape: Shape) -> bool:
    """The boolean kernel's argument check (``BRepAlgoAPI_Check``) passes the
    shape: BRepCheck-valid, no self-intersections, no too-small edges, and an
    argument type a boolean accepts. This is what a fuse or cut demands of an
    operand, and it can be expensive. A null or empty shape is not sound: the
    kernel rejects it as an argument type (``BOPAlgo_BadType``), a verdict,
    not an error. A shape with faces and enough edges stores its verdict and
    an identical one (geometry, placement, orientation) reuses it; a smaller
    shape is checked directly. A check the kernel could not complete raises
    ``GeometryError`` and stores nothing. Closure, solid count and signed
    volume are separate questions; the faulty entities are
    ``self_intersections``'s.
    """
    from cadgen._internal import op_memo
    from OCP.BOPAlgo import BOPAlgo_CheckStatus
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Check

    wrapped = _verdict_input(shape)
    if wrapped is None:
        return False  # BRepAlgoAPI_Check on a null shape: BOPAlgo_BadType
    inconclusive = (BOPAlgo_CheckStatus.BOPAlgo_CheckUnknown, BOPAlgo_CheckStatus.BOPAlgo_OperationAborted)

    def check() -> bool:
        # The constructor performs the check (self-intersections and small
        # edges both on, the kernel's defaults); Perform() would run it again.
        checker = BRepAlgoAPI_Check(wrapped)
        if checker.HasErrors():
            raise GeometryError("boolean argument checker failed")
        for result in _items(checker.Result()):
            if result.GetCheckStatus() in inconclusive:
                raise GeometryError(f"boolean argument check was inconclusive: {result.GetCheckStatus().name}")
        return bool(checker.IsValid())

    try:
        if not _stored(wrapped):
            return check()
        return op_memo.memoized_check("geometry.is_sound.v1", wrapped, check)
    except GeometryError:
        raise
    except Exception as exc:
        raise GeometryError(f"soundness check failed: {exc}") from exc


def topology_errors(shape: Shape) -> tuple[GeometryIssue, ...]:
    """BRepCheck topology/geometry faults, with affected owned entities.

    Codes are OCCT's ``BRepCheck_*`` status names. Open shells and reversed
    solids can have valid topology. Closure, signed volume and expensive
    boolean self-intersection testing are separate questions. A shape with
    faces and enough edges stores its verdict and an identical one
    (geometry, placement, orientation) reuses it.
    """
    from OCP.BRepCheck import BRepCheck_Analyzer, BRepCheck_NoError

    def run(private):
        analyzer = BRepCheck_Analyzer(private)
        if analyzer.IsValid():
            return (), []
        entities = _entity_map(private)
        found = []
        for i in range(1, entities.Extent() + 1):
            entity = entities.FindKey(i)
            result = analyzer.Result(entity)
            if result is None:
                continue
            seen = set()
            def collect(statuses, context=None):
                for status in _items(statuses):
                    key = (int(status), entities.FindIndex(context) if context is not None else 0)
                    if status != BRepCheck_NoError and key not in seen:
                        seen.add(key)
                        found.append((status.name, (entity,) if context is None else (entity, context)))
            collect(result.Status())
            result.InitContextIterator()
            while result.MoreShapeInContext():
                context = result.ContextualShape()
                collect(result.StatusOnShape(context), context)
                result.NextShapeInContext()
        if not found:
            raise GeometryError("topology is invalid but the kernel provided no diagnostic")
        answer = tuple(GeometryIssue(code, tuple(_cast(s) for s in affected)) for code, affected in found)
        encoded = [[code, _encode(entities, affected)] for code, affected in found]
        return answer, None if any(codes is None for _, codes in encoded) else encoded

    def decode(private, encoded):
        entities = _entity_map(private)
        return tuple(GeometryIssue(code, _decode(entities, codes)) for code, codes in encoded)

    wrapped = _wrapped(shape)
    try:
        return _reused("geometry.topology_errors.v1", wrapped, run, decode)
    except Exception as exc:
        raise GeometryError(f"topology check failed: {exc}") from exc


def boundary_edges(shell: Shell) -> tuple[Edge, ...]:
    """Free edges of a shell; seams are not boundaries.

    An empty result establishes no free edges, not full manifold validity.
    Geometry is neither sewn nor repaired.
    """
    from build123d import Shell
    from OCP.ShapeAnalysis import ShapeAnalysis_Shell
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    wrapped = _wrapped(shell, Shell)
    try:
        analyzer = ShapeAnalysis_Shell()
        private = _copy(wrapped)
        analyzer.LoadShells(private)
        analyzer.CheckOrientedShells(private, True)
        edges = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(analyzer.FreeEdges(), TopAbs_EDGE, edges)
        return tuple(_cast(edges.FindKey(i)) for i in range(1, edges.Extent() + 1))
    except Exception as exc:
        raise GeometryError(f"boundary edge check failed: {exc}") from exc


def self_intersections(shape: Shape) -> tuple[GeometryIssue, ...]:
    """Explicit boolean self-intersection check in the supplied placement.

    This can be expensive. Codes are OCCT's ``BOPAlgo_SelfIntersect``; affected
    entities are owned copies. Inconclusive/failed checks raise an exception.
    A shape with faces and enough edges stores its verdict and an identical
    one (geometry, placement, orientation) reuses it.
    """
    from OCP.BOPAlgo import BOPAlgo_CheckStatus
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Check

    def run(private):
        # This constructor performs the check; Perform() would run it again.
        checker = BRepAlgoAPI_Check(private, False, True)
        if checker.HasErrors():
            raise GeometryError("self-intersection checker failed")
        found = []
        for result in _items(checker.Result()):
            status = result.GetCheckStatus()
            if status != BOPAlgo_CheckStatus.BOPAlgo_SelfIntersect:
                raise GeometryError(f"self-intersection check was inconclusive: {status.name}")
            found.append((status.name, _items(result.GetFaultyShapes1()) + _items(result.GetFaultyShapes2())))
        if not checker.IsValid() and not found:
            raise GeometryError("self-intersection check failed without diagnostics")
        answer = tuple(GeometryIssue(code, tuple(_cast(s) for s in entities or [private]))
                       for code, entities in found)
        if not found:
            return answer, []
        entity_map = _entity_map(private)
        encoded = [[code, _encode(entity_map, entities)] for code, entities in found]
        return answer, None if any(codes is None for _, codes in encoded) else encoded

    def decode(private, encoded):
        entities = _entity_map(private)
        return tuple(GeometryIssue(code, _decode(entities, codes) or (_cast(private),))
                     for code, codes in encoded)

    wrapped = _wrapped(shape)
    try:
        return _reused("geometry.self_intersections.v1", wrapped, run, decode)
    except Exception as exc:
        raise GeometryError(f"self-intersection check failed: {exc}") from exc


def mass_properties(bodies: Iterable[tuple[Solid, float]]) -> MassProperties:
    """Add uniform-density solids, including overlapping material as supplied.

    Density must be finite and positive, in mass/input-unit³. Inertia is
    about the combined center of mass, expressed in the input coordinate
    axes. For mm and kg/mm³ the outputs are mm³, kg, mm and kg·mm².
    """
    from build123d import Solid, Vector
    from OCP.GProp import GProp_GProps

    combined = GProp_GProps()
    volume, count = 0.0, 0
    for solid, density in bodies:
        wrapped = _wrapped(solid, Solid)
        if isinstance(density, bool) or not isfinite(density) or density <= 0:
            raise ValueError("density must be finite and positive")
        try:
            props = _properties(wrapped)
            if props.Mass() <= 0:
                raise ValueError("mass_properties requires positively oriented solids with positive volume")
            volume += float(props.Mass())
            combined.Add(props, float(density))
            count += 1
        except ValueError:
            raise
        except Exception as exc:
            raise GeometryError(f"mass integration failed: {exc}") from exc
    if not count:
        raise ValueError("mass_properties requires at least one body")
    tensor = combined.MatrixOfInertia()
    inertia = tuple(tuple(float(tensor.Value(i, j)) for j in range(1, 4)) for i in range(1, 4))
    center = Vector(combined.CentreOfMass())
    if not all(isfinite(v) for v in (volume, combined.Mass(), *center, *(v for row in inertia for v in row))):
        raise GeometryError("mass integration returned a nonfinite result")
    return MassProperties(volume, float(combined.Mass()), center, inertia)
