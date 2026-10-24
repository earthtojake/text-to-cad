#!/usr/bin/env python3
"""Shoulder-yaw yoke: a bent-sheet U-bracket that captures the base sts3250 on both horn axes.

Rev3 datums and helpers the rev4 stages still read; the standalone part model is in git history.

The existing shoulder-yaw link cantilevers off a single horn via servo_end_mount. This yoke takes
both coaxial horns instead, so the joint is supported at two bearings:

  @cad[STEP/tests/base_clamp_assembly/base_clamp_assembly#o1.1.4]  top driven horn
  @cad[STEP/tests/base_clamp_assembly/base_clamp_assembly#o1.1.5]  bottom idler horn

Both are centred on x=-25.5, z=0, lying 32.8 mm apart in y. The yoke rotates with them; the case
does not. Four things drive the shape:

1. The spine is the only part crossing the case's y band, so its radius sets the travel. Hugging the
   case's near corner (15.968 mm) gives a compact yoke good for +/-110 deg, measured. Clearing the
   full sweep circle (37.222 mm) would allow the 360 deg that the URDF's continuous base_yaw implies,
   at roughly twice the size -- ALLOW_CONTINUOUS_ROTATION switches between the two.
2. The top horn protrudes 1.7 mm above the case, so the top arm seats flat on it.
3. The bottom flange seats straight onto the recessed idler horn. The servo's underside is a
   recess, not a flat plane -- over y -28.15..-27.45 the case holds only 22.684 mm^3 out to r=40,
   all of it inside r=5.0 plus thin slivers past r=16 -- so the flange only needs a bore over that
   central feature. No shim or spacer stack.
4. Fabrication is SendCutSend 5052-H32 at 0.063" (1.6002 mm), the same gauge and tooling the v2 link
   brackets use and the only one with rule values verified in this repo. The two 90 deg bends are
   therefore modelled at the published effective radius (0.035") rather than sharp, and flange
   length, hole-to-bend and hole-to-edge are checked against ALU-063's own values. Arm ends are
   capped with a circle on the horn axis.
5. The cheeks seat on servo 2's real mounting faces, which are its HOLE planes at +/-16.000, not its
   overall bbox: the case carries protrusions past those planes on both sides, and the cheeks clear
   them by two different means because the case is not symmetric. The +z side's bosses fall between
   the bolt ears, so the notch clears them; the -z side has a lengthwise rib running past both ears,
   so that cheek's tip is pulled back instead. Both are derived from measured values, and the tip
   relief is what makes the -z flange the shorter of the two (12.126 mm against the 12.090 floor).

Usage:
  python src/shoulder_yaw_yoke.py
"""

from __future__ import annotations

from lib import servo_fit as fit



import math
from pathlib import Path

# Every model and shared module lives under src/, which Python puts on sys.path for us.
SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parent

import build123d

from lib.booleans import as_single_shape

PART_NAME = "shoulder_yaw_yoke_twin_bolt.step"  # pinned: the label these parts shipped with, when the source was shoulder_yaw_yoke_twin_bolt.step.py
DISPLAY_NAME = "Shoulder Yaw Yoke"

from lib import sheet_rule_scs as scs  # noqa: E402


# --- Sheet spec ---------------------------------------------------------------------------------
# SendCutSend 5052-H32. 0.063 in = 1.6002 mm is the gauge nearest the requested 1.6 mm, and it is
# also the only one this repo has VERIFIED rule values for (STEP/link_geometry.py, ALU-063) -- so the
# two 90 deg bends are modelled at the published effective radius instead of sharp, and every
# forming check uses this gauge's own numbers rather than a conservative substitute.
#
# That matters beyond thickness. On the previous 0.080 setting no rules existed here, so the checks
# fell back to 0.125's values and the cheek flange had to reach 12.090 mm, which fought the servo's
# mounting recess for no real reason. At 0.063 the true minimum is 7.696 mm and the conflict is gone.
# Which gauge this family is folded from: the sheet rule's, and only that. (An environment override
# used to let one part be ordered thicker; a thicker part is a factory argument now, not an env var.)
SHEET_GAUGE_IN = scs.THICKNESS_IN
# The 0.080 row was a placeholder (all None, so the code fell back to the 0.125 rules and printed a
# "confirm with SendCutSend" warning). Filled 2026-08-21 from sendcutsend-specs.json,
# materials[sku=ALU-080].bending_specs -- the same source the 0.063 row uses. Note the bend radius is
# LARGER than 0.063's (0.038 against 0.035) and the k-factor jumps to 0.48, so a part re-gauged to
# 0.080 does not merely get thicker: its folds move too.


SENDCUTSEND_RULES_BY_GAUGE_IN: dict[float, dict[str, float | None]] = {
    0.063: {"bend_radius_in": 0.035, "k_factor": 0.42, "die_width_in": 0.472, "min_flange_in": 0.303},
    0.080: {"bend_radius_in": scs.EFFECTIVE_BEND_RADIUS_IN, "k_factor": scs.K_FACTOR,
            "die_width_in": scs.DIE_WIDTH_IN, "min_flange_in": scs.MIN_FLANGE_AFTER_BEND_IN},
    0.125: {"bend_radius_in": 0.125, "k_factor": 0.44, "die_width_in": 0.630, "min_flange_in": 0.476},
}
_RULES = SENDCUTSEND_RULES_BY_GAUGE_IN[SHEET_GAUGE_IN]
_CONSERVATIVE = SENDCUTSEND_RULES_BY_GAUGE_IN[0.125]
SHEET_THICKNESS_MM = 25.4 * SHEET_GAUGE_IN
BEND_RULES_VERIFIED = _RULES["bend_radius_in"] is not None
SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM = (
    25.4 * _RULES["bend_radius_in"] if BEND_RULES_VERIFIED else 0.0
)
SENDCUTSEND_K_FACTOR = _RULES["k_factor"] if BEND_RULES_VERIFIED else _CONSERVATIVE["k_factor"]
SENDCUTSEND_DIE_WIDTH_MM = 25.4 * (
    _RULES["die_width_in"] if _RULES["die_width_in"] is not None else _CONSERVATIVE["die_width_in"]
)
SENDCUTSEND_HALF_DIE_WIDTH_MM = 0.5 * SENDCUTSEND_DIE_WIDTH_MM
SENDCUTSEND_MIN_FLANGE_FORMED_MM = 25.4 * (
    _RULES["min_flange_in"] if _RULES["min_flange_in"] is not None
    else _CONSERVATIVE["min_flange_in"]
)
SENDCUTSEND_MOUNT_HOLE_TO_BEND_BUFFER_MM = 0.5
SENDCUTSEND_MIN_HOLE_TO_EDGE_MM = 0.97

# --- Servo interface, measured from the placed sts3250 in base_clamp_assembly -------------------
HORN_AXIS_X_MM = -25.5
HORN_AXIS_Z_MM = 0.0
TOP_HORN_FACE_Y_MM = 9.2
TOP_HORN_DIAMETER_MM = 20.0
BOTTOM_HORN_FACE_Y_MM = -27.4
SERVO_CASE_X_MIN_MM = -35.610023
SERVO_CASE_X_MAX_MM = 9.610026
SERVO_CASE_Z_MIN_MM = -12.360026
SERVO_CASE_Z_MAX_MM = 12.360024

# Horn bolt circle: 4x M3 at 90 deg, matching the base plate's lower-horn clearance pattern
# (-32.5, 0), (-25.5, -7), (-25.5, 7), (-18.5, 0) taken about the axis.
# Imported here rather than at the top of the file: this module bootstraps sys.path itself
# further up, and fastener_clearance lives in STEP/ alongside it.
from lib import fastener_clearance as fc  # noqa: E402
from lib import servo_horn_interface as shi  # noqa: E402
HORN_BOLT_CIRCLE_RADIUS_MM = shi.HORN_BOLT_CIRCLE_RADIUS_MM
HORN_BOLT_COUNT = shi.HORN_BOLT_COUNT
M3_CLEARANCE_RADIUS_MM = fc.M3_CLEARANCE_RADIUS_MM
# Servo-2 case holes measured Ø2.194 on the vendor STEP -> M2.
M2_CLEARANCE_RADIUS_MM = fc.M2_CLEARANCE_RADIUS_MM
# Both horn-face bores use the established pattern from
# @cad[STEP/servo_horn_yoke#o1.f8] -- a D6.496 bore -- so the two sides match.
HORN_CENTER_CLEARANCE_RADIUS_MM = shi.HORN_CENTER_CLEARANCE_RADIUS_MM

# --- Yoke parameters ---------------------------------------------------------------------------
# As wide as the servo horns. The SendCutSend floor is 2*(7.0+1.7+0.97) = 19.340 mm; the horn's
# 20.0 mm leaves 1.300 mm hole-to-edge against that 0.970 mm minimum.
YOKE_WIDTH_Z_MM = TOP_HORN_DIAMETER_MM
# Arm ends are capped with a circle centred on the horn axis, radius = half width, so the tip
# outline matches the horn footprint exactly.
ARM_CAP_RADIUS_MM = 0.5 * YOKE_WIDTH_Z_MM
# Derived in the Derived section below: this is now the SendCutSend floor, not a chosen value.
# The bottom flange seats straight onto the idler horn -- no shim. The servo's underside is
# recessed, not a flat plane: measured over y -28.15..-27.45 the case holds only 22.684 mm^3 out to
# r=40 (a filled annulus would be ~2487), all of it a central feature inside r=5.0 plus thin slivers
# past r=16. So the flange clears if it carries a bore over that central feature.
BOTTOM_FLANGE_TO_HORN_CLEARANCE_MM = 0.0

# --- Servo-2 interface: tabs wrapping past the spine onto the next sts3250 -----------------------
# From the resolved refs on the next servo (same sts3250 model):
#   f32  @cad[STEP/imports/sts3250#o1.3.f32]  +z side face,  normal (0,0,1)  -> into the wall
#   f22  @cad[STEP/imports/sts3250#o1.3.f22]  -x end face,   normal (-1,0,0) -> faces UP
#   4x M2, axes along the servo's local y, at local z=10.276 -> 2.084 mm past the wall plane
#
# Those two faces fix the orientation completely: local x -> yoke -y, local y -> yoke -z,
# local z -> yoke +x. The horn axis (local y) therefore lands along the yoke's z -- HORIZONTAL --
# so this is a pitch joint, and the hole axes are horizontal too. That is why the cheeks come off
# the wall's vertical side edges (o1.12.e2 / e18) rather than its top and bottom.
INCLUDE_SERVO2_TABS = True
SERVO2_MATING_FACE_LOCAL_Z_MM = 12.36
SERVO2_HOLE_LOCAL_Z_MM = 10.276
# (servo-local x, servo-local y) of the four holes; upper pair then lower pair.
SERVO2_HOLE_LOCAL_XY_MM: tuple[tuple[float, float], ...] = (
    (-17.2, 6.4), (3.5, 6.4), (-17.2, -25.6), (7.25, -25.6),
)
# The servo stands off the wall rather than seating flush on it. 1.5 mm matches link_plate, which
# both asserts LEG_FACE_CLEARANCE_MM >= 1.5 (link_plate.step.py) and documents a 1.5 mm flange
# standoff so the flange clears the case's proud centre ridge (1.1 mm) and horn boss (1.3 mm). The
# cheek bolts locate the servo; the wall is a backstop, not a press fit.
# The cheeks are formed flanges, so SendCutSend's bend rules apply to them as well as to the arms.
# Two of those rules are driven by how far the servo stands off the wall, because the bolt holes sit
# only SERVO2_HOLE_INSET_MM past the mating face:
#   hole-to-bend >= half die width + buffer   -> sets the minimum wall clearance
#   formed flange >= min flange length        -> sets the minimum cheek tip margin (below)
# Both were violated at the previous 1.5 mm clearance (3.584 vs 8.501, and 6.184 vs 12.090), so the
# clearance is now derived from the rule rather than chosen. SENDCUTSEND_BEND_SAFETY_MM is the margin
# kept over the published minimum.
SERVO2_HOLE_INSET_MM = SERVO2_MATING_FACE_LOCAL_Z_MM - SERVO2_HOLE_LOCAL_Z_MM
SENDCUTSEND_BEND_SAFETY_MM = 0.5
_MIN_HOLE_TO_BEND_MM = (
    SENDCUTSEND_HALF_DIE_WIDTH_MM + SENDCUTSEND_MOUNT_HOLE_TO_BEND_BUFFER_MM
)
# Measured rib on servo 2's -z case face; the -z cheek's tip is pulled back by this much. Declared
# here because TAB_EDGE_MARGIN_MM below has to cover it.
SERVO2_TIP_RIB_DEPTH_MM = 0.314
SERVO2_TIP_RIB_CLEARANCE_MM = 0.15
SERVO2_WALL_CLEARANCE_FLOOR_MM = 1.5
# The hole-to-bend datum is the bend TANGENT, not the spine's outer face. With sharp bends those
# coincided; with a real radius the tangent sits one inner-radius further out along the flange, so
# the clearance has to cover that too or the check passes against the wrong line.
_CHEEK_BEND_DATUM_OFFSET_MM = SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM
# Own safety term, separate from SENDCUTSEND_BEND_SAFETY_MM, because this one is being spent to
# shorten the cheek flanges: every mm of cheek hole-to-bend is a mm of flange length. Spent down to a
# token 0.010 mm -- the cheek bolts now sit on the half-die minimum, compliant with no real margin.
# Not exactly 0.0: that lands on the rule value and float noise reads it as a hair under, tripping the
# guard. 0.010 mm is geometrically nothing and keeps the check meaningful.
SERVO2_HOLE_TO_BEND_SAFETY_MM = 0.01
SERVO2_WALL_CLEARANCE_MM = max(
    SERVO2_WALL_CLEARANCE_FLOOR_MM,
    _MIN_HOLE_TO_BEND_MM
    - SERVO2_HOLE_INSET_MM
    + _CHEEK_BEND_DATUM_OFFSET_MM
    + SERVO2_HOLE_TO_BEND_SAFETY_MM,
)
# (derived below, once SPINE_OUTER_X_MM is known)
#
# Edge margin from a cheek bolt to the flange tip, at its floor. It was 1.500 mm -- a design choice
# above the 0.970 mm rule -- and that surplus is flange length, so it is spent.
#
# The floor is NOT the rule value: the -z cheek is SERVO2_TIP_RIB_RELIEF_MM shorter than the +z one
# (it is pulled back to clear the case rib) while carrying its bolt at the same place, so the margin
# has to cover the rule PLUS that relief or the short cheek breaks hole-to-edge. Landing exactly on
# the rule for the -z cheek and rule+relief for the +z one.
TAB_EDGE_MARGIN_MM = SENDCUTSEND_MIN_HOLE_TO_EDGE_MM + (
    SERVO2_TIP_RIB_DEPTH_MM + SERVO2_TIP_RIB_CLEARANCE_MM
)
# Cheek tip margin: at least enough to clear the bolt, and enough that the formed flange reaches the
# published minimum length measured from the bend at the spine's outer face.
CHEEK_TIP_MARGIN_MM = max(
    M2_CLEARANCE_RADIUS_MM + TAB_EDGE_MARGIN_MM,
    SENDCUTSEND_MIN_FLANGE_FORMED_MM
    - (SERVO2_WALL_CLEARANCE_MM + SERVO2_HOLE_INSET_MM)
    + SENDCUTSEND_BEND_SAFETY_MM,
)

ALLOW_CONTINUOUS_ROTATION = False
# Cheek outlines are taken from link_plate's two servo flanges, whose hole spacings match ours
# exactly (24.45 mm and 20.7 mm):
#   @cad[STEP/link_plate_left#f52]  29 x 10 plate, inner edge notched back 2.1 mm across 19.8 mm
#                                     between two hole ears, all corners r=0.8
#   @cad[STEP/link_plate_left#f4]   11.6 x 27.539 plate, r=11.0 relief arc at one corner, r=0.8
# The notch is the dominant feature (41.58 of f52's 49.72 mm2 of relief); it clears the servo's
# raised centre zone while the ears carry the bolts.
# The two flanges are NOT the same shape and do not share holes:
#   top of servo    (local y=6.4 pair, 20.7 mm spacing)  -> f4 outline:  r=11.0 corner sweep
#   bottom of servo (local y=-25.6 pair, 24.45 mm spacing) -> f52 outline: 2.1 mm central notch
# Measured: the servo's tip-end bosses reach 2.556 mm back from the cheek tip. The notch clears them
# with margin, so the ears keep the full flange length while the middle steps clear.
SERVO2_TIP_BOSS_DEPTH_MM = 2.556
CHEEK_NOTCH_DEPTH_MM = SERVO2_TIP_BOSS_DEPTH_MM + SENDCUTSEND_BEND_SAFETY_MM
# The two case faces are NOT mirror images. The -z face carries a lengthwise rib standing 1.100 mm
# proud of the mounting plane and running the full length of the flange, so the notch (which only
# spans between the ears) cannot clear it -- the rib passes outboard of both ears. Measured, the rib
# starts 0.314 mm inboard of the cheek tip, so only that cheek's tip is pulled back. The +z cheek is
# unaffected and keeps its full length; every protrusion on that side falls inside the notch.
SERVO2_TIP_RIB_RELIEF_MM = SERVO2_TIP_RIB_DEPTH_MM + SERVO2_TIP_RIB_CLEARANCE_MM
CHEEK_EAR_HALF_WIDTH_MM = 2.6
# f4's corner sweep: r=11.0 arc cutting legs off the tip corner. link_plate's own legs (2.048 x
# 2.586) cut too deep HERE, because our bolt sits closer to that corner than its does: measured on
# the flat pattern the arc came within 0.468 mm of the M2 bolt against a 0.970 mm hole-to-edge
# minimum, and the -z cheek's rib relief makes it worse by pulling the tip inboard. Scaled to 0.60,
# which is where the arc stops being the governing edge at all (0.60 and below both measure 1.041 mm
# -- another edge takes over), so this is as much arc as the bolt spacing allows:
#   1.00x -> 0.468   0.90x -> 0.653   0.80x -> 0.836   0.70x -> 1.017   0.60x -> 1.041
CHEEK_SWEEP_RADIUS_MM = 11.0
CHEEK_SWEEP_LEG_SCALE = 0.60
CHEEK_SWEEP_LEG_X_MM = 2.048 * CHEEK_SWEEP_LEG_SCALE
CHEEK_SWEEP_LEG_Y_MM = 2.586 * CHEEK_SWEEP_LEG_SCALE
# The arm web is as wide as the servo-2 connector face. Its edge is not a single straight taper: the
# cap arc carries on past the plain tangent point by CAP_ARC_EXTENSION_DEG, and the tangent at that
# extended point sets the direction of the return leg. The web edge therefore runs
#   connector corner -> (inward) vertex -> (outward, tangent) extended cap point -> around the cap
# which is the first cut inwards.
# Tuned for shoulder-yaw travel, not looks. Re-measured at the CURRENT geometry (spine 22.800 mm,
# servo-1 clearance 1.615 mm, 4.000 mm full-width run) -- every earlier table here was taken against
# a 41.664 mm spine and no longer applied:
#   26 -> 86.48 deg (waist 14.748)   28 -> 87.66 (14.241)   30 -> 88.83 (13.762)
#   32 -> 89.84 (13.309)             33 -> 90.35 (13.092)   34 -> 90.82 (12.881)
#   35 -> 91.29 (12.676)             38 -> 92.58 (12.097)   40 -> 93.36 (11.742)
#   45 -> 95.00 (10.972)             50 -> 96.09 (10.407)   55 -> 96.91 (10.069)
#   60 -> fails to build
# Set to the SMALLEST angle that still clears the 90 deg target: 33 deg at 90.35 deg measured. That
# is only 0.35 deg of margin, deliberately -- the arc is being minimised, and everything it gives up
# in travel it returns as waist, which went 10.069 -> 13.092 mm (+30%) against the previous 55 deg.
#
# The trade is far flatter than it used to be: ~0.24 deg of yaw per degree of arc, not the ~1:1 that
# held at the wider spine. Extra arc is expensive in waist and cheap in travel, so the small angle is
# the better side of that curve. The binding obstacle remains the M2 servo standoffs at r=13.195, not
# the yoke's strength, so shortening or moving those buys travel at no structural cost.
CAP_ARC_EXTENSION_DEG = 33.0
# Where the straight run ENDS and the angle out to the cap begins -- i.e. where the indent starts
# straightening. In straight-to-wall mode this also sets the WALL width, because the wall follows the
# indent, so it is the part's main strength knob rather than just a cut length.
#
# Smaller return = straighten earlier (closer to the cap) = wider indent = wider wall = less travel.
# Measured at the current geometry:
#   2.50 -> wall 15.332 mm (24.53 mm2), travel 84.39     3.50 -> 14.395 (23.04), 87.16
#   4.50 -> 13.459 (21.54), 89.84                        4.60 -> 13.365 (21.39), 90.10
#   4.70 -> 13.272 (21.24), 90.37  <-- set here          4.80 -> 13.178 (21.09), 90.63
#   5.00 -> 12.991 (20.79), 91.16                        5.50 -> 12.523 (20.04), 92.43
#   6.50 -> 11.586 (18.54), 94.76                        7.50 -> 10.650 (17.04), 95.33
# 4.700 is the earliest straightening that still clears 90 deg with the same 0.35 deg margin used for
# CAP_ARC_EXTENSION_DEG. It buys back 25% of wall section (17.04 -> 21.24 mm2) against the 7.500 that
# the straight-to-wall change first landed on, spending travel that was surplus to the target.
INTERIOR_CUT_RETURN_MM = 4.7
# The web runs STRAIGHT from the indent into the wall, at the indent's own width, instead of widening
# back out to full width.
#
# The widening was a real cost, not a cosmetic one: it put the web's widest material at the wall end,
# which is the largest radius from the yaw axis, and that is exactly what sweeps the M2 standoffs.
# A parallel-sided section at the indent width removes it, which buys travel -- and travel is what
# pays for a tighter clearance to servo 1.
#
# It is also the shape the arm bends need. The fillets require parallel-sided web at the bend line,
# which is why the earlier symmetric-V attempt (legs mirrored about the vertex) could not be built at
# ANY wall width: the vertex sits ~3x closer to the wall than to the cap, so equal-slope legs cannot
# terminate on both, and the mirrored leg never reaches the cap circle at all.
ARM_WEB_STRAIGHT_TO_WALL = True
# The TOP arm alone drops the interior cut. The cut exists to keep material off the radii that sweep
# the M2 standoffs, and the standoffs are below servo 1 -- only the BOTTOM arm passes them. So the top
# arm runs as a plain triangle: one straight line from each corner of the wall, tangent to the horn
# cap, so it peels off the cap instead of stepping off it. That returns the section the cut removed
# (web area at the wall end: 6.5 mm2 per side) at no cost in travel, since the yaw limit is set by the
# bottom arm.
#
# The wide end stays at the WALL's own corners (z +/-6.636), not out at the cheeks' inner faces
# (+/-16.000). Wider is not manufacturable from this blank: in the flat pattern the material beyond
# |z| = 6.636 above the arm's fold line is the cheek risers (they unfold to |z| 6.636..16.099 and run
# to y = 23.044, well past the fold at 8.311), so a fold line longer than the wall would need the same
# blank area twice.
TOP_ARM_STRAIGHT_TAPER = True
# Parallel-sided root the taper starts from, for the bend fillet's sake -- see _capped_arm. How short it
# can be depends on the wall's distance: at WALL_TO_SERVO1_GAP 1.000 everything down to 0.250 built, but
# at 4.000 the wall sits 3 mm further from the cap, the taper leaves at a shallower angle, and 1.000 mm
# of parallel web is no longer enough for the top arm's inner bend fillet -- swept again, 1.000 fails and
# 1.250 upward build. Held at 2.000 for margin rather than at the threshold. The bottom arm's equivalent
# parallel root -- out to its indent vertex -- is 6.458 mm.
# DERIVED, not 2.000. This run exists so the arm's bend fillet terminates against parallel-sided web
# rather than into the taper -- so it has to be at least the OUTSIDE radius, which grows with sheet.
#   1.6002 -> r_out 2.4892, and the old literal 2.000 was ALREADY 0.489 short of it
#   2.0320 -> r_out 2.9972, and 2.000 fails outright: build123d refuses the fillet
# +0.2 of margin so the fillet lands on flat web, not exactly on the taper's first vertex.
TOP_ARM_TAPER_ROOT_RUN_MM = SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM + SHEET_THICKNESS_MM + 0.2

# --- Derived -----------------------------------------------------------------------------------
_CASE_CORNER_RADII_MM = tuple(
    math.hypot(x - HORN_AXIS_X_MM, z - HORN_AXIS_Z_MM)
    for x in (SERVO_CASE_X_MIN_MM, SERVO_CASE_X_MAX_MM)
    for z in (SERVO_CASE_Z_MIN_MM, SERVO_CASE_Z_MAX_MM)
)
CASE_NEAR_CORNER_RADIUS_MM = min(_CASE_CORNER_RADII_MM)

# The spine radius is set from the MEASURED touch point, not from the case's nearest corner.
#
# CASE_NEAR_CORNER_RADIUS_MM (15.968) is a conservative bound: it assumes a case corner can line up
# perpendicular to the wall, which the geometry never actually allows within the wall's z span. Swept
# through 0..95 deg and measured wall-to-case, the bound overstates the real gap by ~2.3 mm:
#   spine R 16.583 -> 2.290 mm min gap   15.583 -> 1.290   14.583 -> 0.290
#           13.583 -> 0.000, and it strikes servo 1 at 33 deg;  12.583 -> will not build
# Linear in R, so the wall first touches at R = 14.293. The radius is that touch point plus a real
# assembly gap, which is a number you can reason about, unlike the corner bound.
CASE_WALL_TOUCH_RADIUS_MM = 14.293
WALL_TO_SERVO1_GAP_MM = 4.0
# 1.000 -> 4.000 as requested. Everything the wall carries moves out with it, which is mostly good: the
# arm's horn bolts gain the same 3.000 mm from their bend line, so F6's half-die violation (5.704 vs
# 6.494) clears on its own, and travel gets cheaper rather than dearer (tightening this cost ~1.8 deg
# per mm). It also moves servo 2, and therefore the pitch and roll origins -- the params guard in
# tom_v2.step.py prints the new ones.
SPINE_INNER_RADIUS_MM = CASE_WALL_TOUCH_RADIUS_MM + WALL_TO_SERVO1_GAP_MM

SPINE_INNER_X_MM = HORN_AXIS_X_MM - SPINE_INNER_RADIUS_MM
SPINE_OUTER_X_MM = SPINE_INNER_X_MM - SHEET_THICKNESS_MM

TOP_ARM_INNER_Y_MM = TOP_HORN_FACE_Y_MM
TOP_ARM_OUTER_Y_MM = TOP_ARM_INNER_Y_MM + SHEET_THICKNESS_MM
# Seats directly on the horn face, so the flange is attached with no intermediate part.
BOTTOM_ARM_INNER_Y_MM = BOTTOM_HORN_FACE_Y_MM - BOTTOM_FLANGE_TO_HORN_CLEARANCE_MM
BOTTOM_ARM_OUTER_Y_MM = BOTTOM_ARM_INNER_Y_MM - SHEET_THICKNESS_MM

ARM_TIP_X_MM = HORN_AXIS_X_MM + ARM_CAP_RADIUS_MM

# Placement follows the spine's outer face, so the servo tracks any change to the spine radius.
SERVO2_PLACEMENT_TX_MM = (
    SPINE_OUTER_X_MM - SERVO2_WALL_CLEARANCE_MM - SERVO2_MATING_FACE_LOCAL_Z_MM
)

# Vertical: the cheeks sit at the TOP of the yoke, with their upper edge landing where the top bend
# STARTS -- the tangent line on the spine's outer face, @cad[STEP/shoulder_yaw_yoke#e86] -- rather
# than flush with the arm's outer face. Flush put the cheek's top BEND_OUTER_RADIUS_MM (2.489 mm)
# into the arm's bend zone, which in the flat pattern is material the arm bend already owns; stopping
# at the tangent means each flange begins on sound flat metal below the bend. Servo 2 rides down with
# them, since the hole pattern is what positions both.
# Horizontal: centre the two cheek planes about z=0 so the bracket is symmetric.
_HOLE_YOKE_YS = [-x for x, _y in SERVO2_HOLE_LOCAL_XY_MM]
_HOLE_YOKE_ZS = [-y for _x, y in SERVO2_HOLE_LOCAL_XY_MM]
# The cheeks RISE past the wall's top edge, carrying their holes and servo 2 up with them.
#
# Servo 2's horn is a D20 disc whose lower edge hangs 10 mm below its own axis, and its lowest horn
# feature was dipping 6.323 mm below servo 1's top (servo 1 tops out at its horn face, yoke y 9.200).
# Datumed off the LOWEST horn feature, not the disc: the disc alone is 5.123 mm down, and using that
# left the part 0.200 mm short. Lifting the holes fixes it, and there IS room: the cheeks run in -x
# from the
# wall while the top arm extends in +x, so they are on opposite sides of it. A cheek can stand proud
# of the wall's top edge without ever meeting the arm.
#
# In the flat pattern this is ordinary: the fold line only spans the wall's own height, and the cheek
# material above it is contiguous flange that folds along with the rest.
SERVO2_HORN_LOWEST_BELOW_SERVO1_TOP_MM = 6.323
SERVO2_HORN_CLEARANCE_ABOVE_SERVO1_MM = 1.0
# Extra lift so yoke 2's roll collar lands FLUSH on this yoke's top arm at pitch +90 deg, giving the
# pitch joint a hard stop there. Measured: at +90 the collar's back sat at assembly z 42.170 while the
# arm's upper face is at 49.580, so it was 7.410 mm low. Lifting the cheeks raises servo 2, yoke 2 and
# the collar together -- and the pitch origin with them -- so the rotated position moves by the same
# amount. It also only increases the servo-2 horn clearance above servo 1, so G10 still holds.
CHEEK_EXTRA_LIFT_FOR_PITCH_STOP_MM = 6.4002
# 7.410 -> 6.400: the collar's lip lost 1.000 mm of height, which lifted its landing face by the same
# amount, leaving it 1.0098 mm ABOVE the arm at +90 instead of on it. The cheeks come down by exactly
# that, since lowering them lowers servo 2, yoke 2 and the collar together, 1:1 with this number. The
# 0.1998 mm the two yokes measure apart at +90 is a LATERAL gap (yoke 1's cheek at assembly y -17.600
# against yoke 2's flange at -17.800), so it does not close as the collar descends.
CHEEK_RISE_ABOVE_WALL_MM = (
    SERVO2_HORN_LOWEST_BELOW_SERVO1_TOP_MM
    + SERVO2_HORN_CLEARANCE_ABOVE_SERVO1_MM
    + CHEEK_EXTRA_LIFT_FOR_PITCH_STOP_MM
)
CHEEK_TOP_DATUM_Y_MM = (
    TOP_ARM_INNER_Y_MM - SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM + CHEEK_RISE_ABOVE_WALL_MM
)
SERVO2_PLACEMENT_TY_MM = (
    CHEEK_TOP_DATUM_Y_MM
    - (M2_CLEARANCE_RADIUS_MM + TAB_EDGE_MARGIN_MM)
    - max(_HOLE_YOKE_YS)
)
SERVO2_PLACEMENT_TZ_MM = -0.5 * (min(_HOLE_YOKE_ZS) + max(_HOLE_YOKE_ZS))

# Tab geometry, derived from the servo-2 hole positions in yoke coordinates.
# Hole positions in yoke coords: (x, y, z) with the axis along z.
SERVO2_HOLES_YOKE_MM: tuple[tuple[float, float, float], ...] = tuple(
    (SERVO2_HOLE_LOCAL_Z_MM + SERVO2_PLACEMENT_TX_MM,
     -x + SERVO2_PLACEMENT_TY_MM,
     -y + SERVO2_PLACEMENT_TZ_MM)
    for x, y in SERVO2_HOLE_LOCAL_XY_MM
)
_HOLE_PLANE_Z_MM = max(abs(-y + SERVO2_PLACEMENT_TZ_MM) for _x, y in SERVO2_HOLE_LOCAL_XY_MM)
# Seat on the servo's real mounting faces, which are the HOLE planes.
#
# SERVO2_CASE_*_LOCAL_MM are the whole servo's y extremes, so they include the output horn and idler
# boss -- deriving the cheeks from them put the flanges 1-2 mm outboard of anything they could touch.
# Measured inside the cheek footprint, the load-bearing case faces are at the hole planes; the only
# material further out is a set of small bosses near the cheek TIP (measured 10.035..12.591 mm from
# the bend), which the tip notch below clears.
CHEEK_INNER_Z_POS_MM = _HOLE_PLANE_Z_MM + fit.CASE_MOUNT_GAP_MM
# The wall itself is only as wide as the servo horn; the reach out to the cheek bend tangent is a
# local EAR, present only over the cheeks' own height.
#
# The tangent above cannot move: the cheeks have to seat on servo 2's case faces at z=+/-16.000, so
# they must fold from +/-15.111 whatever the wall does. A uniformly horn-width wall therefore cannot
# reach them at all. Splitting the two -- horn-width wall, local ears where the flanges fold -- is
# what satisfies both, and it is an ordinary partial-width flange rather than a compromise. The arms
# ride on the wall width, so they come down to horn width too, which is where most of the material
# and swept radius actually goes.
# The target is the horn's own width, but the arm web cannot run all the way down to it: the web
# blends into a cap of ARM_CAP_RADIUS, and as the web narrows towards that radius its edges go
# tangent to the cap and the blend degenerates. Measured, holding every other constraint fixed:
#   half 15.111 OK | 13.000 OK | 12.000 OK | 11.400 OK | 11.200 bend fillet fails
#   half 10.000 (horn width) fails outright, even with the interior cut and both web fillets removed
# The cap cannot shrink to make room either -- it is floored at 9.670 mm by the horn bolt circle
# (7.000 + 1.700 + 0.970 hole-to-edge). So the wall goes as narrow as the horn asks for OR as narrow
# as the cap blend allows, whichever is wider, and here that is the cap: 22.800 mm rather than 20.000.
# Reaching a true horn width means reworking the arm into a plain tangent strip with no interior cut,
# which trades away the cut's yaw clearance -- a design change, not a width change.
ARM_WEB_CAP_STANDOFF_MM = 1.4
_ARM_WEB_NOMINAL_HALF_Z_MM = max(
    0.5 * YOKE_WIDTH_Z_MM, ARM_CAP_RADIUS_MM + ARM_WEB_CAP_STANDOFF_MM
)
# With the straight-to-wall web the arm arrives at the wall at the INDENT's half width, not the
# nominal one, and the wall has to match it: a 90 deg bend fillet cannot terminate where the flange is
# narrower than the plate it folds from (measured -- it fails at the outer radius every time). So the
# wall follows the arm, and the cheek ears reach out from there to the fold tangent as before.
# The indent is computed from the NOMINAL half width, so there is no circular definition.
def _indent_half_z(spine_inner_x: float) -> float:
    """Half width the web carries into the wall: the interior cut's own vertex z."""
    cx, cz = HORN_AXIS_X_MM, HORN_AXIS_Z_MM
    best = None
    for sign in (1.0, -1.0):
        dx, dz = spine_inner_x - cx, _ARM_WEB_NOMINAL_HALF_Z_MM - cz
        d = math.hypot(dx, dz)
        if d <= ARM_CAP_RADIUS_MM:
            continue
        alpha = math.atan2(dz, dx) + sign * math.acos(ARM_CAP_RADIUS_MM / d)
        tx, tz = cx + ARM_CAP_RADIUS_MM * math.cos(alpha), cz + ARM_CAP_RADIUS_MM * math.sin(alpha)
        if best is None or tz > best[1]:
            best = (tx, tz)
    phi = math.atan2(best[1] - cz, best[0] - cx) + math.radians(CAP_ARC_EXTENSION_DEG)
    ex, ez = cx + ARM_CAP_RADIUS_MM * math.cos(phi), cz + ARM_CAP_RADIUS_MM * math.sin(phi)
    dirx, dirz = -math.sin(phi), math.cos(phi)
    if dirx > 0.0:
        dirx, dirz = -dirx, -dirz
    return ez + INTERIOR_CUT_RETURN_MM * dirz


SPINE_BASE_HALF_Z_MM = (
    _indent_half_z(HORN_AXIS_X_MM - SPINE_INNER_RADIUS_MM)
    if ARM_WEB_STRAIGHT_TO_WALL
    else _ARM_WEB_NOMINAL_HALF_Z_MM
)
# Half width of the TOP arm's fold line, and so of the wide end of its taper (TOP_ARM_STRAIGHT_TAPER).
# The arm can fold off far more than the wall's own 6.636: the ear already carries the wall's plane out
# to the cheeks over the whole height below the fold, so the fold line is free to run the full width of
# the ear. What stops it is the CHEEK's bend, whose zone starts at the cheek's inner tangent -- the two
# bends have to stay disjoint in the flat, so the arm stops exactly there.
TOP_ARM_FOLD_HALF_Z_MM = (
    CHEEK_INNER_Z_POS_MM - SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM
    if INCLUDE_SERVO2_TABS
    else SPINE_BASE_HALF_Z_MM
)
CHEEK_TIP_X_MM = min(x for x, _y, _z in SERVO2_HOLES_YOKE_MM) - CHEEK_TIP_MARGIN_MM


# The arms bolt to a round horn, so they stay symmetric; sized to the narrower spine half so the web
# never overhangs the spine on either side.
ARM_WEB_HALF_Z_MM = SPINE_BASE_HALF_Z_MM
BEND_INNER_RADIUS_MM = SENDCUTSEND_EFFECTIVE_BEND_RADIUS_MM
BEND_OUTER_RADIUS_MM = BEND_INNER_RADIUS_MM + SHEET_THICKNESS_MM
MIN_HOLE_TO_BEND_MM = SENDCUTSEND_HALF_DIE_WIDTH_MM + SENDCUTSEND_MOUNT_HOLE_TO_BEND_BUFFER_MM
# Neutral-axis flat length of the developed strip (two 90 deg bends).
BEND_ALLOWANCE_90_MM = (math.pi / 2.0) * (
    BEND_INNER_RADIUS_MM + (SENDCUTSEND_K_FACTOR * SHEET_THICKNESS_MM)
)


def _horn_bolt_centers_xz() -> tuple[tuple[float, float], ...]:
    return tuple(
        (
            HORN_AXIS_X_MM
            + HORN_BOLT_CIRCLE_RADIUS_MM * math.cos(2.0 * math.pi * i / HORN_BOLT_COUNT),
            HORN_AXIS_Z_MM
            + HORN_BOLT_CIRCLE_RADIUS_MM * math.sin(2.0 * math.pi * i / HORN_BOLT_COUNT),
        )
        for i in range(HORN_BOLT_COUNT)
    )


def _cap_tangent_point(from_x: float, from_z: float) -> tuple[float, float]:
    """Tangent point on the horn cap circle for a line from (from_x, from_z), upper side."""
    cx, cz = HORN_AXIS_X_MM, HORN_AXIS_Z_MM
    r = ARM_CAP_RADIUS_MM
    dx, dz = from_x - cx, from_z - cz
    d = math.hypot(dx, dz)
    if d <= r:
        raise RuntimeError("Web start point is inside the horn cap circle")
    beta = math.acos(r / d)
    ux, uz = dx / d, dz / d
    best = None
    for sign in (1.0, -1.0):
        ca, sa = math.cos(sign * beta), math.sin(sign * beta)
        tx = cx + r * (ux * ca - uz * sa)
        tz = cz + r * (ux * sa + uz * ca)
        if best is None or tz > best[1]:
            best = (tx, tz)
    return best


def _interior_cut_points(
    from_x: float, from_z: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Extended cap contact point and the interior-cut vertex, upper side.

    The plain tangent point is rotated CAP_ARC_EXTENSION_DEG further around the cap (toward the
    spine). The tangent direction there is the return leg; the vertex sits INTERIOR_CUT_RETURN_MM
    back along it, and the connector corner joins straight to that vertex.
    """
    cx, cz = HORN_AXIS_X_MM, HORN_AXIS_Z_MM
    tx, tz = _cap_tangent_point(from_x, from_z)
    phi = math.atan2(tz - cz, tx - cx)
    # Rotate toward the spine (-x): increase the angle for the upper side.
    phi_ext = phi + math.radians(CAP_ARC_EXTENSION_DEG)
    ex = cx + ARM_CAP_RADIUS_MM * math.cos(phi_ext)
    ez = cz + ARM_CAP_RADIUS_MM * math.sin(phi_ext)
    # Tangent at the extended point, pointing back toward the spine.
    dirx, dirz = -math.sin(phi_ext), math.cos(phi_ext)
    if dirx > 0.0:
        dirx, dirz = -dirx, -dirz
    vx = ex + INTERIOR_CUT_RETURN_MM * dirx
    vz = ez + INTERIOR_CUT_RETURN_MM * dirz
    return (ex, ez), (vx, vz)


def _sweep_center(
    corner_x: float, corner_y: float, leg_x: float, leg_y: float, radius: float
) -> tuple[float, float]:
    """Centre of the radius-`radius` arc that cuts `leg_x` x `leg_y` off a corner (f4's relief)."""
    p1 = (corner_x + leg_x, corner_y)
    p2 = (corner_x, corner_y - leg_y)
    mx, my = 0.5 * (p1[0] + p2[0]), 0.5 * (p1[1] + p2[1])
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    chord = math.hypot(dx, dy)
    if chord >= 2.0 * radius:
        raise RuntimeError("Sweep radius too small for the requested corner legs")
    offset = math.sqrt(radius**2 - (0.5 * chord) ** 2)
    px, py = -dy / chord, dx / chord
    if (corner_x - mx) * px + (corner_y - my) * py < 0.0:
        px, py = -px, -py
    return mx + offset * px, my + offset * py


def _fillet_z_corner(shape: build123d.Shape, x: float, y: float, radius: float) -> build123d.Shape:
    """Fillet the full-width edge running along Z at corner (x, y)."""
    tolerance = 0.05
    matches = [
        edge
        for edge in shape.edges().filter_by(build123d.Axis.Z)
        if abs(edge.center().X - x) < tolerance and abs(edge.center().Y - y) < tolerance
    ]
    if not matches:
        raise RuntimeError(f"No Z edge found at corner ({x:.3f}, {y:.3f}) to fillet")
    return as_single_shape(build123d.fillet(matches, radius))


