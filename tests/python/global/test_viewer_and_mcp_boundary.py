"""The CAD Viewer's backend and the CAD app's server are leaves of cadgen.

Outside `cadgen/viewer/`, `cadgen/mcp/` and the commands that start them (`cli/viewer.py`,
`cli/viewer_stop.py`, `cli/mcp.py`, which the CLI registry names by string), no cadgen module
imports either -- except `cadgen.viewer.recents`, the state directory's one definition. CI
leans on this: a change confined to one of them runs only the tests that reach it
(scripts/github-workflows/select_checks.py), so an import across the line has to move the
line there too.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import unittest

from tests.python.support.paths import REPO_ROOT

_spec = importlib.util.spec_from_file_location("select_checks", REPO_ROOT / "scripts/github-workflows/select_checks.py")
selector = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("select_checks", selector)
_spec.loader.exec_module(selector)

CADGEN = REPO_ROOT / selector.CADGEN_SRC
SHELLS = {"cli/viewer.py", "cli/viewer_stop.py", "cli/mcp.py"}
ALLOWED = {"cadgen.viewer.recents"}


def inside(relative: str) -> bool:
    return relative.startswith(("viewer/", "mcp/")) or relative in SHELLS


def leaf(name: str) -> bool:
    if any(name == allowed or name.startswith(allowed + ".") for allowed in ALLOWED):
        return False
    return name in ("cadgen.viewer", "cadgen.mcp") or name.startswith(("cadgen.viewer.", "cadgen.mcp."))


def references(path, relative: str) -> list[str]:
    """Every module the file imports, and every string naming a viewer or MCP module."""
    package = ["cadgen", *relative.split("/")[:-1]]
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join(base + ([node.module] if node.module else []))
            found += [module] + [f"{module}.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and leaf(node.value.split()[0] if node.value.split() else ""):
            found.append(node.value.split()[0])
    return found


class ViewerAndMcpAreLeaves(unittest.TestCase):
    def test_nothing_outside_them_imports_them(self):
        offenders = []
        for path in sorted(CADGEN.rglob("*.py")):
            relative = path.relative_to(CADGEN).as_posix()
            if inside(relative):
                continue
            offenders += [f"{relative} -> {name}" for name in references(path, relative) if leaf(name)]
        self.assertEqual(offenders, [], "outside the viewer and MCP leaves, only cadgen.viewer.recents may be imported")

    def test_the_selector_draws_the_same_line(self):
        self.assertEqual(set(selector.VIEWER_CODE), {f"{selector.CADGEN_SRC}/viewer/**",
                                                     *(f"{selector.CADGEN_SRC}/{shell}" for shell in SHELLS - {"cli/mcp.py"})})
        self.assertEqual(set(selector.MCP_CODE), {f"{selector.CADGEN_SRC}/mcp/**", f"{selector.CADGEN_SRC}/cli/mcp.py"})
        self.assertEqual(set(selector.VIEWER_SHARED), {f"{selector.CADGEN_SRC}/viewer/__init__.py",
                                                       f"{selector.CADGEN_SRC}/viewer/recents.py"})

    def test_a_change_to_a_leaf_reaches_every_test_that_imports_it(self):
        viewer = set(selector._viewer_change("").cadgen)
        mcp = set(selector._mcp_change("").cadgen)
        for path in sorted((REPO_ROOT / selector.CADGEN_SUITE).rglob("test*.py")):
            relative = path.relative_to(REPO_ROOT).as_posix()
            names = [name for name in references(path, "tests/x.py") if leaf(name) or name.startswith("cadgen.cli.")]
            with self.subTest(test=relative):
                if any(name.startswith(("cadgen.viewer", "cadgen.cli.viewer")) for name in names):
                    self.assertIn(relative, viewer)
                if any(name.startswith(("cadgen.mcp", "cadgen.cli.mcp")) for name in names):
                    self.assertIn(relative, mcp)
                    self.assertIn(relative, viewer)


if __name__ == "__main__":
    unittest.main()
