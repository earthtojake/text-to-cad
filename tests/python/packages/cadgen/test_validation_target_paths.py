"""Robot validation must read the exact path the caller supplied."""

from __future__ import annotations

import contextlib
from pathlib import Path
import tempfile
import unittest

from cadgen import urdf
from cadgen._internal.validation_door import resolved_target


class ValidationTargetPathsTests(unittest.TestCase):
    def test_leading_space_does_not_select_a_different_robot(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / "robot.urdf").write_text("<not_a_robot/>", encoding="utf-8")
            target = root / " robot.urdf"
            target.write_text('<robot name="one"><link name="base"/></robot>', encoding="utf-8")

            with contextlib.chdir(root):
                result = urdf.validate(Path(" robot.urdf"))

            self.assertEqual(result.path, target)
            self.assertTrue(result.ok, result)

    def test_blank_input_is_still_rejected(self) -> None:
        for value in ("", " ", "\t"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "non-empty path"):
                    resolved_target(value, label="urdf")


if __name__ == "__main__":
    unittest.main()
