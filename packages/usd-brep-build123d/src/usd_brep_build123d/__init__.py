"""build123d's modeling language on NVIDIA's usd-brep kernel (SMLib), without OpenCascade.

    import usd_brep_build123d as bd

    with bd.BuildPart() as flange:
        bd.Cylinder(40, 10, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        with bd.PolarLocations(30, 6):
            bd.Hole(3)
    bd.export_usd(flange.part, "flange.usda")

The same scripts build the same solids as build123d for the features listed in the
package README; anything else raises rather than approximating. Output is exact B-rep in
OpenUSD (``export_usd``); ``usd_brep_build123d.occt`` converts to OpenCascade when that is
needed.
"""
from __future__ import annotations

from .builders import BuildPart, BuildSketch, GridLocations, LocationList, Locations, PolarLocations
from .exporters import export_usd, import_usd
from .geometry import (
    Align, Axis, BoundBox, Color, GeomType, Keep, Kind, Location, Mode, Plane, Pos, Rot, Rotation, SortBy, Vector,
)
from .objects import (
    BasePartObject, BaseSketchObject, Box, Circle, Cone, CounterBoreHole, CounterSinkHole, Cylinder, Ellipse, Hole,
    Polygon, Rectangle, RectangleRounded, RegularPolygon, SlotCenterToCenter, SlotOverall, Sphere, Torus, Trapezoid,
)
from .operations import add, blend, chamfer, extrude, fillet, loft, mirror, offset, revolve, scale, split
from .topology import Compound, Edge, Face, Part, Shape, ShapeList, Sketch, Solid, Vertex

__all__ = [
    # builders
    "BuildPart", "BuildSketch", "Locations", "GridLocations", "PolarLocations", "LocationList",
    # geometry
    "Align", "Axis", "BoundBox", "Color", "GeomType", "Keep", "Kind", "Location", "Mode", "Plane", "Pos", "Rot",
    "Rotation", "SortBy", "Vector",
    # objects
    "BasePartObject", "Box", "Cylinder", "Cone", "Sphere", "Torus", "Hole", "CounterBoreHole", "CounterSinkHole",
    "BaseSketchObject", "Rectangle", "RectangleRounded", "Circle", "Ellipse", "Polygon", "RegularPolygon",
    "SlotOverall", "SlotCenterToCenter", "Trapezoid",
    # operations
    "add", "chamfer", "extrude", "fillet", "loft", "mirror", "offset", "revolve", "scale", "split",
    # topology
    "Shape", "Part", "Solid", "Compound", "Sketch", "Face", "Edge", "Vertex", "ShapeList",
    # usd-brep extensions and I/O
    "blend", "export_usd", "import_usd",
]
