"""Halo: one continuous titanium loop standing on a central blade pillar.

WHY THE LOOP IS ONE BODY
------------------------
Modelling the halo as three welded tubes gives three junctions to fudge. Here
the loop is a SINGLE loft that runs from the left rear mount, forward and
inboard around the cockpit opening, across the centreline at the front, and
back down to the right rear mount. There is no seam to hide, and the section
frame rotates with the path — which is what makes the cross-section evolve on
its own:

    at the mounts   deep vertical blade, thick across, blunt tail
    over the head   shallow and thin — the loop nearly disappears head-on
    at the front    the frame has swung 90 deg, so the section is deep
                    front-to-back with its round nose into the airstream

The leading edge — top of the blade on the sides, front of the blade at the
apex — is therefore ONE continuous line around the whole loop, and the single
vermillion spine stripe rides it from mount to mount. That is the only accent
on this part.
"""

from __future__ import annotations

import math

from build123d import Cylinder, Location, Plane, Pos, Vector, make_face

from . import lib, spec

# ==========================================================================
# PATH — left rear mount, forward around the opening, to the centreline apex
#
#  x,     y,     z,     chord, t/c,  te
# ==========================================================================

_LOOP = (
    (-1432.0, 336.0, 700.0, 104.0, 0.34, 11.0),
    (-1400.0, 340.0, 730.0, 100.0, 0.32, 10.0),
    (-1355.0, 343.0, 758.0, 95.0, 0.30, 9.0),
    (-1290.0, 344.0, 778.0, 89.0, 0.28, 8.0),
    (-1200.0, 342.0, 792.0, 84.0, 0.26, 7.0),
    (-1100.0, 336.0, 802.0, 80.0, 0.25, 7.0),
    (-990.0, 326.0, 810.0, 77.0, 0.24, 6.0),
    (-880.0, 310.0, 814.0, 75.0, 0.24, 6.0),
    (-780.0, 290.0, 817.0, 76.0, 0.25, 6.0),
    (-690.0, 266.0, 819.0, 79.0, 0.26, 7.0),
    (-615.0, 236.0, 821.0, 84.0, 0.27, 7.0),
    (-556.0, 196.0, 823.0, 90.0, 0.28, 8.0),
    (-508.0, 144.0, 825.0, 96.0, 0.29, 9.0),
    (-480.0, 78.0, 827.0, 101.0, 0.30, 10.0),
    (-472.0, 0.0, 828.0, 104.0, 0.30, 10.0),  # apex, on the centreline
)

HALO_APEX = _LOOP[-1][:3]
HALO_MOUNT = _LOOP[0][:3]

PILLAR_ROOT = (spec.HALO_FRONT_X, 0.0, 560.0)
PILLAR_TOP = (-455.0, 0.0, 824.0)


def _stations():
    """Full loop: left side, apex, mirrored right side."""
    left = list(_LOOP)
    right = [(x, -y, z, c, t, e) for (x, y, z, c, t, e) in reversed(left[:-1])]
    return left + right


def _frame(pts, i):
    """Unit tangent at station i of a polyline."""
    n = len(pts)
    a = pts[max(i - 1, 0)]
    b = pts[min(i + 1, n - 1)]
    return Vector(b[0] - a[0], b[1] - a[1], b[2] - a[2]).normalized()


def _chord_dir(t: Vector) -> Vector:
    """Section long axis: vertical where the loop runs fore/aft, along X where
    it runs across. Blended off the tangent's own plan angle so the frame never
    snaps — which is exactly what `lib._ortho_basis` would do here."""
    plan = math.hypot(t.X, t.Y)
    s = abs(t.Y) / plan if plan > 1e-9 else 1.0
    raw = Vector(0, 0, -1) * (1.0 - s) + Vector(-1, 0, 0) * s
    cd = raw - t * raw.dot(t)
    if cd.length < 1e-6:
        cd = Vector(0, 0, -1) - t * Vector(0, 0, -1).dot(t)
    return cd.normalized()


def _section(p, t: Vector, cd: Vector, chord: float, tr: float, te: float):
    wire = lib.airfoil_profile(
        chord, thickness=tr, camber=0.0, samples=27, te_thickness=te
    )
    face = Location((-0.5 * chord, 0, 0)) * make_face(wire)
    return Plane(origin=Vector(p), x_dir=cd, z_dir=t) * face


def _loop_solid():
    st = _stations()
    faces = []
    for i, (x, y, z, chord, tr, te) in enumerate(st):
        t = _frame(st, i)
        faces.append(_section((x, y, z), t, _chord_dir(t), chord, tr, te))
    return lib.loft_solid(faces)


def _spine_stripe():
    """THE accent: a 12 mm ribbon on the loop's leading edge, mount to mount."""
    st = _stations()
    secs = []
    for i, (x, y, z, chord, _, _) in enumerate(st):
        t = _frame(st, i)
        cd = _chord_dir(t)
        le = Vector(x, y, z) - cd * (0.5 * chord)
        k = 1.0 if 1 < i < len(st) - 2 else 0.5
        secs.append(
            {
                "plane": lib.plate_plane(le, t, up=-cd),
                "pts": lib.rounded_plate_pts(13.0 * k, 4.6 * k, 2.0 * k),
            }
        )
    return lib.swept_plate(secs)


def _pillar():
    return lib.blade_member(
        PILLAR_ROOT, PILLAR_TOP, 138.0, 96.0, thickness_ratio=0.30
    )


# ==========================================================================
# MOUNTS — three machined lugs, each with visible fastener bosses
# ==========================================================================

_FRONT_LUG = ((-430.0, -74.0, 624.0), (-430.0, 74.0, 624.0), 156.0, 0.34)
_REAR_LUG = ((-1432.0, 300.0, 692.0), (-1432.0, 366.0, 692.0), 120.0, 0.44)

_FRONT_STUDS = ((-412.0, 54.0, 645.0), (-472.0, 54.0, 641.0))
_REAR_STUDS = ((-1430.0, 336.0, 713.0), (-1478.0, 336.0, 708.0))


def _lug(spec_tuple):
    p0, p1, chord, tr = spec_tuple
    return lib.blade_member(p0, p1, chord, chord * 0.94, thickness_ratio=tr)


def _studs(tag: str, points, r: float = 8.5, h: float = 17.0):
    out = []
    for i, p in enumerate(points):
        boss = Pos(p) * Cylinder(r, h)
        out += lib.pair(boss, f"halo_stud_{tag}{i}", spec.STEEL)
    return out


def build_halo_bodies():
    """Every halo body, already labelled and coloured."""
    bodies = [
        lib.styled(_loop_solid(), "halo_loop", spec.TITANIUM),
        lib.styled(_pillar(), "halo_pillar", spec.TITANIUM),
        lib.styled(_spine_stripe(), "halo_spine_stripe", spec.ACCENT),
        lib.styled(_lug(_FRONT_LUG), "halo_mount_front", spec.ANODIZED),
    ]
    bodies += lib.pair(_lug(_REAR_LUG), "halo_mount_rear", spec.ANODIZED)
    bodies += _studs("f", _FRONT_STUDS)
    bodies += _studs("r", _REAR_STUDS, r=8.0, h=15.0)
    return bodies
