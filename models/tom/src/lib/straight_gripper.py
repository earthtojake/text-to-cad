"""Straight fixed finger and lighter moving finger for the 600 mm arm.

Align the gripping bend with the fork cap tips; match the fixed cheek width.
Use the far three horn holes. Preserve
stock, bends and the 60 mm moving contact face, then solve the closed angle
against the straight fixed finger. The fixed finger is trimmed to that tip.
"""
from __future__ import annotations
import math
import build123d as b
from lib.booleans import as_single_shape as one
from lib.short_gripper_trial import datums,box,convex_outline
from lib.horn_cap import apply_horn_fork,CIRCULAR_HORN_FORK_PATTERN
T=2.032
# Bend tangent and rounded fork tips share the same across-jaw datum.
CHEEK_WIDTH=(CIRCULAR_HORN_FORK_PATTERN.outer_radius_mm
             +CIRCULAR_HORN_FORK_PATTERN.tip_extension_mm)
HORN_PATTERN_TURN=-90.0
AXIS_XY=(-126.59733008350791,20.525)
# Continuation of the fixed servo-header edge (o1.20.e136 in the source review).
FIXED_BEND_TANGENT_Y=-9.5488

def make_straight_gripper(fixed,moving):
    """Input world parts; return fixed, moving, horn phase change in degrees."""
    _,ftip,froot,fd,_=datums(fixed,False)
    _,mtip,mroot,md,_=datums(moving,True)
    # Move the whole formed finger, not just its outline, so the bend follows
    # the straight servo-header edge. Retain the case mounting header in place.
    turn=-math.degrees(math.atan2(fd.Y,fd.X))
    front=one(fixed.intersect(box((-500,-200,0),(froot.X+2.5,200,300))))
    back=one(fixed.intersect(box((froot.X+1.5,-200,0),(200,200,300))))
    front=front.rotate(b.Axis(froot,(0,0,1)),turn)
    z0=front.bounding_box().min.Z
    flat_edges=[e for fa in front.faces() if fa.geom_type==b.GeomType.PLANE
                and abs(fa.center().Z-z0)<1e-5 and abs(fa.normal_at().Z)>.999
                for e in fa.outer_wire().edges() if e.geom_type==b.GeomType.LINE
                and e.length>30 and abs((e@0).Y-(e@1).Y)<1e-6
                and (e@0).Y<froot.Y]
    old_fold=max((e@0).Y for e in flat_edges)
    fixed_shift=FIXED_BEND_TANGENT_Y-old_fold
    front=front.moved(b.Pos(0,fixed_shift,0))
    original_angle=math.degrees(math.atan2(md.Y,md.X))
    cx,cy=AXIS_XY;axis=b.Axis((cx,cy,0),(0,0,1))
    m=moving.rotate(axis,-original_angle)
    bb=m.bounding_box();core=m
    for z,dz in ((bb.min.Z,T),(bb.max.Z,-T)):
        face=max((f for f in m.faces() if f.geom_type==b.GeomType.PLANE
                  and abs(f.center().Z-z)<1e-5 and abs(f.normal_at().Z)>.999),key=lambda f:f.area)
        core=one(core.cut(b.Solid.extrude(face,(0,0,dz))))
    tangent=[v.center() for v in core.vertices() if abs(v.center().Z-bb.max.Z)<1e-5]
    nose=min(v.X for v in tangent);root=max(v.X for v in tangent)
    fold_y=sum(v.Y for v in tangent)/len(tangent)
    assert max(abs(v.Y-fold_y) for v in tangent)<1e-5
    r=CIRCULAR_HORN_FORK_PATTERN.outer_radius_mm;outer_y=cy+r
    reduction=outer_y-CHEEK_WIDTH-fold_y
    core=core.moved(b.Pos(0,reduction,0));fold_y+=reduction
    pieces=[core]
    for z in (bb.min.Z,bb.max.Z-T):
        cap_y=fold_y+5.8
        knee=(nose+outer_y-cap_y,outer_y)
        pts=[(nose,fold_y),(root,fold_y),(cx,fold_y),(cx,outer_y),knee,(nose,cap_y)]
        face=b.Face(b.Wire.make_polygon([(x,y,z) for x,y in pts],close=True))
        face=face.fillet_2d(1.0,[v for v in face.vertices() if (abs(v.center().X-nose)<1e-5 and v.center().Y>fold_y+.01) or (v.center()-b.Vector(*knee,z)).length<1e-5])
        cheek=one(b.Solid.extrude(face,(0,0,T)).fuse(b.Solid.make_cylinder(r,T,b.Plane(origin=(cx,cy,z)))))
        cheek=apply_horn_fork(cheek,center=(cx,cy,z+T/2),across=(1,0,0),outboard=(0,-1,0),normal=(0,0,1),thickness_mm=T,half_width_mm=r,pattern=CIRCULAR_HORN_FORK_PATTERN)
        # Continue the straight cheek to the near lug's bottom tangent.
        # The generic fork cutter otherwise leaves a 4.5 mm-deep notch
        # between its bounded cut and the circular cap on this side.
        _,cap_c,_,_,_=CIRCULAR_HORN_FORK_PATTERN.cap_geometry
        bridge=box((cx-r-2.0,fold_y,z),(cx-cap_c,cy,z+T))
        cheek=one(cheek.fuse(bridge))
        for u,v,hr in CIRCULAR_HORN_FORK_PATTERN.holes:
            cheek=one(cheek.cut(b.Solid.make_cylinder(hr,T+.02,
                b.Plane(origin=(cx+u,cy-v,z-.01)))))
        pieces.append(cheek)
    m=one(core.fuse(*pieces[1:])).clean()
    # Solve closed position on the unchanged servo axis, rather than stretching
    # the horn or translating its holes. Rephase the associated horn hardware.
    a=math.radians(-original_angle)
    vx,vy=mtip.X-cx,mtip.Y-cy
    tip=b.Vector(cx+vx*math.cos(a)-vy*math.sin(a),cy+vx*math.sin(a)+vy*math.cos(a)+reduction,mtip.Z)
    v=tip-b.Vector(cx,cy,tip.Z);radius=math.hypot(v.X,v.Y);dy=froot.Y+fixed_shift-cy
    dx=-math.sqrt(radius*radius-dy*dy)
    angle=math.degrees(math.atan2(dy,dx)-math.atan2(v.Y,v.X))
    angle=(angle+180)%360-180
    m=m.rotate(axis,angle)
    new_tip_x=cx+dx
    # Rotate the fixed channel to lie straight along X and retain its mounting
    # header. Splice the small length correction through a constant section.
    removal=new_tip_x-(froot.X-60)
    station=froot.X-25
    a=one(front.intersect(box((-500,-200,0),(station,200,300)))).moved(b.Pos(removal,0,0))
    c=one(front.intersect(box((station+removal,-200,0),(200,200,300))))
    front=one(a.fuse(c)).clean()
    fills=[]
    for z,dz in ((front.bounding_box().min.Z,T),(front.bounding_box().max.Z,-T)):
        fs=[f for f in front.faces() if f.geom_type==b.GeomType.PLANE and abs(f.normal_at().Z)>.999 and abs(f.center().Z-z)<1e-5]
        xy=[(v.center().X,v.center().Y) for f in fs for v in f.vertices()]
        fills.append(b.Solid.extrude(b.Face(b.Wire.make_polygon([(x,y,z) for x,y in convex_outline(xy)],close=True)),(0,0,dz)))
    f=one(front.fuse(back,*fills)).clean()
    # Match the fixed finger's cheek width, retaining the mounting header.
    # Limit the trims to the two planar cheek sheets so the formed gripping
    # face and quarter bends keep their original stock and radii.
    fold=FIXED_BEND_TANGENT_Y
    outer=fold-CHEEK_WIDTH
    flat_faces=[fa for fa in f.faces() if fa.geom_type==b.GeomType.PLANE
                and abs(fa.normal_at().Z)>.999 and fa.area>100]
    nose=min(v.center().X for fa in flat_faces for v in fa.vertices())
    cap=fold-5.8
    knee=nose+CHEEK_WIDTH-5.8
    # Continue the constant outside edge through the old diagonal header spur.
    return_x=froot.X+24.0
    cut_poly=[(-500,-200),(return_x+50,-200),(return_x+50,outer),(knee,outer),(nose,cap),(-500,cap)]
    for z in (front.bounding_box().min.Z,front.bounding_box().max.Z-T):
        cutter=b.Solid.extrude(b.Face(b.Wire.make_polygon(
            [(x,y,z-.001) for x,y in cut_poly],close=True)),(0,0,T+.002))
        # Trim the leftover sloping strip beside the gripping bend to the
        # same straight header datum, on both cheek sheets.
        inner=box((froot.X,fold,z-.001),(froot.X+10,fold+5,z+T+.001))
        f=one(f.cut(cutter,inner)).clean()
    from lib.gripper_063 import reform,THICKNESS
    f,camera=reform(f,False)
    m,_=reform(m,True)
    f=lighten_contact_face(f,False,thickness=THICKNESS)
    m=lighten_contact_face(m,True,thickness=THICKNESS)
    for p,old in ((f,fixed),(m,moving)):
        assert p.is_valid and len(p.solids())==1,(old.label,p.is_valid,len(p.solids()))
        p.label=old.label;p.color=old.color
    return f,m,angle-original_angle,camera


CONTACT_WINDOW_HEIGHT_MM=16.0
CONTACT_WINDOW_NOSE_LAND_MM=24.0
CONTACT_WINDOW_ROOT_LAND_MM=10.0
CONTACT_WINDOW_RADIUS_MM=1.0
ATTACHMENT_HOLE_DIAMETER_MM=3.2
ATTACHMENT_ROOT_INSET_MM=4.8
ATTACHMENT_PAIR_PITCH_MM=20.0

def lighten_contact_face(part,moving,*,thickness=T,aligned_pattern=False):
    """Rounded rectangular/triangular web windows and three M3 accessory holes."""
    _,tip,root,direction,_=datums(part,moving)
    angle=math.degrees(math.atan2(direction.Y,direction.X))
    axis=b.Axis((*AXIS_XY,0),(0,0,1))
    q=part.rotate(axis,-angle)
    face,tip,root,_,_=datums(q,moving)
    x0=tip.X+CONTACT_WINDOW_NOSE_LAND_MM+(4 if aligned_pattern else 0)
    x1=root.X-CONTACT_WINDOW_ROOT_LAND_MM
    z0=tip.Z-CONTACT_WINDOW_HEIGHT_MM/2
    z1=tip.Z+CONTACT_WINDOW_HEIGHT_MM/2
    points=[(x0,z0),(x1,z0),(x1,z1),(x0,z1)]
    normal_y=face.normal_at().Y
    wire=b.Wire.make_polygon([(x,tip.Y+normal_y*.01,z) for x,z in points],close=True)
    opening=b.Face(wire)
    opening=opening.fillet_2d(2.0 if aligned_pattern else CONTACT_WINDOW_RADIUS_MM,opening.vertices())
    cutters=[b.Solid.extrude(opening,(0,-normal_y*(thickness+.02),0))]
    triangle=b.Face(b.Wire.make_polygon([
        (tip.X+10,tip.Y+normal_y*.01,tip.Z),
        (tip.X+19,tip.Y+normal_y*.01,tip.Z-9),
        (tip.X+19,tip.Y+normal_y*.01,tip.Z+9)],close=True))
    triangle=triangle.fillet_2d(CONTACT_WINDOW_RADIUS_MM,triangle.vertices())
    cutters.append(b.Solid.extrude(triangle,(0,-normal_y*(thickness+.02),0)))
    centers=[(tip.X+5,tip.Z),
             (root.X-ATTACHMENT_ROOT_INSET_MM,tip.Z-ATTACHMENT_PAIR_PITCH_MM/2),
             (root.X-ATTACHMENT_ROOT_INSET_MM,tip.Z+ATTACHMENT_PAIR_PITCH_MM/2)]
    if aligned_pattern:
        # Four centres align with the ends of the window's straight side edges.
        centers=[(tip.X+5,tip.Z)]+[(x,z) for x in (x0-4,root.X-ATTACHMENT_ROOT_INSET_MM)
                                      for z in (z0+2,z1-2)]
    for x,z in centers:
        cutters.append(b.Solid.make_cylinder(ATTACHMENT_HOLE_DIAMETER_MM/2,thickness+.02,
            b.Plane(origin=(x,tip.Y+normal_y*.01,z),z_dir=(0,-normal_y,0))))
    result=one(q.cut(*cutters)).clean().rotate(axis,angle)
    assert result.is_valid and len(result.solids())==1
    return result
