"""Balance link heights while retaining the elbow at the lower end corner."""
import build123d as bd
from lib.booleans import as_single_shape as one

# Rest datums from the preceding flush-plate layout, in millimetres.
LOWER_BOTTOM=34.175
REST_CONTACT=70.832711045537
UPPER_TOP=113.499976694555
# Lower gains d; upper loses d as the elbow and downstream assembly descend.
BALANCE_DROP=((UPPER_TOP-REST_CONTACT)-(REST_CONTACT-LOWER_BOTTOM))/2
CASE_HOLE_EDGE_MARGIN=2.65
MOUNT_MARGIN_CORRECTION=(2.8-CASE_HOLE_EDGE_MARGIN)/2
LOWER_EXTENSION=BALANCE_DROP-MOUNT_MARGIN_CORRECTION
ELBOW_BALANCE_DROP=BALANCE_DROP+MOUNT_MARGIN_CORRECTION


def extend_lower_down(part,web_end,amount=LOWER_EXTENSION):
    """Extend the long side sheets; retain the shoulder mounting window."""
    floor=part.bounding_box().min.Z
    sides=[f for f in part.faces() if f.geom_type==bd.GeomType.PLANE
           and abs(f.normal_at().Y)>.999 and f.area>500]
    # Start at the existing shoulder-window wall, clear of its hole lands.
    window_edges=[e for f in sides for e in f.outer_wire().edges()
                  if e.geom_type==bd.GeomType.LINE and abs(e.start_point().X-e.end_point().X)<1e-5
                  and e.center().X<0 and 10<e.length<25]
    start=max(web_end,max(e.center().X for e in window_edges))
    additions=[]
    for y in (part.bounding_box().min.Y,part.bounding_box().max.Y-2.032):
        face=next(f for f in sides if abs(f.center().Y-y)<1e-5)
        end=face.bounding_box().max.X
        strip=bd.Solid.make_box(end-start,2.032,amount+1.001,
                 bd.Plane(origin=(start,y,floor-amount)))
        corners=[e for e in strip.edges() if abs(e.length-2.032)<1e-5
                 and abs(e.center().Z-(floor-amount))<1e-5]
        strip=strip.fillet(1.0,corners)
        additions.append(strip)
    result=one(part.fuse(*additions)).clean()
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result
