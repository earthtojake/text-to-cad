"""3.175 mm base pair and one M3 screw length for the current arm.

The thin moving jaw uses six 1.5 mm rigid spacers, ID3.2/OD6, under
the heads. These are nominal procurement envelopes, not a matched SKU:
STEP Parts searches for M3 spacers, washers and 1.5 mm spacers found no
matching narrow 1.5 mm spacer. Do not substitute spring washers.
"""
from dataclasses import asdict, replace
import build123d as b
from lib.mates import fastened, revolute
from lib.restored_base_plate import THICKNESS
from lib.tapered_solid_links import finish

BASE_DELTA=THICKNESS-2.0
ARM_RISE=2*BASE_DELTA
GRIPPER_SPACER=1.5
GRIPPER_SCREWS=tuple(f'gripper_right_claw__hex_socket_m3x5__{i:02}' for i in range(1,7))
PLATE_NAMES={'servo_carrier_5052_2mm':'servo_carrier_5052_3p175mm',
             'flat_base_foot_5052_2mm':'flat_base_foot_5052_3p175mm'}

def rename(n):
    return PLATE_NAMES.get(n,n.replace('m3x5','m3x6'))

def revised_kinematics(data):
    mates=[]
    for m in data['mates']:
        r=asdict(m)
        parent='#'+rename(m.parent.lstrip('#'));child='#'+rename(m.child.lstrip('#'))
        if r['kind']=='revolute':
            xyz=list(r['axis']['origin']);xyz[2]+=ARM_RISE
            m=revolute(m.name,parent=parent,child=child,origin=xyz,
                       direction=r['axis']['dir'],limits=r['limits']['value'])
        else:m=replace(m,parent=parent,child=child)
        mates.append(m)
    for i,n in enumerate(GRIPPER_SCREWS,1):
        mates.append(fastened(f'gripper_spacer_{i}',parent='#'+rename(n),child=f'#gripper_m3_spacer_1p5mm_{i}'))
    return data|{'mates':mates}

def bearing(p,radius=1.5,head_radius=2.75):
    for f in p.faces():
        if f.geom_type!=b.GeomType.PLANE:continue
        circles=[e for e in f.edges() if e.geom_type==b.GeomType.CIRCLE]
        if len(circles)!=2:continue
        if sorted(round(e.radius,5) for e in circles)==[radius,head_radius]:
            return next(e.arc_center for e in circles if abs(e.radius-head_radius)<1e-5),-f.normal_at()
    raise ValueError(f'No screw bearing face: {p.label}')

def grow_screw(p,old_length,diameter,head_radius):
    c,out=bearing(p,diameter/2,head_radius)
    ext=b.Solid.make_cylinder(diameter/2,6-old_length+.01,
                             b.Plane(origin=c-out*6,z_dir=out))
    return finish(p.fuse(ext),p),c,out
