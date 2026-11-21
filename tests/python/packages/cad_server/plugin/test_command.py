"""``cad plugin install``, and ``cad plugin update``, its hidden second name (``cad_server/cli/plugin.py``,
``cad_server/plugin/run.py``): the whole run on a computer of its own (``tests/python/support/agent_apps.py``: a
temporary home, stand-in programs for the apps' CLIs), its exit statuses, the report it writes, the lock that keeps it
the only run, the switch it never changes, the record a server's run keeps and every other run leaves alone, and what
a run says it was (``run.Facts``)."""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import os
import subprocess
import sys
import time
import types
import unittest
from unittest import mock

import cad_server
from cad_server import analytics, updates
from cad_server._internal import auto_update, auto_update_helper, plugin_catch_up
from cad_server.cli import plugin as command
from cad_server.plugin import apps, computer, run, source
from tests.python.support.agent_apps import CODEX_ADD, PluginRuns

ADD = [["plugin", "marketplace", "add", "earthtojake/text-to-cad#latest"],
       ["plugin", "install", "text-to-cad@earthtojake"]]
# ``cad <argv>`` as the cad of the environment named first, with a step that never comes back: the apps' phase does
# one app and then hangs, whatever the run's deadline. The run has no time at all, and its hard stop a moment's
# grace; so that no clock decides what the test sees, the stop's time comes only once the run is stuck.
STUCK = """
import sys, threading
sys.prefix = sys.argv.pop(1)
from cad_server._internal import auto_update_helper, plugin_catch_up, telemetry_send
from cad_server.cli import main
from cad_server.plugin import apps, run

stuck = threading.Event()

def never(here, source, live=None, each=None):
    each("claude", apps.Outcome("updated"), 2.0)
    stuck.set()
    threading.Event().wait()

run.install_apps = never
auto_update_helper.INSTALL_SECONDS, plugin_catch_up.GRACE_SECONDS = 0, 0.01
stop = plugin_catch_up.HardStop._stop
plugin_catch_up.HardStop._stop = lambda self: (stuck.wait(), stop(self))
telemetry_send._spawn = lambda settings: None
sys.exit(main(sys.argv[1:]))
"""
# A run this release's server began, as it names one; and the name 0.11.12 and 0.11.13 give theirs, which a command
# the hosted install command started under such a run would inherit, but for that command taking it out.
SERVER = {plugin_catch_up.SERVER_ENV: "7.0"}
EARLIER = {plugin_catch_up.ATTEMPT_ENV: "7.0"}
# A release's process outside CI, its telemetry switches unset: one whose runs are counted once a person was told.
COUNTED = {"CAD_INSTALLATION_VERSION": cad_server.__version__, "CI": "", "DO_NOT_TRACK": "", "CAD_TELEMETRY": "",
           analytics.NOTICE_ENV: "", "CAD_UPDATE_CHECK": "0", "CAD_API_URL": "http://127.0.0.1:9"}


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line")
class InstallTests(PluginRuns):
    def test_a_computer_gets_the_plugin_in_every_app_found_and_the_switch_left_as_it_is(self) -> None:
        self.programs("claude", "codex", "gemini", "grok", "muse", "cad", "uv", "curl", "sh")
        (self.home / ".cursor").mkdir()
        (self.home / ".cline").mkdir()
        # Muse has no copy yet: its update fails, and it installs from the `latest` branch fetched once.
        line, environ = self.child("install", FAKE_FAIL="muse:update")
        done = subprocess.run(line, env=environ, capture_output=True, text=True, encoding="utf-8", timeout=120)
        self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
        self.assertEqual(self.calls("claude"), ADD)
        self.assertEqual(self.calls("codex"),
                         [CODEX_ADD,
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
        self.assertEqual(said[-2:], ["", "Start a new session in each app to use it."])
        self.assertNotIn("removed", done.stdout)
        self.assertNotIn("update auto", done.stdout)
        # It runs no cad, no uv and no install command. It installs, and nothing else: the switch is the hosted
        # install command's to turn on, and stays off; this release is kept as the one the plugin is up to date for,
        # a fact about the computer.
        self.assertEqual([name for name in ("cad", "uv", "curl", "sh") if self.calls(name)], [])
        self.assertEqual(self.kept(), {"switch": False, "record": {"for": cad_server.__version__}})

    def test_its_exit_status_says_how_it_ended(self) -> None:
        # 0: it ended well, with nothing found too.
        done = self.run_install()
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertNotIn("Start a new session", done.stdout)
        self.assertEqual(self.kept(), {"switch": False, "record": {"for": cad_server.__version__}})
        # 1: every app it found failed. No release is kept for it.
        self.programs("claude", "codex")
        (self.state / "install-command.json").unlink()
        done = self.run_install(FAKE_FAIL="claude,codex")
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("No app got the plugin: see each app's line above, then run this again.", done.stdout)
        self.assertNotIn("Start a new session", done.stdout)
        # It is owed a run, which the server makes (``plugin_catch_up``).
        self.assertEqual(self.kept(), {"switch": False, "record": {"owed": cad_server.__version__}})
        # One of them failing is the run ending well (exit status 0), but the plugin is up to date for a release only
        # where every app found went well: no release is kept for it either.
        self.assertEqual(0, self.run_install(FAKE_FAIL="codex").returncode)
        self.assertEqual(self.kept(), {"switch": False, "record": {"owed": cad_server.__version__}})
        # 2: a command line it does not take; nothing ran.
        for argv in (["install", "--force"], ["install", "claude"]):
            done = self.cad_plugin(*argv)
            self.assertEqual((2, "", []), (done.returncode, done.stdout, self.calls()), argv)
            self.assertIn("usage: cad plugin", done.stderr)
        # 75: another run is going, and a server began this one. Nothing ran, and one line says so.
        with self.another_run():
            done = self.cad_plugin("install", **SERVER, CAD_PLUGIN_REPORT=str(self.root / "report.json"))
        self.assertEqual((plugin_catch_up.BUSY, 75), (done.returncode, done.returncode))
        self.assertEqual((done.stdout, self.calls()), ("", []))
        self.assertEqual(done.stderr, "cad plugin install: another run is setting up the plugin in the agent apps now, "
                                      "so this one ran nothing\n")
        self.assertFalse((self.root / "report.json").exists(), "a run that ran nothing writes none")

    def test_a_cad_that_is_not_the_global_install_keeps_no_release(self) -> None:
        """For an installed cad with no ``cad plugin install`` (0.11.12, 0.11.13) the hosted install command runs the
        newest release's, from uv's cache. That release is not the installed cad's, and may be of a major it never
        reaches: kept as the one the plugin is up to date for, the installed cad's server, which runs its own plugin
        command only where it is newer than the release kept, would never run it again. So only the computer's global
        install keeps its release; any other cad does the work and leaves the record alone, and turning the switch on
        there keeps none either."""
        self.programs("claude")
        with self.from_elsewhere():
            done = self.run_install()
        self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
        self.assertEqual(self.calls("claude"), ADD)
        self.assertEqual(done.stdout.splitlines()[-1], "Start a new session in each app to use it.")
        self.assertEqual(self.kept(), {"switch": False, "record": {}}, "the next server keeps its own release")
        # What the installed cad kept stays as it was, whichever command the other cad runs.
        self.keep(**{"for": "0.0.1"})
        with self.from_elsewhere():
            for argv, switch in ((["install"], False), (["update"], False), (["update", "auto", "on"], True)):
                self.assertEqual(0, self.cad_plugin(*argv).returncode, argv)
                self.assertEqual(self.kept(), {"switch": switch, "record": {"for": "0.0.1"}}, argv)
        # The installed cad's own run keeps its release.
        self.assertEqual(0, self.run_install().returncode)
        self.assertEqual(self.kept(), {"switch": True, "record": {"for": cad_server.__version__}})

    def test_update_is_install_by_another_name_and_no_help_lists_it(self) -> None:
        """``cad plugin update`` is the name 0.11.12 and 0.11.13 gave the run, which released skills and scripts may
        type: parsed, run exactly as ``install`` is, and listed by no help. ``cad plugin update auto`` is the switch,
        as it was."""
        self.programs("claude")
        listed = self.cad_plugin("--help").stdout
        self.assertIn("{install}", listed)
        self.assertNotRegex(listed, r"(?m)^\s+update\s{2,}")  # no line of the list of commands
        self.assertNotIn("{install,update}", listed)
        self.assertIn("usage: cad plugin update [-h] [auto [{status,on,off}]]",
                      self.cad_plugin("update", "--help").stdout)
        installed = self.run_install()
        installed_calls = self.calls()
        updated = self.cad_plugin("update")
        self.assertEqual((installed.returncode, installed.stdout, installed.stderr),
                         (updated.returncode, updated.stdout.replace("cad plugin update", "cad plugin install"),
                          updated.stderr.replace("cad plugin update", "cad plugin install")))
        self.assertEqual(self.calls(), installed_calls)
        self.assertEqual(self.calls("claude"), ADD)
        self.assertEqual(self.kept(), {"switch": False, "record": {"for": cad_server.__version__}})
        self.assertEqual(self.cad_plugin("update", "auto").stdout, "plugin update auto: off\n")
        self.assertEqual(self.cad_plugin("update", "auto", "on").stdout, "plugin update auto: on\n")
        self.assertEqual(self.calls(), [], "the switch runs nothing")

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
            busy = subprocess.run(line, env={**environ, **SERVER}, capture_output=True, text=True,
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
        for began_by in (SERVER, {}):
            with contextlib.ExitStack() as asking, self.subTest(began_by=began_by):
                asking.enter_context(file_lock.exclusive(self.state / plugin_catch_up.LOCK))
                # The one who asked lets go while the run waits its first step. ``time.sleep`` is the one function for
                # every module, so only the lock's own step is taken over: whatever else sleeps in the run (on Python
                # 3.11, a wait on a command with a time limit) sleeps as it would.
                def step(seconds: float, sleep=time.sleep) -> None:
                    if seconds == plugin_catch_up.SETTLE_STEP:
                        asking.close()
                    else:
                        sleep(seconds)

                with mock.patch.object(plugin_catch_up.time, "sleep", side_effect=step) as slept:
                    done = self.cad_plugin("install", **began_by)
                slept.assert_any_call(plugin_catch_up.SETTLE_STEP)
                self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
                self.assertNotIn("Another run", done.stdout)
                self.assertEqual(self.calls("claude"), ADD)

    def test_the_server_an_install_command_s_update_restarted_leaves_the_plugin_to_that_command(self) -> None:
        """A person runs the hosted install command on a computer whose server runs, ``cad plugin update auto`` on. It
        updates cad by that cad's own ``cad update``, which restarts the server, and a moment later hands over to
        ``cad plugin install``. The new server is newer than the release the plugin is up to date for, but begins
        nothing in its first minute (``plugin_catch_up.START_SECONDS``, its clock driven here) nor while a run holds
        the lock; the person's run does the work and keeps this release, so the server, asking after it, begins none.
        Each app gets the plugin once. A run the server began would be a process of its own here, its apps' commands
        logged as the person's are."""
        self.programs("claude", "codex")
        self.keep(**{"for": "0.0.1"})  # up to date for the release before the update
        (self.state / "settings.json").write_text(json.dumps({"plugin": {"auto_update": True}}), encoding="utf-8")
        clock = [1000.0]
        server = plugin_catch_up.Catcher(clock[0], clock=lambda: clock[0])  # the new server, just started
        begun: list = []
        ours, real_popen = str(auto_update.tool_command(self.tool)), subprocess.Popen

        def popen(line, **options):  # ``subprocess.Popen`` is every module's: only the server's run is taken over
            if line[0] != ours:
                return real_popen(line, **options)
            begun.append(line)
            argv, environ = self.child("install", **{plugin_catch_up.SERVER_ENV:
                                                     options["env"][plugin_catch_up.SERVER_ENV]})
            code = subprocess.run(argv, env=environ, capture_output=True, timeout=120).returncode
            return types.SimpleNamespace(poll=lambda: code)

        def tend(seconds: float) -> bool:
            clock[0] = 1000.0 + seconds
            return server.tend(lambda _line: None)

        during: list = []
        real = run.install_apps

        def person_s(*args, **options):  # the server tends while the person's run holds the lock, its minute past
            during.append(tend(plugin_catch_up.START_SECONDS + 1))
            return real(*args, **options)

        with mock.patch.object(updates, "checking", return_value=True), \
                mock.patch.object(plugin_catch_up.subprocess, "Popen", side_effect=popen):
            with self.on_this_computer():
                self.assertTrue(plugin_catch_up.due(), "the rule alone would run it")
                self.assertEqual((tend(0.0), tend(1.0)), (False, False), "the server's start, and a moment later")
            with mock.patch.object(run, "install_apps", side_effect=person_s):
                done = self.run_install(CAD_PLUGIN_BY="script")
            self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
            self.assertNotIn("Another run", done.stdout)
            with self.on_this_computer():
                for seconds in (plugin_catch_up.START_SECONDS + 30, 5 * plugin_catch_up.RETRY_SECONDS):
                    self.assertFalse(tend(seconds), seconds)
        self.assertEqual((during, begun), ([False], []))
        self.assertEqual((self.calls("claude"), len(self.calls("codex"))), (ADD, 2))
        self.assertEqual(self.kept(), {"switch": True, "record": {"for": cad_server.__version__}})

    def test_a_state_folder_it_may_not_lock_never_stops_the_run(self) -> None:
        self.programs("claude")
        with mock.patch("cad_server._internal.file_lock.attempt", side_effect=PermissionError("read-only")), \
                mock.patch("cad_server._internal.file_lock.exclusive", side_effect=PermissionError("read-only")):
            done = self.run_install()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(self.calls("claude"), ADD)

    def test_run_by_cad_every_rename_is_cad_s_one_rename(self) -> None:
        """The table's modules are the standard library alone, and rename with it where a checkout's development
        install loads them without cad; the command gives them cad's rename, which every file cad writes goes by."""
        from cad._internal.atomic_replace import replace_atomic

        self.assertIs(computer.rename, replace_atomic)

    def test_only_this_release_s_server_names_a_server_s_run(self) -> None:
        """A server of 0.11.12 or 0.11.13 names its run ``CAD_INSTALL_ATTEMPT``, and runs its own ``cad plugin
        update``, whose hosted install command everything below inherits that name from. A run here that inherits it
        alone is no server's: it takes no deadline and no hard stop, waits for the lock as a person's run does, and
        leaves the record's run as it is -- the earlier command's to end. Only the name this release's server gives its
        run (``SERVER_ENV``, which no released cad sets) makes one."""
        self.programs("claude")
        underway = {"release": "0.0.2", "at": 7.0, "tries": 1, "outcome": "underway"}
        self.keep(**{"for": "0.0.1"}, **underway)
        with mock.patch.object(plugin_catch_up, "HardStop") as stop, \
                mock.patch.object(auto_update_helper, "INSTALL_SECONDS", 0):
            for name in ("install", "update"):
                failed = self.cad_plugin(name, **EARLIER, FAKE_FAIL="claude")
                self.assertEqual(1, failed.returncode, failed.stdout)
                self.assertEqual(self.kept()["record"], {"for": "0.0.1", "owed": cad_server.__version__, **underway},
                                 "its run untouched, every field; this release owed a run")
            with self.on_this_computer(**EARLIER):
                self.assertIsNone(plugin_catch_up.deadline())
                self.assertEqual(run.began_by(os.environ), run.PERSON)
        self.assertEqual(stop.call_count, 0)
        self.forget_calls()
        with self.another_run():  # it waits for the lock, where a server's run would end 75
            line, environ = self.child("install", **EARLIER)
            waiting = subprocess.Popen(line, env=environ, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                       encoding="utf-8")
            self.addCleanup(waiting.kill)
            self.assertIn("this one waits for it to end, then runs", waiting.stdout.readline())
        out, err = waiting.communicate(timeout=120)
        self.assertEqual((waiting.returncode, err), (0, ""), out)
        self.assertEqual(self.calls("claude"), ADD)
        # Ended well on the global install, it keeps this release as the one the plugin is up to date for, as any run
        # does; the run of the record stays the earlier server's.
        self.assertEqual(self.kept()["record"], {"for": cad_server.__version__, **underway}, "and owed none")
        # This release's server's own name is the one that makes a server's run: its deadline, and its record closed.
        self.keep(**{"for": "0.0.1"}, **underway)
        with self.on_this_computer(**SERVER):
            self.assertEqual(plugin_catch_up.deadline(), float(auto_update_helper.INSTALL_SECONDS))
            self.assertEqual(run.began_by(os.environ), run.SERVER)
        self.assertEqual(0, self.cad_plugin("install", **SERVER).returncode)
        record = self.kept()["record"]
        self.assertEqual((record["outcome"], record["code"]), ("ok", 0))

    def test_a_run_says_what_it_was_for_whoever_counts_it(self) -> None:
        """``run.Facts``, made in one place: who began the run, how it ended, each app found with its status, the
        word for why it failed and its seconds, and what the terminal was shown."""
        self.assertEqual([run.began_by(environ) for environ in (
            {}, {"CAD_PLUGIN_BY": "script"}, {"CAD_PLUGIN_BY": "someone"}, SERVER, {**SERVER, "CAD_PLUGIN_BY": "script"},
            EARLIER, {**EARLIER, "CAD_PLUGIN_BY": "script"})],
            ["person", "script", "person", "server", "server", "person", "script"])
        self.programs("codex", "gemini")
        (self.home / ".cline").mkdir()  # its skills come from GitHub, which nothing reaches here
        # The facts are there from the run's start and filled as it goes, each app as it is done, for whoever must
        # say what a run was that never ended (its hard stop): seen here as the second app's command runs.
        going: list = []
        so_far: list = []
        real = computer.Here.run

        def watched(here, argv, **options):
            if os.path.basename(str(argv[0])) == "gemini":
                so_far.append([(app.app, app.status, app.reason) for app in going[0].apps])
            return real(here, argv, **options)

        with self.on_this_computer(FAKE_FAIL="codex,git:clone", CAD_PLUGIN_BY="script"), \
                mock.patch.object(computer.Here, "run", watched):
            facts = run.install(prog="cad plugin install", going=going.append)
        self.assertIs(going[0], facts)
        self.assertEqual(so_far[0], [("codex", "failed", "command")])
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
        with self.another_run(), self.on_this_computer(**SERVER):
            facts = command._run("cad plugin install")
        self.assertEqual((facts.by, facts.outcome, facts.code, facts.found, facts.apps), ("server", "busy", 75, 0, []))


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line")
class UpdateTests(PluginRuns):
    def test_a_run_keeps_this_release_only_where_it_ended_well(self) -> None:
        self.programs("claude")
        self.keep(**{"for": "0.0.1"})
        done = self.cad_plugin("update", FAKE_FAIL="claude")
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertIn("Claude Code: failed", done.stdout)
        self.assertEqual(self.kept(), {"switch": False, "record": {"for": "0.0.1", "owed": cad_server.__version__}})
        done = self.cad_plugin("update")
        self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
        self.assertEqual(self.calls("claude"), ADD)
        self.assertEqual(done.stdout.splitlines()[:2], ["Setting up the plugin in each agent app found here:",
                                                        "Claude Code: installed"])
        self.assertEqual(self.kept(), {"switch": False, "record": {"for": cad_server.__version__}})

    def test_it_runs_no_install_command_hosted_or_named(self) -> None:
        """The variable that names the bridge's stand-in for the hosted install command is not this command's: named or
        empty, ``cad plugin install`` (by either name) runs the apps' own commands and nothing else."""
        self.programs("claude", "curl", "sh", "powershell")
        marker = self.root / "ran"
        for named, typed in itertools.product((f'"{sys.executable}" -c "open(r\'{marker}\', \'w\')"', ""),
                                              ("install", "update")):
            done = self.cad_plugin(typed, CAD_ENGINE_UPDATE_INSTALLER=named)
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
        done = self.cad_plugin("install", **SERVER)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(ended(), (version, "ok", 0))
        # Its time up (INSTALL_SECONDS): no command is started, no app begun, the switch left as it is, and it failed.
        self.keep(**underway)
        with mock.patch.object(auto_update_helper, "INSTALL_SECONDS", 0):
            done = self.cad_plugin("install", **SERVER)
        self.assertEqual((computer.STOPPED, 124, []), (done.returncode, done.returncode, self.calls()))
        self.assertEqual(done.stderr, "cad plugin install: stopped after 0 seconds, all a run the cad server began may "
                                      "take; the apps it had not reached were left as they were\n")
        self.assertNotIn("update auto", done.stdout)
        self.assertEqual(ended(), ("0.0.1", "failed", 124))
        # Another run going: it ends at once, kept as failed, and the server tries again later.
        self.keep(**underway)
        with self.another_run():
            done = self.cad_plugin("install", **SERVER)
        self.assertEqual((75, []), (done.returncode, self.calls()))
        self.assertEqual(ended(), ("0.0.1", "failed", 75))
        # A person's own run has no deadline, and ends no run of a server's.
        self.keep(**underway)
        with mock.patch.object(auto_update_helper, "INSTALL_SECONDS", 0):
            done = self.cad_plugin("install")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertEqual(ended(), (version, "underway", None))

    def test_a_run_where_one_app_failed_is_tried_again_as_a_failed_run_at_most_three_times(self) -> None:
        """The plugin is up to date for a release only where every app found went well. A run where one app failed
        and the others went well exits 0, keeps no release, and, where a server began it, closes its record as failed:
        the server tries it again an hour later and not before, at most three runs for one release, and then nothing
        more for that release. One where every app went well, or that found none, is up to date."""
        version = cad_server.__version__
        now = time.time()

        def server_run(tries: int, at: float, **extra: str) -> dict:
            # The record as the server keeps a run it begins (``plugin_catch_up._begin``), then the run itself.
            self.keep(**{**{key: value for key, value in self.kept()["record"].items() if key not in ("code", "ended")},
                         "release": version, "at": at, "tries": tries, "outcome": "underway"})
            done = self.cad_plugin("install", **{plugin_catch_up.SERVER_ENV: str(at)}, **extra)
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
            return self.kept()["record"]

        # No app found: nothing to retry, and up to date.
        self.keep(**{"for": "0.0.1"})
        record = server_run(1, now)
        self.assertEqual((record["for"], record["outcome"], record["code"]), (version, "ok", 0))
        self.assertFalse(plugin_catch_up._wanted(record, version, now + plugin_catch_up.RETRY_SECONDS))
        self.programs("claude", "codex")
        # A person's run, one app failing: exit status 0, no release kept.
        self.keep(**{"for": "0.0.1"})
        done = self.cad_plugin("install", FAKE_FAIL="codex")
        self.assertEqual(0, done.returncode, done.stdout)
        self.assertIn("Codex: failed", done.stdout)
        self.assertEqual(self.kept(), {"switch": False, "record": {"for": "0.0.1", "owed": version}})
        # A server's, the same: kept as failed, try 1 of 3, and wanted again an hour after it began, not before.
        at = now
        for tries in range(1, plugin_catch_up.TRIES + 1):
            record = server_run(tries, at, FAKE_FAIL="codex")
            self.assertEqual((record["for"], record["outcome"], record["code"], record["tries"]),
                             ("0.0.1", "failed", 0, tries))
            self.assertFalse(plugin_catch_up._wanted(record, version, at + plugin_catch_up.RETRY_SECONDS - 1))
            later = at + plugin_catch_up.RETRY_SECONDS
            self.assertEqual(plugin_catch_up._wanted(record, version, later), tries < plugin_catch_up.TRIES, tries)
            at = later
        # Three such runs, then nothing more for this release, however long after.
        self.assertFalse(plugin_catch_up._wanted(record, version, at + 100 * plugin_catch_up.RETRY_SECONDS))
        # A run where every app went well is kept as ok, and the plugin up to date for this release.
        record = server_run(1, now)
        self.assertEqual((record["for"], record["outcome"], record["code"]), (version, "ok", 0))
        self.assertFalse(plugin_catch_up._wanted(record, version, now + plugin_catch_up.RETRY_SECONDS))

    def test_a_run_a_server_began_that_never_comes_back_is_ended_for_certain(self) -> None:
        """The deadline is asked between a run's steps, so a step that never comes back would hold the run's lock, and
        with it cad's own update and every run that waits, for as long as the process lived. The command's hard stop
        (``plugin_catch_up.HardStop``) ends it a short while past the deadline: the record closed as a stopped run's,
        one line, the run counted as stopped with the apps it had done, and the process gone with 124, its lock
        free."""
        underway = {"for": "0.0.1", "release": cad_server.__version__, "at": 7.0, "tries": 1, "outcome": "underway"}
        self.keep(**underway)
        with self.on_this_computer(**COUNTED):
            self.assertTrue(analytics.notify(io.StringIO()))  # a person was told: the server's runs are counted
        line, environ = self.child("install", **SERVER, **COUNTED)
        done = subprocess.run([line[0], "-c", STUCK, *line[3:]], env=environ, capture_output=True, text=True,
                              encoding="utf-8", timeout=120)
        self.assertEqual((done.returncode, done.stdout), (124, "Setting up the plugin in each agent app found here:\n"))
        self.assertRegex(done.stderr, r"\Acad plugin install: ended after \d+ seconds, past the 0 a run the cad server "
                                      r"began may take: a step of it never came back, and what it had not done was "
                                      r"left as it was\n\Z")
        kept = self.kept()
        self.assertEqual((kept["switch"], kept["record"]["for"], kept["record"]["outcome"], kept["record"]["code"]),
                         (False, "0.0.1", "failed", 124))
        with mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.state)}):
            self.assertFalse(plugin_catch_up.running(), "the lock went with the process")
        [counted] = [json.loads(row)["install"] for row in
                     (self.state / analytics.INSTALLS).read_text(encoding="utf-8").splitlines()]
        self.assertEqual({name: counted[name] for name in ("by", "outcome", "found", "failed", "failures")},
                         {"by": "server", "outcome": "stopped", "found": 1, "failed": 0, "failures": []},
                         "the app it had updated is counted, never named")

    def test_a_crash_is_kept_as_the_run_s_failure(self) -> None:
        self.keep(**{"for": "0.0.1", "release": cad_server.__version__, "at": 7.0, "tries": 1, "outcome": "underway"})
        with mock.patch.object(run, "install", side_effect=RuntimeError("a mistake of ours")), \
                self.on_this_computer(**SERVER), self.assertRaises(RuntimeError):
            command.main(["install"])
        record = self.kept()["record"]
        self.assertEqual((record["for"], record["outcome"], record["code"]), ("0.0.1", "failed", 1))


if __name__ == "__main__":
    unittest.main()
