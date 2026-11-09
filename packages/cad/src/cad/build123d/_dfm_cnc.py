"""cnc's measurements of exact geometry (``cad._internal.dfm.cnc`` says what they are for).

Each part of the document is measured on its own B-rep (``_dfm_cnc_model.Model``), and every family's items
say which part and face they are at (``plate/face 7``). Each part is machined in its own frame
(``_dfm_cnc_model.machine_frame``: the axes its faces' normals and its holes' axes square, never the world's), so
a part turned in its model reads as drawn: it is measured turned into that frame, every place and direction
it reports turned back to its own coordinates (``machine.frames`` says each part's). "World axis" below is
the machine frame's. The families, and how each is measured:

- ``holes`` (``_dfm_cnc_holes``): concave cylinders and their coaxial neighbours; diameter, depth (the drilled
  length below any counterbore; ``overall_depth_mm`` the whole), blind or through by an exact ray along the
  axis, the floor (drill point and its angle, or flat), counterbores (each with its own depth to diameter),
  countersinks, the standard drill each diameter is.
- ``pockets``: every planar face that meets, by a concave edge (or through a concave root fillet), a face
  lying along its normal is a pocket's floor; its walls are those faces and the faces along the normal joined
  to them by concave or tangent edges. Depth (floor to the walls' rim), depth from the part's top along the
  normal (what a tool must reach), width (the narrowest gap between opposite walls: exact rays from each
  wall along its normal that land on another wall of the pocket, the two walls named), closed or open (a
  convex edge on the floor's outer boundary opens it), the floor's root fillet radius, ``reachable`` (along a
  direction the machine has, or no edge of it left unmade) and ``inclination_deg``. A **through** cavity has
  no floor (a window, a through slot, a cut-out): faces along a machine axis joined by concave or tangent
  edges along it, none a pocket's, closed around the axis (``_open_across``: no ray across the axis from
  inside it leaves the part -- an open valley, or a T-slot or a dovetail open at its neck, is no window), with
  a corner (a concave cylinder along it, or a sharp concave edge along it); its depth is its walls' extent
  along the axis.
- ``internal_corners``: a pocket's in-plane corners -- its concave cylinders along the tool axis (their
  radius) and its sharp concave edges along the tool axis that no tool makes from another side (radius 0);
  a through cavity's likewise. The floor-to-wall root is no corner: a flat end mill makes
  it sharp. Each against its depth and against the largest tool that fits it (``--tools``, else a tool of
  twice its radius); a radius is read to ``RADIUS_TOLERANCE``.
- ``threads`` (``_dfm_cnc_holes``): modelled threads, freeform flanks wound about a cylinder's axis: major and
  minor diameters, pitch, length, internal or external. Their faces are a tap's: no other family reads them.
- ``sharp_edges``: every other sharp concave edge that no rotating tool makes. Each way is tried at stations
  along the edge (``_station_count``: its ends, just inside, and between, at most the smallest tool's radius
  apart) and makes it only where it reaches every one; where some way reaches part of it, the stretch none
  reaches is unmade, its ends bisected between stations (``_unreached_intervals``), the item at that stretch
  (``unreached_mm``). A disc cutter's disc must get in (a bore it fits, an opening as wide as it, or a side the
  recess opens to at its own level), else ``no_way_in``; a dovetail or V of no standard angle is a special
  cutter's, its angle named; a narrow slot opening (``narrow_opening``) and a profile's obtuse root
  (``obtuse_root``) are said as warnings on made edges; slivers under ``SLIVER_MM`` are not judged. A tool's corner makes one where one face is a floor or a ceiling square to an approach
  direction of the machine and the angle in the void is at least 90 degrees: an end mill where a ray from
  that face along the direction escapes the part; a T-slot cutter (a keyseat cutter where its way in is a
  bore beside the recess, a groove inside a bore) where, beside every station, its shank along the
  direction leaves the part from some place across the void and the disc that reaches the station from
  there touches no material (the shank travels along the edge: an opening shorter than the edge, a port
  in a wall, is no way in), through an opening at least as wide as the recess is tall; a dovetail cutter
  makes a 45 or 60 degree one the same way, a chamfer mill a 60, 90 or 120 degree V whose bisector keeps
  to one axis along it, a chamfer mill's shoulder (180 less its half angle) along its axis, a ball end mill
  one of ``BALL_VOID_DEG`` or more along a direction both faces look along. The floor or ceiling must be a
  plane. Along any direction a setup presents (the part clamped to present it), each such direction one of
  the ``setups``: a square end mill where its end lies on one face square to the direction and its flank on
  the other, which lies along it, seen from outside (a profile's corner side-milled, whatever the part's
  turn); a chamfer mill along the bisector of a V between two planes; and an obtuse edge between two planes
  each seen from outside along its own normal, each side faced from its own direction. An obtuse edge (a void
  over ``OBTUSE_DEG``) adds no setup of its own, however it is made: it is made in the setups that make its
  two faces, which the cover counts. On five simultaneous axes a chamfer mill's direction leans along the
  edge as it goes (``LEANS_DEG``), a continuous path station to station; an end mill's stays its face's
  normal. The end mill is tried from both faces
  before any cutter, the setups' ways last.
  Each unmade edge says why (``reason``: ``other_axes``, ``vertical_corner``, ``acute``, ``blocked``,
  ``no_square_face``, see ``_why``); a ball's crease is an item too (``made_by`` ``ball_mill``, its round's
  ``deviation_mm`` from the drawn edge), and so is a corner of ``BALL_VOID_DEG`` or more along the tool's axis
  that its flank makes (``end_mill_flank``, the residue its radius leaves); an edge only a T-slot, a dovetail or a keyseat cutter makes is an
  ``access`` item of kind ``special_cutter``. ``by_tool`` counts every concave edge by the tool that makes it. An edge
  that is a reported corner's run through a small edge round at its end is folded into that corner
  (``folded_edges``, see ``_fold``), not listed again.
- ``walls``: the thickness under each face (an exact ray into the material from points sampled on it, to the
  first face across that faces the other way), the thinnest per face under 5 mm, with the wall's height. The
  listed items are then refined to the exact minimum distance between the face and the face across
  (``BRepExtrema_DistShapeShape``), kept where that segment runs through the material near square to the
  face. A face across that meets the face at a knife edge is no wall: ``knife_edges`` reports it.
- ``gaps``: the width of the void in front of each face (the same ray outward, a face sharing an edge with it
  not counted: the two close to nothing at that edge, its angle ``sharp_edges``' to judge), the narrowest per
  face under 10 mm: the slots and channels a tool must fit in; refined like walls, through the void. One pocket's or
  cavity's gaps are one item, its narrowest (``pocket``, ``also_at``); a recess's floor-to-ceiling height, where a
  slot cutter makes the recess, is that cutter's (``made_by`` ``slot_cutter``), else an end mill's.
- ``knife_edges``: convex edges whose material angle, read along the edge (``brep.edge_angles``; its least then
  found between the samples about it, ``brep.least_edge_angle``), falls under ``KNIFE_DEG`` (printing's
  notion): the material thins to nothing there, whatever a sampled wall would read.
- ``access`` and ``setups``: which sampled points of each face a straight tool reaches from each of the
  machine's approach directions (exact rays along the direction must escape the part), the fewest
  directions that reach them all and make the sharp edges an end mill makes (greedy set cover, ``_setup``)
  and the fixtures they need; the faces no direction
  reaches, and whether any direction at all (a five-axis machine's) would. Five axes try every direction a
  four-axis machine would (each 15 degrees about each world axis) before probing the sphere, so they reach
  at least what four do. A hole or pocket along no direction the machine has adds its own orientation and
  clamping (``inclined_directions``).
- ``voids``: closed cavities inside the material (a solid's inner shells).
- ``stock``: the part's box or ``--stock``, the material removed, the part's size sorted.
- ``small_features``: the shortest edge, the smallest face, and the faces narrower than half a millimetre.
- with ``turning`` (``_dfm_cnc_turning``): the axis, how much of the part turns about it, its diameters,
  bores, grooves and the features a lathe's live tooling makes; ``pockets`` and ``internal_corners`` are then
  those features' alone (a keyway's), measured as a mill's.

One cause is one judged item (``_one_cause``): the faces a special cutter's recess leaves unreached, and those
of an inclined hole on three or four axes, are kept as ``access`` items naming it (``part_of``), judged once
as that recess (``special_cutter``) or that hole (``inclined_feature``).

A figure the geometry does not give is None, never a guess. Lengths are millimetres.
"""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from cad._internal.dfm import Unmeasured, checkpoint
from cad._internal.dfm import cnc as rules_side
from cad._internal.meshops_printing import ANGLE_EPS, KNIFE_DEG
from cad.build123d import _dfm_brep as brep
from cad.build123d._dfm_cnc_holes import holes as find_holes
from cad.build123d._dfm_cnc_holes import threads as find_threads
from cad.build123d._dfm_cnc_model import (LIFT, SAME, WORLD, Model, Stations, about, directions_for, edge_normals,
                                          fibonacci, framed, machine_frame, stations, stations_at, turned, unit)

__all__ = ["measure"]

#: Items a family keeps, worst first; the family counts the rest.
CAP = 200
WALL_CAP_MM = 5.0
GAP_CAP_MM = 10.0
TINY_MM = 0.5
#: Two faces across a wall or a gap face each other within this (cosine of their normals).
OPPOSED = -0.7
#: Standard chamfer (V) mill angles, degrees.
V_MILLS = (60.0, 90.0, 120.0)
#: Standard dovetail cutter angles, degrees (Hubs: 45 and 60).
DOVETAILS = (45.0, 60.0)
#: A sharp concave edge whose void angle is at least this many degrees is a ball end mill's: contouring
#: along a direction both faces look along, the ball leaves a round in the crease that departs from the
#: drawn edge by R (1 / sin(void / 2) - 1) -- 0.035 R at 150 degrees, 0.0006 R at 176 --, under a finish
#: tolerance for any end mill a part this size is cut with. Below it the crease is a corner a radius must
#: be drawn for. A judgement, not a guide's number: the owner's to confirm.
BALL_VOID_DEG = 150.0
#: A face looks along a direction where its normal makes more than half a degree's sine with it: a face along
#: the direction reads 1e-16 either way in a turned part, and is no face a ball's side sees.
LOOKS_ALONG = math.sin(math.radians(0.5))
#: A chamfer mill's cone face makes the mill's half angle with its axis, its normal's cosine to the axis the
#: half angle's sine, within this (the void's half degree, and noise).
CONE_TOLERANCE = 0.01
#: Without ``--tools``, the radius of the ball a crease is judged as rounded by: a 2.5 mm ball end mill's, the
#: smallest standard tool (Hubs: features under 2.5 mm are micro-machining).
BALL_RADIUS_MM = 1.25
#: A face with more edges than this (a web around many holes) is not refined to its exact wall: the least
#: distance between faces costs with their edges, and over 200 listed items that is the check's budget.
COMPLEX_EDGES = 16
#: A corner's radius is read to this (mm): a radius within half of it of a tool's radius is that tool's.
RADIUS_TOLERANCE = 0.01
#: Stations along a sharp concave edge (``_dfm_cnc_model.stations``: its ends, just inside, and between) a
#: tool's way is tried at: a way makes the edge where it reaches every one; a stretch none reaches is unmade.
EDGE_STATIONS = 9
#: An edge is tried at stations at most a tool's radius apart, this many at most.
MAX_STATIONS = 129
#: A stretch no way reaches has its ends found to a tenth of a millimetre, or this share of a short edge.
UNREACHED_TOLERANCE = 0.01
#: A sharp edge shorter than this (mm, or a hundred-thousandth of the part's size) is a sliver of the model's
#: own, no feature a tool makes: not judged (``by_tool`` ``sliver``).
SLIVER_MM = 0.025
#: Places a slot, dovetail or keyseat cutter's shank is looked for across the void beside each station, at most.
WALK_STEPS = 64
#: An edge's needs: each a list of directions any one of which meets it (an end mill's or a chamfer mill's,
#: with whether the machine has it); the edge is made when every need is met.
Needs = list[list[tuple[np.ndarray, bool]]]
#: On five simultaneous axes a chamfer mill leans along the edge as it goes: by one of these (degrees, toward the
#: edge's way), the lean turning by at most ``LEAN_STEP_DEG`` station to station. Own figures.
LEANS_DEG = (0.0, -10.0, 10.0, -20.0, 20.0, -30.0, 30.0, -40.0, 40.0)
LEAN_STEP_DEG = 20.0
#: A sharp concave edge whose void is over this many degrees is obtuse: made in the setups that make its two
#: faces, it adds no setup of its own (a square corner's 90 degrees, its end mill's end and flank, does).
OBTUSE_DEG = 90.5
#: A disc cutter's shank is taken as at least this radius (mm), and its disc as touching no material along its
#: rim, sampled at ``DISC_POINTS``; ``SHANK_TRIES`` places across the void are tried a station. Own figures.
SHANK_RADIUS_MM = 0.5
DISC_POINTS = 24
SHANK_TRIES = 12


def measure(document: brep.Document, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The cnc report of ``document``: facts alone, every family's ``items`` at a ref."""
    if not document.parts:
        raise Unmeasured("no_geometry", "the document has no part to measure")
    axes = int(options.get("axes") or 3)
    turning = bool(options.get("turning"))
    tools = rules_side.tools(options.get("tools"))
    stock = rules_side.stock(options.get("stock"))
    families: dict[str, list[dict[str, Any]]] = {}
    scalars: dict[str, dict[str, Any]] = {}
    failed: dict[str, str] = {}
    models: list[Model] = []
    frames: list[np.ndarray] = []
    framing: list[dict[str, Any]] = []
    for part in document.parts:
        checkpoint()
        try:
            model = Model(part)
            # the part is machined in its own frame (``machine_frame``): measured turned into it, every place
            # and direction it reports turned back
            rotation, share = machine_frame(model.faces, model.surfaces)
            if not np.array_equal(rotation, np.eye(3)):
                model = Model(framed(part, rotation), [turned(surface, rotation) for surface in model.surfaces])
        except Exception as error:  # noqa: BLE001 - a part that does not read is the report's to say
            failed.setdefault("model", f"{part.name}: {error}")
            continue
        models.append(model)
        frames.append(rotation)
        framing.append({"part": part.name, "location": model.ref(1), "axes": [brep.rounded(row, 6) for row in rotation],
                        "turned": not np.array_equal(rotation, np.eye(3)), "aligned_area_fraction": round(share, 4)})
        before = {name: len(items) for name, items in families.items()}
        _measure_part(model, len(models) - 1, axes, turning, tools, stock, families, scalars, failed)
        for name, items in families.items():
            for item in items[before.get(name, 0):]:
                item.setdefault("_model", len(models) - 1)
    report: dict[str, Any] = {"machine": {"axes": axes, "turning": turning,
                                          "tools_mm": list(tools) if tools else None,
                                          "stock_mm": list(stock) if stock else None, "frames": framing}}
    # a turned part's pockets and corners are its live tooling's milled features alone (``_pockets``'s ``only``)
    names = list(_FAMILIES) + (["turning", "turned_diameters", "bores", "grooves", "live_tooling"] if turning else [])
    for name in names:
        if name in failed:
            report[name] = {"error": failed[name]}
            continue
        items = families.get(name, [])
        items.sort(key=_ORDER.get(name, lambda item: 0))
        if name in ("walls", "gaps"):
            # the listed items only: an exact distance per item, not per face, keeps the budget on big parts
            for item in items[:CAP]:
                try:
                    _refine(models[item["_model"]], item, outward=name == "gaps")
                except Exception:  # noqa: BLE001 - a pair the kernel cannot measure keeps its sampled figure
                    pass
            items[:CAP] = sorted(items[:CAP], key=_ORDER[name])
            # one wall (or gap) between two faces is one item: each face's ray finds the other
            pairs: set[tuple[int, frozenset[int]]] = set()
            folded = []
            for item in items:
                key = (item["_model"], frozenset((item["_face"], item["_opposite"])))
                if key not in pairs:
                    pairs.add(key)
                    folded.append(item)
            items = folded
        if name == "gaps":
            # one cavity's width is one item: its narrowest gap, the others named beside it
            narrowest: dict[tuple[int, str], dict[str, Any]] = {}
            kept = []
            for item in items:
                cavity = item.get("pocket")
                if cavity is None:
                    kept.append(item)
                    continue
                key = (item["_model"], cavity)
                if key in narrowest:
                    narrowest[key].setdefault("also_at", []).append(item["location"])
                    continue
                narrowest[key] = item
                kept.append(item)
            items = kept
        family = {"items": [_public(_to_part(item, frames[item["_model"]]) if "_model" in item else item)
                            for item in items[:CAP]], "count": len(items), **scalars.get(name, {})}
        for item in family["items"]:
            if item.get("unreached_mm"):
                # the stretch of an edge no tool reaches, where it lies in the part's own coordinates
                where = ", ".join(f"{float(v):g}" for v in item["xyz"])
                item["unreached"] = f"; {item['unreached_mm']:g} mm of it, around {where}, reached by no tool"
        report[name] = family
    if "model" in failed:
        report["model"] = {"error": failed["model"]}
    report["partial_sections"] = sorted(name for name in failed)
    report["partial"] = bool(failed)
    return report


def _one_cause(model: Model, index: int, state: dict[str, Any], families: dict[str, list[dict[str, Any]]],
               holes: list[dict[str, Any]], pockets: list[dict[str, Any]], turning: bool) -> None:
    """One cause, one item a rule judges; the others it explains name it (``part_of``) and are kept as facts:

    - the faces a special cutter's recess leaves unreached (``undercut``, ``no_line_of_sight``) are that
      recess's, its ``special_cutter`` item listing them (``unreached_faces``);
    - a hole along no direction the machine has is ``inclined_feature``'s: the faces of it no direction reaches
      are its own, not an undercut of their own;
    - a gap between two faces of one pocket or cavity is that cavity's width: its narrowest is the item, the
      others it folds (``measure``), and a gap whose two faces are a floor and a ceiling of a recess a slot
      cutter makes (planes square to one direction) is the cutter's thickness to cut, not an end mill's
      diameter (``made_by`` ``slot_cutter``).

    Only this part's items (``index``'s: those with no ``_model`` yet, its gaps that model's)."""
    access = [item for item in families.get("access", []) if "_model" not in item]
    specials = [item for item in access if item.get("kind") == "special_cutter"]
    for special in specials:
        faces = special.get("_faces") or set()
        folded: dict[str, list[str]] = {"undercut": [], "no_line_of_sight": []}
        for item in access:
            if item.get("kind") in folded and item.get("part_of") is None and _ordinal(item["location"]) in faces:
                item["part_of"] = special["location"]
                folded[item["kind"]].append(item["location"])
        if folded["undercut"] or folded["no_line_of_sight"]:
            special["unreached_faces"] = folded["undercut"] + folded["no_line_of_sight"]
            said = [", ".join(folded["undercut"]) + " (from no machine direction)"] if folded["undercut"] else []
            if folded["no_line_of_sight"]:
                said.append(", ".join(folded["no_line_of_sight"]) + " (by no straight line from outside at all: "
                            "the cutter needs a way in, or a keyseat cutter or EDM)")
            special["also"] = "; ".join(said)
    if not turning and state["axes"] in (3, 4):
        for hole in holes:
            if hole.get("reachable") is False:
                own = set(hole.get("_faces") or ())
                for item in access:
                    if item.get("hole") and item.get("part_of") is None and _ordinal(item["location"]) in own:
                        item["part_of"] = hole["location"]
    for item in [item for item in families.get("gaps", []) if item.get("_model") == index]:
        pair = {item["_face"], item["_opposite"]}
        for special in specials:
            if len(pair) == 2 and pair <= (special.get("_faces") or set()) and _floor_and_ceiling(model, *pair):
                item["made_by"] = "slot_cutter"
                item["cutter_recess"] = special["location"]
        for pocket in pockets:
            faces = set(pocket.get("_walls") or ()) | set(pocket.get("_fillets") or ()) | (
                {pocket["_floor"]} if pocket.get("_floor") else set())
            if pair <= faces:
                item["pocket"] = pocket["floor"] or pocket["location"]
                break


def _ordinal(ref: str) -> int:
    """The face ordinal of a face ref (``plate/face 7``)."""
    return int(str(ref).rsplit(" ", 1)[-1])


def _floor_and_ceiling(model: Model, a: int, b: int) -> bool:
    """Whether two faces are planes facing each other square to one direction (a recess's floor and ceiling)."""
    sa, sb = model.surface(a), model.surface(b)
    return sa.kind == sb.kind == "plane" and float(np.asarray(sa.normal) @ np.asarray(sb.normal)) < -SAME


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if not key.startswith("_")}


#: The fields that hold a place, and those that hold a direction, of an item measured in its part's frame.
_PLACES = frozenset({"xyz", "axis_origin"})
_DIRECTIONS = frozenset({"axis", "opening", "direction", "tangent", "rotary_axis"})


def _to_part(value: Any, rotation: np.ndarray, key: str | None = None) -> Any:
    """``value`` (an item, or what it holds) measured in a part's machine frame (``rotation`` turned the part
    into it), as it lies in the part's own coordinates: places and directions turned back, the rest as it is."""
    if rotation is None or np.array_equal(rotation, np.eye(3)):
        return value
    if isinstance(value, dict):
        return {name: _to_part(found, rotation, name) for name, found in value.items()}
    if key == "inclined_directions" and isinstance(value, list):
        return [_to_part(found, rotation, "direction") for found in value]
    if key == "hole_axis" and isinstance(value, str):
        return ", ".join(f"{v:g}" for v in _to_part([float(part) for part in value.split(",")], rotation, "axis"))
    if key in _PLACES | _DIRECTIONS and isinstance(value, (list, tuple)) and len(value) == 3 and \
            all(isinstance(v, (int, float)) for v in value):
        back = rotation.T @ np.asarray(value, dtype=float)
        return brep.rounded(back, 4 if key in _PLACES else 6)
    if isinstance(value, list):
        return [_to_part(found, rotation, key) for found in value]
    return value


def _measure_part(model: Model, index: int, axes: int, turning: bool, tools: tuple[float, ...] | None,
                  stock: tuple[float, float, float] | None, families: dict[str, list[dict[str, Any]]],
                  scalars: dict[str, dict[str, Any]], failed: dict[str, str]) -> None:
    state: dict[str, Any] = {"axes": axes, "tools": tools, "stock": stock, "turning": turning}

    def run(name: str, step: Callable[[], Any]) -> Any:
        checkpoint()  # between families
        if name in failed:
            return None
        try:
            return step()
        except Exception as error:  # noqa: BLE001 - one family failing never loses the rest
            failed[name] = f"{model.part.name}: {type(error).__name__}: {error}"
            return None

    found = run("holes", lambda: find_holes(model))
    holes, hole_faces = found if found else ([], set())
    state["hole_faces"] = hole_faces
    families.setdefault("holes", []).extend(holes)
    families.setdefault("counterbores", []).extend(bore for hole in holes for bore in hole["_counterbores"])
    if "holes" in failed:
        failed.setdefault("counterbores", failed["holes"])
    found_threads = run("threads", lambda: find_threads(model, holes))
    threads, thread_faces = found_threads if found_threads else ([], set())
    families.setdefault("threads", []).extend(threads)
    state["thread_faces"] = thread_faces
    voids = run("voids", lambda: _voids(model)) or []
    # a modelled thread's flanks are a tap's or a thread mill's, not the end mill's: no rule of reach, walls
    # or gaps reads them (the threads family does)
    state["void_faces"] = {face for void in voids for face in void["_faces"]}
    state["hole_faces"] = hole_faces | thread_faces
    state["hole_axis"] = {face: ", ".join(f"{v:g}" for v in hole["axis"]) for hole in holes for face in hole["_faces"]}
    families.setdefault("voids", []).extend(voids)
    knives = run("knife_edges", lambda: _knife_edges(model, state)) or []
    families.setdefault("knife_edges", []).extend(knives)
    state["knife_pairs"] = {item["_pair"] for item in knives}
    access = run("access", lambda: _access(model, state))
    if access:
        families.setdefault("access", []).extend(access["items"])
        families.setdefault("setups", []).append(access["setup"])
        state["directions"] = access["directions"]
        state["rotary"] = access["rotary"]
    else:
        state["directions"] = directions_for(axes)
        state["rotary"] = None
    gaps = run("gaps", lambda: _gaps(model, state))
    if gaps is not None:
        families.setdefault("gaps", []).extend({**item, "_model": index} for item in gaps)
    walls = run("walls", lambda: _walls(model, state))
    if walls is not None:
        families.setdefault("walls", []).extend({**item, "_model": index} for item in walls)
    sharp = run("sharp_edges", lambda: _sharp_edges(model, state))
    state["unmakeable"] = sharp["unmakeable"] if sharp is not None else None
    state["refixtured"] = sharp["refixtured"] if sharp is not None else set()
    state["unmade"] = sharp["unmade"] if sharp is not None else {}
    if sharp is not None and access:
        families.setdefault("access", []).extend(sharp["special"])
    reported: set[int] = set()
    corners: list[dict[str, Any]] = []
    found_pockets: list[dict[str, Any]] = []
    if not turning:
        pockets = run("pockets", lambda: _pockets(model, state))
        if pockets is not None:
            found_pockets = pockets["pockets"]
            families.setdefault("pockets", []).extend(found_pockets)
            corners = pockets["corners"]
            reported = {corner["_edge"] for corner in corners if corner.get("_edge")}
            families.setdefault("internal_corners", []).extend(corners)
        else:
            failed.setdefault("internal_corners", failed["pockets"])
    inclined = _inclined(model, state, holes, found_pockets)
    if access and sharp is not None and (sharp["made_from"] or sharp["special"]):
        # the setups again, now the sharp edges an end mill makes are known: each needs one of its directions;
        # a special cutter's recess is its own (made along the cutter's axis, which the faces around its way in
        # bring), no face of it asking a direction of its own
        recess = {face for item in sharp["special"] for face in item["_own"]}
        setup = access["setup"]
        setup.clear()
        setup.update(_setup(model, access["cover"], sharp["made_from"], [] if turning else inclined, recess))
    if access and inclined and not turning:
        # each inclined feature's direction is an orientation (and a clamping) of its own
        setup = access["setup"]
        setup["inclined_directions"] = [brep.rounded(d, 4) for d in inclined]
        setup["orientation_count"] += len(inclined)
        setup["setup_count"] += len(inclined)
    if sharp is not None:
        totals = scalars.setdefault("sharp_edges", {"by_tool": {}})["by_tool"]
        for way, count in sharp["ways"].items():
            totals[way] = totals.get(way, 0) + count
        # a pocket's sharp corner is reported once, as a corner of radius 0, and so are the short edges its
        # run makes through a small edge round beside it
        left = [item for item in sharp["items"] if item["_edge"] not in reported]
        families.setdefault("sharp_edges", []).extend(_fold(model, left, corners) + sharp["balls"])
    families.setdefault("stock", []).extend(run("stock", lambda: _stock(model, state)) or [])
    small = run("small_features", lambda: _small(model))
    if small is not None:
        families.setdefault("small_features", []).extend(small["items"])
        previous = scalars.get("small_features", {})
        merged = {key: min(value, previous[key]) if previous.get(key) is not None and value is not None else
                  (value if value is not None else previous.get(key)) for key, value in small["scalars"].items()}
        merged["fine_faces"] = previous.get("fine_faces", 0) + small["scalars"]["fine_faces"]
        scalars["small_features"] = merged
    if turning:
        from cad.build123d import _dfm_cnc_turning

        result = run("turning", lambda: _dfm_cnc_turning.turned(model, state, holes))
        if result is not None:
            for name, items in result.items():
                families.setdefault(name, []).extend(items)
            # the live tooling's features are milled: their pockets and corners are a mill's, judged as such
            live = {face for item in result["live_tooling"] for face in item["_faces"]}
            # and the planes they meet at a concave edge: a keyway's ends are square to the axis, but milled
            live |= {other for face in live for edge, other in model.neighbours(face)
                     if edge.concave and model.surface(other).kind == "plane"}
            pockets = run("pockets", lambda: _pockets(model, state, live))
            if pockets is not None:
                found_pockets = pockets["pockets"]
                families.setdefault("pockets", []).extend(pockets["pockets"])
                families.setdefault("internal_corners", []).extend(pockets["corners"])
                reported = {corner["_edge"] for corner in pockets["corners"] if corner.get("_edge")}
                families["sharp_edges"] = [item for item in families.get("sharp_edges", [])
                                           if item.get("_model") is not None or item["_edge"] not in reported]
            else:
                failed.setdefault("internal_corners", failed["pockets"])
        else:
            for name in ("turned_diameters", "bores", "grooves", "live_tooling", "pockets", "internal_corners"):
                failed.setdefault(name, failed["turning"])
    _one_cause(model, index, state, families, holes, found_pockets, turning)


# --- voids -----------------------------------------------------------------------------------------------


def _voids(model: Model) -> list[dict[str, Any]]:
    """Closed cavities: the inner shells of the part's solids."""
    from OCP.BRepClass3d import BRepClass3d
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    found = []
    for solid in model.part.solids():
        outer = BRepClass3d.OuterShell_s(solid.wrapped)
        for shell in solid.shells():
            if shell.wrapped.IsSame(outer):
                continue
            faces = sorted({model.part.face_ordinal(face) for face in shell.faces()} - {0})
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(shell.wrapped, props)
            if not faces:
                continue
            found.append({"volume_mm3": round(abs(float(props.Mass())), 4), "face_count": len(faces),
                          "location": model.ref(faces[0]), "faces": [model.ref(f) for f in faces[:20]],
                          "xyz": model.center(faces[0]), "_faces": faces})
    return found


# --- access ----------------------------------------------------------------------------------------------


def _reach(model: Model, points: np.ndarray, normals: np.ndarray, direction: np.ndarray) -> np.ndarray:
    reached = np.zeros(len(points), dtype=bool)
    facing = np.flatnonzero(normals @ direction >= -0.01)
    if len(facing):
        reached[facing] = model.escape_all(points[facing], normals[facing], direction)
    return reached


def _access(model: Model, state: dict[str, Any]) -> dict[str, Any]:
    """Which faces' sampled points a straight tool reaches from the machine's directions, the fewest
    directions that reach them (greedy set cover), and the faces left unreached."""
    axes = state["axes"]
    void_faces = state["void_faces"]
    stock_faces = set() if state["stock"] else _stock_faces(model)
    faces = [i for i in range(1, model.n + 1)
             if i not in void_faces and i not in stock_faces and i not in state["thread_faces"]]
    if not faces:
        faces = [i for i in range(1, model.n + 1) if i not in void_faces]
    owner: list[int] = []
    points_l, normals_l, areas_l = [], [], []
    for i in faces:
        p, n, a = model.samples(i)
        points_l.append(p)
        normals_l.append(n)
        areas_l.append(a)
        owner += [i] * len(p)
    if not owner:
        raise ValueError("no face could be sampled")
    points, normals, areas = np.vstack(points_l), np.vstack(normals_l), np.concatenate(areas_l)
    owner_a = np.array(owner)
    world = list(WORLD)
    reach = {k: _reach(model, points, normals, d) for k, d in enumerate(world)}
    candidates = world[:]
    rotary = None
    residual = ~np.any(np.array(list(reach.values())), axis=0)
    if axes == 4:
        best = None
        for axis in (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])):
            extra = [d for d in about(axis) if not any(abs(float(d @ w)) > SAME for w in world)]
            extra_reach = []
            for d in extra:
                r = np.zeros(len(points), dtype=bool)
                idx = np.flatnonzero(residual)
                r[idx] = _reach(model, points[idx], normals[idx], d)
                extra_reach.append(r)
            left = residual.copy()
            for r in extra_reach:
                left &= ~r
            score = (float(areas[left].sum()), -sum(abs(float(axis @ w)) < 1e-9 for w in world))
            if best is None or score < best[0]:
                best = (score, axis, extra, extra_reach)
        _, rotary, extra, extra_reach = best
        for d, r in zip(extra, extra_reach):
            reach[len(candidates)] = r
            candidates.append(d)
    probes = _probe_directions(model)
    if axes == 5:
        # every direction a four-axis machine has, about each world axis, on the points the six miss: five
        # axes reach at least what four do; the sphere's probe then takes what is left
        for axis in np.eye(3):
            for d in about(axis):
                if any(abs(float(d @ known)) > SAME for known in candidates):
                    continue
                idx = np.flatnonzero(residual)
                if not len(idx):
                    break
                r = np.zeros(len(points), dtype=bool)
                r[idx] = _reach(model, points[idx], normals[idx], d)
                if r.any():
                    reach[len(candidates)] = r
                    candidates.append(d)
                    residual &= ~r
        for d, r in _probe(model, points, normals, owner_a, np.flatnonzero(residual), probes):
            reach[len(candidates)] = r
            candidates.append(d)
    reachable_any = np.zeros(len(points), dtype=bool)
    for r in reach.values():
        reachable_any |= r
    unreached = ~reachable_any
    # would any direction at all reach the points the machine does not?
    anywhere = reachable_any.copy()
    if axes < 5 and unreached.any():
        for _, r in _probe(model, points, normals, owner_a, np.flatnonzero(unreached), probes):
            anywhere |= r
    items = []
    for i in faces:
        mask = owner_a == i
        total = float(areas[mask].sum())
        if total <= 0:
            continue
        missed = float(areas[mask & unreached].sum()) / total
        if missed <= 0.0:
            continue
        nowhere = float(areas[mask & ~anywhere].sum()) / total
        where = points[np.flatnonzero(mask & unreached)[0]]
        items.append({"unreached_fraction": round(missed, 9), "unreached_any_direction_fraction": round(nowhere, 9),
                      "kind": "no_line_of_sight" if nowhere > 0 else "undercut",
                      "hole": i in state.get("hole_axis", {}), "hole_axis": state.get("hole_axis", {}).get(i),
                      "surface": model.surface(i).kind, "location": model.ref(i), "xyz": brep.rounded(where)})
    cover = {"reach": reach, "areas": areas, "owner": owner_a, "points": points, "normals": normals, "candidates": candidates, "rotary": rotary,
             "axes": axes, "unreached": unreached}
    return {"items": items, "setup": _setup(model, cover), "directions": candidates, "rotary": rotary,
            "cover": cover}


def _setup(model: Model, cover: dict[str, Any], made_from: dict[int, Needs] | None = None,
           known: list[np.ndarray] | None = None, recess: set[int] | None = None) -> dict[str, Any]:
    """The setups: the fewest directions (greedy set cover) that reach the sampled area and make the sharp edges
    an end mill or a chamfer mill makes (``made_from``: each edge's needs, each met by any one of its directions;
    one ``known`` -- an inclined feature's own -- meets it already), the area first and the edges a direction makes breaking a tie, and the clampings they need.
    An edge made only along a direction no other need picks -- a profile's corner side-milled -- is that
    direction's setup: one more, each distinct direction once."""
    reach, areas, owner = cover["reach"], cover["areas"], cover["owner"]
    candidates = list(cover["candidates"])
    reach = dict(reach)
    needs: list[set[int]] = []
    for made in (need for needs in (made_from or {}).values() for need in needs):
        if any(float(d @ k) > SAME for d, _ in made for k in known or ()):
            continue
        need = set()
        for d, _ in made:
            k = next((k for k, c in enumerate(candidates) if float(d @ c) > SAME), None)
            if k is None:
                # a setup presenting a direction the machine lacks reaches what a straight line along it does
                k = len(candidates)
                candidates.append(d)
                reach[k] = _reach(model, cover["points"], cover["normals"], d)
            need.add(k)
        needs.append(need)
    tiny = 1e-12 * max(1.0, model.area)
    # a special cutter's recess faces (``recess``) are its: covered from the start
    given = np.isin(owner, list(recess)) if recess else np.zeros(len(areas), dtype=bool)
    covered = given.copy()
    met = [False] * len(needs)
    chosen: list[int] = []
    edges_of: dict[int, int] = {}
    while True:
        gains: dict[int, tuple[float, int]] = {}
        for k, r in reach.items():
            if k in chosen:
                continue
            area = float(areas[r & ~covered].sum())
            gains[k] = (area if area > tiny else 0.0, sum(1 for i, need in enumerate(needs) if not met[i] and k in need))
        if not gains:
            break
        k = max(gains, key=lambda key: (gains[key], -key))
        if gains[k] == (0.0, 0):
            break
        chosen.append(k)
        covered |= reach[k]
        edges_of[k] = gains[k][1]
        met = [m or k in need for m, need in zip(met, needs)]
    directions = []
    covered = given.copy()
    for k in chosen:
        new = reach[k] & ~covered
        covered |= reach[k]
        entry = {"direction": brep.rounded(candidates[k], 4),
                 "area_fraction": round(float(areas[new].sum() / areas.sum()), 4),
                 "faces": int(len(set(owner[new].tolist())))}
        if edges_of[k]:
            entry["sharp_edges"] = edges_of[k]  # the sharp edges an end mill makes along it, none before it
        directions.append(entry)
    rotary = cover["rotary"]
    largest = model.largest()
    return {"setup_count": _fixtures([candidates[k] for k in chosen], cover["axes"], rotary),
            "orientation_count": len(chosen), "directions": directions,
            "unreached_area_fraction": round(float(areas[cover["unreached"]].sum() / areas.sum()), 4),
            "rotary_axis": brep.rounded(rotary) if rotary is not None else None,
            "sampled_points": int(len(areas)), "part": model.part.name,
            "location": model.ref(largest), "xyz": model.center(largest)}


#: Of the points no machine direction reaches, each face's first few are probed over every direction
#: (``_probe``); its others try only the directions that reached those.
PROBED_PER_FACE = 2
#: A probed point tries at most this many directions that face it before it is called unreachable.
PROBE_TRIES = 32


def _probe_directions(model: Model) -> list[np.ndarray]:
    """The directions a tool might come from, most likely first: the part's own -- each plane's normal, each
    cylinder's and cone's axis both ways, by the area that names them, the first 64 --, then every 15
    degrees about each world axis, then 200 spread over the sphere."""
    weights: list[tuple[float, np.ndarray]] = []
    for i in range(1, model.n + 1):
        s = model.surface(i)
        area = model.mesh_area(i)
        if s.kind == "plane":
            weights.append((area, unit(s.normal)))
        elif s.kind in ("cylinder", "cone") and s.axis is not None:
            weights += [(area, unit(s.axis)), (area, -unit(s.axis))]
    found: list[tuple[float, np.ndarray]] = []
    for area, d in sorted(weights, key=lambda pair: -pair[0]):
        for k, (total, known) in enumerate(found):
            if float(d @ known) > SAME:
                found[k] = (total + area, known)
                break
        else:
            found.append((area, d))
    ordered = [d for _, d in sorted(found, key=lambda pair: -pair[0])][:64]
    rotations = [d for axis in np.eye(3) for d in about(axis)]  # a rotary table's, about each world axis
    for d in rotations + fibonacci(200):
        if not any(float(d @ known) > SAME for known in ordered):
            ordered.append(d)
    return ordered


def _probe(model: Model, points: np.ndarray, normals: np.ndarray, owner: np.ndarray, idx: np.ndarray,
           directions: list[np.ndarray]) -> list[tuple[np.ndarray, np.ndarray]]:
    """Which of the points ``idx`` each direction reaches: each face's first ``PROBED_PER_FACE`` of them try
    the directions in turn (at most ``PROBE_TRIES`` that face them) until one reaches them; the face's other
    points then try the directions that reached its probed ones, then the 16 that reached most. The
    directions that reach anything, each with the points it reaches."""
    probed: list[int] = []
    rest: list[int] = []
    seen: dict[int, int] = {}
    for index in idx:
        face = int(owner[index])
        seen[face] = seen.get(face, 0) + 1
        (probed if seen[face] <= PROBED_PER_FACE else rest).append(int(index))
    probed_a = np.array(probed, dtype=int)
    reached = np.zeros(len(points), dtype=bool)
    tries = np.zeros(len(points), dtype=int)
    found: list[tuple[np.ndarray, np.ndarray]] = []
    worked: dict[int, set[int]] = {}
    for k, d in enumerate(directions):
        if not len(probed_a):
            break
        pending = probed_a[~reached[probed_a] & (tries[probed_a] < PROBE_TRIES)
                           & (normals[probed_a] @ d >= -0.01)]
        if not len(pending):
            if bool(np.all(reached[probed_a] | (tries[probed_a] >= PROBE_TRIES))):
                break
            continue
        tries[pending] += 1
        hit = model.escape_all(points[pending], normals[pending], d)
        if hit.any():
            r = np.zeros(len(points), dtype=bool)
            r[pending[hit]] = True
            reached |= r
            found.append((d, r))
            for index in pending[hit]:
                worked.setdefault(int(owner[index]), set()).add(len(found) - 1)
    left = np.array([index for index in rest
                     if not any(_try(model, points, normals, index, found[slot])
                                for slot in sorted(worked.get(int(owner[index]), ())))], dtype=int)
    # then, in batches, the directions that reached most, at most 16 of them
    for slot in sorted(range(len(found)), key=lambda k: -int(found[k][1].sum()))[:16]:
        d, r = found[slot]
        pending = left[~r[left] & (normals[left] @ d >= -0.01)] if len(left) else left
        if len(pending):
            r[pending[model.escape_all(points[pending], normals[pending], d)]] = True
            left = left[~r[left]]
    return found


def _try(model: Model, points: np.ndarray, normals: np.ndarray, index: int,
         entry: tuple[np.ndarray, np.ndarray]) -> bool:
    d, r = entry
    if float(normals[index] @ d) >= -0.01 and model.escapes(points[index], normals[index], d):
        r[index] = True
        return True
    return False


def _stock_faces(model: Model) -> set[int]:
    """The planar faces on the part's box, facing out of it: the stock's own surface, which no setup cuts
    when the stock is the part's box."""
    found = set()
    for i in range(1, model.n + 1):
        s = model.surface(i)
        if s.kind != "plane":
            continue
        n = np.asarray(s.normal)
        for axis in range(3):
            if abs(n[axis]) > SAME:
                plane = float(np.asarray(s.origin)[axis])
                edge = model.box_max[axis] if n[axis] > 0 else model.box_min[axis]
                if abs(plane - edge) < 1e-6:
                    found.add(i)
    return found


def _fixtures(chosen: list[np.ndarray], axes: int, rotary: np.ndarray | None) -> int:
    """How many times the part is clamped for the chosen directions: each one on three axes; on four, all
    those square to the rotary axis are one; on five, all within the half-space above one clamping face."""
    if not chosen:
        return 0
    if axes == 3:
        return len(chosen)
    if axes == 4 and rotary is not None:
        square = [d for d in chosen if abs(float(d @ rotary)) < 1e-6]
        return len(chosen) - len(square) + (1 if square else 0)
    left = list(range(len(chosen)))
    count = 0
    while left:
        up = max(WORLD, key=lambda w: sum(float(chosen[i] @ w) > -1e-6 for i in left))
        left = [i for i in left if float(chosen[i] @ up) <= -1e-6]
        count += 1
    return count


def _allowed(state: dict[str, Any], direction: np.ndarray) -> bool:
    if state["axes"] >= 5:
        return True
    if any(float(direction @ w) > SAME for w in WORLD):
        return True
    rotary = state.get("rotary")
    return state["axes"] == 4 and rotary is not None and abs(float(direction @ rotary)) < 1e-6


def _inclination(axis: Any) -> float:
    """Degrees between an axis and the nearest world axis."""
    a = unit(axis)
    return round(math.degrees(math.acos(min(1.0, max(abs(float(a @ w)) for w in WORLD[::2])))), 4)


def _inclined(model: Model, state: dict[str, Any], holes: list[dict[str, Any]],
              pockets: list[dict[str, Any]]) -> list[np.ndarray]:
    """Marks each hole and pocket ``reachable`` (made along a direction the machine has) with its
    ``inclination_deg``, and returns the directions of those that are not, one per orientation. A hole is
    drilled along its axis, so it is reachable where the machine has that axis. A pocket is reachable there,
    or where no sharp edge between its faces is left unmade (a chamfer mill's V groove reads as a pocket on
    one flank; its tool comes along the bisector)."""
    # an edge only a setup of its own makes (a square end mill along a direction the machine lacks) leaves the
    # pocket inclined, unless the pocket is a profile along a machine direction: every face of it lies along
    # one, the tool on that axis cutting it with its side (a plate's notch turned in the plane)
    unmade = (state.get("unmakeable") or set()) | (state.get("refixtured") or set())
    edge_faces = {edge.ordinal: set(edge.faces) for edge in model.edges if edge.ordinal in unmade}
    found: list[np.ndarray] = []

    def add(d: np.ndarray, either: bool) -> None:
        if not any(float(d @ known) > SAME or (either and float(d @ known) < -SAME) for known in found):
            found.append(d)

    for hole in holes:
        a = unit(hole["axis"])
        hole["inclination_deg"] = _inclination(a)
        hole["reachable"] = bool(_allowed(state, a) or _allowed(state, -a))
        if not hole["reachable"]:
            add(unit(hole["opening"]) if hole.get("opening") else a, hole.get("opening") is None)
    for pocket in pockets:
        d = unit(pocket["axis"])
        pocket["inclination_deg"] = _inclination(d)
        faces = set(pocket["_walls"]) | set(pocket.get("_fillets") or ())
        if pocket["_floor"]:
            faces.add(pocket["_floor"])
        made = not any(both <= faces for both in edge_faces.values())
        profile = any(_allowed(state, w) and abs(float(w @ d)) < 1 - SAME and all(model.along(f, w) for f in faces)
                      for w in WORLD[::2])
        pocket["reachable"] = bool(_allowed(state, d) or made or profile)
        if not pocket["reachable"]:
            add(d, False)
    return found


# --- rays across walls and gaps --------------------------------------------------------------------------


def _across(model: Model, state: dict[str, Any], outward: bool, cap: float) -> list[dict[str, Any]]:
    skip = (state["hole_faces"] | state["void_faces"] if outward
            else state["void_faces"] | state["thread_faces"])
    found = []
    knives = state.get("knife_pairs") or set()
    per_face: dict[int, list[tuple[float, int]]] = {}
    for i in range(1, model.n + 1):
        if i in skip:
            continue
        points, normals, _ = model.samples(i)
        best = None
        hits = []
        if not len(points):
            per_face[i] = hits
            continue
        ways = normals if outward else -normals
        # across the void, a face sharing an edge with this one meets it at that edge: the gap between them
        # closes to nothing there, the void's angle (sharp_edges' to judge), never a slot's width -- a
        # dovetail's flank over its floor, a V groove's two flanks
        sharing = {other for _, other in model.neighbours(i) if other != i} if outward else set()
        for p, n, hit in zip(points, normals, model.first_all(points + ways * LIFT, ways)):
            if hit is None or hit.face == 0 or (outward and hit.face in state["hole_faces"]) \
                    or hit.face in state["thread_faces"] or hit.face in sharing:
                continue
            if float(hit.normal @ n) >= OPPOSED:
                continue
            if not outward and frozenset((i, hit.face)) in knives:
                continue  # material thinning to a knife edge: knife_edges reports it, not a wall's figure
            distance = hit.distance + LIFT
            hits.append((distance, hit.face))
            if best is None or distance < best[0]:
                best = (distance, hit.face, p)
        per_face[i] = hits
        if best is not None and best[0] < cap:
            found.append({"_face": i, "distance": best[0], "opposite": model.ref(best[1]), "_opposite": best[1],
                          "location": model.ref(i), "xyz": brep.rounded(best[2])})
    state["gaps_per_face" if outward else "walls_per_face"] = per_face
    return found


def _gaps(model: Model, state: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for item in _across(model, state, True, GAP_CAP_MM):
        item["width_mm"] = round(item.pop("distance"), 9)
        item["made_by"] = "end_mill"  # a slot cutter's where it bounds a recess only such a cutter makes (later)
        item["surface"] = model.surface(item["_face"]).kind
        items.append(item)
    return items


def _walls(model: Model, state: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for item in _across(model, state, False, WALL_CAP_MM):
        i = item["_face"]
        thickness = item.pop("distance")
        height = _height(model, i)
        item.update(thickness_mm=round(thickness, 9), height_mm=round(height, 4) if height else None,
                    height_to_thickness=round(height / thickness, 4) if height and thickness > 0 else None,
                    surface=model.surface(i).kind)
        items.append(item)
    return items


def _touching(model: Model, a: int, b: int) -> bool:
    """Whether two faces share an edge or a vertex: their exact distance is then 0, no wall's."""
    if any(other == b for _, other in model.neighbours(a)):
        return True
    ours = {tuple(np.round(v, 6)) for v in (np.array([x.X, x.Y, x.Z]) for x in model.face(a).vertices())}
    return any(tuple(np.round(np.array([x.X, x.Y, x.Z]), 6)) in ours for x in model.face(b).vertices())


def _refine(model: Model, item: dict[str, Any], outward: bool) -> None:
    """The exact thickness (or width) of a listed wall (or gap): the least distance between its face and the
    face across (``BRepExtrema_DistShapeShape``), taken where that segment leaves the face within ~45 degrees
    of its normal (into the material for a wall, the void for a gap), the two faces' normals are opposed
    there as across a wall (``OPPOSED``), and an exact ray along it from the face
    meets the face across first, at that distance: sampled rays land a few points per face and miss the
    thinnest line between two holes."""
    checkpoint()
    i, j = item.get("_face"), item.get("_opposite")
    key = "width_mm" if outward else "thickness_mm"
    if not i or not j or i == j or _touching(model, i, j):
        return
    si, sj = model.surface(i), model.surface(j)
    if si.kind == sj.kind == "plane" and abs(float(np.asarray(si.normal) @ np.asarray(sj.normal))) > SAME:
        return  # parallel planes: every ray between them is the same length, so the sampled one is exact
    if len(model.adjacent.get(i, ())) > COMPLEX_EDGES:
        return  # a face of many edges (a web around many holes): its sampled figure stands
    # the face across's surface over its (u, v) box where it has many edges: a least distance found where the
    # face is trimmed away (in one of its holes) fails the ray check below and the sampled figure stands
    segments = brep.least_segments(model.face(i), model.face(j), len(model.adjacent.get(j, ())) > COMPLEX_EDGES)
    if not segments or segments[0][0] >= float(item[key]) - 1e-6:
        return
    best = None
    for length, pa, pb, normal, there in segments:
        if best is not None and length >= best[0]:
            continue
        way = (pb - pa) / length
        if float(way @ (normal if outward else -normal)) < -OPPOSED:
            continue
        # the two faces face each other there, as the sampled ray's did: a least distance across a convex
        # round's chord (two faces square to each other, r sqrt 2 apart) is no wall
        if float(normal @ there) >= OPPOSED:
            continue
        # nothing between: the ray from the face along the segment meets the face across first (a segment
        # along a rim may graze the rim's own face: a hit within the tolerance of the far end is the far end)
        hit = model.first(pa + way * LIFT, way)
        if hit is None or (hit.face != j and abs(hit.distance + LIFT - length) > 1e-4):
            continue
        best = (length, pa)
    if best is None or best[0] >= float(item[key]):
        return
    item[key] = round(best[0], 9)
    item["xyz"] = brep.rounded(best[1])
    item["refined"] = True
    if not outward and item.get("height_mm"):
        item["height_to_thickness"] = round(item["height_mm"] / best[0], 4)


#: Points along a curved edge its material's angle is read at (``brep.edge_angles``), as printing reads it.
KNIFE_PROFILE = 17


def _knife_edges(model: Model, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Convex edges whose material angle along them falls under ``KNIFE_DEG``: the material thins to nothing
    there. A curved edge's angle is read along it, not at its middle alone (an edge where a cone meets a sphere
    runs from 63 to 42 degrees): ``angle_deg`` the least, ``length_mm`` the stretch under the limit."""
    skip = state["thread_faces"]
    items = []
    fractions = np.linspace(0.0, 1.0, KNIFE_PROFILE)
    for edge in model.edges:
        if edge.concave or edge.smooth or set(edge.faces) & skip:
            continue
        if all(model.surface(f).kind == "plane" for f in edge.faces):
            angles, points = np.full(len(fractions), float(edge.angle_deg)), None
        else:
            checkpoint()
            points, angles = brep.edge_angles(model.part, edge, fractions)
        under = np.isfinite(angles) & (angles < KNIFE_DEG - ANGLE_EPS)
        if not under.any():
            continue
        # the stretch: each of the profile's segments under the limit at either end, by its share of the length
        segments = under[:-1] | under[1:]
        stretch = float(edge.length) * float(segments.sum()) / (len(fractions) - 1)
        where = edge.midpoint if points is None or under[len(under) // 2] else points[np.flatnonzero(under)[0]]
        least = float(angles[under].min())
        if points is not None and np.isfinite(angles).any():
            # the least found between the samples about it, as printing reads a knife
            least = min(least, float(np.nanmin(brep.least_edge_angle(model.part, edge, fractions, angles)[1])))
        items.append({"angle_deg": round(least, 4), "length_mm": round(stretch, 4),
                      "edge_length_mm": round(edge.length, 4), "thickness_mm": 0.0,
                      "edge": model.part.ref("edge", edge.ordinal), "location": model.ref(edge.faces[0]),
                      "faces": [model.ref(f) for f in edge.faces], "xyz": brep.rounded(where),
                      "_pair": frozenset(edge.faces)})
    return items


def _height(model: Model, ordinal: int) -> float | None:
    """A wall's height: its extent across its root (its longest concave edge), or its narrower extent."""
    s = model.surface(ordinal)
    if s.kind != "plane":
        return None
    n = np.asarray(s.normal)
    roots = [edge for edge, _ in model.neighbours(ordinal) if edge.concave]
    if roots:
        root = max(roots, key=lambda edge: edge.length)
        h = unit(np.cross(n, np.asarray(root.tangent)))
        low, high = model.extent(ordinal, h)
        return high - low
    pts = model.outline(ordinal)
    centred = pts - pts.mean(axis=0)
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    spans = [float(np.ptp(centred @ v)) for v in vt[:2]]
    return min(spans) if spans else None


# --- sharp concave edges ---------------------------------------------------------------------------------


def _sharp_edges(model: Model, state: dict[str, Any]) -> dict[str, Any]:
    """Every sharp concave edge no rotating tool makes, with why (``reason``), the creases a ball end mill
    rounds (``made_by`` ``ball_mill``, the round's departure from the drawn edge), and the edges only a T-slot
    or dovetail cutter makes (see the module)."""
    items = []
    balls = []
    special: list[tuple[Any, str, float | None]] = []
    unmakeable: set[int] = set()
    unmade: dict[int, dict[str, Any]] = {}
    tools = state.get("tools")
    ball_radius = tools[0] / 2 if tools else BALL_RADIUS_MM
    visible: dict[tuple[int, tuple[float, ...]], bool] = {}
    made_from: dict[int, Needs] = {}
    partial: dict[int, dict[str, Any]] = {}
    notes: dict[int, dict[str, Any]] = {}
    sliver = max(SLIVER_MM, 1e-5 * model.size)

    def sees(ordinal: int, d: np.ndarray) -> bool:
        key = (ordinal, tuple(np.round(d, 6)))
        if key not in visible:
            points, normals, _ = model.samples(ordinal)
            facing = np.flatnonzero(normals @ d >= -0.01)[:8]
            visible[key] = bool(len(facing)) and bool(model.escape_all(points[facing], normals[facing], d).any())
        return visible[key]

    def cavity(faces: tuple[int, int]) -> set[int]:
        found = set(faces)
        for face in faces:
            found |= {other for edge, other in model.neighbours(face) if edge.concave}
        return found

    hole_faces = state["hole_faces"]
    ways: dict[str, int] = {}
    for edge in model.edges:
        if not edge.concave or edge.smooth:
            continue
        if edge.faces[0] in hole_faces and edge.faces[1] in hole_faces:
            ways["drill"] = ways.get("drill", 0) + 1
            continue  # a drill's point, a counterbore's or a countersink's root: the hole's own tool makes it
        if edge.faces[0] in state["thread_faces"] or edge.faces[1] in state["thread_faces"]:
            ways["tap"] = ways.get("tap", 0) + 1
            continue  # a thread's root: the tap's or the thread mill's
        if edge.length < sliver:
            ways["sliver"] = ways.get("sliver", 0) + 1
            continue  # a sliver of the model's own (micrometres long), no feature a tool makes
        try:
            n1, n2 = edge_normals(model, edge)
        except Exception:  # noqa: BLE001
            continue
        way = _way(model, state, edge, n1, n2, sees, cavity, made_from, partial, notes)
        ways[way or "none"] = ways.get(way or "none", 0) + 1
        note = notes.get(edge.ordinal, {})
        void = 360.0 - edge.angle_deg
        record = {"void_angle_deg": round(void, 4), "length_mm": round(edge.length, 4),
                  "makeable": 0, "radius_mm": 0.0, "acute": bool(void < 89.9), "reason": None, "made_by": None,
                  "between": " and ".join(model.ref(f) for f in edge.faces),
                  "tangent": brep.rounded(edge.tangent, 4),
                  "edge": model.part.ref("edge", edge.ordinal),
                  "location": model.ref(edge.faces[0]), "faces": [model.ref(f) for f in edge.faces],
                  "xyz": brep.rounded(edge.midpoint), "unreached_mm": None, "unreached": "", "_edge": edge.ordinal}
        if way in ("slot_cutter", "dovetail_cutter", "keyseat_cutter", "v_cutter"):
            special.append((edge, way, note.get("angle")))
        if way is not None and (note.get("narrow") or note.get("obtuse_root")):
            # made, and said: a slot cutter's opening narrower than its recess is tall, or a profile's obtuse
            # root side-milling leaves the tool's radius in (warnings, text-to-cad's own judgements)
            extra = {"reason": "narrow_opening", "opening_mm": round(note["narrow"][0], 4),
                     "recess_mm": round(note["narrow"][1], 4)} if note.get("narrow") else {"reason": "obtuse_root"}
            items.append({**record, **extra, "made_by": way})
        if way == "end_mill_flank":
            # made by the flank of the smallest tool, its radius leaving R (1 / sin(void / 2) - 1) in the corner
            deviation = ball_radius * (1.0 / math.sin(math.radians(void) / 2.0) - 1.0)
            balls.append({**record, "makeable": 1, "radius_mm": round(ball_radius, 4), "made_by": "end_mill_flank",
                          "deviation_mm": round(deviation, 4)})
        if way == "ball_mill":
            # made, but rounded: the ball leaves a round of its radius in the crease, departing from the
            # drawn edge by R (1 / sin(void / 2) - 1); kept in the record so nothing vanishes from it
            deviation = ball_radius * (1.0 / math.sin(math.radians(void) / 2.0) - 1.0)
            balls.append({**record, "makeable": 1, "radius_mm": round(ball_radius, 4), "made_by": "ball_mill",
                          "deviation_mm": round(deviation, 4)})
        if way is not None:
            continue
        unmakeable.add(edge.ordinal)
        if edge.ordinal in partial:
            # some way reaches part of it: the stretch none reaches is what is unmade, and where it is
            stretch = _unreached(model, edge, partial[edge.ordinal]["intervals"])
            unmade[edge.ordinal] = stretch
            record.update(stretch)
        items.append({**record, "reason": _why(model, state, edge, n1, n2, sees, cavity, edge.ordinal in partial,
                                               bool(note.get("no_way_in")))})
    # an edge a square end mill makes only along a direction the machine lacks needs a setup of its own
    refixtured = {ordinal for ordinal, needs in made_from.items()
                  if any(not any(machine for _, machine in need) for need in needs)}
    unmade_edges = [edge for edge in model.edges if edge.ordinal in unmakeable]
    return {"items": items, "balls": balls, "special": _special(model, special, unmade_edges), "unmakeable": unmakeable,
            "ways": ways, "made_from": made_from, "refixtured": refixtured, "unmade": unmade}


def _unreached(model: Model, edge: Any, intervals: list[tuple[float, float]]) -> dict[str, Any]:
    """The stretches of an edge no tool's way reaches (``_unreached_intervals``: fractions of its length): their
    length, and their place, the middle of the longest."""
    length = float(edge.length)
    inset = min(0.05, 0.1 * length)

    def along(f: float) -> float:  # a station's fraction to its place along the edge, the ends' inset its own
        return 0.0 if f <= 0.0 else length if f >= 1.0 else inset + f * (length - 2 * inset)

    total = sum(along(b) - along(a) for a, b in intervals)
    a, b = max(intervals, key=lambda pair: along(pair[1]) - along(pair[0]))
    middle = stations_at(model, edge, np.array([0.5 * (a + b)])).points[0]
    return {"unreached_mm": round(total, 4), "xyz": brep.rounded(middle)}


def _why(model: Model, state: dict[str, Any], edge: Any, n1: np.ndarray, n2: np.ndarray,
         sees: Callable[[int, np.ndarray], bool], cavity: Callable[[tuple[int, int]], set[int]],
         part_reached: bool = False, no_way_in: bool = False) -> str:
    """Why no tool of the machine makes a sharp concave edge, the first that holds: ``other_axes`` (a tool
    along a direction the machine lacks would make it, other than a square end mill's side cut, which a setup
    of its own makes: ``_way``); ``vertical_corner`` (both faces lie along a machine direction the edge runs
    along: a corner of a profile or a cavity cut along it, whatever its angle, where the tool's side leaves its
    radius); ``acute`` (its void is under 90 degrees: no tool's end or side reaches the root); ``blocked`` (a
    face is a plane square to a machine direction, but the way along it is blocked) or ``no_square_face`` (no
    face is a plane square to one). Before the last four: ``no_way_in`` (a disc cutter reaches every station but
    its disc cannot get there: a bore or an opening narrower than it) and ``blocked`` (some way reaches part of
    it, here or with more axes, an obstacle the rest: ``part_reached``)."""
    void = 360.0 - edge.angle_deg
    tangent = np.asarray(edge.tangent)
    along = next((d for d in WORLD[::2] if abs(float(tangent @ d)) > SAME and _allowed(state, d)
                  and all(model.along(f, d) for f in edge.faces)), None)
    more: dict[int, dict[str, Any]] = {}
    if state["axes"] < 5 and _way(model, {**state, "axes": 5, "beyond": state}, edge, n1, n2, sees, cavity,
                                  None, more) is not None:
        return "other_axes"
    if no_way_in:
        return "no_way_in"
    if part_reached or edge.ordinal in more:
        return "blocked"
    if along is not None:
        return "vertical_corner"
    if void < 89.9:
        return "acute"
    for normal, face in ((n1, edge.faces[0]), (n2, edge.faces[1])):
        if model.surface(face).kind == "plane" and (_allowed(state, normal) or _allowed(state, -normal)):
            return "blocked"
    return "no_square_face"


def _special(model: Model, found: list[tuple[Any, str, float | None]], unmade: list[Any] | None = None
             ) -> list[dict[str, Any]]:
    """The edges only a T-slot or a dovetail cutter makes, joined by the faces they share: one ``access`` item
    of kind ``special_cutter`` each, at the face most of them bound (an undercut, whatever line of sight
    says: such a cutter is a special tool). Its faces (``_one_cause``'s) take in those across the edges of them
    no tool makes (``unmade``): a recess's square end, which the cutter's disc leaves round, is the recess's."""
    groups: list[tuple[set[int], list[tuple[Any, str]]]] = []
    for edge, way, angle in found:
        # a cutter of no standard angle is named by its angle
        named = f"{way} of {angle:.0f} deg (no standard angle)" if angle is not None else way
        faces = set(edge.faces)
        joined = [group for group in groups if group[0] & faces]
        merged = (faces.union(*(group[0] for group in joined)), [(edge, named)] + [e for g in joined for e in g[1]])
        groups = [group for group in groups if group not in joined] + [merged]
    items = []
    for faces, edges in groups:
        edges.sort(key=lambda pair: pair[0].ordinal)
        counts: dict[int, int] = {}
        for edge, _ in edges:
            for face in edge.faces:
                counts[face] = counts.get(face, 0) + 1
        face = max(sorted(counts), key=lambda f: counts[f])
        cutters = sorted({way for _, way in edges})
        own = set(faces)
        faces = own | {f for edge in unmade or () if set(edge.faces) & own for f in edge.faces}
        items.append({"kind": "special_cutter", "cutter": " and ".join(c.replace("_", " ") for c in cutters),
                      "edge_count": len(edges), "edges": [model.part.ref("edge", e.ordinal) for e, _ in edges][:20],
                      "unreached_fraction": 0.0, "unreached_any_direction_fraction": 0.0, "hole": False,
                      "hole_axis": None, "surface": model.surface(face).kind, "location": model.ref(face),
                      "faces": [model.ref(f) for f in sorted(faces)][:20], "xyz": brep.rounded(edges[0][0].midpoint),
                      "also": "no face beyond its own edges' (_one_cause lists them)", "_faces": set(faces),
                      "_own": own})
    return items


def _station_count(edge: Any, state: dict[str, Any]) -> int:
    """How many stations an edge is tried at: ``EDGE_STATIONS`` at least, else at most the smallest tool's
    radius apart (``--tools``, else a 2.5 mm end mill's), so an obstacle a tool could not pass between two
    stations is never missed (``MAX_STATIONS`` at most)."""
    tools = state.get("tools")
    spacing = (min(tools) / 2.0) if tools else BALL_RADIUS_MM
    return int(max(EDGE_STATIONS, min(MAX_STATIONS, math.ceil(float(edge.length) / max(spacing, 1e-3)) + 1)))


def _way(model: Model, state: dict[str, Any], edge: Any, n1: np.ndarray, n2: np.ndarray,
         sees: Callable[[int, np.ndarray], bool], cavity: Callable[[tuple[int, int]], set[int]],
         directions: dict[int, Needs] | None = None,
         partial: dict[int, dict[str, Any]] | None = None,
         notes: dict[int, dict[str, Any]] | None = None) -> str | None:
    """How a rotating tool makes a sharp concave edge, or None. Each way is tried at stations along the edge
    (``_station_count``: its ends, just inside, and between, at most the smallest tool's radius apart): it makes
    the edge where it reaches every one.

    A tool's corner makes it where one face is a floor or a ceiling square to the tool's axis (an approach
    direction) and the void's angle is at least 90 degrees: an end mill where a straight line along the axis
    from that face beside the edge leaves the part. A disc cutter -- a T-slot cutter, a keyseat cutter where
    its way in is a bore beside the recess, a dovetail cutter of any acute angle with a floor -- where its
    shank along the axis finds a way out across the void beside every station (it travels along the edge),
    the disc reaching the station from it touching no material, and the disc can get there: a keyseat
    cutter's disc no wider than the bore it comes down, its shank inside it; a slot or dovetail cutter's
    plunged through an opening at least as wide as the disc somewhere along the edge, or fed in at the
    recess's own level from a side it opens to (else the edge is unmade, ``no_way_in``). A slot cutter's
    opening narrower than the recess is tall (the disc's thickness: text-to-cad's own figure) is said
    (``narrow_opening``). A chamfer mill of 60, 90 or 120 degrees makes a V along its bisector; a V of another
    angle is a special V cutter's (the angle said), or on five axes a standard mill tilted to each flank in
    turn (each flank a setup). A square end mill also makes it along any direction a setup presents (the
    part clamped to present it), each such direction one more setup: its end on one face square to that
    direction, its flank on the other, which lies along it, seen from outside; a chamfer mill along the
    bisector of a V of its angle; and an obtuse edge (a void over 90 degrees) between two planes each seen
    from outside along its own normal, each side faced from its own direction. On five simultaneous axes a
    chamfer mill on a curved V leans along it as it goes (``path_reach``); an end mill's axis stays its
    plane face's normal. An obtuse root seen end-on along a machine direction (a profile's) is said
    (``obtuse_root``): side-milled, it keeps the tool's radius. The directions an end mill or a chamfer mill
    needs go to ``directions`` (``Needs``), never an obtuse edge's; where no way reaches every
    station, the stretches none reaches (refined between stations) go to ``partial``."""
    beyond = state.get("beyond")  # only the directions a machine of these axes lacks (``_why``)

    def ok(d: np.ndarray) -> bool:
        return _allowed(state, d) and not (beyond is not None and _allowed(beyond, d))

    void = 360.0 - edge.angle_deg
    count = _station_count(edge, state)
    st = stations(model, edge, count)
    coarse = stations(model, edge, min(EDGE_STATIONS, count))
    step = min(0.05, 0.1 * edge.length)
    faces = tuple(edge.faces)
    mid_normals = (st.normals_a[count // 2], st.normals_b[count // 2])
    planes = tuple(model.surface(face).kind == "plane" for face in faces)
    note = {} if notes is None else notes.setdefault(edge.ordinal, {})
    # each way tried: its name, the directions it needs, which stations it reaches, how to try another place
    tried: list[tuple[str, Needs, np.ndarray, Callable[[Stations], np.ndarray]]] = []

    def normals_of(s: Stations) -> tuple[np.ndarray, np.ndarray]:
        return s.normals_a, s.normals_b

    def inward(s: Stations, k: int, a: int) -> np.ndarray:
        """Along face ``a`` away from the edge, square to it, at station ``k``."""
        normals = normals_of(s)
        na, nb = normals[a][k], normals[1 - a][k]
        return unit(nb - na * float(nb @ na))

    def dense(fn: Callable[[Stations], np.ndarray]) -> np.ndarray:
        """``fn`` at every station, tried first at the edge's ends and middle, then the coarse ones: a way none
        of those reaches is spared the rest (a disc cutter's walk costs rays a station)."""
        if not fn(stations(model, edge, 3)).any():
            return np.zeros(count, dtype=bool)
        if count > len(coarse.points) and not fn(coarse).any():
            return np.zeros(count, dtype=bool)
        return fn(st)

    def floor_reach(a: int, d: np.ndarray) -> Callable[[Stations], np.ndarray]:
        """Per station: a straight line along ``d`` from face ``a`` just beside the edge leaves the part (just
        off the edge, nearer still where the face is narrower than the step)."""
        def fn(s: Stations) -> np.ndarray:
            n = len(s.points)
            reached = np.zeros(n, dtype=bool)
            across = np.array([inward(s, k, a) for k in range(n)]).reshape(-1, 3)
            for off in (step, step / 20):
                left = np.flatnonzero(~reached)
                if not len(left):
                    break
                reached[left] = model.escape_all(s.points[left] + across[left] * off, normals_of(s)[a][left], d)
            return reached
        return fn

    def path_reach(s: Stations, bases: np.ndarray) -> np.ndarray:
        """Per station, on five simultaneous axes: a straight line from the station (lifted along its base
        direction) leaves the part along that direction leaned along the edge by one of ``LEANS_DEG``, the
        leans chosen station to station turning by no more than ``LEAN_STEP_DEG`` -- the tool's direction a
        continuous path along the edge. Where no path runs on, the station it breaks at is unreached."""
        leans = np.radians(np.array(LEANS_DEG))
        n = len(s.points)
        ok_at = np.zeros((n, len(leans)), dtype=bool)
        for j, lean in enumerate(leans):
            ways = np.array([unit(math.cos(lean) * b + math.sin(lean) * t) for b, t in zip(bases, s.tangents)])
            ok_at[:, j] = [_allowed(state, w) and model.escapes(o, b, w) for o, b, w in zip(s.points, bases, ways)]
        reached = np.zeros(n, dtype=bool)
        live = np.zeros(len(leans), dtype=bool)
        near = np.abs(leans[:, None] - leans[None, :]) <= math.radians(LEAN_STEP_DEG) + 1e-9
        for k in range(n):
            live = ok_at[k] & (near[live].any(axis=0) if live.any() and k else np.ones(len(leans), dtype=bool))
            if not live.any():
                live = np.zeros(len(leans), dtype=bool)
                continue
            reached[k] = True
        return reached

    def bore_of(bores: list[int], d: np.ndarray) -> tuple[np.ndarray, np.ndarray, float] | None:
        for b in bores:
            surface = model.surface(b)
            if sees(b, d) and surface.origin is not None and surface.radius:
                return np.asarray(surface.origin, dtype=float), unit(surface.axis), float(surface.radius)
        return None

    def shank_reach(a: int, d: np.ndarray, kind: str, bore: tuple[np.ndarray, np.ndarray, float] | None = None
                    ) -> tuple[Callable[[Stations], np.ndarray], dict[str, Any]]:
        """Per station: a disc cutter on a shank along ``d`` reaches it from across the void -- at some place on
        face ``a``'s side of the void, up to its far side, the shank (``SHANK_RADIUS_MM`` about its axis)
        leaves the part along ``d`` and the disc that reaches the station from it, just off the face, touches no
        material (slid back along the edge past its ends) -- and the disc can be there: a keyseat cutter's
        (``bore``) no wider than the bore and its shank inside it. ``info`` gathers, from the stations tried,
        whether a slot or dovetail cutter's disc could get in (``entry``: plunged through an opening as wide
        as itself along ``d``, or fed at its own level from a side the recess opens to) and, for a slot
        cutter, the narrowest opening across the void against the recess's height (``narrow``)."""
        info: dict[str, Any] = {"entry": False, "every": True, "narrow": None}

        def fits(centre: np.ndarray, radius: float, way: np.ndarray, side: np.ndarray, lift: np.ndarray) -> bool:
            """A disc of ``radius`` at ``centre`` comes straight in along the axis: lines along it from its rim
            leave the part (the opening along the axis is as wide as the disc there)."""
            turns = np.linspace(0, 2 * math.pi, 8, endpoint=False)
            rim = np.array([centre + radius * (math.cos(t) * way + math.sin(t) * side) for t in turns])
            return bool(model.escape_all(rim, np.tile(lift, (len(rim), 1)), d).all())

        def fed(centre: np.ndarray, radius: float, way: np.ndarray, side: np.ndarray) -> bool:
            """A disc of ``radius`` at ``centre`` is fed in at its own level from a side the recess opens to."""
            for t in np.linspace(0, 2 * math.pi, 8, endpoint=False):
                u = math.cos(t) * way + math.sin(t) * side
                across = unit(np.cross(d, u))
                band = (centre, centre + 0.9 * radius * across, centre - 0.9 * radius * across)
                if not any(model.blocked(point, u) for point in band):
                    return True
            return False

        def fn(s: Stations) -> np.ndarray:
            n = len(s.points)
            reached = np.zeros(n, dtype=bool)
            normals = normals_of(s)
            for k in range(n):
                way = inward(s, k, a)
                side = unit(np.cross(d, way))
                start = s.points[k] + normals[a][k] * LIFT
                hit = model.first(start + way * step, way)
                span = hit.distance + step if hit is not None else model.size
                offsets = np.linspace(step, span - step, max(2, min(WALK_STEPS, int(span / 0.05))))
                lifted = np.tile(normals[a][k], (len(offsets), 1))
                out = model.escape_all(start + way * offsets[:, None], lifted, d)
                tangent = s.tangents[k]
                ends = (float((st.points @ tangent).min()), float((st.points @ tangent).max()))
                for j in np.flatnonzero(out)[:SHANK_TRIES]:
                    centre = start + way * offsets[j]
                    radius = float(offsets[j]) - step
                    shank = min(SHANK_RADIUS_MM, radius / 2)
                    ring = np.array([centre - shank * way, centre + shank * way])
                    if not model.escape_all(ring, np.tile(normals[a][k], (2, 1)), d).all():
                        continue
                    ring_at = np.array([(math.cos(t) * way + math.sin(t) * side) * radius
                                        for t in np.linspace(0, 2 * math.pi, DISC_POINTS, endpoint=False)])
                    place = centre
                    if model.solid(centre + ring_at).any():
                        # past the edge's ends the disc meets what bounds them (that end's corner to judge):
                        # slid back along the edge, clear of both ends, it must touch nothing, its shank out
                        along = (centre + ring_at) @ tangent
                        low, high = ends[0] - float(along.min()), float(along.max()) - ends[1]
                        if low > 0 and high > 0:
                            continue
                        place = centre + tangent * (max(low, 0.0) - max(high, 0.0))
                        shifted = np.array([place - shank * way, place + shank * way])
                        if not model.escape_all(shifted, np.tile(normals[a][k], (2, 1)), d).all() \
                                or model.solid(place + ring_at).any():
                            continue
                    reached[k] = True
                    # can the disc get here? The least disc reaching the station from the opening (its shank of
                    # no breadth, at the opening's near side): geometry alone, no figure of text-to-cad's
                    first = int(np.argmax(out))
                    shut = np.flatnonzero(~out[first:])
                    last = first + (int(shut[0]) - 1 if len(shut) else len(out) - 1 - first)

                    def edge_at(inside: float, outside: float, lift: np.ndarray = normals[a][k]) -> float:
                        # the opening's side between a place it is open and one it is not, to a micrometre
                        for _ in range(24):
                            if abs(outside - inside) < 1e-3:
                                break
                            middle = 0.5 * (inside + outside)
                            if model.escapes(start + way * middle, lift, d):
                                inside = middle
                            else:
                                outside = middle
                        return inside

                    near_side, far_side = float(offsets[first]), float(offsets[last])
                    pitch = float(offsets[1] - offsets[0]) if len(offsets) > 1 else 0.0
                    tall = model.first(start + way * step, normals[a][k]) if kind == "slot" else None

                    def close(width: float, least: float) -> bool:
                        # a comparison a walk's step could turn: the opening's sides found exactly first
                        margins = [abs(width - 2.0 * least)]
                        if tall is not None:
                            margins.append(abs(width - tall.distance))
                        return min(margins) < 3.0 * pitch

                    narrowing = tall is not None and far_side - near_side < tall.distance + 3.0 * pitch
                    if close(far_side - near_side, near_side - step) or narrowing:
                        # exact where a verdict turns on it, or a narrow opening is to be said in millimetres
                        if first:
                            near_side = edge_at(near_side, float(offsets[first - 1]))
                        if last + 1 < len(offsets):
                            far_side = edge_at(far_side, float(offsets[last + 1]))
                    least = near_side - step
                    width = far_side - near_side
                    if bore is not None:
                        # down the bore: the disc no wider than the bore, so a station at most twice its radius
                        # from its axis
                        origin, axis, bore_radius = bore
                        rel = s.points[k] - origin
                        here = float(np.linalg.norm(rel - axis * float(rel @ axis))) <= 2.0 * bore_radius + 1e-6
                        info["entry"] = info["entry"] or here
                        info["every"] = info["every"] and here
                    elif not info["entry"]:
                        middle = start + way * (0.5 * (near_side + far_side))
                        info["entry"] = (width >= 2.0 * least - 1e-6 and fits(middle, least, way, side, normals[a][k])) \
                            or fed(place, radius, way, side)
                    if kind == "slot":
                        if tall is not None and width < tall.distance - 1e-6:
                            known = info["narrow"]
                            if known is None or width < known[0]:
                                info["narrow"] = (float(width), float(tall.distance))
                    break
            return reached

        return fn, info

    def made(way: str, needs: Needs | None = None) -> str:
        # an obtuse edge needs no direction of its own: it is made in the setups that make its two faces, which
        # the setups' cover counts; a square corner (an end mill's end and flank) or a V's chamfer mill does
        if directions is not None and needs and void <= OBTUSE_DEG:
            directions[edge.ordinal] = needs
        if void > OBTUSE_DEG and all(planes) and way in ("end_mill", "chamfer_mill") and _end_on(model, state, edge):
            note["obtuse_root"] = True
        return way

    def disc(way: str, kind: str, a: int, d: np.ndarray, bore: Any = None) -> str | None:
        fn, info = shank_reach(a, d, kind, bore)
        reached = dense(fn)
        if reached.all() and info["entry"] and (bore is None or info["every"]):
            if info["narrow"] is not None:
                note["narrow"] = info["narrow"]
            # along its axis, either way (a tool's axis, its recess covered by the setups: ``_setup``'s
            # ``recess``)
            return made(way, [[(d, ok(d)), (-d, ok(-d))]])
        if reached.all():
            note["no_way_in"] = True  # reached at every station, but no disc can get there
            reached = np.zeros(count, dtype=bool)
        tried.append((way, [], reached, lambda s, fn=fn: fn(s)))
        return None

    if void >= 89.9:
        # an end mill first, from either face: its end on that face (a plane square to the tool's axis), seen
        # from outside along the axis. Along a direction the machine has, any void of 90 degrees or more; along
        # any other -- a setup the part is clamped in to present it, one more setup -- a square end mill's
        # end and flank: the other face lies along the axis (a profile's corner side-milled, whatever the turn)
        full: list[tuple[np.ndarray, bool]] = []
        for a in (0, 1):
            if not planes[a]:
                continue  # a floor or a ceiling is a plane: a curved face's normal at one point is no floor's
            na = mid_normals[a]
            machine = ok(na)
            if not machine and (beyond is not None or not model.along(faces[1 - a], na)):
                continue
            # an end mill's end on a plane fixes its axis to the plane's normal, on five axes too
            fn = floor_reach(a, na)
            reached = fn(st)
            if reached.all():
                full.append((na, machine))
            tried.append(("end_mill", [[(na, machine)]], reached, fn))
        if full:
            return made("end_mill", [full])
        # a keyseat cutter: the recess has a floor and a ceiling square to an approach direction, its way in a
        # bore beside it (a concave cylinder along the direction it meets by a convex edge) seen along it
        recess = cavity(faces)
        for a in (0, 1):
            if not planes[a]:
                continue
            na = mid_normals[a]
            ceiling = any(model.surface(f).kind == "plane"
                          and float(np.asarray(model.surface(f).normal) @ na) < -SAME for f in recess)
            if not ceiling:
                continue
            bores = sorted({other for f in recess for e, other in model.neighbours(f)
                            if not e.concave and not e.smooth and other not in recess
                            and model.surface(other).kind == "cylinder" and model.surface(other).concave
                            and abs(float(unit(model.surface(other).axis) @ na)) > SAME})
            for d in (na, -na):
                bore = bore_of(bores, d) if ok(d) else None
                if bore is not None and disc("keyseat_cutter", "keyseat", a, d, bore):
                    return "keyseat_cutter"
        for a in (0, 1):
            if planes[a]:
                for d in (mid_normals[a], -mid_normals[a]):
                    if ok(d) and disc("slot_cutter", "slot", a, d):
                        return "slot_cutter"
    if void < 89.9:
        # a dovetail cutter makes an acute angle with a floor: 45 and 60 degrees are standard, another angle a
        # cutter ground to it (said)
        for a in (0, 1):
            na = mid_normals[a]
            # its floor square to one of the part's own axes (a V's tilted flank is no dovetail's floor)
            square = any(abs(float(na @ w)) > SAME for w in WORLD[::2])
            if planes[a] and square and ok(na) and disc("dovetail_cutter", "dovetail", a, na):
                if not any(abs(void - angle) < 0.5 for angle in DOVETAILS):
                    note["angle"] = void
                return "dovetail_cutter"
    bisectors = np.array([unit(x + y) for x, y in zip(st.normals_a, st.normals_b)])
    bisector = bisectors[count // 2]
    # a chamfer mill along one axis makes a V whose bisector keeps to it; five axes tilt it along the edge
    straight_v = bool(np.all(bisectors @ bisector > SAME))
    standard = any(abs(void - angle) < 0.5 for angle in V_MILLS)
    v_mill = standard and (straight_v or state["axes"] >= 5)

    def chamfer_fn(s: Stations) -> np.ndarray:
        bis = np.array([unit(x + y) for x, y in zip(s.normals_a, s.normals_b)]).reshape(-1, 3)
        if straight_v:
            # a straight V's bisector is one direction: five axes present it as three do, with no lean
            return model.escape_all(s.points, bis, bisector)
        # a curved V's turns along it: on five axes the mill follows it, leaning as it goes
        return path_reach(s, bis)

    if v_mill and (ok(bisector) or not straight_v):
        needs = [[(bisector, True)]] if straight_v else []
        reached = chamfer_fn(st)
        if reached.all():
            return made("chamfer_mill", needs)
        tried.append(("chamfer_mill", needs, reached, chamfer_fn))
    mid = np.asarray(edge.midpoint)
    shoulder = next((angle for angle in V_MILLS if abs(void - (180.0 - angle / 2.0)) < 0.5), None)
    if shoulder is not None:
        # a chamfer mill's shoulder, where its cone meets its body: one face along the mill's axis (a wall),
        # the other the cone's (a chamfer looking along the axis), the mill coming in along it
        for face, other in ((faces[0], n2), (faces[1], n1)):
            for d in WORLD:
                if ok(d) and abs(float(other @ d) - math.sin(math.radians(shoulder / 2.0))) < CONE_TOLERANCE \
                        and model.along(face, d) and model.escapes(mid, bisector, d):
                    return made("chamfer_mill")
    if void >= BALL_VOID_DEG - 1e-6:  # a regular 12-gon's corners are 150 degrees, a rounding either side
        # a ball end mill contours the crease along any direction both faces look along
        for d in (bisector, *WORLD):
            if ok(d) and float(n1 @ d) > LOOKS_ALONG and float(n2 @ d) > LOOKS_ALONG \
                    and model.escapes(mid, bisector, d):
                return made("ball_mill")
        # a corner this open along the tool's axis (a faceted arc's, a many-sided pocket's) is the end mill's
        # flank's: its radius leaves a residue of R (1 / sin(void / 2) - 1) in it, 0.011 mm for a 2.5 mm mill at 166
        # degrees -- made, its residue said (``deviation_mm``)
        for d in WORLD:
            if ok(d) and bool(np.all(np.abs(st.tangents @ d) > SAME)) and all(model.along(f, d) for f in faces) \
                    and (model.escapes(mid, bisector, d) or model.escapes(mid, bisector, -d)):
                return made("end_mill_flank")
    if not standard and straight_v and all(planes) and void <= OBTUSE_DEG:
        if state["axes"] >= 5 and void >= min(V_MILLS) - 0.5:
            # a standard chamfer mill tilted to each flank in turn: its cone's side on that flank, its other
            # side inside the V; each flank a setup of its own
            needs = []
            reached = np.ones(count, dtype=bool)
            half = math.radians(min(V_MILLS) / 2.0)
            for a in (0, 1):
                # the cone's side along the flank, out of the V: its axis turned from the flank toward the void
                tilt = unit(math.cos(half) * inward(st, count // 2, a) + math.sin(half) * mid_normals[a])
                reached &= model.escape_all(st.points, bisectors, tilt)
                needs.append([(tilt, ok(tilt))])
            if reached.all():
                return made("chamfer_mill", needs)
        if ok(bisector) or beyond is None:
            # a V of no standard angle: a V cutter ground to it, along its bisector (said, with its angle)
            reached = model.escape_all(st.points, bisectors, bisector)
            if reached.all():
                note["angle"] = void
                return made("v_cutter", [[(bisector, ok(bisector))]])
    if beyond is None:
        # along the directions a setup presents: an obtuse edge between two planes faced each from its own side,
        # and a chamfer mill along a V's bisector
        if void > OBTUSE_DEG and all(planes):
            fns = [floor_reach(a, mid_normals[a]) for a in (0, 1)]
            needs = [[(mid_normals[a], ok(mid_normals[a]))] for a in (0, 1)]

            def both(s: Stations, fns: list = fns) -> np.ndarray:
                return fns[0](s) & fns[1](s)

            reached = both(st)
            if reached.all():
                return made("end_mill", needs)
            tried.append(("end_mill", needs, reached, both))
        if v_mill and straight_v and all(planes) and not ok(bisector):
            reached = chamfer_fn(st)
            if reached.all():
                return made("chamfer_mill", [[(bisector, False)]])
            tried.append(("chamfer_mill", [[(bisector, False)]], reached, chamfer_fn))
    # no one way reaches every station: end mills and chamfer mills that do between them make the edge, each
    # a setup; else the stretches some way reaches are the edge's made part, the rest unmade
    union = np.zeros(count, dtype=bool)
    for _, _, reached, _ in tried:
        union |= reached
    if tried and union.all():
        picked: Needs = []
        ways: list[str] = []
        covered = np.zeros(count, dtype=bool)
        for way, needs, reached, _ in sorted((t for t in tried if t[1]), key=lambda t: -int(t[2].sum())):
            if (reached & ~covered).any():
                picked += needs
                ways.append(way)
                covered |= reached
        if covered.all():
            return made(ways[0], picked)
    elif partial is not None and union.any():
        partial[edge.ordinal] = {"intervals": _unreached_intervals(model, edge, union, [t[3] for t in tried])}
    return None


def _end_on(model: Model, state: dict[str, Any], edge: Any) -> bool:
    """Whether an edge is a profile's root seen end-on along a machine direction: it runs along one, both its
    faces lie along it, and a line along it from beside the edge leaves the part (a tool along it would
    side-mill both faces, its radius left in the root)."""
    tangent = np.asarray(edge.tangent)
    for d in WORLD:
        if float(tangent @ d) > SAME and _allowed(state, d) and all(model.along(f, d) for f in edge.faces):
            n1, n2 = edge_normals(model, edge)
            if model.escapes(np.asarray(edge.midpoint), unit(n1 + n2), d):
                return True
    return False


def _unreached_intervals(model: Model, edge: Any, reached: np.ndarray,
                         ways: list[Callable[[Stations], np.ndarray]]) -> list[tuple[float, float]]:
    """The stretches (fractions of the edge, 0 to 1) no way reaches: between a reached station and an
    unreached one the boundary is found by bisection (``ways`` tried at each place, any reaching it) to
    a tenth of a millimetre (``UNREACHED_TOLERANCE`` of the edge at most)."""
    n = len(reached)
    fractions = np.linspace(0.0, 1.0, n)
    length = max(float(edge.length), 1e-9)
    tolerance = min(0.1 / length, UNREACHED_TOLERANCE)

    def reach_at(f: float) -> bool:
        place = stations_at(model, edge, np.array([f]))
        return any(bool(np.asarray(way(place))[0]) for way in ways)

    def boundary(lo: float, hi: float, lo_reached: bool) -> float:
        while hi - lo > tolerance:
            middle = 0.5 * (lo + hi)
            if reach_at(middle) == lo_reached:
                lo = middle
            else:
                hi = middle
        return 0.5 * (lo + hi)

    intervals = []
    k = 0
    while k < n:
        if reached[k]:
            k += 1
            continue
        first = k
        while k < n and not reached[k]:
            k += 1
        begin = 0.0 if first == 0 else boundary(fractions[first - 1], fractions[first], True)
        finish = 1.0 if k == n else boundary(fractions[k - 1], fractions[k], False)
        intervals.append((begin, finish))
    return intervals


def _vertex_keys(shape: Any) -> set[tuple[float, ...]]:
    return {tuple(np.round([v.X, v.Y, v.Z], 6)) for v in shape.vertices()}


def _fold(model: Model, items: list[dict[str, Any]], corners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sharp edges left once those beside a reported corner -- the corner's run through the small edge
    rounds at its ends -- are folded into that corner (``folded_edges``). An edge is the corner's run where it
    shares a vertex with the corner and a face with it or with a round tangent to its faces, and either runs
    along the corner's axis or is a face of such a round and under twice its radius long. A floor-to-wall
    edge (two planes, across the axis) is never folded: no tool of the machine may make it."""
    if not corners or not items:
        return items
    edges = model.part.edges()
    edge_of = {edge.ordinal: edge for edge in model.edges}
    near = []
    for corner in corners:
        if corner.get("_edge"):
            shape = edges[corner["_edge"] - 1]
            faces = set(edge_of[corner["_edge"]].faces)
        else:
            ordinal = int(corner["location"].rsplit(" ", 1)[1])
            shape, faces = model.face(ordinal), {ordinal}
        rounds: dict[int, float] = {}
        smooth = set()
        for face in faces:
            for edge, other in model.neighbours(face):
                if not edge.smooth:
                    continue
                smooth.add(other)
                s = model.surface(other)
                radius = s.minor_radius if s.kind == "torus" else s.radius if s.kind in ("cylinder", "sphere") else None
                if radius and other not in faces:
                    rounds[other] = float(radius)
        near.append((corner, _vertex_keys(shape), faces | smooth, rounds, np.asarray(corner["axis"], dtype=float)))

    def run(edge: Any, rounds: dict[int, float], axis: np.ndarray) -> bool:
        if abs(float(np.asarray(edge.tangent) @ axis)) > SAME:
            return True
        return any(face in rounds and edge.length < 2.0 * rounds[face] for face in edge.faces)

    kept = []
    for item in items:
        edge = edge_of[item["_edge"]]
        keys = _vertex_keys(edges[edge.ordinal - 1])
        owner = next((corner for corner, vertices, faces, rounds, axis in near
                      if keys & vertices and set(edge.faces) & faces and run(edge, rounds, axis)), None)
        if owner is None:
            kept.append(item)
        else:
            owner.setdefault("folded_edges", []).append(item["edge"])
    return kept


# --- pockets and their corners ---------------------------------------------------------------------------


def _pockets(model: Model, state: dict[str, Any], only: set[int] | None = None) -> dict[str, Any]:
    """The pockets, through cavities and their internal corners (the module); ``only``: the faces they may be
    made of (a turned part's live-tooling features), else every face."""
    hole_faces = state["hole_faces"]
    if only is not None:
        hole_faces = hole_faces | {i for i in range(1, model.n + 1) if i not in only}
    tools = state["tools"]
    unmakeable = state["unmakeable"]
    gaps = state.get("gaps_per_face", {})
    edge_of = {edge.ordinal: edge for edge in model.edges}
    pockets, corners = [], []
    seen_corners: set[Any] = set()
    for floor in range(1, model.n + 1):
        s = model.surface(floor)
        if s.kind != "plane" or floor in hole_faces or floor in state["void_faces"]:
            continue
        d = unit(s.normal)
        walls: set[int] = set()
        fillets: set[int] = set()
        for edge, other in model.neighbours(floor):
            if other in hole_faces or other == floor:
                continue
            if edge.concave and model.along(other, d):
                walls.add(other)
            elif edge.smooth and model.surface(other).concave is not False and not model.along(other, d) \
                    and model.surface(other).kind != "plane":
                fillets.add(other)
        for fillet in fillets:
            for edge, other in model.neighbours(fillet):
                if edge.smooth and other not in hole_faces and model.along(other, d):
                    walls.add(other)
        if not walls:
            continue
        points, normals, _ = model.samples(floor)
        if not len(points) or not model.escape_all(points[:8], normals[:8], d).any():
            continue  # no tool reaches it end-on: a pocket's wall, not a floor
        frontier = list(walls)
        while frontier:
            wall = frontier.pop()
            for edge, other in model.neighbours(wall):
                if other in walls or other in hole_faces or other == floor:
                    continue
                if (edge.concave or edge.smooth) and abs(float(np.asarray(edge.tangent) @ d)) > SAME \
                        and model.along(other, d):
                    walls.add(other)
                    frontier.append(other)
        level = model.extent(floor, d)[1]
        rim = max(model.extent(w, d)[1] for w in walls)
        top = model.part_extent(d)[1]
        depth = rim - level
        if depth <= 1e-6:
            continue
        outer = model.face(floor).outer_wire()
        boundary = [model.part.edge_ordinal(e) for e in outer.edges()]
        lengths = {o: edge_of[o].length for o in boundary if o in edge_of}
        open_length = sum(length for o, length in lengths.items()
                          if not (edge_of[o].concave or (edge_of[o].smooth and
                                                          (set(edge_of[o].faces) - {floor}) & fillets)))
        total = sum(lengths.values()) or 1.0
        width, pair = _narrowest(walls, gaps)
        closed = open_length / total < 1e-3
        kind = "closed" if closed else ("slot" if width is not None else "open")
        root = None
        for fillet in fillets:
            fs = model.surface(fillet)
            radius = fs.minor_radius if fs.kind == "torus" else fs.radius
            if radius is not None:
                root = radius if root is None else min(root, radius)
        pocket = {"_floor": floor, "_walls": walls, "_fillets": fillets, "kind": kind, "depth_mm": round(depth, 4),
                  "depth_from_top_mm": round(top - level, 4),
                  "width_mm": round(width, 4) if width is not None else None,
                  "depth_to_width": round(depth / width, 9) if width else None,
                  "open_boundary_fraction": round(open_length / total, 4),
                  "floor_radius_mm": round(root, 4) if root is not None else None,
                  "axis": brep.rounded(d, 4), "aligned": _allowed({"axes": 3}, d),
                  "wall_count": len(walls), "floor": model.ref(floor),
                  # a pocket's figure that fails is its width, between these two walls: the place to fix
                  "location": model.ref(pair[0]) if pair else model.ref(floor),
                  "width_faces": [model.ref(f) for f in pair] if pair else None,
                  "faces": [model.ref(f) for f in sorted(walls | fillets | {floor})][:40],
                  "xyz": model.center(floor)}
        pockets.append(pocket)
        # in-plane corners: concave cylinders along the axis, and sharp concave edges along it
        for wall in walls:
            ws = model.surface(wall)
            if ws.kind == "cylinder" and ws.concave and ("face", wall) not in seen_corners:
                seen_corners.add(("face", wall))
                low, high = model.extent(wall, d)
                corners.append(_corner(model, float(ws.radius), high - low, top - low, tools, d, model.ref(floor),
                                       model.ref(wall), [model.ref(wall)], model.center(wall), None))
        for wall in walls:
            for edge, other in model.neighbours(wall):
                if other not in walls or edge.smooth or not edge.concave or ("edge", edge.ordinal) in seen_corners:
                    continue
                if abs(float(np.asarray(edge.tangent) @ d)) <= SAME:
                    continue
                if unmakeable is not None and edge.ordinal not in unmakeable:
                    continue
                seen_corners.add(("edge", edge.ordinal))
                shape = model.part.edges()[edge.ordinal - 1]
                points = np.array([[v.X, v.Y, v.Z] for v in shape.vertices()])
                low, high = float((points @ d).min()), float((points @ d).max())
                corners.append(_corner(model, 0.0, high - low, top - low, tools, d, model.ref(floor),
                                       model.ref(edge.faces[0]),
                                       [model.ref(f) for f in edge.faces], brep.rounded(edge.midpoint),
                                       edge.ordinal, state.get("unmade")))
    # an open step reads two ways: its floor with the wall rising from it, or the wall end-on with the floor
    # beside it; the shallower reading is the cut
    by_floor = {pocket["_floor"]: pocket for pocket in pockets}
    dropped = set()
    for pocket in pockets:
        for wall in pocket["_walls"]:
            other = by_floor.get(wall)
            if other is None or pocket["_floor"] not in other["_walls"]:
                continue
            deeper = max((pocket, other), key=lambda p: (p["depth_mm"], p["_floor"]))
            dropped.add(deeper["_floor"])
    kept = [pocket for pocket in pockets if pocket["_floor"] not in dropped]
    refs = {model.ref(floor) for floor in dropped}
    corners = [corner for corner in corners if corner["pocket"] not in refs]
    claimed = {face for pocket in pockets for face in pocket["_walls"] | pocket["_fillets"] | {pocket["_floor"]}}
    if only is not None:
        claimed |= {i for i in range(1, model.n + 1) if i not in only}
    through, through_corners = _through(model, state, claimed, gaps)
    return {"pockets": kept + through, "corners": corners + through_corners}


def _narrowest(walls: set[int], gaps: dict[int, list[tuple[float, int]]]) -> tuple[float | None, tuple[int, int] | None]:
    """The narrowest sampled gap between two of the walls, and the two walls."""
    width, pair = None, None
    for wall in walls:
        for distance, other in gaps.get(wall, []):
            if other in walls and (width is None or distance < width):
                width, pair = distance, (wall, other)
    return width, pair


def _through(model: Model, state: dict[str, Any], claimed: set[int],
             gaps: dict[int, list[tuple[float, int]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Cavities with no floor -- windows, through slots, cut-outs --, along each
    world axis: faces lying along it joined by concave or tangent edges along it, none a floor pocket's, none
    meeting a plane square to the axis by a concave edge (a floor or an end wall closes it), closed around the
    axis (``_open_across``), with a corner: a concave cylinder along it that is no floor's root fillet (a
    smooth neighbour of it that is a plane seen end-on along its own normal would make it one: a bull nose
    cuts that), or a sharp concave edge along it. Each cavity's corners are its concave cylinders and the
    sharp edges along it no tool makes (radius 0); its depth is its walls' extent along the axis, taken from
    the side that reaches it shallowest."""
    skip = state["hole_faces"] | state["void_faces"] | state["thread_faces"] | claimed
    tools = state["tools"]
    pockets: list[dict[str, Any]] = []
    corners: list[dict[str, Any]] = []
    end_on: dict[int, bool] = {}

    def seen_end_on(face: int) -> bool:
        if face not in end_on:
            s = model.surface(face)
            n = unit(s.normal) if s.kind == "plane" else None
            if n is None or not _allowed(state, n):
                end_on[face] = False
            else:
                points, normals, _ = model.samples(face)
                end_on[face] = bool(len(points)) and bool(model.escape_all(points[:8], normals[:8], n).any())
        return end_on[face]

    unmakeable = state.get("unmakeable")
    for d in (np.array([0.0, 0.0, 1.0]), np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])):
        grouped: set[int] = set()
        for seed in range(1, model.n + 1):
            if seed in skip or seed in grouped or not model.along(seed, d):
                continue
            group, frontier = {seed}, [seed]
            while frontier:
                face = frontier.pop()
                for edge, other in model.neighbours(face):
                    if other in group or other in skip or not (edge.concave or edge.smooth):
                        continue
                    if abs(float(np.asarray(edge.tangent) @ d)) > SAME and model.along(other, d):
                        group.add(other)
                        frontier.append(other)
            grouped |= group
            if any(edge.concave and model.surface(other).kind == "plane"
                   and abs(float(np.asarray(model.surface(other).normal) @ d)) > SAME
                   for face in group for edge, other in model.neighbours(face)):
                continue  # closed at an end along the axis: a floor or an end wall, not a through cut
            round_corners = [face for face in sorted(group)
                             if model.surface(face).kind == "cylinder" and model.surface(face).concave
                             and not any(edge.smooth and seen_end_on(other) for edge, other in model.neighbours(face))]
            # the sharp concave edges along the axis between its faces: its sharp corners where no tool makes
            # them, the run of a T-slot's or a dovetail's cutter where one does
            along_edges = {edge.ordinal: edge for face in group for edge, other in model.neighbours(face)
                           if other in group and other != face and edge.concave and not edge.smooth
                           and abs(float(np.asarray(edge.tangent) @ d)) > SAME}
            sharp_corners = [edge for _, edge in sorted(along_edges.items())
                             if unmakeable is None or edge.ordinal in unmakeable]
            if not round_corners and not along_edges:
                continue
            if _open_across(model, group, d):
                continue  # a channel open to a side (a valley, a groove): its tool comes from that side
            sides = []
            for sign in (1.0, -1.0):
                way = d * sign
                low = min(model.extent(face, way)[0] for face in group)
                high = max(model.extent(face, way)[1] for face in group)
                sides.append((model.part_extent(way)[1] - low, high - low, way))
            reach, depth, way = min(sides, key=lambda side: side[0])
            width, pair = _narrowest(group, gaps)
            first = round_corners[0] if round_corners else min(group)
            ref = model.ref(pair[0]) if pair else model.ref(first)
            pockets.append({"_floor": None, "_walls": group, "kind": "through", "depth_mm": round(depth, 4),
                            "depth_from_top_mm": round(reach, 4),
                            "width_mm": round(width, 4) if width is not None else None,
                            "depth_to_width": round(depth / width, 9) if width else None,
                            "open_boundary_fraction": None, "floor_radius_mm": None,
                            "axis": brep.rounded(way, 4), "aligned": True, "wall_count": len(group), "floor": None,
                            "location": ref, "width_faces": [model.ref(f) for f in pair] if pair else None,
                            "faces": [model.ref(f) for f in sorted(group)][:40], "xyz": model.center(first)})
            for face in round_corners:
                low, high = model.extent(face, way)
                corners.append(_corner(model, float(model.surface(face).radius), high - low,
                                       model.part_extent(way)[1] - low, tools, way, ref, model.ref(face),
                                       [model.ref(face)], model.center(face), None))
            for edge in sharp_corners:
                shape = model.part.edges()[edge.ordinal - 1]
                points = np.array([[v.X, v.Y, v.Z] for v in shape.vertices()])
                low, high = float((points @ way).min()), float((points @ way).max())
                corners.append(_corner(model, 0.0, high - low, model.part_extent(way)[1] - low, tools, way, ref,
                                       model.ref(edge.faces[0]), [model.ref(f) for f in edge.faces],
                                       brep.rounded(edge.midpoint), edge.ordinal, state.get("unmade")))
    return pockets, corners


#: Rays across a cavity's axis, from each point inside it, that look for a way out of it (``_open_across``).
ACROSS_RAYS = 36
#: Points inside a cavity the rays across its axis start from, at most.
ACROSS_POINTS = 12


def _open_across(model: Model, group: set[int], d: np.ndarray) -> bool:
    """Whether the cavity the faces bound is open to a side across ``d`` -- a valley, a groove, a T-slot or a
    dovetail open at its neck -- rather than closed around the axis as a window or a through slot is: rays
    across the axis from inside the cavity tell, from each face's samples along its normal (one that meets
    nothing leaves the part), and from the middle of each such ray in every direction square to the axis
    (``ACROSS_RAYS``) and toward the middle of each pair of the edges that lead out of the group (its mouth's
    sides, those along the axis first): one that leaves the part opens it. Directions the normals take are no
    proof: a dovetail's flanks and floor look every way and its neck is open."""
    along, other = [], []
    for face in group:
        for edge, beyond in model.neighbours(face):
            if beyond not in group:
                (along if abs(float(np.asarray(edge.tangent) @ d)) > SAME else other).append(
                    np.asarray(edge.midpoint, dtype=float))
    rims = along + other
    seed = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = unit(np.cross(d, seed))
    v = np.cross(d, u)
    inside = []
    for face in sorted(group):
        points, normals, _ = model.samples(face)
        if not len(points):
            continue
        points, normals = points[:4], normals[:4]
        across = normals - np.outer(normals @ d, d)
        for p, n, flat, hit in zip(points, normals, across, model.first_all(points + normals * LIFT, normals)):
            if hit is None:
                if np.linalg.norm(flat) > 0.5:
                    return True  # straight out of the cavity across the axis
                continue
            inside.append(p + n * (LIFT + hit.distance) / 2)  # the middle of the void in front of the face
    if not inside:
        return False
    step = len(inside) / ACROSS_POINTS
    inside = [inside[int(k * step)] for k in range(ACROSS_POINTS)] if len(inside) > ACROSS_POINTS else inside
    turns = np.linspace(0.0, 2.0 * math.pi, ACROSS_RAYS, endpoint=False)
    fan = [math.cos(t) * u + math.sin(t) * v for t in turns]
    rims = rims[:8]
    mouths = [(a + b) / 2 for k, a in enumerate(rims) for b in rims[k + 1:]] or rims
    for origin in inside:
        aimed = []
        for mouth in mouths:
            way = mouth - origin
            way = way - (way @ d) * d
            if np.linalg.norm(way) > 1e-9:
                aimed.append(unit(way))
        for way in aimed + fan:
            if not model.blocked(origin, way):
                return True
    return False


def _corner(model: Model, radius: float, height: float, depth: float, tools: tuple[float, ...] | None,
            axis: np.ndarray, pocket: str, location: str, faces: list[str], xyz: list[float],
            edge: int | None, unmade: dict[int, dict[str, Any]] | None = None) -> dict[str, Any]:
    sharp = radius <= 0.0
    radius = round(radius / RADIUS_TOLERANCE) * RADIUS_TOLERANCE  # read to the tolerance: 1.4999 is 1.5
    if tools:
        fitting = [tool for tool in tools if tool <= 2 * radius + 1e-9]
        tool = max(fitting) if fitting else None
    else:
        tool = 2 * radius if radius > 0 else None
    corner = {"radius_mm": round(radius, 4), "sharp": sharp, "height_mm": round(height, 4),
              "depth_mm": round(depth, 4),
              # a figure a rule reads is compared as measured (to a nanometre); the message rounds it to show it
              "radius_to_depth": round(radius / height, 9) if height > 1e-9 else None,
              # the radius a third of the cavity's depth asks for: the millimetres the hint gives
              "third_of_depth_mm": round(max(height, 0.0) / 3.0, 4),
              "tool_mm": round(tool, 4) if tool else None,
              "reach_ratio": round(depth / tool, 9) if tool else None,
              "axis": brep.rounded(axis, 4), "pocket": pocket, "location": location, "faces": faces,
              "xyz": xyz, "unreached_mm": None, "unreached": "", "_edge": edge}
    if edge is not None:
        corner["edge"] = model.part.ref("edge", edge)
        # an edge some tool reaches part of: its stretch no tool reaches is the corner, there
        corner.update((unmade or {}).get(edge, {}))
    return corner


# --- stock and small features ----------------------------------------------------------------------------


def _stock(model: Model, state: dict[str, Any]) -> list[dict[str, Any]]:
    size = [float(v) for v in (model.box_max - model.box_min)]
    stock = state["stock"]
    blank = list(stock) if stock else size
    volume = float(model.part.shape.volume)
    blank_volume = float(np.prod(blank))
    ordered = sorted(size, reverse=True)
    fits = all(p <= s + 1e-6 for p, s in zip(ordered, sorted(blank, reverse=True)))
    largest = model.largest()
    return [{"part": model.part.name, "size_mm": brep.rounded(size), "stock_mm": brep.rounded(blank),
             "stock_given": stock is not None, "fits_stock": fits,
             "length_mm": round(ordered[0], 4), "width_mm": round(ordered[1], 4), "height_mm": round(ordered[2], 4),
             "volume_mm3": round(volume, 4), "stock_volume_mm3": round(blank_volume, 4),
             # material removed from a blank the part does not fit is no figure
             "removal_ratio": round(1.0 - volume / blank_volume, 4) if blank_volume > 0 and fits else None,
             "location": model.ref(largest), "xyz": brep.rounded((model.box_min + model.box_max) / 2)}]


def _small(model: Model) -> dict[str, Any]:
    lengths = [float(edge.length) for edge in model.edges if edge.length > 1e-9]
    areas = [model.mesh_area(i) for i in range(1, model.n + 1)]
    items = []
    fine = 0
    for i in range(1, model.n + 1):
        size = model.size_mm(i)
        if size < 1.0:
            fine += 1
        if size < TINY_MM:
            items.append({"size_mm": round(size, 4), "area_mm2": round(model.face(i).area, 6),
                          "surface": model.surface(i).kind, "location": model.ref(i), "xyz": model.center(i)})
    return {"items": items, "scalars": {"smallest_edge_mm": round(min(lengths), 4) if lengths else None,
                                        "smallest_face_mm2": round(min(areas), 6) if areas else None,
                                        "fine_faces": fine}}


_FAMILIES = ("holes", "counterbores", "threads", "pockets", "internal_corners", "sharp_edges", "knife_edges", "walls", "gaps",
             "access", "setups", "voids", "stock", "small_features")
_ORDER: dict[str, Callable[[dict[str, Any]], Any]] = {
    "holes": lambda item: -(item["depth_to_diameter"] or 0),
    "counterbores": lambda item: -(item["depth_to_diameter"] or 0),
    "pockets": lambda item: -(item["depth_to_width"] or 0),
    "internal_corners": lambda item: item["radius_mm"],
    "sharp_edges": lambda item: item["void_angle_deg"],
    "knife_edges": lambda item: item["angle_deg"],
    "walls": lambda item: item["thickness_mm"],
    "gaps": lambda item: item["width_mm"],
    "access": lambda item: (item["kind"] == "special_cutter", -item["unreached_fraction"]),
    "voids": lambda item: -item["volume_mm3"],
    "small_features": lambda item: item["size_mm"],
}
