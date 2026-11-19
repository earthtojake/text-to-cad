"""``cad.eng_drawing`` as released: what a drawing script written for an earlier
release imports, calls and gets.

The engine reads a part's sizes off its faces, and would rather be told nothing
it can contradict. A script written before it could, types them: a hole's
diameter, a circle's radius, a point where it believes the part to be. Such a
script still draws what it drew. Each call here is one an earlier release took;
it is drawn as typed, and the drawing's report says where the part reads
otherwise.

Every part is built here, small, from build123d.
"""

from __future__ import annotations

import contextlib
import inspect
import io
import unittest
from pathlib import Path

from tests.python.support.tmp_root import temporary_directory


class _Released:
    """The signatures of 0.11.13, the last release before the engine read parts."""

    def Sheet(size="A3", scale=1.0, title="UNTITLED", part_number="", material="", revision="A", author="",  # noqa: N802
              units="mm", projection="THIRD ANGLE", notes=(), ink="mono", text_height=3.5, general_tolerance="",
              revisions=(), views=None): ...
    def three_views(self, shape, *, gap=None, hidden=True, centre_marks=True, iso=False): ...
    def view(self, shape, name, *, at, label=None, hidden=True, centre_marks=True, scale=None): ...
    def dim(self, p1, p2, *, offset=None, text=None, orientation=None, tol=None, fit=None): ...
    def hole(self, center, diameter, *, depth=None, thru=False, cbore=None, csk=None, thread=None, count=None,
             angle=45.0, tol=None, fit=None, label=None): ...
    def diameter(self, center, radius, *, angle=45.0, text=None): ...
    def radius(self, center, radius, *, angle=45.0, text=None): ...
    def angle(self, vertex, p1, p2, *, offset=14.0): ...
    def note(self, text, at, *, offset=(10.0, 10.0)): ...
    def overall(self): ...
    def eng_drawing(func=None, *, out=None): ...
    def hole_callout_text(spec, *, tol=None, fit=None): ...


#: What a released call had to be given, or was given a default for, that is now
#: read off the part when left out: None stands for "as the part reads".
_NOW_READ_OFF_THE_PART = {("hole", "diameter"), ("hole", "thru"), ("diameter", "radius"), ("radius", "radius")}


def _block():
    """80 x 60 x 20 with a ⌀6 hole through at (-20, 0) and a ⌀5 hole 12 deep at (20, 0)."""
    from build123d import Align, Box, Cylinder, Pos

    up = (Align.CENTER, Align.CENTER, Align.MIN)
    return (Box(80, 60, 20, align=up) - Pos(-20, 0, 0) * Cylinder(3, 20, align=up)
            - Pos(20, 0, 20) * Cylinder(2.5, 12, align=(Align.CENTER, Align.CENTER, Align.MAX)))


def _bossed():
    """80 x 60 x 10 with a solid ⌀16 boss standing 10 on its middle."""
    from build123d import Align, Box, Cylinder, Pos

    up = (Align.CENTER, Align.CENTER, Align.MIN)
    return Box(80, 60, 10, align=up) + Pos(0, 0, 10) * Cylinder(8, 10, align=up)


def _plain(callout: str) -> str:
    """A callout's text less the symbols a sheet draws as line work, not as text."""
    return callout.translate(str.maketrans("", "", "⌀↧⌴⌵"))


def _drawn(part, annotate, **sheet_fields):
    """A three-view A3 sheet of ``part`` annotated by ``annotate(top, front, right)``:
    the text runs its callouts print (their symbols are line work), its
    dimensions' values, and what it reports."""
    from cad._internal.drawing_render import _render_sheet
    from cad.eng_drawing import Sheet

    sheet = Sheet("A3", **sheet_fields)
    annotate(*sheet.three_views(part))
    said: list[str] = []
    doc = _render_sheet(sheet, index=1, count=1, label="released", warnings=said)
    printed = [e.dxf.text for e in doc.modelspace().query("TEXT[layer=='DIM']")]
    values = [e.text for d in doc.modelspace().query("DIMENSION") for e in doc.blocks.get(d.dxf.geometry)
              if e.dxftype() == "MTEXT"]
    return printed, values, said


class ReleasedNamesTests(unittest.TestCase):
    """Every name a released script imports is there, taking what it took."""

    def test_every_released_name_takes_what_it_took(self) -> None:
        from cad import eng_drawing as module

        now = {"Sheet": module.Sheet, "eng_drawing": module.eng_drawing,
               "hole_callout_text": module.hole_callout_text,
               **{name: getattr(module.Sheet, name) for name in ("three_views", "view")},
               **{name: getattr(module.View, name) for name in ("dim", "hole", "diameter", "radius", "angle", "note",
                                                                "overall")}}
        for name, call in now.items():
            released = inspect.signature(getattr(_Released, name)).parameters
            current = inspect.signature(call).parameters
            for (given, was), is_now in zip(released.items(), current.values()):
                with self.subTest(call=name, parameter=given):
                    # The same parameter in the same place: a positional call still lands.
                    self.assertEqual((is_now.name, is_now.kind), (was.name, was.kind))
                    if (name, given) in _NOW_READ_OFF_THE_PART:
                        self.assertIsNone(is_now.default)
                    elif given != "views":  # a list of its own per sheet
                        self.assertEqual(is_now.default, was.default)
            for added in list(current.values())[len(released):]:
                with self.subTest(call=name, added=added.name):
                    self.assertEqual(added.kind, inspect.Parameter.KEYWORD_ONLY,
                                     "a parameter added after a release is given by name")
        for name in ("SHEET_SIZES", "VIEW_DIRECTIONS", "PROJECTIONS", "View"):
            self.assertTrue(hasattr(module, name), name)
        self.assertLessEqual({"eng_drawing", "Sheet", "View", "SHEET_SIZES"}, set(module.__all__))

    def test_a_sheet_given_positionally_reads_its_fields_as_released(self) -> None:
        from cad.eng_drawing import Sheet

        sheet = Sheet("A4", 0.5, "BLOCK", "B-1", "ABS", "C", "ME", "mm", "FIRST ANGLE", ["DEBURR."], "color", 3.0,
                      "ISO 2768-m", [("A", "2026-01-01", "RELEASED")])
        self.assertEqual((sheet.size, sheet.scale, sheet.title, sheet.part_number, sheet.material, sheet.revision,
                          sheet.author, sheet.units, sheet.projection, sheet.notes, sheet.ink, sheet.text_height,
                          sheet.general_tolerance, sheet.revisions, sheet.views),
                         ("A4", 0.5, "BLOCK", "B-1", "ABS", "C", "ME", "mm", "FIRST ANGLE", ("DEBURR.",), "color",
                          3.0, "ISO 2768-m", (("A", "2026-01-01", "RELEASED"),), []))

    def test_hole_callout_text_spells_a_callout_as_released(self) -> None:
        from cad.eng_drawing import hole_callout_text

        plain = {"diameter": 6.6, "depth": None, "thru": True, "cbore": (11, 6.5), "csk": None, "thread": None,
                 "count": 4, "label": "WHEEL"}
        self.assertEqual(hole_callout_text(plain), "4× %%c6.6 THRU   ⌴ %%c11 ↧6.5   WHEEL")
        self.assertEqual(hole_callout_text(dict(plain, count=1, cbore=None, csk=(12, 90), label=None),
                                           tol=(0.05, 0.02), fit="H7"),
                         "1× %%c6.6 +0.05/-0.02 H7 THRU   ⌵ %%c12 × 90°")
        self.assertEqual(hole_callout_text({"diameter": 5, "depth": 10, "thru": False, "cbore": None, "csk": None,
                                            "thread": "M6x1 - 6H", "count": None}), "M6x1 - 6H ↧10")


class ReleasedCallsTests(unittest.TestCase):
    """Each call an earlier release took still builds: drawn as typed, and the
    report says where the part reads otherwise."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.block, cls.bossed = _block(), _bossed()

    def test_a_hole_callout_typed_whole_prints_as_typed(self) -> None:
        through, blind = (-20, 0, 20), (20, 0, 20)
        for typed, at, printed, reads in (
                # What the part bears out is drawn and says nothing.
                (dict(diameter=6, thru=True), through, "⌀6 THRU", None),
                (dict(diameter=5, depth=12), blind, "⌀5 ↧12", None),
                (dict(diameter=5, depth=10, thread="M6"), blind, "M6 ↧10", None),
                (dict(diameter=5, depth=12, thread="M6x1.0"), blind, "M6x1.0 ↧12", None),
                (dict(diameter=6, depth=10, thread="M6"), blind, "M6 ↧10", None),   # the thread's own size typed
                # What it does not is drawn all the same, and reported with what the part reads.
                (dict(diameter=6), through, "⌀6", "the part's hole there reads ⌀6 THRU"),
                (dict(diameter=6.6, thru=True), through, "⌀6.6 THRU", "the part's hole there reads ⌀6 THRU"),
                (dict(diameter=6, thru=True, cbore=(11, 6.5)), through, "⌀6 THRU   ⌴ ⌀11 ↧6.5",
                 "the part's hole there reads ⌀6 THRU"),
                (dict(diameter=6, thru=True, count=4), through, "4× ⌀6 THRU", "the part's hole there reads ⌀6 THRU"),
                (dict(diameter=6, thru=True, fit="h7"), through, "⌀6 h7 THRU", "fit='h7' is a shaft's tolerance class"),
                (dict(diameter=5, depth=10, thread="M10"), blind, "M10 ↧10", "thread='M10' does not fit the part's "
                                                                              "hole, which reads ⌀5 ↧12"),
                (dict(diameter=5, depth=10, thread="G1/8"), blind, "G1/8 ↧10", "thread='G1/8' is not a thread this "
                                                                                "drawing can check"),
                (dict(diameter=6, thru=True), (0, 0, 20), "⌀6 THRU", "no hole runs along the top view's line of "
                                                                      "sight")):
            with self.subTest(typed=typed):
                diameter = typed.pop("diameter")
                texts, _values, said = _drawn(self.block, lambda top, _f, _r: top.hole(at, diameter, **typed))
                self.assertEqual("".join(texts), _plain(printed))
                if reads is None:
                    self.assertEqual(said, [])
                else:
                    (line,) = said
                    self.assertIn(f"top.hole({at!r}".replace(".0", ""), line.replace(".0", ""), "it names the call")
                    self.assertIn(reads, line)

    def test_a_callout_typed_on_what_is_no_hole_is_drawn(self) -> None:
        """A released example calls out a boss's outside diameter with ``hole()``."""
        texts, _values, said = _drawn(self.bossed,
                                      lambda top, _f, _r: top.hole((0, 0, 20), 16, thru=True, label="BOSS O.D."))
        self.assertEqual(texts, ["16 THRU   BOSS O.D."])
        (line,) = said
        self.assertRegex(line, r"^top\.hole\(\(0, 0, 20\)\) prints ⌀16 THRU   BOSS O\.D\., as typed: no hole runs")

    def test_two_callouts_typed_on_one_hole_are_both_drawn(self) -> None:
        def twice(top, _front, _right):
            top.hole((-20, 0, 20), 6, thru=True, count=1)
            top.hole((-20, 0, 20), 6, thru=True)

        texts, _values, said = _drawn(self.block, twice)
        self.assertEqual(sorted(texts), ["1× ", "6 THRU", "6 THRU"])
        (line,) = said
        self.assertIn("both call out the hole at (-20, 0, 20)", line)

    def test_a_circle_given_its_radius_is_drawn_on_it(self) -> None:
        centre = (0, 0, 20)
        for call, printed in ((lambda top: top.diameter(centre, 8), "16"),
                              (lambda top: top.diameter(centre, radius=8), "16"),
                              (lambda top: top.radius(centre, 8), "R8"),
                              (lambda top: top.diameter(centre, 8, text="%%c16 BOSS"), "16 BOSS")):
            with self.subTest(printed=printed):
                texts, _values, said = _drawn(self.bossed, lambda top, _f, _r: call(top))
                self.assertEqual((texts, said), ([printed], []))
        texts, _values, said = _drawn(self.bossed, lambda top, _f, _r: top.radius(centre, 9))
        self.assertEqual(texts, ["R9"])
        self.assertEqual(said, ["top.radius((0, 0, 20), 9): no arc of radius 9 is centred there in the top view, "
                                "which shows R8. The callout is drawn as typed."])

    def test_a_dimension_is_drawn_wherever_its_points_are(self) -> None:
        _texts, values, said = _drawn(self.block, lambda top, _f, _r: top.dim((-60, 30, 20), (40, 30, 20)))
        self.assertEqual(values, ["100"])
        (line,) = said
        self.assertRegex(line, r"^top dim 0: 1 of 2 point\(s\) fall outside the view's geometry .* It is drawn, but "
                               r"it measures blank paper")

        def stacked(top, _front, _right):
            top.dim((-40, 30, 20), (40, 30, 20), offset=10)
            top.dim((-40, 30, 20), (40, 30, 20), offset=10)

        _texts, values, said = _drawn(self.block, stacked)
        self.assertEqual(values, ["80", "80"])
        (line,) = said
        self.assertIn("annotation overlaps: '80' is printed over '80'", line)

        texts, _values, said = _drawn(self.block, lambda top, _f, _r: top.note("DEBURR", (0, 0, 20)))
        self.assertEqual(said, [])

    def test_a_tolerance_and_a_fit_typed_together_both_print(self) -> None:
        _texts, values, said = _drawn(
            self.block, lambda _t, front, _r: front.dim((-40, -30, 0), (40, -30, 0), offset=-12, tol=(0.05, 0.02),
                                                        fit="h6"))
        (value,) = values
        self.assertTrue("80 h6" in value and "+0.05" in value and "-0.02" in value, value)
        (line,) = said
        self.assertIn("fit='h6' and tol= are two tolerances for one size, and both print", line)

    def test_a_sheet_takes_the_fields_it_took(self) -> None:
        from build123d import Align, Box, Compound, Pos

        _texts, _values, said = _drawn(self.block, lambda *_views: None, general_tolerance="ISO 2768-mK")
        self.assertEqual(said, [])
        _texts, _values, said = _drawn(self.block, lambda *_views: None, units="in")
        (line,) = said
        self.assertIn("units='in': the title block reads IN", line)
        up = (Align.CENTER, Align.CENTER, Align.MIN)
        pair = Compound(children=[Box(30, 30, 10, align=up), Pos(50, 0, 0) * Box(30, 30, 10, align=up)])
        _texts, _values, said = _drawn(pair, lambda *_views: None)
        (line,) = said
        self.assertIn("the part in the top view is 2 separate solids", line)

    def test_a_released_script_writes_its_pdf_and_says_what_the_part_reads(self) -> None:
        """The shape of the drawing script 0.11.13 shipped as its example: a tray on
        four standoffs, its holes and its bosses both called out with ``hole()``,
        every size typed."""
        from build123d import Align, Box, Cylinder, Pos

        from cad.eng_drawing import Sheet, eng_drawing

        up = (Align.CENTER, Align.CENTER, Align.MIN)
        spots = [(x, y) for x in (-25, 25) for y in (-15, 15)]
        tray = Box(70, 50, 18, align=up) - Pos(0, 0, 2) * Box(66, 46, 16, align=up)
        for x, y in spots:
            tray += Pos(x, y, 2) * Cylinder(3.5, 10, align=up)
            tray -= Pos(x, y, 4) * Cylinder(1.5, 8, align=up)

        with temporary_directory(prefix="tmp-cad-eng-drawing-") as folder:
            out = Path(folder) / "tray.pdf"

            @eng_drawing(out=str(out))
            def tray_drawing():
                sheet = Sheet("A3", title="TRAY", part_number="T-001", material="ABS", revision="A",
                              author="text-to-cad", general_tolerance="ISO 2768-m", notes=["BREAK SHARP EDGES."])
                top, front, right = sheet.three_views(tray)
                top.overall()
                top.dim((-25, 25, 0), (25, 25, 0))
                top.dim((35, -15, 0), (35, 15, 0))
                top.hole((25, 15, 9), 3, depth=8, count=len(spots))
                top.hole((25, -15, 9), 7, thru=True, count=len(spots), angle=-45, label="BOSS O.D.")
                front.dim((35, -25, 0), (35, -25, 18))
                front.dim((-35, -25, 0), (-35, -25, 2), offset=-12, text="2 FLOOR")
                right.dim((35, -25, 0), (35, -23, 0), offset=-12, text="2 WALL")
                return sheet

            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                self.assertEqual(tray_drawing(), [out])
            self.assertTrue(out.read_bytes().startswith(b"%PDF"))
        report = said.getvalue()
        self.assertIn("tray_drawing: top.hole((25, -15, 9)) prints 4× ⌀7 THRU   BOSS O.D., as typed: the part's hole "
                      "there reads 4× ⌀3 ↧8.", report)
        self.assertNotIn("top.hole((25, 15, 9))", report, "the callout the part bears out says nothing")
        self.assertNotIn("⌀3 ↧8 is not called out", report.replace("4× ", ""), "and states its four holes")


if __name__ == "__main__":
    unittest.main()
