"""CNC machining, milling and turning: its options, rule sets, findings and summary (``cad._internal.dfm``).

Measured on exact geometry alone (a STEP, an xbf, a document the engine holds; ``cad.build123d._dfm_cnc``
says how): holes, pockets, internal corners, sharp concave edges no rotating tool makes, walls, gaps, tool
access and setups per approach direction, closed voids, stock, small features, and with ``turning`` the
axis, diameters, bores, grooves and live-tooling features.

The rule sets: ``generic`` (text-to-cad's starting point, each number from Protolabs Network (Hubs)'s CNC
guide unless it says otherwise), ``hubs``, ``protolabs`` (its milling and turning guidelines) and
``xometry`` (its design-tips article and its CNC service's capability list). A limit that follows the tools
given (``--tools``) is the smallest tool's; without ``--tools`` the source's own number stands.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from cad._internal.dfm import materials
from cad._internal.dfm._common import mm
from cad._internal.dfm.rules import Rule, RuleSet, Source
from cad.results import CheckFinding

__all__ = ["MEASURED_FROM", "OPTIONS", "RULE_SETS", "context", "findings", "summary", "validate"]

OPTIONS: dict[str, Any] = {"axes": 3, "turning": False, "tools": None, "stock": None}
MEASURED_FROM = ("brep",)

_ACCESSED = "2026-11-03"
HUBS = Source("hubs-cnc", "Protolabs Network (Hubs)", "How to design parts for CNC machining",
              "https://www.hubs.com/knowledge-base/how-design-parts-cnc-machining/", _ACCESSED)
PROTOLABS_MILLING = Source("protolabs-milling", "Protolabs", "CNC milling design guidelines",
                           "https://www.protolabs.com/services/cnc-machining/cnc-milling/design-guidelines/", _ACCESSED)
PROTOLABS_TURNING = Source("protolabs-turning", "Protolabs", "CNC turning design guidelines",
                           "https://www.protolabs.com/services/cnc-machining/cnc-turning/design-guidelines/", _ACCESSED)
XOMETRY_TIPS = Source("xometry-tips", "Xometry", "10 tips to improve your CAD designs for CNC machining",
                      "https://www.xometry.com/resources/machining/10-tips-improve-cad-cnc-design/", _ACCESSED)
XOMETRY_SERVICE = Source("xometry-cnc", "Xometry", "CNC machining service: capabilities",
                         "https://www.xometry.com/capabilities/cnc-machining-service/", _ACCESSED)

#: Within this share of its area, a face a sample of which no direction reached is still reached: one
#: sampled point is a few percent of a small face, and a ray grazing an edge is no undercut.
ACCESS_TOLERANCE = 0.02

_MILLING = {"turning": False}
_TURNING = {"turning": True}
_NO_TOOLS = {"tools_given": False}
_TOOLS = {"tools_given": True}


#: Without ``--tools``, the radius a sharp corner or edge is told to take: a 2.5 mm end mill's, the smallest
#: standard tool (Hubs: features under 2.5 mm are micro-machining; Xometry: the smallest standard tool).
_SMALL_TOOL_RADIUS = 1.25
#: What a failing item says of itself, appended to the message (``Rule.detail``).
_CORNER_DETAIL = "{edge}, {height_mm:g} mm tall, {depth_mm:g} mm below the top"
_EDGE_DETAIL = "{edge} between {between}, a {void_angle_deg:.0f}-degree void, at {xyz}"
_ACROSS_DETAIL = {"walls": "to {opposite} at {xyz}", "gaps": "to {opposite} at {xyz}"}


def _corner_rules(source: str, sharp_note: str, radius: Any = _SMALL_TOOL_RADIUS,
                  by: str | None = None) -> tuple[Rule, ...]:
    """A sharp vertical corner and a sharp concave edge, judged against the radius they must be given: half
    the smallest tool with ``--tools``, else ``radius`` (a mapping chosen by the context key ``by``)."""
    corner_fix = ("sharp vertical corner: give it a radius of at least {limit:g} mm (a third of the cavity's "
                  "depth or more is better), or a dog-bone relief, or plan EDM")
    acute_fix = ("its {void_angle_deg:.0f}-degree void is under 90, so no tool's end or side reaches its root: open "
                 "it to 90 degrees or more, round it to at least {limit:g} mm, or plan EDM")
    obtuse_fix = ("neither face at its {void_angle_deg:.0f}-degree void is a plane square to a machine direction, "
                  "so no tool's corner makes it sharp: round it to at least {limit:g} mm (a ball end mill's "
                  "radius), square one face to an approach direction, or give more axes")
    found: list[Rule] = []
    for when, scale, limit, key in (({**_MILLING, **_TOOLS}, "min_tool_mm", 0.5, None),
                                    ({**_MILLING, **_NO_TOOLS}, None, radius, by)):
        found += [
            Rule("cnc.internal_corner_sharp", "internal_corners", "radius_mm", "min", limit, "mm",
                 "sharp vertical corner radius", source, scale_by=scale, by=key, when=when,
                 item_when={"sharp": True}, fix=corner_fix, note=sharp_note, detail=_CORNER_DETAIL),
            Rule("cnc.sharp_internal_edge", "sharp_edges", "radius_mm", "min", limit, "mm",
                 "sharp concave edge (void under 90 degrees) radius", source, scale_by=scale, by=key, when=when,
                 item_when={"acute": True}, fix=acute_fix, note=sharp_note, detail=_EDGE_DETAIL),
            Rule("cnc.sharp_internal_edge", "sharp_edges", "radius_mm", "min", limit, "mm",
                 "sharp concave edge (no face square to a machine direction) radius", source, scale_by=scale,
                 by=key, when=when, item_when={"acute": False}, fix=obtuse_fix, note=sharp_note,
                 detail=_EDGE_DETAIL)]
    found.append(Rule("cnc.internal_corner_radius", "internal_corners", "radius_mm", "min", 0.5, "mm",
                      "internal corner radius", source, scale_by="min_tool_mm", when={**_MILLING, **_TOOLS},
                      item_when={"sharp": False},
                      fix="radius the corner to at least {limit:g} mm, the smallest tool's radius, or add a smaller "
                          "tool", note="a corner tighter than the smallest end mill's radius is not cut by it"))
    return tuple(found)


def _knife_rule(source: str, limit: Any, by: str | None, note: str) -> Rule:
    return Rule("cnc.knife_edge", "knife_edges", "thickness_mm", "min", limit, "mm",
                "material at a knife edge (a convex edge under 45 deg)", source, severity="warning", by=by,
                fix="blunt it -- a flat or round at least {limit:g} mm across -- or open its angle to 45 deg or more",
                note=note)


_GENERIC_RULES: tuple[Rule, ...] = (
    *_corner_rules("hubs-cnc", "every CNC tool is round, so an internal vertical edge always has a radius"),
    Rule("cnc.internal_corner_radius", "internal_corners", "radius_mm", "min", 0.025, "mm",
         "internal corner radius", "hubs-cnc", when={**_MILLING, **_NO_TOOLS}, item_when={"sharp": False},
         fix="radius the corner to at least {limit:g} mm (no micro-tool cuts tighter)",
         note="micro-machining tools go down to 0.05 mm in diameter"),
    Rule("cnc.internal_corner_small", "internal_corners", "radius_mm", "min", 1.25, "mm",
         "internal corner radius", "hubs-cnc", severity="warning", when={**_MILLING, **_NO_TOOLS},
         item_when={"sharp": False}, fix="radius the corner to {limit:g} mm or more, so a 2.5 mm end mill cuts it",
         note="features under 2.5 mm are micro-machining"),
    Rule("cnc.corner_radius_to_depth", "internal_corners", "radius_to_depth", "min", 0.3333, "ratio",
         "corner radius to cavity depth", "hubs-cnc", severity="warning", when=_MILLING,
         item_when={"sharp": False}, fix="make the corner radius at least a third of the cavity's depth",
         note="recommended: an internal vertical corner radius of a third of the cavity depth or more"),
    Rule("cnc.corner_reach", "internal_corners", "reach_ratio", "max", 4.0, "ratio",
         "depth to the diameter of the largest tool that fits the corner", "hubs-cnc", severity="warning",
         when=_MILLING, fix="a larger corner radius or a shallower cavity: end mills cut 3 to 4 diameters deep",
         note="end mills typically cut to 3-4 times their diameter"),
    Rule("cnc.corner_reach_limit", "internal_corners", "reach_ratio", "max", 30.0, "ratio",
         "depth to the diameter of the largest tool that fits the corner", "hubs-cnc", when=_MILLING,
         fix="a larger corner radius or a shallower cavity: 30 diameters is the deepest even special tooling reaches",
         note="up to 30:1 depth to tool diameter with specialized tooling"),
    Rule("cnc.pocket_depth_to_width", "pockets", "depth_to_width", "max", 4.0, "ratio",
         "cavity depth to width", "hubs-cnc", severity="warning", when=_MILLING,
         fix="make the cavity no deeper than {limit:g} times its width", note="recommended cavity depth: 4x width"),
    Rule("cnc.wall_thickness", "walls", "thickness_mm", "min", {"metal": 0.5, "plastic": 1.0}, "mm",
         "wall thickness", "hubs-cnc", by="wall_class",
         fix="thicken the wall to at least {limit:g} mm",
         note="feasible minimum walls: 0.5 mm metal, 1.0 mm plastic"),
    Rule("cnc.wall_thickness_recommended", "walls", "thickness_mm", "min", {"metal": 0.8, "plastic": 1.5}, "mm",
         "wall thickness", "hubs-cnc", severity="warning", by="wall_class",
         fix="thicken the wall to {limit:g} mm or more",
         note="recommended minimum walls: 0.8 mm metal, 1.5 mm plastic"),
    _knife_rule("hubs-cnc", {"metal": 0.5, "plastic": 1.0}, "wall_class",
                "the material thins to nothing at an acute convex edge: judged against the feasible wall"),
    Rule("cnc.hole_diameter_limit", "holes", "diameter_mm", "min", 0.05, "mm", "hole diameter", "hubs-cnc",
         fix="make the hole at least {limit:g} mm", note="micro-drills go down to 0.05 mm"),
    Rule("cnc.hole_diameter", "holes", "diameter_mm", "min", 1.0, "mm", "hole diameter", "hubs-cnc",
         severity="warning", fix="make the hole 1 mm or more: smaller is micro-drilling",
         note="any hole above 1 mm is feasible"),
    Rule("cnc.hole_depth", "holes", "depth_to_diameter", "max", 4.0, "ratio", "hole depth to diameter",
         "hubs-cnc", severity="warning", fix="limit the depth to {limit:g} diameters, or widen the hole",
         note="recommended hole depth: 4x the nominal diameter"),
    Rule("cnc.hole_depth_limit", "holes", "depth_to_diameter", "max", 40.0, "ratio", "hole depth to diameter",
         "hubs-cnc", fix="no drill reaches {value:.3g} diameters: shorten or widen the hole",
         note="feasible maximum hole depth: 40x the diameter"),
    Rule("cnc.drill_size", "holes", "drill_deviation_mm", "max", 0.005, "mm",
         "distance from the nearest standard drill", "hubs-cnc", severity="warning", item_when={"drilled": True},
         fix="use a standard drill diameter (metric, fractional, number or letter), or the hole is milled",
         note="recommended: a standard drill bit size"),
    Rule("cnc.thread_size", "threads", "major_diameter_mm", "min", 6.0, "mm", "thread major diameter", "hubs-cnc",
         severity="warning", fix="M6 or larger where it can be: smaller threads are tapped, not thread-milled",
         note="threads M6 or larger recommended; taps go down to M2"),
    Rule("cnc.thread_length", "threads", "length_to_diameter", "max", 3.0, "ratio", "thread length to diameter",
         "hubs-cnc", severity="warning", fix="thread no more than 3 diameters: longer adds no strength",
         note="thread length beyond 3x the nominal diameter is unnecessary"),
    Rule("cnc.thread_length_minimum", "threads", "length_to_diameter", "min", 1.5, "ratio",
         "thread length to diameter", "hubs-cnc", severity="warning", fix="thread at least 1.5 diameters",
         note="minimum thread length 1.5x the nominal diameter"),
    Rule("cnc.gap_width", "gaps", "width_mm", "min", 0.05, "mm", "gap width", "hubs-cnc",
         when={**_MILLING, **_NO_TOOLS}, fix="widen the gap to at least {limit:g} mm",
         note="no micro-tool is under 0.05 mm"),
    Rule("cnc.gap_width", "gaps", "width_mm", "min", 1.0, "mm", "gap width", "hubs-cnc", scale_by="min_tool_mm",
         when={**_MILLING, **_TOOLS}, fix="widen the gap to at least {limit:g} mm, the smallest tool's diameter",
         note="a tool cuts no gap narrower than itself"),
    Rule("cnc.gap_width_small", "gaps", "width_mm", "min", 2.5, "mm", "gap width", "hubs-cnc", severity="warning",
         when={**_MILLING, **_NO_TOOLS}, fix="widen the gap to {limit:g} mm or more",
         note="features under 2.5 mm are micro-machining"),
    Rule("cnc.undercut", "access", "unreached_fraction", "max", ACCESS_TOLERANCE, "share",
         "share of the face no straight tool reaches from the machine's directions", "hubs-cnc",
         severity="warning", when=_MILLING, item_when={"kind": "undercut"},
         fix="open the face to a setup direction, or plan a T-slot or dovetail cutter, or more axes",
         note="undercuts need special cutters (T-slot, dovetail) and cost more"),
    Rule("cnc.no_line_of_sight", "access", "unreached_any_direction_fraction", "max", ACCESS_TOLERANCE, "share",
         "share of the face no straight line from outside reaches", "hubs-cnc", severity="warning", when=_MILLING,
         item_when={"kind": "no_line_of_sight"},
         fix="redesign so the face opens to the outside, or plan a lollipop/keyseat cutter or EDM",
         note="undercuts need special cutters"),
    Rule("cnc.enclosed_void", "voids", "volume_mm3", "max", 0.0, "mm3", "enclosed void", "hubs-cnc",
         fix="open the void to the outside or make the part in pieces: no tool reaches a closed cavity",
         note="a tool reaches only what it can enter"),
    Rule("cnc.setups", "setups", "setup_count", "max", 4, "setups", "setups", "hubs-cnc", severity="warning",
         when=_MILLING, fix="put the features on fewer sides: each setup is a refixturing",
         note="three or four setups are acceptable; more is excessive"),
    Rule("cnc.envelope_length", "stock", "length_mm", "max", 2032.0, "mm", "part length", "xometry-cnc",
         severity="warning", when=_MILLING, note="a large shop's largest milled part: 2032 x 1219 x 610 mm"),
    Rule("cnc.envelope_width", "stock", "width_mm", "max", 1219.0, "mm", "part width", "xometry-cnc",
         severity="warning", when=_MILLING),
    Rule("cnc.envelope_height", "stock", "height_mm", "max", 610.0, "mm", "part height", "xometry-cnc",
         severity="warning", when=_MILLING),
    Rule("cnc.turned_length", "turning", "length_mm", "max", 1575.0, "mm", "turned length", "xometry-cnc",
         severity="warning", when=_TURNING, note="a large shop's lathe: 1575 mm long, 813 mm diameter"),
    Rule("cnc.turned_diameter", "turning", "max_diameter_mm", "max", 813.0, "mm", "turned diameter",
         "xometry-cnc", severity="warning", when=_TURNING),
)

_HUBS_RULES = tuple(rule for rule in _GENERIC_RULES if rule.source == "hubs-cnc")

_PROTOLABS_ENVELOPE = {  # (length, width, height) of the largest part, per material and machine
    "plastic/3": (559.0, 356.0, 19.1), "aluminum/3": (559.0, 356.0, 95.3), "aluminum/5": (254.0, 178.0, 95.3),
    "hard/5": (254.0, 178.0, 44.45), "ss304/5": (107.95, 82.55, 95.25),
}
_PROTOLABS_RULES: tuple[Rule, ...] = (
    # without --tools, the tool its narrowest milled line is cut with (0.018 in. soft, 0.033 in. hard): its radius
    *_corner_rules("protolabs-milling", "an inside corner is left with the radius of the tool that cuts it",
                   radius={"soft": 0.2286, "hard": 0.4191}, by="line_class"),
    Rule("cnc.internal_corner_radius", "internal_corners", "radius_mm", "min", 0.5, "mm", "internal corner radius",
         "protolabs-milling", scale_by="min_tool_mm", when={**_MILLING, **_TOOLS}, item_when={"sharp": False},
         fix="radius the corner to at least {limit:g} mm, the smallest tool's radius",
         note="the resulting radii are the minimum allowable tool radius"),
    Rule("cnc.modelled_thread", "threads", "modelled", "max", 0, "threads", "modelled internal thread",
         "protolabs-turning", severity="warning", item_when={"internal": True},
         fix="model the tap drill's hole and call the thread out on the drawing",
         note="internal threads are best not modelled in the part"),
    Rule("cnc.milled_depth", "pockets", "depth_from_top_mm", "max", 50.8, "mm", "depth milled from one side",
         "protolabs-milling", when=_MILLING, fix="mill no deeper than {limit:g} mm from a side (2 in.)",
         note="maximum depth milled: 2 in. (50.8 mm) from either side"),
    Rule("cnc.part_thickness", "stock", "height_mm", "min", 1.02, "mm", "part thickness", "protolabs-milling",
         when=_MILLING, fix="make the part at least {limit:g} mm thick", note="a nominal thickness above 0.040 in."),
    Rule("cnc.wall_thickness", "walls", "thickness_mm", "min", 0.51, "mm", "feature thickness", "protolabs-milling",
         severity="warning", when=_MILLING, fix="thicken the feature to {limit:g} mm or more",
         note="features recommended thicker than 0.020 in. (0.51 mm)"),
    _knife_rule("protolabs-milling", 0.51, None, "features recommended thicker than 0.020 in. (0.51 mm)"),
    Rule("cnc.gap_width", "gaps", "width_mm", "min", {"soft": 0.457, "hard": 0.838}, "mm", "gap width",
         "protolabs-milling", by="hardness", when={**_MILLING, **_NO_TOOLS},
         fix="widen the gap to at least {limit:g} mm",
         note="the narrowest milled line (engraved text): 0.018 in. in plastics and soft metals, 0.033 in. in "
              "hard metals"),
    Rule("cnc.gap_width", "gaps", "width_mm", "min", 1.0, "mm", "gap width", "protolabs-milling",
         scale_by="min_tool_mm", when={**_MILLING, **_TOOLS}, fix="widen the gap to the smallest tool, {limit:g} mm"),
    Rule("cnc.envelope_length", "stock", "length_mm", "max", {k: v[0] for k, v in _PROTOLABS_ENVELOPE.items()},
         "mm", "part length", "protolabs-milling", by="envelope", when=_MILLING,
         note="maximum part size per material and machine (3-axis rows: two-sided machining only)"),
    Rule("cnc.envelope_width", "stock", "width_mm", "max", {k: v[1] for k, v in _PROTOLABS_ENVELOPE.items()},
         "mm", "part width", "protolabs-milling", by="envelope", when=_MILLING),
    Rule("cnc.envelope_height", "stock", "height_mm", "max", {k: v[2] for k, v in _PROTOLABS_ENVELOPE.items()},
         "mm", "part height", "protolabs-milling", by="envelope", when=_MILLING),
    # turning
    Rule("cnc.turned_diameter", "turning", "max_diameter_mm", "max", 100.33, "mm", "turned diameter",
         "protolabs-turning", when=_TURNING, note="maximum diameter 3.95 in."),
    Rule("cnc.turned_length", "turning", "length_mm", "max", 228.6, "mm", "turned length", "protolabs-turning",
         when=_TURNING, note="maximum length 9 in."),
    Rule("cnc.turned_feature_diameter", "turned_diameters", "diameter_mm", "min", 0.76, "mm", "turned diameter",
         "protolabs-turning", when=_TURNING, note="no region's diameter under 0.030 in."),
    Rule("cnc.turned_feature_diameter_small", "turned_diameters", "diameter_mm", "min", 4.07, "mm",
         "turned diameter", "protolabs-turning", severity="warning", when=_TURNING,
         note="the table's minimum feature diameter, 0.16 in."),
    Rule("cnc.turned_feature_length", "turned_diameters", "length_mm", "min", 1.27, "mm", "turned feature length",
         "protolabs-turning", when=_TURNING, note="minimum feature length 0.05 in."),
    Rule("cnc.turned_wall", "walls", "thickness_mm", "min", 0.51, "mm", "wall thickness", "protolabs-turning",
         when=_TURNING, note="walls under 0.020 in. typically do not survive machining"),
    Rule("cnc.axial_hole_diameter", "holes", "diameter_mm", "min", 1.0, "mm", "axial hole diameter",
         "protolabs-turning", when=_TURNING, item_when={"relation": "axial"}),
    Rule("cnc.radial_hole_diameter", "holes", "diameter_mm", "min", {"al_brass": 1.0, "other": 2.0}, "mm",
         "radial hole diameter", "protolabs-turning", by="lathe_material", when=_TURNING,
         item_when={"relation": "radial"}, note="2 mm, or 1 mm in aluminum and brass"),
    Rule("cnc.off_axis_hole", "holes", "diameter_mm", "max", {"other": 0.0}, "mm",
         "off-axis hole on a turned part", "protolabs-turning", by="lathe_material", when=_TURNING,
         item_when={"relation": "off_axis"}, fix="make the hole axial or radial, or the part aluminum or brass",
         note="odd-angle holes only in aluminum and brass"),
    Rule("cnc.groove_width", "grooves", "width_mm", "min", {"al_brass": 0.5, "other": 1.2}, "mm",
         "outside groove width", "protolabs-turning", by="lathe_material", when=_TURNING,
         item_when={"internal": False}),
    Rule("cnc.groove_depth", "grooves", "depth_mm", "max", 24.1, "mm", "outside groove depth", "protolabs-turning",
         when=_TURNING, item_when={"internal": False}),
    Rule("cnc.internal_groove", "grooves", "width_mm", "max", 0.0, "mm", "internal groove", "protolabs-turning",
         when=_TURNING, item_when={"internal": True}, fix="internal (ID) grooves are not offered: remove it",
         note="ID grooves are not supported"),
)

_XOMETRY_RULES: tuple[Rule, ...] = (
    *_corner_rules("xometry-tips", "round end mills cannot cut a sharp internal corner"),
    Rule("cnc.internal_corner_radius", "internal_corners", "radius_mm", "min", 0.65, "mm", "internal corner radius",
         "xometry-tips", severity="warning", scale_by="min_tool_mm", when={**_MILLING, **_TOOLS},
         item_when={"sharp": False}, fix="radius the corner to {limit:g} mm: 130% of the smallest tool's radius",
         note="add a radius of 130% of the milling tool's radius"),
    Rule("cnc.internal_corner_radius", "internal_corners", "radius_mm", "min", 1.625, "mm",
         "internal corner radius", "xometry-tips", severity="warning", when={**_MILLING, **_NO_TOOLS},
         item_when={"sharp": False}, fix="radius the corner to {limit:g} mm: 130% of a 2.5 mm tool's radius",
         note="130% of the tool radius; the smallest standard tool is 2.5 mm"),
    Rule("cnc.pocket_depth_to_width", "pockets", "depth_to_width", "max", 3.0, "ratio", "cavity depth to width",
         "xometry-tips", severity="warning", when=_MILLING, note="cavity depth should not exceed 3 to 5 times "
                                                                  "its width: the lower bound"),
    Rule("cnc.wall_thickness", "walls", "thickness_mm", "min", 0.5, "mm", "feature thickness", "xometry-cnc",
         fix="thicken the feature to at least {limit:g} mm", note="minimum feature size 0.020 in. (0.50 mm)"),
    _knife_rule("xometry-cnc", 0.5, None, "minimum feature size 0.020 in. (0.50 mm)"),
    Rule("cnc.wall_thickness_recommended", "walls", "thickness_mm", "min", {"metal": 0.794, "plastic": 1.5}, "mm",
         "wall thickness", "xometry-tips", severity="warning", by="wall_class",
         note="standard minimum walls: 0.794 mm metal, 1.5 mm plastic"),
    Rule("cnc.hole_depth", "holes", "depth_to_diameter", "max", 4.0, "ratio", "hole depth to diameter",
         "xometry-tips", severity="warning", note="limit hole depth to 4 diameters"),
    Rule("cnc.hole_depth_limit", "holes", "depth_to_diameter", "max", 10.0, "ratio", "hole depth to diameter",
         "xometry-tips", note="up to 10 diameters is possible, at a cost"),
    Rule("cnc.gap_width", "gaps", "width_mm", "min", 1.0, "mm", "gap width", "xometry-tips", scale_by="min_tool_mm",
         when={**_MILLING, **_TOOLS}, fix="widen the gap to the smallest tool, {limit:g} mm"),
    Rule("cnc.gap_width_small", "gaps", "width_mm", "min", 2.5, "mm", "gap width", "xometry-tips",
         severity="warning", when=_MILLING, note="the smallest standard tool is 2.5 mm; smaller needs special tools"),
    Rule("cnc.envelope_length", "stock", "length_mm", "max", 2032.0, "mm", "part length", "xometry-cnc",
         when=_MILLING, note="largest milled part 80 x 48 x 24 in."),
    Rule("cnc.envelope_width", "stock", "width_mm", "max", 1219.0, "mm", "part width", "xometry-cnc", when=_MILLING),
    Rule("cnc.envelope_height", "stock", "height_mm", "max", 610.0, "mm", "part height", "xometry-cnc",
         when=_MILLING),
    Rule("cnc.turned_length", "turning", "length_mm", "max", 1575.0, "mm", "turned length", "xometry-cnc",
         when=_TURNING, note="largest lathe part 62 in. long"),
    Rule("cnc.turned_diameter", "turning", "max_diameter_mm", "max", 813.0, "mm", "turned diameter", "xometry-cnc",
         when=_TURNING, note="largest lathe part 32 in. in diameter"),
)

def _detailed(rules: tuple[Rule, ...]) -> tuple[Rule, ...]:
    """Every wall and gap rule says the face across and the thinnest point."""
    return tuple(dataclasses.replace(rule, detail=_ACROSS_DETAIL[rule.family])
                 if rule.family in _ACROSS_DETAIL and not rule.detail else rule for rule in rules)


_GENERIC_RULES, _HUBS_RULES = _detailed(_GENERIC_RULES), _detailed(_HUBS_RULES)
_PROTOLABS_RULES, _XOMETRY_RULES = _detailed(_PROTOLABS_RULES), _detailed(_XOMETRY_RULES)

_NOTE = "a starting point drawn from published guides (mostly Protolabs Network's), no shop's limits"
RULE_SETS: dict[str, RuleSet] = {
    "generic": RuleSet("generic", "cnc", "text-to-cad generic", _ACCESSED, _GENERIC_RULES, (HUBS, XOMETRY_SERVICE),
                       generic=True, note=_NOTE),
    "hubs": RuleSet("hubs", "cnc", "Protolabs Network (Hubs)", _ACCESSED, _HUBS_RULES, (HUBS,),
                    note="its CNC design guide's recommended and feasible values"),
    "protolabs": RuleSet("protolabs", "cnc", "Protolabs", _ACCESSED, _PROTOLABS_RULES,
                         (PROTOLABS_MILLING, PROTOLABS_TURNING),
                         note="its milling and turning guidelines; corner radii follow --tools (it gives none)"),
    "xometry": RuleSet("xometry", "cnc", "Xometry", _ACCESSED, _XOMETRY_RULES, (XOMETRY_TIPS, XOMETRY_SERVICE),
                       note="its CNC design tips and its service's size limits"),
}


def tools(text: str | None) -> tuple[float, ...] | None:
    """``3,6,10``: end mill diameters in millimetres, smallest first; None for none given."""
    if text is None:
        return None
    try:
        values = tuple(sorted(float(part) for part in str(text).split(",") if part.strip()))
    except ValueError:
        values = ()
    if not values or not all(value > 0 for value in values):
        raise ValueError(f"--tools is end mill diameters in millimetres, comma separated (3,6,10), not {text!r}")
    return values


def stock(text: str | None) -> tuple[float, float, float] | None:
    """``100x60x25``: the stock's size in millimetres; None for the part's box."""
    if text is None:
        return None
    parts = [part for part in str(text).replace("x", ",").replace("X", ",").split(",") if part.strip()]
    try:
        values = tuple(float(part) for part in parts)
    except ValueError:
        values = ()
    if len(values) != 3 or not all(value > 0 for value in values):
        raise ValueError(f"--stock is three lengths in millimetres, X x Y x Z (100x60x25), not {text!r}")
    return values  # type: ignore[return-value]


def validate(resolved: dict[str, Any], document_type: str) -> None:
    if int(resolved["axes"]) not in (3, 4, 5):
        raise ValueError(f"--axes is 3, 4 or 5, not {resolved['axes']}")
    tools(resolved.get("tools"))
    stock(resolved.get("stock"))


_SOFT = ("aluminum", "brass", "copper")
_HARD = ("steel", "stainless", "titanium", "galvanized")


def _envelope(raw: str | None, material: str | None, material_class: str | None, axes: int) -> str | None:
    if material is None:
        return None
    if raw and raw.strip().lower().replace(" ", "_") in ("304", "ss304", "stainless_304"):
        group = "ss304"
    elif material_class == "plastic":
        group = "plastic"
    elif material == "aluminum":
        group = "aluminum"
    elif material in ("steel", "titanium", "brass", "copper") or (material == "stainless"):
        group = "hard"
    else:
        return None
    return f"{group}/{axes}"


def context(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    material = materials.resolve(resolved.get("material"))
    material_class = materials.material_class(material)
    given = tools(resolved.get("tools"))
    axes = int(resolved["axes"])
    return {"material": material, "material_class": material_class, "axes": axes,
            "turning": bool(resolved.get("turning")), "tools_given": given is not None,
            "min_tool_mm": min(given) if given else None,
            # walls are judged by the material's class; with none given, by a metal's (the laxer) limits
            "wall_class": material_class or "metal",
            "hardness": ("soft" if material_class == "plastic" or material in _SOFT else
                         "hard" if material in _HARD else None),
            # the narrowest tool by hardness; with no material, the soft (laxer) one
            "line_class": "hard" if material in _HARD else "soft",
            "envelope": _envelope(resolved.get("material"), material, material_class, axes),
            "lathe_material": "al_brass" if material in ("aluminum", "brass") else "other"}


def _items(report: dict[str, Any], family: str) -> list[dict[str, Any]]:
    found = report.get(family)
    return list(found.get("items") or []) if isinstance(found, dict) else []


def findings(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> list[CheckFinding]:
    found: list[CheckFinding] = []
    for item in _items(report, "stock"):
        if item.get("stock_given") and not item.get("fits_stock"):
            found.append(CheckFinding(
                "error", "cnc.stock_too_small",
                f"{item['part']} ({' x '.join(mm(v) for v in item['size_mm'])} mm) does not fit the stock "
                f"({' x '.join(mm(v) for v in item['stock_mm'])} mm)", item.get("location"),
                "give a larger --stock"))
    if resolved.get("material") is None:
        found.append(CheckFinding("info", "cnc.material_assumed",
                                  "no --material: walls are judged by a metal's limits, the laxer ones", "walls",
                                  "give --material (aluminum, steel, abs, ...)"))
    if resolved.get("turning"):
        for item in _items(report, "turning"):
            if item.get("axis") is None:
                found.append(CheckFinding("error", "cnc.no_turning_axis",
                                          f"{item.get('part')}: no axis of revolution found: not a turned part",
                                          item.get("location"), "check it for milling (no --turning)"))
            elif (item.get("axisymmetric_fraction") or 0) < 0.5:
                found.append(CheckFinding(
                    "warning", "cnc.mostly_not_turned",
                    f"{item.get('part')}: only {100 * item['axisymmetric_fraction']:.0f}% of its area turns about "
                    f"its axis", item.get("location"), "mill it, or turn the round part and mill the rest"))
        for item in _items(report, "live_tooling")[:20]:
            found.append(CheckFinding("info", "cnc.live_tooling",
                                      f"{item['kind']} off the turning axis: live tooling or a milling setup",
                                      item.get("location")))
    else:
        for item in _items(report, "setups"):
            if item.get("rotary_axis"):
                found.append(CheckFinding("info", "cnc.rotary_axis",
                                          f"{item['part']}: the rotary axis taken is {item['rotary_axis']}",
                                          item.get("location")))
    small = report.get("small_features") or {}
    if isinstance(small, dict) and (small.get("fine_faces") or 0) >= 20:
        found.append(CheckFinding("info", "cnc.fine_detail",
                                  f"{small['fine_faces']} faces are under 1 mm across: text, knurling or fine "
                                  f"detail, which takes micro tools or engraving", "small_features"))
    return found


def summary(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> str:
    bodies = report.get("bodies") or []
    head = "turning" if resolved.get("turning") else f"{resolved['axes']}-axis milling"
    setups = sum(item.get("setup_count") or 0 for item in _items(report, "setups"))
    counts = [f"{len(bodies)} part(s)", f"{mm(round(sum(body.get('volume_mm3') or 0 for body in bodies), 3))} mm3"]
    if setups and not resolved.get("turning"):
        counts.append(f"{setups} setup(s)")
    for family in ("holes", "pockets"):
        value = report.get(family)
        if isinstance(value, dict) and value.get("count"):
            counts.append(f"{value['count']} {family}")
    return f"{head}: {', '.join(counts)}"
