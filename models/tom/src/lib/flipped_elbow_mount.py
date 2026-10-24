"""Forearm-side case mounting for the upright, end-for-end flipped S4."""
import build123d as bd
from lib.booleans import as_single_shape as one
from lib.tom2_link_profiles import _unify

T=2.032
RI=.9652


def flip_servo(part,mid_x,mid_y=-.5):
    return part.rotate(bd.Axis((mid_x,mid_y,0),(0,0,1)),180)


def shorten_case_mount(part,mid_x):
    """Keep the blocky channel, place its end folds against the flipped case.

    Its contact face changes from the flange's inner X face to its outer X
    face. Retain actual bend radii, mounting bores and lower clearance cuts.
    """
    outer=part.bounding_box().max.X
    old_contact=outer-T
    new_contact=2*mid_x-old_contact
    shift=new_contact-outer
    old_root=outer-T-RI
    new_root=old_root+shift
    def box(x0,x1):
        return bd.Solid.make_box(x1-x0,1000,1000,
                                bd.Plane(origin=(x0,-500,-500)))
    channel=one(part.intersect(box(-500,new_root)))
    end=one(part.intersect(box(old_root,500))).moved(bd.Pos(shift,0,0))
    result=_unify(one(channel.fuse(end)).clean())
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result


def round_mount_clearance(part,radius=5.5):
    """Round the outer lower corners without cutting the mounting-hole lands."""
    # Datums come from the preserved root-cut ledge and the case-flange bottom.
    bb=part.bounding_box();root=bb.max.X-T-RI
    side=[f for f in part.faces() if f.geom_type==bd.GeomType.PLANE
          and abs(f.normal_at().Y)>.999 and f.area>1000]
    ledges=[e for f in side for e in f.outer_wire().edges()
            if e.geom_type==bd.GeomType.LINE and e.length>2
            and abs(e.start_point().Z-e.end_point().Z)<1e-6
            and bb.min.Z+5<e.center().Z<bb.max.Z-5
            and abs(e.bounding_box().max.X-root)<1e-5]
    x0=min(e.bounding_box().min.X for e in ledges)
    end_faces=[f for f in part.faces() if f.geom_type==bd.GeomType.PLANE
               and abs(f.normal_at().X)>.999 and f.area>100
               and f.bounding_box().min.X>root]
    z0=min(f.bounding_box().min.Z for f in end_faces)
    span=bb.max.X-x0+1
    cutters=[]
    for sign,cy in ((-1,-15.5348),(1,14.5348)):
        cy_center=cy-sign*radius
        corner_y=min(cy,cy_center)
        block=bd.Solid.make_box(span,radius,radius,
                 bd.Plane(origin=(x0,corner_y,z0)))
        circle=bd.Solid.make_cylinder(radius,span,
                 bd.Plane(origin=(x0,cy_center,z0+radius),z_dir=(1,0,0)))
        cutters.append(one(block.cut(circle)))
        ya=cy if sign>0 else cy-20
        cutters.append(bd.Solid.make_box(span,20,z0+radius+500,
                       bd.Plane(origin=(x0,ya,-500))))
    result=_unify(one(part.cut(*cutters)).clean())
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result
