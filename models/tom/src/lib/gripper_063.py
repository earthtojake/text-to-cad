"""Re-form only Tom's gripper sheets in SCS ALU-063; retain mounting seats.

Use the source-built outlines as templates, not exported STEP. The contact
planes and terminal tips remain fixed. Bend radii and free sheet faces are
rebuilt for .063 inch 5052. Nose cuts are 45 degrees with 4 mm blunt ends.
"""
from __future__ import annotations
import math
import build123d as b
from lib.booleans import as_single_shape as one
from lib.short_gripper_trial import datums,box
from lib.corner_rules import OUTLINE_CORNER_R_MM

THICKNESS=1.6002
RADIUS=.889
TIP_WIDTH=4.0
BEND_NOSE_SETBACK_MM=6.0
OLD_THICKNESS=2.032
OLD_RADIUS=.9652

def reform(part,moving):
    _,tip,root,direction,_=datums(part,moving)
    angle=math.degrees(math.atan2(direction.Y,direction.X))
    axis=b.Axis((0,0,0),(0,0,1));q=part.rotate(axis,-angle)
    face,tip,root,_,_=datums(q,moving)
    horizontal=[f for f in q.faces() if f.geom_type==b.GeomType.PLANE
                and abs(f.normal_at().Z)>.99999 and f.area>500]
    zs=sorted(set(round(f.center().Z,8) for f in horizontal))
    assert len(zs)==4,(part.label,zs)
    lower,upper=zs[1],zs[2]
    new_lo,new_hi=lower+RADIUS,upper-RADIUS
    side=-1 if moving else 1
    # Web contact is the outside of the channel's quarter bends.
    fold=tip.Y-side*(RADIUS+THICKNESS)
    old_fold=tip.Y-side*(OLD_RADIUS+OLD_THICKNESS)
    nxlo=tip.X+(tip.Z-new_lo-TIP_WIDTH/2)
    nxhi=tip.X+(new_hi-tip.Z-TIP_WIDTH/2)
    points=[(tip.X,tip.Z-TIP_WIDTH/2),(nxlo,new_lo),(root.X,new_lo),
            (root.X,new_hi),(nxhi,new_hi),(tip.X,tip.Z+TIP_WIDTH/2)]
    profile=b.Face(b.Wire.make_polygon([(x,tip.Y,z) for x,z in points],close=True))
    profile=profile.fillet_2d(OUTLINE_CORNER_R_MM,
                            [v for v in profile.vertices() if abs(v.center().X-tip.X)<1e-6])
    web=b.Solid.extrude(profile,(0,-side*THICKNESS,0))
    pieces=[web];cheeks=[]
    for sign,z,nose in ((-1,lower,nxlo+BEND_NOSE_SETBACK_MM),
                        (1,upper,nxhi+BEND_NOSE_SETBACK_MM)):
        pf=max((f for f in horizontal if abs(f.center().Z-z)<1e-5),key=lambda f:f.area)
        cheek=b.Solid.extrude(pf,(0,0,sign*THICKNESS))
        # Translate the whole front cap so its diagonal and forming land
        # survive the longer pointed section. Mounting outline stays fixed.
        old_nose=min(v.center().X for v in pf.outer_wire().vertices())
        delta=nose-old_nose
        split=old_nose+12
        front=one(cheek.intersect(box((-500,-500,0),(split,500,400)))).moved(b.Pos(delta,0,0))
        back=one(cheek.intersect(box((split+delta-.01,-500,0),(500,500,400))))
        cheek=one(front.fuse(back)).clean()
        # The new bend tangent is displaced across the flat by the change
        # in outside radius. Extend the existing cheek to that tangent.
        fy0,fy1=sorted((fold,old_fold))
        zz0,zz1=sorted((z,z+sign*THICKNESS))
        strip=box((nose,fy0,zz0),(root.X,fy1,zz1))
        cheek=one(cheek.fuse(strip)).clean()
        cz=z-sign*RADIUS
        def pt(r,a):return(nose,fold+side*r*math.cos(a),cz+sign*r*math.sin(a))
        ri,ro=RADIUS,RADIUS+THICKNESS
        wi=b.Wire([b.Edge.make_three_point_arc(*[pt(ro,a) for a in (0,math.pi/4,math.pi/2)]),
                   b.Edge.make_line(pt(ro,math.pi/2),pt(ri,math.pi/2)),
                   b.Edge.make_three_point_arc(*[pt(ri,a) for a in (math.pi/2,math.pi/4,0)]),
                   b.Edge.make_line(pt(ri,0),pt(ro,0))])
        bend=b.Solid.extrude(b.Face(wi),(root.X-nose,0,0))
        pieces.extend((cheek,bend));cheeks.append(cheek)
    result=one(pieces[0].fuse(*pieces[1:])).clean()
    payload=None
    if not moving:
        from end_effector.servo6_gripper_concept import integrated_camera
        seats=[e.arc_center.X for e in cheeks[1].edges() if e.geom_type==b.GeomType.CIRCLE
               and abs(e.radius-1.1)<1e-5 and abs(abs(e.arc_center.Y)-10.25)<1e-5]
        assert seats
        result,payload=integrated_camera(result,cheeks[1],thickness_mm=THICKNESS,
                                        bend_radius_mm=RADIUS,seat_hole_x=max(seats),prepared_foot=True)
    result=result.rotate(axis,angle)
    if payload is not None:payload=payload.rotate(axis,angle)
    result.label=part.label;result.color=part.color
    assert result.is_valid and len(result.solids())==1,(part.label,len(result.solids()))
    return result,payload
