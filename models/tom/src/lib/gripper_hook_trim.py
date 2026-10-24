"""Remove the user-marked lower mounting hook; retain the integrated camera.

The original one-piece sheet development overlapped at this unused rear hook.
The cut aligns with the existing opposite toe at Y=-5.825. Only the two newly
exposed free corners get the approved SMALL radius; mounting/camera/jaw datums
and all other outlines stay fixed.
"""
import build123d as b
from lib.booleans import as_single_shape as one
from lib.corner_rules import SMALL

LOWER_SHEET_Z = 102.6373766945
HOOK_START_X = -110.413
CUT_Y = -5.825
THICKNESS = 1.6002


def trim_gripper_hook(p):
    cutter=b.Solid.make_box(50,60,THICKNESS+.002,
        b.Plane(origin=(HOOK_START_X,CUT_Y,LOWER_SHEET_Z-.001)))
    q=one(p.cut(cutter)).clean()
    corners=[e for e in q.edges()if e.geom_type==b.GeomType.LINE
        and abs(e.length-THICKNESS)<1e-4
        and abs(e.center().Y-CUT_Y)<1e-5
        and abs(e.center().Z-LOWER_SHEET_Z-THICKNESS/2)<1e-4
        and e.center().X>=HOOK_START_X-1e-5]
    assert len(corners)==2,('Lower hook cut corners',len(corners))
    q=one(q.fillet(SMALL,corners)).clean()
    assert q.is_valid and len(q.solids())==1
    q.label=p.label;q.color=p.color
    return q
