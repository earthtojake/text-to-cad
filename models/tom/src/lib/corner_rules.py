"""House corner-radius standards for the tom brackets, in ONE place.

Every cosmetic corner radius in the arm resolves to one of these. They are NOT manufacturing
minimums -- SendCutSend's floors live in sheet_rule_scs.py and are checked separately -- and they are
NOT functional radii. Anything that has to match a part it mates with (the 10.000 horn cap disc, the
11.000 horn relief, the yoke cap at half its fold width) stays where it is and does not belong here.

WHY A MODULE. Before 2026-08-23 these were nine values written out across a dozen generators, and
they had drifted: the same kind of folded-cheek corner was 0.8 on shoulder_yaw_yoke and 1.0 on
shoulder_yaw_top_bracket, two brackets that bolt to the same servos. Import from here instead.

  OUTLINE_CORNER_R_MM     free corners on the blank's outline, and formed flange tabs
  INTERIOR_CORNER_R_MM    interior cuts -- lightening slots, windows, vertex fillets, cut ends
  BASE_CLAMP_CORNER_R_MM  the desk clamp only, which is a different material and stays coarser

A NOTE ON WHAT WAS GIVEN UP. INTERIOR_CORNER_R_MM was SHEET_THICKNESS_MM (2.0320) at the wall slots
and the collar window -- a rule that read "one gauge", so the corner tracked the material. Pinning it
to a round 2.0 severs that link: a gauge change will no longer carry these corners. That was the
owner's call on 2026-08-23 for a consistent, editable set; restore the tie by setting
INTERIOR_CORNER_R_MM = scs.THICKNESS_MM if it is ever wanted back.
"""

from __future__ import annotations

# Approved palette, 2026-10-10. These are cut-profile radii, not bend,
# bore, horn or tool-clearance radii. Never fillet sheet-thickness edges.
SMALL = 1.0    # Compact lugs/recesses and truss apertures.
MEDIUM = 2.0   # Gripper windows, noses and exposed diagonal knees.
LARGE = 3.0    # Base/clamp free perimeter.
XL = 4.0       # Broad concave link transitions.
XXL = 20.0     # Approved shallow diagonal-to-flat link transitions.

# Compatibility names used by the existing parametric factories.
OUTLINE_CORNER_R_MM = SMALL
INTERIOR_CORNER_R_MM = MEDIUM
BASE_CLAMP_CORNER_R_MM = LARGE

# Explicit exceptions: locked yoke neck R0.6 and functional horn/bend
# geometry remain unchanged. Bend ends and seating datums stay square.
# Clearance-root rounds must enlarge the removed envelope, never fill it.
# A radius that cannot fit must fail visibly; no automatic shrink/skip.
# R11 horn-clearance arcs meeting straight cut edges use SMALL tangent
# blends through the sheet gauge. Preserve the entire horn keep-out;
# the R1 blend removes stock rather than filling the clearance.
