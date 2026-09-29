"""Frame, placement and museum-section helpers shared by every builder.

Author per-cylinder geometry ONCE for cylinder 1 (h = +Z, y = +Y, t = +X) and
place copies with `on_cylinder(shape, k)`; repeated parts then share geometry.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import spec as S


# ---------------------------------------------------------------------------
# Vectors / planes
# ---------------------------------------------------------------------------
def _unit(v):
    n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def plane(origin, z_dir, x_dir=None) -> bd.Plane:
    """A Plane from explicit vectors; x_dir defaults to a stable perpendicular."""
    z = _unit(z_dir)
    if x_dir is None:
        ref = (0.0, 1.0, 0.0) if abs(z[1]) < 0.9 else (1.0, 0.0, 0.0)
        x = _cross(ref, z)
    else:
        x = x_dir
    d = x[0] * z[0] + x[1] * z[1] + x[2] * z[2]
    x = _unit((x[0] - d * z[0], x[1] - d * z[1], x[2] - d * z[2]))
    return bd.Plane(origin=bd.Vector(*origin), x_dir=bd.Vector(*x), z_dir=bd.Vector(*z))


def locate(shape, origin, z_dir, x_dir=None):
    """Copy of `shape` (authored at the origin, +Z up) with local +Z along z_dir."""
    return plane(origin, z_dir, x_dir).location * shape


def cyl_along(p0, p1, d: float):
    """Solid cylinder of diameter d from point p0 to point p1."""
    v = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    L = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    c = bd.Cylinder(d / 2.0, L, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return locate(c, p0, v)


def cyl_y(y0: float, y1: float, d: float, x: float = 0.0, z: float = 0.0):
    """Cylinder along the crank axis between stations y0 and y1."""
    return cyl_along((x, y0, z), (x, y1, z), d)


def revolve_y(profile_rz, arc: float = 360.0):
    """Solid of revolution about the crank axis from a closed (r, y) polygon
    (r >= 0). The profile lies in the +X half of the XY plane."""
    pts = [(r, y) for r, y in profile_rz]
    face = bd.make_face(bd.Polyline(*pts, close=True).edges())
    face = bd.Plane.XY * face
    return bd.revolve(face, axis=bd.Axis.Y, revolution_arc=arc)


# ---------------------------------------------------------------------------
# Cylinder placement
# ---------------------------------------------------------------------------
def cyl_location(k: int) -> bd.Location:
    """Maps the cylinder-1 frame onto cylinder k: a rotation of ALPHA(k) about
    ROT_AXIS (= -Y) through the origin."""
    return axis_rotation(S.ROT_AXIS, S.ALPHA(k))


def axis_rotation(axis, deg, origin=(0.0, 0.0, 0.0)) -> bd.Location:
    """Right-handed rotation of `deg` about `axis` through `origin`."""
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf
    tr = gp_Trsf()
    tr.SetRotation(gp_Ax1(gp_Pnt(*origin), gp_Dir(*axis)), math.radians(deg))
    return bd.Location(tr)


def on_cylinder(shape, k: int):
    """Copy of a cylinder-1-authored shape placed on cylinder k (shares geometry)."""
    return cyl_location(k) * shape


def check_cylinder_frame():
    """cyl_location(k) must map (0,0,h) -> cyl_u(k)*h and (t,0,0) -> cyl_t(k)*t."""
    for k in range(1, S.N_CYL + 1):
        loc = cyl_location(k)
        p = (loc * bd.Vertex(0, 0, 100)).center()
        q = (loc * bd.Vertex(100, 0, 0)).center()
        u, t = S.cyl_u(k), S.cyl_t(k)
        assert abs(p.X - 100 * u[0]) < 1e-6 and abs(p.Z - 100 * u[2]) < 1e-6, (k, p)
        assert abs(q.X - 100 * t[0]) < 1e-6 and abs(q.Z - 100 * t[2]) < 1e-6, (k, q)


# ---------------------------------------------------------------------------
# Cylinder WEDGES. Adjacent cylinders' pistons are both deep in their stroke at
# the same time, and two Ø146 bodies whose axes are 40° apart overlap below
# h ~ 213. So everything that belongs to one cylinder and reaches low (the
# piston skirt, the barrel skirt) is trimmed to its own 40° wedge: the region
# between the two planes through the crank axis at ±20° from its axis, each
# moved inward by WEDGE_CLEARANCE/2. Neighbours then can never meet. The ring
# belt and bore above h ~ 205 are wider than 146 inside the wedge, so they stay
# full circles.
# ---------------------------------------------------------------------------
WEDGE_HALF_ANGLE = 20.0
WEDGE_CLEARANCE = 2.0      # total gap between neighbours (1 mm each side)


def wedge_cutters(lift: float = 0.0):
    """Two half-space boxes that remove everything of a CYLINDER-1-authored shape
    outside its wedge. `lift` raises the cutters along +Z: a moving part authored
    at rest height H0 whose lowest travel is Hmin uses lift = H0 - Hmin, so the
    trim holds at the bottom of its stroke (and hence everywhere)."""
    cutters = []
    for sgn in (1.0, -1.0):
        b = math.radians(WEDGE_HALF_ANGLE)
        # outward normal of the bisector plane toward the neighbour on this side
        n = (sgn * math.cos(b), 0.0, -math.sin(b))
        origin = (-n[0] * WEDGE_CLEARANCE / 2.0, 0.0, -n[2] * WEDGE_CLEARANCE / 2.0 + lift)
        box = bd.Box(6000.0, 6000.0, 6000.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        cutters.append(plane(origin, n) * box)
    return cutters


def wedge_trim(shape, lift: float = 0.0):
    """`shape` (authored for cylinder 1) trimmed to cylinder 1's wedge."""
    return shape - wedge_cutters(lift)


# ---------------------------------------------------------------------------
# The museum sections (STATIC parts only — moving parts are never cut)
#
# 1. SECTIONED CYLINDER: cylinder 1 (top) is cut on the cylinder-row plane
#    y = 0 and its REAR half (0 < y < SECTION_Y_MAX) removed, beyond r =
#    SECTION_R_MIN (above the barrel's hold-down flange and nuts) and within
#    +-SECTION_HALF_ANGLE of its axis: barrel fins, head, rocker boxes and
#    covers, rear plug and lead, the intake pipe near the head, and the top of
#    the rear exhaust collector behind it. Seen from
#    the rear/above you look straight at the piston, rings, master rod and both
#    valves, springs and rockers in profile — nothing moving stands in front of
#    it (the pushrods are all at the front). The front of cylinder 1 is intact,
#    so the head-on star is complete.
# 2. CRANKCASE WINDOW: the crankcase front wall is opened in an annulus
#    WINDOW_R (r between) for y < WINDOW_Y_MAX, leaving three slim webs at
#    WINDOW_WEB_ANGLES carrying the front main-bearing boss, so the master rod,
#    its flange, the knuckle pins and all eight articulating rods show.
# 3. NOSE CUTAWAY: a sector of the nose case (in-plane angles NOSE_CUT_SECTOR,
#    the upper right seen from the front) is removed back to the crankcase, so
#    the cam ring, tappets, cam idler and reduction gearing show, and the line
#    of sight reaches the crankcase window behind them.
# ---------------------------------------------------------------------------
SECTION_CYL = 1
SECTION_HALF_ANGLE = 20.0
SECTION_R_MIN = 300.0
SECTION_Y_MAX = 340.0
WINDOW_R = (70.0, 238.0)
WINDOW_Y_MAX = -60.0
WINDOW_WEB_ANGLES = (60.0, 180.0, 300.0)   # webs sit behind the prop blades at rest
WINDOW_WEB_W = 26.0
NOSE_CUT_SECTOR = (-100.0, 12.0)            # in-plane degrees (negative = +X side)
NOSE_CUT_R_MIN = 60.0


def _inplane_angle(x, z):
    return math.degrees(math.atan2(-x, z))


def _big():
    return 3000.0


def _sector_solid(b0, b1, r0, r1, y0, y1, segments=None):
    """Annular sector between in-plane angles b0 < b1, radii r0 < r1, stations y0 < y1."""
    pts_out = []
    n = max(8, int((b1 - b0) / 3))
    for i in range(n + 1):
        b = math.radians(b0 + (b1 - b0) * i / n)
        pts_out.append((-r1 * math.sin(b), r1 * math.cos(b)))
    pts_in = []
    for i in range(n, -1, -1):
        b = math.radians(b0 + (b1 - b0) * i / n)
        pts_in.append((-r0 * math.sin(b), r0 * math.cos(b)))
    pts = pts_out + pts_in if r0 > 0 else pts_out + [(0.0, 0.0)]
    # profile in the XZ plane at station y0, extruded toward +Y
    pl = bd.Plane(origin=(0, y0, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
    face = bd.make_face(bd.Polyline(*[(x, -z) for x, z in pts], close=True).edges())
    # Plane with z_dir=+Y and x_dir=+X has local y = -Z; so local (x, -z) -> world (x, z)
    return bd.extrude(pl * face, amount=y1 - y0)


def section_cutter():
    """Removal volume of the sectioned cylinder (region 1 above)."""
    return _sector_solid(-SECTION_HALF_ANGLE, SECTION_HALF_ANGLE, SECTION_R_MIN, 1200.0, 0.0, SECTION_Y_MAX)


def window_cutter():
    """Removal volume of the crankcase front window (region 2), webs left standing."""
    ring = _sector_solid(-180.0, 180.0, WINDOW_R[0], WINDOW_R[1], -400.0, WINDOW_Y_MAX)
    webs = []
    for b in WINDOW_WEB_ANGLES:
        web = bd.Box(WINDOW_WEB_W, 400.0, WINDOW_R[1] + 20, align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.MIN))
        webs.append(axis_rotation(S.ROT_AXIS, b) * bd.Pos(0, WINDOW_Y_MAX + 1, 0) * web)
    return ring - webs


def nose_cutter():
    """Removal volume of the nose-case cutaway (region 3)."""
    b0, b1 = NOSE_CUT_SECTOR
    return _sector_solid(b0, b1, NOSE_CUT_R_MIN, 600.0, -2000.0, S.CRANKCASE_Y[0] + 0.5)


SKIN_T = 0.4   # thickness of the red museum paint skin on cut faces


def _eroded_sector(b0, b1, r0, r1, y0, y1, t):
    """The same sector shrunk by t on every face (angles by t at the inner radius)."""
    rin = max(r0, 1.0)
    db = math.degrees(t / rin)
    return _sector_solid(b0 + db, b1 - db, r0 + t if r0 > 0 else 0.0, r1 - t, y0 + t, y1 - t)


def section_band():
    """Thin layer just inside the section cutter's boundary."""
    a, t = SECTION_HALF_ANGLE, SKIN_T
    return section_cutter() - _eroded_sector(-a, a, SECTION_R_MIN, 1200.0, 0.0, SECTION_Y_MAX, t)


def nose_band():
    b0, b1 = NOSE_CUT_SECTOR
    return nose_cutter() - _eroded_sector(b0, b1, NOSE_CUT_R_MIN, 600.0, -2000.0, S.CRANKCASE_Y[0] + 0.5, SKIN_T)


def window_band():
    t = SKIN_T
    ring = _sector_solid(-180.0, 180.0, WINDOW_R[0] + t, WINDOW_R[1] - t, -400.0 + t, WINDOW_Y_MAX - t)
    webs = []
    for b in WINDOW_WEB_ANGLES:
        web = bd.Box(WINDOW_WEB_W + 2 * t, 400.0, WINDOW_R[1] + 20, align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.MIN))
        webs.append(axis_rotation(S.ROT_AXIS, b) * bd.Pos(0, WINDOW_Y_MAX + 1, 0) * web)
    return window_cutter() - (ring - webs)


_BANDS = {"section": section_band, "nose": nose_band, "window": window_band}
_CUTTERS = {"section": section_cutter, "nose": nose_cutter, "window": window_cutter}


def cut_with_skin(shape, which: str = "section"):
    """(cut shape or None when wholly removed, red skin or None). The skin is the SKIN_T-thick layer of the
    ORIGINAL shape lying just inside the removed region against every cut face,
    so it covers the cut faces exactly and never overlaps the kept part. Label
    the skin `<group>:section_skin_<part>` (same group prefix as the part, so a
    moving part's skin moves with it) and colour it palette.SECTION_RED."""
    kept = cut(shape, _CUTTERS[which]())
    if kept is shape:
        return shape, None
    if kept is None:
        return None, None     # entirely removed: omit the part (and its hardware)
    try:
        skin = shape & _BANDS[which]()
    except Exception:
        skin = None
    if skin is None or not skin.solids() or sum(x.volume for x in skin.solids()) < 1e-3:
        return kept, None
    return kept, skin


def in_section(p) -> bool:
    """True when point p lies in the sectioned cylinder's removed region."""
    x, y, z = p
    r = math.hypot(x, z)
    return 0.0 < y < SECTION_Y_MAX and r > SECTION_R_MIN and abs(_inplane_angle(x, z)) < SECTION_HALF_ANGLE


def in_window(p) -> bool:
    x, y, z = p
    r = math.hypot(x, z)
    if not (y < WINDOW_Y_MAX and WINDOW_R[0] < r < WINDOW_R[1]):
        return False
    b = _inplane_angle(x, z)
    for w in WINDOW_WEB_ANGLES:
        # perpendicular distance to the web's centre plane
        d = abs(math.sin(math.radians(b - w))) * r
        if d < WINDOW_WEB_W / 2 and math.cos(math.radians(b - w)) > 0:
            return False
    return True


def in_nose_cut(p) -> bool:
    x, y, z = p
    b = _inplane_angle(x, z)
    return y < S.CRANKCASE_Y[0] and math.hypot(x, z) > NOSE_CUT_R_MIN and NOSE_CUT_SECTOR[0] < b < NOSE_CUT_SECTOR[1]


def cut(shape, cutter):
    """shape minus cutter; returns the shape unchanged if they do not meet."""
    bb1, bb2 = shape.bounding_box(), cutter.bounding_box()
    if (bb1.max.X < bb2.min.X or bb2.max.X < bb1.min.X or bb1.max.Y < bb2.min.Y
            or bb2.max.Y < bb1.min.Y or bb1.max.Z < bb2.min.Z or bb2.max.Z < bb1.min.Z):
        return shape
    out = shape - cutter
    if out is None or not out.solids():
        return None          # the whole shape lay inside the removed region
    # Guard against inverted/garbage booleans: a cut can only remove material.
    v0 = sum(s.volume for s in shape.solids())
    v1 = sum(s.volume for s in out.solids()) if out.solids() else 0.0
    ob = out.bounding_box() if out.solids() else None
    if v1 > v0 * (1 + 1e-6) + 1e-3 or (ob is not None and (
            ob.min.X < bb1.min.X - 0.01 or ob.min.Y < bb1.min.Y - 0.01 or ob.min.Z < bb1.min.Z - 0.01
            or ob.max.X > bb1.max.X + 0.01 or ob.max.Y > bb1.max.Y + 0.01 or ob.max.Z > bb1.max.Z + 0.01)):
        raise RuntimeError(f"geo.cut produced a bad solid for {getattr(shape, 'label', '?')!r}: "
                           f"volume {v0:.1f} -> {v1:.1f}, bbox grew")
    return out


# ---------------------------------------------------------------------------
# Soundness gate (same as the W16's): valid, closed, positive volume, BOP-clean
# ---------------------------------------------------------------------------
def sound(shape) -> bool:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Check

    try:
        if shape is None or shape.wrapped is None or not shape.is_valid:
            return False
        solids = shape.solids()
        if not solids:
            return False
        for s in solids:
            if s.volume <= 1e-6:
                return False
            for sh in s.shells():
                if not BRep_Tool.IsClosed_s(sh.wrapped):
                    return False
        return BRepAlgoAPI_Check(shape.wrapped).IsValid()
    except Exception:
        return False


if __name__ == "__main__":
    check_cylinder_frame()
    for name, c in (("section", section_cutter()), ("window", window_cutter()), ("nose", nose_cutter())):
        print(name, sound(c), round(c.volume))
    print("frame ok")
