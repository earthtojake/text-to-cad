"""Explicit distance-field smoothing of a motion cutter, never the whole sculpt."""
from __future__ import annotations

import math
from .mesh import _deps, _positive, _solid, _check_solid, _mesh


def smooth_clearance_envelope(envelope, *, pitch_mm: float, sigma_mm: float,
                              outset_mm: float, volume_tolerance_mm3: float = 1e-6,
                              max_grid_points: int = 4_000_000):
    """Smooth a cutter and reject loss of its existing mesh-volume coverage.

    VTK samples signed distance (negative inside), convolves it with a Gaussian,
    then extracts the positive-outset isosurface. Smoothing is not inherently
    conservative: a Boolean difference must pass before the result is returned.
    This is a finite-mesh volume check, not a Hausdorff/continuous-motion proof.
    The caller must budget added removal and recheck walls and final motion.
    ``outset_mm`` is a field threshold, not a bound on maximum surface movement.
    """
    np, trimesh, _ = _deps()
    pitch = _positive(pitch_mm, 'pitch_mm')
    sigma = _positive(sigma_mm, 'sigma_mm')
    outset = _positive(outset_mm, 'outset_mm', zero=True)
    tolerance = _positive(volume_tolerance_mm3, 'volume_tolerance_mm3', zero=True)
    if isinstance(max_grid_points, bool) or not isinstance(max_grid_points, int) or max_grid_points < 8:
        raise ValueError('max_grid_points must be an integer >= 8')
    source = _solid(envelope)
    mesh = _mesh(source)
    margin = 4 * sigma + outset + 2 * pitch
    lower = mesh.bounds[0] - margin
    counts = np.ceil((mesh.extents + 2 * margin) / pitch) + 1
    if not np.isfinite(counts).all() or math.prod(float(n) for n in counts) > max_grid_points:
        raise ValueError('Distance grid exceeds max_grid_points; localize the cutter or increase pitch_mm')
    counts = counts.astype(int)
    upper = lower + (counts - 1) * pitch
    try:
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
        from vtkmodules.vtkFiltersCore import vtkImplicitPolyDataDistance, vtkFlyingEdges3D
        from vtkmodules.vtkImagingHybrid import vtkSampleFunction
        from vtkmodules.vtkImagingGeneral import vtkImageGaussianSmooth
        from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
    except ImportError as exc:
        raise RuntimeError('Cutter smoothing needs cadgen[organic,organic-smooth]; install that extra.') from exc
    points = vtkPoints(); points.SetData(numpy_to_vtk(np.asarray(mesh.vertices), deep=True))
    triangles = np.column_stack((np.full(len(mesh.faces), 3), mesh.faces)).astype(np.int64)
    cells = vtkCellArray(); cells.SetCells(len(mesh.faces), numpy_to_vtkIdTypeArray(triangles.ravel(), deep=True))
    poly = vtkPolyData(); poly.SetPoints(points); poly.SetPolys(cells)
    distance = vtkImplicitPolyDataDistance(); distance.SetInput(poly)
    sample = vtkSampleFunction(); sample.SetImplicitFunction(distance)
    sample.SetModelBounds(*np.column_stack((lower, upper)).ravel())
    sample.SetSampleDimensions(*counts); sample.ComputeNormalsOff(); sample.CappingOff()
    sample.SetOutputScalarTypeToDouble()
    smooth = vtkImageGaussianSmooth(); smooth.SetInputConnection(sample.GetOutputPort())
    smooth.SetStandardDeviations(*([sigma / pitch] * 3)); smooth.SetRadiusFactors(3, 3, 3)
    contour = vtkFlyingEdges3D(); contour.SetInputConnection(smooth.GetOutputPort())
    contour.SetValue(0, outset); contour.ComputeNormalsOff(); contour.ComputeGradientsOff(); contour.Update()
    output = contour.GetOutput()
    if output.GetNumberOfPoints() == 0 or output.GetNumberOfPolys() == 0:
        raise ValueError('Smoothed cutter has no surface')
    vertices = vtk_to_numpy(output.GetPoints().GetData()).copy()
    polygons = vtk_to_numpy(output.GetPolys().GetData()).reshape(-1, 4)
    if not np.all(polygons[:, 0] == 3):
        raise ValueError('Distance contour contains non-triangle cells')
    candidate = trimesh.Trimesh(vertices, polygons[:, 1:].copy(), process=False)
    # Contouring scalar orientation is a convention, not a topology repair.
    if candidate.volume < 0:
        candidate.invert()
    result = _solid(candidate)
    loss = _check_solid(source - result, allow_empty=True)
    missing = float(loss.volume())
    if not math.isfinite(missing) or missing < 0 or missing > tolerance:
        raise ValueError(f'Smoothing lost cutter coverage: {missing:.9g} mm^3; '
                         'revise outset/resolution within the design budget')
    if len(result.decompose()) != len(source.decompose()):
        raise ValueError('Smoothing changed cutter connected-component count')
    return _mesh(result), {
        'method': 'sampled signed distance, Gaussian convolution, offset isosurface',
        'pitch_mm': pitch, 'sigma_mm': sigma, 'outset_level_mm': outset,
        'gaussian_radius_sigmas': 3, 'grid_dimensions': counts.tolist(),
        'grid_points': int(math.prod(counts)), 'bounds_mm': [lower.tolist(), upper.tolist()],
        'source_volume_mm3': float(source.volume()), 'result_volume_mm3': float(result.volume()),
        'missing_source_volume_mm3': missing, 'volume_tolerance_mm3': tolerance,
        'added_cutter_volume_mm3': float(result.volume() - source.volume() + missing),
        'input_triangles': len(mesh.faces), 'output_triangles': len(candidate.faces),
        'coverage': 'input discrete mesh contained up to Boolean volume tolerance',
        'limitations': ['not an exact swept surface or Hausdorff bound',
            'does not establish a smooth visible parting seam',
            'field outset is not maximum surface displacement',
            'clipping/protection, walls and final assembled motion must be rechecked'],
    }
