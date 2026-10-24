"""Straight upper-link side sheets with a vertically centered wrist mount."""
import build123d as bd
from lib.booleans import as_single_shape as one
from lib.tom2_link_profiles import _unify

T=2.032
RI=.9652
UPPER_FLOOR_RAISE=13.814642343516
WRIST_RAISE=11.375+UPPER_FLOOR_RAISE/2


def match_upper_height(part,height):
    """Raise the complete lower fold, retaining the top case mounting row."""
    bb=part.bounding_box();dz=bb.size.Z-height
    assert abs(dz-UPPER_FLOOR_RAISE)<1e-5
    split=bb.min.Z+T+RI+1.001
    def region(z0,z1):
        return bd.Solid.make_box(1000,1000,z1-z0,bd.Plane(origin=(-500,-500,z0)))
    floor=one(part.intersect(region(-500,split))).moved(bd.Pos(0,0,dz))
    upper=one(part.intersect(region(split+dz,500)))
    result=_unify(one(upper.fuse(floor)).clean())
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result


def rectangular_upper_link(part):
    """Straighten the top while preserving the lower clearance cuts.

    The four wrist-case bores move with the servo. Existing bend surfaces and
    the elbow-roll case-hole pattern remain at their original datums.
    """
    bb=part.bounding_box()
    bottom=bb.min.Z+T+RI
    top=bb.max.Z-1e-7  # B-rep bounding tolerance, not a design clearance.
    # The upright end bends turn the side sheets into the S4 case mounts.
    root=bb.max.X-T-RI
    result=part
    for y0 in (-18.532,15.5):
        faces=[f for f in part.faces() if f.geom_type==bd.GeomType.PLANE
               and abs(abs(f.normal_at().Y)-1)<1e-6 and f.area>1000
               and abs(f.center().Y-y0)<1e-5]
        left=min(f.bounding_box().min.X for f in faces)
        # Preserve the original root clearance boundary, not the bounding box.
        ledges=[e for f in faces for e in f.outer_wire().edges()
                if e.geom_type==bd.GeomType.LINE and e.length>5
                and abs(e.start_point().Z-e.end_point().Z)<1e-6
                and bottom+1<e.center().Z<top-1
                and e.bounding_box().max.X>root]
        assert len(ledges)==1
        cut_x=ledges[0].bounding_box().min.X
        cut_z=ledges[0].center().Z
        bores=[]
        for f in part.faces():
            if f.geom_type!=bd.GeomType.CYLINDER or abs(f.radius-1.1)>1e-6:
                continue
            b=f.bounding_box()
            if abs(b.min.Y-y0)<1e-5 and abs(b.max.Y-(y0+T))<1e-5:
                bores.append(((b.min.X+b.max.X)/2,(b.min.Z+b.max.Z)/2))
        assert len(bores)==2
        region=bd.Solid.make_box(root-left,T,top-bottom+5,
                                bd.Plane(origin=(left,y0,bottom)))
        result=one(result.cut(region))
        wall=bd.Solid.make_box(root-left,T,top-bottom,
                              bd.Plane(origin=(left,y0,bottom)))
        # Round only the free-end corners. The root joins existing true bends.
        end_edges=[e for e in wall.edges() if abs(e.length-T)<1e-6
                   and abs(e.center().X-left)<1e-5]
        wall=wall.fillet(1.0,end_edges)
        clearance=bd.Solid.make_box(root-cut_x+1,T+2,cut_z-bottom,
                                    bd.Plane(origin=(cut_x,y0-1,bottom)))
        wall=one(wall.cut(clearance))
        for x,z in bores:
            tool=bd.Solid.make_cylinder(1.1,T+2,
                bd.Plane(origin=(x,y0-1,z+WRIST_RAISE),z_dir=(0,1,0)))
            wall=one(wall.cut(tool))
        result=one(result.fuse(wall))
        # Replace the inherited straight patch and interrupted bend together.
        # A quarter annulus continues the original constant-gauge end bend.
        ro=RI+T
        cy=y0+ro if y0<0 else y0-RI
        corner_y=cy-ro if y0<0 else cy
        corner=bd.Solid.make_box(ro+1e-6,ro,top-cut_z+1,
                                 bd.Plane(origin=(root,corner_y,cut_z)))
        result=one(result.cut(corner))
        plane=bd.Plane(origin=(root,cy,cut_z))
        annulus=one(bd.Solid.make_cylinder(ro,top-cut_z,plane).cut(
            bd.Solid.make_cylinder(RI,top-cut_z,plane)))
        bend=one(annulus.intersect(corner))
        result=one(result.fuse(bend))
    result=_unify(result.clean())
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result
