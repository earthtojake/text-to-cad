"""Identical taller yokes with the lower arm held at its existing rest datum."""
from dataclasses import asdict
from lib.mates import revolute

AXIS_INCREASE = 5.0  # Additional 1 mm on each of the two equal collar lands.
UPPER_TOE_CLEARANCE = 0.8
# Forearm-roll axis lies along X. Keep the notch wall 5 mm behind
# the wrist-side horn screw heads throughout rotation about that axis.
ROLL_NOTCH_SCREW_CLEARANCE = 5.0
UPPER_RELIEF_X = 122.27722789367 - ROLL_NOTCH_SCREW_CLEARANCE
COLLAR_EXTENSION = AXIS_INCREASE / 2


def motion_map(data):
    def descendants(root):
        refs={root}
        while True:
            more=refs|{m.child.lstrip('#') for m in data['mates'] if m.parent.lstrip('#') in refs}
            if more==refs:return refs
            refs=more
    up=(0,0,AXIS_INCREASE);distal=(-AXIS_INCREASE,0,AXIS_INCREASE)
    shifts={n:up for n in descendants('elbow_roll_servo')}
    shifts.update({n:distal for n in descendants('wrist_yaw_servo')})
    for n in ['elbow_roll__hex_socket_m3x6__center',*[f'elbow_roll_servo_detail_{i}' for i in (14,15,16)]]:
        shifts[n]=up
    for i in range(1,13):
        if (i-1)%6>=3:shifts[f'integrated_elbow_horn_m3x6_{i}']=up
    for n in [*[f'wrist_yaw_servo_detail_{i}' for i in (14,15,16)],*[f'wrist_yaw_m3x6_{i}' for i in range(1,8)]]:
        shifts[n]=distal
    for n in ['shoulder_yaw_servo','shoulder_yaw__hex_socket_m3x6__center',
              *[f'shoulder_yaw_servo_detail_{i}' for i in range(1,17)],
              *[f'shoulder_yaw_yoke__hex_socket_m3x6__{i:02}' for i in (3,4,5,8,9,10)],
              *[f'clamp_standoff_screw_{i}' for i in range(1,5)]]:
        shifts[n]=(AXIS_INCREASE,0,0)
    return shifts


def revised_kinematics(data):
    offsets={'shoulderYaw':(AXIS_INCREASE,0,0), 'elbowRoll':(0,0,AXIS_INCREASE),
             'wristPitch':(0,0,AXIS_INCREASE), 'wristYaw':(-AXIS_INCREASE,0,AXIS_INCREASE),
             'gripperJaw':(-AXIS_INCREASE,0,AXIS_INCREASE)}
    mates=[]
    for m in data['mates']:
        r=asdict(m)
        if r['kind']=='revolute' and m.name in offsets:
            m=revolute(m.name,parent=m.parent,child=m.child,
                       origin=[a+d for a,d in zip(r['axis']['origin'],offsets[m.name])],
                       direction=r['axis']['dir'],limits=r['limits']['value'])
        mates.append(m)
    return data|{'mates':mates}
