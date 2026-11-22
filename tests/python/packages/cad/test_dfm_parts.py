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

    def test_a_part_is_found_by_the_version_of_a_report_s_shape_too(self) -> None:
        from cad._internal.dfm import kept as measures
        from cad._internal.dfm.parts import CNC

        kept = self.kept()
        kept.keep(CNC, GEOMETRY, {"part": "p"}, [1])
        with mock.patch.object(measures, "MEASURE_VERSION", measures.MEASURE_VERSION + 1):
            self.assertIsNone(kept.get(CNC, GEOMETRY, {"part": "p"}), "a report's shape changed by hand")
        self.assertEqual(kept.get(CNC, GEOMETRY, {"part": "p"}), [1])

    def test_nothing_is_kept_by_code_edited_on_disk_since_its_process_read_its_digest(self) -> None:
        from cad._internal.dfm.parts import CNC, Kept
        from cad.engine import _measuring

        kept = Kept(self.root / "parts", "cnc-code", process="cnc")
        with mock.patch.object(_measuring, "current", return_value="cnc-code-edited"):
            kept.keep(CNC, GEOMETRY, {}, [1])
        self.assertIsNone(kept.get(CNC, GEOMETRY, {}))
        with mock.patch.object(_measuring, "current", return_value="cnc-code"):
            kept.keep(CNC, GEOMETRY, {}, [1])
        self.assertEqual(kept.get(CNC, GEOMETRY, {}), [1])

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
        return [{"available": True, "quiddity": recognised.QUIDDITY, "records": [], "holes": [], "accounting": [],
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

    def test_a_kept_result_no_report_can_be_made_of_is_removed_and_its_part_measured_afresh(self) -> None:
        document = _document(self.root, self.kit(40, 50))
        fresh = self.measure(document)
        self.measure(document, self.kept)
        entries = sorted((self.root / "parts" / "dfm-sheet").rglob("*.json"))
        for broken in (lambda result: result.update(holes="none"), lambda result: result.update(parts=[]),
                       lambda result: result.update(_failed=[["a", 1]]), lambda result: result.update(other=1)):
            with self.subTest(broken=broken):
                entry = json.loads(entries[0].read_text(encoding="utf-8"))
                broken(entry["result"])
                entries[0].write_text(json.dumps(entry), encoding="utf-8")
                self.assertEqual(self.measure(document, self.kept), fresh)
                self.assertEqual(self.measure(document, self.kept), fresh, "measured afresh and kept again")

    def test_a_part_result_that_could_come_out_otherwise_is_never_kept(self) -> None:
        from cad.build123d import _dfm_sheet

        document = _document(self.root, self.kit(40, 50))
        with mock.patch.object(_dfm_sheet, "_holes", side_effect=MemoryError()):
            said = json.loads(self.measure(document, self.kept))
        self.assertEqual(said["holes"], {"error": "p0: MemoryError: "})
        self.assertEqual(self.kept.counts["dfm-sheet"]["kept"], 0)
        self.assertEqual(self.measured(document), 2)



def _block(width: float, holes: int = 1) -> object:
    """A machined block, its holes drilled from the top and a pocket milled beside them."""
    import build123d as bd

    block = bd.Box(width, 30, 12) - bd.Pos(width / 2 - 8, 0, 3) * bd.Box(10, 14, 6)
    for n in range(holes):
        block -= bd.Pos(-width / 2 + 6 + 8 * n, 0, 0) * bd.Cylinder(2, 12)
    return block


class CncKeptTest(_Checked):
    process = "cnc"

    def setUp(self) -> None:
        from cad import quiddity
        from cad.quiddity._features import unavailable

        super().setUp()
        self.reason = "no_wheel"  # a reason of the platform's own, which the next check meets again
        patched = mock.patch.object(quiddity, "features_of", lambda parts, **_given: [
            unavailable(self.reason, "why, in a line") for _part in parts])
        patched.start()
        self.addCleanup(patched.stop)

    def kit(self, *widths: float, turned: bool = False) -> list:
        import build123d as bd

        parts = [_labelled(bd.Pos(0, 50 * n, 0) * _block(width, 2), f"b{n}") for n, width in enumerate(widths)]
        if turned:  # copies of the first, turned a right angle and 37 degrees: measured once, said where each stands
            parts.append(_labelled(bd.Pos(0, -60, 0) * bd.Rot(0, 0, 90) * _block(widths[0], 2), "turned"))
            parts.append(_labelled(bd.Pos(100, -60, 0) * bd.Rot(0, 0, 37) * _block(widths[0], 2), "leaning"))
            # and its mirror image, which is no copy: a part of its own
            parts.append(_labelled(bd.Pos(200, -60, 0) * bd.mirror(_block(widths[0], 2), bd.Plane.YZ), "mirrored"))
        return parts

    def test_a_document_one_part_of_which_changed_measures_that_part_alone(self) -> None:
        self.assertEqual(self.measured(_document(self.root, self.kit(40, 50, 60, turned=True))), 4,
                         "the turned copies are their first's, measured once; the mirror image is its own")
        self.assertEqual(self.measured(_document(self.root, self.kit(40, 50, 61, turned=True))), 1, "the one edited")
        self.assertEqual(self.measured(_document(self.root, self.kit(40, 50, 61, turned=True))), 0)

    def test_a_part_is_found_in_a_document_of_other_neighbours(self) -> None:
        import build123d as bd

        parts = self.kit(40, 50)
        self.assertEqual(self.measured(_document(self.root, parts)), 2)
        other = [parts[0], _labelled(bd.Pos(0, 50, 0) * _block(70, 3), "b1")]
        self.assertEqual(self.measured(_document(self.root, other)), 1, "b0 found beside another b1")

    def test_a_report_from_kept_results_is_the_one_made_with_the_recogniser_there(self) -> None:
        """A part's answer is kept only where it would be given again, so a report served from what was kept
        while quiddity answered is that report still while it cannot be reached."""
        from cad import quiddity
        from cad.build123d import _dfm_cnc_recognised as recognised

        def available(parts: list, **_given: object) -> list:
            return [{"available": True, "quiddity": recognised.QUIDDITY, "records": [], "holes": [],
                     "accounting": []} for _part in parts]

        document = _document(self.root, self.kit(40, 50))
        with mock.patch.object(quiddity, "features_of", available):
            there = self.measure(document, self.kept)
            self.assertEqual(there, self.measure(document))
        self.reason = "not_installed"
        self.assertEqual(self.measure(document, self.kept), there, "served as quiddity read it")
        self.assertFalse(json.loads(self.measure(document))["holes"]["recognition"]["repeatable"],
                         "while a fresh measurement now falls back")

    def test_what_a_failure_for_want_of_memory_touched_is_kept_nowhere(self) -> None:
        """Out of memory where the measurement goes on -- quiddity's part written, an exact wall refined -- is
        no reading of the part's own: answered as measured, and kept neither per part nor whole."""
        from cad.build123d import _dfm_check, _dfm_cnc
        from cad.engine.export import step

        from cad import quiddity
        from cad.quiddity import _features

        document = _document(self.root, self.kit(40, 50))
        # the integration's own reading of each part, its STEP written by a kernel out of memory: quiddity is never
        # reached, so no recogniser runs
        with mock.patch.object(step, "shape_bytes", side_effect=MemoryError()), \
                mock.patch.object(quiddity, "features_of", lambda parts, **_given: _features.features_of(parts, 30.0)):
            said = json.loads(self.measure(document, self.kept))
        recognition = said["holes"]["recognition"]
        self.assertEqual({entry["reason"] for entry in recognition["fallbacks"]}, {"out_of_memory"})
        self.assertFalse(recognition["repeatable"])
        self.assertFalse((self.root / "parts").exists(), "no part's features nor result kept")
        with mock.patch.object(_dfm_cnc, "_refine", side_effect=MemoryError()):
            failing = self.measure(document, self.kept)
            self.assertEqual(failing, self.measure(document), "the sampled figures, as with no store")
            self.assertTrue(_dfm_check._transient("cnc", json.loads(failing)), "and the report kept by no one")
        with mock.patch.object(_dfm_cnc, "_refine", side_effect=_dfm_cnc._refine) as refine:
            self.assertEqual(self.measure(document, self.kept), self.measure(document))
        self.assertGreater(refine.call_count, 0, "the refinements not kept, so made again")

    def test_a_kept_result_no_report_can_be_made_of_is_removed_and_its_part_measured_afresh(self) -> None:
        document = _document(self.root, self.kit(40, 50))
        fresh = self.measure(document)
        self.measure(document, self.kept)
        entries = sorted((self.root / "parts" / "dfm-cnc").rglob("*.json"))
        for broken in (lambda result: result.pop("frame"),
                       lambda result: result["families"].update(walls=[{"thickness_mm": "thin"}]),
                       lambda result: result["families"].update(holes=[{"recognised_by": "nobody"}]),
                       lambda result: result.update(missed=[["a", 1]])):
            with self.subTest(broken=broken):
                entry = json.loads(entries[0].read_text(encoding="utf-8"))
                broken(entry["result"])
                entries[0].write_text(json.dumps(entry), encoding="utf-8")
                self.assertEqual(self.measure(document, self.kept), fresh)
                self.assertEqual(self.measure(document, self.kept), fresh, "measured afresh and kept again")

    def test_a_check_stopped_after_some_parts_measures_the_rest_alone_the_next_time(self) -> None:
        from cad.build123d import _dfm_cnc

        class Stopped(BaseException):
            """A check stopped at its limits: its process killed, nothing after it runs."""

        real, done = _dfm_cnc._part_result, []

        def stopping(*given: object) -> object:
            if len(done) == 2:
                raise Stopped()
            done.append(given)
            return real(*given)

        document = _document(self.root, self.kit(40, 50, 60))
        with mock.patch.object(_dfm_cnc, "_part_result", stopping), self.assertRaises(Stopped):
            self.measure(document, self.kept)
        self.assertEqual(self.measured(document), 1, "the one not finished")

    def test_a_part_result_that_could_come_out_otherwise_is_never_kept(self) -> None:
        from cad.build123d import _dfm_cnc

        document = _document(self.root, self.kit(40, 50))
        with mock.patch.object(_dfm_cnc, "_walls", side_effect=MemoryError()):
            said = json.loads(self.measure(document, self.kept))
        self.assertEqual(said["walls"], {"error": "b0: MemoryError: "})
        shutil.rmtree(self.root / "parts" / "features")  # each part's features asked again
        self.reason = "timed_out"  # quiddity out of time on the part: the moment's
        said = json.loads(self.measure(document, self.kept))
        self.assertFalse(said["holes"]["recognition"]["repeatable"])
        self.assertEqual(len(list((self.root / "parts" / "dfm-cnc").rglob("*.json"))), 1,
                         "b1, measured after b0's walls failed, alone")
        self.reason = "no_wheel"
        self.assertEqual(self.measured(document), 2)

    def test_a_part_measured_after_a_family_failed_is_kept_as_measured_so(self) -> None:
        """A family that failed on a part is not measured on the parts after it, which are measured, and kept,
        so: a part is found by the families failed before it too."""
        from cad.build123d import _dfm_cnc

        real = _dfm_cnc._knife_edges

        def first_fails(model: object, state: object) -> object:
            if model.part.name == "b0":
                raise ValueError("the kernel gave up")
            return real(model, state)

        parts = self.kit(40, 50)
        with mock.patch.object(_dfm_cnc, "_knife_edges", first_fails):
            self.assertEqual(self.measured(_document(self.root, parts)), 2)
            report = json.loads(self.measure(_document(self.root, parts), self.kept))
            self.assertEqual(report["knife_edges"], {"error": "b0: ValueError: the kernel gave up"})
            self.assertEqual(self.measured(_document(self.root, parts)), 0, "each found, b1 as measured after b0")
            self.assertEqual(self.measured(_document(self.root, parts[::-1])), 1,
                             "b1 measured again where no family failed before it; b0 found")

if __name__ == "__main__":
    unittest.main()
