"""Stand-ins for CadQuery's classes, as the cadquery integration's bridge reads them (``cad.cadquery._bridge``).

The bridge never imports CadQuery: it tells a value by the names and modules of its class's ancestry
(``Workplane`` in ``cadquery.cq``, ``Shape`` in ``cadquery.occ_impl.shapes``, ``Sketch`` in ``cadquery.sketch``,
``Assembly`` in ``cadquery.assembly``) and reads the attributes those classes have -- a Workplane's ``vals()``,
a Shape's ``wrapped`` and ``label``, a Sketch's ``_faces``, an Assembly's ``name``, ``obj``, ``loc`` (its
``wrapped``, a ``TopLoc_Location``), ``color`` (its ``toTuple()``) and ``children``. These classes have exactly
that, on shapes build123d makes (the kernel these tests run), so the bridge, the engine's reading of its
description and the hand-over through a daemon are tested where CadQuery is not installed; the KiCad-style
job of ``cad[cadquery]`` (``tests/python/packages/cadquery``) runs the real thing.

A file of its own, with no import of the test support, so a test writes it beside a program it runs.
"""

from __future__ import annotations

from typing import Any


class Shape:
    __module__ = "cadquery.occ_impl.shapes"

    def __init__(self, wrapped: Any, label: str = "") -> None:
        self.wrapped = wrapped
        self.label = label


class Compound(Shape):
    __module__ = "cadquery.occ_impl.shapes"


class Workplane:
    __module__ = "cadquery.cq"

    def __init__(self, *objects: Any) -> None:
        self.objects = list(objects)

    def vals(self) -> list[Any]:
        return list(self.objects)


class Sketch:
    __module__ = "cadquery.sketch"

    def __init__(self, faces: Any) -> None:
        self._faces = faces


class Vector:
    __module__ = "cadquery.occ_impl.geom"


class Color:
    __module__ = "cadquery.occ_impl.assembly"

    def __init__(self, red: float, green: float, blue: float, alpha: float = 1.0) -> None:
        self.channels = (red, green, blue, alpha)

    def toTuple(self) -> tuple[float, float, float, float]:  # noqa: N802 - CadQuery's spelling
        return self.channels


class Location:
    __module__ = "cadquery.occ_impl.geom"

    def __init__(self, wrapped: Any) -> None:
        self.wrapped = wrapped


class Assembly:
    __module__ = "cadquery.assembly"

    def __init__(self, obj: Any = None, loc: Location | None = None, name: str | None = None,
                 color: Color | None = None) -> None:
        self.obj = obj
        self.loc = loc if loc is not None else identity()
        self.name = name or "assembly"
        self.color = color
        self.children: list[Assembly] = []

    def add(self, obj: Any, loc: Location | None = None, name: str | None = None, color: Color | None = None) -> "Assembly":
        child = obj if isinstance(obj, Assembly) else Assembly(obj, loc, name, color)
        if isinstance(obj, Assembly) and loc is not None:
            child.loc = loc
        self.children.append(child)
        return self


def identity() -> Location:
    from OCP.TopLoc import TopLoc_Location

    return Location(TopLoc_Location())


def at(x: float, y: float, z: float) -> Location:
    """A placement by a translation, as CadQuery's ``Location(Vector(x, y, z))``."""
    from OCP.gp import gp_Trsf, gp_Vec
    from OCP.TopLoc import TopLoc_Location

    moved = gp_Trsf()
    moved.SetTranslation(gp_Vec(x, y, z))
    return Location(TopLoc_Location(moved))


def box(length: float, width: float, height: float) -> Workplane:
    """A box on the stack, as ``cq.Workplane("XY").box(...)`` leaves one."""
    import build123d as bd

    return Workplane(Shape(bd.Box(length, width, height).wrapped))


def plate() -> Workplane:
    """A 40 x 20 x 6 plate with an 8 mm hole through it, as a CadQuery chain would leave it on the stack."""
    import build123d as bd

    body = bd.Box(40, 20, 6) - bd.Cylinder(4, 6)
    return Workplane(Shape(body.wrapped))


def peg() -> Workplane:
    import build123d as bd

    return Workplane(Shape(bd.Cylinder(2, 10).wrapped))


def bracket_assembly() -> Assembly:
    """A two-part assembly: the plate, blue, and a red peg standing on it at (10, 0, 8)."""
    found = Assembly(name="bracket_assembly")
    found.add(plate(), name="plate", color=Color(0.3, 0.5, 0.8))
    found.add(peg(), loc=at(10, 0, 8), name="peg", color=Color(1.0, 0.0, 0.0))
    return found
