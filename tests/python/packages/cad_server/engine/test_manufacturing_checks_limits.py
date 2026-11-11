"""Where the engine measures no manufacturing check, and a check that does not complete. A library of
another release than the engine's, or of other code or measuring libraries, is answered at once with
nothing measured, and measures a file itself and a model as before (exported, read back), as one that
reaches no engine does a file, saying so. A check that does not complete says why in one word
(``api.EngineError.reason``): its process lost, over a check's limits, the engine stopped; a request that
is no check is refused in one line. And the pool of checks processes, and what a checks process holds of
what it read. On an engine, a state and a cache folder of this file's own."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

from tests.python.support import engine_daemon
from tests.python.support.manufacturing_fixtures import (DECLARED, JOIN_SECONDS, Checking, Fixture, _counts, _plain,
                                                         _today, _until, box, held_check, held_engine)


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup)


class ReleaseTest(unittest.TestCase):
    """A library of another release than the engine's is answered at once with nothing measured, and measures a
    file itself and a model as before (exported, read back), as one that reaches no engine does a file, saying
    so; the pool of checks processes; and what a checks process holds of what it read."""

    def test_another_releases_check_is_answered_at_once_and_measures_nothing(self) -> None:
        import build123d as bd

        import cad
        from cad.engine import api

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-other-"))
        self.addCleanup(shutil.rmtree, folder, True)
        step = folder / "box.step"
        bd.export_step(bd.Box(20, 20, 15), str(step))
        cad.step.dfm(step, process="cnc")
        before = _counts()
        check = {"type": "step", "process": "cnc", "candidates": False,
                 "resolved": cad._internal.manufacturing.options("step", "cnc", {}), "token": "t"}
        done = api._ask({"op": "export", "source": {"path": str(step)}, "destinations": [], "caller": "0.0.1",
                         "check": check})["done"]
        self.assertNotIn("checked", done)
        self.assertEqual(_counts()["measured"], before["measured"])

    def test_an_engine_that_stops_mid_check_says_to_check_again_and_measures_nothing_here(self) -> None:
        import build123d as bd

        import cad
        from cad.build123d import _dfm_check
        from cad.engine import api, client

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-stop-"))
        self.addCleanup(shutil.rmtree, folder, True)
        step = folder / "box.step"
        bd.export_step(bd.Box(20, 20, 15), str(step))
        with mock.patch.object(client, "connect", return_value=object()), \
                mock.patch.object(api, "_ask", side_effect=ConnectionError("the engine server closed the connection")), \
                mock.patch.object(_dfm_check, "measure", side_effect=AssertionError("measured here")):
            with self.assertRaises(api.Stopped) as stopped:
                cad.step.dfm(step, process="printing")
        self.assertIn("run the check again", str(stopped.exception))

    def test_the_pool_runs_a_check_per_slot_and_one_past_it_waits_saying_so(self) -> None:
        from cad_server.engine.checks import Pool, Withdrawn

        live: list[Any] = []
        room = {"cap": None}
        supervisor = SimpleNamespace(processes=lambda _service: list(live), pressed=lambda: False,
                                     memory=lambda: room["cap"], resident=lambda: 900.0)
        pool = Pool(supervisor, 2)
        self.assertEqual((pool.take("file:a"), pool.take("file:b")), ("checks", "checks-2"))
        said: list[str] = []
        third = Checking(lambda: pool.take("file:c", waiting=said.append))
        third.start()
        _until(self, lambda: said, "the third says it waits")
        self.assertIn("waiting for another manufacturing check", said[0])
        self.assertIn("the 2 checks processes are all busy", said[0])
        self.assertTrue(third.is_alive())
        pool.give("checks")
        self.assertEqual(third.result(self), "checks")
        self.assertEqual(len(said), 1, "said once")
        pool.give("checks")
        pool.give("checks-2")
        live.extend(SimpleNamespace(key=key, pid=1, rss=400.0, retired=False, alive=lambda: True)
                    for key in ("checks", "checks-2"))
        self.assertEqual(pool.take("file:b"), "checks-2", "the slot that last read it")
        pool.give("checks-2")
        del live[1]
        room["cap"] = 1000.0  # no room for another of 400 MB beside 900
        self.assertEqual(pool.take("file:a"), "checks")
        before = len(said)
        with self.assertRaises(Withdrawn):  # given up once it has said what it waits for
            pool.take("file:b", gave_up=lambda: len(said) > before, waiting=said.append)
        self.assertIn("the engine's memory has no room for another checks process", said[-1])

    def test_a_waiter_the_memory_has_no_room_for_reaps_as_one_past_a_full_pool_does(self) -> None:
        """A slot free but no room for another checks process: the waiter asks its ``reap`` as it waits, as it
        does with every slot busy; a waiter deferring to another asks nothing."""
        from cad_server.engine.checks import Pool, Withdrawn

        pool = Pool(SimpleNamespace(processes=lambda _service: [], pressed=lambda: False, memory=lambda: 1000.0,
                                    resident=lambda: 900.0, standby=lambda _service: SimpleNamespace(rss=400.0)), 2)
        self.assertEqual(pool.take("file:a"), "checks")
        reaped: list[str] = []
        with self.assertRaises(Withdrawn):
            pool.take("file:b", gave_up=lambda: bool(reaped), reap=lambda: reaped.append("b"))
        self.assertEqual(reaped, ["b"], "no room beside the one measuring: an abandoned one's process is wanted")
        reaped.clear()
        with self.assertRaises(Withdrawn):
            calls = iter((False, True))
            pool.take("file:c", gave_up=lambda: next(calls), reap=lambda: reaped.append("c"), defer=lambda: True)
        self.assertEqual(reaped, [], "deferring, it reaps nothing")

    def test_the_pool_counts_a_process_it_has_not_heard_from_and_those_starting(self) -> None:
        """No checks process has said its memory: the last one's, else the standby's, else the smallest worker's
        stands for it, and each slot being started counts, so a burst of checks never starts past the cap."""
        from cad_server.engine.checks import Pool, Withdrawn

        live: list[Any] = []
        workers: list[Any] = []
        spare = {"rss": None}
        supervisor = SimpleNamespace(processes=lambda service: list(live if service == "checks" else workers),
                                     pressed=lambda: False, memory=lambda: 1000.0, resident=lambda: 500.0,
                                     standby=lambda _service: SimpleNamespace(rss=spare["rss"]))
        pool = Pool(supervisor, 3)
        self.assertEqual(pool.size_of({}), 0.0, "nothing said: no floor")
        workers.append(SimpleNamespace(rss=300.0, alive=lambda: True, retired=False))
        self.assertEqual(pool.size_of({}), 300.0, "the smallest worker's")
        spare["rss"] = 200.0
        self.assertEqual(pool.size_of({}), 200.0, "the standby's: a kernel loaded, nothing built")
        self.assertEqual(pool.take("file:a"), "checks", "one of 200 MB beside 500")
        self.assertEqual(pool.take("file:b"), "checks-2", "two being started, 900 of 1000")
        said: list[str] = []
        with self.assertRaises(Withdrawn):  # a third would be 1100: it waits, and gives up once it has said so
            pool.take("file:c", gave_up=lambda: bool(said), waiting=said.append)
        self.assertIn("no room for another checks process", said[0])
        live.append(SimpleNamespace(key="checks", pid=1, rss=450.0, retired=False, alive=lambda: True))
        pool.size_of({"checks": live[0]})
        live.clear()
        self.assertEqual(pool.size_of({}), 450.0, "the last one's, after it is gone")

    def test_the_pool_is_half_the_cores_and_its_setting_held_to_them(self) -> None:
        from cad_server.engine import checks

        for cores, given, size, said in ((16, "", 4, False), (2, "", 1, False), (1, "", 1, False), (8, "3", 3, False),
                                         (8, "0", 1, True), (8, "64", 8, True), (8, "many", 4, True)):
            with self.subTest(cores=cores, given=given), mock.patch.object(os, "cpu_count", return_value=cores), \
                    mock.patch.dict(os.environ, {"CAD_ENGINE_CHECKS": given}):
                found, line = checks.pool_size()
                self.assertEqual((found, line is not None), (size, said))

    def test_a_file_is_one_key_by_any_of_its_names(self) -> None:
        from cad_server.engine.checks_runner import file_key as _file_key
        from cad_server.engine.models import durable, revision

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-names-"))
        self.addCleanup(shutil.rmtree, folder, True)
        first = folder / "Part.step"
        first.write_bytes(b"x")
        other = folder / "link.step"
        os.link(first, other)
        self.assertEqual(_file_key(str(first)), _file_key(str(other)), "a hard link")
        if (folder / "part.step").exists():  # a file system that folds case: the other spelling is the file
            self.assertEqual(_file_key(str(folder / "part.step")), _file_key(str(first)))
        self.assertNotEqual(_file_key(str(first)), _file_key(str(folder / "elsewhere.step")))
        self.assertTrue(durable(revision({"closure": {"key": "ab12"}})))
        self.assertFalse(durable(revision({})) or durable(None) or durable(""))

    def test_what_a_checks_process_read_is_bounded_by_bytes_and_shed_over_the_cap(self) -> None:
        from cad.engine import contract, worker

        memo = {name: (name, None, size) for name, size in (("a", 10), ("b", worker.KEPT_BYTES - 5), ("c", 10))}
        worker._bounded(memo, 4, lambda row: row[2])
        self.assertEqual(list(memo), ["c"], "held to its bytes, the least recently used going first")
        worker._FILES["x"] = ("d", None, 1)
        worker._DOCUMENTS["y"] = ("v", None, 1)
        with mock.patch.object(worker, "resident_mb", return_value=5000.0):
            worker.resident_after_check(1000.0)
        self.assertEqual((worker._FILES, worker._DOCUMENTS), ({}, {}), "dropped where the process is over its cap")
        # A caller of other code is measured nothing, before anything is read; and a file rewritten while it was
        # read is measured nothing either, and says so.
        check = {"type": "step", "process": "cnc", "resolved": {}, "token": "t", "measures": contract.measuring()}
        unlike = {**check, "measures": {**contract.measuring(), "code": "other"}}
        self.assertNotIn("checked", worker._check({"source": {"path": "/nowhere/part.step"}, "check": unlike}))
        with mock.patch.object(worker, "_file", return_value=(object(), None, True)):
            torn = worker._check({"source": {"path": "/nowhere/part.step"}, "check": check})["checked"]
        self.assertEqual((torn["changed"], "measured" in torn), (True, False))

    def test_status_says_each_check_running_and_whether_its_caller_waits(self) -> None:
        from cad_server.engine.cli import status_text

        text = status_text({"pid": 1, "workers": [], "cap": 4, "checks": {"running": [
            {"type": "step", "process": "printing", "file": "/p/box.step", "state": "measuring", "where": "checks-2",
             "seconds": 21.0, "attached": False, "waiting": False},
            {"type": "model", "process": "cnc", "document": "abc", "state": "waiting", "where": None,
             "seconds": 3.0, "attached": True, "waiting": True}]}})
        self.assertIn("check    printing of box.step in checks-2 · 21s · its caller gone", text)
        self.assertIn("check    cnc of abc waiting for its process · 3s", text)

    def test_an_engine_without_checks_or_of_another_release_is_measured_here(self) -> None:
        import build123d as bd

        import cad
        from cad.engine import api

        folder = Path(tempfile.mkdtemp(prefix="engine-dfm-old-"))
        self.addCleanup(shutil.rmtree, folder, True)
        step = folder / "box.step"
        bd.export_step(bd.Box(20, 20, 15), str(step))
        expected = _plain(_today("step", step, step.resolve(), "printing"))
        for answer in (api.Unanswered("old"), {"measured": {}, "release": "0.10.0"},
                       api.Unreached("no engine here")):
            with self.subTest(answer=answer), mock.patch.object(
                    api, "check", side_effect=answer if isinstance(answer, Exception) else None,
                    return_value=None if isinstance(answer, Exception) else answer):
                self.assertEqual(_plain(cad.step.dfm(step, process="printing")), expected)
        fixture = Fixture(self, DECLARED)
        (block,) = fixture.ids
        with mock.patch.object(api, "check", side_effect=api.Unanswered("old")):
            exported = cad.model.dfm(block, process="cnc")
        held = cad.model.dfm(block, process="cnc")
        self.assertEqual(_plain(exported), _plain(held), "exported and read back, as before")

    def test_a_file_checked_with_no_engine_to_reach_is_measured_here_and_one_line_says_so(self) -> None:
        """No engine can be reached or started (a sandbox, no installation): a file's check is measured in the
        calling process, and one line on stderr says why and that nothing keeps it, so it is measured again each
        time; the failure itself carries its reason."""
        from contextlib import redirect_stderr
        from io import StringIO

        import cad
        from cad.engine import api, client

        (step,) = box(self, 6)
        expected = _plain(_today("step", step, step.resolve(), "printing"))
        check = {"type": "step", "process": "printing", "candidates": False,
                 "resolved": cad._internal.manufacturing.options("step", "printing", {})}
        said = StringIO()
        with mock.patch.object(client, "connect", side_effect=ConnectionError("cad-server is not installed here")), \
                redirect_stderr(said):
            self.assertEqual(_plain(cad.step.dfm(step, process="printing")), expected)
            with self.assertRaises(api.Unreached) as unreached:
                api.check(step, check)
        self.assertEqual(unreached.exception.reason, "unreachable")
        lines = [line for line in said.getvalue().splitlines() if line.startswith("cad: ")]
        self.assertEqual(len(lines), 2, "one line a check")
        self.assertIn("no CAD server could be reached (cad-server is not installed here)", lines[0])
        self.assertIn("measured again each time", lines[0])
        self.assertEqual(api.check(step, check)["measured_in"], api.IN_ENGINE)


class EngineLimitsTest(unittest.TestCase):
    """A check on a running engine that does not complete, or is no check of the engine's: its checks process
    killed, the engine stopping, a check's limits, a caller of other code, a request that is no check. A check
    waits at the test's seam (``held_engine``) until the test lets it go."""

    def test_an_update_s_drain_waits_for_no_check_and_its_checks_say_stopped(self) -> None:
        """A drain for an update with a check measuring and another waiting for its process: neither is waited
        for, and both callers are told the engine stopped (``api.Stopped``: run the check again)."""
        from cad.engine import client

        env, hold = held_engine(self, {"CAD_ENGINE_CHECKS": "1"})
        reached = Path(f"{hold}.reached")
        callers = []
        for step in box(self, 6, 7):
            code = (f"import cad\nfrom cad.engine import api\ntry:\n    cad.step.dfm({str(step)!r}, process='printing')\n"
                    "except api.Stopped as error:\n    print('stopped:', error.reason, error)")
            callers.append(subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, text=True))
            self.addCleanup(callers[-1].stdout.close)
            self.addCleanup(callers[-1].wait)
            self.addCleanup(callers[-1].kill)
            if len(callers) == 1:
                _until(self, reached.exists, "the first check runs")
        _until(self, lambda: _counts()["asked"] == 2, "the second waits for the checks process")
        self.assertIsNotNone(client.request({"op": "stop", "drain": True}, start=False))
        self.assertTrue(client.wait_gone(), "the engine drained and stopped with the checks under way")
        for caller in callers:
            out = caller.communicate(timeout=JOIN_SECONDS)[0]
            self.assertIn("stopped: stopped the CAD server stopped while it measured the manufacturing check", out)
        self.assertFalse(hold.exists(), "neither check was let go")

    def test_a_caller_of_other_code_or_libraries_is_measured_by_no_process_here(self) -> None:
        """A library whose code or measuring libraries are not the engine's (a checkout's edited copy at the same
        release, a base made again with a newer build123d) is measured by no process here and served nothing the
        engine kept: it measures the file itself; the same code is served the result kept."""
        import cad
        from cad.engine import contract

        (step,) = box(self, 7)
        first = cad.step.dfm(step, process="printing")
        before = _counts()
        real = contract.measuring()
        for unlike in ({**real, "code": "edited"}, {**real, "libraries": {**real["libraries"], "build123d": "0.0.1"}}):
            with self.subTest(unlike=unlike), mock.patch.object(contract, "measuring", return_value=unlike):
                self.assertEqual(_plain(cad.step.dfm(step, process="printing")), _plain(first), "measured here")
        self.assertEqual((_counts()["measured"], _counts()["reused"]), (before["measured"], before["reused"]))
        cad.step.dfm(step, process="printing")
        self.assertEqual(_counts()["reused"], before["reused"] + 1, "the same code reuses its result")

    def test_a_checks_process_killed_in_a_check_tells_every_caller_and_the_next_check_starts_another(self) -> None:
        """Its checks process killed under it (as the system's out-of-memory killer does), the check is not run
        again: its caller and one that waited for it are both told, with what a kill by the system usually
        means, and the next check is a fresh process's."""
        import cad
        from cad.engine.api import EngineError

        _env, hold = held_engine(self)
        (step,) = box(self, 6)
        before = _counts()
        first, pid = held_check(self, hold, lambda: cad.step.dfm(step, process="printing"))
        second = Checking(lambda: cad.step.dfm(step, process="printing"))
        second.start()
        _until(self, lambda: _counts()["waited"] == before["waited"] + 1, "the second waits for the first")
        killed = hasattr(signal, "SIGKILL")
        os.kill(pid, signal.SIGKILL if killed else signal.SIGTERM)
        for thread in (first, second):
            answered = thread.result(self)
            self.assertIsInstance(answered, EngineError)
            self.assertEqual(answered.reason, "process_lost")
            self.assertIn("The check is not run again", str(answered))
            if killed:
                self.assertIn("killed by the system, usually for memory", str(answered))
        hold.write_text("", encoding="utf-8")
        self.assertEqual(cad.step.dfm(step, process="printing").measurements["process"], "printing")
        self.assertNotIn(pid, [row["pid"] for row in _counts()["pool"]["processes"]], "a fresh checks process")

    def test_a_check_over_its_memory_limit_is_stopped_and_says_so(self) -> None:
        """A check's own memory limit (1 MB, which any checks process is over), read from outside the process: the
        check is stopped where it is -- never let go here -- and its caller told why and what to do."""
        import cad
        from cad.engine.api import EngineError
        from cad_server.engine.checks_runner import resident_of

        if resident_of(os.getpid()) is None:
            self.skipTest("this system does not say a process's memory from outside it")
        _env, hold = held_engine(self, {"CAD_ENGINE_CHECK_RSS_MB": "1"})
        (step,) = box(self, 6)
        check = Checking(lambda: cad.step.dfm(step, process="printing"))
        check.start()
        answered = check.result(self)
        self.assertIsInstance(answered, EngineError)
        self.assertEqual(answered.reason, "over_memory")
        self.assertIn("over a check's memory limit of 1 MB", str(answered))
        self.assertIn("CAD_ENGINE_CHECK_RSS_MB", str(answered))
        self.assertFalse(hold.exists(), "stopped by the engine, not let go")
        # The caller is answered before the runner lets the check's entry go: the slot is awaited, not read at once.
        _until(self, lambda: (_counts()["asked"], _counts()["pool"]["busy"]) == (0, 0), "its slot is free again")

    def test_a_checks_process_over_the_memory_cap_after_a_check_is_retired(self) -> None:
        """A real cap: the checks process is over it after its check, so the next check starts another. The cap is
        the engine's, so an engine of this test's own, with no limit of a check's own under it."""
        import cad
        from cad.engine import api

        (step,) = box(self, 15)
        api.stop()
        self.addCleanup(api.stop)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_WORKER_RSS_MB": "1", "CAD_ENGINE_CHECK_RSS_MB": "0"}):
            first = cad.step.dfm(step, process="printing")
            second = cad.step.dfm(step, process="sheet")
        self.assertEqual((first.measurements["process"], second.measurements["process"]), ("printing", "sheet"))
        retired = [row for row in api.status()["retired"] if row.get("process")]
        self.assertEqual(len(retired), 2, "each retired after its check, listed as what it is")
        self.assertNotEqual(retired[0]["pid"], retired[1]["pid"])

    def test_a_request_that_is_no_check_is_refused_and_a_check_that_fails_there_answers_one_line(self) -> None:
        """What a caller that speaks the protocol by hand meets: a process the type has none of is refused in one
        line before anything is read, and a check whose measuring raises answers its type and words (reason
        ``error``), its stack never sent."""
        import cad
        from cad.engine import api
        from cad.engine.contract import measuring, release

        (step,) = box(self, 6)
        cad.step.dfm(step, process="cnc")
        order = {"op": "export", "source": {"path": str(step)}, "destinations": [], "caller": release(),
                 "measures": measuring()}
        before = _counts()["measured"]
        with self.assertRaises(ValueError) as refused:
            api._ask({**order, "check": {"type": "step", "process": "nope", "resolved": {}, "token": "t"}})
        self.assertIn("a check's process is cnc, sheet, molding or printing, not 'nope'", str(refused.exception))
        with self.assertRaises(api.EngineError) as failed:  # options no caller resolved: the measuring raises there
            api._ask({**order, "check": {"type": "step", "process": "printing", "resolved": {}, "token": "t"}})
        self.assertEqual(failed.exception.reason, "error")
        self.assertNotIn("Traceback", str(failed.exception))
        self.assertEqual(len(str(failed.exception).splitlines()), 1)
        self.assertEqual(_counts()["measured"], before, "neither is a check measured")


if __name__ == "__main__":
    unittest.main()
