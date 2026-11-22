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


if __name__ == "__main__":
    unittest.main()
