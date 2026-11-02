"""The document type registry is the one table every layer reads.

The library's `cad.registry` is the source; the JavaScript side is generated from it
(`packages/core/src/lib/documentTypes.generated.js`), as the reference grammars share a parity
fixture, so a type one side learns and the other forgets fails here rather than in a page. The
table holds itself to the definitions: lowercase Python ids, one type per extension, operations
from the fixed set, and exactly one producer per value per type.
"""

from __future__ import annotations

import subprocess
import sys
import unittest

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cad/src")

from cad import registry  # noqa: E402

GENERATED = repo_path("packages", "core", "src", "lib", "documentTypes.generated.js")


class TheTableIsTheSource(unittest.TestCase):
    def test_the_javascript_is_generated_from_the_registry(self) -> None:
        self.assertEqual(registry.as_js(), GENERATED.read_text(encoding="utf-8"),
                         "regenerate: python -m cad.registry --js > packages/core/src/lib/documentTypes.generated.js")

    def test_every_type_is_well_formed(self) -> None:
        seen: dict[str, str] = {}
        for entry in registry.DOCUMENT_TYPES.values():
            with self.subTest(type=entry.id):
                self.assertTrue(entry.id.isidentifier() and entry.id == entry.id.lower())
                self.assertIn(entry.view, registry.VIEWS)
                self.assertTrue(entry.operations, "a type implements at least one operation")
                for operation in entry.operations:
                    self.assertIn(operation.name, registry.OPERATIONS)
                    self.assertTrue(operation.integration is None or operation.integration in registry.INTEGRATIONS)
                for extension in entry.extensions:
                    self.assertTrue(extension.startswith(".") and extension == extension.lower())
                    self.assertNotIn(extension, seen, f"{extension} is {seen.get(extension)}'s already")
                    seen[extension] = entry.id
        self.assertEqual("step", registry.by_extension(".STP").id)
        self.assertEqual("threemf", registry.type_of("/a/part.3mf").id)
        self.assertEqual("3mf", registry.DOCUMENT_TYPES["threemf"].wire)
        self.assertIsNone(registry.type_of("model.py"))

    def test_every_integration_is_well_formed(self) -> None:
        for integration in registry.INTEGRATIONS.values():
            with self.subTest(integration=integration.name):
                self.assertIn(integration.process, registry.PROCESS_KINDS)
                if integration.probe is not None:
                    self.assertTrue(integration.probe.minimum and integration.probe.install_hint)
                self.assertTrue(integration.modules and integration.distributions)
        self.assertEqual(("build123d", "kicad"), registry.integrations_of(["build123d.topology", "kipy", "os"]))
        self.assertEqual("kicad", registry.DOCUMENT_TYPES["kicad_pcb"].decorator_integration)
        self.assertEqual("build123d", registry.DOCUMENT_TYPES["step"].decorator_integration)
        self.assertIsNone(registry.DOCUMENT_TYPES["urdf"].decorator_integration)

    def test_a_decorator_has_exactly_one_producer_per_value(self) -> None:
        class Shape:  # a build123d Shape, by its ancestry's names alone
            __module__ = "build123d.topology"

        class Box(Shape):
            pass

        from cad.kicad._session import BoardScript

        script = BoardScript(lambda board: None, __import__("pathlib").Path("board.kicad_pcb"))
        for entry in registry.DOCUMENT_TYPES.values():
            with self.subTest(type=entry.id):
                producers = registry.producers_for(entry.id)
                self.assertEqual(entry.decorator, bool(producers))
                for producer in producers:
                    self.assertTrue(set(producer.provides) <= set(entry.content), "a producer provides the type's content")
                    self.assertIn(producer.integration, registry.INTEGRATIONS)
                if any(producer.integration == "build123d" for producer in producers):
                    self.assertEqual("build123d", registry.producer_for(entry.id, Box()).integration)
        # A board script's step is the kicad integration's, a shape's the build123d one's: one producer each,
        # and @step declared on a board script by the kicad producer (``declarer_for``).
        self.assertEqual("kicad", registry.producer_for("step", script).integration)
        self.assertEqual("kicad", registry.declarer_for("step", script).integration)
        self.assertIsNone(registry.declarer_for("step", lambda: None), "a function under @step is the engine's model")
        self.assertEqual("kicad", registry.declarer_for("kicad_pcb", lambda board: None).integration)

    def test_an_unsupported_return_names_what_the_type_takes_and_the_integration(self) -> None:
        class Frame:
            __module__ = "pandas.core.frame"

        with self.assertRaises(TypeError) as caught:
            registry.producer_for("step", Frame(), where="model m.py::m")
        said = str(caught.exception)
        self.assertIn("model m.py::m returned Frame", said)
        self.assertIn("a build123d Shape", said)
        self.assertIn("no pandas integration", said)

    def test_each_types_help_is_worked_out_from_the_table(self) -> None:
        said = registry.help_text("step")
        self.assertIn("(.step, .stp)", said)
        self.assertIn("carries: geometry", said)
        self.assertIn('@step("out.step")', said)
        self.assertIn("written by: no producer", registry.help_text("urdf"))

    def test_the_registry_imports_no_kernel(self) -> None:
        code = ("import sys; import cad.registry as r; r.help_text('step'); "
                "print(sorted(m for m in sys.modules if m.split('.')[0] in ('OCP', 'build123d', 'numpy')))")
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              env={"PYTHONPATH": str(repo_path("packages", "cad", "src"))}, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("[]", proc.stdout.strip())


if __name__ == "__main__":
    unittest.main()
