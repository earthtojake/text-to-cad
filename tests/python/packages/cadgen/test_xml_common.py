"""Helpers shared by the URDF, SDF and SRDF readers.

These were five, three and three near-copies before they moved here, so the tests worth
having are the ones that pin the behaviour each format was relying on -- and, just as
importantly, that the deliberate differences were NOT flattened in the process.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cadgen import sdf_validation, srdf_source, urdf_source  # noqa: E402
from cadgen.xml_common import children, display_path, duplicate_values, local_name  # noqa: E402


class DisplayPath(unittest.TestCase):
    def test_a_path_under_the_cwd_is_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp).resolve()
            target = root / "sub" / "robot.urdf"
            previous = os.getcwd()
            os.chdir(root)
            try:
                self.assertEqual(display_path(target), "sub/robot.urdf")
            finally:
                os.chdir(previous)

    def test_a_path_outside_the_cwd_stays_absolute(self):
        # A bare basename would be ambiguous, so the absolute form is kept on purpose.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp).resolve()
            previous = os.getcwd()
            os.chdir(root)
            try:
                shown = display_path(root.parent / "elsewhere.urdf")
            finally:
                os.chdir(previous)
        # Absolute, not "starts with /": on Windows the absolute form is "C:/Users/...",
        # which has a drive and no leading slash. as_posix() has already normalised the
        # separators, so PurePosixPath reads the result the same way on either platform.
        self.assertTrue(pathlib.PurePath(shown).is_absolute() or shown[1:3] == ":/", shown)
        self.assertIn("elsewhere.urdf", shown)

    def test_posix_separators_on_every_platform(self):
        self.assertNotIn("\\", display_path(pathlib.Path("a") / "b" / "c.urdf"))


class LocalName(unittest.TestCase):
    def test_an_expanded_namespace_is_stripped(self):
        self.assertEqual(local_name("{http://example.test/ns}link"), "link")

    def test_a_bare_tag_is_unchanged(self):
        self.assertEqual(local_name("link"), "link")

    def test_a_colon_prefix_is_NOT_stripped(self):
        # An unexpanded `ns:tag` means the document declared no such namespace. SDF
        # reports that rather than accepting it, so this must not be normalised away.
        self.assertEqual(local_name("gazebo:link"), "gazebo:link")

    def test_srdf_keeps_its_own_prefix_stripping_variant(self):
        # SRDF deliberately differs: it accepts and strips the colon form. Pinned so a
        # future tidy-up cannot quietly collapse the two.
        self.assertEqual(srdf_source._local_name("group:name"), "name")
        self.assertEqual(srdf_source._local_name("{uri}group"), "group")


class Children(unittest.TestCase):
    def test_selects_by_local_name_across_namespaces(self):
        root = ET.fromstring(
            '<sdf xmlns:x="http://example.test/x"><model name="a"/><world name="w"/><model name="b"/></sdf>'
        )
        self.assertEqual([c.get("name") for c in children(root, "model")], ["a", "b"])

    def test_comments_are_never_matched(self):
        root = ET.fromstring("<sdf><!-- a comment --><model name='a'/></sdf>")
        self.assertEqual(len(children(root, "model")), 1)


class DuplicateValues(unittest.TestCase):
    def test_returns_each_repeated_value_once_sorted(self):
        self.assertEqual(duplicate_values(["b", "a", "b", "c", "a", "b"]), ["a", "b"])

    def test_no_duplicates_is_empty(self):
        self.assertEqual(duplicate_values(["a", "b", "c"]), [])
        self.assertEqual(duplicate_values([]), [])


class DeliberateDifferencesSurvive(unittest.TestCase):
    """The refactor's real risk was merging things that only looked alike."""

    def test_the_two_unknown_child_checks_are_still_separate(self):
        # URDF skips a `ns:tag` colon prefix as a namespaced extension; SDF only knows the
        # {uri}tag form. One shared implementation would change which unknown children get
        # reported in one of them.
        self.assertIsNot(
            urdf_source._warn_unknown_children, sdf_validation._warn_unknown_children
        )

    def test_the_sdf_reader_and_validator_keep_their_own_required_name(self):
        # The reader raises; the validator records a finding and continues.
        from cadgen import sdf_source

        self.assertIsNot(sdf_source._required_name, sdf_validation._required_name)

    def test_the_inertia_routine_is_now_one_function(self):
        # 17 statements of eigenvalue math that used to exist twice. A divergent copy
        # would let one format accept a tensor the other rejects.
        self.assertIs(
            sdf_validation.symmetric_inertia_eigenvalues,
            urdf_source.symmetric_inertia_eigenvalues,
        )




class InvalidRobotFileText(unittest.TestCase):
    def test_invalid_utf8_is_a_validation_result(self):
        from cadgen import sdf, srdf, urdf
        from cadgen.sdf_source import SdfSourceError, read_sdf_source

        with tempfile.TemporaryDirectory() as tmp:
            for extension, validate in (("urdf", urdf.validate), ("srdf", srdf.validate), ("sdf", sdf.validate)):
                with self.subTest(extension=extension):
                    path = pathlib.Path(tmp) / f"invalid.{extension}"
                    path.write_bytes(b"<robot name='sample'>\xff</robot>")
                    result = validate(path)
                    self.assertFalse(result.ok)
                    self.assertTrue(result.issues)
                    self.assertIn("decode", result.issues[0].message)
            with self.assertRaises(SdfSourceError):
                read_sdf_source(pathlib.Path(tmp) / "invalid.sdf")


if __name__ == "__main__":
    unittest.main()
