"""``uncut_feature``: a hole or a pocket one of the job's setups reaches that no operation cuts.

A feature the job leaves is often an operation forgotten: the warning names it and the setups that reach it, so the
agent adds the operation or confirms with the user it stays. Holes along a setup's axis and pockets with a floor
square to it are judged (``features``' reading of the part); a spot drill or a chamfer does not count as cutting a
hole. Not judged on a blank from STEP, which may hold its features already. From the parallel cam build.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz

__all__ = ["run"]


def run(ctx) -> list[dict]:
    from cadgen._internal.cam.checks._features import (cut_points, hole_cut, pocket_cut, pockets,
                                                       reaching_setups)
    from cadgen._internal.cam.features import holes as part_holes
    from cadgen._internal.cam.features import read_features

    if getattr(ctx.part, "kind", "") == "dxf" or getattr(ctx.stock, "kind", "") == "from_step" or not ctx.ops:
        return []
    if ctx.job.machine.kind not in ("mill", "mill4", "mill5", "router"):
        return []
    points = cut_points(ctx)
    out = []
    # Holes of one size the same setups reach are one warning, an item each.
    left: dict[tuple, list] = {}
    holes = part_holes(ctx.part)
    for hole in holes:
        setups = reaching_setups(ctx, hole.get("reach", ()))
        if setups and not hole_cut(hole, points):
            left.setdefault((round(hole["diameter_mm"], 4), tuple(setups)), []).append(hole)
    for (diameter, setups), group in left.items():
        what = (f"the Ø{diameter:g} hole {group[0]['faces'][0]}" if len(group) == 1 else
                f"{len(group)} Ø{diameter:g} holes ({', '.join(h['faces'][0] for h in group)})")
        out.append(_finding(what, list(setups), [(h["center_mm"], h["faces"][0]) for h in group]))
    for pocket in pockets(ctx.part, read_features(ctx.part)["floors"], holes):
        setups = reaching_setups(ctx, (pocket["normal"],))
        if setups and not pocket_cut(pocket, points):
            centre = pocket["outline"].representative_point()
            out.append(_finding(f"the pocket on floor {pocket['ref']} ({pocket['depth']:g} mm deep)", setups,
                                [((centre.x, centre.y, pocket["z"]), pocket["ref"])]))
    return out


def _finding(what: str, setups: list[str], places) -> dict:
    return finding(
        "uncut_feature", "warning", "uncut_feature",
        f"No operation cuts {what}, which setup{'s' if len(setups) > 1 else ''} {', '.join(setups)} "
        f"reach{'' if len(setups) > 1 else 'es'}",
        "add the operation that makes it, or confirm with the user it stays as it is (a feature made before or "
        "after this job)", [{"setup": setups[0], "ref": ref, "at": xyz(at)} for at, ref in places])
