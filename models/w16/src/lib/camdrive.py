"""Cam drive: two crank sprockets, four cam sprockets, two roller-chain loops
(one per bank, 163 links each), chain guides and tensioner blades.

Everything is placed by lib/kin.chain_layout(): tooth pockets sit exactly on
the rest roller positions, rollers ride the pitch circle on a wrap and the
pitch line on a run, and link k is a rigid body between rollers k and k+1.
Inner links (plates + bushings + rollers, one solid) alternate with outer
links (plates + pins, one solid); pins run through bushing bores with 0.05 mm
of clearance, which covers the <0.01 mm chord/arc length deviation.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import fasteners as F, geo, kin, palette as P, spec as S
from lib.castings import safe_fillet, fuse_all

SPROCKET_T = 6.0                 # disc thickness along X
POCKET_R = S.CHAIN_ROLLER_D / 2 + 0.15
TIP_EXTRA = 1.9                  # tooth tip radius above the pitch radius
PLATE_R = 2.8                    # link plate end radius (plate height 5.6)
INNER_PLATE_X = (2.0, 3.0)       # |x| span of an inner plate (roller width 4 between)
OUTER_PLATE_X = (3.1, 4.1)
BUSH_OD, BUSH_ID = 3.2, 2.5
GUIDE_CLEAR = 0.5


def sprocket(sp: kin.Sprocket, x_centre: float, hub_od: float, bore: float, hub_x: tuple):
    """Toothed disc in the YZ plane at x_centre (+ a hub along X), pockets at rest roller angles."""
    disc = bd.Circle(sp.radius + TIP_EXTRA)
    pockets = None
    for a in kin.pocket_angles(sp):
        c = bd.Pos(sp.centre[0] * 0 + sp.radius * math.cos(a), sp.radius * math.sin(a)) * bd.Circle(POCKET_R)
        pockets = c if pockets is None else pockets + c
    disc = disc - pockets
    # lightening: leave a web with 6 windows on cam sprockets
    solid = bd.extrude(geo.yz_plane(x_centre - SPROCKET_T / 2) * disc, amount=SPROCKET_T)
    solid = solid.moved(bd.Location((0, sp.centre[0], sp.centre[1])))
    hub = geo.cyl_x(hub_x[0], hub_x[1], hub_od, sp.centre[0], sp.centre[1])
    solid = fuse_all([solid, hub])
    solid = solid - geo.cyl_x(hub_x[0] - 5, hub_x[1] + 5, bore, sp.centre[0], sp.centre[1])
    return solid


def _plate2d(pitch: float):
    return bd.Circle(PLATE_R) + bd.Pos(pitch, 0) * bd.Circle(PLATE_R) + bd.Pos(pitch / 2, 0) * bd.Rectangle(pitch, 2 * PLATE_R - 1.2)


def link_prototypes(pitch: float, x_plane: float):
    """(inner, outer) link solids spanning rollers at (0,0) and (pitch,0) in
    the YZ plane, centred on x_plane."""
    def plate_pair(span):
        out = []
        for sx in (-1, 1):
            x0 = x_plane + sx * span[0]
            x1 = x_plane + sx * span[1]
            face = geo.yz_plane(min(x0, x1)) * _plate2d(pitch)
            out.append(bd.extrude(face, amount=abs(x1 - x0)))
        return out

    inner = plate_pair(INNER_PLATE_X)
    for py in (0.0, pitch):
        bush = geo.cyl_x(x_plane - INNER_PLATE_X[1], x_plane + INNER_PLATE_X[1], BUSH_OD, py, 0.0)
        roller = geo.cyl_x(x_plane - INNER_PLATE_X[0] + 0.15, x_plane + INNER_PLATE_X[0] - 0.15, S.CHAIN_ROLLER_D, py, 0.0)
        inner += [bush, roller]
    inner_solid = fuse_all(inner)
    inner_solid = inner_solid - [geo.cyl_x(x_plane - 6, x_plane + 6, BUSH_ID, py, 0.0) for py in (0.0, pitch)]
    outer = plate_pair(OUTER_PLATE_X)
    for py in (0.0, pitch):
        outer.append(geo.cyl_x(x_plane - OUTER_PLATE_X[1] - 0.3, x_plane + OUTER_PLATE_X[1] + 0.3, S.CHAIN_PIN_D, py, 0.0))
    outer_solid = fuse_all(outer)
    return inner_solid, outer_solid


def link_location(layout: kin.ChainLayout, k: int, x_plane: float, advance: float = 0.0) -> bd.Location:
    p0, _ = kin.chain_point(layout, k + advance)
    p1, _ = kin.chain_point(layout, k + 1 + advance)
    ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    return bd.Location((0.0, p0[0], p0[1]), (ang, 0.0, 0.0))


def build_chain(bank: int):
    layout = kin.chain_layout(bank)
    x_plane = S.CHAIN_X[bank]
    inner, outer = link_prototypes(layout.pitch, x_plane)
    parts = []
    for k in range(layout.links):
        proto = inner if k % 2 == 0 else outer
        loc = link_location(layout, k, x_plane)
        kind = "inner" if k % 2 == 0 else "outer"
        parts.append(P.style(proto.moved(loc), f"chain_link:{bank}_{k + 1}_{kind}", P.STEEL_DARK))
    return layout, parts


def build_sprockets(bank: int, layout: kin.ChainLayout):
    x_plane = S.CHAIN_X[bank]
    parts = []
    for sp in layout.sprockets:
        if sp.name == "crank":
            hub_x = (x_plane - 4.0, x_plane + 4.0)
            s = sprocket(sp, x_plane, 58.0, 48.2, hub_x)
            parts.append(P.style(s, f"crank_sprocket:{bank}", P.MACHINED_STEEL))
        else:
            hub_x = (x_plane - 4.0, x_plane + 9.0)
            s = sprocket(sp, x_plane, 44.0, 24.2, hub_x)
            # lightening windows
            wins = []
            for j in range(6):
                a = math.radians(30 + 60 * j)
                r = sp.radius * 0.62
                wins.append(geo.cyl_x(x_plane - 10, x_plane + 10, 14.0, sp.centre[0] + r * math.cos(a), sp.centre[1] + r * math.sin(a)))
            s = s - wins
            kind = sp.name.split("_")[1]
            parts.append(P.style(s, f"cam_sprocket:{bank}_{kind}", P.MACHINED_STEEL))
            bolt = F.hex_flange_bolt(12.0, 30.0)
            parts.append(P.style(geo.locate(bolt, (x_plane + 9.0, sp.centre[0], sp.centre[1]), (1, 0, 0)),
                                 f"cam_sprocket_bolt:{bank}_{kind}", P.STEEL_DARK))
            washer = geo.cyl_x(x_plane + 9.0, x_plane + 12.0, 34.0, sp.centre[0], sp.centre[1]) - geo.cyl_x(
                x_plane + 5, x_plane + 15, 12.6, sp.centre[0], sp.centre[1])
            parts.append(P.style(washer, f"cam_sprocket_washer:{bank}_{kind}", P.MACHINED_STEEL))
    return parts


def build_guides(bank: int, layout: kin.ChainLayout):
    """A blade on the outside of every straight run, GUIDE_CLEAR off the plate
    edge; the first run (slack side) gets the tensioner body."""
    x_plane = S.CHAIN_X[bank]
    parts = []
    run_idx = 0
    for k0, k1, kind, data in layout.segments:
        if kind != "straight":
            continue
        pa, pb = data
        t = kin.norm(kin.sub(pb, pa))
        n = (t[1], -t[0])                     # outward (right of travel) for the CCW loop
        L = math.dist(pa, pb)
        margin = 24.0
        if L < 2 * margin + 40:
            continue
        a = kin.add(pa, kin.mul(t, margin))
        b = kin.add(pb, kin.mul(t, -margin))
        off = PLATE_R + GUIDE_CLEAR
        thick = 9.0
        pts = [kin.add(a, kin.mul(n, off)), kin.add(b, kin.mul(n, off)),
               kin.add(b, kin.mul(n, off + thick)), kin.add(a, kin.mul(n, off + thick))]
        area = sum(pts[i][0] * pts[(i + 1) % 4][1] - pts[(i + 1) % 4][0] * pts[i][1] for i in range(4))
        if area < 0:
            pts = list(reversed(pts))
        blade = geo.prism_yz(pts, x_plane - 7.0, x_plane + 7.0)
        blade, _ = safe_fillet(blade, [e for e in blade.edges() if abs(e.length - 14.0) < 1e-3], 3.0)
        parts.append(P.style(blade, f"chain_guide:{bank}_{run_idx + 1}", P.COMPOSITE))
        # mounting: a spacer + bolt at each end down to the block/head front face
        for j, pt in enumerate((a, b)):
            base = kin.add(pt, kin.mul(n, off + thick + 6.0))
            spacer = geo.cyl_x(S.BLOCK_FRONT_X, x_plane - 7.0, 12.0, base[0], base[1])
            parts.append(P.style(spacer, f"chain_guide_spacer:{bank}_{run_idx + 1}_{j + 1}", P.MACHINED))
            bolt = F.socket_cap_bolt(8.0, 40.0)
            parts.append(P.style(geo.locate(bolt, (x_plane + 7.0, base[0], base[1]), (1, 0, 0)),
                                 f"chain_guide_bolt:{bank}_{run_idx + 1}_{j + 1}", P.STEEL_DARK))
        if run_idx == 0:
            # tensioner body pressing the blade mid-run
            mid = kin.add(kin.add(a, b), (0, 0))
            mid = (mid[0] / 2, mid[1] / 2)
            body_c = kin.add(mid, kin.mul(n, off + thick + 22.0))
            body = geo.cyl_x(x_plane - 11.0, x_plane + 11.0, 26.0, body_c[0], body_c[1])
            plunger = geo.cyl_along((x_plane, *kin.add(mid, kin.mul(n, off + thick + 0.3))), (x_plane, *body_c), 12.0)
            parts.append(P.style(fuse_all([body, plunger]), f"chain_tensioner:{bank}", P.MACHINED))
        run_idx += 1
    return parts


def build_crank_hub():
    hub = geo.cyl_x(S.CHAIN_X[1] - 6.0, S.CHAIN_X[2] + 6.0, 56.0) - geo.cyl_x(300, 350, 48.2)
    hub = hub - bd.Box(60, 6.2, 5.2, align=(bd.Align.MIN, bd.Align.CENTER, bd.Align.MIN)).moved(bd.Location((S.CRANK_NOSE_X[0] + 10, 0, 21.0)))
    return P.style(hub, "crank_sprocket_hub", P.MACHINED_STEEL)


def build(sectioned: bool = True):
    parts = [build_crank_hub()]
    for bank in (1, 2):
        layout, links = build_chain(bank)
        parts += build_sprockets(bank, layout)
        parts += links
        parts += build_guides(bank, layout)
    return parts
