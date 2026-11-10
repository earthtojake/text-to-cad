"""Galatea's kinematics in plain numbers: the joint tree, the couplings, forward kinematics
and the leg's planar inverse kinematics. Nothing here touches the CAD kernel, so the
poses, the motions and the checks all compute with it.

A pose is a mapping of controls to values: a joint's label to degrees, or a coupling's
name to its value (a knee or an ankle in degrees, a finger's curl from 0 to 1).
"""

import math

from .dims import (
    CENTRE_JOINTS, CENTRE_LINKS, FINGER_CURL, FINGERS, hand_joints, hip_can_reach, HIP_X, mirror_joint, SHIN_LEN,
    SIDE_JOINTS, THIGH_LEN, THUMB_CURL,
)

SIDES = ("l", "r")


def all_joints():
    """label -> (parent link, child link, origin, axis direction, (min, max)), both sides."""
    joints = dict(CENTRE_JOINTS)
    for side in SIDES:
        for label, (parent, child, origin, direction, limits) in {**SIDE_JOINTS, **hand_joints()}.items():
            if side == "r":
                origin, direction = mirror_joint(origin, direction)
            parent = parent if parent in CENTRE_LINKS else f"{side}_{parent}"
            joints[f"{side}_{label}"] = (parent, f"{side}_{child}", origin, direction, limits)
    return joints


def couplings():
    """coupling -> {joint: ratio}. The knee and ankle linkages are parallelograms, so the
    crank turns with the joint and the pushrod turns back by as much; a finger's three
    knuckles (a thumb's two) close together on one tendon."""
    table = {}
    for s in SIDES:
        table[f"{s}_knee"] = {f"{s}_knee_pivot": 1.0, f"{s}_knee_crank": 1.0, f"{s}_knee_rod": -1.0}
        table[f"{s}_ankle_pitch"] = {f"{s}_ankle_pitch_pivot": 1.0, f"{s}_ankle_crank": 1.0, f"{s}_ankle_rod": -1.0}
        for finger in FINGERS:
            table[f"{s}_{finger}_curl"] = {f"{s}_{finger}_{joint}": ratio
                                           for joint, ratio in zip(("mcp", "pip", "dip"), FINGER_CURL)}
        table[f"{s}_thumb_curl"] = {f"{s}_thumb_mcp": THUMB_CURL[0], f"{s}_thumb_ip": THUMB_CURL[1]}
    return table


def link_distances():
    """{(link a, link b): how many joints lie between them}, for every pair of links."""
    joints = all_joints()
    neighbours = {}
    for parent, child, *_ in joints.values():
        neighbours.setdefault(parent, set()).add(child)
        neighbours.setdefault(child, set()).add(parent)
    distances = {}
    for start in neighbours:
        seen, frontier = {start: 0}, [start]
        while frontier:
            link = frontier.pop(0)
            for other in neighbours[link]:
                if other not in seen:
                    seen[other] = seen[link] + 1
                    frontier.append(other)
        distances.update({(start, other): hops for other, hops in seen.items()})
    return distances


def controls():
    """Every control a pose may set: the couplings, and the joints no coupling drives."""
    table = couplings()
    driven = {joint for ratios in table.values() for joint in ratios}
    return [*[label for label in all_joints() if label not in driven], *table]


def expand(pose):
    """A pose in controls -> a value for every joint it moves."""
    table, values = couplings(), {}
    for name, value in pose.items():
        if name in table:
            for joint, ratio in table[name].items():
                values[joint] = ratio * value
        else:
            values[name] = value
    return values


def check_limits(pose, name="pose"):
    """Raise if the pose names an unknown control or drives a joint past its travel."""
    joints, known = all_joints(), set(controls())
    unknown = sorted(set(pose) - known)
    if unknown:
        raise ValueError(f"{name}: unknown controls {unknown}")
    for joint, value in expand(pose).items():
        low, high = joints[joint][4]
        if not low - 1e-6 <= value <= high + 1e-6:
            raise ValueError(f"{name}: {joint} = {value:.1f} is outside {low}..{high}")
    # The two hips' roll drives stand behind them and swing inward as the feet turn out: they must not meet.
    reach = sum(hip_can_reach(pose.get(f"{side}_hip_yaw", 0.0)) for side in SIDES)
    if reach > 2 * HIP_X - 4.0:
        raise ValueError(f"{name}: the feet turn out too far together: the hips' roll drives would meet ({reach:.0f} of {2 * HIP_X - 4:.0f} mm)")
    return pose


# ---------------------------------------------------------------------------------------------
# Rigid transforms as (rotation rows, translation)
# ---------------------------------------------------------------------------------------------
IDENTITY = (((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), (0.0, 0.0, 0.0))


def _rotation(direction, degrees):
    x, y, z = direction
    n = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / n, y / n, z / n
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    t = 1.0 - c
    return ((t * x * x + c, t * x * y - s * z, t * x * z + s * y),
            (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
            (t * x * z - s * y, t * y * z + s * x, t * z * z + c))


def _matvec(m, v):
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))


def _matmul(a, b):
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def compose(a, b):
    """The transform that applies b, then a."""
    ra, ta = a
    rb, tb = b
    moved = _matvec(ra, tb)
    return _matmul(ra, rb), tuple(moved[i] + ta[i] for i in range(3))


def about(origin, direction, degrees):
    """A turn of `degrees` about the axis through `origin` along `direction`."""
    r = _rotation(direction, degrees)
    moved = _matvec(r, origin)
    return r, tuple(origin[i] - moved[i] for i in range(3))


def inverse(t):
    r, p = t
    rt = tuple(tuple(r[j][i] for j in range(3)) for i in range(3))
    moved = _matvec(rt, p)
    return rt, tuple(-moved[i] for i in range(3))


def apply(t, point):
    r, p = t
    moved = _matvec(r, point)
    return tuple(moved[i] + p[i] for i in range(3))


def link_transforms(pose):
    """Where every link stands at a pose, the pelvis fixed: link -> transform that carries
    its zero-pose geometry to the pose."""
    values, joints = expand(pose), all_joints()
    parent_of = {child: (label, parent, origin, direction) for label, (parent, child, origin, direction, _)
                 in joints.items()}
    done = {"pelvis": IDENTITY}

    def solve(link):
        if link not in done:
            label, parent, origin, direction = parent_of[link]
            done[link] = compose(solve(parent), about(origin, direction, values.get(label, 0.0)))
        return done[link]

    for link in parent_of:
        solve(link)
    return done


def stance(pose, foot="l_foot"):
    """The transform of the whole robot that puts `foot` back where it stands at the zero
    pose: flat on the ground, the rest of the body posed over it."""
    return inverse(link_transforms(pose)[foot])


# Points under the left foot and toe at the zero pose (link, point): where a sole can touch the ground.
_SOLE_POINTS = [("foot", (HIP_X, 70.0, 0.0)), ("foot", (HIP_X - 30, 40.0, 0.0)), ("foot", (HIP_X + 30, 40.0, 0.0)),
                ("foot", (HIP_X - 38, -104.0, 0.0)), ("foot", (HIP_X + 44, -104.0, 0.0)),
                ("toe", (HIP_X - 34, -130.0, 0.0)), ("toe", (HIP_X + 40, -130.0, 0.0)), ("toe", (HIP_X + 2, -176.0, 0.0))]


def sole_points(pose):
    """Where the soles' contact points stand at a pose: [(side, link, (x, y, z)), ...]."""
    transforms, points = link_transforms(pose), []
    for s in SIDES:
        for link, point in _SOLE_POINTS:
            if s == "r":
                point = (-point[0], point[1], point[2])
            points.append((s, link, apply(transforms[f"{s}_{link}"], point)))
    return points


def settle(pose):
    """The transform that lowers the posed robot, level, until its lowest sole point is on the ground."""
    lowest = min(point[2] for _, _, point in sole_points(pose))
    return IDENTITY[0], (0.0, 0.0, -lowest)


# ---------------------------------------------------------------------------------------------
# The leg in its sagittal plane
# ---------------------------------------------------------------------------------------------
LEG_REACH = THIGH_LEN + SHIN_LEN


def leg_ik(forward, drop=0.0, foot_pitch=0.0):
    """Hip pitch, knee and ankle pitch (degrees) that put the ankle `forward` of the hip and
    `drop` above its straight-leg height, with the sole pitched `foot_pitch` toes-up."""
    height = LEG_REACH - drop
    reach = math.hypot(forward, height)
    if reach > LEG_REACH:
        raise ValueError(f"leg cannot reach {forward:.0f} forward at drop {drop:.0f}")
    knee_inner = math.acos((THIGH_LEN ** 2 + SHIN_LEN ** 2 - reach ** 2) / (2 * THIGH_LEN * SHIN_LEN))
    knee = 180.0 - math.degrees(knee_inner)
    hip = math.degrees(math.atan2(forward, height)
                       + math.acos((THIGH_LEN ** 2 + reach ** 2 - SHIN_LEN ** 2) / (2 * THIGH_LEN * reach)))
    return hip, knee, knee - hip + foot_pitch


def leg(side, forward=0.0, drop=0.0, foot_pitch=0.0, yaw=0.0, roll=0.0, toe=0.0):
    """Controls for one leg from where its foot goes; `roll` leans the leg and keeps the sole flat."""
    hip, knee, ankle = leg_ik(forward, drop, foot_pitch)
    return {f"{side}_hip_yaw": yaw, f"{side}_hip_roll": roll, f"{side}_hip_pitch": hip, f"{side}_knee": knee,
            f"{side}_ankle_pitch": ankle, f"{side}_ankle_roll": -roll, f"{side}_toe": toe}
