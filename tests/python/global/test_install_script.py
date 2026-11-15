"""The install script: scripts/install/install.py, and the two thin scripts that run it.

Each test runs install.py in a fresh temporary home (HOME, XDG_*, APPDATA) with stand-in programs on PATH --
the agent apps' CLIs, uvx, npx, git -- that record how they were called and change nothing else (git clone writes
a small copy of the plugin). No real app, network or cad runs.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from tests.python.support.paths import REPO_ROOT

INSTALL = REPO_ROOT / "scripts" / "install"
spec = importlib.util.spec_from_file_location("text_to_cad_install", INSTALL / "install.py")
install = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = install
spec.loader.exec_module(install)

LATEST = "a" * 40  # the commit of `latest`, as the stand-in git names it
OURS = "---\nname: {name}\ndescription: x\nmetadata:\n  repository: earthtojake/text-to-cad\n---\n"
THEIRS = "---\nname: {name}\ndescription: someone else's\n---\n"

# A stand-in: records {name, argv} as a JSON line, fails where FAKE_FAIL names it (`name`, or `name:word` for a call
# whose arguments hold that word), for `git clone` writes a small plugin folder with our skills, and for
# `git ls-remote` names the commit LATEST.
STAND_IN = textwrap.dedent('''\
    #!{python}
    import json, os, sys
    from pathlib import Path
    name = Path(sys.argv[0]).name
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({{"name": name, "argv": sys.argv[1:]}}) + "\\n")
    if any(fail == name or (fail.partition(":")[0] == name and fail.partition(":")[2] in sys.argv[1:])
           for fail in os.environ.get("FAKE_FAIL", "").split(",")):
        print(f"{{name}}: something went wrong")
        sys.exit(3)
    if name == "git" and "ls-remote" in sys.argv:
        print("{latest}\trefs/heads/latest")
    if name == "git" and "clone" in sys.argv:
        target = Path(sys.argv[-1])
        (target / ".git").mkdir(parents=True)
        (target / ".git" / "config").write_text('[remote "origin"]\\n\\turl = ' + sys.argv[-2] + "\\n")
        for skill in ("cad", "pcb"):
            (target / "skills" / skill).mkdir(parents=True)
            (target / "skills" / skill / "SKILL.md").write_text(
                f"---\\nname: {{skill}}\\nmetadata:\\n  repository: earthtojake/text-to-cad\\n---\\nnew\\n")
''')


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line")
class InstallScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "log.jsonl"
        self.state = self.home / ".local" / "state" / "cad"
        self.programs("uvx", "git")

    def programs(self, *names: str) -> None:
        for name in names:
            path = self.bin / name
            path.write_text(STAND_IN.format(python=sys.executable, latest=LATEST), encoding="utf-8")
            path.chmod(0o755)

    def write(self, relative: str, value) -> Path:
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        return path

    def environ(self, **extra: str) -> dict:
        return {"HOME": str(self.home), "PATH": str(self.bin), "FAKE_LOG": str(self.log),
                "XDG_CONFIG_HOME": str(self.home / ".config"), "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "APPDATA": str(self.home / "AppData" / "Roaming"), "CODEX_CLI": "codex",
                "CAD_INSTALL_FEED": (self.root / "no-feed.json").as_uri(), **extra}

    def run_install(self, *argv: str, **extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(INSTALL / "install.py"), *argv], env=self.environ(**extra),
                              capture_output=True, text=True, timeout=120)

    def calls(self, name: str = None) -> list:
        lines = self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []
        found = [json.loads(line) for line in lines]
        return [call["argv"] for call in found if name is None or call["name"] == name]

    def desktop(self) -> str:
        """Claude Desktop's config, where install.py looks for it on this platform, relative to the home."""
        return str(install.desktop_config(install.Here(self.environ())).relative_to(self.home))

    def claude_records(self, plugins: dict, catalogs: dict) -> None:
        self.write(".claude/plugins/installed_plugins.json",
                   {"version": 2, "plugins": {key: [{"scope": "user"}] for key in plugins}})
        self.write(".claude/plugins/known_marketplaces.json", {name: {"source": source} for name, source in catalogs.items()})

    def test_a_fresh_computer_gets_cad_and_the_plugin_in_every_app_found(self) -> None:
        self.programs("claude", "codex", "gemini", "grok", "muse")
        (self.home / ".cursor").mkdir()
        (self.home / ".cline").mkdir()
        self.write("feed.json", {"latest": "99.0.0"})
        # Muse has no copy yet: its update fails, and it installs from the `latest` branch fetched once.
        done = self.run_install(CAD_INSTALL_FEED=(self.home / "feed.json").as_uri(), FAKE_FAIL="muse:update")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.calls("uvx"), [[*install.UVX_ARGS, "--refresh-package", "cad-server", "--refresh-package",
                                              "cad", "--from", "cad-server==99.0.0", "cad", "setup"]])
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
                                                ["plugin", "install", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad", "--ref", "latest"],
                                               ["plugin", "add", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("gemini"), [["extensions", "install", install.URL, "--ref", "latest", "--consent"]])
        # Cursor and Grok Build load Claude Code's plugin: none of their own.
        self.assertEqual(self.calls("grok"), [])
        self.assertFalse((self.home / ".cursor/plugins/local/text-to-cad").exists())
        # An agent with no plugin command gets the skills in its own folder, from `latest`.
        self.assertIn("new", (self.home / ".cline/skills/cad/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(self.calls("git")[0][:6], ["clone", "--quiet", "--depth", "1", "--branch", "latest"])
        self.assertEqual(len(self.calls("git")), 1)
        fetched = self.calls("git")[0][-1]
        self.assertEqual(self.calls("muse"), [["plugins", "update", "text-to-cad"], ["plugins", "install", fetched],
                                              ["plugins", "approve", "text-to-cad"]])
        for line in ("Claude Code: installed", "Codex: installed", "Gemini CLI: installed",
                     "Grok Build: skipped: it loads Claude Code's plugin", "Cursor: skipped: it loads Claude Code's plugin",
                     "Cline: installed: 2 skills in ~/.cline/skills", "Muse: installed"):
            self.assertIn(line, done.stdout)
        self.assertIn("Not found here: Qwen Code, Hermes Agent", done.stdout)

    def test_the_feed_never_takes_it_below_its_own_release(self) -> None:
        self.write("feed.json", {"latest": "0.0.1"})
        done = self.run_install(CAD_INSTALL_FEED=(self.home / "feed.json").as_uri())
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"cad-server=={install.FALLBACK}", self.calls("uvx")[0])

    def test_run_again_it_updates_each_app_s_github_copy_with_the_app_s_own_command(self) -> None:
        self.programs("claude", "codex", "gemini")
        github = {"source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}
        self.claude_records({"text-to-cad@earthtojake": 1}, {"earthtojake": github})
        self.write(".codex/config.toml", '[marketplaces.earthtojake]\nsource_type = "git"\n'
                                         'source = "https://github.com/earthtojake/text-to-cad.git"\nref = "latest"\n'
                                         '[plugins."text-to-cad@earthtojake"]\nenabled = true\n')
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json",
                   {"type": "git", "source": install.URL, "ref": "latest"})
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "update", "earthtojake"],
                                                ["plugin", "update", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "upgrade", "earthtojake"],
                                               ["plugin", "add", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("gemini"), [["extensions", "update", "text-to-cad"]])
        for name in ("Claude Code", "Codex", "Gemini CLI"):
            self.assertIn(f"{name}: updated\n", done.stdout)

    def test_hermes_installs_latest_by_its_commit_with_no_override_and_moves_it_only_when_it_changed(self) -> None:
        # Hermes's --ref takes a commit alone, and its default branch is main: the commit of `latest`, no --force.
        self.programs("hermes")
        install_it = [["plugins", "install", "earthtojake/text-to-cad", "--no-enable", "--ref", LATEST],
                      ["plugins", "enable", "text-to-cad", "--no-allow-tool-override"]]
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(["ls-remote", install.URL, "refs/heads/latest"], self.calls("git"))
        self.assertEqual(self.calls("hermes"), install_it)
        self.assertIn("Hermes Agent: installed", done.stdout)
        # Installed at that commit (Hermes's record): nothing to do. At another: removed, then that commit installed.
        self.write(".hermes/plugins/text-to-cad/plugin.json", {"name": "text-to-cad"})
        self.write(".hermes/plugins/.install-metadata.json", {"text-to-cad": {"revision": LATEST, "pinned": True}})
        self.log.unlink()
        self.assertIn("Hermes Agent: updated: already the latest release", self.run_install().stdout)
        self.assertEqual(self.calls("hermes"), [])
        self.write(".hermes/plugins/.install-metadata.json", {"text-to-cad": {"revision": "b" * 40, "pinned": True}})
        self.log.unlink()
        self.assertIn("Hermes Agent: updated\n", self.run_install().stdout)
        self.assertEqual(self.calls("hermes"), [["plugins", "remove", "text-to-cad"], *install_it])
        # No git, no commit: said, and nothing run.
        (self.bin / "git").unlink()
        self.log.unlink()
        self.assertIn("Hermes Agent: skipped: needs git", self.run_install().stdout)
        self.assertEqual(self.calls("hermes"), [])

    def test_without_claude_code_cursor_s_clone_and_grok_s_plugin_are_updated(self) -> None:
        self.programs("grok")
        clone = self.home / ".cursor/plugins/local/text-to-cad"
        self.write(".cursor/plugins/local/text-to-cad/.git/config", f'[remote "origin"]\n\turl = {install.URL}.git\n')
        self.write(".grok/installed-plugins/registry.json", {"repos": {"x": {
            "kind": {"type": "Git", "url": install.URL, "git_ref": "latest"}, "path": "/x",
            "plugins": {"text-to-cad": {"version": "0.11.10"}}}}})
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.calls("grok"), [["plugin", "update", "text-to-cad"]])
        self.assertEqual(self.calls("git"), [["-C", str(clone), "fetch", "--quiet", "--depth", "1", "origin", "latest"],
                                             ["-C", str(clone), "checkout", "--quiet", "--force", "-B", "latest", "FETCH_HEAD"]])
        self.assertIn("Cursor: updated", done.stdout)
        self.assertIn("Grok Build: updated", done.stdout)

    def test_what_past_releases_left_is_removed_and_nothing_else(self) -> None:
        self.programs("claude", "codex", "gemini", "grok", "npx")
        folder = str(self.state / "plugin")
        github = {"source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}
        # Claude Code: 0.10-0.11.10's local catalog and its plugin, and 0.7.6's cad@earthtojake; someone else's plugin.
        self.claude_records({"text-to-cad@text-to-cad": 1, "cad@earthtojake": 1, "other@acme": 1},
                            {"text-to-cad": {"source": "directory", "path": folder}, "earthtojake": github,
                             "acme": {"source": "github", "repo": "acme/plugins"}})
        # Codex: the local catalog's copy, and a copy from OpenAI's directory, which stays.
        self.write(".codex/config.toml", f'[marketplaces.text-to-cad]\nsource_type = "local"\nsource = "{folder}"\n'
                                         '[plugins."text-to-cad@text-to-cad"]\nenabled = true\n'
                                         '[plugins."text-to-cad@openai-curated"]\nenabled = true\n')
        # Gemini CLI: the extension linked to the plugin folder.
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json", {"type": "link", "source": folder})
        # Grok Build: the plugin of 0.5-0.7.6, `cad`, from our repository.
        self.write(".grok/installed-plugins/registry.json", {"repos": {"x": {
            "kind": {"type": "Git", "url": install.URL, "git_ref": ""}, "path": "/x", "plugins": {"cad": {}}}}})
        # Cursor: 0.10-0.11.10's marked plain copy.
        self.write(".cursor/plugins/local/text-to-cad/.text-to-cad-copy", {"from": folder})
        # Claude Desktop: our server beside someone else's, in a file whose formatting must survive.
        desktop = self.write(self.desktop(),
                             '{\n    "mcpServers": {\n        "cad": {"command": "uvx", "args": ["--from", "cad-mcp==0.11.10", '
                             '"cad-mcp"]},\n        "notes": {"command": "notes-server"}\n    },\n    "theme": "dark"\n}\n')
        before = desktop.read_text(encoding="utf-8")
        # Loose skills: ours (current and retired, one a link to ours), and someone else's of a retired name.
        self.write(".agents/skills/cad/SKILL.md", OURS.format(name="cad"))
        self.write(".claude/skills/dxf/SKILL.md", OURS.format(name="dxf"))
        (self.home / ".cursor/skills").mkdir(parents=True)
        (self.home / ".cursor/skills/cad").symlink_to(self.home / ".agents/skills/cad")
        self.write(".codex/skills/urdf/SKILL.md", THEIRS.format(name="urdf"))
        self.write(".agents/.skill-lock.json", {"version": 3, "skills": {
            "cad": {"source": "earthtojake/text-to-cad"}, "urdf": {"source": "someone/robots"},
            "pcb": {"source": "someone/boards"}}})

        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        claude = self.calls("claude")
        self.assertEqual(claude[:4], [["plugin", "uninstall", "text-to-cad@text-to-cad"],
                                      ["plugin", "marketplace", "remove", "text-to-cad"],
                                      ["plugin", "uninstall", "cad@earthtojake"],
                                      ["plugin", "marketplace", "update", "earthtojake"]])
        self.assertEqual(claude[4], ["plugin", "install", "text-to-cad@earthtojake"])
        self.assertNotIn(["plugin", "uninstall", "other@acme"], claude)
        self.assertEqual(self.calls("codex")[:2], [["plugin", "remove", "text-to-cad@text-to-cad"],
                                                   ["plugin", "marketplace", "remove", "text-to-cad"]])
        self.assertFalse(any("openai-curated" in " ".join(argv) for argv in self.calls("codex")))
        self.assertEqual(self.calls("gemini"), [["extensions", "uninstall", "text-to-cad"],
                                                ["extensions", "install", install.URL, "--ref", "latest", "--consent"]])
        self.assertEqual(self.calls("grok"), [["plugin", "uninstall", "cad"]])
        self.assertFalse((self.home / ".cursor/plugins/local/text-to-cad").exists())
        # Claude Desktop: only our member gone, every other byte as it was, the file as it was beside it.
        self.assertEqual(desktop.read_text(encoding="utf-8"),
                         '{\n    "mcpServers": {\n        "notes": {"command": "notes-server"}\n    },\n    "theme": "dark"\n}\n')
        self.assertEqual(Path(f"{desktop}.bak").read_text(encoding="utf-8"), before)
        # Loose skills: ours gone, someone else's kept, the lock likewise; never through `npx skills remove`, which
        # removes by name alone.
        self.assertEqual(self.calls("npx"), [])
        self.assertFalse((self.home / ".agents/skills/cad").exists())
        self.assertFalse((self.home / ".claude/skills/dxf").exists())
        self.assertFalse(os.path.lexists(self.home / ".cursor/skills/cad"))
        self.assertTrue((self.home / ".codex/skills/urdf/SKILL.md").is_file())
        self.assertEqual(list(json.loads((self.home / ".agents/.skill-lock.json").read_text(encoding="utf-8"))["skills"]),
                         ["urdf", "pcb"])
        self.assertIn("Loose skills: removed: 3 old copies of our skills", done.stdout)
        self.assertIn("removed old copies: text-to-cad@text-to-cad, cad@earthtojake", done.stdout)

    def test_someone_else_s_server_and_folder_of_our_names_are_left(self) -> None:
        desktop = self.write(self.desktop(),
                             json.dumps({"mcpServers": {"cad": {"command": "freecad-mcp"}}}))
        before = desktop.read_text(encoding="utf-8")
        self.write(".cursor/plugins/local/text-to-cad/plugin.json", {"name": "text-to-cad"})
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(desktop.read_text(encoding="utf-8"), before)
        self.assertFalse(Path(f"{desktop}.bak").exists())
        self.assertTrue((self.home / ".cursor/plugins/local/text-to-cad/plugin.json").is_file())
        self.assertIn("Cursor: failed: ", done.stdout)
        self.assertIn("holds something else", done.stdout)

    def test_one_app_failing_stops_no_other_and_only_cad_setup_fails_the_run(self) -> None:
        self.programs("codex", "gemini")
        done = self.run_install(FAKE_FAIL="codex")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Codex: failed: `plugin marketplace` said: codex: something went wrong", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)
        done = self.run_install(FAKE_FAIL="uvx")
        self.assertEqual(1, done.returncode)
        self.assertIn("cad setup: failed (exit status 3)", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)

    def test_it_takes_no_options_and_does_nothing_when_given_one(self) -> None:
        # Old releases' docs piped options to install.sh (`sh -s -- --dry-run`, `--uninstall`, `--add X`).
        done = self.run_install("--uninstall")
        self.assertEqual(2, done.returncode)
        self.assertIn("takes no options", done.stderr)
        script = subprocess.run(["/bin/sh", "-s", "--", "--add", "0.11.11"], input=(INSTALL / "install.sh").read_text(encoding="utf-8"),
                                env=self.environ(PATH=f"{self.bin}:/usr/bin:/bin"), capture_output=True, text=True,
                                timeout=60)
        self.assertEqual(2, script.returncode)
        self.assertIn("takes no options", script.stderr)
        self.assertEqual(self.calls(), [])

    def test_install_sh_runs_install_py_with_uv_s_python(self) -> None:
        self.programs("uv")
        script = subprocess.run(["/bin/sh"], input=(INSTALL / "install.sh").read_text(encoding="utf-8"), capture_output=True, text=True,
                                env=self.environ(CAD_INSTALL_PY=str(INSTALL / "install.py"), PATH=f"{self.bin}:/usr/bin:/bin"),
                                timeout=60)
        self.assertEqual(0, script.returncode, script.stderr)
        run = self.calls("uv")[0]
        self.assertEqual(run[:-1], ["run", "--no-config", "--managed-python", "--python", "3.14", "--no-project"])
        self.assertEqual(Path(run[-1]).name, "install.py")

    def test_the_development_install_puts_the_checkout_in_place_of_the_published_copy(self) -> None:
        dev_spec = importlib.util.spec_from_file_location("text_to_cad_dev_install", INSTALL / "dev_install.py")
        dev_install = importlib.util.module_from_spec(dev_spec)
        dev_spec.loader.exec_module(dev_install)
        folder = self.root / "dev-plugin" / "text-to-cad"
        release = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        dev_install.assemble(folder, f"{release}-dev.1", "/venv/bin/python")
        self.assertEqual(json.loads((folder / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))["name"], "earthtojake-dev")
        # Every server entry runs the checkout's interpreter under a bare command: Codex reads the Agent Plugins
        # standard's mcp.json first and drops, with no error, a server whose command is a path.
        for config in ("mcp.json", "codex.mcp.json", "cursor.mcp.json"):
            server = json.loads((folder / config).read_text(encoding="utf-8"))["mcpServers"]["cad"]
            self.assertEqual((server["command"], server["args"][-3:]), ("uv", ["/venv/bin/python", "--module", "cad_mcp"]))
        skill = (folder / "skills/cad/SKILL.md").read_text(encoding="utf-8")
        self.assertNotRegex(skill, rf"cad \+{release}(?!-dev)")
        # The published copy goes; the folder's catalog comes in.
        self.programs("claude")
        self.claude_records({"text-to-cad@earthtojake": 1},
                            {"earthtojake": {"source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}})
        source = install.Source(folder=folder, catalog=install.DEV_CATALOG, skills_dir=folder / "skills")
        claude = [app for app in install.APPS if app.key == "claude"]
        lines = install.install_apps(install.Here(self.environ()), source, claude)
        self.assertEqual(self.calls("claude"), [["plugin", "uninstall", "text-to-cad@earthtojake"],
                                                ["plugin", "marketplace", "remove", "earthtojake"],
                                                ["plugin", "marketplace", "add", str(folder)],
                                                ["plugin", "install", "text-to-cad@earthtojake-dev"]])
        self.assertIn("Claude Code: installed (removed old copies: text-to-cad@earthtojake)", lines)


if __name__ == "__main__":
    unittest.main()
