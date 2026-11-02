"""Keeping the fonts that break `import build123d` out of its font scan (#322, #636).

build123d registers every font in the system font folders at import time with no
per-file guard, so one malformed file aborts the import and every cad command with
it, raising a fontTools error that names no file. A font with no family name aborts it
the same way, with OCCT's error (`EmptyFamily`, #636).

cadgen filters that one folder listing so such a file is never opened (`GlobGuard`,
`EmptyFamily`), and a checker names it (`CheckFontsCommand`). The permanent fix
belongs upstream, in `register_folder`.
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

from cad import check_fonts  # noqa: E402
from cad._internal import font_scan  # noqa: E402

# A real OpenType header, for a file that only looks like a font.
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

        with mock.patch.dict(os.environ, {"CAD_FONT_GUARD": "0"}):
            self.assertFalse(font_scan.install_font_guard())
        self.assertIs(glob.glob, self._real_glob)


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
