"""Structural invariants for ``cadgen.viewer``.

The viewer server is part of cadgen, so cadgen's own modules are fair game. What
must never happen is the CAD KERNEL loading into the server:

* ``cadgen viewer`` has to start in the time ``cadgen --help`` does. An OCP or
  build123d import at module scope anywhere in the package costs seconds and
  ~300MB before the first request.
* The long-lived server must not hold a kernel it never uses. The one
  kernel-bearing action -- importing a foreign STEP -- is a compile job in
  cadgen's pool (``imports`` submits and waits); no viewer module names the
  build entry point.

Both are checked twice: on the AST (so the offender is named by file and line)
and on ``sys.modules`` after importing the package (so a kernel import that
hides behind a helper cadgen module is still caught).
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

import cadgen.viewer

PACKAGE_DIR = Path(cadgen.viewer.__file__).resolve().parent

# The kernel and its wrappers. ezdxf and shapely are cadgen dependencies too,
# but they are cheap and not what this fence is about; the kernel is.
KERNEL_ROOTS = frozenset({"OCP", "build123d", "cadquery"})


def _python_sources() -> list[Path]:
    return sorted(PACKAGE_DIR.glob("*.py"))


def _module_scope_imports(tree: ast.Module):
    """Yield ``(node, root_module)`` for imports at module scope only."""
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import
                yield node, ""
            elif node.module:
                yield node, node.module.split(".")[0]
        elif isinstance(node, ast.ClassDef):
            # Class bodies execute at import time too.
            for inner in node.body:
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    for alias in getattr(inner, "names", []):
                        yield inner, alias.name.split(".")[0]


class NoKernelInTheServer(unittest.TestCase):
    def test_no_module_imports_the_kernel_at_module_scope(self) -> None:
        offenders = []
        for path in _python_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node, root in _module_scope_imports(tree):
                if root in KERNEL_ROOTS:
                    offenders.append(f"{path.name}:{node.lineno} imports {root}")
        self.assertEqual(
            offenders,
            [],
            "the CAD kernel is imported inside the compile worker's function bodies, "
            "never at module scope: `cadgen viewer` must start without it",
        )

    def test_importing_the_whole_package_leaves_the_kernel_unloaded(self) -> None:
        # In a SUBPROCESS: this test process may already have the kernel loaded
        # from another suite, which would make an in-process sys.modules check
        # meaningless in one direction and a false failure in the other.
        script = (
            "import sys\n"
            "import cadgen.viewer.main, cadgen.viewer.imports\n"
            "import cadgen.viewer.http_app, cadgen.viewer.cadgen_ops, cadgen.viewer.scanner\n"
            "import cadgen.viewer.artifact_status, cadgen.viewer.tess_cache, cadgen.viewer.registry\n"
            "loaded = sorted(m for m in sys.modules if m.split('.')[0] in "
            f"{sorted(KERNEL_ROOTS)!r})\n"
            "print(loaded)\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "[]", completed.stdout)

    def test_no_module_names_the_build_entry_point(self) -> None:
        # The kernel-bearing call has no home in the viewer at all: an import is a
        # compile JOB in cadgen's pool (imports.py submits and waits). A call site
        # here would be a place for the kernel to leak into the server process.
        callers = []
        for path in _python_sources():
            if "step_artifact_cli" in path.read_text(encoding="utf-8"):
                callers.append(path.name)
        self.assertEqual(callers, [])


class NoLookupPathManipulation(unittest.TestCase):
    def test_no_sys_path_or_pythonpath_manipulation(self) -> None:
        # The server is an installed package now; nothing in it has any business
        # touching a lookup path. Matched on the AST, not on text, so a comment
        # that explains the rule does not trip it.
        offenders = []
        for path in _python_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    target = ast.unparse(node.func)
                    if target.startswith("sys.path.") or "addsitedir" in target:
                        offenders.append(f"{path.name}:{node.lineno} {target}")
                elif isinstance(node, ast.Subscript) and "PYTHONPATH" in ast.unparse(node):
                    offenders.append(f"{path.name}:{node.lineno} PYTHONPATH")
        self.assertEqual(offenders, [], "cadgen.viewer must not manipulate any lookup path")


class ShippedRuntimeData(unittest.TestCase):
    def test_collation_table_ships_beside_the_code(self) -> None:
        # collation.json is RUNTIME data, not a fixture: it is package data in
        # pyproject.toml, or the catalog sorts differently installed than in tests.
        table = PACKAGE_DIR / "collation.json"
        self.assertTrue(table.is_file())
        self.assertGreater(table.stat().st_size, 100_000)

    def test_the_package_is_reachable_as_a_module(self) -> None:
        # `python -m cadgen.viewer` is the documented spelling beside the front door.
        self.assertIsNotNone(importlib.util.find_spec("cadgen.viewer.__main__"))

    def test_no_test_files_live_under_the_package(self) -> None:
        strays = [p.name for p in PACKAGE_DIR.glob("test_*.py")]
        strays += [p.name for p in PACKAGE_DIR.glob("*_test.py")]
        self.assertEqual(strays, [])


if __name__ == "__main__":
    unittest.main()
