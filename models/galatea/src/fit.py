# /// script
# dependencies = ["embreex", "numpy", "rtree", "trimesh"]
# ///
"""Does a lofted form hold what it is meant to cover, and with how much air?

    cad run src/fit.py                 every form in `lib.skin.FORMS` against the mechanism it covers
    cad run src/fit.py thigh shin      the named ones

A form is rows of `geo.S` sections; a skin's inner surface is that form drawn in by the
skin's thickness. For each form this samples the mechanism's meshes (their vertices, and
points along their edges) in the links the form covers and reports the least clearance
to the inner surface, where it is, and which part it is on, then the room at each row.
It is arithmetic on the sections, with no kernel call, so a form can be drawn and
redrawn in seconds; the exact check (`checks/interference.py`) has the last word.
"""

import sys

import build123d  # noqa: F401  (the model needs cad's build123d integration)
import numpy as np

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent / "checks"))
from common import load_parts, pose_parts  # noqa: E402

from galatea import galatea  # noqa: E402
from lib import skin  # noqa: E402

STEP = 4.0        # spacing of the points sampled along a mesh's edges, mm
# Skins that are single shells rather than a panel on a liner: no form has to hold them either.
OLD_SKINS = ("foot_shell", "toe_cap", "hand_back")


def points_of(parts, skip=()):
    """World points on the meshes of `parts` (but those labelled in `skip`): (points, owner index, names)."""
    clouds, owners, names = [], [], []
    for part in parts:
        label = part.path.split("/")[-1]
        if any(label.startswith(prefix) for prefix in skip):
            continue
        mesh = part.geometry.mesh
        vertices = mesh.vertices @ part.world[:3, :3].T + part.world[:3, 3]
        a, b = vertices[mesh.edges_unique[:, 0]], vertices[mesh.edges_unique[:, 1]]
        length = np.linalg.norm(b - a, axis=1)
        extra = [a[k] + (b[k] - a[k]) * t for k in np.nonzero(length > STEP)[0]
                 for t in np.linspace(0, 1, int(length[k] // STEP) + 2)[1:-1]]
        cloud = np.vstack([vertices, np.array(extra)]) if extra else vertices
        clouds.append(cloud)
        owners.append(np.full(len(cloud), len(names)))
        names.append(part.path)
    return np.vstack(clouds), np.concatenate(owners), names


def clearance(rows, points, inset):
    """How far inside the form (drawn in by `inset`) each point lies, mm along the ray from the
    section's centre (negative: outside). Points above or below the form get +inf."""
    rows = np.array(sorted(rows))                    # z, cx, cy, rx+, rx-, ry+, ry-, n
    z = points[:, 2]
    inside = (z >= rows[0, 0]) & (z <= rows[-1, 0])
    out = np.full(len(points), np.inf)
    if not inside.any():
        return out
    p = points[inside]
    k = np.clip(np.searchsorted(rows[:, 0], p[:, 2], side="right") - 1, 0, len(rows) - 2)
    t = ((p[:, 2] - rows[k, 0]) / (rows[k + 1, 0] - rows[k, 0]))[:, None]
    row = rows[k] * (1 - t) + rows[k + 1] * t
    dx, dy = p[:, 0] - row[:, 1], p[:, 1] - row[:, 2]
    rx = np.where(dx >= 0, row[:, 3], row[:, 4]) - inset
    ry = np.where(dy >= 0, row[:, 5], row[:, 6]) - inset
    n = row[:, 7]
    f = (np.abs(dx) / rx) ** n + (np.abs(dy) / ry) ** n
    s = np.maximum(f, 1e-12) ** (1.0 / n)            # the point lies at s of the way from the centre to the surface
    radius = np.hypot(dx, dy)
    out[inside] = np.where(radius > 1e-9, radius * (1.0 - s) / s, np.minimum(rx, ry))
    return out


def report(name, form, links):
    """The form `name` against what it covers, at the zero pose and at each of its `poses`
    (controls): a form rides on its `link`, and what moves under it is measured where it goes."""
    inset = form.get("inset", skin.PANEL_T + skin.LINER_T)
    air = form.get("air", skin.AIR)
    count, shown = 0, False
    for pose in [{}] + list(form.get("poses", ())):
        pose_parts(links, pose)
        parts = [part for link in form["covers"] for part in links[link]]
        points, owners, names = points_of(parts, skip=tuple(form.get("skip", ())) + tuple(skin.SKIN_LABELS) + OLD_SKINS)
        if "link" in form:                            # into the frame the form rides in
            back = np.linalg.inv(links[form["link"]][0].moved)
            points = points @ back[:3, :3].T + back[:3, 3]
        room = clearance(form["rows"], points, inset)
        held = np.isfinite(room)
        if "within" in form:                          # only the points inside a box are this form's to hold
            lo, hi = np.array(form["within"][0]), np.array(form["within"][1])
            held &= np.all((points >= lo) & (points <= hi), axis=1)
        for (y0, z0), (y1, z1) in form.get("above", ()):      # ... above each rim drawn in the side view (y, z)
            held &= points[:, 2] >= z0 + (z1 - z0) / (y1 - y0) * (points[:, 1] - y0)
        for (y0, z0), (y1, z1) in form.get("below", ()):
            held &= points[:, 2] <= z0 + (z1 - z0) / (y1 - y0) * (points[:, 1] - y0)
        for origin, axis, radius in form.get("holes", ()):    # ... and outside each round opening cut through it
            axis = np.array(axis) / np.linalg.norm(axis)
            off = points - np.array(origin)
            held &= np.linalg.norm(off - np.outer(off @ axis, axis), axis=1) > radius
        if not held.any():
            print(f"{name}: nothing of {form['covers']} lies in it")
            continue
        worst = int(np.argmin(np.where(held, room, np.inf)))
        tight = held & (room < air)
        count += int(tight.sum())
        at = "as built" if not pose else ", ".join(f"{k} {v:g}" for k, v in pose.items())
        print(f"{name} ({at}): least clearance {room[worst]:6.1f} mm at ({points[worst, 0]:.0f}, {points[worst, 1]:.0f}, {points[worst, 2]:.0f})"
              f" on {names[owners[worst]]}; {int(tight.sum())} of {int(held.sum())} points have less than {air:g} mm")
        by_part = {}
        for k in np.nonzero(tight)[0]:
            by_part[names[owners[k]]] = min(by_part.get(names[owners[k]], np.inf), room[k])
        for path, least in sorted(by_part.items(), key=lambda item: item[1])[:8]:
            print(f"    {least:6.1f} mm  {path}")
        if not shown or tight.any():
            shown = True
            rows = sorted(form["rows"])
            for low, high in zip(rows, rows[1:]):
                band = held & (points[:, 2] >= low[0]) & (points[:, 2] <= high[0])
                if band.any():
                    p = points[band]
                    print(f"    z {low[0]:6.0f}..{high[0]:6.0f}: x {p[:, 0].min():7.1f}..{p[:, 0].max():7.1f}   y {p[:, 1].min():7.1f}..{p[:, 1].max():7.1f}"
                          f"   least {room[band].min():6.1f}")
    pose_parts(links, {})
    return count


def main(names):
    links = load_parts(galatea())
    count = 0
    for name in names or skin.FORMS:
        count += report(name, skin.FORMS[name], links)
    print("OK: every form holds what it covers" if not count else f"{count} point(s) too close in all")
    return 1 if count else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
