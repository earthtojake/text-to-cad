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

# Palette: warm pearl composite shells over a graphite structural core,
# machined-aluminum joint hardware, near-black soft-touch tactile pads, and
# a restrained amber accent on small functional details. No logos.
PEARL = (0.91, 0.905, 0.89)     # warm-white composite shells
GRAPHITE = (0.15, 0.16, 0.18)   # structural cores / phalanx links
ALU = (0.87, 0.89, 0.93)        # machined-aluminum rims, pins, flange
PAD = (0.10, 0.10, 0.11)        # soft-touch tactile pad rubber
AMBER = (0.83, 0.50, 0.16)      # amber accent (sensor ring, tensioners)
SENSOR = (0.03, 0.06, 0.12)     # gloss midnight sensor glass

PEARL_COLOR = Color(*PEARL)
GRAPHITE_COLOR = Color(*GRAPHITE)
ALU_COLOR = Color(*ALU)
PAD_COLOR = Color(*PAD)
AMBER_COLOR = Color(*AMBER)
SENSOR_COLOR = Color(*SENSOR)


def styled(solid, label: str, color: Color):
    solid.label = label
    solid.color = color
    return solid


def part_compound(label: str, children) -> Compound:
    comp = Compound(children=list(children))
    comp.label = label
    return comp


def safe_chamfer(part, edges, length, length2=None):
    try:
        edges = list(edges)
        if not edges:
            return part
        if length2 is not None:
            return chamfer(edges, length, length2)
        return chamfer(edges, length)
    except Exception:
        return part


def safe_fillet(part, edges, radius):
    try:
        edges = list(edges)
        if not edges:
            return part
        return fillet(edges, radius)
    except Exception:
        return part


def xcyl(r, h):
    """Cylinder along +X centered at the origin."""
    return Rot(0, 90, 0) * Cylinder(radius=r, height=h)


def ycyl(r, h):
    """Cylinder along +Y centered at the origin."""
    return Rot(-90, 0, 0) * Cylinder(radius=r, height=h)


def zcyl(r, h):
    """Cylinder along +Z centered at the origin."""
    return Cylinder(radius=r, height=h)


AXIS_CYL = {"x": xcyl, "y": ycyl, "z": zcyl}


def pin(axis: str, r: float, h: float):
    """Chamfered aluminum pivot pin along a principal axis."""
    p = AXIS_CYL[axis](r, h)
    return safe_chamfer(p, p.edges(), 0.6)


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
    helper transforms them by each part's current location, so parts that
    were already repositioned by upstream connects keep correct joints
    (connect in root-to-leaf order). At angle 0 the child's c_xref direction
    aligns with the parent's p_xref direction about the shared axis.

    (Same verified build123d-0.10 joint-attach math as the juno humanoid.)
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
