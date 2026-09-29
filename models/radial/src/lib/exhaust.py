"""Exhaust: nine identical stacks from the heads' REAR exhaust ports into a slim
collector ring nestled right behind the heads; telescoping slip joints with
T-bolt band clamps; one outlet at the bottom sweeping down and rearward out of
the envelope.

GEOMETRY (engine frame, mm; b = in-plane angle, spec.inplane; (rho, y) = radius
about the crank axis and station along it)
  port       the heads' exhaust flange: face y 110 facing +y, centre (t -80,
             h 468) on cylinder 1 = RHO_PORT 474.8 at in-plane GAMMA 9.70 deg;
             studs M8 at h 430 / 506, the heads' nuts seat on y 118.
  gasket     y 110.25..111 (the heads' side-fin tips stand 0.2 mm proud of
             their port face), the heads' slot outline (76 c-c, 60 wide).
  stack      flange y 111..118, tube OD 42 / ID 39 in the RADIAL PLANE through
             the port (b = ALPHA(k) + GAMMA): 2 mm straight, one true circular
             bend of R 63 (1.5 D) turning 55 deg outward, then 2 mm straight
             into its ring boss (slip fit, 14 mm inside, 0.3 mm clearance).
             Heat-tint bloom: blue at the port, straw through the bend, then
             the base. Authored once on cylinder 1, rotated onto 2..9.
  ring       centreline RC 538 at YC 197 (set by the stack geometry), hard
             behind the heads, as close to the port radius (475) as the
             neighbours allow: a head-height ring must cross every cylinder's
             intake elbow (rel -12..-4 deg, r up to 512 at y 110-160, 480 at
             y 190) and rear plug lead (rel 0..4 deg, r 494-578 at y 100-150),
             so it passes just behind both; the carburettor under the blower
             (r <= 492 at y 200-293) fixes RC >= 533 for the Ø72 bottom
             segment. The flow divides at the top (cylinder 1's boss) and runs
             down both sides to the outlet at b = GAMMA + 180; the ring is
             mirror-symmetric about that diameter. Five tube sizes growing with
             the flow (OD 56 / 60 / 64 / 68 / 72, wall 1.5); each upstream
             segment's spigot telescopes 20 mm into the next one's mouth
             (0.5 mm radial clearance) under a band clamp.
  outlet     a Ø52 stub radially out of the bottom segment, the Ø56 tailpipe
             telescoped over it (band clamp), sweeping down and rearward below
             the carburettor and sump to a six-hole flange at y 420.
  support    the stacks, each clamped to its head by the heads' two studs and
             nuts, carry the ring through their slip-fit bosses; the ring
             segments hang on each other's clamped slip joints; the outlet hangs
             on the bottom segment's tee.

MUSEUM SECTION (0 < y < 340, r > 300, +-20 deg of the top): cylinder 1's
stack, flange and gasket and the top of the collector ring (the top segment and
the adjoining ends of its neighbours) are cut with geo.cut_with_skin (red skins
`exhaust:section_skin_<part>`); the ring ends in two sectioned faces showing its
bore. Hardware seated in the region (clamps, bolts, nuts) is omitted.
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import geo, palette as P, spec as S
from lib.fasteners import _wrench_head

MATERIALS = ("heat_tint", "heat_tint_blue", "heat_tint_straw", "gasket", "fastener", "section_red")

# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------
PORT = (-80.0, 110.0, 468.0)                      # heads EXHAUST_FLANGE centre (cyl 1: x=t, z=h), face +y
STUDS_H = (430.0, 506.0)
GAMMA = math.degrees(math.atan2(-PORT[0], PORT[2]))   # in-plane angle of the port's radial plane
RHO_PORT = math.hypot(PORT[0], PORT[2])

Y_GASKET = (110.25, 111.0)                      # the heads' fin tips stand 0.2 proud of the face (t -90..-50)
Y_FLANGE = (111.0, 118.0)
FLANGE_SLOT = (76.0, 60.0)
STUD_HOLE_R = 4.5

STACK_RO, STACK_RI = 21.0, 19.5
Y_BEND = 120.0                                    # 2 mm straight off the flange, then the bend
BEND_A = 55.0                                     # stack turns outward by this much
BEND_R = 63.0                                     # its radius (1.5 D)

# ring centreline: set by the stack (bend, then STACK_FREE + STUB_L straight into the ring)
WALL = 1.5
SEG_R = (28.0, 30.0, 32.0, 34.0, 36.0)            # outer radius per segment, top -> bottom (0.5 slip)
SPIGOT = 20.0                                     # telescoping insertion (mm of arc)
STUB_L = 42.0                                     # stub end, from the ring centreline
STUB_RI = STACK_RO + 0.3
STUB_RO = STUB_RI + WALL
STACK_TIP = STUB_L - 14.0                         # stack end inside the stub
STACK_FREE = 2.0                                  # straight between the bend and the stub mouth

_A = math.radians(BEND_A)
RC = RHO_PORT + BEND_R * (1.0 - math.cos(_A)) + (STACK_FREE + STUB_L) * math.sin(_A)
YC = Y_BEND + BEND_R * math.sin(_A) + (STACK_FREE + STUB_L) * math.cos(_A)
OUT_STUB_RO, OUT_STUB_L = 26.0, 70.0          # 26: the tee with the Ø72 segment is BOP-sound (25 / 27 are not)
OUT_RI = OUT_STUB_RO + 0.5                         # Ø56 outlet pipe over a Ø52 stub
OUT_RO = OUT_RI + WALL
OUT_START = OUT_STUB_L - SPIGOT                   # outlet pipe start along the stub axis
OUT_END = (30.0, 420.0, -770.0)
OUT_END_DIR = (0.0, 0.6, -0.8)

CLAMP_W = 14.0
SEAM = (0.0, 1.0)                                 # torus circle seam (rho, y): rear, clear of every stub


# ---------------------------------------------------------------------------
# Small vector helpers
# ---------------------------------------------------------------------------
def _add(a, b, s=1.0):
    return (a[0] + s * b[0], a[1] + s * b[1], a[2] + s * b[2])


def _unit(a):
    n = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2)
    return (a[0] / n, a[1] / n, a[2] / n)


def rhat(b):
    r = math.radians(b)
    return (-math.sin(r), 0.0, math.cos(r))


def that(b):
    """Unit tangent of increasing in-plane angle b."""
    r = math.radians(b)
    return (-math.cos(r), 0.0, -math.sin(r))


def rp(rho, y, b):
    """Point at radius rho, station y, in-plane angle b."""
    u = rhat(b)
    return (rho * u[0], y, rho * u[2])


def rdir(drho, dy, b):
    u = rhat(b)
    return (drho * u[0], dy, drho * u[2])


def ring_b(phi):
    """In-plane angle of ring station phi (0 = top stub, +-180 = outlet)."""
    return GAMMA + phi


def V(p):
    return bd.Vector(*p)


def _one(shape):
    sols = shape.solids()
    if len(sols) != 1:
        sols = sorted(sols, key=lambda s: -s.volume)
    return sols[0]


def _fuse(items):
    items = list(items)
    out = items[0]
    if len(items) > 1:
        out = out.fuse(*items[1:])
    return out.clean()


def _cyl(p0, p1, r):
    return geo.cyl_along(p0, p1, 2.0 * r)


# ---------------------------------------------------------------------------
# The stack (cylinder 1; radial plane b = GAMMA, coordinates (rho, y))
# ---------------------------------------------------------------------------
_SA = math.radians(BEND_A)
_D = (-math.sin(_SA), -math.cos(_SA))             # stub axis (rho, y), from the ring toward the stack


def _stub_pt(s):
    return (RC + s * _D[0], YC + s * _D[1])


def _stack_edges():
    """Straight off the flange, one true circular bend of BEND_R through
    BEND_A, straight into the ring stub."""
    a = math.radians(BEND_A)
    arc = [(RHO_PORT + BEND_R * (1.0 + math.cos(math.pi - th)), Y_BEND + BEND_R * math.sin(th))
           for th in (0.0, a / 2.0, a)]
    p0, p1, pm, p2, p3 = [rp(r, y, GAMMA) for r, y in
                          [(RHO_PORT, Y_FLANGE[1])] + arc + [_stub_pt(STACK_TIP)]]
    line0 = bd.Edge.make_line(V(p0), V(p1))
    bend = bd.Edge.make_three_point_arc(V(p1), V(pm), V(p2))
    line2 = bd.Edge.make_line(V(p2), V(p3))
    return line0, bend, line2


def _tube_along(edges, ro, ri):
    path = bd.Wire(list(edges))
    p0, t0 = path @ 0.0, path % 0.0
    pl = bd.Plane(origin=p0, z_dir=t0)
    face = pl * (bd.Circle(ro) - bd.Circle(ri))
    return _one(bd.sweep(face, path=path, transition=bd.Transition.RIGHT))


def _flange_plate(y0, y1, bore_r):
    """The heads' slot outline between stations y0 < y1 (toward +y), stud holes, bore."""
    x, _, z = PORT
    pl = geo.plane((x, y0, z), z_dir=(0.0, 1.0, 0.0), x_dir=(1.0, 0.0, 0.0))
    sk = bd.SlotCenterToCenter(FLANGE_SLOT[0], FLANGE_SLOT[1], rotation=90.0)
    plate = bd.extrude(pl * sk, amount=abs(y1 - y0))
    holes = [_cyl((x, y0 - 1, h), (x, y1 + 1, h), STUD_HOLE_R) for h in STUDS_H]
    holes.append(_cyl((x, y0 - 1, z), (x, y1 + 1, z), bore_r))
    return _one(plate.cut(*holes))


def build_stack_proto():
    """[(name, shape, colour, seat_or_None)] for cylinder 1 (name uses {k})."""
    line0, spl, line2 = _stack_edges()
    # heat-tint bloom: blue at the port, straw through the bend, then the base
    blue = _tube_along([line0, spl.trim(0.0, 0.3)], STACK_RO, STACK_RI)
    straw = _tube_along([spl.trim(0.3, 0.65)], STACK_RO, STACK_RI)
    main = _tube_along([spl.trim(0.65, 1.0), line2], STACK_RO, STACK_RI)

    flange = _flange_plate(Y_FLANGE[0], Y_FLANGE[1], STACK_RI)
    ch = C.safe_chamfer(flange, [e for e in flange.edges()
                                 if abs(e.center().Y - Y_FLANGE[1]) < 0.05
                                 and math.hypot(e.center().X - PORT[0], e.center().Z - PORT[2]) > 30.0], 0.8)
    flange = ch[0] if isinstance(ch, tuple) else ch
    # weld bead where the tube leaves the flange face
    x, _, z = PORT
    bead = geo.locate(bd.Torus(STACK_RO, 2.2), (x, Y_FLANGE[1], z), (0.0, 1.0, 0.0))
    bead = bead - [_cyl((x, Y_FLANGE[1] - 5, z), (x, Y_FLANGE[1], z), 40.0),
                   _cyl((x, Y_FLANGE[1] - 1, z), (x, Y_FLANGE[1] + 6, z), STACK_RO)]
    flange = _one(_fuse([flange, bead]))
    gasket = _flange_plate(Y_GASKET[0], Y_GASKET[1], STACK_RI + 1.0)
    return [
        ("gasket_{k}", gasket, P.GASKET, None),
        ("stack_flange_{k}", flange, P.HEAT_TINT, None),
        ("stack_blue_{k}", blue, P.HEAT_TINT_BLUE, None),     # hottest, next to the port
        ("stack_band_{k}", straw, P.HEAT_TINT_STRAW, None),
        ("stack_{k}", main, P.HEAT_TINT, None),
    ]


# ---------------------------------------------------------------------------
# Band clamp: band axis local +Z, centred at the origin, ears toward local +X
# ---------------------------------------------------------------------------
EAR_T, EAR_GAP, EAR_OUT, EAR_R = 3.0, 6.0, 9.0, 6.0
BOLT_R, HOLE_R, AF = 2.4, 2.8, 8.0


def clamp_proto(rin):
    w = CLAMP_W
    band = bd.Cylinder(rin + 2.0, w) - bd.Cylinder(rin, w + 2)
    xc = rin + 2.0 + EAR_OUT
    ears = []
    for sgn in (1.0, -1.0):
        y0 = sgn * EAR_GAP / 2.0
        y1 = sgn * (EAR_GAP / 2.0 + EAR_T)
        ylo, yhi = min(y0, y1), max(y0, y1)
        box = bd.Pos((rin + 1.0 + xc) / 2.0, (ylo + yhi) / 2.0, 0.0) * bd.Box(xc - rin - 1.0, EAR_T, 2 * EAR_R)
        cap = geo.cyl_along((xc, ylo, 0.0), (xc, yhi, 0.0), 2 * EAR_R)
        ears += [box, cap]
    body = _fuse([band] + ears)
    body = body.cut(geo.cyl_along((xc, -20.0, 0.0), (xc, 20.0, 0.0), 2 * HOLE_R))
    body = _one(body)
    y_out = EAR_GAP / 2.0 + EAR_T
    # bolt: hex head bearing on the -y ear, shank through both ears
    head = _wrench_head(AF, 0.0, 3.5, chamfer_bottom=True, rotation=30.0)
    head = geo.locate(head, (xc, -y_out, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0))
    shank = geo.cyl_along((xc, -y_out - 0.5, 0.0), (xc, y_out + 5.5, 0.0), 2 * BOLT_R)
    bolt = _one(_fuse([head, shank]))
    nut = _wrench_head(AF, 0.0, 4.0, chamfer_bottom=True, rotation=30.0)
    nut = nut.cut(bd.Pos(0, 0, -1) * bd.Cylinder(BOLT_R + 0.1, 8.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    nut = geo.locate(_one(nut), (xc, y_out, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    return body, bolt, nut


def _place(shapes, origin, z_dir, x_dir):
    loc = geo.plane(origin, z_dir, x_dir).location
    return [loc * s for s in shapes]


# ---------------------------------------------------------------------------
# Ring segments (authored on the +phi side; the -phi side is the mirror)
# ---------------------------------------------------------------------------
def _disk_rev(r, phi0, phi1):
    """Solid torus section of tube radius r between stations phi0 < phi1."""
    b0 = ring_b(phi0)
    # circle seam on the rear-inner side of the tube, away from every stub
    pl = bd.Plane(origin=V(rp(RC, YC, b0)), x_dir=V(rdir(SEAM[0], SEAM[1], b0)), z_dir=V(that(b0)))
    face = pl * bd.Circle(r)
    return bd.revolve(face, axis=bd.Axis((0, 0, 0), (0, -1, 0)), revolution_arc=phi1 - phi0)


def _stub(phi, ro, ri, length, drho, dy):
    b = ring_b(phi)
    c = rp(RC, YC, b)
    d = _unit(rdir(drho, dy, b))
    return _cyl(c, _add(c, d, length), ro), _cyl(c, _add(c, d, length + 2.0), ri)


def _arc_deg(mm):
    return math.degrees(mm / RC)


def ring_segment(phi0, phi1, r, stubs=(), outlet=False):
    """Tube radius r over [phi0, phi1] (phi1 includes the spigot), with stack
    stubs at the listed stations; open ends; wall WALL."""
    outer = [_disk_rev(r, phi0, phi1)]
    inner = [_disk_rev(r - WALL, phi0 - 1.0, phi1 + 1.0)]
    for phi in stubs:
        o, i = _stub(phi, STUB_RO, STUB_RI, STUB_L, _D[0], _D[1])
        outer.append(o)
        inner.append(i)
    if outlet:
        o, i = _stub(180.0, OUT_STUB_RO, OUT_STUB_RO - WALL, OUT_STUB_L, 1.0, 0.0)
        outer.append(o)
        inner.append(i)
    body = _fuse(outer)
    return _one(body.cut(_fuse(inner)))


def _mirror_plane():
    """The ring's symmetry plane: contains the crank axis and the top stub."""
    return bd.Plane(origin=(0, 0, 0), z_dir=V(that(GAMMA)))


def _mirror(shape):
    return shape.mirror(_mirror_plane())


def ring_parts():
    """[(name, shape, colour)] in the engine frame."""
    sp = _arc_deg(SPIGOT)
    out = []
    # top: phi -20..20 plus a spigot at both ends (it feeds both halves)
    top = ring_segment(-20.0 - sp, 20.0 + sp, SEG_R[0], stubs=(0.0,))
    out.append(("collector_top", top, P.HEAT_TINT))
    # sides: phi 20-60, 60-100, 100-140, mouth at the start, spigot at the end
    for i, (a, b) in enumerate(((20.0, 60.0), (60.0, 100.0), (100.0, 140.0)), start=1):
        seg = ring_segment(a, b + sp, SEG_R[i], stubs=((a + b) / 2.0,))
        out.append((f"collector_l{i}", seg, P.HEAT_TINT))
        out.append((f"collector_r{i}", _mirror(seg), P.HEAT_TINT))
    # bottom: phi 140..220 with both mouths, stubs at 160 / 200 and the outlet tee
    bottom = ring_segment(140.0, 220.0, SEG_R[4], stubs=(160.0, 200.0), outlet=True)
    out.append(("collector_bottom", bottom, P.HEAT_TINT))
    return out


def ring_clamps():
    """[(name, shape, colour, seat)]: one band clamp over every segment mouth."""
    out = []
    n = 0
    for i, phi_j in enumerate((20.0, 60.0, 100.0, 140.0), start=1):
        r_down = SEG_R[i]
        body, bolt, nut = clamp_proto(r_down + 0.25)
        phi_c = phi_j + _arc_deg(1.0 + CLAMP_W / 2.0)
        for sgn in (1.0, -1.0):
            b = ring_b(sgn * phi_c)
            o = rp(RC, YC, b)
            z = that(b) if sgn > 0 else _add((0, 0, 0), that(b), -1.0)
            ear = _unit(_add(rhat(b), (0.0, 1.0, 0.0)))      # out and rear
            n += 1
            b_, bo_, nu_ = _place([body, bolt, nut], o, z, ear)
            out += [(f"clamp_ring_{n}", b_, P.HEAT_TINT_STRAW, o),
                    (f"clamp_ring_bolt_{n}", bo_, P.FASTENER, o),
                    (f"clamp_ring_nut_{n}", nu_, P.FASTENER, o)]
    return out


# ---------------------------------------------------------------------------
# Outlet
# ---------------------------------------------------------------------------
def outlet_parts():
    b = ring_b(180.0)
    u = rhat(b)
    c = rp(RC, YC, b)
    pa = _add(c, u, OUT_START)
    pb = _add(c, u, OUT_STUB_L + 30.0)
    e0 = bd.Edge.make_line(V(pa), V(pb))
    e1 = bd.Edge.make_spline([V(pb), V(OUT_END)], tangents=[V(u), V(_unit(OUT_END_DIR))], scale=True)
    pipe = _tube_along([e0, e1], OUT_RO, OUT_RI)
    # tail flange (tailpipe / heater-muff joint): 6 holes on PCD 72
    t = _unit(OUT_END_DIR)
    fl = bd.Cylinder(44.0, 6.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)) \
        - bd.Cylinder(OUT_RI, 20.0)
    holes = [bd.Pos(36.0 * math.cos(math.radians(30 + 60 * j)), 36.0 * math.sin(math.radians(30 + 60 * j)), 0.0)
             * bd.Cylinder(3.5, 20.0) for j in range(6)]
    fl = fl.cut(*holes)
    fl = geo.locate(fl, OUT_END, t)
    fl = fl.translate(V(_add((0, 0, 0), t, -6.0)))
    pipe = _one(_fuse([pipe, fl]))
    body, bolt, nut = clamp_proto(OUT_RO + 0.25)
    o = _add(c, u, OUT_START + 1.0 + CLAMP_W / 2.0)
    ear = (0.0, 1.0, 0.0)
    parts = [("collector_outlet", pipe, P.HEAT_TINT)]
    b_, bo_, nu_ = _place([body, bolt, nut], o, u, ear)
    parts += [("clamp_outlet", b_, P.HEAT_TINT_STRAW), ("clamp_outlet_bolt", bo_, P.FASTENER),
              ("clamp_outlet_nut", nu_, P.FASTENER)]
    return parts


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def _section(name, shape, colour, seat, out):
    """Cylinder 1's museum cut: omit hardware seated in the region, cut the rest
    with a red skin on every cut face."""
    if seat is not None:
        if not geo.in_section(seat):
            out.append(P.style(shape, "exhaust:" + name, colour))
        return
    hit = shape & geo.section_cutter()
    if hit is None or not hit.solids():
        # bounding boxes may meet with no real intersection; geo.cut_with_skin
        # then finds no skin (None) and fails on it, so keep such parts whole
        out.append(P.style(shape, "exhaust:" + name, colour))
        return
    kept, skin = geo.cut_with_skin(shape, "section")
    if kept is not None and kept.solids():  # None: wholly removed
        sols = kept.solids()
        kept = sols[0] if len(sols) == 1 else bd.Compound(children=list(sols))
        out.append(P.style(kept, "exhaust:" + name, colour))
    if skin is not None:
        sols = skin.solids()
        skin = sols[0] if len(sols) == 1 else bd.Compound(children=list(sols))
        out.append(P.style(skin, "exhaust:section_skin_" + name, P.SECTION_RED))


def build():
    parts = []
    protos = build_stack_proto()
    for k in range(1, S.N_CYL + 1):
        for name, shape, colour, seat in protos:
            if k == geo.SECTION_CYL:
                _section(name.format(k=k), shape, colour, seat, parts)
            else:
                parts.append(P.style(geo.on_cylinder(shape, k), "exhaust:" + name.format(k=k), colour))
    for name, shape, colour in ring_parts() + outlet_parts():
        _section(name, shape, colour, None, parts)
    for name, shape, colour, seat in ring_clamps():
        _section(name, shape, colour, seat, parts)
    return parts
