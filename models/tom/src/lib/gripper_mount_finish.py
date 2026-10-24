"""Approved camera-stand thinning and underside servo mounting ear."""
import math
import build123d as b

def narrow_camera_support(frame):
    """Six-mm camera legs with square expansion after the upper bend.

    Retain the original flat gripper sheets and both original claw positions.
    """
    from end_effector.servo6_gripper_concept import CAMERA_RISER_LENGTH_MM, CAMERA_RISER_HEADING_DEG, CAMERA_PANEL_BOTTOM_LAND_MM
    riser_height=CAMERA_RISER_LENGTH_MM*math.sin(math.radians(CAMERA_RISER_HEADING_DEG))
    candidates=[f for f in frame.faces() if f.geom_type==b.GeomType.PLANE
                and abs(f.bounding_box().size.Y-40)<1e-5
                and abs(f.bounding_box().size.Z-riser_height)<1e-4
                and f.area>500]
    assert candidates, 'camera riser face not found'
    face=min(candidates,key=lambda f:f.center().Z)
    vertices=[v.center() for v in face.outer_wire().vertices()]
    low=min(vertices,key=lambda v:v.Z)
    origin=b.Vector(low.X,0,low.Z)
    normal=face.normal_at()
    xdir=b.Vector(0,1,0)
    if normal.cross(xdir).Z<0:xdir=-xdir
    plane=b.Plane(origin=origin,x_dir=xdir,z_dir=normal)
    q=frame
    # Keep 32 mm width through both bends; extend through the forming land and expand into a 40 mm square
    # with a perpendicular shoulder, rather than a diagonal on the riser.
    panels=[f for f in frame.faces() if f.geom_type==b.GeomType.PLANE
            and abs(f.bounding_box().size.Y-40)<1e-5
            and f.bounding_box().max.Z>frame.bounding_box().max.Z-2 and f.area>400]
    panel=min(panels,key=lambda f:f.center().Z)
    low_panel=min((v.center() for v in panel.outer_wire().vertices()),key=lambda v:v.Z)
    pn=panel.normal_at();px=b.Vector(0,1,0)
    if pn.cross(px).Z<0:px=-px
    panel_plane=b.Plane(origin=(low_panel.X,0,low_panel.Z),x_dir=px,z_dir=pn)
    from lib.short_gripper_trial import box
    top_z=max(f.bounding_box().max.Z for f in frame.faces()
              if f.geom_type==b.GeomType.PLANE and abs(f.normal_at().Z)>.999 and f.area>100)
    for side in (-1,1):
        xa,xb=sorted((side*16,side*30))
        cut=box((xa,-300,-100),(xb,CAMERA_PANEL_BOTTOM_LAND_MM,100)).moved(panel_plane.location)
        from lib.booleans import as_single_shape
        cut=as_single_shape(cut.intersect(box((-300,-60,top_z),(50,60,300))))
        q=q.cut(cut)
    # Continue the narrow riser through its flat foot, including the sheet
    # thickness. Join the existing claw outline with one straight diagonal.
    from lib.gripper_063 import THICKNESS
    z=top_z-THICKNESS
    outer=-24.0238
    start=-114.1939765254
    end=start+(-16-outer)
    outline=[(start,outer),(end,-16),(0,-16),(0,-60),(start,-60)]
    trim=b.Solid.extrude(b.Face(b.Wire.make_polygon(
        [(x,y,z-.001) for x,y in outline],close=True)),(0,0,THICKNESS+.002))
    q=q.cut(trim)
    q=q.cut(box((-116.62233,16,z-.001),(0,60,top_z+.001)))
    q=q.clean();q.label=frame.label;q.color=frame.color
    assert q.is_valid and len(q.solids())==1
    return q


def underside_mounting_prong(frame):
    """Small lower-sheet ear at the unused servo seat; retain the original jaw."""
    from lib.short_gripper_trial import box
    from lib.booleans import as_single_shape as one
    from lib.gripper_063 import THICKNESS
    z=frame.bounding_box().min.Z
    cx,cy=-136.8473300835,-8.475
    profile=b.Face(b.Wire.make_polygon([
        (cx-3.3,-16,z),(cx+3.3,-16,z),
        (cx+3.3,cy+3.3,z),(cx-3.3,cy+3.3,z)],close=True))
    profile=profile.fillet_2d(1.0,profile.vertices())
    q=one(frame.fuse(b.Solid.extrude(profile,(0,0,THICKNESS))))
    q=one(q.cut(b.Solid.make_cylinder(1.1,THICKNESS+.02,
               b.Plane(origin=(cx,cy,z-.01)))))
    # Original e110 is 0.172 mm proud of e112; trim that short step flush.
    q=one(q.cut(box((-119.0973300835-.001,-14.9752,z-.001),
                   (-118.9253300835,-9.5488,z+THICKNESS+.001)))).clean()
    q.label=frame.label;q.color=frame.color
    assert q.is_valid and len(q.solids())==1
    return q


