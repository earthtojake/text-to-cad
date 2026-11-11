# /// script
# dependencies = ["numpy", "scipy", "trimesh"]
# ///
"""Where is Galatea's mass, does each standing pose balance, and can each motion be followed on a floor?

    cad run src/checks/balance.py

Weighs every part by its material's density (an actuator, the battery and the modules
carry homogenised densities, `lib/finish.py`), sums by link, and for each standing pose
puts the centre of mass over the ground: a pose balances statically when that point lies
inside the support polygon, the hull of the sole points on the floor. The margin is the
distance from the point to the polygon's nearest edge. The sprung toe carries what its
spring gives it, which is nothing while the foot is flat: only the heel's and the ball's
points count as support.

A motion is then followed in time, set down on the foot it never moves. It is one a robot
on a floor can follow when a foot that is down stays where it is (the pelvis is the
mechanism's fixed link, so a motion written joint by joint may slide a foot that a floor
would hold), when no foot goes below the floor, and when the centre of mass stays MARGIN
inside what is down at every instant. Two poses that balance say nothing of the path
between them: a squat eased joint by joint between `ready` and `crouch` passed within 8 mm
of going over backward, and a simulation of it did.

Nor is the centre of mass the whole of it once the motion has a pace. Where the body is
braked, the floor's push stands ahead of the centre of mass: the centre of pressure is
the point about which the links' weights and their accelerations (each link a point mass
at its centre, its acceleration the second difference of its path over STEP either side)
have no moment, and it must stay PRESSURE inside what is down. A weight shift onto one
foot in a second and a half balanced at every instant by its centre of mass and put the
centre of pressure 11 mm from the sole's edge; in three seconds it is 19.

This is what a path can answer for: that a robot which follows it exactly stands. Drives
that give under their load do not follow it exactly, and what comes of that is the
simulation's to say.

The gait is trodden under a fixed pelvis and is reported, not held to any of this.
"""

import re
import sys

import build123d  # noqa: F401  (the model needs cad's build123d integration)
import numpy as np
from common import drive_model, load_parts
from scipy.spatial import ConvexHull

from galatea import galatea
from lib import kin
from lib.dims import ACTUATORS
from lib.poses import MOTIONS, POSES

STANDING = {"zero": {}, **{name: POSES[name] for name in ("ready", "stride", "contrapposto", "reach", "wave",
                                                           "present", "crouch", "bow", "poise", "fists", "rest")}}
PLANTED = {"bow": "l_foot", "crouch": "l_foot"}     # poses that tip the pelvis are set down on a foot, as `stances.py` does
DYNAMIC = {"stride"}                                # a frame of a gait: reported, not required to balance

KEPT = {"settle": "r_foot"}     # the foot a motion never moves, where that is not the left
GAITS = {"walk"}                # trodden under a fixed pelvis: reported, not held to the floor
RATE = 48                       # instants a second at which a motion is looked at
DOWN = 0.5                      # a foot is down while three of its sole's points are within this of the floor, mm
SCRUB = 0.5                     # the most a foot that is down may move over the floor, mm
MARGIN = 20.0                   # the least margin a motion may have, mm: a sole is 60 mm wide at its heel, so a
                                # robot whose weight is over one foot cannot have more than 30
PRESSURE = 15.0                 # the least its centre of pressure may have, mm
STEP = 0.1                      # s either side over which a link's acceleration is taken: the sampled motions' own
G = 9810.0                      # mm/s2


def densities(node, found=None):
    """{part label: kg/m^3} from the model's tree: every part of one label wears one material."""
    found = {} if found is None else found
    if node.children:
        for child in node.children:
            densities(child, found)
    else:
        found[node.label] = node.material.material.density
    return found


def weigh(handle):
    """{link: (kg, centre of mass)} at the zero pose, from the parts' meshes."""
    density = densities(handle.shape)
    links = {}
    for link, parts in load_parts(handle).items():
        mass, moment = 0.0, np.zeros(3)
        for part in parts:
            label = re.sub(r"_\d+$", "", part.path.split("/")[-1])
            mesh, drive = part.geometry.mesh, drive_model(label)
            if drive:                                  # RobStride's solid: its maker's mass, at the middle of its box
                kg, centre = ACTUATORS[drive]["kg"], mesh.bounds.mean(axis=0)
            else:
                kg, centre = abs(mesh.volume) * 1e-9 * density[label], mesh.center_mass
            mass += kg
            moment += kg * (part.rest @ np.append(centre, 1.0))[:3]
        links[link] = (mass, moment / mass)
    return links


def matrix(transform):
    r, p = transform
    m = np.eye(4)
    m[:3, :3], m[:3, 3] = np.array(r), np.array(p)
    return m


def margin(point, polygon):
    """Signed distance from a 2D point to a convex polygon's boundary: positive inside."""
    hull = ConvexHull(polygon)
    return float(-np.max(hull.equations[:, :2] @ point + hull.equations[:, 2]))


def posed(waypoints, ease, t):
    """A motion's pose at t, as the document plays it: linear between waypoints, or each step eased in and out."""
    pose_of = lambda waypoint: POSES[waypoint] if isinstance(waypoint, str) else waypoint
    for (t0, a), (t1, b) in zip(waypoints, waypoints[1:]):
        if t <= t1:
            share = min(1.0, max(0.0, (t - t0) / (t1 - t0)))
            share = share * share * (3.0 - 2.0 * share) if ease == "cubic" else share
            a, b = pose_of(a), pose_of(b)
            return {name: a[name] + (b[name] - a[name]) * share for name in a}
    return pose_of(waypoints[-1][1])


def on_the_floor(pose, foot, links):
    """({link: where its centre of mass is}, {side: its sole's points [(link, point)]}) with `foot` set where it
    stands at the zero pose."""
    ground = matrix(kin.stance(pose, foot))
    transforms = kin.link_transforms(pose)
    centres = {link: (ground @ matrix(transforms[link]) @ np.append(centre, 1.0))[:3] for link, (_, centre) in links.items()}
    soles = {s: [] for s in kin.SIDES}
    for s, link, point in kin.sole_points(pose):
        soles[s].append((link, (ground @ np.append(point, 1.0))[:3]))
    return centres, soles


def follow(name, waypoints, ease, links, total):
    """One motion on a floor: (its least margin, when, on how many feet), the same of its centre of pressure, how
    far each foot moved while down, the lowest any sole point went, and for how long it stood on one foot."""
    duration, foot = waypoints[-1][0], KEPT.get(name, "l_foot")
    least, pressed = (float("inf"), 0.0, 2), (float("inf"), 0.0, 2)
    stood, scrub, lowest, alone = {}, {s: 0.0 for s in kin.SIDES}, 0.0, 0.0
    count = round(duration * RATE)
    centres_at = lambda t: on_the_floor(posed(waypoints, ease, min(duration, max(0.0, t))), foot, links)[0]
    for k in range(count + 1):
        t = duration * k / count
        centres, soles = on_the_floor(posed(waypoints, ease, t), foot, links)
        before, after = centres_at(t - STEP), centres_at(t + STEP)
        com = sum(mass * centres[link] for link, (mass, _) in links.items()) / total
        # The centre of pressure: where the floor's push must stand for the links' weights and accelerations to turn nothing.
        push, moment = 0.0, np.zeros(2)
        for link, (mass, _) in links.items():
            speeding = (before[link] - 2.0 * centres[link] + after[link]) / STEP ** 2
            push += mass * (G + speeding[2])
            moment += mass * ((G + speeding[2]) * centres[link][:2] - speeding[:2] * centres[link][2])
        pressure = moment / push
        down = [s for s in kin.SIDES if sum(point[2] < DOWN for link, point in soles[s] if link != "toe") >= 3]
        for s in kin.SIDES:
            lowest = min(lowest, min(point[2] for _, point in soles[s]))
            if s in down:
                stood.setdefault(s, soles[s])
                scrub[s] = max(scrub[s], max(float(np.linalg.norm(a[:2] - b[:2])) for (_, a), (_, b) in zip(stood[s], soles[s])))
            else:
                stood.pop(s, None)
        bearing = np.array([point[:2] for s in down for link, point in soles[s] if link != "toe"])
        inside = margin(com[:2], bearing) if len(bearing) >= 3 else float("-inf")
        pushed = margin(pressure, bearing) if len(bearing) >= 3 else float("-inf")
        alone += (len(down) == 1) * duration / count
        if inside < least[0]:
            least = (inside, t, len(down))
        if pushed < pressed[0]:
            pressed = (pushed, t, len(down))
    return least, pressed, scrub, lowest, alone


def main():
    links = weigh(galatea())
    total = sum(mass for mass, _ in links.values())
    print(f"mass {total:.1f} kg in {len(links)} links; the heaviest:")
    for name, (mass, _) in sorted(links.items(), key=lambda item: -item[1][0])[:10]:
        print(f"  {mass:6.2f} kg  {name}")
    legs = sum(mass for name, (mass, _) in links.items() if name[2:] in
               ("hip_yoke", "hip_cradle", "thigh", "knee_crank", "knee_rod", "shin", "ankle_crank", "ankle_rods",
                "ankle_gimbal", "foot", "toe"))
    print(f"  legs {legs:.1f} kg, of which below the knees "
          f"{sum(m for n, (m, _) in links.items() if n[2:] in ('shin', 'ankle_crank', 'ankle_rods', 'ankle_gimbal', 'foot', 'toe')):.1f} kg")
    failed = 0
    for name, pose in STANDING.items():
        ground = matrix(kin.stance(pose, PLANTED[name]) if name in PLANTED else kin.settle(pose))
        transforms = kin.link_transforms(pose)
        com = sum(mass * (ground @ matrix(transforms[link]) @ np.append(centre, 1.0))[:3]
                  for link, (mass, centre) in links.items()) / total
        soles = np.array([(ground @ np.append(point, 1.0))[:3] for _, link, point in kin.sole_points(pose)
                          if link != "toe" or name in DYNAMIC])
        contact = soles[soles[:, 2] < soles[:, 2].min() + 2.0][:, :2]
        if len(contact) < 3:
            print(f"  {name:13s} centre of mass ({com[0]:6.1f}, {com[1]:6.1f}, {com[2]:6.1f})  stands on {len(contact)} point(s)")
            failed += name not in DYNAMIC
            continue
        inside = margin(com[:2], contact)
        note = "  (a gait frame)" if name in DYNAMIC else "" if inside > 0 else "  OUTSIDE its support"
        print(f"  {name:13s} centre of mass ({com[0]:6.1f}, {com[1]:6.1f}, {com[2]:6.1f})  margin {inside:6.1f} mm{note}")
        failed += inside <= 0 and name not in DYNAMIC
    print("OK: every standing pose balances" if not failed else f"{failed} pose(s) do not balance")
    print(f"motions on a floor: the least margin of the centre of mass (of {MARGIN:.0f} mm) and of the centre of pressure "
          f"(of {PRESSURE:.0f}), how far a foot that is down moves (of {SCRUB} mm), the lowest a sole goes")
    unfit = 0
    for name, waypoints, ease in MOTIONS:
        (inside, when, feet), (pushed, then, _), scrub, lowest, alone = follow(name, waypoints, ease, links, total)
        wrong = [] if name in GAITS else [text for bad, text in (
            (inside < MARGIN, "its weight leaves its support"), (pushed < PRESSURE, "it is braked too hard for its support"),
            (max(scrub.values()) > SCRUB, "a foot slides"), (lowest < -DOWN, "a foot goes through the floor")) if bad]
        note = "  (a gait under a fixed pelvis)" if name in GAITS else "".join(f"  {text.upper()}" for text in wrong)
        on_one = f", {alone:.1f} s on one foot" if alone else ""
        print(f"  {name:8s} mass {inside:6.1f} mm at {when:4.2f} s on {feet} {'foot' if feet == 1 else 'feet'}, pressure {pushed:6.1f} at "
              f"{then:4.2f} s; feet move {scrub['l']:.2f} and {scrub['r']:.2f} mm; lowest {lowest:6.2f} mm{on_one}{note}")
        unfit += bool(wrong)
    print("OK: every motion but the gait can be followed on a floor" if not unfit else f"{unfit} motion(s) cannot be followed on a floor")
    return 1 if failed or unfit else 0


if __name__ == "__main__":
    sys.exit(main())
