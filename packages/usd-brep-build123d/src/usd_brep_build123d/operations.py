"""build123d's operations, in builder mode (inside BuildPart/BuildSketch) and algebra mode."""
from __future__ import annotations

import math

import usd_brep as ub

from .builders import BuildPart, BuildSketch, current_builder, current_local_locations, current_locations, current_workplanes
from .geometry import Axis, Keep, Kind, Location, Mode, Plane, Rotation, Vector
from .objects import placed_sketch
from .topology import Compound, Edge, Part, Profile, Shape, Sketch, combine, flatten, leaves, sweep_tree, transform


def _pending_or(objects, what):
    """Sketches to sweep: the ones given, or the builder's pending sketches (consumed)."""
    context = current_builder()
    if objects is None:
        if not isinstance(context, BuildPart) or not context.pending:
            raise ValueError(f"A face or sketch must be provided to {what}")
        sketches = [sketch for sketch, _plane in context.pending]
        context.pending = []
        return sketches, context
    return [placed_sketch(o) for o in flatten([objects])], context


def _finish(solids, context, mode):
    if isinstance(context, BuildPart):
        context._add_to_context(*solids, mode=mode)
    breps = [s._brep for s in solids]
    return Part(combine(breps[0], breps[1:], ub.boolean_union))


def extrude(to_extrude=None, amount: float | None = None, dir=None, until=None, target=None, both: bool = False,  # noqa: A002
            taper: float = 0.0, clean: bool = True, mode: Mode = Mode.ADD) -> Part:
    if until is not None or target is not None:
        raise NotImplementedError("extrude(until=...) is not supported on usd-brep yet")
    if taper:
        raise NotImplementedError("tapered extrusion is not supported on usd-brep yet")
    if amount is None:
        raise ValueError("Either amount or until must be provided")
    sketches, context = _pending_or(to_extrude, "extrude")

    def prism(profile: Profile):
        direction = Vector(dir).normalized() if dir is not None else profile.plane.z_dir
        direction = direction * math.copysign(1.0, amount)
        if both:
            start = direction * (-abs(amount))
            curves = [transform(c, Location(start).M) for c in profile.curves()]
            return ub.linear_sweep(curves, direction.to_tuple(), 2 * abs(amount))
        return ub.linear_sweep(profile.curves(), direction.to_tuple(), abs(amount))

    solids = [Part(sweep_tree(sketch._tree, prism)) for sketch in sketches]
    return _finish(solids, context, mode)


def revolve(profiles=None, axis: Axis = Axis.Z, revolution_arc: float = 360.0, clean: bool = True,
            mode: Mode = Mode.ADD) -> Part:
    sign = 1 if revolution_arc >= 0 else -1
    angle = revolution_arc % (sign * 360.0)
    angle = sign * 360.0 if angle == 0 else angle
    sketches, context = _pending_or(profiles, "revolve")

    def revolution(profile: Profile):
        return ub.rotational_sweep(profile.curves(), axis.position.to_tuple(), axis.direction.to_tuple(), angle)

    solids = [Part(sweep_tree(sketch._tree, revolution)) for sketch in sketches]
    return _finish(solids, context, mode)


def loft(sections=None, ruled: bool = False, clean: bool = True, mode: Mode = Mode.ADD) -> Part:
    """Through one-loop sections. Ruled lofts are exact; smooth ones are usd-brep's cubic skin,
    close to but not the same surface as OpenCascade's ThruSections."""
    context = current_builder()
    if sections is None:
        if not isinstance(context, BuildPart) or not context.pending:
            raise ValueError("No sections provided")
        sketches = [sketch for sketch, _plane in context.pending]
        context.pending = []
    else:
        sketches = [placed_sketch(s) for s in flatten([sections])]
    profiles = [p for s in sketches for p in leaves(s._tree)]
    if any(len(p.loops) != 1 for p in profiles):
        raise NotImplementedError("lofting sections with holes is not supported on usd-brep yet")
    counts, curves = [], []
    for p in profiles:
        cs = p.curves()
        counts.append(len(cs))
        curves.extend(cs)
    degree = 1 if ruled else min(3, len(profiles) - 1)
    solid = Part(ub.create_skin_primitive(counts, curves, degree=degree, cap_ends=True))
    return _finish([solid], context, mode)


def add(objects, rotation=None, clean: bool = True, mode: Mode = Mode.ADD):
    context = current_builder()
    objs = [o._result() if isinstance(o, (BuildPart, BuildSketch)) else o for o in flatten([objects])]
    objs = [o for o in objs if o is not None]
    if isinstance(context, BuildPart):
        rotate = Rotation(*rotation) if isinstance(rotation, (tuple, list)) else Location()
        sketches = [o for o in objs if isinstance(o, Sketch)]
        located = [o.moved(loc * rotate) for o in objs if not isinstance(o, Sketch) for loc in current_locations()]
        for sketch in sketches:
            for plane in current_workplanes():
                for loc in current_locations():
                    context.pending.append((sketch.moved(loc), plane))
        context._add_to_context(*located, mode=mode)
        return Compound(located) if located else None
    if isinstance(context, BuildSketch):
        angle = rotation if isinstance(rotation, (int, float)) else 0.0
        placed = [o.moved(loc * Rotation(0, 0, angle)) for o in objs for loc in current_local_locations()]
        context._add_to_context(*placed, mode=mode)
        return placed
    raise RuntimeError("Add must have an active builder context")


def _target(objects, what):
    edges = [e for e in flatten([objects])]
    context = current_builder()
    if any(not isinstance(e, Edge) for e in edges):
        raise NotImplementedError(f"{what} of sketch or line vertices is not supported on usd-brep yet")
    target = context.part if isinstance(context, BuildPart) else edges[0].topo_parent
    if target is None:
        raise ValueError(f"Nothing to {what}")
    return edges, target, context


def fillet(objects, radius: float) -> Part:
    edges, target, context = _target(objects, "fillet")
    new_part = target.fillet(radius, edges)
    if isinstance(context, BuildPart):
        context._add_to_context(new_part, mode=Mode.REPLACE)
    return new_part


def chamfer(objects, length: float, length2: float | None = None, angle: float | None = None, reference=None) -> Part:
    if length2 and angle:
        raise ValueError("Only one of length2 or angle should be provided")
    if angle:
        length2 = length * math.tan(math.radians(angle))
    edges, target, context = _target(objects, "chamfer")
    new_part = target.chamfer(length, length2, edges, reference)
    if isinstance(context, BuildPart):
        context._add_to_context(new_part, mode=Mode.REPLACE)
    return new_part


def blend(objects, radius: float, continuity: int = 2, thumbweight: float = 1.0) -> Part:
    """usd-brep extension, not build123d: a curvature-continuous (G2) or G3 blend where
    fillet() makes a circular (G1) one. Same edge rules as fillet()."""
    edges, target, context = _target(objects, "blend")
    if continuity not in (1, 2, 3):
        raise ValueError("continuity is 1 (G1), 2 (G2) or 3 (G3)")
    new_part = target._blend(edges, radius, ub.FilletXSect.BLEND, continuity=continuity)
    if isinstance(context, BuildPart):
        context._add_to_context(new_part, mode=Mode.REPLACE)
    return new_part


def _targets(objects):
    context = current_builder()
    if objects is None:
        if context is None or context._obj is None:
            raise ValueError("objects must be provided")
        return [context._obj], context
    return flatten([objects]), context


def mirror(objects=None, about: Plane = Plane.XZ, mode: Mode = Mode.ADD):
    object_list, context = _targets(objects)
    mirrored = [o.mirror(about) for o in object_list]
    if context is not None:
        context._add_to_context(*mirrored, mode=mode)
    if all(isinstance(o, Sketch) for o in mirrored):
        tree = mirrored[0]._tree
        for m in mirrored[1:]:
            tree = (Mode.ADD, tree, m._tree)
        return Sketch(tree)
    return Part(combine(mirrored[0]._brep, [m._brep for m in mirrored[1:]], ub.boolean_union)) if len(mirrored) > 1 else mirrored[0]


def split(objects=None, bisect_by: Plane = Plane.XZ, keep: Keep = Keep.TOP, mode: Mode = Mode.REPLACE):
    object_list, context = _targets(objects)
    pieces = []
    for obj in object_list:
        result = obj.split(bisect_by, keep)
        pieces.extend(result if isinstance(result, tuple) else [result])
    if context is not None:
        context._add_to_context(*pieces, mode=mode)
    return Compound(pieces) if len(pieces) > 1 else pieces[0]


def offset(objects=None, amount: float = 0, openings=None, kind: Kind = Kind.ARC, side=None, closed: bool = True,
           min_edge_length=None, mode: Mode = Mode.REPLACE):
    """Solids only: with openings, a shell whose walls grow by ``amount`` (negative: inward)
    and whose opening faces are removed; without, the solid grown or shrunk by ``amount``."""
    if kind == Kind.TANGENT:
        raise NotImplementedError("Kind.TANGENT offsets do not exist in usd-brep")
    object_list, context = _targets(objects)
    opening_faces = flatten([openings]) if openings is not None else []
    results = []
    for obj in object_list:
        if not isinstance(obj, Shape) or isinstance(obj, Sketch):
            raise NotImplementedError("offsetting sketches and lines is not supported on usd-brep yet")
        brep = obj._brep.copy()
        extended = kind == Kind.INTERSECTION
        if opening_faces:
            handles = brep.faces()
            faces = [handles[f._index] for f in opening_faces if f.topo_parent is obj]
            brep = ub.shell_brep(brep, amount, extended_offset=extended, faces_to_shell=faces, create_solid=True)
        else:
            brep = ub.offset_brep(brep, amount, extended_offset=extended)
        results.append(obj._new(brep))
    if context is not None:
        context._add_to_context(*results, mode=mode)
    return results[0] if len(results) == 1 else Compound(results)


def scale(objects=None, by: float | tuple = 1, mode: Mode = Mode.REPLACE):
    object_list, context = _targets(objects)
    factors = tuple(by) if isinstance(by, (tuple, list)) else (by, by, by)
    results = []
    for obj in object_list:
        brep = obj._brep.copy()
        ub.scale(brep, tuple(float(f) for f in factors))
        results.append(obj._new(brep))
    if context is not None:
        context._add_to_context(*results, mode=mode)
    return results[0] if len(results) == 1 else Compound(results)
