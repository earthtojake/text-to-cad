"""The render skill's files, read as text: the skill holds no code of its own, and its pages document the API the
library's blender integration has (``cad.blender``: ``packages/cad/src/cad/blender``).
Standard library alone: ``load`` runs only inside Blender, and its behaviour is the blender job's suite
(tests/python/packages/blender)."""

from __future__ import annotations

import ast
import re
import unittest

from tests.python.support.paths import REPO_ROOT

SKILL = REPO_ROOT / "skills/render"
BLENDER = REPO_ROOT / "packages/cad/src/cad/blender"


class SkillFiles(unittest.TestCase):
    def test_the_skill_holds_no_code_its_script_imports_the_library_s(self) -> None:
        # What a render script needs is the library's, reached by an import: nothing to copy into a project.
        self.assertEqual(sorted(path.relative_to(SKILL).as_posix() for path in SKILL.rglob("*")
                                if path.is_file() and path.suffix not in (".md", ".yaml") and path.name != "LICENSE"
                                and "__pycache__" not in path.parts), [])
        page = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        script = re.search(r"```python\n# render\.py.*?```", page, re.S)[0]
        self.assertIn("from cad.blender import load\n", script)
        for text in (page, *(path.read_text(encoding="utf-8") for path in (SKILL / "references").glob("*.md"))):
            self.assertNotIn("sys.path", text)

    def test_the_page_documents_the_api_the_library_has(self) -> None:
        tree = ast.parse((BLENDER / "_scene.py").read_text(encoding="utf-8"))
        public = ast.literal_eval(next(node.value for node in ast.parse(
            (BLENDER / "__init__.py").read_text(encoding="utf-8")).body
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "__all__"))
        self.assertEqual(public, ["Clip", "Model", "load"])
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        load = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "load")
        defaults = [ast.literal_eval(value) for value in load.args.defaults]
        arguments = [argument.arg for argument in load.args.args]
        self.assertEqual((arguments, defaults), (["path", "clip", "fps"], [None, 24]))
        self.assertIn("`load(path, clip=None, fps=24)`", text)
        model = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Model")
        members = {node.target.id for node in model.body if isinstance(node, ast.AnnAssign)}
        members |= {node.name for node in model.body if isinstance(node, ast.FunctionDef)}
        pages = text + "".join(path.read_text(encoding="utf-8") for path in (SKILL / "references").glob("*.md"))
        named = set(re.findall(r"`?model\.(\w+)", pages))
        self.assertLessEqual({"root", "roots", "objects", "nodes", "clips", "box", "play", "bounds"}, named)
        for name in named:
            with self.subTest(name=name):
                self.assertIn(name, members)


if __name__ == "__main__":
    unittest.main()
