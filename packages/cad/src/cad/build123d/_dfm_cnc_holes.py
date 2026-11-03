"""Holes on exact geometry (``_dfm_cnc``): concave cylinders found with their coaxial neighbours -- a
counterbore, a countersink, a drill point, a flat floor -- and the standard drill each diameter is.

**A hole** is a connected set of faces on one axis: concave cylinders and cones coaxial with each other, and
the planes square to that axis whose every neighbour is one of them (a counterbore's step, a flat floor). At
least one cylinder must sweep 300 degrees or more about the axis (a pocket's quarter-round corner or a slot's
half-round end is not a hole). Its **diameter** is its narrowest full cylinder's; its **depth** the extent
of its cylinders along the axis; **blind** where an exact ray along the axis from inside the narrowest
cylinder meets a face of the hole itself (its floor) and **through** where neither way does. A blind hole's
floor is a ``drill_point`` (a concave cone closing to a point: its included angle, 118 degrees for a jobber
drill) or ``flat`` (a plane).

**Standard drills** (Wikipedia, "Drill bit sizes", after ASME B94.11M): metric 0.2-0.98 mm (N x 0.1 + 0,
0.02, 0.05, 0.08), 1.0-2.95 mm by 0.05, 3.0-13.9 mm by 0.1, 14-25 mm by 0.25; fractional inch by 1/64 to
1 3/4 in; number gauges #80-#1; letters A-Z. A hole over the series' largest is milled, not drilled. A
diameter within 0.005 mm of one is that drill. **Tap drills** (ISO 262 coarse pitches, tap drill = nominal
minus pitch): a hole at one is reported as that thread's candidate, a fact, not a verdict.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from cad.build123d import _dfm_brep as brep
from cad.build123d._dfm_cnc_model import WORLD, Model, unit

__all__ = ["DRILLS", "TAPS", "holes", "standard_drill"]

_NUMBER_IN = (0.228, 0.221, 0.213, 0.209, 0.2055, 0.204, 0.201, 0.199, 0.196, 0.1935, 0.191, 0.189, 0.185,
              0.182, 0.180, 0.177, 0.173, 0.1695, 0.166, 0.161, 0.159, 0.157, 0.154, 0.152, 0.1495, 0.147,
              0.144, 0.1405, 0.136, 0.1285, 0.120, 0.116, 0.113, 0.111, 0.110, 0.1065, 0.104, 0.1015, 0.0995,
              0.098, 0.096, 0.0935, 0.089, 0.086, 0.082, 0.081, 0.0785, 0.076, 0.073, 0.070, 0.067, 0.0635,
              0.0595, 0.055, 0.052, 0.0465, 0.043, 0.042, 0.041, 0.040, 0.039, 0.038, 0.037, 0.036, 0.035,
              0.033, 0.032, 0.031, 0.0292, 0.028, 0.026, 0.025, 0.024, 0.0225, 0.021, 0.020, 0.018, 0.016,
              0.0145, 0.0135)
_LETTER_IN = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                      (0.234, 0.238, 0.242, 0.246, 0.250, 0.257, 0.261, 0.266, 0.272, 0.277, 0.281, 0.290, 0.295,
                       0.302, 0.316, 0.323, 0.332, 0.339, 0.348, 0.358, 0.368, 0.377, 0.386, 0.397, 0.404,
                       0.413)))


def _drills() -> list[tuple[float, str]]:
    found: list[tuple[float, str]] = []
    for n in range(2, 10):
        for extra in (0.0, 0.02, 0.05, 0.08):
            found.append((round(n * 0.1 + extra, 3), "metric"))
    found += [(round(1.0 + 0.05 * k, 3), "metric") for k in range(40)]
    found += [(round(3.0 + 0.1 * k, 3), "metric") for k in range(110)]
    found += [(round(14.0 + 0.25 * k, 3), "metric") for k in range(45)]
    found += [(n * 25.4 / 64, f"{n // math.gcd(n, 64)}/{64 // math.gcd(n, 64)} in") for n in range(1, 113)]
    found += [(inch * 25.4, f"#{number}") for number, inch in enumerate(_NUMBER_IN, start=1)]
    found += [(inch * 25.4, f"letter {letter}") for letter, inch in _LETTER_IN.items()]
    return sorted(found)


#: Every standard drill: its diameter in millimetres and its name.
DRILLS = _drills()
#: The largest drill the series name (1 3/4 in): a hole over it is milled.
LARGEST_DRILL = max(size for size, _ in DRILLS)
#: ISO 262 coarse threads: nominal, pitch.
TAPS = ((1.0, 0.25), (1.2, 0.25), (1.4, 0.3), (1.6, 0.35), (1.8, 0.35), (2.0, 0.4), (2.5, 0.45), (3.0, 0.5),
        (3.5, 0.6), (4.0, 0.7), (5.0, 0.8), (6.0, 1.0), (7.0, 1.0), (8.0, 1.25), (10.0, 1.5), (12.0, 1.75),
        (14.0, 2.0), (16.0, 2.0), (18.0, 2.5), (20.0, 2.5), (22.0, 2.5), (24.0, 3.0))
MATCH_MM = 0.005


def standard_drill(diameter: float) -> tuple[str | None, float]:
    """The standard drill a diameter is (its name, or None) and its distance from the nearest one."""
    sizes = np.array([size for size, _ in DRILLS])
    index = int(np.argmin(np.abs(sizes - diameter)))
    deviation = float(abs(sizes[index] - diameter))
    if deviation > MATCH_MM:
        return None, deviation
    size, name = DRILLS[index]
    label = f"{size:g} mm" if name == "metric" else f"{name} ({size:.3f} mm)"
    return label, deviation


def _tap(diameter: float) -> str | None:
    for nominal, pitch in TAPS:
        if abs((nominal - pitch) - diameter) <= 0.01 or abs(round(nominal - pitch, 1) - diameter) <= 0.01:
            return f"M{nominal:g}x{pitch:g}"
    return None


def _axis_key(s: brep.Surface) -> tuple[Any, ...]:
    a = unit(s.axis)
    for value in a:
        if abs(value) > 1e-9:
            if value < 0:
                a = -a
            break
    o = np.asarray(s.origin)
    foot = o - a * float(o @ a)
    return tuple(np.round(a, 4)) + tuple(np.round(foot, 3))


def _coaxial(a: brep.Surface, b: brep.Surface) -> bool:
    if a.axis is None or b.axis is None:
        return False
    da, db = unit(a.axis), unit(b.axis)
    if abs(float(da @ db)) < 0.99999:
        return False
    gap = np.asarray(b.origin) - np.asarray(a.origin)
    off = gap - da * float(gap @ da)
    return float(np.linalg.norm(off)) < 1e-4


def holes(model: Model) -> tuple[list[dict[str, Any]], set[int]]:
    """The part's holes (see the module), and the ordinals of every face that belongs to one."""
    candidates = [i for i in range(1, model.n + 1)
                  if model.surface(i).kind in ("cylinder", "cone") and model.surface(i).concave]
    claimed: set[int] = set()
    found: list[dict[str, Any]] = []
    for seed in candidates:
        if seed in claimed or model.surface(seed).kind != "cylinder":
            continue
        axis_surface = model.surface(seed)
        group = {seed}
        frontier = [seed]
        while frontier:
            current = frontier.pop()
            for _, other in model.neighbours(current):
                if other in group:
                    continue
                s = model.surface(other)
                if s.kind in ("cylinder", "cone") and s.concave and _coaxial(axis_surface, s):
                    group.add(other)
                    frontier.append(other)
                elif s.kind == "plane" and abs(float(np.asarray(s.normal) @ unit(axis_surface.axis))) > 0.9999:
                    rest = [o for _, o in model.neighbours(other) if o != other]
                    if rest and all(model.surface(o).kind in ("cylinder", "cone") and model.surface(o).concave
                                    and _coaxial(axis_surface, model.surface(o)) for o in rest):
                        group.add(other)
                        frontier.append(other)
        cylinders = [i for i in group if model.surface(i).kind == "cylinder"]
        by_radius: dict[float, float] = {}
        for i in cylinders:
            key = round(float(model.surface(i).radius), 6)
            by_radius[key] = by_radius.get(key, 0.0) + model.span_rad(i)
        full = sorted(radius for radius, span in by_radius.items() if span >= math.radians(300.0))
        if not full:
            continue
        claimed |= group
        hole = _describe(model, group, full)
        if hole is not None:
            found.append(hole)
    return found, claimed


def _describe(model: Model, group: set[int], full: list[float]) -> dict[str, Any] | None:
    radius = full[0]
    narrow = [i for i in group if model.surface(i).kind == "cylinder"
              and abs(float(model.surface(i).radius) - radius) < 1e-6]
    s = model.surface(narrow[0])
    a = unit(s.axis)
    cylinders = [i for i in group if model.surface(i).kind == "cylinder"]
    lows, highs = zip(*(model.extent(i, a) for i in cylinders))
    low, high = min(lows), max(highs)
    n_low, n_high = zip(*(model.extent(i, a) for i in narrow))
    middle = (min(n_low) + max(n_high)) / 2.0
    o = np.asarray(s.origin)
    centre = o + a * (middle - float(o @ a))
    seed = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    aside = centre + unit(np.cross(a, seed)) * 0.3 * radius  # off the axis: a drill point's apex is no face
    ends: dict[int, int | None] = {}
    for sign in (1, -1):
        hit = model.first(aside, a * sign, skip=1e-6)
        ends[sign] = hit.face if hit is not None and hit.face in group else None
    blind = [sign for sign, face in ends.items() if face is not None]
    through = not blind
    bottom = "through"
    point_angle = None
    opening = None
    if blind:
        sign = blind[0]
        floor = ends[sign]
        opening = (-a * sign)
        fs = model.surface(floor)
        if fs.kind == "cone":
            bottom = "drill_point"
            point_angle = 2.0 * float(fs.half_angle_deg)
        elif fs.kind == "plane":
            bottom = "flat"
        else:
            bottom = "other"
        if len(blind) == 2:
            bottom = "closed"
    counterbores = []
    for other in sorted({round(float(model.surface(i).radius), 6) for i in cylinders} - {radius}):
        faces = [i for i in cylinders if abs(float(model.surface(i).radius) - other) < 1e-6]
        el, eh = zip(*(model.extent(i, a) for i in faces))
        counterbores.append({"diameter_mm": round(2 * other, 4), "depth_mm": round(max(eh) - min(el), 4)})
    countersinks = []
    for i in group:
        cs = model.surface(i)
        if cs.kind != "cone" or (bottom == "drill_point" and i == ends.get(blind[0] if blind else 0)):
            continue
        points = model.outline(i)
        radial = points - o - np.outer((points - o) @ a, a)
        countersinks.append({"diameter_mm": round(2 * float(np.linalg.norm(radial, axis=1).max()), 4),
                             "angle_deg": round(2 * float(cs.half_angle_deg), 4), "face": model.ref(i)})
    diameter = 2 * radius
    depth = high - low
    label, deviation = standard_drill(diameter)
    drilled = diameter <= LARGEST_DRILL + MATCH_MM
    aligned = any(abs(float(a @ w)) > 0.9999 for w in WORLD[::2])
    hole = {
        "diameter_mm": round(diameter, 4), "depth_mm": round(depth, 4),
        "depth_to_diameter": round(depth / diameter, 4) if diameter > 0 else None,
        "through": through, "bottom": bottom, "point_angle_deg": round(point_angle, 4) if point_angle else None,
        "axis": brep.rounded(a), "aligned": aligned,
        "opening": brep.rounded(opening) if opening is not None else None,
        "counterbores": counterbores, "countersinks": countersinks,
        "drilled": drilled, "standard_drill": label if drilled else None,
        "drill_deviation_mm": round(deviation, 4) if drilled else None,
        "tap_candidate": _tap(diameter),
        "location": model.ref(narrow[0]), "faces": [model.ref(i) for i in sorted(group)],
        "xyz": brep.rounded(centre),
    }
    hole["_faces"] = sorted(group)
    hole["_axis"] = a
    hole["_origin"] = o
    return hole


_ANALYTIC = ("plane", "cylinder", "cone", "sphere", "torus")


def threads(model: Model, holes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], set[int]]:
    """Modelled threads: freeform faces wound about a cylinder's axis. A face that is not a plane, cylinder,
    cone, sphere or torus is a thread's flank where the points along its edges and sampled on it sweep 350
    degrees or more about some cylinder's axis within a narrow band of radius (under a third of it). Flanks
    on one axis are one thread: its major and minor diameters (the band), its length along the axis, its
    pitch (the axial advance per turn of the points' angle), internal where the cylinder nearest its minor
    radius is a hole's (a tap drill) and external where it is a boss's."""
    axes: list[tuple[np.ndarray, np.ndarray, float, bool]] = []
    for i in range(1, model.n + 1):
        s = model.surface(i)
        if s.kind == "cylinder" and s.concave is not None:
            axes.append((unit(s.axis), np.asarray(s.origin, dtype=float), float(s.radius), bool(s.concave)))
    if not axes:
        return [], set()
    by_axis: dict[int, list[tuple[int, np.ndarray]]] = {}
    for i in range(1, model.n + 1):
        if model.surface(i).kind in _ANALYTIC:
            continue
        points = model.outline(i)
        if len(points) < 8:
            continue
        for k, (a, o, _, _) in enumerate(axes):
            rel = points - o
            along = rel @ a
            radial = rel - np.outer(along, a)
            radius = np.linalg.norm(radial, axis=1)
            mean = float(radius.mean())
            if mean <= 1e-9 or float(radius.max() - radius.min()) > mean / 3:
                continue
            seed = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
            u = unit(np.cross(a, seed))
            v = np.cross(a, u)
            angles = np.sort(np.arctan2(radial @ v, radial @ u))
            gaps = np.diff(np.concatenate([angles, angles[:1] + 2 * math.pi]))
            if float(gaps.max()) > math.radians(10.0):
                continue
            by_axis.setdefault(k, []).append((i, points))
            break
    found, claimed = [], set()
    for k, flanks in by_axis.items():
        a, o, _, _ = axes[k]
        faces = sorted({face for face, _ in flanks})
        points = np.vstack([pts for _, pts in flanks])
        rel = points - o
        along = rel @ a
        radius = np.linalg.norm(rel - np.outer(along, a), axis=1)
        minor, major = 2 * float(radius.min()), 2 * float(radius.max())
        nearest = min((entry for entry in axes if _coaxial(brep.Surface("cylinder", origin=tuple(o), axis=tuple(a)),
                                                            brep.Surface("cylinder", origin=tuple(entry[1]),
                                                                         axis=tuple(entry[0])))),
                      key=lambda entry: min(abs(2 * entry[2] - minor), abs(2 * entry[2] - major)))
        internal = nearest[3]
        # the thread's run-outs and end caps: faces beside a flank that lie wholly within its band
        low, high = float(along.min()), float(along.max())
        for flank in list(faces):
            for _, other in model.neighbours(flank):
                if other in faces or model.surface(other).kind == "cylinder":
                    continue
                pts = model.outline(other) - o
                ax = pts @ a
                rad = np.linalg.norm(pts - np.outer(ax, a), axis=1)
                if rad.min() >= minor / 2 - 1e-3 and rad.max() <= major / 2 + 1e-3 and ax.min() >= low - 1e-3 \
                        and ax.max() <= high + 1e-3:
                    faces.append(other)
        faces = sorted(set(faces))
        pitch = _pitch(model, flanks[0][0], a, o)
        length = float(along.max() - along.min())
        claimed |= set(faces)
        found.append({"internal": internal, "major_diameter_mm": round(major, 4), "minor_diameter_mm": round(minor, 4),
                      "pitch_mm": round(pitch, 4) if pitch else None, "length_mm": round(length, 4),
                      "length_to_diameter": round(length / major, 4) if major > 0 else None, "modelled": 1,
                      "axis": brep.rounded(a), "location": model.ref(faces[0]),
                      "faces": [model.ref(f) for f in faces], "xyz": model.center(faces[0])})
    return found, claimed


def _pitch(model: Model, ordinal: int, a: np.ndarray, o: np.ndarray) -> float | None:
    """The axial advance per turn of a flank's edge points: their angle about the axis unwrapped, against
    their place along it."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve

    seed = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = unit(np.cross(a, seed))
    v = np.cross(a, u)
    best = None
    for edge in model.face(ordinal).edges():
        curve = BRepAdaptor_Curve(edge.wrapped)
        first, last = curve.FirstParameter(), curve.LastParameter()
        pts = []
        for k in range(201):
            p = curve.Value(first + (last - first) * k / 200)
            pts.append((p.X(), p.Y(), p.Z()))
        rel = np.array(pts) - o
        theta = np.unwrap(np.arctan2(rel @ v, rel @ u))
        turns = float(abs(theta[-1] - theta[0])) / (2 * math.pi)
        if turns < 0.5:
            continue
        advance = float(abs((rel @ a)[-1] - (rel @ a)[0]))
        pitch = advance / turns
        if best is None or turns > best[0]:
            best = (turns, pitch)
    return best[1] if best else None
