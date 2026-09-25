"""Conservative local clearance cutters and honest sampled motion reports."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math
from typing import Any

from .mesh import _check_solid, _deps, _mesh, _positive, _solid


@dataclass(frozen=True)
class RotationGrid:
    """Euler box around a fixed pivot; Rz(twist) @ Ry @ Rx in world axes.

    Each interval includes its endpoints and zero when inside the interval.
    This is an explicitly bounded test domain, not a ball joint's true
    mechanical limit surface or a complete multijoint configuration space.
    """

    pivot: tuple[float, float, float]
    x_degrees: tuple[float, float] = (0.0, 0.0)
    y_degrees: tuple[float, float] = (0.0, 0.0)
    z_degrees: tuple[float, float] = (0.0, 0.0)
    step_degrees: float = 10.0

    def axes(self):
        np, _, _ = _deps()
        step = _positive(self.step_degrees, "step_degrees")
        if len(self.pivot) != 3 or not np.isfinite(self.pivot).all():
            raise ValueError("pivot must be a finite 3-vector")
        axes = []
        for limits in (self.x_degrees, self.y_degrees, self.z_degrees):
            if len(limits) != 2 or not np.isfinite(limits).all() or limits[0] > limits[1]:
                raise ValueError("Angular limits must be finite ordered pairs")
            lo, hi = limits
            span = (hi - lo) / step
            if not math.isfinite(span) or span > 9999:
                raise ValueError("Angular axis exceeds the 10000-pose budget")
            count = max(1, int(math.ceil(span)))
            values = np.linspace(lo, hi, count + 1).tolist()
            if lo <= 0 <= hi:
                values.append(0.0)
            axes.append(sorted(set(values)))
        if math.prod(map(len, axes)) > 10000:
            raise ValueError("Rotation grid exceeds 10000 poses; narrow the domain or increase the step")
        return axes

    def frames(self, *, inverse: bool = False):
        np, trimesh, _ = _deps()
        pivot = np.asarray(self.pivot, dtype=float)
        for degrees in product(*self.axes()):
            matrix = trimesh.transformations.euler_matrix(*np.radians(degrees), axes="sxyz")
            matrix[:3, 3] = pivot - matrix[:3, :3] @ pivot
            if inverse:
                matrix = np.linalg.inv(matrix)
            yield {"degrees": list(degrees), "matrix": matrix}

    def max_nearest_angle_radians(self) -> float:
        # Triangle inequality over the three elementary rotations. Every pose
        # in the box is within half the largest cell in each angular axis.
        return math.radians(sum(max((b - a for a, b in zip(v, v[1:])), default=0) / 2
                                for v in self.axes()))


def clearance_envelope(obstacle, grid: RotationGrid, *, clearance_mm: float,
                       inverse: bool = False, geometry_error_mm: float = 0.0,
                       cell_size_mm: float | None = None):
    """Conservative convex sweep covers, optionally spatially partitioned.

    Partitioning preserves obstacle concavities more closely than one global
    hull. Each cell still uses a convex sweep; this is not an exact swept
    surface. Padding bounds interpolation between sampled poses, plus the
    requested Euclidean clearance and input geometry error. Restrict the cut
    with carve_clearance and check the actual final parts afterwards.
    """
    np, _, mf = _deps()
    clearance = _positive(clearance_mm, "clearance_mm", zero=True)
    error = _positive(geometry_error_mm, "geometry_error_mm", zero=True)
    cell = None if cell_size_mm is None else _positive(cell_size_mm, "cell_size_mm")
    solid = _solid(obstacle)
    axes = grid.axes()
    matrices = [f["matrix"] for f in grid.frames(inverse=inverse)]
    # Linear interpolation of one rotation has error <= dtheta**2 / 8
    # in operator norm (the second derivative has norm 1). Telescoping the
    # product of three rotations adds their bounds: rotations have norm 1
    # and convex combinations of rotations have norm <= 1. The interpolated
    # vertex is a convex combination of the grid-cell corner vertices, all
    # contained in the sweep hull. The same proof holds in reversed order
    # for inverse rotations, about the same pivot.
    interpolation_bound = sum(math.radians(max(
        (b - a for a, b in zip(values, values[1:])), default=0)) ** 2 / 8
        for values in axes)
    bounds = np.asarray(obstacle.bounds)
    divisions = [1, 1, 1] if cell is None else [
        max(1, int(math.ceil(span / cell))) for span in bounds[1] - bounds[0]]
    if math.prod(divisions) > 512:
        raise ValueError("Obstacle partition exceeds 512 cells; enlarge cell_size_mm or localize the obstacle")
    edges = [np.linspace(bounds[0, i], bounds[1, i], n + 1)
             for i, n in enumerate(divisions)]
    covers = []
    radii = []
    for index in product(*(range(n) for n in divisions)):
        piece = solid
        if cell is not None:
            low = np.array([edges[i][k] for i, k in enumerate(index)])
            high = np.array([edges[i][k + 1] for i, k in enumerate(index)])
            piece = solid ^ mf.Manifold.cube(tuple(high - low)).translate(tuple(low))
            # A partition touching only a face/edge can have zero volume but
            # nonempty topology. Its boundary is covered by adjacent solid
            # cells. Do not use a positive volume threshold: thin material
            # must survive, and kernel errors must still fail.
            if piece.status() == mf.Error.NoError and piece.volume() == 0:
                continue
            _check_solid(piece)
        vertices = np.array(piece.hull().to_mesh64().vert_properties[:, :3], copy=True)
        radius = float(np.linalg.norm(vertices - np.asarray(grid.pivot), axis=1).max())
        radii.append(radius)
        points = [vertices @ matrix[:3, :3].T + matrix[:3, 3] for matrix in matrices]
        hull = _check_solid(mf.Manifold.hull_points(np.concatenate(points)))
        pad = clearance + error + radius * interpolation_bound
        if pad:
            hull = _check_solid(hull.minkowski_sum(
                mf.Manifold.cube((2 * pad,) * 3, center=True)))
        covers.append(hull)
    result = _mesh(_check_solid(mf.Manifold.batch_boolean(covers, mf.OpType.Add)))
    between = max(radii) * interpolation_bound
    return result, {
        "method": "spatially partitioned convex sweep union" if cell is not None
                  else "convex sweep cover",
        "padding_method": "rotation interpolation error bound + circumscribed cube",
        "domain": "specified Euler rotation box only", "poses": len(matrices),
        "pivot_mm": list(grid.pivot), "inverse": inverse,
        "cell_size_mm": cell, "partition_cells": len(covers),
        "maximum_radius_mm": max(radii), "between_sample_padding_mm": between,
        "requested_clearance_mm": clearance, "geometry_error_mm": error,
        "total_padding_mm": clearance + error + between,
        "coverage": "conservative for the supplied obstacle and rotation box",
        "note": "Clipping the cutter or protecting features requires final motion verification.",
    }


def carve_clearance(host, envelope, *, allowed_region, protected=None):
    """Cut only permitted material and preserve explicit functional features."""
    host_s = _solid(host)
    cutter = _solid(envelope) ^ _solid(allowed_region)
    if protected is not None:
        cutter = cutter - _solid(protected)
    cutter = _check_solid(cutter, allow_empty=True)
    result = _check_solid(host_s - cutter)
    before_count = len(host_s.decompose())
    after_count = len(result.decompose())
    if before_count != after_count:
        raise ValueError(f"Clearance cut changed connected components: {before_count} -> {after_count}")
    return _mesh(result), _mesh(cutter, allow_empty=True), {
        "removed_volume_mm3": host_s.volume() - result.volume(),
        "components_before": before_count, "components_after": after_count,
        "protected_region_supplied": protected is not None,
    }


def check_motion(fixed, moving, grid: RotationGrid, *, clearance_mm: float = 0.0,
                 volume_tolerance_mm3: float = 1e-6,
                 numerical_tolerance_mm: float = 1e-6) -> dict[str, Any]:
    """Check every sampled rigid pose, including full XYZ combinations.

    All intersections and gaps are measured on the supplied meshes. No pairs
    are exempted. Failed kernel evaluations are inconclusive, never passes.
    min_gap saturates at the search radius: a saturated value is a LOWER
    BOUND, not a measured global minimum. This does not simulate snap-fit
    elasticity, holding torque, wear or assembly insertion.
    """
    clearance = _positive(clearance_mm, "clearance_mm", zero=True)
    volume_tol = _positive(volume_tolerance_mm3, "volume_tolerance_mm3", zero=True)
    numeric = _positive(numerical_tolerance_mm, "numerical_tolerance_mm", zero=True)
    a, b = _solid(fixed), _solid(moving)
    search = max(clearance * 2, 1.0)
    samples = []
    errors = []
    for index, frame in enumerate(grid.frames()):
        row: dict[str, Any] = {"index": index, "degrees": frame["degrees"]}
        try:
            placed = _check_solid(b.transform(frame["matrix"][:3, :].copy()))
            common = _check_solid(a ^ placed, allow_empty=True)
            volume = float(common.volume())
            gap = float(a.min_gap(placed, search))
            if not math.isfinite(gap) or not math.isfinite(volume) or gap < 0:
                raise ValueError("Kernel returned an invalid volume or gap")
            overlap = volume > volume_tol
            row.update({"overlap_mm3": volume, "gap_mm": gap,
                        "gap_is_lower_bound": gap >= search - numeric,
                        "status": "collision" if overlap else
                                  "insufficient_clearance" if gap + numeric < clearance else "pass"})
        except Exception as exc:
            row.update({"status": "inconclusive", "error": str(exc)})
            errors.append({"index": index, "error": str(exc)})
        samples.append(row)
    failures = [r for r in samples if r["status"] in {"collision", "insufficient_clearance"}]
    good = [r for r in samples if "gap_mm" in r]
    if not samples:
        raise ValueError("No poses were checked")
    return {
        "ok": not failures and not errors,
        "status": "inconclusive" if errors else "fail" if failures else "pass_sampled",
        "coverage": "discrete pose grid; not continuous collision certification",
        "coordinate_units": "mm", "pivot_mm": list(grid.pivot),
        "rotation_order": "Rz @ Ry @ Rx", "pose_count": len(samples),
        "required_clearance_mm": clearance, "volume_tolerance_mm3": volume_tol,
        "numerical_tolerance_mm": numeric,
        "angular_axes_degrees": grid.axes(),
        "minimum_sampled_gap_mm": min((r["gap_mm"] for r in good), default=None),
        "minimum_gap_is_lower_bound": bool(good) and all(r["gap_is_lower_bound"] for r in good),
        "maximum_overlap_mm3": max((r["overlap_mm3"] for r in good), default=None),
        "failed_pose_count": len(failures), "errors": errors, "samples": samples,
        "not_evaluated": ["elastic insertion", "friction/holding torque", "wear", "unspecified joint configurations"],
    }
