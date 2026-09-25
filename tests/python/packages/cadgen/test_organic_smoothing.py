"""Behavioral checks for optional distance-field cutter smoothing."""
import unittest
import numpy as np
import trimesh
from cadgen.organic import smooth_clearance_envelope
from cadgen.organic.mesh import _solid


class CutterSmoothingTest(unittest.TestCase):
    def test_actual_geometry_is_smooth_and_covers_source(self):
        source = trimesh.creation.box((5, 5, 5))
        vertices = source.vertices.copy()
        result, audit = smooth_clearance_envelope(source, pitch_mm=.25,
                                                  sigma_mm=.3, outset_mm=.5)
        self.assertTrue(result.is_volume)
        self.assertGreater(len(result.faces), len(source.faces))
        self.assertGreater(result.volume, source.volume)
        self.assertLessEqual((_solid(source) - _solid(result)).volume(), 1e-6)
        self.assertEqual(audit['missing_source_volume_mm3'], 0)
        np.testing.assert_array_equal(source.vertices, vertices)
        # Changed positions/volume establish a geometric cutter, not smooth shading.
        self.assertGreater(result.bounds[1, 0], source.bounds[1, 0])

    def test_uncompensated_smoothing_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'lost cutter coverage'):
            smooth_clearance_envelope(trimesh.creation.box((5, 5, 5)),
                                      pitch_mm=.25, sigma_mm=.3, outset_mm=0)

    def test_explicit_budgets_and_parameters(self):
        mesh = trimesh.creation.box((5, 5, 5))
        for changes in [{'pitch_mm': 0}, {'sigma_mm': float('nan')},
                        {'outset_mm': -1}, {'max_grid_points': True},
                        {'volume_tolerance_mm3': -1}]:
            kwargs = {'pitch_mm': .25, 'sigma_mm': .3, 'outset_mm': .5, **changes}
            with self.assertRaises(ValueError):
                smooth_clearance_envelope(mesh, **kwargs)
        with self.assertRaisesRegex(ValueError, 'exceeds max_grid_points'):
            smooth_clearance_envelope(mesh, pitch_mm=.001, sigma_mm=.3, outset_mm=.5)
