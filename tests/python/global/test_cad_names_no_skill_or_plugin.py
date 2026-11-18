"""cad names no skill, and no plugin but in its one command, ``cad plugin``.

The plugin side knows cad; cad knows only that the install command exists. text-to-cad's distribution
(``packages/cad``: the library, the server and the shim) never names a skill or an app, and its one knowledge of
plugins is ``cad plugin``: ``update`` runs the hosted install command, which installs or updates the plugin in the
agent apps, and ``update auto`` says whether the server runs that command once where cad is newer than the release it
is up to date for. So no string a package can print
or return -- every string literal in its sources but a docstring -- says "skill" anywhere, nor "plugin" but where that
command needs the word: its own module, its name and one-line help in the command table, the settings section that
keeps its switch, the command words where the server runs ``cad plugin update``, that switch and its record as
``cad doctor`` reports them, and the telemetry field that counts how that command's run went. Each of those is listed below,
as exact strings wherever it can be. Everything else says what cad does without the word. The words a format uses for
its own elements (SDF's ``<plugin>``) are not messages.
"""

from __future__ import annotations

import ast
import re
import unittest

from tests.python.support.paths import PROJECTS

WORDS = re.compile(r"\b(skills?|plugins?)\b", re.IGNORECASE)
SKILL = re.compile(r"\bskills?\b", re.IGNORECASE)
# Strings that are no message, or that name the one command: per file, the exact strings allowed (None: every string
# of the file, a format's own word).
NOT_MESSAGES = {
    "cad/sdf/_validation.py": None,  # SDF's <plugin> element: the format's word
    "cad/engine/sdf_source.py": None,  # the same element, read
    # BRIDGE-ONLY: the folder 0.10.0 to 0.11.11's setup left in the state folder, which tells a computer its agent apps
    # got text-to-cad from that setup rather than a store alone (``cli.setup.ours``).
    "cad_server/cli/setup.py": {"plugin"},
    # The command's name, its module and its one-line help in the command table, and the command named among those
    # that reach any release's server and that carry no notice (``cad plugin``).
    "cad_server/cli/__init__.py": {"plugin", "cad_server.cli.plugin",
                                   "the plugin: `update` it now; `update auto`: whether cad's updates do"},
    # The settings section that keeps the command's switch (``plugin.auto_update``).
    "cad_server/_internal/auto_update.py": {"plugin"},
    # The command words of ``cad plugin update``, which the server runs where cad is newer than the release that
    # command is up to date for.
    "cad_server/_internal/plugin_catch_up.py": {"plugin"},
    # ``cad doctor`` names the command's switch as it reports it (``cad plugin update auto``), and its record's line.
    "cad_server/cli/doctor.py": {"plugin update auto ", "plugin"},
    # The ``update`` event's field that says how the command's run after an update went (``plugin``), a name the
    # receiver reads, never a message.
    "cad_server/analytics.py": {"plugin"},
}
# The command's own module: "plugin" anywhere in it (its name, help and lines), "skill" never.
COMMAND = "cad_server/cli/plugin.py"


def _docstrings(tree: ast.AST) -> set[int]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def offenders() -> list[str]:
    found = []
    for project in PROJECTS:
        source = project / "src"
        for path in sorted(source.rglob("*.py")):
            relative = path.relative_to(source).as_posix()
            if ".egg-info" in relative:
                continue
            allowed = NOT_MESSAGES.get(relative, set())
            if allowed is None:
                continue
            words = SKILL if relative == COMMAND else WORDS
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = _docstrings(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings \
                        and node.value not in allowed and words.search(node.value):
                    found.append(f"{relative}:{node.lineno}: {node.value[:100]!r}")
    return found


class CadNamesNoSkillOrPlugin(unittest.TestCase):
    def test_no_message_names_a_skill_or_the_plugin_but_the_one_command(self) -> None:
        self.assertEqual(offenders(), [], "a cad package's message names a skill, or the plugin outside `cad plugin`: "
                                          "say what cad does")

    def test_the_command_s_module_is_there_to_be_allowed(self) -> None:
        for project in PROJECTS:
            if (project / "src" / "cad_server").is_dir():
                self.assertTrue((project / "src" / COMMAND).is_file(), "the allowance names the command's module")
                for relative in NOT_MESSAGES:
                    self.assertTrue((project / "src" / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
