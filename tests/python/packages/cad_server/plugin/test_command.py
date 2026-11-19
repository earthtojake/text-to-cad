"""``cad plugin install`` and ``cad plugin update`` (``cad_server/cli/plugin.py``, ``cad_server/plugin/run.py``): the
whole run on a computer of its own (``tests/python/support/agent_apps.py``: a temporary home, stand-in programs for
the apps' CLIs), its exit statuses, the report it writes, the lock that keeps it the only run, the record
``cad plugin update`` keeps and ``cad plugin install`` leaves alone, and what a run says it was (``run.Facts``)."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

import cad_server
from cad_server._internal import auto_update_helper, plugin_catch_up
from cad_server.cli import plugin as command
from cad_server.plugin import apps, computer, run, source
from tests.python.support.agent_apps import PluginRuns

ADD = [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
       ["plugin", "install", "text-to-cad@earthtojake"]]


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line")
class InstallTests(PluginRuns):
    def test_a_computer_gets_the_plugin_in_every_app_found_and_the_switch_turned_on(self) -> None:
        self.programs("claude", "codex", "gemini", "grok", "muse", "cad", "uv", "curl", "sh")
        (self.home / ".cursor").mkdir()
        (self.home / ".cline").mkdir()
        # Muse has no copy yet: its update fails, and it installs from the `latest` branch fetched once.
        line, environ = self.child("install", FAKE_FAIL="muse:update")
        done = subprocess.run(line, env=environ, capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
        self.assertEqual(self.calls("claude"), ADD)
        self.assertEqual(self.calls("codex"),
                         [["plugin", "marketplace", "add", "earthtojake/text-to-cad", "--ref", "latest"],
                          ["plugin", "add", "text-to-cad@earthtojake"]])
        self.assertEqual(self.calls("gemini"), [["extensions", "install", source.URL, "--ref", "latest", "--consent"]])
        # Cursor and Grok Build load Claude Code's plugin: none of their own.
        self.assertEqual(self.calls("grok"), [])
        self.assertFalse((self.home / ".cursor/plugins/local/text-to-cad").exists())
        # An agent with no plugin command gets the skills in its own folder, from `latest`, fetched once.
        self.assertIn("new", (self.home / ".cline/skills/cad/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual([argv[:6] for argv in self.calls("git")],
                         [["clone", "--quiet", "--depth", "1", "--branch", "latest"]])
        fetched = self.calls("git")[0][-1]
        self.assertEqual(self.calls("muse"), [["plugins", "update", "text-to-cad"], ["plugins", "install", fetched],
                                              ["plugins", "approve", "text-to-cad"]])
        said = done.stdout.splitlines()
        self.assertEqual(said[0], "Setting up the plugin in each agent app found here:")
        for said_line in ("Claude Code: installed", "Codex: installed", "Gemini CLI: installed", "Muse: installed",
                          "Grok Build: skipped: it loads Claude Code's plugin",
                          "Cursor: skipped: it loads Claude Code's plugin",
                          "Cline: installed: 2 skills in ~/.cline/skills"):
            self.assertIn(said_line, said)
        self.assertEqual(said[-3:], ["", "plugin update auto: on", "Start a new session in each app to use it."])
        self.assertNotIn("removed", done.stdout)
        # It runs no cad, no uv and no install command: the switch is turned on by this process, and this release kept
        # as the one the plugin is up to date for.
        self.assertEqual([name for name in ("cad", "uv", "curl", "sh") if self.calls(name)], [])
        self.assertEqual(self.kept(), {"switch": True, "record": {"for": cad_server.__version__}})

    def test_its_exit_status_says_how_it_ended(self) -> None:
        # 0: it ended well, with nothing found too.
        done = self.run_install()
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertNotIn("Start a new session", done.stdout)
        self.assertEqual(self.kept(), {"switch": True, "record": {"for": cad_server.__version__}})
        # 1: every app it found failed. The switch is on all the same, and no release is kept for it.
        self.programs("claude", "codex")
        (self.state / "install-command.json").unlink()
        done = self.run_install(FAKE_FAIL="claude,codex")
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("No app got the plugin: see each app's line above, then run this again.", done.stdout)
        self.assertNotIn("Start a new session", done.stdout)
        self.assertEqual(self.kept(), {"switch": True, "record": {}})
        # One of them failing is the run ending well.
        self.assertEqual(0, self.run_install(FAKE_FAIL="codex").returncode)
        # 2: a command line it does not take; nothing ran.
        for argv in (["install", "--force"], ["install", "claude"]):
            done = self.cad_plugin(*argv)
            self.assertEqual((2, "", []), (done.returncode, done.stdout, self.calls()), argv)
            self.assertIn("usage: cad plugin", done.stderr)
        # 75: another run is going, and a server began this one. Nothing ran, and one line says so.
        with self.another_run():
            done = self.cad_plugin("install", CAD_INSTALL_ATTEMPT="7.0",
                                   CAD_PLUGIN_REPORT=str(self.root / "report.json"))
        self.assertEqual((plugin_catch_up.BUSY, 75), (done.returncode, done.returncode))
        self.assertEqual((done.stdout, self.calls()), ("", []))
        self.assertEqual(done.stderr, "cad plugin install: another run is setting up the plugin in the agent apps now, "
                                      "so this one ran nothing\n")
        self.assertFalse((self.root / "report.json").exists(), "a run that ran nothing writes none")

    def test_a_cad_that_is_not_the_global_install_turns_the_switch_on_and_keeps_no_release(self) -> None:
        """For an installed cad with no ``cad plugin install`` (0.11.12, 0.11.13) the hosted install command runs the
        newest release's, from uv's cache. That release is not the installed cad's, and may be of a major it never
        reaches: kept as the one the plugin is up to date for, the installed cad's server, which runs ``cad plugin
        update`` only where it is newer than the release kept, would never run it again. So only the computer's global
        install keeps its release; any other cad does the work, turns the switch on, and leaves the record alone."""
        self.programs("claude")
        with self.from_elsewhere():
            done = self.run_install()
        self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
        self.assertEqual(self.calls("claude"), ADD)
        self.assertEqual(done.stdout.splitlines()[-2:], ["plugin update auto: on",
                                                         "Start a new session in each app to use it."])
        self.assertEqual(self.kept(), {"switch": True, "record": {}}, "the next server keeps its own release")
        # What the installed cad kept stays as it was, whichever command the other cad runs.
        self.keep(**{"for": "0.0.1"})
        with self.from_elsewhere():
            for argv in (["install"], ["update"], ["update", "auto", "on"]):
                self.assertEqual(0, self.cad_plugin(*argv).returncode, argv)
                self.assertEqual(self.kept(), {"switch": True, "record": {"for": "0.0.1"}}, argv)
        # The installed cad's own run keeps its release.
        self.assertEqual(0, self.run_install().returncode)
        self.assertEqual(self.kept(), {"switch": True, "record": {"for": cad_server.__version__}})

    def test_the_report_names_each_app_s_status_and_changes_nothing_the_run_says(self) -> None:
        # CAD_PLUGIN_REPORT (set by the hosted install command, which hands over to this one): what the run did, each
        # app by its key, written whole; the run's output and exit status as without it, and a report that cannot be
        # written fails nothing.
        self.programs("codex", "gemini")
        plain = self.run_install(FAKE_FAIL="codex")
        report = self.root / "report.json"
        done = self.run_install(FAKE_FAIL="codex", CAD_PLUGIN_REPORT=str(report))
        self.assertEqual((done.returncode, done.stdout, done.stderr), (plain.returncode, plain.stdout, plain.stderr))
        found = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual((set(found), found["schema"]), ({"schema", "apps"}, "cad plugin install/1"))
        self.assertEqual(set(found["apps"]), {app.key for app in apps.APPS})
        self.assertEqual((found["apps"]["codex"], found["apps"]["gemini"], found["apps"]["claude"]),
                         ("failed", "installed", "not found"))
        self.assertLessEqual(set(found["apps"].values()),
                             {"installed", "updated", "removed", "skipped", "failed", "not found"})
        self.assertEqual(sorted(path.name for path in self.root.iterdir() if "report" in path.name), ["report.json"])
        nowhere = self.run_install(FAKE_FAIL="codex", CAD_PLUGIN_REPORT=str(self.root / "no folder" / "report.json"))
        self.assertEqual((nowhere.returncode, nowhere.stdout, nowhere.stderr),
                         (plain.returncode, plain.stdout, plain.stderr))

    def test_a_second_run_waits_for_the_first_unless_a_server_began_it(self) -> None:
        self.programs("claude")
        line, environ = self.child("install")
        with self.another_run():
            with mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state)}):
                self.assertTrue(plugin_catch_up.running())
            # A person's, or the hosted install command's: it says it waits, and runs nothing while it does.
            waiting = subprocess.Popen(line, env=environ, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       encoding="utf-8")
            self.addCleanup(waiting.kill)
            self.assertEqual(waiting.stdout.readline(), "Another run is setting up the plugin in the agent apps now: "
                                                        "this one waits for it to end, then runs.\n")
            self.assertEqual((waiting.poll(), self.calls()), (None, []))
            # One a server began (its run is named) ends once it has tried for the lock as long as any run does: the
            # first run is doing the work.
            busy = subprocess.run(line, env={**environ, "CAD_INSTALL_ATTEMPT": "7.0"}, capture_output=True, text=True,
                                  encoding="utf-8", timeout=120)
            self.assertEqual((busy.returncode, busy.stdout, self.calls()), (75, "", []))
        out, err = waiting.communicate(timeout=120)
        self.assertEqual((waiting.returncode, err), (0, ""), out)
        self.assertEqual(self.calls("claude"), ADD)
        self.assertIn("Claude Code: installed", out)
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state)}):
            self.assertFalse(plugin_catch_up.running(), "the lock is let go as the run ends")

    def test_a_lock_held_for_an_instant_is_no_run_going(self) -> None:
        """Whether a run is going can only be asked by trying for its lock (``plugin_catch_up.running``), so a server
        that asks holds it for the instant it asks. A run that begins just then tries again before it takes the lock
        as another run's: a server's run does its work, where it would have answered 75 and been kept as failed for an
        hour, and a person's says nothing of waiting."""
        from cad_server._internal import file_lock

        self.programs("claude")
        self.state.mkdir(parents=True)
        for began_by in ({"CAD_INSTALL_ATTEMPT": "7.0"}, {}):
            with contextlib.ExitStack() as asking, self.subTest(began_by=began_by):
                asking.enter_context(file_lock.exclusive(self.state / plugin_catch_up.LOCK))
                # The one who asked lets go while the run waits its first step.
                with mock.patch.object(plugin_catch_up.time, "sleep", side_effect=lambda _step: asking.close()) as slept:
                    done = self.cad_plugin("install", **began_by)
                slept.assert_called_with(plugin_catch_up.SETTLE_STEP)
                self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
                self.assertNotIn("Another run", done.stdout)
                self.assertEqual(self.calls("claude"), ADD)

    def test_a_state_folder_it_may_not_lock_never_stops_the_run(self) -> None:
        self.programs("claude")
        with mock.patch("cad_server._internal.file_lock.attempt", side_effect=PermissionError("read-only")), \
                mock.patch("cad_server._internal.file_lock.exclusive", side_effect=PermissionError("read-only")):
            done = self.run_install()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.calls("claude"), ADD)
        # Nor does a switch that cannot be kept: said in one line.
        self.assertIn("The plugin's automatic updates were not turned on (read-only). Run this command again to update "
                      "the plugin.", done.stdout)

    def test_run_by_cad_every_rename_is_cad_s_one_rename(self) -> None:
        """The table's modules are the standard library alone, and rename with it where a checkout's development
        install loads them without cad; the command gives them cad's rename, which every file cad writes goes by."""
        from cad._internal.atomic_replace import replace_atomic

        self.assertIs(computer.rename, replace_atomic)

    def test_install_under_an_earlier_cad_s_server_run_leaves_that_run_s_record_alone(self) -> None:
        """A server of an earlier cad runs ``cad plugin update``, whose install command hands over to this cad's ``cad
        plugin install`` with that run's name in its environment: the run is the earlier command's to end. It has no
        deadline either."""
        self.programs("claude")
        underway = {"release": "0.0.2", "at": 7.0, "tries": 1, "outcome": "underway"}
        self.keep(**{"for": "0.0.1"}, **underway)
        done = self.cad_plugin("install", CAD_INSTALL_ATTEMPT="7.0", FAKE_FAIL="claude")
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertEqual(self.kept()["record"], {"for": "0.0.1", **underway})
        with mock.patch.object(plugin_catch_up, "deadline") as deadline, \
                mock.patch.object(plugin_catch_up, "ended") as ended, \
                mock.patch.object(auto_update_helper, "INSTALL_SECONDS", 0):
            done = self.cad_plugin("install", CAD_INSTALL_ATTEMPT="7.0")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual((deadline.call_count, ended.call_count), (0, 0))
        self.assertEqual(self.calls("claude"), ADD)
        # Ended well, it keeps this release as the one the plugin is up to date for, as turning the switch on does.
        self.assertEqual(self.kept()["record"], {"for": cad_server.__version__, **underway})

    def test_a_run_says_what_it_was_for_whoever_counts_it(self) -> None:
        """``run.Facts``, made in one place: who began the run, how it ended, each app found with its status, the
        word for why it failed and its seconds, and what the terminal was shown."""
        self.assertEqual([run.began_by(environ) for environ in (
            {}, {"CAD_PLUGIN_BY": "script"}, {"CAD_PLUGIN_BY": "someone"}, {"CAD_INSTALL_ATTEMPT": "7.0"},
            {"CAD_INSTALL_ATTEMPT": "7.0", "CAD_PLUGIN_BY": "script"})],
            ["person", "script", "person", "server", "server"])
        self.programs("codex", "gemini")
        (self.home / ".cline").mkdir()  # its skills come from GitHub, which nothing reaches here
        with self.on_this_computer(FAKE_FAIL="codex,git:clone", CAD_PLUGIN_BY="script"):
            facts = command._run("cad plugin install")
        self.assertEqual((facts.by, facts.outcome, facts.code, facts.stopped), ("script", "ok", 0, False))
        self.assertEqual((facts.logo, facts.colour), ("none", "none"), "no terminal: the plain lines")
        self.assertEqual([(app.app, app.status, app.reason) for app in facts.apps],
                         [("codex", "failed", "command"), ("gemini", "installed", ""), ("cline", "failed", "network")])
        self.assertEqual((facts.found, facts.failed), (3, 2))
        self.assertTrue(all(0 <= app.seconds <= facts.seconds for app in facts.apps))
        self.assertEqual(set(facts.statuses), {app.key for app in apps.APPS})
        self.assertEqual(facts.statuses["claude"], "not found")
        # Every app found failed; then another run going, for a run a server began.
        with self.on_this_computer(FAKE_FAIL="codex,gemini,git:clone"):
            facts = command._run("cad plugin install")
        self.assertEqual((facts.by, facts.outcome, facts.code, facts.found, facts.failed),
                         ("person", "failed", 1, 3, 3))
        with self.another_run(), self.on_this_computer(CAD_INSTALL_ATTEMPT="7.0"):
            facts = command._run("cad plugin install")
        self.assertEqual((facts.by, facts.outcome, facts.code, facts.found, facts.apps), ("server", "busy", 75, 0, []))


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line")
class UpdateTests(PluginRuns):
    def test_update_is_the_same_run_in_this_process_and_keeps_this_release_only_where_it_ended_well(self) -> None:
        self.programs("claude")
        self.keep(**{"for": "0.0.1"})
        done = self.cad_plugin("update", FAKE_FAIL="claude")
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("Claude Code: failed", done.stdout)
        self.assertEqual(self.kept(), {"switch": True, "record": {"for": "0.0.1"}})
        done = self.cad_plugin("update")
        self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
        self.assertEqual(self.calls("claude"), ADD)
        self.assertEqual(done.stdout.splitlines()[:2], ["Setting up the plugin in each agent app found here:",
                                                        "Claude Code: installed"])
        self.assertEqual(self.kept(), {"switch": True, "record": {"for": cad_server.__version__}})

    def test_it_runs_no_install_command_hosted_or_named(self) -> None:
        """The variable that names the bridge's stand-in for the hosted install command is not this command's: named or
        empty, ``cad plugin update`` runs the apps' own commands and nothing else."""
        self.programs("claude", "curl", "sh", "powershell")
        marker = self.root / "ran"
        for named in (f'"{sys.executable}" -c "open(r\'{marker}\', \'w\')"', ""):
            done = self.cad_plugin("update", CAD_ENGINE_UPDATE_INSTALLER=named)
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
            self.assertEqual({name for name in ("claude", "curl", "sh", "powershell", "cad", "uv") if self.calls(name)},
                             {"claude"})
            self.assertFalse(marker.exists())

    def test_a_run_a_server_began_keeps_how_it_ended_has_a_deadline_and_gives_way_to_a_run_going(self) -> None:
        self.programs("claude")
        version = cad_server.__version__
        underway = {"for": "0.0.1", "release": version, "at": 7.0, "tries": 1, "outcome": "underway"}

        def ended() -> tuple:
            record = self.kept()["record"]
            self.assertEqual({key: record[key] for key in ("release", "at", "tries")},
                             {key: underway[key] for key in ("release", "at", "tries")})
            return record["for"], record["outcome"], record.get("code")

        self.keep(**underway)
        done = self.cad_plugin("update", CAD_INSTALL_ATTEMPT="7.0")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(ended(), (version, "ok", 0))
        # Its time up (INSTALL_SECONDS): no command is started, no app begun, the switch left as it is, and it failed.
        self.keep(**underway)
        with mock.patch.object(auto_update_helper, "INSTALL_SECONDS", 0):
            done = self.cad_plugin("update", CAD_INSTALL_ATTEMPT="7.0")
        self.assertEqual((computer.STOPPED, 124, []), (done.returncode, done.returncode, self.calls()))
        self.assertEqual(done.stderr, "cad plugin update: stopped after 0 seconds, all a run the cad server began may "
                                      "take; the apps it had not reached were left as they were\n")
        self.assertNotIn("update auto", done.stdout)
        self.assertEqual(ended(), ("0.0.1", "failed", 124))
        # Another run going: it ends at once, kept as failed, and the server tries again later.
        self.keep(**underway)
        with self.another_run():
            done = self.cad_plugin("update", CAD_INSTALL_ATTEMPT="7.0")
        self.assertEqual((75, []), (done.returncode, self.calls()))
        self.assertEqual(ended(), ("0.0.1", "failed", 75))
        # A person's own run has no deadline, and ends no run of a server's.
        self.keep(**underway)
        with mock.patch.object(auto_update_helper, "INSTALL_SECONDS", 0):
            done = self.cad_plugin("update")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(ended(), (version, "underway", None))

    def test_a_crash_is_kept_as_the_run_s_failure(self) -> None:
        self.keep(**{"for": "0.0.1", "release": cad_server.__version__, "at": 7.0, "tries": 1, "outcome": "underway"})
        with mock.patch.object(run, "install", side_effect=RuntimeError("a mistake of ours")), \
                self.on_this_computer(CAD_INSTALL_ATTEMPT="7.0"), self.assertRaises(RuntimeError):
            command.main(["update"])
        record = self.kept()["record"]
        self.assertEqual((record["for"], record["outcome"], record["code"]), ("0.0.1", "failed", 1))


if __name__ == "__main__":
    unittest.main()
