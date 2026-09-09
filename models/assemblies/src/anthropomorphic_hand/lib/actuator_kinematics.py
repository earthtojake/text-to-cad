"""Physical actuator transforms, independent of any animation timing.

The fixed-ring 12/12/36 planetary reducer has sun/carrier ratio4. A planet
orbits with the carrier and spins at-2 times the carrier rate in world axes.
All angles here are radians about the actuator's authored local positive Z.
"""
import math
import numpy as np

OUTPUT_ROLES={'gearbox_carrier','gearbox_spindle','capstan','terminal_ferrule',
              'capstan_terminal_bond_line','capstan_retainer_screw'}
INPUT_ROLES={'gearbox_sun','motor_shaft'}

def translation(point):
    result=np.eye(4);result[:3,3]=point;return result

def rotation(q):
    c,s=math.cos(q),math.sin(q)
    return np.array([[c,-s,0.,0.],[s,c,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]])

def actuator_transform(tendon,role,q):
    """Return an assembled-space displacement, or None for fixed hardware."""
    if role in OUTPUT_ROLES or role.startswith('gearbox_planet_pin_'):
        local=rotation(q)
    elif role in INPUT_ROLES:local=rotation(4*q)
    elif role.startswith('gearbox_planet_'):
        index=int(role.rsplit('_',1)[1])-1;assert 0<=index<3
        angle=index*2*math.pi/3;center=np.array([3*math.cos(angle),3*math.sin(angle),0.])
        local=rotation(q)@translation(center)@rotation(-3*q)@translation(-center)
    else:return None
    placement=translation([*tendon['actuator_center'][:2],tendon['sign']*4.])
    placement[:3,:3]=np.diag([tendon['sign'],1.,tendon['sign']])
    return placement@local@np.linalg.inv(placement)

def body_actuator_motion(body_name,tendons,angles):
    for tendon in tendons:
        prefix=tendon['actuator']+'_'
        if body_name.startswith(prefix):
            return actuator_transform(tendon,body_name[len(prefix):],angles[tendon['name']])
    return None

def apply_actuator_motion(bodies,tendons,angles,*,cache_aliases=False):
    """Move exported rigid solids without editing their neutral definitions.

Cache aliases distinguish a body's exact payout geometry for the route/solid
validator, whose static body cache otherwise keys on name and path alone.
"""
    from cadgen import build123d as bd
    from lib.assembly import Body,matrix_location
    moved=[];aliases={};active=set()
    for body in bodies:
        transform=body_actuator_motion(body.name,tendons,angles)
        if transform is None:moved.append(body);continue
        assert body.frame=='forearm',body.name
        tendon=next(t for t in tendons if body.name.startswith(t['actuator']+'_'))
        q=angles[tendon['name']]
        shape=bd.Compound.cast(body.shape.wrapped.Moved(matrix_location(transform).wrapped)).solids()[0]
        name=body.name+(f'__payout_{float(q).hex()}' if cache_aliases else '')
        shape.label=name;shape.color=body.shape.color
        if getattr(body.shape,'cad_material',None):shape.cad_material=body.shape.cad_material
        moved.append(Body(shape,body.frame,body.system,body.kind));aliases[name]=body.name
        if q!=0.:active.add(name)
    return moved,aliases,active
