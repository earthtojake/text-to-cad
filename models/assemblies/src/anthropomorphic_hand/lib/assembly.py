"""Named assembly occurrences and authored kinematic attachment frames.

This registry is shared by static collision audits and the eventual render
module data export. It currently represents an integration study; completeness
is asserted separately before the hand is eligible for final acceptance.
"""
from dataclasses import dataclass
from cadgen import build123d as bd
from lib.layout import FINGERS, JOINTS, THUMB_CMC, THUMB_LENGTHS, THUMB_DIRECTION, TENDONS, assembled_transforms, finger_fan_matrix, drive_pulley_offset
from lib.phalanx import make_phalanx
from lib.pulley import make_pulley
from lib.palm_frame import make_palm_frame, make_palm_frame_bodies, make_little_metacarpal
from lib.universal_carrier import make_universal_carrier
from lib.motor import make_motor_case, make_motor_endcap, make_motor_shaft
from lib.thumb_metacarpal import make_thumb_metacarpal
from lib.gearbox import make_gearbox_parts
from lib.capstan import make_capstan, make_terminal_ferrule
from lib.wrist import make_wrist_fixed_fork,make_wrist_yaw_carrier,make_wrist_palm_cradle,make_wrist_bushings
from lib.tension_cartridge import make_tension_cartridge


@dataclass
class Body:
    shape: object
    frame: str
    system: str
    kind: str
    @property
    def name(self): return self.shape.label


def matrix_location(matrix):
    from OCP.gp import gp_Trsf
    t=gp_Trsf()
    t.SetValues(*[float(matrix[i,j]) for i in range(3) for j in range(4)])
    return bd.Location(t)


def joint_location(joint):
    radial=(THUMB_DIRECTION if joint.system=='thumb' else
            (1.,0.,0.) if joint.name in ('palm_cup','wrist_abduction') else (0.,1.,0.))
    return bd.Plane(origin=joint.origin,x_dir=radial,z_dir=joint.axis).location


def integration_bodies(palm_baseline=False):
    bodies=[]
    def add(shape,frame,system,kind): bodies.append(Body(shape,frame,system,kind))
    if palm_baseline:
        from cadgen import read_step
        from pathlib import Path
        source=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand/palm_frame_review.step'
        def leaves(node):
            if node.label=='fifth_metacarpal_cupping_truss':return []
            return [leaf for child in node.children for leaf in leaves(child)] if node.children else [node]
        main_parts=leaves(read_step(source))
    else:main_parts=make_palm_frame_bodies()
    for part in main_parts:
        kind='fastener' if 'screw' in part.label or 'washer' in part.label else 'frame'
        add(part,'wrist_flexion','palm',kind)
    from cadgen import read_step
    from pathlib import Path
    little_source=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand/palm_little_review.step'
    little_parts=list(read_step(little_source).children)
    if len(little_parts)!=1:raise ValueError('Expected one validated fifth-metacarpal body')
    add(little_parts[0],'palm_cup','palm','frame')
    add(make_wrist_fixed_fork(),'forearm','wrist','frame')
    add(make_wrist_yaw_carrier(),'wrist_abduction','wrist','frame')
    add(make_wrist_palm_cradle(),'wrist_flexion','wrist','frame')
    for frame,shape in make_wrist_bushings():
        add(shape,'forearm' if frame=='fixed' else 'wrist_abduction','wrist','bushing')
    for finger in FINGERS:
        y=finger.base_y
        for i,(length,width) in enumerate(zip(finger.lengths,finger.widths)):
            role=('proximal','middle','distal')[i]
            frame=f'{finger.name}_{("mcp_flexion","pip","dip")[i]}'
            part=make_phalanx(length,width,distal=i==2,label=f'{finger.name}_{role}_frame')
            add(bd.Pos(finger.x,y,0)*part,frame,finger.name,'phalanx')
            y+=length
        carrier=make_universal_carrier(phalanx_width=finger.widths[0],yaw_plane=8.,label=f'{finger.name}_mcp_carrier')
        add(bd.Pos(finger.x,finger.base_y,0)*carrier,f'{finger.name}_mcp_abduction',finger.name,'carrier')
    station=0.
    for i,(length,width) in enumerate(zip(THUMB_LENGTHS,(19.,16.,13.))):
        role=('metacarpal','proximal','distal')[i]
        frame=f'thumb_{("cmc_flexion","mcp_flexion","ip")[i]}'
        p=(make_thumb_metacarpal(label='thumb_metacarpal_frame') if i==0 else
           make_phalanx(length,width,distal=i==2,label=f'thumb_{role}_frame'))
        add(bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*bd.Pos(0,station,0)*p,frame,'thumb','phalanx')
        if i<2:
            joint=('cmc','mcp')[i]
            p=make_universal_carrier(phalanx_width=width,yaw_plane=9.5 if i==0 else 8.,label=f'thumb_{joint}_carrier')
            add(bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*bd.Pos(0,station,0)*p,f'thumb_{joint}_abduction','thumb','carrier')
        station+=length
    # Build each expensive actuator prototype once, then place independent,
    # named occurrences. Shared topology keeps the complete STEP manageable.
    motor_prototypes=[(role,factory(label='motor_'+role)) for role,factory in
                      (('case',make_motor_case),('endcap',make_motor_endcap),('shaft',make_motor_shaft))]
    gearbox_prototypes=make_gearbox_parts(prefix='gearbox')
    capstan_prototype=make_capstan()
    ferrule_prototype=make_terminal_ferrule()
    cartridge_prototypes=make_tension_cartridge()
    for tendon in TENDONS:
        x,y,_=tendon['actuator_center']; sign=tendon['sign']
        placement=bd.Pos(x,y,sign*4.)*(bd.Rot(0,0,0) if sign==1 else bd.Rot(0,180,0))
        cartridge_placement=bd.Pos(x,y,0)*(bd.Rot(0,0,0) if sign==1 else bd.Rot(0,180,0))
        for prototype in cartridge_prototypes:
            p=cartridge_placement*prototype;p.label=f'{tendon["actuator"]}_{prototype.label}'
            add(p,'forearm','forearm','tension_cartridge')
        for role,prototype in motor_prototypes:
            p=placement*prototype; p.label=f'{tendon["actuator"]}_motor_{role}'
            add(p,'forearm','forearm',f'motor_{role}')
        for prototype in gearbox_prototypes:
            p=placement*prototype; p.label=f'{tendon["actuator"]}_{prototype.label}'
            add(p,'forearm','forearm',prototype.label)
        for role,prototype in (('capstan',capstan_prototype),('terminal_ferrule',ferrule_prototype)):
            p=placement*bd.Pos(0,0,29)*prototype; p.label=f'{tendon["actuator"]}_{role}'
            add(p,'forearm','forearm',role)
    names=[b.name for b in bodies]
    if len(names)!=len(set(names)): raise ValueError('Assembly body labels must be unique')
    fan_locations={f.name:matrix_location(finger_fan_matrix(f)) for f in FINGERS}
    for body in bodies:
        if body.system in fan_locations:body.shape=fan_locations[body.system]*body.shape
    # These mount factories already return assembled, fanned geometry.
    from cadgen import read_step
    from pathlib import Path
    guide_source=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand/phalanx_guide_mounts_review.step'
    def guide_leaves(node):
        return [leaf for child in node.children for leaf in guide_leaves(child)] if node.children else [node]
    guide_parts=guide_leaves(read_step(guide_source))
    if len(guide_parts)!=112:raise ValueError('Expected112 separately captured finger guide-mount bodies')
    for shape in guide_parts:
        system=next(f.name for f in FINGERS if shape.label.startswith(f.name+'_'))
        frame=system+('_pip' if '_pip_outlet_' in shape.label else '_mcp_flexion')
        add(shape,frame,system,'guide_mount')
    forearm_source=Path(__file__).resolve().parents[3]/'STEP/anthropomorphic_hand/forearm_mount_system_review.step'
    forearm_parts=guide_leaves(read_step(forearm_source))
    if len(forearm_parts)!=110:raise ValueError('Expected110 validated forearm frame and guide bodies')
    for shape in forearm_parts:
        add(shape,'forearm','forearm','guide_mount' if any(k in shape.label for k in ('jaw','comb','guide','screw','bridge','portal')) else 'frame')
    step_root=forearm_source.parent
    hardware_parts=guide_leaves(read_step(step_root/'joint_hardware_review.step'))
    if len(hardware_parts)!=104:raise ValueError('Expected104 validated shaft, bearing and retaining-ring bodies')
    for shape in hardware_parts:
        joint=next(j for j in JOINTS if shape.label.startswith(j.name+'_'))
        kind='bushing' if shape.label.endswith('_bushing') else 'retaining_ring' if shape.label.endswith('_retaining_ring') else 'shaft'
        add(shape,joint.parent if kind=='bushing' else joint.name,joint.system,kind)
    for filename,count in [('palm_guide_mounts_review.step',67),('thumb_cmc_mounts_review.step',24),('fixed_outlet_mounts_review.step',80),('actuator_fasteners_review.step',824),('yaw_reaction_mounts_review.step',64),('forearm_housing_review.step',42),('thumb_downstream_mounts_review.step',42),('wrist_guide_mounts_review.step',30)]:
        parts=guide_leaves(read_step(step_root/filename))
        if len(parts)!=count:raise ValueError(f'{filename}: expected {count} validated bodies, found {len(parts)}')
        for shape in parts:
            if filename.startswith('palm_'):frame,system='wrist_flexion','palm'
            elif filename.startswith('thumb_downstream_'):
                system='thumb'
                frame='thumb_cmc_flexion' if shape.label.startswith('thumb_metacarpal') else 'thumb_mcp_flexion' if shape.label.startswith(('thumb_mcp_ip_outlet','thumb_ip_drive_guide')) else 'thumb_mcp_abduction'
            elif filename.startswith('wrist_guide_'):
                system='wrist' if shape.label.startswith('wrist_') else 'palm'
                frame='forearm' if shape.label.startswith('wrist_abduction') else 'wrist_abduction' if shape.label.startswith('wrist_flexion') else 'wrist_flexion'
            elif filename.startswith('thumb_'):frame,system=('wrist_flexion' if 'parent' in shape.label else 'thumb_cmc_flexion'),'thumb'
            elif filename.startswith('fixed_'):
                system=next(f.name for f in FINGERS if shape.label.startswith(f.name+'_'))
                frame=system+('_mcp_flexion' if '_pip_drive_guide_' in shape.label else '_pip')
            elif filename.startswith('yaw_'):
                system=next(f.name for f in FINGERS if shape.label.startswith(f.name+'_'))
                frame=system+'_mcp_abduction'
            else:frame,system='forearm','forearm'
            kind='fastener' if any(k in shape.label for k in ('screw','nut','insert','washer','shim')) else 'guide_mount'
            add(shape,frame,system,kind)
    from lib.fingernail import fingernail_bodies
    for shape,frame,system,kind in fingernail_bodies():add(shape,frame,system,kind)
    from lib.fingertip_pad import fingertip_pad_bodies
    for shape,frame,system,kind in fingertip_pad_bodies():add(shape,frame,system,kind)
    drive_parts=guide_leaves(read_step(step_root/'drive_terminal_placements.step'))
    if len(drive_parts)!=336:raise ValueError(f'Expected336 driven terminal and capstan bond bodies, found{len(drive_parts)}')
    for shape in drive_parts:
        if shape.label.endswith('_capstan_terminal_bond_line'):
            add(shape,'forearm','forearm','capstan_terminal_bond_line');continue
        tendon=next(t for t in TENDONS if shape.label.startswith(t['name']+'_'))
        kind=shape.label[len(tendon['name'])+1:]
        joint=next(j for j in JOINTS if j.name==tendon['joint'])
        add(shape,joint.name,joint.system,kind)
    names=[b.name for b in bodies]
    if len(names)!=len(set(names)):raise ValueError('Assembly occurrence labels must remain unique after guide/frame imports')
    # STEP carries source colors; restore distinct physical finishes when
    # an imported occurrence does not carry its original PBR metadata.
    from cadgen import srgb
    from lib.finish import FINISHES
    palette=[(tuple(srgb(color))[:3],material) for color,material in FINISHES.values()]
    for body in bodies:
        if not getattr(body.shape,'cad_material',None):
            color=getattr(body.shape,'color',None)
            rgb=tuple(color)[:3] if color is not None else palette[0][0]
            body.shape.cad_material=dict(min(palette,key=lambda entry:sum((a-b)**2 for a,b in zip(rgb,entry[0])))[1])
    return bodies


def posed_bodies(bodies,pose):
    fk=assembled_transforms(pose)
    placed=[]
    for body in bodies:
        # Native locations share immutable topology; Python multiplication
        # deep-copies every detailed prototype at every sweep pose.
        shape=bd.Compound.cast(body.shape.wrapped.Moved(matrix_location(fk[body.frame]).wrapped))
        shape.label=body.name
        shape.color=body.shape.color
        if getattr(body.shape,'cad_material',None):shape.cad_material=body.shape.cad_material
        placed.append(Body(shape,body.frame,body.system,body.kind))
    return placed


def compound(bodies,label='anthropomorphic_hand_integration_study'):
    return bd.Compound(label=label,children=[b.shape for b in bodies])
