"""CNC machining, milling and turning: its options, rules, findings and summary (``cad._internal.dfm``).

Measured on exact geometry alone (a STEP, an xbf, a document the engine holds; ``cad.build123d._dfm_cnc``
says how): holes, pockets, internal corners, sharp concave edges no rotating tool makes, walls, gaps, tool
access and setups per approach direction, closed voids, stock, small features, and with ``turning`` the
axis, diameters, bores, grooves and live-tooling features.

The rules (``RULES``) are general practice, each number from a published CNC design guide (Protolabs
Network's, cited as the evidence, not as a shop's limit). A limit that follows the tools given
(``--tools``) is the smallest tool's; without ``--tools`` the guide's own number stands. A machine's size,
a lathe's capacity and a shop's own feature limits are no rule here: the stock given (``--stock``) is
checked, and the measurements say the rest.
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
_VERSION = "2026-11-08"
HUBS = Source("hubs-cnc", "Protolabs Network (Hubs)", "How to design parts for CNC machining",
              "https://www.hubs.com/knowledge-base/how-design-parts-cnc-machining/", _ACCESSED)

#: Within this share of its area, a face a sample of which no direction reached is still reached: one
#: sampled point is a few percent of a small face, and a ray grazing an edge is no undercut.
ACCESS_TOLERANCE = 0.02

_MILLING = {"turning": False}
_NO_TOOLS = {"tools_given": False}
_TOOLS = {"tools_given": True}


#: Without ``--tools``, the radius a sharp corner or edge is told to take: a 2.5 mm end mill's, the smallest
#: standard tool (Hubs: features under 2.5 mm are micro-machining).
_SMALL_TOOL_RADIUS = 1.25
#: What a failing item says of itself, appended to the message (``Rule.detail``).
_CORNER_DETAIL = "{edge}, {height_mm:g} mm tall, {depth_mm:g} mm below the top"
_EDGE_DETAIL = "{edge} between {between}, a {void_angle_deg:.0f}-degree void, at {xyz}"
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
    "no_square_face": ("sharp concave edge (no face square to a machine direction)",
                       "neither face at its {void_angle_deg:.0f}-degree void is a plane square to a machine "
                       "direction, so no tool's corner makes it sharp: round it to at least {limit:g} mm (a ball "
                       "end mill's radius), square one face to an approach direction, or give more axes"),
}
#: A sharp edge a tool along a direction the machine lacks would make: the access warning's severity and words.
_OTHER_AXES = ("sharp concave edge (made along a direction this machine lacks)",
               "a tool along a direction this machine lacks makes it sharp: an angled setup or more axes "
               "(--axes 5), or round it to at least {limit:g} mm")


def _corner_rules(source: str, sharp_note: str) -> tuple[Rule, ...]:
    """A sharp vertical corner and a sharp concave edge, judged against the radius they must be given: half
    the smallest tool with ``--tools``, else the smallest standard tool's (``_SMALL_TOOL_RADIUS``). An edge's
    message and fix follow its ``reason``; a sharp edge a tool along a direction the machine lacks would make
    is a warning (more axes make it), every other one an error."""
    corner_fix = ("sharp vertical corner: give it a radius of at least {limit:g} mm (a third of the cavity's "
                  "depth or more is better), or a dog-bone relief, or plan EDM")
    found: list[Rule] = []
    for when, scale, limit in (({**_MILLING, **_TOOLS}, "min_tool_mm", 0.5),
                               ({**_MILLING, **_NO_TOOLS}, None, _SMALL_TOOL_RADIUS)):
        found.append(Rule("cnc.internal_corner_sharp", "internal_corners", "radius_mm", "min", limit, "mm",
                          "sharp vertical corner radius", source, scale_by=scale, when=when,
                          item_when={"sharp": True}, fix=corner_fix, note=sharp_note, detail=_CORNER_DETAIL))
        for reason, (what, fix) in _EDGE_REASONS.items():
            found.append(Rule("cnc.sharp_internal_edge", "sharp_edges", "radius_mm", "min", limit, "mm",
                              what + " radius", source, scale_by=scale, when=when, item_when={"reason": reason},
                              fix=fix, note=sharp_note, detail=_EDGE_DETAIL))
        found.append(Rule("cnc.sharp_internal_edge", "sharp_edges", "radius_mm", "min", limit, "mm",
                          _OTHER_AXES[0] + " radius", source, severity="warning", scale_by=scale, when=when,
                          item_when={"reason": "other_axes"}, fix=_OTHER_AXES[1], note=sharp_note,
                          detail=_EDGE_DETAIL))
    found.append(Rule("cnc.internal_corner_radius", "internal_corners", "radius_mm", "min", 0.5, "mm",
                      "internal corner radius", source, scale_by="min_tool_mm", when={**_MILLING, **_TOOLS},
                      item_when={"sharp": False},
                      fix="radius the corner to at least {limit:g} mm, the smallest tool's radius, or add a smaller "
                          "tool", note="a corner tighter than the smallest end mill's radius is not cut by it"))
    return tuple(found)


def _inclined_rules(source: str, note: str) -> tuple[Rule, ...]:
    """A pocket or hole along no direction the machine has: its own setup, an angled one, or more axes. Five
    axes reach every direction (not applicable); on four, the features square to the rotary axis pass."""
    return tuple(Rule("cnc.inclined_feature", family, "inclination_deg", "max", 0.0, "deg",
                      f"{noun} axis off the machine's directions", source, severity="warning",
                      when={**_MILLING, "axes": (3, 4)}, item_when={"reachable": False},
                      fix=f"an inclined {noun}: an angled fixture (its own setup), or 4 or 5 axes, or square it to "
                          "a side of the part", note=note)
                 for family, noun in (("pockets", "pocket"), ("holes", "hole")))


def _knife_rule(source: str, limit: Any, by: str | None, note: str) -> Rule:
    return Rule("cnc.knife_edge", "knife_edges", "thickness_mm", "min", limit, "mm",
                "material at a knife edge (a convex edge under 45 deg)", source, severity="warning", by=by,
                fix="blunt it -- a flat or round at least {limit:g} mm across -- or open its angle to 45 deg or more",
                note=note)


_RULES: tuple[Rule, ...] = (
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
    *_inclined_rules("hubs-cnc", "align every feature (holes, cavities, vertical walls) to one of the six "
                                 "principal directions; if that is not possible, 5-axis machining is an option"),
    Rule("cnc.hole_diameter", "holes", "diameter_mm", "min", 1.0, "mm", "hole diameter", "hubs-cnc",
         fix="make the hole 1 mm or more", note='"Feasible: any diameter larger than 1 mm"'),
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
         severity="warning", when=_MILLING, item_when={"kind": "undercut", "hole": False},
         fix="open the face to a setup direction, or plan a T-slot or dovetail cutter, or more axes",
         note="undercuts need special cutters (T-slot, dovetail) and cost more"),
    Rule("cnc.undercut", "access", "unreached_fraction", "max", ACCESS_TOLERANCE, "share",
         "share of the hole's face no straight tool reaches from the machine's directions", "hubs-cnc",
         severity="warning", when=_MILLING, item_when={"kind": "undercut", "hole": True},
         fix="the hole's axis ({hole_axis}) is along no machine direction: drill it in an angled setup or on "
             "more axes, or square it to a side", note="a drill comes in along the hole's axis"),
    Rule("cnc.special_cutter", "access", "edge_count", "max", 0, "edges", "edges only a special cutter makes",
         "hubs-cnc", severity="warning", when=_MILLING, item_when={"kind": "special_cutter"},
         fix="a {cutter} cuts it: keep the undercut 3 to 40 mm wide in a standard size (a dovetail 45 or 60 "
             "degrees), or open it to a setup direction",
         note="undercuts (T-slots and dovetails) are machined using special tools; their width can vary between "
              "3 mm and 40 mm"),
    Rule("cnc.no_line_of_sight", "access", "unreached_any_direction_fraction", "max", ACCESS_TOLERANCE, "share",
         "share of the face no straight line from outside reaches", "hubs-cnc", severity="warning", when=_MILLING,
         item_when={"kind": "no_line_of_sight"},
         fix="redesign so the face opens to the outside, or plan a lollipop/keyseat cutter or EDM",
         note="undercuts need special cutters"),
    Rule("cnc.enclosed_void", "voids", "volume_mm3", "max", 0.0, "mm3", "enclosed void", "hubs-cnc",
         fix="open the void to the outside or make the part in pieces: no tool reaches a closed cavity",
         note="a tool reaches only what it can enter"),
    Rule("cnc.setups", "setups", "setup_count", "max", 5, "setups", "setups", "hubs-cnc", severity="warning",
         when=_MILLING, fix="put the features on fewer sides: each setup is a refixturing",
         note='"This is often acceptable if the part needs to be rotated up to three or four times, but anything '
              'above this limit is excessive." Four rotations are five clampings'),
)

def _detailed(rules: tuple[Rule, ...]) -> tuple[Rule, ...]:
    """Every wall and gap rule says the face across and the thinnest point."""
    return tuple(dataclasses.replace(rule, detail=_ACROSS_DETAIL[rule.family])
                 if rule.family in _ACROSS_DETAIL and not rule.detail else rule for rule in rules)


_NOTE = ("general practice from a published CNC design guide (Protolabs Network's), no shop's limits: compare "
         "the measurements with a shop's own")
RULES = RuleSet("cnc", "text-to-cad general rules", _VERSION, _detailed(_RULES), (HUBS,), note=_NOTE)


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
    counts = [f"{len(bodies)} part(s)", f"{mm(round(sum(body.get('volume_mm3') or 0 for body in bodies), 3))} mm3"]
    if setups and not resolved.get("turning"):
        counts.append(f"up to {setups} setup(s) a part" if len(per_part) > 1 else f"{setups} setup(s)")
    for family in ("holes", "pockets"):
        value = report.get(family)
        if isinstance(value, dict) and value.get("count"):
            counts.append(f"{value['count']} {family}")
    return f"{head}: {', '.join(counts)}"
