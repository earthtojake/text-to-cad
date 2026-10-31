"""Automatic updates (``cad_server/auto_updates.py``, ``cad_server._internal.update.Update.automatic``): the
person's setting, the retry rule, and the engine's own update through the update's stand-ins -- a
release's ``cad setup`` a script of the test's, the engine a stand-in with its work, its drain and its
port, the switch's helper not started. The whole update with the real uv is test_update_end_to_end.py's."""

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
from cad_server._internal import installations, releases, switch, update  # noqa: E402

DAY = auto_updates.RETRY_SECONDS


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="cadgen-auto-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        engine = tempfile.mkdtemp(prefix="eng-", dir="/tmp" if os.name != "nt" else None)
        self.addCleanup(shutil.rmtree, engine, True)
        patched = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.root / "state"),
                                               "CAD_CACHE_DIR": str(self.root / "cache"), "CAD_ENGINE_DIR": engine,
                                               "CI": "", "CAD_UPDATE_CHECK": "", "CAD_INSTALL_CHANNEL": "claude-github"})
        patched.start()
        self.addCleanup(patched.stop)
        (self.root / "state").mkdir()

    def release(self, version: str) -> None:
        """A release's folder, made as ``releases.make`` makes one, and registered."""
        folder = releases.where(version)
        python, console = releases.base.interpreter(folder), releases.console(folder)
        python.parent.mkdir(parents=True)
        for path in (python, console):
            path.write_text("", encoding="utf-8")
        (folder / releases.MARKER).write_text(json.dumps({"schema": releases.SCHEMA, "version": version}), encoding="utf-8")
        installations.register(version, (str(console), str(python), str(folder)))


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

    def test_idle_means_nothing_has_run_for_a_minute(self) -> None:
        self.assertFalse(auto_updates.quiet(100.0, 100.0 + auto_updates.IDLE_SECONDS - 0.1))
        self.assertTrue(auto_updates.quiet(100.0, 100.0 + auto_updates.IDLE_SECONDS))


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
        self.release("1.1.0")
        installations.point("1.1.0")
        self.log = self.root / "setup.log"
        self.command = self.setup_script(0)
        self.notice = {"latest": "1.2.0", "version": "1.1.0"}
        for patch in (mock.patch.object(auto_updates, "IDLE_SECONDS", 0.3),
                      mock.patch.object(update, "IDLE_POLL_SECONDS", 0.02),
                      mock.patch("cad_server.updates.notice", side_effect=lambda: self.notice),
                      mock.patch("cad_server.updates.refresh", return_value=None),
                      mock.patch.object(releases, "make", side_effect=lambda version, told=None: {"cadgen": self.command})):
            patch.start()
            self.addCleanup(patch.stop)
        self.spawned = mock.patch.object(switch, "spawn").start()
        self.addCleanup(mock.patch.stopall)
        self.job, self.engine = update.Update(), Engine()
        self.addCleanup(self.stop)

    def stop(self) -> None:
        """The engine stopped: an automatic update still waiting gives up, before the next test's settings."""
        self.engine.stopping.set()
        thread = self.job.thread
        if thread is not None:
            thread.join(30)

    def setup_script(self, code: int) -> str:
        """A release's ``cad setup --engine-update``: each run's ``PREPARE_ENV`` kept in the log, an apps
        frame on stdout for a whole run, and ``code``."""
        frame = {"progress": {"kind": "update", "stage": "apps", "job": "1.2.0", "outputs": [], "detail": "",
                              "done": 2, "total": 4, "elapsedMs": 0}}
        script = self.root / f"setup-{code}.py"
        script.write_text(
            "import json, os, sys\n"
            f"prepare = os.environ.get({update.PREPARE_ENV!r}, '')\n"
            f"open({str(self.log)!r}, 'a', encoding='utf-8').write(json.dumps([sys.argv[1:], prepare]) + '\\n')\n"
            f"if not prepare: print({json.dumps(frame)!r}, flush=True)\n"
            f"if {code}: print('the CAD kernel environment needs the network once', file=sys.stderr)\n"
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

    def test_it_gets_ready_at_once_and_switches_only_once_nothing_has_run_for_a_while(self) -> None:
        self.assertEqual(self.job.automatic(self.engine), "1.2.0")
        self.until(self.waiting, "the release installed and its base made")
        self.assertEqual(self.runs(), [[["setup", "--engine-update"], "1"]], "its first half alone: no app changed")
        self.assertEqual(self.job.snapshot()["state"], "idle", "no page shows an update until it switches")
        self.assertEqual(auto_updates.attempted()["release"], "1.2.0")
        self.assertIsNone(self.job.automatic(self.engine), "one at a time")
        # Busy well past the idle window: it waits.
        asked = self.engine.asked
        self.until(lambda: self.engine.asked > asked + 3 * auto_updates.IDLE_SECONDS / update.IDLE_POLL_SECONDS,
                   "the engine asked while it works")
        self.assertEqual((self.engine.drained, self.waiting()), ([], True))
        # The work ends: once nothing has run for the window, the apps and the switch, as a click's.
        self.engine.busy, self.engine.worked = False, time.monotonic()
        self.until(lambda: self.job.snapshot()["state"] == "restarting", "the switch")
        self.assertEqual(self.runs()[1], [["setup", "--engine-update"], ""], "its whole setup: the apps' plugins")
        self.assertEqual(self.job.snapshot()["target"], "1.2.0")
        self.assertIsNone(self.job.status()["automatic"])
        (then,) = self.engine.drained
        then()  # drained: its helper starts
        self.spawned.assert_called_once_with("1.2.0", port=4567, previous="1.1.0")
        self.assertIsNone(self.job.automatic(self.engine), "a switch underway")

    def test_a_click_while_it_gets_ready_makes_it_the_click_s_at_once(self) -> None:
        self.job.automatic(self.engine)
        self.until(self.waiting, "ready")
        with mock.patch("cad_server.updates.newest", side_effect=AssertionError("the click joins it: no feed read")):
            started = self.job.start(SimpleNamespace(port=4567, retire=self.engine.drain))
        self.assertEqual((started["state"], started["target"]), ("working", "1.2.0"))
        self.until(lambda: self.job.snapshot()["state"] == "restarting", "the switch, though the engine is busy")
        self.assertEqual(len(self.engine.drained), 1, "the drain still waits for what is in flight")

    def test_a_failure_says_nothing_and_that_release_is_not_tried_again_for_a_day(self) -> None:
        self.command = self.setup_script(1)
        self.job.automatic(self.engine)
        self.until(lambda: self.job.status()["automatic"] is None, "the attempt over")
        self.assertEqual(self.job.snapshot()["state"], "idle", "no page was following it: nothing is said")
        self.assertEqual(auto_updates.attempted()["error"], "the CAD kernel environment needs the network once")
        self.assertIsNone(self.job.automatic(self.engine), "not again in a loop")
        self.assertEqual(len(self.runs()), 1)
        self.notice = {"latest": "1.3.0", "version": "1.1.0"}
        self.command = self.setup_script(0)
        self.assertEqual(self.job.automatic(self.engine), "1.3.0", "a newer release the feed names: at once")
        self.until(self.waiting, "ready")
        self.assertIn("text-to-cad 1.3.0 installed, switching once idle", auto_updates.describe(self.job.status()))

    def test_a_switch_that_failed_is_kept_as_the_automatic_attempt_s_and_nothing_starts_for_a_while(self) -> None:
        auto_updates.attempt("1.2.0")
        switch._record({"from": "1.1.0", "to": "1.2.0", "port": 4567, "ok": False, "error": "it exited with code 3"})
        self.job.recall()
        self.assertEqual(auto_updates.attempted()["error"], "it exited with code 3")
        self.notice = {"latest": "1.3.0", "version": "1.1.0"}
        self.assertIsNone(self.job.automatic(self.engine), "a failure recalled: nothing for ten minutes")
        self.job.failed_at -= update.RECALL_SECONDS
        self.assertEqual(self.job.automatic(self.engine), "1.3.0")

    def test_nothing_starts_when_it_is_off_nothing_is_newer_or_another_update_is_underway(self) -> None:
        from cad_server._internal.file_lock import exclusive
        from cad_server.cli.setup import LOCK

        auto_updates.change({"automatic": False})
        self.assertIsNone(self.job.automatic(self.engine))
        auto_updates.change({"automatic": True})
        with mock.patch.dict(os.environ, {"CAD_UPDATE_CHECK": "0"}):
            self.assertIsNone(self.job.automatic(self.engine))
        notice, self.notice = self.notice, None
        self.assertIsNone(self.job.automatic(self.engine), "nothing newer: offline, or the feed unread")
        self.notice = notice
        self.engine.draining = True
        self.assertIsNone(self.job.automatic(self.engine), "a drain: another update's switch")
        self.engine.draining = False
        with exclusive(self.root / "state" / LOCK):
            self.assertTrue(auto_updates.installing())
            self.assertIsNone(self.job.automatic(self.engine), "the install command or `cad update` running")
        self.assertFalse(auto_updates.installing())
        self.assertEqual(self.runs(), [])
        self.assertIsNone(auto_updates.attempted(), "nothing was tried")

    def test_turned_off_while_it_waits_it_is_given_up_and_goes_on_when_turned_on(self) -> None:
        self.job.automatic(self.engine)
        self.until(self.waiting, "ready")
        auto_updates.change({"automatic": False})
        self.until(lambda: self.job.status()["automatic"] is None, "given up")
        self.assertEqual((self.engine.drained, auto_updates.attempted()), ([], None))
        auto_updates.change({"automatic": True})
        self.assertEqual(self.job.automatic(self.engine), "1.2.0")


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
