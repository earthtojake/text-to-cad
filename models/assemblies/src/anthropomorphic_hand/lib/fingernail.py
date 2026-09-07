"""Anatomical dorsal nails, conformal saddles and captive M0.8 hardware.

CAD brief: native distal origin; +Y distal and -Z dorsal. Five delicate
blasted aluminum ovals sit on dark structural saddles, using the existing
pad-bore axes continued dorsally. No pad or routing geometry is altered.
Screws and nominal-thread inserts stop at Z=1.65, leaving 0.30 mm to the
immutable palmar inserts. Every factory is lazy and returns actual solids.
"""
from cadgen import build123d as bd
from lib.finish import finish
from lib.layout import FINGERS,THUMB_CMC,THUMB_LENGTHS,finger_fan_matrix


def _oval(rx,ry,rz,y,z):
    # Two meridian patches avoid a full-period rational face with tiny
    # subtraction loops, which STEP otherwise reloads as the removed pieces.
    half=bd.Sphere(1,arc_size3=180,align=bd.Align.NONE)
    sphere=half.fuse(bd.Rot(0,0,180)*half)
    return bd.Pos(0,y,z)*sphere.transform_geometry(bd.Matrix([
        [rx,0,0,0],[0,ry,0,0],[0,0,rz,0],[0,0,0,1]]))


def _make_fingernail(name,length,width,host):
    y=.71*length;bx=width/2-.825
    # A closed rational ellipsoid yields a continuously rounded uninterrupted
    # dorsal face and rolled perimeter, with no sharp loft boundary.
    nail=_oval(width*.37,length*.27,.68,y+.8,-4.04)
    # The broad end of the shallow oval is the dorsal fingertip, while this
    # narrow capsule carries load directly to the two existing rail seats.
    bridge=bd.Pos(0,y,-3.98)*bd.extrude(bd.SlotCenterToCenter(2*bx,2.1),amount=1.40)
    bridge=bd.fillet(bridge.edges(),.13)
    bridge=bridge.fuse(_oval(width*.355,length*.255,.60,y+.8,-3.81))
    # Exact conformal contact with the host and oval, without any overlap.
    bridge=(bridge-host)-nail
    screws=[];inserts=[]
    for sign,side in ((-1,'radial'),(1,'ulnar')):
        x=sign*bx
        shank=bd.Pos(x,y,(-3.98+1.60)/2)*bd.Cylinder(.40,1.60+3.98)
        head=bd.Pos(x,y,-4.205)*bd.Cylinder(.79,.45)
        head=bd.fillet(head.edges(),.07)
        screw=shank.fuse(head)
        socket=bd.Pos(x,y,-4.5)*bd.extrude(bd.RegularPolygon(.34,6),amount=.29)
        screw=screw-socket
        insert=bd.Pos(x,y,(-3.65+1.65)/2)*bd.Cylinder(.56,1.65+3.65)
        flange=bd.Pos(x,y,-3.30)*bd.Cylinder(.74,.70)
        insert=(insert.fuse(flange)-(bd.Pos(x,y,-1)*bd.Cylinder(.40,8)))-host
        # Upper side of the bridge is relieved around the captive flange;
        # the screw head bears directly on its dorsal seat at Z=-3.98.
        bridge=bridge-insert
        bridge=bridge-(bd.Pos(x,y,-1)*bd.Cylinder(.43,9))
        nail=nail-(bd.Pos(x,y,-1)*bd.Cylinder(.84,10))
        screws.append(finish(screw,'steel',f'{name}_fingernail_{side}_M0p8_socket_screw'))
        inserts.append(finish(insert,'aluminum',f'{name}_fingernail_{side}_M0p8_captive_insert'))
    parts=[finish(nail,'aluminum',f'{name}_dorsal_fingernail'),finish(bridge,'dark',f'{name}_fingernail_conformal_saddle'),*screws,*inserts]
    for shape in parts:
        if len(shape.solids())!=1 or not shape.is_valid or shape.volume<=0:
            raise ValueError(f'{shape.label}: expected one valid positive solid, got {len(shape.solids())}')
    return parts


def make_fingernail(name='index',length=17.,width=12.):
    from lib.phalanx import make_phalanx
    host=make_phalanx(length,width,True,name+'_distal_frame')
    # Keep the two exact meridian faces through subsequent machining; same-
    # domain cleanup would recreate the unstable full-period trimmed face.
    with bd.SkipClean():
        return _make_fingernail(name,length,width,host)


def fingernail_bodies():
    """Already assembled/fanned (shape, frame, system, kind) registry tuples."""
    from lib.assembly import matrix_location
    parts=[]
    for finger in FINGERS:
        place=matrix_location(finger_fan_matrix(finger))*bd.Pos(finger.x,finger.base_y+sum(finger.lengths[:2]),0)
        for p in make_fingernail(finger.name,finger.lengths[2],finger.widths[2]):
            parts.append((place*p,finger.name+'_dip',finger.name,'fingernail' if p.label.endswith('dorsal_fingernail') else 'fastener' if p.label.endswith(('screw','insert')) else 'nail_mount'))
    place=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*bd.Pos(0,sum(THUMB_LENGTHS[:2]),0)
    for p in make_fingernail('thumb',21.,13.):
        parts.append((place*p,'thumb_ip','thumb','fingernail' if p.label.endswith('dorsal_fingernail') else 'fastener' if p.label.endswith(('screw','insert')) else 'nail_mount'))
    return parts
