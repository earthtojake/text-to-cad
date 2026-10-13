"""build123d's builder mode: BuildPart, BuildSketch and the location contexts.

The context rules are build123d's own, quirks included: an outer builder is a parent only
when the inner one is opened in the same Python scope, a builder's workplanes start a fresh
location context (so a BuildSketch inside ``Locations`` is not moved by them), and locations
nest by multiplication.
"""
from __future__ import annotations

import contextvars
import inspect
import math
from itertools import product

import usd_brep as ub

from .geometry import Align, Axis, Location, Mode, Plane, Vector, align_offset, tuplify
from .topology import Part, Shape, ShapeList, Sketch, combine, flatten

_BUILDER: contextvars.ContextVar = contextvars.ContextVar("builder", default=None)
_LOCATIONS: contextvars.ContextVar = contextvars.ContextVar("locations", default=None)
_WORKPLANES: contextvars.ContextVar = contextvars.ContextVar("workplanes", default=None)


def current_builder():
    return _BUILDER.get()


def current_locations() -> list[Location]:
    """Global locations of the innermost location context (identity outside any)."""
    context = _LOCATIONS.get()
    return context.locations if context is not None else [Location()]


def current_local_locations() -> list[Location]:
    context = _LOCATIONS.get()
    return context.local_locations if context is not None else [Location()]


def current_workplanes() -> list[Plane]:
    context = _WORKPLANES.get()
    return context.workplanes if context is not None else [Plane.XY]


class LocationList:
    def __init__(self, locations):
        self.local_locations = list(locations)

    def __enter__(self):
        self._tok = _LOCATIONS.set(self)
        return self

    def __exit__(self, *exc):
        _LOCATIONS.reset(self._tok)

    @property
    def locations(self) -> list[Location]:
        return [p.location * loc for p in current_workplanes() for loc in self.local_locations]

    def __iter__(self):
        return iter(self.locations)

    def __len__(self):
        return len(self.local_locations)


def _move_to_existing(local: list[Location]) -> list[Location]:
    outer = _LOCATIONS.get()
    if outer is None:
        return local
    return [g * loc for g in outer.local_locations for loc in local]


class Locations(LocationList):
    def __init__(self, *pts):
        local = []
        for p in flatten(pts):
            if isinstance(p, Location):
                local.append(p)
            elif isinstance(p, Plane):
                local.append(Location(p))
            elif isinstance(p, Axis):
                local.append(p.location)
            elif hasattr(p, "_plane_frame"):
                local.append(Location(Plane(p)))
            else:
                local.append(Location(Vector(p)))
        super().__init__(_move_to_existing(local))


class GridLocations(LocationList):
    def __init__(self, x_spacing: float, y_spacing: float, x_count: int, y_count: int,
                 align=(Align.CENTER, Align.CENTER)):
        if x_count < 1 or y_count < 1:
            raise ValueError(f"At least 1 elements required, requested {x_count}, {y_count}")
        size = (x_spacing * (x_count - 1), y_spacing * (y_count - 1), 0.0)
        offset = align_offset((0.0, 0.0, 0.0), size, tuplify(align, 2) + (Align.NONE,))
        local = [Location(offset + Vector(i * x_spacing, j * y_spacing)) for i, j in product(range(x_count), range(y_count))]
        super().__init__(_move_to_existing(local))


class PolarLocations(LocationList):
    def __init__(self, radius: float, count: int, start_angle: float = 0.0, angular_range: float = 360.0,
                 rotate: bool = True, endpoint: bool = False):
        if count < 1:
            raise ValueError(f"At least 1 elements required, requested {count}")
        step = 0.0 if count == 1 else angular_range / (count - int(endpoint))
        local = []
        for i in range(count):
            angle = start_angle + step * i
            position = Vector(radius * math.cos(math.radians(angle)), radius * math.sin(math.radians(angle)))
            local.append(Location(position, (0, 0, 1), angle if rotate else 0.0))
        super().__init__(_move_to_existing(local))


class _Workplanes:
    def __init__(self, planes):
        self.workplanes = planes

    def __enter__(self):
        self._tok = _WORKPLANES.set(self)
        self._locs = LocationList([Location()]).__enter__()
        return self

    def __exit__(self, *exc):
        _WORKPLANES.reset(self._tok)
        self._locs.__exit__()


def _to_planes(workplanes) -> list[Plane]:
    return [p if isinstance(p, Plane) else Plane(p) for p in flatten(workplanes)]


class _Builder:
    def __init__(self, *workplanes, mode: Mode = Mode.ADD):
        self.mode = mode
        self.workplanes = _to_planes(workplanes) or [Plane.XY]
        self._python_frame = inspect.currentframe().f_back.f_back  # whoever called BuildPart(...)
        self.builder_parent = None

    def __enter__(self):
        context = _BUILDER.get()
        if context is not None and context._python_frame is inspect.currentframe().f_back:
            self.builder_parent = context
        self._tok = _BUILDER.set(self)
        self._wp = _Workplanes(self.workplanes).__enter__()
        return self

    def __exit__(self, exc_type, *exc):
        _BUILDER.reset(self._tok)
        if self.builder_parent is not None and self.mode != Mode.PRIVATE and exc_type is None:
            # still on this builder's workplanes, as in build123d
            self.builder_parent._add_to_context(self._result(), mode=self.mode)
        self._wp.__exit__()


class BuildPart(_Builder):
    _tag = "BuildPart"

    def __init__(self, *workplanes, mode: Mode = Mode.ADD):
        super().__init__(*workplanes, mode=mode)
        self._part: Part | None = None
        self.pending: list[tuple[Sketch, Plane]] = []

    @property
    def part(self) -> Part | None:
        return self._part

    _obj = part

    def _result(self):
        return self._part

    @property
    def max_dimension(self) -> float:
        return self._part.bounding_box().diagonal if self._part is not None else 0.0

    def edges(self) -> ShapeList:
        return self._part.edges() if self._part is not None else ShapeList()

    def faces(self) -> ShapeList:
        return self._part.faces() if self._part is not None else ShapeList()

    def vertices(self) -> ShapeList:
        return self._part.vertices() if self._part is not None else ShapeList()

    def solids(self) -> ShapeList:
        return self._part.solids() if self._part is not None else ShapeList()

    def _add_to_context(self, *objects, mode: Mode = Mode.ADD):
        if mode == Mode.PRIVATE:
            return
        objects = [o for o in flatten(objects) if o is not None]
        for sketch in (o for o in objects if isinstance(o, Sketch)):
            for plane in current_workplanes():
                self.pending.append((sketch.moved(plane.location), plane))
        solids = [o for o in objects if isinstance(o, Shape) and not isinstance(o, Sketch)]
        if not solids:
            return
        breps = [s._brep for s in solids]
        if mode == Mode.ADD:
            if self._part is None:
                self._part = Part(combine(breps[0], breps[1:], ub.boolean_union))
            else:
                self._part = Part(combine(self._part._brep, breps, ub.boolean_union))
        elif mode == Mode.SUBTRACT:
            if self._part is None:
                raise RuntimeError("Nothing to subtract from")
            self._part = Part(combine(self._part._brep, breps, ub.boolean_difference))
        elif mode == Mode.INTERSECT:
            if self._part is None:
                raise RuntimeError("Nothing to intersect with")
            tool = combine(breps[0], breps[1:], ub.boolean_union)
            self._part = Part(ub.boolean_intersection(self._part._brep.copy(), tool))
        elif mode == Mode.REPLACE:
            self._part = Part(combine(breps[0], breps[1:], ub.boolean_union))


class BuildSketch(_Builder):
    _tag = "BuildSketch"

    def __init__(self, *workplanes, mode: Mode = Mode.ADD):
        super().__init__(*workplanes, mode=mode)
        self._local = Sketch()

    def _result(self):
        return self._local

    @property
    def sketch_local(self) -> Sketch:
        return self._local

    _obj = sketch_local

    @property
    def sketch(self) -> Sketch:
        tree = None
        for plane in self.workplanes:
            placed = self._local.moved(plane.location)
            tree = placed._tree if tree is None else (Mode.ADD, tree, placed._tree)
        return Sketch(tree)

    def _add_to_context(self, *objects, mode: Mode = Mode.ADD):
        if mode == Mode.PRIVATE:
            return
        for sketch in flatten(objects):
            if mode == Mode.REPLACE:
                self._local = sketch
            else:
                self._local = self._local.combine(mode, sketch)
