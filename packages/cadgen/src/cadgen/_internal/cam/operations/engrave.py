"""``engrave`` (Engrave): follow curves at a shallow depth with a vee or engraving tool, the tool's centre on them.

What it follows, one of:

* ``dxf``: a DXF's curves (path relative to the job file, else to the part; or absolute): lines, arcs, circles,
  ellipses, polylines and splines, open or closed, placed with the DXF's origin at ``origin_mm`` ``[x, y]`` in the
  setup's WCS (default ``[0, 0]``); its ``$INSUNITS`` are honoured; blocks are expanded. Text, dimensions and hatches are
  skipped (explode text to curves in the drawing first) and counted in a note; any other entity is refused;
* ``faces``: flat faces facing the tool: the edges of their outlines and holes;
* ``region``: ``{"polygon": [[x, y], ...]}``: its outline (with ``bottom_z``, the engraving's floor instead of
  ``surface_z - depth_mm``).

``depth_mm`` (default 0.2) is how deep below ``surface_z``: the surface engraved, default the named face's height,
else the part's top (in the setup's WCS). A depth deeper than the step down is cut in several passes. The line it
leaves is ``tip diameter + 2 x depth x tan(half angle)`` wide (in the facts). Curves are cut nearest first, an open
one from whichever end is nearer; touching pieces are joined. Each curve is entered by plunging at its start.

The part as modelled has no engraving, so this cuts into it by design: the ``gouge`` check does not judge it.
"""

from __future__ import annotations

import math
from pathlib import Path

from cadgen._internal.cam.job_errors import CamJobError, PlanError, number_list, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["EngraveOp", "read_dxf_curves"]


class EngraveOp(Operation):
    name = "engrave"
    plain = "Engrave"
    family = "2.5D milling"
    machines = MILLS
    status = "full"
    keys = ("dxf", "origin_mm", "depth_mm", "surface_z")
    common_keys = ("feed", "speed", "stepdown_mm")
    tool_types = ("vee", "engraver", "chamfer")
    takes_faces = True
    takes_region = True
    feeds_kind = "engrave"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        extra = spec.extra
        where = spec.where
        given = sum(1 for present in (bool(spec.faces), spec.region is not None, "dxf" in extra) if present)
        if given != 1:
            raise CamJobError(f"{where}: an engrave needs one of \"dxf\" (a drawing's curves), \"faces\" (their edges) or "
                              "\"region\" ({\"polygon\": [[x, y], ...]})")
        if "dxf" in extra and (not isinstance(extra["dxf"], str) or not extra["dxf"].strip()):
            raise CamJobError(f"{where}.dxf must be the DXF's path, relative to the job file or the part")
        if "origin_mm" in extra and "dxf" not in extra:
            raise CamJobError(f"{where}.origin_mm places a DXF; remove it, or give \"dxf\"")
        params = {
            "dxf": extra.get("dxf"),
            "origin_mm": number_list(extra["origin_mm"], f"{where}.origin_mm", length=2) if "origin_mm" in extra
            else (0.0, 0.0),
            "depth_mm": read_number(extra, "depth_mm", where, default=0.2),
            "surface_z": read_number(extra, "surface_z", where, minimum=-1e6),
            "region": region_polygon(spec, where=where) if spec.region is not None else None,
            "base_dir": ctx.job.base_dir,
        }
        return params

    def _curves(self, ctx, params):
        """(curves [(N, 2) arrays, closed ones with first == last], surface z or None, notes)."""
        import numpy as np

        from cadgen._internal.cam import geom2d

        notes = []
        if params["dxf"] is not None:
            path = Path(params["dxf"]).expanduser()
            if not path.is_absolute():
                bases = [params["base_dir"]] if params["base_dir"] is not None else []
                bases.append(Path(ctx.part.document).resolve().parent)
                path = next((base / path for base in bases if (base / path).is_file()), bases[0] / path)
            if not path.is_file():
                raise CamJobError(f"{ctx.spec.where}.dxf: no DXF at {path}; give its path relative to the job file or "
                                  "the part")
            curves, skipped = read_dxf_curves(path, tolerance_mm=ctx.tolerance_mm)
            ox, oy = params["origin_mm"]
            curves = [np.asarray(c) + [ox, oy] for c in curves]
            if skipped:
                from cadgen._internal.cam.part import skipped_words

                notes.append(skipped_words(path.name, skipped))
            if not curves:
                raise CamJobError(f"{ctx.spec.where}.dxf: {path.name} has no lines, arcs, circles, polylines or "
                                  "splines to engrave")
            return curves, None, notes
        if params["region"] is not None:
            polygon, _ = params["region"]
            return [np.asarray(polygon.exterior.coords)[:, :2]], None, notes
        curves, heights = [], []
        for ref in ctx.spec.faces:
            z, footprint = _flat_face(ctx, ref)
            heights.append(z)
            for polygon in geom2d.polygons_of(footprint):
                curves.append(np.asarray(polygon.exterior.coords)[:, :2])
                curves.extend(np.asarray(ring.coords)[:, :2] for ring in polygon.interiors)
        return curves, max(heights), notes

    def plan(self, ctx, params):
        import numpy as np

        from cadgen._internal.cam.operations._milling2d import levels, lift_and_go

        tool = ctx.tool
        heights = ctx.heights
        curves, face_z, notes = self._curves(ctx, params)
        surface = params["surface_z"] if params["surface_z"] is not None else (
            face_z if face_z is not None else heights.part_top)
        bottom = surface - params["depth_mm"]
        if params["region"] is not None and params["region"][1] is not None:
            bottom = params["region"][1]
        if bottom >= heights.stock_top - 1e-6:
            raise PlanError("empty_operation", f"{ctx.spec.where}: the engraving's bottom (Z {bottom:.3f}) is at or "
                            f"above the stock top in setup '{ctx.setup.id}', so it cuts nothing; give a deeper "
                            "depth_mm or a lower surface_z")
        feeds = ctx.feeds(self.feeds_kind)
        cut_levels = levels(min(surface, heights.stock_top), bottom, ctx.stepdown())
        b = ctx.builder()
        remaining = [np.asarray(c, dtype=float) for c in curves if len(c) >= 2]
        total = 0.0
        while remaining:
            here = np.asarray(b.pos[:2])
            best, flip, gap = 0, False, math.inf
            for i, curve in enumerate(remaining):
                for reverse, end in ((False, curve[0]), (True, curve[-1])):
                    d = float(np.hypot(*(end - here)))
                    if d < gap:
                        best, flip, gap = i, reverse, d
            curve = remaining.pop(best)
            closed = len(curve) > 2 and float(np.hypot(*(curve[0] - curve[-1]))) < 1e-6
            if flip and not closed:
                curve = curve[::-1]
            total += float(np.hypot(*np.diff(curve, axis=0).T).sum())
            lift_and_go(b, curve[0], heights)
            path = curve
            for k, z in enumerate(cut_levels):
                if k and not closed:
                    path = path[::-1]
                b.plunge(z=z, f=feeds.plunge_mm_min)
                b.polyline(np.column_stack([path[1:], np.full(len(path) - 1, z)]), f=feeds.feed_mm_min)
            b.rapid(z=heights.retract)
        b.rapid(z=heights.clearance)
        half = math.radians((tool.angle_deg or 90.0) / 2.0)
        line_width = tool.tip_diameter_mm + 2.0 * params["depth_mm"] * math.tan(half)
        note = (f"engraves {len(curves)} curve(s) {params['depth_mm']:g} mm deep, a line {line_width:.2g} mm wide, into "
                "the modelled surface (not judged by the gouge check)")
        ctx.meta.update({"levels": len(cut_levels), "passes": len(curves), "bottom_z": round(bottom, 4),
                         "length_mm": round(total, 2), "line_width_mm": round(line_width, 4), "no_gouge_check": True,
                         "note_level": "warning" if notes else "info",
                         "note": "; ".join([note] + notes)})
        return b.build()


def _flat_face(ctx, ref):
    """A flat face facing the tool: (WCS height, footprint)."""
    import numpy as np

    info = ctx.face(ref)
    normal = None if info.normal is None else ctx.wcs.vectors_to_wcs([info.normal])[0]
    if info.surface != "plane" or normal is None or normal[2] < 1.0 - 1e-6:
        raise CamJobError(f"{ctx.spec.where}.faces: {ref} is not a flat face facing the tool in setup "
                          f"'{ctx.setup.id}'; an engrave follows the edges of flat faces facing it")
    vertices, _ = ctx.mesh
    triangles = ctx.face_triangles(ref)
    z = float(np.asarray(vertices)[np.unique(triangles)][:, 2].mean())
    return z, ctx.footprint(triangles)


def read_dxf_curves(path: Path, *, tolerance_mm: float = 0.01) -> tuple[list, dict[str, int]]:
    """The DXF's curves as (N, 2) mm polylines (closed ones end on their start), touching open pieces joined, and
    the annotation skipped by type (:func:`~cadgen._internal.cam.part.dxf_curves`: blocks expanded, any entity that
    is not a curve or annotation refused)."""
    import numpy as np
    import shapely

    from cadgen._internal.cam.part import dxf_curves

    found, skipped = dxf_curves(path, tolerance_mm=tolerance_mm)
    curves, open_ = [], []
    for points, closed in found:
        if closed and len(points) >= 3:
            points = list(points)
            points[-1] = points[0]
            curves.append(np.asarray(points))
        else:
            open_.append(shapely.LineString(points))
    if open_:
        merged = shapely.line_merge(shapely.set_precision(shapely.MultiLineString(open_), 1e-6))
        for piece in shapely.get_parts(merged):
            coords = np.asarray(piece.coords)[:, :2]
            if len(coords) >= 2:
                curves.append(coords)
    return curves, skipped
