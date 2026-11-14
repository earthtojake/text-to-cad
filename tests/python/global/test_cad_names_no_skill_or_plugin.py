"""The cad packages name no skill and no plugin in what they print or return.

text-to-cad's distributions (``packages/cad``, ``packages/cad-server``, ``packages/cad-mcp``) know nothing of the
skills or the plugin that use them: the plugin side knows cad, never the other way. So no string a package can print
or return -- every string literal in its sources but a docstring -- says "skill" or "plugin". The words a format
uses for its own elements (SDF's ``<plugin>``) and the folder names earlier releases left in the state folder,
which ``cad uninstall`` recognises as its own, are not messages.
"""

from __future__ import annotations

import ast
import re
import unittest

from tests.python.support.paths import PROJECTS

WORDS = re.compile(r"\b(skills?|plugins?)\b", re.IGNORECASE)
# Strings that are no message: SDF's own element and its paths, and the names of folders in the state folder.
NOT_MESSAGES = {
    "cad/sdf/_validation.py": None,  # SDF's <plugin> element: the format's word
    "cad/engine/sdf_source.py": None,  # the same element, read
    "cad_server/cli/uninstall.py": {"plugin", "plugin.lock"},  # folder names earlier releases left
}
# Messages other lanes of the change that removed the rest reword or remove; this set only shrinks.
PENDING = {"cad_server/_internal/pins.py", "cad_mcp/engine.py", "cad_mcp/shim.py"}


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def offenders() -> list[str]:
    found = []
    for project in PROJECTS:
        source = project / "src"
        for path in sorted(source.rglob("*.py")):
            relative = path.relative_to(source).as_posix()
            if ".egg-info" in relative or relative in PENDING:
                continue
            allowed = NOT_MESSAGES.get(relative, set())
            if allowed is None:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = _docstrings(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings \
                        and node.value not in allowed and WORDS.search(node.value):
                    found.append(f"{relative}:{node.lineno}: {node.value[:100]!r}")
    return found


class CadNamesNoSkillOrPlugin(unittest.TestCase):
    def test_no_message_names_a_skill_or_the_plugin(self) -> None:
        self.assertEqual(offenders(), [], "a cad package's message names a skill or the plugin: say what cad does")


if __name__ == "__main__":
    unittest.main()
