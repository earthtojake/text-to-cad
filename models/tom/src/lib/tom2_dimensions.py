"""Shared link height derived from the ALU-080 forming envelope."""
from lib import sheet_rule_scs as sheet

# Lightening/access openings are suppressed for the bend-only layout study.
# Mounting bores stay on the servo pattern. The closest 2.2 mm bore is
# 32.75 mm above the shoulder axis; place its edge just outside half the die.
MIN_FORMED_FLANGE_MM = sheet.MIN_FLANGE_AFTER_BEND_IN * sheet.MM_PER_IN
ROOT_MOUNT_HOLE_Z_MM = 32.75
ROOT_MOUNT_HOLE_RADIUS_MM = 1.1
ROOT_FREE_EDGE_Z_MM = ROOT_MOUNT_HOLE_Z_MM - 2.65
MOUNT_TO_ROOF_MM = (ROOT_MOUNT_HOLE_RADIUS_MM + sheet.HALF_DIE_WIDTH_MM
                   - sheet.BEND_ALLOWANCE_90_MM/2
                   + sheet.EFFECTIVE_BEND_RADIUS_MM + sheet.THICKNESS_MM)
LINK_ROOF_HEIGHT_MM = max(ROOT_MOUNT_HOLE_Z_MM + MOUNT_TO_ROOF_MM,
                          ROOT_FREE_EDGE_Z_MM + MIN_FORMED_FLANGE_MM)
LINK_HEIGHT_REDUCTION_MM = 45.0 - LINK_ROOF_HEIGHT_MM

# Shorten both shared U collars without changing horn-axis positions or width.
COLLAR_SHORTEN_MM = 0.9
