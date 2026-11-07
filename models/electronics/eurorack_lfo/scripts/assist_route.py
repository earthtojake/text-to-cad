# /// script
# dependencies = ["numpy", "scipy", "shapely"]
# ///
"""Script-assisted routing: for each net, in an order and with layer costs this file states, an octolinear
A* search on a 0.1 mm grid finds each connection's path around every other net's copper (pads, tracks,
vias, the board edge and the jacks' F.Cu keepouts, inflated by the clearance), and the paths are written
to the board as tracks and vias through kicad_pcb.edit. GND is left to the two pours (stitched afterwards).

This is NOT the skill's method (it says route by hand, never an autorouter): hand-written geometry for ~170
connections did not converge, so the agent directs this per-net search instead (README: how the board was routed).

Run: cad run scripts/assist_route.py   (reads the saved board; writes tracks + vias; re-run replaces them)"""

from __future__ import annotations

import heapq
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import ndimage
import shapely
from shapely.geometry import LineString, Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardlib import BOARD, H, W, X0, Y0  # noqa: E402
from routelib import Routes, sync  # noqa: E402

from cad import kicad_pcb  # noqa: E402

G = 0.1                                  # grid pitch, mm
NX, NY = int(round(W / G)) + 1, int(round(H / G)) + 1
CLR = 0.2                                # clearance, mm
MARGIN = 0.08                            # the grid's own error: a cell centre is up to 0.07 mm off the true line
EDGE = 0.3                               # copper to board edge
SIG_W, PWR_W = 0.25, 0.4
VIA_D = 0.8
POWER = {"+12V", "-12V"}
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


def grid_xy():
    xs = np.arange(NX) * G
    ys = np.arange(NY) * G
    return np.meshgrid(xs, ys)


GX, GY = grid_xy()


def raster(geom) -> np.ndarray:
    """Cells whose centre lies inside geom (board-local mm)."""
    minx, miny, maxx, maxy = geom.bounds
    i0, i1 = max(0, int(math.floor(minx / G))), min(NX - 1, int(math.ceil(maxx / G)))
    j0, j1 = max(0, int(math.floor(miny / G))), min(NY - 1, int(math.ceil(maxy / G)))
    out = np.zeros((NY, NX), bool)
    if i1 < i0 or j1 < j0:
        return out
    sub = shapely.contains_xy(geom, GX[j0:j1 + 1, i0:i1 + 1], GY[j0:j1 + 1, i0:i1 + 1])
    out[j0:j1 + 1, i0:i1 + 1] = sub
    return out


def disk(r_mm: float) -> np.ndarray:
    n = int(math.ceil(r_mm / G))
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1]
    return (xx * xx + yy * yy) * G * G <= r_mm * r_mm + 1e-9


class Board:
    def __init__(self, board):
        self.b = board
        self.nets: list[str] = ["", "<nonet>"]
        self.id = {"": 0, "<nonet>": 1}
        self.cu = {L: np.zeros((NY, NX), np.int32) for L in ("F.Cu", "B.Cu")}   # net id of copper, -1 = shared
        self.pad_cells: dict[tuple[str, str], dict[str, np.ndarray]] = {}
        self.keep = {L: np.zeros((NY, NX), bool) for L in ("F.Cu", "B.Cu")}
        self.edge_ok = None
        self._load()

    def nid(self, name):
        name = name or "<nonet>"
        if name.startswith("unconnected"):
            name = "<nc>" + name
        if name not in self.id:
            self.id[name] = len(self.nets)
            self.nets.append(name)
        return self.id[name]

    def stamp(self, layer, mask, nid):
        a = self.cu[layer]
        clash = mask & (a != 0) & (a != nid)
        a[mask & (a == 0)] = nid
        a[clash] = -1

    def _load(self):
        outline = Polygon([(x - X0, y - Y0) for x, y in self.b.outline[0]])
        self.outline = outline
        for part in self.b.parts:
            for pad in part.pads:
                poly = Polygon([(x - X0, y - Y0) for x, y in pad.polygon])
                m = raster(poly.buffer(0.001))
                n = self.nid(pad.net)
                layers = ["F.Cu", "B.Cu"] if pad.side == "both" else (["B.Cu"] if pad.side == "bottom" else ["F.Cu"])
                for L in layers:
                    self.stamp(L, m, n)
                self.pad_cells[(part.ref, pad.number + "@" + f"{pad.at[0]:.3f},{pad.at[1]:.3f}")] = {"net": pad.net, "mask": m, "layers": layers, "poly": poly}
        for z in self.b.rule_areas:
            for ring in (z.outline if isinstance(z.outline[0][0], tuple) else [z.outline]):
                poly = Polygon([(x - X0, y - Y0) for x, y in ring])
                for L in z.layers:
                    if L in self.keep:
                        self.keep[L] |= raster(poly)

    def add_track(self, layer, a, b, w, nid):
        m = raster(LineString([a, b]).buffer(w / 2))
        self.stamp(layer, m, nid)

    def add_via(self, p, nid):
        m = raster(Point(p).buffer(VIA_D / 2))
        for L in ("F.Cu", "B.Cu"):
            self.stamp(L, m, nid)

    _inner = {}

    def inner(self, inset):
        if inset not in self._inner:
            self._inner[inset] = raster(self.outline.buffer(-inset))
        return self._inner[inset]

    def free(self, nid, w):
        """Per layer: True where a track of width w on net nid may run its centreline."""
        r = CLR + w / 2 + MARGIN
        inner = self.inner(EDGE + w / 2 + MARGIN)
        out = {}
        for L, a in self.cu.items():
            other = (a != 0) & (a != nid)
            blocked = ndimage.binary_dilation(other, structure=disk(r))
            out[L] = ~blocked & inner & ~ndimage.binary_dilation(self.keep[L], structure=disk(w / 2 + MARGIN))
        vr = CLR + VIA_D / 2 + MARGIN
        via_ok = self.inner(EDGE + VIA_D / 2).copy()
        for L, a in self.cu.items():
            other = (a != 0) & (a != nid)
            via_ok &= ~ndimage.binary_dilation(other, structure=disk(vr))
            via_ok &= ~ndimage.binary_dilation(self.keep[L], structure=disk(VIA_D / 2 + MARGIN))
        out["via"] = via_ok
        return out


def astar(free, src, dst, cost, via_cost, window):
    """src, dst: dict layer -> bool mask. Returns [(layer, i, j), ...] grid path or None."""
    (i0, j0, i1, j1) = window
    dst_cells = {L: np.argwhere(m[j0:j1 + 1, i0:i1 + 1]) for L, m in dst.items()}
    targets = set()
    for L, cells in dst_cells.items():
        for jj, ii in cells:
            targets.add((L, ii + i0, jj + j0))
    if not targets:
        return None
    tx = np.array([t[1] for t in targets])
    ty = np.array([t[2] for t in targets])
    cx, cy = tx.mean(), ty.mean()
    rad = max(np.hypot(tx - cx, ty - cy).max(), 0)

    def h(i, j):
        d = math.hypot(i - cx, j - cy) - rad
        return max(d, 0) * min(cost.values()) * 1.4   # weighted A*: a little longer paths, far fewer pops

    openq = []
    best = {}
    parent = {}
    for L, m in src.items():
        for jj, ii in np.argwhere(m[j0:j1 + 1, i0:i1 + 1]):
            i, j = ii + i0, jj + j0
            s = (L, i, j, -1)
            best[s] = 0.0
            heapq.heappush(openq, (h(i, j), 0.0, s))
    layers = ("F.Cu", "B.Cu")
    pops = 0
    while openq:
        f, g, s = heapq.heappop(openq)
        if g > best.get(s, 1e18) + 1e-9:
            continue
        L, i, j, d = s
        pops += 1
        if pops > 3000000:
            return None
        if (L, i, j) in targets:
            path = [(L, i, j)]
            while s in parent:
                s = parent[s]
                path.append((s[0], s[1], s[2]))
            return path[::-1]
        for k, (di, dj) in enumerate(DIRS):
            ni, nj = i + di, j + dj
            if ni < i0 or nj < j0 or ni > i1 or nj > j1 or not free[L][nj, ni]:
                continue
            step = (1.41421356 if di and dj else 1.0) * cost[L]
            turn = 0.0 if d in (-1, k) else (0.6 if (k - d) % 8 in (1, 7) else 3.0)
            ns = (L, ni, nj, k)
            ng = g + step + turn
            if ng < best.get(ns, 1e18):
                best[ns] = ng
                parent[ns] = s
                heapq.heappush(openq, (ng + h(ni, nj), ng, ns))
        if free["via"][j, i]:
            OL = layers[1] if L == layers[0] else layers[0]
            ns = (OL, i, j, d)
            ng = g + via_cost
            if free[OL][j, i] and ng < best.get(ns, 1e18):
                best[ns] = ng
                parent[ns] = s
                heapq.heappush(openq, (ng + h(i, j), ng, ns))
    return None


def simplify(path):
    """Grid path -> list of (layer, [points]) runs and via points."""
    runs, vias = [], []
    cur_l, pts = path[0][0], [path[0][1:]]
    for (L, i, j) in path[1:]:
        if L != cur_l:
            vias.append(pts[-1])
            runs.append((cur_l, pts))
            cur_l, pts = L, [(i, j)]
            continue
        pts.append((i, j))
    runs.append((cur_l, pts))
    out = []
    for L, ps in runs:
        keep = [ps[0]]
        for a, b, c in zip(ps, ps[1:], ps[2:]):
            if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
                keep.append(b)
        if len(ps) > 1:
            keep.append(ps[-1])
        out.append((L, [(round(i * G, 3), round(j * G, 3)) for i, j in keep]))
    return out, [(round(i * G, 3), round(j * G, 3)) for i, j in vias]


PLAN = json.loads((Path(__file__).parent / "route_plan.json").read_text())


def main():
    board = kicad_pcb.read(BOARD)
    B = Board(board)
    pads_by_net = defaultdict(list)
    for key, pc in B.pad_cells.items():
        if pc["net"] and not pc["net"].startswith("unconnected") and pc["net"] != "GND":
            pads_by_net[pc["net"]].append((key, pc))
    only = set(sys.argv[1:])            # route just these nets, around everything already on the board
    if only:
        for tr in board.tracks:
            if tr.net not in only:
                for a, b in zip(tr.points, tr.points[1:]):
                    B.add_track(tr.layer, (a[0] - X0, a[1] - Y0), (b[0] - X0, b[1] - Y0), tr.width, B.nid(tr.net))
        for v in board.vias:
            if v.net not in only and v.net != "GND":   # stitching is redone after routing
                B.add_via((v.at[0] - X0, v.at[1] - Y0), B.nid(v.net))
        pads_by_net = {n: v for n, v in pads_by_net.items() if n in only}
        PLAN["gnd_ties"] = []
    order = PLAN["order"]
    nets = sorted(pads_by_net, key=lambda n: (order.index(n) if n in order else len(order),
                                              n not in POWER, len(pads_by_net[n])))
    routes = Routes()
    failed = []
    for net in nets:
        nid = B.nid(net)
        w = PWR_W if net in POWER else SIG_W
        pref = PLAN["layer"].get(net, PLAN["layer"].get(net.split("/")[-1], "B"))
        cost = {"F.Cu": 1.0, "B.Cu": 1.0}
        cost["F.Cu" if pref == "B" else "B.Cu"] = PLAN.get("other_layer_cost", 2.5)
        free = B.free(nid, w)
        pads = pads_by_net[net]
        # connect pads in a minimum-spanning order from the first
        cent = lambda pc: pc["poly"].centroid  # noqa: E731
        tree = {L: np.zeros((NY, NX), bool) for L in ("F.Cu", "B.Cu")}
        core = lambda pc: raster(pc["poly"].buffer(-w / 2 + 0.01)) | raster(Point(pc["poly"].centroid).buffer(0.06))  # noqa: E731
        first = pads[0][1]
        for L in first["layers"]:
            tree[L] |= core(first)
        left = pads[1:]
        done_pts = [cent(first)]
        while left:
            k = min(range(len(left)), key=lambda i: min(cent(left[i][1]).distance(p) for p in done_pts))
            key, pc = left.pop(k)
            cm = core(pc)
            dst = {L: (cm if L in pc["layers"] else np.zeros((NY, NX), bool)) for L in ("F.Cu", "B.Cu")}
            for L in ("F.Cu", "B.Cu"):
                free[L] |= tree[L] | dst[L]
            c = cent(pc)
            near = min(done_pts, key=lambda p: p.distance(c))
            path = None
            for m in (6.0, 15.0, 60.0):
                x0, x1 = min(c.x, near.x) - m, max(c.x, near.x) + m
                y0, y1 = min(c.y, near.y) - m, max(c.y, near.y) + m
                win = (max(0, int(x0 / G)), max(0, int(y0 / G)), min(NX - 1, int(x1 / G)), min(NY - 1, int(y1 / G)))
                path = astar(free, tree, dst, cost, PLAN.get("via_cost", 25.0), win)
                if path:
                    break
            if not path:
                failed.append((net, key[0]))
                continue
            runs, vias = simplify(path)
            for L, pts in runs:
                if len(pts) > 1:
                    routes.t(net, L, *pts, w=w)
                    for a, b in zip(pts, pts[1:]):
                        B.add_track(L, a, b, w, nid)
                        tree[L] |= raster(LineString([a, b]).buffer(0.06))
            for p in vias:
                routes.v(net, p)
                B.add_via(p, nid)
                for L in tree:
                    tree[L] |= raster(Point(p).buffer(0.06))
            for L in pc["layers"]:
                tree[L] |= cm
            done_pts.append(c)
            free = B.free(nid, w)
        print(f"routed {net}: {len(pads)} pads", flush=True)
    # GND ties: a pad the pours cannot reach is joined to a named GND pad by a track of its own
    for a_spec, b_spec in PLAN.get("gnd_ties", []):
        nid = B.nid("GND")
        free = B.free(nid, SIG_W)
        def pc_of(spec):
            ref, num = spec.split(".")
            return next(pc for (r, k), pc in B.pad_cells.items() if r == ref and k.split("@")[0] == num)
        pa, pb = pc_of(a_spec), pc_of(b_spec)
        core = lambda pc: raster(pc["poly"].buffer(-SIG_W / 2 + 0.01)) | raster(Point(pc["poly"].centroid).buffer(0.06))  # noqa: E731
        src = {L: (core(pa) if L in pa["layers"] else np.zeros((NY, NX), bool)) for L in ("F.Cu", "B.Cu")}
        dst = {L: (core(pb) if L in pb["layers"] else np.zeros((NY, NX), bool)) for L in ("F.Cu", "B.Cu")}
        for L in src:
            free[L] |= src[L] | dst[L]
        ca, cb = pa["poly"].centroid, pb["poly"].centroid
        win = (max(0, int((min(ca.x, cb.x) - 6) / G)), max(0, int((min(ca.y, cb.y) - 6) / G)),
               min(NX - 1, int((max(ca.x, cb.x) + 6) / G)), min(NY - 1, int((max(ca.y, cb.y) + 6) / G)))
        path = astar(free, src, dst, {"F.Cu": 3.0, "B.Cu": 1.0}, 40.0, win)
        if not path:
            failed.append(("GND", a_spec))
            continue
        runs, vias = simplify(path)
        for L, pts in runs:
            if len(pts) > 1:
                routes.t("GND", L, *pts, w=SIG_W)
                for a, b in zip(pts, pts[1:]):
                    B.add_track(L, a, b, SIG_W, nid)
        for p in vias:
            routes.v("GND", p)
            B.add_via(p, nid)
    (Path(__file__).parent / "routes.json").write_text(json.dumps({"tracks": routes.tracks, "vias": routes.vias}))
    print("FAILED:", failed)
    with kicad_pcb.edit(BOARD) as b:
        print("sync (tracks+, vias+, tracks-, vias-):", sync(b, routes, only or None))


if __name__ == "__main__":
    main()
