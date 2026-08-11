import os
import tempfile
import unittest
from pathlib import Path

from cadgen.cad_ref_syntax import normalize_cad_path
from cadgen.step_targets import CadRefError, entry_target_from_target


class NormalizeCadPathTests(unittest.TestCase):
    def test_strips_logical_step_suffixes(self) -> None:
        self.assertEqual(normalize_cad_path("models/foo.step"), "models/foo")
        self.assertEqual(normalize_cad_path("models/foo.stp"), "models/foo")

    def test_strips_step_py_generator_suffixes(self) -> None:
        self.assertEqual(normalize_cad_path("models/foo.step.py"), "models/foo")
        self.assertEqual(normalize_cad_path("models/foo.stp.py"), "models/foo")

    def test_plain_entry_path_passes_through(self) -> None:
        self.assertEqual(normalize_cad_path("models/foo"), "models/foo")


class EntryTargetAbsolutePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_cwd = Path.cwd()
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name).resolve()
        os.chdir(self.root)

    def tearDown(self) -> None:
        os.chdir(self._original_cwd)
        self._temporary_directory.cleanup()

    def test_absolute_generator_target_under_cwd_relativizes(self) -> None:
        target = self.root / "models" / "foo.step.py"
        entry = entry_target_from_target(str(target))
        self.assertEqual(entry.cad_path, "models/foo")

    def test_absolute_step_target_under_cwd_relativizes(self) -> None:
        target = self.root / "models" / "foo.step"
        entry = entry_target_from_target(str(target))
        self.assertEqual(entry.cad_path, "models/foo")

    def test_absolute_target_outside_cwd_raises_clear_error(self) -> None:
        with self.assertRaises(CadRefError) as caught:
            entry_target_from_target("/definitely/not/under/cwd/foo.step.py")
        self.assertIn("outside the command cwd", str(caught.exception))

    def test_relative_generator_target_normalizes(self) -> None:
        entry = entry_target_from_target("foo.step.py")
        self.assertEqual(entry.cad_path, "foo")


if __name__ == "__main__":
    unittest.main()
