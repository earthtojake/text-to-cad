"""Five smooth silicone fingertips on screwed, conformal mounting bridges.

CAD brief: millimeters; native distal-joint origin, finger +Y, palm +Z.
The index/thumb contact ellipsoids are the immutable solved pinch interface.
Only their lower caps below Z=4.15 are replaced by a dark conformal carrier.
Two M0.8 socket screws seat in the carrier and engage flanged inserts pressed
into the existing Ø1.12 phalange bores. Threads use nominal cylindrical mating
surfaces; the thread helix and press-fit interference are omitted from CAD.
Each returned component is a positive closed native solid.
"""
import math
from cadgen import build123d as bd
from lib.finish import finish
from lib.layout import FINGERS, THUMB_CMC, THUMB_LENGTHS, finger_fan_matrix

PAD_RADII = {'index': (6.25,6.5,2.), 'middle': (6.25,6.5,2.),
             'ring': (6.,6.5,2.), 'little': (5.2,5.5,2.),
             'thumb': (6.75,7.,2.)}
PAD_CENTER_Y_FRACTION=.71
PAD_CENTER_Z=5.4
PAD_BOND_PLANE_Z=4.15
MOUNT_SEAT_Z=3.325


def pad_ellipsoid(name, length, radii=None, lower_z=None, upper_z=None):
    """Exact rational ellipsoid; no faceted or lofted contact approximation."""
    rx,ry,rz=PAD_RADII[name] if radii is None else radii
    # Keep the polar axis normal to the bond plane. Rotating it onto the
    # dorsal hemisphere makes STEP select the complementary lower cap on
    # reload, even though the in-memory Boolean is a valid upper solid.
    # Trim the analytic sphere by latitude before anisotropic conversion.
    latitude=-90. if lower_z is None else math.degrees(math.asin((lower_z-PAD_CENTER_Z)/rz))
    upper_latitude=90. if upper_z is None else math.degrees(math.asin((upper_z-PAD_CENTER_Z)/rz))
    sphere=bd.Sphere(1,arc_size1=latitude,arc_size2=upper_latitude,align=bd.Align.NONE)
    shape=sphere.transform_geometry(bd.Matrix([
        [rx,0,0,0],[0,ry,0,0],[0,0,rz,0],[0,0,0,1]]))
    return bd.Pos(0,length*PAD_CENTER_Y_FRACTION,PAD_CENTER_Z)*shape


def _socket_screw():
    # Turned shank seats under the head at 3.60; its tip is recessed in the
    # host through-bore. A real six-flat socket gives a consistent hardware
    # highlight, without ornamental thread tessellation at this scale.
    shank=bd.Pos(0,0,(1.95+3.60)/2)*bd.Cylinder(.40,3.60-1.95)
    head=bd.Pos(0,0,(3.60+4.05)/2)*bd.Cylinder(.875,.45)
    head=bd.fillet(head.edges(),.075)
    screw=shank.fuse(head)
    socket=bd.Pos(0,0,3.79)*bd.extrude(bd.RegularPolygon(.39,6),amount=.5)
    screw=screw-socket
    return screw


def make_fingertip_pad(name='index', length=17., width=12., radii=None):
    """Return pad, bridge, two screws, two inserts in the distal frame.

    Bridge bottom meets the host boss top at Z=3.325. Its integral lower
    ellipsoid cap shares a Z=4.15 bond plane with the silicone. Screw head
    undersides meet Z=3.60 counterbores. Flanged M0.8 inserts nominally contact
    Ø1.12 host bores and seat on the boss tops, making the bolts captive.
    """
    y=length*PAD_CENTER_Y_FRACTION
    pad=pad_ellipsoid(name,length,radii,lower_z=PAD_BOND_PLANE_Z)
    # A small silicone overhang beyond the bonded support footprint keeps
    # the hard carrier back from the tactile edge (~0.12 mm at the bond rim).
    # It also prevents coincident curved surface edges at the bond boundary.
    rx,ry,rz=PAD_RADII[name] if radii is None else radii
    cap=pad_ellipsoid(name,length,(.975*rx,.975*ry,rz),upper_z=PAD_BOND_PLANE_Z)
    # Capsule-ended bridge reaches both existing bored seats. Rounded edges
    # terminate against the lower cap, creating one smooth, structural body.
    bx=width/2-.825
    beam=bd.Pos(0,y,MOUNT_SEAT_Z)*bd.extrude(bd.SlotCenterToCenter(2*bx,2.45),amount=.625)
    beam=bd.fillet(beam.edges(),.10)
    bridge=beam.fuse(cap)
    from lib.phalanx import make_phalanx
    host=make_phalanx(length,width,True)
    screws=[];inserts=[]
    for sign,side in ((-1,'radial'),(1,'ulnar')):
        x=sign*bx
        bridge=bridge-(bd.Pos(x,y,3.5)*bd.Cylinder(.43,4))
        bridge=bridge-(bd.Pos(x,y,2.5)*bd.Cylinder(.775,2.))
        bridge=bridge-(bd.Pos(x,y,3.60+1)*bd.Cylinder(.925,2))
        screw=bd.Pos(x,y,0)*_socket_screw()
        screws.append(finish(screw,'steel',f'{name}_fingertip_{side}_M0p8_socket_screw'))
        insert=bd.Pos(x,y,(1.95+3.325)/2)*bd.Cylinder(.56,3.325-1.95)
        flange=bd.Pos(x,y,(3.325+3.5)/2)*bd.Cylinder(.75,3.5-3.325)
        insert=(insert.fuse(flange)-(bd.Pos(x,y,2.7)*bd.Cylinder(.40,3.)))-host
        inserts.append(finish(insert,'aluminum',f'{name}_fingertip_{side}_M0p8_captive_insert'))
    # The sculpted rail rises slightly above its nominal boss plane beside
    # each boss. Machine the bridge underside against that real host surface;
    # a flat beam alone would penetrate the curved rail by ~0.075 mm³.
    bridge=bridge-host
    parts=[finish(pad,'pad',f'{name}_fingertip_silicone_pad'),
           finish(bridge,'dark',f'{name}_fingertip_conformal_bridge'),*screws,*inserts]
    for shape in parts:
        if len(shape.solids())!=1 or not shape.is_valid or shape.volume<=0:
            raise ValueError(f'{shape.label}: expected one valid positive solid')
    return parts


def fingertip_pad_bodies():
    """Already assembled/fanned (shape, frame, system, kind) registry tuples."""
    from lib.assembly import matrix_location
    parts=[]
    for finger in FINGERS:
        place=matrix_location(finger_fan_matrix(finger))*bd.Pos(finger.x,finger.base_y+sum(finger.lengths[:2]),0)
        for p in make_fingertip_pad(finger.name,finger.lengths[2],finger.widths[2]):
            parts.append((place*p,finger.name+'_dip',finger.name,
                          'fingertip_pad' if p.label.endswith('silicone_pad') else 'fastener' if p.label.endswith(('screw','insert')) else 'pad_mount'))
    place=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*bd.Pos(0,sum(THUMB_LENGTHS[:2]),0)
    for p in make_fingertip_pad('thumb',21.,13.):
        parts.append((place*p,'thumb_ip','thumb',
                      'fingertip_pad' if p.label.endswith('silicone_pad') else 'fastener' if p.label.endswith(('screw','insert')) else 'pad_mount'))
    return parts
