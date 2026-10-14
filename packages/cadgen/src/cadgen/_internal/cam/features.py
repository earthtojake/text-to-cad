"""The machining reading of a part: what ``cadgen cam features`` lists and what operations look up.

:func:`read_features` returns ``{"faces", "holes", "floors", "profiles"}`` (lists of dicts, the shapes
:class:`~cadgen.results.CamFeaturesResult` documents):

* every face, with a plain ``reading`` ("flat floor at Z 12, facing +Z", "hole wall Ø5 along Z");
* holes: the hole-wall cylinders grouped by axis line and radius, kept where they wrap (nearly) all the way round their
  axis (a pocket's rounded corner, a fillet or a slot's end is not a hole: its faces read "rounded corner"), then split
  where material stands between them along the axis (a split cylinder is one hole; two blind holes either side of a web
  are two), with their diameter, depth, axis (pointing out of the opening), opening centre and whether they go through;
  whether an end is open is asked of the exact solid (OCCT's classifier), off the axis so a drill point's cone reads as
  a bottom. A counterbore (a wider coaxial cylinder stepped onto an open end) and a countersink (a cone widening out of
  one) are part of the hole: it opens where they open on the part, ``depth_mm`` runs from there, and its entry carries
  ``counterbore`` ``{diameter_mm, depth_mm}`` and ``countersink`` ``{diameter_mm, angle_deg}``; a blind hole's drawn
  drill point is ``point_mm`` (its length past the full diameter). ``faces`` lists the walls first, then the
  counterbore's wall and shoulder, the cones and a blind hole's floor, so any of them names the hole. ``reach`` lists
  the ways out of its open ends (``+Z`` ...) that a ray from just past the end, on the axis and near the wall, leaves
  the part along: a hole opening on a floor under a roof lists none;
* floors: the flat faces square to an axis, with ``kind`` top, floor, bottom or underside, and for a +Z floor below
  the top its pocket: the walls around it, their depth and the islands inside it;
* a DXF's profiles: outline size, area and holes (a round hole with its diameter).

:func:`holes` is the grouping alone, for the drilling operations. Stdlib at import; numpy and OCP inside.
"""

from __future__ import annotations

import math

__all__ = ["axis_word", "direction_word", "holes", "read_features"]

_AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
_COS5 = math.cos(math.radians(5.0))


def _g(value: float, digits: int = 3) -> str:
    return f"{round(float(value), digits):g}"


def axis_word(vector) -> str | None:
    """``+Z``, ``-X``, ... when ``vector`` is within 5° of an axis, else ``None``."""
    for name, axis in _AXES.items():
        dot = sum(a * b for a, b in zip(vector, axis))
        if dot > _COS5:
            return f"+{name}"
        if dot < -_COS5:
            return f"-{name}"
    return None


def _vec(vector) -> str:
    return "(" + ", ".join(f"{v:.2f}" for v in vector) + ")"


def holes(part) -> list[dict]:
    """The part's holes: hole-wall cylinders grouped by axis line and radius, split at webs (:func:`_clusters`); a
    wider coaxial cylinder stepped onto an open end is that hole's counterbore and a cone widening out of it its
    countersink (both part of the hole, which opens where they open), a cone closing a blind end its drawn point."""
    import numpy as np

    groups: list[dict] = []
    for info in part.faces.values():
        if info.surface != "cylinder" or not info.hole:
            continue
        d = np.asarray(info.axis, dtype=float)
        p = np.asarray(info.axis_point, dtype=float)
        for group in groups:
            gd, gp = group["d"], group["p"]
            if (abs(abs(float(gd @ d)) - 1.0) < 1e-6 and abs(group["r"] - info.radius_mm) < 1e-4
                    and np.linalg.norm(np.cross(p - gp, gd)) < 1e-4):
                group["faces"].append(info)
                break
        else:
            groups.append({"d": d / np.linalg.norm(d), "p": p, "r": float(info.radius_mm), "faces": [info]})
    triangles = np.asarray(part.triangles)
    owners = np.asarray(part.face_of_triangle)
    vertices = np.asarray(part.vertices)
    touch = max(1e-3, 2.0 * float(getattr(part, "deflection_mm", 0.01)))
    points = _FacePoints(part, triangles, owners, vertices)
    runs = []
    for group in groups:
        d, p, r = group["d"], group["p"], group["r"]
        side = np.cross(d, [1.0, 0.0, 0.0] if abs(d[0]) < 0.9 else [0.0, 1.0, 0.0])
        side = side / np.linalg.norm(side)
        # A hole's wall goes (nearly) all the way round its axis: a pocket's rounded corner, a fillet or a slot's
        # end is a part of a cylinder, not a hole to drill.
        if _wrap_deg(points, group["faces"], d, p, side) < HOLE_WRAP_DEG:
            continue
        for faces, t_low, t_high in _clusters(part, group["faces"], d, p, r, side, triangles, owners, vertices, touch):
            runs.append(_run(part, faces, d, p, r, side, t_low, t_high))
    runs = _counterbores(part, runs, points, touch)
    out = []
    for run in runs:
        _cones(part, run, points, touch)
        out.append(_hole(part, run, points, touch))
    out.sort(key=lambda hole: int(hole["faces"][0].rsplit("f", 1)[1]))
    return out


#: How far round its axis a concave cylinder must wrap to be a hole (degrees): a coarse tessellation of a full hole
#: still covers 300 and more; a pocket corner covers 90, a slot's end 180.
HOLE_WRAP_DEG = 270.0


def _wrap_deg(points, faces, d, p, side) -> float:
    """How far round the axis ``d`` through ``p`` the cylinder faces ``faces`` reach (degrees): the circle less its
    widest gap between their tessellation vertices."""
    import numpy as np

    other = np.cross(d, side)
    xyz = [points.of(info.ordinal) for info in faces]
    xyz = np.vstack([v for v in xyz if len(v)]) if any(len(v) for v in xyz) else np.zeros((0, 3))
    if len(xyz) < 3:
        return 0.0
    rel = xyz - p
    angles = np.sort(np.degrees(np.arctan2(rel @ other, rel @ side)) % 360.0)
    gaps = np.diff(np.concatenate([angles, [angles[0] + 360.0]]))
    return float(360.0 - gaps.max())


class _FacePoints:
    """Each face's tessellation vertices (part mm), gathered once."""

    def __init__(self, part, triangles, owners, vertices):
        import numpy as np

        self.vertices = vertices
        order = np.argsort(owners, kind="stable")
        ordinals, starts = np.unique(owners[order], return_index=True)
        bounds = list(starts[1:]) + [len(order)]
        self._rows = {int(o): order[s:e] for o, s, e in zip(ordinals, starts, bounds)}
        self._triangles = triangles
        self._cache: dict = {}

    def of(self, ordinal: int):
        import numpy as np

        if ordinal not in self._cache:
            rows = self._rows.get(int(ordinal))
            used = np.unique(self._triangles[rows]) if rows is not None else np.zeros(0, dtype=int)
            self._cache[ordinal] = self.vertices[used]
        return self._cache[ordinal]

    def along(self, ordinal: int, run):
        """The face's vertices as ``(t along the run's axis, distance from it)``."""
        import numpy as np

        rel = self.of(ordinal) - run.p
        t = rel @ run.d
        return t, np.linalg.norm(rel - np.outer(t, run.d), axis=1)


class _Run:
    """One hole being read: its wall faces on one axis line (``d`` a unit vector, ``p`` a point on it), its span
    ``low..high`` along ``d``, which ends are open, and how far out each end opens on the part (``outer``: past a
    counterbore or a countersink), with the faces, sizes and point that join it."""

    def __init__(self, faces, d, p, r, side, low, high, open_low, open_high):
        self.faces, self.d, self.p, self.r, self.side = list(faces), d, p, r, side
        self.low, self.high, self.open_low, self.open_high = low, high, open_low, open_high
        self.outer = {"low": low, "high": high}
        #: The radius the hole has at each outer end (a counterbore's, else its own).
        self.end_r = {"low": r, "high": r}
        #: The ends a counterbore was folded into; the faces that joined the walls (counterbore, shoulder, cones).
        self.bored: set[str] = set()
        self.faces_extra: list[str] = []
        self.cone_refs: list[str] = []
        self.counterbore: dict | None = None
        self.countersink: dict | None = None
        self.point_mm = 0.0

    def t(self, point) -> float:
        import numpy as np

        return float((np.asarray(point, dtype=float) - self.p) @ self.d)

    def coaxial(self, d, p) -> bool:
        import numpy as np

        return abs(abs(float(self.d @ d)) - 1.0) < 1e-6 and float(np.linalg.norm(np.cross(p - self.p, self.d))) < 1e-3


def _run(part, faces, d, p, r, side, t_low, t_high) -> _Run:
    """Whether each end is open, asked of the exact solid."""
    import numpy as np

    # Off the axis at 0.7 r and 0.3 r beyond each end: a drill point's cone is air on the axis but material there.
    offset = side * 0.7 * r
    reach = max(0.05, 0.3 * r)
    probes = np.array([p + d * (t_high + reach) + offset, p + d * (t_low - reach) + offset])
    closed_high, closed_low = (bool(v) for v in part.classify(probes))
    return _Run(faces, d, p, r, side, t_low, t_high, not closed_low, not closed_high)


def _counterbores(part, runs: list[_Run], points: _FacePoints, touch: float) -> list[_Run]:
    """Fold each counterbore into the hole under it: a wider cylinder on the hole's line whose one end sits on the
    hole's open end, with material (the shoulder) round the hole there, and whose other end opens on the part."""
    import numpy as np

    taken: set[int] = set()
    for k, hole in sorted(enumerate(runs), key=lambda item: item[1].r):
        if k in taken:
            continue
        for j, bore in enumerate(runs):
            if j == k or j in taken or bore.r <= hole.r + 1e-4 or not hole.coaxial(bore.d, bore.p):
                continue
            ends = sorted(((hole.t(bore.p + bore.d * bore.low), bore.open_low),
                           (hole.t(bore.p + bore.d * bore.high), bore.open_high)))
            (b_lo, open_lo), (b_hi, open_hi) = ends
            for name in ("high", "low"):
                if name in hole.bored:
                    continue
                if name == "high":
                    step, far, far_open, inside = hole.high, b_hi, open_hi, -1.0
                    near = b_lo
                    hole_open = hole.open_high
                else:
                    step, far, far_open, inside = hole.low, b_lo, open_lo, 1.0
                    near = b_hi
                    hole_open = hole.open_low
                if not (hole_open and far_open and abs(near - step) < touch):
                    continue
                # The shoulder: material round the hole just inside the step.
                depth = min(0.5, 0.3 * (hole.high - hole.low))
                probe = hole.p + hole.d * (step + inside * depth) + hole.side * 0.5 * (hole.r + bore.r)
                if not bool(part.classify(np.asarray([probe]))[0]):
                    continue
                taken.add(j)
                hole.bored.add(name)
                hole.outer[name] = far
                hole.end_r[name] = bore.r
                hole.counterbore = {"diameter_mm": round(2 * bore.r, 4), "depth_mm": round(abs(far - near), 4)}
                hole.faces_extra += [info.ref for info in sorted(bore.faces, key=lambda info: info.ordinal)]
                hole.faces_extra += _flats(part, hole, points, step, bore.r, touch)
                break
    return [run for k, run in enumerate(runs) if k not in taken]


def _flats(part, run: _Run, points: _FacePoints, at: float, radius: float, touch: float) -> list[str]:
    """The flat faces square to the run's axis at ``at`` and within ``radius`` of it (a shoulder, a floor)."""
    import numpy as np

    found = []
    for ordinal, info in sorted(part.faces.items()):
        if info.surface != "plane" or info.normal is None:
            continue
        if abs(abs(float(np.asarray(info.normal) @ run.d)) - 1.0) > 1e-6:
            continue
        if abs(run.t(info.center_mm) - at) > touch:
            continue
        _, radial = points.along(ordinal, run)
        if len(radial) and float(radial.max()) <= radius + touch:
            found.append(info.ref)
    return found


def _cones(part, run: _Run, points: _FacePoints, touch: float) -> None:
    """A cone on the run's line at an open end widening outward (a countersink: the hole opens at its top) or at a
    closed end narrowing inward (a drawn drill point: ``point_mm`` its length)."""
    import numpy as np

    for ordinal, info in sorted(part.faces.items()):
        if info.surface != "cone" or info.axis is None:
            continue
        if not run.coaxial(np.asarray(info.axis, dtype=float), np.asarray(info.axis_point, dtype=float)):
            continue
        t, radial = points.along(ordinal, run)
        if not len(t):
            continue
        c_lo, c_hi = float(t.min()), float(t.max())
        r_lo = float(radial[t <= c_lo + touch].mean())
        r_hi = float(radial[t >= c_hi - touch].mean())
        fit = max(0.05, 4 * touch)
        for name, sign in (("high", 1.0), ("low", -1.0)):
            near, far, r_near, r_far = (c_lo, c_hi, r_lo, r_hi) if sign > 0 else (c_hi, c_lo, r_hi, r_lo)
            is_open = run.open_high if name == "high" else run.open_low
            if is_open:
                if abs(near - run.outer[name]) > touch or abs(r_near - run.end_r[name]) > fit or r_far <= r_near:
                    continue
                if run.countersink is None:
                    from OCP.BRepAdaptor import BRepAdaptor_Surface

                    angle = 2.0 * math.degrees(abs(BRepAdaptor_Surface(part.ocp_face(ordinal)).Cone().SemiAngle()))
                    run.countersink = {"diameter_mm": round(2 * r_far, 4), "angle_deg": round(angle, 2)}
                run.outer[name] = far
                run.end_r[name] = r_far
                run.cone_refs.append(info.ref)
                break
            end = run.high if name == "high" else run.low
            if abs(near - end) <= touch and abs(r_near - run.r) <= fit and r_far < r_near:
                run.point_mm = max(run.point_mm, abs(far - near))
                run.cone_refs.append(info.ref)
                break


def _rays_clear(part, origins, direction) -> bool:
    """No ray from ``origins`` along ``direction`` meets the part (its tessellation): the way out is clear."""
    import numpy as np

    d = np.asarray(direction, dtype=float)
    d = d / np.linalg.norm(d)
    u = np.cross(d, [1.0, 0.0, 0.0] if abs(d[0]) < 0.9 else [0.0, 1.0, 0.0])
    u = u / np.linalg.norm(u)
    w = np.cross(d, u)
    vertices = np.asarray(part.vertices)
    flat = np.column_stack([vertices @ u, vertices @ w, vertices @ d])
    tri = flat[np.asarray(part.triangles)]                      # (T, 3, 3): u, w, along
    origins = np.asarray(origins, dtype=float)
    o = np.column_stack([origins @ u, origins @ w, origins @ d])
    lo, hi = tri[:, :, :2].min(axis=1), tri[:, :, :2].max(axis=1)
    near = ((lo[:, 0] <= o[:, 0].max() + 1e-9) & (hi[:, 0] >= o[:, 0].min() - 1e-9)
            & (lo[:, 1] <= o[:, 1].max() + 1e-9) & (hi[:, 1] >= o[:, 1].min() - 1e-9)
            & (tri[:, :, 2].max(axis=1) > o[:, 2].min()))
    tri = tri[near]
    if not len(tri):
        return True
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    det = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    keep = np.abs(det) > 1e-12
    a, b, c, det = a[keep], b[keep], c[keep], det[keep]
    for x, y, z in o:
        w1 = ((x - a[:, 0]) * (c[:, 1] - a[:, 1]) - (y - a[:, 1]) * (c[:, 0] - a[:, 0])) / det
        w2 = ((b[:, 0] - a[:, 0]) * (y - a[:, 1]) - (b[:, 1] - a[:, 1]) * (x - a[:, 0])) / det
        inside = (w1 >= -1e-9) & (w2 >= -1e-9) & (w1 + w2 <= 1 + 1e-9)
        at = a[:, 2] + w1 * (b[:, 2] - a[:, 2]) + w2 * (c[:, 2] - a[:, 2])
        if bool(np.any(inside & (at > z + 1e-6))):
            return False
    return True


def direction_word(vector) -> str:
    """``+Z`` for a vector within 5° of an axis, else the vector to two places."""
    return axis_word(vector) or _vec(vector)


def _clusters(part, faces, d, p, r, side, triangles, owners, vertices, touch):
    """One axis-and-radius group split into holes, ``[(faces, t_low, t_high)]`` along the axis: faces whose spans
    touch are one hole (a split cylinder), and so are spans with air between them (a slot or a cavity the hole
    crosses); material between two spans (a web) makes two holes, so blind holes from both sides of a wall are
    never read as one through hole. The gap is judged at its middle, on the axis and at 0.7 r round it."""
    import numpy as np

    spans = []
    for info in faces:
        used = np.unique(triangles[owners == info.ordinal])
        t = (vertices[used] - p) @ d
        spans.append((float(t.min()), float(t.max()), info))
    spans.sort(key=lambda span: span[0])
    across = np.cross(d, side)
    clusters: list[list] = []
    for low, high, info in spans:
        if clusters and low > clusters[-1][2] + touch:
            centre = p + d * (0.5 * (clusters[-1][2] + low))
            probes = [centre] + [centre + sign * 0.7 * r * axis for axis in (side, across) for sign in (1.0, -1.0)]
            if bool(np.any(part.classify(np.asarray(probes)))):
                clusters.append([[info], low, high])
                continue
        if clusters:
            clusters[-1][0].append(info)
            clusters[-1][2] = max(clusters[-1][2], high)
        else:
            clusters.append([[info], low, high])
    return [(cluster[0], cluster[1], cluster[2]) for cluster in clusters]


def _hole(part, run: _Run, points: _FacePoints, touch: float) -> dict:
    """One hole's entry, its axis pointing out of the opening, its opening where it opens on the part (the top of
    its counterbore or countersink); ``reach`` the ways out of its open ends that no part of the part covers."""
    import numpy as np

    d, p, r = run.d, run.p, run.r
    through = run.open_low and run.open_high
    if through:
        # Point the axis the way a tool comes in: toward +Z, else +X, else +Y.
        reference = np.asarray(_AXES["Z"])
        for axis in (_AXES["Z"], _AXES["X"], _AXES["Y"]):
            if abs(float(np.asarray(axis) @ d)) > 1e-6:
                reference = np.asarray(axis)
                break
        direction = d if float(reference @ d) > 0 else -d
    else:
        direction = d if run.open_high else -d
    up = float(direction @ d) > 0
    opening_t = run.outer["high"] if up else run.outer["low"]
    if through:
        bottom_t = run.outer["low"] if up else run.outer["high"]
    else:
        bottom_t = run.low if up else run.high
    opening = p + d * opening_t
    bottom = p + d * bottom_t
    depth = abs(opening_t - bottom_t)
    word = direction_word(direction)
    # A ray out of each open end, from just past it on the axis and at 0.7 r round it: the part may stand over it
    # (a roof over the floor it opens in), and then no tool comes in along the axis from that side.
    across = np.cross(d, run.side)
    reach = []
    for name, out in (("high", d), ("low", -d)):
        if not (run.open_high if name == "high" else run.open_low):
            continue
        start = p + d * run.outer[name] + out * max(0.05, 0.3 * r)
        origins = [start] + [start + sign * 0.7 * r * axis for axis in (run.side, across) for sign in (1.0, -1.0)]
        if _rays_clear(part, origins, out):
            reach.append(direction_word(out))
    refs = [info.ref for info in sorted(run.faces, key=lambda info: info.ordinal)]
    refs += run.faces_extra + run.cone_refs
    if not through:
        refs += [ref for ref in _flats(part, run, points, bottom_t, r, touch) if ref not in refs]
    entry = {
        "faces": refs, "diameter_mm": round(2 * r, 4), "depth_mm": round(depth, 4),
        "axis": [round(float(v), 6) + 0.0 for v in direction], "axis_word": word,
        "center_mm": [round(float(v), 4) + 0.0 for v in opening],
        "bottom_mm": [round(float(v), 4) + 0.0 for v in bottom], "through": through, "reach": reach,
    }
    extra = []
    if run.counterbore:
        entry["counterbore"] = run.counterbore
        extra.append(f"counterbore Ø{_g(run.counterbore['diameter_mm'])} x {_g(run.counterbore['depth_mm'])}")
    if run.countersink:
        entry["countersink"] = run.countersink
        extra.append(f"countersink Ø{_g(run.countersink['diameter_mm'])} x {_g(run.countersink['angle_deg'])}°")
    if run.point_mm > 0 and not through:
        entry["point_mm"] = round(run.point_mm, 4)
        extra.append(f"drill point {_g(run.point_mm)} long")
    reading = (f"Ø{_g(2 * r)} x {_g(depth)} {'through' if through else 'deep, blind'} along {word} "
               f"at {_vec(opening).replace('.00', '')}")
    if extra:
        reading += ", " + ", ".join(extra)
    if not reach:
        reading += "; the part covers its opening along its axis, so no tool reaches it from there"
    elif through and len(reach) == 1:
        reading += f"; reached from {reach[0]} only (the part covers its other end)"
    entry["reading"] = reading
    return entry


def _pocket(part, ordinal: int, z: float) -> dict | None:
    """The walls around a +Z floor below the top, their height, and the islands inside it."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_WIRE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

    shape = part.shape.wrapped
    ancestors = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, ancestors)
    floor = part.ocp_face(ordinal)
    walls: set[int] = set()
    explorer = TopExp_Explorer(floor, TopAbs_EDGE)
    while explorer.More():
        faces = ancestors.FindFromKey(explorer.Current())
        for neighbour in faces:
            index = part._face_map.FindIndex(neighbour)
            if index and index != ordinal:
                info = part.faces[index]
                vertical = (info.normal is not None and abs(info.normal[2]) < 0.1) or (
                    info.axis is not None and axis_word(info.axis) in ("+Z", "-Z"))
                if vertical and info.bounds and info.bounds[1][2] > z + 1e-6:
                    walls.add(index)
        explorer.Next()
    if not walls:
        return None
    # An inner wire is an island when the faces along it rise above the floor; a deeper step's walls go down.
    from OCP.BRepTools import BRepTools

    outer = BRepTools.OuterWire_s(floor)
    islands = 0
    wires = TopExp_Explorer(floor, TopAbs_WIRE)
    while wires.More():
        wire = wires.Current()
        if not wire.IsSame(outer):
            edges = TopExp_Explorer(wire, TopAbs_EDGE)
            rises = False
            while edges.More() and not rises:
                for neighbour in ancestors.FindFromKey(edges.Current()):
                    index = part._face_map.FindIndex(neighbour)
                    bounds = part.faces[index].bounds if index and index != ordinal else None
                    rises = rises or bool(bounds and bounds[1][2] > z + 1e-6)
                edges.Next()
            islands += rises
        wires.Next()
    top = max(part.faces[w].bounds[1][2] for w in walls)
    return {"walls": [part.faces[w].ref for w in sorted(walls)], "depth_mm": round(top - z, 4),
            "islands": islands}


def read_features(part) -> dict:
    import numpy as np

    if part.kind == "dxf":
        return {"faces": [], "holes": [], "floors": [], "profiles": _profiles(part)}
    low, high = (np.asarray(v) for v in part.bbox)
    faces, floors = [], []
    found = holes(part)
    in_hole = {ref for hole in found for ref in hole["faces"]}
    for ordinal, info in sorted(part.faces.items()):
        entry = {"ref": info.ref, "surface": info.surface, "area_mm2": round(info.area_mm2, 3),
                 "center_mm": [round(v, 4) + 0.0 for v in info.center_mm]}
        if info.surface == "plane":
            entry["normal"] = list(info.normal)
            word = axis_word(info.normal)
            if word:
                index = "XYZ".index(word[1])
                at = info.center_mm[index]
                entry[f"{word[1].lower()}_mm"] = round(at, 4) + 0.0
                if word[1] == "Z":
                    if word[0] == "+":
                        kind = "top" if abs(at - high[2]) < 1e-3 else "floor"
                    else:
                        kind = "bottom" if abs(at - low[2]) < 1e-3 else "underside"
                    floor = {"ref": info.ref, "z_mm": round(at, 4) + 0.0, "normal": word, "kind": kind,
                             "area_mm2": round(info.area_mm2, 3)}
                    reading = f"flat {kind} at Z {_g(at)}, facing {word}"
                    if kind == "floor":
                        pocket = _pocket(part, ordinal, at)
                        if pocket:
                            floor["pocket"] = pocket
                            islands = pocket["islands"]
                            reading += (f" (a pocket floor {_g(pocket['depth_mm'])} mm down"
                                        + (f", {islands} island{'s' if islands > 1 else ''}" if islands else "") + ")")
                    floors.append(floor)
                else:
                    reading = f"flat wall at {word[1]} {_g(at)}, facing {word}"
            else:
                reading = f"flat, tilted, facing {_vec(info.normal)}"
        elif info.surface == "cylinder":
            word = axis_word(info.axis) or _vec(info.axis)
            hole = bool(info.hole) and info.ref in in_hole
            entry.update({"axis": list(info.axis), "diameter_mm": round(2 * info.radius_mm, 4), "hole": hole})
            along = word.lstrip("+-")
            if hole:
                reading = f"hole wall Ø{_g(2 * info.radius_mm)} along {along}"
            elif info.hole:
                reading = (f"rounded corner R{_g(info.radius_mm)} along {along} (a fillet or a pocket's corner, not "
                           "a hole)")
            else:
                reading = f"round wall Ø{_g(2 * info.radius_mm)} along {along} (outside)"
        elif info.surface == "cone":
            word = axis_word(info.axis) or _vec(info.axis)
            entry["axis"] = list(info.axis)
            reading = f"cone along {word.lstrip('+-')} (a chamfer, countersink or drill point)"
        else:
            reading = f"curved ({info.surface})"
        entry["reading"] = f"{reading}, {_g(info.area_mm2, 1)} mm²"
        faces.append(entry)
    return {"faces": faces, "holes": found, "floors": floors, "profiles": []}


def _profiles(part) -> list[dict]:
    import numpy as np

    out = []
    for index, polygon in enumerate(part.profiles):
        x0, y0, x1, y1 = polygon.bounds
        hole_list = []
        for ring in polygon.interiors:
            coords = np.asarray(ring.coords)[:-1]
            centre = coords.mean(axis=0)
            radii = np.linalg.norm(coords - centre, axis=1)
            round_ = len(coords) >= 8 and float(radii.max() - radii.min()) <= max(0.02, 0.01 * radii.mean())
            hole_list.append({"center_mm": [round(float(v), 4) for v in centre],
                              "diameter_mm": round(2 * float(radii.mean()), 4) if round_ else None})
        sizes = [h["diameter_mm"] for h in hole_list if h["diameter_mm"]]
        reading = f"outline {_g(x1 - x0)} x {_g(y1 - y0)} mm, {_g(polygon.area, 1)} mm²"
        if hole_list:
            reading += f", {len(hole_list)} hole{'s' if len(hole_list) > 1 else ''}"
            if sizes:
                reading += " (" + ", ".join(f"Ø{_g(s)}" for s in sorted(set(sizes))) + ")"
        out.append({"index": index, "area_mm2": round(polygon.area, 3),
                    "bounds_mm": [round(v, 4) for v in (x0, y0, x1, y1)], "holes": hole_list, "reading": reading})
    return out
