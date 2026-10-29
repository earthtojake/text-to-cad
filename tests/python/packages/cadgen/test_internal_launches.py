"""cadgen starts its own processes as ``python -P -m cadgen…``.

``python -m`` puts the folder a process runs in first on its import path. cadgen's
processes (the engine's build workers, its document readers and render processes, the
telemetry sender) run in a project or in the system temp folder: whatever other
programs, or on a shared ``/tmp`` other users, leave there must never stand in for
cadgen's own modules. ``-P`` keeps that folder off the path; PYTHONPATH and
the installation still apply. ``test_daemon_pool`` runs a worker beside a shadow package;
this pins every other launch to the same flag.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[4] / "packages" / "cadgen" / "src" / "cadgen"
LAUNCH = re.compile(r'"-m",\s*f?"cadgen')


def flagged_command_prefix(text: str, line: int) -> bool:
    """A module appended to an interpreter command whose initial arguments include -P."""
    tree = ast.parse(text)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.AugAssign) and node.lineno == line and isinstance(node.target, ast.Name)):
            continue
        scope = parents.get(node)
        while scope is not None and not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = parents.get(scope)
        if scope is None:
            return False
        initialized = [statement for statement in ast.walk(scope) if isinstance(statement, ast.Assign)
                       and statement.lineno < line and any(isinstance(target, ast.Name)
                       and target.id == node.target.id for target in statement.targets)]
        if not initialized:
            return False
        value = max(initialized, key=lambda statement: statement.lineno).value
        if isinstance(value, (ast.List, ast.Tuple)):
            return any(isinstance(argument, ast.Constant) and argument.value == "-P" for argument in value.elts)
    return False


class InternalLaunches(unittest.TestCase):
    def test_every_cadgen_launch_keeps_its_working_folder_off_the_import_path(self) -> None:
        launches, unflagged = 0, []
        for path in sorted(SOURCE.rglob("*.py")):
            if "_runtime" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for match in LAUNCH.finditer(text):
                launches += 1
                line = text.count(chr(10), 0, match.start()) + 1
                if not text[:match.start()].rstrip().endswith('"-P",') and not flagged_command_prefix(text, line):
                    unflagged.append(f"{path.relative_to(SOURCE)}:{line}")
        self.assertGreater(launches, 0, "found no launch to check: the pattern no longer matches cadgen's source")
        self.assertEqual([], unflagged, "a cadgen launch without -P")


if __name__ == "__main__":
    unittest.main()
