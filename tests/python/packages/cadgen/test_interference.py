"""cadgen.interference: pairwise part-vs-part clash detection."""

import unittest

from build123d import Box, Pos

from cadgen.interference import Occurrence, _shape_bbox, find_clashes


def occurrence(ref, name, shape):
    return Occurrence(ref=ref, name=name, shape=shape.wrapped, bbox=_shape_bbox(shape.wrapped))


class FindClashesTest(unittest.TestCase):
    def setUp(self):
        self.a = occurrence("o1.1", "block_a", Pos(0, 0, 0) * Box(100, 100, 100))
        # overlaps a by 20 mm across a 100x100 face -> 200000 mm^3
        self.overlapping = occurrence("o1.2", "block_b", Pos(80, 0, 0) * Box(100, 100, 100))
        self.far = occurrence("o1.3", "block_c", Pos(0, 400, 0) * Box(100, 100, 100))
        self.touching = occurrence("o1.4", "block_d", Pos(0, 100, 0) * Box(100, 100, 100))

    def test_reports_a_real_overlap_with_its_volume(self):
        clashes, _stats = find_clashes([self.a, self.overlapping])
        self.assertEqual(len(clashes), 1)
        self.assertAlmostEqual(clashes[0].volume, 200000.0, delta=1.0)
        self.assertEqual({clashes[0].a_ref, clashes[0].b_ref}, {"o1.1", "o1.2"})

    def test_separated_parts_are_rejected_by_bbox_without_a_boolean(self):
        clashes, stats = find_clashes([self.a, self.far])
        self.assertEqual(clashes, [])
        self.assertEqual(stats["pairs_skipped_bbox"], 1)
        self.assertEqual(stats["pairs_tested"], 0)

    def test_touching_faces_are_contact_not_a_clash(self):
        # Neighbouring panels share a face by design; a sliver must not be a clash.
        clashes, stats = find_clashes([self.a, self.touching])
        self.assertEqual(clashes, [], "coincident faces are contact, not interpenetration")
        self.assertGreaterEqual(stats["pairs_tested"], 1, "and it must actually be tested")

    def test_tolerance_can_be_raised_to_ignore_small_overlaps(self):
        clashes, _stats = find_clashes([self.a, self.overlapping], tolerance=500000.0)
        self.assertEqual(clashes, [])

    def test_stats_distinguish_nothing_overlapped_from_nothing_tested(self):
        _clashes, stats = find_clashes([self.a, self.overlapping, self.far, self.touching])
        self.assertEqual(stats["occurrences"], 4)
        self.assertEqual(stats["pairs_total"], 6)
        self.assertGreater(stats["pairs_tested"], 0)

    def test_max_pairs_truncation_is_reported(self):
        _clashes, stats = find_clashes(
            [self.a, self.overlapping, self.touching], max_pairs=0
        )
        self.assertEqual(stats["pairs_tested"], 0)
        self.assertGreater(stats["pairs_truncated"], 0, "silent truncation would fake a pass")

    def test_clashes_are_sorted_worst_first(self):
        small = occurrence("o1.5", "small", Pos(0, 0, 98) * Box(100, 100, 100))
        clashes, _stats = find_clashes([self.a, self.overlapping, small])
        self.assertGreaterEqual(len(clashes), 2)
        volumes = [clash.volume for clash in clashes]
        self.assertEqual(volumes, sorted(volumes, reverse=True))


if __name__ == "__main__":
    unittest.main()
