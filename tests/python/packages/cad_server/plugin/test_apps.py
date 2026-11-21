"""cad's table of the agent apps (``cad_server/plugin/apps.py``), by what ``cad plugin install`` does in each.

Each test runs the command on a computer of its own (``tests/python/support/agent_apps.py``): a fresh temporary home,
stand-in programs on PATH for the apps' CLIs and git, which record how they were called and change nothing else. No
real app, network or uv runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import cad_server
from cad_server.plugin import apps, computer, source
from tests.python.support.agent_apps import CODEX_ADD, LATEST, OURS, OURS_OLD, STAND_IN, THEIRS, PluginRuns


# Codex's config with our catalog as this release adds it: from GitHub at `latest`, a few paths checked out.
CODEX_CONFIG = ('[marketplaces.earthtojake]\nsource_type = "git"\nsource = "https://github.com/earthtojake/text-to-cad.git"\n'
                'ref = "latest"\nsparse_paths = [".claude-plugin", ".codex-plugin", "skills", "codex.mcp.json"]\n'
                '[plugins."text-to-cad@earthtojake"]\nenabled = true\n')


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line")
class AppTableTests(PluginRuns):
    def test_run_again_it_updates_each_app_s_github_copy_with_the_app_s_own_command(self) -> None:
        self.programs("claude", "codex", "gemini")
        github = {"source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}
        self.claude_records({"text-to-cad@earthtojake": 1}, {"earthtojake": github})
        self.write(".codex/config.toml", CODEX_CONFIG)
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json",
                   {"type": "git", "source": source.URL, "ref": "latest"})
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "update", "earthtojake"],
                                                ["plugin", "update", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "upgrade", "earthtojake"],
                                               ["plugin", "add", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("gemini"), [["extensions", "uninstall", "text-to-cad"],
                                                ["extensions", "install", source.URL, "--ref", "latest", "--consent"]])
        for name in ("Claude Code", "Codex", "Gemini CLI"):
            self.assertIn(f"{name}: updated\n", done.stdout)

    def test_gemini_s_github_copy_is_installed_again_never_asked_to_update(self) -> None:
        # `extensions update` asks twice and takes no --consent: with no one to answer, it waits for ever.
        self.programs("gemini")
        github = {"type": "git", "source": source.URL, "ref": "latest"}
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json", github)
        done = self.run_install(FAKE_GEMINI_RECORD="1")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn(["extensions", "update", "text-to-cad"], self.calls("gemini"))
        self.assertEqual(self.calls("gemini"), [["extensions", "uninstall", "text-to-cad"],
                                                ["extensions", "install", source.URL, "--ref", "latest", "--consent"]])
        self.assertIn("Gemini CLI: updated\n", done.stdout)
        self.assertEqual([path.name for path in (self.home / ".gemini/extensions").iterdir()], ["text-to-cad"])
        record = self.home / ".gemini/extensions/text-to-cad/.gemini-extension-install.json"
        self.assertEqual(json.loads(record.read_text(encoding="utf-8")), github)

    def test_gemini_s_github_copy_is_put_back_where_installing_it_again_fails(self) -> None:
        self.programs("gemini")
        github = {"type": "git", "source": source.URL, "ref": "latest"}
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
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(person)
        done = self.run_install()
        self.assertEqual(0, done.returncode, done.stderr)
        runs = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.write(".gemini/extensions/text-to-cad/.gemini-extension-install.json",
                   {"type": "git", "source": source.URL, "ref": "latest"})
        again = self.run_install()
        self.assertEqual(0, again.returncode, again.stderr)
        runs += [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        runs = [call for call in runs if call["name"] == "gemini"]
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
        # Every app it found failed: the run says so, and fails, and keeps no release as the one the plugin is up to
        # date for but this one as owed a run (``plugin_catch_up``), so cad's server runs it again where the switch is
        # on. The switch it leaves as it is.
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("No app got the plugin", done.stdout)
        self.assertEqual(self.kept(), {"switch": False, "record": {"owed": cad_server.__version__}})
        self.assertNotIn("Start a new session", done.stdout)
        self.assertEqual(self.calls("claude"), [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"]])
        self.assertEqual(self.calls("codex"), [CODEX_ADD])
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
        self.write(".cursor/plugins/local/text-to-cad/.git/config", f'[remote "origin"]\n\turl = {source.URL}.git\n')
        self.write(".grok/installed-plugins/registry.json", {"repos": {"x": {
            "kind": {"type": "Git", "url": source.URL, "git_ref": "latest"}, "path": "/x",
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
        self.write(".cursor/plugins/local/text-to-cad/.git/config", f'[remote "origin"]\n\turl = {source.URL}.git\n')
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
        (checkout / ".git/config").write_text(f'[remote "origin"]\n\turl = {source.URL}.git\n', encoding="utf-8")
        clone.symlink_to(checkout)
        for claude in (True, False):
            if not claude:
                (self.bin / "claude").unlink()
            done = self.run_install()
            self.assertTrue(clone.is_symlink())
            self.assertEqual(self.calls("git"), [])
            self.assertIn("~/.cursor/plugins/local/text-to-cad is a link: left alone", done.stdout)

    def test_a_character_the_output_cannot_encode_stops_no_app(self) -> None:
        # An output in a code page that has no ✘ (cp1252, as Python writes a pipe on Windows): the line is printed
        # with the character escaped, as every `cad` command writes one, and the run goes on to the next app and the
        # loose skills.
        self.programs("claude", "gemini")
        stand_in = self.bin / "claude"
        stand_in.write_text(stand_in.read_text(encoding="utf-8").replace(
            "    sys.exit(int(", "    sys.stdout.flush()\n    sys.stdout.buffer.write('\u2718 Failed to add marketplace\\n'.encode())\n    sys.exit(int(", 1),
            encoding="utf-8")
        command, environ = self.child("install", FAKE_FAIL="claude", PYTHONIOENCODING="cp1252")
        done = subprocess.run(command, env=environ, capture_output=True, text=True, encoding="cp1252", timeout=120)
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertIn("Claude Code: failed: ", done.stdout)
        self.assertIn("\\u2718 Failed to add marketplace", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)

    def test_what_past_releases_left_is_removed_once_ours_is_in_and_nothing_else(self) -> None:
        self.programs("claude", "codex", "gemini", "grok", "npx")
        folder = str(self.state / "plugin")
        github = {"source": "github", "repo": "earthtojake/text-to-cad", "ref": "latest"}
        # Claude Code: 0.10-0.11.11's local catalog and its plugin, and 0.7.6's cad@earthtojake; someone else's plugin.
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
            "kind": {"type": "Git", "url": source.URL, "git_ref": ""}, "path": "/x", "plugins": {"cad": {}}}}})
        # Cursor: 0.10-0.11.11's marked plain copy.
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
        self.assertEqual(self.calls("codex"), [CODEX_ADD,
                                               ["plugin", "add", "text-to-cad@earthtojake"],
                                               ["plugin", "remove", "text-to-cad@text-to-cad"],
                                               ["plugin", "marketplace", "remove", "text-to-cad"]])
        self.assertEqual(self.calls("gemini"), [["extensions", "uninstall", "text-to-cad"],
                                                ["extensions", "install", source.URL, "--ref", "latest", "--consent"]])
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

    def desktop(self) -> str:
        """Claude Desktop's config, where the table looks for it on this platform, relative to the home."""
        return str(apps.desktop_config(computer.Here(self.environ())).relative_to(self.home))

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
        self.assertIn("Claude Desktop: " + apps.DESKTOP_NO_CLAUDE + "\n", done.stdout)
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

    def test_an_error_no_row_foresaw_is_that_app_s_failure_and_every_other_app_runs(self) -> None:
        def broken(app, here, context):
            raise KeyError("plugins")

        (self.home / ".cline").mkdir()
        rows = (apps.App("broken", "Broken App", handler=broken),
                *[app for app in apps.APPS if app.key == "cline"])
        said = []
        skills = source.Source(skills_dir=self.root / "skills")
        self.write("../skills/cad/SKILL.md", OURS.format(name="cad"))
        report = apps.install_apps(computer.Here(self.environ()), skills, rows, say=said.append)
        self.assertEqual(said[:2], ["Broken App: failed: KeyError: 'plugins'",
                                    "Cline: installed: 1 skills in ~/.cline/skills"])
        self.assertFalse(report.all_failed)
        self.assertEqual(report.statuses(), {"broken": "failed", "cline": "installed"})
        self.assertEqual(set(report.seconds), {"broken", "cline"})
        # The spots a person's file broke before: a git config not in UTF-8, a Grok registry that is a list, a Codex
        # config whose tables are not tables.
        (self.home / "clone/.git").mkdir(parents=True)
        (self.home / "clone/.git/config").write_bytes(b'[remote "origin"]\n\turl = https://x/y\n[user]\n\tname = Jos\xe9\n')
        self.assertEqual(apps.git_origin(self.home / "clone"), "https://x/y")
        self.write(".grok/installed-plugins/registry.json", [1, 2])
        self.assertEqual(apps.grok_plugins(computer.Here(self.environ())), [])
        self.write(".codex/config.toml", 'plugins = "none"\nmarketplaces = 3\n')
        self.programs("codex")
        outcome = apps.codex(apps.APPS[2], computer.Here(self.environ()),
                             apps.Context(source.Source()))
        self.assertEqual(outcome.status, "installed")

    def test_a_failure_carries_a_word_for_why_chosen_where_it_failed(self) -> None:
        """``Outcome.reason``: a command that ended badly, one stopped because it did not answer, GitHub out of reach,
        an error no row foresaw, and anything else; never a part of its message. Nothing but a failure has one."""
        def broken(app, here, context):
            raise KeyError("plugins")

        def hangs(app, here, context):
            here.must([sys.executable, "-c", "import time; time.sleep(600)"], timeout=0.2)

        self.programs("codex", "gemini")
        (self.home / ".cline").mkdir()  # its skills come from GitHub, which no clone and no download reaches
        self.write(".cursor/plugins/local/text-to-cad/plugin.json", {"name": "text-to-cad"})  # someone else's folder
        rows = (apps.App("broken", "Broken App", handler=broken), apps.App("hangs", "Hanging App", handler=hangs),
                *[app for app in apps.APPS if app.key in ("codex", "cursor", "gemini", "cline")])
        here = computer.Here(self.environ(FAKE_FAIL="codex,git:clone"))
        report = apps.install_apps(here, source.Source(), rows, say=lambda line: None)
        self.assertEqual({key: (outcome.status, outcome.reason) for key, outcome in report.outcomes.items()},
                         {"broken": ("failed", "exception"), "hangs": ("failed", "timeout"),
                          "codex": ("failed", "command"), "cursor": ("failed", "other"),
                          "gemini": ("installed", ""), "cline": ("failed", "network")})
        for outcome in report.outcomes.values():
            self.assertIn(outcome.reason, ("", *computer.REASONS))
        self.assertFalse(report.stopped)

    def test_a_command_s_reason_is_its_most_telling_line(self) -> None:
        """``Ran.last``: the first line that reads as an error, not the advice a command's error ends with; else its
        last line; trimmed; and the exit status where it said nothing."""
        claude = ("Updating marketplace: earthtojake...\n"
                  "Failed to update marketplace(s): Failed to update marketplace 'earthtojake': Failed to clone "
                  "repository: Cloning into '/home/x/.claude/plugins/marketplaces/earthtojake'...  fatal: unable "
                  "to access 'https://github.com/earthtojake/text-to-cad.git/': Failed to connect to github.com "
                  "port 443 after 21040 ms: Could not connect to server\n"
                  "  Check your network connection and that you have access to the repository, and that the URL is "
                  "correct\n"
                  "and the repository exists.\n")
        reason = computer.Ran(1, claude).last()
        self.assertEqual(reason, claude.splitlines()[1][:computer.LAST_CHARACTERS])
        self.assertEqual(len(reason), computer.LAST_CHARACTERS)
        self.assertEqual(computer.Ran(1, "Cloning into 'x'...\n\nfatal: repository 'x' not found\nbye\n").last(),
                         "fatal: repository 'x' not found")
        for said in ("ERROR: no such marketplace", "Permission denied (publickey).", "Could not read from remote",
                     "codex: unable to write config", "npm error code E404", "plugin not found"):
            self.assertEqual(computer.Ran(1, f"working...\n{said}\nsee the docs\n").last(), said)
        self.assertEqual(computer.Ran(1, "one\n  two  \n\n").last(), "two")
        self.assertEqual(computer.Ran(1, "x" * 500).last(), "x" * computer.LAST_CHARACTERS)
        self.assertEqual(computer.Ran(3, " \n").last(), "exit status 3")
        # Every caller has it: a failed command's line, by ``Here.must``.
        here = computer.Here(self.environ())
        with self.assertRaises(computer.Failed) as caught:
            here.must([sys.executable, "-c", f"import sys; sys.stdout.write({claude!r}); sys.exit(1)"])
        self.assertIn("said: Failed to update marketplace(s): ", str(caught.exception))
        self.assertEqual(caught.exception.reason, "network")

    def test_a_command_the_network_failed_is_counted_as_network(self) -> None:
        """``Ran.reason``: ``network`` where what a command printed says the network failed it (git's, curl's and
        Node's words, in any case), ``timeout`` where cad stopped it, else ``command``; always one of ``REASONS``."""
        for said in ("fatal: unable to access 'https://github.com/x/y.git/': Could not resolve host: github.com",
                     "curl: (7) Failed to connect to github.com port 443: Connection refused",
                     "fatal: unable to access 'https://github.com/x/': Recv failure: connection refused",
                     "ssh: connect to host github.com port 22: Connection timed out",
                     "connect: Network is unreachable",
                     "fatal: unable to access 'https://github.com/x/': SSL certificate problem: unable to get issuer",
                     "schannel: failed to receive handshake, SSL/TLS connection failed",
                     "Error: connect ECONNREFUSED 140.82.112.3:443",
                     "npm error getaddrinfo ENOTFOUND registry.npmjs.org",
                     "Error: request to https://github.com failed, reason: ETIMEDOUT",
                     "could not resolve host: GITHUB.COM"):
            ran = computer.Ran(1, f"Installing...\n{said}\n")
            self.assertEqual(ran.reason, "network", said)
        for said in ("codex: something went wrong", "error: unknown option '--scope'", "Permission denied",
                     "plugin text-to-cad not found", "wrote /home/x/openssl.cnf", ""):
            self.assertEqual(computer.Ran(1, said).reason, "command", said)
        stopped = computer.Ran(computer.STOPPED, "Could not resolve host: github.com", stopped=True)
        self.assertEqual(stopped.reason, "timeout")
        self.assertEqual(computer.Ran(computer.STOPPED, "no answer in 3 s: stopped", stopped=True).reason, "timeout")
        for ran in (stopped, computer.Ran(1, "Connection refused"), computer.Ran(2, "usage")):
            self.assertIn(ran.reason, computer.REASONS)

    def test_past_its_deadline_a_run_starts_no_command_and_no_further_app(self) -> None:
        """A run with a deadline (the one a server began) gives each command what is left of it and stops it with
        what it started; past it, no command is started, no further app begun, and nothing more removed."""
        import time

        self.programs("codex", "gemini")
        self.write(".agents/skills/fea/SKILL.md", OURS.format(name="fea"))  # a loose copy of ours, which stays
        here = computer.Here(self.environ())
        here.until = time.monotonic() + 0.2
        ran = here.run([sys.executable, "-c", "import time; time.sleep(600)"])
        self.assertEqual((ran.code, ran.stopped, ran.reason), (computer.STOPPED, True, "timeout"))
        self.assertTrue(here.expired)
        self.assertTrue(here.run([sys.executable, "-c", "pass"]).stopped, "not started")
        report = apps.install_apps(here, source.Source(), say=lambda line: None)
        self.assertTrue(report.stopped)
        self.assertEqual((report.outcomes, self.calls()), ({}, []))
        self.assertTrue((self.home / ".agents/skills/fea/SKILL.md").is_file())

    def test_codex_s_whole_clone_of_our_catalog_is_replaced_by_one_of_a_few_paths(self) -> None:
        # Added whole, Codex clones every commit of the repository, and its upgrade gives that clone 30 seconds: too
        # few on Windows, where every update failed. Such a catalog is added again, sparse, and put back where that
        # fails.
        self.programs("codex")
        whole = CODEX_CONFIG.replace('sparse_paths = [".claude-plugin", ".codex-plugin", "skills", "codex.mcp.json"]\n', "")
        self.write(".codex/config.toml", whole)
        done = self.run_install()
        self.assertEqual(self.calls("codex"), [["plugin", "remove", "text-to-cad@earthtojake"],
                                               ["plugin", "marketplace", "remove", "earthtojake"],
                                               CODEX_ADD, ["plugin", "add", "text-to-cad@earthtojake"]])
        self.assertIn("Codex: updated\n", done.stdout)
        failed = self.run_install(FAKE_FAIL="codex:--sparse")
        self.assertEqual(self.calls("codex")[3:], [["plugin", "marketplace", "add",
                                                    "https://github.com/earthtojake/text-to-cad.git", "--ref", "latest"],
                                                   ["plugin", "add", "text-to-cad@earthtojake"]])
        self.assertIn("the earlier copy was put back", failed.stdout)
        # Added sparse, it is upgraded where it is.
        self.write(".codex/config.toml", CODEX_CONFIG)
        self.run_install()
        self.assertEqual(self.calls("codex"), [["plugin", "marketplace", "upgrade", "earthtojake"],
                                               ["plugin", "add", "text-to-cad@earthtojake"]])

    def test_copilot_adds_our_catalog_only_where_it_has_none(self) -> None:
        # Copilot CLI's `marketplace add` fails for a catalog it has: a run whose add went in and whose install did
        # not, or a person who uninstalled the plugin and kept the catalog, must still get the plugin.
        self.programs("copilot")
        fresh = self.run_install()
        self.assertEqual(self.calls("copilot"), [["plugin", "update", "text-to-cad"],
                                                 ["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
                                                 ["plugin", "install", "text-to-cad@earthtojake"]])
        self.assertIn("GitHub Copilot CLI: installed\n", fresh.stdout)
        self.assertEqual(self.run_install().stdout.count("GitHub Copilot CLI: updated\n"), 1)
        (self.home / ".copilot" / "config.json").unlink()  # uninstalled, the catalog kept
        kept = self.run_install()
        self.assertEqual(self.calls("copilot"), [["plugin", "update", "text-to-cad"],
                                                 ["plugin", "install", "text-to-cad@earthtojake"]])
        self.assertIn("GitHub Copilot CLI: installed\n", kept.stdout)
        # A catalog of that name from somewhere else is left alone.
        self.write(".copilot/settings.json", {"extraKnownMarketplaces": {"earthtojake": {
            "source": {"source": "github", "repo": "someone/else"}}}})
        (self.home / ".copilot" / "config.json").unlink()
        theirs = self.run_install()
        self.assertEqual(self.calls("copilot"), [["plugin", "update", "text-to-cad"]])
        self.assertIn("GitHub Copilot CLI: failed: the earthtojake catalog is another source's (someone/else)",
                      theirs.stdout)

    def test_an_app_nobody_is_signed_in_to_is_skipped_with_what_it_said_not_failed(self) -> None:
        # Devin CLI manages plugins only for a person signed in: nothing a run does changes that, so the run does not
        # count it as failed (and so try it again and again), and says what the app said to do.
        self.programs("devin")
        done = self.run_install(FAKE_SIGNED_OUT="1")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(self.calls("devin"), [["plugins", "update", "text-to-cad"],
                                               ["plugins", "install", "earthtojake/text-to-cad", "-y"]])
        self.assertIn("Devin CLI: skipped: nobody is signed in to it (Error: You must be logged in to manage plugins. "
                      "Run `devin auth login` first.)\n", done.stdout)
        self.assertEqual(self.kept()["record"].get("for"), cad_server.__version__)
        # Any other failure of its command is still a failure.
        self.assertIn("Devin CLI: failed: devin: something went wrong", self.run_install(FAKE_FAIL="devin").stdout)

    def test_one_app_failing_stops_no_other(self) -> None:
        self.programs("codex", "gemini")
        done = self.run_install(FAKE_FAIL="codex")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn("Codex: failed: `plugin marketplace` said: codex: something went wrong", done.stdout)
        self.assertIn("Gemini CLI: installed", done.stdout)


if __name__ == "__main__":
    unittest.main()
