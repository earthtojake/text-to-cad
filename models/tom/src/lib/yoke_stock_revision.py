"""ALU-125 yoke adaptation; baseline coordinates precede the 12 mm base retraction."""
from dataclasses import asdict,replace
from lib.yoke_125_geometry import PITCH,ROLL,T

OLD_T=2.032
OLD_SPAN=31.1624
SPAN=ROLL[0]-PITCH[0]
D=SPAN-OLD_SPAN
THICKNESS_DELTA=T-OLD_T
ZERO={'shoulderYaw':0.,'shoulderPitch':-90.,'elbowPitch':90.,'elbowRoll':0.,'wristPitch':0.,'wristYaw':0.,'gripperJaw':0.}


def motion_map(data):
    def descendants(root):
        refs={root}
        while True:
            more=refs|{m.child.lstrip('#') for m in data['mates'] if m.parent.lstrip('#') in refs}
            if more==refs:return refs
            refs=more
    lower=descendants('shoulder_pitch_yoke')
    upper=descendants('elbow_roll_servo')
    distal=descendants('wrist_yaw_servo')
    shifts={n:(-D,0,0) for n in lower}
    shifts.update({n:(-D,0,D) for n in upper})
    shifts.update({n:(-2*D,0,D) for n in distal})
    # Horns belong to the upstream yoke in the mate graph, but their seating
    # centers move with the associated downstream servo case.
    for n in ['shoulder_pitch__hex_socket_m3x5__center',*[f'shoulder_pitch_servo_detail_{i}' for i in (14,15,16)],*[f'pitch_horn_m3x5_{i}' for i in range(1,7)]]:
        shifts[n]=(-D,0,0)
    for n in ['elbow_roll__hex_socket_m3x5__center',*[f'elbow_roll_servo_detail_{i}' for i in (14,15,16)]]:
        shifts[n]=(-D,0,D)
    for n in [*[f'wrist_yaw_servo_detail_{i}' for i in (14,15,16)],*[f'wrist_yaw_m3x5_{i}' for i in range(1,8)]]:
        shifts[n]=(-2*D,0,D)
    for i in range(1,13):shifts[f'integrated_elbow_horn_m3x5_{i}']=(-D,0,D if (i-1)%6>=3 else 0)
    return shifts

def is_mount_bolt(n):
    return (n.startswith(('pitch_horn_m3x5_','temporary_wrist_m3x5_','integrated_elbow_horn_m3x5_'))
            or n in {f'wrist_yaw_m3x5_{i}' for i in range(1,7)}
            or n.startswith('shoulder_yaw_yoke__hex_socket_m3x5__'))

def new_label(n):return n.replace('m3x5','m3x6') if is_mount_bolt(n) else n

def revised_kinematics(data):
    shifts=motion_map(data);mates=[]
    for m in data['mates']:
        r=asdict(m);parent='#'+new_label(m.parent.lstrip('#'));child='#'+new_label(m.child.lstrip('#'))
        m=replace(m,parent=parent,child=child)
        if r['kind']=='revolute':
            from lib.mates import revolute
            d=shifts.get(r['child'].lstrip('#'),(0,0,0))
            m=revolute(m.name,parent=parent,child=child,
                origin=[a+c for a,c in zip(r['axis']['origin'],d)],direction=r['axis']['dir'],limits=r['limits']['value'])
        mates.append(m)
    return data|{'mates':mates,'poses':data['poses']|{'zero':ZERO}}

