from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path

import build123d
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GeomAbs import GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from build123d.topology import downcast
from build123d.topology.shape_core import shapetype

REPO_ROOT = Path(__file__).resolve().parents[5]
PACKAGE_SRC = REPO_ROOT / "packages" / "cadgen" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

os.environ.setdefault("XDG_CACHE_HOME", str(REPO_ROOT / ".cache"))
os.environ.setdefault("EZDXF_CACHE_HOME", str(REPO_ROOT / ".cache" / "ezdxf"))

from cadgen.step_scene import located_shape, load_step_scene, occurrence_selector_id


SOURCE_STEP = Path(__file__).resolve().with_name("tom_gripper.step")
TARGET_OCCURRENCE = "o1.5"
PATTERN_ROTATION_DEG = 45.0
M2_HOLE_RADIUS = 1.6
CENTER_HOLE_RADIUS = 3.0
MOUNTING_FACE_Z = -52.0
CONNECTOR_CORE_RADIUS = 10.9
CONNECTOR_CORE_DEPTH = 10.0
CONNECTOR_CORE_TOP_Z = -42.0
BOTTOM_CUT_OVERSHOOT = 0.2
RECESS_TOP_Z = -39.0
RECESS_TOP_CUT_OVERSHOOT = 0.2
HOLE_EXIT_Z = -38.8

# Centers from #o1.5.e75, #o1.5.e83, #o1.5.e93, #o1.5.e103.
ORIGINAL_HOLE_CENTERS = (
    (-4.951824, 4.951824),
    (4.947670, 4.951824),
    (-4.951824, -4.947670),
    (4.947670, -4.947670),
)
PATTERN_CENTER = (-0.002077, 0.002077)


def _cast_shape(obj: object) -> build123d.Shape:
    occt_shape = downcast(obj)
    shape_name = build123d.Shape.shape_LUT[shapetype(occt_shape)]
    shape_type = getattr(build123d, shape_name)
    return shape_type.cast(occt_shape)


def _unify_same_domain(shape: object) -> object:
    unified = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
    unified.Build()
    return unified.Shape()


def _fuse_topods(base: object, *tools: object) -> object:
    result = base
    for tool in tools:
        fuse = BRepAlgoAPI_Fuse(result, tool)
        fuse.SetRunParallel(True)
        fuse.Build()
        result = _unify_same_domain(fuse.Shape())
    return result


def _cut_topods(base: object, *tools: object) -> object:
    result = base
    for tool in tools:
        cut = BRepAlgoAPI_Cut(result, tool)
        cut.SetRunParallel(True)
        cut.Build()
        result = _unify_same_domain(cut.Shape())
    return result


def _face_area_center(face: object) -> tuple[float, tuple[float, float, float]]:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    center = props.CentreOfMass()
    return props.Mass(), (center.X(), center.Y(), center.Z())


def _find_recess_floor_face(shape: object) -> object:
    candidates: list[tuple[float, float, object]] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        surface = BRepAdaptor_Surface(face)
        if surface.GetType() == GeomAbs_Plane:
            area, center = _face_area_center(face)
            dx = center[0] - PATTERN_CENTER[0]
            dy = center[1] - PATTERN_CENTER[1]
            if (
                abs(center[2] - CONNECTOR_CORE_TOP_Z) <= 0.01
                and 100.0 <= area <= 260.0
                and math.hypot(dx, dy) <= 2.0
            ):
                candidates.append((math.hypot(dx, dy), -area, face))
        explorer.Next()

    if not candidates:
        raise RuntimeError("Could not find connector recess floor face at z=-42")
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _recess_prism_tool(recess_floor_face: object, *, z_max: float) -> object:
    height = z_max - CONNECTOR_CORE_TOP_Z
    prism = BRepPrimAPI_MakePrism(recess_floor_face, gp_Vec(0.0, 0.0, height))
    prism.Build()
    return _unify_same_domain(prism.Shape())


def _rotate_topods_about_pattern_center(shape: object, angle_deg: float) -> object:
    transform = gp_Trsf()
    transform.SetRotation(
        gp_Ax1(gp_Pnt(PATTERN_CENTER[0], PATTERN_CENTER[1], 0.0), gp_Dir(0.0, 0.0, 1.0)),
        math.radians(angle_deg),
    )
    rotated = BRepBuilderAPI_Transform(shape, transform, True)
    rotated.Build()
    return _unify_same_domain(rotated.Shape())


def _safe_label(text: str | None, fallback: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", text or "").strip("_")
    return value or fallback


def _find_occurrence(scene: object, selector: str) -> object:
    stack = list(reversed(scene.roots))
    while stack:
        node = stack.pop()
        if occurrence_selector_id(node) == selector:
            return node
        stack.extend(reversed(node.children))
    raise RuntimeError(f"Selector {selector} not found in {SOURCE_STEP}")


def _occurrence_shape(scene: object, occurrence: object) -> build123d.Shape:
    if occurrence.prototype_key not in scene.prototype_shapes:
        raise RuntimeError(f"Occurrence {TARGET_OCCURRENCE} has no prototype shape")
    shape = _cast_shape(located_shape(scene.prototype_shapes[occurrence.prototype_key], occurrence.location))
    shape.label = _safe_label(
        occurrence.source_name or occurrence.name,
        occurrence_selector_id(occurrence).replace(".", "_"),
    )
    color = getattr(occurrence, "color", None) or scene.prototype_colors.get(occurrence.prototype_key)
    if color is not None:
        shape.color = build123d.Color(*color)
    return shape


def _cylinder_tool(
    *,
    center_xy: tuple[float, float],
    radius: float,
    z_min: float,
    z_max: float,
) -> build123d.Solid:
    height = z_max - z_min
    return build123d.Cylinder(
        radius=radius,
        height=height,
        align=(build123d.Align.CENTER, build123d.Align.CENTER, build123d.Align.CENTER),
    ).locate(
        build123d.Location(
            (
                center_xy[0],
                center_xy[1],
                z_min + height / 2.0,
            )
        )
    )


def _through_m2_hole_tool(center_xy: tuple[float, float]) -> build123d.Solid:
    return _cylinder_tool(
        center_xy=center_xy,
        radius=M2_HOLE_RADIUS,
        z_min=MOUNTING_FACE_Z - BOTTOM_CUT_OVERSHOOT,
        z_max=HOLE_EXIT_Z,
    )


def _center_hole_tool() -> build123d.Solid:
    return _cylinder_tool(
        center_xy=PATTERN_CENTER,
        radius=CENTER_HOLE_RADIUS,
        z_min=MOUNTING_FACE_Z - BOTTOM_CUT_OVERSHOOT,
        z_max=HOLE_EXIT_Z,
    )


def _connector_core_tool() -> build123d.Solid:
    return build123d.Cylinder(
        radius=CONNECTOR_CORE_RADIUS,
        height=CONNECTOR_CORE_DEPTH,
        align=(build123d.Align.CENTER, build123d.Align.CENTER, build123d.Align.CENTER),
    ).locate(
        build123d.Location(
            (
                PATTERN_CENTER[0],
                PATTERN_CENTER[1],
                (MOUNTING_FACE_Z + CONNECTOR_CORE_TOP_Z) / 2.0,
            )
        )
    )


def _rotated_centers() -> tuple[tuple[float, float], ...]:
    angle = math.radians(PATTERN_ROTATION_DEG)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    cx, cy = PATTERN_CENTER
    centers: list[tuple[float, float]] = []
    for x, y in ORIGINAL_HOLE_CENTERS:
        dx = x - cx
        dy = y - cy
        centers.append((cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a))
    return tuple(centers)


def build_o1_5(*, rotate_m2_pattern: bool = False) -> build123d.Shape:
    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"Missing source STEP: {SOURCE_STEP}")

    scene = load_step_scene(SOURCE_STEP)
    shape = _occurrence_shape(scene, _find_occurrence(scene, TARGET_OCCURRENCE))
    if not rotate_m2_pattern:
        shape.label = "tom_gripper_o1_5"
        return shape

    filled = _fuse_topods(shape.wrapped, _connector_core_tool().wrapped)
    recess_floor = _find_recess_floor_face(filled)
    old_recess_fill = _recess_prism_tool(recess_floor, z_max=RECESS_TOP_Z)
    rotated_recess_cut = _rotate_topods_about_pattern_center(
        _recess_prism_tool(
            recess_floor,
            z_max=RECESS_TOP_Z + RECESS_TOP_CUT_OVERSHOOT,
        ),
        PATTERN_ROTATION_DEG,
    )
    rotated_recess = _cut_topods(_fuse_topods(filled, old_recess_fill), rotated_recess_cut)
    cut_shape = _cut_topods(
        rotated_recess,
        _center_hole_tool().wrapped,
        *[_through_m2_hole_tool(center).wrapped for center in _rotated_centers()],
    )
    cut = _cast_shape(cut_shape)
    cut.label = "tom_gripper_mount_rot45"
    if not cut.is_valid:
        raise RuntimeError("Rotated M2 hole pattern boolean produced invalid geometry")
    return cut


def build_minus_o1_5() -> build123d.Shape:
    """Compose the full gripper assembly minus the o1.5 mount occurrence (the camera-holder part
    that the rotated-M2 mount variant replaces)."""
    if not SOURCE_STEP.exists():
        raise FileNotFoundError(f"Missing source STEP: {SOURCE_STEP}")
    scene = load_step_scene(SOURCE_STEP)
    parts: list[build123d.Shape] = []
    stack = list(reversed(scene.roots))
    while stack:
        node = stack.pop()
        if occurrence_selector_id(node) == TARGET_OCCURRENCE:
            continue  # drop the mount occurrence (and any subtree)
        if getattr(node, "prototype_key", None) in scene.prototype_shapes:
            parts.append(_occurrence_shape(scene, node))
        stack.extend(reversed(node.children))
    if not parts:
        raise RuntimeError("No occurrences composed for the minus-mount gripper")
    result = build123d.Compound(children=parts)
    result.label = "tom_gripper_minus_mount"
    return result


def gen_step() -> build123d.Shape:
    return build_o1_5()


if __name__ == "__main__":
    gen_step()
