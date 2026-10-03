"""Where a board is made: each fab's limits, for the board's checks.

Every fab makes boards from the same files: Gerber X2 layers and Excellon drills,
which ``@pcb(gerber=True)`` writes in the one form all of them take (Protel file
extensions, millimetres, absolute origin, plated and unplated holes apart, the
Gerber job file). The BOM and the placement file are one form for every
assembler too: JLCPCB's required column names, which the others accept, plus
every field any of them asks for (MPN, manufacturer, description, package).

What differs from fab to fab is what it can make: the narrowest track, the
smallest drill, how close copper may come to a hole or the edge. A :class:`Fab`
holds those limits for its standard service -- the price tier with no
surcharge -- for two copper layers and for four or more, and a board checked
against them is one that fab makes at its base price. The numbers are each
fab's own capability pages (``capabilities``), read 2026-10-03. KiCad has one
value where a fab may give several (a via's hole against a component hole's,
say): the stricter is taken. Each preset's default net class (the tracks and
vias a board uses unless a net class says otherwise) sits comfortably inside
its own limits.
"""

from __future__ import annotations

from dataclasses import dataclass

from cadgen.kicad.design import Rules

__all__ = ["AISLER", "EUROCIRCUITS", "FABS", "Fab", "JLCPCB", "NEXTPCB", "OSHPARK", "PCBWAY", "SEEED_FUSION"]


@dataclass(frozen=True)
class Fab:
    """A PCB fab's standard service: its limits on two copper layers and on four or more."""

    name: str
    rules: Rules  # two copper layers
    multilayer: Rules  # four or more
    assembles: bool  # whether it also places and solders parts
    capabilities: str  # where the numbers come from

    def rules_for(self, layers: int) -> Rules:
        """The limits for a board of ``layers`` copper layers."""
        return self.rules if layers <= 2 else self.multilayer

    def __repr__(self) -> str:
        return f"Fab({self.name})"


def _rules(
    *,
    track: float,
    clearance: float,
    via: float,
    annular: float,
    drill: float,
    hole_to_hole: float,
    hole_clearance: float,
    edge: float,
    text_height: float,
    text_thickness: float,
    default_via: tuple[float, float] = (0.6, 0.3),
) -> Rules:
    return Rules(
        min_clearance=clearance,
        min_track_width=track,
        min_via_diameter=via,
        min_via_annular_width=annular,
        min_through_hole_diameter=drill,
        min_hole_to_hole=hole_to_hole,
        min_hole_clearance=hole_clearance,
        min_copper_edge_clearance=edge,
        min_silk_clearance=0.0,
        min_text_height=text_height,
        min_text_thickness=text_thickness,
        track_width=0.25,
        clearance=0.2,
        via_diameter=default_via[0],
        via_drill=default_via[1],
    )


#: JLCPCB. Its free via is a 0.3 mm hole in a 0.45 mm pad (0.2 and 0.25 mm holes cost
#: extra); component holes keep 0.28 mm from copper and 0.45 mm from each other (vias
#: may come closer: the stricter value is the one checked).
JLCPCB = Fab(
    name="JLCPCB",
    rules=_rules(track=0.1, clearance=0.1, via=0.45, annular=0.075, drill=0.3, hole_to_hole=0.45,
                 hole_clearance=0.28, edge=0.2, text_height=1.0, text_thickness=0.15),
    multilayer=_rules(track=0.09, clearance=0.09, via=0.45, annular=0.075, drill=0.3, hole_to_hole=0.45,
                      hole_clearance=0.3, edge=0.2, text_height=1.0, text_thickness=0.15),
    assembles=True,
    capabilities="https://jlcpcb.com/capabilities/pcb-capabilities",
)

#: PCBWay, as its own KiCad design-rules file sets its standard service (its capability
#: page states 0.1 mm tracks; 0.127 is what it publishes for KiCad).
PCBWAY = Fab(
    name="PCBWay",
    rules=_rules(track=0.127, clearance=0.127, via=0.5, annular=0.1, drill=0.2, hole_to_hole=0.41,
                 hole_clearance=0.33, edge=0.3, text_height=0.8, text_thickness=0.15),
    # Inner layers reach 0.1 mm, but KiCad holds one limit for every layer: the outer one.
    multilayer=_rules(track=0.127, clearance=0.127, via=0.5, annular=0.1, drill=0.2, hole_to_hole=0.41,
                      hole_clearance=0.33, edge=0.3, text_height=0.8, text_thickness=0.15),
    assembles=True,
    capabilities="https://www.pcbway.com/capabilities.html",
)

#: OSH Park: bare boards only, its 2-layer and 4-layer services.
OSHPARK = Fab(
    name="OSH Park",
    rules=_rules(track=0.152, clearance=0.152, via=0.508, annular=0.127, drill=0.254, hole_to_hole=0.127,
                 hole_clearance=0.127, edge=0.381, text_height=0.8, text_thickness=0.127),
    multilayer=_rules(track=0.127, clearance=0.127, via=0.457, annular=0.102, drill=0.254, hole_to_hole=0.127,
                      hole_clearance=0.254, edge=0.381, text_height=0.8, text_thickness=0.127),
    assembles=False,
    capabilities="https://docs.oshpark.com/services/two-layer/",
)

#: Aisler: its base 2-layer HASL board, and its 4-layer ENIG board (2-layer ENIG reaches
#: the finer limits too). Its vias want a 0.175 mm ring at least, so its default via is
#: 0.3/0.7 mm.
AISLER = Fab(
    name="Aisler",
    rules=_rules(track=0.2, clearance=0.15, via=0.65, annular=0.175, drill=0.3, hole_to_hole=0.3,
                 hole_clearance=0.25, edge=0.3, text_height=0.8, text_thickness=0.15, default_via=(0.7, 0.3)),
    multilayer=_rules(track=0.125, clearance=0.125, via=0.45, annular=0.1, drill=0.25, hole_to_hole=0.3,
                      hole_clearance=0.25, edge=0.3, text_height=0.8, text_thickness=0.15, default_via=(0.7, 0.3)),
    assembles=True,
    capabilities="https://community.aisler.net/t/2-layer-1-6-mm-35-m-hasl-design-rules/3735",
)

#: Eurocircuits' PCB proto service (pattern class 6). Its pages give a 0.25 or a 0.35 mm
#: smallest finished hole; 0.35 is checked, with a pad 0.35 mm wider than its hole.
EUROCIRCUITS = Fab(
    name="Eurocircuits",
    rules=_rules(track=0.15, clearance=0.15, via=0.7, annular=0.175, drill=0.35, hole_to_hole=0.25,
                 hole_clearance=0.2, edge=0.25, text_height=1.0, text_thickness=0.1, default_via=(0.7, 0.35)),
    multilayer=_rules(track=0.15, clearance=0.15, via=0.7, annular=0.175, drill=0.35, hole_to_hole=0.25,
                      hole_clearance=0.2, edge=0.4, text_height=1.0, text_thickness=0.1, default_via=(0.7, 0.35)),
    assembles=True,
    capabilities="https://www.eurocircuits.com/services/pcb-proto/",
)

#: Seeed Fusion's standard service (6/6 mil, 0.3 mm drill). It publishes no annular ring
#: or hole spacing, so those are the conservative values of the other fabs.
SEEED_FUSION = Fab(
    name="Seeed Fusion",
    rules=_rules(track=0.152, clearance=0.152, via=0.6, annular=0.15, drill=0.3, hole_to_hole=0.5,
                 hole_clearance=0.25, edge=0.3, text_height=0.6, text_thickness=0.1),
    multilayer=_rules(track=0.152, clearance=0.152, via=0.6, annular=0.15, drill=0.3, hole_to_hole=0.5,
                      hole_clearance=0.25, edge=0.3, text_height=0.6, text_thickness=0.1),
    assembles=True,
    capabilities="https://wiki.seeedstudio.com/Service_for_Fusion_PCB/",
)

#: NextPCB's standard service (5/5 mil, 0.3 mm drill), as its "Simple" KiCad template avoids
#: extra cost.
NEXTPCB = Fab(
    name="NextPCB",
    rules=_rules(track=0.127, clearance=0.127, via=0.48, annular=0.09, drill=0.3, hole_to_hole=0.3,
                 hole_clearance=0.23, edge=0.2, text_height=0.762, text_thickness=0.127),
    multilayer=_rules(track=0.127, clearance=0.127, via=0.48, annular=0.09, drill=0.3, hole_to_hole=0.3,
                      hole_clearance=0.23, edge=0.2, text_height=0.762, text_thickness=0.127),
    assembles=True,
    capabilities="https://www.nextpcb.com/pcb-capabilities",
)

#: Every preset, by name.
FABS: dict[str, Fab] = {fab.name: fab for fab in (JLCPCB, PCBWAY, OSHPARK, AISLER, EUROCIRCUITS, SEEED_FUSION, NEXTPCB)}
