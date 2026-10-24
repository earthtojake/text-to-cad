"""Finish exposed wrist-step corners without moving connection datums.

The convex top of each wrist tab receives the common SMALL cut-profile
radius. Concave roots remain square: rounding them with a solid fillet
would add material in the agreed servo clearance, while a relief would
alter the servo-back datum or reduce the mounting-hole ligament.
"""
import build123d as b
from lib.corner_rules import SMALL
from lib.booleans import as_single_shape as one

WRIST_FLANGE_START_X = 1.727756700001
WRIST_STEP_TOP_Z = 135.005553389
WRIST_STEP_ROOT_Z = 132.100153389001
LINK_STOCK = 1.6


def finish_wrist_step_corners(p):
    """Round only the two free convex outline corners, in assembly coordinates."""
    r = SMALL
    assert 0 < r < WRIST_STEP_TOP_Z - WRIST_STEP_ROOT_Z, (
        'Wrist top-corner radius does not fit the free step', r)
    corners = [e for e in p.edges()
               if e.geom_type == b.GeomType.LINE
               and abs(e.length - LINK_STOCK) < 1e-4
               and abs(e.center().X - WRIST_FLANGE_START_X) < 1e-4
               and abs(e.center().Z - WRIST_STEP_TOP_Z) < 1e-4]
    assert len(corners) == 2, ('Expected two exposed wrist-step corners', len(corners))
    # These are thickness-spanning outline edges. The radius is in the
    # blank profile; no bevel/round is applied across the sheet thickness.
    q = one(p.fillet(r, corners)).clean()
    assert q.is_valid and len(q.solids()) == 1, 'Invalid wrist-step corner finish'
    q.label, q.color = p.label, p.color
    return q
