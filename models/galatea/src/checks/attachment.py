# /// script
# dependencies = ["embreex", "numpy", "rtree", "trimesh"]
# ///
"""Is every part of Galatea held by something?

    cad run src/checks/attachment.py

A link is one rigid body, so each of its parts must touch another part of the same link:
bolted to it, seated on it or pinned through it. A part that touches nothing in its own
link (a pushrod, a crankshaft) must then be held by a joint: it must touch a part of a link
it is jointed to. This measures, part by part, the gap to the nearest such part (on the
meshes, so within their 0.3 mm or so) and names any part that hangs in the air.
"""

import sys

import build123d  # noqa: F401  (the model needs cad's build123d integration)
import numpy as np
import trimesh
from common import boxes_meet, load_parts

from galatea import galatea
from lib import kin

REACH = 0.6          # a part within this of a neighbour is held, mm
SAMPLES = 800


def gap(a, b):
    """The smallest distance (mm) from a's sampled surface to b's surface."""
    carry = np.linalg.inv(b.world) @ a.world
    mesh = a.geometry.mesh
    points = np.vstack([mesh.vertices, mesh.triangles_center]) @ carry[:3, :3].T + carry[:3, 3]
    lo, hi = b.geometry.mesh.bounds
    near = points[np.all((points >= lo - 2.0) & (points <= hi + 2.0), axis=1)]
    if not len(near):
        return np.inf
    if len(near) > SAMPLES:
        near = near[np.random.default_rng(0).choice(len(near), SAMPLES, replace=False)]
    _, distance, _ = trimesh.proximity.closest_point(b.geometry.mesh, near)
    return float(distance.min())


def main():
    links = load_parts(galatea())
    jointed = {}
    for parent, child, *_ in kin.all_joints().values():
        jointed.setdefault(parent, []).append(child)
        jointed.setdefault(child, []).append(parent)
    floating, pinned = [], 0

    def nearest(a, others):
        best = np.inf
        for b in others:
            if b is a or not boxes_meet(a.lo, a.hi, b.lo, b.hi, slack=2.0):
                continue
            best = min(best, gap(a, b), gap(b, a))
            if best <= REACH:
                break
        return best

    for link, parts in links.items():
        for a in parts:
            best = nearest(a, parts)
            if best > REACH:                               # not held in its link: by a joint's pin, then?
                best = min(best, nearest(a, [p for other in jointed[link] for p in links[other]]))
                pinned += best <= REACH
            if best > REACH:
                floating.append((best, a.path))
    print(f"{sum(len(p) for p in links.values())} parts in {len(links)} links")
    for best, path in sorted(floating, reverse=True):
        print(f"  {path} hangs {'alone' if np.isinf(best) else f'{best:.1f} mm from its nearest neighbour'}")
    print(f"OK: every part is held ({pinned} of them by a joint's pin alone)" if not floating
          else f"{len(floating)} part(s) are not held")
    return 1 if floating else 0


if __name__ == "__main__":
    sys.exit(main())
