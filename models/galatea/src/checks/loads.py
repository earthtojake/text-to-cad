# /// script
# dependencies = ["numpy", "scipy", "trimesh"]
# ///
"""What does holding a pose ask of Galatea's drives and pushrods?

    cad run src/checks/loads.py

Statics only. Each link's weight (as `balance.py` weighs it) acts at its centre of mass, a
carried load hangs 30 mm off a palm, and the ground pushes up at the soles' contact points:
the set of forces that carries the weight with its resultant under the centre of mass and
asks least of the ankles. The torque a joint's drive holds is then
the moment, about the joint's axis, of everything that acts on the links beyond it. It is
set against the drive's two figures from its maker's datasheet (`dims.ACTUATORS`): its rated
torque, which it holds continuously, and its peak, which it gives briefly. A pose is held
for as long as one likes while every drive is within its rated torque, and held briefly
while every drive is within BRIEF of its peak. The standing poses must be of the first
kind; every other case here must be at least of the second, and is listed with which it is.

The knee's and the ankle's torque reach their joints through pushrods. A rod's force is the
torque over the lever its crank gives it at that angle; where it pushes, it is set against
the rod's Euler buckling load (pin-ended, its material's modulus), and the rod must keep
ROD_MARGIN on it with the drive at its peak at the worst angle of the travel.
"""

import math
import sys

import build123d  # noqa: F401  (the model needs cad's build123d integration)
import numpy as np
from balance import matrix, weigh
from scipy.optimize import nnls
from scipy.spatial import ConvexHull

from galatea import galatea
from lib import dims, kin
from lib.poses import POSES, READY, both, side, walk

G = 9.81
BRIEF = 0.75            # the share of a drive's peak a pose may ask of it and still count as held, briefly
STANDING = ("standing straight", "ready", "contrapposto", "wave", "rest")     # held as long as one likes: within every rated torque
ROD_MARGIN = 1.5
GRIP = (dims.SHOULDER_X - 30.0, 0.0, 800.0)          # where a carried load hangs from the left hand
SOLE_EDGE = 44.0                                     # from the ankle's roll axis to the sole's outer edge, mm
PIVOT = {"knee": "knee_pivot", "ankle_pitch": "ankle_pitch_pivot"}     # a coupled drive's loaded joint

ARMS_DOWN = dict(shoulder_pitch=0, shoulder_roll=0, shoulder_yaw=0, elbow=0, wrist_roll=0, wrist_pitch=0, wrist_yaw=0)
CASES = [
    # name, pose, the feet that carry it, kg in each hand
    ("standing straight", {}, "lr", {}),
    ("ready", POSES["ready"], "lr", {}),
    ("contrapposto", POSES["contrapposto"], "lr", {}),
    ("wave", POSES["wave"], "lr", {}),
    ("rest", POSES["rest"], "lr", {}),
    ("bow", POSES["bow"], "lr", {}),
    ("crouch", POSES["crouch"], "lr", {}),
    ("poise, on the left leg", POSES["poise"], "l", {}),
    ("reach, 2 kg in the hand", POSES["reach"], "lr", {"r": 2.0}),
    ("present, 2.5 kg on each palm", POSES["present"], "lr", {"l": 2.5, "r": 2.5}),
    ("arms out level, 1.5 kg in each hand", {**READY, **both(**{**ARMS_DOWN, "shoulder_roll": 90})}, "lr", {"l": 1.5, "r": 1.5}),
    ("elbows square, 4 kg in each hand", {**READY, **both(**{**ARMS_DOWN, "elbow": 90})}, "lr", {"l": 4.0, "r": 4.0}),
    ("one arm overhead, 2 kg", {**READY, **side("r", **{**ARMS_DOWN, "shoulder_pitch": 170})}, "lr", {"r": 2.0}),
    ("mid-step on the left leg", walk(0.6), "l", {}),
]


def materials(node, found=None):
    """{part label: its material} from the model's tree."""
    found = {} if found is None else found
    if node.children:
        for child in node.children:
            materials(child, found)
    else:
        found[node.label] = node.material.material
    return found


def nearest(point, polygon):
    """(the point of a convex polygon nearest `point`, how far that is from it)."""
    hull = polygon[ConvexHull(polygon).vertices]
    inside, best = True, None
    for a, b in zip(hull, np.roll(hull, -1, axis=0)):
        edge = b - a
        if edge[0] * (point[1] - a[1]) - edge[1] * (point[0] - a[0]) < 0:      # counter-clockwise hull: outside this edge
            inside = False
        on_edge = a + edge * min(1.0, max(0.0, float((point - a) @ edge / (edge @ edge))))
        if best is None or np.linalg.norm(point - on_edge) < np.linalg.norm(point - best):
            best = on_edge
    return (point, 0.0) if inside else (best, float(np.linalg.norm(point - best)))


def reactions(com, weight, points, owners, ankles):
    """The ground's push (N) at each contact point, and how far the centre of mass lies
    outside the support (0 for a pose that balances; then the reaction stands at the
    support's nearest point, as near as the ground can get to holding it).

    The pushes carry the weight with their resultant under the centre of mass. Many sets
    do; this is the one that asks least of the ankles: the smallest moments about each
    foot's ankle (`owners` names each point's foot, `ankles` its ankle on the ground)."""
    under, outside = nearest(com, points)
    if outside:
        under = under + 1e-6 * (points.mean(axis=0) - under)
    levers = points - ankles
    moments = [np.where(np.array(owners) == foot, levers[:, k], 0.0) for foot in sorted(set(owners)) for k in (0, 1)]
    stiff = 1e4                                                    # the balance holds exactly; the rest is least squares
    balance = stiff * np.vstack([100.0 * np.ones(len(points)), points[:, 0], points[:, 1]])
    system = np.vstack([balance, *moments, np.eye(len(points))])   # the last rows spread a push over a patch of sole
    target = np.concatenate([stiff * np.array([100.0, under[0], under[1]]), np.zeros(len(moments) + len(points))])
    shares, _ = nnls(system, target)
    if abs(shares.sum() - 1.0) > 1e-6 or np.linalg.norm(shares @ points - under) > 1e-3:
        raise ValueError("no ground reaction carries the pose")
    return weight * shares, outside


def holding(pose, links, carried, feet):
    """({joint: N m its drive holds, + in the joint's own sense}, how far the centre of mass
    is outside the support)."""
    ground = matrix(kin.stance(pose, f"{feet[0]}_foot"))
    world = {link: ground @ matrix(t) for link, t in kin.link_transforms(pose).items()}
    at = lambda link, point: (world[link] @ np.append(point, 1.0))[:3]
    forces, total, moment = {}, 0.0, np.zeros(3)
    for link, (mass, centre) in links.items():
        forces[link] = [(at(link, centre), np.array([0.0, 0.0, -mass * G]))]
        total += mass
        moment += mass * forces[link][0][0]
    for s, kg in carried.items():
        grip = at(f"{s}_palm", GRIP if s == "l" else dims.mirror_point(GRIP))
        forces[f"{s}_palm"].append((grip, np.array([0.0, 0.0, -kg * G])))
        total += kg
        moment += kg * grip
    points, owners, ankles = [], [], []
    for s, _, point in kin.sole_points(pose):
        p = (ground @ np.append(point, 1.0))[:3]
        if s in feet and p[2] < 2.0:
            points.append(p[:2])
            owners.append(f"{s}_foot")
            ankles.append(at(f"{s}_foot", dims.ANKLE if s == "l" else dims.mirror_point(dims.ANKLE))[:2])
    if {name[0] for name in owners} != set(feet) or len(points) < 3 * len(feet):
        raise ValueError("a carrying foot is not flat on the ground")
    pushes, outside = reactions((moment / total)[:2], total * G, np.array(points), owners, np.array(ankles))
    for point, owner, newtons in zip(points, owners, pushes):
        forces[owner].append((np.array([point[0], point[1], 0.0]), np.array([0.0, 0.0, newtons])))

    joints, hangs = kin.all_joints(), {}
    for parent, child, *_ in joints.values():
        hangs.setdefault(parent, []).append(child)

    def beyond(link):
        yield link
        for child in hangs.get(link, ()):
            yield from beyond(child)

    torques = {}
    for label, (parent, child, origin, direction, _) in joints.items():
        pivot, axis = at(parent, origin), world[parent][:3, :3] @ np.array(direction)
        turning = sum(np.cross(point - pivot, force) for link in beyond(child) for point, force in forces[link])
        torques[label] = -float(turning @ axis) / 1000.0
    return torques, outside


def peak(control):
    size, count = dims.DRIVES[control]
    return count * dims.ACTUATORS[size]["peak"]


def rated(control):
    size, count = dims.DRIVES[control]
    return count * dims.ACTUATORS[size]["rated"]


def drives():
    """[(drive, its loaded joint, rated N m, peak N m)] for every drive of the robot."""
    out = []
    for control in dims.DRIVES:
        names = [control] if control in dims.CENTRE_JOINTS else [f"{s}_{control}" for s in kin.SIDES]
        out += [(name, name.replace(control, PIVOT.get(control, control)), rated(control), peak(control)) for name in names]
    return out


def rod_forces(pose, torques):
    """{rod: N along it, + a pull} at a pose: each knee's pushrod and each ankle's rod."""
    values, out = kin.expand(pose), {}
    for s in kin.SIDES:
        knee = math.radians(dims.KNEE_CRANK_PSI + values.get(f"{s}_knee_pivot", 0.0))
        out[f"{s}_knee_pushrod"] = torques[f"{s}_knee_pivot"] / (dims.KNEE_CRANK_R / 1000.0 * math.cos(knee))
        ankle = math.radians(values.get(f"{s}_ankle_pitch_pivot", 0.0))
        out[f"{s}_achilles_rod"] = -torques[f"{s}_ankle_pitch_pivot"] / (dims.ANKLE_CRANK_R / 1000.0 * math.cos(ankle))
    return out


def buckling(material, radius, length):
    """Euler load (N) of a solid round rod, pinned at both ends."""
    modulus = material.modulus_of_elasticity.min * 1000.0            # GPa -> N/mm^2
    return math.pi ** 2 * modulus * (math.pi * radius ** 4 / 4.0) / length ** 2


def main():
    handle = galatea()
    links, grades = weigh(handle), materials(handle.shape)
    table, worst, failed = drives(), {}, 0
    rods = {"knee_pushrod": 0.0, "achilles_rod": 0.0}
    total = sum(mass for mass, _ in links.values())
    print(f"holding torques, statics ({total:.1f} kg); the three hardest-worked drives of each case, as shares of their rated torque")
    for name, pose, feet, carried in CASES:
        torques, outside = holding(pose, links, carried, feet)
        used = sorted(((abs(torques[joint]) / most, abs(torques[joint]) / top, drive, torques[joint])
                       for drive, joint, most, top in table), reverse=True)
        of_peak = max(share for _, share, _, _ in used)
        if outside < 0.5:                                   # a held pose: it counts
            for of_rated, share, drive, torque in used:
                key = drive.split("_", 1)[1] if drive[:2] in ("l_", "r_") else drive
                if of_rated > worst.get(key, (0.0,))[0]:
                    worst[key] = (of_rated, share, torque, name)
            for rod, force in rod_forces(pose, torques).items():
                rods[rod[2:]] = min(rods[rod[2:]], force)
            kind = "held" if used[0][0] <= 1.0 else "held briefly" if of_peak <= BRIEF else "NOT HELD"
            failed += kind == "NOT HELD" or (name in STANDING and kind != "held")
        else:
            kind = f"not held: the weight stands {outside:.0f} mm outside the sole, as in a step"
        print(f"  {name:36s}" + ",  ".join(f"{drive} {torque:6.1f} N m ({of_rated:4.0%})" for of_rated, _, drive, torque in used[:3])
              + f"   [{kind}]")

    print("each drive's hardest held case")
    for control, (size, count) in dims.DRIVES.items():
        of_rated, share, torque, name = worst[control]
        drive = f"{count} x {size}" if count > 1 else size
        print(f"  {control:15s} {drive:8s} rated {rated(control):5.1f}, peak {peak(control):5.1f} N m   holds {abs(torque):5.1f} N m "
              f"({of_rated:4.0%} of rated, {share:4.0%} of peak)  {name}")

    # What walking adds to the statics: a foot can lever no more than the weight at its own edge.
    on_toe = total * G * abs(dims.TOE[1] - dims.ANKLE[1]) / 1000.0
    on_edge = total * G * SOLE_EDGE / 1000.0
    print(f"  push-off on one forefoot: ankle_pitch {on_toe:.0f} N m ({on_toe / peak('ankle_pitch'):.0%} of its peak); "
          f"the weight on one sole's edge: ankle_roll {on_edge:.0f} N m ({on_edge / peak('ankle_roll'):.0%})")

    print("pushrods (a push is negative)")
    weak = 0
    specs = [("knee_pushrod", "knee_pushrod", dims.KNEE_ROD_R, dims.KNEE_ROD, peak("knee"),
              dims.KNEE_CRANK_R * math.cos(math.radians(dims.KNEE_CRANK_PSI)), 1),
             ("achilles_rod", "achilles_rod", dims.ANKLE_ROD_R, dims.ANKLE_ROD, peak("ankle_pitch"),
              dims.ANKLE_CRANK_R * math.cos(math.radians(max(abs(a) for a in dims.SIDE_JOINTS["ankle_pitch_pivot"][4]))), 1)]
    for rod, label, radius, length, most, lever, count in specs:
        euler = buckling(grades[label], radius, length)
        at_peak = most / (lever / 1000.0) / count
        factor = euler / at_peak
        weak += factor < ROD_MARGIN
        print(f"  {rod:14s} {grades[label].name}, {2 * radius:g} mm x {length:g} mm: Euler load {euler / 1000:.1f} kN; "
              f"hardest held push {-rods[rod]:.0f} N; at the drive's peak and the shortest lever {at_peak / 1000:.1f} kN "
              f"(factor {factor:.1f})")
    ok = not failed and not weak
    print(f"OK: the standing poses are within every drive's rated torque, every other case within {BRIEF:.0%} of every peak, "
          f"and the rods keep {ROD_MARGIN} on buckling" if ok
          else f"{failed} case(s) ask more of a drive than it has, {weak} rod(s) are short of their margin")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
