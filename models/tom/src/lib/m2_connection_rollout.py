"""Seat approved connection contours on existing mounting datums.

Only the local cut contour is replaced. Parent joins, bores, servo seats and
joint axes are fixed. Partial gripper lugs keep their existing coverage where
they meet a neighboring connection rather than growing unused extra lugs.
"""
import math
import build123d as b
from lib.booleans import as_single_shape as one
from lib.m2_connection_profiles import profile,END_HALF_WIDTH
from lib.short_gripper_trial import box
from lib.link_connection_finish import finish_wrist_step_corners
from lib.gripper_connection_finish import finish_gripper_connections
from lib.horn_relief_finish import finish_horn_junctions

# code, origin, along-row, sheet normal, extrusion sign, stock, coverage
LOWER=[
 ('A',(-30.475,15,83.8),(0,0,1),(0,1,0),1,1.6,'full'),
 ('B',(-30.475,-17,85.675),(0,0,1),(0,1,0),-1,1.6,'full'),
 ('C',(117.7522278937,15,83.0125766945),(0,0,1),(0,-1,0),-1,1.6,'full'),
 ('D',(114.0022278937,-17,83.0125766945),(0,0,1),(0,-1,0),1,1.6,'full')]
UPPER=[
 ('A',(129.2202278937,9.75,138.3875766945),(0,0,1),(-1,0,0),-1,1.6,'full'),
 ('A',(129.2202278937,-10.75,138.3875766945),(0,0,1),(1,0,0),1,1.6,'full'),
 ('C',(-4.3848199945,15.5,119.7375766945),(0,0,1),(0,1,0),1,1.6,'full'),
 ('D',(-.6348199945,-16.5,119.7375766945),(0,0,1),(0,1,0),-1,1.6,'full')]
GRIPPER=[
 ('A',(-107.835,1.875,102.6373766945),(0,-1,0),(0,0,1),1,1.6002,'negative'),
 ('A',(-128.335,1.875,102.6373766945),(0,-1,0),(0,0,-1),-1,1.6002,'positive'),
 ('B',(-107.835,0,136.2375766945),(0,-1,0),(0,0,1),1,1.6002,'full'),
 ('B',(-128.335,0,136.2375766945),(0,-1,0),(0,0,-1),-1,1.6002,'positive'),
 ('D',(-102.8598199945,0,136.2375766945),(0,1,0),(0,0,1),1,1.6002,'full'),
 ('C',(-99.1098199945,0,102.6373766945),(0,1,0),(0,0,1),1,1.6002,'positive')]


def replace_connection(p,spec,reference=None):
    code,origin,xdir,normal,sign,t,coverage=spec
    frame=b.Plane(origin=origin,x_dir=xdir,z_dir=normal).location
    old=p.moved(frame.inverse())
    seats=[f.center().Z for f in old.faces() if f.geom_type==b.GeomType.PLANE
           and abs(f.normal_at().Z)>.999 and abs(f.center().Z)<1e-4]
    assert seats,('Missing mounting seat',code,origin)
    offset=min(seats,key=abs)
    frame=frame*b.Pos(0,0,offset)
    # Finish junction rounds after the cropped coupon joins its parent.
    # Rounding a temporary crop can leave a clipped arc inside the parent.
    old=p.moved(frame.inverse());new=profile(code,t,round_horn=False)
    # Use its contour only: existing vendor-derived bore centers can differ
    # from rounded display dimensions by microns. Reuse the exact bores.
    f=max((f for f in new.faces() if f.geom_type==b.GeomType.PLANE and abs(f.normal_at().Z)>.999),key=lambda f:f.area)
    face=b.Face(f.outer_wire()).moved(b.Pos(0,0,-f.center().Z))
    new=b.Solid.extrude(face,(0,0,t))
    if sign<0:new=new.moved(b.Pos(0,0,-t))
    bb=new.bounding_box();xmin,xmax=bb.min.X,bb.max.X
    if coverage=='negative':xmax=0
    if coverage=='positive':xmin=0
    join={'A':4.,'B':4.,'C':8.,'D':2.}[code]
    roi=box((xmin,-10,bb.min.Z-.000001),(xmax,join,bb.max.Z+.000001))
    stock=one(new.intersect(roi))
    centers=set()
    bore_source=(reference if reference is not None else p).moved(frame.inverse())
    for e in bore_source.edges():
        if e.geom_type==b.GeomType.CIRCLE and abs(e.radius-1.1)<1e-5 and abs(e.length-2*math.pi*1.1)<1e-5:
            c=e.arc_center
            if bb.min.Z-1e-4<=c.Z<=bb.max.Z+1e-4:centers.add((round(c.X,8),round(c.Y,8)))
    if centers:stock=stock.cut(*[b.Solid.make_cylinder(1.1,t+.002,b.Plane(origin=(x,y,bb.min.Z-.001))) for x,y in centers])
    # Preserve all existing bores, including another connection's bores in
    # shared gripper stock. No partial mount acquires a new unused hole.
    q=one(one(old.cut(roi)).fuse(stock)).clean()
    if not q.is_valid:
        print('invalid fused result',code,origin,flush=True)
        q=q.fix()
    assert q.is_valid and len(q.solids())==1,(code,origin,'connection topology',q.is_valid,[(s.volume,str(s.bounding_box())) for s in q.solids()])
    q=q.moved(frame);q.label,q.color=p.label,p.color
    return q


def trim_upper_end_lands(p):
    """The wrist tabs start exactly at the common servo-back crossing plane."""
    for spec in UPPER[-2:]:
        code,origin,xdir,normal,sign,t,coverage=spec
        frame=b.Plane(origin=origin,x_dir=xdir,z_dir=normal).location
        q=p.moved(frame.inverse())
        z0,z1=(-t,0) if sign<0 else (0,t)
        # Opposing mounting rows differ by 3.75 mm; the servo-back datum
        # is shared in world space (X1.7277567).
        join=6.112576694501 if code=='C' else 2.362576694501
        tools=[box((END_HALF_WIDTH,-15,z0-.000001),(70,join,z1+.000001)),
               box((-70,-15,z0-.000001),(-END_HALF_WIDTH,join,z1+.000001))]
        q=one(q.cut(*tools)).clean()
        assert q.is_valid and len(q.solids())==1
        q=q.moved(frame);q.label,q.color=p.label,p.color;p=q
    return p


def revise_part(p,specs):
    reference=p
    for spec in specs:p=replace_connection(p,spec,reference)
    if specs is UPPER:
        p=finish_wrist_step_corners(trim_upper_end_lands(p))
    elif specs is GRIPPER:
        p=finish_gripper_connections(p,reference=reference)
    if specs is not GRIPPER:
        p=finish_horn_junctions(p)
    return p


