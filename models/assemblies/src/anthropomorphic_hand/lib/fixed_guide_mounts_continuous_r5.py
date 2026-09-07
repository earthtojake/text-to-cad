from lib.phalanx_r5_boolean import common as _common,cut as _cut
from copy import deepcopy
"""Short fixed-guide outlet clamps seated on the original phalanx side rails."""
import numpy as np
from cadgen import build123d as bd
from lib.guide_mounts import _finish,_bolt,_sweep
from lib.palm_guide_mounts import _row
from lib.phalanx_r5_host import make_phalanx
from lib.layout import FINGERS,finger_fan_matrix


def _saddle(host,x,y,z,height,label,rail_width=1.45):
    raw=bd.Pos(x,y,z)*bd.Box(rail_width+.8,1.10,height)
    raw=_cut(bd.fillet(raw.edges(),.10),host)
    lower=raw & (bd.Pos(x,y,z-height)*bd.Box(5,3,2*height-.02))
    upper=raw & (bd.Pos(x,y,z+height)*bd.Box(5,3,2*height-.02))
    sx=x-np.sign(x)*1.75
    for top in (False,True):
        tab=bd.Pos((x+sx)/2,y,z+(.43 if top else -.43))*bd.Box(abs(sx-x)+.65,1.,.42)
        if top:upper=_cut(upper.fuse(tab),host)
        else:lower=_cut(lower.fuse(tab),host)
    hole=bd.Pos(sx,y,z)*bd.Cylinder(.32,height+2)
    return lower-hole,upper-hole,(sx,y,z+.64)


def make_fixed_outlet_pair(length,width,radius,label):
    full_host=make_phalanx(length,width);parts=[]
    for sign in (-1,1):
        station=length-(15 if sign<0 and radius>4 else 7)
        ylo=station-1.0;yhi=length-2.0
        host=_common(full_host,(bd.Pos(0,(ylo+yhi)/2,0)*bd.Box(width+4,yhi-ylo,20)))
        y=length-3.425;z=sign*radius
        name=label+('_positive' if sign>0 else '_negative')
        from lib.assembly import matrix_location
        from lib.finger_routing import connector
        from scipy.optimize import brentq
        lane=3. if radius>4 else 4.2
        cp=np.array(connector([lane,12.25,0],[.9,length-3,radius])['points'])
        if length==21 and radius<4:cp=np.array([[lane,10,0],[lane,14,0],[.9,14,radius],[.9,18,radius]])
        def point(t):return (1-t)**3*cp[0]+3*(1-t)**2*t*cp[1]+3*(1-t)*t*t*cp[2]+t**3*cp[3]
        t=brentq(lambda t:point(t)[1]-y,0,1)
        origin=point(t);tangent=3*(1-t)**2*(cp[1]-cp[0])+6*(1-t)*t*(cp[2]-cp[1])+3*t*t*(cp[3]-cp[2])
        tangent/=np.linalg.norm(tangent)
        xaxis=np.cross(tangent,[0,0,1]);xaxis/=np.linalg.norm(xaxis)
        zaxis=np.cross(xaxis,tangent)
        mat=np.eye(4);mat[:3,:3]=np.column_stack((xaxis,tangent,zaxis));mat[:3,3]=origin
        if sign<0:mat=np.diag([-1,1,-1,1])@mat
        place=matrix_location(mat)
        lower,cap,screws,roots=_row([0.],0.,0.,name)
        lower=place*lower;cap=place*cap;screws=[place*s for s in screws]
        roots=[(sign,tuple((mat@np.array([*p,1]))[:3])) for side,p in roots]
        railx=sign*(width/2-.725);raily=length-(15 if sign<0 and radius>4 else 7)
        section=_common(host,(bd.Pos(sign*width/2,raily,sign*3.5)*bd.Box(width,.02,6.9)))
        assert len(section.solids()),("empty rail section",label,sign)
        bb=section.bounding_box();railx=(bb.min.X+bb.max.X)/2
        rz=(bb.min.Z+bb.max.Z)/2;rh=bb.size.Z+1.1
        shoe,shoe_cap,bolt=_saddle(host,railx,raily,rz,rh,name,bb.size.X)
        start=roots[0][1];end=(railx-sign*.25,raily,rz-rh/2+.14)
        arm=_sweep([start,(start[0]+sign*.25,raily+4 if sign<0 and radius>4 else y-1,z-.5),
                    (railx-sign*1.3,raily,rz-rh/2+.14),end],.25)
        body=_cut(lower.fuse(arm,shoe),host)
        body=body-(place*bd.Cylinder(.47,2,rotation=(90,0,0)))
        body=body-(place*bd.Pos(.98,0,0)*bd.Cylinder(.32,3))
        rail_screw=_bolt(*bolt,1.35,name+'_rail_M0p6_screw')
        cap=_cut(cap,host)
        # Native opposing parts machine their seats in the fused support root.
        for mate in [cap,shoe_cap,*screws,rail_screw]:body=body-mate
        if len(body.solids())!=1:
            print('FIXED_BODY_DIAGNOSTIC',name,[(s.volume,s.is_valid,str(s.bounding_box())) for s in body.solids()],flush=True)
        parts.extend([_finish(body,name+'_structural_jaw'),_finish(cap,name+'_liner_cap'),
                      _finish(shoe_cap,name+'_rail_cap'),*screws,rail_screw])
    return parts


def fixed_phalanx_guide_mounts(finger_names=None):
    from lib.assembly import matrix_location
    parts=[]
    for f in FINGERS:
        if finger_names and f.name not in finger_names:continue
        for i,radius in enumerate((4.5,3.5)):
            frame=f.name+('_mcp_flexion' if i==0 else '_pip')
            place=matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y+sum(f.lengths[:i]),0)
            for p in make_fixed_outlet_pair(f.lengths[i],f.widths[i],radius,f.name+('_pip_drive_guide' if i==0 else '_dip_drive_guide')):
                parts.append((place*p,frame,f.name,'guide_mount'))
    return parts
