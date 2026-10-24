"""Tom fork: stationary shoulder horns, case-carried continuous upper link.

The frozen production STEP is an intentional independent design input. The
long slotted channel and distal interfaces retain their original geometry;
the shoulder is lowered and tightened against the yaw envelope.
The obsolete shoulder-roll root feet and slit are removed from that channel.
"""
from pathlib import Path
import json
import math
import numpy as np
from dataclasses import asdict
from lib.link_assembly import location_from_transform
import build123d as bd
from cadgen import memo, read_xbf
from lib.mates import revolute, fastened
from lib.booleans import as_single_shape as one
from lib import horn_cap, sheet_rule_scs as sheet
from lib.materials import ALUMINUM_5052_COLOR, SCREW_COLOR
from hardware.hex_socket_cap import hex_socket_m2x6, hex_socket_m3x5
from hardware.m2_mf_standoff_10mm import m2_mf_standoff_10mm
from lib import base_stacked_layout as base_layout
from lib.lower_link_base import ARM_Z_SHIFT, SERVO_PAD_Z

# Tom rev3's production arm (recovered/tom_rev3/tom.step): its kinematics sidecar, and the
# occurrences this stage uses, each extracted once to parts/<occurrence>.xbf at its place in the
# arm (src/rev3_parts.py: a model per occurrence, and the export). The rest of the 354 MB file is never read.
BASELINE=Path(__file__).resolve().parents[2]/'STEP/imported/recovered/tom_rev3/tom.step'
REV3_PARTS=Path(__file__).resolve().parents[2]/'STEP/imported/parts'
REV3_OCCURRENCES=('shoulder_yaw_servo','m8_thumbscrew','shoulder_yaw_assembly',
    'shoulder_pitch_assembly_screws','upper_arm_assembly','elbow_assembly','forearm_assembly',
    'gripper_screws')
T=2.032
RI=.9652
RO=T+RI
BASE_PX,BASE_PZ=-56.2126,94.23199934
# Shoulder axis stays fixed; size the yoke wall from the nearest horn bore.
PIVOT_SHIFT_X=4.7126
PIVOT_SHIFT_Z=-20.525
PIVOT_SHIFT_Y=-.5
PZ=BASE_PZ+PIVOT_SHIFT_Z
PX=BASE_PX+PIVOT_SHIFT_X
def pitch_axis():
    return bd.Axis((PX,.5,PZ),(0,1,0))

def flip_motor(shape):
    return shape.rotate(bd.Axis((BASE_PX,.5,BASE_PZ),(0,1,0)),180).moved(bd.Pos(PIVOT_SHIFT_X,0,PIVOT_SHIFT_Z))
# Native production case faces remain at +/-16 after the end-for-end flip.
HORN_SEATS=(-18.3,18.3)
# ALU-080: keep the hole edge outside the half-die zone even with the
# published +/-0.015 inch bend position and +/-0.005 inch laser cut errors.
# This controls the minimum wall setback before servo-case clearance does.
HORN_BEND_POSITION_TOLERANCE=0.015*25.4
HORN_BEND_MARGIN=HORN_BEND_POSITION_TOLERANCE+sheet.CUT_TOLERANCE_MM
from lib.tom2_dimensions import COLLAR_SHORTEN_MM
WEB_X=COLLAR_SHORTEN_MM+(PX+7+1.6+sheet.HALF_DIE_WIDTH_MM+HORN_BEND_MARGIN
       -sheet.BEND_ALLOWANCE_90_MM/2+RO)
WRIST_YOKE_WEB_X=-34.7096
LINK_REAR=-111.6321767
JOIN_Z=160.36419934
from lib.tom2_dimensions import LINK_ROOF_HEIGHT_MM, LINK_HEIGHT_REDUCTION_MM
LINK_ROOF_HEIGHT=LINK_ROOF_HEIGHT_MM  # Minimum bend setback from retained mounting holes.
LINK_ROOF_DROP=(BASE_PX-LINK_REAR)-LINK_ROOF_HEIGHT
LINK_INSET_MM=12.274283759077829
HORN_CAP_RADIUS=horn_cap.CIRCULAR_HORN_FORK_PATTERN.outer_radius_mm
COLLAR_U_HALF_WIDTH=10.75
COLLAR_SQUARE_CLEARANCE=WEB_X-PX
CASE_HORN_RELIEF_R=11.0
HOOK_ARC_SWEEP_DEG=45.0
HOOK_RETURN_RADIUS=3.0
SHOULDER_HORN_HOLES=((PX,PZ-7),(PX+7,PZ),(PX-7,PZ))
LINK_SLOT_PITCH=19.0
TEMPORARY_WRIST_YOKE=True
ELBOW_YOKE_COPY_PREVIEW=False


def box(x0,x1,y0,y1,z0,z1):
    return bd.Solid.make_box(x1-x0,y1-y0,z1-z0,bd.Plane(origin=(x0,y0,z0)))


def prism(points,y,depth):
    face=bd.Face(bd.Wire.make_polygon([(x,y,z)for x,z in points],close=True))
    return bd.Solid.extrude(face,(0,depth,0))


def bore(x,y,z,r,sign):
    return bd.Solid.make_cylinder(r,T+.04,bd.Plane(origin=(x,y-sign*.02,z),z_dir=(0,sign,0)))


def quarter_bend(cx,cy,z0,z1,sign,xsign):
    ring=bd.Solid.make_cylinder(RO,z1-z0,bd.Plane(origin=(cx,cy,z0))).cut(
        bd.Solid.make_cylinder(RI,z1-z0,bd.Plane(origin=(cx,cy,z0))))
    xa,xb=sorted((cx,cx+xsign*RO));ya,yb=sorted((cy,cy+sign*RO))
    return one(ring.intersect(box(xa,xb,ya,yb,z0,z1)))


def revised_yaw_yoke(original, *, bottom_hook=True):
    from lib.elbow_yoke_integration import PITCH_TOP,PITCH_BOTTOM
    # The base-servo U is narrowed to the established 21.5 mm horn-cap width.
    # The shoulder hook is separate from this constant-width base U.
    lower=PZ-18.3;upper=PZ+18.3
    half_width=COLLAR_U_HALF_WIDTH
    web_x=WEB_X if bottom_hook else WRIST_YOKE_WEB_X
    bend_x=web_x-RO
    retained=box(web_x-T,web_x,-half_width,half_width,lower+RI,upper-RI)
    for z,sign in ((lower,-1),(upper,1)):
        za,zb=sorted((z,z+sign*T))
        cx=web_x+RI;cz=z-sign*RI
        # Retain the established compact fork tips, which clear the base posts.
        cap=bd.Solid.make_cylinder(HORN_CAP_RADIUS,T,
            bd.Plane(origin=(-18.65,0,za)))
        # A full-width 5.5 mm forming land precedes the transition to the horn.
        points=[(cx,-half_width),(cx+5.5,-half_width),(-18.65,-HORN_CAP_RADIUS),
            (-18.65,HORN_CAP_RADIUS),(cx+5.5,half_width),(cx,half_width)]
        face=bd.Face(bd.Wire.make_polygon([(x,y,za) for x,y in points],close=True))
        arm=one(cap.fuse(bd.Solid.extrude(face,(0,0,T))))
        arm=horn_cap.apply_horn_fork(arm,center=(-18.65,0,z+sign*T/2),
            across=(0,1,0),outboard=(1,0,0),normal=(0,0,1),thickness_mm=T,
            half_width_mm=HORN_CAP_RADIUS,pattern=horn_cap.CIRCULAR_HORN_FORK_PATTERN)
        pl=bd.Plane(origin=(cx,-half_width,cz),z_dir=(0,1,0))
        ring=bd.Solid.make_cylinder(RO,2*half_width,pl).cut(bd.Solid.make_cylinder(RI,2*half_width,pl))
        aa,bb=sorted((cz,cz+sign*RO))
        bend=one(ring.intersect(box(cx-RO,cx,-half_width,half_width,aa,bb)))
        retained=one(retained.fuse(arm,bend))
    pieces=[retained]
    # The shoulder hook opens upward, retaining left/bottom/right horn bores.
    # Retain the deep section at the bends, but follow the horn circle on the
    # free side so the case-carried link clears the hook at -180 degrees.
    closed_depth=PITCH_BOTTOM if bottom_hook else 10.75
    z0=PZ-closed_depth
    z1=PZ+(PITCH_TOP if bottom_hook else 10.75)
    bend_ys=[HORN_SEATS[0]+RI,HORN_SEATS[1]-RI]
    pieces.append(box(web_x-T,web_x,bend_ys[0],bend_ys[1],z0,z1))
    for sign,y in zip((-1,1),HORN_SEATS):
        # Rounded cap and straight stem approach from the base side.
        disk=bd.Solid.make_cylinder(HORN_CAP_RADIUS,T,bd.Plane(origin=(PX,y,PZ),z_dir=(0,sign,0)))
        # The case points up at rest and swings away from this straight neck.
        neck_points=([(PX,z0),(bend_x,z0),(bend_x,z1),(PX,z1)] if bottom_hook else
            [(PX,PZ-HORN_CAP_RADIUS),(bend_x,z0),(bend_x,z1),(PX,PZ+HORN_CAP_RADIUS)])
        neck=prism(neck_points,y,sign*T)
        arm=one(disk.fuse(neck))
        for x,z,r in ((PX,PZ,3),(PX,PZ-7,1.6),(PX+7,PZ,1.6),(PX,PZ+7,1.6)):
            arm=one(arm.cut(bore(x,y,z,r,sign)))
        if bottom_hook:
            arm=horn_cap.apply_narrow_horn_fork(arm,center=(PX,y+sign*T/2,PZ),
                across=(0,0,1),outboard=(-1,0,0),normal=(0,1,0),
                thickness_mm=T,half_width_mm=HORN_CAP_RADIUS,
                pattern=horn_cap.CircularSideEntryHornForkPattern(
                    straight_back=True, stem_edge_mm=PITCH_TOP,
                    entry_corner_radius_mm=min(3.0,PITCH_TOP-2.9),
                    arc_sweep_deg=HOOK_ARC_SWEEP_DEG,
                    bend_corner_radius_mm=HOOK_RETURN_RADIUS),
                closed_side_mm=closed_depth,
                bend_return_outboard_mm=PX-bend_x)
        else:
            arm=horn_cap.apply_horn_fork(arm,center=(PX,y+sign*T/2,PZ),
                across=(0,0,1),outboard=(-1,0,0),normal=(0,1,0),
                thickness_mm=T,half_width_mm=HORN_CAP_RADIUS,pattern=horn_cap.CIRCULAR_HORN_FORK_PATTERN)
        pieces.extend((arm,quarter_bend(bend_x,y-sign*RI,z0,z1,sign,1)))
    result=one(pieces[0].fuse(*pieces[1:])).clean()
    assert result.is_valid and len(result.solids())==1
    result.label='shoulder_yaw_yoke';result.color=ALUMINUM_5052_COLOR
    return result


REST_CASE_HOLES=tuple((sign,x,z) for sign,far in ((-1,32.75),(1,29.0))
    for x,z in ((PX+10.25,PZ+far),(PX-10.25,PZ+far))) + tuple(
    (sign,PX+10.25,PZ+8.3) for sign in (-1,1))


def joined_link(original_yaw,original_link):
    """Horizontal rest link with a case envelope and a short horn clearance cut."""
    retained=one(original_link.intersect(box(-200,0,-30,30,JOIN_Z,400)))
    # Close the obsolete roll-foot slit through BOTH panels and their bends,
    # using an intact cross-section of the same constant-width channel edge.
    repair=one(original_link.intersect(box(LINK_REAR-.01,LINK_REAR+25,-30,30,JOIN_Z+3,JOIN_Z+4.5)))
    retained=one(retained.fuse(repair.moved(bd.Pos(0,0,-3))))
    retained=retained.moved(bd.Pos(PIVOT_SHIFT_X,0,PIVOT_SHIFT_Z)).rotate(pitch_axis(),90)
    retained=retained.moved(bd.Pos(-LINK_INSET_MM,0,-LINK_ROOF_DROP))
    left=PX-13.25;right=PX+13.25
    join=PX+JOIN_Z-BASE_PZ-LINK_INSET_MM
    roof_left=left
    top=PZ+LINK_ROOF_HEIGHT
    tangent=top-RO
    lower=PZ-(-52.1876-BASE_PX)-LINK_ROOF_DROP
    end_clear=PZ+32.75-2.65
    pieces=[retained]
    for sign,far in ((-1,32.75),(1,29.0)):
        # Same open two-ear end mount as the production link: 8 mm half
        # window, rounded free corners, and direct material above each screw.
        # No inherited flange fragments or slit separating ears from panel.
        tip=PZ+far-2.65
        outline=[(left,tangent),(left,tip),(PX-8,tip),(PX-8,end_clear),
            (PX+8,end_clear),(PX+8,tip),(right,tip),(right,tangent)]
        face=bd.Face(bd.Wire.make_polygon([(x,sign*16,z) for x,z in outline],close=True))
        face=face.fillet_2d(1.0,[v for v in face.vertices() if abs(v.center().Z-tip)<1e-6])
        mount=bd.Solid.extrude(face,(0,sign*T,0))
        for x in (PX-10.25,PX+10.25):
            mount=one(mount.cut(bore(x,sign*16,PZ+far,1.1,sign)))
        pieces.append(mount)
        # The short underside land clears the stationary horn neck. It then
        # joins the existing link taper without a separate collar or spacer.
        pieces.append(prism([(right,PZ+4.5),(right+1,PZ+4.5),
            (join,lower),(join,tangent),(right,tangent)],sign*16,sign*T))
        cy=sign*(16-RI)
        plane=bd.Plane(origin=(roof_left,cy,tangent),z_dir=(1,0,0))
        ring=bd.Solid.make_cylinder(RO,join-roof_left,plane).cut(bd.Solid.make_cylinder(RI,join-roof_left,plane))
        y0,y1=sorted((cy,sign*(16+T)))
        pieces.append(one(ring.intersect(box(roof_left,join,y0,y1,tangent,top))))
    pieces.append(box(roof_left,join,-16+RI,16-RI,top-T,top))
    result=one(pieces[0].fuse(*pieces[1:])).clean()
    # Fill beside the narrowed base U, ending on the yaw web's X plane.
    # This exact flush rest geometry is intentional; motion interference is
    # recorded separately in analysis/tom2/validation.json, not relieved here.
    for sign in (-1,1):
        y0,y1=sorted((sign*16,sign*(16+T)))
        result=one(result.fuse(box(right,join,y0,y1,lower,tangent))).clean()
    for sign,far in ((-1,32.75),(1,29.0)):
        y0,y1=sorted((sign*16,sign*(16+T)))
        tip=PZ+far-2.65
        result=one(result.cut(box(right,PX+COLLAR_SQUARE_CLEARANCE,
            y0-.01,y1+.01,PZ-35,tip)))
        # Straight ear underside continuing to the aligned vertical end face.
        result=one(result.fuse(box(right-1,PX+COLLAR_SQUARE_CLEARANCE,
            y0,y1,tip,tangent))).clean()
        # Align both tabs with the upper window's X=PX+8 datum. The lower
        # cover needs its original clearance; fill the opposite face only.
        strip_top=end_clear if sign>0 else PZ+10.95
        outline=[(PX+8,PZ+5.65),(PX+8,strip_top),
            (right,strip_top),(right,tip),
            (PX+COLLAR_SQUARE_CLEARANCE,tip),
            (PX+COLLAR_SQUARE_CLEARANCE,PZ+5.65)]
        face=bd.Face(bd.Wire.make_polygon([(x,sign*16,z) for x,z in outline],close=True))
        face=face.fillet_2d(1.0,[v for v in face.vertices()
            if abs(v.center().X-(PX+8))<1e-6 and abs(v.center().Z-(PZ+5.65))<1e-6])
        tab=bd.Solid.extrude(face,(0,sign*T,0))
        tab=one(tab.cut(bore(PX,sign*16,PZ,CASE_HORN_RELIEF_R,sign)))
        tab=one(tab.cut(bore(PX+10.25,sign*16,PZ+8.3,1.1,sign)))
        tab=one(tab.cut(bore(PX+10.25,sign*16,PZ+far,1.1,sign)))
        result=one(result.fuse(tab)).clean()
    # Repeat the first established diagonal opening one 19 mm pitch inward.
    wall=next(f for f in retained.faces() if f.geom_type==bd.GeomType.PLANE
        and f.normal_at().Y>.999 and f.area>100)
    window=min((w for w in wall.inner_wires() if w.bounding_box().size.Z>10),
        key=lambda w:w.bounding_box().min.X)
    tool=bd.Face(window).moved(bd.Pos(-LINK_SLOT_PITCH,-50,0))
    result=one(result.cut(bd.Solid.extrude(tool,(0,100,0)))).clean()
    # The complete long channel, including its distal case mounting ears,
    # moves with the roof. Its original openings and end geometry are kept.
    assert result.is_valid and len(result.solids())==1,('rest envelope',len(result.solids()))
    # The assembly is posed uniformly at the end of the build.
    result=result.rotate(pitch_axis(),-90)
    result.label='shoulder_pitch_yoke';result.color=ALUMINUM_5052_COLOR
    return result.moved(bd.Pos(0,PIVOT_SHIFT_Y,0))


def screw(model,label,point,sign):
    p=model.moved(bd.Plane(origin=point,z_dir=(0,sign,0)).location)
    p.label=label;p.color=SCREW_COLOR
    return p


def upright_kinematics():
    raw=json.loads(BASELINE.with_suffix('.step.json').read_text())['kinematics']
    mates=[]
    remove={'shoulderRoll','shoulderRoll__shoulder_roll_link_plate_pair',
        'shoulderRoll__elbow_pitch_servo','shoulderYaw__shoulder_pitch_servo'}
    for m in raw['mates']:
        m={k:v for k,v in m.items() if k not in ('parentId','childId')}
        name=m['name']
        if name in remove or '__jaw_case_' in name:continue
        numeric={'#o1.1.1.1.13':'#shoulder_yaw_servo_detail_15',
                 '#o1.1.1.1.14':'#shoulder_yaw_servo_detail_16',
                 '#o1.7.2.1.13':'#gripper_jaw_servo_detail_15',
                 '#o1.7.2.1.14':'#gripper_jaw_servo_detail_16'}
        m['child']=numeric.get(m['child'],m['child'])
        if name.startswith('shoulder_pitch_yoke__') or name.startswith('shoulder_roll__'):continue
        if name.startswith('shoulder_roll_link_plate_pair__') and name[-2:] in ('01','02','07','08'):continue
        if name.startswith('shoulder_yaw_yoke__hex_socket_m2'):continue
        if m['parent']=='#shoulder_roll_servo':m['parent']='#shoulder_pitch_yoke'
        if m['parent']=='#shoulder_roll_link_plate_pair':m['parent']='#shoulder_pitch_yoke'
        if name=='shoulder_pitch__hex_socket_m3x5__center':m['parent']='#shoulder_yaw_yoke'
        if m['kind']=='revolute':
            if name!='shoulderYaw':
                m['axis']['origin'][0]+=PIVOT_SHIFT_X
                m['axis']['origin'][1]+=PIVOT_SHIFT_Y
            if name not in ('shoulderYaw','shoulderPitch'):
                m['axis']['origin'][0]+=LINK_ROOF_DROP
                m['axis']['origin'][2]-=LINK_INSET_MM
            m['axis']['origin'][2]+=ARM_Z_SHIFT+(PIVOT_SHIFT_Z if name!='shoulderYaw' else 0)
            mates.append(revolute(name,parent=m['parent'],child=m['child'],origin=m['axis']['origin'],direction=m['axis']['dir'],limits=m['limits']['value']))
        else:
            mates.append(fastened(name,parent=m['parent'],child=m['child']))
    mates.extend((fastened('pitch_case_carried',parent='#shoulder_pitch_yoke',child='#shoulder_pitch_servo'),
        fastened('elbow_case_carried',parent='#shoulder_pitch_yoke',child='#elbow_pitch_servo')))
    mates.extend((fastened('base_case_grounded',parent='#direct_servo_clamp',child='#shoulder_yaw_servo'),
        fastened('jaw_case_carried',parent='#gripper_frame',child='#gripper_jaw_servo')))
    for i in (15,16):
        mates.append(fastened(f'pitch_horn_fixed_{i}',parent='#shoulder_yaw_yoke',child=f'#shoulder_pitch_servo_detail_{i}'))
    for i in range(1,7):mates.append(fastened(f'new_pitch_horn_{i}',parent='#shoulder_yaw_yoke',child=f'#pitch_horn_m3x5_{i}'))
    for i in range(1,len(REST_CASE_HOLES)+1):mates.append(fastened(f'new_pitch_case_{i}',parent='#shoulder_pitch_yoke',child=f'#pitch_case_m2x6_{i}'))
    for servo,parent in (('elbow_pitch_servo','elbow_pitch_yoke'),('elbow_roll_servo','elbow_pitch_yoke'),('wrist_pitch_servo','gripper_frame')):
        for i in (15,16):mates.append(fastened(f'{servo}_horn_{i}',parent=f'#{parent}',child=f'#{servo}_detail_{i}'))
    poses={name:{k:v for k,v in p.items() if k!='shoulderRoll'}for name,p in raw['poses'].items()}
    return {'mates':mates,'poses':poses}


REST_ANGLES={'shoulderPitch':90.0,'elbowPitch':-90.0}

def rotation_matrix(origin,direction,degrees):
    v=np.array(direction,dtype=float);v/=np.linalg.norm(v)
    x,y,z=v;skew=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    a=math.radians(degrees);r=np.eye(3)+math.sin(a)*skew+(1-math.cos(a))*(skew@skew)
    m=np.eye(4);m[:3,:3]=r;o=np.array(origin);m[:3,3]=o-r@o
    return m

def rest_transforms():
    raw=upright_kinematics();rows=[asdict(m) for m in raw['mates']]
    by_child={r['child']:r for r in rows};cache={}
    def transform(ref):
        if ref in cache:return cache[ref]
        row=by_child.get(ref)
        if row is None:return np.eye(4)
        m=transform(row['parent'])
        if row['kind']=='revolute':m=m@rotation_matrix(row['axis']['origin'],row['axis']['dir'],REST_ANGLES.get(row['name'],0))
        cache[ref]=m;return m
    for ref in by_child:transform(ref)
    return raw,rows,cache

def full_kinematics():
    raw,rows,transforms=rest_transforms();mates=[]
    for row in rows:
        if row['kind']=='revolute':
            m=transforms.get(row['parent'],np.eye(4));axis=row['axis']
            origin=(m@[*axis['origin'],1])[:3];direction=m[:3,:3]@axis['dir']
            offset=REST_ANGLES.get(row['name'],0)
            mates.append(revolute(row['name'],parent=row['parent'],child=row['child'],
                origin=origin.tolist(),direction=direction.tolist(),limits=[v-offset for v in row['limits']['value']]))
        else:mates.append(fastened(row['name'],parent=row['parent'],child=row['child']))
    poses={name:{key:pose.get(key,0)-REST_ANGLES.get(key,0) for key in set(pose)|set(REST_ANGLES)} for name,pose in raw['poses'].items()}
    poses['rest']={}
    return {'mates':mates,'poses':poses}

def inline_arm_kinematics():
    original=full_kinematics()
    if not TEMPORARY_WRIST_YOKE:return original
    mates=[]
    for mate in original['mates']:
        m=asdict(mate)
        if m['name']=='wristPitch':
            mates.append(revolute('wristPitch',parent=m['parent'],child='#temporary_wrist_yoke',
                origin=m['axis']['origin'],direction=m['axis']['dir'],limits=m['limits']['value']))
        elif m['name'].startswith('wrist_pitch_servo_horn_') or m['name']=='wrist_pitch__hex_socket_m3x5__center':
            mates.append(fastened(m['name'],parent='#temporary_wrist_yoke',child=m['child']))
        elif not any(token in str(m) for token in ('gripper','camera','jaw_')):
            mates.append(mate)
    for i in range(1,7):
        mates.append(fastened(f'temporary_wrist_screw_{i}',parent='#temporary_wrist_yoke',child=f'#temporary_wrist_m3x5_{i}'))
    wrist=next(asdict(m) for m in original['mates'] if m.name=='wristPitch')['axis']['origin']
    mates.append(revolute('wristYaw',parent='#temporary_wrist_yoke',child='#wrist_yaw_servo',
        origin=(wrist[0]-(-18.65-PX),0,wrist[2]),direction=(0,0,1),limits=(-90,90)))
    for i in (15,16):
        mates.append(fastened(f'wrist_yaw_fixed_horn_{i}',parent='#temporary_wrist_yoke',child=f'#wrist_yaw_servo_detail_{i}'))
    for i in range(1,8):
        mates.append(fastened(f'wrist_yaw_mount_{i}',parent='#temporary_wrist_yoke',child=f'#wrist_yaw_m3x5_{i}'))
    return {'mates':mates,'poses':{name:{k:v for k,v in pose.items() if k!='gripperJaw'} for name,pose in original['poses'].items()}}


def original_kinematics():
    """Six arm joints plus the maintained S7 gripper and camera assembly."""
    from end_effector.servo6_gripper_concept import inline_kinematics
    arm=inline_arm_kinematics();wrist=inline_kinematics()
    # Retain the arm's upstream axes; bring in the concept's jaw joint and
    # its complete hardware ownership, including the fixed S6 horn details.
    added=[]
    for m in wrist['mates']:
        if m.name in ('wristPitch','wristYaw'):continue
        if m.name=='gripperJaw':
            r=asdict(m);o=list(r['axis']['origin']);o[2]-=LINK_HEIGHT_REDUCTION_MM
            m=revolute(m.name,parent=r['parent'],child=r['child'],origin=o,
                       direction=r['axis']['dir'],limits=r['limits']['value'])
        added.append(m)
    replaced={asdict(m)['child']for m in added}
    mates=[m for m in arm['mates']if asdict(m)['child']not in replaced]+added
    poses={name:dict(pose,gripperJaw=0)for name,pose in arm['poses'].items()}
    poses.update(wrist['poses'])
    poses['rest']={}
    if ELBOW_YOKE_COPY_PREVIEW:
        mates.append(fastened('elbow_yoke_copy_preview_mount',
            parent='#elbow_pitch_yoke',child='#elbow_yoke_copy_preview'))
    return {'mates':mates,'poses':poses}


def kinematics():
    from lib.elbow_yoke_integration import update_kinematics
    return update_kinematics(original_kinematics())


def replace_gripper_with_yoke(parts, wrist_yoke):
    if not TEMPORARY_WRIST_YOKE:return parts
    # The shoulder experiment must not silently reshape the copied wrist.
    yaw=wrist_yoke
    source_screws=next(p for p in parts if p.label=='shoulder_yaw_assembly_screws')
    old_screws=next(p for p in parts if p.label=='gripper_screws')
    center=next(p for p in old_screws.children if p.label=='wrist_pitch__hex_socket_m3x5__center')
    wrist=next(asdict(m) for m in full_kinematics()['mates'] if m.name=='wristPitch')['axis']['origin']
    # Both real horn faces are at Y=+/-18.3; the joint-axis origin's Y
    # coordinate is arbitrary along that line and is not the horn midpoint.
    axis=bd.Axis((PX,0,PZ+ARM_Z_SHIFT),(0,0,1))
    delta=bd.Pos(wrist[0]-PX,0,wrist[2]-(PZ+ARM_Z_SHIFT))
    duplicate=yaw.rotate(axis,180).moved(delta)
    duplicate.label='temporary_wrist_yoke'
    screws=[]
    original_pitch_screws=[]
    m3=hex_socket_m3x5()
    for sign,y in zip((-1,1),HORN_SEATS):
        for x,z in ((PX,PZ-7),(PX+7,PZ),(PX,PZ+7)):
            original_pitch_screws.append(screw(m3,'wrist_source_screw',(x,y+sign*T,z+ARM_Z_SHIFT),sign))
    for i,p in enumerate(original_pitch_screws,1):
        copy=p.rotate(axis,180).moved(delta);copy.label=f'temporary_wrist_m3x5_{i}';screws.append(copy)
    screws.append(center)
    # Horns are fixed to the yoke; the sixth servo's case becomes the output.
    base_servo=next(p for p in parts if p.label=='shoulder_yaw_servo')
    motor=base_servo.rotate(axis,180).moved(delta);motor.label='wrist_yaw_servo'
    for node in motor.children:
        node.label=node.label.replace('shoulder_yaw_servo','wrist_yaw_servo')
    mounts=[p for p in source_screws.children if p.label.startswith('shoulder_yaw_yoke__hex_socket_m3x5')
        or p.label=='shoulder_yaw__hex_socket_m3x5__center']
    for i,p in enumerate(mounts,1):
        copy=p.rotate(axis,180).moved(delta);copy.label=f'wrist_yaw_m3x5_{i}';screws.append(copy)
    # Keep complete servos and hardware grouped while flattening the arm root.
    retained=[p for p in parts if not any(token in p.label for token in ('gripper','camera'))]
    return retained+[duplicate,motor,bd.Compound(children=screws,label='temporary_wrist_screws')]


def bake_rest(parts):
    _,_,transforms=rest_transforms()
    phase=rotation_matrix((PX,.5,PZ+ARM_Z_SHIFT),(0,1,0),-90)
    def visit(node,ancestors,inherited):
        transform=transforms.get('#'+node.label,inherited)
        if node.children:
            loc=ancestors*node.location;children=list(node.children);node.children=()
            return bd.Compound(children=[visit(c,loc,transform) for c in children],label=node.label)
        placed=node.move(ancestors)
        if node.label.startswith('shoulder_pitch_servo_detail_') and int(node.label.rsplit('_',1)[1])<15:
            transform=transform@phase
        return placed.move(location_from_transform(transform.flatten().tolist()))
    return [visit(p,bd.Location(),np.eye(4))for p in parts]


def arm_with_inline_wrist():
    """Shared arm context, without a gripper, for full and isolated models."""
    print('Reading pinned Tom rev3 parts',flush=True)
    # One read per part, all named as rev3's (a servo's details are one prototype however
    # many parts carry a servo).
    rev3={name:read_xbf(REV3_PARTS/f'{name}.xbf') for name in REV3_OCCURRENCES}
    print('Building revised shoulder parts',flush=True)
    # Bake group placements when extracting; retain each purchased servo tree.
    def take_children(group):
        loc=group.location
        cs=list(group.children);group.children=()
        return [c.move(loc) for c in cs]
    # rev3's groups: shoulder_yaw_assembly (yoke, pitch servo, screws), shoulder_pitch_assembly
    # (only its screws), upper_arm_assembly (roll servo, link pair, elbow servo, screws), elbow
    # and forearm wholly, and of the gripper its screws (the wrist's centre screw).
    shoulder_yaw=take_children(rev3['shoulder_yaw_assembly'])
    upper_arm=take_children(rev3['upper_arm_assembly'])
    old_yaw=shoulder_yaw[0].solids()[0]
    old_link=upper_arm[1].solids()[0]
    yaw=revised_yaw_yoke(old_yaw)
    link=joined_link(old_yaw,old_link)
    pitch=flip_motor(shoulder_yaw[1]).moved(bd.Pos(0,PIVOT_SHIFT_Y,0));pitch.label='shoulder_pitch_servo'
    # Keep base horn hardware; replace the four former case screws.
    old_screws=shoulder_yaw[2]
    yaw_screws=[c for c in take_children(old_screws) if 'm2x6' not in c.label]
    m3=hex_socket_m3x5();m2=hex_socket_m2x6()
    for sign,y in zip((-1,1),HORN_SEATS):
        for x,z in SHOULDER_HORN_HOLES:
            yaw_screws.append(screw(m3,f'pitch_horn_m3x5_{len(yaw_screws)-6}',(x,y+sign*T,z),sign))
    old_pitch_screws=rev3['shoulder_pitch_assembly_screws']
    yaw_screws += [c.move(bd.Pos(PIVOT_SHIFT_X,PIVOT_SHIFT_Y,PIVOT_SHIFT_Z)) for c in take_children(old_pitch_screws) if c.label=='shoulder_pitch__hex_socket_m3x5__center']
    # Four end holes plus two direct inner-side case tabs.
    case_screws=[]
    for sign,x,z in REST_CASE_HOLES:
        part=screw(m2,f'pitch_case_m2x6_{len(case_screws)+1}',(x,sign*(16+T)+PIVOT_SHIFT_Y,z),sign)
        case_screws.append(part.rotate(pitch_axis(),-90))
    # Root feet vanish with the shoulder-roll motor; distal link screws stay.
    upper_screws=upper_arm[3]
    distal_screws=[c for c in take_children(upper_screws) if c.label[-2:] in ('03','04','05','06')]
    contents=[None,
              [yaw,pitch,bd.Compound(children=yaw_screws,label='shoulder_yaw_assembly_screws')],
              [link,bd.Compound(children=case_screws,label='shoulder_pitch_assembly_screws')],
              [upper_arm[2],bd.Compound(children=distal_screws,label='upper_arm_assembly_screws')],
              take_children(rev3['elbow_assembly']),
              take_children(rev3['forearm_assembly']),
              [rev3['gripper_screws']]]
    for cs in contents[3:]:
        for part in cs:part.move(bd.Pos(PIVOT_SHIFT_X+LINK_ROOF_DROP,PIVOT_SHIFT_Y,PIVOT_SHIFT_Z-LINK_INSET_MM))
    # Retain the production base servo and thumbscrew; the PCB stack, carrier
    # and their hardware are not extracted.
    g=base_layout
    clamp=g.make_clamp()
    clamp=one(clamp.fuse(*[g.cylinder(g.CLAMP_M2_TAP_DIAMETER/2+.01,g.T,x,y)for x,y in g.mount_xy('pi_hat')]))
    clamp=one(clamp.cut(*[g.cylinder(1.1,g.T,x,y)for x,y in g.servo_xy('pi_hat')])).clean()
    clamp.label='direct_servo_clamp'
    base_servo=rev3['shoulder_yaw_servo'].move(bd.Pos(0,0,ARM_Z_SHIFT))
    thumb=rev3['m8_thumbscrew']
    post=m2_mf_standoff_10mm();supports=[]
    for i,(x,y) in enumerate(g.servo_xy('pi_hat'),1):
        p=post.moved(bd.Pos(x,y,SERVO_PAD_Z)*bd.Rot(X=180));p.label=f'servo_standoff_{i}';supports.append(p)
        p=m2.moved(bd.Pos(x,y,0)*bd.Rot(X=180));p.label=f'clamp_standoff_screw_{i}';supports.append(p)
    flat=[clamp,base_servo,thumb,bd.Compound(children=supports,label='clamp_mounting_hardware')]
    for cs in contents[1:]:
        for part in cs:flat.append(part.move(bd.Pos(0,0,ARM_Z_SHIFT)))
    def servo_component(part):
        label=part.label;leaves=[]
        def visit(node,color=None):
            color=node.color or color
            if node.children:
                for c in take_children(node):visit(c,color)
            else:
                node.label=f'{label}_detail_{len(leaves)+1:02d}'
                if color is not None:node.color=color
                leaves.append(node)
        visit(part)
        assert len(leaves)==16,(label,len(leaves))
        return bd.Compound(children=leaves,label=label)
    result=[]
    for part in flat:
        if part.label.endswith('_servo'):
            part=servo_component(part)
        elif part.children and not ('screws' in part.label or 'fasteners' in part.label or 'hardware' in part.label):
            part=bd.Compound(obj=part.solids(),label=part.label,color=part.color)
        result.append(part)
    wrist_yoke=revised_yaw_yoke(old_yaw,bottom_hook=False).moved(bd.Pos(0,0,ARM_Z_SHIFT))
    from lib.tom2_link_profiles import resize_rest_links
    rest=resize_rest_links(bake_rest(result),shoulder_web_x=WEB_X)
    return bd.Compound(children=replace_gripper_with_yoke(rest,wrist_yoke),label='tom2')


@memo
def tom2():
    from end_effector.servo6_gripper_concept import make_connector
    arm=arm_with_inline_wrist()
    parts=list(arm.children);arm.children=()
    from lib.elbow_yoke_integration import integrate
    connector=[p.moved(bd.Pos(0,0,-LINK_HEIGHT_REDUCTION_MM)) for p in make_connector()]
    result=integrate(parts+connector,original_kinematics())
    return bd.Compound(children=result,label='tom2')
