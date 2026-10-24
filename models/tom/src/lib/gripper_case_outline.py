"""Gripper-only case edges: retain the real horn relief, close its unused copy."""
import math
from lib.servo_case_flange import (
    CASE_UPPER_OUTLINE, CASE_LOWER_OUTLINE, CASE_BACK_EDGE_MM,
    CASE_UPPER_INNER_EDGE_MM, CASE_LOWER_INNER_EDGE_MM,
)
from lib.corner_rules import OUTLINE_CORNER_R_MM


def gripper_case_outline(side):
    """The flipped jaw servo has its horn at the positive end of the band.

    Replace only the negative-end R11 relief with the ordinary outer round.
    The case recess, occupied holes, width and real horn clearance stay fixed.
    """
    records = list(CASE_LOWER_OUTLINE if side == 'lower' else CASE_UPPER_OUTLINE)
    inner = CASE_LOWER_INNER_EDGE_MM if side == 'lower' else CASE_UPPER_INNER_EDGE_MM
    xmin = records[0][1][0]
    r = OUTLINE_CORNER_R_MM
    q = math.sqrt(.5)
    tangent = (xmin+r, inner)
    records[-3] = ('line', records[-3][1], tangent)
    records[-2] = ('arc', tangent, (xmin+r-r*q, inner-r+r*q), (xmin, inner-r))
    records[-1] = ('line', (xmin, inner-r), (xmin, CASE_BACK_EDGE_MM))
    return tuple(records)
