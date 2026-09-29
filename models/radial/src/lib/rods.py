"""Rods: the master rod (cylinder 1) with its knuckle-pin flange, eight knuckle
pins and their lock plates, the crankpin bearing, and eight articulating rods.

Everything is authored in the engine frame at theta = 0 (kin's rest pose):
the crankpin centre is at (0, 0, 73), the master rod points straight up (+Z) to
cylinder 1's wrist pin, and articulating rod k runs from kin.knuckle(0, k) to
kin.wrist_pin(0, k).

Stacking along the crank axis (|y|):
  0 .. 11.5   articulating-rod knuckle eyes (+ bronze bushings) in the slot
              between the flange plates; the master's hub (r 41) and shank core
 12 .. 26     the two flange plates (a nine-lobed flower: 8 pin bosses + the
              shank root), knuckle pins through both
 26 .. 30     lock plates, their bolts and safety wire (front); pin heads (rear)
 26 .. 40     big-end barrel (r 43.5); bronze crankpin shell to |y| 40.5
 small ends   master |y| <= 17, articulating |y| <= 15 (piston bosses at 19)

Parts are local-frame prototypes placed with plain Locations so repeated parts
share geometry. `sweep()` is the kinematic collision sweep (python -m lib.rods).
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import fasteners as F
from lib import geo
from lib import kin
from lib import palette as P
from lib import spec as S

MATERIALS = ("steel_machined", "bronze", "fastener", "safety_wire")

# ---------------------------------------------------------------------------
# Dimensions (design, inside the spec envelope)
# ---------------------------------------------------------------------------
PIN_Y = 73.0                         # crankpin centre height at theta = 0 (= R_CRANK)
RUN = 0.15                           # radial running clearance of every bearing (>= 0.1: no render z-fight)
KP_D = 22.0                          # knuckle pin (brief: 22; spec.KNUCKLE_PIN_D says 24, unused)
KP_BORE = 10.0                       # hollow knuckle pin
FLANGE_Y = S.MASTER_FLANGE_Y         # (12, 26)
EYE_HW = S.ART_ROD_EYE_W / 2.0       # 11.5

# master rod
BE_SHELL_OD = 76.0                   # crankpin shell OD (= big-end bore)
BE_SHELL_HW = 40.5
BE_BARREL_R = 43.5                   # big-end barrel outside the flanges
BE_BARREL_HW = 40.0
HUB_R = 41.0                         # hub between the flange plates
FLOWER_CORE_R = 54.0
FLOWER_BOSS_R = 19.0
M_SMALL_R = 31.0
M_SMALL_HW = S.ROD_SMALL_END_HALF_W  # 17
M_BUSH_OD = 45.0
M_SHANK_HW = ((40.0, 17.5), (232.0, 13.0))   # (z from crankpin, half-width)
M_SHANK_DEPTH = 17.0                 # |y| of the shank's I-flanges
M_WEB = 5.0                          # |y| of the web faces (web 10 thick)

# articulating rod (local: knuckle at origin, +Z to the wrist pin)
A_EYE_R = 18.0
A_BUSH_OD = 28.0
A_SMALL_R = 27.0
A_SMALL_HW = 15.0
A_BUSH_SMALL_OD = 44.0
A_SHANK_HW = ((20.0, 10.0), (175.0, 12.0))
A_WEB = 3.5                          # web 7 thick

# lock plates
LP_T = 1.6
LP_BOLT_R = 51.0                     # bolt circle about the crankpin
LP_BOLT_DA = 12.0                    # bolts at pin angle +- this
LP_BOLT_D = 4.0
LP_TAP_D = 3.8                       # tapped-hole bore (bolt shank modelled at pitch dia 3.55)
LP_HEAD_AF = 7.0
LP_HEAD_H = 2.4
WIRE_D = 0.8


# ---------------------------------------------------------------------------
# 2D helpers: faces in the rod plane, (x, z) -> world (x, y, z)
# ---------------------------------------------------------------------------
def _xz_plane(y: float) -> bd.Plane:
    # x_dir +X, z_dir -Y  ->  local (u, v) = world (u, y, v); extrude runs toward -Y
    return bd.Plane(origin=(0, y, 0), x_dir=(1, 0, 0), z_dir=(0, -1, 0))


def slab(sketch, y0: float, y1: float):
    """Extrude an (x, z) sketch between stations y0 < y1."""
    return bd.extrude(_xz_plane(y1) * sketch, amount=y1 - y0)


def circ(r, x=0.0, z=0.0):
    return bd.Pos(x, z) * bd.Circle(r)


def poly(pts):
    return bd.Polygon(*pts, align=None)


def round2d(sk, r):
    """Fillet every vertex of a 2D sketch (ladder down on failure)."""
    for rr in (r, r * 0.75, r * 0.5, r * 0.3):
        try:
            out = bd.fillet(sk.vertices(), radius=rr)
            if out.area > 0:
                return out
        except Exception:
            pass
    return sk


def taper_poly(z0, z1, hw0, hw1, zz0, zz1):
    """Trapezoid spanning z0..z1 with half-width linear between (zz0, hw0) and (zz1, hw1)."""
    def hw(z):
        return hw0 + (hw1 - hw0) * (z - zz0) / (zz1 - zz0)
    return poly([(-hw(z0), z0), (hw(z0), z0), (hw(z1), z1), (-hw(z1), z1)]), hw


def ybore(d, y0, y1, x=0.0, z=0.0):
    return geo.cyl_y(y0, y1, d, x, z)


def _fillet_edges(part, edges, r, min_r=0.4):
    out, got = C.safe_fillet(part, edges, r, min_r)
    return out


def _edges_on_plane_y(part, y, tol=1e-3):
    return [e for e in part.edges()
            if abs(e.bounding_box().min.Y - y) < tol and abs(e.bounding_box().max.Y - y) < tol]


# ---------------------------------------------------------------------------
# Articulating rod (one prototype, placed eight times)
# ---------------------------------------------------------------------------
def _art_rod_proto():
    L = S.L_ART
    (z0, h0), (z1, h1) = A_SHANK_HW
    shank, hw = taper_poly(0.0, L, h0, h1, z0, z1)
    plan = round2d(circ(A_EYE_R) + shank + circ(A_SMALL_R, 0, L), 14.0)
    body = slab(plan, -EYE_HW, EYE_HW)
    # machined thrust bosses on the small-end faces (1 mm shoulder, no tangent boolean)
    body = body + ybore(2 * A_SMALL_R - 2.0, -A_SMALL_HW, A_SMALL_HW, 0, L)
    # I-section: pockets in both faces, rounded-end tapered slots
    pz0, pz1 = 40.0, 158.0
    pk = round2d(taper_poly(pz0, pz1, hw(pz0) - 4.2, hw(pz1) - 4.2, pz0, pz1)[0], 5.0)
    pockets = [slab(pk, A_WEB, EYE_HW + 1), slab(pk, -EYE_HW - 1, -A_WEB)]
    bores = [ybore(A_BUSH_OD, -30, 30), ybore(A_BUSH_SMALL_OD, -30, 30, 0, L)]
    body = C.cut_all(body, pockets + bores)
    # forged blends: web-to-flange roots, then every remaining edge broken
    body = _fillet_edges(body, _edges_on_plane_y(body, A_WEB) + _edges_on_plane_y(body, -A_WEB), 3.0)
    neck = [e for e in body.edges()
            if e.bounding_box().min.Y > EYE_HW - 0.01 and e.bounding_box().max.Y < EYE_HW + 0.01
            and e.bounding_box().min.Z > L - A_SMALL_R - 12 and e.bounding_box().max.Z < L + 1]
    neck += [e for e in body.edges()
             if e.bounding_box().min.Y > -EYE_HW - 0.01 and e.bounding_box().max.Y < -EYE_HW + 0.01
             and e.bounding_box().min.Z > L - A_SMALL_R - 12 and e.bounding_box().max.Z < L + 1]
    body = _fillet_edges(body, neck, 2.5)
    body, _ = C.fillet_all(body, 1.0, min_r=0.3)
    # oil hole through the small-end crown
    body = body - geo.cyl_along((0, 0, L + 10), (0, 0, L + A_SMALL_R + 3), 4.0)
    return body


def _bushing(id_, od, hw, ch=0.6):
    """Bronze bushing along Y centred at the origin, both ends chamfered."""
    ri, ro = id_ / 2.0, od / 2.0
    prof = [(ri + ch, -hw), (ro - ch, -hw), (ro, -hw + ch), (ro, hw - ch), (ro - ch, hw),
            (ri + ch, hw), (ri, hw - ch), (ri, -hw + ch)]
    return geo.revolve_y(prof)


def _art_small_bushing():
    b = _bushing(S.WRIST_PIN_D + 2 * RUN, A_BUSH_SMALL_OD, A_SMALL_HW, 0.7)
    return b - geo.cyl_along((0, 0, 10), (0, 0, A_SMALL_R + 3), 4.0)


def art_rod_location(k: int) -> bd.Location:
    """Local (knuckle at origin, +Z to the wrist pin) -> engine frame at theta = 0."""
    kx = kin.knuckle(0.0, k)
    return bd.Location((kx[0], 0.0, kx[1])) * geo.axis_rotation(S.ROT_AXIS, kin.rod_angle(0.0, k))


# ---------------------------------------------------------------------------
# Master rod (local: crankpin centre at origin, +Z to the wrist pin)
# ---------------------------------------------------------------------------
def _pin_xz(k):
    a = math.radians(S.KNUCKLE_ANGLE(k))
    return (-S.RHO_KNUCKLE * math.sin(a), S.RHO_KNUCKLE * math.cos(a))


def _master_proto():
    L = S.L_MASTER
    (z0, h0), (z1, h1) = M_SHANK_HW
    # flower flange: core disc + 8 pin bosses + the shank-root lobe
    flower = circ(FLOWER_CORE_R)
    for k in range(2, 10):
        flower += circ(FLOWER_BOSS_R, *_pin_xz(k))
    flower += round2d(poly([(-34, 20), (34, 20), (19.0, 104), (-19.0, 104)]), 6.0)
    flower = round2d(flower, 5.0)
    plates = [slab(flower, FLANGE_Y[0], FLANGE_Y[1]), slab(flower, -FLANGE_Y[1], -FLANGE_Y[0])]
    # shank + small end (I-flanges at |y| <= 17)
    shank, hw = taper_poly(24.0, L, h0, h1, z0, z1)
    plan = round2d(shank + circ(M_SMALL_R, 0, L), 16.0)
    shank_body = slab(plan, -M_SHANK_DEPTH, M_SHANK_DEPTH)
    hub = ybore(2 * HUB_R, -FLANGE_Y[0] - 0.5, FLANGE_Y[0] + 0.5)
    barrels = [ybore(2 * BE_BARREL_R, FLANGE_Y[1] - 0.5, BE_BARREL_HW),
               ybore(2 * BE_BARREL_R, -BE_BARREL_HW, -FLANGE_Y[1] + 0.5)]
    body = C.fuse_all([hub, shank_body] + plates + barrels)
    # I-section pockets
    pz0, pz1 = 116.0, 222.0
    pk = round2d(taper_poly(pz0, pz1, hw(pz0) - 5.0, hw(pz1) - 5.0, pz0, pz1)[0], 7.0)
    cuts = [slab(pk, M_WEB, M_SHANK_DEPTH + 1), slab(pk, -M_SHANK_DEPTH - 1, -M_WEB)]
    cuts += [ybore(BE_SHELL_OD, -60, 60), ybore(M_BUSH_OD, -40, 40, 0, L)]
    cuts += [ybore(KP_D, -FLANGE_Y[1] - 1, FLANGE_Y[1] + 1, *_pin_xz(k)) for k in range(2, 10)]
    # tapped holes for the lock-plate bolts (front plate), drilled past the bolt tips
    for k in range(2, 10):
        a0 = S.KNUCKLE_ANGLE(k)
        for s in (-1, 1):
            b = math.radians(a0 + s * LP_BOLT_DA)
            cuts.append(ybore(LP_TAP_D, -FLANGE_Y[1] - 1, -FLANGE_Y[0] - 0.5,
                              -LP_BOLT_R * math.sin(b), LP_BOLT_R * math.cos(b)))
    body = C.cut_all(body, cuts)
    # blends: pocket roots, the plate-to-shank step, then every edge broken
    body = _fillet_edges(body, _edges_on_plane_y(body, M_WEB) + _edges_on_plane_y(body, -M_WEB), 4.0)
    step = [e for e in body.edges()
            if abs(abs(e.bounding_box().min.Y) - M_SHANK_DEPTH) < 1e-3
            and abs(abs(e.bounding_box().max.Y) - M_SHANK_DEPTH) < 1e-3
            and 70 < e.bounding_box().min.Z and e.bounding_box().max.Z < 112]
    body = _fillet_edges(body, step, 6.0)
    body, _ = C.fillet_all(body, 1.2, min_r=0.3)
    body = body - geo.cyl_along((0, 0, L + 12), (0, 0, L + M_SMALL_R + 3), 5.0)
    return body


def _crankpin_bearing():
    """Steel-backed lead-bronze shell with thrust lips, split at the rod axis sides."""
    ri, ro = S.CRANKPIN_D / 2.0 + RUN, BE_SHELL_OD / 2.0
    hw, lip = BE_SHELL_HW, 42.2
    prof = [(ri + 1.0, -hw), (lip - 0.4, -hw), (lip, -hw + 0.4), (lip, -BE_BARREL_HW + 0.0),
            (ro, -BE_BARREL_HW), (ro, BE_BARREL_HW), (lip, BE_BARREL_HW), (lip, hw - 0.4),
            (lip - 0.4, hw), (ri + 1.0, hw), (ri, hw - 1.0), (ri, -hw + 1.0)]
    return geo.revolve_y(prof)


def _small_bushing_master():
    b = _bushing(S.WRIST_PIN_D + 2 * RUN, M_BUSH_OD, M_SMALL_HW, 0.7)
    return b - geo.cyl_along((0, 0, 10), (0, 0, M_SMALL_R + 3), 5.0)


def _knuckle_pin():
    """Hollow pin: rear head (|y| 26..28.5), shank through both plates, front end
    flush with the front plate face under the lock plate."""
    r, rb = KP_D / 2.0, KP_BORE / 2.0
    y0, y1, yh = -FLANGE_Y[1], FLANGE_Y[1], FLANGE_Y[1] + 2.5
    rh = 14.0
    prof = [(rb, y0), (r - 0.6, y0), (r, y0 + 0.6), (r, y1), (rh - 0.6, y1), (rh, y1 + 0.6),
            (rh, yh - 0.8), (rh - 0.8, yh), (rb + 0.6, yh), (rb, yh - 0.6)]
    return geo.revolve_y(prof)


def _lock_plate():
    """Rounded-triangle lock plate over pin 'k' authored at in-plane angle 0 (pin at
    (0, 62) about the crankpin, seated on the FRONT face y = -26, reaching to -27.6)."""
    bolts = [(LP_BOLT_R * -math.sin(math.radians(s * LP_BOLT_DA)),
              LP_BOLT_R * math.cos(math.radians(s * LP_BOLT_DA))) for s in (-1, 1)]
    outline = bd.make_hull((circ(12.5, 0, S.RHO_KNUCKLE) + circ(4.8, *bolts[0]) + circ(4.8, *bolts[1])).edges())
    y0, y1 = -FLANGE_Y[1] - LP_T, -FLANGE_Y[1]
    plate = slab(outline, y0, y1)
    holes = [ybore(7.0, y0 - 1, y1 + 1, 0, S.RHO_KNUCKLE)]
    holes += [ybore(LP_BOLT_D + 0.3, y0 - 1, y1 + 1, *b) for b in bolts]
    plate = plate - holes
    plate = _fillet_edges(plate, _edges_on_plane_y(plate, y0), 0.6, 0.2)
    return plate, bolts


def _retainer_bolt():
    """AN-style hex bolt with a drilled head (wire hole across the flats)."""
    head = F._wrench_head(LP_HEAD_AF, 0.0, LP_HEAD_H)
    shank = F._threaded_shank(LP_BOLT_D, 9.0 + LP_T, z_top=0.3)
    bolt = head + shank
    hole = geo.cyl_along((-6, 0, LP_HEAD_H * 0.5), (6, 0, LP_HEAD_H * 0.5), 1.3)
    return bolt - hole


def _wire(bolts):
    """Safety wire between the two bolt heads, through their cross-drillings,
    with a slight sag toward the crankpin and a short twisted-off pigtail."""
    yw = -FLANGE_Y[1] - LP_T - LP_HEAD_H * 0.5
    (ax, az), (bx, bz) = bolts
    L = math.hypot(bx - ax, bz - az)
    ux, uz = (bx - ax) / L, (bz - az) / L          # a -> b
    nx, nz = uz, -ux                                # in-plane normal
    if nx * (ax + bx) + nz * (az + bz) > 0:        # make it point toward the crankpin
        nx, nz = -nx, -nz

    def P(s, sag, dy=0.0):
        return bd.Vector(ax + ux * s + nx * sag, yw + dy, az + uz * s + nz * sag)

    pts = [P(-2.0, 0.0), P(0.0, 0.0), P(4.6, 0.0), P(L / 2, 0.9), P(L - 4.6, 0.0), P(L, 0.0),
           P(L + 4.6, 0.0), P(L + 6.5, 0.6, -0.2), P(L + 8.0, 1.8, -0.4)]
    path = bd.Spline(*pts)
    t0 = path % 0
    prof = bd.Plane(origin=pts[0], z_dir=t0) * bd.Circle(WIRE_D / 2.0)
    return bd.sweep(prof, path=path)


def _place_pin_parts(proto, k):
    """Parts authored at the angle-0 pin station -> pin k (rotate about the crankpin)."""
    return geo.axis_rotation(S.ROT_AXIS, S.KNUCKLE_ANGLE(k)) * proto


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def _groups():
    """{group: [leaf, ...]} at theta = 0, labelled and coloured."""
    up = bd.Location((0, 0, PIN_Y))
    master = []

    def m(shape, label, color):
        master.append(P.style(up * shape, f"master:{label}", color))

    m(_master_proto(), "rod", P.STEEL_MACHINED)
    m(_crankpin_bearing(), "crankpin_bearing", P.BRONZE)
    m(_bushing_placed(_small_bushing_master(), (0, 0, S.L_MASTER)), "small_end_bushing", P.BRONZE)
    pin = _knuckle_pin()
    plate, bolts = _lock_plate()
    bolt = _retainer_bolt()
    wire = _wire(bolts)
    bolt_protos = [F.place(bolt, (bx, -FLANGE_Y[1] - LP_T, bz), (0, -1, 0), (1, 0, 0)) for bx, bz in bolts]
    for k in range(2, 10):
        px, pz = _pin_xz(k)
        m(bd.Location((px, 0, pz)) * pin, f"knuckle_pin_{k}", P.STEEL_MACHINED)
        m(_place_pin_parts(plate, k), f"knuckle_retainer_{k}", P.FASTENER)
        for n, b in enumerate(bolt_protos, 1):
            m(_place_pin_parts(b, k), f"retainer_bolt_{k}_{n}", P.FASTENER)
        m(_place_pin_parts(wire, k), f"retainer_wire_{k}", P.SAFETY_WIRE)
    groups = {"master": master}

    rod = _art_rod_proto()
    kb = _bushing(KP_D + 2 * RUN, A_BUSH_OD, EYE_HW, 0.6)
    sb = _art_small_bushing()
    sb_local = bd.Location((0, 0, S.L_ART)) * sb
    for k in range(2, 10):
        loc = art_rod_location(k)
        groups[f"artrod{k}"] = [
            P.style(loc * rod, f"artrod{k}:rod", P.STEEL_MACHINED),
            P.style(loc * kb, f"artrod{k}:knuckle_bushing", P.BRONZE),
            P.style(loc * sb_local, f"artrod{k}:small_end_bushing", P.BRONZE),
        ]
    return groups


def _bushing_placed(b, at):
    return bd.Location(at) * b


def build() -> list:
    parts = []
    for leaves in _groups().values():
        parts += leaves
    return parts


# ---------------------------------------------------------------------------
# Kinematic collision sweep: python -m lib.rods [step_deg]
# ---------------------------------------------------------------------------
def _proxy_piston(k):
    """Obstacle envelope of piston k at theta = 0, in the cylinder-1 frame then placed:
    skirt wall (OD 146, 5 thick) from 64 below the pin to the crown, crown underside
    44 above the pin, pin bosses from |y| 19 outward."""
    h = kin.piston_h(0.0, k)
    lo, top = h - S.PISTON_SKIRT_BELOW_PIN, h + S.PISTON_COMPRESSION_H
    skirt = geo.cyl_along((0, 0, lo), (0, 0, top), S.BORE) - geo.cyl_along((0, 0, lo - 1), (0, 0, h + 44), S.BORE - 10)
    bosses = [bd.Pos(0, s * (19 + 30), h + 5) * bd.Box(56, 60, 62) for s in (-1, 1)]
    env = skirt.fuse(*bosses) & geo.cyl_along((0, 0, lo), (0, 0, top), S.BORE)
    return geo.on_cylinder(env, k)


def _proxy_cheeks():
    return [geo.cyl_y(42.0, 64.0, 250.0), geo.cyl_y(-64.0, -42.0, 250.0)]


def _dist(a, b):
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    d.Perform()
    return d.Value() if d.IsDone() else float("nan")


def _bb_gap(a, b):
    A, B = a.bounding_box(), b.bounding_box()
    gx = max(0.0, max(A.min.X - B.max.X, B.min.X - A.max.X))
    gy = max(0.0, max(A.min.Y - B.max.Y, B.min.Y - A.max.Y))
    gz = max(0.0, max(A.min.Z - B.max.Z, B.min.Z - A.max.Z))
    return math.sqrt(gx * gx + gy * gy + gz * gz)


def _overlap(a, b):
    try:
        v = (a & b).volume
        return v
    except Exception:
        return float("nan")


def _samples(shape, spacing=0.7):
    """Dense surface samples (rest pose) of a shape: tessellation vertices plus
    even area samples, so no face is represented only by its corners."""
    import numpy as np
    import trimesh
    verts, tris = shape.tessellate(0.1, 0.2)
    V = np.array([(v.X, v.Y, v.Z) for v in verts])
    T = np.array(tris)
    mesh = trimesh.Trimesh(V, T, process=False)
    n = int(mesh.area / (spacing * spacing)) + 1
    pts, _ = trimesh.sample.sample_surface_even(mesh, n, radius=spacing * 0.5)
    return np.vstack([V, pts])


def _mat(pose):
    import numpy as np
    return np.array(kin.pose_matrix(pose))


def sweep(step=5.0, near=12.0, verbose=False, exact=True):
    """Collision sweep over 0..720 deg.

    Screen: every (theta, pair) on dense surface samples (rods 0.7 mm spacing,
    piston envelopes 1.2 mm), queried in the obstacle's own rest frame against a
    KD-tree built once. Exact: for every pair, BRepExtrema distance + boolean
    common volume on the placed BRep shapes at the pair's worst screened angle
    and its +- step neighbours.

    The master group is screened WITHOUT its knuckle pins: pin k runs inside
    articulating rod k's bushing by design (0.05 mm radial running clearance,
    checked exactly and reported separately), and a neighbouring rod can only
    reach pin j through bushing j. Crank cheeks: motion is planar, so the gap is
    the axial one; confirmed with BRep at a few angles.
    Returns ({pair: (brep_min, theta, screen_min)}, fits)."""
    import numpy as np
    from scipy.spatial import cKDTree
    groups = _groups()
    pins = {int(p.label.rsplit("_", 1)[1]): p for p in groups["master"] if p.label.startswith("master:knuckle_pin_")}
    comp = {g: bd.Compound(children=[p for p in leaves if not p.label.startswith("master:knuckle_pin_")])
            for g, leaves in groups.items()}
    obst = {f"piston{k}": _proxy_piston(k) for k in range(1, 10)}
    shapes = {**comp, **obst}
    pts = {n: _samples(sh, 0.7 if n in comp else 1.2) for n, sh in shapes.items()}
    trees = {n: cKDTree(X) for n, X in pts.items()}
    boxes = {n: (X.min(0) - near, X.max(0) + near) for n, X in pts.items()}

    def pose(n, th):
        if n == "master":
            return kin.pose_master(th)
        if n.startswith("artrod"):
            return kin.pose_art_rod(th, int(n[6:]))
        if n.startswith("piston"):
            return kin.pose_piston(th, int(n[6:]))
        return kin.pose_crank(th)

    names = list(comp)
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    for g in names:
        k = 1 if g == "master" else int(g[6:])
        for j in sorted({k, (k - 2) % 9 + 1, k % 9 + 1}):
            pairs.append((g, f"piston{j}"))
    screen = {p: (1e9, 0.0) for p in pairs}
    n_steps = int(round(720.0 / step))
    for i in range(n_steps):
        th = i * step
        M = {n: _mat(pose(n, th)) for n in shapes}
        for a, b in pairs:
            R = np.linalg.inv(M[b]) @ M[a]              # a's rest frame -> b's rest frame
            A = pts[a] @ R[:3, :3].T + R[:3, 3]
            lo, hi = boxes[b]
            sel = A[np.all((A >= lo) & (A <= hi), axis=1)]
            if len(sel) == 0:
                d = near
            else:
                dd, _ = trees[b].query(sel, k=1, distance_upper_bound=near)
                d = float(min(near, dd.min()))
            if d < screen[(a, b)][0]:
                screen[(a, b)] = (d, th)
        if verbose and i % 12 == 0:
            print(f"theta {th:5.0f}  screen min so far {min(v[0] for v in screen.values()):.2f}", flush=True)

    def exact_min(sa, sb, pa, pb, angles):
        best = (1e9, None)
        for t in angles:
            t %= 720.0
            A, B = kin.place(sa, pa(t)), kin.place(sb, pb(t))
            e = _dist(A, B)
            if e < 1e-6:
                print(f"  CONTACT at theta {t:.0f}: common volume {_overlap(A, B):.3f}")
            if e < best[0]:
                best = (e, t)
        return best

    out = {}
    for (a, b), (d, th) in screen.items():
        if not exact or d >= near:
            out[(a, b)] = (None, th, d)
            continue
        e, t = exact_min(shapes[a], shapes[b], lambda x, a=a: pose(a, x), lambda x, b=b: pose(b, x),
                         (th - step, th, th + step))
        out[(a, b)] = (e, t, d)
    cheeks = bd.Compound(children=_proxy_cheeks())
    for g in names:
        e, t = exact_min(bd.Compound(children=list(groups[g])), cheeks, lambda x, g=g: pose(g, x),
                         kin.pose_crank, (0.0, 90.0, 180.0, 270.0))
        out[(g, "crank_cheeks")] = (e, t, e)
    fits = {}
    for k, pin in pins.items():
        bush = [p for p in groups[f"artrod{k}"] if p.label.endswith("knuckle_bushing")][0]
        fits[k] = exact_min(pin, bush, kin.pose_master, lambda x, k=k: kin.pose_art_rod(x, k),
                            (0.0, 137.0, 293.0, 555.0))
    return out, fits


if __name__ == "__main__":
    import sys
    import time
    t0 = time.time()
    parts = build()
    bad = [p.label for p in parts if not geo.sound(p)]
    print(f"{len(parts)} leaves, unsound: {bad}  ({time.time() - t0:.0f}s)")
    if len(sys.argv) > 1:
        res, fits = sweep(float(sys.argv[1]), verbose=True)
        print("knuckle pin k in bushing k (designed running fit):",
              ", ".join(f"{k}: {e:.3f}" for k, (e, t) in sorted(fits.items())))
        print("\npair                         brep_min  @theta  screen_min   (screen capped at 12)")
        for (a, b), (e, th, d) in sorted(res.items(), key=lambda kv: kv[1][2]):
            es = f"{e:8.2f}" if e is not None else "     >12"
            print(f"{a:>10} x {b:<14} {es}  {th:6.0f}  {d:8.2f}")
        print(f"sweep {time.time() - t0:.0f}s")
