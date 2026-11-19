"""A run of ``cad plugin install`` or ``cad plugin update``, counted (``cad_server.cli.plugin``: ``_tell``, ``_count``;
``cad_server.analytics.install``): from what the run says it was (``run.Facts``) to the batch the sender would post --
one ``install`` event and one ``install_app`` for each app found, words of cad's and whole numbers, runs alike one row
with a count --, kept in a file of its own with a sender started at once, under every rule a count goes by; who is
told what is sent, and who is not; and a crash of the command, which is reported as every command's is. Every run here
is on a computer of its own (``tests/python/support/agent_apps.py``): a temporary home and state folder, stand-in
programs for the apps."""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import cad_server
from cad_server import analytics
from cad_server._internal import auto_update_helper, file_lock, telemetry_send
from cad_server.cli import plugin as command
from cad_server.plugin import apps, computer, run, terminal
from tests.python.support.agent_apps import PluginRuns

RELEASE = cad_server.__version__
# A release's process outside CI, its telemetry switches unset (``test_arrival``'s ``QUIET``).
QUIET = {"CAD_INSTALLATION_VERSION": RELEASE, "CI": "", "DO_NOT_TRACK": "", "CAD_TELEMETRY": "",
         analytics.NOTICE_ENV: "", "CAD_UPDATE_CHECK": "0", "CAD_API_URL": "http://127.0.0.1:9"}


def facts(by: str = "person", *found: tuple, **said) -> run.Facts:
    """What a run says it was: begun by ``by``, with ``found`` its apps, each ``(key, status, reason, seconds)``."""
    return run.Facts(by=by, apps=[run.AppFact(*each) for each in found], **said)


def kept(settings: Path) -> list[dict]:
    """The runs kept beside ``settings`` for a sender, each as its line keeps it."""
    found = settings.with_name(analytics.INSTALLS)
    lines = found.read_text(encoding="utf-8").splitlines() if found.exists() else []
    return [json.loads(line)["install"] for line in lines]


def sent(settings: Path) -> list[dict]:
    """The batches the sender would post of what is kept beside ``settings``, taken as it takes them."""
    payloads: list[dict] = []
    telemetry_send.send(settings, send=lambda payload: payloads.append(payload) or True)
    return payloads


class CountedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="install-counted-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {**QUIET, "CAD_STATE_DIR": str(self.tmp / "state")})
        environment.start()
        self.addCleanup(environment.stop)
        self.settings = analytics.settings_path()
        self.assertEqual(self.settings, self.tmp / "state" / "settings.json")
        self.started: list[Path] = []
        spawn = mock.patch.object(telemetry_send, "_spawn", self.started.append)
        spawn.start()
        self.addCleanup(spawn.stop)

    def tell(self) -> None:
        self.assertTrue(analytics.notify(io.StringIO(), path=self.settings))

    def count(self, found: run.Facts) -> None:
        command._count(found, analytics.in_force())

    def test_a_run_and_each_app_it_found_are_kept_in_one_line_and_sent_as_words_and_whole_numbers(self) -> None:
        self.tell()
        self.count(facts("script", ("claude", "installed", "", 3.2), ("codex", "failed", "command", 0.4),
                         ("cline", "failed", "", 61.9), ("gemini", "skipped", "", 0.0),
                         logo="played", colour="24bit", seconds=72.9,
                         statuses={"claude": "installed", "pi": "not found"}))
        # One line for the run with its apps, in a file of its own: never the spool or the arrivals, which a sender
        # of an earlier release takes whole and keeps only what it knows of.
        self.assertEqual(kept(self.settings), [
            {"by": "script", "outcome": "ok", "logo": "played", "colour": "24bit", "seconds": 72, "found": 4,
             "failed": 2,
             "apps": [{"app": "claude", "status": "installed", "seconds": 3},
                      {"app": "codex", "status": "failed", "reason": "command", "seconds": 0},
                      {"app": "cline", "status": "failed", "reason": "other", "seconds": 61},
                      {"app": "gemini", "status": "skipped", "seconds": 0}]}])
        self.assertEqual(sorted(path.name for path in self.settings.parent.iterdir()),
                         ["settings.json", "settings.lock", analytics.INSTALLS])
        self.assertEqual(self.started, [self.settings], "a sender at once: the run may be cad's last for a long while")
        [batch] = sent(self.settings)
        self.assertEqual((batch["schema"], batch["process"], batch["version"]), (12, "cli", RELEASE))
        self.assertNotIn("client", batch)
        self.assertEqual(batch["events"], [
            {"name": "install", "by": "script", "outcome": "ok", "logo": "played", "colour": "24bit", "seconds": 72,
             "found": 4, "failed": 2, "count": 1},
            {"name": "install_app", "app": "claude", "status": "installed", "seconds": 3, "count": 1},
            {"name": "install_app", "app": "cline", "status": "failed", "reason": "other", "seconds": 61, "count": 1},
            {"name": "install_app", "app": "codex", "status": "failed", "reason": "command", "seconds": 0, "count": 1},
            {"name": "install_app", "app": "gemini", "status": "skipped", "seconds": 0, "count": 1},
        ])
        for event in batch["events"]:  # whole numbers: the receiver refuses a fraction, and a null reason
            self.assertTrue(all(type(event[name]) is int for name in ("seconds", "count")), event)
            self.assertNotIn(None, event.values())
        self.assertFalse(self.settings.with_name(analytics.INSTALLS).exists(), "taken by the sender")

    def test_runs_alike_and_apps_alike_are_one_row_each_with_a_count(self) -> None:
        self.tell()
        for _ in range(3):  # a server's run, stopped at its deadline and tried again: the same every time
            self.count(facts("server", ("claude", "updated", "", 2.2), ("codex", "failed", "timeout", 900.5),
                             seconds=903.1, outcome=run.FAILED, code=computer.STOPPED, stopped=True))
        self.count(facts("server", ("claude", "updated", "", 2.9), ("codex", "updated", "", 4.0), seconds=7.5))
        self.assertEqual(len(kept(self.settings)), 4)
        [batch] = sent(self.settings)
        self.assertEqual(batch["events"], [
            {"name": "install", "by": "server", "outcome": "ok", "logo": "none", "colour": "none", "seconds": 7,
             "found": 2, "failed": 0, "count": 1},
            {"name": "install", "by": "server", "outcome": "stopped", "logo": "none", "colour": "none",
             "seconds": 903, "found": 2, "failed": 1, "count": 3},
            {"name": "install_app", "app": "claude", "status": "updated", "seconds": 2, "count": 4},
            {"name": "install_app", "app": "codex", "status": "failed", "reason": "timeout", "seconds": 900,
             "count": 3},
            {"name": "install_app", "app": "codex", "status": "updated", "seconds": 4, "count": 1},
        ])
        # A batch holds each shape once (everything but its count): what the receiver refuses a batch for.
        shapes = [json.dumps({name: value for name, value in event.items() if name != "count"}, sort_keys=True)
                  for event in batch["events"]]
        self.assertEqual(len(shapes), len(set(shapes)))

    def test_how_a_run_ended_is_read_from_its_apps_and_never_denied_by_them(self) -> None:
        """Of a run that ended, ``failed`` is every app found failed, and nothing else: the receiver refuses a row that
        says otherwise, and its whole batch with it. So whether it ended well is decided where its apps are counted,
        whatever the run's own word for itself was. A run that ran nothing is ``busy``, and one its deadline stopped
        ``stopped``, with whatever it had found by then."""
        self.tell()
        down, fine = ("codex", "failed", "command", 1.0), ("claude", "installed", "", 1.0)

        def counted(found: run.Facts) -> tuple:
            self.count(found)
            [row] = kept(self.settings)
            self.settings.with_name(analytics.INSTALLS).unlink()
            return row["outcome"], row["found"], row["failed"], len(row["apps"])

        self.assertEqual(counted(facts("person")), ("ok", 0, 0, 0), "no app found: it ended well")
        self.assertEqual(counted(facts("person", fine, down)), ("ok", 2, 1, 2))
        self.assertEqual(counted(facts("person", down, outcome=run.FAILED, code=1)), ("failed", 1, 1, 1))
        # Another run was going: it ran nothing and names no app.
        self.assertEqual(counted(facts("server", outcome=run.BUSY, code=75)), ("busy", 0, 0, 0))
        self.assertEqual(counted(facts("server", fine, outcome=run.BUSY, code=75)), ("busy", 0, 0, 0))
        # A run its deadline stopped exits as failed, and is counted as stopped, whatever it had found by then: never
        # as one that ended well, nor as one in which every app failed.
        stopped = dict(outcome=run.FAILED, code=computer.STOPPED, stopped=True)
        self.assertEqual(counted(facts("server", down, **stopped)), ("stopped", 1, 1, 1))
        self.assertEqual(counted(facts("server", fine, down, **stopped)), ("stopped", 2, 1, 2))
        self.assertEqual(counted(facts("server", fine, **stopped)), ("stopped", 1, 0, 1))
        self.assertEqual(counted(facts("server", **stopped)), ("stopped", 0, 0, 0))
        self.assertEqual(counted(facts("server", stopped=True)), ("stopped", 0, 0, 0), "whatever else it said")
        # A run that named itself wrongly cannot be counted wrongly: its apps say how it ended.
        self.assertEqual(counted(facts("person", down, down[:1] + ("failed", "network", 2.0), outcome=run.OK)),
                         ("failed", 2, 2, 2))
        self.assertEqual(counted(facts("person", fine, outcome=run.FAILED, code=1)), ("ok", 1, 0, 1))

    def test_only_words_of_the_vocabulary_and_whole_seconds_within_bounds_are_counted(self) -> None:
        self.tell()
        count = analytics.install
        fine = ("claude", "installed", None, 1.0)
        for refused in (dict(by="someone"), dict(by="person", logo="spinning"), dict(by="person", colour="16"),
                        dict(by="person", seconds=-1.0), dict(by="person", seconds=float("nan")),
                        dict(by="person", seconds=True), dict(by="person", seconds="12"), dict(by="person", busy="yes"),
                        dict(by="person", apps=[("Claude Code", "installed", None, 1.0)]),
                        dict(by="person", apps=[("/Users/someone/.claude", "installed", None, 1.0)]),
                        dict(by="person", apps=[("c" * 41, "installed", None, 1.0)]),
                        dict(by="person", apps=[("claude", "not found", None, 1.0)]),
                        dict(by="person", apps=[("claude", "installed", None, None)]),
                        dict(by="person", apps=[("claude", "installed")]), dict(by="person", apps="claude"),
                        dict(by="person", apps=[fine] * (analytics.MAX_INSTALL_APPS + 1)),
                        dict(by="server", busy=True, apps=[fine]), dict(by="server", busy=True, stopped=True),
                        dict(by="server", stopped="yes")):
            self.assertFalse(count(**refused), refused)
        self.assertEqual((kept(self.settings), self.started), ([], []))
        # A reason outside the words is ``other``, and one on an app that did not fail goes no further; seconds past
        # the most are the most; a run may find as many apps as the receiver reads.
        self.assertTrue(count(by="person", logo="failed", colour="256", seconds=10.0 ** 9, apps=[
            ("codex", "failed", "codex: something went wrong", 10 ** 7), ("claude", "removed", "network", 0.999)]))
        self.assertTrue(count(by="script", logo="still", apps=[fine] * analytics.MAX_INSTALL_APPS))
        first, second = kept(self.settings)
        self.assertEqual(first, {
            "by": "person", "outcome": "ok", "logo": "failed", "colour": "256",
            "seconds": analytics.MAX_INSTALL_SECONDS, "found": 2, "failed": 1,
            "apps": [{"app": "codex", "status": "failed", "reason": "other", "seconds": analytics.MAX_INSTALL_SECONDS},
                     {"app": "claude", "status": "removed", "seconds": 0}]})
        self.assertEqual((second["found"], second["failed"], second["outcome"]), (analytics.MAX_INSTALL_APPS, 0, "ok"))
        # A line changed on disk is checked again as it is taken: one no run would keep is not sent, no part of it.
        answer = list(analytics._answer(analytics._read(self.settings)))
        changed = [dict(first, outcome="failed"), dict(first, found=3), dict(first, seconds=1.5),
                   dict(first, apps=first["apps"] + [{"app": "/home/someone", "status": "installed", "seconds": 1}]),
                   dict(first, apps=[dict(first["apps"][1], reason=None)], found=1, failed=0),
                   dict(first, apps="claude")]
        with open(self.settings.with_name(analytics.INSTALLS), "a", encoding="utf-8") as handle:
            for row in changed:
                handle.write(json.dumps({"answer": answer, "at": time.time(), "source": {}, "install": row}) + "\n")
        [batch] = sent(self.settings)
        self.assertEqual([event["count"] for event in batch["events"] if event["name"] == "install"], [1, 1])
        self.assertNotIn("someone", json.dumps(batch))

    def test_nothing_is_kept_untold_after_a_no_in_ci_from_a_development_build_or_by_the_environment(self) -> None:
        found = facts("person", ("claude", "installed", "", 1.0))
        self.count(found)
        self.assertEqual(analytics.status(path=self.settings)["reason"], "untold", "nobody told yet")
        self.assertEqual((kept(self.settings), self.started), ([], []))
        self.tell()
        for switches in ({"DO_NOT_TRACK": "1"}, {"CAD_TELEMETRY": "0"}, {"CI": "true"},
                         {"CAD_INSTALLATION_VERSION": f"{RELEASE}-dev.20261119120000"}):
            with mock.patch.dict(os.environ, switches):
                self.count(found)
        self.assertEqual((kept(self.settings), self.started), ([], []))
        # A run that began under another answer -- before the person was told, before a yes -- is not kept as it ends.
        command._count(found, [None, None])
        command._count(found, analytics._UNREAD)
        self.assertEqual(kept(self.settings), [])
        self.count(found)
        self.assertEqual(len(kept(self.settings)), 1)
        analytics.choose(False, by="cli", path=self.settings)
        self.assertFalse(self.settings.with_name(analytics.INSTALLS).exists(), "a no deletes what was kept")
        self.count(found)
        self.assertEqual((kept(self.settings), sent(self.settings)), ([], []))

    def test_a_count_never_fails_the_run_and_one_left_waiting_is_found_by_the_next_command(self) -> None:
        self.tell()
        found = facts("person", ("claude", "installed", "", 1.0))
        # Counting raises nothing into the command, whatever fails under it: the state folder, the sender's start.
        with mock.patch.object(analytics, "_keep", side_effect=OSError("read-only")):
            self.count(found)
        with mock.patch.object(analytics, "install", side_effect=RuntimeError("a mistake of ours")):
            self.count(found)
        command._count(object(), analytics.in_force())  # no run at all
        self.assertEqual(kept(self.settings), [])
        with mock.patch.object(telemetry_send, "_spawn", side_effect=OSError("no such program")):
            self.count(found)
        self.assertEqual((len(kept(self.settings)), self.started), (1, []), "kept, though no sender started")
        # The sender a later command starts for what has waited a window takes it (``start_if_due``).
        long_ago = time.time() - 2 * analytics.FLUSH_SECONDS
        os.utime(self.settings.with_name(file_lock.STATE_LOCK), (long_ago, long_ago))
        self.assertFalse(telemetry_send.start_if_due(self.settings))
        self.assertTrue(telemetry_send.start_if_due(self.settings, now=time.time() + 2 * analytics.FLUSH_SECONDS))
        self.assertEqual(self.started, [self.settings])

    def test_the_words_a_run_says_are_the_words_counted(self) -> None:
        """What ``run.Facts`` can say and what telemetry counts are one vocabulary: a word of one the other lacks would
        leave a run uncounted."""
        self.assertEqual({run.PERSON, run.SCRIPT, run.SERVER}, analytics.INSTALL_BY)
        # A run says its deadline stopped it apart (``Facts.stopped``), its exit status that of one that failed.
        self.assertEqual({run.OK, run.FAILED, run.BUSY} | {"stopped"}, analytics.INSTALL_OUTCOMES)
        self.assertEqual({terminal.PLAYED, terminal.STILL, terminal.NONE, run.LOGO_FAILED}, analytics.INSTALL_LOGOS)
        self.assertEqual(set(computer.REASONS), analytics.INSTALL_FAILURES)
        self.assertEqual({"installed", "updated", "removed", "skipped", "failed"}, analytics.INSTALL_STATUSES)
        self.assertLessEqual(len(apps.APPS), analytics.MAX_INSTALL_APPS)
        for app in apps.APPS:
            self.assertRegex(app.key, r"\A[a-z0-9][a-z0-9._-]{0,39}\Z")
        # Every status an app's row can have in a run's report, but the one of an app that is not there.
        for status in sorted(analytics.INSTALL_STATUSES):
            self.assertIsNotNone(analytics._install_run("person", False, False, "none", "none", 0.0,
                                                        [("claude", status, "", 0.0)]))
        for colour in ("24bit", "256", "none"):  # ``terminal.Screen.colour``'s three
            self.assertIn(colour, analytics.INSTALL_COLOURS)
        self.assertEqual(len(analytics.INSTALL_COLOURS), 3)

    def test_everything_a_count_uses_is_imported_before_the_run_begins(self) -> None:
        """An update of cad by hand may replace the environment's files under a run: a module first imported as the
        run is counted would be another release's. So counting imports nothing of cad's the command had not."""
        program = (
            "import io, os, sys\n"
            "from cad_server.cli import plugin as command\n"
            "command._load()\n"
            "from cad_server import analytics\n"
            "from cad_server._internal import telemetry_send\n"
            "from cad_server.plugin import run\n"
            "telemetry_send._spawn = lambda settings: None\n"
            "assert analytics.notify(io.StringIO())\n"
            "before = set(sys.modules)\n"
            "command._count(run.Facts(by='person', apps=[run.AppFact('claude', 'failed', 'command', 1.0)]),"
            " analytics.in_force())\n"
            "assert os.path.exists(os.path.join(os.environ['CAD_STATE_DIR'], analytics.INSTALLS))\n"
            "new = set(sys.modules) - before\n"
            "print(sorted(name for name in new if name.split('.')[0] in ('cad', 'cad_server')))\n")
        import subprocess

        done = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, timeout=120,
                              env={**os.environ, "PYTHONPATH": os.pathsep.join(entry for entry in sys.path if entry)})
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "[]"), done.stderr)


@unittest.skipIf(os.name == "nt", "the stand-ins are scripts run by their #! line")
class ToldTest(PluginRuns):
    """Who is told what cad sends before a run, and so whose run is counted: the whole command, on a computer of its
    own where nobody has been told yet."""

    def setUp(self) -> None:
        super().setUp()
        self.programs("claude")
        self.settings = self.state / "settings.json"
        self.started: list[Path] = []
        spawn = mock.patch.object(telemetry_send, "_spawn", self.started.append)
        spawn.start()
        self.addCleanup(spawn.stop)

    def environ(self, **extra: str) -> dict:
        return super().environ(**{**QUIET, **extra})

    def told(self) -> bool:
        with mock.patch.dict(os.environ, self.environ(), clear=True):
            return analytics.told_at(self.settings) is not None

    def counted(self) -> list[tuple]:
        """The runs kept for a sender, each ``(by, outcome, found)``, taken."""
        found = [(row["by"], row["outcome"], row["found"]) for row in kept(self.settings)]
        self.settings.with_name(analytics.INSTALLS).unlink(missing_ok=True)
        return found

    def cad(self, *argv: str, **extra: str):
        """``cad <argv>`` by the ``cad`` command itself, which says the notice for the commands it tells."""
        import types

        from cad_server import cli

        self.forget_calls()
        with self.on_this_computer(**extra) as (out, err):
            code = cli.main(list(argv))
        return types.SimpleNamespace(returncode=code, stdout=out.getvalue(), stderr=err.getvalue())

    def test_a_person_s_run_is_told_once_before_its_work_and_counted(self) -> None:
        for argv in (["plugin", "install"], ["plugin", "update"]):
            done = self.cad(*argv)
            self.assertEqual(0, done.returncode, done.stdout + done.stderr)
            self.assertIn("Claude Code: ", done.stdout)
            if argv[1] == "install":  # the first run on this computer: the notice, one line, on stderr alone
                self.assertEqual(done.stderr.count("cad now sends usage stats and crash reports"), 1)
                self.assertEqual(len(done.stderr.splitlines()), 1)
                self.assertNotIn("usage stats", done.stdout)
                self.assertTrue(self.told())
            else:  # said once: never again
                self.assertEqual(done.stderr, "")
            self.assertEqual(self.counted(), [("person", "ok", 1)], argv)
        self.assertEqual(self.started, [self.settings] * 2, "a sender at once for each run")

    def test_a_run_the_hosted_install_command_handed_over_is_told_and_counted(self) -> None:
        done = self.cad("plugin", "install", CAD_PLUGIN_BY="script", FAKE_FAIL="claude")
        self.assertEqual(1, done.returncode, done.stdout)
        self.assertEqual(done.stderr.count("cad now sends usage stats and crash reports"), 1)
        self.assertTrue(self.told())
        self.assertEqual(self.counted(), [("script", "failed", 1)])

    def test_a_run_a_server_began_is_told_nothing_and_counted_only_once_a_person_was_told(self) -> None:
        # Its output is a log's: nothing is said there, so nothing is kept as said, and nothing counted.
        done = self.cad("plugin", "update", CAD_INSTALL_ATTEMPT="7.0")
        self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
        self.assertIn("Claude Code: installed", done.stdout)
        self.assertFalse(self.told())
        self.assertEqual((self.counted(), self.started), ([], []))
        # The hosted install command of an earlier cad's server run hands over to ``cad plugin install`` with that
        # run's name: a server's all the same.
        done = self.cad("plugin", "install", CAD_INSTALL_ATTEMPT="7.0", CAD_PLUGIN_BY="script")
        self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
        self.assertFalse(self.told())
        self.assertEqual(self.counted(), [])
        # Told by a command a person ran, its runs are counted from then on, and still say nothing.
        with self.on_this_computer():
            self.assertTrue(analytics.notify(io.StringIO()))
        done = self.cad("plugin", "update", CAD_INSTALL_ATTEMPT="7.0")
        self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
        self.assertEqual(self.counted(), [("server", "ok", 1)])
        # Another run going: it ran nothing, and says so in its count.
        with self.another_run():
            done = self.cad("plugin", "update", CAD_INSTALL_ATTEMPT="7.0")
        self.assertEqual(75, done.returncode)
        self.assertEqual(self.counted(), [("server", "busy", 0)])
        # Its time up before it was done: stopped, and counted as that.
        with mock.patch.object(auto_update_helper, "INSTALL_SECONDS", 0):
            done = self.cad("plugin", "update", CAD_INSTALL_ATTEMPT="7.0")
        self.assertEqual(computer.STOPPED, done.returncode, done.stdout)
        self.assertEqual(self.counted(), [("server", "stopped", 0)])

    def test_a_run_reached_from_an_install_command_cad_started_is_told_nothing(self) -> None:
        """The bridge's runs of the hosted install command have their output nowhere or in a log, and carry cad's
        mark: its hand-over to this command tells nobody, though no server's run is named."""
        done = self.cad("plugin", "install", CAD_PLUGIN_BY="script", CAD_INSTALL_BY_CAD="1")
        self.assertEqual((0, ""), (done.returncode, done.stderr), done.stdout)
        self.assertFalse(self.told())
        self.assertEqual((self.counted(), self.started), ([], []))

    def test_the_switch_and_the_help_tell_nothing_and_count_nothing(self) -> None:
        for argv in (["plugin", "update", "auto"], ["plugin", "update", "auto", "on"],
                     ["plugin", "update", "auto", "off"], ["plugin"], ["plugin", "--refresh"]):
            done = self.cad(*argv)
            self.assertEqual((0, ""), (done.returncode, done.stderr), argv)
        for argv in (["plugin", "install", "--help"], ["plugin", "update", "--help"]):
            with self.assertRaises(SystemExit):
                self.cad(*argv)
        self.assertFalse(self.told())
        self.assertEqual((self.counted(), self.started, self.calls()), ([], [], []))

    def test_nothing_is_said_or_kept_where_telemetry_is_refused(self) -> None:
        for refusal in ({"DO_NOT_TRACK": "1"}, {"CAD_TELEMETRY": "0"}, {"CI": "true"},
                        {"CAD_INSTALLATION_VERSION": f"{RELEASE}-dev.20261119120000"}, {analytics.NOTICE_ENV: "0"}):
            done = self.cad("plugin", "install", **refusal)
            self.assertEqual((0, ""), (done.returncode, done.stderr), refusal)
            self.assertFalse(self.told(), refusal)
            self.assertEqual((self.counted(), self.started), ([], []), refusal)
        # The person's no, said before the run: nothing said, nothing kept.
        with self.on_this_computer():
            analytics.choose(False, by="cli")
        done = self.cad("plugin", "install")
        self.assertEqual((0, ""), (done.returncode, done.stderr))
        self.assertEqual((self.counted(), self.started), ([], []))
        self.assertEqual(sorted(path.name for path in self.state.iterdir() if path.name.startswith("telemetry")), [])

    def test_a_run_that_began_before_the_person_was_told_is_not_counted(self) -> None:
        """A server's run, nobody told yet; a command a person runs meanwhile tells them. What the run noted began
        before that, and is never sent."""
        real = run.install

        def told_meanwhile(*args, **kwargs):
            found = real(*args, **kwargs)
            self.assertTrue(analytics.notify(io.StringIO()))
            return found

        with mock.patch.object(run, "install", told_meanwhile):
            done = self.cad("plugin", "update", CAD_INSTALL_ATTEMPT="7.0")
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertTrue(self.told())
        self.assertEqual((self.counted(), self.started), ([], []))

    def test_a_crash_of_the_run_is_reported_as_every_command_s_is(self) -> None:
        """Nothing of the run's own counts a crash: the ``cad`` command reports any command's (``where``: ``command``,
        the process not going on), kept in the spool for a sender, and the traceback is the person's."""
        with mock.patch.object(run, "install_apps", side_effect=KeyError("a mistake of ours")), \
                self.assertRaises(KeyError):
            self.cad("plugin", "install")
        self.assertTrue(self.told(), "told before its work, so a crash of the first run is one a person was told of")
        self.assertEqual(self.counted(), [], "a run that did not end says nothing it was")
        with mock.patch.dict(os.environ, self.environ(), clear=True):
            [batch] = sent(self.settings)
        [crash] = batch["events"]
        self.assertEqual((crash["name"], crash["where"], crash["type"], crash["handled"], crash["count"]),
                         ("exception", "command", "KeyError", False, 1))
        files = [frame["file"] for frame in crash["frames"]]
        self.assertIn("cad_server/cli/plugin.py", files)
        self.assertIn("cad_server/plugin/run.py", files)
        self.assertNotIn("a mistake of ours", json.dumps(batch))
        # ``cad plugin update`` the same, its run kept as failed first (``plugin_catch_up.ended``).
        with mock.patch.object(run, "install_apps", side_effect=KeyError("a mistake of ours")), \
                self.assertRaises(KeyError):
            self.cad("plugin", "update")
        with mock.patch.dict(os.environ, self.environ(), clear=True):
            [batch] = sent(self.settings)
        self.assertEqual([(event["name"], event["where"]) for event in batch["events"]], [("exception", "command")])


if __name__ == "__main__":
    unittest.main()
