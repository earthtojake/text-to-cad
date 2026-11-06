"""The clearance fields: for every node of the routed region's grid, how much room each kind of obstacle leaves.

The grid is a lattice at ``pitch`` millimetres, aligned to multiples of it (node (i, j) of the region is at
((i0 + i) * pitch, (j0 + j) * pitch)), so two regions over the same board agree on every node they share. Per
copper layer it keeps two fields of the other copper and the holes:

- ``F``: the least ``distance - clearance`` to an obstacle, each obstacle's own clearance (a pad's netclass or
  local clearance, a hole's ``hole_clearance``);
- ``D``: the least raw distance to copper alone.

Copper of net N must keep max(c_N, c_o) from obstacle o, so the room a track of net N has at a node is
``min(F, D - c_N)`` (the larger clearance wins either way), less its half width. N's own copper is no obstacle
to N, so each field holds, per node, its least value, the net that has it, and the least value of any OTHER
net: asking for net N answers the second where N has the first. A value is merged in place (``_merge``), so the
fields grow as each route lands, and the copper already routed is an obstacle to every net routed after it.

Beside them: ``K`` per layer, the distance to the track keep-outs on that layer (rule areas, the board's and the
footprints'); ``KV`` the distance to any via keep-out; ``H`` the distance to any hole of any net (a via's drill
keeps ``hole_to_hole`` from every hole, its own net's too); ``P`` the distance to any pad (no via lands in a
pad); ``E`` the signed distance to the board's edge, inside positive. Distances further than ``reach`` from
everything stay ``inf``: no question asks about room beyond it. Float32: a hundredth of a micron at 100 mm.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .shapes import Shape

__all__ = ["Fields", "move_margin"]

FAR = np.float32(np.inf)
NO_NET = -1  # an obstacle of no net: keep-outs, unplated holes, the edge, copper KiCad gives no net


def move_margin(radius: float, pitch: float) -> float:
    """How much more room than ``radius`` a node needs so that a move to a neighbouring node with as much room is
    clear along its whole length: sqrt(r^2 + (L/2)^2) - r for the longest move, a diagonal, L = pitch * sqrt 2.

    The proof: let x be the move's point nearest an obstacle and o the obstacle's point nearest x. The distance to
    o along the move's line is sqrt(e^2 + (t - t0)^2), e the line's distance from o; both ends are at least
    r + margin from the obstacle, so from o, and one of them is at least L/2 along the line from the foot t0:
    e^2 >= (r + margin)^2 - L^2/4 >= r^2. So x, at least e from o, is at least r from the obstacle."""
    half = pitch * math.sqrt(2.0) / 2.0
    return math.sqrt(radius * radius + half * half) - radius


def _merge(best: np.ndarray, net: np.ndarray, other: np.ndarray, value: np.ndarray, owner: int) -> None:
    """Merge ``value`` of net ``owner`` into a (best, its net, best of any other net) field, in place.

    ``other`` stays the least value of a net other than ``net``'s: a value below ``best`` of another net makes
    the old best the other net's least (it was the least of all); one of the same net only lowers ``best``; one
    above ``best`` of another net may lower ``other``."""
    lower = value < best
    same = net == owner
    np.copyto(other, best, where=lower & ~same)
    np.minimum(other, value, out=other, where=~lower & ~same)
    np.copyto(best, value, where=lower)
    net[lower] = owner


class Fields:
    """The fields of one region: ``nx`` by ``ny`` nodes from lattice node (``i0``, ``j0``), on ``layers`` copper
    layers (KiCad's names, front first), for obstacles whose influence ends ``reach`` mm away."""

    def __init__(self, i0: int, j0: int, nx: int, ny: int, pitch: float, layers: Sequence[str], reach: float):
        self.i0, self.j0, self.nx, self.ny, self.pitch = i0, j0, nx, ny, pitch
        self.layers = list(layers)
        self.reach = reach
        shape = (ny, nx)

        def far() -> np.ndarray:
            return np.full(shape, FAR, dtype=np.float32)

        def nobody() -> np.ndarray:
            return np.full(shape, NO_NET - 1, dtype=np.int32)

        count = len(self.layers)
        self.F = [(far(), nobody(), far()) for _ in range(count)]
        self.D = [(far(), nobody(), far()) for _ in range(count)]
        self.K = [far() for _ in range(count)]
        self.KV, self.H, self.P = far(), far(), far()
        self.E = np.full(shape, FAR, dtype=np.float32)

    # --- where nodes are -------------------------------------------------------------------------------------

    def x(self, i: int) -> float:
        return (self.i0 + i) * self.pitch

    def y(self, j: int) -> float:
        return (self.j0 + j) * self.pitch

    def span(self, box: tuple[float, float, float, float], grow: float) -> tuple[slice, slice] | None:
        """The region's nodes within ``box`` grown by ``grow``, as (rows, columns); None outside the region."""
        g = self.pitch
        c0 = max(0, math.floor((box[0] - grow) / g) - self.i0)
        c1 = min(self.nx, math.ceil((box[2] + grow) / g) - self.i0 + 1)
        r0 = max(0, math.floor((box[1] - grow) / g) - self.j0)
        r1 = min(self.ny, math.ceil((box[3] + grow) / g) - self.j0 + 1)
        if c0 >= c1 or r0 >= r1:
            return None
        return slice(r0, r1), slice(c0, c1)

    def nodes(self, rows: slice, cols: slice) -> tuple[np.ndarray, np.ndarray]:
        """The coordinates of the nodes in ``rows`` x ``cols``, millimetres, as two arrays of that shape."""
        g = self.pitch
        xs = (self.i0 + np.arange(cols.start, cols.stop)) * g
        ys = (self.j0 + np.arange(rows.start, rows.stop)) * g
        return np.meshgrid(xs, ys)

    def _distance(self, shape: Shape) -> tuple[tuple[slice, slice], np.ndarray] | None:
        span = self.span(shape.box, self.reach)
        if span is None:
            return None
        X, Y = self.nodes(*span)
        return span, shape.grid_distance(X, Y).astype(np.float32)

    # --- what obstacles there are ----------------------------------------------------------------------------

    def add_copper(self, shapes: Sequence[Shape], layers: Sequence[int], net: int, clearance: float) -> None:
        """Copper of ``net`` (``NO_NET`` for none) on the layers numbered ``layers``, keeping ``clearance``."""
        for shape in shapes:
            found = self._distance(shape)
            if found is None:
                continue
            (rows, cols), distance = found
            keep = distance - np.float32(clearance)
            for layer in layers:
                best, owner, other = self.F[layer]
                _merge(best[rows, cols], owner[rows, cols], other[rows, cols], keep, net)
                best, owner, other = self.D[layer]
                _merge(best[rows, cols], owner[rows, cols], other[rows, cols], distance, net)

    def add_pad(self, shapes: Sequence[Shape]) -> None:
        """A pad's copper, of any net: no via lands in it."""
        for shape in shapes:
            found = self._distance(shape)
            if found is not None:
                (rows, cols), distance = found
                np.minimum(self.P[rows, cols], distance, out=self.P[rows, cols])

    def add_hole(self, shape: Shape, net: int, hole_clearance: float, layers: Sequence[int]) -> None:
        """A drilled hole of ``net`` (a pad's, a via's, an unplated one's: ``NO_NET``): other nets' copper keeps
        ``hole_clearance`` from it on every layer it passes, and every new via's drill ``hole_to_hole``."""
        found = self._distance(shape)
        if found is None:
            return
        (rows, cols), distance = found
        keep = distance - np.float32(hole_clearance)
        for layer in layers:
            best, owner, other = self.F[layer]
            _merge(best[rows, cols], owner[rows, cols], other[rows, cols], keep, net)
        np.minimum(self.H[rows, cols], distance, out=self.H[rows, cols])

    def add_keepout(self, shape: Shape, layers: Sequence[int], tracks: bool, vias: bool) -> None:
        """A rule area: no track on ``layers`` where ``tracks``, no via anywhere where ``vias``."""
        found = self._distance(shape)
        if found is None:
            return
        (rows, cols), distance = found
        if tracks:
            for layer in layers:
                np.minimum(self.K[layer][rows, cols], distance, out=self.K[layer][rows, cols])
        if vias:
            np.minimum(self.KV[rows, cols], distance, out=self.KV[rows, cols])

    def set_edge(self, rings: Sequence[Sequence[tuple[float, float]]]) -> None:
        """The board's outline, closed rings (the outer edge and any cutout): ``E`` is each node's distance to
        the nearest edge, positive inside the board (even-odd over every ring), negative outside, and +-``reach``
        where no edge is that near."""
        g = self.pitch
        inside = np.zeros((self.ny, self.nx), dtype=bool)
        ys = (self.j0 + np.arange(self.ny)) * g
        xs = (self.i0 + np.arange(self.nx)) * g
        distance = np.full((self.ny, self.nx), np.float32(self.reach), dtype=np.float32)
        for ring in rings:
            points = np.asarray(ring, dtype=float)
            if len(points) > 1 and np.allclose(points[0], points[-1]):
                points = points[:-1]
            if len(points) < 3:
                continue
            nxt = np.roll(points, -1, axis=0)
            for (x1, y1), (x2, y2) in zip(points, nxt):
                # Inside, row by row: an edge that straddles a row's y flips the nodes left of where it crosses.
                rows = np.nonzero((y1 > ys) != (y2 > ys))[0] if y1 != y2 else ()
                if len(rows):
                    crossing = x1 + (ys[rows] - y1) * (x2 - x1) / (y2 - y1)
                    inside[rows] ^= xs[None, :] < crossing[:, None]
                edge = Shape.segment((float(x1), float(y1)), (float(x2), float(y2)), 0.0)
                span = self.span(edge.box, self.reach)
                if span is not None:
                    X, Y = self.nodes(*span)
                    near = edge.grid_distance(X, Y).astype(np.float32)
                    np.minimum(distance[span], near, out=distance[span])
        self.E = np.where(inside, distance, -distance).astype(np.float32)

    # --- the room a net has ----------------------------------------------------------------------------------

    @staticmethod
    def _for(field: tuple[np.ndarray, np.ndarray, np.ndarray], rows: slice, cols: slice, net: int) -> np.ndarray:
        best, owner, other = field
        return np.where(owner[rows, cols] == net, other[rows, cols], best[rows, cols])

    def track_room(self, rows: slice, cols: slice, layer: int, net: int, clearance: float, edge: float) -> np.ndarray:
        """The room a track centreline of ``net`` (keeping ``clearance``) has at each node, before its half width:
        the least of the other copper's and the holes' (each at its clearance) and the edge's (at ``edge``)."""
        room = np.minimum(self._for(self.F[layer], rows, cols, net),
                          self._for(self.D[layer], rows, cols, net) - np.float32(clearance))
        return np.minimum(room, self.E[rows, cols] - np.float32(edge))

    def keepout_room(self, rows: slice, cols: slice, layer: int) -> np.ndarray:
        return self.K[layer][rows, cols]

    def via_room(self, rows: slice, cols: slice, net: int, clearance: float, edge: float, radius: float, drill: float,
                 hole_clearance: float, hole_to_hole: float) -> np.ndarray:
        """The room a via of ``net`` (``radius`` its copper's, ``drill`` its hole's radius) has at each node, all
        its checks in one: its copper on every layer at its clearance and the edge's, its drill ``hole_clearance``
        from other copper and ``hole_to_hole`` from every hole, no pad and no via keep-out under it. A via fits
        where the room is >= 0."""
        room = self.E[rows, cols] - np.float32(edge + radius)
        for layer in range(len(self.layers)):
            copper = self._for(self.D[layer], rows, cols, net)
            room = np.minimum(room, np.minimum(self._for(self.F[layer], rows, cols, net), copper - np.float32(clearance))
                              - np.float32(radius))
            room = np.minimum(room, copper - np.float32(drill + hole_clearance))
        room = np.minimum(room, self.H[rows, cols] - np.float32(drill + hole_to_hole))
        room = np.minimum(room, self.P[rows, cols] - np.float32(radius))
        return np.minimum(room, self.KV[rows, cols] - np.float32(radius))
