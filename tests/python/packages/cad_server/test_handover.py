"""The install command run by cad (``cad_server._internal.install_script``): BRIDGE-ONLY, in install mode once for a
computer a shipped updater brought (the bridge, ``test_setup``); the install command has no other mode, and cad's own
update runs it by ``cad plugin update`` (``test_auto_update``).

Here: the schedule (``plan``) and the server's side (``Carrier``) with a stand-in of the install command, a real
process writing each kind of report. A real 0.11.10 handing over to this build is the update rehearsal's.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import places
from cad_server._internal import arrival, install_script, installations, telemetry_send
from tests.python.packages.cad_server import test_arrival

OLD, X, Y = "0.11.10", "0.12.0", "0.12.1"
HOUR, DAY = install_script.RETRY_SECONDS, install_script.DAY_SECONDS
# The install command's stand-in: notes the environment it ran in, in the file its second argument names, then writes
# the report CAD_INSTALL_REPORT names, of the kind its first argument says (``none``: none; ``hang``: none, ever).
STAND_IN = """import json, os, sys, time
kind, noted = sys.argv[1], sys.argv[2]
with open(noted, "a", encoding="utf-8") as out:
    out.write(json.dumps({key: os.environ.get(key) for key in ("CAD_INSTALL_REPORT", "CAD_INSTALL_UPDATE",
                                                                "UV_NO_MODIFY_PATH")}) + "\\n")
if kind == "hang":
    time.sleep(600)
reports = {"done": {"setup": 0, "apps": {"one": "updated", "two": "not found"}},
           "setup": {"setup": 1, "apps": {"one": "installed"}},
           "app": {"setup": 0, "apps": {"one": "installed", "two": "failed"}},
           "shapeless": ["not", "a", "report"]}
if kind in reports:
    with open(os.environ["CAD_INSTALL_REPORT"], "w", encoding="utf-8") as out:
        json.dump({"schema": "text-to-cad install report/1", "release": None, **reports[kind]}
                  if isinstance(reports[kind], dict) else reports[kind], out)
"""


class State(unittest.TestCase):
    """A state folder of the test's own, and the stand-in of the install command."""

    def setUp(self) -> None:
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="cad-handover-")))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.stand_in = self.root / "install command.py"
        self.stand_in.write_text(STAND_IN, encoding="utf-8")
        self.noted = self.root / "noted.jsonl"
        patch = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.root / "state"),
                                             install_script.INSTALLER_ENV: self.command("done")})
        patch.start()
        self.addCleanup(patch.stop)
        self.said: list[str] = []

    def command(self, kind: str) -> str:
        return f'"{sys.executable}" "{self.stand_in}" {kind} "{self.noted}"'

    def runs(self, kind: str):
        return mock.patch.dict(os.environ, {install_script.INSTALLER_ENV: self.command(kind)})

    def ran(self) -> list[dict]:
        return [json.loads(line) for line in self.noted.read_text(encoding="utf-8").splitlines()] \
            if self.noted.exists() else []


class Schedule(unittest.TestCase):
    """``plan``: when the server runs the install command."""

    def plan(self, record, current=Y, *, wall=10_000.0, mono=500.0, began=0.0, tried=None):  # noqa: PLR0913
        return install_script.plan(record, current, wall=wall, mono=mono, began=began, tried=tried)

    def test_the_schedule(self) -> None:
        owed = {"mode": "install", "version": Y, "state": "owed", "attempts": 0, "first": None, "last": None}
        # The first once the server has run longer than a shipped switch can still be deciding to go back.
        first = install_script.FIRST_SECONDS
        self.assertEqual(first, 300.0)
        self.assertIsNone(self.plan(owed, mono=first - 1), "a switch may yet go back from this server")
        self.assertEqual(self.plan(owed, mono=first), "attempt")
        with mock.patch.dict(os.environ, {install_script.FIRST_ENV: "0"}):
            self.assertEqual(self.plan(owed, mono=0.0), "attempt", "a test's computers set it")
        with mock.patch.dict(os.environ, {install_script.FIRST_ENV: "soon"}):
            self.assertIsNone(self.plan(owed, mono=first - 1), "a word that is no number: the default")
        self.assertIsNone(self.plan(owed, current=OLD), "switched back to the release before: nothing runs")
        self.assertIsNone(self.plan(owed, current=None))
        self.assertEqual(self.plan(owed, current="0.12.2"), "superseded", "a later release took over first")
        for state in ("done", "superseded", "gave up"):
            self.assertIsNone(self.plan({**owed, "state": state}))
        self.assertIsNone(self.plan(None))

        failed = {**owed, "attempts": 1, "first": 10_000.0, "last": 10_000.0}
        # At a server's start: not sooner than an hour after the last, by the wall clock, or by its own run where the
        # wall clock was set back; whatever current names now.
        self.assertIsNone(self.plan(failed, wall=10_000.0 + HOUR - 1, mono=10.0))
        self.assertEqual(self.plan(failed, current="0.12.2", wall=10_000.0 + HOUR, mono=10.0), "attempt")
        self.assertIsNone(self.plan(failed, wall=5_000.0, mono=HOUR - 1), "the clock set back: its run counts")
        self.assertEqual(self.plan(failed, wall=5_000.0, mono=HOUR), "attempt")
        # A server that tried: once a day while it runs, by either clock.
        tried = {"mono": 100.0, "tried": 100.0 - HOUR}
        self.assertIsNone(self.plan(failed, wall=10_000.0 + DAY - 1, **tried))
        self.assertEqual(self.plan(failed, wall=10_000.0 + DAY, **tried), "attempt")
        self.assertEqual(self.plan(failed, wall=5_000.0, mono=100.0 + DAY, tried=100.0), "attempt")
        # The bound: 30 attempts, or 30 days since the first (never by a clock set back).
        self.assertEqual(self.plan({**failed, "attempts": install_script.ATTEMPTS}, wall=10_000.0 + DAY), "gave up")
        self.assertEqual(self.plan(failed, wall=10_000.0 + install_script.GIVE_UP_SECONDS), "gave up")
        self.assertIsNone(self.plan(failed, wall=1_000.0, mono=10.0), "a clock set back gives up nothing")


class Carrying(State):
    """``Carrier.tend``: the server begins an attempt, watches it, and judges the report as it ends -- the stand-in a
    real process, waited for, never slept on."""

    def setUp(self) -> None:
        super().setUp()
        first = mock.patch.dict(os.environ, {install_script.FIRST_ENV: "0"})
        first.start()
        self.addCleanup(first.stop)

    def tend(self, carrier, name=Y, **clocks):
        return carrier.tend(name, self.said.append, **clocks)

    def finish(self, carrier) -> None:
        if carrier.process is not None:
            carrier.process.wait(timeout=60)

    def owed(self, version: str = Y, now: float = 1000.0) -> None:
        install_script.owe(version, now=now)
        installations.point(version)

    def test_install_mode_runs_once_and_is_done(self) -> None:
        self.owed()
        carrier = install_script.Carrier(began=0.0)
        self.assertEqual(self.tend(carrier, mono=30.0, wall=1000.0), "attempt")
        self.finish(carrier)
        self.assertIsNone(self.tend(carrier, mono=60.0, wall=1100.0))
        self.assertEqual(self.said, [f"the install command, owed for cad {Y}: done (attempt 1)"])
        record = install_script.read()
        self.assertEqual((record["mode"], record["state"], record["attempts"], record["installed"]),
                         ("install", "done", 1, True))
        [ran] = self.ran()
        report = str(places.state_dir() / install_script.REPORT)
        self.assertEqual(ran, {"CAD_INSTALL_REPORT": report, "CAD_INSTALL_UPDATE": None, "UV_NO_MODIFY_PATH": "1"})
        self.assertIsNone(self.tend(carrier, mono=60.0 + 3 * DAY), "nothing owed any more")
        self.assertEqual(len(self.ran()), 1)

    def test_a_failure_is_tried_again_later_and_never_sooner(self) -> None:
        self.owed()
        carrier = install_script.Carrier(began=0.0)
        for kind, why in (("app", "app"), ("setup", "setup"), ("none", "no_report"), ("shapeless", "no_report")):
            with self.subTest(kind=kind), self.runs(kind):
                attempts = len(self.ran())
                wall = 1000.0 + attempts * DAY
                self.assertEqual(self.tend(carrier, mono=30.0 + attempts * DAY, wall=wall), "attempt")
                self.finish(carrier)
                self.assertIsNone(self.tend(carrier, mono=31.0 + attempts * DAY, wall=wall + 1))
                self.assertEqual(self.said[-1], f"the install command, owed for cad {Y}: attempt {attempts + 1} of at "
                                                f"most 30 failed ({why}); it runs again later")
                self.assertIsNone(self.tend(carrier, mono=32.0 + attempts * DAY, wall=wall + HOUR),
                                  "a server that tried waits a day")
        self.assertEqual(install_script.read()["state"], "owed", "never done")
        # A server started after a failure: an hour after the last attempt began.
        restarted = install_script.Carrier(began=0.0)
        last = install_script.read()["last"]
        self.assertIsNone(self.tend(restarted, mono=10.0, wall=last + HOUR - 1))
        self.assertEqual(self.tend(restarted, mono=10.0, wall=last + HOUR), "attempt")
        self.finish(restarted)
        self.tend(restarted, mono=11.0, wall=last + HOUR + 1)
        self.assertEqual(install_script.read()["state"], "done")

    def test_install_mode_waits_for_the_switch_and_marks_cad_installed(self) -> None:
        os.environ.pop(install_script.FIRST_ENV)
        install_script.owe(Y, now=1000.0)
        install_script.owe(Y, now=2000.0)  # the updater's second run keeps the record
        self.assertEqual(install_script.read()["owed"], 1000.0)
        installations.point(OLD)
        carrier = install_script.Carrier(began=0.0)
        self.assertIsNone(self.tend(carrier, mono=10 * HOUR), "current names the release before: nothing runs")
        installations.point(Y)
        self.assertIsNone(self.tend(carrier, mono=install_script.FIRST_SECONDS - 1))
        with self.runs("app"):
            self.assertEqual(self.tend(carrier, mono=install_script.FIRST_SECONDS, wall=5000.0), "attempt")
            self.finish(carrier)
        self.tend(carrier, mono=install_script.FIRST_SECONDS + 1, wall=5001.0)
        record = install_script.read()
        self.assertEqual((record["state"], record["outcome"], record["installed"]), ("owed", "app", True),
                         "an app failed: owed still, but cad was installed")
        # Its next attempt runs whatever current names now: the uv tool's server carries it on.
        installations.point("0.12.2")
        later = install_script.Carrier(began=0.0)
        self.assertEqual(self.tend(later, name="0.12.2", wall=5000.0 + HOUR), "attempt")
        self.finish(later)

    def test_superseded_given_up_and_nothing_without_a_command(self) -> None:
        install_script.owe(Y)
        installations.point("0.12.2")
        self.assertEqual(self.tend(install_script.Carrier(began=0.0), wall=5000.0), "superseded")
        self.assertEqual((install_script.read()["state"], install_script.read()["ended"]), ("superseded", 5000.0))
        self.assertEqual(self.said, [f"the install command, owed for cad {Y}: a later cad took over, after 0 attempts"])
        install_script._write({**install_script._new("install", X, 1000.0), "attempts": install_script.ATTEMPTS,
                               "first": 1000.0, "last": 1000.0, "outcome": "app"})
        self.assertEqual(self.tend(install_script.Carrier(began=0.0), name=X, wall=1000.0 + DAY), "gave up")
        self.assertEqual(self.said[-1], f"the install command, owed for cad {X}: given up after 30 attempts")
        install_script.owe(Y)
        installations.point(Y)
        with mock.patch.dict(os.environ, {install_script.INSTALLER_ENV: ""}):
            self.assertIsNone(self.tend(install_script.Carrier(began=0.0)))
        self.assertIsNone(self.tend(install_script.Carrier(began=0.0), name=X), "owed for a later release than this")
        self.assertEqual(install_script.read()["attempts"], 0)

    def test_a_record_of_the_update_mode_that_is_gone_is_no_record(self) -> None:
        install_script._write(install_script._new("update", Y, 1000.0))
        self.assertIsNone(install_script.read())
        self.assertIsNone(self.tend(install_script.Carrier(began=0.0), wall=2000.0), "nothing runs for it")
        self.assertEqual(self.ran(), [])

    def test_an_attempt_another_server_began_and_one_that_hangs_or_cannot_start(self) -> None:
        installations.point(Y)
        record = {**install_script._new("install", Y, 1000.0), "attempts": 1, "first": 1000.0, "last": 1000.0,
                  "outcome": "running"}
        install_script._write(record)
        carrier = install_script.Carrier(began=0.0)
        self.assertIsNone(self.tend(carrier, wall=1000.0 + 60), "still running, maybe: its report is not there yet")
        report = places.state_dir() / install_script.REPORT
        report.write_text(json.dumps({"setup": 0, "apps": {}}), encoding="utf-8")
        self.assertIsNone(self.tend(carrier, wall=1000.0 + 120))
        self.assertEqual(install_script.read()["state"], "done", "judged by the server after it, once its report came")
        install_script._write(record)
        report.unlink()
        self.assertEqual(self.tend(carrier, wall=1000.0 + install_script.RUN_SECONDS, mono=10.0), "attempt",
                         "no report after the longest run: failed, and the hour since has passed")
        self.assertIn("attempt 1 of at most 30 failed (no_report)", self.said[-1])
        self.finish(carrier)
        self.tend(carrier)
        # One that hangs is stopped with what it started, after RUN_SECONDS of the server's own clock.
        install_script._write({**install_script._new("install", Y, 1000.0)})
        with self.runs("hang"):
            self.assertEqual(self.tend(carrier, mono=0.0, wall=9000.0), "attempt")
        process = carrier.process
        self.assertIsNone(self.tend(carrier, mono=install_script.RUN_SECONDS - 1, wall=9001.0))
        self.tend(carrier, mono=install_script.RUN_SECONDS, wall=9002.0)
        self.assertIsNotNone(process.poll(), "stopped")
        self.assertEqual(install_script.read()["outcome"], "no_report")
        # One that cannot start: failed at once.
        install_script._write({**install_script._new("install", Y, 1000.0)})
        with mock.patch.dict(os.environ, {install_script.INSTALLER_ENV: str(self.root / "no such program")}):
            self.assertEqual(self.tend(install_script.Carrier(began=0.0), wall=20_000.0), "attempt")
        self.assertEqual(install_script.read()["outcome"], "other")


class Defaults(unittest.TestCase):
    def test_the_hosted_command_unless_a_test_names_its_own_and_the_environment_it_runs_in(self) -> None:
        with mock.patch.dict(os.environ, {"PYTHONPATH": "x", install_script.UPDATE_ENV: "1"}):
            os.environ.pop(install_script.INSTALLER_ENV, None)
            if os.name != "nt":
                self.assertEqual(install_script.installer(),
                                 ["sh", "-c", "curl -fsSL https://texttocad.dev/install.sh | sh"])
            os.environ[install_script.INSTALLER_ENV] = ""
            self.assertFalse(install_script.installer(), "empty: nothing")
            self.assertEqual(install_script.run(), 0, "nothing to run")
            found = install_script.environment(report=Path("r.json"))
            self.assertEqual((found["CAD_INSTALL_REPORT"], found["UV_NO_MODIFY_PATH"]), ("r.json", "1"))
            self.assertNotIn("PYTHONPATH", found)
            self.assertNotIn(install_script.UPDATE_ENV, found, "no mode: never inherited, never set")
            # a `cad setup` the command reaches runs nothing (``cad_server.cli.setup``)
            self.assertEqual(found[install_script.BY_CAD_ENV], "1")
            self.assertNotIn(install_script.REPORT_ENV, install_script.environment(report=None))


class Counted(State):
    """Install mode's ends are counted (``analytics.arrival``) beside the settings of the server that ran it, as
    ``test_arrival`` shows the counting itself."""

    def setUp(self) -> None:
        super().setUp()
        environment = mock.patch.dict(os.environ, test_arrival.QUIET)
        environment.start()
        self.addCleanup(environment.stop)
        spawn = mock.patch.object(telemetry_send, "_spawn", lambda settings: None)
        spawn.start()
        self.addCleanup(spawn.stop)
        self.settings = places.state_dir() / "settings.json"
        test_arrival.ArrivalTest.tell(self)

    def test_install_mode_is_counted(self) -> None:
        with mock.patch.object(arrival, "read", side_effect=lambda name: {"from": OLD} if name == Y else None):
            installed = {**install_script._new("install", Y, 0.0), "attempts": 2}
            install_script.ended({**installed, "attempts": 1}, "failed", self.said.append, why="app")
            install_script.ended(installed, "done", self.said.append)
            install_script.ended({**installed, "version": X, "attempts": 30}, "gave_up", self.said.append)
        self.assertEqual(test_arrival.ArrivalTest.kept(self), [
            {"step": "handover", "route": "updater", "from": OLD, "outcome": "failed", "reason": "app", "attempts": 1},
            {"step": "handover", "route": "updater", "from": OLD, "outcome": "done", "attempts": 2},
            {"step": "handover", "route": "updater", "from": "none", "outcome": "gave_up", "attempts": 30},
        ])
        self.assertEqual(len(self.said), 3, "each said in the server's log")


if __name__ == "__main__":
    unittest.main()
