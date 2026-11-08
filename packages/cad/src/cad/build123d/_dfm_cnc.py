"""cnc's measurements of exact geometry (``cad._internal.dfm.cnc`` says what they are for).

Each part of the document is measured on its own B-rep (``_dfm_cnc_model.Model``), and every family's items
say which part and face they are at (``plate/face 7``). The families, and how each is measured:

- ``holes`` (``_dfm_cnc_holes``): concave cylinders and their coaxial neighbours; diameter, depth, blind or
  through by an exact ray along the axis, the floor (drill point and its angle, or flat), counterbores,
  countersinks, the standard drill each diameter is.
- ``pockets``: every planar face that meets, by a concave edge (or through a concave root fillet), a face
  lying along its normal is a pocket's floor; its walls are those faces and the faces along the normal joined
  to them by concave or tangent edges. Depth (floor to the walls' rim), depth from the part's top along the
  normal (what a tool must reach), width (the narrowest gap between opposite walls: exact rays from each
  wall along its normal that land on another wall of the pocket, the two walls named), closed or open (a
  convex edge on the floor's outer boundary opens it), the floor's root fillet radius, ``reachable`` (along a
  direction the machine has, or no edge of it left unmade) and ``inclination_deg``. A **through** cavity has
  no floor (a window, a through slot, a cut-out, a through T-slot or dovetail): faces along a machine axis
  joined by concave or tangent edges along it, none a pocket's, closed around the axis (their normals in no
  one half-plane: an open valley is no window), with a corner (a concave cylinder along it, or a sharp
  concave edge along it); its depth is its walls' extent along the axis.
- ``internal_corners``: a pocket's in-plane corners -- its concave cylinders along the tool axis (their
  radius) and its sharp concave edges along the tool axis that no tool makes from another side (radius 0);
  a through cavity's likewise. The floor-to-wall root is no corner: a flat end mill makes
  it sharp. Each against its depth and against the largest tool that fits it (``--tools``, else a tool of
  twice its radius); a radius is read to ``RADIUS_TOLERANCE``.
- ``threads`` (``_dfm_cnc_holes``): modelled threads, freeform flanks wound about a cylinder's axis: major and
  minor diameters, pitch, length, internal or external. Their faces are a tap's: no other family reads them.
- ``sharp_edges``: every other sharp concave edge that no rotating tool makes. A tool's corner makes one where
  one face is a floor or a ceiling square to an approach direction of the machine and the angle in the void
  is at least 90 degrees: an end mill where a ray from that face along the direction escapes the part, a
  T-slot cutter where the cavity the edge bounds opens along the direction somewhere; a dovetail cutter
  makes a 45 or 60 degree one the same way, a chamfer mill a 60, 90 or 120 degree one along its bisector,
  a chamfer mill's shoulder (180 less its half angle) along its axis, and a ball end mill one of
  ``BALL_VOID_DEG`` or more along a direction both faces look along. The floor or ceiling must be a plane.
  Each unmade edge says why (``reason``: ``other_axes``, ``vertical_corner``, ``acute``, ``blocked``,
  ``no_square_face``, see ``_why``); a ball's crease is an item too (``made_by`` ``ball_mill``, its round's
  ``deviation_mm`` from the drawn edge); an edge only a T-slot or a dovetail cutter makes is an ``access``
  item of kind ``special_cutter``. ``by_tool`` counts every concave edge by the tool that makes it. An edge
  that is a reported corner's run through a small edge round at its end is folded into that corner
  (``folded_edges``, see ``_fold``), not listed again.
- ``walls``: the thickness under each face (an exact ray into the material from points sampled on it, to the
  first face across that faces the other way), the thinnest per face under 5 mm, with the wall's height. The
  listed items are then refined to the exact minimum distance between the face and the face across
  (``BRepExtrema_DistShapeShape``), kept where that segment runs through the material near square to the
  face. A face across that meets the face at a knife edge is no wall: ``knife_edges`` reports it.
- ``gaps``: the width of the void in front of each face (the same ray outward), the narrowest per face under
  10 mm: the slots and channels a tool must fit in; refined like walls, through the void.
- ``knife_edges``: convex edges whose material angle is under ``KNIFE_DEG`` (printing's notion): the
  material thins to nothing there, whatever a sampled wall would read.
- ``access`` and ``setups``: which sampled points of each face a straight tool reaches from each of the
  machine's approach directions (exact rays along the direction must escape the part), the fewest
  directions that reach them all (greedy set cover) and the fixtures they need; the faces no direction
  reaches, and whether any direction at all (a five-axis machine's) would. Five axes try every direction a
  four-axis machine would (each 15 degrees about each world axis) before probing the sphere, so they reach
  at least what four do. A hole or pocket along no direction the machine has adds its own orientation and
  clamping (``inclined_directions``).
- ``voids``: closed cavities inside the material (a solid's inner shells).
- ``stock``: the part's box or ``--stock``, the material removed, the part's size sorted.
- ``small_features``: the shortest edge, the smallest face, and the faces narrower than half a millimetre.
- with ``turning`` (``_dfm_cnc_turning``): the axis, how much of the part turns about it, its diameters,
  bores, grooves and the features a lathe's live tooling makes.

A figure the geometry does not give is None, never a guess. Lengths are millimetres.
"""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np

from cad._internal.dfm import Unmeasured, checkpoint
from cad._internal.dfm import cnc as rules_side
from cad._internal.meshops_printing import KNIFE_DEG
from cad.build123d import _dfm_brep as brep
from cad.build123d._dfm_cnc_holes import holes as find_holes
from cad.build123d._dfm_cnc_holes import threads as find_threads
from cad.build123d._dfm_cnc_model import (LIFT, SAME, WORLD, Model, about, directions_for, edge_normals,
                                          fibonacci, unit)

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
#: Without ``--tools``, the radius of the ball a crease is judged as rounded by: a 2.5 mm ball end mill's, the
#: smallest standard tool (Hubs: features under 2.5 mm are micro-machining).
BALL_RADIUS_MM = 1.25
#: A face with more edges than this (a web around many holes) is not refined to its exact wall: the least
#: distance between faces costs with their edges, and over 200 listed items that is the check's budget.
COMPLEX_EDGES = 16
#: A corner's radius is read to this (mm): a radius within half of it of a tool's radius is that tool's.
RADIUS_TOLERANCE = 0.01


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
    for part in document.parts:
        checkpoint()
        try:
            model = Model(part)
        except Exception as error:  # noqa: BLE001 - a part that does not read is the report's to say
            failed.setdefault("model", f"{part.name}: {error}")
            continue
        models.append(model)
        _measure_part(model, len(models) - 1, axes, turning, tools, stock, families, scalars, failed)
    report: dict[str, Any] = {"machine": {"axes": axes, "turning": turning,
                                          "tools_mm": list(tools) if tools else None,
                                          "stock_mm": list(stock) if stock else None}}
    # a turned part is not searched for milled pockets: those families are absent, not empty
    names = ([name for name in _FAMILIES if name not in ("pockets", "internal_corners")]
             + ["turning", "turned_diameters", "bores", "grooves", "live_tooling"]) if turning else list(_FAMILIES)
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
        family = {"items": [_public(item) for item in items[:CAP]], "count": len(items), **scalars.get(name, {})}
        report[name] = family
    if "model" in failed:
        report["model"] = {"error": failed["model"]}
    report["partial_sections"] = sorted(name for name in failed)
    report["partial"] = bool(failed)
    return report


def _public(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if not key.startswith("_")}


def _measure_part(model: Model, index: int, axes: int, turning: bool, tools: tuple[float, ...] | None,
                  stock: tuple[float, float, float] | None, families: dict[str, list[dict[str, Any]]],
                  scalars: dict[str, dict[str, Any]], failed: dict[str, str]) -> None:
    state: dict[str, Any] = {"axes": axes, "tools": tools, "stock": stock, "turning": turning}

    def run(name: str, step: Callable[[], Any]) -> Any:
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
        else:
            for name in ("turned_diameters", "bores", "grooves", "live_tooling"):
                failed.setdefault(name, failed["turning"])


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
    # greedy set cover over the sampled area
    covered = np.zeros(len(points), dtype=bool)
    chosen: list[int] = []
    while True:
        gains = {k: float(areas[r & ~covered].sum()) for k, r in reach.items() if k not in chosen}
        if not gains:
            break
        k = max(gains, key=lambda key: (gains[key], -key))
        if gains[k] <= 1e-12 * max(1.0, model.area):
            break
        chosen.append(k)
        covered |= reach[k]
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
        items.append({"unreached_fraction": round(missed, 4), "unreached_any_direction_fraction": round(nowhere, 4),
                      "kind": "no_line_of_sight" if nowhere > 0 else "undercut",
                      "hole": i in state.get("hole_axis", {}), "hole_axis": state.get("hole_axis", {}).get(i),
                      "surface": model.surface(i).kind, "location": model.ref(i), "xyz": brep.rounded(where)})
    directions = []
    covered = np.zeros(len(points), dtype=bool)
    for k in chosen:
        new = reach[k] & ~covered
        covered |= reach[k]
        directions.append({"direction": brep.rounded(candidates[k], 4),
                           "area_fraction": round(float(areas[new].sum() / areas.sum()), 4),
                           "faces": int(len(set(owner_a[new].tolist())))})
    fixtures = _fixtures([candidates[k] for k in chosen], axes, rotary)
    largest = model.largest()
    setup = {"setup_count": fixtures, "orientation_count": len(chosen), "directions": directions,
             "unreached_area_fraction": round(float(areas[unreached].sum() / areas.sum()), 4),
             "rotary_axis": brep.rounded(rotary) if rotary is not None else None,
             "sampled_points": int(len(points)), "part": model.part.name,
             "location": model.ref(largest), "xyz": model.center(largest)}
    return {"items": items, "setup": setup, "directions": candidates, "rotary": rotary}


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
    unmade = state.get("unmakeable") or set()
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
        pocket["reachable"] = bool(_allowed(state, d) or made)
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
        for p, n, hit in zip(points, normals, model.first_all(points + ways * LIFT, ways)):
            if hit is None or hit.face == 0 or (outward and hit.face in state["hole_faces"]) \
                    or hit.face in state["thread_faces"]:
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
        item["width_mm"] = round(item.pop("distance"), 4)
        item["surface"] = model.surface(item["_face"]).kind
        items.append(item)
    return items


def _walls(model: Model, state: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for item in _across(model, state, False, WALL_CAP_MM):
        i = item["_face"]
        thickness = item.pop("distance")
        height = _height(model, i)
        item.update(thickness_mm=round(thickness, 4), height_mm=round(height, 4) if height else None,
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
    from OCP.BRep import BRep_Tool
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.Extrema import Extrema_ExtFlag_MIN
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf

    i, j = item.get("_face"), item.get("_opposite")
    key = "width_mm" if outward else "thickness_mm"
    if not i or not j or i == j or _touching(model, i, j):
        return
    si, sj = model.surface(i), model.surface(j)
    if si.kind == sj.kind == "plane" and abs(float(np.asarray(si.normal) @ np.asarray(sj.normal))) > SAME:
        return  # parallel planes: every ray between them is the same length, so the sampled one is exact
    if len(model.adjacent.get(i, ())) > COMPLEX_EDGES:
        return  # a face of many edges (a web around many holes): its sampled figure stands
    across = model.face(j).wrapped
    if len(model.adjacent.get(j, ())) > COMPLEX_EDGES:
        # the face across's surface over its (u, v) box, four edges: a least distance found where the face
        # is trimmed away (in one of its holes) fails the ray check below and the sampled figure stands
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        from OCP.BRepTools import BRepTools

        umin, umax, vmin, vmax = BRepTools.UVBounds_s(across)
        made = BRepBuilderAPI_MakeFace(BRep_Tool.Surface_s(across), umin, umax, vmin, vmax, 1e-7)
        if not made.IsDone():
            return
        across = made.Face()
    dist = BRepExtrema_DistShapeShape(model.face(i).wrapped, across, Extrema_ExtFlag_MIN)
    if not dist.IsDone() or dist.NbSolution() == 0 or dist.Value() >= float(item[key]) - 1e-6:
        return
    best = None
    for k in range(1, dist.NbSolution() + 1):
        a, b = dist.PointOnShape1(k), dist.PointOnShape2(k)
        pa, pb = np.array([a.X(), a.Y(), a.Z()]), np.array([b.X(), b.Y(), b.Z()])
        length = float(np.linalg.norm(pb - pa))
        if length <= 1e-9 or (best is not None and length >= best[0]):
            continue
        projector = GeomAPI_ProjectPointOnSurf(a, BRep_Tool.Surface_s(model.face(i).wrapped))
        if projector.NbPoints() == 0:
            continue
        u, v = projector.LowerDistanceParameters()
        _, normal = brep.point_normal(model.face(i), u, v)
        way = (pb - pa) / length
        if float(way @ (normal if outward else -normal)) < -OPPOSED:
            continue
        # the two faces face each other there, as the sampled ray's did: a least distance across a convex
        # round's chord (two faces square to each other, r sqrt 2 apart) is no wall
        projector = GeomAPI_ProjectPointOnSurf(b, BRep_Tool.Surface_s(model.face(j).wrapped))
        if projector.NbPoints() == 0:
            continue
        _, there = brep.point_normal(model.face(j), *projector.LowerDistanceParameters())
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
    item[key] = round(best[0], 4)
    item["xyz"] = brep.rounded(best[1])
    item["refined"] = True
    if not outward and item.get("height_mm"):
        item["height_to_thickness"] = round(item["height_mm"] / best[0], 4)


def _knife_edges(model: Model, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Convex edges whose material angle is under ``KNIFE_DEG``: the material thins to nothing there."""
    skip = state["thread_faces"]
    items = []
    for edge in model.edges:
        if edge.concave or edge.smooth or not edge.angle_deg < KNIFE_DEG or set(edge.faces) & skip:
            continue
        items.append({"angle_deg": round(edge.angle_deg, 4), "length_mm": round(edge.length, 4), "thickness_mm": 0.0,
                      "edge": model.part.ref("edge", edge.ordinal), "location": model.ref(edge.faces[0]),
                      "faces": [model.ref(f) for f in edge.faces], "xyz": brep.rounded(edge.midpoint),
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
    special: list[tuple[Any, str]] = []
    unmakeable: set[int] = set()
    tools = state.get("tools")
    ball_radius = tools[0] / 2 if tools else BALL_RADIUS_MM
    visible: dict[tuple[int, tuple[float, ...]], bool] = {}

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
        try:
            n1, n2 = edge_normals(model, edge)
        except Exception:  # noqa: BLE001
            continue
        way = _way(model, state, edge, n1, n2, sees, cavity)
        ways[way or "none"] = ways.get(way or "none", 0) + 1
        void = 360.0 - edge.angle_deg
        record = {"void_angle_deg": round(void, 4), "length_mm": round(edge.length, 4),
                  "makeable": 0, "radius_mm": 0.0, "acute": bool(void < 89.9), "reason": None, "made_by": None,
                  "between": " and ".join(model.ref(f) for f in edge.faces),
                  "tangent": brep.rounded(edge.tangent, 4),
                  "edge": model.part.ref("edge", edge.ordinal),
                  "location": model.ref(edge.faces[0]), "faces": [model.ref(f) for f in edge.faces],
                  "xyz": brep.rounded(edge.midpoint), "_edge": edge.ordinal}
        if way in ("slot_cutter", "dovetail_cutter"):
            special.append((edge, way))
        if way == "ball_mill":
            # made, but rounded: the ball leaves a round of its radius in the crease, departing from the
            # drawn edge by R (1 / sin(void / 2) - 1); kept in the record so nothing vanishes from it
            deviation = ball_radius * (1.0 / math.sin(math.radians(void) / 2.0) - 1.0)
            balls.append({**record, "makeable": 1, "radius_mm": round(ball_radius, 4), "made_by": "ball_mill",
                          "deviation_mm": round(deviation, 4)})
        if way is not None:
            continue
        unmakeable.add(edge.ordinal)
        items.append({**record, "reason": _why(model, state, edge, n1, n2, sees, cavity)})
    return {"items": items, "balls": balls, "special": _special(model, special), "unmakeable": unmakeable,
            "ways": ways}


def _why(model: Model, state: dict[str, Any], edge: Any, n1: np.ndarray, n2: np.ndarray,
         sees: Callable[[int, np.ndarray], bool], cavity: Callable[[tuple[int, int]], set[int]]) -> str:
    """Why no tool of the machine makes a sharp concave edge, the first that holds: ``other_axes`` (a tool
    along a direction the machine lacks would), ``vertical_corner`` (both faces lie along a machine direction
    the edge runs along: a corner of a cavity cut along it, where the tool's side leaves its radius, whatever
    its angle), ``acute`` (its void is under 90 degrees: no tool's end or side reaches the root),
    ``blocked`` (a face is a plane square to a machine direction, but the way along it is blocked) or
    ``no_square_face`` (no face is a plane square to one)."""
    void = 360.0 - edge.angle_deg
    if state["axes"] < 5 and _way(model, {**state, "axes": 5, "beyond": state}, edge, n1, n2, sees, cavity) is not None:
        return "other_axes"
    tangent = np.asarray(edge.tangent)
    for d in WORLD[::2]:
        if abs(float(tangent @ d)) > SAME and _allowed(state, d) and all(model.along(f, d) for f in edge.faces):
            return "vertical_corner"
    if void < 89.9:
        return "acute"
    for normal, face in ((n1, edge.faces[0]), (n2, edge.faces[1])):
        if model.surface(face).kind == "plane" and (_allowed(state, normal) or _allowed(state, -normal)):
            return "blocked"
    return "no_square_face"


def _special(model: Model, found: list[tuple[Any, str]]) -> list[dict[str, Any]]:
    """The edges only a T-slot or a dovetail cutter makes, joined by the faces they share: one ``access`` item
    of kind ``special_cutter`` each, at the face most of them bound (an undercut, whatever line of sight
    says: such a cutter is a special tool)."""
    groups: list[tuple[set[int], list[tuple[Any, str]]]] = []
    for edge, way in found:
        faces = set(edge.faces)
        joined = [group for group in groups if group[0] & faces]
        merged = (faces.union(*(group[0] for group in joined)), [(edge, way)] + [e for g in joined for e in g[1]])
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
        items.append({"kind": "special_cutter", "cutter": " and ".join(c.replace("_", " ") for c in cutters),
                      "edge_count": len(edges), "edges": [model.part.ref("edge", e.ordinal) for e, _ in edges][:20],
                      "unreached_fraction": 0.0, "unreached_any_direction_fraction": 0.0, "hole": False,
                      "hole_axis": None, "surface": model.surface(face).kind, "location": model.ref(face),
                      "faces": [model.ref(f) for f in sorted(faces)][:20], "xyz": brep.rounded(edges[0][0].midpoint)})
    return items


def _way(model: Model, state: dict[str, Any], edge: Any, n1: np.ndarray, n2: np.ndarray,
         sees: Callable[[int, np.ndarray], bool], cavity: Callable[[tuple[int, int]], set[int]]) -> str | None:
    """How a rotating tool makes a sharp concave edge, or None. A tool's corner makes it where one face is a
    floor or a ceiling square to the tool's axis (an approach direction) and the void's angle is at least 90
    degrees: an end mill where a straight line along the axis from that face leaves the part, a T-slot cutter
    where the cavity the edge bounds opens along the axis somewhere (its shank comes in there); a dovetail
    cutter of 45 or 60 degrees makes that angle with a floor the same way. A chamfer mill
    of 60, 90 or 120 degrees makes it along the edge's bisector."""
    beyond = state.get("beyond")  # only the directions a machine of these axes lacks (``_why``)

    def ok(d: np.ndarray) -> bool:
        return _allowed(state, d) and not (beyond is not None and _allowed(beyond, d))

    void = 360.0 - edge.angle_deg
    mid = np.asarray(edge.midpoint)
    step = min(0.05, 0.1 * edge.length)
    if void >= 89.9:
        faces = tuple(edge.faces)
        for na, nb, face in ((n1, n2, faces[0]), (n2, n1, faces[1])):
            if model.surface(face).kind != "plane":
                continue  # a floor or a ceiling is a plane: a curved face's normal at one point is no floor's
            inward = unit(nb - na * float(nb @ na))
            for d in (na, -na):
                if not ok(d):
                    continue
                # just off the edge on the floor, nearer still where the floor is narrower than the step
                if float(d @ na) > 0 and any(model.escapes(mid + inward * off, na, na) for off in (step, step / 20)):
                    return "end_mill"
                if any(sees(other, d) for other in cavity(faces)):  # noqa: B023
                    return "slot_cutter"
    if any(abs(void - angle) < 0.5 for angle in DOVETAILS):
        faces = tuple(edge.faces)
        for na, face in ((n1, faces[0]), (n2, faces[1])):
            if model.surface(face).kind == "plane" and ok(na) \
                    and any(sees(other, na) for other in cavity(faces)):
                return "dovetail_cutter"
    bisector = unit(n1 + n2)
    if any(abs(void - angle) < 0.5 for angle in V_MILLS) and ok(bisector):
        if model.escapes(mid, bisector, bisector):
            return "chamfer_mill"
    if any(abs(void - (180.0 - angle / 2.0)) < 0.5 for angle in V_MILLS):
        # a chamfer mill's shoulder, where its cone meets its body: one face along the mill's axis (a wall),
        # the other the cone's (a chamfer looking along the axis), the mill coming in along it
        faces = tuple(edge.faces)
        for face, other in ((faces[0], n2), (faces[1], n1)):
            for d in WORLD:
                if ok(d) and float(other @ d) > 0 and model.along(face, d) \
                        and model.escapes(mid, bisector, d):
                    return "chamfer_mill"
    if void >= BALL_VOID_DEG:
        # a ball end mill contours the crease along any direction both faces look along
        for d in (bisector, *WORLD):
            if ok(d) and float(n1 @ d) > 0 and float(n2 @ d) > 0 and model.escapes(mid, bisector, d):
                return "ball_mill"
    return None


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


def _pockets(model: Model, state: dict[str, Any]) -> dict[str, Any]:
    hole_faces = state["hole_faces"]
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
                  "depth_to_width": round(depth / width, 4) if width else None,
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
                                       edge.ordinal))
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
    """Cavities with no floor -- windows, through slots, cut-outs, through T-slots and dovetails --, along each
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
                            "depth_to_width": round(depth / width, 4) if width else None,
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
                                       brep.rounded(edge.midpoint), edge.ordinal))
    return pockets, corners


def _open_across(model: Model, group: set[int], d: np.ndarray) -> bool:
    """Whether the faces' normals, seen along ``d``, all lie in one half-plane: the cavity they bound is open
    to the side that half-plane faces, not closed around the axis as a window or a through slot is."""
    seed = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = unit(np.cross(d, seed))
    v = np.cross(d, u)
    normals = np.vstack([model.samples(face)[1] for face in group if len(model.samples(face)[1])] or [np.zeros((0, 3))])
    flat = normals - np.outer(normals @ d, d)
    keep = np.linalg.norm(flat, axis=1) > 1e-6
    if not keep.any():
        return True
    angles = np.sort(np.degrees(np.arctan2(flat[keep] @ v, flat[keep] @ u)))
    gaps = np.diff(np.concatenate([angles, angles[:1] + 360.0]))
    return float(gaps.max()) >= 179.0


def _corner(model: Model, radius: float, height: float, depth: float, tools: tuple[float, ...] | None,
            axis: np.ndarray, pocket: str, location: str, faces: list[str], xyz: list[float],
            edge: int | None) -> dict[str, Any]:
    sharp = radius <= 0.0
    radius = round(radius / RADIUS_TOLERANCE) * RADIUS_TOLERANCE  # read to the tolerance: 1.4999 is 1.5
    if tools:
        fitting = [tool for tool in tools if tool <= 2 * radius + 1e-9]
        tool = max(fitting) if fitting else None
    else:
        tool = 2 * radius if radius > 0 else None
    corner = {"radius_mm": round(radius, 4), "sharp": sharp, "height_mm": round(height, 4),
              "depth_mm": round(depth, 4),
              "radius_to_depth": round(radius / height, 4) if height > 1e-9 else None,
              "tool_mm": round(tool, 4) if tool else None,
              "reach_ratio": round(depth / tool, 4) if tool else None,
              "axis": brep.rounded(axis, 4), "pocket": pocket, "location": location, "faces": faces,
              "xyz": xyz, "_edge": edge}
    if edge is not None:
        corner["edge"] = model.part.ref("edge", edge)
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


_FAMILIES = ("holes", "threads", "pockets", "internal_corners", "sharp_edges", "knife_edges", "walls", "gaps",
             "access", "setups", "voids", "stock", "small_features")
_ORDER: dict[str, Callable[[dict[str, Any]], Any]] = {
    "holes": lambda item: -(item["depth_to_diameter"] or 0),
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
