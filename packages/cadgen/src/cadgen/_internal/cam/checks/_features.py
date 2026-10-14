"""What the part's features are and whether the job cuts them: the shared reading of ``uncut_feature`` and
``thin_wall``.

A hole is cut when some operation's cutting moves (any setup) go at least halfway down it inside its radius (a spot
drill's cone or a chamfer does not); a pocket when they reach its floor's outline at least halfway down its depth.
Points are the toolpaths' samples in part coordinates, at most :data:`MAX_POINTS` (coarser on a long program).
"""

from __future__ import annotations

__all__ = ["MAX_POINTS", "cut_points", "hole_cut", "pocket_cut", "pockets", "reaching_setups"]

MAX_POINTS = 400_000


def cut_points(ctx):
    """(N, 3) part-mm tool tips of every cutting move of every planned operation."""
    import numpy as np

    from cadgen._internal.cam.ir import DWELL, RAPID

    chunks = []
    total = sum(float(plan.toolpath.lengths().sum()) for plan in ctx.setups if plan.toolpath is not None)
    step = max(0.5, total / MAX_POINTS)
    for plan in ctx.setups:
        if plan.toolpath is None or not len(plan.toolpath):
            continue
        samples = plan.toolpath.sample(max(ctx.tolerance_mm, 0.05), max_step_mm=step)
        mask = (samples.kind != RAPID) & (samples.kind != DWELL) & (samples.op >= 0)
        if mask.any():
            chunks.append(plan.wcs.from_wcs(samples.points[mask]))
    return np.vstack(chunks) if chunks else np.zeros((0, 3))


def _unit(word: str):
    import numpy as np

    vector = np.zeros(3)
    vector["XYZ".index(word[1])] = 1.0 if word[0] == "+" else -1.0
    return vector


def reaching_setups(ctx, words) -> list[str]:
    """The setups whose tool comes from one of ``words`` (``+Z``: from above the part's +Z)."""
    import numpy as np

    out = []
    for plan in ctx.setups:
        axis = np.asarray(plan.wcs.tool_axis, dtype=float)
        if any(float(axis @ _unit(word)) > 0.999 for word in words):
            out.append(plan.setup.id)
    return out


def hole_cut(hole, points) -> bool:
    import numpy as np

    top = np.asarray(hole["center_mm"], dtype=float)
    bottom = np.asarray(hole["bottom_mm"], dtype=float)
    axis = bottom - top
    length = float(np.linalg.norm(axis))
    if length <= 1e-9 or not len(points):
        return length <= 1e-9
    axis /= length
    rel = points - top
    along = rel @ axis
    off = np.linalg.norm(rel - np.outer(along, axis), axis=1)
    inside = off < hole["diameter_mm"] / 2.0
    return bool(inside.any() and float(along[inside].max()) >= 0.5 * length)


def pockets(part, floors, holes=()) -> list[dict]:
    """Each +Z or -Z pocket floor with its outline (shapely, part XY), its height and the pocket's depth; a floor that
    is a hole's own face (a counterbore's shoulder, a blind floor) is the hole's, not a pocket."""
    import numpy as np
    import shapely
    from shapely.geometry import Polygon

    taken = {ref for hole in holes for ref in hole.get("faces", ())}
    out = []
    for floor in floors:
        pocket = floor.get("pocket")
        if not pocket or floor["normal"] not in ("+Z", "-Z") or floor["ref"] in taken:
            continue
        ordinal = int(floor["ref"].rsplit("f", 1)[1])
        tris = np.asarray(part.triangles)[np.asarray(part.face_of_triangle) == ordinal]
        if not len(tris):
            continue
        corners = np.asarray(part.vertices)[tris][:, :, :2]
        polygons = [Polygon(c) for c in corners if abs(Polygon(c).area) > 1e-12]
        if not polygons:
            continue
        outline = shapely.union_all(polygons).buffer(0)
        out.append({"ref": floor["ref"], "z": floor["z_mm"], "depth": pocket["depth_mm"], "normal": floor["normal"],
                    "outline": outline, "walls": pocket["walls"]})
    return out


def pocket_cut(pocket, points) -> bool:
    import numpy as np
    import shapely

    if not len(points):
        return False
    sign = 1.0 if pocket["normal"] == "+Z" else -1.0
    # Below (toward the floor) halfway down the pocket, over its floor.
    deep = sign * (points[:, 2] - pocket["z"]) <= 0.5 * pocket["depth"] + 1e-6
    if not deep.any():
        return False
    candidates = points[deep]
    return bool(shapely.contains_xy(pocket["outline"], candidates[:, 0], candidates[:, 1]).any())
