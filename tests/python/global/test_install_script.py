"""The install script: scripts/install/install.py, and the two thin scripts that run it.

Each test runs install.py in a fresh temporary home (HOME, XDG_*, APPDATA) with stand-in programs on PATH --
the agent apps' CLIs, uvx, uv, npx, git -- that record how they were called and change nothing else (git clone
writes a small copy of the plugin; gemini's uninstall removes its extension's folder). No real app, network or cad
runs: PATH holds only the stand-ins, install.py is told not to search Homebrew's or npm's folders or app bundles
(CAD_INSTALL_PATH_ONLY), and every proxy is a closed port.
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
# A skill of 0.5.0-0.8.4: no metadata, our provenance line in its body.
OURS_OLD = "---\nname: {name}\ndescription: x\nlicense: MIT\n---\n\n# X\n\n" + install.PROVENANCE_LINE + "\n"
THEIRS = "---\nname: {name}\ndescription: someone else's\n---\n"

# A stand-in: records {name, argv} as a JSON line; fails (exit FAKE_EXIT, default 1) where FAKE_FAIL names it
# (`name`, or `name:word` for a call whose arguments hold that word); `git clone` writes a small plugin folder with our
# skills, `git ls-remote` names the commit LATEST, `git status` prints FAKE_GIT_STATUS (a clean clone of `latest` by
# default); `uv --version` says FAKE_UV_VERSION; `gemini extensions uninstall <name>` removes that extension's folder,
# and, with FAKE_GEMINI_RECORD, `gemini extensions install <url> --ref <ref>` writes its record. Each call notes its
# folder and Gemini's trust.
STAND_IN = textwrap.dedent('''\
    #!{python}
    import json, os, shutil, sys
    from pathlib import Path
    name = Path(sys.argv[0]).name
    with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps({{"name": name, "argv": sys.argv[1:], "cwd": os.getcwd(),
                               "trust": os.environ.get("GEMINI_CLI_TRUST_WORKSPACE")}}) + "\\n")
    if any(fail == name or (fail.partition(":")[0] == name and fail.partition(":")[2] in sys.argv[1:])
           for fail in os.environ.get("FAKE_FAIL", "").split(",")):
        print(f"{{name}}: something went wrong")
        sys.exit(int(os.environ.get("FAKE_EXIT", "1")))
    if name == "git" and "ls-remote" in sys.argv:
        print("{latest}\\trefs/heads/latest")
    if name == "git" and "status" in sys.argv:
        print(os.environ.get("FAKE_GIT_STATUS", "## latest...origin/latest"))
    if name == "uv" and sys.argv[1:] == ["--version"]:
        print("uv " + os.environ.get("FAKE_UV_VERSION", "0.11.0") + " (stand-in)")
    if name == "gemini" and "uninstall" in sys.argv:
        shutil.rmtree(Path(os.environ["HOME"]) / ".gemini" / "extensions" / sys.argv[-1], ignore_errors=True)
    if name == "gemini" and sys.argv[1:3] == ["extensions", "install"] and os.environ.get("FAKE_GEMINI_RECORD"):
        record = Path(os.environ["HOME"]) / ".gemini" / "extensions" / "text-to-cad" / ".gemini-extension-install.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        ref = sys.argv[sys.argv.index("--ref") + 1]
        record.write_text(json.dumps({{"source": sys.argv[3], "type": "git", "ref": ref}}))
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
        closed = "http://127.0.0.1:9"
        return {"HOME": str(self.home), "PATH": str(self.bin), "FAKE_LOG": str(self.log),
                "XDG_CONFIG_HOME": str(self.home / ".config"), "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "APPDATA": str(self.home / "AppData" / "Roaming"), "CODEX_CLI": "codex", "CAD_INSTALL_PATH_ONLY": "1",
                "https_proxy": closed, "http_proxy": closed, "HTTPS_PROXY": closed, "HTTP_PROXY": closed, "no_proxy": "",
                "CAD_INSTALL_FEED": (self.root / "no-feed.json").as_uri(), **extra}

    def run_install(self, *argv: str, **extra: str) -> subprocess.CompletedProcess:
        if self.log.exists():
            self.log.unlink()
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
                     "Cline: installed: 2 skills in ~/.cline/skills", "Muse: installed",
                     "other supported apps were not found here.", "Start a new session in each app to use it."):
            self.assertIn(line, done.stdout)
        self.assertNotIn("removed", done.stdout)

    def test_the_feed_never_takes_it_below_its_own_release(self) -> None:
        self.write("feed.json", {"latest": "0.0.1"})
        done = self.run_install(CAD_INSTALL_FEED=(self.home / "feed.json").as_uri())
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn(f"cad-server=={install.FALLBACK}", self.calls("uvx")[0])
        # Nothing found, nothing installed: no word of a new session.
        self.assertNotIn("Start a new session", done.stdout)

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
        self.assertEqual(self.calls("gemini"), [["extensions", "uninstall", "text-to-cad"],
                                                ["extensions", "install", install.URL, "--ref", "latest", "--consent"]])
        for name in ("Claude Code", "Codex", "Gemini CLI"):
            self.assertIn(f"{name}: updated\n", done.stdout)

    def test_gemini_s_github_copy_is_installed_again_never_asked_to_update(self) -> None:
        # `extensions update` asks twice and takes no --consent: with no one to answer, it waits for ever.
        self.programs("gemini")
        github = {"type": "git", "source": install.URL, "ref": "latest"}
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json", github)
        done = self.run_install(FAKE_GEMINI_RECORD="1")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn(["extensions", "update", "text-to-cad"], self.calls("gemini"))
        self.assertEqual(self.calls("gemini"), [["extensions", "uninstall", "text-to-cad"],
                                                ["extensions", "install", install.URL, "--ref", "latest", "--consent"]])
        self.assertIn("Gemini CLI: updated\n", done.stdout)
        self.assertEqual([path.name for path in (self.home / ".gemini/extensions").iterdir()], ["text-to-cad"])
        record = self.home / ".gemini/extensions/text-to-cad/.gemini-extension-install.json"
        self.assertEqual(json.loads(record.read_text(encoding="utf-8")), github)

    def test_gemini_s_github_copy_is_put_back_where_installing_it_again_fails(self) -> None:
        self.programs("gemini")
        github = {"type": "git", "source": install.URL, "ref": "latest"}
        record = self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json", github)
        skill = self.write(".gemini/extensions/text-to-cad/skills/cad/SKILL.md", OURS.format(name="cad"))
        enablement = self.write(".gemini/extensions/extension-enablement.json", {"text-to-cad": {"overrides": []}})
        done = self.run_install(FAKE_FAIL="gemini:install", FAKE_GEMINI_RECORD="1")
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertEqual(self.calls("gemini")[0], ["extensions", "uninstall", "text-to-cad"])
        self.assertIn("Gemini CLI: failed", done.stdout)
        self.assertIn("the earlier copy was put back", done.stdout)
        self.assertEqual(json.loads(record.read_text(encoding="utf-8")), github)
        self.assertEqual(skill.read_text(encoding="utf-8"), OURS.format(name="cad"))
        self.assertEqual(json.loads(enablement.read_text(encoding="utf-8")), {"text-to-cad": {"overrides": []}})

    def test_gemini_s_commands_run_in_a_folder_of_their_own_never_the_person_s(self) -> None:
        # Run in the person's folder, `--consent` records it as trusted in Gemini's trustedFolders.json.
        self.programs("gemini")
        person = self.home / "projects"
        person.mkdir()
        if self.log.exists():
            self.log.unlink()
        done = subprocess.run([sys.executable, str(INSTALL / "install.py")], env=self.environ(), cwd=person,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(0, done.returncode, done.stderr)
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json",
                   {"type": "git", "source": install.URL, "ref": "latest"})
        again = subprocess.run([sys.executable, str(INSTALL / "install.py")], env=self.environ(), cwd=person,
                               capture_output=True, text=True, timeout=120)
        self.assertEqual(0, again.returncode, again.stderr)
        found = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        runs = [call for call in found if call["name"] == "gemini"]
        self.assertEqual(len(runs), 3)  # the install, then the uninstall and the install again
        for call in runs:
            with self.subTest(argv=call["argv"]):
                where = Path(call["cwd"]).resolve()
                self.assertNotEqual(where, person.resolve())
                self.assertFalse(where.is_relative_to(self.home.resolve()))
                self.assertFalse(where.exists())  # made for the command, and removed after it
                self.assertEqual(call["trust"], "true")

    def test_a_second_run_removes_nothing_it_installed_and_says_nothing_of_removing(self) -> None:
        (self.home / ".cline").mkdir()
        (self.home / ".hermes").mkdir()
        self.write(".agents/skills/fea/SKILL.md", OURS.format(name="fea"))  # a 0.8.4-0.11.4 loose copy
        first = self.run_install()
        self.assertIn("Loose skills: removed: 1 old copies of our skills, in ~/.agents/skills", first.stdout)
        second = self.run_install()
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertIn("Cline: updated: 2 skills in ~/.cline/skills\n", second.stdout)
        self.assertIn("Hermes Agent: updated: 2 skills in ~/.hermes/skills\n", second.stdout)
        self.assertNotIn("removed", second.stdout)
        self.assertFalse((self.home / ".agents/skills/fea").exists())
        self.assertEqual(sorted(path.name for path in (self.home / ".cline/skills").iterdir()), ["cad", "pcb"])

    def test_a_person_s_own_skill_of_our_name_that_mentions_the_repository_stays(self) -> None:
        mine = ("---\nname: gcode\ndescription: My own G-code notes\n---\n"
                "For modelling parts I use https://github.com/earthtojake/text-to-cad (earthtojake/text-to-cad).\n")
        self.write(".claude/skills/gcode/SKILL.md", mine)
        self.write(".claude/skills/gcode/notes.md", "months of notes\n")
        (self.home / ".cline").mkdir()
        self.write(".cline/skills/cad/SKILL.md", mine.replace("gcode", "cad"))
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual((self.home / ".claude/skills/gcode/SKILL.md").read_text(encoding="utf-8"), mine)
        self.assertTrue((self.home / ".claude/skills/gcode/notes.md").is_file())
        self.assertIn("left cad: someone else's skill of that name", done.stdout)
        self.assertNotIn("new", (self.home / ".cline/skills/cad/SKILL.md").read_text(encoding="utf-8"))

    def test_an_edited_copy_of_ours_is_deleted_and_replaced(self) -> None:
        (self.home / ".cline").mkdir()
        self.run_install()
        # The person edits the copy the first run made (its provenance kept) and adds a file; a 0.8 copy (its
        # provenance line) sits in a retired name.
        edited = self.home / ".cline/skills/cad/SKILL.md"
        edited.write_text(edited.read_text(encoding="utf-8") + "my own change\n", encoding="utf-8")
        self.write(".cline/skills/cad/extra.md", "added by hand\n")
        self.write(".cline/skills/dxf/SKILL.md", OURS_OLD.format(name="dxf"))
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Cline: updated: 2 skills in ~/.cline/skills\n", done.stdout)
        self.assertNotIn("my own change", edited.read_text(encoding="utf-8"))
        self.assertFalse((self.home / ".cline/skills/cad/extra.md").exists())
        self.assertFalse((self.home / ".cline/skills/dxf").exists())
        # Nothing of the old copies is kept anywhere: no folder beside the skills, nothing new in the home.
        self.assertEqual(sorted(path.name for path in (self.home / ".cline/skills").iterdir()), ["cad", "pcb"])
        self.assertEqual(sorted(path.name for path in self.home.iterdir() if path.name.startswith(".text-to-cad")), [])

    def test_github_failing_leaves_every_app_with_what_it_had(self) -> None:
        self.programs("claude", "codex", "gemini")
        folder = str(self.state / "plugin")
        self.claude_records({"text-to-cad@text-to-cad": 1}, {"text-to-cad": {"source": "directory", "path": folder}})
        self.write(".codex/config.toml", f'[marketplaces.text-to-cad]\nsource_type = "local"\nsource = "{folder}"\n'
                                         '[plugins."text-to-cad@text-to-cad"]\nenabled = true\n')
        record = self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json", {"type": "link", "source": folder})
        copy = self.write(".cursor/plugins/local/text-to-cad/.text-to-cad-copy", {"from": folder})
        self.write(".agents/skills/cad/SKILL.md", OURS.format(name="cad"))
        (self.home / ".cline").mkdir()
        old = self.write(".cline/skills/pcb/SKILL.md", OURS.format(name="pcb"))
        done = self.run_install(FAKE_FAIL="claude:add,codex:add,gemini:install,git:clone")
        # Every app it found failed: the run says so, and fails.
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("No app got the plugin", done.stdout)
        self.assertNotIn("Start a new session", done.stdout)
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"]])
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad", "--ref", "latest"]])
        # Gemini CLI's linked extension had to go for ours to come in: it is put back as it was.
        self.assertEqual(self.calls("gemini")[-1][:2], ["extensions", "install"])
        self.assertEqual(json.loads(record.read_text(encoding="utf-8")), {"type": "link", "source": folder})
        self.assertIn("the earlier copy was put back", done.stdout)
        self.assertTrue(copy.is_file())
        self.assertTrue((self.home / ".agents/skills/cad/SKILL.md").is_file())
        self.assertEqual(old.read_text(encoding="utf-8"), OURS.format(name="pcb"))
        for name in ("Claude Code", "Codex", "Gemini CLI", "Cursor", "Cline"):
            self.assertIn(f"{name}: failed", done.stdout)
        # A same-named catalog of ours from elsewhere is replaced only once GitHub answers; where the new one fails,
        # the old one is put back.
        github_main = {"source": "github", "repo": "earthtojake/text-to-cad"}
        self.claude_records({"text-to-cad@earthtojake": 1}, {"earthtojake": github_main})
        done = self.run_install(FAKE_FAIL="git:ls-remote")
        self.assertEqual(self.calls("claude"), [])
        done = self.run_install(FAKE_FAIL="claude:install")
        self.assertEqual(self.calls("claude"), [["plugin", "uninstall", "text-to-cad@earthtojake"],
                                                ["plugin", "marketplace", "remove", "--scope", "user", "earthtojake"],
                                                ["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
                                                ["plugin", "install", "text-to-cad@earthtojake"],
                                                ["plugin", "marketplace", "add", "earthtojake/text-to-cad"],
                                                ["plugin", "install", "text-to-cad@earthtojake"]])

    def test_hermes_gets_the_skills_in_its_own_folder_and_our_old_plugin_goes(self) -> None:
        # Hermes Agent is a skills-folder agent: our skills in $HERMES_HOME/skills, no plugin command of its own.
        self.programs("hermes")
        hermes = self.root / "hermes-home"
        done = self.run_install(HERMES_HOME=str(hermes))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("new", (hermes / "skills/cad/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(self.calls("hermes"), [])
        self.assertIn(f"Hermes Agent: installed: 2 skills in {hermes / 'skills'}", done.stdout)
        # Found by its folder alone too; someone else's plugin of that name stays.
        (self.bin / "hermes").unlink()
        self.write(".hermes/plugins/text-to-cad/plugin.json", {"name": "text-to-cad"})
        self.write(".hermes/plugins/.install-metadata.json", {"text-to-cad": {"source": "someone/text-to-cad"}})
        done = self.run_install()
        self.assertIn("Hermes Agent: installed: 2 skills in ~/.hermes/skills\n", done.stdout)
        self.assertTrue((self.home / ".hermes/skills/pcb/SKILL.md").is_file())
        # Ours, from 0.11.x: without the hermes command the skills still come in, and the line says how to remove it.
        self.write(".hermes/plugins/.install-metadata.json",
                   {"text-to-cad": {"source": "https://github.com/earthtojake/text-to-cad.git", "pinned": True}})
        done = self.run_install()
        self.assertIn("Hermes Agent: updated: 2 skills in ~/.hermes/skills; the old text-to-cad plugin in "
                      "~/.hermes/plugins/text-to-cad stays until the hermes command removes it", done.stdout)
        self.programs("hermes")
        done = self.run_install()
        self.assertEqual(self.calls("hermes"), [["plugins", "remove", "text-to-cad"]])
        self.assertIn("Hermes Agent: updated: 2 skills in ~/.hermes/skills (removed old copies: the text-to-cad plugin)",
                      done.stdout)

    def test_without_claude_code_cursor_s_clean_clone_and_grok_s_plugin_are_updated(self) -> None:
        self.programs("grok")
        clone = self.home / ".cursor/plugins/local/text-to-cad"
        self.write(".cursor/plugins/local/text-to-cad/.git/config", f'[remote "origin"]\n\turl = {install.URL}.git\n')
        self.write(".grok/installed-plugins/registry.json", {"repos": {"x": {
            "kind": {"type": "Git", "url": install.URL, "git_ref": "latest"}, "path": "/x",
            "plugins": {"text-to-cad": {"version": "0.11.10"}}}}})
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.calls("grok"), [["plugin", "update", "text-to-cad"]])
        self.assertEqual(self.calls("git"), [["-C", str(clone), "status", "--porcelain=v1", "--branch"],
                                             ["-C", str(clone), "fetch", "--quiet", "--depth", "1", "origin", "latest"],
                                             ["-C", str(clone), "checkout", "--quiet", "-B", "latest", "FETCH_HEAD"]])
        self.assertIn("Cursor: updated", done.stdout)
        self.assertIn("Grok Build: updated", done.stdout)

    def test_a_cursor_clone_with_work_of_its_own_or_a_link_is_left_alone(self) -> None:
        clone = self.home / ".cursor/plugins/local/text-to-cad"
        self.write(".cursor/plugins/local/text-to-cad/.git/config", f'[remote "origin"]\n\turl = {install.URL}.git\n')
        for status, why in (("## latest...origin/latest\n M skills/cad/SKILL.md", "it has changes not committed"),
                            ("## latest...origin/latest [ahead 1]", "it has commits of its own"),
                            ("## main...origin/main", "it is on main, not latest")):
            done = self.run_install(FAKE_GIT_STATUS=status)
            self.assertEqual(self.calls("git"), [["-C", str(clone), "status", "--porcelain=v1", "--branch"]], status)
            self.assertIn(f"Cursor: skipped: ~/.cursor/plugins/local/text-to-cad left alone: {why}", done.stdout)
        # Where Claude Code has our plugin, a clean clone of ours goes; one with work of its own stays.
        self.programs("claude")
        done = self.run_install(FAKE_GIT_STATUS="## latest...origin/latest\n?? my-notes.md")
        self.assertTrue((clone / ".git/config").is_file())
        self.assertIn("left alone: it has changes not committed", done.stdout)
        # A link there (a checkout of ours, say) is never followed, changed or removed.
        checkout = self.root / "checkout"
        (clone / ".git").rename(self.root / "moved-git")
        clone.rmdir()
        (checkout / ".git").mkdir(parents=True)
        (checkout / ".git/config").write_text(f'[remote "origin"]\n\turl = {install.URL}.git\n', encoding="utf-8")
        clone.symlink_to(checkout)
        for claude in (True, False):
            if not claude:
                (self.bin / "claude").unlink()
            done = self.run_install()
            self.assertTrue(clone.is_symlink())
            self.assertEqual(self.calls("git"), [])
            self.assertIn("~/.cursor/plugins/local/text-to-cad is a link: left alone", done.stdout)

    def test_a_character_the_output_cannot_encode_stops_no_app(self) -> None:
        # Windows captures output in its ANSI code page, which has no ✘: the line is printed with a `?`, and the run
        # goes on to the next app and the loose skills.
        self.programs("claude", "gemini")
        stand_in = self.bin / "claude"
        stand_in.write_text(stand_in.read_text(encoding="utf-8").replace(
            "    sys.exit(int(", "    sys.stdout.flush()\n    sys.stdout.buffer.write('\u2718 Failed to add marketplace\\n'.encode())\n    sys.exit(int(", 1),
            encoding="utf-8")
        done = self.run_install(FAKE_FAIL="claude", PYTHONIOENCODING="cp1252")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertIn("Claude Code: failed: ", done.stdout)
        self.assertIn("? Failed to add marketplace", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)

    def test_what_past_releases_left_is_removed_once_ours_is_in_and_nothing_else(self) -> None:
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
        # Loose skills: ours (current and retired, one a link to ours), and someone else's of a retired name.
        self.write(".agents/skills/cad/SKILL.md", OURS.format(name="cad"))
        self.write(".claude/skills/dxf/SKILL.md", OURS_OLD.format(name="dxf"))
        (self.home / ".cursor/skills").mkdir(parents=True)
        (self.home / ".cursor/skills/cad").symlink_to(self.home / ".agents/skills/cad")
        self.write(".codex/skills/urdf/SKILL.md", THEIRS.format(name="urdf"))
        self.write(".agents/.skill-lock.json", {"version": 3, "skills": {
            "cad": {"source": "earthtojake/text-to-cad"}, "urdf": {"source": "someone/robots"},
            "pcb": {"source": "someone/boards"}}})

        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        # Ours in first, then the old ones out.
        claude = self.calls("claude")
        self.assertEqual(claude, [["plugin", "marketplace", "update", "earthtojake"],
                                  ["plugin", "install", "text-to-cad@earthtojake"],
                                  ["plugin", "uninstall", "text-to-cad@text-to-cad"],
                                  ["plugin", "marketplace", "remove", "--scope", "user", "text-to-cad"],
                                  ["plugin", "uninstall", "cad@earthtojake"]])
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad", "--ref", "latest"],
                                               ["plugin", "add", "text-to-cad@earthtojake"],
                                               ["plugin", "remove", "text-to-cad@text-to-cad"],
                                               ["plugin", "marketplace", "remove", "text-to-cad"]])
        self.assertEqual(self.calls("gemini"), [["extensions", "uninstall", "text-to-cad"],
                                                ["extensions", "install", install.URL, "--ref", "latest", "--consent"]])
        self.assertEqual(self.calls("grok"), [["plugin", "uninstall", "cad"]])
        self.assertFalse((self.home / ".cursor/plugins/local/text-to-cad").exists())
        # Loose skills: ours deleted (the link unlinked), someone else's kept, the lock likewise; never through
        # `npx skills remove`, which removes by name alone.
        self.assertEqual(self.calls("npx"), [])
        self.assertFalse((self.home / ".agents/skills/cad").exists())
        self.assertFalse((self.home / ".claude/skills/dxf").exists())
        self.assertFalse(os.path.lexists(self.home / ".cursor/skills/cad"))
        self.assertTrue((self.home / ".codex/skills/urdf/SKILL.md").is_file())
        self.assertEqual(list(json.loads((self.home / ".agents/.skill-lock.json").read_text(encoding="utf-8"))["skills"]),
                         ["urdf", "pcb"])
        self.assertFalse(os.path.lexists(self.home / ".cursor/plugins/local/text-to-cad"))
        self.assertEqual(sorted(path.name for path in self.home.iterdir() if path.name.startswith(".text-to-cad")), [])
        self.assertIn("Loose skills: removed: 3 old copies of our skills", done.stdout)
        self.assertIn("removed old copies: text-to-cad@text-to-cad, cad@earthtojake", done.stdout)

    def test_claude_desktop_s_old_server_goes_through_a_link_and_no_earlier_copy_is_overwritten(self) -> None:
        self.programs("claude")
        dotfiles = self.root / "dotfiles" / "claude_desktop_config.json"
        dotfiles.parent.mkdir()
        dotfiles.write_text('{\n    "mcpServers": {\n        "cad": {"command": "uvx", "args": ["--from", '
                            '"cad-mcp==0.11.10", "cad-mcp"]},\n        "notes": {"command": "notes-server"}\n    },\n'
                            '    "theme": "dark"\n}\n', encoding="utf-8")
        before = dotfiles.read_text(encoding="utf-8")
        config = self.home / self.desktop()
        config.parent.mkdir(parents=True)
        config.symlink_to(dotfiles)
        earlier = self.write(self.desktop() + ".bak", "an earlier copy\n")
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        # Only our member gone, every other byte as it was, edited where the link points; the link stays a link.
        self.assertTrue(config.is_symlink())
        self.assertEqual(dotfiles.read_text(encoding="utf-8"),
                         '{\n    "mcpServers": {\n        "notes": {"command": "notes-server"}\n    },\n    "theme": "dark"\n}\n')
        self.assertEqual(earlier.read_text(encoding="utf-8"), "an earlier copy\n")
        kept = [path for path in dotfiles.parent.iterdir() if path.name.endswith(".bak")]
        self.assertEqual([path.read_text(encoding="utf-8") for path in kept], [before])
        self.assertIn(f"Claude Desktop: removed: the old cad server in its settings ({kept[0].name} keeps", done.stdout)

    def test_claude_desktop_without_the_claude_command_says_what_to_do_and_runs_nothing(self) -> None:
        self.write(self.desktop(), "{}")
        # The Claude Code Claude Desktop keeps for its Code tab is that app's own: never run.
        build = (self.home / self.desktop()).parent / "claude-code" / "2.1.325" / "485fdac4332e"
        executable = build / ("claude.app/Contents/MacOS/claude" if sys.platform == "darwin" else "claude")
        executable.parent.mkdir(parents=True)
        executable.write_text(STAND_IN.format(python=sys.executable, latest=LATEST), encoding="utf-8")
        executable.chmod(0o755)
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.calls("claude"), [])
        self.assertIn("Claude Desktop: " + install.DESKTOP_NO_CLAUDE + "\n", done.stdout)
        self.assertIn("claude plugin marketplace add earthtojake/text-to-cad#latest, then claude plugin install "
                      "text-to-cad@earthtojake", done.stdout)
        # With the command, Claude Code gets the plugin, and Claude Desktop needs no line.
        self.programs("claude")
        done = self.run_install()
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
                                                ["plugin", "install", "text-to-cad@earthtojake"]])
        self.assertNotIn("Claude Desktop:", done.stdout)

    def test_someone_else_s_server_and_folder_of_our_names_are_left(self) -> None:
        desktop = self.write(self.desktop(),
                             json.dumps({"mcpServers": {"cad": {"command": "freecad-mcp"}}}))
        before = desktop.read_text(encoding="utf-8")
        self.write(".cursor/plugins/local/text-to-cad/plugin.json", {"name": "text-to-cad"})
        done = self.run_install()
        self.assertEqual(before, desktop.read_text(encoding="utf-8"))
        self.assertEqual([path.name for path in desktop.parent.iterdir()], [desktop.name])
        self.assertTrue((self.home / ".cursor/plugins/local/text-to-cad/plugin.json").is_file())
        self.assertIn("Cursor: failed: ", done.stdout)
        self.assertIn("holds something else", done.stdout)

    def test_one_app_failing_stops_no_other_and_a_failed_cad_setup_fails_the_run(self) -> None:
        self.programs("codex", "gemini")
        done = self.run_install(FAKE_FAIL="codex")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Codex: failed: `plugin marketplace` said: codex: something went wrong", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)
        done = self.run_install(FAKE_FAIL="uvx")
        self.assertEqual(1, done.returncode)
        self.assertIn("cad setup: failed (exit status 1)", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)
        self.assertIn("text-to-cad itself was not installed", done.stdout)
        # In an agent's sandbox (cad setup's exit status 3) the apps are left alone: their commands would fail too.
        done = self.run_install(FAKE_FAIL="uvx", FAKE_EXIT="3")
        self.assertEqual(1, done.returncode)
        self.assertEqual([call for call in self.calls() if call[:1] != list(install.UVX_ARGS[:1])], [])
        self.assertIn("nothing was changed in them", done.stdout)

    def test_the_report_cad_s_hand_over_reads_changes_nothing_the_run_says(self) -> None:
        # CAD_INSTALL_REPORT (set by cad's own hand-over, cad_server._internal.install_script): what the run did, each
        # app by its key, written whole; the run's output and exit status as without it, and a report that cannot be
        # written fails nothing.
        self.programs("codex", "gemini")
        plain = self.run_install(FAKE_FAIL="codex")
        report = self.root / "report.json"
        done = self.run_install(FAKE_FAIL="codex", CAD_INSTALL_REPORT=str(report))
        self.assertEqual((done.returncode, done.stdout, done.stderr), (plain.returncode, plain.stdout, plain.stderr))
        found = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual({key: found[key] for key in ("schema", "release", "setup")},
                         {"schema": "text-to-cad install report/1", "release": install.FALLBACK, "setup": 0})
        self.assertEqual(set(found["apps"]), {app.key for app in install.APPS})
        self.assertEqual((found["apps"]["codex"], found["apps"]["gemini"], found["apps"]["claude"]),
                         ("failed", "installed", "not found"))
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if "report" in path.name), ["report.json"])
        done = self.run_install(FAKE_FAIL="uvx", FAKE_EXIT="3", CAD_INSTALL_REPORT=str(report))
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["setup"], 3)
        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["apps"], {}, "the apps were left alone")
        nowhere = self.run_install(FAKE_FAIL="codex", CAD_INSTALL_REPORT=str(self.root / "no folder" / "report.json"))
        self.assertEqual((nowhere.returncode, nowhere.stdout, nowhere.stderr),
                         (plain.returncode, plain.stdout, plain.stderr))

    def test_an_error_no_row_foresaw_is_that_app_s_failure_and_every_other_app_runs(self) -> None:
        def broken(app, here, context):
            raise KeyError("plugins")

        (self.home / ".cline").mkdir()
        apps = (install.App("broken", "Broken App", handler=broken),
                *[app for app in install.APPS if app.key == "cline"])
        said = []
        source = install.Source(skills_dir=self.root / "skills")
        self.write("../skills/cad/SKILL.md", OURS.format(name="cad"))
        report = install.install_apps(install.Here(self.environ()), source, apps, say=said.append)
        self.assertEqual(said[:2], ["Broken App: failed: KeyError: 'plugins'",
                                    "Cline: installed: 1 skills in ~/.cline/skills"])
        self.assertFalse(report.all_failed)
        # The spots a person's file broke before: a git config not in UTF-8, a Grok registry that is a list, a Codex
        # config whose tables are not tables.
        (self.home / "clone/.git").mkdir(parents=True)
        (self.home / "clone/.git/config").write_bytes(b'[remote "origin"]\n\turl = https://x/y\n[user]\n\tname = Jos\xe9\n')
        self.assertEqual(install.git_origin(self.home / "clone"), "https://x/y")
        self.write(".grok/installed-plugins/registry.json", [1, 2])
        self.assertEqual(install.grok_plugins(install.Here(self.environ())), [])
        self.write(".codex/config.toml", 'plugins = "none"\nmarketplaces = 3\n')
        self.programs("codex")
        outcome = install.codex(install.APPS[2], install.Here(self.environ()),
                                install.Context(install.Source()))
        self.assertEqual(outcome.status, "installed")

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

    def run_sh(self, **extra: str) -> subprocess.CompletedProcess:
        if self.log.exists():
            self.log.unlink()
        return subprocess.run(["/bin/sh"], input=(INSTALL / "install.sh").read_text(encoding="utf-8"), capture_output=True,
                              text=True, env=self.environ(CAD_INSTALL_PY=str(INSTALL / "install.py"),
                                                          PATH=f"{self.bin}:/usr/bin:/bin", **extra), timeout=60)

    def test_install_sh_runs_install_py_with_uv_s_python(self) -> None:
        self.programs("uv")
        script = self.run_sh()
        self.assertEqual(0, script.returncode, script.stderr)
        run = self.calls("uv")[-1]
        self.assertEqual(run[:-1], ["run", "--no-config", "--managed-python", "--python", "3.14", "--no-project"])
        self.assertEqual(Path(run[-1]).name, "install.py")

    def test_install_sh_refuses_a_uv_too_old_for_python_3_14_and_updates_its_own_install(self) -> None:
        self.programs("uv")
        script = self.run_sh(FAKE_UV_VERSION="0.8.24")
        self.assertEqual(1, script.returncode)
        self.assertIn("uv 0.8.24 is older than 0.9.0", script.stderr)
        self.assertIn("brew upgrade uv", script.stderr)
        self.assertEqual(self.calls("uv"), [["--version"]])
        # uv from its own installer (its receipt) updates itself.
        self.write(".config/uv/uv-receipt.json", "{}")
        script = self.run_sh(FAKE_UV_VERSION="0.8.24")
        self.assertEqual(self.calls("uv"), [["--version"], ["self", "update"], ["--version"]])
        self.assertIn("updating it (uv self update)", script.stderr)

    def test_the_development_install_puts_the_checkout_in_place_of_the_published_copy(self) -> None:
        dev_spec = importlib.util.spec_from_file_location("text_to_cad_dev_install", INSTALL / "dev_install.py")
        dev_install = importlib.util.module_from_spec(dev_spec)
        dev_spec.loader.exec_module(dev_install)
        folder = self.root / "dev-plugin" / "text-to-cad"
        release = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        dev_install.assemble(folder, f"{release}-dev.1", "/venv/bin/python")
        self.assertEqual(json.loads((folder / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))["name"], "earthtojake-dev")
        # Codex's server, the one there is, runs the checkout's interpreter under a bare command (Codex has dropped,
        # with no error, a server whose command is a path), and keeps its start allowance.
        self.assertEqual(sorted(path.name for path in folder.glob("*mcp*.json")), ["codex.mcp.json"])
        server = json.loads((folder / "codex.mcp.json").read_text(encoding="utf-8"))["mcpServers"]["cad"]
        self.assertEqual((server["command"], server["args"][-3:]), ("uv", ["/venv/bin/python", "--module", "cad_mcp"]))
        self.assertEqual(server["startup_timeout_sec"], 300)
        skill = (folder / "skills/cad/SKILL.md").read_text(encoding="utf-8")
        self.assertNotRegex(skill, rf"cad \+{release}(?!-dev)")
        # The folder's catalog comes in; then the published copy goes.
        self.programs("claude")
        self.claude_records({"text-to-cad@earthtojake": 1},
                            {"earthtojake": {"source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}})
        source = install.Source(folder=folder, catalog=install.DEV_CATALOG, skills_dir=folder / "skills")
        claude = [app for app in install.APPS if app.key == "claude"]
        lines = install.install_apps(install.Here(self.environ()), source, claude, say=lambda line: None)
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", str(folder)],
                                                ["plugin", "install", "text-to-cad@earthtojake-dev"],
                                                ["plugin", "uninstall", "text-to-cad@earthtojake"],
                                                ["plugin", "marketplace", "remove", "--scope", "user", "earthtojake"]])
        self.assertIn("Claude Code: installed (removed old copies: text-to-cad@earthtojake)", lines)


if __name__ == "__main__":
    unittest.main()
