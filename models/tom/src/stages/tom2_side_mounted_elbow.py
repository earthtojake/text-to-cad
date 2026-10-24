"""Straight first link, horizontal elbow and a shared shoulder-style wrist yoke.

The link plates seat flush in the rest pose. The wrist uses a positioned copy
of the shoulder yoke; its raised collar carries S6 and the complete gripper.
Production tom2 is unchanged.
"""
from dataclasses import asdict
import build123d as bd
from cadgen import memo
from lib.mates import revolute, fastened
from stages import tom2 as base

from lib.booleans import as_single_shape as one
from lib.tom2_link_profiles import _unify
from hardware.hex_socket_cap import hex_socket_m2x6
from lib.tom2_long_collar import EXTENSION,shared_yoke,filled_upper_link,PITCH

# Return the elbow to production's horizontal case orientation and horn datum.
SHIFT=(0,0,0)
LOWER_EDGE_Z=25.8152
GAUGE=2.032
MOUNTS=[(sign,x,y,z) for sign,x,y in
        ((-1,130.125916240922,-16.5),(1,133.875916240922,15.5))
        for z in (35.38268774003746-EXTENSION,55.88268774003746-EXTENSION)]
# Shared-yoke roll center relative to its pitch center, compared with the old
# wrist yoke. The case and all attached gripper geometry follow this delta.
WRIST_SHIFT=(-1.15-2*EXTENSION,.5,7.3598)
OMIT={f'shoulder_roll_link_plate_pair__hex_socket_m2x6__{n:02d}' for n in (3,4,5,6)}


def downstream_refs(root='#elbow_pitch_yoke'):
    refs={root}
    rows=[asdict(m) for m in base.kinematics()['mates']]
    while True:
        grown=refs|{m['child'] for m in rows if m['parent'] in refs}
        if grown==refs:return refs
        refs=grown


def preview_kinematics():
    data=base.kinematics();refs=downstream_refs('#wrist_yaw_servo');mates=[]
    for m in data['mates']:
        d=asdict(m)
        if d['child'].lstrip('#') in OMIT:continue
        if d['kind']=='revolute':
            if d['name']=='shoulderYaw':delta=(0,0,0)
            elif d['name']=='elbowPitch':delta=(-EXTENSION,0,-EXTENSION)
            elif d['child'] in refs:delta=WRIST_SHIFT
            else:delta=(-EXTENSION,0,0)
            m=revolute(d['name'],parent=d['parent'],child=d['child'],
                origin=[a+b for a,b in zip(d['axis']['origin'],delta)],
                direction=d['axis']['dir'],limits=d['limits']['value'])
        mates.append(m)
    for i in range(1,5):
        mates.append(fastened(f'elbow_side_mount_{i}',parent='#shoulder_pitch_yoke',
                     child=f'#elbow_side_m2x6_{i}'))
    return dict(mates=mates,poses=data['poses'])


def straight_link(node):
    """Keep roof/root stock, replace the taper with two straight side flats."""
    body=one(node)
    tangent=body.bounding_box().max.Z-2.9972
    cutters=[];panels=[]
    for sign,x,y,margin in ((-1,130.125916240922,-16.5,2.15),(1,133.875916240922,15.5,2.65)):
        end_x=x+margin
        # A shared exact tangent closes the former 10-nanometre seam.
        cutters.append(base.box(110,180,min(y,y+sign*GAUGE)-.001,
                     max(y,y+sign*GAUGE)+.001,LOWER_EDGE_Z-1,tangent))
        # Preserve a continuous straight connection edge with the original
        # small corner rounds, rather than separate semicircular screw ears.
        profile=bd.Face(bd.Wire.make_polygon([
            (20,y,LOWER_EDGE_Z),(end_x,y,LOWER_EDGE_Z),
            (end_x,y,tangent),(20,y,tangent)],close=True))
        corners=[v for v in profile.vertices() if abs(v.center().X-end_x)<1e-6]
        profile=profile.fillet_2d(1.0,corners)
        panels.append(bd.Solid.extrude(profile,(0,sign*GAUGE,0)))
    result=one(body.cut(*cutters))
    result=one(result.fuse(*panels)).clean()
    bores=[bd.Solid.make_cylinder(1.1,GAUGE+.02,
           bd.Plane(origin=(x,y-sign*.01,z),z_dir=(0,sign,0)))
           for sign,x,y,z in MOUNTS]
    result=_unify(one(result.cut(*bores)).clean())
    assert result.is_valid and len(result.solids())==1
    result.label=node.label;result.color=node.color
    return result


def wrist_yoke_copy(source):
    data={m.name:asdict(m) for m in base.kinematics()['mates']}
    shoulder=data['shoulderPitch']['axis']['origin']
    wrist=data['wristPitch']['axis']['origin']
    pivot=(shoulder[0],0,shoulder[2])
    copy=source.rotate(bd.Axis(pivot,(0,0,1)),180).moved(
        bd.Pos(wrist[0]-shoulder[0],0,wrist[2]-shoulder[2]))
    copy.label='temporary_wrist_yoke'
    return copy.moved(bd.Pos(-EXTENSION,0,0))


def visit(node,refs,replacements):
    if node.label in OMIT:return None
    if node.label in replacements:return replacements[node.label]
    grounded={'direct_servo_clamp','shoulder_yaw_servo','m8_thumbscrew','clamp_mounting_hardware'}
    if node.label in grounded or node.label.startswith('shoulder_yaw_yoke__hex_socket_m3') or node.label=='shoulder_yaw__hex_socket_m3x5__center':return node
    if '#'+node.label in refs or node.label.startswith('wrist_yaw_m3x5_'):
        return node.moved(bd.Pos(*WRIST_SHIFT))
    if node.label.startswith('temporary_wrist_m3x5_'):
        i=int(node.label.rsplit('_',1)[1])-1;sign=(-1,1)[i//3]
        dx,dz=((-7,0),(0,-7),(7,0))[i%3]
        axis=next(asdict(m)['axis']['origin'] for m in base.kinematics()['mates'] if m.name=='wristPitch')
        return base.screw(base.hex_socket_m3x5(),node.label,
            (axis[0]+dx-EXTENSION,sign*(18.3+GAUGE),axis[2]+dz),sign)
    if node.label=='elbow_pitch_servo':return node.moved(bd.Pos(-EXTENSION,0,-EXTENSION))
    if node.label.startswith('integrated_elbow_horn_m3x5_'):
        i=int(node.label.rsplit('_',1)[1]);pitch=i in (1,2,3,7,8,9)
        return node.moved(bd.Pos(-EXTENSION,0,-EXTENSION if pitch else 0))
    if node.label=='elbow_pitch__hex_socket_m3x5__center':
        return node.moved(bd.Pos(-EXTENSION,0,-EXTENSION))
    if node.children:
        loc=node.location;children=list(node.children);node.children=()
        kept=[q for c in children if (q:=visit(c,refs,replacements)) is not None]
        if not kept:return None
        return bd.Compound(children=kept,label=node.label,color=node.color).moved(loc)
    return node.moved(bd.Pos(-EXTENSION,0,0))


@memo
def tom2_side_mounted_elbow():
    source=base.tom2();refs=downstream_refs('#wrist_yaw_servo')
    children=list(source.children);source.children=()
    by={p.label:p for p in children}
    common=shared_yoke(by['shoulder_yaw_yoke'])
    shoulder=common.moved(bd.Pos(-EXTENSION,0,0));shoulder.label='shoulder_yaw_yoke'
    elbow=common.rotate(bd.Axis(PITCH,(0,1,0)),-90).moved(
        bd.Pos(162.875916240922-PITCH[0]-EXTENSION,0,45.63268774003746-PITCH[2]-EXTENSION))
    elbow.label='elbow_pitch_yoke'
    wrist=wrist_yoke_copy(common)
    lower=straight_link(by['shoulder_pitch_yoke']).moved(bd.Pos(-EXTENSION,0,0))
    upper=filled_upper_link(by['elbow_roll_link_plate_pair']).moved(bd.Pos(-EXTENSION,0,0))
    replacements={p.label:p for p in (shoulder,elbow,wrist,lower,upper)}
    updated=[q for p in children if (q:=visit(p,refs,replacements)) is not None]
    m2=hex_socket_m2x6()
    updated += [base.screw(m2,f'elbow_side_m2x6_{i}',
                  (x-EXTENSION,y+sign*GAUGE,z),sign)
                for i,(sign,x,y,z) in enumerate(MOUNTS,1)]
    return bd.Compound(children=updated,label='tom2_side_mounted_elbow')
