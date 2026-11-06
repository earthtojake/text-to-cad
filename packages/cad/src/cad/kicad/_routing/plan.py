"""The routing of one plan: each entry, in order, joined by the search and pulled tight, on the board as read.

``Router(board, rules, wants)`` reads the board's obstacles into the clearance fields (``field``) and the exact
checker (``tighten.Obstacles``) once, then ``run()`` routes each wanted connection in the plan's order:

- a NET: its pads and the copper already on them fall into islands (pieces of the net's copper that touch, as
  KiCad's connectivity joins them: pads, tracks, vias, a pour's saved fill); starting from the island with the
  most pads, the nearest island not yet joined is joined to the tree each time, Prim's way, until every island
  with a pad is one (a connection that fails leaves its island apart, said, and the next nearest goes on);
- a pair of PADS: just that connection, between the islands of the two pads.

Each connection is searched in a window round its two ends (``search``), wider each time it fails (a margin,
a larger margin, the whole region), on the layers its entry allows, at its width and clearance, under its via
limit; a walled-in end is found by a small flood and said as such. A path found is turned into copper: its runs
on each layer, its vias; each end carried onto its anchor (a pad's position, a via's centre, an axis-aligned
track's centreline); each run pulled tight (``tighten.pull``); a via pair whose two vias an elbow or a straight
on the first layer can join is removed. Every segment and via is then checked once more, exactly, against every
obstacle; a route that fails that check is a bug, raised (the edit then saves nothing). The new copper becomes an
obstacle for everything routed after it, and the tree its net grows from.

Nothing here touches KiCad or a file: the caller (``cad.kicad._route``) reads the board and writes the copper.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

from .board import BoardCopper, Pad, Track, Via
from .field import NO_NET, Fields, move_margin
from .rules import Rules
from .search import flood, search
from .shapes import Shape
from .tighten import NM, Obstacles, elbows, octolinear, pull, straighten

__all__ = ["Connection", "NewTrack", "NewVia", "Router", "Want", "pitch_for"]

Point = tuple[int, int]  # nanometres
XY = tuple[float, float]

#: The most nodes the region's fields hold per layer: a 200 x 200 mm board at 0.1 mm. Past it, route in parts.
MAX_NODES = 4_000_000
#: How much longer than the best a path the search settles for may be (its heuristic's weight).
WEIGHT = 1.2
#: The most states one search expands before it gives up on a window.
BUDGET = 3_000_000
#: How far past a connection's ends each window reaches: a margin, a wider one, then the whole region.
MARGINS = (2.0, 8.0)
#: How many states a flood from a connection's end counts before it calls that end open.
FLOOD = 20_000


def pitch_for(widths: Iterable[float], clearances: Iterable[float]) -> float:
    """The grid's pitch: 0.1 mm where every track and its clearance span 0.4 mm or more, finer where they do not
    (a quarter of the narrowest track plus clearance, 0.05 or 0.025 mm), so a lane two clearances and a width
    wide is always found."""
    span = min(w + c for w, c in zip(widths, clearances))
    for pitch in (0.1, 0.05, 0.025):
        if span / 4 >= pitch - 1e-9:
            return pitch
    return 0.025


@dataclass(frozen=True)
class Want:
    """One connection or net the plan asks for, every value worked out: ``net``; ``pads``, a pair of pad
    references for a single connection, None for the whole net; ``layers``, (copper layer, cost per mm) in the
    order given; the track ``width``, the ``clearance`` it keeps, the via (``via_diameter``, ``via_drill``), the
    most ``vias`` it may place (None: no limit) and what a via costs (``via_cost``, in mm of track)."""

    net: str
    pads: tuple[str, str] | None
    layers: tuple[tuple[str, float], ...]
    width: float
    clearance: float
    via_diameter: float
    via_drill: float
    vias: int | None
    via_cost: float

    @property
    def name(self) -> str:
        return f"{self.pads[0]} to {self.pads[1]}" if self.pads else f"net {self.net}"


@dataclass(frozen=True)
class Connection:
    """What became of one connection: ``net``; ``between``, the two ends (a pad, or the copper of the net it
    joined); ``routed`` or not, and ``reason`` why not; the copper it added."""

    net: str
    between: tuple[str, str]
    routed: bool
    reason: str | None = None
    tracks: int = 0
    vias: int = 0
    length: float = 0.0

    def line(self) -> str:
        what = f"{self.net}: {self.between[0]} to {self.between[1]}"
        if self.routed and self.reason:
            return f"{what}: {self.reason}"
        if self.routed:
            via = f", {self.vias} via{'s' if self.vias != 1 else ''}" if self.vias else ""
            return f"routed {what}: {self.length:.2f} mm in {self.tracks} segment{'s' if self.tracks != 1 else ''}{via}"
        return f"NOT routed {what}: {self.reason}"


@dataclass(frozen=True)
class NewTrack:
    net: str
    layer: str
    width: float
    start: Point
    end: Point


@dataclass(frozen=True)
class NewVia:
    net: str
    at: Point
    diameter: float
    drill: float


# --- the net's copper, as items the router joins -----------------------------------------------------------------


@dataclass
class _Item:
    """A piece of a net's copper: a pad, a track, a via or a pour's fill; its shapes, the layers it is on, its
    anchors (where a route may end on it: a pad's position, a via's centre, a track's ends) and what it is."""

    kind: str
    layers: tuple[str, ...]
    shapes: tuple[Shape, ...]
    anchors: tuple[XY, ...]
    pad: Pad | None = None
    track: Track | None = None
    via: Via | None = None
    fill: np.ndarray | None = None
    name: str = ""


def _fill_holds(fill: np.ndarray, points: Sequence[XY]) -> bool:
    """Whether a pour's fill holds any of ``points`` (even-odd, vectorized over its edges)."""
    x1, y1 = fill[:, 0], fill[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    for px, py in points:
        straddles = (y1 > py) != (y2 > py)
        with np.errstate(divide="ignore", invalid="ignore"):
            crossing = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
        if np.count_nonzero(straddles & (px < crossing)) % 2:
            return True
    return False


def _touch(a: _Item, b: _Item) -> bool:
    """Whether two pieces of one net's copper are joined: a layer in common and their shapes meet (a fill by
    holding the other's anchors, as KiCad's connectivity tests a pour)."""
    if not set(a.layers) & set(b.layers):
        return False
    if a.fill is not None or b.fill is not None:
        fill, other = (a, b) if a.fill is not None else (b, a)
        if other.fill is not None:
            return False  # two pours of one net meet through what lies on them
        return _fill_holds(fill.fill, other.anchors)
    for one in a.shapes:
        for two in b.shapes:
            if one.box[0] > two.box[2] or two.box[0] > one.box[2] or one.box[1] > two.box[3] or two.box[1] > one.box[3]:
                continue
            if _shapes_meet(one, two):
                return True
    return False


def _shapes_meet(one: Shape, two: Shape) -> bool:
    if one.kind in ("point", "segment"):
        a, b = one.points[0], one.points[-1]
        return two.segment_distance(a, b) <= one.radius + 1e-6
    if two.kind in ("point", "segment"):
        return _shapes_meet(two, one)
    if one.kind == "polygon":
        ring = one.points
        if any(two.segment_distance(p, q) <= one.radius + 1e-6 for p, q in zip(ring, ring[1:] + ring[:1])):
            return True
        anchor = two.points[0] if two.kind == "polygon" else two.points[1]
        return one.contains(*anchor)
    if two.kind == "polygon":
        return _shapes_meet(two, one)
    (_, start, end) = one.points  # two arcs: their ends against each other, enough for copper KiCad draws
    return two.segment_distance(start, end) <= one.radius + 1e-6


def _islands(items: Sequence[_Item]) -> list[list[_Item]]:
    parent = list(range(len(items)))

    def find(k: int) -> int:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if find(i) != find(j) and _touch(items[i], items[j]):
                parent[max(find(i), find(j))] = min(find(i), find(j))
    groups: dict[int, list[_Item]] = {}
    for k, item in enumerate(items):
        groups.setdefault(find(k), []).append(item)
    return list(groups.values())


def _natural(text: str) -> tuple:
    import re

    return tuple((0, int(chunk), "") if chunk.isdigit() else (1, 0, chunk) for chunk in re.split(r"(\d+)", text) if chunk)


def _island_name(island: Sequence[_Item]) -> str:
    pads = sorted((item.name for item in island if item.kind == "pad" and item.name), key=_natural)
    return pads[0] if pads else "its copper"


def _nm(point: XY) -> Point:
    return round(point[0] * NM), round(point[1] * NM)


def _mm(point: Point) -> XY:
    return point[0] / NM, point[1] / NM


# --- the router ----------------------------------------------------------------------------------------------------


@dataclass
class _Window:
    rows: slice
    cols: slice
    nx: int  # with the padding
    ny: int
    i0: int  # the lattice node of the window's first (padding) column and row
    j0: int


class Router:
    """The routing of ``wants`` on ``board`` by ``rules``: ``run()`` answers each connection's outcome and the new
    copper (see the module's doc)."""

    def __init__(self, board: BoardCopper, rules: Rules, wants: Sequence[Want]):
        self.board, self.rules, self.wants = board, rules, list(wants)
        self.copper = list(board.copper)
        self.layer_of = {name: k for k, name in enumerate(self.copper)}
        names = sorted({pad.net for pad in board.pads if pad.net} | {t.net for t in board.tracks if t.net}
                       | {v.net for v in board.vias if v.net} | {want.net for want in wants})
        self.net_id = {name: k for k, name in enumerate(names)}
        self.pitch = pitch_for([w.width for w in wants], [w.clearance for w in wants])
        self.g_nm = round(self.pitch * NM)
        self.epsilon = rules.epsilon
        local = [pad.clearance or 0.0 for pad in board.pads]
        widest = max([w.width / 2 for w in wants] + [w.via_diameter / 2 for w in wants] + [0.0])
        biggest = max([rules.clearance(net) for net in self.net_id] + [w.clearance for w in wants] + local
                      + [rules.holes, rules.edge + 0.005, rules.hole_gap + max(w.via_drill for w in wants) / 2, 0.0])
        self.reach = biggest + widest + 0.2
        self.started = time.monotonic()
        self._region()
        self.fields = Fields(self.i0, self.j0, self.nx, self.ny, self.pitch, self.copper, self.reach)
        self.obstacles = Obstacles(len(self.copper), self.reach)
        self.tracks: list[NewTrack] = []
        self.vias: list[NewVia] = []
        self._own: dict[str, list[_Item]] = {}  # each net's copper as items, the new copper added as it lands
        self._last: list[_Item] = []  # the copper the last connection added
        self._read_obstacles()

    # --- the region and its obstacles ------------------------------------------------------------------------

    def _region(self) -> None:
        """The region the fields cover: the board's outline's box, or (no outline) its pads' box, a margin round
        it; refused past ``MAX_NODES`` a layer."""
        points = [p for ring in self.board.outline for p in ring] or [pad.at for pad in self.board.pads]
        if not points:
            raise ValueError("the board has no outline and no pads: nothing to route on")
        g, grow = self.pitch, self.reach + 1.0
        x0, y0 = min(p[0] for p in points) - grow, min(p[1] for p in points) - grow
        x1, y1 = max(p[0] for p in points) + grow, max(p[1] for p in points) + grow
        self.i0, self.j0 = math.floor(x0 / g), math.floor(y0 / g)
        self.nx, self.ny = math.ceil(x1 / g) - self.i0 + 1, math.ceil(y1 / g) - self.j0 + 1
        if self.nx * self.ny > MAX_NODES:
            raise ValueError(f"the board spans {x1 - x0:.0f} x {y1 - y0:.0f} mm, {self.nx * self.ny:,} nodes a layer at "
                             f"the {g} mm pitch its rules need: more than the router holds ({MAX_NODES:,})")

    def _ids(self, layers: Iterable[str]) -> list[int]:
        return [self.layer_of[layer] for layer in layers if layer in self.layer_of]

    def _net(self, name: str | None) -> int:
        return self.net_id.get(name, NO_NET) if name else NO_NET

    def _read_obstacles(self) -> None:
        board, rules, fields, obstacles = self.board, self.rules, self.fields, self.obstacles
        every = list(range(len(self.copper)))
        for pad in board.pads:
            keep, net, layers = rules.clearance(pad.net, pad.clearance), self._net(pad.net), self._ids(pad.layers)
            fields.add_copper(pad.copper, layers, net, keep)
            fields.add_pad(pad.copper)
            for shape in pad.copper:
                obstacles.add("copper", shape, layers, net, keep)
                obstacles.add("pad", shape, [], net)
            if pad.hole is not None:
                fields.add_hole(pad.hole, net, rules.holes, every)
                obstacles.add("hole", pad.hole, every, net)
            self._item(pad.net, _Item("pad", pad.layers, pad.copper, (pad.at,), pad=pad, name=pad.ref))
        for track in board.tracks:
            keep, net, layers = rules.clearance(track.net), self._net(track.net), self._ids([track.layer])
            fields.add_copper([track.shape], layers, net, keep)
            obstacles.add("copper", track.shape, layers, net, keep)
            self._item(track.net, _Item("track", (track.layer,), (track.shape,), track.ends, track=track))
        for via in board.vias:
            keep, net, layers = rules.clearance(via.net), self._net(via.net), self._ids(via.layers)
            disc, drill = Shape.point(*via.at, via.diameter / 2), Shape.point(*via.at, via.drill / 2)
            fields.add_copper([disc], layers, net, keep)
            fields.add_hole(drill, net, rules.holes, every)
            obstacles.add("copper", disc, layers, net, keep)
            obstacles.add("hole", drill, every, net)
            self._item(via.net, _Item("via", via.layers, (disc,), (via.at,), via=via))
        for graphic in board.graphics:
            keep, net, layers = rules.clearance(graphic.net), self._net(graphic.net), self._ids([graphic.layer])
            fields.add_copper(graphic.shapes, layers, net, keep)
            for shape in graphic.shapes:
                obstacles.add("copper", shape, layers, net, keep)
        for hole in board.holes:
            fields.add_hole(hole, NO_NET, rules.holes, every)
            obstacles.add("hole", hole, every, NO_NET)
        for keepout in board.keepouts:
            layers = self._ids(keepout.layers)
            fields.add_keepout(keepout.shape, layers, keepout.tracks, keepout.vias)
            if keepout.tracks:
                obstacles.add("tracks", keepout.shape, layers, NO_NET)
            if keepout.vias:
                obstacles.add("vias", keepout.shape, [], NO_NET)
        for fill in board.fills:
            self._item(fill.net, _Item("fill", (fill.layer,), (), (), fill=np.array(fill.points, dtype=float)))
        # The outline as KiCad's chords: its arcs may lie up to CHORD_TOLERANCE outside them (Rules.edge adds it).
        fields.set_edge(board.outline)
        obstacles.set_edge(board.outline)

    def _item(self, net: str | None, item: _Item) -> None:
        if net:
            self._own.setdefault(net, []).append(item)

    # --- the plan ----------------------------------------------------------------------------------------------

    def run(self) -> list[Connection]:
        done: list[Connection] = []
        for want in self.wants:
            done += self._route(want)
        return done

    def _route(self, want: Want) -> list[Connection]:
        if want.pads:
            a, b = self.board.pad(want.pads[0]), self.board.pad(want.pads[1])
            islands = _islands(self._own.get(want.net, []))
            first = next(island for island in islands if any(item.pad is a for item in island))
            second = next(island for island in islands if any(item.pad is b for item in island))
            if first is second:
                return [Connection(want.net, want.pads, True, "already joined by the copper on the board")]
            return [self._join(want, first, second, want.pads)]
        islands = [island for island in _islands(self._own.get(want.net, [])) if any(item.kind == "pad" for item in island)]
        if len(islands) < 2:
            return []
        islands.sort(key=lambda island: (-sum(item.kind == "pad" for item in island), _natural(_island_name(island))))
        tree, apart = islands[0], islands[1:]
        done = []
        while apart:
            nearest = min(range(len(apart)), key=lambda k: (self._gap(tree, apart[k]), _natural(_island_name(apart[k]))))
            island = apart.pop(nearest)
            outcome = self._join(want, tree, island, (self._nearest_name(tree, island), _island_name(island)))
            done.append(outcome)
            if outcome.routed:
                tree = tree + island + self._last
                # An island the new copper crossed on its way (the net's own pad, say) is joined already.
                crossed = [k for k, other in enumerate(apart) if any(_touch(new, item) for new in self._last for item in other)]
                for k in reversed(crossed):
                    tree = tree + apart.pop(k)
        return done

    @staticmethod
    def _nearest_name(tree: Sequence[_Item], island: Sequence[_Item]) -> str:
        """The pad of ``tree`` nearest ``island``: the end a connection to it is named by."""
        pads = [item for item in tree if item.kind == "pad" and item.name]
        if not pads:
            return "its copper"
        return min(pads, key=lambda pad: (min(math.dist(pad.anchors[0], q) for b in island for q in b.anchors),
                                          _natural(pad.name))).name

    @staticmethod
    def _gap(tree: Sequence[_Item], island: Sequence[_Item]) -> float:
        return min((math.dist(p, q) for a in tree for p in a.anchors for b in island for q in b.anchors), default=math.inf)

    # --- one connection ----------------------------------------------------------------------------------------

    def _window(self, boxes: Sequence[tuple[float, float, float, float]], margin: float | None) -> _Window:
        g = self.pitch
        if margin is None:
            c0, c1, r0, r1 = 0, self.nx, 0, self.ny
        else:
            x0, y0 = min(b[0] for b in boxes) - margin, min(b[1] for b in boxes) - margin
            x1, y1 = max(b[2] for b in boxes) + margin, max(b[3] for b in boxes) + margin
            c0, c1 = max(0, math.floor(x0 / g) - self.i0), min(self.nx, math.ceil(x1 / g) - self.i0 + 1)
            r0, r1 = max(0, math.floor(y0 / g) - self.j0), min(self.ny, math.ceil(y1 / g) - self.j0 + 1)
        return _Window(slice(r0, r1), slice(c0, c1), c1 - c0 + 2, r1 - r0 + 2, self.i0 + c0 - 1, self.j0 + r0 - 1)

    def _terminals(self, items: Sequence[_Item], window: _Window, allowed: Sequence[int]) -> dict[int, _Item]:
        """The states (layer * nodes + node) a route may start or end on in ``items``: nodes inside a pad's or a
        via's copper, or on a track's centreline (within its width), on each allowed layer it is on."""
        g, nodes = self.pitch, window.nx * window.ny
        found: dict[int, _Item] = {}
        for item in items:
            layers = [self.layer_of[layer] for layer in item.layers if self.layer_of.get(layer) in allowed]
            if not layers or item.kind == "fill":
                continue
            if item.kind == "track":
                (a, b), half = item.track.ends, item.track.width / 2
                shapes = [Shape.segment(a, b, 0.0) if item.track.shape.kind != "arc" else item.track.shape]
                inside = max(half - 0.01, 0.0) if item.track.shape.kind != "arc" else half
            else:
                shapes, inside = (list(item.pad.inner) if item.kind == "pad" else list(item.shapes)), 0.0
            for shape in shapes:
                box = shape.box
                c0 = max(1, math.floor((box[0] - inside) / g) - window.i0)
                c1 = min(window.nx - 1, math.ceil((box[2] + inside) / g) - window.i0 + 1)
                r0 = max(1, math.floor((box[1] - inside) / g) - window.j0)
                r1 = min(window.ny - 1, math.ceil((box[3] + inside) / g) - window.j0 + 1)
                if c0 >= c1 or r0 >= r1:
                    continue
                X, Y = np.meshgrid((window.i0 + np.arange(c0, c1)) * g, (window.j0 + np.arange(r0, r1)) * g)
                distance = shape.grid_distance(X, Y)
                if item.kind == "track" and item.track.shape.kind == "arc":
                    hit = distance <= 0.0  # grown by half its width already; a node in its copper
                else:
                    hit = distance <= inside + 1e-9
                rows, cols = np.nonzero(hit)
                for r, c in zip((rows + r0).tolist(), (cols + c0).tolist()):
                    node = r * window.nx + c
                    for layer in layers:
                        found.setdefault(allowed.index(layer) * nodes + node, item)
        return found

    def _maps(self, want: Want, window: _Window, allowed: Sequence[int], net: int
              ) -> tuple[bytearray, bytearray, list[np.ndarray]]:
        """The window's free nodes per allowed layer, where a via fits, and each layer's room (for pull-tight's
        quick refusals): padded by one blocked node all round."""
        f, rows, cols = self.fields, window.rows, window.cols
        half = want.width / 2
        nearest = min(want.clearance, self.rules.holes, self.rules.edge)
        need = move_margin(half + nearest, self.pitch) + self.epsilon
        need_keepout = move_margin(half, self.pitch) + self.epsilon
        free = bytearray()
        rooms = []
        for layer in allowed:
            room = f.track_room(rows, cols, layer, net, want.clearance, self.rules.edge) - np.float32(half)
            keep = f.keepout_room(rows, cols, layer) - np.float32(half)
            ok = (room >= need) & (keep >= need_keepout)
            rooms.append(np.minimum(room, keep))
            free += np.pad(ok, 1).astype(np.uint8).tobytes()
        if len(allowed) > 1 and want.vias != 0:
            room = f.via_room(rows, cols, net, want.clearance, self.rules.edge, want.via_diameter / 2,
                              want.via_drill / 2, self.rules.holes, self.rules.hole_gap)
            via_ok = bytearray(np.pad(room >= self.epsilon, 1).astype(np.uint8).tobytes())
        else:
            via_ok = bytearray(window.nx * window.ny)
        return free, via_ok, rooms

    def _swaps(self, items: Sequence[_Item], window: _Window, allowed: Sequence[int]) -> bytearray:
        """Where a route changes layer for nothing: inside the net's own through-hole pads and vias, on allowed
        layers both."""
        swap = bytearray(window.nx * window.ny)
        if len(allowed) < 2:
            return swap
        names = {self.copper[k] for k in allowed}
        multi = [item for item in items if item.kind in ("pad", "via") and len(names & set(item.layers)) >= 2]
        for node in self._terminals(multi, window, allowed):
            swap[node % (window.nx * window.ny)] = 1
        return swap

    def _join(self, want: Want, source: Sequence[_Item], target: Sequence[_Item], between: tuple[str, str]) -> Connection:
        self._last = []
        net = self._net(want.net)
        allowed = [self.layer_of[layer] for layer, _ in want.layers]
        costs = [cost for _, cost in want.layers]
        boxes_target = [shape.box for item in target for shape in item.shapes] or [
            (*p, *p) for item in target for p in item.anchors]
        near = min(((math.dist(p, q), p) for a in source for p in a.anchors for b in target for q in b.anchors),
                   default=(0.0, None))[1]
        boxes = boxes_target + ([(near[0], near[1], near[0], near[1])] if near else [])
        reason = None
        own = self._own.get(want.net, [])
        layers = " and ".join(self.copper[k] for k in allowed)
        for margin in (*MARGINS, None):
            window = self._window(boxes, margin)
            sources = self._terminals(source, window, allowed)
            targets = self._terminals(target, window, allowed)
            free, via_ok, rooms = self._maps(want, window, allowed, net)
            if not any(free[s] for s in targets):
                reason = (f"{between[1]} has no room for a {want.width:g} mm track keeping {want.clearance:g} mm on "
                          f"{' or '.join(self.copper[k] for k in allowed)}")
                break
            if not any(free[s] for s in sources):
                if margin is None:
                    reason = f"{between[0]} has no room for a {want.width:g} mm track keeping {want.clearance:g} mm on {layers}"
                    break
                continue
            swap = self._swaps(own, window, allowed)
            if margin is None:  # the last window, the whole region: an end walled in is said before a long search
                walled = self._walled(want, window, free, via_ok, swap, sources, targets, between, layers)
                if walled:
                    reason = walled
                    break
            goal = bytearray(len(allowed) * window.nx * window.ny)
            for state in targets:
                goal[state] = 1
            heuristic = self._heuristic(window, boxes_target, min(costs))
            found, expanded, out = search(free, len(allowed), window.nx, window.ny, self.pitch, costs, via_ok, swap,
                                          want.via_cost, want.vias, list(sources), goal, heuristic, BUDGET)
            if found is not None:
                return self._land(want, net, found, window, allowed, sources, targets, rooms, between)
            limit = f" with at most {want.vias} via{'s' if want.vias != 1 else ''}" if want.vias is not None else ""
            reason = f"the search gave up after {expanded:,} steps" if out else f"no way through on {layers}{limit}"
        return Connection(want.net, between, False, reason)

    def _walled(self, want: Want, window: _Window, free: bytearray, via_ok: bytearray, swap: bytearray, sources: dict,
                targets: dict, between: tuple[str, str], layers: str) -> str | None:
        """Why one end of a connection is walled in, when a small flood from it fills its room without meeting the
        other end; None when both have a way out."""
        count = len(free)
        for ends, others, name in ((targets, sources, between[1]), (sources, targets, between[0])):
            marks = bytearray(count)
            for state in others:
                marks[state] = 1
            reached, met = flood(free, count // (window.nx * window.ny), window.nx, window.ny, via_ok, swap,
                                 [state for state in ends if free[state]], marks, FLOOD)
            if reached < FLOOD and not met:
                area = reached * self.pitch ** 2 / (count // (window.nx * window.ny))
                return (f"{name} is walled in: no way out of the {area:.1f} mm² round it on {layers} for a "
                        f"{want.width:g} mm track keeping {want.clearance:g} mm")
        return None

    def _heuristic(self, window: _Window, boxes: Sequence[tuple[float, float, float, float]], cheapest: float) -> list[float]:
        g = self.pitch
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        X, Y = np.meshgrid((window.i0 + np.arange(window.nx)) * g, (window.j0 + np.arange(window.ny)) * g)
        dx = np.maximum(np.maximum(x0 - X, X - x1), 0.0)
        dy = np.maximum(np.maximum(y0 - Y, Y - y1), 0.0)
        octile = np.maximum(dx, dy) + (math.sqrt(2.0) - 1.0) * np.minimum(dx, dy)
        return (octile * (cheapest * WEIGHT)).ravel().tolist()

    # --- the path found, as copper ------------------------------------------------------------------------------

    def _node_nm(self, window: _Window, node: int) -> Point:
        r, c = divmod(node, window.nx)
        return (window.i0 + c) * self.g_nm, (window.j0 + r) * self.g_nm

    def _anchor(self, item: _Item, at: Point) -> Point | None:
        """Where a route that reaches ``item`` at ``at`` ends on it: a pad's position, a via's centre, the foot on
        an axis-aligned track's centreline; None to end where it is (inside the copper already)."""
        if item.kind == "pad":
            return _nm(item.pad.at)
        if item.kind == "via":
            return _nm(item.via.at)
        if item.kind == "track" and item.track.shape.kind == "segment":
            (ax, ay), (bx, by) = (_nm(p) for p in item.track.ends)
            if ay == by and min(ax, bx) <= at[0] <= max(ax, bx):
                return at[0], ay
            if ax == bx and min(ay, by) <= at[1] <= max(ay, by):
                return ax, at[1]
        return None

    def _clear(self, want: Want, net: int, layer: int, room: np.ndarray | None, window: _Window | None):
        """The exact check of a segment of this route on ``layer`` (nanometres), with a quick refusal from the
        window's room where the room proves it blocked (it is 1-Lipschitz: a node with less room than minus its
        distance to a point has none at that point)."""
        rules, half, g = self.rules, want.width / 2, self.pitch
        slack = g * math.sqrt(2.0) / 2

        def clear(a: Point, b: Point) -> bool:
            pa, pb = _mm(a), _mm(b)
            if room is not None and window is not None:
                steps = max(1, math.ceil(math.dist(pa, pb) / (g / 2)))
                t = np.linspace(0.0, 1.0, steps + 1)
                c = np.rint((pa[0] + (pb[0] - pa[0]) * t) / g).astype(int) - window.i0 - 1
                r = np.rint((pa[1] + (pb[1] - pa[1]) * t) / g).astype(int) - window.j0 - 1
                inside = (c >= 0) & (c < room.shape[1]) & (r >= 0) & (r < room.shape[0])
                if np.any(room[r[inside], c[inside]] < -slack):
                    return False
            return self.obstacles.segment_clear(layer, pa, pb, half, net, want.clearance, rules.holes, rules.edge,
                                                self.epsilon)

        return clear

    def _via_clear(self, want: Want, net: int, at: Point) -> bool:
        rules = self.rules
        return self.obstacles.via_clear(_mm(at), want.via_diameter / 2, want.via_drill / 2, net, want.clearance,
                                        rules.holes, rules.hole_gap, rules.edge, self.epsilon)

    def _land(self, want: Want, net: int, found, window: _Window, allowed: Sequence[int], sources: dict,
              targets: dict, rooms: list[np.ndarray], between: tuple[str, str]) -> Connection:
        nodes = window.nx * window.ny
        steps = found.steps
        runs: list[tuple[int, list[Point]]] = []
        vias: list[Point] = []
        for (layer, node), nxt in zip(steps, (*steps[1:], None)):
            point = self._node_nm(window, node)
            if not runs or runs[-1][0] != layer:
                runs.append((layer, [point]))
            else:
                runs[-1][1].append(point)
            if nxt is not None and nxt[0] != layer and node in found.vias:
                vias.append(point)
        raw = [(layer, straighten(points)) for layer, points in runs]
        first, last = sources[steps[0][0] * nodes + steps[0][1]], targets[steps[-1][0] * nodes + steps[-1][1]]
        tight = self._tighten(want, net, raw, list(vias), first, last, window, rooms)
        if not self._verified(want, net, *tight, allowed):
            tight = (raw, list(vias))
            if not self._verified(want, net, *tight, allowed):
                raise AssertionError(f"the route of {want.net} ({between[0]} to {between[1]}) failed its own exact "
                                     "clearance check: a bug in the router; nothing is written")
        runs_out, vias_out = tight
        return self._commit(want, net, runs_out, vias_out, allowed, between)

    def _tighten(self, want: Want, net: int, runs: list[tuple[int, list[Point]]], vias: list[Point], first: _Item,
                 last: _Item, window: _Window, rooms: list[np.ndarray]):
        """The runs with their ends carried onto their anchors (where a clear straight or elbow reaches one) and each
        pulled tight; a via pair a straight or an elbow on the first layer can replace, removed."""
        allowed = [self.layer_of[layer] for layer, _ in want.layers]
        clears = {k: self._clear(want, net, allowed[k], rooms[k], window) for k in range(len(allowed))}
        runs = [(layer, list(points)) for layer, points in runs]

        def carried(points: list[Point], item: _Item, k: int, at_start: bool) -> list[Point]:
            end = points[0] if at_start else points[-1]
            anchor = self._anchor(item, end)
            if anchor is None or anchor == end:
                return points
            clear = clears[k]
            joints: list[list[Point]] = [[]] if octolinear(end, anchor) else [[c] for c in elbows(end, anchor)]
            for joint in joints:
                path = [end, *joint, anchor]
                if all(clear(a, b) for a, b in zip(path, path[1:])):
                    added = [*joint, anchor]
                    return ([*reversed(added), *points] if at_start else [*points, *added])
            return points

        runs[0] = (runs[0][0], carried(runs[0][1], first, runs[0][0], True))
        runs[-1] = (runs[-1][0], carried(runs[-1][1], last, runs[-1][0], False))
        runs = [(layer, pull(points, clears[layer])) for layer, points in runs]
        # A via pair round a run on another layer, joined on the first layer instead.
        k = 0
        while k + 2 < len(runs):
            (a, before), (_, middle), (c, after) = runs[k], runs[k + 1], runs[k + 2]
            if a == c and before[-1] in vias and after[0] in vias:
                start, end = before[-1], after[0]
                joints = [[]] if octolinear(start, end) else [[corner] for corner in elbows(start, end)]
                for joint in joints:
                    path = [start, *joint, end]
                    if all(clears[a](p, q) for p, q in zip(path, path[1:])):
                        merged = pull([*before, *joint, *after], clears[a])
                        vias = [v for v in vias if v not in (start, end)]
                        runs[k:k + 3] = [(a, merged)]
                        break
                else:
                    k += 1
                continue
            k += 1
        return [(layer, straighten(points)) for layer, points in runs], vias

    def _verified(self, want: Want, net: int, runs, vias, allowed: Sequence[int]) -> bool:
        rules, half = self.rules, want.width / 2
        for layer, points in runs:
            board_layer = self.layer_of[self.copper[allowed[layer]]]
            for a, b in zip(points, points[1:]):
                if not octolinear(a, b) or not self.obstacles.segment_clear(
                        board_layer, _mm(a), _mm(b), half, net, want.clearance, rules.holes, rules.edge, self.epsilon):
                    return False
        return all(self._via_clear(want, net, at) for at in vias)

    def _commit(self, want: Want, net: int, runs, vias, allowed: Sequence[int], between: tuple[str, str]) -> Connection:
        rules, fields, obstacles = self.rules, self.fields, self.obstacles
        every = list(range(len(self.copper)))
        keep = max(want.clearance, rules.clearance(want.net))
        count, length = 0, 0.0
        for layer, points in runs:
            name = self.copper[allowed[layer]]
            board_layer = self.layer_of[name]
            for a, b in zip(points, points[1:]):
                pa, pb = _mm(a), _mm(b)
                shape = Shape.segment(pa, pb, want.width / 2)
                fields.add_copper([shape], [board_layer], net, keep)
                obstacles.add("copper", shape, [board_layer], net, keep)
                track = Track(want.net, name, want.width, shape, (pa, pb))
                self._item(want.net, item := _Item("track", (name,), (shape,), (pa, pb), track=track))
                self._last.append(item)
                self.tracks.append(NewTrack(want.net, name, want.width, a, b))
                count += 1
                length += math.dist(pa, pb)
        for at in vias:
            p = _mm(at)
            disc, drill = Shape.point(*p, want.via_diameter / 2), Shape.point(*p, want.via_drill / 2)
            fields.add_copper([disc], every, net, keep)
            fields.add_hole(drill, net, rules.holes, every)
            obstacles.add("copper", disc, every, net, keep)
            obstacles.add("hole", drill, every, net)
            via = Via(want.net, p, want.via_diameter, want.via_drill, tuple(self.copper))
            self._item(want.net, item := _Item("via", tuple(self.copper), (disc,), (p,), via=via))
            self._last.append(item)
            self.vias.append(NewVia(want.net, at, want.via_diameter, want.via_drill))
        return Connection(want.net, between, True, None, count, len(vias), length)
