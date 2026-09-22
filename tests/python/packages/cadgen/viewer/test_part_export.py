"""Where an exported part lands, and where it must not."""

from __future__ import annotations

import os
import tempfile
import unittest

from cadgen.viewer.backend import ForbiddenAssetError
from cadgen.viewer.part_export import EXPORT_DIRECTORY, resolve_export_target, safe_export_name


class SafeExportNameTests(unittest.TestCase):
    def test_a_part_name_becomes_one_stl_filename(self):
        self.assertEqual(safe_export_name("plant_1_02"), "plant_1_02.stl")
        self.assertEqual(safe_export_name("plant_1_02.stl"), "plant_1_02.stl")

    def test_a_name_that_looks_like_a_path_is_reduced_to_a_name(self):
        # Part names come from whoever authored the STEP, so they are untrusted
        # text. Anything shaped like traversal is a bug or an attack, never a
        # filename worth preserving.
        self.assertEqual(safe_export_name("../../etc/passwd"), "passwd.stl")
        self.assertEqual(safe_export_name("a/b/c.stl"), "c.stl")
        self.assertEqual(safe_export_name("..").count("."), 1)

    def test_an_unusable_name_still_produces_a_file(self):
        for name in ("", "   ", "..", "///", None):
            self.assertEqual(safe_export_name(name), "part.stl")

    def test_separators_and_punctuation_collapse(self):
        self.assertEqual(safe_export_name("M3x8 bolt <2>"), "M3x8_bolt_2.stl")


class ResolveExportTargetTests(unittest.TestCase):
    def test_a_part_lands_in_the_projects_format_folder(self):
        # Beside STEP/ and DXF/, which is where a CAD project keeps outputs.
        with tempfile.TemporaryDirectory() as root:
            target, relative = resolve_export_target(root, "plant_1_02")
            self.assertEqual(relative, os.path.join(EXPORT_DIRECTORY, "plant_1_02.stl"))
            self.assertEqual(os.path.dirname(target), os.path.join(os.path.realpath(root), EXPORT_DIRECTORY))

    def test_the_reported_path_is_relative_so_the_tree_can_use_it(self):
        with tempfile.TemporaryDirectory() as root:
            _target, relative = resolve_export_target(root, "bracket")
            self.assertFalse(os.path.isabs(relative))

    def test_a_traversing_name_cannot_escape_the_project(self):
        with tempfile.TemporaryDirectory() as root:
            target, _relative = resolve_export_target(root, "../../../../tmp/evil")
            self.assertTrue(os.path.realpath(target).startswith(os.path.realpath(root)))

    def test_no_root_is_refused_rather_than_defaulting_somewhere(self):
        with self.assertRaises(ForbiddenAssetError):
            resolve_export_target("", "plant_1_02")

    def test_an_existing_export_directory_is_reused(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, EXPORT_DIRECTORY))
            target, relative = resolve_export_target(root, "again")
            self.assertEqual(relative, os.path.join(EXPORT_DIRECTORY, "again.stl"))
            self.assertTrue(os.path.realpath(target).startswith(os.path.realpath(root)))


if __name__ == "__main__":
    unittest.main()
