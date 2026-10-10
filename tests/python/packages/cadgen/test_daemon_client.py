"""What the client says when the warm worker running its job dies.

The defect this pins: a 2,700-occurrence validate ran 35 minutes on a warm worker,
the worker was killed (out of memory, most likely), and the caller saw one line --
``cadgen-daemon: worker closed the connection`` -- and exit 1. Nothing said the
worker had died, nothing named the job, nothing said how to run it where the failure
could be seen. The fix is the MESSAGE, deliberately not a silent cold retry: a
half-hour job re-running unannounced is worse than the failure it hides.

Driven through ``_run_request`` with a scripted channel, so the wording is pinned at
the one place it is composed and no daemon has to be started.
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from cadgen.daemon import client, transport  # noqa: E402
from cadgen.daemon import pool as pool_mod  # noqa: E402
from cadgen.daemon import server  # noqa: E402
from cadgen.daemon.jobs import JobLedger


class _ScriptedChannel:
    """A transport channel that answers a request with a fixed sequence of frames."""

    def __init__(self, frames: list[dict]) -> None:
        self.sent: list[dict] = []
        self._frames = [json.dumps(frame).encode("utf-8") for frame in frames]

    def send(self, raw: bytes) -> None:
        self.sent.append(json.loads(raw.decode("utf-8")))

    def recv(self, timeout):
        if not self._frames:
            return b""  # closed
        return self._frames.pop(0)

    def close(self) -> None:
        pass


PAYLOAD = {
    "tool": "step-compile",
    "prog": "cadgen step compile",
    "argv": ["tmp/noexh/noexh.step", "--force"],
    "cwd": "/work",
    "env": {},
    "token": "t",
}


class DeadWorkerMessage(unittest.TestCase):
    def _run(self, frames: list[dict]) -> tuple[object, str, str]:
        channel = _ScriptedChannel(frames)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            outcome = client._run_request(channel, PAYLOAD)
        return outcome, out.getvalue(), err.getvalue()

    def test_the_death_is_explained_and_the_exit_code_kept(self):
        outcome, out, err = self._run([
            {"stream": "stdout", "data": ""},
            {"workerDied": {"pid": 4242, "detail": "worker 4242 was killed by SIGKILL (signal 9)",
                            "exitStatus": -9}},
            {"exit": 1},
        ])
        self.assertEqual(outcome, 1)
        self.assertEqual(out, "")
        # Every clause the caller needed and did not have.
        self.assertIn("the warm worker running", err)
        self.assertIn("died mid-job", err)
        self.assertIn("killed by SIGKILL (signal 9)", err)
        self.assertIn("out of memory", err)
        self.assertIn("`cadgen step compile tmp/noexh/noexh.step --force`", err)
        self.assertIn("NOT retried", err)
        # The rerun spelling is the platform's, so ask the helper that composes it.
        # That makes this assertion only "the message carries the rerun"; the
        # exact text of BOTH spellings is pinned in ColdRerunSpelling below.
        self.assertIn(client.cold_rerun_command(PAYLOAD), err)
        self.assertNotIn("worker closed the connection", err)

    def test_a_death_the_client_runs_cold_says_so_instead_of_advising_a_cold_run(self):
        """No exit frame means the daemon itself is gone, and the ordinary
        non-strict path then runs this job cold in this process. The message
        used to say "The job was NOT retried. Run it cold ... CADGEN_DAEMON=0"
        and the run then succeeded at exit 0 — a failure notice above a success,
        with nothing to tell the reader which one had happened."""
        outcome, out, err = self._run([
            {"workerDied": {"pid": 4242, "detail": "worker 4242 was killed by SIGKILL (signal 9)",
                            "exitStatus": -9}},
        ])  # the connection closes without an exit frame: the fallback follows

        self.assertIsNone(outcome, "a closed connection still means run cold")
        self.assertEqual(out, "")
        self.assertIn("died mid-job", err)
        self.assertIn("killed by SIGKILL (signal 9)", err)
        self.assertIn("Running it cold now", err)
        self.assertNotIn("NOT retried", err)
        self.assertNotIn("CADGEN_DAEMON=0", err)

    def test_a_job_with_no_prog_is_named_by_its_tool(self):
        payload = {**PAYLOAD, "tool": "probe", "prog": None, "argv": ["a b.step"]}
        text = client.worker_died_message(payload, {"detail": "worker 1 exited with code 139"})
        self.assertIn("`cadgen probe a b.step`", text)
        self.assertIn("exited with code 139", text)
        if sys.platform != "win32":
            # The rerun quotes what the shell needs quoted.
            self.assertIn("CADGEN_DAEMON=0 cadgen probe 'a b.step'", text)

    def test_a_model_script_run_is_named_and_rerun_as_python(self):
        # The decorator's warm handoff: prog `python <name>`, argv `[<path>, *args]`.
        payload = {"tool": "run", "prog": "python box.py", "argv": ["/work/src/box.py", "--force"]}
        text = client.worker_died_message(payload, {"detail": "worker 3 was killed by SIGKILL (signal 9)"})
        self.assertIn("`python box.py --force` died mid-job", text)
        self.assertNotIn("box.py /work/src/box.py", text)
        if sys.platform != "win32":
            self.assertIn("CADGEN_DAEMON=0 python /work/src/box.py --force", text)

    def test_an_ordinary_stderr_frame_is_still_just_relayed(self):
        outcome, _out, err = self._run([{"stream": "stderr", "data": "hello\n"}, {"exit": 0}])
        self.assertEqual(outcome, 0)
        self.assertEqual(err, "hello\n")


class ResidentProcessLifecycle(unittest.TestCase):
    def test_the_daemon_starts_outside_the_callers_project_directory(self):
        spawned = mock.Mock(pid=1234)
        with tempfile.TemporaryDirectory(prefix="cadgen-daemon-launch-") as tmp, \
                mock.patch.object(client.transport, "ensure_authkey") as ensure, \
                mock.patch.object(client, "daemon_identity", return_value="test"), \
                mock.patch.object(client, "log_path", return_value=pathlib.Path(tmp) / "daemon.log"), \
                mock.patch.object(client.subprocess, "Popen", return_value=spawned) as popen:
            # worker_env is imported inside the function, so patch its source.
            from cadgen.daemon import executors

            with mock.patch.object(executors, "worker_env", return_value={}):
                self.assertIs(client._spawn_daemon("test-address"), spawned)

        self.assertEqual(popen.call_args.kwargs["cwd"], tempfile.gettempdir())
        ensure.assert_not_called()

    def test_the_daemon_takes_no_telemetry_switch_or_channel_from_the_client_that_started_it(self):
        # It serves every client; each client's switch travels with its own builds instead, and the channel it
        # reports is the one its installation's plugin wrote down (`cadgen/_internal/channel.py`).
        spawned = mock.Mock(pid=1234)
        started_from = {"PATH": "/bin", "DO_NOT_TRACK": "1", "CADGEN_TELEMETRY": "0",
                        "CADGEN_INSTALL_CHANNEL": "claude-github"}
        with tempfile.TemporaryDirectory(prefix="cadgen-daemon-launch-") as tmp, \
                mock.patch.object(client.transport, "ensure_authkey"), \
                mock.patch.object(client, "daemon_identity", return_value="test"), \
                mock.patch.object(client, "log_path", return_value=pathlib.Path(tmp) / "daemon.log"), \
                mock.patch.object(client.subprocess, "Popen", return_value=spawned) as popen:
            from cadgen.daemon import executors

            with mock.patch.object(executors, "worker_env", return_value=started_from):
                self.assertIs(client._spawn_daemon("test-address"), spawned)

        env = popen.call_args.kwargs["env"]
        self.assertEqual(env["PATH"], "/bin")
        for name in ("DO_NOT_TRACK", "CADGEN_TELEMETRY", "CADGEN_INSTALL_CHANNEL"):
            self.assertNotIn(name, env)

    def test_replaced_key_is_retried_only_after_the_live_owner_republishes(self):
        channel = mock.Mock()
        with mock.patch.object(client.transport, "read_authkey", side_effect=[b"stale", b"owned"]), \
                mock.patch.object(
                    client.transport,
                    "connect",
                    side_effect=[transport.AuthenticationError("rejected"), channel],
                ) as connect:
            self.assertIs(client._connect("private-address"), channel)
        self.assertEqual(
            connect.call_args_list,
            [mock.call("private-address", b"stale"), mock.call("private-address", b"owned")],
        )

    def test_an_idle_spare_starts_outside_the_daemons_project_directory(self):
        with io.StringIO('{"ready": 1234}\n') as stdout:
            process = mock.Mock(stdout=stdout)
            with mock.patch.object(pool_mod.subprocess, "Popen", return_value=process) as popen, \
                    mock.patch.object(client, "daemon_address", return_value="test-address"):
                worker = pool_mod.Worker()
                worker._reader.join(timeout=1)
                self.assertFalse(worker._reader.is_alive())
        self.assertEqual(worker.pid, 1234)
        self.assertEqual(popen.call_args.kwargs["cwd"], tempfile.gettempdir())

    def test_prewarm_starts_nothing_when_the_daemon_is_off(self):
        # The viewer warms the daemon at every launch. CADGEN_DAEMON=0 must mean none
        # starts: the launcher tests rely on it to keep dozens of launches daemon-free.
        with mock.patch.dict("os.environ", {"CADGEN_DAEMON": "0"}), \
                mock.patch.object(client, "_connect_or_spawn", side_effect=AssertionError("a daemon was started")):
            self.assertFalse(client.prewarm())

    def test_prewarm_replaces_a_daemon_left_by_older_code(self):
        stale, current = _ScriptedChannel([{"restart": True}]), _ScriptedChannel([{"status": {}}])
        with mock.patch.dict("os.environ", {"CADGEN_DAEMON": "1"}), \
                mock.patch.object(client, "daemon_supported", return_value=True), \
                mock.patch.object(client, "daemon_address", return_value="test-address"), \
                mock.patch.object(client, "_connect_or_spawn", side_effect=[stale, current]) as connect:
            import os

            os.environ.pop("CADGEN_DAEMON_CHILD", None)
            self.assertTrue(client.prewarm())
        self.assertEqual(connect.call_count, 2)
        self.assertEqual([frame["kind"] for frame in stale.sent + current.sent], ["status", "status"])

    def test_a_build_verifies_its_read_back_exactly_when_its_caller_asked(self):
        # CADGEN_VERIFY_READBACK is one build's request (STORE.md §10). It travels with the
        # job, and a job whose caller did not set it runs without it, in a daemon started with it.
        import os

        from cadgen.daemon import worker

        with mock.patch.dict("os.environ", {"CADGEN_VERIFY_READBACK": "1"}):
            self.assertEqual(client.forwarded_env().get("CADGEN_VERIFY_READBACK"), "1")
            worker._apply_request_env({"env": {}})
            self.assertNotIn("CADGEN_VERIFY_READBACK", os.environ)
            worker._apply_request_env({"env": {"CADGEN_VERIFY_READBACK": "1"}})
            self.assertEqual(os.environ.get("CADGEN_VERIFY_READBACK"), "1")

    def test_the_daemon_popen_is_retained_by_an_owned_reaper(self):
        process = mock.Mock(pid=4321)
        finished = threading.Event()
        process.wait.side_effect = lambda: finished.set()
        client._reap_detached(process)
        self.assertTrue(finished.wait(1.0), "the detached process was not handed to its reaper")
        process.wait.assert_called_once_with()


class ServerRelaysTheDeath(unittest.TestCase):
    """The supervisor turns WorkerGone into its own frame, before the exit frame,
    and logs it -- ``cadgen daemon status`` cannot show a worker that is gone."""

    class _DyingWorker:
        pid = 777
        extra = False

        def __init__(self, exit_status: int = -9) -> None:
            self.sent: list[dict] = []
            self.exit_status = exit_status

        def send(self, request: dict) -> None:
            self.sent.append(request)

        def frames(self, **_kwargs):
            yield {"stream": "stdout", "data": "partial "}
            raise pool_mod.WorkerGone(
                f"worker 777 {pool_mod.describe_exit(self.exit_status)}", exit_status=self.exit_status
            )

        def alive(self) -> bool:
            return False

    class _Conn:
        def __init__(self) -> None:
            self.frames: list[dict] = []

        def send(self, raw: bytes) -> None:
            self.frames.append(json.loads(raw.decode("utf-8")))

    def test_worker_died_frame_precedes_the_exit_frame(self):
        worker = self._DyingWorker()
        pool = mock.Mock()
        pool.acquire.return_value = worker
        conn = self._Conn()
        request = {"tool": "step-compile", "argv": ["x.step"], "cwd": "/w", "prog": "cadgen step compile"}
        logged: list[str] = []
        jobs = JobLedger()
        with mock.patch.object(server, "_JOBS", jobs), \
                mock.patch.object(server, "_POOL", pool), \
                mock.patch.object(server, "_log", logged.append), \
                mock.patch.object(server, "CLIENT_LIVENESS_INTERVAL_SECONDS", 60.0):
            server._handle_request(conn, request)
        kinds = [next(iter(frame)) for frame in conn.frames if frame != {"stream": "stdout", "data": ""}]
        self.assertEqual(kinds, ["stream", "workerDied", "exit"])
        died = next(frame["workerDied"] for frame in conn.frames if "workerDied" in frame)
        self.assertEqual(jobs.snapshot()[0]["error"], died["detail"])
        self.assertEqual(died["pid"], 777)
        self.assertEqual(died["exitStatus"], -9)
        self.assertIn(pool_mod.describe_exit(-9), died["detail"])  # the worker's own words, as this platform names the signal
        self.assertEqual(conn.frames[-1], {"exit": 1})
        pool.release.assert_called_once_with(worker, healthy=False)
        self.assertTrue(any("died mid-job" in line for line in logged), logged)

    @unittest.skipIf(os.name == "nt", "a Windows worker's exit status is a code, never a signal")
    def test_a_worker_someone_stopped_is_no_crash_and_one_that_faulted_still_is(self):
        import signal

        # SIGTERM is someone stopping it (a person, a logout, a shutdown): the build was stopped, and the
        # client still hears how its worker went. A fault, or the kernel's kill for memory, is a crash.
        for status, ended in ((-signal.SIGTERM, "cancelled"), (-signal.SIGINT, "cancelled"), (-signal.SIGHUP, "cancelled"),
                              (-signal.SIGSEGV, "crashed"), (-signal.SIGKILL, "crashed"), (-signal.SIGABRT, "crashed")):
            with self.subTest(status=status):
                pool = mock.Mock()
                pool.acquire.return_value = self._DyingWorker(status)
                conn = self._Conn()
                build = mock.Mock()
                with mock.patch.object(server, "_JOBS", JobLedger()), mock.patch.object(server, "_POOL", pool), \
                        mock.patch.object(server, "_log"), mock.patch.object(server, "CLIENT_LIVENESS_INTERVAL_SECONDS", 60.0), \
                        mock.patch.object(server.telemetry, "build", return_value=build), \
                        mock.patch.object(server.telemetry, "worker_died") as worker_died:
                    server._handle_request(conn, {"tool": "step-compile", "argv": ["x.step"], "cwd": "/w",
                                                  "prog": "cadgen step compile"})
                self.assertEqual(build.finish.call_args.args[1], ended)
                self.assertEqual(worker_died.call_args_list, [mock.call(status)] if ended == "crashed" else [])
                self.assertEqual(next(frame["workerDied"]["exitStatus"] for frame in conn.frames if "workerDied" in frame), status)


class AWorkerThatCouldNotStart(unittest.TestCase):
    """A worker that could not start is a crash, unless the daemon's installation was removed under it:
    then no worker can start, and the daemon retires so its clients start the next from their own."""

    def handle(self, gone: bool):
        pool = mock.Mock()
        pool.acquire.side_effect = pool_mod.WorkerGone("worker 777 exited with code 106 before announcing itself",
                                                       exit_status=106)
        conn = ServerRelaysTheDeath._Conn()
        self.addCleanup(server._INSTALLATION_GONE.clear)
        with mock.patch.object(server, "_JOBS", JobLedger()), mock.patch.object(server, "_POOL", pool), \
                mock.patch.object(server, "_log"), \
                mock.patch.object(server.pool_mod, "installation_gone", return_value=gone), \
                mock.patch.object(server.telemetry, "worker_died") as worker_died:
            server._handle_request(conn, {"tool": "step-compile", "argv": ["x.step"], "cwd": "/w",
                                          "prog": "cadgen step compile"})
        self.assertEqual(conn.frames[-1], {"exit": 1})
        return worker_died

    def test_a_start_that_failed_is_a_crash(self):
        self.assertEqual(self.handle(gone=False).call_args_list, [mock.call(106)])
        self.assertFalse(server._INSTALLATION_GONE.is_set())

    def test_a_start_the_removed_installation_failed_is_none_and_retires_the_daemon(self):
        self.assertEqual(self.handle(gone=True).call_args_list, [])
        self.assertTrue(server._INSTALLATION_GONE.is_set())


class ServerStatusIdentity(unittest.TestCase):
    def test_status_keeps_the_loaded_startup_token_when_disk_code_changes(self):
        pool = mock.Mock()
        pool.snapshot.return_value = {"workers": []}
        broker = mock.Mock()
        broker.snapshot.return_value = {}
        jobs = mock.Mock()
        jobs.snapshot.return_value = []
        with mock.patch.object(server, "_POOL", pool), \
                mock.patch.object(server, "_BROKER", broker), \
                mock.patch.object(server, "_JOBS", jobs), \
                mock.patch.object(
                    server,
                    "compute_version_token",
                    side_effect=AssertionError("status reread the changed source tree"),
                ):
            status = server._status_payload("loaded-at-startup")
        self.assertEqual(status["token"], "loaded-at-startup")


class DescribeExit(unittest.TestCase):
    def test_signal_code_and_open_pipe_are_told_apart(self):
        import signal

        expected = "was killed by SIGKILL (signal 9)" if hasattr(signal, "SIGKILL") else "was killed by signal 9"
        self.assertEqual(pool_mod.describe_exit(-9), expected)
        self.assertEqual(pool_mod.describe_exit(2), "exited with code 2")
        self.assertEqual(pool_mod.describe_exit(None), "closed its output while still running")

    def test_an_unnamed_signal_is_not_described_twice(self):
        """99 is not a signal on any host, so this is the Windows wording for 9 --
        `was killed by signal 9 (signal 9)` was the stutter it used to produce."""
        self.assertEqual(pool_mod.describe_exit(-99), "was killed by signal 99")

    def test_a_windows_exit_status_is_a_code_not_a_signal(self):
        """Windows' Popen.wait returns a non-negative DWORD: a TerminateProcess
        kill comes back as the exit CODE, never as a negative signal."""
        self.assertEqual(pool_mod.describe_exit(9), "exited with code 9")


class ColdRerunSpelling(unittest.TestCase):
    """The rerun has to be paste-able in the shell the user is actually in.

    `cold_rerun_command` returns the COMMAND only: the env prefix is
    shell-specific and this code cannot know the shell. `set X=0 && cmd` works
    in cmd.exe and, in PowerShell, assigns a variable literally named `X=0`
    before failing on `&&` -- so the message offers both spellings under a
    neutral instruction instead of guessing.
    """

    COMMAND = "cadgen step compile tmp/noexh/noexh.step --force"

    def test_the_command_carries_no_env_prefix_on_either_platform(self):
        for name in ("posix", "nt"):
            with self.subTest(os_name=name), mock.patch.object(client.os, "name", name):
                spelled = client.cold_rerun_command(PAYLOAD)
                self.assertEqual(self.COMMAND, spelled)
                self.assertNotIn("CADGEN_DAEMON", spelled)

    def test_posix_keeps_the_one_line_env_prefix(self):
        with mock.patch.object(client.os, "name", "posix"):
            self.assertEqual(
                f"  CADGEN_DAEMON=0 {self.COMMAND}\n",
                client.cold_rerun_instructions(PAYLOAD),
            )

    def test_windows_offers_both_shells_under_a_neutral_instruction(self):
        with mock.patch.object(client.os, "name", "nt"):
            spelled = client.cold_rerun_instructions(PAYLOAD)
        self.assertIn("Set CADGEN_DAEMON=0 in the environment", spelled)
        self.assertIn(f"set CADGEN_DAEMON=0 && {self.COMMAND}", spelled)
        self.assertIn(f"$env:CADGEN_DAEMON='0'; {self.COMMAND}", spelled)
        # The bare command stands alone on its own line, so it is paste-able in
        # a shell neither spelling covers (Git Bash, fish, csh).
        self.assertIn(f"\n    {self.COMMAND}\n", spelled)

    def test_the_message_carries_the_spelling_for_the_running_platform(self):
        for name in ("posix", "nt"):
            with self.subTest(os_name=name), mock.patch.object(client.os, "name", name):
                message = client.worker_died_message(PAYLOAD, {"detail": "worker 1 exited with code 1"})
                self.assertIn(client.cold_rerun_instructions(PAYLOAD), message)
                self.assertIn("was NOT", message)

if __name__ == "__main__":
    unittest.main()
