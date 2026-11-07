"""KiCad's S-expressions: read and written back without losing a digit or a quote."""

from __future__ import annotations

import unittest

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.engine.formats.kicad import sexpr  # noqa: E402
from cad.engine.formats.kicad.sexpr import Sym  # noqa: E402

DOCUMENT = (
    '(footprint "R_0603" (version 20241229) (layer "F.Cu")\n'
    '\t(property "Value" "say \\"hi\\"\\\\n" (at 0 1.43 90))\n'
    "\t(attr smd)\n"
    '\t(pad "1" smd roundrect (at -0.825 0) (roundrect_rratio 0.08333333333) (layers "F.Cu" F.Mask))\n'
    "\t(fp_poly (pts (xy 0 0) (xy 1 0) (xy 1 1) (xy 0 1) (xy -1 0) (xy -1 -1) (xy 2 2)) (layer \"F.SilkS\"))\n"
    "\t(effects (font (size 1 1)) hide)\n"
    ")\n"
)


class KicadSexprTest(unittest.TestCase):
    def test_atoms_keep_their_kind(self) -> None:
        tree = sexpr.parse(DOCUMENT)
        pad = sexpr.find(tree, "pad")
        self.assertEqual(pad[:4], [Sym("pad"), "1", Sym("smd"), Sym("roundrect")])
        self.assertIsInstance(pad[2], Sym)
        self.assertNotIsInstance(pad[1], Sym)
        self.assertEqual(sexpr.find(pad, "layers")[1:], ["F.Cu", Sym("F.Mask")])
        self.assertEqual(sexpr.value(tree, "version"), 20241229)
        self.assertEqual(sexpr.find(tree, "property")[2], 'say "hi"\\n')

    def test_writing_round_trips_and_is_idempotent(self) -> None:
        tree = sexpr.parse(DOCUMENT)
        text = sexpr.dumps(tree)
        self.assertEqual(sexpr.parse(text), tree)
        self.assertEqual(sexpr.dumps(sexpr.parse(text)), text)
        # An atom after a child list stays after it.
        effects = sexpr.find(sexpr.parse(text), "effects")
        self.assertEqual(effects[-1], Sym("hide"))

    def test_numbers_are_the_shortest_text_that_reads_back(self) -> None:
        self.assertEqual(
            [sexpr.format_number(value) for value in (12.0, -0.0, 0.1 + 0.2, round(0.1 + 0.2, 6), 1e-07, 0.08333333333, 7)],
            ["12", "0", "0.30000000000000004", "0.3", "0.0000001", "0.08333333333", "7"],
        )
        with self.assertRaises(TypeError):
            sexpr.format_number(True)

    def test_a_string_is_escaped_and_read_as_kicad_does(self) -> None:
        # KiCad's reader (DSNLEXER): a backslash before anything it does not name is itself, so a path
        # written by hand reads as written; the named escapes, hex and octal bytes are its own.
        cases = {
            r"C:\Users\RUNNER~1\x.step": "C:\\Users\\RUNNER~1x.step",
            r"C:\Users\me\outside.step": "C:\\Users\\me\\outside.step",
            r"say \"hi\" \\ \q": 'say "hi" \\ \\q',
            r"\a\b\f\n\r\t\v": "\a\b\f\n\r\t\v",
            r"\x41\x4a2 \xg \101\0 \8": "AJ2 xg A\x00 \\8",
            r"caf\303\251 \xc3\xa9": "café é",
        }
        for written, read in cases.items():
            with self.subTest(written=written):
                self.assertEqual(sexpr.unescape(written), read)
                self.assertEqual(sexpr.parse(f'(model "{written}")')[1], read)
        # It writes what KiCad writes (OUTPUTFORMATTER::Quotes), and every string reads back as itself.
        self.assertEqual(sexpr.quote('C:\\Users\\"x"\r\n\t'), r'"C:\\Users\\\"x\"\r\n' + '\t"')
        for text in ['C:\\Users\\x\\"evil".step', "\\\\server\\share\\a.step", "line\r\nnext", "\\x41 \\101"]:
            with self.subTest(text=text):
                self.assertEqual(sexpr.parse(sexpr.dumps([Sym("model"), text]))[1], text)

    def test_malformed_text_is_refused(self) -> None:
        for text in ("(a (b)", "(a))", "(a) (b)", "", "x"):
            with self.subTest(text=text), self.assertRaises(sexpr.SexprError):
                sexpr.parse(text)


if __name__ == "__main__":
    unittest.main()
