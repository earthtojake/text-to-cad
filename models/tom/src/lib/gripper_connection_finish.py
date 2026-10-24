"""Continuous parent lands around the fixed gripper's approved M2 coupons.

Call once after ``revise_part(original, GRIPPER)``. All work is confined to
horizontal sheet outlines; mounting planes, servo seats and camera bends stay
fixed. Coupon crop boundaries are not intended finished part boundaries.
"""
import build123d as b
from lib.booleans import as_single_shape as one
from lib.short_gripper_trial import box
from lib.corner_rules import SMALL
from lib.m2_connection_profiles import FLAT_END_TOE
import math

T=1.6002
LOWER=102.6373766945
UPPER=136.2375766945


def _at_corner(p,x,y,z,r=SMALL):
    edges=[e for e in p.edges() if e.geom_type==b.GeomType.LINE
           and abs(e.length-T)<1e-4 and abs(e.center().X-x)<1e-4
           and abs(e.center().Y-y)<1e-4 and abs(e.center().Z-(z+T/2))<1e-4]
    assert len(edges)==1,('Gripper free corner',x,y,z,len(edges))
    return one(p.fillet(r,edges)).clean()


def finish_gripper_connections(p, reference=None):
    original=p
    reference=p if reference is None else reference
    bore_cutters=[];seen=set()
    for e in reference.edges():
        if e.geom_type!=b.GeomType.CIRCLE or abs(e.radius-1.1)>1e-5:continue
        c=e.arc_center
        if e.bounding_box().size.Z>1e-4:continue
        if not any(abs(c.Z-z)<1e-4 or abs(c.Z-z-T)<1e-4 for z in (LOWER,UPPER)):continue
        z=min((LOWER,UPPER),key=lambda z:abs(c.Z-z-T/2))
        key=(round(c.X,6),round(c.Y,6),z)
        if key in seen:continue
        seen.add(key)
        bore_cutters.append(b.Solid.make_cylinder(e.radius,T+.02,b.Plane(origin=(c.X,c.Y,z-.01))))
    def fill(x0,x1,y0,y1,z):
        nonlocal p
        stock=box((x0,y0,z),(x1,y1,z+T))
        for bore in bore_cutters:stock=one(stock.cut(bore))
        p=one(p.fuse(stock)).clean()
    def cut(x0,x1,y0,y1,z):
        nonlocal p
        p=one(p.cut(box((x0,y0,z-.00001),(x1,y1,z+T+.00001)))).clean()

    # Uninterrupted parent rails replace the cropped coupons' isolated tongue
    # and slightly different cap levels. The inner recess limits are fixed.
    for z,xl,xr,xe,floor in [
        # The negative-Y jaw-case end is the flat side. Its straight land
        # uses the D connection's 2.3 mm toe from the screw row at Y=-12.225.
        (UPPER,-125.293,-110.877,-106.835,-12.225+FLAT_END_TOE),
        (LOWER,-125.757,-110.413,-110.40,-14.9752)]:
        # Fill from the former root as well when advancing the flat-side
        # land; otherwise the old recess would survive as an enclosed slot.
        # The flat side stops at its straight toe across the complete row;
        # carrying the recessed contour's extra root stock forward here
        # would overlap the drafted cap at the two ends.
        fill(-132.335,xe,min(floor,-14.587576694501)-.1,
             floor if z==UPPER else floor+3*SMALL,z)
        face=b.Face(b.Wire.make_polygon([(xl,floor,z-.00001),(xr,floor,z-.00001),
                                        (xr,3,z-.00001),(xl,3,z-.00001)],close=True))
        face=face.fillet_2d(SMALL,[v for v in face.vertices() if abs(v.Y-floor)<1e-5])
        p=one(p.cut(b.Solid.extrude(face,(0,0,T+.00002)))).clean()
    # Remove empty half-coupon stock; retain 2.65 mm from the lower lug bore.
    cut(-132.33501,-127.335,-9.5488,0.00001,UPPER)
    cut(-132.33501,-125.75699,-5.825,1.87501,LOWER)
    p=_at_corner(p,-125.757,-5.825,LOWER)
    p=_at_corner(p,-132.335,-5.825,LOWER)

    # The imported header used X=-110.4129733835 while the connection
    # profile uses -110.413. Continue the nominal wall through the entire
    # parent land; otherwise two 0.0000266 mm steps survive at the join.
    fill(-110.413,-110.40,-13.9752,12.642080743785,LOWER)

    # Merge the lower C toe into the adjacent A land. This removes a doubled
    # radius and backtracking 1 mm ledge without altering its inner clearance.
    fill(-103.835,-96.4598199945,11.35,15.025,LOWER)
    p=_at_corner(p,-96.4598199945,15.025,LOWER)

    # Reconstruct the full C recess from its shared dimensions. The former
    # half-coupon cleanup displaced its root by 1.0026 mm and retained an
    # unequal opposite side. Parent stock surrounds this one symmetric cut.
    from lib.m2_connection_profiles import END_RECESS_DEPTH, END_RECESS_WIDTH
    root=-99.1098199945-END_RECESS_DEPTH
    half=END_RECESS_WIDTH/2
    fill(-107.0,-96.4598199945,-half-1,half+1,LOWER)
    recess=b.Face(b.Wire.make_polygon([(root,-half,LOWER-.00001),
        (-94,-half,LOWER-.00001),(-94,half,LOWER-.00001),
        (root,half,LOWER-.00001)],close=True))
    recess=recess.fillet_2d(SMALL,[v for v in recess.vertices() if abs(v.X-root)<1e-5])
    p=one(p.cut(b.Solid.extrude(recess,(0,0,T+.00002)))).clean()
    # These are exposed ends of the C recess, not bend/seat datums.
    for y in (-half,half):
        p=_at_corner(p,-96.4598199945,y,LOWER)

    # Replace the camera-foot horn sector with one native planar contour.
    # This removes coincident old/new R11 fragments rather than healing them.
    arc=next(e for e in p.edges() if e.geom_type==b.GeomType.CIRCLE
             and abs(e.radius-11)<1e-5 and abs(e.arc_center.Z-UPPER)<1e-4)
    c=arc.arc_center
    fy=16-SMALL
    fx=c.X+math.sqrt((11+SMALL)**2-(fy-c.Y)**2)
    ax=-110.877;ay=c.Y-math.sqrt(121-(ax-c.X)**2)
    bx=c.X+11/(11+SMALL)*(fx-c.X)
    by=c.Y+11/(11+SMALL)*(fy-c.Y)
    def point(x,y):return b.Vector(x,y,UPPER)
    aa=math.atan2(ay-c.Y,ax-c.X);ab=math.atan2(by-c.Y,bx-c.X)
    mid=point(c.X+11*math.cos((aa+ab)/2),c.Y+11*math.sin((aa+ab)/2))
    a1=math.atan2(by-fy,bx-fx);a2=math.pi/2
    mid1=point(fx+SMALL*math.cos((a1+a2)/2),fy+SMALL*math.sin((a1+a2)/2))
    A=point(ax,ay);B=point(bx,by);C=point(fx,16)
    D=point(-95.2098199945,16);E=point(-95.2098199945,12.15);F=point(ax,12.15)
    wire=b.Wire([b.Edge.make_line(F,A),b.Edge.make_three_point_arc(A,mid,B),
                 b.Edge.make_three_point_arc(B,mid1,C),b.Edge.make_line(C,D),
                 b.Edge.make_line(D,E),b.Edge.make_line(E,F)])
    stock=b.Solid.extrude(b.Face(wire),(0,0,T))
    for bore in bore_cutters:stock=one(stock.cut(bore))
    p=one(p.cut(box((-111,12.15,UPPER-.00001),(-95.2098199945,16.1,UPPER+T+.00001))))
    p=one(p.fuse(stock)).clean()
    assert p.is_valid and len(p.solids())==1,'Camera-foot reconstruction failed'

    # The D coupon's toe is internal to the camera parent, not a free edge.
    # Reuse the native bent side profile for continuous side rails through the
    # first bend, while preserving the central servo clearance opening.
    from end_effector.servo6_gripper_concept import (
        CAMERA_RISER_HEADING_DEG, CAMERA_RISER_LENGTH_MM, CAMERA_PANEL_PITCH_DEG)
    from lib import camera_bends as bends
    from lib.gripper_063 import RADIUS as RI
    a0=math.pi;a1=math.radians(CAMERA_RISER_HEADING_DEG)
    a2=math.radians(90-CAMERA_PANEL_PITCH_DEG)
    rs=bends.bend_end((0,0,0),a0,a1,thickness=T,radius=RI)
    re=bends.add(rs,bends.direction(a1),CAMERA_RISER_LENGTH_MM)
    ps=bends.bend_end(re,a1,a2,thickness=T,radius=RI)
    mapping=b.Pos(-95.2098199945,0,UPPER+T)*b.Rot(Z=90)
    curved=bends.bend((0,0,0),a0,a1,32,thickness=T,radius=RI)
    riser=bends.straight(rs,CAMERA_RISER_LENGTH_MM,a1,32,thickness=T)
    parent_stock=one(curved.fuse(riser)).moved(mapping)
    parent_stock=one(parent_stock.fuse(box((-150,-16,UPPER),(-95.2098199945,16,UPPER+T)))).clean()
    roi=box((-101.5598199956,-16,UPPER-.00001),(-92.85,16,UPPER+T+.00001))
    # Remove flat coupon material protruding outside the true bend profile.
    p=one(p.cut(one(roi.cut(parent_stock)))).clean()
    def world(v):return (-95.2098199945-v[1],v[0],UPPER+T+v[2])
    land_roi=box((-101.5598199956,-16,UPPER-.01),(-92.8,16,140))
    region=land_roi
    stock=one(parent_stock.intersect(region))
    # The central opening must reach through this bend: the wrist servo's
    # raised cap occupies it. Only the two side rails are continuous here.
    stock=one(stock.cut(box((-100.5598199956,-10,UPPER-.02),(-92,10,140))))
    p=one(p.cut(region)).clean()
    for bore in bore_cutters:stock=one(stock.cut(bore))
    p=one(p.fuse(stock)).clean()
    assert p.is_valid and len(p.solids())==1,'Camera bend parent blend failed'

    # Remove tiny legacy tabs outside the camera panel's already-approved R2
    # outline. The mask follows the native panel plane and leaves its bend
    # tangent and all internal holes unchanged.
    panel=max((f for f in p.faces() if f.geom_type==b.GeomType.PLANE
               and f.center().Z>150 and f.area>900
               and f.normal_at().X*f.normal_at().Z>0),key=lambda f:f.area)
    n=panel.normal_at()
    panel_stock=b.Solid.extrude(b.Face(panel.outer_wire()),n*12).moved(b.Pos(-n*6))
    frame=b.Plane(origin=world(ps),x_dir=(0,1,0),
                  z_dir=(math.sin(a2),0,math.cos(a2)))
    below=box((-100,-200,-50),(100,0,50)).moved(frame.location)
    roi=box((-110,-22,world(ps)[2]-.93),(-65,22,p.bounding_box().max.Z+1))
    outside=one(roi.cut(panel_stock,below))
    p=one(p.cut(outside)).clean()
    if not p.is_valid:p=p.fix()
    p.label=original.label
    p.color=original.color
    assert p.is_valid and len(p.solids())==1,'Invalid gripper parent blend'
    return p
