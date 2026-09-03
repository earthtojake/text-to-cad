"""Crankshaft, main caps, main bearing shells, flywheel, damper (engine frame).

The crank is ONE forged solid: five main journals, eight crankpins at the
spec's derived phase angles, thin webs beside the mains, thick counterweighted
webs between the pins of each pair, the nose (sprocket seat + damper seat)
and the rear flange. Everything is placed by lib/spec.py numbers.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import fasteners as F, geo, palette as P, spec as S
from lib.castings import safe_chamfer, safe_fillet, fuse_all, is_sound

HUB_R = 40.0          # web hub radius around the main axis
PIN_WEB_R = 33.0      # web radius around a pin
CW_R = S.COUNTERWEIGHT_R
CW_HALF_ANGLE = 58.0
OIL_HOLE_D = 5.0      # main -> pin oil drilling
WEB_R = 4.0           # web / counterweight edge break


def _edge_radius(e):
    try:
        return e.radius
    except Exception:
        return None


def _ext(p, q, d: float):
    """`p` pushed `d` further away from `q` along the line q -> p."""
    v = [p[k] - q[k] for k in range(3)]
    L = math.sqrt(sum(c * c for c in v))
    return tuple(p[k] + v[k] * d / L for k in range(3))


def _pin_yz(pin: int):
    a = math.radians(S.pin_angle(pin))
    return (-S.THROW * math.sin(a), S.THROW * math.cos(a))


def _web_sketch(pins, cw_dir_deg=None):
    """2D web outline in sketch coords (x = engine Y, y = engine Z)."""
    sk = bd.Circle(HUB_R)
    for pin in pins:
        py, pz = _pin_yz(pin)
        ang = math.degrees(math.atan2(pz, py))
        sk = sk + bd.Pos(py, pz) * bd.Circle(PIN_WEB_R)
        sk = sk + bd.Pos(py / 2.0, pz / 2.0) * bd.Rot(0, 0, ang) * bd.Rectangle(S.THROW, 2 * PIN_WEB_R)
    if cw_dir_deg is not None:
        a0 = math.radians(cw_dir_deg - CW_HALF_ANGLE)
        a1 = math.radians(cw_dir_deg + CW_HALF_ANGLE)
        wedge = bd.Polygon((0, 0), (200 * math.cos(a0), 200 * math.sin(a0)),
                           (200 * math.cos(cw_dir_deg * math.pi / 180), 200 * math.sin(cw_dir_deg * math.pi / 180)),
                           (200 * math.cos(a1), 200 * math.sin(a1)), align=None)
        sk = sk + (bd.Circle(CW_R) & wedge)
    return sk


def _cw_direction(pins):
    vy = sum(_pin_yz(p)[0] for p in pins)
    vz = sum(_pin_yz(p)[1] for p in pins)
    return math.degrees(math.atan2(-vz, -vy))


def _oil_drillings():
    """One straight Ø5 drilling per crankpin, from the neighbouring main journal
    to the pin. It enters the main journal surface on the pin side and breaks
    out on the pin's flank (55 deg off the crank-axis side, away from the rod's
    loaded arc) — both ends are pushed clear of the surface so the hole really
    opens on both journals."""
    cuts = []
    for i in range(S.N_PINS):
        xp = S.PIN_X[i]
        xm = S.MAIN_X[i // 2] if i % 2 == 0 else S.MAIN_X[i // 2 + 1]
        sgn = 1.0 if xm > xp else -1.0
        py, pz = _pin_yz(i)
        n = (py / S.THROW, pz / S.THROW)          # crank axis -> pin centre
        t = (-n[1], n[0])                          # perpendicular, in the swing plane
        rm, rp = S.MAIN_D / 2, S.PIN_D / 2
        a = math.radians(55.0)
        entry = (xm - sgn * 5.0, rm * n[0], rm * n[1])
        exit_ = (xp + sgn * 8.0,
                 py - rp * (math.cos(a) * n[0] - math.sin(a) * t[0]),
                 pz - rp * (math.cos(a) * n[1] - math.sin(a) * t[1]))
        cuts.append(geo.cyl_along(_ext(entry, exit_, 5.0), _ext(exit_, entry, 5.0), OIL_HOLE_D))
    return cuts


def _thrust_faces():
    """The centre main carries the thrust: a root undercut plus a shallow faced
    land on the web face either side of it."""
    cuts = []
    xm = S.MAIN_X[2]
    hm = S.MAIN_LEN / 2
    bore = S.MAIN_D + 0.4
    for s in (-1, 1):
        a0, a1 = sorted((xm + s * hm, xm + s * (hm + 1.2)))
        deep = geo.cyl_x(a0, a1, 76.0) - geo.cyl_x(a0 - 2, a1 + 2, bore)
        b0, b1 = sorted((xm + s * hm, xm + s * (hm + 0.35)))
        face = geo.cyl_x(b0, b1, 92.0) - geo.cyl_x(b0 - 2, b1 + 2, bore)
        cuts.append(fuse_all([face, deep]))
    return cuts


def _web(x0, x1, pins, counterweight=True, fillet_r=WEB_R):
    sk = _web_sketch(pins, _cw_direction(pins) if counterweight else None)
    solid = bd.extrude(geo.yz_plane(x0) * sk, amount=x1 - x0)
    if fillet_r:
        outer = [e for e in solid.edges() if e.radius is None or abs(e.radius - CW_R) < 1e-3] if False else solid.edges()
        solid, _ = safe_fillet(solid, [e for e in solid.edges()
                                       if not (abs(e.center().Y) < HUB_R + 1 and abs(e.center().Z) < HUB_R + 1)],
                               fillet_r, min_r=3.0)
    return solid


def build_crank():
    parts = []
    # main journals (a hair longer than their bay so the fuse has overlap)
    for xm in S.MAIN_X:
        parts.append(geo.cyl_x(xm - S.MAIN_LEN / 2 - 0.5, xm + S.MAIN_LEN / 2 + 0.5, S.MAIN_D))
    # crankpins
    for i, xp in enumerate(S.PIN_X):
        py, pz = _pin_yz(i)
        parts.append(geo.cyl_x(xp - S.PIN_LEN / 2 - 0.5, xp + S.PIN_LEN / 2 + 0.5, S.PIN_D, py, pz))
    # webs: front thin, pairs, rear thin
    half_pin = S.PIN_LEN / 2
    half_main = S.MAIN_LEN / 2
    # pin i (0-based) x, pair index p = i//2
    for i in range(S.N_PINS):
        xp = S.PIN_X[i]
        if i % 2 == 0:
            # front side of the pair's first pin: thin web to the main in front
            xm = S.MAIN_X[i // 2]
            parts.append(_web(xp + half_pin, xm - half_main, [i], counterweight=True))
            # thick web between this pin and the next
            parts.append(_web(S.PIN_X[i + 1] + half_pin, xp - half_pin, [i, i + 1], counterweight=True))
        else:
            xm = S.MAIN_X[i // 2 + 1]
            parts.append(_web(xm + half_main, xp - half_pin, [i], counterweight=True))
    # nose
    parts.append(geo.cyl_x(S.MAIN_X[0] + half_main, S.MAIN_X[0] + half_main + 8.0, 62.0))
    parts.append(geo.cyl_x(S.MAIN_X[0] + half_main + 7.0, S.CRANK_NOSE_X[1], 48.0))
    # rear: seal journal + flange + pilot
    parts.append(geo.cyl_x(S.CRANK_FLANGE_X + 6.0, S.MAIN_X[-1] - half_main + 0.5, 82.0))
    parts.append(geo.cyl_x(S.CRANK_FLANGE_X, S.CRANK_FLANGE_X + 7.0, 132.0))
    parts.append(geo.cyl_x(S.CRANK_FLANGE_X - 12.0, S.CRANK_FLANGE_X + 0.5, 44.0))
    crank = fuse_all(parts)
    # rolled root fillets where each crankpin runs into its webs (the mains are
    # left square: their shells sit 1 mm from the web face and a fillet there
    # would foul them).
    roots = []
    for xp in S.PIN_X:
        for s in (-1, 1):
            roots += [e for e in crank.edges()
                      if _edge_radius(e) is not None and abs(_edge_radius(e) - S.PIN_D / 2) < 0.3
                      and abs(e.center().X - (xp + s * S.PIN_LEN / 2)) < 0.6]
    crank, _ = safe_fillet(crank, roots, 1.5, min_r=0.5)
    # flange bolt holes, nose keyway, flywheel pilot lip, oil drillings
    holes = []
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        holes.append(geo.cyl_x(S.CRANK_FLANGE_X - 20, S.CRANK_FLANGE_X + 20, 10.5, 50 * math.cos(a), 50 * math.sin(a)))
    # end-milled parallel keyway, 8 x 4 deep with round ends, in the D48 nose
    kx0, kw, kd, klen = S.CRANK_NOSE_X[0] + 14.0, 8.0, 4.0, 46.0
    key = bd.Box(klen, kw, 12.0, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((kx0, 0, 24.0 - kd)))
    key = key + [bd.Cylinder(kw / 2, 12.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)).moved(
        bd.Location((kx0 + e, 0, 24.0 - kd))) for e in (0.0, klen)]
    # the flywheel pilot: a lead chamfer plus a root undercut so the flywheel
    # pulls flat onto the flange face and never on the spigot radius
    px = S.CRANK_FLANGE_X - 12.0
    lip = geo.cyl_x(S.CRANK_FLANGE_X - 1.6, S.CRANK_FLANGE_X + 0.5, 49.0) - geo.cyl_x(
        S.CRANK_FLANGE_X - 4, S.CRANK_FLANGE_X + 2, 44.0 + 0.6)
    crank = crank - (holes + [key, lip] + _oil_drillings() + _thrust_faces())
    ends = {(24.0, S.CRANK_NOSE_X[1]): 1.2, (22.0, px): 1.5, (66.0, S.CRANK_FLANGE_X + 7.0): 1.0}
    for (r, x), c in ends.items():
        crank, _ = safe_chamfer(crank, [e for e in crank.edges()
                                        if _edge_radius(e) is not None and abs(_edge_radius(e) - r) < 0.3
                                        and abs(e.center().X - x) < 0.6], c)
    assert is_sound(crank), "crank not sound"
    return P.style(crank, "crankshaft", P.MACHINED_STEEL)


def build_main_caps_and_shells():
    """Main caps (below each main), their bolts, and upper/lower bearing shells."""
    parts = []
    cap_w = 116.0
    cap_h = 46.0
    saddle_d = S.MAIN_D + 4.0            # shell OD
    for k, xm in enumerate(S.MAIN_X):
        t = S.MAIN_LEN
        # The FRONT main (k = 0) runs in a full-round bore through the block's
        # front wall (the wall IS that bulkhead, x 294..306), so it has shells
        # but no separate cap; the other four are capped and cross-bolted.
        if k > 0:
            cap = bd.Box(t, cap_w, cap_h, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
                bd.Location((xm, 0, 0)))
            cap = cap - geo.cyl_x(xm - t, xm + t, saddle_d)
            # register step + soft outer edges
            cap, _ = safe_fillet(cap, [e for e in cap.edges() if e.center().Z < -cap_h + 1e-3], 4.0)
            parts.append(P.style(cap, f"main_cap:{k + 1}", P.MACHINED))
            for sy in (-1, 1):
                bolt = F.twelve_point_bolt(12.0, 95.0)
                parts.append(P.style(geo.locate(bolt, (xm, sy * 40.0, -cap_h), (0, 0, -1)),
                                     f"main_bolt:{k + 1}_{'l' if sy > 0 else 'r'}", P.STEEL_DARK))
        for half, lab in ((1, "upper"), (-1, "lower")):
            ring = geo.cyl_x(xm - 9.0, xm + 9.0, saddle_d) - geo.cyl_x(xm - 10, xm + 10, S.MAIN_D + 0.1)
            cutter = bd.Box(40, 200, 200, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN if half < 0 else bd.Align.MAX)).moved(
                bd.Location((xm, 0, 0)))
            shell = ring - cutter
            parts.append(P.style(shell, f"main_shell:{k + 1}_{lab}", P.MACHINED_STEEL))
    return parts


def build_flywheel():
    x_face = S.CRANK_FLANGE_X            # bolts against the crank flange
    fw = geo.cyl_x(x_face - 32.0, x_face, 320.0)
    fw = fw - geo.cyl_x(x_face - 40, x_face - 22.0, 250.0)      # dished back
    fw = fw - geo.cyl_x(x_face - 40, x_face + 5, 44.2)          # pilot bore
    # ring gear teeth
    teeth = []
    n = 132
    for k in range(n):
        a = 360.0 * k / n
        tooth = bd.Box(14.0, 2.6, 6.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)).moved(
            bd.Location((x_face - 16.0, 0, 161.0)))
        teeth.append(tooth.rotate(bd.Axis.X, a))
    fw = fw - teeth
    holes = []
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        holes.append(geo.cyl_x(x_face - 40, x_face + 5, 10.5, 50 * math.cos(a), 50 * math.sin(a)))
    fw = fw - holes
    fw, _ = safe_fillet(fw, [e for e in fw.edges() if _edge_radius(e) is not None and abs(_edge_radius(e) - 160.0) < 1e-3], 2.0)
    parts = [P.style(fw, "flywheel", P.MACHINED_STEEL)]
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        bolt = F.twelve_point_bolt(10.0, 40.0)
        parts.append(P.style(geo.locate(bolt, (x_face - 32.0, 50 * math.cos(a), 50 * math.sin(a)), (-1, 0, 0)),
                             f"flywheel_bolt:{k + 1}", P.STEEL_DARK))
    return parts


def build_damper():
    x0 = 340.0
    hub = geo.cyl_x(x0 - 4.0, x0 + 34.0, 70.0) - geo.cyl_x(x0 - 10, x0 + 40, 48.2)
    ring = geo.cyl_x(x0, x0 + 30.0, 182.0) - geo.cyl_x(x0 - 5, x0 + 35, 128.0)
    web = geo.cyl_x(x0 + 6.0, x0 + 24.0, 132.0) - geo.cyl_x(x0 - 5, x0 + 35, 66.0)
    grooves = [geo.cyl_x(x0 + 4.0 + 4.5 * k, x0 + 6.0 + 4.5 * k, 190.0) - geo.cyl_x(x0, x0 + 35, 176.0) for k in range(6)]
    damper = fuse_all([hub, ring, web]) - grooves
    damper, _ = safe_fillet(damper, [e for e in damper.edges() if _edge_radius(e) is not None and abs(_edge_radius(e) - 91.0) < 1e-3], 2.0)
    parts = [P.style(damper, "crank_damper", P.MACHINED_STEEL)]
    washer = geo.cyl_x(S.CRANK_NOSE_X[1], S.CRANK_NOSE_X[1] + 6.0, 70.0)
    parts.append(P.style(washer, "damper_washer", P.MACHINED_STEEL))
    bolt = F.hex_flange_bolt(16.0, 60.0)
    parts.append(P.style(geo.locate(bolt, (S.CRANK_NOSE_X[1] + 6.0, 0, 0), (1, 0, 0)), "damper_bolt", P.STEEL_DARK))
    return parts


def build(sectioned: bool = True):
    parts = [build_crank()]
    parts += build_main_caps_and_shells()
    parts += build_flywheel()
    parts += build_damper()
    return parts
