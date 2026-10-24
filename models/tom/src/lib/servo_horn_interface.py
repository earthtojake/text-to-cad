"""The servo horn interface -- the 5-hole pattern -- in ONE place.

Every bracket that bolts to a servo horn drills the same thing: four M3 clearance holes on a Ø14
circle plus a centre bore clearing the horn's own hub boss. Five holes, one pattern, and it was
written out in four files with THREE different centre bores:

    servo_horn_yoke              Ø6.5      (HORN_CENTER_CLEARANCE_RADIUS_MM = 3.25)
    shoulder_yaw_yoke            Ø6.496    (0.5 * 6.496, measured off servo_horn_yoke#o1.f8)
    shoulder_yaw_yoke_twin_bolt  Ø6.496    (the same literal again)
    servo_horn_yoke              Ø6.65     (a third, from the horn table's own measurement)

and the bolt circle written out twice. Same drift the k-factor had before sheet_rule_scs and the M2
clearance had before fastener_clearance. Import from here instead.

THE CENTRE OPENING IS Ø8.0 AS OF 2026-09-13. It clears the provisional Ø7 mm
Feetech horn-retainer head by 0.5 mm radially, as well as the horn hub boss.
The former Ø7 opening touched the new head. Both orientations of reusable
brackets use the same opening; mounting-hole axes and seating planes stay fixed.
Side-entry stem dimensions are independent of the opening, so changing screw
clearance does not move a claw bend or change its gripping geometry.

THE BOLTS stay M3 at medium clearance, from fastener_clearance -- these are screws, so their size is a
fit question and belongs there, not here.
"""

from __future__ import annotations

from lib import fastener_clearance as _fc

# Four M3 at 90 degrees on a Ø14 circle. Measured from the placed sts3215/sts3250 horn discs:
# (-32.5, 0), (-25.5, -7), (-25.5, +7), (-18.5, 0) about the axis at (-25.5, 0).
HORN_BOLT_CIRCLE_RADIUS_MM = 7.0
HORN_BOLT_COUNT = 4
HORN_BOLT_CLEARANCE_RADIUS_MM = _fc.M3_CLEARANCE_RADIUS_MM

# Hub and center-screw head clearance.
HORN_CENTER_CLEARANCE_DIAMETER_MM = 8.0
HORN_CENTER_CLEARANCE_RADIUS_MM = 0.5 * HORN_CENTER_CLEARANCE_DIAMETER_MM
# Original side-entry stem edge; a structural/claw datum, not head clearance.
HORN_SIDE_ENTRY_STEM_EDGE_MM = 3.5
