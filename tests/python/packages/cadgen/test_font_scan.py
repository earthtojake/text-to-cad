"""Naming the font file that breaks `import build123d` (issue #322).

build123d parses every font in the system font folders at import time with no
per-file guard, so one malformed file aborts the import and every cadgen command with
it, raising a fontTools error that names no file. A font with no family name aborts it
the same way, with OCCT's error (`EmptyFamily`, #636).

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


def _font_file(
    fonts: _FontDir,
    name: str,
    *,
    family: str | None = "Test Family",
    preferred: str | None = None,
    undecodable_family: bool = False,
) -> str:
    """Write a real, tiny TrueType font into `fonts` and return its path.

    `family` is nameID 1 and `preferred` is nameID 16. Leaving both out is the shape of a
    font build123d registers with an empty name, which OCCT refuses (#636).
    `undecodable_family` puts a lone UTF-16 surrogate in nameID 1, which `toUnicode()`
    cannot decode.
    """
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables._n_a_m_e import NameRecord

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "A"])
    builder.setupCharacterMap({65: "A"})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((0, 500))
    pen.lineTo((500, 500))
    pen.closePath()
    glyph = pen.glyph()
    builder.setupGlyf({".notdef": glyph, "A": glyph})
    builder.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Scratch", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()

    names = builder.font["name"]
    names.removeNames(nameID=1)
    names.removeNames(nameID=16)
    if undecodable_family:
        record = NameRecord()
        record.nameID, record.platformID, record.platEncID, record.langID = 1, 3, 1, 0x409
        record.string = b"\xd8\x00"  # a lone high surrogate is not valid UTF-16BE
        names.names.append(record)
    elif family is not None:
        names.setName(family, 1, 3, 1, 0x409)
    if preferred is not None:
        names.setName(preferred, 16, 3, 1, 0x409)

    target = fonts.path / name
    builder.save(str(target))
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


class EmptyFamily(unittest.TestCase):
    """#636: a font with no family name passes every parse check, then OCCT refuses its
    empty name and `import build123d` fails. The guard must skip it."""

    def setUp(self):
        import glob

        self._real_glob = glob.glob
        font_scan.skipped_fonts.clear()
        self.addCleanup(setattr, glob, "glob", self._real_glob)
        self.addCleanup(font_scan.skipped_fonts.clear)

    def test_build123d_itself_refuses_a_font_with_no_family_name(self):
        # Pins the cause to build123d's own code, so the fixture cannot drift from what
        # it models. If a build123d release stops raising here, the guard can go.
        from build123d.text import FontManager
        from fontTools.ttLib import TTFont

        with _FontDir() as fonts:
            path = _font_file(fonts, "nofamily.ttf", family=None)
            with self.assertRaisesRegex(Exception, "empty font name"):
                FontManager.__new__(FontManager)._get_font_faces(TTFont(path), path)

    def test_a_font_with_no_family_name_is_skipped(self):
        import glob

        with _FontDir() as fonts:
            bad = _font_file(fonts, "nofamily.ttf", family=None)
            font_scan.install_font_guard()
            kept = glob.glob(os.path.join(str(fonts.path), "*ttf"))
        self.assertEqual(kept, [])
        self.assertEqual(font_scan.skipped_fonts, [bad])

    def test_a_family_name_that_cannot_be_decoded_is_skipped(self):
        import glob

        with _FontDir() as fonts:
            bad = _font_file(fonts, "undecodable.ttf", undecodable_family=True)
            font_scan.install_font_guard()
            kept = glob.glob(os.path.join(str(fonts.path), "*ttf"))
        self.assertEqual(kept, [])
        self.assertEqual(font_scan.skipped_fonts, [bad])

    def test_a_blank_preferred_name_is_empty_as_build123d_sees_it(self):
        # build123d takes nameID 16 over nameID 1 and strips only at the end, so a blank
        # preferred name is an empty name even when nameID 1 has a real one.
        import glob

        with _FontDir() as fonts:
            bad = _font_file(fonts, "blank.ttf", family="Good Family", preferred="   ")
            font_scan.install_font_guard()
            kept = glob.glob(os.path.join(str(fonts.path), "*ttf"))
        self.assertEqual(kept, [])
        self.assertEqual(font_scan.skipped_fonts, [bad])

    def test_a_font_with_a_family_name_is_kept(self):
        import glob

        with _FontDir() as fonts:
            good = _font_file(fonts, "good.ttf", family="Good Family")
            font_scan.install_font_guard()
            kept = glob.glob(os.path.join(str(fonts.path), "*ttf"))
        self.assertEqual(kept, [good])
        self.assertEqual(font_scan.skipped_fonts, [])


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

    def test_the_empty_name_refusal_is_recognised_and_explained(self):
        # OCCT's error is not a fontTools error, so it is recognised by its text.
        error = RuntimeError("Font_SystemFont constructor called with empty font name")
        self.assertTrue(font_scan.is_font_scan_failure(error))
        message = font_scan.font_scan_failure_message(error, dirs=[])
        self.assertIn("family name", message)
        self.assertIn("check_fonts", message)


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

    def test_it_reports_a_font_with_no_family_name(self):
        with _FontDir() as fonts:
            nameless = _font_file(fonts, "nofamily.ttf", family=None)
            failures = check_fonts.check([str(fonts.path)])
        self.assertEqual([path for path, _ in failures], [nameless])
        self.assertIn("family name", failures[0][1])


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
