# /// script
# dependencies = ["shapely>=2", "scipy"]
# ///
"""SHORT CIRCUIT's playfield, its routes as geometry: read the placed board, plan every track and via, write
tmp/routes.json, which `board.py route` turns into KiCad's tracks and vias.

Planned, not hand-drawn: 130 nets over a 112 x 236 mm board (the pcb skill routes by hand; a board this size asked
for a script). Everything the skill asks of a route still holds: tracks octolinear on a 0.1 mm grid, widths from
each net's current (`WIDTH`), one via per ground pad straight down to the In1 plane, the RP2040's pads fanned out
along fixed stubs. A net is grown as a tree: its pads joined to what is already connected, nearest first (A*, on
B.Cu and In2.Cu, a via costing what 2.5 mm of track costs, each 45 degree bend 0.2 mm), every step at its width and
JLCPCB's clearance from all other copper. Nets that find no way go first on the next pass.
"""
from __future__ import annotations

import heapq
import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402
from cad import kicad_pcb  # noqa: E402
from scipy import ndimage  # noqa: E402
from shapely import contains_xy  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import geometry as G  # noqa: E402

L = G.L
P = G.P
BOARD = G.PROJECT / "pinball.kicad_pcb"
OUT = G.PROJECT / "tmp" / "routes.json"

CELL = 0.1
CL = G.CLEARANCE
INFLATE = 0.071                   # every obstacle is stamped this much larger: half a cell's diagonal, so no edge hides between cells
MARGIN = 0.03                     # a raster's error: copper's edge lies up to this past its last cell
VR = G.VIA_D / 2
NARROW = 0.15                     # tracks inside U1's fan-out
U1_R = 8.6                        # ... within this radius of its centre
VIA_FREE_R = 6.0                  # no via this close to U1's centre (the fan-out needs the room)
PORT_R0, PORT_STAGGER, PORT_R = 4.2, 0.1, 8.0   # U1's fan-out: lanes turn from R0, a stagger apart, ports at R
CORRIDOR_R = 11.0                 # ... and no other net crosses in front of a port until this far from the centre
NECK, NECK_R = 0.3, 1.6           # a wide track necks to this, within this of its pads
FINE_PITCH = {"U8", "U9", "J1", "U3", "U2"}
POWER_PINS = {n for _, pins, *_ in G.U1_POWER for n in pins}
POWER_CAPS = {e[4] for e in G.U1_POWER}
HAND = {"/Power/USB_D+", "/Power/USB_D-", "Net-(U1-USB_DM)", "Net-(U1-USB_DP)", "+1V1"}   # routed by hand below
RAILS = {"+3V3", "+1V1"}
WIDTH = {"+9V": 1.0, "VBUS": 1.0, "+5V": 0.6, "+3V3": 0.3, "+1V1": 0.3, "GND": 0.3}
LAYERS = ("B.Cu", "In2.Cu")       # routing layers (F.Cu holds the art, In1.Cu is the ground plane)

GREED = 1.4                       # A*'s weight on the distance to go: near-shortest paths, far fewer cells searched
Dirs = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def off_pad(poly, at):
    """The least distance from a pad's centre at which a via clears the whole pad."""
    return max(math.dist(at, c) for c in poly.exterior.coords) + VR + 0.02


class Grid:
    def __init__(self):
        self.x0, self.y0 = G.ORIGIN[0] - 1.0, G.ORIGIN[1] - 1.0
        self.nx = int((L.BOARD_W + 2.0) / CELL) + 1
        self.ny = int((L.BOARD_L + 2.0) / CELL) + 1
        self.layers = ("F.Cu", "B.Cu", "In2.Cu")
        self.occ = {name: np.full((self.ny, self.nx), -1, dtype=np.int32) for name in self.layers}
        self.xs = self.x0 + CELL * np.arange(self.nx)
        self.ys = self.y0 + CELL * np.arange(self.ny)

    def ij(self, x, y):
        return (int(round((y - self.y0) / CELL)), int(round((x - self.x0) / CELL)))

    def xy(self, i, j):
        return (self.x0 + j * CELL, self.y0 + i * CELL)

    def stamp_poly(self, layer, polygon: Polygon, net):
        polygon = polygon.buffer(INFLATE, quad_segs=4)
        minx, miny, maxx, maxy = polygon.bounds
        i0, j0 = self.ij(minx, miny)
        i1, j1 = self.ij(maxx, maxy)
        i0, j0, i1, j1 = max(i0 - 1, 0), max(j0 - 1, 0), min(i1 + 2, self.ny), min(j1 + 2, self.nx)
        if i0 >= i1 or j0 >= j1:
            return
        xx, yy = np.meshgrid(self.xs[j0:j1], self.ys[i0:i1])
        mask = contains_xy(polygon, xx, yy)
        view = self.occ[layer][i0:i1, j0:j1]
        view[mask] = net

    def stamp_disc(self, layer, x, y, r, net):
        r += INFLATE
        n = int(math.ceil(r / CELL)) + 1
        ci, cj = self.ij(x, y)
        i0, i1, j0, j1 = max(ci - n, 0), min(ci + n + 1, self.ny), max(cj - n, 0), min(cj + n + 1, self.nx)
        ii, jj = np.mgrid[i0:i1, j0:j1]
        mask = (self.y0 + ii * CELL - y) ** 2 + (self.x0 + jj * CELL - x) ** 2 <= r * r + 1e-9
        self.occ[layer][i0:i1, j0:j1][mask] = net


class Plan:
    def __init__(self):
        self.tracks = []          # (net, layer, width, [(x, y), ...])
        self.vias = []            # (net, (x, y))

    def track(self, net, layer, width, pts):
        self.tracks.append((net, layer, width, [(round(x, 4), round(y, 4)) for x, y in pts]))

    def via(self, net, at):
        self.vias.append((net, (round(at[0], 4), round(at[1], 4))))


class Router:
    def __init__(self, board):
        self.board = board
        self.grid = Grid()
        self.plan = Plan()
        self.net_ids = {None: -2}
        self.pads = {}            # net -> [Pad]
        self.tree = {}            # net id -> {layer: boolean array (lazily)} of cells one may join
        self.failed = []
        self.routing = False      # once true, new copper belongs to the net's route (it can be ripped up)
        self.routed = {}
        self.stuck = {}
        self.failed_at = []
        self.necked = []
        self.limit = 1200000
        self.boost = 1
        self.u1 = board.part("U1").at
        g = self.grid
        cj, ci = int(round((self.u1[0] - g.x0) / CELL)), int(round((self.u1[1] - g.y0) / CELL))
        ii, jj = np.mgrid[0:g.ny, 0:g.nx]
        self.in_zone = (ii - ci) ** 2 + (jj - cj) ** 2 <= (U1_R / CELL) ** 2
        # the fan-out's four fans (a plus shape): the package's corners stay open for its capacitors
        ri, rj = (ii - ci) * CELL, (jj - cj) * CELL
        self.fanout_block = ((np.abs(ri) <= 9.0) & (np.abs(rj) <= 5.8)) | ((np.abs(rj) <= 9.0) & (np.abs(ri) <= 5.8))
        self.build()

    # ---------------------------------------------------------------- the obstacles
    def nid(self, net):
        if net is None:
            return -2
        if net not in self.net_ids:
            self.net_ids[net] = len(self.net_ids)
        return self.net_ids[net]

    def build(self):
        g = self.grid
        # the board's outline and its cut-outs: nothing beyond them
        outline = unary_union(G.outline())
        xx, yy = np.meshgrid(g.xs, g.ys)
        inside = np.zeros((g.ny, g.nx), dtype=bool)
        px, py = xx - G.ORIGIN[0], L.BOARD_L - (yy - G.ORIGIN[1])
        inside = contains_xy(outline, px, py)
        for name in g.layers:
            g.occ[name][~inside] = -2
        for led in G.leds():
            if led.package == "SK6812MINI-E":
                cut = G.led_cutout(led.x, led.y).buffer(0.12, quad_segs=6)
                kp = Polygon([G.kicad(x, y) for x, y in cut.exterior.coords])
                for name in g.layers:
                    g.stamp_poly(name, kp, -2)
        # the bearings' flanges against the underside
        for side, (x, y) in L.PIVOTS.items():
            kx, ky = G.kicad(x, y)
            g.stamp_disc("B.Cu", kx, ky, 3.6 + 0.5, -2)
        # holes, on every layer
        for hole in self.board.holes:
            for name in g.layers:
                g.stamp_disc(name, hole.at[0], hole.at[1], hole.diameter / 2 + G.HOLE_CLEARANCE - CL, -2)
        # the art on the top copper
        for shape in self.board.shapes:
            if shape.layer != "F.Cu" or not shape.points or len(shape.points) < 3:
                continue
            net = getattr(shape, "net", None)
            g.stamp_poly("F.Cu", Polygon(shape.points).buffer(0), self.nid(net))
        # the stitching vias
        for via in self.board.vias:
            nid = self.nid(via.net)
            for name in g.layers:
                g.stamp_disc(name, via.at[0], via.at[1], via.diameter / 2, nid)
        # pads
        for part in self.board.parts:
            for pad in part.pads:
                if not pad.polygon or len(pad.polygon) < 3:
                    continue
                poly = Polygon(pad.polygon).buffer(0)
                nid = self.nid(pad.net)
                layers = {"top": ["F.Cu"], "bottom": ["B.Cu"], "both": ["F.Cu", "B.Cu", "In2.Cu"]}.get(pad.side, ["F.Cu", "B.Cu", "In2.Cu"])
                for name in layers:
                    g.stamp_poly(name, poly, nid)
                if part.ref.startswith("FID"):     # a fiducial keeps copper 0.6 mm off (its pad's own clearance)
                    for name in layers:
                        g.stamp_poly(name, poly.buffer(0.6 - CL), -2)
                self.pads.setdefault(pad.net, []).append((part.ref, pad.number, pad.at, pad.side, poly, pad.drill))

    # ---------------------------------------------------------------- stamps
    def stamp_track(self, layer, width, pts, net):
        nid = self.nid(net)
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = max(1, int(math.dist((x0, y0), (x1, y1)) / (CELL / 2)))
            for k in range(n + 1):
                self.grid.stamp_disc(layer, x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n, width / 2, nid)

    def add_track(self, net, layer, width, pts):
        self.plan.track(net, layer, width, pts)
        if self.routing:
            self.routed.setdefault(net, [[], []])[0].append(self.plan.tracks[-1])
        self.stamp_track(layer, width, pts, net)

    def add_via(self, net, at):
        for n, v in self.plan.vias:          # a via of the net already there: it serves
            if n == net and math.dist(v, at) < VR:
                return
        for v in self.board.vias:
            if v.net == net and math.dist(v.at, at) < VR:
                return
        self.plan.via(net, at)
        if self.routing:
            self.routed.setdefault(net, [[], []])[1].append(self.plan.vias[-1])
        nid = self.nid(net)
        for name in self.grid.layers:
            self.grid.stamp_disc(name, at[0], at[1], VR, nid)

    # ---------------------------------------------------------------- free space
    def clear_mask(self, net, layer, half):
        """Cells on `layer` a track of half-width `half` of `net` may run: every other net that far away, and
        no more than a cell's error."""
        nid = self.nid(net)
        occ = self.grid.occ[layer]
        other = (occ != -1) & (occ != nid)
        dist = ndimage.distance_transform_edt(~other) * CELL
        return dist >= half + CL + MARGIN - 1e-6

    def via_ok_at(self, net, at, masks=None, r_extra=0.0):
        """Is a via of `net` clear at `at`: VR plus clearance from all other copper on every layer?"""
        nid = self.nid(net)
        i, j = self.grid.ij(*at)
        n = int((VR + CL + MARGIN + r_extra) / CELL) + 2
        for name in self.grid.layers:
            occ = self.grid.occ[name]
            sub = occ[max(i - n, 0):i + n + 1, max(j - n, 0):j + n + 1]
            ii, jj = np.mgrid[max(i - n, 0):i + n + 1, max(j - n, 0):j + n + 1]
            dist = np.hypot(self.grid.y0 + ii * CELL - at[1], self.grid.x0 + jj * CELL - at[0])   # from the via's own centre
            bad = (sub != -1) & (sub != nid) & (dist < VR + CL + MARGIN + r_extra)
            if bad.any():
                return False
        return True

    # ---------------------------------------------------------------- U1's fan-out
    def u1_stubs(self):
        """A fan-out from the 0.4 mm pads to ports on a 0.8 mm pitch, the outermost lanes turning first (45 degrees,
        each next lane a cell later, so parallel lanes keep their gap): every pad gets a port it can leave from."""
        cx, cy = self.u1
        part = self.board.part("U1")
        self.stub_end = {}
        self.rail_ports = set()
        self.via_ports = set()
        self.corridor = np.full((self.grid.ny, self.grid.nx), -1, dtype=np.int32)
        for pad in part.pads:
            if not pad.number or pad.number == "57" or not pad.net or int(pad.number) in POWER_PINS:
                continue
            n = int(pad.number)
            k = (n - 1) % 14                      # its place along its side
            side = (n - 1) // 14
            ax, ay = pad.at
            dx, dy = ax - cx, ay - cy
            radial = (math.copysign(1, dx), 0) if abs(dx) > abs(dy) else (0, math.copysign(1, dy))
            lateral = (0, 1) if radial[0] else (1, 0)
            s0 = dy if radial[0] else dx          # the pad's offset along the side
            c = abs(k - 6.5)                      # its distance from the side's middle, in lanes
            sign = math.copysign(1, s0)
            shift = c * 0.4                       # to a 0.8 mm pitch
            r_turn = PORT_R0 + (6.5 - c) * PORT_STAGGER
            r_end = PORT_R
            pts = [(ax, ay)]

            def at(rad, lat):
                return (cx + radial[0] * rad + lateral[0] * lat, cy + radial[1] * rad + lateral[1] * lat)
            pts.append(at(r_turn, s0))
            pts.append(at(r_turn + shift, s0 + sign * shift))
            pts.append(at(r_end, s0 + sign * shift))
            pts = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > 1e-6]
            self.add_track(pad.net, "B.Cu", NARROW, pts)
            self.stub_end[pad.number] = pts[-1]
            # the front side faces the field and its fan is the most crowded: the long lines drop to In2.Cu as soon as
            # their corridor ends, staggered, so each can leave on either layer
            if radial == (0, 1) and pad.net.startswith(("/Inputs/", "/Flippers/")):
                v = at(PORT_R + 1.4 + (k % 2) * 0.9, s0 + sign * shift)
                self.add_track(pad.net, "B.Cu", NARROW, [pts[-1], v])
                self.add_via(pad.net, v)
                self.stub_end[pad.number] = v
                self.via_ports.add(pad.number)
            if pad.net in RAILS:           # the rails go to In2.Cu at their ports, so nothing runs over a port
                self.add_via(pad.net, pts[-1])
                self.rail_ports.add(pad.number)
            else:                          # a corridor straight out of the port: no other net may cross in front of it
                g = self.grid
                lat = s0 + sign * shift
                a, b = at(PORT_R, lat - 0.35), at(CORRIDOR_R, lat + 0.35)
                i0, j0 = g.ij(min(a[0], b[0]), min(a[1], b[1]))
                i1, j1 = g.ij(max(a[0], b[0]), max(a[1], b[1]))
                self.corridor[i0:i1 + 1, j0:j1 + 1] = self.nid(pad.net)

    # ---------------------------------------------------------------- U1's supply pins
    def u1_power(self):
        """Each supply pin runs inward, under the package, to a via in the ring between its pads and its exposed pad;
        its capacitor stands on the top copper straight over it (pad 1 on the via, pad 2 in the ground poured over U1).
        On In2.Cu the 3V3 vias sit in an island of 3V3 (board.py zones) and the 1V1 vias are joined by hand."""
        cx, cy = self.u1
        part = self.board.part("U1")

        def frame(side):          # (outward, lateral) unit vectors in KiCad's frame
            ox, oy = G.OUTWARD[side]
            out = (ox, -oy)
            lat = (0, -1) if ox else (1, 0)     # u1_point: lateral is +y for left/right, +x for back/front (playfield)
            return out, lat

        def at(side, radial, lateral):
            px, py = G.u1_point(side, lateral, radial)
            return G.kicad(px, py)
        self.power_via = {}
        for side, pins, via_lat, net, cap, cap_lat, *via_r in G.U1_POWER:
            if via_lat is None:
                v = self.power_via["C27"]
            else:
                v = at(side, via_r[0] if via_r else G.U1_VIA_R, via_lat)
                self.add_via(net, v)
            self.power_via[cap] = v
            out, latv = frame(side)
            for n in pins:
                p = part.pad(str(n)).at
                # the pad's lateral offset, the via's, in this side's frame
                pl = (p[0] - cx) * latv[0] + (p[1] - cy) * latv[1]
                vl = (v[0] - cx) * latv[0] + (v[1] - cy) * latv[1]
                vr = (v[0] - cx) * out[0] + (v[1] - cy) * out[1]
                d = abs(pl - vl)
                turn = (cx + out[0] * (vr + d) + latv[0] * pl, cy + out[1] * (vr + d) + latv[1] * pl)
                pts = [p, turn, v] if d > 1e-6 else [p, v]
                self.add_track(net, "B.Cu", 0.2, pts)
            # the capacitor's supply pad to the via, on the top copper
            c = self.board.part(cap).pad("1").at
            dx, dy = v[0] - c[0], v[1] - c[1]
            if abs(dx) < 1e-6 or abs(dy) < 1e-6:
                pts = [c, v]
            else:                 # 45 degrees first, then straight
                s = min(abs(dx), abs(dy))
                mid = (c[0] + math.copysign(s, dx), c[1] + math.copysign(s, dy))
                pts = [c, mid, v]
            self.add_track(net, "F.Cu", 0.25, pts)
        # 1V1 on In2.Cu: VREG_VOUT's via to DVDD's two
        a, b, f = self.power_via["C29"], self.power_via["C31"], self.power_via["C30"]
        self.add_track("+1V1", "In2.Cu", 0.3, [a, (a[0], a[1] + 0.8), (b[0], b[1] + 0.8), b])
        self.add_track("+1V1", "In2.Cu", 0.3, [a, (a[0] - 0.4, a[1] + 0.4), (a[0] - 0.4, f[1] - 0.8),
                                               (a[0] + 0.4, f[1]), f])
        # the island's ground: vias at its corners tie the top copper's ground to In1
        for sx in (-1, 1):
            for sy in (-1, 1):
                self.add_via("GND", (cx + sx * 6.0, cy + sy * 6.0))
        # the island, a square on In2.Cu: no other net crosses it
        g = self.grid
        h = G.U1_ISLAND
        i0, j0 = g.ij(cx - h - 0.3, cy - h - 0.3)
        i1, j1 = g.ij(cx + h + 0.3, cy + h + 0.3)
        self.island = np.zeros((g.ny, g.nx), dtype=bool)
        self.island[i0:i1 + 1, j0:j1 + 1] = True
        self.island_poly = Polygon([(cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h)])

    # ---------------------------------------------------------------- USB
    def usb_pair(self):
        """The USB pair by hand: the connector's two rows joined (D- over the top of the row, D+ under it), straight
        through the ESD array's flow-through pins, then side by side (0.2 mm tracks, 0.2 mm apart, over In1's ground)
        to the 27 ohm resistors at U1, and on to U1's ports."""
        j1, u4, r10, r11 = (self.board.part(r) for r in ("J1", "U4", "R10", "R11"))
        P = lambda part, n: part.pad(n).at  # noqa: E731
        a6, b6, a7, b7 = P(j1, "A6"), P(j1, "B6"), P(j1, "A7"), P(j1, "B7")
        u1p, u3p, u4p, u6p, u2p, u5p = (P(u4, n) for n in "134625")
        w = 0.2
        dp, dm = "/Power/USB_D+", "/Power/USB_D-"
        top = a7[1] - 1.3                  # D- crosses over the top of the row, under the connector's body
        bot = a6[1] + 1.3                  # D+ joins under it
        self.add_track(dm, "B.Cu", w, [b7, (b7[0], top), (a7[0], top), a7])
        self.add_track(dp, "B.Cu", w, [a6, (a6[0], bot), (b6[0], bot), b6])
        y_pair_p, y_pair_m = u3p[1] + 0.55, u3p[1] + 0.95   # the pair's lanes, past the array
        # to the array's inputs: D+ (inner) turns first
        self.add_track(dp, "B.Cu", w, [(a6[0], bot), (a6[0], u3p[1] - 0.6), (a6[0] + 0.6, u3p[1]), u3p, u4p,
                                       (u4p[0] + 2.26, u4p[1]), (u4p[0] + 2.26 + (y_pair_p - u4p[1]), y_pair_p),
                                       (r11.pad("1").at[0] - (y_pair_p - r11.pad("1").at[1]), y_pair_p), r11.pad("1").at])
        self.add_track(dm, "B.Cu", w, [b7, (b7[0], u1p[1] - 1.0), (b7[0] + 1.0, u1p[1]), u1p, u6p,
                                       (u6p[0] + 2.26, u6p[1]), (u6p[0] + 2.26 + (u6p[1] - y_pair_m), y_pair_m),
                                       (r10.pad("1").at[0] - 0.4, y_pair_m), (r10.pad("1").at[0], y_pair_m + 0.4), r10.pad("1").at])
        # on to U1's ports
        self.add_track("Net-(U1-USB_DP)", "B.Cu", w, [r11.pad("2").at, self.stub_end["47"]])
        self.add_track("Net-(U1-USB_DM)", "B.Cu", w, [r10.pad("2").at, self.stub_end["46"]])
        # the array's ground and VBUS pins, out between the lanes
        g = (u2p[0] - 1.06, u2p[1])
        self.add_track("GND", "B.Cu", 0.3, [u2p, g])
        self.add_via("GND", g)
        vb = (u5p[0] + 1.06, u5p[1])
        self.add_track("VBUS", "B.Cu", 0.3, [u5p, vb])
        self.add_via("VBUS", vb)
        self.done_gnd = {("U4", "2")}
        self.escaped_pre = {("U4", "5"): vb}

    # ---------------------------------------------------------------- ground
    def gnd_vias(self):
        """Every ground pad on the underside gets its own via, as near as it clears; pads with room get a short
        track to it. The RP2040's and the other exposed pads get vias inside them."""
        cx, cy = self.u1
        for ep_ref, ep_num, n in (("U1", "57", 2), ("U3", "11", 1), ("U8", "17", 1)):
            part = self.board.part(ep_ref)
            pads = part.pads_numbered(ep_num)
            ax = sum(p.at[0] for p in pads) / len(pads)
            ay = sum(p.at[1] for p in pads) / len(pads)
            if n == 2:
                for dx, dy in ((-0.9, -0.9), (0.9, -0.9), (-0.9, 0.9), (0.9, 0.9), (0.0, 0.0)):
                    self.add_via("GND", (ax + dx, ay + dy))
            else:
                self.add_via("GND", (ax, ay))
        done = {("U1", "57"), ("U3", "11"), ("U8", "17")} | getattr(self, "done_gnd", set())
        pads = sorted(self.pads.get("GND", []), key=lambda p: (p[0], p[1]))
        for ref, number, at, side, poly, drill in pads:
            if (ref, number) in done or drill:
                continue
            if side not in ("bottom",):
                continue
            if ref == "U1":                    # TESTEN: a via at the end of its lane
                at = self.stub_end[number]
                self.add_via("GND", at)
                continue
            if ref == "U8":                    # the MAX98357A's ground pins run in to its exposed pad, under its body
                centre = self.board.part(ref).at
                dx, dy = at[0] - centre[0], at[1] - centre[1]
                radial, lat = (dy, dx) if abs(dy) > abs(dx) else (dx, dy)
                sr, sl = math.copysign(1, radial), math.copysign(1, lat)
                step = abs(radial) - 1.0        # in to 1.0 mm from the centre, then 45 degrees onto the pad
                diag = min(abs(lat), 0.35)
                pts3 = [(radial, lat), (sr * 1.0, lat), (sr * (1.0 - diag), lat - sl * diag)]
                pts = [(centre[0] + (b if abs(dy) > abs(dx) else a), centre[1] + (a if abs(dy) > abs(dx) else b)) for a, b in pts3]
                self.add_track("GND", "B.Cu", 0.2, pts)
                continue
            part_at = self.board.part(ref).at
            # the via stands off the pad (no via in a pad but an exposed pad's: unfilled, it wicks the solder away)
            r0 = max(1.4 if ref in FINE_PITCH else 1.0 if ref.startswith("LED") else 0.0, off_pad(poly, at))
            if self.escape_to_via("GND", at, poly, "B.Cu", WIDTH["GND"], part_at, r0) is None:
                if not self.escape_to_via("GND", at, poly, "B.Cu", 0.2, part_at, off_pad(poly, at)):
                    self.failed.append(("GND", ref, number))

    def escape_to_via(self, net, at, poly, layer, width, part_at=None, r0=0.0):
        """A via as near the pad as is clear (from r0 out), joined by a straight track, away from the part first; None
        when none within 3 mm. A fine-pitch part's via stands clear of its neighbours' way out."""
        cx, cy = self.u1
        out = math.atan2(at[1] - part_at[1], at[0] - part_at[0]) if part_at else 0.0
        best = None
        for r in np.arange(r0, r0 + 3.01, 0.1):
            angles = [0.0] if r == 0 else sorted((2 * math.pi * k / 8 for k in range(8)),
                                                 key=lambda a: abs((a - out + math.pi) % (2 * math.pi) - math.pi))
            for a in angles:                # octolinear from the pad's centre
                x, y = at[0] + r * math.cos(a), at[1] + r * math.sin(a)
                if math.dist((x, y), (cx, cy)) < VIA_FREE_R:
                    continue
                if any(n == net and 1e-6 < math.dist(v, (x, y)) < G.VIA_D + G.HOLE_CLEARANCE for n, v in self.plan.vias):
                    continue                # too near a via of its own net to stand beside it
                if not self.via_ok_at(net, (x, y)):
                    continue
                if not self.segment_clear(net, layer, width, at, (x, y)):
                    continue
                best = (x, y)
                break
            if best:
                break
        if not best:
            return None
        if math.dist(best, at) > 0.05:
            self.add_track(net, layer, width, [at, best])
        self.add_via(net, best)
        return best

    def segment_clear(self, net, layer, width, a, b):
        nid = self.nid(net)
        occ = self.grid.occ[layer]
        r = width / 2 + CL + MARGIN
        n = int(r / CELL) + 2
        steps = max(1, int(math.dist(a, b) / CELL))
        for k in range(steps + 1):
            x, y = a[0] + (b[0] - a[0]) * k / steps, a[1] + (b[1] - a[1]) * k / steps
            i, j = self.grid.ij(x, y)
            sub = occ[max(i - n, 0):i + n + 1, max(j - n, 0):j + n + 1]
            ii, jj = np.mgrid[max(i - n, 0):i + n + 1, max(j - n, 0):j + n + 1]
            dist = np.hypot(self.grid.y0 + ii * CELL - y, self.grid.x0 + jj * CELL - x)
            if ((sub != -1) & (sub != nid) & (dist < r)).any():
                return False
        return True

    def led_power_vias(self):
        """Each LED's +5V pad and its capacitor's: a via beside it, placed before the wiring can wall the pad in; the
        rail then joins vias."""
        self.escaped = dict(getattr(self, "escaped_pre", {}))
        for ref, number, at, side, poly, drill in sorted(self.pads.get("+5V", []), key=lambda p: (p[0], p[1])):
            if side != "bottom" or drill:
                continue
            if ref.startswith("LED") or (ref.startswith("C1") and len(ref) == 4):
                r0 = max(1.0 if ref.startswith("LED") else 0.0, off_pad(poly, at))
                got = self.escape_to_via("+5V", at, poly, "B.Cu", 0.4, self.board.part(ref).at, r0)
                if got:
                    self.escaped[(ref, number)] = got
        # each comb's 1k: its RP2040 side (pad 1, the IN_* line) drops to a via at once, so the long line can arrive
        # on either layer however the comb's corner fills up
        for net, pads in sorted(self.pads.items(), key=lambda kv: str(kv[0])):
            if not net or "/IN_" not in net:
                continue
            for ref, number, at, side, poly, drill in pads:
                if ref.startswith("R") and side == "bottom":
                    got = self.escape_to_via(net, at, poly, "B.Cu", 0.2, self.board.part(ref).at, off_pad(poly, at))
                    if got:
                        self.escaped[(ref, number)] = got

    # ---------------------------------------------------------------- the top parts' ways down
    def top_pads_down(self):
        """A pad on the top copper (the furniture's LEDs and their caps) goes down through a via beside it, under
        the part that hides it. Answers net -> [via points]."""
        hidden = unary_union([*P.rails(), P.lockdown(), *(P.circle(*L.BUMPERS[n], L.BUMPER_POST_R - 0.3) for n in L.BUMPERS),
                              P.sling_footprint("left"), P.sling_footprint("right"),
                              *(P.target_footprint(n) for n in L.TARGETS)])
        downs = {}
        for part in self.board.parts:
            if part.side != "top" or part.ref in POWER_CAPS:
                continue
            for pad in part.pads:
                if pad.side != "top" or not pad.net or not pad.polygon:
                    continue
                if pad.net.startswith("unconnected"):
                    continue
                at = pad.at
                found = None
                for r in np.arange(0.9, 4.0, 0.1):
                    for k in range(8):      # octolinear from the pad's centre
                        a = 2 * math.pi * k / 8
                        x, y = at[0] + r * math.cos(a), at[1] + r * math.sin(a)
                        px, py = G.playfield(x, y)
                        if not hidden.contains(Point(px, py).buffer(VR + 0.1)):
                            continue
                        if not self.via_ok_at(pad.net, (x, y)):
                            continue
                        if not self.segment_clear(pad.net, "F.Cu", 0.25, at, (x, y)):
                            continue
                        found = (x, y)
                        break
                    if found:
                        break
                if not found:
                    self.failed.append((pad.net, part.ref, pad.number))
                    continue
                self.add_track(pad.net, "F.Cu", 0.25, [at, found])
                self.add_via(pad.net, found)
                downs.setdefault(pad.net, []).append(found)
        return downs

    # ---------------------------------------------------------------- A*
    def route_net(self, net, width, seeds_pts):
        """Join `seeds_pts` (the net's terminals: [(layer or None for both, x, y, polygon or None)]), a tree grown
        nearest first. Answers False when a terminal finds no way."""
        g = self.grid
        if len(seeds_pts) < 2:
            print(f"    {net}: {len(seeds_pts)} terminal(s), nothing to join", flush=True)
            return True
        xs = [t["at"][0] for t in seeds_pts]
        ys = [t["at"][1] for t in seeds_pts]
        self.limit = (800000 if (max(xs) - min(xs)) + (max(ys) - min(ys)) < 40 else 3000000) * self.boost
        nid = self.nid(net)
        half = width / 2
        in_zone = self.in_zone     # the zone round U1 where the track necks to NARROW
        # a wide net necks to NECK as it nears its pads, the way a fan-out does (a 0.8 mm track cannot reach a 0.6 mm
        # pad among others at full width)
        neck_zone = np.zeros_like(in_zone)
        if half > NECK / 2:
            for t in seeds_pts:
                x, y = t["at"]
                r = NECK_R
                i0, j0 = g.ij(x - r, y - r)
                i1, j1 = g.ij(x + r, y + r)
                neck_zone[max(i0, 0):i1 + 1, max(j0, 0):j1 + 1] = True
        free = {}
        for name in LAYERS:
            m = self.clear_mask(net, name, half)
            if half > NARROW / 2:
                m = m | (self.clear_mask(net, name, NARROW / 2) & in_zone)
            if neck_zone.any():
                m = m | (self.clear_mask(net, name, NECK / 2) & neck_zone)
            free[name] = m
        self.neck_zone = neck_zone
        if net in RAILS:               # the rails take In2.Cu past the fan-out: each port a via, its lanes left free
            free["B.Cu"] = free["B.Cu"] & ~self.fanout_block
        if net != "+3V3":
            free["In2.Cu"] = free["In2.Cu"] & ~self.island
        free["B.Cu"] = free["B.Cu"] & ((self.corridor == -1) | (self.corridor == nid))
        # the terminals' cells: inside a pad, along what is already drawn
        tree = {name: np.zeros((g.ny, g.nx), dtype=bool) for name in LAYERS}
        terms = []
        for t in seeds_pts:
            cells = {}
            for name in LAYERS:
                if t["layers"] is not None and name not in t["layers"]:
                    continue
                if t.get("poly") is not None:
                    minx, miny, maxx, maxy = t["poly"].bounds
                    i0, j0 = g.ij(minx, miny)
                    i1, j1 = g.ij(maxx, maxy)
                    xx, yy = np.meshgrid(g.xs[j0:j1 + 1], g.ys[i0:i1 + 1])
                    # a track ends inside its pad, never at the pad's edge beside a neighbour
                    mask = contains_xy(t["poly"].buffer(-min(width / 2, 0.2)), xx, yy)
                    got = [(int(i0 + a), int(j0 + b)) for a, b in zip(*np.nonzero(mask))]
                    if not got:
                        got = [g.ij(*t["at"])]
                else:
                    got = [g.ij(*t["at"])]
                cells[name] = got
            terms.append(cells)
        if len(terms) < 2:
            return True
        # the tree starts as the first terminal
        for name, got in terms[0].items():
            for c in got:
                tree[name][c] = True
        pending = list(range(1, len(terms)))
        ok = True
        while pending:
            # the nearest pending terminal
            any_tree = tree[LAYERS[0]] | tree[LAYERS[1]]
            h = ndimage.distance_transform_edt(~any_tree) * CELL
            best, best_d = None, 1e9
            for k in pending:
                for name, got in terms[k].items():
                    d = min(h[c] for c in got)
                    if d < best_d:
                        best, best_d = k, d
            path = self.astar(net, terms[best], tree, free, h, in_zone, width)
            if path is None and half > NECK / 2:   # no way at full width: at the neck's, this once
                narrow = {name: self.clear_mask(net, name, NECK / 2) for name in LAYERS}
                if net in RAILS:
                    narrow["B.Cu"] = narrow["B.Cu"] & ~self.fanout_block
                if net != "+3V3":
                    narrow["In2.Cu"] = narrow["In2.Cu"] & ~self.island
                narrow["B.Cu"] = narrow["B.Cu"] & ((self.corridor == -1) | (self.corridor == nid))
                path = self.astar(net, terms[best], tree, narrow, h, in_zone, NECK)
                if path is not None:
                    self.necked.append(net)
                    self.commit_path(net, path, NECK, in_zone, tree)
                    pending.remove(best)
                    for name, got in terms[best].items():
                        for c in got:
                            tree[name][c] = True
                    continue
            pending.remove(best)
            if path is None:
                where = next(iter(terms[best].values()))[0]
                print(f"    {net}: no path from {g.xy(*where)} after {self.expanded} cells", flush=True)
                self.failed_at.append((net, g.xy(*where)))
                self.stuck[net] = g.xy(*where)
                ok = False
                continue
            self.commit_path(net, path, width, in_zone, tree)
            for name, got in terms[best].items():
                for c in got:
                    tree[name][c] = True
        return ok

    def astar(self, net, sources, tree, free, h, in_zone, width):
        """From a terminal's cells to any tree cell. State: layer, cell, direction (flat ints); h: the distance to
        the tree (admissible: a straight line). Answers the path or None."""
        g = self.grid
        cost_via = 2.5
        bend = 0.2
        # a wide net stays on B.Cu's 1 oz where it can: In2.Cu is 0.5 oz and carries a third of the current
        inner_cost = 3.0 if width > 0.45 else 1.0
        names = LAYERS
        ny, nx = g.ny, g.nx
        size = ny * nx
        free_b = (free[names[0]].tobytes(), free[names[1]].tobytes())
        tree_b = (tree[names[0]].tobytes(), tree[names[1]].tobytes())
        hf = h.ravel()
        hmv = memoryview(hf)
        cx, cy = self.u1
        best = {}
        came = {}
        heap = []
        counter = 0
        steps = [(dj + di * nx, CELL * (1.414213562 if k % 2 else 1.0), di, dj) for k, (dj, di) in enumerate(Dirs)]

        def key(li, idx, d):
            return (li * size + idx) * 9 + d
        for li, name in enumerate(names):
            for c in sources.get(name, []):
                idx = c[0] * nx + c[1]
                s = key(li, idx, 8)
                best[s] = 0.0
                came[s] = None
                heapq.heappush(heap, (GREED * hmv[idx], counter, 0.0, s))
                counter += 1
        expanded = 0
        limit = self.limit
        while heap:
            f, _, gc, s = heapq.heappop(heap)
            if best.get(s, 1e18) < gc - 1e-9:
                continue
            d = s % 9
            rest = s // 9
            li = rest // size
            idx = rest - li * size
            if tree_b[li][idx]:
                path = []
                node = s
                while node is not None:
                    rest_ = node // 9
                    li_ = rest_ // size
                    idx_ = rest_ - li_ * size
                    path.append((li_, idx_ // nx, idx_ % nx, node % 9))
                    node = came[node]
                return path[::-1]
            expanded += 1
            self.expanded = expanded
            if expanded > limit:
                return None
            free_l = free_b[li]
            tree_l = tree_b[li]
            i, j = idx // nx, idx % nx
            for nd in range(8):
                if d != 8:
                    turn = (nd - d) % 8
                    if turn > 4:
                        turn = 8 - turn
                    if turn > 2:
                        continue
                else:
                    turn = 0
                off, step, di, dj = steps[nd]
                a, b = i + di, j + dj
                if not (0 <= a < ny and 0 <= b < nx):
                    continue
                nidx = idx + off
                if not free_l[nidx] and not tree_l[nidx]:
                    continue
                if nd % 2 and not (free_l[a * nx + j] or free_l[i * nx + b]):
                    continue
                ng = gc + step * (inner_cost if li == 1 else 1.0) + bend * turn
                ns = key(li, nidx, nd)
                if ng < best.get(ns, 1e18) - 1e-9:
                    best[ns] = ng
                    came[ns] = s
                    heapq.heappush(heap, (ng + GREED * hmv[nidx], counter, ng, ns))
                    counter += 1
            if d != 8 or gc == 0.0:     # a via, anywhere along the way or right at the start
                other = 1 - li
                ns = key(other, idx, 8)
                ng = gc + cost_via
                if ng < best.get(ns, 1e18) - 1e-9:
                    at = g.xy(i, j)
                    if math.dist(at, (cx, cy)) >= VIA_FREE_R and self.via_ok_at(net, at):
                        best[ns] = ng
                        came[ns] = s
                        heapq.heappush(heap, (ng + GREED * hmv[idx], counter, ng, ns))
                        counter += 1
        return None

    def commit_path(self, net, path, width, in_zone, tree):
        g = self.grid
        self.path_width = None
        runs = []
        run = [path[0]]
        for s in path[1:]:
            if s[0] != run[-1][0]:
                runs.append(run)
                # a via here
                at = g.xy(s[1], s[2])
                self.add_via(net, at)
                for name in LAYERS:
                    tree[name][s[1], s[2]] = True
                run = [s]
            else:
                run.append(s)
        runs.append(run)
        for run in runs:
            name = LAYERS[run[0][0]]
            pts = [(s[1], s[2]) for s in run]
            for c in pts:
                tree[name][c] = True
            if len(pts) < 2:
                continue
            # split by width (narrow inside U1's zone) and direction changes
            def width_at(c):
                if in_zone[c] and width > NARROW:
                    return NARROW
                if self.neck_zone[c] and width > NECK:
                    return NECK
                return self.path_width if self.path_width else width
            seg = [pts[0]]
            cur_w = width_at(pts[0])
            for k in range(1, len(pts)):
                w = width_at(pts[k])
                if w != cur_w:
                    # the step between two widths is drawn at the narrower: the wide track stops where it was searched
                    if w < cur_w:
                        if len(seg) > 1:
                            self.emit(net, name, cur_w, seg)
                        seg = [pts[k - 1], pts[k]]
                    else:
                        self.emit(net, name, cur_w, seg + [pts[k]])
                        seg = [pts[k]]
                    cur_w = w
                else:
                    seg.append(pts[k])
            if len(seg) > 1:
                self.emit(net, name, cur_w, seg)

    def emit(self, net, layer, width, cells):
        """Cells as a polyline, a point at each turn."""
        g = self.grid
        pts = [g.xy(*cells[0])]
        for a, b, c in zip(cells, cells[1:], cells[2:]):
            if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
                pts.append(g.xy(*b))
        pts.append(g.xy(*cells[-1]))
        self.add_track(net, layer, width, pts)

    # ---------------------------------------------------------------- rip-up
    def rip(self, net):
        """Take a net's route off the board: its pads, stubs and vias of its own stay."""
        tracks, vias = self.routed.pop(net, [[], []])
        ids = {id(t) for t in tracks}
        idv = {id(v) for v in vias}
        self.plan.tracks = [t for t in self.plan.tracks if id(t) not in ids]
        self.plan.vias = [v for v in self.plan.vias if id(v) not in idv]
        nid = self.nid(net)
        for name in self.grid.layers:
            occ = self.grid.occ[name]
            occ[occ == nid] = -1
        # what stays: its pads, the art on its net, and its stubs and vias
        for ref, number, at, side, poly, drill in self.pads.get(net, []):
            layers = {"top": ["F.Cu"], "bottom": ["B.Cu"], "both": ["F.Cu", "B.Cu", "In2.Cu"]}.get(side, ["F.Cu", "B.Cu", "In2.Cu"])
            for name in layers:
                self.grid.stamp_poly(name, poly, nid)
        for shape in self.board.shapes:
            if shape.layer == "F.Cu" and shape.points and len(shape.points) >= 3 and getattr(shape, "net", None) == net:
                self.grid.stamp_poly("F.Cu", Polygon(shape.points).buffer(0), nid)
        for n, layer, width, pts in self.plan.tracks:
            if n == net:
                self.stamp_track(layer, width, pts, net)
        for n, at in self.plan.vias:
            if n == net:
                for name in self.grid.layers:
                    self.grid.stamp_disc(name, at[0], at[1], VR, nid)

    def blockers(self, net, at, radius=3.0):
        """The nets nearest a stuck terminal, nearest first: not its own, not ground, not a power rail."""
        nid = self.nid(net)
        inv = {v: k for k, v in self.net_ids.items()}
        found = {}
        i, j = self.grid.ij(*at)
        n = int(radius / CELL)
        for name in LAYERS:
            sub = self.grid.occ[name][max(i - n, 0):i + n, max(j - n, 0):j + n]
            ii, jj = np.mgrid[max(i - n, 0):i + n, max(j - n, 0):j + n]
            dist = np.hypot(ii - i, jj - j) * CELL
            for v in np.unique(sub):
                if v <= 0 or v == nid:
                    continue
                other = inv.get(int(v))
                if other in (None, "GND", "+5V", "+9V", "VBUS", "+3V3", "+1V1") or other not in self.routed:
                    continue
                d = float(dist[sub == v].min())
                found[other] = min(found.get(other, 1e9), d)
        return sorted(found, key=found.get)

    # ---------------------------------------------------------------- the nets
    def terminals(self, net, downs):
        out = []
        if net == "+3V3":
            out.append({"layers": ("In2.Cu",), "at": self.u1, "poly": self.island_poly.buffer(-0.6)})
        for ref, number, at, side, poly, drill in self.pads.get(net, []):
            if (ref == "U1" and number.isdigit() and int(number) in POWER_PINS) or ref in POWER_CAPS:
                continue
            if (ref, number) in getattr(self, "escaped", {}):
                out.append({"layers": None, "at": self.escaped[(ref, number)], "poly": None})
            elif ref == "U1" and number in self.stub_end:
                layers = None if number in self.rail_ports or number in self.via_ports else ("B.Cu",)
                out.append({"layers": layers, "at": self.stub_end[number], "poly": None})
            elif side in ("both",) or drill:
                out.append({"layers": None, "at": at, "poly": poly})
            elif side == "bottom":
                out.append({"layers": ("B.Cu",), "at": at, "poly": poly})
        for at in downs.get(net, []):
            out.append({"layers": None, "at": at, "poly": None})
        return out


def net_order(nets, r: Router):
    """+9V's trunk first (it needs the width), the rails and U1's short nets; then the nets with the hardest way out,
    those leaving U1's back and left sides for the field; everything else, shortest first; +5V last, joining its vias."""
    def length(net):
        pads = r.pads.get(net, [])
        if len(pads) < 2:
            return 0
        xs = [p[2][0] for p in pads]
        ys = [p[2][1] for p in pads]
        return (max(xs) - min(xs)) + (max(ys) - min(ys))
    first = ["+1V1", "+3V3"]
    power = ["+9V", "VBUS"]
    rest = [n for n in nets if n not in first + power + ["GND", "+5V"]]
    u1 = r.board.part("U1")
    cx, cy = u1.at
    side_of = {}
    for pad in u1.pads:
        if pad.net and pad.number and pad.number != "57":
            dx, dy = pad.at[0] - cx, pad.at[1] - cy
            side_of[pad.net] = "side" if abs(dx) > abs(dy) else ("back" if dy < 0 else "front")   # KiCad's y runs down
    fine = sorted([n for n in rest if n in side_of and length(n) < 25], key=length)
    long_back = sorted([n for n in rest if n not in fine and side_of.get(n) == "back"], key=length, reverse=True)
    long_side = sorted([n for n in rest if n not in fine and side_of.get(n) == "side"], key=length, reverse=True)
    others = sorted([n for n in rest if n not in fine and n not in long_back and n not in long_side], key=length)
    # the LED chain's hops early: short, but each between a cut-out and its neighbours, easily walled in
    chain = sorted([n for n in rest if "DOUT" in n or "CHAIN_" in n], key=length)
    fine = [n for n in fine if n not in chain]
    long_back = [n for n in long_back if n not in chain]
    long_side = [n for n in long_side if n not in chain]
    others = [n for n in others if n not in chain]
    return power + first + chain + fine + long_back + long_side + others + ["+5V"]


def width_of(net):
    if net in WIDTH:
        return WIDTH[net]
    if any(key in net for key in ("COIL_L_DRAIN", "COIL_R_DRAIN", "BUCK_SW")):
        return 0.8                    # the coils' drains, the buck's switch node
    return G.SIGNAL


def run(priority):
    board = kicad_pcb.read(str(BOARD))
    r = Router(board)
    r.u1_stubs()
    r.u1_power()
    r.usb_pair()
    r.gnd_vias()
    downs = r.top_pads_down()
    r.led_power_vias()
    nets = [n for n in r.pads if n and not n.startswith("unconnected") and n != "GND" and n not in HAND
            and len(r.pads[n]) + len(downs.get(n, [])) >= 2]
    order = net_order(nets, r)
    order = [n for n in priority if n in order] + [n for n in order if n not in priority]
    failed = []
    t0 = time.time()
    r.routing = True
    for k, net in enumerate(order):
        ok = r.route_net(net, width_of(net), r.terminals(net, downs))
        if not ok:
            failed.append(net)
            print(f"  no way for {net}", flush=True)
        if k % 10 == 0:
            print(f"  {k}/{len(order)} nets, {time.time() - t0:.0f} s", flush=True)
    print(f"  {len(r.plan.tracks)} tracks, {len(r.plan.vias)} vias, {len(failed)} nets failed, {len(r.failed)} pads without a way", flush=True)
    # rip-up and retry: take the nets round a stuck terminal up, route the stuck net, route them again
    OUT.write_text(json.dumps({"tracks": r.plan.tracks, "vias": r.plan.vias, "failed": failed, "failed_at": r.failed_at,
                               "pads": [list(x) for x in r.failed]}))
    rounds = 0
    tried = {}
    while failed and rounds < int(os.environ.get("ROUTE_ROUNDS", "60")):
        rounds += 1
        net = failed.pop(0)
        tried[net] = tried.get(net, 0) + 1
        at = r.stuck.get(net)
        take = (r.blockers(net, at) if at else [])[:min(1 + tried[net], 4)]
        r.rip(net)
        for other in take:
            r.rip(other)
        r.boost = min(1 + tried[net], 4)       # a stuck net searches further each time
        ok = r.route_net(net, width_of(net), r.terminals(net, downs))
        r.boost = 1
        for other in take:
            if not r.route_net(other, width_of(other), r.terminals(other, downs)):
                failed.append(other)
        if not ok:
            failed.append(net)
        print(f"  round {rounds}: {net}, took up {take}: {'ok' if ok else 'stuck'}; {len(failed)} left, {time.time() - t0:.0f} s", flush=True)
    print(f"  after rip-up: {len(r.plan.tracks)} tracks, {len(r.plan.vias)} vias, {len(failed)} nets failed", flush=True)
    return r, failed


def prune_vias(r):
    """A via whose net's copper meets it on one layer only is no via (an escape the route then reached on the same layer):
    take it out. Ground's stay (In1 is ground)."""
    pads_at = {}
    for net, pads in r.pads.items():
        for ref, number, at, side, poly, drill in pads:
            pads_at.setdefault(net, []).append((poly, ("B.Cu",) if side == "bottom" else ("F.Cu",) if side == "top" else LAYERS + ("F.Cu",)))
    island = {"+3V3"}
    keep, dropped = [], 0
    for net, at in r.plan.vias:
        if net == "GND":
            keep.append((net, at))
            continue
        layers = set()
        p = Point(at)
        for n, layer, width, pts in r.plan.tracks:
            if n == net and len(pts) > 1 and LineString(pts).distance(p) < VR + width / 2 - 0.02:
                layers.add(layer)
        for poly, ls in pads_at.get(net, []):
            if poly.distance(p) < VR - 0.02:
                layers.update(ls)
        if net in island and r.island_poly.contains(p):
            layers.add("In2.Cu")
        if len(layers) >= 2:
            keep.append((net, at))
        else:
            dropped += 1
            # the path search ends on the grid, the via stood off it: join the ends to the via's point
            ends = [(layer, e) for n, layer, width, pts in r.plan.tracks if n == net for e in (pts[0], pts[-1])]
            for n, layer, width, pts in list(r.plan.tracks):
                if n != net:
                    continue
                for e in (pts[0], pts[-1]):
                    # only where another track of the net ends on the via's point (the escape from its pad)
                    if 1e-6 < math.dist(e, at) < 0.1 and any(l2 == layer and math.dist(e2, at) < 1e-4 for l2, e2 in ends):
                        r.plan.tracks.append((net, layer, width, [e, (round(at[0], 4), round(at[1], 4))]))
    r.plan.vias = keep
    print(f"  pruned {dropped} vias that met their net on one layer", flush=True)


def trim_dead_ends(r):
    """Take off any track segment with an end that meets nothing of its net (a pad, a via, another track's end, 3V3's
    island): what a rip-up and a re-route leave behind at a port."""
    pads = {}
    for net, ps in r.pads.items():
        for ref, number, at, side, poly, drill in ps:
            layers = ("B.Cu",) if side == "bottom" else ("F.Cu",) if side == "top" else ("F.Cu", "B.Cu", "In2.Cu")
            for layer in layers:
                pads.setdefault((net, layer), []).append(poly.buffer(0.01))
    segs = [(n, layer, w, tuple(a), tuple(b)) for n, layer, w, pts in r.plan.tracks for a, b in zip(pts, pts[1:])
            if math.dist(a, b) > 1e-4]
    # a segment drawn twice (a route that came back along its own stub) once, at the wider width
    best = {}
    for s in segs:
        n, layer, w, a, b = s
        key = (n, layer, *sorted([(round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))]))
        if key not in best or best[key][2] < w:
            best[key] = s
    removed_twice = len(segs) - len(best)
    segs = list(best.values())
    vias = {}
    for n, at in r.plan.vias:
        vias.setdefault(n, []).append(at)
    for v in r.board.vias:
        vias.setdefault(v.net, []).append(v.at)
    removed = 0
    while True:
        ends = {}
        for k, (n, layer, w, a, b) in enumerate(segs):
            for e in (a, b):
                ends.setdefault((n, layer, round(e[0], 3), round(e[1], 3)), []).append(k)

        def meets(n, layer, e, k):
            if len(ends[(n, layer, round(e[0], 3), round(e[1], 3))]) > 1:
                return True
            if any(math.dist(e, v) < VR for v in vias.get(n, [])):
                return True
            if any(p.contains(Point(e)) for p in pads.get((n, layer), [])):
                return True
            if n == "+3V3" and layer == "In2.Cu" and r.island_poly.buffer(0.3).contains(Point(e)):
                return True
            return False
        dead = [k for k, (n, layer, w, a, b) in enumerate(segs) if not (meets(n, layer, a, k) and meets(n, layer, b, k))]
        if not dead:
            break
        removed += len(dead)
        dead = set(dead)
        segs = [s for k, s in enumerate(segs) if k not in dead]
    r.plan.tracks = [(n, layer, w, [a, b]) for n, layer, w, a, b in segs]
    print(f"  {removed} dead-end segments taken off, {removed_twice} drawn twice", flush=True)


def split_tees(r):
    """A track that ends on the middle of another of its net (a tee) splits that one there, so the two meet end to end."""
    split = 0
    tracks = r.plan.tracks
    ends = {(n, layer): [] for n, layer, w, pts in tracks}
    for n, layer, w, pts in tracks:
        ends[(n, layer)] += [pts[0], pts[-1]]
    out = []
    for n, layer, w, pts in tracks:
        new = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            seg = LineString([a, b])
            cuts = sorted((seg.project(Point(e)), e) for e in ends[(n, layer)]
                          if 1e-4 < math.dist(e, a) and 1e-4 < math.dist(e, b) and seg.distance(Point(e)) < 1e-4)
            for _, e in cuts:
                if math.dist(e, new[-1]) > 1e-4:
                    new.append(tuple(e))
                    split += 1
            if math.dist(b, new[-1]) > 1e-4:
                new.append(b)
        if len(new) > 1:
            out.append((n, layer, w, new))
    r.plan.tracks = out
    print(f"  {split} tees split", flush=True)


def main():
    priority = []
    OUT.parent.mkdir(exist_ok=True)
    attempts = int(os.environ.get("ROUTE_ATTEMPTS", "6"))
    for attempt in range(attempts):
        r, failed = run(priority)
        prune_vias(r)
        split_tees(r)
        trim_dead_ends(r)
        OUT.write_text(json.dumps({"tracks": r.plan.tracks, "vias": r.plan.vias, "failed": failed, "failed_at": r.failed_at, "pads": [list(x) for x in r.failed]}))
        if not failed and not r.failed:
            break
        print(f"attempt {attempt + 1}: failed {failed} {r.failed}", flush=True)
        priority = failed + [n for n in priority if n not in failed]
    print("wrote", OUT, "failed:", failed, r.failed)


if __name__ == "__main__":
    main()
