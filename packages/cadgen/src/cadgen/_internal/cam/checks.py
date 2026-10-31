"""The checks: what cadgen stands behind in a plan, before and after FreeCAD plans it.

FreeCAD plans what it is asked to and checks nothing against the part: asked to pocket a floor that lies under an
overhang, it cuts through the overhang. So every plan is checked here, and a plan with an error posts no G-code:

* before FreeCAD runs, :func:`reach`: every face an operation names can be seen from the setup's side (rays straight
  up the tool's axis from points on the face, each moved a hair off it along the face's outward normal, leave the
  part: a wall is seen, and the wall of a T-slot's undercut is not), every hole it drills opens toward the tool, its
  drill's point is no longer than the drawn one, and no cut goes deeper below the stock top than the tool's flutes;
* after, :func:`check_moves` on each setup's moves (:mod:`toolpath`, setup coordinates, the tool down -Z):
  ``gouge``, a move whose tool (its real profile: flat, ball, bull nose or drill point) comes into the part, tested
  at points on the part's faces (:func:`_surface_points`) by their exact distance from each move; ``rapid_into_stock``,
  a rapid into stock no move before it has cut (the stock lowered along each cutting move, in program order, on a
  grid finer than the tool); ``empty_operation``, an operation FreeCAD planned no cut for; ``uncut``, a face or hole an
  operation names that no cutting move reaches at the operation's final depth (FreeCAD skips what its tool does not
  fit, and says nothing), a floor whose passes leave part of what the tool fits standing (a ball's scallop between
  passes too far apart among it), and a face a face operation leaves part of; ``travel``, a setup whose moves span
  more than the machine travels.

The tool is taken to reach up without end, so the gouge check is exact for a part machined from one side and
conservative for an undercut (a tool under an overhang is a hit). A finding is a dict of ``check``, ``severity``,
``type``, ``summary``, ``description`` and ``items``. Stdlib at import; numpy inside.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

__all__ = ["CHECKS", "Target", "by_severity", "check_moves", "face_edges", "face_points", "finding", "held", "posted",
           "reach"]

#: Each check and the finding types it raises.
CHECKS = {
    "job": ("job", "freecad", "internal_error"),
    "reach": ("unreachable", "too_deep", "not_facing", "drill_size", "drill_point"),
    "gouge": ("gouge",),
    "rapid_into_stock": ("rapid_into_stock",),
    "empty_operation": ("empty_operation",),
    "coverage": ("uncut",),
    "travel": ("travel",),
    "limits": ("clamped",),
    "post": ("overridden", "posted"),
}
_SEVERITY = {"error": 0, "warning": 1, "info": 2}
#: How far a move may come into the part before it is a gouge (mm): the tessellation's own error (part.py's
#: ``DEFAULT_DEFLECTION_MM``) and an arc's chords' (toolpath.py's ``CHORD_MM``).
GOUGE_TOLERANCE_MM = 0.03
#: How far apart the points a gouge is looked for at lie on the part's faces (mm). A wall is met where the tool comes
#: into it to well under a hundredth of a millimetre, however far apart its points: they lie on it.
SURFACE_STEP_MM = 0.25
#: The longest piece of a move judged as one (mm): a ramp's height along a piece is the one at its closest pass.
PIECE_MM = 1.0
#: How much short of the tool's own reach a floor point still counts as one it fits (mm): FreeCAD's offsets, an arc's
#: chords and the tessellation's own error.
REACH_TOLERANCE_MM = 0.1
#: How far a rapid may be below the stock top before it is a hit (mm).
RAPID_TOLERANCE_MM = 0.05
#: The most cells the stock's grid, or points the part's faces, hold: a part over a metre wide checks coarser, never
#: with a full memory.
MAX_CELLS = 16_000_000
#: How far off a face its reach is judged from, along its outward normal (mm): past the tessellation's own error, and
#: far less than any overhang a tool could not pass.
NUDGE_MM = 0.05
#: How far above an operation's final depth a move still counts as cutting at it (mm).
DEPTH_TOLERANCE_MM = 0.05
#: How much longer than the drawn point a drill's may be before the hole is short of its diameter at the bottom (mm).
POINT_TOLERANCE_MM = 0.01


@dataclass(frozen=True)
class Target:
    """What one operation must reach, at its final depth ``final_z`` (setup coordinates): a named face (``points`` on
    it, (K, 3)) that a cutting move's tool must come over (``wall``: come up beside, within its radius and
    ``leave_mm``), or a hole (``axis_xy``) a cutting move must plunge down to that depth. A floor with ``edges`` is
    held to what the tool fits inside them; one without (a face operation's) to the whole of it."""

    ref: str
    final_z: float
    points: Any = None
    axis_xy: tuple[float, float] | None = None
    wall: bool = False
    leave_mm: float = 0.0
    #: A floor's outline, (M, 2, 2) segments in the setup's x and y: what tells the floor a tool fits from the
    #: corners a round tool never reaches.
    edges: Any = None


def finding(check: str, severity: str, kind: str, summary: str, description: str = "", items=()) -> dict:
    if kind not in CHECKS[check] or severity not in _SEVERITY:
        raise ValueError(f"finding {check}/{kind} ({severity}) is not one cadgen raises")
    return {"check": check, "severity": severity, "type": kind, "summary": summary, "description": description,
            "items": list(items)}


#: What FreeCAD reports it holds of what cadgen set, each beside the operation's value cadgen gave it.
_HELD = {"rpm": ("spindle", "rpm"), "feed_mm_min": ("feed", "mm/min"), "plunge_mm_min": ("plunge", "mm/min"),
         "stepdown_mm": ("step down", "mm"), "peck_mm": ("peck", "mm"), "final_z": ("final depth", "mm")}


def _given(spec: dict) -> dict:
    """What cadgen set of one operation (``spec``, as ``freecad_job.py`` reads it), by ``_HELD``'s keys."""
    given = {**spec["feeds"], "stepdown_mm": spec.get("stepdown_mm"), "peck_mm": spec.get("peck_mm"),
             "final_z": spec.get("final_z")}
    return {key: float(value) for key, value in given.items() if value is not None}


def held(setup_id: str, operations, specs, report) -> list[dict]:
    """An error for each value FreeCAD holds, recomputed, that is not the one cadgen set (``report``: ``result.json``'s
    operations, each with its ``held``): an expression of FreeCAD's own puts its number back over a value, and the
    paths and the posts are then planned to it, whatever the job says."""
    where = {op.index: op.where for op in operations}
    found = []
    for spec, entry in zip(specs, report):
        given = _given(spec)
        for key, value in entry["held"].items():
            want = given.get(key)
            if want is not None and abs(value - want) > 1e-6 + 1e-4 * abs(want):
                what, unit = _HELD[key]
                found.append(finding(
                    "post", "error", "overridden", f"{where[spec['index']]}: FreeCAD holds a {what} of {value:g} "
                    f"{unit} where cadgen set {want:g}", "FreeCAD put its own value back over cadgen's on recompute, so "
                    "its paths and the G-code follow FreeCAD's, not the job's. This is a cadgen bug with this FreeCAD: "
                    "report it, with the job", [{"setup": setup_id, "operation": spec["index"]}]))
    return found


#: A posted word cadgen sets: the spindle, a feed, a drilling cycle's peck.
_WORD = re.compile(r"(?<![A-Z])([SFQ])\s*(-?\d*\.?\d+)")
#: A work offset word: G54 to G59, and the extended ones some controllers take (G54.1 P2, G59.3).
_OFFSET = re.compile(r"(?<![A-Z\d.])G(5[4-9](?:\.\d+(?:\s*P\d+)?)?)(?![\d.])")
#: An axis word: the line moves the machine.
_AXIS = re.compile(r"(?<![A-Z])[XYZ]\s*[-+]?[\d.\[#]")


def posted(setup_id: str, name: str, text: str, specs, work_offset: str) -> list[dict]:
    """An error for each spindle speed (S), feed (F) or peck (Q) the posted file ``name`` says that cadgen set for none
    of its operations (``specs``), and for its first move in any work offset but the setup's (``work_offset``, or
    before the program selects one): what FreeCAD's post writes is the program a machine runs, so it is read back,
    not taken on trust."""
    allowed = {"S": set(), "F": set(), "Q": set()}
    for spec in specs:
        given = _given(spec)
        allowed["S"].add(given["rpm"])
        allowed["F"] |= {given["feed_mm_min"], given["plunge_mm_min"]}
        if "peck_mm" in given:
            allowed["Q"].add(given["peck_mm"])
    words = {"S": "spindle speed", "F": "feed", "Q": "peck"}
    found, said, offset, reported = [], set(), None, False
    for line in text.splitlines():
        line = re.sub(r"\(.*?\)", "", line.split(";")[0]).upper()
        for letter, number in _WORD.findall(line):
            value = float(number)
            if any(abs(value - want) <= 0.5 if letter == "S" else abs(value - want) <= 1e-3 * max(1.0, abs(want))
                   for want in allowed[letter]) or (letter, value) in said:
                continue
            said.add((letter, value))
            known = ", ".join(f"{want:g}" for want in sorted(allowed[letter])) or "none"
            found.append(finding(
                "post", "error", "posted", f"{name}: the posted program says {letter}{number}, a {words[letter]} cadgen "
                f"set for none of its operations ({known})", "FreeCAD's post wrote a number cadgen did not give it, so "
                "the program would run at a speed, feed or peck nobody checked. This is a cadgen bug with this "
                "FreeCAD and post: report it, with the job", [{"setup": setup_id, "file": name}]))
        for word in _OFFSET.findall(line):
            offset = "G" + re.sub(r"\s+", "", word)
        if not reported and _AXIS.search(line) and offset != work_offset:
            reported = True
            found.append(finding(
                "post", "error", "posted", f"{name}: the posted program moves in "
                + (f"{offset}, where the setup's work offset is {work_offset}" if offset else
                   f"no work offset it selects, where the setup's is {work_offset}"),
                "FreeCAD's post selected a work offset the job did not set, so the program would cut somewhere other "
                "than the work zero the operator touched off. This is a cadgen bug with this FreeCAD and post: report "
                "it, with the job", [{"setup": setup_id, "file": name}]))
    return found


def by_severity(found) -> list[dict]:
    """Errors first, then warnings, then notes; stable within each."""
    return sorted(found, key=lambda item: _SEVERITY[item["severity"]])


def _xyz(point) -> list[float]:
    return [round(float(c), 3) + 0.0 for c in point]


def _rays_blocked(vertices, triangles, origins):
    """For each origin, whether a ray from it straight up (+Z) meets the mesh."""
    import numpy as np

    tri = np.asarray(vertices, dtype=float)[np.asarray(triangles)]
    out = np.zeros(len(origins), dtype=bool)
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    keep = np.abs(det) > 1e-12
    a, b, c, det = a[keep], b[keep], c[keep], det[keep]
    for k, (x, y, z) in enumerate(origins):
        w1 = ((x - a[:, 0]) * (c[:, 1] - a[:, 1]) - (y - a[:, 1]) * (c[:, 0] - a[:, 0])) / det
        w2 = ((b[:, 0] - a[:, 0]) * (y - a[:, 1]) - (b[:, 1] - a[:, 1]) * (x - a[:, 0])) / det
        inside = (w1 >= -1e-9) & (w2 >= -1e-9) & (w1 + w2 <= 1 + 1e-9)
        at = a[:, 2] + w1 * (b[:, 2] - a[:, 2]) + w2 * (c[:, 2] - a[:, 2])
        out[k] = bool(np.any(inside & (at > z + 1e-6)))
    return out


def face_points(vertices, triangles, mine, step: float, most: int = 2000, nudge: float = 0.0):
    """Points spread over the triangles ``mine`` selects, about ``step`` apart (at most ``most``), each ``nudge`` off
    its triangle along the triangle's outward normal (the tessellation is wound outward)."""
    import numpy as np

    tri = np.asarray(vertices, dtype=float)[np.asarray(triangles)[mine]]
    points = []
    for a, b, c in tri:
        normal = np.cross(b - a, c - a)
        length = float(np.linalg.norm(normal))
        off = normal * (nudge / length) if length > 1e-15 else np.zeros(3)
        n = max(1, int(math.ceil(max(np.linalg.norm(b - a), np.linalg.norm(c - a), np.linalg.norm(c - b)) / step)))
        for i in range(n + 1):
            for j in range(n + 1 - i):
                w1, w2 = (i + 1 / 3) / (n + 1), (j + 1 / 3) / (n + 1)
                points.append(a + w1 * (b - a) + w2 * (c - a) + off)
    points = np.asarray(points).reshape(-1, 3)
    if len(points) > most:
        points = points[np.linspace(0, len(points) - 1, most).astype(int)]
    return points


def face_edges(vertices, triangles, mine):
    """The outline of the triangles ``mine`` selects, as (M, 2, 2) segments in x and y: each edge only one of them
    has."""
    import numpy as np

    tri = np.asarray(triangles)[mine]
    edges = np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]]), axis=1)
    found, count = np.unique(edges, axis=0, return_counts=True)
    return np.asarray(vertices, dtype=float)[found[count == 1]][:, :, :2]


def reach(op, faces, holes, mesh, face_of_triangle, tool, stock_top: float, depth_z: float | None,
          walls=None) -> list[dict]:
    """The reach findings of one operation, in setup coordinates (``mesh``: the part's ``(vertices, triangles)``
    there; ``faces``: the :class:`FaceInfo` of each face it names, their normals turned into the setup; ``holes``: the
    feature reader's hole for each face of a hole, its ``reach`` turned into the setup's words; ``walls``: for a flat
    face an inside profile names, the walls it would mean). A drill naming two faces of one hole drills it once, and
    is judged once. An inside profile runs along walls: a flat face square to the tool gives it nothing to run along
    (FreeCAD traces its outline's inside, cutting nothing of the part), so it is refused, naming its walls. (One
    pocket's floor never gets here: the planner has already put its walls in its place.)"""
    import numpy as np

    found = []
    vertices, triangles = mesh
    drilled: set[str] = set()
    for info in faces:
        where = {"operation": op.index, "face": info.ref}
        if op.op == "drill":
            hole = holes.get(info.ref)
            if hole is None:
                found.append(finding("reach", "error", "not_facing", f"{op.where}: {info.ref} is not a face of a hole",
                                     "drill names a face of a hole (its wall, its counterbore's, its floor), as "
                                     "cadgen cam features lists them", [where]))
                continue
            if hole["faces"][0] in drilled:
                continue
            drilled.add(hole["faces"][0])
            if "+Z" not in hole["reach"]:
                found.append(finding("reach", "error", "unreachable",
                                     f"{op.where}: the hole {info.ref} does not open toward the tool in this setup",
                                     "drill it from a setup the hole opens toward (its reach: "
                                     f"{', '.join(hole['reach']) or 'none'})", [where]))
            elif abs(tool.diameter_mm - hole["diameter_mm"]) > 0.01:
                larger = tool.diameter_mm > hole["diameter_mm"]
                found.append(finding(
                    "reach", "error" if larger else "warning", "drill_size",
                    f"{op.where}: the hole {info.ref} is Ø{hole['diameter_mm']:g} and {tool.id} is a "
                    f"Ø{tool.diameter_mm:g} drill", "a drill larger than its hole cuts into the part: drill it with "
                    "one its size" if larger else "it leaves the hole under size: open it out after (a pocket, or "
                    "a drill its size), or drill it with one its size", [where]))
            drawn = float(hole.get("point_mm", 0.0))
            if "+Z" in hole["reach"] and not hole["through"] and tool.tip_length_mm > drawn + POINT_TOLERANCE_MM:
                short = tool.tip_length_mm - drawn
                found.append(finding(
                    "reach", "warning", "drill_point",
                    f"{op.where}: {tool.id}'s point is {tool.tip_length_mm:.2f} mm long and the hole {info.ref} is "
                    + ("drawn with a flat floor" if drawn == 0 else f"drawn with a {drawn:.2f} mm point")
                    + f": its bottom {short:.2f} mm is left a cone, short of Ø{hole['diameter_mm']:g}",
                    "the drill stops at the drawn bottom, so its longer point leaves material there: mill the floor "
                    "after (a pocket of it with an end mill that fits), or drill with the drawn point angle",
                    [where]))
            continue
        normal = info.normal
        if op.op == "profile" and op.params["side"] == "inside" and normal is not None and abs(normal[2]) > 1 - 1e-6:
            named = (walls or {}).get(info.ref) or []
            found.append(finding(
                "reach", "error", "not_facing",
                f"{op.where}: an inside profile runs along walls, and {info.ref} is a flat face"
                + (f"; the walls round it: {', '.join(named)}" if named else ""),
                "name the walls of the hole, bore, slot or pocket to cut, as cadgen cam features lists them (one "
                "pocket's floor, walled all round with nothing opening in it, stands for its walls): inside any other "
                "flat face FreeCAD traces its outline and cuts nothing of the part", [where]))
            continue
        if op.op in ("pocket", "adaptive", "face") and (normal is None or normal[2] < 1 - 1e-6):
            found.append(finding("reach", "error", "not_facing",
                                 f"{op.where}: {info.ref} is not a flat face looking up at the tool in this setup",
                                 f"{op.op} names the floors it clears down to, flat and facing the tool", [where]))
            continue
        origins = face_points(vertices, triangles, face_of_triangle == info.ordinal, max(0.25, tool.radius / 2),
                              nudge=NUDGE_MM)
        if not len(origins):
            continue
        blocked = _rays_blocked(vertices, triangles, origins)
        if blocked.any():
            share = blocked.mean()
            found.append(finding(
                "reach", "error", "unreachable",
                f"{op.where}: {share:.0%} of {info.ref} is under the part, seen from the tool's side",
                "a tool coming straight down cannot get under what overhangs it: it would cut through it. Machine "
                "that face from a setup that sees it, or name the faces the tool can reach",
                [dict(where, at=_xyz(origins[int(np.argmax(blocked))]))]))
    if depth_z is not None and stock_top - depth_z > tool.flute_length_mm + 1e-6:
        found.append(finding(
            "reach", "error", "too_deep",
            f"{op.where}: the cut goes {stock_top - depth_z:.2f} mm below the stock top, past {tool.id}'s "
            f"{tool.flute_length_mm:g} mm of flutes",
            "use a tool with longer flutes (state its flute_length_mm), or cut less deep from this side",
            [{"operation": op.index}]))
    return found


def _profile_height(tool, d):
    """The tool's lower surface above its tip at radial distance ``d`` (an array within its radius)."""
    import numpy as np

    r = tool.radius
    if tool.type == "ball":
        return r - np.sqrt(np.maximum(0.0, r * r - d * d))
    if tool.type == "bull":
        rc = tool.corner_radius_mm
        out = np.maximum(0.0, d - (r - rc))
        return rc - np.sqrt(np.maximum(0.0, rc * rc - out * out))
    if tool.type == "drill":
        return d / math.tan(math.radians(tool.point_angle / 2.0))
    return np.zeros_like(d)


def _profile_radius(tool, height):
    """The tool's radius at ``height`` above its tip (an array): :func:`_profile_height` turned round, 0 below the tip
    and the tool's radius above its profile."""
    import numpy as np

    r = tool.radius
    up = np.maximum(0.0, height)
    if tool.type == "ball":
        out = np.sqrt(np.maximum(0.0, r * r - np.square(np.maximum(0.0, r - up))))
    elif tool.type == "bull":
        rc = tool.corner_radius_mm
        out = (r - rc) + np.sqrt(np.maximum(0.0, rc * rc - np.square(np.maximum(0.0, rc - up))))
    elif tool.type == "drill":
        out = np.minimum(r, up * math.tan(math.radians(tool.point_angle / 2.0)))
    else:
        out = np.full_like(up, r)
    return np.where(height > 0.0, out, 0.0)


def _cut_reach(tool) -> float:
    """How far from its axis the tool cuts a flat floor to within :data:`DEPTH_TOLERANCE_MM`: a flat end mill its
    radius, a ball's tip far less (the ridge between two passes is the ball's scallop)."""
    import numpy as np

    return float(_profile_radius(tool, np.array([DEPTH_TOLERANCE_MM]))[0])


def _surface_points(vertices, triangles, step: float):
    """The part as the tool, coming down, can meet it: points on every face, none further than ``step`` from the next.
    A triangle is spread in rows parallel to its longest edge, ``step`` apart (its corners and edges among them; a
    sliver is one row, never a grid of its longest edge squared); a wall's, square to the tool, along its foot, each
    at its top there: the tool reaches no lower point of a wall without reaching that one."""
    import numpy as np

    tri = np.asarray(vertices, dtype=float)[np.asarray(triangles)]
    if not len(tri):
        return np.zeros((0, 3))
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    upright = np.abs(normal[:, 2]) <= 1e-9 * np.maximum(np.linalg.norm(normal, axis=1), 1e-30)
    return np.vstack([_spread(tri[~upright], step), _wall_tops(tri[upright], step)])


def _spread(tri, step: float):
    """Points over each triangle, in rows parallel to its longest edge, ``step`` apart along and across."""
    import numpy as np

    lengths = np.stack([np.linalg.norm(tri[:, (k + 1) % 3] - tri[:, k], axis=1) for k in range(3)], axis=1)
    first = np.argmax(lengths, axis=1)
    rows = np.arange(len(tri))
    a, b, c = (tri[rows, (first + k) % 3] for k in range(3))      # a to b the longest edge, c across from it
    longest = lengths[rows, first]
    across = np.linalg.norm(np.cross(b - a, c - a), axis=1) / np.maximum(longest, 1e-12)
    n_rows = np.ceil(across / step).astype(int) + 1
    owner = np.repeat(rows, n_rows)
    f = (np.arange(n_rows.sum()) - np.repeat(np.cumsum(n_rows) - n_rows, n_rows)) / np.maximum(
        np.repeat(n_rows - 1, n_rows), 1)
    start = a[owner] + f[:, None] * (c[owner] - a[owner])
    end = b[owner] + f[:, None] * (c[owner] - b[owner])
    count = np.ceil(longest[owner] * (1.0 - f) / step).astype(int) + 1
    row = np.repeat(np.arange(len(owner)), count)
    g = (np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)) / np.maximum(np.repeat(count - 1, count), 1)
    return start[row] + g[:, None] * (end[row] - start[row])


def _wall_tops(tri, step: float):
    """Points along each upright triangle's foot (its shadow, a segment), ``step`` apart, each at the triangle's
    highest over it."""
    import numpy as np

    if not len(tri):
        return np.zeros((0, 3))
    xy = tri[:, :, :2]
    spread = xy - xy.mean(axis=1, keepdims=True)
    axis = spread[np.arange(len(tri)), np.argmax(np.linalg.norm(spread, axis=2), axis=1)]
    axis /= np.maximum(np.linalg.norm(axis, axis=1, keepdims=True), 1e-12)
    u = np.einsum("tkd,td->tk", spread, axis)                       # each corner along the shadow
    u0, u1 = u.min(axis=1), u.max(axis=1)
    count = np.ceil((u1 - u0) / step).astype(int) + 1
    owner = np.repeat(np.arange(len(tri)), count)
    g = (np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)) / np.maximum(np.repeat(count - 1, count), 1)
    at = u0[owner] + g * (u1 - u0)[owner]
    top = np.full(len(at), -np.inf)
    for k in range(3):                                              # each edge's height where it spans ``at``
        ua, ub = u[owner, k], u[owner, (k + 1) % 3]
        za, zb = tri[owner, k, 2], tri[owner, (k + 1) % 3, 2]
        lo, hi = np.minimum(ua, ub), np.maximum(ua, ub)
        spans = (at >= lo - 1e-9) & (at <= hi + 1e-9)
        f = np.where(hi - lo > 1e-12, (at - ua) / np.where(np.abs(ub - ua) > 1e-12, ub - ua, 1.0), 0.0)
        z = np.where(hi - lo > 1e-12, za + np.clip(f, 0.0, 1.0) * (zb - za), np.maximum(za, zb))
        top = np.where(spans, np.maximum(top, z), top)
    centre = xy.mean(axis=1)[owner]
    return np.column_stack([centre + at[:, None] * axis[owner], top])


def _pieces(moves, select):
    """The moves ``select`` picks (each the move ending at its sample), cut into pieces no longer than
    :data:`PIECE_MM` in XY: their ends ``(a, b)``, (M, 3) each."""
    import numpy as np

    ends = np.nonzero(select)[0]
    ends = ends[ends > 0]
    a, b = moves.points[ends - 1], moves.points[ends]
    n = np.maximum(1, np.ceil(np.linalg.norm((b - a)[:, :2], axis=1) / PIECE_MM).astype(int))
    k = np.repeat(np.arange(len(ends)), n)
    f = (np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)) / np.repeat(n, n)
    step = (b - a)[k] / np.repeat(n, n)[:, None]
    return a[k] + f[:, None] * (b - a)[k], a[k] + f[:, None] * (b - a)[k] + step


def _near(points, a, b, reach: float, most: int = 1_000_000):
    """Each point of ``points`` (K, 3) within ``reach`` in XY of a piece from ``a`` to ``b`` (M, 3), in chunks: ``(k,
    at, d)``, the point's index, where the piece's path passes closest to it (a plunge, no length in XY: its lowest
    end) and how far that is in XY. Exact for a level piece; a ramp's height is the one at its closest pass."""
    import numpy as np

    if not len(points) or not len(a):
        return
    # The points in buckets half the reach wide, and each piece's bounding box, grown by the reach, in buckets.
    size = max(reach / 2.0, 0.25)
    origin = points[:, :2].min(axis=0) - size
    cells = np.floor((points[:, :2] - origin) / size).astype(np.int64)
    nx, ny = int(cells[:, 0].max()) + 2, int(cells[:, 1].max()) + 2
    keys = cells[:, 0] * ny + cells[:, 1]
    order = np.argsort(keys, kind="stable")
    sorted_keys = keys[order]
    low = np.clip(np.floor((np.minimum(a, b)[:, :2] - reach - origin) / size).astype(np.int64), 0, [nx - 1, ny - 1])
    high = np.clip(np.floor((np.maximum(a, b)[:, :2] + reach - origin) / size).astype(np.int64), -1, [nx - 1, ny - 1])
    width = int(math.ceil((PIECE_MM + 2.0 * reach) / size)) + 1
    dx, dy = (g.ravel() for g in np.meshgrid(np.arange(width), np.arange(width), indexing="ij"))
    ix, iy = low[:, :1] + dx, low[:, 1:] + dy
    wanted = (ix <= high[:, :1]) & (iy <= high[:, 1:])
    key = ix * ny + iy
    begin = np.where(wanted, np.searchsorted(sorted_keys, key, "left"), 0)
    stop = np.where(wanted, np.searchsorted(sorted_keys, key, "right"), 0)
    counts = (stop - begin).sum(axis=1)
    cumulative = np.cumsum(counts)
    first = 0
    while first < len(a):
        last = max(first + 1, int(np.searchsorted(cumulative, (cumulative[first - 1] if first else 0) + most, "right")))
        last = min(last, len(a))
        span = (stop[first:last] - begin[first:last]).ravel()
        piece = np.repeat(np.repeat(np.arange(first, last), width * width), span)
        offset = np.arange(span.sum()) - np.repeat(np.cumsum(span) - span, span)
        k = order[np.repeat(begin[first:last].ravel(), span) + offset]
        first = last
        pa, ab = a[piece], b[piece] - a[piece]
        level = np.einsum("nd,nd->n", ab[:, :2], ab[:, :2])
        t = np.where(level > 1e-12, np.clip(np.einsum("nd,nd->n", points[k, :2] - pa[:, :2], ab[:, :2])
                                            / np.maximum(level, 1e-12), 0.0, 1.0), (ab[:, 2] < 0).astype(float))
        at = pa + t[:, None] * ab
        d = np.hypot(points[k, 0] - at[:, 0], points[k, 1] - at[:, 1])
        close = d <= reach
        yield k[close], at[close], d[close]


def _lowest_tip(a, b, points, reach: float):
    """For each of ``points`` (K, 3): the lowest any piece from ``a`` to ``b`` takes the tool's tip within ``reach``
    of it in XY, or more (the pieces' boxes, on a grid half the reach wide); ``inf`` where none comes near."""
    import numpy as np

    size = max(reach / 2.0, 0.25)
    origin = np.minimum(np.minimum(a, b)[:, :2].min(axis=0), points[:, :2].min(axis=0)) - reach - size
    top = np.maximum(np.maximum(a, b)[:, :2].max(axis=0), points[:, :2].max(axis=0)) + reach + size
    shape = np.ceil((top - origin) / size).astype(int) + 1
    lowest = np.full(int(shape[0]) * int(shape[1]), np.inf)
    low = np.floor((np.minimum(a, b)[:, :2] - reach - origin) / size).astype(np.int64)
    high = np.floor((np.maximum(a, b)[:, :2] + reach - origin) / size).astype(np.int64)
    width = int(math.ceil((PIECE_MM + 2.0 * reach) / size)) + 1
    tip = np.minimum(a[:, 2], b[:, 2])
    for dx in range(width):
        for dy in range(width):
            ix, iy = low[:, 0] + dx, low[:, 1] + dy
            ok = (ix <= high[:, 0]) & (iy <= high[:, 1])
            np.minimum.at(lowest, ix[ok] * shape[1] + iy[ok], tip[ok])
    cells = np.floor((points[:, :2] - origin) / size).astype(np.int64)
    return lowest[cells[:, 0] * shape[1] + cells[:, 1]]


def _gouge(moves, select, tool, surface):
    """How far the tool, on the moves ``select`` picks, comes into the part at worst, and where it is then: ``(point,
    depth)`` or None. A point of the part's ``surface`` (:func:`_surface_points`) is in the tool where it stands above
    the tool's lower surface and inside its radius at that height; it is as deep in the part as the less of the two
    (a wall beside the tool cut 0.2 mm under is 0.2 mm, however tall), or, under the tool's axis, as deep as the tool
    would have to rise."""
    import numpy as np

    a, b = _pieces(moves, select)
    if not len(a) or not len(surface):
        return None
    r = tool.radius
    # Only a point above the lowest the tool comes near it can be in it.
    points = surface[surface[:, 2] > _lowest_tip(a, b, surface, r) + GOUGE_TOLERANCE_MM]
    worst = None
    for k, at, d in _near(points, a, b, r):
        height = points[k, 2] - at[:, 2]
        up = height - _profile_height(tool, d)
        side = _profile_radius(tool, height) - d
        depth = np.where((up > GOUGE_TOLERANCE_MM) & (side > GOUGE_TOLERANCE_MM),
                         np.where(d <= SURFACE_STEP_MM, up, np.minimum(up, side)), -np.inf)
        if not len(depth):
            continue
        i = int(np.argmax(depth))
        if depth[i] > GOUGE_TOLERANCE_MM and (worst is None or depth[i] > worst[1]):
            worst = (at[i], float(depth[i]))
    return worst


def _fits(points, edges, radius: float, reach: float, leave: float):
    """Which of a floor's ``points`` (K, 2) a tool of ``radius`` can cut: within its ``reach`` (:func:`_cut_reach`) of
    a centre whose whole disk, and ``leave`` beside it, is on the floor -- the floor's opening by the tool, short of
    :data:`REACH_TOLERANCE_MM` each way. A point outside it (a sharp inside corner, a neck narrower than the tool, a
    ball's fillet at the wall) is the tool's to leave, never FreeCAD's."""
    import numpy as np

    a, b = edges[:, 0], edges[:, 1]
    along = b - a
    t = np.clip(np.einsum("kmd,md->km", points[:, None, :] - a, along) / np.maximum(
        np.einsum("md,md->m", along, along), 1e-12), 0.0, 1.0)
    clear = np.linalg.norm(points[:, None, :] - (a + t[..., None] * along), axis=2).min(axis=1)
    centres = points[clear >= radius + leave + REACH_TOLERANCE_MM]
    if not len(centres):
        return np.zeros(len(points), dtype=bool)
    near = np.zeros(len(points), dtype=bool)
    for chunk in range(0, len(centres), 500):
        gap = np.linalg.norm(points[:, None, :] - centres[None, chunk:chunk + 500], axis=2)
        near |= (gap <= max(0.0, reach - REACH_TOLERANCE_MM)).any(axis=1)
    return near


def _uncut(moves, op, tool, targets) -> list[tuple[str, float | None, float | None]]:
    """``(ref, share, ridge)`` of each of the ``targets`` (:class:`Target`) no cutting move of ``op`` reaches at its
    final depth, ``share`` None: a hole no feed goes down the axis of, a floor or face no tool comes over, a wall no
    tool runs beside; and of each floor it cut only part of what the tool fits (a face: of all of it), ``share`` the
    part it left. A point of a floor or a face is cut where the tool's lower surface comes within
    :data:`DEPTH_TOLERANCE_MM` of it, so a ball's passes too far apart leave it uncut between them: ``ridge`` is the
    highest it left standing there, None where the tool never came over it."""
    import numpy as np

    a, b = _pieces(moves, (moves.op == op.index) & ~moves.rapid)
    if not len(a) or not targets:
        return []
    missed = []
    for target in targets:
        if target.axis_xy is not None:
            axis = np.array([[*target.axis_xy, target.final_z]])
            down = any(np.any(at[:, 2] <= target.final_z + DEPTH_TOLERANCE_MM)
                       for _, at, _ in _near(axis, a, b, DEPTH_TOLERANCE_MM))
            if not down:
                missed.append((target.ref, None, None))
            continue
        points = target.points
        if target.wall:
            beside = np.zeros(len(points), dtype=bool)
            for k, at, _ in _near(points, a, b, tool.radius + target.leave_mm + REACH_TOLERANCE_MM):
                beside[k[at[:, 2] <= target.final_z + DEPTH_TOLERANCE_MM]] = True
            if not beside.any():
                missed.append((target.ref, None, None))
            continue
        lowest = np.full(len(points), np.inf)
        for k, at, d in _near(points, a, b, tool.radius):
            np.minimum.at(lowest, k, at[:, 2] + _profile_height(tool, d))
        left = lowest - target.final_z
        hit = left <= DEPTH_TOLERANCE_MM
        if not hit.any():
            missed.append((target.ref, None, None))
            continue
        fits = np.ones(len(points), dtype=bool) if target.edges is None else _fits(
            points[:, :2], target.edges, tool.radius, _cut_reach(tool), target.leave_mm)
        uncut = fits & ~hit
        if uncut.any():
            standing = left[uncut & np.isfinite(left)]
            missed.append((target.ref, float(uncut.sum() / fits.sum()),
                           float(standing.max()) if len(standing) else None))
    return missed


def _dense(points, step: float):
    """The polyline through ``points`` with no gap over ``step``: each segment split evenly."""
    import numpy as np

    if len(points) < 2:
        return points
    gaps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    counts = np.maximum(1, np.ceil(gaps / step).astype(int))
    pieces = [points[:1]]
    for k, n in enumerate(counts):
        f = (np.arange(1, n + 1) / n)[:, None]
        pieces.append(points[k] + f * (points[k + 1] - points[k]))
    return np.vstack(pieces)


def _cells(here, radius: float, low, cell: float):
    """For points ``here`` (P, 3): the grid cells round each out to ``radius`` and a little past, and each cell
    centre's distance from the point in XY, ``(i, j, d)`` each (P, K)."""
    import numpy as np

    span = int(math.ceil(radius / cell)) + 1
    offsets = np.arange(-span, span + 1)
    di, dj = (a.ravel() for a in np.meshgrid(offsets, offsets, indexing="ij"))
    i = np.floor((here[:, :1] - low[0]) / cell).astype(int) + di[None, :]
    j = np.floor((here[:, 1:2] - low[1]) / cell).astype(int) + dj[None, :]
    return i, j, np.hypot(low[0] + (i + 0.5) * cell - here[:, :1], low[1] + (j + 0.5) * cell - here[:, 1:2])


def _disk(tool, cell: float, here, low):
    """For points ``here`` (P, 3): the grid cells under the tool's end and the tool's lower surface over each,
    ``(i, j, height, inside)`` each (P, K): ``inside`` the cells within the tool's radius."""
    import numpy as np

    i, j, d = _cells(here, tool.radius, low, cell)
    return i, j, here[:, 2:3] + _profile_height(tool, np.minimum(d, tool.radius)), d <= tool.radius


def _rapid_into_stock(moves, operations, tools, stock_low, stock_high, low, shape, cell: float):
    """The first rapid that runs into stock no move before it has cut: ``(operation, point, depth)`` or None.

    The stock is a height on the grid, its top to start with; each cutting move lowers it to the tool's lower surface
    along its way, in program order, so a rapid inside a pocket already cleared (FreeCAD's adaptive links passes so)
    is not a hit, and one through material is."""
    import numpy as np

    nx, ny = shape
    xs = low[0] + (np.arange(nx) + 0.5) * cell
    ys = low[1] + (np.arange(ny) + 0.5) * cell
    over = ((xs >= stock_low[0])[:, None] & (xs <= stock_high[0])[:, None]
            & (ys >= stock_low[1])[None, :] & (ys <= stock_high[1])[None, :])
    stock = np.where(over, float(stock_high[2]), -np.inf)
    tool_of = {op.index: tools[op.tool] for op in operations}
    # Runs of moves of one kind and one operation, each move by the sample it ends at.
    ends = np.arange(1, len(moves.points))
    change = (moves.rapid[2:] != moves.rapid[1:-1]) | (moves.op[2:] != moves.op[1:-1])
    for run in np.split(ends, np.nonzero(change)[0] + 1):
        if not len(run):
            continue
        tool = tool_of.get(int(moves.op[run[0]]))
        if tool is None:
            continue
        points = _dense(moves.points[run[0] - 1:run[-1] + 1], cell)
        for chunk in range(0, len(points), 2000):
            here = points[chunk:chunk + 2000]
            i, j, height, inside = _disk(tool, cell, here, low)
            inside &= (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
            ii, jj = np.clip(i, 0, nx - 1), np.clip(j, 0, ny - 1)
            if moves.rapid[run[0]]:
                depth = np.where(inside, stock[ii, jj] - height, -np.inf).max(axis=1)
                k = int(np.argmax(depth))
                if depth[k] > RAPID_TOLERANCE_MM:
                    return int(moves.op[run[0]]), here[k], float(depth[k])
            else:
                np.minimum.at(stock, (ii[inside], jj[inside]), height[inside])
    return None


def check_moves(setup_id: str, moves, operations, tools, mesh, stock_low, stock_high, machine,
                targets=None) -> list[dict]:
    """The findings of one setup's moves (setup coordinates): ``operations`` its :class:`Operation` list, ``mesh``
    the part's ``(vertices, triangles)`` there, the stock's box from ``stock_low`` to ``stock_high``, ``targets``
    each operation's :class:`Target` list by its index."""
    import numpy as np

    found = []
    vertices, triangles = mesh
    moving = np.concatenate([[False], np.any(np.diff(moves.points, axis=0) != 0, axis=1)])
    for op in operations:
        mine = moves.op == op.index
        if not np.any(mine & moving & ~moves.rapid):
            found.append(finding("empty_operation", "error", "empty_operation",
                                 f"{op.where}: FreeCAD planned no cut for this {op.op}",
                                 "the faces it names give it nothing to cut with this tool: check the faces "
                                 "(cadgen cam features) and that the tool fits them", [{"operation": op.index}]))
    for op in operations:
        what = "drilled nothing down" if op.op == "drill" else "cut nothing at the operation's depth over"
        for ref, share, ridge in _uncut(moves, op, tools[op.tool], (targets or {}).get(op.index, ())):
            said = what if share is None else f"left {share:.0%} of what the tool fits uncut on"
            standing = "" if ridge is None else f", standing up to {ridge:.2f} mm between its passes"
            found.append(finding(
                "coverage", "error", "uncut", f"{op.where}: FreeCAD {said} {ref}{standing}",
                "FreeCAD leaves out what the tool does not fit, and says nothing: a floor, slot or hole narrower "
                "than the tool, a hole it did not take. Cut it in its own operation with a tool that fits it, or "
                "leave it out of this one. A floor counts as cut where the tool comes within "
                f"{DEPTH_TOLERANCE_MM:g} mm of it: a ball's passes leave a ridge between them (its scallop, "
                "r - sqrt(r² - (stepover / 2)²) high), which a smaller stepover or a flat end mill cuts down",
                [{"setup": setup_id, "operation": op.index, "face": ref}]))
    tri = np.asarray(vertices, dtype=float)[np.asarray(triangles)]
    faces_mm2 = float(np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum()) / 2.0
    surface = _surface_points(vertices, triangles, max(SURFACE_STEP_MM, math.sqrt(faces_mm2 / MAX_CELLS)))
    for op in operations:
        hit = _gouge(moves, moves.op == op.index, tools[op.tool], surface)
        if hit is not None:
            point, depth = hit
            found.append(finding(
                "gouge", "error", "gouge",
                f"{op.where}: the tool comes {depth:.2f} mm into the part",
                "FreeCAD's path for this operation runs the tool into the part (often under an overhang it was "
                "not told about): name only faces the tool can reach, or use a smaller tool",
                [{"setup": setup_id, "operation": op.index, "at": _xyz(point)}]))
    # The stock a rapid may not run into, on a grid finer than the smallest tool.
    path_low = np.minimum(moves.points.min(axis=0), np.asarray(vertices).min(axis=0))
    path_high = np.maximum(moves.points.max(axis=0), np.asarray(vertices).max(axis=0))
    cell = max(0.05, min(0.5, min(tools[op.tool].radius for op in operations) / 4.0))
    margin = max(tools[op.tool].radius for op in operations) + cell
    low, high = path_low - margin, path_high + margin
    area = (high[0] - low[0]) * (high[1] - low[1])
    if area / cell ** 2 > MAX_CELLS:
        cell = math.sqrt(area / MAX_CELLS)
    shape = (max(1, int(math.ceil((high[0] - low[0]) / cell))), max(1, int(math.ceil((high[1] - low[1]) / cell))))
    hit = _rapid_into_stock(moves, operations, tools, stock_low, stock_high, low, shape, cell)
    if hit is not None:
        k, point, depth = hit
        found.append(finding("rapid_into_stock", "error", "rapid_into_stock",
                             f"setup {setup_id}: a rapid runs {depth:.2f} mm into stock not yet cut",
                             "a rapid at full speed through material breaks the tool: raise retract_mm, or cut that "
                             "material first", [{"setup": setup_id, "operation": k, "at": _xyz(point)}]))
    if machine.travel_mm is not None:
        span = moves.points.max(axis=0) - moves.points.min(axis=0)
        over = [f"{axis} {s:.1f} mm of {t:g}" for axis, s, t in zip("XYZ", span, machine.travel_mm) if s > t + 1e-6]
        if over:
            found.append(finding("travel", "error", "travel",
                                 f"setup {setup_id}: the moves span more than the machine travels ({', '.join(over)})",
                                 "the part does not fit this machine in this setup", [{"setup": setup_id}]))
    return found
