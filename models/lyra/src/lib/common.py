"""Shared helpers for the lyra dexterous-hand part modules.

Conventions (all part modules must follow):
- Units mm. RIGHT hand: origin at the wrist-flange mount face center,
  +Z distal (fingers up), +Y palmar (palm faces +Y), +X radial (thumb side).
- Every part builder returns an identity-location build123d Compound whose
  children are closed, labeled, colored solids, modeled in the part's local
  frame (origin at the part's proximal joint center).
- Finger phalanges: segment extends +Z local, flexion axis -X local.
- Thumb segments: segment extends +X local, palmar pad faces +Z local,
  flexion axis -Y local.
- Joint hardware: the PARENT link owns the clevis cheeks and the aluminum
  pivot pin; the child owns the tang barrel. Everything touching a joint
  axis is a surface of revolution about that axis, so articulation never
  opens a visual gap.
"""

from __future__ import annotations

import build123d as bd

# Palette: warm pearl composite shells over a graphite structural core,
# machined-aluminum joint hardware, near-black soft-touch tactile pads, and
# a restrained amber accent on small functional details. No logos.
PEARL = "#f5f4f2"     # warm-white composite shells
GRAPHITE = "#6c6f76"   # structural cores / phalanx links
ALU = "#f0f2f7"        # machined-aluminum rims, pins, flange
PAD = "#59595d"        # soft-touch tactile pad rubber
AMBER = "#ebbc6f"      # amber accent (sensor ring, tensioners)
SENSOR = "#304561"     # gloss midnight sensor glass
# Plain RGB tuples: build123d's ``Shape.color`` setter builds the Color on
# assignment.


def styled(solid, label: str, color):
    solid.label = label
    solid.color = color
    return solid


def part_compound(label: str, children) -> bd.Compound:
    comp = bd.Compound(children=list(children))
    comp.label = label
    return comp


def safe_chamfer(part, edges, length, length2=None):
    try:
        edges = list(edges)
        if not edges:
            return part
        if length2 is not None:
            return bd.chamfer(edges, length, length2)
        return bd.chamfer(edges, length)
    except Exception:
        return part


def safe_fillet(part, edges, radius):
    try:
        edges = list(edges)
        if not edges:
            return part
        return bd.fillet(edges, radius)
    except Exception:
        return part


def xcyl(r, h):
    """Cylinder along +X centered at the origin."""
    return bd.Rot(0, 90, 0) * bd.Cylinder(radius=r, height=h)


def ycyl(r, h):
    """Cylinder along +Y centered at the origin."""
    return bd.Rot(-90, 0, 0) * bd.Cylinder(radius=r, height=h)


def zcyl(r, h):
    """Cylinder along +Z centered at the origin."""
    return bd.Cylinder(radius=r, height=h)


AXIS_CYL = {"x": xcyl, "y": ycyl, "z": zcyl}


def pin(axis: str, r: float, h: float):
    """Chamfered aluminum pivot pin along a principal axis."""
    p = AXIS_CYL[axis](r, h)
    return safe_chamfer(p, p.edges(), 0.6)


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
    helper transforms them by each part's current location, so parts that
    were already repositioned by upstream connects keep correct joints
    (connect in root-to-leaf order). At angle 0 the child's c_xref direction
    aligns with the parent's p_xref direction about the shared axis.
    ``angular_range`` is the joint's travel in degrees (absolute, as the URDF
    has it).

    (The same joint-attach math as the juno humanoid's.)
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
