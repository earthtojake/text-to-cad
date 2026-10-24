"""Approved M2 case-pair contours, in a common hole-pair frame.

X follows the hole row; Y points into the parent bracket; Z is sheet normal.
The origin is the midpoint of the bores at the servo seating plane. Cosmetic
rounds use SMALL; the R11 horn relief and mounting pitches are functional.
"""
import build123d as b
from lib.corner_rules import SMALL
from lib.booleans import as_single_shape as one
from lib.servo_case_flange import case_flange

PITCH={'A':20.7,'B':24.45,'C':20.5,'D':20.5}
END_HALF_WIDTH=12.362576694501
END_RECESS_WIDTH=15.5
END_RECESS_DEPTH=6.75
END_TOE=2.65
FLAT_END_TOE=2.3
LOWER_ROOT_ADVANCE=1.014
# Supplier case end is drafted: its true extremum is beyond nominal X9.5.
# Use this same cap on A/B so a tab meets the fixed fold datum flush.
CASE_DRAFT_END_EXTENSION=0.112576694501
CASE_HORN_END_EXTENSION=0.5


def _finish_case_parent_join(p, thickness, *, round_horn=True):
    """Carry the R11 relief tangentially into the full case-end land.

    The legacy coupon stopped 0.5 mm short of that land. Reconstruct this
    shared end rather than retaining clipped pieces of its former R1 cap.
    """
    f=max((f for f in p.faces() if f.geom_type==b.GeomType.PLANE and abs(f.normal_at().Z)>.999),key=lambda f:f.area)
    arc=next(e for e in f.edges() if e.geom_type==b.GeomType.CIRCLE and abs(e.radius-11)<1e-5)
    c=arc.arc_center;bb=p.bounding_box();xmin=bb.min.X-CASE_HORN_END_EXTENSION
    band=b.Solid.make_box(CASE_HORN_END_EXTENSION+.01,bb.max.Y-bb.min.Y+2,thickness,
                         b.Plane(origin=(xmin,bb.min.Y-2,0)))
    p=one(one(p.fuse(band)).cut(b.Solid.make_cylinder(11,thickness+.002,
              b.Plane(origin=(c.X,c.Y,-.001))))).clean()
    corners=[e for e in p.edges() if e.geom_type==b.GeomType.LINE
             and abs(e.length-thickness)<1e-5 and abs(e.center().X-xmin)<1e-5
             and e.center().Y<bb.max.Y-1]
    assert len(corners)==1,('Case end corner',len(corners))
    p=one(p.fillet(SMALL,corners)).clean()
    assert p.is_valid and len(p.solids())==1
    from lib.horn_relief_finish import finish_horn_junctions
    return finish_horn_junctions(p) if round_horn else p


def profile(code, thickness=1.6, *, round_horn=True):
    """One approved contour, extruded +Z, with unchanged Ø2.2 mounting bores."""
    if code in ('A','B'):
        upper=code=='A'
        p=case_flange('upper' if upper else 'lower',-1,reversible=False,thickness_mm=thickness,
                      outer_extension_mm=CASE_DRAFT_END_EXTENSION)
        plane=b.Plane(origin=(-6.85 if upper else -4.975,6.4 if upper else -25.6,-10.25),
                      x_dir=(1,0,0),z_dir=(0,1,0))
        p=p.moved(plane.location.inverse())
        p=p.moved(b.Pos(0,0,-p.bounding_box().min.Z))
        if upper:return _finish_case_parent_join(p,thickness,round_horn=round_horn)
        # Normalize the old slightly asymmetric imported recess to the
        # approved symmetric R1 root, then advance it toward the case.
        w=9.5488;depth=2.014
        f=b.Face(b.Wire.make_polygon([(-w,-10,0),(w,-10,0),(w,depth,0),(-w,depth,0)],close=True))
        f=f.fillet_2d(SMALL,[v for v in f.vertices() if v.Y>0])
        p=one(p.cut(b.Solid.extrude(f,(0,0,thickness))))
        f=max((f for f in p.faces() if f.geom_type==b.GeomType.PLANE and abs(f.normal_at().Z)>.999),key=lambda f:f.area)
        def point(v):
            x,y=v.X,v.Y
            if abs(x)<=w+1e-5 and depth-SMALL-1e-5<=y<=depth+1e-5:y-=LOWER_ROOT_ADVANCE
            return (x,y,0)
        edges=[b.Edge.make_line(point(e@0),point(e@1)) if e.geom_type==b.GeomType.LINE
               else b.Edge.make_three_point_arc(point(e@0),point(e@.5),point(e@1)) for e in f.outer_wire().edges()]
        f=b.Face(b.Wire(edges),[w.moved(b.Pos(0,0,-f.center().Z)) for w in f.inner_wires()])
        return _finish_case_parent_join(b.Solid.extrude(f,(0,0,thickness)),thickness,round_horn=round_horn)
    edge=END_HALF_WIDTH
    if code=='C':
        h=END_RECESS_WIDTH/2
        pts=[(-edge,10),(-edge,-END_TOE),(-h,-END_TOE),(-h,END_RECESS_DEPTH),
             (h,END_RECESS_DEPTH),(h,-END_TOE),(edge,-END_TOE),(edge,10)]
    elif code=='D':pts=[(-edge,10),(-edge,-FLAT_END_TOE),(edge,-FLAT_END_TOE),(edge,10)]
    else:raise ValueError(code)
    f=b.Face(b.Wire.make_polygon([(x,y,0) for x,y in pts],close=True))
    f=f.fillet_2d(SMALL,[v for v in f.vertices() if v.Y<9.9])
    return one(b.Solid.extrude(f,(0,0,thickness)).cut(*[
        b.Solid.make_cylinder(1.1,thickness,b.Plane(origin=(x,0,0))) for x in (-PITCH[code]/2,PITCH[code]/2)]))
