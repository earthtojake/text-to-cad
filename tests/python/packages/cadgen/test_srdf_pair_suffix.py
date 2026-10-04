"""Pairing must recognize every URDF suffix accepted by the URDF validator."""
from pathlib import Path
import tempfile
import unittest

from cadgen import srdf, urdf

URDF = '<robot name="arm"><link name="base"/></robot>'
SRDF = '<robot name="arm"><group name="arm"><link name="base"/></group></robot>'


class SrdfPairSuffixTests(unittest.TestCase):
    def test_uppercase_and_mixed_case_urdf_suffixes_can_pair(self):
        for suffix in (".URDF", ".UrDf"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                description = root / f"description{suffix}"
                description.write_text(URDF, encoding="utf-8")
                semantic = root / "planning.srdf"
                semantic.write_text(SRDF, encoding="utf-8")
                self.assertTrue(urdf.validate(description).ok)
                result = srdf.validate(semantic)
                self.assertTrue(result.ok, result)

    def test_case_variant_suffix_cannot_hide_ambiguous_pair(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("one.urdf", "two.URDF"):
                (root / name).write_text(URDF, encoding="utf-8")
            semantic = root / "planning.srdf"
            semantic.write_text(SRDF, encoding="utf-8")
            result = srdf.validate(semantic)
            self.assertFalse(result.ok)
            self.assertIn("ambiguous_paired_urdf", {item.code for item in result.issues})

    def test_other_suffixes_and_directories_do_not_become_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "description.urdf").write_text(URDF, encoding="utf-8")
            (root / "not_a_robot.xml").write_text(URDF, encoding="utf-8")
            (root / "folder.URDF").mkdir()
            semantic = root / "planning.srdf"
            semantic.write_text(SRDF, encoding="utf-8")
            self.assertTrue(srdf.validate(semantic).ok)


if __name__ == "__main__":
    unittest.main()
