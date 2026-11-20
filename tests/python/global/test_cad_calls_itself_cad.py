"""The cad packages call themselves cad, never text-to-cad.

text-to-cad is the product: the plugin, its skills and its install command. The distribution (``packages/cad``: the
library, the server and the shim) is cad, and a person who uses cad alone never meets the product's
name in what it prints or returns: "cad 0.11.11 is not installed on this computer.", never "text-to-cad 0.11.11".
So no string literal in their sources but a docstring contains "text-to-cad", in any case, but in an address or an
identifier that cannot change: the repository's URL and the XML namespaces earlier files carry.

One package is the product's side inside cad: ``cad_server/plugin/``, which ``cad plugin`` runs to put the plugin in the
agent apps. The plugin is named text-to-cad in every app, and so are its repository, its catalogs and the marks its
copies carry, so that package names it; nothing else does (``test_cad_names_no_skill_or_plugin.py`` holds that it is
the one place that knows the plugin).
"""

from __future__ import annotations

import ast
import re
import unittest

from tests.python.support.paths import PROJECTS

NAME = re.compile(r"text-to-cad", re.IGNORECASE)
# Addresses and identifiers that keep the name: the repository (a migration guide's link, the manufacturing checks'
# source), and the XML namespace a URDF of an earlier release declares.
KEPT = re.compile(r"github\.com/earthtojake/text-to-cad|https://text-to-cad\.dev/urdf", re.IGNORECASE)
# The one package that installs the plugin in the agent apps, where the plugin's name is its name.
PLUGIN_PACKAGE = "cad_server/plugin/"


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
            if ".egg-info" in relative or relative.startswith(PLUGIN_PACKAGE):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = _docstrings(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings \
                        and NAME.search(KEPT.sub("", node.value)):
                    found.append(f"{relative}:{node.lineno}: {node.value[:100]!r}")
    return found


class CadCallsItselfCad(unittest.TestCase):
    def test_no_message_calls_a_package_text_to_cad(self) -> None:
        self.assertEqual(offenders(), [], "a cad package calls itself text-to-cad: say cad (or cad-server, the "
                                          "package to install)")

    def test_the_package_that_names_the_plugin_is_there_to_be_left_out(self) -> None:
        for project in PROJECTS:
            if (project / "src" / "cad_server").is_dir():
                self.assertTrue((project / "src" / PLUGIN_PACKAGE / "__init__.py").is_file(), PLUGIN_PACKAGE)


if __name__ == "__main__":
    unittest.main()
