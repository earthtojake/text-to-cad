"""Every environment variable cad reads is declared once, with who sets it.

The variables had grown to some fifty, read wherever they were needed, with nothing to say which a person may
set, which are a test's and which pass between cad's own processes. ``cad._internal.environment`` is now the
one table of them, each with a tier, and this test holds the table to the source and to what people read:

- a name the distribution's source spells and the table lacks fails, so a variable is added by declaring it;
- a row nothing reads fails, so a retired variable leaves the table with its code;
- the server's README lists the public tier, exactly as the table prints it, and nothing else;
- a skill names only public variables, since a skill is read by an agent on a person's own computer.

Standard library alone.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources, repo_path

add_sources()

from cad._internal import environment, programs  # noqa: E402
from cad.engine import places  # noqa: E402

SOURCE = Path(repo_path("packages/cad/src"))
TABLE = SOURCE / "cad" / "_internal" / "environment.py"
README = SOURCE / "cad_server" / "README.md"
SKILLS = Path(repo_path("skills"))
#: A quoted name in cad's namespace: how the source spells a variable it reads or hands on.
QUOTED = re.compile(r"""["'](CAD(?:GEN)?_[A-Z][A-Z0-9_]*)["']""")
ANY = re.compile(r"\bCAD(?:GEN)?_[A-Z][A-Z0-9_]*\b")
#: Quoted names that are Python names in an ``__all__``, never read from the environment.
NOT_VARIABLES = {"CAD_APP_MODULE", "CAD_APP_SHELL", "CAD_CATALOG_SCHEMA_VERSION"}


def _spelled() -> dict[str, set[str]]:
    """Each quoted name of cad's namespace in the distribution's Python, with the files that spell it."""
    found: dict[str, set[str]] = {}
    for path in sorted(SOURCE.rglob("*.py")):
        if path == TABLE or "__pycache__" in path.parts:
            continue
        for name in QUOTED.findall(path.read_text(encoding="utf-8")):
            if name not in NOT_VARIABLES:
                found.setdefault(name, set()).add(path.relative_to(SOURCE).as_posix())
    return found


class EnvironmentVariables(unittest.TestCase):
    def test_every_variable_the_source_spells_is_declared(self) -> None:
        spelled = _spelled()
        self.assertGreater(len(spelled), 30, "the sweep matched almost nothing")
        for name in sorted(set(spelled) - set(environment.VARIABLES)):
            with self.subTest(variable=name):
                self.fail(f"{name} is read in {', '.join(sorted(spelled[name]))} and is not declared in "
                          "cad/_internal/environment.py: declare it there first, with its tier")

    def test_every_declared_variable_is_still_read(self) -> None:
        spelled = _spelled()
        for name in sorted(set(environment.VARIABLES) - set(spelled)):
            with self.subTest(variable=name):
                self.fail(f"{name} is declared and nothing in the distribution spells it: remove its row")

    def test_every_row_has_a_tier_and_a_deprecated_one_says_what_to_do_instead(self) -> None:
        for row in environment.VARIABLES.values():
            with self.subTest(variable=row.name):
                self.assertIn(row.tier, environment.TIERS)
                self.assertTrue(row.summary and not row.summary.endswith("."))
                self.assertEqual(bool(row.instead), row.tier == environment.DEPRECATED)

    def test_a_deprecated_variable_is_said_once_and_still_read(self) -> None:
        # No variable is deprecated today; this holds the path one is retired by.
        row = environment.Variable("CAD_RETIRED_EXAMPLE", environment.DEPRECATED, "an example", instead="use the option")
        said = io.StringIO()
        with mock.patch.dict(environment.VARIABLES, {row.name: row}), mock.patch.dict(os.environ, {row.name: "kept"}), \
                mock.patch.object(environment, "_SAID", set()), contextlib.redirect_stderr(said):
            self.assertEqual(programs._named_outright(row.name), "kept")  # noqa: SLF001
            self.assertEqual(environment.deprecated(row.name), "kept")
        self.assertEqual(said.getvalue().count("CAD_RETIRED_EXAMPLE is deprecated"), 1, said.getvalue())
        self.assertIn("use the option", said.getvalue())

    def test_the_servers_readme_lists_the_public_variables_as_the_table_prints_them(self) -> None:
        text = README.read_text(encoding="utf-8")
        section = text.split("## Environment variables\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn(environment.table(), section, "run `python -m cad._internal.environment` and paste its table")
        public = {row.name for row in environment.named(environment.PUBLIC)}
        self.assertEqual(set(ANY.findall(section)) - {"CAD_ENGINE"}, public)

    def test_every_setting_is_public_of_a_kind_and_keyed_by_the_one_rule(self) -> None:
        settings = environment.settings()
        # Ten today (the server's limits and port, and three of integrations); a new integration adds its own by
        # declaring it, with no change here.
        self.assertGreaterEqual(len(settings), 10, "the sweep found almost no setting")
        for row in settings:
            with self.subTest(variable=row.name):
                self.assertEqual(row.tier, environment.PUBLIC)
                self.assertIn(row.kind, environment.KINDS)
                self.assertEqual(row.key, row.name.removeprefix("CAD_").lower())
                self.assertEqual(row.key, places.setting_key(row.name), "the engine reads it under the same key")
                self.assertIs(environment.setting(row.key), row)
                self.assertIs(environment.setting(row.name), row)
                self.assertIn(f"| `{row.name}` | `{row.key}` |", environment.table())
        for row in environment.VARIABLES.values():
            if not row.setting:
                self.assertEqual((row.key, row.kind, row.at_start), ("", "", False))
        # One set of words for where a value came from and where it is kept, the engine's and the table's.
        self.assertEqual((environment.ENVIRONMENT, environment.SAVED, environment.DEFAULT, environment.SECTION),
                         (places.ENVIRONMENT, places.SAVED, places.DEFAULT, places.CONFIG))
        for name in ("CAD_STATE_DIR", "CAD_CACHE_DIR", "CAD_ENGINE_DIR", "CAD_TELEMETRY", "CAD_UPDATE_CHECK"):
            self.assertFalse(environment.VARIABLES[name].setting, f"{name} stays the environment's alone")

    def test_a_skill_names_only_public_variables(self) -> None:
        public = {row.name for row in environment.named(environment.PUBLIC)}
        pages = sorted(SKILLS.rglob("*.md"))
        # The sweep is held by the pages it read, never by how many variables they name: a skill that names none
        # is the better skill.
        self.assertGreater(len(pages), 40, "the sweep read almost no page")
        for path in pages:
            for name in sorted(set(ANY.findall(path.read_text(encoding="utf-8")))):
                with self.subTest(page=str(path.relative_to(SKILLS)), variable=name):
                    self.assertIn(name, public, f"{name} is not a variable a person sets: a skill names only the "
                                                "public ones (cad/_internal/environment.py)")


if __name__ == "__main__":
    unittest.main()
