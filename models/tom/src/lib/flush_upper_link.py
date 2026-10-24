"""Seat the upper link's formed floor on the lower link at the rest datum."""
import build123d as bd
from lib.booleans import as_single_shape as one

T=2.032
RI=.9652


def flush_upper_link(part,lower):
    bb=part.bounding_box();base=lower.bounding_box()
    # The short lower side-wall end is the user's e114 alignment datum.
    walls=[f for f in lower.faces() if f.geom_type==bd.GeomType.PLANE
           and abs(f.normal_at().Y)>.999 and f.area>500]
    end=min(f.bounding_box().max.X for f in walls)
    # Preserve the root-cut shoulder while moving its vertical boundary in.
    sides=[f for f in part.faces() if f.geom_type==bd.GeomType.PLANE
           and abs(f.normal_at().Y)>.999 and f.area>500]
    ledges=[e for f in sides for e in f.outer_wire().edges()
            if e.geom_type==bd.GeomType.LINE and e.length>2
            and abs(e.start_point().Z-e.end_point().Z)<1e-5
            and bb.min.Z+5<e.center().Z<bb.max.Z-5
            and e.bounding_box().min.X>end]
    ledge=min(e.center().Z for e in ledges)
    old_end=min(e.bounding_box().min.X for e in ledges)
    cut=bd.Solid.make_box(old_end-end,1000,ledge+500,bd.Plane(origin=(end,-500,-500)))
    trimmed=one(part.cut(cut)).clean()
    # Move the complete floor, both real bends and their corner transitions.
    dz=base.max.Z-bb.min.Z
    split=bb.min.Z+T+RI+1.001
    def region(z0,z1):
        return bd.Solid.make_box(1000,1000,z1-z0,bd.Plane(origin=(-500,-500,z0)))
    fold=one(trimmed.intersect(region(-500,split)))
    upper=one(trimmed.intersect(region(split,500)))
    sections=[f for f in upper.faces() if f.geom_type==bd.GeomType.PLANE
              and abs(f.center().Z-split)<1e-5 and f.normal_at().Z<-.999]
    bridges=[bd.Solid.extrude(f,(0,0,dz)) for f in sections]
    result=one(upper.fuse(fold.moved(bd.Pos(0,0,dz)),*bridges)).clean()
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result
