"""Naming the font file that breaks `import build123d` (issue #322).

build123d parses every font in the system font folders at import time with no
per-file guard, so one malformed file aborts the import and every cadgen command with
it, raising a fontTools error that names no file.

cadgen filters that one folder listing so the bad file is never opened (`GlobGuard`).
The rest is what happens when the guard is off or did not catch it: a message naming
the file (`FailureRecognition`) and a checker that finds it (`CheckFontsCommand`).
The permanent fix belongs upstream, in `register_folder`.
"""

from __future__ import annotations

import io
import contextlib
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cadgen import check_fonts  # noqa: E402
from cadgen._internal import font_scan  # noqa: E402

# A real TrueType header, and a file that only looks like one.
VALID_TTF_HEADER = b"\x00\x01\x00\x00"
VALID_OTF_HEADER = b"OTTO"


class _FontDir:
    """A folder of font-named files, none of which has to be a real font."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="tmp-cadgen-fonts-")
        self.path = pathlib.Path(self._tmp.name)
        return self

    def __exit__(self, *exc):
        self._tmp.cleanup()
        return False

    def write(self, name: str, data: bytes) -> str:
        target = self.path / name
        target.write_bytes(data)
        return str(target)


class HeaderScan(unittest.TestCase):
    """`unparseable_fonts` reads four bytes; it must never parse a font itself."""

    def test_a_file_with_no_sfnt_magic_is_reported(self):
        with _FontDir() as fonts:
            bad = fonts.write("broken.ttf", b"this is not a font at all")
            self.assertEqual(font_scan.unparseable_fonts([str(fonts.path)]), [bad])

    def test_valid_headers_are_left_alone(self):
        with _FontDir() as fonts:
            fonts.write("truetype.ttf", VALID_TTF_HEADER + b"rest")
            fonts.write("opentype.otf", VALID_OTF_HEADER + b"rest")
            fonts.write("collection.ttc", b"ttcf" + b"rest")
            self.assertEqual(font_scan.unparseable_fonts([str(fonts.path)]), [])

    def test_non_font_files_are_not_examined(self):
        # register_folder globs ttf/otf/ttc only, so anything else cannot be the cause.
        with _FontDir() as fonts:
            fonts.write("notes.txt", b"not a font")
            fonts.write("image.png", b"\x89PNG")
            self.assertEqual(font_scan.unparseable_fonts([str(fonts.path)]), [])

    def test_a_missing_directory_is_not_an_error(self):
        # The diagnostic runs on an error path; it may not raise a second error.
        self.assertEqual(font_scan.unparseable_fonts(["/no/such/font/directory"]), [])

    def test_the_scan_is_not_recursive(self):
        # register_folder's glob is single-level, so a file it never opens is not a
        # file that can have broken the import.
        with _FontDir() as fonts:
            nested = fonts.path / "nested"
            nested.mkdir()
            (nested / "broken.ttf").write_bytes(b"not a font")
            self.assertEqual(font_scan.unparseable_fonts([str(fonts.path)]), [])


class GlobGuard(unittest.TestCase):
    """The fix: hide unparseable fonts from the listing build123d hands to fontTools."""

    def setUp(self):
        import glob

        self._real_glob = glob.glob
        font_scan.skipped_fonts.clear()
        self.addCleanup(setattr, glob, "glob", self._real_glob)
        self.addCleanup(font_scan.skipped_fonts.clear)

    def test_it_filters_a_font_folder_listing(self):
        import glob

        with _FontDir() as fonts:
            bad = fonts.write("broken.ttf", b"not a font")
            font_scan.install_font_guard()
            # build123d globs "*" + ext, with no dot -- the pattern shape matters.
            kept = glob.glob(os.path.join(str(fonts.path), "*ttf"))
        self.assertEqual(kept, [])
        self.assertEqual(font_scan.skipped_fonts, [bad])

    def test_a_lazily_broken_font_is_filtered_too(self):
        import glob

        with _FontDir() as fonts:
            bad = fonts.write("plausible.otf", VALID_OTF_HEADER + b"garbage")
            font_scan.install_font_guard()
            kept = glob.glob(os.path.join(str(fonts.path), "*otf"))
        self.assertEqual(kept, [])
        self.assertEqual(font_scan.skipped_fonts, [bad])


    def test_it_can_be_switched_off(self):
        import glob

        with mock.patch.dict(os.environ, {"CADGEN_FONT_GUARD": "0"}):
            self.assertFalse(font_scan.install_font_guard())
        self.assertIs(glob.glob, self._real_glob)

    def test_the_warning_names_what_was_dropped(self):
        self.assertEqual(font_scan.skipped_fonts_warning(), "")
        font_scan.skipped_fonts.append("/fonts/broken.ttf")
        self.assertIn("/fonts/broken.ttf", font_scan.skipped_fonts_warning())


class FailureRecognition(unittest.TestCase):
    def test_a_fonttools_error_is_recognised(self):
        from fontTools.ttLib import TTLibError

        self.assertTrue(font_scan.is_font_scan_failure(TTLibError("bad sfntVersion")))

    def test_a_wrapped_fonttools_error_is_recognised(self):
        from fontTools.ttLib import TTLibError

        try:
            try:
                raise TTLibError("bad sfntVersion")
            except TTLibError as inner:
                raise ImportError("build123d failed") from inner
        except ImportError as outer:
            self.assertTrue(font_scan.is_font_scan_failure(outer))

    def test_an_unrelated_error_is_not(self):
        self.assertFalse(font_scan.is_font_scan_failure(ModuleNotFoundError("no OCP")))
        self.assertEqual(font_scan.font_scan_failure_message(ValueError("nope")), "")

    def test_the_message_names_the_file_and_the_cause(self):
        from fontTools.ttLib import TTLibError

        with _FontDir() as fonts:
            bad = fonts.write("broken.ttf", b"not a font")
            message = font_scan.font_scan_failure_message(
                TTLibError("bad sfntVersion"), dirs=[str(fonts.path)]
            )
        self.assertIn(bad, message)
        self.assertIn("build123d bug", message)
        self.assertIn("Move or rename", message)


class CheckFontsCommand(unittest.TestCase):
    def test_it_catches_a_font_that_only_fails_once_a_table_is_read(self):
        # The regression this guards: TTFont(path) is LAZY. A file with a valid sfnt
        # header but a broken table directory constructs without complaint and then
        # fails inside build123d's _get_font_faces, whose first act is
        # ft_font["name"].names. A check that stopped at construction would report a
        # clean sweep on the exact machine that cannot import build123d.
        with _FontDir() as fonts:
            plausible = fonts.write("plausible.otf", VALID_OTF_HEADER + b"garbage")
            failures = check_fonts.check([str(fonts.path)])
        self.assertEqual([path for path, _ in failures], [plausible])

    def test_it_reports_a_file_with_no_sfnt_magic(self):
        with _FontDir() as fonts:
            bad = fonts.write("broken.ttf", b"not a font")
            failures = check_fonts.check([str(fonts.path)])
        self.assertEqual([path for path, _ in failures], [bad])


    def test_a_bad_font_exits_nonzero_and_names_it(self):
        with _FontDir() as fonts:
            bad = fonts.write("broken.ttf", b"not a font")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = check_fonts.main([str(fonts.path)])
        self.assertEqual(code, 1)
        self.assertIn(bad, out.getvalue())


if __name__ == "__main__":
    unittest.main()
