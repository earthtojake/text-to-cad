"""The WireViz document a harness writes, and how @harness is declared, read and listed, without WireViz.

The document's bytes are a function of the harness: keys in a fixed order,
strings quoted, numbers the one way WireViz reads them, one connection set per
``connect`` call. The decorator, the static reader and the catalog agree on
what a harness model is and what it writes; the plot route takes a
``.harness.yml`` and, with no WireViz installed, says how to get it. What
WireViz makes of the documents is the harness suite's (tests/python/packages/harness).
"""

from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import harness  # noqa: E402
from cadgen.metadata import declared_output_paths, model_function_formats, parse_generator_metadata  # noqa: E402
from cadgen.wireviz.document import harness_document  # noqa: E402

EXPECTED = '''\
metadata:
  title: "Motor \\"A\\" lead"
connectors:
  "NO":
    type: "Molex Micro-Fit 3.0"
    subtype: "female"
    mpn: "43025-0400"
    pins: [1, 2, 3, 4]
    pinlabels: ["A+", "A-", "B+", "B-"]
    notes: "keyed\\ntab up"
    additional_components:
      - type: "Crimp terminal"
        mpn: "43030-0007"
        qty_multiplier: "populated"
  "M1":
    pins: ["A1", "B1"]
  "F1":
    style: "simple"
    pins: [1]
cables:
  "W1":
    gauge: "22 AWG"
    length: 0.3
    wirecount: 4
    colors: ["BK", "WH", "BK", "WH"]
    shield: true
  "W2":
    category: "bundle"
    gauge: "0.5 mm2"
    length: 1.0
    wirecount: 2
    colors: ["RD", "WHGN"]
connections:
  -
    - "NO": [1, 2]
    - "W1": [1, 2]
    - "M1": ["A1", "B1"]
  -
    - "NO": [3]
    - "W1": [3]
    - "F1": [1]
  -
    - "NO": [4]
    - "W2": [1]
'''


def _harness() -> harness.Harness:
    h = harness.Harness(title='Motor "A" lead')
    plug = h.connector(
        "NO", pinlabels=["A+", "A-", "B+", "B-"], type="Molex Micro-Fit 3.0", subtype="female", mpn="43025-0400",
        notes="keyed\ntab up", additional_components=[{"type": "Crimp terminal", "mpn": "43030-0007", "qty_multiplier": "populated"}],
    )
    lead = h.connector("M1", pins=["A1", "B1"])
    ferrule = h.connector("F1", pincount=1, style="simple")
    w1 = h.cable("W1", color_code="BW", wirecount=4, gauge="22 AWG", length=300, shield=True)
    w2 = h.cable("W2", colors=["RD", "WHGN"], gauge="0.5 mm2", length=1000, category="bundle")
    # One call whose rows end on different connectors is one WireViz set per run.
    h.connect([plug[1], plug[2], plug[3]], [w1[1], w1[2], w1[3]], [lead["A1"], lead["B1"], ferrule[1]])
    h.connect(plug[4], w2[1])  # a wire with a free end; W1's fourth wire is a spare
    return h


SCRIPT = textwrap.dedent(
    """
    from cadgen import harness


    @harness
    def lead():
        pass


    @harness(out="cables/main.harness.yml", bom=True)
    def main():
        pass
    """
)


class HarnessDocumentTest(unittest.TestCase):
    def test_the_document_is_a_function_of_the_harness(self) -> None:
        self.assertEqual(harness_document(_harness()), EXPECTED)
        self.assertEqual(harness_document(_harness()), harness_document(_harness()))

    def test_a_harness_with_problems_writes_nothing(self) -> None:
        h = harness.Harness()
        h.connector("X1", pincount=1)
        with self.assertRaisesRegex(harness.HarnessError, "cannot be written:\n  the harness connects nothing"):
            harness_document(h)
        with self.assertRaisesRegex(harness.HarnessError, "returns a harness.Harness, got dict"):
            harness_document({})


class HarnessModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name).resolve()
        self.script = self.folder / "cables.py"
        self.script.write_text(SCRIPT, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_the_static_reader_and_the_decorators_agree_on_a_harness(self) -> None:
        self.assertEqual(model_function_formats(SCRIPT), {"lead": "harness", "main": "harness"})
        main = parse_generator_metadata(self.script, "main")
        self.assertEqual((main.format, main.out_target, [decl.fmt for decl in main.fab_exports]), ("harness", "cables/main.harness.yml", ["bom"]))

        def outputs(name: str) -> list[str]:
            return [path.relative_to(self.folder).as_posix() for path in declared_output_paths(self.script, function=name)]

        self.assertEqual(outputs("lead"), ["lead.harness.yml"])
        self.assertEqual(outputs("main"), ["cables/main.harness.yml", "cables/main.bom.csv"])

    def test_a_harness_is_its_own_model_and_bom_is_its_one_export(self) -> None:
        from cadgen import authoring, pcb, step
        from cadgen.store.index import model_ref

        self.addCleanup(authoring._REGISTRY.pop, model_ref(Path(__file__).resolve(), "body"), None)

        def fresh():
            def body():
                return None

            return body

        refusals = {
            "@step cannot stack on body\\(\\), a @harness": lambda: step(harness(fresh())),
            "@pcb cannot stack on body\\(\\), a @harness": lambda: pcb(harness(fresh())),
            "body\\(\\) is already a @step model; a @harness is a model of its own": lambda: harness(step(fresh())),
            "@harness takes no gerber=: those are a @pcb board's manufacturing files": lambda: harness(gerber=True),
            "@harness out= names the harness document and must end with '.harness.yml'": lambda: harness(out="cable.yml"),
        }
        for message, attempt in refusals.items():
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                attempt()
        declared = harness(bom=True)(fresh()).__cadgen_model__
        self.assertEqual((declared.fmt, [decl.fmt for decl in declared.fab_exports]), ("harness", ["bom"]))

    def test_the_catalog_lists_a_harness_document_and_not_any_yaml(self) -> None:
        from cadgen.viewer.content_types import content_type_for_path, extension_of
        from cadgen.viewer.scanner import scan_cad_directory, source_format_for_path

        self.assertEqual(extension_of("cables/Main.Harness.YML"), ".harness.yml")
        self.assertEqual(extension_of("config.yml"), ".yml")
        self.assertEqual(extension_of(".harness.yml"), ".yml")  # a hidden name, as Node reads it
        self.assertEqual(source_format_for_path("main.harness.yml"), "harness")
        self.assertTrue(content_type_for_path("main.harness.yml").startswith("application/yaml"))
        (self.folder / "main.harness.yml").write_text(EXPECTED, encoding="utf-8")
        (self.folder / "config.yml").write_text("a: 1\n", encoding="utf-8")
        entries = scan_cad_directory(str(self.folder))["entries"]
        self.assertEqual([(entry["file"], entry["kind"]) for entry in entries], [("main.harness.yml", "harness")])

    def test_the_plot_route_takes_a_harness_and_names_what_is_missing(self) -> None:
        from cadgen.kicad.plot import PlotError
        from cadgen.viewer.plots import plot_payload_response

        (self.folder / "main.harness.yml").write_text(EXPECTED, encoding="utf-8")
        (self.folder / "config.yml").write_text("a: 1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "renders KiCad boards and schematics and wiring harnesses"):
            plot_payload_response(str(self.folder), "config.yml")
        self.assertEqual(plot_payload_response(str(self.folder), "absent.harness.yml")[0], 404)
        with mock.patch.dict(os.environ, {"CADGEN_WIREVIZ": str(self.folder / "no-wireviz")}):
            with self.assertRaisesRegex(PlotError, "WireViz's command line, wireviz, was not found: install Graphviz"):
                plot_payload_response(str(self.folder), "main.harness.yml")


if __name__ == "__main__":
    unittest.main()
