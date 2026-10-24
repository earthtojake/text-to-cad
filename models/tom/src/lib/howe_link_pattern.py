"""Rounded Howe windows with uniform 6 mm rails and webs.

The longer lower link includes one additional complete bay at its shoulder end.
Shared bays retain their longitudinal stations; functional mounting lands stay solid.
"""
import build123d as bd
from lib import link_truss as tr
from lib.booleans import as_single_shape as one

# Keep at least 6 mm at the horizontal face's end bend as well as along its sides.
PITCH=26.75
COUNT=4
CENTRE_X=tr.BAY_ORIGIN+(37.5-tr.BAY_WIDTH)/2+1.5*tr.BAY_WIDTH
ORIGIN=CENTRE_X-COUNT*PITCH/2
SIDE_WEB=6.0
FLOOR_WEB=6.0
CORNER_RADIUS=2.0
M3_CLEARANCE_DIAMETER=3.3  # Same clearance as the existing M3 base-plate mounts.
HOLE_EDGE_INSET=8.0
HOLE_NODE_OFFSET=3.0


def bay_faces(index,lo,hi,web=SIDE_WEB):
    a=ORIGIN+PITCH*index;b=a+PITCH
    p=[(a,lo),(b,lo),(b,hi),(a,hi)]
    # / / | \\ \\: a textbook Howe with one centre vertical and no X.
    triangles=([p[0],p[1],p[2]],[p[0],p[2],p[3]]) if index<COUNT//2 else ([p[0],p[1],p[3]],[p[1],p[2],p[3]])
    faces=[tr.triangle_face(t,web=web) for t in triangles]
    return [f.fillet_2d(CORNER_RADIUS,f.vertices()) for f in faces]


def flat_bounds(blank,axis):
    """Outer edge and bend tangent of the principal unperforated flat face."""
    return max((f for f in blank.faces() if f.geom_type==bd.GeomType.PLANE
                and abs(getattr(f.normal_at(),axis))>.99),
               key=lambda f:f.area).bounding_box()


def pattern_faces(upper,lo,hi,web):
    # A half-web inset in bay_faces adds the remaining half of each edge rail.
    return [f for i in range(0 if upper else -1,COUNT)
            for f in bay_faces(i,lo+web/2,hi-web/2,web)]


def side_hole_centers(upper,lo,hi):
    """M3 accessory holes in the solid lands at the diagonal ends, in X/Z."""
    centers=[]
    for i in range(0 if upper else -1,COUNT):
        a=ORIGIN+PITCH*i;c=a+PITCH
        rising=i<COUNT//2
        centers.append((a+HOLE_NODE_OFFSET if rising else c-HOLE_NODE_OFFSET,
                        lo+HOLE_EDGE_INSET))
        # The two inward diagonals share one top-center hole.
        if i not in (COUNT//2-1,COUNT//2):
            centers.append((c-HOLE_NODE_OFFSET if rising else a+HOLE_NODE_OFFSET,
                            hi-HOLE_EDGE_INSET))
    centers.append((CENTRE_X,hi-HOLE_EDGE_INSET))
    return centers


def finish_blank(blank,upper):
    tools=[]
    side=flat_bounds(blank,'Y')
    floor=flat_bounds(blank,'Z')
    for f in pattern_faces(upper,side.min.Z,side.max.Z,SIDE_WEB):
        f=f.rotate(bd.Axis.X,90).moved(bd.Pos(0,25,0))
        tools.append(bd.Solid.extrude(f,(0,-50,0)))
    for f in pattern_faces(upper,floor.min.Y,floor.max.Y,FLOOR_WEB):
        tools.append(bd.Solid.extrude(f.moved(bd.Pos(0,0,tr.REST_Z-3)),(0,0,6)))
    for x,z in side_hole_centers(upper,side.min.Z,side.max.Z):
        tools.append(bd.Solid.make_cylinder(M3_CLEARANCE_DIAMETER/2,50,
                     bd.Plane(origin=(x,-25,z),z_dir=(0,1,0))))
    result=one(blank.cut(*tools)).clean()
    assert result.is_valid and len(result.solids())==1
    result.label=blank.label;result.color=blank.color
    return result
