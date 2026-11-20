"""How a computer got to a version, counted (``cad_server.analytics.arrival``): each step a word of cad's and a
number, under the rules every count goes by, and sent by a sender of its own -- a setup whose version never runs
again on the computer is heard from all the same, with no server and no later command. Each of cad's own updates
(``analytics.update``) is kept and sent the same way."""

from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from cad_server import analytics
from cad_server._internal import file_lock, telemetry_send
from tests.python.support import engine_daemon
from tests.python.support.cache_fixtures import await_
from tests.python.support.paths import add_sources

SRC = add_sources()
RELEASE = __import__("cad_server").__version__
# A release's process outside CI, its telemetry switches unset (``test_analytics``'s ``QUIET``).
QUIET = {"CAD_INSTALLATION_VERSION": RELEASE, "CI": "", "DO_NOT_TRACK": "", "CAD_TELEMETRY": "",
         analytics.NOTICE_ENV: "", "CAD_UPDATE_CHECK": "0", "CAD_API_URL": "http://127.0.0.1:9"}


class ArrivalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="arrival-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        environment = mock.patch.dict(os.environ, {**QUIET, "CAD_STATE_DIR": str(self.tmp / "state")})
        environment.start()
        self.addCleanup(environment.stop)
        self.settings = analytics.settings_path()
        self.assertEqual(self.settings, self.tmp / "state" / "settings.json")  # a process of no version: the state folder's
        self.started: list[Path] = []
        self.spawn = telemetry_send._spawn
        spawn = mock.patch.object(telemetry_send, "_spawn", self.started.append)
        spawn.start()
        self.addCleanup(spawn.stop)

    def tell(self) -> None:
        """The person told what is sent by default, by a command (``notify``), on a computer whose last sender started
        long ago (the time of the data folder's lock)."""
        import io

        self.assertTrue(analytics.notify(io.StringIO(), path=self.settings))
        long_ago = time.time() - 2 * analytics.FLUSH_SECONDS
        os.utime(self.settings.with_name(file_lock.STATE_LOCK), (long_ago, long_ago))

    def kept(self) -> list[dict]:
        found = self.settings.with_name(analytics.ARRIVALS)
        return [json.loads(line)["arrival"] for line in found.read_text(encoding="utf-8").splitlines()] if found.exists() else []

    def sent(self) -> list[dict]:
        payloads: list[dict] = []
        telemetry_send.send(self.settings, send=lambda payload: payloads.append(payload) or True)
        return payloads

    def test_each_step_is_kept_beside_the_settings_and_sent_as_words_and_numbers(self) -> None:
        self.tell()
        arrive = analytics.arrival
        self.assertTrue(arrive("setup", route="updater", earlier="0.11.10", outcome="failed", reason="network"))
        self.assertTrue(arrive("setup", route="updater", earlier="0.11.10", outcome="failed", reason="network"))
        self.assertTrue(arrive("setup", route="setup", earlier=None, outcome="ok"))
        self.assertTrue(arrive("serving", route="setup", earlier="0.10.4", outcome="ok"))
        self.assertTrue(arrive("handover", route="updater", earlier="0.11.10", outcome="gave_up", attempts=7))
        self.assertTrue(arrive("handover", route="updater", earlier="0.11.10", outcome="failed", reason="no_report",
                               attempts=1))
        # A file of its own, never the spool an earlier release's sender in the same folder takes and drops.
        self.assertFalse(self.settings.with_name(analytics.SPOOL).exists())
        self.assertEqual(len(self.kept()), 6)
        self.assertEqual(self.started, [self.settings] * 6, "a sender at once for each, none set to start later")
        [batch] = self.sent()
        self.assertEqual((batch["schema"], batch["process"], batch["version"]), (12, "cli", RELEASE))
        self.assertNotIn("client", batch)
        self.assertEqual(batch["events"], [
            {"name": "arrival", "step": "handover", "route": "updater", "from": "0.11.10", "outcome": "failed",
             "reason": "no_report", "attempts": 1, "count": 1},
            {"name": "arrival", "step": "handover", "route": "updater", "from": "0.11.10", "outcome": "gave_up",
             "attempts": 7, "count": 1},
            {"name": "arrival", "step": "serving", "route": "setup", "from": "0.10.4", "outcome": "ok", "count": 1},
            {"name": "arrival", "step": "setup", "route": "setup", "from": "none", "outcome": "ok", "count": 1},
            {"name": "arrival", "step": "setup", "route": "updater", "from": "0.11.10", "outcome": "failed",
             "reason": "network", "count": 2},
        ])
        self.assertEqual(self.kept(), [], "taken by the sender")

    def test_only_words_of_the_vocabulary_and_a_version_s_name_are_counted(self) -> None:
        self.tell()
        arrive = analytics.arrival
        for refused in (dict(step="install", route="setup", earlier=None, outcome="ok"),
                        dict(step="setup", route="store", earlier=None, outcome="ok"),
                        dict(step="serving", route="setup", earlier=None, outcome="failed"),  # a serving has no failure
                        dict(step="setup", route="setup", earlier="/Users/someone/cad", outcome="ok"),
                        dict(step="setup", route="setup", earlier="0.11.10 (broken)", outcome="ok"),
                        dict(step="setup", route="setup", earlier="1" * 33, outcome="ok"),
                        dict(step="setup", route="setup", earlier="latest", outcome="ok"),
                        dict(step="handover", route="setup", earlier=None, outcome="done"),  # attempts, always
                        dict(step="handover", route="setup", earlier=None, outcome="done", attempts=-1),
                        dict(step="handover", route="setup", earlier=None, outcome="done", attempts=True),
                        dict(step=["setup"], route="setup", earlier=None, outcome="ok")):
            self.assertFalse(arrive(**refused), refused)
        self.assertEqual(self.kept(), [])
        # A reason outside the step's words is ``other``; one on a step that did not fail, and attempts on a step that
        # has none, go no further; attempts past the most are the most.
        self.assertTrue(arrive("setup", route="setup", earlier=None, outcome="failed", reason="uv could not resolve"))
        self.assertTrue(arrive("setup", route="setup", earlier=None, outcome="failed", reason="app"))
        self.assertTrue(arrive("setup", route="setup", earlier=None, outcome="ok", reason="network", attempts=3))
        self.assertTrue(arrive("handover", route="setup", earlier=None, outcome="superseded", attempts=10 ** 6))
        self.assertEqual(self.kept(), [
            {"step": "setup", "route": "setup", "from": "none", "outcome": "failed", "reason": "other"},
            {"step": "setup", "route": "setup", "from": "none", "outcome": "failed", "reason": "other"},
            {"step": "setup", "route": "setup", "from": "none", "outcome": "ok"},
            {"step": "handover", "route": "setup", "from": "none", "outcome": "superseded",
             "attempts": analytics.MAX_ATTEMPTS},
        ])
        # A row changed on disk is checked again as it is taken: one no arrival would keep is not sent.
        with open(self.settings.with_name(analytics.ARRIVALS), "a", encoding="utf-8") as handle:
            row = {"answer": list(analytics._answer(analytics._read(self.settings))), "at": time.time(),
                   "source": {}, "arrival": {"step": "setup", "route": "setup", "from": "/home/someone", "outcome": "ok"}}
            handle.write(json.dumps(row) + "\n")
        [batch] = self.sent()
        self.assertEqual([event["count"] for event in batch["events"]], [1, 2, 1])
        self.assertNotIn("someone", json.dumps(batch))

    def test_nothing_is_counted_untold_after_a_no_in_ci_from_a_development_build_or_by_the_environment(self) -> None:
        def arrive() -> bool:
            return analytics.arrival("setup", route="setup", earlier=None, outcome="ok")

        self.assertFalse(arrive(), "nobody told yet: a computer with nothing older that no command told")
        self.assertEqual(analytics.status(path=self.settings)["reason"], "untold")
        self.tell()
        for switches in ({"DO_NOT_TRACK": "1"}, {"CAD_TELEMETRY": "0"}, {"CI": "true"},
                         {"CAD_INSTALLATION_VERSION": f"{RELEASE}-dev.20261115120000"}):
            with mock.patch.dict(os.environ, switches):
                self.assertFalse(arrive(), switches)
        self.assertEqual((self.kept(), self.started), ([], []))
        self.assertTrue(arrive())
        analytics.choose(False, by="cli", path=self.settings)
        self.assertFalse(self.settings.with_name(analytics.ARRIVALS).exists(), "a no deletes what was kept")
        self.assertFalse(arrive())
        self.assertEqual(self.sent(), [])

    def test_an_update_is_kept_with_the_arrivals_and_sent_as_words_and_numbers_under_the_same_rules(self) -> None:
        update = analytics.update
        failed = dict(earlier="0.11.12", outcome="failed", reason="upgrade", tries=2, installer="uv", asked=False)
        self.tell()
        with mock.patch.dict(os.environ, {"DO_NOT_TRACK": "1"}):
            self.assertFalse(update(**failed), "the environment's no")
        self.assertTrue(update(**failed))
        self.assertTrue(update(**failed))
        self.assertTrue(update(earlier="0.11.12", outcome="installed", tries=1, installer="pipx", asked=True,
                               plugin="ok"))
        self.assertTrue(update(earlier=None, outcome="restored", reason="older", installer="uv"))
        for refused in (dict(failed, outcome="updated"), dict(failed, reason="uv could not reach pypi.org"),
                        dict(failed, reason=None),
                        dict(failed, outcome="restored", reason="put_back"), dict(failed, plugin="ok"),
                        dict(failed, installer="pip"), dict(failed, installer=None), dict(failed, tries=0),
                        dict(failed, tries=True), dict(failed, asked="no"), dict(failed, earlier="/Users/someone"),
                        dict(failed, outcome="installed", reason=None, plugin="skipped")):
            self.assertFalse(update(**refused), refused)
        self.assertTrue(update(**dict(failed, outcome="current")), "a reason on no failure goes no further")
        self.assertEqual(self.started, [self.settings] * 5, "a sender at once for each, as an arrival's")
        self.assertTrue(analytics.arrival("setup", route="setup", earlier=None, outcome="ok"))
        [batch] = self.sent()
        self.assertEqual((batch["schema"], batch["process"], batch["version"]), (12, "cli", RELEASE))
        self.assertEqual([event for event in batch["events"] if event["name"] == "update"], [
            {"name": "update", "from": "0.11.12", "outcome": "current", "tries": 2, "installer": "uv", "asked": False,
             "plugin": "none", "count": 1},
            {"name": "update", "from": "0.11.12", "outcome": "failed", "reason": "upgrade", "tries": 2, "installer": "uv",
             "asked": False, "plugin": "none", "count": 2},
            {"name": "update", "from": "0.11.12", "outcome": "installed", "tries": 1, "installer": "pipx", "asked": True,
             "plugin": "ok", "count": 1},
            {"name": "update", "from": "none", "outcome": "restored", "reason": "older", "tries": 1, "installer": "uv",
             "asked": False, "plugin": "none", "count": 1},
        ])
        self.assertEqual([event["name"] for event in batch["events"]].count("arrival"), 1, "beside the arrivals")
        self.assertFalse(self.settings.with_name(analytics.ARRIVALS).exists(), "taken by the sender")

    def test_each_arrival_starts_a_sender_at_once_and_a_command_none_more_that_window(self) -> None:
        window = analytics.FLUSH_SECONDS
        self.tell()  # the last sender started long ago
        lock = self.settings.with_name(file_lock.STATE_LOCK)
        now = time.time()
        started: list[Path] = []

        def at_once(at: float) -> bool:
            return telemetry_send.start_now(self.settings, now=at, spawn=started.append)

        self.assertTrue(at_once(now))
        self.assertTrue(at_once(now + 1), "one more a second later: started at once too")
        self.assertEqual(started, [self.settings, self.settings])
        self.assertEqual(lock.stat().st_mtime, now + 1, "the lock's time: when the last sender started")
        # A command's sender goes by that time, as in 0.11.10: none within a window of it.
        self.assertTrue(analytics.spool({"builds": [{"kind": "xbf", "via": "script", "outcome": "ok", "seconds": 1.0}]},
                                        path=self.settings))
        self.assertFalse(telemetry_send.start_if_due(self.settings, now=now + window, spawn=started.append))
        self.assertTrue(telemetry_send.start_if_due(self.settings, now=now + window + 2, spawn=started.append))
        # A sender that could not be started leaves the lock's time as it was.
        before = lock.stat().st_mtime

        def broken(settings: Path) -> None:
            raise OSError("no such program")

        self.assertFalse(telemetry_send.start_now(self.settings, now=now + 3 * window, spawn=broken))
        self.assertEqual(lock.stat().st_mtime, before)
        # Detached as every sender is, sending as it starts: nothing it is told to wait for.
        with mock.patch.object(subprocess, "Popen") as popen:
            self.spawn(self.settings)
        [call] = popen.call_args_list
        self.assertEqual(call.args[0], [sys.executable, "-P", "-m", "cad_server._internal.telemetry_send"])
        self.assertEqual(call.kwargs["stdout"], subprocess.DEVNULL)

    def test_a_fresh_folder_s_arrivals_each_start_a_sender_at_once(self) -> None:
        # A version's data folder, made a moment ago as its setup imported (its lock taken then: made then). Its lock's
        # time says nothing of a sender: its first arrival is sent at once, not a window later, and so is each after.
        analytics.choose(True, by="cli", path=self.settings)
        lock = self.settings.with_name(file_lock.STATE_LOCK)
        self.assertLess(time.time() - lock.stat().st_mtime, analytics.FLUSH_SECONDS, "the lock made a moment ago")
        self.assertTrue(analytics.arrival("setup", route="updater", earlier="0.11.10", outcome="ok"))
        self.assertTrue(analytics.arrival("serving", route="updater", earlier="0.11.10", outcome="ok"))
        self.assertTrue(analytics.arrival("handover", route="updater", earlier="0.11.10", outcome="done", attempts=1))
        self.assertEqual(self.started, [self.settings] * 3, "each at once, none set to start later")
        self.assertLessEqual(lock.stat().st_mtime, time.time(), "no time to come: nothing waits to start")
        self.assertEqual(sorted(path.name for path in self.settings.parent.iterdir()),
                         ["settings.json", "settings.lock", analytics.ARRIVALS])


class WithNoServerTest(unittest.TestCase):
    """The hard case: a ``cad setup`` that counts its step and ends, no server of its version running then or after."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="arrival-sent-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.state = self.tmp / "state"
        self.received: list[dict] = []

        received = self.received

        class Receiver(http.server.BaseHTTPRequestHandler):  # a stand-in for the receiver, on this machine alone
            def do_POST(self) -> None:  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if self.path == "/events":
                    received.append(json.loads(body))
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args) -> None:
                pass

        self.receiver = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
        threading.Thread(target=self.receiver.serve_forever, daemon=True).start()
        self.addCleanup(self.receiver.server_close)
        self.addCleanup(self.receiver.shutdown)

    def test_a_command_s_failed_setup_reaches_the_receiver_by_a_sender_of_its_own(self) -> None:
        settings = self.state / "settings.json"
        analytics.choose(True, by="cli", path=settings)
        lock = settings.with_name(file_lock.STATE_LOCK)
        lock.touch()
        long_ago = time.time() - 2 * analytics.FLUSH_SECONDS
        os.utime(lock, (long_ago, long_ago))  # a computer whose last sender started long ago
        env = {**os.environ, **QUIET, "PYTHONPATH": str(SRC), "CAD_STATE_DIR": str(self.state), "HOME": str(self.tmp),
               "CAD_API_URL": f"http://127.0.0.1:{self.receiver.server_address[1]}"}
        # The command: it counts its setup's failure and ends, saying the pid of the one process it started.
        command = ("import subprocess, sys\n"
                   "real = subprocess.Popen\n"
                   "class Seen(real):\n"
                   "    def __init__(self, *args, **kwargs):\n"
                   "        super().__init__(*args, **kwargs)\n"
                   "        print(self.pid, flush=True)\n"
                   "subprocess.Popen = Seen\n"
                   "from cad_server import analytics\n"
                   "sys.exit(0 if analytics.arrival('setup', route='updater', earlier='0.11.10', outcome='failed',"
                   " reason='network') else 1)\n")
        done = subprocess.run([sys.executable, "-c", command], env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        sender = int(done.stdout.split()[0])
        self.addCleanup(self.gone, sender)
        await_(lambda: self.received, "the batch at the stand-in receiver")
        await_(lambda: not engine_daemon._alive(sender), "the sender to exit once it sent")
        [batch] = self.received
        self.assertEqual((batch["schema"], batch["process"], batch["version"]), (12, "cli", RELEASE))
        self.assertEqual(batch["events"], [{"name": "arrival", "step": "setup", "route": "updater", "from": "0.11.10",
                                            "outcome": "failed", "reason": "network", "count": 1}])
        self.assertFalse(settings.with_name(analytics.ARRIVALS).exists())
        self.assertFalse(settings.with_name(analytics.KEPT).exists(), "taken: nothing kept for later")

    def gone(self, pid: int) -> None:
        """The sender this test started, gone: awaited, and stopped where it is not."""
        deadline = time.monotonic() + 60
        while engine_daemon._alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        if engine_daemon._alive(pid):
            import signal

            os.kill(pid, signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
