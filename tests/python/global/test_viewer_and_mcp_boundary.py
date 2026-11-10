"""The CAD Viewer's backend and the CAD app's server are leaves of the server.

Outside `cad_server/viewer/`, `cad_server/mcp/` and the commands that start them (`cli/viewer.py`,
`cli/mcp.py`, which the CLI registry names by string), no module of the server's
imports either (the library imports nothing of the server's at all: test_core_imports)
-- except the injected `_internal/engine_host.py` composition root
and `cad_server.viewer.recents`, the state directory's one definition.
"""
from __future__ import annotations

import ast
import unittest

from tests.python.support.paths import REPO_ROOT

SERVER = REPO_ROOT / "packages/cad-server/src/cad_server"
SHELLS = {"cli/viewer.py"}
ALLOWED = {"cad_server.viewer.recents"}


def inside(relative: str) -> bool:
    return relative.startswith(("viewer/", "mcp/")) or relative in SHELLS


def leaf(name: str) -> bool:
    if any(name == allowed or name.startswith(allowed + ".") for allowed in ALLOWED):
        return False
    return name in ("cad_server.viewer", "cad_server.mcp") or name.startswith(("cad_server.viewer.", "cad_server.mcp."))


def references(path, relative: str) -> list[str]:
    """Every module the file imports, and every string naming a viewer or MCP module."""
    package = ["cad_server", *relative.split("/")[:-1]]
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
        for path in sorted(SERVER.rglob("*.py")):
            relative = path.relative_to(SERVER).as_posix()
            if inside(relative) or relative == "_internal/engine_host.py":
                continue
            offenders += [f"{relative} -> {name}" for name in references(path, relative) if leaf(name)]
        self.assertEqual(offenders, [], "only the application composition root may import viewer/MCP leaves")


if __name__ == "__main__":
    unittest.main()
