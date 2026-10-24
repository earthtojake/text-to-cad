"""Shared base/gripper frame with reversible end-for-end servo mounting.

Rev3 datums and helpers the rev4 stages still read; the standalone part model is in git history.

The original fitted bracket supplies the upper cheek profiles and horn arms.
Each case cheek mirrors its upper flange and horn relief to the lower end,
about the long-pitch mounting pair. The short-pitch cheek has both hole pairs.
The base and gripper call this same model and retain their mounting datums.
"""

from __future__ import annotations



from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
# 2mm tree: SRC_DIR is this folder, so its parent is STEP -- the 1.6002 mm ORIGINALS. Putting
# that on sys.path ahead of this folder silently rebuilds the thin part (it did: the frame came
# out 1.6002 and byte-identical). The repo root is one further up.
REPO_ROOT = SRC_DIR.parents[1]
VENDOR_DIR = REPO_ROOT / "STEP" / "imported"

import build123d

from lib import shoulder_yaw_bracket_common as sb  # noqa: E402
from lib import fastener_clearance as fc
from lib import servo_fit as fit
from lib.shoulder_packaging import PITCH_MOUNT_RISE_MM

PART_NAME = "gripper_frame.step"  # pinned: the label these parts shipped with, when the source was gripper_frame.step.py


# HOW FAR THE CHEEKS SLIDE ALONG THE WALL, in +y. The family derives the cheek band straight from the
# servo's own case holes (sb.cheek_y_band of sb.top_bracket_holes), so the band lands wherever those
# holes are -- centred on y 27.2750, which is 1.7500 short of the wall's own middle.
#
# The wall's full-width face (gripper#o1.1.f3) runs y 11.6892..46.3608, and its centre 29.0250 is the
# ARM MIRROR PLANE: the two arms are mirrored about it, so it is the frame's own centreline, not an
# incidental number. Sliding the cheeks 1.7500 puts them, and everything they carry, on it.
#
# EVERYTHING THEY CARRY MOVES TOO, and that is not local to this file: the cheeks' case bolts go into
# the claw servo, so the servo, the yoke on its horns and the fixed jaw all shift the same 1.7500 in
# gripper.step.py, which reads this constant rather than restating it.
# 1.7500 (the arm-mirror centring) through 2026-08-25, then slid the other way ON INSTRUCTION to
# centre the claw-gap midline on the elbow-roll horn axis (tom#o1.19, world y 1.0750). The
# envelope moves as ONE SHAPE -- a first pass slid further (-0.5508) and cut the fold's low end
# back as bend relief, which the owner rejected ("SHIFT the entire envelope") -- so the limit is
# where the +z cheek fold's low end (family base 12.24 + shift) lands on the arm bend's INNER
# tangent at y 12.1972, the last line where the wall is flat through its full thickness. That buys
# 1.7928 of the 3.1121 the centring asks for; the midline lands at world y 2.3943, a recorded
# 1.3193 residual the envelopes alone cannot close. Closing the rest means the moving jaw's web
# or a longer wall.
# 2026-09-09: stop both shared case flanges at the far horn-arm bend's
# wall tangent. The previous 6.2960982 mm lift ran 1.3444982 mm into that
# bend. The shoulder yoke now supplies the remaining rest-seat reach.
CASE_FLANGE_TOP_Y_MM = (
    sb.TOP_ARM_OUTER_Y_MM + fit.SERVO.horn_span_mm
    + 2 * fit.HORN_MOUNT_GAP_MM - sb.BEND_INNER_RADIUS_MM
)
CHEEK_BAND_SHIFT_Y_MM = (
    CASE_FLANGE_TOP_Y_MM - sb.cheek_y_band(sb.top_bracket_holes())[1]
    + PITCH_MOUNT_RISE_MM
)


# THE CASE-BOLT HOLES SIT ON THE VENDOR SERVO'S BORES as of 2026-08-25, on instruction ("adjust
# position of holes, leave brackets as they are"): the family grid and the vendor model disagree
# by a uniform (0.5080, 0.1762) in this frame -- measured on all four holes, offset 0.5377 each --
# and the bore you can see wins. Moved by plug-and-recut AFTER the build, because the family
# derives the whole cheek band from its hole grid: correcting the grid at the source would slide
# the band and change the bracket's shape, which stays frozen. Horn-side holes are untouched.
_S = CHEEK_BAND_SHIFT_Y_MM             # both grids ride the band slide
CASE_HOLE_MOVES = (
    # (old family-grid centre, vendor bore centre, z side) -- y bases are shift-0 values
    ((-53.3206, 14.8740 + _S), (-52.8126, 15.0502 + _S), +1),
    ((-53.3206, 39.3240 + _S), (-52.8126, 39.5002 + _S), +1),
    ((-53.3206, 18.6240 + _S), (-52.8126, 18.8002 + _S), -1),
    ((-53.3206, 39.3240 + _S), (-52.8126, 39.5002 + _S), -1),
)
CASE_HOLE_R_MM = fc.M2_CLEARANCE_RADIUS_MM

CASE_MOUNT_MIRROR_Y_MM = (CASE_HOLE_MOVES[0][1][1] + CASE_HOLE_MOVES[1][1][1]) / 2


def reversible_case_hole_centers():
    """Both mounting orientations, as (x, y, cheek sign) in the frame."""
    centers = []
    for _old, (x, y), side in CASE_HOLE_MOVES:
        for yy in (y, 2*CASE_MOUNT_MIRROR_Y_MM-y):
            point = (x, yy, side)
            if not any(abs(x-a) < 1e-8 and abs(yy-b) < 1e-8 and side == c
                       for a, b, c in centers):
                centers.append(point)
    return tuple(sorted(centers))


def _make_end_for_end_case_mount(body, *, mirror_y_mm=CASE_MOUNT_MIRROR_Y_MM,
                                hole_centers=None):
    """Mirror upper cheek flanges, bends and wall lobes about the bolt datum.

    The horn arms occupy |z| <= ARM_HALF_Z_MM and stay as authored. The
    adjoining cheek regions are rebuilt from their own upper halves, so
    their tab and clearance profiles match exactly at both ends.
    """
    bounds = body.bounding_box()
    margin = 1.0
    mirror = build123d.Plane(origin=(0, mirror_y_mm, 0),
                            x_dir=(1, 0, 0), z_dir=(0, 1, 0))
    tools, additions = [], []
    for side in (-1, 1):
        zlo, zhi = ((bounds.min.Z-margin, -ARM_HALF_Z_MM) if side < 0
                    else (ARM_HALF_Z_MM, bounds.max.Z+margin))
        upper_region = sb.box(bounds.min.X-margin, bounds.max.X+margin,
                              mirror_y_mm, bounds.max.Y+margin,
                              zlo, zhi)
        upper = sb.as_single_shape(body.intersect(upper_region))
        additions.append(upper.mirror(mirror))
        tools.append(sb.box(bounds.min.X-margin, bounds.max.X+margin,
                            bounds.min.Y-margin, mirror_y_mm,
                            zlo, zhi))
    body = sb.as_single_shape(body.cut(*tools).fuse(*additions))
    # Recut the union of both orientations, including the second pair on
    # the short-pitch cheek. The reflected long-pitch pair already agrees.
    for x, y, side in (reversible_case_hole_centers() if hole_centers is None else hole_centers):
        zlo, zhi = ((sb.CHEEK_INNER_Z_MM, sb.CHEEK_OUTER_Z_MM) if side > 0
                    else (-sb.CHEEK_OUTER_Z_MM, -sb.CHEEK_INNER_Z_MM))
        body = sb.as_single_shape(body.cut(sb.z_cylinder(
            x, y, CASE_HOLE_R_MM, zlo-margin, zhi+margin)))
    solids = body.solids()
    if len(solids) != 1 or not body.is_valid:
        raise RuntimeError(f'{PART_NAME}: reversible cheeks must leave one valid solid')
    return solids[0]


def _load_bracket():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gripper_frame_src", SRC_DIR.parent / "shoulder_yaw_top_bracket.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The cheek-tip fillet is aimed by hardcoded corner coordinates, and it refuses to fillet
    # "whatever happens to be nearby" -- so sliding the band has to move its aim by the same amount.
    # Safe to set here: importlib gives this fork its own module object.
    if CHEEK_BAND_SHIFT_Y_MM:
        module.CHEEK_TIP_FILLET_XYZ_MM = tuple(
            (x, y + CHEEK_BAND_SHIFT_Y_MM, z) for x, y, z in module.CHEEK_TIP_FILLET_XYZ_MM
        )
    return module


bracket = _load_bracket()


# THE HORN ARMS RUN STRAIGHT, not on the family's V. The family tapers each arm from the wall's fold
# half-width (15.111) down to a line tangent to the r10.000 cap; these run parallel-sided at the cap's
# own radius the whole way, which is the shape every other yoke on this arm carries
# (tom_v2#o1.14, #o1.18).
#
# THE COST, accepted: the arm arrives at the fold 10.000 half-wide against the wall's 15.111, so it no
# longer meets the fold across its full width. The bend fillet has less parallel-sided web to die into
# than the family assumes.
OVERSIZE_MM = 300.0
ARM_HALF_Z_MM = 10.0                      # = sb.ARM_CAP_RADIUS_MM, so the web runs flush into the cap


