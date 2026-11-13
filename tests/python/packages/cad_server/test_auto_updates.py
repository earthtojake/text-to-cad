"""Automatic updates (``cad_server/auto_updates.py``, ``cad_server._internal.update.Update.automatic``): the
person's setting, the retry rule, the hour of quiet, and the server's own update through the update's stand-ins --
the release's install stood in for, its ``cad setup`` a script of the test's, the server a stand-in with its work
and its drain. The whole update with the real uv is test_update_end_to_end.py's."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad_server import auto_updates  # noqa: E402
from cad_server._internal import update  # noqa: E402
# A release's process: a checkout is a development build, never told of a release and sending nothing by default,
# unless it is told the version it runs as (``cad_server/_internal/channel.py``).
RELEASE = __import__("cad_server").__version__

DAY = auto_updates.RETRY_SECONDS


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="cad-auto-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        engine = tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
        self.addCleanup(shutil.rmtree, engine, True)
        patched = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.root / "state"),
                                               "CAD_CACHE_DIR": str(self.root / "cache"), "CAD_ENGINE_DIR": engine,
                                               "CI": "", "CAD_UPDATE_CHECK": "", "CAD_INSTALLATION_VERSION": RELEASE})
        patched.start()
        self.addCleanup(patched.stop)
        (self.root / "state").mkdir()
        # The install command ran here: the default channel has an updater.
        (self.root / "state" / "install-receipt.json").write_text('{"schema": 1}', encoding="utf-8")


class SettingTest(Fixture):
    def test_on_by_default_the_person_s_answer_kept_and_an_environment_s_off_fixed(self) -> None:
        self.assertEqual(auto_updates.read(), {"automatic": auto_updates.DEFAULT, "reason": "default"})
        self.assertTrue(auto_updates.DEFAULT, "on by default: the maintainer's open question, flipped in one place")
        self.assertEqual(auto_updates.change({"automatic": False}), {"automatic": False, "reason": "choice"})
        self.assertFalse(auto_updates.enabled())
        settings = json.loads((self.root / "state" / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings, {"updates": {"automatic": False}}, "one section of the settings every app reads")
        self.assertEqual(auto_updates.change({"automatic": True}), {"automatic": True, "reason": "choice"})
        for values in ({"CAD_UPDATE_CHECK": "0"}, {"CI": "true"}):
            with self.subTest(values=values), mock.patch.dict(os.environ, values):
                self.assertEqual(auto_updates.read(), {"automatic": False, "reason": "environment"})
        for wrong in (None, {}, {"automatic": "yes"}, {"automatic": True, "more": 1}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                auto_updates.change(wrong)

    def test_cad_update_auto_says_and_changes_it(self) -> None:
        from cad_server import cli

        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()), \
                mock.patch("cad.engine.client.request", return_value=None):
            self.assertEqual(cli.main(["update", "auto", "off"]), 0)
            self.assertEqual(cli.main(["update", "auto"]), 0)
        self.assertEqual(out.getvalue().splitlines(), ["Automatic updates are off (your choice)."] * 2)
        self.assertFalse(auto_updates.enabled())
        # What the engine is getting ready, from its status.
        auto_updates.change({"automatic": True})
        line = auto_updates.describe({"automatic": {"state": "waiting", "release": "1.2.0"}})
        self.assertTrue(line.startswith("on (your choice); feed not read yet"), line)
        self.assertTrue(line.endswith("; text-to-cad 1.2.0 installed, switching once idle"), line)


class RetryTest(Fixture):
    def test_the_same_release_is_tried_again_by_itself_only_a_day_later_and_a_newer_one_at_once(self) -> None:
        now = 1_000_000.0
        self.assertTrue(auto_updates.due("1.2.0", None, now))
        auto_updates.attempt("1.2.0", now=now)
        auto_updates.attempt("1.2.0", error="dns error", now=now + 300)
        kept = auto_updates.attempted()
        self.assertEqual(kept, {"release": "1.2.0", "at": now, "error": "dns error"}, "a failure is no new attempt")
        self.assertFalse(auto_updates.due("1.2.0", kept, now + DAY - 1))
        self.assertTrue(auto_updates.due("1.2.0", kept, now + DAY))
        self.assertTrue(auto_updates.due("1.3.0", kept, now + 1), "a newer release the feed names: at once")
        self.assertTrue(auto_updates.due("1.2.0", kept, now - 10), "a clock set back counts as long ago")

    def test_idle_means_no_command_for_an_hour(self) -> None:
        self.assertEqual(auto_updates.IDLE_SECONDS, 3600, "the one number: an hour with no command")
        self.assertFalse(auto_updates.quiet(100.0, 100.0 + auto_updates.IDLE_SECONDS - 0.1))
        self.assertTrue(auto_updates.quiet(100.0, 100.0 + auto_updates.IDLE_SECONDS))


class SemanticVersioningTest(Fixture):
    def test_below_1_0_a_patch_release_installs_itself_and_a_minor_or_major_one_waits(self) -> None:
        self.assertTrue(auto_updates.takes("0.11.0", "0.11.1"))
        self.assertTrue(auto_updates.takes("0.11.0", "0.11.12"))
        for latest in ("0.12.0", "1.0.0", "1.1.0"):
            self.assertFalse(auto_updates.takes("0.11.3", latest), latest)

    def test_from_1_0_a_patch_or_minor_release_installs_itself_and_a_major_one_waits(self) -> None:
        for latest in ("1.4.3", "1.5.0", "1.12.0"):
            self.assertTrue(auto_updates.takes("1.4.2", latest), latest)
        for version, latest in (("1.9.3", "2.0.0"), ("1.4.2", "3.1.0")):
            self.assertFalse(auto_updates.takes(version, latest), (version, latest))

    def test_only_a_later_plain_release_is_taken(self) -> None:
        for version, latest in (("0.11.1", "0.11.1"), ("0.11.2", "0.11.1"), ("1.5.0", "1.4.9"),
                                ("0.11.0", "0.11.1rc1"), ("0.11.0.dev0", "0.11.1"), ("1.04.2", "1.4.3"),
                                (None, "0.11.1")):
            self.assertFalse(auto_updates.takes(version, latest), (version, latest))

    def test_cad_update_auto_says_a_release_that_waits_is_out(self) -> None:
        for version, latest, kind in (("0.11.0", "0.12.0", "minor"), ("0.11.3", "1.0.0", "major"),
                                      ("1.1.0", "2.0.0", "major")):
            with mock.patch("cad_server.updates.notice", return_value={"latest": latest, "version": version}):
                self.assertIn(f"; text-to-cad {latest} is out, a new {kind} release, which waits for you: update "
                              "with the button or `cad update`", auto_updates.describe())
        for version, latest in (("0.11.0", "0.11.1"), ("1.1.0", "1.2.0")):
            with mock.patch("cad_server.updates.notice", return_value={"latest": latest, "version": version}):
                self.assertNotIn("is out", auto_updates.describe(), "one it takes is said once it installs")


class Engine:
    """The daemon as an automatic update sees it: its work in flight, when its work last ended, its drain,
    its stop and its server's port."""

    def __init__(self) -> None:
        self.busy = True
        self.asked = 0
        self.worked = time.monotonic()
        self.draining = False
        self.stopping = threading.Event()
        self.server = SimpleNamespace(port=4567)
        self.drained: list = []

    def working(self) -> bool:
        self.asked += 1
        return self.busy

    def drain(self, then=None) -> None:
        self.drained.append(then)


class AutomaticTest(Fixture):
    def setUp(self) -> None:
        super().setUp()
        self.log = self.root / "setup.log"
        self.command = self.setup_script(0)
        self.notice = {"latest": "1.1.1", "version": "1.1.0"}
        self.installs: list[str] = []
        self.refused: Exception | None = None

        def install(version: str) -> dict:
            self.installs.append(version)
            if self.refused is not None:
                raise self.refused
            return {"cad": self.command}

        for patch in (mock.patch.object(auto_updates, "IDLE_SECONDS", 0.3),
                      mock.patch.object(update, "IDLE_POLL_SECONDS", 0.02),
                      mock.patch("cad_server.updates.notice", side_effect=lambda: self.notice),
                      mock.patch("cad_server.updates.refresh", return_value=None),
                      mock.patch.object(update, "install", side_effect=install)):
            patch.start()
            self.addCleanup(patch.stop)
        self.job, self.engine = update.Update(), Engine()
        self.addCleanup(self.stop)

    def stop(self) -> None:
        """The server stopped: an automatic update still waiting gives up, before the next test's settings."""
        self.engine.stopping.set()
        thread = self.job.thread
        if thread is not None:
            thread.join(30)

    def setup_script(self, code: int) -> str:
        """A release's ``cad setup --engine-update``: each run kept in the log, a restart frame on stdout, and
        ``code``."""
        frame = {"progress": {"kind": "update", "stage": "restart", "job": "1.1.1", "outputs": [], "detail": "",
                              "done": 3, "total": 4, "elapsedMs": 0}}
        script = self.root / f"setup-{code}.py"
        script.write_text(
            "import json, sys\n"
            f"open({str(self.log)!r}, 'a', encoding='utf-8').write(json.dumps(sys.argv[1:]) + '\\n')\n"
            f"print({json.dumps(frame)!r}, flush=True)\n"
            f"if {code}: print('the apps could not be reached', file=sys.stderr)\n"
            f"sys.exit({code})\n", encoding="utf-8")
        if os.name == "nt":
            command = self.root / f"cad-{code}.cmd"
            command.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
        else:
            command = self.root / f"cad-{code}"
            command.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
            command.chmod(0o755)
        return str(command)

    def runs(self) -> list:
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()] if self.log.exists() else []

    def until(self, condition, what: str) -> None:
        deadline = time.monotonic() + 30
        while not condition():
            self.assertLess(time.monotonic(), deadline, what)
            time.sleep(0.01)

    def waiting(self) -> bool:
        return (self.job.status()["automatic"] or {}).get("state") == "waiting"

    def test_it_installs_at_once_and_runs_the_release_s_setup_only_once_nothing_has_run_for_a_while(self) -> None:
        self.assertEqual(self.job.automatic(self.engine), "1.1.1")
        self.until(self.waiting, "the release installed")
        self.assertEqual((self.installs, self.runs()), (["1.1.1"], []), "installed alone: no app changed, no move")
        self.assertEqual(self.job.snapshot()["state"], "idle", "no page shows an update until its setup runs")
        self.assertEqual(auto_updates.attempted()["release"], "1.1.1")
        self.assertIsNone(self.job.automatic(self.engine), "one at a time")
        # Busy well past the idle window: it waits. ``Daemon.working`` is the command in flight, asked each poll.
        asked = self.engine.asked
        self.until(lambda: self.engine.asked > asked + 3 * auto_updates.IDLE_SECONDS / update.IDLE_POLL_SECONDS,
                   "the server asked while it works")
        self.assertEqual((self.runs(), self.waiting()), ([], True))
        # The work ends (``Daemon.worked``, the last command's end): once nothing has run for the window, its setup.
        self.engine.busy, self.engine.worked = False, time.monotonic()
        self.until(lambda: self.job.snapshot()["state"] == "restarting", "the release's setup")
        self.assertEqual(self.runs(), [["setup", "--engine-update"]], "its whole setup, the one argument")
        self.assertEqual(self.job.snapshot()["target"], "1.1.1")
        self.assertIsNone(self.job.status()["automatic"])
        self.assertIsNone(self.job.automatic(self.engine), "an update underway")

    def test_a_click_while_it_gets_ready_makes_it_the_click_s_at_once(self) -> None:
        self.job.automatic(self.engine)
        self.until(self.waiting, "ready")
        with mock.patch("cad_server.updates.newest", side_effect=AssertionError("the click joins it: no feed read")):
            started = self.job.start(SimpleNamespace(port=4567))
        self.assertEqual((started["state"], started["target"]), ("working", "1.1.1"))
        self.until(lambda: self.job.snapshot()["state"] == "restarting", "its setup, though the server is busy")
        self.assertEqual(self.runs(), [["setup", "--engine-update"]])

    def test_a_failure_says_nothing_and_that_release_is_not_tried_again_for_a_day(self) -> None:
        from cad_server._internal import base

        self.refused = base.Refused("the CAD kernel environment needs the network once")
        self.job.automatic(self.engine)
        self.until(lambda: self.job.status()["automatic"] is None, "the attempt over")
        self.assertEqual(self.job.snapshot()["state"], "idle", "no page was following it: nothing is said")
        self.assertEqual(auto_updates.attempted()["error"], "the CAD kernel environment needs the network once")
        self.assertIsNone(self.job.automatic(self.engine), "not again in a loop")
        self.assertEqual(self.installs, ["1.1.1"])
        self.notice, self.refused = {"latest": "1.1.2", "version": "1.1.0"}, None
        self.assertEqual(self.job.automatic(self.engine), "1.1.2", "a newer release the feed names: at once")
        self.until(self.waiting, "ready")
        self.assertIn("text-to-cad 1.1.2 installed, switching once idle", auto_updates.describe(self.job.status()))

    def test_a_setup_that_fails_is_kept_as_the_attempt_s_failure(self) -> None:
        self.command = self.setup_script(1)
        self.engine.busy = False
        self.job.automatic(self.engine)
        self.until(lambda: (auto_updates.attempted() or {}).get("error"), "its setup failed, kept as the attempt's")
        self.assertEqual(auto_updates.attempted()["error"], "the apps could not be reached")
        self.assertEqual(self.job.snapshot()["state"], "failed")
        self.assertIsNone(self.job.automatic(self.engine), "not again for a day")

    def test_nothing_starts_when_it_is_off_nothing_is_newer_or_another_update_is_underway(self) -> None:
        from cad_server._internal import versions

        auto_updates.change({"automatic": False})
        self.assertIsNone(self.job.automatic(self.engine))
        auto_updates.change({"automatic": True})
        with mock.patch.dict(os.environ, {"CAD_UPDATE_CHECK": "0"}):
            self.assertIsNone(self.job.automatic(self.engine))
        notice, self.notice = self.notice, None
        self.assertIsNone(self.job.automatic(self.engine), "nothing newer: offline, or the feed unread")
        self.notice = notice
        self.engine.draining = True
        self.assertIsNone(self.job.automatic(self.engine), "a drain: the server retiring")
        self.engine.draining = False
        with versions.install_lock():
            self.assertTrue(auto_updates.installing())
            self.assertIsNone(self.job.automatic(self.engine), "the install command or `cad update` running")
        self.assertFalse(auto_updates.installing())
        receipt = self.root / "state" / "install-receipt.json"
        receipt.unlink()
        self.assertIsNone(self.job.automatic(self.engine), "no install command ran here: no updater")
        self.assertEqual((self.installs, self.runs()), ([], []))
        self.assertIsNone(auto_updates.attempted(), "nothing was tried")

    def test_a_release_that_bumps_the_breaking_part_is_never_started_by_itself(self) -> None:
        for version, latest in (("1.1.0", "2.0.0"), ("0.11.0", "0.12.0"), ("0.11.0", "1.0.0")):
            self.notice = {"latest": latest, "version": version}
            self.assertIsNone(self.job.automatic(self.engine), latest)
        self.assertEqual(self.installs, [])
        self.assertIsNone(auto_updates.attempted(), "nothing was tried")
        self.assertEqual(self.job.status()["automatic"], None)

    def test_from_1_0_a_minor_release_is_started_by_itself(self) -> None:
        self.notice = {"latest": "1.2.0", "version": "1.1.0"}
        self.assertEqual(self.job.automatic(self.engine), "1.2.0")
        self.until(self.waiting, "the release installed")
        self.assertEqual(auto_updates.attempted()["release"], "1.2.0")

    def test_turned_off_while_it_waits_it_is_given_up_and_goes_on_when_turned_on(self) -> None:
        self.job.automatic(self.engine)
        self.until(self.waiting, "ready")
        auto_updates.change({"automatic": False})
        self.until(lambda: self.job.status()["automatic"] is None, "given up")
        self.assertEqual((self.runs(), auto_updates.attempted()), ([], None))
        auto_updates.change({"automatic": True})
        self.assertEqual(self.job.automatic(self.engine), "1.1.1")


class DaemonTest(unittest.TestCase):
    def test_the_engine_asks_as_it_tends_itself_and_says_where_its_update_is(self) -> None:
        from cad_server.engine import daemon

        engine = daemon.Daemon(cap=1)
        self.addCleanup(engine.supervisor.stop)
        with mock.patch("cad_server._internal.engine_host.automatic") as asked:
            engine.tend()
        asked.assert_called_once_with(engine)
        worked = engine.worked
        answers: list[dict] = []
        engine.handle({"op": "status"}, answers.append)
        self.assertEqual(answers[0]["update"], {"state": "idle", "target": None, "automatic": None})
        self.assertEqual(engine.worked, worked, "a status is no work: it never holds an update back")


def setUpModule() -> None:
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
