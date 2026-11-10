"""CNC machining, milling and turning: its options, rules, findings and summary (``cad._internal.dfm``).

Measured on exact geometry alone (a STEP, an xbf, a document the engine holds; ``cad.build123d._dfm_cnc``
says how): holes, pockets, internal corners, sharp concave edges no rotating tool makes, walls, gaps, tool
access and setups per approach direction, closed voids, stock, small features, and with ``turning`` the
axis, diameters, bores, grooves and live-tooling features (its own rules: the grooves, the part's slenderness
and size; the milling rules that do not apply there are said, ``cnc.turning_not_judged``).

The rules (``RULES``) are general practice. A number a published guide states cites it (Protolabs Network's
CNC design guide and its service's page: the evidence, not a shop's limit). A feasibility floor no guide states
is text-to-cad's own and says so, with its reason (``OWN``: its message reads ``source: text-to-cad``, never a
publisher's name). A warning is a recommendation, a cost or a risk; an error is a part no general shop makes as
drawn: a face no tool reaches, a tool that does not exist at that depth, a part beyond any general machine. A
limit that follows the tools given (``--tools``) is the smallest tool's; without ``--tools`` the floor is one
tool's for holes, slots and corners alike (``TOOL_FLOOR_MM``).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from cad._internal.refused import ArgumentRefused
from cad._internal.dfm import materials
from cad._internal.dfm._common import mm
from cad._internal.dfm.rules import Rule, RuleSet, Source
from cad.results import CheckFinding

__all__ = ["MEASURED_FROM", "OPTIONS", "RULES", "context", "findings", "summary", "validate"]

OPTIONS: dict[str, Any] = {"axes": 3, "turning": False, "tools": None, "stock": None}
MEASURED_FROM = ("brep",)

_ACCESSED = "2026-11-06"
#: The rules' own version (``RuleSet.version``), bumped when a rule changes.
_VERSION = "2026-11-09"
HUBS = Source("hubs-cnc", "Protolabs Network (Hubs)", "How to design parts for CNC machining",
              "https://www.hubs.com/knowledge-base/how-design-parts-cnc-machining/", _ACCESSED)
#: The same publisher's service page: the largest parts its network's machines take (read 2026-11-09).
HUBS_SERVICE = Source("hubs-cnc-service", "Protolabs Network (Hubs)", "CNC machining service: maximum part size",
                      "https://www.hubs.com/cnc-machining/", "2026-11-09")
#: text-to-cad's own feasibility floors: no publisher's figure. Each such rule's note gives its reason.
OWN = Source("text-to-cad", "text-to-cad", "its own figure, no publisher's", "", "2026-11-09")

#: Within this share of its area, a face a sample of which no direction reached is still reached: one
#: sampled point is a few percent of a small face, and a ray grazing an edge is no undercut.
ACCESS_TOLERANCE = 0.02

_MILLING = {"turning": False}
_TURNING = {"turning": True}
#: Pockets and their corners are judged on a milled part, and on a turned one for its live tooling's features
#: (the pockets a turned part reports are those alone).
_POCKETS: dict[str, Any] = {}
_NO_TOOLS = {"tools_given": False}
_TOOLS = {"tools_given": True}


#: Without ``--tools``, the radius a sharp corner or edge is told it is recommended to take: a 2.5 mm end mill's,
#: the smallest standard tool (Hubs: "Most machine shops can accurately machine cavities and holes using tools
#: down to 2.5 mm (0.1 inches) in diameter."). A recommendation: the hints say it, no error's limit is it.
_SMALL_TOOL_RADIUS = 1.25
#: Without ``--tools``, the smallest tool there is, for holes, slots and corners alike: the guide's small-features
#: table, minimum hole diameter "Feasible: 0.05 mm (0.005 inches)". It is the guide's figure for a hole, and
#: text-to-cad's own floor for a slot's width (no tool wider than the slot cuts it) and a corner's radius (half of
#: it), which the guide states no figure for: one tool, one floor.
TOOL_FLOOR_MM = 0.05
_FLOOR_NOTE = ("text-to-cad's own floor: the smallest tool the cited guide calls feasible, said there of a hole "
               '(Hubs, minimum hole diameter: "Feasible: 0.05 mm (0.005 inches)"), held for a slot and a corner '
               "too, which the guide gives no figure for")
#: Under this a tool is a micro tool (the guide's holes: "Feasible: any diameter larger than 1 mm"; its
#: small-features table goes on to 0.05 mm): a hole under it warns, and a micro end mill reaches ``MICRO_REACH``
#: diameters at most -- text-to-cad's own floor (long-neck micro end mills are catalogued to about ten diameters;
#: the guide's 30:1 is said of specialised tooling, its example a 1 inch end mill).
MICRO_TOOL_MM = 1.0
MICRO_REACH = 10.0
_MICRO_NOTE = ("text-to-cad's own floor: an end mill under 1 mm across (a micro tool) is made to reach about ten "
               "of its diameters; the guide's 30:1 is said of specialised tooling at full size")
#: What a failing item says of itself, appended to the message (``Rule.detail``).
#: ``{unreached}`` is empty, or where some tool reaches part of the edge, the stretch none reaches and its place
_CORNER_DETAIL = "{edge}, {height_mm:g} mm tall, {depth_mm:g} mm below the top{unreached}"
#: A round corner's: its own face (the finding is at its cavity's ref, which the cavity's corners share).
_ROUND_DETAIL = "the corner {corner}, {height_mm:g} mm tall"
_EDGE_DETAIL = "{edge} between {between}, a {void_angle_deg:.0f}-degree void, at {xyz}{unreached}"
_ACROSS_DETAIL = {"walls": "to {opposite} at {xyz}", "gaps": "to {opposite} at {xyz}"}


#: Why no tool of the machine makes a sharp concave edge (``sharp_edges`` items' ``reason``): the words of the
#: rule's message, and its fix.
_EDGE_REASONS = {
    "acute": ("sharp concave edge (void under 90 degrees)",
              "its {void_angle_deg:.0f}-degree void is under 90, so no tool's end or side reaches its root: open "
              "it to 90 degrees or more, round it to at least {limit:g} mm, or plan EDM"),
    "vertical_corner": ("sharp concave edge (a corner along a tool's axis)",
                        "a corner of a cavity cut along it, where the tool's side leaves its radius: give it a "
                        "radius of at least {limit:g} mm, or a dog-bone relief, or plan EDM"),
    "blocked": ("sharp concave edge (its square face blocked)",
                "a face is square to a machine direction but the way to the edge along it is blocked, so no "
                "tool's end reaches it: give it a radius of at least {limit:g} mm, open that way, or plan EDM"),
    "no_way_in": ("sharp concave edge (its disc cutter cannot get in)",
                  "a disc cutter reaches it from its shank, but its disc cannot get there -- wider than the bore "
                  "it would come down, or than any opening, with no side the recess opens to at its own level: "
                  "widen the way in, open the recess to a side, give it a radius of at least {limit:g} mm, or "
                  "plan EDM"),
    "no_square_face": ("sharp concave edge (no face square to a machine direction)",
                       "neither face at its {void_angle_deg:.0f}-degree void is a plane square to a machine "
                       "direction, so no tool's corner makes it sharp: round it to at least {limit:g} mm (a ball "
                       "end mill's radius), square one face to an approach direction, or give more axes"),
}
#: Sharp edges a tool makes, said as warnings (text-to-cad's own judgements, ``reason``): the words and the fix.
_EDGE_WARNINGS = {
    "narrow_opening": ("sharp concave edge (a slot cutter's opening narrower than its recess)",
                       "its slot cutter's way in is {opening_mm:g} mm wide where the recess is {recess_mm:g} mm "
                       "tall (the disc's thickness): a disc that thick on a shank that thin is a special, fragile "
                       "cutter -- widen the opening to the recess's height, or plan the cutter with the shop"),
    "obtuse_root": ("sharp concave edge (an obtuse root a side-milling tool rounds)",
                    "a tool side-milling the profile leaves its radius in this root; it is sharp only by facing "
                    "each side from its own direction, {more_setups} than the count: round it to at least "
                    "{limit:g} mm, or plan for that"),
}
#: A sharp edge a tool along a direction the machine lacks would make: the access warning's severity and words.
_OTHER_AXES = ("sharp concave edge (made along a direction this machine lacks)",
               "a tool along a direction this machine lacks makes it sharp: an angled setup or more axes "
               "(--axes 5), or round it to at least {limit:g} mm")


#: A corner along the tool's axis of ``BALL_VOID_DEG`` (150 degrees) or more is made by the tool's flank; the
#: radius it leaves in the corner is said as a warning past this (mm): text-to-cad's own figure, no guide's.
FLANK_RESIDUE_MM = 0.05


#: A sharp corner's hint where its cavity is narrower than twice the radius its depth asks.
_UNFIT_FIX = ("sharp vertical corner: no round tool makes it, and its {opening_mm:g} mm width takes a radius of "
              "{fits_mm:g} mm at most, under the third of the cavity's depth ({third_of_depth_mm:g} mm) recommended: "
              "{instead}; or round it to {fits_mm:g} mm at most with a long, small end mill")


def _corner_rules(source: str, sharp_note: str) -> tuple[Rule, ...]:
    """A sharp vertical corner and a sharp concave edge: no round tool makes either (the error); judged against
    half the smallest tool with ``--tools``, else half the tool floor (``TOOL_FLOOR_MM``, text-to-cad's own),
    the hint giving the radius recommended (``_SMALL_TOOL_RADIUS``, a 2.5 mm end mill's). An edge's message and
    fix follow its ``reason``; a sharp edge a tool along a direction the machine lacks would make is a warning
    (more axes make it), every other one an error. A corner is judged on a milled part and on a turned part's
    live-tooling features; a sharp edge on a milled part."""
    corner_fix = {
        "min_tool_mm": ("sharp vertical corner: no round tool makes it. Give it a radius of at least {limit:g} mm, "
                        "half the smallest tool (a third of the cavity's depth, {third_of_depth_mm:g} mm, or more "
                        "is recommended), or a dog-bone relief, or plan EDM"),
        None: ("sharp vertical corner: no round tool makes it. Give it a radius of 1.25 mm or more (recommended: a "
               "2.5 mm end mill's; a third of the cavity's depth, {third_of_depth_mm:g} mm, or more), or a "
               "dog-bone relief, or plan EDM"),
    }
    recommended = "1.25 mm or more (recommended: a 2.5 mm end mill's)"
    found: list[Rule] = []
    given = source
    for when, scale, limit, note, source in (
            ({**_TOOLS}, "min_tool_mm", 0.5,
             sharp_note + "; a tool cuts no radius under its own: half the smallest given", given),
            ({**_NO_TOOLS}, None, TOOL_FLOOR_MM / 2.0, sharp_note + " (Hubs); its least radius is " + _FLOOR_NOTE,
             "text-to-cad")):
        found.append(Rule("cnc.internal_corner_sharp", "internal_corners", "radius_mm", "min", limit, "mm",
                          "sharp vertical corner (no round tool makes it): radius", source, scale_by=scale, when={**_POCKETS, **when},
                          item_when={"sharp": True, "radius_fits": (True, None)}, fix=corner_fix[scale], note=note,
                          detail=_CORNER_DETAIL))
        # a cavity too narrow for the radius its depth asks: the hint names how such a corner is made instead
        found.append(Rule("cnc.internal_corner_sharp", "internal_corners", "radius_mm", "min", limit, "mm",
                          "sharp vertical corner (no round tool makes it): radius", source, scale_by=scale, when={**_POCKETS, **when},
                          item_when={"sharp": True, "radius_fits": False}, fix=_UNFIT_FIX, note=note,
                          detail=_CORNER_DETAIL))
        for reason, (what, fix) in _EDGE_REASONS.items():
            fix = fix.replace("at least {limit:g} mm", "at least {limit:g} mm" if scale else recommended)
            found.append(Rule("cnc.sharp_internal_edge", "sharp_edges", "radius_mm", "min", limit, "mm",
                              what + " radius", source, scale_by=scale, when={**_MILLING, **when},
                              item_when={"reason": reason}, fix=fix, note=note, detail=_EDGE_DETAIL))
        for reason, (what, fix) in _EDGE_WARNINGS.items():
            found.append(Rule("cnc.sharp_internal_edge", "sharp_edges", "radius_mm", "min", limit, "mm",
                              what + " radius", source, severity="warning", scale_by=scale,
                              when={**_MILLING, **when}, item_when={"reason": reason},
                              fix=fix.replace("at least {limit:g} mm", "at least {limit:g} mm" if scale else recommended),
                              note=note, detail=_EDGE_DETAIL))
        found.append(Rule("cnc.sharp_internal_edge", "sharp_edges", "radius_mm", "min", limit, "mm",
                          _OTHER_AXES[0] + " radius", source, severity="warning", scale_by=scale,
                          when={**_MILLING, **when}, item_when={"reason": "other_axes"},
                          fix=_OTHER_AXES[1].replace("at least {limit:g} mm",
                                                     "at least {limit:g} mm" if scale else recommended),
                          note=note, detail=_EDGE_DETAIL))
    found.append(Rule("cnc.internal_corner_radius", "internal_corners", "radius_mm", "min", 0.5, "mm",
                      "internal corner radius", given, scale_by="min_tool_mm", when={**_POCKETS, **_TOOLS},
                      item_when={"sharp": False},
                      fix="radius the corner to at least {limit:g} mm, the smallest tool's radius, or add a smaller "
                          "tool", note="a corner tighter than the smallest end mill's radius is not cut by it",
                      detail=_ROUND_DETAIL))
    return tuple(found)


def _inclined_rules(source: str, note: str) -> tuple[Rule, ...]:
    """A pocket or hole along no direction the machine has: its own setup, an angled one, or more axes. Five
    axes reach every direction (not applicable); on four, the features square to the rotary axis pass."""
    return tuple(Rule("cnc.inclined_feature", family, "inclination_deg", "max", 0.0, "deg",
                      f"{noun} axis off the machine's directions", source, severity="warning",
                      when={**_MILLING, "axes": (3, 4)}, item_when={"reachable": False},
                      fix=f"an inclined {noun}: its axis is along none of the machine's directions in the part's own "
                          "frame (the one its faces and holes square: machine.frames) -- an angled fixture (its own "
                          f"setup), or 4 or 5 axes, or align the {noun} with the part's faces", note=note)
                 for family, noun in (("pockets", "pocket"), ("holes", "hole")))


def _knife_rule(source: str, limit: Any, by: str | None, note: str) -> Rule:
    return Rule("cnc.knife_edge", "knife_edges", "thickness_mm", "min", limit, "mm",
                "material at a knife edge (a convex edge under 45 deg)", source, severity="warning", by=by,
                fix="blunt it -- a flat or round at least {limit:g} mm across -- or open its angle to 45 deg or more",
                note=note)


_RULES: tuple[Rule, ...] = (
    *_corner_rules("hubs-cnc", "every CNC tool is round, so an internal vertical edge always has a radius"),
    Rule("cnc.internal_corner_radius", "internal_corners", "radius_mm", "min", TOOL_FLOOR_MM / 2.0, "mm",
         "internal corner radius", "text-to-cad", when={**_POCKETS, **_NO_TOOLS}, item_when={"sharp": False},
         fix="radius the corner to at least {limit:g} mm (no tool is smaller); 1.25 mm or more is recommended",
         note=_FLOOR_NOTE, detail=_ROUND_DETAIL),
    Rule("cnc.internal_corner_small", "internal_corners", "radius_mm", "min", 1.25, "mm",
         "internal corner radius", "hubs-cnc", severity="warning", when={**_POCKETS, **_NO_TOOLS},
         item_when={"sharp": False}, fix="radius the corner to {limit:g} mm or more, so a 2.5 mm end mill cuts it",
         detail=_ROUND_DETAIL,
         note='"Most machine shops can accurately machine cavities and holes using tools down to 2.5 mm (0.1 '
              'inches) in diameter. Anything below this limit is considered micro-machining."'),
    Rule("cnc.corner_radius_to_depth", "internal_corners", "radius_to_depth", "min", 1.0 / 3.0, "ratio",
         "corner radius to cavity depth", "hubs-cnc", severity="warning", when=_POCKETS,
         item_when={"sharp": False, "radius_fits": (True, None)}, detail=_ROUND_DETAIL,
         fix="make the corner radius {third_of_depth_mm:g} mm or more, a third of the cavity's {height_mm:g} mm depth",
         note='vertical corner radius "Recommended: ⅓ times cavity depth (or larger)"'),
    Rule("cnc.corner_radius_to_depth", "internal_corners", "radius_to_depth", "min", 1.0 / 3.0, "ratio",
         "corner radius to cavity depth", "hubs-cnc", severity="warning", when=_POCKETS,
         item_when={"sharp": False, "radius_fits": False}, detail=_ROUND_DETAIL,
         fix="a third of the cavity's {height_mm:g} mm depth ({third_of_depth_mm:g} mm) does not fit its "
             "{opening_mm:g} mm width: round the corner to {fits_mm:g} mm at most, or {instead}",
         note='vertical corner radius "Recommended: ⅓ times cavity depth (or larger)"'),
    Rule("cnc.corner_reach", "internal_corners", "reach_ratio", "max", 4.0, "ratio",
         "depth to the diameter of the largest tool that fits the corner", "hubs-cnc", severity="warning",
         when=_POCKETS, fix="a larger corner radius or a shallower cavity: end mills cut 3 to 4 diameters deep",
         note="end mills typically cut to 3-4 times their diameter", detail=_ROUND_DETAIL),
    Rule("cnc.corner_reach_limit", "internal_corners", "reach_ratio", "max", 30.0, "ratio",
         "depth to the diameter of the largest tool that fits the corner", "hubs-cnc", when=_POCKETS,
         item_when={"micro_tool": False}, detail=_ROUND_DETAIL,
         fix="a larger corner radius or a shallower cavity: 30 diameters is the deepest even special tooling reaches",
         note="up to 30:1 depth to tool diameter with specialized tooling"),
    Rule("cnc.corner_reach_limit", "internal_corners", "reach_ratio", "max", MICRO_REACH, "ratio",
         "depth to the diameter of the largest tool that fits the corner (a micro tool, under 1 mm)",
         "text-to-cad", when=_POCKETS, item_when={"micro_tool": True},
         fix="no {tool_mm:g} mm tool reaches {depth_mm:g} mm: a larger corner radius (0.5 mm takes a 1 mm tool) or "
             "a shallower cavity, or plan EDM", note=_MICRO_NOTE, detail=_ROUND_DETAIL),
    Rule("cnc.pocket_depth_to_width", "pockets", "depth_to_width", "max", 4.0, "ratio",
         "cavity depth to width", "hubs-cnc", severity="warning", when=_POCKETS,
         fix="make the cavity no deeper than {limit:g} times its width", note="recommended cavity depth: 4x width"),
    Rule("cnc.pocket_depth_limit", "pockets", "depth_to_width", "max", MICRO_REACH, "ratio",
         "cavity depth to width (under 1 mm wide: a micro tool's)", "text-to-cad", when=_POCKETS,
         item_when={"micro_tool": True},
         fix="no tool that fits the {width_mm:g} mm cavity reaches {depth_mm:g} mm: widen it to 1 mm or more, make "
             "it shallower, or plan wire or sinker EDM", note=_MICRO_NOTE),
    Rule("cnc.pocket_depth_limit", "pockets", "depth_to_width", "max", 30.0, "ratio",
         "cavity depth to width", "hubs-cnc", when=_POCKETS, item_when={"micro_tool": False},
         fix="no tool that fits the cavity's width reaches {value:.3g} widths deep: widen it or make it shallower "
             "(30 at most), or plan wire or sinker EDM",
         note='"A tool diameter-to-cavity depth ratio of up to 30:1 is possible using specialized tooling"; a '
              "cavity takes no tool wider than itself, so its depth is at most 30 of its widths (the guide's "
              "figure, text-to-cad's reading of it for a width)"),
    # a thin feature that stands tall: no guide's figure and no hard limit, so a warning at any height
    Rule("cnc.tall_feature", "walls", "height_to_thickness", "max", 4.0, "ratio",
         "height to thickness of a thin standing feature", "text-to-cad",
         severity="warning", item_when={"standing": True},
         fix="it stands {height_mm:g} mm on {thickness_mm:g} mm: shorten it, thicken it, or support it (a rib, a "
             "web to a neighbour); a tall thin feature chatters and bends under the cutter",
         note="text-to-cad's own figure, a rule of thumb (four times the thickness): a taller thin feature is "
              "made, slower and less true -- no hard limit exists, so this is never an error"),
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
    *_inclined_rules("hubs-cnc", "align every feature (holes, cavities, vertical walls) to one of the six "
                                 "principal directions; if that is not possible, 5-axis machining is an option"),
    Rule("cnc.hole_diameter", "holes", "diameter_mm", "min", TOOL_FLOOR_MM, "mm", "hole diameter", "hubs-cnc",
         fix="make the hole at least {limit:g} mm; 1 mm or more is no micro drill's",
         note='minimum hole diameter "Feasible: 0.05 mm (0.005 inches)"'),
    Rule("cnc.hole_diameter_small", "holes", "diameter_mm", "min", MICRO_TOOL_MM, "mm", "hole diameter",
         "hubs-cnc", severity="warning", fix="make the hole {limit:g} mm or more: a smaller one is micro-drilled",
         note='holes, diameter: "Feasible: any diameter larger than 1 mm"; under it the small-features table '
              'applies ("Feasible: 0.05 mm"), micro-machining'),
    Rule("cnc.hole_depth", "holes", "depth_to_diameter", "max", 4.0, "ratio", "hole depth to diameter",
         "hubs-cnc", severity="warning", fix="limit the depth to {limit:g} diameters, or widen the hole",
         note="recommended hole depth: 4x the nominal diameter"),
    Rule("cnc.hole_depth_limit", "holes", "depth_to_diameter", "max", 40.0, "ratio", "hole depth to diameter",
         "hubs-cnc", fix="no drill reaches {value:.3g} diameters: shorten or widen the hole",
         note="feasible maximum hole depth: 40x the diameter"),
    # a counterbore (a stepped bore's larger step) is cut as a hole of its own diameter, to its own depth
    Rule("cnc.hole_depth", "counterbores", "depth_to_diameter", "max", 4.0, "ratio", "counterbore depth to diameter",
         "hubs-cnc", severity="warning", fix="limit the counterbore's depth to {limit:g} diameters, or widen it",
         note="recommended hole depth: 4x the nominal diameter", detail="the counterbore of the hole at {hole}"),
    Rule("cnc.hole_depth_limit", "counterbores", "depth_to_diameter", "max", 40.0, "ratio",
         "counterbore depth to diameter", "hubs-cnc", fix="no tool reaches {value:.3g} diameters: shorten or widen "
         "the counterbore", note="feasible maximum hole depth: 40x the diameter", detail="the counterbore of the "
         "hole at {hole}"),
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
    Rule("cnc.gap_width", "gaps", "width_mm", "min", TOOL_FLOOR_MM, "mm", "gap width", "text-to-cad",
         when={**_MILLING, **_NO_TOOLS},
         fix="widen the gap to at least {limit:g} mm; 2.5 mm or more is recommended",
         note=_FLOOR_NOTE + "; a gap takes no tool wider than itself"),
    Rule("cnc.gap_width", "gaps", "width_mm", "min", 1.0, "mm", "gap width", "hubs-cnc", scale_by="min_tool_mm",
         when={**_MILLING, **_TOOLS}, item_when={"made_by": "end_mill"},
         fix="widen the gap to at least {limit:g} mm, the smallest tool's diameter",
         note="a tool cuts no gap narrower than itself"),
    # a recess's floor-to-ceiling height is a slot cutter's thickness to cut, not an end mill's diameter
    Rule("cnc.gap_width", "gaps", "width_mm", "min", TOOL_FLOOR_MM, "mm", "recess height (a slot cutter's)",
         "text-to-cad", when={**_MILLING, **_TOOLS}, item_when={"made_by": "slot_cutter"},
         fix="open the recess to at least {limit:g} mm; a standard slot cutter's width (3 to 40 mm) is cheaper",
         note=_FLOOR_NOTE + "; a slot cutter, not an end mill given, cuts a recess's height"),
    Rule("cnc.gap_width_small", "gaps", "width_mm", "min", 2.5, "mm", "gap width", "hubs-cnc", severity="warning",
         when={**_MILLING, **_NO_TOOLS}, fix="widen the gap to {limit:g} mm or more",
         note="features under 2.5 mm are micro-machining"),
    Rule("cnc.undercut", "access", "unreached_fraction", "max", ACCESS_TOLERANCE, "share",
         "share of the face no straight tool reaches from the machine's directions", "hubs-cnc",
         severity="warning", when=_MILLING, item_when={"kind": "undercut", "hole": False, "part_of": None},
         fix="open the face to a setup direction, or plan a T-slot or dovetail cutter, or more axes",
         note="undercuts need special cutters (T-slot, dovetail) and cost more"),
    Rule("cnc.undercut", "access", "unreached_fraction", "max", ACCESS_TOLERANCE, "share",
         "share of the hole's face no straight tool reaches from the machine's directions", "hubs-cnc",
         severity="warning", when=_MILLING, item_when={"kind": "undercut", "hole": True, "part_of": None},
         fix="the hole (axis {hole_axis}) is not reached along its axis from outside: open its way, drill it from "
             "the other end, or plan an angled setup or more axes", note="a drill comes in along the hole's axis"),
    Rule("cnc.special_cutter", "access", "edge_count", "max", 0, "edges", "edges only a special cutter makes",
         "hubs-cnc", severity="warning", when=_MILLING, item_when={"kind": "special_cutter"},
         fix="a {cutter} cuts it: {advice}", detail="the recess's faces no straight tool reaches: {also}",
         note="undercuts (T-slots and dovetails) are machined using special tools; their width can vary between "
              "3 mm and 40 mm"),
    # no straight line from outside reaches the face, on a mill or a lathe: it is made only where a disc
    # cutter on a straight shank (a keyseat cutter, a lollipop, a lathe's grooving bar) gets in to it
    Rule("cnc.no_line_of_sight", "access", "no_tool_fraction", "max", ACCESS_TOLERANCE, "share",
         "share of the face no tool reaches", "text-to-cad",
         item_when={"kind": "no_line_of_sight", "part_of": None},
         fix="no straight line from outside reaches it and no disc cutter that fits its way in does: open the "
             "recess to the outside, widen its way in to the disc that reaches it (twice the recess's depth past "
             "the opening), or make the part in pieces or plan EDM",
         detail="{face_count} adjoining face(s): {faces_said}",
         note="text-to-cad's own floor, by geometry: a tool is straight, and a disc on a shank reaches no "
              "further past an opening than the disc that opening lets in"),
    Rule("cnc.undercut", "access", "unreached_any_direction_fraction", "max", ACCESS_TOLERANCE, "share",
         "share of the face no straight tool reaches (a disc cutter through its opening does)", "hubs-cnc",
         severity="warning", when=_MILLING,
         item_when={"kind": "no_line_of_sight", "disc_reach": True, "part_of": None},
         fix="only a keyseat or lollipop cutter through its opening makes it: plan that cutter, or open the "
             "face to a setup direction", detail="{face_count} adjoining face(s): {faces_said}",
         note="undercuts need special cutters (T-slot, dovetail) and cost more"),
    Rule("cnc.enclosed_void", "voids", "volume_mm3", "max", 0.0, "mm3", "enclosed void", "hubs-cnc",
         fix="open the void to the outside or make the part in pieces: no tool reaches a closed cavity",
         note="a tool reaches only what it can enter"),
    Rule("cnc.setups", "setups", "setup_count", "max", 5, "setups", "setups", "hubs-cnc", severity="warning",
         when=_MILLING, fix="put the features on fewer sides: each setup is a refixturing",
         note='"This is often acceptable if the part needs to be rotated up to three or four times, but anything '
              'above this limit is excessive." Four rotations are five clampings'),
    # the part's size: the largest a named network's machines take (a warning: fewer shops), and far past any
    # general machine (an error, text-to-cad's own floor)
    Rule("cnc.part_size", "stock", "length_mm", "max", 2000.0, "mm", "the part's longest side",
         "hubs-cnc-service", severity="warning", when=_MILLING,
         fix="few shops mill a part over {limit:g} mm long: split it, or name the shop and its machine",
         note='maximum part size, "3-axis CNC milling (soft metals)": "2000 x 1500 x 200 mm" (hard metals: "1200 '
              'x 800 x 500 mm"): one network\'s machines, read as where the general ones end'),
    Rule("cnc.part_size_limit", "stock", "length_mm", "max", 4000.0, "mm", "the part's longest side",
         "text-to-cad", when=_MILLING,
         fix="no general shop's mill takes a part {value:.5g} mm long: make it in pieces, or check the model's units",
         note="text-to-cad's own floor: twice the longest part the cited network's mills take (2000 mm); a "
              "gantry mill longer than that is a specialist's, named with its shop"),
    Rule("cnc.part_size", "turning", "max_diameter_mm", "max", 431.0, "mm", "the turned part's largest diameter",
         "hubs-cnc-service", severity="warning", when=_TURNING,
         fix="few lathes swing over {limit:g} mm: reduce the diameter, mill it, or name the shop and its lathe",
         note='maximum part size, "CNC turning (lathe)": "Ø431 x 990 mm"'),
    Rule("cnc.part_size", "turning", "length_mm", "max", 990.0, "mm", "the turned part's length",
         "hubs-cnc-service", severity="warning", when=_TURNING,
         fix="few lathes turn over {limit:g} mm between centres: shorten it, or name the shop and its lathe",
         note='maximum part size, "CNC turning (lathe)": "Ø431 x 990 mm"'),
    Rule("cnc.part_size_limit", "turning", "max_diameter_mm", "max", 1000.0, "mm",
         "the turned part's largest diameter", "text-to-cad", when=_TURNING,
         fix="no general shop's lathe swings {value:.5g} mm: mill it, make it in pieces, or check the model's units",
         note="text-to-cad's own floor: over twice the diameter the cited network's lathes take (431 mm)"),
    Rule("cnc.part_size_limit", "turning", "length_mm", "max", 4000.0, "mm", "the turned part's length",
         "text-to-cad", when=_TURNING,
         fix="no general shop's lathe holds a part {value:.5g} mm long: make it in pieces, or check the model's units",
         note="text-to-cad's own floor: four times the length the cited network's lathes take (990 mm)"),
    # turning's own: what its measurements (turning, grooves) are judged by
    Rule("cnc.turned_slenderness", "turning", "length_to_diameter", "max", 10.0, "ratio",
         "the turned part's length to its largest diameter", "text-to-cad", severity="warning", when=_TURNING,
         fix="a part {value:.3g} diameters long bends away from the tool: shorten or thicken it, or plan a "
             "tailstock and a steady rest, or a sliding-head (Swiss) lathe",
         note="text-to-cad's own figure, a rule of thumb: past about ten diameters a turned part needs a steady "
              "rest or a sliding-head lathe -- made either way, so never an error"),
    Rule("cnc.groove_depth_limit", "grooves", "depth_to_entry", "max", 0.5, "ratio",
         "internal groove depth to the diameter of the bore its tool enters by", "text-to-cad", when=_TURNING,
         item_when={"internal": True},
         fix="no grooving tool that enters the {entry_diameter_mm:g} mm bore reaches {depth_mm:g} mm past its "
             "wall: make the groove shallower (half the bore's diameter at most), widen the bore, or open the "
             "groove to an end",
         note="text-to-cad's own floor, by geometry: a tool that passes the bore is no wider than it, and reaches "
              "past the bore's wall by less than its own width less its bar's -- half the bore at the very most"),
    Rule("cnc.groove_depth", "grooves", "depth_to_width", "max", 5.0, "ratio", "groove depth to width",
         "text-to-cad", severity="warning", when=_TURNING,
         fix="a groove {value:.3g} times deeper than it is wide takes a long, thin grooving blade: widen it or "
             "make it shallower",
         note="text-to-cad's own figure, a rule of thumb for a grooving insert's reach (five of its widths); a "
              "parting blade goes deeper, slower -- never an error"),
)

def _detailed(rules: tuple[Rule, ...]) -> tuple[Rule, ...]:
    """Every wall and gap rule says the face across and the thinnest point."""
    return tuple(dataclasses.replace(rule, detail=_ACROSS_DETAIL[rule.family])
                 if rule.family in _ACROSS_DETAIL and not rule.detail else rule for rule in rules)


_NOTE = ("general practice: a published CNC design guide's numbers (Protolabs Network's) where it states one, "
         "text-to-cad's own feasibility floors where none does (each says so); no shop's limits: compare the "
         "measurements with a shop's own")
RULES = RuleSet("cnc", "text-to-cad general rules", _VERSION, _detailed(_RULES), (HUBS, HUBS_SERVICE, OWN), note=_NOTE)


def tools(text: str | None) -> tuple[float, ...] | None:
    """``3,6,10``: end mill diameters in millimetres, smallest first; None for none given."""
    if text is None:
        return None
    try:
        values = tuple(sorted(float(part) for part in str(text).split(",") if part.strip()))
    except ValueError:
        values = ()
    if not values or not all(value > 0 for value in values):
        raise ArgumentRefused(f"--tools is end mill diameters in millimetres, comma separated (3,6,10), not {text!r}")
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
        raise ArgumentRefused(f"--stock is three lengths in millimetres, X x Y x Z (100x60x25), not {text!r}")
    return values  # type: ignore[return-value]


def validate(resolved: dict[str, Any], document_type: str) -> None:
    if int(resolved["axes"]) not in (3, 4, 5):
        raise ArgumentRefused(f"--axes is 3, 4 or 5, not {resolved['axes']}")
    tools(resolved.get("tools"))
    stock(resolved.get("stock"))


def context(report: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    material = materials.resolve(resolved.get("material"))
    material_class = materials.material_class(material)
    given = tools(resolved.get("tools"))
    axes = int(resolved["axes"])
    return {"material": material, "material_class": material_class, "axes": axes,
            "turning": bool(resolved.get("turning")), "tools_given": given is not None,
            "min_tool_mm": min(given) if given else None,
            # walls are judged by the material's class; with none given, by a metal's (the laxer) limits
            "wall_class": material_class or "metal"}


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
        for item in _items(report, "turning"):
            if item.get("sharp_profile_corners"):
                found.append(CheckFinding(
                    "info", "cnc.turned_corner_sharp",
                    f"{item.get('part')}: {item['sharp_profile_corners']} sharp internal corner(s) on the turned "
                    "profile: a turning insert leaves its nose radius in each (0.2 to 0.8 mm on standard inserts: "
                    "text-to-cad's own figure, no guide's)", item.get("location"),
                    "draw the corner's radius (0.4 mm suits most inserts), or an undercut relief where a "
                    "mating part must seat"))
        # what the milling rules judge and turning's do not: said, never read as a pass
        found.append(CheckFinding(
            "info", "cnc.turning_not_judged",
            "turning judges the profile (the axis, the diameters and length, grooves, bores, walls, closed voids "
            "and faces no tool reaches) and the live tooling's pockets and holes; it does not judge setups and "
            "chucking, a sharp concave edge or a narrow gap off the grooves, or an undercut a five-axis mill "
            "would reach: those rules are milling's (rules: not_applicable)", "rules",
            "check the part without --turning for the milled features"))
    else:
        for item in _items(report, "setups"):
            if item.get("rotary_axis"):
                found.append(CheckFinding("info", "cnc.rotary_axis",
                                          f"{item['part']}: the rotary axis taken is {item['rotary_axis']}",
                                          item.get("location")))
    balls = [item for item in _items(report, "sharp_edges") if item.get("made_by") == "ball_mill"]
    if balls:
        worst = max(balls, key=lambda item: item.get("deviation_mm") or 0)
        found.append(CheckFinding(
            "info", "cnc.ball_creases",
            f"{len(balls)} sharp crease(s) a ball end mill makes, rounded by its {mm(worst['radius_mm'])} mm radius: "
            f"up to {mm(worst['deviation_mm'])} mm off the drawn edge ({worst['edge']}, a "
            f"{worst['void_angle_deg']:.0f}-degree void)", worst.get("location"),
            "draw the round if that is outside the part's tolerance"))
    flanks = [item for item in _items(report, "sharp_edges") if item.get("made_by") == "end_mill_flank"]
    if flanks:
        worst = max(flanks, key=lambda item: item.get("deviation_mm") or 0)
        found.append(CheckFinding(
            "info", "cnc.flank_corners",
            f"{len(flanks)} sharp corner(s) of {min(i['void_angle_deg'] for i in flanks):.0f} degrees or more along "
            f"the tool's axis, made by its flank: its {mm(worst['radius_mm'])} mm radius leaves up to "
            f"{mm(worst['deviation_mm'])} mm in the corner ({worst['edge']}, a {worst['void_angle_deg']:.0f}-degree "
            "void)", worst.get("location"), "draw the corner as the tool leaves it if that is outside the tolerance"))
        over = [item for item in flanks if (item.get("deviation_mm") or 0) > FLANK_RESIDUE_MM]
        if over:
            found.append(CheckFinding(
                "warning", "cnc.flank_corner_residue",
                f"{len(over)} corner(s) along the tool's axis keep more than {FLANK_RESIDUE_MM:g} mm of the "
                f"{mm(worst['radius_mm'])} mm tool's radius, up to {mm(worst['deviation_mm'])} mm ({worst['edge']}, "
                f"a {worst['void_angle_deg']:.0f}-degree corner; {FLANK_RESIDUE_MM:g} mm is text-to-cad's own "
                "figure, no guide's)", worst.get("location"), "draw the corners' radius, or open the corners"))
    small = report.get("small_features") or {}
    if isinstance(small, dict) and (small.get("fine_faces") or 0) >= 20:
        found.append(CheckFinding("info", "cnc.fine_detail",
                                  f"{small['fine_faces']} faces are under 1 mm across: text, knurling or fine "
                                  f"detail, which takes micro tools or engraving", "small_features"))
    return found


def summary(report: dict[str, Any], resolved: dict[str, Any], candidates: bool) -> str:
    bodies = report.get("bodies") or []
    head = "turning" if resolved.get("turning") else f"{resolved['axes']}-axis milling"
    # setups are a part's: an assembly's parts are each clamped on their own, so its largest is said, never a sum
    per_part = [item.get("setup_count") or 0 for item in _items(report, "setups")]
    setups = max(per_part, default=0)
    # the parts judged: each solid of a part that holds several is one (``stock`` has one item a part judged)
    judged = len(_items(report, "stock")) or len(bodies)
    counts = [f"{judged} part(s)", f"{mm(round(sum(body.get('volume_mm3') or 0 for body in bodies), 3))} mm3"]
    if setups and not resolved.get("turning"):
        counts.append(f"up to {setups} setup(s) a part" if len(per_part) > 1 else f"{setups} setup(s)")
    for family in ("holes", "pockets"):
        value = report.get(family)
        if isinstance(value, dict) and value.get("count"):
            counts.append(f"{value['count']} {family}")
    return f"{head}: {', '.join(counts)}"
