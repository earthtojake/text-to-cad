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
    "closest_points", "overlap_volume", "topology_errors", "boundary_edges",
    "self_intersections", "mass_properties",
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


def topology_errors(shape: Shape) -> tuple[GeometryIssue, ...]:
    """BRepCheck topology/geometry faults, with affected owned entities.

    Codes are OCCT's ``BRepCheck_*`` status names. Open shells and reversed
    solids can have valid topology. Closure, signed volume and expensive
    boolean self-intersection testing are separate questions.
    """
    from OCP.BRepCheck import BRepCheck_Analyzer, BRepCheck_NoError
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedMapOfShape

    wrapped = _wrapped(shape)
    try:
        private = _copy(wrapped)
        analyzer = BRepCheck_Analyzer(private)
        if analyzer.IsValid():
            return ()
        entities = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(private, entities)
        issues = []
        for i in range(1, entities.Extent() + 1):
            entity = entities.FindKey(i)
            result = analyzer.Result(entity)
            if result is None:
                continue
            seen = set()
            def collect(statuses, context=None):
                for status in statuses:
                    key = (int(status), entities.FindIndex(context) if context is not None else 0)
                    if status != BRepCheck_NoError and key not in seen:
                        seen.add(key)
                        affected = (entity,) if context is None else (entity, context)
                        issues.append(GeometryIssue(status.name, tuple(_cast(s) for s in affected)))
            collect(result.Status())
            result.InitContextIterator()
            while result.MoreShapeInContext():
                context = result.ContextualShape()
                collect(result.StatusOnShape(context), context)
                result.NextShapeInContext()
        if not issues:
            raise GeometryError("topology is invalid but the kernel provided no diagnostic")
        return tuple(issues)
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
    """
    from OCP.BOPAlgo import BOPAlgo_CheckStatus
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Check

    wrapped = _wrapped(shape)
    try:
        private = _copy(wrapped)
        checker = BRepAlgoAPI_Check(private, False, True)
        checker.Perform()
        if checker.HasErrors():
            raise GeometryError("self-intersection checker failed")
        issues = []
        for result in checker.Result():
            status = result.GetCheckStatus()
            if status != BOPAlgo_CheckStatus.BOPAlgo_SelfIntersect:
                raise GeometryError(f"self-intersection check was inconclusive: {status.name}")
            entities = list(result.GetFaultyShapes1()) + list(result.GetFaultyShapes2())
            issues.append(GeometryIssue(status.name, tuple(_cast(s) for s in entities or [private])))
        if not checker.IsValid() and not issues:
            raise GeometryError("self-intersection check failed without diagnostics")
        return tuple(issues)
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
