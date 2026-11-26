"""Skills and the docs spell the library's names as they are now: no alias of the library's earlier
spellings, among them a document type's operations (``xbf.export(...)``, ``kicad_pcb.drc(...)``: the verbs' now,
``cad.export``, ``cad.kicad.drc``), a file type's call given a shape (``xbf(shape, ...)``: ``cad.save``) and an
integration's function a verb does now (``cad.build123d.dfm(shape)``: ``cad.dfm``).

An alias (``cad._internal.aliases``) is kept out of every document but the migration guide, and an agent
reads the skills each session, so they cut over hard (law 14). The table is read from its source with
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
# The types' operations under their own names, and the file types whose call given a shape writes it: each an
# earlier spelling of a verb's, which warns.
TYPES = r"(?:xbf|model|step|stl|glb|threemf|dxf|urdf|srdf|kicad_pcb|kicad_sch)"
OPERATIONS = re.compile(rf"(?<![\w])(?:cad\.)?{TYPES}\.(?:export|snapshot|inspect|dfm|interference|solve|ranges|"
                        r"validate|drc|erc)\(")
# ``xbf(shape, ...)``, ``step(part, "x.step")``: a call whose first argument is no path (the decorator's,
# ``@step("x.step")`` or ``xbf("XBF/arm.xbf")``, takes a string, or nothing).
CALLED = re.compile(r"(?<![@\w.])(?:cad\.)?(?:xbf|model|step|stl|glb|threemf|dxf)\(\s*(?!(?:out|name)=)"
                    r"[A-Za-z_][\w.]+(?:\([^()]*\))?\s*[,)]")
# What else is read beside the skills: the documents a person reads (the migration guides, which name the earlier
# spellings on purpose, aside). The sample models are no test's to read (tests/python/global/test_tests_are_self_contained.py).
DOCS = [REPO_ROOT / "README.md", REPO_ROOT / "docs" / "install.md", REPO_ROOT / "packages" / "cad" / "README.md",
        *sorted((REPO_ROOT / "apps" / "docs" / "content").rglob("*.md")),
        *sorted((REPO_ROOT / "packages" / "cad" / "src" / "cad_server" / "engine" / "docs").glob("*.md"))]


def _tables() -> tuple[dict[str, dict[str, str]], dict[str, str], dict[str, dict[str, tuple[str, str]]]]:
    found: dict[str, object] = {}
    for node in ast.parse(ALIASES.read_text(encoding="utf-8")).body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(target, ast.Name) and target.id in ("NAME_ALIASES", "MODULE_ALIASES", "VERB_ALIASES") \
                and node.value is not None:
            found[target.id] = ast.literal_eval(node.value)
    return found["NAME_ALIASES"], found["MODULE_ALIASES"], found["VERB_ALIASES"]  # type: ignore[return-value]


def _patterns() -> list[tuple[str, re.Pattern[str]]]:
    """Each alias's spellings: its dotted path (``cad.read_step``, ``cad.ap242``); a name a ``from cad import``
    line lists; and, for a name no word of prose could be (``read_step``, ``ValidationResult``), the name alone."""
    names, modules, verbs = _tables()
    found: list[tuple[str, re.Pattern[str]]] = []
    for owner, table in [*names.items(), *verbs.items()]:
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
        names, modules, verbs = _tables()
        self.assertIn("read_step", names["cad"])
        self.assertIn("cad.ap242", modules)
        self.assertIn("dfm", verbs["cad.build123d"])
        self.assertTrue(any(pattern.search("from cad.build123d import dfm") for _old, pattern in _patterns()))

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

    def test_no_skill_or_document_spells_a_type_s_operation_or_a_shape_s_call(self) -> None:
        found = []
        paths = [*sorted(SKILLS.rglob("*.md")), *DOCS]
        self.assertGreater(len(paths), 40)
        for path in paths:
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if OPERATIONS.search(line) or CALLED.search(line):
                    found.append(f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()[:100]}")
        self.assertEqual([], found, "an earlier spelling of a verb, which warns: cad.export, cad.inspect, cad.snapshot, "
                                    "cad.dfm, cad.fea, cad.kicad.drc, cad.kicad.erc; a shape's .xbf is cad.save")

    def test_the_patterns_tell_an_earlier_spelling_from_a_declaration(self) -> None:
        for line in ("xbf.export(handle, 'a.step')", "cad.kicad_pcb.drc(BOARD)", "step.dfm(path, process='cnc')",
                     "xbf(shape, name='plate')", "step(part, 'x.step')", "cad.xbf(box, 'box.xbf')"):
            with self.subTest(line=line):
                self.assertTrue(OPERATIONS.search(line) or CALLED.search(line))
        for line in ('@xbf("XBF/arm.xbf")', "@step", "@xbf", 'xbf("XBF/arm.xbf")(arm)', "cad.export(handle, 'a.step')",
                     "xbf.read(path)", "xbf.param('wall', 2)", "kicad_pcb.edit(BOARD)", "step.read('v.step')",
                     "a step(s)", "@stl(out='a.stl')", "step(out='arm.step', name='arm')"):
            with self.subTest(line=line):
                self.assertFalse(OPERATIONS.search(line) or CALLED.search(line))


if __name__ == "__main__":
    unittest.main()
