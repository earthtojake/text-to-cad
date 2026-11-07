"""The routes of Orbit's board, planned as geometry, then written by board.py's route stage.

Everything here is millimetres relative to the board's centre (geometry.CX, CY), y down, as geometry.py.
`plan(board)` reads the placed board (kicad_pcb.read) for every pad and returns a Plan: tracks (polylines),
arcs and vias, each with its net, layer and width.

- The LED chain: one arc per link (DOUT of one LED to DIN of the next), from the pads' own positions.
- Each LED's power: VDD pad to its capacitor's +5V pad, a via under each capacitor pad to the planes, and a
  GND via outside the ring at its VSS pad. A via that would collide with a back-side pad, a back track or the
  antenna keep-out is moved along the ring; a GND via that cannot be placed is left out (the GND pours on F.Cu
  and B.Cu reach that pad), a +5V via that cannot be placed fails the plan.
- The back: hand-planned polylines between pads (BACK_ROUTES), each named by the pads it joins.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import geometry as G

CL = G.CLEARANCE + 0.02      # the clearance the planner keeps (DRC checks G.CLEARANCE)
VR = G.VIA_D / 2


@dataclass
class Plan:
    tracks: list = field(default_factory=list)   # (net, layer, width, [(x, y), ...])
    arcs: list = field(default_factory=list)     # (net, layer, width, start, mid, end)
    vias: list = field(default_factory=list)     # (net, (x, y))
    dropped: list = field(default_factory=list)  # (what, net, (x, y), why)
    moved: list = field(default_factory=list)

    def track(self, net, layer, width, *pts):
        self.tracks.append((net, layer, width, [tuple(p) for p in pts]))

    def via(self, net, at):
        self.vias.append((net, tuple(at)))


def rel(p):
    return (p[0] - G.CX, p[1] - G.CY)


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1)
    t = max(0.0, min(1.0, t))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy))


def poly_dist(p, poly):
    """Distance from p to a closed polygon (0 inside)."""
    inside = False
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x > p[0]:
                inside = not inside
    if inside:
        return 0.0
    return min(seg_dist(p, poly[i], poly[(i + 1) % n]) for i in range(n))


def arc_points(start, mid, end, n=24):
    """Points along the circular arc through start, mid, end."""
    (x1, y1), (x2, y2), (x3, y3) = start, mid, end
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    r = math.dist((ux, uy), start)
    a1, a2, a3 = (math.atan2(p[1] - uy, p[0] - ux) for p in (start, mid, end))

    def between(a, b, c):  # is b on the way from a to c going counter-clockwise (math sense)?
        return (b - a) % (2 * math.pi) < (c - a) % (2 * math.pi)
    sweep = (a3 - a1) % (2 * math.pi)
    if not between(a1, a2, a3):
        sweep -= 2 * math.pi
    return [(ux + r * math.cos(a1 + sweep * i / n), uy + r * math.sin(a1 + sweep * i / n)) for i in range(n + 1)]


class Board:
    """The placed board, read back: pads by (ref, number), relative to the centre."""

    def __init__(self, board):
        self.b = board
        self.pads = []                       # (ref, number, net, side, polygon, drill)
        self.by = {}
        for part in board.parts:
            for pad in part.pads:
                poly = [rel(q) for q in pad.polygon] if pad.polygon else []
                item = (part.ref, pad.number, pad.net, pad.side, poly, pad.drill)
                self.pads.append(item)
                self.by.setdefault((part.ref, pad.number), []).append(rel(pad.at))
        self.holes = [(rel(h.at), h.diameter / 2) for h in board.holes] if board.holes else []
        for part in board.parts:      # plated holes too (the module's thermal vias, the receptacle's tabs)
            for pad in part.pads:
                if pad.drill:
                    d = pad.drill if isinstance(pad.drill, (int, float)) else max(pad.drill)
                    if part.ref == "J1" and pad.number == "SH":
                        d = 1.7   # the shell's slots are 0.6 x 1.7 mm; the reader gives their width alone
                    self.holes.append((rel(pad.at), d / 2))

    def P(self, ref, number, near=None):
        """A pad's centre; of several pads of one number, the one nearest `near` (an index or a point)."""
        pads = self.by[(ref, number)]
        if near is None:
            return pads[0]
        if isinstance(near, int):
            return pads[near]
        return min(pads, key=lambda q: math.dist(q, near))


# ------------------------------------------------------------------------------------------ the rings

def ring(index, count, radius):
    deg = G.led_angle(index, count)
    return deg, G.polar(radius, deg)


def chain_links(bd: Board, plan: Plan):
    """DOUT of each LED to DIN of the next as one arc, the two rings joined by a hop near 12 o'clock."""
    for first, count, radius in ((1, G.N_MINUTE, G.R_MINUTE), (G.N_MINUTE + 1, G.N_HOUR, G.R_HOUR)):
        for i in range(count - 1):
            a, b = f"D{first + i}", f"D{first + i + 1}"
            start, end = bd.P(a, "1"), bd.P(b, "3")
            deg_mid = G.led_angle(i + 0.5, count)
            mid = G.polar(radius, deg_mid)
            plan.arcs.append((net_of(bd, a, "1"), "F.Cu", G.SIGNAL, start, mid, end))


def net_of(bd, ref, number):
    for r, n, net, *_ in bd.pads:
        if r == ref and n == number:
            return net
    raise KeyError((ref, number))


def obstacles_hit(bd: Board, plan: Plan, p, net, radius, layers, skip_refs=()):
    """What a round object of `radius` at p on `layers` ("F", "B" or both) would touch: [] when clear."""
    hits = []
    for ref, number, pnet, side, poly, drill in bd.pads:
        if ref in skip_refs or not poly:
            continue
        on = {"top": {"F"}, "bottom": {"B"}, "both": {"F", "B"}}.get(side, {"F", "B"})
        if not (on & layers):
            continue
        if pnet == net:
            continue
        if poly_dist(p, poly) < radius + CL:
            hits.append(f"{ref}.{number}")
    for at, r in bd.holes:
        if math.dist(p, at) < radius + r + 0.3:
            hits.append("hole")
    for tnet, layer, width, pts in plan.tracks:
        if layer[0] not in layers or tnet == net:
            continue
        for a, b in zip(pts, pts[1:]):
            if seg_dist(p, a, b) < radius + width / 2 + CL:
                hits.append(f"track:{tnet}")
                break
    for anet, layer, width, s, m, e in plan.arcs:
        if layer[0] not in layers or anet == net:
            continue
        pts = arc_points(s, m, e, 12)
        if any(seg_dist(p, a, b) < radius + width / 2 + CL for a, b in zip(pts, pts[1:])):
            hits.append(f"arc:{anet}")
    for vnet, at in plan.vias:
        if math.dist(p, at) < radius + VR + (CL if vnet != net else 0.3):
            hits.append(f"via:{vnet}")
    # The antenna keep-out (the module's rule area), and the board's edge
    if -11.4 - radius < p[0] < 16.6 + radius and p[1] < -52.7 + radius:
        hits.append("antenna keep-out")
    if math.hypot(*p) > G.R_BOARD - G.EDGE_CLEARANCE - radius or p[1] > G.FLAT_Y - G.EDGE_CLEARANCE - radius:
        hits.append("edge")
    return hits


def place_via(bd, plan, net, ideal, frm, deg, what, skip, required):
    """A via as near `ideal` as is clear, joined to the pad at `frm` by a track on F.Cu; along the ring first."""
    t = (math.cos(math.radians(deg)), math.sin(math.radians(deg)))
    u = (math.sin(math.radians(deg)), -math.cos(math.radians(deg)))
    tries = [(0, 0)] + [(s * k, 0) for k in (0.4, 0.8, 1.2, 1.6, 2.0, 2.4) for s in (1, -1)] + \
            [(s * k, r) for r in (-0.6, 0.6, -1.2) for k in (0, 0.6, 1.2) for s in (1, -1)]
    for dt, du in tries:
        p = (ideal[0] + dt * t[0] + du * u[0], ideal[1] + dt * t[1] + du * u[1])
        if obstacles_hit(bd, plan, p, net, VR, {"F", "B"}, skip):
            continue
        # the joining track, sampled
        clear = True
        for k in range(1, 6):
            q = (frm[0] + (p[0] - frm[0]) * k / 6, frm[1] + (p[1] - frm[1]) * k / 6)
            if obstacles_hit(bd, plan, q, net, G.SIGNAL / 2 + 0.05, {"F"}, skip):
                clear = False
                break
        if not clear:
            continue
        if (dt, du) != (0, 0):
            plan.moved.append((what, net, p))
        plan.via(net, p)
        plan.track(net, "F.Cu", 0.25, frm, p)
        return p
    why = obstacles_hit(bd, plan, ideal, net, VR, {"F", "B"}, skip)
    if required:
        raise SystemExit(f"no room for {what} ({net}) near {ideal}: {why}")
    plan.dropped.append((what, net, ideal, why))
    return None


def feed_from_neighbour(bd, plan, led, cap, i, count, radius, placed):
    """A +5V capacitor pad with no room for a via of its own, fed on F.Cu from a neighbour's +5V via: in along
    the neighbour's radius to a path inside the capacitors, an arc along it, and out to the pad."""
    deg, _ = ring(i, count, radius)
    pad = bd.P(cap, "1")
    r_path = radius + G.VDD_VIA_LOCAL[1] - 0.9
    for j in ((i + 1) % count, (i - 1) % count):
        via = placed.get((count, j))
        if via is None:
            continue
        a_via = math.degrees(math.atan2(via[0], -via[1]))
        a_pad = math.degrees(math.atan2(pad[0], -pad[1]))
        p1, p3 = G.polar(r_path, a_via), G.polar(r_path, a_pad)
        p2 = G.polar(r_path, (a_via + a_pad) / 2)
        trial = Plan(tracks=list(plan.tracks), arcs=list(plan.arcs), vias=list(plan.vias))
        pts = [via, p1] + arc_points(p1, p2, p3, 8) + [pad]
        if all(not obstacles_hit(bd, trial, q, "+5V", 0.15 + 0.02, {"F"}) for q in pts[1:-1]):
            plan.track("+5V", "F.Cu", 0.3, via, p1)
            plan.arcs.append(("+5V", "F.Cu", 0.3, p1, p2, p3))
            plan.track("+5V", "F.Cu", 0.3, p3, pad)
            plan.moved.append((f"{led} +5V from its neighbour's via", "+5V", via))
            return True
    raise SystemExit(f"no room for {led}'s +5V, nor a neighbour to feed it")


def led_power(bd: Board, plan: Plan):
    leds = [(f"D{i + 1}", f"C{101 + i}", i, G.N_MINUTE, G.R_MINUTE) for i in range(G.N_MINUTE)] + \
           [(f"D{G.N_MINUTE + i + 1}", f"C{101 + G.N_MINUTE + i}", i, G.N_HOUR, G.R_HOUR) for i in range(G.N_HOUR)]
    placed, starved = {}, []
    for led, cap, i, count, radius in leds:
        deg, center = ring(i, count, radius)
        vdd, vss = bd.P(led, "4"), bd.P(led, "2")
        c5, cg = bd.P(cap, "1"), bd.P(cap, "2")
        plan.track("+5V", "F.Cu", 0.3, vdd, c5)
        skip = ()
        at = place_via(bd, plan, "+5V", G.local_to_board(G.VDD_VIA_LOCAL, center, deg), c5, deg,
                       f"{led} +5V via", skip, required=False)
        if at is None:  # under the module's lanes: a +5V via in the gap before this LED, inside the chain
            plan.dropped.pop()
            gap = G.polar(radius - 1.5, deg - 180.0 / count)
            at = place_via(bd, plan, "+5V", gap, vdd, deg, f"{led} +5V via (in the gap)", skip, required=False)
            if at is None:
                plan.dropped.pop()
                starved.append((led, cap, i, count, radius))
                continue
        placed[(count, i)] = at
        place_via(bd, plan, "GND", G.local_to_board(G.GND_VIA_LOCAL, center, deg), cg, deg, f"{led} GND via",
                  skip, required=False)
        place_via(bd, plan, "GND", G.local_to_board(G.VSS_VIA_LOCAL, center, deg), vss, deg, f"{led} VSS via",
                  skip, required=False)
    for args in starved:
        feed_from_neighbour(bd, plan, *args, placed)


# ------------------------------------------------------------------------------------------ the rest, by hand

# Lanes: the module's two pad rows fan out under its body (inward) or beside it (outward), each pad's track
# turning down at its own x, the upper pad on the outer lane, so no two cross.
LANE_RIGHT = {"1": 3.6, "2": 4.2, "3": 4.8, "4": 5.4, "5": 6.0, "7": 6.6, "8": 7.2}   # inward, x of each lane
LANE_LEFT_OUT = {"15": -9.8, "14": -9.25, "13": -8.85}                               # CC2, D+, D- outward
LANE_LEFT_IN = {"16": -3.6, "12": -4.2, "11": -4.8}                                  # IO2, TX, RX inward

VBUS_W, POWER_W, V33_W = 1.0, 0.8, 0.3


def hand_routes(bd: Board, plan: Plan):
    P = bd.P
    B, F = "B.Cu", "F.Cu"
    S = G.SIGNAL
    net = lambda ref, n: net_of(bd, ref, n)  # noqa: E731

    # --- USB: D+, D- and CC2 down the left, CC1 down the right, to the ESD array and the receptacle
    dp, dm, cc2 = net("U1", "14"), net("U1", "13"), net("U1", "15")
    cc1 = net("U1", "3")
    for pin, (lane_x, y_h) in {"13": (LANE_LEFT_OUT["13"], 39.6), "14": (LANE_LEFT_OUT["14"], 40.2),
                               "15": (LANE_LEFT_OUT["15"], 40.8)}.items():
        pad = P("U1", pin)
        end = {"13": P("U3", "6"), "14": P("U3", "4"), "15": (-1.75, 50.9)}[pin]
        plan.track(net("U1", pin), B, S, pad, (lane_x, pad[1]), (lane_x, y_h - 5.0), (lane_x + 5.0, y_h),
                   (end[0], y_h), end)
    plan.track(cc2, B, S, (-1.75, 50.9), P("J1", "B5"))
    plan.track(cc2, B, S, (LANE_LEFT_OUT["15"], P("R2", "1")[1]), P("R2", "1"))           # CC2's 5.1k
    # the receptacle: B6 and A6 (D+) joined under the pads, A7 and B7 (D-) above them
    plan.track(dp, B, S, P("J1", "A6"), (0.25, 53.0), (-0.75, 53.0), P("J1", "B6"))
    plan.track(dp, B, S, P("J1", "B6"), (-0.75, 45.6), (-0.95, 45.4), P("U3", "3"))
    plan.track(dm, B, S, P("J1", "A7"), (-0.25, 50.9), (0.75, 50.9), P("J1", "B7"))
    plan.track(dm, B, S, (0.75, 50.9), (0.75, 45.6), (0.95, 45.4), P("U3", "1"))
    # CC1: the right lane, its 5.1k, down past the ESD array to A5
    lane = LANE_RIGHT["3"]
    plan.track(cc1, B, S, P("U1", "3"), (lane, P("U1", "3")[1]), (lane, 36.0), (1.75, 39.05), (1.75, 47.1),
               (1.25, 47.6), P("J1", "A5"))
    plan.track(cc1, B, S, (lane, P("R1", "1")[1]), P("R1", "1"))
    # the ESD array's +5V and GND
    plan.track(dm, B, S, P("U3", "1"), P("U3", "6"))   # flow-through: each line under the body, pad to pad
    plan.track(dp, B, S, P("U3", "3"), P("U3", "4"))
    plan.track("+5V", B, S, P("U3", "5"), (0.0, 40.6))
    plan.via("+5V", (0.0, 40.6))
    plan.track("GND", B, S, P("U3", "2"), (0.0, 45.5))
    plan.via("GND", (0.0, 45.5))

    # --- VBUS: both receptacle pads, bridged on F.Cu, into the polyfuse; +5V out of it into In2
    for x in (-2.4, 2.4):
        plan.track("VBUS", B, 0.6, P("J1", "A9" if x < 0 else "A4"), (x, 50.85))
        plan.via("VBUS", (x, 50.85))
    plan.track("VBUS", F, POWER_W, (-2.4, 50.85), (-2.4, 51.85), (2.4, 51.85), (2.4, 50.85))
    plan.track("VBUS", B, 0.6, (-2.4, 50.85), (-3.3, 50.45))
    plan.track("VBUS", B, VBUS_W, (-3.3, 50.45), (-5.4, 50.45), (-6.6, 51.65), P("F1", "1"))
    plan.track("+5V", B, VBUS_W, P("F1", "2"), (-10.7, 52.6))
    plan.track("+5V", B, VBUS_W, P("F1", "2"), (-10.7, 54.6))
    plan.via("+5V", (-10.7, 52.6))
    plan.via("+5V", (-10.7, 54.6))
    for x in (-3.2, 3.2):   # the receptacle's GND pads to its shield tabs
        plan.track("GND", B, 0.3, (x, 52.4), (4.32 if x > 0 else -4.32, 52.62))

    # --- the module's right row: inward lanes; LED data and GND outward
    for pin, lane in LANE_RIGHT.items():
        pad = P("U1", pin)
        width = V33_W if pin == "1" else S
        ends = {"1": (lane, -28.05), "2": (lane, -33.0), "3": None, "4": (lane, -6.0), "5": (lane, -5.0),
                "7": (lane, -33.6), "8": (lane, -34.5)}
        if ends[pin] is None:
            continue
        plan.track(net("U1", pin), B, width, pad, (lane, pad[1]), ends[pin])
    plan.track("+3V3", B, V33_W, P("U1", "1"), P("C6", "1"))
    plan.track("GND", B, S, P("U1", "9"), (9.6, -39.6))
    plan.via("GND", (9.6, -39.6))
    plan.track("GND", B, S, P("C6", "2"), (14.73, -50.3))
    plan.via("GND", (14.73, -50.3))
    en, sda, scl, io8, boot = (net("U1", n) for n in ("2", "4", "5", "7", "8"))
    plan.via(en, (LANE_RIGHT["2"], -33.0))
    plan.via(sda, (LANE_RIGHT["4"], -6.0))
    plan.via(scl, (LANE_RIGHT["5"], -5.0))
    plan.via(io8, (LANE_RIGHT["7"], -33.6))
    plan.track(boot, B, S, (LANE_RIGHT["8"], -34.5), (9.0, -32.3), (11.35, -29.95), P("SW1", "1", (11.0, -26.0)))
    plan.via(boot, (9.0, -32.3))
    # LED data out of IO7, through the 74AHCT1G125 and 33 ohm, to the front
    data3, data5 = net("U1", "6"), net("U4", "4")
    din = net("R7", "2")
    plan.track(data3, B, S, P("U1", "6"), (12.9, -44.1), (12.9, -38.6), P("U4", "2"))
    plan.track(data5, B, S, P("U4", "4"), (16.14, -40.4), (16.08, -40.6), P("R7", "1"))
    plan.track(din, B, S, P("R7", "2"), (18.75, -41.6))
    plan.via(din, (18.75, -41.6))
    plan.track("GND", B, S, P("U4", "1"), (13.86, -36.45))
    plan.via("GND", (13.86, -36.45))
    plan.track("GND", B, S, P("U4", "3"), (14.75, -39.55), (15.0, -39.3), (15.0, -37.9), (14.75, -37.65),
               P("U4", "1"))   # pin 3 to pin 1 under the body, pin 1's via for both
    plan.track("+5V", B, 0.4, P("U4", "5"), P("C8", "1"))
    plan.track("+5V", B, 0.4, P("U4", "5"), (16.14, -36.4))
    plan.via("+5V", (16.14, -36.4))
    plan.track("GND", B, S, P("C8", "2"), (19.3, -36.0))
    plan.via("GND", (19.3, -36.0))

    # --- the module's left row: UART to its test points, IO2 to its pull-up
    for pin, lane in LANE_LEFT_IN.items():
        pad = P("U1", pin)
        if pin == "16":
            plan.track(net("U1", pin), B, S, pad, (lane, pad[1]), (lane, -36.0), P("R5", "2"))
        elif pin == "12":   # TX, turning left below RX
            plan.track(net("U1", pin), B, S, pad, (lane, pad[1]), (lane, -35.6), (-5.6, -35.6), P("TP4", "1"))
        else:               # RX, the outer of the two, turning first
            plan.track(net("U1", pin), B, S, pad, (lane, pad[1]), (lane, P("TP5", "1")[1]), P("TP5", "1"))

    # --- 3.3 V: the regulator below the module, its capacitors, the module's lane, the front's two feeds
    plan.track("+3V3", B, V33_W, P("U2", "5"), (LANE_RIGHT["1"], -28.05))
    plan.track("+3V3", B, V33_W, P("U2", "5"), (1.14, -26.6), (1.82, -25.92), P("C4", "1"))
    plan.via("+3V3", (1.14, -26.6))
    plan.track("+3V3", B, V33_W, P("C4", "1"), (0.82, -24.0), P("C5", "1"))
    plan.track("+3V3", B, V33_W, P("C5", "1"), (-1.2, -23.45), P("TP2", "1"), (-1.2, -8.0))
    plan.via("+3V3", (-1.2, -8.0))
    plan.track("+3V3", B, 0.25, (LANE_RIGHT["1"], -32.4), P("R5", "1"))
    plan.track("+5V", B, 0.4, P("U2", "1"), P("C3", "1"))
    plan.track("+5V", B, 0.4, P("C3", "1"), (-3.4, -30.2))
    plan.track("+5V", B, 0.4, P("U2", "3"), (-2.4, -30.2), (-3.4, -30.2))
    plan.via("+5V", (-3.4, -30.2))
    plan.track("GND", B, S, P("U2", "2"), (1.7, -29.0), (2.3, -28.95))
    plan.via("GND", (2.3, -28.95))
    for ref, at in (("C3", (-4.6, -27.22)), ("C4", (3.38, -23.7)), ("C5", (-2.55, -22.7))):
        plan.track("GND", B, S, P(ref, "2"), at)
        plan.via("GND", at)

    # --- EN: its lane to the front (the pull-up), across the front to the RESET switch and its 1 uF
    plan.track(en, F, S, (LANE_RIGHT["2"], -33.0), (3.4, -32.2), P("R3", "2"))
    plan.track(en, F, S, (LANE_RIGHT["2"], -33.0), (-3.5, -33.0), (-11.0, -25.5))
    plan.via(en, (-11.0, -25.5))
    plan.track(en, B, S, (-11.0, -25.5), (-11.0, -24.6), P("SW2", "1", (-12.0, -24.0)))
    plan.track(en, B, S, (-11.0, -25.5), P("C7", "1"))
    plan.track(io8, F, S, (LANE_RIGHT["7"], -33.6), (7.2, -33.0), P("R6", "2"))
    plan.track(boot, F, S, (9.0, -32.3), P("R4", "2"))
    # the front's 3.3 V bus for the three pull-ups
    plan.track("+3V3", F, V33_W, (1.14, -26.6), (1.14, -27.6), (10.5, -27.6))
    for ref in ("R3", "R6", "R4"):
        plan.track("+3V3", F, V33_W, (P(ref, "1")[0], -27.6), P(ref, "1"))

    # --- the light sensor on the front, its bus from the two vias, its 3.3 V from the third
    sx = P("C9", "1")[0]
    plan.track("+3V3", F, V33_W, (-1.2, -8.0), (sx, -7.075), (sx, 2.8), P("R9", "1"))
    plan.track("+3V3", F, V33_W, (sx, -3.0), P("R8", "1"))
    plan.track("+3V3", F, 0.25, P("C9", "1"), P("U5", "1"))
    plan.track(sda, F, S, (LANE_RIGHT["4"], -6.0), (3.4, -4.0), (3.4, -3.0), (3.4, -1.4), (2.65, -0.65),
               P("U5", "6"))
    plan.track(sda, F, S, P("R8", "2"), (3.4, -3.0))
    plan.track(scl, F, S, (LANE_RIGHT["5"], -5.0), (4.6, -3.6), (4.6, 2.8), P("R9", "2"))
    plan.track(scl, F, S, P("R9", "2"), (1.83, 1.58), P("U5", "4"))
    plan.track("GND", F, S, P("U5", "3"), (-0.6, 1.7))
    plan.via("GND", (-0.6, 1.7))
    gx = P("C9", "2")[0]
    plan.track("GND", F, S, P("C9", "2"), P("C10", "2"))
    plan.track("GND", F, S, P("C9", "2"), (gx - 0.9, -1.45))
    plan.via("GND", (gx - 0.9, -1.45))

    # --- the chain's input and its hop between the rings, on the front
    a = math.degrees(math.atan2(18.75, 41.6))
    start, mid, end = G.polar(43.5, a), G.polar(43.5, (a - 3.0) / 2), G.polar(43.5, -3.0)
    plan.track(din, F, S, (18.75, -41.6), start)
    plan.arcs.append((din, F, S, start, mid, end))
    d1 = P("D1", "3")
    plan.track(din, F, S, end, (end[0], d1[1] + 0.58), (end[0] + 0.58, d1[1]), d1)
    d60, d61 = P(f"D{G.N_MINUTE}", "1"), P(f"D{G.N_MINUTE + 1}", "3")
    hop = net_of(bd, f"D{G.N_MINUTE}", "1")
    plan.track(hop, F, S, d60, (-3.4, d60[1]), (-3.4, d61[1] - 1.65), (d61[0] - 0.835, d61[1]), d61)
    dout = P(f"D{G.N_MINUTE + G.N_HOUR}", "1")
    last = G.led_angle(G.N_HOUR - 1, G.N_HOUR)
    plan.track(net_of(bd, f"D{G.N_MINUTE + G.N_HOUR}", "1"), F, S, dout,
               G.polar(G.R_HOUR - 0.55, last + 4.0), G.polar(G.R_HOUR - 4.5, last + 5.5), P("TP6", "1"))

    # --- +5V and GND vias at the rest of the back's pads
    pads5 = [("C1", "1", (0, 2.3)), ("C1", "1", (0, -2.3)), ("C2", "1", (0, 1.6)), ("TP1", "1", (0, 1.6))]
    padsg = [("C1", "2", (0, 2.3)), ("C1", "2", (0, -2.3)), ("C2", "2", (0, 1.6)), ("TP3", "1", (0, 1.6)),
             ("R1", "2", (0, 1.2)), ("R2", "2", (0, 1.2)), ("C7", "2", (0, -1.3))]
    for ref, n, (dx, dy) in pads5 + padsg:
        p = P(ref, n)
        q = (p[0] + dx, p[1] + dy)
        name = net_of(bd, ref, n)
        plan.track(name, B, 0.4, p, q)
        plan.via(name, q)
    for ref in ("SW1", "SW2"):   # each switch's two pads of one number joined under its body
        for n in ("1", "2"):
            plan.track(net_of(bd, ref, n), B, S, P(ref, n, 0), P(ref, n, 1))
        for k in (0, 1):
            p = P(ref, "2", k)
            q = (p[0], p[1] + 1.4)
            plan.track("GND", B, 0.4, p, q)
            plan.via("GND", q)


def plan(board):
    bd = Board(board)
    pl = Plan()
    hand_routes(bd, pl)
    chain_links(bd, pl)
    led_power(bd, pl)
    return bd, pl
