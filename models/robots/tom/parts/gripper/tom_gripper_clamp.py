from __future__ import annotations

import build123d
from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

from tom_gripper_o1_5 import (
    SOURCE_STEP,
    _cast_shape,
    _cut_topods,
    _occurrence_shape,
    load_step_scene,
    occurrence_selector_id,
)

# Upstream RB9.01.062.020_Clamp grips each 6.00 mm rod (Rod_d6_125) with a 5.70 mm
# tube slot -> 0.30 mm diametral interference. Open the slot bore to 5.90 mm so the
# clamp keeps a lighter 0.10 mm grip on the rod instead.
SLOT_RADIUS = 2.85
RELIEVED_RADIUS = 2.95
RADIUS_TOL = 0.01


def _slot_axis_groups(shape: build123d.Shape) -> dict:
    """Group a shape's r2.85 cylindrical tube-slot faces by axis line, tracking each
    group's axial extent so the relief cut stays confined to the slot."""
    groups: dict = {}
    explorer = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        surface = BRepAdaptor_Surface(face)
        if surface.GetType() == GeomAbs_Cylinder and abs(surface.Cylinder().Radius() - SLOT_RADIUS) < RADIUS_TOL:
            axis = surface.Cylinder().Axis()
            p = axis.Location()
            d = axis.Direction()
            point = (p.X(), p.Y(), p.Z())
            direction = (d.X(), d.Y(), d.Z())
            t_point = sum(point[i] * direction[i] for i in range(3))
            foot = tuple(round(point[i] - t_point * direction[i], 2) for i in range(3))
            direction_key = tuple(round(abs(c), 3) for c in direction)

            box = Bnd_Box()
            BRepBndLib.Add_s(face, box, False)
            xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
            corners = (
                (xmin, ymin, zmin), (xmax, ymin, zmin), (xmin, ymax, zmin), (xmax, ymax, zmin),
                (xmin, ymin, zmax), (xmax, ymin, zmax), (xmin, ymax, zmax), (xmax, ymax, zmax),
            )
            projections = [sum(c[i] * direction[i] for i in range(3)) for c in corners]
            lo, hi = min(projections), max(projections)

            key = (foot, direction_key)
            group = groups.get(key)
            if group is None:
                groups[key] = [point, direction, lo, hi]
            else:
                group[2] = min(group[2], lo)
                group[3] = max(group[3], hi)
        explorer.Next()
    return groups


def relieve_slots(shape: build123d.Shape, *, margin: float = 0.5) -> build123d.Shape:
    """Open every r2.85 tube slot in the shape to r2.95 with a coaxial cut spanning only
    the slot's axial extent. Shapes without such slots are returned unchanged."""
    groups = _slot_axis_groups(shape)
    if not groups:
        return shape

    tools = []
    for point, direction, lo, hi in groups.values():
        t_point = sum(point[i] * direction[i] for i in range(3))
        start = lo - margin
        base = gp_Pnt(*[point[i] + (start - t_point) * direction[i] for i in range(3)])
        length = (hi - lo) + 2 * margin
        axis = gp_Ax2(base, gp_Dir(*direction))
        tools.append(BRepPrimAPI_MakeCylinder(axis, RELIEVED_RADIUS, length).Shape())

    result = _cast_shape(_cut_topods(shape.wrapped, *tools))
    result.label = shape.label
    color = getattr(shape, "color", None)
    if color is not None:
        result.color = color
    if not result.is_valid:
        raise RuntimeError("Clamp slot relief produced invalid geometry")
    return result


def build_relieved_gripper() -> build123d.Shape:
    """Compose the full gripper with every clamp tube slot opened from 5.70 mm to 5.90 mm
    (0.30 mm -> 0.10 mm diametral interference on the 6 mm rods)."""
    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"Missing source STEP: {SOURCE_STEP}")
    scene = load_step_scene(SOURCE_STEP)
    parts: list[build123d.Shape] = []
    stack = list(reversed(scene.roots))
    while stack:
        node = stack.pop()
        if getattr(node, "prototype_key", None) in scene.prototype_shapes:
            parts.append(relieve_slots(_occurrence_shape(scene, node)))
        stack.extend(reversed(node.children))
    if not parts:
        raise RuntimeError("No occurrences composed for the relieved gripper")
    result = build123d.Compound(children=parts)
    result.label = "tom_gripper_clamp_relief"
    return result


def build_relieved_clamp(selector: str = "o1.12") -> build123d.Shape:
    """Just the relieved clamp part (for reprinting), opened to r2.95."""
    scene = load_step_scene(SOURCE_STEP)
    stack = list(reversed(scene.roots))
    while stack:
        node = stack.pop()
        if occurrence_selector_id(node) == selector:
            shape = relieve_slots(_occurrence_shape(scene, node))
            shape.label = "tom_gripper_clamp_relief_part"
            return shape
        stack.extend(reversed(node.children))
    raise RuntimeError(f"Selector {selector} not found in {SOURCE_STEP}")
