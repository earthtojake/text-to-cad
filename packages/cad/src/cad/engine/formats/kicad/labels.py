"""The names KiCad's PCB editor writes over copper: a pad's number and net, a via's net.

They are not on the board; the editor draws them on its own netname layers
(``pcb_painter.cpp``'s ``draw( const PAD* )`` and ``draw( const PCB_VIA* )`` for the
netname layers), with its default display options: pad numbers on, net names on pads
and vias. These are those rules, so the plot can carry each name as a ``label`` item
(``docs/plot-payload.md``) the renderers lay out in the stroke font:

- a pad's names fit its bounding box, the number above the net name, both centred on
  it and turned to read upwards on a pad taller than wide; a pad with no net shows its
  number alone, a no-connect pin ``x`` and a free one ``*``;
- a via's net name sits in the via, with a blind or buried via's layer pair
  (``1-2``) above it;
- each is drawn once the view shows its pad or via large enough to read, as KiCad's
  level of detail decides (``PAD::ViewGetLOD``, ``PCB_VIA::ViewGetLOD``): ``lod`` is the
  CSS pixels per millimetre the view must reach.

A track's net name is not in the plot: where KiCad writes it (``renderNetNameForSegment``)
depends on the size of the view, so a renderer lays it out as it draws the track, by
``track_labels`` here and ``plot2d/trackNames.js`` in the viewer, number for number.

Sizes are millimetres and angles degrees counter-clockwise, as everywhere in the plot.
"""

from __future__ import annotations

import math
from typing import Sequence

from cad.engine.formats.kicad.geometry import XY

__all__ = ["KICAD_PX_PER_MM", "is_track", "pad_labels", "short_net_name", "track_labels", "track_name_detail", "via_labels"]

#: KiCad's canvas at zoom 1: 91 dots per inch (ADVANCED_CFG's ScreenDPI), in CSS pixels per millimetre.
KICAD_PX_PER_MM = 91 / 25.4
#: The largest name KiCad draws (PCB_RENDER_SETTINGS::MAX_FONT_SIZE), mm.
_MAX_FONT = 10.0
#: A pad's names show once its smaller side is this many millimetres at KiCad's zoom 1, a via's net once its width is.
_PAD_LOD_MM = 0.5
_VIA_LOD_MM = 10.0
#: A track's net name shows once its width is this many millimetres at KiCad's zoom 1 (``PCB_TRACK::ViewGetLOD``).
_TRACK_LOD_MM = 4.0


def short_net_name(net: str) -> str:
    """A net's name as KiCad shows it on copper: its last hierarchical part (``/cpu/CLK`` is ``CLK``)."""
    return net.rsplit("/", 1)[-1] if "/" in net else net


def _round(value: float) -> float:
    return round(value, 4)


def _label(text: str, at: XY, height: float, width: float, angle: float, stroke: float, lod: float, kind: str) -> dict:
    return {"t": "label", "kind": kind, "text": text, "at": (at[0], at[1]), "size": [_round(height), _round(width)],
            "angle": angle, "w": _round(stroke), "lod": _round(lod)}


def pad_labels(
    *, number: str, net: str | None, pin_type: str | None, box: Sequence[float], size: tuple[float, float],
    round_shape: bool, custom: bool,
) -> list[dict]:
    """A pad's number and net name, as KiCad's PCB editor writes them over the pad.

    ``box`` is the pad's bounding box ``(left, top, right, bottom)`` on the board, ``size``
    its padstack size before its turn, ``round_shape`` a circle or oval pad (whose names
    KiCad sets a shade smaller), ``custom`` a custom-shaped pad (whose box KiCad keeps).
    """
    name = ""
    if net:
        name = short_net_name(net)
    if pin_type and "no_connect" in pin_type:
        name = "x"
    elif net and pin_type == "free" and short_net_name(net).startswith("unconnected-("):
        name = "*"
    if not name and not number:
        return []
    left, top, right, bottom = box
    centre = ((left + right) / 2, (top + bottom) / 2)
    pad_w, pad_h = right - left, bottom - top
    if min(pad_w, pad_h) <= 0:
        return []
    # A pad turned 45 degrees would bloat its box: KiCad keeps the names to the pad's own size.
    if not custom:
        limit = min(abs(size[0]), abs(size[1])) * 1.1
        if pad_w > limit and pad_h > limit:
            pad_w = pad_h = limit
    lod = _PAD_LOD_MM * KICAD_PX_PER_MM / min(right - left, bottom - top)
    text_size = pad_h
    angle = 0.0
    # A pad taller than wide reads upwards: its long side is the line the names run along.
    if pad_w < pad_h * 0.95:
        angle = 90.0
        text_size = pad_w
        pad_w, pad_h = pad_h, pad_w
    text_size = min(text_size, _MAX_FONT)
    offset_name = offset_number = 0.0
    if name and number:
        text_size /= 2.5
        offset_name = text_size / 1.4
        offset_number = text_size / 1.7

    def at(offset: float) -> XY:
        # The names' frame is the pad's turned a quarter turn when they read upwards: down there is +x.
        return (centre[0] + offset, centre[1]) if angle else (centre[0], centre[1] + offset)

    out = []
    if name:
        height = min(1.5 * pad_w / max(len(name) + 1, 5), text_size) * 0.85
        if round_shape:
            height *= 0.9
        out.append(_label(name, at(min(height * 1.4, offset_name)), height, height * 0.9, angle, height * 0.9 / 6, lod, "pad"))
    if number:
        height = min(min(1.5 * pad_w / max(len(number), 3), text_size) * 0.85, text_size)
        out.append(_label(number, at(-offset_number), height, height * 0.9, angle, height * 0.9 / 6, lod, "pad"))
    return out


def _copper_number(layer: str, copper: Sequence[str]) -> int:
    """A copper layer's number as KiCad's via names count them: F.Cu 1, In1.Cu 2, ..., B.Cu the last."""
    if layer == "F.Cu":
        return 1
    if layer == "B.Cu":
        return len(copper)
    return int(layer[2:-3]) + 1


def via_labels(*, net: str | None, at: XY, width: float, kind: str, span: Sequence[str], copper: Sequence[str]) -> list[dict]:
    """A via's net name in it and, for a blind, buried or micro via, its layer pair: ``2-3``."""
    name = short_net_name(net) if net else ""
    pair = ""
    if kind != "through" and len(span) >= 2:
        pair = f"{_copper_number(span[0], copper)}-{_copper_number(span[-1], copper)}"
    if not name and not pair or width <= 0:
        return []
    size = min(width, _MAX_FONT)
    height = min(1.5 * size / max(len(name), 6 if pair else 3), size) * 0.75
    lod = _VIA_LOD_MM * KICAD_PX_PER_MM / width
    out = []
    y = at[1] + (height * 1.3 / 2 if name and pair else 0.0)
    if name:
        out.append(_label(name, (at[0], y), height, height, 0.0, height / 10, lod, "via"))
    if pair:
        if name:
            y -= height * 1.3
        out.append(_label(pair, (at[0], y), height, height, 0.0, height / 10, lod, "via"))
    return out


def is_track(item: dict) -> bool:
    """Whether a plot item is a track: a copper path carrying a net and a width (not a pour's outline or its hatch)."""
    return (item.get("t") == "path" and bool(item.get("net")) and item.get("w", 0) > 0
            and not item.get("closed") and not item.get("pairs"))


def track_name_detail(width: float) -> float:
    """The CSS pixels per millimetre a view must show for a track's name to be drawn: KiCad's 4 mm over its width."""
    return _TRACK_LOD_MM * KICAD_PX_PER_MM / width if width > 0 else math.inf


def _along(dx: float, dy: float) -> float:
    """A direction's angle as KiCad's text takes it: degrees counter-clockwise on the board (y down), read between -90 and 90."""
    angle = -math.degrees(math.atan2(dy, dx))
    while angle < -90:
        angle += 180
    while angle > 90:
        angle -= 180
    return angle


def track_labels(item: dict, viewport: tuple[float, float]) -> list[dict]:
    """A track's names in a view ``viewport`` millimetres across ``(width, height)``, as KiCad writes them.

    Its short net name, 0.55 of its width tall with a pen a twelfth of it, centred on the
    track and read along it. A segment carries one at its middle, or, long against the view,
    one per view it spans at even divisions of it (horizontal against the view's width,
    vertical its height, slanted the diagonal of its shorter side); an arc one at its middle,
    along its tangent. A track shorter than its name (a square character a width wide)
    carries none. Each is ``{"text", "at", "size", "angle", "w"}``, as a label lays out.
    """
    text = short_net_name(str(item.get("net") or ""))
    width = float(item.get("w", 0))
    points = item.get("pts") or []
    if not text or width <= 0 or len(points) < 2:
        return []
    name_size = len(text) * width

    def label(at: XY, angle: float) -> dict:
        return {"text": text, "at": (at[0], at[1]), "size": (width * 0.55, width * 0.55), "angle": angle, "w": width / 12}

    if len(points) == 2:
        (x0, y0), (x1, y1) = points
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < name_size:
            return []
        angle, span = 0.0, viewport[0]
        if dy != 0 and dx == 0:
            angle, span = 90.0, viewport[1]
        elif dy != 0:
            angle, span = _along(dx, dy), math.sqrt(2) * min(viewport)
        # KiCad's KiROUND, half away from zero (Python's round() would take a half to even).
        count = max(1, math.floor(length / span + 0.5)) if span > 0 else 1
        return [label((x0 + dx * (k / (count + 1)), y0 + dy * (k / (count + 1))), angle) for k in range(1, count + 1)]
    steps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    length = sum(steps)
    if length < name_size:
        return []
    walked = 0.0
    for (ax, ay), (bx, by), step in zip(points, points[1:], steps):
        if step > 0 and walked + step >= length / 2:
            share = (length / 2 - walked) / step
            return [label((ax + (bx - ax) * share, ay + (by - ay) * share), _along(bx - ax, by - ay))]
        walked += step
    return []
