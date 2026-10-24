"""Compact reach study with extended upper link and registered truss windows.

Preserve mounting ends, cross sections, bend radii, rest heights and hardware.
The original symmetric-yoke model remains the comparison configuration.
"""
from dataclasses import asdict
from functools import cache
import build123d as bd
from lib.mates import revolute
from stages.tom2_symmetric_yokes import tom2_symmetric_yokes,kinematics as original_kinematics
from lib.booleans import as_single_shape
from lib.tom2_link_profiles import _unify
from lib.link_truss import finish_link
from lib.upper_link_overhang import UPPER_EXTENSION,WRIST_DROP,refine_upper_link

LOWER_SHORTEN=50.0
UPPER_SHORTEN=50.0-UPPER_EXTENSION
CUT_X=50.0

@cache
def descendants(root):
    result={root}
    while True:
        grown=result|{m.child for m in original_kinematics()['mates'] if m.parent in result}
        if grown==result:return result
        result=grown

@cache
def moving_sets():
    elbow=descendants('#elbow_pitch_yoke')|descendants('#elbow_pitch_servo')
    elbow|={f'#elbow_side_m2x6_{i}' for i in range(1,5)}
    wrist=descendants('#temporary_wrist_yoke')|descendants('#wrist_pitch_servo')
    wrist|={f'#elbow_roll_link_plate_pair__hex_socket_m2x6__{i:02d}' for i in (3,4,5,6)}
    return elbow,wrist

def offset(label,groups,inherited=0.0):
    key='#'+label
    if key in groups[0] or key in groups[1]:
        return (-LOWER_SHORTEN if key in groups[0] else 0)+(UPPER_SHORTEN if key in groups[1] else 0)
    return inherited

def shortened(part,amount,move_left):
    left=as_single_shape(part.intersect(bd.Solid.make_box(CUT_X+500,1000,1000,bd.Plane(origin=(-500,-500,-500)))))
    right=as_single_shape(part.intersect(bd.Solid.make_box(500-CUT_X-amount,1000,1000,bd.Plane(origin=(CUT_X+amount,-500,-500)))))
    if move_left:left=left.moved(bd.Pos(amount,0,0))
    else:right=right.moved(bd.Pos(-amount,0,0))
    result=_unify(as_single_shape(left.fuse(right)).clean())
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result

@cache
def kinematics():
    data=original_kinematics();groups=moving_sets();mates=[]
    for m in data['mates']:
        row=asdict(m)
        if row['kind']=='revolute':
            xyz=list(row['axis']['origin']);xyz[0]+=offset(m.child.lstrip('#'),groups)
            if m.child in groups[1]:xyz[2]-=WRIST_DROP
            m=revolute(m.name,parent=m.parent,child=m.child,origin=xyz,direction=row['axis']['dir'],limits=row['limits']['value'])
        mates.append(m)
    return dict(mates=mates,poses=data['poses'])

def build_model(finisher=finish_link):
    source=tom2_symmetric_yokes();groups=moving_sets()
    def visit(p,inherited=0.0,inherited_z=0.0):
        dx=offset(p.label,groups,inherited)
        dz=-WRIST_DROP if '#'+p.label in groups[1] else inherited_z
        if p.label=='shoulder_pitch_yoke':return finisher(shortened(p,LOWER_SHORTEN,False),False)
        if p.label=='elbow_roll_link_plate_pair':
            plate=shortened(p,UPPER_SHORTEN,True).moved(bd.Pos(-LOWER_SHORTEN,0,0))
            return finisher(refine_upper_link(plate),True)
        if p.label in {'shoulder_yaw_servo','shoulder_pitch_servo','elbow_pitch_servo','elbow_roll_servo','wrist_pitch_servo','wrist_yaw_servo','gripper_jaw_servo'}:
            return p.moved(bd.Pos(dx,0,dz))
        if p.children:
            loc=p.location;children=list(p.children);p.children=()
            return bd.Compound(children=[visit(c,dx,dz) for c in children],label=p.label,color=p.color).moved(loc)
        return p.moved(bd.Pos(dx,0,dz))
    result=visit(source);result.label='tom2_500mm';return result

def tom2_500mm():
    return build_model()
