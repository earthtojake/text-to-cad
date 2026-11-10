"""The nets KiCad moved in a ``kicad_pcb.edit``: each track, via, copper shape and zone whose net it changed.

KiCad's connectivity gives an item of copper the net of a pad its copper overlaps, on any layer: when it loads
the board, and again at each commit. A ground via through a supply pad on the far side becomes a supply via, a
copper polygon joined to it goes with it, and the save writes them so; KiCad's DRC then sees that net's copper,
not a short. The edit (``_session``) watches for it: at the save, every item of these kinds is held to the net
it should have -- the one the block gave it (``create_items``, ``update_items``: a net it asked for that
differs from the one KiCad held for the item then), else the one the file had before the edit -- and each
whose saved net differs is a :class:`NetChange`, said on stderr and kept on the board as ``net_changes``.

What is not a change: an item the block deleted, one KiCad made itself (a teardrop's zone), one that carried no
net (KiCad naming a netless track by the pad it touches is how it connects one), and a net renamed or removed
whole (a netlist import's), whose old name no board item carries any more. The pad an item overlaps is found
in the saved board (its index, read only when there is a change), on a copper layer they share; an item that
overlaps none but touches a moved one is named as joined to it.

The files are read by their top-level items' lines (KiCad's layout: one tab, then the item, its fields one
tab deeper), so a 2,000-segment board costs milliseconds; a board laid out otherwise (written by hand, on one
line) is parsed whole.
"""

from __future__ import annotations

import functools
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

__all__ = ["NetChange", "Watch", "board_nets"]

#: The kinds whose nets are watched, by the file's heads; a ``gr_*`` head but a text's is a shape.
_KINDS = {"via": "via", "segment": "track", "arc": "track", "zone": "zone"}
_HEAD = re.compile(r"(via|segment|arc|zone|gr_(?!text)[a-z_]+)[\s)]")
_NET = re.compile(r'\n\t\t\(net (?:"((?:[^"\\]|\\.)*)"|(\d+))')
_NET_NAME = re.compile(r'\n\t\t\(net_name "((?:[^"\\]|\\.)*)"')
_UUID = re.compile(r'\n\t\t\((?:uuid|tstamp) "?([0-9A-Fa-f-]+)"?\)')
_TABLE = re.compile(r'^\t\(net (\d+) "((?:[^"\\]|\\.)*)"\)', re.M)
#: Every net any item names, a pad's among them: a net's name, ``(net "GND")``, or an older table's ``(net 3 "GND")``.
_ANY_NET = re.compile(r'\(net (?:\d+ )?"((?:[^"\\]|\\.)+)"\)')


@functools.lru_cache(maxsize=4096)
def _name(text: str | None) -> str | None:
    """A net's name as the file quotes it, as KiCad shows it (``TX{slash}RX`` is ``TX/RX``)."""
    if not text:
        return None
    if "\\" not in text and "{" not in text:
        return text
    from cad.engine.formats.kicad import sexpr
    from cad.engine.formats.kicad.naming import unescape_net_name

    return unescape_net_name(sexpr.unescape(text)) or None


def board_nets(text: str) -> tuple[dict[str, tuple[str, str | None]], set[str]]:
    """The watched items of the board ``text``, ``{uuid: (kind, net)}`` (``net`` as KiCad shows it, ``None`` for
    none), and every net name an item of it carries (pads, tracks, anything)."""
    names = {name for name in (_name(found) for found in _ANY_NET.findall(text)) if name}
    if not text.startswith("(kicad_pcb\n\t("):
        return _parsed(text), names
    table = {int(number): _name(name) for number, name in _TABLE.findall(text)} if "\n\t(net " in text else {}
    items: dict[str, tuple[str, str | None]] = {}
    for chunk in text.split("\n\t("):  # each top-level item, to the next
        head = _HEAD.match(chunk)
        uuid = _UUID.search(chunk) if head else None
        if uuid is None:
            continue
        net = _NET.search(chunk)
        if net is None:
            named = _NET_NAME.search(chunk)
            name = _name(named.group(1)) if named else None
        elif net.group(1) is not None:
            name = _name(net.group(1))
        else:
            name = table.get(int(net.group(2)))
        items[uuid.group(1).lower()] = (_KINDS.get(head.group(1), "shape"), name)
    return items, names


def _parsed(text: str) -> dict[str, tuple[str, str | None]]:
    """:func:`board_nets`'s items from the whole parsed tree: a board not in KiCad's layout."""
    from cad.engine.formats.kicad import sexpr
    from cad.engine.formats.kicad.board_index import item_id, net_of, net_table

    tree = sexpr.parse(text)
    table = net_table(tree)
    items: dict[str, tuple[str, str | None]] = {}
    for node in tree[1:]:
        head = sexpr.head(node) if isinstance(node, list) else None
        if head is None or not (head in _KINDS or head.startswith("gr_")) or head.startswith("gr_text"):
            continue
        uuid = item_id(node)
        if uuid is not None:
            items[uuid] = (_KINDS.get(head, "shape"), net_of(node, table))
    return items


@dataclass(frozen=True)
class NetChange:
    """An item whose net KiCad changed: its ``kind`` (track, via, shape, zone), uuid (``id``), the reference
    ``board.resolve`` takes (``ref``, ``#via:<uuid>``), the net it should have (``was``: the block's, else the
    file's before the edit) and the one KiCad saved (``now``); ``pad`` the pad of ``now`` its copper overlaps
    (``#J3.1``), else ``joined`` the moved item it touches (``#via:<uuid>``), when either is found."""

    kind: str
    id: str
    ref: str
    was: str | None
    now: str | None
    pad: str | None = None
    joined: str | None = None

    def as_data(self) -> dict[str, Any]:
        return {"kind": self.kind, "id": self.id, "ref": self.ref, "was": self.was, "now": self.now,
                "pad": self.pad, "joined": self.joined}

    def line(self, board: str) -> str:
        """The warning it is said as, on stderr: what KiCad saved, why where it is found, and what to do."""
        said = f"warning: {board}: KiCad saved {self.kind} {self.ref} on {self.now or 'no net'}, not {self.was}"
        if self.joined and not self.pad:
            return (f"{said}: it touches {self.joined}, which KiCad moved too; move that clear of other nets' pads, "
                    f"then give both {self.was} again")
        return (said + (f": it overlaps pad {self.pad} of {self.now}" if self.pad else "")
                + "; move it clear of other nets' pads on every copper layer it spans (a through via spans them all), "
                f"then give it {self.was} again")


def _net(item: Any) -> str | None:
    net = getattr(item, "net", None)
    return _name(getattr(net, "name", None))


def _uuid(item: Any) -> str | None:
    value = getattr(getattr(item, "id", None), "value", None)
    return str(value).lower() if value else None


class Watch:
    """One board edit's watch: the nets the block asked for, and the check at its save."""

    def __init__(self) -> None:
        #: The nets the block gave items, by uuid: what each should be saved with.
        self.asked: dict[str, str | None] = {}

    def board(self, board: Any) -> Any:
        """KiPy's open ``board``, its ``create_items`` and ``update_items`` noting the nets they ask for."""
        from kicode.board import Board  # pyrefly: ignore[missing-import] - the kicad extra

        watch = self

        class WatchedBoard(Board):  # pyrefly: ignore[invalid-inheritance]
            """KiPy's Board, the nets the block gives its items noted for the check at the save (``_drift``);
            ``net_changes``, after the block, the items whose net KiCad changed (:class:`NetChange`)."""

            net_changes: tuple[NetChange, ...] = ()

            def create_items(self, items: Any) -> Any:
                made = super().create_items(items)
                for item in made:  # what KiCad made, with the net the block asked for, before it connects them
                    uuid = _uuid(item)
                    if uuid is not None and hasattr(item, "net"):
                        watch.asked[uuid] = _net(item)
                return made

            def update_items(self, items: Any) -> Any:
                sent = [items] if not isinstance(items, (list, tuple)) else list(items)
                carrying = [item for item in sent if hasattr(item, "net") and _uuid(item) is not None]
                held = {}
                if carrying:  # the nets KiCad holds for them now: a net sent back as it was read is not asked for
                    held = {_uuid(item): _net(item) for item in super().get_items_by_id([item.id for item in carrying])}
                for item in carrying:
                    uuid = _uuid(item)
                    if uuid in held and _net(item) != held[uuid]:
                        watch.asked[uuid] = _net(item)
                return super().update_items(items)

        return WatchedBoard(board.client, board.document)

    def check(self, before: str | None, path: Path) -> list[NetChange]:
        """The items of the board saved at ``path`` whose net KiCad changed: against the nets the block asked for,
        else the ones of ``before`` (the file's text before the edit, ``None`` for a board KiCad made)."""
        was, _ = board_nets(before) if before else ({}, set())
        now, carried = board_nets(path.read_text(encoding="utf-8"))
        moved: list[tuple[str, str, str | None, str | None]] = []
        for uuid, (kind, net) in now.items():
            if uuid in self.asked:
                meant = self.asked[uuid]
            elif uuid in was:
                meant = was[uuid][1]
            else:
                continue  # made by KiCad itself
            if meant is None or net == meant or meant not in carried:
                continue  # no net to lose, or a net renamed or removed whole
            moved.append((uuid, kind, meant, net))
        if not moved:
            return []
        return _explained(moved, path)


def _explained(moved: list[tuple[str, str, str | None, str | None]], path: Path) -> list[NetChange]:
    """Each moved item with the pad of its new net its copper overlaps, else the moved item it touches."""
    from cad.engine.formats.kicad.refs import selector_or_none

    try:
        copper = _copper(path)
    except (OSError, ValueError, UnicodeDecodeError):
        copper = None
    changes = []
    for uuid, kind, meant, net in moved:
        pad = joined = None
        if copper is not None:
            pad = copper.pad(uuid, net)
        changes.append([uuid, kind, meant, net, pad, joined])
    if copper is not None:
        found = {uuid for uuid, *_rest in moved}
        for change in changes:
            if change[4] is None:
                change[5] = copper.touching(change[0], found - {change[0]})
    changes.sort(key=lambda change: (change[4] is None, change[1] != "via", change[0]))
    return [NetChange(kind=kind, id=uuid, ref=selector_or_none(kind, id=uuid) or f"#{kind}:{uuid}", was=meant,
                      now=net, pad=pad, joined=selector_or_none(_kind_of(copper, joined), id=joined) if joined else None)
            for uuid, kind, meant, net, pad, joined in changes]


def _kind_of(copper: "_Copper | None", uuid: str) -> str:
    return copper.kinds.get(uuid, "via") if copper is not None else "via"


class _Copper:
    """The saved board's copper, as the board's reader sees it: each watched item's outline on its layers, and
    each pad's."""

    def __init__(self, index: Any, copper_layers: list[str]) -> None:
        from cad.engine.formats.kicad.geometry import disc, pen_outlines

        self.index = index
        self.layers = copper_layers
        self.outlines: dict[str, tuple[list[list[tuple[float, float]]], set[str]]] = {}
        self.kinds: dict[str, str] = {}
        for via in index.vias:
            if via.id:
                self.outlines[via.id] = ([disc(via.at, via.diameter / 2)], self._span(via.layers))
                self.kinds[via.id] = "via"
        for track in index.tracks:
            if track.id:
                self.outlines[track.id] = (pen_outlines(list(track.points), track.width), {track.layer})
                self.kinds[track.id] = "track"
        for shape in index.shapes:
            if shape.id and shape.part is None and shape.layer in copper_layers:
                outline = ([list(shape.points)] if shape.closed and shape.filled else
                           pen_outlines(list(shape.points), shape.width, closed=shape.closed))
                self.outlines[shape.id] = (outline, {shape.layer})
                self.kinds[shape.id] = "shape"
        for zone in index.zones:
            if zone.id and not zone.rule:
                outlines, layers = self.outlines.get(zone.id, ([], set()))
                self.outlines[zone.id] = ([*outlines, *(list(fill) for fill in zone.fills or (zone.outline,))],
                                          layers | {zone.layer})
                self.kinds[zone.id] = "zone"

    def _span(self, layers: Iterable[str]) -> set[str]:
        named = [layer for layer in layers if layer in self.layers]
        if len(named) != 2:
            return set(self.layers)
        low, high = sorted(self.layers.index(layer) for layer in named)
        return set(self.layers[low:high + 1])

    def _pad_layers(self, side: str) -> set[str]:
        return {"top": {self.layers[0]}, "bottom": {self.layers[-1]}}.get(side, set(self.layers))

    def pad(self, uuid: str, net: str | None) -> str | None:
        """The first pad on ``net`` the item ``uuid`` overlaps on a layer they share, by its reference."""
        from cad.engine.formats.kicad.geometry import polygons_overlap

        if uuid not in self.outlines or net is None:
            return None
        outlines, layers = self.outlines[uuid]
        for pad in self.index.pads:
            if pad.net != net or not pad.polygon or not (layers & self._pad_layers(pad.side)):
                continue
            if any(polygons_overlap(outline, pad.polygon) for outline in outlines if len(outline) >= 3):
                return pad.selector or f"{pad.part}.{pad.number}"
        return None

    def touching(self, uuid: str, others: set[str]) -> str | None:
        """The first of ``others`` whose copper the item ``uuid`` overlaps on a layer they share."""
        from cad.engine.formats.kicad.geometry import polygons_overlap

        if uuid not in self.outlines:
            return None
        outlines, layers = self.outlines[uuid]
        for other in sorted(others):
            if other not in self.outlines:
                continue
            theirs, their_layers = self.outlines[other]
            if layers & their_layers and any(polygons_overlap(mine, outline) for mine in outlines if len(mine) >= 3
                                             for outline in theirs if len(outline) >= 3):
                return other
        return None


def _copper(path: Path) -> _Copper:
    from cad.engine.formats.kicad import sexpr
    from cad.engine.formats.kicad.board_index import canonical_copper, copper_layers, read_index

    tree = canonical_copper(sexpr.parse(path.read_text(encoding="utf-8")))
    return _Copper(read_index(tree), copper_layers(tree))


def say(changes: list[NetChange], board: str) -> None:
    """Each change, a warning line on stderr."""
    for change in changes:
        print(change.line(board), file=sys.stderr)
