"""Turning on exact geometry (``_dfm_cnc``, with ``turning``): the axis a lathe spins the part about, how much
of it turns, its diameters, bores and grooves, and the features its live tooling (or a mill) makes.

**The axis** is the line most of the part's surfaces of revolution share: every cylinder, cone and torus
names its axis; the line whose coaxial faces have the most area is taken. **Axisymmetry** is the share of the
part's area on faces of revolution about it (coaxial cylinders, cones, tori, spheres centred on it) and on
planes square to it whose every edge is a circle about it (a square plate's faces are no turned face). Every other face is **off-axis**: joined into features by their edges, each is a
``cross_hole`` (a hole on another axis: ``radial`` where its axis is square to the turning axis and meets it,
``perpendicular`` where it is square to it beside it, ``off_axis`` otherwise -- the hole itself is marked
so), a ``flat`` (one plane along the axis), a ``slot`` (planes along the axis facing each other: a keyway), or a
``feature``.

**Diameters** are the convex coaxial cylinders (diameter, length along the axis); **bores** the holes on the
axis; **grooves** the coaxial cylinders whose both ends meet planes square to the axis by concave edges: an
outside (OD) groove's floor is convex, an internal (ID) groove's concave; width along the axis, depth to the
lower shoulder. The **length** and **largest diameter** are taken over points along every edge and sampled on
every face (exact for the planes and cylinders a turned part is made of).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from cad.build123d import _dfm_brep as brep
from cad.build123d._dfm_cnc_holes import _axis_key, _coaxial
from cad.build123d._dfm_cnc_model import Model, unit

__all__ = ["turned"]

_REVOLVED = ("cylinder", "cone", "torus")


def _on_axis(s: brep.Surface, origin: np.ndarray, axis: np.ndarray) -> bool:
    if s.kind in _REVOLVED:
        return _coaxial(brep.Surface("cylinder", origin=tuple(origin), axis=tuple(axis)), s)
    if s.kind == "sphere":
        gap = np.asarray(s.origin) - origin
        return float(np.linalg.norm(gap - axis * float(gap @ axis))) < 1e-4
    if s.kind == "plane":
        return abs(float(np.asarray(s.normal) @ axis)) > 0.9999
    return False


def _round(model: Model, ordinal: int, origin: np.ndarray, axis: np.ndarray) -> bool:
    """Whether every edge of a plane square to the axis is a circle about it (a lathe faces it)."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve

    for edge in model.face(ordinal).edges():
        curve = BRepAdaptor_Curve(edge.wrapped)
        first, last = curve.FirstParameter(), curve.LastParameter()
        points = np.array([[p.X(), p.Y(), p.Z()] for p in (curve.Value(first + (last - first) * k / 8)
                                                          for k in range(9))])
        radii = _radial(points, origin, axis)
        if float(radii.max() - radii.min()) > 1e-4 * max(1.0, float(radii.max())):
            return False
    return True


def _radial(points: np.ndarray, origin: np.ndarray, axis: np.ndarray) -> np.ndarray:
    rel = points - origin
    return np.linalg.norm(rel - np.outer(rel @ axis, axis), axis=1)


def turned(model: Model, state: dict[str, Any], holes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    largest = model.largest()
    scores: dict[tuple[Any, ...], list[Any]] = {}
    for i in range(1, model.n + 1):
        s = model.surface(i)
        if s.kind in _REVOLVED and s.axis is not None:
            key = _axis_key(s)
            entry = scores.setdefault(key, [0.0, s])
            entry[0] += model.mesh_area(i)
    base = {"part": model.part.name, "location": model.ref(largest), "xyz": model.center(largest)}
    if not scores:
        return {"turning": [{**base, "axis": None, "axisymmetric_fraction": 0.0, "max_diameter_mm": None,
                             "length_mm": None}], "turned_diameters": [], "bores": [], "grooves": [],
                "live_tooling": []}
    _, chosen = max(scores.values(), key=lambda entry: entry[0])
    axis = unit(chosen.axis)
    origin = np.asarray(chosen.origin, dtype=float)
    on = [i for i in range(1, model.n + 1) if _on_axis(model.surface(i), origin, axis)]
    on_set = set(on)
    revolved_area = sum(model.mesh_area(i) for i in on
                        if model.surface(i).kind != "plane" or _round(model, i, origin, axis))
    total_area = sum(model.mesh_area(i) for i in range(1, model.n + 1))
    points = np.vstack([model.outline(i) for i in range(1, model.n + 1)])
    along = points @ axis
    radii = _radial(points, origin, axis)
    cylinder_radii = [float(model.surface(i).radius) for i in on
                      if model.surface(i).kind == "cylinder" and model.surface(i).concave is False]
    max_radius = max([float(radii.max())] + cylinder_radii)
    length = float(along.max() - along.min())
    volume = float(model.part.shape.volume)
    bar = math.pi * max_radius ** 2 * length
    sharp_corners = sum(1 for edge in model.edges if edge.concave and not edge.smooth
                        and edge.faces[0] in on_set and edge.faces[1] in on_set)
    off = [i for i in range(1, model.n + 1) if i not in on_set]
    turning = {**base, "axis": brep.rounded(axis, 6), "axis_origin": brep.rounded(origin - axis * float(origin @ axis)),
               "axisymmetric_fraction": round(revolved_area / total_area, 4) if total_area else None,
               "max_diameter_mm": round(2 * max_radius, 4), "length_mm": round(length, 4),
               "length_to_diameter": round(length / (2 * max_radius), 4) if max_radius > 0 else None,
               "bar_removal_ratio": round(1 - volume / bar, 4) if bar > 0 else None,
               "off_axis_faces": len(off), "sharp_profile_corners": sharp_corners}
    diameters = []
    groove_floors = _groove_floors(model, on, on_set, origin, axis)
    for i in on:
        s = model.surface(i)
        if s.kind == "cylinder" and s.concave is False and i not in groove_floors:
            low, high = model.extent(i, axis)
            diameters.append({"diameter_mm": round(2 * float(s.radius), 4), "length_mm": round(high - low, 4),
                              "location": model.ref(i), "xyz": model.center(i)})
    bores = []
    hole_faces_by_ordinal = {}
    for hole in holes:
        faces = hole.get("_faces") or []
        hole_axis = hole.get("_axis")
        if hole_axis is None:
            continue
        parallel = abs(float(np.asarray(hole_axis) @ axis)) > 0.9999
        gap = np.asarray(hole["_origin"]) - origin
        offset = float(np.linalg.norm(gap - axis * float(gap @ axis)))
        if parallel:
            hole["relation"] = "axial"
            if offset < 1e-4:
                bores.append({key: hole[key] for key in ("diameter_mm", "depth_mm", "depth_to_diameter", "through",
                                                         "bottom", "location", "xyz")})
                continue
        else:
            # radial: square to the axis and meeting it; perpendicular: square to it, beside it (a lathe's live
            # tooling drills holes parallel or perpendicular to the axis of revolution); off_axis: else
            square = abs(float(np.asarray(hole_axis) @ axis)) < 1e-4
            normal = np.cross(np.asarray(hole_axis), axis)
            meets = abs(float(gap @ unit(normal))) < 1e-4 if np.linalg.norm(normal) > 1e-9 else False
            hole["relation"] = ("radial" if meets else "perpendicular") if square else "off_axis"
        for face in faces:
            hole_faces_by_ordinal[face] = hole
    grooves = [groove for _, groove in sorted(groove_floors.items())]
    live = []
    claimed: set[int] = set()
    for seed in off:
        if seed in claimed:
            continue
        group, frontier = {seed}, [seed]
        while frontier:
            current = frontier.pop()
            for _, other in model.neighbours(current):
                if other not in on_set and other not in group:
                    group.add(other)
                    frontier.append(other)
        claimed |= group
        hole = next((hole_faces_by_ordinal[f] for f in group if f in hole_faces_by_ordinal), None)
        planes = [f for f in group if model.surface(f).kind == "plane"
                  and abs(float(np.asarray(model.surface(f).normal) @ axis)) < 0.02]
        if hole is not None:
            kind = "cross_hole"
        elif len(planes) >= 2 and any(float(np.asarray(model.surface(a).normal) @ np.asarray(model.surface(b).normal))
                                      < -0.99 for a in planes for b in planes):
            kind = "slot"
        elif planes and len(group) <= 3:
            kind = "flat"
        else:
            kind = "feature"
        main = max(group, key=model.mesh_area)
        live.append({"kind": kind, "relation": hole.get("relation") if hole else None,
                     "area_mm2": round(sum(model.mesh_area(f) for f in group), 4), "face_count": len(group),
                     "location": model.ref(main), "faces": [model.ref(f) for f in sorted(group)][:20],
                     "xyz": model.center(main)})
    return {"turning": [turning], "turned_diameters": diameters, "bores": bores, "grooves": grooves,
            "live_tooling": live}


def _groove_floors(model: Model, on: list[int], on_set: set[int], origin: np.ndarray,
                   axis: np.ndarray) -> dict[int, dict[str, Any]]:
    """The grooves (see the module), by the ordinal of each one's floor."""
    found: dict[int, dict[str, Any]] = {}
    for i in on:
        s = model.surface(i)
        if s.kind != "cylinder" or s.concave is None:
            continue
        sides = [other for edge, other in model.neighbours(i)
                 if edge.concave and not edge.smooth and model.surface(other).kind == "plane" and other in on_set]
        low, high = model.extent(i, axis)
        ends = {}
        for side in sides:
            level = float(np.mean(model.outline(side) @ axis))
            ends["low" if abs(level - low) < abs(level - high) else "high"] = side
        if len(ends) < 2:
            continue
        r = float(s.radius)
        if s.concave is False:
            shoulders = [float(_radial(model.outline(side), origin, axis).max()) for side in ends.values()]
            depth = min(shoulders) - r
        else:
            shoulders = [float(_radial(model.outline(side), origin, axis).min()) for side in ends.values()]
            depth = r - max(shoulders)
        if depth <= 1e-6:
            continue
        found[i] = {"internal": bool(s.concave), "width_mm": round(high - low, 4), "depth_mm": round(depth, 4),
                    "diameter_mm": round(2 * r, 4), "location": model.ref(i),
                    "faces": [model.ref(i)] + [model.ref(side) for side in ends.values()], "xyz": model.center(i)}
    return found
