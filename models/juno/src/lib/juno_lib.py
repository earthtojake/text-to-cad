"""Shared helpers for the juno humanoid part modules.

Conventions (all part modules must follow):
- Units mm. Robot faces +X, +Y is robot-left, +Z is up.
- Every part builder returns an identity-location build123d Compound whose
  children are closed, labeled, colored solids. Model geometry directly in the
  part's local frame (joint/mate origins as documented per part).
- Limb segments: origin at the proximal joint center, segment extends -Z.
- Exposed actuator cans: cylinder axis along the joint axis, centered at the
  joint center, built with `actuator_solids()`.

`revolute_attach()` places the child so its joint plane coincides with the
parent joint plane rotated `angle_deg` about the shared axis, and leaves the
two build123d joints that do it on the parts: the robot's mechanism.
"""

from __future__ import annotations

import math

import build123d as bd

# Palette: warm porcelain + graphite + aluminum, with a coral accent on
# small repeated functional details (hub caps, bumpers, vents). No logos.
# Plain RGB(A) tuples: build123d's Shape.color setter builds the Color on
# assignment.
SHELL = "#eae9e6"     # warm porcelain composite shells
STRUCT = "#6f7379"     # graphite structural cores
ALU = "#f1f3f8"        # bright machined-aluminum joint rims
VISOR = "#273f5d"      # gloss midnight-blue sensor glass
RUBBER = "#505055"     # sole / grip rubber
ACCENT = "#f7a66f"     # coral-orange accent details
EYE = "#99f3fd"        # bright cyan display "pixels" (Anki-style)


def styled(solid, label: str, color):
    solid.label = label
    solid.color = color
    return solid


def part_compound(label: str, children) -> bd.Compound:
    comp = bd.Compound(children=list(children))
    comp.label = label
    return comp


def joint_plane(origin, axis_dir, x_ref) -> bd.Location:
    return bd.Plane(
        origin=bd.Vector(origin), x_dir=bd.Vector(x_ref), z_dir=bd.Vector(axis_dir)
    ).location


def revolute_attach(
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
    angular_range,
):
    """Author the revolute joint ``name`` on the parent, its rigid mount on the
    child, and connect them at ``angle_deg`` (the as-built value).

    Joint origins/axes are given in each part's LOCAL modeling frame; the
    helper transforms them by each part's current location, so parts that were
    already repositioned by upstream connects keep correct joints (connect in
    root-to-leaf order). At angle 0 the child's c_xref direction aligns with
    the parent's p_xref direction about the shared axis. ``angular_range`` is
    the joint's travel in degrees (absolute, as the URDF has it).
    """
    j_p_world = parent.location * joint_plane(p_origin, p_axis, p_xref)
    z_tip = (j_p_world * bd.Pos(0, 0, 1)).position
    axis_world = bd.Axis(j_p_world.position, z_tip - j_p_world.position)
    bd.RevoluteJoint(name, parent, axis=axis_world, angular_range=tuple(angular_range))
    # The joint's stored frame may use any x-reference convention; read the
    # actual frame back and fold the constant Rz difference into the child
    # mount so the child's c_xref aligns with p_xref at angle 0.
    a_eff_world = parent.location * parent.joints[name].relative_axis.location
    delta = j_p_world.inverse() * a_eff_world  # pure Rz about the joint axis
    j_c = joint_plane(c_origin, c_axis, c_xref)
    bd.RigidJoint(name, child, child.location * (j_c * delta))
    parent.joints[name].connect_to(child.joints[name], angle=angle_deg)


def _axis_rot(axis_dir) -> bd.Rot:
    """Rotation taking +Z to axis_dir (for placing cylinders along a joint axis)."""
    d = bd.Vector(axis_dir).normalized()
    if abs(d.Z) > 0.999:
        return bd.Rot(0, 0, 0) if d.Z > 0 else bd.Rot(180, 0, 0)
    if abs(d.Y) > 0.999:
        return bd.Rot(-90, 0, 0) if d.Y > 0 else bd.Rot(90, 0, 0)
    if abs(d.X) > 0.999:
        return bd.Rot(0, 90, 0) if d.X > 0 else bd.Rot(0, -90, 0)
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
    at = bd.Pos(*center) * rot
    solids = []

    can_len = length * 0.78
    can = at * bd.Cylinder(radius=r, height=can_len)
    can = bd.fillet(can.edges(), min(2.2, r * 0.08))
    solids.append(styled(can, f"{name}_can", STRUCT))

    cap_len = (length - can_len) / 2.0
    rim_r = r * 0.92
    for sign, tag in ((1.0, "out"), (-1.0, "in")):
        cap = at * bd.Pos(0, 0, sign * (can_len / 2.0 + cap_len / 2.0)) * bd.Cylinder(
            radius=rim_r, height=cap_len
        )
        cap = bd.chamfer(cap.edges(), min(1.2, cap_len * 0.3))
        solids.append(styled(cap, f"{name}_cap_{tag}", ALU))

    hub = at * bd.Pos(0, 0, length / 2.0 + 1.0) * bd.Cylinder(radius=r * 0.45, height=2.0)
    solids.append(styled(hub, f"{name}_hub", ACCENT))

    if bolts and diameter >= 56.0:
        n = 8 if diameter >= 80 else 6
        bc_r = rim_r * 0.74
        for i in range(n):
            a = 2.0 * math.pi * i / n
            bolt = at * bd.Pos(
                bc_r * math.cos(a), bc_r * math.sin(a), length / 2.0 + 0.6
            ) * bd.Cylinder(radius=1.6, height=1.2)
            solids.append(styled(bolt, f"{name}_bolt_{i}", STRUCT))
    return solids


def rounded_box(
    label: str,
    color: bd.Color,
    size,
    *,
    center=(0.0, 0.0, 0.0),
    radius: float = 3.0,
    axes: str = "z",
):
    """Box with filleted edges along the given axes ("z", "xz", "xyz"...)."""
    sx, sy, sz = size
    box = bd.Pos(*center) * bd.Box(sx, sy, sz)
    edges = []
    for ax_name, ax in (("x", bd.Axis.X), ("y", bd.Axis.Y), ("z", bd.Axis.Z)):
        if ax_name in axes:
            edges.extend(box.edges().filter_by(ax))
    if edges:
        box = bd.fillet(edges, min(radius, min(sx, sy, sz) / 2.0 - 0.4))
    return styled(box, label, color)
