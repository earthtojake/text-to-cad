"""What is kept of one part's measurement (``cad._internal.dfm.parts``): a part's result found by the part as it
stands and what measured it, written whole, served only as what its name says, never one that could come out
otherwise; and the checks that keep them (sheet, CNC and the recogniser's features), each measuring only the parts
it holds no result of, its report the one it makes of every part measured afresh. Every part is built here, and
every store is a folder of the test's own."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

GEOMETRY = "0123456789abcdef0123456789abcdef"


class KeptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="dfm-parts-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def kept(self, code: str = "c0de") -> object:
        from cad._internal.dfm.parts import Kept

        return Kept(self.root / "parts", code, {"OCP": "7.8.1"})

    def test_a_result_is_found_by_its_part_and_what_measured_it_and_by_nothing_else(self) -> None:
        from cad._internal.dfm.parts import CNC, FEATURES

        kept = self.kept()
        rest = {"part": {"name": "plate", "owner": "plate", "matrix": [1.0] + [0.0] * 15}, "options": {"axes": 3}}
        kept.keep(CNC, GEOMETRY, rest, {"items": [1, 2]})
        self.assertEqual(kept.get(CNC, GEOMETRY, rest), {"items": [1, 2]})
        self.assertEqual(self.kept().get(CNC, GEOMETRY, json.loads(json.dumps(rest))), {"items": [1, 2]},
                         "found again by another process, its rest read back")
        for other in ({**rest, "options": {"axes": 5}}, {**rest, "part": {**rest["part"], "owner": "other"}}):
            self.assertIsNone(kept.get(CNC, GEOMETRY, other))
        self.assertIsNone(kept.get(FEATURES, GEOMETRY, rest), "another kind")
        self.assertIsNone(kept.get(CNC, GEOMETRY[::-1], rest), "another geometry")
        self.assertIsNone(self.kept("other").get(CNC, GEOMETRY, rest), "other code")
        self.assertEqual(kept.counts[CNC], {"reused": 1, "measured": 3, "kept": 1})
        (path,) = (self.root / "parts" / CNC / GEOMETRY[:2]).iterdir()
        self.assertRegex(path.name, rf"^{GEOMETRY}-[0-9a-f]{{20}}\.json$")

    def test_an_entry_that_does_not_read_as_its_name_says_is_removed_and_never_served(self) -> None:
        from cad._internal.dfm.parts import CNC

        kept = self.kept()
        rest = {"part": {"name": "plate"}}
        kept.keep(CNC, GEOMETRY, rest, [1])
        (path,) = (self.root / "parts" / CNC / GEOMETRY[:2]).iterdir()
        entry = json.loads(path.read_text(encoding="utf-8"))
        for broken in (b"{", json.dumps({**entry, "rest": {"part": {"name": "other"}}}).encode(),
                       json.dumps({**entry, "format": 0}).encode()):
            with self.subTest(broken=broken[:20]):
                path.write_bytes(broken)
                self.assertIsNone(kept.get(CNC, GEOMETRY, rest))
                self.assertFalse(path.exists())

    def test_nothing_is_kept_that_could_come_out_otherwise_or_is_no_plain_data(self) -> None:
        from cad._internal.dfm.parts import CNC, Kept, unrepeatable

        kept = self.kept()
        for result in ({"walls": {"error": "x: MemoryError: "}}, [{"recognition": {"repeatable": False}}], {1, 2}):
            with self.subTest(result=result):
                kept.keep(CNC, GEOMETRY, {"n": str(result)}, result)
        self.assertFalse((self.root / "parts").exists())
        self.assertFalse(unrepeatable({"recognition": {"repeatable": True}, "walls": {"error": "x: ValueError: y"}}))
        self.assertEqual(Kept.settled({"a": (1, 2)}), {"a": [1, 2]}, "as it reads back from disk")
        Kept(None, "c0de").keep(CNC, GEOMETRY, {}, [1])  # no folder: nothing, and no error
        blocked = self.root / "blocked"
        blocked.write_text("", encoding="utf-8")
        Kept(blocked / "parts", "c0de").keep(CNC, GEOMETRY, {}, [1])  # a folder that takes no write

    def test_a_process_keeps_its_parts_where_its_code_is_its_own_and_for_sheet_and_cnc_alone(self) -> None:
        from cad._internal.dfm.parts import FOLDER, Kept
        from cad.engine import _measuring

        said = {"code": "c", "dfm": {"cnc": "cnc-code", "sheet": "sheet-code"}, "libraries": {"OCP": "7"}}
        with mock.patch.object(_measuring, "measuring", return_value=said), \
                mock.patch.dict("os.environ", {"CAD_CACHE_DIR": str(self.root)}):
            cnc = Kept.of("cnc")
            self.assertEqual((cnc.folder, cnc.code, cnc.libraries), (self.root / FOLDER, "cnc-code", {"OCP": "7"}))
            self.assertIsNone(Kept.of("molding"))
            self.assertIsNone(Kept.of("printing"))
        edited = {**said, "dfm": {"cnc": "cnc-code" + _measuring.EDITED}}
        with mock.patch.object(_measuring, "measuring", return_value=edited):
            self.assertIsNone(Kept.of("cnc"), "code edited since its process loaded it is no other process's")



def _document(folder: Path, parts: list) -> object:
    """``parts`` (build123d shapes, each labelled) as one STEP's document, read as a check reads it."""
    import build123d as bd

    from cad.build123d import _dfm_brep as brep

    path = folder / f"kit{len(list(folder.glob('*.step')))}.step"
    bd.export_step(bd.Compound(children=parts, label="kit"), str(path))
    return brep.read("step", path)


def _labelled(shape: object, label: str) -> object:
    shape.label = label
    return shape


class FeaturesKeptTest(unittest.TestCase):
    """The recogniser's answer for a part is kept by the part's geometry and how it stands, when the part would
    answer so again: asked once for each, and asked again where the answer was the moment's."""

    def setUp(self) -> None:
        from cad._internal.dfm.parts import Kept

        self.root = Path(tempfile.mkdtemp(prefix="dfm-parts-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.kept = Kept(self.root / "parts", "c0de")
        self.asked: list[list[str]] = []
        self.reason: str | None = None

    def features_of(self, parts: list, **_given: object) -> list:
        from cad.build123d import _dfm_cnc_recognised as recognised
        from cad.quiddity._features import unavailable

        self.asked.append([part.owner for part in parts])
        if self.reason is not None:
            return [unavailable(self.reason, "why, in a line") for _part in parts]
        return [{"available": True, "quiddity": recognised.QUIDDITY, "records": [], "holes": [],
                 "faces": len(part.faces())} for part in parts]

    def ask(self, document: object) -> list:
        from cad import quiddity
        from cad.build123d import _dfm_brep as brep
        from cad.build123d import _dfm_cnc_recognised as recognised

        with mock.patch.object(quiddity, "features_of", self.features_of):
            return recognised.asked(brep.every_occurrence(document).parts, self.kept)  # as the CNC check asks

    def test_a_part_is_asked_once_for_each_way_it_stands(self) -> None:
        import build123d as bd

        block = bd.Box(20, 10, 5) - bd.Cylinder(2, 5)
        first = self.ask(_document(self.root, [_labelled(bd.Pos(0, 0, 0) * block, "a"),
                                               _labelled(bd.Pos(40, 0, 0) * bd.Box(8, 8, 8), "b")]))
        self.assertEqual(self.asked, [["a", "b"]])
        self.assertEqual([found["faces"] for found in first], [7, 6])
        again = self.ask(_document(self.root, [_labelled(bd.Pos(0, 0, 0) * block, "renamed"),
                                               _labelled(bd.Pos(40, 0, 0) * bd.Box(8, 8, 8), "b"),
                                               _labelled(bd.Pos(0, 30, 0) * block, "moved")]))
        self.assertEqual(self.asked[1:], [["kit/moved"]], "features are the geometry's where it stands, whatever "
                                                          "its name: only the one placed otherwise is asked")
        self.assertEqual([again[0], again[2]], first, "the kept answers")
        self.assertEqual(self.kept.counts["features"], {"reused": 2, "measured": 3, "kept": 3})

    def test_an_answer_of_the_moment_is_asked_again_and_one_of_the_part_s_own_is_not(self) -> None:
        import build123d as bd

        document = _document(self.root, [_labelled(bd.Box(20, 10, 5), "a")])
        for reason, kept in (("timed_out", False), ("not_installed", False), ("over_memory", False),
                             ("too_many_faces", True)):
            with self.subTest(reason=reason):
                self.asked.clear()
                self.reason = reason
                said = self.ask(document)
                self.assertEqual((said[0]["reason"], self.asked), (reason, [["a"]]))
                self.reason = None
                self.ask(document)
                self.assertEqual(len(self.asked), 1 if kept else 2)
                if not kept:
                    self.assertEqual(self.ask(document)[0]["available"], True, "the second answer, kept")
                    shutil.rmtree(self.root / "parts")



class _Checked(unittest.TestCase):
    """A process's measurement of documents built here, with a store of the test's own and without one."""

    process = ""

    def setUp(self) -> None:
        from cad._internal.dfm.parts import Kept

        self.root = Path(tempfile.mkdtemp(prefix="dfm-parts-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.kept = Kept(self.root / "parts", "c0de")

    def measure(self, document: object, kept: object = None) -> str:
        """The report as JSON text, as a check answers it: measured with ``kept`` (this test's store), or with no
        store at all."""
        from cad._internal import manufacturing
        from cad._internal.dfm import kept as measures
        from cad.build123d import _dfm_check

        options = measures.Measuring(self.process, manufacturing.options("step", self.process, {}))
        report = _dfm_check._measured(document, "step", self.process, options, False, kept)
        return json.dumps(report, sort_keys=True)

    def measured(self, document: object) -> int:
        """How many of ``document``'s parts its check measured with this test's store (the rest found kept), its
        report checked against the one measured with none."""
        from cad._internal.dfm.parts import PROCESSES

        counts = self.kept.counts[PROCESSES[self.process]]
        before = counts["measured"]
        self.assertEqual(self.measure(document, self.kept), self.measure(document), "the report of every part "
                                                                                     "measured afresh")
        return counts["measured"] - before


def _plate(width: float, holes: int = 1) -> object:
    import build123d as bd

    plate = bd.Box(width, 30, 2)
    for n in range(holes):
        plate -= bd.Pos(-width / 2 + 8 + 10 * n, 0, 0) * bd.Cylinder(2.5, 2)
    return plate


class SheetKeptTest(_Checked):
    process = "sheet"

    def kit(self, *widths: float, **named: float) -> list:
        import build123d as bd

        parts = [_labelled(bd.Pos(0, 50 * n, 0) * _plate(width, 2), f"p{n}") for n, width in enumerate(widths)]
        return parts + [_labelled(bd.Pos(200, 0, 0) * _plate(width), name) for name, width in named.items()]

    def test_a_document_one_part_of_which_changed_measures_that_part_alone(self) -> None:
        self.assertEqual(self.measured(_document(self.root, self.kit(40, 50, 60, 70))), 4)
        self.assertEqual(self.measured(_document(self.root, self.kit(40, 50, 61, 70))), 1, "the one edited")
        self.assertEqual(self.measured(_document(self.root, self.kit(40, 50, 61, 70))), 0)

    def test_a_part_is_its_own_entry_by_how_it_stands_its_name_and_its_owner(self) -> None:
        import build123d as bd

        self.assertEqual(self.measured(_document(self.root, self.kit(40, a=50))), 2)
        self.assertEqual(self.measured(_document(self.root, self.kit(45, a=50))), 1, "the same part in another "
                                                                                     "document: the same entry")
        self.assertEqual(self.measured(_document(self.root, self.kit(40, b=50))), 1, "renamed")
        moved = [_labelled(bd.Pos(0, 0, 0) * _plate(40, 2), "p0"), _labelled(bd.Pos(210, 0, 0) * _plate(50), "a")]
        self.assertEqual(self.measured(_document(self.root, moved)), 1, "placed otherwise")
        owned = [_labelled(bd.Pos(0, 0, 0) * _plate(40, 2), "p0"),
                 bd.Compound(children=[_labelled(bd.Pos(200, 0, 0) * _plate(50), "a")], label="left"),
                 bd.Compound(children=[_labelled(bd.Pos(200, 100, 0) * _plate(55), "a")], label="right")]
        document = _document(self.root, owned)
        self.assertEqual([part.owner for part in document.parts], ["p0", "kit/left/a", "kit/right/a"])
        self.assertEqual(self.measured(document), 2, "a, the same part standing the same way, under another owner")

    def test_a_check_stopped_after_some_parts_measures_the_rest_alone_the_next_time(self) -> None:
        from cad.build123d import _dfm_sheet

        class Stopped(BaseException):
            """A check stopped at its limits: its process killed, nothing after it runs."""

        real, done = _dfm_sheet._part, []

        def stopping(part: object, options: object) -> object:
            if len(done) == 2:
                raise Stopped()
            done.append(part)
            return real(part, options)

        document = _document(self.root, self.kit(40, 50, 60, 70))
        with mock.patch.object(_dfm_sheet, "_part", stopping), self.assertRaises(Stopped):
            self.measure(document, self.kept)
        self.assertEqual(self.measured(document), 2, "the two not finished")

    def test_a_part_result_that_could_come_out_otherwise_is_never_kept(self) -> None:
        from cad.build123d import _dfm_sheet

        document = _document(self.root, self.kit(40, 50))
        with mock.patch.object(_dfm_sheet, "_holes", side_effect=MemoryError()):
            said = json.loads(self.measure(document, self.kept))
        self.assertEqual(said["holes"], {"error": "p0: MemoryError: "})
        self.assertEqual(self.kept.counts["dfm-sheet"]["kept"], 0)
        self.assertEqual(self.measured(document), 2)


if __name__ == "__main__":
    unittest.main()
