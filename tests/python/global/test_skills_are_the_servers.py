"""The skills the server installs are this repository's: ``providers.SKILLS`` is ``skills/*/SKILL.md``.

The server puts ``SKILLS`` in every agent without a plugin and deletes ``RETIRED_SKILLS`` (an earlier
release's); a skill added, renamed or removed here without the table is one an agent never gets or one
it keeps after it is gone. A policy test, so any change under ``skills/`` runs it. The tables are read
from their source with ``ast``, nothing imported.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROVIDERS = REPO_ROOT / "packages/cad-server/src/cad_server/_internal/providers.py"


def _tables() -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    for node in ast.parse(PROVIDERS.read_text(encoding="utf-8")).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for target in targets:
            if isinstance(target, ast.Name) and target.id in ("SKILLS", "RETIRED_SKILLS") and node.value is not None:
                found[target.id] = tuple(ast.literal_eval(node.value))
    return found


class SkillsAreTheServers(unittest.TestCase):
    def test_the_skills_are_this_repository_s(self) -> None:
        tables = _tables()
        self.assertEqual(list(tables["SKILLS"]), sorted(path.parent.name for path in (REPO_ROOT / "skills").glob("*/SKILL.md")))
        self.assertFalse(set(tables["RETIRED_SKILLS"]) & set(tables["SKILLS"]))


if __name__ == "__main__":
    unittest.main()
