"""Component stock for the current arm, without building discarded link revisions.

Only the two gripper parts need the historical solid-layout finishing datums.
All other layout changes are compiled into occurrence Locations. These nodes
are recipes, not native assemblies; final native groups are created exactly
once by current_arm_parts after each part has its finished geometry.
"""
from dataclasses import dataclass,field
import build123d as b
from lib.current_arm_parts import placed_native


@dataclass
class Stock:
    label: str
    color: object
    location: object
    part: object=None
    children: list=field(default_factory=list)

    @property
    def wrapped(self):
        assert self.part is not None and not self.children
        # Return a fresh shallow occurrence handle, retaining shared topology.
        return self.part.wrapped.Located(self.location.wrapped)


def record(part):
    return Stock(part.label,part.color,part.location,
                 part if not part.children else None,[record(c) for c in part.children])


def component_stock(source):
    from stages import tom2_500mm as short
    from stages import tom2_600mm_solid as solid
    from lib import base_direct_clamp as bay
    from lib.tapered_solid_links import REMOVED_SHOULDER_SCREWS,COMPACT_DROP,WRIST_INSET,LINK_TRANSFER
    from lib.straight_gripper import make_straight_gripper,AXIS_XY,HORN_PATTERN_TURN
    from lib.gripper_063 import THICKNESS as GRIPPER_T
    from lib.gripper_mount_finish import narrow_camera_support,underside_mounting_prong
    from lib.elbow_roll_alignment import ROLL_RISE
    groups=short.moving_sets();distal=set().union(*groups)
    stock=record(source)
    # Compile the two earlier layout translations as metadata. Servo groups
    # receive each translation at their root; all other groups pass it to leaves.
    def pre(n,dx500=0.,dz500=0.,dx600=0.,inside500=False,inside600=False):
        dx500=short.offset(n.label,groups,dx500)
        dz500=-short.WRIST_DROP if '#'+n.label in groups[1] else dz500
        dx600=solid.extension_offset(n.label,dx600)
        servo500=n.label in {'shoulder_yaw_servo','shoulder_pitch_servo','elbow_pitch_servo',
                            'elbow_roll_servo','wrist_pitch_servo','wrist_yaw_servo','gripper_jaw_servo'}
        servo600=n.label.endswith('_servo')
        if not inside500 and (servo500 or not n.children):
            n.location=b.Pos(dx500,0,dz500)*n.location
        if n.label=='direct_servo_clamp':return record(bay.clamp())
        if n.label=='m8_thumbscrew':
            n.location=b.Pos(bay.CLAMP_SCREW_X+17.5,0,bay.THUMB_SHIFT_Z)*n.location
        elif n.label.startswith('clamp_standoff_screw_'):
            return record(bay.servo_screw(int(n.label.rsplit('_',1)[1])))
        elif not inside600 and (servo600 or not n.children):
            n.location=b.Pos(dx600,0,solid.BUILD_ARM_RISE)*n.location
        n.children=[pre(c,dx500,dz500,dx600,inside500 or servo500,inside600 or servo600)
                    for c in n.children if not c.label.startswith('servo_standoff_')
                    and c.label not in REMOVED_SHOULDER_SCREWS]
        return n
    stock=pre(stock)
    lookup={};ancestors={}
    def index(n,a):
        lookup[n.label]=n;ancestors[n.label]=a
        for c in n.children:index(c,a*n.location)
    index(stock,b.Location())
    def world(name):return placed_native(lookup[name],ancestors[name])
    fixed,moving,phase,camera=make_straight_gripper(world('servo6_fixed_gripper_frame'),world('gripper_right_claw'))
    fixed=underside_mounting_prong(narrow_camera_support(fixed))
    replacements={p.label:p for p in (fixed,moving,camera)}
    screw_seats={'gripper_frame__hex_socket_m2x6__01','gripper_frame__hex_socket_m2x6__02',
        'gripper_frame__hex_socket_m2x6__06','gripper_frame__hex_socket_m2x6__07',
        'gripper_left_claw__hex_socket_m2x6__01',
        'servo6_case_m2x6_13','servo6_case_m2x6_14','servo6_case_m2x6_15','servo6_case_m2x6_16'}
    axis=b.Axis((*AXIS_XY,0),(0,0,1))
    for name,n in lookup.items():
        replacement=replacements.get(name)
        if replacement is not None:
            q=record(replacement);q.location=ancestors[name].inverse()*q.location
            n.part,n.location,n.children=q.part,q.location,q.children
        elif name in ('inline_jaw_drive_horn','inline_jaw_idler_horn') or name.startswith('gripper_right_claw__'):
            turn=phase+(HORN_PATTERN_TURN if name.startswith('gripper_right_claw__') else 0)
            q=world(name).rotate(axis,turn)
            if name.startswith('gripper_right_claw__'):
                dz=(GRIPPER_T-2.032)*(1 if q.bounding_box().center().Z>142.9299110455 else -1)
                q=placed_native(q,b.Pos(0,0,dz))
            n.part=q;n.location=ancestors[name].inverse()*q.location
        elif name in screw_seats:
            q=world(name)
            dz=(GRIPPER_T-2.032)*(1 if q.bounding_box().center().Z>142.9299110455 else -1)
            n.location=ancestors[name].inverse()*b.Pos(0,0,dz)*ancestors[name]*n.location
    roll_group={'elbow_pitch_yoke','elbow_roll_servo','elbow_pitch_servo','elbow_yoke_horn_screws',
        'elbow_roll__hex_socket_m3x5__center','elbow_pitch__hex_socket_m3x5__center'}
    roll_group.update(f'elbow_side_m2x6_{i}' for i in range(1,5))
    roll_group.update(f'elbow_roll_link_plate_pair__hex_socket_m2x6__{i:02}' for i in (1,2,7,8))
    elbow_group=roll_group|{'elbow_roll_link_plate_pair'}
    fixed_roots={'direct_servo_clamp','m8_thumbscrew','clamp_mounting_hardware'}
    # Only this recipe walk remains. It combines all downstream placements;
    # there is no native assembly to copy or repeatedly relocate here.
    def final(n,old_parent,new_parent,depth=0,shortened=False,arm=False,roll=False,forearm=None):
        old_world=old_parent*n.location
        shortened=shortened or '#'+n.label in distal
        if depth==1:arm=n.label not in fixed_roots
        roll=roll or n.label in roll_group
        if forearm is None:
            if '#'+n.label in groups[1]:forearm=(WRIST_INSET+2*LINK_TRANSFER,solid.WRIST_SHIFT)
            elif n.label in elbow_group:forearm=(LINK_TRANSFER,-COMPACT_DROP)
        dx=(-solid.SHOULDER_LINK_CUT if shortened else 0)+(bay.SERVO_SHIFT_X if arm else 0)
        dz=(bay.FINAL_ARM_SHIFT if arm else 0)+(ROLL_RISE if roll else 0)
        if forearm is not None:dx+=forearm[0];dz+=forearm[1]
        new_world=b.Pos(dx,0,dz)*old_world
        n.location=new_parent.inverse()*new_world
        for c in n.children:final(c,old_world,new_world,depth+1,shortened,arm,roll,forearm)
        return n
    stock=final(stock,b.Location(),b.Location())
    stock.children.append(record(bay.fixed_bay()))
    stock.label='tom'
    return stock
