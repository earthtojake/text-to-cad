"""Current arm part factories and one-time assembly placement.

The solid configuration supplies reusable component stock. Final profiles are
finished as individual parts before assembling them. Imported vendor geometry
is immutable: placement accumulates as Location values, never as deep copies of
an already-built assembly. Historical preview builders remain independent.
"""
from dataclasses import asdict, dataclass
from functools import cache
from time import perf_counter
import build123d as b
from lib.mates import revolute
from lib.booleans import as_single_shape as one
from lib import yoke_stock_revision as ys, base_and_m3_revision as base
from lib import elbow_pitch_lowering as elbow, gripper_tidy as grip
from lib import rest_wrist_contact as wrist
from lib.link_sheet_thickness import LINK_THICKNESS
from lib.tapered_solid_links import T
from lib.restored_base_plate import common_base_plate
from lib.m2_connection_rollout import revise_part, GRIPPER
from lib.cut_profile_finish import clearance_root
from lib.corner_rules import SMALL, LARGE
from lib.clamp_threads import tap_clamp
from lib.materials import SCREW_COLOR
from lib import gripper_flush_geometry as jaw
from lib import forearm_roll_flip as roll_flip
from lib import yoke_clearance_layout as clearance
from lib import forearm_shortening as shorter
from lib.gripper_hook_trim import trim_gripper_hook
from stages.diagonal_lightning_current import make_diagonal_links

ARM_RETRACTION_X=12.0
LINK_NAMES=('shoulder_pitch_yoke','elbow_roll_link_plate_pair')
FIXED_ROOTS={'direct_servo_clamp','m8_thumbscrew','fixed_electronics_bay'}
BASE_FIXED={'direct_servo_clamp','m8_thumbscrew','clamp_m8_captive_nut','clamp_pressure_pad_32mm'}


@cache
def configuration():
    """Evaluate the kinematic graph once; reuse every intermediate datum."""
    from stages.tom2_600mm_solid import kinematics as solid_kinematics
    solid=solid_kinematics()
    data=ys.revised_kinematics(solid);mates=[]
    for m in data['mates']:
        r=asdict(m)
        if r['kind']=='revolute':
            xyz=list(r['axis']['origin']);xyz[0]+=ARM_RETRACTION_X
            m=revolute(m.name,parent=m.parent,child=m.child,origin=xyz,
                       direction=r['axis']['dir'],limits=r['limits']['value'])
        mates.append(m)
    previous=elbow.revised_kinematics(base.revised_kinematics(data|{'mates':mates}))
    gripper=grip.revised_kinematics(previous)
    contact=wrist.revised_kinematics(gripper)
    return dict(solid=solid,previous=previous,gripper=gripper,
                final=shorter.revised_kinematics(clearance.revised_kinematics(contact)),
                clearance_shifts=shorter.motion_map(contact,clearance.motion_map(contact)),
                yoke_shifts=ys.motion_map(solid),elbow_refs=elbow.moving_refs(previous),
                gripper_refs=grip.gripper_refs(previous),wrist_refs=wrist.wrist_refs(gripper))


def placed_native(part, location):
    """New occurrence wrapper sharing immutable BREP, without Shape.__deepcopy__.

    TopoDS.Moved returns a new location-bearing handle. It does not move the
    input or copy its topology. Only use it on individual parts; build groups
    once from their final children instead of relocating finished subtrees.
    """
    q=b.Compound.cast(part.wrapped.Moved(location.wrapped))
    q.label,q.color=part.label,part.color
    return q


class Part:
    """An unfinished part and its accumulated world placement."""
    def __init__(self,part,ancestor):
        self.part=part;self.pending=ancestor
        self.label,self.color=part.label,part.color
    def shift(self,xyz):self.pending=b.Pos(*xyz)*self.pending
    def shape(self):
        q=placed_native(self.part,self.pending)
        q.label,q.color=self.label,self.color
        return q
    def replace(self,q):self.part=q;self.pending=b.Location()
    def finish(self,ancestor):
        q=placed_native(self.part,ancestor.inverse()*self.pending)
        q.label,q.color=self.label,self.color
        return q


def yoke_parts(data):
    from lib.yoke_125_geometry import make_yoke,PITCH
    axes={m.name:asdict(m)['axis']['origin'] for m in data['mates'] if asdict(m)['kind']=='revolute'}
    common=make_yoke(collar_extension=clearance.COLLAR_EXTENSION);result={}
    for name,joint,angle,direction in [('shoulder_yaw_yoke','shoulderPitch',0,(0,1,0)),
            ('elbow_pitch_yoke','elbowPitch',-90,(0,1,0)),
            ('temporary_wrist_yoke','wristPitch',180,(0,0,1))]:
        pt=list(axes[joint]);pt[1]=0 if joint=='wristPitch' else -.5
        d=(-ys.D,0,ys.D if joint=='wristPitch' else 0)
        result[name]=common.rotate(b.Axis(PITCH,direction),angle).moved(
            b.Pos(*[a+c-v for a,c,v in zip(pt,d,PITCH)]))
    return result


def static_gripper(part):
    """Finish the fixed finger/camera in its final mounting datum."""
    target=b.Vector(-105.86244,-7.35,102.6373766945)
    root=min((v.center() for v in part.vertices()),key=lambda v:(v-target).length)
    assert (root-target).length<.02,('Imported contour datum moved',root)
    xl=root.X-SMALL
    part=clearance_root(part,[(xl,-7.35,102.6363766945),(-96,-7.35,102.6363766945),
        (-96,7.35,102.6363766945),(xl,7.35,102.6363766945)],(0,0,1.6022),
        lambda v:v.X<xl+1e-5,SMALL)
    return jaw.finish_header(revise_part(part,GRIPPER))


@dataclass(frozen=True)
class Placement:
    retracted: bool=False
    elbow: bool=False
    gripper: bool=False
    wrist: bool=False
    bay: bool=False
    yoke: tuple=(0,0,0)
    clearance: tuple=(0,0,0)

    def assembly_offset(self):
        return b.Pos((ARM_RETRACTION_X if self.retracted else 0)
                     +(grip.CASE_INSET if self.gripper else 0)
                     +(wrist.SHIFT if self.wrist else 0),0,
                     -elbow.DROP if self.elbow else 0)


def build_current_arm(stock, *, only_labels=None):
    """Construct final parts and assemble once; no completed-arm revision passes.

    only_labels is for small geometry-equivalence checks, not production export.
    Parent occurrences retain their original hierarchy and final placements.
    Shape processing is restricted to fabricated parts and changed fasteners.
    """
    cfg=configuration();start=perf_counter()
    jaw_dimensions=jaw.dimensions(stock)
    wanted=lambda name:only_labels is None or name in only_labels
    yokes=yoke_parts(cfg['solid']) if only_labels is None or any(wanted(n) for n in
        ('shoulder_yaw_yoke','elbow_pitch_yoke','temporary_wrist_yoke')) else {}
    links={}
    if only_labels is None or any(wanted(n) for n in LINK_NAMES):
        links=dict(zip(LINK_NAMES,make_diagonal_links(lower_root=-20.775+clearance.COLLAR_EXTENSION,
                       upper_rise=clearance.AXIS_INCREASE,upper_shortening=shorter.SHORTENING,
                       toe_clearance=clearance.UPPER_TOE_CLEARANCE,
                       align_upper_relief=True,pattern_shift_x=-2.0,
                       upper_relief_x=clearance.UPPER_RELIEF_X)))
    print(f'current parts: selected links/yokes {perf_counter()-start:.3f}s',flush=True)
    spacers=[];extra_screws=[]

    def visit(p,old_ancestor,new_ancestor,state,depth):
        name=p.label
        label=base.rename(ys.new_label(name))
        state=Placement(
            retracted=(name not in FIXED_ROOTS) if depth==1 else state.retracted,
            elbow=state.elbow or label in cfg['elbow_refs'],
            gripper=state.gripper or label in cfg['gripper_refs'],
            wrist=state.wrist or label in cfg['wrist_refs'],
            bay=state.bay or name=='fixed_electronics_bay',
            yoke=cfg['yoke_shifts'].get(name,state.yoke),
            clearance=cfg['clearance_shifts'].get(label,state.clearance))
        old_world=old_ancestor*p.location
        # Assembly shifts are metadata, separate from leaf-only stock changes.
        new_world=state.assembly_offset()*old_world
        if p.children:
            cs=[q for c in p.children if (q:=visit(c,old_world,new_world,state,depth+1)) is not None]
            if not cs:return None
            if depth==0:return cs
            q=b.Compound(children=cs,label=p.label,color=p.color)
            q.move(new_ancestor.inverse()*new_world)
            return q
        # The added screw/spacers require their source fastener even in a
        # selected sub-model. All other unselected geometry is untouched.
        need_spacer=name in base.GRIPPER_SCREWS and (only_labels is None or any(
            wanted(f'gripper_m3_spacer_1p5mm_{i}') for i in range(1,7)))
        need_screw=name=='gripper_frame__hex_socket_m2x6__02' and wanted('gripper_lower_case_m2x6')
        if not wanted(label) and not need_spacer and not need_screw:return None
        part=Part(p,old_ancestor)
        if name in links:
            part.replace(links[name]);part.label=label
            part.shift(state.clearance)
            return part.finish(new_ancestor)
        if name in base.PLATE_NAMES:
            z=part.shape().bounding_box().min.Z
            part.replace(common_base_plate(servo_offset_x=clearance.AXIS_INCREASE,continuous_servo_connection=True).moved(b.Pos(0,0,z)))
        side_screw=name.startswith(('pitch_case_m2x6_','elbow_side_m2x6_')) or name in {
            f'elbow_roll_link_plate_pair__hex_socket_m2x6__{i:02}' for i in (3,4,5,6)}
        if side_screw:
            cy=part.shape().bounding_box().center().Y
            part.shift((0,(T-LINK_THICKNESS)*(1 if cy<0 else -1),0))
        if name in yokes:
            part.replace(yokes[name])
        elif ys.is_mount_bolt(name):
            q,_,out=base.grow_screw(part.shape(),5,3,2.75)
            part.replace(q);part.shift(tuple(out*ys.THICKNESS_DELTA));part.shift(state.yoke)
        elif name not in LINK_NAMES:part.shift(state.yoke)
        if state.retracted:part.shift((ARM_RETRACTION_X,0,0))
        # Stock thickness and screw seating are part-local construction.
        if name not in BASE_FIXED:
            dz=base.ARM_RISE
            if state.bay:
                dz=base.BASE_DELTA
                if name=='flat_base_foot_5052_2mm' or name.startswith('base_post_m2p5x6_'):dz=0
                if name.startswith('carrier_upper_m2p5x6_'):dz=base.ARM_RISE
            if name.startswith('clamp_standoff_screw_'):dz=base.BASE_DELTA
            if 'm3x5' in ys.new_label(name):
                q,c,out=base.grow_screw(part.shape(),5,3,2.75);part.replace(q)
                if name in base.GRIPPER_SCREWS:
                    plane=b.Plane(origin=c,z_dir=out)
                    ring=one(b.Solid.make_cylinder(3,base.GRIPPER_SPACER,plane).cut(
                        b.Solid.make_cylinder(1.6,base.GRIPPER_SPACER,plane)))
                    ring.label=f'gripper_m3_spacer_1p5mm_{base.GRIPPER_SCREWS.index(name)+1}'
                    ring.color=SCREW_COLOR
                    r=Part(ring,b.Location());r.shift((0,0,dz))
                    if ring.label in cfg['elbow_refs']:r.shift((0,0,-elbow.DROP))
                    if ring.label in cfg['gripper_refs']:r.shift((grip.CASE_INSET,0,0))
                    if ring.label in cfg['wrist_refs']:r.shift((wrist.SHIFT,0,0))
                    r.shift(cfg['clearance_shifts'].get(ring.label,(shorter.SHORTENING-clearance.AXIS_INCREASE,0,clearance.AXIS_INCREASE)))
                    if wanted(ring.label):spacers.append(r.finish(b.Location()))
                    part.shift(tuple(out*base.GRIPPER_SPACER))
            elif name.startswith('clamp_standoff_screw_'):
                from hardware.hex_socket_cap import hex_socket_m2x6
                bb=part.shape().bounding_box()
                part.replace(hex_socket_m2x6().moved(b.Pos(bb.center().X,bb.center().Y,bb.max.Z-4)*b.Rot(X=180)))
            part.shift((0,0,dz))
        part.label=label
        if state.elbow and name!='elbow_roll_link_plate_pair':part.shift((0,0,-elbow.DROP))
        if name=='servo6_fixed_gripper_frame':
            finger=grip.tidy_finger(part.shape(),extension=jaw_dimensions['fixed_extension'],fold_y=jaw.FIXED_FOLD_Y,
                                    contact_length=jaw_dimensions['contact_length'])
            part.replace(grip.compact_frame(grip.camera_corners(finger),outer_y=jaw_dimensions['outer_y'],outer_corner_radius=LARGE))
        elif name=='gripper_right_claw':
            part.replace(grip.tidy_finger(part.shape(),True,extension=jaw_dimensions['moving_extension']));part.shift((grip.CASE_INSET,0,0))
        else:
            if name=='gripper_frame__hex_socket_m2x6__02' and wanted('gripper_lower_case_m2x6'):
                r=Part(part.shape(),b.Location());r.label='gripper_lower_case_m2x6'
                r.shift((-20.5+grip.CASE_INSET,0,0));r.shift((wrist.SHIFT,0,0))
                r.shift((shorter.SHORTENING-clearance.AXIS_INCREASE,0,clearance.AXIS_INCREASE))
                extra_screws.append(r.finish(b.Location()))
            if state.gripper:part.shift((grip.CASE_INSET,0,0))
        if state.wrist:part.shift((wrist.SHIFT,0,0))
        if name=='servo6_fixed_gripper_frame':part.replace(static_gripper(part.shape()))
        elif name=='direct_servo_clamp':part.replace(tap_clamp(part.shape()))
        if roll_flip.flipped_leaf(label):part.pending=roll_flip.placement()*part.pending
        part.shift(state.clearance)
        if name=='servo6_fixed_gripper_frame':
            # This cut is in the part's construction datum. Keep the pending
            # final wrist/yoke placement instead of resetting it via replace().
            part.part=trim_gripper_hook(part.part)
        return part.finish(new_ancestor) if wanted(label) else None

    children=visit(stock,b.Location(),b.Location(),Placement(),0)
    result=b.Compound(children=[*children,*spacers,*extra_screws],label=stock.label,color=stock.color)
    print(f'current parts: final parts and placement {perf_counter()-start:.3f}s',flush=True)
    return result
