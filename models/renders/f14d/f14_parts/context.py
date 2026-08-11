"""Shared helpers every F-14 part module uses.

Keeps part modules short and makes sure everyone builds groups the same way, so
the assembly tree and the explode grouping stay predictable.
"""

from __future__ import annotations

import math

from build123d import Compound, Location, Plane, Vector

from f14_parts.palette import srgb, style  # noqa: F401  (re-export)


def group(label, children):
    """A labelled sub-assembly node.

    NOTE: colour on a group compound is ignored by the render package -- only
    leaves carry colour -- so always ``style()`` the leaves, never the group.
    """
    kids = [c for c in children if c is not None]
    if not kids:
        raise RuntimeError(f"group {label!r} has no children")
    return Compound(children=kids, label=label)


def mirror_pair(build_one, label_base, sides=(1, -1)):
    """Build the same part for both sides.

    ``build_one(side)`` must return a FRESH shape each call: build123d
    ``children=`` REPARENTS, so the same object cannot live in two compounds.
    side=+1 is port (+Y), side=-1 is starboard.
    """
    out = []
    for side in sides:
        shape = build_one(side)
        if shape is None:
            continue
        shape.label = f"{label_base}:{'port' if side > 0 else 'stbd'}"
        out.append(shape)
    return out


def place(shape, x=0.0, y=0.0, z=0.0, rx=0.0, ry=0.0, rz=0.0):
    return Location((x, y, z), (rx, ry, rz)) * shape


def frame(origin, x_dir, z_dir):
    """An explicit Plane from direction vectors.

    ALWAYS build rotated frames this way.  ``Plane.rotated()`` composes in WORLD
    axes, not the plane's own, so on any plane whose axes are not the global
    ones it silently produces a valid solid of the wrong shape -- a spanwise
    aerofoil 'twist' comes out as a yaw that slides the section out of its own
    station.  See references/build123d-modeling.md.
    """
    return Plane(origin=Vector(*origin), x_dir=Vector(*x_dir), z_dir=Vector(*z_dir))


def section_frame(origin, sweep_deg=0.0, twist_deg=0.0, side=1):
    """A spanwise aerofoil section frame.

    Local +x runs aft along the chord, the normal runs outboard along the span.
    ``sweep_deg`` yaws the frame; ``twist_deg`` is incidence about the span
    axis, applied to the direction vectors rather than by rotating a plane.
    """
    t = math.radians(twist_deg)
    s = math.radians(sweep_deg)
    x_dir = Vector(math.cos(t) * math.cos(s), -side * math.cos(t) * math.sin(s), -math.sin(t))
    normal = Vector(math.sin(s), side * math.cos(s), 0.0)
    return Plane(origin=Vector(*origin), x_dir=x_dir, z_dir=normal)


# ---------------------------------------------------------------------------
# aerofoil sections
# ---------------------------------------------------------------------------


def naca4_points(thickness_frac, chord, n=48, camber=0.0, camber_pos=0.4,
                 sharp_te=True):
    """Closed NACA 4-digit-style section as (x, z) pairs, x aft from the LE.

    Wound counter-clockwise in the local frame (upper surface first, aft along
    the lower).  Winding matters: a clockwise polygon fuses as a reversed face
    and extrudes the other way.
    """
    t = thickness_frac
    m, p = camber, camber_pos

    def half(xc):
        yt = 5 * t * (0.2969 * math.sqrt(xc) - 0.1260 * xc - 0.3516 * xc ** 2
                      + 0.2843 * xc ** 3 - (0.1036 if sharp_te else 0.1015) * xc ** 4)
        if m == 0.0:
            return 0.0, yt, 0.0
        if xc < p:
            yc = m / p ** 2 * (2 * p * xc - xc ** 2)
            dy = 2 * m / p ** 2 * (p - xc)
        else:
            yc = m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * xc - xc ** 2)
            dy = 2 * m / (1 - p) ** 2 * (p - xc)
        return yc, yt, math.atan(dy)

    # cosine spacing so the leading edge is dense
    xs = [0.5 * (1 - math.cos(math.pi * i / (n - 1))) for i in range(n)]
    upper, lower = [], []
    for xc in xs:
        yc, yt, th = half(xc)
        upper.append((chord * (xc - yt * math.sin(th)), chord * (yc + yt * math.cos(th))))
        lower.append((chord * (xc + yt * math.sin(th)), chord * (yc - yt * math.cos(th))))
    pts = upper + list(reversed(lower[1:-1]))
    return pts


def biconvex_points(thickness_frac, chord, n=40, le_round=0.06):
    """A sharp-LE biconvex section -- the right shape for the glove vane, the
    ventral fins and the stabilator tips, where a NACA nose reads too blunt."""
    pts_u, pts_l = [], []
    for i in range(n):
        xc = 0.5 * (1 - math.cos(math.pi * i / (n - 1)))
        y = thickness_frac * 0.5 * math.sin(math.pi * xc ** (1.0 - le_round))
        pts_u.append((chord * xc, chord * y))
        pts_l.append((chord * xc, -chord * y))
    return pts_u + list(reversed(pts_l[1:-1]))
