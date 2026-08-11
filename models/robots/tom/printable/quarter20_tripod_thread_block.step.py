#!/usr/bin/env python3
"""
1/4"-20 UNC female-thread test block.

A small rectangular coupon with a single through-hole carrying a modeled
helical 1/4"-20 UNC internal (female) thread. It is meant as a quick fit test
for a standard camera/tripod 1/4-20 screw -- e.g. the tripod at
amazon.com/dp/B0BV2SBWVD, which uses the standard 1/4-20 UNC stud.

Design intent / print optimization:
- Through-threaded hole so the part prints hole-axis vertical (+Z): the thread
  turns become flat layer features (good thread quality) with a flat bottom and
  NO support material.
- Compact 40 x 40 x 15 mm block -> small volume, fast print.
- Real 60 deg V thread form at 1.27 mm pitch (20 TPI), 6.35 mm major diameter.
- A uniform radial clearance is baked into the thread so an FDM/SLA print
  accepts a real metal 1/4-20 screw without re-tapping.
- Chamfered lead-in cones at both hole mouths so the screw starts squarely and
  to relieve first-layer elephant-foot.
"""

from __future__ import annotations

import math
from pathlib import Path

import build123d as bd
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.TopTools import TopTools_ListOfShape

PART_NAME = Path(__file__).stem

# --- Block ---------------------------------------------------------------
BLOCK_X_MM = 40.0
BLOCK_Y_MM = 40.0
BLOCK_Z_MM = 15.0

# --- 1/4"-20 UNC thread ---------------------------------------------------
INCH = 25.4
TPI = 20.0
PITCH_MM = INCH / TPI            # 1.270 mm
MAJOR_DIAMETER_MM = 0.25 * INCH  # 6.350 mm

# Radial print clearance applied to the whole thread form so the printed female
# thread is slightly oversized relative to the nominal mating screw.
RADIAL_CLEARANCE_MM = 0.15

# Lead-in chamfer at each hole mouth.
CHAMFER_DEPTH_MM = 0.8
CHAMFER_EXTRA_RADIUS_MM = 0.8

PLASTIC_COLOR = bd.Color(0.20, 0.45, 0.80, 1.0)

# Sharp-V geometry (UN form, 60 deg included flank angle).
_H = (math.sqrt(3.0) / 2.0) * PITCH_MM          # full sharp-V height
_R_MAJOR = MAJOR_DIAMETER_MM / 2.0              # 3.175 mm (internal thread root / valley)
_R_MINOR = _R_MAJOR - (5.0 / 8.0) * _H          # internal thread crest (inner)

# Female thread, offset outward by the print clearance so it is slightly loose.
_R_CREST = _R_MINOR + RADIAL_CLEARANCE_MM       # tooth crest (smallest passage, inner)
_R_VALLEY = _R_MAJOR + RADIAL_CLEARANCE_MM       # tooth valley (deepest, = bore wall)
_THREAD_RADIAL_DEPTH = _R_VALLEY - _R_CREST

# Construction radii. The bore is opened to the valley diameter, then the thread
# teeth are ADDED pointing inward. The tooth base is buried slightly past the
# bore wall (overlap) so the fuse to the wall is solid, not merely tangent.
_BASE_OVERLAP_MM = 0.4
_R_BASE = _R_VALLEY + _BASE_OVERLAP_MM          # outer (buried) edge of the tooth
_R_PITCH = 0.5 * (_R_CREST + _R_VALLEY)         # helix is driven on the pitch line

_TAN30 = math.tan(math.radians(30.0))
# A small flat at the crest (truncated UN form) avoids a fragile knife edge and
# the sliver faces a sharp apex produces.
_CREST_HALF_AXIAL = (PITCH_MM / 8.0) / 2.0
# 60 deg flanks run crest -> valley; beyond the valley the tooth continues as a
# constant-width tab buried in the wall (so its full width stays under the pitch
# and adjacent turns never self-intersect).
_VALLEY_HALF_AXIAL = _CREST_HALF_AXIAL + _THREAD_RADIAL_DEPTH * _TAN30


def _fuzzy_fuse(base: bd.Shape, tool: bd.Shape, fuzz: float = 1.0e-4) -> bd.Solid:
    """Boolean union with a small fuzzy tolerance.

    The thread teeth meet the bore wall along tangent helical faces, which makes
    the exact (zero-tolerance) OCCT fuse fail with a null result. A tiny fuzzy
    value makes the union robust and yields one connected solid.
    """
    args = TopTools_ListOfShape()
    args.Append(base.wrapped)
    tools = TopTools_ListOfShape()
    tools.Append(tool.wrapped)
    op = BRepAlgoAPI_Fuse()
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetFuzzyValue(fuzz)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise RuntimeError("thread fuse failed")
    return bd.Solid(op.Shape())


def _z_cylinder(radius: float, z_min: float, z_max: float) -> bd.Solid:
    return bd.Solid.make_cylinder(
        radius,
        z_max - z_min,
        plane=bd.Plane(origin=bd.Vector(0.0, 0.0, z_min)),
    )


def _thread_ridge() -> bd.Shape:
    """Helical female thread teeth, pointing inward, to fuse onto the bore wall.

    The teeth crest at _R_CREST (inner) and their base is buried past the bore
    wall at _R_BASE so the union with the block is solid.
    """
    overshoot = PITCH_MM  # run the helix past both faces for clean entry/exit
    z0 = -overshoot
    height = BLOCK_Z_MM + 2.0 * overshoot

    helix = bd.Helix(pitch=PITCH_MM, height=height, radius=_R_PITCH,
                     center=(0.0, 0.0, z0))
    start = helix @ 0          # point on the pitch helix at theta = 0
    tangent = helix % 0        # helix tangent (sweep normal)
    radial = bd.Vector(start.X, start.Y, 0.0).normalized()  # outward radial (+X)

    # Define the tooth section on a plane whose normal is the helix tangent and
    # whose local X is the outward radial, so the swept profile stays radial all
    # the way around (no Frenet twist drifting the teeth off-axis).
    plane = bd.Plane(origin=start, x_dir=radial, z_dir=tangent)
    rc = _R_CREST - _R_PITCH     # crest (inner, < 0)
    rv = _R_VALLEY - _R_PITCH     # valley = end of the 60 deg flanks
    rb = _R_BASE - _R_PITCH       # buried base of the constant-width tab (> 0)
    profile = bd.make_face(
        bd.Polyline(
            plane.from_local_coords((rc, +_CREST_HALF_AXIAL)),
            plane.from_local_coords((rc, -_CREST_HALF_AXIAL)),
            plane.from_local_coords((rv, -_VALLEY_HALF_AXIAL)),
            plane.from_local_coords((rb, -_VALLEY_HALF_AXIAL)),
            plane.from_local_coords((rb, +_VALLEY_HALF_AXIAL)),
            plane.from_local_coords((rv, +_VALLEY_HALF_AXIAL)),
            close=True,
        )
    )
    return bd.sweep(profile, path=helix, is_frenet=True)


def _chamfer_cone(z_face: float, sign: float) -> bd.Solid:
    """Truncated cone removing a lead-in chamfer at a hole mouth.

    sign = +1 for the top face (cone opens upward), -1 for the bottom.
    """
    r_face = _R_VALLEY + CHAMFER_EXTRA_RADIUS_MM
    r_inner = _R_VALLEY
    if sign > 0:
        bottom_r, top_r = r_inner, r_face
        z_base = z_face - CHAMFER_DEPTH_MM
    else:
        bottom_r, top_r = r_face, r_inner
        z_base = z_face
    return bd.Solid.make_cone(
        bottom_r, top_r, CHAMFER_DEPTH_MM,
        plane=bd.Plane(origin=bd.Vector(0.0, 0.0, z_base)),
    )


def build_step() -> bd.Shape:
    block = bd.Solid.make_box(
        BLOCK_X_MM, BLOCK_Y_MM, BLOCK_Z_MM,
        plane=bd.Plane(origin=bd.Vector(-BLOCK_X_MM / 2.0, -BLOCK_Y_MM / 2.0, 0.0)),
    )

    # Open the bore to the valley (major) diameter, then add the thread teeth.
    block = block.cut(_z_cylinder(_R_VALLEY, -1.0, BLOCK_Z_MM + 1.0))
    block = _fuzzy_fuse(block, _thread_ridge())

    # Trim thread teeth that overshoot the block faces back to the envelope.
    slab = 2.0 * PITCH_MM
    block = block.cut(_z_cylinder(_R_BASE + 1.0, BLOCK_Z_MM, BLOCK_Z_MM + slab))
    block = block.cut(_z_cylinder(_R_BASE + 1.0, -slab, 0.0))

    block = block.cut(_chamfer_cone(BLOCK_Z_MM, +1.0))
    block = block.cut(_chamfer_cone(0.0, -1.0))

    solids = list(block.solids())
    if len(solids) != 1:
        raise RuntimeError(f"Expected one solid, found {len(solids)}")

    part = solids[0]
    part.label = PART_NAME
    part.color = PLASTIC_COLOR
    print(
        "1/4-20 UNC female-thread test block "
        f"block={BLOCK_X_MM:.1f}x{BLOCK_Y_MM:.1f}x{BLOCK_Z_MM:.1f} mm, "
        f"pitch={PITCH_MM:.3f} mm ({TPI:.0f} TPI), "
        f"major_dia={MAJOR_DIAMETER_MM:.3f} mm, "
        f"minor_dia~{2.0 * _R_MINOR:.3f} mm, "
        f"radial_clearance={RADIAL_CLEARANCE_MM:.2f} mm"
    )
    return part


def gen_step() -> dict[str, object]:
    return {"shape": build_step()}


if __name__ == "__main__":
    gen_step()
