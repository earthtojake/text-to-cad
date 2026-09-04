import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cadgen.cad_ref_syntax import normalize_cad_path
from cadgen.step_targets import CadRefError, entry_target_from_target, resolve_step_target


class NormalizeCadPathTests(unittest.TestCase):
    def test_strips_logical_step_suffixes(self) -> None:
        self.assertEqual(normalize_cad_path("models/foo.step"), "models/foo")
        self.assertEqual(normalize_cad_path("models/foo.stp"), "models/foo")

    def test_strips_step_py_generator_suffixes(self) -> None:
        self.assertEqual(normalize_cad_path("models/foo.py"), "models/foo")
        self.assertEqual(normalize_cad_path("models/foo.py"), "models/foo")

    def test_plain_entry_path_passes_through(self) -> None:
        self.assertEqual(normalize_cad_path("models/foo"), "models/foo")


class EntryTargetAbsolutePathTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_cwd = Path.cwd()
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name).resolve()
        # A second tree that is NOT under the cwd, for the native-path cases.
        self._outside = tempfile.TemporaryDirectory()
        os.chdir(self.root)

    def tearDown(self) -> None:
        os.chdir(self._original_cwd)
        self._temporary_directory.cleanup()
        self._outside.cleanup()

    def test_absolute_generator_target_under_cwd_relativizes(self) -> None:
        target = self.root / "models" / "foo.py"
        entry = entry_target_from_target(str(target))
        self.assertEqual(entry.cad_path, "models/foo")

    def test_absolute_step_target_under_cwd_relativizes(self) -> None:
        target = self.root / "models" / "foo.step"
        entry = entry_target_from_target(str(target))
        self.assertEqual(entry.cad_path, "models/foo")

    def test_absolute_target_outside_cwd_is_named_by_its_own_parent(self) -> None:
        """Targets are NATIVE paths: absolute works anywhere, cwd or not.

        This used to be an error ("outside the command cwd"), which was wrong twice
        over -- an existing file outside the cwd already resolved through another
        branch, and a rooted path to a MISSING file reported a cwd complaint about a
        file-not-found. Identity is the separate question: a path from outside the
        workspace has no cwd-relative name, so it is named against its own parent,
        which leaves the bare stem.
        """
        entry = entry_target_from_target("/definitely/not/under/cwd/foo.py")
        self.assertEqual(entry.cad_path, "foo")

    def test_a_rooted_target_resolves_even_where_it_is_not_absolute(self) -> None:
        """Resolution keys on ROOTED, not on is_absolute(), because of Windows.

        There, "/definitely/not/under/cwd" has a root and no drive, which makes it
        drive-RELATIVE and is_absolute() False -- so it used to fall through and become
        a cwd-relative cad path ("definitely/not/under/cwd/foo") that could never
        resolve. resolve() anchors it to the current drive, which is what it means
        there, and the identity comes out the same shape as on POSIX.
        """
        entry = entry_target_from_target("/definitely/not/under/cwd/foo.py")
        self.assertEqual(entry.cad_path, "foo")

    def test_an_existing_absolute_target_outside_cwd_resolves_and_inspects(self) -> None:
        outside = Path(self._outside.name).resolve()
        document = outside / "widget.step"
        document.write_text("ISO-10303-21;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
        self.assertEqual(entry_target_from_target(str(document)).cad_path, "widget")
        resolved = resolve_step_target(str(document))
        self.assertEqual(resolved.step_path, document)
        self.assertEqual(resolved.cad_path, "widget")
        # A door takes the document with its extension: a bare stem names nothing.
        with self.assertRaises(CadRefError) as caught:
            resolve_step_target(str(outside / "widget"))
        self.assertIn("not a STEP document path", str(caught.exception))

    def test_a_missing_absolute_target_reports_the_file_not_the_cwd(self) -> None:
        missing = Path(self._outside.name).resolve() / "nope.step"
        with self.assertRaises(CadRefError) as caught:
            resolve_step_target(str(missing))
        message = str(caught.exception)
        self.assertIn("STEP file not found", message)
        self.assertIn(str(missing), message)
        self.assertNotIn("cwd", message)

    def test_a_tilde_target_expands(self) -> None:
        home = Path(self._outside.name).resolve()
        document = home / "gizmo.step"
        document.write_text("ISO-10303-21;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            self.assertEqual(entry_target_from_target("~/gizmo.step").cad_path, "gizmo")
            self.assertEqual(resolve_step_target("~/gizmo.step").step_path, document)

    def test_relative_generator_target_normalizes(self) -> None:
        entry = entry_target_from_target("foo.py")
        self.assertEqual(entry.cad_path, "foo")


if __name__ == "__main__":
    unittest.main()
