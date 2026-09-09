"""Preserve the fingertip bridge envelope using two rational meridian patches."""
import math
from cadgen import build123d as bd
from lib.fingertip_pad import PAD_RADII,PAD_CENTER_Y_FRACTION,PAD_CENTER_Z,PAD_BOND_PLANE_Z,MOUNT_SEAT_Z
from lib.finish import finish

def make_bridge(name,length,width):
    from lib.phalanx import make_phalanx
    host=make_phalanx(length,width,True)
    rx,ry,rz=PAD_RADII[name];y=length*PAD_CENTER_Y_FRACTION;bx=width/2-.825
    with bd.SkipClean():
        half=bd.Sphere(1,arc_size3=180,align=bd.Align.NONE)
        sphere=half.fuse(bd.Rot(0,0,180)*half)
        cap=bd.Pos(0,y,PAD_CENTER_Z)*sphere.transform_geometry(bd.Matrix([
            [.975*rx,0,0,0],[0,.975*ry,0,0],[0,0,rz,0],[0,0,0,1]]))
        # Generate the bond-plane intersection on the transformed ellipsoid.
        # Transforming an already latitude-trimmed sphere leaves its planar
        # cap and curved face reported as intersecting at their common rim.
        cap=cap & (bd.Pos(0,y,PAD_BOND_PLANE_Z-10)*bd.Box(30,30,20))
        beam=bd.Pos(0,y,MOUNT_SEAT_Z)*bd.extrude(bd.SlotCenterToCenter(2*bx,2.45),amount=.625)
        beam=bd.fillet(beam.edges(),.10);bridge=beam.fuse(cap)
        for sign in (-1,1):
            x=sign*bx
            bridge=bridge-(bd.Pos(x,y,3.5)*bd.Cylinder(.43,4))
            bridge=bridge-(bd.Pos(x,y,2.5)*bd.Cylinder(.775,2.))
            bridge=bridge-(bd.Pos(x,y,4.60)*bd.Cylinder(.925,2))
        bridge=bridge-host
    assert len(bridge.solids())==1 and bridge.is_valid and bridge.volume>0,name
    return finish(bridge,'dark',f'{name}_fingertip_conformal_bridge')

def bridge_bodies():
    from lib.layout import FINGERS,THUMB_CMC,THUMB_LENGTHS,finger_fan_matrix
    from lib.assembly import matrix_location
    bodies=[]
    for f in FINGERS:
        placement=matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y+sum(f.lengths[:2]),0)
        bodies.append((placement*make_bridge(f.name,f.lengths[2],f.widths[2]),f.name+'_dip',f.name,'pad_mount'))
    placement=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*bd.Pos(0,sum(THUMB_LENGTHS[:2]),0)
    bodies.append((placement*make_bridge('thumb',21.,13.),'thumb_ip','thumb','pad_mount'))
    return bodies
