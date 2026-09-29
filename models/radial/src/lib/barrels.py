"""Barrels: nine forged Cr-Mo steel cylinder barrels, dark-grey enamel, deep fins,
hold-down flange with twelve castellated nuts + washers, safety-wired in pairs.

Authored ONCE for cylinder 1 in its local frame (h = +Z, y = +Y, t = +X) and
placed on cylinders 2..9 with `geo.on_cylinder`; cylinder 1's barrel is the
museum section (REAR half above h 306 removed: `section_cut()`, a subset of
`geo.section_cutter()`); all of its hold-down hardware stays.

Stations along h (see spec):
  205 .. 282   skirt, OD 158, inside the crankcase bore (O162); below h ~220
               its sides are machined flat to the cylinder's 40 deg wedge
  282 .. 294   hold-down flange, OD 188, 12 stud holes on PCD 170
  294 .. 305   neck (OD 153) where the nuts, washers and safety wire live
  309 .. 381   13 deep fins at 6 mm pitch: root 1.6 -> tip 1.1, rounded tips,
               filleted roots; tip R 108.4 -> 117.5 (see fin_tip_r)
  384 .. 402   threaded spigot, OD 159 (the head is screwed/shrunk on from h 385)
Bore O146 open through, lead chamfer at the skirt.

INTERFACE (crankcase builder owns the studs): studs are clocked at
15 + 30 j deg in the cylinder's (t, y) plane, measured from +t toward +y, and
must END at or below h = 301.5 (the safety wire crosses the castellation
slots at h 303.2, above the stud tip).
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import geo, palette as P, spec as S
from lib.fasteners import _wrench_head, pitch

MATERIALS = ("enamel_grey", "fastener", "safety_wire", "section_red")

# ---------------------------------------------------------------------------
# Numbers (cylinder-local, mm)
# ---------------------------------------------------------------------------
R_BORE = S.BORE / 2.0                  # 73
R_SKIRT = 158.0 / 2.0                  # 79
R_FLANGE = 188.0 / 2.0                 # 94 (neighbour flanges clear by ~16 mm)
R_NECK = 76.5
R_WALL = 80.0                          # fin root radius
R_SPIGOT = 79.5
FIN_PITCH = 4.5                        # close-pitched: the barrel reads as one finned mass
FIN_H0 = 309.0                         # first fin centre
FIN_N = 17                             # 309 .. 381 (top fin 3.2 below the head skirt)
FIN_ROOT_HALF = 0.75                   # 1.5 at the root
FIN_TIP_HALF = 0.5                     # 1.0 at the tip
FIN_ROOT_FILLET = 0.7
FIN_TIP_FILLET = 0.45
H_NECK_TOP = 304.4
H_WALL = 306.2

STUD_D = 9.5
STUD_ANGLES = [15.0 + 30.0 * j for j in range(S.HOLD_DOWN_STUDS)]
R_PCD = S.HOLD_DOWN_PCD / 2.0          # 85

WASHER_T = 1.2
WASHER_OD = 15.0
NUT_AF = 14.0
NUT_HEX_H = 7.0
NUT_H = 10.0
NUT_CROWN_R = 6.2
SLOT_W = 2.4
SLOT_DEPTH = 3.0
# the studs are modelled at their pitch diameter (fasteners.stud): clear it by 0.2 radially
NUT_BORE_D = STUD_D - 0.6495 * pitch(STUD_D) + 0.4
H_NUT_BASE = S.H_FLANGE_TOP + WASHER_T           # 295.2
H_WIRE = H_NUT_BASE + NUT_H - SLOT_DEPTH + 1.0    # 303.2

WIRE_D = 0.8
WIRE_TWIST_R = 0.36                    # strand centre offset from the pair axis (strands bite 0.04: one fused solid)
WIRE_LAY = 4.0                         # one full twist per 4 mm


FIN_TIP_R_MAX = 126.0                 # tip cap: just inside the head fins above (R 118..128)
FIN_WEDGE_MARGIN = 1.8                # inside the cylinder wedge (itself 1 mm inside the bisector)


def fin_tip_r(h: float) -> float:
    """Deep fins (depth 28 -> 37.5 mm, as deep as the head's): the tip grows with
    the room between neighbours (wedge) until the pushrod tubes cap it."""
    b = math.radians(geo.WEDGE_HALF_ANGLE)
    wedge_t = (h * math.sin(b) - geo.WEDGE_CLEARANCE / 2.0) / math.cos(b)
    # the rear ignition lead climbs past the fin tips on the -t side: keep >= 3 mm
    # (measured against ignition:lead_<k>R; a straight line under its path)
    lead_lane = 118.9 + 0.26 * (h - 336.0)
    return min(wedge_t - FIN_WEDGE_MARGIN, lead_lane, FIN_TIP_R_MAX)


# ---------------------------------------------------------------------------
# Barrel
# ---------------------------------------------------------------------------
def _barrel_profile():
    """Closed (r, h) outline, returned with the vertex indices to fillet."""
    pts = []
    root, tip = [], []
    # bore side, bottom to top is the closing edge; start at the skirt bottom
    # lead chamfer into the bore: kept to 0.4 so the wedge trim (below h ~220
    # the skirt's sides are machined flat to its 40 deg wedge) never breaks into it
    pts += [(R_BORE + 0.4, S.H_BARREL_SKIRT),
            (R_SKIRT - 0.8, S.H_BARREL_SKIRT),
            (R_SKIRT, S.H_BARREL_SKIRT + 0.8),
            (R_SKIRT, S.H_PAD)]                           # skirt meets flange underside
    root.append(len(pts) - 1)
    pts += [(R_FLANGE - 0.8, S.H_PAD),
            (R_FLANGE, S.H_PAD + 0.8),
            (R_FLANGE, S.H_FLANGE_TOP - 0.8),
            (R_FLANGE - 0.8, S.H_FLANGE_TOP),
            (R_NECK, S.H_FLANGE_TOP)]
    root.append(len(pts) - 1)
    pts += [(R_NECK, H_NECK_TOP)]
    root.append(len(pts) - 1)
    pts += [(R_WALL, H_WALL)]
    root.append(len(pts) - 1)
    for i in range(FIN_N):
        h = FIN_H0 + FIN_PITCH * i
        rt = fin_tip_r(h)
        pts.append((R_WALL, h - FIN_ROOT_HALF)); root.append(len(pts) - 1)
        pts.append((rt, h - FIN_TIP_HALF)); tip.append(len(pts) - 1)
        pts.append((rt, h + FIN_TIP_HALF)); tip.append(len(pts) - 1)
        pts.append((R_WALL, h + FIN_ROOT_HALF)); root.append(len(pts) - 1)
    h_last = FIN_H0 + FIN_PITCH * (FIN_N - 1) + FIN_ROOT_HALF
    # plain band, then the threaded spigot (V grooves, hidden by the head skirt)
    pts += [(R_WALL, h_last + 1.6), (R_SPIGOT, h_last + 2.1)]
    h = 386.0
    while h + 2.0 <= 400.0:
        pts += [(R_SPIGOT, h), (R_SPIGOT - 0.7, h + 0.7), (R_SPIGOT, h + 1.4)]
        h += 2.0
    pts += [(R_SPIGOT, S.H_BORE_TOP - 1.0),
            (R_SPIGOT - 1.0, S.H_BORE_TOP),
            (R_BORE + 0.6, S.H_BORE_TOP),
            (R_BORE, S.H_BORE_TOP - 0.6)]
    pts += [(R_BORE, S.H_BARREL_SKIRT + 0.4)]
    return pts, root, tip


def _fillet_profile_face(face, pts, idx, r):
    targets = []
    for i in idx:
        x, z = pts[i]
        for v in face.vertices():
            if abs(v.X - x) < 1e-6 and abs(v.Z - z) < 1e-6:
                targets.append(v)
                break
    return face.fillet_2d(r, targets) if targets else face


def build_barrel_proto():
    pts, root, tip = _barrel_profile()
    wire = bd.Wire.make_polygon([bd.Vector(x, 0, z) for x, z in pts], close=True)
    face = bd.Face(wire)
    root_big = [i for i in root if pts[i][1] < 300.0]
    root_fin = [i for i in root if pts[i][1] >= 300.0]
    face = _fillet_profile_face(face, pts, root_big, 1.6)
    face = _fillet_profile_face(face, pts, root_fin, FIN_ROOT_FILLET)
    face = _fillet_profile_face(face, pts, tip, FIN_TIP_FILLET)
    body = bd.revolve(face, axis=bd.Axis.Z, revolution_arc=360.0)
    body = bd.Solid(body.solids()[0].wrapped) if not isinstance(body, bd.Solid) else body
    # stud holes (one multi-tool cut; the tools are disjoint)
    holes = [bd.Pos(R_PCD * math.cos(math.radians(a)), R_PCD * math.sin(math.radians(a)), S.H_PAD - 1.0)
             * bd.Cylinder(10.4 / 2.0, S.H_FLANGE_TOP - S.H_PAD + 2.0,
                           align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
             for a in STUD_ANGLES]
    body = body.cut(*holes)
    # the skirt's sides are machined flat to the cylinder's wedge (geo.wedge_trim):
    # neighbouring skirts (and pistons at BDC) can never meet
    body = geo.wedge_trim(_one_solid(body))
    return _one_solid(body)


def _one_solid(shape):
    sols = shape.solids()
    if len(sols) != 1:
        raise RuntimeError(f"expected one solid, got {len(sols)}")
    return sols[0]


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------
def _rev(points):
    prof = bd.Face(bd.Wire.make_polygon([bd.Vector(x, 0, z) for x, z in points], close=True))
    return bd.revolve(prof, axis=bd.Axis.Z)


def build_washer_proto():
    ri, ro, t, b = 10.2 / 2.0, WASHER_OD / 2.0, WASHER_T, 0.15
    return _one_solid(_rev([(ri, 0), (ro - b, 0), (ro, b), (ro, t - b), (ro - b, t), (ri + b, t), (ri, t - b)]))


def build_nut_proto():
    """Castellated hex nut (AN310 style, 3/8"), bearing face at z = 0, one slot
    axis along local +X (the wire direction)."""
    hexb = _wrench_head(NUT_AF, 0.0, NUT_HEX_H, chamfer_bottom=True, rotation=30.0)
    crown = _rev([(0, NUT_HEX_H - 0.5), (NUT_CROWN_R, NUT_HEX_H - 0.5),
                  (NUT_CROWN_R, NUT_H - 0.5), (NUT_CROWN_R - 0.5, NUT_H), (0, NUT_H)])
    nut = hexb.fuse(crown)
    slots = bd.Sketch() + [bd.Rot(0, 0, a) * bd.Rectangle(2 * NUT_CROWN_R + 6, SLOT_W) for a in (0, 60, 120)]
    slot_tool = bd.Pos(0, 0, NUT_H - SLOT_DEPTH) * bd.extrude(slots, amount=SLOT_DEPTH + 1.0)
    bore = bd.Pos(0, 0, -1) * bd.Cylinder(NUT_BORE_D / 2.0, NUT_H + 2,
                                          align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    nut = nut.cut(slot_tool, bore)
    return _one_solid(nut.clean())


def _sweep_circle(path, d):
    p0 = path @ 0.0
    t0 = path % 0.0
    prof = bd.Plane(origin=p0, z_dir=t0) * bd.Circle(d / 2.0)
    return _one_solid(bd.sweep(prof, path=path, is_frenet=False))


def _twisted_pair(length):
    """Two Ø0.8 strands twisted about local +Z from z = 0 to `length`."""
    out = []
    for phase in (0.0, 180.0):
        hx = bd.Helix(WIRE_LAY, length, WIRE_TWIST_R)
        hx = bd.Rot(0, 0, phase) * hx
        p0, t0 = hx @ 0.0, hx % 0.0
        prof = bd.Plane(origin=p0, z_dir=t0) * bd.Circle(WIRE_D / 2.0)
        out.append(_one_solid(bd.sweep(prof, path=hx, is_frenet=True)))
    return out


def _v(a):
    return bd.Vector(*a)


def pair_geometry():
    """Stud pair (A at 15 deg, B at 45 deg) in cylinder-1 local frame: nut
    placements and the safety wire (a loop around A's crown, twisted to B,
    through B's slot, twisted pigtail beyond)."""
    a, b = math.radians(STUD_ANGLES[0]), math.radians(STUD_ANGLES[1])
    A = bd.Vector(R_PCD * math.cos(a), R_PCD * math.sin(a), H_WIRE)
    B = bd.Vector(R_PCD * math.cos(b), R_PCD * math.sin(b), H_WIRE)
    d = (B - A).normalized()
    z = bd.Vector(0, 0, 1)
    s = z.cross(d)                     # loop side: tension tightens A (clockwise from above)
    # twisted section: from just outside A's crown to 6 mm past B's crown
    p0 = A + d * (NUT_CROWN_R + 1.4)
    p1 = B + d * (NUT_CROWN_R + 6.0)
    L = (p1 - p0).length
    pair = _twisted_pair(L)
    frame = bd.Plane(origin=p0, x_dir=s, z_dir=d)
    pair = [frame * w for w in pair]
    # loop: leaves the pair's start strands (at p0 +- 0.42 s), runs back through
    # A's slot, round the crown on the +s side and back
    rl = NUT_CROWN_R + 0.9
    pts = [p0 - s * WIRE_TWIST_R, A + d * 3.0 - s * 0.25, A, A - d * 3.0]
    for ang in (15, 45, 75, 105, 135, 165):
        r = math.radians(ang)
        pts.append(A + (-d) * (rl * math.cos(r)) + s * (rl * math.sin(r)))
    pts.append(p0 + s * WIRE_TWIST_R)
    loop = _sweep_circle(bd.Spline(*pts), WIRE_D)
    wire = _one_solid(pair[0].fuse(pair[1], loop).clean())
    return A, B, d, wire


# ---------------------------------------------------------------------------
# Museum section (cylinder 1, REAR half)
# ---------------------------------------------------------------------------
H_SECTION = 306.0     # machined step: above the nuts and wire (305.2), below the first fin root


def section_cut():
    """geo.section_cutter() limited to h > H_SECTION: a strict SUBSET of the
    museum-section region. geo's r > 300 boundary is a cylinder about the crank
    axis, which would bite curved scallops out of the rear flange corners and
    the rear nuts; stopping on a flat step at h 306 keeps the flange, all twelve
    nuts and the wire whole, and leaves two deliberate faces: the fin comb on
    y = 0 and a half-annulus step at h 306."""
    keep_low = bd.Pos(0, 0, H_SECTION) * bd.Box(4000, 4000, 4000, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return geo.section_cutter() & keep_low


def section_skin_band():
    """geo.SKIN_T-thick layer of the removed region against both of our cut faces
    (the y = 0 comb face and the h = H_SECTION step): the equivalent of
    geo.cut_with_skin for this limited cut. Intersected with the ORIGINAL barrel
    it covers the cut faces exactly and never overlaps the kept part."""
    t = getattr(geo, "SKIN_T", 0.4)
    big = 4000.0
    comb = bd.Box(big, t, big, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.CENTER))
    step = bd.Pos(0, 0, H_SECTION) * bd.Box(big, big, t, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return section_cut() & comb.fuse(step)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def _style(shape, label, color):
    shape.label = label
    shape.color = color
    return shape


def _stud_seat(ang_deg, h):
    r = math.radians(ang_deg)
    return bd.Vector(R_PCD * math.cos(r), R_PCD * math.sin(r), h)


def _local_to_engine(k, p):
    """Cylinder-1 local point (x=t, y, z=h) -> engine point on cylinder k."""
    return S.cyl_point(k, p.Z, p.Y, p.X)


def build():
    barrel = build_barrel_proto()
    nut0, washer0 = build_nut_proto(), build_washer_proto()
    A, B, d, wire0 = pair_geometry()

    # hardware for one pair, cylinder-1 frame, then rotated about the cylinder axis
    xd = (d.X, d.Y, d.Z)
    pair_parts = []   # (kind, index_in_pair, shape, seat_point)
    for i, (C, ang) in enumerate(((A, STUD_ANGLES[0]), (B, STUD_ANGLES[1]))):
        seat = _stud_seat(ang, S.H_FLANGE_TOP)
        pl_w = bd.Plane(origin=seat, x_dir=xd, z_dir=(0, 0, 1))
        pl_n = bd.Plane(origin=_stud_seat(ang, H_NUT_BASE), x_dir=xd, z_dir=(0, 0, 1))
        pair_parts.append(("washer", i, pl_w * washer0, seat))
        pair_parts.append(("nut", i, pl_n * nut0, seat))

    protos = []   # (label_stem, shape_in_cyl1_frame, seat_point_local, color)
    for p in range(6):
        rot = bd.Rot(0, 0, 60.0 * p)
        for kind, i, shp, seat in pair_parts:
            nn = 2 * p + i + 1
            seat_r = rot * bd.Pos(seat) * bd.Vertex(0, 0, 0)
            protos.append((f"hold_down_{kind}", nn, rot * shp, seat_r.center(), P.FASTENER))
        mid = rot * bd.Pos((A + B) * 0.5) * bd.Vertex(0, 0, 0)
        protos.append(("safety_wire", p + 1, rot * wire0, mid.center(), P.SAFETY_WIRE))

    parts = []
    section = section_cut()
    for k in range(1, S.N_CYL + 1):
        if k == geo.SECTION_CYL:
            cut = geo.cut(barrel, section)
            parts.append(_style(_one_solid(cut), f"barrels:barrel_{k}", P.ENAMEL_GREY))
            skin = _one_solid(barrel & section_skin_band())
            parts.append(_style(skin, f"barrels:section_skin_{k}", P.SECTION_RED))
        else:
            parts.append(_style(geo.on_cylinder(barrel, k), f"barrels:barrel_{k}", P.ENAMEL_GREY))
        for stem, nn, shp, seat, color in protos:
            # the section stops at H_SECTION, above every nut and wire: none is
            # removed (geo.in_section flags the rear flange corners only because
            # its r > 300 boundary is a cylinder about the crank axis)
            if seat.Z > H_SECTION and geo.in_section(_local_to_engine(k, seat)):
                continue
            placed = shp.moved(bd.Location()) if k == 1 else geo.on_cylinder(shp, k)
            parts.append(_style(placed, f"barrels:{stem}_{k}_{nn:02d}", color))
    return parts


if __name__ == "__main__":
    import time
    t0 = time.time()
    ps = build()
    print(len(ps), "parts", f"{time.time() - t0:.1f}s")
    # rigid copies share geometry: check each distinct TShape once
    seen, bad = {}, []
    for p in ps:
        for sol in (p.solids() or [p]):
            key = sol.wrapped.TShape().__hash__() if hasattr(sol.wrapped.TShape(), "__hash__") else id(sol)
            if key in seen:
                continue
            seen[key] = p.label
            if not geo.sound(sol):
                bad.append(p.label)
    print(len(seen), "distinct solids checked; unsound:", bad, f"{time.time() - t0:.1f}s")
