"""Sharp X-braced crane windows and matched rest-face patterns for the reach study.

5052 H32, 2.032 mm. Side webs are 4 mm; shared-face webs are 4.5 mm;
new lightening apertures stay at least 6 mm from bend tangencies.
Mount lands remain solid. These are CAD design checks, not tooling approval.
"""
import math
import build123d as bd
from lib.booleans import as_single_shape as one
from lib.sheet_rule_scs import THICKNESS_MM as T,EFFECTIVE_BEND_RADIUS_MM as RI

REST_Z=70.832711045537
ROOT_X=85.113516240922
WEB=6.0
WINDOW_RADIUS=1.5


def prism_xz(points):
    wire=bd.Wire.make_polygon([(x,-25,z) for x,z in points],close=True)
    return bd.Solid.extrude(bd.Face(wire),(0,50,0))


def inset_triangle(points,distance,radius=WINDOW_RADIUS):
    # Move each triangle vertex toward the incenter so its three edges
    # have exactly distance offset. This retains exact straight diagonals.
    lengths=[math.dist(points[1],points[2]),math.dist(points[2],points[0]),math.dist(points[0],points[1])]
    perimeter=sum(lengths)
    c=[sum(lengths[i]*points[i][j] for i in range(3))/perimeter for j in (0,1)]
    a,b,c0=points
    area=abs((b[0]-a[0])*(c0[1]-a[1])-(b[1]-a[1])*(c0[0]-a[0]))/2
    inradius=2*area/perimeter
    assert inradius>distance+0.01
    factor=1-distance/inradius
    return [(c[0]+factor*(x-c[0]),c[1]+factor*(y-c[1])) for x,y in points]


def windows(cells,lo,hi,web=WEB,radius=WINDOW_RADIUS):
    result=[]
    for i,(a,b) in enumerate(cells):
        p=[(a,lo),(b,lo),(b,hi),(a,hi)]
        tris=([p[0],p[1],p[2]],[p[0],p[2],p[3]]) if i%2==0 else ([p[0],p[1],p[3]],[p[1],p[2],p[3]])
        for tri in tris:
            q=inset_triangle(tri,web/2,radius)
            f=bd.Face(bd.Wire.make_polygon([(x,y,0) for x,y in q],close=True))
            result.append(f.fillet_2d(radius,f.vertices()))
    return result


BAY_WIDTH=30.0
SIDE_HEIGHT=30.0
# Equal perpendicular borders at the upper-left / chamfer and elbow-end /
# chamfer. Their opposite offsets change equally when the whole lattice moves.
LEFT_DIAGONAL_C=(REST_Z+T+RI+24.5)-(-15.8597766945)
RIGHT_DIAGONAL_C=(REST_Z+T+RI)-(ROOT_X-((REST_Z-T-RI)-(54.395222698259+2)))
SIDE_LO=REST_Z+T+RI+4
BAY_ORIGIN=(2*SIDE_LO+SIDE_HEIGHT-2*BAY_WIDTH-LEFT_DIAGONAL_C-RIGHT_DIAGONAL_C)/2
SIDE_WEB=4.0

def triangle_face(points,web=SIDE_WEB):
    q=inset_triangle(points,web/2)
    return bd.Face(bd.Wire.make_polygon([(x,y,0) for x,y in q],close=True))

def x_bay(a,lo,hi):
    b=a+BAY_WIDTH;c=(a+b)/2;m=(lo+hi)/2
    return [[(a,lo),(b,lo),(c,m)],[(b,lo),(b,hi),(c,m)],
            [(b,hi),(a,hi),(c,m)],[(a,hi),(a,lo),(c,m)]]

def side_windows(upper):
    """Sharp X-braced bays with the end half-bays following the plate cuts."""
    lo=REST_Z+T+RI+4 if upper else REST_Z-T-RI-4-SIDE_HEIGHT
    hi=lo+SIDE_HEIGHT;mid=(lo+hi)/2
    result=[]
    first=x_bay(BAY_ORIGIN-BAY_WIDTH,lo,hi)
    if upper:
        # Follow the / outer corner with a large sideways triangle, then
        # complete the rectangular lower corner with the small half-bay.
        result.append(triangle_face(first[1]))
        result.append(triangle_face([(BAY_ORIGIN-15,lo),(BAY_ORIGIN,lo),(BAY_ORIGIN-15,mid)]))
    else:result.extend(triangle_face(t) for t in first)
    for a in (BAY_ORIGIN,BAY_ORIGIN+BAY_WIDTH):
        result.extend(triangle_face(t) for t in x_bay(a,lo,hi))
    # Finish against the elbow-end diagonals with the same sideways half-bay.
    last=x_bay(BAY_ORIGIN+2*BAY_WIDTH,lo,hi)
    result.append(triangle_face(last[3]))
    a=BAY_ORIGIN+2*BAY_WIDTH;c=a+BAY_WIDTH/2
    if upper:
        result.append(triangle_face(last[2]))
        # The last corner is a right triangle, continuing the / diagonal.
        # Its right edge aligns with the adjacent top aperture and retains
        # the case-bend setback instead of continuing a full bay into it.
        b=a+BAY_WIDTH-2*math.sqrt(2)
        result.append(triangle_face([(c,mid),(b,mid),(b,mid+b-c)]))
    else:
        # Horizontal bottom, vertical right side and a 45 degree hypotenuse.
        result.append(triangle_face([(a,lo),(c,lo),(c,mid)]))
    return result

def window_tools(upper):
    sides=[]
    for f in side_windows(upper):
        face=f.rotate(bd.Axis.X,90).moved(bd.Pos(0,25,0))
        sides.append(bd.Solid.extrude(face,(0,-50,0)))
    # Top and side faces use the identical 30 mm post and centre stations.
    # The two facing horizontal sheets use exactly the same common tools.
    floor=[]
    for a in ([BAY_ORIGIN,BAY_ORIGIN+BAY_WIDTH] if upper else [BAY_ORIGIN-BAY_WIDTH,BAY_ORIGIN,BAY_ORIGIN+BAY_WIDTH]):
        for tri in x_bay(a,-15.5348+3,14.0348-3):
            f=triangle_face(tri,web=4.5)
            floor.append(bd.Solid.extrude(f.moved(bd.Pos(0,0,REST_Z-3)),(0,0,6)))
    return sides,floor

def accessory_holes(upper):
    lo=REST_Z+T+RI+4 if upper else REST_Z-T-RI-4-SIDE_HEIGHT
    stations=[BAY_ORIGIN+BAY_WIDTH/2,BAY_ORIGIN+3*BAY_WIDTH/2]
    if not upper:stations.insert(0,BAY_ORIGIN-BAY_WIDTH/2)
    return [(x,lo+SIDE_HEIGHT/2) for x in stations]


def finish_link(part,upper,*,pattern=True):
    result=part
    if upper:
        # The mounting-tab top follows the nominal case wall (2 mm beyond
        # its top row). Continue from that level to the full plate height.
        x=-15.8597766945;top=110.420199392815
        tangent=REST_Z+T+RI
        case_top=tangent+24.5
        result=one(result.cut(prism_xz([(-100,case_top),(x,case_top),(x+top-case_top,top),(-100,top+1)])))
        # Flat sidewall chamfer runs all the way to the case ledge. The bend
        # itself has a square end normal to its axis, with no diagonal cut
        # passing through the curved sheet.
        ledge=81.30762269826
        end=ROOT_X-((REST_Z-T-RI)-(54.395222698259+2.0))
        result=one(result.cut(bd.Solid.make_box(200-end,60,tangent+500,bd.Plane(origin=(end,-30,-500)))))
        result=one(result.cut(prism_xz([(end,tangent),(ROOT_X,tangent),(ROOT_X,ledge),(end+ledge-tangent,ledge)])))
    else:
        # Nominal case walls at the mounting interface, 2 mm from hole axes.
        bottom=33.895222698259-2.0
        case_top=54.395222698259+2.0
        result=one(result.cut(bd.Solid.make_box(500,60,bottom+500,bd.Plane(origin=(-200,-30,-500)))))
        result=one(result.cut(prism_xz([(ROOT_X,case_top),(110,case_top),(110,80),(ROOT_X,80)])))
        tangent=REST_Z-T-RI
        end=ROOT_X-(tangent-case_top)
        result=one(result.cut(bd.Solid.make_box(200-end,60,200-tangent,bd.Plane(origin=(end,-30,tangent)))))
        result=one(result.cut(prism_xz([(end,tangent),(ROOT_X,tangent),(ROOT_X,case_top)])))
    if not pattern:
        result=result.clean();result.label=part.label;result.color=part.color
        return result
    sides,floor=window_tools(upper)
    result=one(result.cut(*sides,*floor)).clean()
    for x,z in accessory_holes(upper):
        result=one(result.cut(bd.Solid.make_cylinder(1.6,50,bd.Plane(origin=(x,-25,z),z_dir=(0,1,0)))))
    for x,_ in accessory_holes(upper):
        result=one(result.cut(bd.Solid.make_cylinder(1.6,6,bd.Plane(origin=(x,-.75,REST_Z-3)))))
    result=result.clean()
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result
