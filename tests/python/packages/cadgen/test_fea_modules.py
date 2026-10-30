"""The fea package's own rules: parsing imports nothing heavy, and no module reaches into another's private names.
Stdlib only."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tests.python.support.fea_fixtures import heavy_at_import

FEA = Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src" / "cadgen" / "_internal" / "fea"


class StdlibAtImport(unittest.TestCase):
    def test_the_study_the_checks_and_the_static_module_load_without_the_solver_stack(self):
        # A malformed study fails before numpy, scipy, netgen or OCP is imported.
        modules = ("cadgen._internal.fea.study", "cadgen._internal.fea.checks", "cadgen._internal.fea.static")
        self.assertEqual(heavy_at_import(*modules), "")


class PrivateNames(unittest.TestCase):
    """No fea module reaches into another's private names: each shares what others use under a public name."""

    def test_no_module_imports_or_reads_another_modules_private_name(self):
        found = []
        for path in sorted(FEA.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            own = "cadgen._internal." + ".".join(path.relative_to(FEA.parent).with_suffix("").parts)
            modules = {}  # a name bound to a cadgen module in this file -> that module
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("cadgen"):
                    for alias in node.names:
                        if alias.name.startswith("_") and not alias.name.startswith("__") and node.module != own:
                            found.append(f"{path.name}:{node.lineno} from {node.module} import {alias.name}")
                        modules[alias.asname or alias.name] = f"{node.module}.{alias.name}"
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("cadgen"):
                            modules[alias.asname or alias.name.split(".")[0]] = alias.name
            for node in ast.walk(tree):
                if (isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__")
                        and isinstance(node.value, ast.Name) and node.value.id in modules):
                    found.append(f"{path.name}:{node.lineno} {node.value.id}.{node.attr}")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
