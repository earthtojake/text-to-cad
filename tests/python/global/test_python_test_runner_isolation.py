"""The Python test runner (``scripts/test/unittest_files.py``): each file in an interpreter of its
own, with an engine directory of its own, and a daemon the file left there stopped after it."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path

add_repo_path("packages/cadgen/src")

spec = importlib.util.spec_from_file_location("isolated_unittest_runner", REPO_ROOT / "scripts/test/unittest_files.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def _stand_in(calls: list, *, child_error: Exception | None = None, leaves_a_daemon: bool = False):
    """subprocess.run for the runner: a file's interpreter runs (or raises ``child_error``), and
    leaves a daemon's socket in its engine directory when ``leaves_a_daemon``; a stop is recorded."""
    def run(argv, *, env, **kwargs):
        calls.append((list(argv), dict(env)))
        stopping = argv[1:3] == ["-P", "-c"]
        if not stopping:
            if leaves_a_daemon:
                Path(env["CADGEN_ENGINE_DIR"]).mkdir(parents=True, exist_ok=True)
                Path(env["CADGEN_ENGINE_DIR"], "0123456789ab.sock").write_text("", encoding="utf-8")
            if child_error is not None:
                raise child_error
        return subprocess.CompletedProcess(argv, 0, "", "")

    return run


class PythonTestRunnerIsolation(unittest.TestCase):
    def test_each_file_has_an_engine_directory_of_its_own_never_the_developers(self):
        calls = []
        with mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": "developer-engine"}), \
                mock.patch.object(runner.subprocess, "run", side_effect=_stand_in(calls)), \
                mock.patch.object(runner.sys, "stderr", io.StringIO()):
            runner.run_files(["first.py", "second.py"], str(REPO_ROOT), 2, False)
            self.assertEqual(os.environ["CADGEN_ENGINE_DIR"], "developer-engine")
        self.assertEqual(len(calls), 2, "no daemon was left, so none was stopped")
        engines = [env["CADGEN_ENGINE_DIR"] for _argv, env in calls]
        self.assertNotIn("developer-engine", engines)
        self.assertNotEqual(engines[0], engines[1])
        self.assertEqual(Path(engines[0]).parent, Path(engines[1]).parent)
        self.assertFalse(Path(engines[0]).parent.exists(), "the run's folder goes with it")
        caches = [env["CADGEN_CACHE_DIR"] for _argv, env in calls]  # never the developer's 0.7 store
        self.assertEqual([Path(cache).parent for cache in caches], [Path(engine).parent for engine in engines])
        self.assertNotEqual(caches[0], caches[1])

    def test_a_daemon_a_file_left_running_is_stopped_after_it(self):
        calls = []
        with mock.patch.object(runner.subprocess, "run", side_effect=_stand_in(calls, leaves_a_daemon=True)), \
                mock.patch.object(runner.sys, "stderr", io.StringIO()):
            runner.run_files(["leaves.py"], str(REPO_ROOT), 1, False)
        (_file_argv, file_env), (stop_argv, stop_env) = calls
        self.assertEqual(stop_argv[1:], ["-P", "-c", "from cadgen.engine import api; api.stop()"])
        self.assertEqual(stop_env["CADGEN_ENGINE_DIR"], file_env["CADGEN_ENGINE_DIR"])

    def test_a_failed_child_still_stops_its_daemon(self):
        calls = []
        stand_in = _stand_in(calls, child_error=OSError("test child could not run"), leaves_a_daemon=True)
        with mock.patch.object(runner.subprocess, "run", side_effect=stand_in), \
                mock.patch.object(runner.sys, "stderr", io.StringIO()):
            with self.assertRaisesRegex(OSError, "test child could not run"):
                runner.run_files(["failed.py"], str(REPO_ROOT), 1, False)
        (_file_argv, file_env), (stop_argv, stop_env) = calls
        self.assertIn("api.stop()", stop_argv[-1])
        self.assertEqual(stop_env["CADGEN_ENGINE_DIR"], file_env["CADGEN_ENGINE_DIR"])
        self.assertFalse(Path(file_env["CADGEN_ENGINE_DIR"]).exists())

    def test_even_one_file_at_one_job_runs_in_an_interpreter_of_its_own(self):
        ran = ("only.py", 0, "Ran 0 tests in 0.000s\n\nOK\n", 0.0)
        with mock.patch.object(runner, "_run_one_file", return_value=ran) as one, \
                mock.patch.object(runner.sys, "stderr", io.StringIO()):
            self.assertEqual(runner.main(["--top", str(REPO_ROOT), "only.py"]), 0)
        (path, top, verbose, env), _kwargs = one.call_args
        self.assertEqual((path, top, verbose), ("only.py", os.path.realpath(REPO_ROOT), False))
        self.assertIn("CADGEN_ENGINE_DIR", env)


class HangGuard(unittest.TestCase):
    def test_a_live_caller_can_prepare_its_input_before_starting_a_daemon(self):
        from tests.python.support import engine_daemon

        process = mock.Mock(stdout=io.BytesIO(b"built\n"), stderr=io.BytesIO(), returncode=0)
        process.poll.side_effect = [None, 0]
        readers = []

        def reader(*, target, args, daemon):
            thread = mock.Mock()
            thread.start.side_effect = lambda: target(*args)
            thread.is_alive.return_value = False
            readers.append(thread)
            return thread

        # Simulate a cold import taking longer than the retired 30-second startup
        # heuristic, without delaying the test. The command has not asked for a server.
        with mock.patch.object(engine_daemon.threading, "Thread", side_effect=reader), \
                mock.patch.object(engine_daemon.time, "monotonic", side_effect=[0, 35, 60]), \
                mock.patch.object(engine_daemon.time, "sleep"):
            self.assertEqual(engine_daemon.communicate(process, {}), ("built\n", ""))
        process.kill.assert_not_called()

        # The overall command timeout still bounds a caller that never finishes.
        process = mock.Mock(stdout=io.BytesIO(), stderr=io.BytesIO())
        process.poll.return_value = None
        with mock.patch.object(engine_daemon.threading, "Thread", side_effect=reader), \
                mock.patch.object(engine_daemon.time, "monotonic", side_effect=[0, 301]), \
                mock.patch.object(engine_daemon, "report", return_value="journal"):
            with self.assertRaisesRegex(AssertionError, "did not finish in 300 s"):
                engine_daemon.communicate(process, {})
        process.kill.assert_called_once()

    def test_a_hung_file_fails_by_name_with_its_stack(self):
        # A hung file once held a CI job silent for 42 minutes, until it was cancelled.
        with tempfile.TemporaryDirectory() as scratch:
            top = os.path.realpath(scratch)
            hung = Path(top, "test_hung_fixture.py")
            hung.write_text(
                "import threading, unittest\n\n\n"
                "class Hung(unittest.TestCase):\n"
                "    def test_waits_forever(self):\n"
                "        threading.Event().wait()\n",
                encoding="utf-8",
            )
            report = io.StringIO()
            with contextlib.chdir(top), mock.patch.object(runner, "FILE_HANG_SECONDS", 1), \
                    mock.patch.object(runner.sys, "stderr", report):
                code = runner.run_files([str(hung)], top, 1, False)
        self.assertEqual(code, 1)
        self.assertIn("in test_waits_forever", report.getvalue())
        self.assertIn(f"failing modules:\n  {hung}", report.getvalue())

    def test_a_windows_childs_summary_still_parses(self):
        # Read from a file, a Windows child's \r\n reaches the parser untranslated:
        # once, every module of a passing Windows run counted as one with no summary.
        with tempfile.TemporaryFile() as stream:
            stream.write(b"..\r\n" + b"-" * 70 + b"\r\nRan 2 tests in 0.010s\r\n\r\nOK (skipped=1)\r\n")
            output = runner._read_all(stream)
        self.assertTrue(runner._RAN.search(output))
        self.assertEqual(runner._counts(output)["tests"], 2)
        self.assertEqual(runner._counts(output)["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
