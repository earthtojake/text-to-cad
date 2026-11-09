"""The render skill's files, read as text: its Blender helper imports nothing but bpy and the standard library, and is
the API the skill's page documents.
Standard library alone: the helper runs only inside Blender, and its behaviour is the blender job's suite
(tests/python/packages/blender)."""

from __future__ import annotations

import ast
import re
import sys
import unittest

from tests.python.support.paths import REPO_ROOT

SKILL = REPO_ROOT / "skills/render"
HELPER = SKILL / "scripts/cad_glb.py"


class HelperCode(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = ast.parse(HELPER.read_text(encoding="utf-8"))

    def test_it_imports_bpy_and_the_standard_library_alone(self) -> None:
        names = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                names |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        self.assertIn("bpy", names)
        self.assertEqual(sorted(names - set(sys.stdlib_module_names) - {"bpy", "mathutils", "__future__"}), [])

    def test_the_page_documents_the_api_it_has(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        load = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name == "load")
        defaults = [ast.literal_eval(value) for value in load.args.defaults]
        arguments = [argument.arg for argument in load.args.args]
        self.assertEqual((arguments, defaults), (["path", "clip", "fps"], [None, 24]))
        self.assertIn("`cad_glb.load(path, clip=None, fps=24)`", text)
        model = next(node for node in self.tree.body if isinstance(node, ast.ClassDef) and node.name == "Model")
        members = {node.target.id for node in model.body if isinstance(node, ast.AnnAssign)}
        members |= {node.name for node in model.body if isinstance(node, ast.FunctionDef)}
        for name in set(re.findall(r"`model\.(\w+)", text)):
            with self.subTest(name=name):
                self.assertIn(name, members)


if __name__ == "__main__":
    unittest.main()
