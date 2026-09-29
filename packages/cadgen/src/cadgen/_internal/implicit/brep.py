"""A B-rep for the exact subset of an implicit tree.

A distance field has no faces, but most of what an author writes with it
does: a box minus cylinders IS a B-rep, and so is every primitive, every
exact boolean, every rigid transform, a uniform scale, a mirror, a repeat
and a metric offset. This module walks a tree and builds that B-rep with
build123d, so an implicit part can leave as a STEP when its tree stays in
the subset -- and says exactly which node took it out when it does not.

A boolean's ``round``/``chamfer`` blend has no exact B-rep (a smooth
minimum is not a fillet), so ``blends`` decides: ``"fillet"`` builds the
sharp boolean and fillets (or chamfers) the edges the boolean created with
the blend's radius, halving the radius up to three times when OCC refuses,
then trying each tool's edges on their own, and finally leaving that join
sharp with a warning in the report; ``"drop"`` leaves every blend sharp and
lists them; ``"refuse"`` raises naming the node. ``elongate`` and a
``custom`` field are always refused. A ``shell`` is two offsets and an
offset is OCC's, which can fail on a shape it dislikes; that failure is
reported as the node that failed, not hidden.

Import discipline: build123d is imported inside :func:`to_brep`, never at
module scope, so the ``implicit`` namespace and ``--help`` stay cheap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field as dataclass_field
from typing import Any

from cadgen._internal.implicit import field as F

__all__ = ["BLEND_MODES", "BrepReport", "to_brep", "Unrepresentable"]

_HALF_SPACE_EXTENT = 1e4
BLEND_MODES = ("fillet", "drop", "refuse")


class Unrepresentable(ValueError):
    """The tree has a node with no exact B-rep; ``node`` says which."""

    def __init__(self, node: F.Field, why: str) -> None:
        where = f" ({node.site})" if node.site else ""
        label = f" {node.label!r}" if node.label else ""
        super().__init__(f"{node.kind}{label}{where}: {why}")
        self.node = node


@dataclass
class BrepReport:
    """What the translation did: blends filleted, blends left sharp, nodes built."""

    filleted_blends: list[str] = dataclass_field(default_factory=list)
    dropped_blends: list[str] = dataclass_field(default_factory=list)
    warnings: list[str] = dataclass_field(default_factory=list)
    nodes: int = 0


def _boolean_edges(bd: Any, result: Any, operands: list[Any], tol: float = 1e-4) -> list[Any]:
    """The edges a boolean created: those lying on the surfaces of two or more operands."""
    found = []
    for edge in result.edges():
        p = edge.position_at(0.5)
        vertex = bd.Vertex(p.X, p.Y, p.Z)
        touching = 0
        for operand in operands:
            try:
                if operand.distance_to(vertex) < tol:
                    touching += 1
            except Exception:
                continue
            if touching >= 2:
                found.append(edge)
                break
    return found


def _blend(bd: Any, result: Any, operands: list[Any], node: F.Field, report: BrepReport, where: str) -> Any:
    """Fillet or chamfer the edges ``node``'s boolean made, degrading gracefully."""
    radius = node.round or node.chamfer
    chamfer = bool(node.chamfer)
    edges = _boolean_edges(bd, result, operands)
    if not edges:
        report.warnings.append(f"{where}: the operands share no edge, so its blend has nothing to round (it bridged a gap in the field)")
        report.dropped_blends.append(where)
        return result

    def attempt(shape: Any, subset: list[Any], r: float) -> Any | None:
        try:
            return shape.chamfer(r, None, subset) if chamfer else shape.fillet(r, subset)
        except Exception:
            return None

    for divisor in (1, 2, 4, 8):
        r = radius / divisor
        blended = attempt(result, edges, r)
        if blended is not None:
            report.filleted_blends.append(where + ("" if divisor == 1 else f" (at {r:g}, not {radius:g})"))
            if divisor != 1:
                report.warnings.append(f"{where}: OCC refused a {radius:g} {'chamfer' if chamfer else 'fillet'}; built at {r:g}")
            return blended
    # One tool at a time: what fails together often succeeds apart.
    shape = result
    done = 0
    for operand in operands[1:]:
        own = [e for e in edges if operand.distance_to(bd.Vertex(*e.position_at(0.5).to_tuple())) < 1e-4]
        for divisor in (1, 2, 4):
            blended = attempt(shape, own, radius / divisor)
            if blended is not None:
                shape = blended
                done += 1
                break
    if done:
        report.filleted_blends.append(f"{where} ({done} of {len(operands) - 1} tools)")
        if done < len(operands) - 1:
            report.warnings.append(f"{where}: OCC could only round {done} of {len(operands) - 1} joins; the rest are sharp")
        return shape
    report.dropped_blends.append(where)
    report.warnings.append(f"{where}: OCC refused every {'chamfer' if chamfer else 'fillet'}; the join is sharp in the STEP")
    return result


def to_brep(root: F.Field, *, blends: str = "fillet", drop_blends: bool | None = None, report: BrepReport | None = None) -> Any:
    """The build123d shape of ``root``, or raise :class:`Unrepresentable`.

    blends: what to do with a boolean's ``round``/``chamfer``: ``"fillet"``
        rounds the boolean's edges with OCC (degrading as the module doc says),
        ``"drop"`` leaves them sharp, ``"refuse"`` raises naming the node.
    drop_blends: the old spelling of ``blends="drop"``.
    """
    from cadgen import build123d as bd

    if drop_blends is not None:
        blends = "drop" if drop_blends else "refuse"
    if blends not in BLEND_MODES:
        raise ValueError(f"blends must be one of {', '.join(BLEND_MODES)}, got {blends!r}")
    report = report if report is not None else BrepReport()

    def where(node: F.Field) -> str:
        return f"{node.kind}{' ' + repr(node.label) if node.label else ''}{' (' + node.site + ')' if node.site else ''}"

    def profile(p: F.Profile):
        if isinstance(p, F.Circle):
            return bd.Circle(p.radius)
        if isinstance(p, F.Rect):
            face = bd.Rectangle(p.width, p.height)
            if p.radius > 0:
                face = bd.fillet(face.vertices(), p.radius)
            return face
        if isinstance(p, F.RegularPolygon):
            return bd.Polygon(*[tuple(map(float, v)) for v in p._poly.points], align=None)
        if isinstance(p, F.Polygon):
            return bd.Polygon(*[tuple(map(float, v)) for v in p.points], align=None)
        raise TypeError(f"unknown profile {type(p).__name__}")

    def offset_solid(shape: Any, amount: float, node: F.Field, what: str) -> Any:
        """OCC's offset, with its rounded corners first and its intersected corners as the fallback it suggests."""
        last: Exception | None = None
        for kind in (bd.Kind.ARC, bd.Kind.INTERSECTION):
            try:
                result = bd.offset(shape, amount=amount, kind=kind)
                if kind is not bd.Kind.ARC:
                    report.warnings.append(f"{where(node)}: OCC offset needed sharp corners (Kind.INTERSECTION) to {what}")
                return result
            except Exception as error:  # OCC's offset is the one operation here that can refuse a valid input
                last = error
        raise Unrepresentable(node, f"OCC could not {what}: {last}") from last

    def build(node: F.Field):
        report.nodes += 1
        if isinstance(node, F.Sphere):
            return bd.Sphere(node.radius)
        if isinstance(node, F.Box):
            shape = bd.Box(*node.size)
            if node.radius > 0:
                shape = shape.fillet(node.radius, shape.edges())
            return shape
        if isinstance(node, F.Cylinder):
            shape = bd.Cylinder(node.radius, node.height)
            if node.radius_edge > 0:
                shape = shape.fillet(node.radius_edge, shape.edges().filter_by(bd.GeomType.CIRCLE))
            return shape
        if isinstance(node, F.Capsule):
            a, b = bd.Vector(*node.a), bd.Vector(*node.b)
            axis = b - a
            length = axis.length
            spheres = bd.Pos(*node.a) * bd.Sphere(node.radius) + bd.Pos(*node.b) * bd.Sphere(node.radius)
            if length < 1e-9:
                return spheres
            body = bd.Cylinder(node.radius, length)
            direction = axis.normalized()
            # Cylinder is along +Z, centred: turn Z onto the segment's direction and move to its midpoint.
            plane = bd.Plane(origin=(a + b) * 0.5, z_dir=direction)
            return plane * body + spheres
        if isinstance(node, F.Cone):
            return bd.Cone(node.radius_bottom, node.radius_top, node.height)
        if isinstance(node, F.Torus):
            return bd.Torus(node.radius, node.tube)
        if isinstance(node, F.HalfSpace):
            n = bd.Vector(*node.normal)
            plane = bd.Plane(origin=bd.Vector(*node.origin) + n * (_HALF_SPACE_EXTENT / 2), z_dir=n)
            return plane * bd.Box(_HALF_SPACE_EXTENT, _HALF_SPACE_EXTENT, _HALF_SPACE_EXTENT)
        if isinstance(node, F.Extrude):
            return bd.extrude(profile(node.profile), amount=node.height / 2, both=True)
        if isinstance(node, F.Revolve):
            face = bd.Plane.XZ * profile(node.profile)
            return bd.revolve(face, axis=bd.Axis.Z)
        if isinstance(node, F.Brep):
            return node.shape  # the way in kept the B-rep: the way out uses it exactly
        if isinstance(node, F.Custom):
            raise Unrepresentable(node, "a custom field is a Python function with no B-rep")
        if isinstance(node, F._Boolean):
            blended = bool(node.round or node.chamfer)
            if blended and blends == "refuse":
                raise Unrepresentable(
                    node,
                    f"a {'round' if node.round else 'chamfer'} blend has no exact B-rep; "
                    "use blends='fillet' to round the boolean's edges with OCC, or 'drop' to leave them sharp",
                )
            parts = [build(child) for child in node.operands]
            result = parts[0]
            for part in parts[1:]:
                if isinstance(node, F.Union):
                    result = result + part
                elif isinstance(node, F.Intersection):
                    result = result & part
                else:
                    result = result - part
            if blended:
                if blends == "drop":
                    report.dropped_blends.append(where(node))
                else:
                    result = _blend(bd, result, parts, node, report, where(node))
            return result
        if isinstance(node, F.Translate):
            return bd.Pos(*node.shift) * build(node.child)
        if isinstance(node, F.Rotate):
            return build(node.child).rotate(bd.Axis((0, 0, 0), node.axis), node.angle_deg)
        if isinstance(node, F.Scale):
            return build(node.child).scale(node.factor)
        if isinstance(node, F.Mirror):
            shape = build(node.child)
            plane = {"x": bd.Plane.YZ, "y": bd.Plane.XZ, "z": bd.Plane.XY}[node.axis]
            return shape + bd.mirror(shape, about=plane)
        if isinstance(node, F.Repeat):
            shape = build(node.child)
            result = None
            for i in range(node.count[0]):
                for j in range(node.count[1]):
                    for k in range(node.count[2]):
                        offset = tuple((c - (n - 1) / 2) * s for c, n, s in zip((i, j, k), node.count, node.spacing))
                        copy = bd.Pos(*offset) * shape
                        result = copy if result is None else result + copy
            return result
        if isinstance(node, F.Offset):
            shape = build(node.child)
            if node.r == 0:
                return shape
            return offset_solid(shape, node.r, node, f"offset this shape by {node.r:g}")
        if isinstance(node, F.Shell):
            shape = build(node.child)
            half = node.thickness / 2
            return offset_solid(shape, half, node, f"shell this shape by {node.thickness:g}") - offset_solid(
                shape, -half, node, f"shell this shape by {node.thickness:g}"
            )
        if isinstance(node, F.Elongate):
            raise Unrepresentable(node, "elongate has no exact B-rep (model the stretched primitive directly)")
        raise Unrepresentable(node, f"no B-rep translation for {type(node).__name__}")

    shape = build(root)
    if hasattr(shape, "clean"):
        try:
            shape = shape.clean()
        except Exception:
            pass
    return shape


def volume_of(shape: Any) -> float:
    return float(getattr(shape, "volume", 0.0))


def solids_of(shape: Any) -> int:
    try:
        return len(shape.solids())
    except Exception:
        return 0


def is_blend_free(root: F.Field) -> bool:
    """True when no boolean in the tree carries a round or chamfer."""

    def walk(node: F.Field) -> bool:
        if isinstance(node, F._Boolean) and (node.round or node.chamfer):
            return False
        return all(walk(child) for child in node.children())

    return walk(root)


def uses(root: F.Field, kinds: tuple[type, ...]) -> bool:
    def walk(node: F.Field) -> bool:
        return isinstance(node, kinds) or any(walk(child) for child in node.children())

    return walk(root)


