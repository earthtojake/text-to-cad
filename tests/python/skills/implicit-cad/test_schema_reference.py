from __future__ import annotations

import unittest

from tests.python.support.paths import repo_path

SCHEMA_PATH_REFERENCE = "scripts/packages/implicitjs/src/lib/implicitCad/schema.js"
HELPER_REEXPORT = "scripts/lib/implicit-cad.mjs"
SCHEMA_MARKER = "implicit.js/0.1.0"


class ImplicitCadSchemaReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.skill_root = repo_path("skills", "implicit-cad")

    def test_skill_md_names_the_schema_source_of_truth(self) -> None:
        source = (self.skill_root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(SCHEMA_PATH_REFERENCE, source)

    def test_schema_path_reference_resolves(self) -> None:
        schema = self.skill_root / SCHEMA_PATH_REFERENCE
        self.assertTrue(schema.is_file(), f"{SCHEMA_PATH_REFERENCE} must resolve to a file")
        self.assertGreater(schema.read_text(encoding="utf-8").strip(), "")
        self.assertIn(SCHEMA_MARKER, schema.read_text(encoding="utf-8"))

    def test_skill_reexport_module_resolves(self) -> None:
        helper = self.skill_root / HELPER_REEXPORT
        self.assertTrue(helper.is_file(), f"{HELPER_REEXPORT} must resolve to a file")
