"""``thin_wall``: a hole or a pocket the job cuts leaves less than 1 mm of wall to the part's outside.

A thin wall bends away from the cutter and chatters, and can break through. The wall is measured in the part's
section halfway down the feature (holes along the part's Z and pockets with a floor square to it): from the
feature's edge to the outside of the material round it. From the parallel cam build.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz

__all__ = ["THIN_MM", "run"]

#: Less wall than this to the outside is said.
THIN_MM = 1.0


def _wall(section, shape):
    """The least wall from ``shape`` (a hole's circle or a pocket's outline) to the outside of the material round it:
    the distance to the outer ring of the piece of section whose outline holds it, or None when none does (a feature
    open to the side has no wall there)."""
    from shapely.geometry import Polygon

    best = None
    for polygon in getattr(section, "geoms", [section]):
        if polygon.is_empty:
            continue
        if shape.within(Polygon(polygon.exterior).buffer(1e-6)):
            gap = polygon.exterior.distance(shape)
            best = gap if best is None else min(best, gap)
    return best


def run(ctx) -> list[dict]:
    import numpy as np
    from shapely.geometry import Point

    from cadgen._internal.cam.checks._features import cut_points, hole_cut, pocket_cut, pockets
    from cadgen._internal.cam.features import holes as part_holes
    from cadgen._internal.cam.features import read_features
    from cadgen._internal.cam.geom2d import Sections

    if getattr(ctx.part, "kind", "") == "dxf" or not ctx.ops:
        return []
    if ctx.job.machine.kind not in ("mill", "mill4", "mill5", "router"):
        return []
    points = cut_points(ctx)
    sections = Sections(ctx.part.vertices, ctx.part.triangles)
    out = []
    holes = part_holes(ctx.part)
    for hole in holes:
        axis = np.asarray(hole["axis"], dtype=float)
        if abs(abs(axis[2]) - 1.0) > 1e-6 or not hole_cut(hole, points):
            continue
        top, bottom = np.asarray(hole["center_mm"]), np.asarray(hole["bottom_mm"])
        mid = 0.5 * (top + bottom)
        wall = _wall(sections.at(float(mid[2])), Point(mid[0], mid[1]).buffer(hole["diameter_mm"] / 2.0, 64))
        if wall is not None and wall < THIN_MM:
            out.append(_finding(f"the Ø{hole['diameter_mm']:g} hole {hole['faces'][0]}", wall, mid,
                                hole["faces"][0]))
    for pocket in pockets(ctx.part, read_features(ctx.part)["floors"], holes):
        if not pocket_cut(pocket, points):
            continue
        sign = 1.0 if pocket["normal"] == "+Z" else -1.0
        z = pocket["z"] + sign * 0.5 * pocket["depth"]
        wall = _wall(sections.at(z), pocket["outline"])
        if wall is not None and wall < THIN_MM:
            centre = pocket["outline"].representative_point()
            out.append(_finding(f"the pocket on floor {pocket['ref']}", wall, (centre.x, centre.y, z), pocket["ref"]))
    return out


def _finding(what: str, wall: float, at, ref: str) -> dict:
    return finding(
        "thin_wall", "warning", "thin_wall",
        f"{what[0].upper()}{what[1:]} leaves {wall:.2f} mm of wall to the part's outside, under {THIN_MM:g} mm",
        "a thin wall bends away from the cutter and chatters: take light finishing passes on it, support it, or "
        "check with the user the part needs it that thin", [{"ref": ref, "wall_mm": round(float(wall), 3),
                                                             "at": xyz(at)}])
