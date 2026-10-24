"""gripper's LEFT CLAW: the fixed jaw, at the shared envelope's 20.000 band, slid out onto the recess line.

Rev3 datums and helpers the rev4 stages still read; the standalone part model is in git history.

Not a fork -- the geometry all comes from gripper_mirrored_envelope.step.py, built through the
variant hook with two settings changed, so anything done to that jaw reaches this one too. The two
settings are independent and both matter:

  CHEEK_WIDTH_MM   20.0000  how wide the band runs. The shared generator's own default, and the same
                            20.000 the moving claw carries (gripper#o1.5.e50 / .e51 / .e52 against
                            this part's #o1.4.e19 / .e69 / .e81) -- the two jaws are the same
                            thickness, so their 45 deg tip cuts come out the same size again.
  CHEEK_FOLD_Y_MM  17.6502  where the fold sits, level with the servo recess's low edge
                            (gripper#o1.4.e71). Without this the band can only grow toward the fold,
                            which walks the jaw plate inboard.

Width and position are separate knobs on purpose. CHEEK_WIDTH_MM alone eats the band from the fold
side, so changing it moves the jaw plate; pinning the fold makes the band grow the OTHER way, out
past the servo's edge, and leaves the plate where the recess line puts it.

WHAT IT COSTS. The band's low edge lands at y -2.3498, which is 15.040 clear of the claw servo's own
edge at 12.690 -- the cheeks simply hang out past it, and nothing is out there to hit (measured
clear against every other solid in gripper). The jaw faces now rest 15.1716 apart. That is the
minimum grasp, and it is NOT what the closing solve assumes: gripper_right_claw's 73.3047 reach and
tom_v2.params.js's -14.8929 limit were solved for 9.518, before either jaw moved. Re-solve the reach
and the limit together before trusting a closed pose here.

Was gripper_mirrored_envelope_narrow.step.py, which existed to hold a 10.7878 band. That band is
gone -- the name outlived it by one edit -- but the 10.7878 solve is written up in the git history of
this file and in gripper.step.py's instance note.
"""

from __future__ import annotations
from lib import fastener_clearance as fc



import math
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
# 2mm tree: SRC_DIR is this folder, so its parent is STEP -- the 1.6002 mm ORIGINALS. Putting
# that on sys.path ahead of this folder silently rebuilds the thin part (it did: the frame came
# out 1.6002 and byte-identical). The repo root is one further up.
REPO_ROOT = SRC_DIR.parents[1]
VENDOR_DIR = REPO_ROOT / "STEP" / "imported"

from lib import sheet_rule_scs as scs  # noqa: E402

PART_NAME = "gripper_left_claw.step"  # pinned: the label these parts shipped with, when the source was gripper_left_claw.step.py
DISPLAY_NAME = "Gripper Left Claw"

# THE WHOLE BAND RIDES THE FOLD, 20.0000 WIDE, since 2026-08-25: first widened downward so its
# width matches the moving jaw's exactly (@cad[gripper#o1.4.e15] to #o1.4.e1 against
# #o1.5.e46..e48 -- the family band gave 19.9238, 0.0762 shy), then shifted UP with the fold when
# the connection plate moved to cover the servo's -z case-bolt bore (see CHEEK_FOLD_Y_MM below).
# The width constraint is the invariant: e1 to e15 stays 20.0000 through both moves.
CHEEK_BAND_LOW_Y_MM = None  # assigned right after CHEEK_FOLD_Y_MM below -- fold minus 20.0

CHEEK_FOLD_Y_MM = 21.8240             # frozen -- see above
CHEEK_BAND_LOW_Y_MM = CHEEK_FOLD_Y_MM - 20.0                            # 1.8240
CHEEK_WIDTH_MM = CHEEK_FOLD_Y_MM - CHEEK_BAND_LOW_Y_MM        # 19.9238

# The lead-in radius stays the CAP's, 10.0000, and is now passed explicitly. The shared generator used
# to take it as half this band -- fine while the band was the cap's diameter, wrong the moment it is
# not: half of 24.2500 would have moved both quarter-round lead-ins to r12.1250 behind our back.
LEAD_IN_R_MM = 10.0


# WHICH GRIP CHEEK STANDS UP OVER THE SERVO. The +z one's block is dropped, so that side is the bare
# band from the tip right through to the corner break; the -z one keeps its block, its two case bolts
# and its connector recess. The jaw, both bends and both cheek strips are untouched either way -- this
# only takes the material above the fold on one side.
#
# Asymmetric on purpose, and it does cost fastening: the servo is now gripped on one side only.
# BOTH, since 2026-08-24. The -z block went the same way the +z one had: the cheek gusset now runs
# out to the back of the claw servo and carries its own M2 (see CHEEK_GUSSET_* above), so the blocks
# were reaching over a servo that is already backed and bolted. What they leave behind is the bare
# band on both sides -- jaw, bend and cheek strip all still there.
#
# WHAT IT COSTS, and it is not small: the two blocks were this jaw's only grip on the servo's far-side
# M2s, one pair each. All four of those are gone. The joint is now the gusset's single M2 plus the
# channel's own stiffness. Deliberate, and the reason the gusset was lengthened first.
DROP_GRIP_CHEEK = "both"

# The connector notch in the cheek that is left. The bracket family cut it to clear the servo's
# connector shroud; this jaw's cheek sits outboard of the case, so it clears nothing here and the
# sheet is better solid. Verified against the built assembly, not taken on trust: with it filled the
# claw still measures 0.00 mm^3 against the claw servo and every other solid in gripper.
FILL_CONNECTOR_RECESS = True

# HOW FAR THE GRIP BLOCK'S BACK WALL SITS BEHIND ITS CASE BOLTS, hole edge to wall. The block was the
# bracket's own 10.8100 wide with everything behind the bolts doing nothing; this brings that wall in
# toward the outboard edge, which is what gripper#o1.4.e26 moving toward #o1.4.e5 asks for.
#
# 3.2004 is 2 x sheet. SendCutSend's floor is 0.9700 and would allow 2.2302 mm more, but that is
# already the ligament on the OUTBOARD side of the same holes -- 2.0700 centre to edge less the 1.1000
# hole -- so cutting the back to match would leave the strap at the floor on both sides at once,
# with two M2s carrying the jaw. Stopping at twice the floor keeps a real ligament on the one side
# that still has one, and the strap 6.3706 wide instead of 4.1400.
GRIP_BLOCK_BACK_MARGIN_MM = 2.0 * 1.6002


# THE GUSSET off the bare cheek's outboard edge (gripper#o1.4.e49): the +z cheek lost its grip block,
# so it has nothing standing up over the servo. This runs a triangular tab back toward the frame --
# full 20.0000 band height where it leaves that edge, tapering to a point.
#
# 15.4320 is solved, not drawn: the cheek's edge sits at x -70.7786 and the FRAME's own +z cheek
# starts at x -55.3466, and the two are coplanar (both z 16.0000..17.6002), so the tab runs out to
# exactly where the frame's sheet begins and the two meet edge to edge.
#
# 1.5000 short of the frame's cheek rather than flush on it: two coplanar sheet edges meeting at zero
# is a fit nobody can assemble, and this joint has no fastener across it to pull them together. The
# gap is between gripper#o1.4.e55 and gripper#o1.1.e149.
CHEEK_GUSSET_CLEARANCE_MM = 1.5

# ...AND THAT IS NO LONGER WHAT SETS IT (2026-08-24). The tab is run further, past the frame's cheek
# entirely, to reach the servo's NEXT case bolt inboard -- @cad[tom#o1.23.3.e145], a D2.0000 hole on
# the same case face this cheek lies against, at part-frame x -52.8070. It shares its y with the
# first bolt in CASE_BOLTS_XY_MM below (15.0502), so it is the same row: the tab simply did not reach
# it before, stopping 3.5316 short of its centre and 2.5372 short of its near edge.
#
# THIS DELIBERATELY OVERRUNS THE FRAME. CHEEK_GUSSET_CLEARANCE_MM above is kept because it still
# records the fit it was solved for, but the two sheets now overlap rather than meet edge to edge --
# interference with the frame (tom#o1.22) is accepted, on instruction.
#
# BACK TO THE BUTT JOINT (2026-08-24). For a while this ran to the servo case's BACK face
# (@cad[tom#o1.23.3.e409], x -50.7026) and carried its own M2 at the case bolt @cad[tom#o1.23.3.e145]
# -- the frame's +z cheek had been cut away there, so this tab took over that fastening. The frame
# has that flange BACK now, and the two sheets lie on the SAME servo face: coplanar plates cannot
# cross, so the tab returns to its original arrangement -- it stops CHEEK_GUSSET_CLEARANCE_MM short
# of the frame cheek's outboard edge and butts it, and the bolt is the frame's again.
# Requested M2 close clearance. Hole size alone does not absorb forming
# position error; see SERVO_FIT_UPDATE.md for this claw's bend-end finding.
M2_CLEARANCE_RADIUS_MM = fc.M2_CLEARANCE_RADIUS_MM
# Both edges REMEASURED 2026-08-24 after the M2 clearance bump: the family derives its cheek edges
# from bolt-plus-margin, so Ø2.2 -> Ø2.4 slid every such edge 0.1 outboard, and the stale pair left
# the butt gap at 1.3000 instead of CHEEK_GUSSET_CLEARANCE_MM.
CHEEK_GUSSET_EDGE_X_MM = -70.1706        # measured: the bare cheek's outboard edge, the tab's root
# The frame's +z cheek outboard edge, measured off the built frame in this part's x (the two share
# it). The tab ends CHEEK_GUSSET_CLEARANCE_MM short of it -- two coplanar sheet edges meeting at
# zero is a fit nobody can assemble.
FRAME_CHEEK_EDGE_X_MM = -55.9546
CHEEK_GUSSET_RUN_MM = (
    FRAME_CHEEK_EDGE_X_MM - CHEEK_GUSSET_CLEARANCE_MM
) - CHEEK_GUSSET_EDGE_X_MM

# ...and it ends STRAIGHT, not at a point. 5.1340 is the overlap the two coplanar sheets actually
# share: this band's top edge is the fold line at part y 17.6502, the frame's own cheek starts at
# 14.2662 in the assembly, which is 12.5162 here once the group's 1.7500 shift is taken off. The tab's
# straight end spans exactly that, so it meets the frame's sheet edge on, and the diagonal runs from
# the foot of it back to the band's low edge.
#
# Both corners of that end carry the family's r1.000 break. The tab's root corners do not -- the
# profile is drawn back into the plate so they are buried, which also swallows the cheek's two old
# outboard breaks rather than leaving them as notches along the new edge.
CHEEK_GUSSET_END_MM = 17.6502 - 12.5162


# THE JAW'S GEOMETRY, all three numbers solved together rather than drawn. Part frame throughout,
# which is the assembly's less the group's 1.7500 y shift.
#
#   fold root   as far INBOARD as SendCutSend allows -- the turn starts there (gripper#o1.4.e1)
#   fold run    whatever length puts the tip at the reach below
#   tilt        whatever angle puts that tip on the wrist servo's centre line
#
# WHY THE ROOT IS WHERE IT IS. The fold is a brake bend, and the die presses on everything within half
# its width of the bend line -- 5.9944 for this material, plus the family's own 0.5000 buffer, so
# 6.4944 from any hole's EDGE. Both cheeks carry the servo's M2 case bolts at x -73.3126, and they sit
# very close to the fold line: 1.1500 off it on the -z cheek, 2.6000 on the +z. So the bend has to
# STOP short of them, and how short is set by the nearer one:
#
#     -z cheek M2   1.1500 off the line  ->  root no further in than -80.8194   <- binds
#     +z cheek M2   2.6000 off the line  ->  root no further in than -80.4481
#     -z cheek M2   21.8500 off the line ->  no limit, it is clear of the die entirely
#
# -80.8194 it is: 4.6114 further in than the family's own root, and the bend runs out at exactly the
# rule minimum to that bolt. Any further and the die lands on the hole.
#
# (2026-08-25: the -z cheek's holes are no longer cut -- the lug went, see build_step() -- so only
# the +z row is a live limit. The solve still reads all three rows, which errs conservative; it is
# unused anyway while the jaw is straight.)
JAW_PIVOT_Y_MM = 17.6502                 # the fold line's y, from CHEEK_FOLD_Y_MM above
CLAW_SERVO_HORN_XY_MM = (-63.0626, 47.8002)
WRIST_SERVO_CENTRE_Y_MM = 27.0000        # assembly 28.7500

# HOW LONG THE JAW IS, tip to the claw servo's horn axis. 82.0000 is the SO-101's own moving jaw,
# measured off TheRobotStudio/SO-ARM100's Moving_Jaw_SO101.stl rather than taken from a spec: its tip
# sits at exactly y -82.000 from the part origin, and that repo's URDF puts the gripper joint's axis
# through the mesh's own x/y origin, so origin-to-tip IS pivot-to-tip.
JAW_REACH_MM = 82.0

MIN_HOLE_TO_BEND_MM = 6.4944             # half die width 5.9944 + the family's 0.5000 buffer
# M2_CLEARANCE_RADIUS_MM is defined above, with the gusset -- that tab now solves against one of the
# servo's case bolts, so the radius has to be in hand before this block.
CASE_BOLTS_XY_MM = ((-73.3126, 15.0502), (-73.3126, 18.8002), (-73.3126, 39.5002))


def _fold_root_x() -> float:
    """The furthest-inboard x the bend can stop at and still clear every case bolt's die zone."""
    need = M2_CLEARANCE_RADIUS_MM + MIN_HOLE_TO_BEND_MM
    limits = [
        hx - math.sqrt(need ** 2 - (hy - JAW_PIVOT_Y_MM) ** 2)
        for hx, hy in CASE_BOLTS_XY_MM
        if abs(hy - JAW_PIVOT_Y_MM) < need
    ]
    if not limits:
        raise ValueError("no case bolt is near the fold line; the root is unconstrained")
    return min(limits)


def _fold_run_and_angle() -> tuple[float, float]:
    """The run and tilt that put the tip JAW_REACH_MM from the horn AND on the centre line.

    Two constraints, two unknowns. The tip is the gripping face's corner, which sits BEND_OUTER off
    the fold line, so the run and the angle are coupled through that offset -- hence the fixed point
    rather than a closed form. Converges in a handful of steps from any sane start.
    """
    root_x = _fold_root_x()
    hx, hy = CLAW_SERVO_HORN_XY_MM
    rise = WRIST_SERVO_CENTRE_Y_MM - hy
    if abs(rise) > JAW_REACH_MM:
        raise ValueError("the centre line is further from the horn than the jaw reaches")
    tip_x = hx - math.sqrt(JAW_REACH_MM ** 2 - rise ** 2)
    theta = 0.1
    for _ in range(400):
        ly = (WRIST_SERVO_CENTRE_Y_MM - JAW_PIVOT_Y_MM) - BEND_OUTER_RADIUS_MM * math.cos(theta)
        lx = (root_x - tip_x) + BEND_OUTER_RADIUS_MM * math.sin(theta)
        theta = math.atan2(ly, lx)
    return math.hypot(lx, ly), -math.degrees(theta)


BEND_OUTER_RADIUS_MM = 2.4892
JAW_ROOT_X_MM = _fold_root_x()
JAW_FOLD_RUN_MM, JAW_ANGLE_SOLVED_DEG = _fold_run_and_angle()

# THE JAW RUNS STRAIGHT OUT AGAIN (2026-08-23). It was tilted onto the wrist servo's centre line on
# 2026-08-22 -- the solve above -- and that solve is left in place and still printed, so the angle it
# would have used stays visible. Two things made the tilt not worth its cost:
#
#   - it never landed where it claimed. _fold_run_and_angle() iterates on BEND_OUTER_RADIUS_MM, which
#     is still the OLD gauge's 2.4892 rather than 2.9972, so it converged on the wrong tip: measured
#     through this part's placement, the angled tip sits 89.7751 from the claw servo's axis against
#     the moving jaw's 82.0000, and the two meet at assembly y -16.0071 instead of the servo's
#     midpoint. Straight, that constant stops feeding geometry at all.
#   - straight, the two jaws end on ONE plane in the open pose, which the tilt gave up.
JAW_ANGLED = False
JAW_ANGLE_DEG = JAW_ANGLE_SOLVED_DEG if JAW_ANGLED else 0.0


# HOW FAR THE JAW PLATE RUNS ON toward the claw servo, past the wall's outer face. Left alone the
# plate simply stops there, at part-frame x -85.4308, and its end face @cad[tom#o1.24.f35] stands in
# mid-air 10.0065 mm short of the servo's own case face @cad[tom#o1.23.1.f11] at -75.4243. Running it
# out backs the fold the whole way to the servo instead of leaving that edge free.
#
# RUN AS FAR AS THE MANUFACTURING RULES ALLOW (2026-08-24), which is the gap less ONE laser cut
# tolerance. Formerly 1.5000, which was a fit clearance rather than a rule.
#
# What each candidate constraint actually does to this dimension:
#   - CUT POSITION, +/-0.1270. Binding. The end of this run is a cut edge, and where it lands along x
#     is a cut-to-cut dimension on the flat pattern.
#   - FORMED ANGLE, +/-1 deg. NOT binding. This plate hangs off the cheek band on a fold whose line
#     runs along x, so an angle error rotates it about an x-parallel axis: it moves the plate in y and
#     z and leaves its x extent alone.
#   - MIN FLANGE, half-die, hole-to-edge. Not engaged -- the run adds sheet to an existing panel and
#     puts no new feature near a bend.
#
# WHAT THIS SPENDS, and it is worth knowing before trusting it: the 1.3730 mm recovered was the only
# allowance for the SERVO's own case tolerance, which Waveshare does not publish. A nominal servo and
# a worst-case cut now clear by 0.0000. Put JAW_ROOT_CLEARANCE_MM back up if a real one fouls.
# THE RUN ENDS ONE CUT TOLERANCE OFF THE SERVO as of 2026-08-25, on instruction ("as flush as
# possible"): the connection face (@cad[tom#o1.24.f26]) runs to the case (@cad[tom#o1.23.1.f11])
# less SendCutSend's published +/-0.005 in cut tolerance -- the one SCS term that binds this
# dimension (bend angle +/-1 deg rotates the plate about an x-parallel fold line, moving it in y/z
# only). Nominal clears by 0.1270; a worst-case-long cut lands line-on-line at 0.0000. The servo's
# own case tolerance is unpublished (Waveshare) and rides on the M2 case-bolt slop (~0.20 radial),
# which lets a light touch self-relieve at assembly -- the same stance this file held before the
# moving-jaw datum. The gap is to the servo's NEAREST material: the case flank carries ~0.5 deg of
# draft and its closest point is the min-x over all five case shells, measured in-assembly
# 2026-08-25. It briefly stopped 0.5000 off (same day) before the flush instruction; the
# 2026-08-24 moving-jaw-level end was x -80.1124 (@cad[tom#o1.25.e1]).
JAW_ROOT_START_X_MM = -85.4308         # the plate's end face the run extrudes from
SERVO_NEAREST_X_MM = -75.4243          # @cad[tom#o1.23.1.f11]'s nearest point (case draft included)
JAW_ROOT_SERVO_GAP_MM = scs.CUT_TOLERANCE_MM                     # 0.1270
JAW_ROOT_END_X_MM = SERVO_NEAREST_X_MM - JAW_ROOT_SERVO_GAP_MM   # -75.5513
JAW_ROOT_EXTENSION_MM = JAW_ROOT_END_X_MM - JAW_ROOT_START_X_MM  # 9.8795


# --- The band's low edge crowned to MATCH the moving jaw, with the same relief slots ---------------
# The IDENTICAL curve gripper_right_claw carries -- same R, same corner span d = 35.4817 -- despite
# this edge being 4.39 shorter. That is only possible because the far end stops being a corner: the
# crown runs past this part's end face, and an r10.0 quarter springs off the (lengthened) end face
# @cad[tom#o1.24.e31] tangent onto the crown, "starting later" down the face. Where it starts
# (yc_far) falls out of the tangency and moves with h. All numbers from
# gripper_common.crown_slot_layout() -- the ONE solve both claws share -- so the curve AND the relief
# slots are identical across the pair, and the slots are sized there to make the canonical crown
# weight-neutral. This side nets slightly positive: the end-quarter fill is extra material the
# canonical solve does not see; the build prints the residual.


# --- What the full-depth run does at each fold's end, checked ------------------------------------
# The run carries the plate and BOTH fold corners to JAW_ROOT_END_X_MM -- the +z fold included, on
# instruction (2026-08-25, gripper#o1.4.e49 extended to meet #o1.4.e5). The -z fold's side is clean:
# that sheet has no holes left (the lug went the same day), and its nearest feature -- the servo
# tab's corner -- is guarded below. The gusset bolt's old +z die-zone deviation CLEARED when the
# fold rose to carry the -z screw hole (its bend margin is 7.71 against the 5.9944 floor now).
# The RECORDED, OWNER-ACCEPTED DEVIATION is the -z screw hole itself: 3.87 by edge from the -z
# bend line's end (4.26 at the family-grid position; the move to the vendor bore cost 0.39),
# under the floor -- but 2.24 beyond the bend's end along the fold, so a punch sectioned to the
# bend length never reaches it; ask for that on the order. Accepted 2026-08-25 with the hole
# itself (the second case fastener is worth the note).


# --- The band top finished: -z remnant filled, free corners rounded ------------------------------
# The -z dropped edge carries its own family remnant (x -73.6906..-71.1346, floor y 21.09..21.22,
# measured 2026-08-25) -- the twin of the +z one, and worse: it dips INTO the screw hole's 2.0
# fastening ligament. Filled flush to the fold, with a post-unify straightness guard. The band
# top's new free corners then take the family outline round: the -z step-down corner at the shroud
# and the held +z edge's east corner at the part's end. The corners at the jaw-root END FACE get
# NOTHING -- those surfaces are flush with the bend and rounding them notched an otherwise flush
# boundary (@cad[gripper#o1.4.e52,o1.4.e31], owner-caught 2026-08-25). Re-entrant corners stay
# square, per the standing doctrine.
