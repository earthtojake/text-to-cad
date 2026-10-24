"""SendCutSend's default sheet spec for ALU-080 (2.032 mm), in ONE place.

All production arm plates share this stock as of 2026-09-13. The existing
base plate is left unchanged. Gauge, bend radius and allowance stay together;
the ALU-063 module remains a historical stock specification only.

Thickness, K factor, radius and relief depth rechecked 2026-09-13 at
https://sendcutsend.com/bending-calculator/. The live calculator lists a
0.138-inch bend relief depth, replacing the older archived 0.150 value.

Pulled 2026-08-23 from cdn.sendcutsend.com/specs/sendcutsend-specs.json,
materials[sku=ALU-080].bending_specs and .cutting_specs (schema_version 1.0,
generated_at 2026-04-29T20:52:33Z), and confirmed against their site.

WHY THIS FILE EXISTS. The k-factor used to be written out FOUR times across the tree -- once in
link_geometry, once in servo_horn_yoke's SHEET_RULE, and once in each of the two gauge tables. All
four happened to say 0.42, but nothing held them together, and the two tables had ALREADY drifted
apart on the 0.080 row (one carries 0.48, the other None). Import from here instead.

It kept happening after that, too: link_plate_pair carried its own SHEET_THICKNESS_MM = 1.6002 and
BEND_INNER_RADIUS_MM = 0.889 straight through the flattening, so its spanning wall built one gauge
thinner than the legs it folds out of and its inner bend arc missed the legs' inner faces by
0.4318 mm. Caught 2026-08-23. Import, do not restate.

THE ONE INCONSISTENCY, and it is SendCutSend's, not ours. Their published k_factor and their
published bend_deduction do not reconcile exactly through the standard formula:

    from k 0.48        BA = (pi/2)(r + k*t)                  = 3.048225 mm
    from BD 0.116 in   BA = 2*OSSB - BD = 2*2.9972 - 2.9464  = 3.048000 mm

0.000225 mm per bend between them at this gauge -- they reconcile to well inside anything that can
be cut or formed, so this is a rounding artefact of their published deduction, not a real conflict.
(An earlier version of this note claimed 0.0496 mm by subtracting the deduction from ONE outside
setback instead of two; the arithmetic above is the corrected one, and ALLOWANCE_DISAGREEMENT_MM
has always computed it correctly.) K_FACTOR IS STILL THE ONE WE FOLLOW -- verified on their site --
so the bend allowance is derived from k below and BEND_DEDUCTION_IN is kept as recorded data only.
Anything that derives an allowance from the deduction is wrong; see the note at
BEND_ALLOWANCE_90_MM.
"""

from __future__ import annotations

import math

MATERIAL = "5052-H32 ALU-080"
SKU = "ALU-080"

K_FACTOR = 0.48
EFFECTIVE_BEND_RADIUS_IN = 0.038
BEND_DEDUCTION_IN = 0.116          # published, NOT used to derive the allowance -- see above
DIE_WIDTH_IN = 0.472
MIN_FLANGE_BEFORE_BEND_IN = 0.255
MIN_FLANGE_AFTER_BEND_IN = 0.313
BEND_RELIEF_DEPTH_IN = 0.138
MIN_CORNER_RELIEF_FROM_BEND_IN = 0.037
MAX_BEND_ANGLE_DEG = 130.0
THICKNESS_IN = 0.080

# --- cutting_specs, same SKU row -------------------------------------------------------------
# The CUT side of the sheet rule; everything above is the BEND side. Kept here rather than at a
# call site for the same reason as the bend numbers: one row, one place, pulled in one go so the
# two halves cannot come from different revisions of the spec.
CUTTING_PROCESS = "Fiber Laser"
MIN_HOLE_SIZE_IN = 0.028            # smallest cut feature: hole diameter or slot width
MIN_BRIDGE_SIZE_IN = 0.030          # smallest web left BETWEEN two cuts
MIN_HOLE_TO_EDGE_IN = 0.024         # smallest web left between a cut and a free part edge
# The laser's own DIMENSIONAL tolerance, +/- this on any cut dimension. NOT from the SKU row -- it is
# not in the specs JSON at all -- but from their published tolerances page, and it was already written
# out in three separate comments across this repo (gripper_right_claw's tip ramp, the closing-limit
# note in tom.params.js) before it was collected here. Anything that needs it should import it.
CUT_TOLERANCE_IN = 0.005

MM_PER_IN = 25.4
THICKNESS_MM = MM_PER_IN * THICKNESS_IN
EFFECTIVE_BEND_RADIUS_MM = MM_PER_IN * EFFECTIVE_BEND_RADIUS_IN
BEND_DEDUCTION_90_MM = MM_PER_IN * BEND_DEDUCTION_IN

MIN_HOLE_SIZE_MM = MM_PER_IN * MIN_HOLE_SIZE_IN                # 0.7112
MIN_BRIDGE_SIZE_MM = MM_PER_IN * MIN_BRIDGE_SIZE_IN            # 0.7620
MIN_HOLE_TO_EDGE_MM = MM_PER_IN * MIN_HOLE_TO_EDGE_IN          # 0.6096
CUT_TOLERANCE_MM = MM_PER_IN * CUT_TOLERANCE_IN                # 0.1270
MIN_CORNER_RELIEF_FROM_BEND_MM = MM_PER_IN * MIN_CORNER_RELIEF_FROM_BEND_IN   # 0.9398

# CONFLICT, recorded rather than resolved away. SendCutSend's human-readable Sheet Cutting
# Guidelines page gives the laser minimum hole/cutout as "at least 50% of material thickness",
# which is 1.0160 mm here -- LARGER than the 0.7112 in the SKU row above. The sendcutsend skill's
# own source precedence puts a SKU-keyed JSON field (rank 2) above a prose page (rank 5), so
# MIN_HOLE_SIZE_MM stays the spec value and this is the figure to actually design against.
MIN_HOLE_SIZE_CONSERVATIVE_MM = 0.5 * THICKNESS_MM             # 1.0160

# Minimum internal corner radius. NO numeric field exists in any of the three source documents:
# the guidelines page only says "approximately the kerf width (very small)" and the kerf FAQ gives
# the beam as roughly 0.006-0.010 in. This is the top of that range, so it is a floor to check
# against and never a target -- a corner that will see fatigue wants far more than a kerf.
MIN_INTERNAL_CORNER_RADIUS_MM = MM_PER_IN * 0.010              # 0.2540

# Half the die width, which is the rule that actually governs cuts near a bend: SendCutSend's
# bend-deformation guideline is that a cut feature must sit at least half a die width from the
# bend LINE (the centre of the bend), measured ON THE FLAT PATTERN, or it distorts when formed.
DIE_WIDTH_MM = MM_PER_IN * DIE_WIDTH_IN                        # 11.9888
HALF_DIE_WIDTH_MM = 0.5 * DIE_WIDTH_MM                         # 5.9944


def bend_allowance_90_mm(radius_mm: float, thickness_mm: float, k: float = K_FACTOR) -> float:
    """(pi/2)(r + k*t) -- the k-derived 90 degree allowance, which is the one this repo follows."""
    return (math.pi / 2.0) * (radius_mm + k * thickness_mm)


BEND_ALLOWANCE_90_MM = bend_allowance_90_mm(EFFECTIVE_BEND_RADIUS_MM, THICKNESS_MM)

# What the published deduction would have given, kept so the gap is visible rather than lost.
BEND_ALLOWANCE_90_FROM_DEDUCTION_MM = (
    2.0 * (EFFECTIVE_BEND_RADIUS_MM + THICKNESS_MM) - BEND_DEDUCTION_90_MM
)
ALLOWANCE_DISAGREEMENT_MM = abs(BEND_ALLOWANCE_90_MM - BEND_ALLOWANCE_90_FROM_DEDUCTION_MM)
