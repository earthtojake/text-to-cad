"""The hand-over a version owes after a shipped updater brought it, and what its server makes of it
(``cad_server._internal.install_script``), and how a version arrived (``cad_server._internal.arrival``).

``--engine-update`` owes the hosted install script's run (``test_setup``); the version's own server runs it, from its
tending, while ``installations/current`` names its version, one attempt at a time, on a schedule, until a report says
it worked. Here: the schedule (``plan``), the server's side (``Carrier``, its attempt started by a stand-in), a real
attempt with a stand-in of the install script writing each kind of report, and the wait for the site's install.py. A
real 0.11.10 handing over to this build, its server and the real install script included, is
scripts/test/rehearse-update.py's.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from cad.engine import places
from cad_server._internal import arrival, install_script, installations, telemetry_send
from cad_server._internal.file_lock import attempt as hold
from tests.python.packages.cad_server import test_arrival

OLD, X, Y = "0.11.10", "0.12.0", "0.12.1"
HOUR, DAY = install_script.RETRY_SECONDS, install_script.DAY_SECONDS
# The install script's stand-in: writes the report CAD_INSTALL_REPORT names, of the kind its first argument says
# (``none``: none), and notes the environment it ran in, in the file its second argument names.
STAND_IN = """import json, os, sys
kind, noted = sys.argv[1], sys.argv[2]
with open(noted, "a", encoding="utf-8") as out:
    out.write(json.dumps({"report": os.environ.get("CAD_INSTALL_REPORT"),
                          "uv": os.environ.get("UV_NO_MODIFY_PATH")}) + "\\n")
reports = {"done": {"setup": 0, "apps": {"one": "installed", "two": "not found", "three": "skipped"}},
           "setup": {"setup": 1, "apps": {"one": "installed"}},
           "app": {"setup": 0, "apps": {"one": "installed", "two": "failed"}},
           "shapeless": ["not", "a", "report"]}
if kind in reports:
    with open(os.environ["CAD_INSTALL_REPORT"], "w", encoding="utf-8") as out:
        json.dump({"schema": "text-to-cad install report/1", "release": "0.12.1", **reports[kind]}
                  if isinstance(reports[kind], dict) else reports[kind], out)
"""


class State(unittest.TestCase):
    """A state folder of the test's own."""

    def setUp(self) -> None:
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix="cad-handover-")))
        self.addCleanup(shutil.rmtree, self.root, True)
        patch = mock.patch.dict(os.environ, {"CAD_STATE_DIR": str(self.root / "state"),
                                             install_script.INSTALLER_ENV: "stand-in"})
        patch.start()
        self.addCleanup(patch.stop)
        self.said: list[str] = []

    def owed(self, name: str = Y, **fields) -> dict:
        install_script.owe(name, now=1000.0)
        record = {**install_script.read(name), **fields}
        install_script._write(name, record)
        return record


class Schedule(unittest.TestCase):
    """``plan``: when a version's server runs its hand-over."""

    def plan(self, record, current=Y, *, wall=10_000.0, mono=500.0, began=0.0, tried=None):  # noqa: PLR0913
        return install_script.plan(record, Y, current, wall=wall, mono=mono, began=began, tried=tried)

    def test_the_schedule(self) -> None:
        owed = {"schema": install_script.SCHEMA, "state": "owed", "attempts": 0, "first": None, "last": None}
        # The first once the server has run longer than a shipped switch can still be deciding to go back from it.
        first = install_script.FIRST_SECONDS
        self.assertEqual(first, 300.0)
        self.assertIsNone(self.plan(owed, mono=first - 1), "a switch may yet go back from this server")
        self.assertEqual(self.plan(owed, mono=first), "attempt")
        with mock.patch.dict(os.environ, {install_script.FIRST_ENV: "0"}):
            self.assertEqual(self.plan(owed, mono=0.0), "attempt", "a test's computers set it")
        with mock.patch.dict(os.environ, {install_script.FIRST_ENV: "soon"}):
            self.assertIsNone(self.plan(owed, mono=first - 1), "a word that is no number: the default")
        self.assertEqual(self.plan(owed), "attempt")
        self.assertIsNone(self.plan(owed, current=OLD), "switched back to the release before: nothing runs")
        self.assertIsNone(self.plan(owed, current=None))
        self.assertEqual(self.plan(owed, current="0.12.2"), "superseded", "a newer version took over")
        for state in ("done", "superseded", "gave up"):
            self.assertIsNone(self.plan({**owed, "state": state}))
        self.assertIsNone(self.plan(None))

        failed = {**owed, "attempts": 1, "first": 10_000.0, "last": 10_000.0}
        # At a server's start (it has tried nothing since): not sooner than an hour after the last, by the wall clock,
        # or by its own run where the wall clock was set back.
        self.assertIsNone(self.plan(failed, wall=10_000.0 + HOUR - 1, mono=10.0))
        self.assertEqual(self.plan(failed, wall=10_000.0 + HOUR, mono=10.0), "attempt")
        self.assertIsNone(self.plan(failed, wall=5_000.0, mono=HOUR - 1), "the clock set back: its own run counts")
        self.assertEqual(self.plan(failed, wall=5_000.0, mono=HOUR), "attempt")
        # A server that tried: once a day while it runs, by either clock (its monotonic one stops while asleep).
        tried = {"mono": 100.0, "tried": 100.0 - HOUR}
        self.assertIsNone(self.plan(failed, wall=10_000.0 + DAY - 1, **tried))
        self.assertEqual(self.plan(failed, wall=10_000.0 + DAY, **tried), "attempt")
        self.assertEqual(self.plan(failed, wall=5_000.0, mono=100.0 + DAY, tried=100.0), "attempt")
        # The bound: 30 attempts, or 30 days since the first (never by a clock set back).
        self.assertEqual(self.plan({**failed, "attempts": install_script.ATTEMPTS}, wall=10_000.0 + DAY), "gave up")
        self.assertEqual(self.plan(failed, wall=10_000.0 + install_script.GIVE_UP_SECONDS), "gave up")
        self.assertIsNone(self.plan(failed, wall=1_000.0, mono=10.0), "a clock set back gives up nothing")


class Carrying(State):
    """``Carrier.tend``: what a version's server does with its hand-over at each tending, its attempts stood in for."""

    def tend(self, carrier, name=Y, **clocks):
        with mock.patch.object(install_script, "start", side_effect=lambda *_: self.process) as started:
            step = carrier.tend(name, self.said.append, **clocks)
        return step, started.call_count

    def setUp(self) -> None:
        super().setUp()
        self.process = mock.Mock(**{"poll.return_value": None})
        installations.point(Y)

    def test_one_attempt_at_a_time_and_each_end_told_once(self) -> None:
        self.owed()
        carrier = install_script.Carrier(began=-install_script.FIRST_SECONDS)  # running long enough
        self.assertEqual(self.tend(carrier, mono=30.0, wall=2000.0), ("attempt", 1))
        self.assertEqual(self.tend(carrier, mono=60.0), (None, 0), "its attempt still runs")
        # It began, and holds the computer's lock: no server starts another.
        self.process.poll.return_value = 0
        install_script._write(Y, {**install_script.read(Y), "attempts": 1, "first": 2000.0, "last": 2000.0,
                                  "outcome": "running"})
        with hold(install_script._lock()) as mine:
            self.assertTrue(mine)
            self.assertEqual(self.tend(install_script.Carrier(began=0.0), mono=90.0), (None, 0))
            self.assertTrue(install_script.in_flight())
        self.assertFalse(install_script.in_flight())
        # Stopped before it said how it went (the computer slept, the program was killed): no report, told once.
        self.assertEqual(self.tend(carrier, mono=120.0, wall=2010.0), (None, 0))
        self.assertEqual(self.said, ["the install script ran for cad 0.12.1's hand-over: attempt 1 of at most 30 failed "
                                     "(no_report); it runs again later"])
        record = install_script.read(Y)
        self.assertEqual((record["outcome"], record["told"], record["state"]), ("no_report", 1, "owed"))
        self.assertEqual(self.tend(carrier, mono=120.0 + DAY, wall=2010.0), ("attempt", 1), "a day later")
        self.assertEqual(len(self.said), 1)
        # Done: told once, and nothing after.
        self.process.poll.return_value = 0
        install_script._write(Y, {**install_script.read(Y), "attempts": 2, "last": 3000.0, "outcome": "done",
                                  "state": "done"})
        self.assertEqual(self.tend(carrier, mono=200.0 + DAY), (None, 0))
        self.assertEqual(self.said[-1], "the install script ran for cad 0.12.1's hand-over: done (attempt 2)")
        self.assertEqual(self.tend(carrier, mono=200.0 + 3 * DAY), (None, 0))
        self.assertEqual(len(self.said), 2)

    def test_a_rolled_back_switch_runs_nothing_a_newer_version_supersedes_and_the_bound_gives_up(self) -> None:
        self.owed()
        installations.point(OLD)
        self.assertEqual(self.tend(install_script.Carrier(began=0.0)), (None, 0), "current names the old release")
        installations.point("0.12.2")
        self.assertEqual(self.tend(install_script.Carrier(began=0.0), wall=5000.0), ("superseded", 0))
        self.assertEqual((install_script.read(Y)["state"], install_script.read(Y)["ended"]), ("superseded", 5000.0))
        self.assertEqual(self.said, ["a newer cad has taken over: cad 0.12.1's hand-over ends after 0 attempts"])
        installations.point(Y)
        self.owed(X, attempts=install_script.ATTEMPTS, first=1000.0, last=1000.0, outcome="app",
                  told=install_script.ATTEMPTS)
        installations.point(X)
        self.assertEqual(self.tend(install_script.Carrier(began=0.0), name=X, wall=1000.0 + DAY), ("gave up", 0))
        self.assertEqual(install_script.read(X)["state"], "gave up")
        self.assertEqual(self.said[-1], "cad 0.12.0's hand-over gave up after 30 attempts: the install script is not "
                                        "run again")

    def test_nothing_without_a_record_or_a_command(self) -> None:
        self.assertEqual(self.tend(install_script.Carrier(began=0.0)), (None, 0))
        self.owed()
        with mock.patch.dict(os.environ, {install_script.INSTALLER_ENV: ""}):
            self.assertEqual(self.tend(install_script.Carrier(began=0.0)), (None, 0))
        self.assertEqual(install_script.read(Y)["attempts"], 0)


class Attempting(State):
    """One real attempt (``attempt``): the install script's stand-in run, and its report judged."""

    def setUp(self) -> None:
        super().setUp()
        self.stand_in = self.root / "install script.py"
        self.stand_in.write_text(STAND_IN, encoding="utf-8")
        self.noted = self.root / "noted.jsonl"
        installations.point(Y)

    def command(self, kind: str) -> str:
        return f'"{sys.executable}" "{self.stand_in}" {kind} "{self.noted}"'

    def attempt(self, kind: str) -> str | None:
        with mock.patch.dict(os.environ, {install_script.INSTALLER_ENV: self.command(kind)}):
            return install_script.attempt(Y)

    def test_each_kind_of_report_and_the_record_it_leaves(self) -> None:
        self.owed()
        for count, kind in enumerate(("none", "shapeless", "setup", "app"), start=1):
            with self.subTest(kind=kind):
                self.assertEqual(self.attempt(kind), {"none": "no_report", "shapeless": "no_report"}.get(kind, kind))
                record = install_script.read(Y)
                self.assertEqual((record["state"], record["attempts"]), ("owed", count))
                self.assertFalse((places.data_dir(Y) / install_script.REPORT).exists() and kind == "none")
        first = install_script.read(Y)["first"]
        self.assertEqual(self.attempt("done"), "done")
        record = install_script.read(Y)
        self.assertEqual((record["state"], record["attempts"], record["outcome"], record["first"]), ("done", 5, "done",
                                                                                                    first))
        self.assertIsNone(self.attempt("done"), "done: nothing more runs")
        noted = [json.loads(line) for line in self.noted.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(noted), 5)
        self.assertEqual({(line["report"], line["uv"]) for line in noted},
                         {(str(places.data_dir(Y) / install_script.REPORT), "1")},
                         "told where to report, and uv's installer told to leave shell profiles alone")

    def test_a_report_from_before_this_attempt_is_not_its_report(self) -> None:
        self.owed()
        report = places.data_dir(Y) / install_script.REPORT
        report.write_text(json.dumps({"setup": 0, "apps": {}}), encoding="utf-8")
        self.assertEqual(self.attempt("none"), "no_report")

    def test_nothing_runs_while_another_attempt_runs_or_another_version_is_current(self) -> None:
        self.owed()
        with hold(install_script._lock()):
            self.assertIsNone(self.attempt("done"))
        installations.point(OLD)
        self.assertIsNone(self.attempt("done"))
        self.assertEqual(install_script.read(Y)["attempts"], 0)
        self.assertFalse(self.noted.exists(), "nothing ran")

    def test_a_site_that_never_names_the_release_and_current_moving_on_run_nothing(self) -> None:
        self.owed()
        site = Site(self, install_py(OLD))
        slept: list[float] = []

        def sleep(seconds: float) -> None:
            slept.append(seconds)
            if sum(slept) >= 3.0:
                installations.point("0.12.2")

        with mock.patch.dict(os.environ, {install_script.INSTALLER_ENV: self.command("done"),
                                          install_script.INSTALL_PY_ENV: site.url}):
            self.assertEqual(install_script.attempt(Y, sleep=sleep), "other")
        self.assertEqual(sum(slept), 3.0, "looked at every second of a delay")
        self.assertFalse(self.noted.exists())
        self.assertEqual(install_script.read(Y)["outcome"], "other")

    def test_a_command_of_quoted_paths_with_spaces_runs_on_every_platform(self) -> None:
        # Windows's rehearsal named its stand-in this way and it never started: the quotes were kept in each word.
        report = self.root / "report.json"
        with mock.patch.dict(os.environ, {install_script.INSTALLER_ENV: self.command("done")}):
            self.assertEqual(install_script.run(install_script.installer(), report), 0)
        self.assertEqual(install_script.judge(report), "done")


class Defaults(unittest.TestCase):
    def test_the_hosted_script_and_the_site_unless_a_test_names_its_own(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(install_script.INSTALLER_ENV, None)
            os.environ.pop(install_script.INSTALL_PY_ENV, None)
            if os.name != "nt":
                self.assertEqual(install_script.installer(),
                                 ["sh", "-c", "curl -fsSL https://texttocad.dev/install.sh | sh"])
            self.assertEqual(install_script.install_py(), "https://www.texttocad.dev/install.py")
            os.environ[install_script.INSTALLER_ENV] = ""
            self.assertFalse(install_script.installer(), "empty: nothing")
            self.assertIsNone(install_script.install_py(), "a command a test names waits for no site")


class Site:
    """A stand-in for the docs site: ``install.py`` served from a local port, its text what ``pages`` holds next (each
    ask takes the next; the last stays), or not found while that is None."""

    def __init__(self, test: unittest.TestCase, *pages: str | None) -> None:
        import http.server

        self.pages, self.asked = list(pages), 0
        site = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - the standard library's name
                site.asked += 1
                page = site.pages.pop(0) if len(site.pages) > 1 else site.pages[0]
                if page is None:
                    self.send_error(404)
                    return
                body = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args) -> None:
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        test.addCleanup(self.server.server_close)
        test.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/install.py"


def install_py(fallback: str) -> str:
    return f'#!/usr/bin/env python3\n"""The installer."""\nFALLBACK = "{fallback}"\n'


class SiteWait(unittest.TestCase):
    """An attempt waits until the site's install.py names this release: the site is deployed after the version feed
    names it."""

    def test_it_waits_for_the_site_to_name_this_release_and_gives_up_once_its_delays_are_spent(self) -> None:
        slept: list[float] = []
        site = Site(self, None, install_py(OLD), install_py(Y))
        self.assertTrue(install_script.wait(site.url, Y, delays=(1.0, 2.0, 4.0, 8.0), sleep=slept.append))
        self.assertEqual((site.asked, sum(slept)), (3, 3.0), "not found, then the release before, then this one")
        for named, version, ready in ((Y, f"{Y}-dev.20261115000000", True), ("0.13.0", Y, True),
                                      ("0.12.0", Y, False), ("0.12", "0.12.0", True)):
            with self.subTest(named=named, version=version):
                self.assertEqual(install_script.serves(Site(self, install_py(named)).url, version), ready)
        slept.clear()
        site = Site(self, install_py(OLD))
        self.assertFalse(install_script.wait(site.url, Y, delays=(1.0, 2.0), sleep=slept.append))
        self.assertEqual((site.asked, sum(slept)), (3, 3.0), "asked at once and after each delay, then no more")
        self.assertFalse(install_script.serves("http://127.0.0.1:9/install.py", Y), "an address that does not answer")
        self.assertEqual(install_script.main([]), 0, "no version: nothing done")


class Arriving(State):
    """``arrival``: how a version arrived, kept once by setup, and its server's first serve said once."""

    def test_kept_once_and_the_first_serve_said_once(self) -> None:
        arrival.keep(Y, arrival.UPDATER, OLD, now=5.0)
        arrival.keep(Y, arrival.SETUP, None, now=6.0)  # a later setup of the same version keeps the first
        self.assertEqual({key: arrival.read(Y)[key] for key in ("route", "from", "at", "served")},
                         {"route": "updater", "from": OLD, "at": 5.0, "served": None})
        self.assertTrue(arrival.first_serve(Y, self.said.append, now=7.0))
        self.assertFalse(arrival.first_serve(Y, self.said.append, now=8.0))
        self.assertEqual(self.said, ["cad 0.12.1 serves for the first time on this computer, set up by updater from "
                                     "0.11.10"])
        self.assertEqual(arrival.read(Y)["served"], 7.0)
        self.assertFalse(arrival.first_serve(X, self.said.append), "a version setup kept nothing of: nothing said")

    def test_the_version_it_came_from(self) -> None:
        self.assertIsNone(arrival.came_from(Y), "nothing older on this computer")
        installations.point(OLD)  # the layout of 0.11.10 and earlier: its current release, installed nowhere else
        self.assertEqual(arrival.came_from(Y), OLD)
        with mock.patch("cad_server._internal.versions.present", return_value=[OLD, X, Y]):
            installations.point(X)
            self.assertEqual(arrival.came_from(Y), X, "the newest installed version older than it")
            installations.point(Y)
            self.assertEqual(arrival.came_from(Y), X)


class Counted(State):
    """Each hook counts its step (``analytics.arrival``) beside the settings of the process that ran it, as
    ``test_arrival`` shows the counting itself: a setup's failure where it failed, its ``ok`` once and in the version's
    own process, the first serving and each hand-over's end in the version's server."""

    def setUp(self) -> None:
        super().setUp()
        environment = mock.patch.dict(os.environ, test_arrival.QUIET)
        environment.start()
        self.addCleanup(environment.stop)
        spawn = mock.patch.object(telemetry_send, "_spawn", lambda settings: None)
        spawn.start()
        self.addCleanup(spawn.stop)
        self.state = places.state_dir() / "settings.json"
        self.version = places.data_dir(Y) / "settings.json"
        for settings in (self.state, self.version):
            self.settings = settings
            test_arrival.ArrivalTest.tell(self)  # the person told, sharing on, in each folder; its last sender long ago

    def kept(self, settings: Path) -> list[dict]:
        self.settings = settings
        return test_arrival.ArrivalTest.kept(self)

    def test_setup_counts_a_failure_where_it_failed_and_ok_once_in_the_version_s_own_process(self) -> None:
        arrival.setup_ended(Y, "updater", OLD, "failed", "network")
        self.assertEqual(self.kept(self.state), [{"step": "setup", "route": "updater", "from": OLD, "outcome": "failed",
                                                  "reason": "network"}], "a process of no version: the state folder's")
        arrival.setup_ended(Y, "setup", OLD, "ok")  # not the run that kept its arrival: counted by that one
        with mock.patch.object(places, "versioned", return_value=Y):
            arrival.setup_ended(Y, "updater", OLD, "ok", first=True)
        self.assertEqual(self.kept(self.version), [{"step": "setup", "route": "updater", "from": OLD, "outcome": "ok"}])
        self.assertEqual(len(self.kept(self.state)), 1)
        # A plain setup runs in uvx's process: the version's own Python counts it, with what COUNT runs.
        marker = places.code_dir(Y) / places.VERSION_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"schema": places.VERSION_SCHEMA, "version": Y, "python": sys.executable,
                                      "cad": sys.executable, "prefix": sys.prefix}), encoding="utf-8")
        with mock.patch.object(arrival.subprocess, "run") as ran:
            arrival.setup_ended(Y, "setup", None, "ok", first=True)
        [call] = ran.call_args_list
        self.assertEqual(call.args[0], [sys.executable, "-P", "-c", arrival.COUNT, "setup", ""])
        self.assertEqual(call.kwargs["env"][places.INSTALLATION_ENV], Y)
        with mock.patch.object(places, "versioned", return_value=Y), mock.patch.object(sys, "argv", call.args[0][3:]):
            exec(compile(arrival.COUNT, "<count>", "exec"), {})
        self.assertEqual(self.kept(self.version)[-1], {"step": "setup", "route": "setup", "from": "none", "outcome": "ok"})

    def test_the_first_serve_and_each_hand_over_s_end_are_counted_by_the_version_s_server(self) -> None:
        arrival.keep(Y, "updater", OLD)
        install_script.owe(Y)
        with mock.patch.object(places, "versioned", return_value=Y):
            self.assertTrue(arrival.first_serve(Y, self.said.append))
            install_script.ended(Y, "failed", 1, self.said.append, why="app")
            install_script.ended(Y, "done", 2, self.said.append)
            install_script.ended(X, "gave_up", 30, self.said.append)  # no arrival kept: from none
        self.assertEqual(self.kept(self.version), [
            {"step": "serving", "route": "updater", "from": OLD, "outcome": "ok"},
            {"step": "handover", "route": "updater", "from": OLD, "outcome": "failed", "reason": "app", "attempts": 1},
            {"step": "handover", "route": "updater", "from": OLD, "outcome": "done", "attempts": 2},
            {"step": "handover", "route": "updater", "from": "none", "outcome": "gave_up", "attempts": 30},
        ])
        self.assertEqual(self.kept(self.state), [], "nothing in a folder of another process's")


if __name__ == "__main__":
    unittest.main()
