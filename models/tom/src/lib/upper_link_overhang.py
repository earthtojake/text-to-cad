"""Bend-referenced wrist holes and continuous elbow case bends."""
import build123d as bd
from lib.booleans import as_single_shape as one
from lib.sheet_rule_scs import THICKNESS_MM as T,EFFECTIVE_BEND_RADIUS_MM as RI

# Exact reference datums measured in the original 500 mm configuration.
UPPER_EXTENSION=28.32329293543
WRIST_HOLE_FROM_TANGENT=2.0
WRIST_DROP=9.857232824481-(T+RI+WRIST_HOLE_FROM_TANGENT-2.65)
WRIST_CASE_BACK_X=16.976092935423-UPPER_EXTENSION


def refine_upper_link(part):
    bb=part.bounding_box()
    result=part
    bores=[]
    for f in part.faces():
        if f.geom_type==bd.GeomType.CYLINDER and abs(f.radius-1.1)<1e-6:
            b=f.bounding_box()
            if abs(b.size.Y-T)<1e-5:
                bores.append(((b.min.X+b.max.X)/2,b.min.Y,(b.min.Z+b.max.Z)/2))
    assert len(bores)==4
    # Fill the old bores before moving the four screw axes downward.
    for x,y,z in bores:
        result=one(result.fuse(bd.Solid.make_cylinder(1.1001,T,bd.Plane(origin=(x,y,z),z_dir=(0,1,0)))))
    # Case wall at the bend tangent; standard case holes are 2 mm inboard.
    # Terminate the bend/floor behind the case so the mounting tabs are wholly
    # outside its span. Tabs finish at the tangent, not at the outer bend bottom.
    tangent=bb.min.Z+T+RI
    result=one(result.cut(bd.Solid.make_box(WRIST_CASE_BACK_X+500,100,tangent+500,bd.Plane(origin=(-500,-50,-500)))))
    for x,y,z in bores:
        result=one(result.cut(bd.Solid.make_cylinder(1.1,T+2,bd.Plane(origin=(x,y-1,z-WRIST_DROP),z_dir=(0,1,0)))))
    # Extend the root ledge and existing constant-gauge end bends by 5.5 mm.
    root=bb.max.X-T-RI;z0=81.30762269826;z1=z0+5.5;x0=85.11351624092
    for y0,cy,flange_y in ((bb.min.Y,bb.min.Y+T+RI,-8.172),(bb.max.Y-T,bb.max.Y-T-RI,7.172)):
        wall=bd.Solid.make_box(root-x0,T,z1-z0,bd.Plane(origin=(x0,y0,z0)))
        corner_y=cy-(RI+T) if y0<0 else cy
        region=bd.Solid.make_box(RI+T,RI+T,z1-z0,bd.Plane(origin=(root,corner_y,z0)))
        outer=bd.Solid.make_cylinder(RI+T,z1-z0,bd.Plane(origin=(root,cy,z0)))
        inner=bd.Solid.make_cylinder(RI,z1-z0,bd.Plane(origin=(root,cy,z0)))
        bend=one(one(outer.cut(inner)).intersect(region))
        flange=bd.Solid.make_box(T,abs(flange_y-cy),z1-z0,bd.Plane(origin=(root+RI,min(cy,flange_y),z0)))
        result=one(result.fuse(wall,bend,flange))
    # Restoring the rectangular flange lands must not plug their lower holes.
    for f in part.faces():
        if f.geom_type==bd.GeomType.CYLINDER and abs(f.radius-1.1)<1e-6:
            b=f.bounding_box()
            if abs(b.size.X-T)<1e-5:
                y=(b.min.Y+b.max.Y)/2;z=(b.min.Z+b.max.Z)/2
                result=one(result.cut(bd.Solid.make_cylinder(1.1,T+2,bd.Plane(origin=(b.min.X-1,y,z),z_dir=(1,0,0)))))
    result=result.clean()
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result
