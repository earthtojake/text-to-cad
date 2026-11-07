"""The board's own rules, as the router keeps them: each net's class, the board's minimums, the custom rules.

They come from KiCad itself, inside the edit (``cad.kicad._route``: the netclass KiCad gives each net, the
board's constraints, the project's custom rules), so the router keeps what DRC holds a board to, not a margin
of its own. Millimetres throughout.

Custom rules (a ``.kicad_dru``) hold conditions only KiCad's DRC can evaluate. The router keeps them the safe
way: every clearance a rule names (clearance, hole clearance, edge clearance, hole to hole, creepage) is kept
everywhere, the largest of each. A rule's sizes (a least track width for a net) are left to the plan and to DRC.
A ``disallow`` rule is refused by name (``custom_limits``): where it applies is a condition the router cannot
evaluate, so it cannot promise to keep it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping

from cad.engine.formats.kicad.geometry import CHORD_TOLERANCE

__all__ = ["NetClass", "Rules", "custom_limits"]


@dataclass(frozen=True)
class NetClass:
    """A netclass's routing values: its name, clearance, track width and via (diameter, drill)."""

    name: str
    clearance: float
    track_width: float
    via_diameter: float
    via_drill: float


@dataclass(frozen=True)
class Rules:
    """The rules a route keeps: each net's class (``classes``, by net name; ``default`` for a net it lacks and for
    copper of no net) and the board's minimums. ``max_error`` is how far KiCad's own arcs may stray from the
    true curve (its board setting), which every check adds, with a micron, to the clearance it keeps."""

    classes: Mapping[str, NetClass]
    default: NetClass
    min_clearance: float = 0.0
    min_track_width: float = 0.0
    edge_clearance: float = 0.0
    hole_clearance: float = 0.0
    hole_to_hole: float = 0.0
    min_via_diameter: float = 0.0
    min_via_drill: float = 0.0
    min_annulus: float = 0.0
    max_error: float = 0.005
    #: From custom rules: the largest of each clearance a rule names, and the least sizes rules ask.
    custom: Mapping[str, float] = field(default_factory=dict)

    def of(self, net: str | None) -> NetClass:
        return self.classes.get(net, self.default) if net else self.default

    def clearance(self, net: str | None, local: float | None = None) -> float:
        """The clearance copper of ``net`` keeps from other nets' copper (its class's, or ``local``, the pad's
        own, where it is larger), never under the board's minimum or a custom rule's."""
        return max(self.of(net).clearance, local or 0.0, self.min_clearance, self.custom.get("clearance", 0.0))

    @property
    def holes(self) -> float:
        return max(self.hole_clearance, self.custom.get("hole_clearance", 0.0))

    @property
    def edge(self) -> float:
        """What copper keeps from the outline as the router reads it: the edge clearance (the board's, or a custom
        rule's where larger) and ``CHORD_TOLERANCE``, since the outline's arcs are read as chords within it and a
        concave arc (a cutout's circle, a notch) passes its chords' middles on the board's side."""
        return max(self.edge_clearance, self.custom.get("edge_clearance", 0.0)) + CHORD_TOLERANCE

    @property
    def hole_gap(self) -> float:
        return max(self.hole_to_hole, self.custom.get("hole_to_hole", 0.0))

    @property
    def epsilon(self) -> float:
        """What every check adds to the clearance it keeps: KiCad's arc error and a micron."""
        return self.max_error + 0.001

    def with_custom(self, limits: Mapping[str, float]) -> "Rules":
        return replace(self, custom=dict(limits))


#: The custom constraints the router keeps everywhere, the largest of each (KiCad's constraint types, as its API
#: names them): the clearances. Creepage, measured along the surface, is never less than the straight gap:
#: keeping it as a clearance keeps it. A rule's sizes (a track's width, a via's) are the plan's to give and DRC's
#: to judge: a size held where its condition does not hold would refuse copper the board allows.
_KEPT = {
    "CRCT_CLEARANCE": "clearance", "CRCT_PHYSICAL_CLEARANCE": "clearance", "CRCT_CREEPAGE": "clearance",
    "CRCT_HOLE_CLEARANCE": "hole_clearance", "CRCT_PHYSICAL_HOLE_CLEARANCE": "hole_clearance",
    "CRCT_EDGE_CLEARANCE": "edge_clearance", "CRCT_HOLE_TO_HOLE": "hole_to_hole",
}


def custom_limits(constraints: Iterable[tuple[str, str, float]]) -> tuple[dict[str, float], list[str]]:
    """The custom rules' constraints, each (its rule's name, KiCad's constraint type, its least value in mm), as
    the router keeps them: the largest least value of each kind it keeps (``_KEPT``), and the names of the rules it
    must refuse (a ``disallow``)."""
    limits: dict[str, float] = {}
    refused: list[str] = []
    for rule, kind, least in constraints:
        if kind == "CRCT_DISALLOW":
            refused.append(rule)
        elif kind in _KEPT and least > 0:
            key = _KEPT[kind]
            limits[key] = max(limits.get(key, 0.0), least)
    return limits, sorted(dict.fromkeys(refused))
