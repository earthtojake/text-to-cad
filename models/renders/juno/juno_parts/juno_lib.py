"""Shared helpers for the juno humanoid part modules.

Conventions (all part modules must follow):
- Units mm. Robot faces +X, +Y is robot-left, +Z is up.
- Every part builder returns an identity-location build123d Compound whose
  children are closed, labeled, colored solids. Model geometry directly in the
  part's local frame (joint/mate origins as documented per part).
- Limb segments: origin at the proximal joint center, segment extends -Z.
- Exposed actuator cans: cylinder axis along the joint axis, centered at the
  joint center, built with `actuator_solids()`.

Verified joint-attach math (see probe_joint.py): for build123d 0.10,
`revolute_attach()` places the child so its joint plane coincides with the
parent joint plane rotated `angle_deg` about the shared axis.
"""

from __future__ import annotations

import math

from build123d import (
    Axis,
    Box,
    Color,
    Compound,
    Cylinder,
    Location,
    Plane,
    Pos,
    Rot,
    Vector,
    chamfer,
    fillet,
)

# Palette: warm porcelain + graphite + aluminum, with a coral accent on
# small repeated functional details (hub caps, bumpers, vents). No logos.
SHELL = (0.82, 0.815, 0.79)     # warm porcelain composite shells
STRUCT = (0.16, 0.17, 0.19)     # graphite structural cores
ALU = (0.88, 0.90, 0.94)        # bright machined-aluminum joint rims
VISOR = (0.02, 0.05, 0.11)      # gloss midnight-blue sensor glass
RUBBER = (0.08, 0.08, 0.09)     # sole / grip rubber
ACCENT = (0.93, 0.38, 0.16)     # coral-orange accent details
EYE = (0.32, 0.90, 0.98)        # bright cyan display "pixels" (Anki-style)

SHELL_COLOR = Color(*SHELL)
STRUCT_COLOR = Color(*STRUCT)
ALU_COLOR = Color(*ALU)
VISOR_COLOR = Color(*VISOR)
RUBBER_COLOR = Color(*RUBBER)
ACCENT_COLOR = Color(*ACCENT)
EYE_COLOR = Color(*EYE)


def styled(solid, label: str, color: Color):
    solid.label = label
    solid.color = color
    return solid


def part_compound(label: str, children) -> Compound:
    comp = Compound(children=list(children))
    comp.label = label
    return comp


def joint_plane(origin, axis_dir, x_ref) -> Location:
    return Plane(
        origin=Vector(origin), x_dir=Vector(x_ref), z_dir=Vector(axis_dir)
    ).location


def revolute_attach(
    asm,
    parent,
    child,
    name: str,
    p_origin,
    p_axis,
    p_xref,
    c_origin,
    c_axis,
    c_xref,
    angle_deg: float,
):
    """Author a parent revolute frame + child rigid frame and connect them.

    Joint origins/axes are given in each part's LOCAL modeling frame; the
    helper transforms them by each part's current location, so parts that were
    already repositioned by upstream connects keep correct joints (connect in
    root-to-leaf order). At angle 0 the child's c_xref direction aligns with
    the parent's p_xref direction about the shared axis.
    """
    j_p_world = parent.location * joint_plane(p_origin, p_axis, p_xref)
    z_tip = (j_p_world * Pos(0, 0, 1)).position
    axis_world = Axis(j_p_world.position, z_tip - j_p_world.position)
    f_parent = asm.revolute_frame(
        parent, f"{name}_axis", axis_world, angular_range=(-360.0, 360.0)
    )
    # The joint's stored frame may use any x-reference convention; read the
    # actual frame back and fold the constant Rz difference into the child
    # mount so the child's c_xref aligns with p_xref at angle 0.
    joint_obj = parent.joints[f"{name}_axis"]
    a_eff_world = parent.location * joint_obj.relative_axis.location
    delta = j_p_world.inverse() * a_eff_world  # pure Rz about the joint axis
    j_c = joint_plane(c_origin, c_axis, c_xref)
    l_c_world = child.location * (j_c * delta)
    f_child = asm.rigid_frame(child, f"{name}_mount", l_c_world)
    asm.revolute(f_parent, f_child, angle=angle_deg, label=name)


def _axis_rot(axis_dir) -> Rot:
    """Rotation taking +Z to axis_dir (for placing cylinders along a joint axis)."""
    d = Vector(axis_dir).normalized()
    if abs(d.Z) > 0.999:
        return Rot(0, 0, 0) if d.Z > 0 else Rot(180, 0, 0)
    if abs(d.Y) > 0.999:
        return Rot(-90, 0, 0) if d.Y > 0 else Rot(90, 0, 0)
    if abs(d.X) > 0.999:
        return Rot(0, 90, 0) if d.X > 0 else Rot(0, -90, 0)
    raise ValueError("actuator axis must be a principal axis")


def actuator_solids(
    name: str,
    diameter: float,
    length: float,
    *,
    center=(0.0, 0.0, 0.0),
    axis=(0.0, 1.0, 0.0),
    bolts: bool = True,
) -> list:
    """Exposed cylindrical actuator module centered on a joint.

    Graphite can, recessed aluminum end caps, shallow rim grooves, and an
    optional bolt circle on the +axis cap for larger sizes. Returns a list of
    labeled, colored solids.
    """
    r = diameter / 2.0
    rot = _axis_rot(axis)
    at = Pos(*center) * rot
    solids = []

    can_len = length * 0.78
    can = at * Cylinder(radius=r, height=can_len)
    can = fillet(can.edges(), min(2.2, r * 0.08))
    solids.append(styled(can, f"{name}_can", STRUCT_COLOR))

    cap_len = (length - can_len) / 2.0
    rim_r = r * 0.92
    for sign, tag in ((1.0, "out"), (-1.0, "in")):
        cap = at * Pos(0, 0, sign * (can_len / 2.0 + cap_len / 2.0)) * Cylinder(
            radius=rim_r, height=cap_len
        )
        cap = chamfer(cap.edges(), min(1.2, cap_len * 0.3))
        solids.append(styled(cap, f"{name}_cap_{tag}", ALU_COLOR))

    hub = at * Pos(0, 0, length / 2.0 + 1.0) * Cylinder(radius=r * 0.45, height=2.0)
    solids.append(styled(hub, f"{name}_hub", ACCENT_COLOR))

    if bolts and diameter >= 56.0:
        n = 8 if diameter >= 80 else 6
        bc_r = rim_r * 0.74
        for i in range(n):
            a = 2.0 * math.pi * i / n
            bolt = at * Pos(
                bc_r * math.cos(a), bc_r * math.sin(a), length / 2.0 + 0.6
            ) * Cylinder(radius=1.6, height=1.2)
            solids.append(styled(bolt, f"{name}_bolt_{i}", STRUCT_COLOR))
    return solids


def rounded_box(
    label: str,
    color: Color,
    size,
    *,
    center=(0.0, 0.0, 0.0),
    radius: float = 3.0,
    axes: str = "z",
):
    """Box with filleted edges along the given axes ("z", "xz", "xyz"...)."""
    sx, sy, sz = size
    box = Pos(*center) * Box(sx, sy, sz)
    edges = []
    for ax_name, ax in (("x", Axis.X), ("y", Axis.Y), ("z", Axis.Z)):
        if ax_name in axes:
            edges.extend(box.edges().filter_by(ax))
    if edges:
        box = fillet(edges, min(radius, min(sx, sy, sz) / 2.0 - 0.4))
    return styled(box, label, color)
