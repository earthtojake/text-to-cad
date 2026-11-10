# /// script
# dependencies = ["numpy", "scipy", "trimesh"]
# ///
"""Where is Galatea's mass, and does each standing pose balance?

    cad run src/checks/balance.py

Weighs every part by its material's density (an actuator, the battery and the modules
carry homogenised densities, `lib/finish.py`), sums by link, and for each standing pose
puts the centre of mass over the ground: a pose balances statically when that point lies
inside the support polygon, the hull of the sole points on the floor. The margin is the
distance from the point to the polygon's nearest edge.
"""

import re
import sys

import build123d  # noqa: F401  (the model needs cad's build123d integration)
import numpy as np
from common import load_parts
from scipy.spatial import ConvexHull

from galatea import galatea
from lib import kin
from lib.poses import POSES

STANDING = {"zero": {}, **{name: POSES[name] for name in ("ready", "stride", "contrapposto", "reach", "wave",
                                                           "present", "crouch", "bow", "poise", "fists")}}
PLANTED = {"bow": "l_foot", "crouch": "l_foot"}     # poses that tip the pelvis are set down on a foot, as `stances.py` does
DYNAMIC = {"stride"}                                # a frame of a gait: reported, not required to balance


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
            mesh = part.geometry.mesh
            kg = abs(mesh.volume) * 1e-9 * density[label]
            mass += kg
            moment += kg * (part.rest @ np.append(mesh.center_mass, 1.0))[:3]
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
        soles = np.array([(ground @ np.append(point, 1.0))[:3] for _, _, point in kin.sole_points(pose)])
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
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
