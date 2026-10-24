"""Reusable reversible ST3215/STS3250 case-flange outlines, in servo coordinates.

The exact line/arc profiles come from the fitted, frozen base/gripper frame
(o1.2), normalized to the vendor servo. All values are millimeters. Each
outline is on the negative-Z case edge; z_sign mirrors it to the other edge.
Arc records contain start, midpoint and end, preserving true circular cuts.
The paired R11 horn reliefs and existing corner shapes are shared by users
of this pattern. Mounting bores derive from servo_fit and fastener_clearance.
"""
import math
import build123d as bd
from lib import servo_fit as fit, fastener_clearance as fc, sheet_rule_scs as scs
from lib import corner_rules as cr

CASE_MIRROR_X_MM = sum(fit.SERVO.case_lower_hole_x_mm)/2
FIXED_FLANGE_X_BOUNDS_MM = (-19.5, 9.5)
REVERSIBLE_FLANGE_HALF_WIDTH_MM = 14.6828
HORN_CLEARANCE_RADIUS_MM = 11.0
CASE_UPPER_INNER_EDGE_MM = -7.672
CASE_LOWER_INNER_EDGE_MM = -7.208
CASE_BACK_EDGE_MM = -18.5058
CASE_LOWER_RECESS_DEPTH_MM = -11.264
CASE_LOWER_RECESS_HALF_WIDTH_MM = 9.5488


def _make_case_outline(side, *, reversible=False, outer_extension_mm=0.0):
    """One case interface: actual horn relief, optionally mirrored for reuse.

    The reversible frame has a horn relief at both ends and unioned bores.
    Fixed link/claw mounts replace the unused relief with an ordinary corner.
    Their mounting depth, central recess and real horn relief are shared.
    """
    if side not in ('upper','lower'): raise ValueError(side)
    if reversible and outer_extension_mm: raise ValueError(outer_extension_mm)
    if reversible:
        xmin,xmax = (CASE_MIRROR_X_MM-REVERSIBLE_FLANGE_HALF_WIDTH_MM,
                     CASE_MIRROR_X_MM+REVERSIBLE_FLANGE_HALF_WIDTH_MM)
    else:
        xmin,xmax = FIXED_FLANGE_X_BOUNDS_MM
        xmax += outer_extension_mm
    r=cr.OUTLINE_CORNER_R_MM; q=math.sqrt(.5)
    inner=CASE_UPPER_INNER_EDGE_MM if side=='upper' else CASE_LOWER_INNER_EDGE_MM
    hx=fit.SERVO.horn_axis_x_mm; hr=HORN_CLEARANCE_RADIUS_MM
    join=(hx+math.sqrt(hr*hr-inner*inner),inner)
    left=(xmin,-math.sqrt(hr*hr-(xmin-hx)**2))
    a0,a1=math.atan2(join[1],join[0]-hx),math.atan2(left[1],left[0]-hx)
    mid=(hx+hr*math.cos((a0+a1)/2),hr*math.sin((a0+a1)/2))
    edges=[('line',(xmin,CASE_BACK_EDGE_MM),(xmax,CASE_BACK_EDGE_MM))]
    if reversible:
        def mirror(p): return (2*CASE_MIRROR_X_MM-p[0],p[1])
        edges.extend((('line',(xmax,CASE_BACK_EDGE_MM),mirror(left)),
                      ('arc',mirror(left),mirror(mid),mirror(join))))
        right_join=mirror(join)
    else:
        right_join=(xmax-r,inner)
        edges.extend((('line',(xmax,CASE_BACK_EDGE_MM),(xmax,inner-r)),
            ('arc',(xmax,inner-r),(xmax-r+r*q,inner-r+r*q),right_join)))
    if side=='upper':
        edges.append(('line',right_join,join))
    else:
        xl=CASE_MIRROR_X_MM-CASE_LOWER_RECESS_HALF_WIDTH_MM
        xr=CASE_MIRROR_X_MM+CASE_LOWER_RECESS_HALF_WIDTH_MM
        # Deepen the root by R before rounding; retain the complete old
        # rectangular case clearance rather than filling its corners.
        depth=CASE_LOWER_RECESS_DEPTH_MM-r
        edges.extend((('line',right_join,(xr+r,inner)),
            ('arc',(xr+r,inner),(xr+r-r*q,inner-r+r*q),(xr,inner-r)),
            ('line',(xr,inner-r),(xr,depth+r)),
            ('arc',(xr,depth+r),(xr-r+r*q,depth+r-r*q),(xr-r,depth)),
            ('line',(xr-r,depth),(xl+r,depth)),
            ('arc',(xl+r,depth),(xl+r-r*q,depth+r-r*q),(xl,depth+r)),
            ('line',(xl,depth+r),(xl,inner-r)),
            ('arc',(xl,inner-r),(xl-r+r*q,inner-r+r*q),(xl-r,inner)),
            ('line',(xl-r,inner),join)))
    return (*edges,('arc',join,mid,left),('line',left,(xmin,CASE_BACK_EDGE_MM)))


CASE_UPPER_OUTLINE = _make_case_outline('upper',reversible=True)
CASE_LOWER_OUTLINE = _make_case_outline('lower',reversible=True)


def fixed_case_outline(side, *, outer_extension_mm=0.0):
    if outer_extension_mm < 0: raise ValueError(outer_extension_mm)
    return _make_case_outline(side,outer_extension_mm=outer_extension_mm)


def case_hole_centers(side, z_sign=-1, *, reversible=True):
    """Union of original and end-for-end pairs as vendor-frame XYZ points."""
    if side not in ('upper','lower'):raise ValueError(side)
    y=fit.SERVO.case_upper_y_mm if side=='upper' else fit.SERVO.case_lower_y_mm
    xs=fit.SERVO.case_upper_hole_x_mm if side=='upper' else fit.SERVO.case_lower_hole_x_mm
    selected=sorted(set(round(x,9) for x0 in xs
        for x in ((x0,2*CASE_MIRROR_X_MM-x0) if reversible else (x0,))))
    return tuple((x,y,z_sign*fit.SERVO.case_hole_z_mm) for x in selected)


def case_flange(side, z_sign=-1, *, reversible=True, thickness_mm=scs.THICKNESS_MM,
                outer_extension_mm=0.0):
    """One constant-gauge flange extending outward from its case seat."""
    if side not in ('upper','lower') or z_sign not in (-1,1):raise ValueError((side,z_sign))
    y=fit.SERVO.case_upper_y_mm if side=='upper' else fit.SERVO.case_lower_y_mm
    if reversible and outer_extension_mm:raise ValueError('Outer extension requires a fixed case flange')
    outline=(CASE_UPPER_OUTLINE if side=='upper' else CASE_LOWER_OUTLINE) if reversible else fixed_case_outline(side, outer_extension_mm=outer_extension_mm)
    def point(p):return (p[0],y,-z_sign*p[1])
    edges=[]
    for kind,*coords in outline:
        pts=[point(p) for p in coords]
        edges.append(bd.Edge.make_line(*pts) if kind=='line' else bd.Edge.make_three_point_arc(*pts))
    bores=[bd.Wire.make_circle(fc.M2_CLEARANCE_RADIUS_MM,
                bd.Plane(origin=p,x_dir=(1,0,0),z_dir=(0,1,0)))
           for p in case_hole_centers(side,z_sign,reversible=reversible)]
    face=bd.Face(bd.Wire(edges),bores)
    if thickness_mm <= 0:raise ValueError(thickness_mm)
    return bd.Solid.extrude(face,(0,thickness_mm*(1 if side=='upper' else -1),0))
