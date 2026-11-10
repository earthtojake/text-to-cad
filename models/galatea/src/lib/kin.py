"""Galatea's kinematics in plain numbers: the joint tree, the couplings, forward kinematics,
the leg's planar inverse kinematics, and the legs solved over feet that stay where they stand
on a floor. Nothing here touches the CAD kernel, so the poses, the motions and the checks
all compute with it.

A pose is a mapping of controls to values: a joint's label to degrees, or a coupling's
name to its value (a knee or an ankle in degrees, a finger's curl from 0 to 1).
"""

import math

from .dims import (
    ANKLE, CENTRE_JOINTS, CENTRE_LINKS, FINGER_CURL, FINGERS, hand_joints, HIP, hip_can_reach, HIP_X, mirror_joint,
    mirror_point, SHIN_LEN, SIDE_JOINTS, THIGH_LEN, THUMB_CURL, X, Y, Z,
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


# ---------------------------------------------------------------------------------------------
# The legs over feet that stay where they stand
#
# The pelvis is the mechanism's fixed link, so a pose written joint by joint moves the feet about
# under it. A robot on a floor is the other way round: its feet stay and its pelvis moves. These
# solve a leg's six joints for that: the foot's link is put where it must be as the pelvis sees it.
# ---------------------------------------------------------------------------------------------
LEG_CONTROLS = ("hip_yaw", "hip_roll", "hip_pitch", "knee", "ankle_pitch", "ankle_roll")
_LEG_JOINTS = ("hip_yaw", "hip_roll", "hip_pitch", "knee_pivot", "ankle_pitch_pivot", "ankle_roll")
HIP_MID = (0.0, 0.0, HIP[2])          # midway between the hips' centres: what a pelvis is turned about
_CHAINS = {}


def _chain(side):
    """[(origin, direction)] of the six joints from the pelvis to one foot."""
    if side not in _CHAINS:
        joints = all_joints()
        _CHAINS[side] = [joints[f"{side}_{label}"][2:4] for label in _LEG_JOINTS]
    return _CHAINS[side]


def foot_at(side, values):
    """The foot link's transform, the pelvis fixed, for one leg's six LEG_CONTROLS (degrees)."""
    t = IDENTITY
    for (origin, direction), value in zip(_chain(side), values):
        t = compose(t, about(origin, direction, value))
    return t


def placed(left=0.0, forward=0.0, drop=0.0, yaw=0.0, roll=0.0, pitch=0.0, centre=HIP_MID):
    """The transform that turns a body about `centre` (`pitch` bows it forward, then `roll` leans it to the
    left, then `yaw` turns it to the left: degrees) and then moves it `left`, `forward` and down by `drop` (mm).
    The robot faces -Y and its left is +X."""
    turn = compose(about(centre, Z, yaw), compose(about(centre, Y, roll), about(centre, X, pitch)))
    return compose((IDENTITY[0], (left, -forward, -drop)), turn)


def _solved(columns, right):
    """x of A x = right, A given by its columns: elimination with pivoting, for the six by six of a leg."""
    n = len(right)
    rows = [[columns[k][i] for k in range(n)] + [right[i]] for i in range(n)]
    for k in range(n):
        pivot = max(range(k, n), key=lambda i: abs(rows[i][k]))
        if abs(rows[pivot][k]) < 1e-12:
            raise ZeroDivisionError("singular")
        rows[k], rows[pivot] = rows[pivot], rows[k]
        for i in range(k + 1, n):
            factor = rows[i][k] / rows[k][k]
            rows[i] = [a - factor * b for a, b in zip(rows[i], rows[k])]
    x = [0.0] * n
    for k in reversed(range(n)):
        x[k] = (rows[k][n] - sum(rows[k][j] * x[j] for j in range(k + 1, n))) / rows[k][k]
    return x


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def leg_to(side, target, start):
    """One leg's six LEG_CONTROLS (degrees) that put its foot's link at `target`, a transform with the pelvis
    fixed. The hip's three axes meet in a point and so do the ankle's two, so the knee's angle is the triangle's
    (hip, knee, ankle) and is set first; Newton's iteration from `start` finds the rest. An error is six numbers:
    how far the ankle's centre is from its place (mm) and the turn left to make (a rotation vector, as mm at
    100 mm from its axis); a joint moves them as a turn about its axis where the leg now holds it."""
    hip, ankle = (HIP, ANKLE) if side == "l" else (mirror_point(HIP), mirror_point(ANKLE))
    goal, turned = apply(target, ankle), tuple(zip(*target[0]))
    reach = math.dist(hip, goal)
    if not abs(THIGH_LEN - SHIN_LEN) < reach < LEG_REACH - 1e-6:
        raise ValueError(f"the {side} leg cannot put its foot there: {reach:.1f} mm from hip to ankle, of {LEG_REACH:.0f}")
    values = list(start)
    values[3] = 180.0 - math.degrees(math.acos((THIGH_LEN ** 2 + SHIN_LEN ** 2 - reach ** 2) / (2 * THIGH_LEN * SHIN_LEN)))
    values[2] += (values[3] - start[3]) / 2.0                       # a knee that bends carries the thigh half as far
    values[4] += (values[3] - start[3]) / 2.0
    for _ in range(60):
        t, axes = IDENTITY, []
        for (origin, direction), value in zip(_chain(side), values):
            axes.append((_matvec(t[0], direction), apply(t, origin)))
            t = compose(t, about(origin, direction, value))
        here, r = apply(t, ankle), _matmul(t[0], turned)
        error = [here[0] - goal[0], here[1] - goal[1], here[2] - goal[2],
                 50.0 * (r[2][1] - r[1][2]), 50.0 * (r[0][2] - r[2][0]), 50.0 * (r[1][0] - r[0][1])]
        if max(abs(e) for e in error) < 1e-9:
            return values
        columns = []
        for axis, origin in axes:
            sweep = _cross(axis, tuple(here[i] - origin[i] for i in range(3)))
            columns.append([math.radians(c) for c in (*sweep, 100.0 * axis[0], 100.0 * axis[1], 100.0 * axis[2])])
        try:
            change = _solved(columns, [-e for e in error])
        except ZeroDivisionError:
            break
        scale = min(1.0, 20.0 / max(1e-12, max(abs(c) for c in change)))
        values = [v + scale * c for v, c in zip(values, change)]
    raise ValueError(f"the {side} leg's joints for its foot's place were not found")


def standing(base, pelvis=IDENTITY, feet=None):
    """The legs' controls that hold the pelvis where `pelvis` (a transform: see `placed`) moves it from its place
    in the pose `base`, each foot left standing where `base` has it, or first moved by `feet[side]` (a transform
    over the floor). The floor's frame is the pelvis's own at `base`."""
    pose = {}
    for side in SIDES:
        start = [base[f"{side}_{name}"] for name in LEG_CONTROLS]
        foot = foot_at(side, start)
        if feet and side in feet:
            foot = compose(feet[side], foot)
        found = leg_to(side, compose(inverse(pelvis), foot), start)
        pose.update({f"{side}_{name}": value for name, value in zip(LEG_CONTROLS, found)})
    return pose


def pelvis_over(base, pose, side):
    """Where a pose's pelvis is, as a transform from its place in `base`, when the `side` foot has stayed where
    `base` stands it: the inverse of `standing`, for a pose written joint by joint."""
    here = foot_at(side, [pose[f"{side}_{name}"] for name in LEG_CONTROLS])
    there = foot_at(side, [base[f"{side}_{name}"] for name in LEG_CONTROLS])
    return compose(there, inverse(here))
