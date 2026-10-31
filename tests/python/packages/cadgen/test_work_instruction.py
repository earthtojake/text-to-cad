"""``@work_instruction``: the steps to build one assembly, as a PDF.

The assembly is three boxes built here -- a base plate, a bracket on it and two
pins of one label on the bracket -- handed to the engine, so every part ref and face
is known from the construction. Most tests write with ``pictures=False``, which
reads the document's shape in this process; one draws the pictures through the
engine's snapshot, because the hidden parts and the marks are resolved there
and nowhere else.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support import engine_daemon, opengl
from tests.python.support.paths import add_repo_path, repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")


_FIXTURE: dict[str, Path] = {}
REFERENCE = repo_path("skills/work-instructions/references/instruction-api.md")
SKILL = repo_path("skills/work-instructions/SKILL.md")
# The model the skill's template calls, with the part names it installs.
ASSEMBLY_MODEL = """
import build123d as bd
from cadgen import model


@model
def bracket_assembly():
    parts = []
    for label, z, size in (("base_plate", 0, 10), ("bracket", 25, 40), ("pin", 50, 4)):
        part = bd.Pos(0, 0, z) * bd.Box(size * 2, size, size)
        part.label = label
        parts.append(part)
    return bd.Compound(children=parts, label="bracket_assembly")
"""


def setUpModule() -> None:
    """One assembly document for every test here, held by an engine of the module's own
    (``engine_daemon.isolate``)."""
    from build123d import Box, Compound, Pos
    from cadgen import model

    engine_daemon.isolate(unittest.addModuleCleanup)
    temporary = generated_cad_directory(prefix="work-instruction-")
    unittest.addModuleCleanup(temporary.cleanup)
    root = Path(temporary.name)
    base = Box(100, 60, 10)
    base.label = "base_plate"
    bracket = Pos(0, 0, 25) * Box(40, 40, 40)
    bracket.label = "bracket"
    pins = []
    for x in (-10, 10):
        pin = Pos(x, 0, 50) * Box(4, 4, 10)
        pin.label = "pin"
        pins.append(pin)
    document = model(Compound(children=[base, bracket, *pins], label="assembly"), name="assembly")
    _FIXTURE.update(root=root, document=document)


class _Assembly(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root, cls.document = _FIXTURE["root"], _FIXTURE["document"]

    def instruction(self, **kwargs):
        from cadgen.work_instruction import Instruction

        kwargs.setdefault("pictures", False)
        return Instruction(self.document, title="BRACKET ASSEMBLY", number="WI-1", revision="A", **kwargs)


def _sources():
    from cadgen.work_instruction import Drawing, Spec

    return Spec("PS-2001", "Threaded fastener installation", revision="D"), Drawing("DWG-1", revision="B")


class _Page:
    """A matplotlib axes that keeps the text drawn on it and draws nothing."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def text(self, _x, _y, value, **_kwargs) -> None:
        self.texts.append(value)

    def plot(self, *_args, **_kwargs) -> None:
        pass

    add_patch = imshow = plot


def _page_texts(wi) -> list[list[str]]:
    """Each page's text, laid out as the PDF is (no pictures)."""
    from cadgen._internal.work_instruction_pages import draw_page, layout

    items = wi.open_items()
    flow = layout(wi, items, {})
    pages = []
    for index in range(1, len(flow.pages) + 1):
        page = _Page()
        draw_page(page, flow, index, len(items))
        pages.append(page.texts)
    return pages


class SourceTests(unittest.TestCase):
    def test_every_process_value_names_where_it_comes_from(self) -> None:
        from cadgen.work_instruction import Adhesive, Cure, Material, Torque

        for make in (lambda: Torque(20, 25, unit="in-lbf"), lambda: Adhesive("EA 9394", mix="100:17"),
                     lambda: Cure("cure", cycle="1 h at 150 F"), lambda: Material("Loctite 242")):
            with self.subTest(make=make), self.assertRaisesRegex(TypeError, r"Spec\(\.\.\.\)\.at"):
                make()

    def test_a_source_names_a_known_kind_a_document_and_where_in_it(self) -> None:
        from cadgen.work_instruction import Source

        for kind, document, where in (("bogus", "X", "y"), ("stated", "", ""), ("spec", "PS-1 Rev A", "")):
            with self.subTest(kind=kind, document=document), self.assertRaises((ValueError, TypeError)):
                Source(kind, document, where)

    def test_a_field_from_a_second_document_cites_that_document(self) -> None:
        from cadgen.work_instruction import Adhesive, Cited, Datasheet

        spec, _ = _sources()
        tds = Datasheet("EA 9394", revision="2019-05")
        adhesive = Adhesive("EA 9394", prep="IPA wipe", mix=Cited("100:17", per=tds.at("Mixing")),
                            per=spec.at("5.1"))
        cites = {caption: source.cite() if source else None for caption, _text, source in adhesive.fields()}
        self.assertEqual(cites, {"prep": "PS-2001 Rev D \u00a75.1", "mix": "EA 9394 datasheet, 2019-05, Mixing",
                                 "pot life": None, "cure": None})
        self.assertEqual(adhesive.missing(), ["pot life", "cure"])

    def test_a_torque_prints_the_numbers_given(self) -> None:
        from cadgen.work_instruction import Torque

        spec, _ = _sources()
        self.assertEqual(Torque(12.345678, unit="N-m", per=spec.at("4")).text(), "12.345678 N-m")
        self.assertEqual(Torque(40.0, 45, unit="in-lbf", per=spec.at("4")).text(), "40\u201345 in-lbf")

    def test_a_torque_s_unit_is_named_never_read_from_where_the_high_end_goes(self) -> None:
        from cadgen.work_instruction import Torque

        spec, _ = _sources()
        with self.assertRaisesRegex(TypeError, r"Torque\(30, unit='N-m'\)"):
            Torque(30, "N-m", per=spec.at("4"))
        with self.assertRaises(TypeError):
            Torque(20, 25, "in-lbf", per=spec.at("4"))

    def test_a_citation_says_which_document_and_where(self) -> None:
        from cadgen.work_instruction import Stated

        spec, drawing = _sources()
        self.assertEqual(spec.at("4.2, Table 3").cite(), "PS-2001 Rev D §4.2, Table 3")
        self.assertEqual(drawing.at("note 4").cite(), "DWG-1 Rev B, note 4 (drawing callout)")
        self.assertEqual(Stated("A. Zhou", on="2026-10-23").cite(), "stated by A. Zhou, 2026-10-23")


class VocabularyTests(_Assembly):
    def test_closed_sets_refuse_what_they_do_not_name(self) -> None:
        from cadgen.work_instruction import Instruction, Torque

        spec, _ = _sources()
        cases = [
            (ValueError, lambda: Torque(20, unit="Nm", per=spec.at("4"))),
            (ValueError, lambda: Torque(30, 20, unit="in-lbf", per=spec.at("4"))),
            (ValueError, lambda: Torque(0, unit="in-lbf", per=spec.at("4"))),
            (ValueError, lambda: self.instruction(status="approved")),
            (ValueError, lambda: self.instruction(camera="isometric")),
            (ValueError, lambda: self.instruction(size="A3")),
            (ValueError, lambda: Instruction(self.document, title="  ", number="WI-1", revision="A", pictures=False)),
            (TypeError, lambda: self.instruction().step("Load", install="base_plate")),
            (ValueError, lambda: self.instruction().step("Load", install=["base_plate"]).bond(None, surfaces=["base_plate"])),
        ]
        for error, make in cases:
            with self.subTest(make=make), self.assertRaises(error):
                make()

    def test_a_single_part_is_not_an_assembly(self) -> None:
        """A file's document is read in this process, as a model's handle is."""
        from build123d import Box, export_step
        from cadgen.work_instruction import Instruction

        single = self.root / "single.step"
        export_step(Box(1, 1, 1), single)
        with self.assertRaisesRegex(TypeError, "single part"):
            Instruction(single, title="T", number="N", revision="A", pictures=False)


class PartTests(_Assembly):
    def test_a_label_installs_every_part_that_carries_it(self) -> None:
        wi = self.instruction()
        self.assertEqual(wi.step("Pins", install=["pin"]).install, ("assembly/pin.1", "assembly/pin.2"))

    def test_a_surface_is_resolved_to_one_face_when_the_step_names_it(self) -> None:
        step = self.instruction().step("Load", install=["bracket"])
        self.assertEqual(step.bond(None, surfaces=["bracket/face 5"]).ops[-1].surfaces, (("bracket/face 5", "bracket"),))
        with self.assertRaisesRegex(ValueError, "face refs"):
            step.bond(None, surfaces=["bracket"])
        with self.assertRaisesRegex(ValueError, "is not one face of assembly"):
            step.bond(None, surfaces=["bolt/face 1"])

    def test_an_unknown_part_is_refused_with_the_parts_there_are(self) -> None:
        with self.assertRaisesRegex(KeyError, r"its parts are: base_plate, bracket"):
            self.instruction().step("Load", install=["brackett"])

    def test_a_refused_step_leaves_its_parts_for_the_next(self) -> None:
        wi = self.instruction()
        with self.assertRaises(ValueError):
            wi.step("Load", install=["base_plate"], camera="isometric")
        self.assertEqual(wi.step("Load", install=["base_plate"]).install, ("base_plate",))

    def test_a_part_is_installed_by_one_step(self) -> None:
        wi = self.instruction()
        wi.step("Load", install=["base_plate"])
        with self.assertRaisesRegex(ValueError, "step 1 already installs"):
            wi.step("Again", install=["base_plate"])


class OpenItemTests(_Assembly):
    def _wi(self, **kwargs):
        from cadgen.work_instruction import Adhesive, Torque

        spec, drawing = _sources()
        kwargs.setdefault("rigor", "controlled")
        wi = self.instruction(**kwargs)
        wi.step("Load", install=["base_plate"])
        wi.step("Bond", install=["bracket"]).bond(
            Adhesive("EA 9394", prep="IPA wipe", mix="100:17", cure="5 days at 77 F", per=spec.at("5.1")))
        wi.step("Pins", install=["assembly/pin.1"]).fasten("NAS1352-3", qty=1,
                                                  torque=Torque(40, 45, unit="in-lbf", per=drawing.at("note 4")))
        return wi

    def test_every_value_nobody_stated_and_every_part_no_step_installs_is_listed(self) -> None:
        wi = self._wi()
        wi.steps[-1].fasten("MS21042-3 nut").inspect("Pin seated")
        self.assertEqual(wi.open_items(), [
            "step 2 (bond): pot life not stated",
            "step 3 (fasten): torque not stated",
            "step 3 (inspect): criterion source not stated",
            "assembly/pin.2: no step installs it",
        ])

    def test_a_released_instruction_with_open_items_is_refused_and_writes_nothing(self) -> None:
        from cadgen.work_instruction import work_instruction

        target = self.root / "refused.pdf"
        earlier = b"%PDF an earlier, released instruction"
        target.write_bytes(earlier)

        @work_instruction(out=str(target))
        def released():
            return self._wi(status="released")

        with self.assertRaisesRegex(ValueError, "released with 2 open item"):
            released()
        self.assertEqual(earlier, target.read_bytes(), "a refused run leaves the earlier file byte for byte")
        self.assertEqual([target], sorted(self.root.glob("*refused.pdf*")), "and no partial file beside it")

    def test_every_blank_prints_not_stated_and_a_draft_says_so_on_every_page(self) -> None:
        wi = self._wi()
        wi.steps[-1].inspect("Pin seated")
        pages = _page_texts(wi)
        self.assertEqual(sum(page.count("NOT STATED") for page in pages), 2, "pot life, the inspection's source")
        self.assertTrue(all(any(text.startswith("DRAFT") for text in page) for page in pages))

    def test_a_block_taller_than_a_page_is_refused_naming_its_step(self) -> None:
        wi = self.instruction()
        wi.step("Load", install=["base_plate"]).instruct("word " * 6000)
        with self.assertRaisesRegex(ValueError, "step 1 is taller than a page"):
            _page_texts(wi)


class DocumentTests(_Assembly):
    def _write(self, name: str, wi_factory):
        from cadgen.work_instruction import work_instruction

        target = self.root / name

        @work_instruction(out=str(target))
        def wi():
            return wi_factory()

        self.assertEqual(wi(), [target])
        return target.read_bytes()

    def _complete(self, **kwargs):
        wi = self.instruction(**kwargs)
        wi.step("Load", install=["base_plate"]).instruct("Datum A down.")
        wi.step("Fit", install=["bracket", "pin"]).inspect("Pins seated", per=_sources()[1].at("note 2"))
        return wi

    def test_a_draft_writes_deterministically(self) -> None:
        first = self._write("a.pdf", self._complete)
        second = self._write("b.pdf", self._complete)
        self.assertEqual(first, second, "no clock reaches the bytes")
        self.assertNotIn(b"/CreationDate", first)

    def test_front_pages_then_a_procedure_table_with_hold_points_and_a_close_out(self) -> None:
        wi = self.instruction(safety=["Safety glasses"], tools=["Fixture F-12"], rigor="controlled")
        wi.operation("Load")
        wi.step("Load", install=["base_plate"]).caution("Lift with two people.")
        wi.operation("Fit")
        wi.step("Fit", install=["bracket", "pin"]).inspect("Pins seated", per=_sources()[1].at("note 2"),
                                                           record="Pin height, mm")
        text = [t for page in _page_texts(wi) for t in page]
        order = [text.index(t) for t in ("APPLICABLE DOCUMENTS", "SAFETY", "PARTS", "EQUIPMENT", "OPERATIONS",
                                         "APPROVALS", "PROCEDURE", "OPERATION 1   Load", "CAUTION", "Close-out")]
        self.assertEqual(order, sorted(order), "front pages, then the procedure in order")
        self.assertIn("Fixture F-12", text)
        self.assertIn("PIN HEIGHT, MM", text, "the measured value has a blank")
        self.assertEqual(text.count("HOLD"), 2, "the inspection and the close-out")

    def test_released_with_nothing_open_writes_with_no_draft_banner(self) -> None:
        self.assertTrue(self._write("released.pdf", lambda: self._complete(status="released")).startswith(b"%PDF"))
        pages = _page_texts(self._complete(status="released"))
        self.assertFalse([text for page in pages for text in page if "DRAFT" in text or "NOT STATED" in text])

    def test_an_instruction_written_is_counted_and_one_refused_is_not(self) -> None:
        """Counted as a drawing is: kept with a command's counts, since the script sends nothing."""
        from unittest import mock

        from cadgen import analytics

        with mock.patch.object(analytics, "hand_over") as handed:
            self._write("counted.pdf", self._complete)
        handed.assert_called_once_with({"features": ["work_instruction"]})
        self.assertIn("work_instruction", analytics.FEATURES)
        with mock.patch.object(analytics, "hand_over") as handed, self.assertRaises(ValueError):
            self._write("refused.pdf", lambda: self.instruction(status="released"))
        handed.assert_not_called()
        with mock.patch.object(analytics, "hand_over", side_effect=RuntimeError("broken")):
            self._write("uncounted.pdf", self._complete)  # a count never fails what it counts
        with self.assertRaisesRegex(ValueError, "'instruction' is not a feature"):
            analytics.counted(lambda: None, "instruction")  # a closed set, as the receiver's is

    def test_the_output_path_is_required_and_names_a_pdf(self) -> None:
        from cadgen.work_instruction import work_instruction

        with self.assertRaisesRegex(ValueError, "needs out="):
            work_instruction(lambda: None)
        with self.assertRaisesRegex(ValueError, "must name a .pdf"):
            work_instruction(out="wi.docx")(lambda: None)
        with self.assertRaisesRegex(TypeError, "must return an Instruction"):
            work_instruction(out=str(self.root / "x.pdf"))(lambda: "steps")()


class LayoutTests(_Assembly):
    """What a rigor lays out, what a process emphasis changes, and a house format."""

    def _texts(self, **kwargs) -> list[str]:
        wi = self.instruction(**kwargs)
        wi.step("Load", install=["base_plate"])
        wi.step("Fit", install=["bracket", "pin"]).inspect("Pins seated")
        return [t for page in _page_texts(wi) for t in page]

    def test_each_rigor_lays_out_what_it_names(self) -> None:
        prototype = self._texts(rigor="prototype")
        self.assertIn("DONE", prototype)
        for absent in ("WORK ORDER", "APPROVALS", "Close-out", "TECH", "QA", "HOLD"):
            self.assertNotIn(absent, prototype, absent)
        production = self._texts()
        for present in ("WORK ORDER", "TECH", "APPROVALS", "Close-out"):
            self.assertIn(present, production, present)
        for absent in ("QA", "HOLD", "NOT STATED"):
            self.assertNotIn(absent, production, f"{absent}: an uncited inspection is fine outside controlled work")
        controlled = self._texts(rigor="controlled")
        self.assertEqual(controlled.count("HOLD"), 2, "the inspection and the close-out")
        self.assertIn("NOT STATED", controlled, "a controlled inspection cites its criterion")

    def test_a_process_emphasis_drops_the_figures_and_maps_documents_to_steps(self) -> None:
        from cadgen.work_instruction import Adhesive

        spec, _ = _sources()
        wi = self.instruction(emphasis="process", pictures=True)
        self.assertFalse(wi.pictures)
        wi.step("Load", install=["base_plate"])
        wi.step("Bond", install=["bracket"]).bond(Adhesive("A", prep="p", mix="m", pot_life="l", cure="c",
                                                           per=spec.at("5.1")))
        text = [t for page in _page_texts(wi) for t in page]
        self.assertNotIn("FIGURE", text)
        self.assertIn("PROCESS REFERENCES", text)
        self.assertEqual(wi.references(), [("PS-2001 Rev D", "\u00a75.1", ["2"])])

    def test_a_house_format_overrides_only_what_it_states(self) -> None:
        from cadgen.work_instruction import Format

        house = Format(title="ASSEMBLY PROCEDURE", company="Acme", step_label="OP", numbering="by-ten",
                       stamps=("MECH", "INSP"), approvals=("Written by", "Quality"))
        wi = self.instruction(rigor="controlled", format=house)
        wi.step("Load", install=["base_plate"])
        wi.step("Fit", install=["bracket", "pin"]).inspect("Pins seated")
        self.assertEqual([step.label for step in wi.steps], ["10", "20"])
        self.assertEqual(wi.open_items(), ["step 20 (inspect): criterion source not stated"])
        text = [t for page in _page_texts(wi) for t in page]
        for present in ("ASSEMBLY PROCEDURE", "OP", "MECH", "INSP", "WRITTEN BY", "QUALITY", "10", "20"):
            self.assertIn(present, text, present)
        self.assertNotIn("TECH", text)
        self.assertEqual(text.count("HOLD"), 2, "controlled still holds, in the house's last column")

    def test_a_format_is_a_closed_set(self) -> None:
        from cadgen.work_instruction import Format

        for make in (lambda: Format(numbering="by-five"), lambda: Format(stamps=()), lambda: Format(stamps="QA"),
                     lambda: Format(logo="acme.png"), lambda: self.instruction(rigor="aerospace"),
                     lambda: self.instruction(emphasis="photos"), lambda: self.instruction(format={"stamps": ["QA"]})):
            with self.subTest(make=make), self.assertRaises((ValueError, TypeError)):
                make()


class WhatTheTestsFoundTests(_Assembly):
    """What agents using the skill on real assemblies tripped over."""

    def test_no_value_is_not_an_open_item_and_needs_no_wrench(self) -> None:
        from cadgen.work_instruction import Stated, Unspecified

        wi = self.instruction()
        wi.step("Bolt", install=["base_plate"]).fasten(
            "M8 bolt", qty=4, torque=Unspecified("Snug; no torque is specified",
                                                 per=Stated("A. Zhou", on="2026-10-25")))
        self.assertEqual(wi.open_items()[:1], ["bracket: no step installs it"])
        self.assertEqual(wi.equipment(), [])
        text = [t for page in _page_texts(wi) for t in page]
        self.assertIn("stated by A. Zhou, 2026-10-25", text, "a statement prints as one, never 'per stated by'")
        self.assertFalse([t for t in text if t.startswith("ACTUAL TORQUE")])

    def test_a_stated_torque_gets_a_blank_per_fastener_and_a_wrench(self) -> None:
        from cadgen.work_instruction import Cited, Torque

        spec, _ = _sources()
        wi = self.instruction()
        wi.step("Bolt", install=["base_plate"]).fasten(
            "#10-32 screw", qty=4, torque=Torque(32, 36, unit="in-lbf", per=spec.at("4.2")),
            sequence=Cited("Cross pattern, two passes", per=spec.at("4.3")))
        self.assertEqual(wi.equipment(), ["Torque wrench"])
        text = [t for page in _page_texts(wi) for t in page]
        self.assertEqual([t for t in text if t.startswith("ACTUAL TORQUE")],
                         [f"ACTUAL TORQUE {n}" for n in range(1, 5)])
        self.assertIn(("PS-2001 Rev D", "\u00a74.3", ["1"]), wi.references())

    def test_what_nobody_knows_yet_is_an_open_item(self) -> None:
        wi = self.instruction()
        wi.step("Pins", install=["pin"]).not_stated("Pin retention method")
        self.assertIn("step 1 (ask): pin retention method not stated", wi.open_items())

    def test_instructions_and_notices_cite_and_a_citation_prints_once(self) -> None:
        from cadgen.work_instruction import Adhesive

        spec, drawing = _sources()
        wi = self.instruction(emphasis="process")
        (wi.step("Bond", install=["base_plate"])
           .caution("Clamp evenly", per=spec.at("5.3"))
           .instruct("One witness coupon per mix", per=spec.at("3.4"))
           .bond(Adhesive("A", prep="p", mix="m", pot_life="l", cure="c", per=spec.at("5.1"))))
        self.assertEqual([where for _doc, where, _steps in wi.references()], ["\u00a75.3", "\u00a73.4", "\u00a75.1"])
        text = [t for page in _page_texts(wi) for t in page]
        self.assertEqual(text.count("per PS-2001 Rev D \u00a75.1"), 1, "one citation for the record's five lines")

    def test_each_operation_prints_its_own_citation(self) -> None:
        """A value cited to the section the operation before it cited still prints its citation."""
        from cadgen.work_instruction import Torque

        spec, _ = _sources()
        wi = self.instruction()
        (wi.step("Bolt", install=["base_plate"])
           .instruct("Clean the threads", per=spec.at("3.1"))
           .fasten("M8 bolt", qty=1, torque=Torque(40, unit="N-m", per=spec.at("3.1"))))
        text = [t for page in _page_texts(wi) for t in page]
        self.assertEqual(text.count("per PS-2001 Rev D \u00a73.1"), 2, "the instruction's, and the torque's")

    def test_apply_prints_the_material_and_lists_it_with_the_materials(self) -> None:
        from cadgen.work_instruction import Material

        spec, _ = _sources()
        sealant = Material("PR-1422 sealant", per=spec.at("6.2"), note="Fillet seal all edges")
        wi = self.instruction()
        wi.step("Seal", install=["base_plate"]).apply(sealant)
        self.assertEqual(wi.materials, [sealant])
        text = [t for page in _page_texts(wi) for t in page]
        for present in ("MATERIALS", "Apply: PR-1422 sealant", "How: Fillet seal all edges", "per PS-2001 Rev D \u00a76.2"):
            self.assertIn(present, text, present)
        with self.assertRaisesRegex(TypeError, "apply\\(\\) takes a Material"):
            wi.steps[0].apply("PR-1422")

    def test_a_warning_and_a_note_are_boxed_above_their_step(self) -> None:
        spec, _ = _sources()
        wi = self.instruction()
        (wi.step("Lift the plate", install=["base_plate"])
           .warning("Two-person lift", per=spec.at("1.2"))
           .note("Datum A down"))
        text = [t for page in _page_texts(wi) for t in page]
        order = [text.index(t) for t in ("WARNING", "Two-person lift", "per PS-2001 Rev D \u00a71.2", "NOTE",
                                         "Datum A down", "Lift the plate")]
        self.assertEqual(order, sorted(order), "each notice, then the step it governs")

    def test_an_a4_instruction_is_laid_out_on_a4(self) -> None:
        from cadgen._internal.work_instruction_pages import layout

        for size, mm in (("A4", (210.0, 297.0)), ("LETTER", (215.9, 279.4))):
            with self.subTest(size=size):
                wi = self.instruction(size=size)
                wi.step("Load", install=["base_plate"])
                flow = layout(wi, wi.open_items(), {})
                self.assertEqual((flow.w, flow.h), mm)

    def test_a_house_format_renames_the_instruction_column_and_drops_figures(self) -> None:
        from cadgen.work_instruction import Format

        wi = self.instruction(pictures=True, format=Format(instruction_label="OPERATION DESCRIPTION", figures=False))
        self.assertFalse(wi.pictures)
        wi.step("Load", install=["base_plate"])
        text = [t for page in _page_texts(wi) for t in page]
        self.assertIn("OPERATION DESCRIPTION", text)
        self.assertNotIn("FIGURE", text)

    def test_a_table_that_runs_onto_a_new_page_repeats_its_headings(self) -> None:
        wi = self.instruction(revisions=[(str(n), "2026-10-25", "change") for n in range(80)])
        wi.step("Load", install=["base_plate"])
        self.assertGreaterEqual([t for page in _page_texts(wi) for t in page].count("CHANGE"), 2)

    def test_an_empty_safety_section_says_so(self) -> None:
        wi = self.instruction()
        wi.step("Load", install=["base_plate"])
        self.assertIn("None stated.", [t for page in _page_texts(wi) for t in page])


class FreeTextValueTests(_Assembly):
    """A value written into free text cites its source as a Torque does, or its source is owed."""

    def _uncited(self, **kwargs):
        from cadgen.work_instruction import Torque

        spec, _ = _sources()
        wi = self.instruction(**kwargs)
        (wi.step("Bolt the base plate", install=["base_plate"])
           .warning("Torque the four M5 screws to 45 in-lbf")
           .instruct("Torque the four M5 screws to 45 in-lbf")
           .fasten("M5 screw", qty=4, torque=Torque(40, 45, unit="in-lbf", per=spec.at("4.2")),
                   sequence="Cross pattern, then 45 in-lbf"))
        wi.step("Set the bracket 0.5 mm proud", install=["bracket", "pin"]).inspect("Gap under 0.25 in")
        return wi

    def _cited(self, **kwargs):
        from cadgen.work_instruction import Cited, Torque

        spec, drawing = _sources()
        wi = self.instruction(**kwargs)
        (wi.step("Bolt the base plate", install=["base_plate"])
           .warning("Torque the four M5 screws to 45 in-lbf", per=spec.at("4.2"))
           .instruct("Torque the four M5 screws to 45 in-lbf", per=spec.at("4.2"))
           .fasten("M5 screw", qty=4, torque=Torque(40, 45, unit="in-lbf", per=spec.at("4.2")),
                   sequence=Cited("Cross pattern, then 45 in-lbf", per=spec.at("4.3"))))
        wi.step("Set the bracket proud", install=["bracket", "pin"]).inspect(
            "Gap under 0.25 in", per=drawing.at("note 2"))
        return wi

    def test_a_value_in_free_text_with_no_source_is_an_open_item_a_draft_lists(self) -> None:
        for rigor in ("production", "controlled"):
            with self.subTest(rigor=rigor):
                wi = self._uncited(rigor=rigor)
                self.assertEqual(wi.open_items(), [
                    "step 1 (warning): source of 45 in-lbf not stated",
                    "step 1 (instruct): source of 45 in-lbf not stated",
                    "step 1 (fasten): source of 45 in-lbf not stated",
                    "step 2 (title): source of 0.5 mm not stated",
                    "step 2 (inspect): " + ("criterion source" if rigor == "controlled" else "source of 0.25 in")
                    + " not stated",
                ])
                pages = _page_texts(wi)
                self.assertEqual(sum(page.count("NOT STATED") for page in pages), 5, "each owed source prints")
                self.assertEqual(self._cited(rigor=rigor).open_items(), [], "a cited value owes nothing")

    def test_a_released_instruction_refuses_an_uncited_value_and_writes_nothing(self) -> None:
        from cadgen.work_instruction import work_instruction

        for rigor in ("production", "controlled"):
            with self.subTest(rigor=rigor):
                target = self.root / f"released-{rigor}.pdf"

                @work_instruction(out=str(target))
                def uncited():
                    return self._uncited(rigor=rigor, status="released")

                @work_instruction(out=str(target))
                def cited():
                    return self._cited(rigor=rigor, status="released")

                with self.assertRaisesRegex(ValueError, r"(?s)released with 5 open item.*source of 45 in-lbf"):
                    uncited()
                self.assertFalse(target.exists())
                self.assertEqual(cited(), [target])

    def test_the_front_page_s_scope_and_safety_are_held_to_the_same_rule(self) -> None:
        from cadgen.work_instruction import Cited

        spec, _ = _sources()
        wi = self.instruction(scope="Bonding at 77 F and above", safety=["Wear gloves", "Parts reach 150 F in cure"])
        wi.step("Fit the plate", install=["base_plate", "bracket", "pin"])
        self.assertEqual(wi.open_items(), ["scope: source of 77 F not stated", "safety: source of 150 F not stated"])
        self.assertEqual(sum(page.count("NOT STATED") for page in _page_texts(wi)), 2, "each owed source prints")

        cited = self.instruction(scope=Cited("Bonding at 77 F and above", per=spec.at("2.1")),
                                 safety=["Wear gloves", Cited("Parts reach 150 F in cure", per=spec.at("5.4"))])
        cited.step("Fit the plate", install=["base_plate", "bracket", "pin"])
        self.assertEqual(cited.open_items(), [])
        self.assertIn(spec.at("2.1").document, [document for document, _ in cited.documents()], "a cited section is applicable")
        with self.assertRaisesRegex(TypeError, "a list of lines"):
            self.instruction(safety="Wear gloves")

    def test_a_value_is_a_number_and_a_unit_never_a_count_or_a_part_number(self) -> None:
        from cadgen.work_instruction import _owed

        for text in ("Support the carrier under the boss while pressing.", "Press planet pin 1 into the carrier",
                     "Slide planet gear 2 in place", "Fasten 4 screws", "Install 2 C-clips", "Step 3 of 4",
                     "Cross pattern, two passes", "Torque the M5 screws"):
            with self.subTest(text=text):
                self.assertEqual(_owed(text, None), [])
        for text, value in (("Cure 5 days at 77 F", "5 days, 77 F"), ("Mix 100:17 by weight", "100:17"),
                            ("Heat to 150°F", "150°F"), ("Torque to 40 to 45 IN-LBS", "40 to 45 IN-LBS"),
                            ("Hold 30 min", "30 min"), ("Gap 0.25 in max", "0.25 in"), ("Load 50 N", "50 N"),
                            ("Rotate 90°", "90°"), ("Torque 12 N·m", "12 N·m")):
            with self.subTest(text=text):
                self.assertEqual(_owed(text, None), [f"source of {value}"])
                self.assertEqual(_owed(text, _sources()[0].at("1")), [], "a cited value owes nothing")


class SubassemblyTests(unittest.TestCase):
    """A subassembly a step installs whole is one line, and copies of a part are one line."""

    @classmethod
    def setUpClass(cls) -> None:
        from build123d import Box, Compound, Pos
        from cadgen import model

        base = Box(100, 60, 10)
        base.label = "base_plate"
        hub = Pos(0, 0, 10) * Box(10, 10, 10)
        hub.label = "hub"
        rim = Pos(0, 0, 10) * Box(30, 30, 4)
        rim.label = "rim"
        pins = []
        for n, x in enumerate((-40, 40), start=1):
            pin = Pos(x, 0, 10) * Box(4, 4, 10)
            pin.label = f"pin_{n}"
            pins.append(pin)
        wheel = Compound(children=[hub, rim], label="wheel")
        cls.document = model(Compound(children=[base, wheel, *pins], label="nested"), name="nested")
        wheels = []
        for x in (-30, 30):
            hub = Pos(x, 0, 10) * Box(10, 10, 10)
            hub.label = "hub"
            rim = Pos(x, 0, 10) * Box(30, 30, 4)
            rim.label = "rim"
            wheels.append(Compound(children=[hub, rim], label="wheel"))
        cls.cart = model(Compound(children=[Box(100, 60, 10), *wheels], label="cart"), name="cart")

    def test_units_and_kinds(self) -> None:
        from cadgen._internal.work_instruction_pages import parts
        from cadgen.work_instruction import Instruction

        wi = Instruction(self.document, title="T", number="N", revision="A", pictures=False)
        self.assertIn("wheel", wi.tree())
        wi.step("Base", install=["base_plate"])
        wheel = wi.step("Wheel", install=["wheel"])
        self.assertEqual(len(wheel.units), 1, "the wheel is one unit")
        self.assertEqual(len(wheel.install), 2, "and two parts in its figure")
        wi.step("Pin 1", install=["pin_1"])
        wi.step("Pin 2", install=["pin_2"])
        rows = [(name, len(refs), steps) for name, refs, steps in parts(wi)]
        self.assertEqual(rows, [("base_plate", 1, ["1"]), ("wheel", 1, ["2"]), ("pin_1", 1, ["3"]),
                                ("pin_2", 1, ["4"])], "a number in a name is the name's, not a copy count")

    def test_a_subassembly_is_installed_by_its_ref_or_its_label(self) -> None:
        from cadgen.work_instruction import Instruction

        wi = Instruction(self.cart, title="T", number="N", revision="A", pictures=False)
        first = wi.step("First wheel", install=["wheel.1"])
        self.assertEqual((first.units, first.install), ((("cart/wheel.1", "wheel"),),
                                                        ("cart/wheel.1/hub", "cart/wheel.1/rim")))
        self.assertEqual(wi.step("Second wheel", install=["cart/wheel.2"]).install,
                         ("cart/wheel.2/hub", "cart/wheel.2/rim"), "its full path is a ref too")
        with self.assertRaisesRegex(KeyError, "names no one part or subassembly.*wheel.1, cart/wheel.2"):
            Instruction(self.cart, title="T", number="N", revision="A", pictures=False).step(
                "Wheels", install=["wheel"])
        alone = Instruction(self.document, title="T", number="N", revision="A", pictures=False)
        self.assertEqual(alone.step("Wheel", install=["wheel"]).units, (("wheel", "wheel"),),
                         "one subassembly of a label is installed by it")


class PartNameTests(unittest.TestCase):
    """The parts list groups only parts of one label: a number in a name is never read as a copy's."""

    @classmethod
    def setUpClass(cls) -> None:
        from build123d import Box, Compound, Pos
        from cadgen import model

        parts = []
        for n, label in enumerate(("base_plate", "bearing_6202", "bearing_6204", "spacer_10", "spacer_12",
                                   "washer", "washer")):
            part = Pos(n * 20, 0, 0) * Box(10, 10, 10)
            part.label = label
            parts.append(part)
        cls.document = model(Compound(children=parts, label="shaft"), name="shaft")

    def test_parts_of_different_names_are_never_one_line(self) -> None:
        from cadgen._internal.work_instruction_pages import _group, parts
        from cadgen.work_instruction import Instruction

        wi = Instruction(self.document, title="T", number="N", revision="A", pictures=False)
        wi.step("Base", install=["base_plate"])
        bearings = wi.step("Bearings", install=["bearing_6202", "bearing_6204"])
        wi.step("Spacers", install=["spacer_10", "spacer_12"])
        wi.step("Washers", install=["washer"])
        rows = [(name, len(refs)) for name, refs, _steps in parts(wi)]
        self.assertEqual(rows, [("base_plate", 1), ("bearing_6202", 1), ("bearing_6204", 1), ("spacer_10", 1),
                                ("spacer_12", 1), ("washer", 2)])
        self.assertEqual(_group(bearings.units), [("bearing_6202", ["bearing_6202"]),
                                                  ("bearing_6204", ["bearing_6204"])], "and two on the step")
        self.assertEqual(_group(wi.steps[-1].units), [("washer", ["shaft/washer.1", "shaft/washer.2"])])


class FileTests(unittest.TestCase):
    """An assembly's .xbf or .step is read as a model's document is, and a face named by the engine
    (``bracket/f:...``) is resolved through ``cadgen.inspect``. The names are a built model's own, so
    this builds the template's model once and writes its files."""

    @classmethod
    def setUpClass(cls) -> None:
        import sys
        from unittest import mock

        import cadgen

        temporary = generated_cad_directory(prefix="wi-files-")
        cls.addClassCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "bracket_assembly.py").write_text(ASSEMBLY_MODEL, encoding="utf-8")
        with mock.patch.object(sys, "path", [str(root), *sys.path]):
            from bracket_assembly import bracket_assembly
        cls.addClassCleanup(sys.modules.pop, "bracket_assembly", None)
        cls.document = bracket_assembly()
        cls.xbf, cls.step_file = root / "assembly.xbf", root / "assembly.step"
        cadgen.export(cls.document, cls.xbf, cls.step_file, log=lambda _line: None)

    def instruction(self, source):
        from cadgen.work_instruction import Instruction

        return Instruction(source, title="T", number="N", revision="A", pictures=False)

    def test_an_xbf_or_a_step_is_an_assembly_as_the_model_s_document_is(self) -> None:
        for source in (self.xbf, self.step_file):
            with self.subTest(source=source.name):
                wi = self.instruction(source)
                self.assertEqual((wi.source, wi.source_name), (str(source), source.name))
                self.assertEqual([leaf.label for leaf in wi.leaves()], ["base_plate", "bracket", "pin"])
                self.assertEqual(wi.step("Bracket", install=["bracket"]).bond(
                    None, surfaces=["bracket/face 5"]).ops[-1].surfaces, (("bracket/face 5", "bracket"),))

    def test_a_named_face_is_resolved_to_its_ordinal_through_the_engine(self) -> None:
        import cadgen

        name = cadgen.inspect(self.document.id, "bracket/face 5")["name"]
        self.assertTrue(name and name.startswith("f:"), name)
        for source in (self.document, self.xbf):
            with self.subTest(source=getattr(source, "name", source)):
                step = self.instruction(source).step("Bond", install=["bracket"])
                self.assertEqual(step.bond(None, surfaces=[f"bracket/{name}"]).ops[-1].surfaces,
                                 (("bracket/face 5", "bracket"),))
                with self.assertRaisesRegex(ValueError, "is not one face of"):
                    step.bond(None, surfaces=["bracket/f:bracket_assembly.no_such_face.1"])


class PictureTests(_Assembly):
    def test_each_picture_hides_what_is_still_to_come_and_tints_what_the_step_installs(self) -> None:
        from cadgen._internal.work_instruction_pages import picture_plan

        wi = self.instruction(pictures=True)
        wi.step("Prepare the fixture")
        wi.step("Load", install=["base_plate"])
        wi.step("Bond", install=["bracket"]).bond(None, surfaces=["bracket/face 5"])
        wi.step("Pins", install=["pin"], camera="top")
        plan = {p.step: p for p in picture_plan(wi)}
        self.assertNotIn(1, plan, "nothing is installed yet, so there is nothing to picture")
        self.assertEqual(plan[2].hide, ("bracket", "assembly/pin.1", "assembly/pin.2"))
        self.assertEqual((plan[3].tint, plan[3].surfaces), (("bracket",), ("bracket/face 5",)))
        self.assertEqual((plan[4].hide, plan[4].camera), ((), "top"))
        self.assertEqual(plan[3].focus, ("bracket",), "a figure is framed on the parts its step installs")

    def test_each_picture_is_one_hidden_line_job_with_the_step_s_parts_tinted(self) -> None:
        """The fill is the snapshot's own (``display.tint``), so it is exactly where the parts show;
        ``frame="assembly"`` places the camera on the whole assembly, ``frame="step"`` on the step's parts."""
        from cadgen._internal.work_instruction_pages import FILL, _extent, picture_jobs

        wi = self.instruction(pictures=True)
        wi.step("Load", install=["base_plate"])
        wi.step("Bracket", install=["bracket"], frame="assembly")
        wi.step("Pins", install=["pin"])
        jobs = picture_jobs(wi, self.root)
        self.assertEqual(jobs[2]["display"], {"mode": "hidden-line", "hidden": ["assembly/pin.1", "assembly/pin.2"],
                                              "tint": {"parts": ["bracket"], "color": FILL}})
        self.assertEqual(jobs[3]["display"], {"mode": "hidden-line",
                                              "tint": {"parts": ["assembly/pin.1", "assembly/pin.2"], "color": FILL}})
        self.assertEqual(jobs[1]["outputs"][0]["path"], str(self.root / "step-1.png"))
        centre, diagonal = _extent(wi)
        whole, pins = jobs[2]["camera"], jobs[3]["camera"]
        self.assertEqual((whole["target"], whole["orthographicHalfHeight"]), (centre, round(0.5 * diagonal, 4)),
                         "the whole assembly")
        self.assertEqual(pins["target"], [0.0, 0.0, 50.0], "the pins' centre")
        self.assertLess(pins["orthographicHalfHeight"], whole["orthographicHalfHeight"])

    def test_a_part_s_fill_shows_where_its_face_lines_up_with_an_earlier_part_s(self) -> None:
        """A shim on a plate: its top face is parallel to the plate's and lit alike, and is filled."""
        import numpy as np
        from build123d import Box, Compound, Pos
        from cadgen import model
        from cadgen._internal.work_instruction_pages import FILL, render_pictures
        from cadgen.engine.render import context
        from cadgen.work_instruction import Instruction
        from PIL import Image

        opengl.require(context.available(), "the pictures are drawn by OCCT")
        base = Box(100, 60, 10)
        base.label = "base_plate"
        shim = Pos(0, 0, 6) * Box(40, 40, 2)
        shim.label = "shim"
        document = model(Compound(children=[base, shim], label="stack"), name="stack")
        wi = Instruction(document, title="T", number="N", revision="A")
        wi.step("Base", install=["base_plate"])
        wi.step("Shim", install=["shim"], frame="assembly")
        folder = self.root / "shim"
        folder.mkdir()
        picture = np.asarray(Image.open(render_pictures(wi, folder)[2]).convert("RGB"), int)
        fill = np.array([int(FILL[at:at + 2], 16) for at in (1, 3, 5)])
        h, w, _ = picture.shape
        top = picture[h // 2 - 10:h // 2 + 10, w // 2 - 10:w // 2 + 10]  # the middle of the shim's top face
        self.assertLessEqual(int(np.abs(top - fill).max()), 2, "the shim's top face is filled, flat")
        self.assertEqual(sorted(path.name for path in folder.iterdir()), ["step-1.png", "step-2.png"],
                         "one picture a step")

    def test_a_surface_on_a_part_not_yet_installed_is_refused(self) -> None:
        from cadgen._internal.work_instruction_pages import picture_plan

        wi = self.instruction(pictures=True)
        wi.step("Load", install=["base_plate"]).bond(None, surfaces=["bracket/face 5"])
        with self.assertRaisesRegex(ValueError, "no step up to and including step 1 installs"):
            picture_plan(wi)

    def test_the_pictures_render_through_the_snapshot_runtime_into_the_pdf(self) -> None:
        from cadgen.engine.render import context
        from cadgen.work_instruction import work_instruction

        opengl.require(context.available(), "the pictures are drawn by OCCT")

        target = self.root / "pictured.pdf"

        @work_instruction(out=str(target))
        def pictured():
            wi = self.instruction(pictures=True)
            wi.step("Load", install=["base_plate"])
            wi.step("Bond", install=["bracket"]).bond(None, surfaces=["bracket/face 6"])
            return wi

        pictured()
        self.assertEqual(len(re.findall(rb"/Subtype\s*/Image", target.read_bytes())), 2)


class DocumentedTemplateTests(unittest.TestCase):
    """The skill's template is run, not just proofread: an agent copies it, so a template that has
    drifted from ``cadgen.work_instruction`` is a generator of broken scripts. It runs here beside
    a model of the part names it uses, built by the module's engine, and must write its PDF with
    the open items its placeholders leave. Its pictures are left out: the test above draws them."""

    def test_the_skill_links_the_template(self) -> None:
        self.assertIn("references/instruction-api.md#template", SKILL.read_text(encoding="utf-8"))

    def test_the_template_runs_and_leaves_its_placeholders_open(self) -> None:
        import contextlib
        import io
        import runpy
        import sys
        from unittest import mock

        section = REFERENCE.read_text(encoding="utf-8").split("## Template", 1)[1]
        found = re.search(r"```python\n(.*?)```", section, re.S)
        assert found, "the reference's Template section has no python block"
        temporary = generated_cad_directory(prefix="wi-template-")
        self.addCleanup(temporary.cleanup)
        src = Path(temporary.name) / "src"
        src.mkdir()
        (src / "bracket_assembly.py").write_text(ASSEMBLY_MODEL, encoding="utf-8")
        script = src / "bracket_assembly_wi.py"
        script.write_text(found.group(1), encoding="utf-8")
        self.enterContext(mock.patch.object(sys, "path", [str(src), *sys.path]))
        self.addCleanup(sys.modules.pop, "bracket_assembly", None)

        printed = io.StringIO()
        with mock.patch("cadgen._internal.work_instruction_pages.render_pictures", return_value={}), \
                contextlib.redirect_stdout(printed):
            runpy.run_path(str(script), run_name="__main__")
        self.assertTrue((src.parent / "PDF/bracket_assembly_wi.pdf").is_file())
        self.assertIn("open item: step 2 (bond): pot life not stated", printed.getvalue())
        self.assertIn("open item: step 4 (fasten): torque not stated", printed.getvalue())


if __name__ == "__main__":
    unittest.main()
