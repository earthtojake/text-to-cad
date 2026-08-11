#!/usr/bin/env python3
"""
Camera tripod stand assembly: tom gripper camera mount stood up vertically.

Components:
- A printable stand = the quarter20_tripod_thread_block (female 1/4-20 hole
  underneath that screws onto a standard tripod stud, e.g.
  amazon.com/dp/B0BV2SBWVD) carrying a vertical plate that reproduces the EXACT
  screw holes and outline cuts of the gripper finger-mount face
  tom_gripper.step #o1.5.f55, plus a base buttress behind it (below the holes)
  for a strong, support-free print.
- The camera tom_gripper.step #o1.9, placed on the mount as a reference so the
  fit and orientation are unambiguous.

Both the mount plate and the camera are mapped from the gripper by the SAME
rigid transform that takes the f55 frame to a vertical, forward-facing (-Y)
pose, so the camera lands on the reproduced bolt pattern exactly as it sits on
the real gripper finger -- just rotated upright off the tripod.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import build123d as bd
from cadgen import step_scene as _scene

HERE = Path(__file__).resolve().parent
PART_NAME = Path(__file__).stem
GRIPPER_STEP = HERE.parent / "parts" / "gripper" / "tom_gripper.step"


def _load_entry(step_py_path: Path):
    spec = importlib.util.spec_from_file_location(step_py_path.stem, step_py_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BLOCK = _load_entry(HERE / "quarter20_tripod_thread_block.step.py")

# --- f55 mount-face signature (from inspect of tom_gripper.step #o1.5.f55) ---
F55_AREA_MM2 = 1744.144361
F55_CENTER = bd.Vector(-0.0020769999999998845, 63.028673999999995, -29.4561435)
F55_NORMAL = bd.Vector(0.0, -0.5, 0.866025)            # outward (front of pad)
CAMERA_OCCURRENCE_PATH = (1, 9)                         # tom_gripper.step #o1.9

PLATE_THICKNESS_MM = 5.0
BLOCK_TOP_Z = BLOCK.BLOCK_Z_MM                          # 15.0
BLOCK_DEPTH_HALF_MM = BLOCK.BLOCK_Y_MM / 2.0           # 20.0 (block extent in y)
PLATE_EMBED_MM = 2.0                                    # sink plate into block top
# Top of the diagonal gussets == bottom of the flat mount face. The flat face
# above this is squared off (its height is made equal to the plate width), and
# the bolt pattern is shifted up to sit centered in that square.
GUSSET_TOP_Z = 26.0

PLASTIC_COLOR = bd.Color(1.0, 1.0, 1.0, 1.0)
CAMERA_COLOR = bd.Color(0.18, 0.18, 0.20, 1.0)


# --------------------------------------------------------------------------
# Geometry pulled from the gripper
# --------------------------------------------------------------------------
def _extract_f55_face() -> bd.Face:
    """Find the exact planar face #o1.5.f55 in the gripper STEP."""
    shape = bd.import_step(str(GRIPPER_STEP))
    candidates = []  # (is_front, center_dist, face)
    for f in shape.faces():
        if f.geom_type != bd.GeomType.PLANE:
            continue
        if abs(f.area - F55_AREA_MM2) > 2.0:
            continue
        n = f.normal_at(f.center())
        if abs(n.dot(F55_NORMAL)) < 0.9:
            continue
        d = (bd.Vector(f.center()) - F55_CENTER).length
        if d > 8.0:
            continue
        candidates.append((n.dot(F55_NORMAL) > 0.0, d, f))
    if not candidates:
        raise RuntimeError("Could not locate gripper mount face #o1.5.f55")
    candidates.sort(key=lambda t: (not t[0], t[1]))
    return candidates[0][2]


def _extract_camera() -> bd.Shape:
    """Pull occurrence #o1.9 (the camera) out of the gripper assembly tree."""
    scene = _scene.load_step_scene(GRIPPER_STEP)

    def walk(nodes):
        for node in nodes:
            yield node
            yield from walk(node.children)

    node = next((n for n in walk(scene.roots)
                 if tuple(n.path) == CAMERA_OCCURRENCE_PATH), None)
    if node is None:
        raise RuntimeError("Could not locate camera occurrence #o1.9")
    shp = _scene.scene_occurrence_shape(scene, node)
    cam = shp if isinstance(shp, bd.Shape) else bd.Shape(shp)
    cam.label = "camera_o1_9"
    cam.color = CAMERA_COLOR
    return cam


# --------------------------------------------------------------------------
# Transform: f55 frame -> vertical, forward-facing (-Y), right-way-up
# --------------------------------------------------------------------------
def _mount_transform(face: bd.Face, plate_pre: bd.Shape) -> bd.Location:
    """Rigid transform mapping gripper coords to the seated vertical mount.

    Maps the pad's in-plane X to world X, the outward normal to world -Y
    (forward), and flips it upright so the camera reads right-way-up. The same
    transform is applied to the plate and the camera so their fit is preserved.
    """
    src = bd.Plane(origin=face.center(), x_dir=(1.0, 0.0, 0.0),
                   z_dir=face.normal_at(face.center()))
    tgt = bd.Plane(origin=(0.0, 0.0, 0.0), x_dir=(1.0, 0.0, 0.0),
                   z_dir=(0.0, -1.0, 0.0))
    loc_pre = bd.Location((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 180.0) \
        * (tgt.location * src.location.inverse())

    # Seat: centre in X and drop so the plate bottom embeds into the block top.
    bb = plate_pre.moved(loc_pre).bounding_box()
    dx = -0.5 * (bb.min.X + bb.max.X)
    dz = (BLOCK_TOP_Z - PLATE_EMBED_MM) - bb.min.Z
    return bd.Location((dx, 0.0, dz)) * loc_pre


def _lowest_hole_z(plate: bd.Shape) -> float | None:
    fwd = bd.Vector(0.0, -1.0, 0.0)
    faces = [f for f in plate.faces()
             if f.geom_type == bd.GeomType.PLANE
             and f.normal_at(f.center()).dot(fwd) > 0.9]
    if not faces:
        return None
    front = max(faces, key=lambda f: f.area)
    zs = [w.bounding_box().min.Z for w in front.inner_wires()]
    return min(zs) if zs else None


def _widened_block(x_half: float) -> bd.Shape:
    """Female-thread base block, widened in x to be flush with the mount plate."""
    base = BLOCK.build_step()
    bb = base.bounding_box()
    add = x_half - bb.max.X
    if add > 1e-6:
        for sign in (+1.0, -1.0):
            x0 = sign * bb.max.X if sign > 0 else -x_half
            bar = bd.Solid.make_box(
                add, BLOCK.BLOCK_Y_MM, BLOCK_TOP_Z,
                plane=bd.Plane(origin=bd.Vector(x0, -BLOCK_DEPTH_HALF_MM, 0.0)),
            )
            base = base.fuse(bar)
    return base


def _y_wedge(y_inner: float, y_outer: float, z0: float, z_top: float,
             x_half: float) -> bd.Shape:
    """A diagonal gusset: vertical against the plate at y_inner, sloping out to
    y_outer at the block top, extruded across the full width."""
    tri = bd.make_face(
        bd.Polyline(
            (0.0, y_inner, z0),
            (0.0, y_inner, z_top),
            (0.0, y_outer, z0),
            close=True,
        )
    )
    return bd.extrude(tri, amount=x_half, both=True)


# --------------------------------------------------------------------------
def build_step() -> bd.Shape:
    face = _extract_f55_face()
    plate_pre = bd.extrude(face, amount=-PLATE_THICKNESS_MM)
    final = _mount_transform(face, plate_pre)
    plate_f55 = plate_pre.moved(final)       # f55-outline plate (just to read holes)

    pbb = plate_f55.bounding_box()
    x_half = pbb.max.X                       # 26 -> square side = 2*x_half = 52
    y_back = pbb.min.Y                       # 0  (back face)
    y_front = pbb.max.Y                      # 5  (mount face, camera side)
    z0 = BLOCK_TOP_Z - PLATE_EMBED_MM
    side = 2.0 * x_half                      # square flat-face side == plate width
    plate_top = GUSSET_TOP_Z + side          # flat face (z GUSSET_TOP..top) is square

    # Bolt pattern from f55, shifted up to sit centered in the flat square.
    front = max(
        (f for f in plate_f55.faces()
         if f.geom_type == bd.GeomType.PLANE and f.normal_at(f.center()).dot(bd.Vector(0, 1, 0)) > 0.9),
        key=lambda f: f.area,
    )
    holes = list(front.inner_wires())
    z_lo = min(w.bounding_box().min.Z for w in holes)
    z_hi = max(w.bounding_box().max.Z for w in holes)
    dz = (GUSSET_TOP_Z + side / 2.0) - 0.5 * (z_lo + z_hi)   # centre pattern in square

    # Square mount plate carrying the (shifted) bolt pattern.
    box = bd.Solid.make_box(
        side, y_front - y_back, plate_top - z0,
        plane=bd.Plane(origin=bd.Vector(-x_half, y_back, z0)),
    )
    cutters = None
    for w in holes:
        cut = bd.extrude(bd.make_face(w), amount=2.0 * PLATE_THICKNESS_MM,
                         both=True).moved(bd.Location((0.0, 0.0, dz)))
        cutters = cut if cutters is None else cutters.fuse(cut)
    plate = box.cut(cutters)

    # Re-cut the large central wire-passage opening. On f55 it was part of the
    # finger-contour outline (not a closed bolt hole), so squaring the outline
    # dropped it; recover it as the largest "square minus f55" region and shift
    # it up with the rest of the pattern so it stays behind the camera cable.
    f55_bb = plate_f55.bounding_box()
    full = bd.Solid.make_box(
        side, y_front - y_back, f55_bb.size.Z,
        plane=bd.Plane(origin=bd.Vector(-x_half, y_back, f55_bb.min.Z)),
    )
    wire_hole = max(full.cut(plate_f55).solids(), key=lambda s: s.volume)
    plate = plate.cut(wire_hole.moved(bd.Location((0.0, 0.0, dz))))

    camera = _extract_camera().moved(final).moved(bd.Location((0.0, 0.0, dz)))

    base = _widened_block(x_half)
    # Diagonal gussets on both faces, blending the wide block up to the square plate.
    back_gusset = _y_wedge(y_back, -BLOCK_DEPTH_HALF_MM, z0, GUSSET_TOP_Z, x_half)
    front_gusset = _y_wedge(y_front, BLOCK_DEPTH_HALF_MM, z0, GUSSET_TOP_Z, x_half)

    stand = base.fuse(plate).fuse(back_gusset).fuse(front_gusset)
    stand_solids = sorted(stand.solids(), key=lambda s: -s.volume)
    if len(stand_solids) != 1:
        raise RuntimeError(f"Stand should be one solid, found {len(stand_solids)}")
    stand = stand_solids[0]
    stand.label = "camera_tripod_stand"
    stand.color = PLASTIC_COLOR

    assembly = bd.Compound(children=[stand, camera])
    assembly.label = PART_NAME
    bb = assembly.bounding_box()
    print(
        "Camera tripod stand assembly (gripper f55 mount + camera o1.9) "
        f"size={bb.max.X - bb.min.X:.1f} x {bb.max.Y - bb.min.Y:.1f} x {bb.max.Z - bb.min.Z:.1f} mm, "
        f"plate_thickness={PLATE_THICKNESS_MM:.1f} mm, base_female=1/4-20"
    )
    return assembly


def gen_step() -> dict[str, object]:
    return {"shape": build_step()}


if __name__ == "__main__":
    gen_step()
