"""A superseded engine steps aside (``Daemon.supersede``, each ``tend``): once the device runs a newer
release (``daemon.SUPERSEDED``) and nothing holds it, nothing runs and nothing has been asked of it for
``QUIET_SECONDS``, it stops; with pages watching it first starts its successor (``daemon.SUCCESSOR``)
and lets its pages go, so the successor's start retires it (the idle ``stop``). And a client's start
brings up the current release's engine rather than its own (``client.CURRENT``)."""

from __future__ import annotations

import os
import sys
import time
import types
import unittest
from unittest import mock

from tests.python.support import engine_daemon


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup, start=False)


class SupersessionTest(unittest.TestCase):
    def engine(self, *, watched: bool = False, holders: int = 0, busy: int = 0, quiet: bool = True):
        """An engine last asked anything a minute ago, ``watched`` by a page or not."""
        from cadgen.engine import daemon

        engine = daemon.Daemon(cap=1)
        self.addCleanup(engine.pool.stop)
        engine.server = types.SimpleNamespace(watched=lambda: ["a-document"] if watched else [],
                                              clients_active=lambda: watched, clients_quiet=lambda _seconds: quiet)
        engine.holders, engine.busy = holders, busy
        engine.asked = time.monotonic() - 60
        return engine

    def hooks(self, superseded: bool = True, answer: str | None = None) -> list[int]:
        from cadgen.engine import daemon

        started: list[int] = []
        for name, value in (("SUPERSEDED", lambda: superseded), ("SUCCESSOR", lambda port: started.append(port) or answer)):
            patch = mock.patch.object(daemon, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        return started

    def test_unwatched_and_idle_it_stops(self) -> None:
        started = self.hooks()
        engine = self.engine()
        engine.tend()
        self.assertTrue(engine.stopping.is_set())
        self.assertEqual(started, [], "no page to carry over: the next client's start brings the current release")

    def test_watched_it_starts_its_successor_and_its_pages_no_longer_keep_it(self) -> None:
        started = self.hooks()
        engine = self.engine(watched=True)
        sent: list[dict] = []
        engine.handle({"op": "stop", "idle": True}, sent.append)
        self.assertEqual(sent[-1]["failed"], "the engine is in use")
        self.assertEqual(engine.supersede(), "handing over")
        self.assertEqual(started, [engine.port])
        self.assertFalse(engine.stopping.is_set())
        self.assertEqual(engine.supersede(), None, "one successor while one is starting")
        self.assertEqual(engine.uses(), {"holders": 0, "watched": 0, "busy": 0, "active": False})
        engine.handle({"op": "stop", "idle": True}, sent.append)  # the successor's retirement of it
        self.assertEqual(sent[-1], {"ok": True})
        self.assertTrue(engine.stopping.is_set())

    def test_a_successor_that_does_not_start_leaves_it_serving_and_is_tried_again(self) -> None:
        started = self.hooks(answer="no installation of 0.9.0 is registered: run the install command")
        engine = self.engine(watched=True)
        with mock.patch("sys.stderr"):
            self.assertEqual(engine.supersede(), "no installation of 0.9.0 is registered: run the install command")
            self.assertFalse(engine.handing())
            self.assertEqual(engine.uses()["watched"], 1)
            engine.supersede()
        self.assertEqual(started, [engine.port, engine.port])
        self.assertFalse(engine.stopping.is_set())

    def test_it_stays_while_held_running_asked_or_not_superseded(self) -> None:
        cases = {"an app server's hold": {"holders": 1}, "a build": {"busy": 1}, "an HTTP request": {"quiet": False}}
        started = self.hooks()
        for why, given in cases.items():
            with self.subTest(why):
                engine = self.engine(watched=True, **given)
                self.assertIsNone(engine.supersede())
                self.assertFalse(engine.stopping.is_set())
        engine = self.engine()
        engine.handle({"op": "pid"}, lambda _answer: None)  # a pid or status read is no work asked of it
        self.assertEqual(engine.supersede(), "stopping")
        engine = self.engine()
        engine.handle({"op": "anything"}, lambda _answer: None)  # any other request is work asked of it
        self.assertIsNone(engine.supersede(), "within the quiet window")
        self.hooks(superseded=False)
        engine = self.engine()
        self.assertIsNone(engine.supersede())
        self.assertFalse(engine.stopping.is_set())
        self.assertEqual(started, [])


class StartTest(unittest.TestCase):
    def start(self, current: str | None) -> tuple[list[str], dict[str, str]]:
        from cadgen.engine import client, daemon

        popen = mock.Mock(return_value=mock.Mock(wait=lambda: 0))
        with mock.patch.object(client, "CURRENT", lambda: current), \
                mock.patch.object(client.subprocess, "Popen", popen), \
                mock.patch.dict(os.environ, {"PYTHONPATH": os.pathsep.join([daemon.engine_root(), "/elsewhere"]),
                                             daemon.INSTALLATION_ENV: "0.8.3-dev.1"}):
            client._start()
        (argv,), options = popen.call_args
        return argv, options["env"]

    def test_a_start_brings_up_the_current_release_s_server(self) -> None:
        from cadgen.engine import client, daemon

        argv, env = self.start("/releases/0.9.0/bin/cadgen")
        self.assertEqual(argv, ["/releases/0.9.0/bin/cadgen", "server", "--port", str(daemon.selected_port())])
        self.assertEqual(env["PYTHONPATH"], "/elsewhere", "none of this installation's code")
        self.assertNotIn(daemon.INSTALLATION_ENV, env)

    def test_with_nothing_newer_it_starts_its_own_daemon(self) -> None:
        from cadgen.engine import client, daemon

        argv, env = self.start(None)
        self.assertEqual(argv, [sys.executable, "-P", "-m", client.DAEMON_MODULE])
        self.assertEqual(env["PYTHONPATH"].split(os.pathsep)[0], daemon.engine_root())


if __name__ == "__main__":
    unittest.main()
