"""Authored joint datums, anatomy and actuator assignment; dimensions in mm.

These are design values, not validation results. Each universal joint uses
coincident orthogonal axes; a carrier between them is a real assembly body.
Positive finger flexion turns the finger toward the +Z palm side.
"""
from dataclasses import dataclass
from math import cos, sin, radians, sqrt

TENDON_RADIUS = .30
MINIMUM_BEND_RADIUS = 3.5
PALM_LENGTH = 105.0
FOREARM_LENGTH = 280.0
MCP_YAW_DRIVE_PLANES = (-9.5, -12.0)  # positive, negative
CMC_YAW_DRIVE_PLANES = (-11.0, -13.5)
MCP_YAW_HUB_PLANES = (9.5, -13.5)    # palmar, dorsal
CMC_YAW_HUB_PLANES = (11.0, -15.0)
MCP_PALM_SUPPORT_PLANES = (12.5, -16.5)
CMC_PALM_SUPPORT_PLANES = (14.0, -18.0)


@dataclass(frozen=True)
class Joint:
    name: str
    parent: str
    origin: tuple
    axis: tuple
    limits: tuple
    drive_radius: float
    system: str


@dataclass(frozen=True)
class Finger:
    name: str
    x: float
    base_y: float
    lengths: tuple
    widths: tuple
    abduction: tuple


FINGERS = (
    Finger('index', -36., 101., (42., 26., 17.), (18., 15., 12.), (-20., 20.)),
    Finger('middle', -12., 105., (45., 28., 17.), (18., 15., 12.), (-15., 15.)),
    Finger('ring', 12., 100., (41., 26., 17.), (17.5, 14.5, 11.5), (-15., 15.)),
    Finger('little', 36., 89., (33., 21., 16.), (17., 14., 11.), (-25., 25.)),
)

# Fixed assembly fan, separate from each joint's unchanged motion limits.
# The exact phalanx sweep certificate is neutral_fan_precheck.json.
NEUTRAL_FINGER_FAN = {'index': 20., 'middle': 5., 'ring': -5., 'little': -25.}

_joints = [
    Joint('wrist_abduction', 'forearm', (0., -9., 0.), (0., 0., 1.), (-20., 20.), 11., 'wrist'),
    Joint('wrist_flexion', 'wrist_abduction', (0., 0., 0.), (1., 0., 0.), (-45., 60.), 11., 'wrist'),
    Joint('palm_cup', 'wrist_flexion', (22., 40., 0.), (0., -1., 0.), (0., 25.), 7., 'palm'),
]
for _finger in FINGERS:
    _n, _x, _y = _finger.name, _finger.x, _finger.base_y
    _parent = 'palm_cup' if _n == 'little' else 'wrist_flexion'
    _joints.extend([
        Joint(f'{_n}_mcp_abduction', _parent, (_x, _y, 0.), (0., 0., 1.), _finger.abduction, 5.5, _n),
        Joint(f'{_n}_mcp_flexion', f'{_n}_mcp_abduction', (_x, _y, 0.), (1., 0., 0.), (-15., 90.), 5.5, _n),
        Joint(f'{_n}_pip', f'{_n}_mcp_flexion', (_x, _y + _finger.lengths[0], 0.), (1., 0., 0.), (0., 110.), 4.5, _n),
        Joint(f'{_n}_dip', f'{_n}_pip', (_x, _y + sum(_finger.lengths[:2]), 0.), (1., 0., 0.), (0., 80.), 3.5, _n),
    ])

_d = 1. / sqrt(2.)
THUMB_DIRECTION = (-_d, _d, 0.)
THUMB_CROSS_AXIS = (_d, _d, 0.)
THUMB_CMC = (-35., 36., 0.)
THUMB_LENGTHS = (36., 27., 21.)


def thumb_station(distance):
    return tuple(THUMB_CMC[i] + distance * THUMB_DIRECTION[i] for i in range(3))


_joints.extend([
    Joint('thumb_cmc_abduction', 'wrist_flexion', THUMB_CMC, (0., 0., 1.), (-25., 45.), 7., 'thumb'),
    Joint('thumb_cmc_flexion', 'thumb_cmc_abduction', THUMB_CMC, THUMB_CROSS_AXIS, (-15., 65.), 7., 'thumb'),
    Joint('thumb_mcp_abduction', 'thumb_cmc_flexion', thumb_station(36.), (0., 0., 1.), (-15., 15.), 5.5, 'thumb'),
    Joint('thumb_mcp_flexion', 'thumb_mcp_abduction', thumb_station(36.), THUMB_CROSS_AXIS, (0., 70.), 5.5, 'thumb'),
    Joint('thumb_ip', 'thumb_mcp_flexion', thumb_station(63.), THUMB_CROSS_AXIS, (0., 85.), 3.5, 'thumb'),
])

JOINTS = tuple(_joints)
JOINT_BY_NAME = {joint.name: joint for joint in JOINTS}
assert len(JOINTS) == 24 and len(JOINT_BY_NAME) == 24


def upstream_joints(name):
    ancestors = []
    parent = JOINT_BY_NAME[name].parent
    while parent in JOINT_BY_NAME:
        ancestors.append(parent)
        parent = JOINT_BY_NAME[parent].parent
    return tuple(reversed(ancestors))


def tendon_manifest():
    """Forty-eight independently terminated antagonists; ordered by system.

    The two forearm faces each hold 24 actuators, four columns × six rows.
    A row's drive radius determines excursion, never its visual size alone.
    """
    tendons = []
    # Keep associated joints in contiguous column blocks where possible.
    order = [j for system in ('thumb','index','middle','ring','little')
             for j in JOINTS if j.system == system]
    order += [j for j in JOINTS if j.system in ('palm', 'wrist')]
    for k, joint in enumerate(order):
        column, row = divmod(k, 6)
        for sign, suffix in ((1, 'positive'), (-1, 'negative')):
            name = f'{joint.name}_{suffix}'
            tendons.append({
                'name': name, 'joint': joint.name, 'sign': sign,
                'upstream': upstream_joints(joint.name),
                'actuator': f'actuator_{name}',
                'actuator_center': (-27. + 18. * column, -252. + 41. * row, sign * 13.),
                'capstan_center': (-27. + 18. * column, -252. + 41. * row, sign * 33.),
                'capstan_axis': (0., 0., float(sign)),
                'capstan_radius': 7., 'tendon_radius': TENDON_RADIUS,
                'minimum_bend_radius': MINIMUM_BEND_RADIUS,
                'target_moment_arm': sign * joint.drive_radius,
                'bundle_lane': -34.5 + column * 18. + row * 3.,
                'face': suffix,
            })
    assert len(tendons) == 48
    return tuple(tendons)


TENDONS = tendon_manifest()


def drive_pulley_offset(joint, sign):
    if joint.name=='wrist_abduction':return sign*5.5
    if joint.name=='wrist_flexion':return sign*14.
    if joint.name=='palm_cup':return -5. if sign>0 else -7.
    if 'abduction' in joint.name and joint.system not in ('wrist','palm'):
        planes=CMC_YAW_DRIVE_PLANES if 'cmc' in joint.name else MCP_YAW_DRIVE_PLANES
        return planes[0 if sign==1 else 1]
    return sign*.9


def rotation_matrix(axis, angle_deg, origin):
    """Homogeneous world-datum rotation, for static pose evaluation."""
    import numpy as np
    a = np.asarray(axis, dtype=float)
    a /= np.linalg.norm(a)
    x, y, z = a
    theta = radians(angle_deg)
    c, s, t = cos(theta), sin(theta), 1. - cos(theta)
    r = np.array([[t*x*x+c, t*x*y-s*z, t*x*z+s*y],
                  [t*x*y+s*z, t*y*y+c, t*y*z-s*x],
                  [t*x*z-s*y, t*y*z+s*x, t*z*z+c]])
    m = np.eye(4)
    m[:3, :3] = r
    o = np.asarray(origin, dtype=float)
    m[:3, 3] = o - r @ o
    return m


def transforms(pose):
    import numpy as np
    result = {'forearm': np.eye(4)}
    for joint in JOINTS:
        q = float(pose.get(joint.name, 0.))
        if q < joint.limits[0] - 1e-9 or q > joint.limits[1] + 1e-9:
            raise ValueError(f'{joint.name}: {q} outside {joint.limits}')
        result[joint.name] = result[joint.parent] @ rotation_matrix(joint.axis, q, joint.origin)
    return result


def finger_fan_matrix(finger):
    return rotation_matrix((0.,0.,1.),NEUTRAL_FINGER_FAN[finger.name],
                           (finger.x,finger.base_y,0.))


def assembled_transforms(pose):
    """Transforms of bodies already placed in their fixed neutral fan.

    Canonical local finger proofs remain reusable. Conjugation rotates their
    joint axes and origins with the fixed assembly fan, including cup motion.
    """
    import numpy as np
    original=transforms(pose);result=dict(original)
    for finger in FINGERS:
        parent=original['palm_cup' if finger.name=='little' else 'wrist_flexion']
        fan=finger_fan_matrix(finger)
        for joint in JOINTS:
            if joint.system==finger.name:
                result[joint.name]=parent@fan@np.linalg.inv(parent)@original[joint.name]@np.linalg.inv(fan)
    return result
