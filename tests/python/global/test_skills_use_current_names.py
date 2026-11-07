"""Skills spell the library's names as they are now: no alias of the library's earlier spellings.

An alias (``cad._internal.aliases``) is kept out of every document but the migration guide, and an agent
reads the skills each session, so they cut over hard (law 15). The table is read from its source with
``ast``, nothing imported: an alias added to it is held out of every skill the moment it is added.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ALIASES = REPO_ROOT / "packages/cad/src/cad/_internal/aliases.py"
SKILLS = REPO_ROOT / "skills"


def _tables() -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    found: dict[str, object] = {}
    for node in ast.parse(ALIASES.read_text(encoding="utf-8")).body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(target, ast.Name) and target.id in ("NAME_ALIASES", "MODULE_ALIASES") and node.value is not None:
            found[target.id] = ast.literal_eval(node.value)
    return found["NAME_ALIASES"], found["MODULE_ALIASES"]  # type: ignore[return-value]


def _patterns() -> list[tuple[str, re.Pattern[str]]]:
    """Each alias's spellings: its dotted path (``cad.read_step``, ``cad.ap242``); a name a ``from cad import``
    line lists; and, for a name no word of prose could be (``read_step``, ``ValidationResult``), the name alone."""
    names, modules = _tables()
    found: list[tuple[str, re.Pattern[str]]] = []
    for owner, table in names.items():
        for name in table:
            old = f"{owner}.{name}"
            found.append((old, re.compile(rf"(?<![\w.]){re.escape(old)}\b")))
            found.append((old, re.compile(rf"\bfrom {re.escape(owner)} import [^\n`]*\b{re.escape(name)}\b")))
            if "_" in name or name[:1].isupper():
                found.append((old, re.compile(rf"(?<![\w.]){re.escape(name)}\b")))
    for old in modules:
        owner, _, name = old.rpartition(".")
        found.append((old, re.compile(rf"(?<![\w.]){re.escape(old)}\b")))
        found.append((old, re.compile(rf"\bfrom {re.escape(owner)} import [^\n`]*\b{re.escape(name)}\b")))
    return found


class SkillsUseCurrentNamesTest(unittest.TestCase):
    def test_the_alias_table_is_read(self) -> None:
        names, modules = _tables()
        self.assertIn("read_step", names["cad"])
        self.assertIn("cad.ap242", modules)

    def test_no_skill_document_spells_an_alias(self) -> None:
        patterns = _patterns()
        found = []
        for path in sorted(SKILLS.rglob("*.md")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for old, pattern in patterns:
                    if pattern.search(line):
                        found.append(f"{path.relative_to(REPO_ROOT)}:{number}: {old}")
        self.assertEqual([], found, "a skill names an alias of an earlier spelling: use the name it has now "
                                    "(cad._internal.aliases says which); only the migration guide names aliases")


if __name__ == "__main__":
    unittest.main()
