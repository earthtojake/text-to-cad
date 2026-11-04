"""A board still's references, lit as the viewer lights its selection.

A Quick Edit packet from a board names what the person picked (``references``: board references,
``#R1``, ``#track:<uuid>``, ``#F.Cu@x10y5..x20y15``), and ``cad <type> snapshot --job`` draws them
over the board in the viewer's highlight (``@cad/core``'s ``board2d/boardOverlay.js``): a part's
outline and pads, a pad, a net's copper, a track, a via, a zone, a text's and a dimension's box, a
graphic's ink, a point's crosshair, an area's box. Each is resolved against the board as it is
saved now (``cad.kicad_pcb.read_board``); one that names nothing there any more is said in the
still's warnings, and the rest are lit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

#: The viewer's selection colour (``BOARD_OVERLAY_THEMES[appearance].selection``) and the light fill of what it
#: boxes, by appearance: the dark theme's light blue, and on the light canvas the same blue darkened to 4.5:1.
SELECTIONS = {"dark": ((141, 197, 255, 255), (141, 197, 255, 48)), "light": ((68, 122, 176, 255), (68, 122, 176, 48))}
SELECTION, FILL = SELECTIONS["dark"]
#: At most this many references are lit in one still.
MAX_REFERENCES = 256

XY = tuple[float, float]


def paint_references(pen, path: Path, references: Sequence[str], origin: Sequence[float], place: Callable[[XY], XY],
                     scale: float, ss: int, appearance: str = "dark") -> list[str]:
    """Light ``references`` on the still ``pen`` draws: ``place`` takes a sheet point to the picture's
    pixels, ``scale`` is pixels per millimetre and ``ss`` the supersampling; ``origin`` is where
    KiCad's (0, 0) lies on the sheet (the plot's ``board.origin``), and ``appearance`` the still's
    (its highlight's colours). Answers the warnings."""
    SELECTION, FILL = SELECTIONS.get(appearance, SELECTIONS["dark"])  # noqa: N806 - the theme's, as the module's
    from cad.engine.formats.kicad.board_index import (
        Area, Copper, Dimension, Net, Pad, Part, Point, Shape, Text, Track, Via, Zone, read_board,
    )

    board = read_board(path)
    warnings: list[str] = []

    def to(point: XY) -> XY:
        return place((point[0] + origin[0], point[1] + origin[1]))

    def stroke(points: Sequence[XY], width: float, closed: bool = False) -> None:
        drawn = [to(point) for point in points]
        if closed and len(drawn) > 2:
            drawn.append(drawn[0])
        if len(drawn) < 2:
            return
        wide = max(round(width * scale), 3 * ss)
        pen.line(drawn, fill=SELECTION, width=wide, joint="curve")
        for x, y in drawn:
            pen.ellipse((x - wide / 2, y - wide / 2, x + wide / 2, y + wide / 2), fill=SELECTION)

    def area(points: Sequence[XY], solid: bool = False) -> None:
        if len(points) > 2:
            pen.polygon([to(point) for point in points], fill=SELECTION if solid else FILL, outline=SELECTION, width=2 * ss)

    def disc(at: XY, diameter: float) -> None:
        x, y = to(at)
        radius = max(diameter * scale / 2, 3 * ss)
        pen.ellipse((x - radius, y - radius, x + radius, y + radius), fill=SELECTION)

    def crosshair(at: XY) -> None:
        x, y = to(at)
        size = 9 * ss
        pen.line([(x - size, y), (x + size, y)], fill=SELECTION, width=2 * ss)
        pen.line([(x, y - size), (x, y + size)], fill=SELECTION, width=2 * ss)
        pen.ellipse((x - size / 2, y - size / 2, x + size / 2, y + size / 2), outline=SELECTION, width=2 * ss)

    def copper(item) -> None:
        if isinstance(item, Track):
            stroke(item.points, item.width)
        elif isinstance(item, Via):
            disc(item.at, item.diameter)
        elif isinstance(item, Zone):
            area(item.outline)
        elif isinstance(item, Pad):
            area(item.polygon, solid=True)

    for reference in references:
        try:
            found = board.resolve(reference)
        except ValueError as error:
            warnings.append(f"{reference} is not lit: {error}")
            continue
        if isinstance(found, Part):
            area(found.outline)
            for pad in found.pads:
                area(pad.polygon, solid=True)
        elif isinstance(found, Pad):
            for pad in board.part(found.part).pads_numbered(found.number):
                area(pad.polygon, solid=True)
        elif isinstance(found, Net):
            for item in (*found.zones, *found.tracks, *found.vias, *found.pads):
                copper(item)
        elif isinstance(found, Copper):
            for item in found.items:
                copper(item)
            crosshair(found.at)
        elif isinstance(found, (Track, Via, Zone)):
            copper(found)
        elif isinstance(found, Text):
            area(found.polygon)
        elif isinstance(found, Dimension):
            for start, end in found.lines:
                stroke([start, end], 0)
            area(found.polygon)
        elif isinstance(found, Shape):
            if found.filled:
                area(found.points)
            else:
                stroke(found.points, found.width, found.closed)
        elif isinstance(found, Area):
            area(found.polygon)
        elif isinstance(found, Point):
            crosshair(found.at)
    return warnings
