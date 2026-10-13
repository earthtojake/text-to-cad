"""build123d's part and sketch objects, built with usd-brep primitives.

Each part object is made where build123d's Solid.make_* puts it (a box from the origin, a
cylinder or cone on the XY plane, a sphere or torus about the origin), then aligned, rotated
and placed at every active location exactly as build123d's BasePartObject does.
"""
from __future__ import annotations

import math

import numpy as np
import usd_brep as ub

from .builders import BuildPart, BuildSketch, current_builder, current_local_locations, current_locations
from .geometry import Align, Location, Mode, Rotation, Vector, align_offset, tuplify
from .topology import Part, Profile, Sketch, combine, flatten, transform

_CENTER3 = (Align.CENTER, Align.CENTER, Align.CENTER)
_CENTER2 = (Align.CENTER, Align.CENTER)


# ------------------------------------------------------------------------ parts
class BasePartObject(Part):
    def __init__(self, brep, bounds, rotation=(0, 0, 0), align=None, mode: Mode = Mode.ADD):
        align = tuplify(align, 3)
        if align is not None:
            transform(brep, Location(align_offset(*bounds, align)).M)
        rotate = Rotation(*rotation) if isinstance(rotation, (tuple, list)) else rotation
        context = current_builder()
        part = Part(brep)
        if isinstance(context, BuildPart):
            placed = [part.moved(loc * rotate) for loc in current_locations()]
            context._add_to_context(*placed, mode=mode)
        else:
            placed = [part.moved(rotate)]
        breps = [p._brep for p in placed]
        super().__init__(combine(breps[0], breps[1:], ub.boolean_union) if len(breps) > 1 else breps[0])
        self.mode = mode


class Box(BasePartObject):
    def __init__(self, length: float, width: float, height: float, rotation=(0, 0, 0), align=_CENTER3,
                 mode: Mode = Mode.ADD):
        self.length, self.width, self.box_height = length, width, height
        super().__init__(ub.create_box((0, 0, 0), length, width, height), ((0, 0, 0), (length, width, height)),
                         rotation, align, mode)


class Cylinder(BasePartObject):
    def __init__(self, radius: float, height: float, arc_size: float = 360, rotation=(0, 0, 0), align=_CENTER3,
                 mode: Mode = Mode.ADD):
        self.radius, self.cylinder_height, self.arc_size = radius, height, arc_size
        if arc_size == 360:
            brep = ub.create_cylinder((0, 0, 0), radius, height)
            bounds = ((-radius, -radius, 0), (radius, radius, height))
        else:
            brep = ub.create_partial_cylinder((0, 0, 0), radius, height, 0.0, arc_size)
            bounds = _sector_bounds(radius, arc_size, 0.0, height)
        super().__init__(brep, bounds, rotation, align, mode)


class Cone(BasePartObject):
    def __init__(self, bottom_radius: float, top_radius: float, height: float, arc_size: float = 360,
                 rotation=(0, 0, 0), align=_CENTER3, mode: Mode = Mode.ADD):
        if arc_size != 360:
            raise NotImplementedError("partial cones are not supported on usd-brep yet")
        self.bottom_radius, self.top_radius, self.cone_height = bottom_radius, top_radius, height
        r = max(bottom_radius, top_radius)
        super().__init__(ub.create_cone((0, 0, 0), bottom_radius, top_radius, height),
                         ((-r, -r, 0), (r, r, height)), rotation, align, mode)


class Sphere(BasePartObject):
    def __init__(self, radius: float, arc_size1: float = -90, arc_size2: float = 90, arc_size3: float = 360,
                 rotation=(0, 0, 0), align=_CENTER3, mode: Mode = Mode.ADD):
        if (arc_size1, arc_size2, arc_size3) != (-90, 90, 360):
            raise NotImplementedError("partial spheres are not supported on usd-brep yet")
        self.radius = radius
        super().__init__(ub.create_sphere((0, 0, 0), radius), ((-radius,) * 3, (radius,) * 3), rotation, align, mode)


class Torus(BasePartObject):
    def __init__(self, major_radius: float, minor_radius: float, minor_start_angle: float = 0,
                 minor_end_angle: float = 360, major_angle: float = 360, rotation=(0, 0, 0), align=_CENTER3,
                 mode: Mode = Mode.ADD):
        if (minor_start_angle, minor_end_angle, major_angle) != (0, 360, 360):
            raise NotImplementedError("partial tori are not supported on usd-brep yet")
        self.major_radius, self.minor_radius = major_radius, minor_radius
        R = major_radius + minor_radius
        super().__init__(ub.create_torus((0, 0, 0), major_radius, minor_radius),
                         ((-R, -R, -minor_radius), (R, R, minor_radius)), rotation, align, mode)


def _sector_bounds(radius, arc_size, z0, z1):
    angles = [0.0, arc_size] + [k * 90.0 for k in range(1, 4) if k * 90.0 < arc_size]
    pts = np.array([(0.0, 0.0)] + [(radius * math.cos(math.radians(a)), radius * math.sin(math.radians(a))) for a in angles])
    return (*pts.min(axis=0), z0), (*pts.max(axis=0), z1)


def _context_depth(depth, what):
    context = current_builder()
    if depth is not None:
        return depth, context
    if isinstance(context, BuildPart):
        return context.max_dimension, context
    raise ValueError(f"No depth provided for {what}")


def _down_cylinder(radius, depth, top=0.0):
    """A cylinder from z=top down to z=top-depth."""
    return ub.create_cylinder((0, 0, top - depth), radius, depth)


class Hole(BasePartObject):
    """build123d's Hole: centred on the location, ``depth`` each way (2 x max_dimension
    when the depth is left to the builder)."""

    def __init__(self, radius: float, depth: float | None = None, mode: Mode = Mode.SUBTRACT):
        depth, _ = _context_depth(depth, "Hole")
        self.radius, self.hole_depth = radius, 2 * depth
        super().__init__(ub.create_cylinder((0, 0, -depth), radius, 2 * depth), ((-radius, -radius, -depth), (radius, radius, depth)),
                         (0, 0, 0), _CENTER3, mode)


class CounterBoreHole(BasePartObject):
    def __init__(self, radius: float, counter_bore_radius: float, counter_bore_depth: float, depth: float | None = None,
                 mode: Mode = Mode.SUBTRACT):
        depth, _ = _context_depth(depth, "CounterBoreHole")
        self.radius, self.counter_bore_radius, self.counter_bore_depth, self.hole_depth = (
            radius, counter_bore_radius, counter_bore_depth, depth)
        bore = ub.create_cylinder((0, 0, -counter_bore_depth), counter_bore_radius, counter_bore_depth + depth)
        brep = ub.boolean_union(_down_cylinder(radius, depth), bore)
        super().__init__(brep, None, (0, 0, 0), None, mode)


class CounterSinkHole(BasePartObject):
    def __init__(self, radius: float, counter_sink_radius: float, depth: float | None = None,
                 counter_sink_angle: float = 82, mode: Mode = Mode.SUBTRACT):
        depth, _ = _context_depth(depth, "CounterSinkHole")
        self.radius, self.counter_sink_radius, self.hole_depth = radius, counter_sink_radius, depth
        cone_height = counter_sink_radius / math.tan(math.radians(counter_sink_angle / 2.0))
        sink = ub.create_cone((0, 0, -cone_height), 0.0, counter_sink_radius, cone_height)
        brep = ub.boolean_union(ub.boolean_union(_down_cylinder(radius, depth), sink),
                                ub.create_cylinder((0, 0, 0), counter_sink_radius, depth))
        super().__init__(brep, None, (0, 0, 0), None, mode)


# ---------------------------------------------------------------------- sketches
class BaseSketchObject(Sketch):
    def __init__(self, loops, rotation: float = 0, align=None, mode: Mode = Mode.ADD):
        profile = Profile(loops)
        align = tuplify(align, 2)
        if align is not None:
            lo, hi = profile.bounds_2d()
            profile = profile.moved(Location(align_offset(lo, hi, align + (Align.NONE,))))
        if rotation:
            profile = profile.moved(Rotation(0, 0, rotation))
        context = current_builder()
        if isinstance(context, BuildSketch):
            pieces = [Sketch.of(profile.moved(loc)) for loc in current_local_locations()]
            tree = pieces[0]._tree
            for piece in pieces[1:]:
                tree = (Mode.ADD, tree, piece._tree)
            context._add_to_context(*pieces, mode=mode)
        else:
            tree = ("leaf", profile)
        super().__init__(tree)
        self.mode = mode


def _polyline(pts):
    pts = [tuple(Vector(p))[:2] for p in pts]
    if np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    return [("line", pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]


class Rectangle(BaseSketchObject):
    def __init__(self, width: float, height: float, rotation: float = 0, align=_CENTER2, mode: Mode = Mode.ADD):
        self.width, self.rectangle_height = width, height
        w, h = width / 2, height / 2
        super().__init__([_polyline([(-w, -h), (w, -h), (w, h), (-w, h)])], rotation, align, mode)


class RectangleRounded(BaseSketchObject):
    def __init__(self, width: float, height: float, radius: float, rotation: float = 0, align=_CENTER2,
                 mode: Mode = Mode.ADD):
        if width <= 2 * radius or height <= 2 * radius:
            raise ValueError("width and height must be > 2*radius")
        self.width, self.rectangle_height, self.radius = width, height, radius
        x, y = width / 2 - radius, height / 2 - radius
        loop = [
            ("line", (-x, -height / 2), (x, -height / 2)), ("arc", (x, -y), radius, -90.0, 0.0),
            ("line", (width / 2, -y), (width / 2, y)), ("arc", (x, y), radius, 0.0, 90.0),
            ("line", (x, height / 2), (-x, height / 2)), ("arc", (-x, y), radius, 90.0, 180.0),
            ("line", (-width / 2, y), (-width / 2, -y)), ("arc", (-x, -y), radius, 180.0, 270.0),
        ]
        super().__init__([loop], rotation, align, mode)


class Circle(BaseSketchObject):
    def __init__(self, radius: float, arc_size: float = 360.0, align=_CENTER2, mode: Mode = Mode.ADD):
        self.radius = radius
        if arc_size == 360.0:
            loop = [("circle", (0.0, 0.0), radius)]
        else:
            end = (radius * math.cos(math.radians(arc_size)), radius * math.sin(math.radians(arc_size)))
            loop = [("line", (0.0, 0.0), (radius, 0.0)), ("arc", (0.0, 0.0), radius, 0.0, float(arc_size)),
                    ("line", end, (0.0, 0.0))]
        super().__init__([loop], 0, align, mode)


class Ellipse(BaseSketchObject):
    def __init__(self, x_radius: float, y_radius: float, rotation: float = 0, align=_CENTER2, mode: Mode = Mode.ADD):
        self.x_radius, self.y_radius = x_radius, y_radius
        super().__init__([[("ellipse", (0.0, 0.0), x_radius, y_radius)]], rotation, align, mode)


class Polygon(BaseSketchObject):
    def __init__(self, *pts, rotation: float = 0, align=(Align.NONE, Align.NONE), mode: Mode = Mode.ADD):
        self.pts = flatten(pts)
        super().__init__([_polyline(self.pts)], rotation, align, mode)


class RegularPolygon(BaseSketchObject):
    def __init__(self, radius: float, side_count: int, major_radius: bool = True, rotation: float = 0,
                 align=_CENTER2, mode: Mode = Mode.ADD):
        rad = radius if major_radius else radius / math.cos(math.pi / side_count)
        self.radius, self.side_count = rad, side_count
        pts = [(rad * math.cos(2 * math.pi * i / side_count), rad * math.sin(2 * math.pi * i / side_count))
               for i in range(side_count)]
        # build123d aligns the polygon by its vertices' box, not the circumscribed circle
        super().__init__([_polyline(pts)], rotation, align, mode)


class SlotOverall(BaseSketchObject):
    def __init__(self, width: float, height: float, rotation: float = 0, align=_CENTER2, mode: Mode = Mode.ADD):
        if width < height:
            raise ValueError(f"Slot requires that width > height. Got: width={width!r}, height={height!r}")
        self.width, self.slot_height = width, height
        if width == height:
            loop = [("circle", (0.0, 0.0), width / 2)]
        else:
            x, r = width / 2 - height / 2, height / 2
            loop = [("line", (-x, -r), (x, -r)), ("arc", (x, 0.0), r, -90.0, 90.0),
                    ("line", (x, r), (-x, r)), ("arc", (-x, 0.0), r, 90.0, 270.0)]
        super().__init__([loop], rotation, align, mode)


class SlotCenterToCenter(BaseSketchObject):
    def __init__(self, center_separation: float, height: float, rotation: float = 0, mode: Mode = Mode.ADD):
        self.center_separation, self.slot_height = center_separation, height
        x, r = center_separation / 2, height / 2
        loop = [("line", (-x, -r), (x, -r)), ("arc", (x, 0.0), r, -90.0, 90.0),
                ("line", (x, r), (-x, r)), ("arc", (-x, 0.0), r, 90.0, 270.0)]
        super().__init__([loop], rotation, None, mode)


class Trapezoid(BaseSketchObject):
    def __init__(self, width: float, height: float, left_side_angle: float, right_side_angle: float | None = None,
                 rotation: float = 0, align=_CENTER2, mode: Mode = Mode.ADD):
        right_side_angle = left_side_angle if right_side_angle is None else right_side_angle
        self.width, self.trapezoid_height = width, height
        left = height / math.tan(math.radians(left_side_angle))
        right = height / math.tan(math.radians(right_side_angle))
        pts = [(-width / 2, -height / 2), (width / 2, -height / 2),
               (width / 2 - right, height / 2), (-width / 2 + left, height / 2)]
        super().__init__([_polyline(pts)], rotation, align, mode)


def placed_sketch(obj) -> Sketch:
    """A sketch from a Sketch or a builder's result."""
    if isinstance(obj, BuildSketch):
        return obj.sketch
    if isinstance(obj, Sketch):
        return obj
    raise TypeError(f"expected a sketch, got {type(obj).__name__}")

