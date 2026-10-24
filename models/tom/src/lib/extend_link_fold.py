"""Continue a link's folded bridge to the end shared by both side walls."""
import build123d as bd
from lib.booleans import as_single_shape as one
from lib.tom2_link_profiles import _unify

T=2.032
RI=.9652


def extend_link_fold(part,roof=True):
    """Extrude the existing formed end section, keeping the original gauge/radii.

    Opposite side walls have staggered ends for the case-hole pattern. Stop at
    the shorter wall so the bridge has a straight, fully supported termination.
    The former 1 mm flat-tab corner becomes part of the continuous fold.
    """
    bb=part.bounding_box()
    tangent=bb.max.Z-T-RI if roof else bb.min.Z+T+RI
    walls=[f for f in part.faces() if f.geom_type==bd.GeomType.PLANE
           and abs(f.normal_at().Y)>.999 and f.area>500]
    target=min(f.bounding_box().max.X for f in walls) if roof else max(f.bounding_box().min.X for f in walls)
    caps=[f for f in part.faces() if f.geom_type==bd.GeomType.PLANE
          and abs(f.normal_at().X)>.999
          and f.bounding_box().size.Y>25
          and (f.bounding_box().min.Z>=tangent-1e-5 if roof else f.bounding_box().max.Z<=tangent+1e-5)]
    assert caps
    cap=(max if roof else min)(caps,key=lambda f:f.center().X)
    start=cap.center().X;dx=target-start
    assert dx>0 if roof else dx<0
    end_faces=[f for f in part.faces() if f.geom_type==bd.GeomType.PLANE
               and abs(f.normal_at().X)>.999 and abs(f.center().X-start)<1e-5
               and (f.bounding_box().min.Z>=tangent-1e-5 if roof else f.bounding_box().max.Z<=tangent+1e-5)]
    extension=[bd.Solid.extrude(f,(dx,0,0)) for f in end_faces]
    x0=min(start,target);length=abs(dx)
    patches=[]
    for y in (bb.min.Y,bb.max.Y-T):
        patches.append(bd.Solid.make_box(length,T,1.0,
            bd.Plane(origin=(x0,y,tangent-1 if roof else tangent))))
    result=one(part.fuse(*extension,*patches)).clean()
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result
