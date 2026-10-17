"""cadgen's tube engine (`tube_deformation`): the centerlines a tube track keys.

It compiles a key's centerline, refuses one no tube could follow -- in the path's
own order, the first failure named -- and refines a rest mesh into bands of rest
arc length, which is what a skin binds (``test_tube_skin.py`` poses it).
"""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen._internal import tube_deformation as td  # noqa: E402

LINE = {"normal": [0.0, 0.0, 1.0], "segments": [{"kind": "line", "start": [0.0, 0.0, 0.0], "end": [10.0, 0.0, 0.0]}]}


def _refusal(path: dict) -> str:
    try:
        td.compile_tube_path(path)
    except td.TubeDeformationError as error:
        return str(error)
    raise AssertionError("compiled a path cadgen refuses")


def _line(start, end) -> dict:
    return {"kind": "line", "start": list(start), "end": list(end)}


class WhatCadgenRefuses(unittest.TestCase):
    def test_a_path_names_its_frame_and_its_closed_vocabulary(self):
        self.assertEqual(
            "tube deformation: path normal is required: give both the rest and the posed path an explicit "
            "transverse normal seed",
            _refusal({"segments": LINE["segments"]}))
        self.assertEqual("tube deformation: path normal transverse to first tangent must be nonzero",
                         _refusal({**LINE, "normal": [1.0, 0.0, 0.0]}))
        self.assertEqual('tube deformation: unknown segment kind "spline"; expected line, arc, bezier',
                         _refusal({**LINE, "segments": [{"kind": "spline"}]}))
        self.assertEqual('tube deformation: unknown segment 0 key "radius"; expected kind, start, end',
                         _refusal({**LINE, "segments": [{**LINE["segments"][0], "radius": 2}]}))
        self.assertEqual("tube deformation: arc sweepDeg must be nonzero and at most 360 degrees", _refusal({
            **LINE, "segments": [{"kind": "arc", "center": [0, 5, 0], "axis": [0, 0, 1], "start": [0, 0, 0], "sweepDeg": 400}]}))
        # A cusp where no split lands is found unresolved at the deepest split; one at
        # t = 1/2, where a split lands, is a zero tangent.
        self.assertEqual("tube deformation: Bezier has a cusp or unresolved tangent", _refusal({
            **LINE, "segments": [{"kind": "bezier", "points": [[0, 0, 0], [1, 1, 0], [0, 1, 0], [0, -3, 0]]}]}))
        self.assertEqual("tube deformation: Bezier tangent must be nonzero", _refusal({
            **LINE, "segments": [{"kind": "bezier", "points": [[0, 0, 0], [1, 1, 0], [0, 1, 0], [1, 0, 0]]}]}))

    def test_segments_meet_end_to_end_and_tangent_to_tangent(self):
        self.assertEqual("tube deformation: path discontinuity before segment 1",
                         _refusal({**LINE, "segments": [_line((0, 0, 0), (10, 0, 0)), _line((11, 0, 0), (20, 0, 0))]}))
        self.assertEqual("tube deformation: path is not tangent-continuous before segment 1",
                         _refusal({**LINE, "segments": [_line((0, 0, 0), (10, 0, 0)), _line((10, 0, 0), (10, 10, 0))]}))

    def test_the_first_failure_in_the_paths_order_is_the_one_reported(self):
        # The segments are read in order: the gap before segment 1 is met before
        # segment 2 is ever read, however wrong segment 2 is.
        self.assertEqual("tube deformation: path discontinuity before segment 1", _refusal({**LINE, "segments": [
            _line((0, 0, 0), (10, 0, 0)), _line((11, 0, 0), (20, 0, 0)), {"kind": "spline"}]}))

    def test_a_deformation_bounds_its_bands_and_its_braid(self):
        with self.assertRaisesRegex(td.TubeDeformationError, "maxSegmentLength must be at least 0.05 mm"):
            td.normalize_tube_deformation({"rest": LINE, "path": LINE, "maxSegmentLength": 0.01})
        with self.assertRaisesRegex(td.TubeDeformationError, "an even strand count from 2 to 64"):
            td.normalize_tube_deformation({"rest": LINE, "path": LINE, "braid": {"pitch": 1, "depth": 0, "strands": 3}})
        with self.assertRaisesRegex(td.TubeDeformationError, 'unknown deformation key "rest_path"'):
            td.normalize_tube_deformation({"rest_path": LINE, "path": LINE})


class TheRestMesh(unittest.TestCase):
    """A straight tube: 1 mm round, 10 mm long, its mesh only the two end rings."""

    def setUp(self):
        sides = 8
        angle = np.arange(sides) * 2 * np.pi / sides
        ring = np.stack([np.zeros(sides), np.cos(angle), np.sin(angle)], axis=1)
        positions = np.vstack([ring, ring + [10.0, 0.0, 0.0]])
        normals = np.vstack([ring, ring])
        indices = []
        for k in range(sides):
            a, b = k, (k + 1) % sides
            indices += [a, b, b + sides, a, b + sides, a + sides]
        self.mesh = td.RestMesh(positions.astype(np.float32), normals.astype(np.float32), np.array(indices, dtype=np.uint32))

    def test_a_long_triangle_is_split_into_bands_of_rest_arc_length(self):
        rest = td.compile_tube_path(LINE)
        refined = td.refine_rest_mesh(self.mesh, rest, 1.0)
        # Ten bands, each carrying every side, and every refined triangle names its source.
        self.assertGreaterEqual(len(refined.indices) // 3, 10 * 16)
        distances = td.project_distances(rest, refined.positions.astype(np.float64))
        self.assertEqual(set(np.round(np.unique(np.round(distances, 6)), 6)), {float(n) for n in range(11)})
        self.assertEqual(len(refined.indices) // 3, len(refined.source_triangles))
        # A band no shorter than the tube leaves it as it is.
        self.assertIsNone(td.refine_rest_mesh(self.mesh, rest, 10.0).source_triangles)

    def test_refinement_past_its_ceiling_and_a_mesh_past_the_bend_are_refused(self):
        rest = td.compile_tube_path(LINE)
        with mock.patch.object(td, "MAX_REFINED_TRIANGLES", 20), self.assertRaisesRegex(
                td.TubeDeformationError, "refined tube exceeds 20 triangles; increase maxSegmentLength"):
            td.refine_rest_mesh(self.mesh, rest, 1.0)
        # Bent tighter than the tube is round, the inside of the rest surface would cross
        # the centre of curvature.
        tight = {"normal": [0.0, 0.0, 1.0], "segments": [
            {"kind": "arc", "center": [0.0, 0.5, 0.0], "axis": [0.0, 0.0, 1.0], "start": [0.0, 0.0, 0.0], "sweepDeg": 90.0}]}
        with self.assertRaisesRegex(td.TubeDeformationError, "rest mesh crosses the centerline curvature radius"):
            td.mapping_for(self.mesh, td.compile_tube_path(tight))


if __name__ == "__main__":
    unittest.main()
