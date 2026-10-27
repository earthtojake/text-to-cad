"""The Python test runner (``scripts/test/unittest_files.py``): each file in an interpreter of its
own, with an engine directory of its own, and a daemon the file left there stopped after it; a test
that writes where the developer's own cadgen keeps its state fails the run, by name."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
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
    leaves a daemon's door in its engine directory when ``leaves_a_daemon``; a stop is recorded."""
    def run(argv, *, env, **kwargs):
        calls.append((list(argv), dict(env)))
        stopping = argv[1:3] == ["-P", "-c"]
        if not stopping:
            if leaves_a_daemon:
                Path(env["CADGEN_ENGINE_DIR"]).mkdir(parents=True, exist_ok=True)
                Path(env["CADGEN_ENGINE_DIR"], "0123456789ab.door").write_text("", encoding="utf-8")
            if child_error is not None:
                raise child_error
        return subprocess.CompletedProcess(argv, 0, "", "")

    return run


class PythonTestRunnerIsolation(unittest.TestCase):
    def setUp(self) -> None:
        # Where nothing names an engine's folder, and the developer's own state (the guards below):
        # none, for the stand-ins here.
        for name, value in (("default_engine_door", None), ("person_places", ([], [], ""))):
            patched = mock.patch.object(runner, name, return_value=value)
            patched.start()
            self.addCleanup(patched.stop)

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
        # Never the developer's 0.7 store, registry of documents, installations or ``cadgen`` command.
        for name in ("CADGEN_CACHE_DIR", "CADGEN_STATE_DIR", "CADGEN_LAUNCHER_DIR"):
            folders = [env[name] for _argv, env in calls]
            self.assertEqual([Path(folder).parent for folder in folders], [Path(engine).parent for engine in engines])
            self.assertNotEqual(folders[0], folders[1])

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


class DefaultEngineGuard(unittest.TestCase):
    """A test never leaves an engine where nothing names its folder (the developer's engine's
    place): one found as a file ends is stopped, and fails the run naming the files running."""

    def run_with(self, answering: list[bool]) -> tuple[int, str, list]:
        stopped: list = []
        door = "/default/cadgen-engine/0123456789ab.door"
        ran = lambda path, top, verbose, env, places: (path, 0, "Ran 1 test in 0.001s\n\nOK\n", 0.0)  # noqa: E731
        said = io.StringIO()
        with mock.patch.object(runner, "default_engine_door", return_value=door), \
                mock.patch.object(runner, "person_places", return_value=([], [], "")), \
                mock.patch.object(runner, "engine_answers", side_effect=answering), \
                mock.patch.object(runner, "_run_one_file", side_effect=ran), \
                mock.patch.object(runner, "_engine_python", side_effect=lambda top, code, **env: stopped.append((code, env))), \
                mock.patch.object(runner.sys, "stderr", said):
            code = runner.run_files(["leaves.py"], str(REPO_ROOT), 1, False)
        return code, said.getvalue(), stopped

    def test_an_engine_a_file_left_in_the_default_folder_is_stopped_and_fails_the_run(self):
        code, said, stopped = self.run_with([False, True])  # none before the run, one after the file
        self.assertEqual(code, 1)
        self.assertIn("/default/cadgen-engine/0123456789ab.door, after leaves.py", said)
        self.assertEqual(stopped, [("from cadgen.engine import api; api.stop()", {"CADGEN_ENGINE_DIR": "/default/cadgen-engine"})])

    def test_the_developer_s_own_engine_running_there_before_the_run_is_left_alone(self):
        code, said, stopped = self.run_with([True])
        self.assertEqual((code, stopped), (0, []))


class PersonStateGuard(unittest.TestCase):
    """A test never writes where the developer's own cadgen keeps its state: what appears there
    during the run fails it, named with the test running then, else with the file that just ended."""

    def test_a_document_a_test_registers_in_the_developer_s_state_fails_the_run_by_the_test_s_name(self):
        with tempfile.TemporaryDirectory() as scratch:
            top = os.path.realpath(scratch)
            person = Path(top, "person-state")
            leaks = Path(top, "test_leaks_fixture.py")
            leaks.write_text(
                "import os, pathlib, unittest\n\n\n"
                "class Leaks(unittest.TestCase):\n"
                "    def test_keeps_to_its_own_state(self):\n"
                "        pathlib.Path(os.environ['CADGEN_STATE_DIR'], 'documents', 'mine').mkdir(parents=True)\n\n"
                "    def test_registers_a_document_in_the_developer_s(self):\n"
                f"        pathlib.Path({str(person)!r}, 'documents', '0123abcd').mkdir(parents=True)\n",
                encoding="utf-8",
            )
            report = io.StringIO()
            with contextlib.chdir(top), mock.patch.object(runner, "default_engine_door", return_value=None), \
                    mock.patch.object(runner, "person_places", return_value=([str(person)], [], "0123456789ab")), \
                    mock.patch.object(runner.sys, "stderr", report):
                code = runner.run_files([str(leaks)], top, 1, False)
        self.assertEqual(code, 1)
        said = report.getvalue()
        self.assertIn(f"  {person / 'documents' / '0123abcd'}, while "
                      f"test_leaks_fixture.Leaks.test_registers_a_document_in_the_developer_s ({leaks}) ran\n", said)
        self.assertNotIn("mine", said, "a test's own state folder is its own")

    def test_an_installation_or_the_command_written_after_a_file_fails_the_run_naming_the_file(self):
        with tempfile.TemporaryDirectory() as scratch:
            person, command = Path(scratch, "state"), Path(scratch, "bin", "cadgen")
            Path(person, "documents", "before").mkdir(parents=True)  # the developer's own, from before the run
            command.parent.mkdir()
            command.write_text("#!/bin/sh\n", encoding="utf-8")
            writes: list = []

            def ran(path, top, verbose, env, places):  # what a process the file left writes as it ends
                for write in writes:
                    write()
                return path, 0, "Ran 1 test in 0.001s\n\nOK\n", 0.0

            def run() -> tuple[int, str]:
                said = io.StringIO()
                with mock.patch.object(runner, "default_engine_door", return_value=None), \
                        mock.patch.object(runner, "person_places",
                                          return_value=([str(person)], [str(command)], "0123456789ab")), \
                        mock.patch.object(runner, "_run_one_file", side_effect=ran), \
                        mock.patch.object(runner.sys, "stderr", said):
                    return runner.run_files(["leaves.py"], str(REPO_ROOT), 1, False), said.getvalue()

            self.assertEqual(run()[0], 0, "nothing appeared")
            writes += [lambda: Path(person, "installations").mkdir(),
                       lambda: Path(person, "installations", "9.9.9.json").write_text("{}", encoding="utf-8"),
                       lambda: command.write_text("#!/bin/sh\nexec cadgen\n", encoding="utf-8")]
            code, said = run()
        self.assertEqual(code, 1)
        self.assertIn(f"  {person / 'installations' / '9.9.9.json'}, after leaves.py (running beside it: none)\n", said)
        self.assertIn(f"  {command}, after leaves.py (running beside it: none)\n", said)
        self.assertNotIn("before", said)

    def test_what_another_cadgen_wrote_meanwhile_is_said_and_only_this_run_s_fails_it(self):
        # A development install the developer made during the run registered itself, and its engine
        # its port: their records name another environment. One this run's engine wrote is the run's.
        elsewhere = os.path.abspath("/opt/another-cadgen")
        records = {"installations/0.9.0-dev.1.json": {"prefix": elsewhere, "python": f"{elsewhere}/bin/python"},
                   "engines/fedcba987654.json": {"port": 3249}, "documents/00ab/document.json": {"root": elsewhere},
                   "engines/0123456789ab.json": {"port": 3249}}
        with tempfile.TemporaryDirectory() as scratch:
            person = Path(scratch, "state")

            def ran(path, top, verbose, env, places):
                for inside, record in records.items():
                    Path(person, inside).parent.mkdir(parents=True, exist_ok=True)
                    Path(person, inside).write_text(json.dumps(record), encoding="utf-8")
                return path, 0, "Ran 1 test in 0.001s\n\nOK\n", 0.0

            said = io.StringIO()
            with mock.patch.dict(os.environ, {"CI": ""}), \
                    mock.patch.object(runner, "default_engine_door", return_value=None), \
                    mock.patch.object(runner, "person_places", return_value=([str(person)], [], "0123456789ab")), \
                    mock.patch.object(runner, "_run_one_file", side_effect=ran), \
                    mock.patch.object(runner.sys, "stderr", said):
                code = runner.run_files(["leaves.py"], str(REPO_ROOT), 1, False)
        tests_wrote, _, meanwhile = said.getvalue().partition("another cadgen wrote")
        self.assertEqual(code, 1)
        self.assertIn(str(person / "engines" / "0123456789ab.json"), tests_wrote)
        for inside in ("installations/0.9.0-dev.1.json", "engines/fedcba987654.json", "documents/00ab"):
            self.assertIn(f"  {person.joinpath(*inside.split('/'))}\n", meanwhile)
            self.assertNotIn(str(person.joinpath(*inside.split("/"))), tests_wrote)


class WindowsProcessExit(unittest.TestCase):
    """An unreadable process is not an exited one; only the native signal permits cleanup."""

    def native(self):
        from types import SimpleNamespace
        from tests.python.support import engine_daemon

        api = mock.Mock(WAIT_OBJECT_0=0, WAIT_TIMEOUT=258)
        api.OpenProcess.return_value = 0x100000001  # a HANDLE must not be narrowed to ctypes' default int
        module = mock.patch.dict("sys.modules", {"_winapi": api})
        platform = mock.patch.object(engine_daemon, "os", SimpleNamespace(name="nt"))
        module.start()
        platform.start()
        self.addCleanup(module.stop)
        self.addCleanup(platform.stop)
        return engine_daemon, api

    def test_cleanup_waits_for_the_native_signal_and_a_timeout_is_not_exit(self):
        helper, api = self.native()
        for result, expected in ((api.WAIT_TIMEOUT, False), (api.WAIT_OBJECT_0, True)):
            with self.subTest(result=result):
                api.WaitForSingleObject.return_value = result
                self.assertIs(helper.await_exit(123, within=0.25), expected)
                api.WaitForSingleObject.assert_called_with(0x100000001, 250)
                api.CloseHandle.assert_called_with(0x100000001)
                self.assertIs(helper._alive(123), not expected)
                api.WaitForSingleObject.assert_called_with(0x100000001, 0)

    def test_only_a_missing_pid_means_already_exited_and_other_errors_are_said(self):
        helper, api = self.native()
        for code in (87, 5):  # ERROR_INVALID_PARAMETER (gone), ERROR_ACCESS_DENIED (not observed)
            error = OSError("cannot open process")
            error.winerror = code
            api.OpenProcess.side_effect = error
            with self.subTest(code=code):
                if code == 87:
                    self.assertTrue(helper.await_exit(123))
                else:
                    with self.assertRaisesRegex(OSError, "cannot open process"):
                        helper.await_exit(123)
                    with self.assertRaisesRegex(OSError, "cannot open process"):
                        helper._alive(123)
        api.WaitForSingleObject.assert_not_called()
        api.CloseHandle.assert_not_called()

    def test_a_failed_wait_is_said_and_its_handle_is_closed(self):
        helper, api = self.native()
        api.WaitForSingleObject.side_effect = OSError("native wait failed")
        with self.assertRaisesRegex(OSError, "native wait failed"):
            helper.await_exit(123)
        api.CloseHandle.assert_called_once_with(0x100000001)


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

    def test_a_failed_command_prints_the_stacks_of_the_processes_that_died(self):
        # A worker that died in native code wrote its stack to the journal, which goes with the test:
        # the failed command's output carries it now. One that fails on its own says nothing more.
        import sys

        from tests.python.support import engine_daemon

        stub = ("import os, sys\n"
                "path = os.path.join(os.environ['CADGEN_TEST_JOURNAL'], f'process-{os.getpid()}.stacks.txt')\n"
                "with open(path, 'a', encoding='utf-8') as handle:\n"
                "    handle.write('Fatal Python error: Segmentation fault\\n  File \"stub.py\", line 7 in load\\n')\n"
                "sys.exit(1)\n")
        cleanups: list = []
        env = engine_daemon.watched(dict(os.environ), lambda *call: cleanups.append(call))
        try:
            for script, said in ((stub, True), ("import sys; sys.exit(2)", False)):
                with self.subTest(said=said), mock.patch.object(sys, "stderr", io.StringIO()) as err:
                    done = engine_daemon.run([sys.executable, "-c", script], env=env)
                    self.assertNotEqual(done.returncode, 0)
                    printed = err.getvalue()
                    if said:
                        self.assertIn("engine journal stacks after a failed command", printed)
                        self.assertRegex(printed, r"--- process \d+ \(gone\): its stacks")
                        self.assertIn('File "stub.py", line 7 in load', printed)
                    else:
                        self.assertNotIn("engine journal stacks", printed, "a refusal leaves no stacks to say")
                for path in Path(env[engine_daemon.JOURNAL]).glob("*.stacks.txt"):
                    path.unlink()
        finally:
            for function, *args in cleanups:
                function(*args)

    def test_the_journal_names_the_distribution_s_daemon_a_daemon(self):
        import sys

        from tests.python.support import engine_daemon

        cleanups: list = []
        env = engine_daemon.watched(dict(os.environ), lambda *call: cleanups.append(call))
        try:
            # Its argv names the module as the distribution starts it; it imports nothing of it.
            done = engine_daemon.run([sys.executable, "-c", "import sys", "cadgen._internal.engine_daemon"], env=env)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual([role for role, _pid in engine_daemon._processes(env)], ["daemon"])
        finally:
            for function, *args in cleanups:
                function(*args)

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
                    mock.patch.object(runner, "person_places", return_value=([], [], "")), \
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


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
