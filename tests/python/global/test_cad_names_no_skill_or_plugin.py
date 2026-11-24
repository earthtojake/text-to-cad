"""cad names a skill, an agent app and the plugin in one place: ``cad_server/plugin/``, reached by ``cad plugin``.

text-to-cad's distribution (``packages/cad``: the library, the server and the shim) knows the agent apps, the plugin
and its skills in exactly one package, ``cad_server.plugin``: the table of apps, how the plugin is installed and
updated in each, and which copies of our skills are ours to remove. It is reached only by the ``cad plugin`` command
(``cad_server.cli.plugin``): ``install`` and ``update`` run it, and ``update auto`` says whether the server runs
``update`` once where cad is newer than the release the plugin is up to date for. Everything else in cad says what
cad does without those words (as ``cad_server/mcp/`` is the one place that knows the host:
``test_host_neutral_packages.py``).

So no string a package can print or return -- every string literal in its sources but a docstring -- says "skill"
anywhere outside that package, nor "plugin" but there and where the command needs the word: its own module, its name
and one-line help in the command table, the settings section that keeps its switch, the command words where the
server runs ``cad plugin update``, that switch and its record as ``cad doctor`` reports them, and the telemetry field
that counts how that command's run went. Each of those is listed below, as exact strings wherever it can be. And
nothing but the command imports the package.
"""

from __future__ import annotations

import ast
import re
import unittest

from tests.python.support.paths import PROJECTS

WORDS = re.compile(r"\b(skills?|plugins?)\b", re.IGNORECASE)
SKILL = re.compile(r"\bskills?\b", re.IGNORECASE)
# Strings that are no message, or that name the one command: per file, the exact strings allowed.
NOT_MESSAGES = {
    # BRIDGE-ONLY: the folder 0.10.0 to 0.11.11's setup left in the state folder, which tells a computer its agent apps
    # got text-to-cad from that setup rather than a store alone (``cli.setup.ours``).
    "cad_server/cli/setup.py": {"plugin"},
    # The command's name, its module and its one-line help in the command table, and the command named among those
    # that reach any release's server and that carry no notice (``cad plugin``).
    "cad_server/cli/__init__.py": {"plugin", "cad_server.cli.plugin",
                                   "the plugin in your agent apps: `install` puts it in or updates it; "
                                   "`update auto`: whether cad's updates update it too"},
    # The settings section that keeps the command's switch (``plugin.auto_update``).
    "cad_server/_internal/auto_update.py": {"plugin"},
    # The command words of ``cad plugin install``, which the server runs where cad is newer than the release the plugin
    # is up to date for, and the lines of the server's log that say so: the command by its name, and why it runs.
    "cad_server/_internal/plugin_catch_up.py": {"plugin", "`cad plugin install`",
                                                " is newer than the one the plugin is up to date for: "},
    # ``cad doctor`` names the command's switch as it reports it (``cad plugin update auto``), and its record's line:
    # the line's name, and what it says of the release the plugin is up to date for.
    "cad_server/cli/doctor.py": {"plugin update auto ", "plugin", "the plugin is up to date for cad ",
                                 "no record of the plugin being up to date on this computer"},
    # The ``update`` event's field that says how the command's run after an update went (``plugin``), a name the
    # receiver reads, never a message.
    "cad_server/analytics.py": {"plugin"},
}
# The command's own module: "plugin" anywhere in it (its name, help and lines), "skill" never.
COMMAND = "cad_server/cli/plugin.py"
# The one package that knows the apps, the plugin and its skills: every string of it.
PACKAGE = "cad_server/plugin/"
# How any other module would reach it: an import of the package, or of a module of it, in any spelling.
IMPORTS_PACKAGE = re.compile(r"^\s*(?:from\s+(?:cad_server\.plugin\b|\.+plugin\b)|import\s+cad_server\.plugin\b"
                             r"|from\s+(?:cad_server|\.+)\s+import\s+(?:[^#\n]*,\s*)?plugin\b)"
                             r"|[\"']cad_server\.plugin\b", re.MULTILINE)


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
            if ".egg-info" in relative or relative.startswith(PACKAGE):
                continue
            allowed = NOT_MESSAGES.get(relative, set())
            words = SKILL if relative == COMMAND else WORDS
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = _docstrings(tree)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings \
                        and node.value not in allowed and words.search(node.value):
                    found.append(f"{relative}:{node.lineno}: {node.value[:100]!r}")
    return found


def importers() -> list[str]:
    """The modules outside the package that import it, each with its line: the command's alone may."""
    found = []
    for project in PROJECTS:
        source = project / "src"
        for path in sorted(source.rglob("*.py")):
            relative = path.relative_to(source).as_posix()
            if ".egg-info" in relative or relative.startswith(PACKAGE):
                continue
            text = path.read_text(encoding="utf-8")
            for match in IMPORTS_PACKAGE.finditer(text):
                found.append(f"{relative}:{text.count(chr(10), 0, match.start()) + 1}")
    return found


class CadNamesSkillsAndThePluginInOnePlace(unittest.TestCase):
    def test_no_message_names_a_skill_or_the_plugin_outside_the_package_and_its_command(self) -> None:
        self.assertEqual(offenders(), [], "a cad package's message names a skill, or the plugin outside "
                                          "`cad_server/plugin/` and `cad plugin`: say what cad does")

    def test_only_the_command_imports_the_package(self) -> None:
        found = importers()
        self.assertTrue(found, "the command no longer reaches the package: this looks in the wrong place")
        self.assertEqual({line.rpartition(":")[0] for line in found}, {COMMAND},
                         "`cad_server/plugin/` is reached only by `cad plugin`: " + ", ".join(found))

    def test_the_package_and_the_command_s_module_are_there_to_be_allowed(self) -> None:
        for project in PROJECTS:
            if (project / "src" / "cad_server").is_dir():
                self.assertTrue((project / "src" / COMMAND).is_file(), "the allowance names the command's module")
                self.assertTrue((project / "src" / PACKAGE / "__init__.py").is_file(),
                                "the allowance names the package")
                for relative in NOT_MESSAGES:
                    self.assertTrue((project / "src" / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
