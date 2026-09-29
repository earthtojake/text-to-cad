"""Mount system: the welded steel engine-mount ring the engine hangs from.

    ring        `mount:ring_left` / `mount:ring_right` gloss black enamel, slim
                round-section Ø28 steel ring, centre radius R_RING 385 about the
                crank axis at y 288, tucked against the blower's lug pads so it
                reads as part of the engine. SPLIT into two C-arcs: open over the
                top (in-plane |b| < 34) so the museum section of cylinder 1 is
                seen from the rear with nothing in front of it, and at the bottom
                (|b - 180| < 14) where the carburettor passes. Each end is closed
                by a welded hemispherical cap just past its end boss (2, 5 | 6, 9).
    bosses      `mount:boss_<k>` k = 2..9 at in-plane ALPHA(k): a forged cup
                (bushing housing, axis along +Y at r 288 — coaxial with the
                blower's mount-lug bolt hole) on a tapered neck welded to the
                ring (the neck is coped to the ring tube).
    mount units (rubber-bushed, Lord/Dynafocal style), per k = 2..9 on the lug
                axis (lug 1, under the open top, is left bare):
                `mount:front_washer_<k>`  steel cup on the lug pad (y 262..264.5)
                `mount:bushing_<k>`       rubber spool: two flanges bulging past the
                                          cup ends, barrel in the housing bore
                `mount:sleeve_<k>`        steel spacer through the rubber, clamped
                                          between the lug pad and the rear washer
                `mount:rear_washer_<k>`   steel cup washer behind the rubber
                `mount:bolt_<k>`          through bolt Ø14 from the FRONT of the lug:
                                          a double-D (tee) head keyed by the flats
                                          (the inner flat keys against the blower's
                                          lug gusset); cross-drilled for the cotter
                `mount:nut_<k>`           castellated nut at the rear
                `mount:cotter_<k>`        cotter pin through a castellation slot

The mount unit is authored once for cylinder 1's lug (in-plane 0: radial
= +Z, tangential = +X) and placed with `geo.on_cylinder`, so they share geometry.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import fasteners as F
from lib import geo
from lib import palette as P
from lib import spec as S

MATERIALS = ("enamel_black", "fastener", "rubber", "safety_wire")

# ---------------------------------------------------------------------------
# Numbers (mm)
# ---------------------------------------------------------------------------
LUG_R = 288.0            # blower lug bolt axis radius
PAD_Y = 262.0            # blower lug machined pad face
LUG_FRONT_Y = 240.0      # blower lug front face (bolt-head seat)
R_RING = 385.0
Y_RING = 288.0
RING_TUBE_R = 14.0
# The top arc is omitted (museum section: clear line of sight to cylinder 1 from
# the rear): the ring runs from boss 2 round the bottom to boss 9 and ends in caps.
RING_GAP = 34.0          # in-plane half-angle of the open top
RING_GAP_BOTTOM = 14.0   # half-angle of the bottom gap the carburettor (x +-66, y <= 292) passes through
UNITS = tuple(range(2, S.N_CYL + 1))   # lugs carrying mount units (lug 1 is left bare)

# stack along the lug axis (y)
FW_Y = (PAD_Y, 264.5)            # front cup washer
HOUS_Y = (269.0, 295.0)          # boss cup (housing)
HOUS_RO, HOUS_RI = 28.0, 23.2
RUB_FLANGE_Y = ((264.5, 269.0), (295.0, 299.5))
RUB_FLANGE_R = 26.0
RUB_BARREL_R = 23.0
RUB_BORE_R = 12.15
SLEEVE_R = (7.15, 12.0)
SLEEVE_Y = (PAD_Y, 299.5)
RW_Y = (299.5, 302.0)            # rear cup washer
NUT_Y0 = 302.0
NUT_HEX_H = 7.5
NUT_H = 13.0
NUT_AF = 22.0
NUT_CROWN_R = 9.5
SLOT_W, SLOT_D = 3.6, 4.8
BOLT_D = 14.0
BOLT_HEAD_H = 9.0
BOLT_HEAD_R = 12.0
BOLT_FLAT_IN, BOLT_FLAT_OUT = 8.0, 7.0   # double-D flats from the axis (radial in / out)
BOLT_END_Y = 318.5
COTTER_Y = 312.0
COTTER_D = 2.8


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _one(shape):
    ss = shape.solids()
    if len(ss) == 1:
        return ss[0]
    return max(ss, key=lambda s: s.volume)


def _rev_y(pts, x=0.0, z=LUG_R):
    """Revolve a closed (radius, y) polygon about the axis parallel to Y through (x, ., z)."""
    face = bd.make_face(bd.Polyline(*[(r, y, 0.0) for r, y in pts], close=True).edges())
    sol = bd.revolve(face, axis=bd.Axis.Y)
    return bd.Pos(x, 0.0, z) * sol


def _torus_ring():
    face = bd.Plane.XY * bd.Pos(R_RING, Y_RING) * bd.Circle(RING_TUBE_R)
    return _one(bd.revolve(face, axis=bd.Axis.Y))


# ---------------------------------------------------------------------------
# Ring and bosses
# ---------------------------------------------------------------------------
def ring_half(side):
    """One C-shaped half of the split ring: from the open top (|in-plane| >
    RING_GAP) round to the carburettor gap at the bottom (|in-plane - 180| >
    RING_GAP_BOTTOM), each end closed by a welded hemispherical cap just past
    its end boss. side +1 = in-plane 0..180 (x < 0, left seen from the front)."""
    b0, b1 = (RING_GAP, 180.0 - RING_GAP_BOTTOM) if side > 0 else (-180.0 + RING_GAP_BOTTOM, -RING_GAP)
    keep = geo._sector_solid(b0, b1, R_RING - 40.0, R_RING + 40.0, Y_RING - 40.0, Y_RING + 40.0)
    body = _one(_torus_ring() & keep)
    caps = [bd.Pos(*S.inplane(b, R_RING, Y_RING)) * bd.Sphere(RING_TUBE_R) for b in (b0, b1)]
    return _one(C.fuse_all([body] + caps))


def full_ring():
    """The uncut torus: the coping tool for the boss necks."""
    return _torus_ring()


def boss_proto(ring_solid):
    """Cylinder-1 boss: machined cup on the lug axis + tapered forged neck coped to the ring."""
    y0, y1 = HOUS_Y
    ro, ri, c = HOUS_RO, HOUS_RI, 1.0
    cup = _rev_y([(ri + 0.8, y0), (ro - c, y0), (ro, y0 + c), (ro, y1 - c), (ro - c, y1),
                  (ri + 0.8, y1), (ri, y1 - 0.8), (ri, y0 + 0.8)])
    # neck: loft between two rounded rectangles normal to the radial direction (+Z)
    s0, s1 = LUG_R + 18.0, R_RING - 5.0
    yc0, yc1 = 0.5 * (y0 + y1), Y_RING
    pl0 = bd.Plane(origin=(0.0, yc0, s0), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    pl1 = bd.Plane(origin=(0.0, yc1, s1), x_dir=(1, 0, 0), z_dir=(0, 0, 1))
    f0 = pl0 * bd.RectangleRounded(36.0, 20.0, 6.5)
    f1 = pl1 * bd.RectangleRounded(22.0, 17.0, 5.5)
    neck = bd.loft([f0, f1], ruled=False)
    body = _one(C.fuse_all([cup, neck]))
    # root blend where the neck leaves the cup
    def root(e):
        if e.geom_type.name in ("LINE", "CIRCLE"):
            return False
        cc = C.edge_center(e)
        return 300.0 < cc.Z < 318.0 and y0 - 1 < cc.Y < y1 + 1
    body, _ = C.safe_fillet(body, [e for e in body.edges() if root(e)], 6.0, min_r=1.5)
    bore = geo.cyl_y(y0 - 1.0, y1 + 1.0, 2 * ri, 0.0, LUG_R)
    # the neck rises rearward: relieve it round the rear flange, washer and nut
    relief = geo.cyl_y(y1, y1 + 30.0, 2 * (RUB_FLANGE_R + 1.5), 0.0, LUG_R)
    body = _one(C.cut_all(body, [_one(bore + relief), ring_solid]))
    return body


# ---------------------------------------------------------------------------
# Mount-unit hardware (cylinder-1 lug; authored in the engine frame)
# ---------------------------------------------------------------------------
def front_washer():
    y0, y1 = FW_Y
    return _rev_y([(12.3, y0), (25.6, y0), (26.0, y0 + 0.4), (26.0, y1 - 0.5), (25.5, y1),
                   (12.8, y1), (12.3, y1 - 0.5)])


def rear_washer():
    y0, y1 = RW_Y
    return _rev_y([(7.25, y0), (24.5, y0), (25.0, y0 + 0.5), (25.0, y1 - 0.4), (24.6, y1),
                   (7.75, y1), (7.25, y1 - 0.5)])


def sleeve():
    y0, y1 = SLEEVE_Y
    ri, ro = SLEEVE_R
    return _rev_y([(ri, y0), (ro - 0.4, y0), (ro, y0 + 0.4), (ro, y1 - 0.4), (ro - 0.4, y1),
                   (ri, y1)])


def bushing():
    """Rubber spool: flanges with bulged, rounded rims, barrel in the housing bore."""
    (a0, a1), (b0, b1) = RUB_FLANGE_Y
    rf, rb, ri = RUB_FLANGE_R, RUB_BARREL_R, RUB_BORE_R
    pts = [(ri, a0), (rf - 1.6, a0), (rf, a0 + 1.6), (rf, a1 - 1.2), (rf - 1.2, a1),
           (rb, a1), (rb, b0), (rf - 1.2, b0), (rf, b0 + 1.2), (rf, b1 - 1.6), (rf - 1.6, b1),
           (ri, b1)]
    body = _rev_y(pts)
    # round the flange rims (circle edges at the outer radius)
    def rim(e):
        if e.geom_type.name != "CIRCLE":
            return False
        bb = e.bounding_box()
        return (bb.max.X - bb.min.X) / 2 > rf - 2.0
    body, _ = C.safe_fillet(body, [e for e in body.edges() if rim(e)], 0.8, min_r=0.2)
    return body


def bolt_proto():
    """Tee-head (double-D) through bolt authored along +Z; head bearing face z = 0,
    local +Y = world radial INWARD after placement (x_dir = world +X, z_dir = +Y)."""
    h = BOLT_HEAD_H
    L = BOLT_END_Y - LUG_FRONT_Y
    r = BOLT_D / 2.0
    b = F._rev([(0.0, -h), (BOLT_HEAD_R - 1.2, -h), (BOLT_HEAD_R, -h + 1.2),
                (BOLT_HEAD_R, -0.4), (BOLT_HEAD_R - 0.4, 0.0), (r, 0.0),
                (r, L - 1.0), (r - 1.0, L), (0.0, L)])
    al = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MAX)
    flats = [bd.Pos(0, BOLT_FLAT_IN + 10.0, 0.0) * bd.Box(40.0, 20.0, h + 3.0, align=al),
             bd.Pos(0, -BOLT_FLAT_OUT - 10.0, 0.0) * bd.Box(40.0, 20.0, h + 3.0, align=al)]
    hole = bd.Pos(0, 0, COTTER_Y - LUG_FRONT_Y) * bd.Rot(0, 90, 0) * bd.Cylinder(1.6, 30.0)
    return _one(C.cut_all(b, flats + [hole]))


def bolt():
    return F.place(bolt_proto(), (0.0, LUG_FRONT_Y, LUG_R), (0, 1, 0), (1, 0, 0))


def nut_proto():
    """Castellated nut along +Z, bearing face z = 0; slots through the flats (one along X)."""
    hexb = F._wrench_head(NUT_AF, 0.0, NUT_HEX_H + 0.6, chamfer_bottom=True, chamfer_top=True)
    crown = F._rev([(0.0, NUT_HEX_H), (NUT_CROWN_R, NUT_HEX_H), (NUT_CROWN_R, NUT_H - 0.6),
                    (NUT_CROWN_R - 0.6, NUT_H), (0.0, NUT_H)])
    body = _one(C.fuse_all([hexb, crown]))
    bore = bd.Pos(0, 0, -1) * bd.Cylinder(7.05, NUT_H + 2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    slots = [bd.Rot(0, 0, a) * bd.Pos(0, 0, NUT_H - SLOT_D) *
             bd.Box(40.0, SLOT_W, SLOT_D + 2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
             for a in (0.0, 60.0, 120.0)]
    slots = [_one(C.fuse_all(slots))]
    return _one(C.cut_all(body, [bore] + slots))


def nut():
    return F.place(nut_proto(), (0.0, NUT_Y0, LUG_R), (0, 1, 0), (1, 0, 0))


def cotter():
    """Cotter pin: straight shank along X through the crown slot and the bolt's
    cross hole, an eye on the -X side, the long leg bent rearward on the +X side."""
    y, z, rw = COTTER_Y, LUG_R, COTTER_D / 2.0
    x0, x1, rb = -12.2, 11.6, 2.2
    path = bd.Wire([
        bd.Line((x0, y, z), (x1, y, z)),
        bd.ThreePointArc((x1, y, z), (x1 + rb * math.sin(math.pi / 4), y + rb * (1 - math.cos(math.pi / 4)), z),
                         (x1 + rb, y + rb, z)),
        bd.Line((x1 + rb, y + rb, z), (x1 + rb, y + 6.5, z)),
    ])
    prof = bd.Plane(origin=(x0, y, z), z_dir=(1, 0, 0)) * bd.Circle(rw)
    pin = bd.sweep(prof, path=path, transition=bd.Transition.ROUND)
    eye = bd.Pos(x0 - 2.4, y, z) * bd.Torus(2.4, rw)
    tip = bd.Pos(x1 + rb, y + 6.5, z) * bd.Sphere(rw)
    return _one(C.fuse_all([_one(pin), eye, tip]))


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def build():
    EB, FA, RU, SW = P.ENAMEL_BLACK, P.FASTENER, P.RUBBER, P.SAFETY_WIRE
    parts = []
    parts.append(P.style(ring_half(+1), "mount:ring_left", EB))
    parts.append(P.style(ring_half(-1), "mount:ring_right", EB))
    ring_solid = full_ring()

    protos = [
        ("boss", boss_proto(ring_solid), EB),
        ("front_washer", front_washer(), FA),
        ("bushing", bushing(), RU),
        ("sleeve", sleeve(), FA),
        ("rear_washer", rear_washer(), FA),
        ("bolt", bolt(), FA),
        ("nut", nut(), FA),
        ("cotter", cotter(), SW),
    ]
    for k in UNITS:
        for name, proto, col in protos:
            parts.append(P.style(geo.on_cylinder(proto, k), f"mount:{name}_{k}", col))

    return parts


if __name__ == "__main__":
    import time
    t0 = time.time()
    ps = build()
    print(f"{len(ps)} leaves in {time.time() - t0:.1f}s")
    print("unsound:", [p.label for p in ps if not geo.sound(p)])
