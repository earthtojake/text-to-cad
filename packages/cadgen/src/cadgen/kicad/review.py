"""The review: what a person reviewing a board checks that KiCad's ERC and DRC do not.

Three checks, each a warning (advice, never a gate): an IC's power input with no decoupling
capacitor to ground, the nearest one too far from it, and a net's tracks too thin for the
current its script gives it (``board.net("VBUS", current=2.0)``, kept in the ``.kicad_pro``
because KiCad keeps no current per net). Each finding names what it is about in board
references, so the viewer selects it and an agent resolves it.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from pathlib import Path

from cadgen.kicad.board_index import BoardIndex, Finding, FindingItem, Net

__all__ = ["DECOUPLING_DISTANCE", "TEMPERATURE_RISE", "is_ground", "net_currents", "required_width", "review"]

DECOUPLING_DISTANCE = 3.0  # mm, pad centre to pad centre
TEMPERATURE_RISE = 10.0  # °C, IPC-2221's outer-layer chart
_COPPER_MILS = 1.378  # 1 oz copper
_GROUND = re.compile(r"(?:.*/)?(?:[ADP]?GND\w*|VSS\w*|0V)", re.IGNORECASE)
_CAPACITOR = re.compile(r"C\d+")


def is_ground(net: str | None) -> bool:
    return bool(net) and _GROUND.fullmatch(net) is not None


def required_width(current: float) -> float:
    """The track width (mm) IPC-2221 gives ``current`` amperes on 1 oz outer copper at a 10 °C rise."""
    area = (current / (0.048 * TEMPERATURE_RISE**0.44)) ** (1 / 0.725)  # square mils
    return area / _COPPER_MILS * 0.0254


def net_currents(project: Path | None) -> dict[str, float]:
    """The currents a board's script gave its nets, from its project file; none when unreadable."""
    if project is None:
        return {}
    try:
        data = json.loads(Path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    currents = (data.get("cadgen") or {}).get("net_currents") or {} if isinstance(data, dict) else {}
    return {str(name): float(value) for name, value in currents.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0}


def _finding(type: str, summary: str, description: str, items: list[FindingItem]) -> Finding:
    return Finding(check="review", severity="warning", type=type, description=description, items=tuple(items), summary=summary)


def review(index: BoardIndex, currents: Mapping[str, float] | None = None) -> tuple[Finding, ...]:
    """The review's findings on ``index``, in its frame: decoupling per IC and power net, then currents."""
    found: list[Finding] = []
    capacitors = [part for part in index.parts if _CAPACITOR.fullmatch(part.ref) and not part.dnp]
    for part in index.parts:
        inputs: dict[str, list] = {}
        for pad in part.pads:
            if pad.type == "power_in" and pad.net and not is_ground(pad.net) and not pad.net.startswith("unconnected-("):
                inputs.setdefault(pad.net, []).append(pad)
        for net, pads in inputs.items():
            decoupling = [
                (cap, cap_pad) for cap in capacitors if cap.ref != part.ref
                if any(is_ground(other.net) for other in cap.pads)
                for cap_pad in cap.pads if cap_pad.net == net
            ]
            first = pads[0]
            if not decoupling:
                found.append(_finding(
                    "decoupling_missing", f"{part.ref}'s {net} has no decoupling capacitor",
                    f"No capacitor joins {net} to ground; {part.ref}'s power input {first.number} is on it.",
                    [FindingItem(text=f"{part.ref} pad {first.number} ({net})", ref=first.selector, at=first.at)],
                ))
                continue
            distance, pad, cap, cap_pad = min(
                ((math.dist(pad.at, cap_pad.at), pad, cap, cap_pad) for pad in pads for cap, cap_pad in decoupling),
                key=lambda entry: entry[0],
            )
            if distance > DECOUPLING_DISTANCE:
                found.append(_finding(
                    "decoupling_far",
                    f"{part.ref}'s {net}: the nearest decoupling capacitor, {cap.ref}, is {distance:.1f} mm away "
                    f"(aim for under {DECOUPLING_DISTANCE:g} mm)",
                    f"{part.ref} pad {pad.number} to {cap.ref} pad {cap_pad.number}: {distance:.2f} mm, centre to centre; "
                    f"review threshold {DECOUPLING_DISTANCE:g} mm.",
                    [FindingItem(text=f"{part.ref} pad {pad.number} ({net})", ref=pad.selector, at=pad.at),
                     FindingItem(text=f"{cap.ref} pad {cap_pad.number} ({net})", ref=cap_pad.selector, at=cap_pad.at)],
                ))
    for net, current in sorted((currents or {}).items()):
        tracks = [track for track in index.tracks if track.net == net]
        if not tracks:
            continue
        need = required_width(current)
        thinnest = min(tracks, key=lambda track: track.width)
        if thinnest.width + 1e-6 < need:
            found.append(_finding(
                "track_current",
                f"{net} carries {current:g} A; its narrowest track is {thinnest.width:g} mm, it needs about {need:.1f} mm",
                f"IPC-2221, 1 oz outer copper, {TEMPERATURE_RISE:g} °C rise: {need:.2f} mm for {current:g} A; "
                f"narrowest {thinnest.width:g} mm on {thinnest.layer}.",
                [FindingItem(text=f"the {net} track", ref=Net(name=net, netclass="").selector, at=thinnest.points[0])],
            ))
    return tuple(found)
