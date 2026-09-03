"""Cylinder heads (one wide cast-aluminium casting per bank, both rows).

Interior (UNCHANGED, every moving part depends on it): pent-roof chambers,
seat cones, throats, ports, spring pockets, follower pockets, HLA bores, cam
journal bores + lobe troughs, deck plane h = 226, top plane h = 358, faces at
CAM_FRONT_X / HEAD_REAR_X and m = +/- 130.

Exterior: cast walls with a 3 deg drafted recess between the raised landings
that other systems bolt to, the parting bead, spark-plug wells + plugs, head
bolts, coolant outlets, a core plug, cam-seal counterbores, rear cam blanks
and lifting-eye bosses.  Machined surfaces are carried as thin separate
solids (`head_face:<bank>_<name>`) so the body can stay cast-coloured.

WHY THE LANDINGS ARE WHERE THEY ARE.  Both faces are interface planes owned by
other builders and there is very little free wall left:
  * outer face m = -130: `exhaust.py` seats an 84 x 62 flange per cylinder
    (h 247..309) with M8 studs at h = 255 / 301, and `ancillaries.py` seats the
    coolant rail's 60 x 76 pads (h 306..382) at every cylinder x.  The exhaust
    band therefore runs the full length (a per-cylinder pad narrow enough to
    leave a gap at the 74 mm bore pitch would have 1 mm of metal outside its
    stud holes); it is fluted between cylinders instead.
  * inner face m = +130: intake port exits at h = 294, plus the plenum rail.
The cast recess is what is LEFT between those landings, drafted 3 deg either
side of the parting line.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import block, fasteners as F, geo, kin, palette as P, spec as S
from lib.castings import fuse_all
from lib.valvetrain import CUP_FLOOR_Z
from lib.geo import sound as is_sound

HEAD_REAR_X = -300.0
HEAD_FRONT_X = S.CAM_FRONT_X
CAM_SADDLE_X = [290.0, 148.0, 0.0, -148.0, -290.0]
CAM_SADDLE_W = 22.0
CAM_TROUGH_D = 2 * (S.CAM_BASE_R + 5.6) + 2 * 5.0     # clears the tallest lobe with margin
SPRING_POCKET_D = S.SPRING_OD + 4.5          # 34.5: clears the Ø33 spring-seat cup

TOP_H = S.DECK_H + S.HEAD_H                  # 358, head top / cam centreline plane
M_FACE = S.HEAD_M_HALF                       # 130, both interface planes

# --- exterior casting form (bank coordinates; |m| unless signed) ------------
PARTING_H = 310.0                # cast parting line; the outer face carries its bead
WALL_M = 127.0                   # cast wall at the parting line (3 mm inside the face)
WALL_DRAFT = 3.0                 # deg, either side of the parting line
DECK_FLANGE_H = 234.0            # deck flange band top (full width to the block joint)
EX_BAND_H = (248.0, 308.0)       # exhaust flange landing (studs at h 255 / 301)
RAIL_LAND_H = (315.0, 356.0)     # coolant-rail pad landing (ancillaries: 60 wide at cyl x)
RAIL_LAND_W = 68.0
IN_BAND_H = (276.0, 312.0)       # intake port landing (Ø21 exits at h 294)
PLENUM_RAIL_H = (328.0, 346.0)   # plenum flange landing
PLENUM_BOLT_H = 337.0
TOP_BAND_H = (350.0, 359.0)      # cam-cover rail edge, both faces
FLUTE_W, FLUTE_M = 9.0, 127.6    # cast flutes between cylinders, cut into the bands
BEAD_M = 128.4                   # parting bead crest


def wall_m(h: float) -> float:
    """|m| of the drafted cast wall at height h."""
    return WALL_M - math.tan(math.radians(WALL_DRAFT)) * abs(h - PARTING_H)


def head_outline(bank: int):
    m0, m1 = -S.HEAD_M_HALF, S.HEAD_M_HALF
    h0, h1 = S.DECK_H, S.DECK_H + S.HEAD_H
    pts = [S.bank_point(bank, 0, m, h)[1:] for m, h in ((m0, h0), (m1, h0), (m1, h1), (m0, h1))]
    # ensure CCW in (y, z)
    area = 0.0
    for i in range(4):
        y0, z0 = pts[i]
        y1, z1 = pts[(i + 1) % 4]
        area += y0 * z1 - y1 * z0
    return pts if area > 0 else list(reversed(pts))


def bank_cylinders(bank: int):
    return [c for c in S.CYLINDERS if c.bank == bank]


def mid_stations(bank: int):
    """x midway between adjacent cylinders of the bank, plus one 37 mm beyond
    each end cylinder — the head-bolt / flute grid."""
    xs = sorted((c.x for c in bank_cylinders(bank)), reverse=True)
    mids = [(xs[i] + xs[i + 1]) / 2.0 for i in range(len(xs) - 1)]
    return [xs[0] + 37.0] + mids + [xs[-1] - 37.0]


def _mh_prism(bank: int, pts_mh, x0: float, x1: float, sign: float = 1.0):
    """Extrude a closed (|m|, h) polygon along X on the `sign` side of the bank."""
    pts = [S.bank_point(bank, 0, sign * m, h)[1:] for m, h in pts_mh]
    area = 0.0
    for i in range(len(pts)):
        y0, z0 = pts[i]
        y1, z1 = pts[(i + 1) % len(pts)]
        area += y0 * z1 - y1 * z0
    if area < 0:
        pts = list(reversed(pts))
    return geo.prism_yz(pts, x0, x1)


def _face_dir(bank: int, sign: float):
    mm = S.bank_m(bank)
    return (0.0, sign * mm[1], sign * mm[2])


def face_block(bank: int, sign: float, xc: float, hc: float, w: float, hh: float,
               r: float = 0.0, m0: float = 116.0, m1: float = 136.0):
    """A block standing on the `sign` face, |m| from m0 out to m1, centred on
    (xc, hc), w along X and hh up the bank; r rounds its plan corners."""
    r = min(r, 0.49 * min(w, hh))
    sk = bd.RectangleRounded(w, hh, r) if r > 0 else bd.Rectangle(w, hh)
    proto = bd.extrude(bd.Plane.XY * sk, amount=m1 - m0)
    return geo.locate(proto, S.bank_point(bank, xc, sign * m0, hc),
                      _face_dir(bank, sign), (1.0, 0.0, 0.0))


def _band(bank: int, sign: float, h0: float, h1: float, m0: float = 116.0):
    """Full-length landing band between two heights."""
    return face_block(bank, sign, (HEAD_REAR_X + HEAD_FRONT_X) / 2.0, (h0 + h1) / 2.0,
                      HEAD_FRONT_X - HEAD_REAR_X + 8.0, h1 - h0, 0.0, m0)


def face_recess(bank: int, sign: float):
    """The material to take OFF one face: the drafted cast wall, minus the
    landings other systems bolt to, plus the flutes between cylinders."""
    poly = [(134.0, DECK_FLANGE_H), (134.0, TOP_H + 4.0),
            (wall_m(TOP_H + 4.0), TOP_H + 4.0),
            (wall_m(PARTING_H), PARTING_H), (wall_m(240.0), 240.0)]
    tool = _mh_prism(bank, poly, HEAD_REAR_X - 2.0, HEAD_FRONT_X + 2.0, sign)
    lands = [_band(bank, sign, *TOP_BAND_H)]
    if sign < 0:
        lands.append(_band(bank, sign, *EX_BAND_H))
        for c in bank_cylinders(bank):
            lands.append(face_block(bank, sign, c.x, sum(RAIL_LAND_H) / 2.0, RAIL_LAND_W,
                                    RAIL_LAND_H[1] - RAIL_LAND_H[0], 8.0))
    else:
        lands.append(_band(bank, sign, *IN_BAND_H))
        lands.append(_band(bank, sign, *PLENUM_RAIL_H))
    tool = tool - lands
    flutes = []
    bands = (EX_BAND_H,) if sign < 0 else (IN_BAND_H, PLENUM_RAIL_H)
    for x in mid_stations(bank):
        for h0, h1 in bands:
            flutes.append(face_block(bank, sign, x, (h0 + h1) / 2.0, FLUTE_W,
                                     h1 - h0 + 4.0, FLUTE_W / 2.0, FLUTE_M))
    return geo.fuse_fuzzy([tool] + flutes)


def parting_bead(bank: int):
    """The flash line where the mould halves met, on the outer face."""
    poly = [(120.0, PARTING_H - 2.6), (WALL_M - 1.0, PARTING_H - 2.6),
            (BEAD_M, PARTING_H), (WALL_M - 1.0, PARTING_H + 2.6), (120.0, PARTING_H + 2.6)]
    return _mh_prism(bank, poly, HEAD_REAR_X, HEAD_FRONT_X, -1.0)


# --- service features ------------------------------------------------------
# Head bolts.  The pattern is the BLOCK's — `block.HEAD_BOLT_M` (m = +/-90 and
# +/-112) at `block.deck_stations()` — imported rather than repeated so the two
# castings cannot drift.  Only the seven MIDPOINT stations are carried through
# the head: the block's two end stations (27 mm beyond the end cylinder) land
# inside the end cylinder's own port band in the head, where a through-hole
# would break into the intake and exhaust ports (see the report).
# The well is a cast spotface that opens at h = 316, just UNDER the follower
# pockets: above that the bolt is reached through the open cam gallery (which
# the cover encloses), as on a real DOHC head, and the top face stays unbroken.
HEAD_BOLT_M = block.HEAD_BOLT_M
HEAD_BOLT_D = 12.0
HEAD_BOLT_LEN = 150.0
WELL_D = 20.0                    # M12 head is 18 across; the m 90/112 pair is 22 apart
WELL_TOP_H = 316.0               # the spotface mouth, just under the follower pockets
WELL_FLOOR_H = 298.0
SHANK_HOLE_D = 13.4
EX_STUD_TAP_D = 7.0                       # M8 studs from exhaust.py
COVER_BOLT_M = 122.5                      # mirrors covers.BOLT_M / BOLT_PITCH
COVER_BOLT_PITCH = 55.0
COVER_TAP_D = 5.0
PLENUM_TAP_D = 5.0
SEAL_CB_D, SEAL_CB_T = 50.0, 6.0          # front cam-seal counterbores
COOLANT_MH = ((-104.0, 340.0), (-104.0, 270.0))   # front face, clear of the stud rows
COOLANT_BOSS_D, COOLANT_BORE_D, COOLANT_PROUD = 30.0, 18.0, 9.0
COOLANT_BORE_T = 18.0
CORE_PLUG_MH = (-40.0, 292.0)             # rear face
CORE_PLUG_D = 35.0
EYE_MH = (-112.0, S.DECK_H + 74.0)        # ancillaries seats its lifting eyes here
EYE_BOSS_D, EYE_PROUD, EYE_TAP_D = 34.0, 7.0, 9.0
CAM_BLANK_D, CAM_BLANK_T = 40.0, 6.0      # rear cam-bore blanking bosses
PLUG_BORE_D = S.PLUG_BORE_D               # 16


def plug_bore(c: S.Cylinder):
    b, t = S.plug_axis(c.number)
    d = (t[0] - b[0], t[1] - b[1], t[2] - b[2])
    n = math.sqrt(sum(v * v for v in d))
    d = tuple(v / n for v in d)
    lo = tuple(b[i] - 3.0 * d[i] for i in range(3))
    hi = tuple(b[i] + 130.0 * d[i] for i in range(3))
    return geo.cyl_along(lo, hi, PLUG_BORE_D)


def head_bolt_seats(bank: int):
    """(x, m) of every head-bolt well on this bank."""
    out = []
    for x in block.deck_stations(bank)[1:-1]:
        for m in HEAD_BOLT_M:
            out.append((x, m))
    return out


def head_bolt_cuts(bank: int):
    out = []
    for x, m in head_bolt_seats(bank):
        top = S.bank_point(bank, x, m, WELL_TOP_H)
        floor = S.bank_point(bank, x, m, WELL_FLOOR_H)
        deck = S.bank_point(bank, x, m, S.DECK_H - 4.0)
        out.append(geo.cyl_along(floor, top, WELL_D))
        out.append(geo.cyl_along(deck, floor, SHANK_HOLE_D))
    return out


def end_bosses(bank: int):
    """Cast bosses that stand PROUD of the front and rear faces."""
    out = []
    for x_face, xdir in ((HEAD_FRONT_X, 1.0), (HEAD_REAR_X, -1.0)):
        p = S.bank_point(bank, x_face, EYE_MH[0], EYE_MH[1])
        out.append(geo.cyl_along(p, (p[0] + xdir * EYE_PROUD, p[1], p[2]), EYE_BOSS_D))
    for m, h in COOLANT_MH:
        p = S.bank_point(bank, HEAD_FRONT_X, m, h)
        out.append(geo.cyl_along(p, (p[0] + COOLANT_PROUD, p[1], p[2]), COOLANT_BOSS_D))
    # rear cam-bore blanking bosses: half discs under the top plane
    for kind in ("intake", "exhaust"):
        yc, zc = S.bank_point(bank, 0, S.CAM_M[kind], S.CAM_H)[1:]
        disc = geo.cyl_x(HEAD_REAR_X - CAM_BLANK_T, HEAD_REAR_X + 1.0, CAM_BLANK_D, yc, zc)
        keep = _mh_prism(bank, [(-90.0, 300.0), (90.0, 300.0), (90.0, TOP_H), (-90.0, TOP_H)],
                         HEAD_REAR_X - CAM_BLANK_T - 2.0, HEAD_REAR_X + 2.0)
        out.append(disc & keep)
    return out


def feature_cuts(bank: int):
    """Threaded holes, counterbores and service bores. Mutually disjoint."""
    out = []
    up = S.bank_up(bank)
    for c in bank_cylinders(bank):
        # M8 exhaust-stud taps (exhaust.py's four studs per cylinder)
        for dx in (-30.0, 30.0):
            for dh in (-23.0, 23.0):
                p = S.bank_point(bank, c.x + dx, -M_FACE - 2.0, S.EXHAUST_EXIT_H + dh)
                q = S.bank_point(bank, c.x + dx, -M_FACE + 22.0, S.EXHAUST_EXIT_H + dh)
                out.append(geo.cyl_along(p, q, EX_STUD_TAP_D))
    # M6 plenum row on the inner face, 55 mm pitch about the head's mid-station
    x_mid = (HEAD_REAR_X + HEAD_FRONT_X) / 2.0
    for k in range(11):
        x = x_mid + COVER_BOLT_PITCH * (k - 5)
        p = S.bank_point(bank, x, M_FACE + 2.0, PLENUM_BOLT_H)
        q = S.bank_point(bank, x, M_FACE - 16.0, PLENUM_BOLT_H)
        out.append(geo.cyl_along(p, q, PLENUM_TAP_D))
        # M6 cam-cover rail taps, both sides of the top face
        for m in (COVER_BOLT_M, -COVER_BOLT_M):
            p = S.bank_point(bank, x, m, TOP_H + 2.0)
            q = S.bank_point(bank, x, m, TOP_H - 16.0)
            out.append(geo.cyl_along(p, q, COVER_TAP_D))
    # front cam-seal counterbores
    for kind in ("intake", "exhaust"):
        yc, zc = S.bank_point(bank, 0, S.CAM_M[kind], S.CAM_H)[1:]
        out.append(geo.cyl_x(HEAD_FRONT_X - SEAL_CB_T, HEAD_FRONT_X + 2.0, SEAL_CB_D, yc, zc))
    # coolant outlet bores, lifting-eye taps, rear core plug
    for m, h in COOLANT_MH:
        p = S.bank_point(bank, HEAD_FRONT_X + COOLANT_PROUD + 2.0, m, h)
        q = S.bank_point(bank, HEAD_FRONT_X - COOLANT_BORE_T, m, h)
        out.append(geo.cyl_along(p, q, COOLANT_BORE_D))
    for x_face, xdir in ((HEAD_FRONT_X, 1.0), (HEAD_REAR_X, -1.0)):
        p = S.bank_point(bank, x_face + xdir * (EYE_PROUD + 2.0), EYE_MH[0], EYE_MH[1])
        q = S.bank_point(bank, x_face - xdir * 28.0, EYE_MH[0], EYE_MH[1])
        out.append(geo.cyl_along(p, q, EYE_TAP_D))
    p = S.bank_point(bank, HEAD_REAR_X - 2.0, *CORE_PLUG_MH)
    q = S.bank_point(bank, HEAD_REAR_X + 12.0, *CORE_PLUG_MH)
    out.append(geo.cyl_along(p, q, CORE_PLUG_D))
    return out


def chamber(c: S.Cylinder):
    bore = geo.cyl_along(c.point(150.0), c.point(300.0), S.BORE)
    pocket = bore
    for kind in ("intake", "exhaust"):
        g = kin.valve_geom(c.number, kind, 0)
        below = bd.Box(400, 400, 200, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX))
        below = geo.locate(below, (c.x, g.ridge[0], g.ridge[1]), g.axis3, (1, 0, 0))
        pocket = pocket & below
    return pocket


def valve_cuts(g: kin.ValveGeom):
    """Seat throat, port, spring pocket, follower pocket, HLA bore for one valve."""
    out = []
    d_head = S.INTAKE_HEAD_D if g.kind == "intake" else S.EXHAUST_HEAD_D
    seat3 = g.point3(g.seat)
    up = g.axis3
    # valve seat: a cone a hair bigger than the valve's own seat/back profile
    r = d_head / 2.0
    seat_cone = bd.Cone(r + 0.6, r - 6.6, 5.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((0, 0, -0.6)))
    out.append(geo.locate(seat_cone, seat3, up, (1, 0, 0)))
    # throat/port: along the valve axis 24 mm, then a straight run out of the head
    out.append(geo.cyl_along(g.point3((g.seat[0] + 4 * g.v[0], g.seat[1] + 4 * g.v[1])),
                             g.point3((g.seat[0] + 30 * g.v[0], g.seat[1] + 30 * g.v[1])), d_head - 8.0))
    exit_m = S.HEAD_M_HALF + 5 if g.kind == "intake" else -(S.HEAD_M_HALF + 5)
    exit_h = S.DECK_H + (68.0 if g.kind == "intake" else 52.0)
    c = S.CYLINDERS[g.cyl - 1]
    exit3 = S.bank_point(c.bank, g.x, exit_m, exit_h)
    # the port is narrower than the throat and starts well inside it, so the two
    # cylinders cross at an angle instead of running tangent (a boolean killer)
    elbow3 = g.point3((g.seat[0] + 16 * g.v[0], g.seat[1] + 16 * g.v[1]))
    out.append(geo.cyl_along(elbow3, exit3, d_head - 11.0))
    # spring pocket from the spring seat up through the top
    s_pocket = CUP_FLOOR_Z - 2.5                    # the cup's underside
    p0 = g.point3((g.seat[0] + s_pocket * g.v[0], g.seat[1] + s_pocket * g.v[1]))
    # stem bore + guide bore between the throat and the spring pocket
    out.append(geo.cyl_along(g.point3((g.seat[0] + 18.0 * g.v[0], g.seat[1] + 18.0 * g.v[1])),
                             g.point3((g.seat[0] + (s_pocket + 1.0) * g.v[0], g.seat[1] + (s_pocket + 1.0) * g.v[1])), S.VALVE_STEM_D + 0.8))
    s_guide = CUP_FLOOR_Z - 20.5
    out.append(geo.cyl_along(g.point3((g.seat[0] + s_guide * g.v[0], g.seat[1] + s_guide * g.v[1])),
                             g.point3((g.seat[0] + (s_pocket + 1.0) * g.v[0], g.seat[1] + (s_pocket + 1.0) * g.v[1])), 12.2))
    p1 = g.point3((g.seat[0] + 200 * g.v[0], g.seat[1] + 200 * g.v[1]))
    out.append(geo.cyl_along(p0, p1, SPRING_POCKET_D))
    # follower pocket: a slab from the pivot to the tip, from below the pivot band up through the top
    b = c.bank
    m_p, _ = S.bank_of_point_m_h(b, (0, g.pivot[0], g.pivot[1]))
    m_t, _ = S.bank_of_point_m_h(b, (0, g.tip[0], g.tip[1]))
    m_lo, m_hi = min(m_p, m_t) - 11.0, max(m_p, m_t) + 11.0   # the pivot cup is R 9.5
    h_lo = S.FOLLOWER_H_BAND - 14.0
    slab_pts = [S.bank_point(b, 0, m, h)[1:] for m, h in ((m_lo, h_lo), (m_hi, h_lo), (m_hi, h_lo + 200), (m_lo, h_lo + 200))]
    area = sum(slab_pts[i][0] * slab_pts[(i + 1) % 4][1] - slab_pts[(i + 1) % 4][0] * slab_pts[i][1] for i in range(4))
    if area < 0:
        slab_pts = list(reversed(slab_pts))
    out.append(geo.prism_yz(slab_pts, g.x - 8.5, g.x + 8.5))   # follower is 15.4 wide
    # HLA bore
    hla_top = g.point3(g.pivot)
    hla_bot = S.bank_point(b, g.x, m_p, S.FOLLOWER_H_BAND - 34.0)
    out.append(geo.cyl_along(hla_bot, hla_top, 12.2))
    return out


def cam_cuts(bank: int, kind: str):
    out = []
    yc, zc = S.bank_point(bank, 0, S.CAM_M[kind], S.CAM_H)[1:]
    # journal bore full length
    out.append(geo.cyl_x(HEAD_REAR_X - 5, HEAD_FRONT_X + 5, S.CAM_JOURNAL_D + 0.2, yc, zc))
    # lobe trough between saddles
    edges = [HEAD_FRONT_X + 5] + [x for x in CAM_SADDLE_X] + [HEAD_REAR_X - 5]
    for k in range(len(CAM_SADDLE_X) + 1):
        x_f = edges[k] if k == 0 else CAM_SADDLE_X[k - 1] - CAM_SADDLE_W / 2
        x_r = edges[k + 1] if k == len(CAM_SADDLE_X) else CAM_SADDLE_X[k] + CAM_SADDLE_W / 2
        if x_f - x_r > 1:
            out.append(geo.cyl_x(x_r, x_f, CAM_TROUGH_D, yc, zc))
    return out


SKIN_T = 0.45


def _common_fuzzy(shape, tools, fuzzy: float = 1e-3):
    """Multi-tool intersection (the skin harvester), fuzzy like geo.cut_fuzzy."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.TopTools import TopTools_ListOfShape

    args = TopTools_ListOfShape()
    args.Append(shape.wrapped)
    tl = TopTools_ListOfShape()
    for t in tools:
        tl.Append(t.wrapped)
    op = BRepAlgoAPI_Common()
    op.SetArguments(args)
    op.SetTools(tl)
    op.SetFuzzyValue(fuzzy)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise RuntimeError("fuzzy common failed")
    return bd.Compound(op.Shape())


def skin_boxes(bank: int):
    """(name, box) for every machined surface of the casting."""
    out = []
    x0, x1 = HEAD_REAR_X - 2.0, HEAD_FRONT_X + 2.0
    out.append(("deck", _mh_prism(bank, [(-M_FACE - 2, S.DECK_H), (M_FACE + 2, S.DECK_H),
                                         (M_FACE + 2, S.DECK_H + SKIN_T),
                                         (-M_FACE - 2, S.DECK_H + SKIN_T)], x0, x1)))
    for side, sgn in (("inner", 1.0), ("outer", -1.0)):
        out.append((f"cover_rail_{side}",
                    _mh_prism(bank, [(sgn * 110.0, TOP_H - SKIN_T), (sgn * 129.0, TOP_H - SKIN_T),
                                     (sgn * 129.0, TOP_H), (sgn * 110.0, TOP_H)], x0, x1)))
    for kind in ("intake", "exhaust"):
        m = S.CAM_M[kind]
        for k, xs in enumerate(CAM_SADDLE_X):
            out.append((f"cam_saddle_{kind}_{k + 1}",
                        _mh_prism(bank, [(m - 26.0, TOP_H - SKIN_T), (m + 26.0, TOP_H - SKIN_T),
                                         (m + 26.0, TOP_H), (m - 26.0, TOP_H)],
                                  xs - CAM_SADDLE_W / 2.0, xs + CAM_SADDLE_W / 2.0)))
        yc, zc = S.bank_point(bank, 0, m, S.CAM_H)[1:]
        out.append((f"cam_seal_{kind}",
                    geo.cyl_x(HEAD_FRONT_X - SEAL_CB_T, HEAD_FRONT_X - SEAL_CB_T + SKIN_T,
                              SEAL_CB_D, yc, zc)))
        out.append((f"cam_blank_{kind}",
                    geo.cyl_x(HEAD_REAR_X - CAM_BLANK_T, HEAD_REAR_X - CAM_BLANK_T + SKIN_T,
                              CAM_BLANK_D, yc, zc)))
    for c in bank_cylinders(bank):
        out.append((f"exhaust_pad_{c.number}",
                    face_block(bank, -1.0, c.x, sum(EX_BAND_H) / 2.0, 70.0,
                               EX_BAND_H[1] - EX_BAND_H[0], 8.0, M_FACE - SKIN_T, M_FACE + 2.0)))
        out.append((f"intake_pad_{c.number}",
                    face_block(bank, 1.0, c.x, sum(IN_BAND_H) / 2.0, 66.0,
                               IN_BAND_H[1] - IN_BAND_H[0], 8.0, M_FACE - SKIN_T, M_FACE + 2.0)))
        out.append((f"rail_pad_{c.number}",
                    face_block(bank, -1.0, c.x, sum(RAIL_LAND_H) / 2.0, RAIL_LAND_W - 4.0,
                               RAIL_LAND_H[1] - RAIL_LAND_H[0] - 4.0, 8.0,
                               M_FACE - SKIN_T, M_FACE + 2.0)))
    out.append(("plenum_rail", _band(bank, 1.0, PLENUM_RAIL_H[0] + 2.0, PLENUM_RAIL_H[1] - 2.0,
                                     M_FACE - SKIN_T)))
    for k, (m, h) in enumerate(COOLANT_MH, start=1):
        yc, zc = S.bank_point(bank, 0, m, h)[1:]
        out.append((f"coolant_face_{k}",
                    geo.cyl_x(HEAD_FRONT_X + COOLANT_PROUD - SKIN_T, HEAD_FRONT_X + COOLANT_PROUD,
                              COOLANT_BOSS_D, yc, zc)))
    return out


def machined_skins(bank: int, body):
    """Peel the bright skins off the casting; returns (body, [(label, solid)])."""
    boxes = skin_boxes(bank)
    harvest = _common_fuzzy(body, [b for _, b in boxes])
    solids = harvest.solids()
    if not solids:
        return body, []
    body = geo.cut_fuzzy(body, [harvest])
    named, counts = [], {}
    centres = [(n, b.bounding_box()) for n, b in boxes]
    for s in solids:
        c = s.center()
        best, best_d = None, 1e18
        for n, bb in centres:
            d = max(0.0, bb.min.X - c.X, c.X - bb.max.X) ** 2 \
                + max(0.0, bb.min.Y - c.Y, c.Y - bb.max.Y) ** 2 \
                + max(0.0, bb.min.Z - c.Z, c.Z - bb.max.Z) ** 2
            if d < best_d:
                best, best_d = n, d
        counts[best] = counts.get(best, 0) + 1
        suffix = "" if counts[best] == 1 else f"_{counts[best]}"
        named.append((f"head_face:{bank}_{best}{suffix}", s))
    return body, named


def spark_plug_local():
    """One plug in its own frame: z along the plug axis, z = 0 on the chamber
    roof, tip 3 mm proud into the chamber. (body, insulator, terminal)."""
    body = bd.revolve(bd.Plane.XZ * bd.make_face(bd.Polyline(
        (0.0, -3.0), (4.4, -3.0), (4.8, -1.4), (4.8, 1.0), (7.0, 2.0), (7.0, 15.0),
        (7.6, 16.0), (0.0, 16.0), close=True).edges()), bd.Axis.Z, 360)
    hexh = F._hex_prism(13.4, 16.0, 34.0)
    collar = bd.Cylinder(6.0, 6.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((0, 0, 34.0)))
    body = fuse_all([body, hexh, collar])
    ins = bd.revolve(bd.Plane.XZ * bd.make_face(bd.Polyline(
        (0.0, 40.0), (6.0, 40.0), (6.0, 56.0), (4.6, 60.0), (4.6, 62.0), (0.0, 62.0),
        close=True).edges()), bd.Axis.Z, 360)
    term = bd.Cylinder(4.0, 8.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((0, 0, 62.0)))
    return body, ins, term


_PLUG = None


def build_plugs(bank: int, sectioned: bool = True):
    global _PLUG
    if _PLUG is None:
        _PLUG = spark_plug_local()
    parts = []
    for c in bank_cylinders(bank):
        b, t = S.plug_axis(c.number)
        if geo.in_section_void(b, bank, sectioned):
            continue
        axis = (t[0] - b[0], t[1] - b[1], t[2] - b[2])
        for shape, name, colour in zip(_PLUG, ("spark_plug", "spark_plug_insulator",
                                               "spark_plug_terminal"),
                                       (P.MACHINED_STEEL, P.MACHINED, P.STEEL)):
            # a plug straddling the section plane is cut with the casting
            solid = geo.sectioned(geo.locate(shape, b, axis, (1, 0, 0)), bank, sectioned)
            if not solid.solids():
                continue
            parts.append(P.style(solid, f"{name}:{c.number}", colour))
    return parts


def build_bolts(bank: int, sectioned: bool = True):
    parts = []
    bolt = F.socket_cap_bolt(HEAD_BOLT_D, HEAD_BOLT_LEN)
    up = S.bank_up(bank)
    for i, (x, m) in enumerate(head_bolt_seats(bank), start=1):
        seat = S.bank_point(bank, x, m, WELL_FLOOR_H)
        if geo.in_section_void(seat, bank, sectioned):
            continue
        solid = geo.sectioned(geo.locate(bolt, seat, up, (1, 0, 0)), bank, sectioned)
        if not solid.solids():
            continue
        parts.append(P.style(solid, f"head_bolt:{bank}_{i}", P.TITANIUM_DARK))
    return parts


def build_core_plug(bank: int, sectioned: bool = True):
    p = S.bank_point(bank, HEAD_REAR_X, *CORE_PLUG_MH)
    if geo.in_section_void(p, bank, sectioned):
        return []
    prof = bd.make_face(bd.Polyline((0.0, 0.0), (CORE_PLUG_D / 2.0, 0.0), (CORE_PLUG_D / 2.0, 2.5),
                                    (11.0, 5.5), (0.0, 7.0), close=True).edges())
    plug = bd.revolve(bd.Plane.XZ * prof, bd.Axis.Z, 360)
    plug = geo.sectioned(geo.locate(plug, (p[0] + 3.0, p[1], p[2]), (-1.0, 0.0, 0.0)),
                         bank, sectioned)
    if not plug.solids():
        return []
    return [P.style(plug, f"core_plug:{bank}", P.STEEL)]


def build_head(bank: int, sectioned: bool = True):
    body = geo.prism_yz(head_outline(bank), HEAD_REAR_X, HEAD_FRONT_X)
    # exterior casting form first, while the body is still a plain prism
    body = geo.cut_fuzzy(body, [face_recess(bank, -1.0), face_recess(bank, 1.0)])
    body = geo.fuse_fuzzy([body, parting_bead(bank)])
    # Tools that overlap each other inside one multi-tool cut give wrong results,
    # so every cylinder's cutters (chamber + 4 valves) are fused into ONE tool;
    # the eight per-cylinder tools are mutually disjoint. Cam cutters overlap
    # the follower pockets, so they go in a second, separate cut per cam.
    tools = []
    for c in S.CYLINDERS:
        if c.bank != bank:
            continue
        cuts = [chamber(c)]
        for kind in ("intake", "exhaust"):
            for side in (-1, 1):
                cuts += valve_cuts(kin.valve_geom(c.number, kind, side))
        tools.append(geo.fuse_fuzzy(cuts))
    body = geo.cut_fuzzy(body, tools)
    for kind in ("intake", "exhaust"):
        body = geo.cut_fuzzy(body, [geo.fuse_fuzzy(cam_cuts(bank, kind))])
    # plug wells (they meet the chamber roof, so a pass of their own)
    body = geo.cut_fuzzy(body, [plug_bore(c) for c in bank_cylinders(bank)])
    # cast bosses on the end faces, then everything drilled into them
    body = geo.fuse_fuzzy([body] + end_bosses(bank))
    body = geo.cut_fuzzy(body, feature_cuts(bank))
    body = geo.cut_fuzzy(body, head_bolt_cuts(bank))
    body, skins = machined_skins(bank, body)
    body = geo.sectioned(body, bank, sectioned)
    assert is_sound(body), f"head {bank} not sound"
    out = [P.style(body, f"head:{bank}", P.CAST)]
    for label, skin in skins:
        skin = geo.sectioned(skin, bank, sectioned)
        if not skin.solids():
            continue
        out.append(P.style(skin, label, P.MACHINED))
    return out


def build(sectioned: bool = True):
    parts = []
    for bank in (1, 2):
        parts += build_head(bank, sectioned)
        parts += build_bolts(bank, sectioned)
        parts += build_plugs(bank, sectioned)
        parts += build_core_plug(bank, sectioned)
    return parts
