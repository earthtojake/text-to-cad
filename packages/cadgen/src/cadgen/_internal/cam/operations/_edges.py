"""The part's edges for the operations that follow them (``trace``): edge selectors, points, chains.

Not an operation (no registry entry). A job names edges the way the Viewer selects them (``#o1.e5``; a bare ``#e5``
on a one-part document, or a ``part.step#o1.e5`` file-prefixed ref); ``part.py`` resolves faces only, so this module
resolves edges through the same scene.

* :func:`edge_refs` checks a job's edge list (strings shaped like edge selectors, none twice).
* :func:`edge_points` resolves one edge on the part and samples it in a setup's WCS, finer than the tolerance.
* :func:`chains` joins edges end to end into :class:`Chain` rows (open or closed); a chain that climbs (not level in
  the setup's XY plane) is refused (``unreachable``).
* :func:`material_heights` lists the heights at which the part's sections change between two heights (its
  tessellation's vertex heights), for an operation that checks what stands over its cut.

numpy, shapely and OCP inside.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from cadgen._internal.cam.job_errors import CamJobError, PlanError, shown

__all__ = ["Chain", "EDGE_REF", "chains", "edge_points", "edge_refs", "material_heights", "resolve_edge"]

#: An edge selector: ``#o1.e5`` (any file prefix), or a bare ``#e5`` on a one-part document.
EDGE_REF = re.compile(r"^(?:[^#\s]*)#o[\w.]+\.e\d+$|^#e\d+$")
#: Two edge ends this close (mm) are one point of a chain; a chain whose heights spread more than this climbs.
JOIN_MM = 1e-3


@dataclass
class Chain:
    """Edges joined end to end, in WCS: ``points`` (N, 3) along them in order, first == last when ``closed``."""

    refs: list
    points: object
    closed: bool

    @property
    def name(self) -> str:
        return "+".join(self.refs)

    @property
    def z(self) -> float:
        return float(self.points[:, 2].max())


def edge_refs(raw: object, where: str) -> tuple[str, ...]:
    """A job's ``edges``: a non-empty list of edge selectors, each once."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw or not all(isinstance(ref, str) and EDGE_REF.match(ref) for ref in raw):
        raise CamJobError(f"{where} must be a list of edge refs like \"#o1.e12\" (select the edges in the Viewer), "
                          f"not {shown(raw)}")
    for i, ref in enumerate(raw):
        if ref in raw[:i]:
            raise CamJobError(f"{where}: {ref!r} is listed twice; name each edge once")
    return tuple(raw)


def resolve_edge(ctx, ref: str, where: str):
    """The scene's selection of the edge ``ref`` names on the part machined, or the teaching error."""
    part = ctx.part
    if part.kind != "step" or part._scene is None:
        raise CamJobError(f"{where}: {ref} names an edge, but a DXF has no edges; follow its profiles with region")
    try:
        selection = part._scene.resolve(ref)
    except ValueError as exc:
        raise CamJobError(f"{where}: {ref} is not an edge of this part ({exc}); select the edges in the Viewer") from None
    if selection.kind != "edge":
        raise CamJobError(f"{where}: {ref} is a {selection.kind} reference; name edges (#o1.e12)")
    if selection.occurrence_ref != part.occurrence:
        raise CamJobError(f"{where}: {ref} is on {selection.occurrence_ref}, but the job machines {part.occurrence}")
    return selection


def edge_points(ctx, ref: str, where: str):
    """``(canonical ref, (N, 3) WCS points)`` along the edge ``ref`` from its first parameter to its last: a line's
    two ends, any other curve sampled within a quarter of the plan's tolerance."""
    import numpy as np
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.TopoDS import TopoDS

    selection = resolve_edge(ctx, ref, where)
    edge = TopoDS.Edge_s(selection.shape().wrapped)
    if BRep_Tool.Degenerated_s(edge):
        raise CamJobError(f"{where}: {selection.ref} is a degenerate edge (a point, at a cone's tip or a sphere's pole); "
                          "name the edges round it")
    curve = BRepAdaptor_Curve(edge)
    first, last = curve.FirstParameter(), curve.LastParameter()
    if curve.GetType() == GeomAbs_Line:
        values = [curve.Value(first), curve.Value(last)]
    else:
        sampler = GCPnts_QuasiUniformDeflection(curve, max(1e-4, ctx.tolerance_mm / 4.0), first, last)
        if not sampler.IsDone() or sampler.NbPoints() < 2:
            raise PlanError("unreachable", f"{where}: the curve of {selection.ref} could not be followed point by point; "
                            "trace a slot path drawn along it instead")
        values = [sampler.Value(i) for i in range(1, sampler.NbPoints() + 1)]
    points = np.array([(p.X(), p.Y(), p.Z()) for p in values], dtype=float)
    return selection.ref, ctx.wcs.to_wcs(points)


def chains(ctx, refs, where: str) -> list[Chain]:
    """The edges ``refs`` joined end to end (either way round) into chains, in WCS, in the order they are named; a
    chain is closed when its ends meet. A chain whose heights spread more than :data:`JOIN_MM` is refused: the
    operations that follow edges cut at one level."""
    import numpy as np

    pieces = [edge_points(ctx, ref, f"{where}[{i}]") for i, ref in enumerate(refs)]
    seen: dict[str, int] = {}
    for i, (canonical, _) in enumerate(pieces):
        if canonical in seen:
            raise CamJobError(f"{where}: {refs[seen[canonical]]} and {refs[i]} are the same edge, {canonical}; name "
                              "each edge once")
        seen[canonical] = i
    out: list[Chain] = []
    remaining = [(canonical, np.asarray(points)) for canonical, points in pieces]
    while remaining:
        ref, chain = remaining.pop(0)
        names = [ref]
        grown = True
        while grown and not _meets(chain[0], chain[-1]):
            grown = False
            for k, (other, points) in enumerate(remaining):
                if _meets(chain[-1], points[0]):
                    chain, names = np.vstack([chain, points[1:]]), names + [other]
                elif _meets(chain[-1], points[-1]):
                    chain, names = np.vstack([chain, points[::-1][1:]]), names + [other]
                elif _meets(chain[0], points[-1]):
                    chain, names = np.vstack([points[:-1], chain]), [other] + names
                elif _meets(chain[0], points[0]):
                    chain, names = np.vstack([points[::-1][:-1], chain]), [other] + names
                else:
                    continue
                remaining.pop(k)
                grown = True
                break
        rise = float(chain[:, 2].max() - chain[:, 2].min())
        if rise > JOIN_MM:
            raise PlanError("unreachable", f"{where}: the edges {'+'.join(names)} climb {rise:.3g} mm in setup "
                            f"'{ctx.setup.id}'; a trace follows edges level in the setup's XY plane (name the edges "
                            "of a face square to the tool, or machine them from a setup that looks square at them)")
        closed = len(chain) > 2 and _meets(chain[0], chain[-1])
        if closed:
            chain[-1] = chain[0]
        if float(np.hypot(*np.diff(chain[:, :2], axis=0).T).sum()) < 1e-6:
            raise PlanError("unreachable", f"{where}: the edges {'+'.join(names)} stand along the tool's axis in setup "
                            f"'{ctx.setup.id}'; a trace follows edges that run across it")
        out.append(Chain(refs=names, points=chain, closed=closed))
    return out


def _meets(a, b) -> bool:
    return math.dist(a, b) <= JOIN_MM


def material_heights(ctx, low: float, high: float, *, most: int = 48) -> list[float]:
    """Heights (WCS) between ``low`` and ``high`` at which to look at the part's sections: just above ``low``, every
    height of the tessellation's vertices between (where a prismatic part's section changes), at most ``most`` of
    them evenly picked, and ``high``."""
    import numpy as np

    vertices, _ = ctx.mesh
    zs = np.unique(np.round(np.asarray(vertices)[:, 2], 6))
    zs = zs[(zs > low + 1e-6) & (zs <= high + 1e-6)]
    if len(zs) > most:
        zs = zs[np.linspace(0, len(zs) - 1, most).round().astype(int)]
    return sorted({round(low + 0.05, 6), *(float(z) for z in zs), round(high, 6)})
