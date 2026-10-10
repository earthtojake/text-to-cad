"""Freerouting's Specctra session read back as KiCad tracks and vias, and those added to the board."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from cadgen.kicad import sexpr
from cadgen.kicad.geometry import nm
from cadgen.kicad.ids import Ids
from cadgen.kicad.sexpr import Sym
from cadgen.kicad.specctra.dsn import Dsn, ViaKind
from cadgen.kicad.specctra.shapes import Point


class SessionError(RuntimeError):
    """A Specctra session that does not answer the design it was routed from."""


# --- the session ---------------------------------------------------------------------------------

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"([^"]*)"|([^\s()"]+))')
_UNIT_UM = {"inch": 25400.0, "mil": 25.4, "cm": 10000.0, "mm": 1000.0, "um": 1.0}


def _specctra(text: str) -> list:
    """A Specctra file as nested lists of strings (atoms keep their spelling)."""
    stack: list[list] = []
    root: list | None = None
    position = 0
    for match in _TOKEN.finditer(text):
        if match.start() != position:
            break
        position = match.end()
        opened, closed, quoted, bare = match.groups()
        if opened:
            node: list = []
            if stack:
                stack[-1].append(node)
            elif root is None:
                root = node
            else:
                raise SessionError("a Specctra session holds more than one expression")
            stack.append(node)
        elif closed:
            if not stack:
                raise SessionError("a Specctra session closes a list it never opened")
            stack.pop()
        elif stack:
            stack[-1].append(quoted if quoted is not None else bare)
        else:
            raise SessionError("a Specctra session has text outside its list")
    if text[position:].strip() or stack or root is None:
        raise SessionError("Freerouting's session file is cut short or unreadable")
    return root


def _scope(node: list, name: str) -> list | None:
    return next((child for child in node[1:] if isinstance(child, list) and child and str(child[0]).lower() == name), None)


def _scopes(node: list, name: str) -> list[list]:
    return [child for child in node[1:] if isinstance(child, list) and child and str(child[0]).lower() == name]


@dataclass(frozen=True)
class RoutedTrack:
    net: str
    layer: str
    width: float
    start: Point  # KiCad millimetres
    end: Point


@dataclass(frozen=True)
class RoutedVia:
    net: str
    at: Point  # KiCad millimetres
    kind: ViaKind


@dataclass(frozen=True)
class Routes:
    tracks: tuple[RoutedTrack, ...]
    vias: tuple[RoutedVia, ...]


def _number(text: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        raise SessionError(f"Freerouting's session has {text!r} where a number belongs") from None


def read_session(text: str, dsn: Dsn) -> Routes:
    """The tracks and vias a Specctra session adds to the board ``dsn`` was written from.

    Only what the router added comes back: the board's own copper went in fixed,
    and a session leaves fixed copper out. Everything is checked against the
    design -- a net, layer or via the DSN never named, a swapped pin, a
    copper area -- and refused, rather than guessed.
    """
    root = _specctra(text)
    if not root or str(root[0]).lower() != "session":
        raise SessionError("Freerouting's output is not a Specctra session (session ...)")
    was_is = _scope(root, "was_is")
    if was_is is not None and _scopes(was_is, "pins"):
        raise SessionError("Freerouting swapped pins (was_is); cadgen does not let the router change the netlist")
    routes = _scope(root, "routes")
    if routes is None:
        return Routes(tracks=(), vias=())
    resolution = _scope(routes, "resolution")
    if resolution is None or len(resolution) < 3 or str(resolution[1]).lower() not in _UNIT_UM:
        raise SessionError("Freerouting's session gives no resolution for its routes")
    scale = _UNIT_UM[str(resolution[1]).lower()] / _number(resolution[2])  # µm per session unit
    frame = dsn.frame
    tracks: list[RoutedTrack] = []
    vias: list[RoutedVia] = []
    network = _scope(routes, "network_out")
    for net_node in _scopes(network, "net") if network is not None else []:
        alias = str(net_node[1]) if len(net_node) > 1 else ""
        net = dsn.nets.get(alias)
        if net is None:
            raise SessionError(f"Freerouting routed a net the design does not have: {alias!r}")
        for item in net_node[2:]:
            if not isinstance(item, list) or not item:
                continue
            kind = str(item[0]).lower()
            if kind == "wire":
                path = _scope(item, "path")
                if path is None:
                    raise SessionError(f"Freerouting answered net {net} with a copper area rather than a track")
                layer = str(path[1])
                if layer not in dsn.layers:
                    raise SessionError(f"Freerouting routed net {net} on {layer!r}, a layer the board does not have")
                width = nm(_number(path[2]) * scale / 1000.0)
                expected = dsn.widths.get(alias)
                if expected is not None and abs(width - expected) <= 0.0005:
                    width = expected
                numbers = [_number(value) * scale for value in path[3:]]
                if len(numbers) % 2 or len(numbers) < 4:
                    raise SessionError(f"Freerouting wrote a track of net {net} with an odd or short list of points")
                points = [frame.to_kicad(numbers[i], numbers[i + 1]) for i in range(0, len(numbers), 2)]
                for start, end in zip(points, points[1:]):
                    if start != end:
                        tracks.append(RoutedTrack(net=net, layer=layer, width=width, start=start, end=end))
            elif kind == "via":
                padstack = str(item[1]) if len(item) > 1 else ""
                via = dsn.vias.get(padstack)
                if via is None:
                    raise SessionError(f"Freerouting placed a via the design does not offer: {padstack!r}")
                at = frame.to_kicad(_number(item[2]) * scale, _number(item[3]) * scale)
                vias.append(RoutedVia(net=net, at=at, kind=via))
            else:
                raise SessionError(f"Freerouting's session holds a {kind!r} in net {net}, which cadgen does not read")
    tracks.sort(key=lambda track: (track.net, track.layer, track.start, track.end, track.width))
    vias.sort(key=lambda via: (via.net, via.at, via.kind.diameter, via.kind.drill))
    unique_tracks = tuple(dict.fromkeys(tracks))
    return Routes(tracks=unique_tracks, vias=tuple(dict.fromkeys(vias)))


# --- routes into the board -----------------------------------------------------------------------


def _route_nodes(routes: Routes, ids: Ids) -> list[list]:
    nodes: list[list] = []
    index = 0
    for track in routes.tracks:
        nodes.append(
            [
                Sym("segment"),
                [Sym("start"), *track.start],
                [Sym("end"), *track.end],
                [Sym("width"), track.width],
                [Sym("layer"), track.layer],
                [Sym("net"), track.net],
                [Sym("uuid"), ids(f"route:{index}")],
            ]
        )
        index += 1
    for via in routes.vias:
        nodes.append(
            [
                Sym("via"),
                [Sym("at"), *via.at],
                [Sym("size"), via.kind.diameter],
                [Sym("drill"), via.kind.drill],
                [Sym("layers"), *via.kind.layers],
                [Sym("net"), via.net],
                [Sym("uuid"), ids(f"route:{index}")],
            ]
        )
        index += 1
    return nodes


def with_routes(pcb_tree: list, routes: Routes, *, project: str) -> list:
    """``pcb_tree`` with the routes added after its own tracks and vias (a copy).

    Each route gets a UUID derived from its place in the sorted routes
    (``route:<index>`` in the project's namespace), so the same routes always
    write the same board.
    """
    tree = copy.deepcopy(pcb_tree)
    nodes = _route_nodes(routes, Ids(project))
    heads = [sexpr.head(item) for item in tree]
    copper = [index for index, head in enumerate(heads) if head in ("segment", "arc", "via")]
    if copper:
        at = copper[-1] + 1
    elif "zone" in heads:
        at = heads.index("zone")
    elif "embedded_fonts" in heads:
        at = heads.index("embedded_fonts")
    else:
        at = len(tree)
    tree[at:at] = nodes
    return tree
