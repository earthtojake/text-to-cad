"""No path loops between the hosted install command, ``cad plugin install``, cad's plugin switch and ``cad update``.

The one way to a loop is a command that starts what started it. On 0.11.12 and 0.11.13, ``cad plugin update`` downloads
and runs the hosted install command (``scripts/install/install.py``), and their server runs that command by itself. So
the hosted command never starts ``cad plugin update`` but as the switch (``cad plugin update auto on``, which keeps a
setting and starts nothing on any release) and never ``cad setup`` (the bridge's, which runs it); else of ``cad plugin``
it starts ``install`` alone, and ``install --help`` before it, which argparse answers on every release, running nothing;
and what cad runs for the plugin (``cad_server/plugin/``, ``cad_server/cli/plugin.py``,
``_internal/plugin_catch_up.py``) never reaches the hosted command, nor cad's own update, and starts cad itself in one
place alone: the server's ``cad plugin install``. Read off the sources, so a change that opens an edge fails here before
any run of it. That the hosted command run against a cad of 0.11.13 never loops is ``test_install_script.py``'s
(``test_run_against_0_11_13_nothing_loops``).
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT

SERVER = REPO_ROOT / "packages" / "cad" / "src" / "cad_server"
# What cad runs for the plugin, and whatever runs it.
PLUGIN = sorted((SERVER / "plugin").glob("*.py")) + [SERVER / "cli" / "plugin.py",
                                                    SERVER / "_internal" / "plugin_catch_up.py"]
SCRIPT = REPO_ROOT / "scripts" / "install" / "install.py"
# The hosted install command, by any of its names; and what runs it (``install_script.run`` is gone and stays gone).
HOSTED = ("texttocad.dev", "install.sh", "install.ps1", "install_script.run", "INSTALLER_WINDOWS")
# What of ``install_script`` the plugin's code may read: the variable that silences the server in a test, cad's mark,
# and whether the bridge owes its own run -- never the command it runs (``installer``) nor a way to start it.
INSTALL_SCRIPT_NAMES = {"INSTALLER_ENV", "BY_CAD_ENV", "read", "OWED"}
# What of ``auto_update`` begins or carries out cad's own update: none of it is the plugin's to call.
UPDATING = {"trigger", "begin", "asked", "helper_command", "_start", "_begin_due", "tend", "at_start", "update_uv"}


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _words(node: ast.AST) -> list:
    """A list's or a tuple's constant strings, in order (anything else as None)."""
    return [elt.value if isinstance(elt, ast.Constant) and isinstance(elt.value, str) else None
            for elt in getattr(node, "elts", [])]


class ThePluginsCodeNeverReachesTheHostedCommandOrCadsUpdate(unittest.TestCase):
    def test_it_names_no_hosted_command_and_runs_none(self) -> None:
        for path in PLUGIN:
            text = path.read_text(encoding="utf-8")
            for name in HOSTED:
                self.assertNotIn(name, text, f"{path.relative_to(REPO_ROOT)}: {name}")
            for node in ast.walk(_tree(path)):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    where = f"{path.relative_to(REPO_ROOT)}:{node.lineno}"
                    if node.value.id == "install_script":
                        self.assertIn(node.attr, INSTALL_SCRIPT_NAMES, where)
                    if node.value.id == "auto_update":
                        self.assertNotIn(node.attr, UPDATING, where)
                if isinstance(node, ast.ImportFrom):
                    where = f"{path.relative_to(REPO_ROOT)}:{node.lineno}"
                    names = {alias.name for alias in node.names}
                    if node.module == "cad_server._internal.install_script":
                        self.assertLessEqual(names, INSTALL_SCRIPT_NAMES, where)
                    self.assertNotEqual(node.module, "cad_server.cli.update", where)
                    if node.module == "cad_server.cli":
                        self.assertFalse(names & {"main", "update", "setup"}, where)
                if isinstance(node, ast.Import):
                    self.assertNotIn("cad_server.cli.update", {alias.name for alias in node.names}, path)

    def test_cad_itself_is_started_in_one_place_and_only_as_cad_plugin_install(self) -> None:
        """A ``cad update``, a ``cad plugin update`` (on an older cad, the hosted command) or a ``cad setup`` would
        need cad's own command: ``auto_update.tool_command`` or this Python. The server's run is the one use of it."""
        started = []
        for path in PLUGIN:
            for node in ast.walk(_tree(path)):
                where = f"{path.relative_to(REPO_ROOT)}:{getattr(node, 'lineno', '?')}"
                if isinstance(node, ast.Attribute) and node.attr == "executable" and \
                        isinstance(node.value, ast.Name) and node.value.id == "sys":
                    self.fail(f"{where}: sys.executable starts a Python, and with it cad")
                if isinstance(node, ast.List) and node.elts and any(
                        isinstance(part, ast.Attribute) and part.attr == "tool_command"
                        for part in ast.walk(node.elts[0])):
                    started.append((path.name, _words(node)[1:]))
                if isinstance(node, ast.Attribute) and node.attr == "tool_command":
                    self.assertEqual(path.name, "plugin_catch_up.py", where)
        self.assertEqual(started, [("plugin_catch_up.py", ["plugin", "install"])])


class TheHostedCommandNeverStartsWhatRunsIt(unittest.TestCase):
    def test_it_starts_cad_plugin_update_only_as_the_switch_and_never_cad_setup(self) -> None:
        commands = [_words(node) for node in ast.walk(_tree(SCRIPT)) if isinstance(node, (ast.List, ast.Tuple))]
        plugin = [words for words in commands if "plugin" in words]
        self.assertTrue(plugin, "the hand-over is there to check")
        for words in plugin:
            after = words[words.index("plugin") + 1:]
            # `install --help` is the question asked before the hand-over: argparse answers it, and nothing runs.
            self.assertIn(after, (["install"], ["install", "--help"], ["update", "auto", "on"]), words)
        self.assertEqual([words for words in commands if "setup" in words], [])
        self.assertEqual(sum(words[words.index("plugin") + 1:] == ["update", "auto", "on"] for words in plugin), 1)


if __name__ == "__main__":
    unittest.main()
