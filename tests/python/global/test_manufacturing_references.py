"""What the docs say of a manufacturing check is what the check has.

An agent runs the CAD skill's manufacturing references verbatim and keys on the codes they name; the library's
README and the checks' own README name them too. A flag renamed or a rule retired leaves the page confidently
teaching it. So: every ``--flag`` a manufacturing reference names is one a ``dfm`` command's parser takes, and
every ``<process>.<name>`` these pages name in code is a rule's id, a finding's code of that process, or a name
of its module. Nothing is measured: the parsers and the rule tables are the type side's, the standard library
alone.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.python.support.paths import add_sources, repo_path

add_sources()

from cad._internal import dfm  # noqa: E402
from cad_server import cli  # noqa: E402

REFERENCES = sorted(Path(repo_path("skills/cad/references")).glob("manufacturing-*.md"))
#: The pages that name rule ids and finding codes: the references, the skill, the library's README and the
#: checks' own README.
PAGES = (*REFERENCES, Path(repo_path("skills/cad/SKILL.md")),
         Path(repo_path("packages/cad/README.md")),
         Path(repo_path("packages/cad/src/cad/_internal/dfm/README.md")))
#: The types that answer ``dfm``: a B-rep's, a mesh's, a cut file's.
TYPES = ("model", "step", "xbf", "stl", "threemf", "glb", "dxf")

FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")
#: ``cnc.hole_depth`` in code: a whole backticked name, or one of several a backticked run lists.
NAMED = re.compile(r"(?<![\w./-])(cnc|sheet|molding|printing)\.([a-z][a-z0-9_]*)(?![\w(])")
CODE = re.compile(r"`([^`\n]+)`")


def _flags() -> set[str]:
    found: set[str] = set()
    for document_type in TYPES:
        parser = cli.build_parser_for(f"{document_type} dfm")
        found.update(option for action in parser._actions for option in action.option_strings)
    return found


def _names(process: str) -> set[str]:
    """What ``<process>.`` may be followed by: a rule's id, a finding's code its module writes, or a name the
    module has (``molding.ranked``, ``sheet.RULES``)."""
    module = dfm.module(process)
    source = Path(module.__file__).read_text(encoding="utf-8")
    codes = {match.group(1) for match in re.finditer(rf'"{process}\.([a-z][a-z0-9_]*)"', source)}
    rules = {rule.id.split(".", 1)[1] for rule in module.RULES.rules}
    return codes | rules | set(vars(module))


class ManufacturingReferences(unittest.TestCase):
    def test_every_flag_a_reference_names_is_a_dfm_flag(self) -> None:
        flags = _flags()
        self.assertIn("--process", flags)
        self.assertIn("--strict", flags)
        named = 0
        for path in REFERENCES:
            for flag in sorted(set(FLAG.findall(path.read_text(encoding="utf-8")))):
                named += 1
                with self.subTest(page=path.name, flag=flag):
                    self.assertIn(flag, flags, f"{path.name} names {flag}, which no `cad <type> dfm` takes")
        self.assertGreater(named, 20, "the sweep matched nothing")

    def test_every_rule_and_code_a_page_names_is_one(self) -> None:
        names = {process: _names(process) for process in dfm.PROCESSES}
        named = 0
        for path in PAGES:
            text = path.read_text(encoding="utf-8")
            found = {(process, name) for code in CODE.findall(text) for process, name in NAMED.findall(code)}
            for process, name in sorted(found):
                if name in ("md", "py"):
                    continue  # a file's name
                named += 1
                with self.subTest(page=path.name, name=f"{process}.{name}"):
                    self.assertIn(name, names[process],
                                  f"{path.name} names {process}.{name}: no rule, finding code or name of {process}'s")
        self.assertGreater(named, 60, "the sweep matched nothing")


if __name__ == "__main__":
    unittest.main()
