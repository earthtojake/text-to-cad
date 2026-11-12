"""Open in's Blender script parses and imports on the oldest Python a Blender it supports bundles.

``cad_server/_internal/open_in_blender.py`` is not run by our Python: ``apps.open_file`` starts a person's own
Blender with it (``--python``), so it runs on whatever Python that Blender bundles, with nothing of cad's installed.
It says it supports Blender 2.80 and later, and 2.80 bundles Python 3.7 (2.93 and 3.0: 3.9). The packages' own floor
(``test_cadgen_python_floor_syntax.py``, read from ``requires-python``) is not this file's, and a file can parse on
an old grammar yet die there at import: ``def f(x: str | None)`` is valid syntax on 3.7 and a TypeError on 3.9 when
the function is defined. So, for this one file:

* it parses with Python 3.7's grammar (``ast.parse(..., feature_version=(3, 7))``);
* it holds no f-string, whose grammar ``feature_version`` does not check on 3.12 and later (PEP 701);
* it evaluates no annotation at import: it has none, unless ``from __future__ import annotations`` keeps them
  unevaluated (a class Blender registers reads its annotations as properties, so the script has none at all);
* it imports, at module scope, the standard library alone; Blender's ``bpy`` only where Blender runs it.

Reads the file alone: nothing is installed for it.
"""

from __future__ import annotations

import ast
import sys
import unittest

from tests.python.support.paths import REPO_ROOT

SCRIPT = REPO_ROOT / "packages" / "cad-server" / "src" / "cad_server" / "_internal" / "open_in_blender.py"
FLOOR = (3, 7)  # Blender 2.80's Python, the oldest the script's docstring claims


def annotations(tree: ast.AST) -> list[int]:
    """The lines holding an annotation: an argument's, a return's, or an annotated assignment's."""
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) or (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                                                and node.returns is not None):
            lines.append(node.lineno)
        elif isinstance(node, ast.arg) and node.annotation is not None:
            lines.append(node.lineno)
    return sorted(lines)


class OpenInBlenderPythonFloorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SCRIPT.read_text(encoding="utf-8")
        self.tree = ast.parse(self.text, str(SCRIPT))

    def test_the_docstring_names_the_floor_checked_here(self) -> None:
        self.assertIn("Blender 2.80 and later", ast.get_docstring(self.tree) or "")
        self.assertIn("Python 3.7", ast.get_docstring(self.tree) or "")

    def test_it_parses_with_the_floors_grammar(self) -> None:
        ast.parse(self.text, str(SCRIPT), feature_version=FLOOR)

    def test_it_holds_no_f_string(self) -> None:
        found = sorted(node.lineno for node in ast.walk(self.tree) if isinstance(node, ast.JoinedStr))
        self.assertEqual(found, [], "an f-string's grammar is not checked against the floor on this Python")

    def test_it_evaluates_no_annotation_at_import(self) -> None:
        future = any(isinstance(node, ast.ImportFrom) and node.module == "__future__"
                     and any(alias.name == "annotations" for alias in node.names) for node in self.tree.body)
        if not future:
            self.assertEqual(annotations(self.tree), [], "an annotation is evaluated where it is defined on 3.7-3.9")

    def test_it_imports_the_standard_library_alone_and_bpy_only_where_blender_runs_it(self) -> None:
        imported = set()
        for node in self.tree.body:
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertEqual(sorted(imported - set(sys.stdlib_module_names)), [])
        [main] = [node for node in self.tree.body if isinstance(node, ast.If)
                  and ast.unparse(node.test) == "__name__ == '__main__'"]
        self.assertIn("importlib.import_module('bpy')", ast.unparse(main))


if __name__ == "__main__":
    unittest.main()
