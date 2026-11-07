"""The routing as data: tracks and vias in board-local millimetres, LFO A's copied 25 mm right for LFO B
(nets renamed /LFO A/ -> /LFO B/), and a sync that makes the board hold exactly these (state, not steps)."""

from __future__ import annotations

from boardlib import LFO_PITCH, X0, Y0

SIG, PWR = 0.25, 0.4
VIA_D, VIA_DRILL = 0.8, 0.4


class Routes:
    def __init__(self):
        self.tracks: list[tuple[str, str, float, tuple, tuple]] = []   # net, layer, width, a, b
        self.vias: list[tuple[str, tuple]] = []

    def t(self, net: str, layer: str, *pts, w: float = SIG):
        for a, b in zip(pts, pts[1:]):
            if a != b:
                self.tracks.append((net, layer, w, tuple(a), tuple(b)))

    def f(self, net, *pts, w=SIG):
        self.t(net, "F.Cu", *pts, w=w)

    def b(self, net, *pts, w=SIG):
        self.t(net, "B.Cu", *pts, w=w)

    def v(self, net, *pts):
        for p in pts:
            self.vias.append((net, tuple(p)))

    def lfo_b(self) -> "Routes":
        out = Routes()

        def net_b(n: str) -> str:
            return n.replace("/LFO A/", "/LFO B/")
        for net, layer, w, a, b in self.tracks:
            out.tracks.append((net_b(net), layer, w, (a[0] + LFO_PITCH, a[1]), (b[0] + LFO_PITCH, b[1])))
        for net, p in self.vias:
            out.vias.append((net_b(net), (p[0] + LFO_PITCH, p[1])))
        return out

    def __iadd__(self, other: "Routes"):
        self.tracks += other.tracks
        self.vias += other.vias
        return self


def key_track(net, layer, w, a, b):
    a, b = (round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))
    return (net, layer, round(w, 3)) + tuple(sorted([a, b]))


def sync(board, routes: Routes, only=None) -> tuple[int, int, int, int]:
    """Make the board's tracks and vias exactly the routes'. Returns (added, removed) tracks and vias."""
    from kicode.board_types import Track, Via
    from kicode.geometry import Vector2
    from kicode.proto.board.board_types_pb2 import BoardLayer
    from kicode.util.units import from_mm

    layers = {"F.Cu": BoardLayer.BL_F_Cu, "B.Cu": BoardLayer.BL_B_Cu}
    names = {v: k for k, v in layers.items()}
    nets = {n.name: n for n in board.get_nets()}
    want_t = {key_track(*t): t for t in routes.tracks}
    want_v = {(n, round(p[0], 3), round(p[1], 3)): (n, p) for n, p in routes.vias}
    have_t, have_v = {}, {}
    for tr in board.get_tracks():
        if not hasattr(tr, "start") or type(tr).__name__ != "Track":
            continue
        a = (tr.start.x / 1e6 - X0, tr.start.y / 1e6 - Y0)
        b = (tr.end.x / 1e6 - X0, tr.end.y / 1e6 - Y0)
        have_t.setdefault(key_track(tr.net.name, names.get(tr.layer, "?"), tr.width / 1e6, a, b), []).append(tr)
    for via in board.get_vias():
        p = (via.position.x / 1e6 - X0, via.position.y / 1e6 - Y0)
        have_v.setdefault((via.net.name, round(p[0], 3), round(p[1], 3)), []).append(via)
    # GND vias are the stitching's (board_04_pour.py): never touched here; GND tracks are the routes' ties
    if only:   # touch only these nets' items
        have_t = {k: v for k, v in have_t.items() if k[0] in only}
        have_v = {k: v for k, v in have_v.items() if k[0] in only}
    drop = [x for k, v in have_t.items() for x in (v if k not in want_t else v[1:])]
    drop += [x for k, v in have_v.items() if k[0] != "GND" for x in (v if k not in want_v else v[1:])]
    if drop:
        board.remove_items(drop)
    add = []
    missing_nets = set()
    for k, (net, layer, w, a, b) in want_t.items():
        if k in have_t:
            continue
        if net not in nets:
            missing_nets.add(net)
            continue
        tr = Track()
        tr.start = Vector2.from_xy_mm(X0 + a[0], Y0 + a[1])
        tr.end = Vector2.from_xy_mm(X0 + b[0], Y0 + b[1])
        tr.width = from_mm(w)
        tr.layer = layers[layer]
        tr.net = nets[net]
        add.append(tr)
    for k, (net, p) in want_v.items():
        if k in have_v:
            continue
        if net not in nets:
            missing_nets.add(net)
            continue
        via = Via()
        via.position = Vector2.from_xy_mm(X0 + p[0], Y0 + p[1])
        via.diameter = from_mm(VIA_D)
        via.drill_diameter = from_mm(VIA_DRILL)
        via.net = nets[net]
        add.append(via)
    if missing_nets:
        raise SystemExit(f"no such nets on the board: {sorted(missing_nets)}")
    if add:
        board.create_items(add)
    n_add_t = sum(1 for x in add if type(x).__name__ == "Track")
    return n_add_t, len(add) - n_add_t, sum(1 for x in drop if type(x).__name__ == "Track"), sum(1 for x in drop if type(x).__name__ == "Via")
