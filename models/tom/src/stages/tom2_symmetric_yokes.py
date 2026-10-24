"""Three identical symmetric yokes, with narrow collars and side-three forks.

Compact geometry experiment. The flipped elbow attachment clears its local
yoke roll sweep; full-arm collision envelopes remain a separate constraint.
"""
from dataclasses import asdict
import build123d as bd
from cadgen import memo
from lib.mates import revolute
from stages.tom2_side_mounted_elbow import tom2_side_mounted_elbow,preview_kinematics
from lib.symmetric_horn_yoke import make_yoke,PITCH,ROLL,T,WEB_X,AXIS_OFFSET,AXIS_SPACING_REDUCTION
from hardware.hex_socket_cap import hex_socket_m3x5,hex_socket_m2x6
from lib.materials import SCREW_COLOR
from lib.booleans import as_single_shape as one
from lib.tom2_link_profiles import _unify
from lib.rectangular_upper_link import rectangular_upper_link,WRIST_RAISE,match_upper_height
from lib.flipped_elbow_mount import flip_servo,shorten_case_mount,round_mount_clearance
from lib.extend_link_fold import extend_link_fold
from lib.flush_upper_link import flush_upper_link
from lib.balanced_link_height import LOWER_EXTENSION,ELBOW_BALANCE_DROP,extend_lower_down

A=(AXIS_SPACING_REDUCTION,-.5,AXIS_OFFSET)
B=(AXIS_OFFSET+AXIS_SPACING_REDUCTION,0,AXIS_OFFSET-AXIS_SPACING_REDUCTION)
C=(AXIS_OFFSET+2*AXIS_SPACING_REDUCTION,-.5,-AXIS_SPACING_REDUCTION)
ELBOW_DROP=36.975-39.14248774003746-ELBOW_BALANCE_DROP


def align_upper_link_fold(part,servo):
    """Raise the lower outline and formed floor to the servo casing edge.

    The one-millimetre end rounds move with the fold; mounting holes and
    everything above that small strip stay at their existing datums.
    """
    old_tangent=part.bounding_box().min.Z+T+.9652
    target=servo.bounding_box().min.Z
    dz=target-old_tangent
    split=old_tangent+1.001  # Above the complete 1 mm end rounds.
    def region(z0,z1):
        return bd.Solid.make_box(1000,1000,z1-z0,
                                bd.Plane(origin=(-500,-500,z0)))
    fold=one(part.intersect(region(-500,split))).moved(bd.Pos(0,0,dz))
    upper=one(part.intersect(region(split+dz,500)))
    result=_unify(one(upper.fuse(fold)).clean())
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result


def raise_lower_roof(part,dz):
    """Extend the side flats; retain the formed roof and its bend radii."""
    split=part.bounding_box().max.Z-(T+.9652)-1.001
    def region(z0,z1):
        return bd.Solid.make_box(1000,1000,z1-z0,
                                bd.Plane(origin=(-500,-500,z0)))
    roof=one(part.intersect(region(split,500)))
    base=one(part.intersect(region(-500,split)))
    sections=[f for f in roof.faces() if f.geom_type==bd.GeomType.PLANE
              and abs(f.center().Z-split)<1e-5 and f.normal_at().Z<-.999]
    bridges=[bd.Solid.extrude(f,(0,0,dz)) for f in sections]
    result=_unify(one(base.fuse(roof.moved(bd.Pos(0,0,dz)),*bridges)).clean())
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result


def trim_lower_link(part,servo):
    """Align the lower edge with the pitch-fork top and the end with the case."""
    floor=anchors()['shoulderPitch'][2]+5.5
    x_min=servo.bounding_box().min.X
    region=bd.Solid.make_box(500-x_min,1000,500-floor,
                            bd.Plane(origin=(x_min,-500,floor)))
    result=one(part.intersect(region)).clean()
    corners=[e for e in result.edges() if e.geom_type==bd.GeomType.LINE
             and abs(e.length-T)<1e-5 and abs(e.center().Z-floor)<1e-5
             and abs(e.start_point().Y-e.end_point().Y)>T-1e-5]
    if corners:result=result.fillet(1.0,corners)
    result=extend_lower_down(result,WEB_X+anchors()['shoulderPitch'][0]-PITCH[0])
    bores=[]
    for f in part.faces():
        if f.geom_type!=bd.GeomType.CYLINDER or abs(f.radius-1.1)>1e-6:continue
        b=f.bounding_box()
        if b.min.X>100 and abs(b.size.Y-T)<1e-5:
            bores.append(((b.min.X+b.max.X)/2,b.min.Y,(b.min.Z+b.max.Z)/2))
    assert len(bores)==4
    plugs=[bd.Solid.make_cylinder(1.1001,T,bd.Plane(origin=(x,y,z),z_dir=(0,1,0))) for x,y,z in bores]
    result=one(result.fuse(*plugs))
    cuts=[bd.Solid.make_cylinder(1.1,T+2,bd.Plane(origin=(x,y-1,z+ELBOW_DROP),z_dir=(0,1,0))) for x,y,z in bores]
    result=one(result.cut(*cuts))
    result=_unify(result.clean())
    assert result.is_valid and len(result.solids())==1
    result.label=part.label;result.color=part.color
    return result


def descendants(root):
    refs={root};mates=preview_kinematics()['mates']
    while True:
        grown=refs|{m.child for m in mates if m.parent in refs}
        if grown==refs:return refs
        refs=grown


def stages():
    return [descendants('#shoulder_pitch_yoke'),descendants('#elbow_roll_servo'),
            descendants('#wrist_yaw_servo'),
            descendants('#temporary_wrist_yoke')|descendants('#wrist_pitch_servo'),
            descendants('#elbow_pitch_yoke')|descendants('#elbow_pitch_servo')]


def delta(label,groups,default=(0,0,0)):
    def dropped(d):return (d[0],d[1],d[2]+ELBOW_DROP)
    def raised(d):return (d[0],d[1],d[2]+WRIST_RAISE+ELBOW_DROP)
    if label=='elbow_roll__hex_socket_m3x5__center':return dropped(B)
    if label=='shoulder_pitch__hex_socket_m3x5__center':return A
    if label.startswith('elbow_side_m2x6_'):return dropped(A)
    if label.startswith('wrist_yaw_m3x5_') or label=='wrist_yaw__hex_socket_m3x5__center':return raised(C)
    if label in {f'elbow_roll_link_plate_pair__hex_socket_m2x6__{i:02d}' for i in (3,4,5,6)}:
        return raised(B)
    for refs,d in reversed(list(zip(groups[:3],(A,B,C)))):
        if '#'+label in refs:
            if '#'+label in groups[3]:return raised(d)
            return dropped(d) if '#'+label in groups[4] else d
    return default


def anchors():
    axes={m.name:asdict(m)['axis']['origin'] for m in preview_kinematics()['mates']
          if asdict(m)['kind']=='revolute'}
    return {name:tuple(a+b for a,b in zip(axes[name],d)) for name,d in
            (('shoulderPitch',A),('elbowPitch',(A[0],A[1],A[2]+ELBOW_DROP)),('wristPitch',(B[0],B[1],B[2]+WRIST_RAISE+ELBOW_DROP)))}


def kinematics():
    data=preview_kinematics();groups=stages();mates=[]
    for m in data['mates']:
        row=asdict(m)
        if row['kind']=='revolute':
            d=delta(m.child.lstrip('#'),groups)
            m=revolute(m.name,parent=m.parent,child=m.child,
                origin=[a+b for a,b in zip(row['axis']['origin'],d)],
                direction=row['axis']['dir'],limits=row['limits']['value'])
        mates.append(m)
    return dict(mates=mates,poses=data['poses'])


def place(part,joint):
    # Only positions normal to the joint axis define the horn seating center.
    target=anchors()[joint];target=(target[0],-.5 if joint!='wristPitch' else 0,target[2])
    if joint=='elbowPitch':part=part.rotate(bd.Axis(PITCH,(0,1,0)),-90)
    if joint=='wristPitch':part=part.rotate(bd.Axis(PITCH,(0,0,1)),180)
    return part.moved(bd.Pos(*(a-b for a,b in zip(target,PITCH))))


def horn_bolt(name,joint,index,roll=False):
    side=-1 if index<3 else 1; j=index%3
    if roll:
        dx,dy=((-7,0),(0,-7),(0,7))[j]
        pt=(ROLL[0]+dx,dy,ROLL[2]+side*(18.3+T));normal=(0,0,side)
    else:
        dx,dz=((0,-7),(7,0),(0,7))[j]
        pt=(PITCH[0]+dx,side*(18.3+T),PITCH[2]+dz);normal=(0,side,0)
    part=hex_socket_m3x5().moved(bd.Plane(origin=pt,z_dir=normal).location)
    part=place(part,joint);part.label=name;part.color=SCREW_COLOR
    return part


@memo
def tom2_symmetric_yokes():
    source=tom2_side_mounted_elbow();groups=stages();common=make_yoke()
    replacements={}
    by={p.label:p for p in source.children}
    link=align_upper_link_fold(by['elbow_roll_link_plate_pair'],by['wrist_pitch_servo'])
    lower=by['shoulder_pitch_yoke']
    # Retain the previous link profile; flushness no longer constrains collars.
    # The roof was matched at 0.8 mm collar reduction in the prior revision.
    roof_raise=link.bounding_box().min.Z+AXIS_OFFSET-.8-(lower.bounding_box().max.Z+A[2])
    lower=raise_lower_roof(lower,roof_raise).moved(bd.Pos(*A))
    replacements[lower.label]=extend_link_fold(trim_lower_link(lower,by['shoulder_pitch_servo'].moved(bd.Pos(*A))))
    mid_x=anchors()['elbowPitch'][0]
    link=rectangular_upper_link(link).moved(bd.Pos(*B))
    link=round_mount_clearance(shorten_case_mount(link,mid_x))
    replacements[link.label]=extend_link_fold(match_upper_height(link,replacements[lower.label].bounding_box().size.Z-LOWER_EXTENSION).moved(bd.Pos(0,0,ELBOW_DROP)),roof=False)
    replacements[link.label]=flush_upper_link(replacements[link.label],replacements[lower.label])
    assert abs(replacements[link.label].bounding_box().size.Z-replacements[lower.label].bounding_box().size.Z)<1e-5
    s4=by['elbow_roll_servo'].moved(bd.Pos(B[0],B[1],B[2]+ELBOW_DROP))
    replacements[s4.label]=flip_servo(s4,mid_x)
    for label,joint in (('shoulder_yaw_yoke','shoulderPitch'),
                        ('elbow_pitch_yoke','elbowPitch'),('temporary_wrist_yoke','wristPitch')):
        q=place(common,joint);q.label=label;replacements[label]=q
    def visit(p,inherited=(0,0,0)):
        shift=delta(p.label,groups,inherited)
        if p.label in replacements:return replacements[p.label]
        if p.label=='elbow_roll__hex_socket_m3x5__center':
            return flip_servo(p.moved(bd.Pos(B[0],B[1],B[2]+ELBOW_DROP)),mid_x)
        if p.label in {f'elbow_roll_link_plate_pair__hex_socket_m2x6__{i:02d}' for i in (1,2,7,8)}:
            i=int(p.label.rsplit('_',1)[1]);y=9.75 if i<7 else -10.75
            z=anchors()['wristPitch'][2]-WRIST_RAISE+(8.3 if i in (1,7) else 29.0)
            seat=replacements[link.label].bounding_box().max.X-T
            q=hex_socket_m2x6().moved(bd.Plane(origin=(seat,y,z),z_dir=(-1,0,0)).location)
            q.label=p.label;q.color=SCREW_COLOR;return q
        if p.label.startswith('pitch_horn_m3x5_'):
            return horn_bolt(p.label,'shoulderPitch',int(p.label.rsplit('_',1)[1])-1)
        if p.label.startswith('temporary_wrist_m3x5_'):
            return horn_bolt(p.label,'wristPitch',int(p.label.rsplit('_',1)[1])-1)
        if p.label.startswith('integrated_elbow_horn_m3x5_'):
            i=int(p.label.rsplit('_',1)[1])-1
            return horn_bolt(p.label,'elbowPitch',(i//6)*3+i%3,roll=(i%6>=3))
        # Servo subassemblies carry their own detailed horns at the new axis.
        if p.label in ('shoulder_pitch_servo','elbow_pitch_servo','elbow_roll_servo','wrist_pitch_servo','wrist_yaw_servo'):
            return p.moved(bd.Pos(*shift))
        if p.children:
            loc=p.location;children=list(p.children);p.children=()
            return bd.Compound(children=[visit(c,shift) for c in children],label=p.label,color=p.color).moved(loc)
        return p.moved(bd.Pos(*shift))
    result=visit(source);result.label='tom2_symmetric_yokes';return result
