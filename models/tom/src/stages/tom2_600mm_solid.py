"""~570 mm gripper-tip radial reach, solid tapered links and stiff fixed clamp.

The shoulder->elbow channel drops the extra Howe bay at its shoulder end, so
both links carry the same 4-bay pattern; everything past that bay moves back
one pitch. The final solid profiles retain those joint locations and use a
shared taper angle. Sizing: analysis/tom2/link-length-payload.
"""
from dataclasses import asdict
from functools import cache
from pathlib import Path
import build123d as bd
from cadgen import read_step
from lib.mates import revolute, fastened
from stages.tom2_500mm import build_model,moving_sets,kinematics as previous_kinematics
from lib.reach600_geometry import LINK_EXTENSION,finish_extended_link
from lib.howe_link_pattern import PITCH as BAY_PITCH,ORIGIN as BAY_ORIGIN
from lib.booleans import as_single_shape as one
from lib.tom2_link_profiles import _unify
from lib import base_direct_clamp as bay
# Finish the accepted gripper in its established datum, then lower the
# complete moving assembly once. This keeps its geometry identical.
BUILD_ARM_RISE = bay.LEGACY_SERVO_PAD - 13.175
from lib.straight_gripper import make_straight_gripper,AXIS_XY,HORN_PATTERN_TURN
from lib.gripper_063 import THICKNESS as GRIPPER_T
from lib.gripper_mount_finish import narrow_camera_support, underside_mounting_prong
from lib.elbow_roll_alignment import ROLL_RISE as LEGACY_ROLL_RISE,CASE_EDGE_ALIGNMENT_EXTRA,align_elbow_roll
from lib.tapered_solid_links import apply_tapered_links,COMPACT_DROP,REMOVED_SHOULDER_SCREWS,WRIST_INSET,LINK_TRANSFER
ROLL_RISE = LEGACY_ROLL_RISE - COMPACT_DROP
WRIST_SHIFT = -COMPACT_DROP + CASE_EDGE_ALIGNMENT_EXTRA

# Orthogonal, fully unfolded preset: both channel webs are horizontal.
REACH_POSE={'shoulderYaw': 0.0, 'shoulderPitch': -180.0, 'elbowPitch': 180.0, 'elbowRoll': 0.0, 'wristPitch': 0.0, 'wristYaw': 0.0, 'gripperJaw': 0}
ZERO_POSE=REACH_POSE|{'shoulderPitch':-90.0}
PACKED_POSE=REACH_POSE|{'elbowPitch':0.0,'wristPitch':90.0}

# One Howe bay out of the shoulder->elbow channel: the extra bay at its
# shoulder end (index -1 in howe_link_pattern), leaving the forearm's pattern.
SHOULDER_LINK_CUT=BAY_PITCH

def extension_offset(label,inherited=0):
    elbow,wrist=moving_sets();key='#'+label
    if key in wrist:return 0.
    if key in elbow:return LINK_EXTENSION
    return inherited

def is_distal(label):
    """Carried past the shoulder link's elbow end: the elbow servo case, its screws and everything beyond."""
    elbow,wrist=moving_sets();key='#'+label
    return key in elbow or key in wrist

def drop_shoulder_bay(part):
    # Both cut planes fall in solid full-section webs (the shoulder land and
    # the node between bays -1 and 0), so the two pieces close up flush.
    x0,x1=BAY_ORIGIN-SHOULDER_LINK_CUT,BAY_ORIGIN
    left=one(part.intersect(bd.Solid.make_box(x0+500,1000,1000,bd.Plane(origin=(-500,-500,-500)))))
    right=one(part.intersect(bd.Solid.make_box(500-x1,1000,1000,bd.Plane(origin=(x1,-500,-500)))))
    result=_unify(one(left.fuse(right.moved(bd.Pos(-SHOULDER_LINK_CUT,0,0)))).clean())
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result

def finish_links(part,upper):
    finished=finish_extended_link(part,upper)
    return finished if upper else drop_shoulder_bay(finished)

@cache
def kinematics():
    data=previous_kinematics();mates=[]
    for m in data['mates']:
        if m.child.lstrip('#') in REMOVED_SHOULDER_SCREWS:continue
        r=asdict(m)
        if m.name=='base_case_grounded':
            m=fastened(m.name,parent='#servo_carrier_5052_2mm',child=m.child)
        if r['kind']=='revolute':
            child=m.child.lstrip('#')
            xyz=list(r['axis']['origin']);xyz[0]+=extension_offset(child)-SHOULDER_LINK_CUT*is_distal(child)+bay.SERVO_SHIFT_X;xyz[2]+=bay.ARM_RISE
            if m.name in ('elbowPitch','elbowRoll'):
                xyz[2]+=ROLL_RISE
                xyz[0]+=LINK_TRANSFER
            if m.name in ('wristPitch','wristYaw','gripperJaw'):
                xyz[2]+=WRIST_SHIFT
                xyz[0]+=WRIST_INSET+2*LINK_TRANSFER
            m=revolute(m.name,parent=m.parent,child=m.child,origin=xyz,direction=r['axis']['dir'],limits=r['limits']['value'])
            if m.name=='wristPitch':
                m=revolute(m.name,parent=m.parent,child=m.child,origin=xyz,direction=r['axis']['dir'],limits=(-97,90))
        mates.append(m)
    mates.append(fastened('fixed_electronics_bay',parent='#direct_servo_clamp',child='#fixed_electronics_bay'))
    return dict(mates=mates,poses={'zero':ZERO_POSE,'rest':{},'reach':REACH_POSE,'packed':PACKED_POSE})

def tom2_600mm_solid():
    source=build_model(finisher=finish_links)
    print('600 mm: source geometry ready',flush=True)
    def visit(p,inherited=0.):
        dx=extension_offset(p.label,inherited)
        if p.label=='direct_servo_clamp':return bay.clamp()
        if p.label=='m8_thumbscrew':return p.moved(bd.Pos(bay.CLAMP_SCREW_X+17.5,0,bay.THUMB_SHIFT_Z))
        if p.label.startswith('clamp_standoff_screw_'):
            return bay.servo_screw(int(p.label.rsplit('_',1)[1]))
        if p.label in {'shoulder_pitch_yoke','elbow_roll_link_plate_pair'}:return p.moved(bd.Pos(0,0,BUILD_ARM_RISE))
        if p.label.endswith('_servo'):return p.moved(bd.Pos(dx,0,BUILD_ARM_RISE))
        if p.children:
            loc=p.location;cs=list(p.children);p.children=()
            return bd.Compound(children=[visit(c,dx) for c in cs if not c.label.startswith('servo_standoff_') and c.label not in REMOVED_SHOULDER_SCREWS],label=p.label,color=p.color).moved(loc)
        return p.moved(bd.Pos(dx,0,BUILD_ARM_RISE))
    result=visit(source)
    print('600 mm: base placements ready',flush=True)
    world={}
    def gather(p,ancestor=None):
        if ancestor is None:ancestor=bd.Location()
        if p.label in ('servo6_fixed_gripper_frame','gripper_right_claw','wrist_camera_payload'):
            q=bd.Compound.cast(p.wrapped).moved(ancestor);q.label=p.label;q.color=p.color;world[p.label]=q
        for c in p.children:gather(c,ancestor*p.location)
    gather(result)
    fixed,moving,phase,camera=make_straight_gripper(world['servo6_fixed_gripper_frame'],world['gripper_right_claw'])
    fixed=underside_mounting_prong(narrow_camera_support(fixed))
    replacements={p.label:p for p in (fixed,moving,camera)}
    axis=bd.Axis((*AXIS_XY,0),(0,0,1))
    def revise(p,ancestor=None):
        if ancestor is None:ancestor=bd.Location()
        if p.label in replacements:return replacements[p.label].moved(ancestor.inverse())
        if p.label in ('inline_jaw_drive_horn','inline_jaw_idler_horn') or p.label.startswith('gripper_right_claw__'):
            turn=phase+(HORN_PATTERN_TURN if p.label.startswith('gripper_right_claw__') else 0)
            q=bd.Compound.cast(p.wrapped).moved(ancestor).rotate(axis,turn)
            if p.label.startswith('gripper_right_claw__'):
                dz=(GRIPPER_T-2.032)*(1 if q.bounding_box().center().Z>142.9299110455 else -1)
                q=q.moved(bd.Pos(0,0,dz))
            q=q.moved(ancestor.inverse());q.label=p.label;q.color=p.color;return q
        if p.label in {'gripper_frame__hex_socket_m2x6__01','gripper_frame__hex_socket_m2x6__02',
                       'gripper_frame__hex_socket_m2x6__06','gripper_frame__hex_socket_m2x6__07',
                       'gripper_left_claw__hex_socket_m2x6__01',
                       'servo6_case_m2x6_13','servo6_case_m2x6_14','servo6_case_m2x6_15','servo6_case_m2x6_16'}:
            q=bd.Compound.cast(p.wrapped).moved(ancestor)
            dz=(GRIPPER_T-2.032)*(1 if q.bounding_box().center().Z>142.9299110455 else -1)
            q=q.moved(bd.Pos(0,0,dz)).moved(ancestor.inverse());q.label=p.label;q.color=p.color;return q
        if p.children:return bd.Compound(children=[revise(c,ancestor*p.location) for c in p.children],label=p.label,color=p.color).moved(p.location)
        return p
    result=revise(result)
    print('600 mm: gripper refinement ready',flush=True)
    # Close up the dropped bay only now: the gripper above is finished
    # against absolute datums (AXIS_XY) at its established position.
    distal=set().union(*moving_sets())
    def shorten(p,ancestor=None):
        if ancestor is None:ancestor=bd.Location()
        if '#'+p.label in distal:
            return p.moved(ancestor.inverse()*bd.Pos(-SHOULDER_LINK_CUT,0,0)*ancestor)
        if p.children:return bd.Compound(children=[shorten(c,ancestor*p.location) for c in p.children],label=p.label,color=p.color).moved(p.location)
        return p
    result=shorten(result)
    fixed_labels={'direct_servo_clamp','m8_thumbscrew','clamp_mounting_hardware'}
    lowered=[p if p.label in fixed_labels else p.moved(bd.Pos(bay.SERVO_SHIFT_X,0,bay.FINAL_ARM_SHIFT)) for p in result.children]
    result=bd.Compound(children=[*lowered,bay.fixed_bay()],label='tom2_600mm')
    print('600 mm: electronics and plates ready',flush=True)
    # Shift the complete upper channel and wrist assembly, preserving the
    # elbow/yoke/roll connection. Raise the wrist mounts by the former
    # case-edge alignment offset so its pitch center meets the roll axis.
    result=align_elbow_roll(result,rise=LEGACY_ROLL_RISE)
    wrist_group=moving_sets()[1]
    elbow_group={'elbow_pitch_servo','elbow_roll_servo','elbow_pitch_yoke',
                 'elbow_yoke_horn_screws','elbow_roll_link_plate_pair',
                 'elbow_roll__hex_socket_m3x5__center','elbow_pitch__hex_socket_m3x5__center'}
    elbow_group.update(f'elbow_side_m2x6_{i}' for i in range(1,5))
    elbow_group.update(f'elbow_roll_link_plate_pair__hex_socket_m2x6__{i:02}' for i in (1,2,7,8))
    def lower_forearm(p,ancestor=None):
        if ancestor is None:ancestor=bd.Location()
        dz=WRIST_SHIFT if '#'+p.label in wrist_group else -COMPACT_DROP if p.label in elbow_group else 0
        dx=WRIST_INSET+2*LINK_TRANSFER if '#'+p.label in wrist_group else LINK_TRANSFER if p.label in elbow_group else 0
        if dz or dx:return p.moved(ancestor.inverse()*bd.Pos(dx,0,dz)*ancestor)
        if p.children:
            loc,children,label,color=p.location,list(p.children),p.label,p.color
            p.children=()
            return bd.Compound(children=[lower_forearm(c,ancestor*loc) for c in children],label=label,color=color).moved(loc)
        return p
    result=lower_forearm(result)
    print('600 mm: sideways elbow ready',flush=True)
    result=apply_tapered_links(result)
    return result
