"""Helpers shared by the URDF and SRDF readers.

These were near-copies before they moved here, so the tests worth
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

from cad import srdf_source  # noqa: E402
from cad._internal.xml_common import children, display_path, duplicate_values, local_name  # noqa: E402


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
        # An unexpanded `ns:tag` means the document declared no such namespace, so the tag
        # is not the one it looks like: this must not be normalised away.
        self.assertEqual(local_name("gazebo:link"), "gazebo:link")

    def test_srdf_keeps_its_own_prefix_stripping_variant(self):
        # SRDF deliberately differs: it accepts and strips the colon form. Pinned so a
        # future tidy-up cannot quietly collapse the two.
        self.assertEqual(srdf_source._local_name("group:name"), "name")
        self.assertEqual(srdf_source._local_name("{uri}group"), "group")


class Children(unittest.TestCase):
    def test_selects_by_local_name_across_namespaces(self):
        root = ET.fromstring(
            '<robot xmlns:x="http://example.test/x"><link name="a"/><joint name="j"/><link name="b"/></robot>'
        )
        self.assertEqual([c.get("name") for c in children(root, "link")], ["a", "b"])

    def test_comments_are_never_matched(self):
        root = ET.fromstring("<robot><!-- a comment --><link name='a'/></robot>")
        self.assertEqual(len(children(root, "link")), 1)


class DuplicateValues(unittest.TestCase):
    def test_returns_each_repeated_value_once_sorted(self):
        self.assertEqual(duplicate_values(["b", "a", "b", "c", "a", "b"]), ["a", "b"])

    def test_no_duplicates_is_empty(self):
        self.assertEqual(duplicate_values(["a", "b", "c"]), [])
        self.assertEqual(duplicate_values([]), [])


class InvalidRobotFileText(unittest.TestCase):
    def test_invalid_utf8_is_a_validation_result(self):
        from cad import srdf, urdf

        with tempfile.TemporaryDirectory() as tmp:
            for extension, validate in (("urdf", urdf.validate), ("srdf", srdf.validate)):
                with self.subTest(extension=extension):
                    path = pathlib.Path(tmp) / f"invalid.{extension}"
                    path.write_bytes(b"<robot name='sample'>\xff</robot>")
                    result = validate(path)
                    self.assertFalse(result.ok)
                    self.assertEqual([issue.code for issue in result.issues], ["unreadable_file"])


if __name__ == "__main__":
    unittest.main()
