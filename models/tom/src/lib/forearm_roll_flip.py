"""Reverse the roll case on its unchanged pair of horn seating planes.

The standard yoke and all joint datums are fixed. Only the servo, its case
fasteners, the centre horn fastener, and the upper link's return change.
"""
import build123d as b
from lib.booleans import as_single_shape as one
from lib.short_gripper_trial import box
from lib.sheet_rule_scs_063 import EFFECTIVE_BEND_RADIUS_MM

SEAT_X=(128.45222789367,165.05222789367)
CENTRE_X=sum(SEAT_X)/2
CENTRE_Y=-0.5
CASE_SCREWS={f'elbow_roll_link_plate_pair__hex_socket_m2x6__{i:02}' for i in (1,2,7,8)}


def placement():
    return b.Pos(CENTRE_X,CENTRE_Y,0)*b.Rot(Z=180)*b.Pos(-CENTRE_X,-CENTRE_Y,0)


def flipped_leaf(label):
    return (label.startswith('elbow_roll_servo_detail_') or label in CASE_SCREWS
            or label=='elbow_roll__hex_socket_m3x6__center')


def extend_return(part,thickness=1.6,*,toe_clearance=0.0):
    """Carry the straight side walls to the flipped case mounting surface.

    Reuse the approved complete return, including its bend radii and hole
    profiles. Its Y reflection exchanges the flat and raised-wall clearances
    in exactly the same way as the reversed case.
    """
    bb=part.bounding_box();outer=bb.max.X
    tangent=outer-thickness-EFFECTIVE_BEND_RADIUS_MM
    shift=sum(SEAT_X)-2*outer+thickness
    return_part=one(part.intersect(box((tangent,-50,0),(outer+1,50,300))))
    kept=one(part.intersect(box((-500,-50,0),(tangent,50,300))))
    return_part=return_part.mirror(b.Plane(origin=(0,CENTRE_Y,0),z_dir=(0,1,0)))
    return_part=b.Compound.cast(return_part.wrapped.Moved(b.Pos(shift,0,0).wrapped))
    # The two straight connection toes, not a guessed servo envelope, define
    # the bottom of the extension. Top height and the long diagonal stay fixed.
    zmin=return_part.bounding_box().min.Z
    bridges=[box((tangent,y,zmin),(tangent+shift,y+thickness,bb.max.Z))
             for y in (bb.min.Y,bb.max.Y-thickness)]
    q=one(kept.fuse(return_part,*bridges)).clean()
    if toe_clearance:
        # One axial end plane for the side cheeks, bend sectors and wrapped
        # mounting lands. Do not leave a separate raised strip on the cheeks.
        floors=[f for f in part.faces() if f.geom_type==b.GeomType.PLANE
                and abs(f.normal_at().Z)>.999 and f.area>1000]
        toe_start=max(floors,key=lambda f:f.area).bounding_box().max.X
        level=zmin+toe_clearance
        q=one(q.cut(box((toe_start,-50,-500),(outer+shift+1,50,level)))).clean()
        from lib.corner_rules import SMALL
        corners=[]
        for e in q.edges():
            if e.geom_type!=b.GeomType.LINE or abs(e.length-thickness)>1e-5:continue
            c=e.center();size=e.bounding_box().size
            if abs(c.Z-level)>1e-5:continue
            # Exposed cheek root and the two free return tips; the bend seams
            # stay square through the sheet thickness, as in our cut standard.
            if (abs(c.X-toe_start)<1e-5 and abs(size.Y-thickness)<1e-5
                or abs(size.X-thickness)<1e-5 and abs(c.Y-CENTRE_Y)<14):
                corners.append(e)
        if corners:q=q.fillet(SMALL,corners).clean()
    q.label,q.color=part.label,part.color
    assert q.is_valid and len(q.solids())==1
    return q
