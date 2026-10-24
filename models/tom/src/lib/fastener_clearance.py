"""Close-clearance sheet holes, explicitly requested for this revision.

These are bracket through-holes, never servo thread sizes. SCS's +/-0.127 mm
cut tolerance leaves 0.073 mm diametral clearance at the low limit. Bend-position
error is separate: locate/finish binding holes after forming in an alignment
fixture rather than forcing the sheet or changing servo axes.
"""
M2_CLEARANCE_DIAMETER_MM = 2.2
M2_5_CLEARANCE_DIAMETER_MM = 2.7
M3_CLEARANCE_DIAMETER_MM = 3.2
M2_CLEARANCE_RADIUS_MM = 0.5 * M2_CLEARANCE_DIAMETER_MM
M2_5_CLEARANCE_RADIUS_MM = 0.5 * M2_5_CLEARANCE_DIAMETER_MM
M3_CLEARANCE_RADIUS_MM = 0.5 * M3_CLEARANCE_DIAMETER_MM
