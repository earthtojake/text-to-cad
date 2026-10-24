"""Shoulder-style formed elbow yoke and clearanced upper-link interface."""
import build123d as bd
from lib.booleans import as_single_shape as one
from lib import horn_cap
from lib.tom2_dimensions import LINK_HEIGHT_REDUCTION_MM as HEIGHT_DROP, COLLAR_SHORTEN_MM

T=2.032
RI=.9652
RO=T+RI
PITCH_X=162.875916240922
PITCH_Z=56.675-HEIGHT_DROP
ROLL_Z=90.675-HEIGHT_DROP
ROLL_Y=-.5
OLD_ROLL_X=123.578716240922
COLLAR_DROP=18.3-RI-horn_cap.CIRCULAR_HORN_FORK_PATTERN.outer_radius_mm
ROLL_X=PITCH_X-COLLAR_DROP
SHIFT_X=ROLL_X-OLD_ROLL_X
COLLAR_HALF_WIDTH=5.5
WEB_TOP=73.25048774003745-HEIGHT_DROP+COLLAR_SHORTEN_MM
BASE_SHIFT=(1.15,-.5,0)
PITCH_TOP=4.5
# Keep the compact horn-following outline. Offset the two joint interfaces
# instead of stretching the flange to reach the lower bend tangent.
PITCH_BOTTOM=horn_cap.CIRCULAR_HORN_FORK_PATTERN.outer_radius_mm


def box(x0,x1,y0,y1,z0,z1):
    return bd.Solid.make_box(x1-x0,y1-y0,z1-z0,bd.Plane(origin=(x0,y0,z0)))


def make_yoke(shoulder):
    p=(-51.5,0,28.675)
    copy=shoulder.rotate(bd.Axis(p,(0,1,0)),-90).moved(bd.Pos(PITCH_X-p[0],0,PITCH_Z-p[2]))
    # Keep the broad pitch flanges and their continuous cross-sheet. Rebuild
    # the roll arms on the original rest height with narrower forming lands.
    result=one(copy.intersect(box(100,220,-30,30,0,WEB_TOP)))
    roll_pieces=[]
    for sign in (-1,1):
        seat=ROLL_X+sign*18.3
        x0=min(seat,seat+sign*T)
        cx=seat-sign*RI
        zt=WEB_TOP+RI
        disc=bd.Solid.make_cylinder(horn_cap.CIRCULAR_HORN_FORK_PATTERN.outer_radius_mm,T,bd.Plane(origin=(x0,ROLL_Y,ROLL_Z),z_dir=(1,0,0)))
        stem=box(x0,x0+T,ROLL_Y-COLLAR_HALF_WIDTH,ROLL_Y+COLLAR_HALF_WIDTH,zt,ROLL_Z)
        cap=one(disc.fuse(stem))
        cap=horn_cap.apply_horn_fork(cap,center=(x0+T/2,ROLL_Y,ROLL_Z),
            across=(0,1,0),outboard=(0,0,1),normal=(1,0,0),thickness_mm=T,
            half_width_mm=horn_cap.CIRCULAR_HORN_FORK_PATTERN.outer_radius_mm,
            pattern=horn_cap.CIRCULAR_HORN_FORK_PATTERN)
        roots=[e for e in cap.edges().filter_by(bd.Axis.X)
               if zt+1 < e.center().Z < ROLL_Z-1
               and abs(abs(e.center().Y-ROLL_Y)-COLLAR_HALF_WIDTH)<1e-6]
        assert len(roots)==2
        cap=cap.fillet(.6,roots).clean()
        pl=bd.Plane(origin=(cx,ROLL_Y-COLLAR_HALF_WIDTH,zt),z_dir=(0,1,0))
        ring=bd.Solid.make_cylinder(RO,2*COLLAR_HALF_WIDTH,pl).cut(bd.Solid.make_cylinder(RI,2*COLLAR_HALF_WIDTH,pl))
        xa,xb=sorted((cx,cx+sign*RO))
        bend=one(ring.intersect(box(xa,xb,ROLL_Y-COLLAR_HALF_WIDTH,ROLL_Y+COLLAR_HALF_WIDTH,zt-RO,zt)))
        roll_pieces.extend((cap,bend))
    # At the near roll collar, continue its narrow land through the base
    # sheet. The broad pitch gusset starts farther inboard so the link's
    # return can sweep past the flange at both 90-degree limits.
    for ya,yb in ((-30,ROLL_Y-COLLAR_HALF_WIDTH),(ROLL_Y+COLLAR_HALF_WIDTH,30)):
        result=one(result.cut(box(100,ROLL_X-13.25,ya,yb,0,WEB_TOP+.001)))
    for ya,yb in ((-30,ROLL_Y-COLLAR_HALF_WIDTH),(ROLL_Y+COLLAR_HALF_WIDTH,30)):
        result=one(result.cut(box(PITCH_X+PITCH_BOTTOM,220,ya,yb,0,WEB_TOP+.001)))
    # Reauthor the central flat as one tapered profile. Shared end points
    # meet each bend land directly instead of leaving rectangular patches.
    lx=ROLL_X-18.3+RI
    rx=ROLL_X+18.3-RI
    a=PITCH_X-PITCH_TOP
    b=PITCH_X+PITCH_BOTTOM
    half_pitch=18.3-RI
    outline=[(lx,ROLL_Y-COLLAR_HALF_WIDTH),(a,-half_pitch),
             (b,-half_pitch),(rx,ROLL_Y-COLLAR_HALF_WIDTH),
             (rx,ROLL_Y+COLLAR_HALF_WIDTH),(b,half_pitch),
             (a,half_pitch),(lx,ROLL_Y+COLLAR_HALF_WIDTH)]
    flat=bd.Face(bd.Wire.make_polygon([(x,y,WEB_TOP-T) for x,y in outline],close=True))
    web=bd.Solid.extrude(flat,(0,0,T))
    # Only replace the flat between tangent lines, preserving formed bends.
    old_flat=box(100,220,-half_pitch,half_pitch,WEB_TOP-T,WEB_TOP+.001)
    result=one(result.cut(old_flat).fuse(web,*roll_pieces)).clean()
    # Level the outer return lands with the pitch flange's straight top.
    # This lets the link's straight lower edge seat without intersecting the
    # tapered cross-sheet. Preserve the full-width center and both roll bends.
    for ya,yb in ((-30,-15.5),(15.5,30)):
        result=one(result.cut(box(100,a,ya,yb,0,WEB_TOP+.001))).clean()
    assert result.is_valid and len(result.solids())==1
    result.label='elbow_pitch_yoke';result.color=shoulder.color
    return result


def moved_references(kinematics):
    from dataclasses import asdict
    refs={'#elbow_roll_servo'}
    rows=[asdict(m) for m in kinematics['mates']]
    for _ in rows:
        grown=refs|{m['child'] for m in rows if m['parent'] in refs}
        if grown==refs:break
        refs=grown
    return refs


def obsolete_screw(label):
    return label.startswith('elbow_pitch_yoke__hex_socket_m3x5__')


def update_kinematics(original):
    from dataclasses import asdict
    from lib.mates import revolute, fastened
    refs=moved_references(original)
    mates=[]
    for m in original['mates']:
        row=asdict(m)
        if obsolete_screw(row['child'].lstrip('#')):continue
        if row['kind']=='revolute' and row['name']=='shoulderYaw':
            o=[v+d for v,d in zip(row['axis']['origin'],BASE_SHIFT)]
            mates.append(revolute(row['name'],parent=row['parent'],child=row['child'],
                origin=o,direction=row['axis']['dir'],limits=row['limits']['value']))
        elif row['kind']=='revolute' and row['child'] in refs:
            o=list(row['axis']['origin']);o[0]+=SHIFT_X;o[2]-=COLLAR_DROP
            mates.append(revolute(row['name'],parent=row['parent'],child=row['child'],
                origin=o,direction=([-v for v in row['axis']['dir']] if row['name']=='elbowRoll' else row['axis']['dir']),limits=row['limits']['value']))
        elif row['kind']=='revolute':
            o=list(row['axis']['origin']);o[2]-=COLLAR_DROP
            mates.append(revolute(row['name'],parent=row['parent'],child=row['child'],
                origin=o,direction=row['axis']['dir'],limits=row['limits']['value']))
        else:mates.append(m)
    mates.append(fastened('integrated_elbow_hardware',parent='#elbow_pitch_yoke',child='#elbow_yoke_horn_screws'))
    for servo in ('elbow_pitch_servo','elbow_roll_servo'):
        mates.append(fastened(servo+'_shaft_fixed',parent='#elbow_pitch_yoke',child='#'+servo+'_detail_14'))
    poses=dict(original['poses'])
    poses.update(elbow_roll_minus_90={'elbowPitch':90,'elbowRoll':-90},
                 elbow_roll_plus_90={'elbowPitch':90,'elbowRoll':90},
                 elbow_open={'elbowPitch':90})
    return {'mates':mates,'poses':poses}


def integrate(parts,kinematics):
    from hardware.hex_socket_cap import hex_socket_m3x5
    from lib.materials import SCREW_COLOR
    refs=moved_references(kinematics)
    refs.add('#elbow_roll__hex_socket_m3x5__center')
    shoulder=next(p for p in parts if p.label=='shoulder_yaw_yoke')
    yoke=make_yoke(shoulder)
    # The same manufactured solid serves both joints. The final lowering
    # step seats its compact side connection at the lower U-bend tangent.
    common_shoulder=yoke.moved(bd.Pos(-PITCH_X-51.5,0,28.675-PITCH_Z)).rotate(
        bd.Axis((-51.5,0,28.675),(0,1,0)),90)
    common_shoulder.label='shoulder_yaw_yoke'
    base_parts={'direct_servo_clamp','shoulder_yaw_servo','m8_thumbscrew','clamp_mounting_hardware'}
    def visit(p):
        if obsolete_screw(p.label):return None
        if p.label=='elbow_pitch_yoke':return yoke
        if p.label=='shoulder_yaw_yoke':return common_shoulder
        if p.label in base_parts:return p.moved(bd.Pos(*BASE_SHIFT))
        if p.label.startswith('shoulder_yaw_yoke__hex_socket_m3') or p.label=='shoulder_yaw__hex_socket_m3x5__center':
            return p.moved(bd.Pos(*BASE_SHIFT))
        if '#'+p.label in refs:return p.moved(bd.Pos(SHIFT_X,0,0))
        if p.children:
            children=[q for c in p.children if (q:=visit(c)) is not None]
            if not children:return None
            return bd.Compound(children=children,label=p.label,color=p.color).moved(p.location)
        return p
    result=[q for p in parts if (q:=visit(p)) is not None]
    hardware=[];model=hex_socket_m3x5()
    def add(point,normal):
        q=model.moved(bd.Plane(origin=point,z_dir=normal).location)
        q.label=f'integrated_elbow_horn_m3x5_{len(hardware)+1}'
        q.color=SCREW_COLOR;hardware.append(q)
    for sign in (-1,1):
        for dx,dz in ((0,-7),(7,0),(0,7)):
            add((PITCH_X+dx,sign*(18.3+T),PITCH_Z+dz),(0,sign,0))
        for dy,dz in ((-7,0),(0,-7),(7,0)):
            add((ROLL_X+sign*(18.3+T),ROLL_Y+dy,ROLL_Z+dz),(sign,0,0))
    result.append(bd.Compound(children=hardware,label='elbow_yoke_horn_screws'))
    result=flip_servo_and_wrap(result)
    # Lower the horn-connected arm with its actual servo interfaces. The
    # base U, its horn screws and grounded servo stay at their existing height.
    def lower(p):
        if p.label in base_parts or p.label.startswith('shoulder_yaw_yoke__hex_socket_m3') or p.label=='shoulder_yaw__hex_socket_m3x5__center':
            return p
        if p.children:
            return bd.Compound(children=[lower(c) for c in p.children],label=p.label,color=p.color).moved(p.location)
        return p.moved(bd.Pos(0,0,-COLLAR_DROP))
    return [lower(p) for p in result]


def flip_servo_and_wrap(parts):
    by={p.label:p for p in parts}
    flip=bd.Axis((ROLL_X,ROLL_Y,ROLL_Z),(0,0,1))
    motor=by['elbow_roll_servo'].rotate(flip,180)
    motor.label='elbow_roll_servo'
    plate=by['elbow_roll_link_plate_pair'].solids()[0]
    old_outer=plate.bounding_box().max.X
    old_tangent=old_outer-RO
    new_inner=2*ROLL_X-old_outer
    shift=new_inner-(old_outer-T)
    mount=one(plate.intersect(box(old_tangent,old_outer+1,-40,40,ROLL_Z+6,140)))
    retained=one(plate.intersect(box(-300,old_tangent,-40,40,0,150)))
    mount=mount.moved(bd.Pos(shift,0,0))
    bridges=[box(old_tangent-.001,old_tangent+shift+.001,y,y+T,
                 ROLL_Z+6,plate.bounding_box().max.Z) for y in (-18.532,15.5)]
    link=one(retained.fuse(mount,*bridges)).clean()
    # A shared shallow arch under the two extensions clears the tapered
    # yoke web at full roll. Keep the four underside screw pads intact.
    # Extend the rounded upper corner 0.6 mm for the shorter roll collars.
    relief=[(ROLL_X-23.7002,0),(ROLL_X+23,0),
            (ROLL_X+23,ROLL_Z+6.5),(ROLL_X+20.0,ROLL_Z+6.5),
            (ROLL_X+16.6,ROLL_Z+22.325),(ROLL_X-3.9,ROLL_Z+22.325),
            (ROLL_X-23.7002,ROLL_Z+6.5)]
    for y,depth in ((14.5348,10),(-15.5348,-10)):
        f=bd.Face(bd.Wire.make_polygon([(x,y,z) for x,z in relief],close=True))
        corners=[v for v in f.vertices() if v.center().Z>ROLL_Z+19.325]
        f=f.fillet_2d(2.0,corners)
        link=one(link.cut(bd.Solid.extrude(f,(0,depth,0))))
    link=link.clean()
    assert link.is_valid and len(link.solids())==1
    link.label='elbow_roll_link_plate_pair';link.color=by['elbow_roll_link_plate_pair'].color
    def hardware(p):
        if p.label=='elbow_roll__hex_socket_m3x5__center' or (
            p.label.startswith('elbow_roll_link_plate_pair__hex_socket_m2x6') and p.bounding_box().min.X>140):
            return p.rotate(flip,180)
        if p.children:
            return bd.Compound(children=[hardware(c) for c in p.children],label=p.label,color=p.color).moved(p.location)
        return p
    result=[]
    for p in parts:
        if p.label=='elbow_roll_servo':p=motor
        elif p.label=='elbow_roll_link_plate_pair':p=link
        else:p=hardware(p)
        result.append(p)
    return result
