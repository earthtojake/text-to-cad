"""The document type registry is the one table every layer reads.

The library's `cad.registry` is the source; the JavaScript side is generated from it
(`packages/core/src/lib/documentTypes.generated.js`), as the reference grammars share a parity
fixture, so a type one side learns and the other forgets fails here rather than in a page. The
table holds itself to the definitions: lowercase Python ids, one type per extension, operations
from the fixed set, and exactly one producer per value per type.
"""

from __future__ import annotations

import os
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
                # What one needs beside it is registered, is not itself, and has an extra cad run can add.
                self.assertNotIn(integration.name, integration.needs)
                for needed in integration.needs:
                    self.assertIn(needed, registry.INTEGRATIONS)
                    self.assertTrue(registry.INTEGRATIONS[needed].extra)
        self.assertEqual(("build123d", "kicad"), registry.integrations_of(["build123d.topology", "kicode", "os"]))
        self.assertEqual(("cadjoint",), registry.integrations_of(["cadjoint.construction"]))
        # cadjoint's solids are build123d's: a program of its fields needs the kernel beside it.
        self.assertEqual(("build123d",), registry.INTEGRATIONS["cadjoint"].needs)
        # A KiCad board and schematic are edited in place (``<type>.edit``), by the kicad integration; no other
        # type is.
        self.assertEqual({"kicad_pcb": "kicad", "kicad_sch": "kicad"},
                         {entry.id: entry.edit.integration for entry in registry.DOCUMENT_TYPES.values() if entry.edit})
        for kind in ("kicad_pcb", "kicad_sch"):
            self.assertFalse(registry.DOCUMENT_TYPES[kind].decorator, "an edit, no producer: the type has no decorator")
        # What cad run reads of the integrations is the registry's view, not a table of its own.
        from cad._internal import integrations

        self.assertEqual(sorted(integrations.INTEGRATIONS), sorted(i.extra for i in registry.INTEGRATIONS.values() if i.extra))
        # A use of an edit needs its integration in the caller's process; a reader of our own, none.
        self.assertEqual("kicad", integrations.for_name("cad.kicad_pcb.edit"))
        self.assertEqual("kicad", integrations.for_name("cad.kicad_sch.edit"))
        self.assertIsNone(integrations.for_name("cad.kicad_pcb.read"))
        self.assertEqual(registry.INTEGRATIONS["build123d"].modules, integrations.INTEGRATIONS["build123d"].modules)
        self.assertIsNone(integrations.for_distribution("pillow"), "a package an extra installs is not the integration")
        self.assertEqual(("build123d",), integrations.INTEGRATIONS["cadjoint"].needs)
        self.assertEqual(("build123d", "cadjoint"), integrations.closed(["cadjoint"]))
        self.assertEqual(("build123d", "cadjoint", "kicad"), integrations.closed(["kicad", "cadjoint", "build123d"]))
        self.assertEqual((), integrations.closed([]))

    def test_a_decorator_has_exactly_one_producer_per_value(self) -> None:
        class Shape:  # a build123d Shape, by its ancestry's names alone
            __module__ = "build123d.topology"

        class Box(Shape):
            pass

        for entry in registry.DOCUMENT_TYPES.values():
            with self.subTest(type=entry.id):
                producers = registry.producers_for(entry.id)
                self.assertEqual(entry.decorator, bool(producers))
                for producer in producers:
                    self.assertTrue(set(producer.provides) <= set(entry.content), "a producer provides the type's content")
                    self.assertIn(producer.integration, registry.INTEGRATIONS)
                if any(producer.integration == "build123d" for producer in producers):
                    self.assertEqual("build123d", registry.producer_for(entry.id, Box()).integration)

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
        # A board and a schematic are written by their edits (``cad kicad_pcb --help``, ``cad kicad_sch --help``).
        self.assertIn('with kicad_pcb.edit("board.kicad_pcb") as board: the open board', registry.help_text("kicad_pcb"))
        self.assertIn('with kicad_sch.edit("schematic.kicad_sch") as schematic: the open schematic',
                      registry.help_text("kicad_sch"))

    def test_the_registry_imports_no_kernel(self) -> None:
        code = ("import sys; import cad.registry as r; r.help_text('step'); "
                "print(sorted(m for m in sys.modules if m.split('.')[0] in ('OCP', 'build123d', 'numpy')))")
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": str(repo_path("packages", "cad", "src"))}, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("[]", proc.stdout.strip())


if __name__ == "__main__":
    unittest.main()
