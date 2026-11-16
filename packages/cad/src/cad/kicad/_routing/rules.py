"""The board's own rules, as the router keeps them: each net's class, the board's minimums, the custom rules.

They come from KiCad itself, inside the edit (``cad.kicad._route``: the netclass KiCad gives each net, the
board's constraints, the project's custom rules), so the router keeps what DRC holds a board to, not a margin
of its own. Millimetres throughout.

Custom rules (a ``.kicad_dru``) hold conditions only KiCad's DRC can evaluate. ``read_custom`` sorts each
constraint of each rule:

- every clearance a rule names (clearance, hole clearance, edge clearance, hole to hole, creepage) is kept
  everywhere, the largest of each, whatever its condition;
- a size of a rule that holds everywhere (no condition, no one layer) is kept as KiCad's DRC holds it: a track's
  width (refused outside it), a via's diameter, hole and annular ring (the router's via taken up to its least,
  refused past its most) and a net's via count (each entry's via limit lowered to fit);
- a ``disallow`` or an ``assertion`` (an expression DRC holds every item it matches to) is refused by name: where it
  applies is a condition the router cannot evaluate, so it cannot promise to keep it;
- every other constraint that can bear on new copper, and every size of a rule with a condition or a layer, is a
  warning naming the rule, said before routing: the router does not keep it, and DRC judges it after;
- the constraints that cannot bear on new copper (``_APART``) are passed over, each with why.

A rule whose severity is ``ignore`` is one KiCad's DRC does not hold, so neither does the router.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Mapping, Sequence

from cad.engine.formats.kicad.geometry import CHORD_TOLERANCE

__all__ = ["Bound", "Constraint", "Custom", "NetClass", "Rules", "read_custom"]

#: What every check keeps past a clearance besides KiCad's arc error: a micron.
SPARE = 0.001


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
    #: From custom rules: the largest of each clearance a rule names (``clearance``, ``hole_clearance``,
    #: ``edge_clearance``, ``hole_to_hole``), and the sizes rules that hold everywhere set (``Bound``s, by the name
    #: of their kind: ``track_width``, ``via_diameter``, ``hole_size``, ``annular_width``, ``via_count``).
    custom: Mapping[str, float] = field(default_factory=dict)
    sizes: Mapping[str, "Bound"] = field(default_factory=dict)

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
        return self.max_error + SPARE

    def with_custom(self, limits: Mapping[str, float], sizes: Mapping[str, "Bound"] | None = None) -> "Rules":
        return replace(self, custom=dict(limits), sizes=dict(sizes or {}))


@dataclass(frozen=True)
class Constraint:
    """One constraint of a custom rule, as KiCad's API gives it: its ``rule``'s name; KiCad's constraint ``kind``
    (``CRCT_TRACK_WIDTH``); the rule's ``condition`` (empty where it has none) and ``layer`` (the one copper layer it
    is limited to, empty for none); its ``least``, ``opt`` and ``most`` (None where the rule sets none), in mm, or a
    count or degrees where its kind counts or turns (``unit``); ``ignored`` where its severity is ``ignore``.

    KiCad's API (10.99, probed) gives a rule's ``(layer outer)`` or ``(layer inner)`` as no layer at all: such a rule
    reads as holding on every layer, which keeps it the safe way."""

    rule: str
    kind: str
    condition: str = ""
    layer: str = ""
    least: float | None = None
    opt: float | None = None
    most: float | None = None
    ignored: bool = False

    @property
    def everywhere(self) -> bool:
        return not self.condition.strip() and not self.layer

    def said(self) -> str:
        """The constraint as a ``.kicad_dru`` names it, with its bounds: ``track_width min 0.15 mm, max 1 mm``."""
        unit = UNITS.get(self.kind, " mm")
        bounds = [f"{name} {value:g}{unit}" for name, value in (("min", self.least), ("opt", self.opt),
                                                               ("max", self.most)) if value is not None]
        return " ".join([keyword(self.kind), ", ".join(bounds)]).strip()


#: The constraint kinds not measured in nanometres by KiCad's API (each its unit as said); every other one is a
#: length, read in mm.
UNITS = {"CRCT_VIA_COUNT": "", "CRCT_MIN_RESOLVED_SPOKES": "", "CRCT_TRACK_ANGLE": " deg",
         "CRCT_SOLDER_PASTE_REL_MARGIN": " %"}
#: Where KiCad's ``.kicad_dru`` keyword is not its API's constraint name, lower-cased.
_KEYWORDS = {"CRCT_MAX_UNCOUPLED": "diff_pair_uncoupled", "CRCT_DIFF_PAIR_INTRA_SKEW": "skew (within_diff_pairs)"}


def keyword(kind: str) -> str:
    """A constraint kind as a ``.kicad_dru`` names it (``CRCT_TRACK_WIDTH``: ``track_width``)."""
    return _KEYWORDS.get(kind, kind.removeprefix("CRCT_").lower())


def scale(kind: str) -> float:
    """What a raw value of KiCad's API for a constraint of ``kind`` is multiplied by to read it (``UNITS``)."""
    return 1.0 if kind in UNITS else 1e-6


@dataclass(frozen=True)
class Bound:
    """A size custom rules hold everywhere: its ``least`` and ``most`` (None where no rule sets one) and the rule
    that sets each. KiCad's DRC holds each bound of the last rule that sets it (probed: ``(min 0.3mm)`` in one rule,
    ``(max 1mm)`` in a later one, both held; two rules' ``min``, the later's)."""

    least: float | None = None
    least_rule: str = ""
    most: float | None = None
    most_rule: str = ""


@dataclass(frozen=True)
class Custom:
    """The custom rules as the router keeps them: the clearances (``limits``), the sizes (``sizes``), the rules it
    refuses (``refused``) and the warnings it says (``warnings``, one sentence each, a rule once)."""

    limits: dict[str, float]
    sizes: dict[str, Bound]
    refused: list[str]
    warnings: list[str]


#: The clearances, kept everywhere, the largest of each. Creepage, measured along the surface, is never less than
#: the straight gap: keeping it as a clearance keeps it.
_KEPT = {
    "CRCT_CLEARANCE": "clearance", "CRCT_PHYSICAL_CLEARANCE": "clearance", "CRCT_CREEPAGE": "clearance",
    "CRCT_HOLE_CLEARANCE": "hole_clearance", "CRCT_PHYSICAL_HOLE_CLEARANCE": "hole_clearance",
    "CRCT_EDGE_CLEARANCE": "edge_clearance", "CRCT_HOLE_TO_HOLE": "hole_to_hole",
}
#: The sizes kept where a rule holds everywhere (by the name ``Rules.sizes`` keys them by). A size held where its
#: condition does not hold would refuse copper the board allows, so a rule with a condition is said, not kept.
_SIZES = {"CRCT_TRACK_WIDTH": "track_width", "CRCT_VIA_DIAMETER": "via_diameter", "CRCT_HOLE_SIZE": "hole_size",
          "CRCT_ANNULAR_WIDTH": "annular_width", "CRCT_VIA_COUNT": "via_count"}
#: The constraints refused by name.
_REFUSED = ("CRCT_DISALLOW", "CRCT_ASSERTION")
#: The constraints that cannot bear on the copper the router adds (a net's tracks and through vias, beside
#: copper it never moves), passed over, each with why.
_APART = {
    "CRCT_COURTYARD_CLEARANCE": "footprints' courtyards, which no track or via has",
    "CRCT_TEXT_HEIGHT": "texts, which the router makes none of",
    "CRCT_TEXT_THICKNESS": "texts, which the router makes none of",
    "CRCT_ZONE_CONNECTION": "how a pour joins its pads, which the refill draws round the new copper",
    "CRCT_THERMAL_RELIEF_GAP": "the thermal reliefs a refill draws, round the new copper",
    "CRCT_THERMAL_SPOKE_WIDTH": "the thermal reliefs a refill draws, round the new copper",
    "CRCT_SOLDER_PASTE_ABS_MARGIN": "pads' paste, which tracks and vias have none of",
    "CRCT_SOLDER_PASTE_REL_MARGIN": "pads' paste, which tracks and vias have none of",
    "CRCT_BRIDGED_MASK": "leave to bridge the solder mask, where the router keeps every opening apart anyway",
    "CRCT_MICROVIA_STACK_DEPTH": "microvias, where the router places through vias alone",
    "CRCT_MICROVIA_ASPECT_RATIO": "microvias, where the router places through vias alone",
}
#: What the agent does about a constraint the router does not keep (the warning's fix), by its kind.
_FIXES = {
    "CRCT_TRACK_WIDTH": "give those entries a width it allows",
    "CRCT_VIA_DIAMETER": "give those nets' netclass a via it allows (the .kicad_pro), or those entries vias: 0",
    "CRCT_HOLE_SIZE": "give those nets' netclass a via it allows (the .kicad_pro), or those entries vias: 0",
    "CRCT_ANNULAR_WIDTH": "give those nets' netclass a via it allows (the .kicad_pro), or those entries vias: 0",
    "CRCT_VIA_COUNT": "give those entries a via limit (vias) it allows",
    "CRCT_LENGTH": "route those nets by hand, to length",
    "CRCT_SKEW": "route those nets by hand, to length",
    "CRCT_NET_CHAIN_LENGTH": "route those nets by hand, to length",
    "CRCT_NET_CHAIN_STUB_LENGTH": "route those nets by hand, to length",
    "CRCT_SILK_CLEARANCE": "move the silk DRC finds too near",
    "CRCT_SOLDER_MASK_EXPANSION": "tent the board's vias, or give those entries vias: 0",
    "CRCT_SOLDER_MASK_SLIVER": "tent the board's vias, or give those entries vias: 0",
    "CRCT_MIN_RESOLVED_SPOKES": "route by hand round the pads whose spokes it counts",
}


def read_custom(constraints: Sequence[Constraint]) -> Custom:
    """The custom rules' constraints, in the order KiCad gives them (its file's), sorted as the module's doc says."""
    limits: dict[str, float] = {}
    sizes: dict[str, Bound] = {}
    refused: list[str] = []
    said: dict[str, list[Constraint]] = {}  # each rule's constraints the router does not keep, in order
    live = [c for c in constraints if not c.ignored]
    for k, c in enumerate(live):
        if c.kind in _REFUSED:
            refused.append(c.rule)
        elif c.kind in _KEPT:
            if c.least is not None and c.least > 0:
                key = _KEPT[c.kind]
                limits[key] = max(limits.get(key, 0.0), c.least)
        elif c.kind in _SIZES and c.everywhere:
            key = _SIZES[c.kind]
            bound = sizes.get(key, Bound())
            if c.least is not None:
                bound = replace(bound, least=c.least, least_rule=c.rule)
            if c.most is not None:
                bound = replace(bound, most=c.most, most_rule=c.rule)
            sizes[key] = bound
        elif c.kind in _SIZES:
            # Held only where no later rule that holds everywhere sets the same bounds (KiCad holds the later).
            later = [d for d in live[k + 1:] if d.kind == c.kind and d.everywhere]
            if ((c.least is not None and not any(d.least is not None for d in later))
                    or (c.most is not None and not any(d.most is not None for d in later))):
                said.setdefault(c.rule, []).append(c)
        elif c.kind not in _APART:
            said.setdefault(c.rule, []).append(c)
    warnings = [_warning(rule, kept) for rule, kept in said.items()]
    return Custom(limits, sizes, sorted(dict.fromkeys(refused)), warnings)


def _warning(rule: str, constraints: Sequence[Constraint]) -> str:
    first = constraints[0]
    where = (f", where ({first.condition.strip()})" if first.condition.strip() else "") + (
        f", on {first.layer}" if first.layer else "")
    held = ("holds where a condition only KiCad's DRC evaluates" if first.condition.strip()
            else f"holds on {first.layer} alone" if first.layer else "holds everywhere")
    fixes = list(dict.fromkeys(_FIXES.get(c.kind, "route by hand where it binds") for c in constraints))
    return (f"the custom rule {rule!r} ({'; '.join(c.said() for c in constraints)}{where}) {held}; the router does "
            f"not keep it: {'; '.join(fixes)}, and read DRC after")
