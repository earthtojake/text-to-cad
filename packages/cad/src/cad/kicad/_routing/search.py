"""The search: A* over a window of the grid, octolinear moves on each layer and a via between them.

A state is a node on a layer (and, under a via limit, how many vias the path has placed so far). From each
state the search may move to the eight neighbouring nodes on its layer, costing the move's length times the
layer's cost per millimetre, where the next node is free for the track; change layer where a via fits, costing
``via_cost``; and change layer for nothing inside the net's own through-hole copper (a through-hole pad or a via
already there), where no via is placed. Its heuristic is the octile distance to the box round the targets
(never more than the cheapest way there), weighted a little, so it settles for a path at most that factor
longer and looks at far fewer nodes.

Determinism: the heap orders by cost then by state number, so equal costs always break the same way, and the
same window, sources and targets give the same path.

The window is padded by one node that is never free, so a neighbour's number never wraps to another row.
"""

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass
from heapq import heappop, heappush
from typing import Sequence

__all__ = ["Found", "flood", "search"]

INF = math.inf


@dataclass(frozen=True)
class Found:
    """A path: each step's (layer, node), from a source to a target, and where a via was placed (the node of
    each layer change that is not inside the net's own through-hole copper). ``cost`` is the search's."""

    steps: tuple[tuple[int, int], ...]
    vias: tuple[int, ...]
    cost: float
    expanded: int


def search(free: bytes | bytearray, layers: int, nx: int, ny: int, pitch: float, costs: Sequence[float],
           via_ok: bytes | bytearray, swap_ok: bytes | bytearray, via_cost: float, via_limit: int | None,
           sources: Sequence[int], targets: bytes | bytearray, heuristic: Sequence[float],
           budget: int) -> tuple[Found | None, int, bool]:
    """The cheapest path (within the heuristic's weight) from any of ``sources`` to any of ``targets``.

    ``free``: per layer then node, 1 where a track centreline may be; ``via_ok`` and ``swap_ok``: per node, where a
    via fits and where the layer changes for nothing; ``sources``: the starting (layer * nodes + node) numbers;
    ``targets``: per layer then node, 1 at a target; ``heuristic``: per node, the weighted estimate to the targets.
    Answers (the path or None, how many states were expanded, whether the budget ran out)."""
    nodes = nx * ny
    depth = 1 if via_limit is None else via_limit + 1
    plane = layers * nodes
    total = depth * plane
    g = array("d", [INF]) * total
    parent = array("l", [-1]) * total
    closed = bytearray(total)
    heap: list[tuple[float, int]] = []
    for state in sources:
        if free[state] and g[state] > 0.0:
            g[state] = 0.0
            heappush(heap, (heuristic[state % nodes], state))
    diagonal = pitch * math.sqrt(2.0)
    moves = ((1, pitch), (-1, pitch), (nx, pitch), (-nx, pitch),
             (nx + 1, diagonal), (nx - 1, diagonal), (-nx + 1, diagonal), (-nx - 1, diagonal))
    steps = [[(offset, length * cost) for offset, length in moves] for cost in costs]
    expanded = 0
    while heap:
        _, state = heappop(heap)
        if closed[state]:
            continue
        closed[state] = 1
        expanded += 1
        if expanded > budget:
            return None, expanded, True
        level, rest = divmod(state, plane)
        layer, node = divmod(rest, nodes)
        if targets[rest]:
            return _path(state, parent, nodes, plane, swap_ok, g[state], expanded), expanded, False
        here = g[state]
        base = state - node
        free_base = layer * nodes
        for offset, cost in steps[layer]:
            nxt = node + offset
            if not free[free_base + nxt]:
                continue
            to = base + nxt
            if closed[to]:
                continue
            cost += here
            if cost < g[to]:
                g[to] = cost
                parent[to] = state
                heappush(heap, (cost + heuristic[nxt], to))
        changes = []
        if swap_ok[node]:
            changes.append((level, 0.0))
        if via_ok[node] and (via_limit is None or level < via_limit):
            changes.append((level if via_limit is None else level + 1, via_cost))
        for into, cost in changes:
            cost += here
            for other in range(layers):
                if other == layer or not free[other * nodes + node]:
                    continue
                to = into * plane + other * nodes + node
                if closed[to] or cost >= g[to]:
                    continue
                g[to] = cost
                parent[to] = state
                heappush(heap, (cost + heuristic[node], to))
    return None, expanded, False


def _path(state: int, parent: array, nodes: int, plane: int, swap_ok: bytes | bytearray, cost: float,
          expanded: int) -> Found:
    chain = []
    while state >= 0:
        chain.append(state)
        state = parent[state]
    chain.reverse()
    steps = tuple(divmod(s % plane, nodes) for s in chain)
    vias = tuple(node for (layer, node), (after, again) in zip(steps, steps[1:])
                 if layer != after and node == again and not swap_ok[node])
    return Found(steps, vias, cost, expanded)


def flood(free: bytes | bytearray, layers: int, nx: int, ny: int, via_ok: bytes | bytearray,
          swap_ok: bytes | bytearray, starts: Sequence[int], goals: bytes | bytearray, limit: int
          ) -> tuple[list[int], bool]:
    """The states of the free space round ``starts``, counted to ``limit``, and whether it reaches a goal: a
    connection whose end is walled in fails here in a few thousand steps, not after the whole board."""
    nodes = nx * ny
    seen = bytearray(layers * nodes)
    queue = []
    for state in starts:
        if free[state] and not seen[state]:
            seen[state] = 1
            queue.append(state)
    moves = (1, -1, nx, -nx, nx + 1, nx - 1, -nx + 1, -nx - 1)
    head = 0
    while head < len(queue):
        if len(queue) >= limit:
            return queue, False
        state = queue[head]
        head += 1
        if goals[state]:
            return queue, True
        layer, node = divmod(state, nodes)
        base = layer * nodes
        for offset in moves:
            to = base + node + offset
            if free[to] and not seen[to]:
                seen[to] = 1
                queue.append(to)
        if via_ok[node] or swap_ok[node]:
            for other in range(layers):
                to = other * nodes + node
                if other != layer and free[to] and not seen[to]:
                    seen[to] = 1
                    queue.append(to)
    return queue, False
